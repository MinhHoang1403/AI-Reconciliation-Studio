import { createContext, useContext } from "react";

import type { Workspace } from "./api";

// Danh sách phiên làm việc và phiên đang mở, dùng chung cho bộ chọn phiên và trang Quản lý
// phiên. App tải danh sách một lần lúc khởi động (trước khi mở trang nào) và tải lại sau mỗi
// lần tạo, đổi tên, xóa.

export type WorkspaceState = {
  workspaces: Workspace[];
  current: Workspace;
  refresh: () => Promise<void>;
};

export const WorkspaceContext = createContext<WorkspaceState | null>(null);

export function useWorkspaces(): WorkspaceState {
  const state = useContext(WorkspaceContext);
  if (!state) throw new Error("useWorkspaces phải nằm trong WorkspaceContext");
  return state;
}
