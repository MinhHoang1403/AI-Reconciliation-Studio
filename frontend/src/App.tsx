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

export function App() {
  const path = usePath();
  const Page = PAGES[path] ?? OverviewPage;

  return (
    <div className="shell">
      <nav className="rail" aria-label="Điều hướng chính">
        <a className="rail__brand" href="/" onClick={(event) => { event.preventDefault(); navigate("/"); }}>
          <img src="/favicon.svg" alt="" width={32} height={32} />
          <span>AI Reconciliation Studio</span>
        </a>
        <ul className="rail__list">
          {ROUTES.map(({ path: target, label, icon: Icon }) => (
            <li key={target}>
              <a
                className="rail__link"
                href={target}
                aria-current={target === path ? "page" : undefined}
                onClick={(event) => {
                  event.preventDefault();
                  navigate(target);
                }}
              >
                <Icon aria-hidden="true" size={20} strokeWidth={1.8} />
                <span>{label}</span>
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
