"""Phiên làm việc đang mở của mỗi yêu cầu, và kiểm một đối tượng có thuộc phiên đó không.

Giao diện gửi mã phiên đang mở trong header `X-Workspace-Id` (luồng SSE và liên kết tải tệp
không đặt được header nên gửi bằng tham số `?workspace=`). Phụ thuộc `use_workspace` gắn cho
mọi router dữ liệu: nó kiểm phiên có thật rồi ghi vào một ContextVar, nên:

- danh sách (bộ dữ liệu, kỳ, lần đối soát, báo cáo, cuộc trò chuyện, nhật ký) chỉ lấy của phiên;
- dữ liệu mới (tệp, chuỗi đối soát, cuộc trò chuyện, dòng nhật ký) được gắn vào phiên;
- đối tượng mở theo mã mà thuộc phiên khác thì trả 404 như không có.

ContextVar là cách Python giữ giá trị riêng cho từng yêu cầu (PEP 567); FastAPI chạy hàm xử
lý đồng bộ và tác vụ nền trong bản sao ngữ cảnh của yêu cầu nên thấy đúng giá trị. Phụ thuộc
phải là hàm `async` để giá trị được đặt ngay trong ngữ cảnh của yêu cầu (không phải trong
luồng phụ). Không gửi mã phiên (công cụ dòng lệnh, kiểm thử cũ) thì dùng phiên tạo sớm nhất.
"""

import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Header, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio import database
from studio.models import (
    ChatMessage,
    ChatThread,
    Dataset,
    DatasetTable,
    MatchResult,
    ReconChain,
    ReconRun,
    Workspace,
)

DOMAIN_LABELS = {"SALES": "Bán hàng"}
DEFAULT_NAME = "Phiên làm việc 1"

_current: ContextVar[uuid.UUID | None] = ContextVar("workspace", default=None)


def new_workspace(name: str) -> Workspace:
    """Phiên mới, giờ tạo ghi từ ứng dụng tới micro giây: "phiên sớm nhất" (phiên mặc định khi
    không gửi mã phiên) phải xác định được kể cả khi hai phiên tạo trong cùng một giây."""
    return Workspace(id=uuid.uuid4(), name=name, domain="SALES", created_at=datetime.now(UTC))


def oldest(session: Session) -> Workspace:
    """Phiên tạo sớm nhất; chưa có phiên nào (cơ sở dữ liệu mới) thì tạo phiên đầu tiên."""
    found = session.scalar(select(Workspace).order_by(Workspace.created_at, Workspace.id).limit(1))
    if found is None:
        found = new_workspace(DEFAULT_NAME)
        session.add(found)
        session.commit()
    return found


def _resolve(wanted: uuid.UUID | None) -> uuid.UUID | None:
    with database.SessionFactory() as session:
        if wanted is None:
            return oldest(session).id
        return wanted if session.get(Workspace, wanted) is not None else None


async def use_workspace(
    x_workspace_id: Annotated[uuid.UUID | None, Header()] = None,
    workspace: Annotated[uuid.UUID | None, Query()] = None,
) -> uuid.UUID:
    """Phụ thuộc của mọi API dữ liệu: xác định phiên đang mở của yêu cầu."""
    found = await run_in_threadpool(_resolve, x_workspace_id or workspace)
    if found is None:
        raise HTTPException(
            404,
            {
                "code": "WORKSPACE_NOT_FOUND",
                "message": "Không tìm thấy phiên làm việc; có thể đã bị xóa.",
            },
        )
    _current.set(found)
    return found


def current_id(session: Session) -> uuid.UUID:
    """Phiên của yêu cầu đang chạy; ngoài yêu cầu (công cụ dòng lệnh) là phiên sớm nhất."""
    found = _current.get()
    return found if found is not None else oldest(session).id


def enter(workspace_id: uuid.UUID) -> None:
    """Đặt phiên cho việc chạy ngoài yêu cầu (lượt chat chạy nền dùng phiên của cuộc trò chuyện)."""
    _current.set(workspace_id)


def workspace_of(session: Session, item: Any) -> uuid.UUID | None:
    """Phiên của một đối tượng, lần theo bảng gốc của nó."""
    if isinstance(item, Dataset | ReconChain | ChatThread):
        return item.workspace_id
    if isinstance(item, DatasetTable):
        return item.dataset.workspace_id
    if isinstance(item, ChatMessage):
        return item.thread.workspace_id
    if isinstance(item, MatchResult):
        item = session.get(ReconRun, item.run_id)
    if isinstance(item, ReconRun):
        table = session.get(DatasetTable, item.left_table_id)
        return table.dataset.workspace_id if table is not None else None
    raise TypeError(f"Không biết phiên của {type(item).__name__}")


def owned[T](session: Session, item: T | None) -> T | None:
    """Trả lại đối tượng nếu nó thuộc phiên đang mở, ngược lại coi như không có (None)."""
    if item is None:
        return None
    return item if workspace_of(session, item) == current_id(session) else None


def table_ids(session: Session) -> Any:
    """Câu truy vấn con: mã các bảng của phiên đang mở (để lọc lần đối soát theo phiên)."""
    return (
        select(DatasetTable.id)
        .join(Dataset, DatasetTable.dataset_id == Dataset.id)
        .where(Dataset.workspace_id == current_id(session))
    )
