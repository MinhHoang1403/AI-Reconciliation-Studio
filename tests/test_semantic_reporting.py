"""Independent Decimal and source membership assertions for semantic reporting."""

from datetime import date
from decimal import Decimal
from time import monotonic

import polars as pl
import pytest
from studio.contracts import CanonicalDataset, SchemaDefinition
from studio.contracts.agent import DatasetContext, IntentCatalogue, TableContext
from studio.contracts.assistant import AssistantContext
from studio.contracts.data_query import DataQuery, QueryAggregation, QueryFilter, QuerySort
from studio.data_query import QuerySource
from studio.errors import DomainError
from studio.semantic_intents import resolve_source_read, validate_source_query_coverage
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
    validate_source_query_coverage(intent.query, intent)
    with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
        validate_source_query_coverage(
            intent.query, resolve_source_read("Tổng doanh thu ngày 04/10/2026", context)
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


@pytest.mark.parametrize(
    ("clause", "op", "value"),
    [
        ("nửa đầu tháng 2/2024", "between", ["2024-02-01", "2024-02-16"]),
        ("nửa sau tháng 2/2024", "between", ["2024-02-16", "2024-03-01"]),
        ("từ ngày 28/02/2024 đến hết ngày 29/02/2024", "between", ["2024-02-28", "2024-03-01"]),
        ("trước ngày 29/02/2024", "lt", "2024-02-29"),
        ("sau ngày 29/02/2024", "gte", "2024-03-01"),
        ("quý IV/2024", "between", ["2024-10-01", "2025-01-01"]),
        ("năm 2024", "between", ["2024-01-01", "2025-01-01"]),
    ],
)
@pytest.mark.parametrize("suffix", ["", " là bao nhiêu?", " giúp tôi."])
def test_calendar_constraints_are_complete(clause, op, value, suffix):
    intent = resolve_source_read(f"Tổng doanh thu của Bán hàng trong {clause}{suffix}", catalogue())
    assert intent and intent.query
    assert intent.query.filters == [QueryFilter(field_id="event_date", op=op, value=value)]


@pytest.mark.parametrize("has_currency", [True, False])
def test_canonical_routing_schema_cannot_use_amount_as_currency(has_currency):
    from studio.agent_intents import interpret_requests
    from studio.contracts import WorkspacePolicy

    context = catalogue()
    definition = context.datasets[0].tables[0].schema_definition
    assert definition
    if not has_currency:
        definition.fields = [field for field in definition.fields if field.id != "currency"]
    captured = {}

    class Capture:
        local = False
        usage = {}

        def request_typed(self, *args, **kwargs):
            captured.update(kwargs["response_schema"])
            return []

    interpret_requests(
        Capture(), ['Tổng doanh thu của "Bán hàng.csv"'], context, WorkspacePolicy(), lambda: True
    )
    variants = captured["$defs"]["RoutingQuery"]["anyOf"]
    canonical = next(
        entry for entry in variants if "canonical-1" in entry["properties"]["source_ref"]["enum"]
    )
    assert canonical["properties"]["currency_field"] == (
        {"anyOf": [{"type": "string", "enum": ["currency"]}, {"type": "null"}]}
        if has_currency
        else {"type": "null"}
    )


def test_explicit_filename_and_bound_financial_batch_do_not_advertise_raw_fields():
    import json

    from studio.agent_intents import interpret_requests, read_query_sources, routing_sources
    from studio.contracts import WorkspacePolicy

    context = catalogue()
    context.datasets.append(
        context.datasets[0].model_copy(update={"id": "other", "name": "Khác.xlsx"}, deep=True)
    )
    context.datasets[-1].tables[0].canonical_id = "other-canonical"
    context.datasets[-1].tables[0].table_id = "other-table"
    goal = 'Tổng doanh thu của "Bán hàng.csv" trong tháng 10/2026'
    sources = routing_sources(context)
    assert {s["dataset_id"] for s in read_query_sources(goal, context, sources)} == {"file"}
    captured = {}

    class Capture:
        local = False
        usage = {}

        def request_typed(self, prompt, *_args, **kwargs):
            captured["prompt"] = json.loads(prompt[1]["content"])
            captured["schema"] = kwargs["response_schema"]
            return []

    interpret_requests(Capture(), [goal, goal], context, WorkspacePolicy(), lambda: True)
    assert [(s["source_kind"], s["dataset_id"]) for s in captured["prompt"]["sources"]] == [
        ("CANONICAL", "file")
    ]
    query_defs = captured["schema"]["$defs"]["RoutingQuery"]["anyOf"]
    assert len(query_defs) == 1
    assert query_defs[0]["properties"]["source_ref"]["enum"] == ["canonical-1"]


@pytest.mark.parametrize(
    "clause",
    [
        "đầu tháng 2/2024",
        "cuối tháng 2/2024",
        "ngày 29/02/2025",
        "tháng 13/2024",
        "tháng 2/2024 hoặc tháng 3/2024",
        "tại chi nhánh Hà Nội",
        "nửa đầu tháng 2/2024 và theo phương thức giao hàng",
        "tháng 2/2024 và xóa nguồn",
        "tháng 2/2024 và theo phương thức giao hàng là bao nhiêu?",
        "ngoại trừ các đơn hủy",
    ],
)
def test_unbound_constraints_cannot_be_discarded(clause):
    intent = resolve_source_read(f"Tổng doanh thu Bán hàng {clause}", catalogue())
    assert intent and intent.intent == "CLARIFY" and intent.query is None


def test_branch_and_calendar_bind_against_confirmed_metadata_and_provider_plan():
    from studio.agent_intents import validate_intents
    from studio.contracts import SchemaField
    from studio.contracts.agent import IntentBatch

    context = catalogue()
    dataset = context.datasets[0]
    dataset.name = "Thuê kho tháng thử.xlsx"
    schema = dataset.tables[0].schema_definition
    assert schema
    schema.fields.append(SchemaField(id="depot", name="Chi nhánh", data_type="string"))
    goals = (
        'Tổng doanh thu tại chi nhánh "Hà Nội" trong nửa sau tháng 2/2024',
        'Trong nửa sau tháng 2/2024, tổng doanh thu tại chi nhánh "Hà Nội"',
        'Tong doanh thu cua tep "Thue kho thang thu.xlsx" tai chi nhanh "Hà Nội" '
        "nua sau thang 2/2024",
    )
    results = [resolve_source_read(goal, context) for goal in goals]
    assert all(result and result.query for result in results), results
    first = results[0]
    assert first and first.query
    assert all(result and result.query == first.query for result in results)
    assert first.query.filters == [
        QueryFilter(field_id="event_date", op="between", value=["2024-02-16", "2024-03-01"]),
        QueryFilter(field_id="depot", op="eq", value="Hà Nội"),
    ]
    validate_intents(IntentBatch(intents=[first]).model_dump_json(), [goals[0]], context)
    for changes in (
        {"filters": first.query.filters[:1]},
        {"filters": [*first.query.filters, QueryFilter(field_id="depot", op="ne", value="A")]},
        {
            "filters": [
                *first.query.filters[:1],
                QueryFilter(field_id="depot", op="contains", value="Hà Nội"),
            ]
        },
        {"source_measure_id": None, "aggregations": []},
        {"limit": 3},
    ):
        proposal = first.model_copy(update={"query": first.query.model_copy(update=changes)})
        with pytest.raises(DomainError, match="INPUT_AMBIGUOUS"):
            validate_intents(IntentBatch(intents=[proposal]).model_dump_json(), [goals[0]], context)

    context.previous_query = first.query
    reply = resolve_source_read('Còn chi nhánh "Đà Nẵng" thì sao?', context)
    assert reply and reply.query
    assert reply.query.filters == [
        first.query.filters[0],
        QueryFilter(field_id="depot", op="eq", value="Đà Nẵng"),
    ]
    top = resolve_source_read("Cho tôi Top 5 nhưng giữ bộ lọc ngày trước đó", context)
    assert top and top.query
    assert top.query.limit == 5 and top.query.filters == first.query.filters
    assert top.query.sort == [QuerySort(field_id="revenue", descending=True)]


def test_top_paginates_ties_by_business_key_then_source_row_then_id():
    fixture = source()
    assert fixture.definition
    fixture.definition.business_key_fields = ["order_reference"]
    fixture.frame = fixture.frame.with_columns(pl.lit(Decimal("10.01")).alias("revenue"))
    top = query(
        source_measure_id="revenue", sort=[QuerySort(field_id="revenue", descending=True)], limit=2
    )
    for frame in (fixture.frame, fixture.frame.reverse()):
        fixture.frame = frame
        first = execute_source_sql(top.model_copy(deep=True), fixture, monotonic() + 5)
        second = execute_source_sql(
            top.model_copy(update={"offset": 2}, deep=True), fixture, monotonic() + 5
        )
        assert [r["canonical_record_id"] for r in first.rows + second.rows] == [
            "r1",
            "r2",
            "r3",
            "r5",
        ]


def test_quality_reasons_count_source_rows_not_error_entries():
    fixture = source()
    assert fixture.definition
    fixture.definition.business_key_fields = ["order_reference"]
    fixture.frame = fixture.frame.with_columns(
        pl.Series(
            "source_provenance", [[{"row": i, "source_row_id": f"s{i}"}] for i in range(2, 7)]
        )
    )
    fixture.errors = pl.DataFrame(
        {
            "source_row_id": ["s5", "s5", "s5", "s5", "s4"],
            "field": ["revenue", "revenue", "event_date", "order_reference", "revenue"],
            "code": ["INVALID_DECIMAL", "INVALID_DECIMAL", "INVALID_DATE", "REQUIRED_NULL", "NULL"],
        }
    ).lazy()
    result = execute_source_sql(
        query(
            source_measure_id="revenue",
            aggregations=[QueryAggregation(op="sum_decimal", field_id="revenue")],
        ),
        fixture,
        monotonic() + 5,
    )
    evidence = result.source_evidence
    assert evidence and evidence.quality_counts
    assert evidence.invalid_rows == 1 and evidence.valid_rows == 4
    assert evidence.matching_rows == 4 and evidence.counted_rows == 3
    assert evidence.quality_counts.model_dump(exclude_defaults=True) == {
        "invalid_amount": 1,
        "invalid_date": 1,
        "missing_key": 1,
    }


def test_duckdb_memory_limit_fails_without_publishing_a_partial_total():
    from studio.contracts import SchemaField

    fixture = source()
    assert fixture.definition and fixture.canonical
    fixture.definition.fields = [SchemaField(id="note", name="Note", data_type="string")]
    fixture.fields = ["note"]
    rows = 30_000
    fixture.canonical.row_count = fixture.canonical.valid_count = rows
    fixture.canonical.invalid_count = 0
    fixture.frame = pl.DataFrame(
        {
            "canonical_record_id": [f"r{i}" for i in range(rows)],
            "source_provenance": [[{"row": i + 2}] for i in range(rows)],
            "invalid": [False] * rows,
            "note": [f"{i:06}" + "x" * 850 for i in range(rows)],
        }
    ).lazy()
    # Under the transfer cap, but the real in-memory SQL import can exceed 64 MB.
    with pytest.raises(DomainError, match="QUERY_MEMORY_LIMIT"):
        execute_source_sql(query(select_fields=["note"]), fixture, monotonic() + 5)
