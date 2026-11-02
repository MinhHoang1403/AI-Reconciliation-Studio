import type { WorkspaceSettings as Settings } from "./types";

const roles: Record<string, string> = {
  owner: "Chủ không gian", editor: "Có thể chỉnh sửa", viewer: "Chỉ xem",
};

/** Chỉ trình bày quyền và giới hạn từ API; cấu hình không chứng minh model đang kết nối. */
export function WorkspaceSettings({ settings: s, role }: { settings: Settings; role: string }) {
  const allowed = s.policy.mode === "CLOUD_ALLOWED" && s.policy.allow_external_ai;
  const permitted = s.agent_cloud_enabled && s.gemini_configured;
  const remaining = Number.isFinite(s.gemini_requests_remaining) ? s.gemini_requests_remaining : null;
  const aiStatus = !allowed ? "Chưa bật AI bên ngoài"
    : !s.gemini_configured ? "Chưa cấu hình dịch vụ AI"
    : remaining === 0 ? "Đã hết lượt sử dụng AI"
    : permitted ? "Được phép hỗ trợ tác vụ dữ liệu" : "Tác vụ AI chưa được cấp quyền";
  return <section className="settings-page" aria-label="Cài đặt">
    <section className="settings-section" aria-labelledby="settings-account">
      <h2 id="settings-account">Tài khoản và không gian làm việc</h2>
      <dl className="settings-rows">
        <div><dt>Tài khoản hiện tại</dt><dd>Người dùng local</dd></div>
        <div><dt>Không gian làm việc</dt><dd>{s.workspace_name}</dd></div>
        <div><dt>Quyền của bạn</dt><dd>{roles[role] || "Chưa xác minh"}</dd></div>
      </dl>
    </section>
    <section className="settings-section" aria-labelledby="settings-privacy">
      <h2 id="settings-privacy">AI và quyền riêng tư dữ liệu</h2>
      <p>AI hỗ trợ chuẩn bị dữ liệu, đối soát, tra cứu và giải thích kết quả. Hệ thống tính toán số liệu và kiểm chứng kết quả đối soát.</p>
      <dl className="settings-rows">
        <div><dt>Hỗ trợ AI</dt><dd>{aiStatus}</dd></div>
        <div><dt>Kết nối dịch vụ AI</dt><dd>{s.cloud_live_status === "VERIFIED" ? "Đã được kiểm tra" : "Chưa kiểm tra trực tiếp"}</dd></div>
        <div><dt>Xử lý dữ liệu</dt><dd>{allowed ? "Có thể sử dụng dịch vụ AI bên ngoài" : "Xử lý nội bộ theo chính sách hiện tại"}</dd></div>
      </dl>
      <p>{allowed
        ? "Khi tác vụ được cấp quyền và còn lượt sử dụng, nội dung yêu cầu, cấu trúc dữ liệu và mẫu có giới hạn có thể được gửi tới dịch vụ AI bên ngoài. Tệp gốc được giữ nguyên."
        : "Tác vụ không được phép gửi dữ liệu tới dịch vụ AI bên ngoài. Bạn vẫn có thể xem dữ liệu, dùng quy tắc đã duyệt và thao tác thủ công."}</p>
      <p>Các quyết định mới về ý nghĩa dữ liệu và quy tắc đối soát cần bạn xác nhận. Quyền sử dụng và cấu hình AI được kiểm tra lại khi thực hiện; kết nối ứng dụng không xác nhận kết nối AI.</p>
      {!permitted && <p>Tra cứu theo dữ kiện, quy tắc đã duyệt và công cụ thủ công vẫn sử dụng được trong phạm vi dữ liệu và quyền của bạn.</p>}
    </section>
    <section className="settings-section" aria-labelledby="settings-limits">
      <h2 id="settings-limits">Giới hạn sử dụng</h2>
      <dl className="settings-rows">
        <div><dt>Dung lượng mỗi tệp</dt><dd>{(s.max_upload_bytes / 1048576).toLocaleString("vi-VN")} MB</dd></div>
        <div><dt>Đính kèm trong hội thoại</dt><dd>{s.agent_max_upload_files == null ? "Chưa có thông tin" : `${s.agent_max_upload_files} tệp mỗi lần`}</dd></div>
        <div><dt>Định dạng trong hội thoại</dt><dd>{s.agent_upload_extensions?.map(ext => ext.slice(1).toUpperCase()).join(", ") || "Chưa có thông tin"}</dd></div>
        <div><dt>Số dòng mỗi bảng</dt><dd>{s.max_rows.toLocaleString("vi-VN")} dòng</dd></div>
      </dl>
    </section>
    {role === "owner" && <details className="settings-advanced settings-section">
      <summary>Thông tin nâng cao</summary>
      <p>Thông tin chỉ đọc dành cho chủ không gian khi cần kiểm tra hoặc liên hệ hỗ trợ.</p>
      <dl className="settings-rows">
        <div><dt>Dịch vụ đề xuất ánh xạ</dt><dd>{s.mapping_ai_provider === "GEMINI" ? "Gemini" : "Qwen"}</dd></div>
        <div><dt>Model Gemini</dt><dd>{s.gemini_configured ? s.gemini_model : "Chưa cấu hình"}</dd></div>
        <div><dt>Lượt AI đã ghi nhận</dt><dd>{Number.isFinite(s.gemini_requests_used) ? s.gemini_requests_used.toLocaleString("vi-VN") : "Chưa có thông tin"}</dd></div>
        <div><dt>Lượt AI còn trong hạn mức chung</dt><dd>{remaining === null ? "Chưa xác minh" : remaining.toLocaleString("vi-VN")}</dd></div>
        <div><dt>Tác vụ hội thoại</dt><dd>{s.agent_cloud_enabled ? "Có quyền theo chính sách" : "Chưa khả dụng theo chính sách hoặc hạn mức"}</dd></div>
        <div><dt>Hỏi dữ kiện qua AI bên ngoài</dt><dd>{s.assistant_cloud_enabled ? "Có quyền theo chính sách" : "Chưa khả dụng"}</dd></div>
        <div><dt>Qwen</dt><dd>{s.qwen_configured ? `Đã cấu hình · ${s.qwen_model} · kết nối chưa xác minh` : "Chưa cấu hình"}</dd></div>
        <div><dt>Trích xuất tài liệu bên ngoài</dt><dd>{s.policy.allow_cloud_parsing ? "Workspace có quyền; mỗi tác vụ cần kiểm tra riêng" : "Workspace chưa cho phép tạo tác vụ"}</dd></div>
        <div><dt>Tải qua công cụ thủ công</dt><dd>{s.max_upload_files} tệp mỗi lần</dd></div>
      </dl>
      <p>Hạn mức chung không đảm bảo còn lượt cho từng tác vụ. Mỗi yêu cầu đã gửi đều được ghi nhận, kể cả lỗi hoặc chưa rõ dịch vụ đã nhận; không tự gửi lại khi chưa xác định.</p>
    </details>}
  </section>;
}
