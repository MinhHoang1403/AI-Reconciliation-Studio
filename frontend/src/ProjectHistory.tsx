import { useEffect, useState, type RefObject } from "react";
import { ArrowUpRight, MessageSquare } from "lucide-react";
import { api, ApiError } from "./api";
import type { Conversation } from "./assistantTypes";
import { Modal, Notice, Spinner } from "./components";

export function HistoryRows({ items, current, busy, onOpen }: {
  items: Conversation[];
  current?: string;
  busy: boolean;
  onOpen: (id: string) => void;
}) {
  return <ul className="conversation-register">{items.map(item => <li key={item.id}>
    <button className="history-item" aria-current={item.id === current ? "true" : undefined}
      disabled={busy} onClick={() => onOpen(item.id)}>
      <MessageSquare size={16} aria-hidden="true" />
      <span><strong>{item.title}</strong><small>{new Date(item.created_at).toLocaleString("vi-VN")}</small></span>
      <ArrowUpRight size={16} aria-hidden="true" />
    </button>
  </li>)}</ul>;
}

export function ProjectHistory({ projectId, projectName, onClose, onOpen, returnFocus }: {
  projectId: string;
  projectName: string;
  onClose: () => void;
  onOpen: (id: string) => void;
  returnFocus: RefObject<HTMLElement | null>;
}) {
  const [items, setItems] = useState<Conversation[]>([]);
  const [cursor, setCursor] = useState("");
  const [next, setNext] = useState("");
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(Boolean(projectId));
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const visible = items.filter(item => item.title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));

  useEffect(() => {
    if (!projectId) return;
    const controller = new AbortController();
    const query = new URLSearchParams({ project_id: projectId, limit: "20" });
    if (cursor) query.set("before_id", cursor);
    setBusy(true);
    setError("");
    void api<{ items: Conversation[]; has_more: boolean }>(`/conversations?${query}`, { signal: controller.signal })
      .then(page => {
        if (controller.signal.aborted) return;
        setItems(previous => cursor ? [...previous, ...page.items] : page.items);
        setNext(page.has_more ? page.items.at(-1)?.id || "" : "");
      })
      .catch(err => {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && [401, 403, 404].includes(err.status ?? 0)) {
          setItems([]);
          setNext("");
        }
        setError(err instanceof Error ? err.message : "Không tải được lịch sử.");
      })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [projectId, cursor, retry]);

  return <Modal title="Lịch sử" open wide returnFocus={returnFocus} onOpenChange={open => { if (!open) onClose(); }}>
    {projectId ? <div className="assistant-history" aria-label="Lịch sử hội thoại">
      <p>{projectName}</p>
      <label>Tìm trong hội thoại đã tải<input type="search" value={search} onChange={event => setSearch(event.target.value)} /></label>
      {busy && <Spinner />}
      {error && <Notice tone="error">{error} <button className="text-button" onClick={() => {
        setCursor("");
        setRetry(value => value + 1);
      }}>Tải lại lịch sử</button></Notice>}
      {!busy && !error && !visible.length && <p>{items.length ? "Không có hội thoại phù hợp." : "Chưa có hội thoại trong dự án này."}</p>}
      <HistoryRows items={visible} busy={busy} onOpen={onOpen} />
      {next && <button className="text-button" disabled={busy || !!error} onClick={() => setCursor(next)}>Tải thêm hội thoại</button>}
    </div> : <p>Chọn dự án để xem lịch sử hội thoại.</p>}
  </Modal>;
}
