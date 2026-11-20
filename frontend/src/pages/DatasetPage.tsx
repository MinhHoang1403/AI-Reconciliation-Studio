import { useState } from "react";
import { ArrowLeft, RotateCw } from "lucide-react";

import { chooseHeaderRow, rereadDataset, type DatasetSummary, type TableSummary } from "../api";
import { ColumnProfileView } from "../components/ColumnProfileView";
import { CleaningView } from "../components/CleaningView";
import { MappingView } from "../components/MappingView";
import { StatusBadge } from "../components/StatusBadge";
import { TablePreview } from "../components/TablePreview";
import { formatBytes, formatCount, formatDateTime } from "../format";
import { linkTo } from "../navigation";
import { useDataset } from "../useDatasets";

// Trang chi tiết một bộ dữ liệu: các bảng (mỗi sheet một bảng), dòng tiêu đề,
// xem trước dữ liệu và hồ sơ cột.

type View = "rows" | "profile" | "mapping" | "cleaning";

export function DatasetPage({ datasetId }: { datasetId: string }) {
  const { state, refresh } = useDataset(datasetId);
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<View>("rows");

  return (
    <div className="dataset-page">
      <a className="back-link" {...linkTo("/du-lieu")}>
        <ArrowLeft aria-hidden="true" size={18} />
        Dữ liệu
      </a>
      {state.kind === "loading" && <p className="notice">Đang tải…</p>}
      {state.kind === "error" && <p className="notice notice--error" role="alert">{state.message}</p>}
      {state.kind === "ready" && (
        <DatasetDetail
          dataset={state.data}
          selectedId={selected}
          onSelect={setSelected}
          view={view}
          onView={setView}
          onChanged={refresh}
        />
      )}
    </div>
  );
}

type DetailProps = {
  dataset: DatasetSummary;
  selectedId: string | null;
  onSelect: (id: string) => void;
  view: View;
  onView: (view: View) => void;
  onChanged: () => void;
};

function DatasetDetail({ dataset, selectedId, onSelect, view, onView, onChanged }: DetailProps) {
  const table =
    dataset.tables.find((item) => item.id === selectedId) ??
    dataset.tables.find((item) => item.status === "READY") ??
    dataset.tables[0];

  return (
    <>
      <header className="page__header">
        <h1>{dataset.name}</h1>
        <p className="dataset-page__meta">
          {dataset.original_filename} · {formatBytes(dataset.size_bytes)} · tải lên {formatDateTime(dataset.created_at)}
          <span title={`SHA-256 của tệp gốc: ${dataset.sha256}`}>
            Mã tệp gốc <code className="dataset-page__hash">{dataset.sha256.slice(0, 12)}</code>
          </span>
        </p>
      </header>

      {dataset.status === "READING" && <p className="notice notice--busy">Đang đọc tệp, trang sẽ tự cập nhật…</p>}
      {dataset.status === "FAILED" && <FailedNotice dataset={dataset} onChanged={onChanged} />}

      {dataset.tables.length > 1 && (
        <div className="tabs" role="tablist" aria-label="Các bảng trong tệp">
          {dataset.tables.map((item) => (
            <button
              key={item.id}
              role="tab"
              type="button"
              aria-selected={item.id === table?.id}
              className="tabs__tab"
              onClick={() => onSelect(item.id)}
            >
              {item.sheet_name ?? "Bảng"}
              <span className="tabs__count">
                {item.status === "READY" ? formatCount(item.row_count) : <StatusBadge status={item.status} />}
              </span>
            </button>
          ))}
        </div>
      )}

      {table && <TableSection key={table.id} table={table} view={view} onView={onView} onChanged={onChanged} />}
    </>
  );
}

function FailedNotice({ dataset, onChanged }: { dataset: DatasetSummary; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="notice notice--error notice--action" role="alert">
      <span>{dataset.error_message ?? "Không đọc được tệp."}</span>
      <button
        className="button button--quiet"
        type="button"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          void rereadDataset(dataset.id).finally(() => {
            setBusy(false);
            onChanged();
          });
        }}
      >
        <RotateCw aria-hidden="true" size={16} />
        Đọc lại
      </button>
    </div>
  );
}

type TableProps = { table: TableSummary; view: View; onView: (view: View) => void; onChanged: () => void };

function TableSection({ table, view, onView, onChanged }: TableProps) {
  if (table.status === "READING") return <p className="notice notice--busy">Đang đọc bảng…</p>;
  if (table.status === "FAILED") {
    return (
      <>
        <p className="notice notice--error" role="alert">{table.error_message ?? "Không đọc được bảng."}</p>
        <HeaderRowControl table={table} onChanged={onChanged} />
      </>
    );
  }
  if (table.status === "NO_DATA") {
    return (
      <div className="notice notice--stack">
        <p>
          Sheet “{table.sheet_name}” không có bảng dữ liệu (cần ít nhất 2 cột và 1 dòng). Nếu đây là bảng, hãy
          chọn đúng dòng tiêu đề.
        </p>
        <HeaderRowControl table={table} onChanged={onChanged} />
      </div>
    );
  }
  return (
    <section className="table-section" aria-label={`Bảng ${table.sheet_name ?? ""}`}>
      <div className="table-section__bar">
        <div className="segmented" role="group" aria-label="Chế độ xem">
          <button type="button" aria-pressed={view === "rows"} onClick={() => onView("rows")}>
            Dữ liệu
          </button>
          <button type="button" aria-pressed={view === "profile"} onClick={() => onView("profile")}>
            Hồ sơ cột
          </button>
          <button type="button" aria-pressed={view === "mapping"} onClick={() => onView("mapping")}>
            Ánh xạ
            {table.mapping_pending > 0 && <span className="segmented__count">{table.mapping_pending}</span>}
          </button>
          <button type="button" aria-pressed={view === "cleaning"} onClick={() => onView("cleaning")}>
            Làm sạch
            {table.clean_open > 0 && <span className="segmented__count">{table.clean_open}</span>}
          </button>
        </div>
        {(view === "rows" || view === "profile") && <HeaderRowControl table={table} onChanged={onChanged} />}
      </div>
      {view === "rows" && <TablePreview tableId={table.id} />}
      {view === "profile" && <ColumnProfileView tableId={table.id} />}
      {view === "mapping" && (
        <MappingView tableId={table.id} mappingStatus={table.mapping_status} onChanged={onChanged} />
      )}
      {view === "cleaning" && (
        <CleaningView tableId={table.id} cleanStatus={table.clean_status} onChanged={onChanged} />
      )}
    </section>
  );
}

function HeaderRowControl({ table, onChanged }: { table: TableSummary; onChanged: () => void }) {
  const [value, setValue] = useState(String(table.header_row ?? ""));
  const [error, setError] = useState<string | null>(null);
  const inputId = `header-${table.id}`;

  async function apply() {
    const row = value.trim() === "" ? null : Number(value);
    if (row !== null && (!Number.isInteger(row) || row < 1)) {
      setError("Nhập số dòng từ 1 trở lên, hoặc để trống nếu bảng không có dòng tiêu đề.");
      return;
    }
    try {
      await chooseHeaderRow(table.id, row);
      setError(null);
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không đọc lại được.");
    }
  }

  return (
    <form
      className="header-row"
      onSubmit={(event) => {
        event.preventDefault();
        void apply();
      }}
    >
      <label htmlFor={inputId}>Dòng tiêu đề</label>
      <input
        id={inputId}
        type="number"
        min={1}
        inputMode="numeric"
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
      <span className="header-row__hint">{table.header_row_chosen_by_user ? "bạn đã chọn" : "tự nhận"}</span>
      <button className="button button--quiet" type="submit">
        Đọc lại
      </button>
      {error && <span className="header-row__error" role="alert">{error}</span>}
    </form>
  );
}
