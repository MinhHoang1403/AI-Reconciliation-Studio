"""Bound SQL analytics over the canonical rows that passed workspace and artifact checks."""

import json
import time
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, localcontext
from threading import Timer
from typing import Any

import duckdb
import polars as pl

from studio.config import settings
from studio.contracts import SourceQualityCounts, source_quality_reason
from studio.contracts.data_query import DataQuery, QueryResult, QuerySort, SourceQueryEvidence
from studio.data_query import QuerySource, _collect_bounded, _value, json_value, source_measures
from studio.errors import DomainError

OPS = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
AGGREGATES = {"sum_decimal": "SUM", "min": "MIN", "max": "MAX", "count": "COUNT"}
SOURCE_POSITION = "_query_source_position"


def identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def predicates(query: DataQuery, schema: pl.Schema) -> tuple[list[str], list[Any], list[pl.Expr]]:
    sql, parameters, expressions = [], [], []
    for rule in query.filters:
        field, dtype = identifier(rule.field_id), schema[rule.field_id]
        col, raw = pl.col(rule.field_id), rule.value
        if rule.op == "is_null" and raw is None:
            sql.append(f"{field} IS NULL")
            expressions.append(col.is_null())
        elif rule.op == "in" and isinstance(raw, list) and 1 <= len(raw) <= 20:
            values = [_value(v, dtype) for v in raw]
            sql.append(f"{field} IN ({', '.join('?' for _ in values)})")
            parameters.extend(values)
            expressions.append(col.is_in(values))
        elif rule.op == "between" and isinstance(raw, list) and len(raw) == 2:
            first, end = [_value(v, dtype) for v in raw]
            sql.append(f"({field} >= ? AND {field} < ?)")
            parameters.extend([first, end])
            expressions.append(col.is_between(first, end, closed="left"))
        elif isinstance(raw, str) and rule.op in OPS:
            value = _value(raw, dtype)
            sql.append(f"{field} {OPS[rule.op]} ?")
            parameters.append(value)
            expressions.append(getattr(col, rule.op)(value))
        elif rule.op == "contains" and isinstance(raw, str) and dtype == pl.String:
            parameters.append(_value(raw, dtype))
            sql.append(f"contains({field}, ?)")
            expressions.append(col.str.contains(raw, literal=True))
        else:
            raise DomainError("QUERY_VALUE_INVALID", "Điều kiện lọc chưa phù hợp với cột đã chọn.")
    return sql, parameters, expressions


def _sql_type(dtype: pl.DataType) -> str:
    if isinstance(dtype, pl.Decimal):
        return f"DECIMAL(38,{dtype.scale})"
    if dtype == pl.Date:
        return "DATE"
    if dtype == pl.String:
        return "VARCHAR"
    if dtype.is_integer():
        return "BIGINT"
    if dtype == pl.Boolean:
        return "BOOLEAN"
    raise DomainError("QUERY_TYPE_UNSUPPORTED", "Kiểu cột chưa được hỗ trợ cho truy vấn này.")


def source_quality_counts(
    errors: pl.LazyFrame | None,
    invalid: pl.LazyFrame,
    amount_fields: set[str],
    date_fields: set[str],
    key_fields: set[str],
    deadline: float,
) -> SourceQualityCounts | None:
    if errors is None:
        return None
    ids = invalid.select(
        pl.col("source_provenance")
        .list.explode()
        .struct.field("source_row_id")
        .alias("source_row_id")
    )
    issues = _collect_bounded(
        errors.select("source_row_id", "field", "code").join(ids, on="source_row_id", how="semi"),
        deadline,
    )
    row_reasons: dict[str, set[str]] = defaultdict(set)
    for row, target, code in issues.iter_rows():
        reason = source_quality_reason(code, target, amount_fields, date_fields, key_fields)
        if reason:
            row_reasons[row].add(reason)
    source_ids = _collect_bounded(ids.unique(), deadline).to_series()
    counts = Counter(reason for row in source_ids for reason in row_reasons.get(row, {"other"}))
    if time.monotonic() >= deadline:
        raise DomainError("QUERY_TIMEOUT", "Truy vấn vượt thời gian kiểm chứng.", 409)
    return SourceQualityCounts(**counts)


def execute_source_sql(query: DataQuery, source: QuerySource, deadline: float) -> QueryResult:
    canonical, schema = source.canonical, source.definition
    assert canonical and schema
    if canonical.quality_status == "FAILED" or canonical.row_count > min(settings.max_rows, 100000):
        raise DomainError("QUERY_ROW_LIMIT", "Nguồn chưa sẵn sàng hoặc vượt giới hạn truy vấn.")
    measures = {measure.field_id: measure for measure in source_measures(schema)}
    types = source.frame.collect_schema()
    if not set(source.fields) <= types.keys():
        raise DomainError("CANONICAL_SCHEMA_MISMATCH", "Bản chuẩn hóa thiếu cột đã xác nhận.")
    if (
        not query.source_measure_id
        and not query.currency_field
        and any(a.op == "sum_decimal" for a in query.aggregations)
    ):
        raise DomainError(
            "QUERY_CURRENCY_REQUIRED", "Chọn chỉ tiêu nguồn hoặc cột tiền tệ đã chuẩn hóa."
        )
    numeric = {
        a.field_id
        for a in query.aggregations
        if a.op == "sum_decimal" or (a.op in {"min", "max"} and a.field_id in measures)
    }
    if not query.source_measure_id and len(numeric) == 1:
        (query.source_measure_id,) = numeric
    measure = measures.get(query.source_measure_id or "")
    if (numeric or query.source_measure_id) and (measure is None or numeric - {measure.field_id}):
        raise DomainError(
            "QUERY_SEMANTICS_REQUIRED", "Hãy chọn một chỉ tiêu tiền đã xác nhận của nguồn này."
        )
    if query.ranking_size and (
        not measure
        or query.aggregations
        or query.sort != [QuerySort(field_id=measure.field_id, descending=True)]
    ):
        raise DomainError("QUERY_SORT_INVALID", "Top N cần giữ thứ tự theo số tiền đã chọn.")
    if query.currency_field and query.currency_field != "currency":
        raise DomainError("QUERY_CURRENCY_REQUIRED", "Cột tiền tệ phải là trường đã chuẩn hóa.")
    currency = "currency" if measure and "currency" in source.fields else None
    if currency:
        query.currency_field = currency
    if query.calendar_bucket and (len(query.group_by) != 1 or not query.aggregations):
        raise DomainError("QUERY_FIELD_INVALID", "Nhóm ngày cần một cột ngày và phép thống kê.")
    aggregate_names = [
        f"{a.op}_{a.field_id or 'rows'}_{i}" for i, a in enumerate(query.aggregations)
    ]
    fields = query.select_fields or source.fields[:20]
    requested = set(query.group_by + query.select_fields + [f.field_id for f in query.filters])
    requested.update(a.field_id for a in query.aggregations if a.field_id)
    requested.update(s.field_id for s in query.sort if s.field_id not in aggregate_names)
    if not requested <= set(source.fields) or any(
        len(values) != len(set(values)) for values in (query.group_by, query.select_fields)
    ):
        raise DomainError("QUERY_FIELD_INVALID", "Trường truy vấn không thuộc nguồn đã chọn.")
    if query.calendar_bucket and types[query.group_by[0]] != pl.Date:
        raise DomainError("QUERY_TYPE_INVALID", "Cần cột ngày lịch đã được xác nhận.")
    if any(
        a.op == "count_distinct" and (not a.field_id or types[a.field_id] != pl.String)
        for a in query.aggregations
    ):
        raise DomainError("QUERY_TYPE_INVALID", "Đếm mã duy nhất cần cột định danh dạng chuỗi.")
    if any(a.op != "count" and not a.field_id for a in query.aggregations):
        raise DomainError("QUERY_FIELD_INVALID", "Phép tính cần một trường đã xác nhận.")
    if any(
        a.field_id
        and a.op in {"min", "max"}
        and types[a.field_id].is_decimal()
        and a.field_id not in measures
        for a in query.aggregations
    ):
        raise DomainError("QUERY_SEMANTICS_REQUIRED", "Cột tiền chưa có định nghĩa đã xác nhận.")
    if not query.aggregations and query.group_by:
        raise DomainError("QUERY_AGGREGATION_REQUIRED", "Cần chọn phép tính cho từng nhóm.")
    date_fields = [f.id for f in schema.fields if f.data_type == "date" and types[f.id] == pl.Date]
    date_field = (
        query.group_by[0]
        if query.calendar_bucket
        else (date_fields[0] if len(date_fields) == 1 else None)
    )
    if date_field:
        requested.add(date_field)
    if measure:
        requested.add(measure.field_id)
    if currency:
        requested.add(currency)
    if not query.aggregations:
        requested.update(fields)
    tie_keys = (
        [
            key
            for key in schema.business_key_fields
            if key in source.fields and all(sort.field_id != key for sort in query.sort)
        ]
        if not query.aggregations
        else []
    )
    requested.update(tie_keys)
    expected_count = _collect_bounded(source.frame.select(pl.len()), deadline).item()
    if expected_count != canonical.row_count:
        raise DomainError("CANONICAL_COUNT_MISMATCH", "Số dòng không khớp bản chuẩn hóa.")
    valid = source.frame.filter(~pl.col("invalid"))
    valid_count = _collect_bounded(valid.select(pl.len()), deadline).item()
    if (
        valid_count != canonical.valid_count
        or expected_count - valid_count != canonical.invalid_count
    ):
        raise DomainError("CANONICAL_COUNT_MISMATCH", "Phân hoạch dòng không khớp bản chuẩn hóa.")
    if currency and measure:
        valid = valid.filter(pl.col(currency) == measure.currency)
    names = sorted(requested)
    frame = _collect_bounded(
        valid.select(names + ["canonical_record_id", "source_provenance"]), deadline
    )
    if currency and frame.height != valid_count:
        raise DomainError(
            "QUERY_CURRENCY_MISMATCH",
            "Có dòng hợp lệ khác tiền tệ đã xác nhận. Hãy kiểm tra phạm vi.",
        )
    if not query.aggregations:
        # A canonical table belongs to one source table. Grouped canonical
        # records use the earliest physical row among their source members.
        frame = frame.with_columns(
            pl.col("source_provenance")
            .list.eval(pl.element().struct.field("row"))
            .list.min()
            .cast(pl.Int64)
            .alias(SOURCE_POSITION)
        )
        names.append(SOURCE_POSITION)
    where, parameters, checks = predicates(query, types)
    if query.ranking_size and measure:
        where.append(f"{identifier(measure.field_id)} IS NOT NULL")
        checks.append(pl.col(measure.field_id).is_not_null())
    subset = frame.filter(*checks) if checks else frame
    projections: list[str] = []
    group_fields = [identifier(f) for f in query.group_by]
    if query.calendar_bucket == "month":
        group_fields[0] = f"CAST(date_trunc('month', {group_fields[0]}) AS DATE)"
    projections.extend(
        f"{expr} AS {identifier(name)}"
        for expr, name in zip(group_fields, query.group_by, strict=True)
    )
    units = {}
    if query.aggregations:
        fields = query.group_by + aggregate_names
        for aggregation, alias in zip(query.aggregations, aggregate_names, strict=True):
            field = identifier(aggregation.field_id) if aggregation.field_id else "*"
            expr = (
                f"COUNT(DISTINCT {field})"
                if aggregation.op == "count_distinct"
                else f"{AGGREGATES[aggregation.op]}({field})"
            )
            projections.append(f"{expr} AS {identifier(alias)}")
            if (
                measure
                and aggregation.field_id == measure.field_id
                and aggregation.op in {"sum_decimal", "min", "max"}
            ):
                units[alias] = measure.unit
            elif aggregation.op in {"count", "count_distinct"}:
                units[alias] = "bản ghi"
    else:
        projections = [identifier(f) for f in [*fields, "canonical_record_id"]]
    if any(s.field_id not in (fields if query.aggregations else source.fields) for s in query.sort):
        raise DomainError("QUERY_SORT_INVALID", "Cột sắp xếp không nằm trong kết quả.")
    order = [
        f"{identifier(s.field_id)} {'DESC' if s.descending else 'ASC'} NULLS LAST"
        for s in query.sort
    ]
    fallback_order = (
        query.group_by
        if query.aggregations
        else [*tie_keys, SOURCE_POSITION, "canonical_record_id"]
    )
    order.extend(f"{identifier(field)} ASC NULLS LAST" for field in fallback_order)
    sql = "SELECT " + ", ".join(projections) + " FROM source"
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    sql += where_sql
    if group_fields:
        sql += " GROUP BY " + ", ".join(group_fields)
    if order:
        sql += " ORDER BY " + ", ".join(order)
    sql += " LIMIT ? OFFSET ?"
    page_limit = (
        min(query.limit, max(0, query.ranking_size - query.offset))
        if query.ranking_size
        else query.limit
    )
    names.append("canonical_record_id")
    values = [
        {k: json_value(v) for k, v in row.items()}
        for row in frame.select(names).iter_rows(named=True)
    ]
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    if len(payload.encode()) > 32_000_000:
        raise DomainError("QUERY_ROW_LIMIT", "Chọn ít cột hơn để kiểm tra nguồn trong giới hạn.")
    types_json = json.dumps([{name: _sql_type(frame.schema[name]) for name in names}])
    if time.monotonic() >= deadline:
        raise DomainError("QUERY_TIMEOUT", "Truy vấn vượt thời gian kiểm chứng.", 409)
    try:
        with duckdb.connect(
            config={
                "enable_external_access": False,
                "autoload_known_extensions": False,
                "autoinstall_known_extensions": False,
                "memory_limit": "64MB",
                "threads": 1,
                "temp_directory": "",
            }
        ) as connection:
            timer = Timer(max(0.001, deadline - time.monotonic()), connection.interrupt)
            timer.daemon = True
            timer.start()
            try:
                connection.execute(
                    "CREATE TEMP TABLE source AS SELECT row_data.* "
                    "FROM unnest(from_json(?, ?)) t(row_data)",
                    [payload, types_json],
                )
                sql_count = connection.execute(
                    "SELECT COUNT(*) FROM source" + where_sql, parameters
                ).fetchone()
                cursor = connection.execute(sql, [*parameters, page_limit, query.offset])
                columns = [d[0] for d in cursor.description]
                raw_rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
            finally:
                timer.cancel()
                timer.join()
    except duckdb.InterruptException as exc:
        raise DomainError("QUERY_TIMEOUT", "Truy vấn vượt thời gian kiểm chứng.", 409) from exc
    except duckdb.OutOfMemoryException as exc:
        raise DomainError(
            "QUERY_MEMORY_LIMIT", "Truy vấn vượt giới hạn bộ nhớ. Hãy thu hẹp phạm vi.", 409
        ) from exc
    except duckdb.Error as exc:
        raise DomainError(
            "QUERY_EXECUTION_FAILED", "Không thể tính đầy đủ trong giới hạn truy vấn."
        ) from exc
    if not sql_count or sql_count[0] != subset.height:
        raise DomainError("QUERY_VERIFICATION_FAILED", "Số dòng khớp điều kiện chưa nhất quán.")
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    ranking_ties = None
    if query.aggregations:
        if not query.group_by:
            groups[()] = []
        for row in subset.iter_rows(named=True):
            keys = tuple(row[name] for name in query.group_by)
            if query.calendar_bucket == "month" and isinstance(keys[0], date):
                keys = (keys[0].replace(day=1),)
            groups[keys].append(row)
        with localcontext() as context:
            context.prec = 100
            for row in raw_rows:
                members = groups[tuple(row[name] for name in query.group_by)]
                for aggregation, alias in zip(query.aggregations, aggregate_names, strict=True):
                    counted: list[Any] = (
                        [
                            item[aggregation.field_id]
                            for item in members
                            if item[aggregation.field_id] is not None
                        ]
                        if aggregation.field_id
                        else members
                    )
                    expected: Decimal | int | str | date | None
                    if aggregation.op == "count":
                        expected = len(counted)
                    elif aggregation.op == "count_distinct":
                        expected = len(set(counted))
                    elif not counted:
                        expected = None
                    elif aggregation.op == "sum_decimal":
                        expected = sum(counted, Decimal(0))
                    elif aggregation.op == "min":
                        expected = min(counted)
                    else:
                        expected = max(counted)
                    if row[alias] != expected:
                        raise DomainError(
                            "QUERY_VERIFICATION_FAILED", "Kết quả SQL không khớp phép tính độc lập."
                        )
                refs = [ref for item in members for ref in item["source_provenance"]]
                row["source_provenance"] = refs[:100]
                if len(refs) > 100:
                    row["_evidence_truncated"] = True
    else:
        evidence = dict(subset.select("canonical_record_id", "source_provenance").iter_rows())
        ordering = [(sort.field_id, sort.descending) for sort in query.sort] + [
            (field, False) for field in fallback_order
        ]
        keys, directions = zip(*ordering, strict=True)
        ordered = subset.sort(list(keys), descending=list(directions), nulls_last=True)
        expected_ids = ordered.slice(query.offset, page_limit)["canonical_record_id"].to_list()
        if query.ranking_size and measure and ordered.height >= query.ranking_size:
            boundary = ordered[measure.field_id][query.ranking_size - 1]
            ranking_ties = subset.filter(pl.col(measure.field_id) == boundary).height
        if [row["canonical_record_id"] for row in raw_rows] != expected_ids:
            raise DomainError("QUERY_VERIFICATION_FAILED", "Thứ tự bản ghi không khớp kiểm chứng.")
        for row in raw_rows:
            row["source_provenance"] = evidence[row["canonical_record_id"]]
    total = len(groups) if query.aggregations else subset.height
    if query.ranking_size:
        total = min(total, query.ranking_size)
    if (
        len(raw_rows) != max(0, min(total - query.offset, query.limit))
        or time.monotonic() >= deadline
    ):
        raise DomainError("QUERY_VERIFICATION_FAILED", "Trang kết quả chưa được kiểm tra đầy đủ.")
    observed = subset[date_field].drop_nulls() if date_field else None
    counted_rows = (
        subset[measure.field_id].len() - subset[measure.field_id].null_count()
        if measure
        else subset.height
    )
    quality_counts = (
        SourceQualityCounts()
        if canonical.invalid_count == 0
        else source_quality_counts(
            source.errors,
            source.frame.filter(pl.col("invalid")),
            set(measures),
            set(date_fields),
            set(schema.business_key_fields)
            | {f.id for f in schema.fields if f.required and f.data_type == "string"},
            deadline,
        )
    )
    return QueryResult(
        project_id=query.project_id,
        source_kind="CANONICAL",
        source_id=query.source_id,
        fields=fields,
        field_labels={
            **source.labels,
            **(
                {name: measure.name for name in units if units[name] == measure.unit}
                if measure
                else {}
            ),
        },
        rows=[{k: json_value(v) for k, v in row.items()} for row in raw_rows],
        query=query,
        total_count=total,
        input_count=subset.height,
        limit=query.limit,
        offset=query.offset,
        truncated=total > query.offset + len(raw_rows),
        verification_status="CANONICAL",
        source_refs=source.evidence,
        measure_units=units,
        quality_status=source.quality_status,
        evidence_complete=not any(row.get("_evidence_truncated") for row in raw_rows),
        source_evidence=SourceQueryEvidence(
            source_name=source.source_name,
            canonical_id=canonical.id,
            mapping_id=canonical.mapping_revision_id,
            schema_revision=schema.revision,
            grain=schema.grain,
            measure=measure,
            source_rows=canonical.source_row_count or canonical.row_count,
            invalid_rows=canonical.invalid_count,
            excluded_rows=canonical.excluded_source_rows,
            matching_rows=subset.height,
            counted_rows=counted_rows,
            valid_rows=valid_count,
            out_of_scope_rows=valid_count - subset.height,
            quality_counts=quality_counts,
            ranking_ties=ranking_ties,
            observed_first=str(observed.min()) if observed is not None and len(observed) else None,
            observed_last=str(observed.max()) if observed is not None and len(observed) else None,
            sql=sql,
        ),
    )
