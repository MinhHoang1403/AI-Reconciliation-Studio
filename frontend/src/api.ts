export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status?: number,
  ) {
    super(message);
  }
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET" && !headers.has("Idempotency-Key"))
    headers.set("Idempotency-Key", crypto.randomUUID());
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      signal:
        !init.method || init.method === "GET"
          ? AbortSignal.any([
              ...(init.signal ? [init.signal] : []),
              AbortSignal.timeout(30000),
            ])
          : init.signal,
      headers,
      credentials: "same-origin",
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError")
      throw new ApiError(
        "API_TIMEOUT",
        "Máy chủ phản hồi quá lâu. Hãy cập nhật hoặc thử lại.",
      );
    if (err instanceof TypeError)
      throw new ApiError(
        "NETWORK_ERROR",
        "Không kết nối được máy chủ. Hãy kiểm tra kết nối rồi thử lại.",
      );
    throw err;
  }
  const body = await response.json();
  if (!response.ok)
    throw new ApiError(
      body.code || "HTTP_ERROR",
      body.message_vi || "Không thể tải dữ liệu.",
      response.status,
    );
  return body as T;
}

/** Collect cursor pages for metadata selectors, preserving stable source identifiers. */
export async function apiPages<T>(path: string, init: RequestInit = {}): Promise<T[]> {
  const items: T[] = [];
  const seen = new Set<string>();
  let cursor: string | null = null;
  do {
    const separator = path.includes("?") ? "&" : "?";
    const url = cursor ? `${path}${separator}after_id=${encodeURIComponent(cursor)}` : path;
    const page: { items: T[]; next_cursor?: string | null } = await api(url, init);
    items.push(...page.items);
    cursor = page.next_cursor ?? null;
    if (cursor && seen.has(cursor))
      throw new ApiError("PAGINATION_STALLED", "Danh sách chưa tải đủ. Hãy cập nhật lại.");
    if (cursor) seen.add(cursor);
  } while (cursor);
  return items;
}
