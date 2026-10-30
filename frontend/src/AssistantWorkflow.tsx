import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Notice, Spinner } from "./components";
import type { Catalogue, Proposal } from "./reconciliationTypes";
import type { AssistantAnswer, AssistantRule } from "./assistantTypes";

/** Chỉ thao tác API reuse hiện có sau xác nhận rõ ràng; kết quả vẫn là PROPOSED. */
export function AssistantWorkflow({
  answer,
  canEdit,
  onReview,
  onCancel,
  onManual,
}: {
  answer: AssistantAnswer;
  canEdit: boolean;
  onReview: (id: string) => void;
  onCancel: () => void;
  onManual: () => void;
}) {
  const [sources, setSources] = useState<Catalogue[]>([]);
  const [templates, setTemplates] = useState<AssistantRule[]>([]);
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const [third, setThird] = useState("");
  const [firstRule, setFirstRule] = useState("");
  const [secondRule, setSecondRule] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [snapshot, setSnapshot] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<Proposal[]>([]);
  const [pending, setPending] = useState<Proposal[]>([]);
  const [pendingTotal, setPendingTotal] = useState(0);
  const alive = useRef(true);
  const keys = useRef(new Map<string, string>());
  const projectId = answer.fact_set.context.project_id;
  const three = answer.proposal?.required_sources === 3;
  useEffect(() => {
    const controller = new AbortController();
    alive.current = true;
    void Promise.all([
      api<{ items: Catalogue[] }>(
        `/projects/${projectId}/canonical-catalogue`,
        { signal: controller.signal },
      ),
      api<{ items: AssistantRule[] }>(
        `/projects/${projectId}/reconciliation-templates`,
        { signal: controller.signal },
      ),
      api<{ items: Proposal[]; total: number }>(
        `/projects/${projectId}/reconciliation-plans?limit=20`,
        { signal: controller.signal },
      ),
    ])
      .then(([catalogue, rules, plans]) => {
        if (!alive.current) return;
        setSources(
          catalogue.items.filter(
            (s) => s.canonical.quality_status === "READY" && !s.canonical.stale,
          ),
        );
        // Proposal contains a bounded shortlist, not an authorization allowlist.
        // The existing scoped endpoint supplies all currently approved templates.
        setTemplates(rules.items);
        setPending(plans.items);
        setPendingTotal(plans.total);
      })
      .catch((err) => {
        if (alive.current)
          setError(
            err instanceof Error ? err.message : "Không tải được nguồn và mẫu.",
          );
      })
      .finally(() => {
        if (alive.current) setLoading(false);
      });
    return () => {
      alive.current = false;
      controller.abort();
    };
  }, [projectId, answer]);
  function changed(action: () => void) {
    action();
    setConfirmed(false);
  }
  function sourceSelect(
    label: string,
    value: string,
    onChange: (id: string) => void,
  ) {
    return (
      <label>
        {label}
        <select
          aria-label={label}
          value={value}
          disabled={busy}
          onChange={(e) => changed(() => onChange(e.target.value))}
        >
          <option value="">Chọn nguồn đã chuẩn hóa</option>
          {sources.map((s) => (
            <option key={s.canonical.id} value={s.canonical.id}>
              {s.name} · {s.canonical.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
    );
  }
  function ruleSelect(
    label: string,
    value: string,
    onChange: (id: string) => void,
  ) {
    const rule = templates.find((t) => t.id === value);
    return (
      <section>
        <label>
          {label}
          <select
            aria-label={label}
            value={value}
            disabled={busy}
            onChange={(e) => changed(() => onChange(e.target.value))}
          >
            <option value="">Chọn rule đã được duyệt</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.plan.name} · revision {t.revision}
              </option>
            ))}
          </select>
        </label>
        {rule && (
          <div className="notice">
            <div>
              <p>
                {rule.plan.name} · {rule.plan.timezone} ·{" "}
                {rule.plan.cardinality}
              </p>
              <p>
                Khóa:{" "}
                {rule.plan.join_keys
                  .map((k) => `${k.left} ↔ ${k.right}`)
                  .join(", ")}
              </p>
              <p>
                Phạm vi trái:{" "}
                {Object.entries(rule.plan.left.filters)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(", ") || "Toàn nguồn theo rule"}
                ; phải:{" "}
                {Object.entries(rule.plan.right.filters)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(", ") || "Toàn nguồn theo rule"}
              </p>
              {rule.plan.comparison_metrics.map((m) => (
                <p key={m.metric_id}>
                  {m.metric_id} · {m.amount_basis} · {m.currency} · tolerance{" "}
                  {m.absolute_tolerance}
                </p>
              ))}
            </div>
          </div>
        )}
      </section>
    );
  }
  const distinct =
    new Set([left, right, ...(three ? [third] : [])]).size === (three ? 3 : 2);
  const valid =
    !!left &&
    !!right &&
    (!three || !!third) &&
    distinct &&
    !!firstRule &&
    (!three || !!secondRule) &&
    !!from &&
    !!to &&
    from < to &&
    !!snapshot &&
    confirmed;
  async function create() {
    if (!valid || !canEdit || busy) return;
    setBusy(true);
    setError("");
    const results: Proposal[] = [];
    try {
      const pairs = [
        { rule: firstRule, right },
        ...(three ? [{ rule: secondRule, right: third }] : []),
      ];
      for (const pair of pairs) {
        const body = JSON.stringify({
          left_canonical_id: left,
          right_canonical_id: pair.right,
          period_start: from,
          period_end: to,
          left_coverage_start: from,
          left_coverage_end: to,
          right_coverage_start: from,
          right_coverage_end: to,
          completeness: "CONFIRMED",
          snapshot_at: new Date(snapshot).toISOString(),
        });
        const signature = pair.rule + body;
        const key = keys.current.get(signature) || crypto.randomUUID();
        keys.current.set(signature, key);
        const proposal = await api<Proposal>(
          `/reconciliation-contracts/${pair.rule}/reuse`,
          { method: "POST", body, headers: { "Idempotency-Key": key } },
        );
        results.push(proposal);
        if (alive.current) setCreated([...results]);
      }
    } catch (err) {
      if (alive.current)
        setError(
          `${results.length ? `Đã tạo ${results.length} kế hoạch; phần còn lại chưa xong. ` : ""}${err instanceof Error ? err.message : "Không tạo được kế hoạch."} Không tự duyệt hoặc chạy đối soát.`,
        );
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  return (
    <section
      className="card assistant-workflow"
      aria-label="Xác nhận bước tiếp theo"
    >
      <h3>Kiểm tra trước khi thực hiện</h3>
      {answer.proposal?.questions.map((q, i) => (
        <p key={i}>{q}</p>
      ))}
      {loading ? (
        <Spinner />
      ) : (
        <>
          {!templates.length && (
            <Notice>
              Chưa có mẫu đã duyệt để tái sử dụng. Mở Đối soát để tạo/review
              rule; Trợ lý không tự tạo quy tắc tài chính.
            </Notice>
          )}
          {!canEdit && (
            <Notice>
              Bạn có quyền xem. Cần quyền chỉnh sửa để tạo kế hoạch.
            </Notice>
          )}
          {templates.length > 0 && (
            <fieldset disabled={busy || !canEdit} className="rule-fieldset">
              <legend>Tái sử dụng rule đã duyệt</legend>
              <p>
                {three
                  ? "Ba nguồn được chia thành hai cặp với nguồn nội bộ; không JOIN ba nguồn trực tiếp."
                  : "Hai nguồn theo đúng rule và revisions đã duyệt."}
              </p>
              {sourceSelect(
                three ? "Nguồn nội bộ" : "Nguồn trái",
                left,
                setLeft,
              )}
              {sourceSelect(
                three ? "Nguồn đối chiếu thứ nhất" : "Nguồn phải",
                right,
                setRight,
              )}
              {three &&
                sourceSelect("Nguồn đối chiếu thứ hai", third, setThird)}
              {ruleSelect("Mẫu cho cặp thứ nhất", firstRule, setFirstRule)}
              {three &&
                ruleSelect("Mẫu cho cặp thứ hai", secondRule, setSecondRule)}
              <label>
                Kỳ bắt đầu
                <input
                  aria-label="Kỳ workflow bắt đầu"
                  type="date"
                  value={from}
                  onChange={(e) => changed(() => setFrom(e.target.value))}
                />
              </label>
              <label>
                Kỳ kết thúc (không gồm ngày này)
                <input
                  aria-label="Kỳ workflow kết thúc"
                  type="date"
                  value={to}
                  onChange={(e) => changed(() => setTo(e.target.value))}
                />
              </label>
              <label>
                Thời điểm đối soát (
                {Intl.DateTimeFormat().resolvedOptions().timeZone})
                <input
                  aria-label="Thời điểm workflow"
                  type="datetime-local"
                  value={snapshot}
                  onChange={(e) => changed(() => setSnapshot(e.target.value))}
                />
              </label>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                Tôi xác nhận nguồn, rule, kỳ và mọi nguồn bao phủ đầy đủ kỳ này.
                Tạo kế hoạch cần duyệt, chưa chạy đối soát.
              </label>
              <button
                className="button primary"
                disabled={!valid || busy || !canEdit}
                onClick={() => void create()}
              >
                {busy ? <Spinner /> : "Tạo kế hoạch cần duyệt"}
              </button>
            </fieldset>
          )}
          {created.map((result) => (
            <Notice tone="success" key={result.id}>
              Đã tạo đề xuất {result.proposal.plan?.name}; chưa approval/chạy.
              <button
                className="text-button"
                onClick={() => onReview(result.id)}
              >
                Mở kế hoạch {result.id.slice(0, 8)} để duyệt
              </button>
            </Notice>
          ))}
          <details>
            <summary>Kế hoạch của bạn đang chờ duyệt ({pendingTotal})</summary>
            {pending.map((result) => (
              <button
                className="text-button"
                key={result.id}
                onClick={() => onReview(result.id)}
              >
                Mở bản nháp{" "}
                {result.proposal.plan?.name || result.id.slice(0, 8)}
              </button>
            ))}
            {pending.length < pendingTotal && (
              <button
                className="text-button"
                onClick={() =>
                  void api<{ items: Proposal[]; total: number }>(
                    `/projects/${projectId}/reconciliation-plans?limit=20&offset=${pending.length}`,
                  )
                    .then((page) => {
                      if (alive.current) {
                        setPending((old) => [...old, ...page.items]);
                        setPendingTotal(page.total);
                      }
                    })
                    .catch((err) => {
                      if (alive.current)
                        setError(
                          err instanceof Error
                            ? err.message
                            : "Không tải được bản nháp.",
                        );
                    })
                }
              >
                Tải thêm bản nháp
              </button>
            )}
          </details>
          {error && <Notice tone="error">{error}</Notice>}
          <p>
            Mở kế hoạch mới sẽ thay bản nháp đang xem; kết quả và nguồn lịch sử
            vẫn được giữ.
          </p>
          <div className="assistant-actions">
            <button className="button secondary" onClick={onManual}>
              Xem và duyệt kế hoạch
            </button>
            <button className="text-button" disabled={busy} onClick={onCancel}>
              Hủy đề xuất
            </button>
          </div>
        </>
      )}
    </section>
  );
}
