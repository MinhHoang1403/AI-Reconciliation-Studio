# Kiến trúc trải nghiệm AI Reconciliation Studio

Ngày 09/11/2026. Trạng thái **PROPOSED · PENDING_OWNER_REVIEW**.

Định hướng **Calm Financial Workspace**. Người dùng bắt đầu bằng câu hỏi, nhìn thấy dự án và dữ liệu mà câu hỏi đang dùng, rồi đọc câu trả lời hoặc quyết định tiếp theo ngay tại chỗ. Công việc cần lọc nhiều dòng, so hai nguồn hoặc rà nhiều bằng chứng có vùng làm việc riêng và lối vào trực tiếp. Một quyết định tài chính luôn nêu rõ phạm vi, căn cứ, phần chưa chắc chắn và hệ quả.

Bản này chốt *đề xuất* về đường đi và phân vai bề mặt. Số đo hiện trạng và giới hạn của phép thử nằm trong [kiểm toán giao diện](../INTERFACE_REDESIGN_AUDIT.md). Bố cục và hành vi triển khai tham chiếu [đặc tả màn hình](SCREEN_AND_COMPONENT_SPECS.md), [design system](DESIGN_SYSTEM_BLUEPRINT.md) và [các quyết định mở](OPEN_DECISIONS.md).

## 1. Đọc đúng hiện trạng và lịch sử

| Phân loại | Bằng chứng | Hàm ý |
| --- | --- | --- |
| DOCUMENTED · 02/11/2026 | [Rules §9.1](../../Rules.md#giao-dien) và [nghiệm thu mục U](../IMPLEMENTATION_STATUS.md) mô tả Assistant-only. Dữ liệu, đối soát, ngoại lệ, báo cáo mở qua hội thoại hoặc đường thủ công. | Giữ ý đồ Assistant là điểm bắt đầu và bảo toàn manual fallback. Đây là quyết định của mốc 02/11. |
| DOCUMENTED · 06/11/2026 | Đoạn mở đầu [kế hoạch sản phẩm](../PROJECT_PLAN.md) xác định các mục Dữ liệu, Đối soát và Báo cáo thay yêu cầu Assistant-only ở mốc lịch sử. [Kế hoạch tự động hóa §6](../AUTOMATION_PRODUCT_PLAN.md#6-giao-diện-và-hành-trình-ux) cho phép tích hợp Lịch sử trong Assistant để tránh menu trùng. | Truy cập nghiệp vụ trực tiếp phù hợp chỉ dẫn triển khai mới hơn. Cách tổ chức đợt thiết kế lại vẫn là quyết định của chủ dự án. |
| DOCUMENTED · kiểm toán trước | [Báo cáo trước §3.C](../INTERFACE_REDESIGN_AUDIT.md) ghi nhận sidebar nhiều mục và từng đề xuất quay về ba mục. | Giữ đề xuất lịch sử như phương án A bên dưới, đặt cạnh bằng chứng mới. |
| SOURCE_VERIFIED · baseline | [App](../../frontend/src/App.tsx) dựng AI Assistant, Dữ liệu, Đối soát, Báo cáo, Lịch sử, Cài đặt. Nút Lịch sử vào Assistant nếu cần rồi mở modal. Ngoại lệ không có nút ngang cấp. [Điều hướng](../../frontend/src/navigation.ts) vẫn nhận `home/data/reconcile/exceptions/reports/settings/assistant`. | Giữ các URL cũ, một Lịch sử và đường mở Ngoại lệ chính xác. `home` là route tương thích, mặc định đi vào Assistant. |
| SOURCE_VERIFIED · trạng thái | [Assistant](../../frontend/src/AssistantStudio.tsx) giữ nháp theo scope trong session storage, phân trang lịch sử và tìm trong các hội thoại đã tải. [Data Drawer](../../frontend/src/AssistantDataDrawer.tsx) hiện là modal chỉ đọc với lối sang thủ công, phân trang nguồn và chọn revision. | Nâng cách trình bày từ các bề mặt hiện có. Tìm toàn bộ lịch sử cần chứng minh có hợp đồng API phù hợp. |
| SOURCE_VERIFIED · phiên bản | Baseline Git/release `c477745d6c4426c663089251f75182aa1e2c375c`. So sánh `frontend` và `backend` giữa commit ứng dụng `1d7f4909a3aa5d6c0a79cdddb88cb4303119e701` và baseline không có thay đổi. | Đọc source ở baseline để giải thích phép đo runtime cùng revision. |
| OBSERVED · giới hạn phiên live | Release hiện tại chặn phiên demo tại bootstrap với `LOCAL_DEMO_NOT_VERIFIED`. Xem [bằng chứng đợt này](../INTERFACE_REDESIGN_AUDIT.md). | Các phép đo giao diện sau bootstrap phải ghi rõ fixture tổng hợp và API mô phỏng nếu dùng. Chưa xác nhận lại quy trình nghiệp vụ live hay hiệu năng từ trạng thái này. |

Mâu thuẫn giữa Rules §9.1 và quyết định 06/11 được chuyển sang [OPEN_DECISIONS](OPEN_DECISIONS.md). Bản thiết kế giữ khả năng tiếp cận nghiệp vụ và trình bày rõ lựa chọn cần chốt. Các tài liệu quy tắc và kế hoạch giữ nguyên trong nhánh nghiên cứu.

## 2. Người dùng, nhiệm vụ và quyền

Các nhóm dưới đây là giả thuyết thiết kế từ luồng sản phẩm, mã quyền và [hướng dẫn TEST](../USER_TEST_GUIDE.md). Một người có thể đảm nhiệm nhiều vai trò công việc. Quyền ghi do Backend xác định ở từng thao tác.

| Người dùng | Câu hỏi khi vào Studio | Đường chính | Điều cần thấy trước | Dấu hiệu hoàn thành |
| --- | --- | --- | --- | --- |
| Người mới có quyền thao tác | “Tôi đưa tệp lên rồi làm gì?” | Assistant → đính kèm hoặc Dữ liệu → tải lên → xem kết quả chuẩn bị → xác nhận khi cần | Tên dự án, tên tệp, tệp được nhận, đang chuẩn bị hay cần kiểm tra. Nói rõ bản xem được và bản đã duyệt. | Tìm được tệp vừa tải và diễn giải đúng bước tiếp theo. |
| Kế toán đối soát | “Kỳ này lệch bao nhiêu, ở giao dịch nào?” | Assistant hoặc Đối soát → chọn đúng run → Kết quả → Ngoại lệ → Bằng chứng → Báo cáo | Hai nguồn, kỳ, tiền tệ, trạng thái xác minh, đơn vị so sánh và phạm vi. | Mở đúng nhóm, giải thích mức chênh và chỉ ra dòng gốc; xuất đúng tập. |
| Người rà soát nghiệp vụ | “Tôi đang duyệt ý nghĩa khoản tiền hay chỉ trả lời câu hỏi?” | Thẻ quyết định trong Chat hoặc cùng thẻ ở Dữ liệu → bằng chứng → sửa nháp → kiểm tra → duyệt | Nguồn/revision, grain, khóa, gross/net, currency, coverage, period, tolerance khi liên quan. | Hiểu dữ kiện và hệ quả, chấp nhận/đổi/từ chối theo quyền. |
| Người dùng nâng cao | “Tôi cần xử lý ngoại lệ hoặc làm thủ công khi AI không sẵn sàng.” | Dữ liệu → phiên bản/cảnh báo/ánh xạ; Đối soát → quy tắc/chạy đã duyệt; Báo cáo → xuất | Chế độ thủ công có tên rõ, revision được chọn, điều kiện đang thiếu và lý do chặn. | Hoàn thành với hợp đồng hiện có hoặc biết chính xác dữ kiện phải bổ sung. |
| Người chỉ xem | “Tôi có thể kiểm tra số và truy nguồn đến đâu?” | Kết quả/Báo cáo → bằng chứng được cấp quyền | Vai trò và nguyên nhân khi thao tác không khả dụng. | Đọc đúng dữ liệu được cấp; nút ghi không trở thành ngõ cụt. |
| Chủ không gian làm việc | “Ai có quyền và AI được dùng với chính sách nào?” | Cài đặt → quyền, riêng tư; nâng cao theo quyền | Chính sách có hiệu lực, nhóm tác động, lựa chọn phụ thuộc quyền. | Phân biệt quyền tài khoản, project context và quyền dùng provider. |
| Người đang phục hồi | “Yêu cầu đã được nhận chưa, có phải làm lại?” | Thông báo ở vị trí phát sinh → thử lại an toàn, kiểm tra lại trạng thái hoặc đi đường thủ công | Phần dữ liệu đã lưu, việc còn chạy, thao tác được phép và trường hợp gửi chưa rõ. | Mở lại đúng nháp/phiên/lần chạy và tránh yêu cầu trùng. |

`owner`, `editor`, `viewer` là quyền hiện có. Viewer đọc tài nguyên được cấp và không ghi/duyệt. Owner/editor được UI cho mở các hành động ghi tương ứng, API vẫn kiểm quyền theo resource. Phân loại dự án và quản lý tái dùng ánh xạ áp dụng quyền owner theo các kiểm tra hiện hành. Tạo báo cáo qua API yêu cầu quyền ghi và run đã xác minh. Tải bản có sẵn là GET theo scope với điều kiện bản xuất hoàn tất và checksum hợp lệ. Đề xuất giao diện 401 có lối khôi phục phiên. Với 403/404 do resource không còn truy cập được, dọn dữ liệu cache không còn được phép hiển thị, giải thích theo phản hồi an toàn và cho đường về danh sách trong scope. [Kiến trúc phân quyền](../ARCHITECTURE.md) · [Hợp đồng dữ liệu](../DATA_CONTRACTS.md) · [Nguồn App](../../frontend/src/App.tsx) · [API đối soát](../../backend/studio/reconciliation_api.py).

## 3. Hành trình, điểm rút gọn và phép đo

Ký hiệu **D** là chuỗi hiện tại theo hướng dẫn và mã, chưa phải số đo UAT. **P** là mục tiêu điều hướng đề xuất. Trong bảng, “mở” là số lần bấm để đổi bề mặt từ điểm bắt đầu, không gồm click chuột trong file picker, đợi công việc, nhập liệu hoặc hành động mở rộng chi tiết. Các phép đếm này phục vụ thiết kế kịch bản. Số click, field và thời gian toàn hành trình phải ghi từ phiên TEST thực trong kiểm toán hoặc lượt UAT, theo từng nhánh.

| Tác vụ | Đường D và thao tác | Đường P và thao tác dự kiến | Nguy cơ cần đo |
| --- | --- | --- | --- |
| T1. Bắt đầu từ không có dữ liệu | Assistant → tạo/chọn dự án → gắn tệp → gửi yêu cầu hoặc Dữ liệu → tải. Tạo dự án có ít nhất tên và phạm vi. Số trường quyết định sau upload phụ thuộc nguồn. | Giữ cả hai lối vào. Từ Assistant đã có dự án, mở trình chọn tệp bằng một nút. Receipt hiển thị trong transcript, xem nguồn bằng một mở panel. Nếu cần tạo dự án, giữ tên/phạm vi hiện có. | Người mới dễ nhầm dự án với tệp, “đã tải” với “sẵn sàng đối soát”. Đo lần mở sai bề mặt và khả năng nói lại trạng thái. |
| T2. Rà hai nguồn và chuẩn hóa | Assistant hoặc Dữ liệu → đọc từng thẻ, sửa dữ kiện, xem preflight, xác nhận phạm vi/cảnh báo nếu có → duyệt. Có batch đủ điều kiện hoặc duyệt từng nguồn. | Một thẻ chính mỗi quyết định, nguồn và dữ kiện trọng yếu ở đầu. Không bắt mở trang riêng để duyệt trong Chat. Có thể mở bằng chứng rồi quay lại cùng vị trí. | Số lần xác nhận dựa vào yêu cầu thật. Đếm số field bắt buộc thực sự chỉnh, lần mở lại thẻ, xác nhận nhầm, trạng thái hết hạn và xung đột. |
| T3. Chuẩn bị rồi chạy đối soát | Chat có lối duyệt và chạy theo workflow. Đường thủ công qua Đối soát có chọn nguồn/kỳ/quy tắc, duyệt, rồi chạy riêng. [Hướng dẫn §6](../USER_TEST_GUIDE.md#6-đối-soát-hai-nguồn). | Từ Chat chuyển không lần nếu contract đủ. Đường thủ công mở Đối soát bằng một mục nav. Dùng chung tóm tắt quy tắc nhưng giữ ngữ nghĩa hai lối, explicit approval và thao tác chạy theo contract. | Đếm approval theo quyết định, không theo số nút. Kiểm nhầm run/nguồn, kỳ, khái niệm dấu số tiền và chuẩn bị một phần. |
| T4. Xem khoản lệch và truy nguồn | Đối soát → chọn run → xem bảng → mở dòng hoặc lối Ngoại lệ → mở bằng chứng. Chiều sâu thay đổi theo cách vào và nhóm nhiều thành viên. | Mở Đối soát trực tiếp, vào tab Ngoại lệ thuộc Kết quả. Từ dòng đã chọn chỉ một mở panel bằng chứng. Báo cáo có liên kết quay về đúng nhóm. | Đếm số lần quay lui sai, số màn hình chuyển và người dùng có phân biệt phần khớp, phần không thể so sánh, phần chưa xác minh. |
| T5. Xuất dữ liệu và mở lại | Báo cáo → chọn run → chọn CSV/XLSX → đợi → Tải báo cáo. Chat cũng hỗ trợ xuất theo phạm vi câu hỏi/dữ liệu đang xem. [Hướng dẫn §9](../USER_TEST_GUIDE.md#9-xuất-và-mở-lại-báo-cáo). | Hiển thị phạm vi trước khi tạo, tách tạo khỏi tải. Từ Kết quả mở Báo cáo một lần và giữ run. Mọi chọn tập dòng chỉ xuất khi backend hỗ trợ đúng loại phạm vi. | Đối chiếu file và oracle cho toàn run, tập lọc, trang và tập chọn. Đếm nhầm scope là lỗi nghiệp vụ, kể cả file tải được. |
| T6. Trở lại sau lỗi, reload hoặc đổi project | Lịch sử, nháp có scope, review được lưu và các đường thủ công. Job đã nhận có thể còn chạy sau khi đổi bề mặt. | Lịch sử mở từ một điểm chung, trở lại hội thoại cụ thể. Quy tắc tự khôi phục bên dưới không tự gửi. Khi lỗi provider, giải thích khả năng tiếp tục và đưa lối thủ công trực tiếp. | Dựng tình huống receipt chưa rõ, access revoked, review expired, hai dự án có tên gần nhau. Đếm trùng request, mất draft, rò dữ liệu và thời gian phục hồi. |

Ghi mỗi lượt bằng route, viewport, vai trò, revision, fixture, thiết bị nhập, thao tác bắt đầu/kết thúc, click, field đã điền, số chuyển trang, số quyết định, lỗi và thời gian. Tách thời gian chờ job khỏi thời gian thao tác. So sánh hiện tại và đề xuất với cùng tác vụ, dữ liệu, người dùng và điều kiện provider, báo riêng số đo thiết kế dự kiến và số đo người dùng. Hành trình thành công khi đạt kết quả nghiệp vụ, như tải đúng run và giải thích đúng nguồn, kể cả giao diện cần nhiều click hơn. Phát hiện sai quyền, sai scope, phê duyệt ngoài ý muốn hoặc mất nháp có ưu tiên cao hơn việc rút ngắn click.

## 4. So sánh điều hướng

| Phương án | Cấu trúc | Lợi | Đổi lại | Thử trước khi duyệt |
| --- | --- | --- | --- | --- |
| A · Assistant-only | AI Assistant, Lịch sử, Cài đặt. Vào Dữ liệu/Đối soát/Báo cáo từ Chat, trợ giúp thao tác hoặc deep link. | Menu ngắn, gần quyết định 02/11. Người mới tập trung vào một điểm bắt đầu. | Người dùng lặp lại phải đoán chỗ mở manual fallback. Tính sẵn có của Chat ảnh hưởng khả năng tìm công việc. Có nguy cơ người dùng nghĩ chỉ thao tác được qua AI. | Với Chat chưa có hội thoại và provider lỗi, tìm được nguồn, bảng đối soát và xuất đúng run bằng đường nhìn thấy. |
| B · Assistant trung tâm với sáu lối vào | AI Assistant · Dữ liệu · Đối soát · Báo cáo · Lịch sử · Cài đặt. Ngoại lệ là phần của Kết quả trong Đối soát. | Bảo toàn lối vào hiện có, ít đổi mô hình người dùng, mỗi bề mặt có một trách nhiệm. Mở nghiệp vụ từ nav độc lập với provider. | Đối soát và Báo cáo có thể bị hiểu là hai nơi có kết quả khác nhau. Cần tách nhãn “xử lý/chọn lần chạy” và “tổng hợp/tải xuống”, cùng một run và dữ kiện. | Người mới biết bắt đầu ở Assistant, kế toán tìm Ngoại lệ trong Đối soát, biết khi nào dùng Báo cáo và không chọn nhầm run. |
| C · Điều hướng theo tác vụ | AI Assistant · Chuẩn bị dữ liệu · Đối soát và kết quả · Cài đặt. Lịch sử ở Assistant, Báo cáo ở Kết quả. | Bốn mục, có thể gần mô hình “chuẩn bị → đối soát → xuất”. | Đổi tên, thêm độ sâu truy cập Báo cáo và Lịch sử. Phải chứng minh người dùng tìm đúng tác vụ trước khi đổi vị trí. | Thử tìm một cuộc trò chuyện và xuất lại báo cáo cũ khi chưa mở run nào. |

**Khuyến nghị B, chờ phê duyệt.** Trải nghiệm duyệt, làm việc với bảng lớn và phục hồi lỗi dựa trên cùng các API ở cả hai lối vào. Hai tên Đối soát và Báo cáo thể hiện hai công việc. Đối soát là nơi chọn quy tắc, theo dõi lần chạy và xử lý chênh lệch. Báo cáo trình bày tổng hợp của một lần chạy cụ thể, lọc nếu được hỗ trợ và tạo bản xuất. Không nhân bản state hoặc kết quả giữa hai vùng. Nếu UAT chỉ ra kế toán chủ yếu vào Ngoại lệ từ mọi màn hình, thử link phụ trong Đối soát trước khi tăng cấp nav.

## 5. Sơ đồ bề mặt đề xuất

```text
Dự án được cấp quyền
├─ AI Assistant (trang vào mặc định)
│  ├─ Bắt đầu / Hội thoại hiện tại
│  ├─ Tiến trình / Làm rõ / Thẻ quyết định / Kết quả ngắn
│  └─ Chi tiết ngữ cảnh: nguồn, bảng, kết quả, nhóm, bằng chứng
├─ Dữ liệu
│  ├─ Danh sách nguồn / tải tệp
│  └─ Nguồn → Gốc / Đã chuẩn bị / Đã chuẩn hóa / Cần kiểm tra
├─ Đối soát
│  ├─ Lần chạy / Quy tắc / Thủ công
│  └─ Kết quả → Tổng quan / Nhóm giao dịch / Ngoại lệ / Bằng chứng
├─ Báo cáo → chọn lần chạy / phạm vi / định dạng / tải báo cáo
├─ Lịch sử → một danh sách hội thoại theo dự án → hội thoại
└─ Cài đặt → tài khoản / không gian / quyền và riêng tư / nâng cao
```

Tabs hoặc disclosure trong sơ đồ là nhóm nội dung. Tên và trạng thái cuối xem đặc tả màn hình. Nút Lịch sử luôn đi đến cùng một panel/drawer theo project. Nội dung trong history không lặp sang sidebar; một trigger có thể dùng lại ở Chat trên mobile nếu nút điều hướng đang thu gọn. Điều hướng theo `historyOpen` và `conversationId` hiện có; không cần route `history` mới. Route `exceptions` cũ có thể làm active parent “Đối soát”, đồng thời giữ URL/ID/khả năng quay lại.

### App Shell và header

| Lớp | Trách nhiệm đề xuất | Quy tắc |
| --- | --- | --- |
| Shell | Khôi phục phiên, navigation, project context, overlay coordinator | AppShell giữ các state route và scope. Vùng nghiệp vụ tải theo project/resource, hủy hoặc bỏ phản hồi cũ khi scope đổi. Một heading chính và skip link tới main. |
| Sidebar | AI Assistant ưu tiên; Dữ liệu/Đối soát/Báo cáo cùng nhóm; Lịch sử và Cài đặt phân biệt hành động/route | Desktop rộng 240 px, rail 64 px. Tên nhìn thấy khi mở, tooltip khi focus/hover ở rail và accessible name tồn tại độc lập. `aria-current` cho route đang hoạt động, `aria-expanded` cho History và trigger thu/mở. Icon chỉ hỗ trợ nhận diện. Ghi preference hiển thị có scope tài khoản, không ghi trạng thái overlay mobile lâu dài. |
| Header shell | Điều hướng nhỏ, tên dự án, khu hành động chính của bề mặt | Mục tiêu 56 px cho hàng shell bình thường, có thể tăng chiều cao khi reflow/zoom. Chat đặt tên project và ngữ cảnh ngắn, model selector thuộc composer. Các trang nghiệp vụ hiện tên trang ở main, header chỉ lặp lại khi cần cho vị trí và lối quay về. |
| Header tác vụ | Tên nguồn hoặc lần chạy, kỳ/currency/revision khi có tác động, một CTA | Chỉ có breadcrumb ở đường sâu có cha thực, như Đối soát → lần chạy → nhóm. Nếu đã có heading “Nguồn B”, nhãn đầu trang không nhắc lại. Scope quan trọng nằm cạnh hành động hoặc ở dòng tóm tắt, không giấu trong tooltip. |
| Thông báo và policy | Kết nối, trạng thái provider, lỗi, thiếu quyền | Không dùng badge policy thường trực như chỉ báo provider khỏe. Ở composer/notice, giữ provider đang chọn, job đã gửi dùng provider nào và lỗi thực tế. Cài đặt hiển thị policy, hạn mức theo quyền. Trạng thái kết nối hiện khi ảnh hưởng công việc. |

Ở 390 px và dưới 768 px, nav là drawer có scrim và nhãn. Escape hoặc nút Đóng trả focus về nút mở. Ở 768 px, mặc định rail hoặc drawer nếu vùng chính không đủ bề rộng, mỗi lần chỉ mở một overlay. Ở 1366 px dùng rail hoặc sidebar theo preference. Context mở drawer. Ở 1440/1920 px dock context khoảng 400 px *khi* vùng Chat vẫn đủ rộng, mục tiêu tối thiểu 640 px vùng đọc sau gutters và thanh cuộn. Ví dụ 1440 − 240 − 400 − 2×32 = 736 px trước các phần cố định khác. Khi triển khai, kiểm bằng kích thước thực. Mặc định panel đóng, khi không đủ bề rộng thì chuyển drawer hoặc mobile fullscreen. Không đặt min-width cưỡng ép làm cả trang tràn ngang. Chiều rộng transcript, composer và mật độ bảng xem các token đề xuất và quyết định mở.

### Chat và Context Panel

- Inline giữ câu trả lời ngắn, receipt tải lên, tiến trình, số liệu có nhãn phạm vi, câu làm rõ và thẻ quyết định. Bảng chỉ preview có giới hạn và hành động rõ để xem thêm; dòng số liệu hiển thị đúng ngữ cảnh và không bị biến thành tóm tắt khác khi đổi kích thước.
- Context Panel mở khi người dùng bấm “Xem dữ liệu”, “Xem nhóm” hoặc “Xem bằng chứng”. Đọc cùng ngữ cảnh gồm project và một hay nhiều ref cụ thể như dataset/table/revision, run/snapshot/group/member/case. Hiển thị tên và kỳ, phản hồi lỗi stale hoặc thiếu quyền. Bằng chứng bên trong panel dùng stack nội dung với nút quay lại, một hệ overlay, không dialog trong dialog.
- Dùng trang nghiệp vụ cho bảng nhiều cột, bộ lọc/phân trang đầy đủ, đối chiếu nhiều thành viên, sửa rule/mapping nâng cao hoặc xử lý nhiều ngoại lệ. Link “Mở trong Dữ liệu/Đối soát” mang theo resource được chọn, không mở mặc định danh sách khác.
- Panel có thể cho đọc dữ kiện ảnh hưởng quyết định. Approval diễn ra ở cùng ReviewCard có hợp đồng quyết định hiện hành, qua Chat hoặc manual fallback được kiểm soát. Panel không tạo thêm action approve hoặc mutation song song. Nút “Quay lại quyết định” đặt focus ở thẻ tương ứng.
- Dock desktop là vùng bổ sung có tiêu đề đọc được, không focus trap, cho chuyển bằng bàn phím giữa main và panel. Drawer/fullscreen overlay quản lý focus, inert vùng nền, khóa scroll nền khi cần. Đóng trở về trigger hoặc heading gần nhất nếu trigger đã biến mất. Đảm bảo vùng Chat tự cuộn, composer không đè dòng cuối hoặc nút review. Mobile bàn phím mở không làm ẩn input/CTA đang focus. Zoom 200% kiểm như trạng thái viewport mới, không cố giữ bố cục desktop.

### Hợp đồng chuyển bề mặt

| Chuyển | Dữ liệu mang theo | Bảo toàn và phục hồi |
| --- | --- | --- |
| Chat → Dữ liệu | Project, dataset, bảng/revision nếu có ref trong DTO | Mở đúng nguồn kể cả ngoài trang danh sách đang tải. Giữ tiêu điểm trên mục đã chọn; quay về đúng hội thoại/anchor. |
| Chat → Review | Conversation, workflow, review, resource/revision | Load cùng review theo quyền và kiểm expiry/fingerprint hiện hành. Nháp của từng review độc lập. Clarification có câu hỏi/options của Backend; xác nhận tài chính qua action nghiệp vụ hiện có. |
| Chat → Đối soát → Kết quả | Project, plan nếu mở quy tắc, run nếu mở kết quả | Gợi ý kế hoạch phải có preflight/approval đúng trình tự. Run đang mở phải xác minh được từ route hoặc ref; không lấy run gần nhất để thay. |
| Chat/Kết quả → Bằng chứng | Run, group/case và member hoặc row ref nếu có | Giữ nguồn trái/phải và đủ thành viên. Khi quay lại trả focus về dòng. Xem lịch sử revision phải có nhãn; phần chưa verified giữ phân loại. |
| Chat/Kết quả → Xuất | Run/snapshot hoặc query đã xác nhận, phạm vi thực và định dạng | Không xuất tự động khi mở URL. Backend tạo artifact; giao diện phục hồi polling/id hiện có rồi hiển thị link đã sẵn sàng. |
| Kết quả/Bằng chứng → Chat | Conversation hiện có nếu người dùng chọn, origin, run/group/case | Gắn chip phạm vi đọc được. Khi đang có nháp khác scope, dùng giao diện làm rõ thay vì tự gắn. Quay về bề mặt/case đã mở. |
| Cài đặt → Chat | Chỉ project hợp lệ và lựa chọn cá nhân được phép | Provider mới chỉ áp dụng yêu cầu chưa gửi. Không thay model của request đã nhận. Giữ nháp, lịch sử và scope. |
| Lịch sử → Hội thoại | Project + conversation ID | Tải conversation theo quyền. Phân trang và nhãn “Tìm trong hội thoại đã tải” tương ứng khả năng hiện có. Hội thoại không còn quyền phải fail-closed. |
| Đổi project hoặc workspace | Project mới đã xác nhận, identity/workspace được cấp quyền | Đóng overlay, xóa state dẫn xuất từ nguồn/run của project trước, hủy/loại kết quả API đến muộn. Ghi nháp cũ trong scope đúng trước khi reset. Không chuyển dữ liệu sang scope mới. |
| Back/forward/reload | URL chỉ chứa ID được phép, state lọc/anchor phù hợp phiên và scope | Tôn trọng các deep link cũ. Điều hướng bề mặt thực tạo history entry. Đóng drawer không nhảy sang run khác. Restore dữ liệu theo authorization, draft/request key hợp lệ và state từng scope. Refresh không gửi lại thao tác. Không đặt raw values, tokens hoặc nội dung chat trong URL. |

Field thêm như `table_id`, revision hoặc query state trong bảng là **yêu cầu trải nghiệm**. `navigation.ts` hiện hỗ trợ tập ID giới hạn; mở rộng hợp đồng URL cần kiểm tương thích, thực hiện tối thiểu hoặc dùng session state scoped theo [kế hoạch nghiệm thu](IMPLEMENTATION_AND_ACCEPTANCE_PLAN.md). Không đòi API mới để dựng shell. Tìm lịch sử toàn cục, ghim panel liên phiên, cross-project views và chọn xuất nhiều dòng chỉ mở khi có contract và quyết định riêng.

## 6. Tham khảo bên ngoài

Các mẫu được đọc ngày 09/11/2026 trong tài liệu gốc. **REFERENCE** mô tả hành vi công bố. Áp dụng vào Studio là **PROPOSED**. Bằng chứng tài liệu nhà cung cấp có giới hạn về hiệu quả trên dữ liệu, nghiệp vụ và người dùng Studio. Dùng mô hình tương tác, không dùng hình ảnh, mã hoặc tài nguyên nhận diện.

| Nguồn | Mẫu được mô tả | Vấn đề và điểm phù hợp | Giới hạn và điều chỉnh cho Studio |
| --- | --- | --- | --- |
| ChatGPT | Project nhóm hội thoại, tệp và ngữ cảnh liên quan. [OpenAI Help](https://help.openai.com/en/articles/10169521-projects-in-chatgpt) | Giảm nhầm dự án và tệp khi quay lại Chat. | ChatGPT project memory không xác lập scope đối soát. Studio dùng project/conversation/run ID và authorization, giữ draft tách theo scope, không tự chuyển chat giữa dự án. |
| Claude | Artifact độc lập mở cạnh hội thoại. [Claude Help](https://support.claude.com/en/articles/17153992-what-are-artifacts-and-how-do-i-use-them) | Đọc bảng và chứng từ trong khi giữ vị trí trao đổi. | Canvas có sửa/chia sẻ là mục đích khác. Context Panel Studio đọc artifact scoped, mở khi người dùng yêu cầu, không sửa raw và không tạo chat thứ hai. |
| Linear | Sidebar chứa lối trực tiếp đến vùng làm việc; nhóm trang theo team. [Linear Teams](https://linear.app/docs/teams) · [Sidebar update](https://linear.app/changelog/2022-02-11-sidebar-update) | Tìm nhanh các trang dùng lặp lại và nhận biết context. | Cây team/custom views không cần cho sáu mục. Giữ một cấp nav chính, đề phòng giấu lối vào nghiệp vụ thêm click. |
| Numeric | Gắn workpaper hỗ trợ vào tài khoản và xem dữ liệu liên quan trong quy trình reconciliation. [Numeric](https://www.numeric.io/solutions/account-reconciliation-software) | Tổng quan phải dẫn được về chứng từ hoặc giao dịch bên dưới. | Trang mô tả sản phẩm, chưa đo hiệu quả. Studio truy đến row/cell/revision thuộc nguồn đã lưu, không sửa workpaper gốc tại panel hoặc nhập chính sách auto-submit của Numeric. |
| Ledge | Audience filter xác định phần giao dịch được đưa vào match, rules đặc hiệu theo định danh và matching có thể độc lập với amount. [Ledge Transaction Matching](https://docs.ledge.co/transaction-matching/overview) | Người đọc cần biết trước hết dòng nào trong phạm vi và theo khóa nào, rồi mới đọc chênh tiền. | Chỉ học cách giải thích scope và rule. Không áp dụng thứ tự rule, tự động tạo match hoặc định nghĩa cutoff của Ledge vào engine Studio. |
| Microsoft Dynamics 365 Finance | Worksheet đối soát dùng cutoff, quy tắc và phần giao dịch khớp/chưa khớp. [Microsoft Learn](https://learn.microsoft.com/en-us/dynamics365/finance/cash-bank-management/reconcile-bank-statements-advanced-bank-reconciliation) | Người làm tài chính cần nhận ra hai nguồn, kỳ và truy ra dòng chưa khớp. | Không mô phỏng bốn bảng ERP trên mobile, không sao chép cơ chế posting, penny corrections hoặc N:M. Dùng tab kết quả và panel thành viên từ hợp đồng Studio. |
| Flatfile | Bước mapping nối cột nguồn với trường đích trước bảng review. [Flatfile Mapping Data](https://support.flatfile.com/articles/8569925090-mapping-data) | Hỗ trợ người mới thấy “cột nào sang trường nào” và chọn sheet đúng. | Giữ mapping đề xuất, kiểm tra và approval là ba trạng thái. Không suy nghiệp vụ từ tỷ lệ marketing hoặc tự chuyển dữ liệu gốc. |
| OneSchema | Trình nhập theo upload → mapping → review; tài liệu nhập phân biệt valid/warning/error và giá trị trước/sau. [Importer](https://docs.oneschema.co/docs/dashboard-importer) · [Validation](https://docs.oneschema.co/docs/validating-and-importing) | Hiểu được tệp đã nhận, bản tự chuẩn bị, dòng cảnh báo và lỗi. | Không áp dụng mặc định partial import/loại dòng. Studio giữ counts, provenance, điều kiện cho phép một phần và xác nhận của người dùng khi contract yêu cầu. |
| Fluent 2 | Drawer inline giữ main tương tác được, overlay dùng cho ngữ cảnh cần tập trung; nav chính có thể thu gọn. [Drawer](https://fluent2.microsoft.design/components/web/react/core/drawer/usage) · [Nav](https://fluent2.microsoft.design/components/web/react/core/nav/usage) | Dùng đúng loại bề mặt ở desktop/tablet/mobile. | Fluent Nav hiện không hỗ trợ icon-only. Rail của Studio là đề xuất riêng cần tên, tooltip và UAT, không mang thư viện. Tooltip ngắn; quyết định có hệ quả dùng thẻ chính hoặc dialog đúng semantics. |
| IBM Carbon | Data table có toolbar và thanh batch chỉ khi có lựa chọn. [Carbon data table](https://www.carbondesignsystem.com/building-blocks/core/components/data-table/guidelines) | Phân biệt tập đang lọc, trang hiện tại và dòng được chọn. | Không suy backend hỗ trợ batch hoặc xuất theo dòng. Chỉ hiện CTA theo contract, hiển thị phạm vi trước thao tác. |
| Nielsen Norman Group | Progressive disclosure đưa phần ít dùng vào lớp chi tiết có lối mở dễ hiểu, cảnh báo về quá nhiều tầng. [NN/g](https://www.nngroup.com/articles/progressive-disclosure/) | Thẻ quyết định ngắn hơn, phần kỹ thuật mở theo nhu cầu. | Currency, gross/net, grain, khóa, kỳ, coverage và tolerance có ảnh hưởng phải nhìn thấy trước khi duyệt. Không đưa vào tooltip hoặc wizard nhiều tầng. |
| WCAG 2.2 | Tiêu chí focus nhìn thấy, không bị che hoàn toàn, reflow, kích cỡ đích và phòng ngừa sai sót pháp lý/tài chính/dữ liệu. [W3C Recommendation](https://www.w3.org/TR/WCAG22/) | Ngăn composer/drawer che focus và duyệt nhầm; dùng bàn phím, zoom và nhãn rõ. | AA 2.4.11 khác AAA 2.4.12. Studio đặt mục tiêu thiết kế focus nhìn thấy hoàn toàn; kiểm AA theo từng SC, thêm thử screen reader, IME và bàn phím thật. |

### Kết quả đối chiếu hai Skill

- **Impeccable 4.8.1 · Operate/critique/shape.** Dùng lăng kính nhiệm vụ, thứ bậc, khả năng tìm đường, thao tác bàn phím và khả năng phục hồi để so phương án. Áp dụng mô hình “một CTA cho bước kế tiếp”, trạng thái tác vụ có nhãn và mở chi tiết có chủ đích. Đây là phần phân tích từ playbook cho đặc tả, không phải một phiên critique độc lập có snapshot. Kiểm lại blueprint bằng các trường hợp người mới, người chỉ xem, người phục hồi và người cần truy nguyên.
- **UI UX Pro Max 2.15.0 · tra cứu cục bộ.** `minimal navigation collapsible sidebar --domain ux` trả Sticky Navigation và Keyboard Navigation. Dùng quy tắc không che vùng focus, giữ thứ tự Tab; số px lấy theo layout Studio. `AI assistant productivity application --domain product` đưa drill-down và visual hierarchy rõ; dùng drill-down từ kết quả đến nguồn, bỏ gợi ý interactive demo, purple accent và glassmorphism vì lệch tác vụ.
- `complex business approval progressive disclosure --domain ux` trả Heading Line Balance, sai trọng tâm nên loại. Truy vấn hẹp `error prevention confirmation financial --domain ux` cho gợi ý báo lỗi và xác nhận kết quả; đối chiếu với NN/g và hợp đồng ReviewRequest để giữ các dữ kiện quyết định. `focus not obscured --domain ux` trả tiêu chí Enhanced AAA, dùng làm mục tiêu thiết kế, giữ tiêu chí nghiệm thu AA theo W3C. Không persist output.
- Kiểm lại 3 điểm dễ lệch khi chuyển qua component. Nav và composer không lặp project label vô cớ. Panel chỉ mở khi yêu cầu và không thêm phê duyệt. Trên mobile giữ một bề mặt hoạt động, cùng dữ kiện quyết định và cùng đường về. Bảng màu/chữ/spacing chỉ có một bộ trong [design system](DESIGN_SYSTEM_BLUEPRINT.md).
