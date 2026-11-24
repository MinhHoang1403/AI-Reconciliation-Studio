"""Kiểm thử lại có giãn cách khi Gemini lỗi tạm thời (429, 5xx), bằng máy chủ giả trên máy.

SDK google-genai gửi yêu cầu thật tới một máy chủ HTTP cục bộ (không gọi Google, không tốn
phí); máy chủ trả lỗi theo kịch bản rồi mới trả lời đúng. Kiểm: lỗi tạm thời được thử lại
(có chờ), lỗi 4xx khác không thử lại, hết số lần thì báo lỗi rõ và ghi vào ai_calls.
"""

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from studio import database, gemini_client
from studio.config import settings
from studio.gemini_client import AiUnavailable
from studio.models import AiCall

ANSWER = {
    "candidates": [{"content": {"role": "model", "parts": [{"text": '{"ok": true}'}]}}],
    "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2},
}


class FakeGemini:
    """Máy chủ trả lần lượt các mã trong `script`, sau đó trả lời đúng."""

    def __init__(self, script: list[int], delay: float = 0.0) -> None:
        self.script = list(script)
        self.times: list[float] = []
        self.active = 0
        self.peak = 0  # số yêu cầu đến cùng lúc nhiều nhất
        self.lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 (tên hàm do http.server quy định)
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                with owner.lock:
                    owner.times.append(time.monotonic())
                    owner.active += 1
                    owner.peak = max(owner.peak, owner.active)
                    status = owner.script.pop(0) if owner.script else 200
                time.sleep(delay)
                with owner.lock:
                    owner.active -= 1
                body = ANSWER if status == 200 else {
                    "error": {"code": status, "message": "giả lập", "status": "UNAVAILABLE"}
                }
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_: Any) -> None:
                return None

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    from google import genai

    servers: list[FakeGemini] = []
    real_client = genai.Client

    def start(script: list[int], delay: float = 0.0) -> FakeGemini:
        server = FakeGemini(script, delay)
        servers.append(server)

        def client(**options: Any) -> Any:
            options["http_options"].base_url = server.url  # trỏ SDK vào máy chủ giả
            return real_client(**options)

        monkeypatch.setattr(genai, "Client", client)
        return server

    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("khoa-gia"))
    monkeypatch.setattr(settings, "gemini_attempts", 4)
    # Giãn cách ngắn cho kiểm thử nhanh; thứ tự tăng dần vẫn giữ nguyên.
    monkeypatch.setattr(gemini_client, "RETRY_INITIAL_DELAY", 0.2)
    monkeypatch.setattr(gemini_client, "RETRY_MAX_DELAY", 1.0)
    yield start
    for server in servers:
        server.server.shutdown()


def ask() -> Any:
    return gemini_client.generate_json(
        purpose="kiem-thu-thu-lai",
        system_instruction="x",
        payload={"a": 1},
        response_schema={"type": "object"},
    )


def last_call() -> AiCall:
    with database.SessionFactory() as session:
        calls = list(session.scalars(select(AiCall).where(AiCall.purpose == "kiem-thu-thu-lai")))
    return calls[-1]


def test_overloaded_server_is_retried_with_growing_waits(fake: Any) -> None:
    server = fake([503, 503])
    assert ask().data == {"ok": True}
    assert len(server.times) == 3  # hai lần lỗi, lần thứ ba thành công
    first_wait = server.times[1] - server.times[0]
    assert first_wait >= 0.05  # có chờ trước khi thử lại, không gửi dồn ngay
    assert last_call().status == "OK"


def test_rate_limit_is_retried_then_reported(fake: Any) -> None:
    server = fake([429, 429, 429, 429])
    with pytest.raises(AiUnavailable) as caught:
        ask()
    assert len(server.times) == settings.gemini_attempts == 4
    assert caught.value.code == "QUOTA_MINUTE" and "mỗi phút" in caught.value.message
    assert last_call().status == "FAILED" and last_call().error_code == "CLIENT_429"


def test_bad_request_is_not_retried(fake: Any) -> None:
    server = fake([400])
    with pytest.raises(AiUnavailable):
        ask()
    assert len(server.times) == 1  # lỗi do yêu cầu sai: thử lại vô ích


def test_tool_calls_share_the_same_retry(fake: Any) -> None:
    server = fake([500])
    turn = gemini_client.generate_with_tools(
        purpose="kiem-thu-thu-lai",
        system_instruction="x",
        conversation=[{"role": "user", "text": "xin chào"}],
        tools=[{"name": "list_datasets", "description": "x", "parameters": {"type": "object"}}],
    )
    assert turn.text == '{"ok": true}' and len(server.times) == 2


def test_parallel_calls_queue_instead_of_flooding(fake: Any) -> None:
    # Tải nhiều tệp một lúc làm nhiều bảng cùng gọi Gemini; chỉ 2 lần gọi được chạy cùng lúc.
    server = fake([], delay=0.3)
    threads = [threading.Thread(target=ask) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(server.times) == 4
    assert server.peak == gemini_client.MAX_CONCURRENT_CALLS == 2


def test_background_suggestions_give_up_sooner(fake: Any) -> None:
    # Gợi ý ánh xạ/sửa ô có phương án thay thế theo quy tắc: chỉ thử 2 lần khi Gemini quá tải.
    server = fake([503, 503, 503, 503])
    with pytest.raises(AiUnavailable):
        gemini_client.generate_json(
            purpose="kiem-thu-thu-lai",
            system_instruction="x",
            payload={"a": 1},
            response_schema={"type": "object"},
            attempts=gemini_client.BACKGROUND_ATTEMPTS,
        )
    assert len(server.times) == gemini_client.BACKGROUND_ATTEMPTS == 2


def test_daily_quota_is_explained_in_plain_vietnamese() -> None:
    from google.genai import errors

    daily = errors.ClientError(
        429,
        {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": (
            "Quota exceeded: Generate content requests per day limit exceeded on Free Tier. "
            "Please retry in 17h15m21.1s."
        )}},
    )
    code, text = gemini_client.explain_error(daily, "CLIENT_429")
    assert code == "QUOTA_DAY" and "17 giờ 15 phút" in text and "trả phí" in text
    busy = errors.ServerError(503, {"error": {"code": 503, "message": "overloaded"}})
    assert gemini_client.explain_error(busy, "SERVER_503")[1].startswith("Máy chủ Gemini")
