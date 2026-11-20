"""Nâng cấu trúc cơ sở dữ liệu lên bản mới nhất bằng Alembic.

Cấu hình Alembic viết bằng code thay cho tệp alembic.ini, để không phụ thuộc bảng mã
của hệ điều hành khi đọc tệp cấu hình (Windows mặc định không phải UTF-8).
Docker chạy `python -m studio.migrate` trước khi khởi động API.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def alembic_config(connection: Connection | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def upgrade_to_latest(connection: Connection | None = None) -> None:
    command.upgrade(alembic_config(connection), "head")


if __name__ == "__main__":
    upgrade_to_latest()
