import { useCallback, useEffect, useState } from "react";

import { getDataset, listDatasets, type DatasetSummary } from "./api";

// Tự hỏi lại backend định kỳ khi còn bộ dữ liệu đang được đọc, để giao diện cập nhật trạng thái.
const POLL_MS = 1200;

const isBusy = (dataset: DatasetSummary) =>
  dataset.status === "READING" || dataset.tables.some((table) => table.status === "READING");

export type Loaded<T> = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: T };

/** Danh sách bộ dữ liệu, tự làm mới khi có bộ đang đọc. */
export function useDatasetList() {
  const [state, setState] = useState<Loaded<DatasetSummary[]>>({ kind: "loading" });
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    listDatasets(controller.signal)
      .then((data) => setState({ kind: "ready", data }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({ kind: "error", message: error instanceof Error ? error.message : "Lỗi không rõ." });
        }
      });
    return () => controller.abort();
  }, [version]);

  const busy = state.kind === "ready" && state.data.some(isBusy);
  useEffect(() => {
    if (!busy) return;
    const timer = window.setTimeout(refresh, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [busy, state, refresh]);

  return { state, refresh };
}

/** Một bộ dữ liệu, tự làm mới khi đang đọc. */
export function useDataset(id: string) {
  const [state, setState] = useState<Loaded<DatasetSummary>>({ kind: "loading" });
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    getDataset(id, controller.signal)
      .then((data) => setState({ kind: "ready", data }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({ kind: "error", message: error instanceof Error ? error.message : "Lỗi không rõ." });
        }
      });
    return () => controller.abort();
  }, [id, version]);

  const busy = state.kind === "ready" && isBusy(state.data);
  useEffect(() => {
    if (!busy) return;
    const timer = window.setTimeout(refresh, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [busy, state, refresh]);

  return { state, refresh };
}
