# Phân tích giao diện trước đợt thiết kế lại

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

### C. Sidebar

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
