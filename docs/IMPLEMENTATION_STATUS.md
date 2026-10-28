# Trạng thái triển khai và nghiệm thu

**Hiện tại:** Giai đoạn 1 đã hợp nhất/tag; Giai đoạn 2 đã triển khai trên `codex/reconciliation-engine`, báo cáo ở mục J. Các mục A–I giữ lịch sử nghiệm thu nền tảng, không dùng quota/counts cũ làm số hiện tại.

## Final Acceptance — Giai đoạn 1 (lịch sử)

Ngày kiểm tra: **28/10/2026**. Phạm vi: Data Foundation + AI Smart Setup + UI cơ sở.

**GIAI ĐOẠN 1 ĐẠT NGHIỆM THU — QWEN LIVE ĐƯỢC HOÃN THEO CHỈ ĐỊNH**

Kết luận lịch sử theo chỉ dẫn thu hẹp phạm vi ngày 28/10/2026: chỉ nghiệm thu Data Foundation + AI Smart Setup. Gemini mặc định hiện tại, Qwen live được hoãn chính thức do IP allowlist. Các gate dữ liệu, bằng chứng Gemini mapping live, LlamaParse PDF/DOCX live, regression, bảo mật, worker recovery và persistence đã đạt trong phạm vi dưới đây. Không đổi lịch sử Qwen thành PASS hoặc mở rộng ngoại lệ sang gate khác. **Quyết định lúc đó: dừng sau báo cáo; không bắt đầu Giai đoạn 2 và không merge main trong lượt đó.** Ủy quyền tiếp theo được ghi tại mục I.

Sau khi nhận chỉ dẫn mới, đã gỡ đúng các thay đổi Giai đoạn 2 chưa commit: contract reconciliation, sáu fixtures/oracle và dependency DuckDB/RapidFuzz/ECharts; dependency/lockfiles trở lại nền Giai đoạn 1. Không có engine/planner/matcher, migration hoặc tính năng Giai đoạn 2 được commit hay triển khai. `.vscode/` của người dùng giữ nguyên.

## A. Kết quả và phạm vi sửa

Giữ nền tảng đã chạy: FastAPI/worker chung image, PostgreSQL metadata, React/Nginx, raw/Parquet bất biến, CSV/XLSX parser, profiling, mapping review/revisions, typed DSL/Decimal và canonical/errors/evidence. Không xây lại Data Foundation hoặc thay công thức.

Đợt này bổ sung Gemini mặc định với cloud OFF/budgets 0 cho cài mới; document adapter cost_effective/page cap/account preflight/two-SHA allowlist/durable reservation; lưu job ID để resume GET; document artifact scoped và preview file/trang/bảng. Extraction luôn UNVERIFIED_EXTRACTION, không tự tạo canonical. Upload explicit manual chỉ parse/profile/review, không enqueue AI hoặc tiêu quota.

Files chính: backend config/ai_gateway/document_parser/repository/worker/api/contracts; frontend/src và E2E; tests/test_ai.py, tests/test_postgres.py; tools/create-document-fixtures.py, tools/check-document-acceptance.py và worker recovery helper. Quyết định và hướng dẫn được cập nhật trong tài liệu hiện có, Rules/AGENTS giữ nguyên.

Các sửa code trên đã có trong commit nghiệm thu source. Lần Final Acceptance sau chỉ dẫn thu hẹp **không phát hiện lỗi code mới cần sửa**; diff bàn giao hiện chỉ gồm báo cáo, hướng dẫn kiểm thử, README và ghi nhận phạm vi mới trong kế hoạch.

## B. Kiến trúc và handoff

Một modular monolith, một Compose project. PostgreSQL giữ scope, session, revisions, approval, job/attempt, audit/trace. Volumes cũ giữ raw, Parquet, document JSON. Không tạo database/server/Compose test project khác.

Giữ CanonicalDataset, DatasetProfile, SchemaDefinition, MappingRevision, EvidenceRef, JobStatus, WorkspacePolicy và artifact refs/DTO/OpenAPI. Bổ sung additive parser_allowed_sha256 mặc định rỗng vào policy JSONB; policy cũ đọc qua defaults. **Không cần migration SQL mới**; Alembic vẫn create_data_foundation (head), không sửa canonical lịch sử.

API mới GET /api/datasets/{id}/documents chỉ đọc cached extraction có authorization/checksum. Upload thêm request_ai_mapping mặc định true; false là lựa chọn workflow, không đổi parse semantics/cache. Xem [hợp đồng](DATA_CONTRACTS.md), [kiến trúc](ARCHITECTURE.md).

## C. AI và ngân sách thực tế

| Gate | Kết quả | Bằng chứng và giới hạn |
|---|---|---|
| Gemini gemini-3.5-flash-lite | PASS LIVE đã ghi nhận | Production worker, Pydantic/semantic checks, c1 → reference_id, preserve string, không AI tự duyệt; lượt thu hẹp phạm vi đọc lại bằng chứng, không gọi mới |
| Gemini quota | 6/10 đã dùng, còn 4 | PostgreSQL reservations, không reset/tăng; gồm một live mapping mới trong đợt này |
| Qwen knowledge | BLOCKED LIVE / HOÃN theo chỉ định | HTTP 403, IP allowlist; adapter PASS MOCK, không probe lại, không ghi PASS LIVE |
| LlamaParse PDF | LIVE PARSE PASS / PARSE VALIDATION PASS / INTEGRATION PASS | 1 trang, 3 credits, 3 dòng/4 cột; ID/date/amount/blank khớp oracle |
| LlamaParse DOCX | LIVE PARSE PASS / PARSE VALIDATION PASS / INTEGRATION PASS | 1 trang, 3 credits; zero-prefix/comma-decimal/text khớp oracle |
| Document UI | PASS E2E | Chạy lại cached preview sau thu hồi quyền, cells đúng, không normalize, mobile không overflow |
| Parser tổng | 2 jobs / 2 trang / 6 credits | Cost_effective; reservations giữ biên trên 4 trang/12 credits, dưới trần được phép 20 |
| Sau thử | Parser tạo job OFF | Env và workspace đã thu hồi quyền; giữ key/history/reservations/artifacts; Gemini còn quyền trong quota cũ |

Account API trước thử xác nhận 9.980 credits và không pay-as-you-go/payment failure/usage alerts. Chỉ hai SHA256 fixtures tổng hợp được cấp phép, một PDF/một DOCX; server max_pages=2, không layout/form extras. [Giá](https://developers.llamaindex.ai/llamaparse/general/pricing/) và [REST contract](https://developers.llamaindex.ai/llamaparse/parse/guides/api-reference/) đã đối chiếu. Không dùng POST để thăm dò credits.

Phân biệt thời điểm: các lần gọi live trên đã thực hiện trước chỉ dẫn thu hẹp phạm vi trong cùng đợt nghiệm thu. Lượt Final Acceptance này chỉ đọc PostgreSQL và artifact cached, so checksum/oracle và chạy E2E MANUAL. **Không phát sinh request Gemini/LlamaParse mới**, không tìm key ở dự án khác, không reset hoặc tăng quota. Usage trace LlamaParse giữ 3 credits/tài liệu; parser creation OFF ở cả env và workspace. Số dư credits tài khoản hiện tại không truy vấn lại, không suy ra từ số dư trước thử.

Lỗi thật đã sửa và giữ bằng chứng: upstream ID pjb-* không phải UUID. PDF đã được nhận trước khi adapter lỗi; xác minh receipt duy nhất theo tên/tier/thời điểm rồi resume GET, **không POST lại PDF**, giữ attempt lỗi/reservation. Reader nghiệm thu ban đầu chỉ đọc Markdown table; response là HTML table có đủ cells. Bổ sung reader cho cách biểu diễn HTML, giữ nguyên oracle/values, không chữa số hoặc ID. DOCX tạo đúng một job riêng.

28 AI/policy contract cases nằm trong 79 offline tests, không cộng thêm vào tổng backend. Không có precision/recall đại diện hoặc OCR accuracy tuyệt đối từ hai tài liệu. Xem [AI integration](AI_INTEGRATION.md).

## D. Kiểm thử đã thực thi

| Nhóm/lệnh | Kết quả cuối |
|---|---|
| uv run pytest -q -m 'not integration' | Chạy lại: 79 PASS, 12 deselected, 0 FAIL; 11,34 giây |
| tools/test-postgres.ps1 -All | Chạy lại: 91 PASS, 0 FAIL/SKIP; 79 offline + 12 PostgreSQL integration; 11,60 giây |
| Ruff / mypy | PASS; typed backend 18 source files |
| TypeScript / ESLint / production build | PASS |
| Playwright GEMINI | Bằng chứng live trước chỉ dẫn thu hẹp: 9 PASS, 0 FAIL (20,3 giây); không chạy lại để giữ quota |
| Playwright MANUAL | Chạy lại: 9 PASS, 0 FAIL/SKIP (19,6 giây), không gọi AI; cùng catalogue, không cộng thành 18 cases |
| Document acceptance | Hai live/oracle/artifact PASS; rerun sau thu hồi quyền chỉ đọc cached refs |
| Worker recovery live | SIGKILL trong normalization 75.000 dòng; 2 attempts, đúng 1 canonical, raw/parsed giữ nguyên |
| Restart / force-recreate / frontend-only recreate | PASS, metadata/checksum mọi artifact giữ nguyên; proof phải xác minh lại |
| Scope/security | HttpOnly/SameSite, CSRF/Host, viewer denial, workspace isolation, upload validation, cloud/allowance guards PASS |
| Source/Git scan | Known local credentials/history, Markdown paths và diff check PASS; runtime/secrets không stage |

Một cảnh báo Starlette TestClient/httpx deprecation vẫn còn. Fault test chỉ dừng worker project này khi không có job khác active; lease của đúng job tổng hợp được cho hết hạn để không chờ 300 giây. Không sửa dữ liệu nghiệp vụ hoặc xóa volume.

So baseline được giao **87 backend / 8 E2E PASS**, hiện có **91 backend / 9 E2E PASS**: thêm bốn backend cases bảo vệ resume parser/Gemini mặc định/document pipeline/manual upload và một E2E document cached; không xóa case cũ. T01–T16 đã chạy lại; xem [ma trận test–bằng chứng](TESTING_GUIDE.md). T09 và các provider error/timeout/injection là **PASS MOCK**, không phải Qwen live. Các integration cases có CSV/XLSX multi-upload, viewer denial, scoped reuse, revisions/stale canonical, lease/fencing và atomic publication.

Snapshot cuối: 19 datasets/versions, 17 source tables, 36 schema/mapping revisions, 14 canonical, 46 jobs/50 attempts, 48 audits, 15 traces, 66 artifact refs, 18 projects/1 workspace. Bao gồm document JSON, raw/Parquet và policy/reservations; giữ nguyên qua cả ba kiểu restart/recreate. Dữ liệu tổng hợp E2E/recovery mới được giữ làm bằng chứng, không xóa dữ liệu cũ.

Responsive 1366/1440/1920, 768, 390; screenshots tổng hợp ở runtime bị ignore. DOCX renderer bundled Windows thiếu LibreOffice: không tuyên bố visual QA Word local; số trang/nội dung xác minh bằng provider có page cap/oracle và UI cached. PDF fixture đã render/kiểm tra. Không tuyên bố audit toàn bộ WCAG 2.2 AA.

## E. Docker và dữ liệu

Project duy nhất ai-reconciliation-studio: frontend/Nginx, backend, worker, postgres, cả bốn healthy. Chỉ publish **127.0.0.1:18180**, backend/PostgreSQL không có host port.

Giữ volumes ai-reconciliation-studio_postgres_data và ai-reconciliation-studio_artifacts, rollback images cũ đã kiểm tra. Backend/worker chung image; Docker image disk usage khoảng 553 MB backend, 90,5 MB frontend, 409 MB PostgreSQL. Không tạo môi trường trùng, global prune hoặc xóa volumes. GitHub không thay backup dữ liệu; disaster recovery chưa được tuyên bố đã kiểm chứng.

Sau lần recreate cuối, RAM tại thời điểm đo: backend 91,23/384 MiB, worker 82,9/512 MiB, PostgreSQL 30,59/256 MiB, frontend 10,06/128 MiB. Ổ C còn 130,8 GiB; các tag rollback backend/frontend vẫn được giữ. Đây là snapshot nhàn rỗi, không phải peak benchmark.

## F. Git/GitHub

Repository chính thức https://github.com/MinhHoang1403/AI-Reconciliation-Studio.git. Nền tảng/Gemini trước ở commit 286c0802a2807bb11e53a89cff882217215b90fc. Source nghiệm thu ở **2e73cad7b7dc1fed5211e699b45b84d0ccbf5ea4**, đã push `codex/data-foundation`. **Trước khi nhận chỉ dẫn thu hẹp**, commit này đã được fast-forward vào main, rồi main có commit báo cáo **061c5558eda4228b430ea4d7ec8558731bf0616f**. Đây là lịch sử đã xảy ra, không phải thao tác merge của lượt Final Acceptance mới; không reset/force-push để thay lịch sử.

Lịch sử Final Acceptance thu hẹp: commit báo cáo 4bde2111e03cf438124a73fe0abe66bc4a46fcd5 trên codex/data-foundation, không merge main trong nhiệm vụ đó. Nhánh local `codex/reconciliation` đã tạo trước chỉ dẫn mới không có commit riêng, không push và không dùng tiếp; giữ nguyên để tránh thao tác Git ngoài yêu cầu.

.vscode/ có sẵn ngoài phạm vi, giữ nguyên và không stage. .env, keys, uploads, Parquet, document fixtures, screenshots, runtime reports và volumes không vào Git. Rules.md/AGENTS.md giữ nguyên; quyết định provider/ngoại lệ ghi trong kế hoạch, không thay nghiệp vụ.

## G. Quyết định nghiệm thu và ngoại lệ

| MUST gate đã điều chỉnh | Trạng thái |
|---|---|
| CSV/XLSX → parse/profile → reviewed mapping → canonical/errors/evidence | PASS |
| AI Schema Understanding, grain/field proposals | PASS MOCK cho classify/infer_grain/unknown/constraints; review schema/grain qua E2E; không tuyên bố precision đại diện |
| Gemini mapping LIVE, Pydantic/semantic checks/approval | PASS |
| LlamaParse PDF/DOCX live + oracle + provenance + bounded cost | PASS trong phạm vi hai fixtures |
| Decimal, invalid/null/zero, lineage/revisions/scoped reuse | PASS |
| Local access, workspace/role/CSRF/Host, secret scan | PASS |
| Worker recovery, persistence, Docker health, FE E2E | PASS |
| Qwen live gốc | HOÃN theo chủ dự án, không PASS LIVE |
| Giai đoạn 1 | GIAI ĐOẠN 1 ĐẠT NGHIỆM THU — QWEN LIVE ĐƯỢC HOÃN THEO CHỈ ĐỊNH |

Ngoại lệ chỉ cho Qwen: tiêu chí gốc yêu cầu một mapping Qwen live, endpoint bị IP allowlist chặn, chủ dự án chấp nhận Gemini thay thế. Rủi ro còn lại: Qwen inference protocol/generation chưa được xác nhận live. Chỉ kiểm tra lại sau khi chủ dự án cấp quyền, giữ contracts/validators. Không dùng ngoại lệ để bỏ gate khác.

Giới hạn/NOT VERIFIED: Qwen inference chưa live PASS; OCR ký tự gây nhầm chưa thử trên ảnh scan đại diện; visual QA Word local bị thiếu LibreOffice; precision/recall đại diện, audit WCAG đầy đủ, public production và disaster backup/restore chưa xác minh. Một sheet là một table candidate; workbook phức tạp/formula cache/date serial cần review; ngày dùng format không mang offset sẵn và timezone IANA được duyệt; advanced transformation rules có typed API nhưng chưa có UI builder. Document không tự normalize/đối soát. Benchmark cũ 1k/10k/50k là scope hẹp, không phải precision/throughput đại diện. Không ghi PASS cho những giới hạn này.

## H. Sử dụng và chuyển tiếp

Mở [ứng dụng local](http://127.0.0.1:18180). Tạo/chọn project → upload CSV/XLSX → Smart Setup → xác nhận grain/locale/metric/currency → duyệt → chuẩn hóa → xem canonical/errors/nguồn. Bỏ chọn AI trong tùy chọn nâng cao để review thủ công, không tiêu quota. Tài liệu tổng hợp đã lưu có thể xem lại, không cần mở allowance.

Khởi động ./tools/start.ps1 -SkipBuild; build mới dùng ./tools/start.ps1, không nhập token. Không xóa volumes. Gemini còn 4 requests trong trần 10; LlamaParse tạo job OFF.

Các gate Giai đoạn 1 đã điều chỉnh đạt, đủ điều kiện bàn giao nền tảng làm đầu vào kỹ thuật cho Giai đoạn 2. **Quyết định lịch sử ở lần Final Acceptance thu hẹp: dừng, không merge main, chờ prompt Giai đoạn 2 riêng.** Quyết định đã được tuân thủ; không tự thay kế hoạch ba giai đoạn.


## I. Hợp nhất theo ủy quyền mới

Chủ dự án đã gửi prompt riêng cho phép hợp nhất Giai đoạn 1 vào main, kiểm thử trước push, tạo annotated tag data-foundation-accepted-20261028 rồi triển khai Giai đoạn 2 trên codex/reconciliation-engine. Merge giữ cả hai parent 061c555 và 4bde211; hai conflict ở mục F/H chỉ là lịch sử Git và quyền chuyển tiếp. Đối chiếu từng đoạn, giữ bằng chứng provider/quota/tests/known limits của báo cáo mới cùng lịch sử tích hợp source của main; không đổi code ứng dụng hoặc nghiệp vụ. Các mục A–H là snapshot nghiệm thu trước nhiệm vụ này. Giai đoạn 2 không được merge main và không bắt đầu Giai đoạn 3.

Kết quả sau hợp nhất: offline 79 PASS/12 deselected (4,33 giây), bộ đầy đủ PostgreSQL 91 PASS/0 FAIL/SKIP (15,26 giây), Ruff/mypy 18 files PASS, TypeScript/ESLint/build PASS, Playwright MANUAL 9 PASS/0 FAIL/SKIP (19,4 giây). T01–T16, AI policy/contract, mapping/normalization/provenance và access-control nằm trong các suite này; không gọi cloud. Gemini giữ 6/10, còn 4, đúng model mặc định; Qwen không probe, parser creation OFF.

Snapshot 66 artifacts của lần nghiệm thu trước được kiểm tra nguyên vẹn trước E2E. E2E tạo thêm bốn refs tổng hợp, snapshot mới 70 artifacts, 20 datasets, 15 canonical, 48 jobs/52 attempts và 50 audits; 15 traces không tăng. Restart, force-recreate đủ bốn service và frontend-only recreate đều PASS metadata/checksum; demo proof fail-closed trước xác minh lại. Compose giữ project/volumes và loopback cũ, 4/4 healthy. Secret/history/Markdown path scan và diff check PASS; .vscode/ giữ nguyên ngoài stage. Không thay đổi source Backend/Frontend/Compose trong merge.

Merge commit **78e68c08e60c7af2359e46def43196cf5b1a6dc1** đã push main; annotated tag **data-foundation-accepted-20261028** trỏ đúng commit này và đã push, không di chuyển tag. Cổng A đạt trước khi tạo/push codex/reconciliation-engine từ mốc này. Sau đó phát hiện một số đoạn tài liệu bổ sung qua PowerShell mất dấu tiếng Việt; sửa bằng bản vá UTF-8 và commit tiến tiếp, không viết lại lịch sử. Mã ứng dụng và kết quả kiểm thử ở tag không đổi.

## J. Giai đoạn 2 — Reconciliation và kết quả

Ngày thực thi: 28/10/2026. Source project/Compose/volumes cũ giữ nguyên, không worktree/bản sao/server test mới. Main sau sửa encoding tài liệu ở **cf7cb1f**; không chứa source Giai đoạn 2. Tag nghiệm thu 78e68c0 giữ nguyên; branch mới được tạo từ đúng tag trước khi có thay đổi triển khai. Source backend Giai đoạn 2 đã push **c88bd85**. Các commit UI/acceptance tiếp theo được đối chiếu remote trong bàn giao; không ghi hash tự tham chiếu.

### Chức năng và contracts

| Nhóm | Kết quả và bằng chứng |
|---|---|
| Domain/Rule DSL | Typed Plan/Contract/Run/MatchGroup/Member/Comparison/ExceptionCase/MetricSnapshot/VerifiedRun; same canonical/schema/profile/mapping refs. Order/OrderLine/FinancialEvent suggestions cần review, Settlement/Payout chỉ khi có source entity thật. Không suy Orders thành tiền quyết toán |
| Contract gate | Scope/project/revision/stale, fields/types/rigid IDs, grain/cardinality, signed aggregation, metric/basis/unit/currency/time basis, `[start,end)`/timezone, coverage/due/effective dates, evidence allowlist; approval actor/audit riêng |
| AI Planner | PASS MOCK và PASS LIVE: Gemini gemini-3.5-flash-lite trả PROPOSED có plan trên cặp vận đơn/giao nhận; validated và chưa tự approved. Manual builder không JSON, không cloud, approval bắt buộc |
| Matching | Composite keys và canonical normalized keys; duplicates không chọn tùy ý; 1:N/N:1 signed Decimal đúng grain; Internal chia platform cho hai pair riêng. Source rows không mất/reuse; full lineage. Fuzzy text/blocking bounded, score chỉ review, không greedy/auto fuzzy IDs |
| Financial comparison | LINKED giữ nguyên khi lệch tiền; exact Decimal, signed/absolute delta, approved rounding, absolute/relative tolerance; EQUAL khác WITHIN_TOLERANCE; null/invalid/mixed currency không thành zero |
| Independent verification | Dựng lại từ canonical nguồn, không import matcher; partition, membership/cardinality, amount conservation, comparisons, full provenance và deterministic IDs. Corruption tests từ chối publish; không KPI/export khi fail |
| Jobs/publication | Queue SKIP LOCKED/lease/fencing cũ, source locks/revision check trước publish, draft Parquet trước atomic DB refs/snapshot/cases. Crash/retry không tạo hai logical runs. Reclaimed AI không tự gửi lại delivery chưa rõ |
| Exception Inbox | Search/filter loại/trạng thái, sort, notes/review, hai nguồn/keys/delta/rule/source row. Resolve/dismiss có lý do/audit, không đổi comparison hoặc frozen snapshot. Không AI risk score |
| Dashboard/report | Light-blue App Shell cũ; 4 KPI, run history/period/source filters, server pagination, ECharts, denominators/excluded/CU/currency, empty/loading/partial states. Case mở hiện tại từ API, tách frozen count lúc run |
| Exports | CSV/XLSX từ đúng verified run/snapshot, summaries/details/quality/evidence/rules/source values. Read-back/API equality, formula injection guards, numeric negative Decimal và zero-prefix PASS |
| Smart Templates | Approved rule signatures gồm schema/mapping transforms/entity/scope/effectiveness; rebind kỳ/source mới thành PROPOSED cần fresh approval. Drift/stale/expired/unknown không chạy tự động |

Các modules mới: contracts/reconciliation, domain_templates, reconciliation_contracts/engine/planner/repository/jobs/api/exports, verification. AI Gateway chỉ tách transport typed dùng chung, mapping/Qwen contracts vẫn giữ regression. Migration **create_reconciliation** additive trên create_data_foundation, chỉ thêm năm bảng/indexes; không sửa canonical/source identifiers. Các routes và gate cụ thể tại [Data Contracts](DATA_CONTRACTS.md). UI thêm ReconciliationStudio/reconciliationTypes và E2E, không viết lại upload/parser/mapping/auth/queue.

### Bộ demo có oracle độc lập

Fixtures source và oracle literal ở tests/fixtures, không lấy matcher/LLM làm ground truth. `tools/check-reconciliation.py` chạy production upload → manual mapping approval → normalize → plan approval → queue matching/verification → CSV/XLSX; rerun reuse cùng refs, 0 cloud mặc định.

| Pair | Oracle và kết quả thật |
|---|---|
| Internal ↔ Shopee | 11 left records = 1 invalid + 5 outside scope + 5 inside; 0001/0003 equal, 0002 LINKED/AMOUNT_MISMATCH delta 10, 0004 missing, 0007 ambiguous duplicate; signed/abs variance 10 VND, full match 2/5 |
| Internal ↔ TikTok | 1:N 0005 gồm đủ hai dòng 20+30=50; 0001 equal, 0008 null counterpart NOT_COMPARABLE, 0009 missing; comparable variance 0, không tự điền null bằng 0 |
| Vận đơn ↔ giao nhận | 000701 equal, 000702 delta 2,75 VND, 000703 left-only, 000704 right-only; full match 1/3, abs variance 2,75; không logic hardcode ecommerce |

### Kiểm thử cuối

| Suite | Thực tế |
|---|---|
| Offline pytest | **104 PASS**, 17 integration deselected, 0 FAIL; bao gồm property permutations, exact arithmetic và domain/AI/export contracts |
| Full PostgreSQL/Linux | **121 PASS, 0 FAIL/SKIP** (104 offline + 17 integration), 17,16 giây; tất cả T01–T16 và T17–T35 thuộc scope đều có ma trận bằng chứng |
| Ruff/mypy | PASS; mypy 28 source files |
| Frontend TypeScript/lint/build | PASS; main chunk khoảng 366 kB, results/chart lazy chunk khoảng 484 kB, không đổi ngưỡng để che warning |
| Playwright MANUAL | **14 PASS, 0 FAIL/SKIP**, 32,2 giây: 9 foundation + 5 reconciliation/workflow/responsive. Không gọi cloud; không cộng lần replay thành cases mới |
| E2E thật | UI manual rule → validate → approve → run → verified cards/chart → exception evidence/review → XLSX download → reopen đúng run. Snapshot không đổi sau RESOLVED. Five-file pipeline kiểm qua production API |
| Security | Existing auth/CSRF/Host/workspace/upload/cloud OFF; thêm viewer-run denial, cross-project sources/group evidence, stale refs, unapproved rule, AI hallucinated fields/evidence/APPROVED, formula injection; không secret trong response/bundle/source scan |

Lỗi thật và nguyên nhân đã sửa: DuckDB Linux date timezone thiếu pytz; source picker có thể lấy lại nguồn mặc định khi hai lựa chọn ban đầu trùng; ECharts ghi đè accessible name; UI loading từng hiện count 0 trước response; PG helper tạo tests/tests và đọc stale source; encoding PowerShell làm mất dấu đoạn báo cáo merge. Có regression API/E2E/read-back thích hợp, không hạ validator hoặc sửa oracle để đạt. Cảnh báo Starlette/httpx deprecation giữ riêng, không phải failure.

### AI, Docker, tài nguyên và giới hạn

Gemini trước 6/10, thêm **1 attempt**, nay **7/10, còn 3**; policy/key hiện có, không reset/tăng. Planner lifetime task ceiling vẫn 2 attempts kể cả retry; live chỉ một bộ tổng hợp, không tuyên bố precision/recall. Qwen giữ **BLOCKED_EXTERNAL_DEPENDENCY — HTTP 403** và không probe. LlamaParse **OFF** tạo job, lịch sử 2 docs/2 pages/6 credits giữ nguyên. Regression/API demo/E2E còn lại 0 cloud requests.

Trace Planner live: VALIDATED_PROPOSAL, latency 3.060 ms, 1 HTTP attempt; provider trả 8.117 prompt tokens, 910 output tokens, tổng 9.027. Không suy ra chi phí tiền tệ khi chưa có đối chiếu billing/unit cost. Supplemental integration kiểm tra bộ lọc run theo nguồn/kỳ PASS, không tăng tổng catalogue 121.

Benchmark exact-key Windows/Ryzen 5 7535HS/16 GB, không GPU, ba subprocess/size: 1k/10k/50k **tổng records hai nguồn**, lần lượt 500/5k/25k groups. Matching p50/p95 ms 31,57/37,58; 268,01/433,78; 1723,77/1792,43. Verification p50/p95 17,06/19,02; 230,28/257,09; 1315,23/1521,31. Peak MiB 38,68/89,10/317,06; không fuzzy/review/cloud trong benchmark. Không đo toàn HTTP/upload/write/export/render hoặc workload phức tạp, không cam kết 50k records mỗi source hay accuracy 99%.

Giới hạn còn lại: fuzzy chỉ review, chưa hiệu chỉnh threshold/precision hoặc blocking recall đại diện; N–M subset sum/FX/phí marketplace/Assistant chat ngoài scope. UI builder một metric chính và một scope filter/side, API có tối đa 5 metrics và 8 filters; evidence drawer preview 100 records/source, full member lineage trong result/export. Excel arithmetic có giới hạn 15 digits dù Decimal numeric lexemes/snapshot strings được giữ đúng. Text vượt 32.767 ký tự/ô hoặc control không biểu diễn được trong XML trả EXPORT_CELL_LIMIT, không cắt/sửa giá trị; regression kiểm chứng guard này. Cỡ lớn nhiều cột/group/export và concurrent workload chưa benchmark production. Không tuyên bố public production, full WCAG audit, OCR đại diện hoặc disaster backup/restore PASS. Archive metadata trước migration đọc danh mục được, chưa có restore drill. Những việc này cần được cân nhắc khi giao hardening/Giai đoạn 3; không tự triển khai Giai đoạn 3 trong nhiệm vụ này.

Kết luận kỹ thuật theo scope đã giao: contracts, planner/manual fallback, exact/group/review-only fuzzy, Decimal/verification, Dashboard/Exception Inbox, export và reuse có kiểm chứng. Bàn giao source feature branch để chủ dự án xem; **không tự merge Giai đoạn 2 vào main**.

Persistence cuối PASS cả restart, force-recreate bốn services và frontend-only recreate, fail-closed demo proof trước re-verification. Snapshot: 1 workspace/23 projects, 28 datasets/versions, 26 tables, 54 schemas/mappings, 23 canonical, 79 jobs/83 attempts, 83 audits/16 traces, 7 plans, 6 approved contracts, 6 runs, 22 cases, 8 export metadata; checksum **102 foundation artifacts + 6 match artifacts + 8 export files** bảo toàn. Bao gồm quota/policy/approvals/snapshots/notes, không xóa volumes/dữ liệu. Lần kiểm tra gần nhất giữ đủ 4/4 healthy, loopback 18180, không sửa Compose. Backend image khoảng 668 MB, frontend 91,2 MB; các tag accepted và rollback của nền tảng vẫn giữ, không dọn global Docker hoặc tài nguyên project khác. Ổ C còn khoảng 128,9 GiB tại thời điểm đo. Không coi Git/tag thay backup dữ liệu.

RAM nhàn rỗi sau recreate cuối: backend 112/384 MiB, worker 83,75/512 MiB, PostgreSQL 54,89/256 MiB, frontend 12,06/128 MiB; không phải peak workload. Sau chốt guard export/grain và recreate backend/worker, kiểm tra lại snapshot trên vẫn PASS; quota vẫn 7/10, task planner 1 attempt, parser 2 reservations/OFF. UI screenshots desktop/mobile đã xem trực tiếp, đủ cards/chart/rows, không ảnh secrets. Chưa audit WCAG đầy đủ.

Chốt chặn cuối bổ sung và kiểm tra: group aggregation không được dùng cùng grain với bản ghi tham chiếu để hợp thức hóa duplicate report rows; grain chi tiết phải được xác nhận riêng. Chỉ approved SUM_SIGNED ở 1:N/N:1 đúng grain mới chạy. Guard export cell giữ null/negative/precision semantics. Tài liệu UTF-8, đường dẫn Markdown, diff và known-key/history scan được kiểm tra trước push. .vscode/ giữ nguyên untracked, không stage; .env/raw/Parquet/archive/runtime reports/screenshots không commit. Kết thúc sau commit/push và báo cáo, chờ chủ dự án review; không bắt đầu Giai đoạn 3.
