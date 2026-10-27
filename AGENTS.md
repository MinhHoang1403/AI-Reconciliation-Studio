# Hướng dẫn Codex — AI Reconciliation Studio

1. **Trước mỗi nhiệm vụ, đọc toàn bộ [Rules.md](Rules.md)** và tuân thủ đầy đủ. Đọc lại khi bắt đầu phiên mới hoặc ngữ cảnh bị đặt lại; không chỉ dựa vào tóm tắt cũ.
2. Đọc [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md), đặc biệt các phần, hợp đồng dữ liệu/nghiệp vụ và điều kiện nghiệm thu liên quan. Kế hoạch xác định sản phẩm/kiến trúc; `Rules.md` là nguồn quy tắc làm việc duy nhất.
3. Kiểm tra hiện trạng thật: repository root, Git status/branch/diff/remote, files, dependencies, dữ liệu và tests; Docker/services khi công việc liên quan môi trường chạy. Bảo toàn thay đổi sẵn có của người dùng.
4. Xác định ngắn gọn mục tiêu, phạm vi files/modules được sửa, contracts ảnh hưởng, phần cần bảo toàn và cách kiểm chứng trước khi thực hiện.
5. Chỉ làm việc được giao. Không tự đổi kế hoạch, kiến trúc, semantic contracts, công thức, công nghệ hoặc bắt đầu giai đoạn kế tiếp. Không tự tạo file/framework/agent/skill hay môi trường trùng lặp.
6. Tuân thủ quy tắc dữ liệu, AI, bảo mật và **một Docker Compose project** trong `Rules.md`; không tự gọi cloud, xóa volumes hoặc tác động dự án cũ.
7. Kiểm chứng trước khi kết luận hoàn thành: tests/checks và regression phù hợp phạm vi; tài liệu phải kiểm tra nội dung, đường dẫn, Markdown và tính nhất quán. Phân biệt live/mock, PASS/chưa kiểm tra/BLOCKED.
8. Áp dụng đầy đủ chính sách Git/GitHub tại mục 11 của `Rules.md`: thay đổi nhỏ có thể trên `main`, việc lớn/rủi ro dùng feature branch trong cùng repo; không tạo worktree/bản sao không cần thiết. Sau mỗi nhóm việc hoàn chỉnh, kiểm tra diff/tests/secrets/nội dung, stage đúng files, commit rồi push lên `origin` chính thức và báo commit hash; xác minh remote trước push, báo blocker nếu thiếu điều kiện. Không commit runtime data, force-push/reset phá hủy.
9. Nếu phát hiện mâu thuẫn tài liệu, báo rõ vị trí và tác động; không tự suy đoán để đổi nghiệp vụ hoặc sửa kế hoạch cho khớp code. Tôn trọng chỉ dẫn hệ thống, bảo mật và quyền hạn cao hơn.
10. Báo cáo kết quả **bằng tiếng Việt**: việc/files đã làm, lý do, kiểm chứng, Docker nếu liên quan, commit/push, giới hạn còn lại và mức sẵn sàng cho nhiệm vụ tiếp theo.
