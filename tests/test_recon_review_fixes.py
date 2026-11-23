"""Kiểm hồi quy cho các lỗi tìm thấy khi rà code Giai đoạn 4 (mỗi bài bắt đúng một lỗi)."""

import time
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from conftest import FIXTURES
from fastapi.testclient import TestClient
from sqlalchemy import select

from studio import database, main, recon_ai
from studio.gemini_client import AiReply
from studio.models import AuditLog, CleanVersion
from studio.reading import ROW_REF
from studio.recon_service import result_key
from studio.reconciliation import ReconConfig, Side, reconcile
from studio.value_parsers import money_vi

client = TestClient(main.app)
POS = "don-hang-cua-hang.csv"
GATEWAY = "giao-dich-cong-thanh-toan.csv"
SCHEMA: dict[str, Any] = {
    ROW_REF: pl.Int64,
    "order_id": pl.String,
    "amount": pl.Decimal(20, 2),
    "day": pl.Date,
}


def frame(refs: list[int], keys: list[str | None], amounts: list[int], days: list[date]) -> Any:
    return pl.DataFrame(
        {ROW_REF: refs, "order_id": keys, "amount": [Decimal(a) for a in amounts], "day": days},
        schema=SCHEMA,
    )


def upload(name: str) -> str:
    reply = client.post("/api/datasets", files={"file": (name, (FIXTURES / name).read_bytes())})
    dataset = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
    table_id: str = dataset["tables"][0]["id"]
    return table_id


def start_run(left: str, right: str, **extra: Any) -> Any:
    return client.post(
        "/api/recon/runs", json={"left_table_id": left, "right_table_id": right, **extra}
    )


def todo(run_id: str) -> dict[str, dict[str, Any]]:
    items = client.get(f"/api/recon/runs/{run_id}/results", params={"group": "todo"}).json()
    return {item["kind"]: item for item in items["items"]}


# ---------------------------------------------------------------- lỗi 1, 2: không có khóa chung


def test_no_common_key_scales_without_a_dense_matrix() -> None:
    """20.000 dòng mỗi bên, không có mã: trước đây dựng ma trận 20.000 × 20.000 (3,2 GB)."""
    size = 20_000
    refs = list(range(2, size + 2))
    day = date(2026, 10, 1)
    left = frame(refs, [None] * size, [1000 + i for i in range(size)], [day] * size)
    right = left.sample(fraction=1.0, shuffle=True, seed=5)
    config = ReconConfig(None, None, "amount", "amount", "day", "day")
    started = time.perf_counter()
    results = reconcile(Side(left), Side(right), config)
    assert time.perf_counter() - started < 30
    assert sum(item.kind == "MATCHED" for item in results) == size


def test_many_identical_candidates_are_not_auto_matched() -> None:
    """Nhiều dòng cùng số tiền, cùng ngày, không mã: không tự ghép, nêu lý do."""
    size = 120
    refs = list(range(2, size + 2))
    rows = frame(refs, [None] * size, [500_000] * size, [date(2026, 10, 1)] * size)
    config = ReconConfig(None, None, "amount", "amount", "day", "day")
    results = reconcile(Side(rows), Side(rows.clone()), config)
    assert all(item.kind in ("ONLY_IN_A", "ONLY_IN_B") for item in results)
    assert all(any(reason["code"] == "TIED" for reason in item.reasons) for item in results)


# ---------------------------------------------------------------- lỗi 3: mã lặp rất nhiều lần


def test_heavily_repeated_key_pairs_quickly() -> None:
    size = 3_000
    refs = list(range(2, size + 2))
    days = [date(2026, 10, 1) + timedelta(days=i % 5) for i in range(size)]
    left = frame(refs, ["0"] * size, [1000 + i for i in range(size)], days)
    right = left.sample(fraction=1.0, shuffle=True, seed=9)
    config = ReconConfig("order_id", "order_id", "amount", "amount", "day", "day")
    started = time.perf_counter()
    results = reconcile(Side(left), Side(right), config)
    assert time.perf_counter() - started < 10
    assert sum(item.kind == "MATCHED" for item in results) == size


def test_small_repeated_key_keeps_best_pair_first() -> None:
    days = [date(2026, 10, 1)] * 2
    left = frame([2, 3], ["K", "K"], [100, 200], days)
    right = frame([2, 3], ["K", "K"], [200, 100], days)
    config = ReconConfig("order_id", "order_id", "amount", "amount", "day", "day")
    pairs = {
        (item.left_refs[0], item.right_refs[0])
        for item in reconcile(Side(left), Side(right), config)
        if item.kind == "MATCHED"
    }
    assert pairs == {(2, 3), (3, 2)}  # ghép theo đúng số tiền, không theo thứ tự dòng


# ---------------------------------------------------------------- lỗi 6: đơn hủy ở bên B


def test_unmatched_cancelled_orders_are_out_of_scope_on_either_side() -> None:
    days = [date(2026, 10, 1)]
    payments = frame([2], ["P1"], [100], days)
    orders = frame([5], ["HD9"], [700], days).with_columns(pl.lit(True).alias("is_cancelled"))
    config = ReconConfig("order_id", "order_id", "amount", "amount", "day", "day")
    for left, right in ((orders, payments), (payments, orders)):
        kinds = {item.kind for item in reconcile(Side(left), Side(right), config)
                 if 5 in item.left_refs + item.right_refs}
        assert kinds == {"OUT_OF_SCOPE"}


# ---------------------------------------------------------------- lỗi 4: mang trạng thái sang


def test_resolved_exception_reopens_when_the_amounts_change() -> None:
    assert result_key("AMOUNT_MISMATCH", [24], [5], Decimal("3410000"), Decimal("3390000")) != (
        result_key("AMOUNT_MISMATCH", [24], [5], Decimal("3410000"), Decimal("3400000"))
    )
    pos, gateway = upload(POS), upload(GATEWAY)
    first = start_run(pos, gateway).json()
    mismatch = todo(first["id"])["AMOUNT_MISMATCH"]
    client.post(
        f"/api/recon/runs/{first['id']}/actions",
        json={"action": "RESOLVE", "result_ids": [mismatch["id"]]},
    )
    # Sửa số tiền bên cổng: vẫn lệch nhưng lệch khác đi → ca này phải được xem lại.
    row = mismatch["right"][0]["row_ref"]
    fixed = client.post(
        f"/api/tables/{gateway}/cleaning/cells",
        json={"row_ref": row, "field_key": "amount", "value": "3400000"},
    )
    assert fixed.status_code == 202, fixed.text
    again = start_run(pos, gateway).json()
    reopened = todo(again["id"])["AMOUNT_MISMATCH"]
    assert reopened["exception_status"] == "OPEN"
    assert reopened["amount_right"] == "3400000.00"


# ---------------------------------------------------------------- lỗi 5: gợi ý cặp bảng


def test_pair_suggestion_skips_an_unreadable_table() -> None:
    pos, gateway = upload(POS), upload(GATEWAY)
    platform = upload("don-hang-san-tmdt.xlsx")
    with database.SessionFactory() as session:
        version = session.scalars(
            select(CleanVersion)
            .where(CleanVersion.table_id == uuid.UUID(platform))
            .order_by(CleanVersion.version.desc())
        ).first()
        assert version is not None
        Path(version.parquet_path).unlink()  # tệp bộ sạch bị mất ngoài ý muốn
    reply = client.get("/api/recon/tables")
    assert reply.status_code == 200
    assert reply.json()["suggested"] == {"left_table_id": pos, "right_table_id": gateway}


# ---------------------------------------------------------------- lỗi 7: sai số


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-1", "1.5", "abc", "1,5"])
def test_invalid_tolerance_is_rejected_with_422(bad: str) -> None:
    pos, gateway = upload(POS), upload(GATEWAY)
    reply = start_run(pos, gateway, tolerance=bad)
    assert reply.status_code == 422
    assert reply.json()["detail"]["code"] == "INVALID_TOLERANCE"


def test_tolerance_accepts_thousand_separators() -> None:
    pos, gateway = upload(POS), upload(GATEWAY)
    run = start_run(pos, gateway, tolerance="20.000").json()
    assert run["config"]["tolerance"] == "20000"
    # Lệch đúng 20.000đ nằm trong sai số nên không còn là ngoại lệ lệch tiền.
    assert "AMOUNT_MISMATCH" not in todo(run["id"])


# ---------------------------------------------------------------- lỗi 8: nhãn nhật ký


def test_audit_label_names_the_result_that_actually_changed() -> None:
    pos, gateway = upload(POS), upload(GATEWAY)
    run = start_run(pos, gateway).json()
    open_items = todo(run["id"])
    duplicate, mismatch = open_items["DUPLICATE"], open_items["AMOUNT_MISMATCH"]
    client.post(
        f"/api/recon/runs/{run['id']}/actions",
        json={"action": "RESOLVE", "result_ids": [duplicate["id"]]},
    )
    # Gửi kèm ca đã xử lý: chỉ ca lệch tiền thật sự đổi trạng thái.
    client.post(
        f"/api/recon/runs/{run['id']}/actions",
        json={"action": "RESOLVE", "result_ids": [duplicate["id"], mismatch["id"]]},
    )
    with database.SessionFactory() as session:
        latest = session.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(1)
        ).one()
    assert "Lệch tiền" in latest.summary and "Trùng" not in latest.summary


# ---------------------------------------------------------------- lỗi 9: giải thích một ca


def test_explain_reads_only_the_rows_of_that_result(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []

    def fake_ai(**kwargs: Any) -> AiReply:
        seen.append(kwargs["payload"])
        return AiReply(data={"text": "Khớp."}, input_tokens=1, output_tokens=1)

    monkeypatch.setattr(recon_ai, "generate_json", fake_ai)
    pos, gateway = upload(POS), upload(GATEWAY)
    run = start_run(pos, gateway).json()
    page = client.get(
        f"/api/recon/runs/{run['id']}/results", params={"group": "matched", "offset": 60}
    ).json()
    target = page["items"][-1]
    assert client.post(f"/api/recon/results/{target['id']}/explain").status_code == 200
    rows = seen[0]["rows"]
    assert rows["A"][0]["row_ref"] == target["left"][0]["row_ref"]
    assert rows["B"][0]["amount"] == target["right"][0]["amount"]


# ---------------------------------------------------------------- lỗi 10: định dạng tiền chung


def test_money_formatting_is_shared() -> None:
    assert money_vi(Decimal("2195000")) == "2.195.000"
    assert money_vi(Decimal("-1250000.5"), "đ") == "-1.250.000,50đ"
    assert money_vi(None) == "trống"
