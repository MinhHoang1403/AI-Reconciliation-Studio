"""Central configuration; provider addresses and credentials never enter browser DTOs."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://studio@postgres/studio"
    storage_root: Path = Path("runtime/storage")
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
    ai_timeout_seconds: float = Field(default=45, ge=1, le=120)
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.5-flash-lite"
    allow_external_ai: bool = False
    external_ai_request_budget: int = Field(default=0, ge=0)
    llama_cloud_api_key: SecretStr = SecretStr("")
    allow_cloud_parsing: bool = False
    cloud_parser_request_budget: int = Field(default=0, ge=0)
    worker_lease_seconds: int = Field(default=300, ge=120)
    worker_poll_seconds: float = 1

    @property
    def origins(self) -> set[str]:
        return set(self.allowed_origins.split(","))


settings = Settings()
