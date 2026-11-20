import { PlannedPage } from "../components/PlannedPage";

export function AssistantPage() {
  return (
    <PlannedPage
      title="Assistant"
      summary="Trò chuyện bằng tiếng Việt để kiểm tra dữ liệu, chạy đối soát và nhận báo cáo."
      capabilities={[
        "Hiểu câu hỏi và chạy đúng bước xử lý cho bạn",
        "Giải thích vì sao một dòng bị thiếu, lệch hay thừa",
        "Hỏi bạn xác nhận trước mọi thay đổi trên dữ liệu",
      ]}
    />
  );
}
