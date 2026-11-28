# config — cấu hình nghiệp vụ (sửa trực tiếp ở đây)

Mọi thứ hay phải chỉnh theo nghiệp vụ nằm trong thư mục này, dạng `.json` và `.md` dễ đọc. Code
Python chỉ **đọc** các tệp này; không cần mở code để thêm tên cột, đổi ngưỡng hay sửa chỉ dẫn AI.

## Cần sửa gì → mở tệp nào

| Muốn… | Tệp | Khóa |
| --- | --- | --- |
| Hệ thống nhận đúng một tên cột mới (ví dụ "Số HĐ" là mã đơn) | `domains/sales/fields.json` | thêm vào `aliases` của cột chuẩn, viết **không dấu, chữ thường**: `"so hd"` |
| Đổi tên hiển thị / ý nghĩa của cột chuẩn (ý nghĩa được gửi cho Gemini) | `domains/sales/fields.json` | `label`, `meaning` |
| Đổi cột bắt buộc, cột khóa, cách nhận ra loại bảng | `domains/sales/table-kinds.json` | `required`, `key_field`, `detect` |
| Thêm từ viết tắt trong tên cột (`sdt` → "so dien thoai") | `domains/sales/vocabulary.json` | `column_abbreviations` |
| Thêm từ chỉ đơn hủy / hoàn tiền | `domains/sales/vocabulary.json` | `cancelled_status_words` |
| Thêm danh xưng bỏ đi khi so tên ("anh", "chú"…) | `domains/sales/vocabulary.json` | `honorifics` |
| Thêm từ nghiệp vụ bỏ đi khi lấy tên người chuyển từ nội dung chuyển khoản | `domains/sales/vocabulary.json` | `transfer_noise_words` |
| Thêm chữ viết tắt số tiền ("tr", "k") hay đơn vị ("vnđ") | `domains/sales/vocabulary.json` | `money_units`, `currency_words` |
| Ngưỡng tự áp dụng ánh xạ, trọng số tên/giá trị, số giá trị mẫu gửi Gemini | `rules/mapping.json` | xem bảng dưới |
| Bật, tắt, đổi thứ tự các vòng khớp đối soát | `rules/reconciliation.json` | `rounds` |
| Ngưỡng, trọng số, khung ngày, sai số tiền, khung chờ tiền về | `rules/reconciliation.json` | `score_match`, `group_match`, `settlement`… |
| Sửa chỉ dẫn (prompt) gửi Gemini | `prompts/<tính năng>.md` | cả tệp |
| Sửa khuôn JSON Gemini phải trả lời | `schemas/<tính năng>-response.json` | cả tệp |

## Áp dụng thay đổi

Thư mục `config/` được gắn thẳng vào container backend (chỉ đọc). Sửa xong:

```powershell
docker compose restart backend
```

Khoảng 10 giây sau là áp dụng, không cần build lại. Backend **kiểm mọi tệp lúc khởi động**: sai
ở đâu (JSON sai cú pháp, thiếu khóa, gõ sai tên khóa, giá trị ngoài khoảng cho phép, cột chuẩn
không có thật…) thì backend không chạy và ghi rõ lỗi. Xem lỗi:

```powershell
docker compose logs backend --tail 30
```

Sau khi sửa, nên chạy lại bài kiểm để chắc kết quả vẫn đúng với các bộ dữ liệu có đáp án:

```powershell
uv run --locked pytest -q
```

Một số bài kiểm đo đúng con số trên bộ mẫu (ví dụ số cặp khớp); đổi ngưỡng có chủ đích làm số
đó đổi thì bài kiểm báo, bạn xem kết quả mới có hợp lý không rồi mới giữ thay đổi.

## Các vòng khớp đối soát (`rules/reconciliation.json` → `rounds`)

Engine chạy theo thứ tự, dòng đã ghép ở bước trước không tham gia bước sau:

1. *(khóa)* Dòng ngoài phạm vi, tiền ra, dòng còn lỗi làm sạch: không tham gia ghép.
2. *(khóa)* Lựa chọn của người dùng: ghép tay, chọn ca mơ hồ, gỡ ghép.
3. **Các vòng trong `rounds`**, đúng thứ tự trong tệp; `"enabled": false` là bỏ qua:

| Vòng | Code | Làm gì |
| --- | --- | --- |
| `key_match` | `backend/studio/matching_rounds/key_match.py` | Cùng mã đơn / mã giao dịch (kể cả mã tách từ nội dung chuyển khoản); một mã nhiều dòng thì dòng thừa là "Trùng" |
| `score_match` | `backend/studio/matching_rounds/score_match.py` | Không có mã chung: cùng số tiền, gần ngày, giống mã/tên; chấm điểm và chọn cặp tốt nhất; ngang điểm thì để người chọn |
| `group_match` | `backend/studio/matching_rounds/group_match.py` | Nhiều dòng cộng lại đúng bằng một dòng bên kia (khách trả gộp, cổng chuyển theo đợt) |

4. *(khóa)* Xếp loại phần còn lại: đơn đã hủy, chờ tiền về, chỉ có ở một bên.

Bước khóa không tắt được vì bước kiểm chứng đòi mỗi dòng nằm trong đúng một kết quả. Tắt một
vòng thì các dòng lẽ ra được vòng đó ghép sẽ thành "chỉ có ở một bên" (kết quả vẫn qua kiểm
chứng). Muốn **thêm vòng mới**: xem hướng dẫn đầu tệp `backend/studio/matching_rounds/__init__.py`.

## Ý nghĩa từng khóa

### `rules/mapping.json` (ánh xạ cột)

| Khóa | Ý nghĩa |
| --- | --- |
| `name_weight`, `value_weight` | Trọng số điểm theo tên cột và theo giá trị (cộng lại bằng 1) |
| `min_name_score`, `weak_name_cap` | Tên cột quá khác mọi tên hay gặp (dưới `min_name_score`) thì điểm bị chặn ở `weak_name_cap` |
| `type_compatibility` | Mức hợp giữa dạng dữ liệu quan sát được và kiểu cột chuẩn (0–1) |
| `auto_apply_rule_score`, `auto_apply_rule_margin` | Không có AI: tự áp dụng khi điểm ≥ mức này và bỏ xa ứng viên thứ hai |
| `auto_apply_combined_score` | Có AI: quy tắc và AI cùng chọn, điểm gộp ≥ mức này thì tự áp dụng |
| `min_suggest_score` | Dưới mức này thì không gợi ý cột nào |
| `rule_weight_with_ai` | Trọng số điểm quy tắc khi gộp với độ tin cậy của Gemini |
| `ai_sample_values` | Số giá trị mẫu tối đa mỗi cột gửi Gemini (đã che dữ liệu cá nhân) |

### `rules/reconciliation.json` (đối soát)

| Khóa | Ý nghĩa |
| --- | --- |
| `key_selection.weights` | Cách chọn cột mã: tỷ lệ khớp thử, độ phủ, độ duy nhất |
| `key_selection.min_match_rate` | Cột mã phải khớp ít nhất tỷ lệ này mới được dùng |
| `key_selection.extract_codes_below_rate` | Không có cột mã chung đạt tỷ lệ này thì thử tách mã từ nội dung chuyển khoản |
| `key_selection.group_when_unique_below` | Cột mã bên trái trùng nhiều (độ duy nhất dưới mức này, ví dụ mã đợt) thì ghép nhóm theo tổng tiền |
| `score_match.weights` | Trọng số điểm: gần ngày, giống mã, giống tên |
| `score_match.min_score` | Điểm tối thiểu để tự ghép |
| `score_match.date_window_days` | Hai dòng cách nhau quá số ngày này thì không là ứng viên |
| `score_match.amount_tolerance` | Sai số tiền cho ghép 1:1 (đồng); 0 là khớp tuyệt đối |
| `group_match.max_rows`, `max_candidates` | Số dòng tối đa một nhóm, số ứng viên xét mỗi dòng |
| `code_extraction.min_precision`, `min_hits` | Mẫu mã tự học từ nội dung phải đúng với tỷ lệ này và đủ số dòng |
| `settlement.business_days` | Khung chờ tiền về (ngày làm việc) |
| `settlement.min_late_share` | Chỉ áp khung chờ khi đủ tỷ lệ cặp có tiền về sau ngày đơn |
| `scope.*` | Tự để ngoài phạm vi các giá trị (ví dụ "Tiền mặt") gần như không khớp với bên kia |
| `chain.*` | Điều kiện hai bảng được nối trong chuỗi đối soát; số ngày cho phép bảng bắt đầu trước kỳ sao kê |

### `prompts/` và `schemas/` (Gemini)

| Tính năng | Chỉ dẫn | Khuôn JSON trả lời |
| --- | --- | --- |
| Gợi ý ánh xạ cột | `prompts/mapping.md` | `schemas/mapping-response.json` |
| Gợi ý giá trị cho ô không đọc được | `prompts/cleaning-suggestion.md` | `schemas/cleaning-suggestion-response.json` |
| Nút "Giải thích" ở trang Đối soát | `prompts/recon-explain.md` | `schemas/recon-explain-response.json` |
| Nhận xét báo cáo | `prompts/report-comment.md`, `prompts/report-kind-meanings.json` | `schemas/report-comment-response.json` |
| AI Assistant | `prompts/assistant.md` | (công cụ khai báo trong `backend/studio/assistant_tools.py`) |

Phần `<!-- ... -->` ở đầu mỗi tệp `.md` là chú thích, không gửi cho Gemini. Trong khuôn JSON, chỗ
ghi `"{table_kinds}"`, `"{field_keys_or_none}"` được code thay bằng danh sách loại bảng và mã cột
chuẩn lấy từ `domains/sales/`, nên thêm cột chuẩn không phải sửa khuôn.

## Lưu ý an toàn

- Không đặt khóa API, mật khẩu hay dữ liệu khách hàng vào thư mục này (thư mục được commit vào Git).
- Mọi kết quả đối soát vẫn qua bước kiểm chứng độc lập; đổi ngưỡng sai có thể làm ghép nhầm hoặc bỏ
  sót, nên chạy bài kiểm và xem lại kết quả trên bộ dữ liệu thử (`du-lieu-thu/`) sau khi đổi.
