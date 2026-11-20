"""Kết nối PostgreSQL dùng chung cho cả ứng dụng."""

from sqlalchemy import create_engine, text

from studio.config import settings

# `pool_pre_ping` thử kết nối trước khi dùng, tránh lỗi khi PostgreSQL vừa khởi động lại.
engine = create_engine(settings.database_url, pool_pre_ping=True)


def database_is_reachable() -> bool:
    """Trả về True khi PostgreSQL trả lời được một truy vấn đơn giản."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
