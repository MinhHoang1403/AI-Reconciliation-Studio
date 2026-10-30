"""Queue/fencing hiện có công bố đúng một câu trả lời; không gửi lại provider mù."""

import time
from collections.abc import Callable
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from studio.access import Actor
from studio.ai_gateway import route_ai_task
from studio.assistant import PROMPT_REVISION, answer_question, plain_question, workflow_proposal
from studio.assistant_api import own_conversation
from studio.assistant_tools import build_fact_set, read_tool
from studio.config import settings
from studio.contracts import WorkspacePolicy
from studio.contracts.assistant import AssistantAnswer, AssistantContext, ToolRequest
from studio.database import AuditRow, JobRow, MembershipRow, MessageRow, TraceRow, WorkspaceRow
from studio.errors import DomainError
from studio.repository import reserve_gemini_request


def execute_assistant(
    job_id: str,
    token: str,
    factory: Any,
    fence: Callable[[Session, str, str], JobRow],
    finish: Callable[[Session, JobRow, dict[str, Any]], None],
) -> None:
    """Đọc scoped facts trước; fence/owner/tombstone kiểm lại trước atomic publish."""
    started = time.monotonic()
    with factory() as db:
        job = fence(db, job_id, token)
        membership = db.get(MembershipRow, (job.workspace_id, job.payload["actor_id"]))
        if membership is None:
            raise DomainError(
                "RESOURCE_NOT_FOUND", "Quyền truy cập hội thoại không còn hợp lệ.", 404
            )
        actor = Actor(membership.actor_id, membership.workspace_id, membership.role)
        conversation = own_conversation(db, actor, job.payload["conversation_id"])
        conversation_id = conversation.id
        message = db.get(MessageRow, job.payload["message_id"])
        if not message or message.conversation_id != conversation.id or message.job_id != job.id:
            raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy câu hỏi trong hội thoại.", 404)
        context = AssistantContext.model_validate(message.context)
        facts = build_fact_set(db, actor, context)
        question = message.text
        workspace = db.get(WorkspaceRow, actor.workspace_id)
        assert workspace is not None
        policy = WorkspacePolicy.model_validate(workspace.policy)
        prior_attempt = db.scalar(
            select(AuditRow.id).where(
                AuditRow.action == "ASSISTANT_REQUEST_RESERVED", AuditRow.resource_id == job.id
            )
        )
        if prior_attempt:
            raise DomainError(
                "AI_DELIVERY_UNKNOWN", "Request trước chưa rõ delivery; không tự gửi lại.", 409
            )
        previous = list(
            db.scalars(
                select(MessageRow)
                .where(
                    MessageRow.conversation_id == conversation.id, MessageRow.role == "assistant"
                )
                .order_by(MessageRow.created_at.desc(), MessageRow.id.desc())
                .limit(20)
            )
        )
        cached = None
        for previous_message in previous:
            old = AssistantAnswer.model_validate(previous_message.answer)
            old_question = db.scalar(
                select(MessageRow.text).where(
                    MessageRow.job_id == previous_message.job_id, MessageRow.role == "user"
                )
            )
            if (
                old.status == "ANSWERED"
                and old.mode in {"DETERMINISTIC", "CACHE"}
                and old.fact_set.id == facts.id
                and plain_question(old_question or "") == plain_question(question)
            ):
                cached = old.model_copy(deep=True, update={"mode": "CACHE", "request_count": 0})
                cached.usage.cache_hits = 1
                assert route_ai_task(policy, approved_cache=True) == "CACHE"
                break
        workflow = None
        if "doi soat" in plain_question(question) and any(
            w in plain_question(question) for w in ("file", "thang", "nguon")
        ):
            workflow = read_tool(
                db, actor, ToolRequest(name="get_workflow_status", context=context)
            ).workflow
        db.rollback()

    def reserve() -> bool:
        if not settings.assistant_cloud_enabled or settings.assistant_request_budget == 0:
            return False
        with factory() as db:
            fence(db, job_id, token)
            own_conversation(db, actor, conversation_id)
            # Shared global lock is acquired inside the existing durable reservation.
            # Hold it until task count/idempotency checks and commit finish together.
            allowed = reserve_gemini_request(db, actor.workspace_id, job_id, settings)
            if not allowed:
                db.rollback()
                return False
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(AuditRow)
                    .where(AuditRow.action == "ASSISTANT_REQUEST_RESERVED")
                )
                or 0
            )
            previous = db.scalar(
                select(AuditRow.id).where(
                    AuditRow.action == "ASSISTANT_REQUEST_RESERVED", AuditRow.resource_id == job_id
                )
            )
            if count >= settings.assistant_request_budget or previous:
                db.rollback()
                return False
            db.add(
                AuditRow(
                    workspace_id=actor.workspace_id,
                    actor_id=actor.id,
                    action="ASSISTANT_REQUEST_RESERVED",
                    resource_id=job_id,
                )
            )
            db.commit()
            return True

    try:
        answer = cached or (
            workflow_proposal(facts, workflow)
            if workflow
            else answer_question(question, facts, policy, settings, reserve)
        )
    except DomainError as exc:
        with factory() as db:
            fence(db, job_id, token)
            reserved = bool(
                db.scalar(
                    select(AuditRow.id).where(
                        AuditRow.action == "ASSISTANT_REQUEST_RESERVED",
                        AuditRow.resource_id == job_id,
                    )
                )
            )
            db.add(
                TraceRow(
                    workspace_id=actor.workspace_id,
                    job_id=job_id,
                    provider="GEMINI" if reserved else "NONE",
                    task_id="answer_verified_question",
                    prompt_revision=PROMPT_REVISION,
                    usage=dict(reserved_attempts=int(reserved), tokens=None, cost_estimate=None),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    outcome=exc.code,
                )
            )
            db.commit()
        raise
    response_id = str(uuid5(NAMESPACE_URL, f"assistant-response:{job_id}"))
    with factory() as db:
        job = fence(db, job_id, token)
        if db.get(MembershipRow, (actor.workspace_id, actor.id)) is None:
            raise DomainError("RESOURCE_NOT_FOUND", "Quyền truy cập đã bị thu hồi.", 404)
        own_conversation(db, actor, conversation_id)
        # Lock conversation against concurrent deletion before publishing a response.
        from studio.database import ConversationRow

        active = db.get(
            ConversationRow, conversation_id, with_for_update=True, populate_existing=True
        )
        if (
            active is None
            or active.deleted_at
            or db.get(MessageRow, job.payload["message_id"]) is None
        ):
            raise DomainError(
                "RESOURCE_NOT_FOUND", "Hội thoại đã xóa; không công bố câu trả lời.", 404
            )
        if db.get(MessageRow, response_id) is None:
            db.add(
                MessageRow(
                    id=response_id,
                    conversation_id=conversation_id,
                    job_id=job_id,
                    role="assistant",
                    text="",
                    context=context.model_dump(),
                    answer=answer.model_dump(mode="json"),
                )
            )
            db.add(
                TraceRow(
                    workspace_id=actor.workspace_id,
                    job_id=job_id,
                    provider=answer.provider or answer.mode,
                    task_id="answer_verified_question",
                    prompt_revision=PROMPT_REVISION,
                    usage=answer.usage.model_dump()
                    | dict(
                        cloud_requests=answer.request_count,
                        ai_calls=answer.request_count,
                        model=answer.model,
                    ),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    outcome=answer.status,
                )
            )
        finish(
            db,
            job,
            {
                "conversation_id": conversation_id,
                "message_id": response_id,
                "status": answer.status,
            },
        )
        db.commit()
