"""Kiểm việc đọc tệp: bảng mã, dấu phân cách, dòng tiêu đề, số 0 đầu mã, số dòng gốc."""

import io
import unicodedata

import polars as pl
import pytest
import xlsxwriter
from conftest import FIXTURES

from studio import reading


def table_from_csv(content: bytes) -> reading.ReadTable:
    raw = reading.read_csv(content)
    return reading.build_table(raw, reading.detect_header_row(raw.frame))


def test_csv_semicolon_with_bom_keeps_leading_zeros_and_row_refs() -> None:
    content = "﻿Mã;Tiền;SĐT\n00123;1.250.000;0912345678\nDH-02;500;\n".encode()
    table = table_from_csv(content)
    assert table.header_row == 1
    assert table.column_names == ["Mã", "Tiền", "SĐT"]
    assert table.frame[reading.ROW_REF].to_list() == [2, 3]
    assert table.frame["Mã"].to_list() == ["00123", "DH-02"]
    assert table.frame["SĐT"].to_list() == ["0912345678", None]


VIETNAMESE_CSV = (
    "Mã đơn,Khách hàng,Số tiền\nHD001,Nguyễn Văn Bình,1.250.000\nHD002,Trần Thị Ưng,300.000\n"
)


def windows_1258(text: str) -> bytes:
    """Mã hóa như Excel trên Windows tiếng Việt: chữ có sẵn trong bảng mã (â, ê, ô, ơ, ư, ă,
    đ…) giữ nguyên, dấu thanh tách thành ký tự tổ hợp rời."""
    out = b""
    for char in text:
        try:
            out += char.encode("cp1258")
        except UnicodeEncodeError:
            parts = unicodedata.normalize("NFD", char)
            out += unicodedata.normalize("NFC", parts[:-1]).encode("cp1258")
            out += parts[-1].encode("cp1258")
    return out


@pytest.mark.parametrize(
    ("content", "encoding"),
    [
        (VIETNAMESE_CSV.encode("utf-8"), "utf-8"),
        (VIETNAMESE_CSV.encode("utf-8-sig"), "utf-8"),
        (VIETNAMESE_CSV.encode("utf-16"), "utf-16"),  # Excel "Unicode Text"
        (windows_1258(VIETNAMESE_CSV), "cp1258"),  # Excel "CSV" trên Windows tiếng Việt
    ],
)
def test_csv_common_encodings_read_to_the_same_text(content: bytes, encoding: str) -> None:
    text, found = reading.decode_text(content)
    assert found == encoding
    # Cùng một chữ ở dạng dựng sẵn (NFC), nên "Bình" từ tệp Windows-1258 khớp "Bình" gõ tay.
    assert text == VIETNAMESE_CSV
    table = table_from_csv(content)
    assert table.column_names == ["Mã đơn", "Khách hàng", "Số tiền"]
    assert table.frame["Khách hàng"].to_list() == ["Nguyễn Văn Bình", "Trần Thị Ưng"]


# Byte không thuộc Windows-1258; ảnh JPEG bị đặt đuôi .csv (giải ra ký tự điều khiển).
@pytest.mark.parametrize("content", [b"Ma,Ten\n1,\x81\x8d", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"])
def test_unreadable_encoding_is_rejected_with_clear_message(content: bytes) -> None:
    with pytest.raises(reading.ReadError, match="CSV UTF-8"):
        reading.read_csv(content)


def test_empty_and_duplicate_header_names_are_made_unique() -> None:
    table = table_from_csv(b"Ma,,Ma\nA1,x,y\nA2,z,w\n")
    assert table.column_names == ["Ma", "Cột 2", "Ma (2)"]


def test_trailing_blank_rows_are_dropped_but_inner_blank_rows_kept() -> None:
    table = table_from_csv(b"Ma,Ten\nA1,An\n,\nA2,Binh\n,\n,\n")
    assert table.frame[reading.ROW_REF].to_list() == [2, 3, 4]


def test_header_is_found_below_report_title_rows() -> None:
    buffer = io.BytesIO()
    book = xlsxwriter.Workbook(buffer)
    sheet = book.add_worksheet("Sheet1")
    sheet.write("A1", "BÁO CÁO DOANH THU")
    sheet.write("A2", "Tháng 10/2026")
    sheet.write_row("A4", ["Mã đơn", "Ngày", "Số tiền"])
    sheet.write_row("A5", ["DH01", "05/10/2026", 120000])
    sheet.write_row("A6", ["DH02", "06/10/2026", 99000])
    book.close()
    [raw] = reading.read_xlsx(buffer.getvalue())
    table = reading.build_table(raw, reading.detect_header_row(raw.frame))
    assert table.header_row == 4
    assert table.frame[reading.ROW_REF].to_list() == [5, 6]
    assert table.frame["Số tiền"].to_list() == ["120000", "99000"]


def test_bank_fixture_reads_visible_sheets_only() -> None:
    sheets = reading.read_xlsx((FIXTURES / "sao-ke-ngan-hang.xlsx").read_bytes())
    assert [sheet.name for sheet in sheets] == ["TK chinh", "TK san"]
    table = reading.build_table(sheets[0], reading.detect_header_row(sheets[0].frame))
    assert table.header_row == 5
    assert table.column_names == ["STT", "Ngày giao dịch", "Số tham chiếu", "Nợ", "Có", "Số dư",
                                  "Nội dung"]


def test_user_header_row_outside_sheet_is_rejected() -> None:
    raw = reading.read_csv(b"a,b\n1,2\n")
    with pytest.raises(reading.ReadError):
        reading.header_index_from_row(raw, 99)


def test_sheet_without_header_uses_generic_names() -> None:
    raw = reading.RawSheet(name=None, frame=pl.DataFrame({"x": ["1", "2"], "y": ["3", "4"]}))
    table = reading.build_table(raw, None)
    assert table.column_names == ["Cột 1", "Cột 2"]
    assert table.frame[reading.ROW_REF].to_list() == [1, 2]
