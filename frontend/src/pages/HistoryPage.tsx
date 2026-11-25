import { useEffect, useState } from "react";

import { getAudit, type AuditEntry } from "../api";
import { formatCount } from "../format";

// Trang Lịch sử: nhật ký kiểm toán, mọi thay đổi của người dùng theo thời gian (mới nhất trước).
// Hệ thống tự ghi, người dùng không phải làm gì; trang này chỉ để xem lại.

const PAGE = 50;
const dayFormat = new Intl.DateTimeFormat("vi-VN", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });
const timeFormat = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

const OBJECT_LABELS: Record<string, string> = {
  DATASET: "Bộ dữ liệu",
  TABLE: "Bảng",
  RECON_RUN: "Đối soát",
  RECON_CHAIN: "Đối soát cả chuỗi",
};

export function HistoryPage() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  async function load(offset: number) {
    try {
      const page = await getAudit(offset, PAGE);
      setTotal(page.total);
      setEntries((current) => (offset === 0 ? page.items : [...(current ?? []), ...page.items]));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không tải được nhật ký.");
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    getAudit(0, PAGE, controller.signal)
      .then((page) => {
        setTotal(page.total);
        setEntries(page.items);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Không tải được nhật ký.");
      });
    return () => controller.abort();
  }, []);

  // Gom theo ngày để dễ dò.
  const days: { day: string; items: AuditEntry[] }[] = [];
  for (const entry of entries ?? []) {
    const day = entry.created_at ? dayFormat.format(new Date(entry.created_at)) : "Không rõ ngày";
    const last = days[days.length - 1];
    if (last?.day === day) last.items.push(entry);
    else days.push({ day, items: [entry] });
  }

  return (
    <div className="history">
      <header className="page__header">
        <h1>Lịch sử</h1>
        <p>
          Nhật ký kiểm toán: hệ thống tự ghi mọi thay đổi bạn làm với dữ liệu, ánh xạ và kết quả đối soát, kèm
          giá trị trước và sau.
        </p>
      </header>

      {error && <p className="notice notice--error" role="alert">{error}</p>}
      {entries === null && !error && <p className="notice">Đang tải…</p>}
      {entries !== null && entries.length === 0 && (
        <p className="notice">Chưa có thay đổi nào. Tải tệp, xác nhận ánh xạ hay xử lý ngoại lệ sẽ được ghi ở đây.</p>
      )}

      {days.map(({ day, items }) => (
        <section key={day} className="history__day" aria-label={day}>
          <h2>{day}</h2>
          <ol className="history__list">
            {items.map((entry) => (
              <li key={entry.id} className="history__item">
                <time dateTime={entry.created_at ?? undefined}>
                  {entry.created_at ? timeFormat.format(new Date(entry.created_at)) : ""}
                </time>
                <div className="history__body">
                  <p className="history__summary">{entry.summary}</p>
                  <p className="history__meta">
                    {/* Loại chưa có tên tiếng Việt thì ghi chung, không lộ mã kỹ thuật cho người dùng. */}
                    {OBJECT_LABELS[entry.object_type] ?? "Đối tượng"}: {entry.object_label} · {entry.actor}
                  </p>
                  {(entry.before || entry.after) && (
                    <details className="history__change">
                      <summary>Giá trị trước và sau</summary>
                      <dl>
                        {entry.before && (
                          <>
                            <dt>Trước</dt>
                            <dd><code>{JSON.stringify(entry.before)}</code></dd>
                          </>
                        )}
                        {entry.after && (
                          <>
                            <dt>Sau</dt>
                            <dd><code>{JSON.stringify(entry.after)}</code></dd>
                          </>
                        )}
                      </dl>
                    </details>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>
      ))}

      {entries !== null && entries.length < total && (
        <button className="button button--quiet history__more" type="button" onClick={() => void load(entries.length)}>
          Xem thêm ({formatCount(total - entries.length)} mục cũ hơn)
        </button>
      )}
    </div>
  );
}
