import type { WorkspaceSettings as Settings } from "./types";
import { Files, PanelTop, ShieldCheck, UserRound } from "lucide-react";

const roles: Record<string, string> = {
  owner: "Chủ không gian",
  editor: "Có thể chỉnh sửa",
  viewer: "Chỉ xem",
};

/** Present user capabilities and privacy from the API, without operator diagnostics. */
export function WorkspaceSettings({ settings: s, role, tableDensity, onDensityChange }: {
  settings: Settings;
  role: string;
  tableDensity: "comfortable" | "compact";
  onDensityChange: (value: "comfortable" | "compact") => void;
}) {
  const externalAllowed = s.policy.mode === "CLOUD_ALLOWED" && s.policy.allow_external_ai;
  const available = externalAllowed && s.agent_cloud_enabled && s.gemini_configured;
  const exhausted = s.gemini_requests_remaining === 0 || s.ai_task_allowances?.agent?.remaining === 0;
  const aiStatus = !externalAllowed ? "Xử lý trong ứng dụng"
    : exhausted ? "Đã hết lượt hỗ trợ AI"
    : available ? "Có thể yêu cầu AI hỗ trợ" : "Hỗ trợ AI hiện chưa khả dụng";

  return <section className="settings-page" aria-label="Cài đặt">
    <section className="settings-section" aria-labelledby="settings-account">
      <h2 id="settings-account"><UserRound size={18} aria-hidden="true" /> Tài khoản và không gian làm việc</h2>
      <dl className="settings-rows">
        <div><dt>Tài khoản hiện tại</dt><dd>Người dùng trên thiết bị này</dd></div>
        <div><dt>Không gian làm việc</dt><dd>{s.workspace_name}</dd></div>
        <div><dt>Quyền của bạn</dt><dd>{roles[role] || "Chưa xác minh"}</dd></div>
      </dl>
      <p>{role === "viewer"
        ? "Bạn có thể xem dữ liệu, kết quả và bằng chứng trong phạm vi được chia sẻ."
        : role === "owner" || role === "editor"
          ? "Bạn có thể tải tệp và làm việc với dữ liệu trong phạm vi được cấp quyền. Các đề xuất cần phê duyệt vẫn chờ bạn xác nhận."
          : "Hãy kết nối lại để xác minh các thao tác tài khoản có thể thực hiện."}</p>
    </section>
    <section className="settings-section" aria-labelledby="settings-privacy">
      <h2 id="settings-privacy"><ShieldCheck size={18} aria-hidden="true" /> AI và quyền riêng tư</h2>
      <dl className="settings-rows">
        <div><dt>Hỗ trợ AI</dt><dd>{aiStatus}</dd></div>
        <div><dt>Chia sẻ để xử lý</dt><dd>{externalAllowed
          ? "Cho phép sử dụng dịch vụ AI bên ngoài"
          : "Không gửi dữ liệu đến dịch vụ AI bên ngoài"}</dd></div>
      </dl>
      <p>AI giúp bạn hiểu dữ liệu và đề xuất cách xử lý. Số liệu được hệ thống tính toán và kiểm chứng; các quyết định cần xác nhận vẫn do bạn thực hiện.</p>
      <details>
        <summary>Dữ liệu của tôi được sử dụng như thế nào?</summary>
        <p>{externalAllowed
          ? "Khi bạn thực hiện yêu cầu được cho phép, nội dung yêu cầu, cấu trúc dữ liệu và mẫu dữ liệu có giới hạn có thể được gửi tới dịch vụ AI bên ngoài. Tệp gốc được giữ nguyên."
          : "Các tác vụ hiện không được phép gửi dữ liệu tới dịch vụ AI bên ngoài. Bạn vẫn có thể xem dữ liệu, tra cứu kết quả và sử dụng các quy tắc đã được duyệt."}</p>
        <p>Dữ liệu và kết quả đã lưu thuộc không gian làm việc của bạn. Quyền truy cập được kiểm tra khi xem, xử lý hoặc tải kết quả.</p>
      </details>
      {externalAllowed && <p>{available && !exhausted
        ? "Khả năng hỗ trợ tùy thuộc vào yêu cầu và lượt sử dụng còn lại. Nếu chưa thể xử lý, ứng dụng sẽ hướng dẫn bạn bước tiếp theo."
        : "Bạn vẫn có thể xem kết quả đã lưu và thao tác với dữ liệu theo quyền của mình. Liên hệ người quản lý không gian làm việc nếu cần hỗ trợ AI."}</p>}
      <details>
        <summary>Chi tiết chính sách AI</summary>
        <dl className="settings-rows">
          <div><dt>Xử lý tài liệu bên ngoài</dt><dd>{externalAllowed && s.policy.allow_cloud_parsing ? "Chính sách cho phép" : "Chính sách không cho phép"}</dd></div>
          <div><dt>Thay đổi chính sách</dt><dd>Liên hệ người quản lý không gian làm việc</dd></div>
        </dl>
        <p>Chính sách áp dụng cho cả không gian làm việc.</p>
      </details>
    </section>
    <section className="settings-section" aria-labelledby="settings-limits">
      <h2 id="settings-limits"><Files size={18} aria-hidden="true" /> Tệp bạn có thể tải lên</h2>
      <dl className="settings-rows">
        <div><dt>Định dạng tệp</dt><dd>{s.agent_upload_extensions?.map(ext => ext.slice(1).toUpperCase()).join(", ") || "Chưa có thông tin"}</dd></div>
        <div><dt>Dung lượng tối đa mỗi tệp</dt><dd>{(s.max_upload_bytes / 1048576).toLocaleString("vi-VN")} MB</dd></div>
        <div><dt>Đính kèm mỗi lần gửi</dt><dd>{s.agent_max_upload_files == null ? "Chưa có thông tin" : `${s.agent_max_upload_files} tệp mỗi lần`}</dd></div>
        <div><dt>Số dòng tối đa mỗi bảng</dt><dd>{s.max_rows.toLocaleString("vi-VN")} dòng</dd></div>
      </dl>
      <p>Các giới hạn trên áp dụng khi đính kèm tệp trong hội thoại. Ứng dụng sẽ thông báo khi tệp vượt giới hạn hoặc cần bạn kiểm tra lại.</p>
    </section>
    <section className="settings-section" aria-labelledby="settings-display">
      <h2 id="settings-display"><PanelTop size={18} aria-hidden="true" /> Hiển thị</h2>
      <fieldset className="density-preference">
        <legend>Mật độ bảng</legend>
        <label><input type="radio" name="table-density" checked={tableDensity === "comfortable"} onChange={() => onDensityChange("comfortable")} /> Tiêu chuẩn</label>
        <label><input type="radio" name="table-density" checked={tableDensity === "compact"} onChange={() => onDensityChange("compact")} /> Gọn</label>
      </fieldset>
      <p>Lưu trên trình duyệt này. Màn hình nhỏ giữ khoảng cách phù hợp để chạm.</p>
    </section>
  </section>;
}
