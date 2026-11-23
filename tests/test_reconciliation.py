"""Kiểm đối soát: đúng đáp án, không phụ thuộc thứ tự dòng, kiểm chứng bắt sửa tay,
xử lý ngoại lệ và nhật ký kiểm toán cho mọi thao tác thay đổi."""

import csv
import random
import uuid
from decimal import Decimal
from typing import Any

import polars as pl
import pytest
from conftest import FIXTURES
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from studio import database, main, recon_ai
from studio.gemini_client import AiReply
from studio.models import AuditLog, MatchResult
from studio.reading import ROW_REF
from studio.reconciliation import ReconConfig, Side, reconcile

client = TestClient(main.app)
POS = "don-hang-cua-hang.csv"
GATEWAY = "giao-dich-cong-thanh-toan.csv"
RELATION = "cua-hang↔cong-thanh-toan"


def upload(name: str) -> dict[str, Any]:
    reply = client.post("/api/datasets", files={"file": (name, (FIXTURES / name).read_bytes())})
    body: dict[str, Any] = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
    return body


def start_pair() -> tuple[str, str]:
    pos = upload(POS)["tables"][0]["id"]
    gateway = upload(GATEWAY)["tables"][0]["id"]
    return pos, gateway


def run(left: str, right: str, **overrides: Any) -> dict[str, Any]:
    reply = client.post(
        "/api/recon/runs", json={"left_table_id": left, "right_table_id": right, **overrides}
    )
    assert reply.status_code == 202, reply.text
    body: dict[str, Any] = client.get(f"/api/recon/runs/{reply.json()['id']}").json()
    assert body["status"] == "READY", body
    return body


def all_results(run_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for group in ("todo", "explained", "resolved", "matched", "out_of_scope"):
        offset = 0
        while True:
            page = client.get(
                f"/api/recon/runs/{run_id}/results",
                params={"group": group, "offset": offset, "limit": 200},
            ).json()
            items += page["items"]
            offset += 200
            if offset >= page["total"]:
                break
    # Một kết quả có thể vừa "khớp" vừa nằm ở nhóm ngoại lệ (đơn hủy có tiền về): bỏ trùng.
    return list({item["id"]: item for item in items}.values())


def answer_cases() -> set[tuple[str, int | None, int | None]]:
    with (FIXTURES / "dap-an.csv").open(encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["relation"] == RELATION]
    cases = set()
    for row in rows:
        left = int(row["left_row"]) if row["left_row"] else None
        right = int(row["right_row"]) if row["right_row"] else None
        if row["kind"] == "DUPLICATE":
            left = None  # kết quả DUPLICATE chỉ giữ dòng thừa; dòng kia đã nằm trong cặp khớp
        cases.add((row["kind"], left, right))
    return cases


def predicted_cases(results: list[dict[str, Any]]) -> set[tuple[str, int | None, int | None]]:
    return {
        (
            item["kind"],
            item["left"][0]["row_ref"] if item["left"] else None,
            item["right"][0]["row_ref"] if item["right"] else None,
        )
        for item in results
        if item["kind"] not in ("OUT_OF_SCOPE", "NEEDS_CLEANING")
    }


# ---------------------------------------------------------------- độ chính xác


def test_precision_and_recall_on_the_keyed_sample_reach_99_percent() -> None:
    pos, gateway = start_pair()
    suggested = client.get("/api/recon/tables").json()["suggested"]
    assert suggested == {"left_table_id": pos, "right_table_id": gateway}
    body = run(pos, gateway)
    assert body["verification"]["passed"], body["verification"]
    results = all_results(body["id"])
    expected, predicted = answer_cases(), predicted_cases(results)
    correct = expected & predicted
    precision, recall = len(correct) / len(predicted), len(correct) / len(expected)
    print(f"\nĐơn cửa hàng ↔ cổng: precision {precision:.2%}, recall {recall:.2%}")
    assert precision >= 0.99 and recall >= 0.99, (expected - predicted, predicted - expected)
    # Đơn tiền mặt, chuyển khoản tự để ngoài phạm vi, không thành ngoại lệ.
    excluded = body["config"]["excluded"]["LEFT"]["payment_method"]
    assert sorted(excluded) == ["Chuyển khoản", "Tiền mặt"]
    assert body["exceptions"]["OPEN"] == 4  # lệch tiền, trùng, thiếu, thừa


def test_shuffled_rows_give_the_same_result() -> None:
    pos, gateway = start_pair()
    first = run(pos, gateway)
    config = ReconConfig.from_json(first["config"])
    from studio.cleaning import latest_version
    from studio.models import DatasetTable

    frames = []
    with database.SessionFactory() as session:
        for table_id in (pos, gateway):
            table = session.get(DatasetTable, uuid.UUID(table_id))
            version = latest_version(table) if table else None
            assert version is not None
            frames.append(pl.read_parquet(version.parquet_path))
    baseline = reconcile(Side(frames[0]), Side(frames[1]), config)
    for seed in (1, 2, 3):
        shuffled = [frame.sample(fraction=1.0, shuffle=True, seed=seed) for frame in frames]
        assert shuffled[0][ROW_REF].to_list() != frames[0][ROW_REF].to_list()
        assert reconcile(Side(shuffled[0]), Side(shuffled[1]), config) == baseline


def test_tied_candidates_are_not_auto_picked() -> None:
    """Hai giao dịch cùng số tiền, cùng ngày, không có mã: không tự chọn bên nào."""
    from datetime import date

    left = pl.DataFrame(
        {
            ROW_REF: [2],
            "order_id": ["HD1"],
            "amount": [Decimal("100")],
            "order_date": [date(2026, 10, 1)],
        }
    )
    right = pl.DataFrame(
        {
            ROW_REF: [2, 3],
            "order_id": [None, None],
            "amount": [Decimal("100"), Decimal("100")],
            "transaction_date": [date(2026, 10, 1), date(2026, 10, 1)],
        },
        schema={
            ROW_REF: pl.Int64,
            "order_id": pl.String,
            "amount": pl.Decimal(20, 2),
            "transaction_date": pl.Date,
        },
    )
    config = ReconConfig(
        "order_id", "order_id", "amount", "amount", "order_date", "transaction_date"
    )
    results = reconcile(Side(left), Side(right), config)
    assert [item.kind for item in results] == ["ONLY_IN_A", "ONLY_IN_B", "ONLY_IN_B"]
    assert any(reason["code"] == "TIED" for reason in results[0].reasons)


def test_unclean_rows_are_reported_not_matched() -> None:
    left = pl.DataFrame({ROW_REF: [2, 3], "order_id": ["A", "B"], "amount": [1, 2]}).with_columns(
        pl.col("amount").cast(pl.Decimal(20, 2))
    )
    right = left.clone()
    config = ReconConfig("order_id", "order_id", "amount", "amount")
    kinds = [item.kind for item in reconcile(Side(left, {3}), Side(right), config)]
    assert kinds == ["MATCHED", "ONLY_IN_B", "NEEDS_CLEANING"]


def test_user_can_bring_out_of_scope_rows_back() -> None:
    pos, gateway = start_pair()
    body = run(pos, gateway, excluded={})
    assert body["summary"]["counts"]["OUT_OF_SCOPE"] == 0
    # Không để ngoài phạm vi thì đơn tiền mặt, chuyển khoản thành "chỉ có ở A".
    assert body["summary"]["counts"]["ONLY_IN_A"] > 100


# ---------------------------------------------------------------- kiểm chứng


@pytest.mark.parametrize("tamper", ["kind", "amount", "delete"])
def test_verification_catches_results_edited_by_hand(tamper: str) -> None:
    pos, gateway = start_pair()
    body = run(pos, gateway)
    run_id = uuid.UUID(body["id"])
    with database.SessionFactory() as session:
        target = session.scalars(
            select(MatchResult).where(
                MatchResult.run_id == run_id, MatchResult.kind == "AMOUNT_MISMATCH"
            )
        ).one()
        if tamper == "kind":
            target.kind = "MATCHED"  # che lệch tiền thành khớp
        elif tamper == "amount":
            target.amount_right = target.amount_left  # sửa số tiền cho "khớp"
        else:
            session.delete(target)  # xóa một kết quả khó chịu
        session.commit()
    verified = client.post(f"/api/recon/runs/{run_id}/verify").json()["verification"]
    assert verified["passed"] is False
    assert [check["code"] for check in verified["checks"] if not check["passed"]]


# ---------------------------------------------------------------- ngoại lệ


def test_exception_status_follows_user_actions_and_survives_rerun() -> None:
    pos, gateway = start_pair()
    body = run(pos, gateway)
    todo = client.get(f"/api/recon/runs/{body['id']}/results", params={"group": "todo"}).json()
    by_kind = {item["kind"]: item for item in todo["items"]}

    noted = client.put(
        f"/api/recon/results/{by_kind['AMOUNT_MISMATCH']['id']}/note",
        json={"note": "Khách được giảm giá tại quầy"},
    ).json()
    assert noted["exception_status"] == "EXPLAINED"
    cleared = client.put(
        f"/api/recon/results/{by_kind['AMOUNT_MISMATCH']['id']}/note", json={"note": " "}
    ).json()
    assert cleared["exception_status"] == "OPEN" and cleared["note"] is None

    view = client.post(
        f"/api/recon/runs/{body['id']}/actions", json={"action": "RESOLVE", "kind": "DUPLICATE"}
    ).json()
    assert view["exceptions"]["RESOLVED"] == 1 and view["exceptions"]["OPEN"] == 3
    client.put(
        f"/api/recon/results/{by_kind['ONLY_IN_B']['id']}/note", json={"note": "Đơn bán online"}
    )

    # Chạy lại trên cùng dữ liệu: các ngoại lệ đã xử lý, đã ghi chú giữ nguyên trạng thái.
    again = run(pos, gateway)
    assert again["exceptions"] == {"OPEN": 2, "EXPLAINED": 1, "RESOLVED": 1}

    reopened = client.post(
        f"/api/recon/runs/{again['id']}/actions",
        json={
            "action": "REOPEN",
            "kind": None,
            "result_ids": [
                item["id"]
                for item in client.get(
                    f"/api/recon/runs/{again['id']}/results", params={"group": "resolved"}
                ).json()["items"]
            ],
        },
    ).json()
    assert reopened["exceptions"]["RESOLVED"] == 0


# ---------------------------------------------------------------- AI chỉ khi bấm


def test_explain_without_key_reports_clearly() -> None:
    pos, gateway = start_pair()
    reply = client.post(
        "/api/recon/preview/explain", json={"left_table_id": pos, "right_table_id": gateway}
    )
    assert reply.status_code == 503
    assert reply.json()["detail"]["code"] == "AI_NOT_CONFIGURED"


def test_explain_sends_no_personal_data(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []

    def fake_ai(**kwargs: Any) -> AiReply:
        seen.append(kwargs["payload"])
        return AiReply(data={"text": "Cổng thu thiếu 20.000đ."}, input_tokens=1, output_tokens=1)

    monkeypatch.setattr(recon_ai, "generate_json", fake_ai)
    pos, gateway = start_pair()
    body = run(pos, gateway)
    item = next(
        entry
        for entry in client.get(f"/api/recon/runs/{body['id']}/results").json()["items"]
        if entry["kind"] == "AMOUNT_MISMATCH"
    )
    reply = client.post(f"/api/recon/results/{item['id']}/explain").json()
    assert reply["text"] == "Cổng thu thiếu 20.000đ."
    sent = str(seen[0])
    assert item["left"][0].get("customer_name") and item["left"][0]["customer_name"] not in sent


# ---------------------------------------------------------------- nhật ký kiểm toán


def audit_count() -> int:
    with database.SessionFactory() as session:
        return session.scalar(select(func.count()).select_from(AuditLog)) or 0


def test_every_user_change_writes_an_audit_entry() -> None:
    def changes(call: Any, action: str) -> Any:
        before = audit_count()
        reply = call()
        assert reply.status_code < 300, reply.text
        assert audit_count() == before + 1, action
        latest = client.get("/api/audit", params={"limit": 1}).json()["items"][0]
        assert latest["action"] == action and latest["summary"]
        return reply

    pos_upload = changes(
        lambda: client.post("/api/datasets", files={"file": (POS, (FIXTURES / POS).read_bytes())}),
        "DATASET_UPLOADED",
    )
    dataset_id = pos_upload.json()["dataset"]["id"]
    table = client.get(f"/api/datasets/{dataset_id}").json()["tables"][0]["id"]
    gateway = upload(GATEWAY)["tables"][0]["id"]
    base = f"/api/tables/{table}"
    changes(
        lambda: client.put(f"{base}/mapping/columns/5", json={"field_key": None}), "MAPPING_CHANGED"
    )
    changes(
        lambda: client.put(f"{base}/mapping/columns/5", json={"field_key": "payment_method"}),
        "MAPPING_CHANGED",
    )
    changes(lambda: client.post(f"{base}/mapping/confirm"), "MAPPING_CONFIRMED")
    changes(
        lambda: client.post(
            f"{base}/cleaning/cells",
            json={"row_ref": 226, "field_key": "amount", "value": "500000"},
        ),
        "CELL_FIXED",
    )
    changes(
        lambda: client.post(
            f"{base}/cleaning/rows", json={"row_refs": [224], "decision": "EXCLUDE"}
        ),
        "ROWS_EXCLUDE",
    )
    changes(lambda: client.post(f"{base}/cleaning/duplicates/accept"), "DUPLICATES_EXCLUDED")
    changes(
        lambda: client.put(
            f"{base}/cleaning/date-order", json={"field_key": "order_date", "order": "DMY"}
        ),
        "DATE_ORDER_CHANGED",
    )
    recon = changes(
        lambda: client.post(
            "/api/recon/runs", json={"left_table_id": table, "right_table_id": gateway}
        ),
        "RECON_RUN",
    )
    run_id = recon.json()["id"]
    first = client.get(f"/api/recon/runs/{run_id}/results").json()["items"][0]
    changes(
        lambda: client.put(f"/api/recon/results/{first['id']}/note", json={"note": "Đã gọi"}),
        "EXCEPTION_NOTE",
    )
    changes(
        lambda: client.post(
            f"/api/recon/runs/{run_id}/actions",
            json={"action": "RESOLVE", "result_ids": [first["id"]]},
        ),
        "EXCEPTION_RESOLVE",
    )
    changes(
        lambda: client.post(
            f"/api/recon/runs/{run_id}/actions",
            json={"action": "REOPEN", "result_ids": [first["id"]]},
        ),
        "EXCEPTION_REOPEN",
    )
    changes(lambda: client.post(f"{base}/mapping/suggest"), "MAPPING_RESUGGESTED")
    changes(lambda: client.put(f"{base}/header-row", json={"header_row": 1}), "HEADER_ROW_CHANGED")
    changes(lambda: client.post(f"/api/datasets/{dataset_id}/read"), "DATASET_REREAD")
    changes(lambda: client.delete(f"/api/datasets/{dataset_id}"), "DATASET_DELETED")


def test_audit_entry_is_kept_when_the_object_is_deleted() -> None:
    dataset = upload(GATEWAY)
    client.delete(f"/api/datasets/{dataset['id']}")
    with database.SessionFactory() as session:
        kept = session.scalars(select(AuditLog).where(AuditLog.object_id == dataset["id"])).all()
    assert {item.action for item in kept} == {"DATASET_UPLOADED", "DATASET_DELETED"}


# ---------------------------------------------------------------- hiệu năng


def test_100k_rows_reconcile_within_reasonable_time() -> None:
    import time

    rng = random.Random(7)
    size = 100_000
    refs = list(range(2, size + 2))
    amounts = [Decimal(rng.randint(90, 4500) * 1000) for _ in refs]
    left = pl.DataFrame(
        {ROW_REF: refs, "order_id": [f"HD{ref:07d}" for ref in refs], "amount": amounts},
        schema={ROW_REF: pl.Int64, "order_id": pl.String, "amount": pl.Decimal(20, 2)},
    )
    right = left.sample(fraction=0.9, seed=3)
    config = ReconConfig("order_id", "order_id", "amount", "amount")
    started = time.perf_counter()
    results = reconcile(Side(left), Side(right), config)
    elapsed = time.perf_counter() - started
    print(f"\nĐối soát 100.000 ↔ 90.000 dòng mất {elapsed:.2f} giây")
    assert sum(item.kind == "MATCHED" for item in results) == right.height
    assert elapsed < 30
