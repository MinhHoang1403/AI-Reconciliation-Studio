"""Immutable, scoped filesystem storage; only backend-generated keys are accepted."""

import hashlib
import re
from pathlib import Path

import polars as pl

from studio.errors import DomainError


def storage_path(root: Path, key: str) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9_./-]+", key) or ".." in key.split("/"):
        raise DomainError("INVALID_STORAGE_KEY", "Tham chiếu lưu trữ không hợp lệ.")
    path = (root / key).resolve()
    if not path.is_relative_to(root.resolve()):
        raise DomainError("INVALID_STORAGE_KEY", "Tham chiếu lưu trữ không hợp lệ.")
    return path


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_parquet(root: Path, key: str, frame: pl.DataFrame) -> str:
    """Publish immutable bytes before DB refs; a rollback leaves an unreferenced artifact."""
    path = storage_path(root, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents concurrent/retried jobs from overwriting published data.
    with path.open("xb") as stream:
        frame.write_parquet(stream)
    return checksum(path)
