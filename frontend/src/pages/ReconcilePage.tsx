import { PlannedPage } from "../components/PlannedPage";

export function ReconcilePage() {
  return (
    <PlannedPage
      title="Đối soát"
      summary="Ghép từng dòng giữa hai bộ dữ liệu sạch và phân loại kết quả."
      capabilities={[
        "Đề xuất các trường dùng để ghép và sai số cho phép",
        "Phân loại khớp, lệch tiền, thiếu, thừa, ghép nhóm và ca mơ hồ",
        "Hiện lý do của từng kết quả và kiểm chứng lại sau mỗi lần chạy",
      ]}
    />
  );
}
