import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { getCleanRows, type CleanRows } from "../api";
import { formatCount, formatMoney } from "../format";

// Xem trước bộ dữ liệu sạch: giá trị đã chuẩn hóa (tiền là số, ngày năm-tháng-ngày),
// kèm số dòng gốc để đối chiếu với tệp ban đầu.

const PAGE_SIZE = 50;

export function CleanPreview({ tableId }: { tableId: string }) {
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<CleanRows | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getCleanRows(tableId, offset, PAGE_SIZE, controller.signal)
      .then(setPage)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Lỗi không rõ.");
      });
    return () => controller.abort();
  }, [tableId, offset]);

  if (error) return <p className="notice notice--error" role="alert">{error}</p>;
  if (!page) return null;
  const last = Math.min(page.offset + page.rows.length, page.total);

  return (
    <section className="cleaning__group" aria-labelledby="clean-preview-title">
      <h3 id="clean-preview-title" className="cleaning__title">Dữ liệu sạch</h3>
      <div className="preview">
        <div className="preview__scroll" tabIndex={0} aria-label="Bảng dữ liệu sạch, cuộn ngang để xem thêm cột">
          <table className="preview__table">
            <thead>
              <tr>
                <th scope="col" className="preview__ref">Dòng gốc</th>
                {page.columns.map((column) => (
                  <th key={column.key} scope="col">{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {page.rows.map((row, index) => (
                <tr key={page.row_refs[index]}>
                  <th scope="row" className="preview__ref">{page.row_refs[index]}</th>
                  {row.map((cell, column) => {
                    const money = page.columns[column]?.type === "MONEY";
                    return (
                      <td key={column} data-missing={cell === null || undefined} data-money={money || undefined}>
                        {cell === null ? "—" : money ? formatMoney(cell) : cell}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <nav className="pager" aria-label="Phân trang dữ liệu sạch">
          <span>
            Dòng {formatCount(page.offset + 1)}–{formatCount(last)} / {formatCount(page.total)}
          </span>
          <button className="icon-button" type="button" aria-label="Trang trước" disabled={page.offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            <ChevronLeft aria-hidden="true" size={18} />
          </button>
          <button className="icon-button" type="button" aria-label="Trang sau" disabled={last >= page.total}
            onClick={() => setOffset(offset + PAGE_SIZE)}>
            <ChevronRight aria-hidden="true" size={18} />
          </button>
        </nav>
      </div>
    </section>
  );
}
