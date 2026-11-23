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
| 2026-11-20 | Bộ dữ liệu mẫu mô phỏng 4 loại nguồn: sàn TMĐT, phần mềm bán hàng, cổng thanh toán, sao kê ngân hàng; dữ liệu tổng hợp, tên tệp và tên cột chung chung, không mang thương hiệu thật | Demo sát thực tế; không giả mạo tệp của doanh nghiệp thật |
| 2026-11-20 | Tệp Excel nhiều sheet: đọc được nhiều sheet, mỗi sheet thành một bảng riêng trong cùng bộ dữ liệu | Owner chọn; nhiều hệ thống xuất mỗi kỳ hoặc mỗi tài khoản một sheet |
| 2026-11-20 | Cho xóa bộ dữ liệu sau khi xác nhận (xóa cả tệp gốc và bảng đã đọc); không bao giờ sửa tệp gốc | Dọn tệp tải nhầm; R15 cấm sửa, không cấm xóa theo ý người dùng |
| 2026-11-20 | Giới hạn mỗi tệp tải lên 50 MB; chỉ hỗ trợ bảng mã UTF-8 (có hoặc không BOM), bảng mã khác báo lỗi rõ ràng | Đủ cho ≥ 100.000 dòng, nhẹ cho máy demo |
| 2026-11-20 | Không bắt người dùng chọn loại dữ liệu khi tải lên; hệ thống tự đoán ở bước ánh xạ | Giảm thao tác |
| 2026-11-20 | Đọc tệp: Polars cho CSV (tự đoán dấu phân cách bằng `csv.Sniffer`), fastexcel (calamine) cho XLSX, mọi ô dạng chữ; lưu bảng Parquet kèm cột `__row_ref` (số dòng gốc tính từ 1) | Giữ số 0 đầu mã; mọi kết quả về sau truy ngược được dòng gốc |
| 2026-11-20 | Dòng tiêu đề tự đoán bằng quy tắc kinh nghiệm (dòng đầu tiên có ≥ một nửa số cột có giá trị, ≥ 80% là chữ, ngay sau có dữ liệu); người dùng chỉnh được | Bỏ qua dòng tên báo cáo phía trên bảng; không có quy tắc chuẩn chung nên cho sửa tay |
| 2026-11-20 | Sheet chỉ được coi là bảng khi có ≥ 2 cột và ≥ 1 dòng dữ liệu; sheet ẩn không đọc | Bỏ sheet ghi chú và bảng tra cứu nội bộ của hệ thống xuất tệp |
| 2026-11-20 | Đọc tệp chạy nền bằng FastAPI BackgroundTasks, trạng thái lưu trên bảng `datasets`/`dataset_tables`; khởi động lại thì việc dở đánh dấu lỗi để đọc lại | Đủ cho demo (đọc 100.000 dòng dưới 1 giây khi đo), chưa cần hàng đợi riêng (R5) |
| 2026-11-20 | Alembic cấu hình bằng code (`studio/migrate.py`), không dùng `alembic.ini`; test chạy migration trên SQLite tạm và so với mô hình | `alembic.ini` có tiếng Việt bị đọc sai bảng mã trên Windows |
| 2026-11-20 | E2E trên container chính chỉ xóa bộ dữ liệu do chính nó tạo, bỏ qua bài nếu tệp mẫu đã có sẵn | Không làm mất dữ liệu người dùng trong môi trường duy nhất (R8) |
| 2026-11-20 | Mẫu gửi Gemini được che bớt bằng code trước khi gửi (điện thoại giữ 2 số đầu/cuối, tên giữ họ, nội dung chuyển khoản che từ không phải mã hay từ nghiệp vụ, email, số tài khoản); mã, ngày, tiền, danh mục gửi nguyên | Owner chọn; giữ hình dạng để AI đoán đúng mà giảm lộ dữ liệu cá nhân |
| 2026-11-20 | Gemini tự gợi ý ánh xạ ngay sau khi đọc mỗi bảng; tệp cùng cấu trúc đã xác nhận thì dùng bộ nhớ, không gọi lại | Owner chọn; ít thao tác nhất |
| 2026-11-20 | Không giới hạn số lần gọi Gemini mỗi ngày; mỗi lần có timeout 45 giây, tối đa 4.096 token ra, thử lại tối đa 2 lần, ghi token vào bảng `ai_calls` | Owner chọn không giới hạn; vẫn giữ giới hạn từng lần gọi theo R11 |
| 2026-11-20 | Langfuse: dùng bộ tự host có sẵn, backend ghi trace thủ công (một generation mỗi lần gọi, gói đã che) qua `host.docker.internal:3000`; không dùng gói instrumentor | Kiểm soát được nội dung gửi lên Langfuse; ít phụ thuộc (R5) |
| 2026-11-20 | Ánh xạ: điểm quy tắc (tên 65%, giá trị 35%) gộp 50/50 với độ tin cậy của Gemini, gán tối ưu bằng `linear_sum_assignment`; tự áp dụng khi quy tắc và AI cùng chọn và điểm gộp ≥ 0,75 (không có AI: điểm ≥ 0,8 và bỏ xa ứng viên thứ hai 0,1); còn lại chờ người dùng xem | Ngưỡng chỉnh trên bộ mẫu và bộ tên cột mới; ưu tiên không tự áp dụng sai |
| 2026-11-20 | Câu trả lời của Gemini bị bắt theo khuôn JSON (chỉ được chọn mã cột chuẩn có thật hoặc NONE) và được kiểm lại; sai khuôn thì dùng kết quả quy tắc | AI không được bịa cột chuẩn hay tên cột |
| 2026-11-20 | Ánh xạ chỉ được ghi nhớ khi người dùng xác nhận (hoặc tự chọn cột) | "Đã xác nhận" phải do người dùng, không do hệ thống tự cho là đúng |
| 2026-11-20 | Thêm bộ "tên cột mới" (`ten-cot-moi.json`) chưa dùng khi soạn quy tắc và `tools/evaluate_mapping.py` | Đo trung thực; bộ mẫu dễ đạt 100% vì quy tắc soạn khi đã thấy tên cột |
| 2026-11-20 | Dòng trùng y hệt chỉ được gợi ý bỏ bản lặp, người dùng đồng ý cho cả nhóm (hoặc giữ tất cả) | Owner chọn; sao kê có thể có giao dịch thật giống hệt |
| 2026-11-20 | Đơn đã hủy/hoàn tiền giữ trong bộ sạch, gắn cờ `is_cancelled` | Owner chọn; Giai đoạn 4 phát hiện được đơn hủy mà vẫn có tiền về |
| 2026-11-20 | Gemini đề xuất giá trị cho ô không đọc được; đề xuất phải đọc được bằng bộ đọc của hệ thống và chỉ áp dụng khi người dùng đồng ý | Owner chọn; AI không tự ghi vào dữ liệu |
| 2026-11-20 | Thứ tự ngày suy từ cả cột; không phân biệt được thì mặc định ngày/tháng, ghi rõ và cho đổi cả cột | Owner chọn; theo thói quen Việt Nam |
| 2026-11-20 | Kiểu dấu phân cách số (Việt 1.250.000 hay Anh 1,250,000) suy từ cả cột; tiền lưu Decimal 2 chữ số lẻ; viết tắt `tr`, `k`, `triệu`, `nghìn` được tự đọc | Không đoán từng ô; không làm tròn kiểu số thực |
| 2026-11-20 | Bộ sạch dựng lại từ đầu (bảng gốc + ánh xạ + sửa ô + quyết định dòng + lựa chọn ngày) mỗi khi có thay đổi; mỗi lần một phiên bản Parquet mới, không ghi đè | Kết quả xác định, truy vết được; tệp gốc không bị sửa (R15) |
| 2026-11-20 | Vấn đề 3 mức: tự sửa (định dạng, khoảng trắng, đầu số 84, dòng trống), gợi ý (dòng trùng), hỏi (thiếu trường bắt buộc theo loại bảng, ô không đọc được, cùng mã khác số tiền) | Theo phân tầng độ tin cậy trong kiến trúc |
| 2026-11-23 | Bổ sung xử lý ngoại lệ tối thiểu (trạng thái tự đổi theo thao tác, ghi chú tùy chọn) và nhật ký kiểm toán `audit_log` vào Giai đoạn 4 | Năng lực cốt lõi của phần mềm đối soát; Owner duyệt với điều kiện không thêm thao tác |
| 2026-11-23 | Bổ sung kỳ đối soát và khoản chuyển kỳ (`PENDING_SETTLEMENT`, khung chờ mặc định T+3 ngày làm việc) vào Giai đoạn 5 | Tránh báo thiếu tiền oan cho đơn cuối kỳ; theo cách xử lý khoản đang chuyển trong kế toán |
| 2026-11-23 | Nguyên tắc giao diện Giai đoạn 4–7: việc cần làm trước, phần đã xong thu gọn, tự động tối đa, một hành động chính mỗi khối | Owner yêu cầu gọn gàng, hiện đại, không thêm thao tác |
| 2026-11-20 | Miền đầu tiên: bán hàng, bộ cột chuẩn có `fee`, `net_amount`, `debit`, `credit`, `description` | Có đủ ca 1:1, 1:N, lệch tiền, phí cổng, mã trong nội dung chuyển khoản |
