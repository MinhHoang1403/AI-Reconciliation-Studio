# data-docs — data model, data catalog, schema JSON và nhật ký AI

Thư mục để người lập trình **xem, đánh giá và lấy bằng chứng** về cấu trúc dữ liệu và mọi thứ hệ
thống gửi cho Gemini, ngoài PostgreSQL. Hệ thống **không đọc lại** các tệp ở đây: muốn đổi thì
sửa code rồi sinh lại.

## Phần tĩnh (commit vào Git, sinh từ code)

Sinh lại sau khi sửa mô hình, cột chuẩn, khuôn JSON hay API:

```powershell
uv run --locked python tools/export_data_docs.py
```

`tests/test_data_docs.py` báo lỗi nếu các tệp này lệch với code.

| Tệp | Nội dung | Sinh từ |
| --- | --- | --- |
| `model/postgres-schema.json` | Data model lưu trữ: mọi bảng PostgreSQL, cột, kiểu, khóa chính, khóa ngoại (kèm `ON DELETE`), chỉ mục, mô tả bảng | `backend/studio/models.py` |
| `model/er-diagram.md` | Sơ đồ quan hệ giữa các bảng (Mermaid; mở bằng VS Code có tiện ích Mermaid hoặc dán vào mermaid.live) | `models.py` |
| `catalog/canonical-fields.json` | 17 cột chuẩn: mã, tên, kiểu, ý nghĩa, các tên cột hay gặp, bắt buộc ở loại bảng nào | `sales_fields.py`, `cleaning.py` |
| `catalog/table-kinds.json` | Loại bảng (đơn sàn, đơn cửa hàng, cổng thanh toán, sao kê), nhóm cột bắt buộc, cột mã | `sales_fields.py`, `cleaning.py` |
| `catalog/result-kinds.json` | 11 loại kết quả đối soát và ý nghĩa | `reconciliation.py`, `recon_api.py` |
| `schemas/ai/*.schema.json` | Khuôn JSON (structured output) bắt Gemini trả lời: ánh xạ cột, gợi ý sửa ô, giải thích đối soát, nhận xét báo cáo | `mapping_service.py`, `cleaning_ai.py`, `recon_ai.py`, `report_ai.py` |
| `schemas/ai/assistant-tools.json` | 25 công cụ của AI Assistant: tên, mô tả, JSON Schema tham số (đúng như khai báo gửi Gemini) | `assistant_tools.py` |
| `schemas/api/openapi.json` | Toàn bộ API của backend (OpenAPI 3) | FastAPI |

## Phần chạy — `runtime/` (Git bỏ qua)

Backend tự ghi khi chạy trong container (thư mục `/data/data-docs` gắn ra đây). Git bỏ qua vì
có mẫu dữ liệu (đã che) và thông tin tệp của người dùng; không bao giờ có khóa API.

| Đường dẫn | Ghi khi nào | Nội dung |
| --- | --- | --- |
| `runtime/ai-calls/<ngày>/<giờ>_<mục đích>_<mã>.json` (giờ Việt Nam) | Mỗi lần gọi Gemini (thành công hay lỗi) | `request`: đúng chỉ dẫn hệ thống, dữ liệu đầu vào đã che, khuôn JSON (`response_schema`) hoặc khai báo công cụ (`tools`) và hội thoại; `response`: câu trả lời; token, thời gian, mã lỗi; `ai_call_id` khớp với bảng `ai_calls` |
| `runtime/catalog/datasets/<mã bộ dữ liệu>.json` | Sau mỗi lần dữ liệu của bộ đó đổi (đọc, ánh xạ, làm sạch, sửa ô, đối soát); xóa bộ dữ liệu thì xóa tệp | Catalog động: tệp gốc (SHA-256, đường dẫn), từng bảng, hồ sơ cột, ánh xạ (cột chuẩn, nguồn, độ tin cậy, lý do), các phiên bản sạch, các lần đối soát dùng bảng |

Mục đích (`purpose`) của các lần gọi Gemini: `goi-y-anh-xa-cot` (ánh xạ), `goi-y-sua-o` (sửa ô),
`giai-thich-cau-hinh-doi-soat`, `giai-thich-ngoai-le-doi-soat`, `assistant`, `nhan-xet-bao-cao`.
Cùng lần gọi còn có trace trên Langfuse (<http://127.0.0.1:3000>).

Xóa sạch dữ liệu app (`docker compose down -v`) **không** xóa `runtime/`; muốn dọn thì xóa tay
thư mục này.
