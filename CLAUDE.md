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

## Tra cứu code và bộ nhớ phiên (trước khi đọc file)

Hai công cụ chạy hoàn toàn trên máy, miễn phí (thay Graphify Cloud):

- **Graph code — Graphify bản mã nguồn mở** (MCP `graphify` trong `.mcp.json`, đọc `graphify-out/graph.json`). Code được đọc bằng tree-sitter, không gọi LLM. Dựng lại sau khi sửa code: `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\code-graph.ps1`. Xem graph trực quan: <http://127.0.0.1:3114/graph.html>.
- **Bộ nhớ phiên — agentmemory** (plugin Claude Code phạm vi local, máy chủ Docker ở `C:\Work\agentmemory`, bộ container `agentmemory`). Hooks tự ghi lại các phiên làm việc; tìm lại quyết định, lỗi đã sửa của phiên trước bằng công cụ MCP của agentmemory. Trang xem: <http://127.0.0.1:3113> (tự mở khóa qua proxy `viewer-proxy`; tab Graph có graph code do `tools/code-graph.ps1` nhập vào). REST ở 3111 vẫn cần khóa trong `C:\Work\agentmemory\.env`. Chỉ tìm theo từ khóa và embedding local, không gọi LLM trả phí.
- Cấu hình riêng của máy (không thuộc repo): `C:\Work\agentmemory\docker-compose.override.yml` (proxy 3113, trang graph 3114, gắn `graphify-out` chỉ đọc) và `.claude/settings.local.json` (plugin agentmemory, `MCP_TIMEOUT` 60 giây).

**Quy trình agentmemory (bắt buộc, Owner yêu cầu 23/11/2026):**
1. **Đầu mỗi việc:** `memory_smart_search` / `memory_recall` (project `ai-reconciliation-studio`) về chủ đề sắp làm, trước khi đọc file hay tài liệu dài.
2. **Trong khi làm:** chốt một quyết định, sửa xong một lỗi khó, phát hiện một bẫy → `memory_save` ngay (type `architecture`/`bug`/`workflow`/`fact`, kèm `files`).
3. **Bị Owner sửa cách làm:** `memory_lesson_save`.
4. **Làm xong một việc (trước khi báo cáo):** `memory_save` tóm tắt việc đã làm, commit, kết quả kiểm thử và việc còn dở.
Không lưu khóa, mật khẩu hay dữ liệu khách hàng vào agentmemory.

Không đọc cả file hay cả thư mục để "nắm lại dự án"; tra trước, chỉ mở đúng đoạn code cần sửa:

| Cần biết | Công cụ MCP `graphify` |
| --- | --- |
| Hàm/lớp nằm ở đâu, chỗ nào làm việc X | `query_graph` |
| Chi tiết một hàm/lớp | `get_node` |
| Ai gọi / gọi ai, file nào dùng file nào | `get_neighbors` |
| Đường nối giữa hai phần | `shortest_path` |
| Các nút trung tâm, thống kê | `god_nodes`, `graph_stats` |
| Vì sao đã chọn X ở phiên trước, lỗi nào đã sửa | công cụ tìm kiếm của agentmemory |

Lưu ý:
- Graph ứng với lần chạy `tools/code-graph.ps1` gần nhất (kể cả code chưa commit). Vừa sửa nhiều thì chạy lại script hoặc tra bằng Grep/Read.
- Graph chỉ có code; `docs/` vẫn đọc trực tiếp.
- Graph không thấy cạnh nào chưa chắc là không có; kiểm lại bằng Grep trước khi xóa hay đổi tên.

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
