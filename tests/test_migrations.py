"""Migration Alembic tạo đúng cấu trúc bảng như mô hình trong code (không lệch nhau)."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from studio import database
from studio.models import Base


def test_migrations_match_models() -> None:
    with database.engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert differences == []
