import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, Play, Sparkles } from "lucide-react";

import {
  explainPreview,
  getReconTables,
  getRun,
  listRuns,
  previewRecon,
  startRun,
  type ReconConfig,
  type ReconRun,
  type ReconTable,
  type ScopeOption,
} from "../api";
import { ReconRunView } from "../components/ReconRunView";
import { formatCount } from "../format";
import { linkTo } from "../navigation";

// Trang Đối soát: chọn hai bảng sạch (hệ thống gợi ý sẵn), xem cấu hình (thu gọn, chỉnh được),
// bấm một nút để chạy; kết quả mở ra ở phần việc cần làm trước.

type Pair = { left: string; right: string };

const message = (reason: unknown, fallback: string) => (reason instanceof Error ? reason.message : fallback);

export function ReconcilePage() {
  const [tables, setTables] = useState<ReconTable[] | null>(null);
  const [runs, setRuns] = useState<ReconRun[]>([]);
  const [pair, setPair] = useState<Pair | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Lần đầu: tải các bảng đã sạch, lần đối soát gần nhất; chọn sẵn cặp của lần đó hoặc cặp gợi ý.
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([getReconTables(controller.signal), listRuns(20, controller.signal)])
      .then(([data, recent]) => {
        setTables(data.tables);
        setRuns(recent);
        const last = recent.find((run) => run.left && run.right);
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

  const run = useMemo(
    () => (pair ? runs.find((item) => item.left?.id === pair.left && item.right?.id === pair.right) ?? null : null),
    [runs, pair],
  );

  const replaceRun = useCallback((next: ReconRun) => {
    setRuns((current) => [next, ...current.filter((item) => item.id !== next.id)]);
  }, []);

  // Lần chạy đang chạy nền: hỏi lại mỗi giây tới khi xong.
  useEffect(() => {
    if (!run || run.status !== "RUNNING") return;
    const timer = window.setInterval(() => {
      getRun(run.id).then(replaceRun).catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [run, replaceRun]);

  return (
    <div className="recon">
      <header className="page__header">
        <h1>Đối soát</h1>
        <p>Ghép từng dòng giữa hai bộ dữ liệu sạch. Mỗi kết quả có lý do và trỏ về đúng dòng gốc.</p>
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
      {tables !== null && tables.length >= 2 && pair && (
        <ReconSetup
          key={`${pair.left}:${pair.right}`}
          tables={tables}
          pair={pair}
          hasRun={run !== null}
          busy={run?.status === "RUNNING"}
          onPair={setPair}
          onStarted={replaceRun}
        />
      )}
      {run && <ReconRunView key={run.id} run={run} onRun={replaceRun} />}
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
