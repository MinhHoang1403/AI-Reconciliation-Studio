# Hướng dẫn kiểm thử

Chạy từ repository root. Các lệnh bên dưới không tạo Compose project hoặc database server thứ hai. Chỉ dùng fixtures tổng hợp; không sửa hoặc xóa dữ liệu dự án khác.

## Backend offline

```powershell
uv sync --frozen
uv run pytest -q -m 'not integration'
uv run ruff check backend tests tools
uv run mypy backend/studio
```

Ngày 28/10/2026: 77 tests offline PASS tại lần kiểm tra gần nhất; Ruff/mypy PASS. Có một cảnh báo deprecation từ Starlette về TestClient/httpx; không phải lỗi ứng dụng. Chưa chuyển test client transport trong đợt này vì contract tests hiện chạy đúng với lock đã chọn.

| Catalogue | Bằng chứng thực thi |
|---|---|
| T01 | size, extension/MIME/signature, archive/XML entity và tên path không hợp lệ bị từ chối |
| T02 | hash/raw bytes không đổi; integration kiểm tra upload scoped dedup và project khác không reuse dataset |
| T03 | route document/cloud OFF và mock transport khẳng định 0 HTTP cloud calls |
| T04 | XLSX nhiều sheet, header lệch, sheet ẩn và physical source rows |
| T05 | text/numeric zero-format `000123`; document adapter luôn UNVERIFIED_EXTRACTION. OCR live chưa kiểm tra |
| T06 | giữ formula/cache metadata và warning, không tính lại công thức hoặc sửa cache |
| T07 | null/empty/distinct/key candidates đúng fixture độc lập; số `0.00` không bị nhận nhầm thành ID |
| T08 | alias tên Việt/Anh → shortlist field IDs thật, chưa tự approve |
| T09 | Qwen malformed JSON, HTTP/timeout, bounded retries, classification/grain/mapping/transformation tasks qua mock |
| T10 | Total mơ hồ, UNKNOWN/AMBIGUOUS giữ review; currency/metric thiếu hoặc UNKNOWN không được approve |
| T11 | type/transform/rule chưa duyệt bị chặn |
| T12 | PostgreSQL viewer approve → 403, có audit denial |
| T13 | approval mới tạo revision, canonical cũ stale, raw/parsed refs/hash giữ nguyên |
| T14 | discriminated DSL từ chối exec/eval/SQL và extra params; không chạy mã AI |
| T15 | `1.234,50` → Decimal `1234.50` dưới locale đã duyệt; zero/negative/exponent/precision và property tests |
| T16 | raw invalid/null/zero tách riêng, error artifact, không mất dòng, Parquet roundtrip và lineage |
| T36/T37 | cloud OFF, hallucinated evidence, AI không được tự APPROVED |

Operator tests bao phủ trim được duyệt, enum, coalesce phân biệt null/empty, arithmetic có rule/semantics, date timezone/DST, grouping signed Decimal và đầy đủ lineage. Đây là dữ liệu tổng hợp có oracle, không phải đánh giá precision/recall mapping trên dữ liệu đại diện.

## PostgreSQL và worker

```powershell
./tools/test-postgres.ps1
./tools/test-postgres.ps1 -All
```

Script copy tests vào `/tmp` của backend hiện có, cài test tooling tạm tại `/tmp/studio-checks` và chạy pytest. Mỗi test tạo schema `test_<UUID>`, chạy migration snapshot, dùng riêng metadata và storage temp, rồi drop đúng schema này. Bộ đầy đủ sau chuyển Gemini: **87 PASS (77 offline + 10 PostgreSQL integration), 0 FAIL/SKIP**. Worker production không thể claim jobs trong schema test. Hai test mới xác minh worker Gemini/usage/budget exhausted và đồng thời nhiều reservation trên hai workspace không vượt trần; transport đều mock, không dùng quota thật.

Kiểm tra pipeline/ref/policy, migrations, same-key enqueue, scoped reuse/template proposal, viewer/CSRF/host/workspace isolation, `SKIP LOCKED`, expired lease fencing, attempts/recovery, parse failure và crash trước publish canonical. Snapshot DDL không phụ thuộc ORM của migration tương lai. Destructive downgrade bị chặn.

Test harness không đưa secret vào output. Nếu không thể tạo schema an toàn, dừng và báo BLOCKED; không chuyển sang SQLite hoặc tạo Compose test project.

## Frontend và E2E

```powershell
npm --prefix frontend ci
npm --prefix frontend run check
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend run test:e2e
```

Playwright chạy trên Nginx production tại `127.0.0.1:18180`, một Chromium worker. Tạo dự án/file tổng hợp có scope riêng mỗi lần để không nhầm cache với live AI. Mặc định test mong Qwen đang bị chặn. Khi kiểm tra Gemini live phải chỉ định explicit trước khi chạy:

```powershell
$env:STUDIO_EXPECT_AI_PROVIDER='GEMINI'
npm --prefix frontend run test:e2e
```

Chế độ này có thể tiêu thụ tối đa hai HTTP attempts cho một bảng tổng hợp, vẫn chịu trần global/workspace; test kiểm tra provider trước khi upload để không gọi cloud nhầm chế độ. Chờ job Gemini SUCCEEDED, kiểm tra source GEMINI, reference mapping theo oracle độc lập và chưa AI tự duyệt rồi thực hiện luồng review/normalization. Lần cuối **8 PASS, 0 FAIL (19,8 giây)**. Regression xác minh refresh cùng revision giữ draft/grain/locale; test đợi refresh nhận proposal mới hoàn tất trước khi nhập. Không hạ validator để làm test PASS. Provider failure/cloud OFF tiếp tục được kiểm tra bằng mock.

Kịch bản: tạo project → upload → xem `000123` → xác nhận metric/locale/currency → approve → normalize → canonical/errors → evidence. Người quay lại thấy mapping/artifacts. Session HttpOnly/SameSite, CSRF và Host spoof rejection, 0 external browser requests được kiểm tra. Regression trì hoãn request tìm kiếm xác nhận UI không trình bày preview cũ dưới query/phiên bản mới.

Responsive: 1440×900, 1920×1080, 1366×768, 768×1024 và 390×844; chờ nội dung thực trước khi kiểm tra overflow, chụp Dashboard/Mapping và mở/đóng upload modal bằng Escape. Screenshots chỉ có dữ liệu tổng hợp, lưu ở `runtime/screenshots` bị Git ignore. Kiểm tra tự động và xem ảnh chưa tương đương audit toàn bộ WCAG 2.2 AA.

## Persistence và deployment

```powershell
./tools/check-persistence.ps1
```

Đợi hết jobs đang chạy. Công cụ snapshot metadata/approvals/canonical refs và kiểm tra SHA256 từng artifact, restart rồi force-recreate đủ bốn service và recreate riêng frontend trong project hiện tại, xác nhận auto-session bị chặn trước re-verification và so lại dữ liệu. Bao gồm workspace policy và audit reservations của Gemini; quota không được reset. Không xóa volumes hoặc raw. Snapshot kiểm tra nằm trong volume, không vào Git. Bộ backend đầy đủ hiện đạt 87 PASS (77 offline + 10 PostgreSQL integration).

## Worker bị dừng đột ngột

```powershell
uv run python tools/check-worker-recovery.py
```

Đã chạy SIGKILL thật khi worker chuẩn hóa 75.000 dòng tổng hợp, sau khi xác minh không có job khác đang xử lý. Job riêng của phép thử được đặt lease hết hạn ngay sau kill để không phải chờ 300 giây; worker được khởi động lại bằng Compose hiện tại. Kết quả: hai attempts, đúng một canonical được công bố, đủ 75.000 dòng, raw hash và parsed ref giữ nguyên. Không xóa dữ liệu hoặc dừng container dự án khác. Dự án tổng hợp được giữ lại làm bằng chứng.

## Benchmark cục bộ

```powershell
uv run python tools/benchmark-foundation.py
```

Đã đo trên Windows/Ryzen 5 7535HS, 16 GB RAM, Python 3.12.14, hai Polars threads; không dùng GPU. Mỗi cỡ chạy ba subprocess mới, CSV hai cột tổng hợp, mỗi 1.000 dòng có một invalid amount. Không gọi AI. Kết quả đo trong phiên nghiệm thu:

| Dòng | Parse p50 / p95 ms | Profile p50 / p95 ms | Normalize + write p50 / p95 ms | Peak process MiB |
|---:|---:|---:|---:|---:|
| 1.000 | 22,53 / 96,36 | 2,93 / 16,26 | 38,36 / 81,17 | 77,59 |
| 10.000 | 35,00 / 36,93 | 14,13 / 14,89 | 232,91 / 234,77 | 92,84 |
| 50.000 | 57,87 / 58,77 | 65,14 / 65,28 | 1.228,25 / 1.420,63 | 172,71 |

p95 là nội suy inclusive trên ba quan sát, không phải cam kết tail latency. Đây là benchmark cục bộ hẹp, không đo SQL/API/network/browser, mapping AI, workload nhiều cột, 100k dòng hoặc matching. Artifact đo chi tiết ở `runtime/benchmarks.json`, không commit runtime data. Không tuyên bố mapping precision ≥98% hoặc khả năng xử lý mọi file từ các số đo này.

## Qwen live và kiểm tra source

```powershell
uv run python tools/probe-qwen.py
uv run python tools/check_repository.py
git diff --check
```

Probe chỉ gửi profile tổng hợp và kiểm tra mapping với oracle mã tham chiếu độc lập. Hiện HTTP 403 từ Qwen là **BLOCKED**, không phải PASS inference. Chủ dự án đã cấp quyền dùng Gemini tạm thời; LlamaParse vẫn chưa được gọi live. Live Gemini đầu tiên bị chặn vì model dùng tên thay ID nguồn, không tự retry semantic error. Prompt revision `schema-understanding-2` làm rõ ID; regression giữ nguyên việc từ chối tên cột. Lần mới đã qua validator và oracle reference_id; số reservation gồm cả attempts lỗi/chẩn đoán, không chỉ successful traces.

Repository checker rà known local credentials trong source candidates/Git history, các pattern secret phổ biến, runtime/binary candidates và đường dẫn Markdown. Kết hợp rà nội dung/diff trước public push; đây không phải bảo đảm đã audit mọi kiểu secret hoặc toàn bộ bảo mật hệ thống.
