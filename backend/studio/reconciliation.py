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

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import polars as pl
from rapidfuzz import fuzz

from studio import config_files
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
# Ngưỡng và trọng số: config/rules/reconciliation.json.
_RULES = config_files.reconciliation_rules()
_KEYS = _RULES.key_selection
_SCORE = _RULES.score_match
# Trọng số điểm khớp theo điểm (chỉ tính các thành phần cả hai bên đều có).
SCORE_WEIGHTS: dict[str, float] = {name: weight for name, weight in _SCORE.weights.items()}
# Cột phân loại có thể dùng để để dòng ra ngoài phạm vi (trạng thái đơn xử lý riêng).
SCOPE_FIELDS = _RULES.scope.fields
# Một giá trị bị coi là ngoài phạm vi khi gần như không dòng nào của nó khớp mã với bên kia
# (chừa chỗ cho dòng nhập nhầm), trong khi giá trị khớp nhiều nhất đạt mức tối thiểu.
SCOPE_MIN_OTHER_RATE = _RULES.scope.min_other_rate
SCOPE_MAX_OWN_RATE = _RULES.scope.max_own_rate
# Giới hạn để ghép không chậm theo bình phương số dòng khi dữ liệu có rất nhiều dòng giống nhau.
MAX_SAME_KEY_PAIRS = 10_000
MAX_CANDIDATES_PER_ROW = 50
MAX_COMPONENT_ROWS = 400
# Khớp nhóm theo tổng tiền: số dòng mỗi nhóm và số ứng viên mỗi dòng có giới hạn
# (ARCHITECTURE 5.2: giới hạn tổ hợp để không bùng nổ).
MAX_GROUP_ROWS = _RULES.group_match.max_rows
MAX_SUBSET_CANDIDATES = _RULES.group_match.max_candidates
# Khung chờ tiền về mặc định, tính bằng ngày làm việc (docs/DECISIONS.md 2026-11-23).
DEFAULT_SETTLE_DAYS = _RULES.settlement.business_days
# Tách mã từ nội dung: mẫu tự học phải đủ đúng và đủ số dòng khớp.
EXTRACT_MIN_PRECISION = _RULES.code_extraction.min_precision
EXTRACT_MIN_HITS = _RULES.code_extraction.min_hits
# Có độ trễ tiền về khi đủ tỷ lệ cặp đã ghép có ngày bên B sau ngày bên A.
SETTLEMENT_LAG_SHARE = _RULES.settlement.min_late_share
# Ngày trong nội dung chuyển khoản, kiểu Việt Nam ngày/tháng/năm.
DATE_IN_TEXT = r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)"
# Từ nghiệp vụ trong nội dung chuyển khoản, bỏ đi khi lấy tên người chuyển
# (config/domains/sales/vocabulary.json, "transfer_noise_words").
NOISE_WORDS = set(config_files.vocabulary().transfer_noise_words)


@dataclass
class ReconConfig:
    """Cấu hình đối soát: trường so khớp của mỗi bên, sai số, phạm vi."""

    key_left: str | None
    key_right: str | None
    amount_left: str
    amount_right: str
    date_left: str | None = None
    date_right: str | None = None
    # Mặc định lấy từ config/rules/reconciliation.json ("score_match").
    tolerance: Decimal = Decimal(_SCORE.amount_tolerance)  # sai số tiền (đồng), chỉ ghép 1:1
    date_window_days: int = _SCORE.date_window_days  # khung ngày cho khớp điểm và khớp nhóm
    min_score: float = _SCORE.min_score
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
class RoundOutcome:
    """Kết quả một vòng khớp: các kết quả tạo ra, số dòng mỗi bên đã dùng (không tham gia vòng
    sau) và lý do các dòng bị để lại có chủ đích (ghi vào kết quả "chỉ có ở một bên")."""

    results: list[Result]
    used_left: set[int]
    used_right: set[int]
    skipped: dict[tuple[str, int], str] = field(default_factory=dict)


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
            score = sum(weight * stats[name] for name, weight in _KEYS.weights.items())
            evidence["keys"].append({"left": left_candidate, "right": right_candidate, **stats})
            if stats["match_rate"] >= _KEYS.min_match_rate and (
                best_key is None or score > best_key[0]
            ):
                best_key = (score, left_candidate, right_candidate)
                best_rate = stats["match_rate"]
    config = ReconConfig(
        key_left=best_key[1] if best_key else None,
        key_right=best_key[2] if best_key else None,
        amount_left="",
        amount_right="",
    )
    if best_rate < _KEYS.extract_codes_below_rate:  # không có mã chung đủ tốt: tách từ nội dung
        extraction, evidence["extract"] = _suggest_extraction(left, right)
        if extraction is not None:
            config.key_left, config.key_right = extraction[0], None
            config.extract = extraction[1]
    if config.key_left:
        values = left[config.key_left].drop_nulls()
        # Mã đợt, ngày dùng chung cho nhiều dòng A → ghép nhóm theo tổng tiền.
        config.group_left = (
            len(values) > 0 and values.n_unique() / len(values) < _KEYS.group_when_unique_below
        )
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
    # "bên A/bên B" để lớp hiển thị đổi thành tên bảng thật (recon_api.name_sides).
    text = f"Lệch tiền: bên A {money_dong(left)}, bên B {money_dong(right)}"
    if left is None or right is None:
        return text + "."
    difference = right - left
    return text + (
        f" (bên B {'thừa' if difference > 0 else 'thiếu'} {money_dong(abs(difference))})."
    )


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

    # 3. Các vòng khớp, theo đúng thứ tự và bật/tắt trong config/rules/reconciliation.json
    # ("rounds"); mỗi vòng ở một tệp trong backend/studio/matching_rounds/. Dòng đã ghép ở vòng
    # trước không tham gia vòng sau.
    from studio.matching_rounds import enabled_rounds

    skipped: dict[tuple[str, int], str] = {}
    for run_round in enabled_rounds():
        outcome = run_round(rest_left, rest_right, config)
        results += outcome.results
        skipped.update(outcome.skipped)
        rest_left = [row for row in rest_left if row.ref not in outcome.used_left]
        rest_right = [row for row in rest_right if row.ref not in outcome.used_right]

    # 4. Còn lại (bước khóa, không tắt được: mỗi dòng phải nằm trong đúng một kết quả).
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
