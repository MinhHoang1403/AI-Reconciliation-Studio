"""Kiểm hồi quy cho các lỗi ẩn tìm thấy khi rà toàn bộ nền hệ thống (Giai đoạn 0–5).

Mỗi bài bắt đúng một lỗi đã sửa; tên bài nói rõ lỗi đó.
"""

import random
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import polars as pl
from conftest import FIXTURES
from fastapi.testclient import TestClient
from sqlalchemy import select

from studio import database, ingestion, main, mapping_service, reading
from studio.models import MatchResult, ReconChain, ReconRun
from studio.reading import ROW_REF
from studio.reconciliation import ReconConfig, Side, reconcile
from studio.value_parsers import is_cancelled_status, parse_date, parse_phone

client = TestClient(main.app)


# ---------------------------------------------------------------- đọc tệp, đọc giá trị


def test_header_is_found_when_a_blank_row_follows_it() -> None:
    # Excel hay để một dòng trống ngay dưới tiêu đề; trước đây cả bảng mất tên cột.
    raw = reading.read_csv("Mã ĐH,Số tiền\n,\nHD1,100\nHD2,200\n".encode())
    table = reading.build_table(raw, reading.detect_header_row(raw.frame))
    assert table.header_row == 1
    assert table.column_names == ["Mã ĐH", "Số tiền"]
    assert table.frame[ROW_REF].to_list() == [2, 3, 4]  # dòng trống ở giữa vẫn giữ số dòng gốc


def test_dates_with_year_first_slashes_and_time_zones_are_read() -> None:
    for text in ("2026/10/01", "2026.10.01", "2026-10-01T08:00:00+07:00", "2026-10-01T08:00:00Z"):
        parsed = parse_date(text)
        assert parsed.state == "VALID" and parsed.value == date(2026, 10, 1), text
    assert parse_date("10/01/2026 2:30 PM", "MDY").value == date(2026, 10, 1)
    assert parse_date("46296.75").value == date(2026, 10, 1)  # số ngày Excel kèm giờ
    assert parse_date("2026-10/01").state == "INVALID"  # dấu phân cách lẫn lộn


def test_landline_numbers_are_valid_phones() -> None:
    assert parse_phone("028 3822 1234").value == "02838221234"
    assert parse_phone("+84 28 3822 1234").value == "02838221234"
    assert parse_phone("+84 912 345 678").value == "0912345678"
    assert parse_phone("02838").state == "INVALID"


def test_cancelled_status_matches_whole_words_only() -> None:
    # "huy" nằm lọt trong "chuyển", "khuyến": trước đây các đơn này bị coi là đã hủy.
    for status in ("Đã chuyển khoản", "Khuyến mãi", "Thành công"):
        assert not is_cancelled_status(status), status
    for status in ("Đã hủy", "Hủy đơn", "Hoàn tiền", "Cancelled", "Order refunded", "Trả hàng"):
        assert is_cancelled_status(status), status


# ---------------------------------------------------------------- ánh xạ


def upload_text(name: str, text: str) -> dict[str, Any]:
    reply = client.post("/api/datasets", files={"file": (name, text.encode())})
    assert reply.status_code in (200, 202), reply.text
    dataset: dict[str, Any] = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
    return dataset


def test_mapping_memory_applies_when_column_names_differ_only_in_case_or_accents() -> None:
    first = upload_text(
        "kenh-a.csv", "Mã ĐH,Ngày đặt,Số tiền\nHD1,01/10/2026,100000\nHD2,02/10/2026,200000\n"
    )["tables"][0]
    assert client.post(f"/api/tables/{first['id']}/mapping/confirm").status_code == 200
    expected = [
        column["field_key"]
        for column in client.get(f"/api/tables/{first['id']}/mapping").json()["columns"]
    ]
    assert "order_id" in expected and "amount" in expected

    # Cùng cấu trúc, tên cột viết hoa không dấu: trước đây nhận ra cấu trúc nhưng tra ánh xạ
    # theo tên gốc nên mọi cột thành "không ánh xạ" mà vẫn ghi là đã xác nhận.
    second = upload_text(
        "kenh-b.csv", "MA DH,NGAY DAT,SO TIEN\nHD3,03/10/2026,300000\n"
    )["tables"][0]
    reused = client.get(f"/api/tables/{second['id']}/mapping").json()
    assert reused["ai_state"] == "MEMORY"
    assert [column["field_key"] for column in reused["columns"]] == expected


def test_table_kind_follows_the_confirmed_mapping() -> None:
    # Loại do AI đoán được giữ khi không mâu thuẫn với cột; mâu thuẫn thì theo cột.
    assert mapping_service.resolve_table_kind("ORDERS_POS", {"order_id", "amount"}) == "ORDERS_POS"
    assert mapping_service.resolve_table_kind("ORDERS_PLATFORM", {"order_id", "amount"}) == (
        "ORDERS_PLATFORM"
    )
    assert mapping_service.resolve_table_kind("ORDERS_POS", {"credit", "description"}) == (
        "BANK_STATEMENT"
    )
    assert mapping_service.resolve_table_kind("UNKNOWN", {"payment_id", "amount"}) == (
        "PAYMENT_GATEWAY"
    )
    assert mapping_service.resolve_table_kind("BANK_STATEMENT", {"description"}) == "BANK_STATEMENT"


def test_failed_resuggest_does_not_leave_the_table_stuck(monkeypatch: Any) -> None:
    table = upload_text("ban-hang.csv", "Mã ĐH,Số tiền\nHD1,100\n")["tables"][0]

    def broken(*_: Any, **__: Any) -> None:
        raise RuntimeError("lỗi giả lập")

    monkeypatch.setattr(mapping_service, "score_columns", broken)
    # "Gợi ý lại" gọi thẳng tác vụ nền; trước đây lỗi lạ làm bảng kẹt ở "đang gợi ý".
    assert client.post(f"/api/tables/{table['id']}/mapping/suggest").status_code == 202
    after = client.get(f"/api/tables/{table['id']}/mapping").json()
    assert after["status"] == "READY" and after["ai_state"] == "FAILED"


# ---------------------------------------------------------------- khởi động lại, đối soát


def test_restart_fails_interrupted_reconciliations() -> None:
    with database.SessionFactory() as session:
        chain = ReconChain(id=uuid.uuid4(), status="RUNNING", label="Kỳ thử", table_ids=[])
        run = ReconRun(
            id=uuid.uuid4(),
            left_table_id=uuid.uuid4(),
            right_table_id=uuid.uuid4(),
            status="RUNNING",
            config={},
        )
        session.add_all([chain, run])
        session.commit()
    ingestion.recover_interrupted()
    with database.SessionFactory() as session:
        statuses = {item.status for item in session.scalars(select(ReconChain))}
        statuses |= {item.status for item in session.scalars(select(ReconRun))}
    # Trước đây hai bản ghi này ở RUNNING mãi, giao diện hỏi lại vô tận.
    assert statuses == {"FAILED"}


def test_large_tables_without_a_common_key_reconcile_quickly() -> None:
    # Hai bảng 20.000 dòng không có mã chung: vòng khớp nhóm trước đây so mọi dòng với mọi dòng
    # (hàng trăm triệu phép so) và gần như treo.
    generator = random.Random(7)
    size = 20_000
    start = date(2026, 10, 1)

    def table(day_column: str) -> pl.DataFrame:
        return pl.DataFrame(
            {
                ROW_REF: list(range(1, size + 1)),
                "amount": [Decimal(generator.randrange(10, 5000) * 1000) for _ in range(size)],
                day_column: [start + timedelta(days=generator.randrange(60)) for _ in range(size)],
            },
            schema={ROW_REF: pl.Int64, "amount": pl.Decimal(20, 2), day_column: pl.Date},
        )

    config = ReconConfig(
        key_left=None,
        key_right=None,
        amount_left="amount",
        amount_right="amount",
        date_left="order_date",
        date_right="transaction_date",
    )
    began = time.perf_counter()
    results = reconcile(Side(table("order_date")), Side(table("transaction_date")), config)
    elapsed = time.perf_counter() - began
    covered = sum(len(item.left_refs) + len(item.right_refs) for item in results)
    assert covered == 2 * size
    assert elapsed < 60, f"đối soát mất {elapsed:.1f} giây"


def test_rerunning_an_earlier_period_does_not_take_pending_rows_from_a_later_one() -> None:
    files = [
        "don-hang-cua-hang.csv",
        "giao-dich-cong-thanh-toan.csv",
        "don-hang-san-tmdt.xlsx",
        "sao-ke-ngan-hang.xlsx",
    ]
    for name in files + [name.replace(".", "-ky-2.", 1) for name in files]:
        client.post("/api/datasets", files={"file": (name, (FIXTURES / name).read_bytes())})

    def run_period(index: int) -> dict[str, Any]:
        period = client.get("/api/recon/periods").json()[index]
        reply = client.post(
            "/api/recon/chains", json={"table_ids": [table["id"] for table in period["tables"]]}
        )
        chain: dict[str, Any] = client.get(f"/api/recon/chains/{reply.json()['id']}").json()
        assert chain["status"] == "READY", chain
        return chain

    run_period(0)
    later = run_period(1)
    assert sum(run["carried_count"] for run in later["runs"]) > 0  # kỳ 2 nhận dòng chờ kỳ 1
    # Bộ mẫu kỳ 2 không còn dòng chờ ở cuối kỳ; thêm một dòng chờ vào mọi cặp của kỳ 2 để thấy
    # kỳ 1 có nhận nhầm hay không.
    with database.SessionFactory() as session:
        for run in later["runs"]:
            session.add(
                MatchResult(
                    id=uuid.uuid4(),
                    run_id=uuid.UUID(run["id"]),
                    position=10_000,
                    kind="PENDING_SETTLEMENT",
                    left_refs=[2],
                    right_refs=[],
                    reasons=[],
                )
            )
        session.commit()
    # Chạy lại kỳ 1 sau kỳ 2: trước đây nhận nhầm dòng chờ của kỳ 2 (lần chạy mới nhất).
    again = run_period(0)
    assert sum(run["carried_count"] for run in again["runs"]) == 0
