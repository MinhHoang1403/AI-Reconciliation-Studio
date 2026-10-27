"""Meaningful boundary/lineage tests for every executable DSL operator."""

from decimal import Decimal

import polars as pl
import pytest
from studio.contracts import ApprovedTransformRule, MappingDecision, SchemaField, SourceColumn
from studio.errors import DomainError
from studio.normalization import apply_transform_plan
from studio.profiling import profile_table
from studio.schema_mapping import compile_transform_plan


def execute(frame, mapping, schema):
    columns = [
        SourceColumn(id=c, name=c, source_index=i + 1)
        for i, c in enumerate(frame.columns)
        if not c.startswith("_")
    ]
    profile = profile_table(frame, columns, "table", "workspace", "parsed")
    return apply_transform_plan(
        frame, compile_transform_plan(mapping, schema, profile), "version", "table", "file", "CSV"
    )


def test_trim_requires_explicit_approval(frame, mapping, schema):
    from studio.contracts import TrimTransform

    mapping.decisions = [mapping.decisions[0]]
    schema.fields = [schema.fields[0]]
    frame = frame.with_columns(pl.Series("c1", [" 000123 ", "000124", "000125", "000126"]))
    mapping.decisions[0].transformation_candidate = TrimTransform(
        op="trim_if_approved", approved=True
    )
    result = execute(frame, mapping, schema)
    assert result.canonical["record_payload"].to_list()[0]["reference_id"] == "000123"
    assert frame["c1"][0] == " 000123 "


@pytest.mark.parametrize(
    "operation,expected", [("add_fields", Decimal("12.30")), ("subtract_fields", Decimal("7.70"))]
)
def test_arithmetic_exact_rule_and_null(operation, expected, mapping, schema):
    frame = pl.DataFrame(
        {
            "c1": ["10.00", None],
            "c2": ["2.30", "2.30"],
            "_source_row": [2, 3],
            "_source_row_id": ["r1", "r2"],
        }
    )
    schema.business_key_fields = []
    schema.fields = [schema.fields[1]]
    mapping.decisions = [
        MappingDecision.model_validate(
            {
                "source_field": "c1",
                "candidate_target": "amount",
                "decision": "APPROVED",
                "evidence_ids": ["table:c1"],
                "grain_assumption": schema.grain,
                "transformation_candidate": {
                    "op": operation,
                    "fields": ["c1", "c2"],
                    "locale": "en-US",
                    "rule_id": "arithmetic",
                },
            }
        )
    ]
    mapping.rules = [
        ApprovedTransformRule(
            id="arithmetic",
            operation=operation,
            fields=["c1", "c2"],
            metric="synthetic_gross",
            currency="VND",
            unit="VND",
            approved_by="owner",
            evidence_ids=["table:c1", "table:c2"],
        )
    ]
    result = execute(frame, mapping, schema)
    assert result.canonical["record_payload"].to_list()[0]["amount"] == expected
    assert result.canonical["record_payload"].to_list()[1]["amount"] is None
    assert result.errors["code"].to_list() == ["ARITHMETIC_NULL"]


def test_enum_and_coalesce_preserve_empty_and_unknown(mapping, schema):
    frame = pl.DataFrame(
        {
            "c1": ["a", "x", None, ""],
            "c2": ["fallback", "fallback", "fallback", "fallback"],
            "_source_row": [2, 3, 4, 5],
            "_source_row_id": ["r1", "r2", "r3", "r4"],
        }
    )
    schema.fields = [
        SchemaField(id="status", name="Status", data_type="enum"),
        SchemaField(id="description", name="Description", data_type="string"),
    ]
    schema.business_key_fields = []
    mapping.decisions = [
        MappingDecision.model_validate(
            {
                "source_field": "c1",
                "candidate_target": "status",
                "decision": "APPROVED",
                "evidence_ids": ["table:c1"],
                "grain_assumption": schema.grain,
                "transformation_candidate": {"op": "normalize_enum", "mapping_id": "enum"},
            }
        ),
        MappingDecision.model_validate(
            {
                "source_field": "c2",
                "candidate_target": "description",
                "decision": "APPROVED",
                "evidence_ids": ["table:c2"],
                "grain_assumption": schema.grain,
                "transformation_candidate": {
                    "op": "coalesce_with_rule",
                    "fields": ["c1", "c2"],
                    "rule_id": "coalesce",
                },
            }
        ),
    ]
    mapping.rules = [
        ApprovedTransformRule(
            id="enum",
            operation="normalize_enum",
            fields=["c1"],
            enum_values={"a": "approved", "": "empty"},
            approved_by="owner",
            evidence_ids=["table:c1"],
        ),
        ApprovedTransformRule(
            id="coalesce",
            operation="coalesce_with_rule",
            fields=["c1", "c2"],
            approved_by="owner",
            evidence_ids=["table:c1", "table:c2"],
        ),
    ]
    result = execute(frame, mapping, schema)
    values = result.canonical["record_payload"].to_list()
    assert values[0]["status"] == "approved"
    assert values[1]["status"] is None
    assert values[2]["description"] == "fallback"
    assert values[3]["description"] == ""
    assert "UNKNOWN_ENUM" in result.errors["code"].to_list()


def test_date_confirmed_timezone_and_dst_rejected(mapping, schema):
    from studio.contracts import DateTransform

    frame = pl.DataFrame(
        {
            "c1": ["2026-10-01 00:00", "2026-11-01 01:30"],
            "_source_row": [2, 3],
            "_source_row_id": ["r1", "r2"],
        }
    )
    schema.fields = [SchemaField(id="event_date", name="Date", data_type="date")]
    schema.business_key_fields = []
    mapping.decisions = [mapping.decisions[0]]
    mapping.decisions[0].candidate_target = "event_date"
    mapping.decisions[0].transformation_candidate = DateTransform(
        op="parse_date", format="%Y-%m-%d %H:%M", timezone="America/New_York"
    )
    result = execute(frame, mapping, schema)
    assert (
        result.canonical["record_payload"].to_list()[0]["event_date"].isoformat()
        == "2026-10-01T04:00:00+00:00"
    )
    assert result.errors["code"].to_list() == ["INVALID_DATE"]


def test_aggregate_keeps_all_lineage_and_signed_decimal(mapping, schema):
    from studio.contracts import AggregateTransform

    frame = pl.DataFrame(
        {
            "c1": ["001", "001", "002"],
            "c2": ["10.50", "-2.25", "5"],
            "_source_row": [2, 3, 4],
            "_source_row_id": ["r1", "r2", "r3"],
        }
    )
    schema.grain = "one reference total"
    for decision in mapping.decisions:
        decision.grain_assumption = schema.grain
    mapping.decisions[1].transformation_candidate = AggregateTransform(
        op="aggregate_by",
        keys=["reference_id"],
        metric="synthetic_gross",
        rule_id="sum",
        locale="en-US",
    )
    mapping.rules = [
        ApprovedTransformRule(
            id="sum",
            operation="aggregate_by",
            fields=["c2"],
            metric="synthetic_gross",
            currency="VND",
            unit="VND",
            grain=schema.grain,
            approved_by="owner",
            evidence_ids=["table:c1", "table:c2"],
        )
    ]
    result = execute(frame, mapping, schema)
    rows = result.canonical.to_dicts()
    assert len(rows) == 2
    assert rows[0]["record_payload"]["amount"] == Decimal("8.25")
    assert [p["source_row_id"] for p in rows[0]["source_provenance"]] == ["r1", "r2"]
    assert sum(len(r["source_provenance"]) for r in rows) == 3
    schema.fields[1].currency = "USD"
    with pytest.raises(DomainError, match="AGGREGATE_SEMANTICS_REQUIRED"):
        execute(frame, mapping, schema)
