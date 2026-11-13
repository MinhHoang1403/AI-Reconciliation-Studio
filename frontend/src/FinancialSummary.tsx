import { formatDecimal, sourceDisplayName } from "./components";
import { label, type Snapshot } from "./reconciliationTypes";

const states: Record<string, string> = {
  MATCHED: "Khớp", AMOUNT_MISMATCH: "Lệch tiền", ONE_SIDED: "Một phía có giao dịch",
  DUPLICATE: "Mã trùng", NOT_COMPARABLE: "Chưa đủ điều kiện so sánh",
};
const number = (value: number) => value.toLocaleString("vi-VN");

export function FinancialSummary({ snapshot, names, metricName = label }: {
  snapshot: Snapshot;
  names?: string[];
  metricName?: (metric: string) => string;
}) {
  const measures = snapshot.financial;
  if (!measures?.length) return <p className="muted">Lượt này chưa lưu tổng tiền theo từng phía và trạng thái.</p>;
  const left = names?.[0] || "Nguồn tham chiếu";
  const right = names?.[1] || "Nguồn đối ứng";
  return <div className="agent-facts">
    <details>
      <summary>Chất lượng và phạm vi</summary>
      <p>Ngày {snapshot.period_start} đến trước {snapshot.period_end} · {snapshot.timezone}</p>
      {measures.map(measure => <div key={measure.metric_id}>
        {measures.length > 1 && <p>{label(metricName(measure.metric_id))} · {measure.currency}</p>}
        {[measure.left, measure.right].map((side, index) => <p key={index}>
          {index === 0 ? left : right} · {number(side.source_rows)} dòng nguồn · {number(side.in_scope_records)} bản ghi trong phạm vi · {number(side.counted_records)} có số tiền được tính · {number(side.invalid_records)} lỗi · {number(side.out_of_scope_records)} ngoài phạm vi · {number(side.excluded_rows)} dòng có quyết định loại · {side.completeness === "CONFIRMED" ? "Đã xác nhận độ đầy đủ" : "Độ đầy đủ chưa được xác nhận"}.
        </p>)}
      </div>)}
      <p>Dấu — dùng khi nhóm thiếu giá trị ở phía tương ứng hoặc số tiền chưa đủ để xác định tổng của nhóm.</p>
    </details>
    <section className="agent-facts" aria-label="Tổng quan tài chính">
      <h4>Tổng quan tài chính</h4>
      {measures.map(measure => {
        const money = (value: string | null) => value === null ? "—" : `${formatDecimal(value)} ${measure.currency}`;
        return <section className="agent-facts" key={measure.metric_id}>
          <p className="agent-answer-context">{label(metricName(measure.metric_id))} · {measure.currency} · {label(measure.amount_basis)}</p>
          <div className="table-scroll" tabIndex={0} aria-label="Giá trị theo trạng thái">
            <table>
              <thead><tr><th scope="col">Trạng thái</th><th scope="col" className="numeric-cell">Nhóm</th><th scope="col" className="numeric-cell">{sourceDisplayName(left)}</th><th scope="col" className="numeric-cell">{sourceDisplayName(right)}</th></tr></thead>
              <tbody>{measure.populations.map(population => <tr key={population.state}>
                <th scope="row">{states[population.state]}</th><td className="numeric-cell">{number(population.groups)}</td>
                <td className="numeric-cell">{money(population.left_amount)}</td><td className="numeric-cell">{money(population.right_amount)}</td>
              </tr>)}</tbody>
              <tfoot><tr><th scope="row">Tổng tiền đủ điều kiện</th><td />
                <td className="numeric-cell"><strong>{money(measure.left.amount)}</strong></td>
                <td className="numeric-cell"><strong>{money(measure.right.amount)}</strong></td></tr></tfoot>
            </table>
          </div>
          <p>Chênh lệch tuyệt đối <strong>{money(measure.absolute_variance)}</strong> · Có dấu {money(measure.signed_variance)}</p>
        </section>;
      })}
    </section>
  </div>;
}
