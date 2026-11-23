"""Engine đối soát hai bộ dữ liệu sạch A ↔ B (docs/ARCHITECTURE.md mục 5).

Theo các bước kinh điển của bài toán ghép bản ghi (Christen, *Data Matching*, 2012):
chọn trường → lọc ứng viên → so sánh từng trường → phân loại. Thứ tự các vòng theo khuyến
nghị của Oracle Cash Management: quy tắc chắc chắn chạy trước, rồi tới khớp theo điểm, khớp
nhóm theo tổng tiền (không sai số), còn lại mới phân loại.

0. Lựa chọn của người dùng (ca mơ hồ đã chọn) được áp dụng trước tiên.
1. Ngoài phạm vi: giá trị phân loại không bao giờ khớp với bên kia (ví dụ đơn tiền mặt khi đối
   với cổng thanh toán), tiền ra (cột Nợ của sao kê) khi đối soát bán hàng.
2. Dữ liệu chưa sạch: dòng còn vấn đề mức "Hỏi" thì không ghép, chỉ ra để sửa.
3. Khớp theo mã: mã ở cột hoặc tách từ nội dung chuyển khoản bằng mẫu tự học từ mã bên kia
   (như SePay, Casso). Một dòng B nhiều mã, hoặc bên A dùng chung mã đợt/ngày → ghép nhóm
   theo tổng tiền (MANY_TO_ONE). Cùng mã nhiều dòng 1:1 → cặp tốt nhất + DUPLICATE.
4. Khớp theo điểm 1:1: cùng số tiền (trong sai số), gần ngày; điểm từ ngày, mã, tên; chọn bằng
   `scipy.optimize.linear_sum_assignment`. Ứng viên ngang điểm → AMBIGUOUS, không tự chọn.
5. Khớp nhóm theo tổng tiền: tổ hợp tối đa MAX_GROUP_ROWS dòng có tổng đúng bằng một dòng bên
   kia; một nghiệm → MANY_TO_ONE / ONE_TO_MANY, nhiều nghiệm → AMBIGUOUS.
6. Còn lại: đơn hủy → ngoài phạm vi; còn trong khung chờ tiền về (T+N ngày làm việc tính tới
   ngày cuối của bên B) → PENDING_SETTLEMENT; dòng chờ từ kỳ trước quá hạn → ONLY_IN_A;
   phần còn lại → ONLY_IN_A / ONLY_IN_B.

Engine là code thuần: cùng đầu vào luôn cho cùng kết quả, kể cả khi thứ tự dòng bị xáo trộn
(mọi bước đều sắp theo số dòng gốc). AI không tham gia quyết định ở đây.
"""

import bisect
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import polars as pl
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from studio.reading import ROW_REF
from studio.sales_fields import FIELDS_BY_KEY
from studio.value_parsers import HONORIFICS, money_vi, name_match_key

# Các loại kết quả. OUT_OF_SCOPE và NEEDS_CLEANING bổ sung cho danh sách ở kiến trúc để mọi
# dòng đều nằm trong đúng một kết quả (điều kiện của bước kiểm chứng).
KINDS = (
    "MATCHED",
    "MANY_TO_ONE",
    "ONE_TO_MANY",
    "AMOUNT_MISMATCH",
    "AMBIGUOUS",
    "DUPLICATE",
    "ONLY_IN_A",
    "ONLY_IN_B",
    "PENDING_SETTLEMENT",
    "NEEDS_CLEANING",
    "OUT_OF_SCOPE",
)
# Trọng số điểm khớp theo điểm (chỉ tính các thành phần cả hai bên đều có).
SCORE_WEIGHTS = {"date": 0.5, "key": 0.3, "name": 0.2}
# Cột phân loại có thể dùng để để dòng ra ngoài phạm vi (trạng thái đơn xử lý riêng).
SCOPE_FIELDS = ("payment_method",)
# Một giá trị bị coi là ngoài phạm vi khi gần như không dòng nào của nó khớp mã với bên kia
# (≤ 5%, chừa chỗ cho dòng nhập nhầm), trong khi giá trị khớp nhiều nhất đạt ít nhất 50%.
SCOPE_MIN_OTHER_RATE = 0.5
SCOPE_MAX_OWN_RATE = 0.05
# Giới hạn để ghép không chậm theo bình phương số dòng khi dữ liệu có rất nhiều dòng giống nhau.
MAX_SAME_KEY_PAIRS = 10_000
MAX_CANDIDATES_PER_ROW = 50
MAX_COMPONENT_ROWS = 400
# Khớp nhóm theo tổng tiền: tối đa 5 dòng một nhóm, xét tối đa 20 ứng viên mỗi dòng
# (ARCHITECTURE 5.2: giới hạn tổ hợp để không bùng nổ).
MAX_GROUP_ROWS = 5
MAX_SUBSET_CANDIDATES = 20
# Khung chờ tiền về mặc định: 3 ngày làm việc (docs/DECISIONS.md 2026-11-23).
DEFAULT_SETTLE_DAYS = 3
# Tách mã từ nội dung: mẫu tự học phải đúng với ≥ 90% mã tách được và có ≥ 3 dòng khớp.
EXTRACT_MIN_PRECISION = 0.9
EXTRACT_MIN_HITS = 3
# Có độ trễ tiền về khi ít nhất 5% cặp đã ghép có ngày bên B sau ngày bên A.
SETTLEMENT_LAG_SHARE = 0.05
# Ngày trong nội dung chuyển khoản, kiểu Việt Nam ngày/tháng/năm.
DATE_IN_TEXT = r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)"
# Từ nghiệp vụ trong nội dung chuyển khoản, bỏ đi khi lấy tên người chuyển.
NOISE_WORDS = {
    "ck", "chuyen", "tien", "khoan", "tt", "thanh", "toan", "don", "hang", "cong", "ngay",
    "doanh", "thu", "san", "tmdt", "nhan", "ho", "qua", "cho", "mua", "ban", "ib", "ft",
    "mbvcb", "noi", "dung", "gd", "giao", "dich", "tk", "so", "tai",
}


@dataclass
class ReconConfig:
    """Cấu hình đối soát: trường so khớp của mỗi bên, sai số, phạm vi."""

    key_left: str | None
    key_right: str | None
    amount_left: str
    amount_right: str
    date_left: str | None = None
    date_right: str | None = None
    tolerance: Decimal = Decimal("0")  # sai số tiền tuyệt đối (đồng), chỉ cho ghép 1:1
    date_window_days: int = 3  # khung ngày cho khớp theo điểm và khớp nhóm
    min_score: float = 0.7
    # Giá trị phân loại để ngoài phạm vi: {"LEFT": {"payment_method": ["Tiền mặt"]}}
    excluded: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    # Tách khóa bên B từ chữ: {"source": "description", "kind": "code"|"date", "pattern": ...}
    extract: dict[str, str] | None = None
    # Bên A dùng chung khóa (mã đợt chuyển, ngày) → ghép nhóm theo tổng tiền.
    group_left: bool = False
    # Lấy tên người chuyển ở bên B từ cột chữ này (ví dụ "description" của sao kê).
    name_right: str | None = None
    # Cột tiền ra của bên B: dòng chỉ có tiền ra thì ngoài phạm vi (ví dụ "debit").
    outflow_right: str | None = None
    # Khung chờ tiền về (ngày làm việc). Mặc định 0 (không chờ); suggest_config bật
    # DEFAULT_SETTLE_DAYS khi dữ liệu cho thấy bên B ghi sau bên A (có độ trễ tiền về).
    settle_days: int = 0
    # Cặp người dùng chọn (ca mơ hồ, ghép tay): [{"left": [số dòng A], "right": [số dòng B]}].
    # Áp dụng trước mọi vòng khớp.
    forced: list[dict[str, list[int]]] = field(default_factory=list)
    # Cặp người dùng đã gỡ ghép: không vòng tự động nào được ghép bất kỳ dòng A nào trong
    # "left" với bất kỳ dòng B nào trong "right" nữa (cùng dạng với forced).
    forbidden: list[dict[str, list[int]]] = field(default_factory=list)

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
    ref: int  # số dòng gốc; dòng chờ mang sang từ kỳ trước có số âm (xem Side.carried)
    keys: list[str]
    amount: Decimal | None
    day: date | None
    name: str | None
    cancelled: bool
    category: dict[str, str | None]
    outflow: bool = False

    @property
    def key(self) -> str | None:
        return self.keys[0] if self.keys else None


@dataclass
class Result:
    kind: str
    left_refs: list[int]
    right_refs: list[int]
    reasons: list[dict[str, Any]]
    score: float | None = None
    amount_left: Decimal | None = None
    amount_right: Decimal | None = None
    needs_review: bool = False
    # Dòng chờ từ kỳ trước: [{"table_id": ..., "row_ref": ...}] (không nằm trong left_refs).
    carried_left: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Side:
    """Một bên đối soát: bảng sạch, các dòng còn vấn đề "Hỏi" chưa xử lý và (bên A) các dòng
    chờ tiền về mang sang từ kỳ trước: bảng có thêm cột "__origin" là mã bảng gốc."""

    frame: pl.DataFrame
    unclean_refs: set[int] = field(default_factory=set)
    carried: pl.DataFrame | None = None
    # Trong chuỗi ba bên: dòng đã ghép (hoặc đã báo) ở cặp khác → số dòng: lý do.
    elsewhere: dict[int, str] = field(default_factory=dict)


# ---------------------------------------------------------------- tiện ích


def money_dong(value: Decimal | None) -> str:
    """2195000 → '2.195.000đ' để đưa vào lý do."""
    return money_vi(value, "đ")


def _reason(code: str, text: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "text": text, **extra}


def _blocked(config: ReconConfig) -> set[tuple[int, int]]:
    """Các cặp (dòng A, dòng B) người dùng đã gỡ ghép, các vòng tự động phải tránh."""
    return {
        (a, b)
        for item in config.forbidden
        for a in item.get("left", [])
        for b in item.get("right", [])
    }


def _within(a: Decimal | None, b: Decimal | None, tolerance: Decimal) -> bool:
    return a is not None and b is not None and abs(a - b) <= tolerance


def _days_apart(a: date | None, b: date | None) -> int | None:
    return None if a is None or b is None else abs((a - b).days)


def _total(rows: list[Row]) -> Decimal | None:
    values = [row.amount for row in rows if row.amount is not None]
    return sum(values, Decimal("0")) if values else None


def add_business_days(day: date, count: int) -> date:
    """Cộng số ngày làm việc, bỏ thứ Bảy và Chủ nhật."""
    while count > 0:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count -= 1
    return day


def _day_vi(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "?"


# ---------------------------------------------------------------- tách mã từ nội dung


def learn_code_pattern(values: list[str]) -> str | None:
    """Mẫu regex của mã, học từ chính các mã bên kia (không cần AI).

    Mỗi mã được tách thành các đoạn chữ / số / ký tự khác; lấy "hình dạng" chung của ≥ 90%
    mã. Đoạn chữ giống hệt nhau ở mọi mã thì giữ nguyên (ví dụ "HD"), khác nhau thì thành
    [A-Z]{n}; đoạn số thành \\d{n}. Ví dụ HD000123, HD000145 → (?<![A-Z0-9])HD\\d{6}(?![A-Z0-9]).
    """
    tokenized = [re.findall(r"[A-Z]+|\d+|[^A-Z\d]", value.upper()) for value in values if value]
    if not tokenized:
        return None

    def shape(tokens: list[str]) -> tuple[tuple[str, int], ...]:
        return tuple(
            ("A", len(token)) if token.isalpha() else ("9", len(token)) if token.isdigit()
            else (token, 1)
            for token in tokens
        )

    shapes = Counter(shape(tokens) for tokens in tokenized)
    common, count = shapes.most_common(1)[0]
    if count / len(tokenized) < EXTRACT_MIN_PRECISION or len(common) == 0:
        return None
    members = [tokens for tokens in tokenized if shape(tokens) == common]
    parts = []
    for index, (kind, length) in enumerate(common):
        if kind == "A":
            texts = {tokens[index] for tokens in members}
            parts.append(re.escape(next(iter(texts))) if len(texts) == 1 else f"[A-Z]{{{length}}}")
        elif kind == "9":
            parts.append(rf"\d{{{length}}}")
        else:
            parts.append(re.escape(kind))
    if all(kind == "9" for kind, _ in common) and sum(length for _, length in common) < 5:
        return None  # chỉ là số ngắn: dễ trùng với số tiền, ngày trong nội dung
    return r"(?<![A-Z0-9])" + "".join(parts) + r"(?![A-Z0-9])"


def extract_keys(text: str | None, extract: dict[str, str]) -> list[str]:
    """Các khóa tách được từ một ô chữ, theo thứ tự xuất hiện, không lặp."""
    if not text:
        return []
    found: list[str] = []
    if extract["kind"] == "date":
        for day, month, year in re.findall(DATE_IN_TEXT, text):
            try:
                found.append(date(int(year), int(month), int(day)).isoformat())
            except ValueError:
                continue
    else:
        found = re.findall(extract["pattern"], text.upper())
    return list(dict.fromkeys(found))


def description_name(text: str | None, keys: list[str]) -> str | None:
    """Tên người chuyển trong nội dung chuyển khoản: bỏ mã, số, từ nghiệp vụ và danh xưng.

    "ANH HOANG CK TIEN HANG" → "hoang"; "CK HD000123 NGUYEN VAN A" → "nguyen van a".
    """
    if not text:
        return None
    plain = text.upper()
    for key in keys:
        plain = plain.replace(key.upper(), " ")
    tokens = [
        token
        for token in name_match_key(plain).split()
        if token not in NOISE_WORDS
        and token not in HONORIFICS
        and not any(char.isdigit() for char in token)
    ]
    return " ".join(tokens) or None


def _name_score(a: str, b: str, from_text: bool) -> float:
    """Độ giống tên. Tên lấy từ nội dung chuyển khoản thường chỉ có tên gọi ("hoang"): khi đó
    tên gọi (từ cuối của tên đầy đủ) phải có mặt, cộng thêm phần họ, tên đệm trùng."""
    if not from_text:
        return fuzz.token_sort_ratio(a, b) / 100
    full, written = a.split(), set(b.split())
    if not full or full[-1] not in written:
        return 0.0
    others = full[:-1]
    return 0.7 + 0.3 * (sum(token in written for token in others) / len(others) if others else 1)


# ---------------------------------------------------------------- đọc dòng


def _column(frame: pl.DataFrame, name: str | None) -> list[Any]:
    if name is None or name not in frame.columns:
        return [None] * frame.height
    return frame[name].to_list()


def _left_keys(value: Any) -> list[str]:
    if value is None:
        return []
    if hasattr(value, "isoformat"):  # khóa là ngày (doanh thu sàn trả theo ngày đơn)
        return [value.isoformat()[:10]]
    return [str(value)]


def rows_of(frame: pl.DataFrame, config: ReconConfig, side: str) -> list[Row]:
    """Đọc các trường cần cho đối soát, sắp theo số dòng gốc để kết quả không phụ thuộc thứ tự."""
    frame = frame.sort(ROW_REF)
    left = side == "A"
    amounts = _column(frame, config.amount_left if left else config.amount_right)
    days = _column(frame, config.date_left if left else config.date_right)
    categories = {name: _column(frame, name) for name in SCOPE_FIELDS}
    cancelled = _column(frame, "is_cancelled")
    if left:
        raw_keys: list[list[str]] = [
            _left_keys(value) for value in _column(frame, config.key_left)
        ]
        names = _column(frame, "customer_name_key")
        outflows = [False] * frame.height
    else:
        if config.key_right:
            raw_keys = [[str(value)] if value is not None else [] for value in
                        _column(frame, config.key_right)]
        elif config.extract:
            raw_keys = [extract_keys(text, config.extract) for text in
                        _column(frame, config.extract["source"])]
        else:
            raw_keys = [[] for _ in range(frame.height)]
        if config.name_right:
            names = [
                description_name(text, keys)
                for text, keys in zip(_column(frame, config.name_right), raw_keys, strict=True)
            ]
        else:
            names = _column(frame, "customer_name_key")
        outflow_values = _column(frame, config.outflow_right)
        outflows = [
            amount is None and outflow is not None and outflow > 0
            for amount, outflow in zip(amounts, outflow_values, strict=True)
        ]
    return [
        Row(
            ref=ref,
            keys=raw_keys[index],
            amount=amounts[index],
            day=days[index].date() if isinstance(days[index], datetime) else days[index],
            name=names[index],
            cancelled=bool(cancelled[index]),
            category={name: values[index] for name, values in categories.items()},
            outflow=outflows[index],
        )
        for index, ref in enumerate(frame[ROW_REF].to_list())
    ]


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


def _suggest_extraction(
    left: pl.DataFrame, right: pl.DataFrame
) -> tuple[tuple[str, dict[str, str]] | None, list[dict[str, Any]]]:
    """Tìm cột A mà mã (hoặc ngày) của nó nằm trong nội dung chuyển khoản của B.

    Mẫu mã tự học từ chính giá trị cột A. Nhận mẫu khi ≥ 90% mã tách được có thật ở bên A và
    có ≥ 3 dòng khớp (docs/DECISIONS.md 2026-11-23); chọn cột có nhiều dòng khớp nhất.
    """
    evidence: list[dict[str, Any]] = []
    if "description" not in right.columns:
        return None, evidence
    texts = right["description"].to_list()
    best: tuple[int, str, dict[str, str]] | None = None
    targets = [(name, "code") for name in _fields_of(left, "IDENTIFIER")] + [
        (name, "date") for name in _fields_of(left, "DATE")
    ]
    for target, kind in targets:
        values = left[target].drop_nulls().to_list()
        if kind == "date":
            known = {value.isoformat()[:10] for value in values}
            extract = {"source": "description", "kind": "date", "pattern": DATE_IN_TEXT}
        else:
            pattern = learn_code_pattern([str(value) for value in values])
            if pattern is None:
                continue
            known = {str(value).upper() for value in values}
            extract = {"source": "description", "kind": "code", "pattern": pattern}
        found = hits = 0
        for text in texts:
            keys = extract_keys(text, extract)
            if keys:
                found += 1
                hits += any(key in known for key in keys)
        precision = hits / found if found else 0.0
        evidence.append(
            {"target": target, "kind": kind, "pattern": extract["pattern"], "found": found,
             "hits": hits, "precision": precision}
        )
        if precision >= EXTRACT_MIN_PRECISION and hits >= EXTRACT_MIN_HITS and (
            best is None or hits > best[0]
        ):
            best = (hits, target, extract)
    return ((best[1], best[2]) if best else None), evidence


def _links(rows_left: list[Row], rows_right: list[Row]) -> list[tuple[list[Row], Row]]:
    """Dòng B → các dòng A có khóa nằm trong khóa của nó (dùng để thử cột tiền, cột ngày)."""
    by_key: dict[str, list[Row]] = defaultdict(list)
    for row in rows_left:
        for key in row.keys:
            by_key[key.upper()].append(row)
    links = []
    for row in rows_right:
        matched = [a for key in row.keys for a in by_key.get(key.upper(), []) if not a.cancelled]
        if matched:
            links.append((list({a.ref: a for a in matched}.values()), row))
    return links


def suggest_config(left: pl.DataFrame, right: pl.DataFrame) -> tuple[ReconConfig, dict[str, Any]]:
    """Tự chọn trường đối soát từ dữ liệu hai bên (ARCHITECTURE 5.1).

    Khóa: cặp cột mã chấm theo tỷ lệ khớp thử (60%), độ phủ (20%), độ duy nhất (20%); nếu
    không có cột mã chung đủ tốt thì tách mã từ nội dung chuyển khoản bằng mẫu tự học.
    Tiền: cặp cột có tỷ lệ "tổng tiền các dòng A của khóa = tiền dòng B" cao nhất.
    Ngày: cặp cột có độ lệch ngày trung vị nhỏ nhất trên các dòng đã nối được.
    Trả về cấu hình và bằng chứng (các con số đã dùng để chọn) cho giao diện.
    """
    evidence: dict[str, Any] = {"keys": [], "amounts": [], "dates": [], "extract": []}
    best_key: tuple[float, str, str] | None = None
    best_rate = 0.0
    for left_candidate in _fields_of(left, "IDENTIFIER"):
        for right_candidate in _fields_of(right, "IDENTIFIER"):
            stats = _key_stats(left[left_candidate], right[right_candidate])
            score = 0.6 * stats["match_rate"] + 0.2 * stats["fill"] + 0.2 * stats["unique"]
            evidence["keys"].append({"left": left_candidate, "right": right_candidate, **stats})
            if stats["match_rate"] >= 0.05 and (best_key is None or score > best_key[0]):
                best_key = (score, left_candidate, right_candidate)
                best_rate = stats["match_rate"]
    config = ReconConfig(
        key_left=best_key[1] if best_key else None,
        key_right=best_key[2] if best_key else None,
        amount_left="",
        amount_right="",
    )
    if best_rate < 0.5:  # không có cột mã chung đủ tốt: thử tách mã từ nội dung
        extraction, evidence["extract"] = _suggest_extraction(left, right)
        if extraction is not None:
            config.key_left, config.key_right = extraction[0], None
            config.extract = extraction[1]
    if config.key_left:
        values = left[config.key_left].drop_nulls()
        # Mã đợt, ngày dùng chung cho nhiều dòng A → ghép nhóm theo tổng tiền.
        config.group_left = len(values) > 0 and values.n_unique() / len(values) < 0.5
    if (
        "customer_name_key" in left.columns
        and "customer_name_key" not in right.columns
        and "description" in right.columns
    ):
        config.name_right = "description"

    amount_pairs = [
        (a, b) for a in _fields_of(left, "MONEY") for b in _fields_of(right, "MONEY")
    ]
    if not amount_pairs:
        raise ValueError("Hai bảng cần có cột số tiền để đối soát.")
    links = (
        _links(rows_of(left, config, "A"), rows_of(right, config, "B")) if config.key_left else []
    )
    left_money = {name: dict(zip(left[ROW_REF].to_list(), left[name].to_list(), strict=True))
                  for name in _fields_of(left, "MONEY")}
    right_money = {name: dict(zip(right[ROW_REF].to_list(), right[name].to_list(), strict=True))
                   for name in _fields_of(right, "MONEY")}
    best_amount = (-1.0, amount_pairs[0])
    for a, b in amount_pairs:
        if links:
            equal = 0
            for group, row in links:
                parts = [left_money[a][member.ref] for member in group]
                target = right_money[b][row.ref]
                if target is not None and None not in parts and sum(parts) == target:
                    equal += 1
            rate = equal / len(links)
        else:
            rate = 1.0 if a == b else 0.0
        evidence["amounts"].append({"left": a, "right": b, "equal_rate": rate})
        # Cùng tỷ lệ thì ưu tiên cặp cùng tên cột chuẩn (ví dụ amount ↔ amount).
        if (rate, a == b) > (best_amount[0], best_amount[1][0] == best_amount[1][1]):
            best_amount = (rate, (a, b))
    config.amount_left, config.amount_right = best_amount[1]
    if config.amount_right == "credit" and "debit" in right.columns:
        config.outflow_right = "debit"

    left_days = {name: dict(zip(left[ROW_REF].to_list(), left[name].to_list(), strict=True))
                 for name in _fields_of(left, "DATE")}
    right_days = {name: dict(zip(right[ROW_REF].to_list(), right[name].to_list(), strict=True))
                  for name in _fields_of(right, "DATE")}
    best_date: tuple[float, tuple[str, str], float] | None = None
    for a, b in [(a, b) for a in left_days for b in right_days]:
        gaps = [
            (right_days[b][row.ref] - left_days[a][group[0].ref]).days
            for group, row in links
            if right_days[b][row.ref] is not None and left_days[a][group[0].ref] is not None
        ]
        median = float(np.median(np.abs(gaps))) if gaps else 999.0
        later = sum(gap > 0 for gap in gaps) / len(gaps) if gaps else 0.0
        evidence["dates"].append({"left": a, "right": b, "median_days": median, "later": later})
        if best_date is None or median < best_date[0]:
            best_date = (median, (a, b), later)
    if best_date:
        config.date_left, config.date_right = best_date[1]
        # Bên B ghi sau bên A ở một phần đáng kể các cặp → có độ trễ tiền về → có khung chờ.
        config.settle_days = DEFAULT_SETTLE_DAYS if best_date[2] >= SETTLEMENT_LAG_SHARE else 0
    else:
        config.settle_days = 0
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
    if not config.key_left:
        return excluded, evidence
    rows = {"LEFT": rows_of(left, config, "A"), "RIGHT": rows_of(right, config, "B")}
    for side, other in (("LEFT", "RIGHT"), ("RIGHT", "LEFT")):
        other_keys = {key.upper() for row in rows[other] for key in row.keys}
        for name in SCOPE_FIELDS:
            rates: dict[str, tuple[int, int]] = {}
            for row in rows[side]:
                value = row.category.get(name)
                if value is None:
                    continue
                total, hits = rates.get(value, (0, 0))
                hit = any(key.upper() in other_keys for key in row.keys)
                rates[value] = (total + 1, hits + hit)
            if not rates:
                continue
            best = max(hits / total for total, hits in rates.values())
            for value, (total, hits) in sorted(rates.items()):
                out = hits / total <= SCOPE_MAX_OWN_RATE and best >= SCOPE_MIN_OTHER_RATE
                evidence.append(
                    {"side": side, "field": name, "value": value, "rows": total,
                     "matched": hits, "excluded": out}
                )
                if out:
                    excluded.setdefault(side, {}).setdefault(name, []).append(value)
    return excluded, evidence


# ---------------------------------------------------------------- kết quả


def _pair_result(left: Row, right: Row, config: ReconConfig, how: str) -> Result:
    """Kết quả cho một cặp 1:1 đã ghép: khớp hay lệch tiền, kèm lý do."""
    reasons = []
    if how == "KEY":
        reasons.append(_reason("KEY", f"Cùng mã {left.key}."))
    elif how == "USER":
        reasons.append(_reason("USER", "Bạn đã chọn cặp này."))
    gap = _days_apart(left.day, right.day)
    if _within(left.amount, right.amount, config.tolerance):
        kind = "MATCHED"
        reasons.append(_reason("AMOUNT_EQUAL", f"Số tiền khớp: {money_dong(left.amount)}."))
    else:
        kind = "AMOUNT_MISMATCH"
        reasons.append(_reason("AMOUNT_DIFF", _difference_text(left.amount, right.amount)))
    if gap is not None:
        reasons.append(_reason("DATE", "Cùng ngày." if gap == 0 else f"Cách nhau {gap} ngày."))
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


def _difference_text(left: Decimal | None, right: Decimal | None) -> str:
    text = f"Lệch tiền: A {money_dong(left)}, B {money_dong(right)}"
    if left is None or right is None:
        return text + "."
    difference = right - left
    return text + f" (B {'thừa' if difference > 0 else 'thiếu'} {money_dong(abs(difference))})."


def _group_result(lefts: list[Row], rights: list[Row], how: str, config: ReconConfig) -> Result:
    """Kết quả cho một nhóm (nhiều A ↔ một B hoặc một A ↔ nhiều B). Tổng tiền phải bằng đúng,
    không áp sai số (Oracle Cash Management: tolerance không dùng cho khớp nhóm)."""
    if len(lefts) == 1 and len(rights) == 1:
        return _pair_result(lefts[0], rights[0], config, how)
    total_left, total_right = _total(lefts), _total(rights)
    kind = "MANY_TO_ONE" if len(lefts) > 1 else "ONE_TO_MANY"
    lead = {
        "KEY": f"Cùng mã {', '.join(sorted({key for row in rights + lefts for key in row.keys}))}.",
        "SUM": "Ghép theo tổng tiền (không có mã chung).",
        "USER": "Bạn đã chọn nhóm này.",
    }[how]
    reasons = [_reason(how, lead)]
    if total_left is not None and total_left == total_right:
        reasons.append(
            _reason(
                "GROUP_SUM",
                f"Tổng {len(lefts)} dòng A = {len(rights)} dòng B = {money_dong(total_left)}.",
            )
        )
        needs_review = False
    else:
        kind = "AMOUNT_MISMATCH"
        reasons.append(_reason("AMOUNT_DIFF", _difference_text(total_left, total_right)))
        needs_review = True
    return Result(
        kind=kind,
        left_refs=sorted(row.ref for row in lefts),
        right_refs=sorted(row.ref for row in rights),
        reasons=reasons,
        amount_left=total_left,
        amount_right=total_right,
        needs_review=needs_review,
    )


def _single(kind: str, row: Row, side: str, reasons: list[dict[str, Any]], review: bool) -> Result:
    return Result(
        kind=kind,
        left_refs=[row.ref] if side == "A" else [],
        right_refs=[row.ref] if side == "B" else [],
        reasons=reasons,
        amount_left=row.amount if side == "A" else None,
        amount_right=row.amount if side == "B" else None,
        needs_review=review,
    )


# ---------------------------------------------------------------- khớp theo mã


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


def _key_round(
    left: list[Row], right: list[Row], config: ReconConfig
) -> tuple[list[Result], set[int], set[int]]:
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
    return results, used_left, used_right


# ---------------------------------------------------------------- khớp theo điểm


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


def _ambiguous_result(
    lefts: list[Row], rights: list[Row], pairs: list[dict[str, Any]], text: str
) -> Result:
    return Result(
        kind="AMBIGUOUS",
        left_refs=sorted(row.ref for row in lefts),
        right_refs=sorted(row.ref for row in rights),
        reasons=[_reason("CANDIDATES", text, pairs=pairs)],
        amount_left=_total(lefts),
        amount_right=_total(rights),
        needs_review=True,
    )


def _score_round(
    left: list[Row], right: list[Row], config: ReconConfig
) -> tuple[list[Result], set[int], set[int], dict[tuple[str, int], str]]:
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
        return [], set(), set(), skipped

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
    return results, used_left, used_right, skipped


# ---------------------------------------------------------------- khớp nhóm theo tổng tiền


def _subsets(candidates: list[Row], target: Decimal, limit: int = 2) -> list[list[Row]]:
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


def _sum_round(
    left: list[Row], right: list[Row], config: ReconConfig
) -> tuple[list[Result], set[int], set[int]]:
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
            solutions = _subsets(pool, target.amount)
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
    return results, used_left, used_right


# ---------------------------------------------------------------- chạy toàn bộ


def _scope_reason(row: Row, excluded: dict[str, list[str]]) -> str | None:
    for name, values in excluded.items():
        value = row.category.get(name)
        if value is not None and value in values:
            label = FIELDS_BY_KEY[name].label.lower() if name in FIELDS_BY_KEY else name
            return f"Ngoài phạm vi: {label} “{value}” không đi qua bên kia."
    return None


def _apply_forced(
    pools: dict[str, list[Row]], config: ReconConfig
) -> tuple[list[Result], set[int], set[int]]:
    """Áp dụng lựa chọn của người dùng cho ca mơ hồ (chỉ khi các dòng vẫn còn để ghép)."""
    results: list[Result] = []
    used_left: set[int] = set()
    used_right: set[int] = set()
    left_by_ref = {row.ref: row for row in pools["A"]}
    right_by_ref = {row.ref: row for row in pools["B"]}
    for choice in config.forced:
        lefts = [left_by_ref.get(ref) for ref in choice.get("left", [])]
        rights = [right_by_ref.get(ref) for ref in choice.get("right", [])]
        if (
            not lefts or not rights or None in lefts or None in rights
            or any(row.ref in used_left for row in lefts if row)
            or any(row.ref in used_right for row in rights if row)
        ):
            continue
        chosen_left = [row for row in lefts if row]
        chosen_right = [row for row in rights if row]
        results.append(_group_result(chosen_left, chosen_right, "USER", config))
        used_left.update(row.ref for row in chosen_left)
        used_right.update(row.ref for row in chosen_right)
    return results, used_left, used_right


def reconcile(left: Side, right: Side, config: ReconConfig) -> list[Result]:
    """Đối soát A ↔ B; mỗi dòng của hai bên (kể cả dòng chờ từ kỳ trước) nằm trong đúng một
    kết quả."""
    rows_left = rows_of(left.frame, config, "A")
    rows_right = rows_of(right.frame, config, "B")
    # Dòng chờ từ kỳ trước: số dòng âm để không trùng số dòng của bảng hiện tại.
    origins: dict[int, dict[str, Any]] = {}
    if left.carried is not None and left.carried.height:
        carried_frame = left.carried.sort(["__origin", ROW_REF])
        for index, (origin, ref) in enumerate(
            zip(carried_frame["__origin"].to_list(), carried_frame[ROW_REF].to_list(), strict=True)
        ):
            origins[-(index + 1)] = {"table_id": origin, "row_ref": ref}
        carried_rows = rows_of(
            carried_frame.with_columns(pl.Series(ROW_REF, list(origins))), config, "A"
        )
        rows_left = carried_rows + rows_left
    results: list[Result] = []
    # Ngày cuối của dữ liệu bên B: tiền chưa về tới ngày này mà còn trong hạn thì chờ.
    period_end = max((row.day for row in rows_right if row.day), default=None)

    # 1–2. Ngoài phạm vi, tiền ra và dữ liệu chưa sạch: không tham gia ghép.
    pools: dict[str, list[Row]] = {}
    for side, rows, source, scope in (
        ("A", rows_left, left, config.excluded.get("LEFT", {})),
        ("B", rows_right, right, config.excluded.get("RIGHT", {})),
    ):
        pool = []
        for row in rows:
            out = _scope_reason(row, scope)
            if out:
                results.append(_single("OUT_OF_SCOPE", row, side, [_reason("SCOPE", out)], False))
            elif row.ref in source.elsewhere:
                results.append(
                    _single(
                        "OUT_OF_SCOPE",
                        row,
                        side,
                        [_reason("ELSEWHERE", source.elsewhere[row.ref])],
                        False,
                    )
                )
            elif row.outflow:
                results.append(
                    _single(
                        "OUT_OF_SCOPE",
                        row,
                        side,
                        [_reason("OUTFLOW", "Tiền ra (cột Nợ), không thuộc đối soát bán hàng.")],
                        False,
                    )
                )
            elif row.ref in source.unclean_refs:
                results.append(
                    _single(
                        "NEEDS_CLEANING",
                        row,
                        side,
                        [_reason("NOT_CLEAN", "Dòng còn vấn đề chưa xử lý ở bước làm sạch.")],
                        True,
                    )
                )
            else:
                pool.append(row)
        pools[side] = pool

    # 0. Lựa chọn của người dùng.
    chosen, used_left, used_right = _apply_forced(pools, config)
    results += chosen
    rest_left = [row for row in pools["A"] if row.ref not in used_left]
    rest_right = [row for row in pools["B"] if row.ref not in used_right]

    # 3. Khớp theo mã.
    matched, used_left, used_right = _key_round(rest_left, rest_right, config)
    results += matched
    rest_left = [row for row in rest_left if row.ref not in used_left]
    rest_right = [row for row in rest_right if row.ref not in used_right]

    # 4. Khớp theo điểm 1:1.
    scored, used_left, used_right, skipped = _score_round(rest_left, rest_right, config)
    results += scored
    rest_left = [row for row in rest_left if row.ref not in used_left]
    rest_right = [row for row in rest_right if row.ref not in used_right]

    # 5. Khớp nhóm theo tổng tiền.
    summed, used_left, used_right = _sum_round(rest_left, rest_right, config)
    results += summed
    rest_left = [row for row in rest_left if row.ref not in used_left]
    rest_right = [row for row in rest_right if row.ref not in used_right]

    # 6. Còn lại.
    for side, rows in (("A", rest_left), ("B", rest_right)):
        for row in rows:
            if row.cancelled:  # đơn đã hủy mà không có dòng tương ứng là bình thường
                results.append(
                    _single(
                        "OUT_OF_SCOPE",
                        row,
                        side,
                        [_reason("CANCELLED", "Đơn đã hủy, không cần có tiền về.")],
                        False,
                    )
                )
                continue
            if side == "A" and config.settle_days and row.day and period_end:
                deadline = add_business_days(row.day, config.settle_days)
                if deadline > period_end:
                    results.append(
                        _single(
                            "PENDING_SETTLEMENT",
                            row,
                            side,
                            [
                                _reason(
                                    "PENDING",
                                    f"Chờ tiền về: hạn {_day_vi(deadline)} "
                                    f"(T+{config.settle_days} ngày làm việc), dữ liệu bên B mới "
                                    f"tới {_day_vi(period_end)}. Kỳ sau sẽ tự ghép lại.",
                                )
                            ],
                            False,
                        )
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
            if row.ref < 0:
                reasons.append(
                    _reason("OVERDUE", "Dòng chờ từ kỳ trước đã quá hạn mà vẫn chưa có tiền về.")
                )
            if (side, row.ref) in skipped:
                reasons.append(_reason("TIED", skipped[(side, row.ref)]))
            results.append(
                _single("ONLY_IN_A" if side == "A" else "ONLY_IN_B", row, side, reasons, True)
            )

    # Dòng chờ từ kỳ trước: tách khỏi left_refs, ghi rõ bảng gốc.
    for item in results:
        carried = [ref for ref in item.left_refs if ref < 0]
        if carried:
            item.carried_left = [origins[ref] for ref in sorted(carried, reverse=True)]
            item.left_refs = [ref for ref in item.left_refs if ref >= 0]
            item.reasons.append(
                _reason("CARRIED", f"Gồm {len(carried)} dòng chờ tiền về từ kỳ trước.")
            )

    # Thứ tự cố định: theo loại, rồi theo số dòng gốc.
    order = {kind: index for index, kind in enumerate(KINDS)}
    results.sort(
        key=lambda item: (
            order[item.kind],
            item.left_refs[0] if item.left_refs else 10**12,
            item.right_refs[0] if item.right_refs else 10**12,
            str(item.carried_left),
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
        rows[item.kind]["A"] += len(item.left_refs) + len(item.carried_left)
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
