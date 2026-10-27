from decimal import Decimal

import polars as pl
import pytest
from hypothesis import given
from hypothesis import strategies as st
from studio.contracts import MappingRevision, SchemaProposal
from studio.errors import DomainError
from studio.normalization import apply_transform_plan, parse_decimal
from studio.schema_mapping import compile_transform_plan, validate_mapping


def test_T10_total_is_ambiguous(profile, schema, mapping):
    decisions = [d.model_copy(update={"decision": "PROPOSED"}) for d in mapping.decisions]
    proposal = SchemaProposal(
        entity_kind="unknown", grain="unknown", status="PROPOSED", decisions=decisions
    )
    result = validate_mapping(proposal, profile, schema)
    assert result.decisions[1].decision == "AMBIGUOUS"


def test_T11_type_and_approval_gate(profile, schema, mapping):
    mapping.status = "PROPOSED"
    with pytest.raises(DomainError, match="MAPPING_NOT_APPROVED"):
        compile_transform_plan(mapping, schema, profile)


@pytest.mark.parametrize("unknown", ["", "  ", "UNKNOWN", " ambiguous "])
def test_unknown_currency_cannot_be_approved(unknown, profile, schema, mapping):
    schema.fields[1].currency = unknown
    with pytest.raises(DomainError, match="MONETARY_SEMANTICS_REQUIRED"):
        compile_transform_plan(mapping, schema, profile)


def test_currency_column_cannot_contradict_approved_amount(frame, schema, mapping):
    from studio.contracts import MappingDecision, SchemaField, SourceColumn
    from studio.profiling import profile_table

    frame = frame.with_columns(pl.Series("c3", ["USD", "VND", "VND", "VND"]))
    schema.fields.append(SchemaField(id="currency", name="Currency", data_type="string"))
    mapping.decisions.append(
        MappingDecision.model_validate(
            {
                "source_field": "c3",
                "candidate_target": "currency",
                "decision": "APPROVED",
                "evidence_ids": ["table:c3"],
                "grain_assumption": schema.grain,
                "transformation_candidate": {"op": "cast_string_preserve"},
            }
        )
    )
    profile = profile_table(
        frame,
        [SourceColumn(id=c, name=c, source_index=i + 1) for i, c in enumerate(["c1", "c2", "c3"])],
        "table",
        "workspace",
        "parsed",
    )
    result = apply_transform_plan(
        frame, compile_transform_plan(mapping, schema, profile), "version", "table", "file", "CSV"
    )
    assert result.quality_status == "PARTIAL"
    assert result.canonical["record_payload"].to_list()[0]["amount"] == Decimal("1234.50")
    assert "CURRENCY_MISMATCH" in result.errors["code"].to_list()


def test_T15_T16_exact_decimal_errors_null_and_lineage(frame, profile, schema, mapping):
    plan = compile_transform_plan(mapping, schema, profile)
    result = apply_transform_plan(frame, plan, "version", "table", "file", "CSV")
    rows = result.canonical.to_dicts()
    assert [r["record_payload"]["amount"] for r in rows] == [
        Decimal("1234.50"),
        None,
        None,
        Decimal("0"),
    ]
    assert rows[0]["record_payload"]["reference_id"] == "000123"
    assert rows[0]["source_provenance"][0]["row"] == 2
    assert result.quality_status == "PARTIAL"
    assert (result.row_count, result.valid_count, result.invalid_count) == (4, 2, 2)
    assert result.errors["value_state"].to_list() == ["INVALID", "NULL"]
    assert result.errors["raw_value"].to_list() == ["invalid", None]
    assert frame["c2"].to_list() == ["1.234,50", "invalid", None, "0"]
    assert result.canonical.schema["record_payload"].fields[1].dtype == pl.Decimal(38, 2)


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "1e3", "1.23,45", " 1,00", "1,000.00", "--1"])
def test_decimal_rejects_invalid_locale(raw):
    with pytest.raises(DomainError):
        parse_decimal(raw, "vi-VN")


@given(st.integers(min_value=-(10**20), max_value=10**20))
def test_decimal_integer_property(value):
    assert parse_decimal(str(value), "en-US") == Decimal(value)


def test_zero_null_invalid_are_distinct():
    assert parse_decimal("0", "en-US") == Decimal(0)
    assert parse_decimal(None, "en-US") is None
    assert parse_decimal("", "en-US") is None
    with pytest.raises(DomainError):
        parse_decimal("oops", "en-US")


def test_canonical_without_business_keys_parquet_roundtrip(
    frame, profile, schema, mapping, tmp_path
):
    # Regression: an empty struct cannot be written to Parquet. Empty typed key
    # components are valid at data foundation; reconciliation readiness checks later.
    schema.business_key_fields = []
    plan = compile_transform_plan(mapping, schema, profile)
    result = apply_transform_plan(frame, plan, "version", "table", "file", "CSV")
    path = tmp_path / "canonical.parquet"
    result.canonical.write_parquet(path)
    restored = pl.read_parquet(path)
    assert restored["business_key_components"].to_list() == [[], [], [], []]
    assert restored["record_payload"].to_list()[0]["amount"] == Decimal("1234.50")


def test_transform_unknown_rule_blocked(mapping, schema, profile):
    from studio.contracts import CoalesceTransform

    mapping.decisions[0].transformation_candidate = CoalesceTransform.model_validate(
        {
            "op": "coalesce_with_rule",
            "fields": ["c1"],
            "rule_id": "fake",
        }
    )
    # Assignment cannot bypass typed contracts at module/API boundaries.

    typed = MappingRevision.model_validate_json(mapping.model_dump_json())
    with pytest.raises(DomainError, match="TRANSFORM_RULE_UNAPPROVED"):
        compile_transform_plan(typed, schema, profile)
