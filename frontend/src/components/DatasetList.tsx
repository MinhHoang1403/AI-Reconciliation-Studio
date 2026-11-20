import { useState } from "react";
import { FileSpreadsheet, FileText, Trash2 } from "lucide-react";

import { deleteDataset, type DatasetSummary } from "../api";
import { formatBytes, formatCount, formatDateTime } from "../format";
import { linkTo } from "../navigation";
import { ConfirmDialog } from "./ConfirmDialog";
import { StatusBadge } from "./StatusBadge";

// Danh sách bộ dữ liệu. Thanh dưới mỗi bộ dài theo số dòng (quy tắc "kích thước nói lên khối lượng").

type Props = { datasets: DatasetSummary[]; onChanged: () => void };

/** Số cột đang chờ người dùng xem ở bước ánh xạ, cộng qua mọi bảng của bộ dữ liệu. */
const pendingColumns = (dataset: DatasetSummary) =>
  dataset.tables.reduce((sum, table) => sum + table.mapping_pending, 0);

const totalRows = (dataset: DatasetSummary) =>
  dataset.tables.filter((table) => table.status === "READY").reduce((sum, table) => sum + table.row_count, 0);

export function DatasetList({ datasets, onChanged }: Props) {
  const [pending, setPending] = useState<DatasetSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const largest = Math.max(1, ...datasets.map(totalRows));

  async function confirmDelete() {
    if (!pending) return;
    setDeleting(true);
    try {
      await deleteDataset(pending.id);
      setPending(null);
      setError(null);
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không xóa được.");
      setPending(null);
    } finally {
      setDeleting(false);
    }
  }

  if (datasets.length === 0) {
    return (
      <section className="datasets datasets--empty" aria-labelledby="datasets-title">
        <h2 id="datasets-title">Bộ dữ liệu</h2>
        <p>Chưa có bộ dữ liệu nào. Tải tệp đơn hàng, thanh toán hoặc sao kê để bắt đầu.</p>
      </section>
    );
  }

  return (
    <section className="datasets" aria-labelledby="datasets-title">
      <h2 id="datasets-title">Bộ dữ liệu</h2>
      {error && <p className="notice notice--error" role="alert">{error}</p>}
      <ul className="datasets__list">
        {datasets.map((dataset) => {
          const rows = totalRows(dataset);
          const Icon = dataset.file_format === "CSV" ? FileText : FileSpreadsheet;
          const readyTables = dataset.tables.filter((table) => table.status === "READY");
          return (
            <li key={dataset.id} className="datasets__item">
              <Icon className="datasets__icon" aria-hidden="true" size={22} strokeWidth={1.6} />
              <div className="datasets__main">
                <a className="datasets__name" {...linkTo(`/du-lieu/${dataset.id}`)}>
                  {dataset.name}
                </a>
                <p className="datasets__meta">
                  {dataset.file_format} · {formatBytes(dataset.size_bytes)} · {formatDateTime(dataset.created_at)}
                  {readyTables.length > 1 && ` · ${readyTables.length} bảng`}
                </p>
                {dataset.status === "FAILED" && dataset.error_message && (
                  <p className="datasets__error">{dataset.error_message}</p>
                )}
                <div className="datasets__bar" aria-hidden="true">
                  <span style={{ width: `${(rows / largest) * 100}%` }} />
                </div>
              </div>
              <div className="datasets__side">
                {pendingColumns(dataset) > 0 ? (
                  <span className="badge" data-status="REVIEW">Cần xem {pendingColumns(dataset)} cột</span>
                ) : (
                  <StatusBadge status={dataset.status} />
                )}
                <span className="datasets__rows">{formatCount(rows)} dòng</span>
              </div>
              <button
                className="icon-button"
                type="button"
                aria-label={`Xóa bộ dữ liệu ${dataset.name}`}
                title="Xóa bộ dữ liệu"
                onClick={() => setPending(dataset)}
              >
                <Trash2 aria-hidden="true" size={18} strokeWidth={1.8} />
              </button>
            </li>
          );
        })}
      </ul>
      <ConfirmDialog
        open={pending !== null}
        title="Xóa bộ dữ liệu?"
        message={`“${pending?.name ?? ""}” cùng tệp gốc và mọi bảng đã đọc sẽ bị xóa hẳn, không khôi phục được.`}
        confirmLabel="Xóa hẳn"
        busy={deleting}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPending(null)}
      />
    </section>
  );
}
