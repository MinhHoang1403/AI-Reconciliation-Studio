"""Kiểm phần ghi trace Langfuse không làm chậm tính năng AI (không cần Langfuse thật)."""

from typing import Any

import pytest
from pydantic import SecretStr

from studio import tracing
from studio.config import settings


class FakeClient:
    def __init__(self) -> None:
        self.flushes = 0
        self.closed = 0

    def start_as_current_observation(self, **_: Any) -> Any:
        client = self

        class Manager:
            def __enter__(self) -> Any:
                return self

            def __exit__(self, *_: Any) -> None:
                client.closed += 1

            def update(self, **_: Any) -> None:
                return None

        return Manager()

    def flush(self) -> None:
        self.flushes += 1


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    client = FakeClient()
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-gia")
    monkeypatch.setattr(settings, "langfuse_secret_key", SecretStr("sk-gia"))
    tracing._client.cache_clear()
    monkeypatch.setattr(tracing, "_client", _cached(client))
    return client


def _cached(client: FakeClient) -> Any:
    def get() -> FakeClient:
        return client

    get.cache_info = lambda: type("Info", (), {"currsize": 1})()  # type: ignore[attr-defined]
    return get


def test_each_step_does_not_wait_for_sending(fake: FakeClient) -> None:
    # Khi Langfuse tắt hay chậm, flush() sau mỗi bước từng làm mỗi lần gọi AI chậm thêm 4–11
    # giây; SDK tự gửi theo lô ở nền nên bước chỉ được đóng, không được đứng chờ gửi.
    for _ in range(3):
        with tracing.observation("thu", "generation", {"a": 1}, {}) as step:
            step.update(output={"b": 2})
    assert fake.closed == 3 and fake.flushes == 0


def test_pending_traces_are_sent_on_shutdown(fake: FakeClient) -> None:
    tracing.flush_traces()
    assert fake.flushes == 1


def test_nothing_happens_without_langfuse_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "langfuse_public_key", "")
    tracing.warm_up()
    tracing.flush_traces()  # không khởi tạo client, không lỗi
    with tracing.observation("thu", "generation", {}, {}) as step:
        step.update(output={})
