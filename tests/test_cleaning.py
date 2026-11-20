"""Kiểm chuẩn hóa và làm sạch: bộ đọc giá trị, lỗi cài sẵn, không sửa nhầm dòng sạch, API, AI."""

import csv
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from conftest import FIXTURES
from fastapi.testclient import TestClient

from studio import cleaning_ai, main, reading
from studio.cleaning import BuildInput, _plan_columns, build
from studio.gemini_client import AiReply
from studio.value_parsers import (
    detect_date_order,
    detect_number_style,
    name_match_key,
    parse_date,
    parse_money,
    parse_phone,
)

client = TestClient(main.app)
POS_MAPPING = [
    ("MaHD", "order_id"),
    ("NgayBan", "order_date"),
    ("KhachHang", "customer_name"),
    ("DienThoai", "customer_phone"),
    ("TongTien", "amount"),
    ("ThanhToan", "payment_method"),
]


# ---------------------------------------------------------------- bộ đọc giá trị


@pytest.mark.parametrize(
    ("raw", "style", "expected"),
    [
        ("1.250.000", "VN", "1250000"),
        ("1,250,000.50", "EN", "1250000.50"),
        ("(500)", "VN", "-500"),
        ("1tr2", "VN", "1200000"),
        ("500k", "VN", "500000"),
        ("1,5tr", "VN", "1500000"),
        ("1.250.000 đ", "VN", "1250000"),
        ("1250000.0", "VN", "1250000"),
    ],
)
def test_money_formats(raw: str, style: Any, expected: str) -> None:
    parsed = parse_money(raw, style)
    assert parsed.state == "VALID" and parsed.value == Decimal(expected)


def test_unreadable_money_and_dates_are_invalid_not_guessed() -> None:
    assert parse_money("khoảng 500k").state == "INVALID"
    assert parse_date("31/02/2026").state == "INVALID"
    assert parse_date("ngày 9 tháng 10").state == "INVALID"


def test_number_style_and_date_order_are_inferred_from_the_whole_column() -> None:
    assert detect_number_style(["1,250,000", "13,750"]) == "EN"
    assert detect_number_style(["1.250.000", "500"]) == "VN"
    assert detect_date_order(["05/10/2026", "13/10/2026"]) == ("DMY", False)
    assert detect_date_order(["10/13/2026", "10/05/2026"]) == ("MDY", False)
    # Không phân biệt được: mặc định ngày/tháng và báo là mặc định.
    assert detect_date_order(["05/10/2026", "06/10/2026"]) == ("DMY", True)
    assert parse_date("10/05/2026", "MDY").value == date(2026, 10, 5)


def test_phone_and_name_keys() -> None:
    assert parse_phone("84915000444").value == "0915000444"
    assert parse_phone("+84 912 345 678").value == "0912345678"
    assert parse_phone("912345678").value == "0912345678"
    assert name_match_key("anh Hoàng") == name_match_key("Chú Hoàng") == "hoang"
    assert name_match_key("Minh Hoàng") == "minh hoang"


# ---------------------------------------------------------------- lỗi cài sẵn


def pos_build(
    corrections: dict[tuple[int, str], str] | None = None, decisions: dict[int, str] | None = None
) -> Any:
    raw = reading.read_csv((FIXTURES / "don-hang-cua-hang.csv").read_bytes())
    table = reading.build_table(raw, reading.detect_header_row(raw.frame))
    return build(
        BuildInput(
            uuid.uuid4(),
            "ORDERS_POS",
            table.frame,
            _plan_columns(table.frame, POS_MAPPING, {}),
            corrections or {},
            decisions or {},
            {},
        )
    ), table.frame


def test_every_injected_error_is_found_at_the_expected_level() -> None:
    result, _ = pos_build()
    clean = {
        ref: row
        for ref, row in zip(
            result.frame["__row_ref"].to_list(), result.frame.iter_rows(named=True), strict=True
        )
    }
    with (FIXTURES / "loi-cai-san.csv").open(encoding="utf-8") as handle:
        expected = list(csv.DictReader(handle))
    for case in expected:
        refs = [int(ref) for ref in case["rows"].split(";")]
        field = case["field"] or None
        if case["level"] == "AUTO":
            if case["kind"] == "EMPTY_ROW":
                assert refs[0] in result.summary["empty_rows"]
                continue
            value = clean[refs[0]][field]
            shown = value.isoformat() if hasattr(value, "isoformat") else str(value)
            assert shown.removesuffix(".00") == case["expected"], case
            continue
        found = [
            issue
            for issue in result.issues
            if issue["kind"] == case["kind"]
            and issue["row_refs"] == refs
            and issue["level"] == case["level"]
            and (field is None or issue["field_key"] == field)
        ]
        assert found, case
    # Không có vấn đề nào ngoài các lỗi đã cài.
    assert len(result.issues) == sum(row["level"] != "AUTO" for row in expected)


def test_clean_rows_are_not_changed_by_mistake() -> None:
    """Mọi đơn bình thường (dòng 2–221) giữ đúng mã, số tiền và ngày như tệp gốc."""
    result, raw = pos_build()
    clean = {row["__row_ref"]: row for row in result.frame.iter_rows(named=True)}
    for row in raw.filter(raw["__row_ref"] <= 221).iter_rows(named=True):
        ref = row["__row_ref"]
        assert clean[ref]["order_id"] == row["MaHD"]
        assert clean[ref]["amount"] == Decimal(row["TongTien"])
        day, month, year = row["NgayBan"].split(" ")[0].split("/")
        assert clean[ref]["order_date"] == date(int(year), int(month), int(day))
        assert clean[ref]["customer_phone"] == (row["DienThoai"] or None)


def test_user_decisions_resolve_issues() -> None:
    result, _ = pos_build(
        corrections={(226, "amount"): "500000", (230, "order_date"): "09/10/2026"},
        decisions={223: "EXCLUDE", 224: "EXCLUDE", 2: "KEEP", 229: "KEEP"},
    )
    assert all(issue["status"] == "RESOLVED" for issue in result.issues)
    refs = result.frame["__row_ref"].to_list()
    assert 223 not in refs and 224 not in refs and 222 not in refs
    row = result.frame.filter(result.frame["__row_ref"] == 226).row(0, named=True)
    assert row["amount"] == Decimal("500000")


def test_100k_rows_build_within_reasonable_time() -> None:
    import time

    from make_sales_fixtures import large_pos_csv

    raw = reading.read_csv(large_pos_csv(100_000))
    table = reading.build_table(raw, reading.detect_header_row(raw.frame))
    started = time.perf_counter()
    result = build(
        BuildInput(
            uuid.uuid4(),
            "ORDERS_POS",
            table.frame,
            _plan_columns(table.frame, POS_MAPPING, {}),
            {},
            {},
            {},
        )
    )
    elapsed = time.perf_counter() - started
    print(f"\nLàm sạch 100.000 dòng mất {elapsed:.2f} giây")
    assert result.frame.height == 100_000


# ---------------------------------------------------------------- qua API


def upload(name: str) -> dict[str, Any]:
    content = (FIXTURES / name).read_bytes()
    reply = client.post("/api/datasets", files={"file": (name, content)})
    body: dict[str, Any] = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
    return body


def cleaning(table_id: str) -> dict[str, Any]:
    body: dict[str, Any] = client.get(f"/api/tables/{table_id}/cleaning").json()
    return body


def test_cleaning_runs_after_upload_and_user_actions_resolve_issues() -> None:
    table = upload("don-hang-cua-hang.csv")["tables"][0]
    assert table["clean_status"] == "READY" and table["clean_open"] == 5
    view = cleaning(table["id"])
    assert view["open_counts"] == {"SUGGEST": 1, "ASK": 4}
    assert view["row_count"] == 228 and view["excluded_count"] == 1

    client.post(f"/api/tables/{table['id']}/cleaning/duplicates/accept")
    client.post(
        f"/api/tables/{table['id']}/cleaning/cells",
        json={"row_ref": 226, "field_key": "amount", "value": "500.000"},
    )
    bad = client.post(
        f"/api/tables/{table['id']}/cleaning/cells",
        json={"row_ref": 230, "field_key": "order_date", "value": "hôm qua"},
    )
    assert bad.status_code == 422
    client.post(
        f"/api/tables/{table['id']}/cleaning/rows", json={"row_refs": [224], "decision": "EXCLUDE"}
    )
    view = cleaning(table["id"])
    assert view["open_counts"] == {"SUGGEST": 0, "ASK": 2}
    assert view["version"] == 4  # mỗi thay đổi dựng một phiên bản sạch mới

    rows = client.get(f"/api/tables/{table['id']}/clean-rows", params={"limit": 3}).json()
    assert [column["key"] for column in rows["columns"]][:2] == ["order_id", "order_date"]
    assert rows["rows"][0][1] == rows["rows"][0][1][:10]  # ngày dạng năm-tháng-ngày


def test_date_order_can_be_flipped_for_the_whole_column() -> None:
    table = upload("sao-ke-ngan-hang.xlsx")["tables"][0]
    view = cleaning(table["id"])
    orders = {item["field_key"]: item for item in view["summary"]["date_orders"]}
    assert orders["transaction_date"]["order"] == "DMY"
    client.put(
        f"/api/tables/{table['id']}/cleaning/date-order",
        json={"field_key": "transaction_date", "order": "MDY"},
    )
    flipped = cleaning(table["id"])
    # Đọc tháng/ngày thì các ngày như 13/10 không còn hợp lệ → thành vấn đề cần hỏi.
    assert flipped["open_counts"]["ASK"] > 0


def test_platform_cancelled_orders_are_kept_and_flagged() -> None:
    table = upload("don-hang-san-tmdt.xlsx")["tables"][0]
    view = cleaning(table["id"])
    assert view["summary"]["cancelled_count"] > 0
    assert view["row_count"] == 180


def test_ai_suggestion_is_validated_and_only_applied_when_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_ai(**kwargs: Any) -> AiReply:
        cells = kwargs["payload"]["cells"]
        answers = {"amount": "500000", "order_date": "không rõ"}
        return AiReply(
            data={
                "suggestions": [
                    {
                        "id": cell["id"],
                        "value": answers[cell["field"]],
                        "confidence": 0.8,
                        "reason": "giả lập",
                    }
                    for cell in cells
                ]
            },
            input_tokens=1,
            output_tokens=1,
        )

    monkeypatch.setattr(cleaning_ai, "generate_json", fake_ai)
    table = upload("don-hang-cua-hang.csv")["tables"][0]
    issues = {
        issue["field_key"]: issue
        for issue in cleaning(table["id"])["issues"]
        if issue["kind"] == "INVALID_VALUE"
    }
    assert issues["amount"]["ai_suggestion"]["value"] == "500000"
    # Đề xuất không đọc được thành ngày thì bị bỏ, không đưa cho người dùng.
    assert issues["order_date"]["ai_suggestion"]["value"] is None
    assert issues["amount"]["status"] == "OPEN"  # chưa đồng ý thì chưa áp dụng

    client.post(
        f"/api/tables/{table['id']}/cleaning/suggestions/accept",
        params={"row_ref": 226, "field_key": "amount"},
    )
    after = {
        issue["field_key"]: issue
        for issue in cleaning(table["id"])["issues"]
        if issue["kind"] == "INVALID_VALUE"
    }
    assert "amount" not in after  # ô đã đọc được sau khi dùng gợi ý


def test_deleting_dataset_removes_clean_files() -> None:
    from pathlib import Path

    from studio.config import settings

    dataset = upload("giao-dich-cong-thanh-toan.csv")
    assert list(Path(settings.storage_root).rglob("*-sach-v*.parquet"))
    client.delete(f"/api/datasets/{dataset['id']}")
    assert not list(Path(settings.storage_root).rglob("*.parquet"))
