"""Điểm vào FastAPI: khai báo ứng dụng và các API kiểm tra trạng thái."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Response, status
from pydantic import BaseModel

from studio import database, ingestion
from studio.assistant_api import router as assistant_router
from studio.cleaning_api import router as cleaning_router
from studio.config import settings
from studio.datasets_api import router as datasets_router
from studio.mapping_api import router as mapping_router
from studio.recon_api import router as recon_router
from studio.tracing import langfuse_configured


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Việc đọc tệp dở dang từ lần chạy trước không thể tiếp tục; đánh dấu để người dùng đọc lại.
    ingestion.recover_interrupted()
    yield


app = FastAPI(
    title="AI Reconciliation Studio", docs_url="/api/docs", openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.include_router(datasets_router)
app.include_router(mapping_router)
app.include_router(cleaning_router)
app.include_router(recon_router)
app.include_router(assistant_router)

# Trạng thái cấu hình của một provider. Chỉ kiểm cấu hình cục bộ, không gọi ra ngoài
# (RULES R11: không tự gọi API trả phí khi kiểm tra sức khỏe hệ thống).
type ProviderState = Literal["CONFIGURED", "NEEDS_CONFIGURATION"]


class HealthReply(BaseModel):
    status: Literal["ok", "unavailable"]


class ProviderStatus(BaseModel):
    name: str
    model: str
    state: ProviderState


class SystemStatus(BaseModel):
    revision: str
    database: Literal["ok", "unavailable"]
    gemini: ProviderStatus
    langfuse: ProviderStatus


@app.get("/api/health")
def health() -> HealthReply:
    """Backend còn sống hay không; Docker dùng để đánh dấu container healthy."""
    return HealthReply(status="ok")


@app.get("/api/ready")
def ready(response: Response) -> HealthReply:
    """Backend đã sẵn sàng phục vụ chưa: cần kết nối được PostgreSQL."""
    if database.database_is_reachable():
        return HealthReply(status="ok")
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthReply(status="unavailable")


@app.get("/api/status")
def system_status() -> SystemStatus:
    """Tóm tắt trạng thái hệ thống để giao diện hiển thị."""
    gemini_state: ProviderState = (
        "CONFIGURED" if settings.gemini_api_key.get_secret_value() else "NEEDS_CONFIGURATION"
    )
    return SystemStatus(
        revision=settings.studio_revision,
        database="ok" if database.database_is_reachable() else "unavailable",
        gemini=ProviderStatus(name="Gemini", model=settings.gemini_model, state=gemini_state),
        langfuse=ProviderStatus(
            name="Langfuse", model=settings.langfuse_base_url,
            state="CONFIGURED" if langfuse_configured() else "NEEDS_CONFIGURATION",
        ),
    )
