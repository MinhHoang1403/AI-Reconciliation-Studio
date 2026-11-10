import { useEffect, useRef, useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { api } from "./api";
import { Modal, Notice } from "./components";
import { statusText, type Mapping } from "./types";

type Action = "archive" | "delete";
type Impact = { busy: boolean; referenced: boolean; allowed: Action[] };

export function MappingVersions({ mappings, selected, canManage, onView, onChange }: {
  mappings: Mapping[];
  selected?: string;
  canManage: boolean;
  onView: (id: string) => void;
  onChange: (id: string, action: Action) => Promise<void>;
}) {
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [id, setId] = useState("");
  const [impact, setImpact] = useState<Impact | null>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const mapping = mappings.find(item => item.id === id);
  useEffect(() => {
    if (!open || !id || !canManage) return;
    const controller = new AbortController();
    void api<Impact>(`/mappings/${id}/lifecycle`, { signal: controller.signal }).then(
      next => { if (!controller.signal.aborted) setImpact(next); },
      reason => { if (!controller.signal.aborted) setError(reason.message); },
    );
    return () => controller.abort();
  }, [open, id, canManage]);

  function select(next: string) {
    setId(next);
    setImpact(null);
    setAction(null);
    setError("");
  }

  async function confirm() {
    if (!action || !mapping || pending) return;
    setPending(true);
    setError("");
    try {
      await api(`/mappings/${mapping.id}/lifecycle`, {
        method: "POST", body: JSON.stringify({ action }), signal: AbortSignal.timeout(30000),
      });
      await onChange(mapping.id, action);
      setOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Chưa cập nhật được phiên bản.");
    } finally {
      setPending(false);
    }
  }

  if (!mappings.length && !open) return null;
  return <>
    <button ref={trigger} type="button" className="icon-button" title="Quản lý phiên bản ánh xạ"
      aria-label="Quản lý phiên bản ánh xạ" aria-haspopup="dialog" aria-expanded={open}
      onClick={() => { select(selected || mappings[0]?.id || ""); setOpen(true); }}>
      <MoreHorizontal size={18} aria-hidden="true" />
    </button>
    <Modal title="Quản lý phiên bản ánh xạ" open={open} returnFocus={trigger}
      onOpenChange={next => { if (!pending) setOpen(next); }}>
      <label>Chọn phiên bản
        <select value={id} disabled={pending} onChange={event => select(event.target.value)}>
          {mappings.map(item => <option key={item.id} value={item.id}>
            Lần {item.revision} · {statusText[item.status] || item.status}{item.archived ? " · Đã ẩn" : ""}
          </option>)}
        </select>
      </label>
      {canManage && mapping && !impact && !error && <p role="status">Đang kiểm tra lịch sử xử lý…</p>}
      {impact?.busy && <Notice tone="warning">Hãy đợi công việc sử dụng phiên bản này hoàn tất.</Notice>}
      {impact?.referenced && !impact.busy && <Notice>Phiên bản có lịch sử xử lý và được giữ để tra cứu.</Notice>}
      {error && <Notice tone="error">{error}</Notice>}
      {action && mapping && <Notice tone={action === "delete" ? "warning" : "info"}>
        {action === "delete"
          ? `Xóa vĩnh viễn Lần ${mapping.revision} khỏi danh sách ánh xạ?`
          : `Ẩn Lần ${mapping.revision} khỏi danh sách thường dùng? Bạn vẫn có thể xem bản này tại đây.`}
      </Notice>}
      <div className="modal-actions">
        {action ? <>
          <button type="button" className="button secondary" disabled={pending} onClick={() => setAction(null)}>Quay lại</button>
          <button type="button" className={`button ${action === "delete" ? "danger" : "primary"}`}
            disabled={pending} onClick={() => void confirm()}>
            {action === "delete" ? "Xác nhận xóa" : "Xác nhận ẩn"}
          </button>
        </> : <>
          <button type="button" className="button secondary" disabled={!mapping}
            onClick={() => { onView(id); setOpen(false); }}>Xem phiên bản</button>
          {impact?.allowed.includes("archive") && <button type="button" className="button secondary"
            onClick={() => setAction("archive")}>Ẩn phiên bản</button>}
          {impact?.allowed.includes("delete") && <button type="button" className="button danger"
            onClick={() => setAction("delete")}>Xóa vĩnh viễn</button>}
        </>}
      </div>
    </Modal>
  </>;
}
