# CLAUDE.md — AI Reconciliation Studio

Đọc trước mọi nhiệm vụ, theo thứ tự:

@RULES.md
@docs/ARCHITECTURE.md
@docs/PLAN.md
@docs/DECISIONS.md

Trả lời và báo cáo cho Owner bằng tiếng Việt.

## Trạng thái (20/11/2026)

Kiến trúc và kế hoạch demo đã được Owner duyệt. Chưa có mã nguồn. Việc tiếp theo: Giai đoạn 0 — khung dự án (`docs/PLAN.md`).

## Môi trường máy Owner

- Windows, dùng **Windows PowerShell 5.1** (`powershell`):
  - Tham số truyền cho lệnh native bị mất dấu nháy kép bên trong; chuỗi nhiều dòng (ví dụ commit message) nên ghi ra file rồi truyền đường dẫn.
  - File `.ps1` có tiếng Việt phải lưu UTF-8 **có BOM**.
  - Không dùng `2>$null` với lệnh native khi `$ErrorActionPreference = 'Stop'`; kiểm `$LASTEXITCODE`.
- Docker Desktop dùng chung với các dự án khác của Owner: không dùng `docker system prune`/`volume prune`, chỉ đụng tài nguyên của dự án này.
- Khóa Gemini ở `GEMINI_API_KEY` trong `.env` (không commit).
