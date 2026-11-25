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
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from studio import recon_api, recon_service
from studio.models import MatchResult, ReconChain, ReconRun

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


def _status_group(item: MatchResult) -> str:
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


def _result_amount(item: MatchResult) -> Decimal:
    """Số tiền liên quan của một kết quả (để xếp ngoại lệ lớn nhất): lệch tiền lấy phần lệch."""
    if item.kind == "AMOUNT_MISMATCH":
        return abs(_money(item.amount_left) - _money(item.amount_right))
    return max(_money(item.amount_left), _money(item.amount_right))


def _results(session: Session, run: ReconRun) -> list[MatchResult]:
    return list(
        session.scalars(
            select(MatchResult).where(MatchResult.run_id == run.id).order_by(MatchResult.position)
        )
    )


def pair_report(session: Session, run: ReconRun) -> dict[str, Any]:
    """Số liệu của một cặp bảng, kèm từng kết quả đã đọc ngày, mã (dùng cho biểu đồ, tệp xuất)."""
    items = _results(session, run)
    views = {view["id"]: view for view in recon_api._result_views(session, run, items)}
    open_by_kind: dict[str, dict[str, Any]] = {}
    for item in items:
        if item.exception_status == "OPEN":
            slot = open_by_kind.setdefault(item.kind, {"count": 0, "amount": ZERO})
            slot["count"] += 1
            slot["amount"] += _result_amount(item)
    view = recon_api.run_view(session, run)
    return {
        "run_id": str(run.id),
        "label": recon_service.run_label(session, run),
        "left_label": view["left"]["label"] if view["left"] else "?",
        "right_label": view["right"]["label"] if view["right"] else "?",
        "verified": bool((run.verification or {}).get("passed")),
        **_pair_numbers(run, items),
        "open_by_kind": open_by_kind,
        "counts": (run.summary or {}).get("counts", {}),
        "_items": [(item, views[str(item.id)]) for item in items],
    }


def _exception_row(
    pair: dict[str, Any], item: MatchResult, view: dict[str, Any], period_end: date | None
) -> dict[str, Any]:
    day = _result_day(view)
    keys = [str(row["key"]) for row in view["left"] + view["right"] if row.get("key")]
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
        "reason": "; ".join(reason["text"] for reason in item.reasons),
        "note": item.note,
        "left_rows": [row["row_ref"] for row in view["left"]],
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
    pairs = [_pair_numbers(run, _results(session, run)) for run in runs if run.status == "READY"]
    return {
        "chain_id": str(chain.id),
        "label": chain.label,
        "period_start": chain.period_start.isoformat() if chain.period_start else None,
        "period_end": chain.period_end.isoformat() if chain.period_end else None,
        "verified": chain_verified(chain, runs),
        "kpis": _headline(pairs) if pairs else None,
    }


def _pair_numbers(run: ReconRun, items: list[MatchResult]) -> dict[str, Any]:
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


def build_report(session: Session, chain: ReconChain) -> dict[str, Any]:
    """Báo cáo đầy đủ của một kỳ: số chính, từng cặp, biểu đồ, ngoại lệ (kèm dữ liệu xuất)."""
    runs = chain_runs(session, chain)
    pairs = [pair_report(session, run) for run in runs if run.status == "READY"]
    period_end = chain.period_end
    exceptions: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    by_day: dict[str, dict[str, int]] = {}
    by_kind: dict[str, dict[str, Any]] = {}
    aging: dict[str, dict[str, Any]] = {
        label: {"count": 0, "amount": ZERO} for label, _, _ in AGE_BUCKETS
    }
    for pair in pairs:
        for item, view in pair["_items"]:
            row = _exception_row(pair, item, view, period_end)
            all_rows.append(row)
            group = _status_group(item)
            slot = by_kind.setdefault(item.kind, {"count": 0, "amount": ZERO})
            slot["count"] += 1
            slot["amount"] += _result_amount(item)
            if row["date"] and group != "out_of_scope":
                day = by_day.setdefault(row["date"], {})
                day[group] = day.get(group, 0) + 1
            if item.exception_status == "OPEN":
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
        "pairs": [{k: v for k, v in pair.items() if k != "_items"} for pair in pairs],
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
