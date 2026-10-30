import { useEffect, useRef, useState, type RefObject } from "react";
import { api } from "./api";
import { Modal, Notice, Spinner } from "./components";
import {
  label,
  type Case,
  type EvidenceRef,
  type SourceEvidence,
} from "./reconciliationTypes";

/** Scoped evidence UI: read original cells and review workflow; never alter run results. */
export function ReconciliationEvidence({
  evidence,
  currentCase,
  onClose,
  onReviewed,
  returnFocus,
  canEdit,
}: {
  evidence: SourceEvidence;
  canEdit: boolean;
  currentCase: Case | null;
  onClose: () => void;
  onReviewed: () => Promise<void>;
  returnFocus: RefObject<HTMLElement | null>;
}) {
  const [sourceDetail, setSourceDetail] = useState<{
    field: string;
    filename: string;
    canonical: unknown;
    cells: { ref: EvidenceRef; name: string; value: unknown }[];
    limited: boolean;
  } | null>(null);
  const [note, setNote] = useState(currentCase?.notes || "");
  const [state, setState] = useState(
    currentCase?.workflow_state || "IN_REVIEW",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const alive = useRef(true);
  const controller = useRef(new AbortController());
  const sourceSequence = useRef(0);
  useEffect(() => {
    alive.current = true;
    controller.current = new AbortController();
    return () => {
      alive.current = false;
      controller.current.abort();
    };
  }, []);
  async function action(task: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await task();
    } catch (err) {
      if (alive.current)
        setError(
          err instanceof Error ? err.message : "Không tải được bằng chứng.",
        );
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  const openSource = (
    field: string,
    filename: string,
    canonical: unknown,
    refs: EvidenceRef[],
  ) =>
    action(async () => {
      const request = ++sourceSequence.current;
      const cells = await Promise.all(
        refs.slice(0, 20).map(async (ref) => {
          const data = await api<{
            column: { name: string };
            items: Record<string, unknown>[];
          }>(`/evidence/${encodeURIComponent(ref.id)}?row=${ref.row}`, {
            signal: controller.current.signal,
          });
          return {
            ref,
            name: data.column.name,
            value: data.items[0]?.[ref.column],
          };
        }),
      );
      if (alive.current && request === sourceSequence.current)
        setSourceDetail({
          field,
          filename,
          canonical,
          cells,
          limited: refs.length > 20,
        });
    });
  return (
    <Modal
      title={currentCase ? "Xem xét ngoại lệ" : "Bằng chứng đối soát"}
      open={!!evidence}
      onOpenChange={(open) => !open && onClose()}
      wide
      returnFocus={returnFocus}
    >
      {error && <Notice tone="error">{error}</Notice>}
      {busy && <Spinner />}
      {evidence && (
        <>
          <p>
            {evidence.group.key.join(" / ")} ·{" "}
            {label(evidence.group.linkage_state)} ·{" "}
            {label(evidence.group.comparison_state)}
          </p>
          {evidence.group.comparisons.map((c) => (
            <Notice key={c.metric_id}>
              {c.metric_id}: {c.left_amount ?? "N/A"} −{" "}
              {c.right_amount ?? "N/A"} = {c.delta ?? "N/A"} {c.currency}
            </Notice>
          ))}
          <div className="evidence-sides">
            {evidence.sources.map((source, i) => (
              <section key={source.canonical.id}>
                <h3>
                  Nguồn {i === 0 ? "trái" : "phải"} · {source.filename}
                </h3>
                <p>{source.member_count} thành viên nguồn</p>
                <details>
                  <summary>Phiên bản dữ liệu dùng so sánh</summary>
                  <p>Canonical: {source.canonical.id}</p>
                  <p>
                    Ánh xạ:{" "}
                    {source.canonical.mapping_revision_id ||
                      "Không có trong phản hồi"}
                  </p>
                </details>
                {source.records.map((r) => (
                  <article className="evidence-record" key={r.id}>
                    <dl>
                      {Object.entries(r.payload).map(([k, v]) => (
                        <div key={k}>
                          <dt>{k}</dt>
                          <dd>
                            {v === null ? "NULL" : String(v)}{" "}
                            {r.field_evidence[k]?.length > 0 && (
                              <button
                                className="text-button"
                                disabled={busy}
                                onClick={() =>
                                  void openSource(
                                    k,
                                    source.filename,
                                    v,
                                    r.field_evidence[k],
                                  )
                                }
                              >
                                Xem nguồn {k}
                              </button>
                            )}
                          </dd>
                        </div>
                      ))}
                    </dl>
                    {r.provenance.map((p, j) => (
                      <p key={j}>
                        {p.sheet}, dòng {p.row}
                      </p>
                    ))}
                    {!r.field_evidence_complete && (
                      <Notice>
                        Hiển thị bằng chứng trường cho 100 dòng gốc đầu; file
                        báo cáo giữ lineage đầy đủ.
                      </Notice>
                    )}
                  </article>
                ))}
                {!source.evidence_complete && (
                  <Notice tone="warning">
                    Đang hiển thị 100 thành viên đầu. Báo cáo chứa đầy đủ
                    lineage.
                  </Notice>
                )}
              </section>
            ))}
          </div>
          {sourceDetail && (
            <section aria-label="Chi tiết giá trị nguồn" className="card">
              <h3>
                {sourceDetail.filename} · {sourceDetail.field}
              </h3>
              <p>
                Giá trị chuẩn hóa dùng so sánh:{" "}
                {sourceDetail.canonical === null
                  ? "NULL"
                  : String(sourceDetail.canonical)}
                . Dòng gốc bên dưới được đọc từ artifact nguồn; phép biến đổi
                theo mapping đã duyệt.
              </p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Sheet</th>
                      <th>Dòng</th>
                      <th>Cột nguồn</th>
                      <th>Giá trị gốc</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sourceDetail.cells.map((c, i) => (
                      <tr key={i}>
                        <td>{c.ref.sheet}</td>
                        <td>{c.ref.row}</td>
                        <td>
                          {c.name} ({c.ref.column})
                        </td>
                        <td>
                          {c.value === null
                            ? "NULL"
                            : String(c.value ?? "Không tìm thấy dòng")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {sourceDetail.limited && (
                <Notice>
                  Hiển thị 20 ô gốc đầu; xem file báo cáo để có đầy đủ lineage.
                </Notice>
              )}
            </section>
          )}
          <details>
            <summary>Quy tắc áp dụng</summary>
            <p>
              {evidence.rule.plan.name} · {evidence.rule.plan.cardinality} ·{" "}
              {evidence.rule.plan.aggregation}
            </p>
            <p>
              {evidence.rule.plan.effective_from} đến{" "}
              {evidence.rule.plan.effective_to || "không giới hạn"}
            </p>
          </details>
          {evidence.group.candidates.length > 0 && (
            <Notice tone="warning">
              Ứng viên fuzzy chỉ để review, score là độ tương tự, không phải xác
              suất. Không tự ghép hoặc sửa tiền.
            </Notice>
          )}
          {currentCase && (
            <div className="rule-approval">
              <p className="muted">
                Trạng thái xử lý chỉ ghi nhận việc xem xét; không đổi kết quả so
                sánh hoặc số tiền của lần đối soát.
              </p>
              <label>
                Trạng thái xử lý
                <select
                  value={state}
                  onChange={(e) => setState(e.target.value)}
                >
                  {[
                    "OPEN",
                    "IN_REVIEW",
                    "RESOLVED",
                    "DISMISSED_WITH_REASON",
                  ].map((s) => (
                    <option key={s} value={s}>
                      {label(s)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Lý do / ghi chú
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
              </label>
              <button
                className="button primary"
                disabled={busy || !canEdit}
                onClick={() =>
                  void action(async () => {
                    await api(`/exceptions/${currentCase.id}/review`, {
                      method: "PATCH",
                      body: JSON.stringify({
                        workflow_state: state,
                        notes: note,
                      }),
                    });
                    await onReviewed();
                  })
                }
              >
                Lưu xem xét
              </button>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
