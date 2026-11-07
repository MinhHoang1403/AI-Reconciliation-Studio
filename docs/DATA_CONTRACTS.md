# Hợp đồng dữ liệu và API

Định nghĩa thực thi nằm trong `backend/studio/contracts/`. OpenAPI tại `/openapi.json` và `/docs` mô tả request/response; endpoint này không cấp quyền đọc dữ liệu. Error envelope: `code`, `message_vi`, `details` đã redacted, `retryable`, `correlation_id`.

## Mapping tên trường và typed prepared reads — 08/11/2026

`field_name_tokens` chỉ dùng cho đề xuất tên/kiểu, tách khỏi `normalized_name` dùng trong chữ ký nguồn. Nó phân rã Unicode, dấu/case, camelCase, gạch dưới và cụm từ nghiệp vụ Việt–Anh có giới hạn. Từ phủ định, lựa chọn hoặc gross/net xung đột giữ abstention. Tên/kiểu/value profile chỉ tạo shortlist cần review; không chứng minh grain, currency, metric hoặc cấp auto-approval. `profiled_fields` vẫn để khóa, cơ sở tiền, metric và timezone chưa được xác nhận. Không thay giá trị, raw ID, fingerprint hoặc approval lịch sử.

Catalogue typed routing công bố cả `PREPARED` và `PREPARED_FINDINGS` khi có artifact tương ứng. Hai nguồn chỉ dùng xem/đếm dữ liệu chưa duyệt. Với câu chưa khớp grammar native, model chỉ được bind bảng đơn đang chọn, nguồn duy nhất, hoặc một tên tệp chính xác trong ngoặc kép, không dùng gần đúng. Bộ lọc, sort, grouping, metric, currency và phép tổng tiền đều bị chặn ở ranh giới này. Schema provider và validator cùng giới hạn; backend vẫn kiểm membership, project, artifact SHA256, row limit và lineage khi thực thi. Các truy vấn native đã xác định vẫn là chuẩn đối chiếu khi model đưa tham số khác.

Native read resolver gom các phép đọc hiện có; yêu cầu đọc kèm xóa/sửa nguồn bị từ chối toàn bộ. Thiếu nguồn và tổng tiền trên bản chưa duyệt trả `CLARIFY`. Model không được tự thêm phép đếm thuần hoặc lọc `is_null` khi người dùng không yêu cầu; trả câu hỏi xác nhận qua `INPUT_AMBIGUOUS`, giữ trace của đề xuất không hợp lệ. Không sửa JSON sai thành phép tính được thực thi.

UI cho phép người dùng nhập thông tin chung khi có ít nhất hai thẻ mapping, mỗi nguồn chỉ có một field tiền. Phạm vi gồm danh sách review/nonce/fingerprint cụ thể. Người dùng khai báo cùng loại dữ liệu, grain, timezone, basis và metric rồi xác nhận áp dụng. Chỉ điền chỗ thiếu; không đổi khóa hoặc giá trị đã có của từng nguồn. Bản nháp lưu theo actor/workflow/token trong session; payload duyệt gộp cũ bị xóa để chờ kiểm lại từng thẻ. Đây không là approval hoặc quyền reuse; nonce, fingerprint, authorization, preflight, idempotency và audit per-resource giữ nguyên.

## Parser giữ header và dòng vật lý — 06/11/2026

`tabular-2` giữ header có nhãn trùng ở đúng vị trí, cảnh báo EMPTY_OR_DUPLICATE_HEADER và giữ từng cột c1/c2 riêng. Không chuyển dòng dữ liệu đầu thành header chỉ vì tên cột lặp. Với CSV, ParseConfig.header_row là dòng vật lý bắt đầu một bản ghi, cùng đơn vị với provenance; dòng nằm giữa một ô quoted nhiều dòng không phải header hợp lệ. Parser dừng ngay trong lúc đọc khi vượt số bản ghi/cột đã giới hạn; không tích lũy hết file trước khi từ chối. Raw/checksum, parser cũ và các artifact/revision lịch sử không bị viết lại. Parse signature mới tách kết quả mới khỏi cache của tabular-1.

## Bản tự chuẩn bị

Tải CSV/XLSX mới tạo bản tự chuẩn bị cùng lần công bố bảng đã đọc, kể cả khi tắt yêu cầu AI mapping. `TableView.prepared` trả ID của Parquet riêng, ID và revision nguồn, revision xử lý, số dòng và thống kê theo cột. Dữ liệu lịch sử có thể trả null. Tham chiếu lưu trong metadata của artifact đã đọc. Parquet prepared dùng chung loại lưu trữ tabular `parsed` để API liệt kê artifact của bản cũ tiếp tục đọc được.

`kind=prepared` trên preview và `DataQuery.source_kind=PREPARED` dùng ID bảng. Backend kiểm nguồn, quyền và SHA-256 trước khi đọc. Cột ngày ISO được chuyển sang kiểu ngày khi toàn cột khớp ngược chính xác, không có chuỗi rỗng hay cảnh báo trích xuất. Cột có giá trị ngày không hợp lệ giữ chuỗi và trả số lỗi. Preview `kind=prepared_findings` lọc dòng có mã lỗi kèm cột và vị trí nguồn. Giá trị gốc, chuỗi rỗng, null và định danh có số 0 đầu được bảo toàn. Kết quả có phạm vi `EXPLORATION`, `review_required=true`. Phép cộng tiền vẫn cần nghĩa nghiệp vụ đã duyệt.

Job parse có thể điền sẵn bản nháp từ một mapping active cùng workspace, phạm vi nghiệp vụ, chữ ký cột và cấu hình parser. Mẫu có quy tắc mở rộng hoặc nguồn đích có cảnh báo trích xuất sẽ đi theo quy trình review thường. Receipt `reused_templates` liên kết ID bản nháp với ID mẫu. Bản nháp giữ evidence của nguồn đích và tiếp tục qua preflight, review và approval hiện có.

Chủ không gian có thể cấp hoặc thu hồi quyền cho một mẫu cụ thể qua `PATCH /api/mappings/{id}/reuse-policy`. API nhận `enabled` và `expected_enabled`, khóa nguồn và lưu audit. Mặc định tắt. Mẫu cần phê duyệt trực tiếp, canonical hiện hành không lỗi và khóa chuỗi đã xác nhận. Job `mapping_reuse` chỉ tự áp dụng khi đúng dự án, phạm vi, sheet và cấu hình/parser revision. Tên tệp phải giống nhau hoặc chỉ khác một token kỳ `YYYY_MM`/`YYYY-MM` hợp lệ trong cùng mẫu tên. Vị trí cột có thể đổi khi tên cột được gắn lại duy nhất, giữ kiểu/identifier flags và mọi trường đã duyệt. Chỉ cho thêm cột mô tả/ghi chú dạng chuỗi không có dấu hiệu ngày, số, mã hoặc currency; mọi cột khác biệt khác cần review. Tên cột chỉ chuẩn hóa chữ hoa/thường, dấu và dấu phân cách, không fuzzy hoặc suy quan hệ ngữ nghĩa từ giá trị mẫu. Định dạng và currency quan sát được phải tương thích. Preflight kiểm tất cả dòng và khóa duy nhất, sau đó kiểm lại grant, approval, bản nháp và phép gắn cột dưới khóa trước khi công bố mapping và enqueue normalization. Source signature cũ vẫn bất biến; mapping mới lưu signature/evidence của nguồn đích và receipt lưu phép gắn cột.

Với phép chuyển đổi chuỗi, ngày và Decimal trực tiếp, tên cột mới có thể khớp chính xác ID hoặc tên trường đã duyệt của schema đích. Nếu cả tên cũ và tên thay thế đều xuất hiện, hoặc hai cột cần dùng cùng một tên đích, hệ thống yêu cầu review. Các điều kiện về quyền và preflight vẫn áp dụng.

Receipt ghi `APPLIED` cùng ID grant, ID phê duyệt gốc và ID mapping được áp dụng. Audit `APPLY_APPROVED_MAPPING` ghi actor `system`. Mapping kế thừa người và thời điểm phê duyệt gốc. Mẫu được áp dụng bởi hệ thống không cấp quyền tái áp dụng tiếp. Khi không đủ điều kiện, job trả `REVIEW_REQUIRED` và giữ bản nháp, dữ liệu gốc và bản prepared.

Khi gửi tệp trong Chat mà không nhập câu hỏi, client gửi `PREPARE_UPLOAD` với danh sách dataset vừa nhận. Agent đợi parse, hiển thị bản xem trước và tạo thẻ từ profile đã kiểm checksum. Job dùng preflight để đề xuất định dạng ngày, cách ghi số và currency quan sát được. Ý nghĩa khoản tiền, múi giờ, khóa nghiệp vụ và grain còn thiếu được giữ ở trạng thái cần xác nhận. Mỗi nguồn đi qua cùng đường duyệt, nonce, fingerprint và khóa bảng hiện có. Workflow chờ job tái sử dụng hoặc chuẩn hóa đang chạy của cùng bảng. Bảng trên 40 cột vẫn xem được trong Chat và có hướng dẫn mở công cụ chi tiết. Tuyến chuẩn bị này chạy không cần kết nối model.

Planner lưu tối đa năm `PlanningCandidate` trong receipt job. Mỗi ứng viên có ID từ bản kế hoạch, số khóa đối ứng, số khóa phân biệt và số dòng đủ điều kiện ở hai phía. Plan chứa grain, cardinality, cơ sở tiền, currency, kỳ và coverage. Khi số khóa đối ứng của hai ứng viên dẫn đầu bằng nhau, thẻ hỏi chọn khóa và chưa điền plan mặc định. Lựa chọn chỉ điền bản nháp. Luồng xác nhận nguồn, tách dòng lỗi và duyệt quy tắc tiếp tục qua API hiện hành.

Câu đối soát nêu chính xác hai tên tệp trong dấu ngoặc kép có thể xác định nguồn tham chiếu và nguồn đối ứng theo thứ tự. Chat yêu cầu kỳ và độ phủ còn thiếu. `POST /api/agent/workflows/{id}/draft` nhận `check_planning_scope: true` kèm `planning_request` và token của thẻ. Server kiểm khóa nguồn, quyền, revision và dữ kiện cần thiết trước khi xếp job tìm khóa. Thẻ cũ hết hiệu lực và thẻ kế hoạch mới vẫn yêu cầu người dùng duyệt trước khi chạy.

Batch `POST /api/agent/workflows/{id}/decisions/batch` nhận hai hoặc ba thẻ mapping đã hiển thị. Từng thẻ giữ payload, nonce, fingerprint và audit riêng. Server khóa theo thứ tự bảng, kiểm lại từng thẻ và dùng cùng đường phê duyệt. Mọi quyết định và lần xếp job đầu tiên nằm trong một transaction. Thẻ không hợp lệ làm cả lần gửi thất bại.

Khi chuẩn hóa ở màn hình thủ công công bố thành công, cùng transaction xếp `agent_resume` cho các workflow đang chờ mapping tương ứng. Lượt tiếp nối này chỉ đọc canonical hiện hành của cùng workspace/project và kiểm quyền actor lại. Nó khóa nguồn theo thứ tự, chuyển thẻ cũ sang `INVALIDATED`, giữ nguyên draft và thêm bằng chứng về bản chuẩn hóa đã được duyệt. Audit `AGENT_REVIEW_INVALIDATED` ghi actor `system`. Các thẻ chưa có canonical tiếp tục chờ xác nhận. Lượt này không gọi model, duyệt mapping, chạy chuẩn hóa hoặc đối soát. Worker khởi động lại kiểm các workflow cũ để phục hồi cùng tín hiệu theo khóa idempotency của tập canonical hiện hành. Workflow đã hủy, hội thoại đã xóa, quyền không còn phù hợp hoặc canonical đã stale không được tiếp tục.

Danh mục `GET /api/projects/{id}/canonical-catalogue` trả tối đa 200 mục mỗi trang và `next_cursor`. Truyền `after_id` để đọc trang kế tiếp, hoặc `canonical_ids` để lấy tối đa năm ID cụ thể trong cùng phạm vi. Danh mục mẫu quy tắc `reconciliation-templates` dùng cùng kiểu cursor, mặc định 100 mục. Các bộ chọn tải tiếp các trang metadata. Backend kiểm cặp canonical được yêu cầu bằng ID trực tiếp, độc lập với giới hạn trang danh mục.

Yêu cầu xuất bảng đang xem ghim truy vấn của trang kết quả đã xác minh trong cùng hội thoại. Cache bao gồm người yêu cầu, run, định dạng và tham số truy vấn. Worker kiểm lại quyền, chạy cùng Query DSL và xuất đúng trang đang xem. Tệp ghi rõ số dòng, query và snapshot toàn run, tách khỏi phạm vi của trang xuất. Báo cáo đầy đủ của run giữ định dạng cũ.

`DataQuery.source_kind=PREPARED_FINDINGS` đọc dòng có cảnh báo ngày do bản tự chuẩn bị ghi nhận. ID nguồn là ID bảng. Kết quả giữ nguyên giá trị gốc, nhãn cột và vị trí dòng, mang phạm vi khám phá như `PREPARED`. Số đếm là số dòng có cảnh báo, kể cả khi một dòng có nhiều cột bị lỗi. Khi chưa chọn được đúng một bảng, Chat yêu cầu chọn nguồn trước.

Các lệnh tường minh như “Cho tôi xem ba nhóm lệch tiền lớn nhất” dùng query xác định trên run hiện hành. Backend chỉ lấy nhóm `AMOUNT_MISMATCH`, sắp xếp theo chênh lệch tuyệt đối giảm dần và dùng `group_id` tăng dần để phân giải giá trị bằng nhau. Chỉ tiêu lấy từ hợp đồng đã duyệt. Lệnh “Giải thích nhóm thứ hai” gắn với nhóm ở vị trí đó trong trang đã lưu của cùng run, hoặc hỏi lại nếu thiếu trang.

Planner kiểm ứng viên khóa chính xác trên canonical đúng kỳ, với tối đa 20.000 dòng tổng và sáu trường định danh mỗi phía. Số khóa trùng và số lần xuất hiện mỗi khóa chỉ dùng để chọn bản nháp. Trường tiền phải trùng chỉ tiêu, cơ sở tiền, đơn vị và currency đã duyệt. Trường hợp chỉ một ứng viên tốt nhất và vượt validator, bản nháp có nguồn `DETERMINISTIC`. `AI_PLAN_MISSING` được giữ trong trace và receipt, đồng thời trả bản nháp cần xác nhận với các dữ kiện còn thiếu. Hợp đồng duyệt và chạy đối soát giữ nguyên.

## Review dùng chung và khôi phục bản nháp — 06/11/2026

Nguồn sự thật của thẻ review là `AgentWorkflowRow.detail.reviews`, tách khỏi proposal ánh xạ thủ công và approval bất biến. `GET /api/agent/tables/{table_id}/mapping-reviews` trả tối đa10 workflow có thẻ MAPPING OPEN đúng bảng, project, workspace và actor, loại hội thoại đã xóa. Chat và Dữ liệu phải đọc cùng thẻ này; không lấy proposal thủ công làm bản thay thế ngầm.

Nguồn chuẩn hóa `PARTIAL` được chọn để tạo đề xuất đối soát mới trong Chat. `PlanReviewDecision.invalid_rows_reviewed` yêu cầu người dùng xác nhận đã xem các dòng lỗi bị tách trước khi duyệt và chạy phần hợp lệ. Workflow mở review riêng khi có nguồn `PARTIAL` và giữ cổng từ chối nguồn chưa dùng được. Cờ này độc lập với `ReconciliationPlan.allow_partial` dành cho độ phủ thời gian. Việc tái gửi quyết định cũ giữ tương thích digest. Review đối soát lấy khóa bảng trước bản chuẩn hóa theo cùng thứ tự với duyệt ánh xạ để tránh chờ khóa vòng tròn.

`POST /api/agent/workflows/{id}/draft` nhận ReviewDraftUpdate: review_id/nonce/fingerprint và đúng một draft, plan hoặc planning_request cùng loại. Lưu bản nháp không tạo approval, canonical hay job AI. Mapping kiểm lại toàn bộ cột với profile; planning kiểm source và những facts đã cung cấp, plan hoàn chỉnh kiểm business contract. Nguồn/nonce cũ, hết hạn, viewer hoặc reply còn chạy bị chặn. Lưu thành công đổi nonce và gia hạn30phút; gửi nonce cũ trả409, client cần đọc bản hiện hành. `POST .../renew-review` là hành động người dùng để mở lại thời hạn; chỉ được gia hạn khi nguồn/fingerprint còn nguyên, không bỏ qua stale-source gate.

`POST /api/mappings/{id}/approve` dùng Idempotency-Key theo actor/workspace. Gửi lại cùng key và nội dung trả nguyên snapshot approval đã lưu, kể cả revision đó được thay thế sau này; nội dung khác cùng key trả409. Advisory transaction lock và audit receipt được công bố cùng approval; không tạo bảng hoặc queue giả. Client cũ thiếu header vẫn tương thích nhưng không có receipt chống gửi lặp. Reject/approve cùng khóa bảng và đọc lại proposal sau khóa để tránh trạng thái cũ.

## Smart Mapping local và lựa chọn ban đầu — 05/11/2026

Adapter local dùng `MappingSemantics` nội bộ: entity, grain, tham chiếu khóa và nghĩa tiền. Schema giới hạn tham chiếu theo cột của bảng hiện tại; Backend vẫn từ chối cột sai/trùng. Backend tạo đầy đủ `NormalizationDraft` từ profile rồi dùng cùng assessment, preflight và approval. Đây là thay đổi cách chuẩn bị đề xuất; public draft, compiler, Decimal, Matcher và Verifier giữ nguyên. Grain unknown không được mang khóa suy đoán. Tham chiếu có thật chưa chứng minh khóa hoặc grain đúng nghiệp vụ.

Tin nhắn có tệp đính kèm mang `dataset_ids` của đúng lần tải. Resolver local chỉ nhận lệnh chuẩn hóa explicit, kiểm toàn câu và exact scope; câu phủ định hoặc nhiều hành động không thuộc grammar tiếp tục qua router. Lỗi một đề xuất giữ những thẻ đã mở của nguồn trước để người dùng tiếp tục duyệt, không tạo lại các đề xuất đã nhận.

`AssistantModelOption.preferred` mặc định false, là trường additive từ cấu hình `ASSISTANT_DEFAULT_MODEL`. Frontend chỉ chọn model ưu tiên khả dụng khi chưa có lựa chọn cá nhân. Model vẫn được đóng vào payload/job; đổi bộ chọn không đổi lần gửi chưa rõ phản hồi hoặc job đã nhận. Không có fallback cloud tự động.

Khóa được chọn trong Chat draft vẫn là trường required theo contract hiện có. Trường khóa của màn hình thủ công có thể không required. So kết quả giữa hai đường phải kiểm cả điều kiện này: bản duyệt Chat của bộ ba nguồn báo thêm bốn dòng thiếu khóa, không phải phát sinh lỗi ngày hoặc mất dữ liệu. Số liệu và oracle từng cấu hình tại báo cáo mục AH.

## Ngày và kiểm chứng Mapping Review — 05/11/2026

`normalization-2` chấp nhận ba alias hiển thị hữu hạn: `YYYY-MM-DD`/`DD/MM/YYYY`/`MM/DD/YYYY` tương đương `%Y-%m-%d`/`%d/%m/%Y`/`%m/%d/%Y`. Không đoán thứ tự ngày/tháng. Compiler và transform kiểm cấu hình trước khi lặp dòng: `DATE_FORMAT_INVALID`, `TIMEZONE_INVALID`, `TIMEZONE_DATABASE_UNAVAILABLE` dừng tác vụ, không tạo hàng nghìn INVALID_DATE. Ngày sai thật là INVALID_DATE; DST mơ hồ/không tồn tại có mã riêng; timestamp có offset phải khớp vùng đã duyệt. Date-only vẫn theo contract timestamp UTC, đối chiếu calendar date sau khi chuyển về múi giờ đã duyệt. Không sửa canonical lịch sử; lần chạy mới dùng revision mới.

ColumnProfile thêm `observations` mặc định rỗng, đọc tương thích hồ sơ cũ. Toàn cột có counts định dạng ngày/locale, zero-prefix, số âm/0 và currency codes cho phép; không gửi raw samples mới ra cloud. Agent làm mới hồ sơ từ parsed artifact đã kiểm checksum trước inference; `agent-normalization-5` yêu cầu định dạng Python, không lấy uniqueness/cột customer làm bằng chứng khóa giao dịch. Context bổ sung phạm vi nghiệp vụ/yêu cầu và tối đa3mẫu đã duyệt cùng workspace/scope/signature. Facts từ mẫu chỉ điền lại khi grain/entity/source-target/transform còn tương thích; luôn cần approval riêng cho nguồn mới. Backend enrich chỉ bản đề xuất; không suy timezone/gross-net của amount mơ hồ hoặc currency từ đa số. Chuỗi số có hai locale cho giá trị khác nhau phải hỏi, còn số nguyên cho cùng Decimal có thể đề xuất en-US tương đương.

`POST /api/agent/mapping-preflight` nhận NormalizationDraft, trả MappingAssessment có số dòng/trường đã kiểm, câu hỏi còn thiếu, lỗi từng cột và số dòng dự kiến lỗi khi đủ cấu hình. `POST /api/tables/{id}/mapping-preflight` nhận ApprovalInput cho màn hình thủ công, trả NormalizationPreflight. Cả hai đọc scoped/checksum, dùng compiler/transform trong bộ nhớ, không ghi approval, job hay artifact. Mọi API duyệt kiểm lại, kể cả client bỏ qua preview. Transform lỗi toàn cột bị chặn trước approval. Nonce/fingerprint/TTL/idempotency/authorization và xác nhận cảnh báo extraction vẫn bắt buộc; trường khóa được duyệt trong draft là required, không biến thiếu mã thành khóa hợp lệ.

RelatedKeyCheck chỉ đo overlap/duplicate/thiếu khóa cho vai trò tham chiếu/lô và scope khi có; đây là quan hệ tiềm năng, không tự duyệt cardinality hoặc chạy đối soát. Nguồn nhiều currency vẫn theo giới hạn field tiền đơn tiền tệ: phải chọn có ý thức, giá trị khác giữ CURRENCY_MISMATCH và raw lineage; không đổi tiền hoặc loại dòng. Review mặc định hiển thị tóm tắt/điểm cần xác nhận/bất thường; chỉnh chi tiết mở khi cần. Kết quả kiểm tra gắn đúng draft hiện tại; sửa draft khóa nút duyệt tới khi kiểm lại.

## Trạng thái chuẩn hóa và phản hồi kết thúc — 04/11/2026

`CHECK_DATASET_STATUS` là intent chỉ đọc metadata, không chuẩn hóa và không đọc số tiền. `read_processing_status` kiểm workspace/project, nguồn explicit hoặc ngữ cảnh, phiên bản cao nhất, bảng, ánh xạ đang dùng và revision chuẩn hóa hiện hành. DTO nội bộ `ProcessingStatus` giữ dataset/table/version/mapping/canonical refs và trạng thái `UPLOADED/PARSING/PARSE_FAILED/PARSED/MAPPING_REVIEW/MAPPED/READY/PARTIAL/FAILED/STALE`. Các trạng thái này chỉ thuộc DTO này; không thêm chúng vào enum Dataset hay Run. READY của nguồn không chứng minh contract readiness, coverage hoặc kết quả đối soát. Không phụ thuộc VerifiedRun. Hỏi mơ hồ trả clarification, không lấy hai nguồn đầu tiên khi có nhiều nguồn. Giới hạn ngữ cảnh được giữ; không dùng lịch sử văn bản để chứng minh trạng thái hiện hành.

Gate câu hỏi trạng thái không nhận yêu cầu đề xuất/chuẩn bị/thiết lập/thực hiện/chỉnh sửa có mệnh đề “nếu chưa rõ” hoặc “khi đã đọc xong”. Từ đã/chưa trong mệnh đề phụ không biến lệnh chuẩn hóa thành câu hỏi chỉ đọc. Những câu này tiếp tục router hành động và các cổng phê duyệt, không trả trạng thái rồi giả là đã thực hiện đề xuất.

Yêu cầu kiểm tra hai nguồn trong phạm vi có số nguồn khác hai trả clarification; không hoàn tất câu hỏi bằng trạng thái của riêng nguồn đang xem. Người dùng có thể chọn **Đổi ngữ cảnh phân tích → Dùng dữ liệu của dự án** để mở hội thoại ở phạm vi dự án. Thao tác chọn phạm vi không ghi dữ liệu, không gọi AI và giữ hội thoại/bản nháp riêng của từng phạm vi.

`MessageView` thêm `job_status` và `error_code` nullable, additive, đọc từ job cùng scope. Terminal failure của câu hỏi/Agent/reply công bố tối đa một assistant message với UUID ổn định và constraint `(job_id, role)`, cùng transaction với lỗi; chỉ dùng thông báo đã redacted. Không hồi sinh hội thoại đã xóa hoặc quyền đã thu hồi. Lỗi unknown delivery/rate limit không tự gửi lại; lỗi kỹ thuật giữ trạng thái lỗi, không giả success. Exhausted lease thông báo kết thúc và giải phóng pending reply đúng workflow. Lịch sử lỗi cũ chưa có assistant reply vẫn hiển thị lỗi từ job DTO, không sửa nội dung lịch sử gốc. Phản hồi mới đã lưu không bị lặp thành hai thông báo lỗi trên giao diện.

Khi hết lần phục hồi lease, parse job chuyển nguồn sang FAILED; reconciliation job chưa có snapshot chuyển run sang BLOCKED, cùng transaction với terminal job và thông báo workflow. Không giữ nguồn/run ở trạng thái đang chạy vô hạn. Phía trình duyệt tiếp tục GET theo dõi job chậm sau đợt polling ban đầu, giảm nhịp xuống hai giây; rời/đổi hội thoại dừng theo dõi. GET này không gửi lại yêu cầu provider hoặc tăng số lần thực thi nghiệp vụ.

`resolve_plain_listing` có đường preview nhiều nguồn chỉ đọc [D]: lời yêu cầu xem/kiểm tra không có filter/tiền/kỳ/phép tính, dùng nguồn trong catalogue hiện tại. Yêu cầu “hai nguồn” chỉ thực hiện khi đã xác định đúng hai; số lượng khác hỏi lại, không chọn hai nguồn đầu. `EXPLORE_DATA` đọc bảng gốc, không đưa ra kết luận tiền hoặc bỏ approval. Bộ lọc, thời gian và hành động tài chính vẫn qua typed router/validator; output model thừa/thiếu intent tiếp tục bị từ chối. Regression D07 không hợp thức hóa output hai intent thành một; đường preview xác định tránh gọi model cho yêu cầu chỉ đọc này.

## Hội thoại: bổ sung thông tin và phê duyệt — 03/11/2026

`ReviewRequest.kind` quyết định hành vi, không phân loại bằng CSS. `CLARIFICATION` nhận `options` optional (mặc định rỗng): mỗi lựa chọn do server tạo gồm id/label/typed intent của metric đã duyệt. Chọn qua decisions hoặc trả lời qua replies đều giữ owner/project/conversation/nonce/fingerprint/expiry, idempotency và pending-job guards. Lựa chọn có options phải khớp nguyên intent được cung cấp; không dùng một lựa chọn để đổi nguồn/filter tùy ý. Không gắn `user_confirmed=true` cho câu chat.

Reply của clarification dùng catalogue scoped thật, mục tiêu gốc và câu trả lời mới để kiểm intent. Đủ dữ kiện thì ghi `AGENT_CLARIFICATION_ANSWERED` và advance trong cùng transaction; không ghi mapping/contract approval. Còn mơ hồ thì giữ OPEN và hỏi tiếp. MAPPING/RECONCILIATION replies vẫn chỉ sửa preview, xoay nonce và chờ nút duyệt chuyên biệt. Reply messages liên kết lại workflow gốc; FE chỉ render panel ở phản hồi mới nhất để tránh lặp.

`resolve_verified_metric` không tính tiền: chỉ bind DataQuery vào metric của immutable approved contract. Unique metric giải quyết money fields trước query-field validation; nhiều metric chưa có lựa chọn trả `QUERY_METRIC_AMBIGUOUS`, không có metric trả `QUERY_METRIC_UNAVAILABLE`. Explicit metric sai trả `QUERY_SEMANTICS_REQUIRED`; field lạ vẫn `QUERY_FIELD_INVALID`. Input query không bị mutate; QueryResult.query ghi lựa chọn thực đã thực thi. Tổng/count, Decimal/null, currency và native verification không đổi. QueryResult thêm `field_labels` optional lấy từ schema/header có thật.

`IntentCatalogue` thêm previous_query/previous_goal/previous_groups và pending_question (internal, bounded); chỉ lấy kết quả đã lưu cùng actor/conversation/project và nguồn còn hợp lệ, không chọn latest của project. AgentIntent/RoutingIntent thêm `result_position` optional, 1–50, chỉ cho EXPLAIN_RESULT, không đi cùng business key; phải nằm trong trang VERIFIED_RUN của đúng current run. Mã nghiệp vụ vẫn qua exact lookup.

`POST /api/agent/workflows/{id}/query-pages` nhận DataQuery của TableBlock đã lưu, chỉ cho thay offset/sort. Authorization/CSRF và query validation được kiểm lại. Lưu WorkflowState.query_selection gồm query và tối đa50group IDs cho follow-up; không sửa original blocks, run, MetricSnapshot hoặc lịch sử nguồn. UI khôi phục trang đã lưu khi reload. Endpoint `/api/agent/queries` hiện có giữ tương thích. Không migration mới; fields JSONB additive có defaults, workflow lịch sử tiếp tục đọc được.

Typed intent thêm gate phân biệt sort và filter: yêu cầu liệt kê nhóm lệch tiền phải có comparison_state AMOUNT_MISMATCH, kể cả khi sort absolute_variance đúng. Tổng delta/absolute_variance toàn run không filter/group trả SUMMARIZE_RESULTS từ MetricSnapshot; phân tích có phạm vi riêng vẫn query native. Việc chuyển sang snapshot diễn ra sau kiểm metric/source, không hợp thức hóa ID bịa. Query rows của verified run giữ thêm business_key chỉ để trình bày/evidence; không cho query tự chọn business key kỹ thuật hoặc mở join mới. UI ẩn UUID và hiển thị vị trí/khóa giao dịch; row provenance vẫn nguyên.

Source aliases lấy từ chữ cái độc lập thực có trong filename và phải duy nhất giữa datasets; không gán A/B theo thứ tự upload. Plain listing fast path chỉ áp dụng một bảng, không filter/kỳ/tiền; câu phức tạp vẫn qua router. Yêu cầu tự phê duyệt/bỏ tiền tệ bị từ chối trước model trong workflow thật. Yêu cầu chọn tệp tên gần giống bị giảm xuống CLARIFY, không được biến thành reuse current run. Đây là policy từ chối/giảm quyền, không sửa proposal tài chính thành hành động được phép.

## Assistant: tools và facts

API bổ sung: `POST /api/assistant/tools`, `POST /api/conversations`, `GET /api/conversations?project_id=...`, `GET /api/conversations/{id}`, `DELETE /api/conversations/{id}`, `POST /api/assistant/messages`. Create/message dùng `Idempotency-Key`; message trả job ID để resume bằng GET, không gửi lại provider. GET hỗ trợ limit 1–50 và `before_id` thuộc đúng project/hội thoại. Context và text khác với key cũ trả 409. Conversation/message output có source context riêng; hội thoại khác actor/project/workspace hoặc đã xóa trả 404.

`GET /api/projects/{id}/reconciliation-plans` phân trang các kế hoạch chưa được duyệt do actor tạo, để tiếp tục workflow sau khi đóng panel. `POST /api/reconciliation-contracts/{id}/reuse` giữ contract cũ và thêm Idempotency-Key optional để tương thích client cũ; cùng key/nội dung trả cùng proposal, nội dung khác 409. Kết quả vẫn cần review/approval hiện có. Assistant không có tool approve/run hoặc quyền suy ra năm, coverage, tiền hay rule tài chính.

`AssistantContext` luôn có project; group/case bắt buộc explicit run. Bảy `ToolName` ở kế hoạch §34 là allowlist đóng, input không nhận SQL, code hoặc đường dẫn. Mỗi truy xuất kiểm workspace/project/run, output typed và có giới hạn trang; PostgreSQL statement timeout 2,5 giây, DuckDB evidence query 3 giây, nhóm tối đa 100 nguồn evidence cho Assistant. Nhóm lớn hơn bị chặn với EVIDENCE_LIMIT; UI bằng chứng hiển thị tối đa 100 thành viên/20 ô gốc, báo cáo giữ lineage đầy đủ. Chưa có phân trang toàn bộ evidence trong UI.

`AnswerFactSet` có content hash, context, trạng thái verification, nguyên bản MetricSnapshot, rule ID/revision, facts và source references (run/snapshot/group/member/file/table/sheet/row). Facts tiền và tỷ lệ chỉ sao chép từ snapshot/comparison đã verified; không tính lại KPI. ID giả, run khác, snapshot/rule không khớp phải bị từ chối. FactSet cũ giữ nguyên run cũ, không được gắn làm kết quả mới.

## Handoff

| Đối tượng | Ref/API | Bất biến |
| --- | --- | --- |
| `FileArtifact` | Raw artifact thuộc `DatasetVersion` | SHA256 trên bytes gốc; owner/workspace; không path do client cung cấp |
| `ParsedTableArtifact` | `GET /api/datasets/{id}/tables` | Cột c1/c2 có tên/vị trí nguồn; row identity độc lập business key; warnings không mất |
| `DatasetProfile` | `GET /api/tables/{id}/profile` | Thống kê bằng code; evidence từng cột; không bịa grain |
| `SchemaDefinition` | `GET /api/schemas/{id}` | Schema có ID/revision/workspace, fields có kiểu, grain và entity do người dùng xác nhận |
| `SchemaProposal` | `GET /api/mapping-proposals/{id}` | Gợi ý chưa được duyệt; UNKNOWN/AMBIGUOUS được giữ |
| `MappingRevision` | `POST /api/mappings/{id}/approve` | Approval mới luôn có ID/revision/actor/time; không ghi đè quyết định cũ |
| `CanonicalDataset` | `GET /api/canonical-datasets/{id}` | Artifact/errors refs, quality, mapping và normalization revision; `stale` độc lập chất lượng lịch sử |
| `EvidenceRef` | `GET /api/evidence/{table_id}:{column_id}?row=3` | Scope từ table đã authorize; file/sheet/physical row/column; formula/cache có metadata |
| `WorkspacePolicy` | `GET /api/settings` | Local-only và cloud budgets mặc định 0 |
| `JobStatus` | `GET /api/jobs/{id}` | QUEUED/RUNNING/RETRYABLE_FAILURE/BLOCKED/SUCCEEDED/FAILED/CANCELLED; mã lỗi và attempts |

Giai đoạn sau phải dùng các refs và API này, không viết parser/mapping thứ hai. DTO không truyền DataFrame hoặc JSON LLM không kiểm tra.

## REST đang hỗ trợ

`GET /api/settings` bổ sung `ai_task_allowances` gồm `agent`, `planner`, `assistant`, mỗi mục có `workspace_used`, `configured_ceiling`, `remaining`. Remaining là min của task lifetime ceiling còn lại, global còn lại và workspace còn lại, hoặc0khi policy cấm; không phải bằng chứng provider khỏe hoặc cấp quyền approve. DTO chỉ đọc, không gọi model/reset ledger hoặc thêm migration. History errors/loading chỉ trình bày trong modal theo project hiện tại; tên tìm kiếm nói rõ chỉ các hội thoại đã tải.

`GET /api/settings` bổ sung `agent_max_upload_files` và `agent_upload_extensions`: số tệp chat là `min(max_upload_files, 5)`, dùng cùng cấu hình với `POST /api/agent/attachments`. Composer đọc giới hạn này và `max_upload_bytes`, không hardcode. Giới hạn upload thủ công `max_upload_files` giữ nguyên. Settings phân biệt quyền/cấu hình với `cloud_live_status`; GET không gọi provider. Bổ sung chỉ đọc, không migration hoặc thay contract tài chính.

Project purpose là metadata hiển thị `WORK/TEST/UNKNOWN`, mặc định UNKNOWN cho project lịch sử chưa có quyết định. Dùng audit append-only `PROJECT_CLASSIFIED_WORK/TEST/UNKNOWN` theo workspace/resource ID; sự kiện mới nhất theo created_at/id là phân loại hiện hành. Không cần migration/cột mới, không suy ra nhóm từ tên. `POST /api/projects` mặc định WORK, nhận classification explicit; tạo TEST/UNKNOWN cần owner. `PATCH /api/projects/{id}/classification` chỉ owner, bắt buộc classification và expected_classification; khóa project/so trạng thái cũ, conflict409, no-op không thêm audit. Không invalidate nguồn/mapping/run hoặc đổi quyền truy cập. `GET /api/projects?include_test=false` lọc TEST trước search/offset/limit và count; UNKNOWN/WORK vẫn hiện. API giữ include_test=true khi bỏ tham số để tương thích clients cũ; UI gửi false mặc định. GET theo ID tiếp tục đọc TEST theo quyền, độc lập bộ lọc.

`GET /api/datasets` sắp xếp created_at DESC, id ASC ổn định. Dashboard dùng riêng offset0/limit5, độc lập offset25 của danh sách Dữ liệu; cùng scoped API, không endpoint hoặc business state mới. Loading/error riêng, abort khi đổi project/page; refresh/upload/job completion cập nhật summary rồi danh sách gần đây.

- `GET/POST /api/projects`, `GET /api/projects/{id}/summary`.
- `GET /api/projects?search=...&offset=0&limit=20` tìm literal theo tên/phạm vi, không phân biệt hoa/thường, giữ Unicode và workspace scope; max search200/limit100, thứ tự created_at DESC/id ổn định. `GET /api/projects/{id}` khôi phục saved project ngoài trang đầu; missing/khác workspace cùng404, không lộ metadata. Không tải toàn bộ danh sách vào frontend.
- `GET /api/datasets?project_id=...&offset=0&limit=25`, `POST /api/datasets/uploads` (multipart nhiều tệp).
- `GET /api/datasets/{id}`, `/tables`, `/artifacts`.
- `GET /api/tables/{id}/profile`, `/mappings`, `/preview`.
- `POST /api/tables/{id}/mapping-proposals` với `Idempotency-Key`.
- `POST /api/mappings/{id}/approve`, `/reject`.
- `POST /api/datasets/{id}/normalize` với `Idempotency-Key` và mapping ID cụ thể.
- `GET /api/schemas/{id}`, `/canonical-datasets/{id}`, `/mapping-proposals/{id}`.
- `GET /api/jobs?project_id=...`, `/jobs/{id}`, `/evidence/{id}`.
- `GET /api/session`, `/api/settings`, `/api/live`, `/api/ready`.
- `GET /api/datasets/{id}/documents` trả `DocumentArtifact` scoped: artifact ref/checksum, `FileArtifact` nguồn và `DocumentExtraction` với pages/items/bbox/usage. Không tự tạo canonical từ extraction.

Preview dùng `kind=raw|parsed|canonical|errors`, `offset`, `limit` tối đa 100 và `search` literal. Canonical/errors bắt buộc `canonical_id` cụ thể. `raw` là preview lexical values đọc từ raw artifact, không phải tải raw bytes ra browser. Tìm kiếm/phân trang thực hiện trên backend; tiền trả chuỗi Decimal chính xác.

Dashboard đếm từ `/projects/{id}/summary`, không tự tính KPI hoặc suy đoán kết luận nghiệp vụ. Dataset list có phân trang 25 nguồn/trang. Metadata lists nhỏ như projects/mappings có giới hạn API theo phạm vi hiện tại.

Quality hardening bổ sung additive `partial_canonical_count`, `stale_canonical_count`, `failed_canonical_count` (đếm artifact; stale tách riêng khỏi chất lượng hiện hành), `preparation_action` và `latest_verified_run_id` vào summary; fields cũ giữ nguyên. Mapping review = bảng không active mapping, job active chỉ QUEUED/RUNNING/RETRYABLE_FAILURE. Action chỉ điều hướng/refresh, không cấp quyền mutate: WAIT → failed dataset → REVIEW_MAPPING → NORMALIZE khi không current canonical → REVIEW_DATA cho PARTIAL/FAILED → RECONCILE khi có ít nhất hai READY → UPLOAD. Cùng ưu tiên chọn theo dataset created_at/id và table id; trả một target có dataset/table/canonical IDs scoped kể cả ngoài trang datasets hiện tại. READY không chứng minh hai nguồn tương thích metric/grain; approval/readiness/verification gates không đổi. Latest verified run chỉ gồm VERIFIED/PARTIAL_VERIFIED đúng project, dùng cho link lịch sử.

## Canonical record

Core có `canonical_record_id`, `dataset_version_id`, `source_table_id`, `source_row_id`, `workspace_id`, `entity_kind`, `business_key_components`, `source_provenance`, `mapping_revision`, `normalization_revision`, `quality_flags`, `invalid`, `record_payload`.

`business_key_components` là danh sách có kiểu `{field, value}`, có thể rỗng khi chưa định nghĩa business key; không dùng technical source ID thay khóa nghiệp vụ. `record_payload` là struct Parquet có chuỗi/Decimal/datetime theo schema. Ngày được chuyển sang UTC sau khi người dùng xác nhận format/timezone; không đoán timezone. Thời gian local DST mơ hồ/không tồn tại bị từ chối. Cả schema và DSL revision cho phép tái lập phép biến đổi.

Row identity tạo từ file/table/physical source row. CSV có quoted newline vẫn giữ physical start row. Source provenance chứa đủ thành viên khi nhóm. Bản ghi nhóm có group source ID kỹ thuật và danh sách lineage đầy đủ. AST đã duyệt nằm trong MappingRevision, không lặp toàn bộ transform JSON trên từng ô.

## Gates và revision

1. Upload kiểm tra size, extension/MIME/signature, ZIP/XML/embedded content; streaming SHA256. Một file tối đa 20 MiB, 10 file/lần; mỗi bảng 100k dòng/200 cột mặc định.
2. CSV đọc strings nghiêm ngặt UTF-8/BOM; Windows-1258 chỉ khi chọn rõ. XLSX dùng fastexcel kiểm tra cấu trúc và XML/openpyxl metadata để giữ lexical numbers/zero formats/formula cache. Không chạy formula.
3. Header lệch dòng, sheet ẩn, merged cells/formula/date serial phát sinh warnings và cần xác nhận extraction trước approval. Một sheet là một table candidate; chưa tự tách nhiều bảng cùng sheet.
4. Proposal kiểm tra field/evidence tồn tại, type, allowlist và semantics. AI không thể trả APPROVED. Tiền Total không tự suy ra gross/net.
5. Approval kiểm tra quyền, grain/entity, required fields, Decimal locale/metric/basis/currency/unit; tạo immutable revision. Mapping trước thành SUPERSEDED; canonical phụ thuộc thành stale; raw/parsed giữ nguyên.
6. Normalize nhận approved active mapping. READY/PARTIAL/FAILED là chất lượng chuẩn hóa; **không** đồng nghĩa đủ điều kiện đối soát tài chính. Rule/coverage/cardinality/period là gate giai đoạn sau.

`GET /api/settings` trả `mapping_ai_provider`, `gemini_model`, boolean `gemini_configured`, `gemini_requests_used` và `gemini_requests_remaining` trong scope workspace; không trả API key. Remaining là min của hạn mức global/workspace còn lại sau durable audit reservations, bằng 0 khi cloud không được phép. `JobView.result.source` phân biệt `GEMINI`, `QWEN`, `APPROVED_TEMPLATE`; success chỉ có nghĩa proposal qua validator, chưa được người dùng approve. Reservation đếm HTTP attempts kể cả lỗi; không phải chi phí tiền tệ hoặc số proposal thành công.

Upload lại cùng project/hash/parser config tái sử dụng dataset và raw. Cùng bytes ở project khác không reuse file ref. Chữ ký mapping gồm tên/thứ tự cột, type candidates, identifier flags; lookup còn yêu cầu workspace và business scope. Template được đưa lại dưới dạng đề xuất cần review, không auto-approve số tiền hoặc dữ liệu mới.

Upload nhận thêm form `request_ai_mapping` (mặc định true). False giữ nguyên parse/profile/manual proposal nhưng không enqueue AI; đây là lựa chọn workflow, không phải parse config để phá cache. Với PDF/DOCX, parser revision riêng `llamaparse-cost-effective-1`, page cap 2, artifact JSON bất biến có chất lượng `UNVERIFIED_EXTRACTION`. WorkspacePolicy bổ sung `parser_allowed_sha256` mặc định rỗng, tối đa hai hash. Dữ liệu policy cũ vẫn đọc được theo defaults; không đổi schema PostgreSQL vì policy đã là JSONB. Cache document được đọc/reuse sau khi quyền tạo job đã bị thu hồi.

## DSL

Allowlist có `cast_string_preserve`, `trim_if_approved`, `parse_decimal`, `parse_date`, `normalize_enum`, `coalesce_with_rule`, `add_fields`, `subtract_fields`, `aggregate_by`. Pydantic discriminated union từ chối operation/params lạ, Python/SQL không được thực thi.

Giao diện cung cấp giữ chuỗi/trim được duyệt, Decimal locale và date format/timezone. Enum, coalesce, arithmetic và aggregation có API contract với `ApprovedTransformRule`; cần rule ID, nguồn và bằng chứng phù hợp, quyền editor. UI chưa có trình soạn các rule nâng cao này. Không tự tạo công thức phí hoặc FX.

Null/empty khi parse Decimal tạo null, giữ raw và `value_state=NULL`; chuỗi sai tạo null kèm lỗi `INVALID`. Zero hợp lệ là Decimal zero. Không ghi lỗi thành 0, không bỏ dòng. Required null hoặc conversion error làm PARTIAL. Error artifact là Parquet riêng có source row/field/raw/code/value state.

## Reconciliation contracts và APIs

Pydantic contracts ở `contracts/reconciliation.py`: ReconciliationPlan/Contract/Run, MatchGroup/Member/ComparisonResult, ExceptionCase, MetricSnapshot và VerifiedRun. Plan/AI JSON không cấp quyền chạy. Approve tạo contract bất biến có actor/time/revision; sửa kế hoạch tạo proposal/approval mới, không ghi đè lịch sử. SourceSelection có canonical ID, role, date/time basis, explicit filters, coverage/completeness/snapshot/due date. Metric có fields/semantic ID/basis/currency/unit/SOURCE_SIGNED, tolerance và rounding. Không chạy Python/SQL tùy ý.

| Route | Contract/gate |
| --- | --- |
| GET /api/projects/{id}/canonical-catalogue | Scoped canonical/schema/profile/mapping/identifier refs; stale không được chạy |
| GET /api/projects/{id}/domain-schema-templates | Order/OrderLine/FinancialEvent đề xuất; Settlement/Payout chỉ khi có nguồn entity thật; không approval |
| POST /api/reconciliation-plans/validate | Metadata/type/semantics/readiness; key uniqueness chỉ trên IN_SCOPE sau cùng partition của engine; trả riêng invalid/out-of-scope/in-scope và coverage_complete |
| POST /api/reconciliation-plans | Manual typed proposal, Idempotency-Key; không execute |
| POST /api/reconciliation-plans/ai | `{project_id, request: PlanningRequest}` với hai canonical IDs, facts đã xác nhận và intent; không bắt nhập keys/metrics. Giữ input `{project_id, plan}` cũ. Queue/policy/key/reservation/task cap; không tự approve |
| GET /api/reconciliation-plans/{id} | Typed proposal, source và approved contract ID nếu có |
| POST /api/reconciliation-contracts/{plan_id}/approve | Editor, validate lại scope/revisions và audit; tạo immutable contract |
| GET /api/projects/{id}/reconciliation-templates | Approved rules trong project |
| POST /api/reconciliation-contracts/{id}/reuse | Rebind canonical/period/coverage mới, kiểm schema/transform semantics/effective dates; tạo proposal cần duyệt lại |
| POST /api/reconciliation-runs | Chỉ approved contract; logical fingerprint sources/rule/engine và queue idempotency |
| GET /api/runs?project_id=... | Pagination, period_start/period_end/source_id server filters |
| GET /api/runs/{id} | Status, source refs/checks và RunArtifactRef; không raw storage path |
| GET /api/runs/{id}/metrics | Chỉ VERIFIED/PARTIAL_VERIFIED, đúng một immutable snapshot |
| GET /api/runs/{id}/matches | Server pagination/search/linkage/comparison filters; match groups typed |
| GET /api/runs/{id}/groups/{group_id}/evidence | Group thuộc đúng run; scoped source records/provenance, filename; `field_evidence` là EvidenceRef theo đúng MappingRevision của canonical lịch sử. Preview mỗi source 100 records, field refs 100 source rows/record |
| GET /api/runs/{id}/exceptions | Search, state/type/case_id filters, type/state sort, pagination; current_open_count riêng; thêm groups gồm id/key/comparisons của đúng các case trong trang, tối đa 100 group, không tính lại tiền và không trả toàn bộ membership. case_id luôn kết hợp run/workspace scope, giúp trở về đúng case từ Assistant dù ngoài trang mặc định |
| PATCH /api/exceptions/{id}/review | Editor, lý do bắt buộc khi resolve/dismiss, audit actor/time; không đổi monetary result |
| POST /api/runs/{id}/exports?format=csv hoặc xlsx | Verified only; queue và cached immutable export theo run/revision |
| GET /api/exports/{id}, /download | Workspace scope, checksum, same-origin auth; metadata revision/review_state_scope/review_state_as_of; không token/path trong URL |

RunArtifactRef độc lập DatasetVersion vì run có hai nguồn; source CanonicalDataset refs được giữ đầy đủ. Không lạm dụng ArtifactRef một-source cho match results. Failure không có MetricSnapshot. PARTIAL_VERIFIED không được trình bày như đầy đủ khi có invalid/pending/not-comparable.

CU là left canonical record ở 1:1/1:N hoặc left canonical group ở N:1. Eligible có scope/keys/own Decimal/currency hợp lệ; invalid/out-of-scope/pending/thiếu own money báo excluded riêng. Ambiguous còn trong mẫu số review. Full match đòi LINKED + EQUAL/WITHIN_TOLERANCE; zero denominator N/A. Automation là phân loại xác định đã verified không cần row-level human decision, không phải tỷ lệ tiền đã đúng. Monetary sums chỉ comparable metrics/currency/unit riêng, không cộng đa tiền tệ. `delta=L-R`, abs variance = abs(delta), tolerance theo PROJECT_PLAN; rounding chỉ khi approved.

CSV/XLSX chứa Summary/Metrics/Matches/Exceptions/Data quality/Evidence/Sources/Rules. Snapshot JSON lưu nguyên DTO để đối chiếu API. Text `=,+,-,@` có guard, IDs giữ chuỗi/zero-prefix, Decimal âm vẫn numeric. OOXML numeric lexemes giữ Decimal chính xác, nhưng Excel arithmetic có giới hạn 15 significant digits; snapshot strings/CSV phục vụ exact interchange. Report không tự tính lại KPI. Exception state được chụp khi export lần đầu, các review sau không sửa file export đã công bố.

Kiểm toán bổ sung 28/10/2026: `PlanningRequest`/`PlanningSource` tách khỏi ReconciliationPlan hoàn chỉnh. Trước AI chỉ kiểm quyền, canonical/schema/profile/mapping/artifact refs và những facts được gửi; key/grain/cardinality/metric không phải tiền điều kiện của request đề xuất. Sau AI, complete plan vẫn phải qua validator đầy đủ, giữ mọi facts được xác nhận. Khi thiếu thời gian/coverage, trả UNKNOWN/NEEDS_REVIEW với `PlanningSuggestions` (roles, field pairs, metrics, grain/cardinality/aggregation, evidence), không cấp quyền chạy. Suggestions cũng kiểm IDs/types/metric/basis/currency/grain/evidence; plan giả field hoặc thay scope bị từ chối. Proposal còn missing_requirements không được approve. Job/draft cũ vẫn đọc được; không đổi matcher, verifier hoặc engine revision.

Automation coverage giữ nguyên `metric-snapshot-1` và công thức PROJECT_PLAN §20. UI gọi **Tự động phân loại**: gồm cả kết luận xác định thiếu đối ứng/lệch đã verified, không diễn đạt như tỷ lệ khớp thành công hoặc case đã giải quyết. Không tính lại/ghi đè snapshots cũ.

Report mới dùng **report-2**, giữ nguyên report-1 và bytes/checksum đã công bố. `Summary` ghi Report generated at, Review state scope FIRST_GENERATION và giải thích automation. Worker đọc trạng thái review nhất quán trong một PostgreSQL REPEATABLE READ snapshot. API trả `review_state_as_of` từ job result; request lại cùng run/format/report revision reuse file cũ. CSV và XLSX được tạo vào hai thời điểm khác nhau có thể chứa trạng thái review khác nhau; KPI vẫn từ cùng MetricSnapshot. Report-1 cũ chưa lưu thời điểm review, trả null kèm thông báo UI; không tự suy ra timestamp hoặc sửa file lịch sử.

UI đọc tối đa 20 ô nguồn mỗi lần mở chi tiết và báo khi giới hạn; tên cột/giá trị/file/sheet/row hiển thị dạng bảng, không JSON. Transform nhiều inputs hiển thị các ô input, aggregate giữ các source members. Không sửa raw/canonical để khớp hiển thị.

## Nghiệm thu hợp đồng AI ngày 30/10/2026

Không đổi schema hay semantic contracts. `POST /api/reconciliation-plans/ai` nhận `{project_id, request: PlanningRequest}`, không nhận trường `plan`; công cụ nghiệm thu đã sửa theo contract này và regression bảo toàn source IDs/period/timezone/coverage. Không gọi live khi chạy regression. Đọc proposal cached được ghi PASS CACHED, không PASS LIVE mới.

Assistant live đã chọn comparison/comparison_0 của đúng FactSet/run/snapshot, citations về nhóm và hai dòng nguồn; số tiền Backend render từ verified facts. Planner live trả JSON chưa đạt PlanProposal nên job BLOCKED/AI_INVALID_JSON, không tạo PlanRow hay approved contract. Đây là FAIL LIVE của provider output, không đổi thành NEEDS_REVIEW thành công hoặc sửa dữ liệu để qua gate. Lịch sử raw/canonical/MetricSnapshot/exports và reservations được bảo toàn.

## Agent-first — hợp đồng hiện tại 02/11/2026

Contracts hiện có tại `backend/studio/contracts/agent.py` và `data_query.py`, không thay raw/canonical/VerifiedRun/MetricSnapshot contracts đã nghiệm thu. Trạng thái live/mock và giới hạn quality ở [báo cáo mục S](IMPLEMENTATION_STATUS.md).

| DTO | Ràng buộc |
| --- | --- |
| `AgentIntent` | 11 intents hữu hạn; tối đa 5 dataset IDs; explicit run/query/planning input; không nhận actor/approval/SQL/path. Source, schema, metric và quyền kiểm lại server-side |
| `WorkflowView` / `WorkflowState` | Context/state theo owner; tối đa 12 steps, 30 result blocks, 10 review lịch sử/3 OPEN; phân biệt CREATED/RUNNING/WAITING_REVIEW/COMPLETED/PARTIAL/FAILED/BLOCKED/CANCELLED_BEFORE_NEXT_STEP |
| `ReviewRequest` | Resource refs, nonce, expiry, source fingerprint, evidence, typed draft/plan và planning facts đã xác nhận; fingerprint gồm source/schema/mapping/canonical/rule revisions liên quan |
| `ReviewDecision` | Chỉ MAPPING/RECONCILIATION/CLARIFICATION, actor hợp lệ; lock/re-authorize/fingerprint/expiry/idempotency. Approval và enqueue bước tiếp cùng transaction; human plan edit tạo proposal mới, không ghi đè AI proposal |
| `ReviewReply` / `ReviewInterpretation` | Text tối đa 2.000 ký tự bind review/nonce/fingerprint; một draft/plan/intent hoặc câu hỏi; pending_reply_job_id và message lưu atomically. Preview xoay nonce, chưa phê duyệt |
| `DataQuery` | RAW_PREVIEW/CANONICAL/VERIFIED_RUN/EXCEPTIONS; 20 fields, 8 predicates, 5 aggregates, 3 group fields, trang tối đa 50; bounded 100k input và deadline chung 5 giây |
| `QueryResult` | Query/source refs, input_count/total_count/offset/limit/truncated, verification_status, units, evidence_complete; aggregation ALL_MATCHING trước paging, không tổng từ trang preview |

`sum_decimal` chỉ với nghĩa metric/currency/unit đã phê duyệt; raw chưa xác nhận không được cộng tiền. Null toàn nhóm vẫn null. Decimal scale kiểm toàn bộ bounded values, precision trên 38 bị từ chối thay vì làm tròn hoặc float. IDs giữ chuỗi và số 0 đầu. Predicate đúng type/operator, không nhận joins/SQL/path tự do. Provenance gốc đủ thành viên; hiển thị tối đa 100 refs/dòng phải đánh dấu truncated/evidence_complete=false.

VERIFIED_RUN cung cấp `left_member_count`/`right_member_count` từ membership bất biến. Chỉ `metric_id` thuộc approved contract mới mở left/right amount, delta, absolute_variance, tolerance, currency/unit; đọc nguyên verified comparisons, không tính lại engine. Thiếu comparison giữ null. Missing-side query phải đúng UNMATCHED và bên vắng/hiện, không gộp PENDING/INVALID.

Linkage/comparison/exception workflow predicates dùng enum đúng chiều, chỉ eq/ne/in/is_null; không MATCHED giả hoặc ordered comparisons trên status. Technical `group_id` chỉ được lấy từ group context hợp lệ; business key đi qua exact lookup có tham số, ambiguity hỏi lại. Grouping thiếu aggregation bị chặn. PAID/TRANSFERRED cần approved payment semantics; COMPLETED không chứng minh đã thanh toán. Chart toàn bộ trạng thái không được tự lọc PAID.

Result blocks có kiểu: progress/dataset_summary/table/facts/chart/download. Points/units/population/verification/completeness do backend trả. Phân bố tất cả groups không dùng nhầm eligible denominator của full-match KPI. `AssistantAnswer` legacy vẫn đọc được; message có optional workflow_id. Latest workflow chip chỉ là display context, không âm thầm sửa conversation/request/draft context khi phản hồi đến muộn.

Một child job SUCCEEDED không đủ kết luận toàn workflow COMPLETED. Hủy chỉ dừng bước tiếp, không xóa published artifacts. Resume và review đều kiểm lại quyền/revision; stale trả lỗi có nghĩa, không tự sửa dữ liệu/approval để tiếp tục.

## Assistant experience — bổ sung hợp đồng đọc và routing

- `GET /api/datasets/{id}/download`: scoped dataset → immutable raw artifact của version → kiểm SHA256 giữa artifact/dataset/bytes → FileResponse attachment, nosniff, private/no-store. Anonymous/foreign workspace bị chặn; corruption trả 409; không nhận path từ client. Không sửa raw để xuất lại.
- Provider-only `RoutingBatch`/`RoutingQuery`/`ReconciliationSelection` mở rộng thành AgentIntent ở server. `QueryOperations` dùng chung cho routing và public DataQuery; source_ref không thay source_id trong API public. Filter/aggregate/group/currency phải khai báo rõ trong routing. Provider schema chỉ cho field refs có trong catalogue và properties thuộc intent; validation server vẫn giữ cardinality/exact-count/caps.
- `confirmed_run_id` chỉ dereference current run với đúng left/right canonical IDs READY. Sao chép đầy đủ PlanningRequest.from_plan, giữ role/date/time basis/filter/coverage/snapshot/effective facts; không cấp approval mới, không đổi lịch sử. Facts mới vẫn review.
- EXCEPTION_FIELDS dùng chung giữa catalogue và native query: case_id/group_id/type/state/notes. Catalogue nguồn có kind/schema/readiness/project scope/current run; tệp trùng tên cần context/ID.

Không migration mới trong nhiệm vụ này. API query, MetricSnapshot, Decimal/null/provenance, mappings/reviews/permissions và dataset/run revisions giữ nguyên.

## Trần request AI local và trình bày kết quả — 04/11/2026

`WorkspacePolicy.external_request_budget` nhận integer không âm hoặc `null`; null bỏ trần tích lũy, không bật cloud. Global/task config tương ứng nhận null qua `unlimited` chỉ trong local demo explicit. Settings DTO `gemini_requests_remaining`, `ai_task_allowances.*.remaining/configured_ceiling` nullable: remaining là min các trần hữu hạn còn hiệu lực; tất cả unlimited thì null, permissionOFF thì0. Ledger/reservations cũ giữ nguyên. Parser request/credit/SHA và workflow caps không đổi. Không có schema migration vì policy là JSONB; cập nhật policy local phải audit quyền mới, không dùng null cho workspace chưa được cấp quyền.

Query/MetricSnapshot/Decimal/provenance không đổi: Chat xem trước10dòng của trang, chế độ chi tiết dùng chính query/page hiện có. Mở rộng không gửi inference hoặc query mới; pagination/sort vẫn qua API được kiểm scope, lưu selection và kiểm ordinal đúng trang. NULL hiển thị dấu gạch, không thành0; IDs và tên cột không dịch bằng replace-all. Định dạng tiền trong tóm tắt chỉ thao tác chuỗi Decimal, không float/tính lại. Dữ liệu gốc đã đọc không được gọi đã chuẩn hóa; PARTIAL luôn nói rõ dữ liệu chưa đầy đủ.

Rollback về image trước khi hỗ trợ null cần khôi phục **cấu hình hạn mức hữu hạn và policy tương thích từ backup/audit**, giữ mọi reservations phát sinh; không chạy image cũ trực tiếp với `unlimited`/null hoặc reset ledger. Raw/canonical/runs/exports không cần chuyển đổi.

Routing27 bổ sung `ReconciliationSelection.left_source/right_source` kiểu PlanningSource và effective dates optional cho dữ kiện người dùng đã nêu. Compiler giữ nguyên toàn bộ facts vào PlanningRequest; canonical IDs trong facts phải khớp hai nguồn được chọn. Reuse confirmed_run_id từ chối mọi facts mới mâu thuẫn, không âm thầm bỏ chúng; missing vẫn null. Source/coverage/timezone/date guards và Planner validator giữ nguyên; complete proposal vẫn phải được người dùng duyệt. Đây là sửa mất dữ kiện giữa router và Planner, không tự suy coverage từ kỳ hoặc tự phê duyệt.

Routing28 phân biệt time_basis (ngày phát sinh/hạch toán) với timezone, từ chối facts mới lấy UTC/múi giờ làm ý nghĩa ngày; không viết lại quy tắc đã duyệt lịch sử. Count một giá trị được trình bày bằng giá trị đếm Backend trả, không lấy số dòng trong bảng aggregate làm số giao dịch.
