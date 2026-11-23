import { useEffect, useState } from "react";
import { Ban, Check, CopyMinus, RotateCw, Sparkles, Wand2 } from "lucide-react";

import {
  acceptCellSuggestion,
  acceptDuplicates,
  chooseDateOrder,
  decideRows,
  fixCell,
  getCleaning,
  rebuildCleaning,
  type Cleaning,
  type CleaningIssue,
} from "../api";
import { formatCount } from "../format";
import { CleanPreview } from "./CleanPreview";

// Làm sạch theo ba mức: hệ thống đã tự sửa (chỉ cần xem), gợi ý (đồng ý một lần cho cả nhóm),
// và cần bạn xử lý (đúng ô, có gợi ý của AI nếu có). Mọi thao tác tạo một phiên bản sạch mới;
// tệp gốc không bao giờ bị sửa.

type Props = { tableId: string; cleanStatus: string; onChanged: () => void };

export function CleaningView({ tableId, cleanStatus, onChanged }: Props) {
  const [cleaning, setCleaning] = useState<Cleaning | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getCleaning(tableId, controller.signal)
      .then((data) => {
        setCleaning(data);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Lỗi không rõ.");
      });
    return () => controller.abort();
  }, [tableId, cleanStatus]);

  // Khi chính khung này đang ở trạng thái "đang dựng lại" hoặc "AI đang đề xuất" thì tự hỏi lại
  // backend mỗi giây tới khi xong. Không chỉ dựa vào trạng thái của trang cha: nếu backend dựng
  // xong trước khi trang cha kịp thấy BUILDING, trạng thái ở đó vẫn là READY → READY (không đổi)
  // và khung sẽ kẹt mãi ở số liệu cũ.
  const pending = cleaning?.status === "BUILDING" || cleaning?.status === "SUGGESTING";
  useEffect(() => {
    if (!pending) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      getCleaning(tableId, controller.signal)
        .then((data) => {
          setCleaning(data);
          // Dựng xong: báo trang cha tải lại số đếm (nhãn số vấn đề trên tab).
          if (data.status !== "BUILDING" && data.status !== "SUGGESTING") onChanged();
        })
        .catch(() => undefined); // lỗi mạng tạm thời: lần hỏi kế tiếp sẽ thử lại
    }, 1000);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [tableId, pending, cleaning, onChanged]);

  async function run(action: () => Promise<Cleaning>) {
    setBusy(true);
    try {
      setCleaning(await action());
      setError(null);
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không lưu được.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !cleaning) return <p className="notice notice--error" role="alert">{error}</p>;
  if (!cleaning) return <p className="notice">Đang tải…</p>;
  if (cleaning.status === "NONE") {
    return <p className="notice">Bộ dữ liệu sạch sẽ được dựng sau khi ánh xạ cột xong (cần ít nhất một cột được ánh xạ).</p>;
  }
  if (cleaning.status === "FAILED") {
    return (
      <div className="notice notice--error notice--action" role="alert">
        <span>Dựng bộ dữ liệu sạch chưa xong (bị gián đoạn hoặc lỗi).</span>
        <button className="button button--quiet" type="button" onClick={() => void run(() => rebuildCleaning(tableId))}>
          <RotateCw aria-hidden="true" size={16} />
          Dựng lại
        </button>
      </div>
    );
  }

  const open = cleaning.issues.filter((issue) => issue.status === "OPEN");
  const asks = open.filter((issue) => issue.level === "ASK");
  const suggests = open.filter((issue) => issue.level === "SUGGEST");
  const resolved = cleaning.issues.filter((issue) => issue.status === "RESOLVED");
  const summary = cleaning.summary;

  return (
    <div className="cleaning">
      <p className="cleaning__meta">
        {cleaning.status === "BUILDING" ? (
          <span className="cleaning__building">
            <Sparkles aria-hidden="true" size={15} /> Đang dựng lại bộ dữ liệu sạch…
          </span>
        ) : (
          <>
            Bộ dữ liệu sạch phiên bản {cleaning.version} · {formatCount(cleaning.row_count)} dòng
            {cleaning.excluded_count > 0 && ` · đã loại ${formatCount(cleaning.excluded_count)} dòng`}
            {summary && summary.cancelled_count > 0 && ` · ${formatCount(summary.cancelled_count)} đơn đã hủy (giữ lại, có đánh dấu)`}
          </>
        )}
      </p>
      {cleaning.status === "SUGGESTING" && (
        <p className="cleaning__building">
          <Sparkles aria-hidden="true" size={15} /> AI đang đề xuất cách sửa cho các ô khó, gợi ý sẽ hiện ngay bên dưới…
        </p>
      )}
      {error && <p className="notice notice--error" role="alert">{error}</p>}

      {asks.length === 0 && suggests.length === 0 && (
        <section className="cleaning__done">
          <Check aria-hidden="true" size={20} />
          <div>
            <h3>Dữ liệu đã sạch</h3>
            <p>Không còn ô hay dòng nào cần bạn xử lý. Bộ dữ liệu này sẵn sàng cho bước đối soát.</p>
          </div>
        </section>
      )}

      {asks.length > 0 && (
        <section className="cleaning__group" aria-labelledby="ask-title">
          <h3 id="ask-title" className="cleaning__title cleaning__title--ask">
            Cần bạn xử lý {asks.length} chỗ
          </h3>
          <ul className="cleaning__list">
            {asks.map((issue) => (
              <AskItem key={issue.id} issue={issue} tableId={tableId} disabled={busy} run={run} />
            ))}
          </ul>
        </section>
      )}

      {suggests.length > 0 && (
        <section className="cleaning__group" aria-labelledby="suggest-title">
          <div className="cleaning__group-head">
            <h3 id="suggest-title" className="cleaning__title">
              Gợi ý: {suggests.length} nhóm dòng trùng y hệt
            </h3>
            <button
              className="button button--primary"
              type="button"
              disabled={busy}
              onClick={() => void run(() => acceptDuplicates(tableId))}
            >
              <CopyMinus aria-hidden="true" size={18} />
              Bỏ các bản lặp
            </button>
          </div>
          <ul className="cleaning__list">
            {suggests.map((issue) => (
              <li key={issue.id} className="cleaning__item">
                <p>{issue.message}</p>
                <button
                  className="button button--quiet"
                  type="button"
                  disabled={busy}
                  onClick={() => void run(() => decideRows(tableId, issue.row_refs, "KEEP"))}
                >
                  Giữ tất cả
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {summary && (summary.fixes.length > 0 || summary.empty_rows.length > 0) && (
        <section className="cleaning__group" aria-labelledby="auto-title">
          <h3 id="auto-title" className="cleaning__title cleaning__title--auto">
            <Wand2 aria-hidden="true" size={18} /> Hệ thống đã tự sửa
          </h3>
          <ul className="fixes">
            {summary.empty_rows.length > 0 && (
              <li>
                <span className="fixes__what">Bỏ {summary.empty_rows.length} dòng trống hoàn toàn</span>
                <span className="fixes__examples">dòng gốc {summary.empty_rows.slice(0, 5).join(", ")}</span>
              </li>
            )}
            {summary.fixes.map((fix) => (
              <li key={`${fix.field_key}-${fix.fix}`}>
                <span className="fixes__what">
                  {fix.field_label}: {fix.fix_label.toLowerCase()}
                  <span className="fixes__count">{formatCount(fix.count)} ô</span>
                </span>
                <span className="fixes__examples">
                  {fix.examples.map((example) => (
                    <span key={example.row_ref}>
                      <code>{example.before}</code> → <code>{example.after}</code>
                    </span>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {summary && summary.date_orders.length > 0 && (
        <section className="cleaning__group" aria-labelledby="date-title">
          <h3 id="date-title" className="cleaning__title">Cách đọc ngày</h3>
          <ul className="cleaning__list">
            {summary.date_orders.map((item) => (
              <li key={item.field_key} className="cleaning__item">
                <p>
                  <strong>{item.field_label}</strong>: đọc theo {item.order === "DMY" ? "ngày/tháng" : "tháng/ngày"}
                  {item.chosen_by_user
                    ? " (bạn đã chọn)."
                    : item.defaulted
                      ? " — mặc định, vì mọi ngày trong cột đều ≤ 12 nên không tự phân biệt được."
                      : " (tự nhận từ dữ liệu)."}
                </p>
                <button
                  className="button button--quiet"
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void run(() => chooseDateOrder(tableId, item.field_key, item.order === "DMY" ? "MDY" : "DMY"))
                  }
                >
                  Đổi sang {item.order === "DMY" ? "tháng/ngày" : "ngày/tháng"}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {resolved.length > 0 && (
        <details className="cleaning__resolved">
          <summary>Đã xử lý {resolved.length} vấn đề</summary>
          <ul>
            {resolved.map((issue) => (
              <li key={issue.id}>
                {issue.message}
                {(issue.kind === "DUPLICATE_ROW" || issue.kind === "CONFLICTING_VALUES") && (
                  <button
                    className="button button--quiet"
                    type="button"
                    disabled={busy}
                    onClick={() => void run(() => decideRows(tableId, issue.row_refs, "UNDO"))}
                  >
                    Hoàn tác
                  </button>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}

      {cleaning.version !== null && <CleanPreview key={cleaning.version} tableId={tableId} />}
    </div>
  );
}

type AskProps = {
  issue: CleaningIssue;
  tableId: string;
  disabled: boolean;
  run: (action: () => Promise<Cleaning>) => Promise<void>;
};

function AskItem({ issue, tableId, disabled, run }: AskProps) {
  const [value, setValue] = useState("");
  const ref = issue.row_refs[0] ?? 0;
  const inputId = `fix-${issue.id}`;
  const suggestion = issue.ai_suggestion;
  const editable = issue.kind !== "CONFLICTING_VALUES" && issue.field_key !== null;

  return (
    <li className="cleaning__item cleaning__item--ask">
      <div className="cleaning__body">
        <p className="cleaning__where">
          {issue.row_refs.length > 1 ? `Dòng gốc ${issue.row_refs.join(", ")}` : `Dòng gốc ${ref}`}
          {issue.field_label && ` · ${issue.field_label}`}
        </p>
        <p>{issue.message}</p>
        {suggestion && (
          <p className="cleaning__ai">
            <Sparkles aria-hidden="true" size={15} />
            {suggestion.value !== null ? (
              <>
                AI đề xuất <code>{suggestion.value}</code> — {suggestion.reason}
                <button
                  className="button button--quiet"
                  type="button"
                  disabled={disabled}
                  onClick={() => void run(() => acceptCellSuggestion(tableId, ref, issue.field_key ?? ""))}
                >
                  Dùng gợi ý
                </button>
              </>
            ) : (
              <>{suggestion.reason}</>
            )}
          </p>
        )}
      </div>
      <div className="cleaning__actions">
        {editable && (
          <form
            className="cleaning__fix"
            onSubmit={(event) => {
              event.preventDefault();
              if (value.trim()) void run(() => fixCell(tableId, ref, issue.field_key ?? "", value));
            }}
          >
            <label htmlFor={inputId} className="visually-hidden">
              Giá trị đúng cho {issue.field_label} ở dòng {ref}
            </label>
            <input
              id={inputId}
              value={value}
              placeholder="Nhập giá trị đúng"
              onChange={(event) => setValue(event.target.value)}
            />
            <button className="button button--quiet" type="submit" disabled={disabled || !value.trim()}>
              Lưu
            </button>
          </form>
        )}
        {issue.kind === "CONFLICTING_VALUES" && (
          <button
            className="button button--quiet"
            type="button"
            disabled={disabled}
            onClick={() => void run(() => decideRows(tableId, issue.row_refs, "KEEP"))}
          >
            Giữ cả {issue.row_refs.length} dòng
          </button>
        )}
        {issue.row_refs.map((rowRef) => (
          <button
            key={rowRef}
            className="button button--quiet button--danger-text"
            type="button"
            disabled={disabled}
            onClick={() => void run(() => decideRows(tableId, [rowRef], "EXCLUDE"))}
          >
            <Ban aria-hidden="true" size={15} />
            Loại dòng {rowRef}
          </button>
        ))}
      </div>
    </li>
  );
}
