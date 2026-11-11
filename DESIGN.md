# Thiết kế Studio

## Hướng thị giác

Lấy nhịp từ mục lục hồ sơ và dấu chỉ mục. Nền sáng, chữ xanh đen, xanh dương dành cho hành động và phạm vi đang chọn. Dùng đường phân tách để nối nhãn với nội dung. Trạng thái luôn có chữ, số tiền dùng chữ số tabular. Font hệ thống giữ khả năng đọc tiếng Việt và hoạt động offline.

## Bố cục vận hành

- **Điều hướng.** Nhận diện Studio mở Dashboard. Nút thu gọn nằm bên phải nhận diện và vẫn ở đầu thanh bên khi thu gọn. Dashboard, bốn khu vực nghiệp vụ và nhóm Quản lý dùng cùng nhịp hàng. Khi thiếu chiều cao, chỉ menu cuộn giữa nhận diện và tài khoản local. Thanh đầu trang chứa hai bộ chọn phạm vi và trạng thái kết nối. Vùng nội dung cuộn độc lập. Trên màn hẹp, điều hướng mở dạng drawer và hai bộ chọn dùng một hàng gọn, với tên đầy đủ trong hộp thoại.
- **Dashboard.** Giới thiệu ngắn và trình tự công việc dạng chữ, sau đó là lưới bốn chức năng, tổng quan dự án và dữ liệu gần đây. Trên điện thoại, các phần xếp dọc. Tổng quan có một hành động theo trạng thái dự án, chẳng hạn tải tệp đầu tiên, mở đúng bảng cần xử lý hoặc xem tiến độ.
- **Assistant.** Danh sách việc khởi đầu cuộn cùng vùng đọc, phía trên ô gửi cố định. Khi đã có hội thoại, cùng vùng đọc chứa transcript và quyết định chờ duyệt. Biểu mẫu chung trong một lô nguồn nằm trước các thẻ quyết định. Nút xác nhận chỉ điền nháp cho đúng các nguồn liệt kê. Người dùng có thể chọn cột khóa chung khi tên cột văn bản trùng khớp duy nhất ở mọi nguồn. Các thẻ vẫn hiển thị từng khóa và giữ lựa chọn đã có. Lượt duyệt được thực hiện riêng sau khi kiểm từng nguồn.
- **Dữ liệu.** Trên màn rộng, mở bảng nguồn cạnh danh mục đang tìm kiếm. Trên màn hẹp, chỉ mở danh mục hoặc chi tiết. Hướng dẫn dưới các tab theo phiên bản ánh xạ và kết quả của đúng bảng đang mở.
- **Đối soát và báo cáo.** Duy trì hai bề mặt thiết lập và kết quả. Mỗi màn cho biết phạm vi trước khi đọc số. Bảng bằng chứng và ngoại lệ nằm trước biểu đồ phụ trợ. Khi mở chi tiết báo cáo từ Assistant, phần phân bố đã sẵn để cuộn tới. Khu xuất báo cáo đi sau phân bố, với mô tả phạm vi xuất.
- **Cài đặt.** Nhóm theo quyền quản lý, chia sẻ AI, hiển thị và giới hạn tệp. Hành động xóa vĩnh viễn nằm tách khỏi thông tin tài khoản và giữ xác nhận theo quyền.

## Tương tác

Giữ điều khiển web quen thuộc, trạng thái focus rõ, nhãn đầy đủ cho nút chỉ có biểu tượng, và cuộn bảng bên trong vùng dữ liệu. Chi tiết hiển thị cạnh nội dung khi còn đủ chỗ và trở về một cột hoặc drawer khi hẹp. Không dùng chuyển động để biểu đạt trạng thái nghiệp vụ.

Ô nhập và bộ chọn dùng nền trắng, viền trung tính nhẹ `#E5E7EB` và bo góc theo kích thước. Composer giữ một viền quanh khung trắng, với vùng nhập bên trong trong suốt. Khi dùng bàn phím, điều khiển có một nét nhấn ở cạnh dưới. Ô đánh dấu và nút chọn tròn dùng nét bao mảnh để giữ rõ dấu chọn. Các dấu hiệu này giữ nguyên kích thước điều khiển và phân biệt với màu của mục đang chọn hoặc cảnh báo.

Danh sách chọn mở dưới điều khiển, cách 4 px, với nền trắng, viền mảnh và vùng cuộn riêng. Khi thiếu chỗ, vùng nội dung cuộn vừa đủ để đặt danh sách dưới điều khiển. Màn hình quá thấp có thể dùng bảng chọn gọn sát đáy. Danh sách ngắn giữ cơ chế biểu mẫu và bàn phím của trình duyệt. Danh sách Trường đích và danh sách dài của workspace hoặc nguồn có ô tìm kiếm. Bộ chọn dự án giữ tìm kiếm và phân trang phía máy chủ.

Trong Xác nhận cột, danh sách Trường đích dùng cấu trúc đang xem. Mỗi lựa chọn cho biết kiểu dữ liệu. Trường đã gán có lý do vô hiệu hóa. Người dùng có thể giữ nguyên cột nguồn hoặc mở mục thêm trường tùy chỉnh. Hộp chọn hỗ trợ phím mũi tên, Enter và Escape.

Menu cạnh Phiên bản ánh xạ mở lịch sử và kiểm quyền xóa theo phiên bản. Chủ workspace có thể xóa phiên bản không có tham chiếu hoặc ẩn phiên bản khỏi danh sách thường dùng. Bản đã ẩn vẫn mở được để đọc lịch sử và các kết quả đã công bố giữ liên kết gốc.

Danh sách Xác nhận cột dùng chung lưới cho tiêu đề và các hàng. Cột nguồn, trường đích và trạng thái giữ vị trí khi một hàng thiếu trạng thái hoặc mở trình chỉnh sửa. Khi vùng nội dung hẹp, tên nguồn ở hàng trên, trường đích và trạng thái ở hàng dưới. Danh mục nguồn chừa vị trí cho trạng thái và nút quản lý. Trong bảng kết quả và bằng chứng, tiêu đề và số tiền căn cùng phía, dùng cùng định dạng số.

Đề xuất lại hiển thị tiến độ đến khi công việc kết thúc. Bản đề xuất mới tự mở khi biểu mẫu chưa chỉnh sửa. Nếu đã có thay đổi, Studio giữ bản nháp theo phiên bản và cho người dùng chọn mở bản mới. Thông báo thành công tạm thời tự ẩn sau 5 giây. Lỗi tác vụ và yêu cầu xác nhận nằm tại chỗ để người dùng xử lý.
