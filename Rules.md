# Quy tắc chính thức — AI Reconciliation Studio

Tài liệu quy tắc kỹ thuật và làm việc duy nhất của dự án, áp dụng xuyên suốt ba giai đoạn. Nguồn yêu cầu sản phẩm, kiến trúc và hợp đồng nghiệp vụ là [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md). Hướng dẫn khởi động dành cho Codex nằm tại [AGENTS.md](AGENTS.md).

## Mục lục

1. [Quản lý tài liệu và phạm vi](#quan-ly)
2. [Kiến trúc và công nghệ](#kien-truc)
3. [Code, tài liệu và đặt tên](#code)
4. [Thuật toán, nguồn và công thức](#thuat-toan)
5. [Toàn vẹn dữ liệu và database](#du-lieu)
6. [Đối soát, kiểm chứng và KPI](#doi-soat)
7. [AI, chính sách cloud và bộ nhớ](#ai)
8. [API, bảo mật và quyền truy cập](#bao-mat)
9. [Giao diện và demo local](#giao-dien)
10. [Docker và tài nguyên](#docker)
11. [Git, GitHub và khôi phục](#git)
12. [Sửa lỗi và kiểm thử](#kiem-thu)
13. [Quy trình thực hiện nhiệm vụ](#quy-trinh)
14. [Nghiệm thu và bàn giao ba giai đoạn](#nghiem-thu)
15. [Ngôn ngữ và báo cáo](#bao-cao)
16. [Điểm cần làm rõ khi triển khai](#can-lam-ro)

<a id="quan-ly"></a>
## 1. Quản lý tài liệu và phạm vi

- Trước **mỗi nhiệm vụ**, đọc toàn bộ `Rules.md`; đọc `AGENTS.md`, `docs/PROJECT_PLAN.md` và các hợp đồng/tài liệu nghiệp vụ liên quan. Phiên mới hoặc ngữ cảnh bị đặt lại phải đọc lại các quy tắc, không chỉ dựa vào tóm tắt cũ.
- `Rules.md` quy định cách làm việc; kế hoạch quy định sản phẩm, kiến trúc, workflow, thuật toán, hợp đồng dữ liệu, giới hạn MVP và các điều kiện nghiệm thu. `AGENTS.md` chỉ dẫn tới các nguồn này, không sao chép toàn bộ quy tắc. Không tạo nhiều bản Rules hoặc AGENTS ở thư mục con khi chưa có nhu cầu rõ ràng.
- Tuân thủ chỉ dẫn hệ thống, bảo mật và quyền hạn cao hơn. Nếu tài liệu mâu thuẫn, nêu rõ đoạn liên quan, tác động và phần cần xác nhận; không tự suy đoán nghiệp vụ hoặc sửa kế hoạch để hợp thức hóa code. Tiếp tục phần độc lập đã được giao nếu an toàn.
- Phân biệt `MUST` (bắt buộc để nghiệm thu), `SHOULD` (hoãn phải có lý do), `LATER/OUT` (ngoài MVP, không làm placeholder giả). Phân biệt `[S]` là cơ sở nguồn, `[D]` là quyết định dự án và `[V]` là điều còn phải đo; ký hiệu không thay thế việc kiểm tra nguồn khi triển khai.
- Chỉ làm phạm vi được giao. Không tự bắt đầu giai đoạn kế tiếp, thêm tính năng, đổi thư viện, workflow hoặc kiến trúc. Thay đổi nghiệp vụ được giao phải cập nhật đặc tả, golden fixtures (dữ liệu mẫu có đáp án chuẩn), tests và migration liên quan trước/song song với code.
- Đây là dự án mới, độc lập với `AIDataReconcileEngine`. Không sửa/xóa dự án khác; không copy code, migrations, dữ liệu, `.env`, khóa, Git history hoặc Docker volumes cũ làm nền. Dự án cũ chỉ dùng để học kinh nghiệm; mọi tái sử dụng cụ thể cần được đánh giá riêng và nằm trong yêu cầu.
- Nhiệm vụ thiết lập quy tắc chỉ tạo `Rules.md`, `AGENTS.md`, kiểm tra tài liệu và Git local phù hợp. Các quy tắc triển khai dưới đây có hiệu lực cho nhiệm vụ sau, không phải lệnh bắt đầu viết ứng dụng, tạo Docker, gọi AI hoặc cài dependency ngay.

<a id="kien-truc"></a>
## 2. Kiến trúc và công nghệ

### 2.1. Ranh giới thành phần

- Giữ kiến trúc **Modular Monolith**: một codebase chính, cấu trúc theo trách nhiệm, cấu hình thống nhất và nguồn dữ liệu nghiệp vụ có kiểm soát. Backend và worker dùng chung code/backend image; worker là tiến trình thực thi nền, không phải lý do tách microservices.
- Một AI Gateway điều phối các tác vụ có kiểu dữ liệu rõ ràng. Không dựng multi-agent framework, fine-tuning hoặc host thêm Qwen/model trong dự án; sử dụng endpoint Qwen công ty hiện có.
- Modules giao tiếp qua Pydantic domain objects và ID/tham chiếu artifact có revision. Artifact là file/kết quả xử lý được quản lý và truy vết. Không truyền DataFrame hoặc JSON LLM tùy tiện qua ranh giới API.
- Giữ các interface tại kế hoạch §7: `FileArtifact`, `ParsedTableArtifact`, `DatasetProfile`, `SchemaProposal`, `MappingDecision`, `CanonicalDataset`, `ReconciliationPlan`, `ReconciliationContract`, `MatchResult`, `VerifiedRun`, `AnswerFactSet`. Chi tiết input/output, tiền điều kiện, hậu điều kiện và tests phải đối chiếu ma trận F01–F29 ở phần XII của kế hoạch.
- FE chỉ trình bày DTO và trạng thái do Backend cung cấp; không tính lại tiền, KPI hoặc suy ra trạng thái nghiệp vụ.

### 2.2. Stack được quy định

| Phần | Công nghệ và ràng buộc |
|---|---|
| Frontend | React, TypeScript, Vite; Tailwind CSS; shadcn/ui hoặc **một** bộ component phù hợp; Lucide |
| Bảng/biểu đồ | TanStack Table; virtualization khi cần; Apache ECharts; lọc/phân trang phía server |
| Backend | Python, FastAPI, Pydantic |
| Metadata/transaction | PostgreSQL, SQLAlchemy, Alembic |
| Worker/jobs | Python, bảng jobs PostgreSQL dùng `SKIP LOCKED`, lease và idempotency |
| Parser bảng | Polars, fastexcel; openpyxl fallback để kiểm tra ô/công thức khi cần |
| Parser tài liệu | LlamaParse opt-in; local fallback chỉ khi có nhu cầu và hạ tầng phù hợp |
| Artifact/xử lý bảng | Parquet, Polars; DuckDB truy vấn Parquet; RapidFuzz tạo ứng viên |
| Tiền | Python `Decimal` hoặc SQL `DECIMAL/NUMERIC` |
| AI | Qwen công ty, model ID `knowledge`; Gemini Flash-Lite theo policy; LlamaParse có allowance riêng |
| Triển khai | Nginx phục vụ SPA và `/api` cùng origin; một Docker Compose project |
| Kiểm tra | pytest, Hypothesis, Playwright; Ruff, mypy, ESLint theo phần thay đổi |

Khi triển khai, kiểm tra bản stable và khả năng tương thích thực tế rồi pin dependency bằng lockfiles, image tags/digests; ghi phiên bản đã chọn. Không tự bịa số version hoặc thay model đang hoạt động. Model Gemini được kế hoạch chỉ định là `gemini-3.5-flash-lite`; phải kiểm tra khả dụng/contract tại thời điểm tích hợp, không tự thay nếu chưa xác minh.

### 2.3. Kiểm soát độ phức tạp

Không tự thêm microservices, Kafka/message broker, Kubernetes, Redis/Celery, MinIO, vector database, database engine mới, sandbox project, nhiều môi trường Docker, authentication framework phức tạp hoặc thư viện lớn chỉ cho chức năng nhỏ. Không tạo nhiều implementation cùng nhiệm vụ, code chết, service không dùng, thư mục thử nghiệm kéo dài hoặc hàng chục tài liệu/skills. Việc kế hoạch cho phép tối đa hai skill hữu ích không phải yêu cầu tạo chúng.

Trước khi đề xuất công nghệ/abstraction mới, chứng minh nhu cầu, khả năng tận dụng thành phần sẵn có, phương án đơn giản hơn, lợi ích đo được, chi phí vận hành/bảo trì và cách kiểm thử. Không chứng minh được lợi ích thì không thêm. Với thay đổi kiến trúc do lỗi thực tế, phải nêu nguyên nhân gốc, vì sao thiết kế hiện tại không đủ, cách sửa nhỏ hơn, modules bị ảnh hưởng, tests, chi phí và rủi ro; không tự triển khai ngoài phạm vi được giao.

<a id="code"></a>
## 3. Code, tài liệu và đặt tên

### 3.1. Code rõ ràng

- Mỗi đoạn code có mục đích rõ; tổ chức theo chức năng/trách nhiệm; tên mô tả đúng ý nghĩa; hạn chế lặp logic; xử lý lỗi phù hợp; khai báo kiểu khi ngôn ngữ hỗ trợ; dễ unit test và sửa mà ít ảnh hưởng module khác.
- Không tạo class/abstraction để làm kiến trúc trông phức tạp; không chia việc đơn giản thành quá nhiều file hoặc gom logic lớn không liên quan vào một file.
- Không có hàm vừa gọi AI, tính tiền và ghi DB như một khối không thể kiểm chứng. Tách trách nhiệm ở mức cần thiết, ưu tiên hàm thuần khi đủ.
- Hàm nghiệp vụ quan trọng phải có typed input/output, preconditions (điều kiện trước), postconditions (đảm bảo sau), errors có mã, invariants (bất biến) và tests. Không thêm code khi chưa hiểu hợp đồng đang sử dụng.

### 3.2. Comment và tài liệu

Hàm nghiệp vụ quan trọng có docstring/mô tả tương đương về mục đích, tham số, kiểu trả về, điều kiện lỗi và bất biến. Comment đầy đủ ở logic khó, lý do chọn thuật toán, tradeoff và giả định nghiệp vụ. Công thức tài chính phải giải thích đơn vị, dấu, làm tròn, điều kiện áp dụng. Không bình luận hiển nhiên từng dòng; kết hợp code tự diễn đạt với giải thích nơi cần thiết. Cập nhật tài liệu khi hành vi thay đổi.

### 3.3. Tên phản ánh trách nhiệm

- Dùng tên như `schema_mapping.py`, `data_profiler.py`, `reconciliation_engine.py`, `matching_rules.py`, `financial_calculations.py`, `ai_provider.py`, `dataset_repository.py` khi đúng chức năng; không phải yêu cầu tạo sẵn các file này.
- Không dùng tên mơ hồ như `utils_final.py`, `new_code.py`, `fix_all.py`, `test_new.py`, `temp_logic.py`.
- Nghiêm cấm nhãn kế hoạch/phát triển `v1`, `v2`, `s1`, `s2`, `e3`, `freeze`, `frozen`, `final`, `final2`, `new_version` trong tên file, thư mục chức năng, class, hàm, biến nghiệp vụ, module, service, branch, container/image tùy tiện. Không đặt tên code bằng tên giai đoạn. Nhãn giai đoạn chỉ dùng trong tài liệu kế hoạch khi cần.
- Giữ nguyên định danh bắt buộc của API, thư viện, model, protocol, migrations và công nghệ ngoài. Không nhầm quy tắc đặt tên với quản lý phiên bản: database schema, parser, prompts, mapping, normalization và reconciliation rules vẫn có revision/version để tái lập và truy vết; dependency/image vẫn pin phiên bản đúng.

<a id="thuat-toan"></a>
## 4. Thuật toán, nguồn và công thức

### 4.1. Cơ sở phương pháp

Các phương pháp quan trọng về schema matching (so ý nghĩa/cấu trúc trường), entity resolution/record linkage (xác định bản ghi liên quan), fuzzy matching (so gần đúng), blocking (giới hạn cặp ứng viên), probabilistic matching, đối soát tài chính, validation, điều phối LLM, phát hiện bất thường và verification phải có cơ sở nghiên cứu, tiêu chuẩn hoặc tài liệu chính thức phù hợp.

Với mỗi thuật toán, ghi nhận: **tên, mục đích, nguồn, input, output, điều kiện áp dụng, trường hợp không phù hợp, độ phức tạp/giới hạn hiệu năng đáng kể, cách kiểm chứng và tình huống biên**. Không cần nghiên cứu cho tiện ích/thao tác lập trình cơ bản. Ưu tiên phương pháp đơn giản đã được kiểm chứng.

- Không bịa thuật toán, công thức, kết luận khoa học, paper, URL hoặc benchmark. Heuristic do dự án thiết kế phải ghi `[D]`, có tests và đánh giá; không gán nguồn khoa học giả.
- Fuzzy score/confidence không phải xác suất đúng đã hiệu chỉnh. Ngưỡng, top-k và auto-approve phải đánh giá trên dữ liệu gán nhãn, có validation/test splits riêng; không tuyên bố tối ưu từ ngưỡng tự chọn. Thiếu dữ liệu hiệu chỉnh thì chỉ tạo candidate để review.
- Khi triển khai quyết định quan trọng, kiểm tra nguồn gốc như DOI/paper, docs chính thức, tiêu chuẩn hoặc quy định nghiệp vụ; cập nhật danh mục tham khảo kỹ thuật tại phần XI của kế hoạch trong phạm vi được giao. Không tạo bộ tài liệu tham khảo trùng lặp chỉ để tăng số file.
- Nguồn chưa xác minh phải ghi `NOT VERIFIED`, nêu giới hạn sử dụng, không dùng làm bằng chứng đã chứng minh để tự chấp nhận kết luận quan trọng. Danh mục nguồn có sẵn trong kế hoạch không đồng nghĩa phiên hiện tại đã kiểm tra trực tiếp mọi nguồn.

### 4.2. Đặc tả công thức

Mỗi công thức đối soát, KPI và tài chính phải định nghĩa chính xác: biến đầu vào, kiểu dữ liệu, đơn vị, null/invalid, dấu âm/dương, Decimal/precision, làm tròn, tolerance (sai số cho phép), phạm vi thời gian, hiệu lực và tests có kết quả mong đợi. Ngày dùng khoảng `[start, end)` với timezone được xác nhận. Không tự tạo công thức phí Shopee/TikTok/ngân hàng hoặc FX nếu chưa có nguồn nghiệp vụ đáng tin cậy, ngày hiệu lực hoặc định nghĩa được người dùng xác nhận.

<a id="du-lieu"></a>
## 5. Toàn vẹn dữ liệu và database

Toàn vẹn dữ liệu là ưu tiên cao nhất trong các module xử lý dữ liệu.

### 5.1. Bảo toàn và provenance

- Raw bytes bất biến, có SHA256 và quyền workspace. Không ghi ngược vào raw/parsed artifact. Dữ liệu xử lý phải có provenance (nguồn gốc): file, sheet/table/row hoặc page/cell, revision và các phép chuyển đổi.
- Không âm thầm mất dòng, JOIN nhân dòng/tiền, tạo giá trị giả để ép schema hợp lệ, biến lỗi/null/unknown thành 0 hoặc làm tròn tùy tiện. Zero, null và invalid là ba tình huống khác nhau, có raw value và error artifact tương ứng.
- Mã định danh phải giữ số 0 đầu và hình thức gốc khi có nguy cơ mất thông tin. Không tự tạo business key, bỏ dấu câu, trim hoặc fuzzy ID nghiêm ngặt nếu chưa có rule được xác minh/phê duyệt. `source_row_id` kỹ thuật không thay thế business key.
- Không suy đoán currency/timezone, record grain (ý nghĩa mỗi dòng) hoặc metric semantics khi thiếu bằng chứng. Tiền không rõ gross/net phải review.
- Lineage qua JOIN/aggregation phải chứa đầy đủ thành viên nguồn; không chỉ trỏ một dòng đại diện. Không báo đối soát thành công khi verification thất bại.

### 5.2. Các tầng và hợp đồng

Luồng `Raw → Parsed → Profiled → Semantic Mapping → Canonical → Reconciled` phải có input/output và gate rõ ràng. Phân biệt source schema, semantic schema, canonical/custom schema và comparison contract theo kế hoạch §9. Không dùng mapping chưa xác nhận cho kết luận nghiệp vụ quan trọng; trường hợp chưa rõ trả review, không làm giả dữ liệu.

PDF/DOCX có thể là bằng chứng hoặc quy định, không nhất thiết là bảng giao dịch. OCR/bảng chưa đáng tin phải mang `UNVERIFIED_EXTRACTION` hoặc trạng thái tương ứng trong hợp đồng; không tự sửa số để bảng trông đúng. Parser phải giữ warnings, raw/cached formula metadata và vị trí nguồn cần thiết.

Normalization chỉ chạy DSL/AST (cây biểu diễn phép biến đổi) đã kiểm tra kiểu, tham số, lỗi và provenance. Allowlist theo kế hoạch §16: `cast_string_preserve`, `trim_if_approved`, `parse_decimal(locale)`, `parse_date(format, timezone)`, `normalize_enum(mapping_id)`, `coalesce_with_rule`, `add_fields`, `subtract_fields`, `aggregate_by(keys, metric)`. Không thực thi Python/SQL tùy ý do AI sinh.

### 5.3. Lưu trữ, revision và tái xử lý

- PostgreSQL là nguồn sự thật cho metadata, owner/scope, approvals, trạng thái, runs, jobs và audit. Parquet chứa bảng parsed/canonical/match detail lớn; file storage chứa raw/exports. Không tạo bảng PostgreSQL mới cho từng upload. DuckDB truy vấn artifact, không dùng file DuckDB ghi đồng thời nhiều worker như nguồn sự thật.
- Dùng migration có kiểm soát, ưu tiên additive và compatibility tests; không đổi schema phá hủy artifact lịch sử. Unique constraints, transaction, lease/retry và idempotency phải ngăn công việc logic bị nhân đôi.
- Dependency của artifact tuân thủ kế hoạch §8: parse phụ thuộc file hash/parser/config; canonical phụ thuộc parsed/mapping/normalization revision; run phụ thuộc canonical refs/contract/engine revision/period/scope.
- Đổi cách đọc/nội dung tạo `DatasetVersion` phù hợp. Chỉ đổi mapping không đổi `file_sha256` hoặc bắt parse lại raw; tạo mapping/canonical/run revision cần thiết và invalidate đúng downstream. Không sửa lịch sử.
- Cache theo owner/workspace, source signature, revision và business scope; không dùng chéo workspace chỉ vì hash giống nhau. Sửa màu/filter UI không gọi lại parse/AI/matching.
- Kết quả/tool request phải xác định `run_id`; không dùng “latest” mơ hồ. FactSet/câu trả lời của run cũ không được trình bày như số liệu hiện tại khi run thay đổi.

<a id="doi-soat"></a>
## 6. Đối soát, kiểm chứng và KPI

### 6.1. Gates và trạng thái

Giữ toàn bộ gates ở kế hoạch §13: **Upload, Parse, Schema, Mapping, Normalization, Readiness, Contract, Result verification, Answer**. Gate không đạt thì từ chối, giữ unverified, review hoặc `PARTIAL/BLOCKED/PENDING` đúng hợp đồng; chỉ chạy rule độc lập đã đủ điều kiện. Không bỏ validation để cho pipeline chạy hết.

Contract trước khi chạy phải xác minh source slots/IDs, grain, keys/uniqueness/cardinality, aggregation, semantic metric/amount basis, unit/currency, period/cutoff/completeness, formula allowlist, tolerance, effective dates, permissions và các trường unknown. AI không phải validator duy nhất và không tự duyệt rule tài chính.

Giữ nguyên các chiều trạng thái tại kế hoạch §11: Dataset, Job, Mapping proposal, Linkage, Comparison, Exception type, Run verification, Exception workflow. Không gom thành status chung. `RESOLVED` là xử lý ngoại lệ, không biến comparison thành `EQUAL`; review không sửa kết quả run bất biến. UI phải dùng enum/DTO Backend cùng bảng diễn giải tiếng Việt.

### 6.2. Liên kết trước, so sánh sau

Record linkage xác định bản ghi liên quan; comparison so giá trị của các bản ghi đó; verification độc lập kiểm tra kết quả. Cùng key khác tiền vẫn là `LINKED + AMOUNT_MISMATCH`, không trở thành hai bản ghi không liên quan. Không ghép chỉ vì tiền bằng hoặc vì tìm thấy số tiền gần hơn.

Theo thứ tự kế hoạch §18: partition scope → exact/composite keys → normalized keys được duyệt → 1:N/N:1 đúng grain → blocking → fuzzy candidates → giải quyết xung đột toàn cục → comparison → exception classification. Kiểm tra uniqueness trước 1:1, không ghép tham lam local-best làm dùng trùng bản ghi; tie/thiếu bằng chứng trả `AMBIGUOUS`. Đo blocking recall, giới hạn candidate/time/RAM, không làm N–M subset-sum không giới hạn.

Với ba file nội bộ/Shopee/TikTok, chia nguồn nội bộ theo platform rồi chạy từng cặp đúng scope; không JOIN ba nguồn trực tiếp. Thiếu kỳ, nguồn chưa đầy đủ hoặc settlement chưa đến hạn phải phân biệt pending/coverage với thiếu đối ứng được xác nhận. Không suy ra Settlement/Payout từ Orders khi thiếu nguồn thật.

### 6.3. Tiền và bất biến

- Chỉ so metric cùng định nghĩa, currency, time basis và grain hoặc có transformation/FX rule được duyệt. `total`, `gross`, `settlement` không mặc nhiên cùng nghĩa.
- Parse Decimal trực tiếp từ chuỗi với locale xác nhận, không đi qua binary float. Chọn precision/scale đủ; rounding mode và điểm quantize thuộc rule, không chọn tùy tiện.
- Theo kế hoạch §19, `delta = L - R`, `abs_variance = abs(L - R)`. Khi rule cho phép relative tolerance: `T = max(T_abs, T_rel * max(abs(L), abs(R)))`; đạt tolerance nếu `abs(L-R) <= T`. `T_abs` có đơn vị tiền, `T_rel` không thứ nguyên. Nếu không dùng relative tolerance, chỉ dùng absolute tolerance; mặc định 0 cho tiền cùng định nghĩa. Tolerance không chọn liên kết ID.
- Tách `EQUAL` khỏi `WITHIN_TOLERANCE`. Null/invalid, mixed currency hoặc semantics chưa tương thích trả `NOT_COMPARABLE`, không đánh giá như zero. Group amount là tổng signed amounts đúng metric/currency/grain/rule và membership không lặp.
- Bảo toàn từng nguồn: `N_input = N_invalid + N_out_of_scope + N_in_scope`. Các partition chính của in-scope loại trừ nhau và cộng đủ. Nhãn ngoại lệ phụ có thể nhiều trên một record, không cộng như partition.
- Tổng tiền theo metric/currency cộng được phải bảo toàn qua partition/grouping; invalid amount báo riêng. Mỗi record đóng góp một lần trừ khi có rule phân bổ được duyệt và trace đầy đủ. Không hợp thức hóa JOIN nhân tiền.
- Idempotency (chạy lại không tạo tác động nghiệp vụ ngoài ý muốn): cùng artifact IDs, mapping/contract/engine revisions và scope cho cùng logical groups/statuses/metrics; không yêu cầu run ID/timestamp giống nhau.

### 6.4. Verification và metrics chính thức

Verifier độc lập với Matcher: kiểm tra partition, membership/cardinality, amount conservation, comparison semantics, evidence và determinism. Oracle (kết quả kiểm tra độc lập) phải từ fixtures tính tay hoặc aggregation đơn giản khác implementation; không so bản sao số Matcher ghi với chính nó. Verification fail thì không publish metrics/report “đã xác minh”. Artifact hoàn tất trước, DB transaction công bố refs atomically; rollback không lộ kết quả chưa đạt. Dọn orphan/temp files phải bảo thủ, có scope rõ.

Mọi KPI phải có comparison unit (CU: đơn vị so sánh nghiệp vụ), population, eligible denominator, metric/currency/period và revision. Theo kế hoạch §20:

| KPI | Cách tính |
|---|---|
| Verified full match rate | CU `LINKED` và `EQUAL/WITHIN_TOLERANCE` đã verified / eligible CU |
| Linkage rate | CU `LINKED` / eligible CU |
| Exception rate | Eligible CU có ít nhất một active exception / eligible CU |
| Unresolved cases | Số case `OPEN/IN_REVIEW`, không gọi là số đơn |
| Signed/absolute variance | Tổng `L-R` / tổng `abs(L-R)` của nhóm comparable, cùng metric/currency |
| Automation coverage | Eligible CU verified không cần quyết định thủ công ở run này / eligible CU; ghi rõ policy reuse |
| Review rate | Eligible CU cần review / eligible CU |

Mẫu số 0 ⇒ `N/A`; không 0%/100%. Liệt kê excluded/pending/invalid riêng. Với 1:N, không dùng source-row count thay CU/group count. Không cộng đa tiền tệ khi chưa có FX rule hợp lệ. FE/API/CSV/XLSX và Assistant dùng cùng **MetricSnapshot đã verified**, không tự tính lại.

Exception cases phải có run/group/CU, type, severity basis, evidence, workflow state, actor/timestamp/rule liên quan. Giải thích nguyên nhân phân biệt `HYPOTHESIS`, `SUPPORTED`, `UNKNOWN`; không gọi sort theo số tiền/tuổi case là AI risk score chưa benchmark. Không tự sửa tiền.

<a id="ai"></a>
## 7. AI, chính sách cloud và bộ nhớ

### 7.1. Vai trò và providers

AI hỗ trợ hiểu/phân loại dữ liệu, suy luận schema/grain, mapping ngữ nghĩa, planning, đề xuất transformation, giải thích ngoại lệ, diễn giải analytics và Assistant. Backend tính toán/kiểm chứng các kết luận cần chính xác: **AI đề xuất — hệ thống kiểm tra — người dùng duyệt khi cần**.

- Qwen công ty là provider ưu tiên cho tác vụ phù hợp; cấu hình base URL từ môi trường theo kế hoạch, model ID `knowledge`, không yêu cầu API key khi endpoint thực tế không yêu cầu, không thêm Authorization header giả. Không hardcode endpoint nhạy cảm/credentials vào source code.
- Khi được giao tích hợp, xác minh `/models` và inference bằng dữ liệu tổng hợp: HTTP 200 ở `/models` không chứng minh generation hoạt động. Không đoán model ID khác hoặc tự thay model.
- Gemini Flash-Lite và LlamaParse chỉ khi người dùng/policy cho phép và còn ngân sách. Mặc định `LOCAL_ONLY`, `external_request_budget=0`; LlamaParse có allowance/credits riêng. Qwen lỗi không cho phép tự chuyển dữ liệu sang cloud. Không tự gửi file doanh nghiệp ra ngoài.
- Thứ tự routing: reuse kết quả/template đã xác nhận và còn tương thích → deterministic rules → Qwen → Gemini khi được phép và có lợi ích đo được → human review. LlamaParse là tuyến parser riêng theo policy, không phải provider fallback cho mọi task.

### 7.2. Output và prompt contracts

Mỗi prompt có task ID/revision, input/output JSON Schema/Pydantic, instructions, samples/golden examples, constraints và compatibility theo policy/model. Giữ các tasks ở kế hoạch §23; không thêm agent framework.

Backend phải kiểm tra cấu trúc/kiểu, field/ID/evidence có tồn tại và được phép truy cập, grain/metric semantics, business constraints, allowlist transformations, unsupported claims và bằng chứng còn thiếu. JSON hợp lệ không chứng minh đúng nghiệp vụ; model confidence không phải độ chính xác đã hiệu chỉnh. AI được trả `UNKNOWN`, `AMBIGUOUS`, `NEEDS_REVIEW`, `INSUFFICIENT_EVIDENCE` theo schema của tác vụ; không ép kết luận và không tự thêm các giá trị này vào mọi enum (xem mục 16).

File, PDF, Excel cells, user data và tool output là dữ liệu không đáng tin, không phải chỉ thị hệ thống. Tách dữ liệu khỏi instructions; mọi tool arguments kiểm tra bằng code, allowlist, quyền workspace và giới hạn calls. Không cho AI chọn raw path, chạy Python/SQL tự sinh hoặc tự duyệt rule tài chính. Không mặc định hai model đồng thuận là truth.

Nếu provider không hỗ trợ Structured Outputs theo contract thật, hỗ trợ JSON prompt + strict Pydantic/semantic checks; không hạ validation. Retry hợp lý tối đa 0–1 lần cho AI theo kế hoạch §26; không lặp vô hạn hoặc retry liên tục để chữa thiếu semantic evidence.

### 7.3. Tốc độ, chi phí và memory

- Chỉ đưa profile và evidence samples có giới hạn/redaction vào context, không gửi toàn bộ hàng chục nghìn dòng; không gọi LLM per-row hoặc mỗi lần UI render.
- Reuse/cache theo scope và revisions; quyết định mơ hồ không được cache như confirmed. Polars/DuckDB xử lý vectorized/batch; concurrency thấp, đo CPU/RAM trước khi tăng.
- Ghi `ai_calls`, tokens, cloud requests, parser credits, cache hit, latency theo stage; chi phí gắn verified run. Chỉ báo usage/pricing đã có bằng chứng, không bịa unit cost hoặc hứa tốc độ trước khi đo.
- Persistent memory gồm dataset artifacts/lineage, approved schemas/mappings/rules, preferences, workflow và conversation/evidence refs. Mỗi phần có owner/scope/revision/source/status/timestamps, sửa/xóa theo quyền. Không biến thói quen thành rule tài chính, không gửi lại mọi dòng hội thoại, không fine-tune liên tục/vector DB mặc định.
- Assistant chỉ dùng typed read-only tools ở kế hoạch §34 trên verified facts đúng `run_id`. Mọi phát biểu định lượng phải có metric/run/evidence refs; thiếu dữ liệu thì nói rõ. Chạy run/review/approve qua API riêng và xác nhận user đúng workflow, không trao quyền tự duyệt cho model.

<a id="bao-mat"></a>
## 8. API, bảo mật và quyền truy cập

- API REST theo resource và prefix `/api` theo kế hoạch §27; DTO/enum ổn định. Error envelope thống nhất: `code`, `message_vi`, `details` đã redacted, `retryable`, `correlation_id`. Không trả stack trace, secret hoặc raw storage path cho FE; không nuốt lỗi, giả success hoặc dùng review như exception lỗi chung.
- Mỗi request, tool, evidence lookup và export đều kiểm tra authorization theo workspace/project; viewer không approve. POST jobs dùng idempotency key; GET lọc/phân trang server-side. Không token trong URL/FE bundle hoặc credentials trong logs/screenshots.
- Upload phải kiểm tra allowlist, MIME/magic bytes, size/row limits, ZIP/XML/malformed files và policy trước parse; không thực thi nội dung upload. Lưu theo scope, không chấp nhận path tùy ý hoặc truy cập xuyên workspace.
- Chống prompt injection bằng phân tách untrusted data và kiểm tra tools ở code, không chỉ dựa system prompt. Logs/AI traces/error details phải redact dữ liệu nhạy cảm.
- Export CSV/XLSX phải ngăn formula injection với dữ liệu text bắt đầu `=`, `+`, `-`, `@`, giữ đúng kiểu tiền/số âm hợp lệ; kiểm tra tại ngữ cảnh xuất file, không thay raw data.
- Secrets, `.env`, keys, tokens, dumps, uploads và Parquet/dữ liệu doanh nghiệp không vào Git hoặc image. `.env.example` chỉ chứa placeholders an toàn khi được giao tạo. Không dùng healthcheck gọi dịch vụ AI trả phí.
- Đây là sản phẩm hỗ trợ đối soát/kiểm tra sai lệch; không tự tuyên bố kết luận kiểm toán độc lập, độ chính xác tuyệt đối hoặc không bao giờ hallucinate từ vài tests.

<a id="giao-dien"></a>
## 9. Giao diện và demo local

### 9.1. Trải nghiệm thống nhất

Giữ **Modern Light SaaS Dashboard — Kosh-inspired**, lấy cảm hứng, không copy pixel/assets/branding. Light theme, xanh dương chủ đạo (`#2563EB`), nền `#F8FAFC`, card trắng, sidebar trái sáng; palette chi tiết theo kế hoạch §28. Sidebar: Tổng quan, Dữ liệu, Đối soát, Ngoại lệ, Báo cáo, Trợ lý AI, Cài đặt.

- Dashboard trực quan, tối đa một hành động chính mỗi màn hình; AI-assisted workflow thật, người dùng không cần biết code. Advanced settings chỉ mở khi cần, không bắt sửa JSON/config kỹ thuật ngay từ đầu.
- Bảng dễ tìm/lọc/kiểm tra, pagination, evidence drawer và truy ngược nguồn. Có loading/error/empty/success, progress và disabled thực; không file/run thì hướng dẫn bước tiếp, không hiện KPI 0% giả.
- Phân biệt gợi ý AI, đã xác nhận, không xác định và pending/missing; không badge “95% đúng” từ confidence. Không chatbot, nút, biểu đồ hoặc KPI giả khi Backend chưa hỗ trợ.
- Responsive tại desktop 1366/1440/1920, tablet 768, mobile 390; sidebar thành drawer, bảng scroll nội bộ. Keyboard focus, contrast và accessibility đối chiếu WCAG 2.2 AA; kiểm tra chứ không chỉ tuyên bố tuân thủ.
- Next action từ status là logic xác định, không gọi AI mỗi render. Tiền và trạng thái do Backend cung cấp, theo mục 6.

### 9.2. Truy cập thẳng Dashboard an toàn

Demo local mở thẳng giao diện, không bắt copy token từ `.env`; không hardcode token hoặc tắt auth middleware. Chỉ bật `LOCAL_DEMO_ACCESS` explicit khi **cổng công bố trên host bind loopback `127.0.0.1`**, host/origin allowlist và port mapping được kiểm tra. Chặn auto-access khi bind host `0.0.0.0`/LAN, qua public reverse proxy hoặc production; không tin header tự khai local. Bind `0.0.0.0` bên trong container có thể cần cho Docker network, không đồng nghĩa cổng host public.

Backend tạo/khôi phục session same-origin cho demo principal, HttpOnly, SameSite/TTL phù hợp, CSRF/origin checks cho write, workspace authorization mọi request; cookie Secure khi HTTPS, HTTP chỉ cho loopback demo. Kiểm tra DNS rebinding/host spoof. Ngoài local dùng auth bình thường; không mở anonymous data hoặc auto-access công cộng.

Phải test local Dashboard, non-local fail closed, anonymous API bị chặn ngoài demo, viewer không approve, CSRF write bị từ chối, isolation và restart. Nếu không bảo đảm auto-session an toàn, dùng phương án demo one-time server-initiated session trong loopback hoặc báo giới hạn; không lách bằng tắt bảo mật.

<a id="docker"></a>
## 10. Docker và tài nguyên

### 10.1. Một Compose project chính

Chỉ một Docker Compose project ứng dụng với frontend/Nginx, Backend, Worker và PostgreSQL, persistent data. Các service có thể là container riêng; không ép cả hệ thống vào một container. Không host lại Qwen. Kiểm tra cổng thật trước khi chọn, không chiếm cổng dự án cũ; số cổng trong kế hoạch chỉ là đề xuất.

Không tự tạo Compose test project, deploy thứ hai, container dev/test/backup/temporary trùng chức năng, database server mới khi hệ hiện có đáp ứng hoặc nhiều app xung đột port/storage. Ưu tiên unit tests, mocks, transaction rollback và test data cô lập trong hạ tầng hiện có. Không tạo container chỉ cho bước kiểm tra đơn giản có thể chạy trong container sẵn có.

Không chạy test có thể sửa/xóa dữ liệu thật trên dữ liệu đó. Nếu không thể kiểm thử an toàn trong môi trường hiện tại, báo giới hạn và yêu cầu phương án phù hợp khi cần; không tự tạo hạ tầng trái phạm vi.

### 10.2. Build và dọn tài nguyên

- Multi-stage build khi có lợi ích, `.dockerignore`, dependency tối thiểu, image gọn, không secrets/runtime data trong image; persistent volumes và healthchecks đúng chức năng. Không đổi kiến trúc Docker nếu thiếu lý do đã xác minh.
- Sau triển khai, kiểm tra containers thuộc project, images đang dùng, image cũ không còn tham chiếu và dữ liệu persistent volumes; báo dung lượng/tài nguyên còn lại.
- Chỉ dọn tài nguyên đã xác minh thuộc dự án, không còn cần, sau healthcheck/regression của bản mới đạt; giữ rollback image cần thiết. Không xóa image đang được container sử dụng, tài nguyên dự án khác hoặc named volumes/file data để tiết kiệm dung lượng.
- Không tự dọn cache/images toàn Docker host bằng lệnh global. Không chạy `docker compose down -v`, `docker volume prune`, `docker system prune --volumes` hoặc thao tác xóa dữ liệu tương đương. Restart/recreate phải giữ dữ liệu.

<a id="git"></a>
## 11. Git, GitHub và khôi phục

### 11.1. Repository và branches

- Một repository chính cho AI Reconciliation Studio, độc lập repository cũ: `https://github.com/MinhHoang1403/AI-Reconciliation-Studio`, remote `origin` là `https://github.com/MinhHoang1403/AI-Reconciliation-Studio.git`, nhánh chính `main`. Kiểm tra repository root, Git status, branch, staged/untracked changes và remote trước thao tác; bảo toàn thay đổi không thuộc nhiệm vụ của người dùng.
- Nếu chưa có Git repository, có thể khởi tạo local an toàn trong đúng workspace. Không đoán remote, tự nối repo cũ hoặc tạo remote khác để tránh blocker. Chỉ push khi xác minh remote thuộc dự án mới và phạm vi đã được cho phép.
- Thay đổi nhỏ có thể trên `main` sau kiểm tra; thay đổi lớn/rủi ro dùng một feature branch trong repository hiện có. Không clone lần hai, tạo Git worktree hoặc Docker riêng. Tích hợp lại `main` an toàn sau tests; chỉ xóa branch đã tích hợp khi xác minh không còn thay đổi cần giữ. Không nhiều branch thừa/thử nghiệm kéo dài.
- Không force-push, reset hard hoặc phá lịch sử/dữ liệu. Public/Private theo quyết định chủ dự án; không tự đổi visibility.

### 11.2. Commit và push

Sau mỗi nhóm việc hoàn chỉnh: kiểm tra files/diff/tests → secrets và dữ liệu nội bộ → loại thay đổi ngoài phạm vi → stage đúng files → commit có ý nghĩa → push lên `origin` đúng nhánh khi đủ điều kiện → xác minh local/remote commit và status sau push → báo commit hash. Kiểm tra thay đổi mới trên remote trước push, không ghi đè lịch sử. Không commit rỗng, không stage toàn workspace khi chưa kiểm tra, không commit runtime data hoặc bí mật theo mục 8. Message phải mô tả nội dung, không `fix all`, `final`, `new`, `update everything` mơ hồ.

Thiếu Git identity thì báo, không tự bịa danh tính. Có thể commit local khi Git được cấu hình dù chưa có remote; thiếu remote/xác thực/conflict phải báo **BLOCKED cho bước Git liên quan**, không trình bày như đã push hoặc đổi sang repo khác. Việc này không xóa kết quả tài liệu/code đã kiểm chứng.

Trước public push phải kiểm tra cả nội dung tài liệu, metadata và lịch sử được push, không chỉ scan pattern secrets. Không đẩy tài liệu nội bộ, endpoint nhạy cảm, dữ liệu khách hàng hoặc dữ liệu “giả lập” còn chứa thực tế. Hai file quy tắc cũng cần kiểm tra như các file khác; không mặc định Markdown an toàn để public.

### 11.3. Backup và rollback

GitHub lưu source/history, **không thay backup PostgreSQL, uploads, Parquet hoặc Docker volumes**. Trước thay đổi ảnh hưởng dữ liệu: xác định scope, kiểm tra backup, bảo vệ nguồn, chuẩn bị rollback code/schema và cách khôi phục phù hợp. `git checkout` không khôi phục database. Không migration phá hủy nếu chưa có phương án bảo toàn dữ liệu; xác minh backup/restore bằng kiểm tra phù hợp, không chỉ nói đã có file backup.

<a id="kiem-thu"></a>
## 12. Sửa lỗi và kiểm thử

### 12.1. Sửa từ nguyên nhân gốc

Tái hiện → xác định module → phân tích nguyên nhân gốc → kiểm tra contract → xác định dependencies bị ảnh hưởng → regression test khi phù hợp → sửa nguyên nhân → chạy tests → kiểm tra regression → cập nhật tài liệu khi hành vi đổi. Nếu lỗi thiết kế, đánh giá toàn pipeline trước thay đổi. Không thử sửa ngẫu nhiên nhiều module, hạ validation hoặc đổi expected output chỉ để test PASS.

### 12.2. Bằng chứng phù hợp phạm vi

Phân biệt unit, property-based, contract, integration, golden, E2E, security, performance và **live AI / mock AI**. Chạy checks phù hợp thay đổi; không tạo framework/test môi trường dư thừa cho sửa tài liệu đơn giản. Với nhiệm vụ chỉ tài liệu, kiểm tra nội dung/đường dẫn/Markdown/consistency thay cho chạy ứng dụng chưa tồn tại.

- Unit test PASS không chứng minh toàn tính năng hoạt động; mock PASS không phải live PASS. Live AI chỉ khi được giao, policy cho phép, dữ liệu phù hợp và có budget khi cần. PDF/DOCX chưa live chỉ được gọi là verified adapter contract nếu đúng bằng chứng.
- Golden fixtures phải có nhãn/oracle độc lập; không để LLM/Matcher tự chấm chính nó. Giữ catalogue F01–F29/T01–T40 của kế hoạch; T01–T16 tiếp tục sau giai đoạn 2/3, T17–T35 tiếp tục giai đoạn 3. Lỗi mới giữ thành regression test có ID/tên rõ; không xóa case cũ để che failure.
- Bắt buộc edge cases liên quan: file rỗng/hỏng/multi-sheet/header/công thức/OCR; zero-prefix; null/invalid/âm/locale; duplicate keys; gross/net; 1:N/N:1/mixed currency; cutoff/coverage; fuzzy tie/ID; tolerance boundary; partition/membership/amount/evidence; crash trước publish; denominator 0; export injection; auth/CSRF/isolation/cloud OFF.
- Đổi algorithm/engine/prompt revision phải replay gold liên giai đoạn và giải thích thay đổi hợp lệ. Không đổi semantic contracts/formula để “chữa” test.
- Benchmark 1k/10k/50k, 100k tùy tài nguyên; ghi máy/workers/GPU, parse/profile/mapping/normalize/match/verify/render latency p50/p95, peak RAM, AI calls/cost và review decisions. Tách split chọn threshold khỏi test cuối.
- Mục tiêu ở kế hoạch §36 (mapping precision ≥98%, auto linkage precision ≥99.5%/recall ≥95% trong phạm vi hỗ trợ) là mục tiêu đánh giá, không kết quả đã đạt. Báo riêng recall/abstention/auto-approve population; không tuyên bố 99% khi chưa có labeled evaluation.

<a id="quy-trinh"></a>
## 13. Quy trình thực hiện nhiệm vụ

1. **Đọc nguồn:** thực hiện mục 1; không bỏ `Rules.md` hoặc mặc định báo cáo cũ còn đúng.
2. **Kiểm tra hiện trạng:** Git/root/branch/diff, files liên quan, dependencies, dữ liệu và tests; kiểm tra Docker services khi nhiệm vụ liên quan runtime. Chỉ kiểm tra môi trường cần thiết, không tạo mới để kiểm tra.
3. **Xác định phạm vi ngắn:** mục tiêu, modules/files, contracts ảnh hưởng, phần phải bảo toàn và cách kiểm chứng. Không lập kế hoạch dài cho sửa nhỏ.
4. **Thực hiện:** đúng yêu cầu/kiến trúc/contracts; chỉ sửa phần ngoài scope khi có dependency rõ và thuộc phạm vi được phép. Không thêm file, feature, môi trường hoặc abstraction không cần.
5. **Kiểm chứng:** logic, tests, dữ liệu, bảo mật, regression và Docker nếu liên quan. Ghi lệnh/kết quả thực và phần chưa kiểm tra.
6. **Dọn dẹp:** bỏ file tạm do nhiệm vụ tạo, kiểm tra dependency mới/tài nguyên riêng dự án; chỉ dọn phần đã xác minh an toàn theo mục 10, không đụng tài nguyên/dữ liệu khác.
7. **Git:** kiểm tra diff/secrets, stage/commit/push và xác minh theo mục 11. Không dùng thành công của một bước để che blocker bước khác.
8. **Báo cáo:** tiếng Việt theo mục 15, kèm mức sẵn sàng cho nhiệm vụ tiếp theo; không tự bắt đầu giai đoạn mới.

<a id="nghiem-thu"></a>
## 14. Nghiệm thu và bàn giao ba giai đoạn

Chỉ có ba giai đoạn theo kế hoạch §§32–34; không đổi tên thực thể/hợp đồng ở giai đoạn sau để làm lại engine trước đó.

| Giai đoạn | Phạm vi và bàn giao bắt buộc | Giới hạn |
|---|---|---|
| 1. Nền tảng dữ liệu + AI Smart Setup + UI cơ sở | Raw → Parsed → Proposal → Approved Mapping → Canonical; auth/local demo, upload, parser adapters/policy, profiling, Qwen Gateway, normalization, memory/restart; bàn giao `CanonicalDataset`, `DatasetProfile`, `SchemaDefinition`, `MappingRevision`, `EvidenceRef`, `JobStatus`, `WorkspacePolicy`, artifacts scoped/quality và contract tests | Không xây matcher, dashboard tài chính hoặc chatbot đầy đủ |
| 2. AI Planning + Matching/Verification + Results | Consume contracts giai đoạn 1; approved reconciliation rules, exact/group/controlled candidates/conflicts, Decimal comparison, independent verification, MetricSnapshot, Exception Inbox/evidence, exports; demo 3-file ecommerce có nhãn và bộ 2-file ngoài ecommerce | Không viết parser/mapping thứ hai; chưa cần Assistant chat hoàn chỉnh |
| 3. Contextual Assistant + tự động hóa + release | Consume `VerifiedRun`, `MetricSnapshot`, `EvidenceRef`, `ExceptionCase` qua typed read-only tools; hội thoại/policy/cost, worker recovery, security/performance, backup/restore, full E2E và release sanitization | Không tự tính tiền/KPI trong LLM hoặc tự duyệt rule tài chính |

Giai đoạn sau chỉ nhận đầu vào khi gates trước đạt; diff tồn tại phải được ghi, migrations không ảnh hưởng dữ liệu khác, compatibility tests bảo vệ luồng trước. Trước dòng code ứng dụng đầu tiên thực hiện checklist kế hoạch §40 trong nhiệm vụ triển khai được giao, không thực hiện checklist đó bằng cách dựng hệ thống ngay ở lượt thiết lập quy tắc.

Một nhiệm vụ chỉ hoàn thành khi deliverable đúng phạm vi đã có, contract được đáp ứng, checks liên quan đạt, không còn lỗi nghiêm trọng/regression đã biết thuộc phạm vi, không vi phạm bảo mật/làm mất dữ liệu, tài liệu cập nhật và trạng thái Git được báo đúng. Với nhiệm vụ code, phải chứng minh chức năng thật; với tài liệu, phải đọc lại/đối chiếu/kiểm tra links và formatting. Commit/push hoàn tất khi có remote đúng và đủ điều kiện; nếu không, nêu phần Git bị BLOCKED.

Nghiệm thu ứng dụng cuối cùng phải chạy luồng kế hoạch §41: local Dashboard → upload → Smart Setup/review → normalization → approved plan → verified run → Dashboard/Exceptions/evidence → Assistant có facts → export → restart/reopen bảo toàn dữ liệu → thử ngành khác. Golden/property/security/E2E và monetary invariants phải đạt; không coi đủ số modules là DONE. Báo trung thực mọi partial/live/mock/blocked và known limits.

<a id="bao-cao"></a>
## 15. Ngôn ngữ và báo cáo

Mọi giải thích cho người dùng bằng **tiếng Việt**, giữ tên kỹ thuật khi cần và giải nghĩa lần đầu. Dùng từ dễ hiểu và ví dụ thực tế: schema là cấu trúc dữ liệu, mapping là ánh xạ trường, profiling là phân tích đặc điểm dữ liệu, normalization là chuẩn hóa, regression test là kiểm tra chức năng cũ không bị hỏng, rollback là khôi phục trạng thái phù hợp. Không lạm dụng tiếng Anh.

Báo cáo ngắn, tránh lặp; gồm: việc đã làm, files thay đổi và lý do, checks/lệnh/kết quả (phân biệt live/mock/chưa chạy), Docker nếu liên quan, commit hash/remote/push status, lỗi/giới hạn/mâu thuẫn còn lại và điều kiện chuyển việc tiếp theo. Báo cáo giai đoạn bổ sung APIs/migrations/test counts và screenshots UI không secrets khi phù hợp. Không nói “PASS”, “verified”, “đã push” hoặc “sẵn sàng release” khi thiếu bằng chứng tương ứng.

<a id="can-lam-ro"></a>
## 16. Điểm cần làm rõ khi triển khai

Các lưu ý dưới đây ghi nhận cách diễn đạt trong kế hoạch, không sửa kế hoạch hoặc tự tạo nghiệp vụ mới:

- Kế hoạch §18, F22 và T29 có chỗ dùng `MISMATCH` làm tên rút gọn, còn enum comparison ở §11 là `AMOUNT_MISMATCH`/`ATTRIBUTE_MISMATCH`. Khi chốt schema/API phải chỉ ra ngữ cảnh và xác định giá trị enum cụ thể theo §11; không thêm `MISMATCH` làm enum chung một cách ngầm định.
- `NEEDS_REVIEW` ở các gates và `INSUFFICIENT_EVIDENCE` trong yêu cầu AI biểu đạt thiếu bằng chứng/review. Không mặc định đây là thành viên của mọi enum Dataset/Mapping/Run. Output schema từng tác vụ phải xác định trường nào mang thông tin này, cùng workflow review và error codes phù hợp.
- Model/API Qwen thực, khả dụng Gemini, policy/credits LlamaParse, resource limits, ports, lockfile compatibility và các mục `[V]` vẫn cần kiểm tra ở nhiệm vụ triển khai tương ứng. Nội dung cấu hình trong kế hoạch không phải bằng chứng live PASS; chưa kiểm tra thì báo chưa kiểm tra, không tự đổi provider/kiến trúc.

Nếu các điểm trên ảnh hưởng quyết định triển khai mà chưa đủ hợp đồng, nêu rõ và yêu cầu làm rõ phần phụ thuộc; vẫn có thể hoàn tất tài liệu hoặc phần độc lập đã được giao.
