# Kế hoạch triển khai (bản nháp chờ duyệt)

Làm theo **lát cắt dọc**: mỗi giai đoạn kết thúc bằng một chức năng dùng được trên giao diện thật, có kiểm thử. [Kiến trúc](ARCHITECTURE.md) · [Quy tắc](../RULES.md)

## Trạng thái

| Giai đoạn | Nội dung | Nhánh | Trạng thái |
| --- | --- | --- | --- |
| 0 | Khung dự án: 3 container, CI, giao diện khung | `main` | Chưa bắt đầu |
| 1 | Tải và đọc CSV/XLSX, hồ sơ cột | `phase-1` | Chưa bắt đầu |
| 2 | Ánh xạ cột chuẩn có gợi ý Gemini, nối Langfuse | `phase-2` | Chưa bắt đầu |
| 3 | Chuẩn hóa, xử lý lỗi, bộ dữ liệu sạch | `phase-3` | Chưa bắt đầu |
| 4 | Chọn trường, đối soát 1:1, kiểm chứng | `phase-4` | Chưa bắt đầu |
| 5 | Tách mã từ nội dung, khớp nhóm 1:N/N:1, ca mơ hồ | `phase-5` | Chưa bắt đầu |
| 6 | AI Assistant điều phối toàn bộ luồng | `phase-6` | Chưa bắt đầu |
| 7 | Báo cáo, KPI, biểu đồ, xuất CSV/XLSX, nhận xét AI | `phase-7` | Chưa bắt đầu |

## Bộ dữ liệu mẫu có đáp án

Làm trước giai đoạn 1 và mở rộng dần, nằm trong `tests/fixtures/sales/`. Gồm 3 tệp tổng hợp (không phải dữ liệu thật): **đơn hàng**, **thanh toán**, **sao kê**. Mỗi tệp có tên cột khác nhau và có cài sẵn: lỗi định dạng, dòng trùng, thiếu khóa, lệch tiền, phí cổng thanh toán, một thanh toán cho nhiều đơn, mã đơn nằm trong nội dung chuyển khoản, tên gần giống nhau. Kèm một tệp **đáp án** ghi cặp nào khớp với cặp nào. Có thêm một bản lớn 100.000 dòng để đo hiệu năng.

## Giai đoạn 0 — Khung dự án

- Cấu trúc thư mục `backend/`, `frontend/`, `tests/`; `compose.yaml` 3 container; script khởi động kiểm 3/3 healthy.
- Kiểm tra tự động: `ruff`, `mypy`, `pytest` (backend); `tsc`, `eslint` (frontend); E2E Chromium bằng Playwright.
- Khung giao diện: Assistant, Dữ liệu, Đối soát, Báo cáo. Thiết kế bằng impeccable + ui-ux-pro-max.
- **Xong khi:** `docker compose up` cho 3/3 healthy, mở được giao diện ở `127.0.0.1`, CI xanh.

## Giai đoạn 1 — Đọc dữ liệu

- Tải CSV/XLSX, chọn sheet, phát hiện dòng tiêu đề; lưu tệp gốc + SHA-256; đọc bằng Polars thành Parquet; hồ sơ cột.
- Giao diện: danh sách bộ dữ liệu, xem trước dòng, hồ sơ cột.
- **Xong khi:** đọc đúng 3 tệp mẫu; tệp 100.000 dòng đọc được và đo thời gian thật để ghi vào báo cáo; mỗi dòng truy ngược được về dòng gốc.

## Giai đoạn 2 — Ánh xạ

- Bộ cột chuẩn miền bán hàng: `order_id`, `order_date`, `customer_name`, `customer_phone`, `amount`, `fee`, `net_amount`, `currency`, `payment_id`, `payment_date`, `bank_ref`, `transaction_date`, `debit`, `credit`, `description`.
- Gợi ý ba lớp (tên cột, giá trị, Gemini xếp hạng lại), ngưỡng tự áp dụng, ghi nhớ ánh xạ.
- Kết nối Gemini và Langfuse (dùng bộ Langfuse đã có trên máy).
- Giao diện: bảng ánh xạ theo nguồn, điểm, nút xác nhận cả nhóm.
- **Xong khi:** trên 3 tệp mẫu, ≥ 95% cột được ánh xạ đúng tự động khi có Gemini; khi không có khóa Gemini vẫn gợi ý được (đo và ghi tỷ lệ); tải lại tệp cùng cấu trúc thì tự ánh xạ; mỗi lần gọi Gemini có trace trên Langfuse.

## Giai đoạn 3 — Chuẩn hóa và xử lý lỗi

- Bộ chuyển đổi tiền (định dạng Việt/Anh), ngày (suy thứ tự theo cột), mã, tên, điện thoại.
- Phát hiện issue ba mức, Gemini gợi ý cho ca khó, nhật ký sửa, tạo bộ dữ liệu sạch.
- Giao diện: tóm tắt đã tự sửa, danh sách cần xác nhận, sửa ô tại chỗ.
- **Xong khi:** trên bộ mẫu, mọi lỗi dễ đã cài được tự sửa, mọi ca khó được chỉ ra, không dòng sạch nào bị sửa nhầm.

## Giai đoạn 4 — Đối soát cốt lõi

- Chọn trường đối soát tự động, cấu hình đối soát.
- Vòng khớp khóa 1:1 và khớp theo điểm 1:1 (phân công tối ưu); phân loại `MATCHED`, `AMOUNT_MISMATCH`, `ONLY_IN_A/B`, `DUPLICATE`.
- Kiểm chứng độc lập sau mỗi lần chạy.
- Giao diện: chọn hai bộ, xem cấu hình, chạy, xem kết quả theo loại kèm lý do.
- **Xong khi:** precision và recall ≥ 99% trên bộ mẫu có khóa (so với tệp đáp án); xáo trộn thứ tự dòng vẫn cho cùng kết quả; kiểm chứng bắt được kết quả bị sửa tay.

## Giai đoạn 5 — Ca khó

- Tách mã từ nội dung chuyển khoản bằng regex (Gemini gợi ý mẫu, người dùng xác nhận).
- Khớp nhóm 1:N, N:1 theo tổng tiền, có giới hạn tổ hợp.
- `AMBIGUOUS` kèm ứng viên và lý do; người dùng chọn trên giao diện.
- Chạy chuỗi ba bên: đơn hàng ↔ thanh toán ↔ sao kê.
- **Xong khi:** đúng đáp án trên bộ mẫu ghép nhóm và ca tên trùng (ví dụ "anh Hoàng", "chú Hoàng" với "Minh Hoàng"); không ca mơ hồ nào bị tự chọn.

## Giai đoạn 6 — AI Assistant

- Vòng gọi công cụ Gemini; các công cụ đọc, xử lý, thay đổi; thẻ xác nhận trong khung chat.
- Lưu hội thoại, tiếp tục được sau khi tải lại trang; mỗi câu chat là một trace trên Langfuse.
- **Xong khi:** bộ 30 câu lệnh mẫu tiếng Việt (gồm câu mơ hồ) gọi đúng công cụ và tham số ≥ 90%, do Owner chạy thật và đánh giá qua Langfuse; câu lệnh cài trong dữ liệu nguồn không làm thay đổi hành vi.

## Giai đoạn 7 — Báo cáo

- KPI, biểu đồ theo loại/ngày/nguồn, xuất CSV và XLSX, nhận xét do Gemini viết từ số liệu của engine.
- **Xong khi:** mọi con số trong báo cáo khớp với kết quả engine trên bộ mẫu; hai định dạng xuất có cùng nội dung.

## Cách làm mỗi giai đoạn

1. Bổ sung bộ dữ liệu mẫu và đáp án cho phần sắp làm.
2. Viết backend + test, rồi giao diện (impeccable + ui-ux-pro-max).
3. Chạy toàn bộ kiểm tra, build lại image, kiểm 3/3 healthy và E2E trên container chính; dọn image cũ ([R8, R9](../RULES.md)).
4. Cập nhật bảng trạng thái và [Quyết định](DECISIONS.md).
5. Merge nhánh vào `main`, push, xác nhận GitHub, xóa nhánh ([R10](../RULES.md)).

## Skill và công cụ dùng trong dự án

| Skill/công cụ | Dùng để |
| --- | --- |
| impeccable, ui-ux-pro-max | Thiết kế và hoàn thiện giao diện |
| dataviz | Biểu đồ và KPI ở giai đoạn 7 |
| xlsx | Tạo và kiểm tra các tệp mẫu Excel |
| code-review, security-review | Rà lỗi và bảo mật trước khi merge mỗi giai đoạn |
| run | Chạy app thật để xác nhận chức năng |
| Graphify | Tra cứu cấu trúc code (định nghĩa, nơi gọi, ảnh hưởng khi sửa) để Claude không phải đọc lại nhiều file |
| Langfuse | Đánh giá Assistant: xem lại từng câu chat, lỗi, độ trễ, token |
