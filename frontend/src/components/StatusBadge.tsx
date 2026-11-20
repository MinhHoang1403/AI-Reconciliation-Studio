import type { DatasetStatus, TableStatus } from "../api";

// Nhãn trạng thái đọc tệp. Màu theo quy tắc mệnh giá: xanh lá = xong, cam đỏ = lỗi,
// tím = đang xử lý (màu dành riêng cho bước đang chạy).

const LABELS: Record<DatasetStatus | TableStatus, string> = {
  READING: "Đang đọc",
  READY: "Đã đọc",
  NO_DATA: "Không có bảng",
  FAILED: "Lỗi",
};

export function StatusBadge({ status }: { status: DatasetStatus | TableStatus }) {
  return (
    <span className="badge" data-status={status}>
      {LABELS[status]}
    </span>
  );
}
