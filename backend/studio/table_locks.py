"""Khóa theo bảng dữ liệu cho các tác vụ nền.

Các tác vụ nền (gợi ý ánh xạ, dựng bộ sạch) chạy trong luồng của backend. Nếu hai tác vụ
trên cùng một bảng chạy chồng nhau, tác vụ đọc dữ liệu cũ có thể ghi sau và thắng. Khóa này
bắt các tác vụ cùng bảng chạy lần lượt. Đủ cho demo vì backend chạy một tiến trình
(docs/DECISIONS.md: tác vụ nền chạy trong backend, chưa tách Worker); khi tách nhiều tiến
trình thì thay bằng khóa của PostgreSQL.
"""

import threading
import uuid
from collections import defaultdict

_registry_guard = threading.Lock()
_locks: defaultdict[uuid.UUID, threading.Lock] = defaultdict(threading.Lock)


def table_lock(table_id: uuid.UUID) -> threading.Lock:
    with _registry_guard:
        return _locks[table_id]
