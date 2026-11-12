# AI Reconciliation Studio

**Trợ lý AI giúp chuẩn hóa, đối soát và phân tích dữ liệu — từ tệp nguồn đến kết quả có thể kiểm chứng.**

Làm việc với nhiều bảng dữ liệu thường bắt đầu bằng việc tìm đúng cột, hiểu ý nghĩa số tiền và lần theo những giao dịch không khớp. AI Reconciliation Studio đưa các bước đó vào một không gian hội thoại tiếng Việt: bạn tải tệp, giao yêu cầu, kiểm tra đề xuất và nhận kết quả có thể truy ngược về nguồn.

Ứng dụng phù hợp với người cần đối chiếu sổ cái, chứng từ, đơn hàng hoặc dữ liệu thanh toán từ CSV/XLSX. Đây là công cụ hỗ trợ kiểm tra sai lệch, không phải kết luận kiểm toán độc lập.

## Bạn có thể làm gì?

- **Chuẩn bị dữ liệu:** tự đọc và kiểm tra CSV/XLSX sau khi tải lên, chuẩn hóa khi đủ căn cứ và giữ riêng những dòng có vấn đề.
- **Đối soát nhiều nguồn:** tìm giao dịch khớp, lệch tiền, thiếu đối ứng hoặc còn mơ hồ; hỗ trợ ghép khóa và gộp dòng theo quy tắc được duyệt.
- **Hỏi và phân tích:** tra cứu bằng tiếng Việt, lọc dữ liệu, hỏi tiếp theo ngữ cảnh và xem biểu đồ từ kết quả có cấu trúc.
- **Kiểm tra bằng chứng:** mở từng dòng gốc, xem dữ liệu trước/sau chuẩn hóa và kiểm tra hai phía của giao dịch.
- **Xuất và tiếp tục công việc:** tải báo cáo CSV/XLSX, mở lịch sử và quay lại kết quả đã lưu.

Các tệp có cấu trúc khác nhau không cần bị ép thành cùng một bảng từ đầu. Khi thiếu nghĩa của cột, kỳ dữ liệu hoặc quy tắc so sánh, ứng dụng hỏi lại để bạn kiểm tra trước khi xử lý.

## Cách hoạt động

**Tải tệp → Studio tự chuẩn bị → Hỏi trong AI Assistant → Kiểm chứng và xuất báo cáo.**

AI giúp hiểu yêu cầu và đề xuất cách làm. Hệ thống tính toán tiền bằng Decimal và kiểm chứng riêng việc phân nhóm, sử dụng dòng nguồn và bảo toàn số tiền. AI không tự phê duyệt quy tắc tài chính hoặc sửa dữ liệu gốc để làm kết quả khớp.

Một đề xuất chưa được duyệt không phải là kết quả đối soát. Dữ liệu đã đọc, đã chuẩn hóa, còn lỗi và kết quả được kiểm chứng một phần được thể hiện riêng.

## Bắt đầu sử dụng

Xem [hướng dẫn từng bước và bộ dữ liệu tự kiểm thử](docs/USER_TEST_GUIDE.md), từ tạo dự án đến kiểm chứng và xuất Excel.

Trong bản giao diện mới, bộ chọn **Trợ lý cho tin nhắn mới** nằm trong **Tùy chọn hội thoại**. Quyền của không gian làm việc và khả dụng của từng trợ lý quyết định mục nào chọn được. Xem phiên bản hiện hành và số liệu kiểm thử trong [báo cáo triển khai](docs/IMPLEMENTATION_STATUS.md).

1. Tải CSV/XLSX từ **Dữ liệu** hoặc **AI Assistant**. Studio xử lý nền ngay sau khi tải.
2. Hỏi **AI Assistant** về dữ liệu gốc, bản đã xử lý, các dòng lỗi hoặc yêu cầu đối chiếu. Khi cần, bổ sung ý nghĩa của một trường ngay trong Chat.
3. Xem kết quả và tải báo cáo trong Chat. **Dữ liệu**, **Đối soát** và **Báo cáo** vẫn cung cấp công cụ kiểm tra chi tiết và thiết lập nghiệp vụ.
4. Dùng **Lịch sử** để tiếp tục công việc. Mở **Cài đặt** để xem quyền, chính sách chia sẻ và chọn mật độ bảng.
5. Chủ không gian có thể mở **Quản lý dự án** hoặc **Quản lý nguồn**, xem tác động rồi lưu trữ hoặc **Đưa vào Thùng rác** khi được phép. Dùng danh sách tương ứng trong trình quản lý để khôi phục.

Ví dụ yêu cầu:

- “Ba tệp của mình đã xử lý xong chưa?”
- “Cho mình xem 10 dòng dữ liệu gốc.”
- “Đối soát ba nguồn giúp mình.”
- “Cho tôi xem ba nhóm giao dịch lệch tiền lớn nhất của kết quả đang xem.”
- “Giải thích nhóm thứ hai.”
- “Xuất kết quả đối soát đang xem ra Excel.”

Câu trả lời phụ thuộc vào nguồn đã chọn, dữ liệu đã xác nhận và quyền sử dụng. Nếu chưa đủ thông tin, ứng dụng cần bạn bổ sung thay vì tự đoán.

## Chạy local

Cần Windows/PowerShell và Docker Desktop đang chạy, cổng `127.0.0.1:18180` còn trống. Trên máy mới, clone repository, đứng tại thư mục gốc và kiểm tra `.env.example`. Script tạo `.env` với bí mật local ngẫu nhiên nếu chưa có; cấu hình dịch vụ AI và quyền workspace là bước riêng, không tự được cấp khi khởi động.

**Khởi động lần đầu hoặc build lại:**

```powershell
.\tools\start.ps1
```

Lệnh build thường yêu cầu các tệp đầu vào của ứng dụng đã được commit để nhãn image trỏ đúng mã nguồn.

**Mở lại môi trường đã có image:**

```powershell
.\tools\start.ps1 -SkipBuild
```

Sau đó mở [AI Reconciliation Studio](http://127.0.0.1:18180). Không cần nhập token trên giao diện.

Lệnh khởi động đợi bốn dịch vụ healthy rồi xác minh loopback và phiên qua địa chỉ web. Nếu thấy `LOCAL_DEMO_NOT_VERIFIED` khi các dịch vụ vẫn healthy sau restart hoặc recreate, chạy `./tools/verify-local.ps1` tại repository root rồi bấm **Thử kết nối lại**. Khi stack đang dừng, chạy `./tools/start.ps1 -SkipBuild`. Kiểm revision, digest release/rollback và kết quả kiểm tra tại [báo cáo triển khai](docs/IMPLEMENTATION_STATUS.md).

## Quyền riêng tư và độ tin cậy

Tệp gốc được bảo toàn, kết quả có tham chiếu nguồn và quy tắc mới cần được phê duyệt. Không tự biến dữ liệu thiếu thành 0, bỏ số 0 đầu mã giao dịch hoặc gộp các loại tiền khác nhau. Các trường hợp chưa đủ bằng chứng được giữ để kiểm tra.

AI hoạt động theo cấu hình, quyền workspace và điều kiện dịch vụ hiện hành; dữ liệu được phép có thể được gửi đến dịch vụ bên ngoài. Môi trường local được cấp quyền có thể bỏ trần số lượt request nội bộ, nhưng usage vẫn được ghi nhận và quota/rate limit/chi phí của nhà cung cấp vẫn áp dụng. Không đồng nghĩa AI miễn phí hoặc nhà cung cấp không giới hạn.

Xóa vĩnh viễn mặc định tắt. Khi môi trường local đã được nghiệm thu và chủ dự án cho phép, người vận hành có thể bật `PURGE_LOCAL_ENABLED=true` cho Backend và Worker rồi chạy `tools/start.ps1` để xác minh loopback. Chủ workspace phải xem tác động và nhập đúng tên cho từng tài nguyên. Biên nhận ghi trạng thái dọn tệp sau khi metadata đã commit. Nếu trạng thái còn đang dọn, giữ cấu hình và volume đã xác minh để Worker tiếp tục. Workspace `demo` và các bản sao lưu được bảo vệ.

PostgreSQL và tệp dữ liệu được giữ trong hai volumes của ứng dụng. GitHub chỉ lưu source, không thay backup dữ liệu. Không xóa volumes để dọn Docker; hướng dẫn backup, kiểm chứng và rollback nằm trong tài liệu kỹ thuật.

## Phạm vi hỗ trợ

Sản phẩm hiện là MVP local với đường sử dụng chuẩn là **CSV/XLSX**. PDF/DOCX có bộ đọc được kiểm soát riêng, cần quyền và allowance riêng; không phải định dạng đính kèm phổ thông trong Chat. Không tự mở quyền parser khi bật AI.

Chưa nghiệm thu triển khai Internet hoặc nhiều người dùng đồng thời. Khả năng hiểu ngôn ngữ tự nhiên có giới hạn; kết quả quan trọng cần được kiểm tra cùng nguồn và quy tắc. Trạng thái nghiệm thu thực tế, lỗi đã biết và phiên bản đang chạy được ghi trong báo cáo triển khai.

## Tài liệu kỹ thuật

- [Kiến trúc](docs/ARCHITECTURE.md) và [hợp đồng dữ liệu](docs/DATA_CONTRACTS.md).
- [Tích hợp và quyền AI](docs/AI_INTEGRATION.md).
- [Kiểm thử, backup và khôi phục](docs/TESTING_GUIDE.md#quy-trình-kiểm-thử-và-khôi-phục-hiện-hành).
- [Báo cáo triển khai và nghiệm thu](docs/IMPLEMENTATION_STATUS.md).
- [Kiểm toán giao diện](docs/INTERFACE_REDESIGN_AUDIT.md), [hướng UX D01–D10 đã phê duyệt](docs/ui-redesign/OPEN_DECISIONS.md) và [kế hoạch nghiệm thu](docs/ui-redesign/IMPLEMENTATION_AND_ACCEPTANCE_PLAN.md).
- [Kế hoạch sản phẩm](docs/PROJECT_PLAN.md), [kế hoạch Agent](docs/AI_AGENT_MVP_IMPLEMENTATION_PLAN.md) và [quy tắc đóng góp](Rules.md).
