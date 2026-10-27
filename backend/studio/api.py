"""Same-origin REST API for data foundation. Monetary values serialize as exact strings."""

import hashlib
import shutil
import tempfile
from collections.abc import Generator
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import uuid4

import polars as pl
from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from studio.access import Actor, authenticate, bootstrap_session, require_editor
from studio.config import settings
from studio.contracts import (
    ApprovedTransformRule,
    CanonicalDataset,
    Contract,
    DatasetProfile,
    ErrorEnvelope,
    MappingDecision,
    MappingRevision,
    MappingStatus,
    ParsedTableArtifact,
    SchemaDefinition,
    SchemaProposal,
    WorkspacePolicy,
)
from studio.contracts.api import (
    ArtifactList,
    DatasetList,
    JobAccepted,
    JobList,
    JobView,
    MappingList,
    MappingView,
    PreviewResponse,
    ProjectList,
    ProjectSummary,
    TableList,
    UploadResponse,
)
from studio.database import (
    ArtifactRow,
    AuditRow,
    CanonicalRow,
    DatasetRow,
    JobRow,
    MappingRow,
    ProjectRow,
    SchemaRow,
    SessionFactory,
    TableRow,
    VersionRow,
    WorkspaceRow,
    identifier,
    now,
)
from studio.errors import DomainError
from studio.normalization import NORMALIZATION_REVISION
from studio.parsing import PARSER_REVISION, ParseConfig, choose_parser, inspect_upload
from studio.repository import (
    artifact_ref,
    create_mapping,
    enqueue_job,
    get_scoped,
    mapping_contract,
    project_for_table,
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


def database() -> Generator[Session, None, None]:
    with SessionFactory() as db:
        yield db


DB = Annotated[Session, Depends(database)]


def current_actor(request: Request, db: DB) -> Actor:
    return authenticate(request, db)


CurrentActor = Annotated[Actor, Depends(current_actor)]


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


@app.get("/api/projects", response_model=ProjectList)
def projects(
    db: DB, actor: CurrentActor, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
) -> dict[str, Any]:
    query = select(ProjectRow).where(ProjectRow.workspace_id == actor.workspace_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(ProjectRow.created_at.desc()).offset(offset).limit(limit))
    return {
        "items": [
            {
                "id": p.id,
                "workspace_id": p.workspace_id,
                "name": p.name,
                "business_scope": p.business_scope,
            }
            for p in items
        ],
        "total": total,
    }


@app.post("/api/projects", status_code=201)
def create_project(body: ProjectInput, db: DB, actor: CurrentActor) -> dict[str, str]:
    require_editor(actor, db)
    row = ProjectRow(
        workspace_id=actor.workspace_id,
        name=body.name.strip(),
        business_scope=body.business_scope.strip(),
    )
    if not row.name or not row.business_scope:
        raise DomainError("PROJECT_NAME_EMPTY", "Tên dự án và phạm vi không được để trống.")
    db.add(row)
    db.commit()
    return {
        "id": row.id,
        "name": row.name,
        "business_scope": row.business_scope,
        "workspace_id": row.workspace_id,
    }


@app.get("/api/projects/{project_id}/summary", response_model=ProjectSummary)
def project_summary(project_id: str, db: DB, actor: CurrentActor) -> ProjectSummary:
    """One backend snapshot of data preparation counts, never financial KPIs."""
    get_scoped(db, ProjectRow, project_id, actor)
    dataset_ids = select(DatasetRow.id).where(DatasetRow.project_id == project_id)
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
    )


@app.get("/api/settings")
def workspace_settings(db: DB, actor: CurrentActor) -> dict[str, Any]:
    workspace = db.get(WorkspaceRow, actor.workspace_id)
    assert workspace is not None
    return {
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "policy": workspace.policy,
        "qwen_configured": bool(settings.qwen_base_url and settings.qwen_enabled),
        "qwen_model": settings.qwen_model,
        "max_upload_bytes": settings.max_upload_bytes,
        "max_upload_files": settings.max_upload_files,
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
) -> dict[str, Any]:
    get_scoped(db, ProjectRow, project_id, actor)
    query = select(DatasetRow).where(
        DatasetRow.workspace_id == actor.workspace_id, DatasetRow.project_id == project_id
    )
    return {
        "items": [
            _dataset_dto(d)
            for d in db.scalars(
                query.order_by(DatasetRow.created_at.desc()).offset(offset).limit(limit)
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
) -> dict[str, Any]:
    require_editor(actor, db)
    get_scoped(db, ProjectRow, project_id, actor)
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
    for _, inspection in inspected:
        route = choose_parser(inspection, policy)
        if route != "tabular":
            raise DomainError(
                "DOCUMENT_ADAPTER_ONLY",
                "PDF/DOCX hiện chỉ có adapter hợp đồng, chưa nghiệm thu cloud trực tiếp.",
            )
    signature = hashlib.sha256(
        (PARSER_REVISION + parse_config.model_dump_json()).encode()
    ).hexdigest()
    result = []
    for file, inspection in inspected:
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
            result.append({**_dataset_dto(existing), "reused": True})
            continue
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
            parser_revision=PARSER_REVISION,
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
            "parse",
            f"parse:{version.id}:{signature}",
            {"dataset_id": dataset.id, "version_id": version.id, "file_id": file_id},
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
    db.commit()
    return {"items": result}


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
    items = db.scalars(
        select(TableRow)
        .join(VersionRow, TableRow.dataset_version_id == VersionRow.id)
        .where(VersionRow.dataset_id == row.id)
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
            }
            for t in items
        ]
    }


@app.get("/api/tables/{table_id}/profile", response_model=DatasetProfile)
def profile(table_id: str, db: DB, actor: CurrentActor) -> DatasetProfile:
    return DatasetProfile.model_validate(get_scoped(db, TableRow, table_id, actor).profile)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
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
    kind: str = Query("parsed", pattern="^(parsed|canonical|errors|raw)$"),
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
    query = pl.scan_parquet(storage_path(settings.storage_root, artifact.storage_key))
    if search:
        expressions = [
            pl.col(name).cast(pl.String).str.contains(search, literal=True).fill_null(False)
            for name, dtype in query.collect_schema().items()
            if dtype == pl.String
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


@app.get("/api/tables/{table_id}/mappings", response_model=MappingList)
def mappings(table_id: str, db: DB, actor: CurrentActor) -> dict[str, Any]:
    table = get_scoped(db, TableRow, table_id, actor)
    rows = db.scalars(
        select(MappingRow)
        .where(MappingRow.source_table_id == table.id)
        .order_by(MappingRow.revision.desc())
    )

    def schema_definition(schema_id: str) -> dict[str, Any]:
        schema = db.get(SchemaRow, schema_id)
        assert schema is not None
        return schema.definition

    return {
        "items": [
            {
                "id": r.id,
                "revision": r.revision,
                "status": r.status,
                "proposal": r.proposal,
                "decision": r.decision,
                "schema": schema_definition(r.schema_id),
            }
            for r in rows
        ]
    }


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
    job = enqueue_job(
        db,
        actor.workspace_id,
        project.id,
        "mapping",
        "mapping:" + idempotency_key,
        {"table_id": table_id},
    )
    db.commit()
    return {"job_id": job.id, "status": job.status}


class ApprovalInput(Contract):
    schema_definition: SchemaDefinition
    decisions: list[MappingDecision]
    rules: list[ApprovedTransformRule] = Field(default_factory=list)
    extraction_reviewed: bool = False


@app.post("/api/mappings/{mapping_id}/approve", response_model=MappingRevision)
def approve_mapping(
    mapping_id: str, body: ApprovalInput, db: DB, actor: CurrentActor
) -> MappingRevision:
    """F09: authorize, validate, create immutable approval; old canonical refs become stale."""
    require_editor(actor, db, mapping_id)
    original = get_scoped(db, MappingRow, mapping_id, actor)
    table = get_scoped(db, TableRow, original.source_table_id, actor)
    db.refresh(table, with_for_update=True)
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
    db.commit()
    return contract


@app.post("/api/mappings/{mapping_id}/reject")
def reject_mapping(mapping_id: str, db: DB, actor: CurrentActor) -> dict[str, str]:
    require_editor(actor, db, mapping_id)
    mapping = get_scoped(db, MappingRow, mapping_id, actor)
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


class NormalizeInput(Contract):
    mapping_id: str


@app.post("/api/datasets/{dataset_id}/normalize", status_code=202, response_model=JobAccepted)
def normalize(
    dataset_id: str,
    body: NormalizeInput,
    db: DB,
    actor: CurrentActor,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=160)],
) -> dict[str, str]:
    require_editor(actor, db, dataset_id)
    dataset = get_scoped(db, DatasetRow, dataset_id, actor)
    mapping = get_scoped(db, MappingRow, body.mapping_id, actor)
    table = get_scoped(db, TableRow, mapping.source_table_id, actor)
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
    job = enqueue_job(
        db,
        actor.workspace_id,
        dataset.project_id,
        "normalize",
        "normalize:" + idempotency_key,
        {
            "dataset_id": dataset_id,
            "table_id": table.id,
            "mapping_id": mapping.id,
            "normalization_revision": NORMALIZATION_REVISION,
        },
    )
    db.commit()
    return {"job_id": job.id, "status": job.status}


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
