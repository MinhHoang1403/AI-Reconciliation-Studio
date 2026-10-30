"""Backup metadata/artifacts nhất quán và restore drill trên UUID schema cùng PostgreSQL.

Chạy trong Backend hiện có, lúc không có job/API write. Không overwrite public,
không tạo server/container; backup nằm trên volume và phải copy ra nơi lưu độc lập.
"""

import json
import shutil
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import MetaData, create_engine, select, text
from studio.config import settings
from studio.database import Base
from studio.storage import checksum, storage_path


def encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, dict):
        return {"$map": {k: encode(v) for k, v in value.items()}}
    if isinstance(value, list):
        return [encode(v) for v in value]
    return value


def decode(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$map"}:
            return {k: decode(v) for k, v in value["$map"].items()}
        if set(value) == {"$datetime"}:
            return datetime.fromisoformat(value["$datetime"])
        if set(value) == {"$date"}:
            return date.fromisoformat(value["$date"])
        if set(value) == {"$decimal"}:
            return Decimal(value["$decimal"])
        return {k: decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode(v) for v in value]
    return value


def canonical(value: Any) -> str:
    return json.dumps(encode(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def capture(connection: Any, metadata: MetaData) -> dict[str, list[dict[str, Any]]]:
    active = connection.scalar(
        text("SELECT count(*) FROM jobs WHERE status IN ('QUEUED','RUNNING','RETRYABLE_FAILURE')")
    )
    if active:
        raise RuntimeError("BLOCKED: wait for active jobs and stop API writes before backup")
    return {
        table.name: sorted(
            [dict(row) for row in connection.execute(select(table)).mappings()], key=canonical
        )
        for table in metadata.sorted_tables
    }


def file_inventory(rows: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    files: dict[str, str] = {}
    for table, key, digest in (
        ("artifacts", "storage_key", "sha256"),
        ("reconciliation_runs", "result_key", "result_sha256"),
        ("run_exports", "storage_key", "sha256"),
    ):
        for row in rows.get(table, []):
            if row[key] and row[digest]:
                path = storage_path(settings.storage_root, row[key])
                if checksum(path) != row[digest]:
                    raise RuntimeError("Published artifact checksum mismatch")
                files[row[key]] = row[digest]
    return files


def validate_backup(directory: Path) -> dict[str, Any]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if checksum(directory / "metadata.json") != manifest["metadata_sha256"]:
        raise RuntimeError("Backup metadata checksum mismatch")
    for key, digest in manifest["files"].items():
        if checksum(storage_path(directory / "files", key)) != digest:
            raise RuntimeError("Backup artifact checksum mismatch")
    return manifest


def main() -> None:
    started = time.monotonic()
    ident = "backup_" + uuid4().hex
    directory = storage_path(settings.storage_root, f"backups/{ident}")
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    engine = create_engine(settings.database_url, isolation_level="REPEATABLE READ")
    metadata = MetaData()
    # Reflect the deployed schema, including exact current migration; not local create_all.
    names = list(Base.metadata.tables) + ["alembic_version"]
    metadata.reflect(bind=engine, only=names)
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        rows = capture(connection, metadata)
        files = file_inventory(rows)
        (directory / "metadata.json").write_text(canonical(rows), encoding="utf-8")
        for key in files:
            target = storage_path(directory / "files", key)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(storage_path(settings.storage_root, key), target)
        connection.rollback()
    with engine.connect() as connection:
        if canonical(capture(connection, metadata)) != canonical(rows):
            raise RuntimeError("BLOCKED: metadata changed during backup; receipt not accepted")
    manifest = dict(
        backup_id=ident,
        created_at=datetime.now().astimezone().isoformat(),
        metadata_sha256=checksum(directory / "metadata.json"),
        files=files,
        counts={k: len(v) for k, v in rows.items()},
        schema_revision=rows["alembic_version"][0]["version_num"],
        backup_seconds=round(time.monotonic() - started, 3),
    )
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    validate_backup(directory)
    # Failure cases use only disposable bytes generated for this drill.
    probe = directory / "checksum-probe"
    probe.write_bytes(b"synthetic backup checksum probe")
    digest = checksum(probe)
    probe.write_bytes(b"corrupted")
    assert checksum(probe) != digest
    probe.unlink()
    try:
        storage_path(directory / "files", "../outside")
    except Exception:
        pass
    else:
        raise AssertionError("Path traversal guard missing")

    schema = "restore_" + uuid4().hex
    restored = directory / "restored-files"
    restore_started = time.monotonic()
    try:
        with engine.begin() as connection:
            # UUID generated locally, never a user-supplied identifier.
            assert len(schema) == 40 and schema.startswith("restore_")
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            scoped = connection.execution_options(schema_translate_map={None: schema})
            metadata.create_all(scoped)
            decoded = decode(json.loads((directory / "metadata.json").read_text(encoding="utf-8")))
            for table in metadata.sorted_tables:
                if decoded[table.name]:
                    scoped.execute(table.insert(), decoded[table.name])
            for table in metadata.sorted_tables:
                actual = sorted(
                    [dict(r) for r in scoped.execute(select(table)).mappings()], key=canonical
                )
                assert canonical(actual) == canonical(rows[table.name]), table.name
        for key, digest in files.items():
            target = storage_path(restored, key)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(storage_path(directory / "files", key), target)
            assert checksum(target) == digest
        # Financial evidence and durable conversations are compared as full metadata,
        # including snapshot/rule revisions, claims, citations and reservation audits.
        manifest.update(
            restore_status="PASS",
            restore_seconds=round(time.monotonic() - restore_started, 3),
            restored_schema=schema,
            checksum_failure_detected=True,
            traversal_rejected=True,
        )
    finally:
        with engine.begin() as connection:
            assert len(schema) == 40 and schema.startswith("restore_")
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        # Only remove this drill's redundant extracted copy after absolute path guard.
        assert restored.resolve().parent == directory.resolve()
        if restored.exists():
            shutil.rmtree(restored)
    with engine.connect() as connection:
        assert canonical(capture(connection, metadata)) == canonical(rows), (
            "Production metadata changed"
        )
    assert file_inventory(rows) == files
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "files"}, ensure_ascii=False))
    print(
        "PASS: restored metadata and files; production unchanged; backup retained on volume"
    )
    engine.dispose()


if __name__ == "__main__":
    main()
