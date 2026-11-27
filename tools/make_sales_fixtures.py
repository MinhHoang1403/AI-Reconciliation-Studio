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
from collections.abc import Callable
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
# Kỳ 2 (3 ngày sau kỳ 1): đơn hàng, giao dịch mới và tiền về muộn của kỳ 1.
PERIOD2_START = PERIOD_START + dt.timedelta(days=PERIOD_DAYS)
PERIOD2_DAYS = 3
FILES_PERIOD1 = {
    "platform": PLATFORM_FILE,
    "pos": POS_FILE,
    "gateway": GATEWAY_FILE,
    "bank": BANK_FILE,
}
FILES_PERIOD2 = {
    "platform": "don-hang-san-tmdt-ky-2.xlsx",
    "pos": "don-hang-cua-hang-ky-2.csv",
    "gateway": "giao-dich-cong-thanh-toan-ky-2.csv",
    "bank": "sao-ke-ngan-hang-ky-2.xlsx",
}
# Ngày cuối của sao kê kỳ 1: tiền về sau ngày này nằm trong sao kê kỳ 2.
BANK1_CUTOFF = PERIOD_START + dt.timedelta(days=PERIOD_DAYS - 1)
# Khung chờ tiền về (docs/DECISIONS.md 2026-11-23): 3 ngày làm việc, bỏ thứ Bảy, Chủ nhật.
SETTLEMENT_BUSINESS_DAYS = 3
KY2 = " (kỳ 2)"


def add_business_days(day: dt.date, count: int) -> dt.date:
    """Cộng số ngày làm việc (bỏ thứ Bảy, Chủ nhật), cùng quy tắc với engine đối soát."""
    while count > 0:
        day += dt.timedelta(days=1)
        if day.weekday() < 5:
            count -= 1
    return day

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


@dataclass
class Link:
    """Một dòng đáp án chờ dòng sao kê có số dòng thật: bên A, dòng sao kê (hoặc không có)."""

    case: str
    relation: str
    kind: str
    left: Ref | None
    left_day: dt.date | None
    item: BankLine | None
    note: str = ""


class SalesFixtureBuilder:
    def __init__(
        self,
        seed: int = SEED,
        platform_orders: int = 180,
        pos_orders: int = 220,
        period_start: dt.date = PERIOD_START,
        period_days: int = PERIOD_DAYS,
        code_start: int = 101,
        files: dict[str, str] | None = None,
        special_cases: bool = True,
        relation_suffix: str = "",
    ) -> None:
        self.rng = random.Random(seed)
        self.platform_count = platform_orders
        self.pos_count = pos_orders
        self.period_start = period_start
        self.period_days = period_days
        self.code_start = code_start
        self.files = files or FILES_PERIOD1
        # Ca cài sẵn (lệch tiền, thiếu, mơ hồ...) chỉ có ở kỳ 1; kỳ 2 là dữ liệu bình thường.
        self.special_cases = special_cases
        self.suffix = relation_suffix
        self.answers = AnswerKey()
        self.links: list[Link] = []
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
        return self.period_start + dt.timedelta(days=self.rng.randrange(self.period_days))

    def moment(self, day: dt.date) -> dt.datetime:
        return dt.datetime.combine(
            day, dt.time(self.rng.randint(8, 21), self.rng.randrange(60), self.rng.randrange(60))
        )

    # ---------- đơn hàng sàn TMĐT (Excel, có phí sàn, sàn trả tiền gộp theo ngày) ----------
    def build_platform(self) -> list[list[object]]:
        rows: list[list[object]] = []
        # ngày → (dòng, thực nhận)
        settled: dict[dt.date, list[tuple[int, int]]] = defaultdict(list)
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
        self._pos_rows = rows  # giữ lại để cài ca đặc biệt ở bước sao kê trước khi ghi tệp
        self._pos_transfer: list[tuple[int, dt.date, int, str, str]] = []
        self._pos_card: list[tuple[int, dt.datetime, int, str]] = []
        for index in range(self.pos_count):
            day = self.day()
            moment = self.moment(day)
            code = f"HD{index + self.code_start:06d}"  # giữ số 0 ở đầu
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
        batches: dict[str, list[tuple[int, int, dt.date]]] = defaultdict(list)
        relation = "cua-hang↔cong-thanh-toan" + self.suffix
        pos_file, gateway_file = self.files["pos"], self.files["gateway"]
        special = self.special_cases

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
            batches[batch].append((line, charged - fee, moment.date()))
            return line

        for index, (pos_line, moment, total, code) in enumerate(self._pos_card):
            txn = f"GD{self.rng.randrange(10**9, 10**10)}"
            pos_ref = Ref(pos_file, "", pos_line)
            if special and index == self.GW_MISSING_AT:
                self.answers.add(
                    f"POS-GW-{code}",
                    relation,
                    "ONLY_IN_A",
                    pos_ref,
                    None,
                    "Đơn quẹt thẻ nhưng cổng không có giao dịch",
                )
                continue
            if special and pos_line == 2:
                # Đơn đầu tiên bị cài trùng mã (khác số tiền) ở bước làm sạch: chưa xử lý thì đơn
                # là "dữ liệu chưa sạch", còn giao dịch của nó tạm là "chỉ có ở B" (bộ mẫu: đơn
                # đầu tiên trả chuyển khoản nên ca này nằm ở sao kê, xem build_bank).
                line = emit(txn, code, moment, total)
                self.answers.add(
                    f"POS-GW-{code}", relation, "NEEDS_CLEANING", pos_ref, None,
                    "Đơn còn lỗi trùng mã ở bước làm sạch",
                )
                self.answers.add(
                    f"POS-GW-{code}-TIEN", relation, "ONLY_IN_B", None,
                    Ref(gateway_file, "", line), "Tiền của đơn còn lỗi trùng mã",
                )
                continue
            kind, note, shown_code, charged = "MATCHED", "", code, total
            if special and index == self.GW_SHORT_PAID_AT:
                kind, charged = "AMOUNT_MISMATCH", total - 20_000
                note = "Cổng thu ít hơn đơn 20.000đ"
            elif special and index == self.GW_NO_CODE_AT:
                note, shown_code = "Giao dịch không ghi mã đơn; khớp theo số tiền và ngày", ""
            elif special and index == self.GW_TYPO_AT:
                note, shown_code = "Mã đơn gõ sai; khớp theo số tiền và ngày", code[:-1] + "X"
            line = emit(txn, shown_code, moment, charged)
            self.answers.add(
                f"POS-GW-{code}", relation, kind, pos_ref, Ref(gateway_file, "", line), note
            )
            if special and index == self.GW_CHARGED_TWICE_AT:
                again = emit(f"GD{int(txn[2:]) + 7}", code, moment + dt.timedelta(minutes=1), total)
                self.answers.add(
                    f"POS-GW-{code}-LAN-2",
                    relation,
                    "DUPLICATE",
                    pos_ref,
                    Ref(gateway_file, "", again),
                    "Khách bị trừ tiền hai lần",
                )
        if special:
            # Giao dịch có mã đơn không tồn tại trong phần mềm bán hàng → ONLY_IN_B. Mã nằm ngoài
            # dải mã đơn của kỳ (bộ mẫu: HD000950), ngày thứ 5 của kỳ.
            stray_code = f"HD{self.code_start + max(849, self.pos_count + 629):06d}"
            stray_time = dt.datetime.combine(
                self.period_start + dt.timedelta(days=4), dt.time(14, 20)
            )
            stray = emit("GD9000000001", stray_code, stray_time, 780_000)
            self.answers.add(
                f"GW-ONLY-{stray_code}",
                relation,
                "ONLY_IN_B",
                None,
                Ref(gateway_file, "", stray),
                "Giao dịch không có đơn trong phần mềm bán hàng",
            )
        self._gateway_batches = batches
        return rows

    # ---------- sao kê ngân hàng ----------
    def _set_pos(
        self,
        transfers: list[tuple[int, dt.date, int, str, str]],
        position: int,
        customer: str | None = None,
        day: dt.date | None = None,
        total: int | None = None,
    ) -> None:
        """Sửa một đơn chuyển khoản đã sinh (không dùng số ngẫu nhiên) để cài ca đặc biệt."""
        line, old_day, old_total, code, old_customer = transfers[position]
        row = self._pos_rows[line - 2]
        if customer is not None:
            row[2] = customer
        if day is not None:
            row[1] = day.strftime("%d/%m/%Y") + row[1][10:]
        if total is not None:
            row[4] = str(total)
        transfers[position] = (
            line,
            day or old_day,
            total or old_total,
            code,
            customer or old_customer,
        )

    def build_bank(self) -> None:
        """Dòng sao kê cho tiền về của cửa hàng, cổng và sàn; đáp án ghi vào self.links."""
        pos_file, gateway_file = self.files["pos"], self.files["gateway"]
        platform_file, bank_file = self.files["platform"], self.files["bank"]
        rel_pos = "cua-hang↔sao-ke" + self.suffix
        rel_gw = "cong-thanh-toan↔sao-ke" + self.suffix
        rel_san = "san-tmdt↔sao-ke" + self.suffix

        def main_ref() -> Ref:
            return Ref(bank_file, "TK chinh", 0)

        # Chuyển khoản của khách cho đơn cửa hàng: thường 1:1, có cài sẵn ca lệch tiền và ca thiếu.
        transfers = list(self._pos_transfer)
        groups: dict[str, list[int]] = {}
        if self.special_cases:
            missing = transfers.pop(5)  # đơn chuyển khoản không thấy tiền về
            self.links.append(
                Link(
                    f"POS-BANK-{missing[3]}",
                    rel_pos,
                    "ONLY_IN_A",
                    Ref(pos_file, "", missing[0]),
                    missing[1],
                    None,
                    "Không có giao dịch tương ứng",
                )
            )
            # Đơn dùng cho ca đặc biệt: sớm trong kỳ (tiền về trong kỳ 1), có tên khách; không
            # dùng dòng 2 (HD000101, bị cài trùng mã ở bước làm sạch) và dòng 12 (bị chép trùng).
            latest = self.period_start + dt.timedelta(days=8)
            picks = [
                position
                for position, (line, day, _total, _code, customer) in enumerate(transfers)
                if day <= latest and position != 7 and line not in (2, 12)
                and customer != "Khách lẻ"
            ]
            groups = {
                "name": picks[0:1],
                "ambiguous": picks[1:3],
                "multi": picks[3:5],
                "subset": picks[5:7],
            }
        special = {position for positions in groups.values() for position in positions}
        for position, (line, day, total, code, customer) in enumerate(transfers):
            # Luôn rút số ngẫu nhiên để các dòng còn lại không đổi khi thêm ca đặc biệt.
            shift = self.rng.choice([0, 0, 1])
            if position in special:
                continue
            paid = total - 50_000 if self.special_cases and position == 7 else total
            who = unaccent_upper(customer) if customer != "Khách lẻ" else ""
            style = position % 3
            content = (
                f"CK {code} {who}".strip()
                if style == 0
                else f"{who} chuyen tien don {code.lower()}".strip()
                if style == 1
                else f"TT DON HANG {code}"
            )
            item = BankLine(day + dt.timedelta(days=shift), paid, 0, content, main_ref())
            self.bank_main.append(item)
            if self.special_cases and line == 2:
                # HD000101 bị cài trùng mã (khác số tiền) ở bước làm sạch: chưa xử lý thì đơn là
                # "dữ liệu chưa sạch", còn tiền của nó tạm là "chỉ có ở B".
                self.links.append(
                    Link(f"POS-BANK-{code}", rel_pos, "NEEDS_CLEANING", Ref(pos_file, "", line),
                         day, None, "Đơn còn lỗi trùng mã ở bước làm sạch")
                )
                self.links.append(
                    Link(f"POS-BANK-{code}-TIEN", rel_pos, "ONLY_IN_B", None, None, item,
                         "Tiền của đơn còn lỗi trùng mã")
                )
                continue
            kind = "AMOUNT_MISMATCH" if paid != total else "MATCHED"
            self.links.append(
                Link(f"POS-BANK-{code}", rel_pos, kind, Ref(pos_file, "", line), day, item)
            )
        if self.special_cases:
            self._special_transfers(transfers, groups, rel_pos, main_ref)

        # Cổng thanh toán trả tiền gộp từng đợt: nhiều giao dịch ↔ một dòng sao kê.
        for batch, items in sorted(self._gateway_batches.items()):
            day = dt.datetime.strptime(batch[3:], "%y%m%d").date()
            item = BankLine(
                day, sum(net for _, net, _ in items), 0, f"CONG TT CHUYEN TIEN {batch}", main_ref()
            )
            self.bank_main.append(item)
            kind = "MANY_TO_ONE" if len(items) > 1 else "MATCHED"
            for gateway_line, _, txn_day in items:
                self.links.append(
                    Link(
                        f"GW-BANK-{batch}",
                        rel_gw,
                        kind,
                        Ref(gateway_file, "", gateway_line),
                        txn_day,
                        item,
                    )
                )
        # Sàn TMĐT trả tiền gộp theo ngày vào tài khoản riêng.
        for day, settled in sorted(self._platform_settled.items()):
            item = BankLine(
                day + dt.timedelta(days=2),
                sum(net for _, net in settled),
                0,
                f"SAN TMDT THANH TOAN DOANH THU NGAY {day:%d/%m/%Y}",
                Ref(bank_file, "TK san", 0),
            )
            self.bank_platform.append(item)
            kind = "MANY_TO_ONE" if len(settled) > 1 else "MATCHED"
            for platform_line, _ in settled:
                self.links.append(
                    Link(
                        f"SAN-BANK-{day:%y%m%d}",
                        rel_san,
                        kind,
                        Ref(platform_file, "Đơn hàng", platform_line),
                        day,
                        item,
                    )
                )
        if not self.special_cases:
            return
        # Giao dịch không liên quan đơn hàng: tiền ra (phí, lương) ngoài phạm vi; tiền vào lạ.
        month = self.period_start.month
        last_month = 12 if month == 1 else month - 1
        for content, debit, credit in [
            (f"PHI QUAN LY TAI KHOAN T{month}", 22_000, 0),
            (f"CHI LUONG NHAN VIEN T{last_month}", 18_500_000, 0),
            ("NOP TIEN MAT VAO TK", 0, 5_000_000),
        ]:
            item = BankLine(
                self.period_start + dt.timedelta(days=self.rng.randrange(self.period_days)),
                credit,
                debit,
                content,
                main_ref(),
            )
            self.bank_main.append(item)
            self.links.append(
                Link(
                    f"BANK-ONLY-{content[:12]}",
                    rel_pos,
                    "OUT_OF_SCOPE" if debit else "ONLY_IN_B",
                    None,
                    None,
                    item,
                    "Tiền ra, không thuộc đối soát bán hàng"
                    if debit
                    else "Không liên quan đơn hàng",
                )
            )

    def _special_transfers(
        self,
        transfers: list[tuple[int, dt.date, int, str, str]],
        groups: dict[str, list[int]],
        relation: str,
        main_ref: Callable[[], Ref],
    ) -> None:
        """Ca khó của Giai đoạn 5: ghép theo tên, mơ hồ, một lần chuyển cho nhiều đơn."""
        pos_file = self.files["pos"]

        def link(position: int, kind: str, item: BankLine, note: str) -> None:
            line, day, _total, code, _customer = transfers[position]
            self.links.append(
                Link(f"POS-BANK-{code}", relation, kind, Ref(pos_file, "", line), day, item, note)
            )

        # Nội dung không có mã, chỉ có "anh Hoàng": ghép được nhờ tên "Lê Minh Hoàng".
        (position,) = groups["name"]
        self._set_pos(transfers, position, customer="Lê Minh Hoàng")
        _line, day, total, _code, _customer = transfers[position]
        item = BankLine(day, total, 0, "ANH HOANG CK TIEN HANG", main_ref())
        self.bank_main.append(item)
        link(position, "MATCHED", item, "Không có mã; ghép theo tên Hoàng, số tiền, ngày")

        # Hai khách "Minh Hoàng" cùng ngày, cùng số tiền; chỉ một dòng "chú Hoàng": không tự chọn.
        first, second = groups["ambiguous"]
        self._set_pos(transfers, first, customer="Phạm Minh Hoàng")
        _line, day, total, _code, _customer = transfers[first]
        self._set_pos(transfers, second, customer="Vũ Minh Hoàng", day=day, total=total)
        item = BankLine(day, total, 0, "CHU HOANG CHUYEN TIEN", main_ref())
        self.bank_main.append(item)
        for position in (first, second):
            link(position, "AMBIGUOUS", item, "Hai khách Minh Hoàng cùng ngày, cùng số tiền")

        # Một lần chuyển khoản cho hai đơn: nội dung ghi cả hai mã.
        first, second = groups["multi"]
        a, b = transfers[first], transfers[second]
        item = BankLine(max(a[1], b[1]), a[2] + b[2], 0, f"CK {a[3]} {b[3]}", main_ref())
        self.bank_main.append(item)
        for position in (first, second):
            link(position, "MANY_TO_ONE", item, "Một lần chuyển cho hai đơn, nội dung ghi hai mã")

        # Một lần chuyển cho hai đơn, không ghi mã: chỉ ghép được theo tổng tiền. Khách trả gộp
        # hai đơn mua cùng ngày (trong khung ngày của vòng khớp nhóm).
        first, second = groups["subset"]
        self._set_pos(transfers, second, day=transfers[first][1])
        a, b = transfers[first], transfers[second]
        item = BankLine(max(a[1], b[1]), a[2] + b[2], 0, "THANH TOAN TIEN HANG", main_ref())
        self.bank_main.append(item)
        for position in (first, second):
            link(position, "MANY_TO_ONE", item, "Một lần chuyển cho hai đơn, không ghi mã")

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
        last_day = self.period_start + dt.timedelta(days=self.period_days - 1)
        sheet.write(1, 0, f"Từ {self.period_start:%d/%m/%Y} đến {last_day:%d/%m/%Y}")
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

    def write_bank(self, first_day: dt.date, last_day: dt.date) -> bytes:
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
            sheet.write(2, 0, f"Kỳ sao kê: {first_day:%d/%m/%Y} - {last_day:%d/%m/%Y}")
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

    def build_sources(self) -> dict[str, bytes]:
        """Sinh và ghi tệp đơn sàn, đơn cửa hàng, giao dịch cổng; sao kê ghi sau khi tách kỳ."""
        platform_rows = self.build_platform()
        pos_rows = self.build_pos()
        gateway_rows = self.build_gateway()
        self.build_bank()  # có thể sửa vài đơn cửa hàng để cài ca đặc biệt, nên chạy trước khi ghi
        return {
            self.files["platform"]: self.write_platform(platform_rows),
            self.files["pos"]: pos_csv(
                pos_rows,
                injected_errors(
                    pos_rows, self.period_start, self.code_start + max(800, self.pos_count + 580)
                ),
            )
            if self.special_cases
            else plain_pos_csv(pos_rows),
            self.files["gateway"]: csv_bytes(
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
        }


def build_all() -> dict[str, bytes]:
    """Sinh bộ mẫu hai kỳ và đáp án.

    Kỳ 1 có mọi ca cài sẵn. Sao kê kỳ 1 cắt ở BANK1_CUTOFF: tiền về sau ngày đó (đơn cuối kỳ,
    đợt chuyển của cổng, doanh thu sàn trả sau 2 ngày) nằm trong sao kê kỳ 2. Đơn kỳ 1 có tiền
    về muộn là "chờ tiền về" ở kỳ 1 và được ghép ở kỳ 2.
    """
    first = SalesFixtureBuilder()
    second = SalesFixtureBuilder(
        seed=SEED + 2,
        platform_orders=20,
        pos_orders=25,
        period_start=PERIOD2_START,
        period_days=PERIOD2_DAYS,
        code_start=501,
        files=FILES_PERIOD2,
        special_cases=False,
        relation_suffix=KY2,
    )
    files = {**first.build_sources(), **second.build_sources()}

    # Tách sao kê: dòng sau ngày cắt chuyển sang tệp kỳ 2.
    for attribute in ("bank_main", "bank_platform"):
        lines: list[BankLine] = getattr(first, attribute)
        late = [item for item in lines if item.day > BANK1_CUTOFF]
        setattr(first, attribute, [item for item in lines if item.day <= BANK1_CUTOFF])
        for item in late:
            item.ref.file = FILES_PERIOD2["bank"]
        getattr(second, attribute).extend(late)
    bank2_end = max(item.day for item in second.bank_main + second.bank_platform)
    files[BANK_FILE] = first.write_bank(PERIOD_START, BANK1_CUTOFF)
    files[FILES_PERIOD2["bank"]] = second.write_bank(PERIOD2_START, bank2_end)

    answers = AnswerKey(first.answers.rows + second.answers.rows)
    for link in first.links:
        resolve_period1_link(answers, link, bank2_end)
    for link in second.links:
        assert link.item is not None
        answers.add(link.case, link.relation, link.kind, link.left, link.item.ref, link.note)
    files[ANSWER_FILE] = csv_bytes(
        list(answers.rows[0]), [list(row.values()) for row in answers.rows]
    )
    return files


def resolve_period1_link(answers: AnswerKey, link: Link, bank2_end: dt.date) -> None:
    """Đáp án cho một dòng kỳ 1, xét tiền có về trong sao kê kỳ 1 hay không.

    Dòng bên A chưa có tiền về mà còn trong khung chờ (hạn = ngày + 3 ngày làm việc, sau ngày
    cuối sao kê) là PENDING_SETTLEMENT; sang kỳ 2 thì được ghép hoặc, nếu quá hạn, thành thiếu.
    """
    if link.kind == "NEEDS_CLEANING":
        answers.add(link.case, link.relation, link.kind, link.left, None, link.note)
        return
    moved = link.item is not None and link.item.day > BANK1_CUTOFF
    if link.item is not None and not moved:
        answers.add(link.case, link.relation, link.kind, link.left, link.item.ref, link.note)
        return
    if link.left is None:  # dòng chỉ có ở sao kê, nằm ở kỳ 2
        assert link.item is not None
        answers.add(link.case, link.relation + KY2, link.kind, None, link.item.ref, link.note)
        return
    assert link.left_day is not None
    deadline = add_business_days(link.left_day, SETTLEMENT_BUSINESS_DAYS)
    if deadline <= BANK1_CUTOFF:
        answers.add(link.case, link.relation, "ONLY_IN_A", link.left, None, link.note)
        return
    answers.add(
        link.case, link.relation, "PENDING_SETTLEMENT", link.left, None, "Chờ tiền về kỳ sau"
    )
    if moved:
        assert link.item is not None
        answers.add(link.case, link.relation + KY2, link.kind, link.left, link.item.ref, link.note)
    elif deadline <= bank2_end:
        answers.add(link.case, link.relation + KY2, "ONLY_IN_A", link.left, None, "Quá hạn chờ")
    else:
        answers.add(
            link.case, link.relation + KY2, "PENDING_SETTLEMENT", link.left, None, link.note
        )


def csv_bytes(
    header: list[str], rows: list[list[str]], delimiter: str = ",", bom: bool = False
) -> bytes:
    text = io.StringIO()
    writer = csv.writer(text, delimiter=delimiter, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    return ("﻿" if bom else "").encode() + text.getvalue().encode("utf-8")


def injected_errors(rows: list[list[str]], start: dt.date, code_base: int) -> list[list[str]]:
    """Lỗi cài sẵn ở cuối tệp đơn hàng cửa hàng; đáp án cho bước làm sạch của bộ mẫu nằm ở
    loi-cai-san.csv. Toàn bộ là đơn trả tiền mặt nên không ảnh hưởng đáp án đối soát. Ngày tính
    theo ngày đầu kỳ, mã mới nằm ngoài dải mã đơn của kỳ (bộ mẫu: HD000901–HD000905)."""

    def on(days: int) -> dt.date:
        return start + dt.timedelta(days=days)

    def code(offset: int) -> str:
        return f"HD{code_base + offset:06d}"

    odd = on(4)  # ngày tháng không có số 0 ở đầu, giờ một chữ số
    strange = on(8)  # ngày viết bằng chữ
    return [
        ["", f"{on(5):%d/%m/%Y} 10:15", "Nguyễn Văn Khoa", "0912000111", "450000", "Tiền mặt"],
        [code(0), f"{on(6):%d/%m/%Y} 11:00", "Lê Thị Mai", "0913000222", "1tr2", "Tiền mặt"],
        [code(1), f"{on(6):%d/%m/%Y} 11:30", "Phạm Văn Tú", "0914000333", "khoảng 500k",
         "Tiền mặt"],
        [code(2), f"{odd.day}/{odd.month:02d}/{odd.year} 9:05", "Võ Thị Lan", "84915000444",
         "320000", "Tiền mặt"],  # đầu 84
        [code(3), f"{on(7):%d/%m/%Y} 15:20", "  Trần   Thị  Bình ", "0916000555", "275000",
         "Tiền mặt"],  # khoảng trắng thừa
        [rows[0][0], f"{on(0):%d/%m/%Y} 09:00", "Nguyễn Văn An", "0917000666", "999000",
         "Tiền mặt"],  # trùng mã đơn đầu tiên, khác số tiền
        [code(4), f"ngày {strange.day} tháng {strange.month}", "Đỗ Văn Hùng", "0918000777",
         "150000", "Tiền mặt"],  # ngày lạ
    ]


def pos_csv(rows: list[list[str]], errors: list[list[str]]) -> bytes:
    """CSV phần mềm bán hàng: có BOM, một dòng trùng y hệt và một dòng trống cài sẵn.

    Dòng cài thêm được chèn ở cuối để không làm lệch số dòng của các đơn đã ghi trong đáp án.
    """
    extra = [
        ["", "", "", "", "", ""],  # bộ mẫu dòng 222: trống (đứng trước để không bị coi là đuôi tệp)
        rows[10],  # bộ mẫu dòng 223: trùng y hệt dòng 12
        *errors,  # bộ mẫu dòng 224–230: lỗi cài sẵn cho bước làm sạch (xem loi-cai-san.csv)
    ]
    return csv_bytes(
        ["MaHD", "NgayBan", "KhachHang", "DienThoai", "TongTien", "ThanhToan"],
        rows + extra,
        bom=True,
    )


def plain_pos_csv(rows: list[list[str]]) -> bytes:
    """CSV phần mềm bán hàng kỳ 2: cùng định dạng, không cài lỗi."""
    return csv_bytes(
        ["MaHD", "NgayBan", "KhachHang", "DienThoai", "TongTien", "ThanhToan"], rows, bom=True
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
    for name, content in build_all().items():
        (OUTPUT_DIR / name).write_bytes(content)
        print(f"{name}: {len(content):,} byte")


if __name__ == "__main__":
    main()
