"""Kiểm ánh xạ cột: quy tắc, che dữ liệu, gộp với AI, phân tầng, bộ nhớ và API."""

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES
from evaluate_mapping import evaluate, sample_cases, unseen_cases
from fastapi.testclient import TestClient

from studio import gemini_client, main, mapping_service
from studio.config import settings
from studio.gemini_client import AiReply, AiUnavailable
from studio.mapping_rules import normalize_name, score_columns
from studio.masking import mask_sample
from studio.models import DatasetTable
from studio.profiling import TableProfile, profile_table
from studio.reading import ROW_REF

client = TestClient(main.app)


# ---------------------------------------------------------------- quy tắc


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MaHD", "ma hoa don"),
        ("SĐT người nhận", "so dien thoai nguoi nhan"),
        ("Mã đơn hàng", "ma don hang"),
        ("NgayBan", "ngay ban"),
        ("Thành tiền (VNĐ)", "thanh tien vnd"),
    ],
)
def test_normalize_name_splits_words_removes_accents_and_expands_abbreviations(
    raw: str, expected: str
) -> None:
    assert normalize_name(raw) == expected


def test_rules_alone_map_every_sample_column_and_never_auto_apply_a_wrong_one() -> None:
    sample = evaluate(sample_cases(), with_ai=False)
    assert sample.correct == sample.total  # 35/35 trên bộ mẫu
    unseen = evaluate(unseen_cases(), with_ai=False)
    # Tên cột lạ: quy tắc đúng ít hơn, nhưng cột nào đã tự áp dụng thì phải đúng.
    assert unseen.auto_correct == unseen.auto
    assert sample.auto_correct == sample.auto


# ---------------------------------------------------------------- che dữ liệu


def test_masking_keeps_shape_but_hides_personal_data() -> None:
    assert mask_sample("0912345678", "PHONE", 200) == "09xxxxxx78"
    assert mask_sample("Nguyễn Văn An", "TEXT", 200) == "Nguyễn V** A*"
    assert mask_sample("CK HD000115 LE NGOC DUNG", "TEXT", 200) == "CK HD000115 L* N*** D***"
    assert mask_sample("Hoàn thành", "TEXT", 2) == "Hoàn thành"  # danh mục: gửi nguyên
    assert mask_sample("HD000101", "CODE", 200) == "HD000101"
    assert mask_sample("0071000012345", "NUMBER", 200) == "0071xxxxx2345"


def test_ai_payload_for_sample_files_contains_no_full_phone_or_customer_name() -> None:
    import csv

    with (FIXTURES / "don-hang-cua-hang.csv").open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    secrets = {row["DienThoai"] for row in rows if row["DienThoai"]}
    secrets |= {row["KhachHang"] for row in rows if row["KhachHang"] not in ("", "Khách lẻ")}
    for case in sample_cases():
        payload = mapping_service.build_ai_payload(
            DatasetTable(sheet_name=None),
            case.profile,
            score_columns(case.profile),
        )
        text = json.dumps(payload, ensure_ascii=False)
        assert not any(secret in text for secret in secrets), case.label


# ---------------------------------------------------------------- gộp với AI


def small_profile() -> TableProfile:
    import polars as pl

    frame = pl.DataFrame(
        {
            ROW_REF: [2, 3, 4],
            "Order No": ["A1001", "A1002", "A1003"],
            "Gross": ["100000", "250000", "90000"],
            "Kênh": ["Web", "App", "Web"],
        }
    )
    return profile_table(frame)


def test_ai_and_rules_agreeing_is_auto_applied_disagreement_waits_for_user() -> None:
    profile = small_profile()
    scores = score_columns(profile)
    names = [column.name for column in profile.columns]
    kind, ai = mapping_service.parse_ai_reply(
        {
            "table_kind": "ORDERS_POS",
            "columns": [
                {"name": "Order No", "field": "order_id", "confidence": 0.95, "reason": "Mã đơn"},
                {"name": "Gross", "field": "amount", "confidence": 0.9, "reason": "Tổng tiền"},
                {"name": "Kênh", "field": "NONE", "confidence": 0.8, "reason": "Kênh bán"},
            ],
        },
        names,
    )
    decisions = {item["column_name"]: item for item in mapping_service.decide(scores, ai, names)}
    assert kind == "ORDERS_POS"
    assert decisions["Kênh"]["field_key"] is None and decisions["Kênh"]["status"] == "AUTO"
    assert decisions["Gross"]["field_key"] == "amount"
    # "Gross" là tên tiếng Anh quy tắc không biết: AI đúng nhưng quy tắc không đồng ý → chờ xem.
    assert decisions["Gross"]["status"] == "SUGGESTED"


def test_ai_reply_with_invented_field_or_unknown_column_is_ignored() -> None:
    names = ["Order No"]
    _, ai = mapping_service.parse_ai_reply(
        {
            "table_kind": "BI_A",
            "columns": [
                {"name": "Cot khong co", "field": "order_id", "confidence": 1, "reason": "x"},
                {"name": "Order No", "field": "ma_bia_ra", "confidence": 1, "reason": "x"},
            ],
        },
        names,
    )
    assert ai == {}


# ---------------------------------------------------------------- qua API


def upload(name: str) -> dict[str, Any]:
    content = (FIXTURES / name).read_bytes()
    reply = client.post("/api/datasets", files={"file": (name, content)})
    body: dict[str, Any] = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
    return body


def test_mapping_without_gemini_key_uses_rules_and_says_so() -> None:
    dataset = upload("don-hang-cua-hang.csv")
    table = dataset["tables"][0]
    assert table["mapping_status"] == "READY" and table["table_kind"] == "ORDERS_POS"
    mapping = client.get(f"/api/tables/{table['id']}/mapping").json()
    assert mapping["ai_state"] == "NOT_CONFIGURED"
    fields = {column["column_name"]: column["field_key"] for column in mapping["columns"]}
    assert fields["MaHD"] == "order_id" and fields["ThanhToan"] == "payment_method"
    assert mapping["table_kind_label"] == "Đơn hàng cửa hàng"


def test_gemini_failure_falls_back_to_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(**_: Any) -> AiReply:
        raise AiUnavailable("FAILED", "Gemini không trả lời được (ServerError).")

    monkeypatch.setattr(mapping_service, "generate_json", broken)
    table = upload("giao-dich-cong-thanh-toan.csv")["tables"][0]
    mapping = client.get(f"/api/tables/{table['id']}/mapping").json()
    assert mapping["ai_state"] == "FAILED" and "ServerError" in mapping["ai_message"]
    assert all(column["field_key"] for column in mapping["columns"])


def test_confirmed_mapping_is_remembered_for_same_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_ai(**kwargs: Any) -> AiReply:
        calls.append(kwargs["purpose"])
        names = [column["name"] for column in kwargs["payload"]["columns"]]
        return AiReply(
            data={
                "table_kind": "BANK_STATEMENT",
                "columns": [
                    {"name": name, "field": "NONE", "confidence": 0.5, "reason": "giả lập"}
                    for name in names
                ],
            },
            input_tokens=10,
            output_tokens=5,
        )

    monkeypatch.setattr(mapping_service, "generate_json", fake_ai)
    dataset = upload("sao-ke-ngan-hang.xlsx")
    first, second = dataset["tables"]
    assert len(calls) == 2  # mỗi sheet một lần gọi AI

    # Người dùng sửa một cột rồi xác nhận tất cả ở sheet đầu.
    client.put(f"/api/tables/{first['id']}/mapping/columns/6", json={"field_key": "description"})
    confirmed = client.post(f"/api/tables/{first['id']}/mapping/confirm").json()
    assert confirmed["pending_count"] == 0

    # Sheet thứ hai cùng cấu trúc: gợi ý lại thì dùng bộ nhớ, không gọi AI nữa.
    monkeypatch.setattr(gemini_client, "gemini_configured", lambda: True)
    mapping_service.suggest_for_table(__import__("uuid").UUID(second["id"]))
    reused = client.get(f"/api/tables/{second['id']}/mapping").json()
    assert reused["ai_state"] == "MEMORY" and len(calls) == 2
    assert reused["columns"][6]["field_key"] == "description"
    assert {column["status"] for column in reused["columns"]} == {"CONFIRMED"}


def test_choosing_a_field_taken_by_another_column_moves_it() -> None:
    table = upload("don-hang-cua-hang.csv")["tables"][0]
    reply = client.put(
        f"/api/tables/{table['id']}/mapping/columns/0", json={"field_key": "amount"}
    ).json()
    by_position = {column["position"]: column for column in reply["columns"]}
    assert by_position[0]["field_key"] == "amount" and by_position[0]["status"] == "CONFIRMED"
    assert by_position[4]["field_key"] is None and by_position[4]["status"] == "SUGGESTED"
    bad = client.put(f"/api/tables/{table['id']}/mapping/columns/0", json={"field_key": "khong_co"})
    assert bad.status_code == 422


def test_status_reports_langfuse_configuration() -> None:
    body = client.get("/api/status").json()
    assert body["langfuse"]["state"] == "NEEDS_CONFIGURATION"
    assert "secret" not in json.dumps(body).lower()


def test_ai_call_log_records_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """generate_json ghi nhật ký (không có nội dung) kể cả khi thất bại."""
    from studio import database
    from studio.models import AiCall

    monkeypatch.setattr(gemini_client, "gemini_configured", lambda: True)
    monkeypatch.setattr(
        settings, "gemini_api_key", __import__("pydantic").SecretStr("khoa-gia")
    )
    monkeypatch.setattr(settings, "gemini_attempts", 1)
    with pytest.raises(AiUnavailable):
        gemini_client.generate_json(
            purpose="kiem-thu",
            system_instruction="x",
            payload={"a": 1},
            response_schema={"type": "object"},
        )
    with database.SessionFactory() as session:
        calls = session.query(AiCall).filter_by(purpose="kiem-thu").all()
    assert calls and calls[-1].status == "FAILED" and calls[-1].error_code


def test_unseen_fixture_file_is_valid() -> None:
    data = json.loads(Path(FIXTURES / "ten-cot-moi.json").read_text(encoding="utf-8"))
    assert sum(len(table["columns"]) for table in data["tables"]) == 30
