"""Đo độ chính xác thật của engine đối soát trên bộ dữ liệu kiểm mù (tests/fixtures/blind/).

Bộ này sinh bởi tools/make_blind_fixtures.py, thiết kế độc lập với bộ mẫu và quy tắc engine
không được chỉnh theo nó. Ánh xạ cột được đặt tay (như người dùng xác nhận) để chỉ đo bước
đối soát. Thước đo là các liên kết đơn ↔ dòng sao kê:

- precision: trong các liên kết hệ thống tự ghép, bao nhiêu phần đúng (ghép sai là lỗi nặng nhất);
- recall: trong các liên kết thật, bao nhiêu phần hệ thống tự ghép được;
- liên kết thật nằm trong ca "cần bạn chọn" không tính là sai, được đếm riêng.
"""

import csv
from pathlib import Path
from typing import Any

from conftest import ROOT
from fastapi.testclient import TestClient

from studio import main

client = TestClient(main.app)
BLIND = ROOT / "tests" / "fixtures" / "blind"
PAIRED = ("MATCHED", "MANY_TO_ONE", "ONE_TO_MANY", "AMOUNT_MISMATCH")
ORDER_FIELDS = ["order_id", "order_date", "customer_name", "amount", "payment_method", "status"]
BANK_FIELDS = ["transaction_date", "bank_ref", "description", "debit", "credit"]


def upload(path: Path, fields: list[str]) -> str:
    reply = client.post("/api/datasets", files={"file": (path.name, path.read_bytes())})
    dataset = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
    table_id: str = dataset["tables"][0]["id"]
    for position, field in enumerate(fields):
        answer = client.put(
            f"/api/tables/{table_id}/mapping/columns/{position}", json={"field_key": field}
        )
        assert answer.status_code == 200, answer.text
    return table_id


def all_results(run_id: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for group in ("todo", "explained", "resolved", "matched", "pending", "out_of_scope"):
        offset = 0
        while True:
            page = client.get(
                f"/api/recon/runs/{run_id}/results",
                params={"group": group, "offset": offset, "limit": 200},
            ).json()
            found += page["items"]
            offset += 200
            if offset >= page["total"]:
                break
    return found


def test_blind_orders_against_bank_statement() -> None:
    orders = upload(BLIND / "don-hang-kenh-b.csv", ORDER_FIELDS)
    bank = upload(BLIND / "sao-ke-kenh-b.csv", BANK_FIELDS)
    cleaning = client.get(f"/api/tables/{orders}/cleaning").json()
    assert cleaning["open_counts"]["ASK"] == 0, [i["message"] for i in cleaning["issues"]][:5]
    run = client.post(
        "/api/recon/runs", json={"left_table_id": orders, "right_table_id": bank}
    ).json()
    run = client.get(f"/api/recon/runs/{run['id']}").json()
    assert run["status"] == "READY" and run["verification"]["passed"], run

    with (BLIND / "dap-an.csv").open(encoding="utf-8") as handle:
        truth = {(int(row["order_row"]), int(row["bank_row"])) for row in csv.DictReader(handle)}
    linked: set[tuple[int, int]] = set()
    held: set[tuple[int, int]] = set()  # liên kết trong ca "cần bạn chọn"
    items = all_results(run["id"])
    kind_of = {
        (side, row["row_ref"]): item["kind"]
        for item in items
        for side, rows in (("A", item["left"]), ("B", item["right"]))
        for row in rows
    }
    texts = {row["row_ref"]: row.get("description") for item in items for row in item["right"]}
    for item in items:
        pairs = {
            (left["row_ref"], right["row_ref"])
            for left in item["left"]
            if not left.get("carried")
            for right in item["right"]
        }
        if item["kind"] in PAIRED:
            linked |= pairs
        elif item["kind"] == "AMBIGUOUS":
            held |= pairs & truth

    correct = linked & truth
    precision = len(correct) / max(len(linked), 1)
    recall = len(correct) / max(len(truth), 1)
    print(
        f"\nKiểm mù: {len(truth)} liên kết thật, hệ thống tự ghép {len(linked)}, đúng "
        f"{len(correct)} → precision {precision:.2%}, recall {recall:.2%}; "
        f"{len(held)} liên kết thật chờ người dùng chọn; sai: {sorted(linked - truth)[:10]}"
    )
    # Liên kết bị sót nằm ở ngoại lệ để người dùng ghép tay: dòng đúng phải nằm trong 3 gợi ý
    # đầu của ô "Ghép tay" (xếp theo độ gần số tiền, rồi ngày).
    result_of = {
        row["row_ref"]: item["id"]
        for item in items
        if item["kind"] in ("ONLY_IN_A", "PENDING_SETTLEMENT")
        for row in item["left"]
    }
    ranks = []
    for order_row, bank_row in sorted(truth - linked - held):
        offered = client.get(
            f"/api/recon/results/{result_of[order_row]}/match-candidates"
        ).json()["candidates"]
        rank = next(
            (index + 1 for index, item in enumerate(offered) if item["row"]["row_ref"] == bank_row),
            None,
        )
        ranks.append(rank)
        print(
            f"  sót: đơn dòng {order_row} ({kind_of.get(('A', order_row))}) ↔ sao kê dòng "
            f"{bank_row} ({kind_of.get(('B', bank_row))}): {texts.get(bank_row)}; "
            f"vị trí trong gợi ý ghép tay: {rank}"
        )
    # Ghép sai là lỗi nặng nhất của hệ thống đối soát: gần như không được có.
    assert precision >= 0.99
    # Mức đo được lần đầu (96,65%), giữ làm mốc chống thụt lùi; không chỉnh engine theo bộ này.
    assert recall >= 0.95
    assert all(rank is not None and rank <= 3 for rank in ranks), ranks
