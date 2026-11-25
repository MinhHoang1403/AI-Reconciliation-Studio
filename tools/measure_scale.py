"""Đo tốc độ trọn luồng ở quy mô lớn: tải tệp → đọc, ánh xạ, làm sạch → đối soát cả chuỗi →
báo cáo, xuất XLSX/CSV.

Chạy trên cơ sở dữ liệu SQLite và thư mục tệp TẠM (như pytest), không đụng dữ liệu của app
đang chạy, không gọi Gemini (ánh xạ chỉ bằng quy tắc). Dữ liệu sinh bằng chính bộ sinh của bộ
mẫu bán hàng (tools/make_sales_fixtures.py), cùng định dạng tệp, chỉ tăng số đơn.

    uv run --locked python tools/measure_scale.py                 # 100.000 đơn cửa hàng
    uv run --locked python tools/measure_scale.py --pos 20000 --platform 5000

Số đo là của máy chạy lệnh; PostgreSQL trong container có thể nhanh/chậm hơn SQLite đôi chút
ở phần ghi kết quả, còn phần đọc tệp và engine đối soát (Polars, Python) giống nhau.
"""

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(tempfile.mkdtemp(prefix="studio-scale-"))
# Phải đặt trước khi import studio: cấu hình đọc biến môi trường lúc import.
os.environ["DATABASE_URL"] = f"sqlite:///{(WORK / 'scale.db').as_posix()}"
os.environ["STORAGE_ROOT"] = str(WORK / "files")
os.environ["GEMINI_API_KEY"] = ""
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools"))

import make_sales_fixtures as fixtures  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from studio import database, main  # noqa: E402
from studio.migrate import upgrade_to_latest  # noqa: E402


def build_files(pos: int, platform: int) -> dict[str, bytes]:
    """Một kỳ 14 ngày đủ 4 nguồn (đơn sàn, đơn cửa hàng, giao dịch cổng, sao kê)."""
    builder = fixtures.SalesFixtureBuilder(
        pos_orders=pos, platform_orders=platform, special_cases=False
    )
    files = builder.build_sources()
    last = max(item.day for item in builder.bank_main + builder.bank_platform)
    files[fixtures.BANK_FILE] = builder.write_bank(fixtures.PERIOD_START, last)
    return files


def timed(label: str, results: list[tuple[str, float, str]], action: Any, note: str = "") -> Any:
    start = time.perf_counter()
    value = action()
    results.append((label, time.perf_counter() - start, note))
    return value


def main_run(pos: int, platform: int) -> None:
    with database.engine.begin() as connection:
        upgrade_to_latest(connection)
    client = TestClient(main.app)
    results: list[tuple[str, float, str]] = []

    files = timed("Sinh dữ liệu mẫu", results, lambda: build_files(pos, platform))
    for name, content in files.items():
        # TestClient chạy tác vụ nền ngay trong lời gọi: thời gian gồm đọc, hồ sơ cột, ánh xạ
        # theo quy tắc và dựng bộ sạch.
        reply = timed(
            f"Tải + đọc + ánh xạ + làm sạch: {name}",
            results,
            lambda name=name, content=content: client.post(
                "/api/datasets", files={"file": (name, content)}
            ),
        )
        dataset = client.get(f"/api/datasets/{reply.json()['dataset']['id']}").json()
        rows = sum(table["row_count"] for table in dataset["tables"])
        results[-1] = (*results[-1][:2], f"{rows:_} dòng".replace("_", "."))

    periods = client.get("/api/recon/periods").json()
    period = max(periods, key=lambda item: len(item["tables"]))
    chain = timed(
        "Đối soát cả chuỗi (mọi cặp + kiểm chứng)",
        results,
        lambda: client.post(
            "/api/recon/chains", json={"table_ids": [t["id"] for t in period["tables"]]}
        ).json(),
    )
    view = client.get(f"/api/recon/chains/{chain['id']}").json()
    results[-1] = (
        *results[-1][:2],
        f"{len(view['runs'])} cặp, {view['status']}, "
        f"kiểm chứng {'đạt' if view['verified'] else 'KHÔNG đạt'}",
    )
    report = timed(
        "Mở trang Báo cáo (GET báo cáo)",
        results,
        lambda: client.get(f"/api/reports/{chain['id']}").json(),
    )
    results[-1] = (*results[-1][:2], f"{report['kpis']['open_count']} ca cần xử lý")
    timed("Tải Excel", results, lambda: client.get(f"/api/reports/{chain['id']}/export.xlsx"))
    timed("Tải CSV", results, lambda: client.get(f"/api/reports/{chain['id']}/export.csv"))
    timed("Dashboard (số chính các kỳ)", results, lambda: client.get("/api/reports"))
    timed(
        "Trang Đối soát: 50 ca cần xử lý đầu tiên",
        results,
        lambda: [
            client.get(
                f"/api/recon/runs/{run['id']}/results", params={"group": "todo", "limit": 50}
            )
            for run in view["runs"]
        ],
    )

    print(f"\nQuy mô: {pos:,} đơn cửa hàng, {platform:,} đơn sàn\n".replace(",", "."))
    for label, seconds, note in results:
        print(f"{seconds:8.2f} giây  {label}" + (f"  ({note})" if note else ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pos", type=int, default=100_000, help="Số đơn cửa hàng")
    parser.add_argument("--platform", type=int, default=20_000, help="Số đơn sàn TMĐT")
    options = parser.parse_args()
    try:
        main_run(options.pos, options.platform)
    finally:
        database.engine.dispose()
        shutil.rmtree(WORK, ignore_errors=True)
