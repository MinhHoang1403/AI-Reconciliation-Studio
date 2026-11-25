"""Tính báo cáo của một kỳ đối soát từ kết quả đã lưu (Giai đoạn 7).

Module chỉ ĐỌC kết quả engine đã lưu (`recon_runs.summary`, `match_results`) và dòng gốc của
đúng phiên bản sạch đã dùng; không chạy lại engine, không tự ghép hay đổi loại kết quả. Vì vậy
mọi con số trong báo cáo, tệp xuất và lời nhận xét AI đều truy ngược được về engine.

Định nghĩa (docs/PLAN.md GĐ7, DECISIONS 2026-11-25):
- Dòng/tiền "cần đối chiếu" của một cặp = các dòng bên A trừ dòng ngoài phạm vi.
- "Đã khớp" = kết quả loại MATCHED, MANY_TO_ONE, ONE_TO_MANY (khớp đúng hoặc ghép nhóm đúng
  tổng); lệch tiền, chờ tiền về, chỉ có ở một bên… không tính là khớp.
- Tỷ lệ khớp của cả kỳ = tổng phần đã khớp / tổng phần cần đối chiếu của mọi cặp (bình quân
  có trọng số theo số dòng hoặc số tiền), giống cách tính tỷ lệ tự khớp của phần mềm đối soát.
- Tổng lệch = tổng |A − B| của các kết quả lệch tiền; thiếu tiền về = tổng tiền các dòng chỉ
  có ở A; tiền về chưa rõ nguồn = tổng tiền các dòng chỉ có ở B.
- Tuổi ngoại lệ tính từ ngày giao dịch tới NGÀY CUỐI KỲ (không phải hôm nay) để báo cáo của một
  kỳ luôn cho cùng kết quả dù mở lúc nào; theo cách chia nhóm tuổi của bảng tuổi nợ kế toán.
"""

import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio import recon_api, recon_service
from studio.models import CleanVersion, MatchResult, ReconChain, ReconRun
from studio.reconciliation import ReconConfig

MATCHED_KINDS = ("MATCHED", "MANY_TO_ONE", "ONE_TO_MANY")
# Nhóm tuổi ngoại lệ còn mở (số ngày từ ngày giao dịch tới ngày cuối kỳ).
AGE_BUCKETS = (("0–3 ngày", 0, 3), ("4–7 ngày", 4, 7), ("Trên 7 ngày", 8, None))
TOP_EXCEPTIONS = 5
ZERO = Decimal("0")


def _money(value: Any) -> Decimal:
    return Decimal(str(value)) if value not in (None, "") else ZERO


def _rate(part: Decimal | int, whole: Decimal | int) -> float | None:
    """Tỷ lệ phần trăm làm tròn 1 chữ số; không có gì cần đối chiếu thì không có tỷ lệ."""
    return round(float(part) * 100 / float(whole), 1) if whole else None


def _status_group(item: Any) -> str:
    """Nhóm cho biểu đồ theo ngày: đã khớp, chờ tiền về, cần xử lý, đã xử lý, ngoài phạm vi."""
    if item.kind == "OUT_OF_SCOPE":
        return "out_of_scope"
    if item.kind == "PENDING_SETTLEMENT":
        return "pending"
    if item.exception_status == "OPEN":
        return "todo"
    if item.exception_status in ("EXPLAINED", "RESOLVED"):
        return "handled"
    return "matched"


def _result_day(view: dict[str, Any]) -> date | None:
    """Ngày của một kết quả: ngày dòng bên A đầu tiên, không có thì ngày dòng bên B."""
    for row in view["left"] + view["right"]:
        if row.get("date"):
            return date.fromisoformat(str(row["date"])[:10])
    return None


def _result_amount(item: Any) -> Decimal:
    """Số tiền liên quan của một kết quả (để xếp ngoại lệ lớn nhất): lệch tiền lấy phần lệch."""
    if item.kind == "AMOUNT_MISMATCH":
        return abs(_money(item.amount_left) - _money(item.amount_right))
    return max(_money(item.amount_left), _money(item.amount_right))


# Đọc kết quả theo CỘT, không nạp cả đối tượng ORM: cột lý do (JSON lớn) chỉ đọc cho các ca
# cần hiện lý do. Đo ở 10.000 đơn (24.092 kết quả): nạp cả đối tượng mất 1,6 giây, chỉ các cột
# đếm mất 0,15 giây; ở 100.000 đơn chênh lệch này thành hàng chục giây mỗi lần mở trang.
COUNT_COLUMNS = (
    MatchResult.kind,
    MatchResult.exception_status,
    MatchResult.amount_left,
    MatchResult.amount_right,
)
LIGHT_COLUMNS = (
    MatchResult.id,
    *COUNT_COLUMNS,
    MatchResult.left_refs,
    MatchResult.right_refs,
    MatchResult.carried_left,
)
TEXT_BATCH = 500  # số kết quả mỗi lần đọc lý do (giới hạn kích thước câu IN của SQL)


def _rows(
    session: Session, run: ReconRun, columns: tuple[Any, ...], in_scope_only: bool = False
) -> list[Any]:
    query = select(*columns).where(MatchResult.run_id == run.id)
    if in_scope_only:
        query = query.where(MatchResult.kind != "OUT_OF_SCOPE")
    return list(session.execute(query.order_by(MatchResult.position)).all())


def _texts(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[list[Any], Any]]:
    """Lý do và ghi chú của đúng các kết quả cần hiện."""
    found: dict[uuid.UUID, tuple[list[Any], Any]] = {}
    for start in range(0, len(ids), TEXT_BATCH):
        query = select(MatchResult.id, MatchResult.reasons, MatchResult.note).where(
            MatchResult.id.in_(ids[start : start + TEXT_BATCH])
        )
        for result_id, reasons, note in session.execute(query):
            found[result_id] = (reasons, note)
    return found


def _views(session: Session, run: ReconRun, rows: list[Any]) -> list[dict[str, Any]]:
    """Mã, ngày, số tiền của các dòng hai bên mỗi kết quả, đọc đúng phiên bản sạch đã dùng (như
    danh sách kết quả của trang Đối soát, nhưng không dựng phần lý do, điểm)."""
    config = ReconConfig.from_json(run.config)
    left = recon_api._details(
        session.get(CleanVersion, run.left_version_id),
        {ref for row in rows for ref in row.left_refs},
        config.key_left,
        config.date_left,
        config.amount_left,
        (),
    )
    right = recon_api._details(
        session.get(CleanVersion, run.right_version_id),
        {ref for row in rows for ref in row.right_refs},
        config.key_right,
        config.date_right,
        config.amount_right,
        (),
    )
    carried = recon_api._carried_details(session, cast(Any, rows), config, ())
    return [
        {
            "left": [left.get(ref, {"row_ref": ref}) for ref in row.left_refs]
            + [
                carried.get((item["table_id"], item["row_ref"]), {"row_ref": item["row_ref"]})
                | {"carried": True}
                for item in row.carried_left or []
            ],
            "right": [right.get(ref, {"row_ref": ref}) for ref in row.right_refs],
        }
        for row in rows
    ]


def pair_report(session: Session, run: ReconRun, full: bool = False) -> dict[str, Any]:
    """Số liệu của một cặp bảng, kèm từng kết quả đã đọc ngày, mã (dùng cho biểu đồ, tệp xuất).

    `full`: đọc lý do, ghi chú của MỌI kết quả (tệp xuất); không thì chỉ của ca đang mở, và
    kết quả ngoài phạm vi (khoảng 60% ở bộ mẫu) chỉ được đếm, không đọc dòng gốc: trang Báo
    cáo không vẽ chúng theo ngày và chúng không bao giờ là ca cần xử lý."""
    if full:
        # Tệp xuất cần lý do của mọi kết quả: đọc chung một truy vấn (đọc theo lô từng 500 mã
        # thì ở 100.000 đơn thành gần 500 truy vấn).
        rows = _rows(session, run, (*LIGHT_COLUMNS, MatchResult.reasons, MatchResult.note))
        counted = rows
        texts = {row.id: (row.reasons, row.note) for row in rows}
    else:
        counted = _rows(session, run, COUNT_COLUMNS)
        rows = _rows(session, run, LIGHT_COLUMNS, in_scope_only=True)
        texts = _texts(session, [row.id for row in rows if row.exception_status == "OPEN"])
    views = _views(session, run, rows)
    open_by_kind: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.exception_status == "OPEN":
            slot = open_by_kind.setdefault(row.kind, {"count": 0, "amount": ZERO})
            slot["count"] += 1
            slot["amount"] += _result_amount(row)
    view = recon_api.run_view(session, run)
    return {
        "run_id": str(run.id),
        "label": recon_service.run_label(session, run),
        "left_label": view["left"]["label"] if view["left"] else "?",
        "right_label": view["right"]["label"] if view["right"] else "?",
        "verified": bool((run.verification or {}).get("passed")),
        # Các phép kiểm của từng cặp để giao diện vẽ con dấu gộp như trang Đối soát.
        "verification": run.verification,
        **_pair_numbers(run, counted),
        "open_by_kind": open_by_kind,
        "counts": (run.summary or {}).get("counts", {}),
        "_counted": counted,
        "_items": [
            (row, views[index], texts.get(row.id, ([], None))) for index, row in enumerate(rows)
        ],
    }


def _exception_row(
    pair: dict[str, Any],
    item: Any,
    view: dict[str, Any],
    text: tuple[list[Any], Any],
    period_end: date | None,
) -> dict[str, Any]:
    day = _result_day(view)
    keys = [str(row["key"]) for row in view["left"] + view["right"] if row.get("key")]
    reasons, note = text
    return {
        "result_id": str(item.id),
        "pair": pair["label"],
        "kind": item.kind,
        "kind_label": recon_api.KIND_LABELS.get(item.kind, item.kind),
        "status": item.exception_status,
        "codes": list(dict.fromkeys(keys)),
        "date": day.isoformat() if day else None,
        "age_days": max((period_end - day).days, 0) if day and period_end else None,
        "amount_left": None if item.amount_left is None else str(item.amount_left),
        "amount_right": None if item.amount_right is None else str(item.amount_right),
        "amount": str(_result_amount(item)),
        "reason": "; ".join(reason["text"] for reason in reasons),
        "note": note,
        # Dòng mang sang từ kỳ trước thuộc bảng của kỳ trước: tách riêng để số dòng không bị
        # hiểu nhầm là dòng của bảng kỳ này.
        "left_rows": [row["row_ref"] for row in view["left"] if not row.get("carried")],
        "carried_rows": [row["row_ref"] for row in view["left"] if row.get("carried")],
        "right_rows": [row["row_ref"] for row in view["right"]],
    }


def _headline(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Các số chính của cả kỳ: cộng các cặp (tỷ lệ là bình quân có trọng số)."""
    total = {
        key: sum((pair[key] for pair in pairs), ZERO)
        for key in (
            "amount_in_scope",
            "amount_matched",
            "mismatch_total",
            "missing_amount",
            "unknown_amount",
            "pending_amount",
        )
    }
    counts = {
        key: sum(pair[key] for pair in pairs)
        for key in ("rows_in_scope", "rows_matched", "pending_count", "open_count", "handled_count")
    }
    return {
        **counts,
        **total,
        "match_rate_rows": _rate(counts["rows_matched"], counts["rows_in_scope"]),
        "match_rate_amount": _rate(total["amount_matched"], total["amount_in_scope"]),
    }


def chain_runs(session: Session, chain: ReconChain) -> list[ReconRun]:
    runs = list(session.scalars(select(ReconRun).where(ReconRun.chain_id == chain.id)))
    return sorted(runs, key=lambda run: recon_service.chain_order(session, run))


def chain_verified(chain: ReconChain, runs: list[ReconRun]) -> bool:
    """Cùng điều kiện với con dấu kiểm chứng trên trang Đối soát."""
    return (
        chain.status == "READY"
        and bool(runs)
        and all((run.verification or {}).get("passed") for run in runs)
    )


def headline_only(session: Session, chain: ReconChain) -> dict[str, Any]:
    """Số chính của một kỳ, chỉ đọc tóm tắt và trạng thái ngoại lệ (nhẹ, dùng cho so sánh các
    kỳ, Dashboard và Assistant)."""
    runs = chain_runs(session, chain)
    # Chỉ đọc các cột để đếm, cộng (Dashboard, so sánh các kỳ, Assistant mở nhanh).
    pairs = [
        _pair_numbers(run, _rows(session, run, COUNT_COLUMNS))
        for run in runs
        if run.status == "READY"
    ]
    return {
        "chain_id": str(chain.id),
        "label": chain.label,
        "period_start": chain.period_start.isoformat() if chain.period_start else None,
        "period_end": chain.period_end.isoformat() if chain.period_end else None,
        "verified": chain_verified(chain, runs),
        "kpis": _headline(pairs) if pairs else None,
    }


def _pair_numbers(run: ReconRun, items: list[Any]) -> dict[str, Any]:
    """Số liệu của một cặp: phần đếm và tiền lấy từ tóm tắt engine lưu lúc chạy; trạng thái
    ngoại lệ đọc trực tiếp vì người dùng đổi được sau khi chạy."""
    summary = run.summary or {}
    rows = summary.get("rows", {})
    amounts = summary.get("amounts", {})
    in_scope = [kind for kind in rows if kind != "OUT_OF_SCOPE"]
    rows_in_scope = sum(rows[kind]["A"] for kind in in_scope)
    rows_matched = sum(rows.get(kind, {}).get("A", 0) for kind in MATCHED_KINDS)
    amount_in_scope = sum((_money(amounts[kind]["A"]) for kind in in_scope), ZERO)
    amount_matched = sum((_money(amounts.get(kind, {}).get("A")) for kind in MATCHED_KINDS), ZERO)
    return {
        "rows_in_scope": rows_in_scope,
        "rows_matched": rows_matched,
        "amount_in_scope": amount_in_scope,
        "amount_matched": amount_matched,
        "match_rate_rows": _rate(rows_matched, rows_in_scope),
        "match_rate_amount": _rate(amount_matched, amount_in_scope),
        "mismatch_total": sum(
            (
                abs(_money(i.amount_left) - _money(i.amount_right))
                for i in items
                if i.kind == "AMOUNT_MISMATCH"
            ),
            ZERO,
        ),
        "missing_amount": _money(amounts.get("ONLY_IN_A", {}).get("A")),
        "unknown_amount": _money(amounts.get("ONLY_IN_B", {}).get("B")),
        "pending_count": rows.get("PENDING_SETTLEMENT", {}).get("A", 0),
        "pending_amount": _money(amounts.get("PENDING_SETTLEMENT", {}).get("A")),
        "open_count": sum(item.exception_status == "OPEN" for item in items),
        "handled_count": sum(i.exception_status in ("EXPLAINED", "RESOLVED") for i in items),
    }


def build_report(session: Session, chain: ReconChain, full: bool = False) -> dict[str, Any]:
    """Báo cáo của một kỳ: số chính, từng cặp, biểu đồ, ngoại lệ đang mở.

    `full=True` (tệp xuất) có thêm "results": mọi kết quả kèm lý do và dòng gốc; trang Báo cáo
    không cần phần này nên không đọc lý do của hàng chục nghìn kết quả đã khớp."""
    runs = chain_runs(session, chain)
    pairs = [pair_report(session, run, full) for run in runs if run.status == "READY"]
    period_end = chain.period_end
    exceptions: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    by_day: dict[str, dict[str, int]] = {}
    by_kind: dict[str, dict[str, Any]] = {}
    aging: dict[str, dict[str, Any]] = {
        label: {"count": 0, "amount": ZERO} for label, _, _ in AGE_BUCKETS
    }
    for pair in pairs:
        for counted in pair["_counted"]:
            slot = by_kind.setdefault(counted.kind, {"count": 0, "amount": ZERO})
            slot["count"] += 1
            slot["amount"] += _result_amount(counted)
        for item, view, text in pair["_items"]:
            group = _status_group(item)
            result_day = _result_day(view)
            if result_day and group != "out_of_scope":
                day = by_day.setdefault(result_day.isoformat(), {})
                day[group] = day.get(group, 0) + 1
            row = (
                _exception_row(pair, item, view, text, period_end)
                if full or item.exception_status == "OPEN"
                else None
            )
            if full and row is not None:
                all_rows.append(row)
            if row is not None and item.exception_status == "OPEN":
                exceptions.append(row)
                age = row["age_days"]
                for label, low, high in AGE_BUCKETS:
                    if age is not None and age >= low and (high is None or age <= high):
                        aging[label]["count"] += 1
                        aging[label]["amount"] += _result_amount(item)
    exceptions.sort(key=lambda row: (-Decimal(row["amount"]), row["pair"], row["date"] or ""))
    return {
        "chain_id": str(chain.id),
        "label": chain.label,
        "period_start": chain.period_start.isoformat() if chain.period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "created_at": chain.created_at.isoformat() if chain.created_at else None,
        "verified": chain_verified(chain, runs),
        "kpis": _headline(pairs),
        "pairs": [{k: v for k, v in pair.items() if not k.startswith("_")} for pair in pairs],
        "by_kind": [
            {"kind": kind, "label": recon_api.KIND_LABELS.get(kind, kind), **value}
            for kind, value in by_kind.items()
        ],
        "by_day": [{"date": day, **groups} for day, groups in sorted(by_day.items())],
        "aging": [{"label": label, **value} for label, value in aging.items()],
        "top_exceptions": exceptions[:TOP_EXCEPTIONS],
        "exceptions": exceptions,
        "results": all_rows,
    }


def comparison(session: Session) -> list[dict[str, Any]]:
    """Số chính của mọi kỳ đã đối soát (lần chạy chuỗi mới nhất mỗi kỳ), theo thứ tự ngày."""
    rows = []
    for period in recon_api.recon_periods(session):
        if not period["chain_id"]:
            continue
        chain = session.get(ReconChain, uuid.UUID(period["chain_id"]))
        if chain is not None and chain.status == "READY":
            rows.append(headline_only(session, chain))
    return sorted(rows, key=lambda row: row["period_start"] or "")


def fingerprint(report: dict[str, Any]) -> str:
    """Dấu vân tay số liệu của báo cáo: đổi khi kỳ được đối soát lại hoặc ngoại lệ đổi trạng
    thái, để biết lời nhận xét AI đã viết có còn đúng với số liệu hiện tại không."""
    payload = {"kpis": report["kpis"], "pairs": report["pairs"]}
    text = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def to_json(value: Any) -> Any:
    """Decimal → chuỗi để trả qua API (giữ chính xác, không đổi sang số thực)."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: to_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_json(item) for item in value]
    return value
