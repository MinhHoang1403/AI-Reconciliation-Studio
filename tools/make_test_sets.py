"""Sinh các bộ dữ liệu thử lớn để Owner kiểm hệ thống bằng tay (7.000–10.000 đơn mỗi bộ).

Mỗi bộ là một kỳ 14 ngày riêng (tháng khác nhau, dải mã đơn khác nhau), đủ 4 nguồn như bộ mẫu:
đơn hàng phần mềm bán hàng (CSV), đơn hàng sàn TMĐT (Excel), giao dịch cổng thanh toán (CSV),
sao kê ngân hàng (Excel hai tài khoản). Dữ liệu hoàn toàn tổng hợp, sinh bằng chính bộ sinh của
bộ mẫu (tools/make_sales_fixtures.py) với seed, kỳ và số đơn khác, nên có đủ các ca cài sẵn:
lệch tiền, thiếu tiền về, tiền lạ, dòng trùng, ô lỗi định dạng, ghép theo tên, ca mơ hồ, một lần
chuyển cho nhiều đơn, cổng trả gộp theo đợt, sàn trả gộp theo ngày. Mỗi bộ kèm đáp án đối soát
(dap-an.csv) và tệp DOC-TRUOC.txt tóm tắt bộ dữ liệu.

Sao kê ghi tới ngày tiền về cuối cùng nên mọi khoản tiền của kỳ đều đã về (không có ca "chờ tiền
về"; ca đó có ở bộ mẫu hai kỳ trong tests/fixtures/sales/).

    uv run --locked python tools/make_test_sets.py

Kết quả nằm trong du-lieu-thu/ (Git bỏ qua vì tệp lớn; chạy lại luôn ra đúng cùng các tệp).
"""

import csv
import datetime as dt
import io
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_sales_fixtures as fixtures  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "du-lieu-thu"
# (số bộ, tổng số đơn, ngày đầu kỳ, mã đơn đầu tiên). Đơn cửa hàng chiếm 70%, đơn sàn 30%.
SETS = [
    (1, 7_000, dt.date(2026, 11, 2), 100_001),
    (2, 8_000, dt.date(2026, 12, 1), 200_001),
    (3, 9_000, dt.date(2027, 1, 4), 300_001),
    (4, 10_000, dt.date(2027, 2, 1), 400_001),
]
PERIOD_DAYS = 14
RELATIONS = {
    "cua-hang↔cong-thanh-toan": "đơn cửa hàng ↔ giao dịch cổng",
    "cua-hang↔sao-ke": "đơn cửa hàng ↔ sao kê (TK chinh)",
    "cong-thanh-toan↔sao-ke": "giao dịch cổng ↔ sao kê (TK chinh)",
    "san-tmdt↔sao-ke": "đơn sàn ↔ sao kê (TK san)",
}
KIND_LABELS = {
    "MATCHED": "khớp",
    "MANY_TO_ONE": "ghép nhóm (nhiều dòng ↔ một dòng)",
    "AMOUNT_MISMATCH": "lệch tiền",
    "ONLY_IN_A": "chỉ có ở bên trái (thiếu tiền về)",
    "ONLY_IN_B": "chỉ có ở bên phải (tiền về chưa rõ nguồn)",
    "DUPLICATE": "trùng (trừ tiền hai lần)",
    "AMBIGUOUS": "mơ hồ, cần người dùng chọn",
    "NEEDS_CLEANING": "dòng còn lỗi ở bước làm sạch",
    "OUT_OF_SCOPE": "ngoài phạm vi (tiền ra)",
}


def build_set(number: int, orders: int, start: dt.date, code_start: int) -> dict[str, bytes]:
    pos = round(orders * 0.7)
    prefix = f"bo-{number}-"
    files = {
        "platform": prefix + "don-hang-san-tmdt.xlsx",
        "pos": prefix + "don-hang-cua-hang.csv",
        "gateway": prefix + "giao-dich-cong-thanh-toan.csv",
        "bank": prefix + "sao-ke-ngan-hang.xlsx",
    }
    builder = fixtures.SalesFixtureBuilder(
        seed=fixtures.SEED + 1000 * number,
        platform_orders=orders - pos,
        pos_orders=pos,
        period_start=start,
        period_days=PERIOD_DAYS,
        code_start=code_start,
        files=files,
        special_cases=True,
    )
    output = builder.build_sources()
    last = max(item.day for item in builder.bank_main + builder.bank_platform)
    output[files["bank"]] = builder.write_bank(start, last)
    # Sao kê có đủ mọi khoản tiền về: mỗi dòng đáp án trỏ thẳng tới dòng sao kê (nếu có).
    answers = builder.answers
    for link in builder.links:
        right = link.item.ref if link.item is not None else None
        answers.add(link.case, link.relation, link.kind, link.left, right, link.note)
    # Dòng cài chép y hệt dòng 12 (ở cuối tệp đơn cửa hàng, sau dòng trống) có cùng số phận
    # với dòng gốc ở mỗi cặp: gốc khớp thì bản chép là "trùng", gốc thiếu tiền thì cũng thiếu.
    pos_file, copy_line = files["pos"], pos + 3
    for row in list(answers.rows):
        if row["left_file"] != pos_file or row["left_row"] != "12":
            continue
        kind = row["kind"] if row["kind"] in ("ONLY_IN_A", "NEEDS_CLEANING") else "DUPLICATE"
        answers.rows.append(
            row | {"case_id": row["case_id"] + "-BAN-CHEP", "kind": kind,
                   "left_row": str(copy_line), "right_file": "", "right_sheet": "",
                   "right_row": "", "note": "Dòng chép y hệt dòng 12 (cài sẵn)"}
        )
    header = list(answers.rows[0])
    output["dap-an.csv"] = fixtures.csv_bytes(header, [list(row.values()) for row in answers.rows])
    output["DOC-TRUOC.txt"] = summary(number, orders, pos, start, last, output, answers.rows)
    return output


def vn(number: int) -> str:
    """Số kiểu Việt Nam: 7.000."""
    return f"{number:,}".replace(",", ".")


def data_rows(name: str, content: bytes) -> str:
    """Số dòng dữ liệu của một tệp (để ghi vào bản tóm tắt)."""
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig")
        first = text.splitlines()[0]
        delimiter = ";" if first.count(";") > first.count(",") else ","
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
        return f"{vn(len(rows) - 1)} dòng (không tính dòng tên cột)"
    import fastexcel

    reader = fastexcel.read_excel(content)
    parts = []
    for sheet_name in reader.sheet_names:
        sheet = reader.load_sheet_by_name(sheet_name, header_row=None)
        if sheet.height > 1:  # bỏ sheet ghi chú, sheet ẩn
            parts.append(f"sheet {sheet_name}: {vn(sheet.height)} dòng (gồm phần tiêu đề)")
    return "; ".join(parts)


def summary(
    number: int,
    orders: int,
    pos: int,
    start: dt.date,
    last: dt.date,
    files: dict[str, bytes],
    answers: list[dict[str, str]],
) -> bytes:
    end = start + dt.timedelta(days=PERIOD_DAYS - 1)
    lines = [
        f"BỘ DỮ LIỆU THỬ SỐ {number} — {vn(orders)} ĐƠN HÀNG (DỮ LIỆU TỔNG HỢP)",
        "",
        f"Kỳ bán hàng: {start:%d/%m/%Y} – {end:%d/%m/%Y}; sao kê tới {last:%d/%m/%Y}.",
        f"Đơn cửa hàng: {vn(pos)}; đơn sàn TMĐT: {vn(orders - pos)}.",
        "",
        "Các tệp:",
    ]
    for name, content in files.items():
        if name.startswith("bo-"):
            lines.append(f"  - {name}: {data_rows(name, content)}")
    lines += [
        "",
        "Cách thử: tạo một phiên làm việc mới, tải cả 4 tệp bo-*, chờ đọc, ánh xạ, làm sạch,",
        "rồi vào Đối soát bấm \"Đối soát cả chuỗi\" cho kỳ này. Tệp đơn cửa hàng có cài sẵn ở",
        "cuối tệp: 1 dòng trống, 1 dòng trùng y hệt, 1 đơn thiếu mã, tiền viết tắt (1tr2,",
        "khoảng 500k), điện thoại đầu 84, khoảng trắng thừa, 1 mã đơn trùng khác số tiền và",
        "1 ngày viết bằng chữ.",
        "",
        "Đáp án đối soát (dap-an.csv), đếm theo cặp và loại:",
    ]
    counts = Counter((row["relation"], row["kind"]) for row in answers)
    for relation, label in RELATIONS.items():
        lines.append(f"  {label}:")
        for (rel, kind), count in sorted(counts.items()):
            if rel == relation:
                lines.append(f"    - {KIND_LABELS.get(kind, kind)}: {vn(count)}")
    lines += [
        "",
        "Ghi chú: đáp án đếm theo dòng bên trái (với ghép nhóm, mỗi dòng bên trái một dòng đáp",
        "án); dòng đơn trả tiền mặt không có trong đáp án vì không có tiền qua cổng hay ngân hàng.",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def main() -> None:
    for number, orders, start, code_start in SETS:
        folder = OUTPUT_DIR / f"bo-{number}-{orders}-don"
        folder.mkdir(parents=True, exist_ok=True)
        for name, content in build_set(number, orders, start, code_start).items():
            (folder / name).write_bytes(content)
        print(f"{folder.relative_to(ROOT)}: xong")


if __name__ == "__main__":
    main()
