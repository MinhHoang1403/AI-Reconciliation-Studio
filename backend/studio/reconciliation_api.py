"""Scoped reconciliation REST routes sharing the existing session and DB dependencies."""

import hashlib
import json
from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from studio.access import Actor, require_editor
from studio.contracts import Contract, EvidenceRef, MappingRevision, ParsedTableArtifact
from studio.contracts.api import JobAccepted
from studio.contracts.reconciliation import (
    ExceptionCase,
    MatchGroup,
    MetricSnapshot,
    PlanningRequest,
    PlanProposal,
    ReconciliationContract,
    ReconciliationPlan,
    ReconciliationRun,
    SourceCatalogue,
)
from studio.database import (
    AuditRow,
    DatasetRow,
    ExceptionRow,
    ExportRow,
    JobRow,
    MappingRow,
    PlanRow,
    ProjectRow,
    ReconciliationContractRow,
    RunRow,
    TableRow,
    VersionRow,
    identifier,
    now,
)
from studio.errors import DomainError
from studio.reconciliation_contracts import validate_reconciliation_contract
from studio.reconciliation_engine import ENGINE_REVISION, coverage_complete, record_partition
from studio.reconciliation_planner import validate_planning_request
from studio.reconciliation_repository import (
    catalogue_for_project,
    load_canonical_records,
    match_page,
    run_contract,
    selected_catalogue,
    template_signatures,
)
from studio.repository import enqueue_job, get_scoped, mapping_contract
from studio.storage import checksum, storage_path

REPORT_REVISION = "report-2"


class PlanInput(Contract):
    project_id: str
    plan: ReconciliationPlan


class AIPlanInput(Contract):
    project_id: str
    request: PlanningRequest


class RunInput(Contract):
    contract_id: str


class ReviewInput(Contract):
    workflow_state: Literal["OPEN", "IN_REVIEW", "RESOLVED", "DISMISSED_WITH_REASON"]
    notes: str = Field(default="", max_length=2000)


class TemplateInput(Contract):
    left_canonical_id: str
    right_canonical_id: str
    period_start: date
    period_end: date
    left_coverage_start: date
    left_coverage_end: date
    right_coverage_start: date
    right_coverage_end: date
    completeness: Literal["CONFIRMED", "INCOMPLETE", "UNKNOWN"]
    snapshot_at: datetime


class PlanView(Contract):
    id: str
    project_id: str
    origin: str
    proposal: PlanProposal
    contract_id: str | None


class CatalogueList(Contract):
    items: list[SourceCatalogue]


class RunList(Contract):
    items: list[ReconciliationRun]
    total: int


class MatchPage(Contract):
    items: list[MatchGroup]
    total: int
    offset: int
    limit: int


class CaseList(Contract):
    items: list[ExceptionCase]
    total: int
    current_open_count: int


def plan_view(db: Session, row: PlanRow) -> PlanView:
    contract_id = db.scalar(
        select(ReconciliationContractRow.id).where(ReconciliationContractRow.plan_id == row.id)
    )
    return PlanView(
        id=row.id,
        project_id=row.project_id,
        origin=row.origin,
        proposal=PlanProposal.model_validate(row.proposal),
        contract_id=contract_id,
    )


def require_verified(run: RunRow) -> None:
    if run.status not in {"VERIFIED", "PARTIAL_VERIFIED"} or run.metric_snapshot is None:
        raise DomainError(
            "RUN_NOT_VERIFIED", "Kết quả chưa verified; không công bố KPI/báo cáo.", 409
        )


def case_view(row: ExceptionRow) -> ExceptionCase:
    return ExceptionCase.model_validate(
        row.definition
        | dict(
            workflow_state=row.workflow_state,
            notes=row.notes,
            reviewed_by=row.reviewed_by,
            reviewed_at=row.reviewed_at,
        )
    )


def build_router(database: Callable[..., Any], current_actor: Callable[..., Any]) -> APIRouter:
    """Bind shared dependencies without creating another authentication implementation."""
    router = APIRouter(prefix="/api", tags=["Reconciliation"])
    DB = Annotated[Session, Depends(database)]
    User = Annotated[Actor, Depends(current_actor)]
    Key = Annotated[str, Header(min_length=1, max_length=160, alias="Idempotency-Key")]

    @router.get("/projects/{project_id}/canonical-catalogue", response_model=CatalogueList)
    def catalogue(project_id: str, db: DB, actor: User) -> CatalogueList:
        get_scoped(db, ProjectRow, project_id, actor)
        return CatalogueList(items=catalogue_for_project(db, actor, project_id))

    @router.get("/projects/{project_id}/domain-schema-templates")
    def schema_templates(project_id: str, db: DB, actor: User) -> dict[str, Any]:
        from studio.domain_templates import domain_templates

        get_scoped(db, ProjectRow, project_id, actor)
        sources = catalogue_for_project(db, actor, project_id)
        return {
            "items": domain_templates(
                actor.workspace_id, {c.canonical.entity_kind for c in sources}
            ),
            "approval_required": True,
        }

    @router.post("/reconciliation-plans", response_model=PlanView, status_code=201)
    def manual_plan(body: PlanInput, db: DB, actor: User, key: Key) -> PlanView:
        require_editor(actor, db, body.project_id)
        get_scoped(db, ProjectRow, body.project_id, actor)
        cats = selected_catalogue(
            db, actor, body.project_id, [body.plan.left.canonical_id, body.plan.right.canonical_id]
        )
        validate_reconciliation_contract(body.plan, cats, actor.workspace_id, body.project_id)
        row_id = str(uuid5(NAMESPACE_URL, actor.workspace_id + ":plan:" + key))
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {
                "key": int.from_bytes(
                    hashlib.sha256(row_id.encode()).digest()[:8], "big", signed=True
                )
            },
        )
        proposal = PlanProposal(status="PROPOSED", plan=body.plan)
        row = db.get(PlanRow, row_id)
        if row is not None:
            if (
                row.project_id != body.project_id
                or PlanProposal.model_validate(row.proposal) != proposal
            ):
                raise DomainError(
                    "IDEMPOTENCY_CONFLICT", "Mã thao tác đã dùng cho nội dung khác.", 409
                )
            return plan_view(db, row)
        row = PlanRow(
            id=row_id,
            workspace_id=actor.workspace_id,
            project_id=body.project_id,
            proposal=proposal.model_dump(mode="json"),
            origin="MANUAL",
            created_by=actor.id,
        )
        db.add(row)
        db.commit()
        return plan_view(db, row)

    @router.post("/reconciliation-plans/validate")
    def validate(body: PlanInput, db: DB, actor: User) -> dict[str, Any]:
        require_editor(actor, db, body.project_id)
        get_scoped(db, ProjectRow, body.project_id, actor)
        cats = selected_catalogue(
            db, actor, body.project_id, [body.plan.left.canonical_id, body.plan.right.canonical_id]
        )
        validate_reconciliation_contract(body.plan, cats, actor.workspace_id, body.project_id)
        # Read key uniqueness/readiness without matching or publishing a result.
        readiness = []
        for side, cat in zip(("left", "right"), cats, strict=True):
            rows = load_canonical_records(db, actor, cat.canonical)
            slot = body.plan.left if side == "left" else body.plan.right
            keys = [
                tuple(r.payload.get(getattr(p, side)) for p in body.plan.join_keys)
                for r in rows
                if record_partition(r, body.plan, side) == "IN_SCOPE"
            ]
            readiness.append(
                dict(
                    side=side,
                    rows=len(rows),
                    key_groups=len(set(keys)),
                    duplicate_key_rows=len(keys) - len(set(keys)),
                    invalid_records=sum(
                        record_partition(r, body.plan, side) == "INVALID" for r in rows
                    ),
                    out_of_scope_records=sum(
                        record_partition(r, body.plan, side) == "OUT_OF_SCOPE" for r in rows
                    ),
                    in_scope_records=len(keys),
                    duplicate_population="IN_SCOPE",
                    coverage_complete=coverage_complete(body.plan, slot),
                )
            )
        return {
            "valid": True,
            "approval_required": True,
            "sources": readiness,
            "duplicate_handling": "REVIEW; never arbitrary selection",
        }

    @router.post("/reconciliation-plans/ai", response_model=JobAccepted, status_code=202)
    def ai_plan(body: AIPlanInput | PlanInput, db: DB, actor: User, key: Key) -> dict[str, str]:
        require_editor(actor, db, body.project_id)
        get_scoped(db, ProjectRow, body.project_id, actor)
        request = (
            body.request if isinstance(body, AIPlanInput) else PlanningRequest.from_plan(body.plan)
        )
        cats = selected_catalogue(
            db, actor, body.project_id, [request.left.canonical_id, request.right.canonical_id]
        )
        validate_planning_request(request, cats, actor.workspace_id, body.project_id)
        job = enqueue_job(
            db,
            actor.workspace_id,
            body.project_id,
            "reconciliation_plan",
            "plan:" + key,
            dict(request=request.model_dump(mode="json", exclude_unset=True), actor_id=actor.id),
        )
        db.commit()
        return {"job_id": job.id, "status": job.status}

    @router.get("/reconciliation-plans/{plan_id}", response_model=PlanView)
    def get_plan(plan_id: str, db: DB, actor: User) -> PlanView:
        return plan_view(db, get_scoped(db, PlanRow, plan_id, actor))

    @router.post(
        "/reconciliation-contracts/{plan_id}/approve", response_model=ReconciliationContract
    )
    def approve(plan_id: str, db: DB, actor: User) -> ReconciliationContract:
        require_editor(actor, db, plan_id)
        row = get_scoped(db, PlanRow, plan_id, actor)
        db.refresh(row, with_for_update=True)
        existing = db.scalar(
            select(ReconciliationContractRow).where(ReconciliationContractRow.plan_id == row.id)
        )
        if existing:
            return ReconciliationContract.model_validate(existing.definition)
        proposal = PlanProposal.model_validate(row.proposal)
        if proposal.plan is None or proposal.status != "PROPOSED" or proposal.missing_requirements:
            raise DomainError("PLAN_NEEDS_REVIEW", "Kế hoạch chưa đủ bằng chứng để duyệt.", 422)
        cats = selected_catalogue(
            db,
            actor,
            row.project_id,
            [proposal.plan.left.canonical_id, proposal.plan.right.canonical_id],
        )
        validate_reconciliation_contract(proposal.plan, cats, actor.workspace_id, row.project_id)
        contract = ReconciliationContract(
            id=identifier(),
            workspace_id=actor.workspace_id,
            project_id=row.project_id,
            revision=1,
            plan=proposal.plan,
            approved_by=actor.id,
            approved_at=now(),
        )
        db.add(
            ReconciliationContractRow(
                id=contract.id,
                workspace_id=actor.workspace_id,
                project_id=row.project_id,
                plan_id=row.id,
                definition=contract.model_dump(mode="json"),
                source_signatures=template_signatures(cats),
            )
        )
        db.add(
            AuditRow(
                workspace_id=actor.workspace_id,
                actor_id=actor.id,
                action="RECONCILIATION_RULE_APPROVED",
                resource_id=contract.id,
            )
        )
        db.commit()
        return contract

    @router.get("/projects/{project_id}/reconciliation-templates")
    def templates(project_id: str, db: DB, actor: User) -> dict[str, Any]:
        get_scoped(db, ProjectRow, project_id, actor)
        rows = db.scalars(
            select(ReconciliationContractRow)
            .where(
                ReconciliationContractRow.project_id == project_id,
                ReconciliationContractRow.workspace_id == actor.workspace_id,
            )
            .limit(100)
        )
        return {"items": [ReconciliationContract.model_validate(r.definition) for r in rows]}

    @router.post(
        "/reconciliation-contracts/{contract_id}/reuse", response_model=PlanView, status_code=201
    )
    def reuse(contract_id: str, body: TemplateInput, db: DB, actor: User) -> PlanView:
        require_editor(actor, db, contract_id)
        row = get_scoped(db, ReconciliationContractRow, contract_id, actor)
        old = ReconciliationContract.model_validate(row.definition)
        cats = selected_catalogue(
            db, actor, row.project_id, [body.left_canonical_id, body.right_canonical_id]
        )
        signatures = template_signatures(cats)
        for side in ("left", "right"):
            for field in ("schema", "transforms", "entity"):
                if signatures[side][field] != row.source_signatures[side][field]:
                    raise DomainError(
                        "TEMPLATE_SCHEMA_DRIFT",
                        "Schema/mapping/semantics đã đổi; không reuse.",
                        409,
                    )
        draft = old.plan.model_copy(deep=True)
        draft.period_start, draft.period_end = body.period_start, body.period_end
        for side, canonical_id in (
            ("left", body.left_canonical_id),
            ("right", body.right_canonical_id),
        ):
            slot = getattr(draft, side)
            slot.canonical_id = canonical_id
            slot.coverage_start = getattr(body, side + "_coverage_start")
            slot.coverage_end = getattr(body, side + "_coverage_end")
            slot.completeness, slot.snapshot_at = body.completeness, body.snapshot_at
            # A new period must not silently inherit an old settlement due date.
            if slot.settlement_due_at is not None:
                raise DomainError(
                    "TEMPLATE_COVERAGE_REVIEW", "Cần khai báo lại hạn quyết toán của kỳ mới.", 422
                )
        draft.evidence_ids = [body.left_canonical_id, body.right_canonical_id]
        draft = ReconciliationPlan.model_validate(draft.model_dump())
        validate_reconciliation_contract(draft, cats, actor.workspace_id, row.project_id)
        plan = PlanRow(
            workspace_id=actor.workspace_id,
            project_id=row.project_id,
            origin="APPROVED_TEMPLATE",
            proposal=PlanProposal(
                status="PROPOSED",
                plan=draft,
                missing_requirements=["Xác nhận lại coverage, kỳ và rule trước approval."],
            ).model_dump(mode="json"),
            created_by=actor.id,
        )
        db.add(plan)
        db.flush()
        db.add(
            AuditRow(
                workspace_id=actor.workspace_id,
                actor_id=actor.id,
                action="RECONCILIATION_TEMPLATE_PROPOSED",
                resource_id=plan.id,
            )
        )
        db.commit()
        return plan_view(db, plan)

    @router.post("/reconciliation-runs", status_code=202)
    def run(body: RunInput, db: DB, actor: User, key: Key) -> dict[str, Any]:
        require_editor(actor, db, body.contract_id)
        rule = get_scoped(db, ReconciliationContractRow, body.contract_id, actor)
        contract = ReconciliationContract.model_validate(rule.definition)
        cats = selected_catalogue(
            db,
            actor,
            rule.project_id,
            [contract.plan.left.canonical_id, contract.plan.right.canonical_id],
        )
        validate_reconciliation_contract(contract.plan, cats, actor.workspace_id, rule.project_id)
        signature = hashlib.sha256(
            json.dumps(
                dict(
                    contract=contract.model_dump(mode="json"),
                    sources=[c.canonical.model_dump(mode="json") for c in cats],
                    engine=ENGINE_REVISION,
                ),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int.from_bytes(bytes.fromhex(signature[:16]), "big", signed=True)},
        )
        existing = db.scalar(
            select(RunRow).where(
                RunRow.project_id == rule.project_id, RunRow.input_signature == signature
            )
        )
        if existing is None:
            existing = RunRow(
                id=identifier(),
                workspace_id=actor.workspace_id,
                project_id=rule.project_id,
                contract_id=rule.id,
                input_signature=signature,
                engine_revision=ENGINE_REVISION,
                source_refs=[c.canonical.model_dump(mode="json") for c in cats],
            )
            db.add(existing)
            db.flush()
        job = enqueue_job(
            db,
            actor.workspace_id,
            rule.project_id,
            "reconcile",
            "run:" + existing.id,
            {"run_id": existing.id},
        )
        db.commit()
        return {"run_id": existing.id, "job_id": job.id, "status": existing.status}

    @router.get("/runs", response_model=RunList)
    def runs(
        project_id: str,
        db: DB,
        actor: User,
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=100),
        period_start: date | None = None,
        period_end: date | None = None,
        source_id: str = Query("", max_length=64),
    ) -> RunList:
        get_scoped(db, ProjectRow, project_id, actor)
        query = select(RunRow).where(
            RunRow.project_id == project_id, RunRow.workspace_id == actor.workspace_id
        )
        if period_start is not None or period_end is not None or source_id:
            query = query.join(
                ReconciliationContractRow, RunRow.contract_id == ReconciliationContractRow.id
            )
            plan_json = ReconciliationContractRow.definition["plan"]
            if period_start is not None:
                query = query.where(plan_json["period_start"].astext >= str(period_start))
            if period_end is not None:
                query = query.where(plan_json["period_end"].astext <= str(period_end))
            if source_id:
                from sqlalchemy import or_

                query = query.where(
                    or_(
                        plan_json["left"]["canonical_id"].astext == source_id,
                        plan_json["right"]["canonical_id"].astext == source_id,
                    )
                )
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.scalars(query.order_by(RunRow.created_at.desc()).offset(offset).limit(limit))
        return RunList(items=[run_contract(r) for r in rows], total=total)

    @router.get("/runs/{run_id}", response_model=ReconciliationRun)
    def get_run(run_id: str, db: DB, actor: User) -> ReconciliationRun:
        return run_contract(get_scoped(db, RunRow, run_id, actor))

    @router.get("/runs/{run_id}/metrics", response_model=MetricSnapshot)
    def metrics(run_id: str, db: DB, actor: User) -> MetricSnapshot:
        row = get_scoped(db, RunRow, run_id, actor)
        require_verified(row)
        return MetricSnapshot.model_validate(row.metric_snapshot)

    @router.get("/runs/{run_id}/matches", response_model=MatchPage)
    def matches(
        run_id: str,
        db: DB,
        actor: User,
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=100),
        search: str = Query("", max_length=120),
        linkage: str = "",
        comparison: str = "",
    ) -> MatchPage:
        row = get_scoped(db, RunRow, run_id, actor)
        require_verified(row)
        items, total = match_page(row, offset, limit, search, linkage, comparison)
        return MatchPage(items=items, total=total, offset=offset, limit=limit)

    @router.get("/runs/{run_id}/groups/{group_id}/evidence")
    def evidence(run_id: str, group_id: str, db: DB, actor: User) -> dict[str, Any]:
        row = get_scoped(db, RunRow, run_id, actor)
        require_verified(row)
        groups, _ = match_page(row, 0, 1, group_id)
        if not groups or groups[0].id != group_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy group trong run này.", 404)
        group = groups[0]
        rule = get_scoped(db, ReconciliationContractRow, row.contract_id, actor)
        sources = []
        from studio.contracts import CanonicalDataset

        for source in row.source_refs:
            cat = CanonicalDataset.model_validate(source)
            members = [m.record_id for m in group.members if m.canonical_id == cat.id]
            # Group membership can be large; paginate evidence within each source.
            records = load_canonical_records(db, actor, cat, members[:100]) if members else []
            table = get_scoped(db, TableRow, cat.source_table_id, actor)
            parsed = ParsedTableArtifact.model_validate(table.parsed_contract)
            mapping: MappingRevision = mapping_contract(
                get_scoped(db, MappingRow, cat.mapping_revision_id, actor)
            )
            if mapping.source_table_id != table.id:
                raise DomainError("EVIDENCE_SCOPE_INVALID", "Mapping không thuộc nguồn.", 422)
            columns = {c.id for c in parsed.columns}
            lineage: dict[str, list[str]] = {}
            for decision in mapping.decisions:
                if decision.candidate_target is None:
                    continue
                transform = decision.transformation_candidate
                inputs = (
                    transform.fields
                    if transform.op in {"add_fields", "subtract_fields", "coalesce_with_rule"}
                    else [decision.source_field]
                )
                lineage[decision.candidate_target] = [c for c in inputs if c in columns]
            record_views = []
            for record in records:
                field_refs: dict[str, list[EvidenceRef]] = {}
                for field, inputs in lineage.items():
                    field_refs[field] = [
                        EvidenceRef(
                            id=f"{p.source_table_id}:{column}",
                            workspace_id=actor.workspace_id,
                            file_id=p.file_id,
                            source_table_id=p.source_table_id,
                            sheet=p.sheet,
                            row=p.row,
                            column=column,
                        )
                        for p in record.provenance[:100]
                        for column in inputs
                        if p.source_table_id == table.id
                    ]
                record_views.append(
                    record.model_dump(mode="json")
                    | dict(
                        field_evidence=field_refs,
                        field_evidence_complete=len(record.provenance) <= 100,
                    )
                )
            version = db.get(VersionRow, table.dataset_version_id)
            assert version is not None
            dataset = get_scoped(db, DatasetRow, version.dataset_id, actor)
            sources.append(
                dict(
                    canonical=cat,
                    filename=dataset.name,
                    records=record_views,
                    member_count=len(members),
                    evidence_complete=len(members) <= 100,
                )
            )
        return {
            "run_id": run_id,
            "group": group,
            "sources": sources,
            "rule": ReconciliationContract.model_validate(rule.definition),
        }

    @router.get("/runs/{run_id}/exceptions", response_model=CaseList)
    def cases(
        run_id: str,
        db: DB,
        actor: User,
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=100),
        state: str = "",
        issue: str = "",
        search: str = Query("", max_length=120),
        sort: Literal["type", "state"] = "type",
    ) -> CaseList:
        row = get_scoped(db, RunRow, run_id, actor)
        require_verified(row)
        base = select(ExceptionRow).where(
            ExceptionRow.run_id == run_id, ExceptionRow.workspace_id == actor.workspace_id
        )
        opened = (
            db.scalar(
                select(func.count()).select_from(
                    base.where(ExceptionRow.workflow_state.in_(["OPEN", "IN_REVIEW"])).subquery()
                )
            )
            or 0
        )
        query = base
        if state:
            query = query.where(ExceptionRow.workflow_state == state)
        if issue:
            query = query.where(ExceptionRow.type == issue)
        if search:
            query = query.where(
                func.strpos(
                    func.lower(ExceptionRow.type + " " + ExceptionRow.notes), search.lower()
                )
                > 0
            )
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        query = (
            query.order_by(
                ExceptionRow.type if sort == "type" else ExceptionRow.workflow_state,
                ExceptionRow.id,
            )
            .offset(offset)
            .limit(limit)
        )
        return CaseList(
            items=[case_view(c) for c in db.scalars(query)], total=total, current_open_count=opened
        )

    @router.patch("/exceptions/{case_id}/review", response_model=ExceptionCase)
    def review(case_id: str, body: ReviewInput, db: DB, actor: User) -> ExceptionCase:
        require_editor(actor, db, case_id)
        row = get_scoped(db, ExceptionRow, case_id, actor)
        if body.workflow_state in {"RESOLVED", "DISMISSED_WITH_REASON"} and not body.notes.strip():
            raise DomainError("REVIEW_REASON_REQUIRED", "Cần ghi lý do khi đóng ngoại lệ.", 422)
        row.workflow_state, row.notes = body.workflow_state, body.notes
        row.reviewed_by, row.reviewed_at = actor.id, now()
        db.add(
            AuditRow(
                workspace_id=actor.workspace_id,
                actor_id=actor.id,
                action="EXCEPTION_REVIEWED",
                resource_id=row.id,
            )
        )
        db.commit()
        return case_view(row)

    @router.post("/runs/{run_id}/exports", status_code=202)
    def export(
        run_id: str, db: DB, actor: User, key: Key, format: Literal["csv", "xlsx"] = "xlsx"
    ) -> dict[str, str]:
        require_editor(actor, db, run_id)
        row = get_scoped(db, RunRow, run_id, actor)
        require_verified(row)
        db.refresh(row, with_for_update=True)
        artifact = db.scalar(
            select(ExportRow).where(
                ExportRow.run_id == run_id,
                ExportRow.format == format,
                ExportRow.revision == REPORT_REVISION,
            )
        )
        if artifact is None:
            artifact = ExportRow(
                id=identifier(),
                workspace_id=actor.workspace_id,
                project_id=row.project_id,
                run_id=run_id,
                format=format,
                revision=REPORT_REVISION,
            )
            db.add(artifact)
            db.flush()
        job = enqueue_job(
            db,
            actor.workspace_id,
            row.project_id,
            "export",
            "export:" + artifact.id,
            {"export_id": artifact.id},
        )
        db.commit()
        return {"export_id": artifact.id, "job_id": job.id, "status": artifact.status}

    @router.get("/exports/{export_id}")
    def export_info(export_id: str, db: DB, actor: User) -> dict[str, Any]:
        row = get_scoped(db, ExportRow, export_id, actor)
        job = db.scalar(
            select(JobRow).where(
                JobRow.workspace_id == actor.workspace_id,
                JobRow.idempotency_key == "export:" + row.id,
            )
        )
        return dict(
            id=row.id,
            run_id=row.run_id,
            status=row.status,
            format=row.format,
            sha256=row.sha256,
            revision=row.revision,
            review_state_scope="FIRST_GENERATION",
            review_state_as_of=(job.result or {}).get("review_state_as_of") if job else None,
            notice_vi="File bất biến từ lần tạo đầu cho định dạng/revision này; "
            "review sau đó không cập nhật file. KPI luôn từ snapshot của run.",
            download_url=f"/api/exports/{row.id}/download" if row.status == "SUCCEEDED" else None,
        )

    @router.get("/exports/{export_id}/download")
    def download(export_id: str, db: DB, actor: User) -> FileResponse:
        from studio.config import settings

        row = get_scoped(db, ExportRow, export_id, actor)
        if row.status != "SUCCEEDED" or row.storage_key is None:
            raise DomainError("EXPORT_NOT_READY", "Báo cáo chưa sẵn sàng.", 409)
        path = storage_path(settings.storage_root, row.storage_key)
        if checksum(path) != row.sha256:
            raise DomainError("ARTIFACT_CHECKSUM_FAILED", "Checksum báo cáo không hợp lệ.")
        return FileResponse(
            path,
            filename=f"reconciliation-{row.run_id}.{row.format}",
            media_type="text/csv; charset=utf-8"
            if row.format == "csv"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return router
