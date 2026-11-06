"""Agent dùng queue/fence hiện có; từng HTTP attempt được giữ ledger trước khi gửi."""

import secrets
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from studio.access import Actor, require_editor
from studio.agent_intents import (
    INTENT_REVISION,
    approval_bypass_requested,
    currency_bypass_requested,
    interpret_requests,
    resolve_attached_normalization,
    resolve_plain_listing,
)
from studio.agent_preparation import (
    LOCAL_PREPARATION_REVISION,
    PREPARATION_REVISION,
    REVIEW_REVISION,
    interpret_review_reply,
    propose_normalization,
    validate_draft,
)
from studio.agent_tools import JobReference
from studio.agent_workflows import (
    advance,
    digest,
    lock_review_sources,
    own_workflow,
    owner,
    review_fingerprint,
    save,
    wait_for,
)
from studio.ai_gateway import typed_provider
from studio.assistant_api import own_conversation
from studio.assistant_tools import agent_catalogue
from studio.config import request_limit_reached, settings
from studio.contracts import DatasetProfile, WorkspacePolicy
from studio.contracts.agent import (
    AgentIntent,
    IntentBatch,
    IntentCatalogue,
    ReviewInterpretation,
    ReviewReply,
    WorkflowState,
)
from studio.contracts.assistant import AssistantContext
from studio.database import (
    AgentWorkflowRow,
    AuditRow,
    ConversationRow,
    JobRow,
    MembershipRow,
    MessageRow,
    TableRow,
    TraceRow,
    WorkspaceRow,
    now,
)
from studio.errors import DomainError, request_failure_message
from studio.repository import get_scoped, project_for_table, reserve_gemini_request

Fence = Callable[[Session, str, str], JobRow]
Finish = Callable[[Session, JobRow, dict[str, Any]], None]


def persist_request_failure(db: Session, job: JobRow) -> None:
    """Publish one durable terminal reply in the same transaction as job failure.

    The stable response ID and (job, role) constraint make recovery idempotent.
    Deleted conversations and revoked membership never resurrect private history.
    """
    if job.kind not in {"agent", "agent_review", "assistant"}:
        return
    message = db.scalar(
        select(MessageRow).where(MessageRow.job_id == job.id, MessageRow.role == "user")
    )
    if message is None or message.job_id != job.id:
        return
    conversation = db.get(ConversationRow, message.conversation_id, with_for_update=True)
    if (
        conversation is None
        or conversation.deleted_at
        or conversation.workspace_id != job.workspace_id
        or conversation.project_id != job.project_id
        or (job.payload.get("actor_id") and conversation.actor_id != job.payload["actor_id"])
        or db.get(MembershipRow, (job.workspace_id, conversation.actor_id)) is None
    ):
        return
    response_id = str(uuid5(NAMESPACE_URL, f"assistant-response:{job.id}"))
    if (
        db.scalar(
            select(MessageRow.id).where(MessageRow.job_id == job.id, MessageRow.role == "assistant")
        )
        is None
    ):
        db.add(
            MessageRow(
                id=response_id,
                conversation_id=conversation.id,
                job_id=job.id,
                role="assistant",
                text=request_failure_message(job.error_code or ""),
                context=message.context,
                answer=None,
            )
        )


def selection_fingerprint(catalogue: IntentCatalogue) -> str:
    """Fence a pronoun/ordinal against page or source changes during inference."""
    return digest(
        [
            catalogue.context.model_dump(mode="json"),
            catalogue.previous_query.model_dump(mode="json") if catalogue.previous_query else None,
            catalogue.previous_groups,
        ]
    )


def model_call(
    job_id: str,
    token: str,
    workflow_id: str,
    task: str,
    revision: str,
    factory: Any,
    fence: Fence,
    call: Callable[..., Any],
) -> Any:
    """Không giữ transaction khi gọi mạng; reserve trước và refence khi công bố."""
    with factory() as db:
        job = fence(db, job_id, token)
        row = db.get(AgentWorkflowRow, workflow_id)
        assert row is not None
        actor = owner(db, row)
        workspace = db.get(WorkspaceRow, actor.workspace_id)
        if workspace is None:
            raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy workspace.", 404)
        policy = WorkspacePolicy.model_validate(workspace.policy)
        state = WorkflowState.model_validate(row.detail)
        reply_choice = (
            ReviewReply.model_validate(job.payload["reply"]).model_choice
            if job is not None and job.kind == "agent_review"
            else None
        )
        choice = reply_choice or state.model_choice or "GEMINI"
        cloud = choice == "GEMINI"
        reservation = "AGENT_REQUEST_RESERVED" if cloud else "AGENT_LOCAL_REQUEST_RESERVED"
        prior = db.scalar(
            select(AuditRow.id).where(
                AuditRow.action == reservation, AuditRow.resource_id == job_id
            )
        )
        if prior:
            raise DomainError("AI_DELIVERY_UNKNOWN", "Request đã gửi; không tự gửi lại.", 409)
        workspace_id = actor.workspace_id
    provider = typed_provider(settings, choice)
    started, outcome = time.monotonic(), "VALIDATED"

    def reserve() -> bool:
        if cloud and (not settings.agent_cloud_enabled or settings.agent_request_budget == 0):
            return False
        with factory() as db:
            fence(db, job_id, token)
            row = db.get(AgentWorkflowRow, workflow_id, with_for_update=True)
            assert row is not None
            actor = owner(db, row)
            state = WorkflowState.model_validate(row.detail)
            if row.state == "CANCELLED_BEFORE_NEXT_STEP":
                return False
            if cloud and not reserve_gemini_request(db, workspace_id, job_id, settings):
                return False
            count = (
                (
                    db.scalar(
                        select(func.count())
                        .select_from(AuditRow)
                        .where(AuditRow.action == "AGENT_REQUEST_RESERVED")
                    )
                    or 0
                )
                if cloud
                else 0
            )
            prior = db.scalar(
                select(AuditRow.id).where(
                    AuditRow.action == reservation, AuditRow.resource_id == job_id
                )
            )
            if (
                prior
                or (cloud and request_limit_reached(count, settings.agent_request_budget))
                or state.model_calls >= settings.agent_max_model_calls
            ):
                db.rollback()
                return False
            state.model_calls += 1
            save(row, state)
            db.add(
                AuditRow(
                    workspace_id=workspace_id,
                    actor_id=actor.id,
                    action=reservation,
                    resource_id=job_id,
                )
            )
            db.commit()
            return True

    try:
        result = call(provider, policy, reserve)
        if isinstance(result, ReviewInterpretation):
            provider.usage["review_shape"] = dict(
                draft_fields=len(result.draft.fields) if result.draft else 0,
                has_plan=result.plan is not None,
                has_planning_request=result.planning_request is not None,
                has_suggestions=result.suggestions is not None,
                has_intent=result.intent is not None,
                question_count=len(result.questions),
            )
        return result
    except DomainError as exc:
        outcome = exc.code
        raise
    finally:
        provider.close()
        with factory() as db:
            db.add(
                TraceRow(
                    workspace_id=workspace_id,
                    job_id=job_id,
                    provider="GEMINI" if cloud else "OLLAMA",
                    task_id=task,
                    prompt_revision=(
                        LOCAL_PREPARATION_REVISION
                        if not cloud and task == "prepare_normalization"
                        else revision
                    ),
                    usage=provider.usage,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    outcome=outcome,
                )
            )
            db.commit()


def interpret(job_id: str, token: str, row_id: str, factory: Any, fence: Fence) -> None:
    with factory() as db:
        fence(db, job_id, token)
        row = db.get(AgentWorkflowRow, row_id, with_for_update=True)
        assert row is not None
        actor = owner(db, row)
        state = WorkflowState.model_validate(row.detail)
        if state.intent or row.state in {
            "CANCELLED_BEFORE_NEXT_STEP",
            "BLOCKED",
            "FAILED",
            "PARTIAL",
        }:
            return
        context = AssistantContext.model_validate(row.context)
        from studio.dataset_status import asks_processing_status

        if asks_processing_status(row.goal):
            state.intent = AgentIntent(intent="CHECK_DATASET_STATUS", dataset_ids=state.dataset_ids)
            save(row, state)
            db.commit()
            return
        catalogue = agent_catalogue(db, actor, context, state.dataset_ids, workflow_id=row.id)
        expected_selection = selection_fingerprint(catalogue)
        ids = [d.id for d in catalogue.datasets]
        parsing = db.scalar(
            select(JobRow)
            .where(
                JobRow.project_id == row.project_id,
                JobRow.workspace_id == actor.workspace_id,
                JobRow.kind == "parse",
                JobRow.payload["dataset_id"].astext.in_(ids),
                JobRow.status != "SUCCEEDED",
            )
            .order_by(JobRow.created_at)
            .limit(1)
        )
        if parsing:
            wait_for(
                db,
                row,
                state,
                "parse",
                parsing.payload["dataset_id"],
                JobReference(job_id=parsing.id, status=parsing.status),
            )
            save(row, state)
            db.commit()
            return
        parent = get_scoped(db, JobRow, row.parent_job_id, actor)
        command = parent.payload.get("command")
        goal = row.goal
        plain_listing = resolve_plain_listing(goal, catalogue)
        if plain_listing is not None:
            state.intent = plain_listing
            save(row, state)
            db.commit()
            return
        if approval_bypass_requested(goal) or currency_bypass_requested(goal):
            state.intent = AgentIntent(
                intent="UNSUPPORTED",
                questions=[
                    "Tôi không thể bỏ qua tiền tệ để cộng gộp số tiền. "
                    "Cần quy tắc quy đổi được duyệt."
                    if currency_bypass_requested(goal)
                    else "Tôi không thể tự phê duyệt ánh xạ hoặc quy tắc nghiệp vụ. "
                    "Bạn cần xem và duyệt quyết định trước khi thực hiện."
                ],
            )
            save(row, state)
            db.commit()
            return
        if command:
            state.intent = AgentIntent(intent=command, dataset_ids=state.dataset_ids)
            save(row, state)
            db.commit()
            return
        if state.model_choice in {"QWEN_8B", "QWEN_27B"}:
            attached = resolve_attached_normalization(goal, catalogue, state.dataset_ids)
            if attached is not None:
                state.intent = attached
                save(row, state)
                db.commit()
                return
    try:
        intents = model_call(
            job_id,
            token,
            row_id,
            "interpret_user_request",
            INTENT_REVISION,
            factory,
            fence,
            lambda provider, policy, reserve: interpret_requests(
                provider, [goal], catalogue, policy, reserve
            ),
        )
    except DomainError as exc:
        if exc.code not in {"INPUT_AMBIGUOUS", "QUERY_SEMANTICS_REQUIRED"}:
            raise
        intents = [AgentIntent(intent="CLARIFY", questions=[exc.message_vi])]
    with factory() as db:
        fence(db, job_id, token)
        row = db.get(AgentWorkflowRow, row_id, with_for_update=True)
        assert row is not None
        owner(db, row)
        if row.state != "CANCELLED_BEFORE_NEXT_STEP":
            state = WorkflowState.model_validate(row.detail)
            current_catalogue = agent_catalogue(
                db,
                owner(db, row),
                AssistantContext.model_validate(row.context),
                state.dataset_ids,
                workflow_id=row.id,
            )
            if selection_fingerprint(current_catalogue) != expected_selection:
                raise DomainError(
                    "STALE_CONTEXT",
                    "Trang dữ liệu hoặc ngữ cảnh đã thay đổi trong lúc xử lý. "
                    "Hãy gửi lại yêu cầu theo lựa chọn hiện tại.",
                    409,
                )
            state.intent = intents[0]
            save(row, state)
            db.commit()


def execute_agent(job_id: str, token: str, factory: Any, fence: Fence, finish: Finish) -> None:
    with factory() as db:
        job = fence(db, job_id, token)
        if job.kind == "agent":
            membership = db.get(MembershipRow, (job.workspace_id, job.payload["actor_id"]))
            if membership is None:
                raise DomainError("RESOURCE_NOT_FOUND", "Quyền đã bị thu hồi.", 404)
            actor = Actor(membership.actor_id, membership.workspace_id, membership.role)
            conversation = own_conversation(db, actor, job.payload["conversation_id"])
            message = db.get(MessageRow, job.payload["message_id"])
            if (
                message is None
                or message.job_id != job.id
                or message.conversation_id != conversation.id
            ):
                raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy yêu cầu.", 404)
            row_id = str(uuid5(NAMESPACE_URL, f"agent-workflow:{job.id}"))
            row = db.get(AgentWorkflowRow, row_id)
            if row is None:
                effective_context = AssistantContext.model_validate(message.context)
                if effective_context.dataset_id is None:
                    previous = db.scalar(
                        select(AgentWorkflowRow)
                        .where(
                            AgentWorkflowRow.conversation_id == conversation.id,
                            AgentWorkflowRow.actor_id == actor.id,
                            AgentWorkflowRow.state.in_(
                                ["COMPLETED", "PARTIAL", "BLOCKED", "FAILED", "WAITING_REVIEW"]
                            ),
                            AgentWorkflowRow.context["run_id"].astext.is_not(None),
                        )
                        .order_by(AgentWorkflowRow.created_at.desc(), AgentWorkflowRow.id.desc())
                        .limit(1)
                    )
                    if previous:
                        effective_context = AssistantContext.model_validate(previous.context)
                row = AgentWorkflowRow(
                    id=row_id,
                    workspace_id=actor.workspace_id,
                    project_id=conversation.project_id,
                    conversation_id=conversation.id,
                    actor_id=actor.id,
                    parent_job_id=job.id,
                    goal=message.text,
                    context=effective_context.model_dump(mode="json"),
                    fingerprint=digest(job.payload),
                    state="CREATED",
                    detail=WorkflowState(
                        dataset_ids=job.payload.get("dataset_ids", []),
                        model_choice=job.payload.get("model_choice"),
                    ).model_dump(),
                )
                db.add(row)
                db.commit()
        else:
            row_id = job.payload["workflow_id"]
            row = get_scoped(
                db, AgentWorkflowRow, row_id, Actor("worker", job.workspace_id, "viewer")
            )
            own_workflow(db, owner(db, row), row_id, lock=True)
            if row.project_id != job.project_id:
                raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy công việc.", 404)
            if job.kind == "agent_resume":
                # Nhận kết quả child trước khi chọn quyết định ngôn ngữ tiếp theo.
                advance(db, row)
                db.commit()
        kind = job.kind
    if kind == "agent_review":
        with factory() as db:
            job = fence(db, job_id, token)
            row = db.get(AgentWorkflowRow, row_id)
            assert row is not None
            actor = owner(db, row)
            require_editor(actor, db, row.id)
            reply = ReviewReply.model_validate(job.payload["reply"])
            state = WorkflowState.model_validate(row.detail)
            review = next((r for r in state.reviews if r.id == reply.review_id), None)
            if (
                row.state != "WAITING_REVIEW"
                or review is None
                or review.state != "OPEN"
                or review.nonce != reply.nonce
                or review.pending_reply_job_id != job_id
                or review.expires_at <= now()
                or review.fingerprint
                != review_fingerprint(
                    db, actor, review.kind, review.resource_id, review.evidence_refs
                )
            ):
                raise DomainError("STALE_CONTEXT", "Câu trả lời không còn thuộc thẻ đang chờ.", 409)
            catalogue = agent_catalogue(
                db,
                actor,
                AssistantContext.model_validate(row.context),
                state.dataset_ids,
                workflow_id=row.id,
            )
            clarification_goal = (
                row.goal
                + "\nCâu hỏi bổ sung: "
                + review.question
                + "\nNgười dùng trả lời: "
                + reply.text
            )
            expected_selection = selection_fingerprint(catalogue)
            if review.kind == "CLARIFICATION":
                catalogue = catalogue.model_copy(
                    update={"previous_goal": row.goal, "pending_question": review.question}
                )
        # Clarification uses the real scoped source catalogue. Mapping/rule edits
        # remain previews and can never be applied by this branch.
        output = model_call(
            job_id,
            token,
            row_id,
            "interpret_user_request"
            if review.kind == "CLARIFICATION"
            else "interpret_review_reply",
            INTENT_REVISION if review.kind == "CLARIFICATION" else REVIEW_REVISION,
            factory,
            fence,
            lambda provider, policy, reserve: (
                ReviewInterpretation(
                    intent=interpret_requests(provider, [reply.text], catalogue, policy, reserve)[0]
                )
                if review.kind == "CLARIFICATION"
                else interpret_review_reply(provider, review, reply.text, policy, reserve)
            ),
        )
        with factory() as db:
            job = fence(db, job_id, token)
            row = db.get(AgentWorkflowRow, row_id, with_for_update=True)
            assert row is not None
            actor = owner(db, row)
            require_editor(actor, db, row.id)
            state = WorkflowState.model_validate(row.detail)
            current = next((r for r in state.reviews if r.id == reply.review_id), None)
            if current:
                lock_review_sources(db, actor, current)
            if (
                row.state != "WAITING_REVIEW"
                or current is None
                or current.state != "OPEN"
                or current.nonce != reply.nonce
                or current.pending_reply_job_id != job_id
                or current.expires_at <= now()
                or current.fingerprint
                != review_fingerprint(
                    db, actor, current.kind, current.resource_id, current.evidence_refs
                )
            ):
                raise DomainError(
                    "STALE_CONTEXT", "Review đã thay đổi; không ghi đè lựa chọn.", 409
                )
            if output.draft:
                table = get_scoped(db, TableRow, current.resource_id, actor)
                validate_draft(output.draft, table.id, DatasetProfile.model_validate(table.profile))
                current.normalization_draft = output.draft
            if output.planning_request:
                from studio.reconciliation_contracts import (
                    validate_planning_suggestions,
                    validate_reconciliation_contract,
                )
                from studio.reconciliation_planner import (
                    missing_confirmations,
                    preview_plan,
                    validate_planning_request,
                )
                from studio.reconciliation_repository import selected_catalogue

                expected = current.planning_request
                supplied = output.planning_request
                if (
                    current.kind != "RECONCILIATION"
                    or not expected
                    or (supplied.left.canonical_id, supplied.right.canonical_id)
                    != (expected.left.canonical_id, expected.right.canonical_id)
                ):
                    raise DomainError("AI_INVALID_SOURCE", "Không được đổi nguồn đang chờ.")
                cats = selected_catalogue(
                    db,
                    actor,
                    row.project_id,
                    [
                        supplied.left.canonical_id,
                        supplied.right.canonical_id,
                    ],
                )
                validate_planning_request(supplied, cats, actor.workspace_id, row.project_id)
                if output.suggestions:
                    validate_planning_suggestions(output.suggestions, cats)
                plan_preview = preview_plan(
                    supplied, output.suggestions, cats[0].canonical.entity_kind, current.plan
                )
                if plan_preview:
                    validate_reconciliation_contract(
                        plan_preview, cats, actor.workspace_id, row.project_id
                    )
                current.planning_request = supplied
                current.suggestions = output.suggestions
                current.plan = plan_preview
                if not plan_preview and not output.questions:
                    missing = missing_confirmations(supplied)
                    output.questions = [
                        "Cần xác nhận thêm phạm vi: " + ", ".join(missing)
                        if missing
                        else "Cần hoàn thiện khóa, chỉ tiêu và quan hệ đối soát."
                    ]
            if output.plan:
                from studio.reconciliation_contracts import validate_reconciliation_contract
                from studio.reconciliation_repository import selected_catalogue

                p, expected = output.plan, current.planning_request
                if not expected or (p.left.canonical_id, p.right.canonical_id) != (
                    expected.left.canonical_id,
                    expected.right.canonical_id,
                ):
                    raise DomainError("AI_INVALID_SOURCE", "Không được đổi nguồn đang chờ.")
                cats = selected_catalogue(
                    db, actor, row.project_id, [p.left.canonical_id, p.right.canonical_id]
                )
                validate_reconciliation_contract(p, cats, actor.workspace_id, row.project_id)
                current.plan = p
            if output.intent:
                from studio.agent_intents import validate_intents

                catalogue = agent_catalogue(
                    db,
                    actor,
                    AssistantContext.model_validate(row.context),
                    state.dataset_ids,
                    workflow_id=row.id,
                )
                if selection_fingerprint(catalogue) != expected_selection:
                    raise DomainError(
                        "STALE_CONTEXT",
                        "Trang dữ liệu đã thay đổi trong lúc đọc câu trả lời. "
                        "Hãy kiểm tra lại lựa chọn.",
                        409,
                    )
                validated = validate_intents(
                    IntentBatch(intents=[output.intent]).model_dump_json(),
                    [
                        clarification_goal
                        if current.kind == "CLARIFICATION"
                        else row.goal + "\n" + reply.text
                    ],
                    catalogue,
                )
                output.intent = validated[0]
                current.reply_intent = output.intent
            continued = bool(
                current.kind == "CLARIFICATION"
                and output.intent
                and output.intent.intent not in {"CLARIFY", "CONTINUE_REVIEW"}
                and not output.questions
            )
            if (
                current.kind == "CLARIFICATION"
                and output.intent
                and output.intent.intent == "CLARIFY"
            ):
                output.questions = output.intent.questions
            current.reply_questions = output.questions or (
                []
                if any([output.draft, output.plan, output.intent, output.planning_request])
                else ["Cần thêm thông tin để tiếp tục."]
            )
            current.pending_reply_job_id = None
            current.nonce = secrets.token_hex(16)
            current.expires_at = now() + timedelta(minutes=30)
            # A successful correction resolves the current reply error; failed
            # messages/jobs remain immutable history. Unrelated failed steps stay visible.
            if not any(step.status in {"FAILED", "BLOCKED"} for step in state.steps):
                state.error_code = None
            if continued:
                assert output.intent is not None
                # No business approval: advance still enforces every mapping,
                # new-period and reconciliation-contract review gate.
                current.state = "DECIDED"
                current.decision_sha256 = digest(
                    dict(type="CLARIFICATION", intent=output.intent.model_dump(mode="json"))
                )
                state.intent = output.intent
                if reply.model_choice is not None:
                    state.model_choice = reply.model_choice
                state.error_code = None
                row.state = "RUNNING"
                db.add(
                    AuditRow(
                        workspace_id=actor.workspace_id,
                        actor_id=actor.id,
                        action="AGENT_CLARIFICATION_ANSWERED",
                        resource_id=current.id,
                    )
                )
                save(row, state)
                advance(db, row)
            conversation = own_conversation(db, actor, row.conversation_id)
            db.refresh(conversation, with_for_update=True)
            if conversation.deleted_at:
                raise DomainError("RESOURCE_NOT_FOUND", "Hội thoại đã được xóa.", 404)
            response_id = str(uuid5(NAMESPACE_URL, f"assistant-response:{job.id}"))
            if db.get(MessageRow, response_id) is None:
                db.add(
                    MessageRow(
                        id=response_id,
                        conversation_id=row.conversation_id,
                        job_id=job.id,
                        role="assistant",
                        text=""
                        if continued
                        else "Cần bổ sung thêm thông tin trên thẻ xác nhận."
                        if output.questions
                        else "Đã cập nhật bản xem trước. Hãy kiểm tra và xác nhận để tiếp tục.",
                        context=conversation.context,
                        answer=None,
                    )
                )
            if not continued:
                save(row, state)
            finish(
                db,
                job,
                {
                    "workflow_id": row.id,
                    "review_id": current.id,
                    "status": row.state if continued else "PREVIEW_REQUIRES_CONFIRMATION",
                },
            )
            db.commit()
        return
    if kind == "agent_prepare":
        with factory() as db:
            job = fence(db, job_id, token)
            row = db.get(AgentWorkflowRow, row_id)
            assert row is not None
            actor = owner(db, row)
            require_editor(actor, db, row.id)
            if row.state == "CANCELLED_BEFORE_NEXT_STEP":
                finish(db, job, {"drafts": [], "cancelled": True})
                db.commit()
                return
            if len(job.payload["table_ids"]) != 1:
                raise DomainError("AGENT_CONTEXT_LIMIT", "Mỗi bước chuẩn bị chỉ nhận một bảng.")
            table_id = job.payload["table_ids"][0]
            table = get_scoped(db, TableRow, table_id, actor)
            if project_for_table(db, table).id != row.project_id:
                raise DomainError("RESOURCE_NOT_FOUND", "Nguồn không thuộc dự án.", 404)
            import polars as pl

            from studio.contracts import SourceColumn
            from studio.database import ArtifactRow
            from studio.profiling import profile_table
            from studio.storage import checksum, storage_path

            artifact = get_scoped(db, ArtifactRow, table.artifact_id, actor)
            path = storage_path(settings.storage_root, artifact.storage_key)
            if checksum(path) != artifact.sha256:
                raise DomainError("PARSED_CHECKSUM_MISMATCH", "Dữ liệu nguồn không khớp checksum.")
            profile = profile_table(
                pl.read_parquet(path),
                [SourceColumn.model_validate(c) for c in table.parsed_contract["columns"]],
                table.id,
                actor.workspace_id,
                artifact.id,
            )
            from studio.database import DatasetRow, MappingRow, SchemaRow, VersionRow
            from studio.profiling import source_signature

            project = project_for_table(db, table)
            version = db.get(VersionRow, table.dataset_version_id)
            assert version is not None  # Bảng và project đã được kiểm scope ở trên.
            dataset = get_scoped(db, DatasetRow, version.dataset_id, actor)
            source_label = {"name": dataset.name[:180], "sheet": table.sheet[:120]}
            patterns = db.scalars(
                select(MappingRow)
                .where(
                    MappingRow.workspace_id == actor.workspace_id,
                    MappingRow.business_scope == project.business_scope,
                    MappingRow.signature == source_signature(profile),
                    MappingRow.status == "APPROVED",
                )
                .order_by(MappingRow.created_at.desc())
                .limit(3)
            ).all()
            mapping_context = {
                "business_scope": project.business_scope[:500],
                "request": row.goal[:1000],
                "approved_patterns": [
                    {
                        "schema": db.get(SchemaRow, m.schema_id).definition,
                        "decisions": m.decision["decisions"],
                    }
                    for m in patterns
                    if m.decision
                ],
            }
        draft = model_call(
            job_id,
            token,
            row_id,
            "prepare_normalization",
            PREPARATION_REVISION,
            factory,
            fence,
            lambda provider, policy, reserve: propose_normalization(
                provider,
                table_id,
                profile,
                policy,
                reserve,
                mapping_context | {"source": source_label} if provider.local else mapping_context,
            ),
        )
        with factory() as db:
            job = fence(db, job_id, token)
            row = db.get(AgentWorkflowRow, row_id)
            assert row is not None
            owner(db, row)
            from studio.mapping_verification import assess_table_mapping

            assessment = assess_table_mapping(db, owner(db, row), draft, enrich=True)
            draft = assessment.draft
            from studio.date_parsing import date_format, date_zone

            # Chỉ lấy facts từ mẫu đã duyệt cùng workspace/scope/signature và grain.
            # Đây vẫn là đề xuất mới, không chuyển approval của nguồn cũ sang nguồn mới.
            for pattern in mapping_context["approved_patterns"]:
                previous = pattern["schema"]
                if previous["grain"] != draft.grain or previous["entity_kind"] != draft.entity_kind:
                    continue
                fields = {f["id"]: f for f in previous["fields"]}
                by_source = {d["source_field"]: d for d in pattern["decisions"]}
                for field in draft.fields:
                    decision = by_source.get(field.source_field)
                    if not decision or decision["candidate_target"] != field.target_id:
                        continue
                    transform = decision["transformation_candidate"]
                    if (
                        field.data_type == "date"
                        and transform["op"] == "parse_date"
                        and field.date_format
                        and date_format(field.date_format) == date_format(transform["format"])
                    ):
                        date_zone(transform["timezone"])
                        field.timezone = transform["timezone"]
                    if (
                        field.data_type == "decimal"
                        and fields.get(field.target_id, {}).get("data_type") == "decimal"
                    ):
                        old = fields[field.target_id]
                        field.semantic_metric, field.amount_basis = (
                            old.get("semantic_metric"),
                            old.get("amount_basis"),
                        )
                break
            finish(db, job, {"drafts": [draft.model_dump(mode="json")]})
            db.commit()
        return
    interpret(job_id, token, row_id, factory, fence)
    with factory() as db:
        job = fence(db, job_id, token)
        row = db.get(AgentWorkflowRow, row_id, with_for_update=True)
        assert row is not None
        advance(db, row)
        if kind == "agent":
            conversation = db.get(
                ConversationRow, row.conversation_id, with_for_update=True, populate_existing=True
            )
            if conversation is None or conversation.deleted_at:
                raise DomainError("RESOURCE_NOT_FOUND", "Hội thoại đã được xóa.", 404)
            response_id = str(uuid5(NAMESPACE_URL, f"assistant-response:{job.id}"))
            if db.get(MessageRow, response_id) is None:
                db.add(
                    MessageRow(
                        id=response_id,
                        conversation_id=row.conversation_id,
                        job_id=job.id,
                        role="assistant",
                        text="Công việc đã được lưu.",
                        context=row.context,
                        answer=None,
                    )
                )
        finish(
            db,
            job,
            {"workflow_id": row.id, "conversation_id": row.conversation_id, "status": row.state},
        )
        db.commit()
