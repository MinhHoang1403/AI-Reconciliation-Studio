"""Gemini đề xuất giá trị cho các ô không đọc được (quyết định 2026-11-20).

AI chỉ đề xuất; giá trị chỉ được dùng khi người dùng bấm đồng ý. Đề xuất phải đọc được bằng
chính bộ đọc giá trị của hệ thống, không thì bị bỏ. Ô chứa thông tin cá nhân được che như
khi ánh xạ; số tiền và ngày không phải thông tin cá nhân nên gửi nguyên.
"""

import logging
import uuid
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, select

from studio import config_files, database
from studio.cleaning import build_clean_version, latest_version, parse_user_value
from studio.gemini_client import BACKGROUND_ATTEMPTS, AiUnavailable, generate_json
from studio.masking import mask_sample
from studio.models import AiCellSuggestion, DatasetTable
from studio.sales_fields import FIELDS_BY_KEY

logger = logging.getLogger(__name__)

# Số ô tối đa mỗi lần gọi, để gói gửi đi nhỏ và câu trả lời gọn.
MAX_CELLS_PER_CALL = 40

# Chỉ dẫn gửi Gemini: config/prompts/cleaning-suggestion.md.
SYSTEM_INSTRUCTION = config_files.prompt("cleaning-suggestion")


class _Suggestion(BaseModel):
    id: str
    value: str | None
    confidence: float
    reason: str


class _Reply(BaseModel):
    suggestions: list[_Suggestion]


def response_schema() -> dict[str, Any]:
    return config_files.response_schema("cleaning-suggestion-response")


def _mask_cell(value: str, field_key: str) -> str:
    field_type = FIELDS_BY_KEY[field_key].type
    if field_type in ("MONEY", "DATE", "IDENTIFIER", "CATEGORY"):
        return value
    return mask_sample(value, "PHONE" if field_type == "PHONE" else "TEXT", distinct_count=1000)


def suggest_cell_fixes(table_id: uuid.UUID) -> None:
    """Gọi Gemini cho các ô không đọc được chưa có đề xuất; lưu đề xuất đã kiểm tra."""
    with database.SessionFactory() as session:
        table = session.get(DatasetTable, table_id)
        version = latest_version(table) if table is not None else None
        if table is None or version is None:
            return
        # Đã hỏi AI cho đúng ô này với đúng giá trị gốc này thì không hỏi lại; ô đổi giá trị
        # (ví dụ ánh xạ sang cột khác) thì gợi ý cũ hết hạn và được hỏi lại.
        known = {
            (item.row_ref, item.field_key, item.raw_value)
            for item in session.scalars(
                select(AiCellSuggestion).where(AiCellSuggestion.table_id == table_id)
            )
        }
        open_cells = [
            issue
            for issue in version.issues
            if issue["kind"] == "INVALID_VALUE"
            and issue["status"] == "OPEN"
            and (issue["row_refs"][0], issue["field_key"], issue["values"][0] or "") not in known
        ][:MAX_CELLS_PER_CALL]
        if not open_cells:
            return
        examples = _context_examples(
            version.parquet_path, {issue["field_key"] for issue in open_cells}
        )
        # Báo cho giao diện biết AI đang đề xuất, để nó tự tải lại khi có gợi ý.
        table.clean_status = "SUGGESTING"
        session.commit()
    try:
        _ask_ai_and_save(table_id, open_cells, examples)
    finally:
        with database.SessionFactory() as session:
            table = session.get(DatasetTable, table_id)
            if table is not None and table.clean_status == "SUGGESTING":
                table.clean_status = "READY"
                session.commit()


def _ask_ai_and_save(
    table_id: uuid.UUID, open_cells: list[dict[str, Any]], examples: dict[str, list[str]]
) -> None:
    cells = [
        {
            "id": issue["id"],
            "field": issue["field_key"],
            "field_label": FIELDS_BY_KEY[issue["field_key"]].label,
            "field_type": FIELDS_BY_KEY[issue["field_key"]].type,
            "value": _mask_cell(issue["values"][0] or "", issue["field_key"]),
            "context_examples": examples.get(issue["field_key"], []),
        }
        for issue in open_cells
    ]
    try:
        reply = generate_json(
            purpose="goi-y-sua-o",
            system_instruction=SYSTEM_INSTRUCTION,
            payload={"cells": cells},
            response_schema=response_schema(),
            table_id=table_id,
            attempts=BACKGROUND_ATTEMPTS,
        )
        parsed = _Reply.model_validate(reply.data)
    except (AiUnavailable, ValidationError) as error:
        logger.info("Không có gợi ý sửa ô từ AI cho bảng %s: %s", table_id, error)
        return

    by_id = {issue["id"]: issue for issue in open_cells}
    with database.SessionFactory() as session:
        # Người dùng có thể đã xóa bộ dữ liệu trong lúc chờ Gemini: không còn gì để lưu.
        if session.get(DatasetTable, table_id) is None:
            return
        for item in parsed.suggestions:
            issue = by_id.get(item.id)
            if issue is None:
                continue  # id không có thật
            value = item.value
            if value is not None and parse_user_value(value, issue["field_key"]).state != "VALID":
                value = None  # đề xuất không đọc được bằng bộ đọc của hệ thống thì bỏ
            # Thay gợi ý cũ (đã hết hạn) của cùng ô.
            session.execute(
                delete(AiCellSuggestion).where(
                    AiCellSuggestion.table_id == table_id,
                    AiCellSuggestion.row_ref == issue["row_refs"][0],
                    AiCellSuggestion.field_key == issue["field_key"],
                )
            )
            session.add(
                AiCellSuggestion(
                    id=uuid.uuid4(),
                    table_id=table_id,
                    row_ref=issue["row_refs"][0],
                    field_key=issue["field_key"],
                    raw_value=issue["values"][0] or "",
                    suggested_value=value,
                    confidence=max(0.0, min(1.0, item.confidence)),
                    reason=item.reason if value is not None else f"AI chưa chắc: {item.reason}",
                )
            )
        session.commit()


def refresh_clean_data(table_id: uuid.UUID) -> None:
    """Dựng lại bộ sạch rồi xin AI gợi ý cho ô mới không đọc được (chạy nền)."""
    build_clean_version(table_id)
    try:
        suggest_cell_fixes(table_id)
    except Exception:
        logger.exception("Lỗi khi xin gợi ý sửa ô cho bảng %s (bỏ qua)", table_id)


def _context_examples(parquet_path: str, field_keys: set[str]) -> dict[str, list[str]]:
    """Vài giá trị đã chuẩn hóa của cùng cột (tiền, ngày, mã) để AI biết ngữ cảnh, ví dụ năm."""
    import polars as pl

    frame = pl.read_parquet(parquet_path)
    examples: dict[str, list[str]] = {}
    for key in field_keys:
        if key in frame.columns and FIELDS_BY_KEY[key].type in ("MONEY", "DATE", "IDENTIFIER"):
            values = frame[key].drop_nulls().head(5).to_list()
            examples[key] = [
                value.isoformat() if hasattr(value, "isoformat") else str(value) for value in values
            ]
    return examples
