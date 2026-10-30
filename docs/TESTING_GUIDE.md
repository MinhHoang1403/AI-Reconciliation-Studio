# Hướng dẫn kiểm thử

Chạy từ repository root. Các lệnh bên dưới không tạo Compose project hoặc database server thứ hai. Chỉ dùng fixtures tổng hợp; không sửa hoặc xóa dữ liệu dự án khác.

Đợt Final UX hardening ngày **30/10/2026** có [inventory và bằng chứng ở mục N](IMPLEMENTATION_STATUS.md#n-final-ux-hardening--phân-loại-project-và-dữ-liệu-gần-đây): **149 backend PASS (120 offline+29PG), 41 E2E MANUAL PASS (9foundation+25interface+7reconciliation), 0 FAIL/SKIP**. Ruff/mypy28/TypeScript/ESLint/build PASS. Full backend38,26s; full browser~1,4phút. Sau khi làm chặt assertion chờ nội dung Dashboard trước screenshot, replay foundation9PASS/31,1s trên image8789940; catalogue vẫn41. Regression mới: phân loại owner/viewer/editor/scope/conflict/concurrent writes, UNKNOWN visible và filter-before-pagination; recent5/30/80nguồn độc lập page2, refresh nguồn mới, delayed/error/retry/project switching; giữ draft khi đổi nhóm và khi rời selector đang lưu. Không cộng replay vào số cases.

Foundation E2E mặc địnhMANUAL tìm lại một project TEST theo exactname/scope, tạo TEST explicit qua API nếu chưa có; bộ chọn thật bật toggle để chọn project này. Tạo project WORK qua UI có browsercontract regression riêng và API PG authorization/default test. Các helper document/reconciliation/recovery cũng khai báo TEST khi tạo mới; không gọi các helper live trong đợt regression này. Chỉ đo retention/delta, không xóa project/artifacts lịch sử hoặc thêm cleanup job.

Quality hardening trước đó ngày 29–30/10/2026 trên `codex/interface-quality`: xem [mục M](IMPLEMENTATION_STATUS.md#m-hoàn-thiện-frontend-và-ux-giai-đoạn-12). Kết quả lịch sử: **145 backend PASS (120offline+25PG), 34 E2E MANUAL PASS (9foundation+18interface+7reconciliation), 0 FAIL/SKIP**; Ruff/mypy31/TypeScript/ESLint/build PASS. Full backend44,02s; full browser ~1,2phút trên image sourceac44915. Baseline143/15 tăng2PG+19browser cases; không cộng replays thành cases mới. Những số liệu bên dưới thuộc các mốc lịch sử.

Bằng chứng Final Acceptance lịch sử ngày **29/10/2026** ở [mục L của báo cáo](IMPLEMENTATION_STATUS.md#l-final-acceptance-hợp-nhất-và-vận-hành--29102026): 120 offline/143 tổng backend và 15 E2E MANUAL PASS, không cloud. T35 hiện xuất cả CSV/XLSX qua UI, đợi đúng export URL của từng format, kiểm SHA256/timestamp và lưu downloads/snapshot dưới runtime để đọc lại. Không đổi oracle hoặc timeout. Những số 91/9 ở phần nền tảng bên dưới là lịch sử Giai đoạn 1.

UI regressions mới dùng control hiển thị thật, không hidden select. Search/restore/race/counts/polling và next action có cả PostgreSQL scoped tests lẫn browser mocked GET fixtures; Planner UI là MOCK. Năm responsive cases đo bounds dialog/focus outline và4mẫu contrast từ computed colors, kiểm keyboard/Enter/Escape/focus-return/mobile drawer. Không suy rộng thành toàn bộ WCAG/screen-reader PASS. Tất cả cases kiểm0uncaught pageerrors; luồng foundation/T35 thành công còn kiểm0console errors. Delayed evidence regression giữ đúng run/project. Các lỗi503/auth mock được kiểm bằng thông báo thật.

Đối chiếu runtime/source khi release: từ tracked application source sạch, đặt build-only `$env:BUILDX_GIT_LABELS='full'` rồi `docker compose build backend frontend`, kiểm OCI revision/source của images trước `up`, `tools/verify-local.ps1` và so source/served assets SHA256. Label base image Nginx không phải revision của ứng dụng; cached Created timestamp không chứng minh commit. Không cần thêm biến runtime, service hoặc thay Dockerfile.

Final Acceptance theo phạm vi mới ngày 28/10/2026 đã chạy lại: **91 backend PASS, 0 FAIL/SKIP** (79 offline + 12 PostgreSQL), Ruff/mypy và frontend TypeScript/lint/build PASS, **9 E2E MANUAL PASS, 0 FAIL/SKIP trong 19,6 giây**. T01–T16 và security nằm trong các suite này, không cộng thêm vào tổng. Baseline 87 backend/8 E2E tăng do bốn backend regression và một case document cached. Gemini live 9 E2E PASS là bằng chứng của lần chạy trước chỉ dẫn thu hẹp; không gọi lại cloud ở lượt này, quota vẫn 6/10. LlamaParse đọc lại hai kết quả live đã lưu, không tạo job mới. Chỉ nghiệm thu Giai đoạn 1, chờ prompt riêng trước Giai đoạn 2.

## Backend offline

```powershell
uv sync --frozen
uv run pytest -q -m 'not integration'
uv run ruff check backend tests tools
uv run mypy backend/studio
```

Ngày 28/10/2026: **79 tests offline PASS**, 12 integration deselected; Ruff/mypy PASS. Có một cảnh báo deprecation từ Starlette về TestClient/httpx; không phải lỗi ứng dụng. Chưa chuyển test client transport trong đợt này vì contract tests hiện chạy đúng với lock đã chọn.

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

Script copy tests vào `/tmp` của backend hiện có, cài test tooling tạm tại `/tmp/studio-checks` và chạy pytest. Mỗi test tạo schema `test_<UUID>`, chạy migration snapshot, dùng riêng metadata và storage temp, rồi drop đúng schema này. Bộ đầy đủ hiện đạt **91 PASS (79 offline + 12 PostgreSQL integration), 0 FAIL/SKIP**. Worker production không thể claim jobs trong schema test. Kiểm tra Gemini concurrency/quota và document reservation/artifact/reuse sau thu hồi quyền; transport đều mock. Upload explicit manual không enqueue AI hoặc tiêu quota.

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

Playwright chạy trên Nginx production tại `127.0.0.1:18180`, một Chromium worker. Foundation reuse đúng một project có tên/scope E2E rõ ràng theo provider mode; nếu không có mới tạo qua UI, nhiều matches thì dừng. Mỗi run dùng CSV bytes/filename mới với UUID ở một ID tổng hợp không thuộc oracle tiền; giữ các mẫu zero-prefix/invalid/null/zero và đáp án cũ. Không approve lại table cũ, không invalidate artifact lịch sử. Không xóa project/dữ liệu cũ, không thêm delete API. Project count được kiểm trước/sau lần replay để chứng minh không tăng tiếp; artifacts/jobs tổng hợp vẫn tăng có chủ đích, cần chủ dự án quyết định retention về sau. UI contract tests search120projects/80datasets chỉ intercept GET và không tạo dữ liệu production. Mặc định MANUAL bỏ chọn yêu cầu AI, không gọi Gemini/Qwen; có thể đặt `STUDIO_EXPECT_AI_PROVIDER=MANUAL` explicit. Khi kiểm tra Gemini live phải chỉ định explicit trước khi chạy:

```powershell
$env:STUDIO_EXPECT_AI_PROVIDER='GEMINI'
npm --prefix frontend run test:e2e
```

Chế độ này có thể tiêu thụ tối đa hai HTTP attempts cho một bảng tổng hợp, vẫn chịu trần global/workspace; test kiểm tra provider trước khi upload để không gọi cloud nhầm chế độ. Chờ job Gemini SUCCEEDED, kiểm tra source GEMINI, reference mapping theo oracle độc lập và chưa AI tự duyệt rồi thực hiện luồng review/normalization. Nghiệm thu lại: **9 PASS ở Gemini LIVE (20,3 giây)** và **9 PASS ở MANUAL (16,2 giây)**, không cộng thành 18 case khác nhau. Regression xác minh refresh cùng revision giữ draft/grain/locale. Case document đọc hai artifact cached khi quyền parser đã đóng, kiểm tra IDs/amounts, không có nút normalize và không overflow ở mobile. Không hạ validator để làm test PASS. Provider failure/cloud OFF tiếp tục được kiểm tra bằng mock.

Các thời gian 20,3/16,2 giây là lần chạy trước chỉ dẫn thu hẹp. Lần chạy lại cuối cùng chỉ MANUAL, 9 PASS/19,6 giây. Trước HTTP/E2E, dùng `./tools/verify-local.ps1` khi proof local không hợp lệ; 403 trước xác minh là fail-closed theo thiết kế, không tắt auth để chạy tests.

Kịch bản: tạo project → upload → xem `000123` → xác nhận metric/locale/currency → approve → normalize → canonical/errors → evidence. Người quay lại thấy mapping/artifacts. Session HttpOnly/SameSite, CSRF và Host spoof rejection, 0 external browser requests được kiểm tra. Regression trì hoãn request tìm kiếm xác nhận UI không trình bày preview cũ dưới query/phiên bản mới.

Responsive: 1440×900, 1920×1080, 1366×768, 768×1024 và 390×844; chờ nội dung thực trước khi kiểm tra overflow, chụp Dashboard/Mapping và mở/đóng upload modal bằng Escape. Screenshots chỉ có dữ liệu tổng hợp, lưu ở `runtime/screenshots` bị Git ignore. Kiểm tra tự động và xem ảnh chưa tương đương audit toàn bộ WCAG 2.2 AA.

## Persistence và deployment

```powershell
./tools/check-persistence.ps1
```

Đợi hết jobs đang chạy. Công cụ snapshot metadata/approvals/canonical refs và kiểm tra SHA256 từng artifact, restart rồi force-recreate đủ bốn service và recreate riêng frontend trong project hiện tại, xác nhận auto-session bị chặn trước re-verification và so lại dữ liệu. Bao gồm workspace policy, reservations, document JSON và raw/Parquet; quota không reset. Không xóa volumes hoặc raw. Snapshot kiểm tra nằm trong volume, không vào Git. Snapshot nghiệm thu lại gồm 17 datasets, 12 canonical, 42 jobs/45 attempts và 58 artifact refs.

Snapshot lần Final Acceptance cuối: 19 datasets/versions, 14 canonical, 46 jobs/50 attempts, 48 audits, 15 traces và 66 artifact refs. Metadata/checksums và quyền parser OFF giữ nguyên sau cả ba kiểu restart/recreate; chỉ dùng project Compose hiện có. Các số 17/12/42/45/58 phía trên là mốc trước khi tạo thêm fixtures E2E/recovery, không phải dữ liệu bị thay thế hoặc mất.

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
uv run python tools/check_repository.py
git diff --check
```

Qwen được hoãn chính thức: `BLOCKED_EXTERNAL_DEPENDENCY — IP allowlist`, không probe lại trong nhiệm vụ này. Tool probe vẫn được giữ cho khi chủ dự án cấp quyền sau. Gemini mapping live và oracle đã PASS, prompt `schema-understanding-2` giữ nguyên. Sau nghiệm thu lại dùng 6/10 requests, còn 4; không reset/tăng để chạy tiếp.

## LlamaParse live có allowance riêng

Đã kiểm tra đúng một PDF và một DOCX tổng hợp, mỗi tài liệu 1 trang/3 credits, tổng 2 trang/6 credits. Raw ID/amount/date/blank cells khớp oracle literal trong `tools/check-document-acceptance.py`; HTML table và Markdown table chỉ là hai cách biểu diễn cells, không tự sửa số. Tier cost_effective, server cap 2 trang/job, two-SHA allowlist, durable reservations: tối đa 2 docs/4 trang/12 credits theo giá đã xác minh, không vượt 20 được cấp. Trước thử API account xác nhận credits đủ; không dùng POST để thăm dò.

Lỗi thật được giữ regression: upstream job ID là opaque `pjb-*`, không bắt buộc UUID. PDF đã được nhận, được tìm lại receipt duy nhất rồi resume GET, không POST lại; attempt lỗi và reservation cũ vẫn còn. Sau thử đã thu hồi quyền tạo job toàn hệ thống/workspace, giữ key/history/artifacts. Chạy lại `uv run python tools/check-document-acceptance.py` hiện chỉ đọc cached refs; không tự mở allowance. Parser contracts có success/error/cloud OFF, page cap, resume không reserve/POST và prefixed ID.

PDF fixture đã render/kiểm tra hình ảnh. Renderer DOCX bundled trên Windows thiếu LibreOffice, nên không tuyên bố visual QA Word local; nội dung và số trang đã kiểm tra bằng kết quả provider có page cap và oracle, cùng UI cached. Hai fixtures là dữ liệu kiểm thử, không phải tuyên bố OCR tài chính đại diện hoặc artifact đã READY. UI không thực thi provider HTML và không tự normalize document.

Repository checker rà known local credentials trong source candidates/Git history, các pattern secret phổ biến, runtime/binary candidates và đường dẫn Markdown. Kết hợp rà nội dung/diff trước public push; đây không phải bảo đảm đã audit mọi kiểu secret hoặc toàn bộ bảo mật hệ thống.

## Reconciliation acceptance

Các mốc số liệu ở phần trên là lịch sử Giai đoạn 1. Suite hiện thêm contracts/golden/property/reporting và PostgreSQL tests. `tools/test-postgres.ps1` làm mới đúng `/tmp/studio-tests` trước copy để không tạo `tests/tests` rồi chạy nhầm bản cũ; chỉ xóa cây source test tạm cố định trong backend, không chạm volume/storage. Bản pytest/hypothesis tạm dùng chung container, không tạo server/Compose test khác.

```powershell
uv run pytest -q -m 'not integration'
./tools/test-postgres.ps1 -All
uv run ruff check backend tests tools
uv run mypy backend/studio
npm --prefix frontend run check
npm --prefix frontend run lint
npm --prefix frontend run build
$env:STUDIO_EXPECT_AI_PROVIDER='MANUAL'
uv run python tools/check-reconciliation.py
npm --prefix frontend run test:e2e
./tools/check-persistence.ps1
uv run python tools/benchmark-reconciliation.py
uv run python tools/check_repository.py
```

| Golden catalogue | Evidence |
|---|---|
| T17–T20 | Invented source/field/evidence/AI APPROVED rejected; gross/net/stale/wrong scope/expired dates/cardinality blocked; incomplete coverage explicit partial; unapproved ID cannot execute |
| T21–T24 | Manual oracle Internal/Shopee partition 11 = 1 invalid + 5 outside + 5 inside; zero-prefix/composite linkage; duplicate reviews; same ID amount diff LINKED/AMOUNT_MISMATCH |
| T25–T26 | TikTok 1:N 20+30=50 with both members; inverse N:1; mixed currency NOT_COMPARABLE, no delta; signed refund retained |
| T27–T28 | Near rigid IDs not auto-fuzzy; approved text blocking, bounded score/top-k, all ties/competing edges review-only; four synthetic admissible labelled pairs retained (not a representative blocking recall benchmark) |
| T29–T30 | Exact/within/beyond boundary; null versus real zero; no null/invalid coercion; explicit date cutoff/coverage/due date |
| T31–T33 | Corrupt amount or reused membership fails independent verifier; fault after draft write leaves no official metrics; retry publishes one logical run; failed verification has no metrics/exports |
| T34–T35 | Zero denominator N/A; manual count/Decimal oracle; immutable snapshot identical API/CSV/XLSX; UI uses DTO; review leaves original snapshot equal; formula injection, numeric negatives, exact XML values, IDs checked by opening outputs |

PostgreSQL migration test first creates approved canonical with historical migration, then upgrades head and compares artifact DTO/preview/counts; stale source/viewer/cross-project evidence/foreign group rejected. Template reuse returns PROPOSED with no contract ID and requires fresh approval. Existing Giai đoạn 1 tests remain in the same suite.

Playwright adds manual rule builder → validate → save → approve → run → verified dashboard → exception evidence/review → XLSX download → reload/run selection, plus result layouts 390/768/1366/1920; combined with prior 1440 and Giai đoạn 1 flow. Screenshots wait for real detail rows, not loading placeholders. It never presses paid planner. Backend/API demo covers upload/manual mapping/normalization for all five labelled source files.

Benchmark measures simple exact match on **total input records across both sources**: 1k (500/source), 10k (5k/source), 50k (25k/source), three new Windows processes/size. Matching p50/p95 ms: 31,57/37,58; 268,01/433,78; 1723,77/1792,43. Verification p50/p95: 17,06/19,02; 230,28/257,09; 1315,23/1521,31. Peak process MiB: 38,68 / 89,10 / 317,06. 500/5k/25k exact groups, zero fuzzy/review/cloud. Ryzen 5 7535HS/16 GB, no GPU. Excludes API/network/load/write/export/render and snapshot's additional verification pass; p95 is inclusive interpolation over 3 observations. Not a calibrated accuracy/throughput claim or 50k rows per source.

Actual final PASS/FAIL/SKIP and persistent object counts are recorded in [implementation status](IMPLEMENTATION_STATUS.md); do not add historical/live/mock replays into one inflated test count.

## Kiểm toán bổ sung Giai đoạn 2 — 28/10/2026

Giữ nguyên oracle và matcher/verifier. Thêm regression vào các suite có sẵn:

- Planner: request không join keys, schema khác field IDs, typed suggestions khi thiếu coverage; giả field/evidence/basis/cardinality hoặc đổi facts đã xác nhận bị từ chối. Context sai refs/workspace/stale bị chặn trước reservation. PostgreSQL quota hết dùng MockTransport, xác nhận 0 provider calls và manual proposal vẫn hoạt động; không thêm reservation trong ứng dụng thật.
- Readiness: cùng ID hai tháng không trùng trong kỳ; duplicate thật trong kỳ, filter carrier/platform, missing date/invalid key và incomplete coverage. Đối chiếu cùng định nghĩa partition của engine, không sửa verifier.
- Evidence: workbook tổng hợp nhiều sheet, ID ở c1/tiền ở c3/zero-prefix; 1:N nhiều source members mở đúng ô của từng dòng. Viewer đọc được, không review; group project khác bị từ chối. Playwright bấm trường tiền thật và kiểm raw value/cột thực tế c4 của CSV demo, không hardcode c1.
- KPI: giữ numerator/denominator cũ; oracle 5 eligible CU, 2 full match, 4 automatically classified, 1 review. RESOLVED không đổi comparison/snapshot.
- Export CSV/XLSX: export trước review → RESOLVED → export lại cùng revision phải cùng export ID/bytes. Summary/API timestamp và FIRST_GENERATION scope khớp; financial snapshot vẫn nguyên. Report-1 lịch sử giữ nguyên.
- UI: period/timezone ban đầu trống, cần scope confirmation; Planner có thể hỏi trước keys, hiển thị review-only suggestions/lý do và chặn approve; provider budget error vẫn mở chỉnh thủ công. Planner E2E mới intercept endpoints hoàn toàn, **PASS MOCK**, không gọi Gemini.

Lệnh chuẩn ở trên chạy cùng Docker project. Sau recreate phải chạy `tools/verify-local.ps1`; nếu proof bị mất trong phiên gián đoạn, UI bị chặn LOCAL_DEMO_NOT_VERIFIED là fail-closed đúng thiết kế, cần xác minh deployment rồi chạy lại E2E. Không bỏ kiểm tra auth hoặc tăng timeout để che lỗi.

So sánh baseline 121 backend/14 E2E với kết quả thật ở mục K của báo cáo; không cộng các lần replay hoặc PASS LIVE lịch sử vào số cases hiện tại. Prompt planner sửa đổi chưa test live theo chỉ định 0 cloud requests.
