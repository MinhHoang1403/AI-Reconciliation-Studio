"""Bộ cột chuẩn và các loại bảng của miền bán hàng (đơn hàng, thanh toán, sao kê ngân hàng).

Nội dung (tên, nghĩa, tên cột hay gặp, cột bắt buộc theo loại bảng, cách nhận ra loại bảng…)
nằm trong config/domains/sales/fields.json và table-kinds.json; module này đọc chúng và đưa ra
dạng các module khác dùng. Mỗi cột trong tệp của người dùng sẽ được ánh xạ về một cột chuẩn
(hoặc không ánh xạ); các bước sau (chuẩn hóa, đối soát) chỉ làm việc với cột chuẩn.
"""

from dataclasses import dataclass
from typing import Literal

from studio import config_files

# Kiểu giá trị của cột chuẩn; quyết định cách chuẩn hóa ở Giai đoạn 3.
type FieldType = Literal["IDENTIFIER", "MONEY", "DATE", "PHONE", "TEXT", "CATEGORY"]


@dataclass(frozen=True)
class StandardField:
    key: str
    label: str  # tên tiếng Việt hiển thị cho người dùng
    type: FieldType
    meaning: str  # mô tả ngắn, gửi cho Gemini để hiểu nghĩa cột
    aliases: tuple[str, ...]  # các tên cột hay gặp (viết không dấu, chữ thường)


SALES_FIELDS: tuple[StandardField, ...] = tuple(
    StandardField(item.key, item.label, item.type, item.meaning, item.aliases)
    for item in config_files.fields().fields
)
FIELDS_BY_KEY: dict[str, StandardField] = {field.key: field for field in SALES_FIELDS}

_KINDS = config_files.table_kinds()
# Tên hiển thị của từng loại bảng (đúng thứ tự trong tệp), cuối cùng là "chưa rõ loại".
TABLE_KIND_LABELS: dict[str, str] = {kind.key: kind.label for kind in _KINDS.kinds} | {
    "UNKNOWN": _KINDS.unknown_label
}
# Trường bắt buộc theo loại bảng; mỗi phần tử là nhóm "ít nhất một trong các cột này".
REQUIRED_FIELDS: dict[str, list[tuple[str, ...]]] = {
    kind.key: list(kind.required) for kind in _KINDS.kinds if kind.required
}
# Cột mã mà mỗi dòng phải khác nhau; cùng mã nhưng khác số tiền là mâu thuẫn.
KEY_FIELD: dict[str, str] = {kind.key: kind.key_field for kind in _KINDS.kinds if kind.key_field}
# Vai trong chuỗi đối soát: số nhỏ là bên ghi nhận (đơn hàng), số lớn là nơi tiền về (sao kê).
CHAIN_ORDER: dict[str, int] = {kind.key: kind.chain_order for kind in _KINDS.kinds}
# Họ loại bảng: các loại cùng họ (đơn sàn, đơn cửa hàng) có cùng vai trò khi đối soát.
KIND_FAMILY: dict[str, str] = {kind.key: kind.family for kind in _KINDS.kinds}


def infer_table_kind(fields: set[str]) -> str:
    """Đoán loại bảng từ các cột chuẩn đã ánh xạ: xét các loại theo "priority" trong
    table-kinds.json, loại đầu tiên có đủ dấu hiệu ("any": có ít nhất một cột, "all": có đủ
    mọi cột) là loại của bảng."""
    for kind in sorted(_KINDS.kinds, key=lambda item: item.detect.priority):
        detect = kind.detect
        if detect.any and not set(detect.any) & fields:
            continue
        if detect.all and not set(detect.all) <= fields:
            continue
        if detect.any or detect.all:
            return kind.key
    return "UNKNOWN"
