# Thiết kế Studio

## Hướng thị giác

Lấy nhịp từ mục lục hồ sơ và dấu chỉ mục. Nền sáng, chữ xanh đen, xanh dương dành cho hành động và phạm vi đang chọn. Dùng đường phân tách để nối nhãn với nội dung. Trạng thái luôn có chữ, số tiền dùng chữ số tabular. Font hệ thống giữ khả năng đọc tiếng Việt và hoạt động offline.

## Bố cục vận hành

- **Điều hướng.** Nút thu gọn nằm bên phải nhận diện Studio và vẫn ở đầu thanh bên khi thu gọn. Bốn khu vực nghiệp vụ và nhóm Quản lý dùng cùng nhịp hàng. Khi thiếu chiều cao, chỉ menu cuộn giữa nhận diện và tài khoản local. Thanh đầu trang chứa hai bộ chọn phạm vi và trạng thái kết nối. Vùng nội dung cuộn độc lập. Trên màn hẹp, điều hướng mở dạng drawer và hai bộ chọn dùng một hàng gọn, với tên đầy đủ trong hộp thoại.
- **Assistant.** Danh sách việc khởi đầu cuộn cùng vùng đọc, phía trên ô gửi cố định. Khi đã có hội thoại, cùng vùng đọc chứa transcript và quyết định chờ duyệt. Biểu mẫu chung trong một lô nguồn nằm trước các thẻ quyết định. Nút xác nhận chỉ điền nháp cho đúng các nguồn liệt kê. Người dùng có thể chọn cột khóa chung khi tên cột văn bản trùng khớp duy nhất ở mọi nguồn. Các thẻ vẫn hiển thị từng khóa và giữ lựa chọn đã có. Lượt duyệt được thực hiện riêng sau khi kiểm từng nguồn.
- **Dữ liệu.** Trên màn rộng, mở bảng nguồn cạnh danh mục đang tìm kiếm. Trên màn hẹp, chỉ mở danh mục hoặc chi tiết. Vị trí đang chọn luôn có nhãn và dấu chọn.
- **Đối soát và báo cáo.** Duy trì hai bề mặt thiết lập và kết quả. Mỗi màn cho biết phạm vi trước khi đọc số. Bảng bằng chứng và ngoại lệ nằm trước biểu đồ phụ trợ. Khi mở chi tiết báo cáo từ Assistant, phần phân bố đã sẵn để cuộn tới. Khu xuất báo cáo đi sau phân bố, với mô tả phạm vi xuất.
- **Cài đặt.** Nhóm theo quyền quản lý, chia sẻ AI, hiển thị và giới hạn tệp. Hành động xóa vĩnh viễn nằm tách khỏi thông tin tài khoản và giữ xác nhận theo quyền.

## Tương tác

Giữ điều khiển web quen thuộc, trạng thái focus rõ, nhãn đầy đủ cho nút chỉ có biểu tượng, và cuộn bảng bên trong vùng dữ liệu. Chi tiết hiển thị cạnh nội dung khi còn đủ chỗ và trở về một cột hoặc drawer khi hẹp. Không dùng chuyển động để biểu đạt trạng thái nghiệp vụ.

Khi bấm chuột hoặc chạm, ô nhập giữ nền hiện có. Vùng nhập câu hỏi trong Chat giữ nền trong suốt trên khung trắng. Khi dùng bàn phím, điều khiển có một nét nhấn ở cạnh dưới. Ô đánh dấu và nút chọn tròn dùng nét bao mảnh để giữ rõ dấu chọn. Cùng quy tắc áp dụng cho hộp thoại. Các dấu hiệu này giữ nguyên kích thước điều khiển và phân biệt với màu của mục đang chọn hoặc cảnh báo.

Trong Xác nhận cột, hộp chọn Trường đích tìm theo tên tiếng Việt và dùng danh sách của cấu trúc đang xem. Mỗi lựa chọn cho biết kiểu dữ liệu. Trường đã gán có lý do vô hiệu hóa. Người dùng có thể giữ nguyên cột nguồn hoặc chủ động thêm trường vào cấu trúc. Hộp chọn hỗ trợ phím mũi tên, Enter và Escape.

Danh sách Xác nhận cột dùng chung lưới cho tiêu đề và các hàng. Cột nguồn, trường đích và trạng thái giữ vị trí khi một hàng thiếu trạng thái hoặc mở trình chỉnh sửa. Khi vùng nội dung hẹp, tên nguồn ở hàng trên, trường đích và trạng thái ở hàng dưới. Danh mục nguồn chừa vị trí cho trạng thái và nút quản lý. Trong bảng kết quả và bằng chứng, tiêu đề và số tiền căn cùng phía, dùng cùng định dạng số.

Đề xuất lại hiển thị tiến độ đến khi công việc kết thúc. Bản đề xuất mới tự mở khi biểu mẫu chưa chỉnh sửa. Nếu đã có thay đổi, Studio giữ bản nháp theo phiên bản và cho người dùng chọn mở bản mới. Thông báo thành công tạm thời tự ẩn sau 5 giây. Lỗi tác vụ và yêu cầu xác nhận nằm tại chỗ để người dùng xử lý.
