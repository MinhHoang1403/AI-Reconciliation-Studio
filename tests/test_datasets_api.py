"""Kiểm API bộ dữ liệu trên bộ dữ liệu mẫu, đối chiếu với đáp án."""

import csv
import io
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES
from fastapi.testclient import TestClient

from studio import main
from studio.config import settings

client = TestClient(main.app)


def upload(name: str, content: bytes | None = None) -> Any:
    data = content if content is not None else (FIXTURES / name).read_bytes()
    return client.post("/api/datasets", files={"file": (name, data)})


def answer_rows(file_name: str) -> set[tuple[str, int]]:
    """Các cặp (sheet, số dòng) của một tệp được nhắc tới trong đáp án."""
    rows: set[tuple[str, int]] = set()
    with (FIXTURES / "dap-an.csv").open(encoding="utf-8") as handle:
        for item in csv.DictReader(handle):
            for side in ("left", "right"):
                if item[f"{side}_file"] == file_name:
                    rows.add((item[f"{side}_sheet"], int(item[f"{side}_row"])))
    return rows


def all_row_refs(table_id: str) -> list[int]:
    refs: list[int] = []
    offset = 0
    while True:
        page = client.get(
            f"/api/tables/{table_id}/rows", params={"offset": offset, "limit": 200}
        ).json()
        refs += page["row_refs"]
        offset += 200
        if offset >= page["total"]:
            return refs


def test_every_fixture_reads_and_row_refs_cover_the_answer_key() -> None:
    expected_tables: dict[str, dict[str | None, int | None]] = {
        "don-hang-san-tmdt.xlsx": {"Đơn hàng": 180, "Hướng dẫn": 0},
        "don-hang-cua-hang.csv": {None: 229},  # 220 đơn + dòng trống + dòng trùng + 7 lỗi cài sẵn
        "giao-dich-cong-thanh-toan.csv": {None: None},
        "sao-ke-ngan-hang.xlsx": {"TK chinh": None, "TK san": None},
    }
    for file_name, tables in expected_tables.items():
        reply = upload(file_name)
        assert reply.status_code == 202, reply.text
        dataset = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
        assert dataset["status"] == "READY", dataset
        assert [table["sheet_name"] for table in dataset["tables"]] == list(tables)
        referenced = answer_rows(file_name)
        for table in dataset["tables"]:
            expected_rows = tables[table["sheet_name"]]
            if expected_rows == 0:
                assert table["status"] == "NO_DATA" and table["row_count"] == 0
                continue
            assert table["status"] == "READY"
            if expected_rows is not None:
                assert table["row_count"] == expected_rows
            refs = set(all_row_refs(table["id"]))
            sheet = table["sheet_name"] or ""
            # Mọi dòng mà đáp án nhắc tới đều có trong bảng đã đọc, đúng số dòng gốc.
            assert {row for s, row in referenced if s == sheet} <= refs


def test_leading_zero_codes_and_phones_survive_reading() -> None:
    dataset = upload("don-hang-cua-hang.csv").json()["dataset"]
    table = client.get(f"/api/datasets/{dataset['id']}").json()["tables"][0]
    page = client.get(f"/api/tables/{table['id']}/rows", params={"limit": 5}).json()
    assert page["columns"][:4] == ["MaHD", "NgayBan", "KhachHang", "DienThoai"]
    assert page["rows"][0][0] == "HD000101"
    assert page["row_refs"][0] == 2
    profile = client.get(f"/api/tables/{table['id']}/profile").json()
    phone = next(column for column in profile["columns"] if column["name"] == "DienThoai")
    assert phone["kind"] == "PHONE" and phone["has_leading_zero"] is True
    assert profile["blank_row_count"] == 1


def test_same_file_uploaded_twice_is_recognised_as_duplicate() -> None:
    first = upload("giao-dich-cong-thanh-toan.csv")
    second = upload("giao-dich-cong-thanh-toan.csv")
    assert second.status_code == 200 and second.json()["duplicate"] is True
    assert second.json()["dataset"]["id"] == first.json()["dataset"]["id"]
    assert len(client.get("/api/datasets").json()) == 1


def test_rejects_unsupported_too_large_and_non_utf8_files(monkeypatch: pytest.MonkeyPatch) -> None:
    assert upload("bang.xls", b"abc").json()["detail"]["code"] == "UNSUPPORTED_FORMAT"
    assert upload("trong.csv", b"").json()["detail"]["code"] == "EMPTY_FILE"
    bad = upload("cu.csv", "Mã,Tên\n1,Bình".encode("cp1252"))
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "NOT_UTF8"
    monkeypatch.setattr(settings, "max_upload_bytes", 10)
    big = upload("lon.csv", b"a,b\n" * 10)
    assert big.status_code == 413 and "MB" in big.json()["detail"]["message"]
    assert client.get("/api/datasets").json() == []
    assert (
        not any((Path(settings.storage_root) / "raw").glob("*"))
        if (Path(settings.storage_root) / "raw").exists()
        else True
    )


def test_user_can_choose_a_different_header_row() -> None:
    dataset = upload("sao-ke-ngan-hang.xlsx").json()["dataset"]
    table = client.get(f"/api/datasets/{dataset['id']}").json()["tables"][0]
    assert table["header_row"] == 5
    reply = client.put(f"/api/tables/{table['id']}/header-row", json={"header_row": 6})
    assert reply.status_code == 202
    updated = client.get(f"/api/datasets/{dataset['id']}").json()["tables"][0]
    assert updated["header_row"] == 6 and updated["header_row_chosen_by_user"] is True
    assert updated["row_count"] == table["row_count"] - 1


def test_delete_removes_dataset_and_its_files() -> None:
    dataset = upload("sao-ke-ngan-hang.xlsx").json()["dataset"]
    files_before = list(Path(settings.storage_root).rglob("*.*"))
    assert len(files_before) >= 3  # tệp gốc + 2 bảng Parquet
    assert client.delete(f"/api/datasets/{dataset['id']}").status_code == 204
    assert client.get(f"/api/datasets/{dataset['id']}").status_code == 404
    assert [path for path in Path(settings.storage_root).rglob("*.*")] == []


def test_failed_read_can_be_retried() -> None:
    reply = upload("hong.xlsx", b"day khong phai excel")
    dataset = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
    assert dataset["status"] == "FAILED" and "Excel" in dataset["error_message"]
    retried = client.post(f"/api/datasets/{dataset['id']}/read")
    assert retried.status_code == 202
    assert client.get(f"/api/datasets/{dataset['id']}").json()["status"] == "FAILED"


def test_rows_of_table_that_is_not_ready_returns_409() -> None:
    dataset = upload("don-hang-san-tmdt.xlsx").json()["dataset"]
    guide = client.get(f"/api/datasets/{dataset['id']}").json()["tables"][1]
    assert client.get(f"/api/tables/{guide['id']}/rows").status_code == 409


def test_large_csv_of_100k_rows_reads_completely() -> None:
    import time

    from make_sales_fixtures import large_pos_csv

    content = large_pos_csv(100_000)
    started = time.perf_counter()
    reply = upload("lon-100k.csv", content)
    elapsed = time.perf_counter() - started
    dataset = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
    assert dataset["status"] == "READY"
    assert dataset["tables"][0]["row_count"] == 100_000
    print(
        f"\nĐọc 100.000 dòng ({len(content) / 1e6:.1f} MB) mất {elapsed:.2f} giây "
        "(tải lên + đọc + ghi Parquet + hồ sơ cột)"
    )
    assert io.BytesIO(content).getbuffer().nbytes < settings.max_upload_bytes


def test_large_xlsx_of_100k_rows_reads_completely() -> None:
    import time

    import xlsxwriter

    buffer = io.BytesIO()
    book = xlsxwriter.Workbook(buffer, {"in_memory": True, "constant_memory": True})
    sheet = book.add_worksheet("Đơn hàng")
    sheet.write_row(0, 0, ["Mã đơn", "Ngày", "Khách hàng", "Số tiền", "Ghi chú"])
    for row in range(1, 100_001):
        sheet.write_row(row, 0, [f"DH{row:07d}", "05/10/2026", "Nguyễn Văn An", row * 1000, "Mẫu"])
    book.close()
    content = buffer.getvalue()
    started = time.perf_counter()
    reply = upload("lon-100k.xlsx", content)
    elapsed = time.perf_counter() - started
    dataset = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
    assert dataset["tables"][0]["row_count"] == 100_000
    print(f"\nĐọc Excel 100.000 dòng ({len(content) / 1e6:.1f} MB) mất {elapsed:.2f} giây")
