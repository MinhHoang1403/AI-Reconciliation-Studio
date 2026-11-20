"""API ánh xạ cột: xem gợi ý, đổi cột chuẩn cho một cột, xác nhận tất cả, gợi ý lại."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from studio import mapping_service
from studio.database import get_session
from studio.datasets_api import fail
from studio.models import DatasetTable
from studio.sales_fields import FIELDS_BY_KEY, SALES_FIELDS, TABLE_KIND_LABELS

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]


class FieldOption(BaseModel):
    key: str
    label: str
    type: str


class CandidateView(BaseModel):
    field: str
    label: str
    score: float


class ColumnMappingView(BaseModel):
    position: int
    column_name: str
    field_key: str | None
    field_label: str | None
    confidence: float
    status: str
    source: str
    reason: str | None
    candidates: list[CandidateView]


class TableMappingView(BaseModel):
    table_id: uuid.UUID
    status: str
    table_kind: str | None
    table_kind_label: str | None
    ai_state: str | None
    ai_message: str | None
    pending_count: int
    columns: list[ColumnMappingView]
    fields: list[FieldOption]


class FieldChoice(BaseModel):
    # Mã cột chuẩn, hoặc null để không ánh xạ cột này.
    field_key: str | None


def _table_or_404(session: Session, table_id: uuid.UUID) -> DatasetTable:
    table = session.get(DatasetTable, table_id)
    if table is None:
        raise fail(404, "TABLE_NOT_FOUND", "Không tìm thấy bảng dữ liệu.")
    return table


def view(table: DatasetTable) -> TableMappingView:
    return TableMappingView(
        table_id=table.id,
        status=table.mapping_status,
        table_kind=table.table_kind,
        table_kind_label=TABLE_KIND_LABELS.get(table.table_kind or "", None),
        ai_state=table.mapping_ai_state,
        ai_message=table.mapping_ai_message,
        pending_count=sum(mapping.status == "SUGGESTED" for mapping in table.mappings),
        columns=[
            ColumnMappingView(
                position=mapping.position,
                column_name=mapping.column_name,
                field_key=mapping.field_key,
                field_label=FIELDS_BY_KEY[mapping.field_key].label if mapping.field_key else None,
                confidence=mapping.confidence,
                status=mapping.status,
                source=mapping.source,
                reason=mapping.reason,
                candidates=[
                    CandidateView(
                        field=item["field"],
                        label=FIELDS_BY_KEY[item["field"]].label,
                        score=item["score"],
                    )
                    for item in mapping.candidates
                    if item["field"] in FIELDS_BY_KEY
                ],
            )
            for mapping in table.mappings
        ],
        fields=[
            FieldOption(key=field.key, label=field.label, type=field.type) for field in SALES_FIELDS
        ],
    )


@router.get("/tables/{table_id}/mapping")
def get_mapping(table_id: uuid.UUID, session: SessionDep) -> TableMappingView:
    return view(_table_or_404(session, table_id))


@router.put("/tables/{table_id}/mapping/columns/{position}")
def choose_field(
    table_id: uuid.UUID, position: int, choice: FieldChoice, session: SessionDep
) -> TableMappingView:
    """Người dùng chọn cột chuẩn cho một cột. Cột chuẩn đang gán cho cột khác thì cột kia
    được bỏ gán và chuyển sang "chờ xem" để người dùng không bỏ sót."""
    table = _table_or_404(session, table_id)
    if choice.field_key is not None and choice.field_key not in FIELDS_BY_KEY:
        raise fail(422, "UNKNOWN_FIELD", "Cột chuẩn không có trong danh sách.")
    target = next((mapping for mapping in table.mappings if mapping.position == position), None)
    if target is None:
        raise fail(404, "COLUMN_NOT_FOUND", "Không tìm thấy cột.")
    for other in table.mappings:
        if other is not target and choice.field_key and other.field_key == choice.field_key:
            other.field_key = None
            other.status = "SUGGESTED"
            other.reason = (
                f"Cột chuẩn đã chuyển sang cột “{target.column_name}”; hãy chọn lại cho cột này."
            )
    target.field_key = choice.field_key
    target.status, target.source, target.confidence = "CONFIRMED", "USER", 1.0
    target.reason = "Bạn đã chọn."
    mapping_service.remember(session, table)
    session.commit()
    return view(table)


@router.post("/tables/{table_id}/mapping/confirm")
def confirm_all(table_id: uuid.UUID, session: SessionDep) -> TableMappingView:
    """Đồng ý mọi gợi ý đang chờ và ghi nhớ ánh xạ cho tệp cùng cấu trúc."""
    table = _table_or_404(session, table_id)
    for mapping in table.mappings:
        if mapping.status in ("SUGGESTED", "AUTO"):
            mapping.status = "CONFIRMED"
    mapping_service.remember(session, table)
    session.commit()
    return view(table)


@router.post("/tables/{table_id}/mapping/suggest", status_code=202)
def suggest_again(
    table_id: uuid.UUID, session: SessionDep, background: BackgroundTasks
) -> TableMappingView:
    """Gợi ý lại từ đầu (bỏ qua ánh xạ đã nhớ), ví dụ khi bạn muốn AI xem lại."""
    table = _table_or_404(session, table_id)
    if table.status != "READY":
        raise fail(409, "TABLE_NOT_READY", "Bảng chưa đọc xong.")
    if table.mapping_status == "MAPPING":
        raise fail(409, "MAPPING_BUSY", "Đang gợi ý ánh xạ, hãy đợi một chút.")
    table.mapping_status = "MAPPING"
    session.commit()
    background.add_task(mapping_service.suggest_for_table, table.id, False)
    return view(table)
