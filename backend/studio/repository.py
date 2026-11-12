"""Scoped persistence and queue operations with transactional idempotency."""

import hashlib
import json
from typing import Any

from sqlalchemy import Integer, case, cast, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from studio.access import Actor
from studio.config import Settings, request_limit_reached
from studio.contracts import (
    ArtifactRef,
    DatasetProfile,
    MappingRevision,
    SchemaDefinition,
    WorkspacePolicy,
)
from studio.contracts.api import PreparationAction, PreparedTable
from studio.database import (
    ArtifactRow,
    AttemptRow,
    AuditRow,
    Base,
    CanonicalRow,
    DatasetRow,
    JobRow,
    MappingRow,
    ProjectRow,
    RunRow,
    SchemaRow,
    TableRow,
    VersionRow,
    WorkspaceRow,
)
from studio.errors import GEMINI_RETRYABLE_ERRORS, DomainError
from studio.profiling import default_schema, source_signature
from studio.resource_lifecycle import active_project, active_source, guard_resource

MAPPING_ARCHIVED = "ARCHIVE_MAPPING"
REMOVED_MAPPING_REVISION = "REMOVED_MAPPING_REVISION:"


def mapping_archived() -> ColumnElement[bool]:
    return (
        select(AuditRow.id)
        .where(
            AuditRow.workspace_id == MappingRow.workspace_id,
            AuditRow.resource_id == MappingRow.id,
            AuditRow.action == MAPPING_ARCHIVED,
        )
        .correlate(MappingRow)
        .exists()
    )


def project_classification_expression() -> ColumnElement[str]:
    """Read explicit classification events only; legacy/no event means UNKNOWN.

    Reuse the existing audit metadata for this small reversible preference. Never
    infer a purpose from names, scopes, uploaded bytes or financial status. The
    expression is usable in WHERE before pagination and respects workspace scope.
    """
    latest = (
        select(
            case(
                (AuditRow.action == "PROJECT_CLASSIFIED_TEST", "TEST"),
                (AuditRow.action == "PROJECT_CLASSIFIED_WORK", "WORK"),
                else_="UNKNOWN",
            )
        )
        .where(
            AuditRow.workspace_id == ProjectRow.workspace_id,
            AuditRow.resource_id == ProjectRow.id,
            AuditRow.action.in_(
                ["PROJECT_CLASSIFIED_TEST", "PROJECT_CLASSIFIED_WORK", "PROJECT_CLASSIFIED_UNKNOWN"]
            ),
        )
        .order_by(AuditRow.created_at.desc(), AuditRow.id.desc())
        .limit(1)
        .correlate(ProjectRow)
        .scalar_subquery()
    )
    return func.coalesce(latest, "UNKNOWN")


def preparation_overview(db: Session, project_id: str, active_jobs: int) -> dict[str, Any]:
    """Read-only navigation hints after project authorization, never execution authority.

    All queries are project bounded; target selection is stable by dataset date/ID and
    table ID. Counts describe artifacts (including stale history), not financial readiness.
    Only one target per priority is returned, even when it is outside the dataset page.
    """
    tables = (
        select(TableRow, DatasetRow)
        .join(VersionRow, TableRow.dataset_version_id == VersionRow.id)
        .join(DatasetRow, VersionRow.dataset_id == DatasetRow.id)
        .where(DatasetRow.project_id == project_id, active_source())
    )
    table_ids = tables.with_only_columns(TableRow.id)
    canonical = select(CanonicalRow).where(CanonicalRow.source_table_id.in_(table_ids))
    quality_status = CanonicalRow.contract["quality_status"].astext
    counts: dict[str, int] = dict(
        db.execute(
            select(quality_status, func.count())
            .where(CanonicalRow.source_table_id.in_(table_ids), CanonicalRow.stale.is_(False))
            .group_by(quality_status)
        ).all()
    )
    stale = (
        db.scalar(
            select(func.count()).select_from(
                canonical.where(CanonicalRow.stale.is_(True)).subquery()
            )
        )
        or 0
    )
    current = canonical.where(CanonicalRow.stale.is_(False)).with_only_columns(
        CanonicalRow.source_table_id
    )
    order = (DatasetRow.created_at, DatasetRow.id, TableRow.id)
    action = PreparationAction(kind="UPLOAD")
    if active_jobs:
        action = PreparationAction(kind="WAIT")
    else:
        failed_dataset = db.scalar(
            select(DatasetRow)
            .where(
                DatasetRow.project_id == project_id, DatasetRow.status == "FAILED", active_source()
            )
            .order_by(DatasetRow.created_at, DatasetRow.id)
            .limit(1)
        )
        review = db.execute(
            tables.where(TableRow.active_mapping_id.is_(None)).order_by(*order).limit(1)
        ).first()
        normalize = db.execute(
            tables.where(TableRow.active_mapping_id.is_not(None), TableRow.id.not_in(current))
            .order_by(*order)
            .limit(1)
        ).first()
        quality = db.execute(
            tables.add_columns(CanonicalRow.id)
            .join(CanonicalRow, CanonicalRow.source_table_id == TableRow.id)
            .where(
                CanonicalRow.stale.is_(False),
                CanonicalRow.contract["quality_status"].astext.in_(["PARTIAL", "FAILED"]),
            )
            .order_by(*order, CanonicalRow.id)
            .limit(1)
        ).first()
        if failed_dataset:
            action = PreparationAction(kind="REVIEW_DATA", dataset_id=failed_dataset.id)
        elif review:
            action = PreparationAction(
                kind="OPEN_ASSISTANT"
                if review[1].status == "EXPLORATION_ONLY"
                else "REVIEW_MAPPING",
                dataset_id=review[1].id,
                table_id=review[0].id,
            )
        elif normalize:
            action = PreparationAction(
                kind="NORMALIZE", dataset_id=normalize[1].id, table_id=normalize[0].id
            )
        elif quality:
            mapping = db.get(MappingRow, quality[0].active_mapping_id)
            action = PreparationAction(
                kind=(
                    "OPEN_ASSISTANT"
                    if mapping and (mapping.decision or {}).get("policy_application")
                    else "REVIEW_DATA"
                ),
                dataset_id=quality[1].id,
                table_id=quality[0].id,
                canonical_id=quality[2],
            )
        elif (counts.get("READY") or 0) >= 2:
            action = PreparationAction(kind="RECONCILE")
    latest_run = db.scalar(
        select(RunRow.id)
        .where(RunRow.project_id == project_id, RunRow.status.in_(["VERIFIED", "PARTIAL_VERIFIED"]))
        .order_by(RunRow.created_at.desc(), RunRow.id)
        .limit(1)
    )
    return dict(
        partial_canonical_count=counts.get("PARTIAL", 0),
        failed_canonical_count=counts.get("FAILED", 0),
        stale_canonical_count=stale,
        preparation_action=action,
        latest_verified_run_id=latest_run,
    )


def gemini_request_counts(db: Session, workspace_id: str) -> tuple[int, int]:
    """Count durable reservations, including failed calls/crashes; never refund unknown delivery."""
    reserved = (
        select(func.count())
        .select_from(AuditRow)
        .where(AuditRow.action == "GEMINI_REQUEST_RESERVED")
    )
    return (
        db.scalar(reserved) or 0,
        db.scalar(reserved.where(AuditRow.workspace_id == workspace_id)) or 0,
    )


def retrying_gemini_response(db: Session, job: JobRow) -> bool:
    """Only the prior acknowledged rejection permits another reservation after a claim."""
    if job.attempts < 2:
        return False
    previous = db.scalar(
        select(AttemptRow).where(AttemptRow.job_id == job.id, AttemptRow.number == job.attempts - 1)
    )
    return bool(
        previous
        and previous.status == "RETRYABLE_FAILURE"
        and previous.error_code in GEMINI_RETRYABLE_ERRORS
    )


def gemini_retry_confirmed(job: JobRow) -> bool:
    """A known HTTP rejection is safe to requeue. An unknown delivery is never safe."""
    return (
        job.error_code in GEMINI_RETRYABLE_ERRORS
        and (job.result or {}).get("provider_retry_safe") is True
    )


def reserve_gemini_request(db: Session, workspace_id: str, job_id: str, config: Settings) -> bool:
    """Reserve one HTTP attempt under a global PG lock; caller commits BEFORE sending.

    Finite ceilings remain supported; None explicitly removes a local internal request cap.
    Retries each consume a slot. Missing credentials, policy OFF or exhausted budget deny.
    """
    if not config.allow_external_ai or not config.gemini_api_key.get_secret_value():
        return False
    lock = int.from_bytes(
        hashlib.sha256(b"studio:gemini-request-budget").digest()[:8], "big", signed=True
    )
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    workspace = db.get(WorkspaceRow, workspace_id)
    if workspace is None:
        return False
    policy = WorkspacePolicy.model_validate(workspace.policy)
    if policy.mode != "CLOUD_ALLOWED" or not policy.allow_external_ai:
        return False
    global_used, workspace_used = gemini_request_counts(db, workspace_id)
    if request_limit_reached(
        global_used, config.external_ai_request_budget
    ) or request_limit_reached(workspace_used, policy.external_request_budget):
        return False
    db.add(
        AuditRow(
            workspace_id=workspace_id,
            actor_id="worker",
            action="GEMINI_REQUEST_RESERVED",
            resource_id=job_id,
        )
    )
    db.flush()
    return True


def reserve_document_request(
    db: Session, workspace_id: str, file_id: str, config: Settings
) -> bool:
    """Reserve a 2-page upper bound, including uncertain delivery/failure.
    The same raw file cannot be submitted again. Caller commits before POST.
    """
    from studio.document_parser import DOCUMENT_RESERVED_CREDITS

    if not config.allow_cloud_parsing or not config.llama_cloud_api_key.get_secret_value():
        return False
    lock = int.from_bytes(
        hashlib.sha256(b"studio:llamaparse-budget").digest()[:8], "big", signed=True
    )
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    workspace = db.get(WorkspaceRow, workspace_id)
    if workspace is None:
        return False
    policy = WorkspacePolicy.model_validate(workspace.policy)
    if not policy.allow_cloud_parsing:
        return False
    reserved = select(AuditRow).where(AuditRow.action == "LLAMAPARSE_DOCUMENT_RESERVED")
    if db.scalar(reserved.where(AuditRow.resource_id == file_id)):
        return False
    raw = db.get(ArtifactRow, file_id)
    if raw is None or raw.workspace_id != workspace_id or raw.kind != "raw":
        return False
    if raw.sha256 not in policy.parser_allowed_sha256:
        return False
    extension = raw.metadata_json.get("extension")
    if extension not in {".pdf", ".docx"}:
        return False
    workspace_ceiling = config.parser_request_ceiling(policy.parser_request_budget)
    if workspace_ceiling == 0:
        return False
    global_ceiling = config.cloud_parser_request_budget
    credit_ceiling = config.cloud_parser_credit_budget
    if global_ceiling is not None or credit_ceiling is not None:
        all_rows = list(db.scalars(reserved))
        global_used = len(all_rows)
        workspace_used = sum(r.workspace_id == workspace_id for r in all_rows)
        if (
            request_limit_reached(
                global_used, min(2, global_ceiling) if global_ceiling is not None else None
            )
            or request_limit_reached(workspace_used, workspace_ceiling)
            or request_limit_reached(
                (global_used + 1) * DOCUMENT_RESERVED_CREDITS - 1, credit_ceiling
            )
        ):
            return False
        if global_ceiling is not None:
            for previous in all_rows:
                prior_raw = db.get(ArtifactRow, previous.resource_id)
                if prior_raw is None or prior_raw.metadata_json.get("extension") == extension:
                    return False  # finite acceptance profile grants one PDF and one DOCX
    db.add(
        AuditRow(
            workspace_id=workspace_id,
            actor_id="worker",
            action="LLAMAPARSE_DOCUMENT_RESERVED",
            resource_id=file_id,
        )
    )
    db.flush()
    return True


def get_scoped[T: Base](db: Session, model: type[T], resource_id: str, actor: Actor) -> T:
    row = db.get(model, resource_id)
    if row is None or getattr(row, "workspace_id", None) != actor.workspace_id:
        # Identical response for missing and other workspace resources.
        raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy tài nguyên trong workspace.", 404)
    guard_resource(db, row, actor)
    return row


def artifact_ref(row: ArtifactRow) -> ArtifactRef:
    return ArtifactRef.model_validate({k: getattr(row, k) for k in ArtifactRef.model_fields})


def read_prepared_artifact(
    db: Session, actor: Actor, table: TableRow, parsed: ArtifactRow
) -> ArtifactRow:
    """Resolve the server-published prepared ref for this exact parsed table."""
    metadata = parsed.metadata_json.get("prepared")
    if metadata is None:
        raise DomainError("PREPARED_NOT_AVAILABLE", "Bảng này chưa có bản tự chuẩn bị.", 404)
    ref = PreparedTable.model_validate(metadata)
    prepared = get_scoped(db, ArtifactRow, ref.prepared_artifact_id, actor)
    if (
        ref.source_artifact_id != table.artifact_id
        or parsed.id != table.artifact_id
        or prepared.dataset_version_id != table.dataset_version_id
        or prepared.metadata_json.get("view") != "prepared"
        or prepared.metadata_json.get("source_table_id") != table.id
        or prepared.revision != ref.preparation_revision
    ):
        raise DomainError("ARTIFACT_SCOPE_MISMATCH", "Artifact không thuộc bảng này.", 409)
    return prepared


def enqueue_job(
    db: Session, workspace_id: str, project_id: str, kind: str, key: str, payload: dict[str, Any]
) -> JobRow:
    """Serialize concurrent enqueue per workspace/key using a PostgreSQL advisory lock."""
    active_project(db, project_id, workspace_id)

    lock = int.from_bytes(
        hashlib.sha256(f"{workspace_id}:{key}".encode()).digest()[:8], "big", signed=True
    )
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    existing = db.scalar(
        select(JobRow).where(JobRow.workspace_id == workspace_id, JobRow.idempotency_key == key)
    )
    if existing:
        if (
            existing.kind != kind
            or existing.payload != payload
            or existing.project_id != project_id
        ):
            raise DomainError(
                "IDEMPOTENCY_CONFLICT", "Mã thao tác đã được dùng cho nội dung khác.", 409
            )
        return existing
    job = JobRow(
        workspace_id=workspace_id,
        project_id=project_id,
        kind=kind,
        idempotency_key=key,
        payload=payload,
    )
    db.add(job)
    db.flush()
    return job


def project_for_table(db: Session, table: TableRow) -> ProjectRow:
    version = db.get(VersionRow, table.dataset_version_id)
    assert version is not None
    dataset = db.get(DatasetRow, version.dataset_id)
    assert dataset is not None
    project = db.get(ProjectRow, dataset.project_id)
    assert project is not None
    return project


def create_mapping(
    db: Session, table: TableRow, proposal: dict[str, Any], schema: SchemaDefinition | None = None
) -> MappingRow:
    """Caller holds table row lock; each proposal or user edit receives a new revision."""
    from studio.database import identifier

    profile = DatasetProfile.model_validate(table.profile)
    schema_id = identifier()
    schema = schema or default_schema(table.workspace_id, schema_id)
    schema = schema.model_copy(update={"id": schema_id, "workspace_id": table.workspace_id})
    db.add(
        SchemaRow(
            id=schema_id, workspace_id=table.workspace_id, definition=schema.model_dump(mode="json")
        )
    )
    db.flush()
    current = db.scalar(
        select(func.max(MappingRow.revision)).where(MappingRow.source_table_id == table.id)
    )
    removed_number = cast(func.substr(AuditRow.action, len(REMOVED_MAPPING_REVISION) + 1), Integer)
    removed = db.scalar(
        select(func.max(removed_number)).where(
            AuditRow.workspace_id == table.workspace_id,
            AuditRow.resource_id == table.id,
            AuditRow.action.startswith(REMOVED_MAPPING_REVISION, autoescape=True),
        )
    )
    mapping = MappingRow(
        workspace_id=table.workspace_id,
        source_table_id=table.id,
        schema_id=schema_id,
        revision=max(current or 0, removed or 0) + 1,
        status=proposal["status"],
        signature=source_signature(profile),
        business_scope=project_for_table(db, table).business_scope,
        proposal=proposal,
    )
    db.add(mapping)
    db.flush()
    return mapping


def mapping_contract(row: MappingRow) -> MappingRevision:
    if row.decision is None:
        raise DomainError("MAPPING_NOT_APPROVED", "Ánh xạ chưa được duyệt.")
    return MappingRevision.model_validate(row.decision)


def schema_fingerprint(schema: SchemaDefinition) -> str:
    definition = schema.model_dump(exclude={"id", "workspace_id", "revision"})
    return hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest()
