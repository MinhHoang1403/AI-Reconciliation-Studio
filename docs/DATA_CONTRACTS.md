# Hợp đồng dữ liệu và API

Định nghĩa thực thi nằm trong `backend/studio/contracts/`. OpenAPI tại `/openapi.json` và `/docs` mô tả request/response; endpoint này không cấp quyền đọc dữ liệu. Error envelope: `code`, `message_vi`, `details` đã redacted, `retryable`, `correlation_id`.

## Assistant: tools và facts

API bổ sung: `POST /api/assistant/tools`, `POST /api/conversations`, `GET /api/conversations?project_id=...`, `GET /api/conversations/{id}`, `DELETE /api/conversations/{id}`, `POST /api/assistant/messages`. Create/message dùng `Idempotency-Key`; message trả job ID để resume bằng GET, không gửi lại provider. GET hỗ trợ limit 1–50 và `before_id` thuộc đúng project/hội thoại. Context và text khác với key cũ trả 409. Conversation/message output có source context riêng; hội thoại khác actor/project/workspace hoặc đã xóa trả 404.

`AssistantContext` luôn có project; group/case bắt buộc explicit run. Bảy `ToolName` ở kế hoạch §34 là allowlist đóng, input không nhận SQL, code hoặc đường dẫn. Mỗi truy xuất kiểm workspace/project/run, output typed và có giới hạn trang; PostgreSQL statement timeout 2,5 giây, DuckDB evidence query 3 giây, nhóm tối đa 100 nguồn evidence cho Assistant. Nhóm lớn hơn yêu cầu mở evidence phân trang.

`AnswerFactSet` có content hash, context, trạng thái verification, nguyên bản MetricSnapshot, rule ID/revision, facts và source references (run/snapshot/group/member/file/table/sheet/row). Facts tiền và tỷ lệ chỉ sao chép từ snapshot/comparison đã verified; không tính lại KPI. ID giả, run khác, snapshot/rule không khớp phải bị từ chối. FactSet cũ giữ nguyên run cũ, không được gắn làm kết quả mới.

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

Project purpose là metadata hiển thị `WORK/TEST/UNKNOWN`, mặc định UNKNOWN cho project lịch sử chưa có quyết định. Dùng audit append-only `PROJECT_CLASSIFIED_WORK/TEST/UNKNOWN` theo workspace/resource ID; sự kiện mới nhất theo created_at/id là phân loại hiện hành. Không cần migration/cột mới, không suy ra nhóm từ tên. `POST /api/projects` mặc định WORK, nhận classification explicit; tạo TEST/UNKNOWN cần owner. `PATCH /api/projects/{id}/classification` chỉ owner, bắt buộc classification và expected_classification; khóa project/so trạng thái cũ, conflict409, no-op không thêm audit. Không invalidate nguồn/mapping/run hoặc đổi quyền truy cập. `GET /api/projects?include_test=false` lọc TEST trước search/offset/limit và count; UNKNOWN/WORK vẫn hiện. API giữ include_test=true khi bỏ tham số để tương thích clients cũ; UI gửi false mặc định. GET theo ID tiếp tục đọc TEST theo quyền, độc lập bộ lọc.

`GET /api/datasets` sắp xếp created_at DESC, id ASC ổn định. Dashboard dùng riêng offset0/limit5, độc lập offset25 của danh sách Dữ liệu; cùng scoped API, không endpoint hoặc business state mới. Loading/error riêng, abort khi đổi project/page; refresh/upload/job completion cập nhật summary rồi danh sách gần đây.

- `GET/POST /api/projects`, `GET /api/projects/{id}/summary`.
- `GET /api/projects?search=...&offset=0&limit=20` tìm literal theo tên/phạm vi, không phân biệt hoa/thường, giữ Unicode và workspace scope; max search200/limit100, thứ tự created_at DESC/id ổn định. `GET /api/projects/{id}` khôi phục saved project ngoài trang đầu; missing/khác workspace cùng404, không lộ metadata. Không tải toàn bộ danh sách vào frontend.
- `GET /api/datasets?project_id=...&offset=0&limit=25`, `POST /api/datasets/uploads` (multipart nhiều tệp).
- `GET /api/datasets/{id}`, `/tables`, `/artifacts`.
- `GET /api/tables/{id}/profile`, `/mappings`, `/preview`.
- `POST /api/tables/{id}/mapping-proposals` với `Idempotency-Key`.
- `POST /api/mappings/{id}/approve`, `/reject`.
- `POST /api/datasets/{id}/normalize` với `Idempotency-Key` và mapping ID cụ thể.
- `GET /api/schemas/{id}`, `/canonical-datasets/{id}`, `/mapping-proposals/{id}`.
- `GET /api/jobs?project_id=...`, `/jobs/{id}`, `/evidence/{id}`.
- `GET /api/session`, `/api/settings`, `/api/live`, `/api/ready`.
- `GET /api/datasets/{id}/documents` trả `DocumentArtifact` scoped: artifact ref/checksum, `FileArtifact` nguồn và `DocumentExtraction` với pages/items/bbox/usage. Không tự tạo canonical từ extraction.

Preview dùng `kind=raw|parsed|canonical|errors`, `offset`, `limit` tối đa 100 và `search` literal. Canonical/errors bắt buộc `canonical_id` cụ thể. `raw` là preview lexical values đọc từ raw artifact, không phải tải raw bytes ra browser. Tìm kiếm/phân trang thực hiện trên backend; tiền trả chuỗi Decimal chính xác.

Dashboard đếm từ `/projects/{id}/summary`, không tự tính KPI hoặc suy đoán kết luận nghiệp vụ. Dataset list có phân trang 25 nguồn/trang. Metadata lists nhỏ như projects/mappings có giới hạn API theo phạm vi hiện tại.

Quality hardening bổ sung additive `partial_canonical_count`, `stale_canonical_count`, `failed_canonical_count` (đếm artifact; stale tách riêng khỏi chất lượng hiện hành), `preparation_action` và `latest_verified_run_id` vào summary; fields cũ giữ nguyên. Mapping review = bảng không active mapping, job active chỉ QUEUED/RUNNING/RETRYABLE_FAILURE. Action chỉ điều hướng/refresh, không cấp quyền mutate: WAIT → failed dataset → REVIEW_MAPPING → NORMALIZE khi không current canonical → REVIEW_DATA cho PARTIAL/FAILED → RECONCILE khi có ít nhất hai READY → UPLOAD. Cùng ưu tiên chọn theo dataset created_at/id và table id; trả một target có dataset/table/canonical IDs scoped kể cả ngoài trang datasets hiện tại. READY không chứng minh hai nguồn tương thích metric/grain; approval/readiness/verification gates không đổi. Latest verified run chỉ gồm VERIFIED/PARTIAL_VERIFIED đúng project, dùng cho link lịch sử.

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

Upload nhận thêm form `request_ai_mapping` (mặc định true). False giữ nguyên parse/profile/manual proposal nhưng không enqueue AI; đây là lựa chọn workflow, không phải parse config để phá cache. Với PDF/DOCX, parser revision riêng `llamaparse-cost-effective-1`, page cap 2, artifact JSON bất biến có chất lượng `UNVERIFIED_EXTRACTION`. WorkspacePolicy bổ sung `parser_allowed_sha256` mặc định rỗng, tối đa hai hash. Dữ liệu policy cũ vẫn đọc được theo defaults; không đổi schema PostgreSQL vì policy đã là JSONB. Cache document được đọc/reuse sau khi quyền tạo job đã bị thu hồi.

## DSL

Allowlist có `cast_string_preserve`, `trim_if_approved`, `parse_decimal`, `parse_date`, `normalize_enum`, `coalesce_with_rule`, `add_fields`, `subtract_fields`, `aggregate_by`. Pydantic discriminated union từ chối operation/params lạ, Python/SQL không được thực thi.

Giao diện cung cấp giữ chuỗi/trim được duyệt, Decimal locale và date format/timezone. Enum, coalesce, arithmetic và aggregation có API contract với `ApprovedTransformRule`; cần rule ID, nguồn và bằng chứng phù hợp, quyền editor. UI chưa có trình soạn các rule nâng cao này. Không tự tạo công thức phí hoặc FX.

Null/empty khi parse Decimal tạo null, giữ raw và `value_state=NULL`; chuỗi sai tạo null kèm lỗi `INVALID`. Zero hợp lệ là Decimal zero. Không ghi lỗi thành 0, không bỏ dòng. Required null hoặc conversion error làm PARTIAL. Error artifact là Parquet riêng có source row/field/raw/code/value state.

## Reconciliation contracts và APIs

Pydantic contracts ở `contracts/reconciliation.py`: ReconciliationPlan/Contract/Run, MatchGroup/Member/ComparisonResult, ExceptionCase, MetricSnapshot và VerifiedRun. Plan/AI JSON không cấp quyền chạy. Approve tạo contract bất biến có actor/time/revision; sửa kế hoạch tạo proposal/approval mới, không ghi đè lịch sử. SourceSelection có canonical ID, role, date/time basis, explicit filters, coverage/completeness/snapshot/due date. Metric có fields/semantic ID/basis/currency/unit/SOURCE_SIGNED, tolerance và rounding. Không chạy Python/SQL tùy ý.

| Route | Contract/gate |
|---|---|
| GET /api/projects/{id}/canonical-catalogue | Scoped canonical/schema/profile/mapping/identifier refs; stale không được chạy |
| GET /api/projects/{id}/domain-schema-templates | Order/OrderLine/FinancialEvent đề xuất; Settlement/Payout chỉ khi có nguồn entity thật; không approval |
| POST /api/reconciliation-plans/validate | Metadata/type/semantics/readiness; key uniqueness chỉ trên IN_SCOPE sau cùng partition của engine; trả riêng invalid/out-of-scope/in-scope và coverage_complete |
| POST /api/reconciliation-plans | Manual typed proposal, Idempotency-Key; không execute |
| POST /api/reconciliation-plans/ai | `{project_id, request: PlanningRequest}` với hai canonical IDs, facts đã xác nhận và intent; không bắt nhập keys/metrics. Giữ input `{project_id, plan}` cũ. Queue/policy/key/reservation/task cap; không tự approve |
| GET /api/reconciliation-plans/{id} | Typed proposal, source và approved contract ID nếu có |
| POST /api/reconciliation-contracts/{plan_id}/approve | Editor, validate lại scope/revisions và audit; tạo immutable contract |
| GET /api/projects/{id}/reconciliation-templates | Approved rules trong project |
| POST /api/reconciliation-contracts/{id}/reuse | Rebind canonical/period/coverage mới, kiểm schema/transform semantics/effective dates; tạo proposal cần duyệt lại |
| POST /api/reconciliation-runs | Chỉ approved contract; logical fingerprint sources/rule/engine và queue idempotency |
| GET /api/runs?project_id=... | Pagination, period_start/period_end/source_id server filters |
| GET /api/runs/{id} | Status, source refs/checks và RunArtifactRef; không raw storage path |
| GET /api/runs/{id}/metrics | Chỉ VERIFIED/PARTIAL_VERIFIED, đúng một immutable snapshot |
| GET /api/runs/{id}/matches | Server pagination/search/linkage/comparison filters; match groups typed |
| GET /api/runs/{id}/groups/{group_id}/evidence | Group thuộc đúng run; scoped source records/provenance, filename; `field_evidence` là EvidenceRef theo đúng MappingRevision của canonical lịch sử. Preview mỗi source 100 records, field refs 100 source rows/record |
| GET /api/runs/{id}/exceptions | Search, state/type filters, type/state sort, pagination; current_open_count riêng |
| PATCH /api/exceptions/{id}/review | Editor, lý do bắt buộc khi resolve/dismiss, audit actor/time; không đổi monetary result |
| POST /api/runs/{id}/exports?format=csv hoặc xlsx | Verified only; queue và cached immutable export theo run/revision |
| GET /api/exports/{id}, /download | Workspace scope, checksum, same-origin auth; metadata revision/review_state_scope/review_state_as_of; không token/path trong URL |

RunArtifactRef độc lập DatasetVersion vì run có hai nguồn; source CanonicalDataset refs được giữ đầy đủ. Không lạm dụng ArtifactRef một-source cho match results. Failure không có MetricSnapshot. PARTIAL_VERIFIED không được trình bày như đầy đủ khi có invalid/pending/not-comparable.

CU là left canonical record ở 1:1/1:N hoặc left canonical group ở N:1. Eligible có scope/keys/own Decimal/currency hợp lệ; invalid/out-of-scope/pending/thiếu own money báo excluded riêng. Ambiguous còn trong mẫu số review. Full match đòi LINKED + EQUAL/WITHIN_TOLERANCE; zero denominator N/A. Automation là phân loại xác định đã verified không cần row-level human decision, không phải tỷ lệ tiền đã đúng. Monetary sums chỉ comparable metrics/currency/unit riêng, không cộng đa tiền tệ. `delta=L-R`, abs variance = abs(delta), tolerance theo PROJECT_PLAN; rounding chỉ khi approved.

CSV/XLSX chứa Summary/Metrics/Matches/Exceptions/Data quality/Evidence/Sources/Rules. Snapshot JSON lưu nguyên DTO để đối chiếu API. Text `=,+,-,@` có guard, IDs giữ chuỗi/zero-prefix, Decimal âm vẫn numeric. OOXML numeric lexemes giữ Decimal chính xác, nhưng Excel arithmetic có giới hạn 15 significant digits; snapshot strings/CSV phục vụ exact interchange. Report không tự tính lại KPI. Exception state được chụp khi export lần đầu, các review sau không sửa file export đã công bố.

Kiểm toán bổ sung 28/10/2026: `PlanningRequest`/`PlanningSource` tách khỏi ReconciliationPlan hoàn chỉnh. Trước AI chỉ kiểm quyền, canonical/schema/profile/mapping/artifact refs và những facts được gửi; key/grain/cardinality/metric không phải tiền điều kiện của request đề xuất. Sau AI, complete plan vẫn phải qua validator đầy đủ, giữ mọi facts được xác nhận. Khi thiếu thời gian/coverage, trả UNKNOWN/NEEDS_REVIEW với `PlanningSuggestions` (roles, field pairs, metrics, grain/cardinality/aggregation, evidence), không cấp quyền chạy. Suggestions cũng kiểm IDs/types/metric/basis/currency/grain/evidence; plan giả field hoặc thay scope bị từ chối. Proposal còn missing_requirements không được approve. Job/draft cũ vẫn đọc được; không đổi matcher, verifier hoặc engine revision.

Automation coverage giữ nguyên `metric-snapshot-1` và công thức PROJECT_PLAN §20. UI gọi **Tự động phân loại**: gồm cả kết luận xác định thiếu đối ứng/lệch đã verified, không diễn đạt như tỷ lệ khớp thành công hoặc case đã giải quyết. Không tính lại/ghi đè snapshots cũ.

Report mới dùng **report-2**, giữ nguyên report-1 và bytes/checksum đã công bố. `Summary` ghi Report generated at, Review state scope FIRST_GENERATION và giải thích automation. Worker đọc trạng thái review nhất quán trong một PostgreSQL REPEATABLE READ snapshot. API trả `review_state_as_of` từ job result; request lại cùng run/format/report revision reuse file cũ. CSV và XLSX được tạo vào hai thời điểm khác nhau có thể chứa trạng thái review khác nhau; KPI vẫn từ cùng MetricSnapshot. Report-1 cũ chưa lưu thời điểm review, trả null kèm thông báo UI; không tự suy ra timestamp hoặc sửa file lịch sử.

UI đọc tối đa 20 ô nguồn mỗi lần mở chi tiết và báo khi giới hạn; tên cột/giá trị/file/sheet/row hiển thị dạng bảng, không JSON. Transform nhiều inputs hiển thị các ô input, aggregate giữ các source members. Không sửa raw/canonical để khớp hiển thị.
