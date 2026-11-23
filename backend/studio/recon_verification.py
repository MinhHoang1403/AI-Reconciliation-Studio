"""Kiểm chứng kết quả đối soát, độc lập với engine (docs/ARCHITECTURE.md 5.3).

Module này không gọi lại engine: nó chỉ đọc hai bảng sạch đã dùng (và các dòng chờ mang sang
từ kỳ trước) cùng danh sách kết quả đã lưu (dạng dict như trong cơ sở dữ liệu), rồi tự đếm và
cộng lại. Nhờ vậy, lỗi của engine hay kết quả bị sửa tay trong cơ sở dữ liệu đều bị phát hiện.
Kiểm chứng không đạt thì lần đối soát bị đánh dấu không dùng được cho báo cáo.
"""

from collections import Counter
from decimal import Decimal
from typing import Any

import polars as pl

from studio.reading import ROW_REF

# Hình dạng của từng loại: (số dòng A tối thiểu, tối đa, số dòng B tối thiểu, tối đa).
# Số dòng A gồm cả dòng chờ từ kỳ trước. None là không giới hạn.
SHAPES: dict[str, tuple[int, int | None, int, int | None]] = {
    "MATCHED": (1, 1, 1, 1),
    "MANY_TO_ONE": (2, None, 1, 1),
    "ONE_TO_MANY": (1, 1, 2, None),
    "AMOUNT_MISMATCH": (1, None, 1, None),
    "AMBIGUOUS": (1, None, 1, None),
    "ONLY_IN_A": (1, 1, 0, 0),
    "PENDING_SETTLEMENT": (1, 1, 0, 0),
    "ONLY_IN_B": (0, 0, 1, 1),
}
# Loại chỉ có đúng một dòng ở một bên bất kỳ.
SINGLE_KINDS = ("DUPLICATE", "NEEDS_CLEANING", "OUT_OF_SCOPE")
SHOWN_REFS = 5  # số chỗ sai tối đa ghi trong chi tiết

type RowKey = tuple[str, int]  # (bảng gốc: "" là bảng hiện tại, số dòng)


def _amounts(frame: pl.DataFrame, column: str, origin: str = "") -> dict[RowKey, Decimal | None]:
    refs = frame[ROW_REF].to_list()
    origins = frame["__origin"].to_list() if "__origin" in frame.columns else [origin] * len(refs)
    values = frame[column].to_list() if column in frame.columns else [None] * len(refs)
    return {(str(o), ref): value for o, ref, value in zip(origins, refs, values, strict=True)}


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _sum(values: list[Decimal | None]) -> Decimal | None:
    if not values or all(value is None for value in values):
        return None
    return sum((value or Decimal("0") for value in values), Decimal("0"))


def _check(code: str, label: str, problems: list[str]) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "passed": not problems,
        "detail": "; ".join(problems[:SHOWN_REFS])
        + (f" (và {len(problems) - SHOWN_REFS} chỗ khác)" if len(problems) > SHOWN_REFS else ""),
    }


def _left_keys(item: dict[str, Any]) -> list[RowKey]:
    return [("", ref) for ref in item["left_refs"]] + [
        (str(row["table_id"]), row["row_ref"]) for row in item.get("carried_left") or []
    ]


def _right_keys(item: dict[str, Any]) -> list[RowKey]:
    return [("", ref) for ref in item["right_refs"]]


def _label(key: RowKey) -> str:
    return f"dòng {key[1]}" + (" (kỳ trước)" if key[0] else "")


def verify(
    left: pl.DataFrame,
    right: pl.DataFrame,
    results: list[dict[str, Any]],
    config: dict[str, Any],
    summary: dict[str, Any],
    carried: pl.DataFrame | None = None,
) -> dict[str, Any]:
    """Trả về {"passed": bool, "checks": [...]} với từng điều kiện và chỗ sai (nếu có)."""
    tolerance = Decimal(str(config.get("tolerance", "0")))
    left_amounts = _amounts(left, config["amount_left"])
    if carried is not None and carried.height:
        left_amounts |= _amounts(carried, config["amount_left"])
    right_amounts = _amounts(right, config["amount_right"])
    sides: dict[str, tuple[dict[RowKey, Decimal | None], Any, str]] = {
        "A": (left_amounts, _left_keys, "amount_left"),
        "B": (right_amounts, _right_keys, "amount_right"),
    }
    checks: list[dict[str, Any]] = []

    # 1. Mỗi dòng của A (kể cả dòng chờ từ kỳ trước) và B nằm trong đúng một kết quả; mọi số
    #    dòng trỏ tới dòng có thật.
    for side, (amounts, keys_of, _) in sides.items():
        seen = Counter(key for item in results for key in keys_of(item))
        problems = [f"{_label(key)} không có thật" for key in sorted(set(seen) - set(amounts))]
        problems += [f"{_label(key)} chưa có kết quả" for key in sorted(set(amounts) - set(seen))]
        problems += [
            f"{_label(key)} nằm trong {count} kết quả"
            for key, count in sorted(seen.items())
            if count > 1
        ]
        label = f"Mỗi dòng bên {side} có đúng một kết quả"
        checks.append(_check(f"COVERAGE_{side}", label, problems))

    # 2. Số tiền ghi trên kết quả đúng bằng tổng tiền của các dòng nó trỏ tới, và tổng tiền
    #    mỗi bên được bảo toàn.
    for side, (amounts, keys_of, amount_key) in sides.items():
        problems = []
        total_results = Decimal("0")
        for index, item in enumerate(results):
            expected = _sum([amounts.get(key) for key in keys_of(item)])
            stored = _decimal(item[amount_key])
            if stored != expected:
                problems.append(f"kết quả {index + 1} ghi {stored}, dòng gốc là {expected}")
            total_results += stored or 0
        total_source = sum((value or Decimal("0") for value in amounts.values()), Decimal("0"))
        if total_results != total_source:
            problems.append(f"tổng trên kết quả {total_results} ≠ tổng bảng {total_source}")
        checks.append(_check(f"AMOUNT_{side}", f"Tổng tiền bên {side} được bảo toàn", problems))

    # 3. Loại kết quả đúng với dữ liệu: số dòng mỗi bên đúng hình dạng của loại; khớp thì tổng
    #    tiền hai bên bằng nhau (1:1 trong sai số, nhóm thì bằng đúng), lệch thì ngược lại.
    problems = []
    for index, item in enumerate(results):
        kind = item["kind"]
        lefts, rights = _left_keys(item), [("", ref) for ref in item["right_refs"]]
        label = f"kết quả {index + 1} ({kind})"
        if kind in SINGLE_KINDS:
            if len(lefts) + len(rights) != 1:
                problems.append(f"{label}: phải có đúng một dòng")
            continue
        shape = SHAPES.get(kind)
        if shape is None:
            problems.append(f"{label}: loại không hợp lệ")
            continue
        low_a, high_a, low_b, high_b = shape
        if not (
            low_a <= len(lefts) <= (high_a if high_a is not None else len(lefts))
            and low_b <= len(rights) <= (high_b if high_b is not None else len(rights))
        ):
            problems.append(f"{label}: sai số dòng mỗi bên")
            continue
        if kind == "AMBIGUOUS" and len(lefts) + len(rights) < 3:
            problems.append(f"{label}: ca mơ hồ phải có ít nhất ba dòng")
            continue
        if kind in ("MATCHED", "MANY_TO_ONE", "ONE_TO_MANY", "AMOUNT_MISMATCH"):
            a = _sum([left_amounts.get(key) for key in lefts])
            b = _sum([right_amounts.get(key) for key in rights])
            allowed = tolerance if len(lefts) == 1 and len(rights) == 1 else Decimal("0")
            within = a is not None and b is not None and abs(a - b) <= allowed
            if within != (kind != "AMOUNT_MISMATCH"):
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
