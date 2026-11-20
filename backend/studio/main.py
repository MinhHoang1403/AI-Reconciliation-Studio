"""Điểm vào FastAPI: khai báo ứng dụng và các API kiểm tra trạng thái."""

from typing import Literal

from fastapi import FastAPI, Response, status
from pydantic import BaseModel

from studio import database
from studio.config import settings

app = FastAPI(
    title="AI Reconciliation Studio", docs_url="/api/docs", openapi_url="/api/openapi.json"
)

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
    )
