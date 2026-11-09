"""Central configuration; provider addresses and credentials never enter browser DTOs."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AGENT_UPLOAD_EXTENSIONS = (".csv", ".xlsx")
ModelChoice = Literal["GEMINI", "QWEN_8B", "QWEN_27B"]
OLLAMA_MODELS: dict[ModelChoice, str] = {"QWEN_8B": "qwen3:8b", "QWEN_27B": "qwen3.8:27b"}


def request_limit_reached(used: int, ceiling: int | None) -> bool:
    """None bỏ trần số lượt nội bộ; không cấp quyền cloud hoặc thay quota provider."""
    return ceiling is not None and used >= ceiling


def remaining_requests(*limits: tuple[int | None, int]) -> int | None:
    """Lấy giới hạn còn hiệu lực; null chỉ khi mọi trần đều được bỏ rõ ràng."""
    finite = [max(0, ceiling - used) for ceiling, used in limits if ceiling is not None]
    return min(finite) if finite else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = Field(default="postgresql+psycopg://studio@postgres/studio", repr=False)
    storage_root: Path = Path("runtime/storage")
    purge_test_schema: str = ""
    session_secret: SecretStr = SecretStr("")
    session_ttl_seconds: int = Field(default=28800, ge=60, le=86400)
    local_demo_access: bool = False
    demo_proof_path: Path = Path("/run/studio/demo-proof.json")
    instance_path: Path = Path("/run/studio/instance")
    allowed_origins: str = "http://127.0.0.1:18180,http://localhost:18180"
    access_token: SecretStr = SecretStr("")
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    max_upload_files: int = Field(default=10, ge=1, le=20)
    max_rows: int = Field(default=100000, ge=1, le=1000000)
    max_columns: int = Field(default=200, ge=1, le=1000)
    max_zip_bytes: int = 100 * 1024 * 1024
    qwen_base_url: str = ""
    qwen_model: str = "knowledge"
    qwen_enabled: bool = True
    mapping_ai_provider: Literal["QWEN", "GEMINI"] = "GEMINI"
    ai_timeout_seconds: float = Field(default=45, ge=1, le=120)
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.5-flash-lite"
    ollama_url: Literal["", "http://127.0.0.1:11434", "http://host.docker.internal:11434"] = ""
    ollama_choice: Literal["QWEN_8B", "QWEN_27B"] = "QWEN_8B"
    assistant_default_model: ModelChoice = "GEMINI"
    ollama_timeout_seconds: float = Field(default=90, ge=5, le=100)
    ollama_context: int = Field(default=8192, ge=2048, le=32768)
    allow_external_ai: bool = False
    external_ai_request_budget: int | None = Field(default=0, ge=0)
    assistant_cloud_enabled: bool = False
    assistant_request_budget: int | None = Field(default=0, ge=0)
    planner_request_budget: int | None = Field(default=2, ge=0, le=50)
    agent_cloud_enabled: bool = False
    agent_request_budget: int | None = Field(default=0, ge=0)
    agent_max_steps: int = Field(default=12, ge=1, le=12)
    # One routing + three source proposals + three human-triggered corrections
    # requires seven calls; keep the existing hard safety ceiling of eight.
    agent_max_model_calls: int = Field(default=8, ge=0, le=8)
    agent_max_tool_calls: int = Field(default=5, ge=1, le=5)
    agent_query_timeout_seconds: float = Field(default=5.0, ge=0.1, le=30.0)
    llama_cloud_api_key: SecretStr = SecretStr("")
    allow_cloud_parsing: bool = False
    cloud_parser_request_budget: int = Field(default=0, ge=0)
    cloud_parser_credit_budget: int = Field(default=0, ge=0, le=20)
    worker_lease_seconds: int = Field(default=300, ge=120)
    worker_poll_seconds: float = 1

    @field_validator(
        "external_ai_request_budget",
        "assistant_request_budget",
        "planner_request_budget",
        "agent_request_budget",
        mode="before",
    )
    @classmethod
    def parse_request_ceiling(cls, value: object) -> object:
        return None if isinstance(value, str) and value.strip().lower() == "unlimited" else value

    @model_validator(mode="after")
    def unlimited_is_local_only(self) -> "Settings":
        if not self.local_demo_access and any(
            value is None
            for value in (
                self.external_ai_request_budget,
                self.assistant_request_budget,
                self.planner_request_budget,
                self.agent_request_budget,
            )
        ):
            raise ValueError("Unlimited AI request ceilings require explicit local demo mode")
        return self

    @property
    def agent_max_upload_files(self) -> int:
        """Giới hạn đính kèm chat, dùng chung cho API và kiểm tra upload."""
        return min(self.max_upload_files, 5)

    @property
    def origins(self) -> set[str]:
        return set(self.allowed_origins.split(","))


settings = Settings()
