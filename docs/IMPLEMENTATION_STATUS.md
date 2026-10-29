# Trạng thái triển khai và nghiệm thu

**Hiện tại:** Final Acceptance ngày 29/10/2026 ở mục L; Giai đoạn 2 đạt nghiệm thu kỹ thuật trong phạm vi MVP đã công bố. Các mục A–K giữ nguyên lịch sử; không dùng quota/counts hoặc lệnh dừng của nhiệm vụ cũ thay cho bằng chứng và ủy quyền mới.

Nhiệm vụ tiếp theo: Quality Hardening + UX Refinement, theo prompt riêng của chủ dự án, trên `codex/interface-quality` từ main `0b9421e`. Chỉ hoàn thiện Giai đoạn 1–2, không merge main, không cloud/Argon/Giai đoạn 3. Bằng chứng thực hiện ghi tại mục M; số liệu mục L là baseline lịch sử.

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

## K. Kiểm toán bổ sung và sửa lỗi Giai đoạn 2

Ngày: **28/10/2026**. Theo prompt kiểm toán riêng, tham chiếu **ab8e9f4f8fb85241c610322cbbea1e4f83df8441**; chỉ sửa sai lệch đã tái hiện và bổ sung regression. Branch `codex/reconciliation-engine`; main giữ **cf7cb1f3424aa61badf3df312b365496e8dfe1ef**. Không đổi kế hoạch ba giai đoạn, matcher/verifier, golden oracle, công thức, schema dữ liệu hoặc lịch sử artifact. Không tạo branch/worktree/Compose project khác.

### Phát hiện, nguyên nhân và kết quả

| Phát hiện | Kết luận | Nguyên nhân | Sửa đổi | Test |
|---|---|---|---|---|
| AI Planner pre-validation | **BUG — đã sửa** | API nhận ReconciliationPlan hoàn chỉnh rồi chạy execution validator, chặn chính các keys/metrics cần AI tìm | Input PlanningRequest nhỏ, gate context refs/quyền/stale/facts trước AI; typed suggestions hoặc complete plan có semantic validation sau AI. Giữ legacy input/job, không làm yếu executable contract, không tự approve | Tái hiện 422 với nguồn không keys trên bản cũ; PG nhận 202 sau sửa. Mock khác field IDs đề xuất đúng pair; giả field/evidence/basis/cardinality hoặc đổi scope/period bị chặn; thiếu facts NEEDS_REVIEW; chưa approved không chạy; durable quota hết 0 cloud calls và manual fallback PASS |
| Source evidence c1 | **BUG — đã sửa** | UI hardcode c1 cho mọi field và đưa JSON vào thông báo | EvidenceRef từ đúng MappingRevision lịch sử và source provenance; mở từng field input qua API evidence cũ, bảng file/sheet/row/column/raw value cạnh canonical value; không API row-detail mới | Regression bản cũ thiếu field_evidence; workbook hai sheet ID c1/amount c3, 000702, 1:N nhiều members; viewer đọc được/không review, foreign project group 404. E2E click tiền CSV mở c4/12.75 thật, không c1 |
| Readiness duplicate scope | **BUG — đã sửa** | Chỉ loại invalid và filter, chưa phân vùng theo ngày hoặc invalid keys/date | Dùng record_partition của engine; duplicate_population=IN_SCOPE, đếm riêng invalid/out-of-scope/in-scope/coverage_complete; verifier vẫn độc lập | Bản cũ báo 1 duplicate do tháng trước; sau sửa 0. Thêm duplicate cùng kỳ, filter ngoài scope, missing date/invalid key, incomplete coverage PASS |
| Automation KPI | **ACCEPTED DEFINITION**, có GAP về nhãn — đã làm rõ | Công thức §20 đo eligible CU được phân loại verified không cần quyết định row-level, có thể gồm UNMATCHED; nhãn Mức tự động hóa dễ bị hiểu là đã đối soát/giải quyết xong | Giữ MetricSnapshot/công thức/revision cũ; UI **Tự động phân loại**, mô tả gồm thiếu đối ứng/lệch đã verified; export giải thích cùng định nghĩa. Không thêm KPI trùng | Oracle 5 eligible CU: 4 automatic classifications, 2 full matches, 1 review; denominator 0 N/A. Review không sửa financial snapshot/comparison; API/CSV/XLSX equality PASS |
| Export after review | **ACCEPTED BEHAVIOR**, DESIGN GAP về thời điểm — đã sửa | Cache bất biến theo run/format/revision, states/notes lấy lần tạo đầu nhưng không ghi rõ as-of | Report-2 thêm generated-at/FIRST_GENERATION và giải thích; API/UI cùng timestamp/thông báo. Đọc states/notes trong REPEATABLE READ. Report-1/bytes cũ giữ nguyên | Hai PG cases CSV/XLSX: export → RESOLVED → export lại cùng ID/bytes, states OPEN trong file ban đầu, timestamp Summary=API, snapshot không đổi. Không biến RESOLVED thành EQUAL |
| UX setup | **IMPROVED**; giới hạn nhỏ còn công bố | Rule builder lộ nhiều thuật ngữ, default tháng 10/2026 và UTC có thể bị dùng mà chưa xác nhận | Bước nguồn → AI chuẩn bị → duyệt → chạy; khóa/chỉ tiêu thủ công trong details; summary/missing requirements; bỏ default period/timezone, checkbox xác nhận scope trước validate/save/approve; manual fallback khi provider lỗi | Playwright MOCK hỏi AI khi không common key, hiển thị đề xuất review-only và chặn approve; hết quota vẫn mở manual. T35 nhập ngày/timezone rõ, đợi đúng run_id mới VERIFIED; setup/results responsive 390/768/1366/1440/1920 PASS |

Ngoài sáu mục: khi mở rộng từ `mypy backend/studio` sang cả `mypy backend`, tái hiện hai lỗi Column thiếu type parameters trong migration đã có. Chỉ hoàn thiện return annotations `Column[Any]`, không đổi DDL/revision; AST đối chiếu runtime bodies giống hệt. Không thêm migration hoặc sửa dữ liệu. E2E trước đây có thể kiểm run cũ đang hiển thị trong khi job mới chạy; đã siết chờ đúng run_id từ POST và trạng thái VERIFIED trước so KPI/evidence/export. Đây là sửa khoảng trống kiểm thử, không sửa oracle cho test qua.

### Kết quả kiểm chứng thực tế

| Lệnh/suite | Kết quả |
|---|---|
| `uv run pytest -q -m 'not integration'` | **120 PASS / 0 FAIL / 0 SKIP**, 23 integration deselected; 3,97 giây |
| `tools/test-postgres.ps1 -All` | **143 PASS / 0 FAIL / 0 SKIP**, 44,91 giây = 120 offline + 23 PG. T01–T35 thuộc phạm vi, Hypothesis, corruption verifier, authorization/CSRF, worker/recovery, export read-back trong suite này |
| Migration sau hoàn thiện type annotations | Chạy riêng regression additive-preservation trên backend image mới: **1 PASS**, 10 deselected, 2,75 giây; không cộng vào catalogue 143 |
| `uv run ruff check backend tests tools` | PASS |
| `uv run mypy backend/studio`; `uv run mypy backend` | PASS: 28 application files và đầy đủ 31 backend/migration files sau sửa annotations |
| Frontend TypeScript / ESLint / production build | PASS; main khoảng 366 kB, lazy reconciliation/chart 489 kB, không đổi ngưỡng warning/dependency |
| Playwright MANUAL | **15 PASS / 0 FAIL / 0 SKIP**, 35,2 giây: 9 foundation + 6 reconciliation. Một case planner hoàn toàn MOCK, không provider/job thật. Không cộng các lần chạy lại thành cases mới |
| Historical integrity | Toàn bộ metadata/approvals/revisions/notes/snapshots và checksum **102 foundation + 6 match + 8 export** ở baseline ab8e9f4 giữ nguyên; dữ liệu E2E bổ sung riêng, không ghi đè cũ |
| Persistence | PASS restart, force-recreate bốn services và frontend-only recreate; mỗi lần proof invalidated/fail-closed rồi xác minh loopback; metadata/checksums giữ nguyên |
| Repository/security | Known credential/history scan, Markdown paths/UTF-8, diff checks PASS; không secrets/runtime/data đưa lên Git |

So baseline **121 backend / 14 E2E**, hiện **143 backend / 15 E2E**: thêm 16 offline + 6 PG + 1 E2E case, giữ mọi case cũ. Cảnh báo Starlette/httpx deprecation và Node color-env vẫn có, không phải failure. Trong quá trình chạy, tests đã tái hiện lỗi trên bản cũ; một lần helper dùng trùng idempotency key khác project đã sửa key của helper theo project, một assertion URL evidence cần decode dấu `:`. Sau phiên bị gián đoạn demo proof hết hiệu lực, E2E bị chặn đúng LOCAL_DEMO_NOT_VERIFIED; xác minh lại deployment rồi chạy toàn bộ PASS. Không tắt auth, tăng timeout hoặc hạ validator để qua test.

### AI, Docker và bảo toàn dữ liệu

Đọc PostgreSQL trước/sau kiểm toán: Gemini **gemini-3.5-flash-lite, 7/10 đã dùng, còn 3**, task Planner **1 attempt** trong trần 2; không reset/tăng quota và **0 request cloud mới**. Prompt `reconciliation-planning-2` **PASS MOCK/CONTRACT**, **NOT VERIFIED LIVE** theo chỉ định không gọi mới; PASS LIVE cũ chỉ thuộc prompt `reconciliation-planning-1`, không chuyển bằng chứng sang revision mới. Qwen **HOÃN/BLOCKED HTTP 403**, không probe. LlamaParse tạo job **OFF**, 2 reservations/2 documents/2 pages/6 credits lịch sử, không request mới.

Snapshot persistence cuối: **1 workspace, 26 projects, 31 datasets/versions, 29 source tables, 60 schemas/mappings, 26 canonical, 94 jobs/98 attempts, 103 audits/16 traces, 12 plans, 11 contracts, 11 runs, 37 cases, 12 export metadata**; checksum **114 foundation artifacts + 11 match artifacts + 12 export files**. Đã so baseline cũ theo từng ID/hash để bảo vệ cả history trong khi E2E thêm dữ liệu tổng hợp. Không xóa volumes, results cũ hoặc files export report-1.

Một Compose project `ai-reconciliation-studio`; 4/4 healthy, chỉ `127.0.0.1:18180`, backend/PG không publish host port. Giữ đúng hai persistent volumes, không thêm services/dependencies. Backend/worker chung image khoảng 668 MB, frontend 91,2 MB; accepted/rollback images cũ giữ lại, không global prune hoặc tác động project khác. Snapshot RAM sau kiểm thử khoảng backend 125,4/384 MiB, worker 101,3/512, PG 49,48/256, FE 10,61/128; C còn 130,1 GiB, không coi là peak benchmark. Rebuild/recreate annotation-only backend sau đó không thay runtime/DDL; persistence kiểm tra lại **PASS** trước bàn giao.

### Files, Git và giới hạn

Backend: `contracts/reconciliation.py`, `reconciliation_api.py`, `reconciliation_contracts.py`, `reconciliation_planner.py`, `reconciliation_jobs.py`, `reconciliation_exports.py`; migration `create_reconciliation.py` chỉ type annotations. Tests bổ sung trong `test_reconciliation_reporting.py`, `test_reconciliation_postgres.py` và `frontend/e2e/reconciliation.spec.ts`. Frontend chỉ `frontend/src/ReconciliationStudio.tsx` và `frontend/src/reconciliationTypes.ts` hiện có. Tài liệu README, AI_INTEGRATION, ARCHITECTURE, DATA_CONTRACTS, TESTING_GUIDE và báo cáo này; Rules/AGENTS/PROJECT_PLAN, engine/verifier và golden fixtures không đổi.

Đã commit/push nhóm backend **d9b51270cffe0006c807b452062d88e92d8a41a3**, nhóm type-check **d395383dadbacc36f4ba9a6c835704920aac4a63** lên đúng origin/codex/reconciliation-engine. Commit UI/báo cáo sau đó sẽ được báo hash trong bàn giao, không ghi hash tự tham chiếu. Remote đã xác minh đúng repository; không force-push hoặc merge main. `.vscode/` có sẵn giữ nguyên ngoài stage; mọi runtime files/screenshots/fixtures workbook/dumps/.env không commit.

Giới hạn: prompt planner mới chưa thử live; fuzzy vẫn chỉ review/chưa có đánh giá precision/recall đại diện; không FX/phí marketplace/N–M/Assistant. UI builder một metric chính và một filter mỗi phía; coverage thực tế vẫn cần người dùng biết/xác nhận. Evidence preview tối đa 100 members mỗi source, 100 source rows/record, UI 20 ô/lần mở có thông báo; full member lineage ở result/export. Report-1 cũ không có review timestamp thì trả null/thông báo, không suy diễn hoặc ghi lại. CSV/XLSX tạo vào thời điểm khác nhau có thể chứa states/notes khác nhau, nhưng financial metrics luôn từ cùng immutable VerifiedRun. Excel arithmetic 15 digits, cell length/control guards giữ nguyên. Không tuyên bố production/WCAG đầy đủ/DR restore/accuracy đại diện đã PASS.

**Kết luận:** các lỗi được giao đã tái hiện/sửa và regression đạt; không phát hiện cần sửa/xóa kết quả lịch sử. Đủ bằng chứng kỹ thuật cho chủ dự án xem xét nghiệm thu chính thức Giai đoạn 2 trong phạm vi đã công bố. **DỪNG sau commit/push báo cáo; không merge main, không bắt đầu Giai đoạn 3.**

## L. Final Acceptance, hợp nhất và vận hành — 29/10/2026

Ủy quyền mới của chủ dự án cho phép nghiệm thu, merge `--no-ff`, chia sẻ cấu hình VS Code an toàn, tag `reconciliation-engine-accepted-20261029`, deploy main và cleanup images đúng project; chỉ nghiên cứu Argon, không tích hợp hoặc triển khai Giai đoạn 3. Các lệnh dừng ở mục K là lịch sử của nhiệm vụ trước. Git đầu nhiệm vụ: feature **e025094139db217b3788d4b446d1eaab23b97a5c**, main **cf7cb1f3424aa61badf3df312b365496e8dfe1ef**, ahead 5/behind 0, tracked tree sạch; chỉ `.vscode/settings.json` untracked. Không phát hiện commit remote mới chưa đối chiếu.

### Gate 1 — source/runtime: PASS

Image cũ thiếu revision ứng dụng; frontend kế thừa revision của Nginx, không được dùng làm bằng chứng Git của dự án. Dựng lại từ tracked source sạch bằng Compose chính với biến build-only `BUILDX_GIT_LABELS=full`. Buildx gắn OCI source/revision chính xác; không sửa Dockerfile, Compose, runtime env hoặc code nghiệp vụ. Created timestamps của image config/layers có thể được giữ từ cache, không diễn giải chúng là thời điểm chạy lại build. Container IDs/creation times, labels, immutable image identifiers và manifest checksums được lưu trong evidence runtime bị ignore.

| Thành phần | Source revision | Immutable image ID tại Gate 1 | Runtime |
|---|---|---|---|
| Frontend | e025094139db217b3788d4b446d1eaab23b97a5c | sha256:57a48c3e6ff1bedf63162b71e3a8d1292af421d177a4e7afa50dedfd31a54979 | Healthy; 4 HTTP-served files khớp SHA256 production build |
| Backend | e025094139db217b3788d4b446d1eaab23b97a5c | sha256:c966a65d026417d8e2a7e7662f8ab888aca582fd1a59aa319a12f6abd396f553 | Healthy; 34 tracked files khớp SHA256 local |
| Worker | Cùng backend | Cùng backend | Healthy; 34 tracked files khớp, heartbeat/queue dùng chung code |
| PostgreSQL | N/A; postgres:18.3-alpine, immutable image | sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7 | Healthy; volume hiện có, không publish host port |

Sau đó chỉ bổ sung assertions/export downloads trong Playwright và tài liệu nghiệm thu; application files không đổi so với e025094. Đây không phải tuyên bố image cũ khớp revision chỉ vì healthcheck xanh.

### Gate 2 — regression không cloud: PASS

| Kiểm tra | Kết quả thực tế |
|---|---|
| Offline pytest | **120 PASS, 0 FAIL/SKIP**, 23 integration deselected; 8,07 giây |
| PostgreSQL `tools/test-postgres.ps1 -All` | **143 PASS, 0 FAIL/SKIP**, 50,19 giây = 120 offline + 23 integration; migration preservation đã nằm trong suite, không đếm thêm |
| Ruff; mypy backend | PASS; 31 backend/migration source files |
| Frontend TypeScript; ESLint; production build | PASS; lockfiles/dependencies không đổi |
| Playwright MANUAL | **15 PASS, 0 FAIL/SKIP**, khoảng 1,1 phút; gồm 9 foundation và 6 reconciliation, responsive 390/768/1366/1440/1920 |
| Planner reconciliation-planning-2 | **PASS MOCK/CONTRACT — LIVE NOT VERIFIED**; incomplete request, khác IDs, fake evidence/basis/cardinality/scope, missing coverage, unapproved execution, exhausted quota/manual fallback |
| Security/invariants | T01–T35, Hypothesis, verifier corruption, membership/conservation, atomic publication, permissions/CSRF/Host/workspace isolation, stale/reuse/idempotency/worker recovery và export-after-review trong các suite trên |

Giữ nguyên golden oracle/validators và timeouts. Starlette/httpx deprecation, Node color-env warning vẫn còn; không phải FAIL. Không gọi Qwen hoặc Gemini/LlamaParse live. Baseline 143 backend/15 E2E không tăng số cases chỉ vì chạy lại hoặc thêm assertions vào T35.

### Gate 3 — UI/oracle/persistence: PASS

Playwright thật trên Nginx production: chọn hai canonical → nhập/xác nhận kỳ, UTC và coverage → readiness → manual proposal → approval → POST run → đợi đúng run_id mới VERIFIED → KPI/eligible denominator → AMOUNT_MISMATCH → cột tiền **c4**, sheet CSV, dòng **3**, raw/canonical **12.75** ↔ **10.00**, delta **2.75 VND**, ID **000702** → RESOLVED → comparison và MetricSnapshot không đổi → xuất **CSV và XLSX qua UI** → kiểm download SHA256 → reload đúng run. Đọc lại cả hai files bằng csv/openpyxl xác nhận nguyên MetricSnapshot JSON, zero-prefix strings, timestamp Summary=API và FIRST_GENERATION scope; XLSX không có công thức tính KPI. Screenshots desktop/mobile đã kiểm tra; không đồng nghĩa audit WCAG toàn diện.

Đối chiếu API production/cached immutable runs với oracle literal có sẵn: Shopee 2/5 full match, signed/abs 10 VND, invalid 1/outside 5, 7 cases; TikTok 0005 có đúng hai members 20+30=50, 0008 NOT_COMPARABLE, signed/abs 0, 3 cases; giao nhận 1/3 full match, delta 2.75, 3 cases. Mọi source member xuất hiện đúng một lần và tổng membership khớp row_count từng canonical; CSV/XLSX của cả ba pairs khớp Snapshot/checksum/as-of. Lookup oracle dùng đầy đủ platform/carrier + ID, không nhầm cùng suffix ID giữa hai platform. Multi-sheet c1 identifier/c3 amount, 1:N/N:1 và incomplete coverage có bằng chứng PG/golden; khác field IDs và quota fallback là MOCK/contract, không giả thành live AI.

Inventory đầu nhiệm vụ thực tế: **114 foundation artifacts, 11 match artifacts, 12 export files**, 31 datasets/26 canonical, 62 schemas/mappings, 95 jobs/99 attempts, 104 audits/17 traces. Một số metadata tăng từ trước nhiệm vụ so với mốc K; chụp hiện trạng thật, không sửa lịch sử cho khớp báo cáo cũ. Sau kiểm thử: **118 foundation + 12 match + 20 export files**; 27 projects/32 datasets, 30 tables, 64 schemas/mappings, 27 canonical, 106 jobs/110 attempts, 109 audits/17 traces, 13 plans/12 contracts/12 runs/40 cases. Tất cả IDs/metadata/checksum thuộc inventory đầu giữ nguyên; refs tổng hợp mới được phân biệt riêng.

Restart, force-recreate cả bốn services và frontend-only recreate đều **PASS**, proof local bị vô hiệu đúng thiết kế rồi xác minh lại loopback. Một Compose project, bốn services healthy, hai volumes cũ giữ nguyên; chỉ publish **127.0.0.1:18180**. Không xóa dữ liệu, job đang chạy hoặc volumes. Gemini trước/sau **7/10**, còn **3**, Planner attempt **1**, parser reservations **2**; global/workspace trần **10**, cloud request delta **0**, parser creation OFF ở cả env/policy. Qwen HTTP 403 vẫn hoãn, không probe. Prompt mới không có live inference trong nhiệm vụ này.

**GIAI ĐOẠN 2 ĐẠT NGHIỆM THU KỸ THUẬT TRONG PHẠM VI MVP ĐÃ CÔNG BỐ.**

Ngoại lệ/giới hạn tiếp tục: Qwen LIVE BLOCKED do IP; Planner mới LIVE NOT VERIFIED; fuzzy chỉ review, precision/recall đại diện chưa đo; không FX/phí marketplace ngoài scope; chưa production security audit toàn diện/DR restore drill; không Assistant Giai đoạn 3. Không tuyên bố production-ready. Kết quả Git/tag/deploy/cleanup và nghiên cứu đã thực hiện được ghi bên dưới.

### Hợp nhất GitHub và cấu hình chia sẻ

Commit bằng chứng/tests nghiệm thu **7dfcb83319ba6c07b5f78fe34105b95c5e577ead** đã push feature branch. Merge `--no-ff` **2a880cc7a7cd92faf32e9885b34cf5f93723ff53** có hai parents cf7cb1f và 7dfcb83, không conflict/squash/rebase. `git diff` giữa merge result và accepted feature tree rỗng. Trước push main chạy lại 120 offline PASS (8,03 giây), Ruff/mypy 31 files/TypeScript/ESLint/source scan PASS; không đếm replay thành tests mới. Main đã push/fetch và local/remote khớp; cả tag Giai đoạn 1 lẫn e025094 là ancestors.

Inventory `.vscode/` đúng một file **settings.json** (không launch/tasks/extensions/private metadata). Đọc toàn bộ, parse JSON và secret scan: chỉ `python.terminal.useEnvFile: true`, không credentials/commands/env values/absolute paths; chuẩn hóa indentation hai spaces, giữ nguyên hành vi. Commit riêng **fcb54343c38bebb7f45e929bf289b6391d526319**, đã push main. Không tạo file config thừa hoặc ignore secrets bằng tên chung để che file chưa kiểm tra. Working tree sạch sau commit; mọi runtime evidence nằm ngoài Git.

### Tags và branches sau hợp nhất

| Mốc | SHA đã push/xác minh |
|---|---|
| Main merge | **2a880cc7a7cd92faf32e9885b34cf5f93723ff53** |
| VS Code config | **fcb54343c38bebb7f45e929bf289b6391d526319** |
| Main tại mốc nghiệm thu/deploy | **be6b8a067ca052ea989a029a15558b0fd5ee48ef** |
| Annotated `data-foundation-accepted-20261028` | Target **78e68c08e60c7af2359e46def43196cf5b1a6dc1**, giữ nguyên |
| Annotated `reconciliation-engine-accepted-20261029` | Target **be6b8a067ca052ea989a029a15558b0fd5ee48ef**, đã push; không di chuyển |

Xác minh PR đang mở bằng GitHub CLI: **0**; không stash, chỉ một worktree tại repo chính, mọi tips được dọn là ancestors của main. Xóa remote/local `codex/reconciliation-engine` và `codex/data-foundation`, local `codex/reconciliation` bằng normal delete sau khi tag/main đã push. Không force-delete, không xóa history/tags hoặc branch có commits riêng. Local/remote chỉ còn main và origin/HEAD. Remote chính thức đã đối chiếu trước mỗi push.

Commit nghiên cứu/bàn giao tiếp theo trên main chỉ thay Markdown theo ủy quyền bước 21; vì vậy final main HEAD sẽ tiến sau tag. SHA commit tài liệu cuối được báo cùng kết quả push, không tự ghi SHA của chính commit vào nội dung của nó. **Tag và runtime giữ mốc be6b8a0**; application/dependencies/Compose không đổi giữa mốc deploy và main sau nghiên cứu.

### Deploy main và kiểm tra sau merge: PASS

Build từ main sạch be6b8a0 bằng Compose hiện có và OCI Git labels; backend/worker dùng cùng image. Kiểm lại **34 source/build files mỗi backend/worker** và **4 production files qua HTTP**: SHA256 khớp source/build. Không có `.env` trong backend image. OCI revision của cả hai app images là be6b8a0, source label đúng repository này.

| Image | Immutable ID | Hành động |
|---|---|---|
| Backend/worker current | `sha256:decbc4ccf59fb822c6d27397bfd52d9701351a234d7c46814a8e667d1cc75477` | KEEP; accepted main |
| Frontend current | `sha256:1dedf4ed08e668a4cde9d56024f541c02d588ffc2e99fa87d47af2c4ee2ba5d1` | KEEP; accepted main |
| Backend `rollback-e025094` | `sha256:c966a65d026417d8e2a7e7662f8ab888aca582fd1a59aa319a12f6abd396f553` | KEEP; bộ đã qua Gate1–3 |
| Frontend `rollback-e025094` | `sha256:57a48c3e6ff1bedf63162b71e3a8d1292af421d177a4e7afa50dedfd31a54979` | KEEP; bộ đã qua Gate1–3 |
| PostgreSQL current | `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` | KEEP; không thay image/volume |

Trên image accepted main chạy lại toàn PostgreSQL suite: **143 PASS, 0 FAIL/SKIP, 44,42 giây**. Smoke T35 thật: **1 PASS, 15,9 giây**, cả CSV/XLSX; đây là replay một case trong baseline15, không phải tăng thành16 E2E. Một lần filter `^T35:` chọn0 tests vì full test title có prefix; sửa lệnh thành `T35:` và chạy thành công, không tính lần chọn0 là PASS. Đọc lại cả hai UI downloads và oracle ba cặp trên API production: PASS. Không phát hiện lỗi ứng dụng mới cần đổi code; chỉ tăng độ chặt assertions/export coverage và độ rõ bằng chứng triển khai, không đổi golden oracle.

Sau smoke trên main: **118 foundation artifacts, 13 match artifacts, 22 export files**; 27 projects/32 datasets/versions, 30 tables, 64 schemas/mappings, 27 canonical; 109 jobs/113 attempts, 112 audits/17 traces; 14 plans/13 contracts/13 runs/43 cases/22 export metadata. Inventory lịch sử đầu nhiệm vụ vẫn là subset nguyên IDs/metadata/hash; snapshot mới giữ toàn bộ hiện trạng sau tests. Không có job đang chạy khi kiểm persistence/cleanup.

### Docker cleanup: PASS

Inventory có IDs/tags/creation times/project labels và references của cả running/stopped containers. Giữ current và gắn tên rõ cho cặp rollback e025094 đã kiểm chứng trước khi xóa legacy images. Chỉ bốn IDs dưới đây có project label `ai-reconciliation-studio`, tất cả tags thuộc project, không còn container tham chiếu, không nằm trong protected set:

| Image cũ | Immutable ID | Hành động/lý do |
|---|---|---|
| Backend `accepted` cũ | `sha256:2025e07ea2514ce39e8bad04bb6bb32687085305fbe0c7f0fa92543c50a24a86` | DELETE; đã có current/rollback xác minh |
| Frontend `accepted` cũ | `sha256:44de606ed1f2fb33c6dbba4c0efc189fc109c39fb9d97669a25678bd94ef1190` | DELETE; đã có current/rollback xác minh |
| Backend `rollback` cũ | `sha256:ed4a4bbf3b9d9991bc58ccd9edae6c5f58b9403153475ed3bbe661dd8ad9d939` | DELETE; cặp rollback e025094 thay thế |
| Frontend `rollback` cũ | `sha256:aa7c869df77a24c3f1e3fec33020e0f5b2e245587d846872dd9a03223abcc9aa` | DELETE; cặp rollback e025094 thay thế |

Xóa từng ID bằng `docker image rm`, **không force/prune**. 47 image ngoài project/không xác định chủ sở hữu trong inventory trước dọn đều còn; không công bố tên/metadata dự án khác. Không xóa containers, volumes, model cache hoặc build cache. Việc xóa legacy image tag `accepted` không xóa Git tag Giai đoạn 1.

| Số đo thực của Docker host | Trước → sau |
|---|---|
| Image count | **55 → 51** |
| `docker system df` Images Size | **39,75 → 39,38 GB**, giảm khoảng 0,37 GB theo cách báo của Docker |
| Build Cache Size | **48,18 → 48,18 GB**, giữ nguyên |
| Containers / named+anonymous volumes tổng host | **31 → 31 / 36 → 36**, không xóa |

Không cộng virtual sizes để tuyên bố dung lượng giải phóng; do layers/cache còn chia sẻ, **số physical filesystem blocks/VM disk đã thu hồi là NOT VERIFIED**. Không dọn cache toàn host để làm số liệu đẹp hơn. Hai volumes `ai-reconciliation-studio_postgres_data` và `ai-reconciliation-studio_artifacts` giữ nguyên. Sau dọn **4/4 healthy**, loopback18180/demo session/API/worker/Nginx/PostgreSQL hoạt động; snapshot metadata/artifact bytes khớp hoàn toàn, UI report read-back và ba oracle PASS. Gemini **7/10**, planner1/parser2 reservations giữ nguyên; cloud delta 0.

Evidence local bị ignore: `runtime/release-source-manifest.json`, `runtime/release-gate1.json`, `runtime/release-main-runtime.json`, `runtime/release-docker-inventory.json`, `runtime/release-before-cleanup.json`, `runtime/release-cleanup-result.json`, UI downloads/manifest và screenshots. Bản baseline metadata/artifact hashes nằm ở artifact volume `verification/acceptance-20261029-before.json`, snapshot sau smoke ở `verification/persistence.json`. Đây là kiểm chứng persistence, **không thay backup/restore database**; không commit nội dung runtime hoặc inventory dự án khác.

### AI và nghiên cứu Argon

| Mục | Kết quả ngày 29/10/2026 |
|---|---|
| Gemini mặc định | `gemini-3.5-flash-lite`; mapping live lịch sử giữ nguyên; không inference mới |
| Gemini budget | Trước/sau **7/10**, còn **3**; global/workspace ceilings10 không đổi |
| Planner `reconciliation-planning-2` | **PASS MOCK/CONTRACT — LIVE NOT VERIFIED**; lịch sử1 attempt của revision trước không được gán cho prompt mới |
| Qwen `knowledge` | **BLOCKED / LIVE DEFERRED** theo chỉ định, HTTP 403/IP; không probe |
| LlamaParse | Creation **OFF** cả env/workspace; lịch sử 2 tài liệu/2 trang/**6 credits** và 2 reservations giữ nguyên; không request mới |
| Argon | **RESEARCH COMPLETE**; model/account inference/quality/latency/cost **NOT VERIFIED**, implementation/live **DEFERRED** |

[Nghiên cứu phân tuyến model](AI_MODEL_ROUTING_RESEARCH.md) gồm đủ 14 phần, tám nguồn Google bắt buộc và tài liệu bổ sung, kiểm tra ngày 29/10/2026. Đề xuất một Gateway, Flash-Lite cho schema/mapping/simple planning, Argon explicit opt-in cho suy luận phức tạp, backend giữ matching/verifier/KPI/approval. Hai lớp attempt/token-USD caps, một ledger nhỏ trong PostgreSQL hiện có; Argon disabled/request 0/USD 0. Phân biệt REST 32K/SDK 64K, thinking+answer budget, timeout/lease/recovery, retention, continuation và pricing revisions. Cần chủ dự án duyệt trước mọi implementation/live; không thêm dependency, biến env runtime, code provider hoặc migration trong nhiệm vụ nghiên cứu.

Kiểm tra tài liệu trước commit: đủ 14 sections và 14 nguồn đã mở, UTF-8/Markdown references/local paths, hai JSON examples (gồm `PlanProposal` validation), phép tính chi phí Decimal và `git diff --check` PASS. Repository scan **106 source candidates**, kiểm known credentials trong source/reachable history và runtime/binary candidates PASS; đây không phải chứng nhận security audit đầy đủ. Commit nghiên cứu chỉ gồm bốn Markdown files: tài liệu nghiên cứu mới, báo cáo này, AI_INTEGRATION và README. Không chạy lại suite ứng dụng chỉ vì sửa tài liệu; sử dụng kết quả accepted-main 143/T35 và full 15 đã ghi, persistence/oracle/budgets vừa kiểm lại PASS.

### Quyết định bàn giao và điểm dừng

**PASS:** ba gates nghiệm thu kỹ thuật; 143 backend/15 E2E catalogue; CSV/XLSX UI và independent oracle; security regression/persistence; main merge/.vscode/tag/branch cleanup; accepted-main deploy; cleanup đúng 4 images; nghiên cứu tài liệu Argon. **FAIL:** không có test FAIL hoặc lỗi ứng dụng mới đã xác định còn tồn tại trong phạm vi này. **BLOCKED:** Qwen live. **NOT VERIFIED:** prompt Planner mới live, Argon live/account/benchmark, representative precision/recall, production security audit và DR restore. **DEFERRED:** tích hợp/live Argon, long decode, Giai đoạn 3.

Mức sẵn sàng: source Giai đoạn 2 đã nghiệm thu trong phạm vi MVP công bố, main/tag/runtime có bằng chứng; đủ để chủ dự án xem xét prompt tiếp theo. Không tự coi các mục NOT VERIFIED là PASS hoặc tự cấp quyền triển khai. **DỪNG sau bàn giao; không bắt đầu Giai đoạn 3, không tích hợp Argon hoặc tăng/reset ngân sách.**

## M. Hoàn thiện frontend và UX Giai đoạn 1–2

Phạm vi được giao: project search/pagination/restore, thống kê/trạng thái/next action, tổ chức frontend có kiểm soát, ngôn ngữ/loading/error/keyboard/responsive, polling và dữ liệu test. Không đổi engine/verifier, tiền, approvals hoặc artifacts lịch sử. Nhánh từ main sạch `0b9421e`, hai acceptance tags giữ nguyên; một repo/Compose. Baseline thật: 27 projects, 32 datasets, 27 canonical, 118 foundation + 13 match + 22 export files; Gemini 7/10, planner1/parser2, parser creation OFF.

### Bản đồ trách nhiệm trước sửa

| Trách nhiệm | Quyết định | Lợi ích | Rủi ro và kiểm chứng |
|---|---|---|---|
| App Shell/sidebar | Giữ ở App; sửa count/footer/mobile focus cục bộ | Giữ điều hướng hiện có | Responsive/keyboard |
| Project selector | Tách một component với typed props; API đọc phân trang/tìm kiếm | Một nơi quản lý search/loading/focus, không tải toàn bộ projects | Restore ngoài trang đầu, scope/race/auth |
| Dashboard/next action | Tách phần hiển thị summary/action nếu có ranh giới rõ | Không lẫn counters với financial KPI | DTO backend, READY/PARTIAL/loading và đúng deep link |
| Data workspace/explorer | Giữ state/API ở App, bổ sung scope guards và lỗi/chất lượng | Không nhân bản fetch/preview logic | Mapping drafts, canonical refs, pagination |
| Upload/settings | Giữ implementation đang PASS | Không refactor ngoài thay đổi cần thiết | Regression pipeline/security |
| Jobs | Poll theo active jobs, refresh thủ công khi idle | Giảm request lặp | Completion refresh, no overlap/unmount/stale response |
| Reconciliation | Format; tách evidence nếu độc lập, giữ rule/result state và contracts | Dễ đọc và sửa cục bộ | T35, historical run/evidence/snapshot/export |

Các phát hiện xác nhận từ source: project chỉ lấy trang50 rồi bỏ saved ID ngoài trang; sidebar dùng page length; Dashboard dùng fallback0 lúc loading, nhãn READY mơ hồ; polling toàn project mỗi3s cả khi idle; một số scope state chưa được xóa khi chuyển project. Đây là confirmed bugs/UX gaps, không phải bằng chứng matcher sai. Chi tiết kiểm thử/kết quả sẽ ghi sau thực thi.

### Nhóm A — project selector

Đã tái hiện regression trên image cũ: saved ID ngoài trang đầu không có single-project GET (404). Bổ sung GET scoped theo ID và search literal name/business_scope có giới hạn, Unicode/case-insensitive, escape `%/_`, stable pagination; không migration/quyền mới. UI tách ProjectSelector: 20 results/trang, debounce/AbortController/sequence guard, loading/error/retry/no-results, scope và ID ngắn cho tên trùng, combobox/listbox/Arrow/Enter/Escape, focus trở về nút mở. Saved ID được xác minh riêng; mất quyền/missing không tự chọn project khác. Chuyển project xóa canonical/evidence/source state, giữ key theo project cho reconciliation.

PG regression sau sửa **1 PASS, 12 deselected** (3,76s), trước sửa FAIL đúng thiếu GET. TypeScript/ESLint/build/Ruff/mypy31 PASS. Sáu browser contract tests **6 PASS** (8,9s): 1/10/50/120 projects, paging, search có dấu/hoa thường, duplicate names/scopes, saved off-page/reload/missing, delayed search/error/loading. Lần đầu keyboard tests phát hiện focus không quay về trigger do Dialog không dùng Dialog.Trigger; sửa returnFocus optional trong Modal rồi cả6 PASS, không đổi expectations. Browser fixtures chỉ intercept API GET, không tạo production projects/dữ liệu/cloud. Các E2E cũ đã đổi sang tương tác bộ chọn thật, không hidden select.

Reconciliation responsive trên saved demo thật: **4 PASS** (17,0s, 390/768/1366/1920), không tạo dữ liệu. Lần đầu helper đọc API trước session bootstrap bị401; sửa helper đợi visible picker (auth đã hoàn tất), không bỏ auth. Bốn màn hình sau đó PASS qua tìm kiếm/selection mới. Diff/known-secret-history/local Markdown links PASS, chưa coi các kiểm tra nhóm này thay cho full regression cuối nhiệm vụ.
