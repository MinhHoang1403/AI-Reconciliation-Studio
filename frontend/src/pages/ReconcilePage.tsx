import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, Layers, Play, Sparkles } from "lucide-react";

import {
  explainPreview,
  getChain,
  getPeriods,
  getReconTables,
  getRun,
  listRuns,
  previewRecon,
  startChain,
  startRun,
  type ReconChain,
  type ReconConfig,
  type ReconPeriod,
  type ReconRun,
  type ReconTable,
  type ScopeOption,
} from "../api";
import { ChainView } from "../components/ChainView";
import { ReconRunView, type Rerun } from "../components/ReconRunView";
import { formatCount } from "../format";
import { linkTo } from "../navigation";

// Trang Đối soát. Có tệp sao kê thì mở ra là "Đối soát theo kỳ": hệ thống tự nhận các kỳ (mỗi
// tệp sao kê một kỳ) và các bảng thuộc kỳ, một nút chạy cả chuỗi đơn hàng ↔ cổng ↔ sao kê
// (docs/DECISIONS.md 2026-11-23). Đối soát hai bảng tự chọn (Giai đoạn 4) nằm trong mục thu gọn.

type Pair = { left: string; right: string };

const message = (reason: unknown, fallback: string) => (reason instanceof Error ? reason.message : fallback);

export function ReconcilePage() {
  const [tables, setTables] = useState<ReconTable[] | null>(null);
  const [runs, setRuns] = useState<ReconRun[]>([]);
  const [pair, setPair] = useState<Pair | null>(null);
  const [periods, setPeriods] = useState<ReconPeriod[] | null>(null);
  const [periodIndex, setPeriodIndex] = useState(0);
  const [chain, setChain] = useState<ReconChain | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Lần đầu: bảng đã sạch, các kỳ, lần đối soát gần nhất. Kỳ được chọn sẵn là kỳ sớm nhất chưa
  // đối soát (để dòng chờ tiền về được mang sang đúng thứ tự), nếu đã hết thì kỳ mới nhất.
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([getReconTables(controller.signal), listRuns(20, controller.signal, true), getPeriods(controller.signal)])
      .then(([data, recent, found]) => {
        setTables(data.tables);
        setRuns(recent);
        setPeriods(found);
        const waiting = found.findIndex((period) => !period.chain_id);
        setPeriodIndex(waiting >= 0 ? waiting : Math.max(found.length - 1, 0));
        const last = recent.find((run) => run.left && run.right && !run.chain_id);
        if (last?.left && last.right) setPair({ left: last.left.id, right: last.right.id });
        else if (data.suggested) setPair({ left: data.suggested.left_table_id, right: data.suggested.right_table_id });
        else {
          const [first, second] = data.tables;
          if (first && second) setPair({ left: first.id, right: second.id });
        }
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(message(reason, "Không tải được dữ liệu đối soát."));
      });
    return () => controller.abort();
  }, []);

  const period = periods?.[periodIndex] ?? null;

  // Đổi kỳ: tải chuỗi gần nhất của kỳ đó (nếu đã chạy).
  useEffect(() => {
    if (!period?.chain_id) return;
    const controller = new AbortController();
    getChain(period.chain_id, controller.signal)
      .then(setChain)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(message(reason, "Không tải được kết quả của kỳ."));
      });
    return () => controller.abort();
  }, [period?.chain_id]);

  // Chuỗi đang chạy nền: hỏi lại mỗi giây tới khi xong.
  useEffect(() => {
    if (!chain || chain.status !== "RUNNING") return;
    const timer = window.setInterval(() => {
      getChain(chain.id).then(setChain).catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [chain]);

  const run = useMemo(
    () => (pair ? runs.find((item) => item.left?.id === pair.left && item.right?.id === pair.right) ?? null : null),
    [runs, pair],
  );

  const replaceRun = useCallback((next: ReconRun) => {
    setRuns((current) => [next, ...current.filter((item) => item.id !== next.id)]);
  }, []);

  // Lần chạy hai bảng đang chạy nền: hỏi lại mỗi giây tới khi xong.
  useEffect(() => {
    if (!run || run.status !== "RUNNING") return;
    const timer = window.setInterval(() => {
      getRun(run.id).then(replaceRun).catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [run, replaceRun]);

  function rememberChain(next: ReconChain) {
    setChain(next);
    setPeriods((current) =>
      current?.map((item, index) => (index === periodIndex ? { ...item, chain_id: next.id } : item)) ?? null,
    );
  }

  async function runChain() {
    if (!period) return;
    setStarting(true);
    try {
      rememberChain(await startChain(period.tables.map((table) => table.id), period.label));
      setError(null);
    } catch (reason) {
      setError(message(reason, "Không chạy được đối soát cả chuỗi."));
    } finally {
      setStarting(false);
    }
  }

  // Sau khi chọn ứng viên cho ca mơ hồ, hệ thống chạy lại chuỗi (hoặc cặp) và trả về mã mới.
  async function onRerun(target: Rerun) {
    try {
      if (target.chain_id) rememberChain(await getChain(target.chain_id));
      else if (target.run_id) replaceRun(await getRun(target.run_id));
    } catch (reason) {
      setError(message(reason, "Không tải được kết quả mới."));
    }
  }

  const earlierMissing = periods?.slice(0, periodIndex).some((item) => !item.chain_id) ?? false;
  const shownChain = chain && period?.chain_id === chain.id ? chain : null;
  // Kỳ đã có lần đối soát (đang chạy hoặc xong): khối chọn kỳ thu gọn.
  const reconciled = Boolean(period?.chain_id);
  const periodRows = period?.tables.reduce((sum, table) => sum + table.row_count, 0) ?? 0;
  const tableList = period && (
    <ul className="period-panel__tables" aria-label="Các bảng thuộc kỳ">
      {period.tables.map((table) => (
        <li key={table.id}>
          <span className="period-panel__name">{table.label}</span>
          <span className="period-panel__kind">
            {table.table_kind_label} · {formatCount(table.row_count)} dòng
          </span>
        </li>
      ))}
    </ul>
  );
  const runButton = (
    <button
      className={reconciled ? "button button--quiet" : "button button--primary"}
      type="button"
      disabled={starting || shownChain?.status === "RUNNING"}
      onClick={() => void runChain()}
    >
      <Play aria-hidden="true" size={reconciled ? 15 : 17} strokeWidth={2} />
      {shownChain?.status === "RUNNING" ? "Đang đối soát…" : reconciled ? "Chạy lại cả chuỗi" : "Đối soát cả chuỗi"}
    </button>
  );
  const pairMode = tables !== null && tables.length >= 2 && pair && (
    <>
      <ReconSetup
        key={`${pair.left}:${pair.right}`}
        tables={tables}
        pair={pair}
        hasRun={run !== null}
        busy={run?.status === "RUNNING"}
        onPair={setPair}
        onStarted={replaceRun}
      />
      {run && <ReconRunView key={run.id} run={run} onRun={replaceRun} onRerun={onRerun} />}
    </>
  );

  return (
    <div className="recon">
      <header className="page__header">
        <h1>Đối soát</h1>
        <p>Ghép từng dòng giữa các bộ dữ liệu sạch. Mỗi kết quả có lý do và trỏ về đúng dòng gốc.</p>
      </header>

      {error && <p className="notice notice--error" role="alert">{error}</p>}
      {tables === null && !error && <p className="notice">Đang tải…</p>}
      {tables !== null && tables.length < 2 && (
        <div className="notice notice--action">
          <span>
            Cần ít nhất hai bộ dữ liệu đã làm sạch để đối soát (hiện có {tables.length}).
          </span>
          <a className="button button--quiet" {...linkTo("/du-lieu")}>Đến trang Dữ liệu</a>
        </div>
      )}

      {period && periods && (
        <section className="period-panel" aria-labelledby="period-title">
          <div className="period-panel__head">
            <h2 id="period-title">
              <Layers aria-hidden="true" size={18} /> Đối soát theo kỳ
            </h2>
            {periods.length > 1 && (
              <div className="segmented" role="group" aria-label="Chọn kỳ">
                {periods.map((item, index) => (
                  <button
                    key={item.label}
                    type="button"
                    aria-pressed={index === periodIndex}
                    onClick={() => {
                      setChain(null);
                      setPeriodIndex(index);
                    }}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          {/* Kỳ đã đối soát: việc chính là xử lý các ca bên dưới, nên danh sách bảng thu vào một
              dòng tóm tắt và "Chạy lại" thành nút phụ; trên điện thoại khối này trước đây chiếm
              hết màn hình đầu, phải cuộn mới thấy số ca cần xem. */}
          {reconciled ? (
            <div className="period-panel__compact">
              <details className="period-panel__more">
                <summary>
                  {formatCount(period.tables.length)} bảng · {formatCount(periodRows)} dòng
                </summary>
                {tableList}
              </details>
              {runButton}
            </div>
          ) : (
            <>
              {tableList}
              {earlierMissing && (
                <p className="recon-setup__warn">
                  Kỳ trước chưa được đối soát: các khoản chờ tiền về của kỳ trước sẽ chưa được mang sang kỳ này.
                </p>
              )}
              <div className="period-panel__actions">
                <p>
                  Hệ thống tự nhận các cặp nối được (đơn hàng ↔ cổng ↔ sao kê), tự tách mã trong nội dung chuyển
                  khoản và ghép nhóm theo tổng tiền.
                </p>
                {runButton}
              </div>
            </>
          )}
        </section>
      )}

      {shownChain && <ChainView key={shownChain.id} chain={shownChain} onChain={setChain} onRerun={onRerun} />}

      {periods && periods.length > 0 ? (
        pairMode && (
          <details className="recon-manual">
            <summary>Đối soát hai bảng tự chọn</summary>
            <div className="recon-manual__body">{pairMode}</div>
          </details>
        )
      ) : (
        pairMode
      )}
    </div>
  );
}

type SetupProps = {
  tables: ReconTable[];
  pair: Pair;
  hasRun: boolean;
  busy: boolean;
  onPair: (pair: Pair) => void;
  onStarted: (run: ReconRun) => void;
};

function ReconSetup({ tables, pair, hasRun, busy, onPair, onStarted }: SetupProps) {
  const [config, setConfig] = useState<ReconConfig | null>(null);
  const [tolerance, setTolerance] = useState("0");
  const [windowDays, setWindowDays] = useState(3);
  const [excluded, setExcluded] = useState<ReconConfig["excluded"]>({});
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [explaining, setExplaining] = useState(false);
  const [explanation, setExplanation] = useState<string | null>(null);
  const body = { left_table_id: pair.left, right_table_id: pair.right };

  useEffect(() => {
    if (pair.left === pair.right) return;
    previewRecon({ left_table_id: pair.left, right_table_id: pair.right })
      .then((data) => {
        setConfig(data.config);
        setTolerance(String(Number(data.config.tolerance)));
        setWindowDays(data.config.date_window_days);
        setExcluded(data.config.excluded);
        setError(null);
      })
      .catch((reason: unknown) => setError(message(reason, "Không gợi ý được cấu hình.")));
  }, [pair.left, pair.right]);

  const isExcluded = (option: ScopeOption) => excluded[option.side]?.[option.field]?.includes(option.value) ?? false;
  const toggleScope = (option: ScopeOption) => {
    setExcluded((current) => {
      const side = { ...(current[option.side] ?? {}) };
      const values = new Set(side[option.field] ?? []);
      if (values.has(option.value)) values.delete(option.value);
      else values.add(option.value);
      side[option.field] = [...values].sort();
      return { ...current, [option.side]: side };
    });
  };
  const excludedCount = Object.values(excluded).reduce(
    (sum, fields) => sum + Object.values(fields ?? {}).reduce((inner, values) => inner + values.length, 0),
    0,
  );

  async function start() {
    setStarting(true);
    try {
      onStarted(await startRun({ ...body, tolerance, date_window_days: windowDays, excluded }));
      setError(null);
    } catch (reason) {
      setError(message(reason, "Không chạy được đối soát."));
    } finally {
      setStarting(false);
    }
  }

  async function explain() {
    setExplaining(true);
    try {
      setExplanation((await explainPreview(body)).text);
    } catch (reason) {
      setExplanation(null);
      setError(message(reason, "Gemini chưa trả lời được."));
    } finally {
      setExplaining(false);
    }
  }

  const option = (table: ReconTable) => (
    <option key={table.id} value={table.id}>
      {table.label} · {table.table_kind_label} · {formatCount(table.row_count)} dòng
    </option>
  );
  const left = tables.find((table) => table.id === pair.left);
  const right = tables.find((table) => table.id === pair.right);

  return (
    <section className="recon-setup" aria-labelledby="recon-setup-title">
      <h2 id="recon-setup-title" className="visually-hidden">Chọn dữ liệu và cấu hình</h2>
      <div className="recon-setup__pair">
        <label className="recon-setup__side">
          <span>Bên A</span>
          <select value={pair.left} onChange={(event) => onPair({ ...pair, left: event.target.value })}>
            {tables.map(option)}
          </select>
        </label>
        <button
          className="icon-button recon-setup__swap"
          type="button"
          aria-label="Đổi chỗ hai bên"
          title="Đổi chỗ hai bên"
          onClick={() => onPair({ left: pair.right, right: pair.left })}
        >
          <ArrowLeftRight aria-hidden="true" size={18} strokeWidth={1.8} />
        </button>
        <label className="recon-setup__side">
          <span>Bên B</span>
          <select value={pair.right} onChange={(event) => onPair({ ...pair, right: event.target.value })}>
            {tables.map(option)}
          </select>
        </label>
        <button
          className="button button--primary recon-setup__run"
          type="button"
          disabled={starting || busy || pair.left === pair.right || config === null}
          onClick={() => void start()}
        >
          <Play aria-hidden="true" size={17} strokeWidth={2} />
          {busy ? "Đang đối soát…" : hasRun ? "Chạy lại" : "Chạy đối soát"}
        </button>
      </div>

      {pair.left === pair.right && <p className="notice notice--error">Hãy chọn hai bảng khác nhau.</p>}
      {(left?.clean_open ?? 0) + (right?.clean_open ?? 0) > 0 && (
        <p className="recon-setup__warn">
          Còn {formatCount((left?.clean_open ?? 0) + (right?.clean_open ?? 0))} vấn đề chưa xử lý ở bước làm sạch.
          Vẫn chạy được; các dòng đó sẽ nằm trong nhóm “Dữ liệu chưa sạch”.
        </p>
      )}
      {error && <p className="notice notice--error" role="alert">{error}</p>}

      {config && (
        <details className="recon-config">
          <summary>
            <span className="recon-config__title">Cấu hình đối soát</span>
            <span className="recon-config__brief">
              {config.labels.key_left ? `Ghép theo ${config.labels.key_left.toLowerCase()}` : "Ghép theo số tiền và ngày"}
              {" · "}
              {Number(tolerance) === 0 ? "khớp tuyệt đối" : `sai số ${formatCount(Number(tolerance))}đ`}
              {excludedCount > 0 && ` · ${excludedCount} giá trị ngoài phạm vi`}
            </span>
          </summary>
          <div className="recon-config__body">
            <ul className="recon-config__lines">
              {config.description.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            <div className="recon-config__fields">
              <label>
                <span>Sai số tiền cho phép (đồng)</span>
                <input
                  inputMode="numeric"
                  value={tolerance}
                  onChange={(event) => setTolerance(event.target.value.replace(/[^\d]/g, "") || "0")}
                />
              </label>
              <label>
                <span>Khung ngày khi ghép theo điểm</span>
                <input
                  type="number"
                  min={0}
                  max={60}
                  value={windowDays}
                  onChange={(event) => setWindowDays(Math.max(0, Math.min(60, Number(event.target.value) || 0)))}
                />
              </label>
            </div>
            {config.scope_options.length > 0 && (
              <fieldset className="recon-config__scope">
                <legend>Để ngoài phạm vi (không đi qua bên kia)</legend>
                {config.scope_options.map((item) => (
                  <label key={`${item.side}:${item.field}:${item.value}`}>
                    <input type="checkbox" checked={isExcluded(item)} onChange={() => toggleScope(item)} />
                    <span>
                      Bên {item.side === "LEFT" ? "A" : "B"} · “{item.value}”
                      <small>
                        {formatCount(item.rows)} dòng, {formatCount(item.matched)} có mã ở bên kia
                      </small>
                    </span>
                  </label>
                ))}
              </fieldset>
            )}
            <div className="recon-config__ai">
              <button className="button button--quiet" type="button" disabled={explaining} onClick={() => void explain()}>
                <Sparkles aria-hidden="true" size={16} />
                {explaining ? "Gemini đang viết…" : "Giải thích bằng AI"}
              </button>
              {explanation && <p className="ai-note">{explanation}</p>}
            </div>
          </div>
        </details>
      )}
    </section>
  );
}
