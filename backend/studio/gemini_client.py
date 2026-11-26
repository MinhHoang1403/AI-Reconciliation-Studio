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
import re
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from studio import data_docs, database
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
) -> uuid.UUID:
    with database.SessionFactory() as session:
        call = AiCall(
                purpose=purpose,
                model=settings.gemini_model,
                table_id=table_id,
                status=status,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error_code=error_code,
            )
        session.add(call)
        session.commit()
        return call.id


# Mã HTTP được thử lại: hết thời gian chờ, quá giới hạn tốc độ, lỗi máy chủ Gemini.
RETRY_STATUS_CODES = (408, 429, 500, 502, 503, 504)
RETRY_INITIAL_DELAY = 1.0  # giây chờ trước lần thử lại đầu tiên, sau đó nhân đôi
RETRY_MAX_DELAY = 8.0
# Số lần gọi Gemini chạy cùng lúc. Tải nhiều tệp một lúc làm mỗi bảng tự gọi gợi ý ánh xạ và
# gợi ý sửa ô song song; gửi dồn như vậy dễ chạm giới hạn số yêu cầu mỗi phút (lỗi 429) của
# khóa. Các lần gọi vượt quá sẽ xếp hàng chờ, không bị bỏ.
MAX_CONCURRENT_CALLS = 2
_slots = threading.BoundedSemaphore(MAX_CONCURRENT_CALLS)
# Gợi ý chạy nền (ánh xạ cột, gợi ý sửa ô) đã có phương án thay thế khi AI lỗi (gợi ý theo quy
# tắc, ô vẫn chờ người dùng sửa), nên chỉ thử 2 lần để khi Gemini quá tải người dùng không phải
# chờ lâu. Assistant và giải thích (người dùng đang chờ, không có phương án thay) dùng
# settings.gemini_attempts.
BACKGROUND_ATTEMPTS = 2


def _client(attempts: int) -> Any:
    """Client Gemini có giới hạn thời gian chờ và thử lại giãn cách cho lỗi tạm thời."""
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(
            timeout=settings.gemini_timeout_seconds * 1000,
            retry_options=types.HttpRetryOptions(
                attempts=attempts,
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


def explain_error(error: Exception, code: str) -> tuple[str, str]:
    """Mã và câu tiếng Việt dễ hiểu cho người dùng từ lỗi của Gemini.

    Lỗi 429 có hai loại: hết hạn mức trong ngày (gói miễn phí giới hạn số yêu cầu mỗi ngày;
    phải chờ sang ngày hoặc dùng khóa trả phí) và vượt giới hạn mỗi phút (chờ ít phút)."""
    from google.genai import errors

    if isinstance(error, errors.ClientError) and error.code == 429:
        text = str(getattr(error, "message", "") or error)
        if re.search(r"per ?day|PerDay", text, re.IGNORECASE):
            wait = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?", text)
            hours = int(wait.group(1) or 0) if wait else 0
            minutes = int(wait.group(2) or 0) if wait else 0
            later = (
                f" Có thể dùng lại sau khoảng {hours} giờ {minutes} phút."
                if hours or minutes
                else " Có thể dùng lại vào ngày mai."
            )
            return (
                "QUOTA_DAY",
                "Khóa Gemini đã dùng hết số yêu cầu được phép trong ngày (giới hạn của gói "
                f"miễn phí).{later} Muốn dùng tiếp ngay thì cần khóa có trả phí.",
            )
        return (
            "QUOTA_MINUTE",
            "Gemini đang giới hạn số yêu cầu mỗi phút của khóa này; hãy thử lại sau ít phút.",
        )
    if code.startswith("SERVER_"):
        return "FAILED", f"Máy chủ Gemini đang quá tải ({code}); hãy thử lại sau ít phút."
    return "FAILED", f"Gemini không trả lời được ({code})."


def _generate(
    purpose: str,
    trace_input: Any,
    table_id: uuid.UUID | None,
    request: Any,
    read: Any,
    attempts: int | None = None,
    request_doc: dict[str, Any] | None = None,
) -> Any:
    """Một lần gọi Gemini dùng chung: thử lại (trong SDK), ghi token, trace và lỗi.

    `request(client)` gửi yêu cầu; `read(response)` đọc câu trả lời thành kết quả và trả về
    (kết quả, phần ghi vào Langfuse). Lỗi nào cũng thành `AiUnavailable` để tính năng gọi
    báo đúng lỗi cho người dùng (R11: không giấu lỗi)."""
    if not gemini_configured():
        raise AiUnavailable("NOT_CONFIGURED", "Chưa có khóa GEMINI_API_KEY trong .env.")
    # Xếp hàng trước, rồi mới bắt đầu đo: thời gian ghi vào ai_calls và Langfuse là thời gian
    # gọi Gemini thật (kể cả các lần thử lại), không gồm lúc chờ lượt.
    with _slots, ai_generation(
        purpose, settings.gemini_model, trace_input, {"table_id": str(table_id)}
    ) as trace:
        started = time.perf_counter()
        try:
            response = request(_client(attempts or settings.gemini_attempts))
            usage = response.usage_metadata
            input_tokens = (usage.prompt_token_count or 0) if usage else 0
            output_tokens = (usage.candidates_token_count or 0) if usage else 0
            result, traced = read(response)
        except Exception as error:
            code = _error_code(error)
            logger.warning("Gọi Gemini (%s) thất bại: %s", purpose, code)
            trace.update(level="ERROR", status_message=code)
            call_id = _record_call(purpose, table_id, "FAILED", started, error_code=code)
            _write_doc(call_id, purpose, table_id, started, request_doc, None, "FAILED", code)
            raise AiUnavailable(*explain_error(error, code)) from error
        trace.update(output=traced, usage_details={"input": input_tokens, "output": output_tokens})
        call_id = _record_call(purpose, table_id, "OK", started, input_tokens, output_tokens)
        _write_doc(
            call_id, purpose, table_id, started, request_doc, traced, "OK", None,
            input_tokens, output_tokens,
        )
        return result


def _write_doc(
    call_id: uuid.UUID,
    purpose: str,
    table_id: uuid.UUID | None,
    started: float,
    request_doc: dict[str, Any] | None,
    response: Any,
    status: str,
    error_code: str | None,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Lưu bằng chứng của lần gọi ra data-docs/runtime/ai-calls (nếu bật): đúng nội dung đã
    gửi (đã che), khuôn JSON hoặc công cụ, câu trả lời; khớp với dòng ai_calls qua ai_call_id.
    Không có khóa API: khóa chỉ nằm trong client SDK, không bao giờ vào request_doc."""
    data_docs.write_ai_call(
        {
            "ai_call_id": str(call_id),
            "purpose": purpose,
            "model": settings.gemini_model,
            "table_id": str(table_id) if table_id else None,
            "status": status,
            "error_code": error_code,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "tokens": {"input": input_tokens, "output": output_tokens},
            "request": request_doc,
            "response": response,
        }
    )


def generate_json(
    *,
    purpose: str,
    system_instruction: str,
    payload: dict[str, Any],
    response_schema: dict[str, Any],
    table_id: uuid.UUID | None = None,
    attempts: int | None = None,
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
        attempts,
        {
            "kind": "structured_output",
            "system_instruction": system_instruction,
            "input": payload,
            "response_schema": response_schema,
            "config": {"temperature": 0, "max_output_tokens": settings.gemini_max_output_tokens},
        },
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
        None,
        {
            "kind": "function_calling",
            "system_instruction": system_instruction,
            "conversation": traced,
            "tools": tools,
            "config": {
                "temperature": 0,
                "max_output_tokens": settings.gemini_max_output_tokens,
                "automatic_function_calling": False,
            },
        },
    )
    return turn
