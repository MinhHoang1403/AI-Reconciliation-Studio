"""Môi trường chạy Alembic: dùng chung chuỗi kết nối và mô hình bảng với ứng dụng."""

from alembic import context
from sqlalchemy import create_engine

from studio.config import settings
from studio.models import Base

target_metadata = Base.metadata


def run_migrations() -> None:
    # Cho phép kiểm thử truyền sẵn kết nối (ví dụ SQLite tạm); bình thường dùng DATABASE_URL.
    connection = context.config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
