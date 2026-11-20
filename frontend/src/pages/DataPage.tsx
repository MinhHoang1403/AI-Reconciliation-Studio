import { DatasetList } from "../components/DatasetList";
import { UploadZone } from "../components/UploadZone";
import { useDatasetList } from "../useDatasets";

// Trang Dữ liệu: tải tệp và danh sách các bộ dữ liệu đã tải.

export function DataPage() {
  const { state, refresh } = useDatasetList();

  return (
    <div className="data-page">
      <header className="page__header">
        <h1>Dữ liệu</h1>
        <p>Tải tệp đơn hàng, thanh toán, sao kê. Hệ thống giữ nguyên tệp gốc và đọc từng bảng để bạn kiểm tra.</p>
      </header>
      <UploadZone onUploaded={refresh} />
      {state.kind === "loading" && <p className="notice">Đang tải danh sách…</p>}
      {state.kind === "error" && (
        <p className="notice notice--error" role="alert">
          Không tải được danh sách: {state.message}
        </p>
      )}
      {state.kind === "ready" && <DatasetList datasets={state.data} onChanged={refresh} />}
    </div>
  );
}
