// Kiểu dữ liệu và hàm gọi API backend. Mọi đường dẫn đi qua Nginx cùng địa chỉ (/api).

export type ProviderState = "CONFIGURED" | "NEEDS_CONFIGURATION";

export type SystemStatus = {
  revision: string;
  database: "ok" | "unavailable";
  gemini: { name: string; model: string; state: ProviderState };
};

export type DatasetStatus = "READING" | "READY" | "FAILED";
export type TableStatus = "READING" | "READY" | "NO_DATA" | "FAILED";

export type TableSummary = {
  id: string;
  sheet_name: string | null;
  position: number;
  status: TableStatus;
  header_row: number | null;
  header_row_chosen_by_user: boolean;
  row_count: number;
  column_count: number;
  error_message: string | null;
  mapping_status: "NONE" | "MAPPING" | "READY";
  table_kind: string | null;
  mapping_pending: number;
  clean_status: "NONE" | "BUILDING" | "SUGGESTING" | "READY" | "FAILED";
  clean_open: number;
};

export type CleaningIssue = {
  id: string;
  kind: "DUPLICATE_ROW" | "INVALID_VALUE" | "MISSING_VALUE" | "CONFLICTING_VALUES";
  level: "SUGGEST" | "ASK";
  field_key: string | null;
  field_label: string | null;
  row_refs: number[];
  values: (string | null)[];
  message: string;
  status: "OPEN" | "RESOLVED";
  ai_suggestion: { value: string | null; confidence: number; reason: string } | null;
};

export type CleaningFix = {
  field_key: string;
  field_label: string;
  fix: string;
  fix_label: string;
  count: number;
  examples: { row_ref: number; before: string | null; after: string | null }[];
};

export type Cleaning = {
  table_id: string;
  status: "NONE" | "BUILDING" | "SUGGESTING" | "READY" | "FAILED";
  version: number | null;
  row_count: number;
  excluded_count: number;
  summary: {
    fixes: CleaningFix[];
    empty_rows: number[];
    cancelled_count: number;
    date_orders: {
      field_key: string;
      field_label: string;
      order: "DMY" | "MDY";
      defaulted: boolean;
      chosen_by_user: boolean;
    }[];
  } | null;
  open_counts: { SUGGEST: number; ASK: number };
  issues: CleaningIssue[];
};

export type CleanRows = {
  columns: { key: string; label: string; type: string }[];
  row_refs: number[];
  rows: (string | null)[][];
  offset: number;
  limit: number;
  total: number;
};

export type MappingStatus = "AUTO" | "SUGGESTED" | "CONFIRMED";
export type MappingSource = "RULE" | "AI" | "RULE_AI" | "MEMORY" | "USER";

export type ColumnMapping = {
  position: number;
  column_name: string;
  field_key: string | null;
  field_label: string | null;
  confidence: number;
  status: MappingStatus;
  source: MappingSource;
  reason: string | null;
  candidates: { field: string; label: string; score: number }[];
};

export type TableMapping = {
  table_id: string;
  status: "NONE" | "MAPPING" | "READY";
  table_kind: string | null;
  table_kind_label: string | null;
  ai_state: "AI" | "MEMORY" | "NOT_CONFIGURED" | "FAILED" | null;
  ai_message: string | null;
  pending_count: number;
  columns: ColumnMapping[];
  fields: { key: string; label: string; type: string }[];
};

export type DatasetSummary = {
  id: string;
  name: string;
  original_filename: string;
  file_format: "CSV" | "XLSX";
  size_bytes: number;
  sha256: string;
  status: DatasetStatus;
  error_message: string | null;
  created_at: string;
  tables: TableSummary[];
};

export type UploadReply = { dataset: DatasetSummary; duplicate: boolean };

export type RowsPage = {
  table_id: string;
  columns: string[];
  row_refs: number[];
  rows: (string | null)[][];
  offset: number;
  limit: number;
  total: number;
};

export type ObservedKind = "EMPTY" | "NUMBER" | "DATE" | "PHONE" | "CODE" | "TEXT";

export type ColumnProfile = {
  name: string;
  position: number;
  filled_count: number;
  empty_count: number;
  distinct_count: number;
  max_length: number;
  kind: ObservedKind;
  has_leading_zero: boolean;
  samples: string[];
};

export type TableProfile = {
  table_id: string;
  row_count: number;
  blank_row_count: number;
  columns: ColumnProfile[];
};

/** Lỗi từ backend, mang thông điệp tiếng Việt để hiện cho người dùng. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function errorFrom(reply: Response): Promise<ApiError> {
  try {
    const body = (await reply.json()) as { detail?: { message?: string } };
    if (body.detail?.message) return new ApiError(body.detail.message, reply.status);
  } catch {
    // Không đọc được nội dung lỗi; dùng thông điệp chung bên dưới.
  }
  return new ApiError(`Máy chủ trả lỗi ${reply.status}. Hãy thử lại.`, reply.status);
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const reply = await fetch(path, { signal });
  if (!reply.ok) throw await errorFrom(reply);
  return (await reply.json()) as T;
}

async function sendJson<T>(path: string, method: string, body?: unknown): Promise<T> {
  const reply = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!reply.ok) throw await errorFrom(reply);
  return (reply.status === 204 ? undefined : await reply.json()) as T;
}

export const fetchSystemStatus = (signal?: AbortSignal) => getJson<SystemStatus>("/api/status", signal);
export const listDatasets = (signal?: AbortSignal) => getJson<DatasetSummary[]>("/api/datasets", signal);
export const getDataset = (id: string, signal?: AbortSignal) =>
  getJson<DatasetSummary>(`/api/datasets/${id}`, signal);
export const getRows = (tableId: string, offset: number, limit: number, signal?: AbortSignal) =>
  getJson<RowsPage>(`/api/tables/${tableId}/rows?offset=${offset}&limit=${limit}`, signal);
export const getProfile = (tableId: string, signal?: AbortSignal) =>
  getJson<TableProfile>(`/api/tables/${tableId}/profile`, signal);
export const deleteDataset = (id: string) => sendJson<undefined>(`/api/datasets/${id}`, "DELETE");
export const rereadDataset = (id: string) => sendJson<DatasetSummary>(`/api/datasets/${id}/read`, "POST");
export const getMapping = (tableId: string, signal?: AbortSignal) =>
  getJson<TableMapping>(`/api/tables/${tableId}/mapping`, signal);
export const chooseMappingField = (tableId: string, position: number, fieldKey: string | null) =>
  sendJson<TableMapping>(`/api/tables/${tableId}/mapping/columns/${position}`, "PUT", { field_key: fieldKey });
export const confirmMapping = (tableId: string) =>
  sendJson<TableMapping>(`/api/tables/${tableId}/mapping/confirm`, "POST");
export const suggestMappingAgain = (tableId: string) =>
  sendJson<TableMapping>(`/api/tables/${tableId}/mapping/suggest`, "POST");
export const getCleaning = (tableId: string, signal?: AbortSignal) =>
  getJson<Cleaning>(`/api/tables/${tableId}/cleaning`, signal);
export const getCleanRows = (tableId: string, offset: number, limit: number, signal?: AbortSignal) =>
  getJson<CleanRows>(`/api/tables/${tableId}/clean-rows?offset=${offset}&limit=${limit}`, signal);
export const fixCell = (tableId: string, rowRef: number, fieldKey: string, value: string) =>
  sendJson<Cleaning>(`/api/tables/${tableId}/cleaning/cells`, "POST", {
    row_ref: rowRef,
    field_key: fieldKey,
    value,
  });
export const acceptCellSuggestion = (tableId: string, rowRef: number, fieldKey: string) =>
  sendJson<Cleaning>(
    `/api/tables/${tableId}/cleaning/suggestions/accept?row_ref=${rowRef}&field_key=${encodeURIComponent(fieldKey)}`,
    "POST",
  );
export const decideRows = (tableId: string, rowRefs: number[], decision: "EXCLUDE" | "KEEP" | "UNDO") =>
  sendJson<Cleaning>(`/api/tables/${tableId}/cleaning/rows`, "POST", { row_refs: rowRefs, decision });
export const acceptDuplicates = (tableId: string) =>
  sendJson<Cleaning>(`/api/tables/${tableId}/cleaning/duplicates/accept`, "POST");
export const chooseDateOrder = (tableId: string, fieldKey: string, order: "DMY" | "MDY") =>
  sendJson<Cleaning>(`/api/tables/${tableId}/cleaning/date-order`, "PUT", { field_key: fieldKey, order });
export const rebuildCleaning = (tableId: string) =>
  sendJson<Cleaning>(`/api/tables/${tableId}/cleaning/rebuild`, "POST");
export const chooseHeaderRow = (tableId: string, headerRow: number | null) =>
  sendJson<TableSummary>(`/api/tables/${tableId}/header-row`, "PUT", { header_row: headerRow });

/**
 * Tải một tệp lên, báo tiến độ (0–1) qua `onProgress`.
 * Dùng XMLHttpRequest vì fetch chưa báo được tiến độ gửi dữ liệu.
 */
export function uploadDataset(file: File, onProgress: (share: number) => void): Promise<UploadReply> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/api/datasets");
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    request.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(request.responseText);
      } catch {
        // Nội dung không phải JSON; xử lý như lỗi chung.
      }
      if (request.status >= 200 && request.status < 300) {
        resolve(body as UploadReply);
        return;
      }
      const message = (body as { detail?: { message?: string } } | null)?.detail?.message;
      reject(new ApiError(message ?? `Tải lên thất bại (mã ${request.status}).`, request.status));
    };
    request.onerror = () => reject(new ApiError("Mất kết nối tới máy chủ khi tải tệp.", 0));
    const form = new FormData();
    form.append("file", file);
    request.send(form);
  });
}

// ---------------------------------------------------------------- đối soát (Giai đoạn 4)

export type ReconKind =
  | "MATCHED"
  | "MANY_TO_ONE"
  | "ONE_TO_MANY"
  | "AMBIGUOUS"
  | "PENDING_SETTLEMENT"
  | "AMOUNT_MISMATCH"
  | "DUPLICATE"
  | "ONLY_IN_A"
  | "ONLY_IN_B"
  | "NEEDS_CLEANING"
  | "OUT_OF_SCOPE";

export type ReconTable = {
  id: string;
  label: string;
  table_kind: string | null;
  table_kind_label: string;
  row_count: number;
  clean_open: number;
};

export type ScopeOption = {
  side: "LEFT" | "RIGHT";
  field: string;
  value: string;
  rows: number;
  matched: number;
  excluded: boolean;
};

export type ReconConfig = {
  key_left: string | null;
  key_right: string | null;
  amount_left: string;
  amount_right: string;
  date_left: string | null;
  date_right: string | null;
  tolerance: string;
  date_window_days: number;
  min_score: number;
  excluded: Partial<Record<"LEFT" | "RIGHT", Record<string, string[]>>>;
  labels: Record<string, string | null>;
  description: string[];
  scope_options: ScopeOption[];
  extract: { source: string; kind: "code" | "date"; pattern: string } | null;
  group_left: boolean;
  settle_days: number;
};

export type VerificationCheck = { code: string; label: string; passed: boolean; detail: string };
export type Verification = { passed: boolean; checks: VerificationCheck[]; error?: string };

export type ReconRun = {
  id: string;
  chain_id: string | null;
  carried_count: number;
  status: "RUNNING" | "READY" | "FAILED";
  error_message: string | null;
  left: ReconTable | null;
  right: ReconTable | null;
  config: ReconConfig;
  period_start: string | null;
  period_end: string | null;
  summary: {
    counts: Record<ReconKind, number>;
    rows: Record<ReconKind, { A: number; B: number }>;
    amounts: Record<ReconKind, { A: string; B: string }>;
    total_results: number;
    needs_review: number;
  } | null;
  verification: Verification | null;
  exceptions: { OPEN: number; EXPLAINED: number; RESOLVED: number };
  open_by_kind: Record<ReconKind, number>;
  group_counts: Record<ResultGroup, number>;
  kind_labels: Record<ReconKind, string>;
  created_at: string | null;
  finished_at: string | null;
};

export type ResultRow = {
  row_ref: number;
  key?: string | null;
  date?: string | null;
  amount?: string | null;
  customer_name?: string | null;
  payment_method?: string | null;
  status?: string | null;
  description?: string | null;
  payment_id?: string | null;
  carried?: boolean;  // dòng chờ tiền về mang từ kỳ trước
  table_label?: string | null;
};

export type ReconResult = {
  id: string;
  kind: ReconKind;
  kind_label: string;
  score: number | null;
  reasons: {
    code: string;
    text: string;
    pairs?: { left: number[]; right: number[]; score: number | null }[];
  }[];
  amount_left: string | null;
  amount_right: string | null;
  exception_status: "OPEN" | "EXPLAINED" | "RESOLVED" | null;
  note: string | null;
  left: ResultRow[];
  right: ResultRow[];
};

export type ResultGroup = "todo" | "explained" | "resolved" | "matched" | "pending" | "out_of_scope";
export type ResultsPage = { total: number; offset: number; limit: number; items: ReconResult[] };

export type AuditEntry = {
  id: string;
  created_at: string | null;
  actor: string;
  action: string;
  object_type: string;
  object_id: string;
  object_label: string;
  summary: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
};
export type AuditPage = { total: number; offset: number; limit: number; items: AuditEntry[] };

type Pair = { left_table_id: string; right_table_id: string };

export const getReconTables = (signal?: AbortSignal) =>
  getJson<{ tables: ReconTable[]; suggested: Pair | null }>("/api/recon/tables", signal);
export const previewRecon = (pair: Pair) =>
  sendJson<{ left: ReconTable; right: ReconTable; config: ReconConfig }>("/api/recon/preview", "POST", pair);
export const explainPreview = (pair: Pair) => sendJson<{ text: string }>("/api/recon/preview/explain", "POST", pair);
export const startRun = (
  body: Pair & { tolerance?: string; date_window_days?: number; excluded?: ReconConfig["excluded"] },
) => sendJson<ReconRun>("/api/recon/runs", "POST", body);
export const listRuns = (limit: number, signal?: AbortSignal) =>
  getJson<ReconRun[]>(`/api/recon/runs?limit=${limit}`, signal);
export const getRun = (id: string, signal?: AbortSignal) => getJson<ReconRun>(`/api/recon/runs/${id}`, signal);
export const getResults = (
  runId: string,
  group: ResultGroup,
  offset: number,
  limit: number,
  signal?: AbortSignal,
) => getJson<ResultsPage>(`/api/recon/runs/${runId}/results?group=${group}&offset=${offset}&limit=${limit}`, signal);
export const verifyRun = (id: string) => sendJson<ReconRun>(`/api/recon/runs/${id}/verify`, "POST");
export const actOnResults = (
  runId: string,
  body: { action: "RESOLVE" | "REOPEN"; result_ids?: string[]; kind?: ReconKind },
) => sendJson<ReconRun>(`/api/recon/runs/${runId}/actions`, "POST", body);
export const saveNote = (resultId: string, note: string) =>
  sendJson<{ id: string; note: string | null; exception_status: ReconResult["exception_status"] }>(
    `/api/recon/results/${resultId}/note`,
    "PUT",
    { note },
  );
export const explainResult = (resultId: string) =>
  sendJson<{ text: string }>(`/api/recon/results/${resultId}/explain`, "POST");
// ---------------------------------------------------------------- chuỗi ba bên (Giai đoạn 5)

export type ReconPeriod = {
  label: string;
  period_start: string;
  period_end: string;
  tables: ReconTable[];
  chain_id: string | null;
};

export type ReconChain = {
  id: string;
  status: "RUNNING" | "READY" | "FAILED";
  error_message: string | null;
  label: string;
  table_ids: string[];
  period_start: string | null;
  period_end: string | null;
  runs: ReconRun[];
  exceptions: { OPEN: number; EXPLAINED: number; RESOLVED: number };
  pending: number;
  verified: boolean;
  created_at: string | null;
};

export type TraceStep = {
  run_id: string;
  pair: string;
  kind: ReconKind;
  result_id: string;
  left_refs: number[];
  right_refs: number[];
  reason: string;
};

export const getPeriods = (signal?: AbortSignal) => getJson<ReconPeriod[]>("/api/recon/periods", signal);
export const startChain = (tableIds: string[], label: string) =>
  sendJson<ReconChain>("/api/recon/chains", "POST", { table_ids: tableIds, label });
export const getChain = (id: string, signal?: AbortSignal) => getJson<ReconChain>(`/api/recon/chains/${id}`, signal);
export const traceRow = (chainId: string, tableId: string, rowRef: number) =>
  getJson<{ steps: TraceStep[] }>(`/api/recon/chains/${chainId}/trace?table_id=${tableId}&row_ref=${rowRef}`);
export const chooseCandidate = (runId: string, resultId: string, leftRefs: number[], rightRefs: number[]) =>
  sendJson<Rerun>(`/api/recon/runs/${runId}/choose`, "POST", {
    result_id: resultId,
    left_refs: leftRefs,
    right_refs: rightRefs,
  });

// Ghép tay, gỡ ghép: lưu quyết định rồi hệ thống chạy lại chuỗi (hoặc cặp) và trả mã mới.
export type Rerun = { chain_id: string | null; run_id: string | null };

export type MatchCandidates = {
  side: "A" | "B";  // bên của các ứng viên
  target: ResultRow;
  candidates: { result_id: string; row: ResultRow; amount_gap: string | null }[];
};

export const getMatchCandidates = (resultId: string, signal?: AbortSignal) =>
  getJson<MatchCandidates>(`/api/recon/results/${resultId}/match-candidates`, signal);

export const manualMatch = (runId: string, leftRefs: number[], rightRefs: number[]) =>
  sendJson<Rerun>(`/api/recon/runs/${runId}/match`, "POST", { left_refs: leftRefs, right_refs: rightRefs });

export const unmatchResult = (resultId: string) => sendJson<Rerun>(`/api/recon/results/${resultId}/unmatch`, "POST");

export const getAudit = (offset: number, limit: number, signal?: AbortSignal) =>
  getJson<AuditPage>(`/api/audit?offset=${offset}&limit=${limit}`, signal);

// ---------------------------------------------------------------- AI Assistant (Giai đoạn 6)

export type ChatStep = { label: string; status: "RUNNING" | "DONE" | "FAILED" };
export type ChatAction = {
  id: string;
  title: string;
  detail: string;
  status: "PENDING" | "DONE" | "CANCELLED" | "FAILED";
  result: string | null;
};
export type ChatLink = { label: string; path: string };
export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  status: "RUNNING" | "DONE" | "FAILED";
  attachments: { dataset_id: string; name: string }[];
  steps: ChatStep[];
  actions: ChatAction[];
  links: ChatLink[];
  created_at: string | null;
};
export type ChatThreadSummary = { id: string; title: string; running: boolean; updated_at: string | null };
export type ChatThread = ChatThreadSummary & { messages: ChatMessage[] };

export const listThreads = (signal?: AbortSignal) => getJson<ChatThreadSummary[]>("/api/assistant/threads", signal);
export const createThread = () => sendJson<ChatThread>("/api/assistant/threads", "POST", {});
export const getThread = (id: string, signal?: AbortSignal) => getJson<ChatThread>(`/api/assistant/threads/${id}`, signal);
export const deleteThread = (id: string) => sendJson<undefined>(`/api/assistant/threads/${id}`, "DELETE");
export const sendChat = (id: string, text: string, datasetIds: string[]) =>
  sendJson<ChatThread>(`/api/assistant/threads/${id}/messages`, "POST", { text, dataset_ids: datasetIds });
export const decideAction = (messageId: string, actionId: string, decision: "CONFIRM" | "CANCEL") =>
  sendJson<ChatThread>(`/api/assistant/messages/${messageId}/actions/${actionId}`, "POST", { decision });
