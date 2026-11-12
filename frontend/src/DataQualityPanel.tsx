import { useEffect, useId, useRef, useState } from "react";
import { api } from "./api";
import { formatDecimal } from "./components";
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
const confirmAction: Record<Action, string> = {
  REPLACE: "Xác nhận và kiểm tra lại", EXCLUDE: "Xác nhận loại trừ", KEEP_PENDING: "Xác nhận giữ để kiểm tra sau",
};
const pageSize = 10;
const pending = new Set(["QUEUED", "RUNNING", "RETRYABLE_FAILURE"]);

export function DataQualityPanel({ tableId, canonicalId, followLatest, onPublished, draft, sourceName }: {
  tableId: string; canonicalId: string; followLatest?: boolean; onPublished?: (id: string) => void;
  sourceName?: string;
  draft?: { source_row_id: string; field: string; code: string; value: string; reason: string; row_index: number } | null;
}) {
  const [snapshotId, setSnapshotId] = useState(canonicalId);
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [page, setPage] = useState(() => Math.floor((draft?.row_index ?? 0) / pageSize));
  const [jobId, setJobId] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [updateMessage, setUpdateMessage] = useState("");
  const [selection, setSelection] = useState<{ row: Row; issue: Issue }>();
  const [action, setAction] = useState<Action>("KEEP_PENDING");
  const [reason, setReason] = useState("");
  const [value, setValue] = useState("");
  const request = useRef({ payload: "", key: "" });
  const openedDraft = useRef(false);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const statusRef = useRef<HTMLParagraphElement>(null);
  const decisionRef = useRef<HTMLSelectElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const focusDecision = useRef(false);
  const submittedAction = useRef<Action | null>(null);
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
          const savedAction = submittedAction.current;
          const restoreFocus = statusRef.current?.closest("section")?.contains(document.activeElement)
            || document.activeElement === document.body;
          setUpdateMessage(savedAction === "KEEP_PENDING"
            ? "Đã ghi nhận quyết định giữ lại. Dòng vẫn cần kiểm tra."
            : "Đã kiểm tra lại sau khi áp dụng quyết định.");
          if (savedAction && restoreFocus) statusRef.current?.focus({ preventScroll: true });
          submittedAction.current = null;
          setPage(0); setSnapshotId(id); setSelection(undefined);
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
  useEffect(() => { if (error) errorRef.current?.focus({ preventScroll: true }); }, [error]);
  useEffect(() => {
    if (selection && focusDecision.current) {
      decisionRef.current?.focus({ preventScroll: true });
      focusDecision.current = false;
    } else if (!selection && triggerRef.current?.isConnected) {
      triggerRef.current.focus({ preventScroll: true });
      triggerRef.current = null;
    }
  }, [selection]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!selection || sending || jobId) return;
    const body = JSON.stringify({
      canonical_id: snapshotId, source_row_id: selection.row.source_row_id,
      field: selection.issue.field, code: selection.issue.code, action, reason,
      replacement: action === "REPLACE" ? value : null,
    });
    if (request.current.payload !== body) request.current = { payload: body, key: crypto.randomUUID() };
    setSending(true); setError(""); setUpdateMessage("");
    try {
      const response = await api<{ job_id: string }>(`/tables/${tableId}/quality-decisions`, {
        method: "POST", body, headers: { "Idempotency-Key": request.current.key },
      });
      submittedAction.current = action;
      triggerRef.current = null;
      setJobId(response.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chưa lưu được quyết định.");
    } finally { setSending(false); }
  }

  const excluded = snapshot?.decision_history.filter(entry => entry.action === "EXCLUDE") ?? [];
  const history = snapshot?.decision_history.filter(entry => entry.action !== "EXCLUDE") ?? [];
  const busy = sending || !!jobId;
  const missingInput = !reason.trim() || (action === "REPLACE" && !value.trim());
  return <section className="quality-resolution" aria-label="Dòng cần xử lý">
    <header className="quality-heading">
      <h4>{snapshot?.dataset || sourceName || "Dòng cần xử lý"}{snapshot && (snapshot.total
        ? ` — ${snapshot.total.toLocaleString("vi-VN")} dòng cần kiểm tra`
        : " — Đã kiểm tra")}</h4>
      {snapshot && <p className="muted">{snapshot.total
        ? `${snapshot.valid_records.toLocaleString("vi-VN")} bản ghi dùng được · ${snapshot.sheet}`
        : `Đã chuẩn hóa ${snapshot.valid_records.toLocaleString("vi-VN")} dòng.`}</p>}
    </header>
    {error && <p ref={errorRef} role="alert" tabIndex={-1} className="quality-error">{error}</p>}
    <p className="quality-update" ref={statusRef} role="status" tabIndex={-1}>{jobId
      ? "Đã lưu quyết định. Đang tạo và kiểm tra bản chuẩn hóa mới…"
      : updateMessage}</p>
    {!snapshot && !error && <p role="status">Đang đọc lỗi từ bản chuẩn hóa…</p>}
    {snapshot && <>
      {draft && snapshotId === canonicalId && snapshot.current && <p>Kiểm tra bản nháp rồi xác nhận để áp dụng cho đúng dòng và cột.</p>}
      {!snapshot.current && !jobId && snapshot.total > 0 && <p className="muted">Các dòng trong bản này chỉ có thể xem.</p>}
      {snapshot.items.map(row => {
        const singleIssue = row.issues.length === 1 ? row.issues[0] : undefined;
        return <section className="quality-row" key={row.source_row_id}>
          <h5>Dòng nguồn {row.source_row} — {singleIssue
            ? qualityText[singleIssue.code] || "Giá trị cần kiểm tra"
            : `${row.issues.length} lỗi`}</h5>
          {row.pending_reason && <p className="quality-pending"><strong>Đã ghi nhận quyết định — Vẫn cần kiểm tra.</strong> {row.pending_reason}</p>}
          {row.issues.map(issue => {
            const open = selection?.row === row && selection.issue === issue;
            const original = (issue.original_value === undefined ? issue.raw_value : issue.original_value) ?? "Ô trống";
            return <div className="quality-issue" key={`${issue.field}:${issue.code}`}>
              {!singleIssue && <p><strong>{qualityText[issue.code] || "Giá trị chưa đáp ứng quy tắc đã xác nhận"}.</strong></p>}
              <p className="quality-value"><span>{issue.source_label ?? "Nhiều cột nguồn"}</span><span>Giá trị gốc <code>{original}</code></span></p>
              {issue.source_label !== issue.target_label && <p className="muted">Trường đích {issue.target_label}</p>}
              <p>Bản ghi chưa dùng được trong đối soát.</p>
              {snapshot.current && <button type="button" className="button secondary quality-action" disabled={busy} hidden={open} aria-expanded={open}
                aria-label={`Xử lý lỗi ${issue.target_label} · dòng ${row.source_row}`}
                onClick={event => {
                  triggerRef.current = event.currentTarget;
                  focusDecision.current = true;
                  setSelection({ row, issue }); setAction(issue.editable ? "REPLACE" : "KEEP_PENDING");
                  setReason(""); setValue(""); setError("");
                }}>
                Xử lý lỗi
              </button>}
              {open && <form className="quality-form" onSubmit={submit} onKeyDown={event => {
                if (event.key === "Escape" && !event.defaultPrevented && !busy) {
                  event.stopPropagation();
                  setSelection(undefined);
                }
              }}>
                <label>Quyết định<select ref={decisionRef} value={action} disabled={busy} onChange={event => setAction(event.target.value as Action)}>
                  {Object.entries(actions).filter(([key]) => issue.editable || key !== "REPLACE").map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                </select></label>
                {action === "REPLACE" && <label>Giá trị đã kiểm tra<input required maxLength={2048} value={value} onChange={event => setValue(event.target.value)} disabled={busy}/></label>}
                {action === "EXCLUDE" && <p>Dòng này nằm ngoài bản chuẩn hóa mới. Bạn sẽ xác nhận phạm vi đối soát trước khi chạy.</p>}
                <label>Lý do<input required maxLength={500} value={reason} onChange={event => setReason(event.target.value)} disabled={busy}/></label>
                {missingInput && <p id={section} className="muted">
                  {action === "REPLACE" ? "Nhập giá trị đã kiểm tra và lý do để xác nhận." : "Nhập lý do để xác nhận quyết định."}
                </p>}
                <div className="agent-pagination">
                  <button type="submit" className="button primary" disabled={busy || missingInput} aria-describedby={missingInput ? section : undefined}>
                    {confirmAction[action]}
                  </button>
                  <button type="button" className="button secondary" disabled={busy} onClick={() => setSelection(undefined)}>Hủy</button>
                </div>
              </form>}
            </div>;
          })}
        </section>;
      })}
      {snapshot.total > pageSize && <div className="agent-pagination">
        <button className="button secondary" disabled={page === 0 || busy} onClick={() => { setSelection(undefined); setPage(page - 1); }}>Trước</button>
        <span>Trang {page + 1} / {Math.ceil(snapshot.total / pageSize)}</span>
        <button className="button secondary" disabled={(page + 1) * pageSize >= snapshot.total || busy} onClick={() => { setSelection(undefined); setPage(page + 1); }}>Sau</button>
      </div>}
      {snapshot.excluded_source_rows > 0 && <section className="quality-excluded">
        <h5>Đã loại trừ khỏi phạm vi</h5>
        <p>{snapshot.excluded_source_rows.toLocaleString("vi-VN")} dòng nằm ngoài bản chuẩn hóa.</p>
        {snapshot.excluded_amounts.map(amount => <p key={`${amount.field}:${amount.currency}`}>
          Số tiền loại trừ đã xác định <strong>{formatDecimal(amount.amount)} {amount.currency}</strong>
          {snapshot.excluded_amounts.length > 1 && ` · ${amount.field}`}
        </p>)}
        {snapshot.excluded_amounts_unavailable && <p>{snapshot.excluded_amounts.length
          ? "Chưa xác định được đầy đủ số tiền loại trừ."
          : "Chưa xác định được số tiền loại trừ."}</p>}
        {excluded.length === 1 && <p>Dòng {excluded[0].source_row} · {excluded[0].reason}</p>}
        {excluded.length > 1 && <details><summary>Lý do loại trừ gần đây</summary><ul>
          {excluded.map(entry => <li key={entry.revision}>Dòng {entry.source_row} · {entry.reason}</li>)}
        </ul></details>}
      </section>}
      {history.length > 0 && <details className="quality-history"><summary>Quyết định gần đây trong bản này</summary><ul>
        {history.map(entry => <li key={entry.revision}>
          <strong>Dòng {entry.source_row} · {entry.action === "REPLACE" ? "Đã lưu chỉnh sửa" : "Đã ghi nhận giữ chờ"}</strong>
          {entry.field && <p>{entry.field}</p>}
          {entry.action === "REPLACE" && <p><code>{entry.original_value ?? "Ô trống"}</code> → <code>{entry.replacement}</code></p>}
          <p>{entry.reason}</p>
        </li>)}
      </ul></details>}
    </>}
  </section>;
}
