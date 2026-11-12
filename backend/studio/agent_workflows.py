"""State machine hữu hạn trên queue hiện có; review và bước mới công bố cùng transaction."""

import hashlib
import json
import re
import secrets
from datetime import date, timedelta
from typing import Any, get_args

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from studio.access import Actor, require_editor
from studio.agent_intents import requests_exclusion_impact
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
from studio.assistant import deterministic_answer, plain_question
from studio.assistant_api import own_conversation
from studio.assistant_tools import agent_catalogue, build_fact_set
from studio.config import settings
from studio.contracts.agent import (
    AgentIntent,
    ChartBlock,
    ChartPoint,
    ClarificationOption,
    DatasetBlock,
    DownloadBlock,
    FactsBlock,
    IntentCatalogue,
    NormalizationDraft,
    ProgressBlock,
    ReviewRequest,
    TableBlock,
    WorkflowState,
    WorkflowStep,
    WorkflowView,
)
from studio.contracts.assistant import AssistantCommand, AssistantContext, ToolRequest, ToolResult
from studio.contracts.data_query import DataQuery, QueryResult
from studio.contracts.reconciliation import (
    PlanningCandidate,
    PlanningRequest,
    PlanningSource,
    PlanProposal,
    ReconciliationContract,
)
from studio.database import (
    AgentWorkflowRow,
    AuditRow,
    CanonicalRow,
    ConversationRow,
    DatasetRow,
    JobRow,
    MappingRow,
    MembershipRow,
    PlanRow,
    ReconciliationContractRow,
    RunRow,
    TableRow,
    VersionRow,
    identifier,
    now,
)
from studio.errors import DomainError
from studio.repository import enqueue_job, get_scoped, mapping_archived


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def publish_source_inspection(
    db: Session,
    row: AgentWorkflowRow,
    state: WorkflowState,
    actor: Actor,
    context: AssistantContext,
    request: tuple[str, int, str | None],
) -> None:
    """Publish actual scoped rows and issue summaries without changing source data."""
    from studio.data_query import compare_source_row

    mode, count, requested = request
    context = AssistantContext(
        project_id=context.project_id, dataset_id=None if requested else context.dataset_id
    )
    catalogue = agent_catalogue(db, actor, context, state.dataset_ids if not requested else [])
    sources = catalogue.datasets
    if requested:

        def words(value: str) -> str:
            return " ".join(re.findall(r"[a-z0-9]+", plain_question(value)))

        name = words(requested)
        sources = [item for item in sources if name and f" {name} " in f" {words(item.name)} "]
        if len(sources) != 1:
            state.blocks.append(
                ProgressBlock(text="Chưa xác định được đúng nguồn. Hãy nêu tên tệp cần xem.")
            )
            return
    targets = [(item, table) for item in sources for table in item.tables]
    if mode == "compare":
        if len(targets) != 1:
            state.blocks.append(ProgressBlock(text=f"Bạn muốn xem dòng {count} của nguồn nào?"))
            return
        dataset, table = targets[0]
        state.blocks.append(
            compare_source_row(db, actor, row.project_id, table, dataset.name, count)
        )
        return
    if not sources:
        state.blocks.append(ProgressBlock(text="Dự án chưa có nguồn dữ liệu."))
        return
    for item in sources:
        if not item.tables:
            text = "Đọc tệp thất bại." if item.status == "FAILED" else "Đang đọc tệp."
            state.blocks.append(ProgressBlock(text=f"{item.name} · {text}"))
    for dataset, table in targets[: settings.agent_max_tool_calls]:
        title = f"{dataset.name} · {table.sheet}"
        canonical = (
            get_scoped(db, CanonicalRow, table.canonical_id, actor) if table.canonical_id else None
        )
        mapping = get_scoped(db, MappingRow, canonical.mapping_id, actor) if canonical else None
        if mode == "quality" and canonical and mapping:
            c = canonical.contract
            state.blocks.append(
                DatasetBlock(
                    dataset_id=dataset.id,
                    canonical_id=canonical.id,
                    table_id=table.table_id,
                    name=dataset.name,
                    rows=c["row_count"],
                    invalid_rows=c["invalid_count"],
                    excluded_rows=c.get("excluded_source_rows", 0),
                    status=c["quality_status"],
                    transformations=[
                        d["transformation_candidate"]["op"]
                        for d in (mapping.decision or {})["decisions"]
                    ],
                )
            )
            continue
        if mode == "processed" and canonical and mapping:
            c = canonical.contract
            policy = (mapping.decision or {}).get("policy_application")
            explanation = (
                "Áp dụng quy tắc đã kiểm chứng tự động." if policy else "Áp dụng quy tắc đã duyệt."
            )
            state.blocks.append(
                ProgressBlock(
                    text=(
                        f"{title} · {c['valid_count']} dòng dùng được, "
                        f"{c['invalid_count']} dòng cần kiểm tra. {explanation}"
                    )
                )
            )
            kind, source_id = "CANONICAL", canonical.id
        elif mode == "raw":
            kind, source_id = "RAW_PREVIEW", table.table_id
        elif table.prepared_artifact_id:
            kind = "PREPARED_ISSUES" if mode == "quality" else "PREPARED"
            source_id = table.table_id
            state.blocks.append(
                ProgressBlock(
                    text=f"{title} · Bản chuẩn bị để xem. Còn thiếu căn cứ đối soát tài chính."
                )
            )
        else:
            state.blocks.append(ProgressBlock(text=f"{title} · Hiện chỉ có dữ liệu gốc để xem."))
            continue
        result = execute_tool(
            db,
            actor,
            QueryAction(
                name="query_dataset",
                query=DataQuery(
                    project_id=row.project_id, source_kind=kind, source_id=source_id, limit=count
                ),
            ),
            row.id,
        )
        assert isinstance(result, QueryResult)
        state.blocks.append(TableBlock(result=result, title=title))
    if len(targets) > settings.agent_max_tool_calls:
        state.blocks.append(ProgressBlock(text="Hãy nêu tên nguồn để xem các bảng còn lại."))


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
    """Persist an export scope using existing query fields, readable by rollback images.

    The typed API/wire scope is transient metadata. DISPLAYED_QUERY is encoded by
    the pinned DataQuery on the intent and existing state.export_query. Never
    discard an unpinned scope or apply this exclusion to untrusted result rows.
    """
    intents = [state.intent]
    for review in state.reviews:
        intents.extend([review.reply_intent, *(option.intent for option in review.options)])
    for intent in intents:
        if intent and intent.intent == "EXPORT_RESULT" and intent.export_scope == "DISPLAYED_QUERY":
            if state.export_query is None or (
                intent.query is not None and intent.query != state.export_query
            ):
                raise DomainError("QUERY_SEMANTICS_REQUIRED", "Bảng cần xuất chưa được ghim.")
            if intent.query is None:
                intent.query = state.export_query.model_copy(deep=True)
    row.detail = state.model_dump(
        mode="json",
        exclude={
            **({"sequence_progress": True} if state.sequence_progress is None else {}),
            **({"sequence_clarifications": True} if not state.sequence_clarifications else {}),
            **({"resumable_job_id": True} if not state.resumable_job_id else {}),
            "blocks": {
                index: (
                    {"discrepancies_only"}
                    if isinstance(block, DownloadBlock)
                    else {
                        **({"excluded_rows": True} if not block.excluded_rows else {}),
                        **({"quality_draft": True} if block.quality_draft is None else {}),
                    }
                )
                for index, block in enumerate(state.blocks)
                if isinstance(block, DatasetBlock)
                or (isinstance(block, DownloadBlock) and not block.discrepancies_only)
            },
            "intent": {"export_scope"},
            "reviews": {
                index: {
                    "reply_intent": {"export_scope"},
                    "options": {"__all__": {"intent": {"export_scope"}}},
                    **({"source_evidence": True} if not review.source_evidence else {}),
                    **({"scope_check_pending": True} if not review.scope_check_pending else {}),
                }
                for index, review in enumerate(state.reviews)
            },
            **(
                {"sequence_progress": {"propose_pairs", "planning_canonicals"}}
                if state.sequence_progress and not state.sequence_progress.propose_pairs
                else {}
            ),
        },
    )
    row.updated_at = now()


def review_fingerprint(
    db: Session, actor: Actor, kind: str, resource_id: str, source_ids: list[str] | None = None
) -> str:
    if kind == "MAPPING":
        table = get_scoped(db, TableRow, resource_id, actor)
        latest = db.scalar(
            select(MappingRow)
            .where(MappingRow.source_table_id == table.id, ~mapping_archived())
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
        scoped = select(CanonicalRow).where(
            CanonicalRow.workspace_id == actor.workspace_id, CanonicalRow.id.in_(ids)
        )
        tables = set(db.scalars(scoped.with_only_columns(CanonicalRow.source_table_id)))
        # Mapping approval holds table locks before marking canonical rows stale.
        # Take the same order, then refresh canonical state for the fingerprint.
        list(
            db.scalars(
                select(TableRow)
                .where(TableRow.id.in_(tables), TableRow.workspace_id == actor.workspace_id)
                .order_by(TableRow.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        list(
            db.scalars(
                scoped.order_by(CanonicalRow.id)
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
    planning_candidates: list[PlanningCandidate] | None = None,
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
        extraction_review_required=bool(table.parsed_contract["warnings"])
        if kind == "MAPPING"
        else None,
        expected_effects=[
            "Giữ nguyên dữ liệu gốc và lịch sử.",
            "Chỉ chạy bước tiếp theo sau quyết định hợp lệ.",
        ],
        evidence_refs=[resource_id] + source_ids,
    )
    if kind == "RECONCILIATION":
        from studio.reconciliation_repository import planning_source_evidence

        plan_row = get_scoped(db, PlanRow, resource_id, actor)
        proposal = PlanProposal.model_validate(plan_row.proposal)
        review.plan = proposal.plan
        review.suggestions = proposal.suggestions
        review.planning_request = state.intent.planning_request if state.intent else None
        review.planning_candidates = planning_candidates or []
        if review.planning_request:
            review.source_evidence = planning_source_evidence(
                db, actor, row.project_id, review.planning_request
            )
        if review.planning_candidates and review.plan is None:
            review.question = "Cột nào dùng để liên kết hai nguồn này?"
        elif review.plan is None and review.planning_request:
            from studio.reconciliation_planner import missing_confirmations

            if missing_confirmations(review.planning_request):
                review.scope_check_pending = True
                review.question = "Xác nhận các thông tin nguồn còn thiếu."
                review.reason = "Thông tin đã lưu và khoảng ngày quan sát được hiển thị bên dưới."
        if (
            plan_row.origin == "DETERMINISTIC"
            and not review.scope_check_pending
            and proposal.plan is None
            and proposal.reasoning
        ):
            review.reason = proposal.reasoning
    state.reviews.append(review)
    row.state = "WAITING_REVIEW"


def resume_prepared_reviews(db: Session, table_id: str | None = None) -> None:
    """Queue a read of approved canonical sources, including historical waiting cards.

    No workflow lock is taken while a normalizer holds its source lock. The
    existing resume job reauthorizes and locks the workflow before invalidating
    old cards. Its restricted advance cannot call a model or approve a mapping.
    """
    if db.scalar(text("SELECT to_regclass('agent_workflows')")) is None:
        return
    query = (
        select(AgentWorkflowRow)
        .join(ConversationRow, ConversationRow.id == AgentWorkflowRow.conversation_id)
        .join(
            MembershipRow,
            (MembershipRow.workspace_id == AgentWorkflowRow.workspace_id)
            & (MembershipRow.actor_id == AgentWorkflowRow.actor_id),
        )
        .where(
            AgentWorkflowRow.state == "WAITING_REVIEW",
            AgentWorkflowRow.waiting_job_id.is_(None),
            AgentWorkflowRow.detail["intent"]["intent"].astext == "PREPARE_NORMALIZATION",
            ConversationRow.deleted_at.is_(None),
            MembershipRow.role.in_(["owner", "editor"]),
        )
    )
    if table_id:
        query = query.where(
            AgentWorkflowRow.detail.contains(
                {"reviews": [dict(kind="MAPPING", resource_id=table_id, state="OPEN")]}
            )
        )
    for row in db.scalars(query):
        tables = [
            review["resource_id"]
            for review in row.detail.get("reviews", [])
            if review["kind"] == "MAPPING" and review["state"] == "OPEN"
        ]
        canonical_ids = sorted(
            db.scalars(
                select(CanonicalRow.id)
                .join(TableRow, TableRow.id == CanonicalRow.source_table_id)
                .join(VersionRow, VersionRow.id == TableRow.dataset_version_id)
                .join(DatasetRow, DatasetRow.id == VersionRow.dataset_id)
                .where(
                    TableRow.id.in_(tables),
                    CanonicalRow.workspace_id == row.workspace_id,
                    DatasetRow.project_id == row.project_id,
                    CanonicalRow.mapping_id == TableRow.active_mapping_id,
                    CanonicalRow.stale.is_(False),
                )
            )
        )
        if canonical_ids:
            enqueue_job(
                db,
                row.workspace_id,
                row.project_id,
                "agent_resume",
                f"agent-approved-sources:{row.id}:{digest(canonical_ids)[:32]}",
                dict(workflow_id=row.id, deterministic=True, approved_sources=True),
            )


def notify_job_finished(db: Session, job: JobRow) -> None:
    """Cùng transaction với kết quả child job; crash không làm mất tín hiệu resume."""
    # Compatibility trước migration additive: jobs nền tảng vẫn công bố được.
    # Không nuốt ProgrammingError (nó sẽ làm hỏng transaction đã chứa artifacts).
    if db.scalar(text("SELECT to_regclass('agent_workflows')")) is None:
        return
    if job.kind == "normalize" and job.status == "SUCCEEDED":
        resume_prepared_reviews(db, job.payload["table_id"])
        if job.payload.get("quality_revision", 0):
            partial = db.scalars(
                select(AgentWorkflowRow)
                .join(ConversationRow, ConversationRow.id == AgentWorkflowRow.conversation_id)
                .join(
                    MembershipRow,
                    (MembershipRow.workspace_id == AgentWorkflowRow.workspace_id)
                    & (MembershipRow.actor_id == AgentWorkflowRow.actor_id),
                )
                .where(
                    AgentWorkflowRow.workspace_id == job.workspace_id,
                    AgentWorkflowRow.project_id == job.project_id,
                    AgentWorkflowRow.state == "PARTIAL",
                    AgentWorkflowRow.detail["intent"]["intent"].astext == "PREPARE_NORMALIZATION",
                    AgentWorkflowRow.detail.contains(
                        {
                            "blocks": [
                                {"type": "dataset_summary", "table_id": job.payload["table_id"]},
                            ]
                        }
                    ),
                    ConversationRow.deleted_at.is_(None),
                    MembershipRow.role.in_(["owner", "editor"]),
                )
            )
            for workflow in partial:
                enqueue_job(
                    db,
                    job.workspace_id,
                    job.project_id,
                    "agent_resume",
                    f"agent-quality:{workflow.id}:{job.id}",
                    {"workflow_id": workflow.id, "deterministic": True, "quality_refresh": True},
                )
    rows = db.scalars(
        select(AgentWorkflowRow)
        .where(
            AgentWorkflowRow.waiting_job_id == job.id,
            AgentWorkflowRow.state == "RUNNING",
        )
        .with_for_update()
    )
    for row in rows:
        parent = db.get(JobRow, row.parent_job_id) if row.detail.get("intent") is None else None
        deterministic = row.detail.get("intent") is not None or (
            parent is not None and parent.payload.get("command") in get_args(AssistantCommand)
        )
        enqueue_job(
            db,
            row.workspace_id,
            row.project_id,
            "agent_resume",
            f"agent-resume:{row.id}:{job.id}" + (f":{job.attempts}" if job.attempts > 1 else ""),
            dict(workflow_id=row.id) | ({"deterministic": True} if deterministic else {}),
        )


def wait_for(
    db: Session,
    row: AgentWorkflowRow,
    state: WorkflowState,
    tool: str,
    resource_id: str,
    reference: JobReference,
) -> None:
    if len(state.steps) >= step_limit(state):
        raise DomainError("AGENT_STEP_LIMIT", "Đã đạt giới hạn bước; chưa thực hiện phần còn lại.")
    row.waiting_job_id = reference.job_id
    row.state = "RUNNING"
    state.steps.append(
        WorkflowStep(tool=tool, resource_id=resource_id, job_id=reference.job_id, status="QUEUED")
    )
    child = get_scoped(db, JobRow, reference.job_id, owner(db, row))
    if child.status in {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}:
        notify_job_finished(db, child)


def step_limit(state: WorkflowState) -> int:
    return settings.agent_max_steps + 8 if state.sequence_progress else settings.agent_max_steps


def advance_sequence(
    db: Session,
    row: AgentWorkflowRow,
    state: WorkflowState,
    context: AssistantContext,
    catalogue: IntentCatalogue,
) -> None:
    """Advance a completed phase without revisiting its jobs or human decisions."""
    progress = state.sequence_progress
    assert progress is not None
    if progress.stage == "EXPORT":
        progress.pair_index += 1
    if progress.pair_index == len(progress.sequence.pairs):
        row.context = context.model_dump(mode="json")
        save(row, state)
        return
    if progress.stage == "RECONCILE":
        assert context.run_id is not None
        run = get_scoped(db, RunRow, context.run_id, owner(db, row))
        snapshot = run.metric_snapshot
        if run.status not in {"VERIFIED", "PARTIAL_VERIFIED"} or snapshot is None:
            row.state = "PARTIAL"
            state.error_code = "INSUFFICIENT_EVIDENCE"
            state.blocks.append(
                ProgressBlock(
                    text="Lượt đối soát chưa được xác minh. Kiểm tra nguồn trước khi xuất."
                )
            )
            save(row, state)
            return
        if run.status == "PARTIAL_VERIFIED":
            state.blocks.append(
                ProgressBlock(text="Đã xác minh kết quả trên phần dữ liệu đủ điều kiện.")
            )
        if progress.pair_index == 0:
            progress.sequence.period_start = date.fromisoformat(snapshot["period_start"])
            progress.sequence.period_end = date.fromisoformat(snapshot["period_end"])
            progress.sequence.timezone = snapshot["timezone"]
        progress.stage = "EXPORT"
        state.intent = AgentIntent(intent="EXPORT_RESULT", run_id=context.run_id)
    else:
        pair = progress.sequence.pairs[progress.pair_index]
        canonical_ids = {
            dataset.id: dataset.tables[0].canonical_id
            for dataset in catalogue.datasets
            if len(dataset.tables) == 1
            and dataset.tables[0].canonical_status in {"READY", "PARTIAL"}
        }
        left = canonical_ids.get(pair.left_dataset_id)
        right = canonical_ids.get(pair.right_dataset_id)
        if not left or not right:
            row.state = "PARTIAL"
            state.error_code = "INSUFFICIENT_EVIDENCE"
            state.blocks.append(ProgressBlock(text="Hai nguồn cần có bản chuẩn hóa đã duyệt."))
            save(row, state)
            return
        progress.stage = "RECONCILE"
        names = {dataset.id: dataset.name for dataset in catalogue.datasets}
        state.blocks.append(
            ProgressBlock(
                text=(
                    f"Cặp {progress.pair_index + 1}: "
                    f"{names[pair.left_dataset_id]} ↔ {names[pair.right_dataset_id]}"
                )
            )
        )
        previous_slots = {}
        if state.confirmed_contract_id:
            approved = get_scoped(
                db, ReconciliationContractRow, state.confirmed_contract_id, owner(db, row)
            )
            previous = PlanningRequest.from_plan(
                ReconciliationContract.model_validate(approved.definition).plan
            )
            previous_slots = {
                source.canonical_id: source
                for source in (previous.left, previous.right)
                if not source.filters and source.settlement_due_at is None
            }
        state.confirmed_contract_id = None
        context.run_id = context.case_id = context.group_id = context.dataset_id = None
        state.intent = AgentIntent(
            intent="RECONCILE_DATASETS",
            planning_request=PlanningRequest(
                left=previous_slots.get(left, PlanningSource(canonical_id=left)).model_copy(
                    update={"role": "reference"}
                ),
                right=previous_slots.get(right, PlanningSource(canonical_id=right)).model_copy(
                    update={"role": "counterpart"}
                ),
                period_start=progress.sequence.period_start,
                period_end=progress.sequence.period_end,
                timezone=progress.sequence.timezone,
                intent=row.goal,
            ),
        )
    progress.step_start = len(state.steps)
    progress.review_start = len(state.reviews)
    row.state = "RUNNING"
    row.context = context.model_dump(mode="json")
    save(row, state)
    advance(db, row)


def consume_child(db: Session, row: AgentWorkflowRow, state: WorkflowState) -> bool:
    if row.waiting_job_id is None:
        return True
    actor = owner(db, row)
    child = get_scoped(db, JobRow, row.waiting_job_id, actor)
    if child.status in {"QUEUED", "RUNNING", "RETRYABLE_FAILURE"}:
        return False
    step = next(s for s in state.steps if s.job_id == child.id)
    if child.kind == "agent_prepare" and child.status == "BLOCKED" and child.attempts < 3:
        from studio.repository import gemini_retry_confirmed

        if gemini_retry_confirmed(child):
            row.state = "BLOCKED"
            state.error_code = child.error_code
            state.resumable_job_id = child.id
            return False
    step.status = "SUCCEEDED" if child.status == "SUCCEEDED" else "BLOCKED"
    row.waiting_job_id = None
    if child.status != "SUCCEEDED":
        if state.observed_comparison:
            return True
        if (
            (
                child.kind in {"parse", "automatic_preparation"}
                or (
                    child.kind in {"normalize", "mapping_reuse"}
                    and step.tool == "automatic_preparation"
                )
            )
            and state.intent
            and state.intent.intent == "PREPARE_NORMALIZATION"
        ):
            # Báo nguồn đọc lỗi từ metadata và tiếp tục với những nguồn khác.
            return True
        if child.kind == "agent_prepare" and any(r.state == "OPEN" for r in state.reviews):
            row.state = "WAITING_REVIEW"
        else:
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
                reason=(
                    "Định dạng được kiểm từ dữ liệu. Ý nghĩa mỗi dòng, khóa và số tiền "
                    "ảnh hưởng đến kết quả đối soát."
                    if state.prepare_upload
                    else "Đây là quy tắc mới; AI chưa có quyền tự phê duyệt."
                ),
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
            planning_candidates=[
                PlanningCandidate.model_validate(item) for item in result.get("candidates", [])
            ],
            reason=(
                "Chưa nhận được phương án từ AI. Bạn có thể thiết lập quy tắc trong Đối soát."
                if result.get("provider_error_code") == "AI_PLAN_MISSING"
                else "Hãy xác nhận mỗi dòng ở hai nguồn đại diện cho gì và quan hệ giữa hai nguồn."
                if result.get("provider_error_code")
                in {"CARDINALITY_GRAIN_INVALID", "AGGREGATION_UNAPPROVED"}
                else "Quy tắc mới cần bạn kiểm tra và duyệt trước khi đối soát."
            ),
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


def advance_pair_proposals(
    db: Session, row: AgentWorkflowRow, state: WorkflowState, catalogue: IntentCatalogue
) -> None:
    """Prepare both pairs before approval. Only explicit decisions enqueue a run."""
    progress = state.sequence_progress
    assert progress is not None and state.intent is not None
    actor = owner(db, row)
    require_editor(actor, db, row.id)
    project_context = AssistantContext(project_id=row.project_id)
    for review in state.reviews:
        if review.kind == "RECONCILIATION" and review.state == "DECIDED" and review.result_id:
            if any(step.resource_id == review.result_id for step in state.steps):
                continue
            reference = execute_tool(
                db,
                actor,
                RunAction(
                    name="run_approved_reconciliation",
                    context=project_context,
                    contract_id=review.result_id,
                ),
                f"{row.id}:approved:{review.id}",
            )
            assert isinstance(reference, JobReference)
            wait_for(db, row, state, "run_approved_reconciliation", review.result_id, reference)
            save(row, state)
            return
    current = [
        review
        for review in state.reviews[progress.review_start :]
        if review.kind == "RECONCILIATION" and review.state in {"OPEN", "DECIDED"}
    ]
    if current:
        review = current[-1]
        if not (review.plan or review.planning_candidates or review.state == "DECIDED"):
            row.state = "WAITING_REVIEW"
            save(row, state)
            return
        progress.pair_index += 1
        progress.review_start = len(state.reviews)
    if progress.pair_index >= len(progress.sequence.pairs):
        row.state = (
            "WAITING_REVIEW" if any(r.state == "OPEN" for r in state.reviews) else "COMPLETED"
        )
        save(row, state)
        return

    # Pin every canonical the first time so a new revision never borrows prior scope facts.
    ready = {
        dataset.id: dataset.tables[0].canonical_id
        for dataset in catalogue.datasets
        if len(dataset.tables) == 1 and dataset.tables[0].canonical_status in {"READY", "PARTIAL"}
    }
    if not progress.planning_canonicals:
        progress.planning_canonicals = {key: value for key, value in ready.items() if value}
    if any(
        ready.get(key) != progress.planning_canonicals.get(key) or not ready.get(key)
        for key in state.dataset_ids
    ):
        raise DomainError(
            "SOURCE_REVISION_INVALID",
            "Mỗi nguồn cần có một bản chuẩn hóa hiện hành. Kiểm tra lại nguồn đã thay đổi.",
        )
    pair = progress.sequence.pairs[progress.pair_index]
    left, right = (
        progress.planning_canonicals[key] for key in (pair.left_dataset_id, pair.right_dataset_id)
    )
    prior = next(
        (
            review.planning_request
            for review in reversed(state.reviews)
            if review.kind == "RECONCILIATION" and (review.plan or review.planning_candidates)
        ),
        None,
    )
    slots = {s.canonical_id: s for s in (prior.left, prior.right)} if prior else {}
    request = PlanningRequest(
        left=slots.get(left, PlanningSource(canonical_id=left)).model_copy(
            update={"role": "reference"}
        ),
        right=slots.get(right, PlanningSource(canonical_id=right)).model_copy(
            update={"role": "counterpart"}
        ),
        period_start=prior.period_start if prior else progress.sequence.period_start,
        period_end=prior.period_end if prior else progress.sequence.period_end,
        timezone=prior.timezone if prior else progress.sequence.timezone,
        effective_from=prior.effective_from if prior else progress.sequence.period_start,
        effective_to=prior.effective_to if prior else None,
        allow_partial=True
        if prior
        and prior.allow_partial
        and any(
            slots[ident].completeness != "CONFIRMED" for ident in (left, right) if ident in slots
        )
        else None,
        intent=row.goal,
    )
    state.intent.planning_request = request
    reference = execute_tool(
        db,
        actor,
        PlanAction(name="prepare_reconciliation_plan", context=project_context, request=request),
        f"{row.id}:proposal:{progress.pair_index}",
    )
    assert isinstance(reference, JobReference)
    wait_for(db, row, state, "prepare_reconciliation_plan", left, reference)
    save(row, state)


def advance(db: Session, row: AgentWorkflowRow, *, approved_only: bool = False) -> None:
    """Chọn bước bằng state/policy xác định; không để model quản lý retry hoặc completion."""
    if row.state in {"COMPLETED", "FAILED", "BLOCKED", "CANCELLED_BEFORE_NEXT_STEP", "PARTIAL"}:
        return
    actor = owner(db, row)
    state = WorkflowState.model_validate(row.detail)
    if approved_only and (
        row.state != "WAITING_REVIEW"
        or state.intent is None
        or state.intent.intent != "PREPARE_NORMALIZATION"
    ):
        return
    if approved_only:
        for review in sorted(state.reviews, key=lambda item: item.resource_id):
            if review.kind == "MAPPING" and review.state == "OPEN":
                lock_review_sources(db, actor, review)
    waiting_step = next(
        (s for s in state.steps if s.job_id and s.job_id == row.waiting_job_id), None
    )
    if not consume_child(db, row, state):
        save(row, state)
        return
    if state.intent is None:
        save(row, state)
        return
    intent = state.intent
    context = AssistantContext.model_validate(row.context)
    sequence = state.sequence_progress
    stage_steps = state.steps[sequence.step_start :] if sequence else state.steps
    stage_reviews = state.reviews[sequence.review_start :] if sequence else state.reviews
    if intent.intent == "CHECK_DATASET_STATUS":
        from studio.agent_intents import explicit_source_filenames
        from studio.dataset_status import (
            asks_source_inventory,
            read_processing_status,
            status_description,
        )

        try:
            statuses = read_processing_status(
                db,
                actor,
                context,
                state.dataset_ids or intent.dataset_ids,
                row.goal,
                dataset_names=tuple(explicit_source_filenames(row.goal)) or None,
            )
        except DomainError as exc:
            if exc.code != "INPUT_AMBIGUOUS":
                raise
            make_review(
                db,
                row,
                state,
                kind="CLARIFICATION",
                resource_id=row.id,
                question=exc.message_vi,
                reason="Cần chọn đúng nguồn để kiểm tra trạng thái.",
            )
            save(row, state)
            return
        if not statuses:
            state.blocks.append(
                ProgressBlock(
                    text="Dự án chưa có tệp dữ liệu. Hãy dùng dấu cộng để tải CSV hoặc XLSX."
                )
            )
        else:
            if asks_source_inventory(row.goal):
                scope = "Phạm vi đang hỏi" if context.dataset_id or state.dataset_ids else "Dự án"
                state.blocks.append(
                    ProgressBlock(
                        text=f"{scope} có {len({s.dataset_id for s in statuses})} nguồn dữ liệu."
                    )
                )
            state.blocks.extend(ProgressBlock(text=status_description(s)) for s in statuses)
            state.blocks.append(
                ProgressBlock(
                    text=(
                        "Đây là trạng thái chuẩn hóa, chưa xác nhận các điều kiện của một q"
                        "uy tắc đối soát hoặc kết quả đối soát."
                    )
                )
            )
        row.state = "COMPLETED"
        save(row, state)
        return
    catalogue = agent_catalogue(
        db, actor, context, state.dataset_ids or intent.dataset_ids, workflow_id=row.id
    )

    def add_source_previews() -> int:
        shown = 0
        for dataset in catalogue.datasets:
            for table in dataset.tables:
                if shown >= settings.agent_max_tool_calls:
                    return shown
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
                count = f"{table.row_count:,}".replace(",", ".")
                state.blocks.extend(
                    [
                        ProgressBlock(
                            text=f"Tôi đã đọc {count} dòng từ {dataset.name} · {table.sheet}."
                        ),
                        TableBlock(result=result),
                    ]
                )
                shown += 1
        return shown

    def facts(explain: bool = False) -> None:
        if len(state.steps) >= step_limit(state):
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
        exclusion_question = not explain and requests_exclusion_impact(row.goal)
        if exclusion_question and result.run:
            excluded = []
            for side, source in zip(("trái", "phải"), result.run.source_refs, strict=False):
                if not source.excluded_source_rows:
                    continue
                excluded.append(
                    f"Nguồn bên {side} đã loại {source.excluded_source_rows} dòng khỏi "
                    "bản chuẩn hóa dùng cho lượt này. Các dòng đó nằm ngoài số nhóm và "
                    "chênh lệch tiền của báo cáo."
                )
                for amount in source.excluded_amounts:
                    field = f" ({amount['field']})" if len(source.excluded_amounts) > 1 else ""
                    excluded.append(
                        f"Số tiền loại trừ đã xác định{field} là {amount['amount']} "
                        f"{amount['currency']}."
                    )
                if source.excluded_amounts_unavailable:
                    excluded.append("Chưa xác định được đầy đủ số tiền loại trừ.")
            if not excluded:
                excluded.append(
                    "Hai bản chuẩn hóa dùng cho lượt này không ghi nhận dòng bị loại trừ."
                    if len(result.run.source_refs) == 2
                    else "Lượt này chưa lưu đủ thông tin nguồn để xác định số dòng bị loại trừ."
                )
            state.blocks.append(ProgressBlock(text="\n".join(excluded)))
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
        if snapshot and not (explain or exclusion_question):
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

    if state.observed_comparison:
        from studio.observed_reconciliation import (
            EQUIVALENCE_CONFIRMATION,
            ROLE_ORDER,
            observed_order_plan,
        )
        from studio.reconciliation_api import enqueue_approved_run, enqueue_observed_run

        require_editor(actor, db, row.id)
        active = db.scalar(
            select(JobRow)
            .where(
                JobRow.workspace_id == actor.workspace_id,
                JobRow.project_id == row.project_id,
                JobRow.status.in_(("QUEUED", "RUNNING", "RETRYABLE_FAILURE")),
                (
                    (JobRow.kind == "parse")
                    & JobRow.payload["dataset_id"].astext.in_(state.dataset_ids)
                )
                | (
                    JobRow.kind.in_(("automatic_preparation", "mapping_reuse", "normalize"))
                    & JobRow.payload["table_id"].astext.in_(
                        [
                            table.table_id
                            for dataset in catalogue.datasets
                            for table in dataset.tables
                        ]
                    )
                ),
            )
            .order_by(JobRow.created_at, JobRow.id)
            .limit(1)
        )
        if active:
            wait_for(
                db,
                row,
                state,
                "automatic_preparation",
                active.id,
                JobReference(job_id=active.id, status=active.status),
            )
            save(row, state)
            return
        if waiting_step and waiting_step.tool == "compare_observed" and waiting_step.result_id:
            run = get_scoped(db, RunRow, waiting_step.result_id, actor)
            if run.status == "PARTIAL_VERIFIED":
                facts()
            else:
                state.blocks.append(ProgressBlock(text="Kết quả một cặp chưa vượt qua kiểm chứng."))
        roles = {
            role: [
                d.tables[0].canonical_id
                for d in catalogue.datasets
                if len(d.tables) == 1
                and d.tables[0].canonical_id
                and d.tables[0].schema_definition
                and d.tables[0].schema_definition.entity_kind == role
            ]
            for role in ROLE_ORDER
        }
        needs_declaration = False
        for left, right in zip(ROLE_ORDER, ROLE_ORDER[1:], strict=False):
            pair = f"{left} ↔ {right}"
            if any(s.tool == "compare_observed" and s.resource_id == pair for s in state.steps):
                continue
            if len(roles[left]) != 1 or len(roles[right]) != 1:
                notice = f"{pair}: chưa đủ căn cứ để chọn một bản dữ liệu hiện hành cho mỗi nguồn."
                if not any(isinstance(b, ProgressBlock) and b.text == notice for b in state.blocks):
                    state.blocks.append(ProgressBlock(text=notice))
                continue
            ids = [roles[left][0], roles[right][0]]
            existing_contract = db.scalar(
                select(ReconciliationContractRow)
                .where(
                    ReconciliationContractRow.workspace_id == actor.workspace_id,
                    ReconciliationContractRow.project_id == row.project_id,
                    ReconciliationContractRow.definition["observation"]["revision"].astext
                    == "observed-order-revenue-1",
                    ReconciliationContractRow.definition["plan"]["left"]["canonical_id"].astext
                    == ids[0],
                    ReconciliationContractRow.definition["plan"]["right"]["canonical_id"].astext
                    == ids[1],
                )
                .limit(1)
            )
            try:
                if existing_contract:
                    accepted = enqueue_approved_run(existing_contract.id, db, actor)
                else:
                    plan, receipt = observed_order_plan(
                        db, actor, row.project_id, ids, state.observed_comparison == "DECLARED"
                    )
                    accepted = enqueue_observed_run(db, actor, row.project_id, plan, receipt)
            except DomainError as exc:
                if exc.code not in {
                    "OBSERVATION_SCOPE_INVALID",
                    "OBSERVATION_METRIC_REQUIRED",
                    "OBSERVATION_KEY_REQUIRED",
                }:
                    raise
                needs_declaration |= exc.code == "OBSERVATION_METRIC_REQUIRED"
                if not any(
                    isinstance(b, ProgressBlock) and b.text == exc.message_vi for b in state.blocks
                ):
                    state.blocks.append(ProgressBlock(text=exc.message_vi))
                continue
            state.blocks.append(ProgressBlock(text=pair))
            wait_for(
                db,
                row,
                state,
                "compare_observed",
                pair,
                JobReference(job_id=accepted["job_id"], status=accepted["status"]),
            )
            save(row, state)
            return
        if needs_declaration:
            state.blocks.append(
                ProgressBlock(
                    text=(
                        "Nếu đúng với nghiệp vụ, hãy nhắn "
                        f"“Đối soát ba nguồn. {EQUIVALENCE_CONFIRMATION}.”"
                    )
                )
            )
        row.context = context.model_dump(mode="json")
        row.state = (
            "COMPLETED" if sum(isinstance(b, FactsBlock) for b in state.blocks) == 2 else "PARTIAL"
        )
        save(row, state)
        return

    if sequence and sequence.propose_pairs:
        if waiting_step and waiting_step.tool == "run_approved_reconciliation":
            facts()
        advance_pair_proposals(db, row, state, catalogue)
        return

    if intent.intent == "PREPARE_NORMALIZATION":
        require_editor(actor, db, row.id)
        unread = [dataset for dataset in catalogue.datasets if not dataset.tables]
        if unread and not approved_only:
            parsing = db.scalar(
                select(JobRow)
                .where(
                    JobRow.workspace_id == actor.workspace_id,
                    JobRow.project_id == row.project_id,
                    JobRow.kind == "parse",
                    JobRow.status.in_(["QUEUED", "RUNNING", "RETRYABLE_FAILURE"]),
                    JobRow.payload["dataset_id"].astext.in_([dataset.id for dataset in unread]),
                )
                .order_by(JobRow.created_at, JobRow.id)
                .limit(1)
            )
            if parsing:
                wait_for(
                    db,
                    row,
                    state,
                    "parse",
                    parsing.payload["dataset_id"],
                    JobReference(job_id=parsing.id, status=parsing.status),
                )
                save(row, state)
                return
            for dataset in unread:
                message = f"{dataset.name} đã tải lên nhưng chưa có bảng đọc được."
                if dataset.status == "FAILED":
                    message = f"{dataset.name} đã tải lên nhưng đọc tệp thất bại."
                if not any(
                    isinstance(b, ProgressBlock) and b.text == message for b in state.blocks
                ):
                    state.blocks.append(ProgressBlock(text=message))
        if state.prepare_upload and not state.blocks:
            add_source_previews()
        waiting_tables = []
        for dataset in catalogue.datasets:
            for table in dataset.tables:
                if (
                    (state.prepare_upload or table.automatic_preparation)
                    and not table.canonical_id
                    and not approved_only
                ):
                    existing = db.scalar(
                        select(JobRow)
                        .where(
                            JobRow.workspace_id == actor.workspace_id,
                            JobRow.project_id == row.project_id,
                            JobRow.kind.in_(
                                ("automatic_preparation", "mapping_reuse", "normalize")
                            ),
                            JobRow.status.in_(("QUEUED", "RUNNING", "RETRYABLE_FAILURE")),
                            JobRow.payload["table_id"].astext == table.table_id,
                        )
                        .order_by(JobRow.created_at, JobRow.id)
                        .limit(1)
                    )
                    if existing:
                        wait_for(
                            db,
                            row,
                            state,
                            "automatic_preparation"
                            if table.automatic_preparation
                            else (
                                "run_normalization"
                                if existing.kind == "normalize"
                                else "reuse_mapping"
                            ),
                            table.table_id,
                            JobReference(job_id=existing.id, status=existing.status),
                        )
                        save(row, state)
                        return
                    if table.automatic_preparation:
                        from studio.dataset_status import read_processing_status, status_description

                        for item in read_processing_status(db, actor, context, [dataset.id]):
                            if item.table_id == table.table_id:
                                notice = status_description(item)
                                if not any(
                                    isinstance(b, ProgressBlock) and b.text == notice
                                    for b in state.blocks
                                ):
                                    state.blocks.append(ProgressBlock(text=notice))
                        continue
                    if (table.column_count or len(table.columns)) > 40:
                        notice = (
                            f"{dataset.name} · {table.sheet}: bảng có hơn 40 cột. "
                            "Xem dữ liệu gốc trong Chat và dùng kiểm tra chi tiết để ghép cột."
                        )
                        if not any(
                            isinstance(b, ProgressBlock) and b.text == notice for b in state.blocks
                        ):
                            state.blocks.append(ProgressBlock(text=notice))
                        continue
                if table.canonical_id:
                    for review in state.reviews:
                        if (
                            review.kind == "MAPPING"
                            and review.resource_id == table.table_id
                            and review.state == "OPEN"
                        ):
                            review.state = "INVALIDATED"
                            review.pending_reply_job_id = None
                            db.add(
                                AuditRow(
                                    workspace_id=actor.workspace_id,
                                    actor_id="system",
                                    action="AGENT_REVIEW_INVALIDATED",
                                    resource_id=review.id,
                                )
                            )
                    canonical = get_scoped(db, CanonicalRow, table.canonical_id, actor)
                    if not any(
                        isinstance(b, DatasetBlock) and b.canonical_id == canonical.id
                        for b in state.blocks
                    ):
                        c = canonical.contract
                        mapping = get_scoped(db, MappingRow, canonical.mapping_id, actor)
                        assert mapping.decision is not None
                        state.blocks = [
                            b
                            for b in state.blocks
                            if not isinstance(b, DatasetBlock) or b.table_id != table.table_id
                        ]
                        state.blocks.append(
                            DatasetBlock(
                                dataset_id=dataset.id,
                                name=dataset.name,
                                table_id=table.table_id,
                                canonical_id=canonical.id,
                                rows=c["row_count"],
                                invalid_rows=c["invalid_count"],
                                excluded_rows=c.get("excluded_source_rows", 0),
                                status=c["quality_status"],
                                transformations=[
                                    d["transformation_candidate"]["op"]
                                    for d in mapping.decision["decisions"]
                                ],
                            )
                        )
                elif approved_only:
                    continue
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
            if any(s.tool == "propose_mapping" and s.status == "BLOCKED" for s in state.steps):
                # Một đề xuất lỗi không hủy thẻ đã tạo. Không tự gửi thêm request AI.
                row.state = (
                    "WAITING_REVIEW" if any(r.state == "OPEN" for r in state.reviews) else "PARTIAL"
                )
                save(row, state)
                return
            if len(state.steps) >= step_limit(state):
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
                    profile_only=state.prepare_upload,
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
        elif sequence:
            # The planner still requires explicit scope and invalid-row confirmations.
            advance_sequence(db, row, state, context, catalogue)
            return
        else:
            row.state = (
                "PARTIAL"
                if any(isinstance(b, DatasetBlock) and b.status != "READY" for b in state.blocks)
                else "COMPLETED"
                if catalogue.datasets
                and all(d.tables for d in catalogue.datasets)
                and (
                    not (state.prepare_upload or approved_only)
                    or all(t.canonical_id for d in catalogue.datasets for t in d.tables)
                )
                else "PARTIAL"
                if state.blocks and (unread or state.prepare_upload or approved_only)
                else "WAITING_REVIEW"
            )
        if approved_only and row.state == "COMPLETED":
            state.error_code = None
    elif intent.intent == "RECONCILE_DATASETS":
        require_editor(actor, db, row.id)
        existing_run = next(
            (
                s.result_id
                for s in stage_steps
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
        elif any(r.kind == "RECONCILIATION" for r in stage_reviews):
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

            partial_source = any(
                table.canonical_id in {p.left.canonical_id, p.right.canonical_id}
                and table.canonical_status == "PARTIAL"
                for dataset in catalogue.datasets
                for table in dataset.tables
            )
            matches = []
            for candidate in approved:
                old = ReconciliationContract.model_validate(candidate.definition)
                data = old.plan.model_dump(mode="json")
                if partial_source or missing_confirmations(p):
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
                f"{row.id}:pair:{sequence.pair_index}" if sequence else row.id,
                model_choice=state.model_choice,
            )
            assert isinstance(ref, JobReference)
            intent.planning_request = p
            wait_for(db, row, state, "prepare_reconciliation_plan", p.left.canonical_id, ref)
    elif intent.intent in {"QUERY_DATA", "CREATE_VISUALIZATION"}:
        if intent.query is None:
            raise DomainError("INPUT_AMBIGUOUS", "Cần chọn nguồn và điều kiện truy vấn rõ ràng.")
        from studio.data_query import resolve_verified_metric

        metrics = catalogue.confirmed_plan.comparison_metrics if catalogue.confirmed_plan else []
        try:
            intent.query = resolve_verified_metric(intent.query, metrics, catalogue.previous_query)
        except DomainError as exc:
            if exc.code != "QUERY_METRIC_AMBIGUOUS":
                raise
            make_review(
                db,
                row,
                state,
                kind="CLARIFICATION",
                resource_id=row.id,
                question=exc.message_vi,
                reason="Có nhiều chỉ tiêu đã được duyệt cho kết quả này.",
            )
            review = state.reviews[-1]
            fields = {
                f.id: f.name
                for d in catalogue.datasets
                for t in d.tables
                if t.schema_definition
                for f in t.schema_definition.fields
            }
            review.options = [
                ClarificationOption(
                    id=m.metric_id,
                    label=f"{fields.get(m.left, m.metric_id)} · {m.amount_basis} · {m.currency}",
                    intent=intent.model_copy(
                        update={"query": intent.query.model_copy(update={"metric_id": m.metric_id})}
                    ),
                )
                for m in metrics
            ]
            save(row, state)
            return
        result = execute_tool(
            db, actor, QueryAction(name="query_dataset", query=intent.query), row.id
        )
        assert isinstance(result, QueryResult)
        intent.query = result.query
        # A new table is a new selection surface; a previously explained group
        # must not silently remain selected for a later pronoun/evidence request.
        context.group_id = context.case_id = None
        if result.query.source_kind in {"VERIFIED_RUN", "EXCEPTIONS"}:
            context.run_id = result.query.source_id
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
        if context.run_id is None:
            make_review(
                db,
                row,
                state,
                kind="CLARIFICATION",
                resource_id=row.id,
                question=(
                    "Bạn muốn xem kết quả đối soát nào? Hãy chọn một kết quả đã xác min"
                    "h trong ngữ cảnh. Nếu chưa đối soát, hãy kiểm tra chuẩn hóa nguồn "
                    "trước."
                ),
                reason="Chưa có kết quả đối soát được chọn; không thể đưa ra kết luận tài chính.",
            )
            save(row, state)
            return
        if intent.intent == "SUMMARIZE_RESULTS":
            context.group_id = context.case_id = None
        if intent.result_position is not None:
            if intent.result_position > len(catalogue.previous_groups):
                raise DomainError(
                    "INPUT_AMBIGUOUS", "Không có giao dịch ở vị trí này trong bảng đang xem."
                )
            context.group_id = catalogue.previous_groups[intent.result_position - 1]
            context.case_id = None
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
        discrepancies_only = (
            sequence is not None
            and context.run_id is not None
            and get_scoped(db, RunRow, context.run_id, actor).status == "VERIFIED"
        )
        exported = next(
            (
                s.result_id
                for s in stage_steps
                if s.tool == "start_export" and s.status == "SUCCEEDED"
            ),
            None,
        )
        if exported:
            assert context.run_id
            state.blocks.append(
                DownloadBlock(
                    export_id=exported,
                    run_id=context.run_id,
                    format=intent.export_format,
                    displayed_query=state.export_query is not None,
                    discrepancies_only=discrepancies_only,
                )
            )
            row.state = "COMPLETED"
        else:
            ref = execute_tool(
                db,
                actor,
                ExportAction(
                    name="start_export",
                    context=context,
                    format=intent.export_format,
                    displayed_query=state.export_query,
                    discrepancies_only=discrepancies_only,
                ),
                row.id,
            )
            assert isinstance(ref, JobReference)
            wait_for(db, row, state, "start_export", context.run_id or "", ref)
    elif intent.intent == "EXPLORE_DATA":
        tools_used = add_source_previews()
        if tools_used < sum(len(dataset.tables) for dataset in catalogue.datasets):
            row.state = "PARTIAL"
            state.blocks.append(
                ProgressBlock(text="Đã đạt giới hạn trang xem; chọn nguồn để xem tiếp.")
            )
        else:
            row.state = "COMPLETED" if tools_used else "WAITING_REVIEW"
    else:
        if intent.intent == "UNSUPPORTED":
            for question in intent.questions or ["Yêu cầu này chưa được hỗ trợ."]:
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
    if sequence and row.state == "COMPLETED":
        advance_sequence(db, row, state, context, catalogue)
        return
    row.context = context.model_dump(mode="json")
    save(row, state)
