"""Hội thoại cá nhân theo workspace/project, queue bền vững và pagination có cursor."""

import hashlib
from collections.abc import Callable
from typing import Annotated, Any
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.orm import Session

from studio.access import Actor
from studio.assistant_tools import read_tool, scoped_context
from studio.contracts.assistant import (
    AssistantAnswer,
    AssistantContext,
    ConversationInput,
    ConversationView,
    Identifier,
    MessageInput,
    MessageView,
    ToolRequest,
    ToolResult,
)
from studio.database import AuditRow, ConversationRow, JobRow, MessageRow, now
from studio.errors import DomainError
from studio.repository import enqueue_job, get_scoped


def own_conversation(db: Session, actor: Actor, ident: str) -> ConversationRow:
    row = get_scoped(db, ConversationRow, ident, actor)
    if row.actor_id != actor.id or row.deleted_at:
        raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy hội thoại.", 404)
    scoped_context(db, actor, AssistantContext.model_validate(row.context))
    return row


def conversation_view(row: ConversationRow) -> ConversationView:
    return ConversationView(
        id=row.id,
        context=AssistantContext.model_validate(row.context),
        title=row.title,
        created_at=row.created_at,
        archived=row.archived,
    )


def build_router(database: Callable[..., Any], current_actor: Callable[..., Any]) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["Assistant"])
    DB = Annotated[Session, Depends(database)]
    User = Annotated[Actor, Depends(current_actor)]
    Key = Annotated[str, Header(min_length=1, max_length=160, alias="Idempotency-Key")]

    @router.post("/assistant/tools", response_model=ToolResult)
    def tool(body: ToolRequest, db: DB, actor: User) -> ToolResult:
        return read_tool(db, actor, body)

    @router.post("/conversations", response_model=ConversationView, status_code=201)
    def create(body: ConversationInput, db: DB, actor: User, key: Key) -> ConversationView:
        scoped_context(db, actor, body.context)
        ident = str(uuid5(NAMESPACE_URL, f"conversation:{actor.workspace_id}:{actor.id}:{key}"))
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": ident})
        row = db.get(ConversationRow, ident)
        if row:
            if (
                row.context != body.context.model_dump()
                or row.title != body.title
                or row.deleted_at
            ):
                raise DomainError(
                    "IDEMPOTENCY_CONFLICT", "Mã hội thoại đã dùng với nội dung khác.", 409
                )
        else:
            row = ConversationRow(
                id=ident,
                workspace_id=actor.workspace_id,
                project_id=body.context.project_id,
                actor_id=actor.id,
                context=body.context.model_dump(),
                title=body.title,
            )
            db.add(row)
            db.commit()
        return conversation_view(row)

    @router.get("/conversations")
    def conversations(
        project_id: Identifier,
        db: DB,
        actor: User,
        before_id: Identifier | None = None,
        limit: int = Query(20, ge=1, le=50),
    ) -> dict[str, Any]:
        scoped_context(db, actor, AssistantContext(project_id=project_id))
        query = select(ConversationRow).where(
            ConversationRow.workspace_id == actor.workspace_id,
            ConversationRow.project_id == project_id,
            ConversationRow.actor_id == actor.id,
            ConversationRow.deleted_at.is_(None),
        )
        if before_id:
            cursor = own_conversation(db, actor, before_id)
            if cursor.project_id != project_id:
                raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy cursor trong dự án.", 404)
            query = query.where(
                or_(
                    ConversationRow.created_at < cursor.created_at,
                    and_(
                        ConversationRow.created_at == cursor.created_at,
                        ConversationRow.id < cursor.id,
                    ),
                )
            )
        rows = list(
            db.scalars(
                query.order_by(ConversationRow.created_at.desc(), ConversationRow.id.desc()).limit(
                    limit + 1
                )
            )
        )
        return dict(items=[conversation_view(r) for r in rows[:limit]], has_more=len(rows) > limit)

    @router.get("/conversations/{conversation_id}")
    def messages(
        conversation_id: Identifier,
        db: DB,
        actor: User,
        before_id: Identifier | None = None,
        limit: int = Query(20, ge=1, le=50),
    ) -> dict[str, Any]:
        conversation = own_conversation(db, actor, conversation_id)
        query = select(MessageRow).where(MessageRow.conversation_id == conversation.id)
        if before_id:
            cursor = db.get(MessageRow, before_id)
            if cursor is None or cursor.conversation_id != conversation.id:
                raise DomainError(
                    "RESOURCE_NOT_FOUND", "Không tìm thấy cursor trong hội thoại.", 404
                )
            query = query.where(
                or_(
                    MessageRow.created_at < cursor.created_at,
                    and_(MessageRow.created_at == cursor.created_at, MessageRow.id < cursor.id),
                )
            )
        rows = list(
            db.scalars(
                query.order_by(MessageRow.created_at.desc(), MessageRow.id.desc()).limit(limit + 1)
            )
        )
        return dict(
            conversation=conversation_view(conversation),
            has_more=len(rows) > limit,
            items=[
                MessageView(
                    id=r.id,
                    job_id=r.job_id,
                    role=r.role,
                    text=r.text,
                    context=AssistantContext.model_validate(r.context),
                    answer=AssistantAnswer.model_validate(r.answer) if r.answer else None,
                    created_at=r.created_at,
                )
                for r in reversed(rows[:limit])
            ],
        )

    @router.delete("/conversations/{conversation_id}")
    def remove(conversation_id: Identifier, db: DB, actor: User) -> dict[str, str]:
        row = own_conversation(db, actor, conversation_id)
        # Giữ tombstone/audit và job refs, xóa nội dung cá nhân; không đụng financial artifacts.
        db.refresh(row, with_for_update=True)
        row.deleted_at, row.archived, row.title = now(), True, "Đã xóa"
        db.execute(delete(MessageRow).where(MessageRow.conversation_id == row.id))
        db.add(
            AuditRow(
                workspace_id=actor.workspace_id,
                actor_id=actor.id,
                action="CONVERSATION_DELETED",
                resource_id=row.id,
            )
        )
        db.commit()
        return {"status": "DELETED"}

    @router.post("/assistant/messages", status_code=202)
    def message(body: MessageInput, db: DB, actor: User, key: Key) -> dict[str, str]:
        row = own_conversation(db, actor, body.conversation_id)
        db.refresh(row, with_for_update=True)
        if row.deleted_at or row.context != body.context.model_dump():
            raise DomainError(
                "CONVERSATION_CONTEXT_CHANGED", "Tạo hội thoại mới cho context khác.", 409
            )
        ident = str(uuid5(NAMESPACE_URL, f"message:{actor.workspace_id}:{actor.id}:{key}"))
        existing = db.get(MessageRow, ident)
        if existing is None:
            pending = db.scalar(
                select(JobRow.id)
                .where(
                    JobRow.kind == "assistant",
                    JobRow.project_id == row.project_id,
                    JobRow.payload["conversation_id"].astext == row.id,
                    JobRow.status.in_(["QUEUED", "RUNNING", "RETRYABLE_FAILURE"]),
                )
                .limit(1)
            )
            if pending:
                raise DomainError(
                    "CONVERSATION_BUSY", "Câu hỏi trước còn xử lý; mở lại để xem kết quả.", 409
                )
        job = enqueue_job(
            db,
            actor.workspace_id,
            row.project_id,
            "assistant",
            f"assistant:{actor.id}:{key}",
            dict(
                conversation_id=row.id,
                message_id=ident,
                actor_id=actor.id,
                context=body.context.model_dump(),
                question_sha256=hashlib.sha256(body.text.encode()).hexdigest(),
            ),
        )
        if existing is None:
            db.add(
                MessageRow(
                    id=ident,
                    conversation_id=row.id,
                    job_id=job.id,
                    role="user",
                    text=body.text,
                    context=body.context.model_dump(),
                )
            )
        db.commit()
        return {"job_id": job.id, "status": job.status, "message_id": ident}

    return router
