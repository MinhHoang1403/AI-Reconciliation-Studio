"""Kiểm Giai đoạn 5: tách mã từ nội dung, khớp nhóm, ca mơ hồ, chuỗi ba bên, chờ tiền về.

So với đáp án trong tests/fixtures/sales/dap-an.csv (kỳ 1 và kỳ 2, sinh bởi
tools/make_sales_fixtures.py). Mọi bài đều không gọi AI.
"""

import csv
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import polars as pl
import pytest
from conftest import FIXTURES
from fastapi.testclient import TestClient
from sqlalchemy import select

from studio import database, main
from studio.models import MatchResult
from studio.reading import ROW_REF
from studio.recon_verification import verify
from studio.reconciliation import (
    ReconConfig,
    Row,
    Side,
    _subsets,
    add_business_days,
    description_name,
    extract_keys,
    learn_code_pattern,
    reconcile,
)

client = TestClient(main.app)
PERIOD1 = [
    "don-hang-cua-hang.csv",
    "giao-dich-cong-thanh-toan.csv",
    "don-hang-san-tmdt.xlsx",
    "sao-ke-ngan-hang.xlsx",
]
PERIOD2 = [
    "don-hang-cua-hang-ky-2.csv",
    "giao-dich-cong-thanh-toan-ky-2.csv",
    "don-hang-san-tmdt-ky-2.xlsx",
    "sao-ke-ngan-hang-ky-2.xlsx",
]
# Quan hệ trong đáp án ↔ (tệp bên A, tệp bên B, sheet bên B).
RELATIONS = {
    "cua-hang↔cong-thanh-toan": ("don-hang-cua-hang", "giao-dich-cong-thanh-toan", None),
    "cua-hang↔sao-ke": ("don-hang-cua-hang", "sao-ke-ngan-hang", "TK chinh"),
    "cong-thanh-toan↔sao-ke": ("giao-dich-cong-thanh-toan", "sao-ke-ngan-hang", "TK chinh"),
    "san-tmdt↔sao-ke": ("don-hang-san-tmdt › Đơn hàng", "sao-ke-ngan-hang", "TK san"),
}
SKIPPED_KINDS = ("OUT_OF_SCOPE", "NEEDS_CLEANING")


# ---------------------------------------------------------------- tiện ích


def upload_all(names: list[str]) -> dict[tuple[str, str | None], dict[str, Any]]:
    """Tải các tệp, trả về {(tên tệp không đuôi, sheet): bảng}."""
    tables = {}
    for name in names:
        reply = client.post("/api/datasets", files={"file": (name, (FIXTURES / name).read_bytes())})
        dataset = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
        for table in dataset["tables"]:
            if table["status"] == "READY":
                tables[(dataset["name"], table["sheet_name"])] = table
    return tables


def run_period(label_index: int) -> dict[str, Any]:
    periods = client.get("/api/recon/periods").json()
    period = periods[label_index]
    reply = client.post(
        "/api/recon/chains", json={"table_ids": [table["id"] for table in period["tables"]]}
    )
    assert reply.status_code == 202, reply.text
    chain: dict[str, Any] = client.get(f"/api/recon/chains/{reply.json()['id']}").json()
    assert chain["status"] == "READY", chain
    return chain


def all_results(run_id: str) -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for group in ("todo", "explained", "resolved", "matched", "pending", "out_of_scope"):
        offset = 0
        while True:
            page = client.get(
                f"/api/recon/runs/{run_id}/results",
                params={"group": group, "offset": offset, "limit": 200},
            ).json()
            items |= {item["id"]: item for item in page["items"]}
            offset += 200
            if offset >= page["total"]:
                break
    return list(items.values())


def answers(relation: str) -> set[tuple[str, str | None, int | None, int | None]]:
    """(loại, tệp bên A, dòng A, dòng B) của một quan hệ; dòng A có tệp để phân biệt kỳ."""
    with (FIXTURES / "dap-an.csv").open(encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["relation"] == relation]
    # Kết quả DUPLICATE chỉ giữ dòng thừa; dòng kia đã nằm trong cặp khớp.
    return {
        (
            row["kind"],
            row["left_file"].rsplit(".", 1)[0]
            if row["left_row"] and row["kind"] != "DUPLICATE"
            else None,
            int(row["left_row"]) if row["left_row"] and row["kind"] != "DUPLICATE" else None,
            int(row["right_row"]) if row["right_row"] else None,
        )
        for row in rows
        if row["kind"] not in SKIPPED_KINDS
    }


def predicted(
    run: dict[str, Any], names: dict[str, str]
) -> set[tuple[str, str | None, int | None, int | None]]:
    """Kết quả của một lần chạy, cùng dạng với đáp án (mỗi dòng A một bộ)."""
    found: set[tuple[str, str | None, int | None, int | None]] = set()
    left_name = run["left"]["label"]
    for item in all_results(run["id"]):
        if item["kind"] in SKIPPED_KINDS:
            continue
        right = item["right"][0]["row_ref"] if item["right"] else None
        lefts = item["left"] or [None]
        for row in lefts:
            if row is None:
                found.add((item["kind"], None, None, right))
                continue
            # Nhãn bảng → tên tệp không đuôi; dòng chờ từ kỳ trước mang nhãn bảng kỳ trước.
            label = row.get("table_label") if row.get("carried") else left_name
            name = names.get(label or "", label)
            found.add((item["kind"], name, row["row_ref"], right))
    return found


def run_for(chain: dict[str, Any], left: str, right: str, sheet: str | None) -> dict[str, Any]:
    right_label = f"{right} › {sheet}" if sheet else right
    return next(
        run
        for run in chain["runs"]
        if run["left"]["label"] == left and run["right"]["label"] == right_label
    )


def assert_matches_answers(chain: dict[str, Any], suffix: str) -> None:
    # Nhãn bảng → tên tệp không đuôi (để so dòng chờ từ kỳ trước với đáp án).
    names = {
        "don-hang-cua-hang": "don-hang-cua-hang",
        "giao-dich-cong-thanh-toan": "giao-dich-cong-thanh-toan",
        "don-hang-san-tmdt › Đơn hàng": "don-hang-san-tmdt",
        "don-hang-cua-hang-ky-2": "don-hang-cua-hang-ky-2",
        "giao-dich-cong-thanh-toan-ky-2": "giao-dich-cong-thanh-toan-ky-2",
        "don-hang-san-tmdt-ky-2 › Đơn hàng": "don-hang-san-tmdt-ky-2",
    }
    for relation, (left, right, sheet) in RELATIONS.items():
        left_name = left.replace(" ›", "-ky-2 ›") if suffix and " ›" in left else (
            left + ("-ky-2" if suffix else "")
        )
        right_name = right + ("-ky-2" if suffix else "")
        run = run_for(chain, left_name, right_name, sheet)
        assert run["verification"]["passed"], (relation, run["verification"])
        expected = answers(relation + suffix)
        got = predicted(run, names)
        correct = expected & got
        precision = len(correct) / max(len(got), 1)
        recall = len(correct) / max(len(expected), 1)
        print(f"\n{relation}{suffix}: precision {precision:.2%}, recall {recall:.2%}")
        assert recall >= 0.99, (relation, sorted(expected - got, key=str)[:10])
        assert precision >= 0.99, (relation, sorted(got - expected, key=str)[:10])


# ---------------------------------------------------------------- theo đáp án


def test_period1_chain_matches_the_answer_key() -> None:
    upload_all(PERIOD1)
    periods = client.get("/api/recon/periods").json()
    assert len(periods) == 1 and len(periods[0]["tables"]) == 5  # 3 bảng + 2 sheet sao kê
    chain = run_period(0)
    assert chain["verified"]
    pairs = [(run["left"]["label"], run["right"]["label"]) for run in chain["runs"]]
    assert ("don-hang-cua-hang", "giao-dich-cong-thanh-toan") in pairs
    assert ("giao-dich-cong-thanh-toan", "sao-ke-ngan-hang › TK chinh") in pairs
    assert ("don-hang-san-tmdt › Đơn hàng", "sao-ke-ngan-hang › TK san") in pairs
    assert len(pairs) == 4  # không ghép sàn với tài khoản chính, cửa hàng với tài khoản sàn
    assert_matches_answers(chain, "")

    # Tiền của cổng thanh toán trong sao kê không bị báo "chỉ có ở B" ở cặp cửa hàng ↔ sao kê.
    pos_bank = run_for(chain, "don-hang-cua-hang", "sao-ke-ngan-hang", "TK chinh")
    only_b = [item for item in all_results(pos_bank["id"]) if item["kind"] == "ONLY_IN_B"]
    assert len(only_b) == 2  # tiền nộp lạ + tiền của đơn còn lỗi trùng mã
    gw_bank = run_for(chain, "giao-dich-cong-thanh-toan", "sao-ke-ngan-hang", "TK chinh")
    assert gw_bank["summary"]["counts"]["ONLY_IN_B"] == 0
    assert pos_bank["config"]["extract"]["pattern"]  # tự học mẫu mã, không cần AI


def test_period2_picks_up_pending_rows_from_period1() -> None:
    upload_all(PERIOD1)
    first = run_period(0)
    pending = sum(run["group_counts"]["pending"] for run in first["runs"])
    assert pending == 28  # 3 đơn cửa hàng + 5 giao dịch cổng + 20 đơn sàn
    upload_all(PERIOD2)
    periods = client.get("/api/recon/periods").json()
    assert [period["label"][:8] for period in periods] == ["Kỳ 01/10", "Kỳ 15/10"]
    second = run_period(1)
    assert second["verified"]
    assert sum(run["carried_count"] for run in second["runs"]) == 28
    assert second["pending"] == 0
    assert_matches_answers(second, " (kỳ 2)")


def test_choosing_an_ambiguous_candidate_is_remembered() -> None:
    upload_all(PERIOD1)
    chain = run_period(0)
    run = run_for(chain, "don-hang-cua-hang", "sao-ke-ngan-hang", "TK chinh")
    ambiguous = next(item for item in all_results(run["id"]) if item["kind"] == "AMBIGUOUS")
    assert sorted(row["row_ref"] for row in ambiguous["left"]) == [16, 20]
    bad = client.post(
        f"/api/recon/runs/{run['id']}/choose",
        json={"result_id": ambiguous["id"], "left_refs": [2], "right_refs": [7]},
    )
    assert bad.status_code == 422
    reply = client.post(
        f"/api/recon/runs/{run['id']}/choose",
        json={"result_id": ambiguous["id"], "left_refs": [16], "right_refs": [7]},
    )
    assert reply.status_code == 202, reply.text
    again = client.get(f"/api/recon/chains/{reply.json()['chain_id']}").json()
    rerun = run_for(again, "don-hang-cua-hang", "sao-ke-ngan-hang", "TK chinh")
    items = all_results(rerun["id"])
    chosen = next(item for item in items if item["right"] and item["right"][0]["row_ref"] == 7)
    assert chosen["kind"] == "MATCHED" and [row["row_ref"] for row in chosen["left"]] == [16]
    assert any(reason["code"] == "USER" for reason in chosen["reasons"])
    assert not any(item["kind"] == "AMBIGUOUS" for item in items)
    latest = client.get("/api/audit", params={"limit": 5}).json()["items"]
    assert any(entry["action"] == "AMBIGUOUS_CHOSEN" for entry in latest)


def test_trace_follows_a_card_order_to_the_bank_line() -> None:
    upload_all(PERIOD1)
    chain = run_period(0)
    pos_gw = run_for(chain, "don-hang-cua-hang", "giao-dich-cong-thanh-toan", None)
    matched = next(
        item for item in all_results(pos_gw["id"])
        if item["kind"] == "MATCHED" and item["left"]
    )
    steps = client.get(
        f"/api/recon/chains/{chain['id']}/trace",
        params={"table_id": pos_gw["left"]["id"], "row_ref": matched["left"][0]["row_ref"]},
    ).json()["steps"]
    assert [step["pair"] for step in steps][:2] == [
        "don-hang-cua-hang ↔ giao-dich-cong-thanh-toan",
        "giao-dich-cong-thanh-toan ↔ sao-ke-ngan-hang › TK chinh",
    ]
    assert steps[1]["kind"] in ("MANY_TO_ONE", "MATCHED")

    # Xóa một bộ dữ liệu của chuỗi thì chuỗi (và các lần chạy trong đó) cũng bị xóa theo.
    dataset = next(
        item for item in client.get("/api/datasets").json()
        if item["original_filename"] == "sao-ke-ngan-hang.xlsx"
    )
    assert client.delete(f"/api/datasets/{dataset['id']}").status_code == 204
    assert client.get(f"/api/recon/chains/{chain['id']}").status_code == 404


# ---------------------------------------------------------------- từng phần của engine


def test_code_pattern_is_learned_from_the_other_side() -> None:
    pattern = learn_code_pattern(["HD000123", "HD000145", "HD000999"])
    assert pattern is not None
    code = {"kind": "code", "pattern": pattern}
    assert extract_keys("chuyen tien don hd000145 NGUYEN", code) == ["HD000145"]
    assert extract_keys("CK HD000123 HD000999", {"kind": "code", "pattern": pattern}) == [
        "HD000123",
        "HD000999",
    ]
    assert extract_keys("SO TK 1234567", {"kind": "code", "pattern": pattern}) == []
    assert learn_code_pattern(["12", "34"]) is None  # số ngắn dễ trùng tiền, ngày
    dates = extract_keys(
        "SAN TMDT THANH TOAN DOANH THU NGAY 03/10/2026", {"kind": "date", "pattern": ""}
    )
    assert dates == ["2026-10-03"]


def test_sender_name_drops_codes_business_words_and_honorifics() -> None:
    assert description_name("ANH HOANG CK TIEN HANG", []) == "hoang"
    assert description_name("CK HD000123 NGUYEN VAN AN", ["HD000123"]) == "nguyen van an"
    assert description_name("THANH TOAN TIEN HANG", []) is None


def test_business_days_skip_weekends() -> None:
    assert add_business_days(date(2026, 10, 9), 3) == date(2026, 10, 14)  # thứ Sáu → thứ Tư
    assert add_business_days(date(2026, 10, 12), 3) == date(2026, 10, 15)


def test_subset_search_finds_unique_and_multiple_solutions() -> None:
    def row(ref: int, amount: int) -> Row:
        return Row(ref, [], Decimal(amount), date(2026, 10, 1), None, False, {})

    one = _subsets([row(1, 100), row(2, 250), row(3, 400)], Decimal(350))
    assert [[item.ref for item in group] for group in one] == [[1, 2]]
    two = _subsets([row(1, 100), row(2, 200), row(3, 300)], Decimal(300))
    assert len(two) == 1  # chỉ tổ hợp ≥ 2 dòng: 100 + 200
    many = _subsets([row(1, 100), row(2, 200), row(3, 100), row(4, 200)], Decimal(300))
    assert len(many) == 2


def test_verification_rejects_a_group_with_wrong_sum() -> None:
    left = pl.DataFrame(
        {ROW_REF: [2, 3], "amount": [Decimal("100"), Decimal("200")]},
        schema={ROW_REF: pl.Int64, "amount": pl.Decimal(20, 2)},
    )
    right = pl.DataFrame(
        {ROW_REF: [2], "credit": [Decimal("350")]},
        schema={ROW_REF: pl.Int64, "credit": pl.Decimal(20, 2)},
    )
    results = [
        {"kind": "MANY_TO_ONE", "left_refs": [2, 3], "right_refs": [2],
         "amount_left": Decimal("300"), "amount_right": Decimal("350")}
    ]
    report = verify(
        left, right, results, {"amount_left": "amount", "amount_right": "credit"},
        {"counts": {"MANY_TO_ONE": 1}, "total_results": 1},
    )
    failed = [check["code"] for check in report["checks"] if not check["passed"]]
    assert failed == ["KIND_RULES"]


def test_shuffled_bank_gives_the_same_groups() -> None:
    from conftest import FIXTURES as fixtures  # noqa: F401

    tables = upload_all(["giao-dich-cong-thanh-toan.csv", "sao-ke-ngan-hang.xlsx"])
    from studio.cleaning import latest_version
    from studio.models import DatasetTable
    from studio.reconciliation import suggest_config

    frames = []
    with database.SessionFactory() as session:
        for key in (("giao-dich-cong-thanh-toan", None), ("sao-ke-ngan-hang", "TK chinh")):
            table = session.get(DatasetTable, uuid.UUID(tables[key]["id"]))
            version = latest_version(table) if table else None
            assert version is not None
            frames.append(pl.read_parquet(version.parquet_path))
    config, _ = suggest_config(frames[0], frames[1])
    baseline = reconcile(Side(frames[0]), Side(frames[1]), config)
    shuffled = [frame.sample(fraction=1.0, shuffle=True, seed=5) for frame in frames]
    assert reconcile(Side(shuffled[0]), Side(shuffled[1]), config) == baseline


@pytest.mark.parametrize("settle_days", [0, 3])
def test_pending_only_when_settlement_lag_exists(settle_days: int) -> None:
    left = pl.DataFrame(
        {ROW_REF: [2], "order_id": ["HD1"], "amount": [Decimal("100")],
         "order_date": [date(2026, 10, 14)]},
        schema={ROW_REF: pl.Int64, "order_id": pl.String, "amount": pl.Decimal(20, 2),
                "order_date": pl.Date},
    )
    right = pl.DataFrame(
        {ROW_REF: [2], "order_id": ["HD9"], "amount": [Decimal("999")],
         "transaction_date": [date(2026, 10, 14)]},
        schema={ROW_REF: pl.Int64, "order_id": pl.String, "amount": pl.Decimal(20, 2),
                "transaction_date": pl.Date},
    )
    config = ReconConfig("order_id", "order_id", "amount", "amount", "order_date",
                         "transaction_date", settle_days=settle_days)
    results = reconcile(Side(left), Side(right), config)
    order = next(item for item in results if item.left_refs == [2])
    assert order.kind == ("PENDING_SETTLEMENT" if settle_days else "ONLY_IN_A")


def test_results_store_carried_rows() -> None:
    upload_all(PERIOD1)
    run_period(0)
    upload_all(PERIOD2)
    second = run_period(1)
    with database.SessionFactory() as session:
        carried = [
            item for item in session.scalars(select(MatchResult))
            if item.carried_left and str(item.run_id) in {run["id"] for run in second["runs"]}
        ]
    assert carried and all(
        row.get("version_id") for item in carried for row in item.carried_left or []
    )


def test_chain_request_returns_before_pairs_are_found() -> None:
    # Dò cặp chạy ở tác vụ nền: API trả về ngay (chưa có cặp nào), các cặp xuất hiện sau.
    tables = upload_all(PERIOD1)
    ids = [table["id"] for table in tables.values()]
    reply = client.post("/api/recon/chains", json={"table_ids": ids})
    assert reply.status_code == 202
    assert reply.json()["status"] == "RUNNING" and reply.json()["runs"] == []
    chain = client.get(f"/api/recon/chains/{reply.json()['id']}").json()
    assert chain["status"] == "READY" and len(chain["runs"]) == 4


def test_chain_without_connectable_pairs_fails_with_a_clear_reason() -> None:
    # Hai bảng đơn hàng không nối được với nhau: chuỗi báo lỗi rõ ràng thay vì treo.
    tables = upload_all(["don-hang-cua-hang.csv", "don-hang-san-tmdt.xlsx"])
    ids = [table["id"] for table in tables.values() if table["row_count"]]
    reply = client.post("/api/recon/chains", json={"table_ids": ids})
    chain = client.get(f"/api/recon/chains/{reply.json()['id']}").json()
    assert chain["status"] == "FAILED" and "Không tìm được cặp" in chain["error_message"]
