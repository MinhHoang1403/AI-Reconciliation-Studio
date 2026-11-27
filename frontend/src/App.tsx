import { useCallback, useEffect, useMemo, useState } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

import { listWorkspaces, type Workspace } from "./api";
import { WorkspaceSwitcher } from "./components/WorkspaceSwitcher";

import { AssistantPage } from "./pages/AssistantPage";
import { DataPage } from "./pages/DataPage";
import { DatasetPage } from "./pages/DatasetPage";
import { HistoryPage } from "./pages/HistoryPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ReconcilePage } from "./pages/ReconcilePage";
import { ReportsPage } from "./pages/ReportsPage";
import { WorkspacesPage } from "./pages/WorkspacesPage";
import { ROUTES, navigate, sectionOf, usePath } from "./navigation";
import { rememberedWorkspace, setWorkspaceId } from "./workspace";
import { WorkspaceContext, type WorkspaceState } from "./WorkspaceContext";

// Khung ứng dụng: thanh điều hướng (bên trái trên máy tính, dưới đáy trên điện thoại)
// và vùng nội dung của trang đang mở.

const PAGES: Record<string, () => React.JSX.Element> = {
  "/": OverviewPage,
  "/assistant": AssistantPage,
  "/du-lieu": DataPage,
  "/doi-soat": ReconcilePage,
  "/bao-cao": ReportsPage,
  "/lich-su": HistoryPage,
  "/phien": WorkspacesPage,
};

// Trạng thái thu gọn thanh bên được nhớ trong trình duyệt của người dùng.
// localStorage có thể bị chặn (chế độ ẩn danh), khi đó chỉ dùng giá trị mặc định.
const RAIL_STORAGE_KEY = "studio.rail-collapsed";

function readRailCollapsed(): boolean {
  try {
    return window.localStorage.getItem(RAIL_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function saveRailCollapsed(collapsed: boolean): void {
  try {
    window.localStorage.setItem(RAIL_STORAGE_KEY, collapsed ? "1" : "0");
  } catch {
    // Không lưu được thì lần sau mở lại ở trạng thái mặc định; không ảnh hưởng chức năng.
  }
}

/** Danh sách phiên và phiên đang mở. Trang chỉ hiện khi đã biết phiên, để mọi lời gọi API
 *  đầu tiên đã mang đúng mã phiên. Phiên nhớ từ lần trước không còn (đã xóa) thì mở phiên
 *  đầu tiên trong danh sách. */
function useWorkspaceState(): { state: WorkspaceState | null; error: string | null } {
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(
    () =>
      listWorkspaces()
        .then((found) => {
          setWorkspaces(found);
          setError(null);
        })
        .catch(() => {
          setError("Không tải được danh sách phiên làm việc. Hãy kiểm tra hệ thống đang chạy rồi tải lại trang.");
        }),
    [],
  );
  useEffect(() => {
    const controller = new AbortController();
    listWorkspaces(controller.signal)
      .then(setWorkspaces)
      .catch(() => {
        if (!controller.signal.aborted) {
          setError("Không tải được danh sách phiên làm việc. Hãy kiểm tra hệ thống đang chạy rồi tải lại trang.");
        }
      });
    return () => controller.abort();
  }, []);
  const state = useMemo(() => {
    if (!workspaces) return null;
    const wanted = rememberedWorkspace();
    const current = workspaces.find((item) => item.id === wanted) ?? workspaces[0];
    if (!current) return null;
    setWorkspaceId(current.id);
    return { workspaces, current, refresh };
  }, [workspaces, refresh]);
  return { state, error };
}

export function App() {
  const { state, error } = useWorkspaceState();
  if (!state) {
    return (
      <main className="page" id="noi-dung">
        <p className={error ? "notice notice--error" : "notice"} role={error ? "alert" : "status"}>
          {error ?? "Đang mở phiên làm việc…"}
        </p>
      </main>
    );
  }
  return (
    <WorkspaceContext.Provider value={state}>
      <Shell />
    </WorkspaceContext.Provider>
  );
}

function Shell() {
  const path = usePath();
  const section = sectionOf(path);
  // Trang chi tiết bộ dữ liệu: /du-lieu/<mã bộ dữ liệu>
  const datasetId = path.match(/^\/du-lieu\/([0-9a-f-]{36})$/)?.[1];
  const Page = PAGES[path] ?? OverviewPage;
  const [collapsed, setCollapsed] = useState(readRailCollapsed);

  const toggleRail = () => {
    const next = !collapsed;
    setCollapsed(next);
    saveRailCollapsed(next);
  };

  return (
    <div className="shell" data-rail={collapsed ? "collapsed" : "expanded"}>
      <nav className="rail" id="thanh-ben" aria-label="Điều hướng chính">
        <div className="rail__head">
          <a
            className="rail__brand"
            href="/"
            aria-label="AI Reconciliation Studio"
            onClick={(event) => {
              event.preventDefault();
              navigate("/");
            }}
          >
            <img src="/favicon.svg" alt="" width={32} height={32} />
            <span className="rail__label">AI Reconciliation Studio</span>
          </a>
          {/* Nút nhỏ ở góc trên bên phải để thu gọn / mở rộng thanh bên. */}
          <button
            className="rail__toggle"
            type="button"
            aria-controls="thanh-ben"
            aria-expanded={!collapsed}
            aria-label={collapsed ? "Mở rộng thanh bên" : "Thu gọn thanh bên"}
            title={collapsed ? "Mở rộng thanh bên" : "Thu gọn thanh bên"}
            onClick={toggleRail}
          >
            {collapsed ? (
              <PanelLeftOpen aria-hidden="true" size={18} strokeWidth={1.8} />
            ) : (
              <PanelLeftClose aria-hidden="true" size={18} strokeWidth={1.8} />
            )}
          </button>
        </div>
        <WorkspaceSwitcher variant="rail" />
        <ul className="rail__list">
          {ROUTES.map(({ path: target, label, icon: Icon }) => (
            <li key={target}>
              <a
                className="rail__link"
                href={target}
                aria-label={label}
                title={collapsed ? label : undefined}
                aria-current={target === section ? "page" : undefined}
                onClick={(event) => {
                  event.preventDefault();
                  navigate(target);
                }}
              >
                <Icon aria-hidden="true" size={20} strokeWidth={1.8} />
                <span className="rail__label">{label}</span>
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <main className="page" id="noi-dung">
        <WorkspaceSwitcher variant="bar" />
        {datasetId ? <DatasetPage key={datasetId} datasetId={datasetId} /> : <Page />}
      </main>
    </div>
  );
}
