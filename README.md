# AI Reconciliation Studio

Ứng dụng hỗ trợ đối soát dữ liệu từ nhiều nguồn bằng AI: đề xuất ý nghĩa trường dữ liệu, chuẩn bị quy tắc so sánh và giải thích sai lệch có bằng chứng. Backend chịu trách nhiệm tính toán xác định và kiểm chứng kết quả; người dùng duyệt các quyết định cần thiết.

**Trạng thái hiện tại:** repository đã có kế hoạch và quy tắc phát triển; chưa triển khai ứng dụng, chưa có kết quả kiểm thử chức năng hoặc benchmark. Giai đoạn 1 chỉ bắt đầu khi có nhiệm vụ triển khai riêng.

## Mục tiêu và tính năng dự kiến

- Tiếp nhận CSV/XLSX; xử lý PDF/DOCX qua adapter có chính sách và kiểm tra chất lượng.
- Phân tích đặc điểm dữ liệu, nhận diện ý nghĩa mỗi dòng, đề xuất ánh xạ trường và chuẩn hóa theo quyết định đã duyệt.
- Lập kế hoạch đối soát; liên kết bản ghi theo khóa hoặc nhóm, so sánh tiền bằng `Decimal`, kiểm chứng độc lập và bảo toàn nguồn gốc.
- Dashboard sáng, xanh dương; danh sách ngoại lệ, bằng chứng về dòng nguồn và xuất CSV/XLSX từ cùng bộ số liệu đã xác minh.
- Trợ lý AI theo ngữ cảnh, trả lời từ dữ liệu đã xác minh; tái sử dụng mapping và quy tắc còn hiệu lực trong đúng phạm vi.

Demo dự kiến gồm nguồn nội bộ, Shopee Orders và TikTok Shop Orders, cùng bộ dữ liệu ngành khác để kiểm tra tính tổng quát. Sản phẩm hỗ trợ đối soát, không tự đưa ra kết luận kiểm toán độc lập.

## Công nghệ và kiến trúc dự kiến

| Thành phần | Lựa chọn trong kế hoạch |
|---|---|
| Giao diện | React, TypeScript, Vite, Tailwind CSS; một bộ component; TanStack Table, Apache ECharts |
| Backend | Python, FastAPI, Pydantic |
| Metadata, quyền và jobs | PostgreSQL, SQLAlchemy, Alembic; worker Python dùng chung code/backend image |
| Dữ liệu và đối soát | Parquet, Polars, fastexcel/openpyxl, DuckDB, RapidFuzz tạo ứng viên; `Decimal/NUMERIC` cho tiền |
| AI | Qwen công ty là provider chính; Gemini Flash-Lite và LlamaParse chỉ khi policy/ngân sách cho phép |
| Triển khai và kiểm thử | Nginx, một Docker Compose project; pytest, Hypothesis, Playwright, Ruff/mypy/ESLint |

Giao diện gọi Backend qua Nginx với `/api` cùng origin. Backend quản lý quyền, hợp đồng dữ liệu và trạng thái trong PostgreSQL; worker xử lý các artifact bất biến trên persistent storage. Một AI Gateway nhận yêu cầu có cấu trúc; mọi đề xuất phải qua kiểm tra nghiệp vụ. Không host lại Qwen trong Docker dự án.

Mặc định chỉ dùng AI nội bộ (`LOCAL_ONLY`), ngân sách request cloud bằng 0. Phiên bản thư viện và contract provider sẽ được kiểm tra, pin khi triển khai; bảng trên là thiết kế, chưa phải các tích hợp đã chạy.

## Ba giai đoạn triển khai

1. **Nền tảng dữ liệu + AI Smart Setup + UI cơ sở:** upload, parse, profiling, đề xuất/duyệt mapping, chuẩn hóa, lưu trữ và demo local an toàn.
2. **AI Planning + Matching/Verification + Results:** hợp đồng đối soát được duyệt, engine liên kết/so sánh, kiểm chứng độc lập, KPI, ngoại lệ, bằng chứng và exports.
3. **Contextual Assistant + tự động hóa + release:** tools chỉ đọc dữ liệu đã xác minh, hội thoại, khôi phục jobs, benchmark, bảo mật và nghiệm thu toàn tuyến.

Mỗi giai đoạn phải vượt qua các điều kiện nghiệm thu trong [kế hoạch chính thức](docs/PROJECT_PLAN.md) trước khi bàn giao sang giai đoạn tiếp theo.

## Cấu trúc repository hiện tại

```text
.
├── .gitignore
├── AGENTS.md
├── README.md
├── Rules.md
└── docs/
    └── PROJECT_PLAN.md
```

- [AGENTS.md](AGENTS.md): hướng dẫn Codex đọc và áp dụng quy tắc trước mỗi nhiệm vụ.
- [Rules.md](Rules.md): quy tắc kỹ thuật, dữ liệu, AI, bảo mật, Git/Docker và kiểm chứng.
- [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md): yêu cầu sản phẩm, kiến trúc, hợp đồng, thuật toán và nghiệm thu.

## Phát triển và cấu hình

Trước mỗi nhiệm vụ, đọc `AGENTS.md`, toàn bộ `Rules.md` và kế hoạch; kiểm tra Git status/branch/diff/remote. Thay đổi nhỏ có thể trên `main`; việc lớn/rủi ro dùng feature branch trong cùng repository. Kiểm tra diff, tests liên quan, secrets và nội dung trước commit/push; không force-push hoặc tạo worktree/bản sao không cần thiết.

Hiện chưa có dependency manifests, cấu hình Compose hoặc lệnh chạy ứng dụng. Khi triển khai Giai đoạn 1, cần chốt hợp đồng cấu hình, dependency lockfiles, ports không xung đột, migrations và tests; sau đó bổ sung lệnh cài đặt/chạy/kiểm thử đã được thực thi thành công vào README. Chưa tạo `.env.example` vì tên và schema cấu hình ứng dụng chưa được chốt; file này sẽ chỉ chứa ví dụ không có credentials.

Không lưu `.env`, keys/tokens, dữ liệu doanh nghiệp, uploads, database backups hoặc Docker volume data vào Git. Runtime dùng các đường dẫn đã loại trừ trong `.gitignore`; fixtures được commit phải là dữ liệu tổng hợp đã kiểm tra. `.gitignore` không thay thế việc rà soát nội dung tài liệu và files trước push lên repository Public.

Repository chính thức: [MinhHoang1403/AI-Reconciliation-Studio](https://github.com/MinhHoang1403/AI-Reconciliation-Studio).
