import { ArrowRight, Check } from "lucide-react";

import { SystemStatusPanel } from "../components/SystemStatusPanel";
import { VerificationSeal, type SealCheck } from "../components/VerificationSeal";
import { formatCount } from "../format";
import { navigate } from "../navigation";
import { useDatasetList } from "../useDatasets";

// Trang Tổng quan: bước cần làm tiếp theo, quy trình xử lý và con dấu kiểm chứng.
// Mọi con số lấy từ backend; chưa có dữ liệu thì hiện trạng thái ban đầu, không hiển thị số liệu giả.

// Các bước hệ thống làm với dữ liệu, giải thích bằng lời thường cho người không chuyên.
const PIPELINE = [
  { name: "Đọc tệp", detail: "Đọc CSV, Excel và giữ nguyên bản gốc." },
  { name: "Ánh xạ cột", detail: "Nhận ra cột nào là mã đơn, số tiền, ngày…" },
  { name: "Chuẩn hóa", detail: "Đưa số tiền, ngày, mã, tên về cùng một dạng." },
  { name: "Xử lý lỗi", detail: "Tự sửa lỗi dễ, chỉ ra ô cần bạn xác nhận." },
  { name: "Đối soát", detail: "Ghép từng dòng giữa hai nguồn, nêu lý do." },
  { name: "Báo cáo", detail: "KPI, biểu đồ và tệp kết quả để tải về." },
] as const;

// Bốn phép kiểm độc lập chạy sau mỗi lần đối soát; mỗi phép là một vòng của con dấu.
const CHECKS: readonly SealCheck[] = [
  { label: "Mỗi dòng nằm trong đúng một kết quả", state: "pending" },
  { label: "Tổng tiền từng bên được bảo toàn", state: "pending" },
  { label: "Số dòng theo từng loại cộng đủ tổng", state: "pending" },
  { label: "Mọi tham chiếu trỏ về dòng gốc có thật", state: "pending" },
];

type StepState = "done" | "current" | "later";

export function OverviewPage() {
  const { state } = useDatasetList();
  const ready = state.kind === "ready" ? state.data.filter((dataset) => dataset.status === "READY") : [];
  const readyRows = ready.reduce(
    (sum, dataset) =>
      sum + dataset.tables.filter((table) => table.status === "READY").reduce((rows, table) => rows + table.row_count, 0),
    0,
  );
  const hasData = ready.length > 0;
  // Bước 1 xong khi đã có bộ dữ liệu đọc được; bước 2 (ánh xạ) đang được xây dựng.
  const stepState = (index: number): StepState =>
    index === 0 ? (hasData ? "done" : "current") : index === 1 && hasData ? "current" : "later";
  const stepLabel = (index: number): string => {
    const current = stepState(index);
    if (current === "done") return `Đã đọc ${ready.length} bộ`;
    if (current === "current") return index === 0 ? "Đang chờ tệp" : "Đang xây dựng";
    return "Chưa tới";
  };

  return (
    <div className="overview">
      <header className="page__header">
        <h1>Tổng quan</h1>
        <p>Đối soát bán hàng: đơn hàng, thanh toán và sao kê ngân hàng.</p>
      </header>

      <section className="next-step" aria-labelledby="next-step-title">
        <div>
          {hasData ? (
            <>
              <h2 id="next-step-title">Đã đọc {ready.length} bộ dữ liệu</h2>
              <p>
                {formatCount(readyRows)} dòng sẵn sàng. Bước tiếp theo là ánh xạ cột, chức năng này đang được xây
                dựng.
              </p>
            </>
          ) : (
            <>
              <h2 id="next-step-title">Tải bộ dữ liệu đầu tiên</h2>
              <p>Chưa có dữ liệu để đối soát. Tải tệp đơn hàng, thanh toán hoặc sao kê (CSV, Excel) để bắt đầu.</p>
            </>
          )}
        </div>
        <button className="button button--primary" type="button" onClick={() => navigate("/du-lieu")}>
          {hasData ? "Xem dữ liệu" : "Đến trang Dữ liệu"}
          <ArrowRight aria-hidden="true" size={18} />
        </button>
      </section>

      <div className="overview__grid">
        <section className="pipeline" aria-labelledby="pipeline-title">
          <h2 id="pipeline-title">Quy trình xử lý</h2>
          <ol className="pipeline__list">
            {PIPELINE.map((step, index) => (
              <li key={step.name} className="pipeline__step" data-state={stepState(index)}>
                <span className="pipeline__index" aria-hidden="true">
                  {stepState(index) === "done" ? <Check size={18} strokeWidth={2.4} /> : index + 1}
                </span>
                <div>
                  <h3>{step.name}</h3>
                  <p>{step.detail}</p>
                </div>
                <span className="pipeline__state">{stepLabel(index)}</span>
              </li>
            ))}
          </ol>
        </section>

        <aside className="verification" aria-labelledby="verification-title">
          <h2 id="verification-title">Kiểm chứng kết quả</h2>
          <VerificationSeal checks={CHECKS} />
          <p className="verification__lead">
            Sau mỗi lần đối soát, một module độc lập kiểm lại kết quả. Mỗi vòng hoa văn là một phép kiểm.
          </p>
          <ul className="verification__checks">
            {CHECKS.map((check) => (
              <li key={check.label} data-state={check.state}>{check.label}</li>
            ))}
          </ul>
        </aside>
      </div>

      <SystemStatusPanel />
    </div>
  );
}
