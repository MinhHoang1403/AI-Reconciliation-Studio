"""Assistant gọi model trên NVIDIA NIM (chuẩn Chat Completions) để đo thử: đổi hội thoại đúng
khuôn, nối kết quả công cụ về đúng `tool_call_id`, đọc tham số công cụ và báo lỗi rõ ràng."""

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from studio import assistant, gemini_client, nvidia_client
from studio.config import settings
from studio.gemini_client import AiUnavailable


def tool_message(*calls: tuple[str, str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "reasoning_content": "nghĩ xem nên gọi gì",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
            for call_id, name, args in calls
        ],
    }


def test_tool_results_are_linked_to_their_call_ids() -> None:
    turn = nvidia_client.read_turn(
        tool_message(("c1", "list_datasets", {}), ("c2", "get_mapping", {"table": "x"}))
    )
    assert [(c.name, c.args) for c in turn.calls] == [
        ("list_datasets", {}),
        ("get_mapping", {"table": "x"}),
    ]
    conversation = [
        {"role": "user", "text": "Có tệp nào?"},
        {"role": "model", "text": "", "raw": turn.raw},
        {
            "role": "tool",
            "results": [
                {"name": "list_datasets", "response": {"count": 1}},
                {"name": "get_mapping", "response": {"error": "không có"}},
            ],
        },
    ]
    messages = nvidia_client.to_messages("chỉ dẫn", conversation)
    assert messages[0] == {"role": "system", "content": "chỉ dẫn"}
    assert messages[1] == {"role": "user", "content": "Có tệp nào?"}
    # Lượt gọi công cụ gửi lại nguyên văn, kể cả phần suy nghĩ mà model suy luận cần.
    assert messages[2]["tool_calls"][0]["id"] == "c1"
    assert messages[2]["reasoning_content"] == "nghĩ xem nên gọi gì"
    assert [(m["role"], m["tool_call_id"]) for m in messages[3:]] == [
        ("tool", "c1"),
        ("tool", "c2"),
    ]
    assert json.loads(messages[4]["content"]) == {"error": "không có"}


def test_bad_json_arguments_become_empty_so_schema_check_reports_them() -> None:
    message = tool_message(("c1", "get_mapping", {}))
    message["tool_calls"][0]["function"]["arguments"] = "{không phải json"
    assert nvidia_client.read_turn(message).calls[0].args == {}


def test_missing_key_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "nvidia_api_key", SecretStr(""))
    with pytest.raises(AiUnavailable) as error:
        nvidia_client.generate_with_tools(
            purpose="assistant", system_instruction="x", conversation=[], tools=[]
        )
    assert error.value.code == "NOT_CONFIGURED"


def test_provider_setting_picks_nvidia_and_retries_rate_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "assistant_provider", "nvidia")
    monkeypatch.setattr(settings, "nvidia_api_key", SecretStr("khoa-thu"))
    monkeypatch.setattr(nvidia_client.time, "sleep", lambda _seconds: None)
    sent: list[dict[str, Any]] = []
    answers = [
        httpx.Response(429, json={"error": "quá nhanh"}),
        httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Chào bạn."}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            },
        ),
    ]

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        sent.append(kwargs["json"])
        response = answers.pop(0)
        response.request = httpx.Request("POST", url)
        return response

    monkeypatch.setattr(nvidia_client.httpx, "post", fake_post)
    monkeypatch.setattr(
        gemini_client, "generate_with_tools", lambda **_: pytest.fail("không được gọi Gemini")
    )
    turn = assistant.ask_model([{"role": "user", "text": "chào"}], assistant.tool_declarations())
    assert turn.text == "Chào bạn." and not turn.calls
    assert len(sent) == 2  # lần đầu bị 429, thử lại thì được
    assert sent[0]["model"] == settings.nvidia_model
    assert sent[0]["tools"][0]["type"] == "function"
