"""LlamaParse opt-in REST adapter. Extraction always remains unverified.

Provider protocol identifiers refer to upstream API versions, not project phase names.
No cloud request occurs before policy, key and transactional allowance checks.
"""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from studio.config import Settings
from studio.contracts import WorkspacePolicy
from studio.errors import DomainError


class DocumentPage(BaseModel):
    model_config = ConfigDict(extra="allow")
    page_number: int = Field(ge=1)
    markdown: str = ""
    items: list[dict[str, Any]] = Field(default_factory=list)


class DocumentExtraction(BaseModel):
    provider_job_id: str
    pages: list[DocumentPage]
    verification_status: str = "UNVERIFIED_EXTRACTION"
    usage: dict[str, Any] = Field(default_factory=dict)


def parse_document(
    path: Path,
    config: Settings,
    policy: WorkspacePolicy,
    client: httpx.Client,
    reserve_request: Callable[[], bool],
    *,
    max_polls: int = 10,
    sleep: Callable[[float], None] = time.sleep,
) -> DocumentExtraction:
    """Submit once, poll bounded times; preserve page/items evidence, never trust OCR amounts."""
    if (
        not config.allow_cloud_parsing
        or not policy.allow_cloud_parsing
        or policy.parser_request_budget <= 0
    ):
        raise DomainError("CLOUD_PARSING_DISABLED", "Parser cloud chưa được cấp phép.")
    if not config.llama_cloud_api_key.get_secret_value():
        raise DomainError("LLAMAPARSE_KEY_MISSING", "Chưa cấu hình khóa LlamaParse.")
    if not reserve_request():
        raise DomainError("PARSER_BUDGET_EXHAUSTED", "Đã hết ngân sách parser cloud.")
    headers = {"Authorization": "Bearer " + config.llama_cloud_api_key.get_secret_value()}
    base = "https://api.cloud.llamaindex.ai/api/v2/parse"
    try:
        with path.open("rb") as stream:
            response = client.post(
                base + "/upload",
                headers=headers,
                files={"file": (path.name, stream)},
                data={"configuration": '{"tier":"agentic","version":"latest"}'},
                timeout=config.ai_timeout_seconds,
            )
        response.raise_for_status()
        job_id = str(UUID(response.json()["id"]))
        for _ in range(max_polls):
            result = client.get(
                base + "/" + job_id,
                headers=headers,
                params={"expand": "markdown,items,metadata,usage"},
                timeout=config.ai_timeout_seconds,
            )
            result.raise_for_status()
            body = result.json()
            status = body["job"]["status"]
            if status in {"FAILED", "CANCELLED"}:
                raise DomainError("LLAMAPARSE_JOB_FAILED", "Parser cloud không hoàn tất tài liệu.")
            if status == "COMPLETED":
                pages = body.get("markdown", {}).get("pages", [])
                items_pages = {
                    p["page_number"]: p.get("items", [])
                    for p in body.get("items", {}).get("pages", [])
                }
                if not pages:
                    raise DomainError(
                        "LLAMAPARSE_INVALID_EXTRACTION",
                        "Parser không trả nội dung có vị trí trang.",
                    )
                return DocumentExtraction(
                    provider_job_id=job_id,
                    pages=[
                        DocumentPage(
                            page_number=p["page_number"],
                            markdown=p.get("markdown", ""),
                            items=items_pages.get(p["page_number"], []),
                        )
                        for p in pages
                    ],
                    usage=body["job"].get("usage", {}),
                )
            if status not in {"PENDING", "RUNNING"}:
                raise DomainError("LLAMAPARSE_INVALID_RESPONSE", "Trạng thái parser không hợp lệ.")
            sleep(1)
    except DomainError:
        raise
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise DomainError(
            "LLAMAPARSE_PROVIDER_ERROR", "Không nhận được kết quả parser hợp lệ."
        ) from exc
    raise DomainError("LLAMAPARSE_POLL_TIMEOUT", "Parser chưa hoàn tất trong thời gian cho phép.")
