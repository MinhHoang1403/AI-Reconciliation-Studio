"""API đối soát: gợi ý cặp bảng và cấu hình, chạy, xem kết quả, xử lý ngoại lệ, kiểm chứng."""

import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

import polars as pl
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from studio import audit, recon_ai, recon_service, workspaces
from studio.cleaning import latest_version
from studio.database import get_session
from studio.datasets_api import fail
from studio.models import (
    AuditLog,
    CleanVersion,
    DatasetTable,
    MatchResult,
    ReconChain,
    ReconChoice,
    ReconRun,
)
from studio.reading import ROW_REF
from studio.reconciliation import KINDS, ReconConfig
from studio.sales_fields import FIELDS_BY_KEY, TABLE_KIND_LABELS

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]

KIND_LABELS = {
    "MATCHED": "Khớp",
    "MANY_TO_ONE": "Ghép nhóm",
    "ONE_TO_MANY": "Ghép nhóm",
    "AMBIGUOUS": "Cần bạn chọn",
    "PENDING_SETTLEMENT": "Chờ tiền về",
    "AMOUNT_MISMATCH": "Lệch tiền",
    "DUPLICATE": "Trùng",
    "ONLY_IN_A": "Chỉ có ở A",
    "ONLY_IN_B": "Chỉ có ở B",
    "NEEDS_CLEANING": "Dữ liệu chưa sạch",
    "OUT_OF_SCOPE": "Ngoài phạm vi",
}
# Ý nghĩa từng loại kết quả (docs/ARCHITECTURE.md mục 5.2); dùng cho data catalog.
KIND_DESCRIPTIONS = {
    "MATCHED": "Khớp hoàn toàn: cùng mã hoặc cùng điểm cao, số tiền trong sai số.",
    "MANY_TO_ONE": "Ghép nhóm: nhiều dòng bên A cộng lại đúng bằng một dòng bên B.",
    "ONE_TO_MANY": "Ghép nhóm: một dòng bên A bằng đúng tổng nhiều dòng bên B.",
    "AMBIGUOUS": "Nhiều ứng viên ngang điểm; hệ thống không tự chọn, người dùng chọn.",
    "PENDING_SETTLEMENT": "Chưa khớp nhưng còn trong khung chờ tiền về (T+3 ngày làm việc); "
    "chênh lệch do thời điểm, kỳ sau tự khớp lại.",
    "AMOUNT_MISMATCH": "Ghép được hai bên nhưng số tiền lệch ngoài sai số.",
    "DUPLICATE": "Một bên có nhiều dòng giống hệt cùng trỏ một dòng bên kia.",
    "ONLY_IN_A": "Chỉ có ở bên A, không tìm được dòng tương ứng bên B (thiếu).",
    "ONLY_IN_B": "Chỉ có ở bên B, không tìm được dòng tương ứng bên A (thừa).",
    "NEEDS_CLEANING": "Dòng còn vấn đề mức \"Hỏi\" ở bước làm sạch; không ghép, cần sửa rồi "
    "chạy lại.",
    "OUT_OF_SCOPE": "Dòng không thuộc phạm vi bên kia (tiền mặt, đơn hủy, tiền ra, đã ghép ở cặp "
    "khác); người dùng đổi lại được.",
}

# Nhãn nhóm của chuỗi (gộp nhiều cặp): "chỉ có ở một bên" gọi theo ý nghĩa tiền.
CHAIN_KIND_LABELS = KIND_LABELS | {
    "ONLY_IN_A": "Thiếu tiền về",
    "ONLY_IN_B": "Tiền về chưa rõ nguồn",
}

# Engine viết nhãn và lý do chung cho mọi cặp ("Chỉ có ở A", "Không có dòng tương ứng ở bên B",
# "Tổng 2 dòng A = 1 dòng B"). Khi hiển thị, "A"/"B" được đổi thành tên bảng thật của cặp để
# người đọc biết ngay là tập dữ liệu nào (Owner 27/11/2026). Đổi lúc hiển thị nên áp dụng cả
# cho kết quả đã lưu từ trước.
_SIDE_WORD = re.compile(r"\b(bên|Bên|ở|Ở) ([AB])\b")
_SIDE_ROWS = re.compile(r"\b(dòng|Dòng) ([AB])\b")
# Mẫu câu lệch tiền của engine trước 27/11/2026: "Lệch tiền: A 2.482.000đ, B 2.432.000đ (B thiếu
# 50.000đ)". Chỉ đổi đúng mẫu này (không đổi chữ A/B bất kỳ trước số, vì tên hay nội dung
# chuyển khoản có thể chứa "VAN A 500000"); từ nay engine ghi "bên A", "bên B".
_OLD_MISMATCH = re.compile(r"Lệch tiền: A (\S+), B (\S+) \(B (thừa|thiếu)")


def name_sides(text: str, left: str, right: str) -> str:
    """Đổi "bên A", "ở B", "dòng A"… thành tên bảng bên trái / bên phải của cặp."""

    def name(side: str) -> str:
        return left if side == "A" else right

    text = _OLD_MISMATCH.sub(
        lambda m: f"Lệch tiền: bên A {m.group(1)}, bên B {m.group(2)} (bên B {m.group(3)}", text
    )
    text = _SIDE_WORD.sub(lambda m: f"{m.group(1)} {name(m.group(2))}", text)
    return _SIDE_ROWS.sub(lambda m: f"{m.group(1)} của {name(m.group(2))}", text)


def _named_verification(
    verification: dict[str, Any] | None, sides: tuple[str, str]
) -> dict[str, Any] | None:
    """Kết quả kiểm chứng đã lưu ghi "bên A/B" ("Tổng tiền bên A được bảo toàn"): đổi thành
    tên bảng khi hiển thị, không sửa bản đã lưu."""
    if not verification:
        return verification
    return verification | {
        "checks": [
            check
            | {
                "label": name_sides(check["label"], *sides),
                "detail": name_sides(check.get("detail") or "", *sides),
            }
            for check in verification.get("checks", [])
        ]
    }


def side_labels(session: Session, run: ReconRun) -> tuple[str, str]:
    """Tên hai bảng của một lần đối soát (bảng đã xóa thì ghi rõ)."""
    left, right = (
        session.get(DatasetTable, table_id) for table_id in (run.left_table_id, run.right_table_id)
    )
    return (
        audit.table_label(left) if left else "bảng đã xóa",
        audit.table_label(right) if right else "bảng đã xóa",
    )


# Nhóm hiển thị: việc cần làm trước, phần đã xong thu gọn (nguyên tắc giao diện Giai đoạn 4–7).
type ResultGroup = Literal[
    "todo", "explained", "resolved", "matched", "pending", "out_of_scope"
]
GROUPS: tuple[ResultGroup, ...] = (
    "todo", "explained", "resolved", "matched", "pending", "out_of_scope"
)
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


class ChainRequest(BaseModel):
    table_ids: list[uuid.UUID] = Field(min_length=2, max_length=20)
    label: str | None = Field(default=None, max_length=120)


class AmbiguousChoice(BaseModel):
    result_id: uuid.UUID
    left_refs: list[int] = Field(min_length=1, max_length=10)
    right_refs: list[int] = Field(min_length=1, max_length=10)


# ---------------------------------------------------------------- tiện ích


def parse_tolerance(text: str) -> Decimal:
    """Sai số tiền người dùng nhập: số đồng nguyên, không âm, có thể có dấu phân cách nghìn
    ("1.000", "1,000", "1 000"). Số lẻ, số âm, NaN hay vô cực đều bị từ chối (422)."""
    compact = text.strip().replace(" ", "")
    if not re.fullmatch(r"\d{1,3}([.,]\d{3})*|\d+", compact):
        raise fail(
            422, "INVALID_TOLERANCE", "Sai số phải là số đồng nguyên không âm, ví dụ 1.000."
        )
    return Decimal(re.sub(r"[.,]", "", compact))


def _table(session: Session, table_id: uuid.UUID) -> DatasetTable:
    table = workspaces.owned(session, session.get(DatasetTable, table_id))
    if table is None:
        raise fail(404, "TABLE_NOT_FOUND", "Không tìm thấy bảng dữ liệu.")
    if latest_version(table) is None:
        raise fail(409, "CLEAN_NOT_READY", "Bảng chưa có bộ dữ liệu sạch.")
    return table


def _run(session: Session, run_id: uuid.UUID) -> ReconRun:
    """Lần đối soát của phiên đang mở (kết quả mở theo mã cũng đi qua đây để kiểm phiên)."""
    run = workspaces.owned(session, session.get(ReconRun, run_id))
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


def config_view(
    config: ReconConfig,
    evidence: dict[str, Any] | None = None,
    sides: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Cấu hình kèm mô tả bằng lời; có `sides` (tên hai bảng) thì "bên A/B" trong mô tả được
    đổi thành tên bảng."""
    """Cấu hình kèm nhãn tiếng Việt và câu mô tả do engine sinh (không cần AI)."""
    lines = []
    if config.key_left and config.extract:
        what = "ngày" if config.extract["kind"] == "date" else "mã"
        line = (
            f"Tách {what} trong nội dung chuyển khoản theo mẫu "
            f"{pattern_text(config.extract)} rồi ghép với {_field_label(config.key_left)}"
        )
        if evidence:
            found = next(
                (item for item in evidence.get("extract", [])
                 if item["target"] == config.key_left),
                None,
            )
            if found:
                line += f" ({found['hits']} dòng tách được, {found['precision']:.0%} đúng)"
        lines.append(line + ".")
    elif config.key_left:
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
    if config.group_left:
        lines.append(
            f"Nhiều dòng bên A chung một {_field_label(config.key_left)} được ghép nhóm với một "
            "dòng bên B khi tổng tiền bằng đúng."
        )
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
    if config.outflow_right:
        lines.append("Dòng tiền ra (cột Nợ) của bên B để ngoài phạm vi đối soát bán hàng.")
    if config.settle_days:
        lines.append(
            f"Dòng chưa có tiền về mà còn trong hạn T+{config.settle_days} ngày làm việc là "
            "\"chờ tiền về\", kỳ sau tự ghép lại."
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
        "description": [name_sides(line, *sides) for line in lines] if sides else lines,
        "scope_options": [
            item for item in (evidence or {}).get("scope", [])
        ],
    }


def pattern_text(extract: dict[str, str]) -> str:
    """Mẫu tách mã dạng dễ đọc: (?<![A-Z0-9])HD\\d{6}(?![A-Z0-9]) → "HD + 6 chữ số"."""
    if extract["kind"] == "date":
        return "ngày/tháng/năm"
    body = re.sub(r"\(\?<?[!=][^)]*\)", "", extract["pattern"])
    parts = []
    # Thứ tự quan trọng: đoạn số, đoạn chữ trước; ký tự thoát (\-) và chữ cố định sau.
    for digits, letters, literal in re.findall(
        r"\\d\{(\d+)\}|\[A-Z\]\{(\d+)\}|([A-Z]+|\\.)", body
    ):
        if digits:
            parts.append(f"{digits} chữ số")
        elif letters:
            parts.append(f"{letters} chữ cái")
        elif literal:
            parts.append(literal.replace("\\", ""))
    return " + ".join(parts) or extract["pattern"]


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
        "chain_id": str(run.chain_id) if run.chain_id else None,
        "status": run.status,
        "error_message": run.error_message,
        "carried_count": len(run.carried or []),
        "left": _table_view(left) if left else None,
        "right": _table_view(right) if right else None,
        "config": config_view(ReconConfig.from_json(run.config), sides=side_labels(session, run)),
        "period_start": run.period_start.isoformat() if run.period_start else None,
        "period_end": run.period_end.isoformat() if run.period_end else None,
        "summary": run.summary,
        "verification": _named_verification(run.verification, side_labels(session, run)),
        "exceptions": {
            "OPEN": statuses.get("OPEN", 0),
            "EXPLAINED": statuses.get("EXPLAINED", 0),
            "RESOLVED": statuses.get("RESOLVED", 0),
        },
        "open_by_kind": {kind: open_by_kind.get(kind, 0) for kind in KINDS},
        # Số kết quả của từng nhóm hiển thị (cùng điều kiện lọc với API danh sách kết quả).
        # Đếm cả 7 nhóm trong một câu truy vấn (COUNT … FILTER), trước đây mỗi nhóm một câu.
        "group_counts": dict(
            zip(
                GROUPS,
                session.execute(
                    select(*(func.count().filter(_group_filter(group)) for group in GROUPS))
                    .select_from(MatchResult)
                    .where(MatchResult.run_id == run.id)
                ).one(),
                strict=True,
            )
        ),
        # Nhãn loại theo đúng cặp: "Chỉ có ở bo-1-don-hang-cua-hang" thay cho "Chỉ có ở A".
        "kind_labels": {
            kind: name_sides(label, *side_labels(session, run))
            for kind, label in KIND_LABELS.items()
        },
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _details(
    version: CleanVersion | None,
    refs: set[int],
    key: str | None,
    day: str | None,
    amount: str,
    extra: tuple[str, ...] = DETAIL_FIELDS,
) -> dict[int, dict[str, Any]]:
    """Giá trị đã chuẩn hóa của các dòng cần hiển thị (đọc đúng phiên bản sạch đã dùng).

    `extra`: các cột thêm ngoài mã, ngày, số tiền; báo cáo chỉ cần mã và ngày nên truyền ()."""
    if version is None or not refs:
        return {}
    frame = pl.scan_parquet(version.parquet_path).filter(pl.col(ROW_REF).is_in(sorted(refs)))
    names = frame.collect_schema().names()
    wanted = {"key": key, "date": day, "amount": amount} | {name: name for name in extra}
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
        "matched": MatchResult.kind.in_(("MATCHED", "MANY_TO_ONE", "ONE_TO_MANY"))
        & MatchResult.exception_status.is_(None),
        "pending": MatchResult.kind == "PENDING_SETTLEMENT",
        "out_of_scope": MatchResult.kind == "OUT_OF_SCOPE",
    }[group]


def _refs_text(session: Session, run: ReconRun, left_refs: list[int], right_refs: list[int]) -> str:
    """Các dòng hai bên đọc được bằng mắt cho nhật ký kiểm toán: mã đơn và tên bảng, ví dụ
    "HD000142 (don-hang-cua-hang) ↔ HD000950 (giao-dich-cong-thanh-toan)". Dòng không có mã
    gọi theo số dòng gốc; dòng mang sang từ kỳ trước (số âm) ghi "dòng kỳ trước".
    Trước đây ghi "A43, B74", người đọc phải tự tra bên A, B là bảng nào."""
    config = ReconConfig.from_json(run.config)

    def side(refs: list[int], version_id: Any, key: str | None, table_id: uuid.UUID) -> str:
        if not refs:
            return ""
        found = _details(session.get(CleanVersion, version_id), set(refs), key, None, "", ())
        names = [
            "dòng kỳ trước" if ref < 0 else found.get(ref, {}).get("key") or f"dòng {ref}"
            for ref in refs
        ]
        table = session.get(DatasetTable, table_id)
        return f"{', '.join(names)} ({audit.table_label(table) if table else 'bảng đã xóa'})"

    parts = [
        side(left_refs, run.left_version_id, config.key_left, run.left_table_id),
        side(right_refs, run.right_version_id, config.key_right, run.right_table_id),
    ]
    return " ↔ ".join(part for part in parts if part)


def _result_label(session: Session, run: ReconRun, item: MatchResult) -> str:
    sides = _refs_text(session, run, list(item.left_refs), list(item.right_refs))
    kind = name_sides(KIND_LABELS.get(item.kind, item.kind), *side_labels(session, run))
    return f"{kind}: {sides}"


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
        "config": config_view(
            config, evidence, (audit.table_label(left), audit.table_label(right))
        ),
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
        config, _ = recon_service.preview(left, right, session)
    except ValueError as error:
        raise fail(422, "CANNOT_RECONCILE", str(error)) from error
    if request.tolerance is not None:
        config.tolerance = parse_tolerance(request.tolerance)
    if request.date_window_days is not None:
        config.date_window_days = request.date_window_days
    if request.excluded is not None:
        config.excluded = {
            side: fields for side, fields in request.excluded.items() if side in ("LEFT", "RIGHT")
        }
    run = recon_service.create_run(session, left, right, config)
    audit.record(
        session,
        "RECON_RUN",
        "RECON_RUN",
        run.id,
        f"{audit.table_label(left)} ↔ {audit.table_label(right)}",
        "Chạy đối soát. "
        + " ".join(
            config_view(
                config, sides=(audit.table_label(left), audit.table_label(right))
            )["description"]
        ),
        after={"config": config.to_json()},
    )
    session.commit()
    background.add_task(recon_service.execute_run, run.id)
    return run_view(session, run)


@router.get("/recon/runs")
def list_runs(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    standalone: bool = False,
) -> list[dict[str, Any]]:
    """Các lần đối soát mới nhất. `standalone`: chỉ lần chạy hai bảng đứng riêng (không thuộc
    chuỗi) — trang Đối soát chỉ cần chúng cho mục "hai bảng tự chọn"; kết quả theo kỳ đọc qua
    chuỗi. Trước đây trang tải 20 lần chạy kể cả của chuỗi (69 KB, khoảng 0,7 giây)."""
    query = (
        select(ReconRun)
        .where(ReconRun.left_table_id.in_(workspaces.table_ids(session)))
        .order_by(ReconRun.created_at.desc())
        .limit(limit)
    )
    if standalone:
        query = query.where(ReconRun.chain_id.is_(None))
    return [run_view(session, run) for run in session.scalars(query)]


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
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": _result_views(session, run, items),
    }


def _result_views(
    session: Session, run: ReconRun, items: list[MatchResult]
) -> list[dict[str, Any]]:
    """Kết quả kèm giá trị đã chuẩn hóa của các dòng hai bên (chỉ đọc đúng các dòng cần)."""
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
    carried = _carried_details(session, items, config)
    sides = side_labels(session, run)
    return [
        {
            "id": str(item.id),
            "kind": item.kind,
            # Nhãn và lý do của engine viết "A"/"B" chung cho mọi cặp: đổi thành tên bảng.
            "kind_label": name_sides(KIND_LABELS.get(item.kind, item.kind), *sides),
            "score": item.score,
            "reasons": [
                reason | {"text": name_sides(reason["text"], *sides)} for reason in item.reasons
            ],
            "amount_left": None if item.amount_left is None else str(item.amount_left),
            "amount_right": None if item.amount_right is None else str(item.amount_right),
            "exception_status": item.exception_status,
            "note": item.note,
            "left": [left.get(ref, {"row_ref": ref}) for ref in item.left_refs]
            + [
                carried.get((row["table_id"], row["row_ref"]), {"row_ref": row["row_ref"]})
                | {"carried": True}
                for row in item.carried_left or []
            ],
            "right": [right.get(ref, {"row_ref": ref}) for ref in item.right_refs],
        }
        for item in items
    ]


def _carried_details(
    session: Session,
    items: list[MatchResult],
    config: ReconConfig,
    extra: tuple[str, ...] = DETAIL_FIELDS,
) -> dict[tuple[str, int], dict[str, Any]]:
    """Giá trị của các dòng chờ từ kỳ trước (đọc từ phiên bản sạch của bảng kỳ trước)."""
    by_version: dict[str, set[int]] = {}
    tables: dict[str, str] = {}
    for item in items:
        for row in item.carried_left or []:
            if row.get("version_id"):
                by_version.setdefault(row["version_id"], set()).add(row["row_ref"])
                tables[row["version_id"]] = row["table_id"]
    found: dict[tuple[str, int], dict[str, Any]] = {}
    for version_id, refs in by_version.items():
        version = session.get(CleanVersion, uuid.UUID(version_id))
        table = session.get(DatasetTable, uuid.UUID(tables[version_id]))
        details = _details(
            version, refs, config.key_left, config.date_left, config.amount_left, extra
        )
        for ref, detail in details.items():
            found[(tables[version_id], ref)] = detail | {
                "table_label": audit.table_label(table) if table else None
            }
    return found


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
    changed_items: list[MatchResult] = []
    for item in items:
        before = item.exception_status
        after = "RESOLVED" if action.action == "RESOLVE" else ("EXPLAINED" if item.note else "OPEN")
        if before != after:
            item.exception_status, item.updated_at = after, now
            changed.append({"id": str(item.id), "before": before, "after": after})
            changed_items.append(item)
    if changed:
        verb = "Đánh dấu đã xử lý" if action.action == "RESOLVE" else "Mở lại"
        # Chỉ đọc mã đơn khi ghi một kết quả; "Đồng ý tất cả" thì ghi số đếm, khỏi đọc tệp.
        target = (
            _result_label(session, run, changed_items[0])
            if len(changed) == 1
            else f"{len(changed)} kết quả"
            + (f" loại {KIND_LABELS.get(action.kind, action.kind)}" if action.kind else "")
        )
        audit.record(
            session,
            f"EXCEPTION_{action.action}",
            "RECON_RUN",
            run.id,
            recon_service.run_label(session, run),
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
        recon_service.run_label(session, run),
        f"Ghi chú cho {_result_label(session, run, item)}: “{note}”." if note else
        f"Xóa ghi chú của {_result_label(session, run, item)}.",
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
    view = _result_views(session, run, [item])[0]
    return recon_ai.explain_result(
        view, config_view(ReconConfig.from_json(run.config), sides=side_labels(session, run))
    )


# ---------------------------------------------------------------- chuỗi ba bên, ca mơ hồ


def chain_view(session: Session, chain: ReconChain) -> dict[str, Any]:
    runs = list(
        session.scalars(select(ReconRun).where(ReconRun.chain_id == chain.id))
    )
    runs.sort(key=lambda run: recon_service.chain_order(session, run))
    views = [run_view(session, run) for run in runs]
    return {
        "id": str(chain.id),
        "status": chain.status,
        "error_message": chain.error_message,
        "label": chain.label,
        # Nhãn nhóm khi gộp ngoại lệ của nhiều cặp: gọi theo ý nghĩa tiền (như trang Báo cáo),
        # tên bảng ghi ở từng ca.
        "kind_labels": CHAIN_KIND_LABELS,
        "table_ids": chain.table_ids,
        "period_start": chain.period_start.isoformat() if chain.period_start else None,
        "period_end": chain.period_end.isoformat() if chain.period_end else None,
        "runs": views,
        "exceptions": {
            status: sum(view["exceptions"][status] for view in views)
            for status in ("OPEN", "EXPLAINED", "RESOLVED")
        },
        "pending": sum(view["group_counts"]["pending"] for view in views),
        "verified": chain.status == "READY"
        and all((view["verification"] or {}).get("passed") for view in views),
        "created_at": chain.created_at.isoformat() if chain.created_at else None,
    }


@router.get("/recon/periods")
def recon_periods(session: SessionDep) -> list[dict[str, Any]]:
    """Các kỳ đối soát nhận ra từ các tệp sao kê, kèm lần chạy chuỗi gần nhất của mỗi kỳ."""
    tables = recon_service.ready_tables(session)
    labels = {str(table.id): _table_view(table) for table in tables}
    periods = recon_service.detect_periods(tables)
    chains = list(
        session.scalars(
            select(ReconChain)
            .where(ReconChain.workspace_id == workspaces.current_id(session))
            .order_by(ReconChain.created_at.desc())
        )
    )
    result = []
    for period in periods:
        latest = next(
            (chain for chain in chains if set(chain.table_ids) == set(period["table_ids"])), None
        )
        result.append(
            {
                "label": period["label"],
                "period_start": period["period_start"].isoformat(),
                "period_end": period["period_end"].isoformat(),
                "tables": [labels[table_id] for table_id in period["table_ids"]],
                "chain_id": str(latest.id) if latest else None,
            }
        )
    return result


def _period_label(session: Session, tables: list[DatasetTable]) -> str:
    """Tên chuỗi khi người gọi không đặt tên: tên kỳ hệ thống nhận ra cho đúng bộ bảng này
    (ví dụ "Kỳ 01/10 – 14/10/2026"); không khớp kỳ nào thì ghép tên các bảng. Tên này hiện ở
    trang Đối soát, Báo cáo và Lịch sử, nên không để dãy tên bảng dài khi đã biết kỳ."""
    wanted = {str(table.id) for table in tables}
    for period in recon_service.detect_periods(recon_service.ready_tables(session)):
        if set(period["table_ids"]) == wanted:
            return str(period["label"])
    return " · ".join(audit.table_label(table) for table in tables)


@router.post("/recon/chains", status_code=202)
def start_chain(
    request: ChainRequest, session: SessionDep, background: BackgroundTasks
) -> dict[str, Any]:
    """Đối soát cả chuỗi của một kỳ: mọi cặp nối được (đơn hàng ↔ cổng ↔ sao kê)."""
    tables = [_table(session, table_id) for table_id in dict.fromkeys(request.table_ids)]
    label = request.label or _period_label(session, tables)
    try:
        chain = recon_service.create_chain(session, tables, label)
    except ValueError as error:
        raise fail(422, "CANNOT_RECONCILE", str(error)) from error
    audit.record(
        session,
        "RECON_CHAIN",
        "RECON_CHAIN",
        chain.id,
        label,
        f"Đối soát cả chuỗi: {label}.",
        after={"table_ids": chain.table_ids},
    )
    session.commit()
    background.add_task(recon_service.execute_chain, chain.id)
    return chain_view(session, chain)


@router.get("/recon/chains/{chain_id}")
def get_chain(chain_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
    chain = workspaces.owned(session, session.get(ReconChain, chain_id))
    if chain is None:
        raise fail(404, "CHAIN_NOT_FOUND", "Không tìm thấy chuỗi đối soát.")
    return chain_view(session, chain)


@router.get("/recon/chains/{chain_id}/trace")
def chain_trace(
    chain_id: uuid.UUID, table_id: uuid.UUID, row_ref: int, session: SessionDep
) -> dict[str, Any]:
    """Đường đi của một dòng qua các cặp trong chuỗi (đơn → giao dịch cổng → dòng sao kê)."""
    chain = workspaces.owned(session, session.get(ReconChain, chain_id))
    if chain is None:
        raise fail(404, "CHAIN_NOT_FOUND", "Không tìm thấy chuỗi đối soát.")
    return {"steps": recon_service.trace(session, chain, table_id, row_ref)}


@router.post("/recon/runs/{run_id}/choose", status_code=202)
def choose_candidate(
    run_id: uuid.UUID, choice: AmbiguousChoice, session: SessionDep, background: BackgroundTasks
) -> dict[str, Any]:
    """Người dùng chọn cặp đúng cho một ca mơ hồ. Lựa chọn được lưu (áp dụng ở mọi lần chạy
    sau) và cặp bảng (hoặc cả chuỗi) được chạy lại để kết quả và kiểm chứng cập nhật."""
    run = _run(session, run_id)
    item = session.get(MatchResult, choice.result_id)
    if item is None or item.run_id != run.id or item.kind != "AMBIGUOUS":
        raise fail(404, "RESULT_NOT_FOUND", "Không tìm thấy ca mơ hồ này.")
    pairs = [
        pair
        for reason in item.reasons
        if reason.get("code") == "CANDIDATES"
        for pair in reason.get("pairs", [])
    ]
    wanted = (sorted(choice.left_refs), sorted(choice.right_refs))
    if not any((sorted(pair["left"]), sorted(pair["right"])) == wanted for pair in pairs):
        raise fail(422, "NOT_A_CANDIDATE", "Lựa chọn không nằm trong các ứng viên của ca này.")
    session.add(
        ReconChoice(
            id=uuid.uuid4(),
            left_table_id=run.left_table_id,
            right_table_id=run.right_table_id,
            left_refs=wanted[0],
            right_refs=wanted[1],
        )
    )
    audit.record(
        session,
        "AMBIGUOUS_CHOSEN",
        "RECON_RUN",
        run.id,
        recon_service.run_label(session, run),
        f"Chọn cặp {_refs_text(session, run, wanted[0], wanted[1])} cho ca mơ hồ.",
        {"candidates": pairs},
        {"left_refs": wanted[0], "right_refs": wanted[1]},
    )
    return _rerun(session, run, background)


def _rerun(session: Session, run: ReconRun, background: BackgroundTasks) -> dict[str, Any]:
    """Sau một quyết định của người dùng (chọn ca mơ hồ, ghép tay, gỡ ghép): chạy lại cả chuỗi
    (nếu lần chạy thuộc chuỗi) hoặc cặp bảng, để kết quả và kiểm chứng phản ánh quyết định.
    Trả về mã chuỗi hoặc mã lần chạy mới để giao diện tải."""
    if run.chain_id:
        chain = session.get(ReconChain, run.chain_id)
        assert chain is not None
        tables = [_table(session, uuid.UUID(table_id)) for table_id in chain.table_ids]
        new_chain = recon_service.create_chain(session, tables, chain.label)
        session.commit()
        background.add_task(recon_service.execute_chain, new_chain.id)
        return {"chain_id": str(new_chain.id), "run_id": None}
    left, right = _table(session, run.left_table_id), _table(session, run.right_table_id)
    new_run = recon_service.create_run(session, left, right, ReconConfig.from_json(run.config))
    session.commit()
    background.add_task(recon_service.execute_run, new_run.id)
    return {"chain_id": None, "run_id": str(new_run.id)}


# ---------------------------------------------------------------- ghép tay, gỡ ghép

# Dòng "chưa được ghép" của mỗi bên: chỉ những dòng này mới ghép tay được.
UNMATCHED_LEFT: tuple[str, ...] = ("ONLY_IN_A", "PENDING_SETTLEMENT")
UNMATCHED_RIGHT: tuple[str, ...] = ("ONLY_IN_B",)
# Kết quả đã ghép (một cặp hoặc một nhóm): những kết quả này gỡ ghép được.
PAIRED = ("MATCHED", "MANY_TO_ONE", "ONE_TO_MANY", "AMOUNT_MISMATCH")
MAX_MATCH_CANDIDATES = 30


class ManualMatch(BaseModel):
    left_refs: list[int] = Field(min_length=1, max_length=20)
    right_refs: list[int] = Field(min_length=1, max_length=20)


def _results_of_kinds(session: Session, run: ReconRun, kinds: tuple[str, ...]) -> list[MatchResult]:
    return list(
        session.scalars(
            select(MatchResult)
            .where(MatchResult.run_id == run.id, MatchResult.kind.in_(kinds))
            .order_by(MatchResult.position)
        )
    )


def _day(row: dict[str, Any]) -> datetime | None:
    value = row.get("date")
    return datetime.fromisoformat(value[:10]) if value else None


@router.get("/recon/results/{result_id}/match-candidates")
def match_candidates(result_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
    """Dòng chưa ghép ở bên kia để ghép tay với một dòng "chỉ có ở một bên": gần số tiền nhất
    trước, rồi gần ngày nhất. Hệ thống chỉ gợi ý thứ tự; người dùng quyết định."""
    item = session.get(MatchResult, result_id)
    if item is None:
        raise fail(404, "RESULT_NOT_FOUND", "Không tìm thấy kết quả.")
    run = _run(session, item.run_id)
    if item.kind in UNMATCHED_LEFT and item.left_refs:
        side, other_kinds = "B", UNMATCHED_RIGHT
    elif item.kind in UNMATCHED_RIGHT:
        side, other_kinds = "A", UNMATCHED_LEFT
    else:
        raise fail(422, "NOT_UNMATCHED", "Chỉ ghép tay được dòng chưa được ghép.")
    others = [
        other
        for other in _results_of_kinds(session, run, other_kinds)
        if (other.left_refs if side == "A" else other.right_refs)
    ]
    views = _result_views(session, run, [item, *others])
    target = (views[0]["left"] if side == "B" else views[0]["right"])[0]
    target_amount = Decimal(target["amount"]) if target.get("amount") else None
    target_day = _day(target)

    def row_of(view: dict[str, Any]) -> dict[str, Any]:
        rows: list[dict[str, Any]] = view["right"] if side == "B" else view["left"]
        return rows[0]

    def closeness(view: dict[str, Any]) -> tuple[Decimal, int, int]:
        row = row_of(view)
        amount = Decimal(row["amount"]) if row.get("amount") else None
        gap = (
            abs(amount - target_amount)
            if amount is not None and target_amount is not None
            else Decimal("Infinity")
        )
        day = _day(row)
        days = abs((day - target_day).days) if day and target_day else 10**6
        return gap, days, row["row_ref"]

    ranked = sorted(views[1:], key=closeness)[:MAX_MATCH_CANDIDATES]
    return {
        "side": side,
        # Tên bảng của các ứng viên (giao diện ghi "dòng chưa ghép ở <bảng>", không "bên A/B").
        "side_label": side_labels(session, run)[0 if side == "A" else 1],
        "target": target,
        "candidates": [
            {
                "result_id": view["id"],
                "row": row_of(view),
                "amount_gap": str(closeness(view)[0]) if target_amount is not None else None,
            }
            for view in ranked
        ],
    }


@router.post("/recon/runs/{run_id}/match", status_code=202)
def manual_match(
    run_id: uuid.UUID, choice: ManualMatch, session: SessionDep, background: BackgroundTasks
) -> dict[str, Any]:
    """Ghép tay các dòng chưa ghép của hai bên (một cặp hoặc một nhóm). Lựa chọn được lưu và
    áp dụng ở mọi lần chạy sau; lệch tiền thì kết quả vẫn là ngoại lệ "lệch tiền" để xử lý."""
    run = _run(session, run_id)
    if run.status != "READY":
        raise fail(409, "RUN_NOT_READY", "Lần đối soát chưa chạy xong.")
    free_left = {
        ref for item in _results_of_kinds(session, run, UNMATCHED_LEFT) for ref in item.left_refs
    }
    free_right = {
        ref for item in _results_of_kinds(session, run, UNMATCHED_RIGHT) for ref in item.right_refs
    }
    left_refs, right_refs = sorted(set(choice.left_refs)), sorted(set(choice.right_refs))
    if not set(left_refs) <= free_left or not set(right_refs) <= free_right:
        raise fail(422, "NOT_UNMATCHED", "Chỉ ghép tay được các dòng chưa được ghép.")
    # Ghép tay lại đúng các dòng từng gỡ ghép thì bỏ lệnh cấm cũ của chúng.
    for old in session.scalars(
        select(ReconChoice).where(
            ReconChoice.left_table_id == run.left_table_id,
            ReconChoice.right_table_id == run.right_table_id,
            ReconChoice.action == "UNMATCH",
        )
    ):
        if set(old.left_refs) & set(left_refs) and set(old.right_refs) & set(right_refs):
            session.delete(old)
    session.add(
        ReconChoice(
            id=uuid.uuid4(),
            left_table_id=run.left_table_id,
            right_table_id=run.right_table_id,
            left_refs=left_refs,
            right_refs=right_refs,
            action="MATCH",
        )
    )
    audit.record(
        session,
        "MANUAL_MATCH",
        "RECON_RUN",
        run.id,
        recon_service.run_label(session, run),
        f"Ghép tay {_refs_text(session, run, left_refs, right_refs)}.",
        None,
        {"left_refs": left_refs, "right_refs": right_refs},
    )
    return _rerun(session, run, background)


@router.post("/recon/results/{result_id}/unmatch", status_code=202)
def unmatch(
    result_id: uuid.UUID, session: SessionDep, background: BackgroundTasks
) -> dict[str, Any]:
    """Gỡ một cặp (hoặc nhóm) đã ghép: các dòng trở về "chưa ghép" và không vòng tự động nào
    được ghép chúng với nhau nữa. Người dùng có thể ghép tay lại theo cách đúng."""
    item = session.get(MatchResult, result_id)
    if item is None:
        raise fail(404, "RESULT_NOT_FOUND", "Không tìm thấy kết quả.")
    run = _run(session, item.run_id)
    if item.kind not in PAIRED or not item.left_refs or not item.right_refs:
        raise fail(422, "NOT_PAIRED", "Chỉ gỡ được kết quả đã ghép giữa hai bên.")
    left_refs, right_refs = sorted(item.left_refs), sorted(item.right_refs)
    # Cặp do người dùng chọn trước đây (ca mơ hồ, ghép tay) nằm trong kết quả này: bỏ lựa chọn.
    for old in session.scalars(
        select(ReconChoice).where(
            ReconChoice.left_table_id == run.left_table_id,
            ReconChoice.right_table_id == run.right_table_id,
            ReconChoice.action == "MATCH",
        )
    ):
        if set(old.left_refs) <= set(left_refs) and set(old.right_refs) <= set(right_refs):
            session.delete(old)
    session.add(
        ReconChoice(
            id=uuid.uuid4(),
            left_table_id=run.left_table_id,
            right_table_id=run.right_table_id,
            left_refs=left_refs,
            right_refs=right_refs,
            action="UNMATCH",
        )
    )
    audit.record(
        session,
        "RESULT_UNMATCHED",
        "RECON_RUN",
        run.id,
        recon_service.run_label(session, run),
        f"Gỡ ghép {_result_label(session, run, item)}.",
        {"kind": item.kind, "left_refs": left_refs, "right_refs": right_refs},
        None,
    )
    return _rerun(session, run, background)


# ---------------------------------------------------------------- nhật ký kiểm toán


@router.get("/audit")
def audit_log(
    session: SessionDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    mine = AuditLog.workspace_id == workspaces.current_id(session)
    total = session.scalar(select(func.count()).select_from(AuditLog).where(mine)) or 0
    items = session.scalars(
        select(AuditLog)
        .where(mine)
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
