"""State machine hữu hạn trên queue hiện có; review và bước mới công bố cùng transaction."""

import hashlib
import json
import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from studio.access import Actor, require_editor
from studio.agent_tools import (
    ExportAction,
    GroupLookupAction,
    GroupReference,
    JobReference,
    MappingAction,
    NormalizeAction,
    PlanAction,
    QueryAction,
    RunAction,
    execute_tool,
)
from studio.assistant import deterministic_answer
from studio.assistant_api import own_conversation
from studio.assistant_tools import agent_catalogue, build_fact_set
from studio.config import settings
from studio.contracts.agent import (
    ChartBlock,
    ChartPoint,
    DatasetBlock,
    DownloadBlock,
    FactsBlock,
    NormalizationDraft,
    ProgressBlock,
    ReviewRequest,
    TableBlock,
    WorkflowState,
    WorkflowStep,
    WorkflowView,
)
from studio.contracts.assistant import AssistantContext, ToolRequest, ToolResult
from studio.contracts.reconciliation import PlanningRequest, PlanProposal, ReconciliationContract
from studio.database import (
    AgentWorkflowRow,
    CanonicalRow,
    DatasetRow,
    JobRow,
    MappingRow,
    MembershipRow,
    PlanRow,
    ReconciliationContractRow,
    TableRow,
    VersionRow,
    identifier,
    now,
)
from studio.errors import DomainError
from studio.repository import enqueue_job, get_scoped


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def owner(db: Session, row: AgentWorkflowRow) -> Actor:
    """Không dùng role do model hoặc job payload tự khai; đọc membership tại mỗi bước."""
    membership = db.get(MembershipRow, (row.workspace_id, row.actor_id))
    if membership is None:
        raise DomainError("RESOURCE_NOT_FOUND", "Quyền truy cập đã bị thu hồi.", 404)
    actor = Actor(row.actor_id, row.workspace_id, membership.role)
    own_conversation(db, actor, row.conversation_id)
    return actor


def own_workflow(db: Session, actor: Actor, ident: str, lock: bool = False) -> AgentWorkflowRow:
    row = get_scoped(db, AgentWorkflowRow, ident, actor)
    if row.actor_id != actor.id:
        raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy công việc.", 404)
    if lock:
        db.refresh(row, with_for_update=True)
    owner(db, row)
    return row


def view(row: AgentWorkflowRow) -> WorkflowView:
    return WorkflowView(
        id=row.id,
        conversation_id=row.conversation_id,
        context=AssistantContext.model_validate(row.context),
        state=row.state,
        detail=WorkflowState.model_validate(row.detail),
        updated_at=row.updated_at,
    )


def save(row: AgentWorkflowRow, state: WorkflowState) -> None:
    row.detail = state.model_dump(mode="json")
    row.updated_at = now()


def review_fingerprint(
    db: Session, actor: Actor, kind: str, resource_id: str, source_ids: list[str] | None = None
) -> str:
    if kind == "MAPPING":
        table = get_scoped(db, TableRow, resource_id, actor)
        latest = db.scalar(
            select(MappingRow)
            .where(MappingRow.source_table_id == table.id)
            .order_by(MappingRow.revision.desc())
            .limit(1)
        )
        return digest(
            [
                table.parsed_contract,
                table.profile,
                table.active_mapping_id,
                [
                    latest.id,
                    latest.revision,
                    latest.status,
                    latest.schema_id,
                    latest.signature,
                    latest.proposal,
                    latest.decision,
                ]
                if latest
                else None,
            ]
        )
    if kind == "RECONCILIATION":
        plan = get_scoped(db, PlanRow, resource_id, actor)
        proposal = PlanProposal.model_validate(plan.proposal)
        ids = (
            [proposal.plan.left.canonical_id, proposal.plan.right.canonical_id]
            if proposal.plan
            else proposal.suggestions.evidence_ids
            if proposal.suggestions
            else []
        )
        refs = []
        for ident in sorted(set(ids + (source_ids or []))):
            canonical = db.get(CanonicalRow, ident)
            if canonical and canonical.workspace_id == actor.workspace_id:
                table = get_scoped(db, TableRow, canonical.source_table_id, actor)
                refs.append(
                    [canonical.id, canonical.stale, canonical.contract, table.active_mapping_id]
                )
        return digest([plan.proposal, refs])
    return digest(resource_id)


def lock_review_sources(db: Session, actor: Actor, review: ReviewRequest) -> None:
    """Cùng lock nguồn với approval/manual worker trước khi kiểm fingerprint và ghi quyết định."""
    if review.kind == "MAPPING":
        table = get_scoped(db, TableRow, review.resource_id, actor)
        db.refresh(table, with_for_update=True)
    elif review.kind == "RECONCILIATION":
        ids = sorted(set(review.evidence_refs))
        canonicals = list(
            db.scalars(
                select(CanonicalRow)
                .where(
                    CanonicalRow.workspace_id == actor.workspace_id,
                    CanonicalRow.id.in_(ids),
                )
                .order_by(CanonicalRow.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        tables = sorted({c.source_table_id for c in canonicals})
        list(
            db.scalars(
                select(TableRow)
                .where(TableRow.id.in_(tables), TableRow.workspace_id == actor.workspace_id)
                .order_by(TableRow.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )


def make_review(
    db: Session,
    row: AgentWorkflowRow,
    state: WorkflowState,
    *,
    kind: str,
    resource_id: str,
    question: str,
    reason: str,
    draft: NormalizationDraft | None = None,
) -> None:
    if sum(r.state == "OPEN" for r in state.reviews) >= 3 or len(state.reviews) >= 10:
        row.state = "PARTIAL"
        state.blocks.append(
            ProgressBlock(text="Đã đạt giới hạn ba quyết định; phần còn lại cần lượt mới.")
        )
        return
    actor = owner(db, row)
    request = state.intent.planning_request if state.intent else None
    source_ids = (
        [request.left.canonical_id, request.right.canonical_id]
        if kind == "RECONCILIATION" and request
        else []
    )
    resource_label = None
    if kind == "MAPPING":
        table = get_scoped(db, TableRow, resource_id, actor)
        filename = db.scalar(
            select(DatasetRow.name)
            .join(VersionRow, VersionRow.dataset_id == DatasetRow.id)
            .where(VersionRow.id == table.dataset_version_id)
        )
        resource_label = f"{filename or 'Nguồn dữ liệu'} · {table.sheet}"
    review = ReviewRequest(
        id=identifier(),
        kind=kind,
        resource_id=resource_id,
        resource_label=resource_label,
        fingerprint=review_fingerprint(db, actor, kind, resource_id, source_ids),
        nonce=secrets.token_hex(16),
        expires_at=now() + timedelta(minutes=30),
        question=question,
        reason=reason,
        normalization_draft=draft,
        expected_effects=[
            "Giữ nguyên dữ liệu gốc và lịch sử.",
            "Chỉ chạy bước tiếp theo sau quyết định hợp lệ.",
        ],
        evidence_refs=[resource_id] + source_ids,
    )
    if kind == "RECONCILIATION":
        proposal = PlanProposal.model_validate(get_scoped(db, PlanRow, resource_id, actor).proposal)
        review.plan = proposal.plan
        review.suggestions = proposal.suggestions
        review.planning_request = state.intent.planning_request if state.intent else None
    state.reviews.append(review)
    row.state = "WAITING_REVIEW"


def notify_job_finished(db: Session, job: JobRow) -> None:
    """Cùng transaction với kết quả child job; crash không làm mất tín hiệu resume."""
    # Compatibility trước migration additive: jobs nền tảng vẫn công bố được.
    # Không nuốt ProgrammingError (nó sẽ làm hỏng transaction đã chứa artifacts).
    if db.scalar(text("SELECT to_regclass('agent_workflows')")) is None:
        return
    rows = db.scalars(
        select(AgentWorkflowRow)
        .where(
            AgentWorkflowRow.waiting_job_id == job.id,
            AgentWorkflowRow.state == "RUNNING",
        )
        .with_for_update()
    )
    for row in rows:
        enqueue_job(
            db,
            row.workspace_id,
            row.project_id,
            "agent_resume",
            f"agent-resume:{row.id}:{job.id}",
            dict(workflow_id=row.id),
        )


def wait_for(
    db: Session,
    row: AgentWorkflowRow,
    state: WorkflowState,
    tool: str,
    resource_id: str,
    reference: JobReference,
) -> None:
    if len(state.steps) >= settings.agent_max_steps:
        raise DomainError("AGENT_STEP_LIMIT", "Đã đạt giới hạn bước; chưa thực hiện phần còn lại.")
    row.waiting_job_id = reference.job_id
    row.state = "RUNNING"
    state.steps.append(
        WorkflowStep(tool=tool, resource_id=resource_id, job_id=reference.job_id, status="QUEUED")
    )
    child = get_scoped(db, JobRow, reference.job_id, owner(db, row))
    if child.status in {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}:
        notify_job_finished(db, child)


def consume_child(db: Session, row: AgentWorkflowRow, state: WorkflowState) -> bool:
    if row.waiting_job_id is None:
        return True
    actor = owner(db, row)
    child = get_scoped(db, JobRow, row.waiting_job_id, actor)
    if child.status in {"QUEUED", "RUNNING", "RETRYABLE_FAILURE"}:
        return False
    step = next(s for s in state.steps if s.job_id == child.id)
    step.status = "SUCCEEDED" if child.status == "SUCCEEDED" else "BLOCKED"
    row.waiting_job_id = None
    if child.status != "SUCCEEDED":
        row.state = (
            "PARTIAL" if any(isinstance(b, DatasetBlock) for b in state.blocks) else "BLOCKED"
        )
        state.error_code = child.error_code or "WORKFLOW_STEP_FAILED"
        state.blocks.append(
            ProgressBlock(text="Một bước bị chặn; các kết quả đã lưu vẫn được giữ.")
        )
        return False
    result = child.result or {}
    if child.kind == "agent_prepare":
        for item in result["drafts"]:
            draft = NormalizationDraft.model_validate(item)
            make_review(
                db,
                row,
                state,
                kind="MAPPING",
                resource_id=draft.table_id,
                question="Xác nhận những trường có ảnh hưởng đến ý nghĩa dữ liệu.",
                reason="Đây là quy tắc mới; AI chưa có quyền tự phê duyệt.",
                draft=draft,
            )
    elif child.kind == "reconciliation_plan":
        step.result_id = result["plan_id"]
        make_review(
            db,
            row,
            state,
            kind="RECONCILIATION",
            resource_id=result["plan_id"],
            question="Xác nhận khóa, số tiền, kỳ và phạm vi đối soát.",
            reason="Rule mới cần quyết định của bạn trước khi chạy.",
        )
    elif child.kind == "reconcile":
        step.result_id = result["run_id"]
        context = AssistantContext.model_validate(row.context)
        context.run_id = result["run_id"]
        context.group_id = context.case_id = None
        row.context = context.model_dump(mode="json")
    elif child.kind == "export":
        step.result_id = result.get("export_id") or child.payload["export_id"]
    elif child.kind == "normalize":
        step.result_id = result["canonical_id"]
    return True


def advance(db: Session, row: AgentWorkflowRow) -> None:
    """Chọn bước bằng state/policy xác định; không để model quản lý retry hoặc completion."""
    if row.state in {"COMPLETED", "FAILED", "BLOCKED", "CANCELLED_BEFORE_NEXT_STEP", "PARTIAL"}:
        return
    actor = owner(db, row)
    state = WorkflowState.model_validate(row.detail)
    if not consume_child(db, row, state):
        save(row, state)
        return
    if state.intent is None:
        save(row, state)
        return
    intent = state.intent
    context = AssistantContext.model_validate(row.context)
    catalogue = agent_catalogue(db, actor, context, state.dataset_ids or intent.dataset_ids)

    def facts(explain: bool = False) -> None:
        if len(state.steps) >= settings.agent_max_steps:
            raise DomainError("AGENT_STEP_LIMIT", "Đã đạt giới hạn bước.")
        result = execute_tool(
            db,
            actor,
            ToolRequest(
                name="get_match_evidence"
                if context.group_id or context.case_id
                else "get_run_summary",
                context=context,
            ),
            row.id,
        )
        assert isinstance(result, ToolResult)
        answer = deterministic_answer(
            "Vì sao lệch?" if explain else "Tóm tắt kết quả đối soát",
            build_fact_set(db, actor, context),
        )
        state.blocks.append(FactsBlock(result=result, answer=answer))
        state.steps.append(
            WorkflowStep(
                tool="read_verified_facts",
                resource_id=context.run_id or "",
                status="SUCCEEDED",
                result_id=context.run_id,
            )
        )
        snapshot = result.snapshot or (result.run.metric_snapshot if result.run else None)
        if snapshot and not explain:
            state.blocks.append(
                ChartBlock(
                    title="Kết luận so sánh theo nhóm",
                    unit="nhóm kết quả",
                    population=sum(snapshot.comparison_counts.values()),
                    population_definition="Tất cả nhóm kết quả; không phải mẫu số KPI khớp.",
                    points=[
                        ChartPoint(label=label, value=str(count))
                        for label, count in snapshot.comparison_counts.items()
                    ],
                    source_refs=[snapshot.run_id, snapshot.id],
                    verification_status=result.run.status if result.run else "VERIFIED",
                    period_start=str(snapshot.period_start),
                    period_end=str(snapshot.period_end),
                    timezone=snapshot.timezone,
                )
            )

    if intent.intent == "PREPARE_NORMALIZATION":
        require_editor(actor, db, row.id)
        waiting_tables = []
        for dataset in catalogue.datasets:
            for table in dataset.tables:
                if table.canonical_id:
                    canonical = get_scoped(db, CanonicalRow, table.canonical_id, actor)
                    if not any(
                        isinstance(b, DatasetBlock) and b.canonical_id == canonical.id
                        for b in state.blocks
                    ):
                        c = canonical.contract
                        mapping = get_scoped(db, MappingRow, canonical.mapping_id, actor)
                        assert mapping.decision is not None
                        state.blocks.append(
                            DatasetBlock(
                                dataset_id=dataset.id,
                                name=dataset.name,
                                table_id=table.table_id,
                                canonical_id=canonical.id,
                                rows=c["row_count"],
                                invalid_rows=c["invalid_count"],
                                status=c["quality_status"],
                                transformations=[
                                    d["transformation_candidate"]["op"]
                                    for d in mapping.decision["decisions"]
                                ],
                            )
                        )
                elif table.mapping_id:
                    reference = execute_tool(
                        db,
                        actor,
                        NormalizeAction(
                            name="run_normalization",
                            context=context,
                            dataset_id=dataset.id,
                            mapping_id=table.mapping_id,
                        ),
                        f"{row.id}:{table.mapping_id}",
                    )
                    assert isinstance(reference, JobReference)
                    wait_for(db, row, state, "run_normalization", table.table_id, reference)
                    save(row, state)
                    return
                elif not any(r.resource_id == table.table_id for r in state.reviews):
                    waiting_tables.append(table.table_id)
        if waiting_tables:
            if len(state.steps) >= settings.agent_max_steps:
                raise DomainError("AGENT_STEP_LIMIT", "Đã đạt giới hạn bước.")
            if (
                sum(r.state == "OPEN" for r in state.reviews) >= 3
                or len(state.reviews) >= 10
                or state.model_calls >= settings.agent_max_model_calls
            ):
                row.state = (
                    "WAITING_REVIEW" if any(r.state == "OPEN" for r in state.reviews) else "PARTIAL"
                )
                notice = (
                    "Còn nguồn chưa chuẩn bị vì giới hạn lượt xử lý; "
                    "các quyết định đã có vẫn được giữ."
                )
                if not any(isinstance(b, ProgressBlock) and b.text == notice for b in state.blocks):
                    state.blocks.append(ProgressBlock(text=notice))
                save(row, state)
                return
            reference = execute_tool(
                db,
                actor,
                MappingAction(
                    name="prepare_mapping_proposal",
                    context=context,
                    table_id=waiting_tables[0],
                    workflow_id=row.id,
                ),
                f"{row.id}:{waiting_tables[0]}",
            )
            assert isinstance(reference, JobReference)
            wait_for(
                db,
                row,
                state,
                "propose_mapping",
                waiting_tables[0],
                reference,
            )
        elif any(r.state == "OPEN" for r in state.reviews):
            row.state = "WAITING_REVIEW"
        else:
            row.state = (
                "PARTIAL"
                if any(isinstance(b, DatasetBlock) and b.status != "READY" for b in state.blocks)
                else "COMPLETED"
                if catalogue.datasets and all(d.tables for d in catalogue.datasets)
                else "WAITING_REVIEW"
            )
    elif intent.intent == "RECONCILE_DATASETS":
        require_editor(actor, db, row.id)
        existing_run = next(
            (
                s.result_id
                for s in state.steps
                if s.tool == "run_approved_reconciliation" and s.status == "SUCCEEDED"
            ),
            None,
        )
        if existing_run:
            context.run_id = existing_run
            facts()
            row.state = "COMPLETED"
        elif state.confirmed_contract_id:
            ref = execute_tool(
                db,
                actor,
                RunAction(
                    name="run_approved_reconciliation",
                    context=context,
                    contract_id=state.confirmed_contract_id,
                ),
                row.id,
            )
            assert isinstance(ref, JobReference)
            wait_for(
                db, row, state, "run_approved_reconciliation", state.confirmed_contract_id, ref
            )
        elif any(r.kind == "RECONCILIATION" for r in state.reviews):
            row.state = "WAITING_REVIEW"
        else:
            p = intent.planning_request
            if p is None:
                canonicals = [
                    t.canonical_id for d in catalogue.datasets for t in d.tables if t.canonical_id
                ]
                if len(canonicals) != 2:
                    raise DomainError("INPUT_AMBIGUOUS", "Chọn hai nguồn đã chuẩn hóa để đối soát.")
                p = PlanningRequest(
                    left=dict(canonical_id=canonicals[0]),
                    right=dict(canonical_id=canonicals[1]),
                    intent=row.goal,
                )
            # Chỉ reuse đúng toàn bộ source/scope đã xác nhận; template kỳ mới luôn review.
            approved = list(
                db.scalars(
                    select(ReconciliationContractRow)
                    .where(
                        ReconciliationContractRow.project_id == row.project_id,
                        ReconciliationContractRow.workspace_id == actor.workspace_id,
                    )
                    .limit(100)
                )
            )
            confirmed = p.model_dump(mode="json", exclude_unset=True)
            from studio.reconciliation_planner import missing_confirmations

            matches = []
            for candidate in approved:
                old = ReconciliationContract.model_validate(candidate.definition)
                data = old.plan.model_dump(mode="json")
                if missing_confirmations(p):
                    continue
                match = all(
                    all(data[k][f] == v for f, v in value.items())
                    if k in {"left", "right"}
                    else data.get(k) == value
                    for k, value in confirmed.items()
                    if k != "intent"
                )
                if match:
                    from studio.reconciliation_contracts import validate_reconciliation_contract
                    from studio.reconciliation_repository import selected_catalogue

                    cats = selected_catalogue(
                        db,
                        actor,
                        row.project_id,
                        [old.plan.left.canonical_id, old.plan.right.canonical_id],
                    )
                    validate_reconciliation_contract(
                        old.plan, cats, actor.workspace_id, row.project_id
                    )
                    matches.append(candidate.id)
            if len(matches) == 1:
                state.confirmed_contract_id = matches[0]
                save(row, state)
                advance(db, row)
                return
            if len(matches) > 1:
                raise DomainError("INPUT_AMBIGUOUS", "Có nhiều quy tắc phù hợp; cần chọn quy tắc.")
            ref = execute_tool(
                db,
                actor,
                PlanAction(name="prepare_reconciliation_plan", context=context, request=p),
                row.id,
            )
            assert isinstance(ref, JobReference)
            intent.planning_request = p
            wait_for(db, row, state, "prepare_reconciliation_plan", p.left.canonical_id, ref)
    elif intent.intent in {"QUERY_DATA", "CREATE_VISUALIZATION"}:
        if intent.query is None:
            raise DomainError("INPUT_AMBIGUOUS", "Cần chọn nguồn và điều kiện truy vấn rõ ràng.")
        result = execute_tool(
            db, actor, QueryAction(name="query_dataset", query=intent.query), row.id
        )
        from studio.contracts.data_query import QueryResult

        assert isinstance(result, QueryResult)
        state.blocks.append(TableBlock(result=result))
        state.steps.append(
            WorkflowStep(tool="query_dataset", resource_id=result.source_id, status="SUCCEEDED")
        )
        if intent.intent == "CREATE_VISUALIZATION":
            if len(intent.query.group_by) != 1 or not result.measure_units:
                raise DomainError(
                    "INSUFFICIENT_EVIDENCE",
                    "Biểu đồ cần một trường nhóm và count/tổng tiền có đơn vị.",
                )
            measure = next(iter(result.measure_units))
            group = intent.query.group_by[0]
            state.blocks.append(
                ChartBlock(
                    title="Kết quả truy vấn theo nhóm",
                    unit=result.measure_units[measure],
                    population=result.input_count,
                    population_definition=(
                        "Toàn bộ dòng khớp điều kiện trước khi phân nhóm/phân trang."
                    ),
                    completeness="TRUNCATED" if result.truncated or result.offset else "COMPLETE",
                    points=[
                        ChartPoint(label=str(record[group]), value=str(record[measure]))
                        for record in result.rows
                    ],
                    source_refs=result.source_refs,
                    verification_status=result.verification_status,
                )
            )
        row.state = "COMPLETED"
    elif intent.intent in {"EXPLAIN_RESULT", "SUMMARIZE_RESULTS"}:
        context.run_id = intent.run_id or context.run_id
        if intent.intent == "EXPLAIN_RESULT" and intent.key_value:
            try:
                found = execute_tool(
                    db,
                    actor,
                    GroupLookupAction(
                        name="find_match_group",
                        context=context.model_copy(update={"group_id": None, "case_id": None}),
                        key_value=intent.key_value,
                    ),
                    row.id,
                )
            except DomainError as exc:
                if exc.code not in {"INPUT_AMBIGUOUS", "INSUFFICIENT_EVIDENCE"}:
                    raise
                state.intent = intent.model_copy(
                    update={"intent": "CLARIFY", "questions": [exc.message_vi]}
                )
                make_review(
                    db,
                    row,
                    state,
                    kind="CLARIFICATION",
                    resource_id=row.id,
                    question=exc.message_vi,
                    reason="Cần xác định đúng nhóm kết quả.",
                )
                save(row, state)
                return
            assert isinstance(found, GroupReference)
            context.group_id, context.case_id = found.group_id, None
        facts(intent.intent == "EXPLAIN_RESULT")
        row.state = "COMPLETED"
    elif intent.intent == "EXPORT_RESULT":
        context.run_id = intent.run_id or context.run_id
        exported = next(
            (
                s.result_id
                for s in state.steps
                if s.tool == "start_export" and s.status == "SUCCEEDED"
            ),
            None,
        )
        if exported:
            assert context.run_id
            state.blocks.append(
                DownloadBlock(
                    export_id=exported, run_id=context.run_id, format=intent.export_format
                )
            )
            row.state = "COMPLETED"
        else:
            ref = execute_tool(
                db,
                actor,
                ExportAction(name="start_export", context=context, format=intent.export_format),
                row.id,
            )
            assert isinstance(ref, JobReference)
            wait_for(db, row, state, "start_export", context.run_id or "", ref)
    elif intent.intent == "EXPLORE_DATA":
        from studio.contracts.data_query import DataQuery, QueryResult

        tools_used = 0
        for dataset in catalogue.datasets:
            for table in dataset.tables:
                if tools_used >= settings.agent_max_tool_calls:
                    row.state = "PARTIAL"
                    state.blocks.append(
                        ProgressBlock(text="Đã đạt giới hạn trang xem; chọn nguồn để xem tiếp.")
                    )
                    save(row, state)
                    return
                result = execute_tool(
                    db,
                    actor,
                    QueryAction(
                        name="query_dataset",
                        query=DataQuery(
                            project_id=row.project_id,
                            source_kind="RAW_PREVIEW",
                            source_id=table.table_id,
                            select_fields=[c.id for c in table.columns[:8]],
                            limit=10,
                        ),
                    ),
                    row.id,
                )
                assert isinstance(result, QueryResult)
                state.blocks.append(
                    ProgressBlock(text=f"{dataset.name} · {table.sheet}: {table.row_count} dòng.")
                )
                state.blocks.append(TableBlock(result=result))
                tools_used += 1
        row.state = "COMPLETED" if tools_used else "WAITING_REVIEW"
    else:
        for question in intent.questions or ["Cần thêm dữ liệu hoặc xác nhận trước khi thực hiện."]:
            state.blocks.append(ProgressBlock(text=question))
        row.state = "WAITING_REVIEW" if intent.intent != "UNSUPPORTED" else "BLOCKED"
        if row.state == "WAITING_REVIEW" and not any(r.state == "OPEN" for r in state.reviews):
            make_review(
                db,
                row,
                state,
                kind="CLARIFICATION",
                resource_id=row.id,
                question=" ".join(intent.questions) or "Bạn muốn xử lý nguồn nào?",
                reason="Cần bổ sung ngữ cảnh trước khi thực hiện.",
            )
    row.context = context.model_dump(mode="json")
    save(row, state)
