import { ArrowRight, Database, FileSpreadsheet, Layers3, RefreshCw, Sparkles, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "./api";
import { Badge, DatasetList, Notice, Spinner } from "./components";
import type { Run } from "./reconciliationTypes";
import type { Dataset, PreparationAction, Project, ProjectSummary } from "./types";

const features = [
  { page: "assistant", icon: Sparkles, title: "AI Assistant", action: "Mở AI Assistant",
    description: "Yêu cầu AI kiểm tra, chuẩn hóa, đối soát và phân tích dữ liệu bằng ngôn ngữ tự nhiên." },
  { page: "data", icon: Database, title: "Dữ liệu", action: "Quản lý dữ liệu",
    description: "Quản lý nguồn dữ liệu, kiểm tra cấu trúc, xác nhận ánh xạ và tạo dữ liệu chuẩn hóa." },
  { page: "reconcile", icon: Layers3, title: "Đối soát", action: "Mở đối soát",
    description: "Thiết lập quy tắc, so sánh nhiều nguồn và phát hiện những giao dịch không khớp." },
  { page: "reports", icon: FileSpreadsheet, title: "Báo cáo", action: "Xem báo cáo",
    description: "Xem kết quả đã xác minh, phân tích ngoại lệ và xuất báo cáo." },
] as const;

const nextActions = {
  WAIT: { label: "Xem công việc đang xử lý", help: "Theo dõi tiến độ trong Hoạt động xử lý của dự án." },
  REVIEW_MAPPING: { label: "Kiểm tra ánh xạ", help: "Xác nhận cách đọc các cột trước khi chuẩn hóa bảng." },
  NORMALIZE: { label: "Chuẩn hóa dữ liệu", help: "Mở bảng đã duyệt ánh xạ để tạo kết quả chuẩn hóa." },
  REVIEW_DATA: { label: "Kiểm tra lỗi dữ liệu", help: "Mở nguồn cần kiểm tra và xem cảnh báo của đúng bảng." },
  RECONCILE: { label: "Mở Đối soát", help: "Chọn nguồn đã chuẩn hóa, kiểm tra quy tắc và kỳ đối soát." },
} satisfies Record<Exclude<PreparationAction["kind"], "UPLOAD">, { label: string; help: string }>;

function LatestResult({ projectId, runId, onOpen }: {
  projectId: string;
  runId: string;
  onOpen: () => void;
}) {
  const [run, setRun] = useState<Run | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void api<Run>(`/runs/${encodeURIComponent(runId)}`, { signal: controller.signal })
      .then(result => {
        if (!controller.signal.aborted && result.id === runId && result.project_id === projectId &&
          ["VERIFIED", "PARTIAL_VERIFIED"].includes(result.status) && result.metric_snapshot?.run_id === runId) {
          setRun(result);
        }
      })
      .catch(() => { /* Báo cáo vẫn là điểm truy cập kết quả khi không tải được chi tiết. */ });
    return () => controller.abort();
  }, [projectId, runId]);

  return <div className="dashboard-result">
    <h3>Kết quả đối soát gần nhất</h3>
    {run?.metric_snapshot && <div className="dashboard-result-detail">
      <Badge status={run.status} />
      <span>{run.metric_snapshot.period_start} đến trước {run.metric_snapshot.period_end}</span>
    </div>}
    <button type="button" className="text-button" onClick={onOpen}>
      Xem kết quả đã xác minh <ArrowRight size={15} aria-hidden="true" />
    </button>
  </div>;
}

function ProjectCounts({ summary }: { summary: ProjectSummary }) {
  const counts = [
    { label: "Nguồn dữ liệu", value: summary.dataset_count, help: `${summary.table_count} bảng / sheet` },
    { label: "Kết quả sẵn sàng sử dụng", value: summary.ready_canonical_count,
      help: `${summary.partial_canonical_count} cần kiểm tra · ${summary.stale_canonical_count} đã cũ` +
        (summary.failed_canonical_count ? ` · ${summary.failed_canonical_count} thất bại` : "") },
    { label: "Bảng cần xác nhận ánh xạ", value: summary.mapping_review_count },
    { label: "Tác vụ đang xử lý", value: summary.active_job_count },
  ];
  return <dl className="dashboard-counts">
    {counts.map(({ label, value, help }) => <div className="stat-card" key={label}>
      <dt>{label}{help && <small>{help}</small>}</dt>
      <dd><strong>{value.toLocaleString("vi-VN")}</strong></dd>
    </div>)}
  </dl>;
}

export function DataOverview({
  project, summary, datasets, recentLoading, recentError, onRecentRetry,
  ready, busy, canEdit, projectLoading, onUpload, onCreate, onRefresh,
  onAction, onResults, onNavigate, chooseDataset,
}: {
  project: Project | null;
  summary: ProjectSummary | null;
  datasets: Dataset[];
  recentLoading: boolean;
  recentError: string;
  onRecentRetry: () => void;
  ready: boolean;
  busy: boolean;
  canEdit: boolean;
  projectLoading: boolean;
  onUpload: () => void;
  onCreate: () => void;
  onRefresh: () => void;
  onAction: (action: PreparationAction) => void;
  onResults: (runId: string) => void;
  onNavigate: (target: (typeof features)[number]["page"]) => void;
  chooseDataset: (dataset: Dataset) => void;
}) {
  const latestRun = summary?.latest_verified_run_id;
  const action = summary?.preparation_action;
  const next = action && action.kind !== "UPLOAD" ? nextActions[action.kind] : null;
  const continueWork = action && next ? () => onAction(action)
    : latestRun ? () => onResults(latestRun) : null;

  return <div className="dashboard">
    <header className="dashboard-intro">
      <h1>Chào mừng đến với Reconciliation Studio</h1>
      <p>Chuẩn bị, đối soát và phân tích dữ liệu với AI. Theo dõi từng bước từ tệp nguồn đến kết quả đã xác minh.</p>
      <div className="dashboard-start">
        <button type="button" className="button primary" disabled={!ready || busy || !canEdit} onClick={onUpload}>
          <Upload size={17} aria-hidden="true" /> Tải dữ liệu
        </button>
        <button type="button" className="button secondary" disabled={!ready} onClick={() => onNavigate("assistant")}>
          <Sparkles size={17} aria-hidden="true" /> Hỏi AI Assistant
        </button>
        {continueWork && <button type="button" className="button secondary" disabled={busy} onClick={continueWork}>
          Tiếp tục công việc <ArrowRight size={16} aria-hidden="true" />
        </button>}
      </div>
    </header>

    <div className="dashboard-grid">
      <section className="dashboard-tools" aria-labelledby="dashboard-tools-title">
        <h2 id="dashboard-tools-title">Chức năng chính</h2>
        <ul className="dashboard-feature-list">
          {features.map(({ page, icon: Icon, title, action: actionLabel, description }) => (
            <li key={page}>
              <button type="button" className="dashboard-feature" aria-label={actionLabel} disabled={!ready}
                onClick={() => onNavigate(page)}>
                <Icon size={20} aria-hidden="true" />
                <strong>{title}</strong>
                <span>{description}</span>
                <span className="dashboard-feature-action">{actionLabel} <ArrowRight size={15} aria-hidden="true" /></span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="dashboard-project" aria-labelledby="dashboard-project-title">
        <div className="dashboard-project-heading">
          <h2 id="dashboard-project-title">Tổng quan công việc</h2>
          {project && <button type="button" className="icon-button" aria-label="Cập nhật dự án" title="Cập nhật dự án"
            disabled={busy || projectLoading} onClick={onRefresh}>
            <RefreshCw size={16} aria-hidden="true" className={projectLoading ? "spin" : ""} />
          </button>}
        </div>
        {project ? <>
          <p className="dashboard-project-name">{project.name}</p>
          {summary && <>
            {summary.dataset_count > 0
              ? <ProjectCounts summary={summary} />
              : <div className="dashboard-status">
                <h3>Chưa có nguồn dữ liệu</h3>
                <p>Tải tệp đầu tiên để bắt đầu.</p>
              </div>}
            {action && next && <div className="dashboard-next">
              <p>{next.help}</p>
              <button type="button" className="text-button" disabled={busy} onClick={() => onAction(action)}>
                {next.label} <ArrowRight size={15} aria-hidden="true" />
              </button>
            </div>}
            {latestRun && <LatestResult key={`${project.id}:${latestRun}`}
              projectId={project.id} runId={latestRun} onOpen={() => onResults(latestRun)} />}
          </>}
        </> : ready && <div className="dashboard-status">
          <p className="dashboard-project-name">Chưa chọn dự án</p>
          <p>Chọn hoặc tạo dự án để tải dữ liệu và xem tiến độ.</p>
          {canEdit && <button type="button" className="text-button" disabled={busy} onClick={onCreate}>
            Tạo dự án <ArrowRight size={15} aria-hidden="true" />
          </button>}
        </div>}
      </section>
    </div>

    {project && summary && summary.dataset_count > 0 && <section className="dashboard-recent panel" aria-labelledby="dashboard-recent-title">
      <div className="panel-heading">
        <h2 id="dashboard-recent-title">Dữ liệu gần đây</h2>
        <button type="button" className="text-button" onClick={() => onNavigate("data")}>
          Xem tất cả <ArrowRight size={15} aria-hidden="true" />
        </button>
      </div>
      {recentLoading ? (
        <div className="dashboard-recent-state" role="status"><Spinner /> Đang tải dữ liệu gần đây…</div>
      ) : recentError ? (
        <Notice tone="error">
          Không tải được dữ liệu gần đây. {recentError}{" "}
          <button className="text-button" onClick={onRecentRetry}>Tải lại dữ liệu gần đây</button>
        </Notice>
      ) : datasets.length ? (
        <DatasetList items={datasets.slice(0, 5)} onSelect={chooseDataset} />
      ) : <div className="dashboard-recent-state">
        <h3>Chưa có nguồn dữ liệu</h3>
        <p>Tải tệp đầu tiên vào dự án để bắt đầu.</p>
      </div>}
    </section>}
  </div>;
}
