import { useEffect, useState } from "react";
import { ArrowRight, Check } from "lucide-react";

import { listReports, listRuns, type ReconRun, type ReportPeriod } from "../api";

import { money, percent } from "../components/ReportCharts";
import { SystemStatusPanel } from "../components/SystemStatusPanel";
import { VerificationSeal } from "../components/VerificationSeal";
import { formatCount } from "../format";
import { navigate } from "../navigation";
import { useDatasetList } from "../useDatasets";
import { sealChecks } from "../verification";

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

type StepState = "done" | "current" | "later";

export function OverviewPage() {
  const { state } = useDatasetList();
  // Lần đối soát gần nhất: quyết định bước Đối soát và con dấu kiểm chứng.
  const [run, setRun] = useState<ReconRun | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    listRuns(1, controller.signal)
      .then((runs) => setRun(runs[0] ?? null))
      .catch(() => setRun(null));
    return () => controller.abort();
  }, []);
  // Kỳ mới nhất đã đối soát cả chuỗi: 4 số chính của báo cáo, bấm vào sang trang Báo cáo.
  const [latest, setLatest] = useState<ReportPeriod | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    listReports(controller.signal)
      .then(({ periods }) => setLatest(periods.at(-1) ?? null))
      .catch(() => setLatest(null));
    return () => controller.abort();
  }, []);
  const checks = sealChecks(run?.status === "READY" ? run.verification : null);
  const reconOpen = run?.status === "READY" ? run.exceptions.OPEN : 0;
  const ready = state.kind === "ready" ? state.data.filter((dataset) => dataset.status === "READY") : [];
  const readyRows = ready.reduce(
    (sum, dataset) =>
      sum + dataset.tables.filter((table) => table.status === "READY").reduce((rows, table) => rows + table.row_count, 0),
    0,
  );
  const hasData = ready.length > 0;
  const readyTables = ready.flatMap((dataset) => dataset.tables.filter((table) => table.status === "READY"));
  const pending = readyTables.reduce((sum, table) => sum + table.mapping_pending, 0);
  const mappingBusy = readyTables.some((table) => table.mapping_status !== "READY");
  const mapped = hasData && !mappingBusy && pending === 0;
  // Chỉ BUILDING là đang chuẩn hóa. NONE nghĩa là bảng không có cột nào được ánh xạ nên
  // không có gì để làm sạch; coi là bận thì bước này kẹt mãi (danh sách không tự tải lại khi NONE).
  const cleanBusy = readyTables.some((table) => table.clean_status === "BUILDING");
  const cleanOpen = readyTables.reduce((sum, table) => sum + table.clean_open, 0);
  const cleaned = mapped && !cleanBusy && cleanOpen === 0;

  // Trạng thái từng bước: 1 đọc tệp, 2 ánh xạ, 3 chuẩn hóa, 4 xử lý lỗi, 5 đối soát, 6 báo cáo.
  const steps: { state: StepState; label: string }[] = PIPELINE.map((_, index) => {
    if (index === 0) return hasData ? { state: "done", label: `Đã đọc ${ready.length} bộ` } : { state: "current", label: "Đang chờ tệp" };
    if (index === 1) {
      if (!hasData) return { state: "later", label: "Chưa tới" };
      if (mappingBusy) return { state: "current", label: "Đang gợi ý" };
      return pending > 0 ? { state: "current", label: `Cần xem ${pending} cột` } : { state: "done", label: "Đã ánh xạ" };
    }
    if (index === 2) {
      if (!mapped) return { state: "later", label: "Chưa tới" };
      return cleanBusy ? { state: "current", label: "Đang chuẩn hóa" } : { state: "done", label: "Đã chuẩn hóa" };
    }
    if (index === 3) {
      if (!mapped || cleanBusy) return { state: "later", label: "Chưa tới" };
      return cleanOpen > 0 ? { state: "current", label: `Cần xử lý ${cleanOpen}` } : { state: "done", label: "Đã sạch" };
    }
    if (index === 4) {
      if (run?.status === "RUNNING") return { state: "current", label: "Đang chạy" };
      if (run?.status === "READY") {
        return reconOpen > 0 ? { state: "current", label: `Cần xem ${reconOpen} ca` } : { state: "done", label: "Đã đối soát" };
      }
      if (cleaned) return { state: "current", label: "Sẵn sàng" };
    }
    if (index === 5 && latest?.kpis) {
      return latest.verified ? { state: "done", label: "Có báo cáo" } : { state: "current", label: "Chờ kiểm chứng" };
    }
    return { state: "later", label: "Chưa tới" };
  });
  // Nút của dải bước tiếp theo dẫn tới Đối soát khi ánh xạ và làm sạch không còn việc chờ.
  const toRecon = hasData && pending === 0 && !(mapped && !cleanBusy && cleanOpen > 0) && (cleaned || run !== null);
  // Đối soát xong, không còn ca cần xem và đã có báo cáo của kỳ: bước tiếp theo là xem báo cáo.
  const toReport = toRecon && run?.status === "READY" && reconOpen === 0 && latest?.kpis != null;
  const stepState = (index: number): StepState => steps[index]?.state ?? "later";
  const stepLabel = (index: number): string => steps[index]?.label ?? "Chưa tới";

  return (
    <div className="overview">
      <header className="page__header">
        <h1>Dashboard</h1>
        <p>Đối soát bán hàng: đơn hàng, thanh toán và sao kê ngân hàng.</p>
      </header>

      <section className="next-step" aria-labelledby="next-step-title">
        <div>
          {hasData && pending > 0 ? (
            <>
              <h2 id="next-step-title">Cần bạn xem {pending} cột ánh xạ</h2>
              <p>Hệ thống đã tự ánh xạ phần lớn các cột; chỉ còn vài cột chưa chắc chắn, chọn sẵn gợi ý tốt nhất.</p>
            </>
          ) : hasData && mapped && !cleanBusy && cleanOpen > 0 ? (
            <>
              <h2 id="next-step-title">Cần bạn xử lý {cleanOpen} lỗi dữ liệu</h2>
              <p>Hệ thống đã tự sửa lỗi định dạng; còn vài ô hoặc dòng cần bạn quyết định, có gợi ý sẵn.</p>
            </>
          ) : hasData && reconOpen > 0 ? (
            <>
              <h2 id="next-step-title">Cần bạn xem {formatCount(reconOpen)} ca đối soát</h2>
              <p>Phần lớn các dòng đã tự khớp; còn vài ca lệch tiền, thiếu hoặc thừa, mỗi ca có lý do sẵn.</p>
            </>
          ) : hasData && run?.status === "READY" ? (
            <>
              <h2 id="next-step-title">
                {run.verification?.passed ? "Đối soát xong, kết quả đã kiểm chứng" : "Đối soát xong nhưng kiểm chứng chưa đạt"}
              </h2>
              <p>Mọi ngoại lệ đã được xử lý. Xem báo cáo của kỳ và tải tệp kết quả.</p>
            </>
          ) : hasData ? (
            <>
              <h2 id="next-step-title">{cleaned ? `${ready.length} bộ dữ liệu đã sạch` : `Đã đọc ${ready.length} bộ dữ liệu`}</h2>
              <p>
                {formatCount(readyRows)} dòng
                {cleaned ? " đã chuẩn hóa và làm sạch, sẵn sàng đối soát." : ", đang ánh xạ và chuẩn hóa…"}
              </p>
            </>
          ) : (
            <>
              <h2 id="next-step-title">Tải bộ dữ liệu đầu tiên</h2>
              <p>Chưa có dữ liệu để đối soát. Tải tệp đơn hàng, thanh toán hoặc sao kê (CSV, Excel) để bắt đầu.</p>
            </>
          )}
        </div>
        <button
          className="button button--primary"
          type="button"
          onClick={() => navigate(toReport ? "/bao-cao" : toRecon ? "/doi-soat" : "/du-lieu")}
        >
          {toReport
            ? "Xem báo cáo"
            : toRecon
              ? reconOpen > 0 || run
                ? "Đến trang Đối soát"
                : "Chạy đối soát"
              : hasData
                ? "Xem dữ liệu"
                : "Đến trang Dữ liệu"}
          <ArrowRight aria-hidden="true" size={18} />
        </button>
      </section>

      {latest?.kpis && (
        <section className="overview-kpis" aria-labelledby="overview-kpis">
          <div className="overview-kpis__head">
            <h2 id="overview-kpis">{latest.label}</h2>
            <button type="button" className="button button--quiet" onClick={() => navigate("/bao-cao")}>
              Xem báo cáo <ArrowRight aria-hidden="true" size={16} />
            </button>
          </div>
          <dl className="report-figures overview-kpis__figures">
            <div>
              <dt>Khớp theo số tiền</dt>
              <dd>{percent(latest.kpis.match_rate_amount)}</dd>
            </div>
            <div>
              <dt>Cần xử lý</dt>
              <dd>{formatCount(latest.kpis.open_count)} ca</dd>
            </div>
            <div>
              <dt>Tổng lệch tiền</dt>
              <dd>{money(latest.kpis.mismatch_total)}</dd>
            </div>
            <div>
              <dt>Kiểm chứng</dt>
              <dd>{latest.verified ? "Đạt" : "Chưa đạt"}</dd>
            </div>
          </dl>
        </section>
      )}

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
          <VerificationSeal checks={checks} />
          <p className="verification__lead">
            {run?.status === "READY"
              ? run.verification?.passed
                ? "Lần đối soát gần nhất đạt cả bốn phép kiểm độc lập."
                : "Lần đối soát gần nhất có phép kiểm không đạt; kết quả không dùng cho báo cáo."
              : "Sau mỗi lần đối soát, một module độc lập kiểm lại kết quả. Mỗi vòng hoa văn là một phép kiểm."}
          </p>
          <ul className="verification__checks">
            {checks.map((check) => (
              <li key={check.label} data-state={check.state}>{check.label}</li>
            ))}
          </ul>
        </aside>
      </div>

      <SystemStatusPanel />
    </div>
  );
}
