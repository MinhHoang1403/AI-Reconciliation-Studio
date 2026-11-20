import { useEffect, useState } from "react";
import type { LucideIcon } from "lucide-react";
import { BarChart3, Database, GitCompareArrows, LayoutDashboard, MessagesSquare } from "lucide-react";

// Các trang chính của ứng dụng; đường dẫn tiếng Việt không dấu để URL dễ đọc.
export type Route = { path: string; label: string; icon: LucideIcon };

export const ROUTES: readonly Route[] = [
  { path: "/", label: "Tổng quan", icon: LayoutDashboard },
  { path: "/assistant", label: "Assistant", icon: MessagesSquare },
  { path: "/du-lieu", label: "Dữ liệu", icon: Database },
  { path: "/doi-soat", label: "Đối soát", icon: GitCompareArrows },
  { path: "/bao-cao", label: "Báo cáo", icon: BarChart3 },
];

/** Đường dẫn hiện tại, cập nhật khi bấm liên kết nội bộ hoặc nút Back/Forward. */
export function usePath(): string {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const sync = () => setPath(window.location.pathname);
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);
  return path;
}

/** Chuyển trang không tải lại toàn bộ ứng dụng. */
export function navigate(path: string): void {
  if (path === window.location.pathname) return;
  window.history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo({ top: 0 });
}
