"""Sinh bộ dữ liệu kiểm mù cho đối soát: đơn hàng kênh B ↔ sao kê ngân hàng kênh B.

"Kiểm mù" nghĩa là bộ này được thiết kế độc lập với bộ mẫu `tests/fixtures/sales/` (khác tên
cột, khác dạng mã, khác dạng ngày và số tiền, khác cách ghi nội dung chuyển khoản) và quy tắc
của engine KHÔNG được chỉnh theo nó. Nó đo độ chính xác thật của engine trên dữ liệu lạ
(docs/DECISIONS.md 2026-11-23). Dữ liệu tổng hợp, không phải dữ liệu thật.

Mỗi đơn chuyển khoản có một "sự thật" ghi trong `dap-an.csv`: đơn này được trả bằng dòng sao
kê nào (hoặc không có tiền về). Chạy lại luôn ra cùng kết quả (hạt giống cố định):

    uv run --locked python tools/make_blind_fixtures.py
"""

import csv
import random
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "blind"
SEED = 20261123
START = date(2026, 11, 2)  # thứ Hai
DAYS = 21
ORDER_COUNT = 320

FAMILY = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ"]
MIDDLE = ["Văn", "Thị", "Minh", "Ngọc", "Thanh", "Quốc", "Hữu", "Thu", "Đức", "Kim"]
GIVEN = [
    "An", "Bình", "Châu", "Dũng", "Giang", "Hà", "Hải", "Hiếu", "Hòa", "Hùng", "Khoa", "Lan",
    "Linh", "Long", "Mai", "Nam", "Nga", "Nhung", "Phúc", "Quân", "Sơn", "Tâm", "Thảo", "Trang",
    "Tuấn", "Vy", "Yến",
]


@dataclass
class Order:
    row: int  # số dòng trong tệp (dòng 1 là tiêu đề)
    code: str
    created: datetime
    buyer: str
    total: int
    payment: str  # "Bank transfer", "COD"
    state: str  # "Completed", "Cancelled"


@dataclass
class BankLine:
    day: date
    reference: str
    text: str
    debit: int | None
    credit: int | None
    orders: list[Order]  # sự thật: các đơn mà dòng này trả tiền (rỗng nếu không liên quan)
    truth: str  # loại quan hệ thật: PAIR, GROUP, FEE, NONE


def plain_upper(name: str) -> str:
    """Tên như ngân hàng in: bỏ dấu, viết hoa."""
    text = unicodedata.normalize("NFD", name.replace("đ", "d").replace("Đ", "D"))
    return "".join(char for char in text if unicodedata.category(char) != "Mn").upper()


def money_en(value: int) -> str:
    return f"{value:,}"


def money_vn(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def build() -> tuple[list[Order], list[BankLine]]:
    rng = random.Random(SEED)
    orders: list[Order] = []
    for index in range(ORDER_COUNT):
        created = datetime.combine(
            START + timedelta(days=rng.randrange(DAYS)), datetime.min.time()
        ) + timedelta(minutes=rng.randrange(8 * 60, 22 * 60))
        payment = rng.choices(["Bank transfer", "COD"], weights=[8, 2])[0]
        state = "Cancelled" if rng.random() < 0.05 else "Completed"
        orders.append(
            Order(
                row=0,
                code=f"SO-26-{4100 + index * 7:06d}",
                created=created,
                buyer=f"{rng.choice(FAMILY)} {rng.choice(MIDDLE)} {rng.choice(GIVEN)}",
                total=rng.randrange(9, 900) * 5_000,
                payment=payment,
                state=state,
            )
        )
    orders.sort(key=lambda order: (order.created, order.code))
    for position, order in enumerate(orders):
        order.row = position + 2

    lines: list[BankLine] = []
    paid = [o for o in orders if o.payment == "Bank transfer" and o.state == "Completed"]
    rng.shuffle(paid)
    used: set[str] = set()

    def arrive(order: Order) -> date:
        return order.created.date() + timedelta(days=rng.choice([0, 0, 0, 1, 1, 2]))

    def name_of(order: Order) -> str:
        return plain_upper(order.buyer)

    # Một lần chuyển trả hai đơn của cùng khách trong cùng ngày (tạo cặp đơn liền nhau).
    pairs = 0
    for order in paid:
        if pairs >= 8 or order.code in used:
            continue
        partner = next(
            (
                other for other in paid
                if other.code not in used and other is not order
                and other.created.date() == order.created.date()
            ),
            None,
        )
        if partner is None:
            continue
        used.update({order.code, partner.code})
        pairs += 1
        lines.append(
            BankLine(
                arrive(order), "", f"TT {order.code} {partner.code} {name_of(order)}", None,
                order.total + partner.total, [order, partner], "GROUP",
            )
        )

    for order in paid:
        if order.code in used:
            continue
        used.add(order.code)
        roll = rng.random()
        day = arrive(order)
        compact = order.code.replace("-", "")
        if roll < 0.06:
            continue  # khách chưa chuyển tiền: không có dòng sao kê (đơn chỉ có ở bên đơn hàng)
        if roll < 0.40:
            text = f"{name_of(order)} chuyen khoan {order.code}"
        elif roll < 0.55:
            text = f"thanh toan don hang {order.code.lower()}"
        elif roll < 0.65:
            text = f"MBVCB.{rng.randrange(10**9)}.{compact}.{name_of(order)}"  # mã viết dính
        elif roll < 0.78:
            text = f"{name_of(order)} CHUYEN TIEN"  # không ghi mã, chỉ có tên
        elif roll < 0.86:
            # Ngân hàng của khách trừ phí chuyển: tiền về thiếu 11.000đ so với đơn.
            lines.append(
                BankLine(day, "", f"{name_of(order)} ck {order.code}", None, order.total - 11_000,
                         [order], "FEE")
            )
            continue
        else:
            text = f"IBFT {order.code} {name_of(order).split()[-1]}"
        lines.append(BankLine(day, "", text, None, order.total, [order], "PAIR"))

    # Dòng không liên quan bán hàng: lãi tiền gửi, tiền vào không rõ, tiền ra.
    for _ in range(10):
        day = START + timedelta(days=rng.randrange(DAYS))
        lines.append(BankLine(day, "", f"KH {rng.randrange(10**6)} NOP TIEN MAT", None,
                              rng.randrange(20, 400) * 5_000, [], "NONE"))
        lines.append(BankLine(day, "", "PHI QUAN LY TAI KHOAN", rng.randrange(1, 9) * 11_000,
                              None, [], "NONE"))
    lines.append(BankLine(START + timedelta(days=DAYS - 1), "", "LAI TIEN GUI THANG 11", None,
                          38_412, [], "NONE"))

    lines.sort(key=lambda line: (line.day, line.text))
    for index, line in enumerate(lines):
        line.reference = f"FT26{index + 1:07d}"
    return orders, lines


def write() -> None:
    orders, lines = build()
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "don-hang-kenh-b.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Order No", "Created At", "Buyer", "Total (VND)", "Payment", "State"])
        for order in orders:
            writer.writerow([
                order.code,
                order.created.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
                order.buyer,
                money_en(order.total),
                order.payment,
                order.state,
            ])
    with (OUT / "sao-ke-kenh-b.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Ngày GD", "Số tham chiếu", "Diễn giải", "Ghi nợ", "Ghi có"])
        for line in lines:
            writer.writerow([
                line.day.strftime("%d/%m/%Y"),
                line.reference,
                line.text,
                money_vn(line.debit) if line.debit else "",
                money_vn(line.credit) if line.credit else "",
            ])
    # Đáp án: mỗi liên kết thật giữa một đơn và một dòng sao kê (dòng sao kê tính từ 2).
    with (OUT / "dap-an.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["order_row", "order_code", "bank_row", "truth"])
        for position, line in enumerate(lines):
            for order in line.orders:
                writer.writerow([order.row, order.code, position + 2, line.truth])
    print(f"Đã ghi {len(orders)} đơn, {len(lines)} dòng sao kê vào {OUT}")


if __name__ == "__main__":
    write()
