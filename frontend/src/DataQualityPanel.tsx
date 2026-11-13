import { useEffect, useId, useRef, useState } from "react";
import { api } from "./api";
import { formatDecimal, Modal } from "./components";
import { errorText, qualityText } from "./types";

type Action = "REPLACE" | "EXCLUDE" | "KEEP_PENDING";
type Issue = { field: string; target_label: string; source_label: string | null;
  raw_value: string | null; original_value?: string | null; code: string; editable: boolean };
type Row = { source_row_id: string; source_row: number; issues: Issue[]; pending_reason: string | null };
type Job = { id: string; status: string };
type Snapshot = {
  dataset: string; sheet: string; current: boolean; total: number; items: Row[]; issue_counts?: Record<string, number>;
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

export function DataQualityPanel({ tableId, canonicalId, followLatest, onPublished, draft, sourceName, chatProjectId, showIssueRows }: {
  tableId: string; canonicalId: string; followLatest?: boolean; onPublished?: (id: string) => void;
  sourceName?: string;
  chatProjectId?: string;
  showIssueRows?: boolean;
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
  const [action, setAction] = useState<Action | "">("");
  const [reason, setReason] = useState("");
  const [value, setValue] = useState("");
  const [showRows, setShowRows] = useState(!!draft || !chatProjectId || !!showIssueRows);
  const [raw, setRaw] = useState<{ row: number; values?: Record<string, unknown>; error?: string }>();
  const rawTrigger = useRef<HTMLButtonElement>(null);
  const nextRow = useRef(false);
  const rowButtons = useRef(new Map<string, HTMLButtonElement>());
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
        if (nextRow.current) {
          nextRow.current = false;
          const row = data.items.find(item => !item.pending_reason);
          if (row?.issues[0] && data.current) {
            setSelection({ row, issue: row.issues[0] });
            setAction(""); setReason(""); setValue("");
          }
        }
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
          nextRow.current = !!chatProjectId && showRows;
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
  }, [jobId, chatProjectId, showRows]);
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
    if (!selection || !action || sending || jobId) return;
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

  useEffect(() => {
    if (!raw || raw.values || raw.error || !chatProjectId) return;
    const controller = new AbortController();
    api<{ rows: Record<string, unknown>[] }>("/agent/source-rows", {
      method: "POST", signal: controller.signal,
      body: JSON.stringify({ project_id: chatProjectId, table_id: tableId, row: raw.row }),
    }).then(result => {
      if (!controller.signal.aborted) setRaw({ row: raw.row, values: result.rows[0] || {} });
    }).catch(err => {
      if (!controller.signal.aborted) setRaw({ row: raw.row, error: err.message || "Không đọc được dòng gốc." });
    });
    return () => controller.abort();
  }, [raw, tableId, chatProjectId]);

  const excluded = snapshot?.decision_history.filter(entry => entry.action === "EXCLUDE") ?? [];
  const history = snapshot?.decision_history.filter(entry => entry.action !== "EXCLUDE") ?? [];
  const busy = sending || !!jobId;
  const missingInput = !reason.trim() || (action === "REPLACE" && !value.trim());
  function closeSelection() {
    if (chatProjectId && selection) triggerRef.current = rowButtons.current.get(selection.row.source_row_id) || null;
    setSelection(undefined);
  }
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
      {chatProjectId && !!snapshot.total && <>
        {!!Object.keys(snapshot.issue_counts || {}).length && <p className="muted">{Object.entries(snapshot.issue_counts || {}).map(([code, count]) =>
          `${count.toLocaleString("vi-VN")} ${code === "CURRENCY_MISMATCH" ? "dòng khác tiền tệ" : (qualityText[code] || "dòng cần kiểm tra").toLocaleLowerCase("vi-VN")}`).join(" · ")}</p>}
        <button type="button" className="text-button quality-action" aria-expanded={showRows} disabled={busy}
          onClick={() => {
            setShowRows(!showRows);
            const row = !showRows ? snapshot.items.find(item => !item.pending_reason) || snapshot.items[0] : undefined;
            if (row?.issues[0]) {
              focusDecision.current = snapshot.current;
              setSelection({ row, issue: row.issues[0] });
              setAction(""); setReason(""); setValue("");
            } else setSelection(undefined);
          }}>
          {showRows ? "Thu gọn các dòng" : `${snapshot.current ? "Xử lý" : "Xem"} ${snapshot.total.toLocaleString("vi-VN")} dòng`}
        </button>
      </>}
      {draft && snapshotId === canonicalId && snapshot.current && <p>Kiểm tra bản nháp rồi xác nhận để áp dụng cho đúng dòng và cột.</p>}
      {!snapshot.current && !jobId && snapshot.total > 0 && <p className="muted">Các dòng trong bản này chỉ có thể xem.</p>}
      {showRows && snapshot.items.map(row => {
        const issues = chatProjectId ? row.issues.filter((issue, index, all) =>
          issue.code !== "CURRENCY_MISMATCH" || all.findIndex(other => other.code === issue.code && other.raw_value === issue.raw_value) === index) : row.issues;
        const singleIssue = issues.length === 1 ? issues[0] : undefined;
        return <section className="quality-row" key={row.source_row_id}>
          <h5>Dòng nguồn {row.source_row} — {singleIssue
            ? qualityText[singleIssue.code] || "Giá trị cần kiểm tra"
            : `${issues.length} lỗi`}</h5>
          {row.pending_reason && <p className="quality-pending"><strong>Đã ghi nhận quyết định — Vẫn cần kiểm tra.</strong> {row.pending_reason}</p>}
          {chatProjectId && <button type="button" className="text-button" disabled={busy} hidden={selection?.row === row}
            ref={button => {if (button) rowButtons.current.set(row.source_row_id, button); else rowButtons.current.delete(row.source_row_id);}}
            aria-label={singleIssue && snapshot.current ? `Xử lý lỗi ${singleIssue.target_label} · dòng ${row.source_row}` : undefined}
            onClick={event => {
              triggerRef.current = event.currentTarget;
              focusDecision.current = snapshot.current;
              setSelection({ row, issue: issues[0] }); setAction(""); setReason(""); setValue("");
            }}>{snapshot.current ? "Xử lý dòng" : "Xem dòng"}</button>}
          {(!chatProjectId || selection?.row === row) && issues.map(issue => {
            const open = snapshot.current && selection?.row === row && selection.issue === issue;
            const original = (issue.original_value === undefined ? issue.raw_value : issue.original_value) ?? "Ô trống";
            return <div className="quality-issue" key={`${issue.field}:${issue.code}`}>
              {!singleIssue && <p><strong>{qualityText[issue.code] || "Giá trị chưa đáp ứng quy tắc đã xác nhận"}.</strong></p>}
              <p className="quality-value"><span>{issue.source_label ?? "Nhiều cột nguồn"}</span><span>Giá trị gốc <code>{original}</code></span></p>
              {(!chatProjectId || !issue.source_label) && issue.source_label !== issue.target_label && <p className="muted">Trường đích {issue.target_label}</p>}
              {issue.code === "CURRENCY_MISMATCH" && <p>Giao dịch {original} nằm ngoài phạm vi tiền tệ đã duyệt.</p>}
              {!chatProjectId && <p>Bản ghi chưa dùng được trong đối soát.</p>}
              {chatProjectId && <button type="button" className="text-button" onClick={event => {
                rawTrigger.current = event.currentTarget;
                setRaw({ row: row.source_row });
              }}>Xem dòng gốc</button>}
              {snapshot.current && <button type="button" className="button secondary quality-action" disabled={busy} hidden={open} aria-expanded={open}
                aria-label={`Xử lý lỗi ${issue.target_label} · dòng ${row.source_row}`}
                onClick={event => {
                  triggerRef.current = event.currentTarget;
                  focusDecision.current = true;
                  setSelection({ row, issue }); setAction(chatProjectId ? "" : issue.editable ? "REPLACE" : "KEEP_PENDING");
                  setReason(""); setValue(""); setError("");
                }}>
                Xử lý lỗi
              </button>}
              {open && <form className="quality-form" onSubmit={submit} onKeyDown={event => {
                if (event.key === "Escape" && !event.defaultPrevented && !busy) {
                  event.stopPropagation();
                  closeSelection();
                }
              }}>
                <label>Quyết định<select ref={decisionRef} value={action} disabled={busy} onChange={event => setAction(event.target.value as Action | "")}>
                  {chatProjectId && <option value="">Chọn cách xử lý</option>}
                  {Object.entries(actions).filter(([key]) => issue.editable || key !== "REPLACE").map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                </select></label>
                {action === "REPLACE" && <label>Giá trị đã kiểm tra<input required maxLength={2048} value={value} onChange={event => setValue(event.target.value)} disabled={busy}/></label>}
                {action === "EXCLUDE" && <p>Dòng này nằm ngoài bản chuẩn hóa mới. Bạn sẽ xác nhận phạm vi đối soát trước khi chạy.</p>}
                {action && <label>Lý do<input required maxLength={500} value={reason} onChange={event => setReason(event.target.value)} disabled={busy}/></label>}
                {action && missingInput && <p id={section} className="muted">
                  {action === "REPLACE" ? "Nhập giá trị đã kiểm tra và lý do để xác nhận." : "Nhập lý do để xác nhận quyết định."}
                </p>}
                <div className="agent-pagination">
                  {action && <button type="submit" className="button primary" disabled={busy || missingInput} aria-describedby={missingInput ? section : undefined}>
                    {confirmAction[action]}
                  </button>}
                  <button type="button" className="button secondary" disabled={busy} onClick={closeSelection}>Hủy</button>
                </div>
              </form>}
            </div>;
          })}
        </section>;
      })}
      {showRows && snapshot.total > pageSize && <div className="agent-pagination">
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
    <Modal title={raw ? `Dòng nguồn ${raw.row}` : "Dữ liệu gốc"} open={!!raw} onOpenChange={open => {if (!open) setRaw(undefined);}} returnFocus={rawTrigger}>
      {raw && <>
      {raw.error ? <p role="alert">{raw.error}</p> : raw.values ? <dl className="quality-source-values">
        {Object.entries(raw.values).map(([field, value]) => <div key={field}>
          <dt>{field}</dt><dd>{value == null || value === "" ? "Ô trống" : String(value)}</dd>
        </div>)}
        {!Object.keys(raw.values).length && <div><dt>Dữ liệu gốc</dt><dd>Chưa tìm thấy dòng.</dd></div>}
      </dl> : <p role="status">Đang đọc dòng gốc…</p>}
      </>}
    </Modal>
  </section>;
}
