"""Independent F23/F25 oracle over original typed canonical records.

No matcher functions or reported partition/amount totals are used as truth.
Reconstruct membership, scope, sums and comparisons before publishing one snapshot.
"""

import json
from collections import Counter, defaultdict
from datetime import datetime
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from rapidfuzz.distance import Indel

from studio.contracts.reconciliation import (
    CanonicalRecord,
    MatchResult,
    MetricSnapshot,
    MonetarySummary,
    RateMetric,
    ReconciliationPlan,
    SourceSelection,
    VerificationCheck,
)
from studio.errors import DomainError


def _complete(plan: ReconciliationPlan, slot: SourceSelection) -> bool:
    return not (
        slot.completeness != "CONFIRMED"
        or slot.coverage_start > plan.period_start
        or slot.coverage_end < plan.period_end
        or (slot.settlement_due_at is not None and slot.snapshot_at < slot.settlement_due_at)
    )


def verify_result(
    plan: ReconciliationPlan,
    left: list[CanonicalRecord],
    right: list[CanonicalRecord],
    result: MatchResult,
) -> list[VerificationCheck]:
    """Rebuild invariants independently; failures retain checks but grant no publication.

    The small oracle uses local dates, counted source identities and explicit
    Decimal loops, separately from the matcher's indexes/comparison implementation.
    """
    flags = dict.fromkeys(
        (
            "membership",
            "partition",
            "scope_keys",
            "cardinality",
            "amount_conservation",
            "comparison",
            "evidence",
            "determinism",
            "candidate_review",
        ),
        True,
    )
    sources = {"left": left, "right": right}
    lookup = {(s, r.id): r for s, rows in sources.items() for r in rows}
    flags["membership"] = len(lookup) == len(left) + len(right)
    for rows in sources.values():
        origins = [
            (p.file_id, p.source_table_id, p.source_row_id)
            for record in rows
            for p in record.provenance
        ]
        if len(origins) != len(set(origins)):
            flags["evidence"] = False
    partition: dict[tuple[str, str], str] = {}
    key_index: dict[str, dict[tuple[str | None, ...], set[str]]] = {
        "left": defaultdict(set),
        "right": defaultdict(set),
    }
    expected_counts: dict[str, dict[str, int]] = {}
    keys: dict[tuple[str, str], tuple[str | None, ...]] = {}
    zone = ZoneInfo(plan.timezone)
    for side, rows in sources.items():
        slot = plan.left if side == "left" else plan.right
        expected_counts[side] = dict.fromkeys(("INVALID", "OUT_OF_SCOPE", "IN_SCOPE"), 0)
        for record in rows:
            values = tuple(record.payload.get(getattr(pair, side)) for pair in plan.join_keys)
            keys[side, record.id] = tuple(str(v) if v is not None else None for v in values)
            stamp = record.payload.get(slot.date_field)
            valid_date = isinstance(stamp, datetime) and stamp.utcoffset() is not None
            if (
                record.invalid
                or not isinstance(stamp, datetime)
                or not valid_date
                or any(not isinstance(v, str) or v == "" for v in values)
            ):
                part = "INVALID"
            elif (
                any(record.payload.get(k) != v for k, v in slot.filters.items())
                or not plan.period_start <= stamp.astimezone(zone).date() < plan.period_end
            ):
                part = "OUT_OF_SCOPE"
            else:
                part = "IN_SCOPE"
                key_index[side][keys[side, record.id]].add(record.id)
            partition[side, record.id] = part
            expected_counts[side][part] += 1
    flags["partition"] = expected_counts == result.partition_counts
    seen: Counter[tuple[str, str]] = Counter()
    source_totals: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    member_totals: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    with localcontext() as context:
        context.prec = 100
        for side, rows in sources.items():
            slot = plan.left if side == "left" else plan.right
            for metric in plan.comparison_metrics:
                for record in rows:
                    amount = record.payload.get(getattr(metric, side))
                    if isinstance(amount, Decimal) and amount.is_finite():
                        currency = (
                            str(record.payload.get(slot.currency_field))
                            if slot.currency_field
                            else metric.currency
                        )
                        source_totals[side, metric.metric_id, currency] += amount
        for group in result.groups:
            owned: dict[str, list[CanonicalRecord]] = {"left": [], "right": []}
            for member in group.members:
                identity = member.side, member.record_id
                seen[identity] += 1
                source_record = lookup.get(identity)
                slot = plan.left if member.side == "left" else plan.right
                if source_record is None or member.canonical_id != slot.canonical_id:
                    flags["membership"] = False
                    continue
                owned[member.side].append(source_record)
                if member.evidence != source_record.provenance:
                    flags["evidence"] = False
                if group.key != list(keys[identity]):
                    flags["scope_keys"] = False
                part = partition[identity]
                if (
                    (part == "INVALID" and group.linkage_state != "INVALID")
                    or (part == "OUT_OF_SCOPE" and group.linkage_state != "OUT_OF_SCOPE")
                    or (part == "IN_SCOPE" and group.linkage_state in {"INVALID", "OUT_OF_SCOPE"})
                ):
                    flags["partition"] = False
                for metric in plan.comparison_metrics:
                    amount = source_record.payload.get(getattr(metric, member.side))
                    if isinstance(amount, Decimal) and amount.is_finite():
                        currency = (
                            str(source_record.payload.get(slot.currency_field))
                            if slot.currency_field
                            else metric.currency
                        )
                        member_totals[member.side, metric.metric_id, currency] += amount
            expected_id = str(
                uuid5(
                    NAMESPACE_URL,
                    json.dumps(
                        [
                            result.engine_revision,
                            [
                                (m.side, m.canonical_id, m.record_id)
                                for m in sorted(group.members, key=lambda m: (m.side, m.record_id))
                            ],
                        ]
                    ),
                )
            )
            if expected_id != group.id:
                flags["determinism"] = False
            if not all((m.side, m.record_id) in lookup for m in group.members):
                flags["comparison"] = False
                continue
            parts = {partition[m.side, m.record_id] for m in group.members}
            if len(parts) != 1:
                flags["partition"] = False
            if parts != {"IN_SCOPE"}:
                expected = "NOT_COMPARABLE" if parts == {"INVALID"} else "NOT_EVALUATED"
                if (
                    group.comparison_state != expected
                    or group.comparisons
                    or len(group.members) != 1
                ):
                    flags["comparison"] = False
                continue
            key = tuple(group.key)
            a, b = key_index["left"].get(key, set()), key_index["right"].get(key, set())
            conflict = (len(a) > 1 and plan.cardinality != "MANY_TO_ONE") or (
                len(b) > 1 and plan.cardinality != "ONE_TO_MANY"
            )
            if conflict:
                if (
                    group.linkage_state != "AMBIGUOUS"
                    or "DUPLICATE_KEY" not in group.exception_types
                ):
                    flags["cardinality"] = False
                for side, ids in (("left", a), ("right", b)):
                    allowed_many = (side == "left" and plan.cardinality == "MANY_TO_ONE") or (
                        side == "right" and plan.cardinality == "ONE_TO_MANY"
                    )
                    if owned[side] and allowed_many and {r.id for r in owned[side]} != ids:
                        flags["cardinality"] = False
            elif a and b:
                if (
                    group.linkage_state != "LINKED"
                    or {r.id for r in owned["left"]} != a
                    or {r.id for r in owned["right"]} != b
                ):
                    flags["cardinality"] = False
            else:
                for side, ids in (("left", a), ("right", b)):
                    if owned[side] and {r.id for r in owned[side]} != ids:
                        flags["cardinality"] = False
                opposite = plan.right if owned["left"] else plan.left
                expected_state = "UNMATCHED" if _complete(plan, opposite) else "PENDING"
                if group.candidates:
                    if group.linkage_state != "AMBIGUOUS" or not plan.fuzzy_fields:
                        flags["candidate_review"] = False
                elif group.linkage_state != expected_state:
                    flags["scope_keys"] = False
                required_issue = (
                    "MISSING_COUNTERPART"
                    if expected_state == "UNMATCHED"
                    else (
                        "NOT_YET_SETTLED"
                        if opposite.settlement_due_at is not None
                        and opposite.snapshot_at < opposite.settlement_due_at
                        else "INSUFFICIENT_COVERAGE"
                    )
                )
                if not group.candidates and required_issue not in group.exception_types:
                    flags["scope_keys"] = False
            if (plan.cardinality != "MANY_TO_ONE" and len(owned["left"]) > 1) or (
                plan.cardinality != "ONE_TO_MANY" and len(owned["right"]) > 1
            ):
                flags["cardinality"] = False
            for candidate in group.candidates:
                arow = lookup.get(("left", candidate.left_record_id))
                brow = lookup.get(("right", candidate.right_record_id))
                if (
                    arow is None
                    or brow is None
                    or candidate.status != "REVIEW_ONLY"
                    or candidate.field_pairs != plan.fuzzy_fields
                    or group.linkage_state != "AMBIGUOUS"
                ):
                    flags["candidate_review"] = False
                    continue
                if (
                    partition["left", arow.id] != "IN_SCOPE"
                    or partition["right", brow.id] != "IN_SCOPE"
                    or any(
                        arow.payload.get(p.left) != brow.payload.get(p.right)
                        for p in plan.fuzzy_block_keys
                    )
                ):
                    flags["candidate_review"] = False
                similarities = [
                    100
                    * Indel.normalized_similarity(
                        str(arow.payload.get(p.left)), str(brow.payload.get(p.right))
                    )
                    for p in plan.fuzzy_fields
                ]
                if (
                    not similarities
                    or min(similarities) < plan.fuzzy_min_score
                    or abs(min(similarities) - candidate.score) > 0.000001
                ):
                    flags["candidate_review"] = False
            if group.linkage_state != "LINKED":
                if group.comparisons or group.comparison_state != "NOT_EVALUATED":
                    flags["comparison"] = False
                continue
            if len(group.comparisons) != len(plan.comparison_metrics):
                flags["comparison"] = False
                continue
            states = []
            for metric, actual in zip(plan.comparison_metrics, group.comparisons, strict=True):
                valid = True
                totals = []
                for side, slot in (("left", plan.left), ("right", plan.right)):
                    total = Decimal(0)
                    if not owned[side]:
                        valid = False
                    for record in owned[side]:
                        amount = record.payload.get(getattr(metric, side))
                        if not isinstance(amount, Decimal) or not amount.is_finite():
                            valid = False
                        else:
                            total += amount
                        if (
                            slot.currency_field
                            and record.payload.get(slot.currency_field) != metric.currency
                        ):
                            valid = False
                    totals.append(total)
                if plan.cardinality != "ONE_TO_ONE" and any(
                    not _complete(plan, s) for s in (plan.left, plan.right)
                ):
                    valid = False
                expected_values: tuple[Decimal | None, ...] = (None, None, None, None, None)
                expected_comparison = "NOT_COMPARABLE"
                if valid:
                    lvalue, rvalue = totals
                    if metric.rounding_scale is not None:
                        quantum = Decimal("10") ** -metric.rounding_scale
                        mode = {"HALF_UP": ROUND_HALF_UP, "HALF_EVEN": ROUND_HALF_EVEN}[
                            metric.rounding_mode
                        ]
                        lvalue = lvalue.quantize(quantum, rounding=mode)
                        rvalue = rvalue.quantize(quantum, rounding=mode)
                    difference = lvalue - rvalue
                    allowed = metric.absolute_tolerance
                    if metric.relative_tolerance is not None:
                        relative = metric.relative_tolerance * max(abs(lvalue), abs(rvalue))
                        if relative > allowed:
                            allowed = relative
                    expected_comparison = (
                        "EQUAL"
                        if difference == 0
                        else (
                            "WITHIN_TOLERANCE"
                            if -allowed <= difference <= allowed
                            else "AMOUNT_MISMATCH"
                        )
                    )
                    expected_values = lvalue, rvalue, difference, abs(difference), allowed
                actual_values = (
                    actual.left_amount,
                    actual.right_amount,
                    actual.delta,
                    actual.absolute_variance,
                    actual.tolerance,
                )
                if (
                    actual_values != expected_values
                    or actual.state != expected_comparison
                    or (actual.metric_id, actual.currency, actual.unit)
                    != (metric.metric_id, metric.currency, metric.unit)
                ):
                    flags["comparison"] = False
                states.append(expected_comparison)
            state = next(
                (
                    s
                    for s in ("NOT_COMPARABLE", "AMOUNT_MISMATCH", "WITHIN_TOLERANCE")
                    if s in states
                ),
                "EQUAL",
            )
            for pair in plan.attributes:
                av = [r.payload.get(pair.left) for r in owned["left"]]
                bv = [r.payload.get(pair.right) for r in owned["right"]]
                if len(set(av)) != 1 or len(set(bv)) != 1 or None in av or None in bv:
                    state = "NOT_COMPARABLE"
                elif av[0] != bv[0] and state in {"EQUAL", "WITHIN_TOLERANCE"}:
                    state = "ATTRIBUTE_MISMATCH"
            if group.comparison_state != state:
                flags["comparison"] = False
            if (
                state in {"AMOUNT_MISMATCH", "ATTRIBUTE_MISMATCH"}
                and state not in group.exception_types
            ):
                flags["comparison"] = False
    flags["membership"] = (
        flags["membership"] and set(seen) == set(lookup) and all(n == 1 for n in seen.values())
    )
    flags["amount_conservation"] = source_totals == member_totals
    flags["determinism"] = (
        flags["determinism"]
        and [g.id for g in result.groups] == sorted(g.id for g in result.groups)
        and len({g.id for g in result.groups}) == len(result.groups)
    )
    return [
        VerificationCheck(
            name=name,
            passed=ok,
            details="Independent source reconstruction passed"
            if ok
            else "Independent source reconstruction failed; publication denied",
        )
        for name, ok in flags.items()
    ]


def calculate_metric_snapshot(
    run_id: str,
    rule_id: str,
    rule_revision: int,
    plan: ReconciliationPlan,
    left: list[CanonicalRecord],
    right: list[CanonicalRecord],
    result: MatchResult,
) -> MetricSnapshot:
    """Publishable metrics only after rerunning the independent oracle, never on blind flags.

    CU is a left reference record (1:1/1:N) or approved left group (N:1).
    Eligible CU has in-scope valid keys, own declared amounts/currency and confirmed
    counterpart coverage. Ambiguity remains eligible/review; missing own money is excluded.
    """
    checks = verify_result(plan, left, right, result)
    if not all(check.passed for check in checks):
        raise DomainError("VERIFICATION_FAILED", "Verification thất bại; không công bố KPI.")
    indexed = {r.id: r for r in left}
    eligible = []
    excluded: Counter[str] = Counter()
    for group in result.groups:
        members = [indexed[m.record_id] for m in group.members if m.side == "left"]
        if not members:
            continue
        reason: str = (
            group.linkage_state
            if group.linkage_state in {"INVALID", "OUT_OF_SCOPE", "PENDING"}
            else ""
        )
        if not reason:
            for record in members:
                if any(
                    not isinstance(record.payload.get(metric.left), Decimal)
                    or (
                        plan.left.currency_field is not None
                        and record.payload.get(plan.left.currency_field) != metric.currency
                    )
                    for metric in plan.comparison_metrics
                ):
                    reason = "OWN_METRIC_NOT_COMPARABLE"
        if reason:
            excluded[reason] += 1
        else:
            eligible.append(group)
    count = len(eligible)

    def rate(numerator: int) -> RateMetric:
        with localcontext() as context:
            context.prec = 100
            percent = (
                str((Decimal(numerator) * 100 / count).quantize(Decimal("0.01"))) if count else None
            )
        return RateMetric(numerator=numerator, denominator=count, percent=percent)

    monetary = []
    with localcontext() as context:
        context.prec = 100
        for metric in plan.comparison_metrics:
            comparisons = [
                c
                for g in result.groups
                for c in g.comparisons
                if c.metric_id == metric.metric_id and c.delta is not None
            ]
            monetary.append(
                MonetarySummary(
                    metric_id=metric.metric_id,
                    currency=metric.currency,
                    unit=metric.unit,
                    comparable_groups=len(comparisons),
                    signed_variance=sum(
                        (c.delta for c in comparisons if c.delta is not None), Decimal(0)
                    ),
                    absolute_variance=sum(
                        (
                            c.absolute_variance
                            for c in comparisons
                            if c.absolute_variance is not None
                        ),
                        Decimal(0),
                    ),
                )
            )
    return MetricSnapshot(
        id=str(uuid5(NAMESPACE_URL, run_id + ":metric-snapshot-1")),
        run_id=run_id,
        revision="metric-snapshot-1",
        rule_id=rule_id,
        rule_revision=rule_revision,
        period_start=plan.period_start,
        period_end=plan.period_end,
        timezone=plan.timezone,
        source_canonical_ids=[plan.left.canonical_id, plan.right.canonical_id],
        comparison_unit="Left canonical reference group"
        if plan.cardinality == "MANY_TO_ONE"
        else "Left canonical reference record",
        eligible_definition=(
            "In-scope left CU with valid key, own declared Decimal amounts/currency; "
            "exclude invalid/out-of-scope/pending/missing-own-money. "
            "Ambiguous CU stays eligible for review. Automation means verified "
            "deterministic classification without a row-level human decision."
        ),
        eligible_units=count,
        full_match_rate=rate(
            sum(
                g.linkage_state == "LINKED" and g.comparison_state in {"EQUAL", "WITHIN_TOLERANCE"}
                for g in eligible
            )
        ),
        linkage_rate=rate(sum(g.linkage_state == "LINKED" for g in eligible)),
        exception_rate=rate(sum(bool(g.exception_types) for g in eligible)),
        automation_coverage=rate(
            sum(
                g.linkage_state in {"LINKED", "UNMATCHED"}
                and g.comparison_state != "NOT_COMPARABLE"
                for g in eligible
            )
        ),
        review_rate=rate(
            sum(
                g.linkage_state == "AMBIGUOUS" or g.comparison_state == "NOT_COMPARABLE"
                for g in eligible
            )
        ),
        monetary=monetary,
        linkage_counts=dict(Counter(g.linkage_state for g in result.groups)),
        comparison_counts=dict(Counter(g.comparison_state for g in result.groups)),
        excluded_counts=dict(excluded),
        unresolved_cases_at_run=sum(len(g.exception_types) for g in result.groups),
    )
