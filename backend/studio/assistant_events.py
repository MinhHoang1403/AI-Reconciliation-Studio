"""Bộ phát sự kiện của câu trả lời đang soạn (SSE: stage, delta, complete).

Lượt chat vẫn chạy nền như trước (`assistant.run_turn`), không gắn với kết nối của trình duyệt:
đóng tab hay mạng chập chờn thì câu trả lời vẫn soạn xong và được lưu. Bộ phát này chỉ chuyển
tiếp những gì lượt chat đang làm tới các kết nối SSE đang nghe:

- `stage`: trạng thái đầy đủ của tin nhắn (các bước, thẻ xác nhận, nút dẫn trang) sau mỗi lần
  ghi vào cơ sở dữ liệu. Gửi trọn trạng thái nên nhận lặp hay nhận lại không sai.
- `delta`: một đoạn chữ mới của câu trả lời (`{"text": ...}`), hoặc thay cả bản nháp
  (`{"text": ..., "reset": true}`) khi bản nháp phải sửa lại.
- `complete`: tin nhắn cuối cùng, đúng như đã lưu; sau đó kết nối đóng.

Mỗi tin nhắn có một kênh giữ số thứ tự sự kiện và bản nháp chữ hiện tại. Kết nối mới (kể cả
trình duyệt tự nối lại) nhận ảnh chụp: trạng thái trong cơ sở dữ liệu + bản nháp, rồi chỉ các
sự kiện có số thứ tự lớn hơn ảnh chụp, nên không mất và không lặp chữ.

Kênh nằm trong bộ nhớ của tiến trình backend: đủ vì backend chạy một tiến trình uvicorn
(DECISIONS 2026-11-27). Lượt chat chạy ở luồng nền, kết nối SSE chạy trên vòng sự kiện, nên
mọi thao tác đi qua một khóa và người nghe tự chuyển sự kiện về vòng sự kiện của mình.
"""

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

type Event = tuple[int, str, dict[str, Any]]  # (số thứ tự, tên sự kiện, dữ liệu)
type Listener = Callable[[Event], None]


@dataclass
class _Channel:
    seq: int = 0
    draft: str = ""
    listeners: list[Listener] = field(default_factory=list)


_channels: dict[uuid.UUID, _Channel] = {}
_lock = threading.Lock()


def publish(message_id: uuid.UUID, event: str, data: dict[str, Any]) -> None:
    """Phát một sự kiện của tin nhắn; `complete` đóng kênh. Không bao giờ ném lỗi ra lượt chat:
    người nghe hỏng (kết nối vừa đóng) không được làm hỏng câu trả lời."""
    with _lock:
        channel = _channels.setdefault(message_id, _Channel())
        channel.seq += 1
        if event == "delta":
            channel.draft = data["text"] if data.get("reset") else channel.draft + data["text"]
        if event == "complete":
            _channels.pop(message_id, None)
        item: Event = (channel.seq, event, data)
        listeners = list(channel.listeners)
    for listener in listeners:
        try:
            listener(item)
        except Exception:
            pass  # vòng sự kiện của kết nối đã đóng: bỏ qua người nghe đó


def subscribe(message_id: uuid.UUID, listener: Listener) -> tuple[str, int]:
    """Bắt đầu nghe; trả về bản nháp và số thứ tự tại lúc bắt đầu (cùng một lần khóa, nên sự
    kiện sau đó luôn có số lớn hơn)."""
    with _lock:
        channel = _channels.setdefault(message_id, _Channel())
        channel.listeners.append(listener)
        return channel.draft, channel.seq


def unsubscribe(message_id: uuid.UUID, listener: Listener) -> None:
    with _lock:
        channel = _channels.get(message_id)
        if channel is None:
            return
        if listener in channel.listeners:
            channel.listeners.remove(listener)
        # Kênh không còn ai nghe và chưa có sự kiện nào (tin nhắn đã xong từ trước): bỏ luôn.
        if not channel.listeners and channel.seq == 0:
            _channels.pop(message_id, None)


def open_channels() -> int:
    """Số kênh đang mở (để kiểm thử: kênh phải đóng khi câu trả lời xong)."""
    with _lock:
        return len(_channels)
