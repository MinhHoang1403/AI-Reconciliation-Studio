"""Bộ cột chuẩn của miền bán hàng (đơn hàng, thanh toán, sao kê ngân hàng).

Mỗi cột trong tệp của người dùng sẽ được ánh xạ về một cột chuẩn dưới đây (hoặc không
ánh xạ). Các bước sau (chuẩn hóa, đối soát) chỉ làm việc với cột chuẩn.
"""

from dataclasses import dataclass
from typing import Literal

# Kiểu giá trị của cột chuẩn; quyết định cách chuẩn hóa ở Giai đoạn 3.
type FieldType = Literal["IDENTIFIER", "MONEY", "DATE", "PHONE", "TEXT", "CATEGORY"]

# Loại bảng dữ liệu mà hệ thống có thể nhận ra.
type TableKind = Literal[
    "ORDERS_PLATFORM", "ORDERS_POS", "PAYMENT_GATEWAY", "BANK_STATEMENT", "UNKNOWN"
]

TABLE_KIND_LABELS: dict[str, str] = {
    "ORDERS_PLATFORM": "Đơn hàng sàn TMĐT",
    "ORDERS_POS": "Đơn hàng cửa hàng",
    "PAYMENT_GATEWAY": "Giao dịch cổng thanh toán",
    "BANK_STATEMENT": "Sao kê ngân hàng",
    "UNKNOWN": "Chưa rõ loại",
}


@dataclass(frozen=True)
class StandardField:
    key: str
    label: str  # tên tiếng Việt hiển thị cho người dùng
    type: FieldType
    meaning: str  # mô tả ngắn, gửi cho Gemini để hiểu nghĩa cột
    aliases: tuple[str, ...]  # các tên cột hay gặp (viết không dấu, chữ thường)


SALES_FIELDS: tuple[StandardField, ...] = (
    StandardField("order_id", "Mã đơn hàng", "IDENTIFIER",
                  "Mã định danh đơn hàng hoặc hóa đơn bán",
                  ("ma don hang", "ma don", "ma hoa don", "so hoa don", "order id", "order code",
                   "invoice", "ma dh", "so don")),
    StandardField("order_date", "Ngày đặt hàng", "DATE",
                  "Ngày hoặc thời điểm tạo đơn, ngày bán",
                  ("ngay dat hang", "ngay ban", "ngay tao don", "order date", "ngay don hang",
                   "thoi gian dat hang", "ngay hoa don")),
    StandardField("customer_name", "Tên khách hàng", "TEXT",
                  "Tên người mua hoặc khách hàng",
                  ("ten khach hang", "khach hang", "ten nguoi mua", "nguoi mua", "customer name",
                   "ho ten", "ten khach")),
    StandardField("customer_phone", "Điện thoại khách", "PHONE",
                  "Số điện thoại của khách hàng hoặc người nhận",
                  ("so dien thoai", "dien thoai", "so dien thoai nguoi nhan", "phone",
                   "so dt", "dien thoai khach hang")),
    StandardField("amount", "Số tiền", "MONEY",
                  "Tổng giá trị đơn hoặc số tiền của giao dịch, trước khi trừ phí",
                  ("so tien", "tong tien", "tong tien hang", "thanh tien", "gia tri", "amount",
                   "tong cong", "tong thanh toan")),
    StandardField("fee", "Phí", "MONEY",
                  "Phí sàn, phí cổng thanh toán hoặc phí giao dịch bị trừ",
                  ("phi", "phi san", "phi giao dich", "phi thanh toan", "fee", "phi dich vu")),
    StandardField("net_amount", "Thực nhận", "MONEY",
                  "Số tiền thực nhận sau khi trừ phí",
                  ("thuc nhan", "so tien thuc nhan", "tien thuc nhan", "net amount",
                   "so tien nhan duoc", "doanh thu thuan")),
    StandardField("payment_method", "Phương thức thanh toán", "CATEGORY",
                  "Hình thức khách trả tiền: tiền mặt, chuyển khoản, thẻ...",
                  ("thanh toan", "phuong thuc thanh toan", "hinh thuc thanh toan", "payment method",
                   "kenh thanh toan")),
    StandardField("status", "Trạng thái", "CATEGORY",
                  "Trạng thái đơn hàng hoặc giao dịch: hoàn thành, đã hủy...",
                  ("trang thai", "tinh trang", "status", "trang thai don hang")),
    StandardField("payment_id", "Mã giao dịch thanh toán", "IDENTIFIER",
                  "Mã giao dịch do cổng thanh toán hoặc ví điện tử cấp",
                  ("ma giao dich", "ma gd", "transaction id", "ma thanh toan", "so giao dich")),
    StandardField("payment_batch", "Mã đợt chuyển tiền", "IDENTIFIER",
                  "Mã đợt mà cổng thanh toán hoặc sàn gộp nhiều giao dịch rồi chuyển về tài khoản",
                  ("ma dot chuyen", "dot chuyen tien", "ma dot", "payout id", "ma doi soat",
                   "settlement id")),
    StandardField("transaction_date", "Ngày giao dịch", "DATE",
                  "Ngày hoặc thời điểm phát sinh giao dịch thanh toán hoặc ngân hàng",
                  ("ngay giao dich", "thoi gian", "thoi gian giao dich", "ngay gd",
                   "transaction date", "ngay hach toan", "ngay")),
    StandardField("bank_ref", "Số tham chiếu ngân hàng", "IDENTIFIER",
                  "Số tham chiếu hoặc mã bút toán của ngân hàng",
                  ("so tham chieu", "ma tham chieu", "so but toan", "reference", "ref no",
                   "so ct")),
    StandardField("debit", "Ghi nợ (tiền ra)", "MONEY",
                  "Số tiền đi ra khỏi tài khoản trên sao kê",
                  ("no", "ghi no", "so tien ghi no", "tien ra", "debit", "phat sinh no", "rut")),
    StandardField("credit", "Ghi có (tiền vào)", "MONEY",
                  "Số tiền đi vào tài khoản trên sao kê",
                  ("co", "ghi co", "so tien ghi co", "tien vao", "credit", "phat sinh co", "nop")),
    StandardField("balance", "Số dư", "MONEY",
                  "Số dư tài khoản sau giao dịch",
                  ("so du", "so du cuoi", "balance", "so du con lai")),
    StandardField("description", "Nội dung", "TEXT",
                  "Nội dung hoặc diễn giải giao dịch, thường chứa mã đơn và tên người chuyển",
                  ("noi dung", "dien giai", "mo ta", "description", "noi dung chuyen khoan",
                   "ghi chu giao dich", "chi tiet")),
)

FIELDS_BY_KEY: dict[str, StandardField] = {field.key: field for field in SALES_FIELDS}
