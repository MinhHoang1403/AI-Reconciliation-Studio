"""Cấu hình đọc từ biến môi trường (Docker Compose nạp từ `.env`)."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # Chuỗi kết nối PostgreSQL; Compose truyền vào kèm mật khẩu từ `.env`.
    database_url: str = Field(default="postgresql+psycopg://studio@postgres/studio", repr=False)

    # Thư mục lưu tệp gốc và các bảng đã đọc (volume `files` trong Docker).
    storage_root: Path = Path("/data/files")
    # Giới hạn mỗi tệp tải lên: 50 MB (quyết định 2026-11-20).
    max_upload_bytes: int = 50 * 1024 * 1024

    # Khóa Gemini nằm trong `.env`, không bao giờ trả ra API hay ghi log (RULES R14).
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.5-flash-lite"

    # Commit Git của source đã build image, để biết đang chạy bản nào.
    studio_revision: str = "unknown"


settings = Settings()
