"""Che bớt giá trị mẫu trước khi gửi cho Gemini (quyết định 2026-11-20).

Mục tiêu: giữ hình dạng giá trị để AI đoán được nghĩa cột (đây là số điện thoại, đây là
tên người…) nhưng không lộ dữ liệu cá nhân. Đây là che bớt để giảm lộ dữ liệu, không phải
ẩn danh tuyệt đối. Mã, ngày, số tiền gửi nguyên vì không phải thông tin cá nhân.
"""

import re
import unicodedata

from studio.profiling import ObservedKind

# Từ nghiệp vụ hay gặp trong nội dung chuyển khoản; giữ nguyên để AI hiểu ngữ cảnh.
# Không đưa vào các từ cũng là tên người phổ biến (ví dụ "thanh" trong Trần Thanh Châu).
KEEP_WORDS = {
    "ck", "tt", "dh", "hd", "chuyen", "tien", "khoan", "don", "hang", "toan", "ngay",
    "dot", "phi", "san", "tmdt", "cong", "doanh", "thu", "nop", "rut", "luong", "chi", "tra",
    "mua", "ban", "the", "qr", "ma", "so", "tk", "tai", "quan", "ly", "nhan", "gui", "vao",
}

_PHONE = re.compile(r"^(\+?84|0)\d{8,10}$")
_EMAIL = re.compile(r"^([^@\s])[^@\s]*@([^@.\s])[^@\s]*(\.[A-Za-z.]+)$")
_LONG_DIGITS = re.compile(r"\d{9,}")
# Mã nghiệp vụ, không phải dữ liệu cá nhân: chữ hoa và số (HD000115, DOT261002) hoặc
# tiền tố chữ ngắn + từ 4 chữ số (hd000192 viết thường trong nội dung chuyển khoản).
_BUSINESS_CODE = re.compile(
    r"^[A-Z0-9][A-Z0-9._/-]*\d[A-Z0-9._/-]*$|^[A-Za-z]{0,6}[-_]?\d{4,}[A-Za-z0-9]*$"
)


def _mask_digits(digits: str) -> str:
    """Giữ 2 số đầu và 2 số cuối (dãy dài từ 12 số như số tài khoản thì giữ 4 đầu, 4 cuối)."""
    keep = 4 if len(digits) >= 12 else 2
    return digits[:keep] + "x" * (len(digits) - 2 * keep) + digits[-keep:]


def _mask_word(word: str) -> str:
    return word[0] + "*" * min(3, max(1, len(word) - 1))


def _plain(word: str) -> str:
    """Bỏ dấu để so với danh sách từ nghiệp vụ."""
    text = unicodedata.normalize("NFD", word.replace("đ", "d").replace("Đ", "D"))
    return "".join(char for char in text if unicodedata.category(char) != "Mn").lower()


def _mask_token(token: str) -> str:
    if _BUSINESS_CODE.match(token) and not _LONG_DIGITS.fullmatch(token):
        return token
    if token.isdigit():
        return _mask_digits(token) if len(token) >= 9 else token
    if _plain(token) in KEEP_WORDS:
        return token
    return _mask_word(token)


def mask_text(value: str) -> str:
    """Che một chuỗi chữ tự do: tên người, nội dung chuyển khoản, tên đăng nhập…"""
    stripped = value.strip()
    compact = re.sub(r"[\s.-]", "", stripped)
    if _PHONE.match(compact):
        return _mask_digits(compact)
    email = _EMAIL.match(stripped)
    if email:
        return f"{email.group(1)}***@{email.group(2)}***{email.group(3)}"
    tokens = stripped.split()
    has_digits = any(char.isdigit() for char in stripped)
    looks_like_name = 2 <= len(tokens) <= 5 and not has_digits
    masked = []
    for index, token in enumerate(tokens):
        if looks_like_name and index == 0:
            masked.append(token)  # họ phổ biến (Nguyễn, Trần…) giữ lại để AI nhận ra là tên người
        else:
            masked.append(_mask_token(token))
    return " ".join(masked)


def mask_sample(value: str, kind: ObservedKind, distinct_count: int) -> str:
    """Che một giá trị mẫu theo dạng của cột.

    - Mã, ngày, số: gửi nguyên (riêng dãy số dài từ 9 chữ số như số tài khoản thì che giữa).
    - Điện thoại: giữ 2 số đầu, 2 số cuối.
    - Chữ: cột ít giá trị khác nhau (trạng thái, phương thức thanh toán) là danh mục, gửi nguyên;
      cột nhiều giá trị (tên, nội dung) thì che từng từ.
    """
    if kind == "PHONE":
        digits = re.sub(r"\D", "", value)
        return _mask_digits(digits) if len(digits) >= 6 else value
    if kind in ("NUMBER", "DATE"):
        return _LONG_DIGITS.sub(lambda match: _mask_digits(match.group()), value)
    if kind == "CODE":
        return value if _BUSINESS_CODE.match(value) else mask_text(value)
    if kind == "TEXT" and distinct_count <= 20:
        return value
    return mask_text(value)
