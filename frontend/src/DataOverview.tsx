import { ArrowRight, Database, FileSpreadsheet, Layers3, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "./api";
import { DatasetList, Notice, Spinner } from "./components";
import type { Run } from "./reconciliationTypes";
import { statusText, type Dataset, type PreparationAction, type Project, type ProjectSummary } from "./types";

const features = [
  { page: "assistant", icon: Sparkles, title: "AI Assistant", action: "Mở AI Assistant",
    description: "Trao đổi với AI để kiểm tra và xử lý dữ liệu." },
  { page: "data", icon: Database, title: "Dữ liệu", action: "Quản lý dữ liệu",
    description: "Quản lý nguồn, xác nhận ánh xạ và chuẩn hóa." },
  { page: "reconcile", icon: Layers3, title: "Đối soát", action: "Mở đối soát",
    description: "Thiết lập quy tắc và kiểm tra chênh lệch giữa các nguồn." },
  { page: "reports", icon: FileSpreadsheet, title: "Báo cáo", action: "Xem báo cáo",
    description: "Xem kết quả đã xác minh, ngoại lệ và xuất báo cáo." },
] as const;

const nextActions: Partial<Record<PreparationAction["kind"], string>> = {
  UPLOAD: "Tải dữ liệu",
  REVIEW_MAPPING: "Kiểm tra ánh xạ",
  NORMALIZE: "Chuẩn hóa dữ liệu",
  REVIEW_DATA: "Kiểm tra lỗi dữ liệu",
};
const workflow = ["Tải dữ liệu", "Xác nhận cột", "Chuẩn hóa", "Đối soát", "Xem báo cáo"];

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
    {run?.metric_snapshot && <p className="dashboard-result-detail">
      {statusText[run.status]} · {run.metric_snapshot.period_start} đến trước {run.metric_snapshot.period_end}
    </p>}
    <button type="button" className="text-button" onClick={onOpen}>
      Xem kết quả đã xác minh <ArrowRight size={15} aria-hidden="true" />
    </button>
  </div>;
}

function ProjectCounts({ summary, onActivity, busy }: {
  summary: ProjectSummary;
  onActivity?: () => void;
  busy: boolean;
}) {
  const counts = [
    { label: "Nguồn dữ liệu", value: summary.dataset_count, help: `${summary.table_count} bảng / sheet` },
    { label: "Kết quả sẵn sàng sử dụng", value: summary.ready_canonical_count,
      help: [
        summary.partial_canonical_count ? `${summary.partial_canonical_count} cần kiểm tra` : "",
        summary.stale_canonical_count ? `${summary.stale_canonical_count} đã cũ` : "",
        summary.failed_canonical_count ? `${summary.failed_canonical_count} thất bại` : "",
      ].filter(Boolean).join(" · ") },
    { label: "Bảng cần xác nhận ánh xạ", value: summary.mapping_review_count },
    { label: "Tác vụ đang xử lý", value: summary.active_job_count, onOpen: onActivity },
  ];
  return <dl className="dashboard-counts">
    {counts.map(({ label, value, help, onOpen }) => <div className="stat-card" key={label}>
      <dt>{onOpen ? <button type="button" className="text-button dashboard-activity"
        aria-label="Xem công việc đang xử lý" disabled={busy} onClick={onOpen}>
        {label} <ArrowRight size={15} aria-hidden="true" />
      </button> : label}{help && <small>{help}</small>}</dt>
      <dd><strong>{value.toLocaleString("vi-VN")}</strong></dd>
    </div>)}
  </dl>;
}

export function DataOverview({
  project, summary, datasets, recentLoading, recentError, onRecentRetry,
  ready, busy, canEdit, projectLoading, onCreate, onRefresh,
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
  onCreate: () => void;
  onRefresh: () => void;
  onAction: (action: PreparationAction) => void;
  onResults: (runId: string) => void;
  onNavigate: (target: (typeof features)[number]["page"]) => void;
  chooseDataset: (dataset: Dataset) => void;
}) {
  const latestRun = summary?.latest_verified_run_id;
  const action = summary?.preparation_action;
  const next = action && (action.kind !== "UPLOAD" || (canEdit && summary?.dataset_count === 0))
    ? nextActions[action.kind] : undefined;
  const onActivity = summary && action?.kind === "WAIT" && summary.active_job_count > 0
    ? () => onAction(action) : undefined;

  return <div className="dashboard">
    <header className="dashboard-intro">
      <h1>Chào mừng đến với Reconciliation Studio</h1>
      <p>Nền tảng AI hỗ trợ chuẩn hóa, đối soát và phân tích dữ liệu trên cùng một không gian làm việc.</p>
    </header>
    <section className="dashboard-workflow" aria-labelledby="dashboard-workflow-title">
      <h2 id="dashboard-workflow-title">Quy trình làm việc</h2>
      <ol role="list">
        {workflow.map((step, index) => <li key={step}>
          {index > 0 && <ArrowRight size={14} aria-hidden="true" />}{step}
        </li>)}
      </ol>
    </section>

    <div className="dashboard-grid">
      <section className="dashboard-tools" aria-labelledby="dashboard-tools-title">
        <div className="dashboard-section-heading"><h2 id="dashboard-tools-title">Chức năng chính</h2></div>
        <ul className="dashboard-feature-list">
          {features.map(({ page, icon: Icon, title, action: actionLabel, description }) => (
            <li key={page}>
              <button type="button" className="dashboard-feature" aria-label={actionLabel} disabled={!ready}
                aria-describedby={`dashboard-${page}-description`} onClick={() => onNavigate(page)}>
                <Icon size={20} aria-hidden="true" />
                <strong>{title}</strong>
                <ArrowRight size={16} className="dashboard-feature-arrow" aria-hidden="true" />
                <span id={`dashboard-${page}-description`}>{description}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="dashboard-project" aria-labelledby="dashboard-project-title">
        <div className="dashboard-section-heading">
          <h2 id="dashboard-project-title">Tổng quan công việc</h2>
          {project && <button type="button" className="icon-button" aria-label="Cập nhật dự án" title="Cập nhật dự án"
            disabled={busy || projectLoading} onClick={onRefresh}>
            <RefreshCw size={16} aria-hidden="true" className={projectLoading ? "spin" : ""} />
          </button>}
        </div>
        <div className="dashboard-project-body">
          {project ? <>
            <p className="dashboard-project-name">{project.name}</p>
            {summary && <>
              <ProjectCounts summary={summary} onActivity={onActivity} busy={busy} />
              {summary.dataset_count === 0 && <div className="dashboard-status">
                <h3>Chưa có nguồn dữ liệu</h3>
                <p>Thêm tệp đầu tiên để bắt đầu.</p>
              </div>}
              {action && next && <div className="dashboard-next">
                <button type="button" className="text-button" disabled={busy} onClick={() => onAction(action)}>
                  {next} <ArrowRight size={15} aria-hidden="true" />
                </button>
              </div>}
              {latestRun && !next && !summary.active_job_count && <LatestResult key={`${project.id}:${latestRun}`}
                projectId={project.id} runId={latestRun} onOpen={() => onResults(latestRun)} />}
            </>}
          </> : ready && <div className="dashboard-status">
            <p className="dashboard-project-name">Chưa chọn dự án</p>
            <p>Chọn hoặc tạo dự án để tải dữ liệu và xem tiến độ.</p>
            {canEdit && <button type="button" className="text-button" disabled={busy} onClick={onCreate}>
              Tạo dự án <ArrowRight size={15} aria-hidden="true" />
            </button>}
          </div>}
        </div>
      </section>
    </div>

    {project && summary && summary.dataset_count > 0 && <section className="dashboard-recent panel" aria-labelledby="dashboard-recent-title">
      <div className="panel-heading">
        <h2 id="dashboard-recent-title">Dữ liệu gần đây</h2>
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
