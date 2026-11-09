# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Người dùng và công việc

Kế toán, nhân viên vận hành và người rà soát nghiệp vụ dùng Studio local để đối chiếu dữ liệu từ nhiều tệp CSV/XLSX. Họ cần biết dữ liệu đã được đọc ra sao, những quyết định nào đang chờ duyệt và giao dịch nào cần truy về dòng gốc.

## Cơ chế sản phẩm

AI Assistant điều phối công việc bằng tiếng Việt. Backend kiểm tra quyền và đề xuất, tính đối soát bằng quy tắc đã duyệt và xác minh kết quả độc lập. Từ kết quả, người dùng mở được bằng chứng và xuất đúng phạm vi. Đường thủ công vẫn sử dụng được khi AI tạm thời không khả dụng.

## Cam kết

- Giữ nguyên dữ liệu gốc, nguồn gốc từng dòng và ngữ nghĩa số tiền. Hiển thị rõ dữ kiện thiếu, cảnh báo và xác minh một phần.
- Giữ các bước phê duyệt nghiệp vụ và quyền của chủ không gian, người chỉnh sửa và người xem.
- Giao diện tiếng Việt, nền sáng, xanh dương làm màu nhận diện và dùng font hệ thống. Giữ điều hướng bàn phím và hỗ trợ màn hình hẹp theo mục tiêu WCAG 2.2 AA.
- Không gian demo local chạy trên loopback. Kết nối AI, quyền chia sẻ và hạn mức phụ thuộc chính sách hiện hành.

## Bằng chứng và phạm vi

[Kế hoạch dự án](docs/PROJECT_PLAN.md) mô tả hợp đồng nghiệp vụ. [Hướng dẫn kiểm thử](docs/USER_TEST_GUIDE.md) cung cấp hành trình thử với dữ liệu tổng hợp. [Báo cáo triển khai](docs/IMPLEMENTATION_STATUS.md) phân biệt các kết quả local, mock và live theo từng mốc.
