import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { getRows, type RowsPage } from "../api";
import { formatCount } from "../format";

// Xem trước các dòng của một bảng, có phân trang. Cột đầu là số dòng trong tệp gốc,
// để người dùng mở tệp gốc và tìm đúng dòng đó.

const PAGE_SIZE = 50;

export function TablePreview({ tableId }: { tableId: string }) {
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<RowsPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getRows(tableId, offset, PAGE_SIZE, controller.signal)
      .then((data) => {
        setPage(data);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Lỗi không rõ.");
      });
    return () => controller.abort();
  }, [tableId, offset]);

  if (error) return <p className="notice notice--error" role="alert">{error}</p>;
  if (!page) return <p className="notice">Đang tải dữ liệu…</p>;

  const last = Math.min(page.offset + page.rows.length, page.total);
  return (
    <div className="preview">
      <div className="preview__scroll" tabIndex={0} aria-label="Bảng dữ liệu, cuộn ngang để xem thêm cột">
        <table className="preview__table">
          <thead>
            <tr>
              <th scope="col" className="preview__ref">Dòng gốc</th>
              {page.columns.map((column) => (
                <th key={column} scope="col">{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {page.rows.map((row, index) => (
              <tr key={page.row_refs[index]}>
                <th scope="row" className="preview__ref">{page.row_refs[index]}</th>
                {row.map((cell, column) => (
                  <td key={column}>{cell ?? ""}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <nav className="pager" aria-label="Phân trang">
        <span>
          Dòng {formatCount(page.offset + 1)}–{formatCount(last)} / {formatCount(page.total)}
        </span>
        <button
          className="icon-button"
          type="button"
          aria-label="Trang trước"
          disabled={page.offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        >
          <ChevronLeft aria-hidden="true" size={18} />
        </button>
        <button
          className="icon-button"
          type="button"
          aria-label="Trang sau"
          disabled={last >= page.total}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          <ChevronRight aria-hidden="true" size={18} />
        </button>
      </nav>
    </div>
  );
}
