"""Vòng khớp theo điểm 1:1 (tên trong config/rules/reconciliation.json: "score_match").

Dùng khi không có mã chung: hai dòng phải cùng số tiền (trong sai số) và cách nhau không quá
khung ngày; mỗi cặp được chấm điểm từ độ gần ngày, độ giống mã và độ giống tên (trọng số trong
"score_match" của tệp cấu hình). Cặp tốt nhất được chọn bằng phân công tối ưu
(scipy.optimize.linear_sum_assignment), mỗi dòng dùng một lần. Dòng có nhiều ứng viên ngang
điểm thì KHÔNG tự chọn mà xếp "Cần bạn chọn" (AMBIGUOUS) kèm các ứng viên.

Đầu ra: RoundOutcome, kèm "skipped": lý do các dòng bị để lại (quá nhiều ứng viên…) để bước
xếp loại cuối ghi rõ vì sao không tự ghép.
"""

import bisect
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from studio.reconciliation import (
    MAX_CANDIDATES_PER_ROW,
    MAX_COMPONENT_ROWS,
    SCORE_WEIGHTS,
    ReconConfig,
    Result,
    RoundOutcome,
    Row,
    _ambiguous_result,
    _blocked,
    _days_apart,
    _name_score,
    _pair_result,
    _reason,
    _within,
)


def _pair_score(a: Row, b: Row, config: ReconConfig) -> float | None:
    """Điểm 0–1 của một cặp ứng viên; None nếu không đủ điều kiện làm ứng viên."""
    if not _within(a.amount, b.amount, config.tolerance):
        return None
    gap = _days_apart(a.day, b.day)
    if gap is not None and gap > config.date_window_days:
        return None
    parts: dict[str, float] = {}
    if gap is not None:
        parts["date"] = 1 - gap / (config.date_window_days + 1)
    if a.key and b.key:
        parts["key"] = fuzz.ratio(a.key, b.key) / 100
    if a.name and b.name:
        parts["name"] = _name_score(a.name, b.name, config.name_right is not None)
    if not parts:
        return None  # chỉ trùng số tiền thì quá yếu để ghép
    weight = sum(SCORE_WEIGHTS[name] for name in parts)
    return round(sum(SCORE_WEIGHTS[name] * value for name, value in parts.items()) / weight, 6)


def _components(edges: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    """Chia đồ thị (A — B) thành các thành phần liên thông (union-find).

    Hai dòng chỉ có thể tranh nhau khi nằm cùng thành phần, nên ghép tối ưu trên từng thành
    phần nhỏ cho đúng kết quả như ghép trên toàn bộ, mà không phải dựng ma trận A×B khổng lồ.
    """
    parent: dict[tuple[str, int], tuple[str, int]] = {}

    def find(node: tuple[str, int]) -> tuple[str, int]:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for a_ref, b_ref in edges:
        root_a, root_b = find(("A", a_ref)), find(("B", b_ref))
        if root_a != root_b:
            parent[root_b] = root_a
    groups: dict[tuple[str, int], list[tuple[int, int]]] = defaultdict(list)
    for pair in sorted(edges):
        groups[find(("A", pair[0]))].append(pair)
    return list(groups.values())


def run(left: list[Row], right: list[Row], config: ReconConfig) -> RoundOutcome:
    """Khớp theo điểm 1:1 bằng phân công tối ưu; ứng viên ngang điểm → AMBIGUOUS.

    Trả về kết quả, số dòng đã dùng và lý do không tự ghép của các dòng bị để lại.
    """
    # Lọc ứng viên (blocking) hai tầng: theo số tiền (trong sai số), rồi trong mỗi số tiền theo
    # khung ngày bằng tìm nhị phân. Dòng B không có ngày luôn là ứng viên (không loại được).
    by_amount: dict[Decimal, list[Row]] = defaultdict(list)
    for row in right:
        if row.amount is not None:
            by_amount[row.amount].append(row)
    buckets: dict[Decimal, tuple[list[date], list[Row], list[Row]]] = {}
    for amount, rows in by_amount.items():
        dated = sorted((row for row in rows if row.day), key=lambda row: (row.day, row.ref))
        undated = [row for row in rows if not row.day]
        buckets[amount] = ([row.day for row in dated if row.day], dated, undated)
    sorted_amounts = sorted(by_amount)
    window = timedelta(days=config.date_window_days)
    skipped: dict[tuple[str, int], str] = {}  # (bên, số dòng) → lý do không tự ghép
    blocked = _blocked(config)

    def nearby(a: Row, amount: Decimal) -> list[Row]:
        days, dated, undated = buckets[amount]
        if a.day is None:
            return dated + undated
        start = bisect.bisect_left(days, a.day - window)
        end = bisect.bisect_right(days, a.day + window)
        return dated[start:end] + undated

    candidates: dict[tuple[int, int], float] = {}
    for a in left:
        if a.amount is None:
            continue
        # Lọc ứng viên (blocking): chỉ xét số tiền trong sai số, không so mọi cặp.
        low = bisect.bisect_left(sorted_amounts, a.amount - config.tolerance)
        found: list[tuple[int, float]] = []
        for amount in sorted_amounts[low:]:
            if amount > a.amount + config.tolerance:
                break
            for b in nearby(a, amount):
                if (a.ref, b.ref) in blocked:
                    continue
                score = _pair_score(a, b, config)
                if score is not None and score >= config.min_score:
                    found.append((b.ref, score))
            if len(found) > MAX_CANDIDATES_PER_ROW:
                break  # đã quá nhiều ứng viên: dừng sớm, không quét hết
        # Quá nhiều dòng cùng số tiền, gần ngày: ghép theo điểm không còn đáng tin.
        if len(found) > MAX_CANDIDATES_PER_ROW:
            skipped[("A", a.ref)] = (
                f"Có hơn {MAX_CANDIDATES_PER_ROW} dòng cùng số tiền, gần ngày ở bên B "
                "nên không tự ghép."
            )
            for b_ref, _ in found:
                skipped.setdefault(
                    ("B", b_ref),
                    "Có quá nhiều dòng cùng số tiền, gần ngày ở bên A nên không tự ghép.",
                )
            continue
        for b_ref, score in found:
            candidates[(a.ref, b_ref)] = score
    if not candidates:
        return RoundOutcome([], set(), set(), skipped)

    left_by_ref = {row.ref: row for row in left}
    right_by_ref = {row.ref: row for row in right}
    results: list[Result] = []
    used_left: set[int] = set()
    used_right: set[int] = set()

    # Ca mơ hồ: một dòng có từ hai ứng viên trở lên cùng đạt điểm cao nhất của nó. Gom các
    # cạnh ngang điểm thành nhóm; cả nhóm thành AMBIGUOUS để người dùng chọn, không tự ghép.
    best_left: dict[int, float] = defaultdict(float)
    best_right: dict[int, float] = defaultdict(float)
    for (a_ref, b_ref), score in candidates.items():
        best_left[a_ref] = max(best_left[a_ref], score)
        best_right[b_ref] = max(best_right[b_ref], score)
    top_left = Counter(a for (a, _), s in candidates.items() if s == best_left[a])
    top_right = Counter(b for (_, b), s in candidates.items() if s == best_right[b])
    tied = [
        (a_ref, b_ref)
        for (a_ref, b_ref), score in candidates.items()
        if (score == best_left[a_ref] and top_left[a_ref] > 1)
        or (score == best_right[b_ref] and top_right[b_ref] > 1)
    ]
    tied_left: set[int] = set()
    tied_right: set[int] = set()
    for group in _components(tied):
        lefts = sorted({pair[0] for pair in group})
        rights = sorted({pair[1] for pair in group})
        pairs = [
            {"left": [a], "right": [b], "score": candidates[(a, b)]}
            for a, b in sorted(group)
        ]
        names = ", ".join(
            f"dòng {ref}" + (f" ({left_by_ref[ref].name})" if left_by_ref[ref].name else "")
            for ref in lefts
        )
        results.append(
            _ambiguous_result(
                [left_by_ref[ref] for ref in lefts],
                [right_by_ref[ref] for ref in rights],
                pairs,
                f"Có {len(pairs)} cặp ngang điểm {pairs[0]['score']:.2f} nên không tự chọn: "
                f"{names}. Hãy chọn cặp đúng.",
            )
        )
        tied_left.update(lefts)
        tied_right.update(rights)
    used_left |= tied_left
    used_right |= tied_right
    remaining = [
        pair for pair in candidates if pair[0] not in tied_left and pair[1] not in tied_right
    ]

    for component in _components(remaining):
        left_refs = sorted({pair[0] for pair in component})
        right_refs = sorted({pair[1] for pair in component})
        if len(left_refs) > MAX_COMPONENT_ROWS or len(right_refs) > MAX_COMPONENT_ROWS:
            message = (
                f"Thuộc một nhóm {len(left_refs)} × {len(right_refs)} dòng cùng số tiền, "
                "gần ngày nên không tự ghép."
            )
            skipped.update({("A", ref): message for ref in left_refs})
            skipped.update({("B", ref): message for ref in right_refs})
            continue
        row_index = {ref: index for index, ref in enumerate(left_refs)}
        col_index = {ref: index for index, ref in enumerate(right_refs)}
        # Ma trận chi phí = -điểm; cặp không phải ứng viên có chi phí 0 (không lợi gì khi chọn).
        cost = np.zeros((len(left_refs), len(right_refs)))
        for a_ref, b_ref in component:
            cost[row_index[a_ref], col_index[b_ref]] = -candidates[(a_ref, b_ref)]
        rows, cols = linear_sum_assignment(cost)
        for r, c in zip(rows, cols, strict=True):
            a_ref, b_ref = left_refs[r], right_refs[c]
            score = candidates.get((a_ref, b_ref))
            if score is None:
                continue
            a, b = left_by_ref[a_ref], right_by_ref[b_ref]
            result = _pair_result(a, b, config, "SCORE")
            detail = [f"điểm {score:.2f}"]
            if a.key and b.key and a.key != b.key:
                detail.append(f"mã khác nhau ({a.key} / {b.key}), có thể gõ sai")
            elif not (a.key and b.key):
                detail.append("một bên không ghi mã")
            if a.name and b.name and config.name_right:
                detail.append(f"tên “{b.name}” khớp “{a.name}”")
            result.reasons.insert(
                0, _reason("SCORE", "Ghép theo số tiền và ngày: " + ", ".join(detail) + ".")
            )
            result.score = score
            results.append(result)
            used_left.add(a_ref)
            used_right.add(b_ref)
    return RoundOutcome(results, used_left, used_right, skipped)
