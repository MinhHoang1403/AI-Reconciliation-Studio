"""Independent Decimal and source membership assertions for semantic reporting."""

from datetime import date
from decimal import Decimal
from time import monotonic

import polars as pl
import pytest
from studio.contracts import CanonicalDataset, SchemaDefinition
from studio.contracts.agent import DatasetContext, IntentCatalogue, TableContext
from studio.contracts.assistant import AssistantContext
from studio.contracts.data_query import DataQuery, QueryAggregation, QueryFilter
from studio.data_query import QuerySource
from studio.errors import DomainError
from studio.semantic_intents import resolve_source_read, validate_source_money_language
from studio.semantic_query import execute_source_sql


def source():
    columns = pl.DataFrame(
        {
            "order_reference": ["001", "001", "002", "003", "004"],
            "event_date": [
                date(2026, 10, 1),
                date(2026, 10, 1),
                date(2026, 10, 2),
                date(2026, 10, 2),
                date(2026, 10, 3),
            ],
            "revenue": [Decimal("10.01"), Decimal("-1.25"), None, Decimal("8.50"), Decimal("5.00")],
            "currency": ["VND", "VND", "VND", "USD", "VND"],
            "invalid": [False, False, False, True, False],
            "canonical_record_id": ["r1", "r2", "r3", "r4", "r5"],
            "source_provenance": [[{"row": n}] for n in range(2, 7)],
        }
    )
    definition = SchemaDefinition.model_construct(revision=1, grain="order_line", fields=[])
    from studio.contracts import SchemaField

    definition.fields = [
        SchemaField(id="order_reference", name="Mã đơn", data_type="string"),
        SchemaField(id="event_date", name="Ngày", data_type="date"),
        SchemaField(id="currency", name="Tiền tệ", data_type="string"),
        SchemaField(
            id="revenue",
            name="Doanh thu",
            data_type="decimal",
            semantic_metric="net_revenue",
            amount_basis="net",
            currency="VND",
            unit="VND",
        ),
    ]
    canonical = CanonicalDataset.model_construct(
        id="canonical",
        mapping_revision_id="mapping",
        quality_status="PARTIAL",
        row_count=5,
        valid_count=4,
        invalid_count=1,
        excluded_source_rows=0,
        source_row_count=5,
    )
    return QuerySource(
        columns.lazy(),
        [f.id for f in definition.fields],
        ["artifact"],
        "CANONICAL",
        {},
        canonical=canonical,
        definition=definition,
        source_name="Fixture.csv",
    )


def query(**kwargs):
    return DataQuery(project_id="project", source_kind="CANONICAL", source_id="canonical", **kwargs)


def catalogue():
    schema = source().definition
    assert schema
    table = TableContext(
        table_id="table",
        sheet="Sheet",
        row_count=5,
        columns=[],
        canonical_id="canonical",
        schema_definition=schema,
        approved_status_values={"payment_status": ["PAID"]},
    )
    return IntentCatalogue(
        context=AssistantContext(project_id="project"),
        datasets=[DatasetContext(id="file", name="Bán hàng.csv", status="READY", tables=[table])],
    )


def test_router_keeps_explicit_scope_and_distinguishes_orders_from_rows():
    context = catalogue()
    intent = resolve_source_read("Có bao nhiêu đơn hàng trong Bán hàng?", context)
    assert intent and intent.query
    assert intent.query.aggregations == [
        QueryAggregation(op="count_distinct", field_id="order_reference")
    ]
    intent = resolve_source_read("Tổng doanh thu ngày 03/10/2026 có trạng thái PAID", context)
    assert intent and intent.query
    assert intent.query.filters == [
        QueryFilter(field_id="event_date", op="between", value=["2026-10-03", "2026-10-04"]),
        QueryFilter(field_id="payment_status", op="eq", value="PAID"),
    ]
    validate_source_money_language(
        "Tổng doanh thu ngày 03/10/2026 có trạng thái PAID",
        intent.query,
        context.datasets[0].tables[0],
    )
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        validate_source_money_language(
            "Tổng doanh thu ngày 04/10/2026", intent.query, context.datasets[0].tables[0]
        )
    for goal in (
        "Tổng doanh thu Bán hàng có mã ABC",
        "Tổng doanh thu Bán hàng hôm qua",
        "Tổng doanh thu có trạng thái VOID",
    ):
        intent = resolve_source_read(goal, context)
        assert intent and intent.intent == "CLARIFY"


@pytest.mark.parametrize("source_name", ["Bán hàng", "Bán hàng.csv", "của báo cáo bán hàng"])
def test_named_source_may_precede_calendar_grouping(source_name):
    intent = resolve_source_read(
        f"Doanh thu {source_name} theo từng ngày tháng 10/2026.", catalogue()
    )
    assert intent and intent.query
    assert intent.query.source_id == "canonical"
    assert intent.query.calendar_bucket == "day"
    assert intent.query.group_by == ["event_date"]
    assert intent.query.filters[0].value == ["2026-10-01", "2026-11-01"]


def test_bound_sql_counts_exact_identifiers_and_decimal_with_null_and_refund():
    result = execute_source_sql(
        query(
            source_measure_id="revenue",
            aggregations=[
                QueryAggregation(op="sum_decimal", field_id="revenue"),
                QueryAggregation(op="count_distinct", field_id="order_reference"),
            ],
        ),
        source(),
        monotonic() + 5,
    )
    assert result.rows[0]["sum_decimal_revenue_0"] == "13.76"
    assert result.rows[0]["count_distinct_order_reference_1"] == 3
    assert result.source_evidence and result.source_evidence.counted_rows == 3
    assert result.source_evidence.invalid_rows == 1


def test_sql_uses_parameters_and_rejects_unknown_measure():
    payload = "001' OR '1'='1"
    result = execute_source_sql(
        query(
            source_measure_id="revenue",
            filters=[
                QueryFilter(field_id="order_reference", op="eq", value=payload),
            ],
        ),
        source(),
        monotonic() + 5,
    )
    assert result.total_count == 0
    assert result.source_evidence and payload not in result.source_evidence.sql
    with pytest.raises(DomainError, match="QUERY_SEMANTICS_REQUIRED"):
        execute_source_sql(query(source_measure_id="made_up"), source(), monotonic() + 5)


def test_sql_preserves_exclusive_dates_and_month_bucket():
    result = execute_source_sql(
        query(
            source_measure_id="revenue",
            calendar_bucket="month",
            group_by=["event_date"],
            filters=[
                QueryFilter(field_id="event_date", op="between", value=["2026-10-01", "2026-10-03"])
            ],
            aggregations=[QueryAggregation(op="sum_decimal", field_id="revenue")],
        ),
        source(),
        monotonic() + 5,
    )
    assert result.rows[0]["event_date"] == "2026-10-01"
    assert result.rows[0]["sum_decimal_revenue_0"] == "8.76"
    with pytest.raises(DomainError, match="QUERY_TIMEOUT"):
        execute_source_sql(query(source_measure_id="revenue"), source(), monotonic() - 1)
