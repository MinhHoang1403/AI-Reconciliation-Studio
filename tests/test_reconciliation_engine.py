import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from reconciliation_cases import FIXTURES, plan, records
from studio.contracts.reconciliation import CanonicalRecord, FieldPair
from studio.reconciliation_engine import match_records
from studio.verification import calculate_metric_snapshot, verify_result


def by_key(result, key, side="left"):
    return [g for g in result.groups if g.key[-1] == key and any(m.side == side for m in g.members)]


@pytest.mark.parametrize("timezone", ["UTC", "Asia/Ho_Chi_Minh", "America/New_York"])
def test_calendar_days_keep_period_boundaries_in_any_zone(timezone):
    rule = plan(
        left="left",
        right="right",
        entity="sale",
        platform="",
        keys=["order_id"],
        amount="amount",
        metric="revenue",
    )
    rule.timezone = timezone
    sides = [
        [
            CanonicalRecord(
                id=f"{side}-{index}",
                invalid=False,
                quality_flags=[],
                payload={
                    "order_id": str(index),
                    "event_date": day,
                    "currency": "VND",
                    "amount": Decimal("-25"),
                },
                provenance=[
                    dict(
                        file_id=side,
                        source_table_id=side,
                        source_row_id=str(index),
                        sheet="CSV",
                        row=index + 2,
                    )
                ],
            )
            for index, day in enumerate(
                [rule.period_start, rule.period_end - timedelta(days=1), rule.period_end]
            )
        ]
        for side in ("left", "right")
    ]
    result = match_records(rule, *sides)
    assert result.partition_counts["left"] == {"INVALID": 0, "IN_SCOPE": 2, "OUT_OF_SCOPE": 1}
    assert all(check.passed for check in verify_result(rule, *sides, result))


def test_refund_batch_tolerance_and_currency_have_independent_signed_oracle():
    inputs = [
        ("0001", "-25.01", "-25.00", "VND"),
        ("0002", "-50.00", "-48.97", "VND"),
        ("0003", "-9.10", "-9.10", "USD"),
    ]
    sides = []
    for side in ("left", "right"):
        sides.append(
            [
                CanonicalRecord(
                    id=f"{side}-{key}",
                    invalid=False,
                    quality_flags=[],
                    payload={
                        "refund_id": key,
                        "event_date": datetime(2026, 10, 15, tzinfo=UTC),
                        "currency": "VND" if side == "left" else currency,
                        "amount": Decimal(left if side == "left" else right),
                    },
                    provenance=[
                        dict(
                            file_id=side,
                            source_table_id=side,
                            source_row_id=f"{side}-{key}",
                            sheet="Refunds",
                            row=index + 2,
                        )
                    ],
                )
                for index, (key, left, right, currency) in enumerate(inputs)
            ]
        )
    rule = plan(
        left="left",
        right="right",
        entity="refund",
        platform="",
        keys=["refund_id"],
        amount="amount",
        metric="signed_refund",
    )
    rule.comparison_metrics[0].absolute_tolerance = Decimal("0.01")
    result = match_records(rule, *sides)
    expected = {
        "0001": ("WITHIN_TOLERANCE", Decimal("-0.01")),
        "0002": ("AMOUNT_MISMATCH", Decimal("-1.03")),
        "0003": ("NOT_COMPARABLE", None),
    }
    for key, (state, delta) in expected.items():
        [group] = by_key(result, key)
        assert group.linkage_state == "LINKED"
        assert group.comparison_state == state and group.comparisons[0].delta == delta
        assert {member.record_id for member in group.members} == {f"left-{key}", f"right-{key}"}
    assert all(check.passed for check in verify_result(rule, *sides, result))
    [amounts] = calculate_metric_snapshot("run", "rule", 1, rule, *sides, result).monetary
    assert amounts.currency == "VND" and amounts.comparable_groups == 2
    assert amounts.signed_variance == Decimal("-1.04")
    assert amounts.absolute_variance == Decimal("1.04")


@pytest.mark.parametrize(
    "entity,left_key,right_key,cardinality,left_values,right_values,delta",
    [
        ("invoice", "invoice_no", "document_no", "ONE_TO_ONE", ["125.10"], ["124.80"], "0.30"),
        ("refund", "refund_ref", "original_ref", "ONE_TO_ONE", ["-50.25"], ["-49.25"], "-1.00"),
        ("receivable", "invoice_ref", "payment_ref", "ONE_TO_MANY", ["75"], ["52", "24"], "-1"),
        (
            "stock_value",
            "item_code",
            "warehouse_sku",
            "MANY_TO_ONE",
            ["8.75", "12.50"],
            ["20.00"],
            "1.25",
        ),
    ],
)
def test_unseen_business_cases_keep_signed_money_and_lineage(
    entity, left_key, right_key, cardinality, left_values, right_values, delta
):
    def source(side, field, values):
        return [
            CanonicalRecord.model_validate(
                {
                    "id": f"{side}-{i}",
                    "payload": {
                        field: "00042",
                        "event_date": datetime(2026, 10, 15, tzinfo=UTC),
                        "currency": "VND",
                        "amount": Decimal(value),
                    },
                    "invalid": False,
                    "quality_flags": [],
                    "provenance": [
                        dict(
                            file_id=side,
                            source_table_id=side,
                            source_row_id=f"{side}-{i}",
                            sheet="Report",
                            row=i + 2,
                        )
                    ],
                }
            )
            for i, value in enumerate(values)
        ]

    left = source("left", left_key, left_values)
    right = source("right", right_key, right_values)
    p = plan(
        left="left",
        right="right",
        platform="",
        entity=entity,
        cardinality=cardinality,
        keys=[left_key],
        amount="amount",
        metric=entity + "_amount",
    )
    p.join_keys = [FieldPair(left=left_key, right=right_key)]
    result = match_records(p, left, right)
    [group] = result.groups
    assert group.key == ["00042"]
    assert group.linkage_state == "LINKED" and group.comparison_state == "AMOUNT_MISMATCH"
    [amounts] = group.comparisons
    assert amounts.delta == Decimal(delta)
    assert amounts.absolute_variance == abs(Decimal(delta))
    assert {m.record_id for m in group.members} == {r.id for r in [*left, *right]}
    assert all(c.passed for c in verify_result(p, left, right, result))


def test_T21_T22_T23_T24_ecommerce_independent_oracle():
    left, right = records("internal-sales.csv"), records("shopee-orders.csv")
    p = plan()
    result = match_records(p, left, right)
    oracle = json.loads((FIXTURES / "reconciliation-oracle.json").read_text())["shopee"]
    assert result.partition_counts["left"] == {"INVALID": 1, "OUT_OF_SCOPE": 5, "IN_SCOPE": 5}
    for key in oracle["equal"]:
        assert by_key(result, key)[0].comparison_state == "EQUAL"
    group = by_key(result, "0002")[0]
    assert group.linkage_state == "LINKED" and group.comparison_state == "AMOUNT_MISMATCH"
    assert group.comparisons[0].delta == Decimal("10.00")
    assert by_key(result, "0007")[0].linkage_state == "AMBIGUOUS"
    assert by_key(result, "0004")[0].linkage_state == "UNMATCHED"
    checks = verify_result(p, left, right, result)
    assert checks and all(c.passed for c in checks)


def test_T25_T26_T30_group_null_refund_and_many_to_one():
    left, right = records("internal-sales.csv"), records("tiktok-order-lines.csv")
    p = plan(right="tiktok", cardinality="ONE_TO_MANY", platform="TikTok")
    result = match_records(p, left, right)
    group = by_key(result, "0005")[0]
    assert len([m for m in group.members if m.side == "right"]) == 2
    assert group.comparisons[0].left_amount == group.comparisons[0].right_amount == Decimal("50")
    assert group.comparison_state == "EQUAL"
    assert by_key(result, "0008")[0].comparison_state == "NOT_COMPARABLE"
    right[2].payload["currency"] = "USD"
    mixed = match_records(p, left, right)
    assert by_key(mixed, "0005")[0].comparison_state == "NOT_COMPARABLE"
    assert by_key(mixed, "0005")[0].comparisons[0].delta is None
    p = plan(left="tiktok", right="internal", cardinality="MANY_TO_ONE", platform="TikTok")
    p.right.filters = {"platform": "TikTok"}
    right[2].payload["currency"] = "VND"
    inverse = match_records(p, right, left)
    assert by_key(inverse, "0005")[0].comparison_state == "EQUAL"
    assert all(c.passed for c in verify_result(p, right, left, inverse))


@pytest.mark.parametrize(
    "delta,state", [("0", "EQUAL"), ("1", "WITHIN_TOLERANCE"), ("1.0001", "AMOUNT_MISMATCH")]
)
def test_T29_exact_tolerance_boundary(delta, state):
    left, right = records("internal-sales.csv")[:1], records("shopee-orders.csv")[:1]
    right[0].payload["gross_amount"] = Decimal("100") - Decimal(delta)
    p = plan()
    p.comparison_metrics[0].absolute_tolerance = Decimal("1")
    result = match_records(p, left, right)
    assert result.groups[0].comparison_state == state
    assert all(c.passed for c in verify_result(p, left, right, result))


def test_T19_cutoff_coverage_and_settlement_not_confirmed_missing():
    left, right = records("internal-sales.csv"), records("shopee-orders.csv")
    p = plan()
    p.right.completeness, p.allow_partial = "INCOMPLETE", True
    result = match_records(p, left, right)
    assert by_key(result, "0010")[0].linkage_state == "OUT_OF_SCOPE"
    assert by_key(result, "0004")[0].linkage_state == "PENDING"
    assert "MISSING_COUNTERPART" not in by_key(result, "0004")[0].exception_types
    p.right.settlement_due_at = p.right.snapshot_at.replace(year=2027)
    result = match_records(p, left, right)
    assert "NOT_YET_SETTLED" in by_key(result, "0004")[0].exception_types


def test_T27_T28_fuzzy_review_only_and_no_greedy_reuse():
    left, right = records("internal-sales.csv")[:2], records("shopee-orders.csv")[:2]
    for row in right:
        row.payload["order_id"] = "DIFFERENT-" + row.payload["order_id"]
    for row in [*left, *right]:
        row.payload["description"] = "Same parcel name"
    p = plan()
    p.fuzzy_fields = [FieldPair(left="description", right="description")]
    p.fuzzy_block_keys = [FieldPair(left="shop_id", right="shop_id")]
    result = match_records(p, left, right)
    assert all(g.linkage_state == "AMBIGUOUS" for g in result.groups)
    assert all(len(g.members) == 1 for g in result.groups)
    assert all(c.status == "REVIEW_ONLY" for g in result.groups for c in g.candidates)
    assert all(c.passed for c in verify_result(p, left, right, result))


def test_T31_T32_verifier_rejects_reused_member_or_corrupted_amount():
    left, right = records("internal-sales.csv"), records("shopee-orders.csv")
    p = plan()
    good = match_records(p, left, right)
    bad = good.model_copy(deep=True)
    bad.groups[1].members.append(bad.groups[0].members[0])
    assert not all(c.passed for c in verify_result(p, left, right, bad))
    bad = good.model_copy(deep=True)
    group = by_key(bad, "0002")[0]
    group.comparisons[0].left_amount = Decimal("999999")
    assert not all(c.passed for c in verify_result(p, left, right, bad))


def test_other_domain_oracle_and_zero_prefix():
    left, right = records("shipments.csv"), records("delivery-confirmations.csv")
    p = plan(
        left="shipments",
        right="delivery",
        platform="",
        amount="delivery_charge",
        metric="delivery_charge",
        keys=["carrier", "tracking_id"],
        entity="delivery",
    )
    result = match_records(p, left, right)
    assert by_key(result, "000701")[0].comparison_state == "EQUAL"
    assert by_key(result, "000702")[0].comparisons[0].delta == Decimal("2.75")
    assert by_key(result, "000703")[0].linkage_state == "UNMATCHED"
    assert all(c.passed for c in verify_result(p, left, right, result))


def test_relative_tolerance_rounding_and_timezone_manual_oracles():
    from datetime import datetime

    left, right = records("internal-sales.csv")[:1], records("shopee-orders.csv")[:1]
    p = plan()
    p.comparison_metrics[0].relative_tolerance = Decimal("0.01")
    right[0].payload["gross_amount"] = Decimal("99")
    result = match_records(p, left, right)
    assert result.groups[0].comparison_state == "WITHIN_TOLERANCE"
    assert result.groups[0].comparisons[0].tolerance == Decimal("1")
    assert all(c.passed for c in verify_result(p, left, right, result))
    p.comparison_metrics[0].relative_tolerance = None
    p.comparison_metrics[0].rounding_scale = 2
    left[0].payload["gross_amount"], right[0].payload["gross_amount"] = (
        Decimal("1.005"),
        Decimal("1.00"),
    )
    for mode, state, expected in (
        ("HALF_EVEN", "EQUAL", "0.00"),
        ("HALF_UP", "AMOUNT_MISMATCH", "0.01"),
    ):
        p.comparison_metrics[0].rounding_mode = mode
        result = match_records(p, left, right)
        assert result.groups[0].comparison_state == state
        assert result.groups[0].comparisons[0].delta == Decimal(expected)
        assert all(c.passed for c in verify_result(p, left, right, result))
    p.timezone = "Asia/Ho_Chi_Minh"
    for stamp, expected in (
        ("2026-10-30T16:59:59+00:00", "LINKED"),
        ("2026-10-30T17:00:00+00:00", "OUT_OF_SCOPE"),
    ):
        for row in left + right:
            row.payload["event_date"] = datetime.fromisoformat(stamp)
        result = match_records(p, left, right)
        assert all(g.linkage_state == expected for g in result.groups)
        assert all(c.passed for c in verify_result(p, left, right, result))


@settings(max_examples=25, deadline=None)
@given(st.permutations(range(11)), st.permutations(range(6)))
def test_property_permutations_membership_and_determinism(left_order, right_order):
    left, right = records("internal-sales.csv"), records("shopee-orders.csv")
    expected = match_records(plan(), left, right)
    result = match_records(plan(), [left[i] for i in left_order], [right[i] for i in right_order])
    assert result == expected
    members = [(m.side, m.record_id) for g in result.groups for m in g.members]
    assert len(members) == len(set(members)) == 17
    assert all(c.passed for c in verify_result(plan(), left, right, result))


@settings(max_examples=40, deadline=None)
@given(st.integers(-10000000, 10000000), st.integers(-10000000, 10000000))
def test_amount_sign_metamorphism_preserves_linkage_and_absolute_variance(left_cents, right_cents):
    """Independent integer-cent oracle; exact linkage must not depend on amounts."""
    left, right = records("internal-sales.csv")[:1], records("shopee-orders.csv")[:1]
    expected = Decimal(left_cents - right_cents) / 100
    for sign in (1, -1):
        left[0].payload["gross_amount"] = Decimal(sign * left_cents) / 100
        right[0].payload["gross_amount"] = Decimal(sign * right_cents) / 100
        result = match_records(plan(), left, right)
        group = result.groups[0]
        assert group.linkage_state == "LINKED"
        assert group.comparisons[0].delta == sign * expected
        assert group.comparisons[0].absolute_variance == abs(expected)
        assert group.comparison_state == ("EQUAL" if not expected else "AMOUNT_MISMATCH")
        assert all(c.passed for c in verify_result(plan(), left, right, result))
