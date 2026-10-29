import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  CheckCheck,
  GitCompareArrows,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import * as echarts from "echarts/core";
import { PieChart } from "echarts/charts";
import {
  TooltipComponent,
  LegendComponent,
  AriaComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import { api } from "./api";
import { ReconciliationEvidence } from "./ReconciliationEvidence";
import { Badge, Notice, Spinner } from "./components";
import {
  label,
  type Catalogue,
  type Case,
  type Group,
  type Metric,
  type Pair,
  type Plan,
  type Proposal,
  type Readiness,
  type Run,
  type Slot,
  type SourceEvidence,
} from "./reconciliationTypes";
import type { Job } from "./types";

echarts.use([
  PieChart,
  TooltipComponent,
  LegendComponent,
  AriaComponent,
  SVGRenderer,
]);
type Mode = "home" | "reconcile" | "exceptions" | "reports";
const send = (body: unknown): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
});
const waitForJob = async (jobId: string, signal: AbortSignal) => {
  for (let i = 0; i < 150; i++) {
    signal.throwIfAborted();
    const job = await api<Job>(`/jobs/${jobId}`, { signal });
    if (job.status === "SUCCEEDED") return job;
    if (["BLOCKED", "FAILED", "CANCELLED"].includes(job.status))
      throw new Error(
        `Tác vụ bị chặn: ${job.error_code}. Có thể tạo rule thủ công.`,
      );
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
  throw new Error(
    "Tác vụ còn xử lý. Dùng Cập nhật để xem lại, không cần gửi lại.",
  );
};

function StatusChart({ counts }: { counts: Record<string, number> }) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!root.current) return;
    const chart = echarts.init(root.current, undefined, { renderer: "svg" });
    chart.setOption({
      aria: { enabled: true },
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      color: ["#2563EB", "#60A5FA", "#F59E0B", "#EF4444", "#94A3B8", "#10B981"],
      series: [
        {
          type: "pie",
          radius: ["48%", "72%"],
          center: ["50%", "42%"],
          label: { show: false },
          data: Object.entries(counts).map(([name, value]) => ({
            name: label(name),
            value,
          })),
        },
      ],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(root.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [counts]);
  return (
    <div role="img" aria-label="Phân bố trạng thái đối soát">
      <div className="result-chart" ref={root} />
    </div>
  );
}

export function ReconciliationStudio({
  projectId,
  mode,
  requestedRun,
  canEdit,
}: {
  projectId: string;
  mode: Mode;
  canEdit: boolean;
  requestedRun: { id: string; request: number } | null;
}) {
  const [catalogue, setCatalogue] = useState<Catalogue[]>([]),
    [runs, setRuns] = useState<Run[]>([]);
  const [runId, setRunId] = useState(
    localStorage.getItem(`studio.run.${projectId}`) || "",
  );
  const [run, setRun] = useState<Run | null>(null),
    [groups, setGroups] = useState<Group[]>([]),
    [total, setTotal] = useState(0);
  const [cases, setCases] = useState<Case[]>([]),
    [caseTotal, setCaseTotal] = useState(0),
    [openCount, setOpenCount] = useState<number | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const [offset, setOffset] = useState(0),
    [search, setSearch] = useState(""),
    [filter, setFilter] = useState("");
  const [issueFilter, setIssueFilter] = useState(""),
    [caseSort, setCaseSort] = useState("type");
  const [evidence, setEvidence] = useState<SourceEvidence | null>(null);
  const [evidenceRunId, setEvidenceRunId] = useState("");
  const [listLoading, setListLoading] = useState(true);
  const [currentCase, setCurrentCase] = useState<Case | null>(null);
  const [draft, setDraft] = useState<Plan | null>(null),
    [proposal, setProposal] = useState<Proposal | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null),
    [download, setDownload] = useState("");
  const [scopeConfirmed, setScopeConfirmed] = useState(false),
    [exportNotice, setExportNotice] = useState("");
  const [templates, setTemplates] = useState<{ id: string; plan: Plan }[]>([]);
  const [runOffset, setRunOffset] = useState(0),
    [runTotal, setRunTotal] = useState(0);
  const [fromPeriod, setFromPeriod] = useState(""),
    [toPeriod, setToPeriod] = useState(""),
    [sourceFilter, setSourceFilter] = useState("");
  useEffect(() => {
    if (!requestedRun) return;
    setRunId(requestedRun.id);
    setRunOffset(0);
    setFromPeriod("");
    setToPeriod("");
    setSourceFilter("");
  }, [requestedRun]);
  const alive = useRef(true);
  const controller = useRef(new AbortController());
  const runScope = useRef({ id: runId });
  if (runScope.current.id !== runId) runScope.current = { id: runId };
  const evidenceSequence = useRef(0);
  const evidenceTrigger = useRef<HTMLElement | null>(null);
  useEffect(() => {
    alive.current = true;
    controller.current = new AbortController();
    return () => {
      alive.current = false;
      controller.current.abort();
    };
  }, []);
  const refreshSequence = useRef(0);
  const action = async (task: () => Promise<void>) => {
    const scope = runScope.current;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await task();
    } catch (e) {
      if (alive.current && scope === runScope.current)
        setError(e instanceof Error ? e.message : "Không thể hoàn tất.");
    } finally {
      if (alive.current) setBusy(false);
    }
  };
  const wait = (jobId: string) => waitForJob(jobId, controller.current.signal);
  const refresh = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    setListLoading(true);
    try {
      const [c, r, t] = await Promise.all([
        api<{ items: Catalogue[] }>(
          `/projects/${projectId}/canonical-catalogue`,
        ),
        api<{ items: Run[]; total: number }>(
          `/runs?project_id=${projectId}&offset=${runOffset}${fromPeriod ? `&period_start=${fromPeriod}` : ""}${toPeriod ? `&period_end=${toPeriod}` : ""}${sourceFilter ? `&source_id=${sourceFilter}` : ""}`,
        ),
        api<{ items: { id: string; plan: Plan }[] }>(
          `/projects/${projectId}/reconciliation-templates`,
        ),
      ]);
      if (!alive.current || sequence !== refreshSequence.current) return;
      setCatalogue(c.items);
      setRuns(r.items);
      setRunTotal(r.total);
      setTemplates(t.items);
      setRunId((old) =>
        r.items.some((r) => r.id === old) ? old : r.items[0]?.id || "",
      );
    } catch (err) {
      if (alive.current && sequence === refreshSequence.current) throw err;
    } finally {
      if (alive.current && sequence === refreshSequence.current)
        setListLoading(false);
    }
  }, [projectId, runOffset, fromPeriod, toPeriod, sourceFilter]);
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
  }, [refresh]);
  useEffect(() => {
    setOffset(0);
    setSearch("");
    setFilter("");
  }, [mode, runId]);
  useEffect(() => {
    if (!runId) {
      setRun(null);
      return;
    }
    let active = true;
    localStorage.setItem(`studio.run.${projectId}`, runId);
    setRun(null);
    setEvidence(null);
    setDownload("");
    setExportNotice("");
    void api<Run>(`/runs/${runId}`)
      .then((r) => {
        if (!active) return;
        if (r.project_id !== projectId)
          throw new Error(
            "Lần đối soát không thuộc dự án đang chọn. Hãy chọn lại từ lịch sử.",
          );
        setRun(r);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [runId, projectId, runs]);
  useEffect(() => {
    let active = true;
    setGroups([]);
    setCases([]);
    setOpenCount(null);
    if (!run?.metric_snapshot) return;
    setDetailLoading(true);
    const query = `offset=${offset}&limit=25&search=${encodeURIComponent(search)}`;
    void Promise.all([
      api<{ items: Group[]; total: number }>(
        `/runs/${run.id}/matches?${query}&linkage=${mode === "exceptions" ? "" : filter}`,
      ),
      api<{ items: Case[]; total: number; current_open_count: number }>(
        `/runs/${run.id}/exceptions?${query}&state=${mode === "exceptions" ? filter : ""}&issue=${issueFilter}&sort=${caseSort}`,
      ),
    ])
      .then(([g, c]) => {
        if (active) {
          setGroups(g.items);
          setTotal(g.total);
          setCases(c.items);
          setCaseTotal(c.total);
          setOpenCount(c.current_open_count);
          setDetailLoading(false);
        }
      })
      .catch((e) => {
        if (active) {
          setError(e.message);
          setDetailLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [run, offset, search, filter, mode, issueFilter, caseSort]);
  const sources = catalogue.filter(
    (c) => !c.canonical.stale && c.canonical.quality_status !== "FAILED",
  );
  const makeDraft = (leftId: string, rightId: string) => {
    const left = sources.find((c) => c.canonical.id === leftId),
      right = sources.find((c) => c.canonical.id === rightId);
    if (!left || !right || leftId === rightId) return;
    const start = draft?.period_start || "",
      end = draft?.period_end || "";
    const slot = (cat: Catalogue, role: string): Slot => ({
      canonical_id: cat.canonical.id,
      role,
      date_field:
        cat.schema_definition.fields.find((f) => f.data_type === "date")?.id ||
        "",
      time_basis: "event_date",
      currency_field: cat.schema_definition.fields.some(
        (f) => f.id === "currency",
      )
        ? "currency"
        : null,
      filters: {},
      coverage_start: start,
      coverage_end: end,
      completeness: "UNKNOWN",
      snapshot_at: new Date().toISOString(),
      settlement_due_at: null,
    });
    const money = left.schema_definition.fields.find(
      (f) => f.data_type === "decimal",
    );
    const other = right.schema_definition.fields.find(
      (f) =>
        f.data_type === "decimal" &&
        f.semantic_metric === money?.semantic_metric,
    );
    const pairs = left.schema_definition.business_key_fields
      .filter((k) => right.schema_definition.fields.some((f) => f.id === k))
      .map((k) => ({ left: k, right: k }));
    const metric: Metric = {
      left: money?.id || "",
      right: other?.id || "",
      metric_id: money?.semantic_metric || "",
      currency: money?.currency || "",
      unit: money?.unit || "",
      amount_basis: money?.amount_basis || "",
      sign_convention: "SOURCE_SIGNED",
      absolute_tolerance: "0",
      relative_tolerance: null,
      rounding_scale: null,
      rounding_mode: "HALF_EVEN",
    };
    setDraft({
      name: "Đối soát nguồn đã chuẩn hóa",
      entity_kind: left.schema_definition.entity_kind,
      left: slot(left, "reference"),
      right: slot(right, "counterpart"),
      join_keys: pairs.length ? pairs : [{ left: "", right: "" }],
      comparison_metrics: [metric],
      attributes: [],
      comparison_grain: left.schema_definition.grain,
      cardinality: "ONE_TO_ONE",
      aggregation: "NONE",
      period_start: start,
      period_end: end,
      timezone: draft?.timezone || "",
      effective_from: start,
      effective_to: null,
      allow_partial: false,
      duplicate_policy: "REVIEW",
      fuzzy_fields: [],
      fuzzy_block_keys: [],
      fuzzy_min_score: 85,
      fuzzy_top_k: 3,
      evidence_ids: [leftId, rightId],
    });
    setProposal(null);
    setReadiness(null);
    setScopeConfirmed(false);
  };
  const change = (update: Partial<Plan>) => {
    if (draft) setDraft({ ...draft, ...update });
    setProposal(null);
    setReadiness(null);
    setScopeConfirmed(false);
  };
  const changeSlot = (side: "left" | "right", update: Partial<Slot>) =>
    draft && change({ [side]: { ...draft[side], ...update } });
  const changeMetric = (update: Partial<Metric>) =>
    draft &&
    change({
      comparison_metrics: [{ ...draft.comparison_metrics[0], ...update }],
    });
  const fieldSelect = (
    side: "left" | "right",
    value: string,
    onChange: (value: string) => void,
    type?: string,
  ) => (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Chọn trường</option>
      {sources
        .find((c) => c.canonical.id === draft?.[side].canonical_id)
        ?.schema_definition.fields.filter((f) => !type || f.data_type === type)
        .map((f) => (
          <option key={f.id} value={f.id}>
            {f.name}
          </option>
        ))}
    </select>
  );
  const pairBuilder = (
    title: string,
    key: "join_keys" | "attributes" | "fuzzy_fields" | "fuzzy_block_keys",
  ) =>
    draft && (
      <fieldset className="rule-fieldset">
        <legend>{title}</legend>
        {draft[key].map((pair, i) => (
          <div className="pair-row" key={i}>
            <label>
              Nguồn trái
              {fieldSelect("left", pair.left, (v) => {
                const pairs = [...draft[key]];
                pairs[i] = { ...pair, left: v };
                change({ [key]: pairs });
              })}
            </label>
            <label>
              Nguồn phải
              {fieldSelect("right", pair.right, (v) => {
                const pairs = [...draft[key]];
                pairs[i] = { ...pair, right: v };
                change({ [key]: pairs });
              })}
            </label>
            <button
              type="button"
              className="text-button"
              onClick={() =>
                change({ [key]: draft[key].filter((_, j) => i !== j) })
              }
            >
              Bỏ
            </button>
          </div>
        ))}
        <button
          type="button"
          className="text-button"
          onClick={() =>
            change({ [key]: [...draft[key], { left: "", right: "" } as Pair] })
          }
        >
          + Thêm cặp trường
        </button>
      </fieldset>
    );
  const openEvidence = (groupId: string, caseRow?: Case) =>
    action(async () => {
      const scope = runScope.current;
      const sequence = ++evidenceSequence.current;
      evidenceTrigger.current = document.activeElement as HTMLElement | null;
      const data = await api<NonNullable<typeof evidence>>(
        `/runs/${runId}/groups/${groupId}/evidence`,
        { signal: controller.current.signal },
      );
      if (
        !alive.current ||
        scope !== runScope.current ||
        sequence !== evidenceSequence.current
      )
        return;
      setEvidence(data);
      setEvidenceRunId(runId);
      setCurrentCase(caseRow || null);
    });
  const exportFile = (format: string) =>
    action(async () => {
      const scope = runScope.current;
      const created = await api<{ job_id: string; export_id: string }>(
        `/runs/${runId}/exports?format=${format}`,
        { method: "POST" },
      );
      await wait(created.job_id);
      const info = await api<{
        download_url: string;
        review_state_as_of: string | null;
        notice_vi: string;
      }>(`/exports/${created.export_id}`);
      if (alive.current && scope === runScope.current) {
        setDownload(info.download_url);
        setExportNotice(
          `${info.notice_vi} Thời điểm tạo: ${info.review_state_as_of || "không được ghi ở định dạng cũ"}.`,
        );
      }
    });
  if (!projectId) return null;
  const snapshot = run?.id === runId ? run.metric_snapshot : null;
  const scopeReady =
    !!draft &&
    !!draft.period_start &&
    !!draft.period_end &&
    !!draft.timezone &&
    !!draft.effective_from &&
    [draft.left, draft.right].every(
      (s) => !!s.coverage_start && !!s.coverage_end,
    );
  if (mode === "home" && !snapshot)
    return error ? <Notice tone="error">{error}</Notice> : null;
  return (
    <section className="reconciliation-studio">
      <div className="section-heading">
        <div>
          <span className="eyebrow">KẾT QUẢ CÓ BẰNG CHỨNG</span>
          <h2>
            {mode === "reconcile"
              ? "Thiết lập đối soát"
              : mode === "exceptions"
                ? "Ngoại lệ cần xem xét"
                : "Kết quả đối soát"}
          </h2>
        </div>
        <button
          className="button secondary"
          disabled={busy}
          onClick={() => void action(refresh)}
        >
          <RefreshCw size={16} />
          Cập nhật đối soát
        </button>
      </div>
      {error && <Notice tone="error">{error}</Notice>}
      {message && <Notice tone="success">{message}</Notice>}
      {!canEdit && (
        <Notice>
          Bạn có quyền xem dữ liệu và bằng chứng. Cần quyền chỉnh sửa để tạo,
          phê duyệt quy tắc, xuất báo cáo mới hoặc lưu xem xét.
        </Notice>
      )}
      {busy && <Spinner />}
      {mode === "reconcile" && (
        <fieldset
          className="card rule-builder"
          disabled={!canEdit}
          aria-label="Thiết lập quy tắc"
        >
          <h3>
            1. Chọn nguồn → 2. AI chuẩn bị → 3. Duyệt → 4. Chạy và xem ngoại lệ
          </h3>
          <p className="muted">
            Chọn hai nguồn đã chuẩn hóa. AI có thể tìm cặp khóa khác tên; bạn
            xác nhận phạm vi và quy tắc trước khi chạy.
          </p>
          {listLoading ? (
            <Spinner />
          ) : error && !catalogue.length ? (
            <Notice>
              Chưa tải được nguồn. Dùng Cập nhật đối soát để thử lại.
            </Notice>
          ) : sources.length < 2 ? (
            <Notice>
              Cần ít nhất hai nguồn đã chuẩn hóa. Mở Dữ liệu để xác nhận ánh xạ
              và chuẩn hóa.
            </Notice>
          ) : (
            <>
              <div className="rule-grid">
                {(["left", "right"] as const).map((side, i) => (
                  <label key={side}>
                    {i === 0 ? "Nguồn tham chiếu" : "Nguồn đối ứng"}
                    <select
                      aria-label={
                        i === 0 ? "Nguồn tham chiếu" : "Nguồn đối ứng"
                      }
                      value={draft?.[side].canonical_id || ""}
                      onChange={(e) => {
                        const selected = e.target.value;
                        const otherSide = side === "left" ? "right" : "left";
                        const previous = draft?.[otherSide].canonical_id;
                        const other =
                          previous && previous !== selected
                            ? previous
                            : sources.find((c) => c.canonical.id !== selected)
                                ?.canonical.id || "";
                        makeDraft(
                          side === "left" ? selected : other,
                          side === "right" ? selected : other,
                        );
                      }}
                    >
                      <option value="">Chọn nguồn</option>
                      {sources.map((c) => (
                        <option key={c.canonical.id} value={c.canonical.id}>
                          {c.name} · {c.schema_definition.grain} ·{" "}
                          {c.canonical.row_count} dòng
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              {draft && (
                <>
                  <button
                    className={`button ${proposal ? "secondary" : "primary"}`}
                    disabled={busy}
                    onClick={() =>
                      void action(async () => {
                        const request = scopeConfirmed
                          ? {
                              left: draft.left,
                              right: draft.right,
                              period_start: draft.period_start,
                              period_end: draft.period_end,
                              timezone: draft.timezone,
                              effective_from: draft.effective_from,
                              effective_to: draft.effective_to,
                              allow_partial: draft.allow_partial,
                            }
                          : {
                              left: { canonical_id: draft.left.canonical_id },
                              right: { canonical_id: draft.right.canonical_id },
                            };
                        const job = await api<{ job_id: string }>(
                          "/reconciliation-plans/ai",
                          send({ project_id: projectId, request }),
                        );
                        const done = await wait(job.job_id);
                        const p = await api<Proposal>(
                          `/reconciliation-plans/${done.result?.plan_id}`,
                        );
                        if (alive.current) {
                          setProposal(p);
                          if (p.proposal.plan) setDraft(p.proposal.plan);
                          else if (p.proposal.suggestions) {
                            const s = p.proposal.suggestions;
                            setDraft({
                              ...draft,
                              left: { ...draft.left, role: s.left_role },
                              right: { ...draft.right, role: s.right_role },
                              join_keys: s.join_keys.length
                                ? s.join_keys
                                : draft.join_keys,
                              comparison_metrics: s.comparison_metrics.length
                                ? s.comparison_metrics
                                : draft.comparison_metrics,
                              cardinality: s.cardinality || draft.cardinality,
                              comparison_grain:
                                s.comparison_grain || draft.comparison_grain,
                              aggregation: s.aggregation || draft.aggregation,
                              evidence_ids: s.evidence_ids,
                            });
                          }
                          setMessage(
                            "AI đã chuẩn bị gợi ý. Hãy kiểm tra các điểm cần xác nhận; chưa có quyền thực thi.",
                          );
                        }
                      })
                    }
                  >
                    <Sparkles size={16} />
                    AI đề xuất kế hoạch (có dùng quota)
                  </button>
                  <p className="muted">
                    Chưa cần nhập khóa chính xác để hỏi AI. Thiếu kỳ, múi giờ
                    hoặc coverage sẽ cần bạn xác nhận. Nếu hết quota, mở phần
                    chỉnh thủ công bên dưới.
                  </p>
                  <div className="rule-grid">
                    <label>
                      Tên quy tắc
                      <input
                        value={draft.name}
                        onChange={(e) => change({ name: e.target.value })}
                      />
                    </label>
                    <label>
                      Quan hệ
                      <select
                        value={draft.cardinality}
                        onChange={(e) =>
                          change({
                            cardinality: e.target.value,
                            aggregation:
                              e.target.value === "ONE_TO_ONE"
                                ? "NONE"
                                : "SUM_SIGNED",
                          })
                        }
                      >
                        <option value="ONE_TO_ONE">Một — Một</option>
                        <option value="ONE_TO_MANY">
                          Một — Nhiều (cộng signed)
                        </option>
                        <option value="MANY_TO_ONE">
                          Nhiều — Một (cộng signed)
                        </option>
                      </select>
                    </label>
                    <label>
                      Từ ngày
                      <input
                        type="date"
                        value={draft.period_start}
                        onChange={(e) =>
                          change({
                            period_start: e.target.value,
                            effective_from:
                              draft.effective_from || e.target.value,
                          })
                        }
                      />
                    </label>
                    <label>
                      Đến ngày (không gồm)
                      <input
                        type="date"
                        value={draft.period_end}
                        onChange={(e) => change({ period_end: e.target.value })}
                      />
                    </label>
                    <label>
                      Múi giờ
                      <input
                        placeholder="Ví dụ Asia/Ho_Chi_Minh — cần xác nhận"
                        value={draft.timezone}
                        onChange={(e) => change({ timezone: e.target.value })}
                      />
                    </label>
                    <label>
                      Đơn vị đối soát (mỗi nhóm đại diện cho)
                      <input
                        value={draft.comparison_grain}
                        onChange={(e) =>
                          change({ comparison_grain: e.target.value })
                        }
                      />
                    </label>
                  </div>
                  <details>
                    <summary>Chỉnh khóa và chỉ tiêu thủ công</summary>
                    {pairBuilder("Khóa liên kết đã xác nhận", "join_keys")}
                    <fieldset className="rule-fieldset">
                      <legend>Chỉ tiêu tiền</legend>
                      <div className="rule-grid">
                        <label>
                          Trường tiền trái
                          {fieldSelect(
                            "left",
                            draft.comparison_metrics[0].left,
                            (v) => changeMetric({ left: v }),
                            "decimal",
                          )}
                        </label>
                        <label>
                          Trường tiền phải
                          {fieldSelect(
                            "right",
                            draft.comparison_metrics[0].right,
                            (v) => changeMetric({ right: v }),
                            "decimal",
                          )}
                        </label>
                        <label>
                          Ý nghĩa chỉ tiêu
                          <input
                            value={draft.comparison_metrics[0].metric_id}
                            onChange={(e) =>
                              changeMetric({ metric_id: e.target.value })
                            }
                          />
                        </label>
                        <label>
                          Cơ sở số tiền
                          <input
                            value={draft.comparison_metrics[0].amount_basis}
                            onChange={(e) =>
                              changeMetric({ amount_basis: e.target.value })
                            }
                          />
                        </label>
                        <label>
                          Tiền tệ
                          <input
                            value={draft.comparison_metrics[0].currency}
                            onChange={(e) =>
                              changeMetric({ currency: e.target.value })
                            }
                          />
                        </label>
                        <label>
                          Đơn vị
                          <input
                            value={draft.comparison_metrics[0].unit}
                            onChange={(e) =>
                              changeMetric({ unit: e.target.value })
                            }
                          />
                        </label>
                        <label>
                          Sai số tuyệt đối
                          <input
                            inputMode="decimal"
                            value={
                              draft.comparison_metrics[0].absolute_tolerance
                            }
                            onChange={(e) =>
                              changeMetric({
                                absolute_tolerance: e.target.value,
                              })
                            }
                          />
                        </label>
                        <label>
                          Sai số tương đối (0.01 = 1%)
                          <input
                            inputMode="decimal"
                            value={
                              draft.comparison_metrics[0].relative_tolerance ||
                              ""
                            }
                            onChange={(e) =>
                              changeMetric({
                                relative_tolerance: e.target.value || null,
                              })
                            }
                          />
                        </label>
                      </div>
                      <p className="muted">
                        Giữ dấu số tiền từ nguồn đã chuẩn hóa. Không tự áp phí,
                        FX hoặc đổi gross/net. Cần xác nhận điều này khi duyệt.
                      </p>
                    </fieldset>
                  </details>
                  <div className="rule-grid">
                    {(["left", "right"] as const).map((side) => (
                      <fieldset className="rule-fieldset" key={side}>
                        <legend>
                          Phạm vi{" "}
                          {side === "left" ? "nguồn trái" : "nguồn phải"}
                        </legend>
                        <label>
                          Trường ngày
                          {fieldSelect(
                            side,
                            draft[side].date_field,
                            (v) => changeSlot(side, { date_field: v }),
                            "date",
                          )}
                        </label>
                        <label>
                          Cơ sở thời gian
                          <input
                            value={draft[side].time_basis}
                            onChange={(e) =>
                              changeSlot(side, { time_basis: e.target.value })
                            }
                          />
                        </label>
                        <label>
                          Trường tiền tệ
                          {fieldSelect(
                            side,
                            draft[side].currency_field || "",
                            (v) =>
                              changeSlot(side, { currency_field: v || null }),
                          )}
                        </label>
                        <label>
                          Đầu kỳ nguồn
                          <input
                            type="date"
                            value={draft[side].coverage_start}
                            onChange={(e) =>
                              changeSlot(side, {
                                coverage_start: e.target.value,
                              })
                            }
                          />
                        </label>
                        <label>
                          Cuối kỳ nguồn (không gồm)
                          <input
                            type="date"
                            value={draft[side].coverage_end}
                            onChange={(e) =>
                              changeSlot(side, { coverage_end: e.target.value })
                            }
                          />
                        </label>
                        <label>
                          Độ đầy đủ
                          <select
                            value={draft[side].completeness}
                            onChange={(e) =>
                              changeSlot(side, { completeness: e.target.value })
                            }
                          >
                            <option value="UNKNOWN">Chưa xác nhận</option>
                            <option value="CONFIRMED">
                              Đã xác nhận đầy đủ
                            </option>
                            <option value="INCOMPLETE">Chưa đầy đủ</option>
                          </select>
                        </label>
                        <label>
                          Lọc phạm vi theo trường
                          {fieldSelect(
                            side,
                            Object.keys(draft[side].filters)[0] || "",
                            (v) =>
                              changeSlot(side, {
                                filters: v ? { [v]: "" } : {},
                              }),
                          )}
                        </label>
                        {!!Object.keys(draft[side].filters).length && (
                          <label>
                            Giá trị phạm vi
                            <input
                              value={
                                Object.values(draft[side].filters)[0] || ""
                              }
                              onChange={(e) =>
                                changeSlot(side, {
                                  filters: {
                                    [Object.keys(draft[side].filters)[0]]:
                                      e.target.value,
                                  },
                                })
                              }
                            />
                          </label>
                        )}
                      </fieldset>
                    ))}
                  </div>
                  <details>
                    <summary>Thuộc tính và quy tắc nâng cao</summary>
                    {pairBuilder("Thuộc tính cần so sánh", "attributes")}
                    {pairBuilder(
                      "Text tạo ứng viên review (không mã định danh)",
                      "fuzzy_fields",
                    )}
                    {pairBuilder("Khóa blocking ứng viên", "fuzzy_block_keys")}
                    <div className="rule-grid">
                      <label>
                        Có hiệu lực từ
                        <input
                          type="date"
                          value={draft.effective_from}
                          onChange={(e) =>
                            change({ effective_from: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        Hết hiệu lực (không gồm)
                        <input
                          type="date"
                          value={draft.effective_to || ""}
                          onChange={(e) =>
                            change({ effective_to: e.target.value || null })
                          }
                        />
                      </label>
                      <label>
                        Làm tròn khi so sánh
                        <select
                          value={
                            draft.comparison_metrics[0].rounding_scale ?? ""
                          }
                          onChange={(e) =>
                            changeMetric({
                              rounding_scale:
                                e.target.value === ""
                                  ? null
                                  : Number(e.target.value),
                            })
                          }
                        >
                          <option value="">Không làm tròn</option>
                          {[0, 2, 3, 4, 6].map((n) => (
                            <option key={n} value={n}>
                              {n} chữ số thập phân
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Quy tắc làm tròn
                        <select
                          value={draft.comparison_metrics[0].rounding_mode}
                          onChange={(e) =>
                            changeMetric({ rounding_mode: e.target.value })
                          }
                        >
                          <option value="HALF_EVEN">Half even</option>
                          <option value="HALF_UP">Half up</option>
                        </select>
                      </label>
                    </div>
                  </details>
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={draft.allow_partial}
                      onChange={(e) =>
                        change({ allow_partial: e.target.checked })
                      }
                    />
                    Cho phép kết quả một phần; nguồn thiếu kỳ sẽ ở trạng thái
                    đang chờ
                  </label>
                  <label className="check-label">
                    <input
                      type="checkbox"
                      disabled={!scopeReady}
                      checked={scopeConfirmed}
                      onChange={(e) => setScopeConfirmed(e.target.checked)}
                    />
                    Tôi xác nhận kỳ, múi giờ và phạm vi nguồn
                  </label>
                  {!scopeReady && (
                    <Notice tone="warning">
                      Nhập kỳ, múi giờ và khoảng dữ liệu thực tế của cả hai
                      nguồn trước khi duyệt. Hệ thống không tự chọn tháng hoặc
                      UTC.
                    </Notice>
                  )}
                  <div className="rule-actions">
                    <button
                      className="button secondary"
                      disabled={busy || !scopeConfirmed}
                      onClick={() =>
                        void action(async () => {
                          setReadiness(
                            await api<Readiness>(
                              "/reconciliation-plans/validate",
                              send({ project_id: projectId, plan: draft }),
                            ),
                          );
                          setMessage(
                            "Rule hợp lệ về cấu trúc/ngữ nghĩa; vẫn cần bạn phê duyệt.",
                          );
                        })
                      }
                    >
                      Kiểm tra điều kiện
                    </button>
                    <button
                      className="button secondary"
                      disabled={busy || !scopeConfirmed}
                      onClick={() =>
                        void action(async () => {
                          setProposal(
                            await api<Proposal>(
                              "/reconciliation-plans",
                              send({ project_id: projectId, plan: draft }),
                            ),
                          );
                          setMessage(
                            "Đã lưu bản đề xuất. Kiểm tra nội dung trước khi xác nhận.",
                          );
                        })
                      }
                    >
                      Lưu đề xuất thủ công
                    </button>
                  </div>
                  {readiness && (
                    <Notice>
                      <p>
                        Đã kiểm tra schema, scope, grain, metric, thời gian và
                        khóa. Trùng khóa được giữ để review.
                      </p>
                      {readiness.sources.map((s) => (
                        <p key={s.side}>
                          {s.side === "left" ? "Nguồn trái" : "Nguồn phải"}:{" "}
                          {s.in_scope_records} trong kỳ/phạm vi,{" "}
                          {s.out_of_scope_records} ngoài phạm vi,{" "}
                          {s.invalid_records} lỗi; {s.duplicate_key_rows} dòng
                          trùng khóa trong phạm vi.{" "}
                          {s.coverage_complete
                            ? "Nguồn đầy đủ kỳ"
                            : "Nguồn chưa đủ kỳ: kết quả có thể đang chờ"}
                          .
                        </p>
                      ))}
                    </Notice>
                  )}
                  {proposal && (
                    <div className="rule-approval">
                      <h3>Review trước khi chạy</h3>
                      <p>
                        {proposal.origin} · {proposal.proposal.status} ·{" "}
                        {draft.join_keys
                          .map((p) => `${p.left} ↔ ${p.right}`)
                          .join(", ")}
                      </p>
                      <p>{proposal.proposal.reasoning}</p>
                      {proposal.proposal.missing_requirements.map((m, i) => (
                        <p key={i}>{m}</p>
                      ))}
                      <p>
                        Quan hệ:{" "}
                        {draft.cardinality === "ONE_TO_ONE"
                          ? "Một — Một"
                          : draft.cardinality === "ONE_TO_MANY"
                            ? "Một — Nhiều"
                            : "Nhiều — Một"}
                        ; chỉ tiêu:{" "}
                        {draft.comparison_metrics
                          .map(
                            (m) =>
                              `${m.metric_id} (${m.currency}, ${m.amount_basis})`,
                          )
                          .join(", ")}
                        ; kỳ {draft.period_start || "chưa xác nhận"} đến{" "}
                        {draft.period_end || "chưa xác nhận"},{" "}
                        {draft.timezone || "chưa xác nhận múi giờ"}.
                      </p>
                      {!proposal.contract_id ? (
                        <button
                          className="button primary"
                          disabled={
                            busy ||
                            !scopeConfirmed ||
                            proposal.proposal.status !== "PROPOSED" ||
                            !proposal.proposal.plan ||
                            proposal.proposal.missing_requirements.length > 0
                          }
                          onClick={() =>
                            void action(async () => {
                              const rule = await api<{ id: string }>(
                                `/reconciliation-contracts/${proposal.id}/approve`,
                                { method: "POST" },
                              );
                              setProposal({
                                ...proposal,
                                contract_id: rule.id,
                              });
                              setMessage(
                                "Đã duyệt scope, grain, coverage và dấu số tiền theo nguồn. Có thể chạy đối soát.",
                              );
                            })
                          }
                        >
                          <CheckCheck size={16} />
                          Xác nhận quy tắc và dấu số tiền
                        </button>
                      ) : (
                        <button
                          className="button primary"
                          disabled={busy}
                          onClick={() =>
                            void action(async () => {
                              const accepted = await api<{
                                job_id: string;
                                run_id: string;
                              }>(
                                "/reconciliation-runs",
                                send({ contract_id: proposal.contract_id }),
                              );
                              await wait(accepted.job_id);
                              await refresh();
                              if (alive.current) setRunId(accepted.run_id);
                            })
                          }
                        >
                          <GitCompareArrows size={16} />
                          Chạy đối soát đã duyệt
                        </button>
                      )}
                    </div>
                  )}
                </>
              )}
              {templates.length > 0 && (
                <details>
                  <summary>Mẫu quy tắc đã duyệt</summary>
                  {templates.map((t) => (
                    <div className="template-row" key={t.id}>
                      <span>
                        {t.plan.name} · {t.plan.cardinality}
                      </span>
                      <button
                        className="text-button"
                        disabled={busy || !draft}
                        onClick={() =>
                          draft &&
                          void action(async () => {
                            const p = await api<Proposal>(
                              `/reconciliation-contracts/${t.id}/reuse`,
                              send({
                                left_canonical_id: draft.left.canonical_id,
                                right_canonical_id: draft.right.canonical_id,
                                period_start: draft.period_start,
                                period_end: draft.period_end,
                                left_coverage_start: draft.left.coverage_start,
                                left_coverage_end: draft.left.coverage_end,
                                right_coverage_start:
                                  draft.right.coverage_start,
                                right_coverage_end: draft.right.coverage_end,
                                completeness: draft.left.completeness,
                                snapshot_at: new Date().toISOString(),
                              }),
                            );
                            setProposal(p);
                            if (p.proposal.plan) setDraft(p.proposal.plan);
                          })
                        }
                      >
                        Tái sử dụng và review lại
                      </button>
                    </div>
                  ))}
                </details>
              )}
            </>
          )}
        </fieldset>
      )}
      {mode !== "home" && (
        <div className="card">
          <h3>Lịch sử các lần đối soát</h3>
          <div className="rule-grid">
            <label>
              Kỳ bắt đầu từ
              <input
                type="date"
                value={fromPeriod}
                onChange={(e) => {
                  setFromPeriod(e.target.value);
                  setRunOffset(0);
                }}
              />
            </label>
            <label>
              Kỳ kết thúc đến
              <input
                type="date"
                value={toPeriod}
                onChange={(e) => {
                  setToPeriod(e.target.value);
                  setRunOffset(0);
                }}
              />
            </label>
            <label>
              Lọc theo nguồn
              <select
                value={sourceFilter}
                onChange={(e) => {
                  setSourceFilter(e.target.value);
                  setRunOffset(0);
                }}
              >
                <option value="">Tất cả nguồn</option>
                {catalogue.map((c) => (
                  <option key={c.canonical.id} value={c.canonical.id}>
                    {c.name} · {c.canonical.id.slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="table-scroll">
            <table className="result-table">
              <thead>
                <tr>
                  <th>Lần đối soát</th>
                  <th>Kỳ</th>
                  <th>Trạng thái</th>
                  <th>Kết quả</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>{r.id.slice(0, 8)}</td>
                    <td>
                      {r.metric_snapshot?.period_start || "—"} /{" "}
                      {r.metric_snapshot?.period_end || "—"}
                    </td>
                    <td>{label(r.status)}</td>
                    <td>
                      <button
                        className="text-button"
                        onClick={() => setRunId(r.id)}
                      >
                        Mở kết quả
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="run-toolbar">
            <span>{runTotal} lần chạy</span>
            <button
              className="button secondary"
              disabled={!runOffset}
              onClick={() => setRunOffset(Math.max(0, runOffset - 25))}
            >
              Trang lần chạy trước
            </button>
            <button
              className="button secondary"
              disabled={runOffset + 25 >= runTotal}
              onClick={() => setRunOffset(runOffset + 25)}
            >
              Trang lần chạy sau
            </button>
          </div>
        </div>
      )}
      {listLoading ? (
        <Spinner />
      ) : runs.length === 0 && !error ? (
        <div className="card empty-state">
          <GitCompareArrows size={28} />
          <h3>Chưa có lần đối soát trong bộ lọc</h3>
          <p>
            Chọn hai nguồn canonical, xác nhận quy tắc rồi chạy để có kết quả đã
            kiểm chứng.
          </p>
        </div>
      ) : (
        <>
          <div className="run-toolbar">
            <label>
              Lần đối soát
              <select
                aria-label="Lần đối soát"
                value={runId}
                onChange={(e) => setRunId(e.target.value)}
              >
                {runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.id.slice(0, 8)} · {label(r.status)}
                  </option>
                ))}
              </select>
            </label>
            {run && <Badge status={run.status} />}
          </div>
          {runId && !run && !error && <Spinner />}
          {run?.id === runId && !snapshot && (
            <Notice tone="warning">
              {label(run.status)}. Chưa có KPI chính thức.
              {run.checks
                .filter((c) => !c.passed)
                .map((c) => (
                  <p key={c.name}>
                    {c.name}: {c.details}
                  </p>
                ))}
            </Notice>
          )}
          {snapshot && (
            <>
              <div className="result-kpis">
                {[
                  [
                    "Tỷ lệ khớp",
                    snapshot.full_match_rate.percent === null
                      ? "N/A"
                      : `${snapshot.full_match_rate.percent}%`,
                    `${snapshot.full_match_rate.numerator}/${snapshot.full_match_rate.denominator} đơn vị đủ điều kiện`,
                  ],
                  [
                    "Cần kiểm tra",
                    openCount === null ? "Đang tải…" : String(openCount),
                    "case đang mở hiện tại",
                  ],
                  [
                    "Giá trị lệch tuyệt đối",
                    snapshot.monetary[0]?.absolute_variance ?? "N/A",
                    `${snapshot.monetary[0]?.currency || ""} · ${snapshot.monetary[0]?.metric_id || ""}`,
                  ],
                  [
                    "Tự động phân loại",
                    snapshot.automation_coverage.percent === null
                      ? "N/A"
                      : `${snapshot.automation_coverage.percent}%`,
                    `${snapshot.automation_coverage.numerator}/${snapshot.automation_coverage.denominator} đơn vị đủ điều kiện; gồm thiếu đối ứng/lệch đã xác minh, không phải ngoại lệ đã xử lý`,
                  ],
                ].map(([name, value, detail]) => (
                  <article className="card" key={name}>
                    <span>{name}</span>
                    <strong>{value}</strong>
                    <small>{detail}</small>
                  </article>
                ))}
              </div>
              <div className="result-panels">
                <div className="card">
                  <h3>Trạng thái liên kết</h3>
                  <p className="muted">
                    Đếm nhóm kết quả, gồm cả ngoài phạm vi. Mẫu số KPI được công
                    bố riêng.
                  </p>
                  <StatusChart counts={snapshot.linkage_counts} />
                </div>
                <div className="card">
                  <h3>Phạm vi và mẫu số</h3>
                  <p>
                    {snapshot.period_start} đến trước {snapshot.period_end} ·{" "}
                    {snapshot.timezone}
                  </p>
                  <p>
                    {snapshot.comparison_unit ===
                    "Left canonical reference group"
                      ? "Một nhóm tham chiếu ở nguồn trái"
                      : "Một bản ghi chuẩn hóa tham chiếu ở nguồn trái"}
                  </p>
                  <p className="muted">
                    Đơn vị trong phạm vi có khóa, số tiền và tiền tệ hợp lệ.
                    Loại lỗi, ngoài kỳ, đang chờ và thiếu tiền nguồn trái khỏi
                    mẫu số. Đơn vị mơ hồ vẫn được tính để review. Tự động hóa là
                    phân loại đã kiểm chứng, không cần quyết định thủ công trên
                    từng đơn vị.
                  </p>
                  <p>
                    Đủ điều kiện: {snapshot.eligible_units}. Case tại thời điểm
                    chạy: {snapshot.unresolved_cases_at_run}.
                  </p>
                  {Object.entries(snapshot.excluded_counts).map(
                    ([key, value]) => (
                      <p key={key}>
                        Loại khỏi mẫu số: {label(key)} — {value}
                      </p>
                    ),
                  )}
                  {snapshot.monetary.map((m) => (
                    <p key={m.metric_id}>
                      {m.metric_id} ({m.currency}): chênh lệch signed{" "}
                      {m.signed_variance}, tuyệt đối {m.absolute_variance};{" "}
                      {m.comparable_groups} nhóm so sánh được.
                    </p>
                  ))}
                </div>
              </div>
              <div className="card">
                <div className="section-heading">
                  <h3>
                    {mode === "exceptions"
                      ? "Danh sách ngoại lệ"
                      : "Chi tiết đối soát"}
                  </h3>
                  <div className="rule-actions">
                    <button
                      className="button secondary"
                      disabled={busy || !canEdit}
                      onClick={() => void exportFile("csv")}
                    >
                      <ArrowDownToLine size={16} />
                      Xuất CSV
                    </button>
                    <button
                      className="button secondary"
                      disabled={busy || !canEdit}
                      onClick={() => void exportFile("xlsx")}
                    >
                      Xuất XLSX
                    </button>
                    {download && (
                      <a className="button primary" href={download} download>
                        Tải báo cáo
                      </a>
                    )}
                  </div>
                </div>
                <div className="result-filters">
                  <label>
                    Tìm kiếm
                    <input
                      value={search}
                      onChange={(e) => {
                        setSearch(e.target.value);
                        setOffset(0);
                      }}
                    />
                  </label>
                  <label>
                    Trạng thái
                    <select
                      value={filter}
                      onChange={(e) => {
                        setFilter(e.target.value);
                        setOffset(0);
                      }}
                    >
                      <option value="">Tất cả</option>
                      {(mode === "exceptions"
                        ? [
                            "OPEN",
                            "IN_REVIEW",
                            "RESOLVED",
                            "DISMISSED_WITH_REASON",
                          ]
                        : [
                            "LINKED",
                            "UNMATCHED",
                            "AMBIGUOUS",
                            "INVALID",
                            "OUT_OF_SCOPE",
                            "PENDING",
                          ]
                      ).map((s) => (
                        <option key={s} value={s}>
                          {label(s)}
                        </option>
                      ))}
                    </select>
                  </label>
                  {mode === "exceptions" && (
                    <>
                      <label>
                        Loại ảnh hưởng
                        <select
                          value={issueFilter}
                          onChange={(e) => {
                            setIssueFilter(e.target.value);
                            setOffset(0);
                          }}
                        >
                          <option value="">Tất cả loại</option>
                          {[
                            "AMOUNT_MISMATCH",
                            "ATTRIBUTE_MISMATCH",
                            "INVALID_DECIMAL",
                            "DUPLICATE_KEY",
                            "MISSING_COUNTERPART",
                            "UNCERTAIN_MATCH",
                            "INSUFFICIENT_COVERAGE",
                            "NOT_YET_SETTLED",
                            "RULE_UNVERIFIED",
                          ].map((s) => (
                            <option key={s} value={s}>
                              {label(s)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Sắp xếp
                        <select
                          value={caseSort}
                          onChange={(e) => setCaseSort(e.target.value)}
                        >
                          <option value="type">Loại ngoại lệ</option>
                          <option value="state">Trạng thái xử lý</option>
                        </select>
                      </label>
                    </>
                  )}
                </div>
                {exportNotice && <Notice>{exportNotice}</Notice>}
                {detailLoading && <Spinner />}
                <div className="table-scroll">
                  <table className="result-table">
                    <thead>
                      <tr>
                        {(mode === "exceptions"
                          ? [
                              "Loại ngoại lệ",
                              "Trạng thái xử lý",
                              "Ghi chú",
                              "Bằng chứng",
                            ]
                          : [
                              "Khóa",
                              "Liên kết",
                              "So sánh",
                              "Chênh lệch",
                              "Bằng chứng",
                            ]
                        ).map((c) => (
                          <th key={c}>{c}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {mode === "exceptions"
                        ? cases.map((c) => (
                            <tr key={c.id}>
                              <td>{label(c.type)}</td>
                              <td>{label(c.workflow_state)}</td>
                              <td>{c.notes || "Chưa có ghi chú"}</td>
                              <td>
                                <button
                                  className="text-button"
                                  onClick={() =>
                                    void openEvidence(c.match_group_id, c)
                                  }
                                >
                                  Xem ngoại lệ
                                </button>
                              </td>
                            </tr>
                          ))
                        : groups.map((g) => (
                            <tr key={g.id}>
                              <td>{g.key.join(" / ")}</td>
                              <td>{label(g.linkage_state)}</td>
                              <td>{label(g.comparison_state)}</td>
                              <td>
                                {g.comparisons.map((c) => (
                                  <div key={c.metric_id}>
                                    {c.delta ?? "N/A"} {c.currency}
                                  </div>
                                ))}
                              </td>
                              <td>
                                <button
                                  className="text-button"
                                  onClick={() => void openEvidence(g.id)}
                                >
                                  Xem bằng chứng
                                </button>
                              </td>
                            </tr>
                          ))}
                    </tbody>
                  </table>
                </div>
                {!detailLoading &&
                  !error &&
                  (mode === "exceptions" ? cases.length : groups.length) ===
                    0 && (
                    <Notice>
                      {mode === "exceptions"
                        ? "Không có ngoại lệ phù hợp bộ lọc này."
                        : "Không có nhóm kết quả phù hợp bộ lọc này."}{" "}
                      Có thể đổi bộ lọc hoặc xem lần đối soát khác; số liệu đã
                      xác minh được giữ nguyên.
                    </Notice>
                  )}
                <div className="run-toolbar">
                  <span>
                    {detailLoading
                      ? "Đang tải kết quả…"
                      : `${mode === "exceptions" ? caseTotal : total} kết quả · trang ${Math.floor(offset / 25) + 1}`}
                  </span>
                  <button
                    className="button secondary"
                    disabled={!offset || detailLoading}
                    onClick={() => setOffset(Math.max(0, offset - 25))}
                  >
                    Trước
                  </button>
                  <button
                    className="button secondary"
                    disabled={
                      detailLoading ||
                      offset + 25 >= (mode === "exceptions" ? caseTotal : total)
                    }
                    onClick={() => setOffset(offset + 25)}
                  >
                    Sau
                  </button>
                </div>
              </div>
            </>
          )}
        </>
      )}
      {evidence && evidenceRunId === runId && (
        <ReconciliationEvidence
          key={`${runId}:${evidence.group.id}`}
          evidence={evidence}
          currentCase={currentCase}
          canEdit={canEdit}
          returnFocus={evidenceTrigger}
          onClose={() => setEvidence(null)}
          onReviewed={async () => {
            setEvidence(null);
            await refresh();
            setMessage(
              "Đã lưu review. Comparison và snapshot của lần chạy được giữ nguyên.",
            );
          }}
        />
      )}
    </section>
  );
}
