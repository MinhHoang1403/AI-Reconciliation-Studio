import { Files, FolderOpen, PanelTop, ShieldCheck, UserRound } from "lucide-react";
import type { WorkspaceSettings as Settings } from "./types";
import { PermanentDeletion } from "./PermanentDeletion";

const roles: Record<string, string> = {
  owner: "Chủ không gian",
  editor: "Có thể chỉnh sửa",
  viewer: "Chỉ xem",
};

export function WorkspaceSettings({ settings: s, role, tableDensity, onDensityChange, onManageProjects }: {
  settings: Settings;
  role: string;
  tableDensity: "comfortable" | "compact";
  onDensityChange: (value: "comfortable" | "compact") => void;
  onManageProjects?: (trigger: HTMLButtonElement) => void;
}) {
  const external = s.policy.mode === "CLOUD_ALLOWED" && s.policy.allow_external_ai;
  const available = external && s.agent_cloud_enabled && s.gemini_configured
    && s.gemini_requests_remaining !== 0 && s.ai_task_allowances?.agent?.remaining !== 0;

  return <section className="settings-page settings-register" aria-label="Cài đặt">
    <section aria-labelledby="settings-account">
      <h2 id="settings-account"><UserRound size={18} aria-hidden="true" /> Tài khoản và không gian làm việc</h2>
      <dl className="settings-rows">
        <div><dt>Không gian làm việc</dt><dd>{s.workspace_name}</dd></div>
        <div><dt>Quyền của bạn</dt><dd>{roles[role] ?? "Chưa xác minh"}</dd></div>
      </dl>
      {onManageProjects && <button className="text-button" onClick={event => onManageProjects(event.currentTarget)}><FolderOpen size={17} /> Quản lý dự án</button>}
      {role === "owner" && <PermanentDeletion kind="workspace" />}
    </section>
    <section aria-labelledby="settings-privacy">
      <h2 id="settings-privacy"><ShieldCheck size={18} aria-hidden="true" /> AI và quyền riêng tư</h2>
      <dl className="settings-rows">
        <div><dt>Hỗ trợ AI</dt><dd>{available ? "Có thể yêu cầu AI hỗ trợ" : external ? "AI tạm thời chưa thể hỗ trợ" : "Xử lý trong ứng dụng"}</dd></div>
        <div><dt>Chia sẻ dữ liệu</dt><dd>{external ? "Cho phép sử dụng dịch vụ AI bên ngoài" : "Không gửi dữ liệu đến dịch vụ AI bên ngoài"}</dd></div>
      </dl>
      {external && !available && <p>Vẫn có thể xem dữ liệu và tiếp tục thiết lập thủ công.</p>}
      <details>
        <summary>Dữ liệu nào được sử dụng?</summary>
        <p>{external ? "Yêu cầu, cấu trúc bảng và một phần nhỏ dữ liệu có thể được gửi đi khi cần xử lý. Tệp gốc được giữ trong không gian làm việc."
          : "Dữ liệu được giữ trong không gian làm việc. Quyền được kiểm tra khi xem, xử lý hoặc tải kết quả."}</p>
        <p>{external && s.policy.allow_cloud_parsing ? "Chính sách cho phép đọc tài liệu bằng dịch vụ bên ngoài." : "Tài liệu không được gửi đến dịch vụ bên ngoài để đọc."}</p>
      </details>
    </section>
    <section aria-labelledby="settings-display">
      <h2 id="settings-display"><PanelTop size={18} aria-hidden="true" /> Hiển thị</h2>
      <fieldset className="density-preference">
        <legend>Mật độ bảng trên màn hình rộng</legend>
        <label><input type="radio" name="table-density" checked={tableDensity === "comfortable"} onChange={() => onDensityChange("comfortable")} /> Tiêu chuẩn</label>
        <label><input type="radio" name="table-density" checked={tableDensity === "compact"} onChange={() => onDensityChange("compact")} /> Gọn</label>
      </fieldset>
    </section>
    <section aria-labelledby="settings-limits">
      <h2 id="settings-limits"><Files size={18} aria-hidden="true" /> Tệp đính kèm</h2>
      <dl className="settings-rows">
        <div><dt>Định dạng</dt><dd>{s.agent_upload_extensions?.map(ext => ext.slice(1).toUpperCase()).join(", ") || "Chưa có thông tin"}</dd></div>
        <div><dt>Dung lượng tối đa</dt><dd>{(s.max_upload_bytes / 1048576).toLocaleString("vi-VN")} MB mỗi tệp</dd></div>
        <div><dt>Số tệp đính kèm</dt><dd>{s.agent_max_upload_files == null ? "Chưa có thông tin" : `${s.agent_max_upload_files} tệp mỗi lần`}</dd></div>
        <div><dt>Số dòng tối đa mỗi bảng</dt><dd>{s.max_rows.toLocaleString("vi-VN")} dòng</dd></div>
      </dl>
    </section>
  </section>;
}
