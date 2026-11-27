"""Ghi dấu vết (trace) các lần gọi AI vào Langfuse.

Chỉ bật khi `.env` có đủ LANGFUSE_PUBLIC_KEY và LANGFUSE_SECRET_KEY. Dữ liệu gửi lên
Langfuse là gói đã che (giống hệt gói gửi Gemini), không bao giờ là dữ liệu gốc.
Lỗi của Langfuse không được làm hỏng tính năng chính: ghi không được thì bỏ qua.
"""

import logging
import threading
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
    with observation(name, "generation", payload, metadata, model=model) as traced:
        yield traced


@contextmanager
def observation(
    name: str, as_type: str, payload: Any, metadata: dict[str, Any], **extra: Any
) -> Iterator[Observation]:
    """Một bước trong Langfuse (lượt chat của Assistant là "agent", mỗi công cụ là "tool",
    mỗi lần gọi Gemini là "generation"). Bước mở bên trong bước khác tự nằm dưới bước đó,
    nên một lượt chat là một trace gồm các lần gọi Gemini và các công cụ đã chạy."""
    if not langfuse_configured():
        yield _NoTrace()
        return
    try:
        manager = _client().start_as_current_observation(
            name=name, as_type=as_type, input=payload, metadata=metadata, **extra
        )
        observation = manager.__enter__()
    except Exception:
        logger.warning("Không ghi được trace Langfuse (bỏ qua).", exc_info=True)
        yield _NoTrace()
        return
    try:
        yield observation
    finally:
        # Chỉ đóng bước; SDK tự gửi trace theo lô ở luồng nền. Không gọi flush() ở đây: flush
        # đứng chờ gửi xong, khi Langfuse tắt hay chậm mỗi bước bị chậm thêm 4–11 giây (đo
        # 27/11/2026), một lượt Assistant nhiều bước có thể chậm thêm cả phút. Tài liệu
        # Langfuse: flush() chỉ cần ở tiến trình chạy ngắn; máy chủ chạy lâu thì gửi nốt lúc tắt.
        try:
            manager.__exit__(None, None, None)
        except Exception:
            logger.warning("Không đóng được trace Langfuse (bỏ qua).", exc_info=True)


def warm_up() -> None:
    """Khởi tạo client Langfuse ở luồng nền lúc backend khởi động. Khởi tạo mất 3–4 giây (đo
    27/11/2026); không làm trước thì lần gọi AI đầu tiên của người dùng phải chờ phần này.
    Chỉ nối tới Langfuse tự host trên máy, không gọi dịch vụ trả phí (R11)."""
    if not langfuse_configured():
        return

    def start() -> None:
        try:
            _client()
        except Exception:
            logger.warning("Không khởi tạo được Langfuse (bỏ qua).", exc_info=True)

    threading.Thread(target=start, name="langfuse-warm-up", daemon=True).start()


def flush_traces() -> None:
    """Gửi nốt trace còn trong hàng đợi khi backend tắt (không khởi tạo client nếu chưa dùng)."""
    if not langfuse_configured() or _client.cache_info().currsize == 0:
        return
    try:
        _client().flush()
    except Exception:
        logger.warning("Không gửi được trace Langfuse khi tắt (bỏ qua).", exc_info=True)
