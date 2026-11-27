"""Kiểm luồng SSE của AI Assistant (stage, delta, complete) với Gemini giả lập (không tốn phí).

Kiểm phần do code quyết định:
- chữ hiện dần ghép lại đúng bằng câu trả lời đã lưu, mã kỹ thuật không lọt ra dù bị cắt giữa
  hai đoạn;
- thứ tự sự kiện: các bước trước, chữ sau, `complete` cuối cùng và đóng kênh;
- kết nối mới hay kết nối lại nhận ảnh chụp đầy đủ, không mất, không lặp chữ;
- Gemini streaming được gom lại thành một câu trả lời giữ nguyên mọi phần (chữ ký suy nghĩ).
"""

import asyncio
import json
import random
import threading
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from conftest import FIXTURES
from fastapi.sse import ServerSentEvent
from fastapi.testclient import TestClient
from google.genai import types
from test_assistant import call, upload, use

from studio import (
    assistant,
    assistant_api,
    assistant_events,
    database,
    gemini_client,
    main,
    workspaces,
)
from studio.gemini_client import ModelTurn
from studio.models import ChatMessage, ChatThread

client = TestClient(main.app)


# ---------------------------------------------------------------- chữ hiện dần


def stream_text(text: str, sizes: list[int]) -> tuple[str, list[dict[str, Any]]]:
    """Cho `text` qua DraftText theo các đoạn dài `sizes`; trả về bản nháp ghép lại và các
    sự kiện delta."""
    events: list[dict[str, Any]] = []
    draft = assistant.DraftText(events.append)
    position = 0
    for size in sizes:
        draft.add(text[position : position + size])
        position += size
    shown = ""
    for event in events:
        shown = event["text"] if event.get("reset") else shown + event["text"]
    return shown, events


ANSWERS = [
    "Có 2 ca cần bạn chọn (loại AMBIGUOUS) và 1 ca ONLY_IN_A đang OPEN.\n- Ca 1: HD000123",
    "Trạng thái: `RESOLVED`. Bảng ORDERS_POS (mã: ORDERS_POS) có 120 dòng (kể cả kỳ trước).",
    "Không có mã kỹ thuật nào ở đây, chỉ có số 1.250.000 đ và mã đơn HD000950.",
]


@pytest.mark.parametrize("answer", ANSWERS)
def test_draft_never_shows_internal_codes_however_it_is_cut(answer: str) -> None:
    rng = random.Random(answer)
    final = assistant.plain_text(answer)
    for _ in range(200):
        sizes = [rng.randint(1, 9) for _ in range(len(answer))]
        shown, events = stream_text(answer, sizes)
        # Bản nháp luôn là phần đầu của câu trả lời cuối (chỉ thiếu phần đuôi đang giữ lại).
        assert final.startswith(shown)
        for event in events:
            for code in assistant.PLAIN_LABELS:
                assert code not in event["text"], (code, event)


def test_draft_grows_without_rewriting_when_codes_are_split() -> None:
    shown, events = stream_text(ANSWERS[0], [3] * 40)
    assert not any(event.get("reset") for event in events)
    assert "(loại" not in shown and "Cần bạn chọn" not in shown.split("chọn")[0]
    assert shown == assistant.plain_text(ANSWERS[0]).rsplit(" ", 1)[0].rstrip()


def test_clear_drops_the_preamble_of_a_tool_turn() -> None:
    events: list[dict[str, Any]] = []
    draft = assistant.DraftText(events.append)
    draft.add("Để tôi xem dữ liệu ")
    draft.clear()
    assert events[-1] == {"text": "", "reset": True}
    draft.clear()  # chưa phát gì thì không phát thêm sự kiện
    assert len(events) == 2


# ---------------------------------------------------------------- cả một lượt chat


def record_events() -> tuple[list[tuple[str, dict[str, Any]]], Any]:
    """Nghe mọi tin nhắn: thay hàm publish để ghi lại sự kiện theo thứ tự phát."""
    seen: list[tuple[str, dict[str, Any]]] = []
    original = assistant_events.publish

    def publish(message_id: uuid.UUID, event: str, data: dict[str, Any]) -> None:
        seen.append((event, data))
        original(message_id, event, data)

    return seen, publish


def test_a_turn_streams_stages_then_text_then_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    upload(FIXTURES / "don-hang-cua-hang.csv")
    answer = "Bạn có 1 tệp đơn hàng, chưa có ca nào AMBIGUOUS cần chọn."
    use(monkeypatch, [ModelTurn("Để tôi xem ", [call("list_datasets").calls[0]]),
                      ModelTurn(answer, [])])
    seen, publish = record_events()
    monkeypatch.setattr(assistant_events, "publish", publish)
    thread = client.post("/api/assistant/threads", json={}).json()
    client.post(f"/api/assistant/threads/{thread['id']}/messages", json={"text": "Có gì?"})

    names = [name for name, _ in seen]
    assert names[-1] == "complete" and names.count("complete") == 1
    # Chữ mở đầu của lượt gọi công cụ ("Để tôi xem") chảy trước, bị xóa khỏi bản nháp khi
    # Gemini gọi công cụ; bước công cụ hiện ra; rồi câu trả lời thật mới chảy.
    steps = [i for i, (name, data) in enumerate(seen) if name == "stage" and data["steps"]]
    cleared = seen.index(("delta", {"text": "", "reset": True}))
    last_delta = max(i for i, (name, _) in enumerate(seen) if name == "delta")
    assert seen[0] == ("delta", {"text": "Để tôi"})  # từ cuối còn giữ lại chờ đủ từ
    assert cleared < steps[0] < last_delta

    shown = ""
    for name, data in seen:
        if name == "delta":
            shown = data["text"] if data.get("reset") else shown + data["text"]
    final = seen[-1][1]
    assert final["status"] == "DONE" and final["text"] == assistant.plain_text(answer)
    assert "AMBIGUOUS" not in final["text"] and final["text"].startswith(shown)
    assert "AMBIGUOUS" not in shown
    assert assistant_events.open_channels() == 0  # kênh đóng khi câu trả lời xong


# ---------------------------------------------------------------- đường SSE


def running_message() -> uuid.UUID:
    """Một câu trả lời đang soạn (như lúc lượt chat còn chạy nền)."""
    with database.SessionFactory() as session:
        thread = ChatThread(
            id=uuid.uuid4(), workspace_id=workspaces.oldest(session).id, title="Thử luồng"
        )
        reply = ChatMessage(
            id=uuid.uuid4(), thread=thread, position=0, role="assistant", text="",
            status="RUNNING", attachments=[], steps=[], actions=[], links=[],
        )
        session.add_all([thread, reply])
        session.commit()
        return reply.id


async def collect(stream: AsyncIterator[ServerSentEvent], count: int) -> list[ServerSentEvent]:
    return [await asyncio.wait_for(anext(stream), timeout=5) for _ in range(count)]


def test_stream_sends_snapshot_then_only_newer_events() -> None:
    message_id = running_message()
    with database.SessionFactory() as session:
        reply = session.get(ChatMessage, message_id)
        assert reply is not None
        assistant._save(session, reply, steps=[{"label": "Đọc dữ liệu", "status": "RUNNING"}])
    assistant_events.publish(message_id, "delta", {"text": "Bạn có "})

    async def scenario() -> list[ServerSentEvent]:
        stream = assistant_api.message_events(message_id)
        # Kết nối mới: ảnh chụp gồm bước đã có và bản nháp đã viết.
        got = await collect(stream, 2)

        def later() -> None:
            assistant_events.publish(message_id, "delta", {"text": "1 tệp."})
            with database.SessionFactory() as session:
                reply = session.get(ChatMessage, message_id)
                assert reply is not None
                assistant._save(session, reply, text="Bạn có 1 tệp.", status="DONE")

        await asyncio.to_thread(later)
        got += await collect(stream, 2)
        with pytest.raises(StopAsyncIteration):
            await anext(stream)  # complete rồi thì đóng luồng
        return got

    events = asyncio.run(scenario())
    assert [event.event for event in events] == ["stage", "delta", "delta", "complete"]
    assert events[0].data["steps"][0]["label"] == "Đọc dữ liệu"
    assert events[1].data == {"text": "Bạn có ", "reset": True}
    assert events[2].data == {"text": "1 tệp."}
    assert events[3].data["text"] == "Bạn có 1 tệp."
    ids = [int(event.id or 0) for event in events[1:]]
    assert ids == sorted(ids)
    assert assistant_events.open_channels() == 0


def test_two_listeners_get_the_same_events_from_a_background_thread() -> None:
    message_id = running_message()

    async def listener() -> list[str]:
        stream = assistant_api.message_events(message_id)
        names = [event.event or "" for event in await collect(stream, 1)]
        ready.release()
        names += [event.event or "" for event in await collect(stream, 3)]
        return names

    ready = threading.Semaphore(0)

    async def scenario() -> list[list[str]]:
        tasks = [asyncio.create_task(listener()) for _ in range(2)]

        def write() -> None:
            ready.acquire()
            ready.acquire()
            for piece in ("Một ", "hai "):
                assistant_events.publish(message_id, "delta", {"text": piece})
            with database.SessionFactory() as session:
                reply = session.get(ChatMessage, message_id)
                assert reply is not None
                assistant._save(session, reply, text="Một hai", status="DONE")

        await asyncio.to_thread(write)
        return list(await asyncio.gather(*tasks))

    for names in asyncio.run(scenario()):
        assert names == ["stage", "delta", "delta", "complete"]


def test_finished_or_missing_message_over_http() -> None:
    message_id = running_message()
    with database.SessionFactory() as session:
        reply = session.get(ChatMessage, message_id)
        assert reply is not None
        assistant._save(session, reply, text="Đã xong.", status="DONE")
    response = client.get(f"/api/assistant/messages/{message_id}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"  # Nginx không giữ lại dữ liệu
    lines = response.text.splitlines()
    assert lines[0] == "event: complete" and "event: stage" not in lines
    assert json.loads(lines[1].removeprefix("data: "))["text"] == "Đã xong."
    missing = client.get(f"/api/assistant/messages/{uuid.uuid4()}/events")
    assert missing.status_code == 404
    assert assistant_events.open_channels() == 0


def test_stream_ends_when_a_turn_dies_without_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backend khởi động lại giữa chừng đánh dấu tin nhắn lỗi mà không phát `complete`: luồng
    tự đọc lại cơ sở dữ liệu và kết thúc, giao diện không chờ mãi."""
    monkeypatch.setattr(assistant_api, "STREAM_RECHECK_SECONDS", 0.2)
    message_id = running_message()

    async def scenario() -> list[ServerSentEvent]:
        stream = assistant_api.message_events(message_id)
        got = await collect(stream, 1)

        def fail_quietly() -> None:
            with database.SessionFactory() as session:
                reply = session.get(ChatMessage, message_id)
                assert reply is not None
                reply.status, reply.text = "FAILED", "Backend khởi động lại."
                session.commit()

        await asyncio.to_thread(fail_quietly)
        got += await collect(stream, 1)
        return got

    events = asyncio.run(scenario())
    assert [event.event for event in events] == ["stage", "complete"]
    assert events[1].data["status"] == "FAILED"
    assistant_events.publish(message_id, "complete", {})  # dọn kênh của bài kiểm


# ---------------------------------------------------------------- gom các đoạn của Gemini


def chunk(*parts: types.Part, usage: int | None = None) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=100, candidates_token_count=usage
        )
        if usage
        else None,
    )


def test_streamed_chunks_keep_every_part_and_signature() -> None:
    pieces: list[str] = []
    chunks = [
        chunk(types.Part(text="Đang nghĩ", thought=True)),
        chunk(types.Part(text="Bạn có ")),
        chunk(types.Part(text="1 tệp."), usage=5),
        chunk(types.Part(text="", thought_signature=b"chu-ky"), usage=7),
        chunk(types.Part.from_function_call(name="list_datasets", args={})),
    ]
    response = gemini_client.collect_stream(chunks, pieces.append)
    assert pieces == ["Bạn có ", "1 tệp."]  # phần suy nghĩ không bao giờ hiện
    parts = response.candidates[0].content.parts
    assert len(parts) == 5 and parts[3].thought_signature == b"chu-ky"
    assert [call.name for call in response.function_calls] == ["list_datasets"]
    assert response.usage_metadata.candidates_token_count == 7
