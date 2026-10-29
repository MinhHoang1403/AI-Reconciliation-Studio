# AI Reconciliation Studio

Nền tảng chuẩn bị dữ liệu CSV/XLSX: đọc và phân tích cấu trúc, AI đề xuất ánh xạ, người dùng xác nhận rồi chuẩn hóa có kiểu và nguồn gốc. Giao diện sáng, xanh dương; dữ liệu, mapping và kết quả được lưu trong PostgreSQL/Parquet.

**Trạng thái:** Giai đoạn 1 đã hợp nhất và gắn tag `data-foundation-accepted-20261028`. Giai đoạn 2 có rule builder/AI Planner, matching/verification, kết quả, ngoại lệ và CSV/XLSX trên `codex/reconciliation-engine`; chưa merge vào main. Gemini mặc định, mapping/rule luôn cần duyệt. Qwen live hoãn vì IP allowlist; LlamaParse tạo job OFF. Xem [bằng chứng và giới hạn](docs/IMPLEMENTATION_STATUS.md).

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

## Cấu hình

[.env.example](.env.example) chứa placeholders, không chứa secret. `.env` không vào Git/image. Khi cài từ repository mới, đặt `QWEN_BASE_URL` trong `.env` theo [thông tin provider](docs/AI_INTEGRATION.md), model `knowledge`, không thêm API key Qwen. Sau khi đổi cấu hình, chạy lại `tools/start.ps1`.

Mặc định `LOCAL_DEMO_ACCESS=true`, Gemini/LlamaParse keys rỗng, cloud permissions false và request budgets bằng 0. Quyền workspace cũng mặc định `LOCAL_ONLY`; biến môi trường không tự cấp quyền cloud. Không tự chuyển provider khi Qwen lỗi.

Workspace local chọn `MAPPING_AI_PROVIDER=GEMINI`, `ALLOW_EXTERNAL_AI=true`, `EXTERNAL_AI_REQUEST_BUDGET=10`, key chỉ trong `.env`; policy workspace `CLOUD_ALLOWED` và trần 10 request. Mỗi HTTP attempt (kể cả retry/lỗi) có reservation bền vững, trừ hạn mức toàn hệ thống lẫn workspace; Cài đặt hiển thị số đã dùng/còn lại. Không reset khi restart. Qwen giữ nguyên adapter/endpoint nhưng không probe lặp lại; chỉ lựa chọn khi chủ dự án mở quyền. LlamaParse có quyền, request/credit ceilings và SHA256 allowlist riêng; sau phép thử đã tắt quyền tạo job, không xóa keys/reservations/artifacts.

`docker compose up -d --build --wait` khởi động đủ bốn service. Sau lệnh này, chạy `./tools/verify-local.ps1` để kích hoạt auto-session local. Nếu chưa xác minh, `/api/session` trả 403; không tắt auth để vượt qua. Proof mất hiệu lực khi restart/recreate backend hoặc frontend. Chỉ hỗ trợ loopback demo; không publish LAN/Internet hoặc public reverse proxy.

## Cách sử dụng

1. Tạo dự án, nhập tên và phạm vi nghiệp vụ để kiểm soát tái sử dụng mapping.
2. Chọn **Tải dữ liệu**, thêm nhiều CSV/XLSX. Encoding/delimiter/header nằm trong tùy chọn nâng cao; UTF-8/BOM là mặc định.
   Có thể bỏ chọn “Dùng AI đề xuất ánh xạ trong hạn mức” để chỉ parse/profile và review thủ công, không enqueue AI hoặc tiêu quota. Quyết định này không thay đổi raw/parsed semantics; có thể yêu cầu đề xuất riêng về sau.
3. Mở nguồn và chọn sheet. **Khám phá dữ liệu** có phân trang/tìm kiếm phía server, thống kê và nguồn gốc.
4. Mở **AI Smart Setup**. Provider được chọn đề xuất ánh xạ; nếu bị chặn, thiếu key hoặc hết ngân sách, UI báo rõ và cho phép dùng shortlist/thủ công. Không hiển thị thành công AI giả.
5. Xác nhận loại dữ liệu, ý nghĩa mỗi dòng và từng trường cần dùng. Có thể giữ cột chuỗi tùy chỉnh. Với tiền, xác nhận locale, chỉ tiêu, gross/net hoặc định nghĩa riêng, currency và đơn vị; với ngày, chọn format/timezone rõ ràng. Cảnh báo công thức/vùng bảng cần được kiểm tra.
6. Bấm **Xác nhận ánh xạ**, rồi **Chuẩn hóa dữ liệu**. Khi job hoàn tất, bấm **Cập nhật kết quả** và **Xem kết quả**.
7. Dùng lớp **Cảnh báo / lỗi** để kiểm tra invalid/null và **Xem nguồn** để mở dòng gốc. Dữ liệu lỗi không bị thay bằng zero hoặc bỏ đi. Sửa mapping tạo revision mới, canonical cũ được đánh dấu đã cũ; raw/parsed được bảo toàn.
8. Mở lại trình duyệt, chọn dự án cũ để tiếp tục. Tệp cùng nội dung/config trong cùng dự án được reuse; mẫu đã duyệt chỉ được gợi ý trong scope tương thích.

PDF/DOCX mới cần allowance riêng được duyệt trước khi upload. Kết quả đã lưu có preview theo file/trang/bảng và luôn “chưa được xác minh”; không tự chuyển thành canonical hoặc suy ra kết luận tiền. Đọc lại kết quả không gọi provider. Trợ lý AI chat chưa triển khai.

## Đối soát và báo cáo

1. Sau khi có hai canonical trong cùng project, mở **Đối soát**, chọn nguồn tham chiếu/đối ứng.
2. Xác nhận khóa, quan hệ một-một/một-nhiều/nhiều-một, grain, metric/currency/basis, dấu tiền theo nguồn, kỳ `[start,end)`, timezone và coverage. Internal ecommerce lọc đúng platform/shop cho từng pair, không JOIN ba nguồn.
3. Dùng **Kiểm tra điều kiện**, rồi lưu đề xuất thủ công hoặc yêu cầu Gemini đề xuất. AI dùng quota hiện có; manual không gọi cloud. Gemini Planner đã dùng thêm 1 attempt, tổng 7/10 còn 3; không reset/tăng. Không gọi Qwen hoặc mở parser khi lỗi AI.
4. Review đề xuất, **Xác nhận quy tắc và dấu số tiền**, rồi **Chạy đối soát đã duyệt**. Duplicate/fuzzy mơ hồ giữ review, không tự chọn; null/invalid không thành zero. Coverage thiếu phải cho phép partial rõ ràng.
5. **Báo cáo/Tổng quan** hiển thị snapshot đã verified, denominator/CU/period và từng metric/currency riêng. Không có verified result thì empty/loading state, không KPI giả. Lọc lịch sử theo kỳ/nguồn, chọn đúng run ID.
6. **Ngoại lệ** có tìm kiếm, lọc loại/trạng thái, sort, bằng chứng hai bên và dòng nguồn. Resolve/dismiss cần ghi chú; review không sửa comparison, variance hoặc snapshot của run.
7. **Xuất CSV/XLSX** → **Tải báo cáo**. Hai định dạng dùng cùng snapshot; text chống formula injection, Decimal âm giữ numeric, IDs giữ zero-prefix. Excel arithmetic vẫn có giới hạn 15 significant digits; exact values có trong OOXML numeric lexemes/snapshot strings và CSV.
8. Mẫu đã duyệt có thể rebind nguồn/kỳ mới, kiểm schema/mapping/effective date và trở thành proposal phải duyệt lại. Nguồn stale không được chạy; lịch sử run cũ vẫn bất biến.

Chạy bộ demo có oracle trên dữ liệu tổng hợp, không gọi AI:

```powershell
uv run python tools/check-reconciliation.py
```

Công cụ tạo/reuse đúng một project demo, năm nguồn CSV và ba pair runs, kiểm oracle, lưu báo cáo tại runtime bị ignore. Gemini planner live đã thử và được cache; không chạy lại cloud chỉ để replay. `--planner-live` là lựa chọn explicit có quota guard/task cap, không phải regression mặc định.

## Vận hành và bảo toàn dữ liệu

```powershell
docker compose ps
docker compose logs --tail=100 backend worker
docker compose restart
./tools/verify-local.ps1
docker compose stop
```

Named volumes `ai-reconciliation-studio_postgres_data` và `ai-reconciliation-studio_artifacts` giữ metadata/raw/Parquet. Không chạy `down -v`, xóa volumes hoặc global prune. GitHub lưu source, không thay backup dữ liệu. Công cụ `./tools/check-persistence.ps1` kiểm tra restart và force-recreate trong project hiện tại, so metadata và checksum trước/sau, không xóa volumes.

## Kiểm thử và phát triển

```powershell
uv sync --frozen
uv run pytest -q -m 'not integration'
uv run ruff check backend tests tools
uv run mypy backend/studio
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

Dependencies khóa bằng `uv.lock`, `requirements.txt` sinh từ lock và `frontend/package-lock.json`. Python 3.12.14; React 19.3.1, Vite 8.3.5, TypeScript 6.0.3, TanStack Table 8.21.3, Tailwind 4.3.3, Radix Dialog 1.3.1. TanStack dùng API stable nhánh 8 đã kiểm tra tương thích với React được chọn. Docker images pin tags trong Dockerfiles/Compose; backend và worker dùng cùng image.

## Tài liệu và phạm vi tiếp theo

- [Kiến trúc](docs/ARCHITECTURE.md), [hợp đồng dữ liệu/API](docs/DATA_CONTRACTS.md).
- [Tích hợp AI và gate Qwen live](docs/AI_INTEGRATION.md).
- [Kiểm thử](docs/TESTING_GUIDE.md), [trạng thái nghiệm thu](docs/IMPLEMENTATION_STATUS.md).
- [Kế hoạch ba giai đoạn](docs/PROJECT_PLAN.md), [Rules](Rules.md), [hướng dẫn Codex](AGENTS.md).

Giai đoạn 2 dùng trực tiếp CanonicalDataset/MappingRevision/SchemaDefinition/EvidenceRef, queue, session và App Shell hiện có. Không triển khai Assistant Giai đoạn 3; dừng sau bàn giao feature branch để chủ dự án xem kết quả. Repository chính thức: [MinhHoang1403/AI-Reconciliation-Studio](https://github.com/MinhHoang1403/AI-Reconciliation-Studio).

Kiểm toán bổ sung: chọn hai nguồn → AI có thể gợi ý khóa/chỉ tiêu dù chưa nhập khóa; thiếu kỳ/coverage giữ trạng thái cần xác nhận. Nhập kỳ, múi giờ và phạm vi thực tế, xác nhận rồi lưu/duyệt rule; phần chỉnh thủ công dùng được khi cloud tắt hoặc hết quota. UI không tự chọn tháng/UTC. Trong bằng chứng, bấm **Xem nguồn [tên trường]** để xem giá trị gốc đúng cột/file/sheet/dòng. KPI **Tự động phân loại** bao gồm kết luận thiếu đối ứng/lệch đã xác minh, không phải tỷ lệ ngoại lệ đã giải quyết. Báo cáo export bất biến theo lần tạo đầu của run/định dạng/revision; UI và Summary ghi thời điểm/phạm vi review, review sau đó không cập nhật file cũ. Xem kết quả kiểm toán trong [báo cáo](docs/IMPLEMENTATION_STATUS.md).
