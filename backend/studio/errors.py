"""Stable, redacted errors shared by API, worker and domain functions."""

from typing import Any

GEMINI_RETRYABLE_ERRORS = {"GEMINI_UNAVAILABLE", "GEMINI_RATE_LIMITED"}


def request_failure_message(code: str) -> str:
    """Safe terminal response; never persist provider bodies, paths or exception text."""
    return {
        "INSUFFICIENT_EVIDENCE": (
            "Chưa có đủ bằng chứng cho yêu cầu này. Hãy kiểm tra nguồn đã chọn;"
            " nếu hỏi kết quả đối soát, cần một kết quả đã xác minh."
        ),
        "INPUT_AMBIGUOUS": (
            "Chưa xác định được nguồn hoặc yêu cầu cụ thể. "
            "Hãy chọn nguồn dữ liệu và bổ sung thông tin."
        ),
        "QUERY_FIELD_INVALID": (
            "Trường cần tra cứu không có trong nguồn đang chọn. Hãy kiểm tra lại nguồn và tên cột."
        ),
        "QUERY_METRIC_AMBIGUOUS": (
            "Có nhiều chỉ tiêu tiền phù hợp. Hãy chọn chỉ tiêu cần xem trước khi tiếp tục."
        ),
        "AI_INVALID_SOURCE": (
            "AI chưa xác định đúng nguồn dữ liệu. Chưa có thao tác nghiệp vụ nà"
            "o được phê duyệt từ kết quả này."
        ),
        "STALE_CONTEXT": (
            "Lựa chọn hoặc nguồn đã thay đổi trong lúc xử lý. Hãy kiểm tra ngữ "
            "cảnh hiện tại trước khi gửi yêu cầu mới."
        ),
        "AUTH_REQUIRED": (
            "Phiên truy cập chưa hợp lệ. Hãy kết nối lại để tiếp tục; dữ liệu đã lưu được giữ."
        ),
        "FORBIDDEN": (
            "Bạn không có quyền thực hiện thao tác này. Hãy liên hệ chủ không gian làm việc."
        ),
        "RESOURCE_NOT_FOUND": (
            "Không tìm thấy nguồn hoặc bạn không còn quyền truy cập. Hãy kiểm t"
            "ra dự án và ngữ cảnh."
        ),
        "LOCAL_DEMO_NOT_VERIFIED": (
            "Kết nối local cần được kiểm tra lại sau khi dịch vụ khởi động. Hãy"
            " dùng quy trình khởi động của ứng dụng."
        ),
        "GEMINI_RATE_LIMITED": (
            "Dịch vụ AI đang giới hạn yêu cầu. Dữ liệu đã lưu vẫn xem được; khô"
            "ng tự gửi lại yêu cầu này."
        ),
        "QWEN_RATE_LIMITED": "Dịch vụ AI đang giới hạn yêu cầu. Không tự gửi lại yêu cầu này.",
        "AI_DELIVERY_UNKNOWN": (
            "Chưa xác định dịch vụ AI đã nhận yêu cầu hay chưa. Không tự gửi lạ"
            "i để tránh xử lý trùng; hãy kiểm tra trạng thái hội thoại."
        ),
        "GEMINI_UNAVAILABLE": (
            "Gemini hiện chưa thể xử lý yêu cầu. Nội dung và dữ liệu của bạn vẫn được giữ nguyên."
        ),
        "OLLAMA_UNAVAILABLE": "Qwen hiện chưa thể xử lý yêu cầu. Nội dung và dữ liệu vẫn được giữ.",
        "OLLAMA_MODEL_MISSING": "Model Qwen được chọn chưa có trên máy.",
        "OLLAMA_NOT_CONFIGURED": "Model Qwen được chọn chưa được cấu hình.",
        "QWEN_UNAVAILABLE": (
            "Dịch vụ AI chưa phản hồi. Hãy xem dữ liệu đã lưu hoặc sử dụng thiết lập thủ công."
        ),
        "WORKER_INTERNAL_ERROR": (
            "Xử lý nền gặp lỗi. Các kết quả đã lưu được giữ; hãy cập nhật hội t"
            "hoại và liên hệ hỗ trợ nếu lỗi còn lặp lại."
        ),
        "JOB_RETRY_EXHAUSTED": (
            "Công việc đã dừng sau các lần phục hồi không thành công. Hãy cập n"
            "hật hội thoại và kiểm tra kết quả đã lưu trước khi tạo yêu cầu mới"
            "."
        ),
    }.get(
        code,
        (
            "Yêu cầu chưa hoàn tất. Các kết quả đã lưu được giữ; hãy xem thông "
            "báo trên công việc hoặc dùng thiết lập thủ công."
        ),
    )


class DomainError(Exception):
    def __init__(self, code: str, message_vi: str, status: int = 422, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.message_vi = message_vi
        self.status = status
        self.retryable = retryable
        self.retry_after_seconds: float | None = None
        # Receipt transport đã redact, chỉ dùng cho trace; không đưa vào error DTO công khai.
        self.provider_usage: dict[str, Any] | None = None
