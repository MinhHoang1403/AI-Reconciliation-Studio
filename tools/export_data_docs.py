"""Sinh phần tĩnh của thư mục data-docs/ từ code: data model, data catalog, schema JSON.

    uv run --locked python tools/export_data_docs.py

Chạy lại sau khi sửa models.py, sales_fields.py, cleaning.py (trường bắt buộc), các khuôn JSON
gửi Gemini, công cụ của Assistant hay API. tests/test_data_docs.py báo lỗi nếu tệp trong
data-docs/ lệch với code (quên chạy lệnh này). Không cần cơ sở dữ liệu, không gọi Gemini.
Phần chạy (data-docs/runtime/) do backend tự ghi khi chạy, không sinh ở đây.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Chỉ đọc mô hình và cấu hình, không kết nối cơ sở dữ liệu; đặt URL tạm cho cấu hình hợp lệ.
os.environ.setdefault("DATABASE_URL", "sqlite://")
sys.path.insert(0, str(ROOT / "backend"))

from studio.data_docs import write_static  # noqa: E402

if __name__ == "__main__":
    for path in write_static(ROOT / "data-docs"):
        print(path.relative_to(ROOT).as_posix())
