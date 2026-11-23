"""Sinh bộ dữ liệu mẫu miền bán hàng, kèm đáp án đối soát.

Dữ liệu hoàn toàn tổng hợp (không phải dữ liệu thật) nhưng mô phỏng 4 loại nguồn:
đơn hàng sàn TMĐT, đơn hàng phần mềm bán hàng, giao dịch cổng thanh toán, sao kê ngân hàng.
Dùng seed cố định nên chạy lại luôn ra đúng cùng các tệp.

Cách chạy:  uv run --locked python tools/make_sales_fixtures.py
Kết quả nằm trong tests/fixtures/sales/.
"""

import csv
import datetime as dt
import io
import random
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import xlsxwriter

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sales"
SEED = 20261020
PERIOD_START = dt.date(2026, 10, 1)
PERIOD_DAYS = 14
FIXED_CREATED = dt.datetime(2026, 11, 1)

# Tệp đầu ra; tên chung chung, không mang thương hiệu thật.
PLATFORM_FILE = "don-hang-san-tmdt.xlsx"
POS_FILE = "don-hang-cua-hang.csv"
GATEWAY_FILE = "giao-dich-cong-thanh-toan.csv"
BANK_FILE = "sao-ke-ngan-hang.xlsx"
ANSWER_FILE = "dap-an.csv"

HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ"]
DEM = ["Văn", "Thị", "Minh", "Thu", "Quang", "Ngọc", "Thanh", "Hữu", "Gia", "Bảo"]
TEN = [
    "An",
    "Bình",
    "Châu",
    "Dũng",
    "Hà",
    "Hải",
    "Hoa",
    "Huy",
    "Khánh",
    "Lan",
    "Linh",
    "Nam",
    "Phúc",
    "Quân",
    "Tâm",
    "Trang",
    "Tuấn",
    "Vy",
    "Yến",
    "Long",
]

# Bỏ dấu tiếng Việt cho nội dung chuyển khoản (ngân hàng thường in chữ hoa không dấu).
_VIET = str.maketrans(
    "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ"
    "ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ",
    "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd"
    "AAAAAAAAAAAAAAAAAEEEEEEEEEEEIIIIIOOOOOOOOOOOOOOOOOUUUUUUUUUUUYYYYYD",
)


def unaccent_upper(text: str) -> str:
    return text.translate(_VIET).upper()


def vn_money(amount: int) -> str:
    """Định dạng tiền kiểu Việt: 1250000 → '1.250.000'."""
    return f"{amount:,}".replace(",", ".")


@dataclass
class Ref:
    """Vị trí một dòng trong tệp nguồn: tệp, sheet (nếu có) và số dòng tính từ 1."""

    file: str
    sheet: str
    row: int = 0


@dataclass
class AnswerKey:
    """Đáp án: mỗi dòng nói một dòng bên trái khớp với dòng nào bên phải và loại khớp."""

    rows: list[dict[str, str]] = field(default_factory=list)

    def add(
        self,
        case: str,
        relation: str,
        kind: str,
        left: Ref | None,
        right: Ref | None,
        note: str = "",
    ) -> None:
        self.rows.append(
            {
                "case_id": case,
                "relation": relation,
                "kind": kind,
                "left_file": left.file if left else "",
                "left_sheet": left.sheet if left else "",
                "left_row": str(left.row) if left else "",
                "right_file": right.file if right else "",
                "right_sheet": right.sheet if right else "",
                "right_row": str(right.row) if right else "",
                "note": note,
            }
        )


@dataclass
class BankLine:
    day: dt.date
    credit: int
    debit: int
    content: str
    ref: Ref


class SalesFixtureBuilder:
    def __init__(self, seed: int = SEED, platform_orders: int = 180, pos_orders: int = 220) -> None:
        self.rng = random.Random(seed)
        self.platform_count = platform_orders
        self.pos_count = pos_orders
        self.answers = AnswerKey()
        self.bank_main: list[BankLine] = []  # tài khoản nhận tiền cửa hàng và cổng thanh toán
        self.bank_platform: list[BankLine] = []  # tài khoản nhận tiền sàn TMĐT

    # ---------- tiện ích ngẫu nhiên ----------
    def name(self) -> str:
        return f"{self.rng.choice(HO)} {self.rng.choice(DEM)} {self.rng.choice(TEN)}"

    def phone(self) -> str:
        return (
            "0" + self.rng.choice("389") + "".join(self.rng.choice("0123456789") for _ in range(8))
        )

    def amount(self, low: int = 90, high: int = 4500) -> int:
        return self.rng.randint(low, high) * 1000

    def day(self) -> dt.date:
        return PERIOD_START + dt.timedelta(days=self.rng.randrange(PERIOD_DAYS))

    def moment(self, day: dt.date) -> dt.datetime:
        return dt.datetime.combine(
            day, dt.time(self.rng.randint(8, 21), self.rng.randrange(60), self.rng.randrange(60))
        )

    # ---------- đơn hàng sàn TMĐT (Excel, có phí sàn, sàn trả tiền gộp theo ngày) ----------
    def build_platform(self) -> list[list[object]]:
        rows: list[list[object]] = []
        settled: dict[dt.date, list[tuple[int, int]]] = defaultdict(
            list
        )  # ngày → (dòng, thực nhận)
        header_rows = 4  # 2 dòng tiêu đề, 1 dòng trống, 1 dòng tên cột
        for index in range(self.platform_count):
            day = self.day()
            code = day.strftime("%y%m%d") + "".join(
                self.rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6)
            )
            total = self.amount(60, 2500)
            fee = round(total * self.rng.choice([0.08, 0.1, 0.12]) / 100) * 100
            cancelled = self.rng.random() < 0.06
            status = "Đã hủy" if cancelled else "Hoàn thành"
            buyer = unaccent_upper(self.name()).lower().replace(" ", ".")[:14] + str(
                self.rng.randint(1, 99)
            )
            phone = "84" + self.phone()[1:]
            rows.append([code, self.moment(day), buyer, phone, total, fee, total - fee, status])
            if not cancelled:
                settled[day].append((header_rows + index + 1, total - fee))
        self._platform_settled = settled
        return rows

    # ---------- đơn hàng phần mềm bán hàng (CSV) ----------
    def build_pos(self) -> list[list[str]]:
        rows: list[list[str]] = []
        self._pos_transfer: list[tuple[int, dt.date, int, str, str]] = []
        self._pos_card: list[tuple[int, dt.datetime, int, str]] = []
        for index in range(self.pos_count):
            day = self.day()
            moment = self.moment(day)
            code = f"HD{index + 101:06d}"  # giữ số 0 ở đầu
            customer = self.name() if self.rng.random() > 0.15 else "Khách lẻ"
            phone = self.phone() if customer != "Khách lẻ" else ""
            total = self.amount()
            method = self.rng.choices(["Tiền mặt", "Chuyển khoản", "Thẻ/QR"], weights=[3, 4, 3])[0]
            rows.append(
                [code, moment.strftime("%d/%m/%Y %H:%M"), customer, phone, str(total), method]
            )
            line = index + 2  # dòng 1 là tên cột
            if method == "Chuyển khoản":
                self._pos_transfer.append((line, day, total, code, customer))
            elif method == "Thẻ/QR":
                self._pos_card.append((line, moment, total, code))
        return rows

    # ---------- giao dịch cổng thanh toán ----------
    # CSV dấu ;, tiền kiểu 1.250.000, cổng trả tiền gộp theo từng đợt.
    # Ca cài sẵn cho đối soát đơn cửa hàng ↔ cổng (theo thứ tự đơn quẹt thẻ, không dùng số
    # ngẫu nhiên để các tệp khác không đổi).
    GW_SHORT_PAID_AT = 3  # cổng thu ít hơn giá trên đơn 20.000đ → AMOUNT_MISMATCH
    GW_MISSING_AT = 10  # đơn quẹt thẻ nhưng cổng không có giao dịch → ONLY_IN_A
    GW_NO_CODE_AT = 15  # giao dịch không ghi mã đơn → khớp theo số tiền và ngày
    GW_TYPO_AT = 20  # mã đơn gõ sai một ký tự → khớp theo số tiền và ngày
    GW_CHARGED_TWICE_AT = 25  # khách bị trừ tiền hai lần → một khớp, một DUPLICATE

    def build_gateway(self) -> list[list[str]]:
        rows: list[list[str]] = []
        batches: dict[str, list[tuple[int, int]]] = defaultdict(list)
        relation = "cua-hang↔cong-thanh-toan"

        def emit(txn: str, code: str, moment: dt.datetime, charged: int) -> int:
            """Ghi một giao dịch cổng; trả về số dòng của nó trong tệp (dòng 1 là tên cột)."""
            fee = round(charged * 0.011)
            batch = "DOT" + (moment.date() + dt.timedelta(days=1)).strftime("%y%m%d")
            rows.append(
                [
                    txn,
                    code,
                    moment.strftime("%Y-%m-%d %H:%M:%S"),
                    vn_money(charged),
                    vn_money(fee),
                    vn_money(charged - fee),
                    batch,
                ]
            )
            line = len(rows) + 1
            batches[batch].append((line, charged - fee))
            return line

        for index, (pos_line, moment, total, code) in enumerate(self._pos_card):
            txn = f"GD{self.rng.randrange(10**9, 10**10)}"
            pos_ref = Ref(POS_FILE, "", pos_line)
            if index == self.GW_MISSING_AT:
                self.answers.add(
                    f"POS-GW-{code}",
                    relation,
                    "ONLY_IN_A",
                    pos_ref,
                    None,
                    "Đơn quẹt thẻ nhưng cổng không có giao dịch",
                )
                continue
            kind, note, shown_code, charged = "MATCHED", "", code, total
            if index == self.GW_SHORT_PAID_AT:
                kind, charged = "AMOUNT_MISMATCH", total - 20_000
                note = "Cổng thu ít hơn đơn 20.000đ"
            elif index == self.GW_NO_CODE_AT:
                note, shown_code = "Giao dịch không ghi mã đơn; khớp theo số tiền và ngày", ""
            elif index == self.GW_TYPO_AT:
                note, shown_code = "Mã đơn gõ sai; khớp theo số tiền và ngày", code[:-1] + "X"
            line = emit(txn, shown_code, moment, charged)
            self.answers.add(
                f"POS-GW-{code}", relation, kind, pos_ref, Ref(GATEWAY_FILE, "", line), note
            )
            if index == self.GW_CHARGED_TWICE_AT:
                again = emit(f"GD{int(txn[2:]) + 7}", code, moment + dt.timedelta(minutes=1), total)
                self.answers.add(
                    f"POS-GW-{code}-LAN-2",
                    relation,
                    "DUPLICATE",
                    pos_ref,
                    Ref(GATEWAY_FILE, "", again),
                    "Khách bị trừ tiền hai lần",
                )
        # Giao dịch có mã đơn không tồn tại trong phần mềm bán hàng → ONLY_IN_B.
        stray = emit("GD9000000001", "HD000950", dt.datetime(2026, 10, 5, 14, 20, 0), 780_000)
        self.answers.add(
            "GW-ONLY-HD000950",
            relation,
            "ONLY_IN_B",
            None,
            Ref(GATEWAY_FILE, "", stray),
            "Giao dịch không có đơn trong phần mềm bán hàng",
        )
        self._gateway_batches = batches
        return rows

    # ---------- sao kê ngân hàng ----------
    def build_bank(self) -> None:
        # Chuyển khoản của khách cho đơn cửa hàng: thường 1:1, có cài sẵn ca lệch tiền và ca thiếu.
        transfers = list(self._pos_transfer)
        missing = transfers.pop(5)  # đơn chuyển khoản không thấy tiền về
        self.answers.add(
            f"POS-BANK-{missing[3]}",
            "cua-hang↔sao-ke",
            "ONLY_IN_A",
            Ref(POS_FILE, "", missing[0]),
            None,
            "Không có giao dịch tương ứng",
        )
        for position, (line, day, total, code, customer) in enumerate(transfers):
            paid = total - 50_000 if position == 7 else total  # khách chuyển thiếu 50.000đ
            who = unaccent_upper(customer) if customer != "Khách lẻ" else ""
            style = position % 3
            content = (
                f"CK {code} {who}".strip()
                if style == 0
                else f"{who} chuyen tien don {code.lower()}".strip()
                if style == 1
                else f"TT DON HANG {code}"
            )
            bank_day = day + dt.timedelta(days=self.rng.choice([0, 0, 1]))
            item = BankLine(bank_day, paid, 0, content, Ref(BANK_FILE, "TK chinh", 0))
            self.bank_main.append(item)
            kind = "AMOUNT_MISMATCH" if paid != total else "MATCHED"
            self._pending_links = getattr(self, "_pending_links", [])
            self._pending_links.append(
                (f"POS-BANK-{code}", "cua-hang↔sao-ke", kind, Ref(POS_FILE, "", line), item, "")
            )
        # Cổng thanh toán trả tiền gộp từng đợt: nhiều giao dịch ↔ một dòng sao kê.
        for batch, items in sorted(self._gateway_batches.items()):
            day = dt.datetime.strptime(batch[3:], "%y%m%d").date()
            item = BankLine(
                day,
                sum(net for _, net in items),
                0,
                f"CONG TT CHUYEN TIEN {batch}",
                Ref(BANK_FILE, "TK chinh", 0),
            )
            self.bank_main.append(item)
            for gateway_line, _ in items:
                self._pending_links.append(
                    (
                        f"GW-BANK-{batch}",
                        "cong-thanh-toan↔sao-ke",
                        "MANY_TO_ONE",
                        Ref(GATEWAY_FILE, "", gateway_line),
                        item,
                        "",
                    )
                )
        # Sàn TMĐT trả tiền gộp theo ngày vào tài khoản riêng.
        for day, items in sorted(self._platform_settled.items()):
            item = BankLine(
                day + dt.timedelta(days=2),
                sum(net for _, net in items),
                0,
                f"SAN TMDT THANH TOAN DOANH THU NGAY {day:%d/%m/%Y}",
                Ref(BANK_FILE, "TK san", 0),
            )
            self.bank_platform.append(item)
            for platform_line, _ in items:
                self._pending_links.append(
                    (
                        f"SAN-BANK-{day:%y%m%d}",
                        "san-tmdt↔sao-ke",
                        "MANY_TO_ONE",
                        Ref(PLATFORM_FILE, "Đơn hàng", platform_line),
                        item,
                        "",
                    )
                )
        # Ca mơ hồ: hai khách cùng tên Hoàng, cùng ngày, cùng số tiền; nội dung không có mã đơn.
        twin_day = PERIOD_START + dt.timedelta(days=9)
        self._ambiguous = []
        for _ in range(2):
            item = BankLine(
                twin_day, 1_350_000, 0, "CK TIEN HANG HOANG", Ref(BANK_FILE, "TK chinh", 0)
            )
            self.bank_main.append(item)
            self._ambiguous.append(item)
        # Giao dịch không liên quan đơn hàng: phí ngân hàng, chi lương, tiền lạ.
        for content, debit, credit in [
            ("PHI QUAN LY TAI KHOAN T10", 22_000, 0),
            ("CHI LUONG NHAN VIEN T9", 18_500_000, 0),
            ("NOP TIEN MAT VAO TK", 0, 5_000_000),
        ]:
            item = BankLine(
                PERIOD_START + dt.timedelta(days=self.rng.randrange(PERIOD_DAYS)),
                credit,
                debit,
                content,
                Ref(BANK_FILE, "TK chinh", 0),
            )
            self.bank_main.append(item)
            self._pending_links.append(
                (
                    f"BANK-ONLY-{content[:12]}",
                    "cua-hang↔sao-ke",
                    "ONLY_IN_B",
                    None,
                    item,
                    "Không liên quan đơn hàng",
                )
            )

    # ---------- ghi tệp ----------
    def write_platform(self, rows: list[list[object]]) -> bytes:
        buffer = io.BytesIO()
        book = xlsxwriter.Workbook(buffer, {"in_memory": True})
        book.set_properties(
            {"created": FIXED_CREATED}
        )  # ngày cố định để tệp sinh ra giống hệt mỗi lần
        title = book.add_format({"bold": True, "font_size": 14})
        date_format = book.add_format({"num_format": "dd/mm/yyyy hh:mm"})
        sheet = book.add_worksheet("Đơn hàng")
        sheet.write(0, 0, "BÁO CÁO ĐƠN HÀNG (DỮ LIỆU MẪU TỔNG HỢP)", title)
        sheet.write(
            1,
            0,
            f"Từ {PERIOD_START:%d/%m/%Y} đến "
            f"{PERIOD_START + dt.timedelta(days=PERIOD_DAYS - 1):%d/%m/%Y}",
        )
        sheet.write_row(
            3,
            0,
            [
                "Mã đơn hàng",
                "Ngày đặt hàng",
                "Tên người mua",
                "SĐT người nhận",
                "Tổng tiền hàng",
                "Phí sàn",
                "Số tiền thực nhận",
                "Trạng thái",
            ],
        )
        for offset, row in enumerate(rows):
            sheet.write_string(4 + offset, 0, str(row[0]))
            sheet.write_datetime(4 + offset, 1, row[1], date_format)
            sheet.write_string(4 + offset, 2, str(row[2]))
            sheet.write_string(4 + offset, 3, str(row[3]))
            for column in (4, 5, 6):
                sheet.write_number(4 + offset, column, row[column])
            sheet.write_string(4 + offset, 7, str(row[7]))
        guide = book.add_worksheet("Hướng dẫn")
        guide.write(0, 0, "Sheet này chỉ có ghi chú, không có dữ liệu đơn hàng.")
        book.close()
        return buffer.getvalue()

    def write_bank(self) -> bytes:
        buffer = io.BytesIO()
        book = xlsxwriter.Workbook(buffer, {"in_memory": True})
        book.set_properties(
            {"created": FIXED_CREATED}
        )  # ngày cố định để tệp sinh ra giống hệt mỗi lần
        bold = book.add_format({"bold": True})
        for sheet_name, account, lines in [
            ("TK chinh", "0071 0000 12345", self.bank_main),
            ("TK san", "1903 0000 67890", self.bank_platform),
        ]:
            sheet = book.add_worksheet(sheet_name)
            sheet.write(0, 0, "SAO KÊ TÀI KHOẢN (DỮ LIỆU MẪU TỔNG HỢP)", bold)
            sheet.write(1, 0, f"Số tài khoản: {account}")
            sheet.write(
                2,
                0,
                f"Kỳ sao kê: {PERIOD_START:%d/%m/%Y} - "
                f"{PERIOD_START + dt.timedelta(days=PERIOD_DAYS + 2):%d/%m/%Y}",
            )
            sheet.write_row(
                4, 0, ["STT", "Ngày giao dịch", "Số tham chiếu", "Nợ", "Có", "Số dư", "Nội dung"]
            )
            lines.sort(key=lambda item: (item.day, item.content))
            balance = 25_000_000
            for offset, item in enumerate(lines):
                balance += item.credit - item.debit
                row = 5 + offset
                item.ref.row = row + 1  # số dòng Excel tính từ 1
                sheet.write_number(row, 0, offset + 1)
                sheet.write_string(row, 1, item.day.strftime("%d/%m/%Y"))
                sheet.write_string(row, 2, f"FT{item.day:%y%j}{self.rng.randrange(10**5, 10**6)}")
                if item.debit:
                    sheet.write_number(row, 3, item.debit)
                if item.credit:
                    sheet.write_number(row, 4, item.credit)
                sheet.write_number(row, 5, balance)
                sheet.write_string(row, 6, item.content)
        hidden = book.add_worksheet("Bang tra cuu")
        hidden.write(0, 0, "Sheet ẩn của hệ thống ngân hàng")
        hidden.hide()
        book.close()
        return buffer.getvalue()

    def resolve_answers(self) -> None:
        """Ghi đáp án sau khi dòng sao kê đã có số dòng thật trong tệp Excel."""
        for case, relation, kind, left, item, note in self._pending_links:
            self.answers.add(case, relation, kind, left, item.ref, note)
        for item in self._ambiguous:
            self.answers.add(
                "AMBIGUOUS-HOANG",
                "cua-hang↔sao-ke",
                "AMBIGUOUS",
                None,
                item.ref,
                "Hai khách tên Hoàng cùng ngày, cùng số tiền, nội dung không có mã đơn",
            )

    def build(self) -> dict[str, bytes]:
        platform_rows = self.build_platform()
        pos_rows = self.build_pos()
        gateway_rows = self.build_gateway()
        self.build_bank()
        files = {
            PLATFORM_FILE: self.write_platform(platform_rows),
            POS_FILE: pos_csv(pos_rows),
            GATEWAY_FILE: csv_bytes(
                [
                    "Mã giao dịch",
                    "Mã đơn hàng",
                    "Thời gian",
                    "Số tiền",
                    "Phí",
                    "Thực nhận",
                    "Mã đợt chuyển",
                ],
                gateway_rows,
                delimiter=";",
            ),
            BANK_FILE: self.write_bank(),
        }
        self.resolve_answers()
        files[ANSWER_FILE] = csv_bytes(
            list(self.answers.rows[0]), [list(row.values()) for row in self.answers.rows]
        )
        return files


def csv_bytes(
    header: list[str], rows: list[list[str]], delimiter: str = ",", bom: bool = False
) -> bytes:
    text = io.StringIO()
    writer = csv.writer(text, delimiter=delimiter, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    return ("﻿" if bom else "").encode() + text.getvalue().encode("utf-8")


# Lỗi cài sẵn ở cuối tệp đơn hàng cửa hàng; đáp án cho bước làm sạch nằm ở loi-cai-san.csv.
# Toàn bộ là đơn trả tiền mặt nên không ảnh hưởng đáp án đối soát (dap-an.csv).
POS_INJECTED_ERRORS = [
    ["", "06/10/2026 10:15", "Nguyễn Văn Khoa", "0912000111", "450000", "Tiền mặt"],  # thiếu mã
    ["HD000901", "07/10/2026 11:00", "Lê Thị Mai", "0913000222", "1tr2", "Tiền mặt"],  # viết tắt
    ["HD000902", "07/10/2026 11:30", "Phạm Văn Tú", "0914000333", "khoảng 500k", "Tiền mặt"],
    ["HD000903", "5/10/2026 9:05", "Võ Thị Lan", "84915000444", "320000", "Tiền mặt"],  # đầu 84
    ["HD000904", "08/10/2026 15:20", "  Trần   Thị  Bình ", "0916000555", "275000", "Tiền mặt"],
    [
        "HD000101",
        "01/10/2026 09:00",
        "Nguyễn Văn An",
        "0917000666",
        "999000",
        "Tiền mặt",
    ],  # trùng mã
    ["HD000905", "ngày 9 tháng 10", "Đỗ Văn Hùng", "0918000777", "150000", "Tiền mặt"],  # ngày lạ
]


def pos_csv(rows: list[list[str]]) -> bytes:
    """CSV phần mềm bán hàng: có BOM, một dòng trùng y hệt và một dòng trống cài sẵn.

    Dòng cài thêm được chèn ở cuối để không làm lệch số dòng của các đơn đã ghi trong đáp án.
    """
    extra = [
        ["", "", "", "", "", ""],  # dòng 222: trống (đứng trước để không bị coi là đuôi tệp)
        rows[10],  # dòng 223: trùng y hệt dòng 12
        *POS_INJECTED_ERRORS,  # dòng 224–230: lỗi cài sẵn cho bước làm sạch (xem loi-cai-san.csv)
    ]
    return csv_bytes(
        ["MaHD", "NgayBan", "KhachHang", "DienThoai", "TongTien", "ThanhToan"],
        rows + extra,
        bom=True,
    )


def large_pos_csv(row_count: int, seed: int = SEED) -> bytes:
    """Tệp CSV lớn cùng định dạng phần mềm bán hàng, dùng để đo tốc độ đọc (không lưu vào Git)."""
    builder = SalesFixtureBuilder(seed=seed, pos_orders=row_count)
    return csv_bytes(
        ["MaHD", "NgayBan", "KhachHang", "DienThoai", "TongTien", "ThanhToan"],
        builder.build_pos(),
        bom=True,
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in SalesFixtureBuilder().build().items():
        (OUTPUT_DIR / name).write_bytes(content)
        print(f"{name}: {len(content):,} byte")


if __name__ == "__main__":
    main()
