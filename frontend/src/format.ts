// Định dạng số, dung lượng và thời gian theo kiểu Việt Nam.

const numberFormat = new Intl.NumberFormat("vi-VN");
const dateFormat = new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" });

/** 100000 → "100.000" */
export const formatCount = (value: number) => numberFormat.format(value);

/** Dung lượng tệp: 16360 → "16 KB", 7400000 → "7,1 MB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${numberFormat.format(Math.round(bytes / 1024))} KB`;
  return `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 }).format(bytes / 1024 / 1024)} MB`;
}

export const formatDateTime = (iso: string) => dateFormat.format(new Date(iso));

/** Số tiền dạng chuỗi số ("2195000.00") → "2.195.000" (giữ phần lẻ nếu có, ví dụ "1.250,50"). */
export function formatMoney(value: string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return value;
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(amount);
}
