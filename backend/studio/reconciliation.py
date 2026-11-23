"""Engine đối soát hai bộ dữ liệu sạch A ↔ B (docs/ARCHITECTURE.md mục 5).

Theo các bước kinh điển của bài toán ghép bản ghi (Christen, *Data Matching*, 2012):
chọn trường → lọc ứng viên → so sánh từng trường → phân loại. Thứ tự các vòng theo khuyến
nghị của Oracle Cash Management: quy tắc chắc chắn (khớp khóa 1:1) chạy trước, sau đó mới
tới khớp theo điểm.

1. Ngoài phạm vi: dòng có giá trị phân loại không bao giờ xuất hiện ở bên kia (ví dụ đơn trả
   tiền mặt khi đối với cổng thanh toán), suy từ dữ liệu, người dùng đổi lại được.
2. Dữ liệu chưa sạch: dòng còn vấn đề mức "Hỏi" chưa xử lý thì không ghép, chỉ ra để sửa.
3. Khớp khóa 1:1: cùng mã. Lệch tiền ngoài sai số → AMOUNT_MISMATCH; cùng mã nhiều dòng
   → ghép cặp tốt nhất, phần thừa là DUPLICATE.
4. Khớp theo điểm 1:1 cho phần còn lại: ứng viên phải cùng số tiền (trong sai số) và gần
   ngày; điểm từ ngày, độ giống mã, độ giống tên (RapidFuzz); chọn cặp bằng phân công tối ưu
   `scipy.optimize.linear_sum_assignment`. Cặp có đối thủ ngang điểm thì không tự chọn.
5. Còn lại: ONLY_IN_A / ONLY_IN_B.

Engine là code thuần: cùng đầu vào luôn cho cùng kết quả, kể cả khi thứ tự dòng bị xáo trộn
(mọi bước đều sắp theo số dòng gốc). AI không tham gia quyết định ở đây.
"""

import bisect
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, cast

import numpy as np
import polars as pl
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from studio.reading import ROW_REF
from studio.sales_fields import FIELDS_BY_KEY

# Các loại kết quả. OUT_OF_SCOPE và NEEDS_CLEANING bổ sung cho danh sách ở kiến trúc để mọi
# dòng đều nằm trong đúng một kết quả (điều kiện của bước kiểm chứng).
KINDS = (
    "MATCHED",
    "AMOUNT_MISMATCH",
    "DUPLICATE",
    "ONLY_IN_A",
    "ONLY_IN_B",
    "NEEDS_CLEANING",
    "OUT_OF_SCOPE",
)
# Trọng số điểm khớp vòng 2 (chỉ tính các thành phần cả hai bên đều có).
SCORE_WEIGHTS = {"date": 0.5, "key": 0.3, "name": 0.2}
# Cột phân loại có thể dùng để để dòng ra ngoài phạm vi (trạng thái đơn xử lý riêng).
SCOPE_FIELDS = ("payment_method",)
# Một giá trị bị coi là ngoài phạm vi khi không dòng nào của nó khớp mã với bên kia, trong khi
# giá trị khớp nhiều nhất đạt ít nhất tỷ lệ này.
SCOPE_MIN_OTHER_RATE = 0.5


@dataclass
class ReconConfig:
    """Cấu hình đối soát: trường so khớp của mỗi bên, sai số, phạm vi."""

    key_left: str | None
    key_right: str | None
    amount_left: str
    amount_right: str
    date_left: str | None = None
    date_right: str | None = None
    tolerance: Decimal = Decimal("0")  # sai số tiền tuyệt đối (đồng)
    date_window_days: int = 3  # khung ngày cho khớp theo điểm
    min_score: float = 0.7
    # Giá trị phân loại để ngoài phạm vi: {"LEFT": {"payment_method": ["Tiền mặt"]}}
    excluded: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["tolerance"] = str(self.tolerance)
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ReconConfig":
        # Bỏ các khóa chỉ để hiển thị (nhãn, mô tả) nếu dữ liệu đến từ giao diện.
        values = {name: data[name] for name in cls.__dataclass_fields__ if name in data}
        values["tolerance"] = Decimal(str(values.get("tolerance", "0")))
        return cls(**values)


@dataclass
class Row:
    ref: int
    key: str | None
    amount: Decimal | None
    day: date | None
    name: str | None
    cancelled: bool
    category: dict[str, str | None]


@dataclass
class Result:
    kind: str
    left_refs: list[int]
    right_refs: list[int]
    reasons: list[dict[str, str]]
    score: float | None = None
    amount_left: Decimal | None = None
    amount_right: Decimal | None = None
    needs_review: bool = False


@dataclass
class Side:
    """Một bên đối soát: bảng sạch và các dòng còn vấn đề mức "Hỏi" chưa xử lý."""

    frame: pl.DataFrame
    unclean_refs: set[int] = field(default_factory=set)


# ---------------------------------------------------------------- tiện ích


def money_vi(value: Decimal | None) -> str:
    """2195000 → '2.195.000đ' để đưa vào lý do."""
    if value is None:
        return "trống"
    sign = "-" if value < 0 else ""
    whole = f"{int(abs(value)):,}".replace(",", ".")
    fraction = abs(value) % 1
    text = whole if fraction == 0 else f"{whole},{str(fraction.quantize(Decimal('0.01')))[2:]}"
    return f"{sign}{text}đ"


def _reason(code: str, text: str) -> dict[str, str]:
    return {"code": code, "text": text}


def _rows(frame: pl.DataFrame, key: str | None, amount: str, day: str | None) -> list[Row]:
    """Đọc các trường cần cho đối soát, sắp theo số dòng gốc để kết quả không phụ thuộc thứ tự."""
    frame = frame.sort(ROW_REF)

    def column(name: str | None) -> list[Any]:
        if name is None or name not in frame.columns:
            return [None] * frame.height
        return frame[name].to_list()

    categories = {name: column(name) for name in SCOPE_FIELDS}
    return [
        Row(
            ref=ref,
            key=key_value,
            amount=amount_value,
            day=day_value,
            name=name_value,
            cancelled=bool(cancelled),
            category={name: values[index] for name, values in categories.items()},
        )
        for index, (ref, key_value, amount_value, day_value, name_value, cancelled) in enumerate(
            zip(
                frame[ROW_REF].to_list(),
                column(key),
                column(amount),
                column(day),
                column("customer_name_key"),
                column("is_cancelled"),
                strict=True,
            )
        )
    ]


def _within(a: Decimal | None, b: Decimal | None, tolerance: Decimal) -> bool:
    return a is not None and b is not None and abs(a - b) <= tolerance


def _days_apart(a: date | None, b: date | None) -> int | None:
    return None if a is None or b is None else abs((a - b).days)


# ---------------------------------------------------------------- chọn trường đối soát


def _fields_of(frame: pl.DataFrame, field_type: str) -> list[str]:
    return [
        name
        for name in frame.columns
        if name in FIELDS_BY_KEY and FIELDS_BY_KEY[name].type == field_type
    ]


def _key_stats(left: pl.Series, right: pl.Series) -> dict[str, float]:
    """Độ phủ, độ duy nhất và tỷ lệ khớp thử của một cặp cột mã."""
    left_values = [value for value in left.to_list() if value]
    right_values = [value for value in right.to_list() if value]
    right_set = set(right_values)
    matched = sum(value in right_set for value in left_values)
    return {
        "match_rate": matched / len(left_values) if left_values else 0.0,
        "fill": min(
            len(left_values) / max(len(left), 1), len(right_values) / max(len(right), 1)
        ),
        "unique": min(
            len(set(left_values)) / max(len(left_values), 1),
            len(right_set) / max(len(right_values), 1),
        ),
    }


def suggest_config(left: pl.DataFrame, right: pl.DataFrame) -> tuple[ReconConfig, dict[str, Any]]:
    """Tự chọn trường đối soát từ cột chuẩn có ở cả hai bên (ARCHITECTURE 5.1).

    Khóa: chấm theo tỷ lệ khớp thử (60%), độ phủ (20%), độ duy nhất (20%).
    Tiền: cặp cột có tỷ lệ bằng nhau cao nhất trên các dòng cùng khóa.
    Ngày: cặp cột có độ lệch ngày trung vị nhỏ nhất trên các dòng cùng khóa.
    Trả về cấu hình và bằng chứng (các con số đã dùng để chọn) cho giao diện.
    """
    evidence: dict[str, Any] = {"keys": [], "amounts": [], "dates": []}
    best_key: tuple[float, str, str] | None = None
    for left_candidate in _fields_of(left, "IDENTIFIER"):
        for right_candidate in _fields_of(right, "IDENTIFIER"):
            stats = _key_stats(left[left_candidate], right[right_candidate])
            score = 0.6 * stats["match_rate"] + 0.2 * stats["fill"] + 0.2 * stats["unique"]
            evidence["keys"].append({"left": left_candidate, "right": right_candidate, **stats})
            if stats["match_rate"] >= 0.05 and (best_key is None or score > best_key[0]):
                best_key = (score, left_candidate, right_candidate)
    key_left: str | None = best_key[1] if best_key else None
    key_right: str | None = best_key[2] if best_key else None

    joined: pl.DataFrame | None = None
    if key_left and key_right:
        joined = left.filter(pl.col(key_left).is_not_null()).join(
            right.filter(pl.col(key_right).is_not_null()),
            left_on=key_left,
            right_on=key_right,
            how="inner",
            suffix="__b",
        )

    def right_name(name: str) -> str:
        # Sau khi nối, cột trùng tên của bên B có hậu tố "__b".
        return f"{name}__b" if joined is not None and f"{name}__b" in joined.columns else name

    amount_pairs = [
        (a, b) for a in _fields_of(left, "MONEY") for b in _fields_of(right, "MONEY")
    ]
    if not amount_pairs:
        raise ValueError("Hai bảng cần có cột số tiền để đối soát.")
    best_amount = (-1.0, amount_pairs[0])
    for a, b in amount_pairs:
        if joined is not None and joined.height:
            equal = (joined[a] == joined[right_name(b)]).fill_null(False).mean()
            rate = float(cast(float | None, equal) or 0.0)
        else:
            rate = 1.0 if a == b else 0.0
        evidence["amounts"].append({"left": a, "right": b, "equal_rate": rate})
        # Cùng tỷ lệ thì ưu tiên cặp cùng tên cột chuẩn (ví dụ amount ↔ amount).
        if (rate, a == b) > (best_amount[0], best_amount[1][0] == best_amount[1][1]):
            best_amount = (rate, (a, b))

    date_pairs = [(a, b) for a in _fields_of(left, "DATE") for b in _fields_of(right, "DATE")]
    best_date: tuple[float, tuple[str, str]] | None = None
    for a, b in date_pairs:
        median = 0.0
        if joined is not None and joined.height:
            gaps = (joined[a] - joined[right_name(b)]).dt.total_days().abs().drop_nulls()
            middle = cast(float | None, gaps.median())
            median = float(middle or 0.0) if len(gaps) else 999.0
        evidence["dates"].append({"left": a, "right": b, "median_days": median})
        if best_date is None or median < best_date[0]:
            best_date = (median, (a, b))

    config = ReconConfig(
        key_left=key_left,
        key_right=key_right,
        amount_left=best_amount[1][0],
        amount_right=best_amount[1][1],
        date_left=best_date[1][0] if best_date else None,
        date_right=best_date[1][1] if best_date else None,
    )
    config.excluded, evidence["scope"] = _suggest_scope(left, right, config)
    return config, evidence


def _suggest_scope(
    left: pl.DataFrame, right: pl.DataFrame, config: ReconConfig
) -> tuple[dict[str, dict[str, list[str]]], list[dict[str, Any]]]:
    """Giá trị phân loại không bao giờ khớp mã với bên kia thì để ngoài phạm vi.

    Ví dụ đơn cửa hàng ↔ cổng thanh toán: đơn "Tiền mặt" và "Chuyển khoản" không có giao dịch
    cổng nào cùng mã, còn đơn "Thẻ/QR" khớp gần hết → hai giá trị đầu ngoài phạm vi.
    """
    excluded: dict[str, dict[str, list[str]]] = {}
    evidence: list[dict[str, Any]] = []
    if not (config.key_left and config.key_right):
        return excluded, evidence
    for side, own, other, own_key, other_key in (
        ("LEFT", left, right, config.key_left, config.key_right),
        ("RIGHT", right, left, config.key_right, config.key_left),
    ):
        other_keys = set(other[other_key].drop_nulls().to_list())
        for name in SCOPE_FIELDS:
            if name not in own.columns:
                continue
            rates: dict[str, tuple[int, int]] = {}
            for value, key in zip(own[name].to_list(), own[own_key].to_list(), strict=True):
                if value is None:
                    continue
                total, hits = rates.get(value, (0, 0))
                rates[value] = (total + 1, hits + (key is not None and key in other_keys))
            best = max((hits / total for total, hits in rates.values()), default=0.0)
            for value, (total, hits) in sorted(rates.items()):
                out = hits == 0 and best >= SCOPE_MIN_OTHER_RATE
                evidence.append(
                    {"side": side, "field": name, "value": value, "rows": total,
                     "matched": hits, "excluded": out}
                )
                if out:
                    excluded.setdefault(side, {}).setdefault(name, []).append(value)
    return excluded, evidence


# ---------------------------------------------------------------- các vòng khớp


def _pair_result(left: Row, right: Row, config: ReconConfig, how: str) -> Result:
    """Kết quả cho một cặp đã ghép: khớp hay lệch tiền, kèm lý do."""
    reasons = [_reason("KEY", f"Cùng mã {left.key}.")] if how == "KEY" else []
    gap = _days_apart(left.day, right.day)
    if _within(left.amount, right.amount, config.tolerance):
        kind = "MATCHED"
        reasons.append(_reason("AMOUNT_EQUAL", f"Số tiền khớp: {money_vi(left.amount)}."))
    else:
        kind = "AMOUNT_MISMATCH"
        difference = (
            None if left.amount is None or right.amount is None else right.amount - left.amount
        )
        reasons.append(
            _reason(
                "AMOUNT_DIFF",
                f"Lệch tiền: A {money_vi(left.amount)}, B {money_vi(right.amount)}"
                + (f" (B {'thừa' if difference > 0 else 'thiếu'} {money_vi(abs(difference))})."
                   if difference is not None else "."),
            )
        )
    if gap is not None:
        reasons.append(
            _reason("DATE", "Cùng ngày." if gap == 0 else f"Cách nhau {gap} ngày.")
        )
    needs_review = kind != "MATCHED"
    if left.cancelled or right.cancelled:
        reasons.append(
            _reason("CANCELLED_BUT_PAID", "Đơn đã hủy nhưng vẫn có giao dịch tương ứng.")
        )
        needs_review = True
    return Result(
        kind=kind,
        left_refs=[left.ref],
        right_refs=[right.ref],
        reasons=reasons,
        amount_left=left.amount,
        amount_right=right.amount,
        needs_review=needs_review,
    )


def _key_round(
    left: list[Row], right: list[Row], config: ReconConfig
) -> tuple[list[Result], set[int], set[int]]:
    """Khớp khóa 1:1. Trả về kết quả và tập số dòng A, B đã dùng."""
    results: list[Result] = []
    used_left: set[int] = set()
    used_right: set[int] = set()
    by_key_left: dict[str, list[Row]] = defaultdict(list)
    by_key_right: dict[str, list[Row]] = defaultdict(list)
    for row in left:
        if row.key is not None:
            by_key_left[row.key].append(row)
    for row in right:
        if row.key is not None:
            by_key_right[row.key].append(row)

    for key in sorted(by_key_left.keys() & by_key_right.keys()):
        lefts, rights = list(by_key_left[key]), list(by_key_right[key])
        paired: list[tuple[Row, Row]] = []
        # Cùng mã nhiều dòng: ghép lần lượt cặp tốt nhất (đúng tiền trước, gần ngày, dòng sớm).
        while lefts and rights:
            best = min(
                ((a, b) for a in lefts for b in rights),
                key=lambda pair: (
                    not _within(pair[0].amount, pair[1].amount, config.tolerance),
                    _days_apart(pair[0].day, pair[1].day) or 0,
                    pair[0].ref,
                    pair[1].ref,
                ),
            )
            paired.append(best)
            lefts.remove(best[0])
            rights.remove(best[1])
        for a, b in paired:
            results.append(_pair_result(a, b, config, "KEY"))
            used_left.add(a.ref)
            used_right.add(b.ref)
        counterpart = paired[0]
        for extra, side in [(row, "A") for row in lefts] + [(row, "B") for row in rights]:
            other = counterpart[1] if side == "A" else counterpart[0]
            results.append(
                Result(
                    kind="DUPLICATE",
                    left_refs=[extra.ref] if side == "A" else [],
                    right_refs=[extra.ref] if side == "B" else [],
                    reasons=[
                        _reason(
                            "DUPLICATE_KEY",
                            f"Trùng mã {key} với dòng {other.ref} bên "
                            f"{'B' if side == 'A' else 'A'} đã được ghép "
                            f"(số tiền {money_vi(extra.amount)}).",
                        )
                    ],
                    amount_left=extra.amount if side == "A" else None,
                    amount_right=extra.amount if side == "B" else None,
                    needs_review=True,
                )
            )
            (used_left if side == "A" else used_right).add(extra.ref)
    return results, used_left, used_right


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
        parts["name"] = fuzz.token_sort_ratio(a.name, b.name) / 100
    if not parts:
        return None  # chỉ trùng số tiền thì quá yếu để ghép
    weight = sum(SCORE_WEIGHTS[name] for name in parts)
    return round(sum(SCORE_WEIGHTS[name] * value for name, value in parts.items()) / weight, 6)


def _score_round(
    left: list[Row], right: list[Row], config: ReconConfig
) -> tuple[list[Result], set[int], set[int], dict[tuple[str, int], int]]:
    """Khớp theo điểm 1:1 bằng phân công tối ưu; cặp có đối thủ ngang điểm thì để lại.

    Trả về kết quả, số dòng đã dùng và số ứng viên ngang điểm của các dòng bị để lại.
    """
    by_amount: dict[Decimal, list[Row]] = defaultdict(list)
    for row in right:
        if row.amount is not None:
            by_amount[row.amount].append(row)
    sorted_amounts = sorted(by_amount)

    candidates: dict[tuple[int, int], float] = {}
    for a in left:
        if a.amount is None:
            continue
        # Lọc ứng viên (blocking): chỉ xét số tiền trong sai số, không so mọi cặp.
        low = bisect.bisect_left(sorted_amounts, a.amount - config.tolerance)
        for amount in sorted_amounts[low:]:
            if amount > a.amount + config.tolerance:
                break
            for b in by_amount[amount]:
                score = _pair_score(a, b, config)
                if score is not None and score >= config.min_score:
                    candidates[(a.ref, b.ref)] = score
    if not candidates:
        return [], set(), set(), {}

    left_refs = sorted({pair[0] for pair in candidates})
    right_refs = sorted({pair[1] for pair in candidates})
    row_index = {ref: index for index, ref in enumerate(left_refs)}
    col_index = {ref: index for index, ref in enumerate(right_refs)}
    # Ma trận chi phí = -điểm; cặp không phải ứng viên có chi phí 0 (không lợi gì khi chọn).
    cost = np.zeros((len(left_refs), len(right_refs)))
    for (a_ref, b_ref), score in candidates.items():
        cost[row_index[a_ref], col_index[b_ref]] = -score
    rows, cols = linear_sum_assignment(cost)

    left_by_ref = {row.ref: row for row in left}
    right_by_ref = {row.ref: row for row in right}
    results: list[Result] = []
    used_left: set[int] = set()
    used_right: set[int] = set()
    ties: dict[tuple[str, int], int] = {}  # (bên, số dòng) → số ứng viên ngang điểm
    for r, c in zip(rows, cols, strict=True):
        a_ref, b_ref = left_refs[r], right_refs[c]
        score = candidates.get((a_ref, b_ref))
        if score is None:
            continue
        rivals = [
            pair
            for pair, other in candidates.items()
            if other == score and pair != (a_ref, b_ref) and (pair[0] == a_ref or pair[1] == b_ref)
        ]
        if rivals:  # có ứng viên khác ngang điểm: không tự chọn
            ties[("A", a_ref)] = ties[("B", b_ref)] = len(rivals) + 1
            continue
        a, b = left_by_ref[a_ref], right_by_ref[b_ref]
        result = _pair_result(a, b, config, "SCORE")
        detail = [f"điểm {score:.2f}"]
        if a.key and b.key and a.key != b.key:
            detail.append(f"mã khác nhau ({a.key} / {b.key}), có thể gõ sai")
        elif not (a.key and b.key):
            detail.append("một bên không ghi mã")
        result.reasons.insert(
            0, _reason("SCORE", "Ghép theo số tiền và ngày: " + ", ".join(detail) + ".")
        )
        result.score = score
        results.append(result)
        used_left.add(a_ref)
        used_right.add(b_ref)
    return results, used_left, used_right, ties


# ---------------------------------------------------------------- chạy toàn bộ


def _scope_reason(row: Row, excluded: dict[str, list[str]]) -> str | None:
    for name, values in excluded.items():
        value = row.category.get(name)
        if value is not None and value in values:
            label = FIELDS_BY_KEY[name].label.lower() if name in FIELDS_BY_KEY else name
            return f"Ngoài phạm vi: {label} “{value}” không đi qua bên kia."
    return None


def reconcile(left: Side, right: Side, config: ReconConfig) -> list[Result]:
    """Đối soát A ↔ B; mỗi dòng của hai bên nằm trong đúng một kết quả."""
    rows_left = _rows(left.frame, config.key_left, config.amount_left, config.date_left)
    rows_right = _rows(right.frame, config.key_right, config.amount_right, config.date_right)
    results: list[Result] = []

    def single(kind: str, row: Row, side: str, reasons: list[dict[str, str]], review: bool) -> None:
        results.append(
            Result(
                kind=kind,
                left_refs=[row.ref] if side == "A" else [],
                right_refs=[row.ref] if side == "B" else [],
                reasons=reasons,
                amount_left=row.amount if side == "A" else None,
                amount_right=row.amount if side == "B" else None,
                needs_review=review,
            )
        )

    # 1–2. Ngoài phạm vi và dữ liệu chưa sạch: không tham gia ghép.
    pools: dict[str, list[Row]] = {}
    for side, rows, source, scope in (
        ("A", rows_left, left, config.excluded.get("LEFT", {})),
        ("B", rows_right, right, config.excluded.get("RIGHT", {})),
    ):
        pool = []
        for row in rows:
            out = _scope_reason(row, scope)
            if out:
                single("OUT_OF_SCOPE", row, side, [_reason("SCOPE", out)], False)
            elif row.ref in source.unclean_refs:
                single(
                    "NEEDS_CLEANING",
                    row,
                    side,
                    [_reason("NOT_CLEAN", "Dòng còn vấn đề chưa xử lý ở bước làm sạch.")],
                    True,
                )
            else:
                pool.append(row)
        pools[side] = pool

    # 3. Khớp khóa 1:1.
    matched, used_left, used_right = _key_round(pools["A"], pools["B"], config)
    results += matched
    rest_left = [row for row in pools["A"] if row.ref not in used_left]
    rest_right = [row for row in pools["B"] if row.ref not in used_right]

    # 4. Khớp theo điểm 1:1 cho phần còn lại.
    scored, used_left, used_right, ties = _score_round(rest_left, rest_right, config)
    results += scored

    # 5. Còn lại: chỉ có ở một bên.
    for side, rows, used in (("A", rest_left, used_left), ("B", rest_right, used_right)):
        for row in rows:
            if row.ref in used:
                continue
            if side == "A" and row.cancelled:
                single(
                    "OUT_OF_SCOPE",
                    row,
                    side,
                    [_reason("CANCELLED", "Đơn đã hủy, không cần có tiền về.")],
                    False,
                )
                continue
            reasons = [
                _reason(
                    "NO_MATCH",
                    f"Không có dòng tương ứng ở bên {'B' if side == 'A' else 'A'}"
                    + (f" (mã {row.key})" if row.key else "")
                    + ".",
                )
            ]
            if (side, row.ref) in ties:
                reasons.append(
                    _reason(
                        "TIED",
                        f"Có {ties[(side, row.ref)]} ứng viên ngang điểm nên không tự ghép.",
                    )
                )
            single("ONLY_IN_A" if side == "A" else "ONLY_IN_B", row, side, reasons, True)

    # Thứ tự cố định: theo loại, rồi theo số dòng gốc.
    order = {kind: index for index, kind in enumerate(KINDS)}
    results.sort(
        key=lambda item: (
            order[item.kind],
            item.left_refs[0] if item.left_refs else 10**12,
            item.right_refs[0] if item.right_refs else 10**12,
        )
    )
    return results


def summarize(results: list[Result]) -> dict[str, Any]:
    """Số kết quả, số dòng và tổng tiền mỗi bên theo từng loại."""
    counts = {kind: 0 for kind in KINDS}
    rows = {kind: {"A": 0, "B": 0} for kind in KINDS}
    money = {kind: {"A": Decimal("0"), "B": Decimal("0")} for kind in KINDS}
    for item in results:
        counts[item.kind] += 1
        rows[item.kind]["A"] += len(item.left_refs)
        rows[item.kind]["B"] += len(item.right_refs)
        money[item.kind]["A"] += item.amount_left or 0
        money[item.kind]["B"] += item.amount_right or 0
    return {
        "counts": counts,
        "rows": rows,
        "amounts": {
            kind: {side: str(value) for side, value in sides.items()}
            for kind, sides in money.items()
        },
        "total_results": len(results),
        "needs_review": sum(item.needs_review for item in results),
    }
