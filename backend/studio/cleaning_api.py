"""API làm sạch: xem tóm tắt và vấn đề, sửa ô, giữ/loại dòng, dùng gợi ý AI, đổi thứ tự ngày."""

import uuid
from typing import Annotated, Any, Literal

import polars as pl
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from studio.cleaning import latest_version, parse_user_value, source_cell
from studio.cleaning_ai import refresh_clean_data
from studio.database import get_session
from studio.datasets_api import fail
from studio.models import AiCellSuggestion, CellCorrection, DatasetTable, RowDecision
from studio.reading import ROW_REF
from studio.sales_fields import FIELDS_BY_KEY

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]


class CellFix(BaseModel):
    row_ref: int
    field_key: str
    value: str = Field(min_length=1, max_length=200)


class RowsDecision(BaseModel):
    row_refs: list[int] = Field(min_length=1, max_length=1000)
    decision: Literal["EXCLUDE", "KEEP", "UNDO"]
    reason: str = Field(default="USER", max_length=64)


class DateOrderChoice(BaseModel):
    field_key: str
    order: Literal["DMY", "MDY"]


def _table_or_404(session: Session, table_id: uuid.UUID) -> DatasetTable:
    table = session.get(DatasetTable, table_id)
    if table is None:
        raise fail(404, "TABLE_NOT_FOUND", "Không tìm thấy bảng dữ liệu.")
    return table


def _rebuild(session: Session, table: DatasetTable, background: BackgroundTasks) -> dict[str, Any]:
    table.clean_status = "BUILDING"
    session.commit()
    background.add_task(refresh_clean_data, table.id)
    return cleaning_view(session, table)


def _save_correction(
    session: Session, table: DatasetTable, row_ref: int, field_key: str, value: str, source: str
) -> None:
    """Ghi giá trị sửa cho một ô (thay bản cũ), kèm ô gốc lúc sửa để biết khi nào hết hiệu lực."""
    cell = source_cell(table, row_ref, field_key)
    if cell is None:
        raise fail(404, "CELL_NOT_FOUND", "Không tìm thấy ô này trong bảng.")
    session.execute(
        delete(CellCorrection).where(
            CellCorrection.table_id == table.id,
            CellCorrection.row_ref == row_ref,
            CellCorrection.field_key == field_key,
        )
    )
    session.add(
        CellCorrection(
            id=uuid.uuid4(),
            table_id=table.id,
            row_ref=row_ref,
            field_key=field_key,
            value=value,
            source=source,
            source_column=cell[0],
            original_value=cell[1],
        )
    )


def cleaning_view(session: Session, table: DatasetTable) -> dict[str, Any]:
    version = latest_version(table)
    suggestions = {
        (item.row_ref, item.field_key): item
        for item in session.scalars(
            select(AiCellSuggestion).where(AiCellSuggestion.table_id == table.id)
        )
    }
    issues = []
    for issue in version.issues if version else []:
        item = dict(issue)
        suggestion = (
            suggestions.get((issue["row_refs"][0], issue["field_key"]))
            if issue["field_key"]
            else None
        )
        # Gợi ý chỉ còn đúng khi ô vẫn mang đúng giá trị gốc lúc AI được hỏi.
        item["ai_suggestion"] = (
            None
            if suggestion is None
            or issue["kind"] != "INVALID_VALUE"
            or suggestion.raw_value != (issue["values"][0] or "")
            else {
                "value": suggestion.suggested_value,
                "confidence": suggestion.confidence,
                "reason": suggestion.reason,
            }
        )
        issues.append(item)
    open_issues = [issue for issue in issues if issue["status"] == "OPEN"]
    return {
        "table_id": str(table.id),
        "status": table.clean_status,
        "version": version.version if version else None,
        "row_count": version.row_count if version else 0,
        "excluded_count": version.excluded_count if version else 0,
        "summary": version.summary if version else None,
        "open_counts": {
            level: sum(issue["level"] == level for issue in open_issues)
            for level in ("SUGGEST", "ASK")
        },
        "issues": issues,
    }


@router.get("/tables/{table_id}/cleaning")
def get_cleaning(table_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
    return cleaning_view(session, _table_or_404(session, table_id))


@router.post("/tables/{table_id}/cleaning/cells", status_code=202)
def fix_cell(
    table_id: uuid.UUID, fix: CellFix, session: SessionDep, background: BackgroundTasks
) -> dict[str, Any]:
    """Người dùng nhập giá trị đúng cho một ô; giá trị phải đọc được theo kiểu cột chuẩn."""
    table = _table_or_404(session, table_id)
    if fix.field_key not in FIELDS_BY_KEY:
        raise fail(422, "UNKNOWN_FIELD", "Cột chuẩn không có trong danh sách.")
    if parse_user_value(fix.value, fix.field_key).state != "VALID":
        label = FIELDS_BY_KEY[fix.field_key].label.lower()
        raise fail(422, "INVALID_VALUE", f"“{fix.value}” không phải {label} hợp lệ.")
    _save_correction(session, table, fix.row_ref, fix.field_key, fix.value.strip(), "USER")
    return _rebuild(session, table, background)


@router.post("/tables/{table_id}/cleaning/suggestions/accept", status_code=202)
def accept_suggestion(
    table_id: uuid.UUID,
    session: SessionDep,
    background: BackgroundTasks,
    row_ref: Annotated[int, Query()],
    field_key: Annotated[str, Query()],
) -> dict[str, Any]:
    """Đồng ý giá trị AI đề xuất cho một ô."""
    table = _table_or_404(session, table_id)
    suggestion = session.scalar(
        select(AiCellSuggestion).where(
            AiCellSuggestion.table_id == table_id,
            AiCellSuggestion.row_ref == row_ref,
            AiCellSuggestion.field_key == field_key,
        )
    )
    if suggestion is None or suggestion.suggested_value is None:
        raise fail(404, "SUGGESTION_NOT_FOUND", "Không có gợi ý cho ô này.")
    cell = source_cell(table, row_ref, field_key)
    if cell is None or (cell[1] or "") != suggestion.raw_value:
        # Ô đã đổi (ánh xạ sang cột khác, đọc lại tiêu đề): gợi ý cũ không còn đúng ô.
        raise fail(409, "SUGGESTION_STALE", "Gợi ý này đã cũ vì ô đã thay đổi.")
    _save_correction(session, table, row_ref, field_key, suggestion.suggested_value, "AI")
    return _rebuild(session, table, background)


@router.post("/tables/{table_id}/cleaning/rows", status_code=202)
def decide_rows(
    table_id: uuid.UUID, choice: RowsDecision, session: SessionDep, background: BackgroundTasks
) -> dict[str, Any]:
    """Loại dòng khỏi bộ sạch, giữ dòng (ví dụ giao dịch lặp thật), hoặc bỏ quyết định cũ."""
    table = _table_or_404(session, table_id)
    session.execute(
        delete(RowDecision).where(
            RowDecision.table_id == table_id, RowDecision.row_ref.in_(choice.row_refs)
        )
    )
    if choice.decision != "UNDO":
        for ref in choice.row_refs:
            session.add(
                RowDecision(
                    id=uuid.uuid4(),
                    table_id=table_id,
                    row_ref=ref,
                    decision=choice.decision,
                    reason=choice.reason,
                )
            )
    return _rebuild(session, table, background)


@router.post("/tables/{table_id}/cleaning/duplicates/accept", status_code=202)
def accept_duplicate_suggestions(
    table_id: uuid.UUID, session: SessionDep, background: BackgroundTasks
) -> dict[str, Any]:
    """Đồng ý mọi gợi ý dòng trùng: giữ dòng đầu của mỗi nhóm, loại các bản lặp."""
    table = _table_or_404(session, table_id)
    version = latest_version(table)
    extra = [
        ref
        for issue in (version.issues if version else [])
        if issue["kind"] == "DUPLICATE_ROW" and issue["status"] == "OPEN"
        for ref in issue["row_refs"][1:]
    ]
    if not extra:
        return cleaning_view(session, table)
    session.execute(
        delete(RowDecision).where(RowDecision.table_id == table_id, RowDecision.row_ref.in_(extra))
    )
    for ref in extra:
        session.add(
            RowDecision(
                id=uuid.uuid4(),
                table_id=table_id,
                row_ref=ref,
                decision="EXCLUDE",
                reason="DUPLICATE",
            )
        )
    return _rebuild(session, table, background)


@router.put("/tables/{table_id}/cleaning/date-order", status_code=202)
def choose_date_order(
    table_id: uuid.UUID, choice: DateOrderChoice, session: SessionDep, background: BackgroundTasks
) -> dict[str, Any]:
    """Đổi cách đọc cả cột ngày: ngày/tháng hoặc tháng/ngày."""
    table = _table_or_404(session, table_id)
    if choice.field_key not in FIELDS_BY_KEY or FIELDS_BY_KEY[choice.field_key].type != "DATE":
        raise fail(422, "NOT_A_DATE_FIELD", "Cột này không phải cột ngày.")
    options = dict(table.clean_options or {})
    orders = dict(options.get("date_orders", {}))
    orders[choice.field_key] = choice.order
    options["date_orders"] = orders
    table.clean_options = options
    return _rebuild(session, table, background)


@router.post("/tables/{table_id}/cleaning/rebuild", status_code=202)
def rebuild(
    table_id: uuid.UUID, session: SessionDep, background: BackgroundTasks
) -> dict[str, Any]:
    """Dựng lại bộ dữ liệu sạch (ví dụ sau khi lần dựng trước bị gián đoạn)."""
    return _rebuild(session, _table_or_404(session, table_id), background)


@router.get("/tables/{table_id}/clean-rows")
def clean_rows(
    table_id: uuid.UUID,
    session: SessionDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    """Xem trước bộ dữ liệu sạch (giá trị chuẩn, kèm số dòng gốc)."""
    table = _table_or_404(session, table_id)
    version = latest_version(table)
    if version is None:
        raise fail(409, "CLEAN_NOT_READY", "Chưa có bộ dữ liệu sạch.")
    page = pl.scan_parquet(version.parquet_path).slice(offset, limit).collect()
    columns = [name for name in page.columns if name != ROW_REF]
    return {
        "columns": [
            {
                "key": name,
                "type": FIELDS_BY_KEY[name].type if name in FIELDS_BY_KEY else "TEXT",
                "label": FIELDS_BY_KEY[name].label
                if name in FIELDS_BY_KEY
                else {"customer_name_key": "Tên để so khớp", "is_cancelled": "Đã hủy"}.get(
                    name, name
                ),
            }
            for name in columns
        ],
        "row_refs": page[ROW_REF].to_list(),
        "rows": [
            [
                None
                if value is None
                else (value.isoformat() if hasattr(value, "isoformat") else str(value))
                for value in row
            ]
            for row in page.select(columns).iter_rows()
        ],
        "offset": offset,
        "limit": limit,
        "total": version.row_count,
    }
