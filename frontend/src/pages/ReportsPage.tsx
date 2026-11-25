import { useCallback, useEffect, useState } from "react";
import { ArrowRight, FileDown, FileSpreadsheet, Sparkles } from "lucide-react";

import {
  ApiError,
  getReport,
  listReports,
  reportExportUrl,
  writeReportComment,
  type ReconKind,
  type Report,
  type ReportException,
  type ReportPeriod,
} from "../api";
import {
  BarList,
  ChartPanel,
  DayColumns,
  DayTable,
  money,
  percent,
  type BarRow,
  type Tone,
} from "../components/ReportCharts";
import { VerificationSeal } from "../components/VerificationSeal";
import { formatCount, formatDateTime } from "../format";
import { navigate } from "../navigation";
import { mergeSealChecks } from "../verification";

// Trang Báo cáo (Giai đoạn 7): người đọc chính là chủ cửa hàng. Phần đầu trả lời "tiền đã về
// đủ chưa, thiếu bao nhiêu, cần xử lý gì trước"; biểu đồ và chi tiết theo cặp nằm bên dưới.
// Mọi con số do backend tính từ kết quả engine đã lưu; trang không tự tính số liệu nghiệp vụ.

type Load<T> = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: T };

const MATCHED_KINDS: ReconKind[] = ["MATCHED", "MANY_TO_ONE", "ONE_TO_MANY"];

function kindTone(kind: ReconKind): Tone {
  if (MATCHED_KINDS.includes(kind)) return "matched";
  if (kind === "PENDING_SETTLEMENT") return "pending";
  if (kind === "OUT_OF_SCOPE") return "scope";
  return "attention";
}

const isZero = (value: string) => Number(value) === 0;

export function ReportsPage() {
  const [periods, setPeriods] = useState<Load<ReportPeriod[]>>({ kind: "loading" });
  const [chainId, setChainId] = useState<string | null>(null);
  // Báo cáo đã tải gắn với mã kỳ; đổi kỳ thì báo cáo cũ không còn khớp và trang hiện khung chờ.
  const [loaded, setLoaded] = useState<{ id: string; state: Load<Report> } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    listReports(controller.signal)
      .then(({ periods: found }) => {
        setPeriods({ kind: "ready", data: found });
        // Mở ra là kỳ mới nhất (danh sách xếp theo ngày bắt đầu).
        setChainId((current) => current ?? found.at(-1)?.chain_id ?? null);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setPeriods({ kind: "error", message: error instanceof Error ? error.message : "Không tải được báo cáo." });
        }
      });
    return () => controller.abort();
  }, []);

  const load = useCallback((id: string, signal?: AbortSignal) => {
    getReport(id, signal)
      .then((data) => setLoaded({ id, state: { kind: "ready", data } }))
      .catch((error: unknown) => {
        if (!signal?.aborted) {
          const message = error instanceof Error ? error.message : "Không tải được báo cáo.";
          setLoaded({ id, state: { kind: "error", message } });
        }
      });
  }, []);

  useEffect(() => {
    if (!chainId) return;
    const controller = new AbortController();
    load(chainId, controller.signal);
    return () => controller.abort();
  }, [chainId, load]);

  const list = periods.kind === "ready" ? periods.data : [];
  const report: Load<Report> | null = !chainId
    ? null
    : loaded?.id === chainId
      ? loaded.state
      : { kind: "loading" };

  return (
    <div className="report">
      <header className="page__header">
        <h1>Báo cáo</h1>
        <p>Kết quả đối soát của từng kỳ: tiền đã về khớp bao nhiêu, còn gì cần xử lý, và tệp để tải về.</p>
      </header>

      {periods.kind === "loading" && <p className="notice notice--busy">Đang tải báo cáo…</p>}
      {periods.kind === "error" && <p className="notice notice--error" role="alert">{periods.message}</p>}
      {periods.kind === "ready" && list.length === 0 && (
        <section className="next-step" aria-labelledby="report-empty">
          <div>
            <h2 id="report-empty">Chưa có kỳ nào được đối soát</h2>
            <p>Báo cáo lập từ kết quả đối soát cả chuỗi của một kỳ. Hãy đối soát một kỳ trước, báo cáo sẽ có ngay sau đó.</p>
          </div>
          <button type="button" className="button button--primary" onClick={() => navigate("/doi-soat")}>
            Mở trang Đối soát <ArrowRight aria-hidden="true" size={18} />
          </button>
        </section>
      )}

      {list.length > 1 && (
        <div className="segmented report__periods" role="group" aria-label="Chọn kỳ báo cáo">
          {list.map((period) => (
            <button
              key={period.chain_id}
              type="button"
              aria-pressed={period.chain_id === chainId}
              onClick={() => setChainId(period.chain_id)}
            >
              {period.label}
            </button>
          ))}
        </div>
      )}

      {report?.kind === "loading" && <div className="report__skeleton" aria-busy="true" aria-label="Đang tải báo cáo" />}
      {report?.kind === "error" && <p className="notice notice--error" role="alert">{report.message}</p>}
      {report?.kind === "ready" && (
        <ReportBody report={report.data} periods={list} onReload={() => chainId && load(chainId)} />
      )}
    </div>
  );
}

function ReportBody({ report, periods, onReload }: { report: Report; periods: ReportPeriod[]; onReload: () => void }) {
  const { kpis } = report;
  const unmatched = Math.max(0, Number(kpis.amount_in_scope) - Number(kpis.amount_matched) - Number(kpis.pending_amount));
  const split = [
    { label: "Đã khớp", value: Number(kpis.amount_matched), tone: "matched" },
    { label: "Chờ tiền về", value: Number(kpis.pending_amount), tone: "pending" },
    { label: "Chưa khớp", value: unmatched, tone: "attention" },
  ] as const;
  const total = Number(kpis.amount_in_scope) || 1;

  return (
    <div className="report__grid">
      <div className="report__main">
        {!report.verified && (
          <p className="notice notice--error" role="alert">
            Kỳ này chưa qua kiểm chứng: số liệu bên dưới chỉ để xem, chưa xuất được tệp và chưa viết được nhận xét AI.
            Hãy kiểm chứng lại ở trang Đối soát.
          </p>
        )}

        <section className="report-answer" aria-labelledby="report-answer">
          <p className="report-answer__period">{report.label}</p>
          <h2 id="report-answer">Đã khớp {percent(kpis.match_rate_amount)} số tiền cần đối chiếu</h2>
          <p className="report-answer__lead">
            {money(kpis.amount_matched)} trên {money(kpis.amount_in_scope)}.{" "}
            {kpis.open_count > 0
              ? `Còn ${formatCount(kpis.open_count)} ca cần bạn xử lý.`
              : "Không còn ca nào cần xử lý."}{" "}
            {kpis.pending_count > 0 &&
              `${formatCount(kpis.pending_count)} khoản đang chờ tiền về: chênh lệch do thời điểm, không phải lỗi.`}
          </p>
          <figure className="composition" aria-label="Số tiền cần đối chiếu chia theo trạng thái">
            <div className="composition__bar">
              {split.map((part) =>
                part.value > 0 ? (
                  <span key={part.label} data-tone={part.tone} style={{ flexGrow: part.value }} title={`${part.label}: ${money(String(part.value))}`} />
                ) : null,
              )}
            </div>
            <figcaption className="composition__legend">
              {split.map((part) => (
                <span key={part.label} data-tone={part.tone}>
                  {part.label} <b>{money(String(part.value))}</b> ({percent(Math.round((part.value / total) * 1000) / 10)})
                </span>
              ))}
            </figcaption>
          </figure>
          <dl className="report-figures">
            <div>
              <dt>Cần xử lý</dt>
              <dd>{formatCount(kpis.open_count)} ca</dd>
            </div>
            <div data-zero={isZero(kpis.missing_amount) || undefined}>
              <dt>Thiếu tiền về</dt>
              <dd>{money(kpis.missing_amount)}</dd>
            </div>
            <div data-zero={isZero(kpis.unknown_amount) || undefined}>
              <dt>Tiền về chưa rõ nguồn</dt>
              <dd>{money(kpis.unknown_amount)}</dd>
            </div>
            <div data-zero={isZero(kpis.mismatch_total) || undefined}>
              <dt>Tổng lệch tiền</dt>
              <dd>{money(kpis.mismatch_total)}</dd>
            </div>
            <div>
              <dt>Khớp theo số dòng</dt>
              <dd>{percent(kpis.match_rate_rows)}</dd>
            </div>
          </dl>
        </section>

        <TopExceptions report={report} />

        <div className="report__charts">
          <ChartPanel
            title="Theo ngày"
            note="Số giao dịch mỗi ngày của kỳ, theo ngày của dòng bên A."
            table={<DayTable days={report.by_day} />}
          >
            {report.by_day.length ? <DayColumns days={report.by_day} /> : <p className="report-chart__empty">Không có ngày nào để vẽ.</p>}
          </ChartPanel>
          <PairsChart report={report} />
          <AgingChart report={report} />
          <KindsChart report={report} />
        </div>

        {periods.length > 0 && <Comparison periods={periods} current={report.chain_id} />}
      </div>

      <aside className="report__side">
        <VerifiedExport report={report} />
        <AiComment report={report} onReload={onReload} />
      </aside>
    </div>
  );
}

function TopExceptions({ report }: { report: Report }) {
  const items = report.top_exceptions;
  return (
    <section className="report-top" aria-labelledby="report-top">
      <div className="report-top__head">
        <h2 id="report-top">Cần xử lý trước</h2>
        {report.kpis.open_count > 0 && (
          <button type="button" className="button button--quiet" onClick={() => navigate("/doi-soat")}>
            Xử lý ở trang Đối soát <ArrowRight aria-hidden="true" size={16} />
          </button>
        )}
      </div>
      {items.length === 0 ? (
        <p className="report-top__empty">Mọi ngoại lệ đã được xử lý hoặc ghi chú.</p>
      ) : (
        <>
          <p className="report-top__note">
            {items.length < report.kpis.open_count
              ? `${formatCount(items.length)} ca có số tiền lớn nhất trong ${formatCount(report.kpis.open_count)} ca đang mở.`
              : "Xếp theo số tiền liên quan, lớn nhất trước."}
          </p>
          <ol className="report-top__list">
            {items.map((item) => (
              <li key={item.result_id}>
                <div className="report-top__what">
                  <span className="report-top__kind">{item.kind_label}</span>
                  <b>{item.codes.join(", ") || rowsText(item)}</b>
                  <span className="report-top__meta">
                    {item.pair}
                    {item.age_days !== null && ` · ${formatCount(item.age_days)} ngày tới cuối kỳ`}
                  </span>
                </div>
                <span className="report-top__amount">{money(item.amount)}</span>
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}

/** Ca không có mã (ví dụ dòng sao kê không ghi mã đơn): gọi theo số dòng gốc. */
function rowsText(item: ReportException): string {
  const parts = [];
  if (item.left_rows.length) parts.push(`dòng A ${item.left_rows.join(", ")}`);
  if (item.carried_rows.length) parts.push(`dòng kỳ trước ${item.carried_rows.join(", ")}`);
  if (item.right_rows.length) parts.push(`dòng B ${item.right_rows.join(", ")}`);
  return `Không có mã (${parts.join("; ")})`;
}

function PairsChart({ report }: { report: Report }) {
  const rows: BarRow[] = report.pairs.map((pair) => ({
    key: pair.run_id,
    label: pair.label,
    value: pair.match_rate_amount ?? 0,
    display: `${percent(pair.match_rate_amount)} · ${formatCount(pair.open_count)} cần xử lý`,
    tone: "matched",
  }));
  return (
    <ChartPanel
      title="Theo cặp đối soát"
      note="Tỷ lệ khớp theo số tiền của từng cặp nguồn."
      table={
        <table className="report-table">
          <thead>
            <tr><th>Cặp</th><th>Khớp theo tiền</th><th>Khớp theo dòng</th><th>Cần xử lý</th><th>Chờ tiền về</th></tr>
          </thead>
          <tbody>
            {report.pairs.map((pair) => (
              <tr key={pair.run_id}>
                <td>{pair.label}</td>
                <td>{percent(pair.match_rate_amount)}</td>
                <td>{percent(pair.match_rate_rows)}</td>
                <td>{formatCount(pair.open_count)}</td>
                <td>{money(pair.pending_amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <BarList rows={rows} max={100} columns={1} />
    </ChartPanel>
  );
}

function KindsChart({ report }: { report: Report }) {
  // Dòng ngoài phạm vi (đơn tiền mặt, tiền ra…) không cần đối chiếu nên không vẽ, chỉ ghi số;
  // vẽ vào thì thanh của nó lấn át các loại cần chú ý.
  const outside = report.by_kind.find((item) => item.kind === "OUT_OF_SCOPE")?.count ?? 0;
  const rows: BarRow[] = report.by_kind
    .filter((item) => item.kind !== "OUT_OF_SCOPE")
    .sort((a, b) => b.count - a.count)
    .map((item) => ({
      key: item.kind,
      label: item.label,
      value: item.count,
      display: formatCount(item.count),
      tone: kindTone(item.kind),
      hint: `${item.label}: ${formatCount(item.count)} kết quả, ${money(item.amount)}`,
    }));
  return (
    <ChartPanel
      title="Theo loại kết quả"
      note={`Số kết quả của mọi cặp; không vẽ ${formatCount(outside)} kết quả ngoài phạm vi (có trong bảng).`}
      table={
        <table className="report-table">
          <thead><tr><th>Loại</th><th>Số kết quả</th><th>Số tiền liên quan</th></tr></thead>
          <tbody>
            {[...report.by_kind].sort((a, b) => b.count - a.count).map((item) => (
              <tr key={item.kind}>
                <td>{item.label}</td>
                <td>{formatCount(item.count)}</td>
                <td>{money(item.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <BarList rows={rows} />
    </ChartPanel>
  );
}

function AgingChart({ report }: { report: Report }) {
  const rows: BarRow[] = report.aging.map((bucket) => ({
    key: bucket.label,
    label: bucket.label,
    value: bucket.count,
    display: `${formatCount(bucket.count)} ca · ${money(bucket.amount)}`,
    tone: "attention",
  }));
  return (
    <ChartPanel
      title="Tuổi ngoại lệ còn mở"
      note="Số ngày từ ngày giao dịch tới ngày cuối kỳ; ca càng cũ càng nên xử lý trước."
      table={
        <table className="report-table">
          <thead><tr><th>Nhóm tuổi</th><th>Số ca</th><th>Số tiền liên quan</th></tr></thead>
          <tbody>
            {report.aging.map((bucket) => (
              <tr key={bucket.label}>
                <td>{bucket.label}</td>
                <td>{formatCount(bucket.count)}</td>
                <td>{money(bucket.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      {report.kpis.open_count === 0 ? (
        <p className="report-chart__empty">Không còn ngoại lệ nào đang mở.</p>
      ) : (
        <BarList rows={rows} columns={1} />
      )}
    </ChartPanel>
  );
}

function Comparison({ periods, current }: { periods: ReportPeriod[]; current: string }) {
  return (
    <section className="report-compare" aria-labelledby="report-compare">
      <h2 id="report-compare">So sánh các kỳ</h2>
      <div className="report-compare__scroll">
        <table className="report-table">
          <thead>
            <tr>
              <th>Kỳ</th>
              <th>Khớp theo tiền</th>
              <th>Cần xử lý</th>
              <th>Tổng lệch</th>
              <th>Thiếu tiền về</th>
              <th>Kiểm chứng</th>
            </tr>
          </thead>
          <tbody>
            {periods.map((period) => (
              <tr key={period.chain_id} aria-current={period.chain_id === current ? "true" : undefined}>
                <td>{period.label}</td>
                <td>{period.kpis ? percent(period.kpis.match_rate_amount) : "—"}</td>
                <td>{period.kpis ? formatCount(period.kpis.open_count) : "—"}</td>
                <td>{period.kpis ? money(period.kpis.mismatch_total) : "—"}</td>
                <td>{period.kpis ? money(period.kpis.missing_amount) : "—"}</td>
                <td>{period.verified ? "Đạt" : "Chưa đạt"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function VerifiedExport({ report }: { report: Report }) {
  const rings = mergeSealChecks(report.pairs.map((pair) => ({ name: pair.label, verification: pair.verification })));
  return (
    <section className="verification" aria-labelledby="report-verify">
      <h2 id="report-verify">Kiểm chứng và tải về</h2>
      <VerificationSeal checks={rings} size={160} />
      <p className="verification__lead">
        {report.verified
          ? "Mọi cặp của kỳ đạt bốn phép kiểm độc lập; số liệu dùng được cho báo cáo."
          : "Có cặp chưa đạt kiểm chứng; chỉ xuất được sau khi kiểm chứng đạt."}
      </p>
      <div className="report-export">
        {report.verified ? (
          <>
            <a className="button button--primary" href={reportExportUrl(report.chain_id, "xlsx")} download>
              <FileSpreadsheet aria-hidden="true" size={18} /> Tải Excel (3 sheet)
            </a>
            <a className="button button--quiet" href={reportExportUrl(report.chain_id, "csv")} download>
              <FileDown aria-hidden="true" size={18} /> Tải CSV
            </a>
          </>
        ) : (
          <button type="button" className="button button--primary" disabled>
            <FileSpreadsheet aria-hidden="true" size={18} /> Tải Excel (3 sheet)
          </button>
        )}
      </div>
      <p className="report-export__note">Excel gồm Tóm tắt, Cần xử lý và Toàn bộ kết quả kèm lý do, dòng gốc; CSV là Toàn bộ kết quả.</p>
    </section>
  );
}

function AiComment({ report, onReload }: { report: Report; onReload: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const comment = report.comment;

  async function write() {
    setBusy(true);
    setError(null);
    try {
      await writeReportComment(report.chain_id);
      onReload();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Không viết được nhận xét, hãy thử lại.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="report-comment" aria-labelledby="report-comment">
      <h2 id="report-comment">Nhận xét bằng AI</h2>
      {comment ? (
        <>
          <p className="ai-note">{comment.text}</p>
          <p className="report-comment__meta">
            {comment.stale
              ? "Số liệu đã đổi sau khi viết nhận xét này; hãy viết lại."
              : `Viết lúc ${formatDateTime(comment.created_at)}, chỉ dùng số liệu của báo cáo.`}
          </p>
        </>
      ) : (
        <p className="report-comment__meta">
          Gemini đọc các số liệu trên và viết vài câu tóm tắt. Mọi con số được kiểm lại với báo cáo trước khi hiện.
        </p>
      )}
      {error && <p className="notice notice--error" role="alert">{error}</p>}
      <button
        type="button"
        className="button button--quiet"
        onClick={() => void write()}
        disabled={busy || !report.verified}
      >
        <Sparkles aria-hidden="true" size={17} />
        {busy ? "Đang viết…" : comment ? "Viết lại nhận xét" : "Viết nhận xét bằng AI"}
      </button>
    </section>
  );
}
