// Phiên làm việc đang mở trong tab này. Mọi lời gọi API gửi kèm mã phiên (header
// X-Workspace-Id; luồng SSE và liên kết tải tệp dùng tham số ?workspace=) để backend chỉ làm
// việc với dữ liệu của phiên đó. Lựa chọn được nhớ trong trình duyệt cho lần mở sau.

const STORAGE_KEY = "studio.workspace";

let current: string | null = readStored();

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // trình duyệt chặn lưu trữ: mỗi lần mở dùng phiên đầu tiên
  }
}

export function workspaceId(): string | null {
  return current;
}

/** Ghi phiên đang mở (gọi khi khởi động đã biết danh sách phiên, hoặc khi đổi phiên). */
export function setWorkspaceId(id: string | null): void {
  current = id;
  try {
    if (id) window.localStorage.setItem(STORAGE_KEY, id);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Không nhớ được: chỉ mất việc mở lại đúng phiên ở lần sau.
  }
}

/** Phiên mà tab này nhớ từ lần trước (có thể đã bị xóa; nơi gọi tự kiểm). */
export function rememberedWorkspace(): string | null {
  return readStored();
}

/** Mở một phiên: tải lại ứng dụng từ Dashboard để mọi trang đọc dữ liệu của phiên mới, không
 *  còn trạng thái nào của phiên cũ (cuộc trò chuyện đang mở, luồng SSE, bộ lọc…). */
export function openWorkspace(id: string, path = "/"): void {
  setWorkspaceId(id);
  window.location.assign(path);
}

export function workspaceHeaders(): Record<string, string> {
  return current ? { "X-Workspace-Id": current } : {};
}

/** Thêm ?workspace= cho đường dẫn không gửi được header (EventSource, liên kết tải tệp). */
export function withWorkspace(path: string): string {
  if (!current) return path;
  return `${path}${path.includes("?") ? "&" : "?"}workspace=${encodeURIComponent(current)}`;
}
