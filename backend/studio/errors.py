"""Stable, redacted errors shared by API, worker and domain functions."""

from typing import Any


class DomainError(Exception):
    def __init__(self, code: str, message_vi: str, status: int = 422, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.message_vi = message_vi
        self.status = status
        self.retryable = retryable
        # Receipt transport đã redact, chỉ dùng cho trace; không đưa vào error DTO công khai.
        self.provider_usage: dict[str, Any] | None = None
