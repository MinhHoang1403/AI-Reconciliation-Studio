# Nhật ký quyết định

Mỗi dòng là một quyết định đã chốt. Đổi quyết định thì thêm dòng mới, không sửa dòng cũ.

| Ngày | Quyết định | Lý do |
| --- | --- | --- |
| 2026-11-20 | Làm lại dự án từ đầu, dạng demo: chỉ cần chức năng chính chạy đúng | Yêu cầu của Owner |
| 2026-11-20 | AI gợi ý, code deterministic quyết định mọi con số và cặp ghép | Kết quả tiền phải tái lập và kiểm chứng được; theo cách làm của Oracle Cash Management |
| 2026-11-20 | Quy trình xử lý cố định trong code, Assistant chỉ chọn bước và giải thích (workflow trước agent) | Anthropic, *Building effective agents*; giảm rủi ro OWASP LLM06 |
| 2026-11-20 | 3 container: frontend, backend, postgres; tác vụ nền chạy trong backend, chưa tách Worker | Demo ~100.000 dòng; giữ đơn giản theo R5 |
| 2026-11-20 | Backend Python 3.12 + FastAPI + Polars; bảng dữ liệu lưu Parquet | Polars đọc CSV/XLSX (engine calamine) và ghi Parquet trong một thư viện |
| 2026-11-20 | LLM: Gemini `gemini-3.5-flash-lite` qua SDK `google-genai` | Model stable, có function calling và structured output, chi phí thấp |
| 2026-11-20 | Chỉ gửi cho Gemini câu chat, tên cột, thống kê và tối đa 5 giá trị mẫu | Giảm lộ dữ liệu; nghiên cứu cho thấy thừa ngữ cảnh làm ánh xạ kém đi |
| 2026-11-20 | Dùng lại bộ Langfuse tự host đã có trên máy (bản 4.70.1) để theo dõi Assistant | Trace không rời máy; không phải dựng thêm hạ tầng |
| 2026-11-20 | Đối soát luôn hai bộ một lần; ba bên của miền bán hàng chạy thành chuỗi | Tái dùng một engine; đơn giản hơn đối soát ba bên cùng lúc |
| 2026-11-20 | Demo không làm: xuất PDF, khớp N:N, Docs/PDF đầu vào, nhiều người dùng | Giữ phạm vi demo; engine viết chung để thêm sau |
| 2026-11-20 | Giao diện theo thế giới hình ảnh "Tờ tiền polymer" (xem `DESIGN.md`); trang đầu là Tổng quan; chỉ tiếng Việt; máy tính và điện thoại đều phải dùng tốt | Owner chọn qua vòng chọn hướng của skill impeccable; trả lời phỏng vấn sản phẩm (`PRODUCT.md`) |
| 2026-11-20 | Màu chính đổi từ xanh lục lam (tờ 500.000đ) sang xanh dương sáng (tờ 20.000đ, `#1f5fae`); nền ngả xanh dương nhạt | Owner muốn sáng hơn và thích xanh dương; mọi cặp chữ/nền vẫn đạt tương phản ≥ 4,5:1 |
| 2026-11-20 | Thanh điều hướng đổi sang nền xanh dương nhạt `#e4eefb` chữ đậm; nút chính xanh dương sáng hơn `#2a6fc9`; thêm nút thu gọn thanh bên (nhớ trạng thái trong trình duyệt, không áp dụng trên điện thoại) | Owner muốn nhạt và sáng hơn, cần thu phóng thanh bên; tương phản vẫn ≥ 4,5:1 |
| 2026-11-20 | Font Be Vietnam Pro tự host qua @fontsource; biểu tượng lucide-react | Đủ dấu tiếng Việt, không tải tài nguyên từ máy chủ ngoài |
| 2026-11-20 | Điều hướng trang tự viết bằng History API, chưa dùng thư viện router | 5 trang cố định; thêm thư viện khi có nhu cầu thật (R5) |
| 2026-11-20 | E2E Playwright chạy trên container chính, hai khung máy tính 1440×900 và điện thoại Pixel 7 | Một môi trường duy nhất (R8); kiểm cả hai thiết bị |
| 2026-11-20 | Miền đầu tiên: bán hàng, bộ cột chuẩn có `fee`, `net_amount`, `debit`, `credit`, `description` | Có đủ ca 1:1, 1:N, lệch tiền, phí cổng, mã trong nội dung chuyển khoản |
