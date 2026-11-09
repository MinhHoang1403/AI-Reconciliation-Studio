"""Hội thoại cá nhân theo workspace/project, queue bền vững và pagination có cursor."""

import hashlib
from collections.abc import Callable
from typing import Annotated, Any
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import and_, delete, or_, select, text
from sqlalchemy.orm import Session

from studio.access import Actor
from studio.ai_gateway import OllamaProvider, require_local_model, route_ai_task
from studio.assistant import explicit_fact_question
from studio.assistant_tools import read_tool, scoped_context
from studio.config import ModelChoice, settings
from studio.contracts import WorkspacePolicy
from studio.contracts.assistant import (
    AssistantAnswer,
    AssistantContext,
    AssistantModelOption,
    ConversationInput,
    ConversationView,
    Identifier,
    MessageInput,
    MessageView,
    ToolRequest,
    ToolResult,
)
from studio.database import (
    AgentWorkflowRow,
    AuditRow,
    ConversationRow,
    JobRow,
    MessageRow,
    TraceRow,
    WorkspaceRow,
    now,
)
from studio.errors import DomainError
from studio.repository import enqueue_job, get_scoped


def check_model_choice(
    db: Session, actor: Actor, choice: ModelChoice | None, *, legacy: bool = False
) -> None:
    if choice is None:
        return
    if choice != "GEMINI":
        require_local_model(settings, choice)
        return
    workspace = db.get(WorkspaceRow, actor.workspace_id)
    assert workspace is not None
    policy = WorkspacePolicy.model_validate(workspace.policy)
    enabled = settings.assistant_cloud_enabled if legacy else settings.agent_cloud_enabled
    if not enabled or not settings.allow_external_ai or route_ai_task(policy) != "GEMINI":
        raise DomainError("CLOUD_AI_DISABLED", "AI đám mây chưa được cấp phép.", 403)
    if not settings.gemini_api_key.get_secret_value():
        raise DomainError("GEMINI_KEY_MISSING", "Gemini chưa được cấu hình.", 409)


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

    @router.get("/assistant/models", response_model=list[AssistantModelOption])
    def models(
        db: DB, actor: User, project_id: Identifier | None = None
    ) -> list[AssistantModelOption]:
        if project_id:
            scoped_context(db, actor, AssistantContext(project_id=project_id))
        gemini = AssistantModelOption(
            id="GEMINI", label="Gemini", available=True, status="UNVERIFIED"
        )
        try:
            check_model_choice(db, actor, "GEMINI")
        except DomainError as exc:
            gemini.available = False
            gemini.status = "NOT_CONFIGURED" if exc.code == "GEMINI_KEY_MISSING" else "NOT_ALLOWED"
        options = [gemini]
        local_digest = None
        if settings.local_demo_access and settings.ollama_url:
            choice = settings.ollama_choice
            local = AssistantModelOption(
                id=choice,
                label="Qwen 8B" if choice == "QWEN_8B" else "Qwen 27B",
                available=True,
                status="UNVERIFIED",
            )
            adapter = OllamaProvider(settings, choice)
            try:
                local_digest = adapter.installed_digest()
            except DomainError as exc:
                local.available = False
                local.status = (
                    "NOT_CONFIGURED" if exc.code == "OLLAMA_MODEL_MISSING" else "UNAVAILABLE"
                )
            finally:
                adapter.close()
            options.append(local)
        for option in options:
            option.preferred = option.id == settings.assistant_default_model
            if not option.available:
                continue
            conditions = (
                TraceRow.usage["model"].astext == settings.gemini_model
                if option.id == "GEMINI"
                else TraceRow.usage["digest"].astext == local_digest
            )
            trace = db.scalar(
                select(TraceRow)
                .where(
                    TraceRow.workspace_id == actor.workspace_id,
                    TraceRow.provider == ("GEMINI" if option.id == "GEMINI" else "OLLAMA"),
                    conditions,
                )
                .join(JobRow, JobRow.id == TraceRow.job_id)
                .order_by(JobRow.created_at.desc(), JobRow.id.desc())
                .limit(1)
            )
            if (
                option.id == "GEMINI"
                and trace
                and trace.outcome in {"VALIDATED", "VALIDATED_PROPOSAL"}
            ):
                option.status = "READY"
            elif trace and trace.usage.get("http_status") == 429:
                option.status = "LIMITED"
            elif trace and trace.outcome in {"OLLAMA_UNAVAILABLE", "GEMINI_UNAVAILABLE"}:
                option.status = "UNAVAILABLE"
        return options

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

        jobs_by_id = {
            j.id: j
            for j in db.scalars(
                select(JobRow).where(
                    JobRow.id.in_([r.job_id for r in rows]),
                    JobRow.workspace_id == actor.workspace_id,
                    JobRow.project_id == conversation.project_id,
                )
            )
        }

        def workflow_for_message(message: MessageRow) -> str | None:
            job = db.get(JobRow, message.job_id)
            condition = AgentWorkflowRow.parent_job_id == message.job_id
            if job and job.kind == "agent_review" and message.role == "assistant":
                condition = AgentWorkflowRow.id == job.payload.get("workflow_id")
            return db.scalar(
                select(AgentWorkflowRow.id).where(
                    condition,
                    AgentWorkflowRow.actor_id == actor.id,
                    AgentWorkflowRow.workspace_id == actor.workspace_id,
                    AgentWorkflowRow.conversation_id == conversation.id,
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
                    workflow_id=workflow_for_message(r),
                    job_status=jobs_by_id[r.job_id].status,
                    error_code=jobs_by_id[r.job_id].error_code,
                    model_choice=jobs_by_id[r.job_id].payload.get("model_choice"),
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
        # Yêu cầu rõ là chỉ đọc dùng cùng bộ dựng facts đã có. Tệp, lệnh
        # xác định và câu ghép luôn vào Agent để giữ đủ các bước của yêu cầu.
        auto_read = (
            body.mode == "AUTO" and not body.command and not body.dataset_ids
            and explicit_fact_question(body.text)
        )
        agent = body.mode == "AGENT" or (body.mode == "AUTO" and not auto_read)
        model_choice = None if auto_read else body.model_choice
        if existing is None:
            check_model_choice(db, actor, model_choice, legacy=not agent)
            pending = db.scalar(
                select(JobRow.id)
                .where(
                    JobRow.kind.in_(["assistant", "agent", "agent_review"]),
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
            "agent" if agent else "assistant",
            f"assistant:{actor.id}:{key}",
            dict(
                conversation_id=row.id,
                message_id=ident,
                actor_id=actor.id,
                context=body.context.model_dump(),
                question_sha256=hashlib.sha256(body.text.encode()).hexdigest(),
            )
            | (
                dict(dataset_ids=body.dataset_ids, command=body.command)
                if agent
                else {}
            )
            | ({"model_choice": model_choice} if model_choice else {}),
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
