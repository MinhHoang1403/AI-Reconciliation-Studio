import { useEffect, useId, useRef, useState } from "react";
import { api } from "./api";
import { Notice } from "./components";
import { errorText, qualityText } from "./types";

type Action = "REPLACE" | "EXCLUDE" | "KEEP_PENDING";
type Issue = { field: string; target_label: string; source_label: string | null;
  raw_value: string | null; original_value?: string | null; code: string; editable: boolean };
type Row = { source_row_id: string; source_row: number; issues: Issue[]; pending_reason: string | null };
type Job = { id: string; status: string };
type Snapshot = {
  dataset: string; sheet: string; current: boolean; total: number; items: Row[];
  valid_records: number; invalid_records: number; excluded_source_rows: number;
  excluded_amounts: { field: string; currency: string; amount: string }[];
  excluded_amounts_unavailable: boolean;
  latest_id: string | null; job: Job | null;
  decision_history: { source_row: number; field: string | null; original_value: string | null;
    replacement: string | null; action: Action; reason: string; revision: number }[];
};
const actions: Record<Action, string> = {
  REPLACE: "Sửa giá trị", EXCLUDE: "Loại dòng khỏi phạm vi", KEEP_PENDING: "Giữ để kiểm tra sau",
};
const pageSize = 10;
const pending = new Set(["QUEUED", "RUNNING", "RETRYABLE_FAILURE"]);

export function DataQualityPanel({ tableId, canonicalId, followLatest, onPublished, draft }: {
  tableId: string; canonicalId: string; followLatest?: boolean; onPublished?: (id: string) => void;
  draft?: { source_row_id: string; field: string; code: string; value: string; reason: string; row_index: number } | null;
}) {
  const [snapshotId, setSnapshotId] = useState(canonicalId);
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [page, setPage] = useState(() => Math.floor((draft?.row_index ?? 0) / pageSize));
  const [jobId, setJobId] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [updated, setUpdated] = useState(false);
  const [selection, setSelection] = useState<{ row: Row; issue: Issue }>();
  const [action, setAction] = useState<Action>("KEEP_PENDING");
  const [reason, setReason] = useState("");
  const [value, setValue] = useState("");
  const request = useRef({ payload: "", key: "" });
  const openedDraft = useRef(false);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const section = useId();
  const callback = useRef(onPublished);
  useEffect(() => { callback.current = onPublished; }, [onPublished]);
  useEffect(() => {
    const controller = new AbortController();
    api<Snapshot>(`/tables/${tableId}/quality-issues?canonical_id=${snapshotId}&offset=${page * pageSize}&limit=${pageSize}`, { signal: controller.signal })
      .then(data => {
        if (controller.signal.aborted) return;
        if (followLatest && data.latest_id && data.latest_id !== snapshotId) {
          setPage(0); setSnapshotId(data.latest_id); setSelection(undefined);
          return;
        }
        setSnapshot(data);
        if (draft && data.current && snapshotId === canonicalId && !openedDraft.current) {
          const row = data.items.find(item => item.source_row_id === draft.source_row_id);
          const issue = row?.issues.find(item => item.field === draft.field && item.code === draft.code);
          if (row && issue?.editable) {
            openedDraft.current = true;
            setSelection({ row, issue }); setAction("REPLACE");
            setReason(draft.reason); setValue(draft.value);
          }
        }
        if (data.job && pending.has(data.job.status)) setJobId(data.job.id);
        else if (data.job && !data.latest_id) setError("Lần chuẩn hóa đang dừng. Hãy xem công việc trong mục Dữ liệu.");
      })
      .catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [tableId, snapshotId, page, followLatest, canonicalId, draft]);
  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const job = await api<Job & { error_code?: string; result?: { canonical_id?: string } }>(
          `/jobs/${jobId}`, { signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        if (pending.has(job.status)) {
          timer = setTimeout(() => void poll(), 1000);
          return;
        }
        setJobId("");
        const id = job.result?.canonical_id;
        if (job.status === "SUCCEEDED" && id) {
          setUpdated(true); setPage(0); setSnapshotId(id); setSelection(undefined);
          callback.current?.(id);
        } else {
          setError(errorText[job.error_code || ""] || "Đã lưu quyết định. Hãy thử lại công việc chuẩn hóa trong Dữ liệu.");
        }
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Chưa đọc được trạng thái.");
      }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [jobId]);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!selection || sending || jobId) return;
    const body = JSON.stringify({
      canonical_id: snapshotId, source_row_id: selection.row.source_row_id,
      field: selection.issue.field, code: selection.issue.code, action, reason,
      replacement: action === "REPLACE" ? value : null,
    });
    if (request.current.payload !== body) request.current = { payload: body, key: crypto.randomUUID() };
    setSending(true); setError(""); setUpdated(false);
    try {
      const response = await api<{ job_id: string }>(`/tables/${tableId}/quality-decisions`, {
        method: "POST", body, headers: { "Idempotency-Key": request.current.key },
      });
      setJobId(response.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chưa lưu được quyết định.");
    } finally { setSending(false); }
  }

  return <section className="quality-resolution" aria-labelledby={section}>
    <h4 id={section}>Dòng cần xử lý</h4>
    {error && <p ref={errorRef} role="alert" tabIndex={-1} className="quality-error">{error}</p>}
    {jobId && <p role="status">Đã lưu quyết định. Đang tạo và kiểm tra bản chuẩn hóa mới…</p>}
    {updated && !jobId && <p role="status">Đã kiểm tra lại sau khi áp dụng quyết định.</p>}
    {!snapshot && !error && <p role="status">Đang đọc lỗi từ bản chuẩn hóa…</p>}
    {snapshot && <>
      <p>{snapshot.dataset} · {snapshot.sheet}</p>
      {draft && snapshotId === canonicalId && snapshot.current && <p>Kiểm tra bản nháp rồi xác nhận để áp dụng cho đúng dòng và cột.</p>}
      <p>{snapshot.valid_records} bản ghi dùng được · {snapshot.total} dòng nguồn cần kiểm tra · {snapshot.excluded_source_rows} dòng nguồn đã loại</p>
      {snapshot.excluded_amounts.map(amount => <p key={`${amount.field}:${amount.currency}`}>{amount.field}: {amount.amount} {amount.currency} đã loại</p>)}
      {snapshot.excluded_amounts_unavailable && <Notice tone="warning">Một số khoản của dòng đã loại chưa xác định được. Các khoản này không được tính là 0.</Notice>}
      {!snapshot.current && !jobId && snapshot.total > 0 && <p className="muted">Các dòng trong bản này chỉ có thể xem.</p>}
      {!snapshot.total && <p>Bản này không còn dòng nguồn cần xử lý.</p>}
      {snapshot.items.map(row => <div className="quality-row" key={row.source_row_id}>
        <h5>Dòng nguồn {row.source_row} · {row.issues.length} lỗi</h5>
        {row.pending_reason && <p>Giữ để kiểm tra sau. {row.pending_reason}</p>}
        {row.issues.map(issue => <div key={`${issue.field}:${issue.code}`}>
          <p><strong>{issue.source_label ?? "Nhiều cột"} → {issue.target_label}</strong></p>
          <p>Giá trị gốc: <strong>{(issue.original_value === undefined ? issue.raw_value : issue.original_value) ?? "Ô trống"}</strong>.
            {" "}{qualityText[issue.code] || "Giá trị chưa đáp ứng quy tắc đã xác nhận"}.
            Bản ghi chưa dùng được trong đối soát.</p>
          {snapshot.current && <button type="button" className="text-button" disabled={sending || !!jobId}
            aria-expanded={selection?.row === row && selection.issue === issue}
            onClick={() => { setSelection({ row, issue }); setAction(issue.editable ? "REPLACE" : "KEEP_PENDING"); setReason(""); setValue(""); setError(""); }}>
            Xử lý lỗi {issue.target_label}
          </button>}
          {selection?.row === row && selection.issue === issue && <form className="quality-form" onSubmit={submit}>
            <label>Quyết định<select value={action} disabled={sending || !!jobId} onChange={event => setAction(event.target.value as Action)}>
              {Object.entries(actions).filter(([key]) => issue.editable || key !== "REPLACE").map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select></label>
            {action === "REPLACE" && <label>Giá trị đã kiểm tra<input required maxLength={2048} value={value} onChange={event => setValue(event.target.value)} disabled={sending || !!jobId} /></label>}
            {action === "EXCLUDE" && <p>Dòng này sẽ không đi vào bản chuẩn hóa mới. Phạm vi đối soát phải được xác nhận trước khi chạy.</p>}
            <label>Lý do<input required maxLength={500} value={reason} onChange={event => setReason(event.target.value)} disabled={sending || !!jobId} /></label>
            <div className="agent-pagination">
              <button className="button primary" disabled={sending || !!jobId || !reason.trim() || (action === "REPLACE" && !value.trim())}>Xác nhận và kiểm tra lại</button>
              <button type="button" className="button secondary" disabled={sending || !!jobId} onClick={() => setSelection(undefined)}>Hủy</button>
            </div>
          </form>}
        </div>)}
      </div>)}
      {snapshot.total > pageSize && <div className="agent-pagination">
        <button className="button secondary" disabled={page === 0 || !!jobId} onClick={() => { setSelection(undefined); setPage(page - 1); }}>Trước</button>
        <span>Trang {page + 1} / {Math.ceil(snapshot.total / pageSize)}</span>
        <button className="button secondary" disabled={(page + 1) * pageSize >= snapshot.total || !!jobId} onClick={() => { setSelection(undefined); setPage(page + 1); }}>Sau</button>
      </div>}
      {!!snapshot.decision_history.length && <details><summary>Quyết định gần đây trong bản này</summary><ul>
        {snapshot.decision_history.map(entry => <li key={entry.revision}>
          Dòng {entry.source_row}{entry.field && ` · ${entry.field}`} · {actions[entry.action]}.
          {entry.action === "REPLACE" && ` ${entry.original_value ?? "Ô trống"} → ${entry.replacement}.`} {entry.reason}
        </li>)}
      </ul></details>}
    </>}
  </section>;
}
