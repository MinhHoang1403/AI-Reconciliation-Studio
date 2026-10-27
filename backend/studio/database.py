"""PostgreSQL metadata, ownership and immutable artifact relationships."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from studio.config import settings


def identifier() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class WorkspaceRow(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=identifier)
    name: Mapped[str] = mapped_column(String(200))
    policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class MembershipRow(Base):
    __tablename__ = "memberships"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role: Mapped[str] = mapped_column(String(20))


class SessionRow(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(64))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=identifier)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    business_scope: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DatasetRow(Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("project_id", "sha256", "parse_signature"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=identifier)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    owner_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    parse_signature: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), default="UPLOADED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class VersionRow(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "revision"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=identifier)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    parser_revision: Mapped[str] = mapped_column(String(60))
    parse_config: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=identifier)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"))
    kind: Mapped[str] = mapped_column(String(20))
    sha256: Mapped[str] = mapped_column(String(64))
    revision: Mapped[str] = mapped_column(String(100))
    quality: Mapped[str] = mapped_column(String(60))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class TableRow(Base):
    __tablename__ = "source_tables"
    __table_args__ = (UniqueConstraint("dataset_version_id", "sheet"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=identifier)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"))
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"))
    sheet: Mapped[str] = mapped_column(String(255))
    row_count: Mapped[int] = mapped_column(Integer)
    parsed_contract: Mapped[dict[str, Any]] = mapped_column(JSONB)
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB)
    active_mapping_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SchemaRow(Base):
    __tablename__ = "schema_definitions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=identifier)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)


class MappingRow(Base):
    __tablename__ = "mapping_revisions"
    __table_args__ = (UniqueConstraint("source_table_id", "revision"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=identifier)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_table_id: Mapped[str] = mapped_column(ForeignKey("source_tables.id"))
    schema_id: Mapped[str] = mapped_column(ForeignKey("schema_definitions.id"))
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40))
    signature: Mapped[str] = mapped_column(String(64), index=True)
    business_scope: Mapped[str] = mapped_column(String(200))
    proposal: Mapped[dict[str, Any]] = mapped_column(JSONB)
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CanonicalRow(Base):
    __tablename__ = "canonical_datasets"
    __table_args__ = (UniqueConstraint("mapping_id", "normalization_revision"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=identifier)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_table_id: Mapped[str] = mapped_column(ForeignKey("source_tables.id"))
    mapping_id: Mapped[str] = mapped_column(ForeignKey("mapping_revisions.id"))
    normalization_revision: Mapped[str] = mapped_column(String(60))
    contract: Mapped[dict[str, Any]] = mapped_column(JSONB)
    stale: Mapped[bool] = mapped_column(default=False)


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("workspace_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=identifier)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(40), default="QUEUED", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AttemptRow(Base):
    __tablename__ = "job_attempts"
    __table_args__ = (UniqueConstraint("job_id", "number"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=identifier)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    number: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="RUNNING")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)


class AuditRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=identifier)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TraceRow(Base):
    __tablename__ = "ai_traces"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=identifier)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    provider: Mapped[str] = mapped_column(String(30))
    task_id: Mapped[str] = mapped_column(String(50))
    prompt_revision: Mapped[str] = mapped_column(String(30))
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB)
    latency_ms: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(80))


engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=2)
SessionFactory = sessionmaker(engine, expire_on_commit=False)
