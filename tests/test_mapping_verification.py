"""Ngày và kiểm chứng mapping: oracle độc lập, không gọi model."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import polars as pl
import pytest
from studio.contracts import SourceColumn
from studio.contracts.agent import NormalizationDraft, NormalizationField
from studio.date_parsing import date_format, date_zone, parse_date
from studio.errors import DomainError
from studio.mapping_verification import assess_mapping
from studio.profiling import profile_table


@pytest.mark.parametrize(
    "incoming,compatible",
    [
        ("thanh_toan_2026_11.xlsx", True),
        ("thanh_toan_2027_01.xlsx", True),
        ("thanh_toan_2026_13.xlsx", False),
        ("thanh_toan_2026_11.csv", False),
        ("chi_phi_2026_11.xlsx", False),
        ("thanh_toan_11.xlsx", False),
        ("thanh_toan_2026_11_2026_12.xlsx", False),
    ],
)
def test_reuse_report_month_is_not_an_arbitrary_filename_wildcard(incoming, compatible):
    from studio.mapping_reuse import report_name_identity

    assert (
        report_name_identity("thanh_toan_2026_10.xlsx") == report_name_identity(incoming)
    ) == compatible


@pytest.mark.parametrize(
    "headers,rows,expected",
    [
        (["Paid Amount", "Order ID"], [["12.75", "0001"]], {"c1": "c2", "c2": "c1"}),
        (["order_id", "paid_amount"], [["0001", "12.75"]], {"c1": "c1", "c2": "c2"}),
        (
            ["Order ID", "Paid Amount", "Ghi chú"],
            [["0001", "12.75", "Đã kiểm"]],
            {"c1": "c1", "c2": "c2"},
        ),
        (["Order ID", "Paid Amount", "Net Amount"], [["0001", "12.75", "12.75"]], None),
        (["Order ID", "Net Amount"], [["0001", "12.75"]], None),
        (["Customer ID", "Paid Amount"], [["0001", "12.75"]], None),
        (["Order ID", "Paid Amount", "order_id"], [["0001", "12.75", "0002"]], None),
        (["Order ID", "Paid Amount", "Notes"], [["0001", "12.75", "VND"]], None),
        (["Order ID", "Paid Amount", "Notes"], [["0001", "12.75", "2026-11-01"]], None),
        (["Order ID", "Paid Amount", "Notes"], [["0001", "12.75", "123.50"]], None),
        (["Order ID", "Paid Amount"], [["0001", "invalid"]], None),
        (["Order ID"], [["0001"]], None),
    ],
)
def test_reuse_binds_headers_but_abstains_on_semantic_and_structural_drift(headers, rows, expected):
    from studio.mapping_reuse import compatible_column_bindings

    def profile(names, values, table_id):
        ids = [f"c{i}" for i in range(1, len(names) + 1)]
        return profile_table(
            pl.DataFrame(values, schema=ids, orient="row"),
            [
                SourceColumn(id=key, name=name, source_index=i)
                for i, (key, name) in enumerate(zip(ids, names, strict=True))
            ],
            table_id,
            "test",
            "artifact",
        )

    original = profile(["Order ID", "Paid Amount"], [["0001", "12.75"]], "source")
    incoming = profile(headers, rows, "incoming")
    assert compatible_column_bindings(original, incoming) == expected


@pytest.mark.parametrize(
    "raw,fmt,expected",
    [
        ("2026-10-10", "%Y-%m-%d", "2026-10-10"),
        ("2026-10-31", "YYYY-MM-DD", "2026-10-31"),
        ("31/10/2026", "DD/MM/YYYY", "2026-10-31"),
        ("10/31/2026", "%m/%d/%Y", "2026-10-31"),
    ],
)
@pytest.mark.parametrize("zone", ["UTC", "Asia/Ho_Chi_Minh"])
def test_dates_keep_calendar_in_approved_zone(raw, fmt, expected, zone):
    value = parse_date(raw, fmt, zone)
    assert value.astimezone(ZoneInfo(zone)).date().isoformat() == expected
    assert value.tzinfo == UTC


@pytest.mark.parametrize("raw", [None, ""])
def test_date_null_stays_absent(raw):
    assert parse_date(raw, "%Y-%m-%d", "UTC") is None


@pytest.mark.parametrize(
    "raw,fmt,zone,code",
    [
        ("2026-02-30", "%Y-%m-%d", "UTC", "INVALID_DATE"),
        ("2026-10-10", "%d/%m/%Y", "UTC", "INVALID_DATE"),
        ("2026-11-01 01:30", "%Y-%m-%d %H:%M", "America/New_York", "AMBIGUOUS_LOCAL_TIME"),
        ("2026-03-08 02:30", "%Y-%m-%d %H:%M", "America/New_York", "NONEXISTENT_LOCAL_TIME"),
        ("2026-10-10", "nonsense", "UTC", "DATE_FORMAT_INVALID"),
        ("2026-10-10", "%Y-%m-%d", "Not/AZone", "TIMEZONE_INVALID"),
        (
            "2026-10-10T10:30:00+03:00",
            "%Y-%m-%dT%H:%M:%S%z",
            "Asia/Ho_Chi_Minh",
            "DATE_OFFSET_MISMATCH",
        ),
    ],
)
def test_date_data_and_configuration_errors_are_distinct(raw, fmt, zone, code):
    with pytest.raises(DomainError, match=code):
        parse_date(raw, fmt, zone)


def test_aware_and_naive_timestamps_agree_with_approved_zone():
    assert parse_date(
        "2026-10-10T10:30:00+07:00", "%Y-%m-%dT%H:%M:%S%z", "Asia/Ho_Chi_Minh"
    ) == datetime(2026, 10, 10, 3, 30, tzinfo=UTC)
    assert parse_date("2026-10-10 10:30:00", "%Y-%m-%d %H:%M:%S", "Asia/Ho_Chi_Minh") == datetime(
        2026, 10, 10, 3, 30, tzinfo=UTC
    )


def test_missing_iana_database_is_runtime_not_invalid_date(monkeypatch):
    from zoneinfo import ZoneInfoNotFoundError

    from studio import date_parsing

    date_zone.cache_clear()

    def missing(value):
        raise ZoneInfoNotFoundError(value)

    monkeypatch.setattr(date_parsing, "ZoneInfo", missing)
    monkeypatch.setattr(date_parsing, "available_timezones", lambda: set())
    with pytest.raises(DomainError, match="TIMEZONE_DATABASE_UNAVAILABLE"):
        parse_date("2026-10-10", "%Y-%m-%d", "UTC")
    date_zone.cache_clear()


def sample():
    frame = pl.DataFrame(
        {
            "c1": ["2026-10-10", "2026-10-31", "2026-02-30"],
            "c2": ["1.25", "-2.50", "0"],
            "c3": ["VND", "VND", "USD"],
            "c4": ["0001", "0001", "0002"],
            "_source_row": [2, 3, 4],
            "_source_row_id": ["r1", "r2", "r3"],
        }
    )
    profile = profile_table(
        frame,
        [
            SourceColumn(id=f"c{i}", name=n, source_index=i)
            for i, n in enumerate(["event_date", "amount", "currency", "customer_code"], 1)
        ],
        "t",
        "w",
        "a",
    )
    fields = [
        NormalizationField(
            source_field=c.column_id,
            target_id=c.name,
            name=c.name,
            data_type="date" if i == 0 else "decimal" if i == 1 else "string",
            business_key=i == 3,
        )
        for i, c in enumerate(profile.columns)
    ]
    fields[0].date_format = "YYYY-MM-DD"
    fields[0].timezone = "UTC"
    fields[1].semantic_metric = "reported_amount"
    fields[1].amount_basis = "gross"
    fields[1].currency = fields[1].unit = "VND"
    fields[1].locale = "en-US"
    return (
        frame,
        profile,
        NormalizationDraft(
            table_id="t", entity_kind="transaction", grain="one source transaction", fields=fields
        ),
    )


def test_full_column_enrichment_does_not_guess_timezone_currency_or_customer_key():
    frame, profile, draft = sample()
    result = assess_mapping(draft, frame, profile, "sha", enrich=True)
    assert result.draft.fields[0].date_format == "%Y-%m-%d"
    assert result.draft.fields[0].timezone is None
    assert result.draft.fields[1].locale == "en-US"
    assert result.draft.fields[1].currency is None
    assert result.draft.fields[1].amount_basis is None
    assert not result.draft.fields[3].business_key
    assert result.pending_fields == 2 and not result.preflight_ready
    assert draft.fields[0].date_format == "YYYY-MM-DD" and draft.fields[3].business_key


def test_preflight_matches_real_transform_without_artifact_publication():
    frame, profile, draft = sample()
    draft.fields[3].business_key = False
    result = assess_mapping(draft, frame, profile, "sha")
    assert result.preflight_ready and result.predicted_invalid_rows == 1
    assert result.error_counts == {"INVALID_DATE": 1, "CURRENCY_MISMATCH": 1}
    assert frame["c1"][0] == "2026-10-10"


def test_all_failed_date_draft_is_blocked_before_approval():
    frame, profile, draft = sample()
    draft.fields[0].date_format = "%d/%m/%Y"
    result = assess_mapping(draft, frame, profile, "sha")
    assert not result.preflight_ready
    assert result.checks[0].affected_rows == 3


@pytest.mark.parametrize("fmt", ["%Q", "%Y", "%Y-%m-%d%", "%Y-%Y-%m-%d"])
def test_invalid_format_is_configuration_error(fmt):
    with pytest.raises(DomainError, match="DATE_FORMAT_INVALID"):
        date_format(fmt)


@pytest.mark.parametrize(
    "values,expected", [(["1,234", "2,345", "3,456"], None), (["1", "-2", "0"], "en-US")]
)
def test_locale_ties_require_confirmation_unless_decimal_values_are_identical(values, expected):
    frame, profile, draft = sample()
    frame = frame.with_columns(pl.Series("c2", values))
    result = assess_mapping(draft, frame, profile, "sha", enrich=True)
    assert result.draft.fields[1].locale == expected


def test_relations_measure_composite_keys_without_customer_or_money_guess():
    from studio.mapping_verification import compare_key_candidates

    a = pl.DataFrame(
        {"a": ["MAIN", "EDGE", "MAIN"], "b": ["0001", "0001", "0002"], "c": ["C1", "C1", "C2"]}
    )
    b = pl.DataFrame(
        {"x": ["MAIN", "MAIN", "EDGE"], "y": ["0001", "0001", "0001"], "z": ["C1", "C1", "C1"]}
    )

    def profile(names):
        return {"columns": [{"column_id": id, "name": name} for id, name in names]}

    result = compare_key_candidates(
        a,
        profile([("a", "scope"), ("b", "reference"), ("c", "customer_code")]),
        b,
        profile([("x", "scope"), ("y", "reference"), ("z", "customer_code")]),
        "t",
        "Untrusted source",
    )
    assert len(result) == 1 and result[0].fields == ["scope", "reference"]
    assert result[0].shared_keys == 2 and result[0].right_duplicate_rows == 1


def test_invalid_rule_fails_before_any_row_transform(mapping, schema, profile, frame, monkeypatch):
    from studio import normalization
    from studio.contracts import DateTransform, SchemaField
    from studio.schema_mapping import TransformPlan

    schema.fields = [SchemaField(id="event_date", name="Date", data_type="date")]
    mapping.decisions = [
        mapping.decisions[0].model_copy(
            update={
                "candidate_target": "event_date",
                "transformation_candidate": DateTransform(
                    op="parse_date", format="INVALID", timezone="UTC"
                ),
            }
        )
    ]

    def no_row(*args):
        raise AssertionError("Runtime/config failure must be found before iterating rows")

    monkeypatch.setattr(normalization, "_transform", no_row)
    with pytest.raises(DomainError, match="DATE_FORMAT_INVALID"):
        normalization.apply_transform_plan(
            frame, TransformPlan(mapping, schema), "v", "t", "f", "CSV"
        )


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_real_parser_dates_and_lineage(extension, tmp_path, config, schema, mapping):
    import hashlib

    from openpyxl import Workbook
    from studio.contracts import DateTransform, SchemaField
    from studio.normalization import apply_transform_plan
    from studio.parsing import ParseConfig, inspect_upload, parse_to_artifacts
    from studio.schema_mapping import compile_transform_plan

    path = tmp_path / ("dates." + extension)
    if extension == "csv":
        path.write_text("date,id\n2026-10-10,0001\n2026-02-30,0002\n", encoding="utf-8")
    else:
        book = Workbook()
        book.active.append(["date", "id"])
        book.active.append(["2026-10-10", "0001"])
        book.active.append(["2026-02-30", "0002"])
        book.save(path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open("rb") as stream:
        inspected = inspect_upload(stream, path.name, "application/octet-stream", config)
    parsed = parse_to_artifacts(path, inspected, ParseConfig(), config)[0]
    parsed.frame = parsed.frame.with_columns(pl.Series("_source_row_id", ["r1", "r2"]))
    profile = profile_table(parsed.frame, parsed.columns, "table", "workspace", "artifact")
    schema.fields = [SchemaField(id="event_date", name="Date", data_type="date")]
    schema.business_key_fields = []
    mapping.decisions = [
        mapping.decisions[0].model_copy(
            update={
                "candidate_target": "event_date",
                "transformation_candidate": DateTransform(
                    op="parse_date", format="YYYY-MM-DD", timezone="UTC"
                ),
            }
        )
    ]
    result = apply_transform_plan(
        parsed.frame,
        compile_transform_plan(mapping, schema, profile),
        "version",
        "table",
        "file",
        parsed.sheet,
    )
    assert result.invalid_count == 1 and result.errors["code"].to_list() == ["INVALID_DATE"]
    assert result.canonical["record_payload"][0]["event_date"] == datetime(2026, 10, 10, tzinfo=UTC)
    assert result.canonical["source_provenance"][0][0]["row"] == 2
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_preflight_batches_check_every_row_and_count_invalid_once():
    frame, profile, draft = sample()
    n = 4001
    frame = pl.DataFrame(
        {
            "c1": ["2026-10-10"] * (n - 1) + ["2026-02-30"],
            "c2": ["1.25"] * n,
            "c3": ["VND"] * n,
            "c4": [str(i) for i in range(n)],
            "_source_row": list(range(2, n + 2)),
            "_source_row_id": ["row-" + str(i) for i in range(n)],
        }
    )
    draft.fields[3].business_key = False
    checked = assess_mapping(draft, frame, profile, "sha")
    assert checked.source_rows == 4001 and checked.predicted_invalid_rows == 1
    assert checked.error_counts == {"INVALID_DATE": 1}


def test_customer_key_requires_grain_evidence_even_without_enrichment():
    frame, profile, draft = sample()
    assert not assess_mapping(draft, frame, profile, "sha").preflight_ready
    draft.grain = "one customer per row"
    result = assess_mapping(draft, frame, profile, "sha", enrich=True)
    assert result.draft.fields[3].business_key
