"""Chạy đối soát trên hai bộ sạch mới nhất, lưu kết quả và kiểm chứng (chạy nền).

Nối engine (`reconciliation`), kiểm chứng độc lập (`recon_verification`) với cơ sở dữ liệu:
- chọn cặp bảng và cấu hình gợi ý;
- mỗi lần chạy lưu thành một `ReconRun` mới kèm phiên bản bộ sạch đã dùng;
- trạng thái ngoại lệ và ghi chú của lần trước được mang sang lần sau nếu kết quả giống hệt
  (cùng loại, cùng các dòng hai bên), để chạy lại không làm mất công người dùng đã xử lý.
"""

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import lru_cache
from itertools import combinations
from typing import Any

import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from studio import database
from studio.cleaning import latest_version
from studio.models import CleanVersion, DatasetTable, MatchResult, ReconRun
from studio.recon_verification import verify
from studio.reconciliation import ReconConfig, Side, reconcile, suggest_config, summarize
from studio.sales_fields import FIELDS_BY_KEY

logger = logging.getLogger(__name__)

# Thứ tự bên A → B theo loại bảng: đơn hàng ở bên A, tiền về ở bên B.
SIDE_RANK = {"ORDERS_POS": 0, "ORDERS_PLATFORM": 0, "PAYMENT_GATEWAY": 1, "BANK_STATEMENT": 2}
# Tỷ lệ khớp mã tối thiểu để gợi ý một cặp bảng.
MIN_PAIR_MATCH_RATE = 0.05


def ready_tables(session: Session) -> list[DatasetTable]:
    """Các bảng đã có bộ sạch, dùng được để đối soát."""
    tables = session.scalars(
        select(DatasetTable).where(DatasetTable.status == "READY")
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


@lru_cache(maxsize=64)
def _key_sets(version_id: uuid.UUID, parquet_path: str) -> dict[str, frozenset[str]]:
    """Tập giá trị của từng cột mã trong một phiên bản bộ sạch (phiên bản không bao giờ đổi
    nội dung nên nhớ theo mã phiên bản là an toàn). Chỉ đọc các cột mã, không đọc cả bảng."""
    names = pl.scan_parquet(parquet_path).collect_schema().names()
    keys = [
        name
        for name in names
        if name in FIELDS_BY_KEY and FIELDS_BY_KEY[name].type == "IDENTIFIER"
    ]
    if not keys:
        return {}
    frame = pl.read_parquet(parquet_path, columns=keys)
    return {name: frozenset(frame[name].drop_nulls().to_list()) for name in keys}


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


def preview(left: DatasetTable, right: DatasetTable) -> tuple[ReconConfig, dict[str, Any]]:
    left_version, right_version = latest_version(left), latest_version(right)
    if left_version is None or right_version is None:
        raise ValueError("Bảng chưa có bộ dữ liệu sạch.")
    return suggest_config(clean_frame(left_version), clean_frame(right_version))


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


def result_rows(session: Session, run_id: uuid.UUID) -> list[MatchResult]:
    return list(
        session.scalars(
            select(MatchResult).where(MatchResult.run_id == run_id).order_by(MatchResult.position)
        )
    )


def verify_run(session: Session, run: ReconRun) -> dict[str, Any]:
    """Kiểm chứng lại lần chạy từ kết quả đã lưu trong cơ sở dữ liệu."""
    left_version = session.get(CleanVersion, run.left_version_id)
    right_version = session.get(CleanVersion, run.right_version_id)
    if left_version is None or right_version is None:
        return {"passed": False, "checks": [], "error": "Không còn bộ sạch đã dùng."}
    rows = [
        {
            "kind": item.kind,
            "left_refs": item.left_refs,
            "right_refs": item.right_refs,
            "amount_left": item.amount_left,
            "amount_right": item.amount_right,
        }
        for item in result_rows(session, run.id)
    ]
    return verify(
        clean_frame(left_version), clean_frame(right_version), rows, run.config, run.summary or {}
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
        for item in result_rows(session, previous.id)
        if item.note or item.exception_status in ("EXPLAINED", "RESOLVED")
    }


def execute_run(run_id: uuid.UUID) -> None:
    """Chạy đối soát cho một ReconRun đang ở trạng thái RUNNING (tác vụ nền)."""
    try:
        _execute(run_id)
    except Exception:
        logger.exception("Lỗi khi đối soát lần chạy %s", run_id)
        with database.SessionFactory() as session:
            run = session.get(ReconRun, run_id)
            if run is not None:
                run.status = "FAILED"
                run.error_message = "Có lỗi khi đối soát. Hãy thử chạy lại."
                session.commit()


def _execute(run_id: uuid.UUID) -> None:
    with database.SessionFactory() as session:
        run = session.get(ReconRun, run_id)
        if run is None:
            return
        left_version = session.get(CleanVersion, run.left_version_id)
        right_version = session.get(CleanVersion, run.right_version_id)
        if left_version is None or right_version is None:
            run.status, run.error_message = "FAILED", "Không còn bộ dữ liệu sạch đã chọn."
            session.commit()
            return
        config = ReconConfig.from_json(run.config)
        left, right = clean_frame(left_version), clean_frame(right_version)
        results = reconcile(
            Side(left, unclean_refs(left_version)), Side(right, unclean_refs(right_version)), config
        )
        summary = summarize(results)
        carried = _previous_decisions(session, run)
        now = datetime.now(UTC)
        for position, item in enumerate(results):
            earlier = carried.get(
                result_key(
                    item.kind, item.left_refs, item.right_refs, item.amount_left, item.amount_right
                )
            )
            session.add(
                MatchResult(
                    id=uuid.uuid4(),
                    run_id=run.id,
                    position=position,
                    kind=item.kind,
                    left_refs=item.left_refs,
                    right_refs=item.right_refs,
                    score=item.score,
                    reasons=item.reasons,
                    amount_left=item.amount_left,
                    amount_right=item.amount_right,
                    exception_status=(
                        None
                        if not item.needs_review
                        else earlier.exception_status
                        if earlier and earlier.exception_status
                        else "OPEN"
                    ),
                    note=earlier.note if earlier else None,
                    updated_at=earlier.updated_at if earlier else now,
                )
            )
        run.summary = summary
        run.period_start, run.period_end = _period(left, right, config)
        session.flush()
        # Kiểm chứng đọc lại kết quả vừa ghi, không dùng biến trong bộ nhớ của engine.
        run.verification = verify_run(session, run)
        run.status = "READY"
        run.finished_at = datetime.now(UTC)
        session.commit()
