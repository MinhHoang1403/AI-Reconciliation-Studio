"""API trang Báo cáo (Giai đoạn 7): số liệu một kỳ, so sánh các kỳ, xuất tệp, nhận xét AI.

Kỳ chưa qua kiểm chứng vẫn xem được (giao diện hiện cảnh báo) nhưng không xuất tệp và không
viết nhận xét AI: kết quả kiểm chứng thất bại không được dùng cho báo cáo (ARCHITECTURE 5.3).
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio import report_ai, report_export, reporting
from studio.database import get_session
from studio.datasets_api import fail
from studio.models import ReconChain

router = APIRouter(prefix="/api/reports")
SessionDep = Annotated[Session, Depends(get_session)]


def _chain(session: Session, chain_id: uuid.UUID) -> ReconChain:
    chain = session.get(ReconChain, chain_id)
    if chain is None:
        raise fail(404, "CHAIN_NOT_FOUND", "Không tìm thấy lần đối soát của kỳ này.")
    if chain.status != "READY":
        raise fail(409, "CHAIN_NOT_READY", "Kỳ này chưa đối soát xong.")
    return chain


def _verified_report(session: Session, chain_id: uuid.UUID) -> dict[str, Any]:
    report = reporting.build_report(session, _chain(session, chain_id))
    if not report["verified"]:
        raise fail(
            409,
            "NOT_VERIFIED",
            "Kỳ này chưa qua kiểm chứng nên chưa được xuất hay nhận xét; "
            "hãy kiểm chứng lại ở trang Đối soát.",
        )
    return report


def _comment_view(session: Session, chain: ReconChain, report: dict[str, Any]) -> Any:
    """Nhận xét mới nhất của kỳ (cùng bộ bảng), kể cả từ lần đối soát trước: số liệu đã đổi
    thì đánh dấu đã cũ thay vì giấu đi."""
    chains = session.scalars(
        select(ReconChain)
        .where(ReconChain.report_comment.is_not(None))
        .order_by(ReconChain.created_at.desc())
    )
    for candidate in chains:
        if set(candidate.table_ids) == set(chain.table_ids) and candidate.report_comment:
            comment = candidate.report_comment
            return {
                "text": comment["text"],
                "created_at": comment["created_at"],
                "stale": comment["fingerprint"] != reporting.fingerprint(report),
            }
    return None


@router.get("")
def list_reports(session: SessionDep) -> dict[str, Any]:
    """Các kỳ đã đối soát kèm số chính (khối so sánh các kỳ, Dashboard)."""
    return dict(reporting.to_json({"periods": reporting.comparison(session)}))


@router.get("/{chain_id}")
def get_report(chain_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
    chain = _chain(session, chain_id)
    report = reporting.build_report(session, chain)
    view = {key: value for key, value in report.items() if key != "results"}
    view["comment"] = _comment_view(session, chain, report)
    return dict(reporting.to_json(view))


def _filename(report: dict[str, Any], extension: str) -> str:
    return f"bao-cao-doi-soat_{report['period_start']}_{report['period_end']}.{extension}"


@router.get("/{chain_id}/export.xlsx")
def export_xlsx(chain_id: uuid.UUID, session: SessionDep) -> Response:
    report = _verified_report(session, chain_id)
    return Response(
        report_export.to_xlsx(report),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{_filename(report, "xlsx")}"'},
    )


@router.get("/{chain_id}/export.csv")
def export_csv(chain_id: uuid.UUID, session: SessionDep) -> Response:
    report = _verified_report(session, chain_id)
    return Response(
        report_export.to_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_filename(report, "csv")}"'},
    )


@router.post("/{chain_id}/comment")
def write_comment(chain_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
    """Gemini viết nhận xét từ số liệu đã tính; lưu lại cùng dấu vân tay số liệu."""
    report = _verified_report(session, chain_id)
    text = report_ai.write_comment(report)
    chain = _chain(session, chain_id)
    chain.report_comment = {
        "text": text,
        "fingerprint": reporting.fingerprint(report),
        "created_at": datetime.now(UTC).isoformat(),
    }
    session.commit()
    return {"text": text, "created_at": chain.report_comment["created_at"], "stale": False}
