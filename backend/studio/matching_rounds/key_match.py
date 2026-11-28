"""Vòng khớp theo mã (tên trong config/rules/reconciliation.json: "key_match").

Hai dòng có cùng mã (mã đơn, mã giao dịch, hoặc mã tách được từ nội dung chuyển khoản) được
ghép với nhau. Một dòng bên B ghi nhiều mã, hoặc bên A dùng chung mã (mã đợt chuyển, ngày) thì
ghép nhóm khi tổng tiền bằng nhau. Cùng một mã có nhiều dòng thì giữ cặp tốt nhất, dòng thừa
xếp "Trùng". Số tiền lệch ngoài sai số thì vẫn ghép nhưng xếp "Lệch tiền".

Đầu vào: các dòng chưa được ghép ở vòng trước (left, right) và cấu hình đối soát.
Đầu ra: RoundOutcome (kết quả, số dòng đã dùng mỗi bên); dòng chưa dùng chuyển sang vòng sau.
"""

from collections import defaultdict
from decimal import Decimal

from studio.reconciliation import (
    MAX_SAME_KEY_PAIRS,
    ReconConfig,
    Result,
    RoundOutcome,
    Row,
    _blocked,
    _days_apart,
    _group_result,
    _pair_result,
    _reason,
    _single,
    _within,
    money_dong,
)


def _pair_same_key(
    lefts: list[Row], rights: list[Row], config: ReconConfig, blocked: set[tuple[int, int]]
) -> list[tuple[Row, Row]]:
    """Ghép các dòng cùng một mã: cặp tốt nhất trước (đúng tiền, gần ngày, dòng sớm).

    Ít dòng (trường hợp thường gặp): xếp hạng mọi cặp một lần rồi ghép tham lam.
    Nhiều dòng trùng mã (ví dụ mã giữ chỗ "0" lặp hàng nghìn lần): không so mọi cặp nữa mà
    ghép theo số tiền bằng nhau, rồi phần còn lại theo thứ tự dòng gốc, để không chậm theo
    bình phương số dòng.
    """
    if len(lefts) == 1 and len(rights) == 1:
        only = (lefts[0], rights[0])
        return [] if (only[0].ref, only[1].ref) in blocked else [only]
    paired: list[tuple[Row, Row]] = []
    used_left: set[int] = set()
    used_right: set[int] = set()
    if len(lefts) * len(rights) <= MAX_SAME_KEY_PAIRS:
        ranked = sorted(
            ((a, b) for a in lefts for b in rights if (a.ref, b.ref) not in blocked),
            key=lambda pair: (
                not _within(pair[0].amount, pair[1].amount, config.tolerance),
                _days_apart(pair[0].day, pair[1].day) or 0,
                pair[0].ref,
                pair[1].ref,
            ),
        )
        for a, b in ranked:
            if a.ref not in used_left and b.ref not in used_right:
                paired.append((a, b))
                used_left.add(a.ref)
                used_right.add(b.ref)
        return paired
    by_amount: dict[Decimal | None, list[Row]] = defaultdict(list)
    for b in sorted(rights, key=lambda row: row.ref):
        by_amount[b.amount].append(b)
    rest_left = []
    for a in sorted(lefts, key=lambda row: row.ref):
        bucket = by_amount.get(a.amount) if a.amount is not None else None
        if bucket:
            b = bucket.pop(0)
            paired.append((a, b))
            used_right.add(b.ref)
        else:
            rest_left.append(a)
    rest_right = [b for b in sorted(rights, key=lambda row: row.ref) if b.ref not in used_right]
    paired += list(zip(rest_left, rest_right, strict=False))
    return [(a, b) for a, b in paired if (a.ref, b.ref) not in blocked]


def run(left: list[Row], right: list[Row], config: ReconConfig) -> RoundOutcome:
    """Khớp theo mã. Trả về kết quả và tập số dòng A, B đã dùng."""
    results: list[Result] = []
    used_left: set[int] = set()
    used_right: set[int] = set()
    blocked = _blocked(config)
    by_key_left: dict[str, list[Row]] = defaultdict(list)
    for row in left:
        for key in row.keys:
            by_key_left[key.upper()].append(row)

    # a) Ghép nhóm: một dòng B ghi nhiều mã, hoặc bên A dùng chung mã (đợt chuyển, ngày).
    by_key_right: dict[str, list[Row]] = defaultdict(list)
    for row in right:
        keys = [key.upper() for key in row.keys if key.upper() in by_key_left]
        if not keys:
            continue
        if len(keys) == 1 and not config.group_left:
            by_key_right[keys[0]].append(row)
            continue
        members = [
            a for key in keys for a in by_key_left[key]
            if a.ref not in used_left and not (config.group_left and a.cancelled)
            and (a.ref, row.ref) not in blocked
        ]
        members = list({a.ref: a for a in members}.values())
        if not members:
            continue
        results.append(_group_result(members, [row], "KEY", config))
        used_left.update(a.ref for a in members)
        used_right.add(row.ref)

    # b) Mã riêng 1:1: cùng mã nhiều dòng → cặp tốt nhất, phần thừa là DUPLICATE.
    for key in sorted(by_key_right):
        lefts = [row for row in by_key_left[key] if row.ref not in used_left]
        rights = by_key_right[key]
        if not lefts:
            continue
        paired = _pair_same_key(lefts, rights, config, blocked)
        if not paired:
            continue  # mọi cặp cùng mã đều đã bị gỡ: để các vòng sau (hoặc người dùng) xử lý
        paired_left = {a.ref for a, _ in paired}
        paired_right = {b.ref for _, b in paired}
        for a, b in paired:
            results.append(_pair_result(a, b, config, "KEY"))
            used_left.add(a.ref)
            used_right.add(b.ref)
        counterpart = paired[0]
        extras = [(row, "A") for row in lefts if row.ref not in paired_left] + [
            (row, "B") for row in rights if row.ref not in paired_right
        ]
        for extra, side in extras:
            other = counterpart[1] if side == "A" else counterpart[0]
            results.append(
                _single(
                    "DUPLICATE",
                    extra,
                    side,
                    [
                        _reason(
                            "DUPLICATE_KEY",
                            f"Trùng mã {key} với dòng {other.ref} bên "
                            f"{'B' if side == 'A' else 'A'} đã được ghép "
                            f"(số tiền {money_dong(extra.amount)}).",
                        )
                    ],
                    True,
                )
            )
            (used_left if side == "A" else used_right).add(extra.ref)
    return RoundOutcome(results, used_left, used_right)
