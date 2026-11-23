"""Đọc giá trị dạng chữ thành giá trị chuẩn theo kiểu cột chuẩn (docs/ARCHITECTURE.md 4.3).

Mỗi hàm trả về `Parsed`: giá trị chuẩn, trạng thái VALID/EMPTY/INVALID và loại sửa đã áp
dụng (để ghi nhật ký). Mọi phép đọc là xác định: cùng đầu vào luôn ra cùng kết quả.
Tiền dùng Decimal (số thập phân chính xác), không dùng float.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal

type ParseState = Literal["VALID", "EMPTY", "INVALID"]
# Thứ tự ngày tháng của một cột: ngày/tháng/năm hoặc tháng/ngày/năm.
type DateOrder = Literal["DMY", "MDY"]
# Kiểu dấu phân cách số của một cột: Việt (1.250.000,5) hay Anh (1,250,000.5).
type NumberStyle = Literal["VN", "EN"]


@dataclass(frozen=True)
class Parsed:
    value: object | None
    state: ParseState
    # Loại sửa tự động đã áp dụng (None nếu giá trị đã đúng dạng chuẩn), ví dụ "SHORTHAND_AMOUNT".
    fix: str | None = None


EMPTY = Parsed(None, "EMPTY")
INVALID = Parsed(None, "INVALID")


def is_blank(text: str | None) -> bool:
    return text is None or text.strip() == ""


# ---------------------------------------------------------------- tiền

_CURRENCY = re.compile(r"\s*(vnđ|vnd|đồng|dong|đ|₫)\s*$", re.IGNORECASE)
# Viết tắt hay gặp: 1tr2 = 1.200.000; 1,5tr / 1.5 triệu = 1.500.000; 500k / 500 nghìn = 500.000.
_SHORTHAND = re.compile(
    r"^(?P<whole>\d+)(?:[.,](?P<frac>\d+))?\s*(?P<unit>tr|triệu|trieu|k|nghìn|nghin|ngàn|ngan)"
    r"(?P<rest>\d{1,3})?$",
    re.IGNORECASE,
)
_UNIT_VALUE = {
    "tr": 1_000_000,
    "triệu": 1_000_000,
    "trieu": 1_000_000,
    "k": 1_000,
    "nghìn": 1_000,
    "nghin": 1_000,
    "ngàn": 1_000,
    "ngan": 1_000,
}


def detect_number_style(values: list[str]) -> NumberStyle:
    """Suy kiểu dấu phân cách từ cả cột.

    - Có dạng 1,250,000 hoặc dấu chấm thập phân sau dấu phẩy (1,250.50) → kiểu Anh.
    - Còn lại (1.250.000, 1.250,5, hoặc không có dấu) → kiểu Việt (mặc định ở Việt Nam).
    """
    english = 0
    vietnamese = 0
    for raw in values:
        text = raw.strip().strip("()-").replace(" ", "")
        if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", text) or re.fullmatch(r"\d+\.\d{1,2}", text):
            english += 1
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", text) or re.fullmatch(r"\d+,\d{1,2}", text):
            vietnamese += 1
    return "EN" if english > vietnamese else "VN"


def parse_money(raw: str | None, style: NumberStyle = "VN") -> Parsed:
    if is_blank(raw):
        return EMPTY
    assert raw is not None
    text = unicodedata.normalize("NFC", raw).strip()
    text = _CURRENCY.sub("", text).strip()
    negative = False
    if text.startswith("(") and text.endswith(")"):  # (500) là số âm theo cách ghi kế toán
        negative, text = True, text[1:-1].strip()
    if text.startswith("-"):
        negative, text = True, text[1:].strip()

    shorthand = _SHORTHAND.fullmatch(text.replace(" ", "") if "tr" in text.lower() else text)
    if shorthand:
        unit = _UNIT_VALUE[shorthand.group("unit").lower()]
        amount = Decimal(shorthand.group("whole")) * unit
        if shorthand.group("frac"):
            amount += Decimal("0." + shorthand.group("frac")) * unit
        if shorthand.group("rest"):  # "1tr2": phần sau đơn vị là trăm nghìn
            rest = shorthand.group("rest")
            amount += Decimal(rest) * unit / (10 ** len(rest))
        return Parsed(-amount if negative else amount, "VALID", "SHORTHAND_AMOUNT")

    compact = text.replace(" ", "")
    if style == "VN":
        if not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?|\d+(,\d+)?|\d+\.\d+", compact):
            return INVALID
        # "1250000.5" hoặc "1250000.0" (số Excel) vẫn đọc được dù cột kiểu Việt
        if re.fullmatch(r"\d+\.\d{1,2}", compact) and not re.fullmatch(r"\d{1,3}\.\d{3}", compact):
            normalized = compact
        else:
            normalized = compact.replace(".", "").replace(",", ".")
    else:
        if not re.fullmatch(r"\d{1,3}(,\d{3})*(\.\d+)?|\d+(\.\d+)?", compact):
            return INVALID
        normalized = compact.replace(",", "")
    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        return INVALID
    fix = None if normalized == compact and not negative else "NUMBER_FORMAT"
    return Parsed(-amount if negative else amount, "VALID", fix)


# ---------------------------------------------------------------- ngày

# Phần giờ đi kèm ngày (bỏ qua khi đọc ngày): 08:30, 08:30:15.123, 2:30 PM, múi giờ Z / +07:00.
_TIME = r"(?:[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:\s*[AaPp][Mm])?(?:Z|[+-]\d{2}:?\d{2})?)?"
# Năm đứng đầu: 2026-11-05, 2026/11/05, 2026.11.05 (thứ tự năm-tháng-ngày không bao giờ mơ hồ).
_ISO = re.compile(r"^(\d{4})([-/.])(\d{1,2})\2(\d{1,2})" + _TIME + "$")
_SLASHED = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})" + _TIME + "$")
EXCEL_EPOCH = date(1899, 12, 30)


def detect_date_order(values: list[str]) -> tuple[DateOrder, bool]:
    """Suy thứ tự ngày/tháng từ cả cột (không đoán từng ô).

    Có giá trị mà phần đầu > 12 thì là ngày/tháng; phần giữa > 12 thì là tháng/ngày.
    Không phân biệt được thì mặc định ngày/tháng theo thói quen Việt Nam
    (quyết định 2026-11-20). Trả về (thứ tự, có phải mặc định do mơ hồ không).
    """
    first_big = second_big = False
    for raw in values:
        match = _SLASHED.match(raw.strip())
        if match:
            first_big |= int(match.group(1)) > 12
            second_big |= int(match.group(2)) > 12
    if second_big and not first_big:
        return "MDY", False
    if first_big:
        return "DMY", False
    has_slashed = any(_SLASHED.match(raw.strip()) for raw in values)
    return "DMY", has_slashed


def parse_date(raw: str | None, order: DateOrder = "DMY") -> Parsed:
    if is_blank(raw):
        return EMPTY
    assert raw is not None
    text = raw.strip()
    iso = _ISO.match(text)
    try:
        if iso:
            value = date(int(iso.group(1)), int(iso.group(3)), int(iso.group(4)))
            exact = text == value.isoformat()
            return Parsed(value, "VALID", None if exact else "DATE_FORMAT")
        slashed = _SLASHED.match(text)
        if slashed:
            first, second, year = int(slashed.group(1)), int(slashed.group(2)), slashed.group(3)
            day, month = (first, second) if order == "DMY" else (second, first)
            full_year = int(year) + (2000 if len(year) == 2 else 0)
            return Parsed(date(full_year, month, day), "VALID", "DATE_FORMAT")
        # Số ngày kiểu Excel, ví dụ 46300; phần lẻ (46300.5) là giờ trong ngày, bỏ qua.
        if re.fullmatch(r"\d{5}(\.\d+)?", text):
            serial = int(text.split(".")[0])
            if 20000 <= serial <= 80000:
                return Parsed(EXCEL_EPOCH + timedelta(days=serial), "VALID", "EXCEL_SERIAL_DATE")
    except ValueError:
        return INVALID  # ví dụ 31/02/2026
    return INVALID


# ---------------------------------------------------------------- mã, điện thoại, chữ


def parse_identifier(raw: str | None) -> Parsed:
    """Mã giữ nguyên dạng chữ (kể cả số 0 đầu); chỉ bỏ khoảng trắng thừa và đuôi '.0' của Excel."""
    if is_blank(raw):
        return EMPTY
    assert raw is not None
    text = raw.strip()
    if re.fullmatch(r"\d+\.0+", text):
        return Parsed(text.split(".")[0], "VALID", "EXCEL_NUMBER_CODE")
    return Parsed(text, "VALID", None if text == raw else "WHITESPACE")


def parse_phone(raw: str | None) -> Parsed:
    """Số điện thoại Việt Nam về dạng bắt đầu bằng 0 (84… và +84… đổi thành 0…).

    Di động 10 số (09…, 03…); máy bàn 11 số (mã vùng 02x, ví dụ 028 3822 1234).
    """
    if is_blank(raw):
        return EMPTY
    assert raw is not None
    digits = re.sub(r"\D", "", raw)
    fix = None if digits == raw.strip() else "PHONE_FORMAT"
    if digits.startswith("84") and (len(digits) == 11 or (len(digits) == 12 and digits[2] == "2")):
        digits, fix = "0" + digits[2:], "PHONE_PREFIX"
    elif len(digits) == 9 and digits[0] in "35789":  # mất số 0 đầu do Excel đọc thành số
        digits, fix = "0" + digits, "PHONE_LEADING_ZERO"
    if not re.fullmatch(r"0\d{9}|02\d{9}", digits):
        return INVALID
    return Parsed(digits, "VALID", fix)


def parse_text(raw: str | None) -> Parsed:
    """Chữ: chuẩn Unicode NFC, gọn khoảng trắng."""
    if is_blank(raw):
        return EMPTY
    assert raw is not None
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFC", raw)).strip()
    return Parsed(text, "VALID", None if text == raw else "WHITESPACE")


# Danh xưng bỏ đi khi so khớp tên (anh Hoàng, chú Hoàng, Mr Hoàng… đều là "hoang").
HONORIFICS = {
    "anh",
    "chi",
    "chu",
    "co",
    "bac",
    "em",
    "ong",
    "ba",
    "a",
    "c",
    "mr",
    "mrs",
    "ms",
    "miss",
    "cau",
    "di",
    "thim",
    "mo",
    "ban",
}


def name_match_key(name: str) -> str:
    """Bản tên dùng để so khớp: bỏ dấu, chữ thường, bỏ danh xưng ở đầu."""
    plain = unicodedata.normalize("NFD", name.replace("đ", "d").replace("Đ", "D"))
    plain = "".join(char for char in plain if unicodedata.category(char) != "Mn").lower()
    tokens = re.findall(r"[a-z0-9]+", plain)
    while tokens and tokens[0] in HONORIFICS and len(tokens) > 1:
        tokens.pop(0)
    return " ".join(tokens)


# Từ cho biết đơn đã hủy hoặc hoàn tiền (so sau khi bỏ dấu).
CANCELLED_WORDS = (
    "huy", "da huy", "cancel", "cancelled", "canceled", "hoan tien", "hoan hang", "refund",
    "refunded", "return", "returned", "tra hang",
)


def is_cancelled_status(status: str) -> bool:
    """So theo từ trọn vẹn: "huy" khớp "Đã hủy" nhưng không khớp "Chuyển khoản", "Khuyến mãi"."""
    padded = f" {name_match_key(status)} "
    return any(f" {word} " in padded for word in CANCELLED_WORDS)


def money_vi(value: Decimal | None, unit: str = "") -> str:
    """Số tiền kiểu Việt để hiển thị trong thông điệp: 2195000 → "2.195.000" (+ đơn vị nếu có).

    Dùng chung cho thông điệp làm sạch và lý do đối soát; ô trống hiện là "trống".
    """
    if value is None:
        return "trống"
    sign = "-" if value < 0 else ""
    whole = f"{int(abs(value)):,}".replace(",", ".")
    fraction = abs(value) % 1
    text = whole if fraction == 0 else f"{whole},{str(fraction.quantize(Decimal('0.01')))[2:]}"
    return f"{sign}{text}{unit}"
