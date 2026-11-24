"""Tác vụ nền: đọc tệp gốc thành các bảng, lưu Parquet và hồ sơ cột.

Chạy sau khi API đã trả lời việc tải tệp, để người dùng không phải chờ.
Mỗi bước ghi trạng thái vào DB (READING → READY/FAILED) để giao diện theo dõi.
"""

import logging
import uuid
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session

from studio import database, mapping_service, reading, storage
from studio.models import ChatMessage, Dataset, DatasetTable, ReconChain, ReconRun
from studio.profiling import profile_table

logger = logging.getLogger(__name__)

INTERRUPTED_MESSAGE = "Việc đọc tệp bị gián đoạn do hệ thống khởi động lại. Hãy đọc lại."
RECON_INTERRUPTED_MESSAGE = "Đối soát bị gián đoạn do hệ thống khởi động lại. Hãy chạy lại."


def _raw_sheets(dataset: Dataset) -> list[reading.RawSheet]:
    content = Path(dataset.storage_path).read_bytes()
    if dataset.file_format == "CSV":
        return [reading.read_csv(content)]
    return reading.read_xlsx(content)


def _save_table(table: DatasetTable, raw: reading.RawSheet, header_index: int | None) -> None:
    """Tách tiêu đề, ghi Parquet và hồ sơ cột cho một bảng."""
    built = reading.build_table(raw, header_index)
    table.header_row = built.header_row
    table.column_names = built.column_names
    table.row_count = built.frame.height
    table.error_message = None
    # Một sheet chỉ được coi là bảng dữ liệu khi có ít nhất 2 cột và 1 dòng dữ liệu;
    # sheet chỉ có vài dòng ghi chú (một cột) không phải bảng để đối soát.
    if len(built.column_names) < 2 or built.frame.height == 0:
        table.status = "NO_DATA"
        table.row_count = 0  # không phải bảng dữ liệu thì không tính dòng
        table.profile = None
        return
    path = storage.table_path(table.id)
    built.frame.write_parquet(path)
    table.parquet_path = str(path)
    table.profile = profile_table(built.frame).model_dump()
    table.status = "READY"


def read_dataset(dataset_id: uuid.UUID) -> None:
    """Đọc mọi bảng của một bộ dữ liệu vừa tải lên."""
    with database.SessionFactory() as session:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            return
        created: list[uuid.UUID] = []  # bảng đã ghi Parquet, để dọn nếu đọc thất bại
        try:
            for position, raw in enumerate(_raw_sheets(dataset)):
                table = DatasetTable(id=uuid.uuid4(), dataset=dataset, sheet_name=raw.name,
                                     position=position)
                created.append(table.id)
                _save_table(table, raw, reading.detect_header_row(raw.frame))
                session.add(table)
            dataset.status = "READY"
            dataset.error_message = None
            session.commit()
        except reading.ReadError as error:
            _fail(session, dataset_id, created, str(error))
            return
        except Exception:
            logger.exception("Lỗi không lường trước khi đọc bộ dữ liệu %s", dataset_id)
            _fail(session, dataset_id, created, "Có lỗi khi đọc tệp. Hãy thử tải lại.")
            return
        ready_tables = [table.id for table in dataset.tables if table.status == "READY"]
    # Đọc xong thì tự gợi ý ánh xạ cột cho từng bảng (quyết định 2026-11-20).
    for ready_table_id in ready_tables:
        mapping_service.suggest_for_table(ready_table_id)


def reread_table(table_id: uuid.UUID, header_row: int | None) -> None:
    """Đọc lại một bảng với dòng tiêu đề do người dùng chọn (None: bảng không có tiêu đề)."""
    with database.SessionFactory() as session:
        table = session.get(DatasetTable, table_id)
        if table is None:
            return
        try:
            raws = _raw_sheets(table.dataset)
            raw = next(item for item in raws if item.name == table.sheet_name)
            index = None if header_row is None else reading.header_index_from_row(raw, header_row)
            _save_table(table, raw, index)
            table.header_row_chosen_by_user = True
            table.mapping_status = "NONE"
        except reading.ReadError as error:
            table.status = "FAILED"
            table.error_message = str(error)
        except Exception:
            logger.exception("Lỗi không lường trước khi đọc lại bảng %s", table_id)
            table.status = "FAILED"
            table.error_message = "Có lỗi khi đọc lại bảng. Hãy thử lại."
        session.commit()
        ready = table.status == "READY"
    if ready:
        mapping_service.suggest_for_table(table_id)


def _fail(
    session: Session, dataset_id: uuid.UUID, created: list[uuid.UUID], message: str
) -> None:
    """Đánh dấu bộ dữ liệu đọc lỗi và dọn các tệp Parquet đã lỡ ghi (bảng không được lưu)."""
    session.rollback()
    for table_id in created:
        storage.delete_file(storage.table_path(table_id))
    # Người dùng có thể đã xóa bộ dữ liệu trong lúc đọc: không tạo lại nó.
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        return
    dataset.status = "FAILED"
    dataset.error_message = message
    session.commit()


def recover_interrupted() -> None:
    """Khi backend khởi động lại giữa chừng, các việc nền dở dang (đọc tệp, ánh xạ, làm sạch,
    đối soát) không thể chạy tiếp: đánh dấu rõ ràng để người dùng làm lại."""
    with database.SessionFactory() as session:
        session.execute(update(Dataset).where(Dataset.status == "READING")
                        .values(status="FAILED", error_message=INTERRUPTED_MESSAGE))
        session.execute(update(DatasetTable).where(DatasetTable.status == "READING")
                        .values(status="FAILED", error_message=INTERRUPTED_MESSAGE))
        session.execute(update(DatasetTable).where(DatasetTable.mapping_status == "MAPPING")
                        .values(mapping_status="NONE"))
        session.execute(update(DatasetTable).where(DatasetTable.clean_status == "BUILDING")
                        .values(clean_status="FAILED"))
        # Bộ sạch đã dựng xong, chỉ phần AI gợi ý sửa ô bị dừng: bộ sạch vẫn dùng được.
        session.execute(update(DatasetTable).where(DatasetTable.clean_status == "SUGGESTING")
                        .values(clean_status="READY"))
        # Đối soát dở dang không chạy tiếp được: báo lỗi để người dùng chạy lại, không để
        # giao diện chờ mãi.
        for model in (ReconRun, ReconChain):
            session.execute(update(model).where(model.status == "RUNNING")
                            .values(status="FAILED", error_message=RECON_INTERRUPTED_MESSAGE))
        # Câu trả lời của Assistant đang soạn dở không chạy tiếp được.
        session.execute(update(ChatMessage).where(ChatMessage.status == "RUNNING")
                        .values(status="FAILED", text="Câu trả lời bị gián đoạn do hệ thống "
                                "khởi động lại. Hãy hỏi lại."))
        session.commit()
