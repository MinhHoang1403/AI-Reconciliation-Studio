"""Kiểm chứng kết quả đối soát, độc lập với engine (docs/ARCHITECTURE.md 5.3).

Module này không gọi lại engine: nó chỉ đọc hai bảng sạch đã dùng và danh sách kết quả đã
lưu (dạng dict như trong cơ sở dữ liệu), rồi tự đếm và cộng lại. Nhờ vậy, lỗi của engine
hay kết quả bị sửa tay trong cơ sở dữ liệu đều bị phát hiện. Kiểm chứng không đạt thì lần
đối soát bị đánh dấu không dùng được cho báo cáo.
"""

from collections import Counter
from decimal import Decimal
from typing import Any

import polars as pl

from studio.reading import ROW_REF

# Số dòng mỗi bên mà từng loại kết quả phải có: (A, B). (-1, -1): đúng một dòng ở một bên.
SHAPES: dict[str, tuple[int | None, int | None]] = {
    "MATCHED": (1, 1),
    "AMOUNT_MISMATCH": (1, 1),
    "DUPLICATE": (-1, -1),
    "ONLY_IN_A": (1, 0),
    "ONLY_IN_B": (0, 1),
    "NEEDS_CLEANING": (-1, -1),
    "OUT_OF_SCOPE": (-1, -1),
}
SHOWN_REFS = 5  # số dòng lỗi tối đa ghi trong chi tiết


def _amounts(frame: pl.DataFrame, column: str) -> dict[int, Decimal | None]:
    if column not in frame.columns:
        return {ref: None for ref in frame[ROW_REF].to_list()}
    return dict(zip(frame[ROW_REF].to_list(), frame[column].to_list(), strict=True))


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _check(code: str, label: str, problems: list[str]) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "passed": not problems,
        "detail": "; ".join(problems[:SHOWN_REFS])
        + (f" (và {len(problems) - SHOWN_REFS} chỗ khác)" if len(problems) > SHOWN_REFS else ""),
    }


def verify(
    left: pl.DataFrame,
    right: pl.DataFrame,
    results: list[dict[str, Any]],
    config: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Trả về {"passed": bool, "checks": [...]} với từng điều kiện và chỗ sai (nếu có)."""
    tolerance = Decimal(str(config.get("tolerance", "0")))
    sides = {
        "A": (_amounts(left, config["amount_left"]), "left_refs", "amount_left"),
        "B": (_amounts(right, config["amount_right"]), "right_refs", "amount_right"),
    }
    checks: list[dict[str, Any]] = []

    # 1. Mỗi dòng của A và B nằm trong đúng một kết quả; mọi số dòng trỏ tới dòng có thật.
    for side, (amounts, refs_key, _) in sides.items():
        seen = Counter(ref for item in results for ref in item[refs_key])
        problems = [f"dòng {ref} không có thật" for ref in sorted(set(seen) - set(amounts))]
        problems += [f"dòng {ref} chưa có kết quả" for ref in sorted(set(amounts) - set(seen))]
        problems += [
            f"dòng {ref} nằm trong {count} kết quả"
            for ref, count in sorted(seen.items())
            if count > 1
        ]
        label = f"Mỗi dòng bên {side} có đúng một kết quả"
        checks.append(_check(f"COVERAGE_{side}", label, problems))

    # 2. Số tiền ghi trên kết quả đúng bằng tổng tiền của các dòng nó trỏ tới, và tổng tiền
    #    mỗi bên được bảo toàn.
    for side, (amounts, refs_key, amount_key) in sides.items():
        problems = []
        total_results = Decimal("0")
        for index, item in enumerate(results):
            values = [amounts.get(ref) for ref in item[refs_key]]
            expected = (
                None
                if not values or all(value is None for value in values)
                else sum((value or Decimal("0") for value in values), Decimal("0"))
            )
            stored = _decimal(item[amount_key])
            if stored != expected:
                problems.append(f"kết quả {index + 1} ghi {stored}, dòng gốc là {expected}")
            total_results += stored or 0
        total_source = sum((value or Decimal("0") for value in amounts.values()), Decimal("0"))
        if total_results != total_source:
            problems.append(f"tổng trên kết quả {total_results} ≠ tổng bảng {total_source}")
        checks.append(_check(f"AMOUNT_{side}", f"Tổng tiền bên {side} được bảo toàn", problems))

    # 3. Loại kết quả đúng với dữ liệu: khớp thì tiền trong sai số, lệch thì ngoài sai số,
    #    số dòng mỗi bên đúng hình dạng của loại.
    problems = []
    for index, item in enumerate(results):
        kind, count_a, count_b = item["kind"], len(item["left_refs"]), len(item["right_refs"])
        shape = SHAPES.get(kind)
        label = f"kết quả {index + 1} ({kind})"
        if shape is None:
            problems.append(f"{label}: loại không hợp lệ")
            continue
        if shape == (-1, -1):
            if count_a + count_b != 1:
                problems.append(f"{label}: phải có đúng một dòng")
            continue
        if (count_a, count_b) != shape:
            problems.append(f"{label}: sai số dòng mỗi bên")
            continue
        if kind in ("MATCHED", "AMOUNT_MISMATCH"):
            a = sides["A"][0].get(item["left_refs"][0])
            b = sides["B"][0].get(item["right_refs"][0])
            within = a is not None and b is not None and abs(a - b) <= tolerance
            if within != (kind == "MATCHED"):
                problems.append(f"{label}: số tiền {a} và {b} không đúng với loại")
    checks.append(_check("KIND_RULES", "Loại kết quả đúng với dữ liệu", problems))

    # 4. Số kết quả theo từng loại cộng lại đúng tổng và đúng với bảng tóm tắt.
    counted = Counter(item["kind"] for item in results)
    stored_counts = summary.get("counts", {})
    problems = [
        f"{kind}: tóm tắt ghi {stored_counts.get(kind, 0)}, đếm được {counted.get(kind, 0)}"
        for kind in sorted(set(counted) | set(stored_counts))
        if stored_counts.get(kind, 0) != counted.get(kind, 0)
    ]
    if summary.get("total_results") != len(results):
        problems.append(f"tổng tóm tắt {summary.get('total_results')} ≠ {len(results)} kết quả")
    checks.append(_check("COUNTS", "Số kết quả theo loại cộng lại đúng tổng", problems))

    return {"passed": all(check["passed"] for check in checks), "checks": checks}
