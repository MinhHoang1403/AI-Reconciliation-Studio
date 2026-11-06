# Trạng thái triển khai và nghiệm thu

## Consolidation và baseline tích hợp — 06/11/2026

Đang thực hiện theo yêu cầu hợp nhất mới: cho phép đưa Foundation hợp lệ vào main khi hồi quy local đạt, dù Planner/Query AI LIVE chưa hoàn tất. Quyền này thay lệnh giữ main ở các báo cáo lịch sử; không biến các cổng AI chưa đạt thành PASS. Công đoạn tự động hóa chỉ bắt đầu sau baseline tích hợp, Docker và rollback được kiểm chứng.

### Kiểm kê, bảo toàn và cleanup

Git đầu lượt: main `a4f70b2`, product-polish `2eecb06`, Foundation `4124d17`; cả ba bằng origin sau fetch. Main là tổ tiên của product-polish, product-polish là tổ tiên của Foundation. Không có commit chưa push hoặc sửa tracked file của người dùng. Kế hoạch `AUTOMATION_PRODUCT_PLAN.md` là tệp chưa tracked được cung cấp mới; bản gốc và SHA-256 được giữ trong runtime, chưa triển khai nội dung ở công đoạn này.

Rà soát cây source, imports, nội dung trùng hoàn toàn, thân hàm trùng, migrations, call sites, dependencies/lockfiles và cấu hình build. Chưa có bằng chứng đủ để xóa source, test hoặc dependency: số xóa tương ứng **0/0/0**. API Assistant cũ vẫn có tuyến tương thích; parser tài liệu, công cụ rollback, oracle và tests bảo mật vẫn cần giữ. Không có cache/runtime được tracked. Tài liệu kiến trúc, contracts, kế hoạch Agent và báo cáo lịch sử tiếp tục có giá trị truy vết; không xóa báo cáo thất bại. README trỏ tới quy trình hiện hành trong TESTING_GUIDE, các liên kết backup lỗi thời đã sửa. Không thay dependency hoặc hợp đồng tài chính.

Xóa cache có thể tái tạo bị bộ kiểm duyệt tự động chặn với thông báo `blocked by policy`; không cache nào bị xóa. Giữ nguyên traces, screenshots, dữ liệu TEST, backups, cache chung và model Ollama. Markdown của 12 tài liệu tracked đạt; kế hoạch mới có 40 lỗi khoảng trắng bảng, giữ nguyên bản gốc để xử lý định dạng khi đọc kế hoạch ở công đoạn sau.

### Lỗi backup đã sửa và bằng chứng

Công cụ backup cũ giữ nhiều bản metadata đồng thời và bị OOM kill trong Worker 512 MiB, exit137. Lượt `backup_0e52b435f88841cf9d3f8d5e1298c023` không có receipt restore PASS, được giữ nguyên, không dùng làm mốc khôi phục. Schema thử của lượt lỗi đã được dọn trước khi tiến trình bị dừng ở bước đối chiếu cuối; không ghi vào public.

`tools/check-backup-restore.py` ghi định dạng metadata cũ theo từng dòng, đối chiếu từng bảng và restore theo batch200; giải phóng bản giải mã sau mỗi bảng. Không tăng tài nguyên, tạo server hoặc đổi backup codec. Bốn ca regression bổ sung kiểm bytes tương thích và phát hiện sửa/mất/thêm bản ghi; ca codec chống giả type tags vẫn giữ.

Backup `backup_676b5d2f0d06435b8032cd8bc228bb95` đạt restore trên PostgreSQL hiện có: **24 bảng, 6.755 tệp**, backup31,379giây, restore40,475giây. Metadata SHA-256 `9fc3cea0c5f2b5a94b26da07af68b8596c9927437c310b163743769da0bdb7d2` trùng bản trước sửa. Toàn bộ metadata sản xuất và artifact checksum không đổi. Backup giữ trên volume và bản sao host tại `runtime/backups/backup_676b5d2f0d06435b8032cd8bc228bb95`; kiểm SHA-256 metadata và đủ6.755tệp trên host PASS. Receipt/log trong `runtime/consolidation/`, không vào Git.

### Kiểm chứng đang thực hiện

Baseline Backend/PostgreSQL **479/479 PASS**, 134,90giây; năm ca backup sau sửa PASS (gồm một ca cũ, bốn ca mới). Ruff, mypy50files, TypeScript, ESLint, production build, dependency consistency, secret/history/path scan và Markdown tracked PASS. GitHub hiện Public, origin chính thức đúng; không có workflow CI hoặc GitHub Actions run để dùng làm bằng chứng CI PASS.

Đã đối chiếu45tệp Backend giữa source và hai container,7tệp Frontend giữa dist/image/HTTP: cùng application revision `58cbc3c`; repository HEAD `4124d17` có thêm tài liệu/công cụ. Bốn dịch vụ healthy, queue không có tác vụ active trước backup. Sau sửa công cụ, full Backend/PostgreSQL **483/483 PASS**,183,60giây; full Playwright **139/139 PASS**,12,7phút, không retry/skip. Main hợp nhất tại `858dfb3a427b457c1afa2e0783cdb9e31d6309bd`, không conflict, cây nội dung bằng Foundation `1aee939`; cả product-polish và Foundation là tổ tiên. Đã push và xác minh SHA origin. Main đạt483/483Backend/PostgreSQL (212,49giây) và139/139Playwright (12,7phút). Image sau build/rollback đạt483/483 (137,88giây), smoke13/13 (4,5phút). Không retry hoặc bỏ test.

Backend/Worker image `sha256:ee459eecd9c99b44b14944bb9a1046d9d0302a451caac4007aaa17fdf87b8619`, Frontend `sha256:231f80c3b30b2ae08bae350d61579275a8f851627414b6840d7881f39457e043`, cùng revision858dfb3; source45files và HTTP7assets khớp. Rollback58cbc3c đã chạy thật rồi trở lại main; cả hai lượt persistence PASS. Giữ image rollback Backend `ec809221ac40`, Frontend `b747bf3b7aef`. Đã xóa đúng hai image cũ `0462a566d402`/`5226dd8c8bd1` sau kiểm ownership, references và smoke. Bốn dịch vụ healthy;27container ngoài Studio cùng IDs/images/mounts (so theo destination, không theo thứ tự mảng);36volumes không đổi. Ledger Gemini378→378, không gọi AI mới.

Hai nhánh cũ trên origin được giữ để truy vết. Toàn bộ commit hợp nhất đã nằm trong main. Kế hoạch được lưu nguyên văn tại `1aee939`. Công đoạn hợp nhất kỹ thuật đã hoàn tất. Cleanup cache có trạng thái **SKIPPED_BY_POLICY — NON_BLOCKING** theo chỉ dẫn tiếp theo của chủ dự án. Triển khai tự động hóa tiếp tục trên `codex/intelligent-automation-experience` từ main `3deac3f`. Mốc hợp nhất chưa phải nghiệm thu hành trình tự động hóa.

---

## Tự động hóa sau upload — nhánh triển khai

CSV/XLSX mới có Parquet tự chuẩn bị và dòng cần kiểm tra, đọc từ màn hình Dữ liệu và API truy vấn có kiểu. Mapping tương thích được điền vào bản nháp cùng evidence mới. Worker có một luồng xử lý job chờ provider và nhận parse trong khi luồng đó bận. Planner kiểm khóa trong kỳ và chọn bản nháp xác định khi đủ bằng chứng. Top-N và câu hỏi theo vị trí dùng bảng đã lưu của đúng run.

Full Backend/PostgreSQL trên nguồn triển khai đạt **488/488** trong 147,39 giây, có một cảnh báo deprecation của TestClient. Có các ca mới kiểm prepared khi tắt AI, giữ dòng nguồn, template khác cấu trúc, parse khi inference bị giữ, Planner trong kỳ và truy vấn theo vị trí. Browser tập trung đạt **8/8** trên frontend build mới với backend baseline. Lượt này kiểm sidebar ở năm chiều rộng và phân trang dữ liệu gần đây. Full browser trên cả ứng dụng mới và nghiệm thu ba nguồn đang chờ.

Benchmark CSV tổng hợp trên Windows với hai luồng Polars, năm lượt mỗi mức, không AI. Bước tạo và ghi Parquet prepared đạt p50/p95 quan sát lần lượt 2,65/68,69 ms ở 10 dòng, 2,73/3,82 ms ở 1.000 dòng, 4,49/5,99 ms ở 10.000 dòng và 15,40/16,15 ms ở 75.000 dòng. Đây là phép đo riêng bước prepared sau parse và profile. Receipt ở `runtime/automation-preparation-benchmark.json`, ngoài Git.

Mapping Memory hỗ trợ cấp quyền tái áp dụng theo mẫu đã duyệt. Kiểm thử PostgreSQL gồm quyền owner, chống gửi cũ, preflight toàn bảng, tiền tệ đổi, tên tệp khác và thu hồi quyền. Full Backend/PostgreSQL trên nguồn bổ sung đạt **489/489** trong 145,25 giây. Bài thử dùng transport giả lập hoặc xử lý nội bộ.

Benchmark kiểm khóa duy nhất và currency dùng 15 mẫu thời gian mỗi kích thước. Cả Polars trực tiếp và Pandera 0.35.0 phát hiện khóa trùng và USD trong bộ hóa đơn tổng hợp. Ở 75.000 dòng, p50/p95 của Polars là 1,872/3,140 ms và Pandera là 8,012/9,717 ms. Đây là phép đo hai điều kiện, tách khỏi preflight nghiệp vụ. Pandera chỉ được cài trong thư mục thử nghiệm ngoài cây source và không vào lockfile. [Pandera Polars](https://pandera.readthedocs.io/en/v0.35.0/polars.html).

Valentine 1.1.0 có matcher cấu trúc và phân bố. Dry-run dependency cho thấy thêm nhiều gói, gồm NumPy, SciPy, pandas và bộ giải tối ưu. Benchmark thực thi Valentine được bỏ qua trong vòng này để giữ phạm vi tài nguyên của máy chạy Ollama. Chưa có bằng chứng so chất lượng Valentine với matcher hiện tại. [Valentine](https://delftdata.github.io/valentine/).

### Nghiệm thu bộ ba nguồn trên candidate `92dd889`

Qua trình duyệt, dự án TEST nhận CSV đơn dự kiến, XLSX sự kiện thanh toán và CSV sao kê. Ba job parse công bố raw và prepared lần lượt sau 1,218 / 2,131 / 2,193 giây kể từ lúc xếp hàng, với 2.418 / 2.685 / 384 dòng. Tổng 5.487 dòng. Người kiểm thử duyệt ba ánh xạ trong giao diện, có 5.458 dòng hợp lệ và 29 dòng cần kiểm tra. Lượt đo này chỉ gồm ba nguồn, chưa phải p95 của upload-to-prepared.

| Cặp nguồn | Quan hệ đã duyệt | Khớp / lệch / thiếu đối ứng | Lệch có dấu / tuyệt đối |
| --- | --- | --- | --- |
| Đơn dự kiến ↔ thanh toán | 1:N, scope và reference | 2.040 / 200 / 215 | 7.867 / 60.883 VND |
| Thanh toán ↔ sao kê | N:1, scope và batch_id | 323 / 40 / 31 | −8.306 / 11.812 VND |

Cả hai run mới là `PARTIAL_VERIFIED`. Số nhóm và tiền khớp oracle Decimal độc lập. Hai XLSX tải từ UI có cùng snapshot với API và giữ kết quả sau reload. Hành trình CSV/XLSX riêng kiểm cả quyền tái sử dụng mapping và lần tải tương thích tự chuẩn hóa, không thêm lượt gọi model. Chat top 3 và giải thích nhóm thứ hai trên hai run đã xác minh có 0 lượt gọi model và giữ đúng tham chiếu khi tải lại. Receipts nằm ngoài Git ở `runtime/automation-three-source/` và `runtime/automation-native-top-results.json`.

Gemini LIVE trên candidate cũ trả HTTP 200 cho định tuyến (3,328 giây, 17.967 token) và Planner (3,024 giây, 14.101 token). Bộ định tuyến thiếu hai vai trò nguồn và bộ lọc đã nêu. Review có gợi ý nhưng thiếu kế hoạch để duyệt. Lượt LIVE được ghi **FAIL cho hành trình đối soát trọn vẹn**. Người kiểm thử dùng hai quy tắc duyệt thủ công cho bảng oracle. Ledger tăng 378 → 380, ứng dụng không đổi ngân sách hoặc chính sách.

### Sửa Planner sau lượt LIVE

Prompt định tuyến nêu rõ vai trò và bộ lọc của từng nguồn. Backend từ chối giá trị lọc không có trong yêu cầu hoặc phạm vi đã duyệt của đúng nguồn. Planner xét khóa ghép đã duyệt ở phía neo ngay cả khi phía chi tiết có khóa chính khác. Trường scope chỉ được thêm theo bộ lọc cố định giống nhau ở hai nguồn hoặc khi cả hai schema xác nhận đó là định danh. Đọc lại canonical của hai run mới, backend tìm đúng cả khóa ghép lẫn quan hệ 1:N và N:1, dựa trên overlap trong kỳ.

Job Planner mới từ Chat chỉ xuất bản đề xuất Backend đã kiểm tra hoặc trả về thẻ chỉnh sửa khi chưa đủ bằng chứng. API yêu cầu gợi ý AI trước đây vẫn giữ khả năng cung cấp gợi ý có kiểu khi không có phương án Backend. Gợi ý và đề xuất mới đều cần người dùng duyệt. Tất cả bước tính và kiểm chứng tiền dùng engine hiện có.

Hồi quy trên source Planner mới đạt **498/498 Backend/PostgreSQL**, trong 236,56 giây, có một cảnh báo deprecation của TestClient. Hai chiều khóa ghép, lọc scope sai, lỗi `AI_PLAN_MISSING` của tuyến cũ và thẻ review Chat khi thiếu phạm vi đều có test. Bốn bộ holdout tổng hợp (hóa đơn, hoàn tiền, công nợ, tồn kho) kiểm đúng Decimal và giữ đủ dòng bằng chứng.

Sidebar sáu mục theo kế hoạch tự động hóa §6.1 là yêu cầu mới thay bố cục ba mục ghi tại Rules §9.1. Vòng Playwright đầu trên `92dd889` đạt 134/139, năm ca visual còn kỳ vọng ba nút. Đã sửa kỳ vọng để kiểm đủ sáu mục và giữ kiểm tra focus.

Lượt full Playwright sau sửa kỳ vọng đạt **139/139**, 13,8 phút, một worker, không retry hoặc bỏ case. Source `b6bcbba` đã push và triển khai với 46 file Python khớp Backend/Worker, bảy assets Frontend khớp HTTP và khớp toàn bộ checksum của frontend đã chạy full browser. Backend/Worker image `eaa6b45496eac2c1ee8083be835d3a25b07ebff9a9e8e86d1970cef962781596`, Frontend `a8ec6eccae5ec17d1c1c33a00c340bb50819ef8bc8409e9df1c523920159cdef`. Bốn dịch vụ healthy.

Gemini LIVE sau sửa tạo đúng scope, vai trò, khóa ghép và quan hệ 1:N trên thẻ duyệt. Người kiểm thử xác nhận thẻ rồi run `b71e077c-442f-42eb-9563-3b17fb580e7b` khớp oracle 2.040 khớp, 200 lệch, 215 thiếu đối ứng và 7.867 / 60.883 VND. Định tuyến dùng một lượt Gemini trong 2,866 giây. Planner phía Backend không gọi provider. Ledger 380 → 381.

Qwen LIVE chọn đúng hai nguồn và kỳ nhưng bỏ dữ kiện vai trò, ngày và phạm vi đã nêu. Workflow dừng ở thẻ cần bổ sung, không tạo run. Định tuyến trả hợp đồng hợp lệ sau 51,058 giây, 2.895 prompt token và 194 output token, 0 cloud requests. Trong lúc inference này đang chạy, một upload CSV tổng hợp 75.000 dòng được parse và tạo prepared xong trước khi inference kết thúc. Browser quan sát 5,677 giây, thời gian xử lý job parse là 3,631 giây. Đây là một lượt đồng thời, chưa phải p50/p95. Receipt ở `runtime/automation-live-planner-QWEN_8B.json`.

Phát hiện prompt rút gọn riêng của Qwen thay toàn bộ prompt chung. Source mới thêm hướng dẫn vai trò/bộ lọc vào đúng prompt local, yêu cầu hai đối tượng nguồn và đủ các trường nullable trong JSON Schema. Dữ kiện chưa được nêu tiếp tục là null. Regression đi qua Ollama transport giả lập, kiểm hợp đồng local thực sự gửi và bảo toàn việc hỏi khi chưa đủ nguồn. Nhãn quan hệ và phép cộng nhóm trên thẻ duyệt được hiển thị bằng tiếng Việt.

Source `d1c34b9` đạt **499/499 Backend/PostgreSQL**, 133,05 giây, cùng Ruff, mypy, TypeScript, ESLint và build. Đã triển khai, đối chiếu source46files/HTTP7assets và bảo toàn metadata/tệp khi recreate. Lượt Qwen tiếp theo vượt timeout90giây, job `17a8553c-0640-484e-8201-b94b38204673` kết thúc FAILED với `OLLAMA_UNAVAILABLE`. Chưa tạo workflow, ledger381không đổi. Giữ receipt này ở `runtime/automation-live-planner-QWEN_8B.json`, lượt thiếu dữ kiện trước đó ở tệp `*-before-schema.json`. Cổng Qwen LIVE vẫn FAIL.

Chat bổ sung hai câu đọc xác định trên bản tự chuẩn bị của một tệp được chọn. Xem trước và đếm dòng dùng cùng Query DSL, kiểm quyền và checksum, không gọi model, không tạo mapping/canonical hoặc quyền đối soát. Không chọn rõ một bảng thì hỏi lại. Validator từ chối việc tự đổi sang prepared bằng yêu cầu khác hoặc tham chiếu bảng ngoài ngữ cảnh. UI ghi rõ đây là bản tự chuẩn bị cần xác nhận nghiệp vụ.

Full Backend/PostgreSQL trên source bổ sung này đạt **501/501**,128,43 giây. Trong ca PostgreSQL, hai câu hỏi trả đúng hai dòng và mã có số0đầu khi provider bị cấm gọi, không có trace AI hoặc canonical được tạo. Ruff, mypy51files, TypeScript, ESLint, build và Markdown đạt.

### Bảo toàn và công cụ backup

Lượt `backup_23e21b4d901442dc8ab9c43e93cd5897` có metadata 64.907.007 byte, bị OOM tại bước đọc toàn bộ metadata để restore. Exit137 được giữ, không có receipt PASS. Công cụ backup lập chỉ mục byte của từng bản ghi lúc ghi file, rồi đọc và insert từng batch200 từ chính file backup. Định dạng codec cũ giữ nguyên byte, được regression kiểm Unicode, ngày, Decimal và nhãn JSON không đáng tin.

Backup mới `backup_675dc832f0084e79858fe51dfed4a107` khôi phục thử thành công **24 bảng và 7.634 tệp**, sao lưu 34,235 giây và restore34,747 giây. Metadata SHA-256 `13cf2fdd930f359a349292ba3e0ac5a3f56c3f92609b830a042443bb71b04dde`. Đã copy đúng backup sang host và kiểm đủ checksum 7.634 tệp. Toàn bộ metadata/tệp của candidate trước và sau recreate khớp. Các bản ghi và 7.203 tệp của baseline ban đầu vẫn đủ và không đổi. Không có migration database.

### Trạng thái các cổng phát hành

| Cổng | Trạng thái và bằng chứng |
| --- | --- |
| AP-01 | PASS, Product Journey chạy upload CSV/XLSX không cần prompt |
| AP-02 | PASS local/mock, raw/preview đọc được trong browser và PostgreSQL mô phỏng inference bận |
| AP-03 | PASS, PostgreSQL và ba nguồn fresh kiểm prepared riêng với trạng thái cần duyệt |
| AP-04 | PASS, 5.487 dòng được giữ, preflight kiểm toàn bảng, 29 dòng cần kiểm tra |
| AP-05 | PASS trong phạm vi tái dùng exact, cấp/thu hồi quyền, loại drift và preflight |
| AP-06 | NOT_RUN, chưa có tập holdout gán nhãn độc lập để đo precision/recall mapping hoặc số liệu Valentine |
| AP-07 | PASS cho lần tải tương thích đã được cấp quyền. NOT_RUN cho nghiệm thu đầy đủ đề xuất AI mới không cần điền kỹ thuật lặp lại |
| AP-08 | PASS Gemini LIVE sau sửa với Backend proposal, duyệt UI và oracle. FAIL Qwen LIVE vì bỏ dữ kiện nguồn |
| AP-09 | PASS local, duyệt quy tắc riêng qua API và hồi quy scope/quyền/idempotency |
| AP-10 | PASS cho API raw/prepared và Chat top-N/giải thích theo vị trí. NOT_RUN cho câu hỏi tự nhiên tổng quát trên prepared |
| AP-11 | PASS cho Product Journey CSV/XLSX, đối chiếu hai XLSX mới và snapshot sau reload |
| AP-12 | PASS ở năm chiều rộng trong hồi quy sidebar sáu mục và focus |
| AP-13 | PASS PostgreSQL với provider giả lập bị giữ và một lượt Qwen LIVE đồng thời với 75.000 dòng. NOT_RUN p50/p95 tải đồng thời |
| AP-14 | PASS baseline rollback/restore, candidate restore24bảng/7.634tệp và bảo toàn lúc recreate |
| AP-15 | NOT_RUN cho phát hành main. Giữ nhánh triển khai riêng cho đến khi các cổng bắt buộc đạt |

---

**Hiện trạng 06/11/2026 — Foundation Reliability Audit.** Bản local chạy `58cbc3c4781d6f331b7c67c2007844bb5b012bce`, đạt 479/479 Backend/PostgreSQL và 139/139 Playwright. Hai model đã tạo đề xuất và cập nhật review thực tế. Mỗi luồng chuẩn hóa đúng 5.458 dòng hợp lệ và 29 dòng lỗi. Hai cặp đối soát trên dự án Gemini khớp đáp án độc lập. **Chưa FOUNDATION_ACCEPTED, chưa hợp nhất main.** Các mốc bên dưới ghi lịch sử theo ngày.

## Foundation — lỗi đã tái hiện và phần kiểm chứng hiện có

### A. Tổng quan

Gemini là lựa chọn mặc định. Qwen 3:8B là lựa chọn phụ do người dùng chọn. Hai model dùng cùng hợp đồng định tuyến và sửa review. Bản local đã dùng được để thử tải tệp, sửa bản nháp, duyệt chuẩn hóa và chạy đối soát theo phạm vi đã kiểm chứng.

### B. Git và baseline

Nhánh làm việc `codex/foundation-reliability-hardening` xuất phát từ `2eecb068b0a866a538cda95a218ac9e375b10eb0` trên `codex/product-polish`. Đã xác minh origin của AI Reconciliation Studio. Các commit được đẩy theo nhóm, gồm parser `38d3f1b`, review và idempotency `1ed78ca`, thẻ dùng chung `ae2268b`, tương thích Gemini `923c8a0`, định tuyến Qwen `96ec609`, khôi phục trang `2d15785`, bộ chọn `ae15e71`, xác nhận dòng lỗi trong Chat `a99cc0b`, bố cục mobile `82efd82`, rút gọn định tuyến local `4347b07`, xem hạn hiệu lực `a28278d` và kiểm xác nhận dòng lỗi ở mọi đường duyệt `58cbc3c`.

### C. Docker và khôi phục

Backup `backup_2fbbe0bc84ed4c5e8b752f83099af041` được tạo trong 53,581 giây và restore trong 33,195 giây vào schema cô lập trên PostgreSQL hiện có. Đối chiếu 24 bảng và manifest 5.910 tệp. Kiểm tra checksum và đường dẫn đạt. Lần chạy đầu trên Backend bị dừng do áp lực bộ nhớ. Bản backup được xác minh nằm trên volume của Studio.

Rollback đầu lượt sang cặp `5373cf7`/`729821e` rồi trở về baseline `a268abe` đã qua health và persistence. Sáu image Studio cũ được xác minh theo ID và kiểm tra không còn tham chiếu trước khi xóa. Hai volumes Studio, backup, cache, model Ollama và 27 container ngoài Studio được giữ.

Trên `58cbc3c`, restart, tạo lại toàn bộ và tạo lại riêng Frontend đều vô hiệu hóa phiên demo cũ trước khi xác minh loopback. Mỗi lần đều khớp snapshot metadata, bản duyệt, canonical refs và toàn bộ checksum artifact. Sau đó `tools/rollback.ps1` thực sự chuyển Backend, Worker, Frontend sang cặp `a268abe` có cùng revision Git. Đối chiếu dữ liệu đạt trên cặp dự phòng và khi trở lại `58cbc3c` bằng `tools/start.ps1 -SkipBuild`.

Sau full regression, xóa thêm đúng hai image Studio mang tag `rollback-before-mapping-recovery`. Cả hai không còn container tham chiếu. Tổng cộng đã bỏ tám image Studio cũ trong đợt này, giữ cặp hiện hành và một cặp dự phòng. Đối chiếu cuối cho thấy 27 container ngoài Studio, image của dự án khác và 36 volume trên máy có cùng định danh và trạng thái kiểm kê. Dung lượng tổng do Docker báo vẫn 38,91 GB cho image ở độ chính xác hiển thị vì có lớp dùng chung. Bốn dịch vụ Studio healthy, không có OOM hoặc restart ngoài dự kiến ở các container đang chạy.

### D. Kiến trúc

Audit theo nhóm tải và lưu nguồn, profile và chuẩn hóa, quy tắc và đối soát, hội thoại và AI, trình duyệt và vận hành. Dùng cùng DTO và bản nháp từ `AgentWorkflowRow` ở Chat và Dữ liệu. Hai provider cùng kiểm kiểu, source, scope và bằng chứng. Duyệt nghiệp vụ tiếp tục đi qua transaction, khóa nguồn, nonce và kiểm quyền. Xem [ma trận kiến trúc](ARCHITECTURE.md).

### E. Lỗi và kiểm thử hồi quy

| ID / mức | Tái hiện và nguyên nhân | Sửa và kiểm chứng | Hiện trạng |
| --- | --- | --- | --- |
| FND01 / P1 | Header CSV/XLSX trùng bị bỏ; dòng dữ liệu đầu thành header | Giữ nhãn trùng và technical column IDs, warning extraction; regression hai định dạng | PASS source, parser commit38d3f1b |
| FND02 / P1 | Header CSV chỉ định sau ô quoted nhiều dòng bị hiểu theo logical index | Ánh xạ dòng vật lý bắt đầu record; từ chối dòng giữa quoted cell | PASS source, commit38d3f1b |
| FND03 / P1 | Review có đề xuất và câu hỏi bị từ chối AI_INVALID_REVIEW do yêu cầu lặp toàn bộ bản nháp | Chỉ nhận các thay đổi có kiểu, giữ phần hợp lệ và hỏi tiếp. Kiểm transport và PostgreSQL | PASS MOCK và lượt bổ sung LIVE Gemini/Qwen |
| FND04 / P2 | Chat giữ draft trong state component, Manager đọc proposal khác | Cùng ReviewCard, API lưu draft có nonce và kiểm nguồn, khôi phục bảng/tab và mở đúng hội thoại | LIVE browser PASS, `ae2268b`, `2d15785`, `ae15e71` |
| FND05 / P2 | Review hết 30 phút thiếu hành động gia hạn | Mở lại khi đúng chủ, nguồn còn nguyên và không có reply đang chạy | PostgreSQL và browser PASS, `1ed78ca`, `ae2268b` |
| FND06 / P1 | POST duyệt mapping thủ công tạo revision mới khi gửi lại | Actor-scoped idempotency receipt cùng transaction/advisory lock, conflict409 | PostgreSQL PASS |
| FND07 / P2 | Reply hợp lệ sau lỗi vẫn giữ error_code hiện hành | Xóa lỗi hiện hành khi không còn bước lỗi khác, giữ message/job cũ | Fault/recovery PostgreSQL PASS |
| FND08 / P2 | Reply rule buộc plan hoàn chỉnh, khó giữ facts từng phần | Hợp nhất PlanningRequest chỉ những trường đã cung cấp, không đổi nguồn, preview/approval riêng | Unit/contract PASS; UAT tiếp tục |
| FND09 / P1 | Gemini trả 400 với giới hạn mảng trong grammar review | Rút giới hạn khỏi envelope gửi provider, Backend vẫn từ chối trên 80 thay đổi | A/B LIVE 400→200 và reply UI PASS, `923c8a0` |
| FND10 / P1 | Router Qwen nhận schema rộng hơn Gemini và bị AI_INVALID_INTENT | Cùng grammar cho từng intent và cùng validator cho hai model | Qwen LIVE tạo đúng ba review sau sửa, `96ec609` |
| FND11 / P1 | Router chặn toàn bộ nguồn PARTIAL trước bước review | Cho lập đề xuất mới và yêu cầu xác nhận tách dòng lỗi ở cả UI lẫn Backend trước khi chạy | PostgreSQL, mock browser và hai oracle LIVE qua UI PASS, `a99cc0b` |
| FND12 / P2 | Danh sách sửa cơ sở tiền thiếu lựa chọn phí khi có giá trị đề xuất sẵn | Bổ sung lựa chọn `fee` và `expected`, giá trị locale chưa chọn dùng null | Qwen duyệt nguồn ngân hàng và đúng 378/6, `a99cc0b` |
| FND13 / P2 | Tên model dài làm ô nhập bị cắt ở 390 px | Danh sách đúng hai tên, model và nút gửi xuống hàng dưới ở điện thoại nhỏ | Browser 390–1920 px PASS, `ae15e71`, `82efd82` |
| FND14 / P2 | Thẻ duyệt chỉ hiển thị ngày bắt đầu hiệu lực, khó phát hiện ngày kết thúc do model đề xuất | Hiện ngày kết thúc trong tóm tắt và cho sửa hoặc xóa trước khi duyệt | Browser MOCK PASS, `a28278d` |
| FND15 / P1 | Màn hình đối soát thủ công đi qua API duyệt khác nên bỏ qua xác nhận tách dòng lỗi | Hàm duyệt dùng chung kiểm tra cả Chat và màn hình thủ công, ghi một sự kiện kiểm toán. UI hiện tên nguồn và số dòng lỗi trước khi duyệt | PostgreSQL và ca vận đơn trên Docker PASS, `58cbc3c` |

### F. AI Agent

Gemini đã nhận sáu HTTP 200 khi thử lại, gồm hai probe và luồng ba nguồn trên giao diện. Reply ánh xạ sau sửa đạt trong 1,378 giây. Qwen định tuyến sau sửa trong 30,898 giây. Ba đề xuất Qwen mất 18,274, 7,349 và 7,895 giây. Reply Qwen đạt trong 16,394 giây. Hai model giữ câu hỏi còn thiếu và để thẻ ở trạng thái chờ duyệt. Với cặp ngân hàng, Gemini trả HTTP 503 ở lượt bổ sung vai trò nguồn. Giữ job lỗi trong lịch sử và hoàn tất từ đề xuất đã có bằng xác nhận trực tiếp trên giao diện.

### G. Data Foundation

Mỗi dự án tổng hợp của Gemini và Qwen có ba nguồn với 2.418, 2.685 và 384 dòng. Số hợp lệ/lỗi lần lượt là 2.406/12, 2.674/11 và 378/6 theo bộ khóa bắt buộc. Tổng 5.458/29. Tệp gốc, checksum, bản chuẩn hóa và tệp lỗi giữ tham chiếu theo revision. Người vận hành dùng thẻ để xác nhận khóa, ngày và tiền theo đặc tả dữ liệu TEST.

### H. Đối soát và oracle

| Cặp nguồn | Khớp | Lệch tiền | Thiếu đối ứng | Tổng có dấu VND | Tổng tuyệt đối VND |
| --- | ---: | ---: | ---: | ---: | ---: |
| Đơn dự kiến và sự kiện thanh toán, 1:N | 2.040 | 200 | 215 | 7.867 | 60.883 |
| Sự kiện thanh toán và sao kê ngân hàng, N:1 | 323 | 40 | 31 | −8.306 | 11.812 |

Run `a725f99a-b85f-4a9b-8a9f-55dacb9b8f1a` đi qua Gemini, duyệt và chạy trong Chat. Run `9134d95e-f944-41e5-9389-010d36e9e265` dùng đề xuất Gemini, người vận hành xác nhận vai trò và phạm vi trên thẻ sau lượt gọi bổ sung bị 503. Oracle tính độc lập với Matcher. Verifier và các phép tính Decimal giữ hợp đồng đã duyệt.

Hai tệp XLSX tải qua giao diện được mở và đọc lại. Mỗi tệp có tám sheet. Đếm nhóm và tổng Decimal trong `Matches` khớp oracle và `Summary`. Nhóm lệch thứ hai có đủ bằng chứng hai phía với 2 tham chiếu ở cặp đơn hàng và 8 tham chiếu ở cặp ngân hàng. Kiểm tra các ô của hai workbook phát hiện 0 công thức.

Sau khi trở lại `58cbc3c`, đọc lại hai snapshot qua HTTP và đối chiếu đủ số nhóm, chênh lệch có dấu và chênh lệch tuyệt đối. Các ca vận đơn 1:1, 1:N và N:1 trong Playwright tiếp tục khớp oracle riêng.

Hai cặp nguồn đã được Qwen hỗ trợ chuẩn hóa cũng khớp cả năm chỉ số trong bảng khi lập và duyệt quy tắc thủ công trên giao diện. Hai run là `453ee28e-6b7e-438d-82a4-5aa4f034e92e` và `5c4bf12b-1667-47c5-af60-2ff3e6969870`. Cả hai qua bước xác nhận dòng lỗi, xuất CSV/XLSX và mở lại đúng snapshot. Mỗi XLSX có tám sheet và không chứa ô công thức. Đây là bằng chứng của đường duyệt thủ công trên dữ liệu chuẩn hóa với Qwen.

### I. Kiểm thử

Baseline đạt 449 Backend/PostgreSQL và 139 Playwright. Revision `82efd82` đạt 478 Backend/PostgreSQL, 137/139 Playwright. Ca tải tệp chờ sau Qwen 90 giây trên Worker chung. Trace PostgreSQL ghi tác vụ tải xong ngay sau khi Qwen kết thúc. Ca mobile còn dùng giới hạn chiều cao của bố cục một hàng. Chạy lại riêng sau khi hết tải đồng thời và cập nhật kiểm tra theo hình học bố cục mới đạt 2/2. Sau đó `a28278d` đạt đủ 478 Backend/PostgreSQL và 139 Playwright trong 12,4 phút.

Ca PostgreSQL mới của `58cbc3c` tái hiện bản trước trả HTTP 200 khi duyệt thiếu xác nhận tách dòng lỗi. Sau sửa, ca này và hai ca Chat liên quan đều đạt. Khi duyệt lần đầu nguồn `PARTIAL`, API yêu cầu giá trị boolean `true`. Quy tắc đã duyệt được giữ và gửi lại trả cùng hợp đồng.

Full regression trên đúng `58cbc3c` sau rollback đạt **479/479 Backend/PostgreSQL** (133,14 giây) và **139/139 Playwright** (12,1 phút). Bộ trình duyệt có luồng thật qua Docker, ca giả lập lỗi provider/mạng và kiểm responsive. Ca vận đơn có ngày lỗi xác nhận nút duyệt bị khóa khi chưa đánh dấu, sau đó chạy đúng oracle. Bộ chọn model kiểm trực tiếp ở 390, 768, 1366, 1440 và 1920 px, chỉ có hai tên đã chốt, giữ Qwen sau reload và không tràn khung.

Các kiểm tra mới có giả lập transport hai provider, chuỗi sửa bản nháp Hypothesis, đối chiếu số tiền theo phép đổi dấu, kiểm trả lời hợp lệ sau lỗi, thử khóa cũ, viewer, pending và nguồn thay đổi. Ba ca dữ liệu hóa đơn, lương và tồn kho bị từ chối khi dùng quy tắc đơn hàng không tương thích. Có một cảnh báo deprecation từ Starlette TestClient.

Đo một lượt trên host Windows, CSV tổng hợp, Polars 2 luồng. Với 75.000 dòng, parse 89,86 ms, profile 1.112,64 ms, chuẩn hóa và ghi 2.528,90 ms, peak 222,83 MiB. Đối soát 75.000 dòng từ hai nguồn mất 2.556,20 ms ở Matcher và 1.509,92 ms ở Verifier, tạo 37.500 nhóm exact, peak 454,68 MiB. Đây là số đo theo bước trên host. Các mức 10/100/1.000/10.000 dòng cũng được kiểm số dòng, số lỗi và mã có 0 đầu.

Trên Docker `a28278d`, Worker bị ngắt giữa chuẩn hóa 75.000 dòng tổng hợp. Phép thử đẩy lease của đúng tác vụ tổng hợp về thời điểm hết hạn để quan sát nhận lại. Sau hai lần nhận, chỉ một canonical 75.000 dòng được công bố, hội thoại tiếp tục và không phát sinh lượt cloud. Tổng thời gian bài thử 17,813 giây. Phép thử này đo khôi phục tác vụ, giới hạn đo độ trễ p95 và tải thực vẫn còn.

### J. Toàn vẹn dữ liệu

Đối chiếu snapshot trước và sau triển khai đạt cho metadata, bản duyệt, canonical refs và toàn bộ bytes artifact đã lưu. Hai dự án TEST thêm dữ liệu và lịch sử có chủ đích. Dữ liệu nghiệp vụ cũ được giữ trong volume. Backup và restore ở phần C áp dụng cho baseline đã ghi nhận.

### K. GitHub và bản đang chạy

Studio dùng một Compose project và bốn dịch vụ trên loopback. Cả Backend, Worker và Frontend mang source revision `58cbc3c`. Backend và Worker dùng chung image `sha256:ec809221ac408f94f1874f862c23faf03bdd0decff4a57cb2e95ddd7c79ef626`. Frontend dùng `sha256:b747bf3b7aef4708c845b33811e9bc597266e7a321ef51c11159684a36e7acb3`. Đối chiếu 45 tệp Python giữa source và image, cùng 7 tệp frontend giữa build, image và HTTP đã đạt.

Commit vận hành `88e9946` xác minh cặp image dự phòng và cập nhật hướng dẫn kiểm thử. Nhánh nghiệm thu lưu mã và bằng chứng mô tả trên origin chính thức. Hai mốc `main` và `codex/product-polish` giữ tại `a4f70b2` và `2eecb06` trong vòng kiểm toán.

### L. Giới hạn đang theo dõi

Gemini từng trả 503 ở tác vụ bổ sung quy tắc, do đó vòng cloud dừng tại lượt này. Kết quả LIVE trên hai dự án TEST chứng minh các luồng được thử. Bộ câu hỏi chuẩn LIVE đầy đủ cho định tuyến và ngữ nghĩa còn thiếu bằng chứng. Một lượt suy luận chậm có thể làm tác vụ tệp đợi trên Worker chung, như trace của lần thử 90 giây ở phần I.

Qwen nhận yêu cầu lập quy tắc dài qua Ollama nhưng vượt 90 giây ở router. Backend ghi `OLLAMA_UNAVAILABLE` với cờ chưa biết Ollama đã nhận đầy đủ hay chưa, giữ job và hội thoại. Qwen dùng RTX 3050 Laptop 6 GiB, lần gọi này đưa 24/37 lớp lên GPU. Probe sau khi rút gọn định tuyến ở `4347b07` trả đúng một intent sau 44,515 giây, còn thiếu một số dữ kiện phạm vi. Planner chuẩn vượt 90 giây trong phép thử tách riêng. Bản thử Planner rút gọn trả HTTP 200 sau 28,657 giây nhưng Backend chặn vì quan hệ gom nhóm sai. Bản thử Planner rút gọn đã được loại khỏi bản triển khai.

Trên bản đang chạy, gửi lại yêu cầu lập quy tắc qua giao diện sau khi thay router. Qwen định tuyến thành công sau 43,786 giây. Planner trả HTTP 200 nhưng thiếu đề xuất hợp lệ sau 64,881 giây. Backend ghi `AI_PLAN_MISSING` và dừng trước duyệt. Trong lần hỏi ba chênh lệch lớn nhất của một run đã xác minh, Qwen hỏi nhầm về độ đầy đủ và ngày chốt nguồn. Luồng dừng ở thẻ hỏi làm rõ. Hai ca này giữ nguyên trong kết quả LIVE và cổng E/J vẫn chưa đạt toàn phần.

### M. Bắt đầu thử local

Mở <http://127.0.0.1:18180>, tạo dự án Kiểm thử và đính kèm ba tệp mẫu. Giữ mặc định **Gemini 3.5 Flash Lite** hoặc chọn **Qwen 3:8B**. Gửi “Tôi vừa tải dữ liệu lên. Hãy kiểm tra và đề xuất cách chuẩn hóa để tôi có thể đối soát.” Xem từng thẻ, lưu bản nháp nếu cần chuyển màn hình rồi xác nhận trước khi chuẩn hóa. Kiểm số dòng và lỗi của từng nguồn, sau đó chọn hai nguồn và duyệt quy tắc đối soát. Xem [hướng dẫn tự kiểm thử](USER_TEST_GUIDE.md).

### Trạng thái các cổng nghiệm thu

| Cổng | Kết quả | Phạm vi đã kiểm |
| --- | --- | --- |
| A. Git và baseline | PASS trong phạm vi | Giữ hai mốc Git gốc, xác minh restore, cặp image dự phòng và dọn image cũ |
| B. Contracts | PASS theo hồi quy | Review từng phần, nonce, fencing, idempotency và duyệt nguồn có dòng lỗi |
| C. Data Foundation | PASS trên bộ đã chạy | Upload, parse, profile, chuẩn hóa, lineage, dữ liệu lưu qua restart |
| D. Đối soát | PASS trên các oracle | Tiền Decimal, dung sai, phạm vi, nhóm nguồn, bằng chứng, KPI và xuất báo cáo |
| E. Agent | Một phần | Hai provider đạt mapping và bổ sung review LIVE. Lập quy tắc, chất lượng LIVE toàn bộ và giới hạn provider ở phần L |
| F. Bảo mật | PASS theo bộ kiểm | Quyền duyệt, cách ly project, CSRF, loopback, upload, policy, idempotency và quét bí mật |
| G. Frontend | PASS | 139 Playwright, lựa chọn model, hành vi keyboard, thiết bị nhỏ và các luồng nghiệp vụ |
| H. Khôi phục | PASS theo các phép thử | Retry/timeout/fault, stale review, 75.000 dòng trên `a28278d`, backup/restore và các lần tạo lại |
| I. Docker | PASS theo triển khai local | Cùng source revision, 4 healthy, checksum, replay oracle, rollback và trở lại bản chạy |
| J. Người dùng | Một phần | Luồng thủ công đi hết qua giao diện. Hai model đạt chuẩn hóa. Bằng chứng LIVE theo provider ở phần F và L |

**Mốc lịch sử — 02/11/2026:** UI AI Assistant và các kiểm tra kỹ thuật đã hoàn tất trên feature branch; **chưa đạt nghiệm thu toàn Agent-first MVP** vì chất lượng NLP chưa đạt và Gemini đã hết 50/50 attempts. Chưa merge hoặc release main. Đọc mục S để biết số đo tại thời điểm đó; các mục A–R là lịch sử.

Bối cảnh lịch sử: Quality Hardening + UX Refinement trước đây nằm trên `codex/interface-quality`, từ main `0b9421e`. Các nhiệm vụ P/Q triển khai Assistant trên `codex/assistant-automation` và dừng trước merge. Mục R ghi ủy quyền hợp nhất mới cùng gate live đang BLOCKED; không thay đổi kết luận lịch sử ở mục N.

## Final Acceptance — Giai đoạn 1 (lịch sử)

Ngày kiểm tra: **28/10/2026**. Phạm vi: Data Foundation + AI Smart Setup + UI cơ sở.

### GIAI ĐOẠN 1 ĐẠT NGHIỆM THU — QWEN LIVE ĐƯỢC HOÃN THEO CHỈ ĐỊNH

Kết luận lịch sử theo chỉ dẫn thu hẹp phạm vi ngày 28/10/2026: chỉ nghiệm thu Data Foundation + AI Smart Setup. Gemini mặc định hiện tại, Qwen live được hoãn chính thức do IP allowlist. Các gate dữ liệu, bằng chứng Gemini mapping live, LlamaParse PDF/DOCX live, regression, bảo mật, worker recovery và persistence đã đạt trong phạm vi dưới đây. Không đổi lịch sử Qwen thành PASS hoặc mở rộng ngoại lệ sang gate khác. **Quyết định lúc đó: dừng sau báo cáo; không bắt đầu Giai đoạn 2 và không merge main trong lượt đó.** Ủy quyền tiếp theo được ghi tại mục I.

Sau khi nhận chỉ dẫn mới, đã gỡ đúng các thay đổi Giai đoạn 2 chưa commit: contract reconciliation, sáu fixtures/oracle và dependency DuckDB/RapidFuzz/ECharts; dependency/lockfiles trở lại nền Giai đoạn 1. Không có engine/planner/matcher, migration hoặc tính năng Giai đoạn 2 được commit hay triển khai. `.vscode/` của người dùng giữ nguyên.

## A. Kết quả và phạm vi sửa

Giữ nền tảng đã chạy: FastAPI/worker chung image, PostgreSQL metadata, React/Nginx, raw/Parquet bất biến, CSV/XLSX parser, profiling, mapping review/revisions, typed DSL/Decimal và canonical/errors/evidence. Không xây lại Data Foundation hoặc thay công thức.

Đợt này bổ sung Gemini mặc định với cloud OFF/budgets 0 cho cài mới; document adapter cost_effective/page cap/account preflight/two-SHA allowlist/durable reservation; lưu job ID để resume GET; document artifact scoped và preview file/trang/bảng. Extraction luôn UNVERIFIED_EXTRACTION, không tự tạo canonical. Upload explicit manual chỉ parse/profile/review, không enqueue AI hoặc tiêu quota.

Files chính: backend config/ai_gateway/document_parser/repository/worker/api/contracts; frontend/src và E2E; tests/test_ai.py, tests/test_postgres.py; tools/create-document-fixtures.py, tools/check-document-acceptance.py và worker recovery helper. Quyết định và hướng dẫn được cập nhật trong tài liệu hiện có, Rules/AGENTS giữ nguyên.

Các sửa code trên đã có trong commit nghiệm thu source. Lần Final Acceptance sau chỉ dẫn thu hẹp **không phát hiện lỗi code mới cần sửa**; diff bàn giao hiện chỉ gồm báo cáo, hướng dẫn kiểm thử, README và ghi nhận phạm vi mới trong kế hoạch.

## B. Kiến trúc và handoff

Một modular monolith, một Compose project. PostgreSQL giữ scope, session, revisions, approval, job/attempt, audit/trace. Volumes cũ giữ raw, Parquet, document JSON. Không tạo database/server/Compose test project khác.

Giữ CanonicalDataset, DatasetProfile, SchemaDefinition, MappingRevision, EvidenceRef, JobStatus, WorkspacePolicy và artifact refs/DTO/OpenAPI. Bổ sung additive parser_allowed_sha256 mặc định rỗng vào policy JSONB; policy cũ đọc qua defaults. **Không cần migration SQL mới**; Alembic vẫn create_data_foundation (head), không sửa canonical lịch sử.

API mới GET /api/datasets/{id}/documents chỉ đọc cached extraction có authorization/checksum. Upload thêm request_ai_mapping mặc định true; false là lựa chọn workflow, không đổi parse semantics/cache. Xem [hợp đồng](DATA_CONTRACTS.md), [kiến trúc](ARCHITECTURE.md).

## C. AI và ngân sách thực tế

| Gate | Kết quả | Bằng chứng và giới hạn |
| --- | --- | --- |
| Gemini gemini-3.5-flash-lite | PASS LIVE đã ghi nhận | Production worker, Pydantic/semantic checks, c1 → reference_id, preserve string, không AI tự duyệt; lượt thu hẹp phạm vi đọc lại bằng chứng, không gọi mới |
| Gemini quota | 6/10 đã dùng, còn 4 | PostgreSQL reservations, không reset/tăng; gồm một live mapping mới trong đợt này |
| Qwen knowledge | BLOCKED LIVE / HOÃN theo chỉ định | HTTP 403, IP allowlist; adapter PASS MOCK, không probe lại, không ghi PASS LIVE |
| LlamaParse PDF | LIVE PARSE PASS / PARSE VALIDATION PASS / INTEGRATION PASS | 1 trang, 3 credits, 3 dòng/4 cột; ID/date/amount/blank khớp oracle |
| LlamaParse DOCX | LIVE PARSE PASS / PARSE VALIDATION PASS / INTEGRATION PASS | 1 trang, 3 credits; zero-prefix/comma-decimal/text khớp oracle |
| Document UI | PASS E2E | Chạy lại cached preview sau thu hồi quyền, cells đúng, không normalize, mobile không overflow |
| Parser tổng | 2 jobs / 2 trang / 6 credits | Cost_effective; reservations giữ biên trên 4 trang/12 credits, dưới trần được phép 20 |
| Sau thử | Parser tạo job OFF | Env và workspace đã thu hồi quyền; giữ key/history/reservations/artifacts; Gemini còn quyền trong quota cũ |

Account API trước thử xác nhận 9.980 credits và không pay-as-you-go/payment failure/usage alerts. Chỉ hai SHA256 fixtures tổng hợp được cấp phép, một PDF/một DOCX; server max_pages=2, không layout/form extras. [Giá](https://developers.llamaindex.ai/llamaparse/general/pricing/) và [REST contract](https://developers.llamaindex.ai/llamaparse/parse/guides/api-reference/) đã đối chiếu. Không dùng POST để thăm dò credits.

Phân biệt thời điểm: các lần gọi live trên đã thực hiện trước chỉ dẫn thu hẹp phạm vi trong cùng đợt nghiệm thu. Lượt Final Acceptance này chỉ đọc PostgreSQL và artifact cached, so checksum/oracle và chạy E2E MANUAL. **Không phát sinh request Gemini/LlamaParse mới**, không tìm key ở dự án khác, không reset hoặc tăng quota. Usage trace LlamaParse giữ 3 credits/tài liệu; parser creation OFF ở cả env và workspace. Số dư credits tài khoản hiện tại không truy vấn lại, không suy ra từ số dư trước thử.

Lỗi thật đã sửa và giữ bằng chứng: upstream ID pjb-* không phải UUID. PDF đã được nhận trước khi adapter lỗi; xác minh receipt duy nhất theo tên/tier/thời điểm rồi resume GET, **không POST lại PDF**, giữ attempt lỗi/reservation. Reader nghiệm thu ban đầu chỉ đọc Markdown table; response là HTML table có đủ cells. Bổ sung reader cho cách biểu diễn HTML, giữ nguyên oracle/values, không chữa số hoặc ID. DOCX tạo đúng một job riêng.

28 AI/policy contract cases nằm trong 79 offline tests, không cộng thêm vào tổng backend. Không có precision/recall đại diện hoặc OCR accuracy tuyệt đối từ hai tài liệu. Xem [AI integration](AI_INTEGRATION.md).

## D. Kiểm thử đã thực thi

| Nhóm/lệnh | Kết quả cuối |
| --- | --- |
| uv run pytest -q -m 'not integration' | Chạy lại: 79 PASS, 12 deselected, 0 FAIL; 11,34 giây |
| tools/test-postgres.ps1 -All | Chạy lại: 91 PASS, 0 FAIL/SKIP; 79 offline + 12 PostgreSQL integration; 11,60 giây |
| Ruff / mypy | PASS; typed backend 18 source files |
| TypeScript / ESLint / production build | PASS |
| Playwright GEMINI | Bằng chứng live trước chỉ dẫn thu hẹp: 9 PASS, 0 FAIL (20,3 giây); không chạy lại để giữ quota |
| Playwright MANUAL | Chạy lại: 9 PASS, 0 FAIL/SKIP (19,6 giây), không gọi AI; cùng catalogue, không cộng thành 18 cases |
| Document acceptance | Hai live/oracle/artifact PASS; rerun sau thu hồi quyền chỉ đọc cached refs |
| Worker recovery live | SIGKILL trong normalization 75.000 dòng; 2 attempts, đúng 1 canonical, raw/parsed giữ nguyên |
| Restart / force-recreate / frontend-only recreate | PASS, metadata/checksum mọi artifact giữ nguyên; proof phải xác minh lại |
| Scope/security | HttpOnly/SameSite, CSRF/Host, viewer denial, workspace isolation, upload validation, cloud/allowance guards PASS |
| Source/Git scan | Known local credentials/history, Markdown paths và diff check PASS; runtime/secrets không stage |

Một cảnh báo Starlette TestClient/httpx deprecation vẫn còn. Fault test chỉ dừng worker project này khi không có job khác active; lease của đúng job tổng hợp được cho hết hạn để không chờ 300 giây. Không sửa dữ liệu nghiệp vụ hoặc xóa volume.

So baseline được giao **87 backend / 8 E2E PASS**, hiện có **91 backend / 9 E2E PASS**: thêm bốn backend cases bảo vệ resume parser/Gemini mặc định/document pipeline/manual upload và một E2E document cached; không xóa case cũ. T01–T16 đã chạy lại; xem [ma trận test–bằng chứng](TESTING_GUIDE.md). T09 và các provider error/timeout/injection là **PASS MOCK**, không phải Qwen live. Các integration cases có CSV/XLSX multi-upload, viewer denial, scoped reuse, revisions/stale canonical, lease/fencing và atomic publication.

Snapshot cuối: 19 datasets/versions, 17 source tables, 36 schema/mapping revisions, 14 canonical, 46 jobs/50 attempts, 48 audits, 15 traces, 66 artifact refs, 18 projects/1 workspace. Bao gồm document JSON, raw/Parquet và policy/reservations; giữ nguyên qua cả ba kiểu restart/recreate. Dữ liệu tổng hợp E2E/recovery mới được giữ làm bằng chứng, không xóa dữ liệu cũ.

Responsive 1366/1440/1920, 768, 390; screenshots tổng hợp ở runtime bị ignore. DOCX renderer bundled Windows thiếu LibreOffice: không tuyên bố visual QA Word local; số trang/nội dung xác minh bằng provider có page cap/oracle và UI cached. PDF fixture đã render/kiểm tra. Không tuyên bố audit toàn bộ WCAG 2.2 AA.

## E. Docker và dữ liệu

Project duy nhất ai-reconciliation-studio: frontend/Nginx, backend, worker, postgres, cả bốn healthy. Chỉ publish **127.0.0.1:18180**, backend/PostgreSQL không có host port.

Giữ volumes ai-reconciliation-studio_postgres_data và ai-reconciliation-studio_artifacts, rollback images cũ đã kiểm tra. Backend/worker chung image; Docker image disk usage khoảng 553 MB backend, 90,5 MB frontend, 409 MB PostgreSQL. Không tạo môi trường trùng, global prune hoặc xóa volumes. GitHub không thay backup dữ liệu; disaster recovery chưa được tuyên bố đã kiểm chứng.

Sau lần recreate cuối, RAM tại thời điểm đo: backend 91,23/384 MiB, worker 82,9/512 MiB, PostgreSQL 30,59/256 MiB, frontend 10,06/128 MiB. Ổ C còn 130,8 GiB; các tag rollback backend/frontend vẫn được giữ. Đây là snapshot nhàn rỗi, không phải peak benchmark.

## F. Git/GitHub

Repository chính thức <https://github.com/MinhHoang1403/AI-Reconciliation-Studio.git>. Nền tảng/Gemini trước ở commit 286c0802a2807bb11e53a89cff882217215b90fc. Source nghiệm thu ở **2e73cad7b7dc1fed5211e699b45b84d0ccbf5ea4**, đã push `codex/data-foundation`. **Trước khi nhận chỉ dẫn thu hẹp**, commit này đã được fast-forward vào main, rồi main có commit báo cáo **061c5558eda4228b430ea4d7ec8558731bf0616f**. Đây là lịch sử đã xảy ra, không phải thao tác merge của lượt Final Acceptance mới; không reset/force-push để thay lịch sử.

Lịch sử Final Acceptance thu hẹp: commit báo cáo 4bde2111e03cf438124a73fe0abe66bc4a46fcd5 trên codex/data-foundation, không merge main trong nhiệm vụ đó. Nhánh local `codex/reconciliation` đã tạo trước chỉ dẫn mới không có commit riêng, không push và không dùng tiếp; giữ nguyên để tránh thao tác Git ngoài yêu cầu.

.vscode/ có sẵn ngoài phạm vi, giữ nguyên và không stage. .env, keys, uploads, Parquet, document fixtures, screenshots, runtime reports và volumes không vào Git. Rules.md/AGENTS.md giữ nguyên; quyết định provider/ngoại lệ ghi trong kế hoạch, không thay nghiệp vụ.

## G. Quyết định nghiệm thu và ngoại lệ

| MUST gate đã điều chỉnh | Trạng thái |
| --- | --- |
| CSV/XLSX → parse/profile → reviewed mapping → canonical/errors/evidence | PASS |
| AI Schema Understanding, grain/field proposals | PASS MOCK cho classify/infer_grain/unknown/constraints; review schema/grain qua E2E; không tuyên bố precision đại diện |
| Gemini mapping LIVE, Pydantic/semantic checks/approval | PASS |
| LlamaParse PDF/DOCX live + oracle + provenance + bounded cost | PASS trong phạm vi hai fixtures |
| Decimal, invalid/null/zero, lineage/revisions/scoped reuse | PASS |
| Local access, workspace/role/CSRF/Host, secret scan | PASS |
| Worker recovery, persistence, Docker health, FE E2E | PASS |
| Qwen live gốc | HOÃN theo chủ dự án, không PASS LIVE |
| Giai đoạn 1 | GIAI ĐOẠN 1 ĐẠT NGHIỆM THU — QWEN LIVE ĐƯỢC HOÃN THEO CHỈ ĐỊNH |

Ngoại lệ chỉ cho Qwen: tiêu chí gốc yêu cầu một mapping Qwen live, endpoint bị IP allowlist chặn, chủ dự án chấp nhận Gemini thay thế. Rủi ro còn lại: Qwen inference protocol/generation chưa được xác nhận live. Chỉ kiểm tra lại sau khi chủ dự án cấp quyền, giữ contracts/validators. Không dùng ngoại lệ để bỏ gate khác.

Giới hạn/NOT VERIFIED: Qwen inference chưa live PASS; OCR ký tự gây nhầm chưa thử trên ảnh scan đại diện; visual QA Word local bị thiếu LibreOffice; precision/recall đại diện, audit WCAG đầy đủ, public production và disaster backup/restore chưa xác minh. Một sheet là một table candidate; workbook phức tạp/formula cache/date serial cần review; ngày dùng format không mang offset sẵn và timezone IANA được duyệt; advanced transformation rules có typed API nhưng chưa có UI builder. Document không tự normalize/đối soát. Benchmark cũ 1k/10k/50k là scope hẹp, không phải precision/throughput đại diện. Không ghi PASS cho những giới hạn này.

## H. Sử dụng và chuyển tiếp

Mở [ứng dụng local](http://127.0.0.1:18180). Tạo/chọn project → upload CSV/XLSX → Smart Setup → xác nhận grain/locale/metric/currency → duyệt → chuẩn hóa → xem canonical/errors/nguồn. Bỏ chọn AI trong tùy chọn nâng cao để review thủ công, không tiêu quota. Tài liệu tổng hợp đã lưu có thể xem lại, không cần mở allowance.

Khởi động ./tools/start.ps1 -SkipBuild; build mới dùng ./tools/start.ps1, không nhập token. Không xóa volumes. Gemini còn 4 requests trong trần 10; LlamaParse tạo job OFF.

Các gate Giai đoạn 1 đã điều chỉnh đạt, đủ điều kiện bàn giao nền tảng làm đầu vào kỹ thuật cho Giai đoạn 2. **Quyết định lịch sử ở lần Final Acceptance thu hẹp: dừng, không merge main, chờ prompt Giai đoạn 2 riêng.** Quyết định đã được tuân thủ; không tự thay kế hoạch ba giai đoạn.

## I. Hợp nhất theo ủy quyền mới

Chủ dự án đã gửi prompt riêng cho phép hợp nhất Giai đoạn 1 vào main, kiểm thử trước push, tạo annotated tag data-foundation-accepted-20261028 rồi triển khai Giai đoạn 2 trên codex/reconciliation-engine. Merge giữ cả hai parent 061c555 và 4bde211; hai conflict ở mục F/H chỉ là lịch sử Git và quyền chuyển tiếp. Đối chiếu từng đoạn, giữ bằng chứng provider/quota/tests/known limits của báo cáo mới cùng lịch sử tích hợp source của main; không đổi code ứng dụng hoặc nghiệp vụ. Các mục A–H là snapshot nghiệm thu trước nhiệm vụ này. Giai đoạn 2 không được merge main và không bắt đầu Giai đoạn 3.

Kết quả sau hợp nhất: offline 79 PASS/12 deselected (4,33 giây), bộ đầy đủ PostgreSQL 91 PASS/0 FAIL/SKIP (15,26 giây), Ruff/mypy 18 files PASS, TypeScript/ESLint/build PASS, Playwright MANUAL 9 PASS/0 FAIL/SKIP (19,4 giây). T01–T16, AI policy/contract, mapping/normalization/provenance và access-control nằm trong các suite này; không gọi cloud. Gemini giữ 6/10, còn 4, đúng model mặc định; Qwen không probe, parser creation OFF.

Snapshot 66 artifacts của lần nghiệm thu trước được kiểm tra nguyên vẹn trước E2E. E2E tạo thêm bốn refs tổng hợp, snapshot mới 70 artifacts, 20 datasets, 15 canonical, 48 jobs/52 attempts và 50 audits; 15 traces không tăng. Restart, force-recreate đủ bốn service và frontend-only recreate đều PASS metadata/checksum; demo proof fail-closed trước xác minh lại. Compose giữ project/volumes và loopback cũ, 4/4 healthy. Secret/history/Markdown path scan và diff check PASS; .vscode/ giữ nguyên ngoài stage. Không thay đổi source Backend/Frontend/Compose trong merge.

Merge commit **78e68c08e60c7af2359e46def43196cf5b1a6dc1** đã push main; annotated tag **data-foundation-accepted-20261028** trỏ đúng commit này và đã push, không di chuyển tag. Cổng A đạt trước khi tạo/push codex/reconciliation-engine từ mốc này. Sau đó phát hiện một số đoạn tài liệu bổ sung qua PowerShell mất dấu tiếng Việt; sửa bằng bản vá UTF-8 và commit tiến tiếp, không viết lại lịch sử. Mã ứng dụng và kết quả kiểm thử ở tag không đổi.

## J. Giai đoạn 2 — Reconciliation và kết quả

Ngày thực thi: 28/10/2026. Source project/Compose/volumes cũ giữ nguyên, không worktree/bản sao/server test mới. Main sau sửa encoding tài liệu ở **cf7cb1f**; không chứa source Giai đoạn 2. Tag nghiệm thu 78e68c0 giữ nguyên; branch mới được tạo từ đúng tag trước khi có thay đổi triển khai. Source backend Giai đoạn 2 đã push **c88bd85**. Các commit UI/acceptance tiếp theo được đối chiếu remote trong bàn giao; không ghi hash tự tham chiếu.

### Chức năng và contracts

| Nhóm | Kết quả và bằng chứng |
| --- | --- |
| Domain/Rule DSL | Typed Plan/Contract/Run/MatchGroup/Member/Comparison/ExceptionCase/MetricSnapshot/VerifiedRun; same canonical/schema/profile/mapping refs. Order/OrderLine/FinancialEvent suggestions cần review, Settlement/Payout chỉ khi có source entity thật. Không suy Orders thành tiền quyết toán |
| Contract gate | Scope/project/revision/stale, fields/types/rigid IDs, grain/cardinality, signed aggregation, metric/basis/unit/currency/time basis, `[start,end)`/timezone, coverage/due/effective dates, evidence allowlist; approval actor/audit riêng |
| AI Planner | PASS MOCK và PASS LIVE: Gemini gemini-3.5-flash-lite trả PROPOSED có plan trên cặp vận đơn/giao nhận; validated và chưa tự approved. Manual builder không JSON, không cloud, approval bắt buộc |
| Matching | Composite keys và canonical normalized keys; duplicates không chọn tùy ý; 1:N/N:1 signed Decimal đúng grain; Internal chia platform cho hai pair riêng. Source rows không mất/reuse; full lineage. Fuzzy text/blocking bounded, score chỉ review, không greedy/auto fuzzy IDs |
| Financial comparison | LINKED giữ nguyên khi lệch tiền; exact Decimal, signed/absolute delta, approved rounding, absolute/relative tolerance; EQUAL khác WITHIN_TOLERANCE; null/invalid/mixed currency không thành zero |
| Independent verification | Dựng lại từ canonical nguồn, không import matcher; partition, membership/cardinality, amount conservation, comparisons, full provenance và deterministic IDs. Corruption tests từ chối publish; không KPI/export khi fail |
| Jobs/publication | Queue SKIP LOCKED/lease/fencing cũ, source locks/revision check trước publish, draft Parquet trước atomic DB refs/snapshot/cases. Crash/retry không tạo hai logical runs. Reclaimed AI không tự gửi lại delivery chưa rõ |
| Exception Inbox | Search/filter loại/trạng thái, sort, notes/review, hai nguồn/keys/delta/rule/source row. Resolve/dismiss có lý do/audit, không đổi comparison hoặc frozen snapshot. Không AI risk score |
| Dashboard/report | Light-blue App Shell cũ; 4 KPI, run history/period/source filters, server pagination, ECharts, denominators/excluded/CU/currency, empty/loading/partial states. Case mở hiện tại từ API, tách frozen count lúc run |
| Exports | CSV/XLSX từ đúng verified run/snapshot, summaries/details/quality/evidence/rules/source values. Read-back/API equality, formula injection guards, numeric negative Decimal và zero-prefix PASS |
| Smart Templates | Approved rule signatures gồm schema/mapping transforms/entity/scope/effectiveness; rebind kỳ/source mới thành PROPOSED cần fresh approval. Drift/stale/expired/unknown không chạy tự động |

Các modules mới: contracts/reconciliation, domain_templates, reconciliation_contracts/engine/planner/repository/jobs/api/exports, verification. AI Gateway chỉ tách transport typed dùng chung, mapping/Qwen contracts vẫn giữ regression. Migration **create_reconciliation** additive trên create_data_foundation, chỉ thêm năm bảng/indexes; không sửa canonical/source identifiers. Các routes và gate cụ thể tại [Data Contracts](DATA_CONTRACTS.md). UI thêm ReconciliationStudio/reconciliationTypes và E2E, không viết lại upload/parser/mapping/auth/queue.

### Bộ demo có oracle độc lập

Fixtures source và oracle literal ở tests/fixtures, không lấy matcher/LLM làm ground truth. `tools/check-reconciliation.py` chạy production upload → manual mapping approval → normalize → plan approval → queue matching/verification → CSV/XLSX; rerun reuse cùng refs, 0 cloud mặc định.

| Pair | Oracle và kết quả thật |
| --- | --- |
| Internal ↔ Shopee | 11 left records = 1 invalid + 5 outside scope + 5 inside; 0001/0003 equal, 0002 LINKED/AMOUNT_MISMATCH delta 10, 0004 missing, 0007 ambiguous duplicate; signed/abs variance 10 VND, full match 2/5 |
| Internal ↔ TikTok | 1:N 0005 gồm đủ hai dòng 20+30=50; 0001 equal, 0008 null counterpart NOT_COMPARABLE, 0009 missing; comparable variance 0, không tự điền null bằng 0 |
| Vận đơn ↔ giao nhận | 000701 equal, 000702 delta 2,75 VND, 000703 left-only, 000704 right-only; full match 1/3, abs variance 2,75; không logic hardcode ecommerce |

### Kiểm thử cuối

| Suite | Thực tế |
| --- | --- |
| Offline pytest | **104 PASS**, 17 integration deselected, 0 FAIL; bao gồm property permutations, exact arithmetic và domain/AI/export contracts |
| Full PostgreSQL/Linux | **121 PASS, 0 FAIL/SKIP** (104 offline + 17 integration), 17,16 giây; tất cả T01–T16 và T17–T35 thuộc scope đều có ma trận bằng chứng |
| Ruff/mypy | PASS; mypy 28 source files |
| Frontend TypeScript/lint/build | PASS; main chunk khoảng 366 kB, results/chart lazy chunk khoảng 484 kB, không đổi ngưỡng để che warning |
| Playwright MANUAL | **14 PASS, 0 FAIL/SKIP**, 32,2 giây: 9 foundation + 5 reconciliation/workflow/responsive. Không gọi cloud; không cộng lần replay thành cases mới |
| E2E thật | UI manual rule → validate → approve → run → verified cards/chart → exception evidence/review → XLSX download → reopen đúng run. Snapshot không đổi sau RESOLVED. Five-file pipeline kiểm qua production API |
| Security | Existing auth/CSRF/Host/workspace/upload/cloud OFF; thêm viewer-run denial, cross-project sources/group evidence, stale refs, unapproved rule, AI hallucinated fields/evidence/APPROVED, formula injection; không secret trong response/bundle/source scan |

Lỗi thật và nguyên nhân đã sửa: DuckDB Linux date timezone thiếu pytz; source picker có thể lấy lại nguồn mặc định khi hai lựa chọn ban đầu trùng; ECharts ghi đè accessible name; UI loading từng hiện count 0 trước response; PG helper tạo tests/tests và đọc stale source; encoding PowerShell làm mất dấu đoạn báo cáo merge. Có regression API/E2E/read-back thích hợp, không hạ validator hoặc sửa oracle để đạt. Cảnh báo Starlette/httpx deprecation giữ riêng, không phải failure.

### AI, Docker, tài nguyên và giới hạn

Gemini trước 6/10, thêm **1 attempt**, nay **7/10, còn 3**; policy/key hiện có, không reset/tăng. Planner lifetime task ceiling vẫn 2 attempts kể cả retry; live chỉ một bộ tổng hợp, không tuyên bố precision/recall. Qwen giữ **BLOCKED_EXTERNAL_DEPENDENCY — HTTP 403** và không probe. LlamaParse **OFF** tạo job, lịch sử 2 docs/2 pages/6 credits giữ nguyên. Regression/API demo/E2E còn lại 0 cloud requests.

Trace Planner live: VALIDATED_PROPOSAL, latency 3.060 ms, 1 HTTP attempt; provider trả 8.117 prompt tokens, 910 output tokens, tổng 9.027. Không suy ra chi phí tiền tệ khi chưa có đối chiếu billing/unit cost. Supplemental integration kiểm tra bộ lọc run theo nguồn/kỳ PASS, không tăng tổng catalogue 121.

Benchmark exact-key Windows/Ryzen 5 7535HS/16 GB, không GPU, ba subprocess/size: 1k/10k/50k **tổng records hai nguồn**, lần lượt 500/5k/25k groups. Matching p50/p95 ms 31,57/37,58; 268,01/433,78; 1723,77/1792,43. Verification p50/p95 17,06/19,02; 230,28/257,09; 1315,23/1521,31. Peak MiB 38,68/89,10/317,06; không fuzzy/review/cloud trong benchmark. Không đo toàn HTTP/upload/write/export/render hoặc workload phức tạp, không cam kết 50k records mỗi source hay accuracy 99%.

Giới hạn còn lại: fuzzy chỉ review, chưa hiệu chỉnh threshold/precision hoặc blocking recall đại diện; N–M subset sum/FX/phí marketplace/Assistant chat ngoài scope. UI builder một metric chính và một scope filter/side, API có tối đa 5 metrics và 8 filters; evidence drawer preview 100 records/source, full member lineage trong result/export. Excel arithmetic có giới hạn 15 digits dù Decimal numeric lexemes/snapshot strings được giữ đúng. Text vượt 32.767 ký tự/ô hoặc control không biểu diễn được trong XML trả EXPORT_CELL_LIMIT, không cắt/sửa giá trị; regression kiểm chứng guard này. Cỡ lớn nhiều cột/group/export và concurrent workload chưa benchmark production. Không tuyên bố public production, full WCAG audit, OCR đại diện hoặc disaster backup/restore PASS. Archive metadata trước migration đọc danh mục được, chưa có restore drill. Những việc này cần được cân nhắc khi giao hardening/Giai đoạn 3; không tự triển khai Giai đoạn 3 trong nhiệm vụ này.

Kết luận kỹ thuật theo scope đã giao: contracts, planner/manual fallback, exact/group/review-only fuzzy, Decimal/verification, Dashboard/Exception Inbox, export và reuse có kiểm chứng. Bàn giao source feature branch để chủ dự án xem; **không tự merge Giai đoạn 2 vào main**.

Persistence cuối PASS cả restart, force-recreate bốn services và frontend-only recreate, fail-closed demo proof trước re-verification. Snapshot: 1 workspace/23 projects, 28 datasets/versions, 26 tables, 54 schemas/mappings, 23 canonical, 79 jobs/83 attempts, 83 audits/16 traces, 7 plans, 6 approved contracts, 6 runs, 22 cases, 8 export metadata; checksum **102 foundation artifacts + 6 match artifacts + 8 export files** bảo toàn. Bao gồm quota/policy/approvals/snapshots/notes, không xóa volumes/dữ liệu. Lần kiểm tra gần nhất giữ đủ 4/4 healthy, loopback 18180, không sửa Compose. Backend image khoảng 668 MB, frontend 91,2 MB; các tag accepted và rollback của nền tảng vẫn giữ, không dọn global Docker hoặc tài nguyên project khác. Ổ C còn khoảng 128,9 GiB tại thời điểm đo. Không coi Git/tag thay backup dữ liệu.

RAM nhàn rỗi sau recreate cuối: backend 112/384 MiB, worker 83,75/512 MiB, PostgreSQL 54,89/256 MiB, frontend 12,06/128 MiB; không phải peak workload. Sau chốt guard export/grain và recreate backend/worker, kiểm tra lại snapshot trên vẫn PASS; quota vẫn 7/10, task planner 1 attempt, parser 2 reservations/OFF. UI screenshots desktop/mobile đã xem trực tiếp, đủ cards/chart/rows, không ảnh secrets. Chưa audit WCAG đầy đủ.

Chốt chặn cuối bổ sung và kiểm tra: group aggregation không được dùng cùng grain với bản ghi tham chiếu để hợp thức hóa duplicate report rows; grain chi tiết phải được xác nhận riêng. Chỉ approved SUM_SIGNED ở 1:N/N:1 đúng grain mới chạy. Guard export cell giữ null/negative/precision semantics. Tài liệu UTF-8, đường dẫn Markdown, diff và known-key/history scan được kiểm tra trước push. .vscode/ giữ nguyên untracked, không stage; .env/raw/Parquet/archive/runtime reports/screenshots không commit. Kết thúc sau commit/push và báo cáo, chờ chủ dự án review; không bắt đầu Giai đoạn 3.

## K. Kiểm toán bổ sung và sửa lỗi Giai đoạn 2

Ngày: **28/10/2026**. Theo prompt kiểm toán riêng, tham chiếu **ab8e9f4f8fb85241c610322cbbea1e4f83df8441**; chỉ sửa sai lệch đã tái hiện và bổ sung regression. Branch `codex/reconciliation-engine`; main giữ **cf7cb1f3424aa61badf3df312b365496e8dfe1ef**. Không đổi kế hoạch ba giai đoạn, matcher/verifier, golden oracle, công thức, schema dữ liệu hoặc lịch sử artifact. Không tạo branch/worktree/Compose project khác.

### Phát hiện, nguyên nhân và kết quả

| Phát hiện | Kết luận | Nguyên nhân | Sửa đổi | Test |
| --- | --- | --- | --- | --- |
| AI Planner pre-validation | **BUG — đã sửa** | API nhận ReconciliationPlan hoàn chỉnh rồi chạy execution validator, chặn chính các keys/metrics cần AI tìm | Input PlanningRequest nhỏ, gate context refs/quyền/stale/facts trước AI; typed suggestions hoặc complete plan có semantic validation sau AI. Giữ legacy input/job, không làm yếu executable contract, không tự approve | Tái hiện 422 với nguồn không keys trên bản cũ; PG nhận 202 sau sửa. Mock khác field IDs đề xuất đúng pair; giả field/evidence/basis/cardinality hoặc đổi scope/period bị chặn; thiếu facts NEEDS_REVIEW; chưa approved không chạy; durable quota hết 0 cloud calls và manual fallback PASS |
| Source evidence c1 | **BUG — đã sửa** | UI hardcode c1 cho mọi field và đưa JSON vào thông báo | EvidenceRef từ đúng MappingRevision lịch sử và source provenance; mở từng field input qua API evidence cũ, bảng file/sheet/row/column/raw value cạnh canonical value; không API row-detail mới | Regression bản cũ thiếu field_evidence; workbook hai sheet ID c1/amount c3, 000702, 1:N nhiều members; viewer đọc được/không review, foreign project group 404. E2E click tiền CSV mở c4/12.75 thật, không c1 |
| Readiness duplicate scope | **BUG — đã sửa** | Chỉ loại invalid và filter, chưa phân vùng theo ngày hoặc invalid keys/date | Dùng record_partition của engine; duplicate_population=IN_SCOPE, đếm riêng invalid/out-of-scope/in-scope/coverage_complete; verifier vẫn độc lập | Bản cũ báo 1 duplicate do tháng trước; sau sửa 0. Thêm duplicate cùng kỳ, filter ngoài scope, missing date/invalid key, incomplete coverage PASS |
| Automation KPI | **ACCEPTED DEFINITION**, có GAP về nhãn — đã làm rõ | Công thức §20 đo eligible CU được phân loại verified không cần quyết định row-level, có thể gồm UNMATCHED; nhãn Mức tự động hóa dễ bị hiểu là đã đối soát/giải quyết xong | Giữ MetricSnapshot/công thức/revision cũ; UI **Tự động phân loại**, mô tả gồm thiếu đối ứng/lệch đã verified; export giải thích cùng định nghĩa. Không thêm KPI trùng | Oracle 5 eligible CU: 4 automatic classifications, 2 full matches, 1 review; denominator 0 N/A. Review không sửa financial snapshot/comparison; API/CSV/XLSX equality PASS |
| Export after review | **ACCEPTED BEHAVIOR**, DESIGN GAP về thời điểm — đã sửa | Cache bất biến theo run/format/revision, states/notes lấy lần tạo đầu nhưng không ghi rõ as-of | Report-2 thêm generated-at/FIRST_GENERATION và giải thích; API/UI cùng timestamp/thông báo. Đọc states/notes trong REPEATABLE READ. Report-1/bytes cũ giữ nguyên | Hai PG cases CSV/XLSX: export → RESOLVED → export lại cùng ID/bytes, states OPEN trong file ban đầu, timestamp Summary=API, snapshot không đổi. Không biến RESOLVED thành EQUAL |
| UX setup | **IMPROVED**; giới hạn nhỏ còn công bố | Rule builder lộ nhiều thuật ngữ, default tháng 10/2026 và UTC có thể bị dùng mà chưa xác nhận | Bước nguồn → AI chuẩn bị → duyệt → chạy; khóa/chỉ tiêu thủ công trong details; summary/missing requirements; bỏ default period/timezone, checkbox xác nhận scope trước validate/save/approve; manual fallback khi provider lỗi | Playwright MOCK hỏi AI khi không common key, hiển thị đề xuất review-only và chặn approve; hết quota vẫn mở manual. T35 nhập ngày/timezone rõ, đợi đúng run_id mới VERIFIED; setup/results responsive 390/768/1366/1440/1920 PASS |

Ngoài sáu mục: khi mở rộng từ `mypy backend/studio` sang cả `mypy backend`, tái hiện hai lỗi Column thiếu type parameters trong migration đã có. Chỉ hoàn thiện return annotations `Column[Any]`, không đổi DDL/revision; AST đối chiếu runtime bodies giống hệt. Không thêm migration hoặc sửa dữ liệu. E2E trước đây có thể kiểm run cũ đang hiển thị trong khi job mới chạy; đã siết chờ đúng run_id từ POST và trạng thái VERIFIED trước so KPI/evidence/export. Đây là sửa khoảng trống kiểm thử, không sửa oracle cho test qua.

### Kết quả kiểm chứng thực tế

| Lệnh/suite | Kết quả |
| --- | --- |
| `uv run pytest -q -m 'not integration'` | **120 PASS / 0 FAIL / 0 SKIP**, 23 integration deselected; 3,97 giây |
| `tools/test-postgres.ps1 -All` | **143 PASS / 0 FAIL / 0 SKIP**, 44,91 giây = 120 offline + 23 PG. T01–T35 thuộc phạm vi, Hypothesis, corruption verifier, authorization/CSRF, worker/recovery, export read-back trong suite này |
| Migration sau hoàn thiện type annotations | Chạy riêng regression additive-preservation trên backend image mới: **1 PASS**, 10 deselected, 2,75 giây; không cộng vào catalogue 143 |
| `uv run ruff check backend tests tools` | PASS |
| `uv run mypy backend/studio`; `uv run mypy backend` | PASS: 28 application files và đầy đủ 31 backend/migration files sau sửa annotations |
| Frontend TypeScript / ESLint / production build | PASS; main khoảng 366 kB, lazy reconciliation/chart 489 kB, không đổi ngưỡng warning/dependency |
| Playwright MANUAL | **15 PASS / 0 FAIL / 0 SKIP**, 35,2 giây: 9 foundation + 6 reconciliation. Một case planner hoàn toàn MOCK, không provider/job thật. Không cộng các lần chạy lại thành cases mới |
| Historical integrity | Toàn bộ metadata/approvals/revisions/notes/snapshots và checksum **102 foundation + 6 match + 8 export** ở baseline ab8e9f4 giữ nguyên; dữ liệu E2E bổ sung riêng, không ghi đè cũ |
| Persistence | PASS restart, force-recreate bốn services và frontend-only recreate; mỗi lần proof invalidated/fail-closed rồi xác minh loopback; metadata/checksums giữ nguyên |
| Repository/security | Known credential/history scan, Markdown paths/UTF-8, diff checks PASS; không secrets/runtime/data đưa lên Git |

So baseline **121 backend / 14 E2E**, hiện **143 backend / 15 E2E**: thêm 16 offline + 6 PG + 1 E2E case, giữ mọi case cũ. Cảnh báo Starlette/httpx deprecation và Node color-env vẫn có, không phải failure. Trong quá trình chạy, tests đã tái hiện lỗi trên bản cũ; một lần helper dùng trùng idempotency key khác project đã sửa key của helper theo project, một assertion URL evidence cần decode dấu `:`. Sau phiên bị gián đoạn demo proof hết hiệu lực, E2E bị chặn đúng LOCAL_DEMO_NOT_VERIFIED; xác minh lại deployment rồi chạy toàn bộ PASS. Không tắt auth, tăng timeout hoặc hạ validator để qua test.

### AI, Docker và bảo toàn dữ liệu

Đọc PostgreSQL trước/sau kiểm toán: Gemini **gemini-3.5-flash-lite, 7/10 đã dùng, còn 3**, task Planner **1 attempt** trong trần 2; không reset/tăng quota và **0 request cloud mới**. Prompt `reconciliation-planning-2` **PASS MOCK/CONTRACT**, **NOT VERIFIED LIVE** theo chỉ định không gọi mới; PASS LIVE cũ chỉ thuộc prompt `reconciliation-planning-1`, không chuyển bằng chứng sang revision mới. Qwen **HOÃN/BLOCKED HTTP 403**, không probe. LlamaParse tạo job **OFF**, 2 reservations/2 documents/2 pages/6 credits lịch sử, không request mới.

Snapshot persistence cuối: **1 workspace, 26 projects, 31 datasets/versions, 29 source tables, 60 schemas/mappings, 26 canonical, 94 jobs/98 attempts, 103 audits/16 traces, 12 plans, 11 contracts, 11 runs, 37 cases, 12 export metadata**; checksum **114 foundation artifacts + 11 match artifacts + 12 export files**. Đã so baseline cũ theo từng ID/hash để bảo vệ cả history trong khi E2E thêm dữ liệu tổng hợp. Không xóa volumes, results cũ hoặc files export report-1.

Một Compose project `ai-reconciliation-studio`; 4/4 healthy, chỉ `127.0.0.1:18180`, backend/PG không publish host port. Giữ đúng hai persistent volumes, không thêm services/dependencies. Backend/worker chung image khoảng 668 MB, frontend 91,2 MB; accepted/rollback images cũ giữ lại, không global prune hoặc tác động project khác. Snapshot RAM sau kiểm thử khoảng backend 125,4/384 MiB, worker 101,3/512, PG 49,48/256, FE 10,61/128; C còn 130,1 GiB, không coi là peak benchmark. Rebuild/recreate annotation-only backend sau đó không thay runtime/DDL; persistence kiểm tra lại **PASS** trước bàn giao.

### Files, Git và giới hạn

Backend: `contracts/reconciliation.py`, `reconciliation_api.py`, `reconciliation_contracts.py`, `reconciliation_planner.py`, `reconciliation_jobs.py`, `reconciliation_exports.py`; migration `create_reconciliation.py` chỉ type annotations. Tests bổ sung trong `test_reconciliation_reporting.py`, `test_reconciliation_postgres.py` và `frontend/e2e/reconciliation.spec.ts`. Frontend chỉ `frontend/src/ReconciliationStudio.tsx` và `frontend/src/reconciliationTypes.ts` hiện có. Tài liệu README, AI_INTEGRATION, ARCHITECTURE, DATA_CONTRACTS, TESTING_GUIDE và báo cáo này; Rules/AGENTS/PROJECT_PLAN, engine/verifier và golden fixtures không đổi.

Đã commit/push nhóm backend **d9b51270cffe0006c807b452062d88e92d8a41a3**, nhóm type-check **d395383dadbacc36f4ba9a6c835704920aac4a63** lên đúng origin/codex/reconciliation-engine. Commit UI/báo cáo sau đó sẽ được báo hash trong bàn giao, không ghi hash tự tham chiếu. Remote đã xác minh đúng repository; không force-push hoặc merge main. `.vscode/` có sẵn giữ nguyên ngoài stage; mọi runtime files/screenshots/fixtures workbook/dumps/.env không commit.

Giới hạn: prompt planner mới chưa thử live; fuzzy vẫn chỉ review/chưa có đánh giá precision/recall đại diện; không FX/phí marketplace/N–M/Assistant. UI builder một metric chính và một filter mỗi phía; coverage thực tế vẫn cần người dùng biết/xác nhận. Evidence preview tối đa 100 members mỗi source, 100 source rows/record, UI 20 ô/lần mở có thông báo; full member lineage ở result/export. Report-1 cũ không có review timestamp thì trả null/thông báo, không suy diễn hoặc ghi lại. CSV/XLSX tạo vào thời điểm khác nhau có thể chứa states/notes khác nhau, nhưng financial metrics luôn từ cùng immutable VerifiedRun. Excel arithmetic 15 digits, cell length/control guards giữ nguyên. Không tuyên bố production/WCAG đầy đủ/DR restore/accuracy đại diện đã PASS.

**Kết luận:** các lỗi được giao đã tái hiện/sửa và regression đạt; không phát hiện cần sửa/xóa kết quả lịch sử. Đủ bằng chứng kỹ thuật cho chủ dự án xem xét nghiệm thu chính thức Giai đoạn 2 trong phạm vi đã công bố. **DỪNG sau commit/push báo cáo; không merge main, không bắt đầu Giai đoạn 3.**

## L. Final Acceptance, hợp nhất và vận hành — 29/10/2026

Ủy quyền mới của chủ dự án cho phép nghiệm thu, merge `--no-ff`, chia sẻ cấu hình VS Code an toàn, tag `reconciliation-engine-accepted-20261029`, deploy main và cleanup images đúng project; chỉ nghiên cứu Argon, không tích hợp hoặc triển khai Giai đoạn 3. Các lệnh dừng ở mục K là lịch sử của nhiệm vụ trước. Git đầu nhiệm vụ: feature **e025094139db217b3788d4b446d1eaab23b97a5c**, main **cf7cb1f3424aa61badf3df312b365496e8dfe1ef**, ahead 5/behind 0, tracked tree sạch; chỉ `.vscode/settings.json` untracked. Không phát hiện commit remote mới chưa đối chiếu.

### Gate 1 — source/runtime: PASS

Image cũ thiếu revision ứng dụng; frontend kế thừa revision của Nginx, không được dùng làm bằng chứng Git của dự án. Dựng lại từ tracked source sạch bằng Compose chính với biến build-only `BUILDX_GIT_LABELS=full`. Buildx gắn OCI source/revision chính xác; không sửa Dockerfile, Compose, runtime env hoặc code nghiệp vụ. Created timestamps của image config/layers có thể được giữ từ cache, không diễn giải chúng là thời điểm chạy lại build. Container IDs/creation times, labels, immutable image identifiers và manifest checksums được lưu trong evidence runtime bị ignore.

| Thành phần | Source revision | Immutable image ID tại Gate 1 | Runtime |
| --- | --- | --- | --- |
| Frontend | e025094139db217b3788d4b446d1eaab23b97a5c | sha256:57a48c3e6ff1bedf63162b71e3a8d1292af421d177a4e7afa50dedfd31a54979 | Healthy; 4 HTTP-served files khớp SHA256 production build |
| Backend | e025094139db217b3788d4b446d1eaab23b97a5c | sha256:c966a65d026417d8e2a7e7662f8ab888aca582fd1a59aa319a12f6abd396f553 | Healthy; 34 tracked files khớp SHA256 local |
| Worker | Cùng backend | Cùng backend | Healthy; 34 tracked files khớp, heartbeat/queue dùng chung code |
| PostgreSQL | N/A; postgres:18.3-alpine, immutable image | sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7 | Healthy; volume hiện có, không publish host port |

Sau đó chỉ bổ sung assertions/export downloads trong Playwright và tài liệu nghiệm thu; application files không đổi so với e025094. Đây không phải tuyên bố image cũ khớp revision chỉ vì healthcheck xanh.

### Gate 2 — regression không cloud: PASS

| Kiểm tra | Kết quả thực tế |
| --- | --- |
| Offline pytest | **120 PASS, 0 FAIL/SKIP**, 23 integration deselected; 8,07 giây |
| PostgreSQL `tools/test-postgres.ps1 -All` | **143 PASS, 0 FAIL/SKIP**, 50,19 giây = 120 offline + 23 integration; migration preservation đã nằm trong suite, không đếm thêm |
| Ruff; mypy backend | PASS; 31 backend/migration source files |
| Frontend TypeScript; ESLint; production build | PASS; lockfiles/dependencies không đổi |
| Playwright MANUAL | **15 PASS, 0 FAIL/SKIP**, khoảng 1,1 phút; gồm 9 foundation và 6 reconciliation, responsive 390/768/1366/1440/1920 |
| Planner reconciliation-planning-2 | **PASS MOCK/CONTRACT — LIVE NOT VERIFIED**; incomplete request, khác IDs, fake evidence/basis/cardinality/scope, missing coverage, unapproved execution, exhausted quota/manual fallback |
| Security/invariants | T01–T35, Hypothesis, verifier corruption, membership/conservation, atomic publication, permissions/CSRF/Host/workspace isolation, stale/reuse/idempotency/worker recovery và export-after-review trong các suite trên |

Giữ nguyên golden oracle/validators và timeouts. Starlette/httpx deprecation, Node color-env warning vẫn còn; không phải FAIL. Không gọi Qwen hoặc Gemini/LlamaParse live. Baseline 143 backend/15 E2E không tăng số cases chỉ vì chạy lại hoặc thêm assertions vào T35.

### Gate 3 — UI/oracle/persistence: PASS

Playwright thật trên Nginx production: chọn hai canonical → nhập/xác nhận kỳ, UTC và coverage → readiness → manual proposal → approval → POST run → đợi đúng run_id mới VERIFIED → KPI/eligible denominator → AMOUNT_MISMATCH → cột tiền **c4**, sheet CSV, dòng **3**, raw/canonical **12.75** ↔ **10.00**, delta **2.75 VND**, ID **000702** → RESOLVED → comparison và MetricSnapshot không đổi → xuất **CSV và XLSX qua UI** → kiểm download SHA256 → reload đúng run. Đọc lại cả hai files bằng csv/openpyxl xác nhận nguyên MetricSnapshot JSON, zero-prefix strings, timestamp Summary=API và FIRST_GENERATION scope; XLSX không có công thức tính KPI. Screenshots desktop/mobile đã kiểm tra; không đồng nghĩa audit WCAG toàn diện.

Đối chiếu API production/cached immutable runs với oracle literal có sẵn: Shopee 2/5 full match, signed/abs 10 VND, invalid 1/outside 5, 7 cases; TikTok 0005 có đúng hai members 20+30=50, 0008 NOT_COMPARABLE, signed/abs 0, 3 cases; giao nhận 1/3 full match, delta 2.75, 3 cases. Mọi source member xuất hiện đúng một lần và tổng membership khớp row_count từng canonical; CSV/XLSX của cả ba pairs khớp Snapshot/checksum/as-of. Lookup oracle dùng đầy đủ platform/carrier + ID, không nhầm cùng suffix ID giữa hai platform. Multi-sheet c1 identifier/c3 amount, 1:N/N:1 và incomplete coverage có bằng chứng PG/golden; khác field IDs và quota fallback là MOCK/contract, không giả thành live AI.

Inventory đầu nhiệm vụ thực tế: **114 foundation artifacts, 11 match artifacts, 12 export files**, 31 datasets/26 canonical, 62 schemas/mappings, 95 jobs/99 attempts, 104 audits/17 traces. Một số metadata tăng từ trước nhiệm vụ so với mốc K; chụp hiện trạng thật, không sửa lịch sử cho khớp báo cáo cũ. Sau kiểm thử: **118 foundation + 12 match + 20 export files**; 27 projects/32 datasets, 30 tables, 64 schemas/mappings, 27 canonical, 106 jobs/110 attempts, 109 audits/17 traces, 13 plans/12 contracts/12 runs/40 cases. Tất cả IDs/metadata/checksum thuộc inventory đầu giữ nguyên; refs tổng hợp mới được phân biệt riêng.

Restart, force-recreate cả bốn services và frontend-only recreate đều **PASS**, proof local bị vô hiệu đúng thiết kế rồi xác minh lại loopback. Một Compose project, bốn services healthy, hai volumes cũ giữ nguyên; chỉ publish **127.0.0.1:18180**. Không xóa dữ liệu, job đang chạy hoặc volumes. Gemini trước/sau **7/10**, còn **3**, Planner attempt **1**, parser reservations **2**; global/workspace trần **10**, cloud request delta **0**, parser creation OFF ở cả env/policy. Qwen HTTP 403 vẫn hoãn, không probe. Prompt mới không có live inference trong nhiệm vụ này.

**GIAI ĐOẠN 2 ĐẠT NGHIỆM THU KỸ THUẬT TRONG PHẠM VI MVP ĐÃ CÔNG BỐ.**

Ngoại lệ/giới hạn tiếp tục: Qwen LIVE BLOCKED do IP; Planner mới LIVE NOT VERIFIED; fuzzy chỉ review, precision/recall đại diện chưa đo; không FX/phí marketplace ngoài scope; chưa production security audit toàn diện/DR restore drill; không Assistant Giai đoạn 3. Không tuyên bố production-ready. Kết quả Git/tag/deploy/cleanup và nghiên cứu đã thực hiện được ghi bên dưới.

### Hợp nhất GitHub và cấu hình chia sẻ

Commit bằng chứng/tests nghiệm thu **7dfcb83319ba6c07b5f78fe34105b95c5e577ead** đã push feature branch. Merge `--no-ff` **2a880cc7a7cd92faf32e9885b34cf5f93723ff53** có hai parents cf7cb1f và 7dfcb83, không conflict/squash/rebase. `git diff` giữa merge result và accepted feature tree rỗng. Trước push main chạy lại 120 offline PASS (8,03 giây), Ruff/mypy 31 files/TypeScript/ESLint/source scan PASS; không đếm replay thành tests mới. Main đã push/fetch và local/remote khớp; cả tag Giai đoạn 1 lẫn e025094 là ancestors.

Inventory `.vscode/` đúng một file **settings.json** (không launch/tasks/extensions/private metadata). Đọc toàn bộ, parse JSON và secret scan: chỉ `python.terminal.useEnvFile: true`, không credentials/commands/env values/absolute paths; chuẩn hóa indentation hai spaces, giữ nguyên hành vi. Commit riêng **fcb54343c38bebb7f45e929bf289b6391d526319**, đã push main. Không tạo file config thừa hoặc ignore secrets bằng tên chung để che file chưa kiểm tra. Working tree sạch sau commit; mọi runtime evidence nằm ngoài Git.

### Tags và branches sau hợp nhất

| Mốc | SHA đã push/xác minh |
| --- | --- |
| Main merge | **2a880cc7a7cd92faf32e9885b34cf5f93723ff53** |
| VS Code config | **fcb54343c38bebb7f45e929bf289b6391d526319** |
| Main tại mốc nghiệm thu/deploy | **be6b8a067ca052ea989a029a15558b0fd5ee48ef** |
| Annotated `data-foundation-accepted-20261028` | Target **78e68c08e60c7af2359e46def43196cf5b1a6dc1**, giữ nguyên |
| Annotated `reconciliation-engine-accepted-20261029` | Target **be6b8a067ca052ea989a029a15558b0fd5ee48ef**, đã push; không di chuyển |

Xác minh PR đang mở bằng GitHub CLI: **0**; không stash, chỉ một worktree tại repo chính, mọi tips được dọn là ancestors của main. Xóa remote/local `codex/reconciliation-engine` và `codex/data-foundation`, local `codex/reconciliation` bằng normal delete sau khi tag/main đã push. Không force-delete, không xóa history/tags hoặc branch có commits riêng. Local/remote chỉ còn main và origin/HEAD. Remote chính thức đã đối chiếu trước mỗi push.

Commit nghiên cứu/bàn giao tiếp theo trên main chỉ thay Markdown theo ủy quyền bước 21; vì vậy final main HEAD sẽ tiến sau tag. SHA commit tài liệu cuối được báo cùng kết quả push, không tự ghi SHA của chính commit vào nội dung của nó. **Tag và runtime giữ mốc be6b8a0**; application/dependencies/Compose không đổi giữa mốc deploy và main sau nghiên cứu.

### Deploy main và kiểm tra sau merge: PASS

Build từ main sạch be6b8a0 bằng Compose hiện có và OCI Git labels; backend/worker dùng cùng image. Kiểm lại **34 source/build files mỗi backend/worker** và **4 production files qua HTTP**: SHA256 khớp source/build. Không có `.env` trong backend image. OCI revision của cả hai app images là be6b8a0, source label đúng repository này.

| Image | Immutable ID | Hành động |
| --- | --- | --- |
| Backend/worker current | `sha256:decbc4ccf59fb822c6d27397bfd52d9701351a234d7c46814a8e667d1cc75477` | KEEP; accepted main |
| Frontend current | `sha256:1dedf4ed08e668a4cde9d56024f541c02d588ffc2e99fa87d47af2c4ee2ba5d1` | KEEP; accepted main |
| Backend `rollback-e025094` | `sha256:c966a65d026417d8e2a7e7662f8ab888aca582fd1a59aa319a12f6abd396f553` | KEEP; bộ đã qua Gate1–3 |
| Frontend `rollback-e025094` | `sha256:57a48c3e6ff1bedf63162b71e3a8d1292af421d177a4e7afa50dedfd31a54979` | KEEP; bộ đã qua Gate1–3 |
| PostgreSQL current | `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` | KEEP; không thay image/volume |

Trên image accepted main chạy lại toàn PostgreSQL suite: **143 PASS, 0 FAIL/SKIP, 44,42 giây**. Smoke T35 thật: **1 PASS, 15,9 giây**, cả CSV/XLSX; đây là replay một case trong baseline15, không phải tăng thành16 E2E. Một lần filter `^T35:` chọn0 tests vì full test title có prefix; sửa lệnh thành `T35:` và chạy thành công, không tính lần chọn0 là PASS. Đọc lại cả hai UI downloads và oracle ba cặp trên API production: PASS. Không phát hiện lỗi ứng dụng mới cần đổi code; chỉ tăng độ chặt assertions/export coverage và độ rõ bằng chứng triển khai, không đổi golden oracle.

Sau smoke trên main: **118 foundation artifacts, 13 match artifacts, 22 export files**; 27 projects/32 datasets/versions, 30 tables, 64 schemas/mappings, 27 canonical; 109 jobs/113 attempts, 112 audits/17 traces; 14 plans/13 contracts/13 runs/43 cases/22 export metadata. Inventory lịch sử đầu nhiệm vụ vẫn là subset nguyên IDs/metadata/hash; snapshot mới giữ toàn bộ hiện trạng sau tests. Không có job đang chạy khi kiểm persistence/cleanup.

### Docker cleanup: PASS

Inventory có IDs/tags/creation times/project labels và references của cả running/stopped containers. Giữ current và gắn tên rõ cho cặp rollback e025094 đã kiểm chứng trước khi xóa legacy images. Chỉ bốn IDs dưới đây có project label `ai-reconciliation-studio`, tất cả tags thuộc project, không còn container tham chiếu, không nằm trong protected set:

| Image cũ | Immutable ID | Hành động/lý do |
| --- | --- | --- |
| Backend `accepted` cũ | `sha256:2025e07ea2514ce39e8bad04bb6bb32687085305fbe0c7f0fa92543c50a24a86` | DELETE; đã có current/rollback xác minh |
| Frontend `accepted` cũ | `sha256:44de606ed1f2fb33c6dbba4c0efc189fc109c39fb9d97669a25678bd94ef1190` | DELETE; đã có current/rollback xác minh |
| Backend `rollback` cũ | `sha256:ed4a4bbf3b9d9991bc58ccd9edae6c5f58b9403153475ed3bbe661dd8ad9d939` | DELETE; cặp rollback e025094 thay thế |
| Frontend `rollback` cũ | `sha256:aa7c869df77a24c3f1e3fec33020e0f5b2e245587d846872dd9a03223abcc9aa` | DELETE; cặp rollback e025094 thay thế |

Xóa từng ID bằng `docker image rm`, **không force/prune**. 47 image ngoài project/không xác định chủ sở hữu trong inventory trước dọn đều còn; không công bố tên/metadata dự án khác. Không xóa containers, volumes, model cache hoặc build cache. Việc xóa legacy image tag `accepted` không xóa Git tag Giai đoạn 1.

| Số đo thực của Docker host | Trước → sau |
| --- | --- |
| Image count | **55 → 51** |
| `docker system df` Images Size | **39,75 → 39,38 GB**, giảm khoảng 0,37 GB theo cách báo của Docker |
| Build Cache Size | **48,18 → 48,18 GB**, giữ nguyên |
| Containers / named+anonymous volumes tổng host | **31 → 31 / 36 → 36**, không xóa |

Không cộng virtual sizes để tuyên bố dung lượng giải phóng; do layers/cache còn chia sẻ, **số physical filesystem blocks/VM disk đã thu hồi là NOT VERIFIED**. Không dọn cache toàn host để làm số liệu đẹp hơn. Hai volumes `ai-reconciliation-studio_postgres_data` và `ai-reconciliation-studio_artifacts` giữ nguyên. Sau dọn **4/4 healthy**, loopback18180/demo session/API/worker/Nginx/PostgreSQL hoạt động; snapshot metadata/artifact bytes khớp hoàn toàn, UI report read-back và ba oracle PASS. Gemini **7/10**, planner1/parser2 reservations giữ nguyên; cloud delta 0.

Evidence local bị ignore: `runtime/release-source-manifest.json`, `runtime/release-gate1.json`, `runtime/release-main-runtime.json`, `runtime/release-docker-inventory.json`, `runtime/release-before-cleanup.json`, `runtime/release-cleanup-result.json`, UI downloads/manifest và screenshots. Bản baseline metadata/artifact hashes nằm ở artifact volume `verification/acceptance-20261029-before.json`, snapshot sau smoke ở `verification/persistence.json`. Đây là kiểm chứng persistence, **không thay backup/restore database**; không commit nội dung runtime hoặc inventory dự án khác.

### AI và nghiên cứu Argon

| Mục | Kết quả ngày 29/10/2026 |
| --- | --- |
| Gemini mặc định | `gemini-3.5-flash-lite`; mapping live lịch sử giữ nguyên; không inference mới |
| Gemini budget | Trước/sau **7/10**, còn **3**; global/workspace ceilings10 không đổi |
| Planner `reconciliation-planning-2` | **PASS MOCK/CONTRACT — LIVE NOT VERIFIED**; lịch sử1 attempt của revision trước không được gán cho prompt mới |
| Qwen `knowledge` | **BLOCKED / LIVE DEFERRED** theo chỉ định, HTTP 403/IP; không probe |
| LlamaParse | Creation **OFF** cả env/workspace; lịch sử 2 tài liệu/2 trang/**6 credits** và 2 reservations giữ nguyên; không request mới |
| Argon | **RESEARCH COMPLETE**; model/account inference/quality/latency/cost **NOT VERIFIED**, implementation/live **DEFERRED** |

[Nghiên cứu phân tuyến model](AI_MODEL_ROUTING_RESEARCH.md) gồm đủ 14 phần, tám nguồn Google bắt buộc và tài liệu bổ sung, kiểm tra ngày 29/10/2026. Đề xuất một Gateway, Flash-Lite cho schema/mapping/simple planning, Argon explicit opt-in cho suy luận phức tạp, backend giữ matching/verifier/KPI/approval. Hai lớp attempt/token-USD caps, một ledger nhỏ trong PostgreSQL hiện có; Argon disabled/request 0/USD 0. Phân biệt REST 32K/SDK 64K, thinking+answer budget, timeout/lease/recovery, retention, continuation và pricing revisions. Cần chủ dự án duyệt trước mọi implementation/live; không thêm dependency, biến env runtime, code provider hoặc migration trong nhiệm vụ nghiên cứu.

Kiểm tra tài liệu trước commit: đủ 14 sections và 14 nguồn đã mở, UTF-8/Markdown references/local paths, hai JSON examples (gồm `PlanProposal` validation), phép tính chi phí Decimal và `git diff --check` PASS. Repository scan **106 source candidates**, kiểm known credentials trong source/reachable history và runtime/binary candidates PASS; đây không phải chứng nhận security audit đầy đủ. Commit nghiên cứu chỉ gồm bốn Markdown files: tài liệu nghiên cứu mới, báo cáo này, AI_INTEGRATION và README. Không chạy lại suite ứng dụng chỉ vì sửa tài liệu; sử dụng kết quả accepted-main 143/T35 và full 15 đã ghi, persistence/oracle/budgets vừa kiểm lại PASS.

### Quyết định bàn giao và điểm dừng

**PASS:** ba gates nghiệm thu kỹ thuật; 143 backend/15 E2E catalogue; CSV/XLSX UI và independent oracle; security regression/persistence; main merge/.vscode/tag/branch cleanup; accepted-main deploy; cleanup đúng 4 images; nghiên cứu tài liệu Argon. **FAIL:** không có test FAIL hoặc lỗi ứng dụng mới đã xác định còn tồn tại trong phạm vi này. **BLOCKED:** Qwen live. **NOT VERIFIED:** prompt Planner mới live, Argon live/account/benchmark, representative precision/recall, production security audit và DR restore. **DEFERRED:** tích hợp/live Argon, long decode, Giai đoạn 3.

Mức sẵn sàng: source Giai đoạn 2 đã nghiệm thu trong phạm vi MVP công bố, main/tag/runtime có bằng chứng; đủ để chủ dự án xem xét prompt tiếp theo. Không tự coi các mục NOT VERIFIED là PASS hoặc tự cấp quyền triển khai. **DỪNG sau bàn giao; không bắt đầu Giai đoạn 3, không tích hợp Argon hoặc tăng/reset ngân sách.**

## M. Hoàn thiện frontend và UX Giai đoạn 1–2

Phạm vi được giao: project search/pagination/restore, thống kê/trạng thái/next action, tổ chức frontend có kiểm soát, ngôn ngữ/loading/error/keyboard/responsive, polling và dữ liệu test. Không đổi engine/verifier, tiền, approvals hoặc artifacts lịch sử. Nhánh từ main sạch `0b9421e`, hai acceptance tags giữ nguyên; một repo/Compose. Baseline thật: 27 projects, 32 datasets, 27 canonical, 118 foundation + 13 match + 22 export files; Gemini 7/10, planner1/parser2, parser creation OFF.

### Bản đồ trách nhiệm trước sửa

| Trách nhiệm | Quyết định | Lợi ích | Rủi ro và kiểm chứng |
| --- | --- | --- | --- |
| App Shell/sidebar | Giữ ở App; sửa count/footer/mobile focus cục bộ | Giữ điều hướng hiện có | Responsive/keyboard |
| Project selector | Tách một component với typed props; API đọc phân trang/tìm kiếm | Một nơi quản lý search/loading/focus, không tải toàn bộ projects | Restore ngoài trang đầu, scope/race/auth |
| Dashboard/next action | Tách phần hiển thị summary/action nếu có ranh giới rõ | Không lẫn counters với financial KPI | DTO backend, READY/PARTIAL/loading và đúng deep link |
| Data workspace/explorer | Giữ state/API ở App, bổ sung scope guards và lỗi/chất lượng | Không nhân bản fetch/preview logic | Mapping drafts, canonical refs, pagination |
| Upload/settings | Giữ implementation đang PASS | Không refactor ngoài thay đổi cần thiết | Regression pipeline/security |
| Jobs | Poll theo active jobs, refresh thủ công khi idle | Giảm request lặp | Completion refresh, no overlap/unmount/stale response |
| Reconciliation | Format; tách evidence nếu độc lập, giữ rule/result state và contracts | Dễ đọc và sửa cục bộ | T35, historical run/evidence/snapshot/export |

Các phát hiện xác nhận từ source: project chỉ lấy trang50 rồi bỏ saved ID ngoài trang; sidebar dùng page length; Dashboard dùng fallback0 lúc loading, nhãn READY mơ hồ; polling toàn project mỗi3s cả khi idle; một số scope state chưa được xóa khi chuyển project. Đây là confirmed bugs/UX gaps, không phải bằng chứng matcher sai. Chi tiết kiểm thử/kết quả sẽ ghi sau thực thi.

### Nhóm A — project selector

Đã tái hiện regression trên image cũ: saved ID ngoài trang đầu không có single-project GET (404). Bổ sung GET scoped theo ID và search literal name/business_scope có giới hạn, Unicode/case-insensitive, escape `%/_`, stable pagination; không migration/quyền mới. UI tách ProjectSelector: 20 results/trang, debounce/AbortController/sequence guard, loading/error/retry/no-results, scope và ID ngắn cho tên trùng, combobox/listbox/Arrow/Enter/Escape, focus trở về nút mở. Saved ID được xác minh riêng; mất quyền/missing không tự chọn project khác. Chuyển project xóa canonical/evidence/source state, giữ key theo project cho reconciliation.

PG regression sau sửa **1 PASS, 12 deselected** (3,76s), trước sửa FAIL đúng thiếu GET. TypeScript/ESLint/build/Ruff/mypy31 PASS. Sáu browser contract tests **6 PASS** (8,9s): 1/10/50/120 projects, paging, search có dấu/hoa thường, duplicate names/scopes, saved off-page/reload/missing, delayed search/error/loading. Lần đầu keyboard tests phát hiện focus không quay về trigger do Dialog không dùng Dialog.Trigger; sửa returnFocus optional trong Modal rồi cả6 PASS, không đổi expectations. Browser fixtures chỉ intercept API GET, không tạo production projects/dữ liệu/cloud. Các E2E cũ đã đổi sang tương tác bộ chọn thật, không hidden select.

Reconciliation responsive trên saved demo thật: **4 PASS** (17,0s, 390/768/1366/1920), không tạo dữ liệu. Lần đầu helper đọc API trước session bootstrap bị401; sửa helper đợi visible picker (auth đã hoàn tất), không bỏ auth. Bốn màn hình sau đó PASS qua tìm kiếm/selection mới. Diff/known-secret-history/local Markdown links PASS, chưa coi các kiểm tra nhóm này thay cho full regression cuối nhiệm vụ.

### Nhóm B–C — thống kê, chất lượng và bước tiếp theo

Sidebar lấy `datasetTotal`, không page length; trước response hiện dấu chờ, Dashboard không dùng fallback0. Tách DataOverview (pure UI) khỏi App, đưa DatasetList dùng chung vào components hiện có; state/fetch vẫn ở App. Nhãn READY thành “Kết quả sẵn sàng sử dụng”, giải thích dataset/bảng, mapping review và active jobs; breakdown PARTIAL/stale/FAILED từ summary additive, không migration hoặc KPI tài chính mới. PARTIAL trong chi tiết nguồn có invalid/row counts từ canonical và nút xem lỗi, không khẳng định do mapping chưa duyệt.

Summary thêm target điều hướng scoped, chọn theo ưu tiên và thứ tự ổn định; next action mở đúng dataset/table/tab/canonical-errors kể cả target không nằm trong trang25 nguồn. Approved chưa canonical → tab Chuẩn hóa; thiếu approval → AI Smart Setup; PARTIAL/FAILED → kiểm lỗi; hai READY → chọn nguồn ở Đối soát, không tự coi tương thích/chạy; verified run có links kết quả/ngoại lệ. Backend vẫn authorize mọi lookup; không sửa nguồn khi bấm thẻ hướng dẫn. Refresh abort/sequence chặn dữ liệu/lỗi cũ sau đổi project; idle không polling3s vô hạn, còn active jobs mới hẹn refresh tiếp, có refresh thủ công. Footer bỏ nhãn phát triển. Reconciliation giữ component key theo project khi chuyển home/reconcile/reports/exceptions để không mất draft không cần thiết.

Sau sửa: **145 backend PASS, 0 FAIL/SKIP** (36,19s, toàn suite PostgreSQL/Linux;120 offline+25 integration), gồm search regression mới và lifecycle summary80datasets/PARTIAL/FAILED/stale; các security/worker/engine/verifier/exports cũ giữ PASS. Browser contract suite hiện **10 PASS** (13,4s) với totals80/page25, READY0/PARTIAL1/stale2, deep link tới sheet thứhai của nguồn ngoài trang đầu, review/normalize đúng tab, pending/error/switch race. Lần đầu SQL group-by JSON dùng hai bind-expression khác nhau bị PostgreSQL từ chối; reuse cùng expression rồi full suite PASS. Một selector test viết thiếu space trong accessible name đã đối chiếu snapshot và sửa selector, không sửa UI để che lỗi.

Reconciliation responsive trên runtime mới **4 PASS**; Planner UI **PASS MOCK** (4,1s). Mock catalogue cũ intercept mọi project rồi giả định luôn có nguồn demo; scope intercept vào đúng project demo, giữ toàn bộ assertions. Không có request provider thật. Không có thay đổi matcher/verifier/migration/dependencies/financial DTO; backend chỉ mở rộng read summary/navigation trong repository/API hiện có.

### Nhóm D–F — tổ chức frontend, UX và fixtures

**Confirmed bug:** request evidence của run A trả sau khi chọn run B có thể mở dialog A dưới context B. Regression trước sửa FAIL (dialog cũ làm control nền không còn accessible); sau sửa PASS. Run scope/generation và sequence guards áp dụng evidence/export; chỉ đọc snapshot khi `run.id === runId`, kiểm project của Run DTO trước hiển thị. ReconciliationEvidence tách đúng cell preview/review form theo run/group, hủy GET khi đóng/unmount; không thay evidence/approval/review APIs. Job polling dừng khi unmount, không hủy job backend hoặc gửi lại POST. ReconciliationStudio giữ setup/results cùng state do còn chia sẻ draft/run, chỉ format và tách evidence có ranh giới rõ; không tạo component/framework thay thế toàn bộ ứng dụng.

UI role lấy từ `/session`, hiển thị Chủ không gian/Có quyền chỉnh sửa/Chỉ xem; viewer không có nút tạo/upload/approve/normalize/export mới/review khả dụng. Backend vẫn là authorization authority; không đổi membership/policy. Tiếp tục cho xem nguồn/bằng chứng. Chuẩn hóa ngôn ngữ múi giờ/phạm vi/tiền tệ, không đổi request fields. Empty/no-results/loading/error của project/summary/run/cases tách biệt; GET timeout30s có thông báo/thử lại, không tự retry mutation. Navigation giữ draft khi chuyển giữa các màn hình reconciliation; link kết quả từ Dashboard có yêu cầu chọn đúng run mới nhất, không chỉ viết localStorage rồi giữ state cũ.

Project dialog dùng combobox/listbox/active descendant, focus visible/Enter/Escape và focus return. Mobile sidebar ẩn khỏi keyboard khi đóng, trap Tab/Shift+Tab, Escape trả focus về nút mở; main inert khi drawer mở. Upload/evidence/project dialogs trả focus và dùng Radix hiện có. Không thêm UI/state library hoặc dependency/lockfile runtime; chỉ dùng Prettier3.9.10 tạm qua npm exec để format các files được sửa (đối chiếu [CLI chính thức](https://prettier.io/docs/cli)), không thêm config/framework. Visual QA desktop/mobile phát hiện thẻ bước tiếp theo thiếu padding; đã sửa spacing, giữ palette/layout cũ.

Fixture foundation mới dùng **một project riêng theo provider mode và scope E2E**, đối chiếu exact name/scope, nhiều kết quả thì fail; lần đầu vẫn tạo qua UI. Mỗi replay dùng CSV bytes mới có UUID ở ID tổng hợp cuối cùng và filename riêng, không approve lại bảng cũ hoặc invalidate canonical đã lưu. Giữ oracle tiền/zero-prefix/null/invalid/zero; không xóa project cũ hoặc thêm API delete. Browser contract tests tạo120projects/80datasets chỉ mock GET; PostgreSQL synthetic schemas vẫn nằm trong server hiện tại rồi tự dọn schema riêng. Hai lần full E2E liên tiếp đã dùng lại cùng project: sau lần đầu projects28 so baseline27; không tạo thêm project theo timestamp ở lần sau. Artifact/job test vẫn tăng có chủ đích, không tuyên bố đã giải quyết retention lịch sử.

Kiểm chứng trước chốt nhóm: toàn suite đầu **33 PASS** (~1,3phút), gồm9foundation+17interface+7reconciliation. Sau bổ sung viewer, full suite **33 PASS/1 FAIL** do test áp `toBeDisabled` lên chính fieldset (DOM đã có disabled); đổi thành kiểm hai source selects thật bị disabled, targeted viewer **1 PASS** (3,5s), không sửa app để che kết quả. Full suite34 trên source/labels chốt sẽ được ghi dưới mục bàn giao. Mọi test có assertion0 uncaught pageerrors; foundation/T35 còn kiểm console errors trên luồng thành công. Mock503/permission denial là kiểm lỗi có chủ đích, không ghi chúng thành live provider PASS.

Backend full vẫn **145 PASS** (120offline+25PG); chạy lại Windows offline **120 PASS, 25 deselected** (10,73s). Bổ sung assertions trong PG T20/T34/T35: summary có latest_verified_run_id đúng run, hai READY dẫn tới RECONCILE; targeted **1 PASS** (4,47s), không tăng catalogue thành146. TypeScript/ESLint/build/Ruff/mypy31 PASS. Đọc lại UI CSV/XLSX và oracle ba pairs production PASS; không đổi golden fixture/engine/verifier. Snapshot sau full E2E đầu: **122foundation+14match+24exports, 28projects/33datasets/28canonical, 114jobs/118attempts/117audits/17traces, 15plans/14contracts/14runs/46cases**. Mọi baseline IDs/metadata/hash trước nhiệm vụ giữ nguyên; evidence JSON tại runtime bị ignore.

### Kiểm tra contrast và giới hạn dialog

Full regression trên runtime `246fe45`: **145 backend PASS, 0 FAIL/SKIP (44,02s)** và **34 E2E PASS, 0 FAIL/SKIP (~1,3phút)**. Bổ sung assertions vào năm cases responsive hiện có: dialog nằm trong viewport, outline focus thấy được, tỷ lệ màu chữ trên nền thực của tên/phạm vi/mã project đang highlight và placeholder ít nhất4,5:1. Regression thực tế phát hiện mã project highlight chỉ **4,3728:1**; đổi riêng màu chữ từ `#64748b` sang `#475569`, giữ nền/palette và hành vi. Sau sửa **5 PASS (10,4s)** trên production frontend vừa build; TypeScript/ESLint/build/source scan PASS. Không tăng số cases vì thêm assertions.

Đối chiếu [WCAG 2.2 SC1.4.3](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) và [ARIA combobox pattern](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/); đây là kiểm tra các màu/interaction cụ thể, chưa phải toàn bộ WCAG/screen-reader audit. Xem ảnh selector390/1440 và Dashboard390, dialog cuộn nội bộ, không cắt control. Restart, recreate toàn bộ và recreate frontend trên runtime246 đều đã PASS metadata/artifact bytes và fail-closed local proof; bản cập nhật contrast sẽ được xác minh lại trên image từ commit sạch trước bàn giao.

### Bàn giao chất lượng — 30/10/2026

#### A. Phân loại phát hiện

- **Confirmed bug:** saved project ngoài trang50 bị bỏ; sidebar đếm page thay tổng; response project/run cũ có thể ghi đè context mới, trong đó evidence đã có regression FAIL trước sửa; focus không trả về trigger của dialog mới; màu mã project highlight4,3728:1. Hai lỗi phát hiện trong quá trình sửa (GROUP BY JSON PostgreSQL và focus dialog) đều được sửa, không còn FAIL trong bộ chốt.
- **UX gap:** READY0 không giải thích PARTIAL/stale/FAILED, thiếu chỉ dẫn đúng dataset/table, số0 lúc chưa tải và lỗi API dễ lẫn empty, role/footer/thuật ngữ khó hiểu, idle polling liên tục.
- **Maintainability concern:** App/ReconciliationStudio gộp nhiều trách nhiệm, JSX dài; tách đúng selector/overview/evidence, giữ state chung của form/results và các phần chưa cần thay.
- **Accepted limitation:** artifacts/jobs tổng hợp vẫn tăng khi replay; chưa cleanup lịch sử hoặc triển khai retention. Các giới hạn AI/accessibility/benchmark còn lại ghi mục G.
- **Not reproduced:** không tìm thấy sai lệch mới trong Decimal, matching, verifier, MetricSnapshot hoặc export khi replay oracle hiện có. Đây không phải chứng minh mọi dữ liệu/thuật toán đều không còn lỗi.

#### B. Thay đổi trước/sau và bằng chứng

| Hạng mục | Trước | Sau | Files chính | Kiểm chứng |
| --- | --- | --- | --- | --- |
| Project selector | Select cơ bản, khó phân biệt tên trùng | Search tên/phạm vi có dấu, scope/ID, keyboard/ARIA, debounce/abort | ProjectSelector.tsx, components.tsx | 1/10/50/120, Unicode, no-result/error/retry/focus |
| Project pagination/restore | Chỉ trang50, saved ID có thể mất | 20/trang, GET theo ID scoped, search literal bounded/stable | api.py, ProjectSelector.tsx, App.tsx | PG120 + browser off-page/reload/foreign404/race |
| Dashboard counts | Sidebar datasets.length; loading fallback0 | Tổng API, loading/error riêng, giải thích nguồn/bảng/job | App.tsx, DataOverview.tsx | 80datasets/page25, pending/error/retry |
| Dataset status | READY không giải thích kết quả chưa đạt | PARTIAL/stale/FAILED riêng, invalid/row counts, link xem lỗi | repository.py, contracts/api.py, App.tsx | PG lifecycle và lỗi đúng canonical/table |
| Next action | Thiếu hướng dẫn theo gate | Target deterministic scoped, stable priority; chỉ điều hướng | repository.py, DataOverview.tsx, App.tsx | WAIT/upload/review/normalize/partial/reconcile/verified links; không tự POST |
| Frontend organization | Evidence/API/state lẫn trong file lớn | 3 focused components typed props; format rule/results; generation guards | ReconciliationEvidence.tsx, ReconciliationStudio.tsx, types | Delayed evidence regression, T35, giữ draft/run khi đổi màn hình |
| UI wording/accessibility | Footer theo giai đoạn, role/thuật ngữ lẫn; drawer keyboard | Footer sản phẩm, role thật, labels Việt, inert/trap/focus return | App.tsx, MappingStudio.tsx, styles.css, api.ts | 5 widths, Escape/Tab/Enter, dialog bounds, outline,4 màu contrast cụ thể |
| Jobs/test fixtures | Poll cả idle, project mới theo timestamp | Poll chỉ active/stop unmount, refresh thật; reuse project, fresh bytes | App.tsx, ReconciliationStudio.tsx, e2e/*.spec.ts | Clock polling/terminal/manual;4 replay pipelines, project28 giữ ổn định |

Backend chỉ thêm read/search/summary DTO, không migration, không thay engine/financial semantics. Trước đó single-project GET thực tế chưa tồn tại; bổ sung đúng endpoint scoped cần khôi phục ID, không tạo API xóa hoặc workflow thứ hai. Schema test tạm nằm trong PostgreSQL hiện có và được harness dọn đúng schema, không là môi trường ứng dụng mới.

#### C. Quality thực tế

| Lệnh/nhóm | Kết quả chốt |
| --- | --- |
| `./tools/test-postgres.ps1 -All` | **145 PASS, 0 FAIL/SKIP,44,02s** =120offline+25PG; baseline143+2casePG mới |
| `uv run pytest -q -m 'not integration'` | **120 PASS**,25integration deselected,10,73s; không cộng replay vào145 |
| Ruff / mypy | PASS;31 backend/migration files được mypy kiểm |
| `npm --prefix frontend run check` / `lint` / `build` | PASS sau sửa contrast; main378,26kB, lazy reconciliation/chart491,55kB; dependency/lockfile không đổi |
| `$env:STUDIO_EXPECT_AI_PROVIDER='MANUAL'; npm --prefix frontend run test:e2e` | **34 PASS, 0 FAIL/SKIP,~1,2phút** trên image source sạch `ac44915`;9foundation+18interface+7reconciliation, baseline15+19case |
| Browser integration / mock | Foundation/T35 chạy UI→API→worker thật trên local production;18interface cases và Planner UI dùng mocked GET/contracts, không ghi chúng thành live AI |
| Security regression | Workspace/foreign resource/viewer/CSRF/Host/local fail-closed, scoped evidence/export, injection/cloud OFF/quota và worker/recovery trong backend/E2E trên; không cộng thêm cases |
| UI/export read-back và oracle độc lập | PASS cả CSV/XLSX downloads: SHA256, nguyên Snapshot JSON/as-of, zero-prefix, không công thức KPI; Shopee/TikTok/giao nhận đúng membership/amounts/denominators/cases |
| Responsive/accessibility thực chạy | 390/768/1366/1440/1920; page overflow, dialog bounds, tables scroll, keyboard/labels/ARIA/status, Escape/focus return/drawer trap;4 mẫu chữ trong selector đều≥4,5:1 (mã highlight sau sửa6,963:1) |

Backend source/tests không đổi từ lần145PASS tại246fe45 sang ac44915; hashes34files trên cả backend/worker khớp source. Frontend chốt chạy lại toàn34 sau thay đổi contrast. Uncaught pageerrors=0 trong từng test; console errors=0 trong các luồng foundation/T35 thành công. Các lỗi HTTP/mock có chủ đích vẫn được kiểm thông báo thật. Cảnh báo Starlette/httpx deprecation và Node color-env còn; không phải test FAIL. Chưa audit mọi màu/trạng thái hoặc chạy screen reader thật; không tuyên bố WCAG toàn bộ PASS.

#### D. Data integrity, cloud và Docker

| Metadata/artifact | Trước nhiệm vụ | Sau bộ chốt |
| --- | ---: | ---: |
| Workspaces / projects | 1 /27 | 1 /28 |
| Datasets / versions / source tables | 32 /32 /30 | 36 /36 /34 |
| Schemas / mappings / canonical | 64 /64 /27 | 72 /72 /31 |
| Jobs / attempts / audits / traces | 109 /113 /112 /17 | 129 /133 /132 /17 |
| Plans / contracts / runs / cases | 14 /13 /13 /43 | 18 /17 /17 /55 |
| Foundation / match / export files | 118 /13 /22 | 134 /17 /30 |

Đã so **từng ID + metadata SHA256 + artifact bytes** của baseline và snapshot sau replay đầu với hiện trạng: nguyên vẹn, chỉ append dữ liệu tổng hợp. VerifiedRun chứa MetricSnapshot, mappings/revisions/approvals, job/run/export lịch sử không bị sửa hoặc xóa. Project count27→28 ở lần đầu, sau đó28 ở cả ba lần replay đầy đủ; không tạo project theo timestamp nữa. Snapshot từ chối khi còn active jobs; không có job active lúc kiểm persistence.

Gemini trước/sau **7/10 attempts**, còn **3**, global/workspace đều7 với ceilings10; planner attempt **1**, LlamaParse reservations **2**, traces **17** không đổi. Model mặc định vẫn `gemini-3.5-flash-lite`; cloud request delta **0**, không reset/tăng budget/reservation, parser creation **OFF** cả env/workspace. Không gọi Qwen/Gemini/LlamaParse/Argon. Qwen vẫn **BLOCKED/DEFERRED** theo chỉ định HTTP403; live planner revision mới vẫn **NOT VERIFIED**. Parser live lịch sử không bị gán thành live request của nhiệm vụ này.

Image sạch build bằng Compose chính với OCI revision/source đúng **ac44915df1610c32fbd82c895b1163a23b65dcf6**. Backend/worker34tracked files mỗi service và4production files phục vụ HTTP đều khớp SHA256 local; không `.env` trong image. Immutable identifiers lấy từ `.Image` của container đang dùng:

| Service | Image ID |
| --- | --- |
| Backend / worker | `sha256:54e818ae7d52fcfeb01d30e6c4d01d1189eb7e7e330e3fa6b5a5b74cc9830879` |
| Frontend | `sha256:c4cfc088571db643b77ee085edf509cbc84dc4671b8adfb186cd3310515c7b6e` |
| PostgreSQL giữ nguyên | `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` |

Một Compose project `ai-reconciliation-studio`,4services healthy, chỉ publish127.0.0.1:18180. Giữ volumes `ai-reconciliation-studio_postgres_data` và `ai-reconciliation-studio_artifacts`, cặp rollback-e025094 đã nghiệm thu không đổi. Không rebuild PostgreSQL, xóa containers/image/volume/cache bằng cleanup hoặc global prune. Docker host aggregate lúc kiểm:51images/39,39GB,31containers/574,6MB,36volumes/5,432GB,build cache47,66GB; đây là tổng host, không quy toàn bộ cho dự án hoặc tuyên bố dung lượng đã thu hồi.

Sau full34E2E trên imageac44915, chạy lại `./tools/check-persistence.ps1`: **restart PASS, force-recreate cả bốn PASS, frontend-only recreate PASS**. Mỗi thao tác xác nhận local demo proof bị vô hiệu (403), verify loopback rồi exact metadata/artifact bytes khớp snapshot sau tests; cả4services healthy. Không có job active trước thao tác. Source/assets hashes, oracle/API/export read-back và quota được kiểm lại sau recreate, không request cloud hoặc sửa dữ liệu lịch sử.

Evidence local bị ignore: `runtime/interface-quality-before.json`, `runtime/interface-quality-after-first-e2e.json`, `runtime/interface-quality-after-tests.json`, `runtime/interface-quality-runtime.json`, screenshots/downloads. Persistence không thay backup/restore PostgreSQL; không commit các inventory/raw/runtime này.

#### E. GitHub và files

Nhánh **codex/interface-quality**,25files so main:3backend/API/DTO,11frontend source,4E2E/helper,2backend test files và5Markdown hiện có. Phần lớn diff ReconciliationStudio/reconciliationTypes là format; không thêm dependency/config/framework. Kiểm diff riêng engine/verifier/normalization/schema_mapping/migrations/Compose/locks/Rules/AGENTS/PROJECT_PLAN: rỗng.

| Nhóm commit đã push | SHA |
| --- | --- |
| Selector/search/restore | `58dc8a0c18387a75e83e2a41c24054f1e625f738` |
| Counts/readiness/next action | `ddceb7dbb43f7da07cc93cd20ca55c4fd3bbb2fb` |
| Scoped evidence/UX/fixtures | `246fe459d127d5c1010c414e9b0cd6faa23719be` |
| Contrast/dialog assertions | `ac44915df1610c32fbd82c895b1163a23b65dcf6` |

Commit báo cáo cuối chỉ sửa Markdown; SHA được báo sau commit, không tự ghi SHA của chính nó vào file. Image giữ source ứng dụngac44915, diff application giữa source này và commit tài liệu phải rỗng. Origin chính thức được đối chiếu/fetch trước push; không force-push/merge/tag mới. Main/origin main giữ **0b9421e1fbbc1e13537b5c5510b3769e387f91a5**; accepted tag targets giữ **78e68c08e60c7af2359e46def43196cf5b1a6dc1** và **be6b8a067ca052ea989a029a15558b0fd5ee48ef**. Repository check111source candidates, known-secret scan trong source/reachable history và Markdown local paths PASS; không đưa runtime/secrets vào stage. Final local/remote HEAD và working tree được xác minh khi bàn giao.

#### F. Đối chiếu Rules.md

Clean Code/trách nhiệm: tách3ranh giới có lợi ích và typed props, không refactor theo số dòng. Contracts/provenance: backend quyết định counts/targets, frontend không tính tiền/KPI hoặc sửa lineage. Không overengineering: dùng Radix/state/API hiện có, không thêm library/service/migration. UX Việt/loading/error/focus và disabled theo quyền đã kiểm; next action thật chỉ điều hướng, không approve/chạy tự động. Permission boundaries vẫn enforce backend, viewer tests/security suite PASS. Docker/Git/scope: một repo/Compose, dữ liệu/rollback giữ nguyên, feature branch đã push từng nhóm, main/tags bảo toàn, không cloud/Giai đoạn3. Đây là đối chiếu phạm vi đã kiểm, không chứng nhận tuân thủ mọi tình huống chưa đo.

#### G. Giới hạn và quyết định

- Retention dữ liệu test: project không tăng tiếp, artifacts/jobs tổng hợp vẫn append; không xóa bằng chứng cũ. Chủ dự án có thể giao chính sách lưu trữ/cleanup có scope riêng.
- App còn lớn; data workspace/settings/setup/results giữ state chung để giảm rủi ro, không coi tách selector/overview/evidence là đã refactor toàn frontend.
- Search ILIKE/paging đã kiểm120projects và80datasets, chưa benchmark search1k/10k hoặc mọi collation. Không tuyên bố khả năng mở rộng từ vài fixtures.
- Keyboard/ARIA/focus/contrast/5widths đã có bằng chứng cụ thể, chưa audit WCAG/screen reader toàn diện. Security regression không thay production penetration test; persistence không thay DR restore drill.
- Qwen live hoãn; Planner revision mới live chưa xác minh; Argon không tích hợp. Mapping/linkage precision/recall đại diện và các giới hạn MVP lịch sử giữ nguyên, không nâng thành PASS bằng UI tests.

**ĐẠT nhiệm vụ hoàn thiện frontend/UX trong phạm vi được giao:** bộ chốt145backend/34E2E không FAIL/SKIP, dữ liệu lịch sử giữ nguyên, không cloud. Đủ để chủ dự án review `codex/interface-quality`; không tự coi đây là quyền merge hoặc production release. **DỪNG sau push báo cáo; chờ lệnh riêng, không merge main, không bắt đầu Giai đoạn3 hoặc Argon.**

## N. Final UX hardening — phân loại project và dữ liệu gần đây

Ủy quyền mới ngày30/10/2026 tiếp tục trên `codex/interface-quality`, baseline8a20c4e/145backend/34E2E; mục M giữ lịch sử. Mục tiêu: phân loại TEST có bằng chứng và ẩn mặc định, quản lý/khôi phục bởi owner, sửa Recent Data, rà UX có giới hạn. Giữ engine/verifier/Decimal/MetricSnapshot/raw/history; không cloud/main merge/Giai đoạn3.

### Thiết kế và kiểm chứng theo nhóm

ProjectRow chưa có classification. Tái sử dụng audit hiện có để lưu nhóm explicit WORK/TEST/UNKNOWN, không migration/bảng/cột mới; legacy không event là UNKNOWN. POST người dùng WORK mặc định; fixtures TEST explicit. PATCH chỉ owner, khóa project và so expected_classification,409 chống stale overwrite; no-op không thêm audit. GET cũ không include_test giữ tương thích; UI gửifalse từ đầu, lọc server trước count/offset/limit, GET theoID không phụ thuộc filter. Selector duy nhất có toggle “Hiển thị dự án kiểm thử” mặc địnhOFF, badge TEST và details quản lý current project có tên/scope/full ID trước xác nhận. Ẩn TEST không đổi project/draft/quyền, restore savedTEST vẫn được; success/error riêng, không retry mutation.

Regression trước sửa backend:2case mới FAIL do thiếuclassification vàtotal120 thay80;25PG cũ PASS. Sau sửa27PG PASS/120offline deselected (32,11s); thêm concurrency test hai owner cùng expectedWORK: một200/một409, toàn28PG PASS (30,29s). Một lần browser23case: option queries cũ đếm lẫn3nativeoptions trong phần phân loại; đã scope listbox thật, không hidden control. Fixture rule-draft mới ban đầu chưa có2nguồn nên không có form; bổ sung catalogue tổng hợp có typed shape. Label nhóm dự án được gắn aria-label rõ; targeted classification1PASS và cả24browser contracts PASS (26,1s). Đây chưa thay full regression cuối.

Recent Data đã tái hiện FAIL:30nguồn, trangDữ liệu thứhai→Tổng quan mấtLatest000. Sửa bằng GETdatasets offset0/limit5 riêng, created_atDESC/idASC stable; không endpoint mới hoặc tải toàn bộ. Loading/error/retry/empty riêng, abort vàproject guard. Browser5/30/80nguồn đều PASS, đúng5mới nhất saupage2; refresh sau nguồn mới cập nhật đúng. Case delayed/error/switch xác nhận responseprojectA không lộởB, lỗi không giả empty.

UX audit mười khu vực hiện có: Tổng quan (recent độc lập, nguồn mới nhất/loading/error), Dữ liệu (nút “Cập nhật trạng thái xử lý” rõGET so với normalize tạojob), Smart Setup (giữ đề xuất/approval/field evidence), Chuẩn hóa (READY/PARTIAL/stale/errors gate cũ), Đối soát (giữ nguồn→scope→approval→run), Ngoại lệ (thêm giải thích trạng thái review không đổi tiền/comparison), Báo cáo (giữ run/kỳ/verified snapshot/as-of/export), Cài đặt (quota/provider/roles thật), Chọn/Tạo dự án (classification gọn), dialogs/thông báo (focus/ARIA). Không redesign hoặc bỏ approval. Rà soát không phát hiện lỗi mới cần sửa matcher/verifier; những kết luận ngoài fixtures vẫn chưa được chứng minh.

Inventory và số liệu bàn giao cuối được ghi sau full regression/persistence; không dùng baseline làm PASS mới.

### A. Project inventory — bằng chứng trước thay đổi

Đầu nhiệm vụ: **28 UNKNOWN** vì chưa có classification event; sau xác minh qua API: **28 TEST,0 WORK,0 UNKNOWN**, tổng28 giữ nguyên. Không gán WORK chỉ dựa vào tên. Tất cả thuộc workspace `demo`, dataset owner `demo-owner`; inventory local còn lưu created_at UTC, scopes, dataset IDs/hash, jobs/runs/audit refs. Không có project nào cần chủ dự án xác nhận ở tập28 này; project cũ khác không có bằng chứng vẫn mặc địnhUNKNOWN.

| Project ID | Tên | Nguồn gốc đã xác minh | Nhóm đề xuất/đã áp dụng | Chắc chắn |
| --- | --- | --- | --- | --- |
| `abe40c9c-d47b-4a2f-8f80-d34888df2d7c` | Dữ liệu tổng hợp · 1793127566266 | E1 | TEST | Cao |
| `1adf15a2-f0cf-4a1a-b918-32be666d8928` | Dữ liệu tổng hợp · 1793127840245 | E1 | TEST | Cao |
| `b13895e2-12fc-45ee-897e-7fa650909031` | Dữ liệu tổng hợp · 1793128199903 | E1 | TEST | Cao |
| `c28360f8-78cc-4723-8f91-b089375e41cb` | Dữ liệu tổng hợp · 1793128391092 | E1 | TEST | Cao |
| `1e0cd1d9-b763-4964-b7a1-4132bc61c5c7` | Dữ liệu tổng hợp · 1793129148032 | E1 | TEST | Cao |
| `42773d37-9a65-421b-8fd3-866b3a3a1c06` | Dữ liệu tổng hợp · 1793129956994 | E1 | TEST | Cao |
| `4997a82a-fc08-42fe-b97a-a0db1bd6c113` | Kiểm tra khôi phục worker | E2 | TEST | Cao |
| `b77b6551-e1fa-40b2-97ef-0a688c015457` | Dữ liệu tổng hợp · 1793131631604 | E1 | TEST | Cao |
| `5c955869-30b3-4db6-8dc1-f7660647a3d1` | Dữ liệu tổng hợp · 1793147126220 | E1 | TEST | Cao |
| `fa7e7d2e-f821-46d7-920e-6b66c1c852be` | Dữ liệu tổng hợp · 1793147302189 | E1 | TEST | Cao |
| `ec4b72ae-a585-491e-abe3-980aac0363ac` | Dữ liệu tổng hợp · 1793147602813 | E1 | TEST | Cao |
| `1e84ddc0-e55e-4827-9407-d5dc17777de4` | Dữ liệu tổng hợp · 1793147655037 | E1 | TEST | Cao |
| `5b655b89-8b0e-4e0d-98b9-e365530bedac` | Kiểm tra tài liệu tổng hợp | E3 | TEST | Cao |
| `d125b6eb-0d25-48cc-a7f0-54beaa946fae` | Dữ liệu tổng hợp · 1793155126628 | E1 | TEST | Cao |
| `c573e971-295d-47a7-a3a3-94c13b3e675f` | Kiểm tra khôi phục worker | E2 | TEST | Cao |
| `8a3bc325-022c-4101-bd86-d8d57b2f48a7` | Dữ liệu tổng hợp · 1793155302402 | E1 | TEST | Cao |
| `29b91f9d-aa22-4791-a44f-52c0c760af2b` | Dữ liệu tổng hợp · 1793157445350 | E1 | TEST | Cao |
| `2358398f-c3d7-4b13-a971-5b40fcac7f2d` | Kiểm tra khôi phục worker | E2 | TEST | Cao |
| `e1c05f6d-1553-46c6-b1a7-45a191706f27` | Dữ liệu tổng hợp · 1793159064934 | E1 | TEST | Cao |
| `faa4f9b1-298a-4333-9b82-c7b939d84774` | Đối soát tổng hợp có oracle | E4 | TEST | Cao |
| `17fba5e0-de6e-4ed2-9fc0-b97a52787807` | Dữ liệu tổng hợp · 1793161569604 | E1 | TEST | Cao |
| `0a5de3e6-2781-4faf-b42b-24292c09184e` | Dữ liệu tổng hợp · 1793161842836 | E1 | TEST | Cao |
| `afa10789-3729-49f5-8676-d5f28a244ad3` | Dữ liệu tổng hợp · 1793162175280 | E1 | TEST | Cao |
| `9c9d30a7-fbd3-44df-89a9-bc17d602505c` | Dữ liệu tổng hợp · 1793175086889 | E1 | TEST | Cao |
| `1b583f85-079f-4e63-bd81-2e3af5dca0c9` | Dữ liệu tổng hợp · 1793180785335 | E1 | TEST | Cao |
| `dcf47c99-7c40-41fa-8515-75a09b6c7626` | Dữ liệu tổng hợp · 1793181069922 | E1 | TEST | Cao |
| `30494cd1-f40e-4075-9408-4b9f87f28614` | Dữ liệu tổng hợp · 1793285254493 | E1 | TEST | Cao |
| `87abdb34-f8e5-4b0a-bb81-8f1fb527391b` | Kiểm thử giao diện · MANUAL | E5 | TEST | Cao |

Bằng chứng (không dùng tên làm bằng chứng duy nhất):

- **E1 (22project):** raw `synthetic-orders.csv` có SHA256 đúng từng byte `6428223f30041b371725896b9d3b944e964e9783cfff18e55c8f842f0006c18d`, cùng fixture E2E trong lịch sử source32741ae/0b9421e; scopes kiểm thử, owner demo và parse/mapping/normalize jobs. Created_at cách timestamp harness0,79–7,88giây; hai scopes ban đầu không chứa timestamp vẫn có checksum/file/ownership/jobs xác nhận.
- **E2 (3project):** exact75000-row synthetic-recovery.csv SHA256 `c2c28b5665c82b099155eeb20493abcf9e4aa47003ef5fedaa483e2b5ff57cb9`, scopeUUID đúng worker-recovery harness, ownership/job recovery; runtime/worker-recovery.json xác định một projectID cuối.
- **E3:** projectID từ document-acceptance/acceptance.json, cả hai PDF/DOCX tổng hợp tại local có SHA256 khớp dataset refs; cached extraction/jobs giữ nguyên, không gọi parser lại.
- **E4:** projectID/datasetIDs từ reconciliation-acceptance.json, năm raw fixture CSV khớp SHA256 bytesLF trong Git (checkout Windows cóCRLF); không sửa raw để đối chiếu. Verified runs/oracle và jobs nguồn giữ nguyên.
- **E5:** project có scope ổn định E2E_MANUAL_INTEGRITY từ246fe45; cả4filenameUUID/CSVbytes dựng theo fixture hiện hành đều khớp SHA256 dataset, ownership/jobs và báo cáo M xác nhận4replays.

Đã phân loại một lần bằng28PATCH explicitID qua session owner hiện có. So trước/sau: **chỉ append28 PROJECT_CLASSIFIED_TEST audit events**, project metadata gốc và mọi metadata/artifact hash khác bằng nhau. Không SQL UPDATE/DELETE; không background classifier hoặc tự phân loại project tương lai từ tên. Một lần gọi trước local proof hoàn tất trả403, chưa ghi metadata; chỉ thực hiện sau verify-local thành công. Người dùng có thể mở TEST, xem tên/phạm vi/ID rồi xác nhậnWORK/UNKNOWN qua UI; việc này không xóa hoặc đổi quyền.

### Kết quả chốt source trước deploy có revision

**149 backend PASS,0 FAIL/SKIP (38,26s)** =120offline+29PG; baseline145 tăng4cases (hai classification, một concurrent owners, một dataset tie-order/scope). Offline Windows **120 PASS/29deselected,5,21s**. **41 E2E PASS,0 FAIL/SKIP (~1,4phút)** =9foundation+25interface+7reconciliation; baseline34 tăng7cases. Ruff/mypy28/TypeScript/ESLint/build PASS. Không cộng full40 và targeted replays thành sốcases mới.

Case mới tái hiện metadata classification không cập nhật khi selector unmount lúc PATCH đang chạy: FAIL trước sửa; parent nhận confirmed DTO có guard currentID, component chỉ set local state khi còn mounted, sau sửa targeted1PASS/4,3s và full41PASS. Không retry write hoặc hủy job backend. Bộ full có cả luồng thật upload→mappingapprove→normalize→manualruleapprove→verifiedrun→evidence/review→CSV/XLSX→reopen, provider MANUAL; Planner và interface contract fixtures là MOCK, không liveAI. Một read-back chạy khi T35 còn ghi downloads/manifest đã thấy hash khác; đợi toàn suite hoàn tất rồi đọc lại đúng cặp files/manifest, không sửa checksum/oracle hoặc bytes backend để hợp thức hóa.

Giữ keyword/source/module contracts, dependencies/locks/Compose/migrations/engine/verifier/formulas. Năm widths390/768/1366/1440/1920, keyboard/focus/ARIA/drawer/dialog bounds/contrast samples tiếp tục PASS. Báo cáo deploy/persistence/Git cuối được bổ sung sau khi commit source sạch; chưa coi healthcheck thay cho revision/hash verification.

### B. Các sửa đổi và bằng chứng

| Vấn đề | Nguyên nhân | Sửa đổi | Bằng chứng |
| --- | --- | --- | --- |
| Danh sách project lẫn dữ liệu thử | Chưa có metadata mục đích | Audit classification explicit; toggle TEST mặc định OFF; owner đổi/khôi phục có ID và audit | 120 project PG filter/count/paging, UNKNOWN visible, Unicode/scopes; browser toggle/current TEST/restore/draft |
| Recent Data lấy nguồn trang hai | Chia sẻ mảng25items của Data Explorer | Bounded GET riêng5nguồn mới nhất, tie-order ổn định | Regression30nguồn FAIL trước sửa;5/30/80PASS, page2/refresh/new source/error/delay/switch |
| Nhãn thao tác khó phân biệt | Nút hoạt động xử lý chỉ ghi “Cập nhật” | “Cập nhật trạng thái xử lý”; normalize/AI/approve/run giữ hành động riêng | Foundation thật và test polling/manualGET; không tạo job/AI khi refresh |
| Review dễ bị hiểu là sửa tiền | Phải giải thích ngay nơi đổi trạng thái | Thêm câu review không đổi comparison/tiền | T35 RESOLVED giữ immutable Snapshot, CSV/XLSX/oracle |
| Phân loại đang lưu khi rời selector | Component không nhận kết quả sau unmount | Parent nhận confirmed DTO với guard ID; không set local state khi unmounted | Targeted FAIL→PASS và full41PASS; không mất draft/chuyển ngầm |
| Bằng chứng ảnh Dashboard chụp loading | Chỉ đợi shell heading, chưa đợi dataset | Đợi nút nguồn thật trước overflow/screenshot | Kiểm lại nhóm foundation9 trên image8789940; ảnh đọc nội dung sau tải |

Files theo trách nhiệm: backend `access.py`, `api.py`, `contracts/__init__.py`, `repository.py`; frontend `App.tsx`, `ProjectSelector.tsx`, `DataOverview.tsx`, `ReconciliationEvidence.tsx`, `styles.css`, `types.ts`; regression trong3E2E/helper và `test_postgres.py`;3tools tạofixture thêm TEST explicit; README/ARCHITECTURE/DATA_CONTRACTS/TESTING_GUIDE/báo cáo. Không thêm framework, dependency, service, migration hoặc module chức năng mới.

### C. Quality và số đo thực tế

| Nhóm | Kết quả |
| --- | --- |
| Backend đầy đủ trên PostgreSQL hiện có | **149 PASS,0 FAIL/SKIP,38,26s**;120offline+29PG; baseline145+4 |
| Offline Windows | **120 PASS**,29integration deselected,5,21s |
| Ruff / mypy | PASS; `ruff check backend tests tools`, `mypy backend/studio`28sourcefiles; không đổi migrations |
| TypeScript / ESLint / production build | PASS; bundle main382,50kB, lazy reconciliation/chart491,74kB; không nâng threshold/đổi locks |
| Full Playwright MANUAL | **41 PASS,0 FAIL/SKIP,~1,4phút**;9foundation+25interface+7reconciliation, baseline34+7 |
| Mock/live phân biệt | Browser classification/recent cases và Planner dùng synthetic MOCK; foundation/T35 chạy thật API/worker local;0liveprovider |
| Security | Owner-only classification, viewer/editordenial, foreign404, expected-state409 và concurrent-write guard; session/CSRF/Host/workspace/file/export/cloud OFF/lease/recovery cũ giữ PASS |
| Independent read-back | Sau toàn suite: CSV/XLSX UI checksum, Snapshot JSON/as-of/zero-prefix và oracle Shopee/TikTok/giao nhận PASS; không FE tính lại KPI |
| Responsive/accessibility | 5widths, keyboard/Enter/Escape/focus-return, drawer trap, labels/status/alert, dialog bounds và4mẫu contrast;0uncaught errors trong từngcase. Không audit WCAG toàn diện/screen reader thực |

Recent browser fixtures đếm **2request limit5**: vàoDashboard lầnđầu + quay lại từData; refresh sau thêm nguồn thành **3**, tất cảoffset0. Không tải toàn bộ80nguồn, không request recent khi ở trangData/settings, idle polling vẫn dừng. Đo riêng API production local bằng5GET/route, HTTPclientkeepalive: defaultfiltered p50/p95 **68,49/88,52ms** (0visible), includeTEST+searchMANUAL **64,70/73,50ms** (1match), recentlimit5 **45,60/64,70ms** (project lúcđó4nguồn). p95 nội suy inclusive chỉ5samples, không benchmark sức tải/1kprojects; có lưu raw timings local.

### D. Dữ liệu, AI và vận hành

Trước nhiệm vụ:28projects/36datasets/34tables,72schemas/mappings,31canonical;129jobs/133attempts/132audits/17traces;18plans/17contracts/17runs/55cases;134foundation+17match+30exportfiles. Phân loại chỉ append28audits, không đổi bất kỳ metadatahash lịch sử. Sau hai fullreplays:28projects/38datasets/36tables,76schemas/mappings,33canonical;139jobs/143attempts/170audits/17traces;20plans/19contracts/19runs/61cases;142foundation+19match+34exportfiles. Snapshot từngID/metadata/hash trước và sau replayđầu đều là subset nguyên vẹn của hiện trạng. Historical ProjectRow, mappings/revisions, Canonical, VerifiedRun/MetricSnapshot, reviews và exports giữ nguyên.

Delta một fullreplay đo được: **0project**, +1dataset/version/table/canonical, +2schema/mapping, +5jobs/attempts/audits, +1plan/contract/run/matchfile, +3cases, +4foundationfiles và+2exportfiles,0traces. Đây là dữ liệu tổng hợp cần giữ để tái kiểm chứng, chưa có phân loại file “tạm có thể xóa” được chủ dự án duyệt. Không SQL DELETE hoặc cleanup job. Đề xuất sau này: chủ workspace xác định thời hạn giữ theo projectTEST/run, pins cho nghiệm thu, dry-run đầy đủ refs trước mọi xóa; không triển khai trong nhiệm vụ này.

Gemini global/workspace trước và sau **7/10**, còn **3**, model `gemini-3.5-flash-lite` giữ nguyên; plannerattempt1, parserreservations2, traces17; parsercreationOFF cảenv/policy. **Cloud delta0**, không provider fallback, reset/tăngquota hoặc tìmkey ở dự án khác. Qwen403 giữ **BLOCKED/DEFERRED**; Planner revision mới LIVE **NOT VERIFIED**; PDF/DOCX chỉ đọc cached extraction, không live request mới; Argon/Giai đoạn3 không triển khai.

Source ứng dụng đã push **87899400903875663258dda2e12b05b186eee97f**, build từ câytracked sạch với OCI source/revision. **34backendfiles ×2services** và **4HTTPservedfrontendfiles** khớp SHA256 source/build; không `.env` trongimage. Cặp rollback-e025094 giữ nguyên; PostgreSQL immutable ID không đổi. Không suy revision từ cachedCreated timestamp.

| Service | Immutable image ID |
| --- | --- |
| Backend/worker | `sha256:c3c8183437647aa1cb7df6f3d2b31a23ff4ddd22f3eede8e7878d6f1c58995b2` |
| Frontend | `sha256:cbba7e5bd7743f8dcb407df924b5bdf46fa5010e8ecdd959809ece0626091de8` |
| PostgreSQL | `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` |

Trên source8789940, saufull41: **restart PASS, force-recreate4services PASS, frontend-onlyrecreate PASS**. Mỗi lượt localproof bị vôhiệu đúngthiếtkế, `/api/session`403 trướcverify, sauverify đọc/so metadata vàartifactbytes khớp hoàn toàn snapshot142foundation/19match/34exports. MộtComposeproject `ai-reconciliation-studio`,4/4healthy, chỉpublish127.0.0.1:18180; giữhai volumesPostgreSQL/artifacts. Không rebuildPostgreSQL, dọnimage/cache hoặc xóa tài nguyên khác. Đây là persistencecheck, khôngDRrestoredrill.

Số đo Docker host cuối: 51 images/39,39GB; 31 containers/574,6MB; 36 volumes/5,667GB; build cache47,69GB. Đây là tổng host có tài nguyên khác, không quy toàn bộ cho ứng dụng và không tuyên bố đã giải phóng dung lượng. Không thực hiện cleanup images/cache/volumes trong nhiệm vụ này.

Evidence local ignored: `runtime/project-visibility-before.json`, `project-visibility-inventory.json`, `project-visibility-after-classification.json`, `project-visibility-after-first-replay.json`, `project-visibility-after-tests.json`, `project-visibility-runtime.json`, `project-navigation-measurements.json`, screenshots/downloads. Không commit dữ liệu runtime.

Sau khi xem ảnh, phát hiện test Dashboard chỉ đợi shell heading nên có ảnh còn loading. Chỉ sửa assertion chờ nút nguồn thật trước overflow/screenshot; không sửa ứng dụng. Chạy lại foundation **9 PASS,0 FAIL/SKIP,31,1s** trên image source8789940; đã xem ảnh Dashboard1440 có đủ counters, next action và đúng5nguồn mới nhất, cùng selector390. Catalogue vẫn **41 cases**, không cộng replay thành50. Snapshot cuối `project-visibility-after-visual.json`: **28projects/39datasets/37tables,78schemas/mappings,34canonical;141jobs/145attempts/172audits/17traces;20plans/19contracts/19runs/61cases;146foundation+19match+34exportfiles**. Phần tăng riêng foundation là1dataset/canonical,2jobs/attempts/audits,4foundationfiles; không có run/export/project mới. So từng ID/metadata/checksum của baseline và snapshot full41 với hiện trạng cuối đều PASS; quota và read-back/oracle tiếp tục không đổi.

### E. GitHub và đối chiếu quy tắc

Nhánh **codex/interface-quality**; commit source **87899400903875663258dda2e12b05b186eee97f** đã push đúng origin chính thức. Diff nhiệm vụ gồm 22 files, source/tests/docs đúng phạm vi. Commit cuối bổ sung báo cáo và assertion chờ nội dung trước khi chụp ảnh; application files so với 8789940 không đổi, runtime giữ revision ứng dụng này. SHA HEAD cuối được báo sau commit. Working tree và local/remote HEAD được kiểm chốt khi bàn giao.

Main/origin main giữ **0b9421e1fbbc1e13537b5c5510b3769e387f91a5**; acceptance tags giữ targets **78e68c08e60c7af2359e46def43196cf5b1a6dc1** và **be6b8a067ca052ea989a029a15558b0fd5ee48ef**. Không merge, tạo tag, force-push, reset, worktree hoặc Compose khác. Diff nhiệm vụ của engine/verification/normalization/schema_mapping/reconciliation_contracts/migrations/locks/Compose/Rules/AGENTS/PROJECT_PLAN rỗng. Scan 111 source candidates, known secrets trong reachable history, local Markdown paths và whitespace PASS; inventory chỉ chứa thông tin tổng hợp đã xác minh, không credentials hoặc dữ liệu khách hàng.

Đã đối chiếu Rules trong phạm vi: DTO bổ sung có kiểu, backend là nguồn sự thật, quyền owner độc lập với ẩn/hiện, audit chỉ thêm và lookup có scope; provenance và lịch sử tài chính bất biến giữ nguyên. Tái sử dụng component/audit, không thêm framework; UX Việt và CTA thật, không bỏ approval. Git/Docker/cloud/phạm vi theo chỉ định. Không tuyên bố tuân thủ hoàn hảo các tình huống chưa đo.

### F. Known limitations và quyết định

- Cả 28 project trong inventory đều đủ bằng chứng TEST; không tự tạo WORK để làm đẹp số liệu. Project lịch sử khác thiếu bằng chứng phải giữ UNKNOWN và đợi owner; không có bộ phân loại runtime theo tên.
- Truy vấn phân loại đọc audit events bằng correlated subquery; đã đo 28 project, integration kiểm 120 project, chưa benchmark 1k/10k hoặc cạnh tranh nhiều owner. Chỉ xem xét index/migration khi số đo thực tế cho thấy cần thiết.
- Retention chỉ được đo và đề xuất; artifacts/jobs tổng hợp vẫn tăng. Không xóa dữ liệu hoặc bằng chứng cũ; persistence/regression không thay kiểm tra khôi phục backup hoặc kiểm toán bảo mật production.
- Accessibility mới kiểm interactions, viewport và contrast cụ thể; chưa chứng nhận toàn bộ WCAG 2.2 AA. App vẫn giữ orchestration/state cần thiết, không refactor máy móc theo số dòng.
- Qwen live, Planner revision mới live, precision/recall đại diện và các giới hạn MVP lịch sử giữ nguyên. Không mở cloud, Argon, Assistant hoặc Giai đoạn 3.

**ĐẠT Final UX hardening trong phạm vi được giao:** TEST ẩn mặc định và có thể mở lại; UNKNOWN không bị ẩn; lựa chọn/bản nháp không đổi ngầm; Recent Data đúng nguồn/project; **149 backend / 41 E2E PASS**, không cloud, lịch sử nguyên vẹn. Đủ để chủ dự án review branch, chưa là quyền merge hoặc release production. **DỪNG sau push báo cáo, chờ review; không merge main hoặc triển khai Giai đoạn 3.**

## O. Hợp nhất UX và Docker release — 30/10/2026

### A. UX merge — PASS

- Baseline thực: main `0b9421e1fbbc1e13537b5c5510b3769e387f91a5`, UX `4b854c631e9cfb68c664b7fc57186281da906976`, ahead 7/behind 0, working tree sạch; origin chính thức đã fetch.
- `tools/test-postgres.ps1 -All`: **149 PASS**, một cảnh báo deprecation Starlette/httpx. Ruff toàn backend/tests/tools, mypy 31 source files, TypeScript, ESLint, production build, repository/history/Markdown scan và diff check PASS.
- Playwright MANUAL: **41 PASS / 0 FAIL / 0 skipped**, 90,599 giây. Lượt trước đó thất bại vì demo chưa được xác minh sau khởi động lại, bị chặn đúng chính sách; chạy `verify-local.ps1` rồi replay toàn bộ, không bỏ auth hay sửa expected values.
- CSV/XLSX đọc lại đúng snapshot/checksum/timestamp/zero-prefix; oracle độc lập Shopee/TikTok/giao nhận, membership/population/cases và historical exports PASS.
- Merge `--no-ff`: **`5f358c487f7f29482951aff1cc5aa757a5f9f1ec`**; tree khớp hoàn toàn UX đã kiểm thử, không conflict. Đã push/fetch, main local = origin/main; UX HEAD là ancestor, không còn unique commits/open PR, đã xóa branch UX bằng normal delete.
- Tags không đổi: `data-foundation-accepted-20261028` trỏ `78e68c08e60c7af2359e46def43196cf5b1a6dc1`, `reconciliation-engine-accepted-20261029` trỏ `be6b8a067ca052ea989a029a15558b0fd5ee48ef` (peeled targets, không nhầm với annotated-tag object IDs).

### B. Docker main — PASS

Build sạch từ main `5f358c4` với `BUILDX_GIT_LABELS=full`; Compose/network/volumes/healthchecks không đổi, không rebuild PostgreSQL. Backend/Worker chung image. OCI source/revision và 34 source hashes trong cả Backend/Worker, bốn frontend assets qua HTTP khớp build local.

| Thành phần | Immutable image ID | Bảo vệ |
| --- | --- | --- |
| Backend/Worker | `sha256:7a00801051416c143e0d0199919bb9a43fa319a01fd01b1a8010b1d5d8781e29` | `ai-reconciliation-studio-backend:accepted-main-5f358c4` |
| Frontend | `sha256:1049ba4457ebad8971d0be29cb523b7429714fb2c3dc1abcd28a9ef1a40ab215` | `ai-reconciliation-studio-frontend:accepted-main-5f358c4` |
| PostgreSQL | `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` | Giữ nguyên |
| Rollback Backend | `sha256:c966a65d026417d8e2a7e7662f8ab888aca582fd1a59aa319a12f6abd396f553` | `rollback-e025094`, không ghi đè |
| Rollback Frontend | `sha256:57a48c3e6ff1bedf63162b71e3a8d1292af421d177a4e7afa50dedfd31a54979` | `rollback-e025094`, không ghi đè |

- Runtime trước build `8789940` khác UX HEAD chỉ tests/docs; source hashes và served assets đã đối chiếu. Runtime mới đúng main merge. Rollback `e025094` có cùng hai migrations, dependencies và Compose với main mới: không cần downgrade/xóa dữ liệu. Chưa chạy đổi runtime về rollback trong nhiệm vụ này, không gọi đây là restore drill.
- Playwright trên image main mới: **41 PASS / 0 FAIL / 0 skipped**, 85,334 giây. Golden/report read-back PASS.
- `check-persistence.ps1`: restart, force-recreate bốn service và frontend-only recreate đều **PASS**; mỗi lần `/api/session` trả 403 trước xác minh loopback, sau `verify-local.ps1` truy cập bình thường. 4/4 healthy, chỉ publish `127.0.0.1:18180`.
- Giữ `ai-reconciliation-studio_postgres_data` và `ai-reconciliation-studio_artifacts`. Snapshot trước/sau xác nhận **mọi record/artifact lịch sử giữ nguyên ID, metadata hash và SHA256**; hai replay chỉ thêm dữ liệu tổng hợp trong project TEST đã có.
- Thực tế sau gates: 28 projects, 41 datasets/versions, 39 tables, 82 schemas/mappings, 36 canonical, 151 jobs/155 attempts, 182 audits/17 AI traces, 22 plans/21 contracts/21 runs, 67 cases/38 exports; 154 foundation artifacts/21 run artifacts/38 export files.
- Gemini mặc định `gemini-3.5-flash-lite`, vẫn **7/10 attempts, còn 3**; không request mới/reset/tăng quota. Qwen hoãn HTTP 403; LlamaParse không tạo job mới; Argon research only.

### C. Docker inventory/cleanup — PASS trong phạm vi an toàn

Đã inventory toàn bộ 51 image IDs và tham chiếu của 31 containers (running và stopped), bảo vệ current/accepted/rollback. Không có old project image không tham chiếu đủ điều kiện xóa; **0 image bị xóa bằng cleanup**. Giữ toàn bộ image không rõ ownership, dự án khác, PostgreSQL, cache và volumes. Hai tag `local` được build thay source theo quy trình Docker; không ghi việc thay tag là cleanup thu hồi storage.

Host trước/sau: 51 images, 39,39 GB; 31 containers; build cache khoảng 47,55 GB. Volume allocation thay đổi trong quá trình test (6,950 → 6,677 GB), không xóa volume và không quy biến động này thành dung lượng thu hồi. **Physical bytes reclaimed: NOT VERIFIED**. Other/unknown image IDs giữ nguyên; 4/4 healthy, lịch sử/evidence/exports và quota kiểm tra lại PASS. Inventory runtime/receipts nằm ngoài Git.

**Cổng A và B đạt.** Được bắt đầu Giai đoạn 3 theo prompt mới trên feature branch; main chỉ giữ UX/release đã nghiệm thu. Chưa có code hoặc kết luận nghiệm thu Assistant trong mốc này.

## P. Assistant, automation và release candidate — 30/10/2026

### A. UX merge và Git

Cổng A/B được hoàn tất trước dòng code Assistant đầu tiên, bằng chứng chi tiết tại mục O. Main trước `0b9421e`, merge UX `--no-ff` tại `5f358c487f7f29482951aff1cc5aa757a5f9f1ec`, báo cáo main tại `eefdd4441d7f7ef52b08e7d35d3c68894de191dd`; đã push/fetch chính thức. UX HEAD `4b854c6` là ancestor; branch đã xóa an toàn sau kiểm tra không có PR/unique commits. Hai acceptance tags cũ không đổi. Giai đoạn 3 chỉ trên `codex/assistant-automation`, từ main đã nghiệm thu; không merge vào main.

Các nhóm đã commit/push: `9ffbf0f` (tools/FactSet/validation), `482ee1c` (hội thoại/queue), `ff00ec9` (panel/workflow), `9c565a6` (templates/restore verification), **`9802545b8a0281cc608f29d1d8b4ffd3444c454b`** (visible context/recovery docs). Commit bàn giao sau cùng chỉ cập nhật tài liệu; runtime vẫn ghi đúng source code `9802545`. Không force-push, worktree, clone, dependency/framework hay Compose project mới.

### B. Docker và phiên bản runtime

| Thành phần | Image ID cuối | Trạng thái |
| --- | --- | --- |
| Backend/Worker | `sha256:a81b192d549497881249036c717d577cf130fe16a46d137351cb6a98f7a1f357` | Chung image, `candidate-9802545` |
| Frontend | `sha256:453b653abb403b4965989951b796eec73eda0a5d512e79cba487a91ff2c3ae2b` | `candidate-9802545` |
| PostgreSQL | `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` | Giữ nguyên image/volume |

OCI source chính thức và revision `9802545` đã đối chiếu; **40 tracked source hashes** trong cả Backend/Worker và **6 frontend assets qua HTTP** khớp build local. 4/4 healthy; chỉ `127.0.0.1:18180`, không publish Backend/PG. Giữ nguyên `ai-reconciliation-studio_postgres_data`/`ai-reconciliation-studio_artifacts` và network. Runtime candidate không được gọi là accepted main.

Giữ hai image main `accepted-main-5f358c4` (IDs tại mục O) và bộ `rollback-e025094`, không ghi đè. **Rollback drill PASS LOCAL**: chạy main trên schema additive bằng `tools/rollback.ps1`, kiểm lại historical golden/evidence/CSV/XLSX, quay lại candidate và đối chiếu metadata/artifacts/hội thoại không đổi. Startup override chỉ tránh Alembic cũ không biết revision mới; không downgrade/xóa schema hay financial data.

Inventory cleanup tại Cổng B: **0 image được xóa**, không có candidate đủ điều kiện. Cuối nhiệm vụ Docker host có **53 images/39,39 GB, 31 containers, 36 volumes khoảng 7,19 GB, build cache khoảng 47,57 GB**; các số là toàn host, không phải riêng ứng dụng. Không prune cache/volumes/unknown/other-project images. Physical bytes reclaimed **NOT VERIFIED**, không nhận biến động allocation làm dung lượng thu hồi. Đối chiếu cuối thấy **45/47 image ngoài dự án giữ nguyên ID, hai image ngoài dự án đổi ID tại các tags đang có** trong thời gian nhiệm vụ; không có thao tác sửa/xóa của nhiệm vụ này lên chúng. Nguyên nhân/chủ thể thay đổi và tính ổn định của hai image ngoài phạm vi: **NOT VERIFIED**; không tự khôi phục hoặc can thiệp. Bằng chứng kiểm inventory ở Cổng B vẫn là checkpoint lịch sử, không suy ra toàn host bất biến đến cuối nhiệm vụ. Các bộ image chính/rollback của ứng dụng được kiểm lại, không đổi.

### C. Chức năng Giai đoạn 3

| Hạng mục | Kết quả thực |
| --- | --- |
| Bảy typed read-only tools | **PASS LOCAL/CONTRACT**: allowlist đóng; auth/workspace/project/run/case/group, pagination, SQL/evidence timeouts; không SQL/code/path/write tools từ model |
| Verified AnswerFactSet | **PASS LOCAL**: content hash, business scope, snapshot/period/currency/rule revision, group/member/source refs; copy đúng số liệu đã verified |
| Answer validation/Gateway | **PASS LOCAL + PASS MOCK**: model chỉ chọn facts/claim codes; reject fake IDs, amounts/prose ngoài schema và unsupported claims; dùng một Gateway, một HTTP attempt tối đa khi được phép |
| Contextual panel | **PASS LOCAL E2E**: sidebar, dataset/run/group/case, source citations/evidence/rule/report; abort/sequence chặn stale responses; phân biệt facts, supported interpretation, hypothesis, unknown/insufficient |
| Persistent conversations | **PASS LOCAL/PG**: private theo actor/project, immutable context, messages/claims/refs/timestamps, cursor pagination, reopen, idempotency, xóa nội dung/tombstone/audit đúng quyền |
| Language workflows | **PASS LOCAL**: yêu cầu hai/ba nguồn tạo review proposal; thiếu năm/kỳ/coverage hỏi xác nhận; chọn READY sources/rule đã duyệt; hai cặp cho ba nguồn; reuse qua API cũ, kiểm signatures, idempotency; vẫn phải kiểm tra/lưu/duyệt trước run |
| Smart suggestions/cache | **PASS LOCAL**: navigation evidence/exception/rule/data/report; reuse chỉ deterministic answer cùng context/FactSet/question, không cache mơ hồ thành confirmed |
| Cost/security/reliability | **PASS LOCAL + MOCK** trong các cases bên dưới; không reset quota, không blind retry khi delivery chưa rõ, không duplicate response/action |

Migration additive duy nhất `create_conversations` thêm `conversations` và `conversation_messages`; historical migrations không đổi. Backend module chính: `contracts/assistant.py`, `assistant_tools.py`, `assistant.py`, `assistant_api.py`, `assistant_jobs.py`; frontend: `AssistantStudio.tsx`, `AssistantWorkflow.tsx`, `assistantTypes.ts`, integration nhỏ trong App/ReconciliationStudio/Modal. Dùng queue/auth/session/AI Gateway/API approved templates có sẵn; không sửa matcher, verifier, normalization, tiền, semantic contracts, lockfiles hoặc kế hoạch ba giai đoạn.

### D. Kiểm thử và hiệu năng

- **176 backend PASS / 0 FAIL / 0 skipped**: 138 offline + 38 PostgreSQL trên UUID schemas thuộc PG hiện có. T01–T40 nằm trong suite, không cộng thêm. Lượt runtime backend tại `9c565a6`: 60,34 giây; Backend/migrations không đổi byte sang source cuối `9802545`, source/container hashes đã xác minh. Một cảnh báo deprecation Starlette/TestClient/httpx còn giữ, không đổi dependency ngoài nhiệm vụ.
- **54 Playwright PASS / 0 FAIL / 0 skipped / 0 flaky**, 145,758 giây trên images `9802545`: 9 foundation + 25 UX + 7 reconciliation + 13 Assistant. TypeScript, ESLint, production build, Ruff toàn backend/tests/tools, mypy **37 source files**, diff và repository/credential/history/Markdown scans PASS.
- T36–T40: cloud OFF không request; ID/claim giả reject; cross-project/actor/cursor và late response không leak; missing metric không tạo KPI; delivery **12.75 − 10.00 = 2.75 VND**, Shopee delta **10.00**, TikTok **EQUAL** đúng oracle, không bịa phí/nguyên nhân. Tests transport Gemini thành công/timeout/invalid output dùng **MOCK**, không phải live.
- Luồng ba file thực: upload UI ba fixtures mới → approval/normalization qua API có auth → đề xuất hai cặp → UI xác nhận nguồn/kỳ/coverage → kiểm tra/lưu/duyệt → verified run → hỏi vì sao lệch → export CSV. Suite foundation riêng tiếp tục kiểm Smart Setup/approval/normalization trên UI; suite reconciliation kiểm evidence/review/CSV và XLSX. Không dùng fixture chứa lỗi như nguồn READY, không sửa oracle để tạo mismatch giả.
- SIGKILL worker normalization **75.000 dòng PASS LOCAL**: reclaim đúng 2 attempts, 1 canonical, raw hash không đổi; toàn pipeline upload/approval/crash/recovery/publish **14,734 giây**, khoảng **5.090 dòng/giây quan sát được**, không coi là throughput steady-state. PG tests Assistant kiểm stale fencing, idempotency, delete pending, unknown delivery/reservation hold và đúng một response.
- Responsive tại 390/768/1366/1440/1920, keyboard/close/focus, error/retry, history/context, source/evidence checks PASS. Đã xem screenshots 390/1440 và capture 768 với dữ liệu tổng hợp ngoài Git; không tuyên bố chứng nhận toàn bộ WCAG.

Benchmark tổng hợp trên Ryzen 5 7535HS (6 cores/12 threads), khoảng 16 GB RAM, Polars 2 threads; worker concurrency 1, không GPU/model inference. Foundation và exact matching chạy local; evidence/SQL trong Backend hiện có. p95 bên dưới là quantile quan sát từ mẫu nhỏ, không phải SLA:

| Khối lượng | Parse p50 ms | Profile p50 ms | Normalize/write p50 ms | Match p50 ms | Verify p50 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1.000 | 33,82 | 6,07 | 64,54 | 32,69 | 18,10 |
| 10.000 | 43,05 | 21,28 | 419,61 | 348,46 | 267,63 |
| 50.000 | 67,24 | 94,16 | 1.671,75 | 2.624,05 | 2.006,15 |

Ba repeats mỗi size. Foundation count là dòng một nguồn; match count là tổng hai nguồn (25.000 mỗi phía ở size 50k), không so các cột như cùng một workload. Peak process lần lượt tối đa 174,31 MiB foundation và 318,71 MiB matcher/verifier. Ở 50k, p95 quan sát parse/profile/normalize là 68,13/97,44/2.145,93 ms; match/verify 2.695,42/2.006,62 ms.

Evidence benchmark 10 samples/size **1k/10k/50k nhóm**: p50 **32,506/36,328/30,696 ms**, p95 **71,100/42,424/33,567 ms**, peak tối đa **297,20 MiB**. Size 50k nhóm tương ứng 100k source records chỉ trong read benchmark; chưa đo full pipeline 100k. Trên run tổng hợp hiện có, summary tool p50/p95 **1,016/2,611 ms**, FactSet **4,004/6,841 ms**; SQL EXPLAIN actual **0,036 ms**, estimated cost **6,35**, shared hits **6** (không phải chi phí tiền). Conversation reopen/render một sample mỗi viewport 390/768/1440: **1.122/1.170/513 ms**; cache contract/hits được test, chưa có production cache-throughput benchmark. Toàn bộ benchmark **0 cloud request**, cost để null khi không có receipt; không suy ra precision/recall/99% accuracy từ exact/golden fixtures.

### E. AI policy và usage cuối

- Gemini mặc định **`gemini-3.5-flash-lite`**, durable HTTP attempts vẫn **7/10, còn 3**; không reset/tăng allowance. **Assistant Gemini live: DEFERRED theo chỉ định không dùng quota**; transport chỉ PASS MOCK.
- **Assistant cloud false, task budget 0**. Facts/answers tại local là **DETERMINISTIC/CACHE**, không gắn nhãn Gemini live. Durable task reservation giữ cùng transaction/global lock; failure ghi reservation đã biết, tokens/cost thiếu để null.
- Qwen `knowledge`: **DEFERRED vì HTTP 403 lịch sử**, không probe/call lại. LlamaParse tạo job **OFF**, hai document reservations giữ nguyên; tests đọc cached PDF/DOCX, không request/credit mới. Argon **research only**, không adapter/env/budget/fallback.
- Trace hiện có 47 rows gồm 30 Assistant deterministic/cache outcomes cộng 17 traces cũ; trace không đồng nghĩa cloud request. Thực tế `ASSISTANT_REQUEST_RESERVED=0`, `GEMINI_REQUEST_RESERVED=7`, `LLAMAPARSE_DOCUMENT_RESERVED=2`.

### F. Dữ liệu, persistence và backup/restore

Toàn bộ ID, metadata hashes và file SHA256 trong snapshot trước nhiệm vụ giữ nguyên sau nhiệm vụ. Chỉ thêm fixtures tổng hợp; **28 projects lịch sử còn đủ**, cộng 1 project TEST rõ ràng cho worker recovery, tổng **29 TEST / 0 WORK / 0 UNKNOWN**; không xóa/hide dữ liệu để giảm counts.

Snapshot cuối: **57 datasets/versions, 55 tables, 114 schemas/mappings, 52 canonical, 228 jobs/233 attempts, 236 audits, 34 plans/27 contracts/27 runs, 97 cases/47 exports, 30 conversations/60 messages**. Published bytes: **218 foundation artifacts + 27 run artifacts + 47 export files**. Không có jobs active; không còn restore schema do drill tạo.

`check-persistence.ps1` trên candidate cuối: **3/3 metadata/artifact comparisons PASS** (restart, recreate cả bốn, frontend-only recreate), **3/3 fail-closed checks PASS** trước loopback re-verification. Hội thoại/FactSet/citations được mở lại sau các thao tác và rollback round-trip. Local Dashboard không nhập token, auth/Origin/CSRF không bị bỏ.

**Backup/restore PASS LOCAL** cuối cùng:

- Backup ID **`backup_5ba8a4af594445098e6ab2010ed0d807`**, receipt **10:48:45 +07 ngày 30/10/2026**, schema `create_conversations`.
- Transaction snapshot phản chiếu **23 bảng / 2.277 metadata rows** tại thời điểm backup (bao gồm sessions, quotas/audits, approved rules, snapshots và conversations); **292 published files** khớp checksum. Metadata SHA256 **`c6ed1eb238640b69fe7213e9610ec99df2d0f9a5e25032742d72cddbdc8000dd`**.
- Backup **1,243 giây**, restore/validation **1,358 giây** đo trên local. Restore vào UUID schema trong PostgreSQL hiện có; đối chiếu đủ metadata và bản sao file rồi chỉ dọn schema/copy do drill tạo. Production metadata/artifact bytes trước/sau không đổi. Corrupted metadata checksum và path traversal bị từ chối.
- Backup trên volume đã copy cả metadata/manifest/files ra host dưới `runtime/backups/` và kiểm lại toàn bộ hashes. Không commit backup/runtime/screenshots/secrets. Baseline pg_dump/artifacts trước migration cũng được giữ ngoài Git. **Off-host encrypted backup và ghi đè production restore: NOT VERIFIED/chưa thực hiện**, không nhận local drill là cam kết DR production.

### G. Lỗi đã sửa và giới hạn bàn giao

1. **DetachedInstanceError sau rollback ORM**: giữ conversation ID độc lập, fence và kiểm membership/tombstone lại trước atomic publish; regression queue/recovery PASS.
2. **Shortlist che mẫu cũ hợp lệ**: UI lấy danh sách approved templates từ API scoped, không dùng shortlist làm quyền; thêm pending-plan pagination trên metadata sẵn có để mở lại action sau khi đóng panel. Workflow E2E PASS.
3. **Context sidebar thiếu dataset/run đang xem**: truyền đúng ID thuộc project, không trộn dữ liệu khi đổi scope; dataset/run/case/late-response regressions PASS.
4. Bổ sung idempotency cho reuse API và giữ explicit request key phía client; resend cùng nội dung không nhân action, khác nội dung 409. Xóa hội thoại đang chờ không được resurrect bởi worker.
5. Sửa harness kiểm backup codec để copy đúng helper vào container hiện có. Các lỗi test-only TikTok không có mismatch, nguồn PARTIAL không READY và focus assertion phải chờ lifecycle đã được sửa theo oracle/contract; không sửa tiền hoặc hạ validation để PASS.

Giới hạn còn lại: Assistant hỗ trợ intents facts/workflow có giới hạn và claim allowlist, không phải chatbot suy luận tự do; nhóm quá 100 evidence cần UI phân trang, sources/templates vẫn theo caps hiện có. Chưa có automatic retention, model quality/precision/recall đại diện, full-pipeline 100k, production load/HA/off-host DR hoặc chứng nhận bảo mật/WCAG toàn diện. API auth ngoài loopback vẫn cần quy trình deployment riêng. Không gọi live provider để che các giới hạn này.

**Hoàn tất triển khai và kiểm chứng candidate Giai đoạn 3 trong phạm vi demo local/manual/mock đã được giao; Gemini Assistant live/Qwen live được hoãn rõ ràng.** Source đã push trên feature branch, main giữ UX được nghiệm thu. **DỪNG sau bàn giao; chủ dự án quyết định nghiệm thu và merge Giai đoạn 3 bằng nhiệm vụ riêng.**

## Q. Product UX và reliability — nhiệm vụ ngày 30/10/2026

### A. Phạm vi và kiểm toán giao diện

Nhiệm vụ mới tiếp tục trên `codex/assistant-automation`, baseline source `3f079150ee14545fcb5fc77197f9104788f68abe`, main `eefdd4441d7f7ef52b08e7d35d3c68894de191dd`, runtime ban đầu `9802545b8a0281cc608f29d1d8b4ffd3444c454b`. Baseline 176 backend/54 E2E là lịch sử, không dùng làm kết quả mới. Một repo/Compose và volumes hiện có; không gọi cloud, thay engine, công thức, semantic contracts hoặc kế hoạch ba giai đoạn. Yêu cầu mới **chính thức cho phép Assistant thành trang riêng**, thay panel bên phải tại kế hoạch §28 và thiết kế của mục P; không sửa kế hoạch để che thay đổi được chủ dự án chỉ định.

Nguyên tắc: một vùng làm việc chính, ngữ cảnh nhìn thấy được, hướng dẫn mở khi cần, thông tin quyết định được giữ trước phê duyệt. Điều hướng dùng History API hiện có của trình duyệt, không thêm router/dependency; tham khảo [MDN History API](https://developer.mozilla.org/en-US/docs/Web/API/History_API/Working_with_the_History_API). Nút thu gọn dùng trạng thái expanded/controls theo [W3C Disclosure](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/), không nhận đây là chứng nhận toàn bộ WCAG.

| Màn hình / phân loại | Bằng chứng, nguyên nhân và ảnh hưởng | Giải pháp / ưu tiên | Kiểm chứng hiện tại |
| --- | --- | --- | --- |
| Assistant — design improvement | Browser thật 390/768/1440: Modal side che trang, lịch sử nằm trên transcript, ô nhập trôi theo hội thoại | Trang trong AppShell, lịch sử riêng và transcript cuộn, composer cố định vùng; P0 | PASS LOCAL; regression baseline FAIL trước sửa, page/focus/composer ở5viewport PASS sau sửa |
| Điều hướng — confirmed UI bug | App chỉ có useState page, không history; bản nháp mất khi unmount; requested run bị thay nếu ngoài trang lịch sử | URL identifiers + back/forward, restore qua API, bản nháp theo scope trong tab, giữ lượt được yêu cầu; P0 | PASS LOCAL; draft/reload/project switching/run ngoài trang/delayed Back/selected case regressions |
| Thanh dự án — usability issue | Cảnh báo TEST dài bên ngoài selector, phạm vi nghiệp vụ lặp lại | Bỏ cảnh báo, nhãn TEST nhỏ, refresh icon, giữ filter/owner classification; P0 | PASS LOCAL/MOCK; selector regressions và hành trình owner classify TEST qua UI |
| Tổng quan — design improvement | Ba thẻ hướng dẫn hiện cả project đang làm việc | Thu gọn khi có dữ liệu, mở sẵn cho project mới; P1 | PASS LOCAL/MOCK; DTO/next action/recent5, empty/error/loading/partial/scope |
| Dữ liệu / Mapping — accepted limitation | Bố cục đã có sheet/paging/raw/canonical/errors, review trường và semantics; không cần đổi parser hay mapping | Bảo toàn gates; kiểm lại luồng thực tế và responsive; P1 | PASS LOCAL CSV/XLSX, T01–T16; PDF/DOCX adapter MOCK và cached read, không gọi live mới |
| Đối soát — usability issue | Khóa/chỉ tiêu thiết yếu bị đóng trong details; tiến trình chỉ ghi bốn bước | Mở mặc định khóa/chỉ tiêu, diễn giải năm bước; giữ xác nhận kỳ/timezone/coverage và approval; P1 | PASS LOCAL/manual và Planner MOCK; golden/schema/approval regressions |
| Ngoại lệ — integration limitation | Case DTO không có key/amount; GET matches có paging khác, không thể ghép hai trang độc lập để đủ 25 cases | Bổ sung summary theo đúng group IDs của trang case, một truy vấn tham số hóa, backend trả số tiền gốc; P1 | PASS PG/UI: 12.75/10.00/2.75, case filter scoped/limit1, quay về case và xem tất cả |
| Báo cáo / ngoại lệ rỗng — usability issue | Lịch sử và bộ lọc đứng trước kết quả; không run vẫn hiện bảng rỗng | Lịch sử thu gọn; empty CTA thiết lập; selected run giữ khi ngoài trang lịch sử; P1 | PASS LOCAL/MOCK; UI downloads CSV/XLSX đọc lại, đúng run/period/snapshot/oracle |
| Cài đặt — accepted limitation | Policy/quotas đọc từ backend, không có quyền sửa secrets; còn thông tin kỹ thuật | Kiểm quyền, quota và trình bày progressive disclosure trong phạm vi hiện có; P2 | PASS LOCAL read-only; basic/advanced và quota thật, không giao diện sửa secrets/budget |
| Cloud / production / trên 100 thành viên — accepted limitation / out of scope | Cloud OFF, caps evidence công bố; chưa có benchmark hoặc off-host DR production | Giữ cap/warnings và ghi NOT VERIFIED, không dựng framework hoặc gọi provider để che giới hạn | Không dùng PASS mock thay PASS live |

Snapshot trước nhiệm vụ: 29 projects, 57 datasets/versions, 55 tables, 114 schemas/mappings, 52 canonical, 27 contracts/runs, 34 plans, 97 cases, 30 conversations/60 messages; 218 foundation artifacts + 27 run artifacts + 47 exports. Hash metadata/bytes đã lưu ngoài Git ở `runtime/product-ux-before.json` để đối chiếu; không xóa fixtures lịch sử. Số liệu cuối và kết quả kiểm thử sẽ ghi sau khi thực thi.

### B. Kiểm tra candidate và lỗi truyền request

Source `f6aa092376e8174889a277cceda3d10c602e9673` đã commit/push, build từ Git sạch; 4/4 service healthy, 40 tracked backend files trong cả backend/worker và 6 assets HTTP khớp hash. PostgreSQL giữ image/volumes, các image main/candidate/rollback được bảo vệ không thay đổi. Bộ backend trên container **190 PASS, 0 FAIL/SKIP**, 79,10 giây: 152 offline + 38 PostgreSQL. Gồm 12 câu hỏi kiểm phạm vi facts, bảy tools từ chối workspace lạ và cap 100/101 thành viên trên Parquet thật. Đây là local/mock, không phải live AI.

Lượt browser đầu **47 PASS / 9 FAIL / 0 SKIP**, 320,66 giây. Lỗi harness sau thay đổi thiết kế: `.first()` trỏ vào trạng thái trong lịch sử đã đóng, sidebar mobile bị ẩn, thao tác mở details lại đóng phần đã mở mặc định, fixture runs nằm ở trang hai khi lịch sử tăng. Điều chỉnh selectors để kiểm badge của selected run, expanded semantics và thao tác phân trang thật; giữ oracle và gates.

Kiểm tra bổ sung tái hiện **lỗi thực tế**: server đã nhận câu hỏi nhưng response bị mất; reload rồi gửi lại tạo job ID khác vì request key chỉ nằm trong ref của React. Regression `unknown message delivery keeps its idempotency key after reload` **FAIL trên runtime f6aa092** với hai job ID khác nhau. Sửa client lưu cặp body/key và key tạo hội thoại trong sessionStorage theo actor/project; response chưa rõ không tự resend, user resend cùng nội dung dùng key cũ. Không đổi queue/Gateway/budget. Bản sửa đang chờ browser replay; không ghi PASS trước khi chạy.

Candidate tiếp theo `bffd5743f0753a8c39584fe001bbe925f7405b32`: **57/58 E2E PASS**, một lỗi selector trong test hành trình mới (`getByLabel` với select có options); chuyển sang role combobox đúng accessible name, không đổi ứng dụng/oracle. Replay riêng hành trình **1 PASS / 26,4 giây**. Regression lost response/reload PASS, backend trả cùng job ID; workflow ba nguồn thử lỗi cặp thứ hai rồi retry cùng keys, vẫn chỉ hai đề xuất và cần người duyệt, PASS. Reports đưa export lên gần selected run/period; Exceptions ưu tiên danh sách thay biểu đồ; thuật ngữ comparison được diễn giải bằng tiếng Việt với bản gốc thu gọn.

Audit race bổ sung: `navigation cancels a delayed Back restore without leaving the page inert` **FAIL trên runtime bffd574**. Khi Back đang GET project, user chọn trang khác làm abort effect; cờ restoring không được giải phóng do guard chỉ nằm trong effect cũ. Sửa navigation sequence chung, hủy hiệu lực restore cũ khi user điều hướng và giải phóng cờ ngay; response cũ không chọn lại project. Đang chờ replay của bản sửa; không bỏ inert/fail-closed hoặc nới quyền API.

Candidate `fc3d959b286dbc12fd3ca18ab97921cbc3b1cbc9`: **59/59 E2E PASS, 0 FAIL/SKIP**, 234,41 giây; race Back/sidebar/new navigation, request idempotency sau reload, partial-pair workflow retry và hành trình mới đều PASS. Bổ sung cuối cho việc trở về đúng case sau reload: `case_id` filter scoped cùng run/workspace, selected case có trạng thái rõ và nút xem tất cả, không suy case từ hai trang khác nhau. Source PostgreSQL full replay sau bổ sung **190 PASS / 0 FAIL/SKIP**, 71,32 giây. Đang chờ build/replay bản source cuối và các drill vận hành trước khi kết luận nhiệm vụ.

### C. Kết quả kiểm thử source cuối

Source ứng dụng **`446d0312048cb0fe70052944e6972d28cf7bf773`** đã commit/push, build từ Git sạch. Không thêm dependency, migration, queue, framework, engine hoặc implementation Assistant thứ hai. Backend chỉ bổ sung case summary/filter scoped để tích hợp UI và sửa câu hướng dẫn EVIDENCE_LIMIT vốn ngụ ý UI đã có phân trang đầy đủ. Semantic/financial contracts giữ nguyên.

| Kiểm tra mới thực thi | Kết quả |
| --- | --- |
| Full backend trên backend/PostgreSQL hiện có | **190 PASS, 0 FAIL/SKIP / 63,08 giây**: 152 offline + 38 PostgreSQL; baseline176 tăng14 cases (12 câu hỏi + cap100/101); các assertions PG bổ sung nằm trong case cũ |
| Full Playwright MANUAL trên Nginx candidate | **59 PASS, 0 FAIL/SKIP/flaky / 200,11 giây**: 9 foundation + 25 interface + 7 reconciliation + 17 Assistant + 1 journey; baseline54 tăng5 cases; không cộng replays |
| TypeScript / ESLint / production build | PASS; 6 served files, không thêm thư viện |
| Ruff / mypy / source sanitization | PASS; mypy33 source files, repository scanner129 source candidates; Markdown paths và `git diff --check` PASS tại nhóm source cuối |
| T01–T40, golden/property/security/migrations/worker fences | PASS trong bộ190; UUID test schemas trên PostgreSQL sẵn có, không Compose test project/server mới |
| Read-back CSV/XLSX và independent oracle | PASS: snapshots/identity/membership/population/cases/exports của Shopee, TikTok, delivery; không dùng Matcher hoặc AI làm oracle |
| Worker recovery local thực tế | PASS: SIGKILL giữa normalize75.000 dòng, expire đúng lease tổng hợp, reclaim2 attempts, **1 canonical**, raw checksum giữ nguyên; 19,750 giây gồm toàn luồng, không gọi là throughput ổn định |

Lỗi đã được regression xác nhận và sửa: thiếu page/history state, mất bản nháp khi unmount, selected run bị thay bởi trang lịch sử, mất request identity sau reload, delayed Back restore làm main inert, thiếu selected-case navigation. Thiết kế được cập nhật: toolbar project gọn/TEST badge, hướng dẫn thu gọn, khóa/chỉ tiêu mở sẵn, lịch sử runs thu gọn, export gần selected run/kỳ, Exceptions ưu tiên danh sách có key/số tiền; Settings chia cơ bản/nâng cao. Mapping/parser/normalization/verifier không được viết lại.

### D. Browser QA và số đo UX

**PASS LOCAL** cho 35 captures của 7 trang ở **390/768/1366/1440/1920**, 0 uncaught pageerrors và không tràn viewport ngang. Kiểm tra ảnh thực tế: sidebar active/breadcrumb, hàng project, Assistant có transcript/history/composer riêng, history đóng/mở, Reports/Exceptions, Settings và các bảng. 12 captures bổ sung cho empty/loading/error/viewer/permission denied/long content ở390/1440 là **MOCK scoped GET**; không coi đây là kết quả authorization server. Quyền thật được kiểm ở PG/E2E. Mapping/PARTIAL source và evidence được mở từ dữ liệu tổng hợp thật; viewport390×600 vẫn có composer trong bounds. Chưa xác minh bàn phím hệ điều hành mobile hoặc screen reader thực; không tuyên bố chứng nhận toàn bộ WCAG.

Ảnh và receipts ở `runtime/screenshots/`, `runtime/product-ux-visual.json`, `runtime/product-ux-states.json`, không đưa vào Git. Lịch sử hội thoại hỗ trợ duyệt từng trang20 và resume, có cap UI rõ; chưa có server search hội thoại. Nhóm lớn hơn100 bị Assistant từ chối kết luận; evidence UI công bố cap100 thành viên/20 ô, export giữ lineage đầy đủ. Không giả vờ đã triển khai pagination toàn evidence.

Số đo serial local (Chromium headless1440×1000, full document navigation; **3 mẫu** cho mỗi điểm trừ khi ghi khác), median và khoảng quan sát:

| Điểm UX | Median / min–max (ms) |
| --- | --- |
| Dashboard | 370 / 361–3260 |
| Run history mở danh sách | 1432 / 932–1651 |
| Evidence | 319 / 288–351 |
| Mở lại conversation | 903 / 876–1425 |
| Mở dataset / trang dữ liệu đầu | 355 / 222–370 |
| Tìm project / đổi project | 1223 / 1102 (mỗi điểm1 mẫu) |

Đổi project: **7 API requests**; idle sau settle: **0 API requests / 3 giây**. Nguồn75.000 dòng: trang đầu343ms, **25 dòng được render**, total75.000 từ backend. Long chat **MOCK GET**, 200 messages qua9 lần lấy trang thêm:1010ms, JS heap20 messages23.055.488bytes →200 messages24.589.772bytes; không điều khiển GC nên không dùng để kết luận không rò bộ nhớ. Không phải SLA/load test/benchmark production. Hai lượt đo harness đầu bị loại: dùng cùng-document navigation chưa chờ settle và init script chạm localStorage ở about:blank; không sửa code/cache ứng dụng để che số đo.

12 câu hỏi bổ sung kiểm why mismatch, total variance, unresolved cases, missing counterpart, unverified run, rule, source, fee uncertainty, ba nguồn, KPI không tồn tại, foreign project và nhóm quá100. Intents chưa hỗ trợ phải trả thiếu bằng chứng/provider unavailable, không tự tính KPI hoặc suy phí. Workflow ba nguồn được kiểm ở API/E2E riêng với xác nhận người dùng, hai approved templates, partial failure và idempotent retry. Không tuyên bố mọi câu hỏi đều được chatbot suy luận tự do trả lời.

### E. Toàn vẹn dữ liệu và AI policy

**PASS LOCAL**: mọi ID và hash metadata/bytes có trong snapshot trước nhiệm vụ vẫn còn và khớp hoàn toàn. Snapshot sau tests/worker drill so với sau restart/backup/rollback round-trip cũng **bằng nhau chính xác** đối với các bảng nghiệp vụ/artifacts được `check-persistence.py` kiểm tra. Không sửa/xóa dữ liệu lịch sử, không reset quota, không đổi schema/parser/mapping/engine revisions để hợp thức hóa kết quả.

Snapshot cuối: **34 projects (34 TEST / 0 WORK / 0 UNKNOWN), 82 datasets/versions, 80 tables, 164 schemas/mappings, 77 canonical, 349 jobs/355 attempts, 329 audits, 53 plans, 38 contracts/runs, 146 cases, 64 exports, 72 conversations/146 messages, 90 traces**. Published bytes: **318 foundation artifacts + 38 run artifacts + 64 export files = 420 files**. So với trước nhiệm vụ thêm5 project tổng hợp (4 lần kiểm journey, gồm1 lượt dừng do test selector; 1 worker recovery); giữ đủ29 project trước đó. Các lần replay tạo thêm dữ liệu tổng hợp có chủ đích, không xóa để giảm counts. Long chat/performance/state mocks chỉ intercept GET, không tạo200 messages trên server.

- Gemini vẫn **`gemini-3.5-flash-lite`**, **7/10 đã dùng, 3 còn lại**; durable `GEMINI_REQUEST_RESERVED=7` trước/sau, không tăng ngân sách hay request. **0 Gemini live requests mới**.
- Assistant cloud **OFF**, task budget **0**, `ASSISTANT_REQUEST_RESERVED=0`. Câu trả lời local là DETERMINISTIC/CACHE hoặc thiếu bằng chứng, không gắn nhãn AI live.
- Qwen `knowledge` **DEFERRED do HTTP403 lịch sử**, không probe/gọi lại. LlamaParse tạo job **OFF**, durable document reservations giữ **2**; PDF/DOCX adapter **PASS MOCK/cached read**, live mới **NOT VERIFIED theo chỉ định không gọi cloud**, không có credits/request phát sinh trong nhiệm vụ. Không tìm key hoặc lấy key từ dự án khác. Argon research only, không adapter/request.
- 90 traces không tương đương90 cloud calls. Các mock transport/timeout/quota/security tests chạy trong UUID test schemas và không tác động quota production.

### F. Docker, persistence, backup và rollback

**PASS LOCAL** trên đúng Compose `ai-reconciliation-studio`, hai volumes `ai-reconciliation-studio_postgres_data` và `ai-reconciliation-studio_artifacts`. Docker cuối **4/4 running/healthy**; frontend bind `127.0.0.1:18180`, local Dashboard không nhập token. Không tắt auth/Origin/CSRF; **3/3 fail-closed** checks trước re-verification. Migration vẫn **`create_conversations`**, không thêm migration ở nhiệm vụ này.

`tools/check-persistence.ps1`: **3/3 metadata/artifact comparisons PASS** qua restart, force-recreate đủ bốn service và frontend-only recreate. Sau các thao tác, hai hội thoại thuộc hai project mở lại đúng run, saved answers/citations khớp, selected case và raw source cells đọc được, snapshot không đổi; **0 browser API mutations** khi reopen.

Backup/restore bằng helper sẵn có, không server/container mới và không overwrite public:

- Backup **`backup_1a0eba7eb2a04228a6792d4a7d9f731b`**, receipt **13:04:32 +07 ngày30/10/2026**, schema `create_conversations`.
- **23 bảng / 3.384 metadata rows** (gồm sessions, memberships, conversations/messages, rules/snapshots, audits và quota reservations), **420 published files**. Metadata SHA256 **`5ffdf4d0e54fb0d858ed732e011e1fb676ee1061711f02ce558c1d79bc299859`**.
- Backup1,899giây, restore/validation2,238giây. Restore schema UUID được đối chiếu đầy đủ rồi dọn đúng schema/copy drill; cuối cùng **0 restore schemas** còn lại. Corrupted metadata checksum và path traversal bị từ chối; production metadata không đổi trong drill.
- Đã copy toàn bộ backup từ volume ra host `runtime/backups/` và kiểm lại metadata cùng từng file SHA256. Không commit backup/data. **Off-host encrypted DR và restore đè production: NOT VERIFIED**, không suy từ local drill.

Rollback bằng `tools/rollback.ps1 -ReleaseRevision 5f358c4`: cặp main được bảo vệ lên4/4healthy, giữ schema/volumes; ba oracle và exports cũ đọc lại PASS. Startup override chỉ áp dụng compatibility đã kiểm cho additive schema, không downgrade DB. Sau đó plain Compose trả về candidate **446d031**, source/assets hash và hội thoại/evidence/case reopen đều PASS. Business snapshot trước/sau round-trip bằng nhau.

Images cuối (OCI revision/source đúng official repository, 40 tracked backend files khớp trong cả backend/worker, 6 served frontend files khớp SHA256):

| Thành phần | Image ID |
| --- | --- |
| Backend/Worker | `sha256:bd55a66b87642c2978370de5c4013120ded2b6fa6fcafab47ce2dacfd31bec67` |
| Frontend | `sha256:929002794a6d1937689f3560adac2fc7caf7323c2ce0b5b908ab8227f4fc6e6a` |
| PostgreSQL giữ nguyên | `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` |

Candidate được giữ thêm bằng hai tag `candidate-446d031`; image sizes backend156.312.351bytes và frontend25.824.956bytes (Docker reported size, không phải exclusive disk usage). Sáu references main/candidate9802545/rollback trước nhiệm vụ vẫn đúng IDs cũ. **Không prune/xóa image/cache/volume**, không dọn tài nguyên toàn host hay tác động project khác.

### G. Git và tài liệu bàn giao

Các nhóm source hợp lệ đã commit/push trên **`codex/assistant-automation`**: `f6aa092` (Assistant page/scoped results), `bffd574` (request identity/result actions), `fc3d959` (cancel stale restores), **`446d031` (selected exception navigation, source đang chạy)**. Remote chính thức `https://github.com/MinhHoang1403/AI-Reconciliation-Studio.git`. Báo cáo và tài liệu hành vi được commit riêng sau kiểm tra; hash commit bàn giao và trạng thái local/remote được báo trong câu trả lời cuối, không tạo hash tự tham chiếu trong file.

Main local/origin giữ **`eefdd4441d7f7ef52b08e7d35d3c68894de191dd`**; không merge main, force-push hoặc di chuyển tags. Chỉ tài liệu hành vi/report được chỉnh sau source446d031; runtime không giả nhận hash commit tài liệu là image revision. README sửa câu lỗi thời “chat chưa triển khai” và phân biệt Planner live lịch sử với đợt này local/mock; Testing Guide cập nhật counts/catalogue. Không sửa kế hoạch ba giai đoạn.

### H. Kết luận và giới hạn

**HOÀN TẤT PRODUCT UX & RELIABILITY TRONG PHẠM VI DEMO LOCAL/MANUAL/MOCK ĐƯỢC GIAO.** Các lỗi xác nhận trong phạm vi đã sửa và regression đạt; không còn FAIL đã biết của suite cuối. Candidate sẵn sàng để chủ dự án đọc báo cáo và review trực tiếp, **chưa tự merge main và không tuyên bố production ready**.

Giới hạn giữ công khai: intents Assistant/claim allowlist có giới hạn, không chatbot suy luận tự do; duyệt history theo trang, chưa server search; evidence caps và catalogue/template caps hiện có; native mobile keyboard/screen reader/full WCAG, production load/HA, representative model precision/recall, retention tự động và off-host DR chưa được xác minh. Bản nháp lưu trong tab, đóng tab có thể mất; đây không phải backup hội thoại. Các giới hạn này không được gắn PASS live hoặc giải quyết bằng cloud/framework ngoài phạm vi.

**DỪNG TOÀN BỘ CÔNG VIỆC SAU BÀN GIAO. Chờ chủ dự án review và giao nhiệm vụ riêng; không tự merge hoặc bắt đầu giai đoạn tiếp theo.**

## R. Acceptance, repository consolidation và Docker release — 30/10/2026

### A. Nghiệm thu trải nghiệm — PASS LOCAL / PASS MOCK theo từng trường hợp

Ủy quyền mới yêu cầu nghiệm thu rồi hợp nhất `codex/assistant-automation`, build main và dọn images an toàn; thay thế điểm dừng không merge của nhiệm vụ Q. Tuy nhiên prompt mới cũng bắt buộc: **nếu gate bắt buộc thất bại thì không được vượt qua bằng cách hạ tiêu chí**. Planner FAIL LIVE ở mục B nên chưa được thực hiện các bước merge/release phụ thuộc. Vẫn hoàn thành các kiểm tra, sửa lỗi công cụ, cleanup cache và bảo toàn dữ liệu độc lập. Không đổi kế hoạch ba giai đoạn, kiến trúc, công thức, matcher/verifier hoặc validators.

Baseline thật: Git sạch trên feature `2971605c3cf5f06b789de35ea8f5390278e964e7`; main/local/origin `eefdd4441d7f7ef52b08e7d35d3c68894de191dd`; app runtime `446d0312048cb0fe70052944e6972d28cf7bf773`. Đã đọc Rules/AGENTS/kế hoạch/hợp đồng và báo cáo. Giữ một checkout, một Compose, hai volumes hiện có; không tìm keys ở dự án khác.

- **PASS LOCAL:** Tổng quan, Dữ liệu, Đối soát, Ngoại lệ, Báo cáo, Trợ lý AI dạng trang và Cài đặt ở390/768/1366/1440/1920:35captures, không uncaught pageerror hoặc tràn viewport ngang. Đã xem ảnh thực tế Assistant mobile, Reports desktop, Exceptions tablet; mapping/PARTIAL và composer390×600 trong bounds.
- **PASS MOCK:**12captures empty/loading/error/viewer/permission-denied/long-content ở390/1440, intercept GET có scope; không dùng làm bằng chứng quyền server. Quyền thật, CSRF/isolation/viewer denial có PG/E2E.
- **PASS LOCAL:** Hành trình project mới → CSV/XLSX → profile/mapping approval → normalize → manual rule review/approve → verified run → exception/source evidence → Assistant → export CSV/XLSX → reload. Oracle literal12.75−10.00=2.75VND; independent readback còn kiểm identity/membership/population/cases của Shopee/TikTok/delivery. Không lấy Matcher hoặc LLM làm oracle.
- Page/history/back-forward/drafts, scope switching, stale responses, request identity/idempotency, permissions/network failures và saved run/case có trong59E2E. Không phát hiện UX bug mới cần sửa ứng dụng. Keyboard/focus/contrast checks có trong suite; native mobile keyboard/screen reader/full WCAG vẫn **NOT VERIFIED**.

Ảnh mới `runtime/screenshots/consolidation-*`; receipts `runtime/consolidation-ux-visual.json`, `consolidation-ux-states.json`, `product-journey.json` và logs tương ứng, ngoài Git. Lượt E2E ban đầu sau gián đoạn gặp403 LOCAL_DEMO_NOT_VERIFIED, không ghi PASS; xác minh published loopback bằng verify-local rồi mới replay. Không tắt auth hoặc sửa timeout.

### B. Gemini LIVE — Assistant PASS, Planner FAIL

Preflight PostgreSQL xác nhận key đã cấu hình trong chính dự án, provider GEMINI/model `gemini-3.5-flash-lite`, workspace CLOUD_ALLOWED và global/workspace ceiling10. Baseline durable Gemini7, Assistant0, Planner1, LlamaParse2; không active jobs. Hai request chỉ dùng dữ liệu tổng hợp có canonical/VerifiedRun thật.

| Task / revision | Kết quả và validator | HTTP attempts / latency | Usage provider trả về |
| --- | --- | --- | --- |
| `answer_verified_question` / `assistant-grounded-1` | **PASS LIVE**: job SUCCEEDED; model chọn comparison/comparison_0 của đúng FactSet/run/snapshot; Backend render12.75/10.00/2.75VND, citations về nhóm và hai dòng nguồn; không bịa nguyên nhân, tiền hoặc thực thi workflow | **1 / 1.564ms**, không retry | Input3.454, output155; thinking/cache không có receipt, cost null |
| `propose_reconciliation_contract` / `reconciliation-planning-2` | **FAIL LIVE**: response JSON đọc được, status NEEDS_REVIEW, plan=null, có suggestions nhưng Pydantic từ chối `AI_INVALID_JSON`; job BLOCKED, không tạo proposal/contract/run | **1 / 2.168ms**, không retry | Input8.163, output436, total8.599; không suy chi phí tiền tệ |

Assistant job `179865c6-3e40-472b-8370-8dd830188a1e`, conversation `b07e67ba-0e5c-56f6-b093-9f05baa76e5d`; Planner job `169b2fd0-5c7f-4c25-9b25-8eee1f3497a7`. Receipt tổng hợp tại `runtime/consolidation-live.json` giữ IDs, trace/usage, input đã scope và response hash, không vào Git. Trace Planner chỉ giữ mã lỗi, không giữ raw response hoặc ValidationError theo trường; **nguyên nhân tại trường cụ thể NOT VERIFIED**, không suy đoán rồi sửa prompt/output. Schema gate FAIL nên semantic validation/oracle của Planner **chưa được nghiệm thu live**. Các mock tests valid suggestions/giả fields/evidence/basis/cardinality/đổi scope vẫn PASS; không thay thế kết quả live.

Harness dùng API auth/queue và production worker handlers/Gateway/reservations/validators hiện có trong backend. Dừng worker thường tạm để tránh claim race; bật Assistant cloud/budget1 chỉ trong tiến trình kiểm thử, giới hạn transport max_attempts=1 và chặn HTTP thứ hai cho mỗi job; không sửa output/validator, `.env` Assistant hoặc global/workspace ceiling. Finally bật lại worker; không tự resend khi lỗi. Chỉ đúng **2/2 attempts mới**, hết allowance của nhiệm vụ.

Durable sau thử và sau restart/backup: **Gemini9/10, còn1; Assistant1; Planner2; LlamaParse2**. Planner task lifetime cap2 cũng đã đầy; không tự nới để kiểm lại. Assistant OFF/budget0. Workspace parser đã OFF từ trước, preflight thấy env parsing vẫn true nên đã đưa `ALLOW_CLOUD_PARSING=false` và recreate đúng backend/worker; giữ nguyên key/credits/allowance/history. Không gọi parser/Qwen/Argon. Qwen **DEFERRED do403 lịch sử**; LlamaParse live mới **NOT VERIFIED theo chỉ định không gọi**, adapter/cached reads kiểm local/mock. Không ghi historical live thành request mới.

### C. Repository audit và cleanup — PASS phần an toàn

Inventory gồm tracked/untracked/ignored: **19.161 files / 3.207 directories / 792.876.283bytes** tại mốc trước kiểm tra, gồm cả Git, dependencies và runtime. Từng path có type/bytes/Git classification/role/KEEP hoặc DELETE/evidence trong `runtime/consolidation-repository-before.json`;129tracked files có SHA/import/reference/role và quyết định trong `consolidation-source-audit.json`. Đây là kiểm toán cấu trúc/static/contracts kết hợp tests, không chứng minh mọi dynamic path là dead code.

Đã rà root, `.vscode`, backend/contracts/migrations/tests, frontend/components/E2E, tools/docs, config/lockfiles, Docker và local cache/build/logs. `.agents` và `.github` không tồn tại, không tạo thay. Ruff/TypeScript noUnused/ESLint kiểm unused imports/locals; imports/references/scripts và dependency use được đối chiếu. Hai constructor có body trùng thuộc Qwen/Gemini adapters có vai trò khác nhau: KEEP, không tạo abstraction mới. Không chứng minh source/component/dependency nào thừa để xóa an toàn. Giữ Qwen adapter, migrations, contracts, Rules/AGENTS/PROJECT_PLAN và research; không chỉnh kế hoạch để khớp code.

**Chỉ xóa73generated ignored cache files, 28.799.351bytes**. Trước mỗi xóa kiểm resolved absolute path nằm trong workspace, không symlink, không Git tracked; loại trừ runtime/.git/.venv/node_modules/.vscode. Danh sách đầy đủ từng file/hash/bytes/lý do ở `runtime/consolidation-cache-cleanup.json`:

| Thư mục cache đã dọn | Files |
| --- | ---: |
| `.mypy_cache` | 18 |
| `.pytest_cache` | 5 |
| `.ruff_cache` | 7 |
| `backend/studio/__pycache__` | 23 |
| `backend/studio/contracts/__pycache__` | 4 |
| `tests/__pycache__` | 16 |

Ngay sau cleanup: **19.164 files / 3.194 directories / 774.138.120bytes**. Mốc inventory sau tests/backup: **19.702 files / 3.904 directories / 855.915.781bytes**. Gross counts/bytes gồm evidence và backup mới, Git/tool caches cũng tái tạo khi kiểm tra; không suy73file đã xóa từ phép trừ gross counts hoặc coi tăng footprint là xóa thất bại. Không xóa cache lặp để làm đẹp số cuối.

KEEP: `.env`, `.vscode`, `.git`, node_modules/.venv, dist dùng so served assets, mọi runtime logs/screenshots/exports/conversations/raw/Parquet/backups và unknown ownership. Không xóa dữ liệu tổng hợp cũ. Không gộp/xóa tài liệu có vai trò hoặc lịch sử riêng; đồng bộ các câu current-status lỗi thời về live/quota và tập trung kết luận mới ở mục R, không tạo Markdown report khác.

Lỗi công cụ thật: `tools/check-reconciliation.py --planner-live` dùng payload cũ `{project_id,plan}` trong khi API yêu cầu `request:PlanningRequest`. Tái hiện offline422 missing request/extra plan → regression FAIL trước sửa → chuyển qua typed PlanningRequest.from_plan, giữ facts đã xác nhận và không gửi join_keys/comparison rule → regression PASS. Sửa harness copy helper vào backend/tmp để PG suite kiểm đúng source. Khi đọc historical cached proposal, CLI nay ghi **PASS CACHED**, không PASS LIVE mới. Đây là sửa công cụ riêng, **không chữa được Planner FAIL LIVE**, vì live harness đã dùng payload đúng.

### D. GitHub consolidation — feature đã push; merge BLOCKED

Remote đã fetch/xác minh `https://github.com/MinhHoang1403/AI-Reconciliation-Studio.git`. Chỉ có main và codex/assistant-automation ở local/origin; main là ancestor của feature. Đã kiểm diff/scope/ancestry/history, source/public-content/known credentials/Markdown links. Feature trước nhiệm vụ có12commits nối tiếp main; giữ nguyên lịch sử, không merge theo tên branch.

Sửa công cụ/tests đã commit/push **`e8e9bcd3aeedfd329d2fec07a669cd17a5b89d25`**. Tài liệu nghiệm thu commit riêng sau kiểm chứng; hash bàn giao/local-origin verification ghi trong trả lời cuối, tránh hash tự tham chiếu. Không stage `.env`, runtime, backup hoặc binary artifacts.

**Main giữ `eefdd4441d7f7ef52b08e7d35d3c68894de191dd`**; không merge commit, không push main, không xóa feature còn chưa tích hợp. Gate live thất bại nên regression trên merge result/main mới **BLOCKED**, không giả kết quả. Hai annotated tags cũ giữ đúng ref objects `37209cb21f8f786dc4b23d316f9e0772170a6122` và `2f3cb8210568e753f85e110cbecaddecd931f81e`; không di chuyển/xóa/tạo tag nghiệm thu mới. Không force-push/reset/worktree/clone.

### E. Docker, persistence và backup — PASS LOCAL; release/cleanup mới BLOCKED

Một Compose `ai-reconciliation-studio`,4/4running/healthy, frontend127.0.0.1:18180; giữ network và hai volumes `ai-reconciliation-studio_postgres_data`, `ai-reconciliation-studio_artifacts`, migration `create_conversations`. Không rebuild PostgreSQL. Runtime vẫn **446d031**, không nhận feature docs/tools commit là image revision. OCI official source/revision,40tracked backend source hashes trong cả backend/worker và6frontend served assets khớp; receipt `runtime/consolidation-runtime.json`.

| Thành phần | Image ID còn chạy |
| --- | --- |
| Backend/Worker | `sha256:bd55a66b87642c2978370de5c4013120ded2b6fa6fcafab47ce2dacfd31bec67` |
| Frontend | `sha256:929002794a6d1937689f3560adac2fc7caf7323c2ce0b5b908ab8227f4fc6e6a` |
| PostgreSQL giữ nguyên | `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` |

**PASS LOCAL:** persistence helper kiểm3/3metadata/artifact comparisons qua restart, force-recreate toàn bộ và frontend-only;3/3demo proof fail-closed trước verify-local. Snapshot sau tests bằng chính xác sau restart và backup. Mọi ID/hash baseline vẫn còn nguyên; chỉ append fixtures/jobs/audits đã nêu. Sau restart mở lại hai scoped conversations/evidence/selected case/source cells và riêng Gemini live answer,0browser API mutations; quota giữ9/10.

Snapshot mới: **37projects,95datasets/versions,93tables,190schemas/mappings,90canonical,415jobs/422attempts,382audits,63plans,44contracts/runs,172cases,74exports,95conversations/192messages,114traces**. Published files **370foundation+44run+74exports=488**; baseline420files đều giữ SHA. Ba projects mới là hai hành trình UI và một worker drill; không xóa34projects trước. Chỉ còn1GEMINI PlanRow lịch sử, Planner lỗi không thêm proposal.

Backup mới **`backup_26fda69452d742cb8dcad9a50b62c918`**, **14:41:48 +07 ngày30/10/2026**:23bảng/3.978metadata rows (gồm798sessions),488files; metadata SHA256 **`96eb7c4e0285e4defa414c2c3e0dfeaa0bf7210bffff767da6bf169e118594e2`**. Backup1,768s, restore/validation2,477s; checksum corruption/path traversal bị chặn, public metadata không đổi. Restore UUID schema/copy drill đã dọn,0restore schemas còn lại. Copy cả backup ra host runtime/backups và kiểm metadata/từngfile SHA PASS. Off-host encrypted DR/restore đè production vẫn **NOT VERIFIED**.

Inventory host trước/sau:55images/31containers, gồm27containers ngoài project ở baseline. Giữ đủ8project image references: candidate446d031, candidate9802545, accepted-main5f358c4 và rollbacke025094 cho backend/frontend. Cặp rollback accepted-main đã có drill tương thích ở mục Q; hai IDs được kiểm lại còn nguyên: backend `7a00801051416c143e0d0199919bb9a43fa319a01fd01b1a8010b1d5d8781e29`, frontend `1049ba4457ebad8971d0be29cb523b7429714fb2c3dc1abcd28a9ef1a40ab215`. **Không có rollback drill mới hoặc main release mới trong mục R**; không lấy healthcheck thay kết quả release.

**0image deletions/0build-cache prune/0volume deletions**: gate main release chưa đạt nên chưa đủ điều kiện dọn images cũ. Không chạy global prune hoặc tác động models/caches của ứng dụng khác. Images virtual total39,39GB cả hai mốc không đồng nghĩa disk đã thu hồi; free C đo137.583.370.240→137.030.660.096bytes, có backup/evidence và hoạt động khác trên host, không quy thành dung lượng cache thực thu hồi.

Inventory cuối có23/27containers ngoài project khớp;4containers có khác biệt ID/image/mount inventory và2images ngoài project biến mất trong khoảng quan sát. Nhiệm vụ chỉ chạy mutation Compose của project này, không sửa các tài nguyên ngoài; nguyên nhân hoạt động ngoài và khẳng định toàn host bất biến **NOT VERIFIED**. Không tự sửa/xóa chúng để khớp baseline. Chi tiết local ở `consolidation-docker-before.json` / `consolidation-final-inventory.json`, không public tên/config dự án khác.

### F. Chất lượng — số liệu mới, không cộng replays

| Kiểm tra thực thi | Kết quả |
| --- | --- |
| Backend/PostgreSQL trước cleanup | 190PASS,0FAIL/SKIP,43,58s |
| Backend/PostgreSQL sau sửa/cleanup | **191PASS,0FAIL/SKIP,55,45s**;153offline+38PG, tăng1regression so baseline190 |
| Playwright trước/sau cleanup | **59PASS mỗi lượt**,0FAIL/SKIP/flaky;192,04s trước/192,85s sau;9foundation+25interface+7reconciliation+17Assistant+1journey |
| T01–T40/golden/property/migrations/security/fencing | PASS trong suite; giữ contract/oracle/monetary invariants; không cộng thêm counts |
| Ruff / mypy33modules / TypeScript / ESLint / production build | PASS; không dependency mới |
| Known credential/history/public source/Markdown paths / diff check | PASS,129source candidates; không phải chứng nhận security toàn diện |
| Export readback / independent oracle | PASS CSV/XLSX/SHA/timestamp/zero-prefix/snapshot và3pair goldens |
| Worker recovery SIGKILL | PASS75.000dòng,2attempts/1canonical/raw hash nguyên;14,875s gồm toàn journey, không là throughput ổn định |
| Persistence / backup restore / saved conversations | PASS LOCAL như mục E; không cloud mới |

Một Starlette TestClient/httpx deprecation warning còn lại. Tool runner sau thay đổi môi trường không tìm thấy pwsh được chạy lại bằng Windows PowerShell hiện có; không tính lệnh chưa khởi chạy pytest là suite PASS. Lỗi encoding ở script chỉnh tài liệu tạm đã được phát hiện và sửa UTF-8 trước scanner/commit; source ứng dụng không thay đổi.

### G. Kết luận, giới hạn và điểm dừng

**CHƯA ĐẠT NGHIỆM THU RELEASE/HỢP NHẤT — PLANNER FAIL LIVE.** Local/manual/mock regressions, Assistant live và các phần bảo toàn/cleanup an toàn đã có bằng chứng. Không dùng chúng để phủ FAIL LIVE hoặc tuyên bố production-ready. Các bước merge main, xóa feature branch, build/deploy main mới và dọn images phụ thuộc giữ **BLOCKED**, không âm thầm bỏ qua.

Cần nhiệm vụ riêng chẩn đoán Planner typed output (hiện không có raw response/chi tiết lỗi theo trường) và quyết định allowance nghiệm thu mới; nhiệm vụ hiện đã hết2attempts, global còn1 nhưng Planner lifetime cap2 đã đầy. Không tự tăng/reset cap, sửa validator hoặc retry. Giữ công khai các giới hạn Q: intents/claim allowlist, caps100evidence/20source cells/catalogue/templates, chưa conversation server search, mobile keyboard/screen-reader/full WCAG, representative model quality/precision/recall, production load/HA, retention và off-host DR chưa verified. Qwen DEFERRED, Argon research-only, không triển khai phase/tính năng khác.

**DỪNG sau kiểm chứng và commit/push báo cáo trên feature branch. Không tự merge hoặc gọi thêm Gemini.**

## S. Agent-first MVP và giao diện AI Assistant — kết quả 02/11/2026

### A. Tổng quan

**CHƯA ĐẠT NGHIỆM THU TOÀN MVP.** Giao diện bổ sung đã được triển khai và kiểm tra; backend, PostgreSQL, browser regression và các phép thử bảo toàn dữ liệu đạt trong phạm vi bên dưới. Tuy nhiên, benchmark ngôn ngữ tự nhiên vẫn có lỗi chọn ý định/nguồn/tham số. Gemini đã dùng đủ **50/50 lifetime attempts**, còn **0**. Không hạ tiêu chí, gọi thêm cloud hoặc dùng vài ca thành công để kết luận toàn Agent đạt. Merge main, release main và cleanup images sau release **BLOCKED**.

Phạm vi theo [kế hoạch Agent-first](AI_AGENT_MVP_IMPLEMENTATION_PLAN.md) và bổ sung UI ngày 02/11: một AI Assistant điều phối chuẩn hóa, đối soát, truy vấn và giải thích bằng công cụ có kiểu; giữ AppShell, logo, font, màu sáng/xanh, API cũ và manual fallback. Không thêm framework, dependency, queue, service, worktree hoặc môi trường thứ hai; không viết lại matcher/verifier/công thức. Dữ liệu gốc, lịch sử, quyền và approvals được bảo toàn.

UI hiện có landing với “Bạn muốn xử lý dữ liệu gì?”, một composer và bốn gợi ý thực; sidebar AI Assistant/Dữ liệu/Kết quả; lịch sử, run context và xác nhận xóa mở khi cần. Review tiếng Việt dùng composer chính, chỉ tạo bản diễn giải để người dùng duyệt. Trạng thái AI phản ánh policy/quota thật. Các trang chuyên dụng tiếp tục dùng được.

### B. Kiến trúc và ranh giới quyền

```text
Composer / attachments / review
  -> session + Origin/CSRF + actor/project
  -> typed intent + semantic validation
  -> durable AgentWorkflow -> finite tool registry
  -> existing PostgreSQL jobs / lease / fencing
  -> mapping review -> normalization / plan review -> matcher -> verifier
  -> typed table / chart / facts / evidence / export
```

- `agent_intents.py`, `agent_preparation.py`, `agent_jobs.py`: intent và đề xuất có kiểu, bounded context, không SQL/code tự do.
- `agent_workflows.py`, `agent_api.py`, `contracts/agent.py`: state/review/nonce/expiry/fingerprint, idempotency, khóa nguồn, resume và API theo owner. Chỉ một bảng mới `agent_workflows` qua migration additive sau `create_conversations`; không downgrade DB.
- `agent_tools.py`: tái dùng bảy read tools của Assistant; thêm profile/query/exact group lookup, prepare mapping/plan, normalize, chạy approved contract và export. **Không có tool approve cho model.** Quyết định người dùng qua API transactional dùng cùng business validators với màn hình thủ công.
- `data_query.py`, `contracts/data_query.py`: predicate/aggregation allowlist, kiểm scope/SHA, Decimal/null/currency/lineage; tổng ALL_MATCHING trước paging. Nguồn raw/canonical không trở thành KPI verified. Tiền đối soát đọc nguyên comparison/snapshot đã verified.
- `AssistantStudio.tsx`, `AgentWorkflowPanel.tsx`, `AgentResultBlocks.tsx`, `App.tsx`, `navigation.ts`, `styles.css`: một UI hội thoại, upload, review, bảng/chart/evidence, giữ các routes cũ.

Giới hạn đang dùng: 12 bước/workflow, 6 model calls/workflow, 5 tool calls/turn, 3 review OPEN/10 review lịch sử, 5 file/lần; query tối đa 100k input, 50 dòng/trang, 20 fields/8 predicates/5 aggregates/3 group fields và deadline chung 5 giây. Lineage gốc giữ đủ; hiển thị trên 100 refs/dòng phải báo bị giới hạn. Exact business-key lookup có timer 3 giây. Không đồng nhất business key với technical group ID.

Child-job finish và `agent_resume` cùng transaction. Review stale/nonce cũ/đổi quyền bị chặn; model không cấp actor/quyền và không tự phê duyệt. Cancel chỉ ngăn bước kế tiếp, không hoàn tác raw hoặc kết quả đã công bố. Delivery unknown giữ reservation và không gửi lại. Upload bootstrap chỉ khi đính kèm thật, scope `UNCONFIRMED`, không tự phân loại WORK/TEST hay reuse chéo scope.

### C. Chất lượng AI và ngân sách

Provider mặc định **Gemini `gemini-3.5-flash-lite`**. Prompt hiện tại: `reconciliation-planning-5`, `agent-intent-6`, `agent-normalization-3`, `agent-review-1`; grounded legacy `assistant-grounded-1`. Provider DTO nhỏ, `responseJsonSchema`, Pydantic và semantic validators độc lập. Diagnostics chỉ status/hash/validation loc/type/count, không log nguyên nội dung doanh nghiệp hoặc secrets.

| Phép đo | Kết quả thực tế |
| --- | --- |
| Lifetime global/demo workspace | 9 trước nhiệm vụ -> **50/50**, còn **0**, không reset |
| Requests mới | **41**, đủ 41 traces; Agent 33/33, Planner 10/10, 7 requests lịch sử thuộc tasks khác |
| Phân bổ Agent | 30 -> 33 **trong tổng 50 không đổi**, có audit; source cài mới vẫn OFF/0 |
| Live trace outcomes mới | 25 VALIDATED, 3 VALIDATED_PROPOSAL, 3 HTTP_ERROR, 3 INVALID_JSON, 1 INVALID_EVIDENCE, 1 INVALID_INTENT_COUNT, 1 INVALID_SOURCE_FIELD, 4 QUERY_SEMANTICS_REQUIRED |
| Token receipts | 38 receipts: input 197.345, output 25.049, total 222.394 tokens; không bịa usage cho receipt thiếu |
| Model latency quan sát | p50 2.367 ms, p95 5.090 ms, trộn tasks/batches/errors; không phải SLA hoặc latency cả workflow |
| Chi phí thanh toán thực | **NOT VERIFIED** — chưa có hóa đơn/receipt số tiền |
| Live parent workflows qua các vòng chẩn đoán/sửa | **16: 9 COMPLETED, 5 BLOCKED, 2 WAITING_REVIEW**, không phải 100% completion |

**Gold NLP:** 60 câu qua hai miền giao nhận và sổ cái/chứng từ, thêm 20 negative. Prompt được đo rộng là **agent-intent-5**. Lần đầu 50 measured/30 BLOCKED; sau sửa guard và repair có kiểm soát, 80/80 measured. Tổng **11 HTTP**: tám batch đầu, ba batch lỗi HTTP 200/STOP đã biết được đo mới một lần; năm batch thành công dùng cache. Job lỗi cũ/repair_of được giữ. Không repair timeout, unknown delivery, HTTP error hoặc truncation.

| Chỉ số trên replies đã lưu, rubric độc lập | Đúng / mẫu số | Tỷ lệ |
| --- | ---: | ---: |
| Intent | 68/80 | 85,00% |
| Source resolution | 53/60 | 88,33% |
| Slots/semantic requirements | 21/34 | 61,76% |
| Inferred tool dispatch | 70/80 | 87,50% |
| Safe abstention của 20 negative | 20/20 | 100% trong tập này |

Các intent chưa đúng: D11/D13/D23, L03/L05/L13/L21/L23/L25/L26, N15/N17. Các slot chưa đúng: D11/D12/D13/D20/D23/D27, L11/L12/L13/L18/L20/L21/L23. Source errors gồm over-abstention/chọn sai source kind hoặc ID; không diễn giải 7 lỗi source thành 7 cross-workspace leaks. Chưa có phép đo độc lập average clarification turns trên toàn gold; số approvals/thao tác trong luồng mẫu được báo ở mục D.

Strict negative intent là 18/20; CLARIFY và UNSUPPORTED không được coi cùng intent chỉ vì đều an toàn. Inferred dispatch không phải công cụ đã được thực thi hay workflow completion. Rubric cũ chấm nhầm D27: tự lọc PAID trước biểu đồ toàn bộ trạng thái. Đã thêm regression, chấm lại stored replies **0 HTTP**, sửa 22/34 thành **21/34**; giữ cả receipts trước/sau. Không đổi oracle để làm đẹp kết quả.

Prompt 6 sửa hướng dẫn và có **PASS LIVE một ca variance cuối**, nhưng **toàn bộ 80 câu trên prompt 6 NOT VERIFIED** vì hết quota. Không dùng kết quả prompt 5 làm bằng chứng prompt 6 đã đạt. Broad NLP quality **FAIL nghiệm thu**; full replay hiện **BLOCKED**.

Planner sau sửa có PASS LIVE NEEDS_REVIEW/PROPOSED ở cổng đầu và một luồng repaired composition -> human approval -> verified run. Normalization hai miền, NL review preview, paid query, missing-side query, variance, grounded explanation và export đã có các ca live thành công cụ thể. Những ca này không xóa các lỗi lịch sử hay chứng minh NLP tổng quát.

**Qwen `knowledge`: DEFERRED theo chỉ định, lịch sử HTTP 403**, không probe lại. **Argon: research only**, không tích hợp/gọi. **LlamaParse tạo job mới OFF**; không request mới. Lịch sử PDF/DOCX tổng hợp 28/10: 2 files/6 credits giữ nguyên; usage/credits hiện tại **NOT VERIFIED**, không tự tìm key hoặc tăng allowance.

### D. Hành trình người dùng và oracle

Mỗi miền có hai nguồn tổng hợp, mỗi nguồn ba dòng; mã `000701`/`000702` giữ số 0 đầu. Kỳ `[2026-10-01, 2026-11-01)`, timezone/coverage/currency VND và nghĩa tiền được xác nhận. Các fixtures QA được owner phân loại TEST; không tự phân loại dữ liệu người dùng.

| Hành trình | Thao tác/quyết định trong lần thử | Kết quả |
| --- | --- | --- |
| Upload từ chat | Mỗi miền 1 lần chọn hai file + 1 lần gửi | PASS LOCAL: bootstrap/parse/profile/owner/source SHA; CSV/XLSX qua E2E |
| Chuẩn hóa và review | 2 xác nhận mapping/miền, tổng **4 approvals**; nguồn giao nhận có thêm 1 reply NL tạo preview rồi human review | PASS LIVE proposal/preview; PASS LOCAL approval -> normalizer -> resume; 4 canonical READY, mỗi canonical 3 valid/0 invalid |
| Rule mới giao nhận | 1 lệnh sau vòng sửa + **1 approval rule** | PASS LIVE Planner -> review -> matcher/verifier; không auto-approve |
| Rule sổ cái/chứng từ | Rule fixture được owner setup/approve thủ công; 1 lệnh NL reuse, **0 approval mới** | PASS LIVE chọn đúng approved scope; reuse cùng run ID, không duplicate; **không phải AI tạo rule mới cho miền này** |
| Paid query | 1 câu ở ca thành công; hai ca trước over-abstention được giữ | PASS LIVE: chỉ `000701`, `000702`, tổng số 2; không coi COMPLETED là PAID |
| Query tổng/count | Stored live plan D17/D18 thực thi qua read-only API | PASS LOCAL: count 3, tổng 42,75 VND, đủ 3 lineage; không cộng từ trang preview |
| Missing và variance | Mỗi ca thành công 1 câu; variance từng bị grouping guard chặn trước sửa | PASS LIVE: B-only `000704` physical row 4; một group variance 2,75 VND, đủ hai phía |
| Chart | Một yêu cầu biểu đồ, backend trả points/units/population | PASS MOCK/contract và native query oracle; **không xác nhận broad NLP chart LIVE**, D27 đã chấm FAIL |
| Giải thích và bằng chứng | 1 câu `000702`, mở evidence, mở source cell | PASS LIVE grounded explanation, PASS LOCAL native modal: 12,75 - 10,00 = 2,75 VND, dòng vật lý 3; không bịa nguyên nhân phí |
| Export | 1 câu yêu cầu, sau đó tải file | PASS LIVE chọn tool/completed export; read-back XLSX 15.837 bytes, 8 sheets, 4 groups/6 unique members, IDs/null/snapshot khớp SHA và oracle |
| Reload/restart/recreate | Mở lại history/conversation, evidence/export; ba persistence drills | PASS LOCAL, không phát sinh AI; latest workflow chip đúng run, raw và approved refs không đổi |

Hai snapshots có **LINKED 2 / UNMATCHED 2; EQUAL 1 / AMOUNT_MISMATCH 1 / NOT_EVALUATED 2; eligible 3; full match 1/3 = 33,33%; signed/absolute variance 2,75 VND** trên hai comparable groups. Tổng nguồn A 42,75 và B 42,00 không được lấy chênh lệch 0,75 thay variance comparable 2,75. Thiếu amount ở unmatched giữ null.

Run giao nhận `decde20d-b891-42c6-a84d-1670460289f6`; run sổ cái `db4fb18a-8da6-487f-ad82-e0d4e49d5771`. Receipts local: `runtime/agent-live-{delivery,ledger}.json`, `agent-products-verification.json`, `agent-export-readback.json`; không đưa dữ liệu/runtime artifacts vào Git.

### E. Regression và UI

| Kiểm tra mới nhất | PASS | FAIL / SKIP | Bằng chứng |
| --- | ---: | ---: | --- |
| Full backend + PostgreSQL source | **248** | **0 / 0** | `runtime/agent-status-filter-tests.log`, 52,45 giây; gồm T01–T40, unit/property/oracle/security/PG |
| Full Playwright | **72** | **0 / 0**, flaky 0 | `runtime/agent-dialog-full-e2e.json`, 226,72 giây trên candidate `95d2956` |
| Ruff / mypy | PASS / 42 modules PASS | 0 lỗi | `ruff check backend tests tools`, `mypy backend` |
| Frontend ESLint / TypeScript / build | PASS | 0 lỗi | `npm --prefix frontend run lint/check/build` |
| Source/secrets/history/Markdown paths | PASS | 0 lỗi | `tools/check_repository.py`: 150 source candidates; đây không phải audit bảo mật tuyệt đối |
| Real worker SIGKILL/reclaim/Agent resume | PASS LOCAL | 0 lỗi ở drill | 75k rows, 2 attempts/1 canonical, workflow COMPLETED, raw SHA giữ nguyên, model_calls 0; 13,797 giây cả hành trình |
| Native query 75k | PASS LOCAL | 0 lỗi ở sample | 50 returned/allmatching 75.000; first ID `00074999`, physical row 75.001; một HTTP sample 132,09 ms, không cloud |

72 E2E gồm 59 cases cũ, 7 Agent cases, 1 regression late report/Back, 5 visual cases. **Không cộng 90 ảnh thành 90 tests.** Visual **PASS MOCK CONTRACT**: 18 trạng thái × 5 widths 390/768/1366/1440/1920; empty/short/long/upload/running/review/completed/wide table/chart/evidence/history/multiline/keyboard/sidebar/delete/error/permission/loading; không horizontal page overflow hoặc pageerror. Các ca backend/PG không dùng mock cho quyền/queue/normalizer/verifier; provider transports trong regression là MOCK, tách khỏi receipts Gemini LIVE.

Ảnh trước: `runtime/agent-ui/empty-{width}.png`; ảnh sau: `runtime/assistant-layout/{width}/{state}.png`. Đã xem trực tiếp các ảnh desktop/mobile/tablet ở những trạng thái trọng yếu, gồm empty/review/delete/history/table/chart/evidence/loading/sidebar/completed. Hai ảnh phác thảo được nhắc trong yêu cầu **không có trong attachment**, nên đối chiếu pixel với sketches **NOT VERIFIED**; đã đối chiếu mô tả và ảnh trước/sau thực. Keyboard viewport mô phỏng, chưa kiểm thiết bị vật lý/screen reader hoặc chứng nhận WCAG.

Các lỗi đã tái hiện, sửa và giữ regression: Planner field/rule evidence sai tầng và optional null composition; grammar provider quá phức tạp/diagnostics thiếu; intent cardinality và source IDs; paid semantics/canonical field khác metric ID; all-status chart population, enum/grouping và technical group ID; late report ghi đè URL Back; restore draft đến muộn; chip run phản hồi workflow cũ; review reply/nonce/publish/tombstone; xác nhận xóa bị khuất trong transcript; worker child/resume recovery. Không hạ validators, thay matcher/formula hoặc xóa gold failures.

Lần full backend trước có 247 PASS/1 FAIL do assertion enum đặt nhầm fixture canonical thay vì verified-run; sửa vị trí test và chạy lại full 248 PASS, giữ failed log. Những lượt UI trung gian 62/4 và 69/3 không dùng làm kết quả cuối; nguyên nhân mode/context/setup và race đã được xử lý trước full 72 PASS. Còn một deprecation warning Starlette/httpx TestClient, không phải lỗi chạy ứng dụng.

Benchmark local trên Windows/Ryzen 5 7535HS, khoảng 16 GB RAM, Polars 2 threads, 3 repetitions/mốc 1k/10k/50k, không GPU/AI:

| Stage 50k | p50 / p95 quan sát (ms) | Peak RAM |
| --- | ---: | ---: |
| Parse | 57,01 / 57,74 | Foundation peak 166,42 MiB |
| Profile | 65,58 / 65,96 | Cùng phép đo foundation |
| Normalize + write | 1.153,76 / 1.260,90 | Cùng phép đo foundation |
| Exact match (50k tổng = 25k/nguồn) | 1.473,57 / 1.474,98 | Reconciliation peak 319,06 MiB |
| Independent verify | 1.192,72 / 1.214,17 | Cùng phép đo reconciliation |

Receipts đủ 1k/10k/50k ở `runtime/benchmarks.json`, `reconciliation-benchmark.json`; không suy SLA từ ba mẫu, không claim fuzzy/100k/full HTTP verified-run load đã đo. Isolated browser render latency chưa đo riêng, không dùng thời gian cả suite làm số render.

### F. Cleanup và các files thay đổi

Bỏ CSS `local-card`/`history-open` sau khi kiểm không còn JSX dùng; hợp nhất review reply vào composer và xác nhận xóa dùng shared Modal. Không xóa source files nghiệp vụ, lịch sử, fixtures, manual routes, raw/canonical, exports hoặc các dự án TEST đã tạo phục vụ bằng chứng.

Các nhóm files được sửa: backend Agent/contracts/query và business helper reuse; Gateway/Planner diagnostics; worker/migration/database; frontend AppShell/Assistant/result blocks/styles/navigation; tests Agent/query/AI/PG/E2E/fixtures; tools benchmark/recovery/persistence/rollback; README và tài liệu chuẩn. Danh sách đầy đủ bằng `git diff --stat main...codex/assistant-automation`. Không thêm dependency mới. Rules/AGENTS không sửa. Các checks ở mục E chạy sau thay đổi code/CSS; thay đổi cuối chỉ tài liệu/rollback tool có drill riêng.

**0 image deletions, 0 volume deletions, 0 global cache prune.** Gate main release chưa đạt nên giữ cả candidate/accepted/rollback images; không coi thay local image tag khi build là thu hồi dung lượng.

### G. GitHub

Một repository/root, remote đã fetch và xác minh: `https://github.com/MinhHoang1403/AI-Reconciliation-Studio.git`. Feature **`codex/assistant-automation`** được commit/push từng nhóm. Các commit chính: `a81ba3d` UI; `4ac8889` Planner null; `938bc7c` grouping/repair; `46eff65` rubric population; `08fb539` run chip; `1132f68` delete Modal; **`95d29560387b6b4e231a86b7b185c6de45928014`** real Agent recovery; **`8d55ba0`** legacy rollback guard đã drill.

`main` và `origin/main` vẫn **`eefdd4441d7f7ef52b08e7d35d3c68894de191dd`**. **Merge SHA: không có; main acceptance BLOCKED.** Không force-push, merge, xóa nhánh chưa tích hợp hoặc tạo worktree. Giữ tags `data-foundation-accepted-20261028` và `reconciliation-engine-accepted-20261029`, không tag đè.

Nhóm tài liệu bàn giao được commit/push sau kiểm diff, paths, secrets và nội dung; hash cuối và clean/local=remote được xác minh trong bàn giao, không tự ghi một commit hash chưa tồn tại vào chính file này. Runtime artifacts, keys, backups và logs đều ngoài Git. Secret scan bao gồm known local credentials trong reachable history và patterns, không chỉ staged diff.

### H. Docker, persistence và khôi phục

Một Compose project **`ai-reconciliation-studio`**, **4/4 healthy**, chỉ publish **127.0.0.1:18180**. Backend/worker/PostgreSQL không có host port. Runtime ứng dụng được build/test từ **`95d29560387b6b4e231a86b7b185c6de45928014`**; thay đổi sau đó chỉ docs/tools, không sửa bytes ứng dụng. Kiểm trực tiếp **50 tracked backend files ở cả backend/worker, toàn bộ dist assets qua HTTP, OCI source/revision, health**; diff từ tested SHA đến HEAD phải không có thay đổi backend/frontend app/Compose/dependencies. Receipt `runtime/assistant-candidate-runtime.json` ghi tested source và report HEAD riêng.

| Thành phần | Image ID đang chạy |
| --- | --- |
| Backend/worker | `sha256:04f64c457fb86717e2420338755d1e0be3b2c1c88307f5c1c60f4fc52cbbef3e` |
| Frontend | `sha256:12eb131f81e31083a1bb3f93d8943cb523d86a5b4449f1cdde9a6fe8e7c9ca48` |
| PostgreSQL, không rebuild | `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` |

Schema **`create_agent_workflows`**, migration additive; volumes nguyên tên **`ai-reconciliation-studio_postgres_data`**, **`ai-reconciliation-studio_artifacts`**. `tools/check-persistence.ps1`: **3/3** full metadata/file comparisons PASS qua restart, force-recreate, frontend-only recreate; **3/3** fail-closed 403 trước verify-local PASS. Snapshot chứa workflow/review, không chỉ raw files.

So baseline trước nhiệm vụ: **toàn bộ IDs và 488 published file SHA giữ nguyên**. Chỉ một WorkspaceRow metadata đổi theo cấp phép policy 10 -> 50; các baseline rows khác không đổi. Snapshot hiện tại: 57 projects, 161 datasets/versions, 136 canonical, 66 runs, 104 exports, 42 workflows; tăng fixtures TEST không xóa dữ liệu cũ. Receipt `runtime/agent-baseline-preservation.json`.

**Backup/restore PASS LOCAL** lúc 07:10 ngày 02/11: `backup_d553d9f091ca4c408749946090d8f81c`, 24 tables/764 published files, metadata SHA **`80fca8fb924739de048e1c21e987bdc6442ed61b1e75602332eec52db6b2ff08`**, backup 3,207 s/restore 2,696 s. Dùng UUID schema trong PostgreSQL hiện có, kiểm corruption/path traversal rồi chỉ dọn schema/copy của drill; public không overwrite. Giữ backup trên volume và host copy `runtime/agent-workflows-backup`, kiểm đủ metadata và 764 SHA. Off-host encrypted DR/production overwrite restore **NOT VERIFIED**, không thực hiện.

**Rollback PASS LOCAL** qua `tools/rollback.ps1 -ReleaseRevision 5f358c4`: accepted backend `sha256:7a00801051416c143e0d0199919bb9a43fa319a01fd01b1a8010b1d5d8781e29`, frontend `sha256:1049ba4457ebad8971d0be29cb523b7429714fb2c3dc1abcd28a9ef1a40ab215`; 4 healthy, cùng PG/schema/volumes, không downgrade. Kiểm lại full snapshot bằng verifier hiện tại chạy read-only trong container cũ, metrics và export SHA PASS. Legacy UI không thể resume Agent review mới; review được giữ để trở về candidate. Sau plain Compose up + verify-local, candidate 95d2956 đã trở lại: full snapshot, source/assets và read-only product/evidence/export replay PASS; Gemini vẫn 50/50. Receipt `runtime/agent-rollback-receipt.json`, log `agent-postrollback-products.log`.

Inventory cuối local: **57 host images/39,39 GB**, 31 containers, 36 volumes/9,024 GB, build cache 47,64 GB; đây là tổng host, không phải riêng ứng dụng. C còn **140.748.185.600 bytes** tại checkpoint `runtime/agent-final-inventory.json`. Agent pre-build inventory lưu containers/images/volumes nhưng không có phép đo free C tương đương, nên before/after physical storage reclaimed **NOT VERIFIED**; không suy dung lượng thu hồi khi không cleanup. Không thao tác tài nguyên dự án khác.

### I. Giới hạn và điểm dừng

- **PASS LOCAL:** backend/PG/static/browser, UI mô tả mới, native money/query/oracle, security cases đã định nghĩa, worker recovery, persistence, backup/restore/rollback và bảo toàn baseline.
- **PASS MOCK:** provider regression và 5 visual cases; không gọi các số này là Gemini live accuracy.
- **PASS LIVE có phạm vi:** các normalization/review/Planner/reuse/query/explain/export đại diện ở mục C–D; giữ lịch sử ca lỗi.
- **FAIL nghiệm thu:** broad NLP intent/source/slot quality trên gold chưa đáp ứng mục tiêu sản phẩm; không công bố full Agent MVP đạt.
- **BLOCKED:** replay gold trên prompt 6 và xác nhận chất lượng sau sửa vì Gemini còn 0; merge/main release và cleanup sau release chưa được làm. Cần allowance mới được chủ dự án cấp riêng, có kế hoạch đo, giữ toàn bộ history; không tự tăng/reset.
- **NOT VERIFIED:** full current-prompt gold, exact sketch comparison, physical mobile keyboard/screen reader/WCAG certification, production SLA/HA/DR, actual billed cloud cost, parser credits hiện tại và physical disk reclaimed.
- **DEFERRED:** Qwen live HTTP 403 theo chỉ định; Argon chỉ nghiên cứu, LlamaParse jobs mới OFF.

Có thể sử dụng feature hiện tại để đọc dữ liệu/kết quả đã lưu và luồng manual/typed commands trong điều kiện đủ quyền/rule. Ngôn ngữ tự nhiên cần model mới sẽ báo hết quota, không giả hiểu hoặc giả thành công. Giữ nguyên nhánh để hoàn thiện cổng AI khi có chỉ định tiếp; chưa đủ điều kiện hợp nhất main hoặc tuyên bố production-ready.

## T. AI Assistant Experience & NLP Quality Finalization

Ngày nghiệm thu: 02/11/2026 (Asia/Saigon). Phạm vi tiếp nối Agent-first, giữ nguyên ba giai đoạn và lịch sử A–S. Chỉ dẫn mới của chủ dự án cho phép dùng Gemini khi cần, thay blocker 50/50 của prompt ban đầu; không reset hoặc xóa request history. Rules §9.1 mô tả sidebar lịch sử khác yêu cầu mới: áp dụng chỉ dẫn Assistant-only được chủ dự án giao và bổ sung trong PROJECT_PLAN, không sửa Rules/AGENTS.

**Kết luận phạm vi:** đủ gate UX/NLP/technical để hợp nhất MVP có giới hạn được nêu ở H. Một ca gold hỏi lại không cần thiết được giữ FAIL; không tuyên bố NLP hoàn hảo hoặc production audit certification. Đã hợp nhất main và triển khai release sau khi kiểm backup/rollback/deployment; bằng chứng ở G.

### A. UX/UI — PASS LOCAL + MOCK CONTRACT + hành trình thực

- Sidebar chính đúng **AI Assistant / Lịch sử / Cài đặt**, giữ brand/workspace/header/font/avatar/light blue. Không menu sáu trang thay tên. Xóa nav state/icon/CSS của nhóm kết quả đã hết tham chiếu; giữ manual pages/deep links được regression bảo vệ.
- `AssistantDataDrawer`: danh sách/paging, raw/canonical/errors/quality/history revision, tìm kiếm, tải raw kiểm SHA, manual mapping fallback. Report/exceptions dùng lại ReconciliationStudio trong Modal đúng explicit run; evidence và export trong hội thoại. Không viết bộ tính tiền/KPI thứ hai.
- Một composer: Enter gửi, Shift+Enter xuống dòng, IME không gửi nhầm; 1–5 CSV/XLSX, upload bootstrap, draft/idempotency/unknown delivery/reload/project scope được giữ. Một history Modal có focus return; review reply dùng composer đang bind nonce/fingerprint.
- 23 trạng thái × 5 widths **390/768/1366/1440/1920 = 115 screenshots**; keyboard/focus/scroll/history/review/source switch/result overlay/draft được tương tác thật. Bao gồm PARTIAL/FAILED/Gemini unavailable/export/tên tệp dài. Ảnh chỉ là bằng chứng bố cục; không cộng số ảnh vào tests, không tuyên bố thiết bị thật hoặc screen reader/WCAG chứng nhận.

### B. NLP — PASS LIVE theo gate, còn một P2 an toàn

Prompt phát hành **agent-intent-15**; normalization 3, review 1, Planner 5 giữ nguyên. Bộ 80 gold/rubric không sửa; thêm riêng 24 variants. Variants độc lập về câu chữ nhưng cũng được dùng trong các vòng chẩn đoán 13–15, không phải blind holdout; không suy accuracy production từ tập regression được tối ưu này.

| Phép đo | Baseline prompt 5 tại S | Full gold prompt 15 | Variants độc lập prompt 15 |
| --- | ---: | ---: | ---: |
| Measured / requested | 80/80 | 80/80 | 24/24 |
| Intent | 68/80 (85%) | **79/80 (98,75%)** | **24/24 (100%)** |
| Source | 53/60 (88,33%) | **59/60 (98,33%)** | **16/16 (100%)** |
| Slots/semantics | 21/34 (61,76%) | **34/34 (100%)** | **10/10 (100%)** |
| Dispatch suy từ typed intent | 70/80 | **79/80** | **24/24** |
| Safe abstention | 20/20 | **20/20** | **8/8** |
| Strict negative label | 18/20 | **20/20** | **8/8** |

Clarification labels của gold/variants đều đúng ở các negative cần hỏi; D04 thêm một clarification không cần thiết nên intent và source vẫn FAIL cho chính ca này. Đây là over-abstention, không chọn nhầm nguồn để thực thi. Router benchmark không execute tools; completion và financial oracle được kiểm riêng tại C.

| Ca lỗi cũ | Nguyên nhân gốc | Sửa/kiểm tra | Kết quả hiện hành |
| --- | --- | --- | --- |
| D11, L03, L05 | Lẫn mục tiêu chuẩn bị và chạy ngay; READY làm model nhảy bước | Intent-specific schema, mô tả hành động hiện tại/tương lai, ví dụ độc lập; prepare dùng approved reuse | PASS LIVE |
| D12, L11, L12 | Model dựng lại plan, mất coverage/filter/snapshot/role/effective facts | Dereference current confirmed_run_id và đúng left/right READY; PlanningRequest.from_plan, reject drift; PG reuse + full scope regression | PASS LIVE + PG |
| D13, L13 | Tra cứu chuyển tiền bị hiểu thành lệnh chuyển tiền | Taxonomy read vs action; paid semantics và status enums trong catalogue; native paid oracle | PASS LIVE |
| D20, L20 | Thiếu state predicate hoặc chọn sai loại nguồn | EXCEPTION_FIELDS dùng chung với native query, schema nguồn/field/status rõ; predicates OPEN/OPEN+IN_REVIEW | PASS LIVE |
| D23, L21, L23 | Business key bị coi technical group ID hoặc unsupported | Exact key_value nguyên văn, facts/explanation branch không có query; provenance hai phía | PASS LIVE |
| L18 | Thiếu currency field/population cho tổng | Query slots bắt buộc, enum field IDs, native Decimal/currency guard | PASS LIVE |
| D27 | Tự lọc PAID khi hỏi toàn trạng thái | Group count không self-filter; guard giữ cả PAID/UNPAID; native count 3 gồm 2+1 | PASS LIVE + regression |
| L25, L26 | KPI bị dựng bằng query hoặc chuyển review khi không có câu hỏi | Summary branch đọc snapshot, query properties bị loại; typed review boundary giữ nguyên | PASS LIVE |
| N15, N17, N07 | Thiếu bằng chứng/nguồn bị dùng UNSUPPORTED hoặc default current run | CLARIFY khi thiếu nguồn/nghĩa, không suy COMPLETED=PAID; variants unknown/near-name không chạy | PASS LIVE |

Provider-facing RoutingBatch tách khỏi domain plan, query binds project/kind/ID ở server; source refs/nhãn phân biệt canonical/raw. Dynamic field enums và schema theo tool chặn sai cột/action combination; không lookup hay regex phân loại từng câu gold, không auto-repair JSON/financial semantics. HTTP 400 được tái hiện ở grammar kết hợp các ràng buộc array/enum trong các revisions chẩn đoán; bỏ bounds chỉ ở provider grammar, Pydantic/exact-count/field/cap gates giữ nguyên. Safe trace chỉ schema/counts, không error body/secret.

Sau sửa guard biểu đồ PAID+UNPAID, AST prompt/schema/catalogue/compiler vẫn giống source 5a7eebc. Revalidate **104 stored replies trên catalogue PostgreSQL thực, 0 HTTP/reservations**; không coi đây là inference mới. Benchmark cache nay chạy lại semantic validator hiện hành trước reuse. Bằng chứng: `assistant-experience-prompt-proof.log`, `assistant-experience-cached-revalidation.log`.

### C. Agent workflows và financial oracle — PASS LIVE có phạm vi

**10/10 hành trình đúng trạng thái: 9 COMPLETED + 1 WAITING_REVIEW đúng kỳ vọng**, mỗi hành trình đúng **1 model call**, không cần chuỗi model để sửa yêu cầu đơn giản:

- Chuẩn hóa reuse mapping/canonical hai miền (giao nhận và sổ cái): hai nguồn READY, 3 dòng/nguồn, 0 lỗi, raw/mã có số 0 đầu nguyên vẹn.
- Hai lệnh đối soát reuse đúng approved scope/run, 0 approval mới, không thêm run logic trùng; snapshot giữ eligible CU=3, full match 1/3=33,33%.
- Paid query trả đúng 000701/000702; 000703 UNPAID không lẫn vào PAID. COMPLETED ở nguồn B không là bằng chứng thanh toán.
- Giải thích 000702: hai source rows, tiền 12,75 và 10,00 VND, delta 2,75, đúng evidence/key/cell. Không suy đoán nguyên nhân nghiệp vụ chưa có chứng từ.
- Chart sum toàn bộ nguồn theo currency = **42,75 VND**, khác tổng variance comparable **2,75 VND**. Chart trạng thái giữ đủ **3 dòng: PAID=2, UNPAID=1**, không tự filter paid.
- XLSX xuất bằng worker thật; read-back export lịch sử **15.837 bytes, 8 sheets**, snapshot/SHA và zero-prefix/unmatched null được giữ.
- Thiếu paid semantics ở Chứng từ B trả một clarification review, không table/chart giả hoặc tự duyệt.

Bốn mapping approvals của lượt live trước là bốn quyết định schema riêng có key/currency/basis/grain/date cần xác nhận; không gom thành approval mù. Lượt này approved mappings/contracts chạy một lệnh và reuse an toàn. Mapping/rule mới, NL preview, nonce/fingerprint/stale/permission/resume vẫn có PG/MOCK regressions và bằng chứng live lịch sử tại S; không ghi các ca lịch sử thành request live mới.

### D. Tests, reliability và persistence

| Kiểm chứng | Kết quả hiện hành |
| --- | --- |
| Full Backend/PostgreSQL | **259 PASS, 0 FAIL/SKIP**, 72,00 giây; source dc8fcc5 |
| Ruff / mypy | PASS; **47 source files** |
| Frontend check/lint/build | PASS |
| Full Playwright | **81 PASS, 0 FAIL/SKIP/flaky**, 269,23 giây; gồm fixture report khớp đúng pathname kể cả query string |
| Financial/property/security/auth/isolation/CSV/XLSX/DSL/backup contracts | PASS trong full suites; không xóa oracle hoặc test cũ |
| Responsive/visual | PASS MOCK CONTRACT 23 × 5, keyboard/focus và các hành động nêu tại A |
| Worker fault injection | PASS source dc8fcc5: 75.000 dòng, SIGKILL/reclaim 2 attempts → 1 canonical → Agent COMPLETED, 0 cloud, 12,984 giây cả hành trình |
| Restart/recreate/frontend recreate | 3/3 full metadata+file comparisons và 3/3 local demo fail-closed PASS; guard/recovery cuối không đổi storage contract |
| Dữ liệu trước nhiệm vụ | Toàn bộ ID/metadata/artifact SHA cũ giữ nguyên; chỉ workspace policy đổi theo quyền mới |
| Backup/restore + host copy | PASS 24 bảng / 981 files; backup 3,820 s, restore 3,404 s; corruption/traversal bị chặn; host copy đủ SHA256 |
| Rollback/return candidate | PASS accepted 5f358c4: metrics/export đọc đúng; return dc8fcc5, full snapshot/50 source hashes/HTTP assets/4 healthy giữ nguyên |

Các lỗi trung gian được giữ trong lịch sử: mock GET conversation thiếu envelope; legacy navigation helper bị race project/Back và listener trước reload-ready; run cũ ngoài 50 đầu cần dùng pagination. Targeted tests rồi full suite chạy lại, không đổi financial oracle. Một lần BE fail do import json trong test bị thiếu đã sửa và full suite cuối PASS. Mock report fixture sau đó được sửa để match pathname cả khi URL có query string; thêm assertion chỉ một workflow và full suite cuối PASS. Fault injection từng từ chối khi còn job khác (đúng guard), không kill job đang chạy khác. Lượt E2E bị gián đoạn không có số liệu PASS được tính; proof local mất hiệu lực đã fail closed và được xác minh lại trước lượt E2E cuối.

Có một Starlette/httpx deprecation warning từ dependency, không là failure hoặc lý do nới validation. Physical keyboard/mobile/screen reader certification và 100k/concurrent production load NOT VERIFIED; performance 1k/10k/50k lịch sử tại S giữ đúng phạm vi.

Backup `backup_a0ea9c9ddaa54797a128b0a00122f804`, metadata SHA256 `84d07768cebeb969fe746f54093251614c65b13724ba0b6dfaef6b02317b4f75`; schema restore UUID cùng PostgreSQL đã được dọn sau drill, public không overwrite. Host copy ở `runtime/assistant-experience-backup`; cùng máy vật lý, chưa là disaster-recovery backup ngoài máy.

### E. Gemini và providers

Gemini `gemini-3.5-flash-lite`: **110/120 lifetime attempts, còn 10**; Agent **93/103**, Planner 10/10, legacy 7. Giữ nguyên 50 attempts trước nhiệm vụ. Chủ dự án cho phép dùng thêm; ceiling global/workspace lần lượt 50→63→100→120, Agent 33→46→83→103, có CLOUD_BUDGET_AUTHORIZED audits; không xóa reservations/keys/history, không gửi bằng key dự án khác. Default cài mới OFF/0 và per-workflow caps giữ nguyên.

Lượt này **60 HTTP attempts**, 55 VALIDATED, 2 HTTP 400, 2 invalid fields và 1 invalid intent được giữ. Trace VALIDATED không đồng nghĩa gold accuracy: canary đầu từng thiếu predicate dù đúng JSON. Revisions 7/8/9/10/11/12/13/14/15 lần lượt **1/2/2/1/3/3/12/12/24 attempts**; final prompt 15 gồm 2 canaries, 8 gold batch, 4 variant batch, 10 native workflows. Mỗi batch ≤10, một HTTP attempt, stop-on-block; không resend timeout/unknown delivery. 58 token receipts, **448.395 tokens**, latency HTTP gồm batch và câu đơn **p50 2.880 ms / p95 5.062 ms**; không suy latency từng câu từ batch. **Actual billed cost NOT VERIFIED**.

Qwen `knowledge` DEFERRED vì HTTP 403 theo chỉ định, **0 calls mới**; Argon không dùng. LlamaParse tạo job mới OFF, **0 calls mới**; PDF/DOCX 2 files/6 credits là bằng chứng lịch sử S, không gọi live lại hoặc báo thành lượt kiểm mới.

### F. Cleanup và bảo toàn

Bỏ sidebar group/count state, icon/import và CSS nav đã hết tham chiếu. Giữ DataOverview, ReconciliationStudio, manual mapping/plan/evidence/export và deep links vì vẫn là fallback có kiểm thử; không coi chúng là code chết. Không xóa migrations, golden fixtures, raw/canonical/runs, backups hoặc hội thoại. Không dependency/framework/agent/service/worktree mới. Cleanup image chỉ thực hiện sau main release/rollback gate, ghi IDs và lý do tại G; không global prune, không xóa volumes.

### G. Git / Docker / release

Source ứng dụng đã full regression: **dc8fcc5fc06f44372fae55aaa3d824cf95fd44a2**; prompt live đầy đủ ở 5a7eebc, chỉ thêm guard/cached validation không đổi prompt và revalidate đầy đủ sau đó. Backend/worker 50 tracked file hashes, HTTP assets và OCI labels PASS. Một Compose project `ai-reconciliation-studio`, 4 healthy, schema `create_agent_workflows`, giữ volumes `ai-reconciliation-studio_postgres_data` và `ai-reconciliation-studio_artifacts`; host chỉ loopback 127.0.0.1:18180.

Candidate dc8fcc5: backend/worker `sha256:df03f902ffa0bc4ad75ddfd9858c79181bacc7a283585d26b0279ee5e4a70600`, frontend `sha256:2e4892705cc595e9e531d598603fbe0a57e3c390305aca9c60eaf2fef278f981`; PostgreSQL `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7` không đổi. Protected accepted 5f358c4 và rollback pairs được giữ. Không thay hai acceptance tags cũ. Các commits chức năng đã push origin/codex/assistant-automation: 05625b0, b0d824b, 5a7eebc, dc8fcc5; fixture regression 8fedd1b. Main trước hợp nhất eefdd444. **Đã fast-forward và push origin/main tới f1ad9f18fead39c449886c4efcb28807412aec19**, cùng source đã chốt báo cáo trên feature branch; không force-push hoặc sửa acceptance tags.

**Release main PASS:** build/deploy từ `f1ad9f18fead39c449886c4efcb28807412aec19`; backend/worker `sha256:f70deb47f560e1a41d33f35051ea16afed697c78586ecebc8bd1d4e1415cba49`, frontend `sha256:73c6716d779626de3ee852ab3e6eaced98957ba5fb3a6e038b88d05975ba3028`. OCI/50 backend source hashes/HTTP assets/4 healthy/loopback/schema/PG image và hai volumes đều kiểm lại PASS. Application diff từ dc8fcc5 đến release rỗng; các commits sau chỉ fixture/tài liệu. Docker tags `accepted-main-f1ad9f1` giữ bản phát hành; `rollback-dc8fcc5`, accepted 5f358c4 và các rollback/candidate đã bảo vệ được giữ.

Sau main deployment: full persistence snapshot PASS; đọc lại cả **10 workflow** đúng toàn bộ DTO/state đã lưu, raw/canonical/snapshot/evidence hai miền và XLSX SHA PASS; **0 request cloud mới**, ledger vẫn 110/120. Tất cả IDs/hashes trước nhiệm vụ vẫn giữ, chỉ workspace policy thay đổi có ủy quyền. Không có image dangling mang label repository trong lần audit cuối; **0 image/volume tự xóa**, không global prune hoặc bịa dung lượng đã giải phóng. C: còn khoảng 131,1 GiB tại kiểm tra cuối.

Cập nhật release này chỉ đổi tài liệu so với SHA đã build; runtime giữ labels f1ad9f1 và source/assets được đối chiếu với HEAD sau commit. Git final status/remote heads nằm trong receipt local `runtime/assistant-experience-git-final.json`.

### H. Giới hạn và kết luận

- **P2 còn lại:** D04 hỏi lại về Xác nhận B khi dùng tên A/B rút gọn; explicit filenames đã chạy thực. Không bỏ ca này hoặc đổi oracle. Không có P0/P1 còn được tái hiện trong phạm vi kiểm tra cuối; không đảm bảo mọi câu hỏi ngoài gold/variants đúng.
- Manual fallback giữ vì cần xử lý nâng cao/AI unavailable; dữ liệu chưa được duyệt vẫn cần review, không auto-approve để giảm click.
- LlamaParse mới OFF, Qwen live hoãn; cost tiền thực, thiết bị vật lý/WCAG certification và tải production chưa được xác minh như nêu trên.
- Kết quả này đáp ứng ngưỡng MVP được giao cho Assistant experience; không tự bắt đầu tính năng/giai đoạn mới. Dừng sau bàn giao và chờ nhiệm vụ riêng.

Receipts local ngoài Git: `runtime/assistant-experience-backend-final.log`, `assistant-experience-e2e-resumed.json`, `assistant-experience-gold-final.json`, `assistant-experience-variants-final.json`, `assistant-experience-native-workflows.json`, `assistant-experience-payment-chart.json`, `assistant-experience-products.json`, `assistant-experience-usage.json`, `assistant-experience-original-data-proof.json`, cùng logs recovery/persistence/backup/rollback/release tương ứng. Không commit runtime artifacts hoặc secrets.

## U. Hoàn thiện Assistant, Settings và kiểm chứng local — 02/11/2026

### Phạm vi và baseline

Nhiệm vụ master prompt ngày 02/11/2026: cải thiện UI, audit luồng nghiệp vụ, sửa lỗi thực tế, kiểm chứng và phát hành local trong cùng repository/Compose. Baseline main và origin/main cùng `952566663e03f37d244d1f97aa000b4571861427`, working tree sạch; runtime accepted-main `f1ad9f1`. Backend baseline chạy mới **259 PASS / 57,75 giây**; 81 E2E là mốc bàn giao/cataloque trước thay đổi, không tính thành một lượt chạy mới. Một Compose, bốn services healthy, hai named volumes; không thay .env/provider/model/quota/migrations hoặc dữ liệu cũ.

### UI và thiết kế

- Một composer, `rows=1`, tự giãn tối đa180px; nút gửi icon có accessible name, attach/remove/Enter/Shift+Enter/IME/draft/review/idempotency giữ nguyên. Gộp các khai báo composer chồng nhau, bỏ focus-within xanh và hai lớp khung. Đo năm widths 390/768/1366/1440/1920: trống64–70px, send40×40px, outline composer khi click=none, focus bàn phím rõ; chữ gợi ý/nền đo7,24:1. Đây là samples, không phải chứng nhận WCAG toàn ứng dụng/thiết bị thật.
- Ghost suggestions, empty state nhẹ, transcript AI không bọc mọi câu trong card; panel giữ cho dữ liệu/review/evidence. AppShell, logo, workspace/account/header và sidebar Assistant/Lịch sử/Cài đặt được bảo toàn. Nhãn TEST trong project selector đổi thành “Thử nghiệm”, enum API không đổi.
- `WorkspaceSettings.tsx` tách trình bày chỉ đọc khỏi App: tài khoản/quyền, quyền riêng tư và giới hạn; owner mới mở thông tin nâng cao. Không nút/switch giả, không endpoint/secret. Cấu hình/quyền/task allowance được phân biệt với kết nối AI: `NOT VERIFIED` không trở thành “sẵn sàng”. Cài đặt vẫn nêu khả năng gửi bounded context/mẫu ra dịch vụ bên ngoài khi policy cho phép.
- Đọc nguồn công khai [ChatGPT](https://chatgpt.com/), [Julius](https://julius.ai/guides/academic), [Copilot](https://learn.microsoft.com/copilot/faq), [Rillet Aura](https://www.rillet.com/product/aura-ai); dùng nguyên tắc [Fluent layout](https://fluent2.microsoft.design/layout), [tokens](https://fluent2.microsoft.design/design-tokens), [WCAG2.2](https://www.w3.org/WAI/WCAG22/quickref/), [Playwright snapshots](https://playwright.dev/docs/test-snapshots) và [trace viewer](https://playwright.dev/docs/trace-viewer). Chỉ đọc public pages/docs, không sao chép code/branding hoặc tuyên bố đã dùng phiên tài khoản riêng của các sản phẩm.
- Baseline screenshots của Assistant/Settings ở cả năm widths vì attachment không chứa hai ảnh gốc. Visual regressions23states×5widths, Settings basic/advanced, keyboard/multiline/file chips và long-category chart có ảnh thực; xem các states chính trước/sau bằng mắt. Giữ phân biệt layout MOCK với luồng Backend thật.

### Lỗi đã sửa và bằng chứng

| Hiện tượng | Nguyên nhân và sửa | Kiểm chứng |
| --- | --- | --- |
| Settings ghi10tệp, chat chỉ nhận5; composer hardcode20MB/5tệp | `config.agent_max_upload_files`/allowlist dùng chung giữa kiểm upload và GET/settings; FE nhận giới hạn từ API | Một PG regression đổi max_files=2, upload3bị422/TOO_MANY_FILES, nâng cấu hình10thìchat5; không job/provider |
| Mất response upload, refresh/đính kèm lại tạo bootstrap khác | Random upload key chỉ nằm trong ref. Giữ key chưa có receipt theo chữ ký SHA256 của ordered files và actor/project trong sessionStorage; hash tuần tự, không lưu bytes | Browser FAIL trên bản trước sửa vì hai key khác nhau; PASS sau sửa: cùng key/project/dataset, một dataset và0cloud |
| Tên nhóm dài làm ECharts chỉ hiện một nhãn, cột bị ép hẹp trên390px | Axis tự bỏ nhãn, grid không đủ chỗ. Thanh ngang/nhãn xuống dòng cho nhóm dài/nhiều; bounded scroll bàn phím, mô tả tiếng Việt và Decimal string chính xác | MOCK DTO6nhóm: FAIL trước/PASS sau; đủ6nhãnSVG, End cuộn, exact12.75VND. Theo [ECharts ARIA](https://echarts.apache.org/handbook/en/best-practices/aria/) |
| Chọn canonical revision đôi khi bị reset, nút xem bị disabled | Effect reset sau tableId render đua với thao tác chọn. Reset đồng thời khi đổi nguồn/bảng/nhận metadata; chọn cùng nguồn giữ revision; abort request cũ | Bắt được trong full suite cuối; tăng assertion giữ revision và chọn lại nguồn, replay5/5PASS. Không nới timeout/validator hoặc sửa dữ liệu |

### Nghiệp vụ, dữ liệu và providers

Upload/parsing/mapping/normalization/exact+composite+group reconciliation/independent verifier/query/evidence/export/auth/isolation được kiểm bằng full Backend/PG và browser journeys thật. Provider transports/NLP failure/permission UI dùng MOCK được ghi riêng; không coi đó là inference mới. Oracle giữ mã000702, hai nguồn12.75/10.00VND, delta2.75VND, full-match1/3=33.33%; CSV/XLSX đối chiếu snapshot, zero-prefix/null/formula injection được giữ.

Prompt15/Gateway/engine/verifier không đổi. **104 phản hồi đã lưu** được revalidate qua validator hiện hành trên catalogue PostgreSQL:80gold+24variants PASS CACHED,0HTTP/reservations; đây không là phép đo inference mới hoặc sửa ca D04 thành PASS. Gemini vẫn110/120, Agent93/103, Planner10/10; default source cloudOFF/0. Qwen không probe, LlamaParse không tạo job, Argon không tích hợp. Billed cost, kết nối model trực tiếp mới, thiết bị thật/screen reader và tải/concurrency production NOT VERIFIED.

Worker fault injection mới:75.000dòng, SIGKILL child normalization,2attempts→1canonical, AgentCOMPLETED,0cloud,13,640giây toàn hành trình; không suy thành steady-state throughput. Đọc lại9workflow đã lưu, hai snapshot/raw/export của hai miền khớp. Full inventory trước nhiệm vụ: mọi ID/metadata/hash artifact cũ được giữ, chỉ thêm synthetic test records; không xóa dữ liệu.

Backup/restore trước deploy: `backup_89d8d39de73040bdac2845ee0225271c`,24bảng/981files; metadata SHA256 `2434d7f889f75a805f367b4a96e3f4e4d817bf4720e57d88c1510227f86e9674`, backup3,849s/restore4,375s, corruption/traversal bị chặn. Copy ra host và kiểm lại toàn bộ981file/SHA; cùng máy vật lý, chưa là backup disaster recovery ngoài máy. Restore schema UUID chỉ dùng trong cùng PostgreSQL và được tool dọn, public không overwrite.

### Source, tài liệu và giới hạn

Thay đổi giới hạn ở Assistant/App/Settings/DataDrawer/ProjectSelector/AgentResultBlocks/CSS/types, ba module settings/upload nhỏ và regressions. Không thêm dependency/framework/service/worktree, không đổi financial contracts hoặc migration. Manual fallback, deep links, advanced workflows và golden fixtures vẫn giữ. Xóa CSS chồng/lỗi thời tại vị trí cũ, không nối override vô hạn. Rules§9.1 và tài liệu đầu trang được đồng bộ Assistant-only theo quyền mới; các mốc S/T và ba giai đoạn giữ làm lịch sử. Không xóa AGENTS hoặc tài liệu bằng chứng.

P2 D04 over-abstention với tên nguồn A/B rút gọn giữ nguyên. Không có bằng chứng accuracy tuyệt đối ngoài gold. Chỉ hướng tới READY_FOR_LOCAL_USE trong phạm vi MVP khi gates vận hành/release bên dưới đạt, không PRODUCTION_READY.

Kết quả source chốt và release được ghi tiếp sau khi chạy các cổng cuối. Receipts/screenshot/backup nằm ở `runtime/ui-refinement/`, ngoài Git.

### Quality gates của source chốt

Source ứng dụng chốt `83d9b35`; các thay đổi tiếp theo trong đợt này chỉ là tài liệu. **260 Backend/PostgreSQL PASS, 0 FAIL/SKIP, 55,86 giây**; baseline259 tăng đúng một PG regression. **90 Playwright PASS, 0 FAIL/SKIP/flaky, 295,30 giây** trên source chốt; baseline81 tăng đúng chín cases:5widths composer/Settings,1ma trận Settings,1IME,1upload recovery,1long-chart. Các assertion được tăng trong ca drawer sẵn có, không tăng số case và không cộng5replays vào90.

Ruff toàn backend/tests/tools, mypy42source files, TypeScript/check, ESLint và production build PASS. T01–T40, financial/property/security/auth/CSRF/isolation/export-injection/query/lease/backup contracts nằm trong full suites; không xóa oracle, hạ validator hoặc thêm dependency. Một Starlette/httpx deprecation warning giữ nguyên, không phải failure. Repository content/known-secret/history/Markdown paths và git diff whitespace checks PASS. Không có workflow CI được định nghĩa trong repository; không ghi GitHub CI PASS từ local tests.

Các lượt trung gian không được cộng PASS: test mới ban đầu kỳ vọng400thay422theo error contract; một lượt chạy bị ngắt khi sửa thông báo định dạng/placeholder; một fixture Settings thiếu API envelope; một test khởi động trước khi proof local được cấp; một full run bắt được drawer reset race89PASS/1FAIL. Nguyên nhân đã xử lý ở lớp tương ứng, không tăng timeout/retry hoặc bỏ case. Full suite cuối ở trên là lượt90/90sau sửa drawer và selector label.

Restart và full recreate đều PASS full metadata/artifact snapshot, đồng thời GET/session fail-closed403trước verify-local (2/2). Rollback thực tới accepted-main-f1ad9f1, đọc lại9workflow/hai snapshot/raw/export và full persistence PASS, rồi quay lại candidate khỏe. Không downgrade, đổi policy/quota, xóa volume hoặc tạo Compose thứ hai. Snapshot trước các phép vận hành có916dataset artifacts+94run artifacts+151exports; toàn bộ giữ nguyên qua các thao tác này.

### Phát hành main và cleanup — READY_FOR_LOCAL_USE

Đã fast-forward và push `origin/main` từ `952566663e03f37d244d1f97aa000b4571861427` tới **`d392c4a9216fe021ce301e2816a712ded025c951`** sau gates. Source ứng dụng giống hệt `83d9b35` đã chạy full suites; diff backend/frontend rỗng. Build/deploy main có OCI revision đúng SHA trên cả Backend/worker/frontend; kiểm48tracked Backend file hashes ở hai tiến trình và assets HTTP so với dist PASS. Không có migration mới, schema vẫn `create_agent_workflows`, PostgreSQL image không đổi.

| Image main | Digest |
| --- | --- |
| Backend + worker | `sha256:2260ad5ee96d75a1cdb8db8fe76a56ba5f56dea041a12e87b302c156e12fe902` |
| Frontend | `sha256:484acae401f9c6ecfcfde3c983fee8e7ac2dc6a50f99df6ae3eb2d03810bd935` |

Sau deploy main: full persistence trước/sau image recreate PASS; đọc9workflow/hai snapshot/raw/export PASS; **19/19 browser smoke PASS, 55,72giây, 0 FAIL/SKIP/flaky**, gồm product journey thực và các ca Assistant/Settings/upload recovery/chart/drawer. Không cộng19replays vào90cases. Bốn services healthy, chỉ `127.0.0.1:18180` được publish; Backend/worker/PostgreSQL không host port. Web: [mở local](http://127.0.0.1:18180). Dữ liệu trước nhiệm vụ được so lại lần cuối theo mọi ID/metadata/hash: PASS; chỉ thêm fixtures tổng hợp, không xóa hoặc sửa bản gốc. Gemini vẫn110/120,0calls mới.

Cleanup đã kiểm labels/source/references trên cả container đang chạy và đã dừng trước mỗi lần xóa, không force: **14→6 application images, xóa8image** gồm candidate446d031/9802545 và rollbackdc8fcc5/e025094 đã có rollbackf1ad9f1 thay thế được thử thực. Giữ các pairs `accepted-main-d392c4a`, `accepted-main-f1ad9f1` (đường rollback đã kiểm) và mốc accepted `5f358c4`; images lưu trữ không là ứng dụng chạy song song. Container ứng dụng4→4; volumes2→2: `ai-reconciliation-studio_postgres_data` và `ai-reconciliation-studio_artifacts`. Không đụng project khác, Git acceptance tags, volumes/backups hoặc global build cache. Docker accounting Images toàn host **39,4→38,91GB**, build cache vẫn47,71GB; không xác nhận số byte vật lý thu hồi vì cache/layers chung. C: còn khoảng139,2GB tại lúc đo; không coi biến động free space là bằng chứng cleanup riêng.

Backup sau release: `backup_3ecc88c9105e45eb8cf2383fdabe6338`,24bảng, metadata SHA256 `be9633bf5689bd97a09e377e140b44d482fa89a55db8eb701c80c63feb091956`; backup3,829s/restore4,880s PASS, giữ nguyên public. Đã copy ra host; manifest/metadata/toàn bộ1176files được kiểm SHA. Cả hai backups của nhiệm vụ được giữ, không thay backup ngoài máy. Xóa script chỉnh CSS tạm của lượt làm việc; giữ receipts/screenshot và công cụ đọc kiểm chứng local ngoài Git. Không phát sinh dependency/service khác.

Kết luận **READY_FOR_LOCAL_USE** trong MVP đã phê duyệt; không P0/P1 còn tái hiện trong phạm vi suites/journeys đã chạy, còn P2 D04 và các NOT VERIFIED nêu trên. Commit ghi báo cáo sau deploy chỉ thay tài liệu; runtime giữ labels `d392c4a`, application diff được kiểm rỗng. Git status/remote SHA cuối ở receipt `runtime/ui-refinement/git-release-proof.json`; không gọi một doc-only commit là binary release khác.

## V. Nghiệm thu demo và khôi phục môi trường — 02/11/2026

Baseline main `c3ca758`, runtime release `d392c4a`, working tree sạch trước nhiệm vụ. Branch `codex/demo-acceptance`, cùng repository và Compose. Chủ dự án yêu cầu tiếp tục kiểm thử, tăng allowance và giữ các công cụ đã triển khai bật. Global/demo workspace ceiling120→200, Agent103→163, Planner10→30, Assistant→20; không reset audit. Trước thay đổi: Gemini113, Agent96, Planner10, Assistant1; ba lượt Gemini phát sinh sau bàn giao U là lượt riêng của người dùng, không là phép thử của Codex. Receipt có CLOUD_BUDGET_AUTHORIZED; flags Agent/Assistant/parser bật, parser còn gate file/allowance riêng. Không đổi key/model hoặc default source OFF/0.

Thay đổi source: tạo dự án ngay trong picker của Assistant; History có loading/error/retry, phạm vi dự án và empty/search rõ ràng; Settings thu gọn và hiển thị task allowance bên cạnh tổng allowance. API settings bổ sung DTO chỉ đọc, không gọi provider. Giữ parser/mapping/normalization/engine/verifier/Decimal/approval/auth contracts. Trace Playwright được giữ khi fail. Generator seed2026110217 tạo11scenarios/24files/2131transaction rows, oracle Decimal độc lập; runtime data không vào Git. E2E mới đang được chạy, chưa tính PASS.

Kiểm chứng source trước browser UAT: **261 Backend/PostgreSQL PASS, 0 FAIL/SKIP, 71,13s**; Ruff/mypy47source files, frontend TypeScript/ESLint/build và repository/secrets/Markdown checks PASS. Test Settings mặc định được cô lập khỏi process environment để không phụ thuộc việc owner bật cloud; không tắt cloud trong deployment. Sửa một dòng indentation sẵn có trong reporting test để full Ruff format gate đạt. Không thêm dependency/service/worktree.

Backup trước policy/source: `backup_991a1fa5762b466dbf5be3867ab36168`,24tables, metadata SHA256 `fee091f8508766928c0133dcc300e12306be37d74ee1a21f83fbd37e3a7155e2`, backup6,571s/restore5,592s PASS; public không overwrite. Inventory toàn bộ dữ liệu cũ được giữ tại runtime/demo-acceptance; xác minh cuối phải phân biệt đúng thay đổi workspace policy đã được cho phép. Trạng thái nghiệm thu/release chưa kết luận cho đến khi các gates còn lại có bằng chứng.

Môi trường host đã được khôi phục sau khi chủ dự án báo xóa AppData: Python3.12.14 cho dự án và các lệnh python/python3/python3.12, Python3.11.9 tương thích alias cũ; sửa registry/alias trỏ interpreter đã mất. Sửa ngay `.venv` hiện có bằng `uv venv --allow-existing`, giữ packages, `uv sync --locked --offline` kiểm51gói/52lock entries. Không tạo venv/Compose thứ hai hoặc đổi lockfile. Node24.19.0/npm11.17.0, dependencies frontend và ChromiumPlaywright đã kiểm; Docker29.7.2/Git2.55.0 hoạt động,4services healthy. Không có inventory trước xóa của các công cụ cá nhân khác; không tuyên bố phục hồi mọi package ngoài dự án.

UAT phát hiện manual fallback từ Chat dùng project list cũ sau upload. App nay refresh danh sách và đọc đúng Dataset theo ID qua openPreparation, kể cả nguồn ngoài trang hiện tại. Tám nhóm dữ liệu hợp lệ và mixed-currency safe block đã chạy; oracle ban đầu phân loại NULL optional thành INVALID được sửa theo DATA_CONTRACTS hiện hữu: giữ linkage, NOT_COMPARABLE và excluded-own-money, không đổi engine. Formula warning phải có xác nhận UI riêng; không bỏ gate. Case1k so1000groups/Decimal và CSV/XLSX/reload PASS,72,085s cả UI gồm export; chưa là steady-state benchmark. Một lượt bị gián đoạn do recreate trong lúc đọc được giữ là FAIL, không gộp thành PASS; lượt chạy ổn định sau đó đạt.

Live chuẩn hóa bộ1k mới dùng3attempts, hai mapping được review từng trường qua UI;0tự phê duyệt. Ba thử đối soát mới trên prompt15 bị AI_INVALID_SOURCE, canonical_count2 nhưng cả hai lựa chọn không thuộc catalogue; các failure/receipts giữ nguyên. Prompt16 bổ sung chỉ dẫn phân biệt canonical source_id với dataset_id/ref/raw, schema provider giới hạn hai source slots bằng danh mục canonical hiện có; semantic checks vẫn bắt buộc ở server. Safe diagnostics chỉ booleans/counts, không raw output/secret. Regression transport/mock40PASS; full backend và replay live gold/variants đang chạy, chưa kết luận release.

Lượt prompt16 full gold dừng đúng guard tại batch ledger thứ3:60measured/80requested,10blocked,10chưa chạy. D04 over-abstention còn; L11 không giữ confirmed scope; L23 dùng business ID để lọc technical group_id và bị từ chối. Không báo60measured thành80PASS. Prompt17 làm rõ các ba phân biệt này bằng chỉ dẫn tổng quát, không thay gold/oracle hoặc validator. Theo quyền chủ dự án cho kiểm thử rộng, kế hoạch Codex được mở từ30lên40attempts mới để gồm replay hiện hành; global/workspace200 không đổi, giữ tất cả failure/ledger và phân biệt lượt người dùng.

Bộ1k cũng tái hiện lỗi UI review Planner khi planning_request có các optional facts explicit null: object spread ghi đè role/filters defaults bằng null, khiến POST quyết định bị422. Sửa bỏ qua null/undefined khi ghép form, giữ false/zero/filters được cung cấp; không tự xác nhận coverage hoặc đổi server gate. Thêm browser regression sparse-planning-request; kiểm trước/sau và live approval tiếp tục trên cùng proposal, không gọi model lại.

Sau sửa form, cùng proposal live đã được duyệt qua UI và tạo verified run1k: full-match966/1000=96,60%,19lệch,15thiếu đối ứng, absolute variance7,03VND. Không gọi model lại để sửa POST bị422. Regression MOCK form đã tái hiện role=null trên binary trước sửa và PASS sau sửa. Những lượt fixture chưa đủ reply_questions/updated_at được sửa ở test, không tính làm bằng chứng lỗi ứng dụng.

Đánh giá prompt17: full batch gold dừng tại một câu sai field; các câu cùng batch không được tự chấm PASS. Bổ sung tùy chọn benchmark `--evaluate-completed-cases`: chỉ đọc typed reply đã xác minh HTTP200/STOP trong project TEST, chạy lại cùng production validator từng câu, giữ job/batch gốc BLOCKED, giữ câu sai trong mọi mẫu số và đánh trượt source/slot tương ứng. Không thực thi/rewrite/retry action, không dùng LLM tự chấm, mặc định harness vẫn stop-on-block. Regression bảo đảm candidate bị từ chối không bị loại khỏi mẫu số. Replay các responses prompt17 đã nhận là CACHED validation; chỉ hai batch chưa từng gửi được gọi thêm. Kết quả80observed: intent78/80, source57/60, slots31/34, dispatch77/80, negatives20/20;1casevalidationfailure. Đây là benchmark routing theo câu, không phải80workflow hoàn thành hoặc8/8batch đều hợp lệ. Variants24/24intent,16/16source,10/10slots,8/8negatives,0validationfailures;4HTTPbatches mới. D04 được đo lại trong full gold, không xóa ca cũ.

Qwen đã mở truy cập trở lại tại lúc kiểm tra mới: cả host và backend Docker GET/models200, modelknowledge có trong danh sách và synthetic mapping inference qua JSON/semantic gates PASS LIVE. Hai phép thử không đổi MAPPING_AI_PROVIDER=GEMINI hoặc gửi business files; mốc403 lịch sử không còn mô tả kết nối ở lần kiểm tra này. Không suy ra độ chính xác mọi dữ liệu từ hai mẫu.

Live paid và chart trên fixture1k PASS:686PAID,200UNPAID,114COMPLETED, chartpopulation1000. Một query thiếu đối ứng bị QUERY_FIELD_INVALID vì model yêu cầu money fields nhưng không chọn metric; không có số liệu giả. Sau failure rồi reload, UI còn lộ lỗi context: latestWorkflowId xét cả user message nhưng chỉ assistant message render panel, khiến run chip rơi về project context. Sửa chọn latest rendered assistant workflow; regression tái hiện trước sửa, bảo vệ reload và giữ đúng run. Các ca ngôn ngữ tiếp theo chạy lại lần đầu sau khi khôi phục context, không resend request đã mất receipt.

Lượt full browser đầu source d03d738:107/109PASS,2FAIL,0SKIP/flaky,739,066s. Hai lỗi không bị bỏ qua: regressionHistory còn tìm alert ở trang thay vì modal mới (đổi thao tác đúng Lịch sử/Tải lại); legacyAssistant khi cloud bật đã gửi một request cho câu yêu cầu SQL/resetbudget/.env. Output vẫn thiếu bằng chứng, không có tool/SQL/secret/budget mutation; nhưng yêu cầu này cần bị từ chối trước provider. Thêm deterministic deny guard cho explicit code/secret/bypass requests và3unitcases trong cloudON. RegressionT39 giữ assertion không gọi provider và thêm ledger before/after. Không tắt Assistant hoặc hạ gate.34Assistant unitPASS; full suites chạy lại sau sửa.

Lượt legacy trên là job do `assistant.spec.ts` gửi, đã đối chiếu literal question với source mà không in nội dung/secret. Nó thuộc Codex regression, không được ghi thành lượt người dùng. Tổng mới41attempts=40lượt đã gắn native/benchmark refs+1legacyregression. Kế hoạch vận hành được nâng tối đa45theo quyền kiểm thử rộng; không tăng global200hoặc reset ledger. Baseline113 bao gồm3lượt riêng sau bàn giao trước; hiện154/200, Agent135/163, Planner11/30, legacy2/20.41traces,40tokenreceipts314674tokens, HTTPp50/p95=2813/5557ms;1legacyreceipt không có token total trong trường tiêu chuẩn, không suy billed cost. Không có reservation mới chưa gắn được với hoạt động Codex tại audit này.

Hai câu NL chung về thiếu đối ứng/lệch tiền bị QUERY_FIELD_INVALID; hai câu mới nêu rõ chỉ tiêu reported_transaction_amount đã duyệt PASS LIVE, đúng15và19. Follow-up chung hỏi lại (WAITING_REVIEW), không tự coi là chọn nguồnAđúng. Yêu cầu sửa raw/chạy mã/tự duyệt trả UNSUPPORTED+BLOCKED,0toolsteps: đây là safe refusal, không là lỗi thực thi. Không xóa những lần bị chặn. D04 trên hai nguồn mới đã hoàn thành chuẩn hóa reuse, không approval mới. UI readback: chart1000hiện đủ3nhóm, paid686phân trang, dòng gốcPAID, evidence4479.17−4478.80=0.37VND và reloadđúngrun PASSLOCAL,0modelsubmissions. PDF/DOCX đã lưu được đọc và đối chiếu rawSHA/oracle PASS CACHED,0providerHTTP; allowance parser vẫn2/2đã dùng.

Đã kiểm mọi ID/metadata/hash trước nhiệm vụ:106projects/268datasets/196canonicals/95runs/153exports cùng928artifacts và toàn bộ approvals/conversations/jobs cũ giữ nguyên. Workspace policy là ngoại lệ duy nhất có quyền; thay policy trong memory về bản trước tạo lại đúng metadatahash ban đầu, không ghi đè DB. Kết quả này không bỏ qua hash hoặc so chỉ counts.

Full browser lượt tiếp theo tiếp tục giữ mọi test, phát hiện bug UI khi chọn lại cùng sheet: handler xóa profile/mappings nhưng tableId không đổi nên effect không chạy lại; khi request cũ chưa xong đôi lúc tự hồi, gây failure không ổn định ở manual mapping. Sửa return sớm khi chọn đúng table hiện tại, giữ draft/profile và không thêm request/AI. Tăng assertion trong UAT: sau nhập loại dữ liệu, chọn lại sheet hiện tại phải giữ loại dữ liệu và form. Không tăng timeout/retry để che lỗi; các failure/traces của lượt trước giữ riêng. TypeScript/ESLint PASS, cần replay full suite sau deploy sửa này.

### Kết quả quality gates và khôi phục môi trường hiện hành

Source ứng dụng `1ab3fa4dd3858a8e1bbd2c406684984d72fc0643`: **265 Backend/PostgreSQL PASS,0FAIL/SKIP,78,55s**; **109 Playwright PASS,0FAIL/SKIP/flaky,581,489s**, full suite sau sửa sheet-reselection.265=baseline260+taskallowance1+benchmarkdenominator1+guard3;109=baseline90+12UAT+6History/context+1sparsePlanner. Không cộng các replay/targeted cases vào tổng. Lượt trung gian104/109,5FAIL do cùng race chọn sheet được giữ logs/traces; không gọi chúng là kết quả cuối. Full backend source sau265 không đổi; mypy47files/Ruffformat79files/TypeScript/ESLint/build/repositorypaths/secrets PASS. Một dependency deprecationwarning giữ nguyên.

UAT có11scenarios và một ca reject hai tệp lỗi/quágiới hạn; upload quaChat và toàn bộ mappings/rules mới review quaUI.10scenarios chạy verified/partialverified theo chất lượng,1mixedcurrency safeBLOCK trước run. So rawSHA, tất cảgroupkeys/left-rightamount/delta bằng Decimal, membership không lặp, toàn bộ physical rows/invalid/out-of-period partitions, CSV/XLSX snapshot và reload đều PASS. Bộ1k cuối gồm1000/985dòng,1000groups,966EQUAL/19AMOUNT_MISMATCH/15UNMATCHED;966/1000=96,60%,variance7,03VND. Excel có giới hạn15significantdigits khi người dùng tính toán; exactDecimal strings/OOXML và CSV được giữ, không ép float để chấm.

Sau fullsuite mới bắt đầu rà soát môi trường theo yêu cầu chủ dự án. `uv sync --locked --offline`/`uv pip check`:51packages tương thích, giữ lockfiles và venvhiệncó. Pythonproject3.12.14;3.11.9giữchoalias/phầnmềmkhác; Node24.19.0/npm11.17.0; Playwright1.64.1/Chromium; Git2.55.0/GCM2.9.1. GitHubCLI2.100.0 đã có, authstatusPASS, APIuser đúng chủ repo và repositorypermissionADMIN; không cần đọc/in/chuyển token hoặc đăng nhập lại.

Tạo CurrentUserAllHosts profile cho PowerShell7 và WindowsPowerShell tại Documents thực tế doWindowsresolve (máy này redirectOneDrive), chỉ tự kích hoạt `.venv` trong đúng repository hoặc thư mục con, giữ promptgốc, không ghi đèvenvkhác; rời projecttự deactivate phần dohookbật. Existinghostprofile được giữ nguyên; không hạ executionpolicy hoặc dùngBypass.10freshshellcasesPASS trên cả hai shells: mởproject/subdirectory, mởngoài, đi vào/rời project; đúnginterpreter`.venv`vàPython3.12.14trongproject. VSCodeworkspace chỉ định interpreter, activationcommand vàcwdworkspace; Python/PythonEnvs/PowerShell extensions có sẵn, cácsettingskeys được đốichiếumanifestinstalled. Không cài lại dependency/server/tool đang chạy tốt hoặc dựng thêm môi trường.

DockerDesktop4.89.0/LinuxEngine29.7.2/Compose5.5.0, contextdesktop-linux/WSL2:4serviceshealthy,loopback127.0.0.1:18180,2namedvolumesđúngproject; khôngserviceDB/backendhostport, OOM=false/restarts0ởlầnđo. SampleRAM trong regression:backend322MiB,worker119,3MiB,postgres175,1MiB,frontend16,46MiB; đây là maxima của96samples, không continuouspeak hoặc dedicatedloadbenchmark. Không tác động UbuntuWSLdistro hoặc dựánkhác.

Backup trước main: `backup_06bf8019bbfe4a1aaab98fbcb62bbe92`,24tables,metadataSHA256 `58e5080da9841a3fbadf4cf0ab9706e64b31f2f5bb99bfa223bceb495a4a8550`; backup10,931s/restore11,039sPASS,publicunchanged,corruption/traversalrejected. Hostcopy metadata+1652publishedfilesSHA PASS; cùng máy, chưa thay off-hostdisasterrecovery. Cácgatesrestart/recreate/main được ghi tiếp sau thực thi, không suy từ backup.

### Bàn giao main — READY_FOR_LOCAL_USE_WITH_LIMITATIONS

Đã fast-forward và push `origin/main` từ `c3ca75887ab9bf782f48ea915605b6506d90c0ec` tới **`34c0ff16b59924fc60fe7f35684a1170f0f8e4fd`**. Build/deploy đúng SHA main này trong Compose hiện có; application diff từ source đã full regression rỗng. Migrations không đổi, schema vẫn `create_agent_workflows`.

| Kiểm chứng cuối | Kết quả |
| --- | --- |
| Backend / PostgreSQL | 265 PASS, 0 FAIL/SKIP, 78,55 giây |
| Browser full suite | 109 PASS, 0 FAIL/SKIP/flaky, 581,489 giây |
| Smoke sau main | 19 PASS, 0 FAIL/SKIP/flaky, 72,618 giây; không cộng replay vào 109 |
| PowerShell mới | 10/10 ca PASS trên hai phiên bản; đúng venv/interpreter trong dự án |
| Restart / recreate / frontend recreate | 3/3 full metadata và artifact checksum PASS; 3/3 session403 trước verify-local |
| Source runtime | 48 tracked Backend hashes trên API và worker; sáu HTTP assets; OCI revision/source PASS |
| Dữ liệu trước nhiệm vụ | Tất cả ID, metadata và SHA gốc giữ nguyên; chỉ workspace policy có thay đổi được phép |
| Sau main | Chart, phân trang PAID, dòng gốc, bằng chứng chênh lệch, export oracle, PDF/DOCX cached và reload đúng run PASS; 0 model submissions |

Backend/worker image `sha256:e2b5cabd53cec8ca519c51b3d07abeb6e5ec1973db71f860a28664b5a04edfac`; frontend image `sha256:b1a4d9e2151c3c68dd98edfa31c8913709d7480bc6f7f1dd6948124fc1bfb349`. Giữ tags `accepted-main-34c0ff1` và các pairs d392c4a/f1ad9f1/5f358c4 để rollback. Một Compose, bốn services healthy, hai named volumes không đổi. Audit không thấy dangling application image mang source label của repository: 0 image tự xóa, không prune/cache/volumes hoặc can thiệp dự án khác; giữ tám application images phân biệt. C: còn khoảng133,1GiB tại audit, không suy thành dung lượng đã giải phóng. Không tuyên bố đã chạy rollback mới trong nhiệm vụ này; đường rollback cũ có bằng chứng tại U và images được giữ.

Backup sau main: `backup_84ebe7f606ac47e8be896010de8c333b`, 24 bảng; metadata SHA256 `faaff586bae3f24366a8dd0d70288dc3d37be3dc9c53086c1fc7e8e5b9add722`; backup8,251s / restore9,034s PASS, không overwrite public. Bản sao trên host được giữ cùng bản trước main; kiểm metadata và mọi file theo manifest. Đây vẫn là bản sao cùng máy, chưa phải phục hồi thảm họa ngoài máy.

Kết quả AI phải đọc tách biệt: 18 mục tiêu NL mới tạo 21 Gemini attempts, gồm 10 mục tiêu hoàn thành sau review khi cần, hai clarification, một safe refusal và năm mục tiêu bị chặn. Không lấy số COMPLETED làm accuracy mọi câu. Riêng mục refusal có stateBLOCKED nhưng intentUNSUPPORTED và0toolsteps là từ chối đúng. Gold hiện hành80câu dùng8HTTPbatches mới trong nhiệm vụ, variants24câu dùng4batches; khi đọc lại typed responses trong cùng nhiệm vụ phải ghi CACHED validation. Benchmark cũ prompt16 có7batches được giữ; một legacy regression có1attempt. Tổng **41 attempts** có đủ job/trace attribution; không reset hoặc loại failure. Việc gắn nhầm finalreceipt của reconciliation vào phase ban đầu trong script kiểm thử đã được sửa theo exact workflowID và giữ nguyên file receipt trước chỉnh; failure ban đầu vẫn hiện diện. Không có workflow bị gửi lại vì mất receipt.

Giới hạn được giữ rõ: hai câu chung thiếu đối ứng/lệch tiền còn có thể thiếu metric và bị chặn; câu nêu rõ `reported_transaction_amount` đã chạy đúng15/19. Follow-up chung có thể hỏi lại. Gold intent78/80, nguồn57/60, slots31/34; variants24/24,16/16,10/10;28/28negative cases an toàn theo rubric, không chứng minh miễn nhiễm tấn công. D04 mới PASS cả gold và workflow reuse, không xóa FAIL lịch sử. Tìm kiếm Ngoại lệ hiện lọc loại/ghi chú, chưa tìm businesskey; chọn dòng hoặc đi từ kết quả Chat/evidence để xem giao dịch cụ thể. Parser flagsON nhưng allowance2/2 và SHA allowlist đã dùng hết, tài liệu mới chưa được cấp xử lý; không báo PDF/DOCX mới PASS LIVE. Qwen hai probe mapping synthetic mới PASS, không bảo đảm mọi tác vụ hoặc tự đổi provider mặc định. Billed cost, tải production, thiết bị vật lý/screen-reader và mọi dữ liệu/cấu hình phần mềm khác đã xóa trong AppData chưa có backup để phục hồi đều ngoài bằng chứng hiện có.

Các công cụ đã triển khai vẫn bật: external AI, Agent, Assistant, parser và Qwen. Global154/200 còn46; Agent135/163, Planner11/30, Assistant2/20 tại audit cuối. Mỗi lần mở Settings đọc lại ledger thực; lượt người dùng sau audit sẽ làm số còn lại thay đổi. Không có workflow GitHub Actions trong repository (API trả0), nên các gates ở đây là kiểm tra local, không gọi là CI PASS.

Mở [ứng dụng local](http://127.0.0.1:18180), bật dự án kiểm thử và tìm **DEMO UAT 1000 giao dịch** để xem hội thoại/run đã chuẩn bị. Kịch bản/câu hỏi và đáp án tại README, fixtures và manifest độc lập tại runtime/demo-acceptance/data. Để tự thử từ đầu, tạo project khác và dùng chính các files tổng hợp. Đóng/mở terminal để nạp profile mới; `python` trong dự án phải trỏ `.venv/Scripts/python.exe`. Hạn mức ứng dụng đã mở theo chỉ dẫn, nhưng không thay quota/billing riêng của Google hoặc allowance LlamaParse.

Receipts chi tiết, screenshots, traces, logs ba lượt full browser (kể cả thất bại), backups và proofs môi trường nằm tại `runtime/demo-acceptance/`, ngoài Git. Commit bàn giao sau phần này chỉ sửa tài liệu; runtime giữ revision34c0ff1 với application diff được kiểm rỗng.

## W. Rà soát môi trường VS Code và Antigravity IDE — 02/11/2026

Phạm vi: môi trường phát triển sau khi chủ máy xóa nhầm AppData; không sửa nghiệp vụ, dependencies/lockfiles, database, quota hoặc quyền AI. Bắt đầu tại main6a4c2a5 sạch, đúng origin chính thức. Không tạo venv, Compose, bản sao repository hay framework mới. Không cài lại phần mềm đang hoạt động chỉ để tăng số lượt cài đặt.

Hiện trạng xác minh: VS Code1.144.0; Antigravity IDE2.6.0 (nền editor1.107.0); Python3.12.14 trong `.venv`, Node24.19.0/npm11.17.0, uv0.12.15, Git2.55.0, gh2.100.0. Antigravity2.24.0 là ứng dụng khác với Antigravity IDE, không coi là bản cài trùng để gỡ. CLI đúng của IDE là `antigravity-ide`, không phải `antigravity`. Hai IDE đã có Python, Python Environments, Ruff, Mypy, PowerShell và Containers extensions; Antigravity dùng Pyrefly cho hỗ trợ Python.

Các lỗi phát hiện và thay đổi:

- Antigravity có interpreter người dùng3.11 và terminal mặc định mang tên dự án khác. `.vscode/settings.json` ưu tiên trình quản lý venv, đặt terminal Windows PowerShell riêng **PowerShell (AI Reconciliation Studio)** và cwd repository. Profile terminal của dự án khác được giữ nguyên. Profile PowerShell cá nhân đã khôi phục ở mụcV tiếp tục xử lý tự kích hoạt; 10ca mở shell/vào/rời dự án đều đạt, đã chạy lại cả ngoài Codex.
- VS Code đã chọn Python toàn cục3.11; Python Environments của hai IDE từng trả versionnull cho `.venv`. PET CLI/JSON-RPC và việc ghi lại cache chỉ giải quyết nhận diện, chưa giải quyết nguyên nhân khởi động Python. Không sửa SQLite hay xóa toàn bộ storage.
- Nguyên nhân gốc được chứng minh bằng `GetFinalPathNameByHandleW`: Python dưới `%APPDATA%/uv/python` mà lệnh trong Codex nhìn thấy thực tế nằm trong `LocalCache/Roaming` của gói MSIX Codex. Vì vậy kiểm tra PASS trong Codex trước đó chưa chứng minh IDE bên ngoài truy cập được Python nền; venv launcher trả `No Python at`, Mypy EPIPE, Pyrefly/Pylance không truy vấn được interpreter.
- Chuyển hai bản Python đã khôi phục3.12.14/3.11.9 sang `C:/Users/admin/.local/share/uv/python`, giữ tên thư mục theo patch version chuẩn uv. Liên kết lại chính `.venv` hiện có bằng `uv venv --allow-existing`, giữ51gói và lockfile. Đặt `UV_PYTHON_INSTALL_DIR` ở cấu hình tài khoản cả trong và ngoài MSIX; uv cập nhật đăng ký Python/aliases offline. Giữ `python` toàn cục3.11.9 cho tương thích cũ; có `python3.12` và `python3.11`. Các đường dẫn Python AppData cũ còn thiếu được nối về bản dùng chung bằng junction; không thay thư mục Python cũ đang tồn tại hoặc sao chép thêm interpreter.
- Thông báo Antigravity `Default interpreter path '${workspaceFolder}...' could not be resolved` còn xuất hiện do Python Environments1.20.1 thử phân giải biến workspace ở phạm vi global. Bản1.40.0 của VS Code cần editor>=1.110 nên không ép cài vào Antigravity1.107. Workspace dùng `python-envs.defaultEnvManager=ms-python.python:venv`; cấu hình người dùng của hai IDE đặt đường dẫn dự phòng cụ thể `C:/Users/admin/.local/bin/python3.12.exe` và autoActivationType command. Backup cấu hình trước sửa nằm trong runtime, không vào Git. Sau reload, log Antigravity chọn đúng `.venv`3.12.14 theo defaultEnvManager, không lặp lỗi phân giải đường dẫn.
- Pylance từng mất hơn10giây để liệt kê workspace và cảnh báo quá nhiều thư mục. Cấu hình include backend/tests/tools, extraPaths backend, exclude môi trường/dependencies/runtime/build output; watcher bỏ các thư mục sinh tự động. Log workspace sau thay đổi tìm79source files trong khoảng0,6giây ở một lượt đo; không gọi đây là benchmark tổng thể.
- Ruff từng lỗi dò executable qua Python và rơi về bản bundled. Workspace trỏ thẳng `.venv/Scripts/ruff.exe`; log mới xác minh Ruff0.17.3 và lệnh chạy server tại đúng đường dẫn. Mypy dùng interpreter `.venv`, importStrategy fromEnvironment; log sau khôi phục của cả hai IDE chạy mypy2.4.0 và publish diagnostics cho file đang mở. Pylance nhận đúng Python3.12.14; Pyrefly chạy language server và truy vấn được môi trường.

| Kiểm tra thực tế của lượt này | Kết quả |
| --- | --- |
| `uv sync --locked --offline`, `uv pip check` | PASS; 51gói cài tương thích, không đổi lock |
| PowerShell7 và Windows PowerShell, mở tại root/thư mục con/ngoài, vào/rời root | 10/10 PASS; trong dự án dùng đúng `.venv`3.12.14 |
| PET CLI và JSON-RPC của hai extensions | PASS nhận version3.12.14/x64 của venv |
| Python/gh/Docker/uv từ tiến trình Windows ngoài MSIX | PASS; xác minh GetCurrentPackageFullName trả15700 (không có package identity) |
| Python dùng chung ngoài repository / đường dẫn AppData tương thích | PASS3.12.14, 3.11.9 và đường dẫn base3.12 cũ; không tạo venv thử khác |
| Dịch vụ Python trong IDE sau sửa và mở lại | PASS interpreter `.venv`3.12.14, Mypy chạy được trong cả hai IDE; Pylance/Pyrefly hoạt động |
| Node và Electron runtime của hai IDE gọi Python bằng subprocess | PASS; bằng chứng bổ sung, không thay thế log extension host |
| Ruff CLI / mypy CLI | PASS; mypy47source files |
| `pytest -q -m 'not integration and not live'` sau liên kết lại Python | 203PASS, 62deselected, 14,23giây; offline/mock, không live AI hoặc PostgreSQL integration |
| TypeScript / ESLint / `npm ls --depth=0` / npm registry ping | PASS |
| Docker Desktop / context / Compose config | PASS; running, desktop-linux, config hợp lệ |
| Backend / worker / frontend / PostgreSQL | 4/4healthy, cùng một Compose của dự án |
| HTTP `/`, `/health`, `/api/live`, `/api/ready` | 4/4HTTP200 |
| Session demo sau khi Docker khởi động lại bên ngoài lượt thao tác của Codex | Ban đầu403 đúng fail-closed; chạy `tools/verify-local.ps1` xác minh cổng loopback rồi `/api/session`200 |
| GitHub API user và repository | PASS tài khoản đúng; repository chính thức, quyền ADMIN |

Docker Engine29.7.2/Compose5.5.0 và WSL2 hoạt động. WSLSvc/WSLService chạy automatic, vmcompute chạy manual bình thường; không suy ra thiếu `com.docker.service` là lỗi với bản Desktop cài theo người dùng. Không restart Docker hoặc recreate services trong lượt này. Hai named volumes và image revision34c0ff1 giữ nguyên; Compose của dự án khác được bảo toàn. Một mẫu tài nguyên: Backend142MiB/384MiB, frontend11,04MiB/128MiB, PostgreSQL83,46MiB/256MiB, worker107,4MiB/512MiB; C: còn khoảng132,1GiB. Không prune/xóa tài nguyên.

**Giới hạn và phân biệt cảnh báo:** các lỗi launcher/interpreter/EPIPE ở log cũ được giữ làm bằng chứng lịch sử, không gọi là lỗi hiện hành sau khôi phục. Sau người dùng mở lại và reload cấu hình, log phiên VS Code171729 và Antigravity171735 ghi nhận dịch vụ hoạt động. Trực tiếp đọc Problems của Antigravity còn hai cảnh báo Pyrefly `unnecessary-type-conversion`: lời gọi bool dư thừa tại api.py437/455; đây là cảnh báo mã nguồn, không phải thiếu Python hoặc hỏng môi trường. Không sửa nghiệp vụ hoặc tắt trình phân tích để xóa cảnh báo. Pyrefly dùng cấu hình mypy được nhập tự động (Legacy); dòng Python extension báo languageServerNone là do Pyrefly phụ trách language services, không phải mọi hỗ trợ Python bị tắt. Conda/Poetry/Pipenv/Pyenv chưa cài và không thuộc stack uv của dự án, không cài thêm managers trùng chức năng chỉ vì log dò tìm.

Python nền dùng chung được xác minh ở ngoài repository và ngoài MSIX, nhưng mỗi dự án vẫn phải có venv/dependencies phù hợp. Không tự sửa các venv/lockfile của dự án cũ hoặc cam kết mọi phiên bản Python khác đã phục hồi. Các terminal đã mở từ trước có thể báo environment stale; mở terminal mới để nạp môi trường mới. Trong hai IDE đã quan sát được prompt `.venv`; không nhập lệnh Windows qua tự động hóa UI. Cấu hình mới sẵn sàng cho phát triển và kiểm thử local trong phạm vi đã xác minh.

Lượt này không gọi Gemini/Qwen/LlamaParse hoặc thay đổi cấu hình công cụ AI. Không chạy lại full265Backend/109E2E vì chỉ sửa môi trường và thiết lập editor; kết quả nghiệm thu mụcV là bằng chứng của lượt trước. Lượt203unit mới có một StarletteDeprecationWarning về testclient/httpx từ dependencies đã khóa; không tự cài thêm httpx2 hoặc thay lockfile để che cảnh báo. Receipts môi trường mới nằm tại `runtime/ide-environment/`, ngoài Git; đây là bằng chứng local, không phải CI hoặc bảo đảm đã phục hồi mọi dữ liệu AppData bị xóa.

## X. Kiểm tra lại môi trường sau khi mở lại máy — 03/11/2026

Chủ dự án yêu cầu rà soát lại và báo cáo kết quả kiểm thử. Bắt đầu tại main163b7e9 sạch, đúng repository/origin; không thay đổi mã nghiệp vụ, lockfiles, cấu hình AI hay dự án khác. Python nền dùng chung vẫn ở `C:/Users/admin/.local/share/uv/python`, venv Studio trỏ đúng bản3.12.14; aliases3.11.9/3.12.14, biến UV_PYTHON_INSTALL_DIR của tài khoản, cấu hình người dùng của hai IDE và đường dẫn tương thích AppData còn hoạt động. Đã kiểm tra lại từ tiến trình Windows ngoài MSIX Codex (GetCurrentPackageFullName=15700), không chỉ dựa vào kết quả trong Codex.

**Điểm đã xử lý:** Docker Desktop/WSL2 chạy nhưng cả bốn container ứng dụng đang dừng từ lượt tắt trước: Backend/frontend/PostgreSQL exit0, worker exit137; OOMKilled=false ở cả bốn, chưa đủ bằng chứng gọi worker là lỗi thiếu RAM. Hai volumes và bốn container/images cũ còn nguyên. Chạy `docker compose start --wait --wait-timeout 90`, không build/pull/recreate hoặc tạo hạ tầng khác. Đủ4healthy với chính các IDs cũ e32d2ba31703/9597a1e33d2c/22fa413d2693/c66ce610a473. Session ban đầu403 đúng cơ chế fail-closed sau khởi động; `tools/verify-local.ps1` xác minh published ports loopback rồi `/api/session`200. Khi tự mở lại ứng dụng, dùng `tools/start.ps1 -SkipBuild` như README; restart policy unless-stopped giữ nguyên ý nghĩa không tự bật container đã bị dừng thủ công.

| Xác minh mới ngày03/11 | Kết quả |
| --- | --- |
| Python dùng chung ngoài repository, ngoài Codex | 3.12.14 và3.11.9 chạy được; đường dẫn base3.12 cũ chạy được |
| Hai phiên bản PowerShell: mở trong/ngoài/thư mục con, vào/rời dự án | 10/10PASS; đúng `.venv`3.12.14 trong Studio |
| `uv sync --locked --offline`, `uv pip check` | PASS;51gói tương thích, không đổi lock |
| Unit offline/mock chạy bằng Python ngoài MSIX | 203PASS,62deselected,9,17giây;1deprecation warning |
| Toàn bộ backend/PostgreSQL trong backend hiện có | 265PASS,0FAIL/SKIP,57,15giây;1deprecation warning |
| Playwright MANUAL, nhóm hồi quy sau sửa UI/workflow | 19/19PASS,0FAIL/SKIP/flaky,77,40giây |
| Ruff / mypy / TypeScript / ESLint / npm dependency tree | PASS; mypy47source files |
| Chromium của Playwright khởi chạy ngoài MSIX | PASS; executable hiện hữu, launch headless thành công, không cần tải lại |
| GitHub CLI ngoài Codex | PASS đúng tài khoản, repository chính thức, quyền ADMIN |
| Docker Desktop/Engine/Compose, bốn healthchecks | PASS; desktop-linux,29.7.2/5.5.0, một Compose của Studio |
| HTTP `/`, `/health`, `/api/live`, `/api/ready`, `/api/session` | HTTP200 sau xác minh loopback |

Không cộng203unit Windows vào265backend vì đó là phần chồng lắp chạy trên hai môi trường. Bộ265 dùng `tools/test-postgres.ps1 -All`, tests trong `/tmp` của backend hiện có, schema UUID `test_*` và storage tạm; không chạy tests phá hủy trên bảng public. Nhóm19browser có cả mock contracts và luồng CSV/XLSX local thật qua verified exceptions/exports/reopen; dữ liệu tổng hợp phục vụ kiểm thử được giữ theo quy tắc hiện có. Chế độ provider MANUAL, không bấm gọi model trả phí. Bộ109Playwright đầy đủ ở mụcV là kết quả ngày02/11, không trình bày như đã replay cả109 ở lượt này. Đợt môi trường trước ở mụcW đạt203unit/10shell; lượt này bổ sung full backend/PostgreSQL và19browser sau mở lại.

Log VS Code phiên153900 và Antigravity phiên153950/window2 của Studio chọn đúng `.venv`3.12.14; Mypy/Ruff/Pylance/Pyrefly hoạt động. Mở Studio trong cửa sổ Antigravity riêng để bảo toàn project khác đang mở. Không tái hiện `No Python at`, EPIPE, lỗi khởi động Mypy hoặc thông báo không phân giải được defaultInterpreterPath trong các log workspace này. Còn dòng log của PET về cancelRequest/cache/không có HKLM Python; registry/discovery theo người dùng và việc phân giải cuối vẫn thành công. Antigravity còn telemetry cảnh báo bản ghi khám phá ban đầu thiếu version, rồi resolve thành công3.12.14/x64; không coi là mất interpreter. Không tạo registry máy giả, xóa cache, sửa mã extension hoặc ép nâng extension không tương thích để làm log trống.

Giới hạn cũ được giữ rõ: hai cảnh báo Pyrefly về bool dư thừa và deprecation TestClient/httpx không phải lỗi cài đặt; không đổi dependency hoặc tắt kiểm tra để che chúng. Chưa kiểm thử mọi dự án cũ/phiên bản Python khác. Không thay hạn mức/công cụ AI; API Settings cuối lượt vẫn Agent/Assistant/Qwen/Gemini configured/enabled tương ứng, Gemini154/200, bằng số cuối mụcV nên không phát sinh lượt Gemini mới. Không lấy cờ configured làm bằng chứng live inference mới. Không thực hiện prune/xóa volumes, không restart Docker engine hoặc tác động Compose dự án khác; Backend/frontend giữ runtime revision34c0ff1 vì application source không đổi. C: còn khoảng128,2GiB tại kiểm tra.

Kết luận trong phạm vi kiểm tra: môi trường phát triển và ứng dụng local hoạt động, không phát hiện lỗi chức năng môi trường còn chặn các checks trên. Cảnh báo/giới hạn không bị gọi là đã hết tuyệt đối. Receipts mới tại `runtime/ide-environment/recheck-20261103/` ngoài Git; log/test artifacts trước đó được giữ riêng. Thay đổi Git của lượt này chỉ bổ sung báo cáo kiểm chứng.

## Y. Hội thoại, clarification và natural language reliability — 03/11/2026

### A. Phạm vi và release gate

Bắt đầu tại main/origin `58d2d65`, sạch; feature `codex/assistant-conversation` trong repository hiện có, không worktree/Compose/dependency/migration mới. Runtime đầu nhiệm vụ `34c0ff1`, đủ4healthy và2volumes. Mục tiêu là trải nghiệm Assistant, typed routing/query/context, xác nhận và nghiệm thu; Matcher/Verifier/Decimal/parsers/normalization/lockfiles không sửa. `worker.py` chỉ đổi nội dung lỗi review, không đổi claim/lease/retry/queue publication.

**Kết luận hiện hành: READY_FOR_GUIDED_DEMO.** Source ứng dụng/runtime `dac8dd179fe9cd57bf5e86abae8d4784103c0d6b`;302Backend/PostgreSQL,117browser và39checks sau triển khai PASS. Đủ4healthy, bảo toàn dữ liệu gốc và backup/restore đã kiểm. Đọc phầnI để đánh giá mức sẵn sàng local và giới hạn; các lượt lỗi và release trung gian ở dưới là lịch sử được giữ, không thay kết quả chốt. Log/receipts/screenshots/backup nằm tại `runtime/assistant-conversation/`, ngoài Git.

### B. UI/UX và files

Composer vẫn một textarea tự giãn40–180px, Enter/Shift+Enter/IME/draft/upload/drop/chips/idempotency/recovery. Focus bàn phím nằm trên một bề mặt composer; textarea không có outline riêng. Nút gửi dùng icon spinner18px, không còn component chứa chữ trong ô40px; synchronous send lock chặn Enter/click đồng thời và focus trở lại input sau gửi. Transcript không lặp tên AI/timestamp/“Chuẩn bị dữ liệu” trên từng tin: metadata dưới dấu ba chấm, tool steps trong “Chi tiết xử lý”. Reply chỉ render workflow tại phản hồi mới nhất; dữ liệu message/audit không bị xóa.

CLARIFICATION có vùng hội thoại riêng, câu hỏi, lựa chọn metric từ server hoặc “Trả lời bằng tiếng Việt”; không checkbox hay nút approval. MAPPING/RECONCILIATION giữ thẻ quyết định, tóm tắt nguồn/keys/metric/period/currency/tolerance, chỉnh sửa thu gọn, extraction acknowledgement và nút ghi rõ tác động. Generic checkbox được thay bằng “Duyệt ánh xạ và chuẩn hóa” / “Duyệt quy tắc và đối soát”; server gates không giảm. Kết quả ưu tiên counts từ snapshot, bằng chứng/phạm vi mở khi cần; bảng ẩn UUID, có vị trí/khóa giao dịch và nhãn từ schema thật. Chuỗi định danh giống enum(EQUAL/OPEN/PAID) vẫn giữ nguyên; chỉ dịch enum metadata của verified result/exception.

Ảnh trước23states×5width được giữ tại `runtime/assistant-conversation/before/`; ảnh sau layout tại `runtime/assistant-layout/` và clarification/loading tại `runtime/assistant-conversation/after/`. Kiểm390/768/1366/1440/1920, multiline, loading, failed/partial/allowance/permission, history, keyboard, charts, evidence, export. Đã xem trực quan mobile approval, clarification tablet, composer desktop và results. Không có chứng nhận screen-reader hoặc bàn phím thiết bị vật lý.

Files ứng dụng: `frontend/src/AssistantStudio.tsx`, `AgentWorkflowPanel.tsx`, `AgentResultBlocks.tsx`, `App.tsx`, `agentTypes.ts`, `styles.css`, `types.ts`; Backend `agent_intents.py`, `agent_jobs.py`, `agent_workflows.py`, `agent_api.py`, `assistant_api.py`, `assistant_tools.py`, `data_query.py`, contracts và thông báo review của worker. Browser fixture dùng dist candidate tại cùng origin/API để kiểm trước release, không dựng server/container thứ hai. Existing E2E chuyển import test sang fixture chung; assertions/oracles cũ giữ nguyên, chỉ đổi tương tác approval/focus theo contract mới.

### C. Root causes, sửa và regression

| Lỗi thực chứng | Nguyên nhân và sửa | Kiểm chứng |
| --- | --- | --- |
| Composer lồng khung, loading lệch | Outline trên textarea bên trong border; Spinner có chữ. Focus chuyển ra surface, spinner icon cố định | Năm widths, keyboard/IME/double submit/loading/draft |
| Bản nháp không tự giãn khi thu hẹp màn hình | Chiều cao chỉ đo khi text thay đổi; width đổi làm wrap mà height giữ cũ. ResizeObserver chỉ theo thay đổi width, tránh vòng lặp height | Regression desktop→390→desktop FAIL trước/PASS sau sửa, draft và nút gửi giữ nguyên |
| Clarification trông như approval | Chung ReviewCard/checkbox và luôn giữ preview | Renderer riêng; scoped reply đủ điều kiện advance cùng workflow; mapping/rule vẫn approval |
| QUERY_FIELD_INVALID với money fields | Run có metric duy nhất nhưng query thiếu metric_id, money fields chưa được mở | Regression PG FAIL trước sửa; resolver bind đúng approved contract, Decimal2,75VND PASS; ambiguity/absence/foreign context giữ gate |
| Top lệch đúng sort nhưng sai population | Model bỏ comparison_state AMOUNT_MISMATCH, chỉ sort variance | Semantic guard bắt filter, prompt hướng dẫn; live repaired trả3dòng/19eligible matches đúng thứ tự |
| Follow-up theo vị trí có thể lấy nhầm trang | Backend chưa lưu trang/sort, context chỉ run cũ | QuerySelection bền, result_position bound current run/page; race đổi trang trong inference trả STALE_CONTEXT, không giải thích nhóm khác |
| Nguồn rút gọn rõ vẫn hỏi lại | Thiếu alias có bằng chứng và safe listing path | Alias duy nhất trong filename, một bảng, từ vựng liệt kê hạn chế; không đoán A/B theo upload order |
| Tổng variance qua query thay snapshot | Intent chọn sum_decimal toàn run | Sau validation chuyển sang SUMMARIZE_RESULTS; filtered/group analysis giữ query |
| Nguồn tên gần giống có thể reuse current run | Prompt không đủ bảo đảm model từ chối | Native policy giảm xuống CLARIFY; fake source/permissions vẫn fail closed |
| Tự duyệt/bỏ currency chỉ bị hỏi lại | Chưa có denial trước provider cho Agent | Explicit authority guard0cloud/0tools; không cản approved reuse hoặc câu “không tự duyệt” |
| Câu phủ định bị hiểu thành yêu cầu vượt gate | Guard bỏ qua tiền tệ/nguồn chưa loại phủ định; accent folding gom “đừng” với “dùng” | Bộ nhận yêu cầu tường minh loại phủ định sát động từ, giữ Unicode trước khi bỏ dấu; regression FAIL→PASS, cả trường hợp phủ định rồi yêu cầu thật; currency/FX/scope validators không đổi |
| Mapping draft mất sau chuyển nguồn/sheet | Render table mới với profile/mapping cũ trong lúc async load | Detail scope dataset/table và component key; delayed-profile regression và UAT giữ loại dữ liệu |
| Reply lỗi bảo người dùng xác nhận thẻ | Thông báo chung của worker không phân biệt nguyên nhân | Giữ redacted DomainError.message_vi; clarification không bị dẫn sang approval giả |

Các guards mới là heuristic[D]/allowlist có tests; không nhận là thuật toán NLP đã hiệu chỉnh hoặc hiểu mọi câu tiếng Việt. API vẫn kiểm role/scope/revisions/nonce/fingerprint/expiry/pending jobs, không gắn user_confirmed từ chat. Không tự approve, sửa tiền, raw hay oracle.

### D. Ngôn ngữ tự nhiên: mẫu số và bằng chứng riêng

Giữ80gold/24variants cũ, thêm24câu độc lập/24chủ đề tại `tests/fixtures/assistant-conversation-cases.json`. Không sửa oracle cũ để tăng tỷ lệ. Prompt hiện hành `agent-intent-26`.

| Tập/cách đo | Intent | Nguồn | Slots/ngữ nghĩa | Negative/safety | Giới hạn |
| --- | ---: | ---: | ---: | ---: | --- |
| 80gold,8batches mới LIVE | 79/80 | 60/60 | 34/34 | 20/20 | Routing, không80workflow; N08 gold cũ mong UNSUPPORTED nhưng yêu cầu hiện hành báo thiếu metric bằng CLARIFY |
| 24variants,4batches mới LIVE | 23/24 | 16/16 | 10/10 | 7/8 | VN08 raw proposal chọn reuse khi xin nguồn gần giống; bị sửa ở native policy sau đó |
| 24variants CACHED revalidation trên policy mới | 24/24 | 16/16 | 10/10 | 8/8 | 0HTTP; không gọi đây là inference mới |
| 24câu mới,4batches mới LIVE | 22/24 | 14/16 | 10/10 | 8/8 | C05 hỏi lại nguồn B; C16 chọn full-run sum thay snapshot |
| 24câu mới CACHED revalidation sau resolver/policy | 24/24 | 16/16 | 10/10 | 8/8 | 0HTTP; C05 dùng safe listing và C16 đọc snapshot |

Model-only output và hệ thống sau policy không được gộp thành một accuracy. Gate finalizer gốc ≥95%intent/source,≥90%slots được đo; negative phải xem sau server policy và native tests. C12/C24 có model hỏi lại nhưng workflow thật từ chối trước provider. N08 là khác biệt taxonomy giữa gold lịch sử và yêu cầu mới về chỉ tiêu chưa tồn tại; giữ strict79/80, không biến thành100%.

LIVE workflow qua source API/TestClient/queue thật trong container hiện có, không HTTP server mới: top3mismatch + giải thích dòng thứ hai đúng cùng run/group; Decimal và source refs giữ nguyên. Clarification→reply trên project TEST có approved payment semantics hoàn thành đúng workflow, trả200UNPAID; nonce/reply binding hoạt động, không tạo contract/mapping approval. Một thử trên UAT mới chỉ có cột trạng thái string bị QUERY_SEMANTICS_REQUIRED đúng gate, không coi là mất tiền hoặc tự sửa semantics để PASS. UI readback sau release được ghi ở phần phát hành.

### E. Chất lượng, dữ liệu và giới hạn

`tools/test-postgres.ps1 -All -Source`:302PASS/0FAIL/SKIP trên UUID schemas và storage tạm, cùng PostgreSQL/Backend hiện có;92,22s trên source chốt sau sửa guards (lượt trước134,04s). Bao gồm financial oracle/property/security/auth/persistence/export contracts và regression mới. Baseline265 không cộng lại;302=231offline+71PG. Ruff, mypy47files, TypeScript, ESLint, production build,79Python files formatting, uv lock/pip consistency và repository/secrets/Markdown paths PASS. Starlette/httpx deprecation warning giữ nguyên, không đổi dependency để che warning. Full117browser và39postdeploy checks ở phầnI, không cộng các lượt replay thành tests mới.

Full browser đầu112/114PASS: một ledger assertion bị nhiễu do inference của Codex chạy đồng thời và một mapping draft race thực tế. Lượt tiếp114/115PASS bị chạy chồng hai Playwright cùng artifacts ở ca export cuối, kèm ENOENT trace; đây là lỗi orchestration kiểm thử, không được gọi full PASS. Logs/failure screenshots được giữ; không tăng timeout/retry hoặc sửa oracle. Lượt cuối chạy duy nhất một browser runner với build cố định và output riêng: **116/116PASS,0FAIL/SKIP/retry,12,8phút**, gồm toàn bộ11UAT scenarios và bộ1000giao dịch, oracle/CSV/XLSX/reload. `browser-stable.log` là receipt chốt; không cộng các lượt replay thành tests mới.

Backup trước sửa `backup_0772609005574617a32d91471a43d1c3`,24tables, metadataSHA256 `855a365717f26315bc8fbd77404e042accf63a069a7e17e7fee118bf7ac77a5e`, backup17,981s/restore9,870s PASS; checksum/path traversal probes từ chối đúng. Host copy giữ nguyên. So mọi original primary key/metadata và1.841files với backup:0missing/0changed/0checksumfail; policy external_request_budget210 là ngoại lệ đã được audit, normalize về policy trước cho đúng phép so. Không chỉ so counts hoặc bỏ hash. Hai persistent volumes, schema `create_agent_workflows`, approved mappings/contracts/runs/conversations gốc giữ nguyên.

### F. AI usage và Docker/Git

Global154→203/210; Agent135→184/193; Planner11/30, legacy2/20 không đổi.49attempts mới=42benchmark+5Agent+2review, đủ49trace.43VALIDATED/6provider-schema-semantic failures được giữ; VALIDATED không là tỷ lệ câu trả lời đúng.48token receipts tổng726.021tokens; actual billed cost NOT VERIFIED. Sau chỉ dẫn tiếp tục của chủ dự án có audit Agent163→183→193, global/workspace200→210; không reset reservations/đổi model/key/provider. Cài mới vẫnOFF/0, Qwen/parser0calls mới, LlamaParse2/2 không mở thêm. Hạn mức còn lại là min global/workspace/task và có thể đổi khi người dùng tự thử.

Runtime đầu và rollback images `accepted-main-34c0ff1` còn nguyên; không prune/images/volumes hoặc tài nguyên dự án khác. Sample trước release:Backend222MiB/384,worker209MiB/512,PG167MiB/256,FE13MiB/128; không là load benchmark/peak liên tục. Feature chưa được coi là main release tại lúc ghi phần này; commit/source/runtime/digests/health/smoke và mức sẵn sàng sẽ ghi sau gate.

### G. Demo dự kiến và giới hạn còn lại

Chọn TEST **DEMO UAT 1000 giao dịch** có mappings/payment semantics/rule đã duyệt, mở hội thoại nghiệm thu. Câu chat: “Cho tôi xem ba nhóm giao dịch lệch tiền lớn nhất…”, “Giải thích giao dịch thứ hai”, hoặc trả lời câu hỏi bổ sung “Cho xem các giao dịch chưa thanh toán của nguồn A”. Expected:966EQUAL/19AMOUNT_MISMATCH/15UNMATCHED, absolute variance7,03VND,200UNPAID,686PAID,114COMPLETED. COMPLETED không được gọi PAID. Mở dòng nguồn/evidence rồi CSV/XLSX từ verified run; reload/history giữ cùng workflow/context. Để thử từ đầu dùng24files tổng hợp tại `runtime/demo-acceptance/data/`, project TEST khác và approval rõ nghĩa/phạm vi.

Toàn pipeline UAT qua UI/manual fallback và native engines là PASS LOCAL; không trình bày mọi bước mapping/planner như một live end-to-end mới. Các model requests cụ thể/benchmarks có receipts riêng. PDF/DOCX mới, live inference mọi kiểu câu, nhiều người dùng/Internet, thiết bị vật lý/screen-reader, off-host disaster recovery và billed cost nằm ngoài bằng chứng nghiệm thu này. Không dùng nhãn production-ready hoặc tuyên bố hết mọi lỗi phần mềm.

### H. Phát hành và kiểm tra trực tiếp

Đợt ứng dụng đầu `1ac2139e57c3528187e4d7e9eb6deb68704b283e` đã push feature rồi fast-forward main/origin, build đúng source và up cùng Compose.37/37postdeploy browser và1/1UAT1000PASS, cùng tài sản phục vụ thật, không cờ candidate. So42filePython trong Backend/Worker bằng SHA256 với source; image revision/source labels và7index/assets HTTP khớp image. Bốn services healthy, hai volumes giữ nguyên, không migration/dependency mới hoặc prune.

So metadata20bảng nghiệp vụ vàartifact refs/checksums trước/sau recreate PASS:224projects,510datasets,919mapping revisions,397canonical datasets,185runs,322exports,527conversations/1.114messages,337workflows;23nhóm kiểm tra gồm1.821artifacts/185runfiles/322exportfiles. Đây là phép so metadata theo ID và nội dung, không chỉ so counts. Sau proof loopback, UI đọc lại hội thoại LIVE đúng một workflow/200UNPAID, trang2vàdraft còn sau reload, bảng gốc không đổi, raw evidence đúng row; snapshot966/19/15 vàDecimal7,03VND đúng. Usage203trước/sau, không có inference mới. Receipts đợt đầu giữ riêng với hậu tố`first`.

Quan sát ảnh mobile của runtime phát hiện lỗi giãn draft khi đổi độ rộng. Đã tái hiện bằng regression độc lập và sửa trong cùng feature; typed API/engine không đổi. Targeted regression, TypeScript, ESLint và buildPASS. Kiểm tra phủ định tiếp theo sửa false positives ở currency/source guards;69intent tests và231offlinePASS, cácPG tests không chạy offline được ghi71SKIP, không tính là302fullPASS của source mới. Backend đầy đủ và browser được replay trước bản tích hợp tiếp theo.

Lượt117browser đầu của bản giãn draft:116PASS/1FAIL, tổng3,9giờ sau gián đoạn phiên; ca C Vận đơn composite timeout tại GET metrics sau reload, trước đó oracle và hai exports đã đạt. Context teardown cũng timeout; không có container restart/OOM và không có tracezip hoàn chỉnh. Không đủ bằng chứng quy lỗi cho ứng dụng hoặc coi lượt nàyPASS. Giữ log/error screenshot, không tăng timeout/retries hoặc đổi oracle; kiểm lại ca composite và full suite trong lượt liên tục. Kết quả và identity bản chốt được bổ sung sau gate.

Gate source bổ sung đã chốt: **302Backend/PostgreSQL PASS/0FAIL/SKIP,92,22giây** sau sửa guards; **117/117Playwright PASS/0FAIL/SKIP/retry,11,5phút**, trên dist cố định và cùng API. Ca composite chạy riêng23,6giâyPASS rồi17,8giâyPASS trong full suite. CACHED-only revalidation trên source cuối:79/80gold,24/24variants,24/24conversation, toàn bộ source/slots/negative denominators giữ đúng bảngD; không enqueue/gọi provider, ledger203→203. Ruff/79Python formats/mypy47/TypeScript/ESLint/build/locks/dependencies/repository/secrets/MarkdownPASS. Bản này chưa được gọi là runtime đã triển khai tại lúc commit source; identity/postdeploy được ghi tiếp khi có kết quả thật.

### I. Hiện trạng hệ thống và mức sẵn sàng sử dụng

**Ứng dụng/runtime đã phát hành:** `dac8dd179fe9cd57bf5e86abae8d4784103c0d6b`, push feature rồi fast-forward main trên origin chính thức. Các commit báo cáo sau mốc này chỉ tài liệu; application diff phải rỗng. Không migration/dependency/Compose mới; schema vẫn `create_agent_workflows`. Local URL `http://127.0.0.1:18180`, chỉ loopback đã xác minh, không tắt auth/CSRF để demo.

| Gate chốt | Bằng chứng và kết quả |
| --- | --- |
| Backend thật + PG | 302/302 PASS, 0 FAIL/SKIP, 92,22 giây; gồm oracle tài chính, property, phân quyền, bảo mật, query/review/context, persistence, exports |
| Browser đầy đủ | 117/117 PASS, 0 FAIL/SKIP/retry, 11,5 phút; gồm 11 tình huống UAT, CSV/XLSX/Decimal oracle/reload và 5 viewports |
| Sau triển khai | 38/38 browser PASS trong 2,9 phút trên assets thật; UAT 1000 độc lập 1/1 PASS trong 1,4 phút; đây là 39 checks replay, không phải 39 test cases mới |
| Source/runtime | 42 file Python Backend/Worker khớp SHA256 source; 7 HTML/assets HTTP khớp image; OCI revision/source labels khớp commit/origin |
| Queue/API | 0 job QUEUED/RUNNING/RETRYABLE_FAILURE khi chốt; `/`, `/health`, `/api/live`, `/api/ready`, `/api/session` đều HTTP 200 sau loopback proof |
| Dữ liệu qua recreate | Metadata 20 bảng và artifact refs/hashes khớp hoàn toàn trước/sau: 259 projects, 582 datasets, 1.055 mappings, 459 canonicals, 214 runs, 378 exports, 582 conversations/1.224 messages, 369 workflows; 2.091 artifacts/214 run files/378 export files |
| Dữ liệu trước nhiệm vụ | So mọi primary key/metadata gốc của 24 bảng và 1.841 file: 0 missing/changed/checksum failures; ngoại lệ duy nhất là budget 210 đã được audit |
| Hội thoại thật đọc lại | Clarification→reply vẫn cùng workflow; 1 panel/200 UNPAID, trang 2 và draft qua reload, bảng gốc không đổi, raw source đúng row; top 3 trong 19 mismatch và giải thích dòng 2 đúng group/run; 0 cloud mới |
| Tài chính | UAT 1000: 966 EQUAL/19 AMOUNT_MISMATCH/15 UNMATCHED, absolute variance 7,03 VND; CSV/XLSX dùng cùng snapshot; approved payment semantics trả 200 UNPAID, không suy COMPLETED=PAID |

Ảnh source/runtime sau sửa tại `runtime/assistant-conversation/after/390/reflow.png`, `deployed/clarification-result-390.png`, `deployed/clarification-result-1440.png`, `deployed/evidence-1440.png`, `deployed/top-three-and-followup.png`. Đã xem trực quan ảnh mobile/composer/evidence. Các kiểm tra keyboard/focus/IME và overflow trên 390/768/1366/1440/1920 PASS; không nhận là chứng nhận WCAG hoặc kiểm thiết bị vật lý/screen-reader.

Image manifest IDs: Backend/Worker `sha256:798c2afbe2f11a3c0583bbb2e024cee5c205729eb388022ad0ac3d23b29f615e`; frontend `sha256:e843ee4440308349746cd155ebc5762f53c195b543aaa96607b64de0fee68a73`. Đã giữ tags `accepted-main-dac8dd1` và các rollback tags trước, gồm `accepted-main-34c0ff1`; không tag đè hoặc prune. Một Compose, hai volumes `ai-reconciliation-studio_postgres_data`/`ai-reconciliation-studio_artifacts`; 4 healthy, 0 restart/OOM của containers hiện hành. Sample cuối: Backend 190,6 MiB/384, worker 104,3/512, PG 140/256, frontend 12,12/128; C: còn 111,9 GiB. Đây là sample, không load/soak benchmark. Rà logs Backend/Worker 10 phút cuối: 0 HTTP 500/ERROR/traceback matches.

**Backup sau nghiệm thu:** `backup_71e7a6fdf216429192946b088b7c81c1`, 24 bảng, 2.709 published files, metadata SHA256 `790fd1c1da03be5a281d77f0df89fbcaac8608a5e60955f0c75957aedfcfdd87`. Backup 17,424 giây; restore 20,068 giây trong schema UUID riêng PASS, public metadata không đổi, corruption/path-traversal bị từ chối đúng. Chạy helper sẵn có trong worker dùng chung image/volume/PG, không thêm service. Bản sao host tại `runtime/assistant-conversation/backup-after/backup_71e7a6fdf216429192946b088b7c81c1/` đã kiểm độc lập metadata và toàn bộ 2.709 checksums. Backup này gồm 588 datasets, 463 canonicals, 216 runs, 382 exports và 586 conversations/372 workflows sau các bài test; số cao hơn snapshot recreate là dữ liệu TEST bổ sung hợp lệ. Bản trước nhiệm vụ vẫn giữ. Không coi cùng volume/host là off-host disaster recovery; rollback image được giữ, không thực hiện lại rollback ứng dụng trên dữ liệu hiện hành trong vòng này.

**AI còn hoạt động trong giới hạn đã cấp:** Agent/Assistant enabled, Gemini 203/210 global/workspace; Agent 184/193, Planner 11/30, legacy 2/20. API trả remaining hiệu lực 7 cho các task vì chung global 7, không cộng chúng thành 21. Có receipts cho 49 attempts mới/726.021 tokens như phần F; không inference mới ở các vòng layout/negative guard/postdeploy/backup. Qwen 0 calls mới trong vòng này; lần probe trước không là kiểm kết nối mới. Parser vẫn 2/2 đã dùng; không đủ allowance để xử lý PDF/DOCX mới. Không reset ledger, đổi key/model/provider hoặc mặc định cloud ON cho source cài mới. Hết 7 lượt thì cloud bị chặn theo policy; đây là giới hạn vận hành cần tính trước khi dùng liên tục.

**Kết luận:** đủ bằng chứng dùng local cho luồng CSV/XLSX đã nghiệm thu và **READY_FOR_GUIDED_DEMO**; không còn P0/P1/P2 đã biết làm hỏng các hành trình trong phạm vi này. Phân biệt hỏi bổ sung/phê duyệt, query metric/context, số tiền, nguồn, export và persistence đã qua native regressions. Các yêu cầu thiếu semantic/currency/coverage hoặc ngoài quyền vẫn hỏi lại/chặn; không coi đó là lỗi và không hạ gate để cho chạy. Lịch sử lỗi kiểm thử/AI được giữ, không tuyên bố mọi request lịch sử thành công.

Chưa đủ bằng chứng gọi production-ready hoặc bảo đảm mọi câu tự nhiên đều đúng: gold strict 79/80; variants/raw LIVE 23/24, conversation/raw LIVE 22/24 trước native policy, sau sửa CACHED 24/24 mỗi bộ (0 HTTP). Không đánh đồng native repair với model accuracy 100%. Internet/nhiều người dùng, soak dài hạn, off-host restore, thiết bị thật/screen-reader, billed cloud cost và inference mọi loại câu không nằm trong nghiệm thu này. Một Starlette/httpx test deprecation warning còn nguyên, không phải lỗi chức năng đã quan sát. Giới hạn này phải đi cùng kết luận sử dụng, không che bằng tổng số tests PASS.

## Z. Giao diện tối giản, source/runtime và Docker cleanup — 04/11/2026

### A. Docker/source audit

Baseline local/main/origin `519a44b08a7ea0da11777f40b9e217022ca5926c`, chỉ tài liệu sau application `dac8dd179fe9cd57bf5e86abae8d4784103c0d6b`. Fresh production build từ source baseline khớp bytes trong frontend image, HTTP và Chromium profile mới với cache disabled. Năm resources thực sự tải khi mở Assistant khớp SHA256; không service worker hoặc bằng chứng cache cũ. **Không có lỗi đồng bộ Docker ở baseline.** Composer xấu do CSS thật: border1px và `:has(textarea:focus-visible)` outline2px; Chromium vẫn đánh dấu textarea focus-visible khi click chuột. Desktop empty height70px, mobile64px.

Baseline Backend/Worker image `sha256:798c2afbe2f11a3c0583bbb2e024cee5c205729eb388022ad0ac3d23b29f615e`; frontend `sha256:e843ee4440308349746cd155ebc5762f53c195b543aaa96607b64de0fee68a73`, đều OCI revisionDAC. Chỉ frontend source thay đổi; Backend/Worker không rebuild hoặc đổi tag giả thành revisionUI. Cần chứng minh lại source42files và assets production sau release.

Runtime mới: frontend source `18706a7864871bfeddd65570c88348676ceb5bba`, image/manifest `sha256:d04074feee418e6e8ae0cadb762b15fbea32aec5c6e673fe24710924fd603d53`, container `21d5f1c49d81d070968fc1050d04dca04939241e456e3615099fa03f916f5150`. OCI source đúng origin và revision18706a7. Backend/Worker vẫn cùng IDs/images DAC; SHA256 toàn bộ42Python files khớp workspace và Git diff backendDAC→18706a7rỗng. Không rebuild Backend/Worker/PG. Bảy HTML/assets khớp host production build=image=HTTP;5resources Chromium tải từ profile mới/cache disabled khớp ba lớp,0serviceworker/0pageerror, usage203→203. Không suy runtime từ tên tag.

| Asset production | SHA256 host/image/HTTP khớp |
| --- | --- |
| index.html | `ee4984588272c3c9ed7e20cc577eeab3777ee1ee52fdecdabc4951dae6e2b216` |
| index-CpPUh-E_.css | `e8fce3f861ad3ec227c15881f41e9ab15ec55bdf6f4ad67757aa228c470ed247` |
| index-kJphbDMg.js | `81bd22057062eafa4cb98233df06ac4b797546295f0f11013fae2bae1e0657f2` |
| AssistantStudio-BuiYjGA5.js | `de93b6bdc16036a50086383a512f2216fd0c5aaef5c60d4e90bb1f88729e6b18` |

Ba lazy assets DataDrawer/ReconciliationStudio/Evidence còn lại cũng khớp trong `runtime/minimal-interface/component-identity.json`. Computed runtime tại năm widths: pointer border0/outline none/noinset, keyboard inset2px/textareaoutline none; empty60desktop/56mobile. Đã xem ảnh production `after/pointer-1440.png` và `after/keyboard-390.png`, khác baseline thực tế.

### B. UI trước/sau và khả năng dùng bàn phím

Sửa tại selectors gốc trong `styles.css`: bề mặt trắng/neutral gray, blue accent; sidebar/header ít đường kẻ, project/history/menu dùng vùng nhấn nhẹ; Settings, review/fieldset/manual fallback/result/evidence bỏ khung ngoài lồng nhau. Bảng và controls vẫn có ranh giới khi cần. Hợp nhất tokens màu/border/radius/shadow, selectors bảng/checkbox/rule-builder và media query Assistant768px; không nối override cuối file, thêm dependency/framework hoặc thay contracts.

Composer là một bề mặt neutral bo24px, border0, empty60pxdesktop/56pxmobile. Click chuột không outline hay underline; Tab có inset underline2px nhìn rõ, textarea không khung riêng. App Shell theo dõi pointer/Tab/Escape chỉ để hiển thị focus; controls khác giữ focus indicator. Placeholder kiểm contrast≥4,5:1; icon/send/spinner giữ40px, auto-grow/reflow/IME/Enter/Shift+Enter/draft/upload/reply binding giữ nguyên. Cơ sở thiết kế: [Fluent2 elevation](https://fluent2.microsoft.design/elevation) và [W3C Focus Visible](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html), kiểm04/11/2026; không nhận là chứng nhận WCAG.

Ảnh trước từ assets runtime cũ: `runtime/minimal-interface/before/{empty,pointer,keyboard}-{width}.png`, layout/settings cùng thư mục; ảnh bổ sung native drawer/report/Planner tại `detail-before-artifacts/`. Candidate mới tại `candidate/`, `focus/` và layout matrix có23states×5widths390/768/1366/1440/1920. Đã xem trực quan composer1440, keyboard390, Settings1440 và mapping mobile; ảnh runtime sau deploy được bổ sung khi gates đạt. Browser baseline10/10 và detail3/3; candidate targeted16/16PASS. Đây là replay/capture, không tăng117cases độc lập.

### C. Chất lượng nghiệp vụ và dữ liệu

Backend/PostgreSQL **302/302PASS,0FAIL/SKIP,103,37giây** trên hạ tầng sẵn có, UUID schemas/storage tạm. Ruff/mypy47files/TypeScript/ESLint/build/repository checksPASS. Chưa đổi Backend/worker/engine/verifier/Decimal/parsing/approvals/nonces/leases hoặc migrations/dependencies. Giữ oracle966EQUAL/19AMOUNT_MISMATCH/15UNMATCHED và absolute variance7,03VND; CSV/XLSX/reload kiểm snapshot độc lập.

Full candidate đầu **115/117PASS,2FAIL,22,1phút**, logs/failure screenshots/trace được giữ, không gọi là fullPASS. Một failure mobile390 là race focus: animation frame có thể chạy trước React commit bật lại textarea. Sửa bằng `useLayoutEffect` sau commit với mounted/sequence guard, giữ assertion và timeout. Cơ sở [React useLayoutEffect](https://react.dev/reference/react/useLayoutEffect), kiểm04/11. Failure còn lại ở upload C Gộp vận đơn: agent job chờ14,842giây mới claim, xử lý1,123giây, SUCCEEDED lần đầu; vượt assertion15giây trước UI panel. Không chứng minh lỗi financial/AI hoặc quy hết cho CSS; phải kiểm lại ca và full suite, không tăng timeout/retry hoặc đổi oracle.

Sau sửa, năm ca clarification/focus lặp3lượt **15/15PASS,51,6giây**; ca C Gộp vận đơn **1/1PASS,35giây**, không sửa test/timeout/worker cho ca này. Đây là targeted rechecks, chưa thay full suite. Xem trực quan thêm chart768/history1366/evidence1920/table390/Settings nâng cao1440: không thấy khung chồng, modal clipping hoặc lệch composer; bảng rộng vẫn cuộn ngang trong vùng riêng.

Đối chiếu `job_attempts` đúng cửa sổ failure cho thấy worker đang lần lượt parse hai tệp:18:12:26,175→33,566UTC (7,390giây),18:12:34,010→42,111UTC (8,101giây), rồi Agent42,190→43,313UTC. Cả baSUCCEEDED, không retry/error/lease expiry. Đây là thời gian chờ sau hai parse jobs trong worker tuần tự hiện có, không job bị mất hoặc deadlock. Không đổi concurrency/worker architecture, bỏ queue gates hoặc nới assertion để che failure; không cam kết SLA15giây trên host dùng chung. Receipt chỉ chứa loại job/timestamps/status, không payload.

Gate source chốt: **117/117PlaywrightPASS,0FAIL/SKIP/retry,13,0phút** trên dist cố định sau sửa focus, cùng API thật; `full-candidate-accepted.log`. Toàn bộ11UAT cases gồm1000giao dịch, Decimal oracle, hai exports/reloadPASS; C Gộp vận đơn18,6giâyPASS cả hành trình. Mock contract và native/manual fallback được phân biệt theo tên case;0inference mới. Không cộng15+1rechecks vào117cases độc lập.

Sau deploy **8/8checksPASS,2,7phút** trên assets Nginx thật, không cờ dist candidate:5composer/Settings,1Planner mock contract,1native CSV/XLSX journey và1UAT1000. Persistence trước/sau chỉ recreate frontend khớp toàn bộ20bảng nghiệp vụ/23nhóm metadata+artifact hashes:295projects/655datasets/1.190mappings/519canonicals/242runs/432exports/638conversations/1.336messages/402workflows;2.359artifact files/242run files/432exports. Đây là so original IDs/full row digests/file hashes, không chỉ counts. Local proof và4serviceshealthyPASS.

Backup trước nhiệm vụ `backup_48ed66d5c7c249afa3cd8b596c7dbbea`:24tables/2.709files, metadata SHA256 `3dbd965ffc1f37ee5e817e39e63090ed771657a7932477993e100d45c510fce3`. Backup28,579giây/restore19,776giây trong UUID schemaPASS, corruption/path-traversal từ chối đúng, public không overwrite; host copy kiểm độc lập toàn bộ checksumsPASS. So toàn bộ original primary keys/full metadata và2.709file hashes sau candidate:0missing/0changed/0checksumfail, không ngoại lệ policy. Các project TEST mới được phép bổ sung. Không inference mới/tăng quota/reset ledger;203/210 còn7 tại baseline và các browser audits.

### D. Docker cleanup

Inventory baseline57uniqueimages/10Studio-owned; sau build frontend58/11, sau cleanup **50/3**. Có31containers gồm4Studio,36volumes gồm2Studio. Đã xóa chính xác8manifest IDs dưới đây bằng `docker image rm <ID>`, không force. Mỗi ID có OCI source chính thức, revision là ancestor của main, chỉ accepted tagsStudio, không container nào tham chiếu kể cả stopped; kiểm lại refs ngay trước từng lần xóa. Source/deploy8checks đãPASS trước cleanup.

| Bộ cũ | Frontend image ID đã xóa | Backend image ID đã xóa |
| --- | --- | --- |
| 34c0ff1 | `b1a4d9e2151c3c68dd98edfa31c8913709d7480bc6f7f1dd6948124fc1bfb349` | `e2b5cabd53cec8ca519c51b3d07abeb6e5ec1973db71f860a28664b5a04edfac` |
| d392c4a | `484acae401f9c6ecfcfde3c983fee8e7ac2dc6a50f99df6ae3eb2d03810bd935` | `2260ad5ee96d75a1cdb8db8fe76a56ba5f56dea041a12e87b302c156e12fe902` |
| f1ad9f1 | `73c6716d779626de3ee852ab3e6eaced98957ba5fb3a6e038b88d05975ba3028` | `f70deb47f560e1a41d33f35051ea16afed697c78586ecebc8bd1d4e1415cba49` |
| 5f358c4 | `1049ba4457ebad8971d0be29cb523b7429714fb2c3dc1abcd28a9ef1a40ab215` | `7a00801051416c143e0d0199919bb9a43fa319a01fd01b1a8010b1d5d8781e29` |

Giữ frontend18706a7/current tag, frontendDAC rollback và BackendDAC dùng chung current/rollback (full IDs ởA); tags`accepted-main-18706a7`/`accepted-main-dac8dd1` không tag đè. PG hiện hành giữ `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7`. DAC đã là runtime ổn định ngay trước phát hành, cùng schema/Backend bytes; không chạy rollback drill mới hoặc giả nhận đã restore production. `rollback.ps1` mặc địnhDAC, syntaxPASS và giữ compatibility/active-job guards.

`cleanup-verification.json` chứng minh toàn bộ47image ngoàiStudio (IDs/tags/digests),31containers (IDs/image refs/health/restarts/mounts) và36volumes (name/driver/creation/ownership) **không đổi trong bước cleanupStudio**. Hai volumes `ai-reconciliation-studio_postgres_data`/`ai-reconciliation-studio_artifacts`, backups/raw/canonical/runs/exports/conversations/workflows/audit/ledger giữ nguyên. Không có stopped Studio container dư để xóa; không xóa container hoặc volume.

`docker system df`: Images38,91→38,90GB, giảm xấp xỉ0,01GB ở độ chính xác hiển thị; reclaimable13,87→13,86GB. Build cache490entries/38,51GB không bị dọn (reclaimable classification12,54→12,55GB). Không cộng virtual image sizes để báo giải phóng vật lý, không xác minh VHDX thu nhỏ. Volumes9,737→9,754GB do dữ liệu/hoạt động hiện hành,36volumes vẫn nguyên; không dùng prune/cache cleanup để ép con số giảm lớn hơn. Receipts inventory/plan/deletion outputs lưu tại `runtime/minimal-interface/` ngoài Git.

### E. GitHub và release

Feature `codex/minimal-interface` trong repository chính đã commit/push rồi fast-forward main/origin tại source `18706a7864871bfeddd65570c88348676ceb5bba`. Runtime mới được build sau commit sạch và chỉ recreate frontend; identity/persistence/postdeploy gates ở phầnA/C. Các commit báo cáo sau mốc này chỉ tài liệu; phải kiểm application diff rỗng, không dùng docsHEAD để giả nhận Backend image đã rebuild.

Source repository hiện không có `.github/workflows`; các gates nêu ở đây chạy local/Docker/Chromium, không báo CI remotePASS hoặc tự thêm pipeline ngoài phạm vi. Sau cleanup Backend302/302PASS,0FAIL/SKIP,116,39giây; browser runtime đầy đủ117/117PASS,0FAIL/SKIP/retry,14,8phút. Các logs trước bịFAIL vẫn được giữ riêng, không sửa timeout/retries/oracles.

### F. Trạng thái nghiệm thu

**READY_FOR_GUIDED_DEMO**, trong phạm vi local CSV/XLSX đã nghiệm thu. Giao diện mới, runtime thật và gates sau cleanup đềuPASS:

| Gate cuối | Kết quả |
| --- | --- |
| Backend/PostgreSQL | 302/302PASS,116,39giây;0FAIL/SKIP |
| Full browser runtime | 117/117PASS,14,8phút;0FAIL/SKIP/retry, gồm11UAT cases/1000giao dịch/CSV/XLSX/reload |
| Source/runtime sau cleanup | 42Backend files và7HTML/assets khớp source/image/HTTP;5resources Chromium cache disabled khớp,0serviceworkers/pageerrors |
| CSS/ảnh production | 5widths390/768/1366/1440/1920, pointer khôngborder/outline, Tab cóinsetfocus; screenshots thật và matrix/layout/settings/native tại`after/` |
| Tài chính | 966EQUAL/19AMOUNT_MISMATCH/15UNMATCHED, absolute variance7,03VND; independent checks và hai exports khớp snapshot |
| Original data sau toàn bộ tests/cleanup | Mọi primary key/full metadata24bảng và2.709file hashes so backup trước:0missing/changed/checksumfail; không ngoại lệ policy |
| Health/queue/ledger | 4/4healthy,0restart/OOM;`/`, `/health`, `/api/live`, `/api/ready`, `/api/session`HTTP200;0activejobs;Gemini203/210 còn7,0inference mới |
| Logs | 0ERROR/traceback matches trong Backend/Worker10phút cuối; không dùng thống kê này thay functional gates |

Hiện có312projects/691datasets/551canonicals/257runs/461exports/665conversations/417workflows sau các native tests, tăng do project TEST hợp lệ. Không dùng counts để thay chứng minh full row/hash preservation. Hai volumes và tất cả backups còn nguyên; backup trước nhiệm vụ đã restore UUID và kiểm host copy, không mới restore production hoặc off-host drill.

Đã sửa race focus thực tế và thiết kế composer/card/focus tại nguồn; không còn regression đã biết làm hỏng các hành trình trong phạm vi nghiệm thu. Độ trễ queue phụ thuộc hai parse jobs và tải host, không có SLA15giây; các gates còn thiếu semantic/currency/coverage/permission vẫn chặn/hỏi lại đúng hợp đồng. Giới hạn LIVE/model accuracy/physical keyboard/screen-reader/nhiều người dùng/soak/off-host restore ở mụcY vẫn áp dụng; kiểm CSS không mở rộng bằng chứng AI hoặc chứng minh phần mềm không thể có lỗi. Không gọi production-ready hoặc đổi allowance7lượt thành khả năng dùng cloud không giới hạn.

## AA. Sửa Markdown và môi trường VS Code — 04/11/2026

Phạm vi là tài liệu, cấu hình editor và profiles cá nhân. Không đổi source ứng dụng, contracts, dependencies/lockfiles, AI policy hoặc Docker runtime đã nghiệm thu ở mục Z.

Markdownlint extension 0.62.1/engine 0.41.1/CLI2 0.23.2 tái hiện đúng **398 cảnh báo** trong IMPLEMENTATION_STATUS và **781 cảnh báo trên 9/11 tài liệu**: 680 MD060, 32 MD034, 15 MD012, 6 MD036, 12 MD025, 4 MD024, 16 MD033 và 16 MD022. Sửa khoảng trắng bảng/blank lines/URL, dùng headings thật cho các Journey và kết luận lịch sử; PROJECT_PLAN có một H1, các phần La Mã và headings con được lồng đúng cấp. Không sửa nội dung nghiệp vụ hoặc số liệu lịch sử. So toàn bộ nội dung sau chuẩn hóa markup và fenced examples với Git trước sửa PASS, trước khi thêm ghi chú nhiệm vụ này.

Một cấu hình `.markdownlint-cli2.jsonc` dùng chung CLI/editor: MD013 OFF giống mặc định extension; MD024 chỉ chặn headings trùng trong cùng sections; MD033 chỉ cho phép `<a>` phục vụ navigation anchors; MD060 compact vẫn bật. Không tắt lint hoặc các quy tắc trong screenshot. Kết quả **11/11 tài liệu, 0 issues**; VS Code status bar đọc được **No Problems**. Markdown có formatter mặc định và fix-on-save explicit; không bật auto-format source toàn dự án.

Nguyên nhân prompt venv trùng là hook `Sync-StudioProjectVenv` của hai profile PowerShell đã kích hoạt trước, rồi Python Environments gửi lệnh Activate.ps1 tiếp. Tái hiện trong cả Windows PowerShell và PowerShell 7: trước sửa, profile có một prefix rồi extension activation thành hai. Profiles cá nhân nay bỏ qua hook khi `TERM_PROGRAM=vscode`; extension giữ vai trò kích hoạt trong IDE. Tắt `python.terminal.activateEnvInCurrentTerminal` ở user/workspace để không tự kích hoạt lại terminal đang mở; bỏ `python-envs.terminal.autoActivationType` sai scope trong workspace, giữ giá trị user `command`. Ngoài IDE, hook vào/ra thư mục tiếp tục hoạt động.

Sáu checks trên hai shells PASS: mỗi shell tái hiện baseline, kiểm sau sửa kích hoạt lần đầu/lặp lại đều một prefix và interpreter đúng `.venv/Scripts/python.exe`, kiểm vào subdirectory/rời project có một/không prefix tương ứng. Đây là subprocess/profile tests; terminal VS Code mở từ trước vẫn giữ function/prompt cũ và báo environment stale, phải mở terminal mới để dùng cấu hình mới. Không nhận là đã đóng hoặc sửa bộ nhớ của các phiên terminal đang mở của operator.

Inventory VS Code 1.144.1: **36 extensions trước sửa khớp danh sách installed trong Settings Sync còn lưu**, không có extension installed nào trong snapshot bị thiếu. Kiểm manifests/entrypoints của extensions người dùng và manifests của **95 built-in extensions** PASS; TypeScript/JavaScript, Markdown preview, JSON, HTML/CSS, Git/npm có sẵn. Bổ sung đúng extension **ESLint 3.0.34** từ publisher chính thức, tổng CLI hiện 37; dùng thư mục `frontend` và dependency/config sẵn có. Không tự cài bộ extensions lớn hoặc coi mọi packages VS Code cần cài lại sau mất AppData. Snapshot còn lưu không chứng minh mọi tùy chỉnh có trước ngày xóa AppData đã được khôi phục đầy đủ.

`.vscode/extensions.json` ghi mười recommendations phù hợp dự án. Settings/profiles/danh sách extensions trước sửa được sao lưu ngoài Git, pointer tại `runtime/vscode-repair/backup-pointer.json`; profiles cá nhân và user settings không commit. `uv sync --locked --check` xác nhận 51 packages không cần thay đổi; `uv pip check`, frontend dependency tree, TypeScript, ESLint và repository/secrets/Markdown paths PASS. Không cần chạy lại financial/E2E hoặc build Docker cho thay đổi tài liệu/editor khi application diff rỗng.

Nguồn đã đối chiếu: [Python Environments](https://code.visualstudio.com/docs/python/environments), [Settings Sync](https://code.visualstudio.com/docs/configure/settings-sync), [CLI VS Code](https://code.visualstudio.com/docs/configure/command-line), [ESLint extension](https://marketplace.visualstudio.com/items?itemName=dbaeumer.vscode-eslint) và README/schema của các extensions đang cài. Các receipts ở `runtime/vscode-repair/`, ngoài Git.

## AB. Khôi phục phiên local và Cài đặt dành cho người dùng — 04/11/2026

**READY_FOR_LOCAL_TEST — nghiệm thu trên Docker thật sau recreate, re-verification và cleanup.** Source ứng dụng `a7c1e8bebec34db5eeb14b0e606df8bb117f6635`, Backend/Worker giữ `dac8dd179fe9cd57bf5e86abae8d4784103c0d6b`. Phần này bổ sung mốc Z/AA và chỉ dẫn Cài đặt mới; không thay nghiệp vụ hoặc policy AI.

### A. Nguyên nhân kết nối và trình tự khôi phục

Frontend vẫn trả200, Backend live/ready200 và đủ4services healthy nhưng session403 `LOCAL_DEMO_NOT_VERIFIED`; API dữ liệu anonymous401. Windows khởi động lại lúc **10:10:07**, Docker backend processes lúc10:10:58, container Backend lúc10:11:46 và nonce mới ghi10:11:53 ngày04/11, giờ Việt Nam. IDs/images trước sửa trùng bản nghiệm thu trước; đây là restart sau reboot, không phải các container đã bị thay nhầm. Lúc kiểm tra, proof không tồn tại trong tmpfs. `startup.py` tạo nonce mới/xóa proof theo thiết kế; session cũ trong DB vẫn bị kiểm lại proof. Không có bằng chứng Langfuse rename gây lỗi và Studio không có phụ thuộc vận hành vào Langfuse. Docker events hữu hạn không đủ xác định ai đã bấm restart; không suy đoán lệnh của operator.

`./tools/start.ps1 -SkipBuild` khôi phục thành công trên bốn containers đang có, không reset DB/cookie/role. Khoảng trống vận hành trước sửa: verify chỉ chứng minh published ports/proof, chưa kiểm xuyên Nginx tới session/settings. Docker tự khởi động healthy sau reboot không thay thế bước xác minh host.

### B. Sửa đổi và hợp đồng được bảo toàn

- `tools/start.ps1`: `-SkipBuild` dùng `--no-build`; giữ một Compose project, `.env` hiện có và exit-on-failure.
- `tools/verify-local.ps1`: đủ4services healthy, host proof, Frontend HTTP identity, root/live/ready/session/settings/projects cùng cookie; xác minh actor/workspace/role, cookie HttpOnly/path; so lại IDs/StartedAt/health trước khi báo success. Startup process với session403 mô phỏng trả exit1 và không in success; script thật chạy được trên Windows PowerShell và PowerShell7.
- `frontend/src/App.tsx`: bootstrap có tổng thời hạn30giây và abort khi unmount/retry; phân biệt proof local với offline, kết thúc loading và trạng thái xác minh quyền; retry chỉ GET, không reload trang hoặc phát lại mutation. Giữ draft và history. Hướng dẫn operator chỉ nằm trong disclosure ở lỗi proof.
- `WorkspaceSettings.tsx`: bỏ hoàn toàn **Thông tin nâng cao**, kể cả owner. Ba phần dành cho người dùng: tài khoản/quyền, AI/quyền riêng tư, giới hạn tệp. Không trình bày provider/model, cấu hình/kết nối kiểm thử, bộ đếm ledger hoặc phân bổ từng task. Trạng thái AI dùng DTO/quyền/hạn mức thật, không nhận cấu hình là kết nối đã kiểm chứng. Không thêm nút cài đặt giả.
- `styles.css`: màu trạng thái kết nối đúng và bỏ selector của phần nâng cao đã xóa. Các tests hiện có được cập nhật theo yêu cầu Cài đặt mới; thêm regression proof/bootstrap, giữ mọi ca cũ.
- README, ARCHITECTURE, PROJECT_PLAN, TESTING_GUIDE và báo cáo này ghi quy trình/ủy quyền mới. Yêu cầu owner xem thông tin vận hành ngày02/11 được thay rõ bằng chỉ dẫn04/11, không sửa lịch sử nghiệm thu.

Không thay source Backend/auth/session policy, CSRF, Host/Origin, workspace permissions, TTL, Decimal, engine/verifier, migrations, model/key, quota hoặc `.env`. Không mount Docker socket, tự bật proof từ HTTP/browser, xóa session hoặc tự đổi role. Chỉ build Frontend mới; Backend/Worker có42source hashes khớp code hiện hành.

### C. Kết nối và trình duyệt sau recreate

Recreate Frontend lúc11:09:04 và Backend lúc11:09:41; trước mỗi lần re-verification, session bị chặn403 đúng. Lệnh startup chính thức sau thao tác cuối đã đạt session200 `workspace=demo / actor=demo-owner / role=owner`, settings200. Cookie cũ được giữ qua recreate Backend, draft giữ qua reload, Lịch sử/Cài đặt/Assistant mở được; không mutation hoặc uncaught page error trong recovery drill. Snapshot metadata và toàn bộ artifact bytes không đổi qua cả hai lần recreate.

Cài đặt thật đã kiểm ở390/768/1366/1440/1920px: ba nhóm nội dung, không tràn ngang, không có thông tin vận hành cho owner; keyboard mở phần giải thích quyền riêng tư. Mock kiểm thêm owner/editor/viewer và các trạng thái quyền/cấu hình/hết lượt tổng hoặc từng tác vụ. Không gửi request ghi để mở Cài đặt. Receipts/screenshots ở `runtime/session-recovery/`, ngoài Git.

### D. Docker và source/runtime

| Service | Container ID (rút gọn) | Source revision |
| --- | --- | --- |
| Frontend | `d2f2c30e85a9` | `a7c1e8b` |
| Backend | `2650558bff90` | `dac8dd1` |
| Worker | `fede0f52b473` | `dac8dd1` |
| PostgreSQL | `22fa413d2693` | PostgreSQL18.3, image giữ nguyên |

Image Frontend: `sha256:d07d753c4f7490e768e465719eac2b3864d70caf226c4d8a0db2ca1f3c303eff`; Backend/Worker: `sha256:798c2afbe2f11a3c0583bbb2e024cee5c205729eb388022ad0ac3d23b29f615e`; PostgreSQL: `sha256:54451ecb8ab38c24c3ec123f2fd501303a3a1856a5c66e98cecf2460d5e1e9d7`. Bảy HTML/assets host build=image=HTTP; năm tài nguyên Chromium tải khớp cả ba, không service worker. Hai component khác revision là có chủ đích, không phải runtime drift; commit tài liệu sau đó không phải image revision.

Bốn services healthy, RestartCount0/OOMfalse; Worker/PostgreSQL không recreate trong vòng này. Chỉ publish Studio127.0.0.1:18180. Hai volumes giữ nguyên `ai-reconciliation-studio_postgres_data` và `ai-reconciliation-studio_artifacts`.

Langfuse được kiểm chỉ đọc:6/6healthy, RestartCount0/OOMfalse, UI/health/ready200 và API đọc quan sát cũ200. Không restart/build/deploy/đổi credentials hoặc dữ liệu Langfuse. Giữ nguyên5volumes, networks và các backup trước; tên storage còn prefix cũ là external refs được bảo toàn. Ports3000/9090 vẫn loopback, không phụ thuộc vào phiên Studio. Cửa sổ log10phút của6services không có ERROR hoặc socket timeout; hai networks external vẫn là `shopquery-observability_default` và `shopquery-observability_ingestion`.

Dọn Docker sau121/121PASS: gỡ image Frontend18706a7 `sha256:d04074feee418e6e8ae0cadb762b15fbea32aec5c6e673fe24710924fd603d53` sau xác minh không container nào tham chiếu; bỏ tag candidate, giữ local/accepted-main-a7c1e8b. Studio còn đúng3images: Frontend hiện hành, Frontend rollbackDAC, Backend hiện hành/rollbackDAC dùng chung; PostgreSQL giữ nguyên. Không container Studio thừa. IDs/images của mọi container dự án khác và toàn bộ36volumes trước đó được giữ nguyên; không global prune. Docker host hiện50images/31containers, image size38,9GB, volumes9,3GB; phần reclaimable toàn host gồm dự án khác nên không coi là tài nguyên được phép xóa. Cặp rollback và mọi backup vẫn tồn tại.

### E. Kiểm thử và bảo toàn dữ liệu

- Backend/PostgreSQL đầy đủ: **312 PASS/139,63giây**, gồm10ca bổ sung so với302; PostgreSQL tests dùng UUID schema cô lập trong server hiện có. Một warning deprecation từ thư viện TestClient, không có test failure. Ruff/mypy47source files, TypeScript/ESLint/build, repository/secrets/paths và Markdown11tài liệu đạt.
- Candidate trước chỉ dẫn Cài đặt mới:120/121PASS; một ca late-report chờ request không chắc phát sinh khi run đã cache. Sửa thiết lập chọn run khác và đợi route callbacks kết thúc; không bỏ test/tăng timeout/đổi expected data. Vòng tập trung sau sửa Cài đặt và fixture: **13/13PASS**. Không cộng replay vào catalogue.
- Playwright toàn bộ trên assets Docker sau recreate: vòng đầu119PASS/2FAIL khi kiểm tra bổ sung của Codex giả lập Docker sai, làm activation nhận stdin rỗng và thu hồi proof. Đây là nhiễu từ test harness chạy xen, không phải thay source ứng dụng; đã sửa harness, kiểm startup403/exit1 và khôi phục bằng verifier chính thức. **Vòng chạy lại không gián đoạn:121/121PASS trong12,8phút**, không xen thao tác proof. Sau cleanup thêm **8/8smoke PASS/43giây**, gồm bootstrap/proof/network/settings, CSRF/Host, landing và journey CSV/XLSX thật; không cộng replay vào catalogue. Cả11journeys dữ liệu tổng hợp, bộ1000 và ca tệp hỏng/quá dung lượng đã qua trong full run; CSV/XLSX được so với Snapshot JSON và oracle độc lập.
- LOCAL thật: hai lần recreate/proof403/reverify200, cookie/draft/reload/History/Settings; negative verification403 có kiểm soát. MOCK: các trạng thái proof, mạng, timeout/settings, deadline, quyền và UI retry không mutation.
- Demo hiện có **DEMO UAT1000** đúng run cũ:966EQUAL,19AMOUNT_MISMATCH,15UNMATCHED, absolute7,03VND. LOCAL typed query dùng intent đã kiểm để lấy top3/19 và evidence đúng group thứ hai; query UNPAID trả200giao dịch. CACHED browser mở hội thoại/biểu đồ1000 =686PAID +200UNPAID +114COMPLETED, evidence và tải XLSX có Snapshot JSON đúng/không formulas; reload giữ kết quả. Không nhận là fresh NLP inference.
- Backup/restore trước sửa:24bảng, metadata SHA256 `3bc297745a03b4419a6fb9f759d7260e39f18b5ce3985c088d0980682959318a`; restore UUID schema PASS, checksum corruption/path traversal bị chặn, production unchanged. Host copy195.103.109bytes/3.216files đã kiểm metadata và **3.214artifact checksums**. Backup giữ trên volume và host; không nhận là off-host backup.
- Đối chiếu bản ghi gốc24bảng và3.214files trước deploy:0missing/0changed/0file failures; bài kiểm tra chỉ thêm dữ liệu tổng hợp, không đổi bản ghi gốc. Đối chiếu lại sau toàn bộ tests/cleanup vẫn0missing/0changed/0file failures trên bản gốc; kiểm thêm toàn bộ metadata và checksum artifacts/results/exports hiện có cũng PASS. Số lượng tăng chỉ do bài kiểm tra tổng hợp và các phiên mới, không thay bản ghi gốc.
- Gemini ledger **203/210, còn7** trước/sau recovery, Settings và demo readback; không inference mới, tăng hoặc reset quota. Traces từ các bài LOCAL/MANUAL không được nhận là cloud calls.

### F. GitHub

Source `a7c1e8b` đã commit/push lên `origin/codex/local-session-recovery` của repository chính thức; các quality gates đạt trước khi tích hợp. Bàn giao dùng fast-forward main gồm source và commit báo cáo, xác minh SHA local/remote rồi dọn đúng nhánh công việc đã tích hợp. SHA main cuối được báo trong kết quả Git bàn giao; image revision tiếp tục là application sourcea7c, không build lại vì commit tài liệu. Không có worktree/repository hoặc Compose project bổ sung; receipts, backup, cookies và runtime data không vào Git.

### G. Điều kiện sử dụng

**READY_FOR_LOCAL_TEST**: root/health/live/ready/session/settings/projects đều200 sau cleanup, đúng demo/demo-owner/owner. Assistant, History, Settings, chart/evidence/XLSX và reload đã được kiểm lại trên browser thật sau cleanup, không uncaught page errors hoặc mutation từ Settings/readback. Phạm vi sẵn sàng là local CSV/XLSX và các luồng đã kiểm; không phải bảo đảm mọi câu tự nhiên hoặc deployment Internet/nhiều người dùng. Sau reboot/Docker/Backend restart hoặc Frontend recreate, dùng `./tools/start.ps1 -SkipBuild` rồi **Thử kết nối lại**; không bỏ bảo mật để tự cấp proof từ browser.

## AC. Hoàn thiện sản phẩm, AI local và nghiệm thu — 04/11/2026

### A. Tình trạng sản phẩm

**Chưa đạt `READY_FOR_FINAL_USER_TEST`: phần nghiệm thu AI còn `BLOCKED_AI_PROVIDER`.** Gemini đã trả HTTP 429 thực tế. Dừng gọi mới, không đổi tài khoản/key/model hoặc tăng quota nội bộ để vượt giới hạn nhà cung cấp. Những cổng local bên dưới được kiểm chứng riêng; không dùng chúng để tuyên bố AI đã hoàn tất.

Giao diện và các luồng dữ liệu local có thể mở để kiểm tra. Bản Docker hiện tại là candidate đã qua kiểm tra local, chưa phát hành lên `main`. Không phát hiện lỗi P0/P1 trong các luồng đã kiểm tra; còn các giới hạn hiểu ngôn ngữ và coverage LIVE chưa đủ, nên không khẳng định phần mềm không còn lỗi. Không nghiệm thu triển khai Internet, nhiều người dùng đồng thời hoặc nghiên cứu người dùng độc lập.

Giữ kiến trúc, Matcher/Verifier, công thức, Decimal, migrations và dependencies. Không tạo service, framework, worktree hoặc môi trường Docker thứ hai. Các mục trước của tài liệu là snapshots lịch sử; trạng thái hiện hành được mô tả trong mục AC này.

### B. Ngôn ngữ và các lỗi đã sửa

| Nguyên nhân | Thay đổi và kiểm chứng |
| --- | --- |
| Trạng thái đọc tệp dễ bị hiểu thành đã chuẩn hóa | Hiển thị “Đã đọc dữ liệu; chưa chuẩn hóa”; dataset READY/PARTIAL, đề xuất và verified được phân biệt. Nút duyệt nói rõ việc lưu ánh xạ và chuẩn hóa, hoặc lưu quy tắc và chạy đối soát. |
| DTO định tuyến làm mất phạm vi người dùng đã nêu | Thêm source facts có kiểu, giữ coverage/snapshot/date/effective dates sang Planner; kiểm canonical IDs và từ chối facts mới mâu thuẫn khi reuse. Missing vẫn null, không nới gates. |
| UTC bị dùng làm ý nghĩa ngày | `time_basis` tách khỏi timezone; yêu cầu mới không được dùng UTC thay ngày phát sinh/hạch toán. Run mới đã kiểm tra dùng `event_date`, UTC riêng. |
| Count kèm tổng lệch toàn run bị dựng lại bằng query | Chuyển sang MetricSnapshot đã verified khi không có filter/group; truy vấn phạm vi con vẫn dùng typed query. Có regression cho cả sum riêng và count kèm sum. |
| AI tự điền currency vào danh sách ngoại lệ | Prompt nhắc fields phải thuộc đúng source; unknown field vẫn bị Backend chặn. Không tự bỏ validation hoặc bịa trường tiền tệ. |
| “Kết quả đang mở” bị hiểu là ngoại lệ OPEN | Prompt phân biệt tổng quan run đang xem với công việc xử lý ngoại lệ; còn phải xác minh nốt các cách nói sau blocker provider. Không tuyên bố đã hết lỗi NLP. |
| Timeout/429 và usage lỗi dễ bị hiểu sai | Không resend read/write timeout hoặc delivery chưa rõ; known connect failure/5xx mới retry có giới hạn và backoff. 429 có mã rate-limit riêng; safe usage của lỗi Assistant được giữ trong trace. |
| Harness trả exit thành công khi provider đã dừng | CLI nay trả exit 2 khi stopped. Launcher phải lưu/kiểm exitcode ngay, trước bước copy receipts. Thiếu/thừa/gộp replies được ghi FAIL cho toàn bộ ca không gán được, giữ mẫu số; ba regression cho số reply 0/1/3 khi yêu cầu 2 đều đạt. |

Files chính: `agent_intents.py`, `contracts/agent.py`, `contracts/reconciliation.py`, `agent_workflows.py`, `assistant.py`, `ai_gateway.py`, `assistant_jobs.py`, `errors.py`; các job handlers/config/repository/API và tests được cập nhật tương ứng. Không sửa raw/canonical hoặc lịch sử để che các lần thử thất bại.

### C. Giao diện và yêu cầu màu trắng mới nhất

Chủ dự án đã yêu cầu giữ **nền trắng**, không dùng nền xanh cho ô chat hoặc ô gửi câu hỏi. Commit `2ab64e0` áp dụng:

- Tin nhắn người dùng, phản hồi trợ lý và composer có nền trắng, viền xám trung tính 1px và bóng nhẹ để tách khỏi nền trang. Hover composer chỉ làm đậm viền; bàn phím vẫn có chỉ báo focus riêng.
- Tin nhắn người dùng căn phải; nội dung/menu dùng grid riêng, không float làm ép chữ. Giữ xuống dòng chủ động, mã có số 0 đầu và chữ tiếng Việt.
- Preview 10 dòng; “Dữ liệu chi tiết” mở toàn bộ trang của cùng query/result, không gọi AI hoặc fetch lại chỉ vì mở. Pagination/sort/evidence giữ nguồn và trang đang xem.
- Kết quả count lấy giá trị Backend, kể cả 0; không nhầm một dòng tổng hợp là một giao dịch. Số dòng đầu vào, tổng nhóm và trang hiện tại được tách rõ.
- Decimal được định dạng bằng chuỗi, không qua float; chỉ áp dụng với trường có kiểu. NULL khác 0; giá trị nguồn/evidence giữ nguyên để truy vết.
- Settings chỉ có thông tin sử dụng, quyền và riêng tư; không có panel provider/model/ledger/kiểm thử nâng cao.

Sau khi chốt màu trắng, chủ dự án yêu cầu chữ lớn hơn. Commit `e9867ab` tăng chữ câu hỏi/phản hồi lên 16px, bảng và thao tác trong chat lên 14px. Ô nhập vốn kế thừa 12px từ label toàn cục, nay được kế thừa đúng 16px từ composer; giữ chiều cao một dòng và không che nút gửi. Bảng chi tiết cũng dùng 14px.

TypeScript, ESLint và production build đạt. Trước deploy: 11 ca viền trắng đạt trong 32,8 giây; sau sửa cỡ chữ, 16 ca liên quan đạt trong 2,0 phút trên 5 viewport: 390/768/1366/1440/1920. Ảnh hội thoại thật `after/white-chat-*.png`, `white-answer-*.png` và receipt `white-surfaces.json` nằm trong `runtime/product-polish` tại máy nghiệm thu. Đã xác minh cả ba bề mặt là trắng, có viền và bóng, không tràn ngang; ledger không tăng khi kiểm màu.

Ảnh baseline của release a7c1e8b còn tại `runtime/session-recovery/after`. Bộ chụp “before” đầu đợt này dừng vì local proof đã hết hiệu lực sau restart; không trình bày bộ chụp thất bại đó là baseline thành công. Ảnh sau và hashes được chụp lại trên chính assets Docker hiện tại.

#### Thu gọn công cụ theo yêu cầu tiếp theo

Commit `7157f6a` gộp chọn dự án và các thao tác vào một thanh cao tối đa 40px. Tệp đã tải, chọn ngữ cảnh và hội thoại mới dùng nút biểu tượng có tên truy cập/title; chính sách/chế độ, thiết lập thủ công và xóa hội thoại nằm trong menu ba chấm. Escape đóng và trả focus về nút mở; bấm ra ngoài đóng menu. Menu nổi và cuộn nội bộ, không làm co/đẩy transcript. Project picker vẫn tìm kiếm/chọn/phân loại theo cùng quyền, không tạo nguồn “latest” mới hoặc bỏ kiểm tra scope/run.

Giảm topbar/khoảng trống và tăng bề ngang đọc desktop tối đa 1.120px. Đo cùng hội thoại ở 1.440px: vùng đọc rộng 920→1.120px, bắt đầu y179,5→114px, thêm 65,5px chiều cao đọc; ở 1.366px rộng 920→1.064px. Mobile 390px vẫn rộng 358px, bắt đầu y174→112px. Không thay sidebar của các trang khác; giữ chữ 16px, bảng 14px và nền trắng đã duyệt.

Mười ca bố cục gồm 23 trạng thái và đọc bảng ở 5 viewport đạt trong 1,6 phút trên candidate. Đã kiểm menu không đổi bounding box transcript, nằm trong viewport, Escape/focus, bấm ra ngoài, không tràn ngang và mở đúng dữ liệu. Một lượt candidate trước đó có navigation ERR_ABORTED khi build assets đang thay; giữ log và chạy lại trên dist ổn định, không gọi đó là lỗi nghiệp vụ hoặc bỏ ca. `compact-before.json`, `compact-after.json`, screenshots `compact-after/chat-*.png` và `options-*.png` giữ bằng chứng thực tế trên máy nghiệm thu.

### D. Nghiệp vụ, hành trình và bảo toàn dữ liệu

| Hành trình | Bằng chứng |
| --- | --- |
| A — Tải và đọc tệp | Browser thật tải CSV/XLSX tổng hợp, giữ bytes/hash và báo trạng thái đọc; full UAT kiểm tệp hỏng/quá dung lượng, multi-sheet và dòng nguồn. |
| B — Chuẩn hóa | LIVE đề xuất mapping, người kiểm thử duyệt 2 nguồn rồi chuẩn hóa 5+5 dòng. Có kiểm mã 0 đầu, số âm/0, locale và COMPLETED khác PAID. Không tự duyệt. |
| C — Đối soát | LIVE tạo đề xuất; xác nhận completeness còn thiếu bằng UI, duyệt quy tắc rồi Matcher và Verifier chạy. Run `be230b6f-d0b3-4246-9b76-7f83564ef63d`: 3 EQUAL, 1 AMOUNT_MISMATCH, 2 UNMATCHED; signed/absolute variance 0.50 VND, đúng oracle tính tay. |
| D — Tra cứu/phân tích | LIVE count lệch, top 1, hỏi tiếp theo vị trí, UNPAID riêng, chart đủ 5 dòng và thiếu đối ứng. G 1000 được đọc lại bằng typed query: top 3 trong 19 nhóm lệch, evidence đúng dòng thứ hai; chart 686 PAID + 200 UNPAID + 114 COMPLETED. |
| E — Xuất/khôi phục | Tải XLSX thật qua browser và đọc lại đúng run/snapshot; CSV/XLSX của UAT so với oracle, không có formula injection. Reload, History, Settings, draft/cookie và recreate đều được kiểm riêng. |

Giữ nguyên 11 tình huống, 24 tệp, 2.131 dòng UAT: đơn hàng/thanh toán, thu chia kỳ, chi gộp ngân hàng, ngày ghi sổ, khóa composite vận đơn, nhiều lần xử lý, gộp vận đơn, cấu trúc khác, không tương thích, biên/bảo mật và 1.000 giao dịch. G 1000: **966 khớp / 19 lệch tiền / 15 thiếu đối ứng / 7.03 VND**. Kết quả đọc lại run cũ là LOCAL/CACHED, không phải inference mới.

Run tổng hợp trước dùng `time_basis=UTC` được giữ là lịch sử chẩn đoán; run mới dùng `event_date`, timezone UTC riêng. Model có thể để completeness null dù câu tự nhiên đã nói đầy đủ; UI buộc xác nhận, không tự điền để chạy.

Backup trước đổi policy: `backup_d66ade0c9753404ea12dc99938051927`, 24 bảng; metadata SHA256 `9f56d8058d7c64757b68acd48acb973827d0fd786e2f84234d1e4d25d4393e0a`. Backup 21,971 giây, restore UUID schema trong cùng PostgreSQL 16,231 giây đạt; phát hiện checksum hỏng và chặn path traversal, không overwrite public. Bản sao host đã kiểm metadata và 3.712 tệp theo manifest. Đây vẫn là backup cùng máy, chưa phải phục hồi thảm họa ngoài máy.

So nguyên PK/full rows của 24 bảng gốc và checksum mọi tệp cũ: không mất/đổi dữ liệu; chỉ một thay đổi được cấp quyền là demo policy.external_request_budget từ 210 thành null. Giữ nguyên 203 reservations gốc. Snapshot/verify khi recreate kiểm 20 bảng nghiệp vụ và 3 nhóm artifact/run/export, không chỉ counts; HttpOnly/SameSite Strict cookie và draft được giữ. Trước/sau deploy màu trắng cũng kiểm lại toàn bộ metadata/artifact hiện tại và đạt.

### E. AI không còn trần nội bộ, nhưng còn giới hạn provider

Global, Agent, Planner, Assistant và workspace demo dùng `unlimited` → typed null, không số cực lớn và không reset usage. Chỉ cấu hình unlimited trong local demo được cấp quyền; default cài mới vẫn cloud OFF/0. Null không cấp permission/key. `.env` và policy có backup riêng ngoài Git cùng audit thay đổi. LlamaParse giữ nguyên request/credit/SHA allowance; không mở parser cloud mới.

Giữ reservation lock, quyền cloud, privacy, idempotency, timeout, giới hạn của workflow/model/tool/payload, backoff và stop khi unknown delivery. Provider 429 không được coi là cần tăng quota nội bộ. Không đổi Gemini mặc định, key hoặc account; Knowledge không bị dùng để vượt blocker Gemini.

| Phép đo | Intent | Nguồn | Slots | Dispatch | Abstention | Giới hạn |
| --- | --- | --- | --- | --- | --- | --- |
| Routing 30, 80 gold LIVE theo lô | 79/80 | 60/60 | 34/34 | 80/80 | 20/20 | N08 hỏi lại thay vì UNSUPPORTED; không tính EBITDA |
| Routing 30, 24 variants đo đủ | 23/24 | 15/16 | 10/10 | 23/24 | 8/8 | Giữ V16 sai; một batch gộp 2 câu bị chặn, các ca còn lại được đo riêng, không bỏ failure |
| Routing 31, 80 gold observed | 79/80 | 59/60 | 33/34 | 79/80 | 20/20 | Một batch bị chặn; chỉ chấm từng response đã biết HTTP200/STOP. L14 đảo PAID/UNPAID bị guard chặn, không thực thi |
| Routing 31, 24 variants theo lô | Chưa đủ | Chưa đủ | Chưa đủ | Chưa đủ | Chưa đủ | Có trộn/gộp câu; không lấy kết quả revision cũ thay revision mới |
| Routing 31, 1 goal/request, gold | 26/26 đã đo | 26/26 | 15/15 | 26/26 | Chưa đo | D27 nhận 429; 54 ca chưa validated |
| Routing 31, 1 goal/request, variants | 15/15 đã đo | 11/11 | 7/7 | 15/15 | 4/4 | V12 nhận 429; 9 ca chưa validated |

Một goal/request khớp cách Chat gửi yêu cầu. Giữ nguyên 104 ca gốc: **41 ca đo đơn đã validated, 63 ca còn thiếu**, gồm 2 ca bị 429 và 61 ca chưa gửi theo phép đo một goal/request. Không báo 104/104. IDs và receipts tại `runtime/product-polish/provider-blocker-pending.json`; V16 chưa được chốt lại bằng phép đo đơn. Benchmark chỉ đo router, không chứng minh 80/24 workflow đã thực thi, không phải accuracy tổng quát.

Các revisions 28–29 và failure cũ vẫn còn receipts: gold 28 intent 78/80, variants 28 intent 23/24; gold 29 dừng vì unknown field, variants 29 đạt 24/24 trong một lượt. Không xóa hoặc sửa expected output để tăng tỷ lệ.

Ledger Gemini **203 → 311**, thêm **108 HTTP attempts: 106 HTTP200 và 2 HTTP429**. Token đo được: prompt 1.617.148, output 48.860, total 1.666.008; cached content 15.042 thuộc usage, không tự trừ thành hóa đơn. Latency 108 receipts/trace: p50 4.140ms, p95 7.396ms, không phải latency toàn hành trình. 103 attempts có receipt từng lần; 5 lần đầu chỉ có receipt tổng của một call. Những trace Assistant xác định không gọi HTTP được tách riêng. **Chi phí hóa đơn NOT VERIFIED.**

D27 chạm 429 trước; harness lúc đó trả exit 0 khiến launcher tiếp tục variants thêm 16 attempts trước 429 ở V12. Đây là lỗi orchestration của Codex, không phải Gateway tự retry D27. CLI đã sửa exit 2 và evaluator giữ các ca lỗi trong mẫu số. Không gọi provider tiếp để retest 429. Chưa đủ bằng chứng xác định đây là quota ngày, RPM hay token quota. Sau khi điều kiện provider được khôi phục mới đo nốt với attempt IDs mới có audit; không overwrite failure hoặc resend delivery chưa rõ.

Knowledge: `/models` HTTP200, model `knowledge` có mặt; mapping tổng hợp LIVE qua JSON/semantic validators, 2 decisions PROPOSED, không tự duyệt. Có 2 HTTP attempts; receipt cũ chỉ giữ token lần cuối: prompt 2.497, output 1.390, total 3.887, trong đó reasoning 1.048 đã nằm trong output. Tổng token của cả 2 attempts và latency Knowledge chưa đo; billed cost NOT VERIFIED. Không coi đây là đã nghiệm thu mọi workflow Knowledge.

### F. Kiểm chứng và gates

Backend/PostgreSQL đầy đủ **337 PASS / 82,01 giây**, tăng 25 ca so baseline 312: 22 ca cho runtime và 3 ca cho harness. Một deprecation warning từ Starlette TestClient/httpx; không có test failure. Ruff đạt, mypy 47 files đạt; TypeScript/ESLint/production build đạt.

Frontend giữ 121 ca cũ, thêm 5 ca đọc dữ liệu thành 126. Các vòng trước đổi viền đều 126/126, vòng cuối 11,8 phút; sau cleanup 8/8 smoke trong 55,5 giây. Một vòng kiểm viền trắng có 123 PASS/3 FAIL do harness chạy chồng: hai runners dùng chung thư mục trace gây ENOENT khi teardown; việc collection chạy lại generator tệp UAT làm SHA256 XLSX không còn khớp manifest đã nạp ở runner trước. Candidate cỡ chữ vòng đầu còn bắt được textarea vẫn 12px; đã sửa label inheritance, không đổi expected để che lỗi. Lượt candidate tách output đạt 16/16. Giữ đầy đủ log/trace; lượt full sau tăng chữ chạy riêng sau khi mọi runner khác kết thúc đạt 126/126 trong 11,8 phút. Không tăng timeout hoặc gọi AI để chữa các lỗi này. Lượt full trên thanh công cụ gọn ghi bên dưới. Không cộng replay thành test độc lập.

Security và các bất biến được kiểm: CSRF/Host/origin, viewer/isolation, cloud OFF, unknown delivery, zero-prefix, NULL/âm/locale, Decimal, grouping/cardinality/coverage, export injection và preservation. Tests có cả MOCK CONTRACT và LOCAL; chỉ những hành trình có receipt provider mới gọi là LIVE. Chưa có nghiên cứu screen-reader/thiết bị vật lý hoặc soak/multi-user mới trong đợt này.

#### Kết quả bàn giao local sau thanh công cụ gọn

- Full Playwright **126/126 PASS trong 11,7 phút** trên assets Docker của `7157f6a`, một runner, output riêng; không xen build hoặc regenerate fixtures. Đủ 11 tình huống UAT, kể cả F biên/bảo mật và G 1.000 giao dịch, tệp hỏng/quá dung lượng; các ca lỗi harness trước đã được chạy lại trong full suite này.
- Kiểm trình duyệt thật ở 5 viewport đạt: nền trắng/viền/bóng, chữ 16px, một thanh công cụ, menu không đẩy khung chat, Escape/focus/click ngoài, không page errors hoặc tràn ngang. Cached readback của run LIVE mới và G 1000 cùng tải/đọc lại Excel tiếp tục đạt; không gọi model mới để kiểm CSS.
- So 24 bảng/tất cả PK gốc và 3.712 tệp gốc: không missing/changed/checksum failure; chỉ đúng policy demo 210→null được cấp quyền. Toàn bộ metadata hiện tại và **3.502 artifacts + 364 run artifacts + 663 exports = 4.529 tệp** cũng qua checksum/snapshot/verify. Số dự án hiện tại 440, datasets 961, canonicals 780, runs 364; 78 dự án phát sinh trong đợt này đều TEST, giữ để audit thay vì xóa lịch sử nhằm làm counts nhỏ đi.
- Không có job đang queued/running/retryable khi snapshot bàn giao. Ledger vẫn 311, bốn config ceilings và workspace limit đều null; parser request allowance vẫn 2. Các traces tăng do regression xác định được tách khỏi 108 HTTP attempts đã đo. Không có inference mới sau khi dừng vì 429.
- Docker hiện 4/4 Studio healthy, chỉ 4 images riêng Studio: cặp current và cặp rollback; PostgreSQL và 2 volumes ứng dụng giữ nguyên. Toàn host có 51 images/31 containers/36 volumes; 27 containers ngoài Studio và mọi volumes đối chiếu nguyên trạng. Shared build cache không dọn toàn host. Langfuse 6/6 healthy; UI/health/ready/đọc observation cũ HTTP200.
- Source/OCI/HTTP hashes và phiên demo-owner/demo/owner được kiểm lại sau lần frontend recreate cuối. Frontend container/image revision `7157f6a`, Backend/Worker `98d93c9`; không thay backend code khi làm UI. Tài liệu và harness mới hơn không cần recreate Backend.

**Kết luận:** giao diện và các cổng kỹ thuật/nghiệp vụ local đã đạt trong phạm vi đo. Cổng AI live đầy đủ và phát hành main còn BLOCKED do HTTP429 cùng 63 ca đo đơn chưa hoàn tất; không gán nhãn READY_FOR_FINAL_USER_TEST. Hệ thống không bị trần request nội bộ cũ chặn, nhưng không thể cam kết provider khả dụng hoặc hiểu đúng mọi câu.

### G. KEEP / DELETE / ARCHIVE

Inventory có trước xóa tại `runtime/product-polish/cleanup-inventory.json`. 20/21 TS/TSX modules reachable; `vite-env.d.ts` là ambient type declaration cần giữ. Không có production component đủ bằng chứng để xóa. Bỏ các declarations CSS float/nền cũ đã được thay; giữ contracts, migrations, tests, manual fallback, security, lockfiles, `.venv`, node_modules, current dist và mọi backup.

Đã xóa đúng Frontend a7c1e8b không còn container tham chiếu; giữ current và cặp rollback dac8dd1. Đã xóa 3 nhánh local/remote `assistant-automation`, `assistant-conversation`, `demo-acceptance` sau khi xác minh SHA remote khớp và đã merge origin/main. Giữ `product-polish` để xử lý AI gate. Không xóa container nghiệp vụ hoặc tệp dữ liệu để giảm counts.

Xóa cache bị kiểm duyệt tự động chặn với lý do “blocked by policy”; 6 thư mục cache khoảng 30MB được giữ, không lách qua công cụ khác. Shared build cache và tài nguyên dự án khác được giữ; không global prune. Tài liệu/receipts lịch sử giữ để audit trong các vị trí sẵn có, không tạo archive framework mới.

27 containers ngoài Studio và toàn bộ 36 volumes được đối chiếu nguyên trạng. Langfuse có 6 dịch vụ healthy; UI/health/ready và đọc observation cũ HTTP200, không restart hoặc đổi deployment của Langfuse.

### H. README và khởi động

README được viết lại thành giới thiệu giá trị, hành trình sử dụng, phạm vi/quyền riêng tư và **2 lệnh**: `tools/start.ps1` hoặc `tools/start.ps1 -SkipBuild`. Thông tin backup/tests/usage ở tài liệu kỹ thuật. Build chuẩn tự giữ nhãn Git và khôi phục biến môi trường trước đó; cả hai lệnh kiểm HTTP/session/identity sau healthcheck và đã chạy thực tế.

Sau máy/Docker/Backend khởi động lại, dùng `-SkipBuild`, rồi bấm “Thử kết nối lại” nếu trang đang mở. Không xóa cookie hoặc dữ liệu để sửa kết nối. Không đưa request ledger hoặc biến môi trường lên Settings.

### I. GitHub, Docker và khả năng khôi phục

Các nhóm source đã push trên `codex/product-polish`: `0285d0a`, `2bcf27a`, `d32c488`, `ef966fc`, `fb76d10`, `75cfb16`, `98d93c9`, `1f82518`, `210f75b`, `2ab64e0`, `e9867ab`, `7157f6a`. **Main giữ `a4f70b2`** vì AI gate còn blocker; chưa fast-forward, không force-push. Commit bàn giao docs và SHA local/remote báo riêng để tránh hash tự tham chiếu. Không commit runtime, backups, `.env` hoặc keys.

Một Compose `ai-reconciliation-studio`, 4 services, 2 persistent volumes. Backend/Worker dùng source `98d93c9`, Frontend `7157f6a`; app code không đổi trong các commits harness/docs về sau. 42 Backend Python files khớp host/image ở cả hai dịch vụ; 7 frontend files khớp host/image/HTTP; Chromium resources được so SHA256 với cache tắt, không service worker. Proof/session được xác minh sau lần đổi container identity cuối.

Giữ cặp rollback `dac8dd1` cùng backup env/policy trước unlimited. Image cũ cần khôi phục cấu hình/policy hữu hạn tương thích, giữ mọi reservations mới. Script chặn trước Docker mutation nếu đang null/unlimited; negative compatibility test đạt. Không gọi đó là đã diễn tập rollback thực về mã cũ trong đợt này; không downgrade schema hoặc reset ledger. Candidate hiện tại chưa gắn nhãn accepted khi AI gate chưa đủ.

#### Định danh bản Docker đã đối chiếu

| Dịch vụ | Source revision | Image ID/digest |
| --- | --- | --- |
| frontend | `7157f6a8dc0a18d12458f2b695b625eca497f4a1` | `sha256:a1a9639479953e52415dbc5554b98a39ab685e1060657c86d5cee536fd92248a` |
| backend | `98d93c9e40f9d3dc3735006df055ff40a38b3e8d` | `sha256:d6d4f0268fc96b83dcedf0ee124d16fcc6f4fd526529a194124b03b0cb4a4a69` |
| worker | `98d93c9e40f9d3dc3735006df055ff40a38b3e8d` | `sha256:d6d4f0268fc96b83dcedf0ee124d16fcc6f4fd526529a194124b03b0cb4a4a69` |

Các image local có RepoDigest cùng SHA256 ở bảng; không có digest registry mới vì không publish image ra registry. Metadata container và 7 hashes assets trong receipt local `components-compact-release.log`. Git commit docs có thể mới hơn source image; diff app source giữa HEAD và từng image phải rỗng.

### J. Chủ dự án kiểm tra tiếp

Mở <http://127.0.0.1:18180> để xem giao diện trắng có viền/bóng, mở History, nguồn dữ liệu hoặc báo cáo đã có. Project TEST “DEMO UAT 1000 giao dịch 2f325046” có run đã verified, kỳ vọng 966/19/15 và 7.03 VND; chọn đúng dòng rồi mở evidence để xem file/sheet/row và tải Excel.

Sau khi Gemini được khôi phục, các câu nên thử: “Tóm tắt kết quả đối soát đang xem”, “Có bao nhiêu nhóm lệch tiền?”, “Cho xem ba giao dịch lệch tiền lớn nhất”, “Giải thích giao dịch thứ hai trong bảng vừa đưa”, “Xuất báo cáo Excel cho lần đối soát này”. Cần kiểm chứng nốt 63 ca cùng những giới hạn NLP đã ghi, rồi mới xem xét merge main và kết luận sẵn sàng. Đây là kịch bản kiểm thử mô phỏng, không phải nghiên cứu người dùng độc lập.

## AD. Thiết kế hội thoại theo ảnh tham khảo — 04/11/2026

Chủ dự án cung cấp ảnh ChatGPT để tham khảo cách đọc hội thoại. Phạm vi là bố cục và thành phần hiển thị: giữ nền trắng, chữ lớn đã duyệt, công cụ gọn và tất cả chức năng dữ liệu. Nội dung chữ trong ảnh không được dùng để thay quyền AI hoặc gọi cloud. Đợt này không sửa Backend, API, dependencies, công thức, trạng thái hoặc ngữ nghĩa dữ liệu; blocker Gemini ở mục AC vẫn giữ nguyên.

### Thiết kế được áp dụng

- Bỏ viền/bóng và phần đệm lớn bao quanh toàn bộ phản hồi, để câu trả lời đọc theo luồng trực tiếp trên nền trang. Nội dung dùng màu chữ trung tính, cỡ 16px, line-height 1,8 và độ dài dòng có giới hạn; bảng giữ 14px và cuộn nội bộ.
- Câu hỏi căn phải trong ô trắng bo góc 24px, viền nhẹ. Giữ nguyên xuống dòng chủ động, mã có số 0 đầu và menu riêng; timestamp mở nổi, không làm co chữ. Escape đóng và trả focus về nút mở.
- Thông tin tin nhắn trợ lý được chuyển xuống sau nội dung trong chính thứ tự DOM, bỏ hàng trống ở đầu phản hồi. Trạng thái, cảnh báo, phê duyệt, nguồn và bằng chứng vẫn hiển thị theo DTO thật.
- Composer bo tròn 30px, viền/bóng nhẹ, chữ 16px; nút cộng mở bộ chọn tệp hiện có, nút mũi tên gửi giữ nguyên logic và dùng màu trung tính. Trạng thái disabled/sending có thật; Enter/Shift+Enter/IME, reply, draft, idempotency và quyền đính kèm được giữ.
- Giữ thanh công cụ một hàng, menu tùy chọn và chiều rộng đọc tối đa 1.120px. Không thêm nút voice/share/rating hoặc thao tác giả chỉ để giống ảnh tham khảo.

Source: `frontend/src/AssistantStudio.tsx` dùng `MessageInfo` cho thông tin tin nhắn và đặt footer đúng vai trò; `frontend/src/styles.css` cập nhật bề mặt, typography, spacing và composer. `assistant-layout.spec.ts` bảo vệ bề mặt mới, vị trí footer, timestamp không đổi bounding box đoạn chữ, Escape/focus và viewport bounds. Yêu cầu mới đã được ghi ở đầu PROJECT_PLAN; thiết kế viền bao phản hồi ở mục AC là snapshot trước chỉ dẫn này.

### Kiểm chứng

TypeScript, ESLint và production build đạt. Candidate có **35 ca giao diện/tương tác đạt trong 2,5 phút**; sau chỉnh timestamp, chạy lại **5 ca ở 5 viewport đạt trong 22,3 giây**. Đây là replay của catalogue hiện có, không cộng thành 40 ca mới. Các ca bao gồm 23 trạng thái Assistant, nhập/gửi, giữ draft, review/clarification, Settings, đọc bảng/evidence và phân trang.

Đã xem screenshots desktop/mobile và đo trình duyệt thật tại 390/768/1366/1440/1920. Không tràn ngang hoặc page errors; phản hồi không viền, menu thông tin nằm sau nội dung, composer luôn có chỗ. Bản nháp hai dòng được nhập và reload còn nguyên, nút gửi bật đúng với mũi tên nền trung tính; không bấm gửi. Ledger trước/sau vẫn **311**. Receipts/screenshots tại `runtime/product-polish/reference-before`, `reference-candidate`, `reference-after` và các JSON tương ứng, đã ignored khỏi Git.

Trước/sau recreate riêng Frontend, snapshot/verify toàn bộ metadata và artifacts hiện có đạt; không đổi Backend/Worker hoặc volumes. Sau mutation đã chạy verifier chính thức qua HTTP/session. Định danh source/image/HTTP, full browser regression và Git handover được ghi bổ sung sau lượt cuối bên dưới. Không gọi Gemini/Knowledge để kiểm CSS; LIVE 429 và 63 ca AI còn thiếu không được coi là đã giải quyết bởi đợt thiết kế này.

### Cân đối và làm rõ ô chọn dự án

Chủ dự án xác nhận “Dữ liệu mới” là tên dự án, không phải tệp mất tên. Nguyên nhân gây nhầm là ô chọn giữ chiều rộng 420px và đẩy badge/mũi tên ra xa nội dung. `ProjectSelector.tsx` nay có nhãn “Dự án” khi dùng trong Chat, `title` giữ đầy đủ tên; các trang khác giữ cách hiển thị phạm vi nghiệp vụ hiện có. App chỉ bật nhãn trong thanh Chat.

Ô chọn co theo tên thay vì giữ khoảng trống: tên ngắn gọn tự nhiên, tên dài được giãn tối đa 560px và co lại theo màn hình. Badge và mũi tên đi cùng nội dung; ellipsis chỉ khi thiếu chỗ. Danh sách chọn vẫn giữ nguyên tên đầy đủ, tìm kiếm/phân trang/keyboard và quyền phân loại. Không sửa tên dự án/tệp, không tự chọn một tệp để đặt làm tên chung hoặc thay context/run.

Đã chạy **20 ca liên quan đạt trong 2,0 phút** trên candidate: tên ngắn/dài ở 5 viewport, header không vượt44px/không đè nút công cụ, caption và title đúng, danh sách5/50/120dự án và khôi phục ID ngoài trang. Kiểm trình duyệt thật thêm hai dự án TEST có tên ngắn/dài: kích thước tự giãn đúng, mở/đóng danh sách và focus đúng, ledger không tăng. Screenshots/receipts tại `runtime/product-polish/project-picker-candidate` và `project-picker-after`.

Bố cục theo ảnh tham khảo ở commit `279d3e1` đã đạt full **126/126 trong 12,5 phút** trước yêu cầu cân đối tên. Commit `e2f3153` bổ sung nhãn/kích thước ô chọn; các kết quả final dưới đây áp dụng sau lần triển khai này, không lấy lượt cũ thay lượt mới. Backend/Worker vẫn source `98d93c9`; không thay policy, quota hoặc gọi AI khi sửa header.

### Nghiệm thu bản hiện hành sau cân đối tên

Full Playwright **126/126 PASS trong 11,7 phút** trên chính assets Docker của `e2f3153`, chạy tuần tự với output riêng. Đã kiểm đủ 11 tình huống UAT và bộ 1.000 giao dịch, tệp hỏng/quá dung lượng, chọn dự án, ngữ cảnh, lịch sử, reply/review, bảng, modal, evidence, CSV/XLSX và reload. Các ca bao gồm MOCK CONTRACT và LOCAL; không gọi đó là đã nghiệm thu thêm AI LIVE.

Đối chiếu trình duyệt thật: ô tên ngắn “Dữ liệu mới” khoảng 223px, tên UAT dài khoảng 359px ở desktop; không giữ khoảng trống 420px. Tên dài synthetic được kiểm với giới hạn 560px và đầy đủ title; ở 5 viewport không đè nút công cụ hoặc gây tràn ngang. Caption “Dự án” phân biệt rõ nhóm dữ liệu với các tệp bên trong. Tất cả screenshots/receipts ở `project-picker-after`, `reference-after` và JSON tương ứng.

Sau lần recreate Frontend cuối, HTTP/session verifier đạt, cả 4 dịch vụ Studio healthy. Metadata và toàn bộ **3.748 artifacts + 390 run artifacts + 713 exports = 4.851 tệp** hiện tại qua checksum/snapshot/verify. So PK/full rows của 24 bảng gốc và 3.712 tệp gốc không missing/changed/file failure ngoài đúng thay đổi policy đã ghi ở AC. Không có job đang queued/running/retryable khi bàn giao. Ledger Gemini vẫn311, không có inference mới trong đợt thiết kế.

Giữ một Compose hiện có, 2 volumes Studio, 27 containers ngoài Studio và toàn bộ 36 volumes host. Chỉ 4 images riêng Studio là cặp current và cặp rollback cần giữ; không phát sinh container/project thử nghiệm, không xóa volumes hoặc dữ liệu để làm sạch. Langfuse6/6healthy, UI/health/ready/đọc observation cũ HTTP200. Chính sách cache đã bị chặn ở AC được giữ nguyên, không thử lách.

TypeScript/ESLint/build, 11 tài liệu Markdown không lỗi và repository secrets/history/links checks đạt. Source UI đã commit/push `279d3e1` và `e2f3153` trên nhánh `codex/product-polish`. Commit báo cáo và xác minh SHA local/remote được ghi riêng trong bàn giao; chưa merge main vì nghiệm thu AI ở AC vẫn BLOCKED, không gán READY_FOR_FINAL_USER_TEST cho toàn hệ thống.

| Dịch vụ | Source revision | Image ID/digest đã xác minh |
| --- | --- | --- |
| frontend | `e2f31538ca1391f0c8ab3223ec87cbc49f4a1d46` | `sha256:3743d305bd8dec13a490223593ee1d2492f2b105d958fc5d7979a11f300d3650` |
| backend | `98d93c9e40f9d3dc3735006df055ff40a38b3e8d` | `sha256:d6d4f0268fc96b83dcedf0ee124d16fcc6f4fd526529a194124b03b0cb4a4a69` |
| worker | `98d93c9e40f9d3dc3735006df055ff40a38b3e8d` | `sha256:d6d4f0268fc96b83dcedf0ee124d16fcc6f4fd526529a194124b03b0cb4a4a69` |

42 Backend Python files và 7 frontend files khớp host/image/HTTP; Chromium resources khớp với cache tắt, không service worker. Các commit docs sau source không làm thay code ứng dụng trong image.

## AE. Độ tin cậy, phục hồi lỗi, cuộn Chat và hướng dẫn người dùng — 05/11/2026

Phạm vi được giao: truy vết lỗi thật, trạng thái chuẩn hóa, phản hồi kết thúc, gửi trùng/cuộn Chat, kiểm toán nghiệp vụ, kiểm thử và hướng dẫn người mới. Tiếp tục cùng nhánh `codex/product-polish`, một Compose Studio; không thay engine, Verifier, công thức, Decimal, approval, quyền cloud/parser hoặc dữ liệu cũ.

### A. Nguyên nhân job bị báo lỗi

Job `64a84041-5fe4-4380-8764-bbf9839de525`, owner đúng workspace/project, nhận câu “2 bộ dữ liệu trên đã được chuẩn hoá chưa”. Trace cho thấy Gemini **HTTP200/STOP**, `agent-intent-31`, output được kiểm kiểu nhưng chọn **SUMMARIZE_RESULTS**. Hai dataset đã có mapping APPROVED và canonical READY, không stale: normalize jobs thành công lúc08:48:52 và08:48:55UTC; câu hỏi lúc09:07:01UTC. Đây không phải thiếu dữ liệu chuẩn hóa hoặc provider429 tại job đó.

`agent_workflows.advance` đi vào nhánh SUMMARIZE_RESULTS → `facts()` chọn tool `get_run_summary`. `context.run_id` là null; `assistant_tools.read_tool` gặp điều kiện `row is None or row.status not in {VERIFIED, PARTIAL_VERIFIED} or not row.metric_snapshot`, ném INSUFFICIENT_EVIDENCE. Gate financial này đúng với câu hỏi kết quả đối soát, nhưng routing đã dùng sai loại bằng chứng cho câu hỏi trạng thái nguồn.

Worker lưu job FAILED và workflow BLOCKED/error_code; transaction `advance` bị rollback trước đoạn tạo assistant MessageRow trong `execute_agent`. Do đó không có phản hồi trợ lý cho lượt này. Frontend khi đó chỉ hiện lỗi chung tạm thời, không có lỗi cụ thể bền vững trong transcript sau mở lại. Nguyên nhân đã chứng minh bằng metadata/job/workflow/trace; không suy ra chỉ từ một dòng log.

Trong hội thoại có hai user message khác nhau với cùng nội dung, hai jobs `e168cf34-e77a-4695-a55c-e9bacc501f38` và `64a84041-5fe4-4380-8764-bbf9839de525`, lúc09:06:09 và09:07:01UTC, khóa idempotency khác nhau, mỗi job một attempt. Đây là hai logical requests; không có HAR gốc để kết luận người dùng chủ động gửi lại hay trình duyệt tự tạo lần gửi mới. Không xóa/gộp hai lịch sử hợp lệ hoặc quy trách nhiệm cho người dùng từ DB alone.

### B. Sửa Agent và vòng đời lỗi

- `dataset_status.py`: DTO đọc metadata scoped; xác định phiên bản nguồn mới nhất, active mapping và revision normalization hiện hành. Phân biệt upload/đang đọc/đọc lỗi/đã đọc/chờ duyệt/đã duyệt/READY/PARTIAL/FAILED/stale. Không cần VerifiedRun và không gọi AI để trả lời các biến thể câu hỏi trạng thái được nhận diện.
- `agent_jobs.interpret` ưu tiên câu hỏi trạng thái; `agent_workflows.advance` công bố phản hồi từ metadata. Nguồn không xác định hỏi lại; thiếu tệp hướng dẫn tải. READY chỉ là chuẩn hóa, không tuyên bố đối soát hoặc đủ coverage cho một contract.
- SUMMARIZE_RESULTS không có run chuyển thành câu hỏi chọn kết quả hợp lệ; financial tool vẫn fail-closed. Không biến lỗi lập trình/hạ tầng thành clarification chung.
- `persist_request_failure` tạo tối đa một assistant reply cùng transaction với terminal failure, UUID ổn định/unique job-role, thông báo redacted theo lỗi. Không hồi sinh hội thoại đã xóa/quyền bị thu hồi. MessageView thêm job_status/error_code để UI còn trình bày được các lỗi cũ chưa có assistant reply, không sửa lịch sử cũ.
- Phân biệt thiếu bằng chứng/thông tin, sai trường/chỉ tiêu, thiếu quyền/phiên, stale, provider429/timeout/unknown delivery và worker failure. Không lưu exception body, path hay credentials trong phản hồi.
- Khi hết ba attempts/lease, parse source chuyển FAILED, run chưa có snapshot chuyển BLOCKED, workflow/pending reply nhận lỗi kết thúc. Không treo trạng thái “đang chạy” hoặc giả publish thành công.
- Trình duyệt không ngừng quan sát job sau60poll ban đầu; GET chậm lại hai giây và dừng khi rời/đổi hội thoại. Không POST lại hoặc gọi provider để kiểm trạng thái.

Trên đúng dự án của lỗi gốc, tạo hội thoại TEST riêng, gửi lại câu hỏi gốc qua Chromium thật: job `83408844-1f07-4c00-8c91-50d52a61ab5b`, workflow `c88e6e32-0a81-5ace-af7c-46ac96f19821`, SUCCEEDED/COMPLETED, CHECK_DATASET_STATUS, hai nguồn READY, model_calls0. Reload vẫn có phản hồi; ledger313→313. Không sửa hai job thất bại cũ. Receipt `reported-status-browser.json`, ảnh trong hướng dẫn.

LIVE còn tái hiện D07 “Cho tôi xem trước cả hai nguồn giao nhận”: model trả hai intents cho một mục tiêu, bị AI_INVALID_INTENT_COUNT chặn. Đường preview chỉ đọc trong `resolve_plain_listing` nay xử lý plural preview từ đúng catalogue mà không hỏi model; thiếu/khác số nguồn thì hỏi lại. Filter/tiền/kỳ/tác vụ write vẫn qua router typed. Không hợp thức hóa output model sai hoặc đổi golden expected. Các biến thể có regression PostgreSQL; đây là sửa LOCAL xác định, không đổi kết quả chấm LIVE D07 thành PASS.

### C. Cuộn hội thoại

Trước sửa, effect chỉ phụ thuộc lastMessageId: bảng/thẻ workflow đến muộn cùng message ID không cuộn theo; thêm lịch sử hoặc mở lại tin cũ chưa có trạng thái đọc rõ ràng. Bản sửa chỉ điều khiển `.assistant-scroll`, không window:

- Gửi câu mới luôn xuống cuối, gồm khi đang đọc ở trên; giữ focus và bộ gõ/draft.
- Theo dõi cuối bằng refs và ResizeObserver có cleanup, theo cả nội dung và chiều cao pane.
- Chủ động đọc cũ thì không kéo xuống; có nút quay về mới nhất, tôn trọng reduced motion.
- Prepend giữ anchor theo chênh lệch chiều cao. Nội dung lịch sử cũ không tạo thông báo “Tin nhắn mới”; resize pane đơn thuần cũng không giả là tin mới.
- Reload/mở hội thoại xem phần mới nhất; bảng/modal và thông tin tin nhắn giữ khả năng quay lại vị trí đọc.

Regression đo scrollTop/scrollHeight, bounding box, phần tử trong viewport, window.scrollY và POST count; có390/1440/1920px, phản hồi chậm, bảng dài, clarification, approval, lỗi terminal, double-click và clock vượt60poll. Ca cũ đo metadata phải đưa câu hỏi cũ vào viewport trước khi đo; giữ so sánh bounding box chính xác, không nới yêu cầu để che reflow. Lỗi thông báo nhầm sau prepend có receipt FAIL trước sửa và **9/9 PASS** sau sửa.

### D. Hành trình nghiệp vụ và tài liệu

Giữ 11 bộ UAT tổng hợp với oracle độc lập, không sửa đáp án: CSV/XLSX/multi-sheet, tiền Decimal/âm/NULL/0, zero-prefix, duplicate,1:1/1:N/N:1/composite, tolerance, currency/coverage và evidence/export. Bộ1.000 giữ966EQUAL/19AMOUNT_MISMATCH/15UNMATCHED/7,03VND; bộ nhỏ đúng run giữ3/1/2/0,50VND. Đã đọc lại qua browser, typed read tools, chart, evidence và tải XLSX rồi kiểm snapshot/formula injection; đó là LOCAL/CACHED, không LIVE inference mới.

`USER_TEST_GUIDE.md` dành cho người mới, README liên kết ngắn. Có vị trí/nút thật, hai tệp tổng hợp A25/B24, đáp án từng mã và tổng chênh lệch, đường AI và manual fallback, phê duyệt, dữ liệu lỗi/stale, chọn explicit phiên bản chuẩn hóa, chọn đúng run, bảng/chart/evidence/export, History/draft/reload, lỗi và khôi phục kết nối. Các ảnh chỉ có dữ liệu tổng hợp của runtime thực, không mockup hoặc credentials.

Khi tự làm theo hướng dẫn đã phát hiện bước chọn bản chuẩn hóa còn thiếu: nút Đã chuẩn hóa/Dòng lỗi khóa cho đến khi chọn **Phiên bản chuẩn hóa**. Đã bổ sung bước, giữ guard chọn revision, không tự chọn bản cũ. Hướng dẫn cũng phân biệt một cụm khóa mơ hồ000002 với ba dòng chưa liên kết của báo cáo; bộ A có27mục kết quả,19/24đơn vị eligible khớp79,17%, không tự dùng19/27 làm KPI. Tiền trống không thành0; raw Decimal `264.600` được giải thích là264,600VND, không phải hàng nghìn.

### E. Cổng kiểm chứng và giới hạn

Baseline trước sửa337Backend/PostgreSQL PASS. Sau các sửa bổ sung khi làm theo hướng dẫn, source `f2de497` **400/400 PASS**123,75giây; đúng backend/worker Docker cùng source **400/400 PASS**138,42giây. Lượt391 trước đó là mốc trung gian, không thay gate của bản hiện hành. Ruff, mypy43files, ESLint, TypeScript/build, repository secrets/history/links và Markdown đạt tại các receipts nhiệm vụ. Một cảnh báo deprecation của Starlette TestClient còn được ghi; không phải test failure hoặc lý do nâng đồng loạt dependencies.

Full browser đầu trên `bf07d16`:129PASS/5FAIL; năm failure là đo metadata khi Playwright tự cuộn câu hỏi từ ngoài viewport, đã sửa cách đo và giữ assertions. Candidate sau sửa chờ job chậm/metadata **19/19 PASS**; thêm kiểm notification prepend phát hiện lỗi thật, sửa và9/9PASS. Full regression production tại source `f2de497`: **136/136 PASS,14,9phút**, gồm11bộ UAT LOCAL có oracle, upload→review→normalization→verification→evidence→CSV/XLSX→reload, security/recovery/responsive và các ca MOCK CONTRACT được ghi riêng trong tên. Receipt `reliability-final-browser.log`; không gọi đây là136ca AI LIVE. Cập nhật CSS `cdef8fb` sau đó **19/19ca bố cục/cuộn PASS,2,3phút** trên Docker mới (`reliability-spacing-browser.log`). Đo hai nút Xem bằng chứng/Hỏi vì sao lệch: trước sửa gap0 FAIL, sau sửa gap12px ở390/768/1366/1440/1920, không document overflow; mở đúng evidence tiếp tục PASS (`guide-evidence.json`, `reliability-spacing-before.log`/`after.log`). Không tuyên bố full136 được chạy lại trên image CSS mới; diff chỉ một CSS declaration, Backend không thay.

### F. Backup, runtime và Git

Backup mới `backup_8ea050f8963f480da761d396be4bb1a5`: metadata SHA256 `87b95f751847c7a37c1c30a85c2489ea7dc06ac61577b62fd8894602bc7b34d2`,24bảng/4.851tệp, restore UUID schema PASS, checksum corruption/path traversal bị chặn, public không đổi. Backup43,954giây/restore30,337giây; bản host độc lập kiểm lại đủ4.851SHA. Giữ cả backup gốc ở AC và hai volumes.

Backend/Worker source **`f2de497978ddd344c0108e06000cda4e65e41703`**; Frontend source **`cdef8fbd90af1916defd17ab8eced9b132683420`** bổ sung đúng một rule CSS giãn hai nút ở bảng kết quả. Backend/Worker image `sha256:851850744ae750021359cac496c93c602c973ec9a874113692ec546c9dd31222`; Frontend image `sha256:7620b3d1d0268efa358a32bfa199071a1ba82497cb8075fa1c249adf9df949f6`.43Python files và7HTML/assets khớp host/image/HTTP; backend/worker cùng image và Git diff backend từ source image tới HEAD rỗng. Các sửa code gồm `bf07d16`, `4de04f0`, `b6071c0`, `91646b4`, `f2de497`, `cdef8fb`; sau lỗi GitHub commit_refs/Internal Server Error tạm thời, push bình thường đã thành công, không force hoặc đổi remote. Official origin không đổi. Main chưa merge khi AI LIVE còn chưa qua đủ gate.

Recreate Backend/Worker và Frontend đã snapshot/verify metadata/artifact bytes không đổi; cả4serviceshealthy, loopback18180 và session verifier đạt. Sau khởi động lại môi trường05/11 dùng đúng start-SkipBuild để khôi phục proof, không xóa cookie/volume hoặc dữ liệu. Receipt snapshot/verify của deploy logic: `reliability-scope-persistence-before.log` và `reliability-scope-persistence-after.log`; cập nhật CSS cuối có `reliability-spacing-persistence-before.log`/`after.log` PASS. Mã nguồn/image/HTTP hiện hành tại `reliability-release-components.log`; diff Backend từ source image tới HEAD rỗng. Không rebuild Backend vì chỉ đổi CSS.

### G. Lỗi bổ sung tìm được qua hướng dẫn thực tế

Câu “Đề xuất cách chuẩn hóa hai nguồn dữ liệu. Hãy hỏi tôi nếu có cột hoặc ý nghĩa chưa rõ.” từng bị classifier trạng thái nhận vì có từ “chưa”. Job `e428f855-b313-4b52-8f39-0fcbd4987c47` đã trả trạng thái thay vì chuẩn bị đề xuất. `91646b4` loại các lệnh thực hiện/đề xuất khỏi shortcut trạng thái; thêm7ca phân biệt lệnh có mệnh đề điều kiện với câu hỏi chỉ đọc. Gửi yêu cầu mới sau sửa đi đúng PREPARE_NORMALIZATION, nhưng provider lỗi ở nguồn B; không sửa hoặc xóa lượt sai trước đó.

Khi trở về Chat từ màn hình nguồn B, sidebar giữ đúng dataset scope. Trước sửa, câu hỏi “Hai bộ dữ liệu đã được chuẩn hóa chưa?” chỉ trả một nguồn rồi COMPLETED. `f2de497` kiểm số nguồn được yêu cầu, trả clarification khi phạm vi không đủ; thêm hai ca PostgreSQL. Dialog ngữ cảnh hiển thị tên tệp và nút **Dùng dữ liệu của dự án**, giữ draft/hội thoại riêng, không gọi AI hoặc ghi nghiệp vụ. Browser regression kiểm tên, scope, giữ draft, reload và zero write; initializer MOCK chỉ chạy một lần để không tự khôi phục scope cũ khi reload.

Dự án thực hành mới **TEST Học đối soát đơn hàng — nghiệm thu hướng dẫn**, ID `a623bee0-ffdb-4407-a34d-be77d43df21f`, tải hai tệp qua composer; chuẩn hóa thủ công có kiểm tra/phê duyệt từng nguồn. Sau sửa phạm vi, câu hỏi trạng thái trả đúng hai READY, model_calls0. Phê duyệt quy tắc và chạy từ nút thật tạo run **`71801df7-fb6d-4b5c-8f97-7e9b648e84be`**, PARTIAL_VERIFIED đúng fixture chứa thiếu/mơ hồ/NULL:19EQUAL/2AMOUNT_MISMATCH/2UNMATCHED, full match19/24=79,17%, signed−249,900/absolute264,600VND. Không đổi engine/oracle để ép VERIFIED toàn phần.

Hướng dẫn đã sửa đúng chuỗi **Lưu đề xuất thủ công → Xác nhận quy tắc và dấu số tiền → Chạy đối soát đã duyệt**, giữ hai quyết định riêng. Lượt chạy công cụ hướng dẫn đầu gọi sai tên nút đã lưu một đề xuất chưa duyệt; giữ lịch sử, lần thực hành tiếp lưu đề xuất được kiểm tra và phê duyệt, không tạo thêm canonical hoặc chạy đối soát trùng. CSV và XLSX tải qua Chromium, Snapshot JSON của cả hai bằng đúng snapshot API; giữ mã000001/000010, không ô công thức. Đọc Sources xác nhận amount của000010 làNULL,000011 là0,000009 là−42,125 và phía đối ứng000010 là357,25, không chỉ so tổng. Bằng chứng dòng000004 mở đúng run/mã, hai nguồn113,25/105,90. Reload/report/draft/History đạt, không lỗi JavaScript. Receipts `guide-walkthrough.json`, `guide-export-readback.json`, `guide-evidence.json`; không xem những bước thủ công là AI LIVE.

### H. AI LIVE, chi phí và giới hạn nghiệm thu

Vòng prompt `agent-intent-32` có canary D27 PASS LIVE. Full gold dừng tại D21 vì HTTP429:20ca đo được trong lượt chính,19/20intent,19/20source,12/12semantic,19/20tool. Gộp canary là21gold khác nhau đã đo, một D07 sai intent count;59gold chưa nghiệm thu (gồm D21 bị quota),24variants chưa chạy. Launcher không chạy variants sau429. D07 được sửa LOCAL bằng preview xác định, không đổi kết quả LIVE sai thành PASS và không gọi benchmark của prompt31 là kết quả prompt32.

Ngày05/11, sau khi người dùng tiếp tục và quota có phản hồi lại, câu hỏi kiểm tra hai tệp của hướng dẫn có HTTP200/SUCCEEDED/COMPLETED thật. Yêu cầu chuẩn hóa sau sửa classifier đi đúng intent; đề xuất A được lưu, nguồn B nhận **HTTP503 GEMINI_UNAVAILABLE**, receipt `delivery_unknown:false`, một attempt. Workflow BLOCKED, không tự duyệt đề xuất A hay gửi lại B. Đây là phản hồi dịch vụ503, không có bằng chứng unknown delivery. Trạng thái provider gần nhất không còn chỉ là429 của vòng trước; full quality gate vẫn chưa đạt vì coverage thiếu và một lỗi model đã đo.

Từ backup đầu nhiệm vụ313 đến339 reservations: **26 HTTP attempts mới,24HTTP200/1HTTP429/1HTTP503**. HTTP200 chỉ xác nhận dịch vụ trả, không chứng minh hiểu đúng ý. Prompt tokens356.402/output4.938/total361.340, cached0; latency26samples p50=2.883,5ms/p95=4.688ms. Chi phí hóa đơn **NOT VERIFIED**; không bịa đơn giá hoặc tiền đã trả. Ledger/tokens/failures không reset; không đổi key/account/provider/model hoặc parser allowance. Active public jobs0 tại lần chốt usage. Receipt `reliability-final-usage.json`.

### I. Dữ liệu, Docker và mức sẵn sàng

Đối chiếu tất cả PK/nội dung24bảng và4.851tệp từ backup đầu nhiệm vụ: không thiếu/thay đổi bản ghi cũ, SHA đầy đủ đạt. Backup trước đó3.712tệp cũng đạt; chỉ có amendment policy210→null đã được ủy quyền từ nhiệm vụ trước, không thay business rows. Snapshot/verify qua recreate đạt; hai volumes Studio, backups, uploads và artifacts được giữ. Full browser tạo thêm dữ liệu TEST; đó là dữ liệu nghiệm thu mới, không phải mất/thay dữ liệu cũ.

Inventory cuối:31containers/51images/36volumes toàn host; Studio đúng4containershealthy, hai image hiện hành và cặp rollback `dac8dd1`. **0 image cũ thuộc Studio đủ điều kiện xóa thêm**, không tạo con số dung lượng đã giải phóng giả.27container dự án khác giữ nguyên IDs/image/volume refs;36volume names giữ nguyên. Shared build cache38,62GB không có bằng chứng sở hữu riêng nên giữ; không global prune/volume delete. Một ảnh hướng dẫn thừa do nhiệm vụ tạo đã xóa, runtime receipts/backup giữ phục vụ kiểm toán. Inventory/ownership review hiện hành: `reliability-release-cleanup-plan.json`; không có container Studio dư hoặc dừng, không OOM/restart ở bốn services hiện hành.

Langfuse đang thuộc Compose `langfuse`,6services được Docker khởi động sau reboot; không sửa dữ liệu hoặc config dự án đó. Kiểm tra chỉ đọc: web200/health200/ready200, đọc một observation cũ200, không lỗi JavaScript. Không tuyên bố kiểm tra cả mọi dự án sử dụng Langfuse.

Có thể sử dụng local tại `http://127.0.0.1:18180` cho các luồng đã kiểm chứng, gồm manual fallback và câu hỏi trạng thái nguồn. **Chưa chứng nhận READY_FOR_FINAL_USER_TEST cho toàn bộ AI tự động**: full current-prompt80gold/24variants còn thiếu, provider429/503 và lỗi model cần replay lại khi dịch vụ khả dụng. Các ví dụ chat mở trong hướng dẫn không phải tất cả đã được LIVE xác nhận trên dự án mới. Không merge main hoặc tuyên bố không còn mọi lỗi khi gate này chưa đạt. Source sửa đã push official feature branch; commit tài liệu được báo tại bàn giao Git.

### J. Bàn giao source và tài liệu

Các lỗi tái hiện thuộc phạm vi đã được sửa, full regression và các checks liên quan đạt như mục E; không còn lỗi tái hiện LOCAL nghiêm trọng đã biết trong các luồng đã đo. Điều này không phải cam kết không có mọi lỗi hoặc AI luôn hiểu đúng. README liên kết hướng dẫn mới; `USER_TEST_GUIDE.md` có8ảnh thực chụp từ Docker hiện hành, từng bước và đường manual đã thực hành trên dự án mới. Markdown12tài liệu0issue; Ruff/mypy43files, ESLint/TypeScript/build, repository paths/known-secrets/history và diff whitespace đạt. Không thêm dependencies, migrations, services hoặc worktree.

Code hiện hành đã push nhánh `codex/product-polish`, official origin được kiểm trước push. Main vẫn `a4f70b289b935b11928e6d1c2b2e0748160fbfa1`, chưa merge vì mục H chưa đủ full LIVE gate. Commit tài liệu bàn giao tiếp theo chỉ đổi README/hướng dẫn/ảnh/báo cáo; source ứng dụng trong Docker vẫn trùng với source đã kiểm tra. Commit hash bàn giao được nêu trong trả lời và xác minh bằng remote/status, không tự ghi hash chưa tồn tại vào báo cáo.

## AF. Chuẩn hóa ngày và kiểm chứng Smart Mapping với ba nguồn tháng 10/2026

### A. Nguyên nhân và bản sửa

Nguồn `01_don_hang_du_kien_2400.csv` có 2.418 dòng. Job gốc `5adf1d0e-2089-4cde-a2ef-5970d249cefe` hoàn tất với chất lượng PARTIAL, nhưng cả 2.418 dòng bị đánh dấu không hợp lệ. Bản ánh xạ đã duyệt `bef7cbec-77b7-47d7-958b-9a8bac9f37ab` lưu định dạng `YYYY-MM-DD`, múi giờ UTC. Cùng artifact Parsed và image Worker cũ tái hiện lỗi: bộ chuyển đổi truyền chuỗi hiển thị nguyên văn cho [Python datetime.strptime](https://docs.python.org/3.12/library/datetime.html#strftime-and-strptime-format-codes); chuỗi `2026-10-10` gây `ValueError: time data '2026-10-10' does not match format 'YYYY-MM-DD'`, rồi bị ghi là `INVALID_DATE`. Đây là exception từ lần tái hiện; artifact lỗi gốc không lưu traceback.

`date_parsing.py` chuyển ba mẫu hiển thị sang định dạng Python, kiểm tra cú pháp và múi giờ IANA trước khi đọc dòng, tách lỗi cấu hình/môi trường khỏi lỗi dữ liệu. Kiểm tra offset và giờ nhập nhằng hoặc không tồn tại khi đổi giờ mùa hè. Backend và Worker dùng cùng image, có dữ liệu múi giờ Debian `2026b-0+deb12u1`; UTC, Asia/Ho_Chi_Minh và America/New_York được kiểm. Hành vi dùng dữ liệu hệ thống phù hợp [Python zoneinfo](https://docs.python.org/3.12/library/zoneinfo.html#data-sources). Không đổi dependency Python hay migration.

### B. Kết quả trên nguồn gốc và dự án kiểm thử

Giữ bản chuẩn hóa `cf3f21ef-2a8c-4795-8419-0545f64aec46`. Job mới `a3e58d64-1829-4589-9b16-90aa70d065f8` dùng cùng ánh xạ đã duyệt, tạo `7e492f46-b668-42df-9be6-ef84139df85f` (`normalization-2`): **2.408 hợp lệ, 10 không hợp lệ**. Số lỗi ngày từ 2.418 còn đúng 2; số bản ghi lỗi từ 2.432 còn 16. Mười bốn lỗi khác vẫn còn. SHA-256 của file gốc và metadata bản chuẩn hóa cũ không đổi.

Tải ba tệp gốc vào dự án TEST mới `7967303e-0bdc-461b-ad07-cd8ce9d4f31f`; kiểm chứng và duyệt thủ công từng nguồn trên trình duyệt sau khi AI bị chặn. Đọc lại artifact Worker và so từng ngày, giá trị Decimal đã chuyển được, mã có số 0 đầu và dấu vết dòng vật lý với dữ liệu nguồn.

| Nguồn | Tổng dòng | Hợp lệ | Không hợp lệ | Lỗi ngày thật | Lỗi ngoài ngày |
| --- | ---: | ---: | ---: | ---: | --- |
| 01 · Đơn dự kiến CSV | 2.418 | 2.408 | 10 | 2 | `amount`: 4 trống, 5 sai định dạng, 3 khác tiền tệ; `reference`: 2 trống |
| 02 · Sự kiện thanh toán XLSX | 2.685 | 2.674 | 11 | 5 | `amount`: 3 trống, 5 sai định dạng, 3 khác tiền tệ; `batch_id`, `currency`, `reference`: 2, 3, 3 trống |
| 03 · Sao kê theo lô CSV | 384 | 380 | 4 | 0 | `batch_id`: 2 trống; `gross_amount`: 2 sai định dạng; gross, net và fee: mỗi cột 2 khác tiền tệ |

Tổng 5.487 dòng, 5.462 hợp lệ, 25 cần kiểm tra. Mọi dòng `MAIN_VND` hợp lệ; lỗi chỉ ở `EDGE_CASE`. Một dòng có thể có nhiều lỗi. Giữ nguyên giá trị gốc, không bù NULL bằng 0, không đổi USD thành VND hoặc tự đổi trạng thái dự kiến thành đã thanh toán.

![Bản chuẩn hóa cũ và bản mới của nguồn 01 hiển thị cùng nhau trên Docker](images/user-guide/date-normalization-comparison.png)

### C. Kiểm chứng đề xuất trước khi duyệt

Profiling bổ sung thống kê định dạng ngày, cách viết số, giá trị rỗng, số 0 đầu, tiền tệ và tính duy nhất. Chỉ điền sẵn dữ kiện đủ bằng chứng. So mẫu đã duyệt theo workspace, nghiệp vụ và chữ ký cấu trúc tương thích; quyền duyệt cũ không chuyển sang bản mới. Không suy múi giờ từ ngày trần, tự đoán gross/net hoặc dùng mã khách hàng làm khóa khi dòng là đơn/sự kiện/lô và thiếu bằng chứng quan hệ.

Preflight kiểm thử toàn bảng với đúng bộ chuyển đổi của Worker, không xuất bản dữ liệu. Kiểm checksum và báo số dòng dự kiến lỗi, chặn cấu hình làm tất cả giá trị không rỗng của một trường cùng lỗi. Kiểm phép biến đổi không tổng hợp theo lô 2.000 dòng để hạn chế RAM; phép tổng hợp giữ đầy đủ thành viên. API kiểm quyền và kiểm lại bản nháp tại thời điểm duyệt; thay đổi bản nháp làm kết quả cũ mất hiệu lực. Hợp đồng đối soát, công thức tiền, trạng thái và cơ chế quyền giữ nguyên.

### D. Giao diện

Khung duyệt trong chat gom thành **Đã xác định bằng bằng chứng**, **Cần bạn xác nhận** và **Dữ liệu bất thường**. Chọn múi giờ chung một lần cho nguồn khi thích hợp; mở **Xem và chỉnh các lựa chọn** để sửa từng cột. Nút duyệt chờ kết quả kiểm tra của đúng bản nháp và mỗi nguồn vẫn cần quyết định riêng. [Ảnh khung duyệt](images/user-guide/mapping-review.png) chụp từ Chromium với phản hồi mô phỏng (MOCK). Ảnh trước, ảnh kiểm tra thủ công và biên bản dữ liệu tổng hợp giữ tại `runtime/mapping-audit/` trên máy kiểm thử.

### E. Đối soát, bằng chứng và xuất tệp

Cả hai run `PARTIAL_VERIFIED`, đúng với bộ thử có nhóm chưa đủ điều kiện và dòng bị loại. Hai hợp đồng riêng theo `MAIN_VND`, UTC, kỳ tháng 10/2026 và sai số 0 VND. Oracle độc lập đọc CSV/XLSX, nhóm khóa ghép và cộng có dấu bằng Decimal; không dùng Matcher hoặc Verifier.

| Run | Quan hệ và khóa | Khớp | Lệch tiền | Thiếu đối ứng (trái/phải) | Lệch có dấu / tuyệt đối |
| --- | --- | ---: | ---: | ---: | ---: |
| `a40bbb98-c05f-499a-ac03-f13be55d23c7` | 01 ↔ 02, 1:N theo `scope + reference` | 2.040 | 200 | 215 (160/55) | 7.867 / 60.883 VND |
| `d94ed637-0e80-4b0a-bac4-1256d4eabd1e` | 02 ↔ 03, N:1 theo `scope + batch_id`, dùng gross | 323 | 40 | 31 (18/13) | −8.306 / 11.812 VND |

Đã mở đúng hai báo cáo, biểu đồ, truy vấn ba nhóm lệch lớn nhất và bằng chứng của nhóm thứ hai; kiểm khóa và nguồn, mở đúng dòng từ bảng, tải lại vẫn giữ kết quả. CSV và XLSX của từng run giữ đúng snapshot API; cả 240 nhóm lệch khớp khóa và tiền từng phía với oracle. Hai bản xuất có 5.103/3.069 dòng bằng chứng và 51.297/33.375 ô nguồn; không có ô công thức, giữ số âm và số 0 đầu.

Excel cặp đầu từng treo hơn 4 phút vì mỗi lần thêm dòng lại duyệt toàn worksheet để tra dòng cuối. Bản sửa dùng tọa độ trực tiếp và giới hạn số dòng dùng để ước lượng độ rộng. Job `7043c3ac-e7da-413f-91c6-bc414f75d4a4` được phục hồi qua lease và hoàn tất lần xử lý sau trong 14,490 giây, với cùng một export. Khi tải phiên chậm, mở liên kết run B trước khi tải xong run A từng bị trả về A. Frontend hiện ghi nhận đích mới trong lúc tải phiên; đổi dự án hủy lần đọc cũ. Đã tái hiện trên bản cũ và xác nhận URL, báo cáo đúng run B trên bản triển khai.

### F. Kiểm thử và AI LIVE

Backend/PostgreSQL **435/435** (một cảnh báo deprecation từ Starlette TestClient); Playwright toàn bộ **137/137** trên bản Docker trước bản sửa điều hướng và **39/39** ca thuộc Assistant, Mapping Review, bố cục và cuộn chat trên bản Docker sau sửa. Có ca bảo mật, responsive 390–1920 px, đường thủ công và kiểm thử hợp đồng AI mô phỏng. Bộ kiểm ngày gồm CSV/XLSX, NULL/invalid, lỗi cấu hình/múi giờ, DST, offset và truy vết dòng. Có ca từ chối khóa khách hàng không phù hợp, xử lý currency/locale mơ hồ và sửa bản nháp sau preflight.

Vòng đầu và vòng sau đổi khóa đều dùng dữ liệu tổng hợp, cùng model `gemini-3.5-flash-lite`. Đã kiểm Backend/Worker dùng cấu hình mới mà không in khóa. Vòng sau: job `69765cf3-7984-4ab3-a9e8-90be22d47efb` nhận HTTP 200 sau 4.735 ms, xác định đúng lệnh chuẩn hóa và cả ba nguồn. Job đề xuất `eab07043-5e88-4b2c-a898-70adf644e05e` (`agent-normalization-5`) nhận HTTP 503 sau 1.853 ms, một attempt, `delivery_unknown: false`. Luồng BLOCKED, không có đề xuất để duyệt, không gửi lại sau 503. Không có bằng chứng khóa mới bị từ chối hoặc cơ sở kết luận nguyên nhân nội bộ của Gemini.

Hai vòng cộng **4 HTTP attempts mới** (2 × 200, 2 × 503), ledger 342 → 346; hai phản hồi có số đo ghi nhận 21.583 tokens (21.271 đầu vào, 312 đầu ra). Chi phí hóa đơn chưa xác minh. Chưa có bộ đề xuất LIVE để đo mức tăng độ chính xác, độ bao phủ hoặc số lần người dùng phải sửa. Kết quả thủ công, kiểm chứng local và MOCK không thay phép đo LIVE.

### G. Dữ liệu, Docker và Git

Backup `backup_39aa77c2aa464f11ac3655deee279ce5` trên volume artifact: sao lưu 80,138 giây, restore thử vào schema tách biệt 36,228 giây. Đối chiếu sau kiểm thử: đủ bản ghi cũ trong 24 bảng, không đổi giá trị; SHA-256 của 5.347 tệp đều khớp. Giữ backup, hai volumes Studio, raw, ánh xạ đã duyệt và artifact cũ. Sau recreate Frontend, snapshot/verify đạt. Cả bốn dịch vụ healthy; cổng chỉ bind loopback. Đã đối chiếu 45 file Python giữa host và hai container, 7 file Frontend giữa bản dựng, image và HTTP.

Studio có 4 container đang chạy, 2 image hiện hành (Frontend 24,7 MiB, Backend/Worker 149,1 MiB) và 4 image giữ để rollback. Không có job chờ hoặc đang chạy tại lần kiểm cuối. Không có container Studio dư hoặc image cũ của Studio đủ điều kiện xóa. So với đầu nhiệm vụ, 27 container ngoài Studio giữ nguyên danh tính, image và volume; 36 volume toàn host giữ nguyên. Compose `langfuse` vẫn độc lập và 6 dịch vụ đều healthy. Giữ cache dùng chung và tài nguyên của các dự án khác.

Backend/Worker ở `09290a46ea82a8905386b0d7a314d1f537a05a6d`, Frontend ở `ef9cf0c2e32a81549d0df545b740b047c25199ca`. Các nhóm thay đổi: `b1478d3` sửa ngày và preflight; `cd6ae91` kiểm dữ kiện theo phạm vi và giới hạn bộ nhớ kiểm tra; `09290a4` sửa hiệu năng xuất Excel; `ef9cf0c` sửa liên kết báo cáo. Mã đã push nhánh `codex/product-polish` trên origin chính thức. Main giữ `a4f70b289b935b11928e6d1c2b2e0748160fbfa1` vì cổng AI LIVE chưa đạt.

### H. Mức sẵn sàng và cách bắt đầu

Có thể dùng [Studio local](http://127.0.0.1:18180) để chuẩn hóa có kiểm chứng và duyệt thủ công, đối soát, đọc báo cáo/bằng chứng và xuất tệp trong phạm vi đã thử. Bắt đầu theo [hướng dẫn](USER_TEST_GUIDE.md), mục 5 và 13. Luồng tự tạo đề xuất Smart Mapping ba nguồn vẫn **BLOCKED ở Gemini HTTP 503**. Cần một lượt LIVE thành công để nghiệm thu độ chính xác đề xuất và đo mức giảm thao tác; chưa có cơ sở phát hành toàn bộ luồng AI tự động.

## AG. Gemini và Qwen trong AI Assistant

### Chẩn đoán Gemini

Trạng thái **GEMINI_INTERMITTENT**. Kiểm tra có dùng khóa hiện hành của Worker. Yêu cầu kết nối nhỏ trả HTTP 200; đối tượng JSON nhỏ đạt schema. Ca intent tiếng Việt thiếu nguồn trả đúng `CLARIFY` qua validator. Bảng tổng hợp hai cột trả hai trường hợp lệ. Trong luồng trình duyệt với ba tệp, intent đạt và bước ánh xạ đầu tiên trả 503. Bản sửa loại schema lặp khỏi prompt ánh xạ. Trên cùng profile nguồn 01, kích thước request đo được giảm 10.747 → 8.455 byte, schema 2.107 byte, output limit 6.000 tokens, timeout 45 giây. Bản sau sửa vẫn trả HTTP 503 `UNAVAILABLE` trong 4,007 giây. HTTP response đã nhận, không có request ID được gửi qua hai header được hỗ trợ. Phép đo này chưa tách được nguyên nhân bên trong nhà cung cấp. HTTP 429 trong lịch sử là tín hiệu giới hạn từ nhà cung cấp, mức quota hoặc billing cụ thể chưa được xác minh. [Tài liệu xử lý lỗi Gemini](https://ai.google.dev/gemini-api/docs/troubleshooting).

Gateway ghi metadata của request và receipt đã lọc, giữ giới hạn một attempt của các job Agent. Tuyến cũ có thể thử lại lỗi kết nối trước khi gửi hoặc lỗi HTTP tạm thời đã nhận trong giới hạn đã cấp. Lỗi kiểm chứng nội dung và delivery chưa rõ không được thử lại tự động. Schema Pydantic, validation nghiệp vụ và quyền phê duyệt tiếp tục áp dụng.

Đợt chẩn đoán có 7 attempts Gemini qua ledger, 5 HTTP 200 và 2 HTTP 503. Tổng receipt 19.524 tokens, gồm 19.011 đầu vào và 513 đầu ra. Request kết nối HTTP 200 trả nội dung khác giá trị mong đợi, nên chỉ dùng làm bằng chứng kết nối. Chi phí hóa đơn chưa xác minh.

### Nghiệm thu lại Qwen 8B

Windows Ollama 0.40.9, AMD Ryzen 5 7535HS (6 nhân, 12 luồng), RAM vật lý khoảng 15,3 GiB, NVIDIA RTX 3050 6 GiB (driver 617.42), Windows Docker Desktop WSL2. Tại các lần lấy mẫu, RAM khả dụng khoảng 0,4–1,0 GiB và VRAM khả dụng khoảng 5,9 GiB. Ollama nghe loopback 11434, cache model hiện có trong thư mục người dùng Windows. Backend và Worker truy cập được endpoint qua `host.docker.internal`. Tag `qwen3:8b` có digest `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`, Q4_K_M, 5,23 GB.

| Phép đo LIVE | Kết quả |
| --- | --- |
| Hai lần nạp đầu | Timeout tại 65 và 100 giây |
| Nghiệm thu lại 4.096 context | 3/3 câu intent đơn giản đúng và hợp lệ JSON. Cold 28,188 giây (nạp 15,047 giây, token đầu 15,579 giây). Warm 1,344 và 1,437 giây (token đầu 0,391 và 0,515 giây) |
| Tốc độ và bộ nhớ khi nạp thành công | Warm khoảng 9,8–10,6 token/giây. Ollama báo 5,99 GB model resident, 4,21 GB VRAM tại 4.096 context. Ở 8.192, `ollama ps` báo 6,6 GB và offload 37% CPU/63% GPU. Đây là số đo khi model đang nạp, chưa đo peak toàn máy |
| Intent Agent ba nguồn | Hợp đồng ban đầu trả `UNSUPPORTED` sai sau 27,675 giây. Bản giảm schema lặp trả JSON nhưng bị validator từ chối `AI_INVALID_INTENT` sau 56,090 giây |
| Ánh xạ ba nguồn | 0/3 hoàn tất ở mỗi vòng, trước và sau thay đổi envelope cho Ollama. Các lượt riêng từng nguồn chạm khoảng 95 giây. Không có ánh xạ đạt để đo độ chính xác hoặc đưa vào phê duyệt |
| Chat thật trên Docker sau triển khai | Job `d4f275d9-863f-4f34-a06d-c4a2257c5cb5` chọn đúng `PREPARE_NORMALIZATION` và cả ba nguồn sau 45,740 giây. Job đề xuất `2c8c1a83-0f5e-4c53-b87e-7ec951cb57c0` hết thời gian sau 90,187 giây. Luồng BLOCKED, 0 thẻ duyệt. Cả hai trace là OLLAMA với 0 lượt cloud, ledger Gemini giữ 356 |
| Qwen 27B | Tag chính thức tồn tại và có bản tải khoảng 18 GB. Chưa cài trên máy này. Tải và nạp để benchmark được hoãn do thiếu RAM khả dụng và yêu cầu bảo toàn dịch vụ đang chạy. [Tag Qwen 27B](https://ollama.com/library/qwen3.8:27b) |

Qwen 8B chỉ dùng để thử nghiệm. Các số đo JSON nhỏ không đại diện cho Planner, Q&A hay độ chính xác ánh xạ. Chưa có quy trình AI local hoàn chỉnh đủ điều kiện để đo lại hai cặp đối soát. Các ca local sử dụng cấu hình `LOCAL_ONLY` ở hợp đồng thử, với adapter Ollama báo `cloud_requests=0`.

### Tích hợp và kiểm thử

Thêm lựa chọn model ngay cạnh nút gửi. API theo phiên đọc các tag đã cài và trace mà không thực hiện inference. Khi gửi, job giữ model được chọn và các bước con dùng cùng lựa chọn. Thay model giữ hội thoại, bản nháp, phạm vi dữ liệu và yêu cầu đã xếp hàng. Khi không rõ một lần gửi đã được nhận, UI giữ mã và payload cũ cho đúng yêu cầu đó. Ollama dùng cùng validator với Gemini. Lịch sử và các cổng phê duyệt không thay đổi.

Bản dựng thử qua Playwright tại 390 px đã kiểm chuyển model khi job đang chạy, bản nháp, reload, đúng payload và số lần gửi. Adapter được kiểm riêng với mock transport cho JSON, timeout, phản hồi thiếu và tag cloud bị từ chối. Test PostgreSQL mô phỏng routing xác nhận chọn Qwen không tạo reservation Gemini, cùng idempotency key không đổi được provider, và policy chặn Gemini khi cloud bị tắt.

Backend/PostgreSQL trên image triển khai **440/440**. Có một cảnh báo deprecation Starlette TestClient. Ruff, mypy, TypeScript, ESLint, build và kiểm tra link Markdown đạt. Sau deploy, mở lại đúng hai lần chạy ở mục AF và kiểm lại snapshot, bảng, biểu đồ, bằng chứng. Các file xuất của hai lần chạy đã được đối chiếu độc lập ở mục AF. Phép đọc lại dùng kết quả nghiệp vụ đã có, tách khỏi kiểm thử LIVE tạo đề xuất của Qwen.

Playwright đầy đủ trên Frontend `fb225fe` có **138/139** ca đạt. Ca còn lại phát hiện placeholder xuống dòng làm ô Chat rỗng cao 82 px ở màn hình 390 px. `729821e` giữ ô rỗng cao 58 px và tiếp tục giãn khi nhập nhiều dòng. Chạy lại **12/12** ca liên quan trên Docker hiện hành, gồm ca từng lỗi, bố cục 390–1920 px, nhập bằng IME, đổi model khi có job và tải lại. Bộ đầy đủ không chạy lại sau thay đổi chiều cao này.

Backup `backup_3d91f44503674f01946a3824bd5f5fc8` giữ trên volume. Đã khôi phục thử trong schema riêng và đối chiếu 24 bảng cùng SHA-256 của 5.552 tệp sau triển khai. Không thiếu hoặc thay đổi dữ liệu đã sao lưu. Các lần cập nhật Docker đều đạt snapshot/verify. Backend và Worker chạy `5373cf7`, image `sha256:ec4e1da3ea379d35cef0480fc6205230865176cc88d0b295e7b6f78291d1b9da`. Frontend chạy `729821e`, image `sha256:8bf23dc215d58ae534c27285e0c9fcc4e058a067bb58087d1140b128b9dc4346`. Đã đối chiếu 45 tệp Python và 7 tệp Frontend phục vụ qua HTTP với source đã dựng. Bốn dịch vụ Studio healthy, giao diện và Ollama bind loopback. Sáu dịch vụ Langfuse healthy, 27 container ngoài Studio và danh sách volumes giữ nguyên. [Ảnh bộ chọn](images/user-guide/composer-model.png).

### Bắt đầu thử

Mở [Studio local](http://127.0.0.1:18180) và dùng mục 14 của [hướng dẫn sử dụng](USER_TEST_GUIDE.md). Dùng Qwen 8B để thử các câu tổng hợp đơn giản khi thấy lựa chọn. Nếu cần chuẩn hóa ba tệp để đối soát, dùng luồng thủ công đã được kiểm tại mục AF và mục 13 của hướng dẫn. Trạng thái AI tự động vẫn chưa đạt gate để hợp nhất `main`.

## AH. Khôi phục Smart Mapping với Qwen local — 05/11/2026

### A. Kết luận và phạm vi nghiệm thu

Đã có một đường LIVE từ câu tiếng Việt kèm ba tệp → ba đề xuất Qwen → kiểm tra Backend → chỉnh/xác nhận trên UI → chuẩn hóa → hai hợp đồng đối soát duyệt thủ công → kết quả verified → biểu đồ/bằng chứng/CSV/XLSX → mở lại sau recreate. Gemini vẫn **INTERMITTENT**, dừng chẩn đoán cloud. Qwen là mặc định của phiên local chưa có lựa chọn cá nhân, tiếp tục hiện **Chưa kiểm chứng** cho AI tổng thể. Grain/khóa vẫn cần sửa; không công bố mapping chính xác hoàn toàn hoặc Agent tổng quát đã đạt. Mục này cập nhật hiện trạng sau AG, không thay lịch sử bằng chứng ở các mục trước.

Intent của lệnh chuẩn hóa explicit kèm tệp được resolver hữu hạn trên Backend xác định, có kiểm toàn câu, phủ định và exact scope. Qwen LIVE thực hiện phần đề xuất ngữ nghĩa từng bảng. Hai hợp đồng đối soát của lượt này do người kiểm thử lập và duyệt trên UI; chưa nghiệm thu Qwen Planner bằng lượt này. Không gọi model để tính tiền hoặc tự duyệt.

### B. Gemini với khóa cấu hình mới

Ban đầu container chưa khớp khóa trong cấu hình. Sau cập nhật theo quy trình snapshot/start/verify, Backend và Worker đều có khóa và khớp cấu hình; không công bố giá trị hoặc hash khóa. HTTP 200 xác nhận khóa được chấp nhận ở những lượt thành công. Model giữ `gemini-3.5-flash-lite`, REST GenerateContent v1beta qua httpx 0.28.1, không thêm Google SDK hoặc retry ngầm. Các nguồn chính thức và ranh giới API tại [AI Integration](AI_INTEGRATION.md).

| Phép thử mới | HTTP / thời gian | Kết luận đúng phạm vi |
| --- | --- | --- |
| Kết nối ngắn | 200 / 0,882 giây | Nội dung khác giá trị diagnostic mong đợi; chỉ PASS kết nối |
| JSON Schema nhỏ, 118 byte schema | 503 UNAVAILABLE / 10,653 giây | Không có output để kiểm JSON |
| Đề xuất riêng nguồn 01 | 200 / 9,837 giây | Đủ 9 cột, typed validation đạt; chưa xuất bản proposal trên UI |
| Intent qua Chat thật, ba tệp | 200 / 3,453 giây | Đúng PREPARE_NORMALIZATION và ba nguồn |
| Bước mapping đầu của Chat thật | 503 UNAVAILABLE / 1,325 giây | Workflow BLOCKED, 0 thẻ duyệt; không resend |

Tổng **5 HTTP attempts mới: 3 × 200, 2 × 503, 0 × 401/403/429**. Ledger giữ toàn bộ history, tăng **356 → 361**, không reset. Ba receipt có token: **14.353 tổng**, **12.889 đầu vào**, **1.464 đầu ra**; hai lỗi không có token receipt. Billed cost, quota và billing Google project **chưa xác minh**. Mỗi Agent job giữ một attempt. Lượt thất bại cuối có `delivery_unknown=false`, đã nhận phản hồi HTTP, không có request ID qua các header được hỗ trợ.

Request riêng nguồn 01 là 8.455 byte, schema 2.107 byte; request mapping trong workflow là 15.455 byte do ngữ cảnh có phạm vi. JSON nhỏ 424 byte vẫn nhận 503, trong khi đề xuất 8.455 byte nhận 200. Vì vậy kích thước hoặc độ phức tạp schema đơn thuần không giải thích được kết quả. Tài liệu Google mô tả 503 là dịch vụ quá tải/không khả dụng, 429 là giới hạn; không có bằng chứng để quy lỗi vòng này cho khóa sai, hết quota hoặc schema bị từ chối. Không thể xác định nguyên nhân nội bộ Google chỉ từ receipt này. Dừng Gemini sau lỗi workflow theo chỉ thị chủ dự án.

### C. Cách sửa và số đo Qwen

Giữ Ollama 0.40.9, tag `qwen3:8b`, digest `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`, Q4_K_M 5,23 GB trên Windows. Giữ context 8.192 và timeout ứng dụng 90 giây. Không tải 27B, thêm Gateway/service/dependency hoặc đổi Matcher, Verifier, compiler và công thức tiền.

Backend tạo đầy đủ các trường từ profile, giữ mã định danh dạng chuỗi và gợi ý kiểu ngày/tiền bằng dữ kiện toàn cột. Model chỉ trả entity, grain, mã cột khóa và nghĩa gross/net/fee. Dynamic JSON Schema chỉ cho tham chiếu cột có trong bảng; Backend tiếp tục kiểm cột sai/trùng. Unknown grain không được giữ khóa đoán. Amount chung vẫn chờ nghĩa tiền; timezone không suy từ date-only; currency hỗn hợp tiếp tục cảnh báo. Tên tệp/sheet là ngữ cảnh giới hạn và không đáng tin. Không hardcode ba tên tệp vào code ứng dụng.

Lượt trước tối ưu trong cùng nhiệm vụ có full router trả AI_INVALID_INTENT sau 80,473 giây. Sau khi gắn scope đính kèm và resolver explicit, một mapping còn bị chặn INVALID_SOURCE_FIELD. Sau bổ sung enum cột, phép gọi riêng ba nguồn đạt typed validation trong 7,151 / 13,031 / 19,185 giây (diagnostic timeout 95 giây; tách khỏi cấu hình ứng dụng 90 giây). Các receipt lỗi được giữ, không tính là PASS.

Trên **Docker/UI thật ở source `a268abe`**, ba mapping đều VALIDATED, không timeout:

| Nguồn | Tổng thời gian | Load / prefill / decode | Prompt / output tokens |
| --- | ---: | --- | ---: |
| 03 · Sao kê, gọi đầu sau nạp lại | 31,337 giây | 12,072 / 1,609 / 17,529 giây | 543 / 122 |
| 01 · Đơn dự kiến | 9,350 giây | 0,008 / 0,600 / 8,606 giây | 516 / 63 |
| 02 · Thanh toán | 13,187 giây | 0,006 / 0,759 / 12,296 giây | 577 / 92 |

Ba lần gọi tổng 53,874 giây, request khoảng 3,3–3,5 KB, tổng 1.636 prompt và 277 output tokens, **0 cloud requests**; intent explicit không cần inference. Decode khoảng 7,0–7,5 token/giây. Không đo trực tiếp thời gian token đầu vì API không streaming. Mẫu phần cứng 60 lần từ 16:15:53 đến 16:18:18 UTC+7, bao quanh lượt này: VRAM dùng cao nhất quan sát 4.111 MiB, RAM khả dụng thấp nhất 250 MiB. Đây là cửa sổ lấy mẫu, không phải peak toàn phiên hoặc benchmark tải đồng thời. Máy RTX 3050 6 GiB/RAM khoảng 15,3 GiB còn áp lực RAM; tốc độ có thể khác khi mở thêm ứng dụng.

### D. Chất lượng đề xuất và quyết định người dùng

Project TEST `510a220a-2e94-46be-9537-0940a115fa8b`, workflow `b1b20284-2bcf-55ad-b9db-aea28f206d60`. Ba nguồn có đủ 9/11/10 trường, đúng kiểu trong bộ thử; phần tạo kiểu là Backend profiling, không phải chỉ số độ chính xác Qwen. Cả ba output đúng schema và tham chiếu, nhưng còn khác nghiệp vụ:

- Nguồn 01 trả grain unknown và chưa có khóa; người kiểm thử xác nhận order, scope + reference.
- Nguồn 02 nhận diện sự kiện thanh toán, gợi ý payment_id + scope; người kiểm thử giữ payment_id làm khóa chuẩn hóa.
- Nguồn 03 mô tả giao dịch trong lô và chọn settlement_id + scope; cần sửa grain settlement_batch và khóa scope + batch_id.
- Hai cột amount chung không có nghĩa tiền; phải xác nhận reported_gross_amount/gross theo bộ thử. Nguồn 03 gợi ý gross/net theo header, fee vẫn cần basis; thống nhất metric gross để so hai nguồn. Cả ba nguồn xác nhận VND, đơn vị VND, en-US và UTC; không đổi currency trong raw hoặc biến EXPECTED thành PAID.

Đã sửa và bấm **Duyệt cách ghép cột và chuẩn hóa** riêng từng nguồn qua UI. Có đúng ba quyết định, model không tự duyệt. Backend kiểm toàn bảng trước và tại lúc duyệt. Trường required của Chat không bị hạ để khớp số liệu tham chiếu.

| Nguồn | Dòng | Hợp lệ / cần kiểm tra, bản Chat | Bản thủ công tham chiếu | Giải thích chênh lệch |
| --- | ---: | ---: | ---: | --- |
| 01 | 2.418 | 2.406 / 12 | 2.408 / 10 | Khóa reference required: thêm 2 dòng thiếu mã |
| 02 | 2.685 | 2.674 / 11 | 2.674 / 11 | Khóa payment_id không thiếu |
| 03 | 384 | 378 / 6 | 380 / 4 | Khóa batch_id required: thêm 2 dòng thiếu mã |
| Tổng | 5.487 | 5.458 / 29 | 5.462 / 25 | Cấu hình required khác nhau, không thay oracle cũ |

Oracle độc lập đọc raw CSV/openpyxl, datetime và Decimal trước khi duyệt xác nhận đúng 4 dòng thêm do khóa bắt buộc; không đổi expected tùy tiện. Đối chiếu canonical sau chạy: đủ từng dòng và provenance, giữ ID/số 0 đầu, tiền Decimal, ngày hợp lệ và NULL/invalid. Lỗi ngày thật vẫn 2/5/0. Cả 29 dòng cần kiểm tra thuộc EDGE_CASE; MAIN_VND không có dòng lỗi. Workflow kết thúc **PARTIAL** đúng với nguồn chứa lỗi, không giả COMPLETED sạch.

![Đề xuất Qwen LIVE trên giao diện trước khi duyệt](images/user-guide/qwen-mapping-live.png)

![Mở lại luồng Qwen sau khi duyệt ba nguồn và cập nhật cấu hình](images/user-guide/qwen-mapping-completed.png)

### E. Đối soát, analytics và tệp xuất mới

Hai run mới dùng canonical vừa tạo, hợp đồng riêng MAIN_VND, VND, UTC, `[2026-10-01, 2026-11-01)`, SUM_SIGNED, sai số 0; người kiểm thử xác nhận scope/coverage và quy tắc trên UI. Cả hai **PARTIAL_VERIFIED** vì bộ thử còn nhóm không đủ điều kiện; không gọi là VERIFIED toàn bộ.

| Run mới | Quan hệ / khóa | Khớp | Lệch | Thiếu trái / phải | Tổng lệch có dấu / tuyệt đối |
| --- | --- | ---: | ---: | ---: | ---: |
| `9c0e90cd-0285-4778-94c2-419072d858df` | 01 ↔ 02, 1:N, scope + reference | 2.040 | 200 | 160 / 55 | 7.867 / 60.883 VND |
| `376d4447-2d6a-4e61-9654-3516b17fac36` | 02 ↔ 03, N:1, scope + batch_id, gross | 323 | 40 | 18 / 13 | −8.306 / 11.812 VND |

Oracle nghiệp vụ độc lập giữ nguyên từ raw, không dùng Matcher/Verifier hoặc sửa đáp án. Đã kiểm từng khóa, tiền trái/phải và delta của cả **240 nhóm lệch**. Màn hình/bảng/biểu đồ và typed query cùng run; mở đúng nhóm thứ hai, đầy đủ nguồn, reload không đổi snapshot. CSV và XLSX mới đã tải và đọc lại, mọi ô nghiệp vụ giữa hai định dạng khớp (thời điểm tạo mỗi file khác nhau hợp lệ). KPI và monetary snapshot khớp API; 0 ô công thức; giữ số âm và số 0 đầu. Hai báo cáo có 5.103/3.069 dòng bằng chứng và 51.297/33.375 ô nguồn.

### F. So sánh và mức sử dụng

| Tiêu chí LIVE của vòng này | Gemini | Qwen 8B |
| --- | --- | --- |
| Kết nối | Có 200 nhưng xen 503 | Ollama local hoạt động |
| Intent ba nguồn | Đúng qua model | Resolver explicit exact-scope; full router trước sửa từng bị chặn |
| JSON/schema | Một bảng đạt, JSON nhỏ gặp 503 | 3/3 output cuối đạt cấu trúc/tham chiếu |
| Một nguồn | 01 đạt typed diagnostic, chưa duyệt UI | Cả ba nguồn có lượt riêng đạt |
| Ba nguồn trên UI | BLOCKED, 0 proposal | 3 thẻ, 3 quyết định, chuẩn hóa hoàn tất ở PARTIAL |
| Chất lượng ngữ nghĩa | Chưa đủ workflow để đo | Cần chỉnh grain/khóa, xác nhận tiền và múi giờ |
| Thời gian | Single 9,837 giây; workflow mapping lỗi 1,325 giây | Mapping UI 9,350–31,337 giây, tổng 53,874 giây |
| Lỗi provider | 2/5 attempts 503 trong vòng giới hạn | 0 timeout trong ba mapping UI cuối; lỗi router/tham chiếu của các candidate được giữ |
| Khuyến nghị | Giữ lựa chọn, chưa coi ổn định; không gọi tiếp vòng này | Có thể tiếp tục TEST local với review; chưa đủ live gold để công bố AI tổng quát |

Không có tỷ lệ mapping precision/recall đã hiệu chỉnh từ bộ ba tệp. Dùng lại chính ba tệp để tối ưu không thay được tập đánh giá độc lập. Không extrapolate ba JSON thành Planner/NLP chính xác hoặc tốc độ mọi workload. Chưa đạt cổng AI tổng thể để merge main.

### G. Kiểm thử, bảo toàn và đồng bộ

Backend/PostgreSQL toàn bộ trên image triển khai: **449/449**, 194,44 giây; một cảnh báo deprecation Starlette TestClient, không thêm dependency để che cảnh báo. Ruff, mypy (50 source files), TypeScript, ESLint và production build đạt. Có regression cho scope tệp gắn tin nhắn, phủ định/multitask, cột sai/trùng, unknown grain, bảo toàn thẻ nguồn trước khi nguồn sau lỗi, idempotency và model-bound pending request. Các ca provider/security trong bộ tự động dùng mock; lượt Qwen/Gemini LIVE được báo riêng ở trên.

Playwright **139/139** trên bản Docker cuối, **13,0 phút**, một worker, không retry hoặc bỏ case. Gồm composer/IME/scroll, chọn model và giữ payload, mapping/preflight, History/Settings, responsive 390–1920 px, auth/isolation, upload sai/quá lớn, manual fallback và oracle/export qua nhiều bộ khác ngành. LIVE local và MOCK AI được ghi ngay tên ca; bộ tự động không thay phép đánh giá AI LIVE. Ledger Gemini sau toàn bộ test vẫn 361, không có inference cloud mới. Không sửa application source sau lượt full regression này.

Backup `backup_68c1884e375d4fe98477cf9482578ad8` trên volume: sao lưu 46,007 giây, restore thử trong schema riêng 42,558 giây. Kiểm bảo toàn sau triển khai: đủ bản ghi cũ trong **24 bảng**, giá trị không đổi, **5.711 tệp** khớp checksum. Bản ghi TEST mới là phần thêm; giữ raw, approvals, các canonical/runs cũ và ledger. Mỗi lần cập nhật key/code/default local đều snapshot/start/verify; sau recreate, đọc lại hai run mới, biểu đồ/bằng chứng và snapshot đạt. Không migration hoặc sửa database schema nghiệp vụ.

Backend, Worker và Frontend cùng revision **`a268abecd21c9eed76c06bc1816c8767f406e3f7`**. Backend/Worker image `sha256:0462a566d40227172850e1a52f40414e6615a93636161f527477c13e4095b0bd`; Frontend `sha256:5226dd8c8bd193f9cbb9e4607a4cd78fbb59bc8a496c5279208acb85495fec0c`. Đối chiếu đủ 45 file Python với host và hai container, 7 file Frontend giữa bản dựng/image/HTTP. Bốn dịch vụ healthy, 0 OOM/restart, cổng ứng dụng chỉ loopback; lần kiểm cuối 0 job QUEUED/RUNNING. Phiên mới đã kiểm chọn Qwen 8B; lựa chọn cá nhân được bảo toàn theo regression và job cũ giữ model ban đầu.

Kiểm kê có đúng 4 container Studio, 2 image hiện hành (Frontend khoảng 24,7 MiB, Backend khoảng 149,1 MiB), 8 image giữ các cặp rollback có nhãn. Không có container Studio dư hoặc image không còn tham chiếu đủ điều kiện xóa; không xóa bản khôi phục chỉ vì hiện không chạy. 27 container ngoài Studio giữ nguyên ID/image/mounts; danh sách 36 volume toàn host không đổi. Sáu dịch vụ Langfuse healthy, project `langfuse` độc lập. Giữ hai volume Studio, backups và cache dùng chung; không global prune.

Các commit ứng dụng đã push origin chính thức trên `codex/product-polish`: `759500c` (profile + semantic draft và recovery), `89320d9` (scope tệp và resolver explicit), `a268abe` (enum tham chiếu và mặc định model). Các thay đổi sau đó chỉ cập nhật tài liệu/ảnh, không thay application bytes đã kiểm thử. Main giữ **`a4f70b289b935b11928e6d1c2b2e0748160fbfa1`**; chưa merge vì full live gold NLP/Planner và độ chính xác mapping tổng thể chưa đạt. Sẵn sàng tiếp tục kiểm thử local có người duyệt trong phạm vi đã đo; chưa đủ cơ sở phát hành toàn bộ AI Agent hoặc cam kết không còn lỗi.

### H. Bắt đầu thử tiếp

Mở [Studio local](http://127.0.0.1:18180), theo [hướng dẫn mục 14–15](USER_TEST_GUIDE.md#14-chọn-model-trong-ô-chat). Phiên chưa lưu lựa chọn chọn Qwen 8B; lựa chọn cá nhân cũ được giữ. Model của job đã gửi không đổi khi chuyển bộ chọn. Tải ba tệp vào dự án TEST, dùng câu chuẩn hóa explicit kèm tệp, kiểm đủ ba thẻ và duyệt từng nguồn sau khi đọc cảnh báo. Không bấm gửi lại khi delivery chưa rõ; nếu provider lỗi, đọc thông báo và dùng đường thủ công. Không có fallback sang Gemini tự động.
