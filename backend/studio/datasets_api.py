"""API bộ dữ liệu: tải tệp lên, xem danh sách, xem dòng, hồ sơ cột, đọc lại, xóa."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import polars as pl
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio import ingestion, reading, storage
from studio.config import settings
from studio.database import get_session
from studio.models import Dataset, DatasetTable

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]

# Đuôi tệp được nhận và định dạng tương ứng.
FORMATS = {"csv": "CSV", "xlsx": "XLSX"}
MAX_PAGE_SIZE = 200


def fail(status_code: int, code: str, message: str) -> HTTPException:
    """Lỗi trả về cho giao diện: mã lỗi để xử lý, thông điệp tiếng Việt để hiển thị."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


# ---------------------------------------------------------------- kiểu dữ liệu trả về

class TableSummary(BaseModel):
    id: uuid.UUID
    sheet_name: str | None
    position: int
    status: str
    header_row: int | None
    header_row_chosen_by_user: bool
    row_count: int
    column_count: int
    error_message: str | None
    # Ánh xạ cột: trạng thái, loại bảng đoán được và số cột đang chờ người dùng xem.
    mapping_status: str
    table_kind: str | None
    mapping_pending: int


class DatasetSummary(BaseModel):
    id: uuid.UUID
    name: str
    original_filename: str
    file_format: str
    size_bytes: int
    sha256: str
    status: str
    error_message: str | None
    created_at: datetime
    tables: list[TableSummary]


class UploadReply(BaseModel):
    dataset: DatasetSummary
    # True khi đúng tệp này đã được tải lên trước đó; không lưu thêm bản mới.
    duplicate: bool


class RowsPage(BaseModel):
    table_id: uuid.UUID
    columns: list[str]
    row_refs: list[int]
    rows: list[list[str | None]]
    offset: int
    limit: int
    total: int


class HeaderChoice(BaseModel):
    # Số dòng tiêu đề trong tệp gốc (tính từ 1); null nghĩa là bảng không có dòng tiêu đề.
    header_row: int | None = Field(default=None, ge=1)


def summarize(dataset: Dataset) -> DatasetSummary:
    return DatasetSummary(
        id=dataset.id, name=dataset.name, original_filename=dataset.original_filename,
        file_format=dataset.file_format, size_bytes=dataset.size_bytes, sha256=dataset.sha256,
        status=dataset.status, error_message=dataset.error_message, created_at=dataset.created_at,
        tables=[
            TableSummary(
                id=table.id, sheet_name=table.sheet_name, position=table.position,
                status=table.status, header_row=table.header_row,
                header_row_chosen_by_user=table.header_row_chosen_by_user,
                row_count=table.row_count, column_count=len(table.column_names),
                error_message=table.error_message,
                mapping_status=table.mapping_status, table_kind=table.table_kind,
                mapping_pending=sum(mapping.status == "SUGGESTED" for mapping in table.mappings),
            )
            for table in dataset.tables
        ],
    )


def _dataset_or_404(session: Session, dataset_id: uuid.UUID) -> Dataset:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise fail(404, "DATASET_NOT_FOUND", "Không tìm thấy bộ dữ liệu.")
    return dataset


def _ready_table_or_error(session: Session, table_id: uuid.UUID) -> tuple[DatasetTable, str]:
    """Bảng đã đọc xong cùng đường dẫn tệp Parquet của nó."""
    table = session.get(DatasetTable, table_id)
    if table is None:
        raise fail(404, "TABLE_NOT_FOUND", "Không tìm thấy bảng dữ liệu.")
    if table.status != "READY" or table.parquet_path is None:
        raise fail(409, "TABLE_NOT_READY", "Bảng chưa đọc xong hoặc không có dữ liệu.")
    return table, table.parquet_path


# ---------------------------------------------------------------- tải tệp lên

@router.post("/datasets", status_code=202)
def upload_dataset(
    file: UploadFile, session: SessionDep, response: Response, background: BackgroundTasks
) -> UploadReply:
    filename = Path(file.filename or "tep-tai-len").name
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in FORMATS:
        raise fail(415, "UNSUPPORTED_FORMAT",
                   "Chỉ nhận tệp CSV hoặc Excel (.xlsx). Tệp .xls cũ hãy lưu lại thành .xlsx.")
    try:
        upload = storage.receive_upload(file.file)
    except storage.UploadTooLarge as error:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise fail(413, "FILE_TOO_LARGE", f"Tệp lớn hơn {limit_mb} MB.") from error
    if upload.size_bytes == 0:
        upload.temp_path.unlink(missing_ok=True)
        raise fail(422, "EMPTY_FILE", "Tệp trống.")
    # CSV phải là UTF-8: kiểm ngay để báo lỗi tức thì, không lưu tệp sai bảng mã.
    if extension == "csv":
        try:
            reading.decode_utf8(upload.temp_path.read_bytes())
        except reading.ReadError as error:
            upload.temp_path.unlink(missing_ok=True)
            raise fail(422, "NOT_UTF8", str(error)) from error

    existing = session.scalar(select(Dataset).where(Dataset.sha256 == upload.sha256))
    if existing is not None:
        upload.temp_path.unlink(missing_ok=True)
        response.status_code = 200
        return UploadReply(dataset=summarize(existing), duplicate=True)

    raw_path = storage.keep_raw_file(upload, extension)
    dataset = Dataset(
        id=uuid.uuid4(), name=filename.rsplit(".", 1)[0], original_filename=filename,
        file_format=FORMATS[extension], size_bytes=upload.size_bytes, sha256=upload.sha256,
        storage_path=str(raw_path), status="READING",
    )
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    background.add_task(ingestion.read_dataset, dataset.id)
    return UploadReply(dataset=summarize(dataset), duplicate=False)


# ---------------------------------------------------------------- xem

@router.get("/datasets")
def list_datasets(session: SessionDep) -> list[DatasetSummary]:
    datasets = session.scalars(select(Dataset).order_by(Dataset.created_at.desc())).all()
    return [summarize(dataset) for dataset in datasets]


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: uuid.UUID, session: SessionDep) -> DatasetSummary:
    return summarize(_dataset_or_404(session, dataset_id))


@router.get("/tables/{table_id}/rows")
def table_rows(
    table_id: uuid.UUID, session: SessionDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
) -> RowsPage:
    table, parquet_path = _ready_table_or_error(session, table_id)
    page = pl.scan_parquet(parquet_path).slice(offset, limit).collect()
    columns = list(table.column_names)
    return RowsPage(
        table_id=table.id, columns=columns,
        row_refs=page[reading.ROW_REF].to_list(),
        rows=[list(row) for row in page.select(columns).iter_rows()],
        offset=offset, limit=limit, total=table.row_count,
    )


@router.get("/tables/{table_id}/profile")
def table_profile(table_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
    table, _ = _ready_table_or_error(session, table_id)
    return {"table_id": str(table.id), **(table.profile or {})}


# ---------------------------------------------------------------- đọc lại, xóa

@router.put("/tables/{table_id}/header-row", status_code=202)
def choose_header_row(
    table_id: uuid.UUID, choice: HeaderChoice, session: SessionDep, background: BackgroundTasks
) -> TableSummary:
    table = session.get(DatasetTable, table_id)
    if table is None:
        raise fail(404, "TABLE_NOT_FOUND", "Không tìm thấy bảng dữ liệu.")
    if table.status == "READING":
        raise fail(409, "TABLE_BUSY", "Bảng đang được đọc, hãy đợi một chút.")
    table.status = "READING"
    session.commit()
    background.add_task(ingestion.reread_table, table.id, choice.header_row)
    return summarize(table.dataset).tables[table.position]


@router.post("/datasets/{dataset_id}/read", status_code=202)
def reread_dataset(
    dataset_id: uuid.UUID, session: SessionDep, background: BackgroundTasks
) -> DatasetSummary:
    """Đọc lại toàn bộ tệp gốc, dùng khi lần đọc trước thất bại hoặc bị gián đoạn."""
    dataset = _dataset_or_404(session, dataset_id)
    if dataset.status == "READING":
        raise fail(409, "DATASET_BUSY", "Bộ dữ liệu đang được đọc.")
    for table in list(dataset.tables):
        storage.delete_file(table.parquet_path)
        dataset.tables.remove(table)
    dataset.status = "READING"
    dataset.error_message = None
    session.commit()
    background.add_task(ingestion.read_dataset, dataset.id)
    return summarize(dataset)


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: uuid.UUID, session: SessionDep) -> Response:
    """Xóa hẳn bộ dữ liệu: tệp gốc, các bảng đã đọc và bản ghi trong DB."""
    dataset = _dataset_or_404(session, dataset_id)
    paths = [dataset.storage_path, *(table.parquet_path for table in dataset.tables)]
    session.delete(dataset)
    session.commit()
    for path in paths:
        storage.delete_file(path)
    return Response(status_code=204)
