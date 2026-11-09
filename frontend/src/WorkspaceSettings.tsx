import { ChevronDown, Files, FolderOpen, PanelTop, ShieldCheck, UserRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Modal, Notice, Spinner } from "./components";
import type { WorkspaceSettings as Settings } from "./types";
import { PermanentDeletion } from "./PermanentDeletion";

const roles: Record<string, string> = {
  owner: "Chủ không gian",
  editor: "Có thể chỉnh sửa",
  viewer: "Chỉ xem",
};

type WorkspaceChoice = { id: string; name: string; role: string };

export function WorkspaceManager({ current, onRename }: {
  current: WorkspaceChoice;
  onRename: (name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [choices, setChoices] = useState<WorkspaceChoice[] | null>(null);
  const [selected, setSelected] = useState(current.id);
  const [action, setAction] = useState<"create" | "rename" | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [pending, setPending] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const submitting = useRef(false);
  const createRequest = useRef<{ name: string; key: string } | null>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void api<WorkspaceChoice[]>("/workspaces", { signal: controller.signal })
      .then(rows => { if (!controller.signal.aborted) setChoices(rows); })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Chưa tải được danh sách.");
      });
    return () => controller.abort();
  }, [open]);

  async function save() {
    if (submitting.current) return;
    submitting.current = true;
    setPending(true);
    setError("");
    setStatus("");
    try {
      if (!action) {
        await api("/workspaces/current", { method: "POST", body: JSON.stringify({ id: selected }) });
        const lastProject = localStorage.getItem("studio.project");
        if (lastProject) localStorage.setItem(`studio.project.${current.id}`, lastProject);
        const nextProject = localStorage.getItem(`studio.project.${selected}`);
        if (nextProject) localStorage.setItem("studio.project", nextProject);
        else localStorage.removeItem("studio.project");
        window.history.replaceState(null, "", "#page=settings");
        window.location.reload();
        return;
      }
      const body = action === "create" ? { name } : { name, expected_name: current.name };
      if (action === "create" && createRequest.current?.name !== name) {
        createRequest.current = { name, key: crypto.randomUUID() };
      }
      const saved = await api<WorkspaceChoice>(
        action === "create" ? "/workspaces" : "/workspaces/current/name",
        { method: action === "create" ? "POST" : "PATCH", body: JSON.stringify(body),
          headers: action === "create" && createRequest.current
            ? { "Idempotency-Key": createRequest.current.key }
            : undefined },
      );
      createRequest.current = null;
      setChoices(rows => [...(rows ?? []).filter(row => row.id !== saved.id), saved]);
      setSelected(saved.id);
      if (action === "rename") onRename(saved.name);
      setStatus(action === "create" ? "Đã tạo. Chọn Chuyển không gian để mở." : "Đã lưu tên mới.");
      setAction(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chưa thể hoàn tất thao tác.");
    } finally {
      submitting.current = false;
      setPending(false);
    }
  }

  return <>
    <button className="workspace-picker" aria-label="Quản lý không gian làm việc" aria-description={current.name} aria-haspopup="dialog"
      aria-expanded={open} title={current.name} ref={trigger} onClick={() => {
      setChoices(null);
      setSelected(current.id);
      setError("");
      setStatus("");
      setAction(null);
      setOpen(true);
    }}><strong>{current.name}</strong><ChevronDown size={15} aria-hidden="true" /></button>
    <Modal title="Quản lý không gian làm việc" open={open} returnFocus={trigger}
      onOpenChange={next => { if (!pending) setOpen(next); }}>
      {error && <Notice tone="error">{error}</Notice>}
      {status && <Notice tone="success">{status}</Notice>}
      {!choices && !error && <Spinner />}
      {choices && <form onSubmit={event => { event.preventDefault(); void save(); }}>
        {action ? <label>Tên không gian làm việc
          <input value={name} maxLength={200} required disabled={pending} onChange={event => setName(event.target.value)} />
        </label> : <label>Không gian có quyền truy cập
          <select value={selected} disabled={pending} onChange={event => setSelected(event.target.value)}>
            {choices.map(row => <option key={row.id} value={row.id}>{row.name} · {roles[row.role] ?? row.role}</option>)}
          </select>
        </label>}
        <div className="modal-actions">
          {action ? <button type="button" className="button secondary" disabled={pending} onClick={() => setAction(null)}>Hủy</button>
            : current.role === "owner" && <>
              <button type="button" className="button secondary" disabled={pending} onClick={() => { setName(""); setAction("create"); }}>Tạo không gian</button>
              <button type="button" className="button secondary" disabled={pending} onClick={() => { setName(current.name); setAction("rename"); }}>Đổi tên không gian hiện tại</button>
            </>}
          <button className="button primary" disabled={pending || (action ? !name.trim() : selected === current.id)}>
            {action === "create" ? "Tạo" : action === "rename" ? "Lưu tên" : "Chuyển không gian"}
          </button>
        </div>
      </form>}
    </Modal>
  </>;
}

export function WorkspaceSettings({ settings: s, role, tableDensity, onDensityChange, onManageProjects }: {
  settings: Settings;
  role: string;
  tableDensity: "comfortable" | "compact";
  onDensityChange: (value: "comfortable" | "compact") => void;
  onManageProjects?: (trigger: HTMLButtonElement) => void;
}) {
  const external = s.policy.mode === "CLOUD_ALLOWED" && s.policy.allow_external_ai;
  const available = external && s.agent_cloud_enabled && s.gemini_configured
    && s.gemini_requests_remaining !== 0 && s.ai_task_allowances?.agent?.remaining !== 0;

  return <section className="settings-page settings-register" aria-label="Cài đặt">
    <section aria-labelledby="settings-account">
      <h2 id="settings-account"><UserRound size={18} aria-hidden="true" /> Tài khoản và không gian làm việc</h2>
      <dl className="settings-rows">
        <div><dt>Không gian làm việc</dt><dd>{s.workspace_name}</dd></div>
        <div><dt>Quyền của bạn</dt><dd>{roles[role] ?? "Chưa xác minh"}</dd></div>
      </dl>
      {onManageProjects && <div className="settings-actions">
        <button className="text-button" onClick={event => onManageProjects(event.currentTarget)}>
          <FolderOpen size={17} aria-hidden="true" /> Quản lý dự án
        </button>
      </div>}
    </section>
    <section aria-labelledby="settings-privacy">
      <h2 id="settings-privacy"><ShieldCheck size={18} aria-hidden="true" /> AI và quyền riêng tư</h2>
      <dl className="settings-rows">
        <div><dt>Hỗ trợ AI</dt><dd>{available ? "Có thể yêu cầu AI hỗ trợ" : external ? "AI tạm thời chưa thể hỗ trợ" : "Xử lý trong ứng dụng"}</dd></div>
        <div><dt>Chia sẻ dữ liệu</dt><dd>{external ? "Cho phép sử dụng dịch vụ AI bên ngoài" : "Không gửi dữ liệu đến dịch vụ AI bên ngoài"}</dd></div>
      </dl>
      {external && !available && <p>Vẫn có thể xem dữ liệu và tiếp tục thiết lập thủ công.</p>}
      <details>
        <summary>Dữ liệu nào được sử dụng?</summary>
        <p>{external ? "Yêu cầu, cấu trúc bảng và một phần nhỏ dữ liệu có thể được gửi đi khi cần xử lý. Tệp gốc được giữ trong không gian làm việc."
          : "Dữ liệu được giữ trong không gian làm việc. Quyền được kiểm tra khi xem, xử lý hoặc tải kết quả."}</p>
        <p>{external && s.policy.allow_cloud_parsing ? "Chính sách cho phép đọc tài liệu bằng dịch vụ bên ngoài." : "Tài liệu không được gửi đến dịch vụ bên ngoài để đọc."}</p>
      </details>
    </section>
    <section aria-labelledby="settings-display">
      <h2 id="settings-display"><PanelTop size={18} aria-hidden="true" /> Hiển thị</h2>
      <fieldset className="density-preference">
        <legend>Mật độ bảng trên màn hình rộng</legend>
        <label><input type="radio" name="table-density" checked={tableDensity === "comfortable"} onChange={() => onDensityChange("comfortable")} /> Tiêu chuẩn</label>
        <label><input type="radio" name="table-density" checked={tableDensity === "compact"} onChange={() => onDensityChange("compact")} /> Gọn</label>
      </fieldset>
    </section>
    <section aria-labelledby="settings-limits">
      <h2 id="settings-limits"><Files size={18} aria-hidden="true" /> Tệp đính kèm</h2>
      <dl className="settings-rows">
        <div><dt>Định dạng</dt><dd>{s.agent_upload_extensions?.map(ext => ext.slice(1).toUpperCase()).join(", ") || "Chưa có thông tin"}</dd></div>
        <div><dt>Dung lượng tối đa</dt><dd>{(s.max_upload_bytes / 1048576).toLocaleString("vi-VN")} MB mỗi tệp</dd></div>
        <div><dt>Số tệp đính kèm</dt><dd>{s.agent_max_upload_files == null ? "Chưa có thông tin" : `${s.agent_max_upload_files} tệp mỗi lần`}</dd></div>
        <div><dt>Số dòng tối đa mỗi bảng</dt><dd>{s.max_rows.toLocaleString("vi-VN")} dòng</dd></div>
      </dl>
    </section>
    {role === "owner" && <PermanentDeletion kind="workspace" />}
  </section>;
}
