import { useEffect, useRef, useState } from "react";
import { Trash2 } from "lucide-react";
import { api } from "./api";
import { Notice } from "./components";

type Capability = { enabled: boolean; workspace_id: string | null };
type Impact = {
  name: string;
  fingerprint: string;
  counts: Record<string, number>;
  missing_files: number;
};
type Receipt = { id: string; status: "DELETING" | "DELETED" };

const impactLabels: Record<string, string> = {
  projects: "Dự án",
  datasets: "Nguồn dữ liệu",
  dataset_versions: "Phiên bản nguồn",
  canonical_datasets: "Bản chuẩn hóa",
  reconciliation_runs: "Lượt đối soát",
  exception_cases: "Ngoại lệ",
  run_exports: "Báo cáo",
  conversations: "Hội thoại",
  files: "Tệp sẽ xóa",
  shared_files: "Tệp dùng chung được giữ",
};

export function PermanentDeletion({ kind, resourceId, onDeleted, onPending }: {
  kind: "dataset" | "project" | "workspace";
  resourceId?: string;
  onDeleted?: () => void;
  onPending?: (value: boolean) => void;
}) {
  const [capability, setCapability] = useState<Capability | null>(null);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [name, setName] = useState("");
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const confirmationInput = useRef<HTMLInputElement>(null);
  const done = useRef(onDeleted);
  useEffect(() => { done.current = onDeleted; }, [onDeleted]);
  useEffect(() => {
    if (impact) confirmationInput.current?.focus();
  }, [impact]);

  useEffect(() => {
    const controller = new AbortController();
    void api<Capability>("/permanent-deletion-capability", { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) setCapability(result); })
      .catch(() => { /* Chỉ hiện thao tác khi backend đã xác nhận quyền và môi trường. */ });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (receipt?.status !== "DELETING") return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api<Receipt>(`/permanent-deletion-receipts/${receipt.id}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (next.status === "DELETED") {
          setReceipt(next);
          setError("");
          done.current?.();
          return;
        }
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Chưa đọc được tiến độ.");
      }
      if (!controller.signal.aborted) timer = setTimeout(() => void poll(), 2000);
    };
    timer = setTimeout(() => void poll(), 2000);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [receipt]);

  const id = resourceId ?? capability?.workspace_id;
  if (!capability?.enabled || !id) return null;
  const endpoint = `/permanent-deletion/${kind}/${encodeURIComponent(id)}`;
  const label = kind === "workspace" ? "không gian làm việc" : kind === "project" ? "dự án" : "nguồn dữ liệu";

  async function preview() {
    if (request.current) return;
    request.current = true;
    setBusy(true);
    onPending?.(true);
    setError("");
    try {
      setImpact(await api<Impact>(endpoint));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chưa thể xem tác động.");
    } finally {
      request.current = false;
      setBusy(false);
      onPending?.(false);
    }
  }

  async function confirm() {
    if (!impact || name !== impact.name || request.current) return;
    request.current = true;
    setBusy(true);
    onPending?.(true);
    setError("");
    try {
      const result = await api<Receipt>(endpoint, {
        method: "POST",
        body: JSON.stringify({ fingerprint: impact.fingerprint, confirmation: name }),
      });
      setReceipt(result);
      if (result.status === "DELETED") done.current?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chưa xác định được kết quả. Thử lại cùng yêu cầu.");
    } finally {
      request.current = false;
      setBusy(false);
      onPending?.(false);
    }
  }

  if (receipt?.status === "DELETED") return <Notice tone="success">
    Đã xóa vĩnh viễn {label}.
    {kind === "workspace" && <button className="text-button" onClick={() => window.location.reload()}>Mở lại Studio</button>}
  </Notice>;

  if (receipt?.status === "DELETING") return <Notice tone="warning">
    Đang xóa {label}. Thông tin trên Studio đã được gỡ. Hệ thống tiếp tục kiểm tra các tệp còn lại.
    {error && <p>{error}</p>}
  </Notice>;

  return <section className="permanent-deletion" aria-label="Xóa vĩnh viễn" aria-busy={busy}>
    {error && <Notice tone="error">{error}</Notice>}
    {impact ? <div className="management-confirm">
      <h4>Xóa vĩnh viễn {impact.name}</h4>
      <p>Các mục liệt kê bên dưới sẽ bị xóa. Bạn không thể khôi phục từ Thùng rác. Bản sao lưu được giữ riêng.</p>
      <dl>{Object.entries(impactLabels).filter(([key]) => (impact.counts[key] ?? 0) > 0)
        .map(([key, title]) => <div key={key}><dt>{title}</dt><dd>{impact.counts[key].toLocaleString("vi-VN")}</dd></div>)}</dl>
      {impact.missing_files > 0 && <Notice tone="warning">{impact.missing_files} tệp trong danh mục đã vắng mặt.</Notice>}
      <label>Nhập đúng tên {label}<input ref={confirmationInput} value={name} maxLength={255} disabled={busy}
        onChange={event => setName(event.target.value)} /></label>
      <div className="modal-actions">
        <button type="button" className="button secondary" disabled={busy} onClick={() => {
          setImpact(null); setName(""); setError("");
          requestAnimationFrame(() => trigger.current?.focus());
        }}>Hủy</button>
        <button type="button" className="button danger" disabled={busy || name !== impact.name}
          onClick={() => void confirm()}>{busy ? "Đang xóa…" : "Xác nhận xóa vĩnh viễn"}</button>
      </div>
    </div> : <button ref={trigger} type="button" className="text-button" disabled={busy} onClick={() => void preview()}>
      <Trash2 size={16} aria-hidden="true" /> {busy ? "Đang xem tác động…" : "Xóa vĩnh viễn"}
    </button>}
  </section>;
}
