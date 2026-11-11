"""Agent dùng queue/fence hiện có; từng HTTP attempt được giữ ledger trước khi gửi."""

import re
import secrets
import time
import unicodedata
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from studio.access import Actor, require_editor
from studio.agent_intents import (
    INTENT_REVISION,
    explicit_source_filenames,
    export_query_for_intent,
    interpret_reconciliation_sequence,
    interpret_requests,
    named_reconciliation_files,
    requests_reconciliation_sequence,
    requests_source_preparation,
    requests_three_source_reconciliation,
    resolve_attached_normalization,
    resolve_deferred_export_read,
    resolve_named_reconciliation,
    resolve_native_read,
)
from studio.agent_preparation import (
    LOCAL_PREPARATION_REVISION,
    PREPARATION_REVISION,
    REVIEW_REVISION,
    interpret_review_reply,
    profiled_fields,
    propose_normalization,
    validate_draft,
)
from studio.agent_tools import JobReference
from studio.agent_workflows import (
    advance,
    consume_child,
    digest,
    lock_review_sources,
    own_workflow,
    owner,
    review_fingerprint,
    save,
    wait_for,
)
from studio.ai_gateway import typed_provider
from studio.assistant import plain_question
from studio.assistant_api import own_conversation
from studio.assistant_tools import agent_catalogue, select_project_datasets
from studio.config import request_limit_reached, settings
from studio.contracts import DatasetProfile, WorkspacePolicy
from studio.contracts.agent import (
    AgentIntent,
    DatasetBlock,
    IntentBatch,
    IntentCatalogue,
    NormalizationDraft,
    ProgressBlock,
    QualityDraft,
    ReconciliationSequence,
    ReviewInterpretation,
    ReviewReply,
    SequenceProgress,
    SequenceResolution,
    WorkflowState,
)
from studio.contracts.assistant import AssistantContext
from studio.contracts.reconciliation import PlanningRequest
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
from studio.dataset_status import (
    asks_processing_status,
    asks_source_inventory,
    read_processing_status,
    requests_project_sources,
    status_description,
)
from studio.errors import DomainError, request_failure_message
from studio.repository import (
    get_scoped,
    mapping_archived,
    project_for_table,
    reserve_gemini_request,
    retrying_gemini_response,
)

Fence = Callable[[Session, str, str], JobRow]
Finish = Callable[[Session, JobRow, dict[str, Any]], None]

QUALITY_CORRECTION = re.compile(r"^\s*(?:hãy\s+)?sửa\s+dòng\b", re.IGNORECASE)
QUALITY_VALUE = re.compile(
    r"^\s*(?:hãy\s+)?sửa\s+dòng\s+(này|\d+)\s+thành\s+(.+?)\s+theo\s+(.+?)\s*[.!]?\s*$",
    re.IGNORECASE,
)


def asks_for_current_source_evidence(text: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:(?:hay|vui long|ban|tu|chu dong) )*kiem tra (?:lai )?"
            r"(?:du lieu|cac nguon|ba nguon|3 nguon)(?: hien (?:hanh|tai)| dang co)?"
            r"(?: giup toi)?[.!?]*",
            " ".join(plain_question(text).split()),
        )
    )


def pending_planning_request(
    db: Session, actor: Actor, conversation_id: str, project_id: str
) -> PlanningRequest | None:
    waiting = db.scalar(
        select(AgentWorkflowRow)
        .where(
            AgentWorkflowRow.workspace_id == actor.workspace_id,
            AgentWorkflowRow.actor_id == actor.id,
            AgentWorkflowRow.project_id == project_id,
            AgentWorkflowRow.conversation_id == conversation_id,
            AgentWorkflowRow.state == "WAITING_REVIEW",
            AgentWorkflowRow.detail.contains(
                {"reviews": [{"kind": "RECONCILIATION", "state": "OPEN"}]}
            ),
        )
        .order_by(AgentWorkflowRow.updated_at.desc(), AgentWorkflowRow.id.desc())
        .limit(1)
    )
    if waiting is None:
        return None
    return next(
        (
            review.planning_request
            for review in reversed(WorkflowState.model_validate(waiting.detail).reviews)
            if review.kind == "RECONCILIATION"
            and review.state == "OPEN"
            and review.planning_request is not None
        ),
        None,
    )


def quality_reply(
    db: Session,
    actor: Actor,
    row: AgentWorkflowRow,
    state: WorkflowState,
    context: AssistantContext,
) -> None:
    """Chỉ điền bản nháp khi xác định duy nhất lỗi còn hiệu lực trong hội thoại."""
    from studio.data_quality import read_issues

    previous = db.scalars(
        select(AgentWorkflowRow)
        .where(
            AgentWorkflowRow.conversation_id == row.conversation_id,
            AgentWorkflowRow.workspace_id == actor.workspace_id,
            AgentWorkflowRow.project_id == row.project_id,
            AgentWorkflowRow.actor_id == actor.id,
            AgentWorkflowRow.id != row.id,
        )
        .order_by(AgentWorkflowRow.created_at.desc(), AgentWorkflowRow.id.desc())
        .limit(10)
    )
    blocks = next(
        (
            blocks
            for prior in previous
            if (
                blocks := [
                    block
                    for block in WorkflowState.model_validate(prior.detail).blocks
                    if isinstance(block, DatasetBlock)
                    and (not context.dataset_id or context.dataset_id == block.dataset_id)
                ]
            )
        ),
        [],
    )
    form = QUALITY_VALUE.fullmatch(row.goal)
    matches = []
    incomplete = False
    for block in blocks:
        try:
            issues = read_issues(db, actor, block.table_id, block.canonical_id, 0, 50)
        except DomainError as exc:
            if exc.status not in {404, 409}:
                raise
            continue
        if not issues["current"] or not issues["total"]:
            continue
        state.blocks.append(block.model_copy(update={"quality_draft": None}))
        incomplete = incomplete or issues["total"] > 50
        if form and issues["total"] <= 50:
            matches.extend(
                (block, issue, index)
                for index, source in enumerate(issues["items"])
                for issue in source["issues"]
                if form[1].lower() == "này" or str(source["source_row"]) == form[1]
            )
    if (
        form
        and not incomplete
        and len(matches) == 1
        and matches[0][1]["editable"]
        and len(form[2]) <= 2048
        and len(form[3]) <= 494
    ):
        block, issue, index = matches[0]
        draft = QualityDraft(
            source_row_id=issue["source_row_id"],
            field=issue["field"],
            code=issue["code"],
            value=form[2],
            reason=f"Theo {form[3]}",
            row_index=index,
        )
        state.blocks = [block.model_copy(update={"quality_draft": draft})]
    else:
        state.blocks.insert(
            0,
            ProgressBlock(
                text=(
                    "Bạn muốn sửa dòng và cột nào? Chọn lỗi trong bản hiện hành, "
                    "rồi nhập giá trị và căn cứ."
                )
            ),
        )
    if state.blocks and any(isinstance(block, DatasetBlock) for block in state.blocks):
        state.dataset_ids = list(
            dict.fromkeys(
                block.dataset_id for block in state.blocks if isinstance(block, DatasetBlock)
            )
        )
        state.intent = AgentIntent(intent="PREPARE_NORMALIZATION", dataset_ids=state.dataset_ids)
    row.state = "PARTIAL"
    save(row, state)


def effective_request_context(
    db: Session, actor: Actor, conversation_id: str, context: AssistantContext
) -> AssistantContext:
    """Use the same conversation-scoped run inheritance for dispatch and execution."""
    if context.dataset_id is not None or context.run_id is not None:
        return context
    previous = db.scalar(
        select(AgentWorkflowRow)
        .where(
            AgentWorkflowRow.conversation_id == conversation_id,
            AgentWorkflowRow.actor_id == actor.id,
            AgentWorkflowRow.state.in_(
                ["COMPLETED", "PARTIAL", "BLOCKED", "FAILED", "WAITING_REVIEW"]
            ),
            AgentWorkflowRow.context["run_id"].astext.is_not(None),
        )
        .order_by(AgentWorkflowRow.created_at.desc(), AgentWorkflowRow.id.desc())
        .limit(1)
    )
    return AssistantContext.model_validate(previous.context) if previous else context


def native_dispatch_eligible(db: Session, job: JobRow) -> bool:
    """Read-only eligibility hint; never mutate payload/idempotency or call a provider.

    Actual execution rechecks scope and is forbidden from falling back to AI on
    the native lane. Stale/malformed hints remain on the ordinary inference lane.
    """
    try:
        if job.kind == "agent":
            member = db.get(MembershipRow, (job.workspace_id, job.payload["actor_id"]))
            if member is None or member.role not in {"owner", "editor"}:
                return False
            actor = Actor(member.actor_id, member.workspace_id, member.role)
            conversation = own_conversation(db, actor, job.payload["conversation_id"])
            message = db.get(MessageRow, job.payload["message_id"])
            if (
                not message
                or message.job_id != job.id
                or message.conversation_id != conversation.id
            ):
                return False
            context = effective_request_context(
                db, actor, conversation.id, AssistantContext.model_validate(message.context)
            )
            if not job.payload.get("command") and QUALITY_CORRECTION.match(message.text):
                return True
            if not job.payload.get("command") and asks_for_current_source_evidence(message.text):
                return (
                    pending_planning_request(db, actor, conversation.id, context.project_id)
                    is not None
                )
            if (
                asks_processing_status(message.text)
                or asks_source_inventory(message.text)
                or requests_source_preparation(message.text)
            ):
                return True
            if not job.payload.get("command") and (
                requests_reconciliation_sequence(message.text)
                or requests_three_source_reconciliation(message.text)
            ):
                return False
            catalogue = agent_catalogue(
                db,
                actor,
                context,
                job.payload.get("dataset_ids", []),
                dataset_names=(
                    named_reconciliation_files(message.text)
                    or tuple(explicit_source_filenames(message.text))
                    or None
                ),
            )
            return bool(
                resolve_native_read(message.text, catalogue)
                or resolve_named_reconciliation(message.text, catalogue)
            )
        if job.kind == "agent_review":
            row = db.get(AgentWorkflowRow, job.payload["workflow_id"])
            if row is None or row.workspace_id != job.workspace_id:
                return False
            member = db.get(MembershipRow, (job.workspace_id, row.actor_id))
            if member is None or member.role not in {"owner", "editor"}:
                return False
            actor = Actor(member.actor_id, member.workspace_id, member.role)
            own_conversation(db, actor, row.conversation_id)
            state = WorkflowState.model_validate(row.detail)
            reply = ReviewReply.model_validate(job.payload["reply"])
            review = next((r for r in state.reviews if r.id == reply.review_id), None)
            if review is None or review.state != "OPEN":
                return False
            if review.kind == "RECONCILIATION":
                return bool(
                    review.planning_request and asks_for_current_source_evidence(reply.text)
                )
            if review.kind != "CLARIFICATION":
                return False
            if requests_reconciliation_sequence(row.goal) or requests_three_source_reconciliation(
                row.goal
            ):
                return False
            catalogue = agent_catalogue(
                db,
                actor,
                AssistantContext.model_validate(row.context),
                state.dataset_ids,
                workflow_id=row.id,
            )
            catalogue = catalogue.model_copy(
                update={"previous_goal": row.goal, "pending_question": review.question}
            )
            return resolve_deferred_export_read(reply.text, catalogue) is not None
    except (DomainError, ValidationError, KeyError, TypeError):
        return False
    return False


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
        retrying = cloud and retrying_gemini_response(db, job)
        if prior and not retrying:
            raise DomainError("AI_DELIVERY_UNKNOWN", "Request đã gửi; không tự gửi lại.", 409)
        workspace_id = actor.workspace_id
    provider = typed_provider(settings, choice)
    started, outcome = time.monotonic(), "VALIDATED"
    reserved = False

    def reserve() -> bool:
        nonlocal reserved
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
                reserved
                or (prior and not retrying)
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
            reserved = True
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


def interpret(
    job_id: str, token: str, row_id: str, factory: Any, fence: Fence, *, native_only: bool = False
) -> None:
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
        if row.waiting_job_id:
            if not consume_child(db, row, state):
                save(row, state)
                db.commit()
                return
            save(row, state)
            db.commit()
        context = AssistantContext.model_validate(row.context)
        parent = get_scoped(db, JobRow, row.parent_job_id, actor)
        command = parent.payload.get("command")
        goal = row.goal
        if not command and QUALITY_CORRECTION.match(goal):
            quality_reply(db, actor, row, state, context)
            db.commit()
            return
        if not command and asks_for_current_source_evidence(goal):
            pending = pending_planning_request(db, actor, row.conversation_id, row.project_id)
            if pending:
                from studio.reconciliation_repository import planning_source_evidence

                evidence = planning_source_evidence(db, actor, row.project_id, pending)
                for source in evidence:
                    rows = f"{source.valid_rows:,}".replace(",", ".")
                    dates = ", ".join(
                        f"{item.field} từ {item.first} đến {item.last}"
                        for item in source.observed_dates
                    )
                    state.blocks.append(
                        ProgressBlock(
                            text=(
                                f"{source.name} · phiên bản {source.dataset_revision}"
                                f" · {rows} dòng dùng được"
                                + (
                                    f" · {source.excluded_rows} dòng đã loại"
                                    if source.excluded_rows
                                    else ""
                                )
                                + (f" · {dates} ({source.observation_timezone})" if dates else "")
                            )
                        )
                    )
                state.blocks.append(
                    ProgressBlock(
                        text="Đã kiểm tra lại bản chuẩn hóa. Xem dữ kiện trên thẻ đang chờ."
                    )
                )
                state.intent = AgentIntent(intent="CHECK_DATASET_STATUS")
                row.state = "COMPLETED"
                save(row, state)
                db.commit()
                return
        status_request = asks_processing_status(goal) or asks_source_inventory(goal)
        propose_pairs = command is None and requests_three_source_reconciliation(goal)
        native_preparation = (
            command is None and not propose_pairs and requests_source_preparation(goal)
        )
        prepare = command == "PREPARE_NORMALIZATION" or native_preparation
        sequence_requested = not (command or prepare) and (
            propose_pairs or requests_reconciliation_sequence(goal)
        )
        if sequence_requested:
            require_editor(actor, db, row.id)
            context = AssistantContext(project_id=context.project_id)
            row.context = context.model_dump(mode="json")
        if (
            status_request
            or prepare
            or (command is None and requests_source_preparation(goal, require_selector=False))
        ):
            if requests_project_sources(goal) and not state.steps:
                if state.dataset_ids:
                    select_project_datasets(db, actor, context.project_id, state.dataset_ids)
                state.dataset_ids = []
                context = AssistantContext(project_id=context.project_id)
            else:
                context = AssistantContext(
                    project_id=context.project_id, dataset_id=context.dataset_id
                )
            row.context = context.model_dump(mode="json")
        if status_request:
            state.intent = AgentIntent(intent="CHECK_DATASET_STATUS", dataset_ids=state.dataset_ids)
            save(row, state)
            db.commit()
            return
        files = (
            None
            if (sequence_requested and not propose_pairs) or command
            else (
                (None if prepare or propose_pairs else named_reconciliation_files(goal))
                or tuple(explicit_source_filenames(goal))
                or None
            )
        )
        if prepare:
            selected = state.dataset_ids or (
                [context.dataset_id] if context.dataset_id and not files else []
            )
            datasets = select_project_datasets(db, actor, context.project_id, selected, files)
            ids = [dataset.id for dataset in datasets]
            names = {unicodedata.normalize("NFC", dataset.name).casefold() for dataset in datasets}
            quantity = re.search(
                r"\b(?:ca )?(ba|3|hai|2) (?:bo du lieu|du lieu|nguon|file|tep)\b",
                plain_question(goal),
            )
            expected = (3 if quantity[1] in {"ba", "3"} else 2) if quantity else None
            if (
                not ids
                or (files and (names != set(files) or len(ids) != len(names)))
                or (expected and len(ids) != expected)
            ):
                state.intent = AgentIntent(
                    intent="CLARIFY",
                    questions=[
                        "Chưa xác định được đủ nguồn trong phạm vi yêu cầu. "
                        "Hãy nêu tên tệp hoặc yêu cầu chuẩn bị toàn bộ dự án."
                    ],
                )
                save(row, state)
                db.commit()
                return
            # Mỗi workflow ghim phạm vi lúc nhận yêu cầu. Tin nhắn tiếp theo đọc lại dự án.
            state.dataset_ids = ids
            if native_preparation:
                statuses = read_processing_status(db, actor, context, ids)
                state.blocks.append(
                    ProgressBlock(text=f"Khi bắt đầu: {len(ids)} nguồn trong phạm vi yêu cầu.")
                )
                state.blocks.extend(
                    ProgressBlock(
                        text="\n".join(
                            status_description(s) for s in statuses if s.dataset_id == dataset_id
                        )
                    )
                    for dataset_id in ids
                )
            state.intent = AgentIntent(intent="PREPARE_NORMALIZATION", dataset_ids=ids)
            save(row, state)
            db.commit()
            return
        catalogue = agent_catalogue(
            db, actor, context, state.dataset_ids, workflow_id=row.id, dataset_names=files
        )
        expected_selection = selection_fingerprint(catalogue)
        ids = [d.id for d in catalogue.datasets]
        if command == "PREPARE_UPLOAD":
            if not state.dataset_ids:
                raise DomainError("INPUT_AMBIGUOUS", "Cần chọn các tệp vừa tải lên.", 422)
            state.prepare_upload = True
            state.intent = AgentIntent(
                intent="PREPARE_NORMALIZATION", dataset_ids=state.dataset_ids
            )
            save(row, state)
            db.commit()
            return
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
        plain_listing = (
            None
            if sequence_requested
            else resolve_native_read(goal, catalogue)
            or resolve_named_reconciliation(goal, catalogue)
        )
        if plain_listing is not None:
            state.export_query = export_query_for_intent(plain_listing, catalogue)
            if files and plain_listing.intent == "RECONCILE_DATASETS":
                if not state.dataset_ids:
                    state.dataset_ids = ids
                # An explicit new pair owns its planning context. Old case/group
                # references cannot follow it into the new verified run.
                context = AssistantContext(project_id=context.project_id)
                row.context = context.model_dump(mode="json")
            if plain_listing.intent == "SUMMARIZE_RESULTS":
                context.group_id = context.case_id = None
                row.context = context.model_dump(mode="json")
            if plain_listing.result_position is not None:
                # Pin the displayed group before committing the intent. The user
                # may sort or page the previous table before advance runs.
                context.group_id = catalogue.previous_groups[plain_listing.result_position - 1]
                context.case_id = None
                row.context = context.model_dump(mode="json")
                plain_listing = plain_listing.model_copy(update={"result_position": None})
            state.intent = plain_listing
            save(row, state)
            db.commit()
            return
        if command:
            state.intent = AgentIntent(intent=command, dataset_ids=state.dataset_ids)
            save(row, state)
            db.commit()
            return
        if state.model_choice == "QWEN_27B":
            attached = resolve_attached_normalization(goal, catalogue, state.dataset_ids)
            if attached is not None:
                state.intent = attached
                save(row, state)
                db.commit()
                return
    if native_only:
        raise DomainError(
            "STALE_CONTEXT", "Ngữ cảnh đọc đã đổi; hãy kiểm tra lại trước khi gửi.", 409
        )
    sequence = None
    try:
        interpreted = model_call(
            job_id,
            token,
            row_id,
            "interpret_user_request",
            INTENT_REVISION,
            factory,
            fence,
            lambda provider, policy, reserve: (
                interpret_reconciliation_sequence(
                    provider, goal, [], catalogue, policy, reserve, propose_pairs=True
                )
                if propose_pairs
                else interpret_reconciliation_sequence(
                    provider, goal, [], catalogue, policy, reserve
                )
                if sequence_requested
                else interpret_requests(provider, [goal], catalogue, policy, reserve)
            ),
        )
        if isinstance(interpreted, SequenceResolution):
            sequence = interpreted.sequence
            intents = [
                AgentIntent(
                    intent="PREPARE_NORMALIZATION" if sequence else "CLARIFY",
                    questions=[interpreted.question] if interpreted.question else [],
                )
            ]
        else:
            intents = interpreted
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
            if sequence_requested:
                row.context = context.model_dump(mode="json")
            current_catalogue = agent_catalogue(
                db,
                owner(db, row),
                AssistantContext.model_validate(row.context),
                state.dataset_ids,
                workflow_id=row.id,
                dataset_names=files,
            )
            if selection_fingerprint(current_catalogue) != expected_selection:
                raise DomainError(
                    "STALE_CONTEXT",
                    "Trang dữ liệu hoặc ngữ cảnh đã thay đổi trong lúc xử lý. "
                    "Hãy gửi lại yêu cầu theo lựa chọn hiện tại.",
                    409,
                )
            state.intent = intents[0]
            if state.intent.intent == "PREPARE_NORMALIZATION" and not state.dataset_ids:
                state.dataset_ids = state.intent.dataset_ids or ids
            if sequence:
                initialize_sequence(state, sequence, propose_pairs=propose_pairs)
            state.export_query = export_query_for_intent(state.intent, current_catalogue)
            save(row, state)
            db.commit()


def initialize_sequence(
    state: WorkflowState, sequence: ReconciliationSequence, *, propose_pairs: bool = False
) -> None:
    state.sequence_progress = SequenceProgress(sequence=sequence, propose_pairs=propose_pairs)
    state.dataset_ids = list(
        dict.fromkeys(
            ident
            for pair in sequence.pairs
            for ident in (pair.left_dataset_id, pair.right_dataset_id)
        )
    )
    if propose_pairs:
        state.intent = AgentIntent(intent="RECONCILE_DATASETS", dataset_ids=state.dataset_ids)
    else:
        state.prepare_upload = True


def execute_agent(
    job_id: str,
    token: str,
    factory: Any,
    fence: Fence,
    finish: Finish,
    *,
    native_only: bool = False,
) -> None:
    with factory() as db:
        job = fence(db, job_id, token)
        approved_refresh = (
            job.kind == "agent_resume" and job.payload.get("approved_sources") is True
        )
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
                effective_context = effective_request_context(
                    db, actor, conversation.id, AssistantContext.model_validate(message.context)
                )
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
                    ).model_dump(
                        exclude={"sequence_progress", "sequence_clarifications", "resumable_job_id"}
                    ),
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
                if job.payload.get("quality_refresh"):
                    if row.state == "PARTIAL" and row.waiting_job_id is None:
                        state = WorkflowState.model_validate(row.detail)
                        if state.intent and state.intent.intent == "PREPARE_NORMALIZATION":
                            row.state = "WAITING_REVIEW"
                            advance(db, row, approved_only=True)
                else:
                    advance(db, row, approved_only=approved_refresh)
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
            propose_pairs = requests_three_source_reconciliation(row.goal)
            sequence_reply = review.kind == "CLARIFICATION" and (
                propose_pairs or requests_reconciliation_sequence(row.goal)
            )
            sequence_answers = [*state.sequence_clarifications[-3:], reply.text]
            original_goal = row.goal
            inspect_sources = (
                review.kind == "RECONCILIATION"
                and review.planning_request is not None
                and asks_for_current_source_evidence(reply.text)
            )
            planning_sources = None
            if review.kind == "RECONCILIATION" and review.planning_request and not inspect_sources:
                from studio.reconciliation_repository import selected_catalogue

                request = review.planning_request
                planning_sources = selected_catalogue(
                    db,
                    actor,
                    row.project_id,
                    [request.left.canonical_id, request.right.canonical_id],
                )
            expected_selection = selection_fingerprint(catalogue)
            if review.kind == "CLARIFICATION":
                catalogue = catalogue.model_copy(
                    update={"previous_goal": row.goal, "pending_question": review.question}
                )
        # Clarification uses the real scoped source catalogue. Mapping/rule edits
        # remain previews and can never be applied by this branch.
        native_reply = (
            resolve_deferred_export_read(reply.text, catalogue)
            if review.kind == "CLARIFICATION" and not sequence_reply
            else None
        )
        if native_only and native_reply is None and not inspect_sources:
            raise DomainError("STALE_CONTEXT", "Ngữ cảnh trả lời đã đổi; hãy kiểm tra lại.", 409)
        output = (
            ReviewInterpretation()
            if inspect_sources
            else ReviewInterpretation(intent=native_reply)
            if native_reply is not None
            else model_call(
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
                    interpret_reconciliation_sequence(
                        provider,
                        original_goal,
                        sequence_answers,
                        catalogue,
                        policy,
                        reserve,
                        propose_pairs=True,
                    )
                    if sequence_reply and propose_pairs
                    else interpret_reconciliation_sequence(
                        provider, original_goal, sequence_answers, catalogue, policy, reserve
                    )
                    if sequence_reply
                    else ReviewInterpretation(
                        intent=interpret_requests(
                            provider, [reply.text], catalogue, policy, reserve
                        )[0]
                    )
                    if review.kind == "CLARIFICATION"
                    else interpret_review_reply(
                        provider, review, reply.text, policy, reserve, planning_sources
                    )
                ),
            )
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
            resolved_sequence = None
            if inspect_sources and current.planning_request:
                from studio.reconciliation_repository import planning_source_evidence

                current.source_evidence = planning_source_evidence(
                    db, actor, row.project_id, current.planning_request
                )
            if isinstance(output, SequenceResolution):
                state.sequence_clarifications = sequence_answers
                if output.sequence is not None:
                    resolved_sequence = output.sequence
                    output = ReviewInterpretation(
                        intent=AgentIntent(intent="PREPARE_NORMALIZATION")
                    )
                else:
                    output = ReviewInterpretation(
                        questions=[output.question or "Chọn nguồn cho từng cặp đối soát."]
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
                validated = (
                    [output.intent]
                    if sequence_reply
                    else validate_intents(
                        IntentBatch(intents=[output.intent]).model_dump_json(),
                        [
                            clarification_goal
                            if current.kind == "CLARIFICATION"
                            else row.goal + "\n" + reply.text
                        ],
                        catalogue,
                    )
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
                if inspect_sources
                or any([output.draft, output.plan, output.intent, output.planning_request])
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
                    dict(
                        type="CLARIFICATION",
                        intent=output.intent.model_dump(mode="json", exclude={"export_scope"}),
                    )
                )
                state.intent = output.intent
                if resolved_sequence:
                    initialize_sequence(state, resolved_sequence, propose_pairs=propose_pairs)
                state.export_query = export_query_for_intent(state.intent, catalogue)
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
                        else "Đã kiểm tra lại bản chuẩn hóa. Xem dữ kiện trên thẻ đang chờ."
                        if inspect_sources
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
            if job.payload.get("profile_only"):
                from studio.mapping_verification import assess_table_mapping

                profile = DatasetProfile.model_validate(table.profile)
                proposal = NormalizationDraft(
                    table_id=table.id,
                    entity_kind="unknown",
                    grain="unknown",
                    fields=profiled_fields(profile),
                )
                draft = assess_table_mapping(db, actor, proposal, enrich=True).draft
                finish(db, job, {"drafts": [draft.model_dump(mode="json")]})
                db.commit()
                return
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
                    ~mapping_archived(),
                )
                .order_by(MappingRow.created_at.desc())
                .limit(3)
            ).all()
            mapping_context = {
                "source": source_label,
                "business_scope": (
                    None
                    if project.business_scope.startswith("UNCONFIRMED:")
                    else project.business_scope[:120]
                ),
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
                mapping_context,
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
    if not approved_refresh and not job.payload.get("quality_refresh"):
        interpret(job_id, token, row_id, factory, fence, native_only=native_only)
    with factory() as db:
        job = fence(db, job_id, token)
        row = db.get(AgentWorkflowRow, row_id, with_for_update=True)
        assert row is not None
        if not job.payload.get("quality_refresh"):
            advance(db, row, approved_only=approved_refresh)
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
