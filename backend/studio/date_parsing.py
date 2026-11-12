"""Ngày theo quy tắc đã duyệt; lỗi cấu hình không phải lỗi từng dòng."""

import re
from datetime import UTC, date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from studio.errors import DomainError


@lru_cache(maxsize=128)
def date_format(value: str) -> str:
    """Chuẩn hóa nhãn ngày hiển thị tương đương, không đoán thứ tự ngày/tháng."""
    aliases = {"YYYY-MM-DD": "%Y-%m-%d", "DD/MM/YYYY": "%d/%m/%Y", "MM/DD/YYYY": "%m/%d/%Y"}
    result = aliases.get(value, value)
    directives = re.findall(r"%(.)", result)
    if (
        not {"Y", "m", "d"} <= set(directives)
        or any(c not in "YmdHMSfz%" for c in directives)
        or re.search(r"%(?![YmdHMSfz%])", result)
    ):
        raise DomainError(
            "DATE_FORMAT_INVALID",
            "Định dạng ngày phải có năm, tháng, ngày và mã chuyển đổi được hỗ trợ.",
        )
    try:
        sample = datetime(2026, 10, 23, 13, 24, 35, 123456, tzinfo=UTC)
        datetime.strptime(sample.strftime(result), result)
    except (ValueError, re.error) as exc:
        raise DomainError("DATE_FORMAT_INVALID", "Cấu hình định dạng ngày không hợp lệ.") from exc
    return result


@lru_cache(maxsize=128)
def date_zone(value: str) -> ZoneInfo:
    """Kiểm tra cả CSDL IANA và tên vùng; không thay timezone lỗi bằng UTC."""
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        if not {"UTC", "Asia/Ho_Chi_Minh"} <= available_timezones():
            raise DomainError(
                "TIMEZONE_DATABASE_UNAVAILABLE",
                "Môi trường thiếu dữ liệu múi giờ; liên hệ người vận hành.",
            ) from exc
        raise DomainError("TIMEZONE_INVALID", "Múi giờ không tồn tại trong dữ liệu IANA.") from exc


def source_date_operation(format_value: str) -> str:
    directives = set(re.findall(r"%(.)", date_format(format_value)))
    if not directives & set("HMSfz"):
        return "parse_calendar_date"
    if "z" in directives:
        return "parse_offset_timestamp"
    return "parse_date"


def parse_source_date(raw: str | None, format_value: str, operation: str) -> date | None:
    if source_date_operation(format_value) != operation:
        raise DomainError("DATE_FORMAT_INVALID", "Định dạng không khớp kiểu ngày hoặc thời điểm.")
    if raw in (None, ""):
        return None
    try:
        parsed = datetime.strptime(str(raw), date_format(format_value))
    except ValueError as exc:
        raise DomainError(
            "INVALID_DATE", "Giá trị ngày không khớp định dạng hoặc ngày không tồn tại."
        ) from exc
    return parsed.date() if operation == "parse_calendar_date" else parsed.astimezone(UTC)


def parse_date(raw: str | None, format_value: str, timezone: str) -> datetime | None:
    """Giữ ngày lịch trong vùng đã duyệt; kết quả timestamp UTC tương thích contract cũ.

    Timestamp có offset phải khớp vùng được duyệt. Giờ DST mơ hồ/không tồn tại
    bị từ chối; không tự chọn fold. Lỗi quy tắc được kiểm trước cả đầu vào rỗng.
    """
    fmt, zone = date_format(format_value), date_zone(timezone)
    if raw in (None, ""):
        return None
    try:
        parsed = datetime.strptime(str(raw), fmt)
    except ValueError as exc:
        raise DomainError(
            "INVALID_DATE", "Giá trị ngày không khớp định dạng hoặc ngày không tồn tại."
        ) from exc
    if parsed.tzinfo is not None:
        if parsed.utcoffset() != parsed.astimezone(zone).utcoffset():
            raise DomainError("DATE_OFFSET_MISMATCH", "Offset của thời điểm khác múi giờ đã duyệt.")
        return parsed.astimezone(UTC)
    earlier, later = parsed.replace(tzinfo=zone, fold=0), parsed.replace(tzinfo=zone, fold=1)
    if earlier.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != parsed:
        raise DomainError(
            "NONEXISTENT_LOCAL_TIME", "Thời điểm không tồn tại do đổi giờ; cần kiểm tra nguồn."
        )
    if earlier.utcoffset() != later.utcoffset():
        raise DomainError("AMBIGUOUS_LOCAL_TIME", "Thời điểm có hai offset do đổi giờ; cần làm rõ.")
    return earlier.astimezone(UTC)
