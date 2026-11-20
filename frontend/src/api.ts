// Kiểu dữ liệu và hàm gọi API backend. Mọi đường dẫn đi qua Nginx cùng địa chỉ (/api).

export type ProviderState = "CONFIGURED" | "NEEDS_CONFIGURATION";

export type SystemStatus = {
  revision: string;
  database: "ok" | "unavailable";
  gemini: { name: string; model: string; state: ProviderState };
};

export async function fetchSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  const reply = await fetch("/api/status", { signal });
  if (!reply.ok) throw new Error(`Backend trả lỗi ${reply.status}`);
  return (await reply.json()) as SystemStatus;
}
