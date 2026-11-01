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
from studio.agent_intents import INTENT_REVISION, interpret_requests
from studio.agent_preparation import (
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
    own_workflow,
    owner,
    review_fingerprint,
    save,
    wait_for,
)
from studio.ai_gateway import GeminiProvider
from studio.assistant_api import own_conversation
from studio.assistant_tools import agent_catalogue
from studio.config import settings
from studio.contracts import DatasetProfile, WorkspacePolicy
from studio.contracts.agent import AgentIntent, IntentBatch, ReviewReply, WorkflowState
from studio.contracts.assistant import AssistantContext
from studio.database import (
    AgentWorkflowRow,
    AuditRow,
    JobRow,
    MembershipRow,
    MessageRow,
    TableRow,
    TraceRow,
    WorkspaceRow,
    now,
)
from studio.errors import DomainError
from studio.repository import get_scoped, project_for_table, reserve_gemini_request

Fence = Callable[[Session, str, str], JobRow]
Finish = Callable[[Session, JobRow, dict[str, Any]], None]


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
        fence(db, job_id, token)
        row = db.get(AgentWorkflowRow, workflow_id)
        assert row is not None
        actor = owner(db, row)
        workspace = db.get(WorkspaceRow, actor.workspace_id)
        if workspace is None:
            raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy workspace.", 404)
        policy = WorkspacePolicy.model_validate(workspace.policy)
        prior = db.scalar(
            select(AuditRow.id).where(
                AuditRow.action == "AGENT_REQUEST_RESERVED", AuditRow.resource_id == job_id
            )
        )
        if prior:
            raise DomainError("AI_DELIVERY_UNKNOWN", "Request đã gửi; không tự gửi lại.", 409)
        workspace_id = actor.workspace_id
    provider = GeminiProvider(settings)
    started, outcome = time.monotonic(), "VALIDATED"

    def reserve() -> bool:
        if not settings.agent_cloud_enabled or settings.agent_request_budget == 0:
            return False
        with factory() as db:
            fence(db, job_id, token)
            row = db.get(AgentWorkflowRow, workflow_id, with_for_update=True)
            assert row is not None
            actor = owner(db, row)
            state = WorkflowState.model_validate(row.detail)
            if row.state == "CANCELLED_BEFORE_NEXT_STEP":
                return False
            allowed = reserve_gemini_request(db, workspace_id, job_id, settings)
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(AuditRow)
                    .where(AuditRow.action == "AGENT_REQUEST_RESERVED")
                )
                or 0
            )
            prior = db.scalar(
                select(AuditRow.id).where(
                    AuditRow.action == "AGENT_REQUEST_RESERVED", AuditRow.resource_id == job_id
                )
            )
            if (
                not allowed
                or prior
                or count >= settings.agent_request_budget
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
                    action="AGENT_REQUEST_RESERVED",
                    resource_id=job_id,
                )
            )
            db.commit()
            return True

    try:
        return call(provider, policy, reserve)
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
                    provider="GEMINI",
                    task_id=task,
                    prompt_revision=revision,
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
        catalogue = agent_catalogue(db, actor, context, state.dataset_ids)
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
        if command:
            state.intent = AgentIntent(intent=command, dataset_ids=state.dataset_ids)
            save(row, state)
            db.commit()
            return
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
    with factory() as db:
        fence(db, job_id, token)
        row = db.get(AgentWorkflowRow, row_id, with_for_update=True)
        assert row is not None
        owner(db, row)
        if row.state != "CANCELLED_BEFORE_NEXT_STEP":
            state = WorkflowState.model_validate(row.detail)
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
                if effective_context.run_id is None:
                    previous = db.scalar(
                        select(AgentWorkflowRow)
                        .where(
                            AgentWorkflowRow.conversation_id == conversation.id,
                            AgentWorkflowRow.actor_id == actor.id,
                            AgentWorkflowRow.state.in_(["COMPLETED", "PARTIAL"]),
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
                        dataset_ids=job.payload.get("dataset_ids", [])
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
        output = model_call(
            job_id,
            token,
            row_id,
            "interpret_review_reply",
            REVIEW_REVISION,
            factory,
            fence,
            lambda provider, policy, reserve: interpret_review_reply(
                provider, review, reply.text, policy, reserve
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
                    db, actor, AssistantContext.model_validate(row.context), state.dataset_ids
                )
                validate_intents(
                    IntentBatch(intents=[output.intent]).model_dump_json(),
                    [row.goal + "\n" + reply.text],
                    catalogue,
                )
                # Chưa áp dụng intent: chỉ đổi bản preview, đợi human decision.
                current.reply_intent = output.intent
            current.reply_questions = output.questions or (
                []
                if any([output.draft, output.plan, output.intent])
                else ["Cần thêm thông tin để tiếp tục."]
            )
            current.pending_reply_job_id = None
            current.nonce = secrets.token_hex(16)
            current.expires_at = now() + timedelta(minutes=30)
            save(row, state)
            finish(
                db,
                job,
                {
                    "workflow_id": row.id,
                    "review_id": current.id,
                    "status": "PREVIEW_REQUIRES_CONFIRMATION",
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
            profile = DatasetProfile.model_validate(table.profile)
        draft = model_call(
            job_id,
            token,
            row_id,
            "prepare_normalization",
            PREPARATION_REVISION,
            factory,
            fence,
            lambda provider, policy, reserve: propose_normalization(
                provider, table_id, profile, policy, reserve
            ),
        )
        with factory() as db:
            job = fence(db, job_id, token)
            row = db.get(AgentWorkflowRow, row_id)
            assert row is not None
            owner(db, row)
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
