"""Vòng khớp nhóm theo tổng tiền (tên trong config/rules/reconciliation.json: "group_match").

Cho các dòng còn lại sau hai vòng trước: tìm vài dòng bên A cộng lại đúng bằng một dòng bên B
(ví dụ khách trả gộp hai đơn bằng một lần chuyển khoản), rồi ngược lại một dòng A bằng tổng
nhiều dòng B. Tổng phải bằng đúng, không áp sai số (theo Oracle Cash Management). Số dòng mỗi
nhóm và số ứng viên có giới hạn ("group_match" trong tệp cấu hình) để không bùng nổ tổ hợp.
Nhiều tổ hợp cùng đúng thì không tự chọn mà xếp "Cần bạn chọn".
"""

import bisect
from datetime import timedelta
from decimal import Decimal

from studio.reconciliation import (
    MAX_GROUP_ROWS,
    MAX_SUBSET_CANDIDATES,
    ReconConfig,
    Result,
    RoundOutcome,
    Row,
    _ambiguous_result,
    _blocked,
    _group_result,
    money_dong,
)


def subsets(candidates: list[Row], target: Decimal, limit: int = 2) -> list[list[Row]]:
    """Các tổ hợp 2..MAX_GROUP_ROWS dòng có tổng đúng bằng target (dừng khi đủ `limit`)."""
    ordered = sorted(candidates, key=lambda row: (row.amount, row.ref))
    amounts = [row.amount or Decimal("0") for row in ordered]
    suffix = [sum(amounts[index:], Decimal("0")) for index in range(len(amounts) + 1)]
    found: list[list[Row]] = []

    def walk(start: int, chosen: list[Row], total: Decimal) -> None:
        if len(found) >= limit:
            return
        if total == target and len(chosen) >= 2:
            found.append(list(chosen))
            return
        if len(chosen) == MAX_GROUP_ROWS or total + suffix[start] < target:
            return
        for index in range(start, len(ordered)):
            next_total = total + amounts[index]
            if next_total > target:
                break  # đã sắp tăng dần: các dòng sau còn lớn hơn
            chosen.append(ordered[index])
            walk(index + 1, chosen, next_total)
            chosen.pop()
            if len(found) >= limit:
                return

    walk(0, [], Decimal("0"))
    return found


def run(left: list[Row], right: list[Row], config: ReconConfig) -> RoundOutcome:
    """Khớp nhóm theo tổng tiền cho dòng chưa có cặp: nhiều A ↔ một B, rồi một A ↔ nhiều B."""
    results: list[Result] = []
    used_left: set[int] = set()
    used_right: set[int] = set()
    window = timedelta(days=config.date_window_days)
    blocked = _blocked(config)

    for one, many, one_side in ((right, left, "B"), (left, right, "A")):
        used_one = used_right if one_side == "B" else used_left
        used_many = used_left if one_side == "B" else used_right
        # Lọc ứng viên theo ngày bằng tìm nhị phân trên danh sách đã sắp theo ngày, để không
        # phải so mọi dòng với mọi dòng (hai bảng lớn không có mã chung vẫn chạy nhanh).
        dated = sorted(
            (row for row in many if row.day and row.amount is not None and row.amount > 0),
            key=lambda row: (row.day, row.ref),
        )
        days = [row.day for row in dated if row.day]
        for target in sorted(one, key=lambda row: row.ref):
            if target.ref in used_one or target.amount is None or target.amount <= 0:
                continue
            if target.day is None:
                continue
            # Dòng gộp ghi sau (hoặc cùng ngày) các dòng thành phần, trong khung ngày: B gộp
            # nhiều A thì A nằm trong [ngày B − khung, ngày B]; A trả bằng nhiều B thì ngược lại.
            low, high = (
                (target.day - window, target.day) if one_side == "B"
                else (target.day, target.day + window)
            )
            pool = [
                row
                for row in dated[bisect.bisect_left(days, low) : bisect.bisect_right(days, high)]
                if row.ref not in used_many and row.amount is not None
                and row.amount < target.amount
                and ((row.ref, target.ref) if one_side == "B" else (target.ref, row.ref))
                not in blocked
            ]
            if len(pool) < 2 or len(pool) > MAX_SUBSET_CANDIDATES:
                continue
            solutions = subsets(pool, target.amount)
            if not solutions:
                continue
            members = [row for solution in solutions for row in solution]
            members = list({row.ref: row for row in members}.values())
            lefts, rights = (members, [target]) if one_side == "B" else ([target], members)
            if len(solutions) == 1:
                results.append(_group_result(lefts, rights, "SUM", config))
            else:
                results.append(
                    _ambiguous_result(
                        lefts,
                        rights,
                        [
                            {
                                "left": [row.ref for row in solution] if one_side == "B"
                                else [target.ref],
                                "right": [target.ref] if one_side == "B"
                                else [row.ref for row in solution],
                                "score": None,
                            }
                            for solution in solutions
                        ],
                        f"Có nhiều tổ hợp dòng cùng tổng {money_dong(target.amount)} nên không "
                        "tự chọn. Hãy chọn tổ hợp đúng.",
                    )
                )
            used_one.add(target.ref)
            used_many.update(row.ref for row in members)
    return RoundOutcome(results, used_left, used_right)
