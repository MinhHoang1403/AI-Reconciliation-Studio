"""Kiểm tra các API trạng thái mà Docker và giao diện dựa vào."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from studio import database, main
from studio.config import settings

client = TestClient(main.app)


def test_health_is_always_ok() -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_ready_reports_503_when_database_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database, "database_is_reachable", lambda: False)
    reply = client.get("/api/ready")
    assert reply.status_code == 503
    assert reply.json() == {"status": "unavailable"}


def test_ready_is_ok_when_database_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database, "database_is_reachable", lambda: True)
    assert client.get("/api/ready").status_code == 200


def test_status_reports_gemini_configuration_without_leaking_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(database, "database_is_reachable", lambda: True)
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("khoa-bi-mat-thu-nghiem"))
    reply = client.get("/api/status")
    assert reply.json()["gemini"]["state"] == "CONFIGURED"
    # Khóa không bao giờ được trả ra API (RULES R14).
    assert "khoa-bi-mat-thu-nghiem" not in reply.text


def test_status_without_key_needs_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database, "database_is_reachable", lambda: True)
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr(""))
    assert client.get("/api/status").json()["gemini"]["state"] == "NEEDS_CONFIGURATION"
