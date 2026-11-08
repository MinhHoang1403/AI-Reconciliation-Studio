# Đặc tả màn hình và thành phần

**Trạng thái PROPOSED · 09/11/2026 · Chờ chủ dự án duyệt.** Đặc tả áp dụng cho đợt thiết kế sau. Các hợp đồng và điểm vào được đối chiếu với source tại `c477745d6c4426c663089251f75182aa1e2c375c`. Chứng cứ trên bản chạy, viewport và giới hạn tái hiện nằm trong [kiểm toán hiện trạng](../INTERFACE_REDESIGN_AUDIT.md). Các phần dưới đây ghi **SOURCE_VERIFIED** cho hành vi đã đối chiếu mã và **PROPOSED** cho cách tổ chức mới. `UX-S01` đến `UX-S12` là mã màn hình/luồng để dùng trong nghiệm thu.

Đọc cùng [kiến trúc thông tin](UX_INFORMATION_ARCHITECTURE.md), [Design System](DESIGN_SYSTEM_BLUEPRINT.md), [microcopy](MICROCOPY_AUDIT.md), [kế hoạch nghiệm thu](IMPLEMENTATION_AND_ACCEPTANCE_PLAN.md) và [quyết định mở](OPEN_DECISIONS.md). Nguồn hợp đồng [DATA_CONTRACTS.md](../DATA_CONTRACTS.md) và [kế hoạch sản phẩm](../PROJECT_PLAN.md) quyết định trạng thái, quyền và ngữ nghĩa nghiệp vụ.

## 1. Hợp đồng chung giữa các màn hình

- **App Shell.** Assistant mở đầu. Đề xuất sáu mục AI Assistant, Dữ liệu, Đối soát, Báo cáo, Lịch sử, Cài đặt. Ngoại lệ thuộc kết quả đối soát. Giữ các đích URL hiện có theo `navigation.ts`, gồm `#page=home`, `data`, `reconcile`, `exceptions`, `reports`, `settings`, `assistant` và các tham số hợp lệ `project`, `from`, `conversation`, `run_id`, `dataset_id`, `group_id`, `case_id`. Lịch sử trong bản hiện tại là modal do Assistant sở hữu. Hình thức trình bày đề xuất có thể là một panel theo vị trí trong shell. Nếu muốn URL độc lập cho Lịch sử, đây là quyết định frontend bổ sung, có đường quay về tương thích.
- **Mốc bố cục đề xuất.** Header shell 56px, sidebar 240px hoặc rail 64px từ 768px, dưới 768px chuyển thành drawer. Chat có cột đọc khoảng 760px tối đa và co theo diện tích. Panel khoảng 400px chỉ dock từ 1440px nếu cột Chat vẫn đủ đọc với sidebar và padding. Nếu thiếu chỗ, chuyển sang drawer. Dưới 768px dùng màn hình chi tiết toàn chiều rộng. Mốc đề xuất không phải số đo bản chạy. Mỗi trang có một tiêu đề chính, tối đa một CTA chính theo trạng thái, phần còn lại ở toolbar hoặc menu đúng tác vụ. Cuộn trang chính độc lập với bảng có tràn ngang. Panel đọc có vùng cuộn riêng, không đẩy composer khỏi màn hình.
- **Khóa ngữ cảnh.** Mọi đích mang đúng `projectId`, và ID hội thoại/nguồn/bảng/canonical/run/group/case theo nhu cầu. Giữ run cùng snapshot, rule revision và kỳ; giữ nguồn cùng table/version và mapping revision; UI chỉ dùng revision nào DTO có thật. Không lấy run mới nhất thay bản ghi đang mở. Nếu URL thiếu ID, cho người dùng chọn và ghi rõ nguồn được chọn; nếu ID rõ nhưng bị xóa/thu hồi, giữ đích ở trạng thái không mở được và cung cấp lối về phạm vi hợp lệ. Các selector có thể ghi nhớ lựa chọn hợp lệ theo dự án; local cache không cấp quyền.
- **Quyền.** `GET /api/session` cho role; mọi API tự kiểm quyền. Viewer có thể đọc tài nguyên được phép và dùng câu hỏi đọc nếu policy cho phép, nhưng không tải nguồn mới, duyệt, chạy hoặc yêu cầu sinh báo cáo mới. Khả năng tải file đã sinh đi theo quyền server của export hiện có. Editor/owner có các thao tác sửa theo từng endpoint; đổi phân loại dự án và chính sách reuse mapping dùng quyền owner. Quyền mới không tự suy ra từ giao diện. Xử lý 401 quay về bước phiên hiện có; 403/404 không giữ bản xem dữ liệu nhạy cảm trên màn hình và không đoán tài nguyên có tồn tại.
- **Mất kết nối và thao tác trùng.** Fetch cũ phải bị hủy hoặc bỏ theo generation key khi đổi đích. Lỗi đọc có nút tải lại đúng đích; lỗi mutation chưa rõ kết quả phải truy hồi job/receipt hoặc gửi lại đúng key + payload nếu hợp đồng hỗ trợ, không tạo một thao tác khác. Tách rõ “chưa có dữ liệu”, “không khớp bộ lọc”, “đang tải”, “không tải được”, “đã cũ”, “không còn quyền”. Không dùng skeleton thay cho lỗi. Unknown enum dùng nhãn trung tính, chi tiết hỗ trợ có mã nếu an toàn; không suy ra thành công.
- **Focus và thông báo.** Khi đổi trang đưa focus vào tiêu đề hoặc vùng main bằng điều hướng có chủ đích. Tab theo trật tự nhìn. Drawer/modal có tên, giới hạn focus, Escape, trả focus về nút mở hoặc đầu mục hợp lệ khi nút biến mất. Panel dock là landmark có tên, không trap focus. Popover đóng bằng Escape rồi về trigger. Chỉ cập nhật live region phần mới, không đọc lại toàn transcript. Label dài, 200% zoom và bàn phím không che nút, lỗi hoặc mục đang focus.
- **Tiền và trạng thái.** Giữ Decimal dạng chuỗi từ API, phần hiển thị theo locale và đơn vị đã duyệt không mất chữ số. Chữ số dùng tabular figures, canh phải; giữ dấu âm và số 0 đầu của ID. `0`, NULL, chuỗi rỗng và dữ liệu lỗi có nhãn riêng, không biến lẫn nhau. Mẫu số 0 hiển thị “Không áp dụng”. `LINKED` có thể đồng thời `AMOUNT_MISMATCH`; xử lý xong ngoại lệ không sửa trạng thái so sánh hoặc snapshot. Tiền đa loại không cộng chung.

## 2. Bản phác thảo dùng chung

```text
Desktop có đủ chỗ
┌───────────┬─────────────────────────────────────────────────────────────────┐
│ Sidebar   │ [Dự án ▾]                 [Ngữ cảnh tác vụ]        [Hành động] │
│ 240 / 64  ├──────────────────────────────────────────┬──────────────────────┤
│ Assistant │ Cột chính · nội dung có thứ bậc           │ Chi tiết đọc (khi mở) │
│ Dữ liệu   │                                          │ Tệp / kết quả /      │
│ Đối soát  │ Chat: lời đáp → khối cần thiết → hành động │ bằng chứng theo ID   │
│ Báo cáo   │       [Đính kèm] [Nhập yêu cầu] [Model][↑] │ [Đóng] [Mở trang]    │
│ Lịch sử   │ Trang nghiệp vụ: tiêu đề → toolbar → bảng │                      │
│ Cài đặt   │                                → phân trang                     │
└───────────┴─────────────────────────────────────────────────────────────────┘

Mobile
┌──────────────────────────────┐
│ [☰] [Dự án ▾]  [Tác vụ / ⋯]  │
├──────────────────────────────┤
│ Một cột nội dung              │
│ Chat hoặc trang nghiệp vụ     │
│ Bảng có vùng cuộn ngang riêng │
├──────────────────────────────┤
│ Chat: composer và safe-area   │
└──────────────────────────────┘
Khi xem sâu, mở một màn hình chi tiết có nút Quay lại.
Review nghiệp vụ chỉ có một nơi thao tác; panel bằng chứng chỉ đọc.
```

## 3. Đặc tả theo màn hình và điểm vào

### UX-S01 · App Shell, dự án và trang Tổng quan cũ

**Mục tiêu và điểm vào.** Mở Assistant mặc định hoặc tiếp tục URL cũ. Biết đang làm việc trong dự án nào, chuyển dự án chính xác, tìm lại tác vụ mà không nhớ tên thuật ngữ. **SOURCE_VERIFIED** [App.tsx](../../frontend/src/App.tsx) chọn/khôi phục dự án và cung cấp mục Lịch sử, menu workspace, cùng trang `home` trong [navigation.ts](../../frontend/src/navigation.ts). [ProjectSelector.tsx](../../frontend/src/ProjectSelector.tsx) có combobox và danh sách dự án phân trang.

**PROPOSED.** Header chứa combobox dự án và một tiêu đề theo đích. Rail có tooltip, tên đọc được và `aria-current`; nhóm điều hướng và Cài đặt không lặp thương hiệu. Khi không có dự án, hiển thị hướng dẫn bắt đầu và hành động hợp lệ theo role. Trong selector, hiển thị tên, phân loại TEST khi thực sự có và phạm vi nghiệp vụ khi cần phân biệt tên trùng; danh sách lọc phân trang, mũi tên chọn, Enter mở, Escape đóng, focus về trigger. Tạo dự án dùng modal hai trường tên/phạm vi và báo lỗi tại trường. Trang Tổng quan cũ giữ nội dung hợp lệ và CTA “Tiếp tục” từ `preparation_action` khi sẵn có; không thêm mục chính trong sidebar. Nếu đổi URL chuẩn sau này, link cũ phải mở tương đương và được kiểm thử.

**Dữ liệu và lỗi.** `GET /api/projects?search=…&offset=…&limit=…`, `GET /api/projects/{project_id}`, `GET /api/projects/{project_id}/summary` (`ProjectSummary`, `PreparationAction`), `POST /api/projects` theo quyền server, `PATCH /api/projects/{project_id}/classification` owner. Hiện route project hợp lệ trong khi list chưa tải; ID bị từ chối giữ lỗi đúng đích, xóa selection cũ trên UI. Trạng thái kết nối chỉ xuất hiện khi ảnh hưởng thao tác.

**Nghiệm thu.** Dự án tên dài, trùng tên, TEST lọc/hiện đúng, nhập bàn phím hoàn chỉnh, back/forward, link cũ, request đến trễ sau đổi dự án, 403/404, bảo toàn scope và không xuất hiện dữ liệu dự án trước.

### UX-S02 · Assistant: bắt đầu, transcript và composer

**Mục tiêu và điểm vào.** Một câu hỏi ngắn hoặc tệp cần xử lý. Mở Assistant mới, chọn Lịch sử, vào từ nguồn/run/ngoại lệ. **SOURCE_VERIFIED** [AssistantStudio.tsx](../../frontend/src/AssistantStudio.tsx) có file picker CSV/XLSX, nháp theo owner và context, `isComposing`, phiên xử lý theo job, cuộn đuôi, menu tin nhắn và panel kết quả. Mở trang hiện tại đôi khi cần tải quyền, mô hình và dữ liệu lịch sử độc lập; hiển thị tương ứng.

**PROPOSED.** Màn hình mới chỉ có lời dẫn một dòng, composer và tối đa ba gợi ý theo scope có thật. Bấm gợi ý đặt nội dung vào ô nhập, đưa focus về đó; không tự gửi. Hội thoại có lịch sử hiển thị turn theo thời gian, nhãn vai trò đọc được, khối AI theo mục 4 và nút “Tải tin nhắn trước” giữ vị trí. Khi người dùng đang đọc phía trên, trả lời mới chỉ hiện “Có tin nhắn mới”; khi ở cuối, tự cuộn vừa đủ để thấy dòng mới. Cho nhiều workflow cùng tồn tại nhưng mỗi workflow chỉ có một điểm tương tác hiện hành gắn turn mới nhất của workflow đó.

Composer có nhãn rõ, textarea nở từ một dòng đến khoảng 4–6 dòng rồi cuộn trong. Luôn thấy Đính kèm, Gửi và model nếu có lựa chọn. File chips bọc dòng; tên dài có cách đọc đủ, nút Bỏ kèm tên. Trạng thái gửi/chờ lấy từ job; upload không có tỷ lệ thật thì dùng tiến trình vô định “Đang tải 2 tệp…”. Trạng thái pending khóa gửi tiếp cho cùng hội thoại, không xóa bản nháp mới. Hạn chế định dạng/số tệp/dung lượng từ `WorkspaceSettings`; server kiểm lại. Trong chế độ trả lời thẻ hiện tên câu hỏi + “Bỏ liên kết”, khóa file nếu endpoint không nhận. Khi mobile mở bàn phím, composer nằm trong vùng nhìn được, safe-area dưới nút gửi, giữ vùng đuôi transcript trên composer. Desktop Enter gửi, Shift+Enter xuống dòng, IME không gửi giữa composition; cần test bộ gõ Windows thực. Mobile luôn có nút Gửi rõ, phím xuống dòng và thao tác chọn dấu không gây gửi nhầm. Nút gửi duy nhất cho mỗi lượt, label phụ rõ nếu upload-only.

**Dữ liệu, quyền, lỗi.** `POST /api/conversations`, `GET /api/conversations/{id}` có `limit` và `before_id`, `POST /api/assistant/messages` trả `job_id`, `GET /api/jobs/{job_id}`, `GET /api/assistant/models`, `POST /api/agent/attachments` trả project/dataset references. `AssistantContext` có `project_id` và run/dataset/group/case hợp lệ. Lượt cũ giữ model đã chọn; model lần sau theo lựa chọn hợp lệ và policy hiện tại. Model không khả dụng/giới hạn hiển thị cạnh selector hoặc trên turn lỗi, đọc được nguồn và kết quả đã lưu. `AI_DELIVERY_UNKNOWN` cung cấp cập nhật hội thoại, không mời tự gửi lại. `CONVERSATION_CONTEXT_CHANGED` cho tạo hội thoại mới có scope đã chọn. Upload và gửi yêu cầu là các giai đoạn phân biệt; mất phản hồi sau upload giữ kết quả chấp nhận đã lưu, khôi phục message theo request key thay vì tải lại tệp.

**Nghiệm thu.** Welcome có/không dự án, tệp quá cỡ/sai loại/tên dài, attach-only, pending/reload, job không trả kết quả, nhiều lượt/older load không nhảy cuộn, mất phản hồi upload và gửi, đổi model khi pending không đổi message lịch sử, IME/Shift+Enter/Tab, bàn phím thật 390px và zoom 200%.

### UX-S03 · Review và làm rõ trong Chat

**Mục tiêu và điểm vào.** Từ turn chờ, hoàn tất câu hỏi thiếu dữ kiện hoặc duyệt một bản nháp sau khi biết hệ quả. **SOURCE_VERIFIED** [AgentWorkflowPanel.tsx](../../frontend/src/AgentWorkflowPanel.tsx) phân biệt `CLARIFICATION` với `MAPPING` và `RECONCILIATION`, cập nhật workflow, có batch mapping 2–3 thẻ qua endpoint hiện có, render [ReviewCard.tsx](../../frontend/src/ReviewCard.tsx). Backend tách nonce, fingerprint, expiry, preflight, reply và decision.

**PROPOSED.** Một thẻ gồm “Cần bạn bổ sung” hoặc “Cần bạn xác nhận” + tên nguồn, tóm tắt thay đổi, dòng dữ kiện quan trọng, một CTA cụ thể và nút “Xem chi tiết”. Mở chi tiết bằng disclosure; panel chỉ xem bằng chứng, không có điểm duyệt thứ hai. Khi ở mobile, thẻ nằm trong transcript, chi tiết mở riêng rồi quay về tiêu đề thẻ. Tiêu đề lỗi dẫn tới trường đầu tiên cần sửa; nội dung giữ được khi cuộn/đóng chi tiết. Xem đầy đủ quy tắc mục 5.

**Nghiệm thu.** Câu trả lời bổ sung không sinh approval, sửa draft không tự duyệt, đổi nguồn/nonce/expire khi đang mở, 403, bản cũ, batch thiếu một thẻ, draft phục hồi và idempotency mất phản hồi. Dùng dữ liệu TEST rõ nguồn và cổng kiểm thử riêng.

### UX-S04 · Lịch sử hội thoại

**Mục tiêu và điểm vào.** Tiếp tục hội thoại đúng dự án, tạo hội thoại mới, xóa nội dung riêng khi có quyền. **SOURCE_VERIFIED** lịch sử là Modal trong `AssistantStudio.tsx`; tìm trong các hội thoại đã tải, tải thêm và xác nhận xóa qua API.

**PROPOSED.** Một danh sách có ngày, tiêu đề và dự án đang xem, không nhúng kết quả tài chính. Trên desktop có thể dùng panel/drawer một cột, mobile toàn màn hình; focus vào ô tìm hoặc tiêu đề. Nút hội thoại mới cùng nhóm với danh sách; xóa trong menu dòng, mở xác nhận có hậu quả rõ. Mở dòng đóng overlay rồi khôi phục đúng hội thoại, không tự gửi lại request. Giữ tìm kiếm/pagination khi quay về cùng dự án trong phiên. Nếu chỉ lọc trang đã tải, label nêu giới hạn và có “Tải thêm”; tìm toàn bộ server chỉ làm nếu hợp đồng hỗ trợ, không mượn bộ lọc tiêu đề cục bộ để hứa kết quả đầy đủ.

**Dữ liệu và lỗi.** `GET /api/conversations?project_id=…`, `GET /api/conversations/{id}`, `DELETE /api/conversations/{id}`; scope actor, không gian, dự án; xóa transcript giữ dữ kiện nghiệp vụ theo `assistant_api.py`. Phân biệt rỗng, tìm không ra, tải lỗi, hội thoại đã xóa, đã hết quyền. Escape trả focus về mục Lịch sử; sau xóa trả về dòng kế tiếp hoặc “Hội thoại mới”.

**Nghiệm thu.** Lịch sử dài, truy cập nhầm actor/project, xóa có xác nhận, khôi phục hội thoại cũ cùng job, giữ scroll khi tải trước, không mất nháp của hội thoại khác.

### UX-S05 · Data Workspace: nguồn, Raw, Prepared, Canonical và dòng lỗi

**Mục tiêu và điểm vào.** Tìm nguồn, chọn đúng sheet/phiên bản và hiểu dữ liệu đã ở tầng nào. Đi từ sidebar, thẻ kết quả hoặc deep link. **SOURCE_VERIFIED** [App.tsx](../../frontend/src/App.tsx) và [DataOverview.tsx](../../frontend/src/DataOverview.tsx) cung cấp preview theo tầng, findings, profile, Mapping và quy trình upload. [AssistantDataDrawer.tsx](../../frontend/src/AssistantDataDrawer.tsx) hiện có raw/canonical/errors và lối sang manual.

**PROPOSED.** Danh sách Nguồn → tiêu đề nguồn với tên tệp, sheet/bảng, phiên bản, trạng thái và CTA theo `PreparationAction` có scope hợp lệ → tabs Dữ liệu gốc, Bản chuẩn bị, Đã chuẩn hóa và nhóm chức năng Cấu trúc & lỗi. Lỗi của bản chuẩn hóa, findings của prepared và warning đọc tệp giữ đúng tầng và version. Tab label rõ, chỉ mở khi có dữ liệu tương ứng; trước chuẩn hóa giải thích còn thiếu gì và dẫn tới thẻ/biểu mẫu có quyền. Data tab có caption, số dòng khớp, phân trang server và cuộn trong bảng. Giữ vị trí/tìm kiếm theo project + dataset + table + view + canonical version; đổi nguồn/phiên bản xóa bộ lọc không còn hợp lệ. Desktop danh sách có thể cạnh bảng, tablet/mobile dùng lối quay lại danh sách, không xếp bảng thành thẻ từng ô. Tệp PDF/DOCX hiển thị bản trích xuất chưa xác minh ở tab tài liệu nếu đã có; cảnh báo phép đọc bên ngoài và kết quả chưa đủ chuẩn giữ nguyên.

**Dữ liệu và lỗi.** `GET /api/datasets?project_id=…&offset=…&limit=…`, `GET /api/datasets/{id}`, `/tables`, `/artifacts`, `/documents`, `/download` dưới cùng tài nguyên; `GET /api/tables/{id}/profile`, `/mappings`, `/preview?kind=raw|prepared|prepared_findings|canonical|errors&offset=…&limit=…&search=…`. Canonical và errors bắt buộc có `canonical_id` thuộc đúng bảng. Nếu `stale=true`, cho xem lịch sử nhưng không gợi ý là dữ liệu mới để lập run. Giữ parsed warning công thức, header, sheet ẩn, lỗi ô; provenance mở từ dòng đúng phiên bản. Data Workspace upload qua `POST /api/datasets/uploads`, tùy chọn encoding/delimiter/header chỉ mở khi cần; parser cloud có allowance riêng. Danh sách nguồn không có tham số search ở hợp đồng hiện tại; tìm toàn bộ nguồn cần hợp đồng riêng hoặc chọn bằng phân trang, không hứa “mọi nguồn” từ bộ lọc cục bộ. Bảng preview có search server; sắp xếp toàn bộ chỉ hiện khi API đích hỗ trợ.

**Nghiệm thu.** Raw giữ số 0 đầu và bytes; Prepared chỉ để khám phá, findings liên kết đúng dòng; Canonical version mới/cũ; NULL/rỗng/0/lỗi, hai sheet, PDF/DOCX chưa xác minh, cảnh báo chuyển đổi, bảng lớn không tràn trang, no results và fetch cũ sau đổi filter.

### UX-S06 · Mapping Studio và chuẩn hóa thủ công

**Mục tiêu và điểm vào.** Xác nhận ý nghĩa nguồn và kết quả kiểm trước chuẩn hóa. Đi từ Dữ liệu, CTA review, hoặc khi AI không khả dụng. **SOURCE_VERIFIED** [MappingStudio.tsx](../../frontend/src/MappingStudio.tsx) có draft, preflight, approval, reject và kiểm soát reuse; App gọi normalize sau khi có mapping đã duyệt. Data có thể mở thẻ mapping hội thoại qua API hiện hành.

**PROPOSED.** Ở đầu màn hình ghi nguồn, bảng, phiên bản và mục tiêu. Hiện mục “Cần quyết định” trước danh sách đã kiểm tra. Thao tác chọn field, kiểu và business key trong form có group label; phần advanced mở rộng cho transform, định dạng và quy tắc có hợp đồng. Preflight báo phạm vi, số hàng ảnh hưởng, cảnh báo nào cần xác nhận và lỗi cụ thể. Cùng tài nguyên đang có thẻ hội thoại, dùng đường dẫn quay đúng thẻ hoặc theo đúng quy trình manual đã có; không tự sao chép approval hay chia sẻ nonce giữa các luồng. Tách “Duyệt ghép cột” và “Chuẩn hóa” khi đi luồng manual. Editor/owner được sửa, viewer xem. Xác nhận riêng trước reuse nếu điều kiện thay đổi. Chuẩn hóa đưa người dùng về dataset đã xử lý hoặc phần lỗi, giữ Raw và revision trước.

**Dữ liệu và lỗi.** `GET /api/tables/{id}/mappings`, `GET /api/mapping-proposals/{mapping_id}`, `GET /api/agent/tables/{table_id}/mapping-reviews`, `POST /api/tables/{id}/mapping-proposals`, `POST /api/tables/{id}/mapping-preflight`, `POST /api/mappings/{mapping_id}/approve`, `POST /api/mappings/{mapping_id}/reject`, `PATCH /api/mappings/{mapping_id}/reuse-policy`, `POST /api/datasets/{dataset_id}/normalize`, `GET /api/jobs/{job_id}`. Gate preflight theo đúng payload và nguồn, giữ refresh/error với draft; revision không khớp yêu cầu rà lại. Hiển thị kết quả partial và dòng không hợp lệ riêng. Reject chỉ hiển thị cho mapping manual có endpoint, không tự thêm cho Agent.

**Nghiệm thu.** Locale, date/timezone, currency/basis/unit/semantic metric, dữ liệu trích xuất, thay đổi cột nguồn, token/receipt và khôi phục sau reload; bảng lỗi và record counts lấy đúng server, không bấm duyệt khi đang kiểm lại.

### UX-S07 · Đối soát: chọn nguồn, lập phương án, duyệt và chạy

**Mục tiêu và điểm vào.** Biết hai nguồn nào được so, dùng khóa, kỳ, chỉ tiêu và quy tắc gì. Mở từ sidebar, bản nháp trong Chat hoặc template đã duyệt. **SOURCE_VERIFIED** [ReconciliationStudio.tsx](../../frontend/src/ReconciliationStudio.tsx) có chế độ setup/reports/exceptions, catalogue, AI/manual plan, validate, approve, run và reuse. [AssistantWorkflow.tsx](../../frontend/src/AssistantWorkflow.tsx) có các lối tiếp tục draft/thủ công và dùng lại rule trong Assistant.

**PROPOSED.** Bố cục trình tự “Chọn nguồn → Kiểm phạm vi → Xác nhận quy tắc → Chạy”. Hai nguồn hiển thị theo đúng trái/phải, tên, bảng, phiên bản, vai trò, số dòng hợp lệ/lỗi và grain. Thời kỳ cùng timezone, từng coverage, loại ngày, độ đầy đủ, thời điểm chốt và hạn quyết toán nếu có phải rõ. Không tự điền coverage dựa vào min/max hoặc vai trò từ thứ tự tệp. Khi rule đầy đủ, tóm tắt khóa ghép theo thứ tự, 1:1/1:N/N:1, grain so sánh, phép gom nhóm, tiêu chí tiền/đơn vị/basis/currency, dấu, tolerance và cách làm tròn; phần nâng cao vẫn có các trường hỗ trợ hiện hành. Danh sách draft có “Tiếp tục” và hiển thị dự án/nguồn/kỳ. CTA theo gate: “Kiểm tra phạm vi”, “Duyệt quy tắc”, “Chạy đối soát” ở manual; nếu Chat approve có thể xếp việc theo workflow server thì nêu điều đó trước duyệt. Trên mobile xếp hai nguồn theo thứ tự, giữ nhãn trái/phải khi cuộn. Link xem readiness và lỗi tập trung trong checklist ngay trước xác nhận.

**Dữ liệu và lỗi.** `GET /api/projects/{project_id}/canonical-catalogue`, `/reconciliation-plans`, `/reconciliation-templates` dưới tài nguyên project. `POST /api/reconciliation-plans/ai` + job, `GET /api/reconciliation-plans/{plan_id}`, `POST /api/reconciliation-plans/validate`, `POST /api/reconciliation-plans`, `POST /api/reconciliation-contracts/{plan_id}/approve`, `POST /api/reconciliation-contracts/{contract_id}/reuse`, `POST /api/reconciliation-runs`, `GET /api/jobs/{job_id}`. Tách plan nháp, contract đã duyệt và run. Reuse sinh bản nháp có xác nhận lại theo kỳ, không suy ra tự duyệt hoặc bỏ kiểm schema drift. Giữ trạng thái partial cần xác nhận nếu backend yêu cầu `invalid_rows_reviewed`; không chạy nếu gate không đạt. Worker phục hồi theo job hiện có; màn hình cung cấp “Xem lần chạy” khi có run ID. Không đặt spinner mơ hồ nếu server đã trả lỗi terminal.

**Nghiệm thu.** Vai trò nguồn tường minh, tên trùng, nguồn chưa chuẩn hóa hoặc cũ, khóa ghép có thứ tự, cùng khóa khác tiền, gross/net khác, thiếu coverage/hạn quyết toán, 1:N/N:1, rule reuse đổi revision, chặn quyền và chạy trùng, fail/partial/verified theo đúng run.

### UX-S08 · Kết quả đối soát: snapshot, bảng và biểu đồ

**Mục tiêu và điểm vào.** Hiểu kết quả cho run đã chọn, kiểm tra số lệch/thiếu và đi từ tổng quan tới nhóm. Đi từ “Xem lần chạy”, Đối soát, Chat hoặc Báo cáo. **SOURCE_VERIFIED** `ReconciliationStudio.tsx` gọi run, matches, exceptions. Backend bảo vệ metrics/matches/evidence sau kiểm chứng. Kết quả có khả năng partial.

**PROPOSED.** Header run với kỳ/timezone, nguồn, quy tắc và trạng thái kiểm chứng. Thứ tự “Tổng quan → Giao dịch → Ngoại lệ”. KPI ưu tiên số đã kiểm chứng, ghi đơn vị so sánh và mẫu số, kỳ, currency; hiển thị phạm vi không được kiểm chứng khi partial. Biểu đồ đi cùng bảng số/caption (đơn vị, kỳ, nhóm, nguồn, đầy đủ hay cắt). Không dùng cùng màu để thay cho nhãn khác biệt. Các hàng hiển thị khóa, trạng thái liên kết, trạng thái so sánh, số hai phía, chênh lệch theo từng metric và nút “Xem bằng chứng”. Vùng kiểm soát lọc, số khớp, trang hiện tại và tổng run ghi riêng. Khi kết quả không phù hợp bộ lọc, giữ KPI toàn run có nhãn và có nút xóa lọc, không biến thành “Chưa có run”. Trên mobile KPI có thể xếp dọc và bảng tràn trong vùng riêng, có cách đọc đủ nhãn/giá trị. Khi verification thất bại, hiển thị trạng thái và lối xem kiểm tra có sẵn, không hiển thị KPI hoặc export.

**Dữ liệu và lỗi.** `GET /api/runs?project_id=…` hỗ trợ bộ lọc kỳ/nguồn của API, `GET /api/runs/{id}`, `GET /api/runs/{id}/metrics`, `GET /api/runs/{id}/matches?offset=…&limit=…&search=…&linkage=…&comparison=…`. Dùng `Run`, `MetricSnapshot`, `MatchPage`/group. Snapshot chỉ đổi khi người dùng đổi run. Sort toàn bộ matches không suy từ sort của bảng cục bộ vì endpoint không có sort; Chat query đã có allowlist sort riêng. Hai con số tổng kỳ và hiện có thể cùng tồn tại nếu ghi nguồn. Không sao chép logic Matcher/Verifier vào UI, không tính lại tỷ lệ, không coi chart number chuyển cho ECharts là giá trị kế toán dùng trong bảng/tooltip.

**Nghiệm thu.** 0 eligible, nhiều currencies/metrics, exact Decimal âm/dương, cùng một run ở Chat và trang, sort/filter/page không đổi snapshot, partial có phạm vi, lỗi verification chặn đọc tài chính và export, biểu đồ có text fallback và đọc được không màu.

### UX-S09 · Ngoại lệ và xử lý

**Mục tiêu và điểm vào.** Lọc ngoại lệ, xem lý do, ghi chú và chốt trạng thái công việc. Đi từ tab Ngoại lệ của kết quả, Chat “Xem ngoại lệ”, hoặc link `#page=exceptions` với đúng run/case. **SOURCE_VERIFIED** [ReconciliationEvidence.tsx](../../frontend/src/ReconciliationEvidence.tsx) đọc bằng chứng và ghi review ngoại lệ. `PATCH` chỉ cập nhật workflow case.

**PROPOSED.** Toolbar có loại ngoại lệ, trạng thái xử lý, tìm kiếm theo chức năng server và sắp xếp hỗ trợ. Danh sách cột lý do, nhóm, tình trạng nghiệp vụ, workflow case và liên kết “Xem bằng chứng”. Tiêu đề case giữ run, phạm vi và nguyên nhân có mức tin cậy theo hợp đồng, không gắn nhãn nguyên nhân đã biết nếu thiếu chứng cứ. Editor/owner chọn trạng thái trong một điểm tương tác, hiển thị bắt buộc ghi chú khi kết thúc theo backend. Khi thành công giữ case và cập nhật số mở hiện tại; KPI tại run không đổi. Viewer chỉ đọc. Không làm đồng thời hai overlay; nếu mở bằng chứng từ case, dùng một overlay với đường quay lại case và focus phù hợp.

**Dữ liệu và lỗi.** `GET /api/runs/{run_id}/exceptions?state=…&issue=…&sort=…&search=…&case_id=…` kèm offset/limit, server sort `type|state`, `PATCH /api/exceptions/{case_id}/review`. `current_open_count` phản ánh hiện tại, `unresolved_cases_at_run` thuộc snapshot. `RESOLVED` hoặc `DISMISSED_WITH_REASON` cần lý do không rỗng; hiển thị `REVIEW_REASON_REQUIRED` cạnh ô ghi chú. Nếu case không còn hợp lệ theo filter hoặc quyền, đóng chi tiết nhạy cảm, hiển thị lỗi trong danh sách và giữ scope đã chọn.

**Nghiệm thu.** Case link sai run, reviewer không có quyền, chốt cần lý do, đóng overlay phục hồi focus, cập nhật số mở nhưng không đổi tiền/kết quả, distinct state khi không có ngoại lệ hoặc lọc không có kết quả.

### UX-S10 · Bằng chứng và Context Panel

**Mục tiêu và điểm vào.** Kiểm tra một chi tiết rồi quay về đúng dòng/hội thoại. Đi từ dẫn chiếu facts, hàng bảng, ReviewCard hoặc ngoại lệ. **SOURCE_VERIFIED** hiện có `AssistantDataDrawer`, modal kết quả trong Assistant, `ReconciliationEvidence`, evidence sheet/cell và nguồn dòng cho bảng Chat.

**PROPOSED.** Ba mức hiển thị. Inline cho câu trả lời ngắn, tiến trình một dòng, tóm tắt hoặc thẻ cần quyết định. Panel cho đọc một nguồn, một snapshot, một nhóm hoặc bằng chứng ngắn; trigger ghi rõ đích. Trang nghiệp vụ cho nhiều bảng, lọc nâng cao, chọn revision, thao tác dài hoặc manual. Panel có tiêu đề, breadcrumb ngữ cảnh ngắn (ví dụ “Kỳ tháng 10 · Nhóm 00017”), “Đóng” và “Mở trang đầy đủ” nếu có đích. Dòng bằng chứng trình bày số hai phía, khóa, metric, ID run/snapshot ở chi tiết, rule version và danh sách thành viên mỗi phía, sau đó tệp/sheet/dòng/cột. Không tự rút lineage về một thành viên; ghi rõ “Đang hiển thị … trong …” nếu API giới hạn. Panel chỉ đọc; CTA chuyển trang cho workflow cần sửa. Dock và overlay theo mục 1, không có panel thứ hai. Khi đóng về trigger/trật tự phù hợp, khôi phục neo transcript; chờ dữ liệu cập nhật nếu trigger nằm sau “Tải tin nhắn trước”. Khi request chuyển scope, xóa nội dung cũ trước tải mới.

**Dữ liệu và lỗi.** `GET /api/runs/{run_id}/groups/{group_id}/evidence` trả group, rule, sources, `member_count`, `evidence_complete`, `field_evidence_complete`; API hiện giới hạn đến 100 bản ghi mỗi nguồn và 100 provenance mỗi record ở đoạn này, giao diện hiện có thêm giới hạn hiển thị ô. `GET /api/evidence/{evidence_id}` trả bằng chứng trường/source, `POST /api/agent/source-rows` nhận project/table/row hợp lệ. Phân trang evidence toàn bộ hoặc bằng chứng ngoài giới hạn là dependency tương lai, không thêm điều khiển giả. Link evidence bắt buộc thuộc tài nguyên được phép. Đóng panel không thực hiện lưu/approve. Chưa có route mở một số loại panel trong hash thì có thể dùng điều hướng trang nghiệp vụ hiện có, chỉ thêm state frontend sau khi có quyết định.

**Nghiệm thu.** Nhóm 1:N/N:1, flags bị cắt, nguồn không còn quyền, xử lý link chéo run, file/sheet/dòng có tên dài, mở panel khi đang đọc trên cao, quay lại đúng trigger, không chồng drawer/modal, mobile/zoom giữ scroll và focus.

### UX-S11 · Báo cáo, chọn run và xuất

**Mục tiêu và điểm vào.** Chọn lần đối soát và xuất đúng tập. Đi từ sidebar, run hoặc nút Chat. **SOURCE_VERIFIED** báo cáo sử dụng cùng `ReconciliationStudio`; export API của trang hiện xuất toàn run. Chat hỗ trợ `FULL_RUN` và `DISPLAYED_QUERY` đã ghim cùng run, phân trang và truy vấn.

**PROPOSED.** Một bản tóm tắt report dùng snapshot đã xác minh, với nguồn, kỳ, tiền tệ, lần chạy, thời điểm trạng thái ngoại lệ được chụp. Khối Xuất liệt kê định dạng CSV/XLSX và phạm vi thực tế ngay trước nút. Bốn khái niệm được ghi rõ: “Toàn bộ lần đối soát”, “Tập khớp bộ lọc”, “Trang đang xem”, “Dòng đã chọn”. Hiện tại trang Báo cáo chỉ tạo file toàn run; Chat hỗ trợ đúng trang query đã hiển thị của verified run, giữ filter/sort/offset/limit đã xác minh. Chỉ hiển thị lựa chọn được endpoint hỗ trợ; hai phạm vi còn lại cần hợp đồng xuất mới và phê duyệt sau. Không dùng số tổng bộ lọc làm số dòng file khi file chỉ xuất trang. Job tiến triển hiển thị riêng, “Tải CSV” hoặc “Tải Excel” chỉ khi thành công. Thể hiện file bất biến theo lần tạo/format/revision và trạng thái review tại lần xuất; không hứa làm mới vì review vừa thay đổi. Mobile đặt khối xuất dưới header tóm tắt, tránh overflow nhóm nút.

**Dữ liệu và lỗi.** `POST /api/runs/{run_id}/exports?format=…` trả job/export id, `GET /api/jobs/{job_id}`, `GET /api/exports/{id}`, `GET /api/exports/{id}/download`. Chat xử lý `AgentIntent.export_scope` và `DownloadBlock`; giữ query đã ghim qua backend, không gửi DSL không được duyệt trực tiếp đến endpoint full run. `review_state_scope`, `review_state_as_of` và `revision` phân biệt trạng thái lúc tạo. Khi lỗi trước/đang xử lý, tra job trước thử lại. Không public link hoặc token. Viewer không sinh file mới; tải file đã có theo quyền.

**Nghiệm thu.** Oracle cho toàn run và đúng trang lọc/sắp xếp, khóa ghim khi người dùng đổi trang sau yêu cầu, reload job, CSV/XLSX precision/Unicode/formula injection, download chưa sẵn sàng/404, same snapshot, format, first-generation metadata. Không xác nhận export tùy ý hoặc row selection khi API chưa có.

### UX-S12 · Cài đặt và quyền

**Mục tiêu và điểm vào.** Biết đang ở không gian nào, vai trò, policy và giới hạn tệp. **SOURCE_VERIFIED** [WorkspaceSettings.tsx](../../frontend/src/WorkspaceSettings.tsx) hiển thị tài khoản thiết bị, quyền, AI/privacy và giới hạn theo `GET /api/settings`. Đây là phần hiển thị thông tin hiện tại, không phải màn quản trị đầy đủ.

**PROPOSED.** Bố cục một cột có nhóm Tài khoản và không gian, AI và quyền riêng tư, Giới hạn tệp, và tùy chọn trình bày ở frontend nếu chủ dự án chọn lưu cục bộ. Thiếu thông tin hiển thị “Chưa có thông tin” thay vì giả định. Chỉ hiện thông tin kỹ thuật có ích khi có quyền và vấn đề thực, mở chi tiết thay vì gắn nhãn vào shell. Các quyền đổi hồ sơ/thành viên, sửa policy provider/quota hay thao tác hệ thống phụ thuộc hợp đồng quản trị được duyệt. Nếu không có endpoint, chỉ mô tả mục tiêu và trạng thái, không thiết kế control trông như chạy được. Reuse policy thực tế nằm ở mapping manual theo quyền owner, giữ đường dẫn đúng. Model theo lần gửi vẫn đặt trong composer theo `GET /api/assistant/models`.

**Dữ liệu và lỗi.** `GET /api/session`, `GET /api/settings`, `WorkspaceSettings`, `AssistantModelOption`. DTO chỉ dùng config flags, nhãn model và hạn mức được phép, không hiển thị secret, endpoint nội bộ, storage path hoặc raw operator log. 403/401 xử lý theo mục 1; liên kết quay về giữ đúng hội thoại.

**Nghiệm thu.** Viewer/editor/owner, Cloud bị chặn/hết ngân sách/khả dụng, Qwen chưa sẵn sàng, giới hạn thật, keyboard details, không lộ config secret, Settings→Chat giữ draft và không gửi request.

## 4. Ngữ pháp phản hồi AI

**PROPOSED.** Mỗi turn đi theo thứ tự `tóm tắt (nếu cần) → dữ liệu tối thiểu → hành động liên quan → xem sâu`. Một câu hỏi thông thường chỉ cần văn bản. Chọn khối theo dữ liệu đã có và tác vụ, không sinh khối cho đủ hình thức. Nguồn renderer là discriminant `ResultBlock.type`, `ReviewRequest.kind`, `WorkflowView.state`, hoặc thông tin job/answer typed, không phân loại bằng màu, chuỗi title, regex hoặc văn bản model tự nhận. Bốn lớp thông tin phải đọc được bằng chữ: dữ liệu thô/chưa xác nhận, AI gợi ý, quyết định người dùng, kết quả đã kiểm chứng. Một câu trả lời có thể chứa nhiều lớp, gắn nhãn đúng từng khối.

Quy tắc chung cho cả 15 loại bên dưới. Khối nằm dưới nội dung cùng turn, có title rõ khi nhiều khối, Tab tới hành động theo thứ tự đọc. Nội dung trạng thái chỉ được thông báo khi đổi trạng thái có ý nghĩa. Với mobile, khối xếp một cột, không mở overlay tự động; bảng/biểu đồ có cuộn nội bộ hoặc hành động xem sâu. Trạng thái chờ, thiếu dữ liệu, lỗi hoặc bị thu hồi giữ chỗ ở đúng turn và giải thích tiếp theo. Ví dụ tiếng Việt dùng dữ liệu giả để minh họa copy, không phải số đo hiện trạng. Bỏ khối khi không có payload phù hợp. Với loại dữ liệu còn thiếu, dùng notice đúng ngữ nghĩa.

| Loại và mục đích | Tối thiểu và ví dụ | Chi tiết, hành động, panel và mobile | Hợp đồng, trạng thái và gate |
| --- | --- | --- | --- |
| 1 · Văn bản trả lời | Văn bản ngắn có chủ thể và việc cần làm nếu có. “Bạn có thể đính kèm tệp CSV hoặc Excel ở đây.” | Inline, xuống dòng tự nhiên. Chỉ đặt link/action nếu đích có thật. Bàn phím tới link, screen reader đọc theo thứ tự. | `AssistantMessage.text` hoặc `AssistantAnswer.lines`; giữ classification/fact refs nếu có. Không dùng text làm xác nhận quyền hoặc dựng kết quả tài chính. |
| 2 · Tệp vừa tải | Tên và số tệp được server nhận, dự án và bước đang làm. “Đã nhận 2 tệp. Đang đọc dữ liệu.” | Inline gọn; chi tiết gồm trạng thái từng tệp, tệp tái dùng/tệp lỗi. “Xem dữ liệu” chỉ sau có dataset ref. Tên dài có cách đọc đầy đủ và danh sách thu gọn. | Receipt từ `POST /api/agent/attachments`, `Dataset`, job/steps. Pending upload không được nói đã lưu; một tệp lỗi không thay trạng thái các tệp đã thành công. |
| 3 · Tiến trình | Tên bước và trạng thái. “Đang kiểm tra cách ghép cột.” | Inline một dòng với `role=status`; mở các bước và kết quả đã lưu bằng disclosure. Dừng bước tiếp theo khi có hành động và quyền. Không báo phần trăm suy đoán. | `ProgressBlock`, `WorkflowView`, `WorkflowStep`, `Job`. Tách queued/running/waiting/partial/failed/blocked/cancelled; không lặp nội dung trong thẻ review. |
| 4 · Chuẩn hóa | Nguồn/phiên bản, số dòng và số lỗi, trạng thái. “Đã chuẩn hóa 97 dòng. Có 3 dòng cần kiểm tra.” | Inline tóm tắt, “Xem dữ liệu đã chuẩn hóa” và “Xem dòng lỗi” khi có refs; chi tiết mở panel hoặc Data. | `DatasetBlock`, `Canonical`, `Preview`; chỉ hiển thị hoàn tất khi artifact đã công bố, giữ quality/stale và provenance. Prepared dùng nhãn “Bản chuẩn bị”, không render thành canonical. |
| 5 · Hỏi làm rõ | Một câu hỏi về dữ kiện thiếu, tên nguồn/run liên quan. “Bạn muốn xem tiền đã trả hay tổng đơn?” | Inline `Clarification`; tùy chọn server hoặc nút “Bổ sung thông tin” focus composer có scope. Hủy liên kết bằng nút có label. Mobile không giấu câu hỏi sau bàn phím. | `ReviewRequest.kind=CLARIFICATION`, `options`, `reply_intent`, `pending_reply_job_id`. Không gọi câu trả lời là duyệt hoặc cho chỉnh typed intent tùy ý. Hết hạn yêu cầu mở lại. |
| 6 · Đề xuất ghép cột | Bảng, “mỗi dòng là gì”, khóa và thay đổi nổi bật. “Đề xuất dùng Mã đơn để nhận diện mỗi đơn.” | Inline tóm tắt. Chi tiết trường đã kiểm tra/cần xác nhận, preflight và bằng chứng theo mục 5. Mở chỉ đọc khi đi sâu. | `NormalizationDraft`, `MappingAssessment`, `ReviewRequest.kind=MAPPING`. Chỉ dùng “đề xuất” trước approval; thiếu facts hiện điều còn thiếu. |
| 7 · Đề xuất đối soát | Hai nguồn đúng vai trò, kỳ, khóa, metric và điều còn thiếu. “Đề xuất đối chiếu Mã đơn cho kỳ tháng 10.” | Inline tóm tắt đề xuất/candidate, chi tiết có readiness, rule và nguồn. Nếu nhiều phương án, radio với hậu quả từng phương án; không mặc định chấp nhận. | `ReviewRequest.plan`, `planning_request`, `planning_candidates`, `Plan`/proposal. Kỳ, coverage, tiền hay nguồn chưa rõ vẫn cần bổ sung; candidate không phải rule đã duyệt. |
| 8 · Quyết định nghiệp vụ | Dữ kiện, bằng chứng, rủi ro, tác dụng và CTA cụ thể. “Duyệt ghép cột và chuẩn hóa tệp này.” | Một `ReviewCard` cho mỗi quyết định có token hợp lệ. Có nút sửa/bổ sung, xem bằng chứng chỉ đọc. Khi workflow có đề xuất và quyết định, dùng cùng thẻ với các vùng, không nhân đôi. | `ReviewRequest` + preflight/validate và quyết định typed. Action chỉ khi đủ quyền và trạng thái server cho phép; expired/stale không dùng token cũ. Duyệt xong hiển thị receipt nếu DTO có. |
| 9 · Kết quả tài chính | Kỳ, trạng thái kiểm chứng, đơn vị và scope. “Có 7 nhóm lệch tiền trong kỳ này.” | Inline tối đa vài chỉ số phù hợp câu hỏi. “Xem kết quả”/“Xem ngoại lệ” mở đúng run. Chi tiết mẫu số, currency và excluded ở panel/trang. Screen reader có nhãn chỉ số và số. | `FactsBlock`, `AnswerFactSet`, `MetricSnapshot`, refs cùng run; `PARTIAL_VERIFIED` nêu giới hạn. Không công bố facts nếu gate verification thất bại hoặc scope khác. |
| 10 · Bảng truy vấn | Tên nguồn, cột đúng label, lọc/tổng/trang. “Trang 2 · 25 dòng trong 64 dòng khớp.” | Inline bảng gọn nếu vừa; xem sâu cho nhiều cột. Caption, semantic headers, nút phân trang/aria-sort khi hỗ trợ, hàng bằng chứng theo ref. Không chuyển chỉ số thứ tự thành business key. | `TableBlock`, `QueryResult`, `query_selection`; `/query-pages` đổi offset/sort hợp lệ, không sửa query gốc. `truncated`, `warnings` và `verification_status` phải hiện khi ảnh hưởng. |
| 11 · Biểu đồ | Tên, loại đơn vị, kỳ, population, độ đầy đủ. “Phân bố 64 nhóm giao dịch trong kỳ.” | Chart chỉ khi có dữ liệu có ích, kèm bảng/danh sách bằng số chính xác. Xem sâu nếu cần đọc nhãn dài. Tooltip có đường tương đương bằng keyboard, không dùng màu là tín hiệu duy nhất. | `ChartBlock`, points/period/timezone/refs/completeness. Nhãn cắt hoặc top subset phải nêu. Không tự dựng chart tiền từ dòng trộn currency hoặc facts chưa kiểm. |
| 12 · Bằng chứng | Tên nguồn, run hoặc tệp/sheet/dòng, loại bằng chứng. “Tệp đối ứng · sheet Thanh toán · dòng 48.” | Link inline “Xem bằng chứng”; dock/drawer theo mục 1. Mở đúng nhiều thành viên, “Quay lại” trả focus. | `FactReference`, `SourceEvidence`, `EvidenceRef` và endpoint scoped. Thiếu/không còn quyền: mô tả không mở được và giữ nguồn hợp lệ còn lại, không dựng raw dữ liệu. |
| 13 · Tệp xuất | Định dạng, run, phạm vi và trạng thái. “Excel đã sẵn sàng · 25 dòng của trang đang xem.” | Trạng thái đang tạo inline. Link tải chỉ khi backend có file; chi tiết revision, thời điểm review và phạm vi nếu DTO có. Nếu chưa có số dòng file trong DTO, dùng mô tả phạm vi đã ghim, không tự ghi con số. | `DownloadBlock`, job/export metadata; `displayed_query` và query ghim backend. Không nhầm full run, tất cả khớp bộ lọc và trang. |
| 14 · Lỗi có thể phục hồi | Việc bị gián đoạn, dữ liệu còn an toàn và đúng bước tiếp. “Chưa tải được kết quả. Cập nhật hội thoại để xem lại.” | Lỗi cục bộ dưới hành động. Nút “Tải lại” cho đọc, “Cập nhật” nếu delivery chưa rõ, “Thử lại” cho thao tác an toàn. Có mã hỗ trợ trong details. | `ApiError.code`, status job và error envelope. Cùng key/payload khi hợp đồng cho phép; không thêm retry mù hoặc tự đổi provider. |
| 15 · Lỗi không thể tiếp tục | Lý do nghiệp vụ và đích hợp lệ. “Quy tắc chưa xác minh. Mở Đối soát để kiểm tra phạm vi.” | Inline notice có hành động thay thế theo quyền. Không có CTA gây lại lỗi bằng dữ liệu y cũ; focus lỗi khi do thao tác người dùng. | Ví dụ `RUN_NOT_VERIFIED`, `FORBIDDEN`, `STALE_CONTEXT` không thể dùng bản cũ. Không nói “mất dữ liệu” nếu chưa biết; không lộ scope khác. |

**SOURCE_VERIFIED.** Sáu discriminant kết quả thực tế là `progress`, `dataset_summary`, `table`, `facts`, `chart`, `download`. Chín dạng UX còn lại dùng nguồn kiểu dữ liệu hiện có ở trên. Không cần thêm chín DTO mới để triển khai grammar. Tham chiếu [AgentResultBlocks.tsx](../../frontend/src/AgentResultBlocks.tsx), [agentTypes.ts](../../frontend/src/agentTypes.ts), [assistantTypes.ts](../../frontend/src/assistantTypes.ts), [contracts/agent.py](../../backend/studio/contracts/agent.py) và [contracts/data_query.py](../../backend/studio/contracts/data_query.py).

## 5. ReviewCard, dữ kiện tối thiểu và vòng đời quyết định

```text
Cần bạn xác nhận · [Tên nguồn hoặc cặp nguồn]
[Đề xuất và bằng chứng chính, 1–2 câu]
[Chỉ tiêu/đơn vị/basis] [Kỳ, grain hoặc khóa] [Điều còn thiếu/rủi ro]
[Chi tiết có thể mở: bảng trường, bằng chứng và kiểm tra]
[Chỉnh lựa chọn / Bổ sung]                          [Duyệt và …]
```

| Đối tượng | Dữ kiện nhìn thấy trước CTA | Chi tiết theo nhu cầu | Chốt kỹ thuật |
| --- | --- | --- | --- |
| Mapping | Tệp, sheet, version, ý nghĩa mỗi dòng, khóa hoặc thiếu khóa, các cột tiền với currency/unit/gross-net/semantic metric, định dạng ngày/locale nếu ảnh hưởng, số dòng lỗi dự kiến, scope preflight và hành động sau duyệt. | Nguồn → trường, kiểu, transform được phép, bản mẫu và bằng chứng, thông tin cần bổ sung, ảnh hưởng theo trường. | `NormalizationDraft` và preflight cùng bản nháp. Xác nhận bản trích xuất nếu server yêu cầu, không dùng thống kê để tự kết luận nghiệp vụ. |
| Đối soát | Hai nguồn đúng revision/vai trò, grain mỗi nguồn và grain so sánh, thứ tự khóa ghép, 1:1/1:N/N:1, aggregation, kỳ/timezone, coverage/completeness từng nguồn, metric/currency/unit/basis, tolerance, cảnh báo partial và hệ quả sau duyệt. | Date field/time basis, snapshot và hạn quyết toán, thời hạn hiệu lực, filters, dấu/làm tròn, candidate, duplicate/fuzzy và bằng chứng nếu có. Nếu một chi tiết thay đổi số liệu phải tóm tắt trước CTA, giữ bản đầy đủ ở mở rộng. | `planning_request` thiếu dữ kiện chỉ là bản nháp. Chỉ mở duyệt với plan đủ và gate đạt. Có `invalid_rows_reviewed` khi áp dụng. |
| Làm rõ | Một câu hỏi, phạm vi và lý do nếu người dùng cần để trả lời đúng. | Nguồn hiện có, lựa chọn server, nhập nội dung hoặc tiếp tục có scope. | `CLARIFICATION` trả lời qua `replies` hoặc typed option qua `decisions`. Cả hai ghi câu trả lời và không phải approval nghiệp vụ. |
| Batch mapping | Từng nguồn và tóm tắt quyết định riêng, danh sách nguồn sẽ duyệt, hậu quả sau thao tác. | Mở từng thẻ để kiểm preflight, khác biệt currency/grain/key và lỗi. | `decisions/batch` 2–3 mapping, mỗi nguồn đúng một token và payload riêng. Dữ kiện chung chỉ điền nháp; không copy trạng thái duyệt. Backend xử lý trong transaction. |

Tóm tắt số đã kiểm tra kỹ thuật và ý nghĩa còn chờ riêng. Gắn nhãn “Đã kiểm tra định dạng” cho bằng chứng kỹ thuật, “Bạn đã xác nhận” khi có receipt, “Cần làm rõ” khi thiếu facts. Nội dung hệ quả dùng động từ theo luồng thật, ví dụ “Sau khi duyệt, hệ thống chuẩn hóa tệp này” chỉ khi workflow sẽ làm việc đó. Không ẩn currency/basis/grain/keys/scope/coverage/period/tolerance thích hợp sau “nâng cao”. Các mục không áp dụng bỏ có chủ đích; giá trị thiếu ảnh hưởng duyệt ghi “Chưa xác định” và CTA bổ sung. Không dùng checkbox để mặc định approve, mặc định chọn option, hoặc gây thay đổi ở panel chỉ đọc.

| Trạng thái UX | Điều kiện quan sát được | Hiển thị và hành động |
| --- | --- | --- |
| Gợi ý | Candidate/draft chưa có bước chờ quyết định hợp lệ. | Dòng đề xuất và chi tiết, không hiện nút duyệt có thể bấm. |
| Cần xác nhận | Review `OPEN`, đúng fingerprint/nonce, chưa hết hạn, workflow cho phép và có quyền. | Dữ kiện tối thiểu, lỗi thiếu facts, CTA chuyên biệt chỉ khi sẵn sàng. |
| Đang chỉnh | Local draft khác server hoặc đang preflight/lưu. | Giữ nội dung, khóa CTA khi chưa kiểm xong, báo lỗi sát trường. Chuyển scope không tự gắn draft sang nguồn khác. |
| Đã duyệt | `DECIDED` + kết quả mapping/contract thành công do server xác nhận. | Tóm tắt receipt và link kết quả đúng version. `DECIDED` của clarification hiển thị “Đã bổ sung”, không ghi đã duyệt. Nếu DTO lịch sử thiếu receipt, chỉ mô tả trạng thái server thực. |
| Đã từ chối | Mapping manual `REJECTED` hoặc bằng chứng từ chối tương ứng do server trả. | Cho xem lịch sử nếu có quyền. Agent hiện không có decision `REJECT`; nút “Dừng bước tiếp theo” của workflow khác với từ chối mapping. |
| Hết hạn | `expires_at` đã qua và backend không còn chấp nhận token. | “Mở lại thẻ” gọi renew khi hợp lệ. Nạp nonce mới, so nguồn và bản nháp, không tự gửi duyệt. |
| Xung đột / bản cũ | `STALE_CONTEXT`, `INVALIDATED`, revision/nguồn thay đổi, approval payload xung đột hoặc reply chưa xong. | Tải lại thẻ theo workflow, hiển thị điểm đã đổi nếu có dữ kiện; cho rà lại. Lưu nháp đã nhập đúng scope, không tự áp bản cũ lên bản mới. |
| Không có quyền | UI role không cho phép, hoặc server trả 401/403/404. | CTA tắt hoặc ẩn theo tình huống, giải thích khả năng đọc và người có quyền. Bỏ dữ liệu đã bị thu hồi. |
| Cần tiếp tục | Job/draft đã lưu và chưa hoàn tất; người dùng quay về. | Mở đúng thẻ và job hiện có. Nếu còn chờ bổ sung, focus câu hỏi. Không gửi lại model vì reload. |
| Đang xử lý | Job reply/preflight/decision còn chạy hoặc gửi chưa rõ. | Báo bước cụ thể, chặn gửi trùng, tra job/receipt. Hiện pending reply để phân biệt chưa có draft mới. |

**SOURCE_VERIFIED.** Review token chỉ có `OPEN`, `DECIDED`, `INVALIDATED`. Các nhãn UX còn lại là phép chiếu từ quyền, job, thời hạn và dữ kiện, không thêm enum. `POST /api/agent/mapping-preflight` kiểm bản nháp, `GET /api/agent/workflows/{id}` đọc trạng thái, `POST /api/agent/workflows/{id}/draft` lưu hoặc kiểm scope plan, `/renew-review` làm mới token, `/replies` tiếp nhận câu trả lời, `/decisions` và `/decisions/batch` thực thi typed decisions, `/cancel` dừng bước kế tiếp nếu server chấp nhận. Mọi lệnh ghi kiểm scope và actor theo backend. Các thao tác thẻ cần nonce, fingerprint và thời hạn đúng theo hợp đồng từng endpoint. Giữ hành vi idempotency hiện có. Khi renew, chỉ nạp token theo response mới. Reuse mapping/rule chỉ theo điều kiện tương thích đã duyệt; reuse đối soát mở bản nháp mới, luôn hỏi lại nếu điều kiện/coverage không còn phù hợp. [Agent API](../../backend/studio/agent_api.py) · [Mapping/Reconciliation contract](../DATA_CONTRACTS.md).

## 6. Hợp đồng thành phần dùng chung

Các props dưới đây là tên khái niệm của dữ liệu đã có. Mỗi control tái sử dụng quy tắc mặc định/hover/focus/disabled/pending/error từ Design System. Không tạo component mới nếu tách phần hiện có đã đủ. Ranh giới cho điểm dữ liệu, mode và quyền nhất quán giữa Chat, Dữ liệu, Đối soát và Báo cáo.

| Thành phần | Dữ liệu vào, trạng thái và biến thể | Tương tác, a11y, responsive | Tái sử dụng và ràng buộc |
| --- | --- | --- | --- |
| AppShell | `location, project, role, readiness, sidebarMode, activeDetail`; sẵn sàng, chưa có dự án, lỗi kết nối. | Skip link, main và landmarks rõ; focus khi điều hướng, chỉ một overlay. Rail/drawer theo viewport. | `App`, `navigation`. Không mở đích ngoài scope khi bootstrap chưa xác nhận. |
| Sidebar | Danh sách đích, active, expanded/rail/drawer, khả năng thao tác. | Link có tên, icon ẩn với assistive tech, `aria-current`; Escape trả focus, không trap rail. | Giữ đích hiện hữu; việc nhóm mục chờ quyết định chủ dự án. |
| PageHeader | Tiêu đề, tên dự án, ref nguồn/run, trạng thái và CTA. | Một H1 theo trang; toolbar phụ có label; reflow và cho wrap thông tin quan trọng. | Header hiện có trong `App`; không lặp title/breadcrumb. Badge theo status server. |
| ProjectSelector | `Project[]`, selected, tìm kiếm, tổng, loading/error, action quyền. | Combobox/listbox, mũi tên/Enter/Escape, announce loading và item đang focus. Kích cỡ popup theo màn hình. | `ProjectSelector`; role từ session, dữ liệu phân trang server. |
| ChatComposer | `draft, files, modelOptions, activeJob, reviewBinding, limits, canUpload`; empty/multiline/disabled/error. | Textarea có label, Enter/Shift+Enter/IME, file picker có phương án bàn phím; safe-area, hiện lý do disabled. | `AssistantStudio`; cùng context/key khi retry, không suy policy từ UI. |
| ChatMessage | `AssistantMessage`, `answer`, `workflow_id`, timestamp/model. | Role label và heading khi cần; thông báo phần mới; metadata trong details, mobile wrap. | `AssistantStudio`; không mất lớp verified/hypothesis hay đổi model của turn cũ. |
| WorkflowSummary | `WorkflowView.state`, steps, error, refs và actions. | Một câu trạng thái, disclosure các bước; không announce mỗi poll; cancel có label chính xác. | `AgentWorkflowPanel`; không suy tỷ lệ tiến độ, không thay server cancel semantics. |
| ReviewCard | `ReviewRequest`, readiness, draft, preflight, capability, receipt. | Disclosure, label trường, focus lỗi, không có CTA trùng ở panel; mobile một cột. | `ReviewCard`, `MappingStudio`; token/expiry và typed payload mục 5. |
| Clarification | `question, options, reply_intent, pending_job`; open, waiting, answered/expired. | Một câu hỏi, lựa chọn đọc được; focus composer, không mặc định chọn. | `ReviewCard` biến thể CLARIFICATION; trả lời khác với duyệt. |
| ContextPanel | `kind, sourceRefs, returnAnchor`; loading/ready/truncated/error/denied. | Dock landmark, overlay dialog, nút đóng/quay lại, focus và scroll phục hồi. | `AssistantDataDrawer`, result modal, `ReconciliationEvidence`; chỉ đọc, một scope. |
| DataTable | `columns, rows, sourceVersion, total, offset, limit, sort, supportedActions`; skeleton/empty/error. | Native table/caption, `scope=col`, aria-sort chỉ cho cột hỗ trợ, nút hành động tên theo dòng, cuộn ngang có nhãn. | `DataTable`, `AgentResultBlocks`, Reconciliation; server pagination, không tính tiền hoặc thay null. |
| Filters | `supportedFilters, selected, totalMatching, scope`; áp dụng, reset, pending/error. | Label theo nội dung, keyboard, báo số khớp sau lọc; mobile dùng disclosure/drawer cùng chỗ. | Kết hợp input hiện tại; đổi filter đặt offset về đầu, không đổi run/source. |
| KPI | `MetricSnapshot`, label, numerator/denominator, precision/scope, partial note. | Mô tả bằng chữ và số, không dùng màu duy nhất; mobile stack. | Tái dùng view snapshot; không tính phần trăm hoặc tổng từ trang hiện tại. |
| Chart | `ChartBlock` hoặc snapshot distribution đúng scope, completeness, labels, unit. | Tiêu đề/caption, bảng số tương đương, reduced motion, co theo vùng, keyboard không phụ thuộc hover. | ECharts hiện có; tooltip/label dùng dữ liệu gốc chính xác, không suy chart từ text. |
| EvidencePanel | `SourceEvidence`, `FactReference`, source row, completeness. | Trật tự nguồn→dòng→cột, tiêu đề phía trái/phải, list thành viên và nút quay lại. | `ReconciliationEvidence`/modal evidence; giữ giới hạn và scope backend. |
| ExportPanel | `runId, format, scope, job, exportMeta, canCreate`; idle/pending/ready/failed. | Ghi phạm vi trước nút, keyboard chọn format, link download có tên rõ, status update theo job. | `ReconciliationStudio`/DownloadBlock; API full run hoặc typed Chat scope ghim. |
| Modal | `open, title, returnFocus, actions`; mở/chờ/lỗi/đóng. | `dialog` có tên, trap, Escape, cuộn trong, focus khôi phục. Confirm destructive focus lựa chọn an toàn. | `Modal` dùng chung; không hủy server job ngầm khi đóng. |
| Drawer | `open, title, role, returnAnchor`, mobile/overlay. | Escape, trap và inert nền cho overlay, thao tác đóng luôn thấy. Giữ một bề mặt overlay. | Biến thể từ primitive dialog/context, không tạo focus behavior riêng cho mỗi trang. |
| Dropdown | `options, selected, disabledReason, loading`. | Native select khi chọn giá trị, menu khi thao tác, tên/keyboard đầy đủ, không cắt bởi container. | Model selector, project selector; không suy choice khả dụng từ tên. |
| Tooltip | Trigger label + giải thích tùy chọn. | Hover và focus, Escape, không giữ focus hoặc chứa action. Nút icon vẫn có tên truy cập độc lập. | Dùng cho rail và trợ giúp ngắn; dữ kiện quyết định không đặt chỉ trong tooltip. |
| Notice | `tone, summary, retryAction, diagnosticCode`; info/warning/error/status. | Alert cho lỗi cần chú ý ngay, status cho diễn tiến, text và icon có nghĩa; không lặp live announcement. | `Notice`, `Badge`; dùng mã đã redacted, không hiển thị stack/raw config. |
| Loading | `target, indeterminate, countIfKnown`; list/row/action. | Skeleton giữ bố cục, aria-busy/status riêng, reduced motion, không chặn cả shell vì một pane. | `Spinner` cho action ngắn, placeholder tĩnh cho khối dữ liệu. |
| EmptyState | `reason, target, capability, filterState`; chưa có dữ liệu hoặc không khớp lọc. | Tiêu đề một dòng, bước tiếp hợp lệ hoặc xóa lọc, focus hợp lý khi đổi state. | Chỉ hiện sau kết quả đọc thành công và đúng scope, không nhầm lỗi/đang tải. |
| ErrorState | `code, userMessage, recoverability, action, scope`. | Liên kết lỗi form bằng aria-describedby; focus lỗi từ mutation, retry có tên. | `ApiError`, `errorText`, error envelope; xử lý delivery unknown và forbidden khác nhau. |

## 7. Hợp đồng điều hướng và giữ ngữ cảnh

| Tương tác | Hợp đồng chuyển giao | Quay lại, refresh và quyền |
| --- | --- | --- |
| Chat → Data | Nếu đọc nhanh dùng Context Panel với project/dataset/table/version đã chọn. Nếu cần sửa hoặc lọc nhiều, mở Dữ liệu đúng nguồn bằng deep link hiện có. | Đóng hoặc back giữ transcript, composer draft và vị trí cũ. Nguồn 404/403 không thay bằng nguồn khác. |
| Chat → Review | Neo tới thẻ cùng conversation/workflow/review. Phần bổ sung có binding tới nonce/fingerprint hiện hành. | Thẻ đổi thì nạp lại và rà soát. Panel bằng chứng không thực thi approval. |
| Chat → Đối soát | Mở draft và cặp canonical được phép nếu đã có, hoặc đích chọn nguồn khi thiếu. | Giữ draft Chat; không lấy rule/latest để điền đích nếu có plan explicit. Nếu draft hết quyền, giải thích. |
| Chat → Kết quả | Đi từ fact/run, carry `run_id` và mục đích đọc. Nếu chưa verified chỉ tới trạng thái công việc. | Đổi tab giữ run và snapshot; không tự chuyển sang run mới. |
| Chat → Bằng chứng | `projectId, runId, groupId` hoặc `projectId, tableId, row` đúng ref. | Giữ neo trigger khi đóng; handle evidence không còn quyền/không đầy đủ. |
| Chat → Xuất | Lựa chọn thật giữa run và trang query đã xác minh; preview tên/scope/format. | Mở job/export hiện có sau reload. Không xuất lại do quay lại màn hình. |
| Kết quả → Chat | “Hỏi về kết quả” mang đúng `run_id`, có thể group/case; tạo/chọn hội thoại hợp lệ cho scope. | Draft cũ giữ trong key cũ; không đổi context hội thoại hiện có sau lưng người dùng. |
| Bằng chứng → Chat | Cho câu hỏi theo cùng group/nguồn nếu backend hỗ trợ. Gợi ý điền nháp, không tự gửi. | Nếu người dùng chỉ quay lại, focus về trigger và giữ scroll. |
| Cài đặt → Chat | Khôi phục project, conversation và draft đã chọn sau khi revalidate session/policy. | Model cũ được phép thì giữ; nếu hết khả dụng nói rõ và cho chọn, không tự gửi. |
| Lịch sử → Hội thoại | `GET` đúng ID thuộc actor/project. Giữ nhãn trạng thái job và model lịch sử. | Nếu ID bị xóa/thu hồi, mở lại danh sách trong cùng project có notice. |
| Chuyển dự án | Cất nháp đúng owner/project/conversation, đóng panel và hủy fetch cũ. Reset filter/selection không thuộc phạm vi mới. | Chỉ khôi phục lựa chọn còn quyền. Không reset workspace hoặc chạy job ngoài scope. |
| Back/forward | Phản chiếu URL hợp lệ, cập nhật state có kiểm tra; các chuyển đổi tạm (sort/focus/overlay) theo thiết kế history, không thêm entry cho mỗi poll. | Không tái gửi mutation. Tương thích hash cũ và xử lý `popstate`/thay đổi hash. |
| Refresh/reopen | Revalidate session và ID, phục hồi đúng draft/query selection/position nếu đã lưu an toàn và còn scope. | Server là nguồn sự thật cho job, approval, run và quyền; dữ liệu máy cục bộ chỉ hỗ trợ phục hồi UI. |

Nếu phải chuyển đổi local state, kiểm các key hiện có `studio.project`, `studio.run.<project>`, `studio.conversation.<project>`, nháp Assistant theo owner/context và `studio.data-view.<owner>.<project>.<dataset>`; phân biệt state trình bày với state nghiệp vụ. Giữ draft cũ có thể đọc theo scope; test profile đã có key cũ, private storage bị chặn và version không còn hợp lệ. Các key mới có namespace/version, tránh đưa dữ liệu người dùng vào URL hoặc log, tránh dùng localStorage cho payload công việc tài chính. Chỉ xóa trạng thái không thuộc scope khi chuyển hoặc mất quyền, không xóa nháp dự án khác.

## 8. Ma trận chuyển trạng thái

| Hiện tại | Hành động | Đang tải/xử lý | Thành công → trạng thái sau | Thất bại → phục hồi |
| --- | --- | --- | --- | --- |
| Không có tệp hoặc đã chọn tệp | Gửi upload qua Chat hoặc Data | Chặn nhấn trùng, hiển thị tên và số tệp, chờ receipt | Chấp nhận → `UPLOADED`/job parse → đọc/chuẩn bị theo kết quả server | File invalid/quota/403 → báo theo tệp; delivery chưa rõ → kiểm receipt/key, giữ tệp đã nhận |
| Đã tải/đang đọc | Mở lại nguồn hoặc chờ job | `QUEUED/RUNNING/RETRYABLE_FAILURE`, không giả percent | Raw/Prepared có ref → xem; có review thì đúng thẻ; không gọi là canonical | `FAILED/BLOCKED` → cảnh báo, giữ raw và kết quả còn dùng được |
| Mapping cần quyết định | Sửa/bổ sung facts | Preflight đúng draft hoặc reply pending | Thấy bản diễn giải, nếu đủ → chờ duyệt riêng | Lỗi định dạng/preflight/nguồn cũ → giữ draft, focus trường và tải đúng ref |
| Mapping đủ điều kiện | Duyệt một thẻ hoặc batch được hỗ trợ | Decision gửi một lần, khóa CTA | `DECIDED` + receipt, chuẩn hóa theo luồng hiện hành → canonical hoặc partial | 403/409/validation → không đánh dấu đã duyệt; cập nhật thẻ/receipt; batch không commit dở |
| Câu hỏi làm rõ mở | Chọn option server hoặc nhập trả lời | Job review pending | Đã bổ sung → workflow tiếp tục hoặc hiện câu hỏi mới | Còn mơ hồ → giữ OPEN; stale/expired → nạp lại, không biến thành approval |
| Thẻ hết hạn/xung đột | Mở lại/refresh | Đọc scope, renew nếu server cho | Token mới → xem lại nội dung rồi mới duyệt | Đổi nguồn/không quyền → bản cũ vô hiệu, hướng dẫn chọn nguồn hợp lệ |
| Nguồn chuẩn hoặc rule mẫu | Chọn nguồn, kiểm phạm vi hoặc reuse | Đọc catalogue và validate | Plan đủ → chờ duyệt; thiếu dữ kiện → chỉ bổ sung phần thiếu | Schema drift/coverage thiếu → hướng dẫn sửa, giữ cặp nguồn hợp lệ và nháp |
| Plan chờ duyệt | Duyệt quy tắc | Khóa thao tác trùng, server kiểm role/revision | Approved contract → CTA chạy hoặc job theo Agent workflow | Validation/403/409 → quay về bước kiểm điều kiện, không sinh run giả |
| Contract đã duyệt | Chạy đối soát | Job theo đúng run ID | `VERIFIED` hoặc `PARTIAL_VERIFIED` → kết quả đúng scope | `VERIFICATION_FAILED`/job thất bại → lý do, không publish KPI/export, giữ run cũ |
| Kết quả đang xem | Lọc/đổi trang/mở nhóm | Hủy đọc đã lỗi thời, giữ scope run | Render trang mới/bằng chứng, giữ snapshot; query Chat ghi selection | No results riêng; 403/404 giữ đích và bỏ dữ liệu thu hồi; retry đọc |
| Ngoại lệ đang mở | Ghi chú và cập nhật trạng thái | Lưu đúng case, khóa CTA | Cập nhật case và current count, snapshot giữ nguyên | Lý do thiếu/không quyền → focus lỗi, không cập nhật cục bộ thành đã xử lý |
| Báo cáo chọn scope | Xuất CSV/XLSX | Job export và status | File sẵn sàng → link download cùng revision, review as-of | Giữ selection và ref job; resolve delivery trước khi tạo lần mới |
| Chat có nháp | Gửi | Chặn IME/double send, lưu job/receipt | Append message → cập nhật cùng hội thoại | Network/provider/timeout → giữ text nếu chưa nhận; cập nhật nếu delivery chưa rõ |
| Provider lỗi hoặc bị policy chặn | Xem lý do, cập nhật, chọn model có quyền khi làm lượt mới | Đọc trạng thái model/job, không gọi lại mặc định | Cùng hội thoại đọc lại kết quả, gửi mới chỉ theo thao tác rõ | Chỉ đọc dữ liệu đã lưu hoặc manual; không đổi ngầm model/budget |
| Dự án/hội thoại đang mở | Chuyển scope hoặc bị thu hồi quyền | Abort/reset selection cũ, kiểm quyền scope mới | Mở đúng dữ liệu, nếu quay về phục hồi nháp hợp lệ | Cũ không còn quyền → dọn hiển thị, báo lý do tổng quát và về đích hợp lệ |

## 9. Kiểm chứng đặc tả trước khi triển khai

- Bảo toàn các entry point và tests hiện có trong [frontend/e2e](../../frontend/e2e). Các nhóm `assistant-experience`, `assistant-layout`, `assistant-scroll`, `history-readiness`, `mapping-review`, `agent-plan-review`, `data-foundation`, `reconciliation`, `product-journey`, `user-acceptance` và `interface-quality` là điểm tái sử dụng. Kết quả của lần nghiên cứu theo báo cáo kiểm toán, kết quả phiên bản tương lai theo kế hoạch nghiệm thu.
- Dùng fixtures TEST/mô phỏng có oracle cho khác tiền, NULL/rỗng/0, 1:N/N:1, khóa ghép, nhiều sources/runs, quyền, stale/revoked, export exact page và partial verification. Mỗi case ghi revision, dữ kiện đầu vào, thao tác, trạng thái mong đợi và side effect bị cấm.
- Mọi viewport 390/768/1366/1440/1920 kiểm điều hướng, composer, review, bảng, evidence và export. Bổ sung 320 CSS px cho reflow, 200% zoom thật, thấp chiều cao, text scaling, Việt IME thật, bàn phím mobile thật, keyboard-only, screen reader và reduced motion. Bảng hai chiều chỉ cuộn trong vùng của nó. Không gắn PASS WCAG từ test tự động đơn lẻ.
- Nghiệm thu kiểm chứng từng đề xuất qua đối chiếu props/hợp đồng, workflow và bằng chứng. Cổng chủ dự án cần chốt là kiến trúc điều hướng, dock/drawer, bố cục Chat, review, density, chữ/màu và phạm vi state frontend. Các API bổ sung nêu ở trên là dependency tương lai, không nằm trong đợt nghiên cứu. Nhận định bố cục dựa trên Impeccable Operate/Shape được chốt lại theo nhiệm vụ, dữ liệu và khả năng kiểm chứng, không suy chất lượng chỉ từ thị giác.
