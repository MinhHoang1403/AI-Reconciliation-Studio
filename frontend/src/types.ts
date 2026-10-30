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
  assistant_cloud_enabled?: boolean;
  workspace_name: string;
  qwen_configured: boolean;
  qwen_model: string;
  mapping_ai_provider: "QWEN" | "GEMINI";
  gemini_model: string;
  gemini_configured: boolean;
  gemini_requests_used: number;
  gemini_requests_remaining: number;
  max_upload_bytes: number;
  max_upload_files: number;
  max_rows: number;
  policy: {
    mode: string;
    allow_external_ai: boolean;
    allow_cloud_parsing: boolean;
    external_request_budget: number;
    parser_request_budget: number;
  };
}

export const statusText: Record<string, string> = {
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
  document_parse: "Đọc tài liệu có allowance",
  parse: "Đọc và phân tích",
  mapping: "AI đề xuất ánh xạ",
  normalize: "Chuẩn hóa dữ liệu",
  reconciliation_plan: "AI đề xuất quy tắc đối soát",
  reconcile: "Đối soát và kiểm chứng",
  export: "Xuất báo cáo",
  assistant: "Trợ lý có bằng chứng",
};
export const errorText: Record<string, string> = {
  PARSER_BUDGET_EXHAUSTED:
    "Hết allowance LlamaParse. Không tạo thêm job tính phí.",
  PARSER_CREDITS_NOT_VERIFIED:
    "Chưa xác minh được credits LlamaParse. Tệp gốc được giữ nguyên.",
  CLOUD_PARSING_DISABLED:
    "Chưa có quyền tạo job LlamaParse. Kết quả đã lưu vẫn đọc được.",
  LLAMAPARSE_POLL_TIMEOUT:
    "Tài liệu chưa hoàn tất trong thời gian chờ. Không gửi lại job tính phí.",
  GEMINI_KEY_MISSING: "Chưa cấu hình khóa Gemini. Có thể dùng ánh xạ thủ công.",
  GEMINI_HTTP_ERROR:
    "Gemini từ chối yêu cầu. Cần kiểm tra khóa, model hoặc quyền truy cập.",
  GEMINI_UNAVAILABLE: "Gemini chưa phản hồi. Có thể dùng ánh xạ thủ công.",
  CLOUD_AI_DISABLED: "Workspace chưa được cấp quyền AI cloud.",
  CLOUD_BUDGET_EXHAUSTED:
    "Đã hết ngân sách request Gemini. Có thể duyệt ánh xạ thủ công.",
  QWEN_ACCESS_DENIED:
    "Qwen từ chối IP truy cập. Bạn vẫn có thể xác nhận ánh xạ thủ công.",
  QWEN_UNAVAILABLE: "Qwen chưa phản hồi. Bạn vẫn có thể chỉnh ánh xạ thủ công.",
  QWEN_NOT_CONFIGURED: "Chưa cấu hình Qwen. Có thể dùng ánh xạ thủ công.",
  AI_INVALID_JSON: "Phản hồi AI sai định dạng. Cần kiểm tra ánh xạ thủ công.",
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
