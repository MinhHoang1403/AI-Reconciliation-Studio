import * as Dialog from "@radix-ui/react-dialog";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import {
  CheckCircle2,
  ChevronRight,
  FileSpreadsheet,
  Info,
  LoaderCircle,
  X,
} from "lucide-react";
import { useLayoutEffect, useRef, type ReactNode, type RefObject } from "react";
import { statusText, type Dataset } from "./types";

/** Chỉ định dạng chuỗi Decimal để đọc; không qua float hoặc tính lại tiền. */
export function formatDecimal(value: string): string {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value);
  if (!match) return value;
  return `${match[1]}${match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ".")}${match[3] ? `,${match[3]}` : ""}`;
}

export function Badge({ status, label }: { status: string; label?: string }) {
  return (
    <span className={`badge badge-${status.toLowerCase()}`}>
      {label ?? statusText[status] ?? status}
    </span>
  );
}
export function Notice({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: "info" | "error" | "success" | "warning";
}) {
  return (
    <div
      className={`notice ${tone}`}
      role={tone === "error" ? "alert" : "status"}
    >
      {tone === "success" ? <CheckCircle2 size={18} /> : <Info size={18} />}
      <div>{children}</div>
    </div>
  );
}
export function Spinner() {
  return (
    <span className="busy">
      <LoaderCircle size={18} className="spin" />
      Đang xử lý…
    </span>
  );
}
export function Modal({
  title,
  children,
  open,
  onOpenChange,
  wide = false,
  placement = "center",
  anchorName,
  returnFocus,
  shouldRestoreFocus,
}: {
  title: string;
  children: ReactNode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  wide?: boolean;
  placement?: "center" | "context";
  anchorName?: string;
  returnFocus?: RefObject<HTMLElement | null>;
  shouldRestoreFocus?: () => boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className={anchorName ? "modal-overlay dropdown-overlay" : "modal-overlay"} />
        <Dialog.Content
          className={`modal${wide ? " modal-wide" : ""}${placement === "context" ? " modal-context" : ""}${anchorName ? " dropdown-panel dropdown-dialog" : ""}`}
          style={anchorName ? { positionAnchor: anchorName } : undefined}
          aria-describedby={undefined}
          onFocusCapture={(event) => {
            const modal = event.currentTarget;
            const control = event.target;
            if (!(control instanceof HTMLElement) || control === modal) return;
            const bounds = modal.getBoundingClientRect();
            const item = control.getBoundingClientRect();
            // Radix wraps focus with preventScroll; keep the focused control visible.
            if (item.top < bounds.top || item.bottom > bounds.bottom) {
              control.scrollIntoView({ block: "nearest", inline: "nearest" });
            }
          }}
          onCloseAutoFocus={(event) => {
            if (shouldRestoreFocus && !shouldRestoreFocus()) {
              event.preventDefault();
              return;
            }
            if (returnFocus?.current?.isConnected) {
              event.preventDefault();
              returnFocus.current.focus({ preventScroll: true });
            }
          }}
        >
          <div className="modal-heading">
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Close className="icon-button" aria-label="Đóng">
              <X size={20} />
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
/** Vùng đọc phụ mở theo tác vụ. Radix tiếp tục quản lý focus khi vùng này phủ lên Chat. */
export function ContextPanel({ title, children, docked, onClose, returnFocus }: {
  title: string;
  children: ReactNode;
  docked: boolean;
  onClose: () => void;
  returnFocus?: RefObject<HTMLElement | null>;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const dockedNow = useRef(docked);
  useLayoutEffect(() => {
    dockedNow.current = docked;
    if (docked) closeButton.current?.focus({ preventScroll: true });
  }, [docked]);

  if (!docked) {
    return <Modal title={title} open placement="context" wide
      onOpenChange={open => { if (!open) onClose(); }} returnFocus={returnFocus}
      shouldRestoreFocus={() => !dockedNow.current}>
      {children}
    </Modal>;
  }

  function close() {
    onClose();
    if (returnFocus?.current?.isConnected) returnFocus.current.focus({ preventScroll: true });
  }
  return (
    <aside className="context-panel" aria-label={title} onKeyDown={event => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        close();
      }
    }}>
      <div className="modal-heading">
        <h2>{title}</h2>
        <button ref={closeButton} className="icon-button" aria-label="Đóng" onClick={close}>
          <X size={20} aria-hidden="true" />
        </button>
      </div>
      {children}
    </aside>
  );
}
export function DataTable({
  rows,
  columns,
  numericColumns,
}: {
  rows: Record<string, unknown>[];
  columns: ColumnDef<Record<string, unknown>>[];
  numericColumns?: ReadonlySet<string>;
}) {
  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <div
      className="table-scroll"
      tabIndex={0}
      aria-label="Bảng dữ liệu có thể cuộn"
    >
      <table>
        <thead>
          {table.getHeaderGroups().map((g) => (
            <tr key={g.id}>
              {g.headers.map((h) => (
                <th key={h.id} scope="col" className={numericColumns?.has(h.column.id) ? "numeric-cell" : undefined}>
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((r) => (
            <tr key={r.id}>
              {r.getVisibleCells().map((c) => (
                <td key={c.id} className={numericColumns?.has(c.column.id) ? "numeric-cell" : undefined}>
                  {flexRender(c.column.columnDef.cell, c.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && (
        <div className="empty-small">Không có dòng phù hợp.</div>
      )}
    </div>
  );
}
export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "∅";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function DatasetList({
  items,
  onSelect,
  selected,
}: {
  items: Dataset[];
  onSelect: (dataset: Dataset) => void;
  selected?: string;
}) {
  return (
    <div className="dataset-list">
      {items.map((d) => (
        <button
          className={`dataset-item ${selected === d.id ? "dataset-selected" : ""}`}
          key={d.id}
          aria-pressed={selected === d.id}
          onClick={() => onSelect(d)}
        >
          <span className="file-type">
            <FileSpreadsheet size={22} />
          </span>
          <span className="dataset-name">
            <strong>{d.name}</strong>
            <small>{new Date(d.created_at).toLocaleString("vi-VN")}</small>
          </span>
          <Badge status={d.status} />
          <ChevronRight size={18} />
        </button>
      ))}
    </div>
  );
}
