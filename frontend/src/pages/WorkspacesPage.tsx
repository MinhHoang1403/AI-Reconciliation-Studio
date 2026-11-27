import { useEffect, useRef, useState, type FormEvent } from "react";
import { Pencil, Trash2 } from "lucide-react";

import { createWorkspace, deleteWorkspace, renameWorkspace, type Workspace } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { formatCount, formatDateTime } from "../format";
import { openWorkspace } from "../workspace";
import { useWorkspaces } from "../WorkspaceContext";

// Trang Quản lý phiên làm việc (/phien): tạo phiên trống mới (tạo xong mở ngay), đổi tên,
// xóa hẳn một phiên cùng mọi thứ bên trong, mở phiên khác. Không nằm trên thanh điều hướng;
// vào từ bộ chọn phiên.

const message = (reason: unknown, fallback: string) => (reason instanceof Error ? reason.message : fallback);

function contents(item: Workspace, separator = " · "): string {
  return [
    `${formatCount(item.datasets)} tệp`,
    `${formatCount(item.reconciliations)} lần đối soát`,
    `${formatCount(item.threads)} cuộc trò chuyện`,
  ].join(separator);
}

export function WorkspacesPage() {
  const { workspaces, current, refresh } = useWorkspaces();
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState<Workspace | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const createRef = useRef<HTMLInputElement>(null);

  // Đến từ "Tạo phiên mới" ở bộ chọn phiên: đặt con trỏ sẵn vào ô tên.
  useEffect(() => {
    if (window.location.hash === "#tao") createRef.current?.focus();
  }, []);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || creating) return;
    setCreating(true);
    try {
      const made = await createWorkspace(name);
      openWorkspace(made.id); // phiên mới trống: bắt đầu từ Dashboard
    } catch (reason) {
      setError(message(reason, "Không tạo được phiên."));
      setCreating(false);
    }
  }

  async function saveName(event: FormEvent, item: Workspace) {
    event.preventDefault();
    if (!draft.trim() || saving) return;
    setSaving(true);
    try {
      await renameWorkspace(item.id, draft);
      await refresh();
      setEditing(null);
      setError(null);
    } catch (reason) {
      setError(message(reason, "Không đổi được tên phiên."));
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    if (!removing) return;
    setDeleting(true);
    try {
      await deleteWorkspace(removing.id);
      if (removing.id === current.id) {
        // Xóa chính phiên đang mở: chuyển sang phiên còn lại đầu tiên.
        const next = workspaces.find((item) => item.id !== removing.id);
        if (next) openWorkspace(next.id);
        return;
      }
      await refresh();
      setRemoving(null);
      setError(null);
    } catch (reason) {
      setError(message(reason, "Không xóa được phiên."));
      setRemoving(null);
    } finally {
      setDeleting(false);
    }
  }

  const onlyOne = workspaces.length === 1;

  return (
    <div className="workspaces">
      <header className="page__header">
        <h1>Phiên làm việc</h1>
        <p>
          Mỗi phiên là một không gian riêng: tệp, kỳ đối soát, báo cáo, cuộc trò chuyện với AI và lịch sử thao tác chỉ
          nằm trong phiên đó. Tạo phiên mới để bắt đầu từ trang trắng cho một cửa hàng, một khách hàng hay một đợt làm việc
          khác.
        </p>
      </header>

      <form className="workspaces__create" onSubmit={create}>
        <label htmlFor="workspace-name">Tên phiên mới</label>
        <div className="workspaces__create-row">
          <input
            ref={createRef}
            id="workspace-name"
            value={name}
            maxLength={80}
            placeholder="Ví dụ: Cửa hàng Quận 1 – tháng 11"
            autoComplete="off"
            onChange={(event) => setName(event.target.value)}
          />
          <button className="button button--primary" type="submit" disabled={!name.trim() || creating}>
            {creating ? "Đang tạo…" : "Tạo và mở phiên"}
          </button>
        </div>
        <p className="workspaces__hint">Lĩnh vực: Bán hàng (đơn hàng ↔ thanh toán ↔ sao kê ngân hàng).</p>
      </form>

      {error && (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      )}

      <section className="workspaces__list-panel" aria-labelledby="workspaces-list">
        <h2 id="workspaces-list">Các phiên ({formatCount(workspaces.length)})</h2>
        <ul className="workspaces__list">
          {workspaces.map((item) => {
            const here = item.id === current.id;
            return (
              <li key={item.id} className="workspaces__item" aria-current={here ? "true" : undefined}>
                {editing === item.id ? (
                  <form className="workspaces__rename" onSubmit={(event) => void saveName(event, item)}>
                    <label className="visually-hidden" htmlFor={`rename-${item.id}`}>
                      Tên mới cho phiên {item.name}
                    </label>
                    <input
                      id={`rename-${item.id}`}
                      value={draft}
                      maxLength={80}
                      autoFocus
                      onChange={(event) => setDraft(event.target.value)}
                      onKeyDown={(event) => event.key === "Escape" && setEditing(null)}
                    />
                    <button className="button button--primary" type="submit" disabled={!draft.trim() || saving}>
                      {saving ? "Đang lưu…" : "Lưu"}
                    </button>
                    <button className="button button--quiet" type="button" onClick={() => setEditing(null)}>
                      Hủy
                    </button>
                  </form>
                ) : (
                  <>
                    <div className="workspaces__main">
                      <h3 className="workspaces__name">
                        {item.name}
                        {here && <span className="workspaces__here">Đang mở</span>}
                      </h3>
                      <p className="workspaces__meta">
                        {item.domain_label} · {contents(item)}
                      </p>
                      <p className="workspaces__meta">
                        Hoạt động gần nhất: {item.last_activity ? formatDateTime(item.last_activity) : "chưa có"}
                      </p>
                    </div>
                    <div className="workspaces__actions">
                      {!here && (
                        <button className="button button--quiet" type="button" onClick={() => openWorkspace(item.id)}>
                          Mở phiên
                        </button>
                      )}
                      <button
                        className="icon-button"
                        type="button"
                        aria-label={`Đổi tên phiên ${item.name}`}
                        title="Đổi tên"
                        onClick={() => {
                          setEditing(item.id);
                          setDraft(item.name);
                        }}
                      >
                        <Pencil aria-hidden="true" size={18} />
                      </button>
                      <button
                        className="icon-button"
                        type="button"
                        aria-label={`Xóa phiên ${item.name}`}
                        title={onlyOne ? "Cần ít nhất một phiên; hãy tạo phiên mới trước khi xóa" : "Xóa phiên"}
                        disabled={onlyOne}
                        onClick={() => setRemoving(item)}
                      >
                        <Trash2 aria-hidden="true" size={18} />
                      </button>
                    </div>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      <ConfirmDialog
        open={removing !== null}
        title="Xóa phiên làm việc"
        message={
          removing
            ? `Xóa vĩnh viễn phiên “${removing.name}” cùng ${contents(removing, ", ")} và toàn bộ lịch sử thao tác của ` +
              "phiên. Không hoàn tác được. Các phiên khác không bị ảnh hưởng."
            : ""
        }
        confirmLabel="Xóa phiên"
        busy={deleting}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setRemoving(null)}
      />
    </div>
  );
}
