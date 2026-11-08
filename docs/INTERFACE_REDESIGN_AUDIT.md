# Phân tích giao diện trước đợt thiết kế lại

## W1–W5

**09/11/2026 · Nhánh `codex/full-interface-redesign`.** Chủ dự án miễn W0 riêng. Các phép kiểm bố cục và thao tác chạy trực tiếp trên bản build Frontend với API local. Nghiên cứu ở các phần dưới ghi lại trạng thái trước triển khai.

| Gói | Thay đổi chính | Bất biến kiểm chứng |
| --- | --- | --- |
| W1 | Sáu mục điều hướng, rail lưu theo trình duyệt, drawer trên màn hình hẹp và font hệ thống. Ngoại lệ đi cùng Đối soát. | Bảy route hash, quyền và picker dự án hiện hành. |
| W2 | Composer và văn bản theo cùng trục đọc. Panel dữ liệu, kết quả và bằng chứng mở theo tác vụ; dock khi còn đủ diện tích. Biểu đồ đổi hướng và giảm nhãn trục ở chiều rộng hẹp. | Ngữ cảnh, scroll, bản nháp, phân trang lịch sử và focus. Giữ giá trị chính xác bên cạnh biểu đồ. |
| W3 | Thẻ quyết định tách nguồn, kỳ, hiệu lực, khóa, đơn vị, chỉ tiêu và tác động. Workspace chia danh sách nguồn với phần đọc, cho chọn từng lớp. | Mapping preflight, nonce, expiry, quyền, revision, file gốc và fallback thủ công. |
| W4 | Thứ tự thiết lập rõ hơn. Phạm vi và tình trạng xác minh hiện trước KPI và hành động xuất. Bảng có căn số, danh sách số đếm thay thế biểu đồ và số bản ghi nguồn thực sự hiển thị. | Snapshot và Decimal từ Backend. Báo cáo toàn run khác với trang truy vấn đã ghim. Trạng thái liên kết, so sánh và xử lý ngoại lệ tách riêng. |
| W5 | Cài đặt theo vai trò và chính sách, mật độ bảng lưu trong trình duyệt, dừng hiển thị dữ liệu dự án khi API từ chối. | Tên và quyền chọn mô hình, API phân quyền và giới hạn tải hiện hành. |

### Kiểm toán thiết kế

- **Impeccable 4.8.1.** Hai lượt rà độc lập phát hiện trục composer đổi bề rộng, nhãn biểu đồ chồng trên mobile và panel mất lượt đã chọn khi chuyển bố cục. Đã sửa theo kích thước vùng và vòng đời state. Probe Chromium 1920 → 768 → 1920 giữ run, bộ lọc, Escape và focus về nút mở, có receipt trước/sau. Detector trả về mảng rỗng.
- **UI UX Pro Max 2.15.0.** Tra cứu cục bộ theo nhóm điều hướng, Chat, review, bảng, biểu đồ và cài đặt. Áp dụng phân cấp bằng chữ, căn phải số, nhãn trạng thái đi kèm màu, bảng cuộn riêng và quyền riêng tư theo ngữ cảnh. Bỏ gợi ý animation đếm, định dạng làm tròn cố định và palette riêng vì không phù hợp với hệ thống đã duyệt. Kết quả tra cứu ở các tệp `search-*.json` trong thư mục chứng cứ local.
- **Live TEST.** Vòng đầu có 54 ảnh trên bảy route, năm viewport chính và 320 CSS px/390×520. Không quan sát thấy tràn ngang toàn trang, lỗi JavaScript hoặc request ghi. Composer rộng 358, 736 và 760 CSS px theo chiều rộng khả dụng. Welcome và hội thoại cùng 760 px ở 1440. Ảnh Mapping lúc còn spinner chỉ minh họa trạng thái tải. Bằng chứng thẻ duyệt đầy đủ dùng fixture Playwright riêng.
- **Mock contract.** Chromium zoom trình duyệt thực 200% ở 1440×900 cho CSS 720×450. Chat, Dữ liệu và Báo cáo đều có doc/client width 720/720. Giả lập sự kiện IME và chiều cao thấp chỉ bao phủ xử lý phía ứng dụng.

### Cổng hồi quy và bàn giao

Source Backend/PostgreSQL qua 782 ca trong 205,79 giây, có một cảnh báo deprecation. TypeScript, ESLint, production build, Ruff và mypy được kiểm riêng. Nhật ký Chromium lưu theo từng vòng để phân biệt lỗi quan sát ở ứng viên trước sửa với bản phát hành. Chứng cứ local nằm trong `runtime/ui-redesign-20261109/`, gồm `implementation-matrix.json`, ảnh và phép đo, log kiểm thử và receipt của hai lượt critique. Runtime và dữ liệu TEST không vào Git.

Môi trường thử là Chromium trên Windows. Kiểm nhập tiếng Việt qua bộ gõ hệ điều hành, bàn phím vật lý trên mobile, iOS Safari/Android Chrome, screen reader thực và phóng riêng cỡ chữ 200% còn cần thiết bị hoặc UAT. Các bằng chứng hình ảnh chỉ áp dụng các trạng thái đã chụp. Chủ dự án thực hiện bước nghiệm thu sau khi ứng viên vượt qua các cổng kỹ thuật.

---

**Cập nhật quyết định ngày 09/11/2026.** Chủ dự án duyệt A cho [D01–D10](ui-redesign/OPEN_DECISIONS.md). Sáu mục và Chat-first là hướng hiện hành; phương án ba mục trong phần 3.C đã được thay thế. D03 dùng khoảng 760 CSS px làm mốc đọc, giữ trục composer ổn định, cho phép nội dung rộng dùng vùng phù hợp. D08 chọn breakpoint theo diện tích thật và kết quả prototype, không ép dock. Prototype **PENDING_VALIDATION**, triển khai **NOT_STARTED**. Phiên demo đã khôi phục trong [vòng vận hành](IMPLEMENTATION_STATUS.md). Số đo, ảnh và cổng bị chặn ở vòng nghiên cứu bên dưới là bằng chứng lịch sử.

Ngày kiểm tra: 08/11/2026. Phạm vi: AI Reconciliation Studio trong repository hiện tại. Đây là **phân tích và đề xuất**, không phải đặc tả đã được duyệt hoặc bằng chứng đã triển khai giao diện mới. Trạng thái phát hành được ghi riêng tại [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

## 1. Cơ sở đánh giá và giới hạn

- **[D] Quan sát trực tiếp:** đọc các component, DTO, route và CSS hiện hành; chụp 30 màn hình trên ứng dụng Docker đang chạy: AI Assistant, Dữ liệu, Đối soát, Báo cáo, Ngoại lệ, Cài đặt × 390/768/1366/1440/1920 px. Số đo nằm trong `runtime/interface-audit/measurements.json`, ảnh cùng thư mục. Đây là dữ liệu tổng hợp TEST.
- **[D] Kiểm chứng chức năng:** dùng các hành trình browser upload ba nguồn, review, chuẩn hóa, truy vấn, duyệt quy tắc, đối soát, bằng chứng và xuất file. Kết quả cụ thể và revision thuộc báo cáo nghiệm thu; ảnh một trạng thái không chứng minh toàn bộ workflow đạt.
- **[S] Tham khảo:** tài liệu chính thức của sản phẩm và design system ở mục 7. Không đăng nhập hoặc thao tác sản phẩm tham khảo, không copy branding/assets, không coi quảng cáo nhà cung cấp là kết quả đo của Studio.
- **[P] Đề xuất:** phương án cho đợt sau. Kích thước và token đề xuất cần prototype, kiểm tra tương phản, bàn phím và thử với chủ dự án trước khi chốt.

Không phát hiện body tràn ngang hoặc lỗi JavaScript trong 30 lần chụp. Điều này chỉ áp dụng sáu màn hình/trạng thái đã chụp; không chứng nhận WCAG hoặc bao phủ mọi dialog, dữ liệu dài, zoom, lỗi mạng và thiết bị. Computed font khai báo `Inter, "Segoe UI", Arial, sans-serif`; chưa xác nhận font nào thực sự render từng glyph tiếng Việt.

## 2. Kiểm kê giao diện, dữ liệu và quyền

Các route được quản lý trong [navigation.ts](../frontend/src/navigation.ts). URL hash lưu ID, không cấp quyền; Backend vẫn kiểm workspace/project. Trang thủ công phải được bảo toàn khi thiết kế lại. Không đổi semantic contract để phù hợp bố cục.

| Bề mặt/component hiện hành | Dữ liệu, thao tác và trạng thái cần bảo toàn | Vấn đề/định hướng cho đợt sau |
| --- | --- | --- |
| App Shell, `App.tsx`, sidebar/header | Session, workspace, role, project; điều hướng route và back/forward | Một header hiển thị dự án và ngữ cảnh hiện hành; thu gọn sidebar desktop; giữ drawer mobile. |
| `ProjectSelector.tsx` | Tìm kiếm/phân trang/chọn/tạo dự án theo quyền, giữ lựa chọn | Gộp nơi chọn dự án; tên dài phải đọc được, tránh nhiều selector cạnh tranh. |
| Landing `assistant`, `AssistantStudio.tsx` | Hội thoại mới, welcome, gợi ý, upload, chọn model và gửi yêu cầu | Giữ Chat là điểm bắt đầu; một hành động gửi chính, giảm câu hướng dẫn thường trực. |
| Lịch sử hội thoại và dữ liệu | Tìm kiếm, phân trang, chọn, reload, xóa theo quyền | Tách rõ lịch sử hội thoại và nguồn dữ liệu bằng nhãn trong cùng panel; không tải toàn bộ lịch sử. |
| Composer, file chips, model/options | Nội dung đang soạn, tệp đính kèm, model cho tin nhắn mới, busy/disabled | Tệp và ngữ cảnh gần nút gửi; tùy chọn ít dùng vào menu; giữ model đã chọn và thông báo lỗi gửi. |
| Transcript/message/result blocks | User/Assistant, progress, lỗi, bảng, facts, chart, download | Phân cấp câu trả lời theo ý nghĩa; không lặp nguyên trạng thái job ở nhiều khối. |
| `AgentWorkflowPanel.tsx` | Workflow/steps, polling, cancel, next action, mapping batch | Một summary ngắn cho mỗi yêu cầu; chi tiết kỹ thuật mở theo nhu cầu; cancel phải nói rõ điểm dừng. |
| `ReviewCard.tsx`, common facts | Nonce, expiry, fingerprint, bản nháp, nguồn, rule, quyền editor; duyệt từng phần hoặc batch | Ưu tiên quyết định nghiệp vụ; trường nhập chung chỉ áp dụng sau xác nhận cùng nghĩa; không giấu dữ kiện tài chính quan trọng. |
| Clarification/reply | Câu hỏi thiếu nghĩa, trả lời tự nhiên, bản xem trước, resume | Phân biệt trả lời làm rõ với duyệt rule. Giữ lịch sử câu trả lời lỗi, không hiện lỗi cũ như lỗi đang xảy ra. |
| Upload/data drawer, `AssistantDataDrawer.tsx` | Upload, parse status, raw download, prepared/canonical, source evidence | Bằng chứng nguồn cạnh hội thoại; cho thấy tầng dữ liệu và phiên bản mà không bắt hiểu thuật ngữ nội bộ. |
| Route `data`, preview/profile | Dataset/version/table/profile, warnings, prepared findings, paging | Một màn hình đọc dữ liệu có tabs rõ; lỗi ngày/null/invalid tách khỏi dữ liệu hợp lệ và giá trị zero. |
| `MappingStudio.tsx` | Schema, business keys, metric/currency/locale/date, preflight, approve, mapping reuse | Giữ manual fallback; nhóm trường theo nhận diện/ngày/tiền; mặc định không yêu cầu chỉnh JSON. |
| Route `reconcile`, `ReconciliationStudio.tsx` | Hai nguồn, kỳ, scope, approved plan/contract, jobs/runs | Bản tóm tắt trái–phải và thiếu xác nhận trước nút chạy; trạng thái hợp đồng khác trạng thái run. |
| Route `home`, summary/KPI | `MetricSnapshot`, CU, denominator, exclusions, run/period/currency | Kết quả tổng quan của run; không biến thành landing cạnh tranh với Chat. Không có run thì hướng dẫn bước tiếp, không KPI zero giả. |
| Bảng kết quả/`QueryTable`, `components.tsx` | Backend filters/sort/page, selected query, group IDs, detail | Thanh phạm vi rõ, phân biệt tổng số khớp và trang đang xem; sticky header có kiểm tra focus. |
| Charts/`AgentResultBlocks.tsx`, ECharts | Backend aggregations, metric/currency, nhóm dữ liệu | Biểu đồ có bảng thay thế và nhãn phạm vi; không tính lại KPI trong frontend. |
| Route `exceptions` | Case workflow, linkage/comparison, owner/action/audit | Không dùng một badge chung cho ba chiều trạng thái. RESOLVED không biến mismatch thành equal. |
| `ReconciliationEvidence.tsx` | Group/members, hai phía, source row/cell, provenance, rule | Một evidence panel nhất quán cho Chat và trang thủ công; nhiều thành viên nguồn phải xem đủ. |
| Route `reports`/export | Run, CSV/XLSX, job, download; toàn run hoặc query được ghim | Hiện rõ phạm vi và định dạng trước xuất; giữ snapshot, thứ tự, phân trang, formula-injection protection. |
| `WorkspaceSettings.tsx` | Account/role, privacy, mapping reuse grants, provider/policy/budget | Nhóm cài đặt người dùng trước; vận hành cho owner trong phần mở rộng; không lộ key hoặc cho viewer sửa quyền. |
| `Modal`/dialog | Radix focus trap, Escape, returnFocus, danger confirmation | Chuẩn hóa một hệ modal/drawer/popover; tránh chồng nhiều lớp overlay; giữ nội dung bản nháp khi đóng theo contract. |
| Menus/popovers/tooltips | Context/model/options/source/project actions | Một hệ vị trí, z-index, dismissal và keyboard; tooltip bổ trợ, không chứa hướng dẫn bắt buộc. |
| `Notice`, `Spinner`, `Badge`, empty states | Loading/error/blocked/review/success, retryability, next action | Lỗi trong ngữ cảnh tác vụ; không biến mọi notice thành toast; chỉ retry khi Backend cho phép. |
| Viewer/owner và workspace isolation | Disabled/hidden actions, CSRF/session, tất cả resource refs | UI giải thích quyền thiếu; không xem nút bị ẩn là biện pháp bảo mật thay Backend. |

API nền đang có đủ phần lớn dữ liệu cần trình bày. Việc gộp panel dùng lại API, không tạo một hệ truy vấn/đối soát khác. Nếu cần DTO tổng hợp cho trải nghiệm mới, phải đánh giá riêng freshness, quyền, pagination và số request; hiện chưa kết luận cần endpoint mới.

## 3. Sáu nhóm vấn đề

### A. Quá nhiều chữ chú thích

[D] Transcript, thẻ review, thông tin bước chạy và các khối giải thích có nhiều lớp chữ phụ. Việc lặp thông điệp “AI đề xuất/người dùng duyệt” giúp nhắc quyền nhưng làm giảm độ nổi của quyết định cụ thể. Mapping/plan vẫn có các trường kỹ thuật trong phần mở rộng; đây là công cụ cần giữ cho manual fallback, không phải nội dung nên thấy đầu tiên.

[P] Chuyển lời giải thích chung vào trợ giúp theo ngữ cảnh. Mỗi khối giữ một tiêu đề, kết luận ngắn, nguồn/phạm vi và hành động tiếp. Cảnh báo thiếu tiền tệ, kỳ, khóa, completeness, quyền và approval vẫn luôn hiện khi ảnh hưởng quyết định. Không rút gọn bằng cách giấu dữ kiện bắt buộc duyệt.

### B. Bố cục và không gian

[D] Sidebar desktop đo được 246 px, topbar 56 px. Toolbar Chat có max-width 1120 px; composer desktop max-width 760 px. Ở 390 px, composer rộng 358 px/cao 104 px trong trạng thái đo; ở 768 px rộng 736 px/cao 58 px. Khoảng trắng welcome là lựa chọn bố cục, chưa có nghiên cứu người dùng chứng minh gây lỗi. Review dài và bảng rộng đặt trong transcript tạo nhiều lần cuộn và thay đổi bề rộng nội dung.

[P] Dùng cùng trục canh cho header/transcript/composer. Transcript văn bản có giới hạn chiều dài đọc; bảng/review được mở rộng vào vùng làm việc cạnh Chat. Cần kiểm soát thứ tự đọc và trả focus khi mở panel. Composer không che dòng cuối hoặc quyết định đang duyệt; mobile kiểm với bàn phím ảo và chiều cao nhỏ.

### C. Sidebar · đề xuất ba mục đã được thay thế

[D] CSS hiện hành ẩn sidebar ở breakpoint hẹp và dùng nút mở drawer; desktop chưa có thao tác thu gọn. Điều hướng hiện tại có nhiều mục nghiệp vụ. Có mâu thuẫn tài liệu: `Rules.md` §9.1 yêu cầu Assistant/Lịch sử/Cài đặt; các bổ sung và nghiệm thu sau mở thêm truy cập nghiệp vụ. Tác động là chưa có một sơ đồ sidebar đã chốt duy nhất cho đợt đại tu. Báo cáo này **không tự sửa Rules/kế hoạch hoặc xóa route**.

[P] Đề nghị chủ dự án chốt sidebar chính gồm AI Assistant, Lịch sử, Cài đặt; Dữ liệu/Kết quả/Báo cáo là vùng làm việc mở từ Chat, tìm kiếm hoặc deep link. Sidebar thu gọn vẫn có tên truy cập cho icon, active state, tooltip và keyboard. Giữ đường vào manual fallback và khả năng quay lại đúng hội thoại.

### D. Nhất quán giữa các trang

[D] Có shared primitives `Modal`, `Notice`, `Spinner`, `Badge`, bảng TanStack và token CSS. Tuy vậy, `App.tsx`, `ReconciliationStudio.tsx` và các component Chat có nhiều cách bố trí header/actions/notice. Hiển thị Decimal đã có formatter chung, trong khi một số bảng/chi tiết dùng `String(value)`; việc này chưa tự nó chứng minh sai tiền nhưng tạo trải nghiệm định dạng khác nhau. Nhãn trạng thái và mapping hiển thị nằm ở nhiều khu vực cần đối chiếu khi đổi.

[P] Dùng một mẫu PageHeader/SectionHeader/ResultToolbar và một bộ formatters nhận typed Backend DTO. Định dạng trình bày không được chuyển Decimal qua float để cộng hoặc đánh giá tolerance. Bảng cần cùng quy tắc empty/loading/error, unit/currency, pagination, số dòng và export. Bản ghi null, invalid và zero phải có biểu đạt khác nhau.

### E. AI Assistant

[D] Chat đã điều khiển upload, review, truy vấn, planning và export bằng workflows thật. Kết quả nhiều dạng hiện nối tiếp theo thời điểm hoàn thành, khiến người dùng phải tự ghép nguồn–quy tắc–kết quả. Context chip và tùy chọn giúp gọn nhưng cần mở thêm để kiểm tra run/nguồn. Review quan trọng có thể nằm xa composer sau bảng dài.

[P] Tổ chức câu trả lời theo **Conversation → Summary → Data/Table → Business Decision → Evidence**. Conversation giữ ý định và tiến trình; Summary nêu kết quả/phạm vi; Data/Table tương tác bằng typed queries; Business Decision trình bày phần cần người dùng quyết định; Evidence mở khi cần và quay về đúng vị trí. Không bắt đủ năm khối ở câu hỏi đơn giản. Không thêm một luồng duyệt thứ hai trong right panel hoặc tự chuyển từ làm rõ sang approve.

### F. Thẩm mỹ và cảm giác sản phẩm

[D] CSS đã có token cho surface/border/radius/shadow, nhưng còn nhiều literal màu, khoảng cách và font-size trong các nhóm selector. Body base 14 px, h1 29 px; các caption 11–12 px xuất hiện ở nhiều thành phần. Chưa có ma trận tương phản/font/zoom toàn bộ trạng thái, nên chưa kết luận độ tương phản hoặc cỡ chữ nào vi phạm.

[P] Củng cố hệ token dùng stack hiện có, không cài thêm UI framework: scale chữ, spacing, radius, border, elevation, focus, status và chart palette. Ưu tiên rõ cấp bậc, dễ đọc tiếng Việt, mật độ dữ liệu vừa đủ; hạn chế shadow/khung lặp. Màu phải đi kèm chữ/icon, không mã hóa tiền âm hoặc trạng thái chỉ bằng màu.

## 4. Kiến trúc giao diện đề xuất

| Khu vực | Cách tổ chức [P] | Hợp đồng phải giữ |
| --- | --- | --- |
| App Shell | Sidebar mở/thu gọn; một header; nội dung và context panel; mobile drawer | Route/deep link, session/workspace, quyền, project selection và return navigation. |
| Chat | Welcome ngắn, transcript theo yêu cầu, composer nhất quán; gợi ý theo status xác định | Model cho tin nhắn mới, job/fence/idempotency, không gọi AI khi render hoặc chỉ mở panel. |
| Context panel | Tabs nguồn/kết quả/bằng chứng; desktop cạnh Chat, hẹp thì drawer/toàn màn hình | Mỗi tab gắn project/run/dataset/revision cụ thể; không dùng latest thay run đã chọn. |
| Review | Summary quyết định + các trường nghiệp vụ; advanced theo nhu cầu; ghi rõ nguồn đề xuất | Nonce/fingerprint/expiry/actor, preflight, quyền duyệt và immutable audit. |
| Data workspace | Preview/profile/mapping/quality theo nguồn; mở từ Chat và deep link | Raw bất biến, prepared chưa duyệt khác canonical, giữ toàn bộ lỗi/partition/provenance. |
| Results workspace | Summary, bảng, chart, exceptions, reports cùng một run context | MetricSnapshot, CU/denominator, Decimal, status độc lập, evidence và exact export scope. |
| Settings | Account/privacy trước; owner controls mở rộng; trạng thái provider rõ | Không đổi policy/default/quota khi chỉnh UI; không lộ credentials. |

Right panel không nên thành một cửa sổ Chat thứ hai. Khi panel và hội thoại cùng mở, cả hai phải hiển thị cùng context hoặc có nhãn khác run rõ ràng. Mở nhiều nguồn/run cần explicit selection; không dùng việc đổi tab để âm thầm đổi đối tượng duyệt.

## 5. Quy tắc thiết kế cần chốt bằng prototype

- Typography: đánh giá một font hỗ trợ tiếng Việt, xác nhận tải/font fallback; scale đề xuất 12/14/16/20/24/28 px, body line-height khoảng 1,5. Cỡ nhỏ chỉ cho metadata không thiết yếu; kiểm 200% zoom và nội dung dài.
- Spacing: scale 4/8/12/16/24/32 px; control heights đủ thao tác; tên tệp dài và nhiều currency không ép tràn body.
- Layout: mobile một cột; tablet ưu tiên Chat và drawer; desktop sidebar có thể thu gọn và panel theo tác vụ. Breakpoint phải theo nội dung đã đo, không sao chép thiết bị mẫu.
- Tables: server pagination/filter/sort; chỉ virtualize nếu đo cần thiết. Header, frozen key column và density là lựa chọn cần test. Tổng số khớp, khoảng trang và tập xuất phải nói cùng một nghĩa.
- States: phân biệt chưa có dữ liệu, chưa chọn run, không khớp bộ lọc, đang đọc, đang xử lý, chờ review, bị chặn quyền/policy, lỗi có/không retry, thành công và dữ liệu cũ. Không thay lỗi/unknown bằng zero hoặc badge thành công.
- Accessibility: tên truy cập cho icon, thứ tự Tab, focus-visible, focus return, Escape, live-region cho tiến trình có giới hạn, bảng thay thế cho chart. Kiểm contrast, reflow, screen reader và focus không bị composer/sticky header che.
- Exports: chọn CSV/XLSX, giải thích toàn run hay bảng/trang được ghim; read-back thật để kiểm rows/order/money/snapshot. Không thêm client-side tính tiền hoặc xuất từ dữ liệu chưa verified.

## 6. Backlog đề xuất cho nhiệm vụ tiếp theo

P1 là ưu tiên thiết kế lại sau khi release ổn định; không tự coi mọi mục là lỗi chặn release hiện tại. API impact là đánh giá sơ bộ, cần thiết kế chi tiết trước sửa.

| Vấn đề → mục tiêu | Component/phạm vi | Ưu tiên | API impact | Regression bắt buộc |
| --- | --- | --- | --- | --- |
| Chưa chốt IA → một đường vào Chat và manual fallback rõ | App Shell/navigation/sidebar/history | P1 | Dùng lại | Back/forward, deep links, workspace switch, quyền và lịch sử >200. |
| Context khó rà → nguồn/run/kỳ hiện đúng lúc quyết định | Header/context chip/panel | P1 | Dùng lại typed context | Đổi run/project, stale query/review, reload, không dùng nhầm current/latest. |
| Review dài → quyết định nghiệp vụ dễ kiểm và ít lặp | ReviewCard/common facts/WorkflowPanel | P1 | Giữ DTO và approvals | Nonce/expiry/conflict/cross-workspace, thiếu scope, chung facts nhưng khóa riêng, không tự approve. |
| Transcript nhiều loại khối → phân cấp câu trả lời | AssistantStudio/AgentResultBlocks | P1 | Dùng lại | Streaming/progress/job failure, clarification/resume, scroll anchor, cancel và lịch sử. |
| Bảng và export khó thấy scope → biết đang xem và xuất gì | QueryTable/reports/export | P1 | Giữ typed scope | Filters/sort/page/run đồng nhất; CSV/XLSX rows/order, formula injection, âm/zero/ID có số 0 đầu. |
| Nhiều overlay → một hệ panel/modal nhất quán | Modal/evidence/data/history/options | P1 | Dùng lại | Focus trap/return/Escape, không mất draft, nguồn nhiều thành viên và mobile keyboard. |
| Định dạng/nhãn phân tán → một bộ trình bày có kiểu | components/status/formatters | P1 | Không đổi money DTO | Decimal lớn/âm/null/invalid/zero, nhiều currency, mọi chiều status, snapshot không tính lại. |
| Token chưa đồng nhất → typography/spacing/color nhất quán | styles/shared primitives | P2 | Không | Five widths, zoom, contrast, focus, tên dài, bảng rộng, trạng thái loading/error/empty. |
| Manual workspaces khác nhịp Chat → cùng language/actions | Data/Mapping/Reconciliation/Reports/Settings | P2 | Chủ yếu dùng lại | Toàn pipeline trước/sau chuyển Chat–manual; viewer/owner, mapping reuse/policy không đổi. |
| Chưa có đo usability độc lập → quyết định bằng hành vi | Prototype và thử với chủ dự án | P1 | Không | Task completion, hiểu scope, nhầm approval, thời gian, số trường/click và lỗi; không chỉ chấm ảnh đẹp. |

Trình tự đề nghị: (1) chốt IA và luồng quyết định bằng prototype; (2) shared tokens/primitives/App Shell; (3) Chat/composer/context; (4) review/evidence/data tables; (5) đồng bộ trang thủ công/settings; (6) full functional/security/browser/visual/accessibility regression. Mỗi bước cần phạm vi được chủ dự án giao; báo cáo này không tự mở đợt triển khai đó.

## 7. Nguồn tham khảo và cách áp dụng

| Nguồn chính thức [S] | Điều tham khảo | Giới hạn áp dụng cho Studio |
| --- | --- | --- |
| [ChatGPT Projects](https://help.openai.com/en/articles/10169521-projects-in-chatgpt) | Tổ chức hội thoại và tệp theo dự án | Không nhập cơ chế memory/quyền của sản phẩm khác vào contract Studio. |
| [Claude Artifacts](https://support.claude.com/en/articles/17153992-what-are-artifacts-and-how-do-i-use-them) | Nội dung làm việc cạnh hội thoại | Panel Studio vẫn là typed views trên Backend, không tạo sandbox code/agent mới. |
| [Linear custom views](https://linear.app/docs/custom-views) | Bộ lọc, view theo nhiệm vụ và ngữ cảnh | Áp dụng tính rõ ràng của view, không biến financial state thành task status chung. |
| [Numeric Reconcile](https://www.numeric.io/product/reconcile) | Tổng hợp workpapers và drill-down | Chỉ học cách tổ chức chứng cứ; không tiếp nhận cam kết marketing về accuracy. |
| [Ledge reconciliation overview](https://docs.ledge.co/reconciliation/overview) | Quy trình và dữ liệu đối soát có ngữ cảnh | Không thay grain, grouping, formulas hoặc approval của Studio bằng nghiệp vụ nhà cung cấp. |
| [Microsoft Finance reconciliation](https://learn.microsoft.com/en-us/copilot/finance/reconcile/reconcile-data) | Người dùng kiểm lựa chọn khóa và báo cáo được hỗ trợ | Studio độc lập Excel add-in, vẫn giữ Backend verifier và human approval. |
| [Flatfile mapping data](https://support.flatfile.com/articles/8569925090-mapping-data) | Mapping theo bảng và bước kiểm tra | Không áp dụng hành vi loại bỏ trường/dòng làm mất raw hay partition. |
| [OneSchema validations](https://docs.oneschema.co/docs/validations) | Trình bày validation gần dữ liệu | Không coi cảnh báo client là thay thế gate server hoặc tự sửa dữ liệu. |
| [Fluent drawer guidance](https://fluent2.microsoft.design/components/web/react/core/drawer/usage) | Inline panel/overlay theo ngữ cảnh, focus và hạn chế nhiều lớp | Dùng primitives hiện có; không thêm Fluent framework. |
| [Fluent design tokens](https://fluent2.microsoft.design/design-tokens/) | Token hóa màu, chữ, spacing và elevation | Chỉ tham khảo hệ thống hóa, giữ brand/stack đã giao. |
| [Carbon empty states](https://www.carbondesignsystem.com/building-blocks/core/patterns/empty-states) | Empty state có nguyên nhân và hành động phù hợp | Chưa có kết quả không đồng nghĩa kết quả bằng 0. |
| [NN/g progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/) | Chuyển tùy chọn ít dùng sang tầng sau | Không giấu dữ kiện mà người dùng cần để duyệt tiền/nguồn/scope. |
| [WCAG 2.2](https://www.w3.org/TR/WCAG22/) | Reflow, contrast, focus không bị che, target size và keyboard | AA target-size 24 CSS px có ngoại lệ; phải kiểm từng ngữ cảnh, không suy compliance từ ảnh. |

Các quyết định cần chủ dự án chốt cho đợt sau: cấu trúc sidebar và vai trò trang thủ công; context panel mặc định/khả năng ghim; mức thông tin luôn hiện khi duyệt; độ rộng/mật độ bảng; font có hỗ trợ tiếng Việt và hệ token; các tác vụ usability dùng làm tiêu chí nghiệm thu. Decimal, raw immutability, workspace isolation, chính sách AI và human approval là ràng buộc bảo toàn, không phải lựa chọn thẩm mỹ.

## 8. Kiểm toán bổ sung ngày 09/11/2026

Phần 1–7 giữ nguyên biên bản ngày 08/11. Các số đo và phương án dưới đây bổ sung cho biên bản đó. Mâu thuẫn về sidebar và phương án từng đề nghị quay về ba mục được đối chiếu lại ở mục 8.6.

### 8.1. Phạm vi và cách đọc bằng chứng

| Nhãn | Ý nghĩa trong vòng này |
| --- | --- |
| OBSERVED | Quan sát trực tiếp trên bản Docker. Nếu phiên không qua bootstrap, kết quả chỉ phản ánh shell và trạng thái lỗi phiên. |
| SOURCE_VERIFIED | Kiểm trong React/CSS, API/DTO và test source tại cùng revision. Giải thích quy tắc có trong mã, không suy ra tần suất xảy ra. |
| TEST_VERIFIED · MOCK CONTRACT | Chromium tải HTML/CSS/JS từ release đang chạy, nhận DTO TEST tổng hợp do Playwright trả trong trình duyệt. Bao phủ trình bày và tương tác được assert. Backend, model, permissions thật và tác dụng ghi nằm ngoài chứng cứ này. |
| DOCUMENTED | Hành trình và kết quả đã lưu ở biên bản cũ, hướng dẫn TEST hoặc kế hoạch. Chưa chạy lại live trong vòng này. |
| REFERENCE | Pattern tham khảo từ tài liệu chính thức hoặc tra cứu cục bộ của skill. |
| PROPOSED / NEEDS_DECISION | Đặc tả cho đợt sau hoặc lựa chọn cần chủ dự án chốt. |

Baseline Git `c477745d6c4426c663089251f75182aa1e2c375c`. Source ứng dụng được nghiệm thu tại `1d7f4909a3aa5d6c0a79cdddb88cb4303119e701`. Diff giữa hai mốc ở frontend/backend rỗng. Frontend, backend và worker có label revision `c477745d6c4426c663089251f75182aa1e2c375c`; PostgreSQL cùng Compose. Origin khớp repository dự án. Đã đối chiếu [AGENTS](../AGENTS.md), [Rules](../Rules.md), [kế hoạch sản phẩm](PROJECT_PLAN.md), [kế hoạch tự động hóa](AUTOMATION_PRODUCT_PLAN.md), [kiến trúc](ARCHITECTURE.md), [hợp đồng dữ liệu](DATA_CONTRACTS.md), [biên bản nghiệm thu](IMPLEMENTATION_STATUS.md) và [hướng dẫn TEST](USER_TEST_GUIDE.md).

**OBSERVED · giới hạn vận hành.** Tại năm viewport, `GET /api/session` trả HTTP 403 `LOCAL_DEMO_NOT_VERIFIED`; giao diện hiện hướng dẫn xác minh và “Thử kết nối lại”. Bốn container healthy, tức health không chứng minh phiên demo hợp lệ. [Bootstrap](../backend/studio/access.py) kiểm proof gắn instance và frontend. Không kết luận nguyên nhân sâu hơn của proof từ riêng mã lỗi. Không mở dữ liệu thật, thay proof, restart, redeploy, hoặc dùng thông tin xác thực thay để vượt qua gate. Không thể kiểm lại hành trình nghiệp vụ live, mặc dù [nghiệm thu 08/11](IMPLEMENTATION_STATUS.md) có các kết quả lịch sử.

**TEST_VERIFIED · cách cô lập.** Test và phép đo dùng HTML/assets của đúng release. API trên trình duyệt do fixture synthetic trả, request không có fixture bị chặn khỏi Backend trong suite. Harness đo chỉ mở route, đọc bảng, mở modal và gắn tệp trong bộ nhớ trình duyệt. Những ca giả lập ghi như submit review hoặc lỗi upload do handler mock chặn và trả tại trình duyệt. Không tạo project/run/workflow/report thật hoặc gọi AI. Ảnh và đo thô nằm ngoài Git ở thư mục audit local `studio-ux-research-20261109`. Manifest ghi route, state, fixture, revision, viewport, tên ảnh, thông số và nhận xét.

### 8.2. Bố cục đo bằng computed styles

Năm viewport chính là **390×844, 768×1024, 1366×768, 1440×900, 1920×1080**. Ma trận dùng `assistant/data/reconcile/home/exceptions/reports/settings`. Baseline Chat có hội thoại TEST và run đã chọn, nên khác welcome. CSS đóng drawer mobile bằng dịch vị trí; 215 px là chiều rộng của drawer khi mở, không trừ khỏi main khi đóng. Kích thước sau làm tròn theo CSS px.

| Rộng viewport | Sidebar | Main | Header Chat / trang nghiệp vụ | Toolbar Chat / transcript | Composer Chat có kết quả |
| --- | --- | --- | --- | --- | --- | --- |
| 390 | Drawer 215 | 390 | 56 / 64 | 358 / 358 | 358 × 104 |
| 768 | Drawer 215 | 768 | 56 / 64 | 736 / 736 | 736 × 58 |
| 1366 | Cố định 246 | 1120 | 56 / 73 | 1064 / 1064 | 1064 × 62 |
| 1440 | Cố định 246 | 1194 | 56 / 73 | 1120 / 1120 | 1120 × 62 |
| 1920 | Cố định 246 | 1674 | 56 / 73 | 1120 / 1120 | 1120 × 62 |

Ở 1440, composer welcome đo rộng **760 px** và composer có kết quả **1120 px**. Số đo 760 px ở phần cũ đúng cho một trạng thái, không phải trần mọi trạng thái. Dialog Lịch sử, Đổi ngữ cảnh, Chọn dự án và Tải dữ liệu rộng **580 px**. Tệp và dữ liệu trong Chat rộng **900 px**. Bảng Data trong fixture desktop rộng **1070 px**. Modal bằng chứng Báo cáo rộng **900 px**, bảng kết quả đo **1118 px** trong vùng cuộn cùng chiều rộng ở mẫu desktop. Bộ ảnh bổ sung ghi padding, gap, font-size, line-height, scrollWidth/clientWidth, chiều cao panel, table, composer, dialog; không suy một mẫu chung cho mọi route. Cấu hình font CSS hiện tại khai báo Inter/Segoe UI/Arial; detector đọc khai báo chứ chưa xác minh glyph được dùng ở thiết bị khác.

Ở 390 px, ảnh báo cáo cho thấy tiêu đề, mô tả, bộ chọn dự án, tiêu đề kết quả, lịch sử, bộ chọn run và nút xuất nằm trước phần dữ kiện. Ảnh `table` trong fixture Chat cho thấy 10 dòng xem trước nhưng bộ đếm có “25 dòng trong trang”; câu này mô tả trang query, còn hành động bên dưới mở trang đó. Đây là nguy cơ đọc nhầm phạm vi, cần đặt hai con số cạnh nhau. Bảng nhiều cột dùng cuộn nội bộ. Không thấy tràn ngang body trong các mẫu đạt. 390×520 có probe focus, 720×450 là phép thử giảm chiều rộng, 320 px là probe reflow, cùng override root font 200%. Ngoài các probe đó, kiểm zoom thật **200%** trong profile Chromium tạm bằng API zoom của trình duyệt tại Assistant, Data, Reports. Khung 1440×900 thành 720×450 CSS px, DPR 2 và document scrollWidth/clientWidth đều 720. Chat composer 688 px; bảng Data 622 px; bảng Reports 670 px. Không dùng profile hay preference của người dùng. Chưa kiểm zoom chỉ chữ của trình duyệt, bàn phím ảo/IME thật hoặc screen reader.

### 8.3. Ma trận màn hình và trạng thái

| Bề mặt · chức năng | Bằng chứng vòng này | Giới hạn cần kiểm tiếp |
| --- | --- | --- |
| AI Assistant · khởi động, welcome, chat mới, model, composer | OBSERVED lỗi phiên. MOCK empty, short, multiline, đính kèm local, loading, sidebar, draft và Enter/Shift+Enter. [AssistantStudio](../frontend/src/AssistantStudio.tsx) kiểm `nativeEvent.isComposing`. | Bộ gõ và bàn phím vật lý/ảo thật. Thử upload end-to-end chỉ trên TEST đã xác minh phiên. |
| Chat lịch sử, nhiều tin/kết quả, trạng thái đang chạy, hoàn tất, partial, blocked, failed | MOCK 23 trạng thái × năm chiều rộng, scroll anchor, tải tin cũ, pending polling, lỗi provider và lỗi lịch sử; long filename và chart dài. | Số workflow/run lớn thật và provider thực theo policy. Không suy sức tải từ fixture. |
| Upload từ Chat, dữ liệu vừa tải | MOCK trạng thái đính kèm, request đang đợi, thất bại có kiểm soát và mở dialog upload Data. SOURCE_VERIFIED đường attachments → parse/profile/prepared và limits. | Chưa gửi tệp vào release trong lần audit này. Xem USER_TEST_GUIDE §4, §13 cho kịch bản tiếp theo. |
| Nguồn/dự án, Data, raw/prepared/canonical/errors, profile, mapping, normalize | MOCK các route/tầng dữ liệu, tách lỗi, đổi sheet chống hiển thị dữ liệu cũ, xử lý API summary lỗi và stale query. SOURCE_VERIFIED các nhánh nguồn/tầng/revision. | Không dùng fixture để khẳng định mapping/canonical thực. PDF/DOCX và phân trang lớn live theo gate riêng. |
| Làm rõ, Mapping Review và phê duyệt | MOCK tách làm rõ khỏi duyệt ở năm chiều rộng; preflight, chưa đủ thông tin, sparse Planner, xác nhận phạm vi và dữ liệu lỗi. | Expiry/replay/conflict thật theo backend và UAT. Không gửi approval đến release. |
| Đối soát, lập phương án, rule, chạy | SOURCE_VERIFIED form thủ công và contract; MOCK thẻ Planner và validation payload. RUNNING/COMPLETED được quan sát ở workflow giả lập. | Không tạo plan hoặc run live. Dữ liệu đầu vào và hai oracle tài chính đối chiếu tài liệu nghiệm thu. |
| Tổng quan/Kết quả, bảng, chart, ngoại lệ | MOCK route `home/reconcile/exceptions/reports`, snapshot, tabular counts, nhóm LINKED và AMOUNT_MISMATCH, biểu đồ, mở evidence. SOURCE_VERIFIED case state độc lập. | Lần chạy verified/partial thật, đa currency, truy cập bị thu hồi và điều hướng trường hợp run ngoài trang cần UAT. |
| Bằng chứng, báo cáo, xuất CSV/XLSX | MOCK bằng chứng theo run/group, source row ở Chat, nút xuất và download block. SOURCE_VERIFIED giới hạn thành viên và hai export scopes. | Không bấm export live, chưa đọc lại file ở vòng này. 1:N/N:1 nhiều members cần oracle độc lập. |
| Settings và vai trò | MOCK quyền owner/viewer và trạng thái privacy, kiểm nút ghi của viewer. SOURCE_VERIFIED editor dùng `canEdit`, owner-only classification/reuse và backend guard. | Editor và revoked role chưa được kiểm qua tài khoản live. Không suy ẩn nút thay kiểm quyền API. |
| Dialog, drawer, popover, manual/deep links | MOCK lịch sử, đổi ngữ cảnh, mobile drawer, tệp, upload, project picker, bằng chứng, xác nhận xóa chỉ mở/đóng; deep links bảy route. History trap: 12 lần Tab vẫn trong dialog, Escape đóng và trả focus Lịch sử. | Kiểm toàn overlay với Shift+Tab, zoom, screen reader và nút đã unmount; giữ manual fallback khi AI lỗi. |

Trạng thái **retryable/non-retryable**, **stale**, **expired**, **revoked** và **no results** có quy tắc riêng ở [ma trận chuyển trạng thái](ui-redesign/SCREEN_AND_COMPONENT_SPECS.md#8-ma-trận-chuyển-trạng-thái). Pending, partial và blocked trong fixture không cấp quyền ghi. Các ca lâu, hết quyền và hết hạn chưa được tái hiện đầy đủ trên phiên thật. Phân biệt wait và đang xử lý: quyết định chưa có hiệu lực khi người dùng mới trả lời làm rõ; một phần đã xác minh chỉ áp dụng đúng phần được chỉ định.

### 8.4. Phát hiện và ưu tiên

P1 ưu tiên giải quyết trước phát hành UX do ảnh hưởng tới việc hiểu hoặc thực hiện quyết định. P2 có lối đi hiện tại nhưng thêm thao tác/khó đọc. P3 là hoàn thiện. Mức ưu tiên đề xuất không đồng nghĩa một lỗi nghiệp vụ đã tái hiện.

| ID · nhóm · mức | Bằng chứng và ảnh hưởng | Hướng cho đặc tả |
| --- | --- | --- |
| A01 · Navigation · P2 | SOURCE_VERIFIED có sáu mục thực, desktop cố định 246 px, drawer ở tối đa 900 px. Cài đặt dùng class active và chưa có `aria-current` như các mục trang chính. Trạng thái local/cloud luôn chiếm chỗ đáy sidebar. | Giữ sáu lối vào, active semantic, rail/drawer. Hiện chính sách AI ở chỗ quyết định/chọn model và Settings. |
| A02 · Chat · P2 | TEST_VERIFIED ở 1440 composer từ 760 px (welcome) sang 1120 px khi có kết quả. Một số khối dài chiếm bề ngang đầy đủ. Source có metadata/chi tiết để giữ. | Trục đọc ổn định; nội dung chi tiết/bảng lớn mở panel; gợi ý xuất hiện theo trạng thái. |
| A03 · Review · P1 | Ảnh `review` 1440 có cơ sở số tiền, tiền tệ, bước bổ sung, nháp, checkbox và approval trong một cột dài. SOURCE_VERIFIED điều kiện nonce, fingerprint, preflight và ảnh hưởng. MOCK chứng minh làm rõ giữ approval riêng. | Thông tin bắt buộc đọc trước quyết định, phần chuyên sâu theo nhu cầu, một CTA xác nhận có hệ quả rõ. Không gộp trả lời làm rõ và duyệt. |
| A04 · Dữ liệu · P2 | SOURCE_VERIFIED `App.tsx` tách Tự chuẩn bị và Chuẩn hóa qua nút phụ, ngoài các tabs tác vụ. Ảnh Data lặp tiêu đề/tên nguồn và nhiều tầng trước bảng. Các chiều raw/prepared/canonical đều có thật. | Một hàng scope nguồn–sheet–revision; ba tầng có tên phân biệt; lỗi nằm gần bảng và link đúng dòng. |
| A05 · Đối soát · P1 | SOURCE_VERIFIED form có quan hệ, khóa, kỳ, độ đầy đủ và metric; một phần điều kiện được lặp ở bước xác nhận. MOCK Planner xác nhận trường thiếu vẫn giữ nút duyệt bị chặn khi chưa đủ điều kiện. | Tóm tắt đối chiếu trái–phải và các dữ kiện chi phối số liệu, mở chuyên sâu khi sửa, không hạ guard nghiệp vụ. |
| A06 · Báo cáo và xuất · P1 | Ảnh Reports 390 nút CSV/XLSX đứng trước kỳ/đơn vị; chưa thấy phạm vi xuất ngay cạnh nút. SOURCE_VERIFIED xuất thủ công full run, Chat có `DISPLAYED_QUERY` cho đúng trang query đã ghim. Không tái hiện xuất nhầm trên Backend. | Hiện kỳ/run/scope sát thao tác xuất. Giữ query ghim và trang phân biệt với toàn run; không hứa xuất selection/chọn toàn tập lọc khi chưa có API. |
| A07 · Bằng chứng · P1 | SOURCE_VERIFIED API giới hạn tối đa 100 thành viên mỗi phía và cung cấp cờ đầy đủ; screenshot MOCK có sheet/dòng, giá trị và chênh lệch. | Hiện số đã trả/tổng và cảnh báo thiếu khi cờ báo thiếu. Giữ liên kết đúng run, group, nguồn và revision. |
| A08 · Cài đặt · P2 | MOCK giao diện tài khoản/quyền/riêng tư/giới hạn; SOURCE_VERIFIED vai trò và capability. Đổi model là hành động theo tin mới, không suy từ nhãn local/cloud toàn shell. | Cài đặt người dùng dùng copy đơn giản. Operator diagnostics chỉ khi liên quan. Tên model và lý do không khả dụng hiển thị ở composer. |
| A09 · Typography/consistency · P2 | Detector trả 1 cảnh báo `overused-font` cho khai báo Inter trong `styles.css:19`; đây là heuristic thẩm mỹ, không phải thiếu glyph/vi phạm WCAG. Ảnh cho thấy lặp eyebrow/tiêu đề/caption, source có cả tokens và literal. | Chữ hệ thống, phân cấp theo nhiệm vụ, kiểm glyph tiếng Việt và định dạng số bằng formatter dùng chung. |
| A10 · Responsive/a11y · P2 | Reports 390 đặt nhiều thao tác trước dữ kiện chính. Ảnh live lỗi 390 cho thấy nút “Thử kết nối lại” ngắt thành ba dòng. TEST_VERIFIED history trap và return focus, các phép đo không tràn body, nhưng bảng, sticky composer và zoom cần kiểm theo ngữ cảnh. | Xếp CTA lỗi xuống hàng ở viewport hẹp; bảng có tên, focus, cuộn rõ; kiểm zoom, target, chart alternative và focus không bị che. |
| A11 · Hiệu năng · cần đo | SOURCE_VERIFIED `App.tsx` giữ `ReconciliationStudio` ẩn khi ở Assistant có dự án. `AssistantStudio.tsx` kiểm phản hồi workflow trùng qua `slice().some()` trong render. Chưa đo đây là bottleneck. | Profile request/render với nhiều run và lịch sử dài trước khi đổi mount strategy hoặc thuật toán presentation. |

Giữ những phần đã hoạt động trong phạm vi kiểm gồm điều hướng manual, project context có kiểm scope, focus trap/return, thông tin nguồn, khả năng mở chi tiết và tách approval. Impeccable Operate đặt tiêu chí hoàn thành việc và độ chính xác lên trước trang trí. Áp dụng critique theo tìm đường, hiểu trạng thái và kiểm soát, audit theo cấu trúc/focus/reflow/theming, shape cho phương án. Detector chạy static với `detect --json --no-config frontend/src`, exit 2 do một cảnh báo. Không dùng overlay tự sinh của critique hoặc scan URL cần browser phụ. Chưa có đủ dữ liệu performance, screen reader hoặc độ phủ zoom cho mọi overlay để chấm tổng điểm accessibility/performance.

### 8.5. Hành trình và phép đo tiếp theo

| Hành trình | Bằng chứng một phần đã đo hoặc kiểm | Phần chưa đo và rủi ro |
| --- | --- | --- |
| Mới bắt đầu → gửi tệp | MOCK mở hội thoại mới một lần bấm, 0 route/approval, gắn tệp synthetic trong bộ nhớ rồi thấy chip. Fixture workflow có loading/lỗi. | Không đo thời gian tới dữ liệu sẵn sàng trên release. Dễ nhầm trạng thái “đã gửi” với “sẵn sàng”. |
| Đọc dữ liệu → chọn tầng → tìm dòng | MOCK mỗi thao tác đổi tầng dùng nút riêng, không chuyển route. Canonical từ Prepared cần nút “Xem bản chuẩn hóa đã duyệt”. | Số bước tìm đúng sheet/phiên bản phụ thuộc source. Kiểm field/click với hai nguồn và kết quả lịch sử. |
| Kế toán → Báo cáo → xem bằng chứng | MOCK đã vào đúng run qua deep link, một click “Xem bằng chứng”, 0 route/field/approval. Thử đọc nhóm `000701` và chênh lệch theo cùng run. | Chưa đo chọn run và xuất từ điểm đầu. Phải đo nhầm scope và đối chiếu byte khi chạy UAT. |
| Chuyên gia → chỉnh và xác nhận | MOCK mở phần phạm vi trong Planner, điền dữ kiện rồi mới mở nút duyệt. Ca synthetic dùng trường bắt buộc khác nhau theo dữ liệu/coverage. | Số field và click không đồng nhất giữa reuse, đề xuất đủ và đề xuất thưa. UAT đo từng nhánh; không bỏ bước xác nhận partial hoặc tolerance. |
| Người gặp lỗi → phục hồi | OBSERVED một nút “Thử kết nối lại” ở 403; mã nguồn giữ lỗi và hướng dẫn riêng. MOCK ba ca bootstrap error retry thành công theo fixture, draft/history giữ lại. | Retry live chỉ có tác dụng sau khi điều kiện phiên hợp lệ. Không đo thời gian phục hồi từ ảnh. |
| Chỉ xem → kiểm tra số liệu | MOCK xem Điều hướng, Dữ liệu, quyền viewer và disabled write; 0 xác nhận trong tác vụ đọc. | Chưa kiểm thực tế người xem tìm đúng nguồn trên tài khoản độc lập. |

Số lần bấm trên là đoạn đo bằng Playwright sau khi fixture đã đặt đúng điểm bắt đầu. Các con số end-to-end về thời gian, thao tác nhập, chuyển trang và số lần xác nhận do người dùng cần một vòng baseline UAT. [Kiến trúc trải nghiệm](ui-redesign/UX_INFORMATION_ARCHITECTURE.md#3-hành-trình-điểm-rút-gọn-và-phép-đo) và [kế hoạch nghiệm thu](ui-redesign/IMPLEMENTATION_AND_ACCEPTANCE_PLAN.md#5-đo-hành-trình-và-cửa-nghiệm-thu) định nghĩa cách thu cùng dữ liệu và tránh đếm hộ tác vụ người dùng.

### 8.6. Các phương án tại thời điểm nghiên cứu

**NEEDS_DECISION.** `Rules.md` §9.1 giữ quyết định ngày 02/11 về sidebar ba mục. Bổ sung 06/11 đầu `PROJECT_PLAN.md` và §6.1 `AUTOMATION_PRODUCT_PLAN.md` mở các lối nghiệp vụ, tương ứng source. Phương án ba mục trong phần 3.C là đề xuất lịch sử. Đề xuất mới giữ sáu mục, Chat là mặc định, Ngoại lệ nằm trong Kết quả của Đối soát và deep links giữ nguyên. [D01](ui-redesign/OPEN_DECISIONS.md) so ưu/nhược điểm và chờ chủ dự án chốt.

**PROPOSED.** Một hệ thiết kế sáng, trung tính, xanh dương, phân cấp bằng khoảng cách và chữ. UI UX Pro Max 2.15.0 chạy 16 tra cứu cục bộ. Hướng tối, landing hero, font tải từ xa và thay bộ icon bị loại vì không hợp bối cảnh sử dụng/stack/giấy phép. Hướng bảng mật độ phù hợp, nhãn trạng thái kèm chữ, đánh giá accessibility theo tác vụ và drill-down được giữ có chọn lọc. [Design System Blueprint](ui-redesign/DESIGN_SYSTEM_BLUEPRINT.md) ghi truy vấn, kết quả và contrast đề xuất. [Microcopy Audit](ui-redesign/MICROCOPY_AUDIT.md) ghi 72 quyết định có source và điều kiện.

Lượt critique cuối trên đặc tả kiểm các xung đột dễ xảy ra. Panel chỉ dock nếu còn đủ trục Chat, nếu thiếu thì chuyển overlay. Preview và toàn bảng cùng dùng một scope có ID; khi mở rộng không đổi query. Review vẫn hiện dữ kiện tài chính dù ẩn trường kỹ thuật. Hai đường xuất được gọi đúng tên; bằng chứng thiếu có biểu đạt riêng. Các số đo 56/240/64/760/400 là đề xuất cần prototype; không lẫn với số đo bản chạy tại mục 8.2. [Đặc tả màn hình](ui-redesign/SCREEN_AND_COMPONENT_SPECS.md) có 12 nhóm màn hình, wireframe, ngữ pháp phản hồi, contracts, handoff và ma trận trạng thái. [Kiến trúc trải nghiệm](ui-redesign/UX_INFORMATION_ARCHITECTURE.md) ghi đối chiếu 12 nguồn chính thức và giới hạn áp dụng. [Kế hoạch triển khai và nghiệm thu](ui-redesign/IMPLEMENTATION_AND_ACCEPTANCE_PLAN.md) giữ các cổng nghiệp vụ, quyền, tiền và rollback cho nhiệm vụ sau.

### 8.7. Biên bản kiểm thử vòng này

| Kiểm tra | Kết quả | Bằng chứng local ngoài repo |
| --- | --- | --- |
| Bootstrap thật tại 5 viewport | **BLOCKED LIVE**. Cùng HTTP 403, chưa mở dataset/run thật. | `live-access.json`, 5 ảnh. |
| Kiểm bố cục và tương tác theo route | **54 mẫu MOCK** trên 7 route và trạng thái bổ sung. Không lỗi JS, không lỗi response hoặc request ghi thoát khỏi fixture trong lượt đo cuối. | `mock-measurements.json`, `mock-activity.json`, 54 ảnh. |
| Zoom thật 200% | **3 mẫu MOCK** ở Chat, Dữ liệu và Báo cáo, không tràn body. | `native-zoom200.json`, 3 ảnh. |
| Bộ ca Playwright có sẵn | **50 ca PASS ở lượt đầu** và **1 ca IME PASS sau khi bổ sung bootstrap mock vào bản sao tạm của test**. Không sửa test source. Hai ca đối soát được chọn quá rộng, cần fixture run đã lưu nên dừng trước khi kiểm giao diện; không tính là regression sản phẩm hoặc ca đạt. | `mock-playwright.log`, `ime-playwright.log`. |
| Trạng thái Chat và focus | **23 trạng thái × 5 viewport** trong suite mock, 115 ảnh. Tab trong History và Escape/return focus kiểm riêng. Cả Enter và Shift+Enter kiểm bằng sự kiện tổng hợp. | `runtime/assistant-layout` trong thư mục audit, `mock-activity.json`. |
| Manifest và đối chiếu hình ảnh | **177 ảnh** gồm 5 live bootstrap và 172 mock. Có 57 mẫu computed/zoom, các ảnh còn lại gắn với assert của suite. Đã xem ảnh đại diện của lỗi phiên, review, bảng mobile và evidence. | `screenshot-manifest.json`. |
| Đối chiếu Docker | Cùng bốn container, ID/image/thời điểm khởi động và revision khớp trước/sau. Cả bốn healthy. | `docker-before.txt`, `docker-after.txt`. |

Hạn chế để chủ dự án biết trước khi phê duyệt triển khai. Vòng này đủ bằng chứng để thảo luận các phương án, mô tả hiện trạng theo source, chốt nhiệm vụ cần thử và đánh giá thiết kế. Nghiệm thu live end-to-end, UAT độc lập, screen reader, bàn phím mobile thật, bộ gõ tiếng Việt thật và profiling tải dài được theo dõi riêng. Bổ sung hoặc chỉnh số đo baseline khi phiên demo hoạt động trở lại.
