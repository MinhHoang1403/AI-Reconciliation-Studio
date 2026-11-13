"""Bảy tools chỉ đọc: kiểm quyền/context trước query và giới hạn dữ liệu tại backend."""

import hashlib
import json
import re
import unicodedata
from threading import Timer
from typing import Any

import duckdb
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from studio.access import Actor
from studio.contracts.agent import IntentCatalogue
from studio.contracts.assistant import (
    AnswerFactSet,
    AssistantContext,
    DatasetItem,
    FactReference,
    ToolRequest,
    ToolResult,
    VerifiedFact,
    WorkflowStatus,
)
from studio.contracts.reconciliation import (
    ExceptionCase,
    MatchGroup,
    ReconciliationContract,
    VerifiedRun,
)
from studio.database import DatasetRow, ExceptionRow, ProjectRow, ReconciliationContractRow, RunRow
from studio.errors import DomainError
from studio.reconciliation_repository import _connection, result_path, run_contract
from studio.repository import get_scoped
from studio.resource_lifecycle import active_source


def scoped_context(db: Session, actor: Actor, context: AssistantContext) -> RunRow | None:
    """Không phân biệt missing/foreign resource; group/case luôn thuộc đúng explicit run."""
    get_scoped(db, ProjectRow, context.project_id, actor)
    run = None
    if context.dataset_id:
        dataset = get_scoped(db, DatasetRow, context.dataset_id, actor)
        if dataset.project_id != context.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy tài nguyên trong context.", 404)
    if context.run_id:
        run = get_scoped(db, RunRow, context.run_id, actor)
        if run.project_id != context.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy tài nguyên trong context.", 404)
    if context.case_id:
        case = get_scoped(db, ExceptionRow, context.case_id, actor)
        if (
            case.project_id != context.project_id
            or case.run_id != context.run_id
            or (context.group_id and case.match_group_id != context.group_id)
        ):
            raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy tài nguyên trong context.", 404)
    if context.group_id and run:
        if run.status not in {"VERIFIED", "PARTIAL_VERIFIED"}:
            raise DomainError("INSUFFICIENT_EVIDENCE", "Run chưa có evidence đã xác minh.", 409)
        exact_group(run, context.group_id)
    return run


def select_project_datasets(
    db: Session,
    actor: Actor,
    project_id: str,
    dataset_ids: list[str],
    dataset_names: tuple[str, ...] | None = None,
    *,
    dataset_stem: str | None = None,
    dataset_label: str | None = None,
) -> list[DatasetRow]:
    """Đọc nguồn hiện hành theo phạm vi đã xác thực, kể cả tệp chưa đọc."""
    query = select(DatasetRow).where(
        DatasetRow.workspace_id == actor.workspace_id,
        DatasetRow.project_id == project_id,
        active_source(),
    )
    if dataset_ids:
        query = query.where(DatasetRow.id.in_(dataset_ids))
    elif dataset_names or dataset_stem or dataset_label:
        from studio.assistant import plain_question

        names = {unicodedata.normalize("NFC", name).casefold() for name in dataset_names or ()}
        label_text = (dataset_label or "").strip(' "“”')
        filename_label = label_text if re.search(r"\.(?:csv|xlsx)$", label_text) else None
        identities: list[str] = []
        exact: list[str] = []
        label = " ".join(re.findall(r"[a-z0-9]+", label_text))
        lookup = query.with_only_columns(DatasetRow.id, DatasetRow.name)
        with db.execute(lookup.execution_options(yield_per=128)) as result:
            for dataset_id, name in result:
                folded = plain_question(name)
                if filename_label:
                    if folded == filename_label and len(exact) < 6:
                        exact.append(dataset_id)
                    continue
                if label:
                    words = " ".join(re.findall(r"[a-z0-9]+", folded))
                    if words == label and len(exact) < 6:
                        exact.append(dataset_id)
                    if len(identities) < 6 and f" {label} " in f" {words} ":
                        identities.append(dataset_id)
                    continue
                if unicodedata.normalize("NFC", name).casefold() in names or (
                    dataset_stem and folded.rsplit(".", 1)[0] == dataset_stem
                ):
                    identities.append(dataset_id)
                    if len(identities) == 6:
                        break
        query = query.where(DatasetRow.id.in_(exact or identities))
    datasets = list(db.scalars(query.order_by(DatasetRow.created_at, DatasetRow.id).limit(6)))
    if len(datasets) > 5:
        raise DomainError("INPUT_AMBIGUOUS", "Phạm vi có hơn năm nguồn. Hãy chọn tối đa năm tệp.")
    if dataset_ids and {d.id for d in datasets} != set(dataset_ids):
        raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy nguồn trong dự án này.", 404)
    return datasets


def agent_catalogue(
    db: Session,
    actor: Actor,
    context: AssistantContext,
    dataset_ids: list[str],
    *,
    workflow_id: str | None = None,
    dataset_names: tuple[str, ...] | None = None,
    project_sources: bool = False,
) -> "IntentCatalogue":
    """Catalogue bounded cho router; chỉ metadata/profile, không raw values/paths/secrets."""
    from studio.contracts import EnumTransform, MappingRevision, SchemaDefinition
    from studio.contracts.agent import (
        DatasetContext,
        SourceColumn,
        TableBlock,
        TableContext,
        WorkflowState,
    )
    from studio.data_query import STATUS_VALUES
    from studio.database import (
        AgentWorkflowRow,
        ArtifactRow,
        CanonicalRow,
        MappingRow,
        SchemaRow,
        TableRow,
        VersionRow,
    )

    scoped_context(db, actor, context)
    selected_names = dataset_names if not dataset_ids else None
    if not project_sources and not dataset_ids and not selected_names and context.dataset_id:
        dataset_ids = [context.dataset_id]
    if not project_sources and not dataset_ids and not selected_names and context.run_id:
        run = get_scoped(db, RunRow, context.run_id, actor)
        rule = get_scoped(db, ReconciliationContractRow, run.contract_id, actor)
        plan = ReconciliationContract.model_validate(rule.definition).plan
        dataset_ids = list(
            db.scalars(
                select(VersionRow.dataset_id)
                .join(TableRow, TableRow.dataset_version_id == VersionRow.id)
                .join(CanonicalRow, CanonicalRow.source_table_id == TableRow.id)
                .where(CanonicalRow.id.in_([plan.left.canonical_id, plan.right.canonical_id]))
                .distinct()
            )
        )
    datasets = select_project_datasets(db, actor, context.project_id, dataset_ids, selected_names)
    sources = []
    from studio.normalization import NORMALIZATION_REVISION

    for dataset in datasets:
        tables = list(
            db.scalars(
                select(TableRow)
                .where(
                    TableRow.workspace_id == actor.workspace_id,
                    TableRow.dataset_version_id
                    == (
                        select(VersionRow.id)
                        .where(VersionRow.dataset_id == dataset.id)
                        .order_by(VersionRow.revision.desc())
                        .limit(1)
                        .scalar_subquery()
                    ),
                )
                .order_by(TableRow.id)
                .limit(6)
            )
        )
        if len(tables) > 5:
            raise DomainError("INPUT_AMBIGUOUS", "Nguồn có nhiều bảng; chọn bảng cần xử lý.")
        items = []
        for table in tables:
            artifact = db.get(ArtifactRow, table.artifact_id)
            prepared = (artifact.metadata_json.get("prepared") or {}) if artifact else {}
            if len(table.profile["columns"]) > 40 and not prepared.get("automatic"):
                raise DomainError("AGENT_CONTEXT_LIMIT", "Bảng vượt giới hạn 40 cột của tác vụ AI.")
            canonical = (
                db.scalar(
                    select(CanonicalRow).where(
                        CanonicalRow.source_table_id == table.id,
                        CanonicalRow.workspace_id == actor.workspace_id,
                        CanonicalRow.mapping_id == table.active_mapping_id,
                        CanonicalRow.quality_revision == table.quality_revision,
                        CanonicalRow.normalization_revision == NORMALIZATION_REVISION,
                        CanonicalRow.stale.is_(False),
                    )
                )
                if table.active_mapping_id
                else None
            )
            definition = None
            approved_status_values: dict[str, list[str]] = {}
            if canonical:
                schema = get_scoped(db, SchemaRow, canonical.contract["schema_id"], actor)
                definition = SchemaDefinition.model_validate(schema.definition)
                mapping = get_scoped(db, MappingRow, canonical.mapping_id, actor)
                if mapping.decision:
                    revision = MappingRevision.model_validate(mapping.decision)
                    fields = {f.id for f in definition.fields if f.data_type == "enum"}
                    enums = {r.id: sorted(set(r.enum_values.values())) for r in revision.rules}
                    approved_status_values = {
                        d.candidate_target: enums[d.transformation_candidate.mapping_id]
                        for d in revision.decisions
                        if d.candidate_target
                        and d.candidate_target in fields
                        and isinstance(d.transformation_candidate, EnumTransform)
                        and d.transformation_candidate.mapping_id in enums
                    }
            parsed = get_scoped(db, ArtifactRow, table.artifact_id, actor)
            prepared = parsed.metadata_json.get("prepared") or {}
            items.append(
                TableContext(
                    table_id=table.id,
                    sheet=table.sheet,
                    row_count=table.row_count,
                    column_count=len(table.profile["columns"]),
                    prepared_artifact_id=prepared.get("prepared_artifact_id"),
                    automatic_preparation=bool(prepared.get("automatic")),
                    columns=[
                        SourceColumn(
                            id=c["column_id"],
                            name=c["name"],
                            type_candidates=c["type_candidates"],
                            null_count=c["null_count"],
                            distinct_count=c["distinct_count"],
                        )
                        for c in table.profile["columns"][:40]
                    ],
                    canonical_id=canonical.id if canonical else None,
                    canonical_status=canonical.contract["quality_status"] if canonical else None,
                    schema_definition=definition,
                    mapping_id=table.active_mapping_id,
                    approved_status_values=approved_status_values,
                    paid_status_fields=[
                        f.id for f in definition.fields if f.semantic_metric == "payment_status"
                    ]
                    if definition
                    else [],
                )
            )
        sources.append(
            DatasetContext(id=dataset.id, name=dataset.name, status=dataset.status, tables=items)
        )
    runs = [context.run_id] if context.run_id else []
    verified_pairs: dict[str, tuple[str, str]] = {}
    names = {t.canonical_id: d.name for d in sources for t in d.tables if t.canonical_id}
    if names:
        for saved_run in db.scalars(
            select(RunRow)
            .where(
                RunRow.project_id == context.project_id,
                RunRow.workspace_id == actor.workspace_id,
                RunRow.status.in_(("VERIFIED", "PARTIAL_VERIFIED")),
            )
            .order_by(RunRow.created_at.desc(), RunRow.id.desc())
            .limit(20)
        ):
            refs = [str(source.get("id", "")) for source in saved_run.source_refs]
            if len(refs) == 2 and all(ref in names for ref in refs):
                verified_pairs[saved_run.id] = (names[refs[0]], names[refs[1]])
    confirmed = None
    if context.run_id:
        run = get_scoped(db, RunRow, context.run_id, actor)
        rule = get_scoped(db, ReconciliationContractRow, run.contract_id, actor)
        confirmed = ReconciliationContract.model_validate(rule.definition).plan
    previous_query = None
    previous_source_queries = []
    earlier_source_total = None
    previous_source_year = None
    previous_goal = None
    previous_groups: list[str] = []
    if workflow_id:
        current = get_scoped(db, AgentWorkflowRow, workflow_id, actor)
        if current.actor_id != actor.id or current.project_id != context.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy ngữ cảnh hội thoại.", 404)
        history = db.scalars(
            select(AgentWorkflowRow)
            .where(
                AgentWorkflowRow.conversation_id == current.conversation_id,
                AgentWorkflowRow.actor_id == actor.id,
                AgentWorkflowRow.id != current.id,
                AgentWorkflowRow.created_at <= current.created_at,
            )
            .order_by(AgentWorkflowRow.updated_at.desc(), AgentWorkflowRow.id.desc())
            .limit(10)
        )
        valid_sources = {t.table_id for d in sources for t in d.tables} | {
            t.canonical_id for d in sources for t in d.tables if t.canonical_id
        }
        for old in history:
            state = WorkflowState.model_validate(old.detail)
            result_table = next(
                (b for b in reversed(state.blocks) if isinstance(b, TableBlock)), None
            )
            if not result_table:
                if state.intent and state.intent.intent in {"CLARIFY", "UNSUPPORTED"}:
                    break
                continue
            q = state.query_selection.query if state.query_selection else result_table.result.query
            if (
                q.source_kind == "CANONICAL"
                and (q.source_measure_id or any(a.op == "sum_decimal" for a in q.aggregations))
                and (
                    not result_table.result.source_evidence
                    or result_table.result.source_evidence.valid_rows is None
                )
            ):
                # Historical monetary queries may have dropped a user constraint.
                break
            if q.project_id != context.project_id or (
                q.source_id != context.run_id
                if q.source_kind in {"VERIFIED_RUN", "EXCEPTIONS"}
                else q.source_id not in valid_sources
            ):
                # A newer, different scope must never resurrect an earlier query.
                break
            source_results = [
                b.result
                for b in state.blocks
                if isinstance(b, TableBlock)
                and b.result.query.source_kind == "CANONICAL"
                and b.result.query.source_id in valid_sources
                and b.result.source_evidence
            ]
            if previous_query:
                if (
                    len(source_results) == 1
                    and q.source_id != previous_query.source_id
                    and any(a.op == "sum_decimal" for a in q.aggregations)
                ):
                    earlier_source_total = q
                break
            previous_query, previous_goal = q, old.goal
            previous_source_queries = [result.query for result in source_results]
            years = {
                int(day[:4])
                for result in source_results
                if (evidence := result.source_evidence)
                for day in (evidence.observed_first, evidence.observed_last)
                if day
            }
            previous_source_year = next(iter(years)) if len(years) == 1 else None
            if q.source_kind == "VERIFIED_RUN":
                previous_groups = (
                    state.query_selection.group_ids
                    if state.query_selection
                    else [str(r["group_id"]) for r in result_table.result.rows if r.get("group_id")]
                )
            if len(source_results) != 1 or not any(a.op == "sum_decimal" for a in q.aggregations):
                break
    return IntentCatalogue(
        context=context,
        project_scope=get_scoped(db, ProjectRow, context.project_id, actor).business_scope,
        datasets=sources,
        run_ids=runs,
        confirmed_plan=confirmed,
        previous_query=previous_query,
        previous_source_queries=previous_source_queries,
        earlier_source_total=earlier_source_total,
        previous_source_year=previous_source_year,
        previous_goal=previous_goal,
        previous_groups=previous_groups,
        verified_run_fields=(
            [
                "group_id",
                "linkage_state",
                "comparison_state",
                "left_member_count",
                "right_member_count",
                "metric_id",
                "currency",
                "unit",
                "left_amount",
                "right_amount",
                "delta",
                "absolute_variance",
                "tolerance",
            ]
            if confirmed
            else []
        ),
        verified_metric_ids=[m.metric_id for m in confirmed.comparison_metrics]
        if confirmed
        else [],
        verified_pairs=verified_pairs,
        status_values=STATUS_VALUES if confirmed else {},
    )


def exact_group(run: RunRow, group_id: str) -> MatchGroup:
    """ID tham số hóa, checksum bắt buộc, không nhận SQL/path do người dùng/model sinh."""
    with _connection() as connection:
        path = result_path(run)
        timer = Timer(3, connection.interrupt)
        timer.daemon = True
        timer.start()
        try:
            found = connection.execute(
                "SELECT group_json FROM read_parquet(?) WHERE group_id = ? LIMIT 1",
                [str(path), group_id],
            ).fetchone()
        except duckdb.Error as exc:
            raise DomainError(
                "TOOL_UNAVAILABLE", "Không truy xuất được evidence trong giới hạn.", 503
            ) from exc
        finally:
            timer.cancel()
    if found is None:
        raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy group trong context.", 404)
    group = MatchGroup.model_validate_json(found[0])
    if group.id != group_id:
        raise DomainError("EVIDENCE_SCOPE_INVALID", "Nguồn không khớp group.")
    if len(group.members) > 100 or sum(len(m.evidence) for m in group.members) > 100:
        raise DomainError(
            "EVIDENCE_LIMIT", "Nhóm quá lớn; mở bằng chứng hoặc báo cáo đầy đủ để kiểm tra.", 409
        )
    return group


def group_for_key(db: Session, actor: Actor, context: AssistantContext, key_value: str) -> str:
    """Exact string lookup trong key của run đã verified; không đoán nguồn hoặc fuzzy ID."""
    row = scoped_context(db, actor, context)
    if (
        row is None
        or row.status not in {"VERIFIED", "PARTIAL_VERIFIED"}
        or row.metric_snapshot is None
    ):
        raise DomainError("INSUFFICIENT_EVIDENCE", "Chọn đúng kết quả đã xác minh để tìm mã.", 409)
    if not key_value or len(key_value) > 200:
        raise DomainError("INPUT_AMBIGUOUS", "Mã cần tìm không hợp lệ.")
    with _connection() as connection:
        path = result_path(row)
        timer = Timer(3, connection.interrupt)
        timer.daemon = True
        timer.start()
        try:
            matches = connection.execute(
                "SELECT group_id FROM read_parquet(?) "
                "WHERE list_contains(json_extract_string(group_json, '$.key[*]'), ?) LIMIT 2",
                [str(path), key_value],
            ).fetchall()
        except duckdb.Error as exc:
            raise DomainError("TOOL_UNAVAILABLE", "Không tìm được mã trong giới hạn.", 503) from exc
        finally:
            timer.cancel()
    if not matches:
        raise DomainError("INSUFFICIENT_EVIDENCE", "Không có mã chính xác trong run đã chọn.", 409)
    if len(matches) != 1:
        raise DomainError("INPUT_AMBIGUOUS", "Mã trùng ở nhiều nhóm; cần thêm khóa phân biệt.")
    return str(matches[0][0])


def read_tool(db: Session, actor: Actor, request: ToolRequest) -> ToolResult:
    """F28: output DTO allowlist; không gọi provider và không ghi database."""
    context = request.context
    db.execute(text("SET LOCAL statement_timeout = '2500ms'"))
    row = scoped_context(db, actor, context)
    result = ToolResult(
        name=request.name,
        workspace_id=actor.workspace_id,
        project_id=context.project_id,
        run_id=context.run_id,
    )
    if request.name == "list_datasets":
        query = select(DatasetRow).where(
            DatasetRow.workspace_id == actor.workspace_id,
            DatasetRow.project_id == context.project_id,
            active_source(),
        )
        result.total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        result.datasets = [
            DatasetItem(id=r.id, name=r.name[:255], status=r.status)
            for r in db.scalars(
                query.order_by(DatasetRow.created_at.desc(), DatasetRow.id)
                .offset(request.offset)
                .limit(request.limit)
            )
        ]
        result.truncated = result.total > request.offset + len(result.datasets)
        return result
    if request.name == "get_workflow_status":
        from studio.database import CanonicalRow, TableRow, VersionRow

        tables = (
            select(TableRow.id)
            .join(VersionRow, TableRow.dataset_version_id == VersionRow.id)
            .join(DatasetRow, VersionRow.dataset_id == DatasetRow.id)
            .where(DatasetRow.project_id == context.project_id, active_source())
        )
        ready = (
            db.scalar(
                select(func.count())
                .select_from(CanonicalRow)
                .where(
                    CanonicalRow.workspace_id == actor.workspace_id,
                    CanonicalRow.source_table_id.in_(tables),
                    CanonicalRow.stale.is_(False),
                    CanonicalRow.contract["quality_status"].astext == "READY",
                )
            )
            or 0
        )
        reviews = (
            db.scalar(
                select(func.count())
                .select_from(TableRow)
                .where(TableRow.id.in_(tables), TableRow.active_mapping_id.is_(None))
            )
            or 0
        )
        rules = list(
            db.scalars(
                select(ReconciliationContractRow.id)
                .where(
                    ReconciliationContractRow.workspace_id == actor.workspace_id,
                    ReconciliationContractRow.project_id == context.project_id,
                )
                .order_by(ReconciliationContractRow.created_at.desc(), ReconciliationContractRow.id)
                .limit(20)
            )
        )
        from studio.database import JobRow

        active = (
            db.scalar(
                select(func.count())
                .select_from(JobRow)
                .where(
                    JobRow.workspace_id == actor.workspace_id,
                    JobRow.project_id == context.project_id,
                    JobRow.status.in_(["QUEUED", "RUNNING", "RETRYABLE_FAILURE"]),
                )
            )
            or 0
        )
        result.workflow = WorkflowStatus(
            dataset_count=db.scalar(
                select(func.count())
                .select_from(DatasetRow)
                .where(DatasetRow.project_id == context.project_id, active_source())
            )
            or 0,
            ready_canonical_count=ready,
            mapping_review_count=reviews,
            active_job_count=active,
            approved_rule_ids=rules,
            questions=["Xác nhận nguồn, kỳ có năm, timezone và coverage trước khi tạo kế hoạch."],
        )
        return result
    if row is None or row.status not in {"VERIFIED", "PARTIAL_VERIFIED"} or not row.metric_snapshot:
        raise DomainError("INSUFFICIENT_EVIDENCE", "Chọn run đã xác minh để tra cứu facts.", 409)
    verified = VerifiedRun.model_validate(run_contract(row).model_dump())
    if request.name == "get_run_summary":
        result.run = verified
    elif request.name == "get_metric_breakdown":
        allowed = {
            "full_match_rate",
            "linkage_rate",
            "exception_rate",
            "automation_coverage",
            "review_rate",
            *(m.metric_id for m in verified.metric_snapshot.monetary),
        }
        if request.metric_id and request.metric_id not in allowed:
            raise DomainError(
                "INSUFFICIENT_EVIDENCE", "Metric không có trong snapshot của run.", 409
            )
        result.snapshot = verified.metric_snapshot
    elif request.name == "list_exceptions":
        cases_query = select(ExceptionRow).where(
            ExceptionRow.workspace_id == actor.workspace_id,
            ExceptionRow.project_id == context.project_id,
            ExceptionRow.run_id == row.id,
        )
        result.total = db.scalar(select(func.count()).select_from(cases_query.subquery())) or 0
        result.exceptions = [
            ExceptionCase.model_validate(
                r.definition
                | dict(
                    workflow_state=r.workflow_state,
                    notes=r.notes[:500],
                    reviewed_by=r.reviewed_by,
                    reviewed_at=r.reviewed_at,
                )
            )
            for r in db.scalars(
                cases_query.order_by(ExceptionRow.id).offset(request.offset).limit(request.limit)
            )
        ]
        result.truncated = result.total > request.offset + len(result.exceptions)
    elif request.name == "get_match_evidence":
        group_id = context.group_id
        if context.case_id:
            group_id = get_scoped(db, ExceptionRow, context.case_id, actor).match_group_id
        if not group_id:
            raise DomainError("INSUFFICIENT_EVIDENCE", "Chọn group hoặc ngoại lệ cụ thể.", 409)
        result.group = exact_group(row, group_id)
    elif request.name == "get_rule":
        rule = get_scoped(db, ReconciliationContractRow, row.contract_id, actor)
        if rule.project_id != context.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy rule trong context.", 404)
        result.rule = ReconciliationContract.model_validate(rule.definition)
    return result


def build_fact_set(db: Session, actor: Actor, context: AssistantContext) -> AnswerFactSet:
    """Facts chỉ copy từ VerifiedRun/MetricSnapshot/comparison, không tính lại KPI/tiền."""
    row = scoped_context(db, actor, context)
    values: dict[str, Any] = dict(
        workspace_id=actor.workspace_id,
        business_scope=get_scoped(db, ProjectRow, context.project_id, actor).business_scope,
        context=context,
        verification_status="INSUFFICIENT_EVIDENCE",
        facts=[],
        references=[],
    )
    if row and row.status in {"VERIFIED", "PARTIAL_VERIFIED"} and row.metric_snapshot:
        summary = read_tool(db, actor, ToolRequest(name="get_run_summary", context=context)).run
        assert summary is not None
        snapshot = summary.metric_snapshot
        rule = read_tool(db, actor, ToolRequest(name="get_rule", context=context)).rule
        assert rule is not None
        if (
            snapshot.run_id != row.id
            or snapshot.rule_id != rule.id
            or snapshot.rule_revision != rule.revision
        ):
            raise DomainError("EVIDENCE_SCOPE_INVALID", "Snapshot không khớp run/rule revision.")
        base_ref = FactReference(id=snapshot.id, run_id=row.id, snapshot_id=snapshot.id)
        refs = [base_ref]
        facts = [
            VerifiedFact(
                id="run_status",
                label="Trạng thái run",
                value=row.status,
                reference_ids=[base_ref.id],
            )
        ]
        for metric in (
            "full_match_rate",
            "linkage_rate",
            "exception_rate",
            "automation_coverage",
            "review_rate",
        ):
            rate = getattr(snapshot, metric)
            facts.append(
                VerifiedFact(
                    id=metric,
                    label={
                        "full_match_rate": "Tỷ lệ khớp đã xác minh",
                        "linkage_rate": "Tỷ lệ liên kết",
                        "exception_rate": "Tỷ lệ ngoại lệ",
                        "automation_coverage": "Mức tự động hóa",
                        "review_rate": "Tỷ lệ cần review",
                    }[metric],
                    value=(
                        f"{rate.percent if rate.percent is not None else 'N/A'} "
                        f"({rate.numerator}/{rate.denominator})"
                    ),
                    reference_ids=[base_ref.id],
                    metric_id=metric,
                )
            )
        for i, money in enumerate(snapshot.monetary):
            facts.append(
                VerifiedFact(
                    id=f"variance_{i}",
                    label="Lệch tuyệt đối / lệch có dấu",
                    value=f"{money.absolute_variance} / {money.signed_variance} {money.currency}",
                    reference_ids=[base_ref.id],
                    metric_id=money.metric_id,
                    currency=money.currency,
                )
            )
        if context.group_id or context.case_id:
            group = read_tool(
                db, actor, ToolRequest(name="get_match_evidence", context=context)
            ).group
            assert group is not None
            group_ref = FactReference(
                id=group.id, run_id=row.id, snapshot_id=snapshot.id, group_id=group.id
            )
            refs.append(group_ref)
            for member in group.members:
                for source in member.evidence:
                    refs.append(
                        FactReference(
                            id=f"{group.id}:{source.source_row_id}:{source.row}",
                            run_id=row.id,
                            snapshot_id=snapshot.id,
                            group_id=group.id,
                            member_id=member.record_id,
                            file_id=source.file_id,
                            source_table_id=source.source_table_id,
                            sheet=source.sheet,
                            row=source.row,
                        )
                    )
            evidence_ids = list(dict.fromkeys(r.id for r in refs[1:]))
            facts.append(
                VerifiedFact(
                    id="comparison",
                    label="Kết luận so sánh",
                    value=f"{group.linkage_state} + {group.comparison_state}",
                    reference_ids=evidence_ids,
                )
            )
            for i, comparison in enumerate(group.comparisons):
                facts.append(
                    VerifiedFact(
                        id=f"comparison_{i}",
                        label="Trái / phải / delta / tolerance",
                        value=(
                            f"{comparison.left_amount} / {comparison.right_amount} / "
                            f"{comparison.delta} / {comparison.tolerance} {comparison.currency}"
                        ),
                        reference_ids=evidence_ids,
                        metric_id=comparison.metric_id,
                        currency=comparison.currency,
                    )
                )
        values.update(
            verification_status=row.status,
            snapshot=snapshot,
            rule_id=rule.id,
            rule_revision=rule.revision,
            facts=facts,
            references=list({r.id: r for r in refs}.values()),
        )
    body = AnswerFactSet(id="pending", **values)
    digest = hashlib.sha256(
        json.dumps(body.model_dump(mode="json", exclude={"id"}), sort_keys=True).encode()
    ).hexdigest()
    return body.model_copy(update={"id": digest})
