"""Ghi nhật ký kiểm toán (docs/ARCHITECTURE.md mục 6).

Mỗi thao tác thay đổi dữ liệu của người dùng gọi `record` trong cùng phiên làm việc với
thay đổi đó, nên nhật ký và thay đổi cùng được lưu hoặc cùng bị hủy. Demo có một người
dùng nên tác nhân luôn là "Người dùng"; khi có đăng nhập thì thay bằng tên tài khoản.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from studio.models import AuditLog, DatasetTable

USER = "Người dùng"


def table_label(table: DatasetTable) -> str:
    """Tên dễ đọc của một bảng: tên bộ dữ liệu, kèm sheet nếu có."""
    name = table.dataset.name
    return f"{name} › {table.sheet_name}" if table.sheet_name else name


def record(
    session: Session,
    action: str,
    object_type: str,
    object_id: uuid.UUID | str,
    object_label: str,
    summary: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            id=uuid.uuid4(),
            # Ghi giờ từ ứng dụng (tới micro giây) để thứ tự nhật ký luôn đúng thứ tự thao tác.
            created_at=datetime.now(UTC),
            actor=USER,
            action=action,
            object_type=object_type,
            object_id=str(object_id),
            object_label=object_label,
            summary=summary,
            before=before,
            after=after,
        )
    )
