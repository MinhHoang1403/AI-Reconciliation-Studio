"""F16–F22 deterministic linkage before Decimal comparison.

Exact groups use approved composite keys, never amount proximity. Duplicates
remain disjoint review units; fuzzy edges cannot become accepted memberships.
Complexity is O(n log n + bounded candidate pairs), with explicit row/pair caps.
"""

import json
from collections import defaultdict
from datetime import datetime, time
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from rapidfuzz.fuzz import ratio

from studio.contracts.reconciliation import (
    CandidateLink,
    CanonicalRecord,
    ComparisonMetric,
    ComparisonResult,
    ComparisonState,
    LinkageState,
    MatchGroup,
    MatchMember,
    MatchResult,
    ReconciliationPlan,
    SourceSelection,
)
from studio.errors import DomainError

ENGINE_REVISION = "reconciliation-1"
MAX_RECORDS = 100000
MAX_FUZZY_PAIRS = 20000
MAX_FUZZY_BLOCK = 200


def coverage_complete(plan: ReconciliationPlan, slot: SourceSelection) -> bool:
    return (
        slot.completeness == "CONFIRMED"
        and slot.coverage_start <= plan.period_start
        and slot.coverage_end >= plan.period_end
        and (slot.settlement_due_at is None or slot.snapshot_at >= slot.settlement_due_at)
    )


def record_partition(record: CanonicalRecord, plan: ReconciliationPlan, side: str) -> str:
    """Invalid, excluded and eligible partitions are exclusive; no row is dropped."""
    slot = plan.left if side == "left" else plan.right
    stamp = record.payload.get(slot.date_field)
    keys = [record.payload.get(getattr(pair, side)) for pair in plan.join_keys]
    if (
        record.invalid
        or any(not isinstance(k, str) or k == "" for k in keys)
        or not isinstance(stamp, datetime)
        or stamp.utcoffset() is None
    ):
        return "INVALID"
    if any(record.payload.get(field) != value for field, value in slot.filters.items()):
        return "OUT_OF_SCOPE"
    zone = ZoneInfo(plan.timezone)
    start = datetime.combine(plan.period_start, time.min, zone)
    end = datetime.combine(plan.period_end, time.min, zone)
    return "IN_SCOPE" if start <= stamp < end else "OUT_OF_SCOPE"


def _key(record: CanonicalRecord, plan: ReconciliationPlan, side: str) -> tuple[str | None, ...]:
    return tuple(
        str(value) if value is not None else None
        for value in (record.payload.get(getattr(p, side)) for p in plan.join_keys)
    )


def _amount(rows: list[CanonicalRecord], field: str) -> Decimal | None:
    values = [r.payload.get(field) for r in rows]
    if not values or any(not isinstance(v, Decimal) or not v.is_finite() for v in values):
        return None
    return sum((v for v in values if isinstance(v, Decimal)), Decimal(0))


def _compare(
    plan: ReconciliationPlan,
    left: list[CanonicalRecord],
    right: list[CanonicalRecord],
    metric: ComparisonMetric,
) -> ComparisonResult:
    result = ComparisonResult(
        metric_id=metric.metric_id,
        currency=metric.currency,
        unit=metric.unit,
        state="NOT_COMPARABLE",
    )
    for slot, rows in ((plan.left, left), (plan.right, right)):
        if slot.currency_field and any(
            r.payload.get(slot.currency_field) != metric.currency for r in rows
        ):
            return result
    # An incomplete multi-row source cannot establish that the group sum is complete.
    if plan.cardinality != "ONE_TO_ONE" and not all(
        coverage_complete(plan, s) for s in (plan.left, plan.right)
    ):
        return result
    a, b = _amount(left, metric.left), _amount(right, metric.right)
    if a is None or b is None:
        return result
    if metric.rounding_scale is not None:
        quantum = Decimal(1).scaleb(-metric.rounding_scale)
        rounding = ROUND_HALF_UP if metric.rounding_mode == "HALF_UP" else ROUND_HALF_EVEN
        a, b = a.quantize(quantum, rounding=rounding), b.quantize(quantum, rounding=rounding)
    delta = a - b
    tolerance = metric.absolute_tolerance
    if metric.relative_tolerance is not None:
        tolerance = max(tolerance, metric.relative_tolerance * max(abs(a), abs(b)))
    result.left_amount, result.right_amount = a, b
    result.delta, result.absolute_variance, result.tolerance = delta, abs(delta), tolerance
    result.state = (
        "EQUAL"
        if delta == 0
        else ("WITHIN_TOLERANCE" if abs(delta) <= tolerance else "AMOUNT_MISMATCH")
    )
    return result


def _group(
    plan: ReconciliationPlan,
    left: list[CanonicalRecord],
    right: list[CanonicalRecord],
    state: LinkageState,
    issues: list[str],
    algorithm: str,
) -> MatchGroup:
    members = [
        MatchMember(
            side=side, canonical_id=slot.canonical_id, record_id=r.id, evidence=r.provenance
        )
        for side, slot, rows in (("left", plan.left, left), ("right", plan.right, right))
        for r in sorted(rows, key=lambda r: r.id)
    ]
    group_id = str(
        uuid5(
            NAMESPACE_URL,
            json.dumps([ENGINE_REVISION, [(m.side, m.canonical_id, m.record_id) for m in members]]),
        )
    )
    first, side = (left[0], "left") if left else (right[0], "right")
    comparisons = []
    comparison: ComparisonState = "NOT_COMPARABLE" if state == "INVALID" else "NOT_EVALUATED"
    if state == "LINKED":
        comparisons = [_compare(plan, left, right, m) for m in plan.comparison_metrics]
        states = {c.state for c in comparisons}
        if "NOT_COMPARABLE" in states:
            comparison = "NOT_COMPARABLE"
            issues.append("RULE_UNVERIFIED")
        elif "AMOUNT_MISMATCH" in states:
            comparison = "AMOUNT_MISMATCH"
            issues.append("AMOUNT_MISMATCH")
        elif "WITHIN_TOLERANCE" in states:
            comparison = "WITHIN_TOLERANCE"
        else:
            comparison = "EQUAL"
        for pair in plan.attributes:
            a = {r.payload.get(pair.left) for r in left}
            b = {r.payload.get(pair.right) for r in right}
            if len(a) != 1 or len(b) != 1 or None in a or None in b:
                comparison = "NOT_COMPARABLE"
                issues.append("MISSING_FIELD")
            elif a != b:
                issues.append("ATTRIBUTE_MISMATCH")
                if comparison in {"EQUAL", "WITHIN_TOLERANCE"}:
                    comparison = "ATTRIBUTE_MISMATCH"
    return MatchGroup(
        id=group_id,
        key=list(_key(first, plan, side)),
        members=members,
        linkage_state=state,
        comparison_state=comparison,
        comparisons=comparisons,
        exception_types=sorted(set(issues)),
        algorithm=algorithm,
    )


def _fuzzy(
    plan: ReconciliationPlan,
    groups: list[MatchGroup],
    records: dict[tuple[str, str], CanonicalRecord],
) -> int:
    if not plan.fuzzy_fields:
        return 0
    buckets: dict[tuple[str, ...], list[tuple[MatchGroup, CanonicalRecord]]] = defaultdict(list)
    for group in groups:
        if group.linkage_state != "UNMATCHED" or len(group.members) != 1:
            continue
        member = group.members[0]
        if member.side == "right":
            row = records[("right", member.record_id)]
            values = tuple(row.payload.get(p.right) for p in plan.fuzzy_block_keys)
            if all(isinstance(v, str) and v for v in values):
                buckets[tuple(str(v) for v in values)].append((group, row))
    count = 0
    for group in groups:
        if group.linkage_state != "UNMATCHED" or len(group.members) != 1:
            continue
        member = group.members[0]
        if member.side != "left":
            continue
        row = records[("left", member.record_id)]
        values = tuple(row.payload.get(p.left) for p in plan.fuzzy_block_keys)
        candidates = (
            buckets.get(tuple(str(v) for v in values), [])
            if all(isinstance(v, str) and v for v in values)
            else []
        )
        if len(candidates) > MAX_FUZZY_BLOCK:
            raise DomainError(
                "CANDIDATE_LIMIT_EXCEEDED", "Block fuzzy quá lớn; cần khóa chặn hẹp hơn."
            )
        scored = []
        for other_group, other in candidates:
            if count >= MAX_FUZZY_PAIRS:
                raise DomainError(
                    "CANDIDATE_LIMIT_EXCEEDED", "Vượt hạn mức ứng viên; cần thu hẹp scope."
                )
            count += 1
            currency_ok = all(
                not slot.currency_field or r.payload.get(slot.currency_field) == metric.currency
                for slot, r in ((plan.left, row), (plan.right, other))
                for metric in plan.comparison_metrics
            )
            if not currency_ok:
                continue
            scores = []
            for pair in plan.fuzzy_fields:
                a, b = row.payload.get(pair.left), other.payload.get(pair.right)
                if not isinstance(a, str) or not isinstance(b, str) or not a or not b:
                    break
                if max(len(a), len(b)) > 512:
                    raise DomainError(
                        "CANDIDATE_TEXT_TOO_LONG", "Text fuzzy vượt giới hạn 512 ký tự."
                    )
                scores.append(ratio(a, b))
            if len(scores) == len(plan.fuzzy_fields) and min(scores) >= plan.fuzzy_min_score:
                scored.append((min(scores), other.id, other_group))
        for score, other_id, other_group in sorted(scored, key=lambda x: (-x[0], x[1]))[
            : plan.fuzzy_top_k
        ]:
            candidate = CandidateLink(
                left_record_id=row.id,
                right_record_id=other_id,
                score=score,
                field_pairs=plan.fuzzy_fields,
            )
            for target in (group, other_group):
                target.candidates.append(candidate)
                target.linkage_state = "AMBIGUOUS"
                target.exception_types = ["UNCERTAIN_MATCH"]
    return count


def match_records(
    plan: ReconciliationPlan, left: list[CanonicalRecord], right: list[CanonicalRecord]
) -> MatchResult:
    """Execute an already approved/validated plan over typed canonical projections.

    Returns disjoint memberships for every canonical record, even excluded/invalid.
    This function cannot publish metrics; verifier and scoped worker do that later.
    """
    if len(left) + len(right) > MAX_RECORDS:
        raise DomainError(
            "RECONCILIATION_ROW_LIMIT", "Vượt giới hạn 100.000 bản ghi mỗi lần đối soát."
        )
    identities = [(side, r.id) for side, rows in (("left", left), ("right", right)) for r in rows]
    if len(identities) != len(set(identities)):
        raise DomainError("DUPLICATE_RECORD_ID", "Canonical record ID bị lặp.")
    groups: list[MatchGroup] = []
    indexes: list[dict[tuple[str | None, ...], list[CanonicalRecord]]] = []
    counts: dict[str, dict[str, int]] = {}
    with localcontext() as context:
        context.prec = 100
        for side, rows in (("left", left), ("right", right)):
            index: dict[tuple[str | None, ...], list[CanonicalRecord]] = defaultdict(list)
            counts[side] = {"INVALID": 0, "OUT_OF_SCOPE": 0, "IN_SCOPE": 0}
            for record in sorted(rows, key=lambda r: r.id):
                partition = record_partition(record, plan, side)
                counts[side][partition] += 1
                if partition == "IN_SCOPE":
                    index[_key(record, plan, side)].append(record)
                else:
                    issues = (
                        (["INVALID_DECIMAL"] if record.invalid else ["MISSING_FIELD"])
                        if partition == "INVALID"
                        else []
                    )
                    groups.append(
                        _group(
                            plan,
                            [record] if side == "left" else [],
                            [record] if side == "right" else [],
                            "INVALID" if partition == "INVALID" else "OUT_OF_SCOPE",
                            issues,
                            "scope-partition",
                        )
                    )
            indexes.append(index)
        for key in sorted(set(indexes[0]) | set(indexes[1])):
            a, b = indexes[0].get(key, []), indexes[1].get(key, [])
            conflict = (len(a) > 1 and plan.cardinality != "MANY_TO_ONE") or (
                len(b) > 1 and plan.cardinality != "ONE_TO_MANY"
            )
            if conflict:
                for side, rows in (("left", a), ("right", b)):
                    allowed_many = (side == "left" and plan.cardinality == "MANY_TO_ONE") or (
                        side == "right" and plan.cardinality == "ONE_TO_MANY"
                    )
                    for chunk in [rows] if allowed_many and rows else [[r] for r in rows]:
                        groups.append(
                            _group(
                                plan,
                                chunk if side == "left" else [],
                                chunk if side == "right" else [],
                                "AMBIGUOUS",
                                ["DUPLICATE_KEY"],
                                "duplicate-review",
                            )
                        )
            elif a and b:
                groups.append(
                    _group(
                        plan,
                        a,
                        b,
                        "LINKED",
                        [],
                        "exact-composite" if plan.cardinality == "ONE_TO_ONE" else "approved-group",
                    )
                )
            else:
                counterpart = plan.right if a else plan.left
                pending = not coverage_complete(plan, counterpart)
                issue = "INSUFFICIENT_COVERAGE"
                if (
                    counterpart.settlement_due_at is not None
                    and counterpart.snapshot_at < counterpart.settlement_due_at
                ):
                    issue = "NOT_YET_SETTLED"
                groups.append(
                    _group(
                        plan,
                        a,
                        b,
                        "PENDING" if pending else "UNMATCHED",
                        [issue if pending else "MISSING_COUNTERPART"],
                        "exact-composite",
                    )
                )
        lookup = {
            (side, r.id): r for side, rows in (("left", left), ("right", right)) for r in rows
        }
        pairs = _fuzzy(plan, groups, lookup)
    for group in groups:
        group.candidates.sort(key=lambda c: (-c.score, c.left_record_id, c.right_record_id))
    return MatchResult(
        engine_revision=ENGINE_REVISION,
        groups=sorted(groups, key=lambda g: g.id),
        partition_counts=counts,
        warnings=[f"fuzzy_pairs_evaluated={pairs}; scores are similarity, review only"]
        if plan.fuzzy_fields
        else [],
    )
