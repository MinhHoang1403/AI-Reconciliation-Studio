import { useCallback, useEffect, useState } from "react";
import { ArrowLeftRight, Check, MessageSquareText, RotateCcw, ShieldCheck, Sparkles } from "lucide-react";

import {
  actOnResults,
  explainResult,
  getResults,
  getRun,
  saveNote,
  verifyRun,
  type ReconKind,
  type ReconResult,
  type ReconRun,
  type ResultGroup,
  type ResultRow,
} from "../api";
import { formatCount, formatMoney } from "../format";
import { sealChecks } from "../verification";
import { VerificationSeal } from "./VerificationSeal";

// Kết quả một lần đối soát. Mở ra là việc cần làm (ngoại lệ đang mở, gom theo loại, mỗi nhóm
// một nút chính); khớp, ngoài phạm vi, đã xử lý nằm ở các tab thu gọn. Cột phải là con dấu
// kiểm chứng: bốn vòng ứng với bốn nhóm phép kiểm độc lập của backend.

type Props = { run: ReconRun; onRun: (run: ReconRun) => void };

const GROUPS: { key: ResultGroup; label: string }[] = [
  { key: "todo", label: "Cần xử lý" },
  { key: "explained", label: "Đã ghi chú" },
  { key: "resolved", label: "Đã xử lý" },
  { key: "matched", label: "Khớp" },
  { key: "out_of_scope", label: "Ngoài phạm vi" },
];

// Thứ tự nhóm ngoại lệ (nặng trước) và giải thích bằng lời thường.
const KIND_HELP: [ReconKind, string][] = [
  ["AMOUNT_MISMATCH", "Cùng mã nhưng số tiền hai bên khác nhau."],
  ["DUPLICATE", "Một mã xuất hiện nhiều lần; dòng thừa có thể là thu tiền hai lần."],
  ["ONLY_IN_A", "Có ở bên A nhưng không thấy ở bên B, ví dụ đơn chưa có tiền về."],
  ["ONLY_IN_B", "Có ở bên B nhưng không có ở bên A, ví dụ tiền về không rõ của đơn nào."],
  ["NEEDS_CLEANING", "Dòng còn lỗi ở bước làm sạch; sửa xong rồi chạy lại."],
  ["MATCHED", "Đã ghép được nhưng cần xem lại, ví dụ đơn đã hủy vẫn có tiền về."],
];
const PAGE = 50;

const message = (reason: unknown, fallback: string) => (reason instanceof Error ? reason.message : fallback);

function formatDay(iso: string | null): string {
  if (!iso) return "";
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${day}/${month}/${year}`;
}

export function ReconRunView({ run, onRun }: Props) {
  const [group, setGroup] = useState<ResultGroup>("todo");
  const [items, setItems] = useState<ReconResult[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ready = run.status === "READY";

  const load = useCallback(
    async (offset: number) => {
      const page = await getResults(run.id, group, offset, group === "todo" ? 200 : PAGE);
      setTotal(page.total);
      setItems((current) => (offset === 0 ? page.items : [...(current ?? []), ...page.items]));
    },
    [run.id, group],
  );

  useEffect(() => {
    if (!ready) return;
    const controller = new AbortController();
    getResults(run.id, group, 0, group === "todo" ? 200 : PAGE, controller.signal)
      .then((page) => {
        setTotal(page.total);
        setItems(page.items);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(message(reason, "Không tải được kết quả."));
      });
    return () => controller.abort();
  }, [ready, run.id, group]);

  // Sau mỗi thao tác: cập nhật số đếm của lần chạy và tải lại nhóm đang xem.
  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
      onRun(await getRun(run.id));
      await load(0);
      setError(null);
    } catch (reason) {
      setError(message(reason, "Không lưu được."));
    } finally {
      setBusy(false);
    }
  }

  const rows = run.summary?.rows;
  const rowsOf = (kinds: ReconKind[]) => kinds.reduce((sum, kind) => sum + (rows ? rows[kind].A + rows[kind].B : 0), 0);
  const groupCount = run.group_counts;

  return (
    <div className="recon-run">
      <div className="recon-run__main">
        <section className="next-step recon-run__band" aria-live="polite">
          {run.status === "RUNNING" ? (
            <div>
              <h2>Đang đối soát…</h2>
              <p>Hệ thống đang ghép từng dòng và kiểm chứng kết quả.</p>
            </div>
          ) : run.status === "FAILED" ? (
            <div>
              <h2>Lần đối soát không chạy xong</h2>
              <p>{run.error_message ?? "Có lỗi khi đối soát. Hãy chạy lại."}</p>
            </div>
          ) : (
            <div>
              <h2>
                {run.exceptions.OPEN > 0 ? `Cần bạn xem ${formatCount(run.exceptions.OPEN)} ca` : "Không còn ca nào cần xem"}
              </h2>
              <p>
                {run.left?.label} ↔ {run.right?.label}
                {run.period_start && ` · kỳ ${formatDay(run.period_start)} – ${formatDay(run.period_end)}`}
              </p>
            </div>
          )}
        </section>

        {ready && rows && (
          <Composition
            parts={[
              { label: "Khớp", value: rowsOf(["MATCHED"]), tone: "matched" },
              {
                label: "Cần xem",
                value: rowsOf(["AMOUNT_MISMATCH", "DUPLICATE", "ONLY_IN_A", "ONLY_IN_B", "NEEDS_CLEANING"]),
                tone: "attention",
              },
              { label: "Ngoài phạm vi", value: rowsOf(["OUT_OF_SCOPE"]), tone: "scope" },
            ]}
          />
        )}

        {error && <p className="notice notice--error" role="alert">{error}</p>}

        {ready && (
          <>
            <div className="segmented recon-run__tabs" role="group" aria-label="Nhóm kết quả">
              {GROUPS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  aria-pressed={group === item.key}
                  onClick={() => {
                    if (item.key === group) return;
                    setItems(null);
                    setGroup(item.key);
                  }}
                >
                  {item.label}
                  <span className={item.key === "todo" && groupCount.todo > 0 ? "segmented__count" : "recon-run__count"}>
                    {formatCount(groupCount[item.key])}
                  </span>
                </button>
              ))}
            </div>

            {items === null ? (
              <p className="notice">Đang tải kết quả…</p>
            ) : group === "todo" ? (
              <TodoGroups items={items} run={run} busy={busy} act={act} />
            ) : items.length === 0 ? (
              <p className="notice">Không có kết quả trong nhóm này.</p>
            ) : (
              <>
                <ul className="results">
                  {items.map((item) => (
                    <ResultItem key={item.id} item={item} run={run} busy={busy} act={act} />
                  ))}
                </ul>
                {items.length < total && (
                  <button className="button button--quiet recon-run__more" type="button" onClick={() => void load(items.length)}>
                    Xem thêm ({formatCount(total - items.length)} kết quả)
                  </button>
                )}
              </>
            )}
          </>
        )}
      </div>

      <SealPanel run={run} busy={busy} onVerify={() => void act(() => verifyRun(run.id))} />
    </div>
  );
}

type Part = { label: string; value: number; tone: "matched" | "attention" | "scope" };

/** Thanh tỷ lệ: độ dài mỗi đoạn theo số dòng (hai bên cộng lại) của từng nhóm. */
function Composition({ parts }: { parts: Part[] }) {
  const sum = parts.reduce((total, part) => total + part.value, 0) || 1;
  return (
    <figure className="composition" aria-label="Tỷ lệ dòng theo nhóm kết quả">
      <div className="composition__bar">
        {parts.map((part) =>
          part.value > 0 ? (
            <span key={part.label} data-tone={part.tone} style={{ flexGrow: part.value }} title={`${part.label}: ${formatCount(part.value)} dòng`} />
          ) : null,
        )}
      </div>
      <figcaption className="composition__legend">
        {parts.map((part) => (
          <span key={part.label} data-tone={part.tone}>
            <b>{formatCount(part.value)}</b> dòng {part.label.toLowerCase()} ({Math.round((part.value / sum) * 100)}%)
          </span>
        ))}
        <span className="composition__unit">tính cả hai bên</span>
      </figcaption>
    </figure>
  );
}

type ActProps = { run: ReconRun; busy: boolean; act: (action: () => Promise<unknown>) => Promise<void> };

function TodoGroups({ items, run, busy, act }: ActProps & { items: ReconResult[] }) {
  if (items.length === 0) {
    return (
      <section className="cleaning__done">
        <Check aria-hidden="true" size={20} />
        <div>
          <h3>Đã xử lý hết ngoại lệ</h3>
          <p>Các ca đã ghi chú hoặc đã xử lý vẫn xem lại được ở các tab bên cạnh.</p>
        </div>
      </section>
    );
  }
  return (
    <div className="recon-groups">
      {KIND_HELP.map(([kind, help]) => {
        const group = items.filter((item) => item.kind === kind);
        if (group.length === 0) return null;
        return (
          <section key={kind} className="recon-group" aria-labelledby={`group-${kind}`}>
            <div className="recon-group__head">
              <div>
                <h3 id={`group-${kind}`}>
                  {run.kind_labels[kind]} <span className="recon-group__count">{formatCount(group.length)}</span>
                </h3>
                <p>{help}</p>
              </div>
              {group.length > 1 && (
                <button
                  className="button button--quiet"
                  type="button"
                  disabled={busy}
                  onClick={() => void act(() => actOnResults(run.id, { action: "RESOLVE", kind }))}
                >
                  <Check aria-hidden="true" size={16} />
                  Đánh dấu cả nhóm đã xử lý
                </button>
              )}
            </div>
            <ul className="results">
              {group.map((item) => (
                <ResultItem key={item.id} item={item} run={run} busy={busy} act={act} />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function ResultItem({ item, run, busy, act }: ActProps & { item: ReconResult }) {
  const [noting, setNoting] = useState(false);
  const [note, setNote] = useState(item.note ?? "");
  const [explanation, setExplanation] = useState<string | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);
  const reasons = item.reasons.filter((reason) => !["AMOUNT_EQUAL", "DATE", "KEY"].includes(reason.code));
  const shown = reasons.length ? reasons : item.reasons;

  async function explain() {
    setExplaining(true);
    try {
      setExplanation((await explainResult(item.id)).text);
      setExplainError(null);
    } catch (reason) {
      setExplainError(message(reason, "Gemini chưa trả lời được."));
    } finally {
      setExplaining(false);
    }
  }

  return (
    <li className="result" data-kind={item.kind}>
      <div className="result__sides">
        <Side label="A" rows={item.left} kind={item.kind} />
        <ArrowLeftRight className="result__link" aria-hidden="true" size={16} strokeWidth={1.8} />
        <Side label="B" rows={item.right} kind={item.kind} />
      </div>
      <p className="result__reason">{shown.map((reason) => reason.text).join(" ")}</p>
      {item.note && !noting && (
        <p className="result__note">
          <MessageSquareText aria-hidden="true" size={15} /> {item.note}
        </p>
      )}
      {noting && (
        <form
          className="result__note-form"
          onSubmit={(event) => {
            event.preventDefault();
            void act(() => saveNote(item.id, note)).then(() => setNoting(false));
          }}
        >
          <label className="visually-hidden" htmlFor={`note-${item.id}`}>Ghi chú</label>
          <input
            id={`note-${item.id}`}
            value={note}
            maxLength={1000}
            placeholder="Ví dụ: khách được giảm giá tại quầy"
            onChange={(event) => setNote(event.target.value)}
            autoFocus
          />
          <button className="button button--quiet" type="submit" disabled={busy}>Lưu</button>
          <button className="button button--quiet" type="button" onClick={() => setNoting(false)}>Hủy</button>
        </form>
      )}
      {explanation && <p className="ai-note">{explanation}</p>}
      {explainError && <p className="result__error">{explainError}</p>}
      {item.exception_status && (
        <div className="result__actions">
          {item.exception_status === "RESOLVED" ? (
            <button
              className="button button--quiet"
              type="button"
              disabled={busy}
              onClick={() => void act(() => actOnResults(run.id, { action: "REOPEN", result_ids: [item.id] }))}
            >
              <RotateCcw aria-hidden="true" size={15} /> Mở lại
            </button>
          ) : (
            <button
              className="button button--quiet"
              type="button"
              disabled={busy}
              onClick={() => void act(() => actOnResults(run.id, { action: "RESOLVE", result_ids: [item.id] }))}
            >
              <Check aria-hidden="true" size={15} /> Đã xử lý
            </button>
          )}
          {!noting && (
            <button className="button button--text" type="button" onClick={() => setNoting(true)}>
              {item.note ? "Sửa ghi chú" : "Ghi chú"}
            </button>
          )}
          <button className="button button--text" type="button" disabled={explaining} onClick={() => void explain()}>
            <Sparkles aria-hidden="true" size={15} /> {explaining ? "Đang giải thích…" : "Giải thích"}
          </button>
        </div>
      )}
    </li>
  );
}

// Bên không có dòng: nói rõ vì sao, tùy loại kết quả.
const EMPTY_SIDE: Partial<Record<ReconKind, string>> = {
  DUPLICATE: "Dòng tương ứng đã được ghép với một dòng khác cùng mã",
  NEEDS_CLEANING: "Chưa ghép vì dòng còn lỗi",
  OUT_OF_SCOPE: "Không cần ghép",
};

function Side({ label, rows, kind }: { label: string; rows: ResultRow[]; kind: ReconKind }) {
  if (rows.length === 0) {
    return (
      <div className="side side--empty" data-kind={kind}>
        <span className="side__tag">{label}</span>
        <span>{EMPTY_SIDE[kind] ?? "Không có dòng tương ứng"}</span>
      </div>
    );
  }
  return (
    <div className="side">
      <span className="side__tag">{label}</span>
      {rows.map((row) => (
        <div key={row.row_ref} className="side__row">
          <span className="side__key">{row.key ?? "Không có mã"}</span>
          <span className="side__amount">{row.amount ? `${formatMoney(row.amount)}đ` : "—"}</span>
          <span className="side__meta">
            Dòng {row.row_ref}
            {row.date && ` · ${formatDay(row.date)}`}
            {row.payment_method && ` · ${row.payment_method}`}
          </span>
        </div>
      ))}
    </div>
  );
}

function SealPanel({ run, busy, onVerify }: { run: ReconRun; busy: boolean; onVerify: () => void }) {
  const rings = sealChecks(run.status === "READY" ? run.verification : null);
  const passed = run.verification?.passed;
  return (
    <aside className="verification recon-run__seal" aria-labelledby="seal-title">
      <h2 id="seal-title">Kiểm chứng kết quả</h2>
      <VerificationSeal checks={rings} />
      <p className="verification__lead">
        {run.status !== "READY"
          ? "Con dấu được in sau khi đối soát xong."
          : passed
            ? "Đạt cả bốn phép kiểm độc lập. Kết quả dùng được cho báo cáo."
            : "Có phép kiểm không đạt. Kết quả không được dùng cho báo cáo."}
      </p>
      <ul className="verification__checks">
        {rings.map((ring) => (
          <li key={ring.label} data-state={ring.state}>
            <span>
              {ring.label}
              {ring.detail && <small className="verification__detail">{ring.detail}</small>}
            </span>
          </li>
        ))}
      </ul>
      {run.status === "READY" && (
        <button className="button button--quiet" type="button" disabled={busy} onClick={onVerify}>
          <ShieldCheck aria-hidden="true" size={16} /> Kiểm chứng lại
        </button>
      )}
    </aside>
  );
}
