"""Same-origin REST API for data foundation. Monetary values serialize as exact strings."""

import hashlib
import json
import re
import shutil
import tempfile
from collections.abc import Generator
from datetime import date
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Annotated, Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import polars as pl
from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import Field
from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.orm import Session

from studio.access import (
    Actor,
    _demo_allowed,
    authenticate,
    bootstrap_session,
    default_local_workspace_policy,
    require_editor,
    require_owner,
    require_workspace_scope,
    session_token_hash,
)
from studio.config import request_limit_reached, settings
from studio.contracts import (
    CanonicalDataset,
    Contract,
    DatasetProfile,
    ErrorEnvelope,
    MappingRevision,
    MappingStatus,
    ParsedTableArtifact,
    Project,
    ProjectClassification,
    SchemaDefinition,
    SchemaProposal,
    WorkspacePolicy,
)
from studio.contracts.api import (
    ApprovalInput,
    ArtifactList,
    DatasetList,
    JobAccepted,
    JobList,
    JobView,
    MappingList,
    MappingReusePolicy,
    MappingView,
    NormalizationPreflight,
    PreviewResponse,
    ProjectList,
    ProjectSummary,
    TableList,
    UploadResponse,
)
from studio.contracts.data_query import DataQuery, QueryResult
from studio.database import (
    ArtifactRow,
    AuditRow,
    CanonicalRow,
    DatasetRow,
    JobRow,
    MappingRow,
    MembershipRow,
    ProjectRow,
    SchemaRow,
    SessionFactory,
    SessionRow,
    TableRow,
    VersionRow,
    WorkspaceRow,
    identifier,
    now,
)
from studio.document_parser import (
    DOCUMENT_PARSER_REVISION,
    DOCUMENT_RESERVED_CREDITS,
    DocumentArtifact,
    DocumentExtraction,
)
from studio.errors import DomainError
from studio.mapping_lifecycle import MappingChange, MappingImpact, change_mapping, mapping_impact
from studio.mapping_reuse import (
    REUSE_DISABLED,
    REUSE_ENABLED,
    approved_reference,
    current_reuse_grant,
)
from studio.normalization import NORMALIZATION_REVISION
from studio.parsing import PARSER_REVISION, ParseConfig, choose_parser, inspect_upload
from studio.permanent_deletion import (
    PurgeConfirmation,
    PurgeImpact,
    PurgeKind,
    PurgeStatus,
    purge_root,
)
from studio.permanent_deletion import (
    confirm as confirm_purge,
)
from studio.permanent_deletion import (
    preview as preview_purge,
)
from studio.permanent_deletion import (
    status as purge_status,
)
from studio.repository import (
    artifact_ref,
    create_mapping,
    enqueue_job,
    gemini_request_counts,
    get_scoped,
    mapping_archived,
    mapping_contract,
    preparation_overview,
    project_classification_expression,
    project_for_table,
    read_prepared_artifact,
)
from studio.resource_lifecycle import (
    LifecycleChange,
    LifecycleImpact,
    State,
    active_project,
    active_source,
    change_resource,
    lifecycle_state,
    resource_impact,
)
from studio.schema_mapping import compile_transform_plan, validate_mapping
from studio.storage import checksum, storage_path

app = FastAPI(title="AI Reconciliation Studio — Data Foundation", version="0.1.0")


@app.middleware("http")
async def redact_unexpected_failures(request: Request, call_next: Any) -> Response:
    """Keep unexpected parser/provider exception values out of server traceback logs."""
    try:
        result: Response = await call_next(request)
        return result
    except Exception as exc:
        return await unexpected_error(request, exc)


def database(request: Request) -> Generator[Session, None, None]:
    with SessionFactory() as db:
        path = request.url.path
        read_checks = {"/api/assistant/tools", "/api/agent/queries", "/api/agent/source-rows",
            "/api/reconciliation-plans/validate"}
        db.info["resource_write"] = (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and path not in read_checks and not path.endswith("/mapping-preflight")
        )
        yield db


DB = Annotated[Session, Depends(database)]


def current_actor(request: Request, db: DB) -> Actor:
    actor = authenticate(request, db)
    require_workspace_scope(request, actor)
    return actor


CurrentActor = Annotated[Actor, Depends(current_actor)]


@app.get("/api/permanent-deletion-capability")
def permanent_deletion_capability(db: DB, actor: CurrentActor) -> dict[str, bool | str | None]:
    if actor.role != "owner":
        return {"enabled": False, "workspace_id": None}
    try:
        purge_root(db)
    except DomainError:
        return {"enabled": False, "workspace_id": None}
    workspace_id = actor.workspace_id if actor.workspace_id != "demo" else None
    return {"enabled": True, "workspace_id": workspace_id}


@app.get("/api/permanent-deletion/{kind}/{resource_id}", response_model=PurgeImpact)
def permanent_deletion_impact(
    kind: PurgeKind, resource_id: str, db: DB, actor: CurrentActor
) -> PurgeImpact:
    return preview_purge(db, actor, kind, resource_id)


@app.post("/api/permanent-deletion/{kind}/{resource_id}", response_model=PurgeStatus)
def permanent_deletion_confirm(
    kind: PurgeKind,
    resource_id: str,
    body: PurgeConfirmation,
    request: Request,
    db: DB,
    actor: CurrentActor,
) -> PurgeStatus:
    token = request.cookies.get("studio_session")
    session_hash = session_token_hash(token) if token else None
    return confirm_purge(db, actor, kind, resource_id, body, session_hash=session_hash)

@app.get("/api/permanent-deletion-receipts/{receipt_id}", response_model=PurgeStatus)
def permanent_deletion_status(receipt_id: str, request: Request, db: DB) -> PurgeStatus:
    try:
        actor = authenticate(request, db)
    except DomainError as exc:
        token = request.cookies.get("studio_session")
        if exc.code != "AUTH_REQUIRED" or not token:
            raise
        # Phiên cũ chỉ đọc được biên nhận đã ràng buộc sau khi workspace bị xóa.
        return purge_status(db, None, receipt_id, session_hash=session_token_hash(token))
    return purge_status(db, actor, receipt_id)


from studio.reconciliation_api import build_router  # noqa: E402

app.include_router(build_router(database, current_actor))
from studio.assistant_api import build_router as build_assistant_router  # noqa: E402

app.include_router(build_assistant_router(database, current_actor))
from studio.agent_api import build_router as build_agent_router  # noqa: E402

app.include_router(build_agent_router(database, current_actor))


@app.exception_handler(DomainError)
async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content=ErrorEnvelope(
            code=exc.code,
            message_vi=exc.message_vi,
            details={},
            retryable=exc.retryable,
            correlation_id=str(uuid4()),
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=ErrorEnvelope(
            code="REQUEST_VALIDATION_FAILED",
            message_vi="Thông tin gửi lên chưa đúng định dạng.",
            details={},
            retryable=False,
            correlation_id=str(uuid4()),
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    import logging

    correlation_id = str(uuid4())
    logging.getLogger("studio").error(
        "Unexpected error %s type=%s", correlation_id, type(exc).__name__
    )
    return JSONResponse(
        status_code=500,
        content=ErrorEnvelope(
            code="INTERNAL_ERROR",
            message_vi="Không thể hoàn tất thao tác; vui lòng kiểm tra dịch vụ.",
            details={},
            retryable=False,
            correlation_id=correlation_id,
        ).model_dump(),
    )


@app.get("/api/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/ready")
def ready(db: DB) -> dict[str, str]:
    db.execute(text("SELECT 1 FROM alembic_version"))
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=settings.storage_root) as probe:
        probe.write(b"ready")
        probe.flush()
    return {"status": "ready"}


@app.get("/api/session")
def session(request: Request, response: Response, db: DB) -> dict[str, str]:
    actor = bootstrap_session(request, response, db)
    return {"actor_id": actor.id, "workspace_id": actor.workspace_id, "role": actor.role}


class ProjectInput(Contract):
    name: str = Field(min_length=1, max_length=200)
    business_scope: str = Field(min_length=1, max_length=200)
    classification: ProjectClassification = ProjectClassification.WORK


class ProjectClassificationInput(Contract):
    classification: ProjectClassification
    expected_classification: ProjectClassification


class DatasetNameInput(Contract):
    name: str = Field(min_length=1, max_length=255)
    expected_name: str = Field(min_length=1, max_length=255)


class WorkspaceInput(Contract):
    name: str = Field(min_length=1, max_length=200)


class WorkspaceNameInput(WorkspaceInput):
    expected_name: str = Field(min_length=1, max_length=200)


class WorkspaceChoice(Contract):
    id: str = Field(min_length=1, max_length=64)


class WorkspaceSummary(Contract):
    id: str
    name: str
    role: str


def workspace_label(name: str) -> str:
    label = name.strip()
    if not label or re.search(r"[\x00-\x1f]", label):
        raise DomainError("INVALID_WORKSPACE_NAME", "Tên không gian làm việc không hợp lệ.")
    return label


@app.get("/api/workspaces", response_model=list[WorkspaceSummary])
def member_workspaces(db: DB, actor: CurrentActor) -> list[WorkspaceSummary]:
    rows = db.execute(
        select(WorkspaceRow, MembershipRow.role)
        .join(MembershipRow, MembershipRow.workspace_id == WorkspaceRow.id)
        .where(MembershipRow.actor_id == actor.id)
        .order_by(WorkspaceRow.name, WorkspaceRow.id)
    )
    return [WorkspaceSummary(id=row.id, name=row.name, role=role) for row, role in rows]


@app.post("/api/workspaces", status_code=201, response_model=WorkspaceSummary)
def create_workspace(
    body: WorkspaceInput,
    db: DB,
    actor: CurrentActor,
    request_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> WorkspaceSummary:
    require_owner(actor, db, actor.workspace_id)
    name = workspace_label(body.name)
    workspace_id = (
        str(uuid5(NAMESPACE_URL, f"studio:workspace:{actor.id}:{request_key}"))
        if request_key
        else identifier()
    )
    if request_key:
        lock_key = int.from_bytes(
            hashlib.sha256(workspace_id.encode()).digest()[:8], "big", signed=True
        )
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        existing = db.get(WorkspaceRow, workspace_id)
        if existing is not None:
            membership = db.get(MembershipRow, (workspace_id, actor.id))
            if membership is None or existing.name != name:
                raise DomainError(
                    "WORKSPACE_CREATE_CONFLICT", "Yêu cầu tạo không gian đã đổi.", 409
                )
            return WorkspaceSummary(id=existing.id, name=existing.name, role=membership.role)
    policy = (
        default_local_workspace_policy()
        if actor.id == "demo-owner" and _demo_allowed()
        else WorkspacePolicy()
    )
    row = WorkspaceRow(id=workspace_id, name=name, policy=policy.model_dump())
    db.add(row)
    db.flush()
    db.add(MembershipRow(workspace_id=row.id, actor_id=actor.id, role="owner"))
    db.add(
        AuditRow(
            workspace_id=row.id, actor_id=actor.id, action="WORKSPACE_CREATED", resource_id=row.id
        )
    )
    db.commit()
    return WorkspaceSummary(id=row.id, name=row.name, role="owner")


@app.patch("/api/workspaces/current/name", response_model=WorkspaceSummary)
def rename_workspace(body: WorkspaceNameInput, db: DB, actor: CurrentActor) -> WorkspaceSummary:
    require_owner(actor, db, actor.workspace_id)
    row = db.get(WorkspaceRow, actor.workspace_id, with_for_update=True)
    assert row is not None
    name = workspace_label(body.name)
    if row.name != name:
        if row.name != body.expected_name:
            raise DomainError(
                "WORKSPACE_NAME_CONFLICT", "Tên đã thay đổi. Tải lại Studio trước khi đổi tên.", 409
            )
        row.name = name
        db.add(
            AuditRow(
                workspace_id=row.id,
                actor_id=actor.id,
                action="WORKSPACE_RENAMED",
                resource_id=row.id,
            )
        )
        db.commit()
    return WorkspaceSummary(id=row.id, name=row.name, role=actor.role)


@app.post("/api/workspaces/current", response_model=WorkspaceSummary)
def switch_workspace(
    body: WorkspaceChoice, request: Request, db: DB, actor: CurrentActor
) -> WorkspaceSummary:
    token = request.cookies.get("studio_session")
    session = (
        db.get(SessionRow, session_token_hash(token), populate_existing=True, with_for_update=True)
        if token
        else None
    )
    if session is None or session.actor_id != actor.id or session.expires_at <= now():
        raise DomainError("AUTH_REQUIRED", "Cần phiên trình duyệt hợp lệ để đổi không gian.", 401)
    if session.workspace_id != actor.workspace_id:
        raise DomainError(
            "WORKSPACE_CHANGED", "Không gian làm việc đã thay đổi. Tải lại Studio.", 409
        )
    membership = db.get(MembershipRow, (body.id, actor.id))
    row = db.get(WorkspaceRow, body.id) if membership else None
    if row is None or membership is None:
        raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy không gian làm việc.", 404)
    if session.workspace_id != row.id:
        session.workspace_id = row.id
        db.commit()
    return WorkspaceSummary(id=row.id, name=row.name, role=membership.role)


@app.get("/api/projects", response_model=ProjectList)
def projects(
    db: DB,
    actor: CurrentActor,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str = Query("", max_length=200),
    include_test: bool = True,
    lifecycle: State = "active",
) -> dict[str, Any]:
    """Bounded, workspace-scoped literal search; stable tie ordering across pages."""
    classification = project_classification_expression().label("classification")
    query = select(ProjectRow, classification).where(ProjectRow.workspace_id == actor.workspace_id)
    if lifecycle != "active":
        require_owner(actor, db, "workspace")
    query = query.where(
        ProjectRow.deleted_at.is_not(None)
        if lifecycle == "deleted" else ProjectRow.deleted_at.is_(None),
        ProjectRow.archived_at.is_not(None)
        if lifecycle == "archived" else ProjectRow.archived_at.is_(None),
    )
    if not include_test:
        query = query.where(classification != ProjectClassification.TEST)
    if search.strip():
        literal = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(
            or_(
                ProjectRow.name.ilike(f"%{literal}%", escape="\\"),
                ProjectRow.business_scope.ilike(f"%{literal}%", escape="\\"),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.execute(
        query.order_by(ProjectRow.created_at.desc(), ProjectRow.id).offset(offset).limit(limit)
    )
    return {
        "items": [
            {
                "id": p.id,
                "workspace_id": p.workspace_id,
                "name": p.name,
                "business_scope": p.business_scope,
                "classification": category,
            }
            for p, category in items
        ],
        "total": total,
    }


@app.get("/api/projects/{project_id}", response_model=Project)
def project_detail(project_id: str, db: DB, actor: CurrentActor) -> Project:
    """Restore a saved ID without scanning pages or changing workspace authorization."""
    row = get_scoped(db, ProjectRow, project_id, actor)
    return Project(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        business_scope=row.business_scope,
        classification=db.scalar(
            select(project_classification_expression()).where(ProjectRow.id == row.id)
        ),
    )


@app.get("/api/projects/{project_id}/lifecycle", response_model=LifecycleImpact)
def project_impact(project_id: str, db: DB, actor: CurrentActor) -> LifecycleImpact:
    return resource_impact(db, actor, "project", project_id)


@app.post("/api/projects/{project_id}/lifecycle", response_model=LifecycleImpact)
def project_lifecycle(
    project_id: str, body: LifecycleChange, db: DB, actor: CurrentActor
) -> LifecycleImpact:
    return change_resource(db, actor, "project", project_id, body)


@app.get("/api/datasets/{dataset_id}/lifecycle", response_model=LifecycleImpact)
def dataset_impact(dataset_id: str, db: DB, actor: CurrentActor) -> LifecycleImpact:
    return resource_impact(db, actor, "dataset", dataset_id)


@app.patch("/api/datasets/{dataset_id}/name", response_model=LifecycleImpact)
def rename_dataset(
    dataset_id: str, body: DatasetNameInput, db: DB, actor: CurrentActor
) -> LifecycleImpact:
    """Change the display label under the existing project write lock."""
    require_owner(actor, db, dataset_id)
    row = get_scoped(db, DatasetRow, dataset_id, actor)
    name = body.name.strip()
    if (
        not name
        or re.search(r"[/\\:\x00-\x1f]", name)
        or PurePosixPath(name).suffix.lower() != PurePosixPath(row.name).suffix.lower()
    ):
        raise DomainError(
            "INVALID_DATASET_NAME", "Tên nguồn phải hợp lệ và giữ nguyên phần mở rộng."
        )
    if row.name != name:
        if row.name != body.expected_name:
            raise DomainError(
                "DATASET_NAME_CONFLICT", "Tên nguồn đã thay đổi. Tải lại trước khi đổi tên.", 409
            )
        row.name = name
        db.add(
            AuditRow(
                workspace_id=actor.workspace_id,
                actor_id=actor.id,
                action="DATASET_RENAMED",
                resource_id=dataset_id,
            )
        )
        db.commit()
    return resource_impact(db, actor, "dataset", dataset_id)


@app.post("/api/datasets/{dataset_id}/lifecycle", response_model=LifecycleImpact)
def dataset_lifecycle(
    dataset_id: str, body: LifecycleChange, db: DB, actor: CurrentActor
) -> LifecycleImpact:
    return change_resource(db, actor, "dataset", dataset_id, body)


@app.patch("/api/projects/{project_id}/classification", response_model=Project)
def classify_project(
    project_id: str, body: ProjectClassificationInput, db: DB, actor: CurrentActor
) -> Project:
    """Owner-only reversible metadata, serialized per project; no downstream invalidation.

    A stale expected classification returns 409 rather than overwriting another
    owner's decision. A no-op adds no event. Audit stores actor/time/project and
    exact destination; earlier events retain the complete classification history.
    """
    require_owner(actor, db, project_id)
    get_scoped(db, ProjectRow, project_id, actor)
    db.scalar(select(ProjectRow).where(ProjectRow.id == project_id).with_for_update())
    current = db.scalar(
        select(project_classification_expression()).where(ProjectRow.id == project_id)
    )
    if current != body.expected_classification:
        raise DomainError(
            "PROJECT_CLASSIFICATION_CONFLICT",
            "Phân loại đã thay đổi. Đóng và mở lại danh sách để kiểm tra trước khi xác nhận.",
            409,
        )
    if current != body.classification:
        db.add(
            AuditRow(
                workspace_id=actor.workspace_id,
                actor_id=actor.id,
                action=f"PROJECT_CLASSIFIED_{body.classification}",
                resource_id=project_id,
            )
        )
        db.commit()
    return project_detail(project_id, db, actor)


@app.post("/api/projects", status_code=201)
def create_project(body: ProjectInput, db: DB, actor: CurrentActor) -> dict[str, str]:
    require_editor(actor, db)
    if body.classification != ProjectClassification.WORK:
        require_owner(actor, db, "workspace")
    row = ProjectRow(
        workspace_id=actor.workspace_id,
        name=body.name.strip(),
        business_scope=body.business_scope.strip(),
    )
    if not row.name or not row.business_scope:
        raise DomainError("PROJECT_NAME_EMPTY", "Tên dự án và phạm vi không được để trống.")
    db.add(row)
    db.flush()
    db.add(
        AuditRow(
            workspace_id=actor.workspace_id,
            actor_id=actor.id,
            action=f"PROJECT_CLASSIFIED_{body.classification}",
            resource_id=row.id,
        )
    )
    db.commit()
    return {
        "id": row.id,
        "name": row.name,
        "business_scope": row.business_scope,
        "workspace_id": row.workspace_id,
        "classification": body.classification,
    }


@app.get("/api/projects/{project_id}/summary", response_model=ProjectSummary)
def project_summary(project_id: str, db: DB, actor: CurrentActor) -> ProjectSummary:
    """One backend snapshot of data preparation counts, never financial KPIs."""
    get_scoped(db, ProjectRow, project_id, actor)
    dataset_ids = select(DatasetRow.id).where(DatasetRow.project_id == project_id, active_source())
    table_ids = (
        select(TableRow.id)
        .join(VersionRow, TableRow.dataset_version_id == VersionRow.id)
        .where(VersionRow.dataset_id.in_(dataset_ids))
    )
    dataset_count = (
        db.scalar(
            select(func.count()).select_from(DatasetRow).where(DatasetRow.project_id == project_id)
        )
        or 0
    )
    table_count = (
        db.scalar(select(func.count()).select_from(TableRow).where(TableRow.id.in_(table_ids))) or 0
    )
    review_count = (
        db.scalar(
            select(func.count())
            .select_from(TableRow)
            .where(TableRow.id.in_(table_ids), TableRow.active_mapping_id.is_(None))
        )
        or 0
    )
    canonical_count = (
        db.scalar(
            select(func.count())
            .select_from(CanonicalRow)
            .where(
                CanonicalRow.source_table_id.in_(table_ids),
                CanonicalRow.stale.is_(False),
                CanonicalRow.contract["quality_status"].astext == "READY",
            )
        )
        or 0
    )
    job_count = (
        db.scalar(
            select(func.count())
            .select_from(JobRow)
            .where(
                JobRow.project_id == project_id,
                JobRow.status.in_(["QUEUED", "RUNNING", "RETRYABLE_FAILURE"]),
            )
        )
        or 0
    )
    return ProjectSummary(
        dataset_count=dataset_count,
        table_count=table_count,
        mapping_review_count=review_count,
        ready_canonical_count=canonical_count,
        active_job_count=job_count,
        **preparation_overview(db, project_id, job_count),
    )


@app.get("/api/settings")
def workspace_settings(db: DB, actor: CurrentActor) -> dict[str, Any]:
    from studio.config import AGENT_UPLOAD_EXTENSIONS

    workspace = db.get(WorkspaceRow, actor.workspace_id)
    assert workspace is not None
    global_used, workspace_used = gemini_request_counts(db, workspace.id)
    policy = WorkspacePolicy.model_validate(workspace.policy)
    from studio.config import remaining_requests

    permitted = (
        settings.allow_external_ai and policy.mode == "CLOUD_ALLOWED" and policy.allow_external_ai
    )
    global_remaining = (
        remaining_requests(
            (settings.external_ai_request_budget, global_used),
            (policy.external_request_budget, workspace_used),
        )
        if permitted
        else 0
    )
    task_allowances = {}
    for task, action, ceiling in (
        ("agent", "AGENT_REQUEST_RESERVED", settings.agent_request_budget),
        ("planner", "RECONCILIATION_PLANNER_ATTEMPT", settings.planner_request_budget),
        ("assistant", "ASSISTANT_REQUEST_RESERVED", settings.assistant_request_budget),
    ):
        total = (
            db.scalar(select(func.count()).select_from(AuditRow).where(AuditRow.action == action))
            or 0
        )
        scoped = (
            db.scalar(
                select(func.count())
                .select_from(AuditRow)
                .where(AuditRow.action == action, AuditRow.workspace_id == workspace.id)
            )
            or 0
        )
        task_allowances[task] = {
            "workspace_used": scoped,
            "configured_ceiling": ceiling,
            "remaining": remaining_requests(
                (ceiling, total),
                (settings.external_ai_request_budget, global_used),
                (policy.external_request_budget, workspace_used),
            )
            if permitted
            else 0,
        }
    return {
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "ai_task_allowances": task_allowances,
        "policy": workspace.policy,
        "qwen_configured": bool(settings.qwen_base_url and settings.qwen_enabled),
        "qwen_model": settings.qwen_model,
        "mapping_ai_provider": settings.mapping_ai_provider,
        "agent_cloud_enabled": bool(
            settings.agent_cloud_enabled
            and permitted
            and task_allowances["agent"]["remaining"] != 0
        ),
        "assistant_cloud_enabled": bool(
            settings.assistant_cloud_enabled
            and permitted
            and task_allowances["assistant"]["remaining"] != 0
        ),
        "gemini_model": settings.gemini_model,
        "gemini_configured": bool(settings.gemini_api_key.get_secret_value()),
        "gemini_requests_used": workspace_used,
        "gemini_requests_remaining": global_remaining,
        "max_upload_bytes": settings.max_upload_bytes,
        "max_upload_files": settings.max_upload_files,
        "agent_max_upload_files": settings.agent_max_upload_files,
        "agent_upload_extensions": AGENT_UPLOAD_EXTENSIONS,
        "max_rows": settings.max_rows,
        "cloud_live_status": "NOT VERIFIED",
    }


def _dataset_dto(row: DatasetRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "project_id": row.project_id,
        "name": row.name,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
    }


@app.get("/api/datasets", response_model=DatasetList)
def datasets(
    project_id: str,
    db: DB,
    actor: CurrentActor,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    lifecycle: State = "active",
    search: str = Query("", max_length=200),
) -> dict[str, Any]:
    get_scoped(db, ProjectRow, project_id, actor)
    query = select(DatasetRow).where(
        DatasetRow.workspace_id == actor.workspace_id, DatasetRow.project_id == project_id
    )
    if lifecycle != "active":
        require_owner(actor, db, project_id)
    query = query.where(
        DatasetRow.deleted_at.is_not(None)
        if lifecycle == "deleted" else DatasetRow.deleted_at.is_(None),
        DatasetRow.archived_at.is_not(None)
        if lifecycle == "archived" else DatasetRow.archived_at.is_(None),
    )
    if search.strip():
        literal = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(DatasetRow.name.ilike(f"%{literal}%", escape="\\"))
    return {
        "items": [
            _dataset_dto(d)
            for d in db.scalars(
                query.order_by(DatasetRow.created_at.desc(), DatasetRow.id)
                .offset(offset)
                .limit(limit)
            )
        ],
        "total": db.scalar(select(func.count()).select_from(query.subquery())),
    }


@app.post("/api/datasets/uploads", status_code=202, response_model=UploadResponse)
def upload(
    db: DB,
    actor: CurrentActor,
    project_id: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
    parse_options: Annotated[str, Form()] = "{}",
    request_ai_mapping: Annotated[bool, Form()] = True,
) -> dict[str, Any]:
    result = persist_uploads(db, actor, project_id, files, parse_options, request_ai_mapping)
    db.commit()
    return result


def persist_uploads(
    db: Session,
    actor: Actor,
    project_id: str,
    files: list[UploadFile],
    parse_options: str = "{}",
    request_ai_mapping: bool = True,
) -> dict[str, Any]:
    """Giữ cùng validation/raw/dedup; caller công bố metadata và queue trong transaction."""
    require_editor(actor, db)
    get_scoped(db, ProjectRow, project_id, actor)
    active_project(db, project_id, actor.workspace_id)
    if len(files) > settings.max_upload_files:
        raise DomainError("TOO_MANY_FILES", "Vượt giới hạn số tệp trong một lần tải lên.")
    try:
        parse_config = ParseConfig.model_validate_json(parse_options)
    except ValueError as exc:
        raise DomainError("PARSE_OPTIONS_INVALID", "Tùy chọn đọc tệp không hợp lệ.") from exc
    workspace = db.get(WorkspaceRow, actor.workspace_id)
    assert workspace is not None
    policy = WorkspacePolicy.model_validate(workspace.policy)
    inspected = [
        (file, inspect_upload(file.file, file.filename or "", file.content_type or "", settings))
        for file in files
    ]
    result = []
    for file, inspection in inspected:
        document = inspection.extension in {".pdf", ".docx"}
        parser_revision = DOCUMENT_PARSER_REVISION if document else PARSER_REVISION
        signature = hashlib.sha256(
            (
                parser_revision
                + ("cost_effective:max_pages=2" if document else parse_config.model_dump_json())
            ).encode()
        ).hexdigest()
        # Upload dedup and dataset creation serialize per project/source/config.
        lock = int.from_bytes(
            hashlib.sha256((project_id + inspection.sha256 + signature).encode()).digest()[:8],
            "big",
            signed=True,
        )
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
        existing = db.scalar(
            select(DatasetRow).where(
                DatasetRow.project_id == project_id,
                DatasetRow.sha256 == inspection.sha256,
                DatasetRow.parse_signature == signature,
            )
        )
        if existing:
            if lifecycle_state(existing) != "active":
                raise DomainError(
                    "SOURCE_RETAINED", "Khôi phục nguồn đã lưu trữ hoặc xóa để dùng lại tệp.", 409
                )
            result.append({**_dataset_dto(existing), "reused": True})
            continue
        choose_parser(inspection, policy)
        if document and inspection.sha256 not in policy.parser_allowed_sha256:
            raise DomainError(
                "PARSER_DOCUMENT_NOT_ALLOWED", "Tài liệu chưa nằm trong allowance được duyệt."
            )
        if document and (
            not settings.allow_cloud_parsing
            or request_limit_reached(0, settings.cloud_parser_request_budget)
            or request_limit_reached(
                DOCUMENT_RESERVED_CREDITS - 1, settings.cloud_parser_credit_budget
            )
        ):
            raise DomainError("CLOUD_PARSING_DISABLED", "PDF/DOCX chưa có allowance tạo job mới.")
        dataset = DatasetRow(
            id=identifier(),
            workspace_id=actor.workspace_id,
            project_id=project_id,
            owner_id=actor.id,
            name=inspection.filename,
            sha256=inspection.sha256,
            parse_signature=signature,
            status="UPLOADED",
        )
        db.add(dataset)
        db.flush()
        version = VersionRow(
            id=identifier(),
            dataset_id=dataset.id,
            revision=1,
            parser_revision=parser_revision,
            parse_config=parse_config.model_dump(),
        )
        db.add(version)
        db.flush()
        file_id = identifier()
        key = f"{actor.workspace_id}/{version.id}/raw/{file_id}"
        path = storage_path(settings.storage_root, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        file.file.seek(0)
        with path.open("xb") as stream:
            shutil.copyfileobj(file.file, stream, length=1024 * 1024)
        if checksum(path) != inspection.sha256:
            raise DomainError("UPLOAD_CHECKSUM_FAILED", "Checksum lưu trữ không khớp tệp tải lên.")
        artifact = ArtifactRow(
            id=file_id,
            workspace_id=actor.workspace_id,
            dataset_version_id=version.id,
            kind="raw",
            sha256=inspection.sha256,
            revision="1",
            quality="IMMUTABLE",
            storage_key=key,
            metadata_json=inspection.model_dump(),
        )
        db.add(artifact)
        db.flush()
        job = enqueue_job(
            db,
            actor.workspace_id,
            project_id,
            "document_parse" if document else "parse",
            f"parse:{version.id}:{signature}",
            {
                "dataset_id": dataset.id,
                "version_id": version.id,
                "file_id": file_id,
                "request_ai_mapping": request_ai_mapping,
            },
        )
        db.add(
            AuditRow(
                workspace_id=actor.workspace_id,
                actor_id=actor.id,
                action="UPLOAD",
                resource_id=dataset.id,
            )
        )
        result.append({**_dataset_dto(dataset), "reused": False, "job_id": job.id})
    return {"items": result}


@app.get("/api/datasets/{dataset_id}/documents", response_model=list[DocumentArtifact])
def documents(dataset_id: str, db: DB, actor: CurrentActor) -> list[DocumentArtifact]:
    """Read scoped cached extraction only; never invokes the provider or promotes quality."""
    get_scoped(db, DatasetRow, dataset_id, actor)
    rows = db.scalars(
        select(ArtifactRow)
        .join(VersionRow, ArtifactRow.dataset_version_id == VersionRow.id)
        .where(
            VersionRow.dataset_id == dataset_id,
            ArtifactRow.workspace_id == actor.workspace_id,
            ArtifactRow.kind == "document",
        )
        .limit(20)
    )
    result = []
    for row in rows:
        path = storage_path(settings.storage_root, row.storage_key)
        if checksum(path) != row.sha256:
            raise DomainError("ARTIFACT_CHECKSUM_FAILED", "Artifact không khớp checksum.")
        result.append(
            DocumentArtifact(
                artifact=artifact_ref(row),
                source_file=row.metadata_json["source_file"],
                extraction=DocumentExtraction.model_validate_json(path.read_text(encoding="utf-8")),
            )
        )
    return result


@app.get("/api/datasets/{dataset_id}")
def dataset(dataset_id: str, db: DB, actor: CurrentActor) -> dict[str, Any]:
    row = get_scoped(db, DatasetRow, dataset_id, actor)
    versions = db.scalars(select(VersionRow).where(VersionRow.dataset_id == row.id))
    return {
        **_dataset_dto(row),
        "versions": [
            {
                "id": v.id,
                "revision": v.revision,
                "parser_revision": v.parser_revision,
                "parse_config": v.parse_config,
            }
            for v in versions
        ],
    }


@app.get("/api/datasets/{dataset_id}/tables", response_model=TableList)
def tables(dataset_id: str, db: DB, actor: CurrentActor) -> dict[str, Any]:
    row = get_scoped(db, DatasetRow, dataset_id, actor)
    items = db.execute(
        select(TableRow, ArtifactRow.metadata_json["prepared"])
        .join(VersionRow, TableRow.dataset_version_id == VersionRow.id)
        .join(ArtifactRow, TableRow.artifact_id == ArtifactRow.id)
        .where(VersionRow.dataset_id == row.id, ArtifactRow.workspace_id == actor.workspace_id)
        .order_by(TableRow.sheet)
    )
    return {
        "items": [
            {
                "id": t.id,
                "sheet": t.sheet,
                "row_count": t.row_count,
                "active_mapping_id": t.active_mapping_id,
                "parsed": t.parsed_contract,
                "prepared": prepared,
            }
            for t, prepared in items
        ]
    }


@app.get("/api/tables/{table_id}/profile", response_model=DatasetProfile)
def profile(table_id: str, db: DB, actor: CurrentActor) -> DatasetProfile:
    return DatasetProfile.model_validate(get_scoped(db, TableRow, table_id, actor).profile)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_value(v) for v in value]
    return value


@app.get("/api/tables/{table_id}/preview", response_model=PreviewResponse)
def preview(
    table_id: str,
    db: DB,
    actor: CurrentActor,
    kind: str = Query(
        "parsed", pattern="^(parsed|canonical|errors|raw|prepared|prepared_findings)$"
    ),
    canonical_id: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    search: str = Query("", max_length=200),
) -> dict[str, Any]:
    table = get_scoped(db, TableRow, table_id, actor)
    artifact_id = table.artifact_id
    if kind in {"canonical", "errors"}:
        if canonical_id is None:
            raise DomainError("CANONICAL_REF_REQUIRED", "Cần chọn phiên bản canonical cụ thể.")
        canonical = get_scoped(db, CanonicalRow, canonical_id, actor)
        if canonical.source_table_id != table_id:
            raise DomainError("ARTIFACT_SCOPE_MISMATCH", "Artifact không thuộc bảng này.")
        contract = CanonicalDataset.model_validate(canonical.contract)
        artifact_id = contract.artifact.id if kind == "canonical" else contract.error_artifact.id
    artifact = get_scoped(db, ArtifactRow, artifact_id, actor)
    if kind in {"prepared", "prepared_findings"}:
        artifact = read_prepared_artifact(db, actor, table, artifact)
    path = storage_path(settings.storage_root, artifact.storage_key)
    if checksum(path) != artifact.sha256:
        raise DomainError("ARTIFACT_CHECKSUM_FAILED", "Artifact không khớp checksum.", 409)
    query = pl.scan_parquet(path)
    if kind == "prepared_findings":
        query = query.filter(pl.col("_preparation_flags").list.len() > 0)
    elif kind == "prepared":
        query = query.drop("_preparation_flags")
    if search:
        expressions = [
            pl.col(name).cast(pl.String).str.contains(search, literal=True).fill_null(False)
            for name, dtype in query.collect_schema().items()
            if dtype in {pl.String, pl.Date}
        ]
        payload_type = query.collect_schema().get("record_payload")
        if isinstance(payload_type, pl.Struct):
            expressions.extend(
                pl.col("record_payload")
                .struct.field(field.name)
                .cast(pl.String)
                .str.contains(search, literal=True)
                .fill_null(False)
                for field in payload_type.fields
            )
        if expressions:
            query = query.filter(pl.any_horizontal(expressions))
    total = query.select(pl.len()).collect().item()
    frame = query.slice(offset, limit).collect()
    return {
        "items": _json_value(frame.to_dicts()),
        "total": total,
        "columns": frame.columns,
        "offset": offset,
        "limit": limit,
        "view": "parsed_raw_values" if kind == "raw" else kind,
    }


def table_mapping_jobs(table: TableRow) -> Select[tuple[JobRow]]:
    return select(JobRow).where(
        JobRow.workspace_id == table.workspace_id,
        JobRow.kind == "mapping",
        JobRow.payload["table_id"].astext == table.id,
    )


@app.get("/api/tables/{table_id}/mappings", response_model=MappingList)
def mappings(
    table_id: str, db: DB, actor: CurrentActor, include_archived: bool = False
) -> dict[str, Any]:
    table = get_scoped(db, TableRow, table_id, actor)
    archived = mapping_archived()
    query = (
        select(MappingRow, archived.label("archived"))
        .where(MappingRow.source_table_id == table.id)
        .order_by(MappingRow.revision.desc())
    )
    rows = db.execute(query if include_archived else query.where(~archived)).all()
    parse_result = db.scalar(
        select(JobRow.result)
        .where(
            JobRow.workspace_id == actor.workspace_id,
            JobRow.kind == "parse",
            JobRow.status == "SUCCEEDED",
            JobRow.payload["version_id"].astext == table.dataset_version_id,
        )
        .limit(1)
    )
    template_ids = (parse_result or {}).get("reused_templates", {})

    def schema_definition(schema_id: str) -> dict[str, Any]:
        schema = db.get(SchemaRow, schema_id)
        assert schema is not None
        return schema.definition

    latest_job = db.scalar(
        table_mapping_jobs(table).order_by(JobRow.created_at.desc(), JobRow.id.desc()).limit(1)
    )
    origins = {
        result["mapping_id"]: result.get("source")
        for result in db.scalars(
            table_mapping_jobs(table)
            .with_only_columns(JobRow.result)
            .where(JobRow.status == "SUCCEEDED")
        )
        if result and "mapping_id" in result
    }
    return {
        "job": JobView.model_validate(latest_job, from_attributes=True) if latest_job else None,
        "items": [
            {
                "id": r.id,
                "revision": r.revision,
                "status": r.status,
                "proposal": r.proposal,
                "decision": r.decision,
                "schema": schema_definition(r.schema_id),
                "proposal_source": origins.get(r.id),
                "archived": is_archived,
                "template_mapping_id": template_ids.get(r.id),
                "reuse_enabled": r.id == table.active_mapping_id
                and current_reuse_grant(db, r) is not None,
                "reuse_eligible": r.id == table.active_mapping_id
                and approved_reference(db, r, table),
            }
            for r, is_archived in rows
        ],
    }


@app.get("/api/mappings/{mapping_id}/lifecycle", response_model=MappingImpact)
def mapping_lifecycle(mapping_id: str, db: DB, actor: CurrentActor) -> MappingImpact:
    mapping = get_scoped(db, MappingRow, mapping_id, actor)
    require_owner(actor, db, mapping_id)
    return mapping_impact(db, mapping, get_scoped(db, TableRow, mapping.source_table_id, actor))


@app.post("/api/mappings/{mapping_id}/lifecycle")
def change_mapping_lifecycle(
    mapping_id: str, body: MappingChange, db: DB, actor: CurrentActor
) -> dict[str, str]:
    change_mapping(db, actor, mapping_id, body.action)
    return {"status": "archived" if body.action == "archive" else "deleted"}


@app.post("/api/tables/{table_id}/mapping-draft", status_code=201)
def create_manual_mapping(table_id: str, db: DB, actor: CurrentActor) -> dict[str, str]:
    from studio.ai_gateway import manual_proposal
    from studio.profiling import default_schema

    require_editor(actor, db, table_id)
    table = get_scoped(db, TableRow, table_id, actor)
    db.refresh(table, with_for_update=True)
    existing = db.scalar(
        select(MappingRow.id)
        .where(MappingRow.source_table_id == table.id, ~mapping_archived())
        .order_by(MappingRow.revision.desc())
        .limit(1)
    )
    if existing:
        return {"mapping_id": existing}
    schema = default_schema(actor.workspace_id, identifier())
    proposal = manual_proposal(DatasetProfile.model_validate(table.profile), schema)
    mapping = create_mapping(db, table, proposal.model_dump(mode="json"), schema)
    db.commit()
    return {"mapping_id": mapping.id}


@app.patch("/api/mappings/{mapping_id}/reuse-policy")
def set_mapping_reuse(
    mapping_id: str, body: MappingReusePolicy, db: DB, actor: CurrentActor
) -> dict[str, bool]:
    """Authorize reuse of one human-approved reference for exact repeat uploads."""
    require_owner(actor, db, mapping_id)
    mapping = get_scoped(db, MappingRow, mapping_id, actor)
    table = get_scoped(db, TableRow, mapping.source_table_id, actor)
    db.refresh(table, with_for_update=True)
    mapping = editable_mapping(db, mapping_id, actor)
    enabled = current_reuse_grant(db, mapping) is not None
    if body.expected_enabled != enabled:
        raise DomainError("REUSE_POLICY_CONFLICT", "Chính sách đã đổi. Hãy cập nhật lại.", 409)
    if enabled == body.enabled:
        return {"enabled": enabled}
    if body.enabled and not approved_reference(db, mapping, table):
        raise DomainError(
            "REUSE_REFERENCE_NOT_ELIGIBLE",
            "Cần mẫu được duyệt trực tiếp, còn hiệu lực và đã chuẩn hóa không lỗi.",
        )
    db.add(
        AuditRow(
            workspace_id=actor.workspace_id,
            actor_id=actor.id,
            resource_id=mapping_id,
            action=REUSE_ENABLED if body.enabled else REUSE_DISABLED,
        )
    )
    db.commit()
    return {"enabled": body.enabled}


@app.get("/api/mapping-proposals/{mapping_id}", response_model=MappingView)
def mapping_proposal(mapping_id: str, db: DB, actor: CurrentActor) -> dict[str, Any]:
    mapping = get_scoped(db, MappingRow, mapping_id, actor)
    schema = get_scoped(db, SchemaRow, mapping.schema_id, actor)
    return {
        "id": mapping.id,
        "revision": mapping.revision,
        "status": mapping.status,
        "proposal": mapping.proposal,
        "decision": mapping.decision,
        "schema": schema.definition,
        "archived": bool(db.scalar(select(mapping_archived()).where(MappingRow.id == mapping.id))),
    }


@app.get("/api/schemas/{schema_id}", response_model=SchemaDefinition)
def schema_definition(schema_id: str, db: DB, actor: CurrentActor) -> SchemaDefinition:
    return SchemaDefinition.model_validate(get_scoped(db, SchemaRow, schema_id, actor).definition)


@app.get("/api/canonical-datasets/{canonical_id}", response_model=CanonicalDataset)
def canonical_dataset(canonical_id: str, db: DB, actor: CurrentActor) -> CanonicalDataset:
    row = get_scoped(db, CanonicalRow, canonical_id, actor)
    return CanonicalDataset.model_validate({**row.contract, "stale": row.stale})


@app.post("/api/tables/{table_id}/mapping-proposals", status_code=202, response_model=JobAccepted)
def propose(
    table_id: str,
    db: DB,
    actor: CurrentActor,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=160)],
) -> dict[str, str]:
    require_editor(actor, db, table_id)
    table = get_scoped(db, TableRow, table_id, actor)
    project = project_for_table(db, table)
    db.refresh(table, with_for_update=True)
    key = "mapping:" + idempotency_key
    replay = db.scalar(
        select(JobRow).where(
            JobRow.workspace_id == actor.workspace_id, JobRow.idempotency_key == key
        )
    )
    if not replay:
        pending = db.scalar(
            table_mapping_jobs(table)
            .where(JobRow.status.in_(["QUEUED", "RUNNING", "RETRYABLE_FAILURE"]))
            .order_by(JobRow.created_at.desc())
            .limit(1)
        )
        if pending:
            return {"job_id": pending.id, "status": pending.status}
    payload: dict[str, Any] = {"table_id": table_id}
    if replay is None or "refresh" in replay.payload:
        payload["refresh"] = True
    job = enqueue_job(
        db,
        actor.workspace_id,
        project.id,
        "mapping",
        key,
        payload,
    )
    db.commit()
    return {"job_id": job.id, "status": job.status}


@app.post("/api/tables/{table_id}/mapping-preflight", response_model=NormalizationPreflight)
def preview_mapping(
    table_id: str, body: ApprovalInput, db: DB, actor: CurrentActor
) -> NormalizationPreflight:
    from studio.mapping_verification import preflight_approval

    return preflight_approval(db, actor, table_id, body)


@app.post("/api/mappings/{mapping_id}/approve", response_model=MappingRevision)
def approve_mapping(
    mapping_id: str,
    body: ApprovalInput,
    db: DB,
    actor: CurrentActor,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=160)] = None,
) -> MappingRevision:
    """Replay the immutable approval receipt on a retried request, under one DB lock."""
    require_editor(actor, db, mapping_id)
    receipt_id = None
    request_hash = None
    if idempotency_key is not None:
        receipt_id = hashlib.sha256(
            json.dumps(["approve-mapping", actor.workspace_id, actor.id, idempotency_key]).encode()
        ).hexdigest()
        request_hash = hashlib.sha256(
            json.dumps([mapping_id, body.model_dump(mode="json")], sort_keys=True).encode()
        ).hexdigest()
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int.from_bytes(bytes.fromhex(receipt_id)[:8], "big", signed=True)},
        )
        receipt = db.get(AuditRow, receipt_id)
        if receipt:
            if receipt.action != "APPROVE_RECEIPT:" + request_hash:
                raise DomainError(
                    "IDEMPOTENCY_CONFLICT", "Mã duyệt đã dùng cho nội dung khác.", 409
                )
            return mapping_contract(get_scoped(db, MappingRow, receipt.resource_id, actor))
    result = apply_mapping_approval(mapping_id, body, db, actor)
    if receipt_id is not None:
        db.add(
            AuditRow(
                id=receipt_id,
                workspace_id=actor.workspace_id,
                actor_id=actor.id,
                action="APPROVE_RECEIPT:" + str(request_hash),
                resource_id=result.id,
            )
        )
    db.commit()
    return result


@app.post("/api/mappings/{mapping_id}/reject")
def reject_mapping(mapping_id: str, db: DB, actor: CurrentActor) -> dict[str, str]:
    require_editor(actor, db, mapping_id)
    mapping = get_scoped(db, MappingRow, mapping_id, actor)
    table = get_scoped(db, TableRow, mapping.source_table_id, actor)
    db.refresh(table, with_for_update=True)
    mapping = editable_mapping(db, mapping_id, actor)
    if mapping.status in {"APPROVED", "SUPERSEDED"}:
        raise DomainError(
            "IMMUTABLE_APPROVAL", "Cần tạo revision mới thay vì sửa lịch sử đã duyệt.", 409
        )
    mapping.status = "REJECTED"
    db.add(
        AuditRow(
            workspace_id=actor.workspace_id,
            actor_id=actor.id,
            action="REJECT_MAPPING",
            resource_id=mapping.id,
        )
    )
    db.commit()
    return {"status": "REJECTED"}


def editable_mapping(db: Session, mapping_id: str, actor: Actor) -> MappingRow:
    mapping = db.get(MappingRow, mapping_id, populate_existing=True)
    if mapping is None or mapping.workspace_id != actor.workspace_id:
        raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy phiên bản ánh xạ.", 404)
    if db.scalar(select(mapping_archived()).where(MappingRow.id == mapping_id)):
        raise DomainError("MAPPING_ARCHIVED", "Phiên bản đã ẩn chỉ dùng để xem lịch sử.", 409)
    return mapping


class NormalizeInput(Contract):
    mapping_id: str


@app.post("/api/agent/queries", response_model=QueryResult)
def data_query(body: DataQuery, db: DB, actor: CurrentActor) -> QueryResult:
    from studio.data_query import execute_query

    return execute_query(db, actor, body)


@app.post("/api/datasets/{dataset_id}/normalize", status_code=202, response_model=JobAccepted)
def normalize(
    dataset_id: str,
    body: NormalizeInput,
    db: DB,
    actor: CurrentActor,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=160)],
) -> dict[str, str]:
    result = enqueue_normalization(dataset_id, body.mapping_id, db, actor, idempotency_key)
    db.commit()
    return result


@app.get("/api/datasets/{dataset_id}/artifacts", response_model=ArtifactList)
def artifacts(dataset_id: str, db: DB, actor: CurrentActor) -> dict[str, Any]:
    dataset = get_scoped(db, DatasetRow, dataset_id, actor)
    rows = db.scalars(
        select(ArtifactRow)
        .join(VersionRow, ArtifactRow.dataset_version_id == VersionRow.id)
        .where(VersionRow.dataset_id == dataset.id)
    )
    canonicals = db.scalars(
        select(CanonicalRow)
        .join(TableRow, CanonicalRow.source_table_id == TableRow.id)
        .join(VersionRow, TableRow.dataset_version_id == VersionRow.id)
        .where(VersionRow.dataset_id == dataset.id)
    )
    return {
        "items": [artifact_ref(r).model_dump() for r in rows],
        "canonical_datasets": [{**r.contract, "stale": r.stale} for r in canonicals],
    }


@app.get("/api/datasets/{dataset_id}/download")
def download_source(dataset_id: str, db: DB, actor: CurrentActor) -> FileResponse:
    """Tải đúng raw bytes có quyền và SHA; không nhận path hoặc sinh lại nội dung."""
    dataset = get_scoped(db, DatasetRow, dataset_id, actor)
    artifact = db.scalar(
        select(ArtifactRow)
        .join(VersionRow, ArtifactRow.dataset_version_id == VersionRow.id)
        .where(
            VersionRow.dataset_id == dataset.id,
            ArtifactRow.workspace_id == actor.workspace_id,
            ArtifactRow.kind == "raw",
        )
    )
    if artifact is None:
        raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy tệp nguồn.", 404)
    path = storage_path(settings.storage_root, artifact.storage_key)
    if checksum(path) != artifact.sha256 or artifact.sha256 != dataset.sha256:
        raise DomainError("ARTIFACT_CHECKSUM_FAILED", "Tệp nguồn không khớp checksum đã lưu.", 409)
    return FileResponse(
        path,
        filename=artifact.metadata_json.get("filename") or dataset.name,
        media_type="application/octet-stream",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )


@app.get("/api/evidence/{evidence_id}")
def evidence(
    evidence_id: str, db: DB, actor: CurrentActor, row: int | None = Query(None, ge=1)
) -> dict[str, Any]:
    parts = evidence_id.split(":")
    table = get_scoped(db, TableRow, parts[0], actor)
    parsed = ParsedTableArtifact.model_validate(table.parsed_contract)
    if len(parts) != 2 or parts[1] not in {c.id for c in parsed.columns}:
        raise DomainError("EVIDENCE_NOT_FOUND", "Không tìm thấy bằng chứng.", 404)
    artifact = get_scoped(db, ArtifactRow, table.artifact_id, actor)
    query = pl.scan_parquet(storage_path(settings.storage_root, artifact.storage_key))
    if row is not None:
        query = query.filter(pl.col("_source_row") == row)
    values = query.select("_source_row", "_source_row_id", parts[1]).head(10).collect().to_dicts()
    return {
        "id": evidence_id,
        "sheet": table.sheet,
        "header_row": parsed.header_row,
        "column": next(c.model_dump() for c in parsed.columns if c.id == parts[1]),
        "items": values,
        "warnings": parsed.warnings,
        "cell_metadata": artifact.metadata_json.get("cell_metadata", [])[:100],
        "preamble": artifact.metadata_json.get("preamble", []),
    }


@app.get("/api/jobs", response_model=JobList)
def jobs(
    project_id: str,
    db: DB,
    actor: CurrentActor,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    get_scoped(db, ProjectRow, project_id, actor)
    rows = db.scalars(
        select(JobRow)
        .where(JobRow.workspace_id == actor.workspace_id, JobRow.project_id == project_id)
        .order_by(JobRow.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return {
        "items": [
            {
                "id": j.id,
                "kind": j.kind,
                "status": j.status,
                "attempts": j.attempts,
                "error_code": j.error_code,
                "result": j.result,
                "normalization": {
                    "mapping_id": j.payload["mapping_id"],
                    "dataset_id": j.payload["dataset_id"],
                }
                if j.kind == "normalize"
                else None,
            }
            for j in rows
        ]
    }


@app.get("/api/jobs/{job_id}", response_model=JobView)
def job(job_id: str, db: DB, actor: CurrentActor) -> dict[str, Any]:
    row = get_scoped(db, JobRow, job_id, actor)
    return {
        "id": row.id,
        "kind": row.kind,
        "status": row.status,
        "attempts": row.attempts,
        "error_code": row.error_code,
        "result": row.result,
    }


def apply_mapping_approval(
    mapping_id: str, body: ApprovalInput, db: Session, actor: Actor
) -> MappingRevision:
    """F09: authorize, validate, create immutable approval; old canonical refs become stale."""
    require_editor(actor, db, mapping_id)
    original = get_scoped(db, MappingRow, mapping_id, actor)
    table = get_scoped(db, TableRow, original.source_table_id, actor)
    db.refresh(table, with_for_update=True)
    original = editable_mapping(db, mapping_id, actor)
    if original.status in {"REJECTED", "SUPERSEDED"}:
        raise DomainError("MAPPING_SUPERSEDED", "Ánh xạ đã bị thay thế hoặc từ chối.", 409)
    if table.parsed_contract["warnings"] and not body.extraction_reviewed:
        raise DomainError(
            "EXTRACTION_REVIEW_REQUIRED", "Cần kiểm tra cảnh báo và xác nhận vùng dữ liệu nguồn."
        )
    schema = body.schema_definition.model_copy(update={"workspace_id": actor.workspace_id})
    for decision in body.decisions:
        if decision.candidate_target is not None:
            decision.decision = MappingStatus.APPROVED
            decision.grain_assumption = schema.grain
    proposal = SchemaProposal(
        entity_kind=schema.entity_kind,
        grain=schema.grain,
        status="PROPOSED",
        decisions=body.decisions,
    )
    profile = DatasetProfile.model_validate(table.profile)
    validate_mapping(proposal, profile, schema, for_approval=True)
    from studio.mapping_verification import preflight_approval

    preflight_approval(db, actor, table.id, body)
    # Every edit is a new schema/mapping row, including editing an approved revision.
    mapping = create_mapping(db, table, proposal.model_dump(mode="json"), schema)
    persisted_schema = db.get(SchemaRow, mapping.schema_id)
    assert persisted_schema is not None
    schema = SchemaDefinition.model_validate(persisted_schema.definition)
    rules = [r.model_copy(update={"approved_by": actor.id}) for r in body.rules]
    contract = MappingRevision(
        id=mapping.id,
        workspace_id=actor.workspace_id,
        source_table_id=table.id,
        source_signature=mapping.signature,
        schema_id=schema.id,
        schema_revision=schema.revision,
        business_scope=mapping.business_scope,
        revision=mapping.revision,
        status=MappingStatus.APPROVED,
        decisions=body.decisions,
        approved_by=actor.id,
        approved_at=now(),
        rules=rules,
    )
    compile_transform_plan(contract, schema, profile)
    if table.active_mapping_id:
        old = db.get(MappingRow, table.active_mapping_id)
        if old:
            old.status = "SUPERSEDED"
        for row in db.scalars(select(CanonicalRow).where(CanonicalRow.source_table_id == table.id)):
            row.stale = True
    mapping.status = "APPROVED"
    mapping.decision = contract.model_dump(mode="json")
    table.active_mapping_id = mapping.id
    version = db.get(VersionRow, table.dataset_version_id)
    assert version is not None
    dataset = db.get(DatasetRow, version.dataset_id)
    assert dataset is not None
    dataset.status = "MAPPED"
    db.add(
        AuditRow(
            workspace_id=actor.workspace_id,
            actor_id=actor.id,
            action="APPROVE_MAPPING",
            resource_id=mapping.id,
        )
    )
    db.flush()
    return contract


def enqueue_normalization(
    dataset_id: str, mapping_id: str, db: Session, actor: Actor, idempotency_key: str
) -> dict[str, str]:
    require_editor(actor, db, dataset_id)
    dataset = get_scoped(db, DatasetRow, dataset_id, actor)
    mapping = get_scoped(db, MappingRow, mapping_id, actor)
    table = get_scoped(db, TableRow, mapping.source_table_id, actor)
    # Serialize requests for the same source table before looking for an active normalization.
    db.refresh(table, with_for_update=True)
    version = db.get(VersionRow, table.dataset_version_id)
    if version is None or version.dataset_id != dataset.id or table.active_mapping_id != mapping.id:
        raise DomainError(
            "STALE_MAPPING", "Ánh xạ không phải revision hiện hành của dữ liệu này.", 409
        )
    contract = mapping_contract(mapping)
    schema = db.get(SchemaRow, mapping.schema_id)
    assert schema is not None
    compile_transform_plan(
        contract,
        SchemaDefinition.model_validate(schema.definition),
        DatasetProfile.model_validate(table.profile),
    )
    key = "normalize:" + idempotency_key
    existing_key = db.scalar(
        select(JobRow.id).where(
            JobRow.workspace_id == actor.workspace_id,
            JobRow.idempotency_key == key,
        )
    )
    if not existing_key:
        active = db.scalar(
            select(JobRow)
            .where(
                JobRow.workspace_id == actor.workspace_id,
                JobRow.project_id == dataset.project_id,
                JobRow.kind == "normalize",
                JobRow.status.in_(["QUEUED", "RUNNING", "RETRYABLE_FAILURE"]),
                JobRow.payload["mapping_id"].astext == mapping.id,
                JobRow.payload["normalization_revision"].astext == NORMALIZATION_REVISION,
            )
            .order_by(JobRow.created_at, JobRow.id)
            .limit(1)
        )
        if active:
            return {"job_id": active.id, "status": active.status}
    job = enqueue_job(
        db,
        actor.workspace_id,
        dataset.project_id,
        "normalize",
        key,
        {
            "dataset_id": dataset_id,
            "table_id": table.id,
            "mapping_id": mapping.id,
            "normalization_revision": NORMALIZATION_REVISION,
        },
    )
    db.flush()
    return {"job_id": job.id, "status": job.status}
