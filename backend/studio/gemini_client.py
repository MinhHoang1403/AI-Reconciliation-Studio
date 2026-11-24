"""Gọi Gemini và bắt câu trả lời theo khuôn JSON cố định (structured output).

Mỗi lần gọi: kiểm cấu hình, giới hạn thời gian chờ và số token, thử lại hữu hạn,
ghi số token vào DB (bảng ai_calls) và trace vào Langfuse.
Không bao giờ gọi Gemini lúc khởi động hay kiểm tra sức khỏe hệ thống (RULES R11).
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from studio import database
from studio.config import settings
from studio.models import AiCall
from studio.tracing import ai_generation

logger = logging.getLogger(__name__)


class AiUnavailable(Exception):
    """Không dùng được AI cho lần này; `code` cho biết lý do để giao diện hiển thị."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class AiReply:
    data: dict[str, Any]
    input_tokens: int
    output_tokens: int


def gemini_configured() -> bool:
    return bool(settings.gemini_api_key.get_secret_value())


def _record_call(
    purpose: str,
    table_id: uuid.UUID | None,
    status: str,
    started: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    error_code: str | None = None,
) -> None:
    with database.SessionFactory() as session:
        session.add(
            AiCall(
                purpose=purpose,
                model=settings.gemini_model,
                table_id=table_id,
                status=status,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error_code=error_code,
            )
        )
        session.commit()


def generate_json(
    *,
    purpose: str,
    system_instruction: str,
    payload: dict[str, Any],
    response_schema: dict[str, Any],
    table_id: uuid.UUID | None = None,
) -> AiReply:
    """Gửi `payload` (đã che) cho Gemini và nhận về JSON đúng `response_schema`."""
    if not gemini_configured():
        raise AiUnavailable("NOT_CONFIGURED", "Chưa có khóa GEMINI_API_KEY trong .env.")

    from google import genai
    from google.genai import errors, types

    client = genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(timeout=settings.gemini_timeout_seconds * 1000),
    )
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0,
        max_output_tokens=settings.gemini_max_output_tokens,
        response_mime_type="application/json",
        response_json_schema=response_schema,
    )
    contents = json.dumps(payload, ensure_ascii=False)
    started = time.perf_counter()
    last_error = "FAILED"
    with ai_generation(
        purpose, settings.gemini_model, payload, {"table_id": str(table_id)}
    ) as trace:
        for attempt in range(1, settings.gemini_attempts + 1):
            try:
                response = client.models.generate_content(
                    model=settings.gemini_model, contents=contents, config=config
                )
                usage = response.usage_metadata
                input_tokens = (usage.prompt_token_count or 0) if usage else 0
                output_tokens = (usage.candidates_token_count or 0) if usage else 0
                data = json.loads(response.text or "")
                trace.update(
                    output=data, usage_details={"input": input_tokens, "output": output_tokens}
                )
                _record_call(purpose, table_id, "OK", started, input_tokens, output_tokens)
                return AiReply(data=data, input_tokens=input_tokens, output_tokens=output_tokens)
            except errors.ClientError as error:  # lỗi 4xx: sai khóa, sai model… thử lại vô ích
                last_error = f"CLIENT_{error.code}"
                break
            except json.JSONDecodeError:
                last_error = "INVALID_JSON"
            except Exception as error:  # lỗi mạng, hết thời gian chờ, lỗi 5xx: thử lại
                last_error = type(error).__name__
            logger.warning("Gọi Gemini lần %s thất bại: %s", attempt, last_error)
        trace.update(level="ERROR", status_message=last_error)
    _record_call(purpose, table_id, "FAILED", started, error_code=last_error)
    raise AiUnavailable(
        "FAILED", f"Gemini không trả lời được ({last_error}); đã dùng gợi ý theo quy tắc."
    )


# ---------------------------------------------------------------- gọi có công cụ (Assistant)


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class ModelTurn:
    """Một lượt trả lời của Gemini: lời nói và/hoặc các công cụ nó muốn gọi.

    `raw` là nội dung gốc của Gemini, phải gửi lại nguyên vẹn ở lần gọi kế tiếp trong cùng
    lượt (giữ "chữ ký suy nghĩ" mà các model Gemini 3 yêu cầu khi gọi công cụ nhiều bước).
    """

    text: str
    calls: list[ToolCall]
    raw: Any = None


def _to_contents(conversation: list[dict[str, Any]]) -> list[Any]:
    """Đổi hội thoại dạng trung tính của Assistant thành nội dung của SDK google-genai."""
    from google.genai import types

    contents = []
    for entry in conversation:
        if entry.get("raw") is not None:
            contents.append(entry["raw"])
        elif entry["role"] == "tool":
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=item["name"], response=item["response"]
                        )
                        for item in entry["results"]
                    ],
                )
            )
        else:
            contents.append(
                types.Content(role=entry["role"], parts=[types.Part.from_text(text=entry["text"])])
            )
    return contents


def generate_with_tools(
    *,
    purpose: str,
    system_instruction: str,
    conversation: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> ModelTurn:
    """Gửi hội thoại cho Gemini kèm danh sách công cụ; Gemini chỉ trả tên công cụ và tham số,
    không tự chạy gì (tắt tự gọi hàm của SDK). Backend kiểm tham số rồi mới chạy công cụ."""
    if not gemini_configured():
        raise AiUnavailable("NOT_CONFIGURED", "Chưa có khóa GEMINI_API_KEY trong .env.")

    from google import genai
    from google.genai import errors, types

    client = genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(timeout=settings.gemini_timeout_seconds * 1000),
    )
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0,
        max_output_tokens=settings.gemini_max_output_tokens,
        tools=[
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=tool["name"],
                        description=tool["description"],
                        parameters_json_schema=tool["parameters"],
                    )
                    for tool in tools
                ]
            )
        ],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    contents = _to_contents(conversation)
    # Langfuse nhận hội thoại trung tính (câu chat, kết quả công cụ đã rút gọn và che).
    traced = [
        {key: value for key, value in entry.items() if key != "raw"} for entry in conversation
    ]
    started = time.perf_counter()
    last_error = "FAILED"
    with ai_generation(purpose, settings.gemini_model, traced, {}) as trace:
        for attempt in range(1, settings.gemini_attempts + 1):
            try:
                response = client.models.generate_content(
                    model=settings.gemini_model, contents=contents, config=config
                )
                usage = response.usage_metadata
                input_tokens = (usage.prompt_token_count or 0) if usage else 0
                output_tokens = (usage.candidates_token_count or 0) if usage else 0
                content = response.candidates[0].content if response.candidates else None
                parts = (content.parts or []) if content else []
                text = "".join(part.text for part in parts if part.text and not part.thought)
                calls = [
                    ToolCall(name=call.name or "", args=dict(call.args or {}))
                    for call in response.function_calls or []
                ]
                trace.update(
                    output={"text": text, "calls": [call.__dict__ for call in calls]},
                    usage_details={"input": input_tokens, "output": output_tokens},
                )
                _record_call(purpose, None, "OK", started, input_tokens, output_tokens)
                return ModelTurn(text=text.strip(), calls=calls, raw=content)
            except errors.ClientError as error:  # lỗi 4xx: thử lại vô ích
                last_error = f"CLIENT_{error.code}"
                break
            except Exception as error:  # lỗi mạng, hết thời gian chờ, lỗi 5xx: thử lại
                last_error = type(error).__name__
            logger.warning("Gọi Gemini (Assistant) lần %s thất bại: %s", attempt, last_error)
        trace.update(level="ERROR", status_message=last_error)
    _record_call(purpose, None, "FAILED", started, error_code=last_error)
    raise AiUnavailable("FAILED", f"Gemini không trả lời được ({last_error}). Hãy thử lại.")
