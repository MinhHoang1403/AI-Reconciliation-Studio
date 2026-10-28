# AI Gateway và provider contracts

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

Thứ tự: approved compatible template → deterministic shortlist → provider được chọn → review. Mặc định `MAPPING_AI_PROVIDER=QWEN`. Chủ dự án ngày 28/10/2026 đã chỉ định tạm chọn `GEMINI` khi Qwen bị chặn; Qwen sẽ được mở sau. Gemini vẫn cần workspace policy, key và reserve budget thành công. Không có fallback cloud tự động khi provider lỗi.

Template lookup dùng workspace, source schema signature và business scope. Chữ ký chứa cột/kiểu/identifier flags. Kết quả template được rebind evidence về bảng mới và trở thành proposal phải kiểm tra; không cache UNKNOWN/AMBIGUOUS như approved. Các thay đổi màu/filter/UI không gọi parse hoặc AI lại. Nhấn “Đề xuất lại” tạo job explicit với idempotency key.

## Gemini — tuyến Smart Setup được cấp quyền

Giữ model `gemini-3.5-flash-lite`, đã kiểm tra [model chính thức](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) và [REST generateContent](https://ai.google.dev/api/generate-content) ngày 28/10/2026.

Adapter dùng `generateContent`, `x-goog-api-key`, JSON MIME và cùng validator Pydantic/ngữ nghĩa. Mỗi HTTP attempt cần reserve budget trước khi gửi; thiếu key, cloud OFF hoặc reserve thất bại thì 0 HTTP calls. Có contract tests success, invalid JSON, HTTP errors, missing key, budget, cloud OFF.

Cấu hình mặc định vẫn `ALLOW_EXTERNAL_AI=false`, `EXTERNAL_AI_REQUEST_BUDGET=0`, key rỗng. Theo chỉ định mới, local chọn `MAPPING_AI_PROVIDER=GEMINI`, cấp quyền demo workspace `CLOUD_ALLOWED`/external AI và đặt trần tổng cộng 10 HTTP attempts. LlamaParse không được bật. API không trả key; không tự tìm hoặc tái sử dụng key từ dự án khác.

`reserve_gemini_request` dùng PostgreSQL advisory transaction lock toàn hệ thống, đếm audit `GEMINI_REQUEST_RESERVED`, kiểm tra trần global/workspace rồi commit reservation trước HTTP. Mỗi retry tiêu thụ một lượt; lỗi/worker crash không hoàn lượt vì chưa thể biết provider đã nhận chưa. Trần là lifetime ceiling, không phải quota tự reset theo ngày hoặc mỗi restart. Thay đổi hạn mức cần chủ dự án quyết định; không bịa chi phí tiền tệ. Các tests PostgreSQL kiểm tra worker/trace và concurrent reservations trên hai workspace.

Gateway ghi provider `GEMINI`, tokens từ `usageMetadata`, số HTTP calls và cloud requests; job result không được ghi thành Qwen. Dùng JSON MIME, prompt hợp đồng và cùng Pydantic/semantic checks; không hạ validator nếu live output không đạt. Bằng chứng live gần nhất nằm trong [báo cáo nghiệm thu](IMPLEMENTATION_STATUS.md).

## LlamaParse — contract adapter

Đối chiếu [REST API chính thức](https://developers.llamaindex.ai/llamaparse/parse/guides/api-reference/) ngày 28/10/2026. Adapter dùng `POST /api/v2/parse/upload` multipart `file` + `configuration`, đọc ID top-level khi tạo, poll `GET /api/v2/parse/{id}` với `job.status` nested và expand markdown/items/metadata/usage.

Policy/allowance/key được kiểm tra trước khi mở file hoặc gửi HTTP. Upload một lần; tối đa 10 polls có timeout. Fail/cancel/response sai/không có trang/timeout đều có error code. Output giữ page numbers, markdown/items và usage nếu có, luôn `UNVERIFIED_EXTRACTION`.

**MOCK CONTRACT PASS / LIVE NOT VERIFIED.** Không gọi LlamaParse thật. PDF/DOCX chưa có end-to-end cloud pipeline trong UI; upload báo rõ policy/adapter-only. Không tự chuyển tài liệu OCR thành canonical giao dịch. `ALLOW_CLOUD_PARSING=false`, `CLOUD_PARSER_REQUEST_BUDGET=0`, key rỗng.

## Sau khi mở quyền Qwen

Chạy kiểm tra giới hạn bằng dữ liệu tổng hợp. `tools/probe-qwen.py` kiểm tra cả `/models` và mapping inference, ghi kết quả rút gọn không chứa endpoint response/credentials. Khi provider contract xác nhận cần thay adapter, giữ output schema và semantic validators. Sau đó replay tests offline, PostgreSQL và E2E; cập nhật [trạng thái nghiệm thu](IMPLEMENTATION_STATUS.md). Việc dùng Gemini hiện tại là chỉ định explicit của chủ dự án, không phải bằng chứng Qwen đã PASS.
