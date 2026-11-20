import { useState } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

import { AssistantPage } from "./pages/AssistantPage";
import { DataPage } from "./pages/DataPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ReconcilePage } from "./pages/ReconcilePage";
import { ReportsPage } from "./pages/ReportsPage";
import { ROUTES, navigate, usePath } from "./navigation";

// Khung ứng dụng: thanh điều hướng (bên trái trên máy tính, dưới đáy trên điện thoại)
// và vùng nội dung của trang đang mở.

const PAGES: Record<string, () => React.JSX.Element> = {
  "/": OverviewPage,
  "/assistant": AssistantPage,
  "/du-lieu": DataPage,
  "/doi-soat": ReconcilePage,
  "/bao-cao": ReportsPage,
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

export function App() {
  const path = usePath();
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
        <ul className="rail__list">
          {ROUTES.map(({ path: target, label, icon: Icon }) => (
            <li key={target}>
              <a
                className="rail__link"
                href={target}
                aria-label={label}
                title={collapsed ? label : undefined}
                aria-current={target === path ? "page" : undefined}
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
        <Page />
      </main>
    </div>
  );
}
