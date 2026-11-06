# AI RECONCILIATION STUDIO — KẾ HOẠCH TỰ ĐỘNG HÓA VÀ TỐI ƯU TRẢI NGHIỆM TOÀN HỆ THỐNG

> **Tài liệu:** Product requirements + technical design + implementation contract + acceptance plan  
> **Ngày đề xuất:** 06/11/2026  
> **Trạng thái:** Đặc tả mục tiêu được chủ dự án yêu cầu, **chưa phải chức năng đã triển khai hay đã nghiệm thu**.  
> **Vị trí đề xuất trong repository:** `docs/AUTOMATION_PRODUCT_PLAN.md`  
> **Repository:** <https://github.com/MinhHoang1403/AI-Reconciliation-Studio>  
> **Nhánh nguồn đã đối chiếu:** `codex/foundation-reliability-hardening`, HEAD `4124d17f2c4ca0205fe8283bce716a68ac5e9424`  
> **Revision ứng dụng được Codex báo triển khai và kiểm thử:** `58cbc3c4781d6f331b7c67c2007844bb5b012bce`  
> **Ứng dụng local:** <http://127.0.0.1:18180>

## 0. Phạm vi, nguồn sự thật và nguyên tắc thực hiện

### 0.1. Mục đích

Thực hiện **một chương trình tối ưu tích hợp từ đầu đến cuối**, đưa AI Reconciliation Studio từ một ứng dụng yêu cầu người dùng phải hiểu ánh xạ/chuẩn hóa/thiết lập quy tắc thành sản phẩm vận hành theo cách:

**Tải dữ liệu → Hệ thống tự đọc, chuẩn bị, kiểm tra, lưu → Người dùng xem/hỏi dữ liệu → Chat yêu cầu đối soát → Xác nhận quyết định nghiệp vụ mới nếu cần → Xem kết quả/biểu đồ/bằng chứng → Xuất báo cáo.**

Không chia thành nhiều đợt phát hành cần chủ dự án phải tự kiểm tra và yêu cầu sửa liên tục. Codex được phép triển khai lần lượt các nhóm phụ thuộc **trong cùng một nhiệm vụ**, chủ động kiểm thử, sửa lỗi phát hiện và tiếp tục cho đến cổng nghiệm thu cuối hoặc blocker thực sự không thể khắc phục an toàn.

### 0.2. Thứ tự ưu tiên tài liệu và tính tương thích

1. Tuân thủ `AGENTS.md` và **đọc toàn bộ `Rules.md`** trước triển khai.
2. `docs/PROJECT_PLAN.md` và các hợp đồng đang được phê duyệt vẫn là nguồn sự thật cho **các phép tính, an toàn dữ liệu, xác nhận, quyền, kiến trúc và chức năng đã có**.
3. Tài liệu này là **đặc tả bổ sung được chủ dự án yêu cầu cho hành trình tự động hóa/UX mới**. Nếu mâu thuẫn với quyết định cũ của `PROJECT_PLAN.md` về thời điểm tự động khởi chạy, Codex phải ghi rõ và đồng bộ quyết định mới vào tài liệu chính thức khi triển khai; **không âm thầm thay đổi luật nghiệp vụ**.
4. Không sử dụng nội dung báo cáo lịch sử như bằng chứng chức năng mới đã PASS.
5. Những lựa chọn kỹ thuật được nêu là *giải pháp đề xuất*, cần xác minh hợp đồng API, performance và migration trước khi code; **đầu ra và bất biến dưới đây mới là bắt buộc**.

### 0.3. Phạm vi giữ nguyên

- **Modular Monolith** với FastAPI, Worker, PostgreSQL, React/Vite/Nginx; một Compose project Studio; Backend và Worker dùng chung source/image theo thiết kế hiện hành.
- Giữ nguyên **raw bất biến, artifact/checksum, provenance, revision, owner/workspace isolation, transaction/nonce/fingerprint/idempotency**, approval và lịch sử.
- Giữ **Matching Engine, Decimal/tolerance, Independent Verifier, snapshot, chứng cứ và công thức KPI** trừ khi phát hiện lỗi có oracle chứng minh; không thay chỉ để làm mới code.
- Giữ **Gemini 3.5 Flash Lite** và **Ollama Qwen 3:8B** là hai lựa chọn được người dùng biết; không âm thầm chuyển provider. Gemini mặc định theo cấu hình bản foundation; tình trạng HTTP 503 phải được báo đúng.
- Giữ Polars, fastexcel, openpyxl, RapidFuzz, DuckDB, ECharts, TanStack Table, Pytest/Hypothesis/Playwright; không lắp thêm framework Agent/DB/vector store/Redis/Kafka/Airflow/Spark vì lý do trang trí kiến trúc.
- Không sửa dữ liệu hoặc quyền của AIDataReconcileEngine, ShopQueryAI, ChatSAR, Langfuse hay dự án khác.

### 0.4. Baseline đối chiếu (không phải kết quả của kế hoạch mới)

| Thành phần | Baseline Codex báo cáo ngày 06/11/2026 |
|---|---|
| Backend/PostgreSQL | 479/479 PASS |
| Browser E2E | 139/139 PASS |
| Docker | 4/4 Studio healthy, backend/worker/frontend cùng revision `58cbc3c` |
| Dữ liệu TEST ba nguồn | 5.487 dòng gốc; 5.458 hợp lệ / 29 cần xem xét theo mapping đã duyệt |
| Đối soát 01↔02 | 2.040 khớp, 200 lệch tiền, 215 thiếu đối ứng; lệch có dấu +7.867 VND / tuyệt đối 60.883 VND |
| Đối soát 02↔03 | 323 khớp, 40 lệch tiền, 31 thiếu đối ứng; lệch có dấu −8.306 VND / tuyệt đối 11.812 VND |
| Hạn chế Agent LIVE | Qwen Planner `AI_PLAN_MISSING`/sai nhóm, câu hỏi top chênh lệch bị hiểu sai; Gemini có HTTP 503; Qwen chậm chặn job file trên Worker chung |
| Git | `codex/foundation-reliability-hardening` HEAD `4124d17`; `main` chưa merge |

Baseline phải được **đo lại trên máy thật trước khi sửa** vì source, Docker và commit có thể đã thay đổi sau thời điểm viết tài liệu.

---

## 1. Yêu cầu sản phẩm và hành trình người dùng (product contract)

### 1.1. Người dùng mới — chưa có mapping được duyệt

1. Vào Studio, tạo/chọn dự án; kéo thả một hoặc nhiều CSV/XLSX ở Chat hoặc mục **Dữ liệu**.
2. Upload thành công thì **tự động khởi chạy** parse/profile, kiểm tra định dạng, nhận diện cột và tạo kết quả chuẩn bị. Không cần gửi câu “hãy chuẩn hóa”.
3. Có thể xem **Dữ liệu gốc** ngay sau khi parse thành công, không đợi LLM.
4. Hệ thống tự điền các loại/format/chuyển đổi **có bằng chứng kiểm chứng được**, lưu bản chuẩn bị (`prepared`) và thống kê đầy đủ.
5. Chỉ với ý nghĩa quan trọng chưa thể chứng minh (grain, gross/net, timezone, currency, khóa nghiệp vụ, quan hệ...), hiển thị **một danh sách quyết định ngắn, bằng tiếng Việt dễ hiểu**, gom theo nguồn và mức ảnh hưởng; không bắt duyệt 9/11/10 trường.
6. Người dùng có thể tiếp tục xem/tra cứu raw và prepared dù chưa trả lời quyết định đó; không được gọi bản chưa duyệt là đủ điều kiện đối soát.
7. Khi người dùng yêu cầu đối soát, Backend tự tìm các phương án an toàn và quy tắc đã phê duyệt. Chỉ hỏi phần không thể xác minh, cho xem tóm tắt một lần rồi xác nhận.
8. Chạy engine và verifier; hiển thị kết quả, evidence, biểu đồ, xuất Excel/CSV; lịch sử, state, source version giữ qua reload/restart.

### 1.2. Người dùng quay lại — đã có mapping/rule được duyệt

- Tải dữ liệu kỳ mới/phiên mới với cấu trúc tương thích.
- Hệ thống tự phát hiện mapping/rule có khả năng tái sử dụng theo workspace, nghiệp vụ và dấu vân tay schema, kiểm tra độ tương thích và data drift.
- Chỉ **tự áp dụng quyết định cũ theo chính sách tái sử dụng đã được người dùng/owner cho phép**, đúng phạm vi đã duyệt, có audit/lineage và preflight lại; không tạo approval mới giả.
- Nếu tương thích không đủ: vẫn chuẩn bị phần an toàn, yêu cầu xác nhận khác biệt, không đánh đồng “tên tệp giống” với cùng nghiệp vụ.
- Khi có đủ nguồn và quy tắc đã duyệt, Chat có thể chạy đối soát theo yêu cầu; **không tự chạy/chốt báo cáo tài chính mới chỉ vì upload**, trừ khi có chính sách tự động riêng được phê duyệt rõ.

### 1.3. Người dùng chỉ muốn hỏi về dữ liệu

Có thể hỏi ngay sau parse:

- “Tôi đã tải những tệp nào? Bao nhiêu dòng?” → trạng thái từ metadata.
- “Cho tôi xem 20 dòng đầu của bảng thanh toán” → typed query trên raw.
- “Có bao nhiêu mã trùng?” → phép tính xác định có mô tả định nghĩa “trùng”.
- “Những dòng ngày sai là gì?” → quality findings và source row.
- “Dữ liệu này đã chuẩn hóa chưa?” → phân biệt raw/prepared/approved/revision.
- “So sánh bảng gốc với bản đã chuẩn bị” → so sánh giá trị theo source lineage, không sinh số liệu tưởng tượng.
- “Cho tôi ba khoản lệch tiền lớn nhất” → nếu có VerifiedRun hợp lệ, truy vấn theo `abs(delta)` và snapshot; nếu chưa có, giải thích rõ thiếu lần đối soát nào, không tự bịa kết quả.

### 1.4. Điều kiện “không chặn” và trường hợp phải dừng an toàn

**Không được chặn** xem raw, lưu prepared, tra cứu chất lượng và thao tác không gây thay đổi nghiệp vụ chỉ vì LLM lỗi hoặc chưa có quyết định gross/net.

**Phải chặn hoặc yêu cầu xác nhận** trước khi dùng một chỉ tiêu/khóa/tiền tệ/ngày chưa được xác minh để công bố kết luận đối soát. Phải chặn hành động khi vượt quyền, checksum sai, nguồn stale, thiếu evidence, schema không tương thích hoặc transaction không hợp lệ.

Mục tiêu “test liền mạch” nghĩa là **luôn có đường tiến tiếp an toàn**, không đồng nghĩa bỏ phê duyệt hoặc bảo đảm mọi tệp đều có thể tự suy ra ý nghĩa chính xác.

---

## 2. Luồng tự động chuẩn bị dữ liệu

### 2.1. Chuỗi xử lý chuẩn

```text
Upload (Chat / Dữ liệu)
    |
    v
Persist raw + ownership + content SHA + version + idempotency receipt
    |
    v
Parse / extract table / warnings / exact source line & sheet
    |----> Publish raw readable state (LLM-independent)
    v
Full profile + deterministic type/format/value/quality evidence
    |
    v
Find approved reusable mapping / schema candidate
    |
    +-- compatible: validate reuse policy + full preflight
    |
    +-- unmatched: deterministic candidates + bounded schema matching
    |                      |
    |                      +-- unresolved semantics --> optional typed LLM task
    v
Build typed mapping/transform candidate + provenance
    |
    v
Full-table preflight + produce AUTO_PREPARED artifact & quality findings
    |
    +-- no blocking business ambiguity, approved/reusable rules:
    |     may publish eligible canonical through the existing approval contract
    |
    +-- business ambiguity:
    |     prepared stays queryable; create concise decision requests
    v
Update project/dataset status + Chat notification + Data workspace
```

### 2.2. Bắt buộc ngay sau upload

- `persist_uploads(..., request_ai_mapping=False)` hiện diện trong bản đối chiếu lịch sử; Codex phải kiểm tra API upload của bản foundation hiện hành, không sửa theo đường dẫn cũ một cách máy móc.
- Tạo một **orchestrator sử dụng jobs/DB hiện có**; idempotency key gắn `(workspace, dataset_version, source_sha, processing_contract_revision, action)`. Không dựa vào tên file.
- Bước tiếp theo được enqueue sau commit của bước trước; không giữ transaction DB xuyên suốt inference hoặc đọc tệp lớn.
- Không làm lặp parse/profile/prepare khi cùng job được retry/restart; nếu schema/config thay đổi thì tạo **revision mới**, không ghi đè artifact cũ.
- Một file XLSX nhiều sheet có thể tạo nhiều bảng; mỗi bảng có trạng thái và lỗi riêng; khi header/sheet chưa chắc chắn, **đưa bằng chứng và lựa chọn** thay vì âm thầm lấy nhầm sheet.
- Nếu LLM chưa sẵn sàng, pipeline xác định vẫn hoàn thành phần có thể chứng minh và hiện trạng thái `NEEDS_BUSINESS_CONTEXT` khi cần.

### 2.3. Trạng thái nghiệp vụ

Đề nghị DTO hiển thị **cả giai đoạn xử lý và mức độ được phép sử dụng**; không tạo một enum đơn lẻ trộn lẫn `PARTIAL` với `APPROVED`.

| Chiều | Trạng thái logic | Ý nghĩa |
|---|---|---|
| Processing | `RECEIVED`, `PARSING`, `PROFILING`, `PREPARING`, `PREPARED`, `FAILED` | Tiến độ công việc kỹ thuật |
| Readiness | `RAW_QUERYABLE`, `PREPARED_QUERYABLE`, `BUSINESS_REVIEW_REQUIRED`, `RECONCILIATION_ELIGIBLE`, `STALE` | Quyền dùng đầu ra |
| Quality | `CLEAN`, `WITH_EXCEPTIONS`, `FAILED` | Phát hiện bất thường; không đánh đồng với readiness |

Các tên trên là **khái niệm đề xuất**, Codex phải map vào các contract hiện có và không tạo enum/table dư. API trả `source_revision`, `mapping_revision`, `canonical_revision`, `prepared_artifact_id`, `review_required`, `eligible_scope`, `quality_summary`, `updated_at` khi có căn cứ. Không công bố `RECONCILIATION_ELIGIBLE` nếu chưa qua authorization/approval/contract validation tương ứng.

### 2.4. Hợp đồng auto-prepared / approved canonical

- **Raw:** bytes bất biến; source hash + source rows, có thể truy vấn bản đọc được nhưng không làm mất giá trị gốc.
- **Auto-prepared:** artifact tách biệt có checksum, processing revision, typed field map, record status, per-value transform provenance, warnings; *không có `APPROVED` giả*; không thay thế canonical đã duyệt.
- **Approved canonical:** giữ cổng phê duyệt và compiler hiện hành. Có thể tái dùng mapping đã duyệt theo chính sách cho phép và kiểm chứng lại; chưa từng được duyệt thì cần quyết định mới của con người với trường quan trọng.
- Nếu không cần persistence mới có thể tái dùng artifact/version hiện hành với trạng thái mới. Nếu cần migration, phải mô tả forward/backward, defaults, unique indexes, data read compatibility; không phá lịch sử 24 bảng đã có.
- Trường hợp nhiều currency: giữ giá trị gốc và currency row, **không chuyển đổi tự động**; một trường tiền chuẩn hóa một tiền tệ có thể chứa `CURRENCY_MISMATCH` cho dòng ngoài phạm vi. Việc phân tách thành dataset theo currency là lựa chọn có hợp đồng và kiểm chứng, không tự tạo các con số cộng lẫn tiền tệ.

### 2.5. Kiểm tra chất lượng trên toàn bảng

Phải phân biệt: `source_rows`, `eligible_rows`, `invalid_rows`, `warning_rows`, `error_records`; một dòng có thể có nhiều lỗi. Ghi rõ lỗi hệ thống/contract khác lỗi giá trị nguồn. Có thể dự đoán kết quả preflight, không ghi approval trong preflight.

- Header duplicate, multi-line CSV, physical source row, sheet & formula semantics.
- Identifier as string, zero-prefix, Unicode, NULL/blank, decimal exact, negative/refund, date format/timezone/DST.
- Composite key, duplicate within allowed grain, unmatched join keys, amounts, multi-currency, invalid identifiers.
- Row-level evidence cho mọi lỗi; raw bytes giữ nguyên.
- Dữ liệu chuẩn bị không bị xóa/sửa âm thầm để “sạch” hơn.

---

## 3. Intelligent Schema Mapping và Rule Memory

### 3.1. Phân công trách nhiệm

| Thành phần | Đầu ra | Có thể tự quyết? |
|---|---|---|
| Deterministic profiler/Polars | Kiểu giá trị, phân bố, parse score, null, định dạng, cardinality, overlap | Có nếu kiểm chứng không mơ hồ |
| Approved Mapping Memory | Mapping/rule đã duyệt và dấu vân tay tương thích | Tái dùng đúng scope/policy với audit |
| RapidFuzz | Ứng viên tên cột tương đồng | Chỉ gợi ý |
| Valentine (tùy benchmark) | Xếp hạng cặp cột bằng schema/instance | Chỉ gợi ý |
| Qwen/Gemini typed | Entity/grain/money semantics + reason/candidate IDs | Không phê duyệt |
| Backend validator | Kiểm đúng ID, types, source/grain/keys/metrics/policy + full preflight | Quyết định tính hợp lệ kỹ thuật |
| Human approval | Xác nhận các quyết định chưa đủ bằng chứng | Quyết định nghiệp vụ |

### 3.2. Mapping candidate builder

- Chuẩn hóa tên cột đa ngôn ngữ, alias có nguồn/phiên bản; không hardcode tên 3 file test.
- Sinh các ứng viên từ schema, profiles, value distribution, uniqueness, missingness, cross-table overlap; xếp thứ tự giải thích được.
- Không dùng một điểm `confidence` tự tạo của LLM làm điều kiện tự phê duyệt. Mọi quyết định automatic phải có evidence và predicate kiểm chứng độc lập.
- `customer_code` không trở thành transaction key vì tên có `code`; unique không chứng minh grain. `gross_amount` khác `net_amount`, `EXPECTED` không đồng nghĩa paid; refund có dấu; date-only không chứng minh timezone.
- Nếu có nhiều ứng viên ngang nhau hoặc xung đột dữ kiện: giữ unresolved và hỏi người dùng đúng một thông tin cần thiết.

### 3.3. Mapping Memory

Tận dụng `MappingRevision`/artifact hiện hành, bổ sung indexing hoặc DTO khi cần. Reuse signature bao gồm ít nhất: workspace/project scope, entity/grain, source columns + types, business keys, currency/amount basis, date/time semantics, normalization operations, parser revision, approval lineage và policy scope. Tên file chỉ là tín hiệu phụ.

**Phân loại reuse:**

1. `EXACT_COMPATIBLE`: cùng hợp đồng và kết quả preflight đạt → có thể tái áp dụng nếu người dùng đã cho phép reuse.
2. `COMPATIBLE_WITH_NONCRITICAL_DRIFT`: thêm cột mô tả hoặc đổi thứ tự, cột quan trọng không đổi → chuẩn bị phần chắc chắn, ghi drift; nếu quyết định có ảnh hưởng thì review.
3. `BUSINESS_DRIFT`: đổi grain, khóa, currency, gross/net, timezone, trạng thái thanh toán, tolerance → không tự phê duyệt.
4. `INCOMPATIBLE`: profile/schema không còn khớp → đề xuất mới.

Tất cả auto-reuse có `rule_id`, `approved_by`, `approved_at`, `source_scope`, `applied_by=system`, `new_revision`, `evidence`, audit và khả năng rollback. Tái sử dụng không được vượt owner/workspace; không có học tự động xuyên tenant.

### 3.4. Thử nghiệm thư viện mới theo bằng chứng

| Thư viện | Quyết định | Benchmark bắt buộc | Quy tắc khi không đạt |
|---|---|---|---|
| Polars, fastexcel, openpyxl | Giữ/tận dụng | Exactness, RAM, performance, source fidelity | Không thay nếu regress |
| RapidFuzz | Mở rộng candidate mapping | Precision@k, recall@k, latency | Giữ chỉ với giá trị tăng thêm |
| Valentine | Thử schema matcher không embeddings trước | So với RapidFuzz+profile trên dữ liệu unseen; CPU/RAM | Không tích hợp production nếu không cải thiện |
| Pandera | Thử validation Polars | Lỗi mới phát hiện, false-positive, RAM/latency, duplicate validators | Không thêm nếu tăng complexity |
| DuckDB | Tận dụng phân tích/oracle được phép | So SQL độc lập, Decimal/currency semantics | Không thay financial authority |
| Splink | Hoãn | Chỉ khi có record linkage thiếu khóa có oracle riêng | Không ép cài |
| ECharts/openpyxl | Giữ | Export/read-back, consistent charts | Không tạo chart/export stack mới |

**Không** thêm Valentine embeddings/sentence-transformers/Torch theo mặc định trên máy RTX 3050 6GB và RAM 16GB. Mọi dependency mới phải kiểm version/license/transitive security, pin trong lockfile, so build size và hiệu năng, rồi mới quyết định.

---

## 4. Reconciliation Planner — chuyển sang Backend-first

### 4.1. Vấn đề phải giải quyết

Từ báo cáo kiểm toán: Qwen định tuyến intent được nhưng Planner trả `AI_PLAN_MISSING`, hoặc tạo quan hệ gom nhóm sai; câu hỏi tiếp theo không phải đường lỗi mà người dùng nên gặp khi yêu cầu đối soát bình thường. Cần loại bỏ việc yêu cầu LLM tự tạo toàn bộ hợp đồng kế hoạch phức tạp từ văn bản trống.

### 4.2. Phương pháp

1. **Resolve intent & sources:** nguồn từ attachment/context/project/canonical được Backend resolve; người dùng chưa nói đủ nguồn mới hỏi chọn nguồn.
2. **Readiness gate:** tìm approved canonical/reusable rules và giới hạn eligible rows; prepared không mặc nhiên eligible.
3. **Candidate generation:** tạo kế hoạch hợp lệ từ thống kê và các hợp đồng sẵn có; candidates gắn ID, bằng chứng join key overlap, duplicate, cardinality, grain, metric and basis, coverage, currency, date, tolerance; không tự bịa thời gian và completeness.
4. **Rank/explain:** Qwen/Gemini chỉ chọn hoặc diễn giải ứng viên có ID và đề xuất câu hỏi còn thiếu; local Qwen dùng structured output nhỏ.
5. **Typed validator & preflight:** compiler kiểm tất cả chi tiết; loại quan hệ sai thay vì sửa ngầm.
6. **Business review:** một thẻ tóm tắt ngôn ngữ tự nhiên, hiển thị **chỉ các quyết định thực sự chưa được xác nhận**; có “Xem chi tiết” và “Chỉnh sửa”.
7. **Approval:** giữ transaction, nonce/fingerprint, authorization, evidence, row-exclusion confirmation và idempotency. Quy tắc mới có ảnh hưởng tài chính bắt buộc duyệt.
8. **Execution:** Existing Matching Engine → Independent Verifier → immutable snapshot → analytics/export.

### 4.3. Reuse reconciliation rules

Chỉ tự sử dụng quy tắc được duyệt khi cả hai nguồn có cùng business scope, grain, metric/basis, currency, timezone, period/coverage policy, cardinality, aggregation, tolerance và các cột liên kết còn đúng. Kỳ mới được lấy từ dữ liệu được kiểm chứng hoặc người dùng cung cấp; không giả định kỳ hoặc `allow_partial`.

Nếu thiếu coverage/effective period/FX semantics, hỏi người dùng chính xác phần còn thiếu; không chặn cả pipeline chuẩn bị dữ liệu.

### 4.4. Quy tắc không thay đổi

- Exact/composite, 1:1, 1:N, N:1, sign/refund, Decimal/tolerance, verifier, duplicate review, period & currency safety phải giữ.
- Candidate fuzzy (RapidFuzz/Splink tương lai) chỉ là đề xuất; không công bố kết quả “matched verified” nếu chưa có chính sách đã duyệt.
- Nếu AI Planner thất bại: hiện phương án Backend đã kiểm chứng và các câu hỏi cần thiết; nếu không có ứng viên hợp lệ, trả lời dễ hiểu và cung cấp form rút gọn, **không trả lỗi kỹ thuật như điểm kết thúc duy nhất**.

---

## 5. Chat Query, Facts, Analytics và báo cáo

### 5.1. Intent routing ưu tiên xác định

| Nhóm câu hỏi | Xử lý |
|---|---|
| File list, upload state, processing progress | DB metadata / job status, không cần LLM |
| Preview raw/prepared, số dòng, lỗi, thống kê | Typed Query DSL đã giới hạn nguồn và quyền |
| Query theo canonical đã duyệt | Typed Query DSL, revision explicit |
| Đối soát/rule mới | Backend candidate planner + LLM chỉ khi còn ngữ nghĩa |
| Top-N mismatch, unmatched, signed/absolute totals | VerifiedRun snapshot + typed filters, sort, stable group ID |
| Follow-up “dòng thứ hai”, “nhóm này” | Dựa trên query-selection đã lưu, run/revision/cursor/sort và item ID |
| Giải thích chênh lệch | Deterministic facts + evidence; LLM chỉ diễn đạt, không thay số |
| Biểu đồ | Chart spec gắn verified metrics; không tính KPI trong Frontend |
| Xuất CSV/XLSX | Existing export job, snapshot immutable và read-back |

### 5.2. Hợp đồng Q&A bắt buộc

- Phân biệt `raw`, `prepared`, `canonical`, `verified_run`; tiêu đề/bảng phải hiển thị nguồn và phiên bản đang xem.
- Câu hỏi không nêu nguồn nhưng có ngữ cảnh duy nhất phải dùng đúng ngữ cảnh; nếu nhiều nguồn khác nhau phù hợp thì hỏi một câu rõ ràng.
- “Ba nhóm lệch lớn nhất”: lọc **amount mismatch**, sort theo `abs(delta)` giảm dần, tie-breaker ổn định bằng `group_id`, limit 3; kết quả phải có signed delta, absolute delta, currency, run ID và source evidence.
- Câu hỏi kế tiếp “giải thích khoản thứ hai” phải mở item thứ hai **đúng bảng vừa hiển thị**, không phải dòng số hai trong database.
- Status `PARTIAL_VERIFIED` phải giải thích phần đủ điều kiện, phần chưa kiểm chứng và mẫu số; không gọi là đối soát toàn bộ.
- Không suy luận `payment_status` thành paid nếu rule chưa duyệt; không sum nhiều currency; không biến NULL thành 0.
- LLM output chỉ chọn source/metric/operator/sort/limit trong tập enum hợp lệ; Backend biên dịch và kiểm quyền/timeout/row limit; không thực thi SQL/Python tùy ý do model tạo.
- Không nhân bản logic tính tiền giữa Query Engine, Dashboard và Export: tất cả lấy từ cùng verified snapshot/fact set.

### 5.3. Báo cáo

Mẫu báo cáo mặc định gồm Tổng quan, Chất lượng dữ liệu, Khớp/Lệch/Thiếu, Xu hướng, Danh sách ngoại lệ ưu tiên, Evidence, Quy tắc & Phạm vi, Hạn chế/Excluded rows, Export CSV/XLSX. Chỉ render các phần có dữ kiện. ECharts hiển thị số Backend; openpyxl bảo toàn Decimal/string identifiers và chống formula injection trong cells xuất.

---

## 6. Giao diện và hành trình UX

### 6.1. Cấu trúc điều hướng

Sidebar tối giản:

- **AI Assistant** — hội thoại, tạo chat, lịch sử gắn dự án, tương tác qua tiếng Việt.
- **Dữ liệu** — danh sách nguồn, upload, raw, prepared, canonical, quality, revisions.
- **Đối soát** — danh sách các lần đối soát, cách ghép đã duyệt, kết quả, ngoại lệ.
- **Báo cáo** — bảng tổng hợp, biểu đồ, evidence, download.
- **Lịch sử** (có thể tích hợp trong AI Assistant để tránh menu trùng).
- **Cài đặt** — tài khoản, quyền, quyền riêng tư; không nhồi các cấu hình nhà phát triển trong luồng chính.

Chỉ một bộ điều hướng theo source of truth. Không dựng hai Data Manager hoặc hai ReviewCard độc lập.

### 6.2. Mục Dữ liệu là điểm xuất phát

Mỗi nguồn hiển thị: tên, số dòng, trạng thái parse/prepared/business eligibility, số dòng cảnh báo/lỗi, lần cập nhật và trạng thái job. Khi mở nguồn hiển thị **bảng dữ liệu trước** và ba tab chính:

1. **Dữ liệu gốc**: table server-side filter/sort/pagination, sheet/source row, download raw theo quyền.
2. **Đã chuẩn hóa**: prepared/canonical phân biệt rõ, phiên bản, hai cột trước/sau khi chọn một ô, lý do chuyển đổi và các giá trị bị giữ nguyên.
3. **Cần kiểm tra**: nhóm ngoại lệ theo nguyên nhân, dòng chịu ảnh hưởng, evidence, quyết định nghiệp vụ chưa xác nhận. Cho xem/sửa có kiểm tra nhưng không sửa raw âm thầm.

Chỉnh mapping chi tiết, xử lý revision, tái chuẩn hóa, xóa dữ liệu và inspect technical metadata ở menu bổ sung. Xóa/ghi đè phải giải thích ảnh hưởng các kết quả đang tham chiếu và cần xác nhận riêng.

### 6.3. Chat và thông điệp

- Header gọn, project/model đúng vị trí, nút `+` upload, composer bo tròn nền trắng, một hàng mặc định tự giãn; mobile đủ diện tích nhập.
- Khi upload xong, Chat có thể tự hiển thị **thông báo trạng thái có nguồn từ DB**, không cần gọi AI để tạo câu thông báo.
- Câu trả lời: **kết luận dễ hiểu → số liệu/những vấn đề đáng chú ý → bước tiếp theo → bảng/biểu đồ/evidence khi cần**.
- Không hiển thị mã lỗi như `AI_PLAN_MISSING` trong thông báo chính; cho xem kỹ thuật trong phần chi tiết. Không che lỗi thật, không giả vờ thành công.
- Nút hành động chỉ khi thật sự khả dụng và phải gắn đúng resource/revision; không có nút trang trí.
- Lựa chọn mới có hiệu lực cho tin nhắn mới, không đổi provider của job đã nhận.

### 6.4. Business decision card (UI xác nhận tối giản)

- Hiển thị *quyết định có ảnh hưởng*, không lặp mọi cột đã kiểm chứng.
- Mỗi câu hỏi chứa: diễn giải nghiệp vụ, đề xuất, dữ kiện giải thích, tác động dự kiến, lựa chọn “Đồng ý / Thay đổi / Xem chi tiết”.
- Nguồn nhiều câu hỏi có thể gom vào một bảng review tổng quan; người dùng có thể xác nhận tất cả các quyết định đã đọc trong **một thao tác submit có audit per-decision**; vẫn giữ backend approval cho từng resource/revision nếu hợp đồng yêu cầu.
- Không giới hạn tùy tiện số câu hỏi bằng cách bỏ qua nguồn thứ tư; dùng pagination/batch và trạng thái tiếp nối.
- Phê duyệt **không** được núp trong câu Chat. LLM không được tự gọi approve.
- Hỗ trợ draft save/reopen/TTL extension, partial edit và shared Chat/Data Manager từ bản foundation.

### 6.5. Accessibility/responsive

- 390, 768, 1366, 1440, 1920 px; keyboard/focus/IME, Escape/Enter/Shift+Enter, ARIA labels; bảng scroll vùng riêng không kéo ngang toàn trang.
- Giữ bố cục trắng, thoáng, không quá nhiều ô đóng khung màu; chữ body Chat khoảng 16px, bảng/actions khoảng 14px theo quy tắc trước.
- Không để review chiếm toàn màn hình hoặc text cố định cắt trong nút; loading là trạng thái có thể quay lại/refresh an toàn.
- Thử bằng **Browser E2E + thao tác thật**, không chỉ screenshot CSS.

---

## 7. Job scheduling và độ tin cậy

### 7.1. Vấn đề gốc

Qwen có thể chiếm nhiều chục giây hoặc hơn 90 giây; một lượt infer đã làm job xử lý tệp chờ trên Worker chung. Sửa này **không chỉ là tăng timeout**.

### 7.2. Thiết kế lựa chọn theo benchmark

1. Đo queue wait, service time, Qwen/Ollama load/decode, CPU/RAM/VRAM, throughput, worker lease; theo `job_kind` và project.
2. Ưu tiên parse/raw preview và deterministic normalization hơn AI inference kéo dài; không dùng một priority queue đơn thuần khi vẫn chỉ có một worker chạy đồng bộ một job lâu.
3. Trước tiên đánh giá cô lập AI network wait bằng bounded concurrency/executor hoặc tách tiến trình xử lý công việc **trong kiến trúc hiện có**; không giữ DB transaction hay lock nguồn trong thời gian chờ inference.
4. Nếu không đáp ứng, chỉ cho phép thêm **một worker role/process chuyên AI trong cùng Compose project**, không thêm broker/service/database mới; đo chi phí RAM trên 16GB và không nhân đôi model Ollama trong Docker.
5. Giữ `SKIP LOCKED`, leases, idempotency, fencing, cancellation/recovery, resource ownership; tránh starvation giữa nhóm job. Có giới hạn hàng đợi/retention và lỗi rõ ràng khi quá tải.
6. Không fallback cloud âm thầm. Nếu Gemini 503, job đó kết thúc đúng trạng thái nhưng pipeline deterministic tiếp tục; lỗi AI mới có đường retry có điều kiện, không nhân đôi unknown delivery.

### 7.3. Quan sát (Observability)

Theo dõi tối thiểu: `upload_to_raw_queryable`, `upload_to_prepared`, `queue_wait_by_job`, `provider_attempts`, `failed_invalid_contract`, `review_decisions_per_source`, `reuse_rate`, `mapping_precision_recall`, `worker_recoveries`, `reconciliation_oracle_failures`, `export_snapshot_mismatches`. Không lưu nội dung dữ liệu nhạy cảm/prompts đầy đủ vào log công khai. Tách LIVE, MOCK, CACHED, BLOCKED.

---

## 8. API/DTO, dữ liệu và tương thích ngược

### 8.1. Quy tắc API

Ưu tiên mở rộng endpoint sẵn có; các đường dẫn sau **chỉ là ngữ nghĩa yêu cầu**, không yêu cầu tạo đúng đường dẫn nếu code đã có tương đương:

- Get project source list + processing/readiness/quality status.
- Get raw/prepared/canonical preview with source version and bounded page.
- Get quality findings and impacted rows.
- Get mapping candidate and explainable evidence.
- Save/resolve/reopen business decision.
- Get preparation job status; trigger safe reprepare/retry.
- Get reusable mapping/rule compatibility result.
- Get reconciliation candidates, preview, approval, run.
- Typed data query across permitted source kinds; verified run query and export.

Mọi mutation phải gắn resource ID, scope, revision/fingerprint, actor, idempotency; `POST` không thay semantics đọc. FE không tính KPI; Backends trả DTO typed, timezone/Decimal được serialized rõ.

### 8.2. Database migration

Đọc schema thực tế trước khi quyết định. Nếu bổ sung bảng/trường, Codex phải viết Alembic migration có rollback semantics được thử và safe defaults; không migrate bằng cách tính lại các artifact lịch sử. Có read compatibility với source/MappingRevision/CanonicalRow/VerifiedRun cũ. Backfill metadata nếu cần phải idempotent và bounded. Không sửa trực tiếp 24 bảng lịch sử để ép kết quả mới.

### 8.3. Đồng bộ trạng thái giữa các giao diện

Chat, Dữ liệu, Đối soát, Báo cáo phải đọc từ **cùng canonical API source-of-truth**, không mỗi nơi tự giữ lại một bản status hay mapping business riêng. React local state chỉ dành cho form chưa submit; draft cần khôi phục phải lưu Backend theo cơ chế review đã có. Refresh/navigation không xóa các chọn lựa người dùng đã lưu.

---

## 9. Test plan và oracle độc lập

### 9.1. Các lớp test

| Lớp | Phạm vi |
|---|---|
| Unit & property | parsing, decimal/date, type inference, schema compatibility, mapping candidates, financial calculations, query sort/limit, review-state transition |
| PostgreSQL integration | upload→jobs→artifacts→prepared→review→canonical; idempotency; schema migration; isolation |
| Contract/provider MOCK | structured output invalid/partial, missing fields, stale reviews, wrong source, 429/503, Ollama timeout, unknown delivery |
| LIVE Gemini/Qwen | actual mapping, partial reply, intent, planning, top mismatch query, cancellation/recovery; usage bounded and recorded |
| Browser E2E | người dùng mới từ upload đến report, responsive, keyboard, reload, data tabs, error paths, export |
| Fault & concurrency | restart worker, lease expiration, duplicate submit, concurrent approval, source stale, storage failure, LLM long-running |
| Security | unauthorized reads, cross-workspace/owner access, source-specific download, prompt injection, SQL/export safety, secrets |
| Benchmark | no-LLM raw/prepared, mapping score, queue fairness, RAM/VRAM, 75k rows, export performance |
| Data integrity | checksum, old artifacts, DB rows, historical approvals/outputs, backup/restore, rollback |

### 9.2. Oracle nghiệp vụ bắt buộc

**Bộ ba nguồn gốc:**

- `01_don_hang_du_kien_2400.csv`: 2.418 dòng, 2.406 hợp lệ / 12 ngoại lệ theo mapping đã duyệt.
- `02_su_kien_thanh_toan_2685.xlsx`: 2.685 dòng, 2.674 hợp lệ / 11 ngoại lệ.
- `03_sao_ke_ngan_hang_theo_lo.csv`: 384 dòng, 378 hợp lệ / 6 ngoại lệ.
- Tổng 5.487, trong phạm vi và hợp đồng mapping **5.458 hợp lệ / 29 ngoại lệ**.

**01↔02:** `scope + reference`, 1:N, `MAIN_VND`, VND, UTC, `[2026-10-01,2026-11-01)`, signed sum, tol 0 → 2.040 equal / 200 mismatched / 215 unmatched (160 left, 55 right), +7.867 VND signed, 60.883 VND absolute.

**02↔03:** `scope + batch_id`, N:1, so signed payment aggregate với `gross_amount`, cùng kỳ/currency/tolerance → 323 equal / 40 mismatched / 31 unmatched (18 left, 13 right), −8.306 VND signed, 11.812 VND absolute.

Cả hai `PARTIAL_VERIFIED` do dữ liệu có ngoại lệ; không giả VERIFIED toàn bộ. Nếu đường mới chưa được người dùng xác nhận quyết định nghiệp vụ, không được ép công bố canonical và run chỉ để khớp oracle.

### 9.3. Dữ liệu unseen bổ sung

Tạo golden fixtures độc lập cho hóa đơn, bán hàng, công nợ, tồn kho, trả hàng, lương, sai mã, NULL, đổi tên cột, multi-sheet, encoding, 1:1, 1:N, N:1, multi-currency, refund âm, incomplete period, duplicate key, header duplicate, quoted multiline CSV. Nhãn và oracle được xây dựng **độc lập với Matcher/Planner**. Không hardcode tên file/đáp án vào production. Kiểm theo nhóm dữ liệu mới chưa từng dùng khi thiết kế prompt.

### 9.4. Nghiệm thu hành trình bắt buộc

- **UAT-A**: Upload tệp kỳ mới có mapping đã duyệt → tự chuẩn bị và áp quy tắc cũ tương thích, không phải chat hay duyệt lại.
- **UAT-B**: Upload ba tệp mới chưa có mapping → raw queryable, prepared queryable, AI gợi ý, xác nhận phần nghiệp vụ còn mơ hồ qua UI tối giản, chuẩn hóa/canonical và đối soát qua Chat, evidence/report đúng.
- **UAT-C**: Upload hỗn hợp lỗi/đa tiền tệ/thiếu nguồn → cảnh báo chi tiết, không mất raw/không bịa, chỉ phần eligible có thể đối soát, người dùng vẫn tiếp tục xem và hỏi dữ liệu.
- **UAT-D**: Gemini 503 và Ollama timeout → deterministic path tiếp tục, no duplication, user được chọn model cho job mới, recovery qua UI.
- **UAT-E**: Worker restart đang parse/normalize 75.000 dòng → exactly one published result + correct lineage + recovery.
- **UAT-F**: “Ba nhóm chênh lệch lớn nhất”, “giải thích nhóm thứ hai”, “xuất Excel”, mở file Excel đọc lại, reload/reopen cùng snapshot, không hỏi sai completeness.
- **UAT-G**: Permissions/owner isolation; người không được phép không thể xem prepared/canonical/evidence/export của workspace khác.
- **UAT-H**: Năm kích thước responsive và keyboard/IME; người mới không cần dùng developer console/SQL/API để đi từ upload đến báo cáo trong các tình huống được hỗ trợ.

### 9.5. Chỉ tiêu nghiệm thu

**Hard gates (bắt buộc):**

- 100% oracle tài chính được định nghĩa đạt; **0 false auto-approval** trên bộ negative có nhãn; 0 cross-workspace leak, 0 duplicate publication, 0 silent currency conversion, 0 silent data loss.
- Full baseline + regression mới PASS trên source/image cuối; không skip test FAIL để đạt cổng.
- Không có P0/P1 hoặc P2 tái hiện gây nghẽn hành trình mục tiêu mà chưa xử lý.
- Raw queryable không phụ thuộc inference; prepared giữ phần an toàn khi LLM thất bại; manual editing nâng cao là tùy chọn, không là bước bắt buộc với dữ liệu bình thường đã đủ bằng chứng.
- Q&A top-N, follow-up, data status và reports đúng oracle và bằng chứng, kể cả khi LLM không hoạt động đối với những intent được Backend hỗ trợ xác định.
- Source/image/runtime, backup/restore/rollback, histories và audit đạt.

**Performance/UX metrics (phải đo, đặt ngưỡng theo baseline trước tối ưu):**

- `upload_to_raw_queryable` p50/p95 trên 10/1k/10k/75k rows.
- `upload_to_prepared` p50/p95, tách LLM-required/LLM-independent.
- Số thao tác/nhập liệu/số quyết định người dùng trên bộ dữ liệu compatible và new/unseen.
- Mapping precision/recall và severity-weighted error rate, false-positive/missed key/amount/grain metrics.
- Task queue wait p50/p95 khi Qwen chậm; memory & storage cost.
- Gemini/Qwen LIVE success/failure split theo intent, mapping, planner, reply; không dùng mock thay LIVE.

**Giới hạn nhà cung cấp:** Gemini HTTP 503 không thể bảo đảm biến mất từ code Studio. Có thể đạt **READY_FOR_SEAMLESS_LOCAL_UAT** nếu luồng dữ liệu và đối soát có đường hoàn thành hợp lệ, provider thất bại được xử lý an toàn và các test LIVE được công bố rõ; **không gọi AI_FULLY_ACCEPTED** nếu cổng LIVE tương ứng chưa đạt. Quy tắc mới chưa đủ bằng chứng phải hỏi, không bỏ guard chỉ để đạt trải nghiệm “không chặn”.

---

## 10. Quy trình thực hiện trong một nhiệm vụ, không chờ duyệt nhỏ lẻ

### 10.1. Khởi động Git và backup

1. Kiểm `git status`, remote, HEAD, kiểm secrets. Commit/push các thay đổi hợp lệ trên nhánh `codex/foundation-reliability-hardening` nếu có; không đưa runtime files/keys/logs/datasets vào Git.
2. Bảo toàn nhánh foundation làm mốc; tạo **một nhánh công việc mới** đề nghị `codex/intelligent-automation-experience` từ HEAD đã xác minh (không tạo repo/worktree khác trừ khi thực sự cần).
3. Chụp manifest DB tables, artifacts/checksums, image digests, volumes, Compose services, existing backups; tạo và thử restore backup đúng phạm vi Studio trước migrations.
4. Phân loại tất cả các tài liệu mâu thuẫn và cập nhật `PROJECT_PLAN.md` sau khi đã đối chiếu với yêu cầu mới. Giữ `Rules.md` làm quy tắc chung.

### 10.2. Triển khai trọn gói theo thứ tự phụ thuộc

**Gói A — Contracts & baseline:** rà API/jobs/mapping/canonical/query/review/UX; đưa các cổng bất biến và oracle vào test trước khi thay behavior.

**Gói B — Automatic Preparation:** enqueue sau upload; raw preview độc lập; deterministic candidate, prepared artifact, quality report, trạng thái, idempotency, restart.

**Gói C — Mapping & Memory:** reuse policy, diff/drift, candidate ranking; benchmark RapidFuzz/Valentine, Polars/Pandera, chỉ giữ dependency có lợi ích; partial AI semantics.

**Gói D — Planner:** Backend candidate generation, typed ranking, preview, safe approval; rule reuse; chính sách thiếu nguồn/coverage.

**Gói E — Typed Q&A & Reports:** raw/prepared/canonical/run queries, deterministic top-N, follow-up context, charts, evidence and export consistency.

**Gói F — UX:** Data sidebar/table/quality, review tối giản, Chat status, kết quả, Đối soát, Báo cáo; state dùng chung.

**Gói G — Worker & Reliability:** không để Qwen block parse, bounded concurrency, provider fault, security, 75k rows, restart, backup/rollback.

**Gói H — Integrated UAT & Release:** chạy full tests, Docker build/deploy, browser live workflows, verified image/source, docs, Git push/CI, final handoff.

Các gói là **workstreams nội bộ trong một đợt triển khai**, không phải yêu cầu người dùng duyệt sau từng gói. Codex chủ động quay lại sửa khi tích hợp phát hiện xung đột; không coi unit PASS ở một gói là kết thúc nhiệm vụ.

### 10.3. Công việc không làm

- Không merge `main` khi cổng Agent/UAT chưa đạt, trừ khi được chủ dự án yêu cầu rõ.
- Không thay model/tag, nâng GPU/RAM, thêm container broker/framework AI, rewrite backend, thay financial engine hoặc mô hình database toàn bộ chỉ để tối ưu cảm tính.
- Không tự xóa các dự án TEST/historical artifacts/approved mappings/logs cần audit, không global `prune`, không `down -v`.
- Không dùng Gemini ngoài policy hiện hành; không reset ledger/quota hoặc gọi nhiều lần vô ích khi đã có 429/503.
- Không ngầm sửa raw, auto approve quyết định có tác động tài chính, biến nguồn lỗi thành “clean”, hay trả bảng số liệu do LLM bịa.
- Không dùng `v1/v2/s1/s2/freeze/frozen` trong tên module/source hoặc tên class sản phẩm; tên revision hợp đồng chính thức/historical IDs có thể phải giữ để tương thích.

---

## 11. Bảng truy vết yêu cầu → hợp đồng → kiểm thử

| ID | Yêu cầu phải có | Vùng code dự kiến cần khảo sát | Bằng chứng nghiệm thu |
|---|---|---|---|
| AP-01 | Upload tự khởi chạy pipeline | upload/agent API, jobs, repository | E2E upload không cần prompt |
| AP-02 | Raw có thể xem khi LLM unavailable | parser/artifact, data query | MOCK provider down + raw browser |
| AP-03 | Prepared artifact không giả approved | normalization, contracts, revisions | DB integration + access safety |
| AP-04 | Full-table deterministic checks & lineage | profiling, mapping verification, normalization | Oracle row/error/checksum |
| AP-05 | Mapping reusable đúng scope | mapping repository, schema matching | EXACT/DRIFT/INCOMPATIBLE tests |
| AP-06 | Candidate mapping đáng tin | RapidFuzz/optional Valentine, AI Gateway | Unseen precision/recall + safety |
| AP-07 | Business decisions tối giản | Review API, shared UI, state | Browser no repeated technical edits |
| AP-08 | Backend-first rule proposal | planner, contracts, validator | Qwen/Gemini LIVE + negative tests |
| AP-09 | Rules có approval và policy | reconciliation API/repository | approval nonce/idempotency |
| AP-10 | Typed raw/prepared/run query | data_query, intents, context | top-N/follow-up oracle |
| AP-11 | Charts/CSV/XLSX cùng verified snapshot | export, analytics, UI | read-back + snapshot equality |
| AP-12 | Sidebar Dữ liệu và 3 tab | App/MappingStudio/UI | 5 viewport E2E, accessibility |
| AP-13 | Job không bị chặn bởi AI dài | Worker/jobs/scheduler | concurrency Qwen slow + parse |
| AP-14 | Recovery/permissions/data integrity | DB/jobs/access/artifacts | fault/security/restart/restore |
| AP-15 | Bản release sạch | Git, Docker, docs | HEAD/image/HTTP, 4 healthy, rollback |

Với mỗi ID, Codex phải ghi rõ trạng thái `PASS`, `FAIL`, `BLOCKED` hoặc `NOT_RUN` và dẫn tới test/receipt; không tuyên bố đạt bằng mô tả chung chung.

---

## 12. Báo cáo nghiệm thu và bàn giao

Báo cáo cuối phải gồm:

1. **Source of truth:** branch, baseline HEAD, commit cuối, working tree, remote SHA, source/image/HTTP revision.
2. **Architecture delta:** module/contract/DB migration/jobs/UX đã thay, giải thích vì sao cần.
3. **Những lỗi đã sửa:** nguyên nhân gốc, bài test tái hiện trước/sau, tác động liên module.
4. **Pipeline tự động:** thời gian upload→raw/prepared, số nguồn tự chuẩn bị, số review, cách xử lý nguồn mơ hồ.
5. **Mapping/Planner:** precision/recall, rule reuse/drift, Gemini/Qwen LIVE outcomes (kể cả errors), token/latency và giá trị benchmark Valentine/Pandera.
6. **Q&A:** số câu đúng oracle, top-N, follow-up, raw/prepared/canonical/run separation; errors/recovery.
7. **Matching/Reports:** full oracle, verifier, excluded rows, evidence, charts, CSV/XLSX read-back.
8. **UX:** screenshots/traces thật ở 390/768/1366/1440/1920, hành trình người dùng và giảm thao tác so baseline.
9. **Reliability/security:** priority/fairness, worker restart, provider errors, owner isolation, prompt injection, idempotency.
10. **Dữ liệu/Docker:** tables/artifact checksum before/after, backup/restore, current+rollback images, 4 healthy, dữ liệu dự án khác không đổi.
11. **Full regression:** số unique tests PASS/FAIL/SKIP/NOT_RUN; LIVE/MOCK/CACHED/BLOCKED phân biệt rõ.
12. **Kết luận chính xác:** `READY_FOR_SEAMLESS_LOCAL_UAT`, `PARTIAL_READY` hoặc `BLOCKED`; AI LIVE gate có thể chưa đạt dù deterministic local UAT đạt. Không claim zero-bug.
13. **Hướng dẫn user:** một kịch bản người dùng mới, thao tác chính xác trên UI local, không cần chỉnh API/DB/SQL; cách xử lý nếu cần xác nhận nghiệp vụ.

---

## 13. Tài liệu kỹ thuật tham chiếu

- Tài liệu nội bộ dự án: `Rules.md`, `AGENTS.md`, `docs/PROJECT_PLAN.md`, `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_STATUS.md`, `docs/USER_TEST_GUIDE.md` — **kiểm tra sự tồn tại, nhánh/revision và nội dung mới nhất**.
- Polars Lazy API: <https://docs.pola.rs/user-guide/lazy/>
- DuckDB Decimal: <https://duckdb.org/docs/stable/sql/data_types/numeric.html>
- RapidFuzz: <https://rapidfuzz.github.io/RapidFuzz/>
- Valentine (schema matching & evaluation): <https://delftdata.github.io/valentine/>; <https://github.com/delftdata/valentine>
- Pandera Polars integration: <https://pandera.readthedocs.io/en/stable/polars.html>
- Ollama structured outputs (typed JSON schema): <https://docs.ollama.com/capabilities/structured-outputs>
- PostgreSQL `SKIP LOCKED` queues: <https://www.postgresql.org/docs/current/sql-select.html>
- Pydantic validation: <https://docs.pydantic.dev/latest/>
- Playwright test traces: <https://playwright.dev/docs/trace-viewer-intro>
- Hypothesis stateful testing: <https://hypothesis.readthedocs.io/en/latest/stateful.html>
- OWASP ASVS: <https://asvs.owasp.org/>

> Các đường dẫn chính thức hỗ trợ phương pháp triển khai; không thay thế việc kiểm tra phiên bản đang pin, hợp đồng nghiệp vụ hoặc benchmark trên máy local. Cập nhật nguồn nếu tài liệu/phiên bản chính thức thay đổi.

---

## 14. Định nghĩa thành công

**Thành công không phải “AI luôn trả lời ngay” hay “mọi tệp đều được tự duyệt”.** Thành công là:

- Upload được tiếp nhận một lần, tự xử lý tối đa trong giới hạn an toàn, có thể xem raw và prepared mà không cần khởi động bằng Chat.
- Những quyết định quan trọng được hỏi đúng lúc, dễ hiểu và có bằng chứng; không ép người dùng cấu hình từng cột.
- Đối soát và báo cáo xuất phát từ hợp đồng được duyệt và phép tính xác định, đúng oracle; phần chưa đủ điều kiện được giữ riêng và giải thích rõ.
- Khi model/Worker lỗi, hệ thống không làm mất dữ liệu hay công việc, không nhân đôi, và vẫn có đường tiến tiếp hợp lệ.
- Người dùng mới có thể đi trọn hành trình trên UI mà không phải nhờ người phát triển chỉnh code, DB hoặc API giữa chừng.
- Source, tests, GitHub, Docker, backup, UI và hướng dẫn khớp nhau, có chứng cứ đủ để chủ dự án tự nghiệm thu trong một đợt.

**Đích nghiệm thu:** `READY_FOR_SEAMLESS_LOCAL_UAT`, đồng thời công bố riêng cổng `AI_LIVE_FULL_ACCEPTANCE` và mọi giới hạn nhà cung cấp chưa thể khắc phục. Không đổi nghĩa các cổng nghiệm thu chỉ để báo hoàn thành.
