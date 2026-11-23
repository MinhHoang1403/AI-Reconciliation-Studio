"""API đối soát: gợi ý cặp bảng và cấu hình, chạy, xem kết quả, xử lý ngoại lệ, kiểm chứng."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

import polars as pl
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from studio import audit, recon_ai, recon_service
from studio.cleaning import latest_version
from studio.database import get_session
from studio.datasets_api import fail
from studio.models import AuditLog, CleanVersion, DatasetTable, MatchResult, ReconRun
from studio.reading import ROW_REF
from studio.reconciliation import KINDS, ReconConfig
from studio.sales_fields import FIELDS_BY_KEY, TABLE_KIND_LABELS

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]

KIND_LABELS = {
    "MATCHED": "Khớp",
    "AMOUNT_MISMATCH": "Lệch tiền",
    "DUPLICATE": "Trùng",
    "ONLY_IN_A": "Chỉ có ở A",
    "ONLY_IN_B": "Chỉ có ở B",
    "NEEDS_CLEANING": "Dữ liệu chưa sạch",
    "OUT_OF_SCOPE": "Ngoài phạm vi",
}
# Nhóm hiển thị: việc cần làm trước, phần đã xong thu gọn (nguyên tắc giao diện Giai đoạn 4–7).
type ResultGroup = Literal["todo", "explained", "resolved", "matched", "out_of_scope"]
# Cột hiển thị cho mỗi dòng của kết quả (ngoài mã, ngày, số tiền theo cấu hình).
DETAIL_FIELDS = ("customer_name", "payment_method", "status", "description", "payment_id")


class PairChoice(BaseModel):
    left_table_id: uuid.UUID
    right_table_id: uuid.UUID


class RunRequest(PairChoice):
    # Người dùng chỉnh được sai số, khung ngày và giá trị để ngoài phạm vi; còn lại tự chọn.
    tolerance: str | None = Field(default=None, max_length=20)
    date_window_days: int | None = Field(default=None, ge=0, le=60)
    excluded: dict[str, dict[str, list[str]]] | None = None


class RunAction(BaseModel):
    action: Literal["RESOLVE", "REOPEN"]
    result_ids: list[uuid.UUID] | None = Field(default=None, max_length=5000)
    kind: str | None = None  # thay cho result_ids: mọi ngoại lệ đang mở của một loại


class NoteChange(BaseModel):
    note: str = Field(max_length=1000)


# ---------------------------------------------------------------- tiện ích


def _table(session: Session, table_id: uuid.UUID) -> DatasetTable:
    table = session.get(DatasetTable, table_id)
    if table is None:
        raise fail(404, "TABLE_NOT_FOUND", "Không tìm thấy bảng dữ liệu.")
    if latest_version(table) is None:
        raise fail(409, "CLEAN_NOT_READY", "Bảng chưa có bộ dữ liệu sạch.")
    return table


def _run(session: Session, run_id: uuid.UUID) -> ReconRun:
    run = session.get(ReconRun, run_id)
    if run is None:
        raise fail(404, "RUN_NOT_FOUND", "Không tìm thấy lần đối soát.")
    return run


def _table_view(table: DatasetTable) -> dict[str, Any]:
    version = latest_version(table)
    return {
        "id": str(table.id),
        "label": audit.table_label(table),
        "table_kind": table.table_kind,
        "table_kind_label": TABLE_KIND_LABELS.get(table.table_kind or "", "Chưa rõ loại"),
        "row_count": version.row_count if version else 0,
        "clean_open": sum(issue["status"] == "OPEN" for issue in version.issues) if version else 0,
    }


def _field_label(key: str | None) -> str | None:
    return FIELDS_BY_KEY[key].label if key and key in FIELDS_BY_KEY else None


def config_view(config: ReconConfig, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cấu hình kèm nhãn tiếng Việt và câu mô tả do engine sinh (không cần AI)."""
    lines = []
    if config.key_left:
        line = f"Ghép theo {_field_label(config.key_left)}"
        if config.key_right != config.key_left:
            line += f" ↔ {_field_label(config.key_right)}"
        if evidence:
            stats = next(
                (
                    item
                    for item in evidence["keys"]
                    if item["left"] == config.key_left and item["right"] == config.key_right
                ),
                None,
            )
            if stats:
                line += f" ({stats['match_rate']:.0%} mã bên A có ở bên B)"
        lines.append(line + ".")
    else:
        lines.append("Hai bên không có cột mã chung; chỉ ghép theo số tiền và ngày.")
    amount = f"So {_field_label(config.amount_left)}"
    if config.amount_right != config.amount_left:
        amount += f" ↔ {_field_label(config.amount_right)}"
    tolerance = "khớp tuyệt đối" if config.tolerance == 0 else f"sai số {config.tolerance}đ"
    lines.append(f"{amount}, {tolerance}.")
    if config.date_left and config.date_right:
        lines.append(
            f"Dòng không có mã chung được ghép theo số tiền và {_field_label(config.date_left)}"
            f" ↔ {_field_label(config.date_right)}, "
            f"cách nhau tối đa {config.date_window_days} ngày."
        )
    for side, fields in config.excluded.items():
        for key, values in fields.items():
            lines.append(
                f"Ngoài phạm vi bên {'A' if side == 'LEFT' else 'B'}: "
                f"{_field_label(key)} “{'”, “'.join(values)}” (không đi qua bên kia)."
            )
    return {
        **config.to_json(),
        "labels": {
            name: _field_label(getattr(config, name))
            for name in ("key_left", "key_right", "amount_left", "amount_right", "date_left",
                         "date_right")
        },
        "description": lines,
        "scope_options": [
            item for item in (evidence or {}).get("scope", [])
        ],
    }


def run_view(session: Session, run: ReconRun) -> dict[str, Any]:
    left = session.get(DatasetTable, run.left_table_id)
    right = session.get(DatasetTable, run.right_table_id)
    statuses = dict(
        session.execute(
            select(MatchResult.exception_status, func.count())
            .where(MatchResult.run_id == run.id)
            .group_by(MatchResult.exception_status)
        ).all()
    )
    open_by_kind = dict(
        session.execute(
            select(MatchResult.kind, func.count())
            .where(MatchResult.run_id == run.id, MatchResult.exception_status == "OPEN")
            .group_by(MatchResult.kind)
        ).all()
    )
    return {
        "id": str(run.id),
        "status": run.status,
        "error_message": run.error_message,
        "left": _table_view(left) if left else None,
        "right": _table_view(right) if right else None,
        "config": config_view(ReconConfig.from_json(run.config)),
        "period_start": run.period_start.isoformat() if run.period_start else None,
        "period_end": run.period_end.isoformat() if run.period_end else None,
        "summary": run.summary,
        "verification": run.verification,
        "exceptions": {
            "OPEN": statuses.get("OPEN", 0),
            "EXPLAINED": statuses.get("EXPLAINED", 0),
            "RESOLVED": statuses.get("RESOLVED", 0),
        },
        "open_by_kind": {kind: open_by_kind.get(kind, 0) for kind in KINDS},
        # Số kết quả của từng nhóm hiển thị (cùng điều kiện lọc với API danh sách kết quả).
        "group_counts": {
            group: session.scalar(
                select(func.count())
                .select_from(MatchResult)
                .where((MatchResult.run_id == run.id) & _group_filter(group))
            )
            or 0
            for group in ("todo", "explained", "resolved", "matched", "out_of_scope")
        },
        "kind_labels": KIND_LABELS,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _details(
    version: CleanVersion | None, refs: set[int], key: str | None, day: str | None, amount: str
) -> dict[int, dict[str, Any]]:
    """Giá trị đã chuẩn hóa của các dòng cần hiển thị (đọc đúng phiên bản sạch đã dùng)."""
    if version is None or not refs:
        return {}
    frame = pl.scan_parquet(version.parquet_path).filter(pl.col(ROW_REF).is_in(sorted(refs)))
    names = frame.collect_schema().names()
    wanted = {"key": key, "date": day, "amount": amount} | {name: name for name in DETAIL_FIELDS}
    columns = {label: name for label, name in wanted.items() if name and name in names}
    rows = frame.select(ROW_REF, *set(columns.values())).collect()
    details = {}
    for row in rows.iter_rows(named=True):
        item: dict[str, Any] = {"row_ref": row[ROW_REF]}
        for label, name in columns.items():
            value = row[name]
            item[label] = (
                None
                if value is None
                else value.isoformat()
                if hasattr(value, "isoformat")
                else str(value)
            )
        details[row[ROW_REF]] = item
    return details


def _group_filter(group: ResultGroup) -> Any:
    return {
        "todo": MatchResult.exception_status == "OPEN",
        "explained": MatchResult.exception_status == "EXPLAINED",
        "resolved": MatchResult.exception_status == "RESOLVED",
        "matched": (MatchResult.kind == "MATCHED") & MatchResult.exception_status.is_(None),
        "out_of_scope": MatchResult.kind == "OUT_OF_SCOPE",
    }[group]


def _result_label(item: MatchResult) -> str:
    refs = [f"A{ref}" for ref in item.left_refs] + [f"B{ref}" for ref in item.right_refs]
    return f"{KIND_LABELS.get(item.kind, item.kind)} ({', '.join(refs)})"


# ---------------------------------------------------------------- chọn bảng, cấu hình


@router.get("/recon/tables")
def recon_tables(session: SessionDep) -> dict[str, Any]:
    """Các bảng đã có bộ sạch và cặp bảng nên đối soát."""
    tables = recon_service.ready_tables(session)
    pair = recon_service.suggest_pair(tables)
    return {
        "tables": [_table_view(table) for table in tables],
        "suggested": {"left_table_id": str(pair[0]), "right_table_id": str(pair[1])}
        if pair
        else None,
    }


@router.post("/recon/preview")
def preview(choice: PairChoice, session: SessionDep) -> dict[str, Any]:
    """Cấu hình đối soát gợi ý cho một cặp bảng (chưa chạy)."""
    if choice.left_table_id == choice.right_table_id:
        raise fail(422, "SAME_TABLE", "Hãy chọn hai bảng khác nhau.")
    left, right = _table(session, choice.left_table_id), _table(session, choice.right_table_id)
    try:
        config, evidence = recon_service.preview(left, right)
    except ValueError as error:
        raise fail(422, "CANNOT_RECONCILE", str(error)) from error
    return {
        "left": _table_view(left),
        "right": _table_view(right),
        "config": config_view(config, evidence),
    }


@router.post("/recon/preview/explain")
def explain_preview(choice: PairChoice, session: SessionDep) -> dict[str, Any]:
    """Gemini diễn giải cấu hình bằng lời (chỉ khi người dùng bấm "Giải thích")."""
    view = preview(choice, session)
    return recon_ai.explain_config(view)


# ---------------------------------------------------------------- chạy và xem


@router.post("/recon/runs", status_code=202)
def start_run(
    request: RunRequest, session: SessionDep, background: BackgroundTasks
) -> dict[str, Any]:
    if request.left_table_id == request.right_table_id:
        raise fail(422, "SAME_TABLE", "Hãy chọn hai bảng khác nhau.")
    left, right = _table(session, request.left_table_id), _table(session, request.right_table_id)
    try:
        config, _ = recon_service.preview(left, right)
    except ValueError as error:
        raise fail(422, "CANNOT_RECONCILE", str(error)) from error
    if request.tolerance is not None:
        try:
            config.tolerance = Decimal(request.tolerance.replace(".", "").replace(",", "."))
        except InvalidOperation as error:
            raise fail(422, "INVALID_TOLERANCE", "Sai số phải là số tiền.") from error
        if config.tolerance < 0:
            raise fail(422, "INVALID_TOLERANCE", "Sai số không được âm.")
    if request.date_window_days is not None:
        config.date_window_days = request.date_window_days
    if request.excluded is not None:
        config.excluded = {
            side: fields for side, fields in request.excluded.items() if side in ("LEFT", "RIGHT")
        }
    run = ReconRun(
        id=uuid.uuid4(),
        left_table_id=left.id,
        right_table_id=right.id,
        left_version_id=latest_version(left).id,  # type: ignore[union-attr]
        right_version_id=latest_version(right).id,  # type: ignore[union-attr]
        status="RUNNING",
        config=config.to_json(),
    )
    session.add(run)
    audit.record(
        session,
        "RECON_RUN",
        "RECON_RUN",
        run.id,
        f"{audit.table_label(left)} ↔ {audit.table_label(right)}",
        "Chạy đối soát. " + " ".join(config_view(config)["description"]),
        after={"config": config.to_json()},
    )
    session.commit()
    background.add_task(recon_service.execute_run, run.id)
    return run_view(session, run)


@router.get("/recon/runs")
def list_runs(
    session: SessionDep, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> list[dict[str, Any]]:
    runs = session.scalars(select(ReconRun).order_by(ReconRun.created_at.desc()).limit(limit))
    return [run_view(session, run) for run in runs]


@router.get("/recon/runs/{run_id}")
def get_run(run_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
    return run_view(session, _run(session, run_id))


@router.get("/recon/runs/{run_id}/results")
def run_results(
    run_id: uuid.UUID,
    session: SessionDep,
    group: ResultGroup = "todo",
    kind: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    """Kết quả theo nhóm (cần xử lý, đã ghi chú, đã xử lý, khớp, ngoài phạm vi) kèm dòng."""
    run = _run(session, run_id)
    condition = (MatchResult.run_id == run.id) & _group_filter(group)
    if kind:
        condition = condition & (MatchResult.kind == kind)
    total = session.scalar(select(func.count()).select_from(MatchResult).where(condition)) or 0
    items = list(
        session.scalars(
            select(MatchResult)
            .where(condition)
            .order_by(MatchResult.position)
            .offset(offset)
            .limit(limit)
        )
    )
    config = ReconConfig.from_json(run.config)
    left = _details(
        session.get(CleanVersion, run.left_version_id),
        {ref for item in items for ref in item.left_refs},
        config.key_left,
        config.date_left,
        config.amount_left,
    )
    right = _details(
        session.get(CleanVersion, run.right_version_id),
        {ref for item in items for ref in item.right_refs},
        config.key_right,
        config.date_right,
        config.amount_right,
    )
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": str(item.id),
                "kind": item.kind,
                "kind_label": KIND_LABELS.get(item.kind, item.kind),
                "score": item.score,
                "reasons": item.reasons,
                "amount_left": None if item.amount_left is None else str(item.amount_left),
                "amount_right": None if item.amount_right is None else str(item.amount_right),
                "exception_status": item.exception_status,
                "note": item.note,
                "left": [left.get(ref, {"row_ref": ref}) for ref in item.left_refs],
                "right": [right.get(ref, {"row_ref": ref}) for ref in item.right_refs],
            }
            for item in items
        ],
    }


@router.post("/recon/runs/{run_id}/verify")
def reverify(run_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
    """Kiểm chứng lại từ kết quả đang lưu (bắt được kết quả bị sửa tay trong cơ sở dữ liệu)."""
    run = _run(session, run_id)
    if run.status != "READY":
        raise fail(409, "RUN_NOT_READY", "Lần đối soát chưa chạy xong.")
    run.verification = recon_service.verify_run(session, run)
    session.commit()
    return run_view(session, run)


# ---------------------------------------------------------------- xử lý ngoại lệ


@router.post("/recon/runs/{run_id}/actions")
def act_on_results(run_id: uuid.UUID, action: RunAction, session: SessionDep) -> dict[str, Any]:
    """Đánh dấu đã xử lý / mở lại một hoặc nhiều ngoại lệ (ví dụ "Đồng ý tất cả" của một loại)."""
    run = _run(session, run_id)
    condition = (MatchResult.run_id == run.id) & MatchResult.exception_status.is_not(None)
    if action.result_ids is not None:
        condition = condition & MatchResult.id.in_(action.result_ids)
    elif action.kind is not None:
        condition = condition & (MatchResult.kind == action.kind)
        condition = condition & (MatchResult.exception_status == "OPEN")
    else:
        raise fail(422, "NO_TARGET", "Hãy chọn kết quả cần xử lý.")
    items = list(session.scalars(select(MatchResult).where(condition)))
    now = datetime.now(UTC)
    changed = []
    for item in items:
        before = item.exception_status
        after = "RESOLVED" if action.action == "RESOLVE" else ("EXPLAINED" if item.note else "OPEN")
        if before != after:
            item.exception_status, item.updated_at = after, now
            changed.append({"id": str(item.id), "before": before, "after": after})
    if changed:
        verb = "Đánh dấu đã xử lý" if action.action == "RESOLVE" else "Mở lại"
        target = (
            _result_label(items[0])
            if len(changed) == 1
            else f"{len(changed)} kết quả"
            + (f" loại {KIND_LABELS.get(action.kind, action.kind)}" if action.kind else "")
        )
        audit.record(
            session,
            f"EXCEPTION_{action.action}",
            "RECON_RUN",
            run.id,
            _run_label(session, run),
            f"{verb} {target}.",
            {"results": [{"id": item["id"], "status": item["before"]} for item in changed]},
            {"results": [{"id": item["id"], "status": item["after"]} for item in changed]},
        )
    session.commit()
    return run_view(session, run)


@router.put("/recon/results/{result_id}/note")
def change_note(result_id: uuid.UUID, change: NoteChange, session: SessionDep) -> dict[str, Any]:
    """Ghi chú tùy chọn; ngoại lệ đang mở có ghi chú thì tự thành "đã giải thích"."""
    item = session.get(MatchResult, result_id)
    if item is None:
        raise fail(404, "RESULT_NOT_FOUND", "Không tìm thấy kết quả.")
    run = _run(session, item.run_id)
    note = change.note.strip() or None
    before = {"note": item.note, "status": item.exception_status}
    item.note = note
    if item.exception_status == "OPEN" and note:
        item.exception_status = "EXPLAINED"
    elif item.exception_status == "EXPLAINED" and not note:
        item.exception_status = "OPEN"
    item.updated_at = datetime.now(UTC)
    audit.record(
        session,
        "EXCEPTION_NOTE",
        "RECON_RUN",
        run.id,
        _run_label(session, run),
        f"Ghi chú cho {_result_label(item)}: “{note}”." if note else
        f"Xóa ghi chú của {_result_label(item)}.",
        before,
        {"note": item.note, "status": item.exception_status},
    )
    session.commit()
    return {"id": str(item.id), "note": item.note, "exception_status": item.exception_status}


@router.post("/recon/results/{result_id}/explain")
def explain_result(result_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
    """Gemini giải thích một ngoại lệ bằng lời từ lý do của engine (chỉ khi người dùng bấm)."""
    item = session.get(MatchResult, result_id)
    if item is None:
        raise fail(404, "RESULT_NOT_FOUND", "Không tìm thấy kết quả.")
    run = _run(session, item.run_id)
    page = run_results(run.id, session, group=_group_of(item), kind=None, offset=0, limit=200)
    view = next((entry for entry in page["items"] if entry["id"] == str(item.id)), None)
    if view is None:  # nằm ngoài trang đầu: dựng riêng
        view = {"kind": item.kind, "reasons": item.reasons, "left": [], "right": []}
    return recon_ai.explain_result(view, run_view(session, run)["config"])


def _group_of(item: MatchResult) -> ResultGroup:
    if item.exception_status == "OPEN":
        return "todo"
    if item.exception_status == "EXPLAINED":
        return "explained"
    if item.exception_status == "RESOLVED":
        return "resolved"
    return "out_of_scope" if item.kind == "OUT_OF_SCOPE" else "matched"


def _run_label(session: Session, run: ReconRun) -> str:
    left = session.get(DatasetTable, run.left_table_id)
    right = session.get(DatasetTable, run.right_table_id)
    names = [audit.table_label(table) if table else "?" for table in (left, right)]
    return " ↔ ".join(names)


# ---------------------------------------------------------------- nhật ký kiểm toán


@router.get("/audit")
def audit_log(
    session: SessionDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    total = session.scalar(select(func.count()).select_from(AuditLog)) or 0
    items = session.scalars(
        select(AuditLog)
        .order_by(AuditLog.created_at.desc(), AuditLog.id)
        .offset(offset)
        .limit(limit)
    )
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": str(item.id),
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "actor": item.actor,
                "action": item.action,
                "object_type": item.object_type,
                "object_id": item.object_id,
                "object_label": item.object_label,
                "summary": item.summary,
                "before": item.before,
                "after": item.after,
            }
            for item in items
        ],
    }
