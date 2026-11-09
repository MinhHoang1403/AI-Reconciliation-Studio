import {
  ArrowRight,
  CheckCheck,
  Database,
  FileSpreadsheet,
  Layers3,
  Sparkles,
  Upload,
} from "lucide-react";
import { DatasetList, Notice, Spinner } from "./components";
import type {
  Dataset,
  PreparationAction,
  ProjectSummary,
} from "./types";
import type { ReactNode } from "react";

const actionText: Record<
  PreparationAction["kind"],
  { title: string; help: string }
> = {
  UPLOAD: {
    title: "Tải dữ liệu đầu tiên",
    help: "Thêm CSV/XLSX để bắt đầu. Nếu đã có kết quả chuẩn hóa, hãy bổ sung nguồn thứ hai.",
  },
  WAIT: {
    title: "Cập nhật trạng thái xử lý",
    help: "Dữ liệu đang được xử lý. Kiểm tra trạng thái để tiếp tục.",
  },
  REVIEW_MAPPING: {
    title: "Kiểm tra ánh xạ",
    help: "Xác nhận cách đọc các cột để chuẩn hóa bảng.",
  },
  NORMALIZE: {
    title: "Chuẩn hóa dữ liệu",
    help: "Bảng đã duyệt ánh xạ chưa có kết quả chuẩn hóa hiện hành. Mở đúng bảng để kiểm tra trước khi xử lý.",
  },
  REVIEW_DATA: {
    title: "Kiểm tra lỗi dữ liệu",
    help: "Mở kết quả và cảnh báo từ nguồn. Tác vụ hoàn tất không đồng nghĩa dữ liệu đã đạt chất lượng.",
  },
  RECONCILE: {
    title: "Mở Đối soát",
    help: "Đã có ít nhất hai nguồn chuẩn hóa. Chọn cặp nguồn để kiểm tra quy tắc và kỳ đối soát.",
  },
};

function PreparationGuide({
  summary,
  busy,
  onAction,
  onResults,
}: {
  summary: ProjectSummary;
  busy: boolean;
  onAction: (action: PreparationAction) => void;
  onResults: (page: "reports" | "exceptions") => void;
}) {
  const action = summary.preparation_action;
  return (
    <section className="panel preparation-guide" aria-label="Bước tiếp theo">
      {action ? (
        <>
          <div>
            <h2>Bước tiếp theo</h2>
            <p>{actionText[action.kind].help}</p>
            {action.kind === "UPLOAD" && summary.dataset_count > 0 && (
              <p>
                Đối soát cần hai nguồn đã chuẩn hóa và tương thích.
              </p>
            )}
          </div>
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => onAction(action)}
          >
            {action.kind === "UPLOAD" && summary.dataset_count > 0
              ? "Bổ sung nguồn dữ liệu"
              : actionText[action.kind].title}
            <ArrowRight size={16} />
          </button>
        </>
      ) : (
        <p>Mở Dữ liệu để xem trạng thái từng nguồn.</p>
      )}
      {summary.latest_verified_run_id && (
        <div className="rule-actions">
          <button className="text-button" onClick={() => onResults("reports")}>
            Xem kết quả đã xác minh
          </button>
          <button
            className="text-button"
            onClick={() => onResults("exceptions")}
          >
            Mở ngoại lệ
          </button>
        </div>
      )}
    </section>
  );
}

function Stat({
  icon,
  value,
  label,
  help,
}: {
  icon: ReactNode;
  value: number;
  label: string;
  help?: string;
}) {
  return (
    <article className="stat-card">
      <span>{icon}</span>
      <strong>{value}</strong>
      <p>{label}</p>
      <small>{help}</small>
    </article>
  );
}

/** Preparation counters and navigation only; financial metrics stay in ReconciliationStudio. */
export function DataOverview({
  summary,
  datasets,
  recentLoading,
  recentError,
  onRecentRetry,
  busy,
  onAction,
  onResults,
  onData,
  chooseDataset,
}: {
  summary: ProjectSummary;
  datasets: Dataset[];
  recentLoading: boolean;
  recentError: string;
  onRecentRetry: () => void;
  busy: boolean;
  onAction: (action: PreparationAction) => void;
  onResults: (page: "reports" | "exceptions") => void;
  onData: () => void;
  chooseDataset: (dataset: Dataset) => void;
}) {
  return (
    <>
      <PreparationGuide
        summary={summary}
        busy={busy}
        onAction={onAction}
        onResults={onResults}
      />
      {summary.dataset_count > 0 && (
        <section className="stats-grid">
          <Stat
            icon={<FileSpreadsheet />}
            value={summary.dataset_count}
            help={`${summary.table_count} bảng / sheet; không phải số dòng`}
            label="Nguồn dữ liệu"
          />
          <Stat
            icon={<Layers3 />}
            value={summary.mapping_review_count}
            help="Bảng chưa có ánh xạ được duyệt; không đại diện toàn bộ chất lượng."
            label="Bảng cần xác nhận ánh xạ"
          />
          <Stat
            icon={<CheckCheck />}
            value={summary.ready_canonical_count}
            help={`${summary.partial_canonical_count} cần kiểm tra · ${summary.stale_canonical_count} đã cũ · ${summary.failed_canonical_count} thất bại`}
            label="Kết quả sẵn sàng sử dụng"
          />
          <Stat
            icon={<Sparkles />}
            value={summary.active_job_count}
            help="Đang chờ, đang chạy hoặc chờ thử lại; không gồm tác vụ hoàn tất."
            label="Tác vụ đang xử lý"
          />
        </section>
      )}
      <details
        className="preparation-help"
      >
        <summary>Quy trình chuẩn bị dữ liệu · 3 bước</summary>
        <section className="steps-grid">
          {[
            {
              title: "Tải nguồn dữ liệu",
              icon: <Upload size={21} />,
              text: "CSV, Excel nhiều sheet. Tệp gốc được lưu bất biến trong workspace.",
            },
            {
              title: "Kiểm tra ánh xạ",
              icon: <Sparkles size={21} />,
              text: "Xem đề xuất AI, dữ liệu mẫu và xác nhận những trường cần sử dụng.",
            },
            {
              title: "Chuẩn hóa & khám phá",
              icon: <Database size={21} />,
              text: "Xem kết quả có kiểu dữ liệu, lỗi chuyển đổi và nguồn gốc từng dòng.",
            },
          ].map((s, i) => (
            <article className="step-card" key={s.title}>
              <div className="step-top">
                <span>{s.icon}</span>
                <small>0{i + 1}</small>
              </div>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </article>
          ))}
        </section>
      </details>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Dữ liệu gần đây</h2>
            <p>Năm nguồn tải lên mới nhất trong dự án.</p>
          </div>
          <button className="text-button" onClick={() => onData()}>
            Xem tất cả <ArrowRight size={15} />
          </button>
        </div>
        {recentLoading ? (
          <div role="status">
            <Spinner /> Đang tải dữ liệu gần đây…
          </div>
        ) : recentError ? (
          <Notice tone="error">
            Không tải được dữ liệu gần đây. {recentError}{" "}
            <button className="text-button" onClick={onRecentRetry}>
              Tải lại dữ liệu gần đây
            </button>
          </Notice>
        ) : datasets.length ? (
          <DatasetList items={datasets.slice(0, 5)} onSelect={chooseDataset} />
        ) : (
          <div className="empty-state">
            <FileSpreadsheet size={31} />
            <h3>Chưa có nguồn dữ liệu</h3>
            <p>Tải tệp đầu tiên vào dự án để bắt đầu.</p>

          </div>
        )}
      </section>
    </>
  );
}
