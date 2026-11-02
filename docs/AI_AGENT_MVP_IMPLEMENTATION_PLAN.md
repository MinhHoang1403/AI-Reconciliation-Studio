# AI RECONCILIATION STUDIO — KẾ HOẠCH CẢI TẠO MVP AI AGENT-FIRST

> **Tài liệu thiết kế và triển khai dành cho Codex**  
> **Ngày chốt nghiên cứu:** 01/11/2026  
> **Đường dẫn đề xuất trong dự án:** `docs/AI_AGENT_MVP_IMPLEMENTATION_PLAN.md`  
> **Trạng thái:** `IMPLEMENTED — ACCEPTANCE BLOCKED` (02/11/2026: UI/technical gates đã kiểm chứng; broad NLP quality chưa đạt, Gemini 50/50 còn 0; chưa merge/release)
> **Mục tiêu:** Upload dữ liệu → ra lệnh bằng tiếng Việt → AI tự thực hiện việc an toàn → hỏi đúng phần mơ hồ → trả bảng, biểu đồ, kết quả và bằng chứng.  
> **Phạm vi:** MVP demo local; KHÔNG xây hệ thống kế toán doanh nghiệp, KHÔNG viết lại engine đang hoạt động.

---

## 0. Cách sử dụng tài liệu này

1. Đây là **kế hoạch cải tạo sản phẩm mới**, không phải báo cáo đã hoàn thành hay một lệnh tự động merge/deploy. Codex phải đọc cùng `Rules.md`, `AGENTS.md`, `docs/PROJECT_PLAN.md`, `docs/DATA_CONTRACTS.md`, `docs/ARCHITECTURE.md`, `docs/AI_INTEGRATION.md`, `docs/TESTING_GUIDE.md`, `docs/IMPLEMENTATION_STATUS.md` trước khi bắt đầu.
2. Khi có xung đột giữa tài liệu này và quyết định trong kế hoạch ba giai đoạn cũ, **không âm thầm sửa hoặc xóa lịch sử**: lập bảng thay đổi yêu cầu, ghi lý do và chỉ cập nhật tài liệu chuẩn khi chủ dự án giao thực hiện. Ví dụ: kế hoạch cũ ưu tiên các bước mapping/approval trên màn hình; kế hoạch mới **giữ approval ở Backend nhưng đưa vào hội thoại, và tự động hóa các bước đã có ủy quyền**.
3. **Sự thật từ repository** được nêu tại mục 2; **thiết kế đề xuất chưa tồn tại** được ghi rõ bằng nhãn `ĐỀ XUẤT`, các tên class/endpoint mới là tên gợi ý, không phải API đã có.
4. Không triển khai đồng thời tất cả rồi mới kiểm thử. Dùng **một đợt triển khai có các cổng kiểm chứng**, dừng ở mỗi cổng khi có FAIL thuộc phạm vi.
5. Không tự merge vào `main`, không xóa dữ liệu, không dọn Docker đại trà, không gọi AI ngoài ngân sách đã xác minh. Việc release là cổng riêng và phải được chủ dự án cho phép trong nhiệm vụ triển khai tương ứng.
6. **Mục tiêu “AI Agent thật”** được định nghĩa bằng khả năng nhận mục tiêu, chọn công cụ, thực thi nhiều bước, tạm dừng/chờ quyết định, phục hồi trạng thái, tiếp tục và trả kết quả có kiểm chứng; không phải chỉ gọi Gemini để tạo một đoạn văn.

## 1. Product vision và giới hạn MVP

### 1.1. Tuyên bố sản phẩm

**AI Reconciliation Studio là không gian làm việc đối soát dữ liệu được điều khiển bằng hội thoại.** Người dùng tải CSV/XLSX, giao việc như “chuẩn hóa”, “đối soát”, “lọc giao dịch”, “giải thích chênh lệch”, “vẽ biểu đồ” bằng tiếng Việt. AI hiểu yêu cầu, Backend điều phối công cụ được phép để làm việc; phần mềm tự động xử lý những trường hợp đã đủ điều kiện và chỉ hỏi khi cần người dùng quyết định ngữ nghĩa/rủi ro. Mọi kết quả tài chính phải truy ngược được về dữ liệu và quy tắc đã kiểm chứng.

**Người dùng demo:** một người cần so sánh 2–5 bộ dữ liệu sổ cái, chứng từ, đơn hàng, thanh toán; không bắt buộc biết SQL, mapping schema, grain, cardinality hay thao tác từng màn hình.

### 1.2. Bốn năng lực MUST của MVP

| Năng lực | Ví dụ yêu cầu bằng tiếng Việt | Kết quả | Trường hợp phải hỏi |
|---|---|---|---|
| Chuẩn bị / chuẩn hóa | “Chuẩn hóa 2 file mới tải lên giúp tôi” | Bản chuẩn hóa, tóm tắt phép biến đổi, lỗi và chứng cứ | Ý nghĩa khóa/tiền/ngày, biến đổi có thể đổi ID, extraction mơ hồ |
| Đối soát | “Đối soát sổ cái với chứng từ tháng 10” | VerifiedRun, tóm tắt khớp/thiếu/lệch, ngoại lệ, biểu đồ | Rule mới, kỳ/timezone/coverage/basis chưa rõ, hai nguồn không tương thích |
| Tra cứu dữ liệu | “Liệt kê các giao dịch đã chuyển tiền ở file A” | Bảng lọc có phân trang, tổng số bản ghi, nguồn và điều kiện thực thi | “Đã chuyển tiền” không có cột/trạng thái chứng minh được |
| Phân tích & giải thích | “Vì sao giao dịch này có ở cả A và B nhưng không khớp?” | Số hai phía, khóa, trạng thái, lý do *kiểm chứng được*, bằng chứng; giới hạn kết luận | Không có bằng chứng cho nguyên nhân nghiệp vụ |

### 1.3. NON-GOALS

- ERP, ghi bút toán, sửa raw document, chuyển tiền, đồng bộ ngân hàng, theo dõi lịch thanh toán tự động, đa cấp phê duyệt doanh nghiệp.
- Multi-agent, LangGraph/CrewAI/AutoGen mới, vector database mới, Redis/Kafka/Celery, nền tảng RAG tổng quát, Text-to-SQL không kiểm soát, LLM được chạy Python/SQL/shell tùy ý.
- Phục vụ PDF/DOCX scan phức tạp hoàn toàn tự động; giữ adapter hiện có nhưng đường demo chuẩn là **CSV/XLSX**.
- “Tự động” bằng cách giả lập click UI, auto-approve mapping/rule tùy ý hoặc đổi các công thức tài chính.
- SLA production, HA, audit chứng nhận pháp lý, off-host disaster recovery; chưa thuộc MVP.

### 1.4. Definition of success từ góc nhìn người dùng

1. Mở ứng dụng thấy ngay nơi **đính kèm file và giao việc**; không cần tự mở trang Dữ liệu/Mapping/Đối soát để bắt đầu.
2. Một lệnh chat có thể điều phối nhiều bước nghiệp vụ liên tiếp; các bước rõ ràng được chạy tự động.
3. Nếu mơ hồ, hệ thống **hỏi một nhóm câu hỏi tối thiểu**, giải thích vì sao phải hỏi và sau trả lời tự tiếp tục, không bắt người dùng làm lại từ đầu.
4. Kết quả hiện ngay trong chat: bảng, biểu đồ, KPI, lỗi, link mở nguồn, tải file; các trang chuyên dụng chỉ là chế độ chi tiết.
5. AI trả lời “chưa đủ dữ liệu”, “chưa hỗ trợ” hoặc “cần xác nhận” thay vì đoán số, đặt tên trường hoặc bịa nguyên nhân.
6. Refresh, chuyển trang, mất mạng, worker crash hoặc gửi lại không nhân đôi job, không mất approval/đầu ra đã ghi.

---

## 2. Baseline có căn cứ — KHÔNG coi là kết quả nghiệm thu mới

**Tham chiếu repository đã đọc ngày 01/11/2026:** `MinhHoang1403/AI-Reconciliation-Studio`, branch `codex/assistant-automation`, HEAD `8044b47e79b664acafc0457de75a7312b7c83b7d`; `main` `eefdd4441d7f7ef52b08e7d35d3c68894de191dd`. Cần **fetch/verify lại trước khi Codex thay đổi**. Báo cáo mục R ghi runtime candidate source `446d031`, chưa merge Stage 3.

**Các số đã được Codex báo cáo ngày 30/10/2026, không phải kết quả vừa chạy trong tài liệu:** Backend/PostgreSQL **191 PASS**, Playwright **59 PASS**, Docker Compose **4/4 healthy**, local persistence/recovery/backup/restore đạt. AI Assistant **PASS LIVE một trường hợp**; AI Reconciliation Planner **FAIL LIVE** với `AI_INVALID_JSON` do Pydantic từ chối response JSON có thể parse, field cụ thể chưa xác định. Gemini ledger ở báo cáo: **9/10 used**, Planner task cap 2/2. Người dùng **đã cấp phép nâng tổng trần thành 50 attempts trong hội thoại sau đó**, nhưng tài liệu/report chưa xác nhận config/ledger đã áp dụng. **Tuyệt đối không mặc định còn 41 attempts runtime**; kiểm tra lại global/workspace/task ceilings, giữ history trước khi cấp request mới. Qwen `knowledge` lịch sử HTTP 403; LlamaParse new jobs OFF; Gemini 4 Argon research only.

### 2.1. Công nghệ đang dùng — giữ và tái sử dụng

| Lớp | Công nghệ / source | Định hướng |
|---|---|---|
| UI | React, TypeScript, Vite, `frontend/src/App.tsx`, `AssistantStudio.tsx`, `navigation.ts`, `styles.css`; ECharts 6, Lucide, TanStack Table, Radix Dialog | Giữ App Shell & theme, mở rộng UI chat |
| API & validation | Python FastAPI, Pydantic, Pydantic Settings, SQLAlchemy | Giữ; bổ sung DTO/tools typed |
| Storage | PostgreSQL 18 image đang cấu hình trong `compose.yaml`; artifacts files/Parquet; SQLAlchemy models `backend/studio/database.py` | Giữ schema hiện có, migration additive tối thiểu |
| Processing | Polars, DuckDB đang được dùng cho truy vấn evidence/Parquet, Decimal pipeline | Giữ; làm typed query/aggregate có kiểm soát |
| Worker | `backend/studio/worker.py`, PostgreSQL jobs, lease/fencing/SKIP LOCKED, one worker process | Giữ; bổ sung điều phối công việc cấp cao |
| AI | `backend/studio/ai_gateway.py`, Gemini Flash-Lite theo policy, strict JSON/Pydantic/semantic validation | Giữ; structured tool intent/Planner contract repair |
| Reconciliation | `backend/studio/reconciliation_api.py`, engine/verifier/MetricSnapshot/evidence | Giữ bất biến công thức và status |
| Infra | `compose.yaml`: `postgres`, `backend`, `worker`, `frontend`; `127.0.0.1:18180`, volumes `postgres_data` và `artifacts` | Giữ 1 Compose; bảo vệ dữ liệu và image rollback |
| Test | pytest/PG integration, Playwright, Ruff, mypy, ESLint, TypeScript/build | Duy trì, mở rộng golden NL/tool-flow/security tests |

Không thêm dependency mới nếu thư viện đang có đáp ứng. Không nâng đồng loạt versions trong nhiệm vụ này.

### 2.2. Công cụ thực tế đang có

- Read-only Assistant tools tại `backend/studio/assistant_tools.py`: `list_datasets`, `get_run_summary`, `get_metric_breakdown`, `list_exceptions`, `get_match_evidence`, `get_rule`, `get_workflow_status`.
- `backend/studio/assistant.py`: `deterministic_answer`, `workflow_proposal`, `validate_answer`, `answer_question`; current live AI chỉ được chọn facts/claim codes. `backend/studio/assistant_jobs.py` đang nhận diện một số workflow bằng **từ khóa**, chưa điều phối các hành động write.
- Existing endpoints (đã kiểm mã nguồn): `POST /api/projects`, `POST /api/datasets/uploads` (cần project_id), `POST /api/tables/{table_id}/mapping-proposals`, `POST /api/mappings/{mapping_id}/approve`, `POST /api/datasets/{dataset_id}/normalize`, `POST /api/reconciliation-plans/ai`, `POST /api/reconciliation-contracts/{plan_id}/approve`, `POST /api/reconciliation-runs`, các GET reports/matches/cases/metrics/export.
- Mapping approval tạo revision và đánh dấu canonical cũ stale; normalization chỉ nhận active **APPROVED** mapping. Reconciliation template reuse hiện tạo **PROPOSED** và yêu cầu xác nhận lại kỳ/coverage/rule; chưa thể coi là quyền tự chạy.
- `frontend/src/App.tsx` hiện cấm vào Assistant nếu thiếu project; file upload diễn ra trong modal, xong điều hướng đến trang Dữ liệu. `frontend/src/AssistantStudio.tsx` là trang riêng đã có lịch sử/draft/context, nhưng giao diện chat chưa phải trang mặc định hoặc entrypoint upload-first.

### 2.3. Technical debt / blockers cần xử lý theo thứ tự

1. **Planner LIVE typed output thất bại:** chẩn đoán schema/provider/Pydantic, thêm diagnostic field locations, sửa bằng offline fixtures và live gate có ngân sách — KHÔNG bỏ validator. Đây là blocker nếu Agent dựa vào Planner cho rule mới.
2. **AI chỉ đọc:** thiếu typed action-planning, orchestration, workflow persistence và tool permission để thực hiện normalize/reconcile.
3. **Upload cần project:** cần safe bootstrap project với trạng thái business scope chưa xác nhận; không giả định scope nghiệp vụ bằng nhãn mặc định.
4. **Bằng chứng/query giới hạn:** Assistant đang tập trung VerifiedRun; chưa có tra cứu linh hoạt dữ liệu nguồn/canonical, tables/charts trong chat.
5. **Approval UI rời rạc:** cần review-by-exception và tiếp tục workflow sau quyết định, nhưng không được lách approval.

---

## 3. Thiết kế UX — Giữ nguyên khung giao diện hiện tại

### 3.1. Bố cục MUST KEEP

- Sidebar trái màu sáng, brand Reconciliation Studio, thẻ workspace, thanh điều hướng.
- Topbar trên với breadcrumb, kết nối, tài khoản.
- Vùng main content bên phải, bộ màu xanh `#2563EB`, background sáng, cards trắng, typography/các component sẵn có.
- Responsive và keyboard/focus của phiên bản đã cải thiện; không dựng UI framework/thiết kế lại branding.

### 3.2. Điều hướng mới — chỉ tổ chức lại

| Vị trí | Trước | Sau (đề xuất) | Ghi chú |
|---|---|---|---|
| Trang khi mở | Tổng quan | **Trợ lý AI** | Nếu URL chỉ định trang hợp lệ, tôn trọng deep link |
| Sidebar mục đầu | Tổng quan | **Trợ lý AI** | Luôn mở được khi session ready; không cần project để xem empty chat |
| Sidebar mục 2 | Dữ liệu | Dữ liệu | Chi tiết, kiểm tra nguồn khi cần |
| Các mục nghiệp vụ | Đối soát, Ngoại lệ, Báo cáo | Nhóm **Kết quả & công cụ** (có thể thu gọn) | Giữ các trang và URL; không gộp engine/source |
| Cài đặt | Cuối sidebar | Cuối sidebar | Giữ an toàn quyền/AI policy |
| Tổng quan cũ | Trang chính | Không còn landing chính; có thể giữ route cũ hoặc chuyển nội dung hữu ích vào “Kết quả” | Không phá deep links/tests, chọn phương án ít sửa nhất |

Tránh sidebar lồng quá nhiều tầng. Khi người dùng mở deep link Ngoại lệ/Run, navigation phải giữ context. Không được hiển thị số của project cũ trong quá trình chuyển project.

### 3.3. Empty state Chat khi chưa có project

**Heading:** `Bạn muốn làm gì với dữ liệu hôm nay?`  
**Subtext:** `Tải CSV/Excel lên hoặc mô tả yêu cầu bằng tiếng Việt.`  
**Composer:** 1 vùng nhập bo tròn, nút `+` / đính kèm và nút gửi; file chips tên/kích cỡ, nút bỏ file.  
**Gợi ý:** `Chuẩn hóa dữ liệu`, `Đối soát hai file`, `Tìm giao dịch`, `Phân tích kết quả`.

- Chat mở ngay khi app `ready`, dù chưa có project. Không tự hiện thông báo “Chọn hoặc tạo dự án” chiếm cả trang.
- Đính kèm CSV/XLSX → hệ thống tạo project mặc định *an toàn* nếu chưa chọn project, rồi upload/parse; chỉ sau đó gắn conversation/project đúng scope.
- Nếu chỉ nhắn “đối soát giúp tôi” mà chưa có dữ liệu: hỏi người dùng tải file, KHÔNG tạo giả run/project vô nghĩa.
- Nếu người dùng muốn chọn project hiện có, hiển thị control nhỏ trong header chat. Các file mới gắn vào selected project; không tự trộn file qua hai project.
- Khi parser/upload lỗi phải thông báo lý do, không tạo conversation giả có dữ liệu chưa lưu.

### 3.4. Chat khi có dữ liệu

- Cột lịch sử hội thoại sẵn có (thu gọn trên màn hình nhỏ), transcript chính, composer ở cuối vùng chat.
- Trên transcript: chip `Dự án • 2 file • Đang xử lý...` hoặc `Kết quả đối soát • Đã xác minh` theo status thật, không lộ UUID mặc định.
- Một tin nhắn từ AI có thể chứa *nhiều block có cấu trúc*, không chỉ prose: `progress`, `review_request`, `dataset_summary`, `table`, `chart`, `reconciliation_summary`, `exception_list`, `citation`, `download`.
- Frontend render theo DTO typed, không parse Markdown do LLM tự chế thành dữ liệu nghiệp vụ.
- Khi có câu hỏi cần xác nhận: thẻ ngắn, lựa chọn, vài dòng minh họa/đường dẫn chứng cứ, nút `Xác nhận và tiếp tục`; cho phép trả lời bằng ngôn ngữ tự nhiên nhưng cần parse và ràng buộc vào review request cụ thể.
- Nếu công việc chạy lâu: trạng thái thật từ worker, không tạo phần trăm giả. Polling có backoff hợp lý, chống stale responses.
- Đảm bảo nút `Dừng` chỉ dừng các bước **chưa chạy**; không hứa hoàn tác kết quả đã công bố. Nút `Tiếp tục` dùng workflow đã lưu.
- Không ép người dùng đọc JSON, IDs, revision, transaction trace; cho xem trong “Chi tiết kỹ thuật” khi cần.

### 3.5. Bảng/biểu đồ trong chat

- Bảng chỉ lấy trang dữ liệu có giới hạn; hiển thị `N kết quả` với trạng thái đã/đang tải đầy đủ, lọc/sort, nút mở trang đầy đủ.
- Biểu đồ dùng **ECharts hiện có**, chỉ nhận dữ liệu có nguồn do Backend tính; show tên metric, đơn vị, kỳ, denominator (nếu có) và nguồn run/dataset.
- Không dùng chart khi metric không có định nghĩa hoặc population không đủ; thay bằng thông báo thiếu chứng cứ.
- `PARTIAL`, `UNKNOWN`, `OUT_OF_SCOPE`, `PENDING_SETTLEMENT` không được gom bừa vào “lệch”.
- Trên mobile: lịch sử drawer, transcript một cột, composer không bị bàn phím che, bảng cuộn riêng, review request không vượt viewport.

### 3.6. Hiển thị trạng thái kết nối/demo

- Phân biệt `API connected`, `LOCAL_DEMO_NOT_VERIFIED`, `AI disabled/quota`, `job running`. Không dùng đèn xanh “đã kết nối” để ngầm báo đã sẵn sàng AI.
- Cảnh báo proof local không được ẩn theo cách bỏ auth/CSRF/Origin; thể hiện ngắn gọn, có link hướng dẫn chạy `tools/start.ps1` nếu phù hợp. Khi chưa verify, chặn write theo backend như hiện tại.
- Không hiển thị API key/secret/quota internals ở vùng chat; có thể có trạng thái `AI đang khả dụng` hoặc `Chế độ xử lý an toàn` liên kết tới Cài đặt.

---

## 4. Kiến trúc mục tiêu — Một Agent Orchestrator nhỏ, không multi-agent

### 4.1. Sơ đồ luồng

```text
React App Shell / Chat / Upload
     |
     v
FastAPI: Auth + Chat Message + Attachment + Workflow API
     |
     v
Intent/Tool Plan (Gemini Flash-Lite hoặc deterministic router)
     |
     v
Pydantic DTO + Scope/Permission/Policy/Schema Checks
     |
     v
Durable Agent Workflow Orchestrator (PostgreSQL state)
     |        |                          |
     |        +--> WAITING_REVIEW ------> Human decision API
     |                                    | validate/revision/fence
     v                                    v
Existing worker/jobs: parse -> mapping -> normalize -> plan -> approve -> run -> verify -> export
     |
     v
Read-only facts/query + evidence/citations + typed view blocks
     |
     v
Chat response: completed / partial / blocked / awaiting review
```

AI **không trực tiếp thực thi SQL/code** và không được quyết định quyền. Tool executor/server guard là cổng cuối. Không tạo một model process chạy liên tục; LLM chỉ được gọi ở những điểm ra quyết định cần suy luận ngôn ngữ.

### 4.2. Thành phần mới được đề xuất

Tên module là gợi ý, Codex phải đối chiếu trách nhiệm tránh trùng:

| Module đề xuất | Vai trò | Tái sử dụng |
|---|---|---|
| `backend/studio/agent_intents.py` | Parse/validate intent và tham số; deterministic fast path; Gemini typed routing | AI Gateway, Pydantic |
| `backend/studio/agent_workflows.py` | State machine điều phối nhiều job và resume | JobRow/Worker, conversations, audit |
| `backend/studio/agent_policy.py` | Quy tắc khi nào auto execute hoặc cần review; **code deterministic**, không do prompt quyết định | Approved Mapping/Rules, workspace permissions |
| `backend/studio/agent_tools.py` | Registry typed read/write actions, scope, idempotency, action budget | Existing services/API logic |
| `backend/studio/data_query.py` | Typed filter/group/sum trên nguồn/canonical/verified outputs | Polars/DuckDB/Parquet, API scope |
| `backend/studio/contracts/agent.py` | DTO intents, workflows, review, result blocks, tool arguments | Base Contract Pydantic |
| `frontend/src/AgentConversation.tsx` (hoặc mở rộng `AssistantStudio.tsx`) | Chat-first composer, cards, progress, review | Current Assistant UI/history |
| `frontend/src/AgentResultBlocks.tsx` | Typed table/chart/evidence rendering | ECharts, TanStack Table, current reports |

**Không bắt buộc tạo đúng số lượng file này.** Nếu existing module phù hợp, mở rộng có giới hạn thay vì tạo wrapper và abstraction không cần thiết. Không đưa toàn bộ logic Agent vào `App.tsx`.

### 4.3. Những gì tuyệt đối không thay đổi

- Raw uploads bất biến, source SHA, lineage, zero-prefix identifiers.
- Mapping Revision + `ApprovedTransformRule` + validation; không âm thầm sửa meaning.
- Normalization transformation DSL allowlist, Decimal/null/error semantics.
- Reconciliation Matcher, matching cardinality, independent Verifier, immutable VerifiedRun/MetricSnapshot.
- Approvals, audit, role/scope checks, CSRF/local-demo proof.
- Durable Job Queue lease/fencing/SKIP LOCKED, idempotency.
- Existing accepted historical migrations/artifacts/reports/backup.

**Nguyên tắc:** AI chỉ *điều phối* qua các business services đã có. Những thay đổi mới nên tập trung ở orchestration, approved reuse policy, query, UI.

---

## 5. Hợp đồng Agent và cơ chế hành động

### 5.1. Intent taxonomy hữu hạn

| Intent | Ví dụ | Loại | Điều kiện |
|---|---|---|---|
| `EXPLORE_DATA` | “File này có những cột nào?” | Read | Project/file đã tồn tại |
| `PREPARE_NORMALIZATION` | “Chuẩn hóa file A” | Workflow | File/profile hợp lệ |
| `RECONCILE_DATASETS` | “So khớp A và B trong tháng 10” | Workflow | Nguồn READY và rule/scope |
| `QUERY_DATA` | “Liệt kê đơn đã chuyển tiền” | Read | Semantics đã xác nhận |
| `EXPLAIN_RESULT` | “Vì sao dòng này lệch?” | Read | Run/case/evidence hợp lệ |
| `SUMMARIZE_RESULTS` | “Tỷ lệ khớp thế nào?” | Read | Snapshot đã xác minh |
| `CREATE_VISUALIZATION` | “Vẽ biểu đồ theo loại sai lệch” | Read | Metric và population xác minh |
| `CONTINUE_REVIEW` | “Cột này là tiền đã thanh toán” | Review decision | Có active review item khớp context |
| `EXPORT_RESULT` | “Xuất kết quả này ra Excel” | Workflow | VerifiedRun có quyền xuất |
| `CLARIFY` | Câu thiếu nguồn, kỳ, nghĩa | No action | Hỏi tối thiểu |
| `UNSUPPORTED` | Sửa sổ gốc, chuyển tiền, tax filing | No action | Giải thích giới hạn |

Không dùng regex keyword làm **cơ chế điều phối chính**. Có thể dùng deterministic router cho lệnh rõ và cache; với ngôn ngữ đa dạng, Gemini xuất typed intent; Backend xác thực. Model phải được phép từ chối/UNKNOWN. Chat không có model live thì hỗ trợ các command rõ ràng và nói đúng giới hạn, không giả vờ hiểu tự nhiên hoàn chỉnh.

### 5.2. DTO gợi ý — KHÔNG phải schema hiện đã tồn tại

```python
from typing import Literal
from pydantic import BaseModel, Field

class AgentIntent(BaseModel):
    intent: Literal[
        "EXPLORE_DATA", "PREPARE_NORMALIZATION", "RECONCILE_DATASETS",
        "QUERY_DATA", "EXPLAIN_RESULT", "SUMMARIZE_RESULTS",
        "CREATE_VISUALIZATION", "CONTINUE_REVIEW", "EXPORT_RESULT",
        "CLARIFY", "UNSUPPORTED",
    ]
    dataset_ids: list[str] = Field(default_factory=list, max_length=5)
    run_id: str | None = None
    user_requested_period: str | None = None  # Raw phrase until normalized and confirmed
    unresolved_questions: list[str] = Field(default_factory=list, max_length=5)

class AgentAction(BaseModel):
    tool_name: str                  # server-enforced allowlist
    arguments: dict                # validate against tool-specific DTO on server
    target_resource_ids: list[str]
    requires_review: bool
```

Đây là **pseudocode hướng hợp đồng**, không được đưa `str` + `dict` trực tiếp vào executor production. Mỗi action phải có Pydantic type chuyên biệt, allowlist operation, max length/range, schema migration/revision rõ ràng. Model không được tự sinh/điền `approved_by`, `approved_at`, `workspace_id`, `actor_id`, `is_admin`, `storage_path`, `sql`, `python`, `file_path`, `authorization`.

### 5.3. Quy trình gọi công cụ

1. Server xác minh session, role, workspace, project và message context.
2. Intent parser chọn intent; nếu cần Gemini, gửi prompt bounded context, field IDs/catalogue, không gửi toàn raw rows.
3. Pydantic parse + semantic validation về scope, IDs, phép biến đổi, kỳ, loại tiền, quyền.
4. Orchestrator kiểm trạng thái công việc, chính sách thực thi, dependencies, quota/cost, idempotency key.
5. Với tool `read`: thực thi ngay, giới hạn dữ liệu/timeouts; trả typed result.
6. Với tool `write` ít rủi ro **đã có quyền và điều kiện**: enqueue job theo stable key, không gọi HTTP nội bộ tự cấp token.
7. Với quyết định mới làm đổi ngữ nghĩa: tạo review request, tạm dừng; không auto-approve do model tự đặt cờ.
8. Sau mỗi tool: kiểm kết quả/next state; có thể tiếp tục deterministic steps; nếu cần quyết định ngôn ngữ mới, gọi Gemini trong hạn mức.
9. Khi job xong: xây result blocks từ canonical/VerifiedRun/MetricSnapshot; render kết quả có bằng chứng.
10. Lưu state/log/audit; không leak dữ liệu vào user-visible logs hoặc provider traces.

### 5.4. Bounded execution

Thiết kế `max_steps_per_workflow`, `max_model_calls_per_workflow`, `max_tool_calls_per_turn`, `max_rows_per_query`, `max_duration`, `max_pending_reviews`. Giá trị khởi đầu **đề xuất**: tối đa 12 bước xử lý logic, 3 quyết định cần LLM, 5 tool calls/turn, query trả trang 25–50 dòng, 3 review items/lần; Codex cần đo, điều chỉnh và ghi rõ config. Không dùng các giới hạn này để bỏ bước bắt buộc; chuyển `WAITING_REVIEW` hoặc `PARTIAL` có giải thích. Một lệnh chat có thể tạo nhiều jobs nhưng từng job phải có deterministic IDs/fencing và checks.

---

## 6. Bộ công cụ của Agent — registry có mức quyền rõ ràng

### 6.1. Read-only tools (kế thừa + bổ sung)

| Tool | Trạng thái | Đầu vào giới hạn | Đầu ra quan trọng |
|---|---|---|---|
| `list_datasets` | Có | project, pagination | Danh sách nguồn, status |
| `get_workflow_status` | Có | project | READY/review/active job |
| `get_run_summary` | Có | verified run | VerifiedRun |
| `get_metric_breakdown` | Có | metric/run | MetricSnapshot |
| `list_exceptions` | Có | run, filter/paging | Cases + total |
| `get_match_evidence` | Có | run/case/group | Lineage/evidence, caps |
| `get_rule` | Có | run | Approved contract |
| `get_dataset_profile` | **ĐỀ XUẤT** | dataset/table owned | Columns, types, quality, warnings |
| `get_dataset_preview` | **ĐỀ XUẤT** | selected source/table + offset | Bounded rows, raw/canonical provenance |
| `query_dataset` | **ĐỀ XUẤT** | typed predicates/aggregation | Total, page, source refs, completeness |
| `get_job_or_workflow_status` | **ĐỀ XUẤT** | IDs scoped | Durable statuses/progress/errors |

Tất cả tool phải re-authorize scope **bên server trên mỗi call**, không chỉ kiểm đầu hội thoại. Không trả file system paths, SQL, DB session hoặc secrets cho Gemini.

### 6.2. Write/workflow tools — chỉ gọi qua policy executor

| Action gợi ý | Server thực hiện | Cho phép tự chạy khi | Cần review khi |
|---|---|---|---|
| `start_upload_parse` | Existing upload/parser job | Người dùng đã đính kèm và gửi, file hợp lệ | Parsing/extraction region ambiguous; PDF policy |
| `prepare_mapping_proposal` | Mapping proposal job | File hợp lệ, AI quota policy | Cần quyết định mới về field/grain |
| `apply_approved_mapping` | Existing approval/service reuse | Chỉ khi có **explicit approved reuse policy** và chữ ký/schema/semantics khớp; không tự đóng dấu người duyệt mới | Mapping mới/khác nghĩa/không chứng minh equivalence |
| `run_normalization` | Existing normalize job | Active approved mapping, revision/fingerprint phù hợp | Source/transform đổi hoặc quality cảnh báo cần người xác nhận |
| `prepare_reconciliation_plan` | Planner + deterministic validations | Sources canonical READY | Rule/scope/period chưa được duyệt |
| `run_approved_reconciliation` | Existing reconciliation run | Contract đã APPROVED, đúng sources/period/coverage, requested intent explicit | Bất kỳ thay đổi tài chính mới |
| `start_export` | Existing export job | VerifiedRun, quyền hợp lệ, user requested | Source/run chưa verified hoặc format không hỗ trợ |
| `record_review_decision` | Atomic review API | Người dùng trả lời đúng current review token | Token cũ, dữ liệu đã drift, câu trả lời mơ hồ |

**Quy tắc cứng:** Agent không được tự gọi endpoint approve qua cách giả actor hay “người dùng ủy quyền chung”. Server chỉ ghi approval khi có quyết định người dùng hoặc policy auto-reuse cụ thể đã được phê duyệt trước, không được giả `approved_by=AI` dưới danh nghĩa user. Trường hợp reuse mapping hiện tại trả về proposal cần phê duyệt phải **giữ nguyên** cho đến khi thiết kế/kiểm thử được policy giảm thao tác hợp lệ.

---

## 7. Review-by-exception: Hệ thống tự làm phần an toàn, chỉ hỏi khi cần

### 7.1. Ma trận quyết định bắt buộc

| Tình huống | Hành động Agent | Lý do |
|---|---|---|
| Chỉ đọc/profile/null/count/preview | Tự làm | Không đổi dữ liệu |
| Có approved mapping **đúng chữ ký** và phép biến đổi đã được chấp nhận | Tự normalize | User đã xác nhận semantic tại revision tương thích |
| Cột tiền `amount` chưa biết gross/net/paid/due | **WAITING_REVIEW** | Nghĩa tiền ảnh hưởng công thức |
| ID `00123`, có dấu cách/punctuation | Giữ nguyên, đề xuất, hỏi nếu cần | Biến đổi có thể phá identity |
| Date không rõ định dạng/ngữ cảnh timezone | Hỏi; không tự chọn timezone hệ thống | Sai kỳ/cutoff ảnh hưởng đối soát |
| Parser warning, nguồn PARTIAL | Chỉ xử lý phần cho phép, hiển thị PARTIAL; không tự coi READY | Không mất/giấu dữ liệu |
| Rule approved cùng nguồn, period, currency, amount basis, coverage | Tự chạy nếu yêu cầu người dùng rõ và rule phù hợp | Không cần approval lại cho cùng quyết định đã phê duyệt |
| Rule template approved nhưng kỳ/coverage mới hoặc nguồn đã drift | Hỏi/duyệt lại | Existing reuse contract chủ ý giữ review gate |
| Dữ liệu A/B có tên giống nhưng grain/amount semantics khác | Hỏi | Không suy join key chỉ từ tên |
| “Lệch do phí vận chuyển” nhưng không có cột phí | Trả chưa đủ bằng chứng | Không phỏng đoán nguyên nhân |
| “Đánh dấu tất cả lỗi là khớp” | Từ chối tự thực thi; hướng dẫn review có chứng cứ | Không giả kết quả đối soát |

### 7.2. Review request — ĐỀ XUẤT dữ liệu cần lưu

- `review_id`, `workflow_id`, `conversation_id`, `actor_id`, `workspace_id`, `project_id`.
- `reason_code`, `question`, `options` (typed, không tạo từ prose chưa kiểm chứng), `suggested_option` nếu có, `evidence_refs`.
- `affected_resource_ids` + **fingerprints** (file SHA, dataset version, table/schema signature, mapping/rule revision, run/period/coverage).
- `expected_effects` (có thể biến đổi trường nào, bất biến gì, invalidate downstream nào).
- `state` (`OPEN`, `DECIDED`, `INVALIDATED`), `created_at`, `resolved_at`, actor và audit.
- `decision_nonce`/idempotency key và expiry phù hợp, re-authorize khi submit.

Review phải được hoàn thành **qua API transactional**, kiểm row lock/fingerprint; stale review trả 409 và yêu cầu kiểm tra lại. Người dùng chọn “Chưa rõ” giữ workflow chờ, không ép lựa chọn bịa.

### 7.3. Không hợp thức hóa dữ liệu sai bằng xác nhận

Một click không biến một trường `PARTIAL` thành `READY` nếu data-quality checks vẫn FAIL. Phải tái chuẩn hóa/kiểm chứng revision mới trước khi công bố. Approval chỉ xác định lựa chọn nghiệp vụ, **không thay thế independent verification**.

---

## 8. Workflow A — Upload → AI chuẩn hóa

### 8.1. Hành trình chuẩn

1. Người dùng mở ứng dụng và thả 1–5 file CSV/XLSX vào composer; có thể gửi đồng thời “chuẩn hóa tất cả”.
2. Server xác minh session và upload constraints; nếu chưa có project, tạo project bootstrap an toàn và conversation gắn đúng project trong một flow idempotent.
3. Upload giữ bytes/SHA, parse/profile bằng worker hiện có; AI mapping proposal có thể được gọi **theo policy + quota**, không per-row.
4. Agent tìm mapping approved/template tương thích trước; nếu không có, dùng AI đề xuất và constraint validator.
5. Với từng bảng: phân biệt `SAFE_APPROVED`, `REQUIRES_REVIEW`, `UNSUPPORTED`.
6. Nếu có review, gom **các trường quyết định quan trọng** vào 1 thẻ, kèm sample/evidence; dừng đúng trạng thái.
7. Sau người dùng xác nhận, server tạo MappingRevision/ApprovedTransformRule như API hiện có, kiểm lại schema/fingerprint.
8. Agent tự enqueue normalization; worker tạo CanonicalArtifact, error artifact, DataQualityReport; snapshot/lineage bất biến.
9. Trả chat: nguồn, số dòng input/valid/invalid, status READY/PARTIAL, danh sách thay đổi, số dòng lỗi, link before/after.
10. Nếu có phần không thể xử lý, trả `PARTIAL` + next action, không trả “đã hoàn thành toàn bộ” sai sự thật.

### 8.2. Bootstrap project an toàn

API hiện tại `POST /api/projects` bắt buộc `name` và `business_scope`, còn upload cần `project_id`. **ĐỀ XUẤT**: backend tạo một project nháp cho lần upload đầu tiên, với scope nội bộ rõ là **chưa xác nhận**, cấm tái sử dụng template/approved rules từ domain khác cho đến khi đã xác nhận scope. Chọn một trong hai cách sau sau khi kiểm code/migration impact:

- **Ưu tiên nếu cần semantics đúng:** thêm trạng thái scope `UNCONFIRMED` additive; không biến nhãn `Dữ liệu mới` thành business scope đã phê duyệt.
- **Giải pháp ít migration hơn khi đủ an toàn:** giữ metadata marker typed cho bootstrap nhưng policy tuyệt đối cấm reuse cross-scope và cần thủ tục xác nhận phạm vi trước khi dùng template.

Không tạo project ngay khi load trang trống. Không tạo nhiều project khi double-submit/reload cùng attachment token. Không tự phân loại data tổng hợp là WORK hoặc TEST nếu policy/actor không cho phép; tôn trọng classification hiện có.

### 8.3. Phân biệt raw / cleaned / canonical

Raw file không thay đổi. Canonical dữ liệu chuẩn hóa là revision/artefact riêng, có lineage từng dòng và quy tắc transform. Nếu người dùng nói “sửa file”, phải hỏi có muốn xuất **bản xử lý mới** hay không; không ghi đè bản gốc.

### 8.4. Kết quả chat mẫu (câu chữ minh họa)

> Đã phân tích 2 tệp. Một tệp đã đủ điều kiện chuẩn hóa; tệp còn lại cần xác nhận nghĩa cột “Số tiền”. Tôi đã giữ nguyên file gốc và chưa dùng trường này để tính đối soát. Sau khi bạn xác nhận, tôi sẽ tự hoàn thành chuẩn hóa và báo các dòng còn lỗi.

Khi xong:

> Đã chuẩn hóa 2 nguồn theo các quy tắc đã duyệt. Kết quả: 1.240 dòng hợp lệ, 12 dòng lỗi định dạng, 3 trường cần xem thêm. Có thể mở dữ liệu trước/sau và 12 dòng lỗi.

**Số ở ví dụ chỉ là minh họa, không phải kết quả hệ thống.**

---

## 9. Workflow B — AI đối soát

### 9.1. Hành trình chuẩn

1. Người dùng: “Đối soát A với B trong tháng 10/2026”.
2. Agent resolve A/B thành đúng canonical IDs; nếu chỉ có file chưa chuẩn hóa, đề nghị/tiếp tục workflow chuẩn hóa trước.
3. Backend kiểm READY, owner/workspace, source signature, grain, metric/currency, period/timezone/coverage, row population, template revisions.
4. Nếu approved contract khớp đầy đủ với nguồn/phạm vi và không stale: có thể tự enqueue run theo **explicit user request**; không hỏi lại chỉ để bấm nút.
5. Nếu chưa có contract phù hợp: Planner typed proposal → semantic checks → review một lần những khóa, chỉ tiêu tiền, kỳ, coverage và rule quan trọng.
6. Sau approval hợp lệ, Agent tự chạy Existing Matcher + Independent Verifier.
7. Chỉ khi VerifiedRun/MetricSnapshot được publish mới trả KPI chính thức; nếu PARTIAL_VERIFIED ghi rõ phạm vi đã/ chưa verified.
8. Tạo thẻ kết quả trong chat: số matching groups, full match, unmatched left/right, pending/mismatch/review, KPI đã định nghĩa, chart, link exception/evidence/CSV/XLSX.
9. Người dùng hỏi tiếp trong cùng conversation; Agent không cần tự tính lại KPI, đọc VerifiedRun.

### 9.2. Blocker hiện tại: Planner `AI_INVALID_JSON`

Phải xử lý như **cổng độc lập trước khi dùng Agent lập rule mới**:

- Kiểm bằng chứng Planner lỗi: JSON syntax có thể parse, `status=NEEDS_REVIEW`, `plan=null`, `suggestions` có nhưng Pydantic không nhận; **chưa biết field nào sai** từ receipt cũ.
- Bổ sung diagnostics an toàn (`ValidationError.loc`, type/count, prompt/schema revision, response hash; không log raw dữ liệu bí mật).
- So sánh Pydantic schema/provider schema; tài liệu Gemini structured output chỉ hỗ trợ subset JSON Schema; đánh giá `responseSchema`/`responseJsonSchema` phù hợp model/REST endpoint thực, không tự giả API fields.
- Tách DTO đề xuất provider nhỏ khỏi domain `ReconciliationPlan` đầy đủ **chỉ nếu chứng minh là cần**; server vẫn kiểm approved contract.
- Unit/contract/property/mock tests cho null, missing fields, invalid enum, fabricated IDs, mismatch currency/timezone, NEEDS_REVIEW và PROPOSED.
- Không dùng regex sửa JSON bừa, không điền evidence giả, không bật auto retry mù, không hạ validator.
- LIVE: transport, schema, semantic, oracle quality **đánh giá riêng**. Chỉ coi PASS nếu cả bốn phù hợp bài thử.

Manual planner và approved template vẫn là fallback vận hành, nhưng không tuyên bố Agent hoàn toàn tự hiểu kế hoạch mới nếu live chưa đạt.

### 9.3. Ba nguồn

Không bắt buộc auto 3-way reconciliation mới trong MVP. Có thể giữ khả năng tạo hai cặp 2-source như hiện tại và trả kết quả riêng có nguồn; không gộp tùy ý hai run thành một kết quả với denominator khác.

---

## 10. Workflow C — Truy vấn và biểu đồ bằng ngôn ngữ tự nhiên

### 10.1. Typed Query Plan, không Text-to-SQL tự do

**ĐỀ XUẤT** typed query cho `RAW_PREVIEW`, `CANONICAL`, `VERIFIED_RUN`, `EXCEPTIONS`:

- `source_ref`: một dataset/table/canonical/run đã được scope-check.
- `select_fields`: field IDs trong catalogue allowlist, không nhận tên cột tự chế.
- `filters`: toán tử `eq`, `ne`, `in`, `gt`, `gte`, `lt`, `lte`, `between`, `is_null`, `contains` (contains chỉ trên text an toàn).
- `aggregations`: `count`, `sum_decimal`, `min`, `max`, `group_by` trên fields hợp lệ; average chỉ khi business meaning phù hợp.
- `sort`, `page`, `limit`, `period`, `timezone`, `null_policy`.
- `result_scope`: `ALL_MATCHING` vs `CURRENT_PAGE`, ghi rõ; không tính tổng từ 25 dòng preview mà nhận là tổng 50k.

Model chỉ sinh plan có kiểu. Backend validate nguồn/field/type/operator/limits và **compile từ allowlist** bằng Polars LazyFrame hoặc SQLAlchemy Core cho metadata; không đưa user text trực tiếp vào SQL hoặc DuckDB `read_parquet(path)` do model chọn. File path do Backend từ storage key được xác minh, không do LLM. Không infer paid = completed.

### 10.2. Query example (minh họa hợp đồng)

```json
{
  "source_kind": "CANONICAL",
  "source_id": "<canonical_id_from_catalogue>",
  "filters": [{"field_id": "<approved_status_field>", "op": "eq", "value": "PAID"}],
  "select_fields": ["<approved_transaction_id>", "<approved_paid_amount>"],
  "limit": 25,
  "offset": 0
}
```

Đây là JSON **minh họa**, không phải API đã tồn tại hoặc field ID thực. Nếu chỉ có trạng thái `completed` mà chưa có định nghĩa “đã chuyển tiền”, Agent phải hỏi hoặc từ chối suy luận.

### 10.3. Query semantics bắt buộc

- Cột có kiểu `Decimal` không được downcast float khi tính tiền; giữ scale/currency semantics, null != 0.
- Zero-prefix transaction IDs giữ dạng string, không parse thành integer.
- Date filters: year/timezone/interval rõ; `tháng 10` không có năm → hỏi hoặc yêu cầu ngữ cảnh đã xác nhận.
- Dữ liệu PARSED chưa được chuẩn hóa có thể cho xem/đếm chất lượng với nhãn **raw/unverified**, không dùng để báo KPI tài chính verified.
- `truncated` và `total_count` bắt buộc đúng; dữ liệu bị capped phải được báo thiếu.
- Với câu hỏi chứa “thiếu ở A nhưng có ở B” dùng verified run hoặc công cụ kiểm tra liên kết có rule được xác định; không làm một anti-join tự phát với khóa AI đoán.
- Group/aggregation trên VERIFIED snapshots không làm thay đổi định nghĩa tiền hoặc mẫu số; dùng metric IDs có định nghĩa.
- Mọi bảng kết quả trả `source_refs`/field provenance để có thể mở dòng nguồn.

### 10.4. Chart DTO

ĐỀ XUẤT `ChartResult {chart_type, title, x_label, y_label, unit, data_points, source_refs, filters, verified_status, completeness}`. Gemini chỉ chọn chart type và yêu cầu nhóm; Backend trả points được tính từ query/verified metric. Chart không được tự dựng giá trị do LLM sinh.

---

## 11. Durable workflow & resume/recovery

### 11.1. Workflow lifecycle

Các trạng thái **đề xuất**, chỉ tạo DB enums khi thực sự cần:

```text
CREATED -> PREPARING -> RUNNING -> COMPLETED
                       |-> WAITING_REVIEW -> RUNNING
                       |-> PARTIAL
                       |-> FAILED
                       |-> CANCELLED_BEFORE_NEXT_STEP
```

Không giả `COMPLETED` khi chỉ tạo job. `WAITING_REVIEW` không phải error; nếu người dùng bỏ dở, công việc vẫn mở lại được. `PARTIAL` có danh sách thứ đã thực hiện và phần chưa xong.

### 11.2. State persistence tối thiểu

Tận dụng `JobRow`, `ConversationRow`, `MessageRow`, `AuditRow`, approved revisions. Nếu chúng **không đủ để nối bước/chờ xác nhận**, tạo **một migration additive** với bảng workflow và review (hoặc JSONB state có constraint/index hợp lý). Không tạo hai cơ chế queue.

Trường tối thiểu:

- Workflow: `id`, `workspace_id`, `project_id`, `conversation_id`, `actor_id`, `goal`, `intent`, `state`, `input_fingerprint`, `context`, `approved_action_scope`, `current_step`, `created_at`, `updated_at`.
- Step: `tool_name`, `idempotency_key`, `job_id`, `status`, `input_hash`, `result_ref`, `error_code`, `attempt_count` (có thể JSONB với bounded steps nếu đơn giản hơn).
- Review: như mục 7.2, audit/revision.
- Links tới immutable canonical/run/export IDs và typed result blocks.

### 11.3. Idempotency/fencing

- Stable request key cho cùng **conversation + message + file hashes + action scope**. Khi client timeout/reload, phải trả same workflow/job, không tạo duplicate.
- Trước khi chạy bước đã hoàn thành, kiểm result/claim status và fingerprint. Không enqueue lại completed step do polling.
- Worker giữ lease/fencing như hiện tại; orchestrator chỉ publish workflow step state khi job result tương ứng đã có; không suy `SUCCEEDED` từ HTTP 202.
- Khi user đổi scope/permission/source revision trong lúc chờ: reauthorize + revalidate; invalidated review không tiếp tục.
- Nếu workflow gồm nhiều nguồn và có partial success: lưu từng step; retry chỉ bước chưa hoàn thành khi an toàn.
- Tắt/dừng: không hủy hoặc xóa raw/canonical/run đã publish; thông báo chính xác.

### 11.4. Không dùng LLM để quản lý retry

Retry transient theo policy worker hiện có; model không quyết định retry 10 lần. Với request Gemini delivery unknown: giữ reservation, không tự gửi lại cùng request để tránh trùng và vượt ngân sách.

---

## 12. API, DTO và permission boundary

### 12.1. API đã có — phải giữ tương thích

Existing `POST /api/assistant/messages`, conversation endpoints, upload, mapping approval, normalize, planning, approval, reconciliation run, read-only tools, exports tiếp tục tồn tại. UI cũ nâng cao vẫn gọi được; không làm mất workflow manual phục vụ debug và fallback.

### 12.2. API mới đề xuất (cần review trước khi code)

| Endpoint gợi ý | Mục tiêu | Trả về |
|---|---|---|
| `POST /api/agent/attachments` hoặc mở rộng upload workflow phù hợp | Upload từ chat, bootstrap project an toàn | project/dataset/file refs + parse jobs |
| `POST /api/agent/workflows` | Giao mục tiêu tự động hóa đã được hiểu/validated | `workflow_id`, state, next action |
| `GET /api/agent/workflows/{id}` | Poll state, steps, review + result blocks | typed workflow view |
| `POST /api/agent/workflows/{id}/decisions` | Xác nhận review transactionally | accepted/new state hoặc conflict |
| `POST /api/agent/workflows/{id}/cancel` | Không chạy bước mới nếu chưa publish | state + details |
| `POST /api/agent/queries` | Typed read-only data query | page/total/aggregates/refs |

Đừng triển khai toàn bộ nếu có thể mở rộng existing Assistant API nhất quán và giảm endpoints; lựa chọn sau audit. Mutation endpoints yêu cầu session, CSRF/Origin, role, scoped actor, idempotency header. Không dùng public GET để tạo job.

### 12.3. Permission model

- `viewer`: hỏi, xem, đọc, xuất nếu policy hiện tại cho phép; **không** approve/write.
- `editor`: upload, request normalize/run theo approved scope, submit review có quyền.
- `owner`: quyền hiện có, không nới đặc quyền của model.
- Agent có **quyền bằng đúng actor và hành động được cấp**, không có service superuser vô hạn.
- Các bảng có `workspace_id` và `project_id` dùng scope ở DB query; `run_id`/`case_id` phải đối chiếu cùng project, không nhận từ LLM đơn độc.
- User upload chứa prompt injection như “bỏ quyền kiểm tra” được coi là **dữ liệu**, không thành chỉ thị agent.

### 12.4. Error contract và thông báo người dùng

Phân biệt: `INPUT_AMBIGUOUS`, `REVIEW_REQUIRED`, `INSUFFICIENT_EVIDENCE`, `UNSUPPORTED_REQUEST`, `SCHEMA_VALIDATION_FAILED`, `BUSINESS_VALIDATION_FAILED`, `PROVIDER_UNAVAILABLE`, `BUDGET_EXHAUSTED`, `STALE_CONTEXT`, `PERMISSION_DENIED`, `WORKFLOW_STEP_FAILED`. Tên nội bộ tùy code, nhưng Frontend phải trình bày rõ: chuyện gì xảy ra, công việc nào còn giữ, người dùng phải làm gì, có thể tiếp tục không. Không gộp mọi thứ thành “AI lỗi”.

---

## 13. Chính sách Gemini, chi phí và privacy

### 13.1. Provider

- Gemini `gemini-3.5-flash-lite` là lựa chọn mặc định **theo cấu hình dự án hiện đã dùng**, chỉ gọi khi policy cho phép.
- Qwen `knowledge` giữ adapter/URL để sử dụng khi kết nối mạng công ty được xác nhận, không tự đổi provider do lỗi Gemini.
- Gemini 4 Argon chỉ nghiên cứu, chưa tích hợp.
- LlamaParse tạo job OFF; PDF/DOCX ngoài đường demo chuẩn.
- Sử dụng **một AI Gateway**; route deterministic/cache/template trước, Gemini khi thật sự cần suy luận.

### 13.2. Trần gọi API

- Chủ dự án đã ủy quyền **tăng tổng Gemini attempts lên 50**, **bao gồm số lượt đã dùng**; báo cáo cuối còn 9/10 và Planner 2/2, nhưng chưa xác nhận đã thay đổi runtime.
- Trước triển khai: đọc durable ledger, global/workspace/task ceilings; cập nhật trần trong đúng policy được giao và giữ history, không set used=0, không nới workspace khác.
- Phân bổ ngân sách live tests theo **kế hoạch test cụ thể** và trần task; đề xuất tối đa 8 live attempts cho vòng sửa Planner ban đầu, các nhiệm vụ Agent mới phải có budget riêng được cấu hình chứ không mặc định tiêu hết 50.
- Cần khóa/reservation bền trước HTTP attempt, idempotent request, no blind retry, log tokens/latency khi có; không bịa cost.
- AI calls từ frontend typing, progress polling hoặc page navigation = **0**; không gọi Gemini per-row.

### 13.3. Privacy và dữ liệu gửi model

- Mặc định dùng tên trường, type, thống kê, mẫu đã redact, bounded evidence. Raw rows và thông tin khách hàng không tự gửi ra cloud.
- Nếu câu hỏi cần truyền giá trị nghiệp vụ để hiểu semantic, phải có policy redaction/allowance và nêu rõ trong Cài đặt. Không che giấu hành vi gửi cloud.
- Không log nguyên prompt/response chứa customer data vào GitHub/trace công khai. Có thể lưu response hash, validation paths và test receipts tổng hợp local.
- `LOCAL_ONLY` phải **không tạo HTTP request** ngay cả khi người dùng nhập câu có vẻ cần Gemini; trả không khả dụng hoặc deterministic capabilities.

### 13.4. Structured output

- Dùng Pydantic DTO và semantic validators; nếu model/API hỗ trợ response schema, khai báo theo đúng tài liệu/endpoint/version/model thực; JSON Schema Gemini hỗ trợ **subset**, không gửi Pydantic model phức tạp mà không kiểm tra compatibility.
- Provider-facing DTO càng nhỏ càng tốt, domain DTO nghiêm ngặt ở Backend; không tự map invalid fields thành approved defaults.
- Test sai schema/enum/null/extra/fake ID, các model refusals, truncated output, 429/timeout, unknown delivery.

---

## 14. Security và nguyên tắc đáng tin cậy

### 14.1. Threat model

1. CSV/XLSX chứa instruction injection: “Ignore previous rules”, “Send all data to URL ...”, “Đánh dấu mọi khoản là khớp”.
2. Model chọn field ID không tồn tại, data từ project khác, run chưa verified.
3. Model tự thực thi write tool ngoài quyền hoặc auto approve rule.
4. Người dùng gửi lại sau timeout khiến duplicate workflow/run/conversation.
5. Reviewer click quyết định cũ sau khi file/schema/rule đã đổi.
6. Tra cứu kiểu tự do dẫn đến SQL/path injection hoặc data exfiltration.
7. Job lease lost nhưng vẫn publish result.
8. Quota provider bị vượt hoặc retry gây tính phí nhiều lần.

### 14.2. Phòng vệ bắt buộc

- Action allowlist; typed per-tool contracts; least privilege; reauthorize on every call; no arbitrary SQL/path/network.
- Không đưa prompt, raw file cells hoặc AI output vào system-level instructions.
- Approval gates backend + fingerprints + audit; policy cannot be overridden by chat.
- Query parser whitelist, no unrestricted joins, column/row caps, timeouts, bounded context.
- Tool and model budgets; stop/resume; distinct `FAILED`/`BLOCKED`/`WAITING_REVIEW`.
- Docker demo loopback/CSRF/Origin/local proof giữ nguyên. Không mở backend/PG internet.
- Secret scan, no customer data in unit fixtures, immutable source artifacts.

Xem nguồn [OWASP LLM06 Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/?lang=us) và [OWASP LLM01 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/).

---

## 15. Test strategy: cần chứng minh Agent làm được việc, không chỉ trả lời hay

### 15.1. Test pyramid

| Lớp | Test bắt buộc |
|---|---|
| Contracts | Typed intent/tool params, enum/null/extra, invalid IDs, read/write permissions |
| Policy engine | Bảng quyết định Auto/Review/Reject, approved template drift, partial/unknown, no fake approval |
| Workflow unit | Step transitions, review/resume, cancellation, stale revisions, idempotency, max steps |
| PostgreSQL integration | actor/project isolation, CSRF, concurrent submits, locks/fencing, failure/partial/recovery |
| Financial oracle | Decimal, matching, duplicates, unmatched left/right, 1:N/N:1, coverage, null != zero, full/partial verified |
| Typed query oracle | Filter/sort/page/count/aggregation, statuses, total vs page, provenance, group-by/Decimal |
| Gemini mock/contract | Intent selection, schema validation, prompt injection, Planner error handling, timeout/unknown delivery |
| Gemini live | Bounded representative intents/mapping/Planner tool selection, transport/schema/semantic/business quality riêng |
| Browser E2E | Upload from chat → automatic safe steps → review → resume → run → table/chart → evidence → reload |
| Runtime | 4/4 healthy, re-create, persistence, backup/restore local, rollback, source/image SHA |

### 15.2. NLP benchmark tiếng Việt

Xây bộ **gold intents/slots** độc lập gồm những cách diễn đạt tự nhiên khác nhau (không copy prompt/fixtures model):

- “chuẩn hóa”, “làm sạch”, “định dạng lại”, “sắp xếp về một mẫu”.
- “đối soát”, “so khớp”, “kiểm tra tiền lệch”, “kiểm tra đơn thiếu”.
- “đã chuyển khoản”, “đã thanh toán”, “đã hoàn thành”, “chờ xử lý” (*không coi đồng nghĩa khi semantics khác*).
- “trong tháng 10”, “tháng 10/2026”, “kỳ trước”, “từ ngày ... đến ngày ...”.
- “file A/B”, “bảng doanh thu”, “sheet sổ cái”, tên nguồn bị trùng.
- “số lượng”, “số tiền”, “tỷ lệ khớp”, “tổng giá trị lệch”.
- “trả các dòng thiếu phía A”, “vì sao có cả hai mà không khớp”.
- Câu đa bước, lỗi chính tả, thiếu nguồn, ngữ nghĩa không chắc, câu ngoài phạm vi.

Tối thiểu đề xuất **60 câu** qua ít nhất 2 miền dữ liệu (đơn hàng/giao nhận và sổ cái/chứng từ) + 20 cases âm tính/điều kiện biên. Đây là mục tiêu thiết kế, Codex phải tạo, review oracle và báo actual số case.

Đo riêng:

1. Intent accuracy.
2. Slot/source resolution accuracy.
3. Tool selection accuracy.
4. Action authorization pass (không có unauthorized writes trong negative tests).
5. Workflow completion rate trên kịch bản đủ thông tin.
6. Abstention chất lượng khi thiếu evidence.
7. Financial correctness theo independent oracle, không tính câu LLM làm oracle.
8. Average clarification turns (mục tiêu giảm, không giấu quyết định quan trọng).
9. Cloud attempts/tokens/latency theo workflow.

### 15.3. Golden demo E2E MUST

**Journey 1 — Normalization có điểm mơ hồ**

- Tạo conversation khi chưa có project → upload hai Excel/CSV tổng hợp → yêu cầu chuẩn hóa.
- AI tự profile; tìm 1 trường tiền ambiguous; gửi đúng review card; người dùng xác nhận; workflow resume; canonical READY/PARTIAL đúng oracle; raw hashes không đổi.

**Journey 2 — Reconciliation**

- Hai canonical READY → yêu cầu đối soát.
- Nếu rule approved phù hợp: tự enqueue; nếu rule mới: review đúng các trường; approved mới chạy.
- Independent Verifier PASS; KPI, biểu đồ, unmatched/mismatch đúng fixtures; không bịa nguyên nhân.

**Journey 3 — Data Q&A**

- “Liệt kê đơn đã chuyển tiền” trên source có trạng thái chứng minh được → filter + total + page + evidence đúng.
- Trên source chỉ có `completed` nhưng không chứng minh `paid` → hỏi/từ chối suy luận.

**Journey 4 — Multi-turn context**

- “Các trường hợp thiếu?” → “Còn những đơn lệch trên 100.000?” → “Vì sao đơn đó lệch?”; giữ đúng run/source/case sau back/forward/reload.

**Journey 5 — Robustness/security**

- Client gửi lại cùng action sau timeout → không thêm job; worker SIGKILL/reclaim → không duplicate canonical/run; viewer không approve; cross-project data inaccessible; fake evidence; prompt injection trong cell.

### 15.4. Acceptance targets

- **MUST = zero known failures** đối với approved rules/financial oracle/authorization/idempotency/persistence trong suite xác định.
- Intent/router/tool accuracy phải có bảng đo trên gold set và phân tích lỗi; **không tuyên bố 100% ngoài tập thử**. Nếu chưa đủ mức hữu dụng, thu hẹp intent và nêu giới hạn thay vì bịa.
- Với source có approved mapping/contract trùng scope và request đủ: mục tiêu **một lệnh chat, không yêu cầu duyệt lại**.
- Với source mơ hồ: chỉ những thông tin có ảnh hưởng đến semantics được hỏi, được nhóm hợp lý; không khóa người dùng trong form dài.
- Mọi số KPI trong UI đối chiếu cùng VerifiedRun/MetricSnapshot hoặc data-query oracle; `UNKNOWN/PARTIAL` hiển thị trung thực.
- Không có lỗi layout nghiêm trọng ở 390/768/1366/1440/1920; keyboard, focus, responsive, long files, long chat.

---

## 16. Milestones & các cổng triển khai cho Codex

### Cổng 0 — Preflight / bảo vệ baseline

**Làm:** đọc Rules/AGENTS/PROJECT_PLAN/status; fetch Git main/feature, kiểm hiện trạng code, DB, Gemini ledger, Docker image IDs, rollback, SHA/volumes; backup local đúng quy trình; chạy baseline 191/59 (hoặc số hiện tại được đo lại). Ghi compatibility với workflow người dùng mới.  
**Ra:** `Baseline Matrix`, risk register, dependency map, existing tests and blockers.  
**Dừng nếu:** local demo proof không đủ, DB không ổn, dữ liệu/rollback không bảo toàn.

### Cổng 1 — Planner/AI Gateway quality foundation

**Làm:** chẩn đoán lỗi live `AI_INVALID_JSON` theo field, provider schema, Pydantic/semantic; sửa tận gốc, diagnostics, retry policy; kiểm Gemini ceiling 50 đã được phê duyệt và lifetime task caps theo yêu cầu triển khai; offline regression rồi live tests giới hạn.  
**Ra:** Typed Planner đáp ứng `NEEDS_REVIEW` và `PROPOSED` đúng chất lượng nghiệp vụ, không giả `PASS LIVE`.  
**Dừng nếu:** semantic validator không đạt hoặc provider policy không rõ.

### Cổng 2 — Chat-first UI + upload-first bootstrap

**Làm:** giữ App Shell, đặt Agent/Assistant làm home, upload inline, safe project bootstrap, history/context, chips file, empty/error/loading; giữ Dữ liệu/Đối soát/Ngoại lệ/Báo cáo trong nhóm secondary.  
**Ra:** Người mới upload được và chat ngay, không cần tạo project bằng tay.  
**Tests:** E2E no-project, multiple files, double submit, duplicate content, denied write, source scope, responsive/back-forward.

### Cổng 3 — Durable Agent workflow + review-by-exception

**Làm:** bounded typed intents/tools, policy engine, workflow/review state, resume/idempotency, action rights, optimistic concurrency/fencing; orchestration chạy chuẩn hóa theo existing engine, không bypass approvals.  
**Ra:** User nhắn chuẩn hóa, Agent tự làm phần an toàn, hỏi điểm mơ hồ, tiếp tục khi xác nhận.  
**Tests:** complete/partial/stale/cancel/timeout/reload/worker crash; golden normalization.

### Cổng 4 — Agentic reconciliation

**Làm:** resolve datasets, approved rule/template policy, plan with review, backend execute/verify; result blocks, exceptions/evidence.  
**Ra:** Chat → verified run → phân tích tại chat.  
**Tests:** no approval bypass, period/coverage/drift/Decimal oracle, no fabricated KPI, rollback.

### Cổng 5 — Typed query + charts + follow-up questions

**Làm:** read-only typed query, schema/permission checks, pagination, aggregation, chart DTO; multi-turn context/resolution; read-only evidence links.  
**Ra:** hỏi giao dịch theo trạng thái, lọc nhóm, vẽ chart, giải thích case bằng dữ liệu thật.  
**Tests:** query oracle, semantics status, large data capped, consistent units, late response, injection.

### Cổng 6 — Product acceptance + release readiness

**Làm:** full regression offline/PG/UI, representative Gemini live within approved budget, source/data integrity, security/UX review, Docker Compose restart/recreate/backup/rollback, docs sync, verify current source/image.  
**Ra:** bảng PASS/FAIL/BLOCKED/NOT VERIFIED/DEFERRED; demo runbook; SHA/receipts/quotas.  
**Merge:** chỉ theo ủy quyền release riêng và khi gates đạt; không force/delete branches unmerged, không xóa volumes/images rollback.

### Dependencies / nguyên tắc triển khai

`Cổng 0 → Cổng 1 → Cổng 2 → Cổng 3 → Cổng 4 → Cổng 5 → Cổng 6` là thứ tự nghiệm thu đề xuất. Có thể phát triển offline một số phần độc lập song song ở cấp code, nhưng **không được báo hoàn thành kịch bản Agentic Reconciliation nếu Planner live/semantic blocker còn mở**.

---

## 17. Work breakdown / hồ sơ bàn giao theo từng phần

### 17.1. Cổng chất lượng yêu cầu kỹ thuật

Mỗi module thay đổi phải có:

1. Problem statement + expected behavior (tiếng Việt).
2. Current source references và contract owners.
3. Design alternative và lý do chọn cách ít phức tạp nhất.
4. Pydantic DTO/tool policy/schema migration (nếu cần).
5. Failure modes (happy/partial/blocked/unknown delivery/stale).
6. Tests added and real outcome.
7. AI attempts usage ledger (nếu có).
8. Changelog & related docs.

### 17.2. Tài liệu cần cập nhật khi triển khai

- `docs/PROJECT_PLAN.md`: bổ sung quyết định đổi UX/agent-first như **amendment có ngày và lý do**, không xóa ba giai đoạn nghiệm thu cũ.
- `docs/ARCHITECTURE.md`: orchestrator, worker, state, tool boundary.
- `docs/DATA_CONTRACTS.md`: workflow, review, typed query/result DTO.
- `docs/AI_INTEGRATION.md`: Gemini API schema, model routing, policy/quota, tool call validation.
- `docs/TESTING_GUIDE.md`: agent golden set và E2E.
- `docs/IMPLEMENTATION_STATUS.md`: mỗi cổng, SHA/test/limitations.
- `README.md`: hướng dẫn demo ngắn theo Upload → Chat → Result.

Không thêm hàng chục Markdown trùng lặp, không xóa audit history hay accepted tags.

### 17.3. Chất lượng deploy

- Docker Compose vẫn **4 services**. Không tách Agent thành service mới khi worker/Backend đủ.
- Bảo vệ `postgres_data`/`artifacts`; migration additive; backup + restore drill trước/sau.
- Build từ đúng commit/revision; FE/BE/worker SHA và OCI labels; 4/4 health không thay thế E2E proof.
- Giữ accepted-main rollback images, không `docker system prune -a`, `docker volume prune`, `docker compose down -v` hay global image delete.
- Dọn cache/file chỉ khi có bằng chứng không thuộc dữ liệu/runtime/hợp đồng. Release image cleanup là nhiệm vụ riêng sau khi main candidate đạt.

---

## 18. Rủi ro cần chốt trước khi giao Codex

| Rủi ro | Cách kiểm soát | Mức ưu tiên |
|---|---|---|
| Agent tạo approved mapping/rule từ prompt | Policy gate server + review decision binding | P0 |
| Planner Gemini sai schema | Chẩn đoán typed output + regression + live oracle | P0 |
| Chat bootstrap project scope giả dẫn đến reuse nhầm | `UNCONFIRMED` scope, forbid template reuse | P0 |
| Tự động chạy khi chỉ có dữ liệu PARTIAL | Quality/readiness policy fail closed | P0 |
| Tool result lẫn project/run | Scope check mỗi call + context revision | P0 |
| Duplicate workflows sau reload/retry | Durable idempotency, job fencing | P0 |
| Chat trả lời “đã chuyển tiền” theo completed | Query semantics + field evidence + abstention | P0 |
| Chart dùng page count làm total | Typed query result total + verified metric source | P0 |
| Gemini quota không đúng lịch sử | Validate ledger global/workspace/task; no reset | P0 |
| Agent quá phức tạp, chậm/tốn token | Bounded steps, deterministic pipeline, no per-row LLM | P1 |
| Giao diện mới làm mất manual fallback | Giữ routes/API, smoke regression | P1 |
| PDF/DOCX khiến scope phình | CSV/XLSX main path, PDF/DOCX review-only giới hạn | P1 |

---

## 19. Demo script chuẩn cho chủ dự án

**Bối cảnh:** Browser `http://127.0.0.1:18180` trong loopback demo đã xác minh; một workspace, hai bộ fixture thuộc hai miền nghiệp vụ; cloud consent và quota được kiểm tra.

1. Mở ứng dụng thấy trang **Trợ lý AI** trong khung UI hiện tại.
2. Upload `SoCai.xlsx`, `ChungTu.xlsx` ngay trong composer.
3. Nhắn: `Hãy kiểm tra và chuẩn hóa hai bộ dữ liệu này, báo cho tôi những vấn đề quan trọng.`
4. Hệ thống tự parse/profile và tận dụng mapping đã approved nếu tương thích; nêu rõ phép biến đổi an toàn.
5. AI yêu cầu xác nhận **một** trường tiền mơ hồ trong review card; người dùng xem vài dòng nguồn và trả lời.
6. Workflow tiếp tục, trả READY/PARTIAL và link trước/sau; không cần sang màn hình Mapping hay Normalize.
7. Nhắn: `Đối soát hai bộ dữ liệu này cho kỳ tháng 10/2026.`
8. Agent kiểm source/rule; nếu chưa có approved rule đúng scope, hỏi khóa/metric/coverage quan trọng trong một thẻ. Người dùng duyệt; Agent tự chạy, Independent Verifier tạo VerifiedRun.
9. Chat trả KPI, bar chart, số missing/variance theo metric thật và link ngoại lệ.
10. Nhắn: `Liệt kê các chứng từ có ở sổ cái mà không có ở file chứng từ.` → bảng paging đúng oracle.
11. Nhắn: `Vì sao chứng từ 000702 không khớp?` → số/nguồn/rule chính xác, không đoán nguyên nhân thiếu căn cứ.
12. Nhắn: `Xuất kết quả ra Excel.` → export từ run đã verified.
13. Reload hoặc restart worker/browser, mở lại conversation và workflow vẫn đúng; gửi lại cùng câu không duplicate action.
14. Đổi sang dự án khác, thử hỏi dữ liệu cũ → chặn đúng quyền; quay về project original để xem data.
15. Ngắt cloud hoặc hết budget giả lập → chức năng deterministic/manual tiếp tục trong giới hạn; trạng thái báo trung thực, không fake model response.

**Điều kiện demo đạt:** Với bộ fixture và approval được định nghĩa trước, các bước trên thực sự chạy qua Backend/worker, không hardcode chat response; các numbers được so với oracle độc lập và có source references. Nếu bất kỳ bước nào mới chỉ mock, báo rõ và không gọi `PASS LIVE`.

---

## 20. Checklist Definition of Done

Đây là checklist tiêu chí của kế hoạch, không tự động đánh dấu toàn bộ từ số tests PASS. Kết quả từng gate hiện tại ở IMPLEMENTATION_STATUS mục S: 248 backend/PG và 72 E2E PASS; UI 18 states/5 widths, persistence/recovery/backup/rollback đạt trong phạm vi kiểm tra. Broad NLP còn lỗi và full gold trên prompt 6 chưa đo lại, nên tiêu chí toàn MVP/merge/release vẫn mở. Giữ nguyên các yêu cầu bên dưới.

### Product / UX

- [ ] Giữ App Shell, sidebar/header/theme như trước; Trợ lý AI làm trang chính.
- [ ] Có thể vào chat chưa có project; upload trực tiếp không tạo nhầm project.
- [ ] Chat hiểu và thực thi bốn năng lực MVP; không chỉ dẫn người dùng sang màn hình khác.
- [ ] Có progress, review-by-exception, resume, bảng/biểu đồ và source links.
- [ ] Manual advanced routes vẫn hoạt động.
- [ ] Các viewport 390/768/1366/1440/1920 và keyboard/focus PASS.

### Core correctness

- [ ] Không tự approve mapping/rule mới; phù hợp source signatures/revisions.
- [ ] Decimal, NULL, zero-prefix, 1:N/N:1, lineage và immutable artifacts không regression.
- [ ] VerifiedRun/MetricSnapshot là nguồn sự thật duy nhất cho KPI đối soát.
- [ ] Không bịa field, paid status, evidence, nguyên nhân chênh lệch, số tiền hay biểu đồ.
- [ ] Typed Query đủ quyền và logic, tổng/đếm/aggregate đúng oracle.

### Agent / security

- [ ] Action registry có kiểu, allowlist, rate/budget/step bound.
- [ ] Workflow state bền, review token/fingerprint, idempotency, resume/recovery.
- [ ] Viewer không ghi, không cross-project leak, CSRF/local demo proof giữ nguyên.
- [ ] Prompt injection từ file và câu hỏi bị chặn ở tool boundary.
- [ ] Provider failure/invalid JSON/timeout/budget được ghi chính xác.

### Acceptance / operations

- [ ] Planner live blocker được xử lý hoặc được báo là blocker; không fake PASS.
- [ ] Gemini total ceiling 50 chỉ sau khi config/ledger hợp lệ; lịch sử 9 attempts bảo toàn theo dữ liệu thực.
- [ ] Bộ golden tiếng Việt và workflow E2E đã đo, có báo cáo các trường hợp FAIL.
- [ ] Full backend/PG/Playwright/Ruff/mypy/TypeScript/ESLint/build PASS.
- [ ] Docker/persistence/restart/backup-restore/rollback có bằng chứng từ runtime đúng SHA.
- [ ] Git sạch, code/docs đồng bộ, feature branch được push; merge/release theo ủy quyền riêng.

---

## 21. Tài liệu chính thức và nguồn phương pháp

> Các đường dẫn sau hỗ trợ các quyết định kỹ thuật; chúng **không thay thế kiểm tra version/model/API/driver đang dùng**. Tài liệu source trong repository là cơ sở xác minh code thực tế, còn phần này là nguồn tham khảo bên ngoài.

1. **Google Gemini — Function calling:** https://ai.google.dev/gemini-api/docs/function-calling — model tạo tool request, ứng dụng thực thi công cụ thực, không giao quyền trực tiếp cho model.
2. **Google Gemini — Structured output:** https://ai.google.dev/gemini-api/docs/structured-output — supported subset JSON Schema, kiểm output bằng validators.
3. **Google — GenerateContent API:** https://ai.google.dev/api/generate-content — kiểm request/response format đúng transport endpoint.
4. **Microsoft Finance Agent — Reconcile data:** https://learn.microsoft.com/en-us/copilot/finance/reconcile/reconcile-data — AI đề xuất đối soát, assisted/autonomous mode và template review.
5. **Microsoft Finance Agent — Create reconciliation agent:** https://learn.microsoft.com/en-us/copilot/finance/reconcile/create-reconciliation-agent — tái sử dụng template để tự động hóa, không sao chép enterprise scope.
6. **Polars Lazy API:** https://docs.pola.rs/user-guide/lazy/using/ — lazy scan, tối ưu và kiểm tra schema.
7. **Polars optimization:** https://docs.pola.rs/user-guide/lazy/optimizations/ — predicate/projection pushdown.
8. **PostgreSQL SELECT / SKIP LOCKED:** https://www.postgresql.org/docs/current/sql-select.html — kiểm ngữ nghĩa row locking/queue.
9. **PostgreSQL explicit locking:** https://www.postgresql.org/docs/current/explicit-locking.html — advisory/transaction locks.
10. **OWASP LLM06 Excessive Agency:** https://genai.owasp.org/llmrisk/llm062025-excessive-agency/?lang=us — least privilege, hạn quyền tự động hóa.
11. **OWASP LLM01 Prompt Injection:** https://genai.owasp.org/llmrisk/llm01-prompt-injection/ — uploaded data là dữ liệu không tin cậy.
12. **W3C ARIA Combobox Pattern:** https://www.w3.org/WAI/ARIA/apg/patterns/combobox/ — chọn project/nguồn, keyboard & accessibility.

### Tham chiếu nội bộ bắt buộc

- `Rules.md`, `AGENTS.md`, `docs/PROJECT_PLAN.md`, `docs/ARCHITECTURE.md`, `docs/DATA_CONTRACTS.md`, `docs/AI_INTEGRATION.md`, `docs/TESTING_GUIDE.md`, `docs/IMPLEMENTATION_STATUS.md`.
- `backend/studio/api.py`, `backend/studio/reconciliation_api.py`, `backend/studio/worker.py`, `backend/studio/assistant.py`, `backend/studio/assistant_jobs.py`, `backend/studio/assistant_tools.py`, `backend/studio/ai_gateway.py`, `backend/studio/contracts/assistant.py`, `backend/studio/normalization.py`, `backend/studio/database.py`.
- `frontend/src/App.tsx`, `frontend/src/AssistantStudio.tsx`, `frontend/src/AssistantWorkflow.tsx`, `frontend/src/navigation.ts`, `frontend/src/styles.css`.

---

## 22. Quyết định cuối cùng và lời nhắc cho Codex

**Một sản phẩm đúng ý chủ dự án không phải có nhiều nút AI, mà phải có khả năng làm việc bằng ngôn ngữ tự nhiên trên dữ liệu thật.** Người dùng giao mục tiêu, hệ thống tự thực hiện những thao tác an toàn, biết dừng ở điểm phải xin quyết định, tiếp tục sau xác nhận và xuất kết quả có bằng chứng.

**Ưu tiên thứ tự:**

1. Giữ chính xác và an toàn của engine hiện có.
2. Giải quyết lỗi typed Planner trước khi Agent dựa vào Planner.
3. Chuyển entrypoint thành chat/upload và thực thi workflow thật.
4. Thu gọn yêu cầu phê duyệt bằng chính sách rõ ràng, không lách approval.
5. Tra cứu và phân tích linh hoạt nhưng có typed query/oracle.
6. Demo end-to-end, regression, rollback và báo cáo trung thực.

Không được đánh đổi 1–2 click ít hơn để tạo kết quả tài chính sai. Không thêm hệ thống doanh nghiệp/multi-agent vì mục tiêu nhỏ là chứng minh **AI Agent thật, chính xác, dễ dùng** trong MVP.

**MỐC LỊCH SỬ S 02/11/2026: UI và technical gates đã kiểm chứng, chưa nghiệm thu toàn MVP vì broad NLP quality và hết quota; chưa merge hoặc deploy accepted-main release.**

## 23. Bổ sung chính thức 02/11/2026 — tối giản giao diện AI Assistant

Yêu cầu chủ dự án gửi tiếp trong nhiệm vụ thay cách tổ chức UI ở mục 3: tên hiển thị thống nhất **AI Assistant** (không đổi endpoint/model/table/module). Sidebar chỉ có AI Assistant, Dữ liệu và nhóm Kết quả mở/đóng gồm Tổng quan/Đối soát/Ngoại lệ/Báo cáo; Cài đặt/tài khoản ở dưới, trạng thái bảo vệ dữ liệu thu gọn. Giữ logo, màu/font/components/AppShell.

Empty chat không có khung chat trống hoặc cột lịch sử thường trực: biểu tượng nhỏ, “Bạn muốn xử lý dữ liệu gì?”, mô tả “Tải file lên hoặc giao việc cho AI bằng tiếng Việt.”, một composer giữa trang, gợi ý bên dưới. Có hội thoại thì composer xuống cuối, transcript cuộn độc lập; table/chart/review/evidence trong chat. Lịch sử mở bằng nút nhỏ/panel, ngữ cảnh run bằng chip và danh sách chỉ mở khi cần; xóa vào menu và giữ confirmation. Origin hợp lệ từ Data/Exceptions/Reports mới có quay lại. Không lặp tên project hoặc bắt chọn trước upload. Cloud/provider status phải từ backend, không suy sẵn sàng chỉ từ kết nối API.

Nghiệm thu bổ sung ít nhất 15 trạng thái ở 5 widths 390/768/1366/1440/1920: empty/short/long/upload/running/review/completed/wide table/chart/evidence/history/multiline/mobile keyboard/sidebar/loading-error-permission. Chụp và xem trước/sau, giữ regression cũ bằng thao tác phù hợp UI mới, không xóa oracle. Không đổi backend/security/approvals/ledger vì layout. Tệp bổ sung nhận được hiện chỉ chứa văn bản, chưa có hai ảnh phác thảo trong attachment; kiểm chứng bố cục theo mô tả chi tiết và screenshots thực tế, không tuyên bố đã đối chiếu ảnh chưa nhận. Toàn bộ gate Agent/live/release của nhiệm vụ trước vẫn tiếp tục.

Kết quả bổ sung UI: **PASS LOCAL/MOCK CONTRACT** theo mô tả, 18 trạng thái × 5 widths = 90 screenshots, trong 5 visual tests của full 72 E2E PASS. Ảnh trước/sau đã xem; exact sketch comparison NOT VERIFIED vì attachment chỉ chứa văn bản. Không suy UI PASS thành broad Agent LIVE hoặc quyền merge. Chi tiết source SHA, bằng chứng và các gate chưa đạt ở IMPLEMENTATION_STATUS mục S.


## 24. Chỉ dẫn tiếp theo — Assistant Experience & NLP Quality Finalization

Mục này thay primary navigation của mục 23: **AI Assistant, Lịch sử, Cài đặt**; không còn Dữ liệu hoặc nhóm Kết quả ở sidebar. Nguồn dữ liệu/kết quả/evidence/export mở từ hội thoại. Giữ manual fallback/deep links để bảo toàn chức năng, không tạo lại menu sáu trang. Một composer và một history Modal; Enter gửi, Shift+Enter xuống dòng, không gửi lúc IME composition. Giữ logo/workspace/header/light blue/font/avatar và responsive 5 widths.

Giữ nguyên bộ 80 gold/rubric; bổ sung 24 biến thể độc lập. Gate full gold: intent/source ≥95%, slots ≥90%, không P0/P1; financial/auth/security/persistence gates không thay. Bằng chứng routing 15: gold 79/80 intent, 59/60 nguồn, 34/34 slots; variants 24/24, 16/16, 10/10; 28/28 negatives an toàn. Một ca gold hỏi lại không cần thiết còn được ghi P2, không tô thành PASS từng ca.

Chủ dự án sau đó cho phép gọi Gemini khi cần để hoàn thành hiệu quả, thay điều kiện dừng 50/50 của prompt đầu. Ceiling được tăng có audit, giữ lịch sử và reservation trước HTTP; default source OFF/0. Không cho phép sửa raw, nới semantic validators, tự approve hoặc tùy tiện gọi Qwen/parser. Kết quả đầy đủ, source/runtime/Git và trạng thái release ở IMPLEMENTATION_STATUS mục T. Ba giai đoạn giữ nguyên.
