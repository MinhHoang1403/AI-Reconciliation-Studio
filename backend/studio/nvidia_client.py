"""Gọi model trên NVIDIA NIM (build.nvidia.com) cho vòng gọi công cụ của AI Assistant.

Dùng để đo thử model khác Gemini trên cùng bộ câu lệnh mẫu (Owner yêu cầu 25/11/2026). Chỉ
dùng khi `.env` đặt `ASSISTANT_PROVIDER=nvidia`; mặc định Assistant vẫn gọi Gemini.

NVIDIA NIM nhận yêu cầu theo chuẩn Chat Completions của OpenAI tại
`https://integrate.api.nvidia.com/v1/chat/completions` (công cụ khai báo dạng
`{"type": "function", "function": {...}}`, model trả `tool_calls`, kết quả công cụ gửi lại bằng
tin nhắn `role: "tool"` kèm `tool_call_id`). Gửi bằng `httpx` (đã có sẵn vì SDK google-genai
dùng nó), không thêm thư viện OpenAI (R5).

Gói miễn phí giới hạn khoảng 40 yêu cầu mỗi phút, nên lỗi 429 và 5xx được thử lại giãn cách
1 → 2 → 4 giây như với Gemini. Điều khoản gói thử của NVIDIA cho phép dùng câu hỏi và câu trả
lời để cải tiến sản phẩm; Assistant vốn chỉ gửi dữ liệu đã che (docs/DECISIONS.md 2026-11-24).
"""

import json
import logging
import time
from typing import Any

import httpx

from studio.config import settings
from studio.gemini_client import (
    AiUnavailable,
    ModelTurn,
    ToolCall,
    _record_call,
    _slots,
)
from studio.tracing import ai_generation

logger = logging.getLogger(__name__)

RETRY_STATUS_CODES = (408, 429, 500, 502, 503, 504)


def nvidia_configured() -> bool:
    return bool(settings.nvidia_api_key.get_secret_value())


def to_messages(
    system_instruction: str, conversation: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Đổi hội thoại dạng trung tính của Assistant thành tin nhắn chuẩn Chat Completions.

    Lượt model có gọi công cụ được gửi lại nguyên văn (`raw`, gồm cả `tool_calls` và phần suy
    nghĩ nếu model có), để mỗi kết quả công cụ nối được về đúng `tool_call_id` của nó."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_instruction}]
    pending_ids: list[str] = []
    for entry in conversation:
        if isinstance(entry.get("raw"), dict):
            messages.append(entry["raw"])
            pending_ids = [call["id"] for call in entry["raw"].get("tool_calls") or []]
        elif entry["role"] == "tool":
            # Kết quả công cụ theo đúng thứ tự các lần gọi của lượt model ngay trước.
            for index, item in enumerate(entry["results"]):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": pending_ids[index] if index < len(pending_ids) else "",
                        "content": json.dumps(item["response"], ensure_ascii=False, default=str),
                    }
                )
            pending_ids = []
        else:
            role = "assistant" if entry["role"] == "model" else "user"
            messages.append({"role": role, "content": entry.get("text") or ""})
    return messages


def read_turn(message: dict[str, Any]) -> ModelTurn:
    """Đọc tin nhắn trả lời của model thành lời nói và các lần gọi công cụ."""
    calls = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        raw_args = function.get("arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except json.JSONDecodeError:
            # Tham số không phải JSON: để trống, bước kiểm schema sẽ báo lỗi cho model sửa.
            args = {}
        calls.append(ToolCall(name=function.get("name") or "", args=args or {}))
    raw = {
        "role": "assistant",
        "content": message.get("content") or "",
        **({"tool_calls": message["tool_calls"]} if message.get("tool_calls") else {}),
        # Model suy luận (ví dụ Kimi) cần nhận lại phần suy nghĩ ở bước gọi công cụ kế tiếp.
        **(
            {"reasoning_content": message["reasoning_content"]}
            if message.get("reasoning_content")
            else {}
        ),
    }
    return ModelTurn(text=(message.get("content") or "").strip(), calls=calls, raw=raw)


def _post(body: dict[str, Any]) -> dict[str, Any]:
    """Gửi một yêu cầu, thử lại giãn cách cho lỗi tạm thời (408, 429, 5xx, mất kết nối)."""
    headers = {"Authorization": f"Bearer {settings.nvidia_api_key.get_secret_value()}"}
    url = settings.nvidia_base_url.rstrip("/") + "/chat/completions"
    delay = 1.0
    for attempt in range(1, settings.gemini_attempts + 1):
        try:
            response = httpx.post(
                url, json=body, headers=headers, timeout=settings.nvidia_timeout_seconds
            )
        except httpx.TransportError:
            if attempt == settings.gemini_attempts:
                raise
        else:
            if (
                response.status_code not in RETRY_STATUS_CODES
                or attempt == settings.gemini_attempts
            ):
                response.raise_for_status()
                result: dict[str, Any] = response.json()
                return result
        time.sleep(min(delay, 8.0))
        delay *= 2
    raise RuntimeError("không bao giờ tới đây")


def _error_code(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        return f"SERVER_{status}" if status >= 500 else f"CLIENT_{status}"
    if isinstance(error, httpx.TimeoutException):
        return "TIMEOUT"
    return type(error).__name__.upper()


def generate_with_tools(
    *,
    purpose: str,
    system_instruction: str,
    conversation: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> ModelTurn:
    """Cùng vai trò `gemini_client.generate_with_tools`: model chỉ trả tên công cụ và tham số,
    backend kiểm tham số rồi mới chạy. Ghi token vào `ai_calls` và trace vào Langfuse."""
    if not nvidia_configured():
        raise AiUnavailable("NOT_CONFIGURED", "Chưa có khóa NVIDIA_API_KEY trong .env.")
    body = {
        "model": settings.nvidia_model,
        "messages": to_messages(system_instruction, conversation),
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in tools
        ],
        "temperature": 0,
        "max_tokens": settings.nvidia_max_output_tokens,
    }
    traced = [{key: val for key, val in entry.items() if key != "raw"} for entry in conversation]
    with _slots, ai_generation(purpose, settings.nvidia_model, traced, {}) as trace:
        started = time.perf_counter()
        try:
            data = _post(body)
            turn = read_turn(data["choices"][0]["message"])
        except Exception as error:
            code = _error_code(error)
            logger.warning("Gọi NVIDIA (%s) thất bại: %s", purpose, code)
            trace.update(level="ERROR", status_message=code)
            _record_call(
                purpose, None, "FAILED", started, error_code=code, model=settings.nvidia_model
            )
            raise AiUnavailable(code, f"Model NVIDIA không trả lời được ({code}).") from error
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        trace.update(
            output={"text": turn.text, "calls": [call.__dict__ for call in turn.calls]},
            usage_details={"input": input_tokens, "output": output_tokens},
        )
        _record_call(
            purpose, None, "OK", started, input_tokens, output_tokens, model=settings.nvidia_model
        )
        return turn
