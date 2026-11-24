"""API của AI Assistant: hội thoại, gửi câu chat, đồng ý hoặc bỏ qua thẻ xác nhận."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio import assistant
from studio.assistant_tools import TOOLS_BY_NAME, ToolError
from studio.database import get_session
from studio.datasets_api import fail
from studio.models import ChatMessage, ChatThread, Dataset

router = APIRouter(prefix="/api/assistant")
SessionDep = Annotated[Session, Depends(get_session)]
TITLE_LENGTH = 60


class NewThread(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class NewMessage(BaseModel):
    text: str = Field(default="", max_length=4000)
    dataset_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)


class CardDecision(BaseModel):
    decision: Literal["CONFIRM", "CANCEL"]


def _message_view(message: ChatMessage) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "role": message.role,
        "text": message.text,
        "status": message.status,
        "attachments": message.attachments,
        "steps": message.steps,
        "actions": [
            {key: card[key] for key in ("id", "title", "detail", "status", "result")}
            for card in message.actions
        ],
        "links": message.links,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _running(thread: ChatThread) -> bool:
    return any(message.status == "RUNNING" for message in thread.messages)


def thread_view(thread: ChatThread) -> dict[str, Any]:
    return {
        "id": str(thread.id),
        "title": thread.title,
        "running": _running(thread),
        "updated_at": thread.updated_at.isoformat() if thread.updated_at else None,
        "messages": [_message_view(message) for message in thread.messages],
    }


def _thread(session: Session, thread_id: uuid.UUID) -> ChatThread:
    thread = session.get(ChatThread, thread_id)
    if thread is None:
        raise fail(404, "THREAD_NOT_FOUND", "Không tìm thấy cuộc trò chuyện.")
    return thread


@router.get("/threads")
def list_threads(session: SessionDep) -> list[dict[str, Any]]:
    threads = session.scalars(select(ChatThread).order_by(ChatThread.updated_at.desc())).all()
    return [
        {
            "id": str(thread.id),
            "title": thread.title,
            "running": _running(thread),
            "updated_at": thread.updated_at.isoformat() if thread.updated_at else None,
        }
        for thread in threads
    ]


@router.post("/threads", status_code=201)
def create_thread(request: NewThread, session: SessionDep) -> dict[str, Any]:
    thread = ChatThread(id=uuid.uuid4(), title=request.title or "Cuộc trò chuyện mới")
    session.add(thread)
    session.commit()
    return thread_view(thread)


@router.get("/threads/{thread_id}")
def get_thread(thread_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
    return thread_view(_thread(session, thread_id))


@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: uuid.UUID, session: SessionDep) -> Response:
    """Xóa cuộc trò chuyện (chỉ hội thoại; dữ liệu và kết quả đối soát không bị đụng tới)."""
    session.delete(_thread(session, thread_id))
    session.commit()
    return Response(status_code=204)


@router.post("/threads/{thread_id}/messages", status_code=202)
def send_message(
    thread_id: uuid.UUID, request: NewMessage, session: SessionDep, background: BackgroundTasks
) -> dict[str, Any]:
    """Lưu câu chat (kèm tệp đính kèm nếu có), tạo câu trả lời đang soạn và chạy nền."""
    thread = _thread(session, thread_id)
    text = request.text.strip()
    if not text and not request.dataset_ids:
        raise fail(422, "EMPTY_MESSAGE", "Hãy nhập câu hỏi hoặc đính kèm tệp.")
    if _running(thread):
        raise fail(409, "ASSISTANT_BUSY", "Assistant đang trả lời câu trước, hãy đợi một chút.")
    attachments = []
    for dataset_id in dict.fromkeys(request.dataset_ids):
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            raise fail(404, "DATASET_NOT_FOUND", "Không tìm thấy tệp đính kèm.")
        attachments.append({"dataset_id": str(dataset.id), "name": dataset.original_filename})
    if not text:
        text = "Tôi vừa tải tệp lên, hãy kiểm tra giúp tôi."
    position = len(thread.messages)
    if position == 0 and thread.title == "Cuộc trò chuyện mới":
        thread.title = text if len(text) <= TITLE_LENGTH else text[: TITLE_LENGTH - 1] + "…"
    user = ChatMessage(
        id=uuid.uuid4(),
        thread=thread,
        position=position,
        role="user",
        text=text,
        status="DONE",
        attachments=attachments,
        steps=[],
        actions=[],
        links=[],
    )
    reply = ChatMessage(
        id=uuid.uuid4(),
        thread=thread,
        position=position + 1,
        role="assistant",
        text="",
        status="RUNNING",
        attachments=[],
        steps=[],
        actions=[],
        links=[],
    )
    session.add_all([user, reply])
    thread.updated_at = datetime.now(UTC)
    session.commit()
    background.add_task(assistant.run_turn, reply.id)
    return thread_view(thread)


@router.post("/messages/{message_id}/actions/{action_id}")
def decide_card(
    message_id: uuid.UUID,
    action_id: str,
    request: CardDecision,
    session: SessionDep,
    background: BackgroundTasks,
) -> dict[str, Any]:
    """Người dùng bấm "Đồng ý" (chạy đúng hàm API của nút trên giao diện) hoặc "Bỏ qua"."""
    message = session.get(ChatMessage, message_id)
    if message is None:
        raise fail(404, "MESSAGE_NOT_FOUND", "Không tìm thấy tin nhắn.")
    cards = [dict(card) for card in message.actions]
    card = next((item for item in cards if item["id"] == action_id), None)
    if card is None:
        raise fail(404, "ACTION_NOT_FOUND", "Không tìm thấy thẻ xác nhận.")
    if card["status"] != "PENDING":
        raise fail(409, "ACTION_DONE", "Thẻ này đã được xử lý.")
    if request.decision == "CANCEL":
        card["status"] = "CANCELLED"
    else:
        tool = TOOLS_BY_NAME[card["tool"]]
        assert tool.apply is not None
        try:
            card["result"] = tool.apply(
                session, tool.params.model_validate(card["args"]), background
            )
            card["status"] = "DONE"
        except (ToolError, ValidationError) as error:
            session.rollback()
            card["status"], card["result"] = "FAILED", str(error)
    message = session.get(ChatMessage, message_id)
    assert message is not None
    message.actions = cards
    message.thread.updated_at = datetime.now(UTC)
    session.commit()
    return thread_view(message.thread)
