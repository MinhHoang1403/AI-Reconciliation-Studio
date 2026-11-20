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
| 2026-11-20 | Miền đầu tiên: bán hàng, bộ cột chuẩn có `fee`, `net_amount`, `debit`, `credit`, `description` | Có đủ ca 1:1, 1:N, lệch tiền, phí cổng, mã trong nội dung chuyển khoản |
