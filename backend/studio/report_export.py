"""Xuất báo cáo một kỳ ra XLSX (3 sheet) và CSV (toàn bộ kết quả), cùng một nguồn số liệu.

Hai định dạng dựng từ CÙNG danh sách cột và cùng giá trị (`result_table`), nên "Toàn bộ kết quả"
trong XLSX và tệp CSV luôn có cùng nội dung (điều kiện xong của Giai đoạn 7).

Chống chèn công thức (CSV/Formula Injection, OWASP): ô chữ bắt đầu bằng = + - @ (hoặc tab,
xuống dòng) được thêm dấu ' ở đầu để Excel coi là chữ, không chạy như công thức. Nội dung
chuyển khoản, ghi chú là chữ người khác nhập nên có thể chứa công thức độc hại.
"""

import csv
import io
from decimal import Decimal
from typing import Any

import xlsxwriter

from studio import report_ai

STATUS_LABELS = {"OPEN": "Cần xử lý", "EXPLAINED": "Đã giải thích", "RESOLVED": "Đã xử lý"}
RESULT_HEADERS = (
    "Cặp đối soát",
    "Loại kết quả",
    "Trạng thái",
    "Mã",
    "Ngày",
    "Số tiền bên A",
    "Số tiền bên B",
    "Số tiền liên quan",
    "Dòng bên A",
    "Dòng bên B",
    "Lý do",
    "Ghi chú",
)
EXCEPTION_HEADERS = ("Tuổi (ngày, tới cuối kỳ)",) + RESULT_HEADERS
FORMULA_START = ("=", "+", "-", "@", "\t", "\r", "\n")


def safe_text(value: str) -> str:
    return "'" + value if value.startswith(FORMULA_START) else value


def _amount(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _left_rows(item: dict[str, Any]) -> str:
    """Dòng bên A; dòng chờ mang sang từ kỳ trước ghi riêng (thuộc bảng của kỳ trước)."""
    text = ", ".join(str(ref) for ref in item["left_rows"])
    if item.get("carried_rows"):
        carried = "kỳ trước: " + ", ".join(str(ref) for ref in item["carried_rows"])
        text = f"{text}; {carried}" if text else carried
    return text


def _row(item: dict[str, Any]) -> list[Any]:
    return [
        item["pair"],
        item["kind_label"],
        STATUS_LABELS.get(item["status"] or "", ""),
        ", ".join(item["codes"]),
        item["date"] or "",
        _amount(item["amount_left"]),
        _amount(item["amount_right"]),
        _amount(item["amount"]),
        _left_rows(item),
        ", ".join(str(ref) for ref in item["right_rows"]),
        item["reason"],
        item["note"] or "",
    ]


def result_table(report: dict[str, Any]) -> list[list[Any]]:
    """Bảng "Toàn bộ kết quả": mỗi kết quả của mọi cặp một dòng, kèm lý do và dòng gốc."""
    return [_row(item) for item in report["results"]]


def exception_table(report: dict[str, Any]) -> list[list[Any]]:
    return [[item["age_days"]] + _row(item) for item in report["exceptions"]]


def summary_table(report: dict[str, Any]) -> list[list[Any]]:
    kpis = report["kpis"]
    # Tỷ lệ viết như trên trang Báo cáo (91,3%); không có gì cần đối chiếu thì "chưa có".
    rate = report_ai.rate_text
    rows: list[list[Any]] = [
        ["Kỳ đối soát", report["label"]],
        ["Đã qua kiểm chứng", "Có" if report["verified"] else "Không"],
        ["Tỷ lệ khớp theo số tiền", rate(kpis["match_rate_amount"])],
        ["Tỷ lệ khớp theo số dòng", rate(kpis["match_rate_rows"])],
        ["Số tiền cần đối chiếu", kpis["amount_in_scope"]],
        ["Số tiền đã khớp", kpis["amount_matched"]],
        ["Số ca cần xử lý", kpis["open_count"]],
        ["Tổng lệch tiền", kpis["mismatch_total"]],
        ["Thiếu tiền về (chỉ có ở bên A)", kpis["missing_amount"]],
        ["Tiền về chưa rõ nguồn (chỉ có ở bên B)", kpis["unknown_amount"]],
        ["Số dòng chờ tiền về", kpis["pending_count"]],
        ["Số tiền chờ tiền về", kpis["pending_amount"]],
        [],
        [
            "Cặp đối soát",
            "Tỷ lệ khớp theo tiền",
            "Tỷ lệ khớp theo dòng",
            "Cần xử lý",
            "Tổng lệch",
            "Thiếu tiền về",
            "Chưa rõ nguồn",
            "Chờ tiền về",
        ],
    ]
    for pair in report["pairs"]:
        rows.append(
            [
                pair["label"],
                rate(pair["match_rate_amount"]),
                rate(pair["match_rate_rows"]),
                pair["open_count"],
                pair["mismatch_total"],
                pair["missing_amount"],
                pair["unknown_amount"],
                pair["pending_amount"],
            ]
        )
    return rows


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        # Tiền VND không có số lẻ: 3410000.00 → 3410000 (giữ phần lẻ nếu có).
        return format(value.normalize(), "f") if value == value.to_integral() else str(value)
    return safe_text(str(value))


def to_csv(report: dict[str, Any]) -> bytes:
    """CSV UTF-8 có BOM (Excel trên Windows đọc đúng tiếng Việt), dấu phẩy phân cách."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(RESULT_HEADERS)
    for row in result_table(report):
        writer.writerow([_csv_value(value) for value in row])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def to_xlsx(report: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    book = xlsxwriter.Workbook(buffer, {"in_memory": True})
    bold = book.add_format({"bold": True})
    money = book.add_format({"num_format": "#,##0"})

    def write(name: str, headers: tuple[str, ...] | None, rows: list[list[Any]]) -> None:
        sheet = book.add_worksheet(name)
        start = 0
        if headers:
            sheet.write_row(0, 0, headers, bold)
            sheet.freeze_panes(1, 0)
            start = 1
        for r, row in enumerate(rows, start=start):
            for c, value in enumerate(row):
                if value is None:
                    continue
                if isinstance(value, Decimal):
                    sheet.write_number(r, c, float(value), money)
                elif isinstance(value, int):
                    sheet.write_number(r, c, value)
                else:
                    # write_string: không bao giờ hiểu chữ là công thức; vẫn thêm ' cho giống CSV.
                    sheet.write_string(r, c, safe_text(str(value)))
        sheet.set_column(0, max(len(headers or ()), 2), 18)

    write("Tóm tắt", None, summary_table(report))
    write("Cần xử lý", EXCEPTION_HEADERS, exception_table(report))
    write("Toàn bộ kết quả", RESULT_HEADERS, result_table(report))
    book.close()
    return buffer.getvalue()
