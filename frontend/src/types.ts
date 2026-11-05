export type Status =
  | "UPLOADED"
  | "PARSING"
  | "PARSED"
  | "PROFILED"
  | "NEEDS_MAPPING_REVIEW"
  | "MAPPED"
  | "NORMALIZING"
  | "READY"
  | "PARTIAL"
  | "FAILED";
export type ProjectClassification = "WORK" | "TEST" | "UNKNOWN";
export interface Project {
  id: string;
  name: string;
  business_scope: string;
  workspace_id: string;
  classification: ProjectClassification;
}
export interface ProjectSummary {
  dataset_count: number;
  table_count: number;
  mapping_review_count: number;
  ready_canonical_count: number;
  active_job_count: number;
  partial_canonical_count: number;
  stale_canonical_count: number;
  failed_canonical_count: number;
  preparation_action: PreparationAction | null;
  latest_verified_run_id: string | null;
}
export interface PreparationAction {
  kind:
    | "UPLOAD"
    | "WAIT"
    | "REVIEW_MAPPING"
    | "NORMALIZE"
    | "REVIEW_DATA"
    | "RECONCILE";
  dataset_id: string | null;
  table_id: string | null;
  canonical_id: string | null;
}
export interface Dataset {
  id: string;
  name: string;
  status: Status;
  created_at: string;
  project_id: string;
}
export interface SourceColumn {
  id: string;
  name: string;
  source_index: number;
}
export interface Table {
  id: string;
  sheet: string;
  row_count: number;
  active_mapping_id: string | null;
  parsed: { columns: SourceColumn[]; warnings: string[]; header_row: number };
}
export interface ColumnProfile {
  column_id: string;
  name: string;
  null_count: number;
  empty_count: number;
  distinct_count: number;
  duplicate_count: number;
  samples: (string | null)[];
  type_candidates: string[];
  evidence_ids: string[];
  identifier_candidate: boolean;
}
export interface Profile {
  row_count: number;
  columns: ColumnProfile[];
  key_candidates: string[][];
}
export interface DocumentArtifact {
  artifact: { id: string; quality: string };
  source_file: { id: string; filename: string; sha256: string };
  extraction: {
    verification_status: "UNVERIFIED_EXTRACTION";
    pages: {
      page_number: number;
      markdown: string;
      items: Record<string, unknown>[];
    }[];
    usage: { credits?: number | null };
  };
  warnings: string[];
}
export type DataType = "string" | "decimal" | "date" | "enum";
export interface SchemaField {
  id: string;
  name: string;
  data_type: DataType;
  required: boolean;
  semantic_metric: string | null;
  amount_basis: string | null;
  currency: string | null;
  unit: string | null;
}
export interface Schema {
  id: string;
  workspace_id: string;
  revision: number;
  name: string;
  entity_kind: string;
  grain: string;
  fields: SchemaField[];
  business_key_fields: string[];
}
export type Transform = {
  op: string;
  [key: string]: string | boolean | string[] | undefined;
};
export interface Decision {
  source_field: string;
  candidate_target: string | null;
  decision: string;
  evidence_ids: string[];
  grain_assumption: string;
  transformation_candidate: Transform;
  unresolved_questions: string[];
  reasoning: string;
}
export interface Proposal {
  entity_kind: string;
  grain: string;
  status: string;
  decisions: Decision[];
  unresolved_questions: string[];
}
export interface Mapping {
  id: string;
  revision: number;
  status: string;
  proposal: Proposal;
  decision: { decisions: Decision[] } | null;
  schema: Schema;
}
export interface Canonical {
  id: string;
  source_table_id: string;
  mapping_revision_id: string;
  row_count: number;
  valid_count: number;
  invalid_count: number;
  quality_status: string;
  stale: boolean;
}
export interface Job {
  id: string;
  kind: string;
  status: string;
  attempts: number;
  error_code: string | null;
  result: Record<string, unknown> | null;
}
export interface Preview {
  items: Record<string, unknown>[];
  total: number;
  columns: string[];
  offset: number;
  limit: number;
  view: string;
}
export interface WorkspaceSettings {
  ai_task_allowances?: Record<"agent" | "planner" | "assistant", {workspace_used:number; configured_ceiling:number | null; remaining:number | null}>;
  agent_cloud_enabled?: boolean;
  assistant_cloud_enabled?: boolean;
  workspace_name: string;
  qwen_configured: boolean;
  qwen_model: string;
  mapping_ai_provider: "QWEN" | "GEMINI";
  gemini_model: string;
  gemini_configured: boolean;
  gemini_requests_used: number;
  gemini_requests_remaining: number | null;
  max_upload_bytes: number;
  max_upload_files: number;
  agent_max_upload_files?: number;
  agent_upload_extensions?: string[];
  cloud_live_status?: string;
  max_rows: number;
  policy: {
    mode: string;
    allow_external_ai: boolean;
    allow_cloud_parsing: boolean;
    external_request_budget: number | null;
    parser_request_budget: number;
  };
}

export const statusText: Record<string, string> = {
  RAW_UNVERIFIED: "Nguồn gốc chưa xác nhận",
  CANONICAL: "Dữ liệu đã chuẩn hóa",
  UPLOADED: "Đã tải lên",
  PARSING: "Đang đọc",
  PARSED: "Đã đọc",
  PROFILED: "Đã phân tích",
  NEEDS_MAPPING_REVIEW: "Cần xác nhận ánh xạ",
  MAPPED: "Đã duyệt ánh xạ",
  NORMALIZING: "Đang chuẩn hóa",
  READY: "Đã chuẩn hóa",
  PARTIAL: "Cần kiểm tra",
  FAILED: "Xử lý thất bại",
  PROPOSED: "Đề xuất",
  UNKNOWN: "Chưa xác định",
  AMBIGUOUS: "Cần làm rõ",
  APPROVED: "Đã xác nhận",
  REJECTED: "Đã từ chối",
  SUPERSEDED: "Đã thay thế",
  QUEUED: "Chờ xử lý",
  RUNNING: "Đang xử lý",
  RETRYABLE_FAILURE: "Chờ thử lại",
  BLOCKED: "Bị chặn",
  SUCCEEDED: "Hoàn tất",
  CANCELLED: "Đã hủy",
  VERIFIED: "Đã xác minh",
  PARTIAL_VERIFIED: "Đã xác minh một phần",
  VERIFICATION_FAILED: "Kiểm chứng thất bại",
  DRAFT: "Chờ chạy",
};
export const jobKind: Record<string, string> = {
  document_parse: "Đọc tài liệu được cấp phép",
  parse: "Đọc và phân tích",
  mapping: "AI đề xuất cách ghép cột",
  normalize: "Chuẩn hóa dữ liệu",
  reconciliation_plan: "AI đề xuất quy tắc đối soát",
  reconcile: "Đối soát và kiểm chứng",
  export: "Xuất báo cáo",
  assistant: "AI Assistant có bằng chứng",
};
export const errorText: Record<string, string> = {
  INSUFFICIENT_EVIDENCE: "Chưa đủ bằng chứng cho yêu cầu này. Hãy kiểm tra nguồn đã chọn; kết quả đối soát cần được xác minh trước khi dùng.",
  AI_INVALID_SOURCE: "AI chưa chọn đúng nguồn. Hãy kiểm tra dữ liệu trong ngữ cảnh trước khi tiếp tục.",
  AUTH_REQUIRED: "Phiên truy cập chưa hợp lệ. Hãy kết nối lại để tiếp tục.",
  FORBIDDEN: "Bạn không có quyền thực hiện thao tác này. Hãy liên hệ chủ không gian làm việc.",
  LOCAL_DEMO_NOT_VERIFIED: "Kết nối local cần được kiểm tra lại sau khi dịch vụ khởi động. Hãy chạy quy trình khởi động ứng dụng.",
  AI_DELIVERY_UNKNOWN: "Chưa xác định dịch vụ AI đã nhận yêu cầu hay chưa. Không tự gửi lại để tránh xử lý trùng; hãy cập nhật hội thoại.",
  WORKER_INTERNAL_ERROR: "Xử lý nền gặp lỗi. Kết quả đã lưu được giữ; hãy cập nhật hội thoại và liên hệ hỗ trợ nếu lỗi tiếp tục.",
  JOB_RETRY_EXHAUSTED: "Công việc đã dừng sau các lần phục hồi không thành công. Hãy kiểm tra kết quả đã lưu trước khi tạo yêu cầu mới.",
  QUERY_FIELD_INVALID: "Trường được yêu cầu không có trong nguồn đang chọn. Hãy kiểm tra nguồn và chỉ tiêu cần xem.",
  QUERY_METRIC_AMBIGUOUS: "Có nhiều chỉ tiêu tiền phù hợp. Hãy chọn chỉ tiêu bạn muốn xem.",
  QUERY_METRIC_UNAVAILABLE: "Nguồn này chưa có chỉ tiêu tiền được duyệt để tính kết quả.",
  QUERY_SEMANTICS_REQUIRED: "Yêu cầu chưa khớp ý nghĩa dữ liệu đã duyệt. Cần làm rõ chỉ tiêu hoặc trạng thái trước khi tra cứu.",
  INPUT_AMBIGUOUS: "Cần bổ sung thông tin để xác định đúng yêu cầu.",
  STALE_CONTEXT: "Nguồn hoặc lựa chọn đã thay đổi. Hãy mở lại câu hỏi đang chờ để tiếp tục.",
  AI_INVALID_INTENT_COUNT: "AI chưa phân chia yêu cầu đúng cách; hệ thống đã dừng trước khi thực hiện.",
  INVALID_SOURCE_FIELD: "Đề xuất AI chưa khớp các cột nguồn; hệ thống đã dừng trước khi chuẩn hóa.",
  PARSER_BUDGET_EXHAUSTED:
    "Đã hết lượt đọc tài liệu được cấp phép. Kết quả đã lưu vẫn được giữ.",
  PARSER_CREDITS_NOT_VERIFIED:
    "Chưa kiểm tra được quyền sử dụng dịch vụ đọc tài liệu. Tệp gốc được giữ nguyên.",
  CLOUD_PARSING_DISABLED:
    "Chưa được phép đọc tài liệu mới qua dịch vụ bên ngoài. Bạn vẫn có thể xem kết quả đã lưu.",
  LLAMAPARSE_POLL_TIMEOUT:
    "Tài liệu vẫn chưa có kết quả trong thời gian chờ. Yêu cầu đã gửi được giữ lại để tránh xử lý trùng.",
  GEMINI_RATE_LIMITED: "Dịch vụ AI đang giới hạn yêu cầu. Hãy thử lại sau; dữ liệu và kết quả đã lưu vẫn được giữ.",
  QWEN_RATE_LIMITED: "Dịch vụ AI đang giới hạn yêu cầu. Hãy thử lại sau.",
  GEMINI_KEY_MISSING: "Hỗ trợ AI hiện chưa được thiết lập. Bạn vẫn có thể kiểm tra và ghép cột thủ công.",
  GEMINI_HTTP_ERROR:
    "Dịch vụ AI chưa chấp nhận yêu cầu. Bạn có thể tiếp tục xem dữ liệu và kiểm tra quyền sử dụng.",
  GEMINI_UNAVAILABLE: "Dịch vụ AI chưa phản hồi. Yêu cầu đã gửi không được tự gửi lại; dữ liệu của bạn vẫn được giữ.",
  CLOUD_AI_DISABLED: "Không gian làm việc chưa cho phép sử dụng dịch vụ AI bên ngoài.",
  CLOUD_BUDGET_EXHAUSTED:
    "Tác vụ AI hiện chưa được phép tiếp tục. Bạn vẫn có thể xem dữ liệu và dùng quy tắc đã duyệt.",
  QWEN_ACCESS_DENIED:
    "Dịch vụ AI chưa cho phép kết nối từ ứng dụng. Bạn vẫn có thể ghép cột thủ công.",
  QWEN_UNAVAILABLE: "Dịch vụ AI chưa phản hồi. Bạn vẫn có thể ghép cột thủ công.",
  QWEN_NOT_CONFIGURED: "Dịch vụ AI hiện chưa được thiết lập. Bạn vẫn có thể ghép cột thủ công.",
  AI_INVALID_JSON: "Đề xuất AI chưa đủ rõ để sử dụng an toàn. Hãy kiểm tra dữ liệu hoặc bổ sung yêu cầu.",
  INVALID_EVIDENCE:
    "AI trả bằng chứng không hợp lệ. Đề xuất chưa được sử dụng.",
};
export const qualityText: Record<string, string> = {
  CURRENCY_MISMATCH: "Tiền tệ khác định nghĩa đã duyệt",
  INVALID_DECIMAL: "Số tiền không hợp lệ",
  DECIMAL_PRECISION_EXCEEDED: "Số vượt độ chính xác cho phép",
  NULL: "Chưa có giá trị",
  REQUIRED_NULL: "Thiếu giá trị bắt buộc",
  INVALID: "Không hợp lệ",
  INVALID_DATE: "Ngày cần kiểm tra",
  DATE_FORMAT_INVALID: "Cấu hình định dạng ngày không hợp lệ",
  TIMEZONE_INVALID: "Múi giờ không tồn tại",
  TIMEZONE_DATABASE_UNAVAILABLE: "Môi trường thiếu dữ liệu múi giờ",
  AMBIGUOUS_LOCAL_TIME: "Thời điểm mơ hồ do đổi giờ",
  NONEXISTENT_LOCAL_TIME: "Thời điểm không tồn tại do đổi giờ",
  DATE_OFFSET_MISMATCH: "Offset khác múi giờ đã duyệt",
  MAPPING_PREFLIGHT_REQUIRED: "Cần hoàn tất kiểm tra trước chuẩn hóa",
  UNKNOWN_ENUM: "Danh mục chưa xác định",
  ARITHMETIC_NULL: "Phép tính thiếu đầu vào",
};
export const warningText: Record<string, string> = {
  HEADER_INFERRED_REVIEW:
    "Tiêu đề được phát hiện sau phần ghi chú; hãy kiểm tra vùng bảng.",
  FORMULA_UNVERIFIED:
    "Có ô công thức: giá trị cache chưa được xác minh. Hệ thống không chạy công thức.",
  HIDDEN_SHEET_REVIEW: "Sheet ẩn được giữ lại để kiểm tra.",
  MERGED_CELLS_REVIEW: "Có ô gộp; cần xác nhận cấu trúc bảng.",
  EMPTY_OR_DUPLICATE_HEADER:
    "Có tiêu đề trống hoặc trùng; cột được định danh riêng.",
  EXCEL_DATE_SERIAL_REVIEW:
    "Có ngày Excel dạng số: cần xác nhận cách chuyển đổi.",
  CELL_ERROR_UNVERIFIED: "Có ô Excel báo lỗi; không tự thay thế giá trị.",
};
