"""Xóa vật lý theo manifest PostgreSQL trong triển khai local hoặc TEST đã ràng buộc."""

import hashlib
import hmac
import json
import re
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import batched
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from sqlalchemy import String, Table, any_, literal, or_, select, text, tuple_
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from studio.access import Actor, _demo_allowed, require_owner
from studio.config import settings
from studio.contracts import Contract
from studio.database import Base, DatasetRow, MembershipRow, ProjectRow, PurgeReceiptRow, now
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
    "RECONCILIATION_PLANNER_ATTEMPT",
    "LLAMAPARSE_DOCUMENT_RESERVED",
}
UUID_IN_REFERENCE = re.compile(r"(?<![\w-])[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}(?![\w-])")
Row = dict[str, Any]
BATCH_SIZE = 256
LOCAL_ROOT = Path("/var/lib/studio")


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


def purge_root(db: Session, *, interactive: bool = True) -> Path:
    """Bind interactive local access to host proof and every receipt to one storage root."""
    schema = settings.purge_test_schema
    denied = DomainError(
        "PURGE_DISABLED", "Xóa vĩnh viễn chưa được bật trong môi trường đã xác minh.", 403
    )
    if not schema:
        if not (
            settings.purge_local_enabled
            and settings.local_demo_access
            and settings.storage_root == LOCAL_ROOT
            and LOCAL_ROOT.resolve() == LOCAL_ROOT
            and LOCAL_ROOT.is_mount()
            and (not interactive or _demo_allowed())
        ):
            raise denied
        database, schemas = db.execute(
            text("SELECT current_database(), current_schemas(true)")
        ).one()
        if (database, schemas) != ("studio", ["pg_catalog", "public"]):
            raise denied
        return LOCAL_ROOT
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
    # Scope validation limits these table locks to the verified PostgreSQL schema.
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


def _has_id(column: Any, ids: set[str]) -> Any:
    return column == any_(literal(sorted(ids), type_=ARRAY(String())))


def _manifest(db: Session, actor: Actor, kind: PurgeKind, resource_id: str, root: Path) -> Manifest:
    tables = _business_tables()
    by_name = {table.name: table for table in tables}
    selected: dict[str, dict[tuple[str, ...], Row]] = {table.name: {} for table in tables}

    def load_row(name: str, resource: str) -> Row | None:
        cached = selected[name].get((resource,))
        if cached is not None:
            return cached
        table = by_name[name]
        row = db.execute(select(table).where(table.c.id == resource)).mappings().one_or_none()
        return dict(row) if row is not None else None

    target = load_row(TARGET[kind], resource_id)
    workspace_id = actor.workspace_id
    if target is None or target.get("workspace_id", target["id"]) != workspace_id:
        raise missing()
    if kind == "workspace" and resource_id == "demo":
        raise DomainError(
            "PURGE_ACTIVE_WORKSPACE", "Không thể xóa không gian local đang sử dụng.", 409
        )
    project_id = target.get("project_id", resource_id)
    project_ids = (
        set(db.scalars(select(ProjectRow.id).where(ProjectRow.workspace_id == workspace_id)))
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
            parent = load_row(table, row[column])
            if parent is None or parent.get("workspace_id", workspace_id) != workspace_id:
                return False
            row = parent
        if kind == "dataset" and table == "datasets":
            return bool(row["id"] == resource_id)
        return row.get("project_id", project_id) in project_ids or kind == "workspace"

    external_reference = DomainError(
        "PURGE_EXTERNAL_REFERENCE", "Có dữ liệu ngoài phạm vi đang tham chiếu.", 409
    )
    jobs = by_name["jobs"].c
    workflows = by_name["agent_workflows"].c
    if db.scalar(
        select(jobs.id).where(_has_id(jobs.project_id, project_ids), jobs.status.in_(BUSY)).limit(1)
    ):
        raise DomainError("PURGE_BUSY", "Chờ công việc trong dự án kết thúc trước khi xóa.", 409)
    if db.scalar(
        select(workflows.id)
        .where(_has_id(workflows.project_id, project_ids), workflows.state.in_(OPEN_WORK))
        .limit(1)
    ):
        raise DomainError(
            "PURGE_OPEN_REVIEW", "Hoàn tất lượt đang chờ xác nhận trước khi xóa.", 409
        )

    selected[TARGET[kind]][(resource_id,)] = target
    if kind != "dataset":
        column, value = (
            ("workspace_id", workspace_id) if kind == "workspace" else ("project_id", project_id)
        )
        for table in tables:
            if column not in table.c:
                continue
            statement = select(table).where(table.c[column] == value)
            with db.execute(statement.execution_options(yield_per=BATCH_SIZE)) as result:
                for candidate in result.mappings():
                    row = dict(candidate)
                    if not in_scope(table.name, row):
                        raise external_reference
                    selected[table.name][_identity(table, row)] = row

    def add_dependent(table: Table, row: Row, *, foreign_ref: bool) -> None:
        if (
            not in_scope(table.name, row)
            or table.name in {"workspaces", "memberships", "sessions", "projects"}
            or (kind == "dataset" and table.name in SOURCE_ROWS and not foreign_ref)
        ):
            raise external_reference
        selected[table.name][_identity(table, row)] = row

    def json_matches(ids: set[str]) -> Iterator[tuple[Table, tuple[str, ...], set[str]]]:
        # Legacy JSON can contain nested references or UUIDs embedded in prose.
        # Project only JSON + PK and stream the scan. Never retain unrelated rows or refs.
        if not ids:
            return
        for table in tables:
            columns = [column for column in table.columns if isinstance(column.type, JSONB)]
            if not columns:
                continue
            statement = select(*table.primary_key, *columns)
            with db.execute(statement.execution_options(yield_per=BATCH_SIZE)) as result:
                for item in result.mappings():
                    identity = tuple(item[column] for column in table.primary_key)
                    if identity in selected[table.name]:
                        continue
                    refs = set().union(*(_strings(item[column]) for column in columns)) & ids
                    if refs:
                        yield table, identity, refs

    scanned: set[str] = set()
    while True:
        # Follow indexed FK relationships first. A JSON reference can introduce
        # another owner, so repeat only while new identifiers were discovered.
        while True:
            before = sum(map(len, selected.values()))
            ids = {key[0] for keys in selected.values() for key in keys if len(key) == 1}
            for table in tables:
                predicates = []
                for fk in table.foreign_keys:
                    parents = selected[fk.column.table.name]
                    if parents and len(fk.column.table.primary_key) == 1:
                        predicates.append(_has_id(fk.parent, {key[0] for key in parents}))
                if "resource_id" in table.c:
                    predicates.append(_has_id(table.c.resource_id, ids))
                if not predicates:
                    continue
                statement = select(table).where(or_(*predicates))
                with db.execute(statement.execution_options(yield_per=BATCH_SIZE)) as result:
                    for candidate in result.mappings():
                        row = dict(candidate)
                        if _identity(table, row) not in selected[table.name]:
                            add_dependent(
                                table,
                                row,
                                foreign_ref=any(
                                    (row[fk.parent.name],) in selected[fk.column.table.name]
                                    for fk in table.foreign_keys
                                ),
                            )
            if sum(map(len, selected.values())) == before:
                break

        pending = ids - scanned
        if not pending:
            break
        for table, identity, _ in json_matches(pending):
            if table.name == "schema_definitions":
                continue
            columns = list(table.primary_key)
            if len(columns) == 1:
                dependent = load_row(table.name, identity[0])
            else:
                item = (
                    db.execute(select(table).where(tuple_(*columns) == identity)).mappings().one()
                )
                dependent = dict(item)
            if dependent is not None:
                add_dependent(table, dependent, foreign_ref=False)
        scanned.update(pending)

    # Shared definitions survive if a mapping or provenance outside the manifest uses them.
    mappings = by_name["mapping_revisions"].c
    schema_ids = {row["schema_id"] for row in selected["mapping_revisions"].values()}
    if schema_ids:
        with db.execute(
            select(mappings.id, mappings.schema_id)
            .where(_has_id(mappings.schema_id, schema_ids))
            .execution_options(yield_per=BATCH_SIZE)
        ) as result:
            surviving = {
                schema_id
                for mid, schema_id in result
                if (mid,) not in selected["mapping_revisions"]
            }
        surviving.update(ref for _, _, refs in json_matches(schema_ids - surviving) for ref in refs)
        for schema_id in schema_ids - surviving:
            definition = load_row("schema_definitions", schema_id)
            if definition is not None:
                if not in_scope("schema_definitions", definition):
                    raise external_reference
                selected["schema_definitions"][(schema_id,)] = definition

    removed = {name: list(items.values()) for name, items in selected.items()}
    reservations = [row for row in removed["audit_events"] if row["action"] in RESERVATIONS]
    removed["audit_events"] = [row for row in removed["audit_events"] if row not in reservations]

    files: dict[str, str] = {}
    for table_name, (key_col, sha_col) in FILE_COLUMNS.items():
        for row in removed[table_name]:
            key = row[key_col]
            if key is None:
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
    # Các thư mục phiên bản/lượt/xuất được tạo từ ID. Nếu có tệp chưa công bố,
    # dừng để không bỏ sót tệp hoặc xóa theo tên suy đoán.
    dirs = [f"{workspace_id}/{row['id']}" for row in removed["dataset_versions"]]
    dirs += [f"{workspace_id}/runs/{row['id']}" for row in removed["reconciliation_runs"]]
    dirs += [f"{workspace_id}/exports/{row['id']}" for row in removed["run_exports"]]
    if kind == "workspace":
        dirs = [workspace_id]
    inventory: set[str] = set()
    for directory in dirs:
        path = storage_path(root, directory)
        if path != root / directory:
            raise DomainError("PURGE_UNSAFE_FILE", "Có liên kết tệp cần kiểm tra.", 409)
        for entry in path.rglob("*"):
            if entry.is_symlink():
                raise DomainError(
                    "PURGE_UNTRACKED_FILE", "Có tệp chưa có biên nhận trong phạm vi xóa.", 409
                )
            if not entry.is_dir():
                inventory.add(entry.relative_to(root).as_posix())

    surviving_keys: set[str] = set()
    lookup = inventory | files.keys()
    for table_name, (key_col, _) in FILE_COLUMNS.items():
        if not lookup:
            break
        table = by_name[table_name]
        storage_key = table.c[key_col]
        with db.execute(
            select(table.c.id, storage_key)
            .where(_has_id(storage_key, lookup))
            .execution_options(yield_per=BATCH_SIZE)
        ) as result:
            surviving_keys.update(
                key for row_id, key in result if (row_id,) not in selected[table_name]
            )
    surviving_keys.update(
        ref for _, _, refs in json_matches(files.keys() - surviving_keys) for ref in refs
    )
    if inventory - files.keys() - surviving_keys:
        raise DomainError(
            "PURGE_UNTRACKED_FILE", "Có tệp chưa có biên nhận trong phạm vi xóa.", 409
        )
    shared_count = len(files.keys() & surviving_keys)
    files = {key: sha for key, sha in files.items() if key not in surviving_keys}
    absent = []
    for key, sha in files.items():
        path = _file_path(root, key)
        if not path.exists():
            absent.append(key)
        elif checksum(path) != sha:
            raise DomainError("PURGE_CHECKSUM", "Tệp đã thay đổi. Hãy kiểm tra trước khi xóa.", 409)

    counts = {table: len(items) for table, items in removed.items() if items}
    counts["files"] = len(files)
    counts["shared_files"] = shared_count
    # Ràng buộc bản xem trước với cả giá trị và ID của metadata, không chỉ số dòng.
    payload = [
        kind,
        resource_id,
        target["name"],
        files,
        sorted(absent),
        sorted(row["id"] for row in reservations),
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
    root = purge_root(db)
    require_owner(actor, db, resource_id)
    target = _purge_target_actor(db, actor, kind, resource_id)
    _lock_scope(db, target, kind, resource_id)
    return _manifest(
        db, _purge_target_actor(db, actor, kind, resource_id), kind, resource_id, root
    ).impact


def _purge_target_actor(db: Session, actor: Actor, kind: PurgeKind, resource_id: str) -> Actor:
    if kind != "workspace" or resource_id == actor.workspace_id:
        return actor
    role = db.scalar(
        select(MembershipRow.role).where(
            MembershipRow.workspace_id == resource_id,
            MembershipRow.actor_id == actor.id,
        )
    )
    if role != "owner":
        raise missing()
    return Actor(actor.id, resource_id, role)


def _status(receipt: PurgeReceiptRow) -> PurgeStatus:
    return PurgeStatus(
        id=receipt.id,
        status="DELETED" if receipt.completed_at else "DELETING",
        counts=receipt.counts,
    )


def _confirmation_hash(body: PurgeConfirmation) -> str:
    return hmac.new(
        settings.session_secret.get_secret_value().encode(),
        f"{body.fingerprint}:{body.confirmation}".encode(),
        hashlib.sha256,
    ).hexdigest()


def status(
    db: Session, actor: Actor | None, receipt_id: str, *, session_hash: str = ""
) -> PurgeStatus:
    purge_root(db)
    if actor is not None:
        require_owner(actor, db, receipt_id)
    receipt = db.get(PurgeReceiptRow, receipt_id)
    if receipt is None:
        raise missing()
    if actor is not None:
        if receipt.actor_id != actor.id or (
            receipt.kind != "workspace" and receipt.workspace_id != actor.workspace_id
        ):
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
    root = purge_root(db, interactive=False)
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
    root = purge_root(db)
    require_owner(actor, db, resource_id)
    receipt = db.get(PurgeReceiptRow, body.fingerprint)
    if receipt is None:
        target = _purge_target_actor(db, actor, kind, resource_id)
        _lock_scope(db, target, kind, resource_id)
        receipt = db.get(PurgeReceiptRow, body.fingerprint)
    if receipt is not None:
        if (receipt.actor_id, receipt.kind, receipt.resource_id) != (
            actor.id,
            kind,
            resource_id,
        ) or (kind != "workspace" and receipt.workspace_id != actor.workspace_id):
            raise missing()
        if not receipt.confirmation_hash or not hmac.compare_digest(
            receipt.confirmation_hash, _confirmation_hash(body)
        ):
            raise DomainError("PURGE_CONFIRMATION_STALE", "Xác nhận không khớp biên nhận.", 409)
        db.commit()
        return finish_files(db, receipt.id)
    actor = _purge_target_actor(db, actor, kind, resource_id)
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
            .values(
                resource_id=hashlib.sha256(row["resource_id"].encode()).hexdigest(),
                **(
                    {"workspace_id": None, "actor_id": "purged-workspace"}
                    if kind == "workspace"
                    else {}
                ),
            )
        )
    for table in reversed(_business_tables()):
        columns = list(table.primary_key)
        for batch in batched(manifest.rows[table.name], BATCH_SIZE):
            identities = [_identity(table, row) for row in batch]
            predicate = (
                _has_id(columns[0], {key[0] for key in identities})
                if len(columns) == 1
                else tuple_(*columns).in_(identities)
            )
            db.execute(table.delete().where(predicate))
    db.add(
        PurgeReceiptRow(
            id=body.fingerprint,
            workspace_id=actor.workspace_id,
            actor_id=actor.id,
            kind=kind,
            resource_id=resource_id,
            receipt_session_hash=session_hash if kind == "workspace" else None,
            confirmation_hash=_confirmation_hash(body),
            files=manifest.files,
            counts=manifest.impact.counts,
        )
    )
    # Metadata và manifest phải commit cùng nhau trước khi chạm vào tệp.
    db.commit()
    return finish_files(db, body.fingerprint)


def resume_pending(db: Session) -> None:
    try:
        purge_root(db, interactive=False)
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
