# Nghiên cứu phân tuyến Gemini Flash-Lite và Gemini 4 Argon

## 1. Mục tiêu và trạng thái

Ngày kiểm tra: **29/10/2026**. **RESEARCH COMPLETE — IMPLEMENTATION DEFERRED — LIVE NOT VERIFIED**. Chỉ đọc tài liệu Google và source hiện có; không inference, không thêm dependency/env runtime, không thay mặc định hoặc ngân sách. `[S]` là thông tin nguồn; `[D]` là đề xuất dự án chưa triển khai; `[V]` cần đo/xác minh sau khi được cấp phép. Nghiên cứu này không cấp quyền bắt đầu Giai đoạn 3.

[D] Giữ một Gateway: tác vụ thường dùng Flash-Lite; Argon chỉ nhận đề xuất/suy luận phức tạp được cho phép rõ ràng. Backend tiếp tục tính tiền, matching, verification, KPI và kiểm quyền phê duyệt. Không dùng model khác để chọn model, không multi-agent.

## 2. Nguồn chính thức đã đọc

Tất cả liên kết sau được mở ngày **29/10/2026**; đây là ngày nghiên cứu, không phải ngày phát hành của từng trang.

| Nguồn | Nội dung đối chiếu |
|---|---|
| [S1 — Argon model][s1] | ID, context, modalities, capabilities |
| [S2 — Latest model][s2] | Migration, sampling, thinking/output và timeout |
| [S3 — Thinking][s3] | Levels, hard cutoff, signatures |
| [S4 — Structured output][s4] | JSON Schema subset, Pydantic, Interactions format |
| [S5 — GenerateContent reference][s5] | REST fields, finish reasons, usage, continuation |
| [S6 — Pricing][s6] | Standard, Paid Tier, cache và phụ phí |
| [S7 — Rate limits][s7] | Scope quota, active limits theo project |
| [S8 — Interactions overview][s8] | Endpoint, trạng thái, retention |
| [S9 — Long decode][s9] | Background, streaming, polling |
| [S10 — GenerateContent long decode][s10] | REST/SDK khác nhau, hop, timeout |
| [S11 — Caching][s11] | Implicit cache của Argon |
| [S12 — Flash-Lite model][s12] | Thông số model đang dùng |
| [S13 — Tokens][s13] | Count trước request, usage sau response |
| [S14 — Troubleshooting][s14] | Retry, lỗi quyền/billing, SDK retries |

[V] Chưa kiểm tra Paid Tier/quota Argon của tài khoản, inference, SDK thực chạy, latency, chất lượng hoặc hóa đơn. Không dùng `models.list` làm bằng chứng inference được cấp phép.

## 3. Thông số Argon

| Thuộc tính [S] | Kết quả |
|---|---|
| Stable ID | `gemini-4-argon`, cập nhật model tháng 10/2026 |
| Input/output | Text, image, video, audio, PDF → text |
| Unified context | **1.048.576** tokens chung input + thinking + answer |
| Output | Mặc định 65.536; long decode tối đa phần context còn lại |
| Capabilities | Structured output, function calling, thinking; explicit cache không hỗ trợ |

Nguồn: [model specification][s1]. Paid Tier bắt buộc, không có Free Tier; giá ở §10. Giới hạn mỗi request phụ thuộc API/transport, không suy ra từ model window (§9).

## 4. So sánh với Flash-Lite

| Tiêu chí | Flash-Lite | Argon |
|---|---|---|
| Model | `gemini-3.5-flash-lite` | `gemini-4-argon` |
| Context | Input tối đa 1.048.576 | Unified 1.048.576 |
| Output model | Tối đa 65.536 | 65.536 mặc định; long decode có điều kiện |
| Thinking | minimal mặc định; low/medium/high | medium mặc định; low/medium/high |
| Vai trò đề xuất [D] | Tác vụ thường xuyên, context nhỏ | Suy luận khó, explicit opt-in |
| Bằng chứng dự án | Mapping live lịch sử; planner mới mock | Chưa tích hợp/chưa live |

Thông số Flash-Lite từ [S12][s12], levels từ [S3][s3]. Không cấu hình `off`/`minimal` cho Argon dựa trên khả năng của model khác. Không có benchmark dự án chứng minh Argon tốt hơn hoặc nhanh hơn; context lớn không phải lý do gửi toàn bộ dữ liệu.

## 5. Tác vụ → tuyến đề xuất [D]

| Nhóm | Tuyến khi policy cho phép |
|---|---|
| Dataset classification, schema understanding, mapping | Flash-Lite sau reuse/rules |
| Simple grain và simple reconciliation planning | Flash-Lite |
| Giải thích ngoại lệ đơn giản | Flash-Lite; chức năng AI này chỉ triển khai khi được giao riêng |
| Rule planning có nhiều giả thuyết/grain/metric mâu thuẫn | Argon được chọn rõ ràng, đủ evidence và hai loại ngân sách |
| Refund/settlement hoặc nguyên nhân nhiều bằng chứng | Argon đề xuất giả thuyết, phân biệt UNKNOWN/SUPPORTED; không bịa quy tắc phí |
| KPI liên kỳ/nhiều chiều, Assistant chuyên sâu | Argon tiềm năng; thuộc nhiệm vụ tương lai, chưa có Assistant |
| Exact/composite, 1:N/N:1, Decimal/tolerance, aggregation | Backend deterministic |
| Verifier, KPI, VerifiedRun publication, rule approval | Backend kiểm tra; người có quyền duyệt rule |

Routing dùng task đã đăng ký + điều kiện nghiệp vụ được phê duyệt + lựa chọn người dùng, không suy ra từ free text upload. Giữ thứ tự reuse → rules → provider được chọn → review và trạng thái hoãn Qwen. Flash-Lite hết quota/timeout/JSON lỗi/thiếu evidence **không** cho phép tự gọi Argon. Thiếu scope/coverage/basis vẫn NEEDS_REVIEW. Phân tích nhiều nguồn không đổi `ReconciliationPlan` hai nguồn thành JOIN ba nguồn: chỉ đề xuất từng cặp đúng scope trong contract hiện có.

## 6. Đối chiếu Gateway hiện tại

Đã đọc các module được giao; đây là hiện trạng source được nghiệm thu, không phải thiết kế Argon đã có.

| Module | Hiện trạng và điểm cần chú ý |
|---|---|
| [ai_gateway.py](../backend/studio/ai_gateway.py) | `route_ai_task`, context che mẫu và `GeminiProvider.request_typed`; model duy nhất từ settings, REST/httpx, tối đa 2 attempts, reservation trước mỗi POST; `maxOutputTokens=6000`, `temperature=0`, đọc `parts[0].text` |
| [config.py](../backend/studio/config.py) | `gemini_model` Flash-Lite; timeout mặc định 45s, schema trần 120s; worker lease 300s; chưa có reasoning profile |
| [repository.py](../backend/studio/repository.py) | `reserve_gemini_request`: global advisory lock, lifetime global/workspace attempt caps, AuditRow; caller commit trước gửi |
| [reconciliation_planner.py](../backend/studio/reconciliation_planner.py) | `propose_plan`, `validate_planning_request`, `missing_confirmations`; bảo toàn user-confirmed facts, validate suggestions/plan/evidence |
| [reconciliation_jobs.py](../backend/studio/reconciliation_jobs.py) | Queue/fencing hiện có, planner lifetime cap 2; recovery thấy reservation cũ chặn gửi lại delivery chưa rõ; TraceRow ghi usage |
| [contracts/reconciliation.py](../backend/studio/contracts/reconciliation.py) | `PlanningRequest`, `PlanningSuggestions`, `PlanProposal`; executable plan tách khỏi proposal; Money chặn binary float |
| [verification.py](../backend/studio/verification.py) | Tái dựng membership/partition/sums/evidence độc lập; `calculate_metric_snapshot` kiểm lại verifier, không nhận kết luận AI làm truth |

AuditRow không có JSON payload hoặc số USD; TraceRow có `usage` JSONB nhưng được ghi ở cuối handler. Vì vậy không thể coi trace cuối cùng là durable USD reservation trước HTTP. Job có payload/result JSONB; tất cả nằm trong PostgreSQL hiện có.

## 7. Thay đổi tối thiểu khi được duyệt [D]

1. Mở rộng `request_typed` bằng execution profile bất biến do code chọn: model, thinking, output cap, timeout, retry cap, pricing revision. Callers cũ mặc định Flash-Lite như hiện tại. `select_model_for_task` có thể là hàm nhỏ cạnh `route_ai_task`, không Gateway mới.
2. Giữ `GEMINI_MODEL=gemini-3.5-flash-lite`. Chỉ sau phê duyệt mới thêm `GEMINI_REASONING_MODEL=gemini-4-argon` cùng công tắc **disabled**, request cap **0**, USD cap **0**. Các tên này chỉ là đề xuất, chưa thêm vào config hoặc `.env.example`.
3. Tái sử dụng `build_evidence_context`/catalogue trong `propose_plan`; chỉ thêm builder riêng nếu có nhiệm vụ/evidence contract thật cần nó. Reuse validators hiện có, không tạo `validate_ai_recommendation` trùng nhiệm vụ.
4. Mở rộng reservation hiện tại thành một transaction giữ nguyên Audit attempt + kiểm cap từng model/token/USD. Một bảng ledger nhỏ, migration additive trong **cùng PostgreSQL**, là thay đổi tối thiểu cần thiết cho amounts/settlement (§10). Không thêm database/service/billing framework. Giữ khả năng đọc audit/trace cũ không có model.
5. Thêm model/pricing/attempt receipt vào `TraceRow.usage`; reuse job IDs, fencing, queue. Profile timeout phải đi cùng lease/recovery (§9), không chỉ tăng timeout trong adapter.

Ưu tiên đầu tiên là REST GenerateContent một lượt, typed JSON giới hạn, tools tắt. Chưa cần SDK hay Interactions/long decode; không refactor module đang PASS trước khi được giao tích hợp.

## 8. Request/response contracts dự kiến

[S] GenerateContent: `POST /v1beta/models/{model}:generateContent`, header `x-goog-api-key`; `systemInstruction`, `contents`, `generationConfig`. Response: `candidates[].content.parts`, `finishReason`, `promptFeedback`, `usageMetadata`, `modelVersion`. [API reference][s5].

[D] Fragment cấu hình Argon để contract-test sau này, **không phải request đã chạy**:

```json
{
  "generationConfig": {
    "responseMimeType": "application/json",
    "maxOutputTokens": 32768,
    "thinkingConfig": {"thinkingLevel": "LOW"}
  }
}
```

Task input vẫn là `PlanningRequest` + catalogue/evidence đã scope/redact; system prompt chứa schema `PlanProposal`. Bỏ sampling overrides cho Argon; không áp dụng việc này ngược vào Flash-Lite trong lượt nghiên cứu. Nếu chọn provider structured schema, phải contract-test JSON Schema subset trước; không làm yếu Pydantic để vừa API. [Structured output][s4] hỗ trợ subset JSON Schema và Pydantic; Interactions dùng `response_format: {type: "text", mime_type: "application/json", schema: ...}`.

[D] Pipeline nhận: kiểm HTTP/blocked/finish reason → lấy answer text parts, bỏ thought parts → strict Pydantic → semantic/evidence/confirmed facts → proposal cần review. Không parse JSON dở hoặc lấy mặc định part đầu. Ví dụ output domain hợp lệ, chưa executable:

```json
{
  "status": "NEEDS_REVIEW",
  "plan": null,
  "suggestions": null,
  "missing_requirements": ["Confirm coverage and amount basis"],
  "reasoning": "Insufficient evidence"
}
```

Interactions là phương án khác, không trộn snake_case của nó với camelCase GenerateContent. Endpoint `POST /v1beta/interactions`, GET theo ID; kết quả ở `steps`/`output_text` và `usage`. [Overview][s8]. Nội dung typed không mang quyền approve/run/publish, không gửi raw LLM dict qua API nghiệp vụ.

## 9. Thinking, timeout, output và continuation

[S] Thinking và answer cùng chịu hard output cutoff; incomplete/empty vẫn có thể bị tính phí. Signatures là dữ liệu opaque để giữ ngữ cảnh, không phải evidence tài chính. [Thinking][s3]. Hướng dẫn migration khuyên tăng app cap dưới 32K lên ít nhất 32.768, giảm thinking thay vì cắt cap quá nhỏ, bỏ `temperature/top_p/top_k`; timeout hard prompts ít nhất 15 phút. [Latest model][s2].

**Phân biệt transport:** Direct non-streaming REST có cap **32.768/request**, đặt cao hơn khi chưa có continuation token bị 400; SDK/streaming có hop 65.536. Hướng dẫn riêng khuyên read timeout **20 phút**, server non-streaming đóng sau 10 phút, streaming sau 20 phút. [GenerateContent long decode][s10]. Không lấy timeout 300.000ms trong ví dụ Managed Agent làm mặc định Argon trực tiếp.

[D] Vì app đang timeout 45s/trần 120s và lease 300s, **không thể đổi model string là xong**. Phương án cần duyệt: reasoning-only read timeout 1200s, total deadline hữu hạn lớn hơn read timeout, lease reasoning job lớn hơn total deadline cộng margin; Flash-Lite giữ profile cũ. Dùng queue/202 hiện có, không giữ browser request chờ model. Phải test mất lease/crash/recovery; nếu không bảo đảm thì tuyến Argon BLOCKED. Số deadline/margin cuối cùng là `[V]`, chưa sửa global lease hoặc runtime.

[D] Initial cap 32.768/LOW là điểm bắt đầu đánh giá, không bảo đảm model sẽ hoàn tất. MAX_TOKENS/CONTINUATION/empty không được tự nâng cap hoặc gọi lại. Người dùng nhận trạng thái rõ ràng, reservation giữ để đối soát; không publish plan dở.

[S] GenerateContent CONTINUATION trả `continuationToken`; request tiếp giữ nguyên `contents`, cumulative `maxOutputTokens` tăng hoặc bỏ giới hạn. [Reference][s5]. Interactions long decode dùng `background=true` và output>65.536, server tiếp các hops; cần nối text của mọi `model_output`, lưu ID/poll trạng thái và usage. [Long decode][s9].

[D] **Long decode DEFERRED.** Mỗi hop tương lai cần attempt/USD reservation, checkpoint/fencing và chống đếm usage lặp; không bỏ cap để tiếp vô hạn. Retry/continuation là hai hành vi khác nhau. Không làm theo ví dụ resend/higher cap nếu chưa có quyền chi phí. SDK có thể tự tiếp/retry bên trong nên không dùng trước khi kiểm soát được mọi HTTP attempt.

## 10. Hai ngân sách và usage [D]

**Attempt ceiling:** giữ lifetime global/workspace hiện có (tại mốc nghiên cứu 29/10/2026: **7/10**, còn3; số hiện tại xem báo cáo nghiệm thu), planner cap2 (đã1 tại mốc nghiên cứu); thêm cap Argon mặc định0, không reset audit khi restart/đổi model. Mọi POST retry/hop là attempt mới. **Token/USD ceiling:** độc lập, Argon mặc định0; phải đồng thời còn cả hai loại ngân sách mới được gửi.

[S] Rate limits theo **project**, không theo key; gồm RPM/TPM/RPD, reset RPD theo Pacific. Google còn giới hạn spend rolling; active limits xem AI Studio. [Rate limits][s7]. `[V]` Không có con số Standard RPM/TPM của tài khoản này; không lấy Batch enqueued-token limits làm quota Standard. App budget không thay provider quota.

Giá **USD/1M tokens, Standard**, kiểm tra ngày 29/10/2026:

| Model/thời gian | Input | Cached input | Output gồm thinking |
|---|---:|---:|---:|
| Argon đến 30/11/2026 | 2 | 0,10 | 10 |
| Argon từ 01/12/2026 | 4 | 0,20 | 20 |
| Flash-Lite hiện tại | 0,30 | 0,03 | 2,50 |

[Pricing][s6]: Argon không Free Tier; Batch/Flex/Priority là tier khác, không dùng giá của chúng cho ví dụ Standard. Search/Maps có allowance rồi phụ phí $14/1.000 queries; tool instructions/declarations cũng có thể bill tokens. Thiết kế ban đầu tắt tools, không có phụ phí grounding trong ví dụ.

Ví dụ tự tính bằng Decimal, **không phải usage/hóa đơn thực**: 10.000 input + 2.000 answer + 8.000 thinking, không cache/tools/tax/FX:

| Model/rate | Phép tính USD | Tổng |
|---|---|---:|
| Flash-Lite | 0,01×0,30 + 0,01×2,50 | **0,028** |
| Argon ưu đãi | 0,01×2 + 0,01×10 | **0,12** |
| Argon từ 01/12 | 0,01×4 + 0,01×20 | **0,24** |

Cùng token counts chỉ để so giá, không chứng minh cùng chất lượng. Với input bound 10.000/output cap 32.768, reserve tối đa **$0,34768** ở giá ưu đãi hoặc **$0,69536** từ 01/12, chưa gồm khoản ngoài ví dụ. Không dùng output answer 2.000 để quên 8.000 thinking. Khi request có thể vượt ngày đổi giá, reserve theo rate cao hơn, lưu pricing revision/effective date; không đoán timezone billing.

[S] `count_tokens` đếm input trước gửi; usage Interactions có `total_input_tokens`, `total_output_tokens`, `total_thought_tokens`, `total_cached_tokens`, `total_tool_use_tokens`, `total_tokens`. Ví dụ SDK của Google yêu cầu version **mới hơn 2.0.0**. [Tokens][s13]. GenerateContent dùng `promptTokenCount`, `cachedContentTokenCount`, `candidatesTokenCount`, `thoughtsTokenCount`, `totalTokenCount`. [Reference][s5].

[D] Chỉ đếm trên đúng serialized context/schema/model; local heuristic không là hard bound. Nếu không có count được xác minh hoặc input upper bound bảo thủ thì chặn request. Count endpoint cũng gửi dữ liệu ra cloud, cần policy riêng; không gọi trong nghiên cứu này. Không thêm SDK: REST/httpx hiện có đủ cho phương án đầu. Nếu sau này chọn SDK, pin version tương thích và tắt/kiểm soát auto-retries/continuations, kiểm thực tế trước khi ghi PASS.

Ledger dự kiến tối thiểu: unique attempt_id, workspace/job/task/model, pricing revision/service tier, input bound/output cap, Decimal reserved USD, receipt/usage, trạng thái RESERVED/SETTLED/DELIVERY_UNKNOWN. Đây là trạng thái ledger đề xuất, không thêm vào enum nghiệp vụ. Transaction dưới lock hiện có kiểm tổng spent+outstanding ở global/workspace/model, ghi Audit+ledger rồi commit trước HTTP. Không giữ DB transaction suốt thời gian model nghĩ.

Sau response lưu receipt và settle chênh lệch USD theo usage đã đối chiếu; không hoàn attempt slot. Timeout/đứt mạng/crash thiếu receipt giữ **DELIVERY_UNKNOWN**, không hoàn tiền giả định bằng 0. Worker recovery không POST lại; operator đối soát receipt trước. Trace legacy thiếu tokens/cost vẫn UNKNOWN. Chống hai worker settlement cùng attempt bằng unique key/row lock; ledger phải sống qua recreate. Với GenerateContent, tính riêng input uncached/cached và answer+thoughts; không cộng `totalTokenCount` thêm một lần. Interactions chuẩn hóa tương tự, kiểm semantics bằng fixtures trước dùng cho ledger; không double-count usage cumulative qua polls/hops.

[S] Argon chỉ implicit cache, ngưỡng input 4.096; không explicit cache API. [Caching][s11]. [D] Reserve theo input uncached; chỉ giảm actual cost khi receipt xác nhận cache hit. Không nhồi prompt để đạt ngưỡng, không tạo cache infrastructure mới.

## 11. Privacy, security và retry

[S] Interactions mặc định `store=true`; Paid retention 55 ngày, có lựa chọn 7/14/28/55. `store=false` không dùng background hoặc previous_interaction_id. [Overview][s8]. [D] Ban đầu dùng one-shot context tối thiểu; không coi Paid Tier là zero retention. Muốn background phải duyệt retention/data classification và cách xóa/lưu ID; không gửi business files/raw rows hay tự bật tools.

Reuse scope checks/masking/prompt-injection boundaries. Evidence từ đúng workspace/project/canonical revision; raw cell không điều khiển model routing, paths hoặc permissions. Không lưu keys, raw prompts/thoughts/outputs vào Git/logs; ledger chỉ metadata/usage cần thiết. Model không có SQL/Python, write tool hoặc quyền phê duyệt. Multi-turn sau này phải bảo toàn opaque signatures, kiểm scope và redaction trước resend.

[S] Google khuyên backoff+jitter cho transient errors; không retry 400/402/403. SDK có auto-retry transient mặc định. [Troubleshooting][s14]. [D] Argon ban đầu **0 automatic retries**; delivery chưa rõ không resend. Nếu sau này cho 1 retry, phải phân loại lỗi, reservation mới, explicit remaining cap và deadline; không blind retry JSON/thiếu semantic evidence hoặc fallback model đắt hơn. Thiếu Paid Tier trả lỗi cấu hình/quyền rõ ràng, không đổi key/quota tự động.

## 12. Acceptance dự kiến, chưa chạy Argon

| Lớp kiểm thử tương lai | Điều kiện cần chứng minh |
|---|---|
| Mock routing | Disabled/request 0/USD 0/exhausted/policy OFF → 0 HTTP; không unauthorized fallback; model chọn đúng task |
| Contract | Typed output, schema subset, unknown fields/IDs/evidence, đổi confirmed facts, incomplete coverage → reject/review; không auto-approve |
| Transport | Thought part trước text, empty/blocked/MAX_TOKENS/CONTINUATION, HTTP 402/403/429/5xx, timeout, usage thiếu/cumulative; no blind resend |
| PostgreSQL integration | Concurrent reserve/settle, duplicate receipt, crash sau reserve/trước response, lease expiry, workspace isolation, migration compatibility; lịch sử 7/10 không reset |
| Regression | Flash-Lite mapping/planner golden không giảm; matcher/Decimal/verifier/snapshot bit-for-bit cho inputs/approved rules cũ; T01–T35 vẫn PASS |
| E2E/security | Chọn tuyến explicit, review/approval riêng, trạng thái/quota chính xác, không raw data/log secrets; restart giữ reservations |
| LIVE gated | Chủ dự án cho phép, paid access+budget+redacted synthetic evidence; cap nhỏ xác nhận trước, receipt/model/tokens/USD/latency ghi thật |

[D] Benchmark cùng bounded context và oracle độc lập: chia train/validation/holdout; không sửa oracle theo model. Đo field/evidence validity, approved-fact preservation, proposal correctness trên supported cases, abstention/review, timeout, latency p50/p95, input/answer/thinking/cache và USD theo model/level. So Flash-Lite với Argon LOW/MEDIUM/HIGH trên cùng ca; chọn level thấp nhất đạt tiêu chí chủ dự án duyệt. Quyết định chất lượng/ngân sách phải trước holdout. Số mẫu, ngưỡng và lợi ích chi phí là `[V]`; không tuyên bố 98%/99,5% đã đạt. Không tổ chức live benchmark bằng quota 3 còn lại khi chưa được giao.

## 13. Rủi ro và giới hạn

- Context/output lớn, thinking/continuation làm tăng chi phí và latency; cap lớn là reservation upper bound, không phải dự báo usage.
- API/model/docs có thể đổi; khác biệt REST 32K/SDK 64K, casing/schema, timeout/lease và auto-retry dễ làm sai contract/budget.
- Output JSON đúng vẫn có thể sai nghiệp vụ; nhiều model đồng thuận không thay independent verifier hoặc bằng chứng.
- Quyền Paid Tier, Standard limits, SDK version thực chạy, quality/latency/cost Argon đều **NOT VERIFIED**. Không có inference Argon để nghiệm thu.
- Giữ lịch sử Flash-Lite 7/10, Qwen HTTP 403 deferred, LlamaParse creation OFF; không gán dữ liệu lịch sử này cho Argon.

## 14. Quyết định cần duyệt và bước tiếp theo

Chủ dự án cần chốt task allowlist/điều kiện chọn Argon; Paid Tier/data retention; request cap và token/USD caps; Standard rate/pricing revision; thinking/output profile; timeout/lease/recovery; phạm vi ledger migration và tiêu chí benchmark/live allowance. Chưa có các quyết định này thì Argon tiếp tục disabled 0/0.

Thứ tự đề xuất khi có prompt triển khai riêng: (1) chốt contracts/fixtures và caps; (2) mở rộng Gateway/reservation nhỏ nhất, offline/mock/PG regression; (3) transport/security/E2E không cloud; (4) live synthetic canary có giới hạn được duyệt; (5) đối soát usage rồi mới đánh giá benchmark/routing. Long decode và Assistant cần phạm vi riêng. **Dừng ở tài liệu nghiên cứu trong nhiệm vụ hiện tại.**

[s1]: https://ai.google.dev/gemini-api/docs/models/gemini-4-argon
[s2]: https://ai.google.dev/gemini-api/docs/latest-model
[s3]: https://ai.google.dev/gemini-api/docs/thinking
[s4]: https://ai.google.dev/gemini-api/docs/structured-output
[s5]: https://ai.google.dev/api/generate-content
[s6]: https://ai.google.dev/gemini-api/docs/pricing
[s7]: https://ai.google.dev/gemini-api/docs/rate-limits
[s8]: https://ai.google.dev/gemini-api/docs/interactions-overview
[s9]: https://ai.google.dev/gemini-api/docs/long-decode
[s10]: https://ai.google.dev/gemini-api/docs/generate-content/long-decode
[s11]: https://ai.google.dev/gemini-api/docs/caching
[s12]: https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite
[s13]: https://ai.google.dev/gemini-api/docs/tokens
[s14]: https://ai.google.dev/gemini-api/docs/troubleshooting
