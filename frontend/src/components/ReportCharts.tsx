import { useState, type CSSProperties, type ReactNode } from "react";

import type { ReportDay } from "../api";
import { formatCount, formatMoney } from "../format";

// Biểu đồ của trang Báo cáo, vẽ bằng HTML/CSS (không thêm thư viện, R5), theo skill dataviz:
// thanh mảnh, đầu bo 4px tựa vào đường gốc, khe 2px giữa các đoạn, lưới mờ, chữ mang màu mực
// (không mang màu dữ liệu), mỗi biểu đồ có chú thích và bảng dữ liệu tương ứng.
// Màu theo nghĩa của "Tờ tiền polymer": đã khớp (xanh lá), chờ tiền về (xanh dương),
// ngoại lệ (cam đỏ), ngoài phạm vi (xanh nhạt). Bộ ba màu đầu đã qua bộ kiểm màu của dataviz
// (độ sáng, độ đậm, khoảng cách cho người mù màu, tương phản ≥ 3:1 trên nền trắng).

export type Tone = "matched" | "pending" | "attention" | "scope";

/** Khung chung: tiêu đề, mô tả ngắn, biểu đồ và bảng dữ liệu (mở khi cần). */
export function ChartPanel({
  title,
  note,
  table,
  children,
}: {
  title: string;
  note?: string;
  table: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="report-chart" aria-label={title}>
      <header className="report-chart__head">
        <h3>{title}</h3>
        {note && <p>{note}</p>}
      </header>
      {children}
      <details className="report-chart__table">
        <summary>Xem dạng bảng</summary>
        {table}
      </details>
    </section>
  );
}

export type BarRow = { key: string; label: string; value: number; display: string; tone: Tone; hint?: string };

/** Thanh ngang: mỗi hàng nhãn bên trái, giá trị bên phải, thanh dài theo giá trị bên dưới
 *  (giá trị không đặt ở đầu thanh để thanh gần 100% không đẩy chữ tràn khung). */
export function BarList({ rows, max, columns }: { rows: BarRow[]; max?: number; columns?: number }) {
  const top = max ?? Math.max(1, ...rows.map((row) => row.value));
  return (
    <ul className="bar-list" style={columns ? ({ "--bar-columns": columns } as CSSProperties) : undefined}>
      {rows.map((row) => (
        <li key={row.key} title={row.hint ?? `${row.label}: ${row.display}`}>
          <span className="bar-list__head">
            <span className="bar-list__label">{row.label}</span>
            <span className="bar-list__value">{row.display}</span>
          </span>
          <span className="bar-list__track">
            <span
              className="bar-list__bar"
              data-tone={row.tone}
              style={{ width: `${row.value > 0 ? Math.max((row.value / top) * 100, 1.5) : 0}%` }}
            />
          </span>
        </li>
      ))}
    </ul>
  );
}

const DAY_GROUPS = [
  { key: "matched", label: "Đã khớp", tone: "matched" },
  { key: "pending", label: "Chờ tiền về", tone: "pending" },
  { key: "exception", label: "Ngoại lệ", tone: "attention" },
] as const;

type DayKey = (typeof DAY_GROUPS)[number]["key"];

function dayValues(day: ReportDay): Record<DayKey, number> & { handled: number } {
  // "Ngoại lệ" gồm ca còn mở và ca đã xử lý/giải thích (vẫn là ngoại lệ của ngày đó);
  // khung gợi ý nói rõ đã xử lý bao nhiêu.
  return {
    matched: day.matched ?? 0,
    pending: day.pending ?? 0,
    exception: (day.todo ?? 0) + (day.handled ?? 0),
    handled: day.handled ?? 0,
  };
}

const shortDay = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

/** Mốc trục tròn số: 0, bước, 2×bước… vượt giá trị lớn nhất. */
function ticks(max: number): number[] {
  const raw = Math.max(1, max) / 4;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 5, 10].find((factor) => factor * power >= raw) ?? 10) * power;
  const result = [];
  for (let value = 0; value <= max + step - 1 && result.length < 7; value += step) result.push(value);
  if ((result.at(-1) ?? 0) < max) result.push((result.at(-1) ?? 0) + step);
  return result;
}

/** Cột chồng theo ngày: số kết quả đã khớp, chờ tiền về, ngoại lệ. Rê chuột (hoặc Tab tới
 *  cột) hiện khung số liệu của ngày đó. */
export function DayColumns({ days }: { days: ReportDay[] }) {
  const [active, setActive] = useState<number | null>(null);
  const entries = days.map((day) => {
    const value = dayValues(day);
    return { day, value, total: value.matched + value.pending + value.exception };
  });
  const axis = ticks(Math.max(0, ...entries.map((entry) => entry.total)));
  const top = axis.at(-1) || 1;
  // Nhãn ngày thưa dần khi nhiều ngày để không chồng chữ.
  const every = days.length > 20 ? 5 : days.length > 10 ? 2 : 1;
  const current = active === null ? undefined : entries[active];

  return (
    <div className="day-chart">
      <div className="day-chart__legend" aria-hidden="true">
        {DAY_GROUPS.map((group) => (
          <span key={group.key} data-tone={group.tone}>{group.label}</span>
        ))}
      </div>
      <div className="day-chart__plot">
        <div className="day-chart__axis" aria-hidden="true">
          {axis.map((value) => (
            <span key={value} style={{ bottom: `${(value / top) * 100}%` }}>{formatCount(value)}</span>
          ))}
        </div>
        <div className="day-chart__grid" aria-hidden="true">
          {axis.map((value) => (
            <span key={value} style={{ bottom: `${(value / top) * 100}%` }} />
          ))}
        </div>
        <ol className="day-chart__columns" onMouseLeave={() => setActive(null)}>
          {entries.map(({ day, value, total }, index) => {
            const label = `${shortDay(day.date)}: ${formatCount(value.matched)} đã khớp, ${formatCount(value.pending)} chờ tiền về, ${formatCount(value.exception)} ngoại lệ`;
            return (
              <li key={day.date}>
                <button
                  type="button"
                  className="day-chart__hit"
                  aria-label={label}
                  aria-pressed={active === index}
                  onMouseEnter={() => setActive(index)}
                  onFocus={() => setActive(index)}
                  onBlur={() => setActive(null)}
                >
                  <span className="day-chart__stack" style={{ height: `${(total / top) * 100}%` }}>
                    {DAY_GROUPS.map((group) =>
                      value[group.key] > 0 ? (
                        <span key={group.key} data-tone={group.tone} style={{ flexGrow: value[group.key] }} />
                      ) : null,
                    )}
                  </span>
                </button>
                <span className="day-chart__tick" aria-hidden="true">
                  {index % every === 0 ? shortDay(day.date) : ""}
                </span>
              </li>
            );
          })}
        </ol>
        {current && active !== null && (
          <div className="day-chart__tip" role="status" style={{ left: `${((active + 0.5) / days.length) * 100}%` }}>
            <b>Ngày {shortDay(current.day.date)}</b>
            {DAY_GROUPS.map((group) => (
              <span key={group.key} data-tone={group.tone}>
                {group.label}: <b>{formatCount(current.value[group.key])}</b>
              </span>
            ))}
            {current.value.handled > 0 && (
              <span className="day-chart__tip-note">trong đó đã xử lý {formatCount(current.value.handled)}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function DayTable({ days }: { days: ReportDay[] }) {
  return (
    <table className="report-table">
      <thead>
        <tr><th>Ngày</th><th>Đã khớp</th><th>Chờ tiền về</th><th>Ngoại lệ</th><th>Trong đó đã xử lý</th></tr>
      </thead>
      <tbody>
        {days.map((day) => {
          const value = dayValues(day);
          return (
            <tr key={day.date}>
              <td>{shortDay(day.date)}</td>
              <td>{formatCount(value.matched)}</td>
              <td>{formatCount(value.pending)}</td>
              <td>{formatCount(value.exception)}</td>
              <td>{formatCount(value.handled)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** "1250000.00" → "1.250.000 đ" */
export const money = (value: string) => `${formatMoney(value)} đ`;

/** 96.5 → "96,5%"; chưa có gì cần đối chiếu thì "—". */
export const percent = (value: number | null) =>
  value === null ? "—" : `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 }).format(value)}%`;
