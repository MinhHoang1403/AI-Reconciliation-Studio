"""Các bảng trong cơ sở dữ liệu.

Dữ liệu dạng bảng lớn (các dòng đã đọc) nằm trong tệp Parquet; DB chỉ giữ thông tin mô tả.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
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


class Workspace(Base):
    """Một phiên làm việc: không gian riêng có tệp, kỳ, kết quả đối soát, báo cáo, cuộc trò
    chuyện, nhật ký và bộ nhớ ánh xạ của riêng nó. Mở phiên mới là bắt đầu từ trang trắng.

    `domain` là lĩnh vực đối soát của phiên; hiện chỉ có bán hàng (SALES), các lĩnh vực khác
    (kế toán, công nợ…) thêm sau mà không phải đổi cấu trúc."""

    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    domain: Mapped[str] = mapped_column(String(32), default="SALES")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def _workspace_column() -> Mapped[uuid.UUID]:
    """Cột phiên làm việc của các bảng gốc; xóa phiên thì xóa theo."""
    return mapped_column(Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)


class Dataset(Base):
    """Một tệp người dùng đã tải lên. Tệp gốc được giữ nguyên, nhận diện bằng SHA-256."""

    __tablename__ = "datasets"
    # Cùng một tệp được tải vào hai phiên khác nhau là hai bộ dữ liệu riêng; trong một phiên
    # thì tải lại đúng tệp cũ được nhận ra là trùng.
    __table_args__ = (UniqueConstraint("workspace_id", "sha256"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_column()
    name: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_format: Mapped[str] = mapped_column(String(8))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # Dấu vân tay của tệp gốc; tải lại đúng tệp cũ thì nhận ra nhờ cột này.
    sha256: Mapped[str] = mapped_column(String(64))
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
    # Làm sạch: NONE (chưa), BUILDING (đang dựng bộ sạch), READY, FAILED.
    clean_status: Mapped[str] = mapped_column(String(16), default="NONE")
    # Lựa chọn của người dùng khi làm sạch, ví dụ {"date_orders": {"order_date": "MDY"}}.
    clean_options: Mapped[dict[str, Any]] = mapped_column(default=dict)

    dataset: Mapped[Dataset] = relationship(back_populates="tables")
    clean_versions: Mapped[list["CleanVersion"]] = relationship(
        back_populates="table", cascade="all, delete-orphan", order_by="CleanVersion.version"
    )
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
    """Ánh xạ đã được xác nhận, nhớ theo chữ ký cấu trúc bảng (tập tên cột đã chuẩn hóa),
    riêng cho từng phiên làm việc (phiên mới không mang theo ánh xạ của phiên khác)."""

    __tablename__ = "mapping_memory"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    signature: Mapped[str] = mapped_column(String(64), primary_key=True)
    table_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # {tên cột: mã cột chuẩn hoặc null}
    mapping: Mapped[dict[str, Any]] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CleanVersion(Base):
    """Một phiên bản bộ dữ liệu sạch của bảng. Dựng lại từ đầu mỗi khi ánh xạ hoặc sửa đổi
    thay đổi; tệp Parquet của mỗi phiên bản không bao giờ bị ghi đè."""

    __tablename__ = "clean_versions"
    # Mỗi bảng không có hai phiên bản cùng số (chặn thêm một lớp ngoài khóa theo bảng).
    __table_args__ = (
        UniqueConstraint("table_id", "version", name="uq_clean_versions_table_id_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("dataset_tables.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    parquet_path: Mapped[str] = mapped_column(Text)
    row_count: Mapped[int] = mapped_column(Integer)
    excluded_count: Mapped[int] = mapped_column(Integer)
    # Tóm tắt: các loại sửa tự động, số đơn hủy, thứ tự ngày của từng cột ngày.
    summary: Mapped[dict[str, Any]] = mapped_column()
    # Danh sách vấn đề (mỗi vấn đề gắn với dòng/ô cụ thể, mức SUGGEST hoặc ASK).
    issues: Mapped[list[Any]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    table: Mapped[DatasetTable] = relationship(back_populates="clean_versions")


class CellCorrection(Base):
    """Giá trị người dùng nhập (hoặc đồng ý theo gợi ý AI) cho một ô; tệp gốc không bị sửa."""

    __tablename__ = "cell_corrections"
    __table_args__ = (UniqueConstraint("table_id", "row_ref", "field_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("dataset_tables.id", ondelete="CASCADE"), index=True
    )
    row_ref: Mapped[int] = mapped_column(Integer)
    field_key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))  # USER hoặc AI (người dùng đồng ý gợi ý AI)
    # Ô gốc lúc sửa: tên cột trong tệp và giá trị gốc. Nếu sau đó cột chuẩn được ánh xạ sang
    # cột khác hoặc đọc lại với dòng tiêu đề khác, ô không còn là ô đã sửa nên bỏ qua giá trị
    # sửa. Để trống ở các bản sửa trước khi có hai cột này (khi đó vẫn áp dụng như cũ).
    source_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RowDecision(Base):
    """Quyết định của người dùng cho một dòng: loại khỏi bộ sạch (EXCLUDE) hay giữ (KEEP)."""

    __tablename__ = "row_decisions"
    __table_args__ = (UniqueConstraint("table_id", "row_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("dataset_tables.id", ondelete="CASCADE"), index=True
    )
    row_ref: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiCellSuggestion(Base):
    """Giá trị Gemini đề xuất cho một ô không đọc được; chỉ áp dụng khi người dùng đồng ý."""

    __tablename__ = "ai_cell_suggestions"
    __table_args__ = (UniqueConstraint("table_id", "row_ref", "field_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("dataset_tables.id", ondelete="CASCADE"), index=True
    )
    row_ref: Mapped[int] = mapped_column(Integer)
    field_key: Mapped[str] = mapped_column(String(64))
    raw_value: Mapped[str] = mapped_column(Text)
    suggested_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text)


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


class ReconRun(Base):
    """Một lần đối soát hai bảng sạch A ↔ B: cấu hình, kỳ, tóm tắt và kết quả kiểm chứng."""

    __tablename__ = "recon_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    left_table_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("dataset_tables.id", ondelete="CASCADE"), index=True
    )
    right_table_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("dataset_tables.id", ondelete="CASCADE"), index=True
    )
    # Phiên bản bộ sạch đã dùng: kết quả luôn truy ngược được về đúng dữ liệu lúc chạy.
    left_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("clean_versions.id", ondelete="CASCADE"), nullable=True
    )
    right_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("clean_versions.id", ondelete="CASCADE"), nullable=True
    )
    # RUNNING (đang chạy), READY (xong), FAILED (lỗi).
    status: Mapped[str] = mapped_column(String(16), default="RUNNING")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column()
    # Kỳ đối soát suy từ khoảng ngày của dữ liệu hai bên.
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    # {"passed": bool, "checks": [...]}; không đạt thì không dùng cho báo cáo.
    verification: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Lần chạy thuộc một chuỗi ba bên (đơn hàng ↔ cổng ↔ sao kê) thì có mã chuỗi.
    chain_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("recon_chains.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Dòng chờ tiền về nhận từ kỳ trước: [{"table_id", "version_id", "row_ref"}].
    carried: Mapped[list[Any] | None] = mapped_column(nullable=True)


class ReconChain(Base):
    """Một lần đối soát cả chuỗi của một kỳ: chạy mọi cặp bảng nối được với nhau."""

    __tablename__ = "recon_chains"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_column()
    # RUNNING (đang chạy), READY (xong), FAILED (lỗi).
    status: Mapped[str] = mapped_column(String(16), default="RUNNING")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    label: Mapped[str] = mapped_column(Text)
    table_ids: Mapped[list[Any]] = mapped_column()
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Nhận xét AI của báo cáo kỳ này (chỉ viết khi người dùng bấm): {"text", "fingerprint",
    # "created_at"}; fingerprint khác số liệu hiện tại thì báo nhận xét đã cũ.
    report_comment: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)


class ReconChoice(Base):
    """Lựa chọn của người dùng (chọn ca mơ hồ, ghép tay, gỡ ghép); áp dụng ở mọi lần chạy sau
    của cùng cặp bảng."""

    __tablename__ = "recon_choices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    left_table_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("dataset_tables.id", ondelete="CASCADE"), index=True
    )
    right_table_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("dataset_tables.id", ondelete="CASCADE"), index=True
    )
    left_refs: Mapped[list[Any]] = mapped_column()
    right_refs: Mapped[list[Any]] = mapped_column()
    # MATCH: ghép các dòng này với nhau (chọn ca mơ hồ, ghép tay); UNMATCH: không được tự ghép
    # các dòng này với nhau nữa (gỡ ghép).
    action: Mapped[str] = mapped_column(String(16), default="MATCH", server_default="MATCH")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MatchResult(Base):
    """Một kết quả đối soát: loại, các dòng hai bên, điểm, lý do và trạng thái ngoại lệ."""

    __tablename__ = "match_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("recon_runs.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(24))
    left_refs: Mapped[list[Any]] = mapped_column()
    right_refs: Mapped[list[Any]] = mapped_column()
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # [{"code": ..., "text": ...}] do engine sinh ra; Gemini chỉ diễn giải lại khi được hỏi.
    reasons: Mapped[list[Any]] = mapped_column()
    amount_left: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    amount_right: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    # Ngoại lệ: OPEN (cần xem) → EXPLAINED (đã ghi chú) / RESOLVED (đã xử lý); trống nếu
    # kết quả không cần người xem (khớp, ngoài phạm vi).
    exception_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Dòng chờ từ kỳ trước nằm trong kết quả này: [{"table_id", "version_id", "row_ref"}].
    carried_left: Mapped[list[Any] | None] = mapped_column(nullable=True)


class AuditLog(Base):
    """Nhật ký kiểm toán: mọi thay đổi của người dùng, ai làm, lúc nào, trước và sau."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Nhật ký thuộc phiên nơi thao tác diễn ra; chỉ mất khi cả phiên bị xóa.
    workspace_id: Mapped[uuid.UUID] = _workspace_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(48))
    # Không dùng khóa ngoại: nhật ký giữ lại kể cả khi đối tượng đã bị xóa.
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str] = mapped_column(String(64))
    object_label: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    before: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)


class ChatThread(Base):
    """Một cuộc trò chuyện với AI Assistant."""

    __tablename__ = "chat_threads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = _workspace_column()
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ChatMessage.position",
    )


class ChatMessage(Base):
    """Một tin nhắn: của người dùng, hoặc câu trả lời của Assistant kèm các bước đã làm.

    Câu trả lời của Assistant có `steps` (từng công cụ đã chạy, để giao diện hiện "đang làm
    gì"), `actions` (thẻ xác nhận cho thao tác thay đổi, chỉ chạy khi người dùng bấm) và
    `links` (nút dẫn sang trang Dữ liệu / Đối soát).
    """

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    # "user" hoặc "assistant".
    role: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text, default="")
    # RUNNING (Assistant đang làm), DONE, FAILED.
    status: Mapped[str] = mapped_column(String(16), default="DONE")
    # Tệp người dùng đính kèm: [{"dataset_id", "name"}].
    attachments: Mapped[list[Any]] = mapped_column(default=list)
    steps: Mapped[list[Any]] = mapped_column(default=list)
    actions: Mapped[list[Any]] = mapped_column(default=list)
    links: Mapped[list[Any]] = mapped_column(default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    thread: Mapped[ChatThread] = relationship(back_populates="messages")
