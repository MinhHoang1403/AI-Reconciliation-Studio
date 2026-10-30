import {
  ArrowRight,
  CheckCheck,
  Database,
  FileSpreadsheet,
  Layers3,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react";
import { DatasetList, Notice, Spinner } from "./components";
import type {
  Dataset,
  PreparationAction,
  ProjectSummary,
  WorkspaceSettings,
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
    help: "Worker đang xử lý. Bạn có thể cập nhật; không cần gửi lại tác vụ.",
  },
  REVIEW_MAPPING: {
    title: "Kiểm tra ánh xạ",
    help: "Mở bảng chưa có ánh xạ được duyệt. Các bảng cần xác nhận được chọn theo ngày tải và mã nguồn.",
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
    help: "Có ít nhất hai kết quả READY. Hãy chọn nguồn và kiểm tra khóa, ý nghĩa chỉ tiêu, kỳ và phạm vi trước khi duyệt quy tắc.",
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
                Bổ sung hoặc chuẩn hóa nguồn thứ hai; READY chưa xác nhận tính
                tương thích giữa các nguồn.
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
  workspace,
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
  workspace: WorkspaceSettings | null;
  busy: boolean;
  onAction: (action: PreparationAction) => void;
  onResults: (page: "reports" | "exceptions") => void;
  onData: () => void;
  chooseDataset: (dataset: Dataset) => void;
}) {
  return (
    <>
      {summary.dataset_count === 0 ? (
        <section className="welcome-card">
          <div className="welcome-copy">
            <span className="pill">
              <Sparkles size={14} />
              AI SMART SETUP
            </span>
            <h2>
              Khởi đầu từ dữ liệu.
              <br />
              <span>Sẵn sàng cho điều tiếp theo.</span>
            </h2>
            <p>
              Tải CSV hoặc Excel lên. Hệ thống đọc cấu trúc, phân tích chất
              lượng và dùng{" "}
              {workspace?.mapping_ai_provider === "GEMINI" ? "Gemini" : "Qwen"}{" "}
              để đề xuất ánh xạ. Quyết định cuối cùng luôn thuộc về bạn.
            </p>
            <div className="welcome-points">
              <span>
                <CheckCheck size={16} />
                Giữ nguyên tệp nguồn
              </span>
              <span>
                <CheckCheck size={16} />
                Truy vết từng dòng
              </span>
              <span>
                <CheckCheck size={16} />
                Lưu quyết định đã duyệt
              </span>
            </div>
            <button
              className="text-button"
              onClick={() => {
                onData();
              }}
            >
              Tìm hiểu quy trình chuẩn bị dữ liệu <ArrowRight size={16} />
            </button>
          </div>
          <div
            className="flow-illustration"
            aria-label="Quy trình từ tệp nguồn đến dữ liệu chuẩn hóa"
          >
            <div className="flow-node">
              <span className="node-icon">
                <FileSpreadsheet size={23} />
              </span>
              <div>
                <strong>Tệp nguồn</strong>
                <small>CSV · XLSX</small>
              </div>
              <ShieldCheck size={18} />
            </div>
            <div className="flow-line" />
            <div className="flow-node flow-ai">
              <span className="node-icon">
                <Sparkles size={23} />
              </span>
              <div>
                <strong>AI Smart Setup</strong>
                <small>Đề xuất · kiểm tra · xác nhận</small>
              </div>
            </div>
            <div className="flow-line" />
            <div className="flow-node">
              <span className="node-icon mint">
                <Database size={23} />
              </span>
              <div>
                <strong>Dữ liệu chuẩn hóa</strong>
                <small>Có kiểu · có nguồn gốc</small>
              </div>
              <CheckCheck size={18} />
            </div>
          </div>
        </section>
      ) : (
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
      <PreparationGuide
        summary={summary}
        busy={busy}
        onAction={onAction}
        onResults={onResults}
      />
      <div className="section-heading">
        <div>
          <h2>Quy trình chuẩn bị dữ liệu</h2>
          <p>Một luồng thống nhất, từ bản gốc đến dữ liệu có thể sử dụng.</p>
        </div>
        <span className="subtle">3 bước rõ ràng</span>
      </div>
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
            <span className="supported">
              CSV & XLSX · Tối đa{" "}
              {workspace ? workspace.max_upload_bytes / 1048576 : 20} MB/tệp
            </span>
          </div>
        )}
      </section>
    </>
  );
}
