import { useCallback, useEffect, useState } from "react";
import { ArrowRight, ShieldAlert, ShieldCheck } from "lucide-react";

import { getChain, getResults, type ReconChain, type ReconKind, type ReconResult, type ReconRun } from "../api";
import { formatCount } from "../format";
import { sealChecks, type SealRing } from "../verification";
import { ReconRunView, TodoGroups, formatDay, message, type ItemContext, type Rerun } from "./ReconRunView";
import { VerificationSeal } from "./VerificationSeal";

// Kết quả đối soát cả chuỗi của một kỳ (docs/DECISIONS.md 2026-11-23: một nút cho cả chuỗi).
// Mở ra là "Tất cả cần xử lý": ngoại lệ của mọi cặp gộp chung, mỗi ca ghi rõ cặp; từng cặp
// xem chi tiết ở tab riêng. Con dấu bên phải gộp kiểm chứng của mọi cặp: một vòng chỉ đạt khi
// phép kiểm đó đạt ở tất cả các cặp.

type Props = { chain: ReconChain; onChain: (chain: ReconChain) => void; onRerun: (target: Rerun) => void };

const shortLabel = (run: ReconRun) => `${run.left?.label ?? "?"} ↔ ${run.right?.label ?? "?"}`;
const pairName = (run: ReconRun | undefined) => (run ? shortLabel(run) : "?");

const TODO_PAGE = 200;

type TodoItem = { item: ReconResult; run: ReconRun };
// Ngoại lệ đã tải của cả chuỗi và tổng số ca đang mở của từng cặp (để biết còn ca chưa tải).
type Todo = { items: TodoItem[]; totals: Record<string, number> };

/** Tải một trang ngoại lệ của mọi cặp còn ca chưa tải (offset theo số ca đã tải của cặp). */
async function loadTodoPage(runs: ReconRun[], current: Todo | null, signal?: AbortSignal): Promise<Todo> {
  const loaded = (run: ReconRun) => current?.items.filter((entry) => entry.run.id === run.id).length ?? 0;
  const wanted = runs.filter((run) => !current || loaded(run) < (current.totals[run.id] ?? 0));
  const pages = await Promise.all(wanted.map((run) => getResults(run.id, "todo", loaded(run), TODO_PAGE, signal)));
  const items = [...(current?.items ?? [])];
  const totals = { ...(current?.totals ?? {}) };
  pages.forEach((page, index) => {
    const run = wanted[index];
    if (!run) return;
    totals[run.id] = page.total;
    items.push(...page.items.map((item) => ({ item, run })));
  });
  // Giữ thứ tự cặp trong chuỗi để các ca của cùng cặp đứng gần nhau trong mỗi nhóm.
  const order = new Map(runs.map((run, index) => [run.id, index]));
  items.sort((a, b) => (order.get(a.run.id) ?? 0) - (order.get(b.run.id) ?? 0));
  return { items, totals };
}

/** Gộp con dấu của nhiều cặp: hỏng nếu một cặp hỏng, chưa kiểm nếu một cặp chưa kiểm. */
function mergedRings(runs: ReconRun[]): SealRing[] {
  const perRun = runs.map((run) => sealChecks(run.status === "READY" ? run.verification : null));
  const first = perRun[0] ?? sealChecks(null);
  return first.map((ring, index) => {
    const states = perRun.map((rings) => rings[index]?.state ?? "pending");
    const failed = perRun.flatMap((rings, runIndex) =>
      rings[index]?.state === "failed" ? [`${pairName(runs[runIndex])}: ${rings[index]?.detail ?? ""}`] : [],
    );
    return {
      label: ring.label,
      state: failed.length ? "failed" : states.every((state) => state === "passed") ? "passed" : "pending",
      detail: failed.join("; "),
    };
  });
}

export function ChainView({ chain, onChain, onRerun }: Props) {
  const [tab, setTab] = useState<string>("all");
  const [todo, setTodo] = useState<Todo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ready = chain.status === "READY";

  // Tải trang đầu mỗi khi chuỗi đổi (sau mỗi thao tác, chuỗi được tải lại nên danh sách cũng
  // tải lại từ đầu, không cần tải riêng).
  useEffect(() => {
    if (!ready || tab !== "all") return;
    const controller = new AbortController();
    loadTodoPage(chain.runs, null, controller.signal)
      .then(setTodo)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(message(reason, "Không tải được ngoại lệ."));
      });
    return () => controller.abort();
  }, [ready, tab, chain.runs]);

  const loadMore = useCallback(() => {
    loadTodoPage(chain.runs, todo)
      .then(setTodo)
      .catch((reason: unknown) => setError(message(reason, "Không tải được ngoại lệ.")));
  }, [chain.runs, todo]);

  // Thao tác trên một ca: lưu, rồi tải lại chuỗi (số đếm và danh sách ngoại lệ tự cập nhật).
  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
      onChain(await getChain(chain.id));
      setError(null);
    } catch (reason) {
      setError(message(reason, "Không lưu được."));
    } finally {
      setBusy(false);
    }
  }

  const replaceRun = (run: ReconRun) => onChain({ ...chain, runs: chain.runs.map((item) => (item.id === run.id ? run : item)) });
  const selected = chain.runs.find((run) => run.id === tab);
  const kindLabels = chain.runs[0]?.kind_labels;
  const rings = mergedRings(chain.runs);
  // Số ca đang mở theo loại, cộng mọi cặp (backend đếm, đúng cả khi danh sách mới tải một phần).
  const openByKind: Partial<Record<ReconKind, number>> = {};
  for (const run of chain.runs) {
    for (const [kind, count] of Object.entries(run.open_by_kind) as [ReconKind, number][]) {
      openByKind[kind] = (openByKind[kind] ?? 0) + count;
    }
  }
  const hidden = todo ? Object.values(todo.totals).reduce((sum, value) => sum + value, 0) - todo.items.length : 0;

  return (
    <div className="chain">
      <section className="next-step chain__band" aria-live="polite">
        {chain.status === "RUNNING" ? (
          <div>
            <h2>Đang đối soát cả chuỗi…</h2>
            <p>Hệ thống đang ghép từng cặp bảng và kiểm chứng kết quả.</p>
          </div>
        ) : chain.status === "FAILED" ? (
          <div>
            <h2>Chuỗi đối soát không chạy xong</h2>
            <p>{chain.error_message ?? "Có lỗi khi đối soát. Hãy chạy lại."}</p>
          </div>
        ) : (
          <div>
            <h2>
              {chain.exceptions.OPEN > 0 ? `Cần bạn xem ${formatCount(chain.exceptions.OPEN)} ca` : "Không còn ca nào cần xem"}
            </h2>
            <p>
              {chain.runs.length} cặp
              {chain.period_start && ` · kỳ ${formatDay(chain.period_start)} – ${formatDay(chain.period_end)}`}
              {chain.pending > 0 && ` · ${formatCount(chain.pending)} khoản chờ tiền về kỳ sau`}
            </p>
          </div>
        )}
      </section>

      {ready && (
        <ol className="chain__pairs" aria-label="Các cặp trong chuỗi">
          {chain.runs.map((run) => (
            <li key={run.id}>
              <button type="button" className="chain__pair" aria-pressed={tab === run.id} onClick={() => setTab(run.id)}>
                <span className="chain__pair-name">
                  {run.left?.label} <ArrowRight aria-hidden="true" size={14} /> {run.right?.label}
                </span>
                <span className="chain__pair-stats">
                  <span data-tone="matched">{formatCount(run.group_counts.matched)} khớp</span>
                  <span data-tone={run.exceptions.OPEN ? "attention" : "calm"}>{formatCount(run.exceptions.OPEN)} cần xem</span>
                  {run.group_counts.pending > 0 && (
                    <span data-tone="pending">{formatCount(run.group_counts.pending)} chờ tiền về</span>
                  )}
                  {run.carried_count > 0 && <span>{formatCount(run.carried_count)} từ kỳ trước</span>}
                </span>
                {run.verification?.passed ? (
                  <ShieldCheck className="chain__seal" data-state="passed" aria-label="Đã kiểm chứng" size={18} />
                ) : (
                  <ShieldAlert className="chain__seal" data-state="failed" aria-label="Kiểm chứng chưa đạt" size={18} />
                )}
              </button>
            </li>
          ))}
        </ol>
      )}

      {error && <p className="notice notice--error" role="alert">{error}</p>}

      {ready && (
        <div className="segmented chain__tabs" role="group" aria-label="Xem theo">
          <button type="button" aria-pressed={tab === "all"} onClick={() => setTab("all")}>
            Tất cả cần xử lý
            <span className={chain.exceptions.OPEN > 0 ? "segmented__count" : "recon-run__count"}>
              {formatCount(chain.exceptions.OPEN)}
            </span>
          </button>
          {chain.runs.map((run) => (
            <button key={run.id} type="button" aria-pressed={tab === run.id} onClick={() => setTab(run.id)}>
              {run.left?.label} ↔ {run.right?.label}
            </button>
          ))}
        </div>
      )}

      {ready && tab === "all" && (
        <div className="recon-run">
          <div className="recon-run__main">
            {todo === null || !kindLabels ? (
              <p className="notice">Đang tải ngoại lệ…</p>
            ) : (
              <TodoGroups
                kindLabels={kindLabels}
                counts={openByKind}
                more={hidden > 0 ? { count: hidden, load: loadMore } : undefined}
                items={todo.items.map(({ item, run }) => {
                  const context: ItemContext = { run, busy, act, onRerun, chainId: chain.id, pairLabel: shortLabel(run) };
                  return { item, context };
                })}
              />
            )}
          </div>
          <aside className="verification recon-run__seal" aria-labelledby="chain-seal-title">
            <h2 id="chain-seal-title">Kiểm chứng cả chuỗi</h2>
            <VerificationSeal checks={rings} />
            <p className="verification__lead">
              {chain.verified
                ? `Cả ${chain.runs.length} cặp đều đạt bốn phép kiểm độc lập.`
                : "Có cặp chưa đạt kiểm chứng; xem chi tiết ở từng cặp."}
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
          </aside>
        </div>
      )}

      {ready && selected && (
        <ReconRunView key={selected.id} run={selected} onRun={replaceRun} onRerun={onRerun} chainId={chain.id} />
      )}
    </div>
  );
}
