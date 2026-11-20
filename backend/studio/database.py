"""Kết nối cơ sở dữ liệu dùng chung cho cả ứng dụng."""

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from studio.config import settings

# `pool_pre_ping` thử kết nối trước khi dùng, tránh lỗi khi PostgreSQL vừa khởi động lại.
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionFactory = sessionmaker(engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Phiên làm việc với DB cho mỗi request API; tự đóng khi request kết thúc."""
    with SessionFactory() as session:
        yield session


def database_is_reachable() -> bool:
    """Trả về True khi cơ sở dữ liệu trả lời được một truy vấn đơn giản."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
