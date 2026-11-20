"""Các bảng trong cơ sở dữ liệu.

Dữ liệu dạng bảng lớn (các dòng đã đọc) nằm trong tệp Parquet; DB chỉ giữ thông tin mô tả.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

type DatasetStatus = Literal["READING", "READY", "FAILED"]
# NO_DATA: sheet không có bảng dữ liệu (ví dụ sheet chỉ có ghi chú).
type TableStatus = Literal["READING", "READY", "NO_DATA", "FAILED"]
type FileFormat = Literal["CSV", "XLSX"]


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class Dataset(Base):
    """Một tệp người dùng đã tải lên. Tệp gốc được giữ nguyên, nhận diện bằng SHA-256."""

    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_format: Mapped[str] = mapped_column(String(8))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # Dấu vân tay của tệp gốc; tải lại đúng tệp cũ thì nhận ra nhờ cột này.
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    storage_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="READING")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tables: Mapped[list["DatasetTable"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", order_by="DatasetTable.position"
    )


class DatasetTable(Base):
    """Một bảng đọc được từ tệp: CSV có một bảng, Excel có một bảng cho mỗi sheet hiển thị."""

    __tablename__ = "dataset_tables"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    # Tên sheet trong Excel; CSV không có sheet nên để trống.
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="READING")
    # Dòng tiêu đề, tính từ 1 theo số dòng trong tệp gốc; người dùng có thể chỉnh.
    header_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    header_row_chosen_by_user: Mapped[bool] = mapped_column(default=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    column_names: Mapped[list[Any]] = mapped_column(default=list)
    parquet_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Loại bảng đoán được khi ánh xạ (đơn hàng sàn, sao kê…), xem sales_fields.TableKind.
    table_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Trạng thái ánh xạ: NONE (chưa), MAPPING (đang gợi ý), READY (đã có gợi ý).
    mapping_status: Mapped[str] = mapped_column(String(16), default="NONE")
    # AI có được dùng không: AI (đã dùng), MEMORY (dùng ánh xạ đã nhớ),
    # NOT_CONFIGURED (thiếu khóa), FAILED (Gemini lỗi) — kèm thông điệp.
    mapping_ai_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    mapping_ai_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    dataset: Mapped[Dataset] = relationship(back_populates="tables")
    mappings: Mapped[list["ColumnMapping"]] = relationship(
        back_populates="table", cascade="all, delete-orphan", order_by="ColumnMapping.position"
    )


class ColumnMapping(Base):
    """Ánh xạ một cột của bảng về cột chuẩn (hoặc không ánh xạ: field_key rỗng)."""

    __tablename__ = "column_mappings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("dataset_tables.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    column_name: Mapped[str] = mapped_column(String(255))
    field_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # AUTO: hệ thống tự áp dụng; SUGGESTED: chờ người dùng xem; CONFIRMED: người dùng đã duyệt.
    status: Mapped[str] = mapped_column(String(16))
    # Nguồn: RULE (quy tắc), AI, RULE_AI (hai bên đồng ý), MEMORY (đã nhớ), USER (người dùng chọn).
    source: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Ứng viên theo quy tắc: [{"field": ..., "score": ...}], để giao diện gợi ý thay thế.
    candidates: Mapped[list[Any]] = mapped_column(default=list)

    table: Mapped[DatasetTable] = relationship(back_populates="mappings")


class MappingMemory(Base):
    """Ánh xạ đã được xác nhận, nhớ theo chữ ký cấu trúc bảng (tập tên cột đã chuẩn hóa)."""

    __tablename__ = "mapping_memory"

    signature: Mapped[str] = mapped_column(String(64), primary_key=True)
    table_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # {tên cột: mã cột chuẩn hoặc null}
    mapping: Mapped[dict[str, Any]] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AiCall(Base):
    """Nhật ký từng lần gọi AI: mục đích, model, kết quả, token, thời gian (không lưu nội dung)."""

    __tablename__ = "ai_calls"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    purpose: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    # Không dùng khóa ngoại: nhật ký giữ lại kể cả khi bảng dữ liệu đã bị xóa.
    table_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
