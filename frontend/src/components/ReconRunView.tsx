import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeftRight,
  Check,
  History,
  MessageSquareText,
  Route,
  RotateCcw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import {
  actOnResults,
  chooseCandidate,
  explainResult,
  getResults,
  getRun,
  saveNote,
  traceRow,
  verifyRun,
  type ReconKind,
  type ReconResult,
  type ReconRun,
  type ResultGroup,
  type ResultRow,
  type TraceStep,
} from "../api";
import { formatCount, formatMoney } from "../format";
import { sealChecks } from "../verification";
import { VerificationSeal } from "./VerificationSeal";

// Kết quả một lần đối soát. Mở ra là việc cần làm (ngoại lệ đang mở, gom theo loại, mỗi nhóm
// một nút chính); khớp, chờ tiền về, ngoài phạm vi, đã xử lý nằm ở các tab thu gọn. Cột phải là
// con dấu kiểm chứng: bốn vòng ứng với bốn nhóm phép kiểm độc lập của backend.

/** Sau khi chọn ứng viên cho ca mơ hồ, hệ thống chạy lại: trả về lần chạy hoặc chuỗi mới. */
export type Rerun = { chain_id: string | null; run_id: string | null };

type Props = {
  run: ReconRun;
  onRun: (run: ReconRun) => void;
  onRerun?: (target: Rerun) => void;
  chainId?: string;
};

const GROUPS: { key: ResultGroup; label: string }[] = [
  { key: "todo", label: "Cần xử lý" },
  { key: "pending", label: "Chờ tiền về" },
  { key: "explained", label: "Đã ghi chú" },
  { key: "resolved", label: "Đã xử lý" },
  { key: "matched", label: "Khớp" },
  { key: "out_of_scope", label: "Ngoài phạm vi" },
];

// Thứ tự nhóm ngoại lệ (cần quyết định trước) và giải thích bằng lời thường.
export const KIND_HELP: [ReconKind, string][] = [
  ["AMBIGUOUS", "Có nhiều ứng viên ngang nhau; hệ thống không tự chọn. Hãy chọn cặp đúng."],
  ["AMOUNT_MISMATCH", "Ghép được nhưng số tiền hai bên khác nhau."],
  ["DUPLICATE", "Một mã xuất hiện nhiều lần; dòng thừa có thể là thu tiền hai lần."],
  ["ONLY_IN_A", "Có ở bên A nhưng không thấy ở bên B, ví dụ đơn chưa có tiền về và đã quá hạn chờ."],
  ["ONLY_IN_B", "Có ở bên B nhưng không có ở bên A, ví dụ tiền về không rõ của đơn nào."],
  ["NEEDS_CLEANING", "Dòng còn lỗi ở bước làm sạch; sửa xong rồi chạy lại."],
  ["MATCHED", "Đã ghép được nhưng cần xem lại, ví dụ đơn đã hủy vẫn có tiền về."],
  ["MANY_TO_ONE", "Đã ghép nhóm nhưng cần xem lại."],
  ["ONE_TO_MANY", "Đã ghép nhóm nhưng cần xem lại."],
];
const PAGE = 50;
const MATCHED_KINDS: ReconKind[] = ["MATCHED", "MANY_TO_ONE", "ONE_TO_MANY"];
const ATTENTION_KINDS: ReconKind[] = ["AMBIGUOUS", "AMOUNT_MISMATCH", "DUPLICATE", "ONLY_IN_A", "ONLY_IN_B", "NEEDS_CLEANING"];

export const message = (reason: unknown, fallback: string) => (reason instanceof Error ? reason.message : fallback);

export function formatDay(iso: string | null): string {
  if (!iso) return "";
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${day}/${month}/${year}`;
}

// Khóa ghép có thể là một ngày (ví dụ sàn TMĐT trả tiền theo đợt, ghép theo ngày trong nội dung
// chuyển khoản); khi đó hiện theo kiểu ngày Việt Nam thay vì dạng ISO.
function keyText(key: string | null | undefined): string | null {
  if (!key) return null;
  return /^\d{4}-\d{2}-\d{2}(T|$)/.test(key) ? `Đợt ${formatDay(key)}` : key;
}

export function ReconRunView({ run, onRun, onRerun, chainId }: Props) {
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
  const rowsOf = (kinds: ReconKind[]) =>
    kinds.reduce((sum, kind) => sum + (rows?.[kind] ? rows[kind].A + rows[kind].B : 0), 0);
  const groupCount = run.group_counts;
  const context: ItemContext = { run, busy, act, onRerun, chainId };

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
                {run.carried_count > 0 && ` · nhận ${formatCount(run.carried_count)} dòng chờ từ kỳ trước`}
              </p>
            </div>
          )}
        </section>

        {ready && rows && (
          <Composition
            parts={[
              { label: "Khớp", value: rowsOf(MATCHED_KINDS), tone: "matched" },
              { label: "Cần xem", value: rowsOf(ATTENTION_KINDS), tone: "attention" },
              { label: "Chờ tiền về", value: rowsOf(["PENDING_SETTLEMENT"]), tone: "pending" },
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
                    {formatCount(groupCount[item.key] ?? 0)}
                  </span>
                </button>
              ))}
            </div>

            {items === null ? (
              <p className="notice">Đang tải kết quả…</p>
            ) : group === "todo" ? (
              <TodoGroups
                items={items.map((item) => ({ item, context }))}
                kindLabels={run.kind_labels}
                counts={run.open_by_kind}
                more={items.length < total ? { count: total - items.length, load: () => void load(items.length) } : undefined}
              />
            ) : items.length === 0 ? (
              <p className="notice">Không có kết quả trong nhóm này.</p>
            ) : (
              <>
                <ul className="results">
                  {items.map((item) => (
                    <ResultItem key={item.id} item={item} context={context} />
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

type Part = { label: string; value: number; tone: "matched" | "attention" | "pending" | "scope" };

/** Thanh tỷ lệ: độ dài mỗi đoạn theo số dòng (hai bên cộng lại) của từng nhóm. */
export function Composition({ parts }: { parts: Part[] }) {
  const sum = parts.reduce((total, part) => total + part.value, 0) || 1;
  const shown = parts.filter((part) => part.value > 0 || part.tone !== "pending");
  return (
    <figure className="composition" aria-label="Tỷ lệ dòng theo nhóm kết quả">
      <div className="composition__bar">
        {shown.map((part) =>
          part.value > 0 ? (
            <span key={part.label} data-tone={part.tone} style={{ flexGrow: part.value }} title={`${part.label}: ${formatCount(part.value)} dòng`} />
          ) : null,
        )}
      </div>
      <figcaption className="composition__legend">
        {shown.map((part) => (
          <span key={part.label} data-tone={part.tone}>
            <b>{formatCount(part.value)}</b> dòng {part.label.toLowerCase()} ({Math.round((part.value / sum) * 100)}%)
          </span>
        ))}
        <span className="composition__unit">tính cả hai bên</span>
      </figcaption>
    </figure>
  );
}

/** Những gì một ca cần để thao tác: lần chạy chứa nó, trạng thái bận, hàm thực hiện. */
export type ItemContext = {
  run: ReconRun;
  busy: boolean;
  act: (action: () => Promise<unknown>) => Promise<void>;
  onRerun?: (target: Rerun) => void;
  chainId?: string;
  pairLabel?: string; // hiện nhãn cặp khi gộp ngoại lệ của cả chuỗi
};

/** Ngoại lệ đang mở gom theo loại; mỗi nhóm có một nút chính "Đánh dấu cả nhóm đã xử lý"
 *  (chỉ khi mọi ca của nhóm cùng một lần chạy, để thao tác gộp đúng phạm vi). */
/**
 * Danh sách cần xử lý, gom theo loại ngoại lệ. `counts` là số ca đang mở của từng loại do
 * backend đếm (đúng cả khi danh sách mới tải một phần); `more` hiện nút tải thêm khi còn ca
 * chưa tải, để không ca nào bị giấu.
 */
export function TodoGroups({
  items,
  kindLabels,
  counts,
  more,
}: {
  items: { item: ReconResult; context: ItemContext }[];
  kindLabels: Record<ReconKind, string>;
  counts: Partial<Record<ReconKind, number>>;
  more?: { count: number; load: () => void };
}) {
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
        const group = items.filter(({ item }) => item.kind === kind);
        if (group.length === 0) return null;
        const runs = new Set(group.map(({ context }) => context.run.id));
        const first = group[0]?.context;
        return (
          <section key={kind} className="recon-group" aria-labelledby={`group-${kind}`}>
            <div className="recon-group__head">
              <div>
                <h3 id={`group-${kind}`}>
                  {kindLabels[kind] ?? kind}{" "}
                  <span className="recon-group__count">{formatCount(Math.max(counts[kind] ?? 0, group.length))}</span>
                </h3>
                <p>{help}</p>
              </div>
              {group.length > 1 && runs.size === 1 && first && kind !== "AMBIGUOUS" && (
                <button
                  className="button button--quiet"
                  type="button"
                  disabled={first.busy}
                  onClick={() => void first.act(() => actOnResults(first.run.id, { action: "RESOLVE", kind }))}
                >
                  <Check aria-hidden="true" size={16} />
                  Đánh dấu cả nhóm đã xử lý
                </button>
              )}
            </div>
            <ul className="results">
              {group.map(({ item, context }) => (
                <ResultItem key={item.id} item={item} context={context} />
              ))}
            </ul>
          </section>
        );
      })}
      {more && (
        <button className="button button--quiet recon-run__more" type="button" onClick={more.load}>
          Xem thêm ({formatCount(more.count)} ca)
        </button>
      )}
    </div>
  );
}

export function ResultItem({ item, context }: { item: ReconResult; context: ItemContext }) {
  const { run, busy, act, onRerun, chainId, pairLabel } = context;
  const [noting, setNoting] = useState(false);
  const [note, setNote] = useState(item.note ?? "");
  const [explanation, setExplanation] = useState<string | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);
  const [steps, setSteps] = useState<TraceStep[] | null>(null);
  const [choosing, setChoosing] = useState(false);
  const reasons = item.reasons.filter(
    (reason) => !["AMOUNT_EQUAL", "DATE", "KEY", "CANDIDATES"].includes(reason.code),
  );
  const shown = reasons.length ? reasons : item.reasons;
  const candidates = item.reasons.find((reason) => reason.code === "CANDIDATES")?.pairs ?? [];
  const firstLeft = item.left.find((row) => !row.carried);

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

  async function trace() {
    if (!chainId || !run.left || !firstLeft) return;
    try {
      setSteps((await traceRow(chainId, run.left.id, firstLeft.row_ref)).steps);
    } catch (reason) {
      setExplainError(message(reason, "Không lấy được đường đi."));
    }
  }

  async function choose(left: number[], right: number[]) {
    setChoosing(true);
    try {
      const target = await chooseCandidate(run.id, item.id, left, right);
      onRerun?.(target);
    } catch (reason) {
      setExplainError(message(reason, "Không lưu được lựa chọn."));
      setChoosing(false);
    }
  }

  const describe = (side: ResultRow[], refs: number[]) =>
    refs
      .map((ref) => {
        const row = side.find((entry) => entry.row_ref === ref);
        const name = row?.customer_name ? ` · ${row.customer_name}` : "";
        return `dòng ${ref}${name}`;
      })
      .join(", ");

  return (
    <li className="result" data-kind={item.kind}>
      {pairLabel && <span className="result__pair">{pairLabel}</span>}
      <div className="result__sides">
        <Side label="A" rows={item.left} kind={item.kind} />
        <ArrowLeftRight className="result__link" aria-hidden="true" size={16} strokeWidth={1.8} />
        <Side label="B" rows={item.right} kind={item.kind} />
      </div>
      <p className="result__reason">{shown.map((reason) => reason.text).join(" ")}</p>

      {item.kind === "AMBIGUOUS" && candidates.length > 0 && (
        <fieldset className="candidates" disabled={busy || choosing}>
          <legend>Chọn cặp đúng</legend>
          {candidates.map((pair) => (
            <div key={`${pair.left.join("-")}:${pair.right.join("-")}`} className="candidates__row">
              <span>
                A {describe(item.left, pair.left)} <span aria-hidden="true">↔</span> B {describe(item.right, pair.right)}
              </span>
              <button className="button button--quiet" type="button" onClick={() => void choose(pair.left, pair.right)}>
                <Check aria-hidden="true" size={15} /> Chọn
              </button>
            </div>
          ))}
          {choosing && <p className="candidates__busy">Đang lưu lựa chọn và đối soát lại…</p>}
        </fieldset>
      )}

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
      {steps && (
        <ol className="trace" aria-label="Đường đi của dòng qua các cặp">
          {steps.map((step) => (
            <li key={step.result_id}>
              <span className="trace__pair">{step.pair}</span>
              <span className="trace__kind" data-kind={step.kind}>{run.kind_labels[step.kind] ?? step.kind}</span>
              <span className="trace__refs">
                A {step.left_refs.join(", ") || "—"} ↔ B {step.right_refs.join(", ") || "—"}
              </span>
            </li>
          ))}
          {steps.length === 0 && <li>Dòng này chưa đi qua cặp nào khác.</li>}
        </ol>
      )}
      {explanation && <p className="ai-note">{explanation}</p>}
      {explainError && <p className="result__error">{explainError}</p>}
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
        ) : item.exception_status && item.kind !== "AMBIGUOUS" ? (
          <button
            className="button button--quiet"
            type="button"
            disabled={busy}
            onClick={() => void act(() => actOnResults(run.id, { action: "RESOLVE", result_ids: [item.id] }))}
          >
            <Check aria-hidden="true" size={15} /> Đã xử lý
          </button>
        ) : null}
        {item.exception_status && !noting && (
          <button className="button button--text" type="button" onClick={() => setNoting(true)}>
            {item.note ? "Sửa ghi chú" : "Ghi chú"}
          </button>
        )}
        {chainId && firstLeft && !steps && (
          <button className="button button--text" type="button" onClick={() => void trace()}>
            <Route aria-hidden="true" size={15} /> Đường đi
          </button>
        )}
        {item.exception_status && (
          <button className="button button--text" type="button" disabled={explaining} onClick={() => void explain()}>
            <Sparkles aria-hidden="true" size={15} /> {explaining ? "Đang giải thích…" : "Giải thích"}
          </button>
        )}
      </div>
    </li>
  );
}

// Bên không có dòng: nói rõ vì sao, tùy loại kết quả.
const EMPTY_SIDE: Partial<Record<ReconKind, string>> = {
  DUPLICATE: "Dòng tương ứng đã được ghép với một dòng khác cùng mã",
  NEEDS_CLEANING: "Chưa ghép vì dòng còn lỗi",
  OUT_OF_SCOPE: "Không cần ghép",
  PENDING_SETTLEMENT: "Chưa có tiền về, còn trong hạn chờ",
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
      <span className="side__tag">
        {label}
        {rows.length > 1 && ` · ${rows.length} dòng`}
      </span>
      {rows.map((row) => (
        <div key={`${row.carried ? "c" : ""}${row.row_ref}`} className="side__row">
          <span className="side__key">{keyText(row.key) ?? row.description ?? "Không có mã"}</span>
          <span className="side__amount">{row.amount ? `${formatMoney(row.amount)}đ` : "—"}</span>
          <span className="side__meta">
            {row.carried && (
              <span className="side__carried" title={row.table_label ?? undefined}>
                <History aria-hidden="true" size={12} /> Kỳ trước
              </span>
            )}
            Dòng {row.row_ref}
            {row.date && ` · ${formatDay(row.date)}`}
            {row.customer_name && ` · ${row.customer_name}`}
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
    <aside className="verification recon-run__seal" aria-labelledby={`seal-title-${run.id}`}>
      <h2 id={`seal-title-${run.id}`}>Kiểm chứng kết quả</h2>
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
