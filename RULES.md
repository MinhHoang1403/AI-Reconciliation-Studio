# Quy tắc làm việc — AI Reconciliation Studio

Áp dụng cho mọi nhiệm vụ trong dự án. Đọc lại trước khi bắt đầu mỗi việc.

## 1. Viết code

**R1. Code sạch, dễ đọc, dễ quản lý.**
- Đặt tên file, thư mục, module, hàm, biến theo đúng chức năng; cấu trúc gọn gàng.
- Viết chú thích bằng tiếng Việt sao cho đọc tới dòng code nào cũng hiểu nó làm gì và vì sao. Ưu tiên giải thích logic khó, điều kiện nghiệp vụ, công thức; không lặp lại điều tên hàm đã nói rõ.

**R2. Không dùng nhãn lập kế hoạch trong sản phẩm.**
- Các nhãn như `v1`, `v2`, `s1`, `s2`, `e3`, `freeze`, `frozen`, `snapshot`… chỉ dùng khi lập kế hoạch và trao đổi.
- Không đưa các nhãn này vào tên code, file, thư mục, project, image hay nhánh Git.

## 2. Căn cứ kỹ thuật

**R3. Mọi lựa chọn kỹ thuật phải có nguồn kiểm chứng.**
- Phương pháp, công thức tính, thuật toán, kiến trúc và công nghệ phải dựa trên nguồn rõ ràng: tài liệu gốc/chính thức, bài báo khoa học, công trình nghiên cứu, dự án uy tín.
- Ghi lại nguồn tham khảo cho các quyết định quan trọng.
- Không tự nghĩ ra phương pháp hay bịa số liệu, nguồn, kết quả đo.

## 3. Phạm vi và độ phức tạp

**R4. Làm đúng nhiệm vụ, bám kế hoạch.**
- Làm chính xác, hiệu quả đúng việc được giao; không suy diễn quá mức, không lan man sang việc ngoài phạm vi.
- Gặp điểm chưa rõ hoặc mâu thuẫn thì hỏi Owner trước khi làm phần phụ thuộc.

**R5. Kiểm soát over-engineering (làm phức tạp quá mức cần thiết).**
- Chỉ thêm tính năng, thư viện, lớp trừu tượng, hạ tầng khi hợp lý, thật sự cần và có kiểm chứng.
- Chọn giải pháp đơn giản nhất đáp ứng yêu cầu.

**R6. Triển khai chắc chắn, hiệu quả, tối ưu.**
- Ưu tiên tính đúng của dữ liệu và kết quả; sau đó tới hiệu năng và tài nguyên.
- Có kiểm thử chứng minh trước khi báo hoàn thành.

## 4. Sửa lỗi

**R7. Sửa tận gốc.**
- Tái hiện lỗi, điều tra rõ nguyên nhân, sửa đúng chỗ gây ra lỗi — không thấy lỗi ở đâu vá ở đó.
- Thêm kiểm thử bắt được lỗi đó để không tái diễn.

## 5. Môi trường, Docker

**R8. Một môi trường duy nhất, không phân tán.**
- Không tạo nhiều môi trường/bộ container test riêng. Làm và kiểm thử trên bộ container chính của dự án; thay đổi bằng cách cập nhật source rồi build lại image.

**R9. Quản lý container và image gọn, tối ưu.**
- Không sinh thêm container hay image thừa.
- Khi bản mới đã chạy ổn định, dọn image cũ không còn được tham chiếu để không chiếm tài nguyên.
- Chỉ dọn tài nguyên của dự án này; không đụng tới dự án khác dùng chung Docker.

## 6. Git và GitHub

**R10. Thao tác Git cẩn thận, gọn gàng.**
- Việc nhỏ: làm thẳng trên `main`.
- Việc lớn hoặc khó: tạo nhánh riêng, làm xong kiểm kỹ rồi merge vào `main` sạch sẽ và xóa nhánh.
- Mỗi lần làm xong: commit với nội dung rõ ràng, push lên GitHub và xác nhận GitHub đã nhận đúng commit.

## 7. Provider AI và tính năng

**R11. Luôn bật sẵn sàng để test bất kỳ lúc nào.**
- Các provider AI/LLM/Parser… và các tính năng đã làm phải luôn ở trạng thái bật, sẵn sàng để Owner kiểm thử.
- Không tự tắt, ẩn hay thay bằng giả lập để né lỗi; có lỗi thì báo đúng lỗi.

## 8. Giải thích và báo cáo

**R12. Giải thích dễ hiểu bằng tiếng Việt.**
- Việt hóa hoặc chú thích từ chuyên ngành; giải nghĩa từng chức năng để Owner nắm rõ hệ thống.

**R13. Báo cáo chi tiết sau mỗi lần làm.**
- Đã triển khai được gì, đã thay đổi file/phần nào.
- Chức năng nào chạy thành công (kèm kết quả kiểm thử), chức năng nào còn lỗi hoặc chưa làm.
- Commit và trạng thái push lên GitHub.
