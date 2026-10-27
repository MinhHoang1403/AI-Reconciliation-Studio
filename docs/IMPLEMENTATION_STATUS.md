# Báo cáo triển khai Giai đoạn 1

Ngày kiểm tra: **28/10/2026**. Phạm vi: Data Foundation + AI Smart Setup + UI cơ sở.

**Giai đoạn 1 chưa DONE: BLOCKED tại gate Qwen live.** Endpoint từ chối IP bằng HTTP 403. Các phần dữ liệu, UI, Docker và kiểm thử độc lập đã chạy thật; không chuyển sang Giai đoạn 2 hoặc nhập code vào main khi gate bắt buộc này chưa đạt.

## A. Kết quả đã xây

- Backend FastAPI, PostgreSQL metadata/migration, worker durable queue và Nginx/React trong một Compose project.
- Tạo/chọn project; nhiều CSV/XLSX; inspection/MIME/magic/ZIP/XML/size; raw streaming SHA256 và scoped reuse.
- Đọc nhiều sheet/header lệch dòng, giữ zero-prefix, raw cell/formula/cache metadata, physical source positions và cảnh báo cần review.
- Profiling bằng code, shortlist, AI Gateway, Qwen adapter và manual review khi provider lỗi.
- Mapping Studio chỉnh/sửa/duyệt/từ chối, schema tùy chỉnh, immutable mapping revisions, audit và stale canonical.
- Normalization DSL có kiểu, Decimal trực tiếp từ chuỗi, timezone rõ ràng, error artifacts và lineage đầy đủ; không mất dòng hoặc ép invalid/null thành zero.
- Dashboard dữ liệu thật, Explorer phân trang/tìm kiếm phía server, canonical/error preview, evidence và settings policy. Lưu/khôi phục dự án, schema, approval, jobs và artifacts.

Files/modules chính: `backend/studio/contracts`, `parsing.py`, `profiling.py`, `schema_mapping.py`, `normalization.py`, `ai_gateway.py`, `document_parser.py`, `database.py`, `repository.py`, `access.py`, `api.py`, `worker.py`; `backend/migrations`; `frontend/src`; `compose.yaml`; tests và các công cụ vận hành trong `tools`.

Các lỗi phát hiện qua kiểm tra đã được sửa và giữ regression: Parquet struct khóa rỗng; openpyxl không đọc raw UUID thiếu đuôi; nhận nhầm `0.00`/Paid thành định danh; stale preview khi đổi lớp/query; locale đã duyệt không hiển thị lại; global cloud budget bằng 0 vẫn cần chặn trước reserve/HTTP. Không thay đổi công thức hoặc kế hoạch để làm test PASS.

## B. Kiến trúc và handoff

Modular monolith, backend/worker chung image; PostgreSQL là nguồn metadata/permissions/approvals/jobs/audit, raw/Parquet trên volume riêng. Không có Redis/Celery, model server, database mới hoặc Compose project test.

Pydantic/OpenAPI xuất `CanonicalDataset`, `DatasetProfile`, `SchemaDefinition`, `MappingRevision`, `EvidenceRef`, `JobStatus`, `WorkspacePolicy` và artifact refs có scope/quality. Giai đoạn sau consume các contracts này. Chi tiết tại [kiến trúc](ARCHITECTURE.md) và [hợp đồng API/dữ liệu](DATA_CONTRACTS.md).

## C. AI — phân biệt live và mock

| Phần | Trạng thái | Bằng chứng |
|---|---|---|
| Qwen model `knowledge`, không API key | BLOCKED LIVE | Base URL mới đã cấu hình; models và inference đều 403 do allowlist; host và worker Docker cùng bị chặn |
| Request/response inference Qwen thực | NOT VERIFIED | 403 chưa chứng minh candidate chat protocol hoặc generation thành công |
| Qwen JSON/schema/semantic/error/retry | PASS MOCK | Mock transport, task IDs, no fake Authorization, strict Pydantic, evidence/type/approval gates |
| Gemini `gemini-3.5-flash-lite` | PASS CONTRACT / LIVE NOT VERIFIED | API/model docs đã đối chiếu; mock success/error/missing key/JSON/budget/cloud OFF |
| LlamaParse | PASS CONTRACT / LIVE NOT VERIFIED | REST upload/poll/extraction/timeout/policy contract; output UNVERIFIED_EXTRACTION |
| Cloud policy | PASS | Gemini/LlamaParse không được gọi thật; global và workspace budgets mặc định 0; không fallback khi Qwen lỗi |

25 AI contract test cases nằm trong bộ offline, không cộng thêm vào tổng backend. Không có kết quả precision/recall đại diện hoặc auto-approve benchmark. AI không tự duyệt mapping tiền. Xem [tích hợp AI](AI_INTEGRATION.md).

## D. Kiểm chứng thực tế

| Lệnh/nhóm | Kết quả |
|---|---|
| `uv run pytest -q -m 'not integration'` trên Windows | 76 PASS, 8 deselected, 0 FAIL |
| `tools/test-postgres.ps1 -All` trong backend Linux | **84 PASS**, 0 FAIL, 0 SKIP; gồm 76 offline + 8 PostgreSQL integration |
| PostgreSQL integration riêng | 8 PASS; UUID schema cô lập, không tác động bảng ứng dụng |
| Ruff / mypy | PASS cho backend/tests/tools và typed backend |
| Frontend TypeScript / ESLint / production build | PASS |
| Playwright production UI | **8 PASS**, 0 FAIL; first-time/returning/invalid/provider error/security và 5 kích thước màn hình |
| Stale-preview regression | PASS; trì hoãn response tìm kiếm, UI không trình bày dữ liệu query cũ dưới query mới |
| Live worker failure/recovery | PASS; SIGKILL trong normalization 75.000 dòng tổng hợp, 2 attempts, đúng 1 canonical, đủ dòng và raw/parsed giữ nguyên |
| Restart / force-recreate / recreate riêng frontend | PASS; metadata, jobs/attempts, approvals và SHA256 mọi artifact trong snapshot giữ nguyên |
| Local access | PASS; HttpOnly/SameSite session, CSRF/Host/workspace/role checks; proof mất hiệu lực trước re-verification |
| Source secrets / Markdown / diff | PASS tại các lần rà source; kiểm tra lại trước mỗi push |
| Qwen mapping live | BLOCKED, không có PASS giả |

Có một cảnh báo deprecation Starlette TestClient/httpx từ dependency; bộ tests vẫn PASS. Tests golden T01–T16 và giới hạn OCR được đối chiếu trong [hướng dẫn kiểm thử](TESTING_GUIDE.md). Mock không thay live.

Fault test chỉ dừng worker của project này, khi không có job khác đang xử lý. Lease của đúng job tổng hợp được đặt hết hạn sau kill để rút ngắn chờ 300 giây; sau đó production worker nhận lại qua cơ chế lease thật. Không sửa dữ liệu nghiệp vụ hoặc xóa volume.

Benchmark hẹp trên Windows/Ryzen 5 7535HS/16 GB, hai Polars threads, ba lượt/cỡ: 1k/10k/50k CSV hai cột; ở 50k, parse p50 57,87 ms, profile 65,14 ms, normalize+write 1.228,25 ms, peak process 172,71 MiB. Không gọi AI. Đây không phải cam kết latency/throughput hoặc benchmark dữ liệu đại diện; p95/scope đầy đủ trong hướng dẫn kiểm thử.

Screenshots chỉ chứa dữ liệu tổng hợp, lưu tại `runtime/screenshots` và bị Git ignore. Đã xem Dashboard/Mapping, desktop/tablet/mobile; chưa tuyên bố audit toàn bộ WCAG 2.2 AA.

## E. Docker và lưu trữ

Project duy nhất: `ai-reconciliation-studio`.

| Service | Image | Trạng thái kiểm tra | Host port |
|---|---|---|---|
| frontend | ai-reconciliation-studio-frontend:local | healthy | 127.0.0.1:18180 |
| backend | ai-reconciliation-studio-backend:local | healthy | không publish |
| worker | dùng chung backend image | healthy; recovery đạt | không publish |
| postgres | postgres:18.3-alpine | healthy | chỉ network nội bộ |

`docker image ls` báo SIZE khoảng **553 MB backend/worker**, **90,5 MB frontend**, **409 MB PostgreSQL**; đây là số đo theo cột SIZE của Docker, không cộng backend/worker thành hai image riêng. PostgreSQL/artifact volumes được giữ nguyên. Kiểm tra sau fault test thấy artifacts khoảng 7,6 MiB, PostgreSQL khoảng 65,8 MiB và ổ C còn khoảng 129 GiB; số này thay đổi khi thêm dữ liệu.

Named volumes: `ai-reconciliation-studio_postgres_data`, `ai-reconciliation-studio_artifacts`. Không dùng global prune hoặc xóa volumes. Không có dangling image cũ có label project được xác minh để dọn; không xóa cache/images không rõ sở hữu. Tooling `/tmp` phục vụ tests được loại bỏ khi recreate container; runtime evidence được giữ ngoài Git.

## F. Git/GitHub

- Remote chính thức: `https://github.com/MinhHoang1403/AI-Reconciliation-Studio.git`.
- Nhánh triển khai: `codex/data-foundation`; không có repo/worktree phụ.
- Commit nền tảng đã push: `be3071e3e71fa1362a7615e59595a4f96180c800` — `feat: establish typed data contracts and immutable parsing pipeline`.
- Nhóm runtime/UI/acceptance được commit/push sau rà diff/tests/secrets; hash và đối chiếu remote được chốt trong cập nhật bàn giao tiếp theo.
- `main` được giữ nguyên vì gate Qwen live chưa đạt; không force-push/reset phá hủy.
- `.vscode/` xuất hiện ngoài phạm vi triển khai, được giữ nguyên và không stage/commit. `.env`, uploads, Parquet, volumes, screenshots và runtime reports không vào Git.

## G. Mức nghiệm thu và giới hạn

| MUST gate | Trạng thái |
|---|---|
| Một Compose project, FE/BE/worker/PostgreSQL và healthchecks | PASS |
| CSV/XLSX security → parse/profile → approved mapping → canonical preview | PASS |
| Provenance, Decimal, invalid/null/zero, revisions và scoped reuse | PASS |
| Typed handoff/API, permission/CSRF/workspace isolation | PASS |
| Gemini/LlamaParse adapter contracts và cloud OFF | PASS CONTRACT |
| UI trực tiếp local, responsive, không KPI hoặc AI success giả | PASS |
| Persistence và worker recovery | PASS |
| Ít nhất một mapping Qwen live hợp lệ | **BLOCKED** |
| PDF/DOCX cloud live, mapping accuracy đại diện, production/public deployment | NOT VERIFIED; không được tuyên bố đã hỗ trợ/nghiệm thu live |
| Nghiệm thu Giai đoạn 1 và chuyển Giai đoạn 2 | **BLOCKED bởi Qwen live** |

Giới hạn cụ thể: một sheet là một table candidate; nhiều vùng bảng cùng sheet, formula cache, merged cells và Excel date serial cần review. Không chạy công thức Excel/OCR để tự chữa số. Date conversion dùng format không mang offset sẵn và timezone IANA được xác nhận; trường hợp chưa hỗ trợ được giữ raw/cần kiểm tra. Các rule enum/coalesce/arithmetic/grouping nâng cao có typed API, chưa có UI rule builder. Benchmark không bao phủ 100k/wide workbooks hoặc mọi nguồn. Backup/restore thảm họa và public production deployment chưa nằm trong phần đã kiểm chứng; Git không thay backup volumes.

## H. Sử dụng và việc còn lại

Mở [http://127.0.0.1:18180](http://127.0.0.1:18180). Chọn/tạo project → Tải CSV/XLSX → chọn sheet → AI Smart Setup → xác nhận schema/grain/locale/metric/currency → Xác nhận ánh xạ → Chuẩn hóa → Cập nhật kết quả → xem canonical/errors/nguồn. Dataset lỗi vẫn giữ raw và hiện rõ cần kiểm tra.

Khởi động/mở lại bằng `./tools/start.ps1 -SkipBuild`; build mới dùng `./tools/start.ps1`. Không nhập token trong UI. Các dự án dữ liệu tổng hợp từ kiểm thử được giữ lại để xem thử; có thể tạo dự án riêng cho dữ liệu thực.

Để mở gate còn lại: cấp quyền truy cập endpoint Qwen cho máy hiện tại, chạy `uv run python tools/probe-qwen.py`, xác minh request/response thật và mapping theo oracle, rồi replay tests/E2E tương ứng. Chỉ khi MUST gates đạt mới tích hợp main và bàn giao Giai đoạn 2. Không tự bật Gemini/LlamaParse hoặc xây matching engine để vượt blocker.
