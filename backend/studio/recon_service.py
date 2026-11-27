"""Chạy đối soát trên các bộ sạch mới nhất, lưu kết quả và kiểm chứng (chạy nền).

Nối engine (`reconciliation`), kiểm chứng độc lập (`recon_verification`) với cơ sở dữ liệu:
- chọn cặp bảng và cấu hình gợi ý;
- mỗi lần chạy lưu thành một `ReconRun` mới kèm phiên bản bộ sạch đã dùng;
- trạng thái ngoại lệ và ghi chú của lần trước được mang sang lần sau nếu kết quả giống hệt;
- dòng "chờ tiền về" của kỳ trước được mang sang lần đối soát kỳ sau của cùng loại bảng;
- lựa chọn của người dùng cho ca mơ hồ được áp dụng ở mọi lần chạy sau;
- chuỗi ba bên: nhận ra các kỳ theo sao kê, chạy mọi cặp nối được trong kỳ, mỗi dòng chỉ
  được báo ở một cặp (docs/DECISIONS.md 2026-11-23).
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from itertools import combinations
from typing import Any

import polars as pl
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from studio import audit, database, workspaces
from studio.cleaning import latest_version
from studio.models import (
    CleanVersion,
    DatasetTable,
    MatchResult,
    ReconChain,
    ReconChoice,
    ReconRun,
)
from studio.reading import ROW_REF
from studio.recon_verification import verify
from studio.reconciliation import (
    ReconConfig,
    Result,
    Side,
    reconcile,
    suggest_config,
    summarize,
)
from studio.sales_fields import FIELDS_BY_KEY

logger = logging.getLogger(__name__)

# Thứ tự bên A → B theo loại bảng: đơn hàng ở bên A, tiền về ở bên B.
SIDE_RANK = {"ORDERS_POS": 0, "ORDERS_PLATFORM": 0, "PAYMENT_GATEWAY": 1, "BANK_STATEMENT": 2}
# Tỷ lệ khớp mã tối thiểu để gợi ý một cặp bảng.
MIN_PAIR_MATCH_RATE = 0.05
# Trong chuỗi: tỷ lệ tối thiểu các dòng nối được có tổng tiền hai bên bằng nhau.
MIN_PAIR_AMOUNT_RATE = 0.5
# Bảng thuộc kỳ của một sao kê khi ngày sớm nhất của nó không trước ngày đầu sao kê quá 3 ngày.
PERIOD_LEAD_DAYS = 3
# Loại kết quả đã ghép (dòng không còn là "chỉ có ở một bên").
PAIRED_KINDS = ("MATCHED", "MANY_TO_ONE", "ONE_TO_MANY", "AMOUNT_MISMATCH", "DUPLICATE")
# Ghép chắc chắn: theo mã hoặc do người dùng chọn (không phải theo điểm hay tổng tiền).
STRONG_REASONS = ("KEY", "USER")


def ready_tables(session: Session) -> list[DatasetTable]:
    """Các bảng của phiên đang mở đã có bộ sạch, dùng được để đối soát."""
    tables = session.scalars(
        select(DatasetTable).where(
            DatasetTable.status == "READY", DatasetTable.id.in_(workspaces.table_ids(session))
        )
    ).all()
    return [table for table in tables if latest_version(table) is not None]


def clean_frame(version: CleanVersion) -> pl.DataFrame:
    return pl.read_parquet(version.parquet_path)


def unclean_refs(version: CleanVersion) -> set[int]:
    """Dòng còn vấn đề mức "Hỏi" chưa xử lý ở bộ sạch."""
    return {
        ref
        for issue in version.issues
        if issue["level"] == "ASK" and issue["status"] == "OPEN"
        for ref in issue["row_refs"]
    }


def forget_chains(session: Session, table_ids: list[uuid.UUID]) -> None:
    """Xóa các chuỗi đối soát có dùng một trong các bảng sắp bị xóa (xóa hoặc đọc lại bộ dữ
    liệu). Chuỗi lưu danh sách bảng dạng JSON, không có khóa ngoại để tự xóa theo; các lần
    chạy trong chuỗi bị xóa theo chuỗi (ondelete CASCADE)."""
    wanted = {str(table_id) for table_id in table_ids}
    for chain in session.scalars(select(ReconChain)):
        if wanted & {str(item) for item in chain.table_ids}:
            session.delete(chain)


# ---------------------------------------------------------------- gợi ý cặp, kỳ


@lru_cache(maxsize=64)
def _key_sets(version_id: uuid.UUID, parquet_path: str) -> dict[str, frozenset[str]]:
    """Tập giá trị của từng cột mã trong một phiên bản bộ sạch (phiên bản không bao giờ đổi
    nội dung nên nhớ theo mã phiên bản là an toàn). Chỉ đọc các cột mã, không đọc cả bảng."""
    names = pl.scan_parquet(parquet_path).collect_schema().names()
    keys = [
        name for name in names if name in FIELDS_BY_KEY and FIELDS_BY_KEY[name].type == "IDENTIFIER"
    ]
    if not keys:
        return {}
    frame = pl.read_parquet(parquet_path, columns=keys)
    return {name: frozenset(frame[name].drop_nulls().to_list()) for name in keys}


@lru_cache(maxsize=64)
def _date_range(version_id: uuid.UUID, parquet_path: str) -> tuple[date, date] | None:
    """Ngày sớm nhất và muộn nhất của bảng (theo các cột ngày chuẩn)."""
    names = pl.scan_parquet(parquet_path).collect_schema().names()
    columns = [
        name for name in names if name in FIELDS_BY_KEY and FIELDS_BY_KEY[name].type == "DATE"
    ]
    if not columns:
        return None
    frame = pl.read_parquet(parquet_path, columns=columns)
    days = [value for name in columns for value in frame[name].drop_nulls().to_list()]
    return (min(days), max(days)) if days else None


def suggest_pair(tables: list[DatasetTable]) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Cặp bảng nên đối soát: cặp có tỷ lệ khớp mã cao nhất; bên A là bảng đơn hàng.

    Chỉ so tập mã của các cột mã (rẻ, nhớ theo phiên bản bộ sạch), không dựng cấu hình đầy
    đủ cho mọi cặp. Bảng nào đọc lỗi thì bỏ qua, không làm hỏng cả trang.
    """
    keys: dict[uuid.UUID, dict[str, frozenset[str]]] = {}
    for table in tables:
        version = latest_version(table)
        if version is None:
            continue
        try:
            keys[table.id] = _key_sets(version.id, version.parquet_path)
        except Exception:
            logger.warning("Không đọc được bộ sạch của bảng %s; bỏ qua khi gợi ý cặp", table.id)
    best: tuple[float, uuid.UUID, uuid.UUID] | None = None
    for first, second in combinations([table for table in tables if table.id in keys], 2):
        left, right = sorted(
            (first, second),
            key=lambda table: (SIDE_RANK.get(table.table_kind or "", 3), str(table.id)),
        )
        for left_values in keys[left.id].values():
            for right_values in keys[right.id].values():
                if not left_values:
                    continue
                rate = len(left_values & right_values) / len(left_values)
                if rate >= MIN_PAIR_MATCH_RATE and (best is None or rate > best[0]):
                    best = (rate, left.id, right.id)
    return (best[1], best[2]) if best else None


def detect_periods(tables: list[DatasetTable]) -> list[dict[str, Any]]:
    """Các kỳ đối soát, mỗi kỳ theo một tệp sao kê (docs/DECISIONS.md 2026-11-23: mỗi lần tải
    tệp kỳ mới). Bảng khác thuộc kỳ khi ngày sớm nhất của nó nằm trong khoảng ngày sao kê
    (cho phép sớm hơn PERIOD_LEAD_DAYS ngày vì tiền về sau ngày đơn)."""
    ranges: dict[uuid.UUID, tuple[date, date]] = {}
    for table in tables:
        version = latest_version(table)
        if version is None:
            continue
        try:
            found = _date_range(version.id, version.parquet_path)
        except Exception:
            logger.warning("Không đọc được ngày của bảng %s", table.id)
            continue
        if found:
            ranges[table.id] = found
    banks: dict[uuid.UUID, list[DatasetTable]] = defaultdict(list)
    for table in tables:
        if table.table_kind == "BANK_STATEMENT" and table.id in ranges:
            banks[table.dataset_id].append(table)
    periods = []
    used: set[uuid.UUID] = set()
    for sheets in sorted(banks.values(), key=lambda group: min(ranges[t.id][0] for t in group)):
        start = min(ranges[t.id][0] for t in sheets)
        end = max(ranges[t.id][1] for t in sheets)
        members = list(sheets)
        for table in tables:
            if table.id in used or table.table_kind == "BANK_STATEMENT" or table.id not in ranges:
                continue
            first_day = ranges[table.id][0]
            if start - timedelta(days=PERIOD_LEAD_DAYS) <= first_day <= end:
                members.append(table)
                used.add(table.id)
        periods.append(
            {
                "label": f"Kỳ {start:%d/%m} – {end:%d/%m/%Y}",
                "period_start": start,
                "period_end": end,
                "table_ids": [str(table.id) for table in members],
            }
        )
    return periods


def preview(
    left: DatasetTable, right: DatasetTable, session: Session | None = None
) -> tuple[ReconConfig, dict[str, Any]]:
    """Cấu hình gợi ý cho một cặp bảng.

    Có `session` thì bên A gồm cả các dòng chờ tiền về từ kỳ trước: chúng cũng được ghép ở
    kỳ này, nên phải được tính khi tự học mẫu mã (ví dụ sao kê kỳ 2 có mã đơn kỳ 1 về muộn).
    """
    left_version, right_version = latest_version(left), latest_version(right)
    if left_version is None or right_version is None:
        raise ValueError("Bảng chưa có bộ dữ liệu sạch.")
    left_frame = clean_frame(left_version)
    if session is not None:
        extra = carried_frame(session, pending_from_previous(session, left, right))
        if extra is not None and extra.height:
            # Số dòng âm để không trùng số dòng của bảng hiện tại khi chấm cột tiền, cột ngày.
            extra = extra.drop("__origin").with_columns(
                pl.Series(ROW_REF, [-(index + 1) for index in range(extra.height)])
            )
            left_frame = pl.concat([left_frame, extra], how="diagonal_relaxed")
    return suggest_config(left_frame, clean_frame(right_version))


def reconcilable(config: ReconConfig, evidence: dict[str, Any]) -> bool:
    """Cặp bảng có nối được không: có cột mã chung khớp ≥ 5% hoặc tách được mã từ nội dung,
    và trên các dòng nối được, tổng tiền hai bên bằng nhau ở ít nhất một nửa số trường hợp.

    Điều kiện tiền chặn các cặp chỉ tình cờ trùng khóa, ví dụ ngày giao dịch của cổng thanh
    toán trùng với ngày ghi trong nội dung "doanh thu ngày dd/mm" của tài khoản sàn.
    """
    if not config.key_left:
        return False
    amounts = [
        item for item in evidence.get("amounts", [])
        if item["left"] == config.amount_left and item["right"] == config.amount_right
    ]
    if amounts and amounts[0]["equal_rate"] < MIN_PAIR_AMOUNT_RATE:
        return False
    if config.extract:
        return True
    return any(
        item["left"] == config.key_left
        and item["right"] == config.key_right
        and item["match_rate"] >= MIN_PAIR_MATCH_RATE
        for item in evidence["keys"]
    )


def _period(
    left: pl.DataFrame, right: pl.DataFrame, config: ReconConfig
) -> tuple[date | None, date | None]:
    """Kỳ đối soát: từ ngày sớm nhất tới ngày muộn nhất của hai bên."""
    days: list[date] = []
    for frame, column in ((left, config.date_left), (right, config.date_right)):
        if column and column in frame.columns:
            values = frame[column].drop_nulls()
            if len(values):
                days += [values.min(), values.max()]  # type: ignore[list-item]
    return (min(days), max(days)) if days else (None, None)


def result_rows(
    session: Session,
    run_id: uuid.UUID,
    *,
    kinds: tuple[str, ...] | None = None,
    decided_only: bool = False,
) -> list[MatchResult]:
    """Kết quả của một lần chạy. Lọc ngay trong SQL (theo loại, hoặc chỉ ca người dùng đã ghi
    chú/xử lý) để không nạp hàng trăm nghìn kết quả khi chỉ cần vài chục."""
    query = select(MatchResult).where(MatchResult.run_id == run_id)
    if kinds is not None:
        query = query.where(MatchResult.kind.in_(kinds))
    if decided_only:
        query = query.where(
            MatchResult.note.is_not(None)
            | MatchResult.exception_status.in_(("EXPLAINED", "RESOLVED"))
        )
    return list(session.scalars(query.order_by(MatchResult.position)))


# ---------------------------------------------------------------- dòng chờ, lựa chọn


def pending_from_previous(
    session: Session, left: DatasetTable, right: DatasetTable
) -> list[dict[str, Any]]:
    """Dòng "chờ tiền về" ở lần đối soát của kỳ liền trước, cùng loại bảng.

    Kỳ trước: bảng A cùng loại, bảng B cùng loại và cùng tên sheet nhưng là bảng khác (tệp của
    kỳ khác), và dữ liệu bên B bắt đầu TRƯỚC bên B hiện tại. Chọn kỳ gần nhất theo ngày dữ liệu
    (không theo thời điểm bấm chạy: chạy lại kỳ 1 sau kỳ 2 không được nhận dòng chờ của kỳ 2);
    trong cùng kỳ lấy lần chạy mới nhất. Lấy cả dòng chờ mà lần đó đã nhận từ kỳ trước nữa.
    """
    current = _start_day(right)
    if current is None:
        return []
    earlier: list[tuple[date, str, ReconRun]] = []
    for run in session.scalars(
        select(ReconRun).where(
            ReconRun.status == "READY",
            ReconRun.left_table_id != left.id,
            ReconRun.right_table_id != right.id,
        )
    ):
        run_left = session.get(DatasetTable, run.left_table_id)
        run_right = session.get(DatasetTable, run.right_table_id)
        version = session.get(CleanVersion, run.right_version_id) if run.right_version_id else None
        if (
            run_left is None
            or run_right is None
            or version is None
            # Kỳ trước phải cùng phiên làm việc: không mang dòng chờ của phiên khác sang.
            or run_left.dataset.workspace_id != left.dataset.workspace_id
            or run_left.table_kind != left.table_kind
            or run_right.table_kind != right.table_kind
            or run_right.sheet_name != right.sheet_name
        ):
            continue
        found = _date_range(version.id, version.parquet_path)
        if found and found[0] < current:
            earlier.append((found[0], str(run.created_at), run))
    if earlier:
        run = max(earlier, key=lambda item: (item[0], item[1]))[2]
        rows: list[dict[str, Any]] = []
        for item in result_rows(session, run.id, kinds=("PENDING_SETTLEMENT",)):
            rows += [
                {"table_id": str(run.left_table_id), "version_id": str(run.left_version_id),
                 "row_ref": ref}
                for ref in item.left_refs
            ]
            rows += list(item.carried_left or [])
        return rows
    return []


def _start_day(table: DatasetTable) -> date | None:
    """Ngày sớm nhất trong bộ sạch mới nhất của bảng (None nếu chưa có bộ sạch hay cột ngày)."""
    version = latest_version(table)
    if version is None:
        return None
    found = _date_range(version.id, version.parquet_path)
    return found[0] if found else None


def carried_frame(session: Session, carried: list[dict[str, Any]]) -> pl.DataFrame | None:
    """Bảng các dòng chờ từ kỳ trước, đọc đúng phiên bản sạch đã dùng, thêm cột "__origin"."""
    if not carried:
        return None
    by_version: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in carried:
        by_version[row["version_id"]].append(row)
    frames = []
    for version_id, rows in by_version.items():
        version = session.get(CleanVersion, uuid.UUID(version_id))
        if version is None:
            continue
        refs = [row["row_ref"] for row in rows]
        frame = clean_frame(version).filter(pl.col(ROW_REF).is_in(refs))
        frames.append(frame.with_columns(pl.lit(rows[0]["table_id"]).alias("__origin")))
    return pl.concat(frames, how="diagonal_relaxed") if frames else None


def choices_for(
    session: Session, left_id: uuid.UUID, right_id: uuid.UUID, action: str = "MATCH"
) -> list[dict[str, Any]]:
    """Lựa chọn của người dùng cho cặp bảng (cũ trước, mới sau): MATCH là các cặp phải ghép
    (chọn ca mơ hồ, ghép tay), UNMATCH là các cặp đã gỡ, không được tự ghép lại."""
    rows = session.scalars(
        select(ReconChoice)
        .where(
            ReconChoice.left_table_id == left_id,
            ReconChoice.right_table_id == right_id,
            ReconChoice.action == action,
        )
        .order_by(ReconChoice.created_at)
    )
    return [{"left": list(row.left_refs), "right": list(row.right_refs)} for row in rows]


# ---------------------------------------------------------------- tạo và chạy một lần


def create_run(
    session: Session,
    left: DatasetTable,
    right: DatasetTable,
    config: ReconConfig,
    chain_id: uuid.UUID | None = None,
) -> ReconRun:
    """Tạo một lần chạy RUNNING: gắn lựa chọn đã lưu và dòng chờ từ kỳ trước."""
    left_version, right_version = latest_version(left), latest_version(right)
    if left_version is None or right_version is None:
        raise ValueError("Bảng chưa có bộ dữ liệu sạch.")
    config.forced = choices_for(session, left.id, right.id, "MATCH")
    config.forbidden = choices_for(session, left.id, right.id, "UNMATCH")
    run = ReconRun(
        id=uuid.uuid4(),
        left_table_id=left.id,
        right_table_id=right.id,
        left_version_id=left_version.id,
        right_version_id=right_version.id,
        status="RUNNING",
        config=config.to_json(),
        chain_id=chain_id,
        carried=pending_from_previous(session, left, right) if config.settle_days else [],
    )
    session.add(run)
    return run


def compute(
    session: Session, run: ReconRun, elsewhere: dict[str, dict[int, str]] | None = None
) -> tuple[list[Result], pl.DataFrame, pl.DataFrame, ReconConfig]:
    """Chạy engine cho một lần chạy (chưa lưu)."""
    left_version = session.get(CleanVersion, run.left_version_id)
    right_version = session.get(CleanVersion, run.right_version_id)
    if left_version is None or right_version is None:
        raise ValueError("Không còn bộ dữ liệu sạch đã chọn.")
    config = ReconConfig.from_json(run.config)
    left, right = clean_frame(left_version), clean_frame(right_version)
    elsewhere = elsewhere or {}
    results = reconcile(
        Side(
            left,
            unclean_refs(left_version),
            carried_frame(session, run.carried or []),
            elsewhere.get("A", {}),
        ),
        Side(right, unclean_refs(right_version), elsewhere=elsewhere.get("B", {})),
        config,
    )
    versions = {row["table_id"]: row["version_id"] for row in run.carried or []}
    for item in results:
        for row in item.carried_left:
            row["version_id"] = versions.get(row["table_id"])
    return results, left, right, config


def persist(
    session: Session, run: ReconRun, results: list[Result], period: tuple[Any, Any]
) -> None:
    """Lưu kết quả, mang trạng thái ngoại lệ của lần trước sang, rồi kiểm chứng."""
    carried = _previous_decisions(session, run)
    now = datetime.now(UTC)
    values = []
    for position, item in enumerate(results):
        earlier = carried.get(
            result_key(item.kind, item.left_refs, item.right_refs, item.amount_left,
                       item.amount_right)
        )
        values.append(
            {
                "id": uuid.uuid4(),
                "run_id": run.id,
                "position": position,
                "kind": item.kind,
                "left_refs": item.left_refs,
                "right_refs": item.right_refs,
                "score": item.score,
                "reasons": item.reasons,
                "amount_left": item.amount_left,
                "amount_right": item.amount_right,
                "exception_status": (
                    None
                    if not item.needs_review
                    else earlier.exception_status
                    if earlier and earlier.exception_status
                    else "OPEN"
                ),
                "note": earlier.note if earlier else None,
                "updated_at": earlier.updated_at if earlier else now,
                "carried_left": item.carried_left or None,
            }
        )
    # Ghi một lượt (ORM bulk INSERT của SQLAlchemy 2) thay vì tạo từng đối tượng: ở 100.000 đơn
    # chuỗi có khoảng 240.000 kết quả, tạo từng đối tượng chiếm phần lớn thời gian đối soát.
    if values:
        session.execute(insert(MatchResult), values)
    run.summary = summarize(results)
    run.period_start, run.period_end = period
    session.flush()
    # Kiểm chứng đọc lại kết quả vừa ghi, không dùng biến trong bộ nhớ của engine.
    run.verification = verify_run(session, run)
    run.status = "READY"
    run.finished_at = datetime.now(UTC)


def verify_run(session: Session, run: ReconRun) -> dict[str, Any]:
    """Kiểm chứng lại lần chạy từ kết quả đã lưu trong cơ sở dữ liệu."""
    left_version = session.get(CleanVersion, run.left_version_id)
    right_version = session.get(CleanVersion, run.right_version_id)
    if left_version is None or right_version is None:
        return {"passed": False, "checks": [], "error": "Không còn bộ sạch đã dùng."}
    # Đọc đúng các cột cần kiểm từ cơ sở dữ liệu (không nạp đối tượng ORM, không đọc lý do).
    query = (
        select(
            MatchResult.kind,
            MatchResult.left_refs,
            MatchResult.right_refs,
            MatchResult.carried_left,
            MatchResult.amount_left,
            MatchResult.amount_right,
        )
        .where(MatchResult.run_id == run.id)
        .order_by(MatchResult.position)
    )
    rows = [
        {
            "kind": kind,
            "left_refs": left_refs,
            "right_refs": right_refs,
            "carried_left": carried_left or [],
            "amount_left": amount_left,
            "amount_right": amount_right,
        }
        for kind, left_refs, right_refs, carried_left, amount_left, amount_right in session.execute(
            query
        )
    ]
    return verify(
        clean_frame(left_version),
        clean_frame(right_version),
        rows,
        run.config,
        run.summary or {},
        carried_frame(session, run.carried or []),
    )


# Khóa so một kết quả giữa hai lần chạy: loại, các dòng hai bên và số tiền hai bên. Số tiền
# nằm trong khóa để khi dữ liệu đổi (ví dụ sửa ô làm lệch tiền khác đi), ca đã xử lý không
# được coi là "đã xử lý" nữa.
type ResultKey = tuple[str, tuple[int, ...], tuple[int, ...], Decimal | None, Decimal | None]


def result_key(
    kind: str,
    left_refs: list[int],
    right_refs: list[int],
    amount_left: Decimal | None,
    amount_right: Decimal | None,
) -> ResultKey:
    def money(value: Decimal | None) -> Decimal | None:
        return None if value is None else Decimal(value).quantize(Decimal("0.01"))

    return kind, tuple(left_refs), tuple(right_refs), money(amount_left), money(amount_right)


def _previous_decisions(session: Session, run: ReconRun) -> dict[ResultKey, MatchResult]:
    """Kết quả đã được người dùng xử lý ở lần chạy trước của cùng cặp bảng."""
    previous = session.scalar(
        select(ReconRun)
        .where(
            ReconRun.left_table_id == run.left_table_id,
            ReconRun.right_table_id == run.right_table_id,
            ReconRun.status == "READY",
            ReconRun.id != run.id,
        )
        .order_by(ReconRun.created_at.desc())
        .limit(1)
    )
    if previous is None:
        return {}
    return {
        result_key(
            item.kind, item.left_refs, item.right_refs, item.amount_left, item.amount_right
        ): item
        for item in result_rows(session, previous.id, decided_only=True)
    }


def execute_run(run_id: uuid.UUID) -> None:
    """Chạy đối soát cho một ReconRun đang ở trạng thái RUNNING (tác vụ nền)."""
    try:
        with database.SessionFactory() as session:
            run = session.get(ReconRun, run_id)
            if run is None:
                return
            results, left, right, config = compute(session, run)
            persist(session, run, results, _period(left, right, config))
            session.commit()
    except Exception:
        logger.exception("Lỗi khi đối soát lần chạy %s", run_id)
        _fail_run(run_id)


def _fail_run(run_id: uuid.UUID) -> None:
    with database.SessionFactory() as session:
        run = session.get(ReconRun, run_id)
        if run is not None:
            run.status = "FAILED"
            run.error_message = "Có lỗi khi đối soát. Hãy thử chạy lại."
            session.commit()


# ---------------------------------------------------------------- chuỗi ba bên


@dataclass
class ChainPair:
    left: DatasetTable
    right: DatasetTable
    config: ReconConfig


def chain_pairs(session: Session, tables: list[DatasetTable]) -> list[ChainPair]:
    """Mọi cặp nối được trong kỳ, theo thứ tự: đơn hàng ↔ cổng, đơn hàng ↔ sao kê, cổng ↔
    sao kê. Thứ tự này quyết định cặp nào báo một dòng chưa ghép (cặp đầu tiên có nó)."""
    pairs = []
    ordered = sorted(
        tables,
        key=lambda table: (SIDE_RANK.get(table.table_kind or "", 3), audit.table_label(table)),
    )
    for left in ordered:
        for right in ordered:
            rank_left = SIDE_RANK.get(left.table_kind or "", 3)
            rank_right = SIDE_RANK.get(right.table_kind or "", 3)
            if rank_left >= rank_right or rank_right == 3:
                continue
            try:
                config, evidence = preview(left, right, session)
            except ValueError:
                continue
            if reconcilable(config, evidence):
                pairs.append(ChainPair(left, right, config))
    return sorted(
        pairs,
        key=lambda pair: (
            SIDE_RANK.get(pair.left.table_kind or "", 3),
            SIDE_RANK.get(pair.right.table_kind or "", 3),
            audit.table_label(pair.left),
            audit.table_label(pair.right),
        ),
    )


NO_PAIRS = "Không tìm được cặp bảng nào nối được với nhau trong các bảng đã chọn."


def create_chain(session: Session, tables: list[DatasetTable], label: str) -> ReconChain:
    """Tạo chuỗi RUNNING và trả về ngay; các cặp được dò và tạo ở tác vụ nền (execute_chain).

    Dò cặp phải đọc dữ liệu và thử chọn trường cho từng cặp bảng: đo 27/11/2026 ở 30.000 đơn
    mất 5,7 giây, khi còn làm ngay trong lời gọi API thì nút "Đối soát cả chuỗi" (và mọi lần
    chạy lại sau khi ghép tay, chọn ca mơ hồ) đứng im chừng ấy. Ở đây chỉ kiểm nhanh điều kiện
    bắt buộc (mỗi bảng đã có bộ sạch) để báo lỗi ngay."""
    if any(latest_version(table) is None for table in tables):
        raise ValueError("Bảng chưa có bộ dữ liệu sạch.")
    chain = ReconChain(
        id=uuid.uuid4(),
        workspace_id=tables[0].dataset.workspace_id,
        status="RUNNING",
        label=label,
        table_ids=[str(table.id) for table in tables],
    )
    session.add(chain)
    session.flush()
    return chain


def _create_chain_runs(session: Session, chain: ReconChain) -> bool:
    """Dò các cặp nối được của chuỗi và tạo lần chạy cho từng cặp (trong tác vụ nền). Không có
    cặp nào thì chuỗi thành FAILED kèm lý do để giao diện báo đúng như trước."""
    tables = [session.get(DatasetTable, uuid.UUID(table_id)) for table_id in chain.table_ids]
    pairs = chain_pairs(session, [table for table in tables if table is not None])
    if not pairs:
        chain.status = "FAILED"
        chain.error_message = NO_PAIRS
        chain.finished_at = datetime.now(UTC)
        session.commit()
        return False
    for pair in pairs:
        create_run(session, pair.left, pair.right, pair.config, chain.id)
    session.commit()  # giao diện thấy ngay các cặp đang chạy
    return True


def _strong(item: Result) -> bool:
    return item.kind in PAIRED_KINDS and any(
        reason.get("code") in STRONG_REASONS for reason in item.reasons
    )


# Một dòng trong chuỗi: (bảng, vai A/B, số dòng). Hai cặp chỉ tranh nhau một dòng khi bảng đó
# đứng CÙNG VAI ở cả hai cặp (ví dụ sao kê là bên B ở cặp cửa hàng ↔ sao kê và cặp cổng ↔ sao
# kê). Cùng một dòng ở hai vai khác nhau (giao dịch cổng: bên B khi so với đơn, bên A khi so
# với sao kê) là một mắt xích của chuỗi, không phải tranh chấp.
type ChainRow = tuple[uuid.UUID, str, int]


@dataclass
class ChainClaims:
    """Kết quả lượt 1: mỗi dòng đã được cặp nào nhận.

    - strong: cặp đầu tiên ghép chắc chắn dòng đó (theo mã hoặc do người dùng chọn);
    - handled: cặp đầu tiên đã ghép dòng đó (kể cả theo điểm) hoặc đang chờ người dùng chọn;
    - owner: cặp đầu tiên báo dòng đó "chỉ có ở một bên".
    """

    strong: dict[ChainRow, uuid.UUID]
    handled: dict[ChainRow, uuid.UUID]
    owner: dict[ChainRow, uuid.UUID]


def _sides(run: ReconRun, item: Result) -> list[tuple[uuid.UUID, str, list[int]]]:
    return [(run.left_table_id, "A", item.left_refs), (run.right_table_id, "B", item.right_refs)]


def _claims(runs: list[ReconRun], first: dict[uuid.UUID, list[Result]]) -> ChainClaims:
    claims = ChainClaims({}, {}, {})
    for run in runs:  # theo thứ tự chuỗi: cặp đứng trước được nhận trước
        for item in first[run.id]:
            for table_id, role, refs in _sides(run, item):
                for ref in refs:
                    key = (table_id, role, ref)
                    if _strong(item):
                        claims.strong.setdefault(key, run.id)
                    if item.kind in PAIRED_KINDS + ("AMBIGUOUS",):
                        claims.handled.setdefault(key, run.id)
                    elif item.kind in ("ONLY_IN_A", "ONLY_IN_B"):
                        claims.owner.setdefault(key, run.id)
    return claims


def _elsewhere(
    run: ReconRun, results: list[Result], claims: ChainClaims, labels: dict[uuid.UUID, str]
) -> dict[str, dict[int, str]]:
    """Dòng của cặp này đã được cặp khác lo, kèm lý do; ở lượt 2 chúng thành "ngoài phạm vi".

    1. Cặp khác đã ghép chắc chắn, còn cặp này chỉ ghép yếu hoặc không ghép được.
    2. Cặp này không ghép được, nhưng cặp khác đã ghép (hoặc đang chờ người dùng chọn).
    3. Không cặp nào ghép được: chỉ cặp đầu tiên báo "chỉ có ở một bên", các cặp sau không
       báo lặp lại.
    """
    elsewhere: dict[str, dict[int, str]] = {"A": {}, "B": {}}
    for item in results:
        unmatched = item.kind in ("ONLY_IN_A", "ONLY_IN_B")
        for table_id, role, refs in _sides(run, item):
            for ref in refs:
                key = (table_id, role, ref)
                strong, done, first_owner = (
                    claims.strong.get(key), claims.handled.get(key), claims.owner.get(key)
                )
                if strong and strong != run.id and not _strong(item):
                    elsewhere[role][ref] = f"Đã ghép ở cặp {labels[strong]}."
                elif unmatched and done and done != run.id:
                    elsewhere[role][ref] = f"Đã xử lý ở cặp {labels[done]}."
                elif unmatched and first_owner and first_owner != run.id and not strong:
                    elsewhere[role][ref] = f"Chưa ghép được; đã báo ở cặp {labels[first_owner]}."
    return elsewhere


def execute_chain(chain_id: uuid.UUID) -> None:
    """Chạy cả chuỗi (tác vụ nền) theo hai lượt.

    Lượt 1 chạy từng cặp độc lập để biết dòng nào đã được cặp nào nhận (`_claims`). Lượt 2
    chạy lại từng cặp, dòng đã được cặp khác lo thành "ngoài phạm vi" kèm lý do (`_elsewhere`),
    để mỗi khoản tiền chỉ hiện một lần trong danh sách cần xử lý (ví dụ đợt chuyển của cổng
    thanh toán không bị báo "chỉ có ở sao kê" ở cặp đơn hàng ↔ sao kê).
    """
    try:
        with database.SessionFactory() as session:
            chain = session.get(ReconChain, chain_id)
            if chain is None:
                return
            has_runs = session.scalar(select(ReconRun.id).where(ReconRun.chain_id == chain.id))
            if has_runs is None and not _create_chain_runs(session, chain):
                return
            runs = list(session.scalars(select(ReconRun).where(ReconRun.chain_id == chain.id)))
            runs.sort(key=lambda run: (*chain_order(session, run), str(run.id)))
            first = {run.id: compute(session, run)[0] for run in runs}
            labels = {run.id: run_label(session, run) for run in runs}
            claims = _claims(runs, first)

            days: list[date] = []
            for run in runs:
                elsewhere = _elsewhere(run, first[run.id], claims, labels)
                results, left, right, config = compute(session, run, elsewhere)
                period = _period(left, right, config)
                persist(session, run, results, period)
                run.config = {
                    **run.config,
                    "elsewhere": {side: {str(k): v for k, v in refs.items()}
                                  for side, refs in elsewhere.items()},
                }
                days += [day for day in period if day]
            chain.period_start = min(days) if days else None
            chain.period_end = max(days) if days else None
            chain.status = "READY"
            chain.finished_at = datetime.now(UTC)
            session.commit()
    except Exception:
        logger.exception("Lỗi khi đối soát chuỗi %s", chain_id)
        with database.SessionFactory() as session:
            chain = session.get(ReconChain, chain_id)
            if chain is not None:
                chain.status = "FAILED"
                chain.error_message = "Có lỗi khi đối soát cả chuỗi. Hãy thử chạy lại."
                for run in session.scalars(select(ReconRun).where(ReconRun.chain_id == chain_id)):
                    if run.status == "RUNNING":
                        run.status = "FAILED"
                        run.error_message = "Chuỗi đối soát bị lỗi."
                session.commit()


def chain_order(session: Session, run: ReconRun) -> tuple[int, int, str, str]:
    left = session.get(DatasetTable, run.left_table_id)
    right = session.get(DatasetTable, run.right_table_id)
    return (
        SIDE_RANK.get(left.table_kind or "", 3) if left else 3,
        SIDE_RANK.get(right.table_kind or "", 3) if right else 3,
        audit.table_label(left) if left else "",
        audit.table_label(right) if right else "",
    )


def run_label(session: Session, run: ReconRun) -> str:
    left = session.get(DatasetTable, run.left_table_id)
    right = session.get(DatasetTable, run.right_table_id)
    return " ↔ ".join(audit.table_label(table) if table else "?" for table in (left, right))


def trace(
    session: Session, chain: ReconChain, table_id: uuid.UUID, row_ref: int
) -> list[dict[str, Any]]:
    """Đường đi của một dòng qua các cặp của chuỗi: đơn → giao dịch cổng → dòng sao kê.

    Bắt đầu từ dòng đã cho, tìm kết quả chứa nó ở từng cặp; các dòng được ghép cùng nó lại
    được tìm tiếp ở cặp khác (tối đa 4 bước).
    """
    runs = list(session.scalars(select(ReconRun).where(ReconRun.chain_id == chain.id)))
    steps: list[dict[str, Any]] = []
    queue = [(table_id, row_ref)]
    seen = {(table_id, row_ref)}
    visited_runs: set[uuid.UUID] = set()
    while queue and len(steps) < 4:
        current_table, current_ref = queue.pop(0)
        for run in runs:
            if run.id in visited_runs or current_table not in (
                run.left_table_id,
                run.right_table_id,
            ):
                continue
            side_is_left = current_table == run.left_table_id
            for item in result_rows(session, run.id):
                refs = item.left_refs if side_is_left else item.right_refs
                if current_ref not in refs or item.kind == "OUT_OF_SCOPE":
                    continue
                visited_runs.add(run.id)
                steps.append(
                    {
                        "run_id": str(run.id),
                        "pair": run_label(session, run),
                        "kind": item.kind,
                        "result_id": str(item.id),
                        "left_refs": item.left_refs,
                        "right_refs": item.right_refs,
                        "reason": item.reasons[0]["text"] if item.reasons else "",
                    }
                )
                other_table = run.right_table_id if side_is_left else run.left_table_id
                for ref in item.right_refs if side_is_left else item.left_refs:
                    if (other_table, ref) not in seen:
                        seen.add((other_table, ref))
                        queue.append((other_table, ref))
                break
    return steps
