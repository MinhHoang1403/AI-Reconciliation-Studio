"""Ghi dấu vết (trace) các lần gọi AI vào Langfuse.

Chỉ bật khi `.env` có đủ LANGFUSE_PUBLIC_KEY và LANGFUSE_SECRET_KEY. Dữ liệu gửi lên
Langfuse là gói đã che (giống hệt gói gửi Gemini), không bao giờ là dữ liệu gốc.
Lỗi của Langfuse không được làm hỏng tính năng chính: ghi không được thì bỏ qua.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Protocol

from studio.config import settings

logger = logging.getLogger(__name__)


class Observation(Protocol):
    def update(self, **fields: Any) -> Any: ...


class _NoTrace:
    """Thay cho Langfuse khi chưa cấu hình: nhận lệnh cập nhật nhưng không làm gì."""

    def update(self, **fields: Any) -> None:
        return None


def langfuse_configured() -> bool:
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key.get_secret_value())


@lru_cache(maxsize=1)
def _client() -> Any:
    from langfuse import Langfuse

    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_base_url,
        environment="local",
        release=settings.studio_revision,
    )


@contextmanager
def ai_generation(
    name: str, model: str, payload: Any, metadata: dict[str, Any]
) -> Iterator[Observation]:
    """Bao quanh một lần gọi AI; trả về đối tượng để ghi kết quả, token và lỗi."""
    if not langfuse_configured():
        yield _NoTrace()
        return
    try:
        manager = _client().start_as_current_observation(
            name=name, as_type="generation", model=model, input=payload, metadata=metadata
        )
        observation = manager.__enter__()
    except Exception:
        logger.warning("Không ghi được trace Langfuse (bỏ qua).", exc_info=True)
        yield _NoTrace()
        return
    try:
        yield observation
    finally:
        try:
            manager.__exit__(None, None, None)
            _client().flush()
        except Exception:
            logger.warning("Không gửi được trace Langfuse (bỏ qua).", exc_info=True)
