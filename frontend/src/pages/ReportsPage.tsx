import { PlannedPage } from "../components/PlannedPage";

export function ReportsPage() {
  return (
    <PlannedPage
      title="Báo cáo"
      summary="KPI, biểu đồ và nhận xét về kết quả đối soát."
      capabilities={[
        "Tỷ lệ khớp theo số dòng và theo giá trị tiền",
        "Biểu đồ theo loại kết quả, theo ngày và theo nguồn",
        "Xuất kết quả ra CSV và Excel",
      ]}
    />
  );
}
