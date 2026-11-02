# AI Gateway và provider contracts

**Kết quả 02/11/2026:** Gemini `gemini-3.5-flash-lite`, lifetime global/demo workspace **50/50, còn 0**, gồm 9 lượt lịch sử và 41 lượt mới; Agent 33/33, Planner 10/10. Không reset hoặc tự tăng trần. Planner đã có PASS LIVE sau sửa DTO/evidence/null composition; broad Agent NLP chưa đạt. Kết quả hiện hành ở [báo cáo mục S](IMPLEMENTATION_STATUS.md); các phần ngày 28–30/10 bên dưới là lịch sử. Qwen hoãn, parser jobs mới OFF, Argon chưa tích hợp; chưa merge hoặc release main.

Planner gửi DTO nhỏ `PlannerReply` bằng GenerateContent `responseJsonSchema` (serialization schema, Decimal chuỗi); server giữ source/scope đã xác nhận, ghép domain plan rồi chạy lại validator. `allowed_rule_evidence_ids` tách canonical/schema/artifact khỏi field-level evidence trong catalogue. Model chọn field evidence không đúng tầng bị từ chối, không lọc/sửa IDs để qua gate. Optional không gửi hoặc explicit null dùng `exclude_unset` và `exclude_none` khi ghép domain defaults; false/0/filters tường minh vẫn giữ. Missing confirmations không được tự điền thành approval. Mỗi Planner job1HTTP attempt; trace hash/status/loc/type không chứa input/secret. Google schema subset/complexity có giới hạn; UUID enum trong nested evidence array đã bị400 ở live, không dùng constraint đó để ép provider.

## Assistant có bằng chứng

Task `answer_verified_question`, prompt `assistant-grounded-1`, dùng cùng GeminiProvider/Gateway. Reuse facts trước, câu hỏi facts hỗ trợ được trả bằng backend deterministic; không gọi đây là LLM/live. Model chỉ chọn fact IDs và mã diễn giải allowlist theo `ModelAnswer`, không sinh prose/tiền/citations tùy ý. Backend kiểm FactSet/run/snapshot, claims và render số liệu từ facts; mismatch chỉ chứng minh chênh lệch, chưa chứng minh nguyên nhân/phí. Metric không có phải báo thiếu bằng chứng.

`ASSISTANT_CLOUD_ENABLED=false`, `ASSISTANT_REQUEST_BUDGET=0` là mặc định độc lập với ngân sách mapping/planner đang có. Ủy quyền nghiệm thu mới ngày 30/10/2026 cho phép đúng hai HTTP attempts tổng hợp: Assistant một lượt và Planner một lượt, không retry. Assistant chỉ bật trong tiến trình kiểm thử queue hiện có; không sửa env/global/workspace ceiling. Sau thử vẫn OFF/budget0. Transport Assistant giới hạn một attempt, không tự retry khi delivery chưa rõ. Qwen vẫn hoãn, LlamaParse OFF và Argon research only.

Task allowance dùng audit `ASSISTANT_REQUEST_RESERVED` dưới cùng transaction/lock với `GEMINI_REQUEST_RESERVED`; reservation commit trước HTTP. Reclaimed job có reservation chưa rõ delivery bị BLOCKED, không resend. Output chỉ được cache khi deterministic, đã có facts, cùng context/FactSet hash và câu hỏi; cache hit không gửi provider. Trace tách `DETERMINISTIC`/`CACHE` khỏi Gemini, lưu actual provider/model/task/tokens/latency khi có receipt; token hoặc cost thiếu để null. Tests transport thành công/timeout/invalid output là **PASS MOCK**, không là Gemini Assistant live. Facts backend/REST/queue/UI là kiểm chứng local thật.

Thiết kế quyền và output allowlist áp dụng hướng dẫn [OWASP Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html): user/file/tool output là dữ liệu không tin cậy; kiểm quyền/tham số tại tool boundary, không dựa riêng vào prompt. Đây là giới hạn thiết kế và các regression cụ thể, không là tuyên bố miễn nhiễm prompt injection.

Nghiên cứu ngày 29/10/2026: [phân tuyến Flash-Lite/Argon, contracts, ngân sách và giới hạn](AI_MODEL_ROUTING_RESEARCH.md). **Chỉ nghiên cứu**; Argon chưa tích hợp/chưa live, không có runtime env hoặc quota mới. Gemini mặc định và lịch sử request hiện tại được giữ nguyên.

## Qwen

Thông tin được người dùng cập nhật cho dự án:

- Base URL chính thức: `https://ai.inetcloud.vn/memochat/v1`.
- Model ID: `knowledge`.
- Không cần API key, không gửi Authorization giả/rỗng.
- Cấu hình duy nhất qua `QWEN_BASE_URL`, `QWEN_MODEL`, `QWEN_ENABLED`; URL không được nhúng vào frontend.

Ngày 28/10/2026 đã kiểm tra từ host: `GET /models` và `POST /chat/completions` đều trả **HTTP 403, IP address not allowed**. Worker trong Docker cũng nhận HTTP 403 với dữ liệu tổng hợp. Không lưu IP, provider response đầy đủ hoặc request ID nội bộ vào Git.

**LIVE BLOCKED.** Chưa xác minh generation hoặc mapping live. Adapter hiện dùng candidate OpenAI-compatible chat contract; HTTP 403 chưa chứng minh request/response inference này được provider hỗ trợ đầy đủ. Sau khi cấp allowlist phải chạy lại kiểm tra `/models`, inference, JSON và semantic validation; không được đánh dấu PASS chỉ vì `/models` trả 200.

Các task `classify_dataset`, `infer_grain`, `propose_mapping`, `suggest_transformation` dùng hợp đồng `SchemaProposal` thống nhất. Luồng upload gọi `propose_mapping` một lần cho cả bảng, chứa entity/grain/field/transform suggestions, không gọi per-row. Prompt ID/revision `schema-understanding-2`, schema Pydantic, ví dụ UNKNOWN, ràng buộc không tự phê duyệt và evidence IDs rõ ràng. Revision mới nói rõ source_field phải là column ID, không phải tên cột; live response dùng tên cột đã bị từ chối, không tự sửa ID.

Profile/count được tính bằng code. Context gửi tối đa ba mẫu dạng ký tự đã che/cột (tối đa 40 ký tự), type/null/distinct và tên cột; không gửi nguyên file hoặc hàng chục nghìn dòng. Tên cột và mọi dữ liệu nguồn là untrusted data, tách khỏi system instructions. ID/evidence/transforms luôn kiểm tra lại bằng code. Không lưu prompt/raw model output vào logs/AITrace.

Timeout mặc định 45 giây/request. Tối đa hai HTTP attempts cho JSON sai/timeout/lỗi transient; 401/403 và semantic error không retry. Worker giữ job BLOCKED, UI hiển thị nguyên nhân và cho phép mapping thủ công. Trace lưu task/revision/outcome, số HTTP calls, usage nếu có và latency; không bịa token/cost khi provider không trả.

## Routing và memory

Thứ tự: approved compatible template → deterministic shortlist → provider được chọn → review. Mặc định `MAPPING_AI_PROVIDER=GEMINI` theo quyết định mới 28/10/2026. Qwen được hoãn chính thức ở trạng thái `BLOCKED_EXTERNAL_DEPENDENCY — IP allowlist`; giữ adapter/endpoint và không probe lại khi chưa được mở. Gemini vẫn cần workspace policy, key và reserve budget thành công. Không có fallback tự động khi provider lỗi.

Template lookup dùng workspace, source schema signature và business scope. Chữ ký chứa cột/kiểu/identifier flags. Kết quả template được rebind evidence về bảng mới và trở thành proposal phải kiểm tra; không cache UNKNOWN/AMBIGUOUS như approved. Các thay đổi màu/filter/UI không gọi parse hoặc AI lại. Nhấn “Đề xuất lại” tạo job explicit với idempotency key.

## Gemini — tuyến Smart Setup được cấp quyền

Giữ model `gemini-3.5-flash-lite`, đã kiểm tra [model chính thức](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) và [REST generateContent](https://ai.google.dev/api/generate-content) ngày 28/10/2026.

Adapter dùng `generateContent`, `x-goog-api-key`, JSON MIME và cùng validator Pydantic/ngữ nghĩa. Mỗi HTTP attempt cần reserve budget trước khi gửi; thiếu key, cloud OFF hoặc reserve thất bại thì 0 HTTP calls. Có contract tests success, invalid JSON, HTTP errors, missing key, budget, cloud OFF.

Cấu hình mặc định vẫn `ALLOW_EXTERNAL_AI=false`, `EXTERNAL_AI_REQUEST_BUDGET=0`, key rỗng. Theo chỉ định mới, local chọn `MAPPING_AI_PROVIDER=GEMINI`, cấp quyền demo workspace `CLOUD_ALLOWED`/external AI và đặt trần tổng cộng 10 HTTP attempts. LlamaParse không được bật. API không trả key; không tự tìm hoặc tái sử dụng key từ dự án khác.

`reserve_gemini_request` dùng PostgreSQL advisory transaction lock toàn hệ thống, đếm audit `GEMINI_REQUEST_RESERVED`, kiểm tra trần global/workspace rồi commit reservation trước HTTP. Mỗi retry tiêu thụ một lượt; lỗi/worker crash không hoàn lượt vì chưa thể biết provider đã nhận chưa. Trần là lifetime ceiling, không phải quota tự reset theo ngày hoặc mỗi restart. Thay đổi hạn mức cần chủ dự án quyết định; không bịa chi phí tiền tệ. Các tests PostgreSQL kiểm tra worker/trace và concurrent reservations trên hai workspace.

Gateway ghi provider `GEMINI`, tokens từ `usageMetadata`, số HTTP calls và cloud requests; job result không được ghi thành Qwen. Dùng JSON MIME, prompt hợp đồng và cùng Pydantic/semantic checks; không hạ validator nếu live output không đạt. Bằng chứng live gần nhất nằm trong [báo cáo nghiệm thu](IMPLEMENTATION_STATUS.md).

## LlamaParse — contract adapter

Đối chiếu [REST API chính thức](https://developers.llamaindex.ai/llamaparse/parse/guides/api-reference/) ngày 28/10/2026. Adapter dùng `POST /api/v2/parse/upload` multipart `file` + `configuration`, đọc ID top-level khi tạo, poll `GET /api/v2/parse/{id}` với `job.status` nested và expand markdown/items/metadata/usage.

Policy/allowance/key được kiểm tra trước khi mở file hoặc gửi HTTP. Upload một lần; adapter mặc định 10 polls, worker giới hạn tối đa 60 polls có timeout. Polling GET không tạo reservation tài liệu mới. Fail/cancel/response sai/không có trang/timeout đều có error code. Output giữ page numbers, markdown/items/bbox và usage nếu có, luôn `UNVERIFIED_EXTRACTION`.

**PASS LIVE / PARSE VALIDATION PASS / INTEGRATION PASS** trên đúng một PDF và một DOCX tổng hợp, mỗi file 1 trang/3 credits; tổng thực tế **2 trang/6 credits**. API tài khoản trước thử xác nhận 9.980 credits và không pay-as-you-go. Tier `cost_effective` có giá [3 credits/trang](https://developers.llamaindex.ai/llamaparse/general/pricing/); mỗi request đặt `page_ranges.max_pages=2`, không bật layout/form extras. Reservation giữ biên trên 2 trang/6 credits mỗi tài liệu: tối đa 2 docs/4 trang/12 credits, dưới trần 20 đã cho phép. Chỉ hai SHA256 của fixtures được cấp phép trong WorkspacePolicy, giới hạn một PDF/một DOCX, không tự tăng allowance.

POST upload được giữ nguyên theo [REST API chính thức](https://developers.llamaindex.ai/llamaparse/parse/guides/api-reference/). Lỗi live đã xác định: upstream trả ID `pjb-*`, không phải UUID. Adapter đã sửa sang opaque ID có allowlist ký tự, giữ legacy UUID; regression bảo vệ cả POST và resume GET. PDF đã được provider nhận trước khi lỗi format ID được phát hiện; đối chiếu receipt duy nhất theo tên/tier/thời điểm, lấy lại đúng job qua GET và giữ attempt lỗi trong lịch sử. **Không POST lại PDF.** DOCX tạo đúng một job riêng. Không thay giá trị trích xuất để khớp oracle; HTML table và Markdown table được đọc như hai dạng biểu diễn của cùng cells.

Luồng dùng storage/metadata/jobs hiện có: upload → immutable raw → account preflight → durable reservation → POST một lần → lưu job ID ngay → bounded polling → document artifact JSON scoped với file/hash/page/items/bbox/usage. Artifact và preview luôn `UNVERIFIED_EXTRACTION`, không tự sinh canonical. Cache/restart đọc local artifact, không tạo job khác. Job nhận rồi có ID được resume bằng GET; đã reserve mà mất receipt thì fail closed, không tự gửi lại. `GET /api/datasets/{id}/documents` có authorization và checksum; UI chỉ render text/cell strings, không inject provider HTML.

Sau thử đã đóng `ALLOW_CLOUD_PARSING` và quyền workspace; giữ nguyên API key, request ceiling 2, credit ceiling 20, hai reservations và artifacts. Cài mới vẫn cloud OFF/budget 0/không key. `CLOUD_PARSER_CREDIT_BUDGET` là trần bổ sung, không phải usage đã tiêu. Fixture/runtime reports không vào Git.

## Sau khi mở quyền Qwen

Chạy kiểm tra giới hạn bằng dữ liệu tổng hợp. `tools/probe-qwen.py` kiểm tra cả `/models` và mapping inference, ghi kết quả rút gọn không chứa endpoint response/credentials. Khi provider contract xác nhận cần thay adapter, giữ output schema và semantic validators. Sau đó replay tests offline, PostgreSQL và E2E; cập nhật [trạng thái nghiệm thu](IMPLEMENTATION_STATUS.md). Việc dùng Gemini hiện tại là chỉ định explicit của chủ dự án, không phải bằng chứng Qwen đã PASS.

## Gemini Reconciliation Planner

Hợp đồng lịch sử 30/10: task `propose_reconciliation_contract`, prompt khi đó `reconciliation-planning-2`, PlanProposal JSON schema riêng, dùng transport request_typed trên GeminiProvider hiện có. Source catalogue có canonical/schema/approved mapping refs, bounded profile và masked samples; không gửi full table/per-row hoặc raw file. Input PlanningRequest chỉ cần hai nguồn đúng quyền/revisions/provenance, các facts đã xác nhận là optional; không yêu cầu join keys hoặc rule đầy đủ trước AI. Output complete plan phải qua validator đầy đủ; typed PlanningSuggestions cho phép đề xuất keys/metric/cardinality/grain/aggregation trong lúc period/coverage còn thiếu. Không biến gợi ý thành contract. AI không được đổi source IDs/roles/scope/coverage/timezone đã khai báo hoặc tự trả APPROVED. UNKNOWN/NEEDS_REVIEW là hợp lệ, không phải kết quả thực thi.

Bằng chứng lịch sử prompt `reconciliation-planning-1`: **PASS LIVE** trên cặp vận đơn/giao nhận tổng hợp, PROPOSED có plan, job SUCCEEDED và chưa có approval. Đúng **1 HTTP attempt** sau mốc Giai đoạn 1: durable usage **7/10, còn 3**. Mốc kiểm toán trước đây: prompt `reconciliation-planning-2` chỉ PASS MOCK/CONTRACT. Lượt nghiệm thu mới 30/10/2026: **FAIL LIVE**, JSON đọc được nhưng không đạt Pydantic (`AI_INVALID_JSON`); không tạo proposal/contract và không retry. Trần task vẫn tối đa 2 attempts, retry cũng reserve; không reset/tăng global/workspace budgets. Reclaimed job có delivery chưa rõ không tự gửi lại. Provider failure không gọi Qwen. Regression kiểm khác tên/ID cột, không keys trong input, giả field/evidence/currency/basis/cardinality, đổi scope/period, missing requirements, context sai refs và quota hết 0 cloud calls. PG kiểm durable quota/manual fallback và giữ concurrent budget protections. UI vẫn tạo/review rule thủ công khi cloud không khả dụng.

LlamaParse vẫn tạo job OFF, usage lịch sử 2 documents/2 pages/6 credits; không gọi lại trong Giai đoạn 2. Qwen vẫn BLOCKED_EXTERNAL_DEPENDENCY HTTP 403. Gemini mapping prompt/revision không đổi; mọi regression/E2E thông thường chạy MANUAL/mock, không tiêu quota.


## Nghiệm thu Gemini giới hạn — 30/10/2026

Assistant `answer_verified_question` / `assistant-grounded-1`: **PASS LIVE**, một HTTP attempt, `gemini-3.5-flash-lite`, 1.564ms; usage 3.454 input/155 output tokens, thinking/cache không có receipt để xác nhận. FactSet/run/snapshot/citations và 12.75 / 10.00 / delta2.75 VND khớp oracle tổng hợp; model chỉ chọn facts, Backend render số, không thực thi workflow.

Planner `propose_reconciliation_contract` / `reconciliation-planning-2`: **FAIL LIVE**, một HTTP attempt, 2.168ms, 8.163 input/436 output/8.599 total tokens. Response JSON đọc được, mang NEEDS_REVIEW, plan=null và suggestions nhưng Pydantic từ chối. Job BLOCKED; không sửa output/validator hoặc dùng lượt còn lại retry. Trace chỉ giữ mã lỗi và usage, không lưu raw response hay chi tiết trường validation; nguyên nhân ở trường cụ thể **NOT VERIFIED**. Không suy nguyên nhân từ một response hash. Mock/contract PASS không thay thế nghiệm thu live thất bại.

Durable reservations: Gemini7→9/10 (còn1), Assistant0→1, Planner1→2; không reset/tăng ceiling10, không tự phục hồi lượt thất bại. Cả hai dùng Gateway/authorization/queue/reservation và validators hiện có; worker thường dừng tạm để tránh claim race, tiến trình kiểm thử giới hạn max_attempts=1 và chặn HTTP thứ hai. Worker được bật lại; Assistant OFF/budget0, parser OFF ở env/workspace. Qwen không probe, LlamaParse không gọi mới, Argon không tích hợp. Merge/release mới BLOCKED theo gate nghiệm thu; xem [báo cáo](IMPLEMENTATION_STATUS.md).

## Agent-first — hợp đồng tại mốc S ngày 02/11/2026

Một Gateway và PostgreSQL queue hiện có phục vụ `agent-intent-6`, `agent-normalization-3`, `agent-review-1` và `reconciliation-planning-5`. Source defaults `agent_cloud_enabled=false`, `agent_request_budget=0`; demo từng được cấp Agent 30 rồi 33 **bên trong tổng 50 không đổi**, có audit, không reset history. Settings hiện trả Agent cloud không khả dụng do hết quota. Không gọi Qwen, Argon hoặc parser mới.

Reservation global/workspace/task được commit trước HTTP. Mỗi job Agent/Planner tối đa một HTTP attempt; unknown delivery giữ reservation, không resend. Workflow tối đa 12 bước, 6 model calls, 5 tool calls/turn và 3 review OPEN/10 lịch sử. UI gợi ý tường minh có thể bỏ intent call; GET/query/polling/render không gọi model. Không gọi theo từng dòng dữ liệu.

Provider dùng DTO nhỏ với `responseJsonSchema`; server giữ đầy đủ Pydantic, scope/field/semantic/evidence validators. Normalization 3 yêu cầu nullable properties rõ ràng, bỏ `maxItems=40` ở grammar provider nhưng giữ cap 40 và exact-source checks phía backend. Planner tách rule evidence khỏi field evidence và loại optional None khi compose, không tự xác nhận facts thiếu. Safe diagnostics chỉ HTTP status, allowlisted provider status, complexity flag, hash, validation loc/type và counts; không nguyên error body hoặc business values.

Intent 6 phân biệt canonical field ID với approved metric ID, listing với grouping, business key với technical group ID. Paid cần approved payment semantics và literal PAID/TRANSFERRED; COMPLETED không được suy thành PAID. Enum linkage/comparison/exception workflow đúng chiều, không dùng MATCHED giả hoặc ordered status predicates. Biểu đồ toàn bộ trạng thái không được tự thêm bộ lọc PAID. Grouping thiếu aggregation phải hỏi lại. Catalogue/field IDs luôn kiểm lại ở server.

`agent-review-1` chỉ diễn giải câu trả lời đang bind với review/nonce/fingerprint thành draft/plan/intent preview hoặc câu hỏi. Preview xoay nonce, giữ OPEN, không ghi approval. Chỉ quyết định người dùng hợp lệ qua transactional API mới duyệt; stale/deleted conversation/đổi quyền bị chặn. Câu mơ hồ giữ chờ, lỗi provider không biến thành đã phê duyệt.

### Bằng chứng live và giới hạn

- 41 requests mới: 25 VALIDATED, 3 VALIDATED_PROPOSAL; 13 lỗi HTTP/schema/evidence/intent/source/semantics được giữ. Có 38 token receipts, tổng 222.394 tokens; actual billed cost NOT VERIFIED.
- Các ca normalization hai miền, NL review preview, repaired Planner mới, approved-rule reuse, paid/missing/variance query, explanation và export có PASS LIVE có phạm vi. Lịch sử 16 parent workflows: 9 COMPLETED, 5 BLOCKED, 2 WAITING_REVIEW; không báo 100% completion.
- Gold **prompt 5**: 80 measured, intent 68/80, source 53/60, slots 21/34, inferred dispatch 70/80, safe abstention 20/20. D27 rubric đã sửa population, chấm lại replies đã lưu bằng 0 HTTP; không dùng số cũ 22/34.
- Gold dùng 8 batch đầu + 3 known completed failed batches đo lại một lần, 5 successes cached; tổng 11 HTTP. `--repair-known payment-status-grouping` chỉ cho job đã biết HTTP 200/STOP semantic/JSON fail sau regression fix, giữ `repair_of`; không cho timeout/unknown/HTTP error/truncation.
- Prompt 6 chỉ có representative variance LIVE PASS, **full 80-case replay NOT VERIFIED/BLOCKED** do global 50/50. Broad NLP chưa đạt nghiệm thu; không merge/release, không tự sửa quota để chạy tiếp.

Receipts local ngoài Git và bảng đầy đủ ở IMPLEMENTATION_STATUS mục S. Mọi số tiền/chart points do native tools/snapshot tính và kiểm chứng; model không là oracle, không tự approve hoặc sinh SQL/Python.


### Assistant experience — routing contract 7 (02/11/2026)

`agent-intent-7` đưa `RoutingBatch` hữu hạn vào `responseJsonSchema`. Model chọn `source_ref` từ catalogue; server bind project, loại nguồn và ID, kiểm trường trước khi gọi native query. `QueryOperations` dùng chung giữ nguyên public `DataQuery`. Catalogue có tên, project scope, kind, schema, readiness, paid semantics và current run; trường ngoại lệ dùng chung `EXCEPTION_FIELDS` với bộ truy vấn. Tệp trùng tên phải có lựa chọn context/ID; không đoán bằng tên gần giống.

Đối soát trong phạm vi đã duyệt chỉ tham chiếu current `confirmed_run_id` và đúng canonical IDs; server tạo `PlanningRequest.from_plan`, giữ filters, coverage, snapshot, effective dates, role/time basis. Kỳ mới, nguồn mới hoặc facts chưa rõ vẫn review. Không cấp quyền cho model hoặc thay financial contract. Prompt phân biệt chuẩn bị dữ liệu với chạy đối soát, tra cứu thanh toán với chuyển tiền thật, KPI snapshot với query, exact business key với technical group ID. Guard không phải bộ phân loại dựa trên từng câu gold.

Sau chỉ dẫn bổ sung của chủ dự án “cứ gọi Gemini … nếu cần”, được phép phân bổ thêm request cần thiết, giữ nguyên toàn bộ 50 reservations lịch sử. Kế hoạch đầu: 1 canary, 8 batch gold gốc 80 câu, 4 batch biến thể 24 câu; tối đa 13 attempts, mỗi batch tối đa 10 câu, không retry tự động. Benchmark dừng khi transport/schema/semantic gate lỗi; successes cùng prompt/gold/context/subset được cache, không gán cache prompt cũ thành kết quả prompt mới. Chất lượng live chỉ kết luận theo receipts của lượt đo, không từ unit/MOCK.


#### Kết quả sửa và đo tiếp: routing 15

Sau canary và các lượt chẩn đoán có dừng khi lỗi, `agent-intent-15` là revision hiện hành. Bắt buộc khai báo filters/aggregation/group/currency trong routing query; enum field IDs lấy từ catalogue thực. Provider grammar tách thuộc tính theo intent và bỏ array bounds gây HTTP 400; Pydantic/exact-count/source/field/cap checks ở server giữ nguyên. Source refs/nhãn phân biệt canonical với raw, ưu tiên canonical khi có schema đã duyệt. Prompt phân biệt mục tiêu ngay với mục đích tương lai, kể cả khi nguồn đã READY; ví dụ hướng dẫn độc lập, không chép câu gold vào bộ nhận dạng regex.

Gemini LIVE trên code này: **80/80 measured**, intent **79/80 (98,75%)**, nguồn **59/60 (98,33%)**, slots **34/34 (100%)**, inferred dispatch **79/80**, safe/strict abstention **20/20**. Bộ 24 biến thể riêng: intent **24/24**, nguồn **16/16**, slots **10/10**, safe/strict abstention **8/8**. D04 còn hỏi lại khi tên rút gọn, không chọn nguồn sai hoặc tự chạy. Giữ nguyên 80 gold và rubric gốc. Batch router không chứng minh workflow execution/latency từng câu; kiểm tra native workflow và test kỹ thuật được báo riêng ở IMPLEMENTATION_STATUS mục T.

Ceiling demo được chủ dự án cho phép tăng tiếp có audit (không reset 50 requests cũ); default cài mới vẫn cloud OFF/0. Gỡ cap cấu hình cố định 50 của Agent để dùng lifetime ceiling được cấp, tương tự global budget; reservation workspace/global/task và max model/tool calls mỗi workflow vẫn giữ. Chi phí tiền thực phải ghi NOT VERIFIED nếu không có hóa đơn/pricing receipt.


Routing 15 giữ nguyên prompt/schema sau khi sửa thêm guard population: biểu đồ trạng thái nêu cả PAID và UNPAID giữ toàn bộ nhóm, không bị ép thành hai predicate đơn trạng thái; vẫn từ chối self-filter. Regression tái hiện FAIL trước sửa và PASS sau sửa. Toàn bộ 104 replies đã đo được revalidate bằng validator hiện hành trên catalogue PostgreSQL thực, **0 HTTP/reservations mới**; AST prompt/schema/catalogue/compiler giống source 5a7eebc, không gọi đây là một lượt model inference mới. Cache benchmark nay luôn chạy lại semantic validator trước reuse, không bỏ qua guard mới.
