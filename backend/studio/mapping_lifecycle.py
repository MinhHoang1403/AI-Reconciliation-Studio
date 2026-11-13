"""Protect mapping evidence while allowing unused revisions to be removed."""

from typing import Any, Literal

from sqlalchemy import String, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONPATH
from sqlalchemy.orm import Session

from studio.access import Actor, require_owner
from studio.contracts import Contract
from studio.database import (
    AgentWorkflowRow,
    ArtifactRow,
    AuditRow,
    CanonicalRow,
    DatasetRow,
    JobRow,
    MappingRow,
    PlanRow,
    ReconciliationContractRow,
    TableRow,
    VersionRow,
)
from studio.errors import DomainError
from studio.repository import (
    MAPPING_ARCHIVED,
    REMOVED_MAPPING_REVISION,
    get_scoped,
    mapping_archived,
    project_for_table,
)
from studio.resource_lifecycle import active_project, missing

MappingAction = Literal["archive", "delete"]
PENDING = ("QUEUED", "RUNNING", "RETRYABLE_FAILURE")


class MappingImpact(Contract):
    archived: bool
    active: bool
    busy: bool
    referenced: bool
    allowed: list[MappingAction]


class MappingChange(Contract):
    action: MappingAction


def mapping_impact(db: Session, mapping: MappingRow, table: TableRow) -> MappingImpact:
    project = project_for_table(db, table)
    version = db.get(VersionRow, table.dataset_version_id)
    assert version is not None
    variables = func.jsonb_build_object("ref", mapping.id)
    path = cast(literal("strict $.** ? (@ == $ref)"), JSONPATH)

    def references(document: Any) -> Any:
        return func.jsonb_path_exists(document, path, variables)

    # A proposal job's output identifies what it created. Its payload and any
    # template identifier still identify dependencies and are always checked.
    job_reference = or_(
        references(JobRow.payload),
        (JobRow.kind != "mapping") & references(JobRow.result),
        (JobRow.kind == "mapping")
        & references(JobRow.result.op("-")(literal("mapping_id", String))),
    )
    jobs = select(JobRow.id).where(JobRow.workspace_id == mapping.workspace_id)
    related_work = or_(
        job_reference,
        (JobRow.project_id == project.id)
        & (
            (JobRow.payload["table_id"].astext == table.id)
            | (JobRow.payload["dataset_id"].astext == version.dataset_id)
            | JobRow.kind.in_(("agent", "agent_prepare", "agent_resume", "agent_review"))
        ),
        # Existing template discovery can look across projects in this workspace.
        literal(mapping.status == "APPROVED")
        & JobRow.kind.in_(("parse", "mapping", "mapping_reuse")),
    )
    busy = bool(db.scalar(select(jobs.where(JobRow.status.in_(PENDING), related_work).exists())))
    if not busy:
        busy = bool(
            db.scalar(
                select(
                    select(AgentWorkflowRow.id)
                    .where(
                        AgentWorkflowRow.project_id == project.id,
                        AgentWorkflowRow.workspace_id == mapping.workspace_id,
                        AgentWorkflowRow.state == "WAITING_REVIEW",
                        AgentWorkflowRow.detail["reviews"].contains(
                            [{"kind": "MAPPING", "resource_id": table.id, "state": "OPEN"}]
                        ),
                    )
                    .exists()
                )
            )
        )
    archived = bool(db.scalar(select(mapping_archived()).where(MappingRow.id == mapping.id)))
    used = bool(
        db.scalar(
            select(
                or_(
                    select(CanonicalRow.id).where(CanonicalRow.mapping_id == mapping.id).exists(),
                    jobs.where(job_reference).exists(),
                    select(ArtifactRow.id)
                    .where(
                        ArtifactRow.dataset_version_id == version.id,
                        references(ArtifactRow.metadata_json),
                    )
                    .exists(),
                    select(AgentWorkflowRow.id)
                    .where(
                        AgentWorkflowRow.workspace_id == mapping.workspace_id,
                        or_(
                            references(AgentWorkflowRow.detail),
                            references(AgentWorkflowRow.context),
                        ),
                    )
                    .exists(),
                    select(PlanRow.id)
                    .where(
                        PlanRow.workspace_id == mapping.workspace_id, references(PlanRow.proposal)
                    )
                    .exists(),
                    select(ReconciliationContractRow.id)
                    .where(
                        ReconciliationContractRow.workspace_id == mapping.workspace_id,
                        or_(
                            references(ReconciliationContractRow.definition),
                            references(ReconciliationContractRow.source_signatures),
                        ),
                    )
                    .exists(),
                )
            )
        )
    )
    allowed: list[MappingAction] = []
    if not busy:
        if not archived:
            allowed.append("archive")
        if not used:
            allowed.append("delete")
    return MappingImpact(
        active=table.active_mapping_id == mapping.id,
        archived=archived,
        busy=busy,
        referenced=used,
        allowed=allowed,
    )


def change_mapping(db: Session, actor: Actor, mapping_id: str, action: MappingAction) -> None:
    mapping = get_scoped(db, MappingRow, mapping_id, actor)
    require_owner(actor, db, mapping_id)
    table = get_scoped(db, TableRow, mapping.source_table_id, actor)
    active_project(db, project_for_table(db, table).id, actor.workspace_id)
    db.refresh(table, with_for_update=True)
    locked_mapping = db.get(MappingRow, mapping_id, populate_existing=True, with_for_update=True)
    if locked_mapping is None:
        raise missing()
    mapping = locked_mapping
    impact = mapping_impact(db, mapping, table)
    if action == "archive" and impact.archived:
        return
    if action not in impact.allowed:
        raise DomainError(
            "MAPPING_IN_USE",
            "Công việc đang sử dụng phiên bản này."
            if impact.busy
            else "Phiên bản có lịch sử xử lý. Bạn có thể ẩn và xem lại trong lịch sử.",
            409,
        )
    db.add(
        AuditRow(
            workspace_id=actor.workspace_id,
            actor_id=actor.id,
            resource_id=mapping_id,
            action=MAPPING_ARCHIVED if action == "archive" else "DELETE_MAPPING",
        )
    )
    if action == "delete":
        db.add(
            AuditRow(
                workspace_id=actor.workspace_id,
                actor_id=actor.id,
                resource_id=table.id,
                action=f"{REMOVED_MAPPING_REVISION}{mapping.revision}",
            )
        )
        if impact.active:
            table.active_mapping_id = None
            version = db.get(VersionRow, table.dataset_version_id)
            assert version is not None
            dataset = db.get(DatasetRow, version.dataset_id)
            if (
                dataset
                and dataset.status == "MAPPED"
                and not db.scalar(
                    select(TableRow.id)
                    .join(VersionRow, TableRow.dataset_version_id == VersionRow.id)
                    .where(
                        VersionRow.dataset_id == dataset.id, TableRow.active_mapping_id.is_not(None)
                    )
                    .limit(1)
                )
            ):
                dataset.status = "NEEDS_MAPPING_REVIEW"
        db.delete(mapping)
    db.commit()
