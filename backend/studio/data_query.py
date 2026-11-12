"""Compile truy vấn allowlist trên artifact đã kiểm quyền; không nhận SQL hoặc path."""

import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, get_args

import polars as pl
from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.access import Actor
from studio.config import settings
from studio.contracts import CanonicalDataset, SchemaDefinition
from studio.contracts.agent import SourceComparisonBlock, SourceValueChange, TableContext
from studio.contracts.data_query import DataQuery, QueryResult
from studio.contracts.reconciliation import (
    ComparisonMetric,
    ComparisonState,
    LinkageState,
    MatchGroup,
    ReconciliationContract,
)
from studio.contracts.reconciliation import (
    WorkflowState as CaseState,
)
from studio.database import (
    ArtifactRow,
    CanonicalRow,
    ExceptionRow,
    MembershipRow,
    ReconciliationContractRow,
    RunRow,
    SchemaRow,
    TableRow,
)
from studio.errors import DomainError
from studio.reconciliation_repository import result_path
from studio.repository import get_scoped, project_for_table, read_prepared_artifact
from studio.storage import checksum, storage_path


@dataclass
class QuerySource:
    frame: pl.LazyFrame
    fields: list[str]
    evidence: list[str]
    status: str
    money: dict[str, tuple[str, str]]
    quality_status: str | None = None
    labels: dict[str, str] = field(default_factory=dict)


VERIFIED_FIELDS = [
    "group_id",
    "linkage_state",
    "comparison_state",
    "left_member_count",
    "right_member_count",
]
VERIFIED_MONEY_FIELDS = ["left_amount", "right_amount", "delta", "absolute_variance", "tolerance"]
EXCEPTION_FIELDS = ["case_id", "group_id", "type", "state", "notes"]
STATUS_VALUES = {
    "VERIFIED_RUN": {
        "linkage_state": list(get_args(LinkageState)),
        "comparison_state": list(get_args(ComparisonState)),
    },
    "EXCEPTIONS": {"state": list(get_args(CaseState))},
}


def compare_source_row(
    db: Session, actor: Actor, project_id: str, table_context: TableContext, name: str, row: int
) -> SourceComparisonBlock:
    """Compare one physical source row against its current, checksum-checked view."""
    from studio.database import MappingRow
    from studio.repository import mapping_contract

    deadline = time.monotonic() + settings.agent_query_timeout_seconds
    raw_query = DataQuery(
        project_id=project_id, source_kind="RAW_PREVIEW", source_id=table_context.table_id
    )
    raw = _source(db, actor, raw_query, deadline)
    originals = _collect_bounded(
        raw.frame.filter(pl.col("_source_row") == row).head(1), deadline
    ).to_dicts()
    if not originals:
        raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy dòng này trong bảng.", 404)
    old = originals[0]
    values = {}
    target_by_source = {}
    scope: Literal["CANONICAL", "PREPARED", "RAW"] = "RAW"
    if table_context.canonical_id:
        scope = "CANONICAL"
        query = raw_query.model_copy(
            update={"source_kind": scope, "source_id": table_context.canonical_id}
        )
        source = _source(db, actor, query, deadline)
        matches = _collect_bounded(
            source.frame.filter(
                pl.col("source_provenance")
                .list.eval(pl.element().struct.field("source_row_id") == old["_source_row_id"])
                .list.any()
            ).head(1),
            deadline,
        ).to_dicts()
        if matches and len(matches[0]["source_provenance"]) != 1:
            raise DomainError(
                "INSUFFICIENT_EVIDENCE", "Dòng này thuộc một nhóm đã gộp; xem bằng chứng của nhóm."
            )
        values = matches[0] if matches else {}
        if not table_context.mapping_id:
            raise DomainError("INSUFFICIENT_EVIDENCE", "Thiếu quy tắc của bản chuẩn hóa hiện hành.")
        mapping = mapping_contract(get_scoped(db, MappingRow, table_context.mapping_id, actor))
        target_by_source = {d.source_field: d.candidate_target for d in mapping.decisions}
    elif table_context.prepared_artifact_id:
        scope = "PREPARED"
        prepared = _source(db, actor, raw_query.model_copy(update={"source_kind": scope}), deadline)
        items = _collect_bounded(
            prepared.frame.filter(pl.col("_source_row") == row).head(1), deadline
        ).to_dicts()
        values = items[0] if items else {}
        target_by_source = {field: field for field in raw.fields}
    fields = []
    for field_id in raw.fields:
        target = target_by_source.get(field_id)
        before = json_value(old[field_id])
        after = json_value(values.get(target)) if target else None
        errors = values.get("quality_flags", values.get("_preparation_flags", []))
        outcome = (
            "Chưa có phép biến đổi"
            if target is None
            else "Dòng ngoài bản hiện hành"
            if not values
            else "Giá trị cần kiểm tra"
            if any(flag.endswith(f":{target}") and not flag.startswith("NULL:") for flag in errors)
            else "Giữ nguyên"
            if before == after
            else "Đã xử lý theo quy tắc lưu"
        )
        fields.append(
            SourceValueChange(
                field=raw.labels[field_id],
                original=str(before) if before is not None else None,
                processed=str(after) if after is not None else None,
                outcome=outcome,
            )
        )
    fields.sort(key=lambda item: item.outcome == "Giữ nguyên")
    return SourceComparisonBlock(name=name, row=row, scope=scope, fields=fields)


def resolve_verified_metric(
    query: DataQuery, metrics: list[ComparisonMetric], previous: DataQuery | None = None
) -> DataQuery:
    """Bind money only to an approved metric, never to a guessed column name.

    Count/status queries need no money metric. An explicit selection wins; otherwise
    only a unique approved metric or a still-scoped prior selection is admissible.
    Ambiguity and absence have distinct errors; inputs and historical rules stay immutable.
    """
    if query.source_kind != "VERIFIED_RUN":
        return query
    known = {m.metric_id for m in metrics}
    if query.metric_id:
        if query.metric_id not in known:
            raise DomainError("QUERY_SEMANTICS_REQUIRED", "Chỉ tiêu không thuộc quy tắc đã duyệt.")
        return query
    mentioned = {
        *query.select_fields,
        *query.group_by,
        *(f.field_id for f in query.filters),
        *(s.field_id for s in query.sort),
        *(a.field_id for a in query.aggregations if a.field_id),
    }
    if not mentioned.intersection([*VERIFIED_MONEY_FIELDS, "currency", "unit", "metric_id"]):
        return query
    if len(known) == 1:
        selected = next(iter(known))
    elif (
        previous
        and previous.project_id == query.project_id
        and previous.source_kind == query.source_kind
        and previous.source_id == query.source_id
        and previous.metric_id in known
    ):
        selected = previous.metric_id
    elif known:
        raise DomainError("QUERY_METRIC_AMBIGUOUS", "Bạn muốn xem số tiền theo chỉ tiêu nào?")
    else:
        raise DomainError(
            "QUERY_METRIC_UNAVAILABLE", "Kết quả này chưa có chỉ tiêu tiền được duyệt."
        )
    return query.model_copy(update={"metric_id": selected})


def validate_status_predicates(query: DataQuery) -> None:
    """Status dimensions have explicit enums, not invented MATCHED/lexical ranges."""
    for rule in query.filters:
        allowed = STATUS_VALUES.get(query.source_kind, {}).get(rule.field_id)
        if allowed is None:
            continue
        values = rule.value if isinstance(rule.value, list) else [rule.value]
        if rule.op not in {"eq", "ne", "in", "is_null"} or (
            rule.op != "is_null" and any(value not in allowed for value in values)
        ):
            raise DomainError(
                "QUERY_VALUE_INVALID", "Điều kiện không thuộc trạng thái đã định nghĩa."
            )


def _verified_source(
    db: Session, actor: Actor, run: RunRow, query: DataQuery, deadline: float
) -> QuerySource:
    """Read immutable verified members/comparisons, never recompute a match or amount.

    One output row per group. A selected approved metric is mandatory for money;
    missing comparisons remain null. Decode only a bounded artifact with a common
    deadline, infer exact Decimal scale from every value (no sampling/float/rounding).
    """
    rule = get_scoped(db, ReconciliationContractRow, run.contract_id, actor)
    plan = ReconciliationContract.model_validate(rule.definition).plan
    assert run.metric_snapshot is not None
    # Resolve before exposing money fields, so a unique approved metric does not
    # become an unrelated QUERY_FIELD_INVALID later in the compiler.
    query.metric_id = resolve_verified_metric(query, plan.comparison_metrics).metric_id
    metric = next((m for m in plan.comparison_metrics if m.metric_id == query.metric_id), None)
    if query.metric_id and metric is None:
        raise DomainError("QUERY_SEMANTICS_REQUIRED", "Chỉ tiêu không thuộc quy tắc đã duyệt.")
    frame = pl.scan_parquet(result_path(run))
    cap = min(settings.max_rows, 100000)
    encoded = _collect_bounded(frame.select("group_json").limit(cap + 1), deadline)
    if encoded.height > cap:
        raise DomainError("QUERY_ROW_LIMIT", "Run vượt giới hạn truy vấn an toàn.")
    records = []
    for value in encoded.get_column("group_json"):
        if time.monotonic() >= deadline:
            raise DomainError("QUERY_TIMEOUT", "Truy vấn vượt thời gian; chưa trả kết quả.", 409)
        group = MatchGroup.model_validate_json(value)
        row: dict[str, Any] = dict(
            group_id=group.id,
            business_key=" · ".join("—" if value is None else value for value in group.key),
            linkage_state=group.linkage_state,
            comparison_state=group.comparison_state,
            left_member_count=sum(m.side == "left" for m in group.members),
            right_member_count=sum(m.side == "right" for m in group.members),
            source_provenance=[
                {
                    **e.model_dump(),
                    "canonical_id": m.canonical_id,
                    "record_id": m.record_id,
                    "side": m.side,
                }
                for m in group.members
                for e in m.evidence
            ],
        )
        if metric:
            matches = [c for c in group.comparisons if c.metric_id == metric.metric_id]
            if len(matches) > 1 or any(
                c.currency != metric.currency or c.unit != metric.unit for c in matches
            ):
                raise DomainError("QUERY_SEMANTICS_REQUIRED", "Chỉ tiêu kết quả không nhất quán.")
            comparison = matches[0] if matches else None
            row.update(metric_id=metric.metric_id, currency=metric.currency, unit=metric.unit)
            row.update(
                {f: getattr(comparison, f) if comparison else None for f in VERIFIED_MONEY_FIELDS}
            )
        records.append(row)
    schema: dict[str, Any] = {f: pl.String for f in VERIFIED_FIELDS[:3]}
    schema.update(
        business_key=pl.String,
        left_member_count=pl.UInt32,
        right_member_count=pl.UInt32,
        source_provenance=pl.List(
            pl.Struct(
                {
                    "source_table_id": pl.String,
                    "source_row_id": pl.String,
                    "sheet": pl.String,
                    "row": pl.Int64,
                    "canonical_id": pl.String,
                    "record_id": pl.String,
                    "side": pl.String,
                }
            )
        ),
    )
    fields = VERIFIED_FIELDS.copy()
    money = {}
    if metric:
        for field in VERIFIED_MONEY_FIELDS:
            values = [r[field] for r in records if r[field] is not None]
            scale = max((max(0, -v.as_tuple().exponent) for v in values), default=0)
            if scale > 38 or any(v.adjusted() + 1 + scale > 38 for v in values):
                raise DomainError("QUERY_PRECISION_LIMIT", "Không thể giữ chính xác số tiền.")
            schema[field] = pl.Decimal(38, scale)
            money[field] = (metric.currency, metric.unit)
        schema.update(metric_id=pl.String, currency=pl.String, unit=pl.String)
        fields += ["metric_id", "currency", "unit", *VERIFIED_MONEY_FIELDS]
    return QuerySource(
        pl.DataFrame(records, schema=schema).lazy(),
        fields,
        [run.id, run.metric_snapshot["id"]],
        run.status,
        money,
    )


def _source(db: Session, actor: Actor, query: DataQuery, deadline: float) -> QuerySource:
    """Mỗi truy vấn kiểm lại actor/project/artifact/checksum, không tin IDs model chọn."""
    if db.get(MembershipRow, (actor.workspace_id, actor.id)) is None:
        raise DomainError("RESOURCE_NOT_FOUND", "Quyền truy cập không còn hợp lệ.", 404)
    if query.metric_id and query.source_kind != "VERIFIED_RUN":
        raise DomainError("QUERY_SEMANTICS_REQUIRED", "Chỉ chọn metric cho kết quả đã xác minh.")
    if query.source_kind in {
        "RAW_PREVIEW",
        "PREPARED",
        "PREPARED_FINDINGS",
        "PREPARED_ISSUES",
        "CANONICAL",
    }:
        canonical = None
        if query.source_kind == "CANONICAL":
            row = get_scoped(db, CanonicalRow, query.source_id, actor)
            canonical = CanonicalDataset.model_validate(row.contract)
            if row.stale:
                raise DomainError("STALE_CONTEXT", "Dữ liệu chuẩn hóa đã cũ.", 409)
            table = get_scoped(db, TableRow, row.source_table_id, actor)
            if (
                table.active_mapping_id != row.mapping_id
                or table.quality_revision != row.quality_revision
            ):
                raise DomainError("STALE_CONTEXT", "Dữ liệu chuẩn hóa đã cũ.", 409)
            artifact = get_scoped(db, ArtifactRow, canonical.artifact.id, actor)
        else:
            table = get_scoped(db, TableRow, query.source_id, actor)
            artifact = get_scoped(db, ArtifactRow, table.artifact_id, actor)
        if project_for_table(db, table).id != query.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Nguồn không thuộc dự án.", 404)
        parsed_artifact = artifact
        if query.source_kind in {"PREPARED", "PREPARED_FINDINGS", "PREPARED_ISSUES"}:
            artifact = read_prepared_artifact(db, actor, table, artifact)
        path = storage_path(settings.storage_root, artifact.storage_key)
        if checksum(path) != artifact.sha256:
            raise DomainError("ARTIFACT_CHECKSUM_FAILED", "Dữ liệu không khớp checksum.")
        frame = pl.scan_parquet(path)
        money = {}
        labels = {}
        if canonical:
            definition = SchemaDefinition.model_validate(
                get_scoped(db, SchemaRow, canonical.schema_id, actor).definition
            )
            fields = [f.id for f in definition.fields]
            labels = {f.id: f.name for f in definition.fields}
            money = {
                f.id: (f.currency, f.unit)
                for f in definition.fields
                if f.data_type == "decimal" and f.currency and f.unit and f.semantic_metric
            }
            frame = frame.unnest("record_payload")
        else:
            fields = [c["id"] for c in table.parsed_contract["columns"]]
            labels = {c["id"]: c["name"] for c in table.parsed_contract["columns"]}
            if query.source_kind == "PREPARED_FINDINGS":
                flags = pl.col("_preparation_flags").list.filter(
                    pl.element().str.starts_with("INVALID_DATE:")
                )
                names = {f"INVALID_DATE:{field}": label for field, label in labels.items()}
                frame = frame.filter(flags.list.len() > 0).with_columns(
                    flags.list.eval(pl.element().replace_strict(names, default=pl.element()))
                    .list.join(", ")
                    .alias("date_findings")
                )
                fields.insert(0, "date_findings")
                labels["date_findings"] = "Cột có ngày không hợp lệ"
            elif query.source_kind == "PREPARED_ISSUES":
                from studio.data_quality import artifact_scan

                flags = pl.col("_preparation_flags")
                descriptions = {
                    "INVALID_DATE": "Ngày không hợp lệ",
                    "INVALID_DECIMAL": "Số tiền không hợp lệ",
                    "DECIMAL_PRECISION_EXCEEDED": "Số tiền vượt độ chính xác hỗ trợ",
                }
                issue_labels = {
                    f"{code}:{field}": f"{label} · {description}"
                    for field, label in labels.items()
                    for code, description in descriptions.items()
                }
                issues = frame.filter(flags.list.len() > 0).select(
                    "_source_row_id",
                    flags.list.eval(
                        pl.element().replace_strict(issue_labels, default="Giá trị cần kiểm tra")
                    )
                    .list.join(" · ")
                    .alias("source_issue"),
                )
                frame = artifact_scan(parsed_artifact).join(
                    issues, on="_source_row_id", validate="1:1"
                )
                fields.insert(0, "source_issue")
                labels["source_issue"] = "Vấn đề phát hiện"
            frame = frame.with_columns(
                pl.concat_list(
                    pl.struct(
                        pl.lit(table.id).alias("source_table_id"),
                        pl.col("_source_row").alias("row"),
                        pl.col("_source_row_id").alias("source_row_id"),
                        pl.lit(table.sheet).alias("sheet"),
                    )
                ).alias("source_provenance")
            )
        return QuerySource(
            frame,
            fields,
            [artifact.id, table.id],
            "CANONICAL" if canonical else "RAW_UNVERIFIED",
            money,
            canonical.quality_status if canonical else None,
            labels,
        )
    run = get_scoped(db, RunRow, query.source_id, actor)
    if run.project_id != query.project_id:
        raise DomainError("RESOURCE_NOT_FOUND", "Run không thuộc dự án.", 404)
    if run.status not in {"VERIFIED", "PARTIAL_VERIFIED"} or run.metric_snapshot is None:
        raise DomainError("INSUFFICIENT_EVIDENCE", "Run chưa được xác minh.", 409)
    if query.source_kind == "VERIFIED_RUN":
        return _verified_source(db, actor, run, query, deadline)
    else:
        cases = list(
            db.scalars(
                select(ExceptionRow)
                .where(
                    ExceptionRow.workspace_id == actor.workspace_id,
                    ExceptionRow.run_id == run.id,
                    ExceptionRow.project_id == query.project_id,
                )
                .order_by(ExceptionRow.id)
                .limit(min(settings.max_rows, 100000) + 1)
            )
        )
        frame = pl.DataFrame(
            [
                dict(
                    case_id=c.id,
                    group_id=c.match_group_id,
                    type=c.type,
                    state=c.workflow_state,
                    notes=c.notes,
                )
                for c in cases
            ],
            schema={k: pl.String for k in EXCEPTION_FIELDS},
        ).lazy()
        fields = EXCEPTION_FIELDS.copy()
    return QuerySource(frame, fields, [run.id, run.metric_snapshot["id"]], run.status, {})


def _value(value: str, dtype: pl.DataType) -> str | Decimal | date | int | bool:
    if len(value) > 200:
        raise DomainError("QUERY_VALUE_LIMIT", "Giá trị lọc quá dài.")
    try:
        if dtype.is_decimal():
            result = Decimal(value)
            if not result.is_finite() or len(result.as_tuple().digits) > 38:
                raise ValueError("precision")
            return result
        if dtype.is_integer():
            return int(value)
        if dtype == pl.Boolean:
            if value not in {"true", "false"}:
                raise ValueError("boolean")
            return value == "true"
        if dtype == pl.Date:
            return date.fromisoformat(value)
        if isinstance(dtype, pl.Datetime):
            result_date = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if result_date.utcoffset() is None:
                raise ValueError("timezone required")
            return result_date
        if dtype != pl.String:
            raise ValueError("unsupported type")
        return value
    except (ValueError, InvalidOperation) as exc:
        raise DomainError("QUERY_VALUE_INVALID", "Giá trị không phù hợp kiểu của cột.") from exc


def json_value(value: Any) -> JsonValue:
    """Tiền giữ chuỗi Decimal, ngày giữ timezone; không downcast float."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, list):
        return [json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if value is None or isinstance(value, str | int | bool):
        return value
    raise DomainError("QUERY_TYPE_UNSUPPORTED", "Kết quả có kiểu chưa được hỗ trợ an toàn.")


def _collect_bounded(frame: pl.LazyFrame, deadline: float) -> pl.DataFrame:
    """Native cancellable query trên Polars đã pin; deadline chung cho mọi collect/query.

    cancel là cooperative của engine, không phải kill thread/process. Row/column/operation
    caps vẫn bắt buộc; không dùng deadline thay giới hạn bộ nhớ/đầu vào.
    """
    if time.monotonic() >= deadline:
        raise DomainError("QUERY_TIMEOUT", "Truy vấn vượt thời gian; chưa trả kết quả đầy đủ.", 409)
    query = frame.collect(background=True, engine="in-memory")
    try:
        while time.monotonic() < deadline:
            result = query.fetch()
            if result is not None:
                return result
            time.sleep(0.01)
        raise DomainError("QUERY_TIMEOUT", "Truy vấn vượt thời gian; chưa trả kết quả đầy đủ.", 409)
    finally:
        query.cancel()


def execute_query(db: Session, actor: Actor, query: DataQuery) -> QueryResult:
    """Fail closed với lỗi tính toán/precision, không công bố một phần như tổng đầy đủ."""
    try:
        return _execute_query(db, actor, query.model_copy(deep=True))
    except pl.exceptions.PolarsError as exc:
        raise DomainError(
            "QUERY_EXECUTION_FAILED", "Truy vấn không thực hiện được an toàn."
        ) from exc


def _execute_query(db: Session, actor: Actor, query: DataQuery) -> QueryResult:
    """Đếm/aggregate ALL_MATCHING trước paging; raw không được báo KPI verified.

    Tối đa100k input,50 output/page,8predicates,5aggregates. Chỉ field catalogue
    và phép toán xác định; không join tự do, không suy PAID từ COMPLETED.
    """
    deadline = time.monotonic() + settings.agent_query_timeout_seconds
    source = _source(db, actor, query, deadline)
    validate_status_predicates(query)

    def collect(frame: pl.LazyFrame) -> pl.DataFrame:
        return _collect_bounded(frame, deadline)

    frame = source.frame
    count = collect(frame.select(pl.len())).item()
    if count > min(settings.max_rows, 100000):
        raise DomainError(
            "QUERY_ROW_LIMIT", "Nguồn vượt giới hạn truy vấn; chưa trả kết quả đầy đủ."
        )
    schema = frame.collect_schema()
    aggregate_names = {
        f"{agg.op}_{agg.field_id or 'rows'}_{i}" for i, agg in enumerate(query.aggregations)
    } | {f"null_count_{i}" for i, agg in enumerate(query.aggregations) if agg.op != "count"}
    if (
        len(set(query.select_fields)) != len(query.select_fields)
        or len(set(query.group_by)) != len(query.group_by)
        or len({s.field_id for s in query.sort}) != len(query.sort)
    ):
        raise DomainError("QUERY_FIELD_INVALID", "Không được lặp trường chọn, nhóm hoặc sắp xếp.")
    mentioned = (
        query.select_fields
        + query.group_by
        + [f.field_id for f in query.filters]
        + [s.field_id for s in query.sort if s.field_id not in aggregate_names]
        + [a.field_id for a in query.aggregations if a.field_id]
    )
    if not set(mentioned) <= set(source.fields):
        raise DomainError("QUERY_FIELD_INVALID", "Trường truy vấn không nằm trong nguồn đã chọn.")
    for rule in query.filters:
        col = pl.col(rule.field_id)
        if rule.op == "is_null":
            if rule.value is not None:
                raise DomainError("QUERY_VALUE_INVALID", "is_null không nhận giá trị.")
            expr = col.is_null()
        else:
            raw = rule.value
            if raw is None:
                raise DomainError("QUERY_VALUE_INVALID", "Dùng is_null để lọc null.")
            if rule.op in {"in", "between"}:
                if not isinstance(raw, list) or not 1 <= len(raw) <= 20:
                    raise DomainError("QUERY_VALUE_INVALID", "Cần danh sách lọc có giới hạn.")
                values = [_value(v, schema[rule.field_id]) for v in raw]
                if rule.op == "between":
                    if len(values) != 2:
                        raise DomainError("QUERY_VALUE_INVALID", "between cần hai cận.")
                    expr = col.is_between(values[0], values[1], closed="left")
                else:
                    expr = col.is_in(values)
            elif rule.op == "contains":
                if not isinstance(raw, str) or schema[rule.field_id] != pl.String:
                    raise DomainError("QUERY_TYPE_INVALID", "contains chỉ dành cho text.")
                _value(raw, pl.String())
                expr = col.str.contains(raw, literal=True)
            else:
                if not isinstance(raw, str):
                    raise DomainError("QUERY_VALUE_INVALID", "Cần một giá trị lọc.")
                value = _value(raw, schema[rule.field_id])
                expr = {
                    "eq": col == value,
                    "ne": col != value,
                    "gt": col > value,
                    "gte": col >= value,
                    "lt": col < value,
                    "lte": col <= value,
                }[rule.op]
        frame = frame.filter(expr.fill_null(False))
    matching = collect(frame.select(pl.len())).item()
    fields = query.select_fields or source.fields[:20]
    units = {}
    if query.aggregations:
        expressions = []
        for index, agg in enumerate(query.aggregations):
            name = f"{agg.op}_{agg.field_id or 'rows'}_{index}"
            if agg.op == "count":
                units[name] = "bản ghi"
                expressions.append(
                    (pl.col(agg.field_id).count() if agg.field_id else pl.len()).alias(name)
                )
                continue
            if agg.field_id is None:
                raise DomainError("QUERY_FIELD_INVALID", "Aggregate cần tên trường.")
            col = pl.col(agg.field_id)
            if agg.op == "sum_decimal":
                if agg.field_id not in source.money or not schema[agg.field_id].is_decimal():
                    raise DomainError(
                        "QUERY_SEMANTICS_REQUIRED",
                        "Chỉ cộng tiền đã xác nhận metric/currency/unit.",
                    )
                units[name] = source.money[agg.field_id][1]
                if query.currency_field is None or query.currency_field not in source.fields:
                    raise DomainError(
                        "QUERY_CURRENCY_REQUIRED", "Chọn cột currency để kiểm tra tổng tiền."
                    )
                currencies = (
                    collect(frame.select(pl.col(query.currency_field).unique()))
                    .to_series()
                    .to_list()
                )
                if currencies and currencies != [source.money[agg.field_id][0]]:
                    raise DomainError(
                        "QUERY_CURRENCY_MISMATCH", "Currency thiếu/khác định nghĩa; không cộng gộp."
                    )
                # Null toàn nhóm vẫn null; không biến unknown thành zero.
                expr = pl.when(col.count() > 0).then(col.sum()).otherwise(None)
            else:
                expr = col.min() if agg.op == "min" else col.max()
            expressions += [expr.alias(name), col.null_count().alias(f"null_count_{index}")]
        if "source_provenance" in schema:
            expressions.append(
                pl.col("source_provenance")
                .list.explode(keep_nulls=False, empty_as_null=False)
                .implode()
                .alias("source_provenance")
            )
        frame = (
            frame.group_by(query.group_by).agg(expressions)
            if query.group_by
            else frame.select(expressions)
        )
        fields = [f for f in frame.collect_schema().names() if f != "source_provenance"]
        total = collect(frame.select(pl.len())).item()
    else:
        if query.group_by:
            raise DomainError("QUERY_AGGREGATION_REQUIRED", "group_by cần aggregate rõ ràng.")
        total = matching
    if query.sort:
        if any(s.field_id not in frame.collect_schema() for s in query.sort):
            raise DomainError("QUERY_SORT_INVALID", "Trường sort không có trong kết quả.")
        sort_fields = [s.field_id for s in query.sort]
        descending = [s.descending for s in query.sort]
        if query.source_kind == "VERIFIED_RUN" and "group_id" not in sort_fields:
            if "group_id" in frame.collect_schema():
                sort_fields.append("group_id")
                descending.append(False)
        frame = frame.sort(sort_fields, descending=descending, nulls_last=True)
    elif query.group_by:
        frame = frame.sort(query.group_by, nulls_last=True)
    evidence_fields = [
        f
        for f in (
            "source_provenance",
            "_source_row_id",
            "_source_row",
            "group_id",
            "case_id",
            "canonical_record_id",
            "business_key",
        )
        if f in frame.collect_schema() and f not in fields
    ]
    records = collect(
        frame.select(fields + evidence_fields).slice(query.offset, query.limit)
    ).to_dicts()
    evidence_complete = True
    for row in records:
        lineage = row.get("source_provenance")
        if isinstance(lineage, list) and len(lineage) > 100:
            row["source_provenance"] = lineage[:100]
            row["_evidence_truncated"] = True
            evidence_complete = False
    rows = [{str(k): json_value(v) for k, v in row.items()} for row in records]
    return QueryResult(
        source_kind=query.source_kind,
        project_id=query.project_id,
        source_id=query.source_id,
        fields=fields,
        field_labels={f: source.labels[f] for f in fields if f in source.labels},
        rows=rows,
        total_count=total,
        offset=query.offset,
        limit=query.limit,
        truncated=total > query.offset + len(rows),
        input_count=matching,
        query=query,
        verification_status=source.status,
        source_refs=source.evidence,
        measure_units=units,
        quality_status=source.quality_status,
        evidence_complete=evidence_complete,
        warnings=["Tổng/đếm áp dụng toàn bộ dữ liệu khớp điều kiện, không chỉ trang hiện tại."]
        + (["Dữ liệu chưa được xác nhận ngữ nghĩa."] if source.status == "RAW_UNVERIFIED" else [])
        + (
            ["Nguồn canonical còn lỗi/thiếu dữ liệu; đây chưa phải KPI đối soát đã xác minh."]
            if source.quality_status and source.quality_status != "READY"
            else []
        ),
    )
