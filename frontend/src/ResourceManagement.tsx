import { useEffect, useRef, useState, type RefObject } from "react";
import { Archive, ArrowLeft, RotateCcw, Trash2 } from "lucide-react";
import { api } from "./api";
import { Modal, Notice, Spinner } from "./components";
import { PermanentDeletion } from "./PermanentDeletion";

type State = "active" | "archived" | "deleted";
type Action = "archive" | "delete" | "restore";
export type ManagedResource = { kind: "projects" | "datasets"; projectId?: string; id?: string };
type Impact = {
  id: string;
  name: string;
  project_id: string;
  state: State;
  version: number;
  references: Record<string, number>;
  running_jobs: number;
  open_work: number;
  allowed: Action[];
};
const counts: Record<string, string> = {
  datasets: "Nguồn dữ liệu", mappings: "Cách đọc cột", prepared_results: "Bản chuẩn hóa",
  conversations: "Hội thoại", workflows: "Công việc", plans: "Phương án đối soát",
  runs: "Lượt đối soát", exports: "Báo cáo đã xuất",
};
const states = { active: "Đang dùng", archived: "Đã lưu trữ", deleted: "Đã xóa khỏi danh sách" };

export function ResourceManagement({ target, onClose, onChanged, returnFocus }: {
  target: ManagedResource;
  onClose: () => void;
  onChanged: (id: string, projectId: string, state: State) => void;
  returnFocus: RefObject<HTMLElement | null>;
}) {
  const [id, setId] = useState(target.id || "");
  const [filter, setFilter] = useState<State>("active");
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState<{ id: string; name: string }[]>([]);
  const [total, setTotal] = useState(0);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [newName, setNewName] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [purgePending, setPurgePending] = useState(false);
  const [busy, setBusy] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const request = useRef<AbortController | null>(null);
  const submitting = useRef(false);
  const project = target.kind === "projects";
  const object = project ? "dự án" : "nguồn dữ liệu";
  const endpoint = `/${target.kind}/${encodeURIComponent(id)}/lifecycle`;

  useEffect(() => {
    const controller = new AbortController();
    setBusy(true);
    setError("");
    setImpact(null);
    setRows([]);
    const options = { signal: controller.signal };
    const params = new URLSearchParams({ lifecycle: filter, offset: String(offset), limit: "20" });
    params.set("search", search);
    if (!project && target.projectId) params.set("project_id", target.projectId);
    const load = id
      ? api<Impact>(endpoint, options).then(value => { if (!controller.signal.aborted) setImpact(value); })
      : api<{ items: { id: string; name: string }[]; total: number }>(`/${target.kind}?${params}`, options)
        .then(page => { if (!controller.signal.aborted) { setRows(page.items); setTotal(page.total); } });
    void load.catch(err => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Chưa tải được thông tin."); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [id, endpoint, filter, offset, project, search, target.kind, target.projectId, refresh]);
  useEffect(() => () => request.current?.abort(), []);

  async function submit() {
    if (!action || !impact || submitting.current) return;
    submitting.current = true;
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    setError("");
    try {
      const changed = await api<Impact>(endpoint, {
        method: "POST", signal: controller.signal,
        body: JSON.stringify({ action, expected_state: impact.state, expected_version: impact.version, confirmation: project ? confirmation : null }),
      });
      if (controller.signal.aborted) return;
      setImpact(changed);
      setResult(changed.state === "active" ? "Đã khôi phục." : changed.state === "archived" ? "Đã lưu trữ." : "Đã xóa khỏi danh sách.");
      setAction(null);
      setConfirmation("");
      onChanged(changed.id, changed.project_id, changed.state);
    } catch (err) {
      if (!controller.signal.aborted) {
        setAction(null);
        setError(err instanceof Error ? err.message : "Chưa thể hoàn tất. Hãy kiểm tra lại.");
      }
    } finally {
      submitting.current = false;
      if (!controller.signal.aborted) setPending(false);
    }
  }

  async function rename() {
    if (!impact || newName === null || !newName.trim() || submitting.current) return;
    submitting.current = true;
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    setError("");
    try {
      const renamed = await api<Impact>(`/datasets/${encodeURIComponent(impact.id)}/name`, {
        method: "PATCH",
        signal: controller.signal,
        body: JSON.stringify({ name: newName, expected_name: impact.name }),
      });
      if (controller.signal.aborted) return;
      setImpact(renamed);
      setNewName(null);
      setResult("Đã đổi tên hiển thị.");
      onChanged(renamed.id, renamed.project_id, renamed.state);
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : "Chưa thể đổi tên nguồn.");
      }
    } finally {
      submitting.current = false;
      if (!controller.signal.aborted) setPending(false);
    }
  }

  return <Modal title={`Quản lý ${object}`} open wide returnFocus={returnFocus}
    onOpenChange={open => { if (!open && !pending && !purgePending) onClose(); }}>
    {id && <button className="text-button" disabled={pending || purgePending} onClick={() => {
      setId(""); setAction(null); setConfirmation(""); setNewName(null); setResult("");
    }}><ArrowLeft size={16} /> Danh sách {object}</button>}
    {result && <Notice tone="success">{result}</Notice>}
    {error && <Notice tone="error">{error} <button className="text-button" onClick={() => {
      setNewName(null);
      setRefresh(n => n + 1);
    }}>Kiểm tra lại</button></Notice>}
    {!id && <div className="resource-management">
      <div className="workspace-toolbar">
        <label>Danh sách<select value={filter} onChange={event => { setFilter(event.target.value as State); setOffset(0); }}>
          {Object.entries(states).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
        </select></label>
        <label>{project ? "Tìm dự án" : "Tìm nguồn"}<input type="search" value={search} maxLength={200}
          onChange={event => { setSearch(event.target.value); setOffset(0); }} /></label>
      </div>
      {!busy && !error && (rows.length ? <ul className="management-list">{rows.map(row => <li key={row.id}>
        <span>{row.name}</span><button className="text-button" aria-label={`Quản lý ${row.name}`} onClick={() => { setId(row.id); setResult(""); }}>Quản lý</button>
      </li>)}</ul> : <p>Không có {object} trong danh sách này.</p>)}
      {total > 20 && <div className="pagination"><button className="button secondary" disabled={busy || !offset} onClick={() => setOffset(n => Math.max(0, n - 20))}>Trang trước</button>
        <span>{offset + 1}–{Math.min(offset + 20, total)} / {total}</span>
        <button className="button secondary" disabled={busy || offset + 20 >= total} onClick={() => setOffset(n => n + 20)}>Trang sau</button>
      </div>}
    </div>}
    {busy && <Spinner />}
    {impact && <section className="management-impact" aria-label="Tác động">
      <div><h3>{impact.name}</h3><p>{states[impact.state]}</p></div>
      <dl>{Object.entries(impact.references).filter(([, count]) => count > 0).map(([key, count]) => <div key={key}><dt>{counts[key]}</dt><dd>{count.toLocaleString("vi-VN")}</dd></div>)}</dl>
      {Boolean(impact.running_jobs || impact.open_work) && <Notice tone="warning">
        {impact.running_jobs} tác vụ đang xử lý · {impact.open_work} công việc chưa kết thúc. Hoàn tất hoặc dừng công việc trước khi quản lý mục này.
      </Notice>}
      {impact.state === "active" && impact.allowed.includes("archive") && !impact.allowed.includes("delete") &&
        <p>Có dữ liệu hoặc lịch sử liên quan. Có thể lưu trữ để ngừng dùng trong công việc mới và giữ kết quả đã lưu.</p>}
      {!project && !impact.allowed.length && !impact.running_jobs && !impact.open_work &&
        <Notice>Khôi phục dự án trước khi thay đổi trạng thái của nguồn này.</Notice>}
      {newName !== null ? <form className="management-confirm" onSubmit={event => { event.preventDefault(); void rename(); }}>
        <p>Tên mới chỉ dùng để hiển thị trong Studio. Giữ phần mở rộng của tệp.</p>
        <label>Tên hiển thị<input value={newName} maxLength={255} required disabled={pending}
          onChange={event => setNewName(event.target.value)} /></label>
        <div className="modal-actions">
          <button type="button" className="button secondary" disabled={pending} onClick={() => setNewName(null)}>Hủy</button>
          <button className="button primary" disabled={pending || !newName.trim() || newName.trim() === impact.name}>Lưu tên</button>
        </div>
      </form> : !action ? <><div className="modal-actions">
        {!project && impact.state === "active" && <button className="button secondary" disabled={purgePending}
          onClick={() => setNewName(impact.name)}>Đổi tên hiển thị</button>}
        {impact.allowed.includes("archive") && <button className="button secondary" disabled={purgePending} onClick={() => setAction("archive")}><Archive size={16} /> Lưu trữ</button>}
        {impact.allowed.includes("delete") && <button className="button secondary" disabled={purgePending} onClick={() => setAction("delete")}><Trash2 size={16} /> Đưa vào Thùng rác</button>}
        {impact.allowed.includes("restore") && <button className="button primary" disabled={purgePending} onClick={() => setAction("restore")}><RotateCcw size={16} /> Khôi phục</button>}
      </div>
      <PermanentDeletion key={id} kind={project ? "project" : "dataset"} resourceId={id}
        onPending={setPurgePending} onDeleted={() => {
          setId(""); setResult("Đã xóa vĩnh viễn.");
          onChanged(impact.id, impact.project_id, "deleted");
        }} />
      </> : <form className="management-confirm" onSubmit={event => { event.preventDefault(); void submit(); }}>
        <p>{action === "archive" ? "Mục này rời danh sách đang dùng. Dữ liệu và lịch sử vẫn được giữ."
          : action === "delete" ? "Mục này bị xóa khỏi danh sách và đường dẫn cũ. Có thể khôi phục trong mục quản lý."
          : "Mục này sẽ xuất hiện lại trong danh sách đang dùng."}</p>
        {project && action !== "restore" && <label>Nhập lại tên dự án<input value={confirmation} maxLength={200} onChange={event => setConfirmation(event.target.value)} /></label>}
        <div className="modal-actions"><button type="button" className="button secondary" disabled={pending} onClick={() => setAction(null)}>Hủy</button>
          <button className={`button ${action === "delete" ? "danger" : "primary"}`} disabled={pending || (project && action !== "restore" && confirmation !== impact.name)}>Xác nhận {action === "archive" ? "lưu trữ" : action === "delete" ? "xóa" : "khôi phục"}</button>
        </div>
      </form>}
    </section>}
  </Modal>;
}
