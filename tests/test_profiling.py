"""Kiểm hồ sơ cột: nhận dạng mã, số, ngày, điện thoại, chữ; đếm ô trống và dòng trống."""

import polars as pl

from studio.profiling import profile_table
from studio.reading import ROW_REF


def test_profile_detects_kinds_and_counts() -> None:
    frame = pl.DataFrame({
        ROW_REF: [2, 3, 4, 5],
        "Mã": ["HD000101", "HD000102", "HD000103", None],
        "Tiền": ["1.250.000", "500000", "(20.000)", None],
        "Ngày": ["05/10/2026", "2026-10-06 14:32:10", "07/10/2026 09:15", None],
        "SĐT": ["0912345678", "84 912 345 679", "0387654321", None],
        "Tên": ["Nguyễn Văn An", "Trần Thị Bình", "  ", None],
    })
    profile = profile_table(frame)
    kinds = {column.name: column.kind for column in profile.columns}
    assert kinds == {"Mã": "CODE", "Tiền": "NUMBER", "Ngày": "DATE", "SĐT": "PHONE", "Tên": "TEXT"}
    name_column = profile.columns[4]
    assert name_column.filled_count == 2 and name_column.empty_count == 2
    assert profile.blank_row_count == 1
    assert profile.columns[0].samples == ["HD000101", "HD000102", "HD000103"]


def test_leading_zero_flag_marks_codes_stored_as_digits() -> None:
    frame = pl.DataFrame({ROW_REF: [2, 3], "Mã KH": ["00123", "00456"]})
    column = profile_table(frame).columns[0]
    assert column.has_leading_zero is True
