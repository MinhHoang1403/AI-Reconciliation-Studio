"""LlamaParse opt-in REST adapter. Extraction always remains unverified.

Provider protocol identifiers refer to upstream API versions, not project phase names.
No cloud request occurs before policy, key and transactional allowance checks.
"""

import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from studio.config import Settings
from studio.contracts import ArtifactRef, Contract, FileArtifact, WorkspacePolicy
from studio.errors import DomainError

DOCUMENT_PARSER_REVISION = "llamaparse-cost-effective-1"
DOCUMENT_MAX_PAGES = 2
DOCUMENT_RESERVED_CREDITS = 6  # official cost_effective: 3 credits/page, at most 2 pages


def provider_job_id(value: Any) -> str:
    """Upstream IDs are opaque (including pjb-*), not necessarily UUIDs; prevent path injection."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise DomainError("LLAMAPARSE_INVALID_RESPONSE", "Job ID parser không hợp lệ.")
    return value


def verify_parser_account(client: httpx.Client, config: Settings) -> int:
    """Read documented account APIs, fail closed unless unexpired credits cover one bounded job.

    Read-only preflight never creates a parse job. Do not expose account IDs or response bodies.
    """
    try:
        headers = {"Authorization": "Bearer " + config.llama_cloud_api_key.get_secret_value()}
        base = "https://api.cloud.llamaindex.ai"
        response = client.get(
            base + "/api/v2/organizations",
            headers=headers,
            params={"page_size": 10},
            timeout=config.ai_timeout_seconds,
        )
        response.raise_for_status()
        organizations = response.json()["items"]
        if len(organizations) != 1:
            raise ValueError("ambiguous account")
        response = client.get(
            base + "/api/v1/organizations/" + organizations[0]["id"] + "/usage",
            headers=headers,
            timeout=config.ai_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if data["plan"].get("is_payment_failed") or data["usage"].get("active_alerts"):
            raise ValueError("account restricted")
        remaining = sum(
            int(grant["remaining_balance"])
            for grant in data["usage"]["active_free_credits_usage"]
            if datetime.fromisoformat(grant["expires_at"].replace("Z", "+00:00"))
            > datetime.now(UTC)
        )
        if remaining < DOCUMENT_RESERVED_CREDITS:
            raise ValueError("insufficient confirmed credits")
        return remaining
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise DomainError(
            "PARSER_CREDITS_NOT_VERIFIED",
            "Chưa xác minh được credits LlamaParse đủ cho tài liệu giới hạn.",
        ) from exc


class DocumentPage(BaseModel):
    model_config = ConfigDict(extra="allow")
    page_number: int = Field(ge=1)
    markdown: str = ""
    items: list[dict[str, Any]] = Field(default_factory=list)


class DocumentExtraction(BaseModel):
    provider_job_id: str
    pages: list[DocumentPage]
    verification_status: Literal["UNVERIFIED_EXTRACTION"] = "UNVERIFIED_EXTRACTION"
    usage: dict[str, Any] = Field(default_factory=dict)


class DocumentArtifact(Contract):
    artifact: ArtifactRef
    source_file: FileArtifact
    extraction: DocumentExtraction
    warnings: list[str] = Field(default_factory=lambda: ["UNVERIFIED_EXTRACTION"])


def parse_document(
    path: Path,
    config: Settings,
    policy: WorkspacePolicy,
    client: httpx.Client,
    reserve_request: Callable[[], bool],
    *,
    max_polls: int = 10,
    sleep: Callable[[float], None] = time.sleep,
    resume_job_id: str | None = None,
    on_job_created: Callable[[str], None] | None = None,
    filename: str | None = None,
) -> DocumentExtraction:
    """Submit once, poll bounded times; preserve page/items evidence, never trust OCR amounts."""
    if (
        not config.allow_cloud_parsing
        or not policy.allow_cloud_parsing
        or (resume_job_id is None and policy.parser_request_budget <= 0)
    ):
        raise DomainError("CLOUD_PARSING_DISABLED", "Parser cloud chưa được cấp phép.")
    if not config.llama_cloud_api_key.get_secret_value():
        raise DomainError("LLAMAPARSE_KEY_MISSING", "Chưa cấu hình khóa LlamaParse.")
    if not 1 <= max_polls <= 60:
        raise DomainError("PARSER_POLL_LIMIT", "Giới hạn polling phải từ 1 đến 60.")
    if resume_job_id is None and config.cloud_parser_request_budget <= 0:
        raise DomainError("PARSER_BUDGET_EXHAUSTED", "Ngân sách parser toàn hệ thống bằng 0.")
    headers = {"Authorization": "Bearer " + config.llama_cloud_api_key.get_secret_value()}
    base = "https://api.cloud.llamaindex.ai/api/v2/parse"
    try:
        if resume_job_id is None:
            if not reserve_request():
                raise DomainError("PARSER_BUDGET_EXHAUSTED", "Đã hết ngân sách parser cloud.")
            with path.open("rb") as stream:
                response = client.post(
                    base + "/upload",
                    headers=headers,
                    files={"file": (filename or path.name, stream)},
                    data={
                        "configuration": json.dumps(
                            {
                                "tier": "cost_effective",
                                "version": "latest",
                                "page_ranges": {"max_pages": DOCUMENT_MAX_PAGES},
                            }
                        )
                    },
                    timeout=config.ai_timeout_seconds,
                )
            response.raise_for_status()
            job_id = provider_job_id(response.json()["id"])
            if on_job_created:
                on_job_created(job_id)
        else:
            job_id = provider_job_id(resume_job_id)
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
                if (
                    not pages
                    or len(pages) > DOCUMENT_MAX_PAGES
                    or any(p["page_number"] not in range(1, DOCUMENT_MAX_PAGES + 1) for p in pages)
                ):
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
