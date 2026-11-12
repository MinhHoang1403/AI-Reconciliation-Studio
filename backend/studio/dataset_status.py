"""Read processing metadata without requiring reconciliation facts or calling a model."""

import re
import unicodedata
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio.access import Actor
from studio.assistant import plain_question
from studio.assistant_tools import scoped_context, select_project_datasets
from studio.contracts import Contract
from studio.contracts.assistant import AssistantContext
from studio.database import (
    AgentWorkflowRow,
    ArtifactRow,
    CanonicalRow,
    ConversationRow,
    JobRow,
    MappingRow,
    TableRow,
    VersionRow,
)
from studio.errors import DomainError
from studio.repository import mapping_archived


class ProcessingStatus(Contract):
    dataset_id: str
    name: str
    table_id: str | None = None
    sheet: str | None = None
    row_count: int | None = None
    version_id: str | None = None
    mapping_id: str | None = None
    canonical_id: str | None = None
    valid_rows: int | None = None
    invalid_rows: int | None = None
    excluded_rows: int = 0
    automatic: bool = False
    state: Literal[
        "UPLOADED",
        "PARSING",
        "PARSE_FAILED",
        "PARSED",
        "PREPARING",
        "EXPLORATION_ONLY",
        "MAPPING_REVIEW",
        "MAPPED",
        "READY",
        "PARTIAL",
        "FAILED",
        "STALE",
    ]


def asks_source_inventory(goal: str) -> bool:
    """Nhận câu hỏi danh mục, tách khỏi việc xem dòng và tính chỉ tiêu."""
    text = " ".join(plain_question(goal).split()).rstrip(" ?.!")
    source = r"(?:tep(?: du lieu)?|file|nguon(?: du lieu)?|bo du lieu)"
    project = r"(?: (?:trong|cua|o) du an(?: nay| hien tai)?)?"
    modifier = r"(?: (?:da|vua|moi) tai len)?"
    return bool(
        re.fullmatch(
            r"(?:(?:hay|vui long|cho toi) )?"
            r"(?:(?:liet ke|cho biet|xem) (?:danh sach )?(?:tat ca |toan bo )?(?:cac |nhung )?"
            rf"{source}{modifier}{project}"
            r"|(?:trong )?du an(?: nay| hien tai)? (?:(?:dang|hien) )?co "
            rf"(?:nhung {source} nao|(?:bao nhieu|may) {source})"
            rf"|(?:hien )?co (?:nhung {source} nao|bao nhieu {source}){modifier}{project}"
            rf"|(?:danh sach (?:cac )?{source}|(?:cac |nhung )?{source} nao){modifier}{project})",
            text,
        )
    )


def requests_project_sources(goal: str) -> bool:
    """Phạm vi toàn dự án chỉ ghi đè tệp đã ghim khi yêu cầu nêu rõ."""
    text = plain_question(goal)
    return bool(
        re.search(
            r"\b(?:trong|cua|o) du an\b|\bdu an (?:nay |hien tai )?(?:dang |hien )?co\b", text
        )
        or re.search(
            r"\b(?:toan bo|tat ca|ca ba|ba|3) (?:cac )?(?:bo du lieu|du lieu|nguon|file|tep)\b",
            text,
        )
    )


def requested_source_stem(goal: str) -> str | None:
    """Tên tệp không có phần mở rộng trong câu kiểm tra một nguồn cụ thể."""
    text = " ".join(plain_question(goal).split()).rstrip(" ?!")
    match = re.fullmatch(
        r"(?:hay )?kiem tra rieng (?:tep |file |nguon )?([^.!?;,]{1,200})\.?", text
    )
    return (match[1].strip(' "“”') or None) if match else None


def asks_processing_status(goal: str) -> bool:
    """Conservative read shortcut: status questions, never instructions to perform work."""
    if requested_source_stem(goal):
        return True
    text = plain_question(goal)
    subject = re.search(r"\b(?:du lieu|nguon|file|tep|cot)\b", text)
    status = re.search(
        (
            "\\b(?:chuan hoa|da doc|doc xong|xu ly xong|san sang|dung duoc|trang thai xu ly|xac "
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
    db: Session,
    actor: Actor,
    context: AssistantContext,
    dataset_ids: list[str],
    goal: str = "",
    *,
    dataset_names: tuple[str, ...] | None = None,
) -> list[ProcessingStatus]:
    """Read current versions/mappings only; stale/partial can never become READY.

    Every source must belong to the selected workspace/project. A result is metadata,
    not readiness for a particular financial contract. No writes, artifact scans or AI.
    """
    scoped_context(db, actor, context)
    stem = requested_source_stem(goal) if not dataset_names else None
    selected = dataset_ids or (
        [context.dataset_id] if context.dataset_id and not (dataset_names or stem) else []
    )
    datasets = select_project_datasets(
        db, actor, context.project_id, selected, dataset_names, dataset_stem=stem
    )
    actual = [unicodedata.normalize("NFC", d.name).casefold() for d in datasets]
    if (
        dataset_names
        and (len(actual) != len(set(actual)) or set(actual) != set(dataset_names))
        or stem
        and (len(datasets) != 1 or plain_question(datasets[0].name.rsplit(".", 1)[0]) != stem)
    ):
        raise DomainError(
            "INPUT_AMBIGUOUS", "Chưa xác định được đúng tệp theo tên trong dự án này."
        )
    requested = re.findall(r"\b(?:nguon|file|tep) ([a-z])\b", plain_question(goal))
    if requested and not selected and not (dataset_names or stem):
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
            + ". Hãy nêu tên hai nguồn hoặc hỏi về toàn bộ dự án.",
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
            artifact = db.get(ArtifactRow, table.artifact_id)
            automatic = bool(
                artifact and (artifact.metadata_json.get("prepared") or {}).get("automatic")
            )
            preparation = (
                db.scalar(
                    select(JobRow)
                    .where(
                        JobRow.project_id == dataset.project_id,
                        JobRow.workspace_id == actor.workspace_id,
                        JobRow.kind.in_(["automatic_preparation", "mapping_reuse", "normalize"]),
                        JobRow.payload["table_id"].astext == table.id,
                    )
                    .order_by(JobRow.created_at.desc(), JobRow.id.desc())
                    .limit(1)
                )
                if automatic
                else None
            )
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
                        CanonicalRow.quality_revision == table.quality_revision,
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
                    MappingRow.status.in_(["PROPOSED", "AMBIGUOUS", "NEEDS_REVIEW"]),
                    ~mapping_archived(),
                )
                .limit(1)
            )
            if not proposed and not mapping:
                proposed = db.scalar(
                    select(AgentWorkflowRow.id)
                    .join(ConversationRow, ConversationRow.id == AgentWorkflowRow.conversation_id)
                    .where(
                        AgentWorkflowRow.workspace_id == actor.workspace_id,
                        AgentWorkflowRow.project_id == context.project_id,
                        AgentWorkflowRow.actor_id == actor.id,
                        ConversationRow.deleted_at.is_(None),
                        AgentWorkflowRow.state.in_(["RUNNING", "WAITING_REVIEW"]),
                        AgentWorkflowRow.detail.contains(
                            {
                                "reviews": [
                                    {"kind": "MAPPING", "resource_id": table.id, "state": "OPEN"},
                                ]
                            }
                        ),
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
                else "PREPARING"
                if preparation and preparation.status in {"QUEUED", "RUNNING", "RETRYABLE_FAILURE"}
                else "FAILED"
                if preparation and preparation.status in {"FAILED", "BLOCKED"}
                else "EXPLORATION_ONLY"
                if automatic and not mapping
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
                    row_count=table.row_count,
                    mapping_id=mapping.id if mapping else None,
                    canonical_id=canonical.id if canonical else None,
                    valid_rows=canonical.contract["valid_count"] if canonical else None,
                    invalid_rows=canonical.contract["invalid_count"] if canonical else None,
                    excluded_rows=canonical.contract.get("excluded_source_rows", 0)
                    if canonical
                    else 0,
                    automatic=automatic,
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
        "PREPARING": "Đang chuẩn bị và kiểm tra dữ liệu.",
        "EXPLORATION_ONLY": "Đã chuẩn bị để xem. Còn thiếu căn cứ đối soát tài chính.",
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
    description = descriptions[item.state]
    if item.automatic and item.state == "READY":
        description = "Đã chuẩn bị và kiểm chứng dữ liệu."
    elif (
        item.automatic
        and item.state == "PARTIAL"
        and item.valid_rows is not None
        and item.invalid_rows is not None
    ):
        valid = f"{item.valid_rows:,}".replace(",", ".")
        invalid = f"{item.invalid_rows:,}".replace(",", ".")
        description = (
            f"Đã chuẩn bị, có ngoại lệ. {valid} dòng dùng được, {invalid} dòng cần kiểm tra."
        )
    return (
        f"{item.name}"
        + (f" · {item.sheet}" if item.sheet else "")
        + (
            " · " + f"{item.row_count:,}".replace(",", ".") + " dòng"
            if item.row_count is not None
            else ""
        )
        + ": "
        + description
    )
