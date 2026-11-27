"""Kiểm báo cáo Giai đoạn 7 trên bộ mẫu bán hàng (không gọi Gemini thật).

Mốc xong (docs/PLAN.md): mọi con số trong báo cáo khớp kết quả engine; CSV và XLSX cùng nội
dung; kỳ chưa kiểm chứng không xuất được; nhận xét AI không có con số nào ngoài số liệu báo cáo.
Số liệu "đúng" ở đây được tính lại độc lập từ danh sách kết quả mà API đối soát trả về.
"""

import csv
import io
import uuid
from decimal import Decimal
from typing import Any

import polars as pl
import pytest
from fastapi.testclient import TestClient
from test_phase5 import PERIOD1, PERIOD2, all_results, run_period, upload_all

from studio import database, main, report_ai, reporting
from studio.gemini_client import AiReply
from studio.models import ReconRun

client = TestClient(main.app)
MATCHED = ("MATCHED", "MANY_TO_ONE", "ONE_TO_MANY")


def money(value: Any) -> Decimal:
    return Decimal(str(value)) if value not in (None, "") else Decimal("0")


def expected_pair(run_id: str) -> dict[str, Any]:
    """Tính lại số liệu một cặp chỉ từ các kết quả engine (không dùng module báo cáo)."""
    results = all_results(run_id)
    scoped = [item for item in results if item["kind"] != "OUT_OF_SCOPE"]
    matched = [item for item in results if item["kind"] in MATCHED]
    return {
        "rows_in_scope": sum(len(item["left"]) for item in scoped),
        "rows_matched": sum(len(item["left"]) for item in matched),
        "amount_in_scope": sum((money(item["amount_left"]) for item in scoped), Decimal(0)),
        "amount_matched": sum((money(item["amount_left"]) for item in matched), Decimal(0)),
        "mismatch_total": sum(
            (
                abs(money(item["amount_left"]) - money(item["amount_right"]))
                for item in results
                if item["kind"] == "AMOUNT_MISMATCH"
            ),
            Decimal(0),
        ),
        "missing_amount": sum(
            (money(item["amount_left"]) for item in results if item["kind"] == "ONLY_IN_A"),
            Decimal(0),
        ),
        "unknown_amount": sum(
            (money(item["amount_right"]) for item in results if item["kind"] == "ONLY_IN_B"),
            Decimal(0),
        ),
        "open_count": sum(item["exception_status"] == "OPEN" for item in results),
        "total": len(results),
    }


@pytest.fixture
def period1() -> dict[str, Any]:
    upload_all(PERIOD1)
    chain = run_period(0)
    report: dict[str, Any] = client.get(f"/api/reports/{chain['id']}").json()
    return report


def test_every_number_matches_the_engine_results(period1: dict[str, Any]) -> None:
    assert period1["verified"] and len(period1["pairs"]) == 4
    # Chuỗi tạo không kèm tên lấy tên kỳ, không phải dãy tên bảng.
    assert period1["label"].startswith("Kỳ ") and "›" not in period1["label"]
    totals: dict[str, Decimal] = {}
    for pair in period1["pairs"]:
        want = expected_pair(pair["run_id"])
        for key in ("rows_in_scope", "rows_matched", "open_count"):
            assert pair[key] == want[key], (pair["label"], key)
        for key in (
            "amount_in_scope",
            "amount_matched",
            "mismatch_total",
            "missing_amount",
            "unknown_amount",
        ):
            assert money(pair[key]) == want[key], (pair["label"], key)
        for key, value in want.items():
            totals[key] = totals.get(key, Decimal(0)) + Decimal(value)
    kpis = period1["kpis"]
    assert kpis["open_count"] == totals["open_count"] == 10
    assert money(kpis["amount_matched"]) == totals["amount_matched"]
    rate = round(float(totals["amount_matched"]) * 100 / float(totals["amount_in_scope"]), 1)
    assert kpis["match_rate_amount"] == rate
    # Biểu đồ theo loại phủ đúng mọi kết quả; tuổi ngoại lệ phủ đúng mọi ca đang mở.
    assert sum(item["count"] for item in period1["by_kind"]) == totals["total"]
    assert sum(bucket["count"] for bucket in period1["aging"]) == kpis["open_count"]
    assert len(period1["exceptions"]) == kpis["open_count"]
    amounts = [money(item["amount"]) for item in period1["top_exceptions"]]
    assert amounts == sorted(amounts, reverse=True) and len(amounts) == 5
    # HD000123: cổng thu ít hơn đơn 20.000đ (đáp án) — lệch phải hiện đúng số.
    mismatch = next(item for item in period1["exceptions"] if "HD000123" in item["codes"])
    assert money(mismatch["amount"]) == Decimal("20000")
    # Báo cáo gọi "chỉ có ở một bên" theo nghĩa tiền, trùng tên ô số chính; mỗi ca có tên hai
    # bảng để ca không có mã được gọi "dòng 41 của <bảng>" thay vì "dòng B 41".
    labels = {item["kind"]: item["kind_label"] for item in period1["exceptions"]}
    assert labels.get("ONLY_IN_A", "Thiếu tiền về") == "Thiếu tiền về"
    assert labels.get("ONLY_IN_B", "Tiền về chưa rõ nguồn") == "Tiền về chưa rõ nguồn"
    assert not any(item["label"].startswith("Chỉ có ở") for item in period1["by_kind"])
    assert all(item["left_label"] and item["right_label"] for item in period1["exceptions"])
    no_code = {"left_rows": [], "right_rows": [41], "left_label": "x", "right_label": "sao kê"}
    assert reporting.rows_text(no_code) == "dòng 41 của sao kê"


def test_csv_and_xlsx_have_the_same_content(period1: dict[str, Any]) -> None:
    chain_id = period1["chain_id"]
    csv_reply = client.get(f"/api/reports/{chain_id}/export.csv")
    xlsx_reply = client.get(f"/api/reports/{chain_id}/export.xlsx")
    assert csv_reply.status_code == xlsx_reply.status_code == 200
    assert "attachment" in xlsx_reply.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(csv_reply.content.decode("utf-8-sig"))))
    sheet = pl.read_excel(
        io.BytesIO(xlsx_reply.content), sheet_name="Toàn bộ kết quả", infer_schema_length=0
    )
    assert rows[0] == sheet.columns
    body = rows[1:]
    assert len(body) == sheet.height == sum(item["count"] for item in period1["by_kind"])

    def same(text: str, cell: Any) -> bool:
        if cell is None:
            return text == ""
        try:
            return Decimal(text) == Decimal(str(cell))
        except ArithmeticError:
            return text == str(cell)

    for csv_row, xlsx_row in zip(body, sheet.iter_rows(), strict=True):
        assert all(same(a, b) for a, b in zip(csv_row, xlsx_row, strict=True)), csv_row
    names = pl.read_excel(io.BytesIO(xlsx_reply.content), sheet_id=0)
    assert list(names) == ["Tóm tắt", "Cần xử lý", "Toàn bộ kết quả"]


def test_unverified_period_is_viewable_but_not_exported(period1: dict[str, Any]) -> None:
    with database.SessionFactory() as session:
        run = session.get(ReconRun, uuid.UUID(period1["pairs"][0]["run_id"]))
        assert run is not None
        run.verification = {"passed": False, "checks": []}
        session.commit()
    chain_id = period1["chain_id"]
    report = client.get(f"/api/reports/{chain_id}").json()
    assert report["verified"] is False and report["kpis"]["open_count"] == 10
    for path in ("export.csv", "export.xlsx"):
        reply = client.get(f"/api/reports/{chain_id}/{path}")
        assert reply.status_code == 409 and reply.json()["detail"]["code"] == "NOT_VERIFIED"
    assert client.post(f"/api/reports/{chain_id}/comment").status_code == 409


def fake_gemini(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    def answer(**_: Any) -> AiReply:
        return AiReply(data={"text": text}, input_tokens=1, output_tokens=1)

    monkeypatch.setattr(report_ai, "generate_json", answer)


def test_ai_comment_uses_only_report_numbers(
    period1: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    facts = report_ai.facts(period1 | {"kpis": period1["kpis"]})
    good = (
        f"Kỳ này đã khớp {facts['ty_le_khop_theo_tien']} số tiền. Còn "
        f"{facts['so_ca_can_xu_ly']} ca cần xử lý, thiếu tiền về {facts['thieu_tien_ve']}."
    )
    fake_gemini(monkeypatch, good)
    chain_id = period1["chain_id"]
    reply = client.post(f"/api/reports/{chain_id}/comment")
    assert reply.status_code == 200 and reply.json()["text"] == good
    assert client.get(f"/api/reports/{chain_id}").json()["comment"]["stale"] is False

    # Con số AI tự suy ra (không có trong báo cáo) làm cả lời nhận xét bị bỏ.
    fake_gemini(monkeypatch, "Kỳ này đã khớp 99,9% số tiền, chỉ thiếu 123.456 đ.")
    bad = client.post(f"/api/reports/{chain_id}/comment")
    assert bad.status_code == 503 and bad.json()["detail"]["code"] == "AI_UNGROUNDED"
    assert client.get(f"/api/reports/{chain_id}").json()["comment"]["text"] == good

    # Xử lý xong một ngoại lệ: số liệu đổi nên nhận xét cũ được đánh dấu đã cũ.
    run_id = period1["pairs"][0]["run_id"]
    target = next(item for item in all_results(run_id) if item["exception_status"] == "OPEN")
    client.post(
        f"/api/recon/runs/{run_id}/actions",
        json={"action": "RESOLVE", "result_ids": [target["id"]]},
    )
    after = client.get(f"/api/reports/{chain_id}").json()
    assert after["kpis"]["open_count"] == 9 and after["comment"]["stale"] is True


def test_comparison_lists_each_reconciled_period() -> None:
    upload_all(PERIOD1 + PERIOD2)
    run_period(0)
    run_period(1)
    periods = client.get("/api/reports").json()["periods"]
    assert len(periods) == 2 and periods[0]["period_start"] < periods[1]["period_start"]
    assert all(period["verified"] and period["kpis"]["match_rate_amount"] for period in periods)


def test_money_and_rate_are_written_the_vietnamese_way() -> None:
    assert report_ai.money_text("1250000.00") == "1.250.000 đ"
    assert report_ai.money_text(Decimal("-20000")) == "-20.000 đ"
    assert report_ai.rate_text(96.5) == "96,5%"
    assert report_ai.rate_text(91.0) == "91%"  # giống cách trang Báo cáo hiển thị
    assert report_ai.unknown_numbers("Khớp 96,5%, HD000123", {"a": "96,5%", "b": "HD000123"}) == []


def test_assistant_reads_the_same_report_numbers(period1: dict[str, Any]) -> None:
    from studio import assistant_tools

    with database.SessionFactory() as session:
        result = assistant_tools.get_report(session, assistant_tools.ReportArgs())
    assert result["verified"] is True and result["_link"]["path"] == "/bao-cao"
    assert result["so_ca_can_xu_ly"] == str(period1["kpis"]["open_count"])
    assert result["ty_le_khop_theo_tien"] == report_ai.rate_text(
        period1["kpis"]["match_rate_amount"]
    )
    # Số ca theo loại do engine đếm, cộng lại đúng tổng số ca cần xử lý.
    by_kind = result["ca_can_xu_ly_theo_loai"]
    assert sum(int(item["so_ca"]) for item in by_kind) == period1["kpis"]["open_count"]
    assert {"Dữ liệu chưa sạch", "Lệch tiền"} <= {item["loai"] for item in by_kind}
    text = repr(result)
    assert "Nguyen" not in text and "NGUYEN" not in text  # không có tên khách


def test_period2_numbers_include_rows_carried_from_period1() -> None:
    # Kỳ 2 nhận dòng chờ tiền về của kỳ 1: số liệu vẫn phải khớp kết quả engine, dòng mang
    # sang ghi riêng "kỳ trước" trong tệp xuất.
    upload_all(PERIOD1 + PERIOD2)
    run_period(0)
    chain = run_period(1)
    report = client.get(f"/api/reports/{chain['id']}").json()
    for pair in report["pairs"]:
        want = expected_pair(pair["run_id"])
        assert pair["rows_in_scope"] == want["rows_in_scope"], pair["label"]
        assert money(pair["amount_matched"]) == want["amount_matched"], pair["label"]
    text = client.get(f"/api/reports/{chain['id']}/export.csv").content.decode("utf-8-sig")
    assert "kỳ trước: " in text
    summary = pl.read_excel(
        io.BytesIO(client.get(f"/api/reports/{chain['id']}/export.xlsx").content),
        sheet_name="Tóm tắt",
        has_header=False,
        infer_schema_length=0,
    )
    cells = [str(value) for row in summary.iter_rows() for value in row if value is not None]
    assert not any("None" in cell or "." in cell and cell.endswith("%") for cell in cells)
