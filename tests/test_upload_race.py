"""Hai lần tải cùng một tệp chạy song song: lần sau trả về "đã có", không lỗi 500."""

from typing import Any

import pytest
from conftest import FIXTURES
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from studio import main

client = TestClient(main.app)


def test_parallel_duplicate_upload_is_reported_as_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = (FIXTURES / "giao-dich-cong-thanh-toan.csv").read_bytes()
    first = client.post("/api/datasets", files={"file": ("a.csv", content)})
    assert first.status_code == 202

    # Giả lập lần thứ hai kiểm "đã có chưa" trước khi lần thứ nhất ghi xong: bỏ qua lần tra
    # SHA-256 đầu tiên, để lần ghi vấp ràng buộc duy nhất trong cơ sở dữ liệu.
    original = Session.scalar
    calls = {"count": 0}

    def scalar_missing_first(self: Session, *args: Any, **kwargs: Any) -> Any:
        calls["count"] += 1
        return None if calls["count"] == 1 else original(self, *args, **kwargs)

    monkeypatch.setattr(Session, "scalar", scalar_missing_first)
    second = client.post("/api/datasets", files={"file": ("b.csv", content)})
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["dataset"]["id"] == first.json()["dataset"]["id"]
