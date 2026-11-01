"""Registry duy nhất cho Agent, dùng lại bảy read tools và business services hiện có."""

from typing import Annotated, Literal, get_args

from pydantic import Field
from sqlalchemy.orm import Session

from studio.access import Actor, require_editor
from studio.assistant_tools import read_tool, scoped_context
from studio.contracts import Contract, DatasetProfile
from studio.contracts.assistant import (
    AssistantContext,
    Identifier,
    ToolName,
    ToolRequest,
    ToolResult,
)
from studio.contracts.data_query import DataQuery, QueryResult
from studio.contracts.reconciliation import PlanningRequest
from studio.data_query import execute_query
from studio.database import MembershipRow, TableRow
from studio.errors import DomainError
from studio.repository import enqueue_job, get_scoped, project_for_table


class QueryAction(Contract):
    name: Literal["query_dataset"]
    query: DataQuery


class ProfileAction(Contract):
    name: Literal["get_dataset_profile"]
    context: AssistantContext
    table_id: Identifier


class NormalizeAction(Contract):
    name: Literal["run_normalization"]
    context: AssistantContext
    dataset_id: Identifier
    mapping_id: Identifier


class PlanAction(Contract):
    name: Literal["prepare_reconciliation_plan"]
    context: AssistantContext
    request: PlanningRequest


class MappingAction(Contract):
    name: Literal["prepare_mapping_proposal"]
    context: AssistantContext
    table_id: Identifier
    workflow_id: Identifier


class RunAction(Contract):
    name: Literal["run_approved_reconciliation"]
    context: AssistantContext
    contract_id: Identifier


class ExportAction(Contract):
    name: Literal["start_export"]
    context: AssistantContext
    format: Literal["csv", "xlsx"]


AgentAction = Annotated[
    ToolRequest
    | QueryAction
    | ProfileAction
    | NormalizeAction
    | PlanAction
    | MappingAction
    | RunAction
    | ExportAction,
    Field(discriminator="name"),
]


class JobReference(Contract):
    job_id: str
    run_id: str | None = None
    export_id: str | None = None
    status: str


TOOL_ACCESS = {name: "READ" for name in get_args(ToolName)} | {
    "query_dataset": "READ",
    "get_dataset_profile": "READ",
    "run_normalization": "WRITE_APPROVED",
    "prepare_reconciliation_plan": "WRITE_PROPOSAL",
    "prepare_mapping_proposal": "WRITE_PROPOSAL",
    "run_approved_reconciliation": "WRITE_APPROVED",
    "start_export": "WRITE_VERIFIED",
}


def execute_tool(
    db: Session,
    actor: Actor,
    action: AgentAction,
    idempotency_key: str,
) -> ToolResult | QueryResult | DatasetProfile | JobReference:
    """Kiểm quyền mỗi call; không commit để workflow/review/action công bố nguyên tử.

    Không có tool approve do model được gọi. Quyết định người dùng xử lý bằng API
    riêng có nonce/fingerprint/row lock; write tự động chỉ dùng approval đã tồn tại.
    """
    membership = db.get(MembershipRow, (actor.workspace_id, actor.id))
    if membership is None or membership.role != actor.role:
        raise DomainError("RESOURCE_NOT_FOUND", "Quyền truy cập đã thay đổi.", 404)
    if action.name not in TOOL_ACCESS:
        raise DomainError("TOOL_NOT_ALLOWED", "Công cụ không được phép.")
    if isinstance(action, ToolRequest):
        return read_tool(db, actor, action)
    if isinstance(action, QueryAction):
        return execute_query(db, actor, action.query)
    scoped_context(db, actor, action.context)
    if isinstance(action, ProfileAction):
        table = get_scoped(db, TableRow, action.table_id, actor)
        if project_for_table(db, table).id != action.context.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Nguồn sai project.", 404)
        return DatasetProfile.model_validate(table.profile)
    require_editor(actor, db, action.context.project_id)
    if isinstance(action, NormalizeAction):
        from studio.api import enqueue_normalization
        from studio.database import DatasetRow

        dataset = get_scoped(db, DatasetRow, action.dataset_id, actor)
        if dataset.project_id != action.context.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Nguồn sai project.", 404)
        return JobReference.model_validate(
            enqueue_normalization(
                action.dataset_id,
                action.mapping_id,
                db,
                actor,
                idempotency_key,
            )
        )
    if isinstance(action, MappingAction):
        from studio.database import AgentWorkflowRow

        table = get_scoped(db, TableRow, action.table_id, actor)
        workflow = get_scoped(db, AgentWorkflowRow, action.workflow_id, actor)
        if workflow.actor_id != actor.id or workflow.project_id != action.context.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Công việc sai owner/project.", 404)
        if project_for_table(db, table).id != action.context.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Nguồn sai project.", 404)
        job = enqueue_job(
            db,
            actor.workspace_id,
            action.context.project_id,
            "agent_prepare",
            "agent-mapping:" + idempotency_key,
            dict(workflow_id=workflow.id, table_ids=[table.id]),
        )
        return JobReference(job_id=job.id, status=job.status)
    if isinstance(action, PlanAction):
        from studio.reconciliation_planner import validate_planning_request
        from studio.reconciliation_repository import selected_catalogue

        cats = selected_catalogue(
            db,
            actor,
            action.context.project_id,
            [action.request.left.canonical_id, action.request.right.canonical_id],
        )
        validate_planning_request(
            action.request, cats, actor.workspace_id, action.context.project_id
        )
        job = enqueue_job(
            db,
            actor.workspace_id,
            action.context.project_id,
            "reconciliation_plan",
            "agent-plan:" + idempotency_key,
            dict(
                request=action.request.model_dump(mode="json", exclude_unset=True),
                actor_id=actor.id,
            ),
        )
        return JobReference(job_id=job.id, status=job.status)
    if isinstance(action, RunAction):
        from studio.database import ReconciliationContractRow
        from studio.reconciliation_api import enqueue_approved_run

        contract = get_scoped(db, ReconciliationContractRow, action.contract_id, actor)
        if contract.project_id != action.context.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Rule sai project.", 404)
        return JobReference.model_validate(enqueue_approved_run(action.contract_id, db, actor))
    if isinstance(action, ExportAction):
        from studio.reconciliation_api import enqueue_export

        if action.context.run_id is None:
            raise DomainError("INSUFFICIENT_EVIDENCE", "Cần run đã xác minh.")
        return JobReference.model_validate(
            enqueue_export(action.context.run_id, action.format, db, actor)
        )
    raise DomainError("TOOL_NOT_ALLOWED", "Công cụ chưa hỗ trợ.")
