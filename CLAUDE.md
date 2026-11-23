# CLAUDE.md — AI Reconciliation Studio

Đọc trước mọi nhiệm vụ, theo thứ tự:

@RULES.md
@docs/ARCHITECTURE.md
@docs/PLAN.md
@docs/DECISIONS.md

Trả lời và báo cáo cho Owner bằng tiếng Việt.

## Trạng thái (23/11/2026)

Giai đoạn 0 (khung), 1 (đọc dữ liệu), 2 (ánh xạ cột có Gemini, Langfuse), 3 (chuẩn hóa, làm sạch), 4 (đối soát 1:1, kiểm chứng, ngoại lệ, nhật ký kiểm toán) đã xong. Việc tiếp theo: Giai đoạn 5 — tách mã từ nội dung chuyển khoản, khớp nhóm, ca mơ hồ, kỳ đối soát (`docs/PLAN.md`).

Đáp án đối soát cặp đơn cửa hàng ↔ cổng thanh toán nằm trong `tests/fixtures/sales/dap-an.csv` (quan hệ `cua-hang↔cong-thanh-toan`); `tests/test_reconciliation.py` đo precision/recall trên đó.

Lỗi cài sẵn cho bước làm sạch: `tests/fixtures/sales/loi-cai-san.csv` (dòng 222–230 của tệp đơn hàng cửa hàng). E2E gọi Gemini thật nên mỗi bài trong `data.spec.ts` được tối đa 120 giây.

Đo độ chính xác ánh xạ: `uv run --locked python tools/evaluate_mapping.py` (chỉ quy tắc, miễn phí); thêm `--with-ai` để gọi Gemini thật (tốn phí, cần nạp khóa từ `.env` vào biến môi trường). Langfuse tự host ở <http://127.0.0.1:3000> (bộ container `langfuse` riêng); khóa trong `.env`.

Bộ dữ liệu mẫu có đáp án ở `tests/fixtures/sales/`, sinh lại bằng `uv run --locked python tools/make_sales_fixtures.py` (kết quả luôn giống hệt).

## Tra cứu code bằng Graphify (trước khi đọc file)

Repo `MinhHoang1403/AI-Reconciliation-Studio` đã được Graphify lập chỉ mục (đồ thị hàm, lớp, lời gọi, file, test) và tự lập lại sau mỗi lần push lên `main`. Không đọc cả file hay cả thư mục để "nắm lại dự án"; tra đồ thị trước, chỉ mở đúng đoạn code cần sửa:

| Cần biết | Công cụ Graphify |
| --- | --- |
| Hàm/lớp nằm ở đâu | `graphify_find` |
| Danh sách hàm của một file (không đọc thân hàm) | `graphify_file_neighbors` với `symbols_only` |
| Ai gọi hàm này | `graphify_callers` |
| Sửa hàm này ảnh hưởng tới đâu | `graphify_impact` |
| Test nào kiểm hàm/file này | `graphify_tests_for` |
| Hỏi bằng lời (ví dụ "chỗ nào ghi trạng thái làm sạch") | `query_graph`, `graphify_rank_files` |

Lưu ý:
- Chỉ mục ứng với commit đã push (xem `freshness.commit` trong kết quả). Code đang sửa dở chưa push thì tra bằng Grep/Read.
- Gói miễn phí chỉ lập chỉ mục `README.md` trong số tài liệu; `docs/` vẫn đọc trực tiếp.
- `n=0` ở `graphify_callers` nghĩa là đồ thị chưa thấy cạnh nào, không chắc là không có; kiểm lại bằng Grep trước khi xóa hay đổi tên.

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
