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
    # Mỗi lần gọi Gemini: chờ tối đa bao lâu, trả lời tối đa bao nhiêu token, và tổng số lần
    # gửi (lần đầu + thử lại giãn cách 1 giây, 2 giây… khi gặp lỗi 408/429/5xx).
    gemini_timeout_seconds: int = Field(default=45, ge=5, le=300)
    gemini_max_output_tokens: int = Field(default=4096, ge=256, le=32768)
    gemini_attempts: int = Field(default=4, ge=1, le=6)

    # Langfuse ghi dấu vết từng lần gọi AI. Thiếu khóa thì không ghi, phần còn lại vẫn chạy.
    langfuse_public_key: str = ""
    langfuse_secret_key: SecretStr = SecretStr("")
    langfuse_base_url: str = "http://host.docker.internal:3000"

    # Commit Git của source đã build image, để biết đang chạy bản nào.
    studio_revision: str = "unknown"
    # Thư mục data-docs phần chạy (nhật ký gọi Gemini, catalog động). Không đặt thì không ghi
    # tệp (mặc định khi chạy kiểm thử); container đặt /data/data-docs, gắn ra data-docs/runtime.
    data_docs_dir: Path | None = None


settings = Settings()
