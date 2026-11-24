# Kế hoạch triển khai

Làm theo **lát cắt dọc**: mỗi giai đoạn kết thúc bằng một chức năng dùng được trên giao diện thật, có kiểm thử. [Kiến trúc](ARCHITECTURE.md) · [Quy tắc](../RULES.md)

## Trạng thái

| Giai đoạn | Nội dung | Nhánh | Trạng thái |
| --- | --- | --- | --- |
| 0 | Khung dự án: 3 container, CI, giao diện khung | `main` | Xong |
| 1 | Tải và đọc CSV/XLSX, hồ sơ cột | `phase-1` | Xong |
| 2 | Ánh xạ cột chuẩn có gợi ý Gemini, nối Langfuse | `phase-2` | Xong |
| 3 | Chuẩn hóa, xử lý lỗi, bộ dữ liệu sạch | `phase-3` | Xong |
| 4 | Chọn trường, đối soát 1:1, kiểm chứng | `phase-4` | Xong |
| 5 | Tách mã từ nội dung, khớp nhóm 1:N/N:1, ca mơ hồ | `phase-5` | Xong |
| 6 | AI Assistant điều phối toàn bộ luồng | `phase-6` | Xong (đo thật 27/30 = 90%); đo lại sau bản sửa tìm theo mã khi khóa Gemini còn hạn mức |
| 7 | Báo cáo, KPI, biểu đồ, xuất CSV/XLSX, nhận xét AI | `phase-7` | Chưa bắt đầu |

## Bộ dữ liệu mẫu có đáp án

Làm trước giai đoạn 1 và mở rộng dần, nằm trong `tests/fixtures/sales/`, sinh bằng script cố định. Gồm các tệp tổng hợp (không phải dữ liệu thật) mô phỏng 4 loại nguồn: **đơn hàng sàn TMĐT** (có phí sàn, tiền thực nhận), **đơn hàng phần mềm bán hàng**, **giao dịch cổng thanh toán** (có phí cổng, một lần chuyển gộp nhiều đơn), **sao kê ngân hàng** (cột Nợ/Có, mã đơn trong nội dung chuyển khoản; một tệp nhiều sheet). Mỗi tệp có tên cột khác nhau và có cài sẵn: lỗi định dạng, dòng trùng, thiếu khóa, lệch tiền, phí cổng thanh toán, một thanh toán cho nhiều đơn, mã đơn nằm trong nội dung chuyển khoản, tên gần giống nhau. Kèm một tệp **đáp án** ghi cặp nào khớp với cặp nào. Có thêm một bản lớn 100.000 dòng để đo hiệu năng.

## Giai đoạn 0 — Khung dự án

- Cấu trúc thư mục `backend/`, `frontend/`, `tests/`; `compose.yaml` 3 container; script khởi động kiểm 3/3 healthy.
- Kiểm tra tự động: `ruff`, `mypy`, `pytest` (backend); `tsc`, `eslint` (frontend); E2E Chromium bằng Playwright.
- Khung giao diện: Assistant, Dữ liệu, Đối soát, Báo cáo. Thiết kế bằng impeccable + ui-ux-pro-max.
- **Xong khi:** `docker compose up` cho 3/3 healthy, mở được giao diện ở `127.0.0.1`, CI xanh.

## Giai đoạn 1 — Đọc dữ liệu

- Tải CSV/XLSX tối đa 50 MB (UTF-8); Excel nhiều sheet thì mỗi sheet một bảng; tự đoán dòng tiêu đề, người dùng chỉnh được; lưu tệp gốc + SHA-256, tải trùng thì nhận ra; đọc bằng Polars thành Parquet, mọi ô dạng chữ, mỗi dòng có `row_ref`; hồ sơ cột; xóa bộ dữ liệu có xác nhận.
- Giao diện: kéo-thả tải tệp, danh sách bộ dữ liệu, xem trước dòng có phân trang, hồ sơ cột.
- **Xong khi:** đọc đúng mọi tệp mẫu (đủ dòng, giữ số 0 đầu mã, đủ sheet, `row_ref` đúng); tệp 100.000 dòng đọc được và đo thời gian thật để ghi vào báo cáo; tải trùng không lưu thêm bản; test backend và E2E (máy tính, điện thoại) đạt.

## Giai đoạn 2 — Ánh xạ

- Bộ cột chuẩn miền bán hàng (17 cột, `backend/studio/sales_fields.py`): `order_id`, `order_date`, `customer_name`, `customer_phone`, `amount`, `fee`, `net_amount`, `payment_method`, `status`, `payment_id`, `payment_batch`, `transaction_date`, `bank_ref`, `debit`, `credit`, `balance`, `description`.
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
- **Xử lý ngoại lệ tối thiểu:** mỗi kết quả không khớp có trạng thái `OPEN` / `EXPLAINED` / `RESOLVED`, lý do do engine sinh ra và ghi chú tùy chọn. Trạng thái tự đổi khi người dùng thao tác (chọn, loại, xác nhận lệch do phí); không bắt điền gì.
- **Nhật ký kiểm toán:** bảng `audit_log` ghi mọi thay đổi có ý nghĩa từ Giai đoạn 2 trở đi (xác nhận/đổi ánh xạ, sửa ô, giữ/loại dòng, đổi cách đọc ngày, xử lý ngoại lệ): ai, lúc nào, đối tượng, giá trị trước và sau. Ghi tự động; xem ở trang "Lịch sử".
- Giao diện: chọn hai bộ, xem cấu hình, chạy, xem kết quả theo loại kèm lý do; trang "Lịch sử" đọc nhật ký kiểm toán.
- **Xong khi:** precision và recall ≥ 99% trên bộ mẫu có khóa (so với tệp đáp án); xáo trộn thứ tự dòng vẫn cho cùng kết quả; kiểm chứng bắt được kết quả bị sửa tay; mọi thao tác thay đổi của người dùng có dòng tương ứng trong nhật ký kiểm toán (có test).

## Giai đoạn 5 — Ca khó

- Tách mã từ nội dung chuyển khoản bằng regex (Gemini gợi ý mẫu, người dùng xác nhận).
- Khớp nhóm 1:N, N:1 theo tổng tiền, có giới hạn tổ hợp.
- `AMBIGUOUS` kèm ứng viên và lý do; người dùng chọn trên giao diện.
- Chạy chuỗi ba bên: đơn hàng ↔ thanh toán ↔ sao kê.
- **Kỳ đối soát và khoản chuyển kỳ:** kỳ tự suy từ khoảng ngày của dữ liệu (người dùng chỉnh được). Dòng chưa khớp nhưng còn trong khung chờ tiền về (mặc định T+3 ngày làm việc, chỉnh được theo nguồn) được xếp loại `PENDING_SETTLEMENT` (chờ tiền về), không báo thiếu. Lần đối soát sau tự đưa các dòng chờ vào khớp lại; quá hạn thì chuyển thành `ONLY_IN_A/B`.
- **Xong khi:** đúng đáp án trên bộ mẫu ghép nhóm và ca tên trùng (ví dụ "anh Hoàng", "chú Hoàng" với "Minh Hoàng"); không ca mơ hồ nào bị tự chọn; đơn cuối kỳ tiền về đầu kỳ sau (có trong bộ mẫu) được xếp "chờ tiền về" rồi tự khớp ở kỳ sau.

## Nguyên tắc giao diện cho Giai đoạn 4–7

Thêm chức năng nhưng không thêm thao tác và không làm rối màn hình:

- **Việc cần làm trước, phần đã xong thu gọn:** màn hình kết quả mở ra là số ca cần quyết định; khớp đúng, chờ tiền về, đã xử lý nằm trong nhóm thu gọn hoặc tab riêng.
- **Tự động hết mức:** trạng thái ngoại lệ tự đổi theo thao tác; nhật ký kiểm toán ghi ngầm; kỳ đối soát tự suy; ghi chú luôn là tùy chọn.
- **Một hành động chính mỗi khối:** mỗi nhóm ngoại lệ có một nút chính (ví dụ "Đồng ý tất cả"), các thao tác phụ nhỏ hơn.
- **Giữ đúng hệ thống "Tờ tiền polymer"** (`DESIGN.md`): màu theo nghĩa, chữ số thẳng cột, con dấu guilloche chỉ cho kiểm chứng. Mỗi màn hình mới qua quy trình skill impeccable (bối cảnh, craft floor, bộ dò lỗi thiết kế, chụp máy tính + điện thoại) trước khi merge.

## Giai đoạn 6 — AI Assistant

- Vòng gọi công cụ Gemini; các công cụ đọc, xử lý, thay đổi; thẻ xác nhận trong khung chat.
- Lưu hội thoại, tiếp tục được sau khi tải lại trang; mỗi câu chat là một trace trên Langfuse.

**Cách làm (Owner chốt 23/11/2026, `DECISIONS.md`):**

1. **Bộ câu lệnh mẫu trước:** `tests/fixtures/assistant/cau-lenh-mau.json`, 30 câu tiếng Việt (rõ ràng, mơ hồ, nhiều bước, câu cài lệnh trong dữ liệu), mỗi câu ghi công cụ và tham số mong đợi.
2. **Công cụ = chính các hàm giao diện đang dùng** (`assistant_tools.py`), mỗi công cụ một khuôn tham số kiểm bằng schema:
   - *Đọc* (tự chạy): danh sách bộ dữ liệu, trạng thái, ánh xạ, vấn đề làm sạch, các kỳ, kết quả đối soát, đường đi của một dòng, nhật ký.
   - *Xử lý* (tự chạy, báo lại đã làm gì): gợi ý lại ánh xạ, đối soát cả chuỗi, đối soát hai bảng, kiểm chứng lại.
   - *Thay đổi* (thẻ xác nhận, người dùng bấm mới chạy): xác nhận/đổi ánh xạ, sửa ô, giữ/loại dòng, đồng ý bỏ dòng trùng, đổi cách đọc ngày, chọn ca mơ hồ, ghép tay, gỡ ghép, đánh dấu đã xử lý/mở lại, ghi chú.
3. **Vòng gọi công cụ** (`assistant.py`): Gemini trả tên công cụ + tham số, backend chạy (function calling, không để SDK tự gọi). Tối đa 8 bước mỗi lượt; việc chạy nền (đọc tệp, làm sạch, đối soát) thì chờ trong lượt, mỗi bước ghi vào tin nhắn để giao diện hiện "đang làm gì". Không truyền chữ từng phần (streaming).
4. **Bảo vệ** (OWASP LLM01, LLM06): kết quả công cụ đưa cho Gemini dưới dạng dữ liệu JSON, chỉ dẫn hệ thống nói rõ dữ liệu không phải lệnh; Gemini chỉ thấy tóm tắt, số đếm và vài dòng đã che, không thấy cả bảng; thao tác thay đổi không bao giờ tự chạy.
5. **Lưu hội thoại**: bảng `chat_threads`, `chat_messages` (tin nhắn, lần gọi công cụ, thẻ xác nhận và trạng thái). Mỗi lượt là một trace Langfuse: một generation mỗi lần gọi Gemini, một span mỗi công cụ.
6. **Giao diện trang Assistant** (impeccable + ui-ux-pro-max): danh sách hội thoại, khung tin nhắn, các bước đang làm, thẻ xác nhận, ô nhập có đính kèm tệp (dùng lại API tải tệp), nút dẫn sang đúng trang Dữ liệu / Đối soát.
7. **Kiểm thử**: test với Gemini giả lập (đúng công cụ, đúng tham số, thẻ xác nhận không tự chạy, lệnh cài trong dữ liệu bị bỏ qua) và E2E; đo với Gemini thật bằng `tools/evaluate_assistant.py` (tốn phí, Owner chạy).

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
| Graphify (bản mã nguồn mở, chạy local) | Graph code: định nghĩa, nơi gọi, ảnh hưởng khi sửa; xem trực quan ở 127.0.0.1:3114 |
| agentmemory (Docker local) | Bộ nhớ các phiên làm việc của Claude: quyết định, lỗi đã sửa; xem ở 127.0.0.1:3113 |
| Langfuse | Đánh giá Assistant: xem lại từng câu chat, lỗi, độ trễ, token |
