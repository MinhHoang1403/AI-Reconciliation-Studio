import { useEffect, useState } from "react";
import { Link2 } from "lucide-react";

import { getMatchCandidates, manualMatch, type MatchCandidates, type ReconResult, type ResultRow } from "../api";
import { formatMoney } from "../format";

// Ghép tay một dòng "chỉ có ở một bên" với các dòng chưa ghép ở bên kia. Hệ thống chỉ xếp
// ứng viên gần số tiền nhất lên trước; người dùng tích một hoặc vài dòng (ví dụ một lần chuyển
// khoản trả cho hai đơn) rồi bấm ghép. Ghép xong hệ thống chạy lại đối soát.

type Props = {
  runId: string;
  item: ReconResult;
  onDone: (target: { chain_id: string | null; run_id: string | null }) => void;
  onCancel: () => void;
};

const day = (iso?: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "");
const label = (row: ResultRow) => row.key ?? row.description ?? `Dòng ${row.row_ref}`;

export function MatchPicker({ runId, item, onDone, onCancel }: Props) {
  const [data, setData] = useState<MatchCandidates | null>(null);
  const [chosen, setChosen] = useState<Set<number>>(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getMatchCandidates(item.id, controller.signal)
      .then(setData)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Không tải được ứng viên.");
      });
    return () => controller.abort();
  }, [item.id]);

  const picked = data?.candidates.filter((candidate) => chosen.has(candidate.row.row_ref)) ?? [];
  const total = picked.reduce((sum, candidate) => sum + Number(candidate.row.amount ?? 0), 0);
  const target = Number(data?.target.amount ?? 0);
  const gap = total - target;

  function toggle(ref: number) {
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(ref)) next.delete(ref);
      else next.add(ref);
      return next;
    });
  }

  async function save() {
    if (!data) return;
    setSaving(true);
    try {
      const own = data.target.row_ref;
      const others = picked.map((candidate) => candidate.row.row_ref);
      const [left, right] = data.side === "B" ? [[own], others] : [others, [own]];
      onDone(await manualMatch(runId, left, right));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không ghép được.");
      setSaving(false);
    }
  }

  return (
    <fieldset className="match-picker" disabled={saving}>
      <legend>Ghép tay với dòng chưa ghép ở {data?.side_label ?? "bảng kia"}</legend>
      {error && <p className="result__error">{error}</p>}
      {!data && !error && <p className="match-picker__hint">Đang tìm dòng chưa ghép…</p>}
      {data && data.candidates.length === 0 && (
        <p className="match-picker__hint">{data.side_label} không còn dòng nào chưa ghép.</p>
      )}
      {data && data.candidates.length > 0 && (
        <>
          <p className="match-picker__hint">Gần số tiền {formatMoney(data.target.amount ?? "0")}đ nhất xếp trước.</p>
          <ul className="match-picker__list">
            {data.candidates.map((candidate) => (
              <li key={candidate.result_id}>
                <label>
                  <input
                    type="checkbox"
                    checked={chosen.has(candidate.row.row_ref)}
                    onChange={() => toggle(candidate.row.row_ref)}
                  />
                  <span className="match-picker__key">{label(candidate.row)}</span>
                  <span className="match-picker__amount">
                    {candidate.row.amount ? `${formatMoney(candidate.row.amount)}đ` : "—"}
                  </span>
                  <span className="match-picker__meta">
                    Dòng {candidate.row.row_ref}
                    {candidate.row.date && ` · ${day(candidate.row.date)}`}
                    {candidate.amount_gap !== null &&
                      (Number(candidate.amount_gap) === 0 ? " · đúng số tiền" : ` · lệch ${formatMoney(candidate.amount_gap)}đ`)}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <div className="match-picker__actions">
            <span className="match-picker__sum" aria-live="polite">
              {picked.length === 0
                ? "Chưa chọn dòng nào"
                : `Đã chọn ${picked.length} dòng · tổng ${formatMoney(String(total))}đ` +
                  (gap === 0 ? " · khớp đúng" : ` · lệch ${formatMoney(String(Math.abs(gap)))}đ`)}
            </span>
            <button className="button button--quiet" type="button" onClick={onCancel}>Hủy</button>
            <button className="button button--primary" type="button" disabled={picked.length === 0} onClick={() => void save()}>
              <Link2 aria-hidden="true" size={16} />
              {saving ? "Đang ghép và đối soát lại…" : `Ghép ${picked.length || ""} dòng`.replace("  ", " ")}
            </button>
          </div>
        </>
      )}
    </fieldset>
  );
}
