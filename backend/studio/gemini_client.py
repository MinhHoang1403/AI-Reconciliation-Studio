"""Gọi Gemini: câu trả lời theo khuôn JSON (structured output) hoặc gọi công cụ (Assistant).

Mỗi lần gọi: kiểm cấu hình, giới hạn thời gian chờ và số token, ghi số token vào DB (bảng
ai_calls) và trace vào Langfuse. Lỗi tạm thời của Gemini (408, 429 quá giới hạn tốc độ, 5xx
máy chủ quá tải) được thử lại bằng cơ chế sẵn có của SDK google-genai (`HttpRetryOptions`):
chờ tăng dần theo cấp số nhân có ngẫu nhiên hóa, đúng khuyến nghị của Google cho lỗi 429/503
(https://ai.google.dev/gemini-api/docs/troubleshooting). Lỗi 4xx khác (sai khóa, sai model)
không thử lại. Không bao giờ gọi Gemini lúc khởi động hay kiểm tra sức khỏe (RULES R11).
"""

import json
import logging
import threading
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


# Mã HTTP được thử lại: hết thời gian chờ, quá giới hạn tốc độ, lỗi máy chủ Gemini.
RETRY_STATUS_CODES = (408, 429, 500, 502, 503, 504)
RETRY_INITIAL_DELAY = 1.0  # giây chờ trước lần thử lại đầu tiên, sau đó nhân đôi
RETRY_MAX_DELAY = 8.0
# Số lần gọi Gemini chạy cùng lúc. Tải nhiều tệp một lúc làm mỗi bảng tự gọi gợi ý ánh xạ và
# gợi ý sửa ô song song; gửi dồn như vậy dễ chạm giới hạn số yêu cầu mỗi phút (lỗi 429) của
# khóa. Các lần gọi vượt quá sẽ xếp hàng chờ, không bị bỏ.
MAX_CONCURRENT_CALLS = 2
_slots = threading.BoundedSemaphore(MAX_CONCURRENT_CALLS)


def _client() -> Any:
    """Client Gemini có giới hạn thời gian chờ và thử lại giãn cách cho lỗi tạm thời."""
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(
            timeout=settings.gemini_timeout_seconds * 1000,
            retry_options=types.HttpRetryOptions(
                attempts=settings.gemini_attempts,
                initial_delay=RETRY_INITIAL_DELAY,
                max_delay=RETRY_MAX_DELAY,
                exp_base=2.0,
                jitter=1.0,
                http_status_codes=list(RETRY_STATUS_CODES),
            ),
        ),
    )


def _error_code(error: Exception) -> str:
    """Mã lỗi ngắn để ghi vào ai_calls và Langfuse (không chứa nội dung hay khóa)."""
    from google.genai import errors

    if isinstance(error, errors.ClientError):
        return f"CLIENT_{error.code}"
    if isinstance(error, errors.ServerError):
        return f"SERVER_{error.code}"
    if isinstance(error, json.JSONDecodeError):
        return "INVALID_JSON"
    return type(error).__name__


def _generate(
    purpose: str,
    trace_input: Any,
    table_id: uuid.UUID | None,
    request: Any,
    read: Any,
) -> Any:
    """Một lần gọi Gemini dùng chung: thử lại (trong SDK), ghi token, trace và lỗi.

    `request(client)` gửi yêu cầu; `read(response)` đọc câu trả lời thành kết quả và trả về
    (kết quả, phần ghi vào Langfuse). Lỗi nào cũng thành `AiUnavailable` để tính năng gọi
    báo đúng lỗi cho người dùng (R11: không giấu lỗi)."""
    if not gemini_configured():
        raise AiUnavailable("NOT_CONFIGURED", "Chưa có khóa GEMINI_API_KEY trong .env.")
    started = time.perf_counter()
    with ai_generation(
        purpose, settings.gemini_model, trace_input, {"table_id": str(table_id)}
    ) as trace:
        try:
            with _slots:  # xếp hàng nếu đã có đủ lần gọi đang chạy
                response = request(_client())
            usage = response.usage_metadata
            input_tokens = (usage.prompt_token_count or 0) if usage else 0
            output_tokens = (usage.candidates_token_count or 0) if usage else 0
            result, traced = read(response)
        except Exception as error:
            code = _error_code(error)
            logger.warning("Gọi Gemini (%s) thất bại: %s", purpose, code)
            trace.update(level="ERROR", status_message=code)
            _record_call(purpose, table_id, "FAILED", started, error_code=code)
            raise AiUnavailable("FAILED", f"Gemini không trả lời được ({code}).") from error
        trace.update(output=traced, usage_details={"input": input_tokens, "output": output_tokens})
        _record_call(purpose, table_id, "OK", started, input_tokens, output_tokens)
        return result


def generate_json(
    *,
    purpose: str,
    system_instruction: str,
    payload: dict[str, Any],
    response_schema: dict[str, Any],
    table_id: uuid.UUID | None = None,
) -> AiReply:
    """Gửi `payload` (đã che) cho Gemini và nhận về JSON đúng `response_schema`."""
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0,
        max_output_tokens=settings.gemini_max_output_tokens,
        response_mime_type="application/json",
        response_json_schema=response_schema,
    )
    contents = json.dumps(payload, ensure_ascii=False)

    def read(response: Any) -> tuple[AiReply, Any]:
        data = json.loads(response.text or "")
        usage = response.usage_metadata
        reply = AiReply(
            data=data,
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(usage.candidates_token_count or 0) if usage else 0,
        )
        return reply, data

    reply: AiReply = _generate(
        purpose,
        payload,
        table_id,
        lambda client: client.models.generate_content(
            model=settings.gemini_model, contents=contents, config=config
        ),
        read,
    )
    return reply


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
    from google.genai import types

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
    contents = _to_contents(conversation) if gemini_configured() else []
    # Langfuse nhận hội thoại trung tính (câu chat, kết quả công cụ đã rút gọn và che).
    traced = [{key: val for key, val in entry.items() if key != "raw"} for entry in conversation]

    def read(response: Any) -> tuple[ModelTurn, Any]:
        content = response.candidates[0].content if response.candidates else None
        parts = (content.parts or []) if content else []
        text = "".join(part.text for part in parts if part.text and not part.thought)
        calls = [
            ToolCall(name=call.name or "", args=dict(call.args or {}))
            for call in response.function_calls or []
        ]
        turn = ModelTurn(text=text.strip(), calls=calls, raw=content)
        return turn, {"text": turn.text, "calls": [call.__dict__ for call in calls]}

    turn: ModelTurn = _generate(
        purpose,
        traced,
        None,
        lambda client: client.models.generate_content(
            model=settings.gemini_model, contents=contents, config=config
        ),
        read,
    )
    return turn
