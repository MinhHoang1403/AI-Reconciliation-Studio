# Trạng thái triển khai và nghiệm thu

**Hiện tại — 30/10/2026:** Nghiệm thu mới tại **mục R**: **191 backend / 59 E2E PASS**, Assistant **PASS LIVE**, Planner `reconciliation-planning-2` **FAIL LIVE** (`AI_INVALID_JSON`). **CHƯA ĐẠT GATE RELEASE**: merge main, dọn feature branch và Docker release/image cleanup mới **BLOCKED** theo prompt. Gemini **9/10**, còn1; không retry hoặc tăng/reset ngân sách. Runtime vẫn source `446d031`, bốn dịch vụ healthy, dữ liệu/persistence/backup đã kiểm tra lại. Các mục A–Q là lịch sử, không thay cho kết quả mới.

Bối cảnh lịch sử: Quality Hardening + UX Refinement trước đây nằm trên `codex/interface-quality`, từ main `0b9421e`. Các nhiệm vụ P/Q triển khai Assistant trên `codex/assistant-automation` và dừng trước merge. Mục R ghi ủy quyền hợp nhất mới cùng gate live đang BLOCKED; không thay đổi kết luận lịch sử ở mục N.

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

### Nhóm B–C — thống kê, chất lượng và bước tiếp theo

Sidebar lấy `datasetTotal`, không page length; trước response hiện dấu chờ, Dashboard không dùng fallback0. Tách DataOverview (pure UI) khỏi App, đưa DatasetList dùng chung vào components hiện có; state/fetch vẫn ở App. Nhãn READY thành “Kết quả sẵn sàng sử dụng”, giải thích dataset/bảng, mapping review và active jobs; breakdown PARTIAL/stale/FAILED từ summary additive, không migration hoặc KPI tài chính mới. PARTIAL trong chi tiết nguồn có invalid/row counts từ canonical và nút xem lỗi, không khẳng định do mapping chưa duyệt.

Summary thêm target điều hướng scoped, chọn theo ưu tiên và thứ tự ổn định; next action mở đúng dataset/table/tab/canonical-errors kể cả target không nằm trong trang25 nguồn. Approved chưa canonical → tab Chuẩn hóa; thiếu approval → AI Smart Setup; PARTIAL/FAILED → kiểm lỗi; hai READY → chọn nguồn ở Đối soát, không tự coi tương thích/chạy; verified run có links kết quả/ngoại lệ. Backend vẫn authorize mọi lookup; không sửa nguồn khi bấm thẻ hướng dẫn. Refresh abort/sequence chặn dữ liệu/lỗi cũ sau đổi project; idle không polling3s vô hạn, còn active jobs mới hẹn refresh tiếp, có refresh thủ công. Footer bỏ nhãn phát triển. Reconciliation giữ component key theo project khi chuyển home/reconcile/reports/exceptions để không mất draft không cần thiết.

Sau sửa: **145 backend PASS, 0 FAIL/SKIP** (36,19s, toàn suite PostgreSQL/Linux;120 offline+25 integration), gồm search regression mới và lifecycle summary80datasets/PARTIAL/FAILED/stale; các security/worker/engine/verifier/exports cũ giữ PASS. Browser contract suite hiện **10 PASS** (13,4s) với totals80/page25, READY0/PARTIAL1/stale2, deep link tới sheet thứhai của nguồn ngoài trang đầu, review/normalize đúng tab, pending/error/switch race. Lần đầu SQL group-by JSON dùng hai bind-expression khác nhau bị PostgreSQL từ chối; reuse cùng expression rồi full suite PASS. Một selector test viết thiếu space trong accessible name đã đối chiếu snapshot và sửa selector, không sửa UI để che lỗi.

Reconciliation responsive trên runtime mới **4 PASS**; Planner UI **PASS MOCK** (4,1s). Mock catalogue cũ intercept mọi project rồi giả định luôn có nguồn demo; scope intercept vào đúng project demo, giữ toàn bộ assertions. Không có request provider thật. Không có thay đổi matcher/verifier/migration/dependencies/financial DTO; backend chỉ mở rộng read summary/navigation trong repository/API hiện có.

### Nhóm D–F — tổ chức frontend, UX và fixtures

**Confirmed bug:** request evidence của run A trả sau khi chọn run B có thể mở dialog A dưới context B. Regression trước sửa FAIL (dialog cũ làm control nền không còn accessible); sau sửa PASS. Run scope/generation và sequence guards áp dụng evidence/export; chỉ đọc snapshot khi `run.id === runId`, kiểm project của Run DTO trước hiển thị. ReconciliationEvidence tách đúng cell preview/review form theo run/group, hủy GET khi đóng/unmount; không thay evidence/approval/review APIs. Job polling dừng khi unmount, không hủy job backend hoặc gửi lại POST. ReconciliationStudio giữ setup/results cùng state do còn chia sẻ draft/run, chỉ format và tách evidence có ranh giới rõ; không tạo component/framework thay thế toàn bộ ứng dụng.

UI role lấy từ `/session`, hiển thị Chủ không gian/Có quyền chỉnh sửa/Chỉ xem; viewer không có nút tạo/upload/approve/normalize/export mới/review khả dụng. Backend vẫn là authorization authority; không đổi membership/policy. Tiếp tục cho xem nguồn/bằng chứng. Chuẩn hóa ngôn ngữ múi giờ/phạm vi/tiền tệ, không đổi request fields. Empty/no-results/loading/error của project/summary/run/cases tách biệt; GET timeout30s có thông báo/thử lại, không tự retry mutation. Navigation giữ draft khi chuyển giữa các màn hình reconciliation; link kết quả từ Dashboard có yêu cầu chọn đúng run mới nhất, không chỉ viết localStorage rồi giữ state cũ.

Project dialog dùng combobox/listbox/active descendant, focus visible/Enter/Escape và focus return. Mobile sidebar ẩn khỏi keyboard khi đóng, trap Tab/Shift+Tab, Escape trả focus về nút mở; main inert khi drawer mở. Upload/evidence/project dialogs trả focus và dùng Radix hiện có. Không thêm UI/state library hoặc dependency/lockfile runtime; chỉ dùng Prettier3.9.10 tạm qua npm exec để format các files được sửa (đối chiếu [CLI chính thức](https://prettier.io/docs/cli)), không thêm config/framework. Visual QA desktop/mobile phát hiện thẻ bước tiếp theo thiếu padding; đã sửa spacing, giữ palette/layout cũ.

Fixture foundation mới dùng **một project riêng theo provider mode và scope E2E**, đối chiếu exact name/scope, nhiều kết quả thì fail; lần đầu vẫn tạo qua UI. Mỗi replay dùng CSV bytes mới có UUID ở ID tổng hợp cuối cùng và filename riêng, không approve lại bảng cũ hoặc invalidate canonical đã lưu. Giữ oracle tiền/zero-prefix/null/invalid/zero; không xóa project cũ hoặc thêm API delete. Browser contract tests tạo120projects/80datasets chỉ mock GET; PostgreSQL synthetic schemas vẫn nằm trong server hiện tại rồi tự dọn schema riêng. Hai lần full E2E liên tiếp đã dùng lại cùng project: sau lần đầu projects28 so baseline27; không tạo thêm project theo timestamp ở lần sau. Artifact/job test vẫn tăng có chủ đích, không tuyên bố đã giải quyết retention lịch sử.

Kiểm chứng trước chốt nhóm: toàn suite đầu **33 PASS** (~1,3phút), gồm9foundation+17interface+7reconciliation. Sau bổ sung viewer, full suite **33 PASS/1 FAIL** do test áp `toBeDisabled` lên chính fieldset (DOM đã có disabled); đổi thành kiểm hai source selects thật bị disabled, targeted viewer **1 PASS** (3,5s), không sửa app để che kết quả. Full suite34 trên source/labels chốt sẽ được ghi dưới mục bàn giao. Mọi test có assertion0 uncaught pageerrors; foundation/T35 còn kiểm console errors trên luồng thành công. Mock503/permission denial là kiểm lỗi có chủ đích, không ghi chúng thành live provider PASS.

Backend full vẫn **145 PASS** (120offline+25PG); chạy lại Windows offline **120 PASS, 25 deselected** (10,73s). Bổ sung assertions trong PG T20/T34/T35: summary có latest_verified_run_id đúng run, hai READY dẫn tới RECONCILE; targeted **1 PASS** (4,47s), không tăng catalogue thành146. TypeScript/ESLint/build/Ruff/mypy31 PASS. Đọc lại UI CSV/XLSX và oracle ba pairs production PASS; không đổi golden fixture/engine/verifier. Snapshot sau full E2E đầu: **122foundation+14match+24exports, 28projects/33datasets/28canonical, 114jobs/118attempts/117audits/17traces, 15plans/14contracts/14runs/46cases**. Mọi baseline IDs/metadata/hash trước nhiệm vụ giữ nguyên; evidence JSON tại runtime bị ignore.

### Kiểm tra contrast và giới hạn dialog

Full regression trên runtime `246fe45`: **145 backend PASS, 0 FAIL/SKIP (44,02s)** và **34 E2E PASS, 0 FAIL/SKIP (~1,3phút)**. Bổ sung assertions vào năm cases responsive hiện có: dialog nằm trong viewport, outline focus thấy được, tỷ lệ màu chữ trên nền thực của tên/phạm vi/mã project đang highlight và placeholder ít nhất4,5:1. Regression thực tế phát hiện mã project highlight chỉ **4,3728:1**; đổi riêng màu chữ từ `#64748b` sang `#475569`, giữ nền/palette và hành vi. Sau sửa **5 PASS (10,4s)** trên production frontend vừa build; TypeScript/ESLint/build/source scan PASS. Không tăng số cases vì thêm assertions.

Đối chiếu [WCAG 2.2 SC1.4.3](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) và [ARIA combobox pattern](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/); đây là kiểm tra các màu/interaction cụ thể, chưa phải toàn bộ WCAG/screen-reader audit. Xem ảnh selector390/1440 và Dashboard390, dialog cuộn nội bộ, không cắt control. Restart, recreate toàn bộ và recreate frontend trên runtime246 đều đã PASS metadata/artifact bytes và fail-closed local proof; bản cập nhật contrast sẽ được xác minh lại trên image từ commit sạch trước bàn giao.

### Bàn giao chất lượng — 30/10/2026

#### A. Phân loại phát hiện

- **Confirmed bug:** saved project ngoài trang50 bị bỏ; sidebar đếm page thay tổng; response project/run cũ có thể ghi đè context mới, trong đó evidence đã có regression FAIL trước sửa; focus không trả về trigger của dialog mới; màu mã project highlight4,3728:1. Hai lỗi phát hiện trong quá trình sửa (GROUP BY JSON PostgreSQL và focus dialog) đều được sửa, không còn FAIL trong bộ chốt.
- **UX gap:** READY0 không giải thích PARTIAL/stale/FAILED, thiếu chỉ dẫn đúng dataset/table, số0 lúc chưa tải và lỗi API dễ lẫn empty, role/footer/thuật ngữ khó hiểu, idle polling liên tục.
- **Maintainability concern:** App/ReconciliationStudio gộp nhiều trách nhiệm, JSX dài; tách đúng selector/overview/evidence, giữ state chung của form/results và các phần chưa cần thay.
- **Accepted limitation:** artifacts/jobs tổng hợp vẫn tăng khi replay; chưa cleanup lịch sử hoặc triển khai retention. Các giới hạn AI/accessibility/benchmark còn lại ghi mục G.
- **Not reproduced:** không tìm thấy sai lệch mới trong Decimal, matching, verifier, MetricSnapshot hoặc export khi replay oracle hiện có. Đây không phải chứng minh mọi dữ liệu/thuật toán đều không còn lỗi.

#### B. Thay đổi trước/sau và bằng chứng

| Hạng mục | Trước | Sau | Files chính | Kiểm chứng |
|---|---|---|---|---|
| Project selector | Select cơ bản, khó phân biệt tên trùng | Search tên/phạm vi có dấu, scope/ID, keyboard/ARIA, debounce/abort | ProjectSelector.tsx, components.tsx | 1/10/50/120, Unicode, no-result/error/retry/focus |
| Project pagination/restore | Chỉ trang50, saved ID có thể mất |20/trang, GET theo ID scoped, search literal bounded/stable | api.py, ProjectSelector.tsx, App.tsx | PG120 + browser off-page/reload/foreign404/race |
| Dashboard counts | Sidebar datasets.length; loading fallback0 | Tổng API, loading/error riêng, giải thích nguồn/bảng/job | App.tsx, DataOverview.tsx |80datasets/page25, pending/error/retry |
| Dataset status | READY không giải thích kết quả chưa đạt | PARTIAL/stale/FAILED riêng, invalid/row counts, link xem lỗi | repository.py, contracts/api.py, App.tsx | PG lifecycle và lỗi đúng canonical/table |
| Next action | Thiếu hướng dẫn theo gate | Target deterministic scoped, stable priority; chỉ điều hướng | repository.py, DataOverview.tsx, App.tsx | WAIT/upload/review/normalize/partial/reconcile/verified links; không tự POST |
| Frontend organization | Evidence/API/state lẫn trong file lớn |3 focused components typed props; format rule/results; generation guards | ReconciliationEvidence.tsx, ReconciliationStudio.tsx, types | Delayed evidence regression, T35, giữ draft/run khi đổi màn hình |
| UI wording/accessibility | Footer theo giai đoạn, role/thuật ngữ lẫn; drawer keyboard | Footer sản phẩm, role thật, labels Việt, inert/trap/focus return | App.tsx, MappingStudio.tsx, styles.css, api.ts |5 widths, Escape/Tab/Enter, dialog bounds, outline,4 màu contrast cụ thể |
| Jobs/test fixtures | Poll cả idle, project mới theo timestamp | Poll chỉ active/stop unmount, refresh thật; reuse project, fresh bytes | App.tsx, ReconciliationStudio.tsx, e2e/*.spec.ts | Clock polling/terminal/manual;4 replay pipelines, project28 giữ ổn định |

Backend chỉ thêm read/search/summary DTO, không migration, không thay engine/financial semantics. Trước đó single-project GET thực tế chưa tồn tại; bổ sung đúng endpoint scoped cần khôi phục ID, không tạo API xóa hoặc workflow thứ hai. Schema test tạm nằm trong PostgreSQL hiện có và được harness dọn đúng schema, không là môi trường ứng dụng mới.

#### C. Quality thực tế

| Lệnh/nhóm | Kết quả chốt |
|---|---|
| `./tools/test-postgres.ps1 -All` | **145 PASS, 0 FAIL/SKIP,44,02s** =120offline+25PG; baseline143+2casePG mới |
| `uv run pytest -q -m 'not integration'` | **120 PASS**,25integration deselected,10,73s; không cộng replay vào145 |
| Ruff / mypy | PASS;31 backend/migration files được mypy kiểm |
| `npm --prefix frontend run check` / `lint` / `build` | PASS sau sửa contrast; main378,26kB, lazy reconciliation/chart491,55kB; dependency/lockfile không đổi |
| `$env:STUDIO_EXPECT_AI_PROVIDER='MANUAL'; npm --prefix frontend run test:e2e` | **34 PASS, 0 FAIL/SKIP,~1,2phút** trên image source sạch `ac44915`;9foundation+18interface+7reconciliation, baseline15+19case |
| Browser integration / mock | Foundation/T35 chạy UI→API→worker thật trên local production;18interface cases và Planner UI dùng mocked GET/contracts, không ghi chúng thành live AI |
| Security regression | Workspace/foreign resource/viewer/CSRF/Host/local fail-closed, scoped evidence/export, injection/cloud OFF/quota và worker/recovery trong backend/E2E trên; không cộng thêm cases |
| UI/export read-back và oracle độc lập | PASS cả CSV/XLSX downloads: SHA256, nguyên Snapshot JSON/as-of, zero-prefix, không công thức KPI; Shopee/TikTok/giao nhận đúng membership/amounts/denominators/cases |
| Responsive/accessibility thực chạy |390/768/1366/1440/1920; page overflow, dialog bounds, tables scroll, keyboard/labels/ARIA/status, Escape/focus return/drawer trap;4 mẫu chữ trong selector đều≥4,5:1 (mã highlight sau sửa6,963:1) |

Backend source/tests không đổi từ lần145PASS tại246fe45 sang ac44915; hashes34files trên cả backend/worker khớp source. Frontend chốt chạy lại toàn34 sau thay đổi contrast. Uncaught pageerrors=0 trong từng test; console errors=0 trong các luồng foundation/T35 thành công. Các lỗi HTTP/mock có chủ đích vẫn được kiểm thông báo thật. Cảnh báo Starlette/httpx deprecation và Node color-env còn; không phải test FAIL. Chưa audit mọi màu/trạng thái hoặc chạy screen reader thật; không tuyên bố WCAG toàn bộ PASS.

#### D. Data integrity, cloud và Docker

| Metadata/artifact | Trước nhiệm vụ | Sau bộ chốt |
|---|---:|---:|
| Workspaces / projects |1 /27 |1 /28 |
| Datasets / versions / source tables |32 /32 /30 |36 /36 /34 |
| Schemas / mappings / canonical |64 /64 /27 |72 /72 /31 |
| Jobs / attempts / audits / traces |109 /113 /112 /17 |129 /133 /132 /17 |
| Plans / contracts / runs / cases |14 /13 /13 /43 |18 /17 /17 /55 |
| Foundation / match / export files |118 /13 /22 |134 /17 /30 |

Đã so **từng ID + metadata SHA256 + artifact bytes** của baseline và snapshot sau replay đầu với hiện trạng: nguyên vẹn, chỉ append dữ liệu tổng hợp. VerifiedRun chứa MetricSnapshot, mappings/revisions/approvals, job/run/export lịch sử không bị sửa hoặc xóa. Project count27→28 ở lần đầu, sau đó28 ở cả ba lần replay đầy đủ; không tạo project theo timestamp nữa. Snapshot từ chối khi còn active jobs; không có job active lúc kiểm persistence.

Gemini trước/sau **7/10 attempts**, còn **3**, global/workspace đều7 với ceilings10; planner attempt **1**, LlamaParse reservations **2**, traces **17** không đổi. Model mặc định vẫn `gemini-3.5-flash-lite`; cloud request delta **0**, không reset/tăng budget/reservation, parser creation **OFF** cả env/workspace. Không gọi Qwen/Gemini/LlamaParse/Argon. Qwen vẫn **BLOCKED/DEFERRED** theo chỉ định HTTP403; live planner revision mới vẫn **NOT VERIFIED**. Parser live lịch sử không bị gán thành live request của nhiệm vụ này.

Image sạch build bằng Compose chính với OCI revision/source đúng **ac44915df1610c32fbd82c895b1163a23b65dcf6**. Backend/worker34tracked files mỗi service và4production files phục vụ HTTP đều khớp SHA256 local; không `.env` trong image. Immutable identifiers lấy từ `.Image` của container đang dùng:

| Service | Image ID |
|---|---|
| Backend / worker |`sha256:54e818ae7d52fcfeb01d30e6c4d01d1189eb7e7e330e3fa6b5a5b74cc9830879` |
| Frontend |`sha256:c4cfc088571db643b77ee085edf509cbc84dc4671b8adfb186cd3310515c7b6e` |
| PostgreSQL giữ nguyên |`sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` |

Một Compose project `ai-reconciliation-studio`,4services healthy, chỉ publish127.0.0.1:18180. Giữ volumes `ai-reconciliation-studio_postgres_data` và `ai-reconciliation-studio_artifacts`, cặp rollback-e025094 đã nghiệm thu không đổi. Không rebuild PostgreSQL, xóa containers/image/volume/cache bằng cleanup hoặc global prune. Docker host aggregate lúc kiểm:51images/39,39GB,31containers/574,6MB,36volumes/5,432GB,build cache47,66GB; đây là tổng host, không quy toàn bộ cho dự án hoặc tuyên bố dung lượng đã thu hồi.

Sau full34E2E trên imageac44915, chạy lại `./tools/check-persistence.ps1`: **restart PASS, force-recreate cả bốn PASS, frontend-only recreate PASS**. Mỗi thao tác xác nhận local demo proof bị vô hiệu (403), verify loopback rồi exact metadata/artifact bytes khớp snapshot sau tests; cả4services healthy. Không có job active trước thao tác. Source/assets hashes, oracle/API/export read-back và quota được kiểm lại sau recreate, không request cloud hoặc sửa dữ liệu lịch sử.

Evidence local bị ignore: `runtime/interface-quality-before.json`, `runtime/interface-quality-after-first-e2e.json`, `runtime/interface-quality-after-tests.json`, `runtime/interface-quality-runtime.json`, screenshots/downloads. Persistence không thay backup/restore PostgreSQL; không commit các inventory/raw/runtime này.

#### E. GitHub và files

Nhánh **codex/interface-quality**,25files so main:3backend/API/DTO,11frontend source,4E2E/helper,2backend test files và5Markdown hiện có. Phần lớn diff ReconciliationStudio/reconciliationTypes là format; không thêm dependency/config/framework. Kiểm diff riêng engine/verifier/normalization/schema_mapping/migrations/Compose/locks/Rules/AGENTS/PROJECT_PLAN: rỗng.

| Nhóm commit đã push | SHA |
|---|---|
| Selector/search/restore |`58dc8a0c18387a75e83e2a41c24054f1e625f738` |
| Counts/readiness/next action |`ddceb7dbb43f7da07cc93cd20ca55c4fd3bbb2fb` |
| Scoped evidence/UX/fixtures |`246fe459d127d5c1010c414e9b0cd6faa23719be` |
| Contrast/dialog assertions |`ac44915df1610c32fbd82c895b1163a23b65dcf6` |

Commit báo cáo cuối chỉ sửa Markdown; SHA được báo sau commit, không tự ghi SHA của chính nó vào file. Image giữ source ứng dụngac44915, diff application giữa source này và commit tài liệu phải rỗng. Origin chính thức được đối chiếu/fetch trước push; không force-push/merge/tag mới. Main/origin main giữ **0b9421e1fbbc1e13537b5c5510b3769e387f91a5**; accepted tag targets giữ **78e68c08e60c7af2359e46def43196cf5b1a6dc1** và **be6b8a067ca052ea989a029a15558b0fd5ee48ef**. Repository check111source candidates, known-secret scan trong source/reachable history và Markdown local paths PASS; không đưa runtime/secrets vào stage. Final local/remote HEAD và working tree được xác minh khi bàn giao.

#### F. Đối chiếu Rules.md

Clean Code/trách nhiệm: tách3ranh giới có lợi ích và typed props, không refactor theo số dòng. Contracts/provenance: backend quyết định counts/targets, frontend không tính tiền/KPI hoặc sửa lineage. Không overengineering: dùng Radix/state/API hiện có, không thêm library/service/migration. UX Việt/loading/error/focus và disabled theo quyền đã kiểm; next action thật chỉ điều hướng, không approve/chạy tự động. Permission boundaries vẫn enforce backend, viewer tests/security suite PASS. Docker/Git/scope: một repo/Compose, dữ liệu/rollback giữ nguyên, feature branch đã push từng nhóm, main/tags bảo toàn, không cloud/Giai đoạn3. Đây là đối chiếu phạm vi đã kiểm, không chứng nhận tuân thủ mọi tình huống chưa đo.

#### G. Giới hạn và quyết định

- Retention dữ liệu test: project không tăng tiếp, artifacts/jobs tổng hợp vẫn append; không xóa bằng chứng cũ. Chủ dự án có thể giao chính sách lưu trữ/cleanup có scope riêng.
- App còn lớn; data workspace/settings/setup/results giữ state chung để giảm rủi ro, không coi tách selector/overview/evidence là đã refactor toàn frontend.
- Search ILIKE/paging đã kiểm120projects và80datasets, chưa benchmark search1k/10k hoặc mọi collation. Không tuyên bố khả năng mở rộng từ vài fixtures.
- Keyboard/ARIA/focus/contrast/5widths đã có bằng chứng cụ thể, chưa audit WCAG/screen reader toàn diện. Security regression không thay production penetration test; persistence không thay DR restore drill.
- Qwen live hoãn; Planner revision mới live chưa xác minh; Argon không tích hợp. Mapping/linkage precision/recall đại diện và các giới hạn MVP lịch sử giữ nguyên, không nâng thành PASS bằng UI tests.

**ĐẠT nhiệm vụ hoàn thiện frontend/UX trong phạm vi được giao:** bộ chốt145backend/34E2E không FAIL/SKIP, dữ liệu lịch sử giữ nguyên, không cloud. Đủ để chủ dự án review `codex/interface-quality`; không tự coi đây là quyền merge hoặc production release. **DỪNG sau push báo cáo; chờ lệnh riêng, không merge main, không bắt đầu Giai đoạn3 hoặc Argon.**

## N. Final UX hardening — phân loại project và dữ liệu gần đây

Ủy quyền mới ngày30/10/2026 tiếp tục trên `codex/interface-quality`, baseline8a20c4e/145backend/34E2E; mục M giữ lịch sử. Mục tiêu: phân loại TEST có bằng chứng và ẩn mặc định, quản lý/khôi phục bởi owner, sửa Recent Data, rà UX có giới hạn. Giữ engine/verifier/Decimal/MetricSnapshot/raw/history; không cloud/main merge/Giai đoạn3.

### Thiết kế và kiểm chứng theo nhóm

ProjectRow chưa có classification. Tái sử dụng audit hiện có để lưu nhóm explicit WORK/TEST/UNKNOWN, không migration/bảng/cột mới; legacy không event là UNKNOWN. POST người dùng WORK mặc định; fixtures TEST explicit. PATCH chỉ owner, khóa project và so expected_classification,409 chống stale overwrite; no-op không thêm audit. GET cũ không include_test giữ tương thích; UI gửifalse từ đầu, lọc server trước count/offset/limit, GET theoID không phụ thuộc filter. Selector duy nhất có toggle “Hiển thị dự án kiểm thử” mặc địnhOFF, badge TEST và details quản lý current project có tên/scope/full ID trước xác nhận. Ẩn TEST không đổi project/draft/quyền, restore savedTEST vẫn được; success/error riêng, không retry mutation.

Regression trước sửa backend:2case mới FAIL do thiếuclassification vàtotal120 thay80;25PG cũ PASS. Sau sửa27PG PASS/120offline deselected (32,11s); thêm concurrency test hai owner cùng expectedWORK: một200/một409, toàn28PG PASS (30,29s). Một lần browser23case: option queries cũ đếm lẫn3nativeoptions trong phần phân loại; đã scope listbox thật, không hidden control. Fixture rule-draft mới ban đầu chưa có2nguồn nên không có form; bổ sung catalogue tổng hợp có typed shape. Label nhóm dự án được gắn aria-label rõ; targeted classification1PASS và cả24browser contracts PASS (26,1s). Đây chưa thay full regression cuối.

Recent Data đã tái hiện FAIL:30nguồn, trangDữ liệu thứhai→Tổng quan mấtLatest000. Sửa bằng GETdatasets offset0/limit5 riêng, created_atDESC/idASC stable; không endpoint mới hoặc tải toàn bộ. Loading/error/retry/empty riêng, abort vàproject guard. Browser5/30/80nguồn đều PASS, đúng5mới nhất saupage2; refresh sau nguồn mới cập nhật đúng. Case delayed/error/switch xác nhận responseprojectA không lộởB, lỗi không giả empty.

UX audit mười khu vực hiện có: Tổng quan (recent độc lập, nguồn mới nhất/loading/error), Dữ liệu (nút “Cập nhật trạng thái xử lý” rõGET so với normalize tạojob), Smart Setup (giữ đề xuất/approval/field evidence), Chuẩn hóa (READY/PARTIAL/stale/errors gate cũ), Đối soát (giữ nguồn→scope→approval→run), Ngoại lệ (thêm giải thích trạng thái review không đổi tiền/comparison), Báo cáo (giữ run/kỳ/verified snapshot/as-of/export), Cài đặt (quota/provider/roles thật), Chọn/Tạo dự án (classification gọn), dialogs/thông báo (focus/ARIA). Không redesign hoặc bỏ approval. Rà soát không phát hiện lỗi mới cần sửa matcher/verifier; những kết luận ngoài fixtures vẫn chưa được chứng minh.

Inventory và số liệu bàn giao cuối được ghi sau full regression/persistence; không dùng baseline làm PASS mới.

### A. Project inventory — bằng chứng trước thay đổi

Đầu nhiệm vụ: **28 UNKNOWN** vì chưa có classification event; sau xác minh qua API: **28 TEST,0 WORK,0 UNKNOWN**, tổng28 giữ nguyên. Không gán WORK chỉ dựa vào tên. Tất cả thuộc workspace `demo`, dataset owner `demo-owner`; inventory local còn lưu created_at UTC, scopes, dataset IDs/hash, jobs/runs/audit refs. Không có project nào cần chủ dự án xác nhận ở tập28 này; project cũ khác không có bằng chứng vẫn mặc địnhUNKNOWN.

| Project ID | Tên | Nguồn gốc đã xác minh | Nhóm đề xuất/đã áp dụng | Chắc chắn |
|---|---|---|---|---|
| `abe40c9c-d47b-4a2f-8f80-d34888df2d7c` | Dữ liệu tổng hợp · 1793127566266 | E1 | TEST | Cao |
| `1adf15a2-f0cf-4a1a-b918-32be666d8928` | Dữ liệu tổng hợp · 1793127840245 | E1 | TEST | Cao |
| `b13895e2-12fc-45ee-897e-7fa650909031` | Dữ liệu tổng hợp · 1793128199903 | E1 | TEST | Cao |
| `c28360f8-78cc-4723-8f91-b089375e41cb` | Dữ liệu tổng hợp · 1793128391092 | E1 | TEST | Cao |
| `1e0cd1d9-b763-4964-b7a1-4132bc61c5c7` | Dữ liệu tổng hợp · 1793129148032 | E1 | TEST | Cao |
| `42773d37-9a65-421b-8fd3-866b3a3a1c06` | Dữ liệu tổng hợp · 1793129956994 | E1 | TEST | Cao |
| `4997a82a-fc08-42fe-b97a-a0db1bd6c113` | Kiểm tra khôi phục worker | E2 | TEST | Cao |
| `b77b6551-e1fa-40b2-97ef-0a688c015457` | Dữ liệu tổng hợp · 1793131631604 | E1 | TEST | Cao |
| `5c955869-30b3-4db6-8dc1-f7660647a3d1` | Dữ liệu tổng hợp · 1793147126220 | E1 | TEST | Cao |
| `fa7e7d2e-f821-46d7-920e-6b66c1c852be` | Dữ liệu tổng hợp · 1793147302189 | E1 | TEST | Cao |
| `ec4b72ae-a585-491e-abe3-980aac0363ac` | Dữ liệu tổng hợp · 1793147602813 | E1 | TEST | Cao |
| `1e84ddc0-e55e-4827-9407-d5dc17777de4` | Dữ liệu tổng hợp · 1793147655037 | E1 | TEST | Cao |
| `5b655b89-8b0e-4e0d-98b9-e365530bedac` | Kiểm tra tài liệu tổng hợp | E3 | TEST | Cao |
| `d125b6eb-0d25-48cc-a7f0-54beaa946fae` | Dữ liệu tổng hợp · 1793155126628 | E1 | TEST | Cao |
| `c573e971-295d-47a7-a3a3-94c13b3e675f` | Kiểm tra khôi phục worker | E2 | TEST | Cao |
| `8a3bc325-022c-4101-bd86-d8d57b2f48a7` | Dữ liệu tổng hợp · 1793155302402 | E1 | TEST | Cao |
| `29b91f9d-aa22-4791-a44f-52c0c760af2b` | Dữ liệu tổng hợp · 1793157445350 | E1 | TEST | Cao |
| `2358398f-c3d7-4b13-a971-5b40fcac7f2d` | Kiểm tra khôi phục worker | E2 | TEST | Cao |
| `e1c05f6d-1553-46c6-b1a7-45a191706f27` | Dữ liệu tổng hợp · 1793159064934 | E1 | TEST | Cao |
| `faa4f9b1-298a-4333-9b82-c7b939d84774` | Đối soát tổng hợp có oracle | E4 | TEST | Cao |
| `17fba5e0-de6e-4ed2-9fc0-b97a52787807` | Dữ liệu tổng hợp · 1793161569604 | E1 | TEST | Cao |
| `0a5de3e6-2781-4faf-b42b-24292c09184e` | Dữ liệu tổng hợp · 1793161842836 | E1 | TEST | Cao |
| `afa10789-3729-49f5-8676-d5f28a244ad3` | Dữ liệu tổng hợp · 1793162175280 | E1 | TEST | Cao |
| `9c9d30a7-fbd3-44df-89a9-bc17d602505c` | Dữ liệu tổng hợp · 1793175086889 | E1 | TEST | Cao |
| `1b583f85-079f-4e63-bd81-2e3af5dca0c9` | Dữ liệu tổng hợp · 1793180785335 | E1 | TEST | Cao |
| `dcf47c99-7c40-41fa-8515-75a09b6c7626` | Dữ liệu tổng hợp · 1793181069922 | E1 | TEST | Cao |
| `30494cd1-f40e-4075-9408-4b9f87f28614` | Dữ liệu tổng hợp · 1793285254493 | E1 | TEST | Cao |
| `87abdb34-f8e5-4b0a-bb81-8f1fb527391b` | Kiểm thử giao diện · MANUAL | E5 | TEST | Cao |

Bằng chứng (không dùng tên làm bằng chứng duy nhất):

- **E1 (22project):** raw `synthetic-orders.csv` có SHA256 đúng từng byte `6428223f30041b371725896b9d3b944e964e9783cfff18e55c8f842f0006c18d`, cùng fixture E2E trong lịch sử source32741ae/0b9421e; scopes kiểm thử, owner demo và parse/mapping/normalize jobs. Created_at cách timestamp harness0,79–7,88giây; hai scopes ban đầu không chứa timestamp vẫn có checksum/file/ownership/jobs xác nhận.
- **E2 (3project):** exact75000-row synthetic-recovery.csv SHA256 `c2c28b5665c82b099155eeb20493abcf9e4aa47003ef5fedaa483e2b5ff57cb9`, scopeUUID đúng worker-recovery harness, ownership/job recovery; runtime/worker-recovery.json xác định một projectID cuối.
- **E3:** projectID từ document-acceptance/acceptance.json, cả hai PDF/DOCX tổng hợp tại local có SHA256 khớp dataset refs; cached extraction/jobs giữ nguyên, không gọi parser lại.
- **E4:** projectID/datasetIDs từ reconciliation-acceptance.json, năm raw fixture CSV khớp SHA256 bytesLF trong Git (checkout Windows cóCRLF); không sửa raw để đối chiếu. Verified runs/oracle và jobs nguồn giữ nguyên.
- **E5:** project có scope ổn định E2E_MANUAL_INTEGRITY từ246fe45; cả4filenameUUID/CSVbytes dựng theo fixture hiện hành đều khớp SHA256 dataset, ownership/jobs và báo cáo M xác nhận4replays.

Đã phân loại một lần bằng28PATCH explicitID qua session owner hiện có. So trước/sau: **chỉ append28 PROJECT_CLASSIFIED_TEST audit events**, project metadata gốc và mọi metadata/artifact hash khác bằng nhau. Không SQL UPDATE/DELETE; không background classifier hoặc tự phân loại project tương lai từ tên. Một lần gọi trước local proof hoàn tất trả403, chưa ghi metadata; chỉ thực hiện sau verify-local thành công. Người dùng có thể mở TEST, xem tên/phạm vi/ID rồi xác nhậnWORK/UNKNOWN qua UI; việc này không xóa hoặc đổi quyền.

### Kết quả chốt source trước deploy có revision

**149 backend PASS,0 FAIL/SKIP (38,26s)** =120offline+29PG; baseline145 tăng4cases (hai classification, một concurrent owners, một dataset tie-order/scope). Offline Windows **120 PASS/29deselected,5,21s**. **41 E2E PASS,0 FAIL/SKIP (~1,4phút)** =9foundation+25interface+7reconciliation; baseline34 tăng7cases. Ruff/mypy28/TypeScript/ESLint/build PASS. Không cộng full40 và targeted replays thành sốcases mới.

Case mới tái hiện metadata classification không cập nhật khi selector unmount lúc PATCH đang chạy: FAIL trước sửa; parent nhận confirmed DTO có guard currentID, component chỉ set local state khi còn mounted, sau sửa targeted1PASS/4,3s và full41PASS. Không retry write hoặc hủy job backend. Bộ full có cả luồng thật upload→mappingapprove→normalize→manualruleapprove→verifiedrun→evidence/review→CSV/XLSX→reopen, provider MANUAL; Planner và interface contract fixtures là MOCK, không liveAI. Một read-back chạy khi T35 còn ghi downloads/manifest đã thấy hash khác; đợi toàn suite hoàn tất rồi đọc lại đúng cặp files/manifest, không sửa checksum/oracle hoặc bytes backend để hợp thức hóa.

Giữ keyword/source/module contracts, dependencies/locks/Compose/migrations/engine/verifier/formulas. Năm widths390/768/1366/1440/1920, keyboard/focus/ARIA/drawer/dialog bounds/contrast samples tiếp tục PASS. Báo cáo deploy/persistence/Git cuối được bổ sung sau khi commit source sạch; chưa coi healthcheck thay cho revision/hash verification.

### B. Các sửa đổi và bằng chứng

| Vấn đề | Nguyên nhân | Sửa đổi | Bằng chứng |
|---|---|---|---|
| Danh sách project lẫn dữ liệu thử | Chưa có metadata mục đích | Audit classification explicit; toggle TEST mặc định OFF; owner đổi/khôi phục có ID và audit | 120 project PG filter/count/paging, UNKNOWN visible, Unicode/scopes; browser toggle/current TEST/restore/draft |
| Recent Data lấy nguồn trang hai | Chia sẻ mảng25items của Data Explorer | Bounded GET riêng5nguồn mới nhất, tie-order ổn định | Regression30nguồn FAIL trước sửa;5/30/80PASS, page2/refresh/new source/error/delay/switch |
| Nhãn thao tác khó phân biệt | Nút hoạt động xử lý chỉ ghi “Cập nhật” | “Cập nhật trạng thái xử lý”; normalize/AI/approve/run giữ hành động riêng | Foundation thật và test polling/manualGET; không tạo job/AI khi refresh |
| Review dễ bị hiểu là sửa tiền | Phải giải thích ngay nơi đổi trạng thái | Thêm câu review không đổi comparison/tiền | T35 RESOLVED giữ immutable Snapshot, CSV/XLSX/oracle |
| Phân loại đang lưu khi rời selector | Component không nhận kết quả sau unmount | Parent nhận confirmed DTO với guard ID; không set local state khi unmounted | Targeted FAIL→PASS và full41PASS; không mất draft/chuyển ngầm |
| Bằng chứng ảnh Dashboard chụp loading | Chỉ đợi shell heading, chưa đợi dataset | Đợi nút nguồn thật trước overflow/screenshot | Kiểm lại nhóm foundation9 trên image8789940; ảnh đọc nội dung sau tải |

Files theo trách nhiệm: backend `access.py`, `api.py`, `contracts/__init__.py`, `repository.py`; frontend `App.tsx`, `ProjectSelector.tsx`, `DataOverview.tsx`, `ReconciliationEvidence.tsx`, `styles.css`, `types.ts`; regression trong3E2E/helper và `test_postgres.py`;3tools tạofixture thêm TEST explicit; README/ARCHITECTURE/DATA_CONTRACTS/TESTING_GUIDE/báo cáo. Không thêm framework, dependency, service, migration hoặc module chức năng mới.

### C. Quality và số đo thực tế

| Nhóm | Kết quả |
|---|---|
| Backend đầy đủ trên PostgreSQL hiện có | **149 PASS,0 FAIL/SKIP,38,26s**;120offline+29PG; baseline145+4 |
| Offline Windows | **120 PASS**,29integration deselected,5,21s |
| Ruff / mypy | PASS; `ruff check backend tests tools`, `mypy backend/studio`28sourcefiles; không đổi migrations |
| TypeScript / ESLint / production build | PASS; bundle main382,50kB, lazy reconciliation/chart491,74kB; không nâng threshold/đổi locks |
| Full Playwright MANUAL | **41 PASS,0 FAIL/SKIP,~1,4phút**;9foundation+25interface+7reconciliation, baseline34+7 |
| Mock/live phân biệt | Browser classification/recent cases và Planner dùng synthetic MOCK; foundation/T35 chạy thật API/worker local;0liveprovider |
| Security | Owner-only classification, viewer/editordenial, foreign404, expected-state409 và concurrent-write guard; session/CSRF/Host/workspace/file/export/cloud OFF/lease/recovery cũ giữ PASS |
| Independent read-back | Sau toàn suite: CSV/XLSX UI checksum, Snapshot JSON/as-of/zero-prefix và oracle Shopee/TikTok/giao nhận PASS; không FE tính lại KPI |
| Responsive/accessibility |5widths, keyboard/Enter/Escape/focus-return, drawer trap, labels/status/alert, dialog bounds và4mẫu contrast;0uncaught errors trong từngcase. Không audit WCAG toàn diện/screen reader thực |

Recent browser fixtures đếm **2request limit5**: vàoDashboard lầnđầu + quay lại từData; refresh sau thêm nguồn thành **3**, tất cảoffset0. Không tải toàn bộ80nguồn, không request recent khi ở trangData/settings, idle polling vẫn dừng. Đo riêng API production local bằng5GET/route, HTTPclientkeepalive: defaultfiltered p50/p95 **68,49/88,52ms** (0visible), includeTEST+searchMANUAL **64,70/73,50ms** (1match), recentlimit5 **45,60/64,70ms** (project lúcđó4nguồn). p95 nội suy inclusive chỉ5samples, không benchmark sức tải/1kprojects; có lưu raw timings local.

### D. Dữ liệu, AI và vận hành

Trước nhiệm vụ:28projects/36datasets/34tables,72schemas/mappings,31canonical;129jobs/133attempts/132audits/17traces;18plans/17contracts/17runs/55cases;134foundation+17match+30exportfiles. Phân loại chỉ append28audits, không đổi bất kỳ metadatahash lịch sử. Sau hai fullreplays:28projects/38datasets/36tables,76schemas/mappings,33canonical;139jobs/143attempts/170audits/17traces;20plans/19contracts/19runs/61cases;142foundation+19match+34exportfiles. Snapshot từngID/metadata/hash trước và sau replayđầu đều là subset nguyên vẹn của hiện trạng. Historical ProjectRow, mappings/revisions, Canonical, VerifiedRun/MetricSnapshot, reviews và exports giữ nguyên.

Delta một fullreplay đo được: **0project**, +1dataset/version/table/canonical, +2schema/mapping, +5jobs/attempts/audits, +1plan/contract/run/matchfile, +3cases, +4foundationfiles và+2exportfiles,0traces. Đây là dữ liệu tổng hợp cần giữ để tái kiểm chứng, chưa có phân loại file “tạm có thể xóa” được chủ dự án duyệt. Không SQL DELETE hoặc cleanup job. Đề xuất sau này: chủ workspace xác định thời hạn giữ theo projectTEST/run, pins cho nghiệm thu, dry-run đầy đủ refs trước mọi xóa; không triển khai trong nhiệm vụ này.

Gemini global/workspace trước và sau **7/10**, còn **3**, model `gemini-3.5-flash-lite` giữ nguyên; plannerattempt1, parserreservations2, traces17; parsercreationOFF cảenv/policy. **Cloud delta0**, không provider fallback, reset/tăngquota hoặc tìmkey ở dự án khác. Qwen403 giữ **BLOCKED/DEFERRED**; Planner revision mới LIVE **NOT VERIFIED**; PDF/DOCX chỉ đọc cached extraction, không live request mới; Argon/Giai đoạn3 không triển khai.

Source ứng dụng đã push **87899400903875663258dda2e12b05b186eee97f**, build từ câytracked sạch với OCI source/revision. **34backendfiles ×2services** và **4HTTPservedfrontendfiles** khớp SHA256 source/build; không `.env` trongimage. Cặp rollback-e025094 giữ nguyên; PostgreSQL immutable ID không đổi. Không suy revision từ cachedCreated timestamp.

| Service | Immutable image ID |
|---|---|
| Backend/worker |`sha256:c3c8183437647aa1cb7df6f3d2b31a23ff4ddd22f3eede8e7878d6f1c58995b2` |
| Frontend |`sha256:cbba7e5bd7743f8dcb407df924b5bdf46fa5010e8ecdd959809ece0626091de8` |
| PostgreSQL |`sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` |

Trên source8789940, saufull41: **restart PASS, force-recreate4services PASS, frontend-onlyrecreate PASS**. Mỗi lượt localproof bị vôhiệu đúngthiếtkế, `/api/session`403 trướcverify, sauverify đọc/so metadata vàartifactbytes khớp hoàn toàn snapshot142foundation/19match/34exports. MộtComposeproject `ai-reconciliation-studio`,4/4healthy, chỉpublish127.0.0.1:18180; giữhai volumesPostgreSQL/artifacts. Không rebuildPostgreSQL, dọnimage/cache hoặc xóa tài nguyên khác. Đây là persistencecheck, khôngDRrestoredrill.

Số đo Docker host cuối: 51 images/39,39GB; 31 containers/574,6MB; 36 volumes/5,667GB; build cache47,69GB. Đây là tổng host có tài nguyên khác, không quy toàn bộ cho ứng dụng và không tuyên bố đã giải phóng dung lượng. Không thực hiện cleanup images/cache/volumes trong nhiệm vụ này.

Evidence local ignored: `runtime/project-visibility-before.json`, `project-visibility-inventory.json`, `project-visibility-after-classification.json`, `project-visibility-after-first-replay.json`, `project-visibility-after-tests.json`, `project-visibility-runtime.json`, `project-navigation-measurements.json`, screenshots/downloads. Không commit dữ liệu runtime.

Sau khi xem ảnh, phát hiện test Dashboard chỉ đợi shell heading nên có ảnh còn loading. Chỉ sửa assertion chờ nút nguồn thật trước overflow/screenshot; không sửa ứng dụng. Chạy lại foundation **9 PASS,0 FAIL/SKIP,31,1s** trên image source8789940; đã xem ảnh Dashboard1440 có đủ counters, next action và đúng5nguồn mới nhất, cùng selector390. Catalogue vẫn **41 cases**, không cộng replay thành50. Snapshot cuối `project-visibility-after-visual.json`: **28projects/39datasets/37tables,78schemas/mappings,34canonical;141jobs/145attempts/172audits/17traces;20plans/19contracts/19runs/61cases;146foundation+19match+34exportfiles**. Phần tăng riêng foundation là1dataset/canonical,2jobs/attempts/audits,4foundationfiles; không có run/export/project mới. So từng ID/metadata/checksum của baseline và snapshot full41 với hiện trạng cuối đều PASS; quota và read-back/oracle tiếp tục không đổi.

### E. GitHub và đối chiếu quy tắc

Nhánh **codex/interface-quality**; commit source **87899400903875663258dda2e12b05b186eee97f** đã push đúng origin chính thức. Diff nhiệm vụ gồm 22 files, source/tests/docs đúng phạm vi. Commit cuối bổ sung báo cáo và assertion chờ nội dung trước khi chụp ảnh; application files so với 8789940 không đổi, runtime giữ revision ứng dụng này. SHA HEAD cuối được báo sau commit. Working tree và local/remote HEAD được kiểm chốt khi bàn giao.

Main/origin main giữ **0b9421e1fbbc1e13537b5c5510b3769e387f91a5**; acceptance tags giữ targets **78e68c08e60c7af2359e46def43196cf5b1a6dc1** và **be6b8a067ca052ea989a029a15558b0fd5ee48ef**. Không merge, tạo tag, force-push, reset, worktree hoặc Compose khác. Diff nhiệm vụ của engine/verification/normalization/schema_mapping/reconciliation_contracts/migrations/locks/Compose/Rules/AGENTS/PROJECT_PLAN rỗng. Scan 111 source candidates, known secrets trong reachable history, local Markdown paths và whitespace PASS; inventory chỉ chứa thông tin tổng hợp đã xác minh, không credentials hoặc dữ liệu khách hàng.

Đã đối chiếu Rules trong phạm vi: DTO bổ sung có kiểu, backend là nguồn sự thật, quyền owner độc lập với ẩn/hiện, audit chỉ thêm và lookup có scope; provenance và lịch sử tài chính bất biến giữ nguyên. Tái sử dụng component/audit, không thêm framework; UX Việt và CTA thật, không bỏ approval. Git/Docker/cloud/phạm vi theo chỉ định. Không tuyên bố tuân thủ hoàn hảo các tình huống chưa đo.

### F. Known limitations và quyết định

- Cả 28 project trong inventory đều đủ bằng chứng TEST; không tự tạo WORK để làm đẹp số liệu. Project lịch sử khác thiếu bằng chứng phải giữ UNKNOWN và đợi owner; không có bộ phân loại runtime theo tên.
- Truy vấn phân loại đọc audit events bằng correlated subquery; đã đo 28 project, integration kiểm 120 project, chưa benchmark 1k/10k hoặc cạnh tranh nhiều owner. Chỉ xem xét index/migration khi số đo thực tế cho thấy cần thiết.
- Retention chỉ được đo và đề xuất; artifacts/jobs tổng hợp vẫn tăng. Không xóa dữ liệu hoặc bằng chứng cũ; persistence/regression không thay kiểm tra khôi phục backup hoặc kiểm toán bảo mật production.
- Accessibility mới kiểm interactions, viewport và contrast cụ thể; chưa chứng nhận toàn bộ WCAG 2.2 AA. App vẫn giữ orchestration/state cần thiết, không refactor máy móc theo số dòng.
- Qwen live, Planner revision mới live, precision/recall đại diện và các giới hạn MVP lịch sử giữ nguyên. Không mở cloud, Argon, Assistant hoặc Giai đoạn 3.

**ĐẠT Final UX hardening trong phạm vi được giao:** TEST ẩn mặc định và có thể mở lại; UNKNOWN không bị ẩn; lựa chọn/bản nháp không đổi ngầm; Recent Data đúng nguồn/project; **149 backend / 41 E2E PASS**, không cloud, lịch sử nguyên vẹn. Đủ để chủ dự án review branch, chưa là quyền merge hoặc release production. **DỪNG sau push báo cáo, chờ review; không merge main hoặc triển khai Giai đoạn 3.**

## O. Hợp nhất UX và Docker release — 30/10/2026

### A. UX merge — PASS

- Baseline thực: main `0b9421e1fbbc1e13537b5c5510b3769e387f91a5`, UX `4b854c631e9cfb68c664b7fc57186281da906976`, ahead 7/behind 0, working tree sạch; origin chính thức đã fetch.
- `tools/test-postgres.ps1 -All`: **149 PASS**, một cảnh báo deprecation Starlette/httpx. Ruff toàn backend/tests/tools, mypy 31 source files, TypeScript, ESLint, production build, repository/history/Markdown scan và diff check PASS.
- Playwright MANUAL: **41 PASS / 0 FAIL / 0 skipped**, 90,599 giây. Lượt trước đó thất bại vì demo chưa được xác minh sau khởi động lại, bị chặn đúng chính sách; chạy `verify-local.ps1` rồi replay toàn bộ, không bỏ auth hay sửa expected values.
- CSV/XLSX đọc lại đúng snapshot/checksum/timestamp/zero-prefix; oracle độc lập Shopee/TikTok/giao nhận, membership/population/cases và historical exports PASS.
- Merge `--no-ff`: **`5f358c487f7f29482951aff1cc5aa757a5f9f1ec`**; tree khớp hoàn toàn UX đã kiểm thử, không conflict. Đã push/fetch, main local = origin/main; UX HEAD là ancestor, không còn unique commits/open PR, đã xóa branch UX bằng normal delete.
- Tags không đổi: `data-foundation-accepted-20261028` trỏ `78e68c08e60c7af2359e46def43196cf5b1a6dc1`, `reconciliation-engine-accepted-20261029` trỏ `be6b8a067ca052ea989a029a15558b0fd5ee48ef` (peeled targets, không nhầm với annotated-tag object IDs).

### B. Docker main — PASS

Build sạch từ main `5f358c4` với `BUILDX_GIT_LABELS=full`; Compose/network/volumes/healthchecks không đổi, không rebuild PostgreSQL. Backend/Worker chung image. OCI source/revision và 34 source hashes trong cả Backend/Worker, bốn frontend assets qua HTTP khớp build local.

| Thành phần | Immutable image ID | Bảo vệ |
|---|---|---|
| Backend/Worker | `sha256:7a00801051416c143e0d0199919bb9a43fa319a01fd01b1a8010b1d5d8781e29` | `ai-reconciliation-studio-backend:accepted-main-5f358c4` |
| Frontend | `sha256:1049ba4457ebad8971d0be29cb523b7429714fb2c3dc1abcd28a9ef1a40ab215` | `ai-reconciliation-studio-frontend:accepted-main-5f358c4` |
| PostgreSQL | `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` | Giữ nguyên |
| Rollback Backend | `sha256:c966a65d026417d8e2a7e7662f8ab888aca582fd1a59aa319a12f6abd396f553` | `rollback-e025094`, không ghi đè |
| Rollback Frontend | `sha256:57a48c3e6ff1bedf63162b71e3a8d1292af421d177a4e7afa50dedfd31a54979` | `rollback-e025094`, không ghi đè |

- Runtime trước build `8789940` khác UX HEAD chỉ tests/docs; source hashes và served assets đã đối chiếu. Runtime mới đúng main merge. Rollback `e025094` có cùng hai migrations, dependencies và Compose với main mới: không cần downgrade/xóa dữ liệu. Chưa chạy đổi runtime về rollback trong nhiệm vụ này, không gọi đây là restore drill.
- Playwright trên image main mới: **41 PASS / 0 FAIL / 0 skipped**, 85,334 giây. Golden/report read-back PASS.
- `check-persistence.ps1`: restart, force-recreate bốn service và frontend-only recreate đều **PASS**; mỗi lần `/api/session` trả 403 trước xác minh loopback, sau `verify-local.ps1` truy cập bình thường. 4/4 healthy, chỉ publish `127.0.0.1:18180`.
- Giữ `ai-reconciliation-studio_postgres_data` và `ai-reconciliation-studio_artifacts`. Snapshot trước/sau xác nhận **mọi record/artifact lịch sử giữ nguyên ID, metadata hash và SHA256**; hai replay chỉ thêm dữ liệu tổng hợp trong project TEST đã có.
- Thực tế sau gates: 28 projects, 41 datasets/versions, 39 tables, 82 schemas/mappings, 36 canonical, 151 jobs/155 attempts, 182 audits/17 AI traces, 22 plans/21 contracts/21 runs, 67 cases/38 exports; 154 foundation artifacts/21 run artifacts/38 export files.
- Gemini mặc định `gemini-3.5-flash-lite`, vẫn **7/10 attempts, còn 3**; không request mới/reset/tăng quota. Qwen hoãn HTTP 403; LlamaParse không tạo job mới; Argon research only.

### C. Docker inventory/cleanup — PASS trong phạm vi an toàn

Đã inventory toàn bộ 51 image IDs và tham chiếu của 31 containers (running và stopped), bảo vệ current/accepted/rollback. Không có old project image không tham chiếu đủ điều kiện xóa; **0 image bị xóa bằng cleanup**. Giữ toàn bộ image không rõ ownership, dự án khác, PostgreSQL, cache và volumes. Hai tag `local` được build thay source theo quy trình Docker; không ghi việc thay tag là cleanup thu hồi storage.

Host trước/sau: 51 images, 39,39 GB; 31 containers; build cache khoảng 47,55 GB. Volume allocation thay đổi trong quá trình test (6,950 → 6,677 GB), không xóa volume và không quy biến động này thành dung lượng thu hồi. **Physical bytes reclaimed: NOT VERIFIED**. Other/unknown image IDs giữ nguyên; 4/4 healthy, lịch sử/evidence/exports và quota kiểm tra lại PASS. Inventory runtime/receipts nằm ngoài Git.

**Cổng A và B đạt.** Được bắt đầu Giai đoạn 3 theo prompt mới trên feature branch; main chỉ giữ UX/release đã nghiệm thu. Chưa có code hoặc kết luận nghiệm thu Assistant trong mốc này.

## P. Assistant, automation và release candidate — 30/10/2026

### A. UX merge và Git

Cổng A/B được hoàn tất trước dòng code Assistant đầu tiên, bằng chứng chi tiết tại mục O. Main trước `0b9421e`, merge UX `--no-ff` tại `5f358c487f7f29482951aff1cc5aa757a5f9f1ec`, báo cáo main tại `eefdd4441d7f7ef52b08e7d35d3c68894de191dd`; đã push/fetch chính thức. UX HEAD `4b854c6` là ancestor; branch đã xóa an toàn sau kiểm tra không có PR/unique commits. Hai acceptance tags cũ không đổi. Giai đoạn 3 chỉ trên `codex/assistant-automation`, từ main đã nghiệm thu; không merge vào main.

Các nhóm đã commit/push: `9ffbf0f` (tools/FactSet/validation), `482ee1c` (hội thoại/queue), `ff00ec9` (panel/workflow), `9c565a6` (templates/restore verification), **`9802545b8a0281cc608f29d1d8b4ffd3444c454b`** (visible context/recovery docs). Commit bàn giao sau cùng chỉ cập nhật tài liệu; runtime vẫn ghi đúng source code `9802545`. Không force-push, worktree, clone, dependency/framework hay Compose project mới.

### B. Docker và phiên bản runtime

| Thành phần | Image ID cuối | Trạng thái |
|---|---|---|
| Backend/Worker | `sha256:a81b192d549497881249036c717d577cf130fe16a46d137351cb6a98f7a1f357` | Chung image, `candidate-9802545` |
| Frontend | `sha256:453b653abb403b4965989951b796eec73eda0a5d512e79cba487a91ff2c3ae2b` | `candidate-9802545` |
| PostgreSQL | `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` | Giữ nguyên image/volume |

OCI source chính thức và revision `9802545` đã đối chiếu; **40 tracked source hashes** trong cả Backend/Worker và **6 frontend assets qua HTTP** khớp build local. 4/4 healthy; chỉ `127.0.0.1:18180`, không publish Backend/PG. Giữ nguyên `ai-reconciliation-studio_postgres_data`/`ai-reconciliation-studio_artifacts` và network. Runtime candidate không được gọi là accepted main.

Giữ hai image main `accepted-main-5f358c4` (IDs tại mục O) và bộ `rollback-e025094`, không ghi đè. **Rollback drill PASS LOCAL**: chạy main trên schema additive bằng `tools/rollback.ps1`, kiểm lại historical golden/evidence/CSV/XLSX, quay lại candidate và đối chiếu metadata/artifacts/hội thoại không đổi. Startup override chỉ tránh Alembic cũ không biết revision mới; không downgrade/xóa schema hay financial data.

Inventory cleanup tại Cổng B: **0 image được xóa**, không có candidate đủ điều kiện. Cuối nhiệm vụ Docker host có **53 images/39,39 GB, 31 containers, 36 volumes khoảng 7,19 GB, build cache khoảng 47,57 GB**; các số là toàn host, không phải riêng ứng dụng. Không prune cache/volumes/unknown/other-project images. Physical bytes reclaimed **NOT VERIFIED**, không nhận biến động allocation làm dung lượng thu hồi. Đối chiếu cuối thấy **45/47 image ngoài dự án giữ nguyên ID, hai image ngoài dự án đổi ID tại các tags đang có** trong thời gian nhiệm vụ; không có thao tác sửa/xóa của nhiệm vụ này lên chúng. Nguyên nhân/chủ thể thay đổi và tính ổn định của hai image ngoài phạm vi: **NOT VERIFIED**; không tự khôi phục hoặc can thiệp. Bằng chứng kiểm inventory ở Cổng B vẫn là checkpoint lịch sử, không suy ra toàn host bất biến đến cuối nhiệm vụ. Các bộ image chính/rollback của ứng dụng được kiểm lại, không đổi.

### C. Chức năng Giai đoạn 3

| Hạng mục | Kết quả thực |
|---|---|
| Bảy typed read-only tools | **PASS LOCAL/CONTRACT**: allowlist đóng; auth/workspace/project/run/case/group, pagination, SQL/evidence timeouts; không SQL/code/path/write tools từ model |
| Verified AnswerFactSet | **PASS LOCAL**: content hash, business scope, snapshot/period/currency/rule revision, group/member/source refs; copy đúng số liệu đã verified |
| Answer validation/Gateway | **PASS LOCAL + PASS MOCK**: model chỉ chọn facts/claim codes; reject fake IDs, amounts/prose ngoài schema và unsupported claims; dùng một Gateway, một HTTP attempt tối đa khi được phép |
| Contextual panel | **PASS LOCAL E2E**: sidebar, dataset/run/group/case, source citations/evidence/rule/report; abort/sequence chặn stale responses; phân biệt facts, supported interpretation, hypothesis, unknown/insufficient |
| Persistent conversations | **PASS LOCAL/PG**: private theo actor/project, immutable context, messages/claims/refs/timestamps, cursor pagination, reopen, idempotency, xóa nội dung/tombstone/audit đúng quyền |
| Language workflows | **PASS LOCAL**: yêu cầu hai/ba nguồn tạo review proposal; thiếu năm/kỳ/coverage hỏi xác nhận; chọn READY sources/rule đã duyệt; hai cặp cho ba nguồn; reuse qua API cũ, kiểm signatures, idempotency; vẫn phải kiểm tra/lưu/duyệt trước run |
| Smart suggestions/cache | **PASS LOCAL**: navigation evidence/exception/rule/data/report; reuse chỉ deterministic answer cùng context/FactSet/question, không cache mơ hồ thành confirmed |
| Cost/security/reliability | **PASS LOCAL + MOCK** trong các cases bên dưới; không reset quota, không blind retry khi delivery chưa rõ, không duplicate response/action |

Migration additive duy nhất `create_conversations` thêm `conversations` và `conversation_messages`; historical migrations không đổi. Backend module chính: `contracts/assistant.py`, `assistant_tools.py`, `assistant.py`, `assistant_api.py`, `assistant_jobs.py`; frontend: `AssistantStudio.tsx`, `AssistantWorkflow.tsx`, `assistantTypes.ts`, integration nhỏ trong App/ReconciliationStudio/Modal. Dùng queue/auth/session/AI Gateway/API approved templates có sẵn; không sửa matcher, verifier, normalization, tiền, semantic contracts, lockfiles hoặc kế hoạch ba giai đoạn.

### D. Kiểm thử và hiệu năng

- **176 backend PASS / 0 FAIL / 0 skipped**: 138 offline + 38 PostgreSQL trên UUID schemas thuộc PG hiện có. T01–T40 nằm trong suite, không cộng thêm. Lượt runtime backend tại `9c565a6`: 60,34 giây; Backend/migrations không đổi byte sang source cuối `9802545`, source/container hashes đã xác minh. Một cảnh báo deprecation Starlette/TestClient/httpx còn giữ, không đổi dependency ngoài nhiệm vụ.
- **54 Playwright PASS / 0 FAIL / 0 skipped / 0 flaky**, 145,758 giây trên images `9802545`: 9 foundation + 25 UX + 7 reconciliation + 13 Assistant. TypeScript, ESLint, production build, Ruff toàn backend/tests/tools, mypy **37 source files**, diff và repository/credential/history/Markdown scans PASS.
- T36–T40: cloud OFF không request; ID/claim giả reject; cross-project/actor/cursor và late response không leak; missing metric không tạo KPI; delivery **12.75 − 10.00 = 2.75 VND**, Shopee delta **10.00**, TikTok **EQUAL** đúng oracle, không bịa phí/nguyên nhân. Tests transport Gemini thành công/timeout/invalid output dùng **MOCK**, không phải live.
- Luồng ba file thực: upload UI ba fixtures mới → approval/normalization qua API có auth → đề xuất hai cặp → UI xác nhận nguồn/kỳ/coverage → kiểm tra/lưu/duyệt → verified run → hỏi vì sao lệch → export CSV. Suite foundation riêng tiếp tục kiểm Smart Setup/approval/normalization trên UI; suite reconciliation kiểm evidence/review/CSV và XLSX. Không dùng fixture chứa lỗi như nguồn READY, không sửa oracle để tạo mismatch giả.
- SIGKILL worker normalization **75.000 dòng PASS LOCAL**: reclaim đúng 2 attempts, 1 canonical, raw hash không đổi; toàn pipeline upload/approval/crash/recovery/publish **14,734 giây**, khoảng **5.090 dòng/giây quan sát được**, không coi là throughput steady-state. PG tests Assistant kiểm stale fencing, idempotency, delete pending, unknown delivery/reservation hold và đúng một response.
- Responsive tại 390/768/1366/1440/1920, keyboard/close/focus, error/retry, history/context, source/evidence checks PASS. Đã xem screenshots 390/1440 và capture 768 với dữ liệu tổng hợp ngoài Git; không tuyên bố chứng nhận toàn bộ WCAG.

Benchmark tổng hợp trên Ryzen 5 7535HS (6 cores/12 threads), khoảng 16 GB RAM, Polars 2 threads; worker concurrency 1, không GPU/model inference. Foundation và exact matching chạy local; evidence/SQL trong Backend hiện có. p95 bên dưới là quantile quan sát từ mẫu nhỏ, không phải SLA:

| Khối lượng | Parse p50 ms | Profile p50 ms | Normalize/write p50 ms | Match p50 ms | Verify p50 ms |
|---|---:|---:|---:|---:|---:|
| 1.000 | 33,82 | 6,07 | 64,54 | 32,69 | 18,10 |
| 10.000 | 43,05 | 21,28 | 419,61 | 348,46 | 267,63 |
| 50.000 | 67,24 | 94,16 | 1.671,75 | 2.624,05 | 2.006,15 |

Ba repeats mỗi size. Foundation count là dòng một nguồn; match count là tổng hai nguồn (25.000 mỗi phía ở size 50k), không so các cột như cùng một workload. Peak process lần lượt tối đa 174,31 MiB foundation và 318,71 MiB matcher/verifier. Ở 50k, p95 quan sát parse/profile/normalize là 68,13/97,44/2.145,93 ms; match/verify 2.695,42/2.006,62 ms.

Evidence benchmark 10 samples/size **1k/10k/50k nhóm**: p50 **32,506/36,328/30,696 ms**, p95 **71,100/42,424/33,567 ms**, peak tối đa **297,20 MiB**. Size 50k nhóm tương ứng 100k source records chỉ trong read benchmark; chưa đo full pipeline 100k. Trên run tổng hợp hiện có, summary tool p50/p95 **1,016/2,611 ms**, FactSet **4,004/6,841 ms**; SQL EXPLAIN actual **0,036 ms**, estimated cost **6,35**, shared hits **6** (không phải chi phí tiền). Conversation reopen/render một sample mỗi viewport 390/768/1440: **1.122/1.170/513 ms**; cache contract/hits được test, chưa có production cache-throughput benchmark. Toàn bộ benchmark **0 cloud request**, cost để null khi không có receipt; không suy ra precision/recall/99% accuracy từ exact/golden fixtures.

### E. AI policy và usage cuối

- Gemini mặc định **`gemini-3.5-flash-lite`**, durable HTTP attempts vẫn **7/10, còn 3**; không reset/tăng allowance. **Assistant Gemini live: DEFERRED theo chỉ định không dùng quota**; transport chỉ PASS MOCK.
- **Assistant cloud false, task budget 0**. Facts/answers tại local là **DETERMINISTIC/CACHE**, không gắn nhãn Gemini live. Durable task reservation giữ cùng transaction/global lock; failure ghi reservation đã biết, tokens/cost thiếu để null.
- Qwen `knowledge`: **DEFERRED vì HTTP 403 lịch sử**, không probe/call lại. LlamaParse tạo job **OFF**, hai document reservations giữ nguyên; tests đọc cached PDF/DOCX, không request/credit mới. Argon **research only**, không adapter/env/budget/fallback.
- Trace hiện có 47 rows gồm 30 Assistant deterministic/cache outcomes cộng 17 traces cũ; trace không đồng nghĩa cloud request. Thực tế `ASSISTANT_REQUEST_RESERVED=0`, `GEMINI_REQUEST_RESERVED=7`, `LLAMAPARSE_DOCUMENT_RESERVED=2`.

### F. Dữ liệu, persistence và backup/restore

Toàn bộ ID, metadata hashes và file SHA256 trong snapshot trước nhiệm vụ giữ nguyên sau nhiệm vụ. Chỉ thêm fixtures tổng hợp; **28 projects lịch sử còn đủ**, cộng 1 project TEST rõ ràng cho worker recovery, tổng **29 TEST / 0 WORK / 0 UNKNOWN**; không xóa/hide dữ liệu để giảm counts.

Snapshot cuối: **57 datasets/versions, 55 tables, 114 schemas/mappings, 52 canonical, 228 jobs/233 attempts, 236 audits, 34 plans/27 contracts/27 runs, 97 cases/47 exports, 30 conversations/60 messages**. Published bytes: **218 foundation artifacts + 27 run artifacts + 47 export files**. Không có jobs active; không còn restore schema do drill tạo.

`check-persistence.ps1` trên candidate cuối: **3/3 metadata/artifact comparisons PASS** (restart, recreate cả bốn, frontend-only recreate), **3/3 fail-closed checks PASS** trước loopback re-verification. Hội thoại/FactSet/citations được mở lại sau các thao tác và rollback round-trip. Local Dashboard không nhập token, auth/Origin/CSRF không bị bỏ.

**Backup/restore PASS LOCAL** cuối cùng:

- Backup ID **`backup_5ba8a4af594445098e6ab2010ed0d807`**, receipt **10:48:45 +07 ngày 30/10/2026**, schema `create_conversations`.
- Transaction snapshot phản chiếu **23 bảng / 2.277 metadata rows** tại thời điểm backup (bao gồm sessions, quotas/audits, approved rules, snapshots và conversations); **292 published files** khớp checksum. Metadata SHA256 **`c6ed1eb238640b69fe7213e9610ec99df2d0f9a5e25032742d72cddbdc8000dd`**.
- Backup **1,243 giây**, restore/validation **1,358 giây** đo trên local. Restore vào UUID schema trong PostgreSQL hiện có; đối chiếu đủ metadata và bản sao file rồi chỉ dọn schema/copy do drill tạo. Production metadata/artifact bytes trước/sau không đổi. Corrupted metadata checksum và path traversal bị từ chối.
- Backup trên volume đã copy cả metadata/manifest/files ra host dưới `runtime/backups/` và kiểm lại toàn bộ hashes. Không commit backup/runtime/screenshots/secrets. Baseline pg_dump/artifacts trước migration cũng được giữ ngoài Git. **Off-host encrypted backup và ghi đè production restore: NOT VERIFIED/chưa thực hiện**, không nhận local drill là cam kết DR production.

### G. Lỗi đã sửa và giới hạn bàn giao

1. **DetachedInstanceError sau rollback ORM**: giữ conversation ID độc lập, fence và kiểm membership/tombstone lại trước atomic publish; regression queue/recovery PASS.
2. **Shortlist che mẫu cũ hợp lệ**: UI lấy danh sách approved templates từ API scoped, không dùng shortlist làm quyền; thêm pending-plan pagination trên metadata sẵn có để mở lại action sau khi đóng panel. Workflow E2E PASS.
3. **Context sidebar thiếu dataset/run đang xem**: truyền đúng ID thuộc project, không trộn dữ liệu khi đổi scope; dataset/run/case/late-response regressions PASS.
4. Bổ sung idempotency cho reuse API và giữ explicit request key phía client; resend cùng nội dung không nhân action, khác nội dung 409. Xóa hội thoại đang chờ không được resurrect bởi worker.
5. Sửa harness kiểm backup codec để copy đúng helper vào container hiện có. Các lỗi test-only TikTok không có mismatch, nguồn PARTIAL không READY và focus assertion phải chờ lifecycle đã được sửa theo oracle/contract; không sửa tiền hoặc hạ validation để PASS.

Giới hạn còn lại: Assistant hỗ trợ intents facts/workflow có giới hạn và claim allowlist, không phải chatbot suy luận tự do; nhóm quá 100 evidence cần UI phân trang, sources/templates vẫn theo caps hiện có. Chưa có automatic retention, model quality/precision/recall đại diện, full-pipeline 100k, production load/HA/off-host DR hoặc chứng nhận bảo mật/WCAG toàn diện. API auth ngoài loopback vẫn cần quy trình deployment riêng. Không gọi live provider để che các giới hạn này.

**Hoàn tất triển khai và kiểm chứng candidate Giai đoạn 3 trong phạm vi demo local/manual/mock đã được giao; Gemini Assistant live/Qwen live được hoãn rõ ràng.** Source đã push trên feature branch, main giữ UX được nghiệm thu. **DỪNG sau bàn giao; chủ dự án quyết định nghiệm thu và merge Giai đoạn 3 bằng nhiệm vụ riêng.**

## Q. Product UX và reliability — nhiệm vụ ngày 30/10/2026

### A. Phạm vi và kiểm toán giao diện

Nhiệm vụ mới tiếp tục trên `codex/assistant-automation`, baseline source `3f079150ee14545fcb5fc77197f9104788f68abe`, main `eefdd4441d7f7ef52b08e7d35d3c68894de191dd`, runtime ban đầu `9802545b8a0281cc608f29d1d8b4ffd3444c454b`. Baseline 176 backend/54 E2E là lịch sử, không dùng làm kết quả mới. Một repo/Compose và volumes hiện có; không gọi cloud, thay engine, công thức, semantic contracts hoặc kế hoạch ba giai đoạn. Yêu cầu mới **chính thức cho phép Assistant thành trang riêng**, thay panel bên phải tại kế hoạch §28 và thiết kế của mục P; không sửa kế hoạch để che thay đổi được chủ dự án chỉ định.

Nguyên tắc: một vùng làm việc chính, ngữ cảnh nhìn thấy được, hướng dẫn mở khi cần, thông tin quyết định được giữ trước phê duyệt. Điều hướng dùng History API hiện có của trình duyệt, không thêm router/dependency; tham khảo [MDN History API](https://developer.mozilla.org/en-US/docs/Web/API/History_API/Working_with_the_History_API). Nút thu gọn dùng trạng thái expanded/controls theo [W3C Disclosure](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/), không nhận đây là chứng nhận toàn bộ WCAG.

| Màn hình / phân loại | Bằng chứng, nguyên nhân và ảnh hưởng | Giải pháp / ưu tiên | Kiểm chứng hiện tại |
|---|---|---|---|
| Assistant — design improvement | Browser thật 390/768/1440: Modal side che trang, lịch sử nằm trên transcript, ô nhập trôi theo hội thoại | Trang trong AppShell, lịch sử riêng và transcript cuộn, composer cố định vùng; P0 | PASS LOCAL; regression baseline FAIL trước sửa, page/focus/composer ở5viewport PASS sau sửa |
| Điều hướng — confirmed UI bug | App chỉ có useState page, không history; bản nháp mất khi unmount; requested run bị thay nếu ngoài trang lịch sử | URL identifiers + back/forward, restore qua API, bản nháp theo scope trong tab, giữ lượt được yêu cầu; P0 | PASS LOCAL; draft/reload/project switching/run ngoài trang/delayed Back/selected case regressions |
| Thanh dự án — usability issue | Cảnh báo TEST dài bên ngoài selector, phạm vi nghiệp vụ lặp lại | Bỏ cảnh báo, nhãn TEST nhỏ, refresh icon, giữ filter/owner classification; P0 | PASS LOCAL/MOCK; selector regressions và hành trình owner classify TEST qua UI |
| Tổng quan — design improvement | Ba thẻ hướng dẫn hiện cả project đang làm việc | Thu gọn khi có dữ liệu, mở sẵn cho project mới; P1 | PASS LOCAL/MOCK; DTO/next action/recent5, empty/error/loading/partial/scope |
| Dữ liệu / Mapping — accepted limitation | Bố cục đã có sheet/paging/raw/canonical/errors, review trường và semantics; không cần đổi parser hay mapping | Bảo toàn gates; kiểm lại luồng thực tế và responsive; P1 | PASS LOCAL CSV/XLSX, T01–T16; PDF/DOCX adapter MOCK và cached read, không gọi live mới |
| Đối soát — usability issue | Khóa/chỉ tiêu thiết yếu bị đóng trong details; tiến trình chỉ ghi bốn bước | Mở mặc định khóa/chỉ tiêu, diễn giải năm bước; giữ xác nhận kỳ/timezone/coverage và approval; P1 | PASS LOCAL/manual và Planner MOCK; golden/schema/approval regressions |
| Ngoại lệ — integration limitation | Case DTO không có key/amount; GET matches có paging khác, không thể ghép hai trang độc lập để đủ 25 cases | Bổ sung summary theo đúng group IDs của trang case, một truy vấn tham số hóa, backend trả số tiền gốc; P1 | PASS PG/UI: 12.75/10.00/2.75, case filter scoped/limit1, quay về case và xem tất cả |
| Báo cáo / ngoại lệ rỗng — usability issue | Lịch sử và bộ lọc đứng trước kết quả; không run vẫn hiện bảng rỗng | Lịch sử thu gọn; empty CTA thiết lập; selected run giữ khi ngoài trang lịch sử; P1 | PASS LOCAL/MOCK; UI downloads CSV/XLSX đọc lại, đúng run/period/snapshot/oracle |
| Cài đặt — accepted limitation | Policy/quotas đọc từ backend, không có quyền sửa secrets; còn thông tin kỹ thuật | Kiểm quyền, quota và trình bày progressive disclosure trong phạm vi hiện có; P2 | PASS LOCAL read-only; basic/advanced và quota thật, không giao diện sửa secrets/budget |
| Cloud / production / trên 100 thành viên — accepted limitation / out of scope | Cloud OFF, caps evidence công bố; chưa có benchmark hoặc off-host DR production | Giữ cap/warnings và ghi NOT VERIFIED, không dựng framework hoặc gọi provider để che giới hạn | Không dùng PASS mock thay PASS live |

Snapshot trước nhiệm vụ: 29 projects, 57 datasets/versions, 55 tables, 114 schemas/mappings, 52 canonical, 27 contracts/runs, 34 plans, 97 cases, 30 conversations/60 messages; 218 foundation artifacts + 27 run artifacts + 47 exports. Hash metadata/bytes đã lưu ngoài Git ở `runtime/product-ux-before.json` để đối chiếu; không xóa fixtures lịch sử. Số liệu cuối và kết quả kiểm thử sẽ ghi sau khi thực thi.

### B. Kiểm tra candidate và lỗi truyền request

Source `f6aa092376e8174889a277cceda3d10c602e9673` đã commit/push, build từ Git sạch; 4/4 service healthy, 40 tracked backend files trong cả backend/worker và 6 assets HTTP khớp hash. PostgreSQL giữ image/volumes, các image main/candidate/rollback được bảo vệ không thay đổi. Bộ backend trên container **190 PASS, 0 FAIL/SKIP**, 79,10 giây: 152 offline + 38 PostgreSQL. Gồm 12 câu hỏi kiểm phạm vi facts, bảy tools từ chối workspace lạ và cap 100/101 thành viên trên Parquet thật. Đây là local/mock, không phải live AI.

Lượt browser đầu **47 PASS / 9 FAIL / 0 SKIP**, 320,66 giây. Lỗi harness sau thay đổi thiết kế: `.first()` trỏ vào trạng thái trong lịch sử đã đóng, sidebar mobile bị ẩn, thao tác mở details lại đóng phần đã mở mặc định, fixture runs nằm ở trang hai khi lịch sử tăng. Điều chỉnh selectors để kiểm badge của selected run, expanded semantics và thao tác phân trang thật; giữ oracle và gates.

Kiểm tra bổ sung tái hiện **lỗi thực tế**: server đã nhận câu hỏi nhưng response bị mất; reload rồi gửi lại tạo job ID khác vì request key chỉ nằm trong ref của React. Regression `unknown message delivery keeps its idempotency key after reload` **FAIL trên runtime f6aa092** với hai job ID khác nhau. Sửa client lưu cặp body/key và key tạo hội thoại trong sessionStorage theo actor/project; response chưa rõ không tự resend, user resend cùng nội dung dùng key cũ. Không đổi queue/Gateway/budget. Bản sửa đang chờ browser replay; không ghi PASS trước khi chạy.

Candidate tiếp theo `bffd5743f0753a8c39584fe001bbe925f7405b32`: **57/58 E2E PASS**, một lỗi selector trong test hành trình mới (`getByLabel` với select có options); chuyển sang role combobox đúng accessible name, không đổi ứng dụng/oracle. Replay riêng hành trình **1 PASS / 26,4 giây**. Regression lost response/reload PASS, backend trả cùng job ID; workflow ba nguồn thử lỗi cặp thứ hai rồi retry cùng keys, vẫn chỉ hai đề xuất và cần người duyệt, PASS. Reports đưa export lên gần selected run/period; Exceptions ưu tiên danh sách thay biểu đồ; thuật ngữ comparison được diễn giải bằng tiếng Việt với bản gốc thu gọn.

Audit race bổ sung: `navigation cancels a delayed Back restore without leaving the page inert` **FAIL trên runtime bffd574**. Khi Back đang GET project, user chọn trang khác làm abort effect; cờ restoring không được giải phóng do guard chỉ nằm trong effect cũ. Sửa navigation sequence chung, hủy hiệu lực restore cũ khi user điều hướng và giải phóng cờ ngay; response cũ không chọn lại project. Đang chờ replay của bản sửa; không bỏ inert/fail-closed hoặc nới quyền API.

Candidate `fc3d959b286dbc12fd3ca18ab97921cbc3b1cbc9`: **59/59 E2E PASS, 0 FAIL/SKIP**, 234,41 giây; race Back/sidebar/new navigation, request idempotency sau reload, partial-pair workflow retry và hành trình mới đều PASS. Bổ sung cuối cho việc trở về đúng case sau reload: `case_id` filter scoped cùng run/workspace, selected case có trạng thái rõ và nút xem tất cả, không suy case từ hai trang khác nhau. Source PostgreSQL full replay sau bổ sung **190 PASS / 0 FAIL/SKIP**, 71,32 giây. Đang chờ build/replay bản source cuối và các drill vận hành trước khi kết luận nhiệm vụ.

### C. Kết quả kiểm thử source cuối

Source ứng dụng **`446d0312048cb0fe70052944e6972d28cf7bf773`** đã commit/push, build từ Git sạch. Không thêm dependency, migration, queue, framework, engine hoặc implementation Assistant thứ hai. Backend chỉ bổ sung case summary/filter scoped để tích hợp UI và sửa câu hướng dẫn EVIDENCE_LIMIT vốn ngụ ý UI đã có phân trang đầy đủ. Semantic/financial contracts giữ nguyên.

| Kiểm tra mới thực thi | Kết quả |
|---|---|
| Full backend trên backend/PostgreSQL hiện có | **190 PASS, 0 FAIL/SKIP / 63,08 giây**: 152 offline + 38 PostgreSQL; baseline176 tăng14 cases (12 câu hỏi + cap100/101); các assertions PG bổ sung nằm trong case cũ |
| Full Playwright MANUAL trên Nginx candidate | **59 PASS, 0 FAIL/SKIP/flaky / 200,11 giây**: 9 foundation + 25 interface + 7 reconciliation + 17 Assistant + 1 journey; baseline54 tăng5 cases; không cộng replays |
| TypeScript / ESLint / production build | PASS; 6 served files, không thêm thư viện |
| Ruff / mypy / source sanitization | PASS; mypy33 source files, repository scanner129 source candidates; Markdown paths và `git diff --check` PASS tại nhóm source cuối |
| T01–T40, golden/property/security/migrations/worker fences | PASS trong bộ190; UUID test schemas trên PostgreSQL sẵn có, không Compose test project/server mới |
| Read-back CSV/XLSX và independent oracle | PASS: snapshots/identity/membership/population/cases/exports của Shopee, TikTok, delivery; không dùng Matcher hoặc AI làm oracle |
| Worker recovery local thực tế | PASS: SIGKILL giữa normalize75.000 dòng, expire đúng lease tổng hợp, reclaim2 attempts, **1 canonical**, raw checksum giữ nguyên; 19,750 giây gồm toàn luồng, không gọi là throughput ổn định |

Lỗi đã được regression xác nhận và sửa: thiếu page/history state, mất bản nháp khi unmount, selected run bị thay bởi trang lịch sử, mất request identity sau reload, delayed Back restore làm main inert, thiếu selected-case navigation. Thiết kế được cập nhật: toolbar project gọn/TEST badge, hướng dẫn thu gọn, khóa/chỉ tiêu mở sẵn, lịch sử runs thu gọn, export gần selected run/kỳ, Exceptions ưu tiên danh sách có key/số tiền; Settings chia cơ bản/nâng cao. Mapping/parser/normalization/verifier không được viết lại.

### D. Browser QA và số đo UX

**PASS LOCAL** cho 35 captures của 7 trang ở **390/768/1366/1440/1920**, 0 uncaught pageerrors và không tràn viewport ngang. Kiểm tra ảnh thực tế: sidebar active/breadcrumb, hàng project, Assistant có transcript/history/composer riêng, history đóng/mở, Reports/Exceptions, Settings và các bảng. 12 captures bổ sung cho empty/loading/error/viewer/permission denied/long content ở390/1440 là **MOCK scoped GET**; không coi đây là kết quả authorization server. Quyền thật được kiểm ở PG/E2E. Mapping/PARTIAL source và evidence được mở từ dữ liệu tổng hợp thật; viewport390×600 vẫn có composer trong bounds. Chưa xác minh bàn phím hệ điều hành mobile hoặc screen reader thực; không tuyên bố chứng nhận toàn bộ WCAG.

Ảnh và receipts ở `runtime/screenshots/`, `runtime/product-ux-visual.json`, `runtime/product-ux-states.json`, không đưa vào Git. Lịch sử hội thoại hỗ trợ duyệt từng trang20 và resume, có cap UI rõ; chưa có server search hội thoại. Nhóm lớn hơn100 bị Assistant từ chối kết luận; evidence UI công bố cap100 thành viên/20 ô, export giữ lineage đầy đủ. Không giả vờ đã triển khai pagination toàn evidence.

Số đo serial local (Chromium headless1440×1000, full document navigation; **3 mẫu** cho mỗi điểm trừ khi ghi khác), median và khoảng quan sát:

| Điểm UX | Median / min–max (ms) |
|---|---|
| Dashboard | 370 / 361–3260 |
| Run history mở danh sách | 1432 / 932–1651 |
| Evidence | 319 / 288–351 |
| Mở lại conversation | 903 / 876–1425 |
| Mở dataset / trang dữ liệu đầu | 355 / 222–370 |
| Tìm project / đổi project | 1223 / 1102 (mỗi điểm1 mẫu) |

Đổi project: **7 API requests**; idle sau settle: **0 API requests / 3 giây**. Nguồn75.000 dòng: trang đầu343ms, **25 dòng được render**, total75.000 từ backend. Long chat **MOCK GET**, 200 messages qua9 lần lấy trang thêm:1010ms, JS heap20 messages23.055.488bytes →200 messages24.589.772bytes; không điều khiển GC nên không dùng để kết luận không rò bộ nhớ. Không phải SLA/load test/benchmark production. Hai lượt đo harness đầu bị loại: dùng cùng-document navigation chưa chờ settle và init script chạm localStorage ở about:blank; không sửa code/cache ứng dụng để che số đo.

12 câu hỏi bổ sung kiểm why mismatch, total variance, unresolved cases, missing counterpart, unverified run, rule, source, fee uncertainty, ba nguồn, KPI không tồn tại, foreign project và nhóm quá100. Intents chưa hỗ trợ phải trả thiếu bằng chứng/provider unavailable, không tự tính KPI hoặc suy phí. Workflow ba nguồn được kiểm ở API/E2E riêng với xác nhận người dùng, hai approved templates, partial failure và idempotent retry. Không tuyên bố mọi câu hỏi đều được chatbot suy luận tự do trả lời.

### E. Toàn vẹn dữ liệu và AI policy

**PASS LOCAL**: mọi ID và hash metadata/bytes có trong snapshot trước nhiệm vụ vẫn còn và khớp hoàn toàn. Snapshot sau tests/worker drill so với sau restart/backup/rollback round-trip cũng **bằng nhau chính xác** đối với các bảng nghiệp vụ/artifacts được `check-persistence.py` kiểm tra. Không sửa/xóa dữ liệu lịch sử, không reset quota, không đổi schema/parser/mapping/engine revisions để hợp thức hóa kết quả.

Snapshot cuối: **34 projects (34 TEST / 0 WORK / 0 UNKNOWN), 82 datasets/versions, 80 tables, 164 schemas/mappings, 77 canonical, 349 jobs/355 attempts, 329 audits, 53 plans, 38 contracts/runs, 146 cases, 64 exports, 72 conversations/146 messages, 90 traces**. Published bytes: **318 foundation artifacts + 38 run artifacts + 64 export files = 420 files**. So với trước nhiệm vụ thêm5 project tổng hợp (4 lần kiểm journey, gồm1 lượt dừng do test selector; 1 worker recovery); giữ đủ29 project trước đó. Các lần replay tạo thêm dữ liệu tổng hợp có chủ đích, không xóa để giảm counts. Long chat/performance/state mocks chỉ intercept GET, không tạo200 messages trên server.

- Gemini vẫn **`gemini-3.5-flash-lite`**, **7/10 đã dùng, 3 còn lại**; durable `GEMINI_REQUEST_RESERVED=7` trước/sau, không tăng ngân sách hay request. **0 Gemini live requests mới**.
- Assistant cloud **OFF**, task budget **0**, `ASSISTANT_REQUEST_RESERVED=0`. Câu trả lời local là DETERMINISTIC/CACHE hoặc thiếu bằng chứng, không gắn nhãn AI live.
- Qwen `knowledge` **DEFERRED do HTTP403 lịch sử**, không probe/gọi lại. LlamaParse tạo job **OFF**, durable document reservations giữ **2**; PDF/DOCX adapter **PASS MOCK/cached read**, live mới **NOT VERIFIED theo chỉ định không gọi cloud**, không có credits/request phát sinh trong nhiệm vụ. Không tìm key hoặc lấy key từ dự án khác. Argon research only, không adapter/request.
- 90 traces không tương đương90 cloud calls. Các mock transport/timeout/quota/security tests chạy trong UUID test schemas và không tác động quota production.

### F. Docker, persistence, backup và rollback

**PASS LOCAL** trên đúng Compose `ai-reconciliation-studio`, hai volumes `ai-reconciliation-studio_postgres_data` và `ai-reconciliation-studio_artifacts`. Docker cuối **4/4 running/healthy**; frontend bind `127.0.0.1:18180`, local Dashboard không nhập token. Không tắt auth/Origin/CSRF; **3/3 fail-closed** checks trước re-verification. Migration vẫn **`create_conversations`**, không thêm migration ở nhiệm vụ này.

`tools/check-persistence.ps1`: **3/3 metadata/artifact comparisons PASS** qua restart, force-recreate đủ bốn service và frontend-only recreate. Sau các thao tác, hai hội thoại thuộc hai project mở lại đúng run, saved answers/citations khớp, selected case và raw source cells đọc được, snapshot không đổi; **0 browser API mutations** khi reopen.

Backup/restore bằng helper sẵn có, không server/container mới và không overwrite public:

- Backup **`backup_1a0eba7eb2a04228a6792d4a7d9f731b`**, receipt **13:04:32 +07 ngày30/10/2026**, schema `create_conversations`.
- **23 bảng / 3.384 metadata rows** (gồm sessions, memberships, conversations/messages, rules/snapshots, audits và quota reservations), **420 published files**. Metadata SHA256 **`5ffdf4d0e54fb0d858ed732e011e1fb676ee1061711f02ce558c1d79bc299859`**.
- Backup1,899giây, restore/validation2,238giây. Restore schema UUID được đối chiếu đầy đủ rồi dọn đúng schema/copy drill; cuối cùng **0 restore schemas** còn lại. Corrupted metadata checksum và path traversal bị từ chối; production metadata không đổi trong drill.
- Đã copy toàn bộ backup từ volume ra host `runtime/backups/` và kiểm lại metadata cùng từng file SHA256. Không commit backup/data. **Off-host encrypted DR và restore đè production: NOT VERIFIED**, không suy từ local drill.

Rollback bằng `tools/rollback.ps1 -ReleaseRevision 5f358c4`: cặp main được bảo vệ lên4/4healthy, giữ schema/volumes; ba oracle và exports cũ đọc lại PASS. Startup override chỉ áp dụng compatibility đã kiểm cho additive schema, không downgrade DB. Sau đó plain Compose trả về candidate **446d031**, source/assets hash và hội thoại/evidence/case reopen đều PASS. Business snapshot trước/sau round-trip bằng nhau.

Images cuối (OCI revision/source đúng official repository, 40 tracked backend files khớp trong cả backend/worker, 6 served frontend files khớp SHA256):

| Thành phần | Image ID |
|---|---|
| Backend/Worker | `sha256:bd55a66b87642c2978370de5c4013120ded2b6fa6fcafab47ce2dacfd31bec67` |
| Frontend | `sha256:929002794a6d1937689f3560adac2fc7caf7323c2ce0b5b908ab8227f4fc6e6a` |
| PostgreSQL giữ nguyên | `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` |

Candidate được giữ thêm bằng hai tag `candidate-446d031`; image sizes backend156.312.351bytes và frontend25.824.956bytes (Docker reported size, không phải exclusive disk usage). Sáu references main/candidate9802545/rollback trước nhiệm vụ vẫn đúng IDs cũ. **Không prune/xóa image/cache/volume**, không dọn tài nguyên toàn host hay tác động project khác.

### G. Git và tài liệu bàn giao

Các nhóm source hợp lệ đã commit/push trên **`codex/assistant-automation`**: `f6aa092` (Assistant page/scoped results), `bffd574` (request identity/result actions), `fc3d959` (cancel stale restores), **`446d031` (selected exception navigation, source đang chạy)**. Remote chính thức `https://github.com/MinhHoang1403/AI-Reconciliation-Studio.git`. Báo cáo và tài liệu hành vi được commit riêng sau kiểm tra; hash commit bàn giao và trạng thái local/remote được báo trong câu trả lời cuối, không tạo hash tự tham chiếu trong file.

Main local/origin giữ **`eefdd4441d7f7ef52b08e7d35d3c68894de191dd`**; không merge main, force-push hoặc di chuyển tags. Chỉ tài liệu hành vi/report được chỉnh sau source446d031; runtime không giả nhận hash commit tài liệu là image revision. README sửa câu lỗi thời “chat chưa triển khai” và phân biệt Planner live lịch sử với đợt này local/mock; Testing Guide cập nhật counts/catalogue. Không sửa kế hoạch ba giai đoạn.

### H. Kết luận và giới hạn

**HOÀN TẤT PRODUCT UX & RELIABILITY TRONG PHẠM VI DEMO LOCAL/MANUAL/MOCK ĐƯỢC GIAO.** Các lỗi xác nhận trong phạm vi đã sửa và regression đạt; không còn FAIL đã biết của suite cuối. Candidate sẵn sàng để chủ dự án đọc báo cáo và review trực tiếp, **chưa tự merge main và không tuyên bố production ready**.

Giới hạn giữ công khai: intents Assistant/claim allowlist có giới hạn, không chatbot suy luận tự do; duyệt history theo trang, chưa server search; evidence caps và catalogue/template caps hiện có; native mobile keyboard/screen reader/full WCAG, production load/HA, representative model precision/recall, retention tự động và off-host DR chưa được xác minh. Bản nháp lưu trong tab, đóng tab có thể mất; đây không phải backup hội thoại. Các giới hạn này không được gắn PASS live hoặc giải quyết bằng cloud/framework ngoài phạm vi.

**DỪNG TOÀN BỘ CÔNG VIỆC SAU BÀN GIAO. Chờ chủ dự án review và giao nhiệm vụ riêng; không tự merge hoặc bắt đầu giai đoạn tiếp theo.**

## R. Acceptance, repository consolidation và Docker release — 30/10/2026

### A. Nghiệm thu trải nghiệm — PASS LOCAL / PASS MOCK theo từng trường hợp

Ủy quyền mới yêu cầu nghiệm thu rồi hợp nhất `codex/assistant-automation`, build main và dọn images an toàn; thay thế điểm dừng không merge của nhiệm vụ Q. Tuy nhiên prompt mới cũng bắt buộc: **nếu gate bắt buộc thất bại thì không được vượt qua bằng cách hạ tiêu chí**. Planner FAIL LIVE ở mục B nên chưa được thực hiện các bước merge/release phụ thuộc. Vẫn hoàn thành các kiểm tra, sửa lỗi công cụ, cleanup cache và bảo toàn dữ liệu độc lập. Không đổi kế hoạch ba giai đoạn, kiến trúc, công thức, matcher/verifier hoặc validators.

Baseline thật: Git sạch trên feature `2971605c3cf5f06b789de35ea8f5390278e964e7`; main/local/origin `eefdd4441d7f7ef52b08e7d35d3c68894de191dd`; app runtime `446d0312048cb0fe70052944e6972d28cf7bf773`. Đã đọc Rules/AGENTS/kế hoạch/hợp đồng và báo cáo. Giữ một checkout, một Compose, hai volumes hiện có; không tìm keys ở dự án khác.

- **PASS LOCAL:** Tổng quan, Dữ liệu, Đối soát, Ngoại lệ, Báo cáo, Trợ lý AI dạng trang và Cài đặt ở390/768/1366/1440/1920:35captures, không uncaught pageerror hoặc tràn viewport ngang. Đã xem ảnh thực tế Assistant mobile, Reports desktop, Exceptions tablet; mapping/PARTIAL và composer390×600 trong bounds.
- **PASS MOCK:**12captures empty/loading/error/viewer/permission-denied/long-content ở390/1440, intercept GET có scope; không dùng làm bằng chứng quyền server. Quyền thật, CSRF/isolation/viewer denial có PG/E2E.
- **PASS LOCAL:** Hành trình project mới → CSV/XLSX → profile/mapping approval → normalize → manual rule review/approve → verified run → exception/source evidence → Assistant → export CSV/XLSX → reload. Oracle literal12.75−10.00=2.75VND; independent readback còn kiểm identity/membership/population/cases của Shopee/TikTok/delivery. Không lấy Matcher hoặc LLM làm oracle.
- Page/history/back-forward/drafts, scope switching, stale responses, request identity/idempotency, permissions/network failures và saved run/case có trong59E2E. Không phát hiện UX bug mới cần sửa ứng dụng. Keyboard/focus/contrast checks có trong suite; native mobile keyboard/screen reader/full WCAG vẫn **NOT VERIFIED**.

Ảnh mới `runtime/screenshots/consolidation-*`; receipts `runtime/consolidation-ux-visual.json`, `consolidation-ux-states.json`, `product-journey.json` và logs tương ứng, ngoài Git. Lượt E2E ban đầu sau gián đoạn gặp403 LOCAL_DEMO_NOT_VERIFIED, không ghi PASS; xác minh published loopback bằng verify-local rồi mới replay. Không tắt auth hoặc sửa timeout.

### B. Gemini LIVE — Assistant PASS, Planner FAIL

Preflight PostgreSQL xác nhận key đã cấu hình trong chính dự án, provider GEMINI/model `gemini-3.5-flash-lite`, workspace CLOUD_ALLOWED và global/workspace ceiling10. Baseline durable Gemini7, Assistant0, Planner1, LlamaParse2; không active jobs. Hai request chỉ dùng dữ liệu tổng hợp có canonical/VerifiedRun thật.

| Task / revision | Kết quả và validator | HTTP attempts / latency | Usage provider trả về |
|---|---|---|---|
| `answer_verified_question` / `assistant-grounded-1` | **PASS LIVE**: job SUCCEEDED; model chọn comparison/comparison_0 của đúng FactSet/run/snapshot; Backend render12.75/10.00/2.75VND, citations về nhóm và hai dòng nguồn; không bịa nguyên nhân, tiền hoặc thực thi workflow | **1 / 1.564ms**, không retry | Input3.454, output155; thinking/cache không có receipt, cost null |
| `propose_reconciliation_contract` / `reconciliation-planning-2` | **FAIL LIVE**: response JSON đọc được, status NEEDS_REVIEW, plan=null, có suggestions nhưng Pydantic từ chối `AI_INVALID_JSON`; job BLOCKED, không tạo proposal/contract/run | **1 / 2.168ms**, không retry | Input8.163, output436, total8.599; không suy chi phí tiền tệ |

Assistant job `179865c6-3e40-472b-8370-8dd830188a1e`, conversation `b07e67ba-0e5c-56f6-b093-9f05baa76e5d`; Planner job `169b2fd0-5c7f-4c25-9b25-8eee1f3497a7`. Receipt tổng hợp tại `runtime/consolidation-live.json` giữ IDs, trace/usage, input đã scope và response hash, không vào Git. Trace Planner chỉ giữ mã lỗi, không giữ raw response hoặc ValidationError theo trường; **nguyên nhân tại trường cụ thể NOT VERIFIED**, không suy đoán rồi sửa prompt/output. Schema gate FAIL nên semantic validation/oracle của Planner **chưa được nghiệm thu live**. Các mock tests valid suggestions/giả fields/evidence/basis/cardinality/đổi scope vẫn PASS; không thay thế kết quả live.

Harness dùng API auth/queue và production worker handlers/Gateway/reservations/validators hiện có trong backend. Dừng worker thường tạm để tránh claim race; bật Assistant cloud/budget1 chỉ trong tiến trình kiểm thử, giới hạn transport max_attempts=1 và chặn HTTP thứ hai cho mỗi job; không sửa output/validator, `.env` Assistant hoặc global/workspace ceiling. Finally bật lại worker; không tự resend khi lỗi. Chỉ đúng **2/2 attempts mới**, hết allowance của nhiệm vụ.

Durable sau thử và sau restart/backup: **Gemini9/10, còn1; Assistant1; Planner2; LlamaParse2**. Planner task lifetime cap2 cũng đã đầy; không tự nới để kiểm lại. Assistant OFF/budget0. Workspace parser đã OFF từ trước, preflight thấy env parsing vẫn true nên đã đưa `ALLOW_CLOUD_PARSING=false` và recreate đúng backend/worker; giữ nguyên key/credits/allowance/history. Không gọi parser/Qwen/Argon. Qwen **DEFERRED do403 lịch sử**; LlamaParse live mới **NOT VERIFIED theo chỉ định không gọi**, adapter/cached reads kiểm local/mock. Không ghi historical live thành request mới.

### C. Repository audit và cleanup — PASS phần an toàn

Inventory gồm tracked/untracked/ignored: **19.161 files / 3.207 directories / 792.876.283bytes** tại mốc trước kiểm tra, gồm cả Git, dependencies và runtime. Từng path có type/bytes/Git classification/role/KEEP hoặc DELETE/evidence trong `runtime/consolidation-repository-before.json`;129tracked files có SHA/import/reference/role và quyết định trong `consolidation-source-audit.json`. Đây là kiểm toán cấu trúc/static/contracts kết hợp tests, không chứng minh mọi dynamic path là dead code.

Đã rà root, `.vscode`, backend/contracts/migrations/tests, frontend/components/E2E, tools/docs, config/lockfiles, Docker và local cache/build/logs. `.agents` và `.github` không tồn tại, không tạo thay. Ruff/TypeScript noUnused/ESLint kiểm unused imports/locals; imports/references/scripts và dependency use được đối chiếu. Hai constructor có body trùng thuộc Qwen/Gemini adapters có vai trò khác nhau: KEEP, không tạo abstraction mới. Không chứng minh source/component/dependency nào thừa để xóa an toàn. Giữ Qwen adapter, migrations, contracts, Rules/AGENTS/PROJECT_PLAN và research; không chỉnh kế hoạch để khớp code.

**Chỉ xóa73generated ignored cache files, 28.799.351bytes**. Trước mỗi xóa kiểm resolved absolute path nằm trong workspace, không symlink, không Git tracked; loại trừ runtime/.git/.venv/node_modules/.vscode. Danh sách đầy đủ từng file/hash/bytes/lý do ở `runtime/consolidation-cache-cleanup.json`:

| Thư mục cache đã dọn | Files |
|---|---:|
| `.mypy_cache` |18|
| `.pytest_cache` |5|
| `.ruff_cache` |7|
| `backend/studio/__pycache__` |23|
| `backend/studio/contracts/__pycache__` |4|
| `tests/__pycache__` |16|

Ngay sau cleanup: **19.164 files / 3.194 directories / 774.138.120bytes**. Mốc inventory sau tests/backup: **19.702 files / 3.904 directories / 855.915.781bytes**. Gross counts/bytes gồm evidence và backup mới, Git/tool caches cũng tái tạo khi kiểm tra; không suy73file đã xóa từ phép trừ gross counts hoặc coi tăng footprint là xóa thất bại. Không xóa cache lặp để làm đẹp số cuối.

KEEP: `.env`, `.vscode`, `.git`, node_modules/.venv, dist dùng so served assets, mọi runtime logs/screenshots/exports/conversations/raw/Parquet/backups và unknown ownership. Không xóa dữ liệu tổng hợp cũ. Không gộp/xóa tài liệu có vai trò hoặc lịch sử riêng; đồng bộ các câu current-status lỗi thời về live/quota và tập trung kết luận mới ở mục R, không tạo Markdown report khác.

Lỗi công cụ thật: `tools/check-reconciliation.py --planner-live` dùng payload cũ `{project_id,plan}` trong khi API yêu cầu `request:PlanningRequest`. Tái hiện offline422 missing request/extra plan → regression FAIL trước sửa → chuyển qua typed PlanningRequest.from_plan, giữ facts đã xác nhận và không gửi join_keys/comparison rule → regression PASS. Sửa harness copy helper vào backend/tmp để PG suite kiểm đúng source. Khi đọc historical cached proposal, CLI nay ghi **PASS CACHED**, không PASS LIVE mới. Đây là sửa công cụ riêng, **không chữa được Planner FAIL LIVE**, vì live harness đã dùng payload đúng.

### D. GitHub consolidation — feature đã push; merge BLOCKED

Remote đã fetch/xác minh `https://github.com/MinhHoang1403/AI-Reconciliation-Studio.git`. Chỉ có main và codex/assistant-automation ở local/origin; main là ancestor của feature. Đã kiểm diff/scope/ancestry/history, source/public-content/known credentials/Markdown links. Feature trước nhiệm vụ có12commits nối tiếp main; giữ nguyên lịch sử, không merge theo tên branch.

Sửa công cụ/tests đã commit/push **`e8e9bcd3aeedfd329d2fec07a669cd17a5b89d25`**. Tài liệu nghiệm thu commit riêng sau kiểm chứng; hash bàn giao/local-origin verification ghi trong trả lời cuối, tránh hash tự tham chiếu. Không stage `.env`, runtime, backup hoặc binary artifacts.

**Main giữ `eefdd4441d7f7ef52b08e7d35d3c68894de191dd`**; không merge commit, không push main, không xóa feature còn chưa tích hợp. Gate live thất bại nên regression trên merge result/main mới **BLOCKED**, không giả kết quả. Hai annotated tags cũ giữ đúng ref objects `37209cb21f8f786dc4b23d316f9e0772170a6122` và `2f3cb8210568e753f85e110cbecaddecd931f81e`; không di chuyển/xóa/tạo tag nghiệm thu mới. Không force-push/reset/worktree/clone.

### E. Docker, persistence và backup — PASS LOCAL; release/cleanup mới BLOCKED

Một Compose `ai-reconciliation-studio`,4/4running/healthy, frontend127.0.0.1:18180; giữ network và hai volumes `ai-reconciliation-studio_postgres_data`, `ai-reconciliation-studio_artifacts`, migration `create_conversations`. Không rebuild PostgreSQL. Runtime vẫn **446d031**, không nhận feature docs/tools commit là image revision. OCI official source/revision,40tracked backend source hashes trong cả backend/worker và6frontend served assets khớp; receipt `runtime/consolidation-runtime.json`.

| Thành phần | Image ID còn chạy |
|---|---|
| Backend/Worker |`sha256:bd55a66b87642c2978370de5c4013120ded2b6fa6fcafab47ce2dacfd31bec67`|
| Frontend |`sha256:929002794a6d1937689f3560adac2fc7caf7323c2ce0b5b908ab8227f4fc6e6a`|
| PostgreSQL giữ nguyên |`sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7`|

**PASS LOCAL:** persistence helper kiểm3/3metadata/artifact comparisons qua restart, force-recreate toàn bộ và frontend-only;3/3demo proof fail-closed trước verify-local. Snapshot sau tests bằng chính xác sau restart và backup. Mọi ID/hash baseline vẫn còn nguyên; chỉ append fixtures/jobs/audits đã nêu. Sau restart mở lại hai scoped conversations/evidence/selected case/source cells và riêng Gemini live answer,0browser API mutations; quota giữ9/10.

Snapshot mới: **37projects,95datasets/versions,93tables,190schemas/mappings,90canonical,415jobs/422attempts,382audits,63plans,44contracts/runs,172cases,74exports,95conversations/192messages,114traces**. Published files **370foundation+44run+74exports=488**; baseline420files đều giữ SHA. Ba projects mới là hai hành trình UI và một worker drill; không xóa34projects trước. Chỉ còn1GEMINI PlanRow lịch sử, Planner lỗi không thêm proposal.

Backup mới **`backup_26fda69452d742cb8dcad9a50b62c918`**, **14:41:48 +07 ngày30/10/2026**:23bảng/3.978metadata rows (gồm798sessions),488files; metadata SHA256 **`96eb7c4e0285e4defa414c2c3e0dfeaa0bf7210bffff767da6bf169e118594e2`**. Backup1,768s, restore/validation2,477s; checksum corruption/path traversal bị chặn, public metadata không đổi. Restore UUID schema/copy drill đã dọn,0restore schemas còn lại. Copy cả backup ra host runtime/backups và kiểm metadata/từngfile SHA PASS. Off-host encrypted DR/restore đè production vẫn **NOT VERIFIED**.

Inventory host trước/sau:55images/31containers, gồm27containers ngoài project ở baseline. Giữ đủ8project image references: candidate446d031, candidate9802545, accepted-main5f358c4 và rollbacke025094 cho backend/frontend. Cặp rollback accepted-main đã có drill tương thích ở mục Q; hai IDs được kiểm lại còn nguyên: backend `7a00801051416c143e0d0199919bb9a43fa319a01fd01b1a8010b1d5d8781e29`, frontend `1049ba4457ebad8971d0be29cb523b7429714fb2c3dc1abcd28a9ef1a40ab215`. **Không có rollback drill mới hoặc main release mới trong mục R**; không lấy healthcheck thay kết quả release.

**0image deletions/0build-cache prune/0volume deletions**: gate main release chưa đạt nên chưa đủ điều kiện dọn images cũ. Không chạy global prune hoặc tác động models/caches của ứng dụng khác. Images virtual total39,39GB cả hai mốc không đồng nghĩa disk đã thu hồi; free C đo137.583.370.240→137.030.660.096bytes, có backup/evidence và hoạt động khác trên host, không quy thành dung lượng cache thực thu hồi.

Inventory cuối có23/27containers ngoài project khớp;4containers có khác biệt ID/image/mount inventory và2images ngoài project biến mất trong khoảng quan sát. Nhiệm vụ chỉ chạy mutation Compose của project này, không sửa các tài nguyên ngoài; nguyên nhân hoạt động ngoài và khẳng định toàn host bất biến **NOT VERIFIED**. Không tự sửa/xóa chúng để khớp baseline. Chi tiết local ở `consolidation-docker-before.json` / `consolidation-final-inventory.json`, không public tên/config dự án khác.

### F. Chất lượng — số liệu mới, không cộng replays

| Kiểm tra thực thi | Kết quả |
|---|---|
| Backend/PostgreSQL trước cleanup |190PASS,0FAIL/SKIP,43,58s|
| Backend/PostgreSQL sau sửa/cleanup |**191PASS,0FAIL/SKIP,55,45s**;153offline+38PG, tăng1regression so baseline190|
| Playwright trước/sau cleanup |**59PASS mỗi lượt**,0FAIL/SKIP/flaky;192,04s trước/192,85s sau;9foundation+25interface+7reconciliation+17Assistant+1journey|
| T01–T40/golden/property/migrations/security/fencing |PASS trong suite; giữ contract/oracle/monetary invariants; không cộng thêm counts|
| Ruff / mypy33modules / TypeScript / ESLint / production build |PASS; không dependency mới|
| Known credential/history/public source/Markdown paths / diff check |PASS,129source candidates; không phải chứng nhận security toàn diện|
| Export readback / independent oracle |PASS CSV/XLSX/SHA/timestamp/zero-prefix/snapshot và3pair goldens|
| Worker recovery SIGKILL |PASS75.000dòng,2attempts/1canonical/raw hash nguyên;14,875s gồm toàn journey, không là throughput ổn định|
| Persistence / backup restore / saved conversations |PASS LOCAL như mục E; không cloud mới|

Một Starlette TestClient/httpx deprecation warning còn lại. Tool runner sau thay đổi môi trường không tìm thấy pwsh được chạy lại bằng Windows PowerShell hiện có; không tính lệnh chưa khởi chạy pytest là suite PASS. Lỗi encoding ở script chỉnh tài liệu tạm đã được phát hiện và sửa UTF-8 trước scanner/commit; source ứng dụng không thay đổi.

### G. Kết luận, giới hạn và điểm dừng

**CHƯA ĐẠT NGHIỆM THU RELEASE/HỢP NHẤT — PLANNER FAIL LIVE.** Local/manual/mock regressions, Assistant live và các phần bảo toàn/cleanup an toàn đã có bằng chứng. Không dùng chúng để phủ FAIL LIVE hoặc tuyên bố production-ready. Các bước merge main, xóa feature branch, build/deploy main mới và dọn images phụ thuộc giữ **BLOCKED**, không âm thầm bỏ qua.

Cần nhiệm vụ riêng chẩn đoán Planner typed output (hiện không có raw response/chi tiết lỗi theo trường) và quyết định allowance nghiệm thu mới; nhiệm vụ hiện đã hết2attempts, global còn1 nhưng Planner lifetime cap2 đã đầy. Không tự tăng/reset cap, sửa validator hoặc retry. Giữ công khai các giới hạn Q: intents/claim allowlist, caps100evidence/20source cells/catalogue/templates, chưa conversation server search, mobile keyboard/screen-reader/full WCAG, representative model quality/precision/recall, production load/HA, retention và off-host DR chưa verified. Qwen DEFERRED, Argon research-only, không triển khai phase/tính năng khác.

**DỪNG sau kiểm chứng và commit/push báo cáo trên feature branch. Không tự merge hoặc gọi thêm Gemini.**
