import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Notice, Spinner } from "./components";
import { AgentResultBlocks } from "./AgentResultBlocks";
import type { DraftField, NormalizationDraft, Review, Workflow } from "./agentTypes";
import type { AssistantContext, Suggestion } from "./assistantTypes";
import { label, type Plan, type Catalogue, type Slot } from "./reconciliationTypes";
function proposedPlan(review: Review, catalogue: Catalogue[]): Plan | null {
    const request = review.planning_request, s = review.suggestions;
    if (!request || !s || !s.join_keys.length || !s.comparison_metrics.length || !s.cardinality || !s.aggregation || !s.comparison_grain)
        return null;
    const left = catalogue.find(c => c.canonical.id === request.left.canonical_id);
    const right = catalogue.find(c => c.canonical.id === request.right.canonical_id);
    if (!left || !right)
        return null;
    const slot = (side: "left" | "right"): Slot => ({ ...{ canonical_id: request[side].canonical_id,
            role: side === "left" ? s.left_role : s.right_role, date_field: "", time_basis: "", currency_field: null,
            filters: {}, coverage_start: "", coverage_end: "", completeness: "", snapshot_at: "", settlement_due_at: null },
        ...request[side] });
    return { name: "Đối soát đã xác nhận", entity_kind: left.schema_definition.entity_kind,
        left: slot("left"), right: slot("right"), join_keys: s.join_keys, comparison_metrics: s.comparison_metrics,
        attributes: [], comparison_grain: s.comparison_grain, cardinality: s.cardinality, aggregation: s.aggregation,
        period_start: request.period_start || "", period_end: request.period_end || "", timezone: request.timezone || "",
        effective_from: request.effective_from || "", effective_to: request.effective_to || null,
        allow_partial: request.allow_partial || false, duplicate_policy: "REVIEW", fuzzy_fields: [], fuzzy_block_keys: [],
        fuzzy_min_score: 85, fuzzy_top_k: 3, evidence_ids: s.evidence_ids };
}
const states: Record<string, string> = { CREATED: "Đã nhận yêu cầu", RUNNING: "Đang thực hiện",
    WAITING_REVIEW: "Cần bạn xác nhận", COMPLETED: "Đã hoàn thành", PARTIAL: "Hoàn thành một phần",
    FAILED: "Xử lý thất bại", BLOCKED: "Chưa thể tiếp tục", CANCELLED_BEFORE_NEXT_STEP: "Đã dừng các bước tiếp theo" };
const tools: Record<string, string> = { parse: "Đọc dữ liệu", propose_mapping: "Chuẩn bị đề xuất",
    run_normalization: "Chuẩn hóa", prepare_reconciliation_plan: "Đề xuất quy tắc đối soát",
    run_approved_reconciliation: "Đối soát và kiểm chứng", start_export: "Tạo báo cáo",
    query_dataset: "Tra cứu dữ liệu", read_verified_facts: "Đọc kết quả đã xác minh" };
function MappingReview({ draft, onChange, disabled }: {
    draft: NormalizationDraft;
    onChange: (draft: NormalizationDraft) => void;
    disabled: boolean;
}) {
    function field(index: number, patch: Partial<DraftField>) { onChange({ ...draft, fields: draft.fields.map((f, i) => i === index ? { ...f, ...patch } : f) }); }
    return <div className="agent-review-fields"><label>Loại dữ liệu<input value={draft.entity_kind} disabled={disabled} onChange={e => onChange({ ...draft, entity_kind: e.target.value })}/></label>
    <label>Mỗi dòng thể hiện điều gì?<input value={draft.grain} disabled={disabled} onChange={e => onChange({ ...draft, grain: e.target.value })}/></label>
    {draft.fields.map((f, i) => <details key={f.source_field} open={f.data_type !== "string" || !!f.question || f.business_key} className="agent-field">
      <summary>{f.name} · {f.data_type === "decimal" ? "Số tiền" : f.data_type === "date" ? "Ngày" : "Giữ nguyên văn bản"}</summary>
      {f.question && <p>{f.question}</p>}<div className="agent-form-grid">
      <label>Tên trường<input value={f.name} disabled={disabled} onChange={e => field(i, { name: e.target.value })}/></label>
      <label>Kiểu dữ liệu<select value={f.data_type} disabled={disabled} onChange={e => field(i, { data_type: e.target.value as DraftField["data_type"] })}><option value="string">Văn bản, giữ nguyên mã</option><option value="decimal">Số tiền chính xác</option><option value="date">Ngày và múi giờ</option></select></label>
      <label><input type="checkbox" checked={f.business_key} disabled={disabled} onChange={e => field(i, { business_key: e.target.checked })}/>Trường khóa nghiệp vụ</label>
      {f.data_type === "decimal" && <>
        <label>Ý nghĩa số tiền<input value={f.semantic_metric || ""} disabled={disabled} placeholder="Ví dụ: delivery_charge" onChange={e => field(i, { semantic_metric: e.target.value || null })}/></label>
        <label>Cơ sở số tiền<select value={f.amount_basis || ""} disabled={disabled} onChange={e => field(i, { amount_basis: e.target.value || null })}><option value="">Chưa xác định</option>{Array.from(new Set(["gross", "net", "paid", "due", ...(f.amount_basis ? [f.amount_basis] : [])])).map(v => <option key={v} value={v}>{v}</option>)}</select></label>
        <label>Tiền tệ<input value={f.currency || ""} disabled={disabled} placeholder="VND / USD" maxLength={3} onChange={e => field(i, { currency: e.target.value.toUpperCase() || null })}/></label>
        <label>Đơn vị<input value={f.unit || ""} disabled={disabled} placeholder="VND" onChange={e => field(i, { unit: e.target.value || null })}/></label>
        <label>Định dạng số<select value={f.locale || ""} disabled={disabled} onChange={e => field(i, { locale: e.target.value as DraftField["locale"] })}><option value="">Cần xác nhận</option><option value="en-US">1,234.56</option><option value="vi-VN">1.234,56</option></select></label>
      </>}
      {f.data_type === "date" && <><label>Định dạng ngày<select value={f.date_format || ""} disabled={disabled} onChange={e => field(i, { date_format: e.target.value || null })}><option value="">Cần xác nhận</option>{Array.from(new Set(["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", ...(f.date_format ? [f.date_format] : [])])).map(v => <option value={v} key={v}>{({ "%Y-%m-%d": "2026-10-31", "%d/%m/%Y": "31/10/2026", "%m/%d/%Y": "10/31/2026" } as Record<string, string>)[v] || v}</option>)}</select></label>
        <label>Múi giờ<input value={f.timezone || ""} disabled={disabled} placeholder="Asia/Ho_Chi_Minh / UTC" onChange={e => field(i, { timezone: e.target.value || null })}/></label></>}
      {f.data_type === "string" && <label>Ý nghĩa trạng thái (nếu có)<select value={f.semantic_metric || ""} disabled={disabled} onChange={e => field(i, { semantic_metric: e.target.value || null })}><option value="">Văn bản / chưa xác nhận</option><option value="payment_status">Trạng thái thanh toán, có bằng chứng</option>{f.semantic_metric && f.semantic_metric !== "payment_status" && <option value={f.semantic_metric}>{f.semantic_metric}</option>}</select></label>}
      </div></details>)}
  </div>;
}
function PlanReview({ plan, onChange, disabled }: {
    plan: Plan;
    onChange: (plan: Plan) => void;
    disabled: boolean;
}) {
    return <div className="agent-review-fields"><p>Khóa: {plan.join_keys.map(k => `${k.left} ↔ ${k.right}`).join(", ")}</p><p>{plan.comparison_grain} · {label(plan.cardinality)} · {label(plan.aggregation)}</p>
    {plan.comparison_metrics.map(m => <p key={m.metric_id}>{m.metric_id} · {m.amount_basis} · {m.currency} · sai số {m.absolute_tolerance}</p>)}
    <div className="agent-form-grid">{(["period_start", "period_end", "effective_from"] as const).map(k => <label key={k}>{{ period_start: "Bắt đầu kỳ", period_end: "Kết thúc kỳ (không bao gồm)", effective_from: "Quy tắc có hiệu lực từ" }[k]}<input type="date" value={plan[k]} disabled={disabled} onChange={e => onChange({ ...plan, [k]: e.target.value })}/></label>)}
    <label>Múi giờ<input value={plan.timezone} disabled={disabled} onChange={e => onChange({ ...plan, timezone: e.target.value })}/></label></div>
    {(["left", "right"] as const).map(side => <fieldset key={side}><legend>{side === "left" ? "Nguồn trái" : "Nguồn phải"} · {plan[side].role}</legend><div className="agent-form-grid">
      <label>Trường ngày<input value={plan[side].date_field} disabled={disabled} onChange={e => onChange({ ...plan, [side]: { ...plan[side], date_field: e.target.value } })}/></label>
      <label>Ý nghĩa ngày<input value={plan[side].time_basis} disabled={disabled} onChange={e => onChange({ ...plan, [side]: { ...plan[side], time_basis: e.target.value } })}/></label>
      {(["coverage_start", "coverage_end", "snapshot_at"] as const).map(key => <label key={key}>{{ coverage_start: "Dữ liệu đầy đủ từ (ISO và timezone)", coverage_end: "Dữ liệu đầy đủ đến (không bao gồm)", snapshot_at: "Thời điểm chốt dữ liệu" }[key]}<input value={plan[side][key]} disabled={disabled} onChange={e => onChange({ ...plan, [side]: { ...plan[side], [key]: e.target.value } })}/></label>)}
      <label>Độ đầy đủ<select value={plan[side].completeness} disabled={disabled} onChange={e => onChange({ ...plan, [side]: { ...plan[side], completeness: e.target.value } })}><option value="">Chưa xác nhận</option><option value="CONFIRMED">Đã xác nhận đầy đủ</option><option value="INCOMPLETE">Chưa đầy đủ</option><option value="UNKNOWN">Chưa xác định</option></select></label></div></fieldset>)}
    <details><summary>Thông số quy tắc</summary><p>Khóa, chỉ tiêu, cardinality và sai số ở trên là đề xuất; trả lời bằng tiếng Việt để chỉnh lại trước khi duyệt.</p><p>Bộ lọc trái: {JSON.stringify(plan.left.filters)} · phải: {JSON.stringify(plan.right.filters)}</p></details>
  </div>;
}
function ReviewCard({ review, workflow, canEdit, refresh }: {
    review: Review;
    workflow: Workflow;
    canEdit: boolean;
    refresh: () => Promise<void>;
}) {
    const [draft, setDraft] = useState(review.normalization_draft);
    const [plan, setPlan] = useState(review.plan);
    const [reply, setReply] = useState("");
    const [confirmed, setConfirmed] = useState(false);
    const [extraction, setExtraction] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const alive = useRef(true);
    const pending = useRef<{
        body: string;
        key: string;
    } | null>(null);
    useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
    useEffect(() => {
        if (review.kind !== "RECONCILIATION" || review.plan)
            return;
        const controller = new AbortController();
        void api<{
            items: Catalogue[];
        }>(`/projects/${workflow.context.project_id}/canonical-catalogue`, { signal: controller.signal })
            .then(data => { if (!controller.signal.aborted)
            setPlan(proposedPlan(review, data.items)); })
            .catch(err => { if (!controller.signal.aborted)
            setError(String(err)); });
        return () => controller.abort();
    }, [review.id, review.nonce]);
    const disabled = busy || !canEdit || !!review.pending_reply_job_id;
    async function action(kind: "decision" | "reply") {
        setBusy(true);
        setError("");
        try {
            const decision = review.kind === "MAPPING" ? { type: "MAPPING", draft, extraction_reviewed: extraction } :
                review.kind === "RECONCILIATION" ? { type: "RECONCILIATION", plan } : { type: "CLARIFICATION", intent: review.reply_intent };
            const body = JSON.stringify({ review_id: review.id, nonce: review.nonce,
                fingerprint: review.fingerprint, ...(kind === "reply" ? { text: reply } : { decision }) });
            if (pending.current?.body !== body)
                pending.current = { body, key: crypto.randomUUID() };
            await api(`/agent/workflows/${workflow.id}/${kind === "reply" ? "replies" : "decisions"}`, { method: "POST",
                headers: { "Idempotency-Key": pending.current.key }, body });
            if (alive.current) {
                pending.current = null;
                setReply("");
                await refresh();
            }
        }
        catch (err) {
            if (alive.current)
                setError(err instanceof Error ? err.message : "Không lưu được quyết định.");
        }
        finally {
            if (alive.current)
                setBusy(false);
        }
    }
    const ready = review.kind === "MAPPING" ? !!draft?.fields.every(f => f.data_type === "string" || (f.data_type === "decimal" ? f.locale && f.semantic_metric && f.amount_basis && f.currency && f.unit : f.date_format && f.timezone)) :
        review.kind === "RECONCILIATION" ? !!plan?.period_start && !!plan.period_end && !!plan.timezone && !!plan.effective_from && [plan.left, plan.right].every(s => s.date_field && s.time_basis && s.coverage_start && s.coverage_end && s.snapshot_at && s.completeness) : !!review.reply_intent;
    return <section className="agent-review card" aria-label="Quyết định cần xác nhận"><h4>{review.question}</h4><p>{review.reason}</p>
    {error && <Notice tone="error">{error}</Notice>}{review.reply_questions.map(q => <Notice key={q}>{q}</Notice>)}
    {draft && <MappingReview draft={draft} disabled={disabled} onChange={v => { setDraft(v); setConfirmed(false); }}/>}
    {plan && <PlanReview plan={plan} disabled={disabled} onChange={v => { setPlan(v); setConfirmed(false); }}/>}
    {review.kind === "RECONCILIATION" && !plan && <Notice>Cần bổ sung kỳ, múi giờ và độ đầy đủ bằng câu trả lời bên dưới. Chưa có quy tắc đủ điều kiện chạy.</Notice>}
    {review.reply_intent && <p>Thao tác sẽ thực hiện: {review.reply_intent.intent}</p>}
    <div className="agent-reply"><label>Bổ sung hoặc sửa bằng tiếng Việt<textarea value={reply} maxLength={2000} disabled={disabled} onChange={e => setReply(e.target.value)} placeholder="Ví dụ: cột tiền là gross VND, ngày theo UTC; cần xem lại đề xuất trước khi duyệt."/></label><button className="button secondary" disabled={disabled || !reply.trim()} onClick={() => void action("reply")}>Đọc câu trả lời và xem lại</button></div>
    {review.pending_reply_job_id && <Spinner />}<p className="muted">Câu trả lời được diễn giải để bạn kiểm tra; hệ thống chưa phê duyệt thay bạn.</p>
    {draft && <label><input type="checkbox" checked={extraction} disabled={disabled} onChange={e => setExtraction(e.target.checked)}/>Tôi đã kiểm tra cảnh báo/vùng bảng nguồn nếu có.</label>}
    <label><input type="checkbox" checked={confirmed} disabled={disabled} onChange={e => setConfirmed(e.target.checked)}/>Tôi xác nhận các lựa chọn ở trên và cho phép tiếp tục.</label>
    <button className="button primary" disabled={disabled || !confirmed || !ready} onClick={() => void action("decision")}>Xác nhận và tiếp tục</button>
  </section>;
}
export function AgentWorkflowPanel({ id, canEdit, onNavigate, onContext }: {
    id: string;
    canEdit: boolean;
    onNavigate: (target: Suggestion, context: AssistantContext) => void;
    onContext: (context: AssistantContext) => void;
}) {
    const [workflow, setWorkflow] = useState<Workflow | null>(null);
    const [error, setError] = useState("");
    const alive = useRef(true);
    const sequence = useRef(0);
    const controller = useRef(new AbortController());
    const current = useRef<Workflow | null>(null);
    const contextCallback = useRef(onContext);
    contextCallback.current = onContext;
    async function refresh() { const seq = ++sequence.current; try {
        const row = await api<Workflow>(`/agent/workflows/${id}`, { signal: controller.current.signal });
        if (alive.current && seq === sequence.current) {
            current.current = row;
            setWorkflow(old => old?.updated_at === row.updated_at ? old : row);
            setError("");
            contextCallback.current(row.context);
        }
    }
    catch (err) {
        if (alive.current && seq === sequence.current)
            setError(err instanceof Error ? err.message : "Không tải được công việc.");
    } }
    useEffect(() => {
        alive.current = true;
        controller.current = new AbortController();
        let timer: ReturnType<typeof setTimeout>;
        let attempts = 0;
        const poll = async () => { await refresh(); if (alive.current && !['COMPLETED', 'BLOCKED', 'FAILED', 'PARTIAL', 'CANCELLED_BEFORE_NEXT_STEP'].includes(current.current?.state || ''))
            timer = setTimeout(() => void poll(), Math.min(4000, 800 + attempts++ * 150)); };
        void poll();
        return () => { alive.current = false; sequence.current++; controller.current.abort(); clearTimeout(timer); };
    }, [id]);
    async function cancel() { try {
        await api(`/agent/workflows/${id}/cancel`, { method: "POST" });
        await refresh();
    }
    catch (err) {
        if (alive.current)
            setError(String(err));
    } }
    return <section className="agent-workflow" aria-label="Công việc của Trợ lý">{error && <Notice tone="error">{error}<button className="text-button" onClick={() => void refresh()}>Cập nhật</button></Notice>}
    {!workflow ? <Spinner /> : <><p className="agent-workflow-state"><strong>{states[workflow.state] || workflow.state}</strong>{["CREATED", "RUNNING", "WAITING_REVIEW"].includes(workflow.state) && <button className="text-button" onClick={() => void cancel()}>Dừng bước tiếp theo</button>}</p>
      {workflow.detail.error_code && <Notice tone="warning">Cần kiểm tra: {workflow.detail.error_code}. Dữ liệu và kết quả đã lưu được giữ.</Notice>}
      <ol className="agent-steps">{workflow.detail.steps.map((s, i) => <li key={i}>{tools[s.tool] || s.tool} · {label(s.status)}</li>)}</ol>
      {workflow.detail.reviews.filter(r => r.state === "OPEN").map(r => <ReviewCard key={`${r.id}:${r.nonce}`} review={r} workflow={workflow} canEdit={canEdit && workflow.state === "WAITING_REVIEW"} refresh={refresh}/>)}
      <AgentResultBlocks blocks={workflow.detail.blocks} context={workflow.context} onNavigate={onNavigate}/>
    </>}</section>;
}
