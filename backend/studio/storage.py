"""Lưu tệp gốc và các bảng đã đọc trên đĩa (volume `files`).

- Tệp gốc: `raw/<sha256>.<đuôi>`; ghi một lần, không bao giờ sửa (RULES R15).
- Bảng đã đọc: `tables/<id bảng>.parquet`; đọc lại thì ghi đè bằng bản mới.
"""

import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from studio.config import settings

CHUNK_BYTES = 1024 * 1024


class UploadTooLarge(Exception):
    """Tệp vượt giới hạn kích thước cho phép."""


@dataclass
class StoredUpload:
    temp_path: Path
    sha256: str
    size_bytes: int


def raw_dir() -> Path:
    return settings.storage_root / "raw"


def tables_dir() -> Path:
    return settings.storage_root / "tables"


def receive_upload(stream: BinaryIO) -> StoredUpload:
    """Ghi tệp tải lên ra tệp tạm, vừa ghi vừa tính SHA-256 và kiểm giới hạn kích thước."""
    temp_dir = settings.storage_root / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    handle, name = tempfile.mkstemp(dir=temp_dir)
    path = Path(name)
    try:
        with os.fdopen(handle, "wb") as target:
            while chunk := stream.read(CHUNK_BYTES):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise UploadTooLarge
                digest.update(chunk)
                target.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return StoredUpload(temp_path=path, sha256=digest.hexdigest(), size_bytes=size)


def keep_raw_file(upload: StoredUpload, extension: str) -> Path:
    """Chuyển tệp tạm thành tệp gốc chính thức, chỉ đọc."""
    target = raw_dir() / f"{upload.sha256}.{extension}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        upload.temp_path.unlink(missing_ok=True)
    else:
        upload.temp_path.replace(target)
        target.chmod(0o444)
    return target


def table_path(table_id: uuid.UUID) -> Path:
    path = tables_dir() / f"{table_id}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def delete_file(path: str | Path | None) -> None:
    if path is None:
        return
    target = Path(path)
    if target.exists():
        target.chmod(0o644)  # tệp gốc được đặt chỉ đọc; mở quyền ghi trước khi xóa trên Windows
        target.unlink()
