"""Retention and authorization for projects and imported sources."""

import hashlib
from typing import Literal

from pydantic import Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from studio.access import Actor, require_owner
from studio.contracts import Contract
from studio.database import (
    AgentWorkflowRow,
    ArtifactRow,
    AuditRow,
    Base,
    CanonicalRow,
    ConversationRow,
    DatasetRow,
    ExportRow,
    JobRow,
    MappingRow,
    MessageRow,
    PlanRow,
    ProjectRow,
    ReconciliationContractRow,
    RunRow,
    TableRow,
    VersionRow,
    now,
)
from studio.errors import DomainError

Resource = ProjectRow | DatasetRow
State = Literal["active", "archived", "deleted"]
Action = Literal["archive", "delete", "restore"]
Kind = Literal["project", "dataset"]
DESTINATIONS: dict[Action, State] = {
    "archive": "archived",
    "delete": "deleted",
    "restore": "active",
}


class LifecycleChange(Contract):
    action: Action
    expected_state: State
    expected_version: int = Field(ge=0)
    confirmation: str | None = Field(default=None, max_length=200)


class LifecycleImpact(Contract):
    id: str
    name: str
    project_id: str
    state: State
    version: int
    references: dict[str, int]
    running_jobs: int
    open_work: int
    allowed: list[Action]


def active_source() -> ColumnElement[bool]:
    return DatasetRow.archived_at.is_(None) & DatasetRow.deleted_at.is_(None)


def lifecycle_state(resource: Resource) -> State:
    if resource.deleted_at is not None:
        return "deleted"
    return "archived" if resource.archived_at is not None else "active"


def missing() -> DomainError:
    return DomainError(
        "RESOURCE_NOT_FOUND", "Không tìm thấy mục này trong không gian làm việc.", 404
    )


def lock_project(db: Session, project_id: str) -> None:
    """Serialize lifecycle changes and work submission until the transaction commits."""
    key = int.from_bytes(
        hashlib.sha256(f"studio:lifecycle:{project_id}".encode()).digest()[:8], "big", signed=True
    )
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def active_project(db: Session, project_id: str, workspace_id: str) -> None:
    lock_project(db, project_id)
    project = db.get(ProjectRow, project_id, populate_existing=True)
    if project is None or project.workspace_id != workspace_id or project.deleted_at is not None:
        raise missing()
    if project.archived_at is not None:
        raise DomainError("PROJECT_ARCHIVED", "Khôi phục dự án để tiếp tục công việc.", 409)


def guard_resource(db: Session, row: Base, actor: Actor) -> None:
    """Keep historical reads available while excluding tombstones and fencing writes."""
    dataset: DatasetRow | None = row if isinstance(row, DatasetRow) else None
    table: TableRow | None = row if isinstance(row, TableRow) else None
    if isinstance(row, (MappingRow, CanonicalRow)):
        table = db.get(TableRow, row.source_table_id)
    version_id = (
        row.dataset_version_id
        if isinstance(row, ArtifactRow)
        else table.dataset_version_id
        if table is not None
        else None
    )
    if version_id is not None:
        version = db.get(VersionRow, version_id)
        if version is not None:
            dataset = db.get(DatasetRow, version.dataset_id)
    project_id = row.id if isinstance(row, ProjectRow) else getattr(row, "project_id", None)
    if dataset is not None:
        project_id = dataset.project_id
    if project_id is None:
        return
    writing = db.info.get("resource_write", False)
    if writing:
        active_project(db, project_id, actor.workspace_id)
        if dataset is not None:
            db.refresh(dataset)
    else:
        project = db.get(ProjectRow, project_id)
        if (
            project is None
            or project.workspace_id != actor.workspace_id
            or project.deleted_at is not None
        ):
            raise missing()
    if dataset is not None:
        if dataset.deleted_at is not None:
            raise missing()
        if writing and dataset.archived_at is not None:
            raise DomainError("SOURCE_ARCHIVED", "Khôi phục nguồn để tiếp tục xử lý dữ liệu.", 409)


def _count(db: Session, model: type[Base], *filters: ColumnElement[bool]) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*filters)) or 0


def _target(db: Session, actor: Actor, kind: Kind, resource_id: str) -> tuple[Resource, ProjectRow]:
    resource: Resource | None
    if kind == "project":
        resource = db.get(ProjectRow, resource_id, populate_existing=True)
    else:
        resource = db.get(DatasetRow, resource_id, populate_existing=True)
    if resource is None or resource.workspace_id != actor.workspace_id:
        raise missing()
    project = (
        resource if isinstance(resource, ProjectRow) else db.get(ProjectRow, resource.project_id)
    )
    if project is None or project.workspace_id != actor.workspace_id:
        raise missing()
    require_owner(actor, db, resource_id)
    return resource, project


def _impact(db: Session, resource: Resource, project: ProjectRow) -> LifecycleImpact:
    project_id = project.id
    running = _count(
        db,
        JobRow,
        JobRow.project_id == project_id,
        JobRow.status.in_(("QUEUED", "RUNNING", "RETRYABLE_FAILURE")),
    )
    open_work = _count(
        db,
        AgentWorkflowRow,
        AgentWorkflowRow.project_id == project_id,
        AgentWorkflowRow.state.in_(("CREATED", "RUNNING", "WAITING_REVIEW")),
    )
    conversations = ConversationRow.project_id == project_id
    workflows = AgentWorkflowRow.project_id == project_id
    plans = PlanRow.project_id == project_id
    runs = RunRow.project_id == project_id
    exports = ExportRow.project_id == project_id
    references: dict[str, int] = {}
    if isinstance(resource, ProjectRow):
        references["datasets"] = _count(db, DatasetRow, DatasetRow.project_id == project_id)
    else:
        dataset_id = resource.id
        versions = select(VersionRow.id).where(VersionRow.dataset_id == dataset_id)
        tables = select(TableRow.id).where(TableRow.dataset_version_id.in_(versions))
        canonicals = select(CanonicalRow.id).where(CanonicalRow.source_table_id.in_(tables))
        contracts = select(ReconciliationContractRow.id).where(
            ReconciliationContractRow.project_id == project_id,
            or_(
                ReconciliationContractRow.definition["plan"]["left"]["canonical_id"].astext.in_(
                    canonicals
                ),
                ReconciliationContractRow.definition["plan"]["right"]["canonical_id"].astext.in_(
                    canonicals
                ),
            ),
        )
        conversations &= or_(
            ConversationRow.context["dataset_id"].astext == dataset_id,
            ConversationRow.id.in_(
                select(MessageRow.conversation_id).where(
                    MessageRow.context["dataset_id"].astext == dataset_id
                )
            ),
        )
        workflows &= or_(
            AgentWorkflowRow.context["dataset_id"].astext == dataset_id,
            AgentWorkflowRow.detail["intent"]["dataset_ids"].contains([dataset_id]),
            AgentWorkflowRow.detail["intent"]["dataset_id"].astext == dataset_id,
        )
        plans &= or_(
            PlanRow.proposal["plan"]["left"]["canonical_id"].astext.in_(canonicals),
            PlanRow.proposal["plan"]["right"]["canonical_id"].astext.in_(canonicals),
        )
        runs &= RunRow.contract_id.in_(contracts)
        exports &= ExportRow.run_id.in_(select(RunRow.id).where(runs))
        references["mappings"] = _count(db, MappingRow, MappingRow.source_table_id.in_(tables))
        references["prepared_results"] = _count(
            db, CanonicalRow, CanonicalRow.source_table_id.in_(tables)
        )
    references.update(
        conversations=_count(db, ConversationRow, conversations),
        workflows=_count(db, AgentWorkflowRow, workflows),
        plans=_count(db, PlanRow, plans),
        runs=_count(db, RunRow, runs),
        exports=_count(db, ExportRow, exports),
    )
    state = lifecycle_state(resource)
    allowed: list[Action] = []
    if state != "active":
        if resource is project or lifecycle_state(project) == "active":
            allowed.append("restore")
    elif (
        not running
        and not open_work
        and (resource is project or lifecycle_state(project) == "active")
    ):
        allowed.append("archive")
        if not any(references.values()):
            allowed.append("delete")
    return LifecycleImpact(
        id=resource.id,
        name=resource.name,
        project_id=project_id,
        state=state,
        version=resource.lifecycle_version,
        references=references,
        running_jobs=running,
        open_work=open_work,
        allowed=allowed,
    )


def resource_impact(db: Session, actor: Actor, kind: Kind, resource_id: str) -> LifecycleImpact:
    return _impact(db, *_target(db, actor, kind, resource_id))


def change_resource(
    db: Session, actor: Actor, kind: Kind, resource_id: str, body: LifecycleChange
) -> LifecycleImpact:
    _, project = _target(db, actor, kind, resource_id)
    lock_project(db, project.id)
    resource, project = _target(db, actor, kind, resource_id)
    db.refresh(project)
    impact = _impact(db, resource, project)
    destination = DESTINATIONS[body.action]
    if impact.state == destination and impact.version == body.expected_version + 1:
        return impact
    if (
        impact.version != body.expected_version
        or impact.state != body.expected_state
        or body.action not in impact.allowed
    ):
        raise DomainError(
            "RESOURCE_LIFECYCLE_CONFLICT",
            "Trạng thái hoặc dữ liệu liên quan đã thay đổi. Xem lại trước khi xác nhận.",
            409,
        )
    if kind == "project" and body.action != "restore" and body.confirmation != resource.name:
        raise DomainError("PROJECT_CONFIRMATION_REQUIRED", "Nhập đúng tên dự án để xác nhận.", 422)
    resource.archived_at = now() if destination == "archived" else None
    resource.deleted_at = now() if destination == "deleted" else None
    resource.lifecycle_version += 1
    db.add(
        AuditRow(
            workspace_id=actor.workspace_id,
            actor_id=actor.id,
            action=f"{kind.upper()}_{body.action.upper()}",
            resource_id=resource.id,
        )
    )
    db.flush()
    result = _impact(db, resource, project)
    db.commit()
    return result
