# Quy chuẩn thiết kế Calm Financial Workspace

Trạng thái **PROPOSED · PENDING_OWNER_REVIEW**. Đặc tả này dùng để duyệt hướng thiết kế và làm chuẩn cho đợt triển khai sau. Mọi kích thước, token và tiêu chí sản phẩm mới dưới đây là đề xuất, trừ khi ghi rõ chuẩn tham chiếu hoặc hiện trạng đã xác minh.

Phạm vi sử dụng là một ứng dụng làm việc tài chính, với AI Assistant là điểm bắt đầu, Dữ liệu là nơi kiểm tra nguồn, Đối soát là nơi xác nhận phạm vi và theo dõi lượt chạy, Báo cáo là nơi xem kết quả đã xác minh. Điều hướng, giao diện theo trạng thái và câu chữ có đặc tả riêng. [Kiến trúc trải nghiệm](UX_INFORMATION_ARCHITECTURE.md) · [Đặc tả màn hình](SCREEN_AND_COMPONENT_SPECS.md) · [Kiểm kê câu chữ](MICROCOPY_AUDIT.md) · [Quyết định cần duyệt](OPEN_DECISIONS.md).

## 1. Cơ sở và phương pháp

**SOURCE_VERIFIED.** Frontend hiện dùng React, TypeScript, Vite, Tailwind qua plugin hiện có, CSS dự án, Lucide, Radix Dialog, TanStack Table và ECharts. Các nền, viền, focus, chữ và bán kính hiện có trong `styles.css` nhưng màn hình vẫn có nhiều giá trị riêng. Hợp nhất theo vai trò trong CSS dự án rồi chuyển từng cụm giao diện sang token. Giữ primitive đang dùng nếu đáp ứng hợp đồng tương tác và khả năng tiếp cận. [Stack hiện hành](../../frontend/package.json) · [CSS](../../frontend/src/styles.css) · [Thành phần dùng chung](../../frontend/src/components.tsx).

**Impeccable 4.8.1, Operate.** Áp dụng playbook đọc và phân tích. Distill dùng để gộp tín hiệu trùng và chọn một hành động chính. Typeset dùng một họ chữ và tách mật độ hội thoại khỏi bảng. Layout dùng khoảng cách và thứ tự đọc trước khi thêm nền, khung hoặc tiêu đề. Clarify giữ hậu quả duyệt và đường khôi phục gần hành động. Adapt chuyển bố cục theo không gian khả dụng. Harden và polish đặt ca kiểm phóng to, dữ liệu dài, bàn phím, trạng thái đồng thời và lỗi quyền cho lần triển khai. Đây là phương pháp rà soát, không phải kết quả kiểm thử giao diện đề xuất.

**UI UX Pro Max 2.15.0, REFERENCE.** Chạy 16 truy vấn Python cục bộ với đầu ra JSON và đối chiếu danh tính hàng kết quả. Không dùng chế độ ghi tài liệu. Kết quả chỉ cung cấp từ vựng và phương án để cân nhắc.

| Truy vấn và chế độ | Kết quả trả về | Cách áp dụng hoặc loại |
| --- | --- | --- |
| `financial reconciliation workspace light minimal professional` · design system | General, `minimalism-and-swiss-style`, B2B Service, Financial Trust, không có product/reasoning cụ thể, Hero + Features + CTA | Dùng nguyên tắc chữ rõ và cấu trúc đơn giản. Loại bố cục hero/CTA, màu tự sinh và nhập font bên ngoài. |
| `AI assistant productivity application` · product | Productivity Tool, Drill-Down Analytics | Dùng phân tầng từ tóm tắt đến chi tiết theo tác vụ. Bỏ Interactive Product Demo và các mẫu landing. |
| `enterprise data table financial analytics` · style | `data-dense-dashboard` | Dùng header cố định khi phù hợp, cuộn nội bộ và hàng gọn có điều kiện. Loại mặc định nhiều KPI, 12 px cho toàn bộ bảng và thư viện biểu đồ được gợi ý. |
| `complex business approval progressive disclosure` · UX | Heading Line Balance, không đúng ý định | Tra lại `error prevention confirmation` có Error Messages, Confirmation Messages, Confirmation Dialogs. Dùng thông tin hậu quả và lỗi theo trường. Tiêu chí trường bắt buộc vẫn lấy từ hợp đồng Studio. |
| `minimal navigation collapsible sidebar` · UX | Sticky Navigation | Tra lại `keyboard navigation sidebar` có Keyboard Navigation, Skip Links. Dùng focus, skip link và kiểm chồng lấp. Kích thước rail do Studio đề xuất. |
| `accessible dashboard data visualization` · chart | Performance vs Target (Compact), Bullet Chart | Dùng nhãn, bàn phím và bảng tương đương. Loại bullet/gauge vì không có ngưỡng tương ứng. Tra `categorical comparison bar chart` rồi chọn hàng Compare Categories ở vị trí 3, bỏ radar và scatter vì sai mục đích so sánh. |
| `Vietnamese interface typography` · typography; `Vietnamese sans serif` · Google Fonts | Vietnamese Friendly (Be Vietnam Pro/Noto Sans); Estedad có subset tiếng Việt | Dùng tiêu chí kiểm dấu và độ rộng tên, giữ một họ chữ hệ thống. Không tải, nhúng hoặc sao chép font từ gói. |
| `financial dashboard light`, `enterprise SaaS dashboard` · color | Hạng đầu Financial Dashboard, nền `#020617` ở cả hai | Loại bảng màu tối. Dùng tông sáng đã chốt trong brief và tính tương phản trực tiếp. |
| `large table rerender state` · react | Defer State Reads | Tham khảo quản lý đăng ký state và đo rerender. Không tối ưu theo kết quả tra cứu nếu chưa đo trên hành trình thực. |
| `focus not obscured`, `error summary validation` · UX | Focus Not Obscured (Enhanced), Focusable Error Summary | Đối chiếu lại W3C để phân biệt AA/AAA. Giữ lỗi cạnh trường và summary có thể focus khi gửi thất bại. |

**REFERENCE.** Tiêu chuẩn khả năng tiếp cận dựa vào W3C. Cách tổ chức thang chữ theo vai trò và dùng họ chữ có sẵn trên hệ điều hành tham khảo Fluent 2. Tham chiếu này hướng dẫn phương pháp, không nhập thương hiệu, font, CSS hoặc tài nguyên của nhà cung cấp. [WCAG 2.2](https://www.w3.org/TR/WCAG22/) · [Fluent 2 Typography](https://fluent2.microsoft.design/typography).

## 2. Nguyên tắc thiết kế

1. Hành động kế tiếp luôn gắn với dữ liệu hoặc quyết định cụ thể. Mỗi bề mặt chỉ có một hành động chính tại một thời điểm. Hành động trên các review độc lập chỉ nổi bật ở review đang mở.
2. Đọc hội thoại từ trên xuống. Dùng văn bản, khoảng cách và một điểm nhấn xanh trước khi dùng khung. Chỉ dùng mặt nổi cho hộp thoại, composer và khu vực cần tách khỏi nội dung.
3. Tín hiệu quan trọng có chữ và hình thức rõ. Sắc độ chỉ hỗ trợ nhận biết, không mã hóa trạng thái độc quyền.
4. Mọi số tài chính đi cùng đơn vị, phạm vi và trạng thái xác minh có thể kiểm tra. Mở rộng để truy đúng nguồn, ngày, dòng, nhóm và phiên bản.
5. Đưa thông tin nâng cao vào đúng chỗ dùng. Điều kiện chặn, hậu quả phê duyệt và trạng thái chưa xác minh luôn gần hành động hoặc kết quả chịu ảnh hưởng.

## 3. Token màu và tương phản

Các token là tên vai trò đề xuất. Một màu có thể phục vụ nhiều vai trò nhưng component chỉ tham chiếu vai trò. Tỷ lệ dưới đây được tính với giá trị sRGB nguyên, công thức độ chói tương đối W3C, làm tròn hai chữ số **để báo cáo**. Khi nghiệm thu so sánh tỷ lệ chưa làm tròn và màu thực sau khi kết hợp nền, opacity hoặc overlay.

| Vai trò | Token và giá trị | Cặp đã tính |
| --- | --- | --- |
| Nền chính, bề mặt | `canvas #F8FAFC`, `surface #FFFFFF`, `surface-subtle #F1F5F9` | Dùng bề mặt trắng cho tài liệu đọc, form và bảng. |
| Chữ chính, thân bài, phụ | `text #0F172A`, `text-body #334155`, `text-muted #475569` | Chính trên trắng 17,85:1. Thân/phụ trên canvas 9,90/7,24:1. |
| Hành động chính | `accent #2563EB`, `accent-hover #1D4ED8`, `accent-pressed #1E40AF`, `on-accent #FFFFFF` | Trắng trên ba nền 5,17/6,70/8,72:1. |
| Liên kết và chọn | `link #1D4ED8`, `selected-bg #EFF6FF`, `selected-fg #1E40AF` | Link trên trắng 6,70:1. Chọn 8,01:1. Dùng vạch/chữ và trạng thái ARIA cùng màu. |
| Đường phân vùng | `border-subtle #E2E8F0`, `border-control #64748B` | Viền control trên trắng/canvas 4,76/4,55:1. Viền subtle dùng cho phân vùng trang trí, không làm dấu duy nhất để nhận biết control. |
| Focus | `focus #1D4ED8`, viền 2 px lệch 2 px | 6,70:1 trên trắng, 6,41:1 trên canvas. Thêm đệm trắng 2 px khi ring kề mặt nút xanh hoặc nền tối. |
| Thông tin, đang xử lý | `info-fg #1E40AF`, `info-bg #EFF6FF` | 8,01:1. Tên bước và tín hiệu đang chạy khi thật sự pending. |
| Thành công, đã xác minh | `success-fg #166534`, `success-bg #F0FDF4` | 6,81:1. Nêu rõ đã lưu, đã duyệt hoặc đã xác minh, tùy trục trạng thái. |
| Cần xem, xác minh một phần | `warning-fg #854D0E`, `warning-bg #FFFBEB` | 6,61:1. Kèm điều kiện và phạm vi bị ảnh hưởng. |
| Lỗi, bị chặn | `danger-fg #991B1B`, `danger-bg #FEF2F2` | 7,60:1. Cặp chữ/nền cho notice. Hành động phá hủy dùng `#B91C1C` với chữ trắng, 6,47:1. |
| Trung tính, thiếu dữ liệu | `neutral-fg #475569`, `neutral-bg #F1F5F9` | 6,92:1. Giải thích trạng thái thiếu qua chữ, không đồng nhất với thành công hoặc số 0. |

- Trạng thái nút có default, hover, pressed, focus, disabled và pending. Pending giữ kích thước nhãn và khóa gửi lặp trong lúc yêu cầu chưa hoàn tất. Disabled phải có lý do đọc được khi lý do quan trọng. Dùng `aria-disabled` có kiểm soát kích hoạt nếu cần giữ khả năng khám phá qua focus.
- Màu đỏ cho lỗi và hành động phá hủy. Chênh lệch âm vẫn mang dấu và đơn vị. Âm không tự động là lỗi, xanh không tự động là đạt. Các trục `linkage`, `comparison`, `verification` và `exception state` giữ nhãn riêng.
- Nền trong table và transcript chủ yếu trắng. Badge dùng nền màu nhẹ khi cần quét nhiều trạng thái. Notice chặn hoặc partial đặt ngay trước phần dữ liệu tương ứng. Cảnh báo có cùng nội dung chỉ có một nơi đọc chính, kể cả với trình đọc màn hình.

## 4. Chữ, khoảng cách và hình khối

**Họ chữ.** Đề xuất `system-ui, "Segoe UI", Arial, sans-serif`. Không dùng cặp display/body. Không phụ thuộc mạng để tải phông. Số dùng `font-variant-numeric: tabular-nums` nơi hỗ trợ, kiểm từng nền tảng. ID và chuỗi kỹ thuật dài có thể dùng monospace hệ thống trong chi tiết kỹ thuật. Giữ dấu tiếng Việt, chữ đ/Đ, ký tự tổ hợp, mã có số 0 đầu và tiền tệ Unicode. Dùng line height tương đối. Cho phép chọn và sao chép giá trị đầy đủ nếu cột phải rút gọn hiển thị.

| Vai trò | Kích thước / dòng | Độ đậm | Nơi dùng |
| --- | --- | --- | --- |
| Tiêu đề trang | 24/32 px (1,5 rem / 1,33) | 600–650 theo họ chữ | Một H1 cho mỗi route, Assistant có thể giữ tiêu đề trực quan nhỏ hoặc H1 hỗ trợ. |
| Tiêu đề khu vực | 18/26 px | 600 | Review, nhóm cài đặt, thông tin bảng. |
| Tiêu đề phụ | 16/24 px | 600 | Nhóm nguồn, câu hỏi duyệt, kết quả. |
| Hội thoại và input mobile | 16/26 px, input 16/24 px | 400 | Transcript, composer, nhãn và nội dung đọc chính trên mobile. |
| UI, bảng | 14/21 px | 400, 600 ở header | Điều hướng, filter, bảng desktop. Nội dung chính trên mobile ưu tiên 16 px. |
| Thông tin phụ | 12/18 hoặc 13/20 px | 400–500 | Thời gian, mô tả nguồn, nhãn phụ. Không dùng cho số tiền và quyết định bắt buộc. |

- Khoảng cách theo bước 4 px. Dùng 4, 8, 12, 16, 20, 24, 32, 40 và 48. Quan hệ gần như nhãn–trường dùng 4–8, cụm điều khiển 8–12, nội dung panel 16–24, nhóm lớn 24–32. Dùng khoảng trống trước khi thêm viền.
- Bán kính 6 px cho badge, 8 px cho input và nút, 12 px cho panel, 16 px cho dialog và 20 px cho composer. Tránh bo viên thuốc ở mọi control. Hình nổi chỉ dùng shadow nhẹ `0 4px 12px #0F172A14` cho popover và `0 12px 32px #0F172A26` cho dialog. Scrim `#0F172A66` là lớp riêng, không giảm độ tương phản chữ bên trong dialog.
- Viền 1 px, hàng phân cách bảng mảnh. Trạng thái active cần thể hiện được khi forced colors bật. Dùng icon Lucide 16 px ở inline, 18–20 ở nút/rail. Icon trang trí ẩn khỏi AT, icon độc lập có tên đọc được, tooltip không thay cho tên hoặc hint quan trọng.
- Motion 120–180 ms cho hover, focus style tức thì, 180–220 ms cho mở/đóng panel nếu không mất định vị. Ưu tiên opacity/transform nhỏ và tôn trọng `prefers-reduced-motion`. Không tự cuộn để giành vị trí người đang đọc. Khi giảm chuyển động, giữ tín hiệu đang xử lý bằng chữ/trạng thái tĩnh.

## 5. Bố cục, responsive và hành vi tương tác

| Điều kiện | App Shell | Hội thoại và vùng chi tiết |
| --- | --- | --- |
| Dưới 768 CSS px, gồm 390 | Điều hướng drawer. Padding 16 px. Một cột. Header cao tối thiểu 56 px và giãn khi chữ xuống dòng. | Transcript cuộn, composer gọn, bằng chứng mở toàn màn hình. Menu và thanh điều khiển chia hàng. Tôn trọng safe-area và bàn phím ảo. |
| 768–1023, gồm 768 | Rail 64 px mặc định khi nội dung đủ chỗ, menu mở rộng dạng overlay. Padding 24 px. | Context mở drawer bên phải khi giữ được lối đọc. Form hai cột chỉ khi nhãn và trường đủ chỗ. |
| 1024–1439, gồm 1366 | Sidebar 240 px mặc định, rail 64 px khi thu gọn. Header tối thiểu 56 px. Padding 24 px. | Transcript và composer cùng trục, mỗi vùng tối đa khoảng 760 px. Panel overlay có chiều rộng mục tiêu 400 px. |
| Từ 1440, gồm 1440 và 1920 | Sidebar 240/64 px, padding 32 px tùy chiều rộng khả dụng. | Cho dock panel khoảng 400 px khi cột hội thoại còn tối thiểu 640 px sau khi tính gutter/rail. Có thể thu sidebar hoặc dùng overlay. Transcript tối đa khoảng 760 px, đoạn chữ tối đa 72ch. |

- Các kích thước là đầu vào thử nghiệm, cần xác nhận qua các quyết định mở. Xác định breakpoint theo **CSS viewport sau zoom** và chiều rộng container. Ưu tiên đơn cột khi nhãn hoặc thao tác không còn chỗ. Giao diện chính không cuộn ngang ở 320 CSS px trừ vùng nội dung hai chiều thực sự cần thiết, ví dụ bảng đối chiếu.
- Trang nghiệp vụ dùng lưới 12 cột trên desktop nếu có nhiều vùng, 8 ở tablet, 4 ở mobile. Một header và một vùng chính. Bề mặt bảng có thể dùng toàn chiều rộng khả dụng. Dòng dài ưu tiên vùng trong bảng, không kéo thân trang.
- Giữ vùng transcript và composer có biên dưới rõ. Dùng `100dvh` có fallback, safe-area và kiểm hành vi visual viewport trên thiết bị thật. Vùng cuộn có padding cuối bằng chiều cao composer thực, kể cả đính kèm và review reply.
- Modal, drawer và popover dùng một lớp tương tác tại một thời điểm. Dock panel desktop là vùng bổ trợ không trap focus. Overlay modal và drawer quản lý focus, Esc, trả focus về trigger có thực, làm nền inert và khôi phục vị trí cuộn. Không mở modal lồng chỉ để xem một dòng.
- Nút desktop chính cao tối thiểu 40 px, mobile ưu tiên 44×44 px. WCAG 2.2 AA 2.5.8 yêu cầu mục tiêu 24×24 CSS px hoặc đáp ứng điều kiện khoảng cách/ngoại lệ. Focus visible (2.4.7 AA) và không bị che hoàn toàn (2.4.11 AA). Studio đặt mục tiêu thấy trọn focus khi có sticky controls. Không dùng tiêu chí 2.4.12 Enhanced (AAA) làm yêu cầu AA. [WCAG 2.2](https://www.w3.org/TR/WCAG22/).

## 6. Quy chuẩn thành phần và tái sử dụng

Props ở bảng là đầu vào về mặt khái niệm. Tên cụ thể, liên kết nghiệp vụ và chuyển trạng thái nằm ở đặc tả màn hình. Hành động được cấp phép dựa trên quyền và điều kiện từ server. Tách nhãn hiển thị khỏi giá trị enum.

| Thành phần | Vai trò, đầu vào, biến thể | Hành vi, responsive và nguồn tái sử dụng |
| --- | --- | --- |
| AppShell / Sidebar / PageHeader | Route, dự án, quyền, tiêu đề, action; expanded/rail/drawer, active, kết nối | Landmark, skip link, `aria-current`, giữ focus khi đổi route; `App.tsx` và `navigation.ts`. |
| ProjectSelector / Dropdown | Dự án hiện tại, danh sách phân trang, trạng thái tải, quyền tạo; trigger gọn hoặc có nhãn | Một tên dự án chính, lọc và trạng thái đã chọn đọc được, danh sách hỗ trợ bàn phím và mobile; tái dùng ProjectSelector và native select nếu phù hợp. |
| ChatComposer / ChatMessage | Draft, tệp, model, binding review, nội dung và trạng thái yêu cầu; rỗng/soạn/gửi/lỗi | Nhãn nút chính rõ, Enter và IME an toàn, liên kết ngữ cảnh và giữ draft. Tách hội thoại khỏi bảng dày; dựa trên AssistantStudio. |
| WorkflowSummary / ReviewCard / Clarification | Bước, câu hỏi, nguồn, lý do, lựa chọn, quyền, fingerprint, hiệu lực; đọc/chờ/đang gửi/hết hạn/đã xử lý | Câu hỏi đơn giản inline, quyết định cần căn cứ có chi tiết, giữ điều kiện chặn gần nút. Không mặc định duyệt. Dựa trên AgentWorkflowPanel và ReviewCard. |
| ContextPanel / EvidencePanel | Project/run/source/group/revision, nội dung, trigger; loading/error/no access và partial | Dock/drawer/fullscreen, một mặt chi tiết, giữ focus và vị trí transcript. Dựa trên AssistantDataDrawer, ReconciliationEvidence và Modal. |
| DataTable / Filters | Columns, định danh hàng, filters/sort/page, scope, total theo server, lỗi | Native table, sort có `aria-sort`, nhãn filter, scroll độc lập và trạng thái refresh. Dựa trên DataTable, TanStack và truy vấn hiện có. |
| KPI / Chart | Snapshot, metric, đơn vị, phân mẫu, series, timezone, verification | Số thật và mẫu số, nhãn không dựa riêng màu, bảng/danh sách tương đương, không dùng lại chart DTO để tự tính tổng. Dựa trên ReconciliationStudio, AgentResultBlocks, ECharts. |
| ExportPanel | Run hoặc query, filter, định dạng, quyền, kết quả đã có, lỗi | Nêu phạm vi thực trước nút, không hứa xuất trang/dòng chọn nếu API không có. Dựa trên luồng xuất của ReconciliationStudio và khối tải trong chat. |
| Modal / Drawer / Tooltip | Tên, mô tả, trigger, open, pending; dialog xác nhận, chi tiết và popover hỗ trợ | Radix Dialog hiện có cho lớp modal. Tooltip focus/hover, tắt bằng Esc, không chứa trường hoặc hành động. |
| Notice / Loading / EmptyState / ErrorState | Mã trạng thái, điều gì xảy ra, bước tiếp theo, retryable, quyền | Notice inline theo tài nguyên, `status` cho tiến độ, `alert` cho lỗi cần chú ý. Loading giữ khung, empty có bước kế tiếp, error giữ draft và chi tiết hỗ trợ. Tái dùng Notice, Spinner, Badge. |

## 7. Bảng, biểu đồ và phạm vi số liệu

**Bảng.** Mặc định hàng 44 px, tùy chọn gọn 36 px trên desktop khi có nhu cầu so sánh nhiều dòng. Cả hai cho phép hàng giãn theo nội dung; giữ mục tiêu chạm 44 px cho thao tác mobile. Thứ tự cột mặc định đặt khóa nghiệp vụ, trạng thái và số tiền cần so ở đầu theo nhiệm vụ. Text và mã căn trái, số tiền và phần trăm căn phải bằng chữ số đồng độ rộng, đơn vị trong tiêu đề hoặc ô khi có nhiều loại tiền. Dấu âm và chuỗi Decimal hiển thị đúng độ chính xác nguồn. Dùng định dạng hiển thị locale có bảo toàn chuỗi, không qua float; cho xem giá trị đầy đủ. Chỉ làm nổi sticky header/cột nếu không che focus hoặc chiếm hết vùng đọc khi zoom.

| Tín hiệu | Quy tắc |
| --- | --- |
| Số 0 hợp lệ | Hiện đúng `0` hoặc số Decimal nguyên bản đã định dạng. |
| NULL / ô trống | Phân biệt theo khả năng DTO. Nếu DTO chỉ có null, ghi “Chưa có giá trị” và không suy ra nguyên nhân. |
| Giá trị lỗi | Hiện “Không hợp lệ” kèm giá trị nguồn khi có quyền và được cấp bởi DTO. Lỗi ngày khác lỗi số tiền. |
| Không áp dụng / chưa đủ căn cứ | Hiện “Không áp dụng” với mẫu số 0 hoặc “Chưa đủ dữ liệu” theo trạng thái. Mẫu số và lý do trong chi tiết. |
| Số âm / nhiều tiền tệ | Giữ dấu, định danh đơn vị và phân nhóm tiền tệ. Không cộng nhiều loại tiền hoặc dùng màu để hàm ý hướng chênh lệch. |
| Trạng thái nhiều chiều | Cột hoặc nhãn riêng cho liên kết, so sánh, xác minh, xử lý ngoại lệ. Ví dụ “Đã ghép” và “Lệch tiền” cùng tồn tại. |

**Phân trang và lọc.** Bảng nhận dữ liệu theo scope hiện tại, công bố số dòng trong trang, tổng phù hợp nếu có và trạng thái có trang tiếp. Header sort có trạng thái và tên cột, focus ổn định sau refresh. Đặt nhãn trực quan cho vùng cuộn có thể truy cập bằng bàn phím. Thao tác hàng dùng nút/link có tên gắn với mã hoặc dòng. Rút gọn tên rất dài có đường xem đầy đủ bằng bàn phím, không cắt nội dung tài chính thiết yếu. Chỉ đưa chọn hàng hàng loạt khi có tác vụ đã hỗ trợ.

**Phạm vi số liệu.** “Toàn bộ lượt” gắn snapshot và đơn vị so sánh. “Theo bộ lọc” chỉ dùng cho số do server trả về cho query đó. “Trang hiện tại” chỉ số dòng đã tải. “Các dòng đã chọn” chỉ áp dụng khi có API nhận bộ chọn. Nhãn xuất nói rõ phạm vi đã xác nhận. Đổi bộ lọc bảng không đổi KPI của lượt chạy nếu DTO vẫn là snapshot toàn lượt.

**Biểu đồ.** Ưu tiên cột/thanh so sánh nhóm có giá trị cùng đơn vị, đường thời gian khi có dữ liệu theo kỳ, bảng khi mục tiêu là đối chiếu số chính xác. Dùng các màu ứng viên `#2563EB`, `#0F766E`, `#6D28D9`, `#92400E`, `#475569`, `#B91C1C` với tương phản 5,17–7,58:1 trên trắng. Đây là tương phản từng màu với nền, không bảo đảm các series cạnh nhau dễ phân biệt. Kèm nhãn trực tiếp, nét/gạch/hình dạng và khoảng cách phù hợp. Tooltip bổ sung chi tiết, bảng hoặc danh sách giữ đầy đủ số liệu và nguồn. Mọi chart có tên metric, khoảng thời gian, timezone khi liên quan, currency/unit, population, verification và mức đầy đủ. Khi chỉ có một phần, hiển thị giới hạn sát biểu đồ. Không vẽ trạng thái thiếu thành 0. Giữ giá trị chính xác qua chuỗi nguồn dù ECharts cần số để đặt vị trí điểm.

## 8. Cổng xác nhận trước khi áp dụng

- Kiểm tra token thực trên nền/overlay ở tất cả trạng thái, kiểm cặp chữ thường 4,5:1 và non-text 3:1 nơi áp dụng. Kiểm màu chart bên cạnh nhau, reduced motion và forced colors. Tỷ lệ tính tĩnh trong tài liệu này chưa thay cho test giao diện.
- Đọc và nhập tiếng Việt với dấu ghép, tên tệp dài, ký tự Unicode và IME thật. Kiểm resize text 200%, reflow 320 CSS px, zoom và bàn phím ảo riêng. Giữ focus không bị composer, sticky header hoặc drawer che.
- Kiểm bảng ở 390/768/1366/1440/1920 và zoom, thử null, zero, invalid, số âm, tiền nhiều đơn vị, ID có số 0 đầu, mẫu số 0, nhiều thành viên và partial. Đối chiếu kết quả hiển thị với DTO và xuất file, giữ đúng ID và phạm vi.
- Chốt mật độ, kích thước chat, panel, font và chính sách responsive trong danh sách quyết định. Kiểm nhãn tiếng Việt bằng tác vụ thật, không dùng mức đẹp/thẩm mỹ để thay tiêu chí hiểu và thực hiện đúng. [Kế hoạch triển khai và nghiệm thu](IMPLEMENTATION_AND_ACCEPTANCE_PLAN.md).
