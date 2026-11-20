import { useEffect, useState } from "react";

import { fetchSystemStatus, type SystemStatus } from "../api";

// Bảng trạng thái hệ thống: cơ sở dữ liệu, cấu hình Gemini, phiên bản đang chạy.
// Chỉ đọc cấu hình từ backend, không gọi Gemini (RULES R11).

type Load = { kind: "loading" } | { kind: "error" } | { kind: "ready"; status: SystemStatus };

export function SystemStatusPanel() {
  const [load, setLoad] = useState<Load>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetchSystemStatus(controller.signal)
      .then((status) => setLoad({ kind: "ready", status }))
      .catch(() => {
        if (!controller.signal.aborted) setLoad({ kind: "error" });
      });
    return () => controller.abort();
  }, []);

  return (
    <section className="status" aria-labelledby="status-title" aria-busy={load.kind === "loading"}>
      <h2 id="status-title">Trạng thái hệ thống</h2>
      {load.kind === "loading" && <p className="status__note">Đang kiểm tra…</p>}
      {load.kind === "error" && (
        <p className="status__note status__note--bad">
          Không liên lạc được với backend. Kiểm tra Docker đang chạy rồi tải lại trang.
        </p>
      )}
      {load.kind === "ready" && (
        <dl className="status__list">
          <div>
            <dt>Cơ sở dữ liệu</dt>
            <dd data-state={load.status.database === "ok" ? "good" : "bad"}>
              {load.status.database === "ok" ? "Hoạt động" : "Không kết nối được"}
            </dd>
          </div>
          <div>
            <dt>{load.status.gemini.name}</dt>
            <dd data-state={load.status.gemini.state === "CONFIGURED" ? "good" : "bad"}>
              {load.status.gemini.state === "CONFIGURED"
                ? `Đã cấu hình · ${load.status.gemini.model}`
                : "Chưa có khóa GEMINI_API_KEY trong .env"}
            </dd>
          </div>
          <div>
            <dt>Phiên bản</dt>
            <dd className="status__mono">
              {load.status.revision.slice(0, 7)}
              {load.status.revision.endsWith("-dirty") && " · có thay đổi chưa commit"}
            </dd>
          </div>
        </dl>
      )}
    </section>
  );
}
