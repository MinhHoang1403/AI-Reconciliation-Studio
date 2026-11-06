# AI Gateway và provider contracts

## Review từng phần dùng chung Gemini/Qwen — 06/11/2026

Theo chỉ dẫn mới, Gemini là lựa chọn chính khi gọi được, Qwen `qwen3:8b` là lựa chọn phụ. Cấu hình local đã chuyển về Gemini; lựa chọn cá nhân và model đã bind vào job được giữ. Vòng kiểm tra mới ngày06/11 nhận sáu HTTP200 (hai probe có schema và một yêu cầu tự nhiên qua UI với router/ba đề xuất). Kết quả503 ngày05/11 bên dưới là lịch sử, không còn là kết luận duy nhất về hiện trạng; sáu thành công cũng chưa chứng minh ổn định dài hạn hoặc đạt full live gold.

`agent-review-3` dùng cùng schema/validators cho cả hai provider. Mapping chỉ trả thay đổi typed theo source_field/property/value cùng câu hỏi còn thiếu; Backend giữ cột/target/table ID, hợp nhất những giá trị hợp lệ và giữ giá trị cũ khi cập nhật sai. Hai giá trị mâu thuẫn cho cùng thuộc tính không được chọn theo thứ tự. Kiểm kiểu strict, ngày/IANA và draft/profile được thực hiện độc lập; bản xem trước có câu hỏi không bị biến thành AI_INVALID_REVIEW. Review đối soát trả PlanningRequest từng phần và suggestions riêng, không phải approval. Backend giữ facts chưa được thay, kiểm catalogue/source và chỉ dựng preview plan khi đủ thông tin.

Mỗi giá trị hợp nhất được validate, không dùng model_copy(update=...) như một bước kiểm kiểu; xem [Pydantic model_copy](https://docs.pydantic.dev/latest/api/base_model/#pydantic.BaseModel.model_copy). Không ghi raw provider output vào trace; review_shape chỉ lưu số trường, số câu hỏi và cờ loại preview. Lỗi reply trước được giải quyết khi có reply hợp lệ và không còn bước FAILED/BLOCKED khác; tin nhắn lỗi và job lịch sử giữ nguyên.

A/B LIVE cùng review tổng hợp: grammar `changes.maxItems=80` trả400 INVALID_ARGUMENT, chỉ bỏ thuộc tính này khỏi envelope trả200 (1.914ms). Giữ ràng buộc <=80 ở MappingEdits trên Backend và test80/81; không thay semantic validation. Không kết luận mọi lỗi400 đều có nguyên nhân này.

Audit Qwen nhận HTTP200 nhưng bị AI_INVALID_INTENT ở lượt router tự nhiên. Phát hiện Gateway local đang nhận public RoutingBatch rộng, trong khi Gemini đã nhận grammar chia theo từng intent; public DTO cho phép các optional tool fields cùng xuất hiện trước kiểm tra ngữ nghĩa. `agent-intent-33` truyền cùng grammar theo intent cho cả hai: chuẩn bị ánh xạ không được kèm query/reconciliation. Không thêm grammar khớp câu hỏi mẫu để thay suy luận. Trace routing_shape chỉ lưu enum intent/cờ tool/số nguồn và câu hỏi; không lưu raw output. Chưa có raw output của lượt lỗi cũ nên không quy kết chính xác thuộc tính nào model đã trộn. MOCK transport xác minh schema tương đương; LIVE sau sửa được báo riêng.

Trần an toàn mặc định của workflow là8model calls, vẫn trong hard ceiling8 có sẵn: một router + ba proposal + ba phản hồi chủ động cần7calls. Không tăng timeout, không gọi per-row, không reset ledger và không tự retry unknown delivery. Mốc6calls bên dưới mô tả cấu hình lịch sử.

## Smart Mapping local theo profile và ngữ nghĩa — 05/11/2026

Theo yêu cầu khôi phục Smart Mapping, Qwen 8B nhận một envelope ngắn cho từng bảng. Backend tạo đủ trường của `NormalizationDraft` từ profile toàn cột. Header và số liệu đọc được cùng hỗ trợ gợi ý kiểu ngày/tiền, còn mã định danh giữ chuỗi. Qwen chỉ gợi ý loại bảng, ý nghĩa một dòng, ứng viên khóa và nghĩa gross/net/fee. Schema đầu ra giới hạn tham chiếu trong danh sách cột thực. Bộ kiểm tra từ chối tham chiếu sai hoặc trùng. Múi giờ, nghĩa tiền còn mơ hồ, đơn vị và các điều kiện nghiệp vụ tiếp tục chờ xác nhận qua preflight và thẻ duyệt.

Heuristic kiểu tiền `[D]` cần header phù hợp và ít nhất 80% giá trị không rỗng đọc được như số, đồng thời không phải ứng viên mã định danh. Header ngày cần có quan sát định dạng ngày. Đây là gợi ý bản nháp, không phải ngưỡng chất lượng đã hiệu chỉnh; normalization vẫn kiểm từng giá trị, không bỏ dòng còn lại để đạt tỷ lệ này.

Tên tệp và sheet là ngữ cảnh có giới hạn, được gửi như dữ liệu không đáng tin. Nếu grain còn unknown, Backend bỏ ứng viên khóa. Cột tiền tên chung `amount` hoặc `total` vẫn cần nghĩa được xác nhận. Công cụ không chuyển trạng thái dự kiến/hoàn thành thành đã thanh toán. Các đề xuất của nhiều bảng vẫn thuộc cùng một workflow và có quyết định riêng cho từng nguồn.

Lệnh chuẩn hóa rõ ràng đi cùng tệp đính kèm có thể dùng resolver hữu hạn trên Backend khi chọn Qwen. Resolver kiểm đầy đủ câu và danh sách tệp gắn vào tin nhắn. Câu phủ định, scope thiếu hoặc câu chứa thêm hành động ngoài chuẩn hóa đi qua router. Frontend lưu danh sách tệp vào payload cùng mã yêu cầu. Khi phản hồi một lần gửi chưa rõ, bản ghi payload cũ tiếp tục xác định model và phạm vi đã gửi.

`ASSISTANT_DEFAULT_MODEL` chọn mặc định của bộ chọn khi người dùng chưa có lựa chọn cá nhân. Cài mới mặc định Gemini. Giá trị này không sửa các job đã gửi. Trạng thái kết nối và trạng thái nghiệm thu tác vụ được trình bày riêng trong báo cáo.

Local hiện hành đã đặt `QWEN_8B` sau lượt tạo đủ ba đề xuất LIVE và duyệt/chuẩn hóa qua UI. Model vẫn mang trạng thái **Chưa kiểm chứng** cho phạm vi AI tổng thể: grain/khóa cần người dùng sửa và chưa có full live gold cho Planner/NLP. Không nâng trạng thái hoặc bật cloud fallback chỉ từ ba JSON hợp lệ. Bằng chứng hiện hành tại IMPLEMENTATION_STATUS mục AH, thay số đo thời điểm AG.

Vòng chẩn đoán khóa mới dùng REST `v1beta ...:generateContent` qua httpx 0.28.1, không dùng SDK Google; không có SDK retry ngầm. Đối chiếu [GenerateContent](https://ai.google.dev/api/generate-content), [Structured Outputs](https://ai.google.dev/gemini-api/docs/structured-output), [mã lỗi](https://ai.google.dev/gemini-api/docs/api-errors), [quota theo project](https://ai.google.dev/gemini-api/docs/rate-limits), [token receipts](https://ai.google.dev/gemini-api/docs/tokens), [billing](https://ai.google.dev/gemini-api/docs/billing) và [SDK chính thức](https://github.com/googleapis/python-genai). Không áp dụng ví dụ của API khác vào request đang chạy. Khóa mới đã nhận HTTP 200, nhưng cả JSON nhỏ lẫn bước mapping thật vẫn có HTTP 503. Không có bằng chứng 401/403/429 trong vòng này, không có quyền xem quota/billing project Google để xác minh nguyên nhân sâu hơn. Dừng Gemini sau năm attempts, giữ toàn bộ ledger. Với Ollama, dùng [Chat API](https://docs.ollama.com/api/chat) và metadata load/prefill/decode; thời gian token đầu không đo trực tiếp khi phản hồi không streaming.

## Chọn Gemini hoặc Qwen trong AI Assistant

AI Assistant gửi `model_choice` cùng tin nhắn hoặc câu trả lời cho thẻ xác nhận. Backend kiểm quyền, lưu lựa chọn theo job, rồi chuyển tiếp lựa chọn đó cho các bước chuẩn bị và đề xuất đối soát thuộc cùng luồng. Đổi lựa chọn trong ô Chat áp dụng cho tin nhắn sau. Job cũ đọc được khi thiếu trường này và tiếp tục theo tuyến Gemini hiện có. Các tác vụ đọc xác định và quy tắc đã duyệt vẫn dùng dữ kiện của Backend.

`GET /api/assistant/models` cần phiên hợp lệ. Với Qwen, endpoint đọc danh sách model đã cài. Với Gemini, trạng thái dựa trên quyền, cấu hình và trace đã ghi. Mở bộ chọn không yêu cầu inference. Qwen local dùng API native `/api/chat` với `format`, kiểm kết thúc phản hồi, đọc `message.content` rồi dùng cùng Pydantic và validator nghiệp vụ. Các trạng thái lỗi và lượt gọi được ghi riêng cho từng provider. Qwen có dấu vết chặn gửi trùng riêng và không tiêu thụ lượt Gemini. [Ollama Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs).

Ollama chạy trên Windows. Trong Docker, đặt `OLLAMA_URL=http://host.docker.internal:11434` và `OLLAMA_CHOICE=QWEN_8B` khi cần thử tag `qwen3:8b`. Cấu hình để trống mặc định. Backend chỉ chấp nhận các địa chỉ local đã định và chỉ gọi tag tương ứng đã cài. Giới hạn thử hiện tại là context 8.192 và timeout 90 giây cho mỗi lần suy luận. Lựa chọn Qwen dùng cho thử nghiệm local và có thể hiện **Chưa kiểm chứng** hoặc **Không khả dụng** tùy lần đo.

Gemini ghi HTTP status, trạng thái Google theo danh sách cho phép, request ID nếu có, kích thước body, hash schema, giới hạn đầu ra và thời gian từng attempt. Các tác vụ Agent giữ một attempt mỗi job. Với tuyến cũ cho phép tối đa hai attempts, chỉ thử lại lỗi kết nối trước khi gửi hoặc lỗi HTTP tạm thời đã nhận, với thời gian chờ và jitter. HTTP 429, dữ liệu không hợp lệ và delivery chưa xác định dừng lượt. [Hướng dẫn xử lý lỗi Gemini](https://ai.google.dev/gemini-api/docs/troubleshooting).

**Quyết định hiện hành04/11/2026:** chủ dự án bỏ trần request nội bộ cho local được cấp quyền. Config `EXTERNAL_AI_REQUEST_BUDGET`, `AGENT_REQUEST_BUDGET`, `PLANNER_REQUEST_BUDGET`, `ASSISTANT_REQUEST_BUDGET` nhận `unlimited` thành typed `null`; chỉ cấu hình như vậy khi `LOCAL_DEMO_ACCESS=true`. WorkspacePolicy `external_request_budget=null` là bỏ trần riêng workspace, không bật permission. Global/workspace/task finite cũ vẫn tương thích; local hiện có được chuyển rõ ràng sang null sau backup/audit, không để ceiling210/193/30/20 chặn ngầm. Mặc định cài mới cloudOFF/0, không tự cấp quyền cho workspace khác. Không có `CLOUD_MAX_REQUESTS`/`CLOUD_BUDGET_USD` trong source hiện có; không tạo quota system song song. Knowledge không có trần request tích lũy nội bộ, giữ cấu hình/quyền/kết nối thật.

Reservation vẫn commit trước HTTP dưới lock, giữ nguyên ledger cũ và ownership. `remaining=null` chỉ khi mọi trần được bỏ,0vẫn có nghĩa không còn quyền/lượt; Settings người dùng không trình bày cấu hình/ledger. Provider429 dừng tự retry và báo rate limit; read/write timeout hay mất response không resend mù quáng, finite connect/server retries và structural validation vẫn bounded. Agent/model/tool/step/payload caps là an toàn vòng thực thi, không phải lifetime quota. Token/cost thiếu receipt để null; không bịa giá. Parser2documents/credits/SHA không đổi. Các đoạn quota/trạng thái provider dưới đây là lịch sử tại mốc ghi, không ghi đè quyền mới; kết quả live hiện hành phải đo lại.

**Phạm vi 03/11/2026:** `agent-intent-26` bổ sung metadata metric đã duyệt, aliases duy nhất có trong filename, previous query cùng hội thoại, pending clarification và vị trí trong trang kết quả. Source-specific provider grammar không cho metric của verified run vào query canonical/raw; không ép array bounds gây HTTP400, nhưng Pydantic/caps ở server giữ nguyên. Router không tự tính tiền hoặc phê duyệt. Clarification reply dùng cùng router/catalogue thay parser preview thiếu nguồn; edits mapping/rule vẫn `agent-review-1`, chờ người dùng duyệt. Unique metric được bind vào approved run contract; nhiều metric hỏi lựa chọn do server tạo. Toàn-run sum delta/absolute_variance chuyển sang đọc snapshot sau semantic validation; phân tích có filter/group giữ typed query. Yêu cầu tự duyệt/bỏ tiền tệ bị policy từ chối; chọn nguồn gần giống không được reuse run. Fast path liệt kê chỉ nhận từ vựng đọc đơn giản và một alias có bằng chứng duy nhất, không nhận filter/tiền/kỳ hoặc nhiều bảng. Đây là heuristic[D] có regression, không bộ hiểu mọi câu tiếng Việt.

Chủ dự án sau6attempts yêu cầu tiếp tục sửa và tăng lượt. Có audit cho Agent163→183→193 và global/workspace200→210, không reset history/đổi model/key/provider.49attempts mới có49trace:43VALIDATED,1AI_INVALID_JSON,2QUERY_SEMANTICS_REQUIRED,2INPUT_AMBIGUOUS,1HTTP400. VALIDATED chỉ là transport/schema/semantics theo contract, không đồng nghĩa câu nào cũng đúng intent hoặc workflow hoàn thành.48token receipts tổng726.021tokens; tiền thực NOT VERIFIED. Cuối inference203/210global,184/193Agent,11/30Planner,2/20legacy; remaining là min global/workspace/task, không cộng các số task. Qwen/parser không gọi mới; cài mới OFF/0 và parser2/2 giữ nguyên. LIVE/MOCK/CACHED đọc riêng tại IMPLEMENTATION_STATUS.

**Nhiệm vụ nghiệm thu demo đang thực hiện — 02/11/2026:** chủ dự án cho phép tăng allowance và để toàn bộ công cụ đã triển khai bật cho việc tự thử. Global/workspace ceiling200, Agent163, Planner30, legacy Assistant20; không reset ledger hoặc đổi model/key. Agent/Assistant/parser flags bật trong demo; parser vẫn có allowance và approved-file gate riêng. Không gán kết nối VERIFIED chỉ từ flags. Các thông số110/120, Planner10/10 và yêu cầu OFF bên dưới là mốc lịch sử, đã được chỉ dẫn mới thay thế cho nhiệm vụ này. Lượt UAT của Codex gắn với project/job/trace riêng; lượt người dùng giữ nguyên trong tổng ledger, không được tính thành phép kiểm thử của Codex.

Kết nối Qwen mới đã PASS LIVE: `/models`200 và mapping inference synthetic qua strict JSON/semantic checks từ cả host Windows và backend Docker; giữ model `knowledge`, không Authorization giả, không thay mapping provider Gemini. Lỗi403 ở phần lịch sử không phải trạng thái phép probe mới. Gemini routing hiện `agent-intent-17`; source slots đối soát giới hạn vào canonical IDs trong context, không đổi validator/financial contracts. Legacy Assistant có deterministic guard trước cloud cho explicit SQL/Python/secret/bypass requests; đây là guard hữu hạn và typed tools vẫn bảo vệ mọi hành động.

Phép nghiệm thu mới41Gemini attempts có job/trace refs, gồm failures và một legacy regression phát hiện được khi cloudON. Usage154/200 là ảnh chụp tại audit, còn46tổng; Agent135/163, Planner11/30, Assistant2/20. Cài đặt đọc ledger mới nhất, không dùng số này như quota còn cố định. Billed cost chưa xác minh. Parser flagsON nhưng allowance2/2 đã dùng và chỉ hai SHA lịch sử: tài liệu mới chưa được mở allowance; PDF/DOCX cũ đọc lại PASS CACHED,0providerHTTP. Argon chưa tích hợp. Chi tiết live/mock/cached và sai số NLP ở [báo cáo mục V](IMPLEMENTATION_STATUS.md#v-nghiệm-thu-demo-và-khôi-phục-môi-trường--02112026).

**Hiện hành trước nhiệm vụ hoàn thiện UI/Settings 02/11/2026:** Gemini `gemini-3.5-flash-lite`, lifetime global/demo workspace **110/120, còn 10**, Agent 93/103, Planner 10/10; giữ toàn bộ lịch sử. Routing 15 đã đạt gate có giới hạn và main đã phát hành theo [báo cáo mục T](IMPLEMENTATION_STATUS.md#t-ai-assistant-experience--nlp-quality-finalization). Mốc S 50/50/BLOCKED và các kết quả ngày 28–30/10 bên dưới là lịch sử. Nhiệm vụ tiếp theo không cho tăng trần/reset ledger hoặc dùng cloud để test giao diện. Qwen hoãn, parser jobs mới OFF, Argon chưa tích hợp.

Settings phân biệt cấu hình, quyền workspace, quyền tác vụ, lượt còn lại và kết nối model. `cloud_live_status=NOT VERIFIED` không được suy thành AI sẵn sàng từ `/api/ready` hoặc key đã cấu hình. Mở Settings, đổi kích thước và đọc giới hạn không gọi provider.

Planner gửi DTO nhỏ `PlannerReply` bằng GenerateContent `responseJsonSchema` (serialization schema, Decimal chuỗi); server giữ source/scope đã xác nhận, ghép domain plan rồi chạy lại validator. `allowed_rule_evidence_ids` tách canonical/schema/artifact khỏi field-level evidence trong catalogue. Model chọn field evidence không đúng tầng bị từ chối, không lọc/sửa IDs để qua gate. Optional không gửi hoặc explicit null dùng `exclude_unset` và `exclude_none` khi ghép domain defaults; false/0/filters tường minh vẫn giữ. Missing confirmations không được tự điền thành approval. Mỗi Planner job1HTTP attempt; trace hash/status/loc/type không chứa input/secret. Google schema subset/complexity có giới hạn; UUID enum trong nested evidence array đã bị400 ở live, không dùng constraint đó để ép provider.

**Trạng thái LIVE04/11/2026:** đã gặp Gemini HTTP429, dừng gọi mới; đây là giới hạn provider, các ceilings nội bộ vẫn null. Nghiệm thu AI cuối còn BLOCKED, không lấy receipts bản cũ thay coverage bản hiện hành. Chi tiết/usage tại IMPLEMENTATION_STATUS mụcAC.

## Routing và usage hiện hành — 04/11/2026

`agent-intent-31` giữ source/date/coverage/snapshot/effective facts đã nêu qua DTO sang Planner, chặn việc dùng múi giờ thay ý nghĩa ngày. Facts thiếu vẫn cần người dùng bổ sung; model không tự xác nhận độ đầy đủ hoặc phê duyệt quy tắc. Truy vấn tổng chênh lệch toàn run, kể cả đi cùng count, dùng MetricSnapshot đã verified; phân tích có filter/group vẫn là typed query. Tổng quan run đang mở không tự trở thành lọc ngoại lệ OPEN. Các revision và hạn mức trong những mục lịch sử bên dưới không thay cấu hình hiện hành ở đầu tài liệu.

Routing31 nhắc rõ optional currency_field chỉ thuộc catalogue của đúng nguồn; danh sách/đếm EXCEPTIONS không có trường tiền tệ. Unknown fields vẫn bị từ chối, không tự bỏ validation.

Gateway ghi model, từng HTTP attempt, status, tokens và latency khi provider trả được. Read/write timeout hoặc delivery chưa rõ dừng, không gửi lại mù; connect failure/known5xx mới retry có giới hạn và backoff.429 dừng bằng mã rate-limit riêng; unlimited nội bộ không thay quota thật. Usage của lỗi Assistant được giữ trong trace, không trả nội dung nhạy cảm ra UI.

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

Phân loại lỗi timeout tham chiếu [HTTPX exceptions](https://www.python-httpx.org/exceptions/);429/quota nhà cung cấp tham chiếu [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits). Không suy ReadTimeout thành chưa gửi request.
