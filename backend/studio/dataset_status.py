"""Read processing metadata without requiring reconciliation facts or calling a model."""

import re
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.access import Actor
from studio.assistant import plain_question
from studio.assistant_tools import scoped_context
from studio.contracts import Contract
from studio.contracts.assistant import AssistantContext
from studio.database import CanonicalRow, DatasetRow, MappingRow, TableRow, VersionRow
from studio.errors import DomainError
from studio.resource_lifecycle import active_source


class ProcessingStatus(Contract):
    dataset_id: str
    name: str
    table_id: str | None = None
    sheet: str | None = None
    version_id: str | None = None
    mapping_id: str | None = None
    canonical_id: str | None = None
    state: Literal[
        "UPLOADED",
        "PARSING",
        "PARSE_FAILED",
        "PARSED",
        "MAPPING_REVIEW",
        "MAPPED",
        "READY",
        "PARTIAL",
        "FAILED",
        "STALE",
    ]


def asks_processing_status(goal: str) -> bool:
    """Conservative read shortcut: status questions, never instructions to perform work."""
    text = plain_question(goal)
    subject = re.search(r"\b(?:du lieu|nguon|file|tep|cot)\b", text)
    status = re.search(
        (
            "\\b(?:chuan hoa|xu ly xong|san sang|dung duoc|trang thai xu ly|xac "
            "nhan cot|co the doi soat)\\b"
        ),
        text,
    )
    question = re.search(
        r"\b(?:kiem tra trang thai|co can xac nhan cot)\b"
        r"|\b(?:file|nguon|tep) nao\b[^.!?;]*\b(?:chua|da)\b"
        r"|\bchua\s*[?.!]*$",
        text,
    )
    writes = re.search(
        r"\b(?:de xuat|chuan bi|thiet lap|thuc hien|tao|cap nhat|chinh sua|dieu chinh|"
        r"tiep tuc|lam sach|chuyen doi|hay chuan hoa|chuan hoa .*giup|"
        r"tien hanh|chay doi soat|xuat bao cao|"
        r"duyet|bo qua|tu dong|sau do|roi .*doi soat|va .*doi soat|"
        r"bao nhieu|tong tien|tong so|bieu do|loc|sap xep|giai thich|liet ke|tim|dem)\b",
        text,
    )
    return bool(subject and status and question and not writes)


def read_processing_status(
    db: Session, actor: Actor, context: AssistantContext, dataset_ids: list[str], goal: str = ""
) -> list[ProcessingStatus]:
    """Read current versions/mappings only; stale/partial can never become READY.

    Every source must belong to the selected workspace/project. A result is metadata,
    not readiness for a particular financial contract. No writes, artifact scans or AI.
    """
    scoped_context(db, actor, context)
    selected = dataset_ids or ([context.dataset_id] if context.dataset_id else [])
    query = select(DatasetRow).where(
        DatasetRow.workspace_id == actor.workspace_id,
        DatasetRow.project_id == context.project_id,
        active_source(),
    )
    if selected:
        query = query.where(DatasetRow.id.in_(selected))
    datasets = list(db.scalars(query.order_by(DatasetRow.created_at, DatasetRow.id).limit(6)))
    if selected and {d.id for d in datasets} != set(selected):
        raise DomainError("RESOURCE_NOT_FOUND", "Không tìm thấy nguồn trong dự án này.", 404)
    if len(datasets) > 5:
        raise DomainError(
            "INPUT_AMBIGUOUS", "Dự án có nhiều nguồn. Hãy chọn tối đa năm tệp trong ngữ cảnh."
        )
    requested = re.findall(r"\b(?:nguon|file|tep) ([a-z])\b", plain_question(goal))
    if requested and not selected:
        matched = []
        for alias in sorted(set(requested)):
            matches = [
                d
                for d in datasets
                if re.search(rf"\b(?:nguon|file|tep) {alias}\b", plain_question(d.name))
            ]
            if len(matches) != 1:
                raise DomainError(
                    "INPUT_AMBIGUOUS",
                    "Chưa xác định được nguồn theo tên. Hãy chọn tệp cụ thể trong ngữ cảnh.",
                )
            matched.extend(matches)
        datasets = list({d.id: d for d in matched}.values())
    if (
        datasets
        and re.search(r"\b(?:hai|2)\s+(?:bo du lieu|nguon|file|tep)\b", plain_question(goal))
        and len(datasets) != 2
    ):
        raise DomainError(
            "INPUT_AMBIGUOUS",
            f"Ngữ cảnh hiện tại có {len(datasets)} nguồn: "
            + "; ".join(d.name for d in datasets)
            + ". Hãy chọn đúng hai nguồn. Nếu đang xem một tệp, "
            "mở Đổi ngữ cảnh phân tích và chọn Dùng dữ liệu của dự án trước khi hỏi lại.",
        )
    result = []
    from studio.normalization import NORMALIZATION_REVISION

    for dataset in datasets:
        version = db.scalar(
            select(VersionRow)
            .where(VersionRow.dataset_id == dataset.id)
            .order_by(VersionRow.revision.desc())
            .limit(1)
        )
        tables = list(
            db.scalars(
                select(TableRow)
                .where(
                    TableRow.workspace_id == actor.workspace_id,
                    TableRow.dataset_version_id == (version.id if version else ""),
                )
                .order_by(TableRow.id)
                .limit(6)
            )
        )
        if len(tables) > 5:
            raise DomainError(
                "INPUT_AMBIGUOUS", "Tệp có nhiều bảng. Hãy mở Tệp đã tải để kiểm tra từng bảng."
            )
        base = dict(
            dataset_id=dataset.id, name=dataset.name, version_id=version.id if version else None
        )
        if not tables:
            result.append(
                ProcessingStatus(
                    **base,
                    state="PARSE_FAILED"
                    if dataset.status == "FAILED"
                    else "PARSING"
                    if dataset.status == "PARSING"
                    else "UPLOADED",
                )
            )
        for table in tables:
            mapping = (
                db.get(MappingRow, table.active_mapping_id) if table.active_mapping_id else None
            )
            if mapping and (
                mapping.workspace_id != actor.workspace_id or mapping.source_table_id != table.id
            ):
                raise DomainError(
                    "RESOURCE_NOT_FOUND", "Ánh xạ không thuộc nguồn đang kiểm tra.", 404
                )
            canonical = (
                db.scalar(
                    select(CanonicalRow)
                    .where(
                        CanonicalRow.workspace_id == actor.workspace_id,
                        CanonicalRow.source_table_id == table.id,
                        CanonicalRow.mapping_id == table.active_mapping_id,
                        CanonicalRow.normalization_revision == NORMALIZATION_REVISION,
                    )
                    .order_by(CanonicalRow.id)
                    .limit(1)
                )
                if mapping
                else None
            )
            history = db.scalar(
                select(CanonicalRow.id)
                .where(
                    CanonicalRow.workspace_id == actor.workspace_id,
                    CanonicalRow.source_table_id == table.id,
                )
                .limit(1)
            )
            proposed = db.scalar(
                select(MappingRow.id)
                .where(
                    MappingRow.workspace_id == actor.workspace_id,
                    MappingRow.source_table_id == table.id,
                    MappingRow.status.in_(["PROPOSED", "NEEDS_REVIEW"]),
                )
                .limit(1)
            )
            state = (
                "STALE"
                if canonical and canonical.stale
                else canonical.contract["quality_status"]
                if canonical and mapping and mapping.status == "APPROVED"
                else "STALE"
                if history
                else "MAPPED"
                if mapping and mapping.status == "APPROVED"
                else "MAPPING_REVIEW"
                if proposed
                else "PARSED"
            )
            result.append(
                ProcessingStatus(
                    **base,
                    table_id=table.id,
                    sheet=table.sheet,
                    mapping_id=mapping.id if mapping else None,
                    canonical_id=canonical.id if canonical else None,
                    state=state,
                )
            )
    return result


def status_description(item: ProcessingStatus) -> str:
    descriptions = {
        "UPLOADED": (
            "Đã tải lên, chưa đọc xong. Chờ đọc tệp hoặc kiểm tra tiến độ trong Tệp đã tải."
        ),
        "PARSING": "Đang đọc tệp; chưa chuẩn hóa.",
        "PARSE_FAILED": (
            "Đọc tệp thất bại; chưa chuẩn hóa. Kiểm tra định dạng và thông báo của tệp."
        ),
        "PARSED": (
            "Đã đọc dữ liệu, chưa chuẩn hóa. Cần đề xuất ghép cột và xác nhận trước khi chuẩn hóa."
        ),
        "MAPPING_REVIEW": "Đang chờ kiểm tra, xác nhận cách ghép cột; chưa chuẩn hóa.",
        "MAPPED": (
            "Cách ghép cột đã được duyệt, nhưng chưa có bản chuẩn hóa hiện hành"
            ". Hãy tiếp tục chuẩn hóa."
        ),
        "READY": (
            "Đã chuẩn hóa; bản chuẩn hóa hiện hành hợp lệ. Có thể xem dữ liệu h"
            "oặc thiết lập đối soát."
        ),
        "PARTIAL": (
            "Đã chuẩn hóa một phần; còn dòng không hợp lệ. Cần kiểm tra lỗi trước khi sử dụng."
        ),
        "FAILED": "Chuẩn hóa thất bại. Kiểm tra lỗi dữ liệu và cách ghép cột trước khi tiếp tục.",
        "STALE": (
            "Đã từng chuẩn hóa nhưng bản cũ không còn hiệu lực. Kiểm tra lại án"
            "h xạ và chuẩn hóa lại."
        ),
    }
    return (
        f"{item.name}"
        + (f" · {item.sheet}" if item.sheet else "")
        + ": "
        + descriptions[item.state]
    )
