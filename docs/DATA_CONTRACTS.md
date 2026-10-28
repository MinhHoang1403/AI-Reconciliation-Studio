# Hợp đồng dữ liệu và API

Định nghĩa thực thi nằm trong `backend/studio/contracts/`. OpenAPI tại `/openapi.json` và `/docs` mô tả request/response; endpoint này không cấp quyền đọc dữ liệu. Error envelope: `code`, `message_vi`, `details` đã redacted, `retryable`, `correlation_id`.

## Handoff

| Đối tượng | Ref/API | Bất biến |
|---|---|---|
| `FileArtifact` | Raw artifact thuộc `DatasetVersion` | SHA256 trên bytes gốc; owner/workspace; không path do client cung cấp |
| `ParsedTableArtifact` | `GET /api/datasets/{id}/tables` | Cột c1/c2 có tên/vị trí nguồn; row identity độc lập business key; warnings không mất |
| `DatasetProfile` | `GET /api/tables/{id}/profile` | Thống kê bằng code; evidence từng cột; không bịa grain |
| `SchemaDefinition` | `GET /api/schemas/{id}` | Schema có ID/revision/workspace, fields có kiểu, grain và entity do người dùng xác nhận |
| `SchemaProposal` | `GET /api/mapping-proposals/{id}` | Gợi ý chưa được duyệt; UNKNOWN/AMBIGUOUS được giữ |
| `MappingRevision` | `POST /api/mappings/{id}/approve` | Approval mới luôn có ID/revision/actor/time; không ghi đè quyết định cũ |
| `CanonicalDataset` | `GET /api/canonical-datasets/{id}` | Artifact/errors refs, quality, mapping và normalization revision; `stale` độc lập chất lượng lịch sử |
| `EvidenceRef` | `GET /api/evidence/{table_id}:{column_id}?row=3` | Scope từ table đã authorize; file/sheet/physical row/column; formula/cache có metadata |
| `WorkspacePolicy` | `GET /api/settings` | Local-only và cloud budgets mặc định 0 |
| `JobStatus` | `GET /api/jobs/{id}` | QUEUED/RUNNING/RETRYABLE_FAILURE/BLOCKED/SUCCEEDED/FAILED/CANCELLED; mã lỗi và attempts |

Giai đoạn sau phải dùng các refs và API này, không viết parser/mapping thứ hai. DTO không truyền DataFrame hoặc JSON LLM không kiểm tra.

## REST đang hỗ trợ

- `GET/POST /api/projects`, `GET /api/projects/{id}/summary`.
- `GET /api/datasets?project_id=...&offset=0&limit=25`, `POST /api/datasets/uploads` (multipart nhiều tệp).
- `GET /api/datasets/{id}`, `/tables`, `/artifacts`.
- `GET /api/tables/{id}/profile`, `/mappings`, `/preview`.
- `POST /api/tables/{id}/mapping-proposals` với `Idempotency-Key`.
- `POST /api/mappings/{id}/approve`, `/reject`.
- `POST /api/datasets/{id}/normalize` với `Idempotency-Key` và mapping ID cụ thể.
- `GET /api/schemas/{id}`, `/canonical-datasets/{id}`, `/mapping-proposals/{id}`.
- `GET /api/jobs?project_id=...`, `/jobs/{id}`, `/evidence/{id}`.
- `GET /api/session`, `/api/settings`, `/api/live`, `/api/ready`.

Preview dùng `kind=raw|parsed|canonical|errors`, `offset`, `limit` tối đa 100 và `search` literal. Canonical/errors bắt buộc `canonical_id` cụ thể. `raw` là preview lexical values đọc từ raw artifact, không phải tải raw bytes ra browser. Tìm kiếm/phân trang thực hiện trên backend; tiền trả chuỗi Decimal chính xác.

Dashboard đếm từ `/projects/{id}/summary`, không tự tính KPI hoặc suy đoán kết luận nghiệp vụ. Dataset list có phân trang 25 nguồn/trang. Metadata lists nhỏ như projects/mappings có giới hạn API theo phạm vi hiện tại.

## Canonical record

Core có `canonical_record_id`, `dataset_version_id`, `source_table_id`, `source_row_id`, `workspace_id`, `entity_kind`, `business_key_components`, `source_provenance`, `mapping_revision`, `normalization_revision`, `quality_flags`, `invalid`, `record_payload`.

`business_key_components` là danh sách có kiểu `{field, value}`, có thể rỗng khi chưa định nghĩa business key; không dùng technical source ID thay khóa nghiệp vụ. `record_payload` là struct Parquet có chuỗi/Decimal/datetime theo schema. Ngày được chuyển sang UTC sau khi người dùng xác nhận format/timezone; không đoán timezone. Thời gian local DST mơ hồ/không tồn tại bị từ chối. Cả schema và DSL revision cho phép tái lập phép biến đổi.

Row identity tạo từ file/table/physical source row. CSV có quoted newline vẫn giữ physical start row. Source provenance chứa đủ thành viên khi nhóm. Bản ghi nhóm có group source ID kỹ thuật và danh sách lineage đầy đủ. AST đã duyệt nằm trong MappingRevision, không lặp toàn bộ transform JSON trên từng ô.

## Gates và revision

1. Upload kiểm tra size, extension/MIME/signature, ZIP/XML/embedded content; streaming SHA256. Một file tối đa 20 MiB, 10 file/lần; mỗi bảng 100k dòng/200 cột mặc định.
2. CSV đọc strings nghiêm ngặt UTF-8/BOM; Windows-1258 chỉ khi chọn rõ. XLSX dùng fastexcel kiểm tra cấu trúc và XML/openpyxl metadata để giữ lexical numbers/zero formats/formula cache. Không chạy formula.
3. Header lệch dòng, sheet ẩn, merged cells/formula/date serial phát sinh warnings và cần xác nhận extraction trước approval. Một sheet là một table candidate; chưa tự tách nhiều bảng cùng sheet.
4. Proposal kiểm tra field/evidence tồn tại, type, allowlist và semantics. AI không thể trả APPROVED. Tiền Total không tự suy ra gross/net.
5. Approval kiểm tra quyền, grain/entity, required fields, Decimal locale/metric/basis/currency/unit; tạo immutable revision. Mapping trước thành SUPERSEDED; canonical phụ thuộc thành stale; raw/parsed giữ nguyên.
6. Normalize nhận approved active mapping. READY/PARTIAL/FAILED là chất lượng chuẩn hóa; **không** đồng nghĩa đủ điều kiện đối soát tài chính. Rule/coverage/cardinality/period là gate giai đoạn sau.

`GET /api/settings` trả `mapping_ai_provider`, `gemini_model`, boolean `gemini_configured`, `gemini_requests_used` và `gemini_requests_remaining` trong scope workspace; không trả API key. Remaining là min của hạn mức global/workspace còn lại sau durable audit reservations, bằng 0 khi cloud không được phép. `JobView.result.source` phân biệt `GEMINI`, `QWEN`, `APPROVED_TEMPLATE`; success chỉ có nghĩa proposal qua validator, chưa được người dùng approve. Reservation đếm HTTP attempts kể cả lỗi; không phải chi phí tiền tệ hoặc số proposal thành công.

Upload lại cùng project/hash/parser config tái sử dụng dataset và raw. Cùng bytes ở project khác không reuse file ref. Chữ ký mapping gồm tên/thứ tự cột, type candidates, identifier flags; lookup còn yêu cầu workspace và business scope. Template được đưa lại dưới dạng đề xuất cần review, không auto-approve số tiền hoặc dữ liệu mới.

## DSL

Allowlist có `cast_string_preserve`, `trim_if_approved`, `parse_decimal`, `parse_date`, `normalize_enum`, `coalesce_with_rule`, `add_fields`, `subtract_fields`, `aggregate_by`. Pydantic discriminated union từ chối operation/params lạ, Python/SQL không được thực thi.

Giao diện cung cấp giữ chuỗi/trim được duyệt, Decimal locale và date format/timezone. Enum, coalesce, arithmetic và aggregation có API contract với `ApprovedTransformRule`; cần rule ID, nguồn và bằng chứng phù hợp, quyền editor. UI chưa có trình soạn các rule nâng cao này. Không tự tạo công thức phí hoặc FX.

Null/empty khi parse Decimal tạo null, giữ raw và `value_state=NULL`; chuỗi sai tạo null kèm lỗi `INVALID`. Zero hợp lệ là Decimal zero. Không ghi lỗi thành 0, không bỏ dòng. Required null hoặc conversion error làm PARTIAL. Error artifact là Parquet riêng có source row/field/raw/code/value state.
