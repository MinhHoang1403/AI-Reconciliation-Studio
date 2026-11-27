"""Kiểm ghép tay và gỡ ghép: engine tôn trọng lựa chọn, API lưu lựa chọn, chạy lại, ghi nhật ký."""

from datetime import date
from decimal import Decimal
from typing import Any

import polars as pl
from conftest import FIXTURES
from fastapi.testclient import TestClient

from studio import main
from studio.reading import ROW_REF
from studio.reconciliation import ReconConfig, Side, reconcile

client = TestClient(main.app)
SCHEMA: dict[str, Any] = {
    ROW_REF: pl.Int64,
    "order_id": pl.String,
    "amount": pl.Decimal(20, 2),
    "day": pl.Date,
}


def frame(refs: list[int], keys: list[str | None], amounts: list[int]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            ROW_REF: refs,
            "order_id": keys,
            "amount": [Decimal(a) for a in amounts],
            "day": [date(2026, 10, 1)] * len(refs),
        },
        schema=SCHEMA,
    )


def kinds(results: list[Any]) -> dict[str, list[tuple[list[int], list[int]]]]:
    found: dict[str, list[tuple[list[int], list[int]]]] = {}
    for item in results:
        found.setdefault(item.kind, []).append((item.left_refs, item.right_refs))
    return found


# ---------------------------------------------------------------- engine


def test_unmatched_pair_is_never_paired_again_by_any_round() -> None:
    left = frame([2, 3], ["HD1", None], [100, 500])
    right = frame([2, 3], ["HD1", None], [100, 500])
    config = ReconConfig("order_id", "order_id", "amount", "amount", "day", "day")
    assert kinds(reconcile(Side(left), Side(right), config))["MATCHED"] == [([2], [2]), ([3], [3])]

    # Gỡ cả hai cặp: cặp cùng mã không được ghép theo mã, cặp không mã không được ghép theo điểm.
    config.forbidden = [{"left": [2], "right": [2]}, {"left": [3], "right": [3]}]
    found = kinds(reconcile(Side(left), Side(right), config))
    assert "MATCHED" not in found
    assert sorted(found["ONLY_IN_A"]) == [([2], []), ([3], [])]
    assert sorted(found["ONLY_IN_B"]) == [([], [2]), ([], [3])]


def test_unmatched_group_is_not_rebuilt_by_the_sum_round() -> None:
    left = frame([2, 3], [None, None], [300, 700])
    right = frame([2], [None], [1000])
    config = ReconConfig(None, None, "amount", "amount", "day", "day")
    assert kinds(reconcile(Side(left), Side(right), config))["MANY_TO_ONE"] == [([2, 3], [2])]
    config.forbidden = [{"left": [2, 3], "right": [2]}]
    assert "MANY_TO_ONE" not in kinds(reconcile(Side(left), Side(right), config))


def test_manual_match_overrides_rounds_and_keeps_mismatch_visible() -> None:
    left = frame([2], ["HD1"], [100])
    right = frame([2, 3], ["HD9", None], [90, 100])
    config = ReconConfig("order_id", "order_id", "amount", "amount", "day", "day")
    # Người dùng biết dòng B2 (mã gõ sai, lệch 10đ) mới là tiền của đơn này.
    config.forced = [{"left": [2], "right": [2]}]
    found = kinds(reconcile(Side(left), Side(right), config))
    assert found["AMOUNT_MISMATCH"] == [([2], [2])]  # ghép theo người dùng, lệch tiền vẫn báo
    assert found["ONLY_IN_B"] == [([], [3])]


# ---------------------------------------------------------------- API


def upload(name: str) -> str:
    reply = client.post("/api/datasets", files={"file": (name, (FIXTURES / name).read_bytes())})
    dataset = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
    table_id: str = dataset["tables"][0]["id"]
    return table_id


def results(run_id: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for group in ("todo", "explained", "resolved", "matched", "pending", "out_of_scope"):
        page = client.get(
            f"/api/recon/runs/{run_id}/results", params={"group": group, "limit": 200}
        ).json()
        found += page["items"]
    return found


def latest_audit(action: str) -> dict[str, Any] | None:
    items = client.get("/api/audit", params={"limit": 10}).json()["items"]
    return next((entry for entry in items if entry["action"] == action), None)


def test_manual_match_then_unmatch_through_the_api() -> None:
    pos, gateway = upload("don-hang-cua-hang.csv"), upload("giao-dich-cong-thanh-toan.csv")
    run = client.post(
        "/api/recon/runs", json={"left_table_id": pos, "right_table_id": gateway}
    ).json()
    items = results(run["id"])
    only_a = next(item for item in items if item["kind"] == "ONLY_IN_A")
    only_b = next(item for item in items if item["kind"] == "ONLY_IN_B")
    a_ref, b_ref = only_a["left"][0]["row_ref"], only_b["right"][0]["row_ref"]

    # Gợi ý ứng viên: dòng chưa ghép ở bên B, gần số tiền nhất trước.
    offered = client.get(f"/api/recon/results/{only_a['id']}/match-candidates").json()
    assert offered["side"] == "B"
    gaps = [Decimal(item["amount_gap"]) for item in offered["candidates"]]
    assert gaps == sorted(gaps) and any(
        item["row"]["row_ref"] == b_ref for item in offered["candidates"]
    )

    # Dòng đã ghép thì không ghép tay được.
    matched = next(item for item in items if item["kind"] == "MATCHED")
    refused = client.post(
        f"/api/recon/runs/{run['id']}/match",
        json={"left_refs": [matched["left"][0]["row_ref"]], "right_refs": [b_ref]},
    )
    assert refused.status_code == 422

    reply = client.post(
        f"/api/recon/runs/{run['id']}/match", json={"left_refs": [a_ref], "right_refs": [b_ref]}
    )
    assert reply.status_code == 202, reply.text
    second = reply.json()["run_id"]
    assert client.get(f"/api/recon/runs/{second}").json()["verification"]["passed"]
    paired = next(
        item for item in results(second)
        if [row["row_ref"] for row in item["left"]] == [a_ref]
        and [row["row_ref"] for row in item["right"]] == [b_ref]
    )
    assert paired["kind"] in ("MATCHED", "AMOUNT_MISMATCH")
    assert any(reason["code"] == "USER" for reason in paired["reasons"])
    # Nhật ký ghi mã đơn và tên bảng (không "A43 ↔ B74") để người đọc khỏi tra bên A, B.
    logged = latest_audit("MANUAL_MATCH")
    assert logged is not None
    a_code, b_code = only_a["left"][0]["key"], only_b["right"][0].get("key")
    assert f"{a_code} (don-hang-cua-hang)" in logged["summary"]
    assert "(giao-dich-cong-thanh-toan)" in logged["summary"]
    assert f"A{a_ref}" not in logged["summary"]
    assert (b_code or f"dòng {b_ref}") in logged["summary"]

    # Gỡ chính cặp vừa ghép tay: hai dòng trở về chưa ghép và không tự ghép lại.
    third = client.post(f"/api/recon/results/{paired['id']}/unmatch").json()["run_id"]
    after = results(third)
    assert any(
        item["kind"] == "ONLY_IN_A" and item["left"][0]["row_ref"] == a_ref for item in after
    )
    assert any(
        item["kind"] == "ONLY_IN_B" and item["right"][0]["row_ref"] == b_ref for item in after
    )
    unmatched = latest_audit("RESULT_UNMATCHED")
    assert unmatched is not None and f"{a_code} (don-hang-cua-hang) ↔" in unmatched["summary"]

    # Gỡ một cặp khớp theo mã: cả hai dòng thành "chỉ có ở một bên", kiểm chứng vẫn đạt.
    target = next(item for item in after if item["kind"] == "MATCHED")
    fourth = client.post(f"/api/recon/results/{target['id']}/unmatch").json()["run_id"]
    assert client.get(f"/api/recon/runs/{fourth}").json()["verification"]["passed"]
    left_ref = target["left"][0]["row_ref"]
    assert any(
        item["kind"] == "ONLY_IN_A" and item["left"][0]["row_ref"] == left_ref
        for item in results(fourth)
    )
    # Kết quả chưa ghép thì không có gì để gỡ.
    lonely = next(item for item in results(fourth) if item["kind"] == "ONLY_IN_A")
    assert client.post(f"/api/recon/results/{lonely['id']}/unmatch").status_code == 422


def test_unmatch_inside_a_chain_reruns_the_whole_chain() -> None:
    for name in (
        "don-hang-cua-hang.csv",
        "giao-dich-cong-thanh-toan.csv",
        "don-hang-san-tmdt.xlsx",
        "sao-ke-ngan-hang.xlsx",
    ):
        client.post("/api/datasets", files={"file": (name, (FIXTURES / name).read_bytes())})
    period = client.get("/api/recon/periods").json()[0]
    chain = client.post(
        "/api/recon/chains", json={"table_ids": [table["id"] for table in period["tables"]]}
    ).json()
    run = client.get(f"/api/recon/chains/{chain['id']}").json()["runs"][0]
    target = next(item for item in results(run["id"]) if item["kind"] == "MATCHED")
    reply = client.post(f"/api/recon/results/{target['id']}/unmatch").json()
    assert reply["chain_id"] and reply["chain_id"] != chain["id"]
    rerun = client.get(f"/api/recon/chains/{reply['chain_id']}").json()
    assert rerun["status"] == "READY" and rerun["verified"]
    # Trang Đối soát chỉ tải lần chạy hai bảng đứng riêng; lần chạy của chuỗi không lẫn vào.
    assert client.get("/api/recon/runs", params={"standalone": True}).json() == []
    latest = client.get("/api/recon/runs", params={"limit": 1}).json()[0]
    # Số đếm theo nhóm (một câu truy vấn) cộng lại đúng tổng số kết quả của lần chạy.
    assert sum(latest["group_counts"].values()) == latest["summary"]["total_results"]
