"""API phiên làm việc: danh sách, tạo mới, đổi tên, xóa.

Mỗi phiên là một không gian riêng (tệp, kỳ, kết quả, báo cáo, cuộc trò chuyện, nhật ký, bộ nhớ
ánh xạ). Các API dữ liệu khác chỉ làm việc trong phiên mà giao diện gửi kèm (`workspaces.py`).
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from studio import audit, storage, workspaces
from studio.database import get_session
from studio.datasets_api import fail, remove_dataset
from studio.models import (
    AuditLog,
    ChatMessage,
    ChatThread,
    Dataset,
    DatasetTable,
    MappingMemory,
    ReconChain,
    ReconRun,
    Workspace,
)

router = APIRouter(prefix="/api/workspaces")
SessionDep = Annotated[Session, Depends(get_session)]


class WorkspaceName(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def _tidy(cls, value: str) -> str:
        # Gọn khoảng trắng thừa; tên chỉ toàn khoảng trắng coi như trống.
        tidy = " ".join(value.split())
        if not tidy:
            raise ValueError("Tên phiên không được để trống.")
        return tidy


def _counts(session: Session, column: Any, model: Any) -> dict[uuid.UUID, int]:
    rows = session.execute(select(column, func.count()).select_from(model).group_by(column))
    return {workspace_id: count for workspace_id, count in rows}


def _latest(session: Session, column: Any, moment: Any) -> dict[uuid.UUID, datetime]:
    rows = session.execute(select(column, func.max(moment)).group_by(column))
    return {workspace_id: value for workspace_id, value in rows if value is not None}


def _view(
    item: Workspace,
    datasets: dict[uuid.UUID, int],
    threads: dict[uuid.UUID, int],
    chains: dict[uuid.UUID, int],
    activity: dict[uuid.UUID, datetime],
) -> dict[str, Any]:
    active = activity.get(item.id) or item.created_at
    return {
        "id": str(item.id),
        "name": item.name,
        "domain": item.domain,
        "domain_label": workspaces.DOMAIN_LABELS.get(item.domain, item.domain),
        "datasets": datasets.get(item.id, 0),
        "reconciliations": chains.get(item.id, 0),
        "threads": threads.get(item.id, 0),
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "last_activity": active.isoformat() if active else None,
    }


def _all_views(session: Session) -> list[dict[str, Any]]:
    """Mọi phiên kèm số tệp, số lần đối soát cả chuỗi, số cuộc trò chuyện và lần hoạt động gần
    nhất (mỗi con số một câu truy vấn gộp, không truy vấn từng phiên)."""
    workspaces.oldest(session)  # cơ sở dữ liệu mới chưa có phiên nào thì tạo phiên đầu tiên
    datasets = _counts(session, Dataset.workspace_id, Dataset)
    threads = _counts(session, ChatThread.workspace_id, ChatThread)
    chains = _counts(session, ReconChain.workspace_id, ReconChain)
    activity: dict[uuid.UUID, datetime] = {}
    for found in (
        _latest(session, AuditLog.workspace_id, AuditLog.created_at),
        _latest(session, ChatThread.workspace_id, ChatThread.updated_at),
    ):
        for workspace_id, moment in found.items():
            if workspace_id not in activity or _naive(moment) > _naive(activity[workspace_id]):
                activity[workspace_id] = moment
    items = session.scalars(select(Workspace).order_by(Workspace.created_at, Workspace.id)).all()
    return [_view(item, datasets, threads, chains, activity) for item in items]


def _naive(moment: datetime) -> datetime:
    """So sánh được giờ có và không có múi giờ (SQLite trong kiểm thử bỏ múi giờ)."""
    return moment.replace(tzinfo=None)


def _workspace(session: Session, workspace_id: uuid.UUID) -> Workspace:
    found = session.get(Workspace, workspace_id)
    if found is None:
        raise fail(404, "WORKSPACE_NOT_FOUND", "Không tìm thấy phiên làm việc.")
    return found


def _unique_name(session: Session, name: str, skip: uuid.UUID | None = None) -> None:
    """Tên phiên không trùng (không phân biệt hoa thường) để danh sách chọn phiên rõ ràng."""
    query = select(Workspace.id).where(func.lower(Workspace.name) == name.lower())
    if skip is not None:
        query = query.where(Workspace.id != skip)
    if session.scalar(query) is not None:
        raise fail(409, "WORKSPACE_NAME_TAKEN", f"Đã có phiên tên “{name}”; hãy đặt tên khác.")


@router.get("")
def list_workspaces(session: SessionDep) -> list[dict[str, Any]]:
    return _all_views(session)


@router.post("", status_code=201)
def create_workspace(request: WorkspaceName, session: SessionDep) -> dict[str, Any]:
    """Tạo phiên trống (lĩnh vực bán hàng, lĩnh vực duy nhất hiện có)."""
    _unique_name(session, request.name)
    item = workspaces.new_workspace(request.name)
    session.add(item)
    session.flush()
    workspaces.enter(item.id)
    audit.record(
        session, "WORKSPACE_CREATED", "WORKSPACE", item.id, item.name,
        f"Tạo phiên làm việc “{item.name}”.",
    )
    session.commit()
    return next(view for view in _all_views(session) if view["id"] == str(item.id))


@router.patch("/{workspace_id}")
def rename_workspace(
    workspace_id: uuid.UUID, request: WorkspaceName, session: SessionDep
) -> dict[str, Any]:
    item = _workspace(session, workspace_id)
    if request.name != item.name:
        _unique_name(session, request.name, item.id)
        workspaces.enter(item.id)
        audit.record(
            session, "WORKSPACE_RENAMED", "WORKSPACE", item.id, request.name,
            f"Đổi tên phiên “{item.name}” thành “{request.name}”.",
            {"name": item.name}, {"name": request.name},
        )
        item.name = request.name
        session.commit()
    return next(view for view in _all_views(session) if view["id"] == str(item.id))


def _busy(session: Session, workspace_id: uuid.UUID) -> bool:
    """Phiên còn việc chạy nền (đọc tệp, ánh xạ, làm sạch, đối soát, Assistant đang trả lời):
    xóa lúc này thì việc nền sẽ ghi vào dữ liệu đã mất."""
    tables = session.scalar(
        select(func.count())
        .select_from(DatasetTable)
        .join(Dataset, DatasetTable.dataset_id == Dataset.id)
        .where(
            Dataset.workspace_id == workspace_id,
            (DatasetTable.status == "READING")
            | (DatasetTable.mapping_status == "MAPPING")
            | DatasetTable.clean_status.in_(("BUILDING", "SUGGESTING")),
        )
    )
    reading = session.scalar(
        select(func.count()).where(
            Dataset.workspace_id == workspace_id, Dataset.status == "READING"
        )
    )
    chains = session.scalar(
        select(func.count()).where(
            ReconChain.workspace_id == workspace_id, ReconChain.status == "RUNNING"
        )
    )
    # Lần đối soát hai bảng đứng riêng (không thuộc chuỗi) đang chạy nền.
    runs = session.scalar(
        select(func.count())
        .select_from(ReconRun)
        .join(DatasetTable, ReconRun.left_table_id == DatasetTable.id)
        .join(Dataset, DatasetTable.dataset_id == Dataset.id)
        .where(Dataset.workspace_id == workspace_id, ReconRun.status == "RUNNING")
    )
    replies = session.scalar(
        select(func.count())
        .select_from(ChatMessage)
        .join(ChatThread, ChatMessage.thread_id == ChatThread.id)
        .where(ChatThread.workspace_id == workspace_id, ChatMessage.status == "RUNNING")
    )
    return bool(tables or reading or chains or runs or replies)


@router.delete("/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: uuid.UUID, session: SessionDep) -> Response:
    """Xóa hẳn phiên cùng mọi thứ bên trong: tệp gốc (trừ khi phiên khác cũng tải đúng tệp đó),
    bảng đã đọc, bộ sạch, kết quả đối soát, báo cáo, cuộc trò chuyện, nhật ký và bộ nhớ ánh xạ.
    Luôn giữ ít nhất một phiên để giao diện có chỗ làm việc."""
    item = _workspace(session, workspace_id)
    if session.scalar(select(func.count()).select_from(Workspace)) == 1:
        raise fail(
            409, "LAST_WORKSPACE", "Đây là phiên duy nhất; hãy tạo phiên mới trước khi xóa."
        )
    if _busy(session, item.id):
        raise fail(
            409, "WORKSPACE_BUSY",
            "Phiên đang có việc chạy (đọc tệp, đối soát hoặc AI đang trả lời); hãy đợi xong.",
        )
    paths: list[str | None] = []
    for dataset in session.scalars(select(Dataset).where(Dataset.workspace_id == item.id)):
        paths += remove_dataset(session, dataset)
    session.flush()
    # Xóa rõ từng loại thay vì chỉ trông vào xóa dây chuyền của cơ sở dữ liệu (SQLite trong
    # kiểm thử không bật); cuộc trò chuyện xóa qua ORM để xóa luôn tin nhắn.
    for thread in session.scalars(select(ChatThread).where(ChatThread.workspace_id == item.id)):
        session.delete(thread)
    for model in (ReconChain, AuditLog, MappingMemory):
        session.execute(delete(model).where(model.workspace_id == item.id))
    session.delete(item)
    session.commit()
    for path in paths:
        storage.delete_file(path)
    return Response(status_code=204)
