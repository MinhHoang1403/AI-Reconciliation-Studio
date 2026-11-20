"""Chấm điểm ánh xạ cột bằng quy tắc (không dùng AI).

Hai lớp tín hiệu, gộp thành điểm 0–1 cho mỗi cặp (cột của người dùng, cột chuẩn):
1. Tên cột: bỏ dấu, tách từ, mở rộng viết tắt, so độ giống với các tên hay gặp
   bằng RapidFuzz (token_sort_ratio: so cả chuỗi, không phụ thuộc thứ tự từ).
2. Giá trị: dạng dữ liệu quan sát được (hồ sơ cột) có hợp kiểu của cột chuẩn không,
   cùng vài dấu hiệu phụ (cột mã thường gần như không trùng, cột trạng thái ít giá trị).
"""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from studio.profiling import ColumnProfile, TableProfile
from studio.sales_fields import SALES_FIELDS, FieldType, StandardField

# Trọng số gộp hai lớp tín hiệu.
NAME_WEIGHT = 0.65
VALUE_WEIGHT = 0.35
EMPTY_COLUMN_VALUE_SCORE = 0.5
# Tên cột quá khác mọi tên hay gặp thì giá trị hợp kiểu cũng không đủ để ánh xạ:
# điểm bị giới hạn dưới ngưỡng gợi ý (ví dụ cột STT toàn số không phải cột tiền).
MIN_NAME_SCORE = 0.5
WEAK_NAME_CAP = 0.4
# Tên cột chỉ số thứ tự dòng, không bao giờ là cột chuẩn.
ROW_NUMBER_NAMES = {"stt", "so thu tu", "so tt", "no", "#"}

# Viết tắt hay gặp trong tên cột tiếng Việt; mở rộng trước khi so.
ABBREVIATIONS = {
    "sdt": "so dien thoai", "dt": "dien thoai", "hd": "hoa don", "dh": "don hang",
    "kh": "khach hang", "gd": "giao dich", "tt": "thanh toan", "nh": "ngan hang",
    "ck": "chuyen khoan", "tk": "tai khoan", "sl": "so luong", "ct": "chung tu",
}

# Mức hợp giữa dạng quan sát được và kiểu cột chuẩn (0 = không thể, 1 = rất hợp).
COMPATIBILITY: dict[FieldType, dict[str, float]] = {
    "IDENTIFIER": {"CODE": 1.0, "NUMBER": 0.6, "TEXT": 0.3, "PHONE": 0.2},
    "MONEY": {"NUMBER": 1.0},
    "DATE": {"DATE": 1.0},
    "PHONE": {"PHONE": 1.0, "NUMBER": 0.4},
    "TEXT": {"TEXT": 1.0, "CODE": 0.3},
    "CATEGORY": {"TEXT": 1.0, "CODE": 0.4},
}


def _split_camel_case(name: str) -> str:
    """Tách chữ viết liền kiểu 'MaHD', 'NgayBan' thành 'Ma HD', 'Ngay Ban'.

    Dùng str.islower/isupper thay cho dải ký tự trong regex, vì bảng mã tiếng Việt xếp
    chữ hoa và chữ thường có dấu xen kẽ nhau (dải À-Ỹ chứa cả chữ thường).
    """
    output: list[str] = []
    for index, char in enumerate(name):
        if index and char.isupper() and name[index - 1].islower():
            output.append(" ")
        output.append(char)
    return "".join(output)


def normalize_name(name: str) -> str:
    """'MaHD' → 'ma hoa don'; 'SĐT người nhận' → 'so dien thoai nguoi nhan'."""
    spaced = _split_camel_case(name).replace("đ", "d").replace("Đ", "D")
    plain = unicodedata.normalize("NFD", spaced)
    plain = "".join(char for char in plain if unicodedata.category(char) != "Mn").lower()
    tokens = re.findall(r"[a-z0-9]+", plain)
    return " ".join(ABBREVIATIONS.get(token, token) for token in tokens)


def name_score(column_name: str, field: StandardField) -> float:
    normalized = normalize_name(column_name)
    if not normalized:
        return 0.0
    best = max(fuzz.token_sort_ratio(normalized, alias) for alias in field.aliases)
    return best / 100


def value_score(column: ColumnProfile, row_count: int, field: StandardField) -> float:
    if column.filled_count == 0:
        # Cột trống hoàn toàn (ví dụ cột Nợ của tài khoản chỉ có tiền vào): giá trị không
        # nói được gì, nên trung lập để tên cột quyết định.
        return EMPTY_COLUMN_VALUE_SCORE
    base = COMPATIBILITY[field.type].get(column.kind, 0.0)
    if base == 0.0:
        return 0.0
    distinct_share = column.distinct_count / column.filled_count
    if field.type == "IDENTIFIER" and distinct_share >= 0.9:
        base = min(1.0, base + 0.2)  # mã thường gần như không trùng nhau
    if field.type == "CATEGORY" and column.distinct_count > 30:
        base *= 0.4  # trạng thái, phương thức chỉ có ít giá trị
    if field.type == "TEXT" and field.key == "description" and column.max_length < 15:
        base *= 0.5  # nội dung giao dịch thường dài
    return base


@dataclass
class Candidate:
    field: str
    score: float


def score_columns(profile: TableProfile) -> dict[str, dict[str, float]]:
    """Điểm cho mọi cặp: {tên cột: {mã cột chuẩn: điểm}}."""
    scores: dict[str, dict[str, float]] = {}
    for column in profile.columns:
        row: dict[str, float] = {}
        is_row_number = _is_row_number(column.name)
        for field in SALES_FIELDS:
            if is_row_number:
                row[field.key] = 0.0
                continue
            value = value_score(column, profile.row_count, field)
            name = name_score(column.name, field)
            if value == 0.0:
                # Kiểu giá trị không hợp (ví dụ cột chữ mà cột chuẩn là tiền) thì gần như loại.
                score = 0.2 * name
            else:
                score = NAME_WEIGHT * name + VALUE_WEIGHT * value
                if name < MIN_NAME_SCORE:
                    score = min(score, WEAK_NAME_CAP)
            row[field.key] = round(score, 4)
        scores[column.name] = row
    return scores


def _is_row_number(column_name: str) -> bool:
    # "No" viết hoa kiểu "No." là số thứ tự; "Nợ" sau khi bỏ dấu cũng thành "no" nên chỉ
    # coi là số thứ tự khi tên gốc không có dấu.
    normalized = normalize_name(column_name)
    if normalized == "no":
        return column_name.strip().rstrip(".").lower() == "no"
    return normalized in ROW_NUMBER_NAMES


def top_candidates(row: dict[str, float], count: int = 3) -> list[Candidate]:
    ranked = sorted(row.items(), key=lambda item: item[1], reverse=True)[:count]
    return [Candidate(field=key, score=score) for key, score in ranked]
