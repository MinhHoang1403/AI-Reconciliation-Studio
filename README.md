# AI Reconciliation Studio

**Trợ lý AI giúp chuẩn hóa, đối soát và phân tích dữ liệu — từ tệp nguồn đến kết quả có thể kiểm chứng.**

Làm việc với nhiều bảng dữ liệu thường bắt đầu bằng việc tìm đúng cột, hiểu ý nghĩa số tiền và lần theo những giao dịch không khớp. AI Reconciliation Studio đưa các bước đó vào một không gian hội thoại tiếng Việt: bạn tải tệp, giao yêu cầu, kiểm tra đề xuất và nhận kết quả có thể truy ngược về nguồn.

Ứng dụng phù hợp với người cần đối chiếu sổ cái, chứng từ, đơn hàng hoặc dữ liệu thanh toán từ CSV/XLSX. Đây là công cụ hỗ trợ kiểm tra sai lệch, không phải kết luận kiểm toán độc lập.

## Bạn có thể làm gì?

- **Chuẩn bị dữ liệu:** đọc CSV/XLSX, xem các sheet, đề xuất cách ghép cột và chuẩn hóa theo ý nghĩa bạn xác nhận.
- **Đối soát nhiều nguồn:** tìm giao dịch khớp, lệch tiền, thiếu đối ứng hoặc còn mơ hồ; hỗ trợ ghép khóa và gộp dòng theo quy tắc được duyệt.
- **Hỏi và phân tích:** tra cứu bằng tiếng Việt, lọc dữ liệu, hỏi tiếp theo ngữ cảnh và xem biểu đồ từ kết quả có cấu trúc.
- **Kiểm tra bằng chứng:** mở từng dòng gốc, xem dữ liệu trước/sau chuẩn hóa và kiểm tra hai phía của giao dịch.
- **Xuất và tiếp tục công việc:** tải báo cáo CSV/XLSX, mở lịch sử và quay lại kết quả đã lưu.

Các tệp có cấu trúc khác nhau không cần bị ép thành cùng một bảng từ đầu. Khi thiếu nghĩa của cột, kỳ dữ liệu hoặc quy tắc so sánh, ứng dụng hỏi lại để bạn kiểm tra trước khi xử lý.

## Cách hoạt động

**Tải tệp → AI đề xuất → Bạn xác nhận → Chuẩn hóa → Đối soát → Kiểm chứng → Phân tích → Xuất báo cáo.**

AI giúp hiểu yêu cầu và đề xuất cách làm. Hệ thống tính toán tiền bằng Decimal và kiểm chứng riêng việc phân nhóm, sử dụng dòng nguồn và bảo toàn số tiền. AI không tự phê duyệt quy tắc tài chính hoặc sửa dữ liệu gốc để làm kết quả khớp.

Một đề xuất chưa được duyệt không phải là kết quả đối soát. Dữ liệu đã đọc, đã chuẩn hóa, còn lỗi và kết quả được kiểm chứng một phần được thể hiện riêng.

## Bắt đầu sử dụng

Xem [hướng dẫn từng bước và bộ dữ liệu tự kiểm thử](docs/USER_TEST_GUIDE.md), từ tạo dự án đến kiểm chứng và xuất Excel.

Trong ô Chat, bạn có thể chọn Gemini cloud hoặc thử Qwen local qua Ollama, tùy cấu hình và quyền của không gian làm việc. Trạng thái nghiệm thu từng model được ghi trong [báo cáo triển khai](docs/IMPLEMENTATION_STATUS.md).

1. Mở **AI Assistant**, đính kèm CSV/XLSX và nêu công việc bằng tiếng Việt.
2. Xem dữ liệu và trả lời các điểm chưa rõ. Kiểm tra, duyệt cách ghép cột hoặc quy tắc mới khi được yêu cầu.
3. Đọc kết quả, mở **Xem dòng gốc** để kiểm tra bằng chứng hoặc xuất báo cáo.
4. Dùng **Lịch sử** để tiếp tục công việc. **Cài đặt** chỉ hiển thị tài khoản, quyền riêng tư và giới hạn tệp dành cho người sử dụng.

Ví dụ yêu cầu:

- “Kiểm tra hai tệp vừa tải và cho tôi xem cấu trúc dữ liệu.”
- “Đề xuất cách chuẩn hóa các cột; hỏi lại những điểm chưa rõ.”
- “Cho tôi xem ba nhóm giao dịch lệch tiền lớn nhất của kết quả đang xem.”
- “Giải thích giao dịch thứ hai dựa trên dữ liệu nguồn.”
- “Xuất kết quả đối soát đang xem ra Excel.”

Câu trả lời phụ thuộc vào nguồn đã chọn, dữ liệu đã xác nhận và quyền sử dụng. Nếu chưa đủ thông tin, ứng dụng cần bạn bổ sung thay vì tự đoán.

## Chạy local

Cần Windows/PowerShell và Docker Desktop đang chạy, cổng `127.0.0.1:18180` còn trống. Trên máy mới, clone repository, đứng tại thư mục gốc và kiểm tra `.env.example`. Script tạo `.env` với bí mật local ngẫu nhiên nếu chưa có; cấu hình dịch vụ AI và quyền workspace là bước riêng, không tự được cấp khi khởi động.

**Khởi động lần đầu hoặc build lại:**

```powershell
.\tools\start.ps1
```

**Mở lại môi trường đã có image:**

```powershell
.\tools\start.ps1 -SkipBuild
```

Sau đó mở [AI Reconciliation Studio](http://127.0.0.1:18180). Không cần nhập token trên giao diện.

Lệnh khởi động đợi bốn dịch vụ khỏe, xác minh cổng loopback và kiểm tra phiên làm việc qua chính địa chỉ web. Sau khi máy/Docker/Backend khởi động lại hoặc recreate Frontend, dùng lại lệnh `-SkipBuild`; nếu trang đang mở, bấm **Thử kết nối lại**. Không xóa cookies hoặc dữ liệu để khôi phục kết nối.

## Quyền riêng tư và độ tin cậy

Tệp gốc được bảo toàn, kết quả có tham chiếu nguồn và quy tắc mới cần được phê duyệt. Không tự biến dữ liệu thiếu thành 0, bỏ số 0 đầu mã giao dịch hoặc gộp các loại tiền khác nhau. Các trường hợp chưa đủ bằng chứng được giữ để kiểm tra.

AI hoạt động theo cấu hình, quyền workspace và điều kiện dịch vụ hiện hành; dữ liệu được phép có thể được gửi đến dịch vụ bên ngoài. Môi trường local được cấp quyền có thể bỏ trần số lượt request nội bộ, nhưng usage vẫn được ghi nhận và quota/rate limit/chi phí của nhà cung cấp vẫn áp dụng. Không đồng nghĩa AI miễn phí hoặc nhà cung cấp không giới hạn.

PostgreSQL và tệp dữ liệu được giữ trong hai volumes của ứng dụng. GitHub chỉ lưu source, không thay backup dữ liệu. Không xóa volumes để dọn Docker; hướng dẫn backup, kiểm chứng và rollback nằm trong tài liệu kỹ thuật.

## Phạm vi hỗ trợ

Sản phẩm hiện là MVP local với đường sử dụng chuẩn là **CSV/XLSX**. PDF/DOCX có bộ đọc được kiểm soát riêng, cần quyền và allowance riêng; không phải định dạng đính kèm phổ thông trong Chat. Không tự mở quyền parser khi bật AI.

Chưa nghiệm thu triển khai Internet hoặc nhiều người dùng đồng thời. Khả năng hiểu ngôn ngữ tự nhiên có giới hạn; kết quả quan trọng cần được kiểm tra cùng nguồn và quy tắc. Trạng thái nghiệm thu thực tế, lỗi đã biết và phiên bản đang chạy được ghi trong báo cáo triển khai.

## Tài liệu kỹ thuật

- [Kiến trúc](docs/ARCHITECTURE.md) và [hợp đồng dữ liệu](docs/DATA_CONTRACTS.md).
- [Tích hợp và quyền AI](docs/AI_INTEGRATION.md).
- [Kiểm thử, backup và khôi phục](docs/TESTING_GUIDE.md).
- [Báo cáo triển khai và nghiệm thu](docs/IMPLEMENTATION_STATUS.md).
- [Kế hoạch sản phẩm](docs/PROJECT_PLAN.md), [kế hoạch Agent](docs/AI_AGENT_MVP_IMPLEMENTATION_PLAN.md) và [quy tắc đóng góp](Rules.md).
