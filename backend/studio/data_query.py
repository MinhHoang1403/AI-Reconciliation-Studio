"""Compile truy vấn allowlist trên artifact đã kiểm quyền; không nhận SQL hoặc path."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import polars as pl
from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.access import Actor
from studio.config import settings
from studio.contracts import CanonicalDataset, SchemaDefinition
from studio.contracts.data_query import DataQuery, QueryResult
from studio.database import (
    ArtifactRow,
    CanonicalRow,
    ExceptionRow,
    MembershipRow,
    RunRow,
    SchemaRow,
    TableRow,
)
from studio.errors import DomainError
from studio.reconciliation_repository import result_path
from studio.repository import get_scoped, project_for_table
from studio.storage import checksum, storage_path


@dataclass
class QuerySource:
    frame: pl.LazyFrame
    fields: list[str]
    evidence: list[str]
    status: str
    money: dict[str, tuple[str, str]]


def _source(db: Session, actor: Actor, query: DataQuery) -> QuerySource:
    """Mỗi truy vấn kiểm lại actor/project/artifact/checksum, không tin IDs model chọn."""
    if db.get(MembershipRow, (actor.workspace_id, actor.id)) is None:
        raise DomainError("RESOURCE_NOT_FOUND", "Quyền truy cập không còn hợp lệ.", 404)
    if query.source_kind in {"RAW_PREVIEW", "CANONICAL"}:
        canonical = None
        if query.source_kind == "CANONICAL":
            row = get_scoped(db, CanonicalRow, query.source_id, actor)
            canonical = CanonicalDataset.model_validate(row.contract)
            if row.stale:
                raise DomainError("STALE_CONTEXT", "Dữ liệu chuẩn hóa đã cũ.", 409)
            table = get_scoped(db, TableRow, row.source_table_id, actor)
            artifact = get_scoped(db, ArtifactRow, canonical.artifact.id, actor)
        else:
            table = get_scoped(db, TableRow, query.source_id, actor)
            artifact = get_scoped(db, ArtifactRow, table.artifact_id, actor)
        if project_for_table(db, table).id != query.project_id:
            raise DomainError("RESOURCE_NOT_FOUND", "Nguồn không thuộc dự án.", 404)
        path = storage_path(settings.storage_root, artifact.storage_key)
        if checksum(path) != artifact.sha256:
            raise DomainError("ARTIFACT_CHECKSUM_FAILED", "Dữ liệu không khớp checksum.")
        frame = pl.scan_parquet(path)
        money = {}
        if canonical:
            definition = SchemaDefinition.model_validate(
                get_scoped(db, SchemaRow, canonical.schema_id, actor).definition
            )
            fields = [f.id for f in definition.fields]
            money = {
                f.id: (f.currency, f.unit)
                for f in definition.fields
                if f.data_type == "decimal" and f.currency and f.unit and f.semantic_metric
            }
            frame = frame.unnest("record_payload")
        else:
            fields = [c["id"] for c in table.parsed_contract["columns"]]
        return QuerySource(
            frame,
            fields,
            [artifact.id, table.id],
            "CANONICAL" if canonical else "RAW_UNVERIFIED",
            money,
        )
    run = get_scoped(db, RunRow, query.source_id, actor)
    if run.project_id != query.project_id:
        raise DomainError("RESOURCE_NOT_FOUND", "Run không thuộc dự án.", 404)
    if run.status not in {"VERIFIED", "PARTIAL_VERIFIED"} or run.metric_snapshot is None:
        raise DomainError("INSUFFICIENT_EVIDENCE", "Run chưa được xác minh.", 409)
    if query.source_kind == "VERIFIED_RUN":
        frame = pl.scan_parquet(result_path(run))
        fields = ["group_id", "linkage_state", "comparison_state"]
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
                .limit(settings.max_rows + 1)
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
            schema={k: pl.String for k in ("case_id", "group_id", "type", "state", "notes")},
        ).lazy()
        fields = ["case_id", "group_id", "type", "state", "notes"]
    return QuerySource(frame, fields, [run.id, run.metric_snapshot["id"]], run.status, {})


def _value(value: str, dtype: pl.DataType) -> str | Decimal | datetime | int | bool:
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


def execute_query(db: Session, actor: Actor, query: DataQuery) -> QueryResult:
    """Đếm/aggregate ALL_MATCHING trước paging; raw không được báo KPI verified.

    Tối đa100k input,50 output/page,8predicates,5aggregates. Chỉ field catalogue
    và phép toán xác định; không join tự do, không suy PAID từ COMPLETED.
    """
    source = _source(db, actor, query)
    frame = source.frame
    count = frame.select(pl.len()).collect().item()
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
    matching = frame.select(pl.len()).collect().item()
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
                    frame.select(pl.col(query.currency_field).unique())
                    .collect()
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
        total = frame.select(pl.len()).collect().item()
    else:
        if query.group_by:
            raise DomainError("QUERY_AGGREGATION_REQUIRED", "group_by cần aggregate rõ ràng.")
        total = matching
    if query.sort:
        if any(s.field_id not in frame.collect_schema() for s in query.sort):
            raise DomainError("QUERY_SORT_INVALID", "Trường sort không có trong kết quả.")
        frame = frame.sort(
            [s.field_id for s in query.sort],
            descending=[s.descending for s in query.sort],
            nulls_last=True,
        )
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
        )
        if f in frame.collect_schema() and f not in fields
    ]
    records = (
        frame.select(fields + evidence_fields).slice(query.offset, query.limit).collect().to_dicts()
    )
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
        evidence_complete=evidence_complete,
        warnings=["Tổng/đếm áp dụng toàn bộ dữ liệu khớp điều kiện, không chỉ trang hiện tại."]
        + (
            ["Dữ liệu raw chưa được xác nhận ngữ nghĩa."]
            if source.status == "RAW_UNVERIFIED"
            else []
        ),
    )
