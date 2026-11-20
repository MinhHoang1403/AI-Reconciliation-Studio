# CLAUDE.md — AI Reconciliation Studio

Đọc trước mọi nhiệm vụ, theo thứ tự:

@RULES.md
@docs/ARCHITECTURE.md
@docs/PLAN.md
@docs/DECISIONS.md

Trả lời và báo cáo cho Owner bằng tiếng Việt.

## Trạng thái (20/11/2026)

Giai đoạn 0 (khung), 1 (đọc dữ liệu), 2 (ánh xạ cột có Gemini, Langfuse) đã xong. Việc tiếp theo: Giai đoạn 3 — chuẩn hóa và xử lý lỗi (`docs/PLAN.md`).

Đo độ chính xác ánh xạ: `uv run --locked python tools/evaluate_mapping.py` (chỉ quy tắc, miễn phí); thêm `--with-ai` để gọi Gemini thật (tốn phí, cần nạp khóa từ `.env` vào biến môi trường). Langfuse tự host ở <http://127.0.0.1:3000> (bộ container `langfuse` riêng); khóa trong `.env`.

Bộ dữ liệu mẫu có đáp án ở `tests/fixtures/sales/`, sinh lại bằng `uv run --locked python tools/make_sales_fixtures.py` (kết quả luôn giống hệt).

## Lệnh kiểm

```powershell
uv run --locked ruff check backend tests tools
uv run --locked mypy backend tests tools
uv run --locked pytest -q          # gồm kiểm migration trên SQLite tạm và đo đọc 100.000 dòng
Push-Location frontend; npm run check; npm run lint; npm run build; Pop-Location
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start.ps1   # build + chạy + kiểm 3/3 healthy + dọn image cũ
Push-Location frontend; npm run test:e2e; Pop-Location                 # E2E trên 127.0.0.1:18180
```

## Giao diện

Dùng skill **impeccable** (bối cảnh ở `PRODUCT.md`, `DESIGN.md`, `.impeccable/`) và **ui-ux-pro-max**. Thế giới hình ảnh đã chốt: "Tờ tiền polymer" (`DESIGN.md`).

## Môi trường máy Owner

- Windows, dùng **Windows PowerShell 5.1** (`powershell`):
  - Tham số truyền cho lệnh native bị mất dấu nháy kép bên trong; chuỗi nhiều dòng (ví dụ commit message) nên ghi ra file rồi truyền đường dẫn.
  - File `.ps1` có tiếng Việt phải lưu UTF-8 **có BOM**.
  - Không dùng `2>$null` với lệnh native khi `$ErrorActionPreference = 'Stop'`; kiểm `$LASTEXITCODE`.
- Docker Desktop dùng chung với các dự án khác của Owner: không dùng `docker system prune`/`volume prune`, chỉ đụng tài nguyên của dự án này.
- Khóa Gemini ở `GEMINI_API_KEY` trong `.env` (không commit).
