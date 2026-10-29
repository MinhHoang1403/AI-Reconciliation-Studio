import * as Dialog from "@radix-ui/react-dialog";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { CheckCircle2, Info, LoaderCircle, X } from "lucide-react";
import type { ReactNode, RefObject } from "react";
import { statusText } from "./types";

export function Badge({ status }: { status: string }) {
  return (
    <span className={`badge badge-${status.toLowerCase()}`}>
      {statusText[status] || status}
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
  returnFocus,
}: {
  title: string;
  children: ReactNode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  wide?: boolean;
  returnFocus?: RefObject<HTMLElement | null>;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content
          className={`modal ${wide ? "modal-wide" : ""}`}
          aria-describedby={undefined}
          onCloseAutoFocus={event => {
            if (returnFocus?.current) {
              event.preventDefault();
              returnFocus.current.focus();
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
export function DataTable({
  rows,
  columns,
}: {
  rows: Record<string, unknown>[];
  columns: ColumnDef<Record<string, unknown>>[];
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
                <th key={h.id}>
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
                <td key={c.id}>
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
