"""Thư mục `data-docs/`: data model, data catalog, schema JSON và nhật ký gọi Gemini ra tệp.

Mục đích (Owner yêu cầu 26/11/2026): ngoài PostgreSQL, người lập trình xem được cấu trúc dữ
liệu, ý nghĩa nghiệp vụ và mọi thứ gửi cho Gemini dưới dạng tệp JSON, làm bằng chứng khi báo
cáo. Các tệp này chỉ để XEM: hệ thống không đọc lại chúng; muốn đổi thì sửa code rồi sinh lại.

Hai phần:
- Tĩnh (`model/`, `catalog/`, `schemas/`, commit vào Git): sinh từ code bằng
  `tools/export_data_docs.py`; `tests/test_data_docs.py` báo lỗi khi tệp lệch với code.
- Chạy (`runtime/`, Git bỏ qua vì có mẫu dữ liệu đã che): backend tự ghi khi
  `settings.data_docs_dir` được đặt (container: `/data/data-docs`, gắn ra `data-docs/runtime`).
  * `ai-calls/<ngày>/<giờ>_<mục đích>_<mã>.json`: mỗi lần gọi Gemini, gồm đúng đầu vào đã che
    gửi đi, khuôn JSON hoặc khai báo công cụ, câu trả lời, token, thời gian, lỗi. Không bao giờ
    có khóa API.
  * `catalog/datasets/<mã bộ dữ liệu>.json`: catalog động của từng bộ dữ liệu, tự cập nhật sau
    mỗi lần dữ liệu của bộ đó đổi (đọc, ánh xạ, làm sạch, đối soát) và tự xóa khi xóa bộ dữ liệu.

Ghi tệp không bao giờ làm hỏng tính năng chính: lỗi ghi chỉ được ghi log.
"""

import json
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from studio.config import settings
from studio.models import (
    Base,
    CellCorrection,
    CleanVersion,
    ColumnMapping,
    Dataset,
    DatasetTable,
    ReconRun,
    RowDecision,
)

logger = logging.getLogger(__name__)
# Giờ Việt Nam (UTC+7, không đổi giờ theo mùa) cho tên thư mục, tên tệp nhật ký: container chạy
# giờ UTC nên nếu không đặt, tệp gọi lúc 11:49 sẽ mang tên 04:49.
VIETNAM = timezone(timedelta(hours=7))


def _json(value: Any) -> str:
    """JSON dễ đọc, giữ tiếng Việt, kết thúc bằng xuống dòng (ổn định giữa các lần sinh)."""
    return json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"


# ---------------------------------------------------------------- phần tĩnh: data model


def _table_docs() -> dict[str, str]:
    """Dòng đầu docstring của lớp mô hình ứng với mỗi bảng (mô tả bằng tiếng Việt)."""
    docs = {}
    for mapper in Base.registry.mappers:
        table = getattr(mapper.class_, "__tablename__", None)
        doc = (mapper.class_.__doc__ or "").strip().split("\n\n")[0]
        if table:
            docs[table] = " ".join(doc.split())
    return docs


def postgres_schema() -> dict[str, Any]:
    """Mọi bảng PostgreSQL: cột, kiểu (theo PostgreSQL), khóa chính, khóa ngoại, chỉ mục."""
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    docs = _table_docs()
    tables = []
    for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
        tables.append(
            {
                "name": table.name,
                "description": docs.get(table.name, ""),
                "columns": [
                    {
                        "name": column.name,
                        "type": str(column.type.compile(dialect=dialect)),
                        "nullable": bool(column.nullable),
                        "primary_key": bool(column.primary_key),
                        "foreign_key": [
                            {
                                "references": f"{fk.column.table.name}.{fk.column.name}",
                                "on_delete": fk.ondelete,
                            }
                            for fk in column.foreign_keys
                        ],
                    }
                    for column in table.columns
                ],
                "indexes": [
                    {"name": index.name, "columns": [c.name for c in index.columns]}
                    for index in sorted(table.indexes, key=lambda item: str(item.name))
                ],
            }
        )
    return {
        "description": "Mô hình lưu trữ PostgreSQL, sinh từ backend/studio/models.py (SQLAlchemy). "
        "Tệp gốc và các bảng dữ liệu (Parquet) nằm ở thư mục tệp, đường dẫn ghi trong "
        "datasets.storage_path, dataset_tables.parquet_path, clean_versions.parquet_path.",
        "tables": tables,
    }


def er_diagram() -> str:
    """Sơ đồ quan hệ giữa các bảng (Mermaid erDiagram), sinh từ khóa ngoại."""
    lines = [
        "# Sơ đồ quan hệ (ER) — sinh tự động",
        "",
        "Sinh từ `backend/studio/models.py` bằng `tools/export_data_docs.py`; không sửa tay.",
        "Mỗi đường nối là một khóa ngoại: bảng con (nhiều) trỏ về bảng cha (một).",
        "",
        "```mermaid",
        "erDiagram",
    ]
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    tables = sorted(Base.metadata.tables.values(), key=lambda item: item.name)
    for table in tables:
        lines.append(f"    {table.name} {{")
        for column in table.columns:
            # Mermaid chỉ nhận tên kiểu một từ: bỏ độ dài "(64)", viết gọn kiểu thời gian.
            compiled = str(column.type.compile(dialect=dialect))
            compiled = compiled.replace("TIMESTAMP WITH TIME ZONE", "TIMESTAMPTZ")
            kind = re.sub(r"\(.*\)", "", compiled).strip().replace(" ", "_")
            marks = "PK" if column.primary_key else "FK" if column.foreign_keys else ""
            lines.append(f"        {kind} {column.name} {marks}".rstrip())
        lines.append("    }")
    for table in tables:
        for fk in sorted(table.foreign_keys, key=lambda item: item.parent.name):
            parent = fk.column.table.name
            lines.append(f'    {parent} ||--o{{ {table.name} : "{fk.parent.name}"')
    lines += ["```", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- phần tĩnh: data catalog


def canonical_fields() -> dict[str, Any]:
    from studio.cleaning import REQUIRED_FIELDS
    from studio.sales_fields import SALES_FIELDS

    return {
        "description": "17 cột chuẩn của miền bán hàng (backend/studio/sales_fields.py). Mỗi cột "
        "trong tệp người dùng được ánh xạ về một cột chuẩn; mọi bước sau chỉ làm việc với cột "
        "chuẩn. 'aliases' là tên cột hay gặp (đã bỏ dấu, chữ thường) dùng cho lớp quy tắc.",
        "fields": [
            {
                "key": field.key,
                "label": field.label,
                "type": field.type,
                "meaning": field.meaning,
                "aliases": list(field.aliases),
                "required_in": sorted(
                    kind
                    for kind, groups in REQUIRED_FIELDS.items()
                    if any(field.key in group for group in groups)
                ),
            }
            for field in SALES_FIELDS
        ],
    }


def table_kinds() -> dict[str, Any]:
    from studio.cleaning import KEY_FIELD, REQUIRED_FIELDS
    from studio.sales_fields import TABLE_KIND_LABELS

    return {
        "description": "Loại bảng hệ thống nhận ra sau bước ánh xạ. 'required' là các nhóm cột "
        "bắt buộc: mỗi nhóm cần ít nhất một cột (backend/studio/cleaning.py). 'key_field' là "
        "cột mã mà mỗi dòng phải khác nhau.",
        "kinds": [
            {
                "kind": kind,
                "label": label,
                "required": [list(group) for group in REQUIRED_FIELDS.get(kind, [])],
                "key_field": KEY_FIELD.get(kind),
            }
            for kind, label in TABLE_KIND_LABELS.items()
        ],
    }


def result_kinds() -> dict[str, Any]:
    from studio.recon_api import KIND_DESCRIPTIONS, KIND_LABELS
    from studio.reconciliation import KINDS

    return {
        "description": "Các loại kết quả đối soát (backend/studio/reconciliation.py). Mọi dòng "
        "của hai bên nằm trong đúng một kết quả; kết quả cần người xem có trạng thái ngoại lệ "
        "OPEN → EXPLAINED / RESOLVED.",
        "kinds": [
            {
                "kind": kind,
                "label": KIND_LABELS.get(kind, kind),
                "description": KIND_DESCRIPTIONS.get(kind, ""),
            }
            for kind in KINDS
        ],
    }


# ---------------------------------------------------------------- phần tĩnh: schema JSON


def ai_schemas() -> dict[str, Any]:
    """Khuôn JSON bắt Gemini trả lời (structured output) và khai báo công cụ của Assistant."""
    from studio import assistant, cleaning_ai, mapping_service, recon_ai, report_ai

    return {
        "mapping-response.schema.json": mapping_service.response_schema(),
        "cleaning-suggestion-response.schema.json": cleaning_ai.response_schema(),
        "recon-explain-response.schema.json": recon_ai.response_schema(),
        "report-comment-response.schema.json": report_ai.response_schema(),
        "assistant-tools.json": assistant.tool_declarations(),
    }


def static_documents() -> dict[str, str]:
    """Mọi tệp tĩnh của data-docs: đường dẫn tương đối → nội dung."""
    from studio.main import app

    files = {
        "model/postgres-schema.json": _json(postgres_schema()),
        "model/er-diagram.md": er_diagram(),
        "catalog/canonical-fields.json": _json(canonical_fields()),
        "catalog/table-kinds.json": _json(table_kinds()),
        "catalog/result-kinds.json": _json(result_kinds()),
        "schemas/api/openapi.json": _json(app.openapi()),
    }
    for name, schema in ai_schemas().items():
        files[f"schemas/ai/{name}"] = _json(schema)
    return files


def write_static(root: Path) -> list[Path]:
    written = []
    for relative, content in static_documents().items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return written


# ---------------------------------------------------------------- phần chạy: nhật ký gọi Gemini


def _runtime() -> Path | None:
    return settings.data_docs_dir


def write_ai_call(record: dict[str, Any]) -> Path | None:
    """Ghi một lần gọi Gemini ra tệp JSON riêng. Không bao giờ ném lỗi ra ngoài."""
    root = _runtime()
    if root is None:
        return None
    try:
        now = datetime.now(VIETNAM)
        purpose = re.sub(r"[^a-z0-9-]+", "-", str(record.get("purpose", "goi")).lower())
        folder = root / "ai-calls" / now.strftime("%Y-%m-%d")
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{now.strftime('%H%M%S-%f')[:10]}_{purpose}_{uuid.uuid4().hex[:8]}.json"
        path = folder / name
        path.write_text(_json({"time": now.isoformat(), **record}), encoding="utf-8")
        return path
    except Exception:
        logger.exception("Không ghi được nhật ký gọi Gemini ra data-docs")
        return None


# ---------------------------------------------------------------- phần chạy: catalog động


def dataset_catalog(session: Session, dataset: Dataset) -> dict[str, Any]:
    """Catalog của một bộ dữ liệu: tệp gốc, từng bảng, cột, ánh xạ, phiên bản sạch, đối soát."""
    from studio import audit

    tables = []
    for table in sorted(dataset.tables, key=lambda item: item.position):
        profile = {col.get("position"): col for col in (table.profile or {}).get("columns", [])}
        mappings = {mapping.position: mapping for mapping in table.mappings}
        versions = sorted(table.clean_versions, key=lambda item: item.version)
        runs = session.scalars(
            select(ReconRun)
            .where((ReconRun.left_table_id == table.id) | (ReconRun.right_table_id == table.id))
            .order_by(ReconRun.created_at)
        ).all()
        tables.append(
            {
                "table_id": str(table.id),
                "label": audit.table_label(table),
                "sheet": table.sheet_name,
                "status": table.status,
                "header_row": table.header_row,
                "row_count": table.row_count,
                "table_kind": table.table_kind,
                "mapping_status": table.mapping_status,
                "clean_status": table.clean_status,
                "read_parquet": table.parquet_path,
                "columns": [
                    {
                        "position": position,
                        "name": name,
                        "profile": profile.get(position),
                        "mapping": None
                        if position not in mappings
                        else {
                            "field": mappings[position].field_key,
                            "status": mappings[position].status,
                            "source": mappings[position].source,
                            "confidence": mappings[position].confidence,
                            "reason": mappings[position].reason,
                        },
                    }
                    for position, name in enumerate(table.column_names)
                ],
                "clean_versions": [
                    {
                        "version_id": str(version.id),
                        "version": version.version,
                        "created_at": version.created_at,
                        "parquet": version.parquet_path,
                        "row_count": version.row_count,
                        "excluded_count": version.excluded_count,
                        "summary": version.summary,
                        "issue_count": len(version.issues or []),
                    }
                    for version in versions
                ],
                "reconciliations": [
                    {
                        "run_id": str(run.id),
                        "chain_id": str(run.chain_id) if run.chain_id else None,
                        "side": "A" if run.left_table_id == table.id else "B",
                        "status": run.status,
                        "created_at": run.created_at,
                        "period": [run.period_start, run.period_end],
                        "verified": bool((run.verification or {}).get("passed")),
                        "counts": (run.summary or {}).get("counts"),
                    }
                    for run in runs
                ],
            }
        )
    return {
        "description": "Catalog động của một bộ dữ liệu, ghi lại sau mỗi lần dữ liệu đổi. Chỉ để "
        "xem: nguồn thật là PostgreSQL và các tệp Parquet ghi đường dẫn ở đây.",
        "updated_at": datetime.now(UTC).isoformat(),
        "dataset": {
            "dataset_id": str(dataset.id),
            "name": dataset.name,
            "original_filename": dataset.original_filename,
            "format": dataset.file_format,
            "size_bytes": dataset.size_bytes,
            "sha256": dataset.sha256,
            "stored_file": dataset.storage_path,
            "status": dataset.status,
            "uploaded_at": dataset.created_at,
        },
        "tables": tables,
    }


def _catalog_path(dataset_id: uuid.UUID) -> Path | None:
    root = _runtime()
    return None if root is None else root / "catalog" / "datasets" / f"{dataset_id}.json"


def refresh_datasets(dataset_ids: set[uuid.UUID], removed: set[uuid.UUID]) -> None:
    """Ghi lại catalog của các bộ dữ liệu vừa đổi, xóa tệp của bộ đã xóa."""
    from studio import database

    try:
        for dataset_id in removed:
            path = _catalog_path(dataset_id)
            if path is not None:
                path.unlink(missing_ok=True)
        if not dataset_ids:
            return
        with database.SessionFactory() as session:
            for dataset_id in dataset_ids - removed:
                dataset = session.get(Dataset, dataset_id)
                path = _catalog_path(dataset_id)
                if dataset is None or path is None:
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(_json(dataset_catalog(session, dataset)), encoding="utf-8")
    except Exception:
        logger.exception("Không ghi được catalog động ra data-docs")


# Các đối tượng mà khi đổi thì catalog của bộ dữ liệu chứa chúng phải ghi lại.
_TRACKED = (
    Dataset,
    DatasetTable,
    ColumnMapping,
    CleanVersion,
    CellCorrection,
    RowDecision,
    ReconRun,
)
_PENDING = "data_docs_pending"


def _dataset_ids(session: Session, item: Any) -> set[uuid.UUID]:
    """Bộ dữ liệu chứa đối tượng vừa đổi. Đối tượng mới gắn qua quan hệ (ví dụ bảng thêm vào
    `dataset.tables`) chưa có mã khóa ngoại trước khi ghi, nên lấy qua quan hệ nếu có."""
    if isinstance(item, Dataset):
        return {item.id} if item.id else set()
    if isinstance(item, DatasetTable):
        dataset_id = item.dataset_id or (item.dataset.id if item.dataset else None)
        return {dataset_id} if dataset_id else set()
    if isinstance(item, ReconRun):
        table_ids = [item.left_table_id, item.right_table_id]
    else:
        related = getattr(item, "table", None)
        if related is not None:
            return _dataset_ids(session, related)
        table_ids = [item.table_id]
    found = set()
    for table_id in table_ids:
        table = session.get(DatasetTable, table_id) if table_id else None
        if table is not None:
            found |= _dataset_ids(session, table)
    return found


@event.listens_for(Session, "before_flush")
def _remember_changes(session: Session, *_: Any) -> None:
    """Ghi nhớ bộ dữ liệu nào vừa đổi trong phiên này; ghi tệp sau khi commit thành công."""
    if _runtime() is None:
        return
    pending = session.info.setdefault(_PENDING, {"changed": set(), "removed": set()})
    with session.no_autoflush:
        for item in [*session.new, *session.dirty]:
            if isinstance(item, _TRACKED):
                pending["changed"] |= _dataset_ids(session, item)
        for item in session.deleted:
            if isinstance(item, Dataset):
                pending["removed"].add(item.id)
            elif isinstance(item, _TRACKED):
                pending["changed"] |= _dataset_ids(session, item)


@event.listens_for(Session, "after_commit")
def _write_after_commit(session: Session) -> None:
    pending = session.info.pop(_PENDING, None)
    if pending and _runtime() is not None:
        refresh_datasets(pending["changed"], pending["removed"])


@event.listens_for(Session, "after_rollback")
def _forget_on_rollback(session: Session) -> None:
    session.info.pop(_PENDING, None)
