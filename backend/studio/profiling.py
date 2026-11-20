"""Hồ sơ cột: tóm tắt từng cột để người dùng và bước ánh xạ hiểu dữ liệu.

Hồ sơ chỉ mô tả những gì quan sát được trên dữ liệu dạng chữ; không sửa dữ liệu.
"""

from typing import Literal

import polars as pl
from pydantic import BaseModel

from studio.reading import ROW_REF

# Dạng dữ liệu quan sát được. Chỉ là gợi ý cho bước ánh xạ, không phải kết luận.
type ObservedKind = Literal["EMPTY", "NUMBER", "DATE", "PHONE", "CODE", "TEXT"]

# Một cột được xếp vào một dạng khi ít nhất 90% ô có giá trị khớp mẫu của dạng đó.
KIND_THRESHOLD = 0.9
SAMPLE_COUNT = 5

# Mẫu nhận dạng, áp lên giá trị đã bỏ khoảng trắng hai đầu.
_PATTERNS: list[tuple[ObservedKind, str]] = [
    # Ngày: 05/10/2026, 5-10-26, 2026-10-05, 2026-10-05 14:32:10, 05/10/2026 14:32
    ("DATE", r"^(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2})([ T]\d{1,2}:\d{2}(:\d{2})?)?$"),
    # Điện thoại Việt Nam: 0912345678, 84912345678, +84 912 345 678
    ("PHONE", r"^(\+?84|0)[35789]\d{8}$"),
    # Số và tiền: 1250000, 1.250.000, 1,250,000.50, (500), -12.5
    ("NUMBER", r"^[-(]?\d{1,3}([.,]\d{3})*([.,]\d+)?\)?$|^[-(]?\d+([.,]\d+)?\)?$"),
]
# Mã: chỉ gồm chữ, số và . _ / -, có cả chữ lẫn số, ví dụ HD000123, DH-01, 261005KX7Q2M.
# (Thư viện regex của Polars không hỗ trợ "lookahead" nên kiểm ba điều kiện riêng.)
_CODE_SHAPE = r"^[A-Za-z0-9._/-]{3,40}$"


class ColumnProfile(BaseModel):
    name: str
    position: int
    filled_count: int
    empty_count: int
    distinct_count: int
    max_length: int
    kind: ObservedKind
    # Có giá trị bắt đầu bằng số 0 (dấu hiệu cột là mã, không được đổi thành số).
    has_leading_zero: bool
    samples: list[str]


class TableProfile(BaseModel):
    row_count: int
    blank_row_count: int
    columns: list[ColumnProfile]


def _observed_kind(values: pl.Series) -> ObservedKind:
    if values.len() == 0:
        return "EMPTY"
    compact = values.str.replace_all(r"\s+", "")
    for kind, pattern in _PATTERNS:
        source = compact if kind == "PHONE" else values
        if _share(source.str.contains(pattern)) >= KIND_THRESHOLD:
            return kind
    is_code = (
        values.str.contains(_CODE_SHAPE)
        & values.str.contains(r"\d")
        & values.str.contains(r"[A-Za-z]")
    )
    return "CODE" if _share(is_code) >= KIND_THRESHOLD else "TEXT"


def _share(mask: pl.Series) -> float:
    """Tỷ lệ ô thỏa điều kiện."""
    return float(mask.sum()) / mask.len() if mask.len() else 0.0


def profile_table(frame: pl.DataFrame) -> TableProfile:
    columns = [name for name in frame.columns if name != ROW_REF]
    profiles: list[ColumnProfile] = []
    for position, name in enumerate(columns):
        series = frame[name]
        values = series.drop_nulls().str.strip_chars()
        values = values.filter(values.str.len_chars() > 0)
        profiles.append(ColumnProfile(
            name=name,
            position=position,
            filled_count=values.len(),
            empty_count=frame.height - values.len(),
            distinct_count=values.n_unique(),
            max_length=int(values.str.len_chars().max() or 0),  # type: ignore[arg-type]
            kind=_observed_kind(values),
            # Chỉ tính giá trị toàn chữ số (mã, số điện thoại); ngày như 01/10/2026 không tính.
            has_leading_zero=bool(values.str.contains(r"^0\d+$").any()),
            samples=values.unique(maintain_order=True).head(SAMPLE_COUNT).to_list(),
        ))
    if columns:
        blank_rows = frame.select(
            pl.all_horizontal([
                pl.col(name).is_null() | (pl.col(name).str.strip_chars().str.len_chars() == 0)
                for name in columns
            ])
        ).to_series().sum()
    else:
        blank_rows = frame.height
    return TableProfile(row_count=frame.height, blank_row_count=int(blank_rows), columns=profiles)
