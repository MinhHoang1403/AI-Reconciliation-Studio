# AI Reconciliation Studio

Không gian đối soát CSV/XLSX bằng hội thoại: tải tệp, chuẩn hóa, duyệt quy tắc, tra cứu và phân tích kết quả có bằng chứng. Backend tính tiền bằng Decimal, kiểm chứng độc lập và lưu dữ liệu/hội thoại trong PostgreSQL/Parquet.

Composer trung tính, bo tròn và không khung ngoài khi click chuột; Tab có chỉ báo focus mảnh. Ô nhập tự giãn theo nội dung và độ rộng; Enter gửi, Shift+Enter xuống dòng. Cài đặt, lịch sử, review, bảng và evidence dùng cùng giao diện tối giản; trạng thái/quyền/giới hạn lấy từ Backend. Trạng thái được cấp quyền AI và đã cấu hình không chứng minh model đang kết nối.

**Nghiệm thu hiện hành 04/11/2026 — READY_FOR_GUIDED_DEMO:** **302 Backend/PostgreSQL và 117 Playwright PASS sau Docker cleanup**, thêm8checks sau deploy đãPASS trước cleanup. Frontend `18706a7` là bản giao diện mới, Backend/Worker giữDAC với42source files khớp;7HTML/assets host/image/HTTP và Chromium đều khớp. Đủ4dịch vụ healthy, dữ liệu gốc24bảng/2.709checksums không đổi, backup/restore đã kiểm. Xem [báo cáo giao diện và hiện trạng mục Z](docs/IMPLEMENTATION_STATUS.md#z-giao-diện-tối-giản-sourceruntime-và-docker-cleanup--04112026); bằng chứng AI trước đó và giới hạn tại mụcY vẫn áp dụng. Có thể dùng local cho luồng CSV/XLSX đã nghiệm thu; chưa nghiệm thu Internet/nhiều người dùng hoặc bảo đảm mọi câu ngôn ngữ tự nhiên đều đúng. Gemini còn7lượt tổng, không inference mới/tăng quota/reset ledger trong nhiệm vụ UI. Đã bỏ8image cũ, giữ release/rollbackDAC/PG/volumes/backups; không global prune. Số tests/các checks replay không cộng thành cases mới.

## Mở ứng dụng trong workspace hiện tại

Ứng dụng tại [http://127.0.0.1:18180](http://127.0.0.1:18180). Không nhập token trên giao diện.

Từ PowerShell tại repository root:

```powershell
./tools/start.ps1
```

Script tạo `.env` với credentials local ngẫu nhiên nếu chưa có, build/up đúng một Compose project, đợi healthchecks rồi xác minh published ports thực tế. Không ghi đè `.env` hiện có. Nếu Docker đã build và chỉ cần mở lại:

```powershell
./tools/start.ps1 -SkipBuild
```

Máy đã kiểm tra: Windows, Ryzen 5 7535HS (6 cores/12 threads), khoảng 16 GB RAM; Docker Desktop/Linux Engine 29.7.2, Compose 5.5.0. Chỉ cần Docker để chạy ứng dụng; Node/Python local dùng cho phát triển và tests. Cổng `18180` phải còn trống. Backend/worker/PostgreSQL không publish host ports.

## AI Assistant có bằng chứng

Mở **AI Assistant** → đính kèm 1–5 CSV/XLSX → giao việc bằng tiếng Việt → kiểm tra điểm cần xác nhận → nhận kết quả và nguồn. Khi chưa chọn project, upload tạo scope `UNCONFIRMED` riêng, không tự dùng quy tắc khác. Mapping/rule mới vẫn cần quyết định người dùng; rule đã duyệt đúng phạm vi có thể chạy lại theo yêu cầu rõ ràng. Kết quả query/raw/canonical và KPI verified được phân biệt, LLM không tính tiền.

Sidebar chỉ **AI Assistant / Lịch sử / Cài đặt**. **Tệp đã tải** mở dữ liệu gốc/chuẩn hóa/lỗi/tải raw ngay trong chat; kết quả mở bảng chi tiết dùng đúng run. Các màn hình thủ công nằm trong fallback theo ngữ cảnh. UI đã kiểm tra 23 trạng thái tại 390/768/1366/1440/1920: lịch sử mở bằng nút **Lịch sử**, ngữ cảnh kết quả mở từ chip, xóa trong menu hội thoại. Reply dùng composer chính: dữ kiện đủ và truy vấn an toàn tiếp tục cùng workflow; mapping/rule mới vẫn cần duyệt riêng. Luồng manual/facts cũ vẫn qua các trang chi tiết và chế độ **Chỉ hỏi dữ kiện đã xác minh**. Hội thoại có owner/project và run refs; drafts lưu sessionStorage riêng theo actor/context/conversation, đóng tab có thể mất draft. Dữ liệu persisted không phụ thuộc drafts.

Source cài mới mặc định cloud OFF/0 cho Agent và Assistant. Chủ dự án đã cho phép demo bật Agent, Assistant cloud, parser và Qwen; theo chỉ dẫn tiếp tục03/11, global/workspace lifetime ceiling210, Agent193, Planner30, Assistant20. Không reset ledger; Cài đặt hiển thị remaining thực tại lúc mở, gồm giới hạn task và tổng. Qwen mapping synthetic đã PASS LIVE trên host và Docker; Gemini vẫn là provider mapping mặc định. LlamaParse mới vẫn bị ràng buộc allowance2tài liệu và SHA allowlist, đã dùng2/2; đọc lại PDF/DOCX đã lưu hoạt động, không tạo job mới. Argon chưa tích hợp. Đọc dữ liệu/polling/layout không tự gọi model.

Với dữ liệu đã chọn, có thể thử các câu: `Chuẩn hóa các file này giúp tôi`; `Liệt kê giao dịch đã thanh toán ở file A`; `Vì sao giao dịch 000702 không khớp?`. Cần đủ nguồn/quyền/ngữ nghĩa đã xác nhận. Tên nguồn A/B chỉ được rút gọn khi có alias duy nhất từ tên tệp; nguồn chưa rõ vẫn hỏi bổ sung. Kết quả benchmark không bảo đảm mọi câu ngoài tập kiểm tra đều đúng.

## Vận hành và khôi phục

```powershell
docker compose stop
./tools/start.ps1 -SkipBuild
docker compose restart
./tools/verify-local.ps1
docker compose up -d --force-recreate --wait
./tools/verify-local.ps1
```

Không dùng `down -v`, prune volumes hoặc tạo Compose project khác. Sau recreate, local demo bị khóa cho đến khi xác minh đúng published loopback ports; HTTP 403 ở bước này không phải lý do bỏ auth/CSRF.

Backup/restore drill, trong lúc không có jobs hoặc thao tác ghi từ giao diện:

```powershell
docker compose cp tools/check-backup-restore.py backend:/tmp/check-backup-restore.py
docker compose exec -T backend python /tmp/check-backup-restore.py
```

Tool dùng transaction PostgreSQL `REPEATABLE READ`, chụp metadata và copy mọi file đã được công bố theo DB refs/checksum; từ chối nếu metadata đổi hoặc jobs đang chạy. Backup giữ tại `/var/lib/studio/backups/backup_<UUID>/`, ngoài Git/image. Restore drill tạo schema UUID trong PostgreSQL hiện có, kiểm đủ metadata/artifacts rồi chỉ bỏ schema/copy do drill tạo; không overwrite public. Tool không phục hồi production tự động. Receipt ghi counts, schema, hashes, thời gian và lỗi checksum/path. Cơ sở: [PostgreSQL transaction isolation](https://www.postgresql.org/docs/18/transaction-iso.html).

Copy cả thư mục backup theo ID được trả về ra host bằng `docker compose cp backend:/var/lib/studio/backups/backup_<UUID> runtime/backups/`, sau đó lưu bản sao mã hóa/off-host và cấu hình bí mật riêng theo quyền vận hành. Bản trên cùng volume hoặc GitHub không thay backup độc lập. Khôi phục production cần chọn backup đã xác minh và kế hoạch quyền/cấu hình riêng; chưa có thao tác tự ghi đè DB thật.

Để quay lại bộ image đã giữ cho rollback: `./tools/rollback.ps1 -ReleaseRevision dac8dd1` (cũng là mặc định hiện hành). Script kiểm source/labels, schema additive tương thích và không có job active; dùng cùng Compose/volumes, không downgrade. Override nằm ngoài Git tại `runtime/rollback-compose.json`; dùng cả hai file Compose khi vận hành bản rollback. `start.ps1 -SkipBuild` với Compose chuẩn quay lại release `local`. Chỉ dẫn cleanup ngày 04/11 cho phép bỏ những image cũ đã chứng minh không còn cần; luôn giữ cặp `accepted-main-dac8dd1`, release đang chạy, PostgreSQL và backups. Đây là demo loopback; chưa cấp quyền triển khai public/production.

## Cấu hình

Trải nghiệm hội thoại03/11: câu hỏi bổ sung dùng **Trả lời bằng tiếng Việt** hoặc lựa chọn đã kiểm tra, không checkbox phê duyệt. Mapping/quy tắc mới dùng **Duyệt ánh xạ và chuẩn hóa** / **Duyệt quy tắc và đối soát** sau khi đã xem ý nghĩa/phạm vi; cung cấp dữ kiện chưa cấp quyền phê duyệt. **Chi tiết xử lý** giữ các bước công việc; thông tin tin nhắn nằm dưới dấu ba chấm. Truy vấn tiền theo metric duy nhất của kết quả đã duyệt không bắt nhập tên kỹ thuật; nhiều metric thì hỏi lựa chọn. Kết quả, nguồn, export và lịch sử vẫn từ Backend có quyền truy cập.

[.env.example](.env.example) chứa placeholders, không chứa secret. `.env` không vào Git/image. Khi cài từ repository mới, đặt `QWEN_BASE_URL` trong `.env` theo [thông tin provider](docs/AI_INTEGRATION.md), model `knowledge`, không thêm API key Qwen. Sau khi đổi cấu hình, chạy lại `tools/start.ps1`.

Mặc định `LOCAL_DEMO_ACCESS=true`, Gemini/LlamaParse keys rỗng, cloud permissions false và request budgets bằng 0. Quyền workspace cũng mặc định `LOCAL_ONLY`; biến môi trường không tự cấp quyền cloud. Không tự chuyển provider khi Qwen lỗi.

Demo được cấp phép chọn `MAPPING_AI_PROVIDER=GEMINI`, `ALLOW_EXTERNAL_AI=true`, `EXTERNAL_AI_REQUEST_BUDGET=210`; key chỉ trong `.env`, workspace `CLOUD_ALLOWED` có cùng ceiling210. Đây là hạn mức nội bộ của ứng dụng, không thay quota/billing của Google. Mỗi HTTP attempt có reservation bền vững, kể cả lỗi; không reset khi restart. Không cộng lượt người dùng vào phép đo UAT của Codex: phân loại bằng job/workflow/trace refs, đồng thời giữ mọi lượt trong tổng ledger. Qwen đang bật và đã probe synthetic; không tự đổi provider. Parser có quyền, request/credit ceilings và SHA256 allowlist riêng; bật flag không mở phép xử lý tài liệu chưa được cấp allowance.

`docker compose up -d --build --wait` khởi động đủ bốn service. Sau lệnh này, chạy `./tools/verify-local.ps1` để kích hoạt auto-session local. Nếu chưa xác minh, `/api/session` trả 403; không tắt auth để vượt qua. Proof mất hiệu lực khi restart/recreate backend hoặc frontend. Chỉ hỗ trợ loopback demo; không publish LAN/Internet hoặc public reverse proxy.

## Chế độ thủ công và kiểm tra chi tiết

Luồng mặc định là upload/giao việc trong AI Assistant ở trên. Mở **Tệp đã tải → Kiểm tra thủ công khi cần → Mở kiểm tra và ánh xạ thủ công** để vào công cụ chi tiết. Các bước dưới đây là fallback khi cần kiểm tra hoặc AI chưa khả dụng.

Bộ chọn dự án mặc định ẩn nhóm **Kiểm thử**, vẫn giữ dự án **Chưa phân loại**. Bật “Hiển thị dự án kiểm thử” để mở lại; dự án đang chọn và dữ liệu không bị xóa hoặc đổi ngầm. Chủ không gian có thể mở “Phân loại dự án hiện tại”, kiểm tra tên/phạm vi/ID rồi xác nhận nhóm. “Dữ liệu gần đây” luôn lấy tối đa năm nguồn tải mới nhất, độc lập trang danh sách Dữ liệu.

1. Tạo dự án, nhập tên và phạm vi nghiệp vụ để kiểm soát tái sử dụng mapping.
   Bộ chọn có tìm kiếm theo tên/phạm vi, phân trang và hỗ trợ bàn phím ↑/↓/Enter/Escape; reload giữ project đã chọn kể cả ngoài trang đầu. Project mất quyền/không tồn tại được báo rõ để chọn lại. Dashboard phân biệt số nguồn, bảng cần xác nhận ánh xạ, kết quả READY và PARTIAL/đã cũ/thất bại. **Bước tiếp theo** mở đúng bảng/tab cần xử lý, không tự chạy job hoặc duyệt quy tắc.
2. Chọn **Tải dữ liệu**, thêm nhiều CSV/XLSX. Encoding/delimiter/header nằm trong tùy chọn nâng cao; UTF-8/BOM là mặc định.
   Có thể bỏ chọn “Dùng AI đề xuất ánh xạ trong hạn mức” để chỉ parse/profile và review thủ công, không enqueue AI hoặc tiêu quota. Quyết định này không thay đổi raw/parsed semantics; có thể yêu cầu đề xuất riêng về sau.
3. Mở nguồn và chọn sheet. **Khám phá dữ liệu** có phân trang/tìm kiếm phía server, thống kê và nguồn gốc.
4. Mở **AI Smart Setup**. Provider được chọn đề xuất ánh xạ; nếu bị chặn, thiếu key hoặc hết ngân sách, UI báo rõ và cho phép dùng shortlist/thủ công. Không hiển thị thành công AI giả.
5. Xác nhận loại dữ liệu, ý nghĩa mỗi dòng và từng trường cần dùng. Có thể giữ cột chuỗi tùy chỉnh. Với tiền, xác nhận locale, chỉ tiêu, gross/net hoặc định nghĩa riêng, currency và đơn vị; với ngày, chọn format/timezone rõ ràng. Cảnh báo công thức/vùng bảng cần được kiểm tra.
6. Bấm **Xác nhận ánh xạ**, rồi **Chuẩn hóa dữ liệu**. Khi job hoàn tất, bấm **Cập nhật kết quả** và **Xem kết quả**.
7. Dùng lớp **Cảnh báo / lỗi** để kiểm tra invalid/null và **Xem nguồn** để mở dòng gốc. Dữ liệu lỗi không bị thay bằng zero hoặc bỏ đi. Sửa mapping tạo revision mới, canonical cũ được đánh dấu đã cũ; raw/parsed được bảo toàn.
8. Mở lại trình duyệt, chọn dự án cũ để tiếp tục. Tệp cùng nội dung/config trong cùng dự án được reuse; mẫu đã duyệt chỉ được gợi ý trong scope tương thích.

PDF/DOCX mới cần allowance riêng được duyệt trước khi upload. Kết quả đã lưu có preview theo file/trang/bảng và luôn “chưa được xác minh”; không tự chuyển thành canonical hoặc suy ra kết luận tiền. Đọc lại kết quả không gọi provider. Assistant đã phát hành trên main được mô tả ở phần trên; kết quả live của provider không được suy từ câu trả lời xác định.

## Đối soát và báo cáo thủ công khi cần

Từ phần chế độ hội thoại, mở **Thiết lập đối soát thủ công**. Luồng chính vẫn là giao việc và xem kết quả ngay trong chat.

1. Sau khi có hai canonical trong cùng project, mở **Đối soát**, chọn nguồn tham chiếu/đối ứng.
2. Có thể dùng AI chuẩn bị gợi ý khóa/chỉ tiêu trước khi nhập rule đầy đủ khi được cấp phép, hoặc mở phần chỉnh thủ công. Thiếu kỳ/coverage phải xác nhận, gợi ý không cấp quyền chạy. Planner hiện tại đã qua một số ca live sau sửa contract, và full routing đã đạt gate ở mục T. Regression deterministic dùng MANUAL/MOCK; không gọi live khi hết quota.
3. Xác nhận khóa, quan hệ một-một/một-nhiều/nhiều-một, grain, metric/currency/basis, dấu tiền, kỳ `[start,end)`, timezone và coverage rồi **Kiểm tra điều kiện** và lưu đề xuất. Internal lọc đúng platform/shop cho từng pair, không JOIN ba nguồn. Manual không cloud; Gemini theo allowance hiện hành được cấp; không reset hoặc tự fallback khi lỗi. Không gọi Qwen/mở parser.
4. Review đề xuất, **Xác nhận quy tắc và dấu số tiền**, rồi **Chạy đối soát đã duyệt**. Duplicate/fuzzy mơ hồ giữ review, không tự chọn; null/invalid không thành zero. Coverage thiếu phải cho phép partial rõ ràng.
5. **Báo cáo/Tổng quan** hiển thị snapshot đã verified, denominator/CU/period và từng metric/currency riêng. Không có verified result thì empty/loading state, không KPI giả. Lọc lịch sử theo kỳ/nguồn, chọn đúng run ID.
6. **Ngoại lệ** có tìm kiếm, lọc loại/trạng thái, sort, bằng chứng hai bên và dòng nguồn. Resolve/dismiss cần ghi chú; review không sửa comparison, variance hoặc snapshot của run.
7. **Xuất CSV/XLSX** → **Tải báo cáo**. Hai định dạng dùng cùng snapshot; text chống formula injection, Decimal âm giữ numeric, IDs giữ zero-prefix. Excel arithmetic vẫn có giới hạn 15 significant digits; exact values có trong OOXML numeric lexemes/snapshot strings và CSV.
8. Mẫu đã duyệt có thể rebind nguồn/kỳ mới, kiểm schema/mapping/effective date và trở thành proposal phải duyệt lại. Nguồn stale không được chạy; lịch sử run cũ vẫn bất biến.

Chạy bộ demo có oracle trên dữ liệu tổng hợp, không gọi AI:

```powershell
uv run python tools/check-reconciliation.py
```

Công cụ tạo/reuse đúng một project demo, năm nguồn CSV và ba pair runs, kiểm oracle, lưu báo cáo tại runtime bị ignore. Planner prompt cũ có cả cached success và FAIL LIVE lịch sử; prompt hiện tại `reconciliation-planning-5` có ca PASS LIVE sau sửa, xem báo cáo mục S. Đọc cache không phải live mới; không chạy lại cloud chỉ để replay. `--planner-live` là lựa chọn explicit có quota guard/task cap, không phải regression mặc định.

## Vận hành và bảo toàn dữ liệu

```powershell
docker compose ps
docker compose logs --tail=100 backend worker
docker compose restart
./tools/verify-local.ps1
docker compose stop
```

Named volumes `ai-reconciliation-studio_postgres_data` và `ai-reconciliation-studio_artifacts` giữ metadata/raw/Parquet. Không chạy `down -v`, xóa volumes hoặc global prune. GitHub lưu source, không thay backup dữ liệu. Công cụ `./tools/check-persistence.ps1` kiểm tra restart và force-recreate trong project hiện tại, so metadata và checksum trước/sau, không xóa volumes.

## Thử bộ dữ liệu nghiệm thu mới

Bộ chọn dự án → bật **Hiển thị dự án kiểm thử** → tìm **DEMO UAT 1000 giao dịch**. Dự án tổng hợp đã có hai nguồn, mappings/rule được duyệt và run verified; Lịch sử mở lại hội thoại đã chạy. Có thể kiểm tra run cũ mà không gọi AI. Muốn kiểm thử độc lập, tạo dự án khác và đính kèm tệp trong `runtime/demo-acceptance/data/`; `tools/create-uat-fixtures.py` tái tạo fixture và đáp án cùng seed, không cần cloud.

Các câu đã chạy trên dự án demo: `Liệt kê các giao dịch đã thanh toán ở G 1000 giao dịch nguồn A.csv`; `Vẽ biểu đồ đếm toàn bộ giao dịch theo từng payment_status, không lọc bỏ trạng thái nào`; `Vì sao giao dịch GD-0000002 không khớp?`; `Xuất kết quả đối soát đang xem ra Excel`. Đáp án:686PAID,114COMPLETED,200UNPAID; tổng1000; giao dịchGD-0000002 có4479.17−4478.80=0.37VND; run966/1000khớp đủ,19lệch,15thiếu đối ứng, tổng lệch tuyệt đối7.03VND.

Khi liệt kê thiếu đối ứng hoặc lệch tiền, nêu rõ **chỉ tiêu reported_transaction_amount đã duyệt** nếu model chưa chọn được chỉ tiêu. Hai câu chung đã bị chặn an toàn trong UAT; câu có chỉ tiêu trả đúng15/19. Câu nối tiếp `Còn bên A thì sao?` có thể hỏi lại; ghi rõ thao tác/tệp khi được hỏi. Manual fallback, Ngoại lệ và báo cáo vẫn dùng được. Đây là giới hạn NLP được ghi nhận, không là bảo đảm hiểu mọi câu.

## Kiểm thử và phát triển

```powershell
uv sync --frozen
uv run pytest -q -m 'not integration'
uv run ruff check backend tests tools
uv run mypy backend
./tools/test-postgres.ps1
npm --prefix frontend ci
npm --prefix frontend run check
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend exec -- playwright install chromium
$env:STUDIO_EXPECT_AI_PROVIDER='MANUAL' # Regression mặc định không tiêu quota AI
npm --prefix frontend run test:e2e
uv run python tools/check_repository.py
```

Gemini E2E live chỉ khi explicit đặt `STUDIO_EXPECT_AI_PROVIDER=GEMINI`; có tiêu quota hiện hữu. LlamaParse không phải regression tự động: hai tài liệu thử đã lưu tại runtime và `tools/check-document-acceptance.py` đọc lại/reuse đúng refs. Không mở allowance hoặc tạo tài liệu/job khác chỉ để chạy lại tests.

PostgreSQL tests chạy trong schema UUID `test_*` của server hiện tại rồi dọn đúng schema tổng hợp đó; không dùng bảng dữ liệu ứng dụng hoặc Compose test project. Chi tiết, catalogue T01–T16, benchmark và trạng thái live/mock nằm trong [hướng dẫn kiểm thử](docs/TESTING_GUIDE.md).

Trong VS Code hoặc Antigravity IDE, mở đúng thư mục repository và chọn terminal **PowerShell (AI Reconciliation Studio)**. Workspace đặt terminal này làm mặc định để tránh dùng profile của dự án khác. Máy hiện tại có profile PowerShell 7/Windows PowerShell tự kích hoạt `.venv` khi vào repository hoặc thư mục con và tự tắt khi rời ra ngoài; profile cá nhân này không nằm trong Git. Trong dự án, `python -c "import sys; print(sys.executable)"` phải trỏ tới `.venv/Scripts/python.exe`, Python 3.12.14. Terminal cũ cần đóng/mở lại để nạp profile mới; máy khác cần cài dependencies theo hướng dẫn ở trên.

Workspace ưu tiên trình quản lý venv, dùng Ruff/mypy từ môi trường dự án, thêm `backend` vào đường dẫn phân tích và bỏ thư mục runtime/dependencies khỏi việc quét mã nguồn. Nếu IDE còn giữ lựa chọn cũ, dùng **Python: Select Interpreter → Enter interpreter path** và chọn `.venv\Scripts\python.exe`. Không đặt `${workspaceFolder}` vào đường dẫn interpreter dự phòng ở cấu hình người dùng: Python Environments của Antigravity hiện tại còn thử phân giải giá trị đó ở phạm vi toàn cục và báo lỗi.

Python nền trên máy này dùng chung tại `C:\Users\admin\.local\share\uv\python`; `UV_PYTHON_INSTALL_DIR` của tài khoản trỏ tới đó, bên ngoài vùng AppData riêng của Codex. Python3.12.14 và3.11.9 có thể dùng cho dự án khác qua `python3.12` hoặc `python3.11`. Hai IDE dùng Python3.12 làm dự phòng; giữ `python` toàn cục3.11 để bảo toàn tương thích cũ. Mỗi dự án vẫn dùng `.venv` và lockfile riêng; không dùng venv của Studio cho dự án khác. Đường dẫn AppData cũ còn thiếu được nối về bản Python dùng chung, không sao chép thêm interpreter. Các venv dùng phiên bản khác chưa được kiểm tra. Xem bằng chứng trong và ngoài Codex, log IDE và giới hạn tại [báo cáo triển khai](docs/IMPLEMENTATION_STATUS.md#w-rà-soát-môi-trường-vs-code-và-antigravity-ide--02112026).

GitHub CLI đã kiểm tra đăng nhập và quyền repository; Docker Desktop/WSL2 chạy đủ bốn services. Không cần cài lại các thành phần đang khỏe.

Dependencies khóa bằng `uv.lock`, `requirements.txt` sinh từ lock và `frontend/package-lock.json`. Python 3.12.14; React 19.3.1, Vite 8.3.5, TypeScript 6.0.3, TanStack Table 8.21.3, Tailwind 4.3.3, Radix Dialog 1.3.1. TanStack dùng API stable nhánh 8 đã kiểm tra tương thích với React được chọn. Docker images pin tags trong Dockerfiles/Compose; backend và worker dùng cùng image.

## Tài liệu và phạm vi tiếp theo

- [Kiến trúc](docs/ARCHITECTURE.md), [hợp đồng dữ liệu/API](docs/DATA_CONTRACTS.md).
- [Tích hợp AI và gate Qwen live](docs/AI_INTEGRATION.md).
- [Nghiên cứu phân tuyến Flash-Lite/Argon](docs/AI_MODEL_ROUTING_RESEARCH.md) — chưa tích hợp, chưa gọi Argon live.
- [Kiểm thử](docs/TESTING_GUIDE.md), [trạng thái nghiệm thu](docs/IMPLEMENTATION_STATUS.md).
- [Kế hoạch ba giai đoạn](docs/PROJECT_PLAN.md), [Rules](Rules.md), [hướng dẫn Codex](AGENTS.md).

Giai đoạn 2 và Assistant/Agent dùng trực tiếp CanonicalDataset/MappingRevision/SchemaDefinition/EvidenceRef, queue, session và App Shell hiện có. Trạng thái nhánh/main/image của lần nghiệm thu hiện hành nằm ở báo cáo mục V; các mốc gate NLP cũ được giữ theo lịch sử. Argon chưa tích hợp. `.vscode/settings.json` chỉ chia sẻ boolean dùng env file local; `.env`/credentials vẫn bị ignore. Repository chính thức: [MinhHoang1403/AI-Reconciliation-Studio](https://github.com/MinhHoang1403/AI-Reconciliation-Studio).

Kiểm toán bổ sung: chọn hai nguồn → AI có thể gợi ý khóa/chỉ tiêu dù chưa nhập khóa; thiếu kỳ/coverage giữ trạng thái cần xác nhận. Nhập kỳ, múi giờ và phạm vi thực tế, xác nhận rồi lưu/duyệt rule; phần chỉnh thủ công dùng được khi cloud tắt hoặc hết quota. UI không tự chọn tháng/UTC. Trong bằng chứng, bấm **Xem nguồn [tên trường]** để xem giá trị gốc đúng cột/file/sheet/dòng. KPI **Tự động phân loại** bao gồm kết luận thiếu đối ứng/lệch đã xác minh, không phải tỷ lệ ngoại lệ đã giải quyết. Báo cáo export bất biến theo lần tạo đầu của run/định dạng/revision; UI và Summary ghi thời điểm/phạm vi review, review sau đó không cập nhật file cũ. Xem kết quả kiểm toán trong [báo cáo](docs/IMPLEMENTATION_STATUS.md).
