# Final Acceptance — Giai đoạn 1

Ngày kiểm tra: **28/10/2026**. Phạm vi: Data Foundation + AI Smart Setup + UI cơ sở.

**GIAI ĐOẠN 1 ĐẠT NGHIỆM THU — QWEN LIVE ĐƯỢC HOÃN THEO CHỈ ĐỊNH**

Kết luận theo chỉ dẫn thu hẹp phạm vi mới nhất ngày 28/10/2026: chỉ nghiệm thu Data Foundation + AI Smart Setup. Gemini mặc định hiện tại, Qwen live được hoãn chính thức do IP allowlist. Các gate dữ liệu, bằng chứng Gemini mapping live, LlamaParse PDF/DOCX live, regression, bảo mật, worker recovery và persistence đã đạt trong phạm vi dưới đây. Không đổi lịch sử Qwen thành PASS hoặc mở rộng ngoại lệ sang gate khác. **Dừng sau báo cáo; không bắt đầu Giai đoạn 2 và không merge main trong lượt này.**

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

Repository ch?nh th?c https://github.com/MinhHoang1403/AI-Reconciliation-Studio.git. N?n t?ng/Gemini tr??c ? commit 286c0802a2807bb11e53a89cff882217215b90fc. Source nghi?m thu **2e73cad7b7dc1fed5211e699b45b84d0ccbf5ea4** ? feat: accept bounded document parsing and Gemini data foundation ? ?? push codex/data-foundation, fast-forward v?o main v? ???c ??i chi?u c?ng hash t?i th?i ?i?m ??. Main sau ?? c? commit b?o c?o **061c5558eda4228b430ea4d7ec8558731bf0616f**.

L?ch s? Final Acceptance thu h?p: commit b?o c?o **4bde2111e03cf438124a73fe0abe66bc4a46fcd5** tr?n codex/data-foundation; kh?ng merge main trong nhi?m v? ??. Nh?nh local codex/reconciliation xu?t ph?t 061c555 kh?ng c? commit ri?ng, ch?a push v? kh?ng d?ng ti?p. Kh?ng reset/force-push ho?c ghi ?? nh?nh n?y.

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

C?c gate Giai ?o?n 1 ?? ?i?u ch?nh ??t, ?? ?i?u ki?n b?n giao n?n t?ng l?m ??u v?o k? thu?t cho Giai ?o?n 2. **Quy?t ??nh l?ch s? ? l?n Final Acceptance thu h?p: d?ng, kh?ng merge main, ch? prompt Giai ?o?n 2 ri?ng.** Quy?t ??nh n?y ?? ???c tu?n th? v? ???c gi? l?m l?ch s?; kh?ng t? cho ph?p chuy?n giai ?o?n.

## I. Nhi?m v? h?p nh?t ???c giao ti?p theo

Ch? d? ?n ?? g?i prompt ri?ng cho ph?p h?p nh?t Giai ?o?n 1 v?o main, ki?m th? tr??c push, t?o annotated tag data-foundation-accepted-20261028 r?i tri?n khai Giai ?o?n 2 tr?n codex/reconciliation-engine. Vi?c h?p nh?t gi? c? hai parent 061c555 v? 4bde211; hai conflict trong m?c F/H ch? l? l?ch s? Git v? quy?n chuy?n ti?p. ??i chi?u t?ng ?o?n, gi? b?ng ch?ng provider/quota/tests/known limits c?a b?o c?o m?i c?ng l?ch s? t?ch h?p source c?a main; kh?ng ??i code ?ng d?ng ho?c nghi?p v?. C?c m?c A?H l? snapshot nghi?m thu tr??c nhi?m v? n?y. K?t qu? ch?y l?i sau h?p nh?t s? ghi b?n d??i tr??c commit/push/tag. Giai ?o?n 2 kh?ng ???c merge main v? kh?ng b?t ??u Giai ?o?n 3.


K?t qu? sau h?p nh?t: offline 79 PASS/12 deselected (4,33 gi?y), b? ??y ?? PostgreSQL 91 PASS/0 FAIL/SKIP (15,26 gi?y), Ruff/mypy 18 files PASS, TypeScript/ESLint/build PASS, Playwright MANUAL 9 PASS/0 FAIL/SKIP (19,4 gi?y). T01?T16, AI policy/contract, mapping/normalization/provenance v? access-control n?m trong c?c suite n?y; kh?ng g?i cloud. Gemini gi? 6/10, c?n 4, ??ng model m?c ??nh; Qwen kh?ng probe, parser creation OFF.

Snapshot 66 artifacts c?a l?n nghi?m thu tr??c ???c ki?m tra nguy?n v?n tr??c E2E. E2E t?o th?m b?n refs t?ng h?p, snapshot m?i 70 artifacts, 20 datasets, 15 canonical, 48 jobs/52 attempts v? 50 audits; 15 traces kh?ng t?ng. Restart, force-recreate ?? b?n service v? frontend-only recreate ??u PASS metadata/checksum, demo proof fail-closed tr??c x?c minh l?i. Compose gi? project/volumes v? loopback c?, 4/4 healthy. Secret/history/Markdown path scan v? diff check PASS; .vscode/ gi? nguy?n ngo?i stage. Kh?ng thay ??i source Backend/Frontend/Compose trong merge. M?c Git s? l? merge commit hai parent ?? ki?m th?, g?n annotated tag data-foundation-accepted-20261028; hash x?c minh trong Git/tag v? b?o c?o b?n giao. C?ng A ??t v? k? thu?t; push/tag ph?i th?nh c?ng tr??c t?o branch ti?p theo.
