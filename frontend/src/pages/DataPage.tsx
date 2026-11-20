import { PlannedPage } from "../components/PlannedPage";

export function DataPage() {
  return (
    <PlannedPage
      title="Dữ liệu"
      summary="Tải tệp, ánh xạ cột chuẩn, chuẩn hóa và làm sạch dữ liệu trước khi đối soát."
      capabilities={[
        "Tải tệp CSV và Excel, tối thiểu 100.000 dòng mỗi tệp",
        "Gợi ý cột nào là mã đơn, số tiền, ngày… và chờ bạn xác nhận chỗ chưa chắc",
        "Tự sửa lỗi định dạng, chỉ ra đúng ô cần bạn xử lý",
      ]}
    />
  );
}
