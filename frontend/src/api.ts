export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET")
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
    );
  return body as T;
}
