"""Thiết lập chung cho kiểm thử.

Kiểm thử chạy trên cơ sở dữ liệu SQLite tạm và thư mục tệp tạm, không đụng tới dữ liệu
của container đang chạy. Bảng được tạo bằng chính migration Alembic để kiểm luôn migration.
Biến môi trường phải được đặt trước khi import `studio`, nên đặt ngay ở đầu tệp này.
"""

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

_WORK_DIR = Path(tempfile.mkdtemp(prefix="studio-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_WORK_DIR / 'test.db').as_posix()}"
os.environ["STORAGE_ROOT"] = str(_WORK_DIR / "files")

import pytest  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from studio import database  # noqa: E402
from studio.migrate import upgrade_to_latest  # noqa: E402
from studio.models import Dataset  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "sales"


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    with database.engine.begin() as connection:
        upgrade_to_latest(connection)
    yield
    database.engine.dispose()
    shutil.rmtree(_WORK_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_state() -> Iterator[None]:
    """Mỗi bài kiểm bắt đầu với DB trống và thư mục tệp trống."""
    yield
    with database.SessionFactory() as session:
        session.execute(delete(Dataset))
        session.commit()
    files = _WORK_DIR / "files"
    if files.exists():
        for path in files.rglob("*"):
            if path.is_file():
                path.chmod(0o644)
        shutil.rmtree(files, ignore_errors=True)
