# CLAUDE.md — AI Reconciliation Studio

Đọc trước mọi nhiệm vụ, theo thứ tự:

@RULES.md
@docs/ARCHITECTURE.md
@docs/PLAN.md
@docs/DECISIONS.md

Trả lời và báo cáo cho Owner bằng tiếng Việt.

## Trạng thái (20/11/2026)

Giai đoạn 0 (khung dự án) đã xong. Việc tiếp theo: Giai đoạn 1 — đọc dữ liệu, làm trên nhánh `phase-1` (`docs/PLAN.md`).

## Lệnh kiểm

```powershell
uv run --locked ruff check backend tests
uv run --locked mypy backend tests
uv run --locked pytest -q
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
