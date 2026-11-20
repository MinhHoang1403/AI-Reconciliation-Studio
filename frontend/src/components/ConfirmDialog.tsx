import { useEffect, useRef } from "react";

// Hộp thoại xác nhận cho thao tác không hoàn tác được (ví dụ xóa bộ dữ liệu).
// Dùng thẻ <dialog> gốc của trình duyệt: tự giữ focus bên trong, phím Esc để hủy.

type Props = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({ open, title, message, confirmLabel, busy, onConfirm, onCancel }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog ref={ref} className="dialog" aria-labelledby="dialog-title" onCancel={onCancel}>
      <h2 id="dialog-title">{title}</h2>
      <p>{message}</p>
      <div className="dialog__actions">
        <button className="button button--quiet" type="button" onClick={onCancel} disabled={busy}>
          Hủy
        </button>
        <button className="button button--danger" type="button" onClick={onConfirm} disabled={busy}>
          {busy ? "Đang xóa…" : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
