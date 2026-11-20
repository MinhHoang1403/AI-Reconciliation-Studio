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
