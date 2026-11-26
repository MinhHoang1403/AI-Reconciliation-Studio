"""Kiểm thư mục data-docs: phần tĩnh khớp code, nhật ký gọi Gemini và catalog động được ghi đúng.

Không gọi Gemini thật: client SDK được thay bằng bản giả trả lời sẵn.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import FIXTURES, ROOT
from fastapi.testclient import TestClient
from pydantic import SecretStr

from studio import data_docs, gemini_client, main
from studio.config import settings

client = TestClient(main.app)
SECRET = "khoa-gia-khong-duoc-lo-123"


def test_static_documents_match_the_code() -> None:
    # Quên chạy tools/export_data_docs.py sau khi sửa mô hình, cột chuẩn, khuôn JSON hay API thì
    # bài này báo đúng tệp lệch.
    stale = [
        relative
        for relative, content in data_docs.static_documents().items()
        if not (ROOT / "data-docs" / relative).exists()
        or (ROOT / "data-docs" / relative).read_text(encoding="utf-8") != content
    ]
    assert stale == [], f"Chạy: uv run --locked python tools/export_data_docs.py ({stale})"


def test_catalog_describes_the_whole_domain() -> None:
    fields = data_docs.canonical_fields()["fields"]
    assert len(fields) == 17 and {"order_id", "amount", "description"} <= {f["key"] for f in fields}
    order_id = next(field for field in fields if field["key"] == "order_id")
    assert "ORDERS_POS" in order_id["required_in"]
    kinds = data_docs.result_kinds()["kinds"]
    assert len(kinds) == 11 and all(kind["description"] for kind in kinds)
    tables = {table["name"] for table in data_docs.postgres_schema()["tables"]}
    assert {"datasets", "match_results", "ai_calls", "audit_log"} <= tables
    tools = data_docs.ai_schemas()["assistant-tools.json"]
    assert len(tools) == 25 and all("parameters" in tool for tool in tools)


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "data_docs_dir", tmp_path)
    return tmp_path


def fake_gemini(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    reply = SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=5),
    )
    models = SimpleNamespace(generate_content=lambda **_: reply)
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr(SECRET))
    monkeypatch.setattr(gemini_client, "_client", lambda attempts: SimpleNamespace(models=models))


def records(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / "ai-calls").rglob("*.json"))
    ]


def test_each_gemini_call_is_saved_with_input_schema_and_answer(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_gemini(monkeypatch, '{"text": "Đã khớp 91%."}')
    schema = {"type": "object", "properties": {"text": {"type": "string"}}}
    gemini_client.generate_json(
        purpose="nhan-xet-bao-cao",
        system_instruction="Chỉ dùng số liệu được gửi.",
        payload={"facts": {"ty_le": "91%"}},
        response_schema=schema,
    )
    [record] = records(runtime)
    assert record["purpose"] == "nhan-xet-bao-cao" and record["status"] == "OK"
    assert record["request"]["input"] == {"facts": {"ty_le": "91%"}}
    assert record["request"]["response_schema"] == schema
    assert record["response"] == {"text": "Đã khớp 91%."}
    assert record["tokens"] == {"input": 12, "output": 5} and record["ai_call_id"]
    # Bằng chứng không bao giờ chứa khóa API.
    assert SECRET not in json.dumps(record)


def test_failed_calls_are_saved_too(runtime: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_gemini(monkeypatch, "không phải JSON")
    with pytest.raises(gemini_client.AiUnavailable):
        gemini_client.generate_json(
            purpose="goi-y-sua-o",
            system_instruction="x",
            payload={"a": 1},
            response_schema={"type": "object"},
        )
    [record] = records(runtime)
    assert record["status"] == "FAILED" and record["error_code"] and record["response"] is None


def test_assistant_call_saves_conversation_and_tool_declarations(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[]))],
        function_calls=[],
        usage_metadata=None,
    )
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr(SECRET))
    monkeypatch.setattr(
        gemini_client,
        "_client",
        lambda attempts: SimpleNamespace(
            models=SimpleNamespace(generate_content=lambda **_: fake)
        ),
    )
    tools = [{"name": "list_datasets", "description": "x", "parameters": {"type": "object"}}]
    gemini_client.generate_with_tools(
        purpose="assistant",
        system_instruction="Bạn là AI Assistant.",
        conversation=[{"role": "user", "text": "Tôi đã tải tệp nào?"}],
        tools=tools,
    )
    [record] = records(runtime)
    assert record["request"]["kind"] == "function_calling"
    assert record["request"]["tools"] == tools
    assert record["request"]["conversation"][0]["text"] == "Tôi đã tải tệp nào?"


def test_dataset_catalog_is_written_and_removed_with_the_dataset(runtime: Path) -> None:
    content = (FIXTURES / "don-hang-cua-hang.csv").read_bytes()
    reply = client.post("/api/datasets", files={"file": ("don-hang-cua-hang.csv", content)})
    dataset_id = reply.json()["dataset"]["id"]
    path = runtime / "catalog" / "datasets" / f"{dataset_id}.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    assert catalog["dataset"]["sha256"] == reply.json()["dataset"]["sha256"]
    [table] = catalog["tables"]
    assert table["row_count"] > 200 and table["clean_versions"]
    mapped = {column["name"]: column["mapping"]["field"] for column in table["columns"]}
    assert mapped["MaHD"] == "order_id" and mapped["TongTien"] == "amount"
    assert table["columns"][0]["profile"]["name"] == "MaHD"

    client.delete(f"/api/datasets/{dataset_id}")
    assert not path.exists()


def test_nothing_is_written_when_the_folder_is_not_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "data_docs_dir", None)
    fake_gemini(monkeypatch, '{"text": "ok"}')
    gemini_client.generate_json(
        purpose="x", system_instruction="x", payload={}, response_schema={"type": "object"}
    )
    assert data_docs.write_ai_call({"purpose": "x"}) is None
    assert list(tmp_path.iterdir()) == []


def test_catalog_errors_never_break_the_user_action(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: Any) -> set[Any]:
        raise RuntimeError("hỏng khi theo dõi")

    monkeypatch.setattr(data_docs, "_dataset_ids", broken)
    content = (FIXTURES / "giao-dich-cong-thanh-toan.csv").read_bytes()
    reply = client.post("/api/datasets", files={"file": ("cong.csv", content)})
    assert reply.status_code == 202
    dataset = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
    assert dataset["status"] == "READY"
