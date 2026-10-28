"""Scoped persistence and queue operations with transactional idempotency."""

import hashlib
import json
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from studio.access import Actor
from studio.config import Settings
from studio.contracts import (
    ArtifactRef,
    DatasetProfile,
    MappingRevision,
    SchemaDefinition,
    WorkspacePolicy,
)
from studio.database import (
    ArtifactRow,
    AuditRow,
    Base,
    DatasetRow,
    JobRow,
    MappingRow,
    ProjectRow,
    SchemaRow,
    TableRow,
    VersionRow,
    WorkspaceRow,
)
from studio.errors import DomainError
from studio.profiling import default_schema, source_signature


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


def reserve_gemini_request(db: Session, workspace_id: str, job_id: str, config: Settings) -> bool:
    """Reserve one HTTP attempt under a global PG lock; caller commits BEFORE sending.

    Global/workspace budgets are lifetime ceilings on reservations, not reset on restart.
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
    if (
        global_used >= config.external_ai_request_budget
        or workspace_used >= policy.external_request_budget
    ):
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


def get_scoped[T: Base](db: Session, model: type[T], resource_id: str, actor: Actor) -> T:
    row = db.get(model, resource_id)
    if row is None or getattr(row, "workspace_id", None) != actor.workspace_id:
        # Identical response for missing and other workspace resources.
        raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy tài nguyên trong workspace.", 404)
    return row


def artifact_ref(row: ArtifactRow) -> ArtifactRef:
    return ArtifactRef.model_validate({k: getattr(row, k) for k in ArtifactRef.model_fields})


def enqueue_job(
    db: Session, workspace_id: str, project_id: str, kind: str, key: str, payload: dict[str, Any]
) -> JobRow:
    """Serialize concurrent enqueue per workspace/key using a PostgreSQL advisory lock."""
    from sqlalchemy import text

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
    revisions = list(
        db.scalars(select(MappingRow.revision).where(MappingRow.source_table_id == table.id))
    )
    mapping = MappingRow(
        workspace_id=table.workspace_id,
        source_table_id=table.id,
        schema_id=schema_id,
        revision=max(revisions, default=0) + 1,
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
