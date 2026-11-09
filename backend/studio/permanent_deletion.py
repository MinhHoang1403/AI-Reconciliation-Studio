"""Xóa vật lý theo manifest PostgreSQL, chỉ mở trong schema và kho TEST đã ràng buộc."""

import hashlib
import hmac
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from sqlalchemy import Table, and_, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from studio.access import Actor, require_owner
from studio.config import settings
from studio.contracts import Contract
from studio.database import Base, DatasetRow, ProjectRow, PurgeReceiptRow, now
from studio.errors import DomainError
from studio.resource_lifecycle import lock_project, missing
from studio.storage import checksum, storage_path

PurgeKind = Literal["dataset", "project", "workspace"]
TARGET = {"dataset": "datasets", "project": "projects", "workspace": "workspaces"}
BUSY = {"QUEUED", "RUNNING", "RETRYABLE_FAILURE"}
OPEN_WORK = {"CREATED", "RUNNING", "WAITING_REVIEW"}
SOURCE_ROWS = {
    "datasets",
    "dataset_versions",
    "source_tables",
    "artifacts",
    "mapping_revisions",
    "canonical_datasets",
}
OWNERSHIP_PARENT = {
    "dataset_versions": ("datasets", "dataset_id"),
    "source_tables": ("dataset_versions", "dataset_version_id"),
    "artifacts": ("dataset_versions", "dataset_version_id"),
    "mapping_revisions": ("source_tables", "source_table_id"),
    "canonical_datasets": ("source_tables", "source_table_id"),
    "job_attempts": ("jobs", "job_id"),
    "ai_traces": ("jobs", "job_id"),
    "conversation_messages": ("conversations", "conversation_id"),
}
FILE_COLUMNS = {
    "artifacts": ("storage_key", "sha256"),
    "reconciliation_runs": ("result_key", "result_sha256"),
    "run_exports": ("storage_key", "sha256"),
}
RESERVATIONS = {
    "GEMINI_REQUEST_RESERVED",
    "AGENT_REQUEST_RESERVED",
    "ASSISTANT_REQUEST_RESERVED",
    "LLAMAPARSE_DOCUMENT_RESERVED",
}
UUID_IN_REFERENCE = re.compile(r"(?<![\w-])[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}(?![\w-])")
Row = dict[str, Any]


class PurgeImpact(Contract):
    name: str
    fingerprint: str
    counts: dict[str, int]
    missing_files: int
    backup_retention: Literal["preserved"] = "preserved"


class PurgeConfirmation(Contract):
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmation: str = Field(min_length=1, max_length=255)


class PurgeStatus(Contract):
    id: str
    status: Literal["DELETING", "DELETED"]
    counts: dict[str, int]


@dataclass
class Manifest:
    impact: PurgeImpact
    rows: dict[str, list[Row]]
    files: dict[str, str]
    reservations: list[Row]


def isolated_root(db: Session) -> Path:
    """Từ chối trước khi đọc manifest nếu schema hoặc đường ghi chưa được cách ly."""
    schema = settings.purge_test_schema
    denied = DomainError(
        "PURGE_DISABLED", "Chỉ bật xóa vĩnh viễn trong môi trường TEST cô lập.", 403
    )
    if not re.fullmatch(r"test_[a-f0-9]{32}", schema):
        raise denied
    database, schemas = db.execute(text("SELECT current_database(), current_schemas(true)")).one()
    if schemas != ["pg_catalog", schema]:
        raise denied
    root = settings.storage_root
    resolved = root.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    marker = resolved / ".studio-purge-test"
    if (
        root != resolved
        or resolved.name != schema
        or not resolved.is_relative_to(temp_root)
        or resolved.is_mount()
        or not marker.is_file()
        or marker.is_symlink()
        or marker.read_text(encoding="ascii") != f"{database}:{schema}"
    ):
        raise denied
    return resolved


def _business_tables() -> list[Table]:
    return [table for table in Base.metadata.sorted_tables if table.name != "purge_receipts"]


def _lock_scope(db: Session, actor: Actor, kind: PurgeKind, resource_id: str) -> None:
    db.execute(text("SET LOCAL lock_timeout = '5s'"))
    if kind == "workspace":
        project_ids = list(
            db.scalars(
                select(ProjectRow.id)
                .where(ProjectRow.workspace_id == actor.workspace_id)
                .order_by(ProjectRow.id)
            )
        )
    elif kind == "dataset":
        project_ids = list(
            db.scalars(
                select(DatasetRow.project_id).where(
                    DatasetRow.id == resource_id, DatasetRow.workspace_id == actor.workspace_id
                )
            )
        )
    else:
        project_ids = [resource_id]
    # Chặn DML qua cả các đường không lấy khóa dự án, ví dụ tạo dự án hoặc ghi lịch sử.
    # Cổng cách ly giới hạn khóa mức bảng trong schema TEST hiện tại.
    names = ", ".join(f'"{table.name}"' for table in _business_tables())
    try:
        for project_id in project_ids:
            lock_project(db, project_id)
        db.execute(text(f"LOCK TABLE {names} IN SHARE ROW EXCLUSIVE MODE"))
    except OperationalError as exc:
        if getattr(exc.orig, "sqlstate", None) not in {"55P03", "40P01"}:
            raise
        raise DomainError(
            "PURGE_BUSY", "Phạm vi đang được cập nhật. Hãy xem lại tác động.", 409
        ) from exc


def _strings(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_strings(child) for child in value.values()))
    if isinstance(value, list):
        return set().union(*(_strings(child) for child in value))
    if isinstance(value, str):
        return {value, *UUID_IN_REFERENCE.findall(value)}
    return set()


def _identity(table: Table, row: Row) -> tuple[str, ...]:
    return tuple(row[column.name] for column in table.primary_key)


def _file_path(root: Path, key: str) -> Path:
    path = storage_path(root, key)
    if path != root / key or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1)):
        raise DomainError("PURGE_UNSAFE_FILE", "Có tham chiếu tệp cần kiểm tra trước khi xóa.", 409)
    return path


def _manifest(db: Session, actor: Actor, kind: PurgeKind, resource_id: str, root: Path) -> Manifest:
    tables = _business_tables()
    rows = {
        table.name: [dict(row) for row in db.execute(select(table)).mappings()] for table in tables
    }
    by_id = {
        name: {row["id"]: row for row in values if "id" in row} for name, values in rows.items()
    }
    target = next((row for row in rows[TARGET[kind]] if row["id"] == resource_id), None)
    workspace_id = actor.workspace_id
    if target is None or target.get("workspace_id", target["id"]) != workspace_id:
        raise missing()
    if kind == "workspace" and resource_id == "demo":
        raise DomainError(
            "PURGE_ACTIVE_WORKSPACE", "Không thể xóa không gian local đang sử dụng.", 409
        )
    project_id = target.get("project_id", resource_id)
    project_ids = (
        {row["id"] for row in rows["projects"] if row["workspace_id"] == workspace_id}
        if kind == "workspace"
        else {project_id}
    )

    def in_scope(table: str, row: Row) -> bool:
        if row.get("workspace_id", workspace_id) != workspace_id:
            return False
        if row.get("project_id", project_id) not in project_ids and kind != "workspace":
            return False
        while table in OWNERSHIP_PARENT:
            table, column = OWNERSHIP_PARENT[table]
            row = by_id[table][row[column]]
            if row.get("workspace_id", workspace_id) != workspace_id:
                return False
        if kind == "dataset" and table == "datasets":
            return bool(row["id"] == resource_id)
        return row.get("project_id", project_id) in project_ids or kind == "workspace"

    external_reference = DomainError(
        "PURGE_EXTERNAL_REFERENCE", "Có dữ liệu ngoài phạm vi đang tham chiếu.", 409
    )
    if any(row["project_id"] in project_ids and row["status"] in BUSY for row in rows["jobs"]):
        raise DomainError("PURGE_BUSY", "Chờ công việc trong dự án kết thúc trước khi xóa.", 409)
    if any(
        row["project_id"] in project_ids and row["state"] in OPEN_WORK
        for row in rows["agent_workflows"]
    ):
        raise DomainError(
            "PURGE_OPEN_REVIEW", "Hoàn tất lượt đang chờ xác nhận trước khi xóa.", 409
        )

    selected: dict[str, set[tuple[str, ...]]] = {table.name: set() for table in tables}
    json_refs: dict[tuple[str, tuple[str, ...]], set[str]] = {}
    for table in tables:
        json_columns = [column.name for column in table.columns if isinstance(column.type, JSONB)]
        for row in rows[table.name]:
            identity = _identity(table, row)
            if (
                (table.name == TARGET[kind] and row is target)
                or (kind == "workspace" and row.get("workspace_id") == workspace_id)
                or (kind == "project" and row.get("project_id") == project_id)
            ):
                if not in_scope(table.name, row):
                    raise external_reference
                selected[table.name].add(identity)
            json_refs[table.name, identity] = set().union(
                *(_strings(row[column]) for column in json_columns)
            )

    while True:
        before = sum(map(len, selected.values()))
        selected_ids = {
            identity[0] for keys in selected.values() for identity in keys if len(identity) == 1
        }
        for table in tables:
            for row in rows[table.name]:
                identity = _identity(table, row)
                if identity in selected[table.name] or table.name == "schema_definitions":
                    continue
                foreign_ref = any(
                    (row[key.parent.name],) in selected[key.column.table.name]
                    for key in table.foreign_keys
                    if len(key.column.table.primary_key) == 1
                )
                json_ref = not selected_ids.isdisjoint(json_refs[table.name, identity])
                audit_ref = row.get("resource_id") in selected_ids
                if not (foreign_ref or json_ref or audit_ref):
                    continue
                if (
                    not in_scope(table.name, row)
                    or table.name in {"workspaces", "memberships", "sessions", "projects"}
                    or (kind == "dataset" and table.name in SOURCE_ROWS and not foreign_ref)
                ):
                    raise external_reference
                selected[table.name].add(identity)
        if sum(map(len, selected.values())) == before:
            break

    # Schema dùng chung còn giá trị nếu còn mapping hoặc JSON provenance tham chiếu.
    removed_mapping_schemas = {
        row["schema_id"]
        for row in rows["mapping_revisions"]
        if (row["id"],) in selected["mapping_revisions"]
    }
    surviving_schema_ids = {
        row["schema_id"]
        for row in rows["mapping_revisions"]
        if (row["id"],) not in selected["mapping_revisions"]
    }
    for (table_name, identity), refs in json_refs.items():
        if identity not in selected[table_name]:
            surviving_schema_ids.update(removed_mapping_schemas & refs)
    selected["schema_definitions"].update(
        (schema_id,) for schema_id in removed_mapping_schemas - surviving_schema_ids
    )

    removed = {
        table.name: [
            row for row in rows[table.name] if _identity(table, row) in selected[table.name]
        ]
        for table in tables
    }
    reservations = [row for row in removed["audit_events"] if row["action"] in RESERVATIONS]
    if reservations and kind == "workspace":
        raise DomainError("PURGE_BUDGET_HISTORY", "Không gian còn biên nhận chi phí cần giữ.", 409)
    removed["audit_events"] = [row for row in removed["audit_events"] if row not in reservations]

    files: dict[str, str] = {}
    surviving_keys: set[str] = set()
    for table_name, (key_col, sha_col) in FILE_COLUMNS.items():
        for row in rows[table_name]:
            key = row[key_col]
            if key is None:
                continue
            if (row["id"],) not in selected[table_name]:
                surviving_keys.add(key)
                continue
            sha = row[sha_col]
            if (
                not key.startswith(f"{workspace_id}/")
                or not sha
                or not re.fullmatch(r"[0-9a-f]{64}", sha)
            ):
                raise DomainError(
                    "PURGE_UNSAFE_FILE", "Tham chiếu tệp thiếu phạm vi hoặc checksum.", 409
                )
            if files.setdefault(key, sha) != sha:
                raise DomainError("PURGE_UNSAFE_FILE", "Tệp có nhiều checksum khác nhau.", 409)
    for (table_name, identity), refs in json_refs.items():
        if identity not in selected[table_name]:
            surviving_keys.update(files.keys() & refs)
    files = {key: sha for key, sha in files.items() if key not in surviving_keys}
    absent = []
    for key, sha in files.items():
        path = _file_path(root, key)
        if not path.exists():
            absent.append(key)
        elif checksum(path) != sha:
            raise DomainError("PURGE_CHECKSUM", "Tệp đã thay đổi. Hãy kiểm tra trước khi xóa.", 409)
    # Các thư mục phiên bản/lượt/xuất được tạo từ ID. Nếu có tệp chưa công bố,
    # dừng để không bỏ sót tệp hoặc xóa theo tên suy đoán.
    dirs = [f"{workspace_id}/{row['id']}" for row in removed["dataset_versions"]]
    dirs += [f"{workspace_id}/runs/{row['id']}" for row in removed["reconciliation_runs"]]
    dirs += [f"{workspace_id}/exports/{row['id']}" for row in removed["run_exports"]]
    if kind == "workspace":
        dirs = [workspace_id]
    known = files.keys() | surviving_keys
    for directory in dirs:
        path = storage_path(root, directory)
        if path != root / directory:
            raise DomainError("PURGE_UNSAFE_FILE", "Có liên kết tệp cần kiểm tra.", 409)
        for entry in path.rglob("*"):
            if entry.is_symlink() or (
                not entry.is_dir() and entry.relative_to(root).as_posix() not in known
            ):
                raise DomainError(
                    "PURGE_UNTRACKED_FILE", "Có tệp chưa có biên nhận trong phạm vi xóa.", 409
                )

    counts = {table: len(items) for table, items in removed.items() if items}
    counts["files"] = len(files)
    counts["shared_files"] = len(
        {
            row[col]
            for table, (col, _) in FILE_COLUMNS.items()
            for row in removed[table]
            if row[col] in surviving_keys
        }
    )
    # Ràng buộc bản xem trước với cả giá trị và ID của metadata, không chỉ số dòng.
    payload = [
        kind,
        resource_id,
        target["name"],
        files,
        sorted(absent),
        {
            key: sorted(json.dumps(row, sort_keys=True, default=str) for row in items)
            for key, items in removed.items()
            if items
        },
    ]
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return Manifest(
        PurgeImpact(
            name=target["name"], fingerprint=fingerprint, counts=counts, missing_files=len(absent)
        ),
        removed,
        files,
        reservations,
    )


def preview(db: Session, actor: Actor, kind: PurgeKind, resource_id: str) -> PurgeImpact:
    root = isolated_root(db)
    require_owner(actor, db, resource_id)
    _lock_scope(db, actor, kind, resource_id)
    return _manifest(db, actor, kind, resource_id, root).impact


def _status(receipt: PurgeReceiptRow) -> PurgeStatus:
    return PurgeStatus(
        id=receipt.id,
        status="DELETED" if receipt.completed_at else "DELETING",
        counts=receipt.counts,
    )


def status(
    db: Session, actor: Actor | None, receipt_id: str, *, session_hash: str = ""
) -> PurgeStatus:
    isolated_root(db)
    if actor is not None:
        require_owner(actor, db, receipt_id)
    receipt = db.get(PurgeReceiptRow, receipt_id)
    if receipt is None:
        raise missing()
    if actor is not None:
        if (receipt.workspace_id, receipt.actor_id) != (actor.workspace_id, actor.id):
            raise missing()
    elif not (
        receipt.kind == "workspace"
        and session_hash
        and receipt.receipt_session_hash
        and hmac.compare_digest(receipt.receipt_session_hash, session_hash)
    ):
        raise missing()
    return _status(receipt)


def finish_files(db: Session, receipt_id: str) -> PurgeStatus:
    """Tệp thiếu là kết quả hợp lệ khi thử lại sau crash. Tệp sai checksum giữ chờ."""
    root = isolated_root(db)
    receipt = db.get(PurgeReceiptRow, receipt_id, with_for_update=True)
    if receipt is None:
        raise missing()
    if receipt.completed_at is None:
        try:
            for key, sha in receipt.files.items():
                path = _file_path(root, key)
                if path.exists():
                    if checksum(path) != sha:
                        return _status(receipt)
                    path.unlink(missing_ok=True)
            if any(_file_path(root, key).exists() for key in receipt.files):
                return _status(receipt)
        except (OSError, DomainError):
            return _status(receipt)
        receipt.files = {}
        receipt.completed_at = now()
        db.commit()
    return _status(receipt)


def confirm(
    db: Session,
    actor: Actor,
    kind: PurgeKind,
    resource_id: str,
    body: PurgeConfirmation,
    *,
    session_hash: str | None = None,
) -> PurgeStatus:
    root = isolated_root(db)
    require_owner(actor, db, resource_id)
    _lock_scope(db, actor, kind, resource_id)
    receipt = db.get(PurgeReceiptRow, body.fingerprint)
    if receipt is not None:
        if (receipt.workspace_id, receipt.actor_id, receipt.kind, receipt.resource_id) != (
            actor.workspace_id,
            actor.id,
            kind,
            resource_id,
        ):
            raise missing()
        db.commit()
        return finish_files(db, receipt.id)
    manifest = _manifest(db, actor, kind, resource_id, root)
    if body.confirmation != manifest.impact.name or body.fingerprint != manifest.impact.fingerprint:
        raise DomainError(
            "PURGE_CONFIRMATION_STALE", "Xem lại tác động và nhập đúng tên tài nguyên.", 409
        )
    for row in manifest.reservations:
        audit = Base.metadata.tables["audit_events"]
        db.execute(
            audit.update()
            .where(audit.c.id == row["id"])
            .values(resource_id=hashlib.sha256(row["resource_id"].encode()).hexdigest())
        )
    for table in reversed(_business_tables()):
        for row in manifest.rows[table.name]:
            db.execute(
                table.delete().where(
                    and_(*(column == row[column.name] for column in table.primary_key))
                )
            )
    db.add(
        PurgeReceiptRow(
            id=body.fingerprint,
            workspace_id=actor.workspace_id,
            actor_id=actor.id,
            kind=kind,
            resource_id=resource_id,
            receipt_session_hash=session_hash if kind == "workspace" else None,
            files=manifest.files,
            counts=manifest.impact.counts,
        )
    )
    # Metadata và manifest phải commit cùng nhau trước khi chạm vào tệp.
    db.commit()
    return finish_files(db, body.fingerprint)


def resume_pending(db: Session) -> None:
    try:
        isolated_root(db)
    except DomainError as exc:
        if exc.code != "PURGE_DISABLED":
            raise
        return
    pending = list(
        db.scalars(
            select(PurgeReceiptRow.id)
            .where(PurgeReceiptRow.completed_at.is_(None))
            .order_by(PurgeReceiptRow.created_at)
            .limit(20)
        )
    )
    db.rollback()
    for receipt_id in pending:
        finish_files(db, receipt_id)
        db.rollback()
