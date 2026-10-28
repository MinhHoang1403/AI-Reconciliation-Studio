# AI Reconciliation Studio

Nền tảng chuẩn bị dữ liệu CSV/XLSX: đọc và phân tích cấu trúc, AI đề xuất ánh xạ, người dùng xác nhận rồi chuẩn hóa có kiểu và nguồn gốc. Giao diện sáng, xanh dương; dữ liệu, mapping và kết quả được lưu trong PostgreSQL/Parquet.

**Trạng thái:** chủ dự án đã chỉ định dùng Gemini tạm thời cho Smart Setup trong lúc chờ mở Qwen. LlamaParse vẫn tắt; mapping luôn cần người dùng duyệt. Qwen live còn **BLOCKED** do allowlist. Xem [bằng chứng nghiệm thu](docs/IMPLEMENTATION_STATUS.md); chưa chuyển Giai đoạn 2.

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

Workspace local hiện được chủ dự án cho phép chọn `MAPPING_AI_PROVIDER=GEMINI`, `ALLOW_EXTERNAL_AI=true`, `EXTERNAL_AI_REQUEST_BUDGET=10`, key chỉ trong `.env`; policy workspace `CLOUD_ALLOWED` và trần 10 request. Mỗi HTTP attempt (kể cả retry/lỗi) có reservation bền vững, trừ hạn mức toàn hệ thống lẫn workspace; Cài đặt hiển thị số đã dùng/còn lại. Không reset khi restart. Đổi lại `MAPPING_AI_PROVIDER=QWEN` rồi khởi động lại khi endpoint được mở; không cần upload lại raw. LlamaParse có quyền riêng và vẫn tắt.

`docker compose up -d --build --wait` khởi động đủ bốn service. Sau lệnh này, chạy `./tools/verify-local.ps1` để kích hoạt auto-session local. Nếu chưa xác minh, `/api/session` trả 403; không tắt auth để vượt qua. Proof mất hiệu lực khi restart/recreate backend hoặc frontend. Chỉ hỗ trợ loopback demo; không publish LAN/Internet hoặc public reverse proxy.

## Cách sử dụng

1. Tạo dự án, nhập tên và phạm vi nghiệp vụ để kiểm soát tái sử dụng mapping.
2. Chọn **Tải dữ liệu**, thêm nhiều CSV/XLSX. Encoding/delimiter/header nằm trong tùy chọn nâng cao; UTF-8/BOM là mặc định.
3. Mở nguồn và chọn sheet. **Khám phá dữ liệu** có phân trang/tìm kiếm phía server, thống kê và nguồn gốc.
4. Mở **AI Smart Setup**. Provider được chọn đề xuất ánh xạ; nếu bị chặn, thiếu key hoặc hết ngân sách, UI báo rõ và cho phép dùng shortlist/thủ công. Không hiển thị thành công AI giả.
5. Xác nhận loại dữ liệu, ý nghĩa mỗi dòng và từng trường cần dùng. Có thể giữ cột chuỗi tùy chỉnh. Với tiền, xác nhận locale, chỉ tiêu, gross/net hoặc định nghĩa riêng, currency và đơn vị; với ngày, chọn format/timezone rõ ràng. Cảnh báo công thức/vùng bảng cần được kiểm tra.
6. Bấm **Xác nhận ánh xạ**, rồi **Chuẩn hóa dữ liệu**. Khi job hoàn tất, bấm **Cập nhật kết quả** và **Xem kết quả**.
7. Dùng lớp **Cảnh báo / lỗi** để kiểm tra invalid/null và **Xem nguồn** để mở dòng gốc. Dữ liệu lỗi không bị thay bằng zero hoặc bỏ đi. Sửa mapping tạo revision mới, canonical cũ được đánh dấu đã cũ; raw/parsed được bảo toàn.
8. Mở lại trình duyệt, chọn dự án cũ để tiếp tục. Tệp cùng nội dung/config trong cùng dự án được reuse; mẫu đã duyệt chỉ được gợi ý trong scope tương thích.

PDF/DOCX hiện báo policy/adapter-only; chưa có cloud parsing end-to-end được nghiệm thu. Các mục Đối soát, Ngoại lệ, Báo cáo và Trợ lý AI chưa kích hoạt. Không có KPI tài chính giả.

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
$env:STUDIO_EXPECT_AI_PROVIDER='GEMINI' # Chỉ khi chủ dự án đã bật Gemini; có gọi live tổng hợp
npm --prefix frontend run test:e2e
uv run python tools/check_repository.py
```

PostgreSQL tests chạy trong schema UUID `test_*` của server hiện tại rồi dọn đúng schema tổng hợp đó; không dùng bảng dữ liệu ứng dụng hoặc Compose test project. Chi tiết, catalogue T01–T16, benchmark và trạng thái live/mock nằm trong [hướng dẫn kiểm thử](docs/TESTING_GUIDE.md).

Dependencies khóa bằng `uv.lock`, `requirements.txt` sinh từ lock và `frontend/package-lock.json`. Python 3.12.14; React 19.3.1, Vite 8.3.5, TypeScript 6.0.3, TanStack Table 8.21.3, Tailwind 4.3.3, Radix Dialog 1.3.1. TanStack dùng API stable nhánh 8 đã kiểm tra tương thích với React được chọn. Docker images pin tags trong Dockerfiles/Compose; backend và worker dùng cùng image.

## Tài liệu và phạm vi tiếp theo

- [Kiến trúc](docs/ARCHITECTURE.md), [hợp đồng dữ liệu/API](docs/DATA_CONTRACTS.md).
- [Tích hợp AI và gate Qwen live](docs/AI_INTEGRATION.md).
- [Kiểm thử](docs/TESTING_GUIDE.md), [trạng thái nghiệm thu](docs/IMPLEMENTATION_STATUS.md).
- [Kế hoạch ba giai đoạn](docs/PROJECT_PLAN.md), [Rules](Rules.md), [hướng dẫn Codex](AGENTS.md).

Giai đoạn 2 sẽ consume trực tiếp CanonicalDataset/MappingRevision/SchemaDefinition/EvidenceRef sau khi gates Giai đoạn 1 đạt. Chưa triển khai matching/verification tài chính hoặc Assistant. Repository chính thức: [MinhHoang1403/AI-Reconciliation-Studio](https://github.com/MinhHoang1403/AI-Reconciliation-Studio).
