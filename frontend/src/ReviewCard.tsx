import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Notice, Spinner } from "./components";
import type { DraftField, NormalizationDraft, Review, Workflow, MappingAssessment } from "./agentTypes";
import { label, type Plan, type Catalogue, type Slot } from "./reconciliationTypes";
import { errorText as errors } from "./types";
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
        // Missing optional facts can be explicit null; keep editable defaults.
        // Explicit false, zero and filters remain part of the reviewed proposal.
        ...Object.fromEntries(Object.entries(request[side]).filter(([, value]) => value !== null && value !== undefined)) });
    return { name: "Đối soát hai nguồn", entity_kind: left.schema_definition.entity_kind,
        left: slot("left"), right: slot("right"), join_keys: s.join_keys, comparison_metrics: s.comparison_metrics,
        attributes: [], comparison_grain: s.comparison_grain, cardinality: s.cardinality, aggregation: s.aggregation,
        period_start: request.period_start || "", period_end: request.period_end || "", timezone: request.timezone || "",
        effective_from: request.effective_from || "", effective_to: request.effective_to || null,
        allow_partial: request.allow_partial || false, duplicate_policy: "REVIEW", fuzzy_fields: [], fuzzy_block_keys: [],
        fuzzy_min_score: 85, fuzzy_top_k: 3, evidence_ids: s.evidence_ids };
}
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
function storedDraft(key: string, review: Review) {
    try {
        const saved = JSON.parse(sessionStorage.getItem(key) || "null");
        if (!saved || saved.base !== JSON.stringify([review.normalization_draft, review.plan, review.planning_request, review.suggestions])) return null;
        if (saved.draft && (!review.normalization_draft || typeof saved.draft.entity_kind !== "string" || typeof saved.draft.grain !== "string" || saved.draft.table_id !== review.resource_id ||
            !Array.isArray(saved.draft.fields) || saved.draft.fields.length !== review.normalization_draft.fields.length ||
            !saved.draft.fields.every((f: DraftField, i: number) => f && f.source_field === review.normalization_draft?.fields[i].source_field && f.target_id === review.normalization_draft.fields[i].target_id && typeof f.name === "string" && typeof f.data_type === "string"))) return null;
        if (saved.plan && (!saved.plan.left || !saved.plan.right || !Array.isArray(saved.plan.join_keys) || !Array.isArray(saved.plan.comparison_metrics) ||
            saved.plan.left.canonical_id !== review.planning_request?.left.canonical_id || saved.plan.right.canonical_id !== review.planning_request?.right.canonical_id)) return null;
        return saved as {draft: NormalizationDraft | null; plan: Plan | null; extraction: boolean};
    } catch { return null; }
}

export function ReviewCard({ review, workflow, canEdit, draftOwner, refresh, onReply }: {
    review: Review;
    workflow: Workflow;
    canEdit: boolean;
    draftOwner: string;
    refresh: () => Promise<void>;
    onReply?: (workflowId:string,review:Review)=>void;
}) {
    const storageKey = `studio.review-draft.${draftOwner}.${workflow.id}.${review.id}.${review.nonce}.${review.fingerprint}`;
    const cached = useRef(storedDraft(storageKey, review)).current;
    const [draft, setDraft] = useState(cached?.draft ?? review.normalization_draft ?? null);
    const [plan, setPlan] = useState(cached?.plan ?? review.plan ?? null);
    const [assessment,setAssessment]=useState<MappingAssessment|null>(null);
    const [checking,setChecking]=useState(false);
    const [assessmentSignature,setAssessmentSignature]=useState('');
    const draftSignature=JSON.stringify(draft);
    useEffect(()=>{
      if(!draft)return;
      const controller=new AbortController();
      setAssessment(null);setChecking(true);
      const timer=setTimeout(()=>{
        void api<MappingAssessment>('/agent/mapping-preflight',{method:'POST',body:draftSignature,signal:controller.signal})
        .then(result=>{if(!controller.signal.aborted){setAssessment(result);setAssessmentSignature(draftSignature);setError('');}})
        .catch(err=>{if(!controller.signal.aborted)setError(err instanceof Error?err.message:'Không kiểm tra được đề xuất.');})
        .finally(()=>{if(!controller.signal.aborted)setChecking(false);});
      },250);
      return()=>{clearTimeout(timer);controller.abort();};
    },[draftSignature]);
    const [catalogue,setCatalogue]=useState<Catalogue[]>([]);
    const submitting = useRef(false);
    const [extraction, setExtraction] = useState(cached?.extraction || false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [expired, setExpired] = useState(Date.now() >= Date.parse(review.expires_at));
    const [replyOpen, setReplyOpen] = useState(false);
    const replyKey = `studio.inline-review-reply.${draftOwner}.${workflow.id}.${review.id}`;
    const [replyText, setReplyText] = useState(() => {try{return sessionStorage.getItem(replyKey) || "";}catch{return "";}});
    const replyPending = useRef<{body: string; key: string} | null>((() => {try{
        const saved=JSON.parse(sessionStorage.getItem(`${replyKey}.pending`)||"null");
        return saved&&typeof saved.body==="string"&&typeof saved.key==="string"?saved:null;
    }catch{return null;}})());
    useEffect(() => {
        let timer: ReturnType<typeof setTimeout>;
        function tick() {
            const remaining=Date.parse(review.expires_at)-Date.now();
            if(remaining<=0)setExpired(true);
            else timer=setTimeout(tick,Math.min(remaining+20,2147483647));
        }
        tick();
        return () => clearTimeout(timer);
    }, [review.expires_at]);
    useEffect(() => {
        try { sessionStorage.setItem(storageKey, JSON.stringify({
            base: JSON.stringify([review.normalization_draft, review.plan, review.planning_request, review.suggestions]),
            draft, plan, extraction,
        })); } catch { /* Server save stays available when browser storage is full. */ }
    }, [storageKey, draft, plan, extraction]);
    const alive = useRef(true);
    const pending = useRef<{
        body: string;
        key: string;
    } | null>(null);
    useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
    useEffect(() => {
        if (review.kind !== "RECONCILIATION")
            return;
        const controller = new AbortController();
        void api<{
            items: Catalogue[];
        }>(`/projects/${workflow.context.project_id}/canonical-catalogue`, { signal: controller.signal })
            .then(data => { if (!controller.signal.aborted){
            setCatalogue(data.items);if(!review.plan&&!cached?.plan)setPlan(proposedPlan(review, data.items));} })
            .catch(err => { if (!controller.signal.aborted)
            setError(String(err)); });
        return () => controller.abort();
    }, [review.id, review.nonce]);
    const disabled = busy || !canEdit || expired || !!review.pending_reply_job_id;
    const replyDisabled = disabled || workflow.state !== "WAITING_REVIEW";
    function preserveLocal(next: Review) {
        const key=`studio.review-draft.${draftOwner}.${workflow.id}.${next.id}.${next.nonce}.${next.fingerprint}`;
        try { sessionStorage.setItem(key,JSON.stringify({
            base:JSON.stringify([next.normalization_draft,next.plan,next.planning_request,next.suggestions]),
            draft,plan,extraction,
        })); } catch { /* server draft remains the durable source */ }
    }
    async function savePreview() {
        const base = {review_id: review.id, nonce: review.nonce, fingerprint: review.fingerprint};
        if (review.kind === "CLARIFICATION") return review;
        if (JSON.stringify(draft) === JSON.stringify(review.normalization_draft ?? null) &&
            JSON.stringify(plan) === JSON.stringify(review.plan || proposedPlan(review, catalogue))) return review;
        const facts = plan && {
            ...Object.fromEntries(["period_start", "period_end", "timezone", "effective_from", "effective_to", "allow_partial"].map(k => {const value=plan[k as keyof Plan];return [k,value===""?null:value??null];})),
            ...Object.fromEntries((["left", "right"] as const).map(side => [side, Object.fromEntries(Object.entries(plan[side]).map(([k,v]) => [k, v === "" ? null : v]))])),
        };
        const body = {...base, ...(draft ? {draft} : ready && plan ? {plan} : {planning_request: facts || review.planning_request})};
        const saved = await api<Workflow>(`/agent/workflows/${workflow.id}/draft`, {method: "POST", body: JSON.stringify(body)});
        try { sessionStorage.removeItem(storageKey); } catch { /* server draft was saved */ }
        const next = saved.detail.reviews.find(r => r.id === review.id);
        if (!next) throw new Error("Không tìm thấy bản nháp vừa lưu.");
        preserveLocal(next);
        return next;
    }
    async function saveOrRenew(renew = false) {
        if (busy || !canEdit || review.pending_reply_job_id) return;
        setBusy(true); setError("");
        try {
            if (renew) {
                const row=await api<Workflow>(`/agent/workflows/${workflow.id}/renew-review`, {method: "POST", body: JSON.stringify({review_id: review.id, nonce: review.nonce, fingerprint: review.fingerprint})});
                const next=row.detail.reviews.find(r=>r.id===review.id);if(next)preserveLocal(next);
            }
            else await savePreview();
            await refresh();
        } catch (err) { setError(err instanceof Error ? err.message : "Không lưu được bản nháp."); }
        finally { setBusy(false); }
    }
    async function requestReply() {
        if (replyDisabled) return;
        if (!onReply) { setReplyOpen(true); return; }
        setBusy(true); setError("");
        try { const next = await savePreview(); onReply(workflow.id, next); await refresh(); }
        catch (err) { setError(err instanceof Error ? err.message : "Không lưu được bản nháp."); }
        finally { setBusy(false); }
    }
    async function sendInlineReply() {
        if (replyDisabled || !replyText.trim()) return;
        setBusy(true); setError("");
        try {
            const next = replyPending.current ? review : await savePreview();
            const body = JSON.stringify({review_id: next.id, nonce: next.nonce, fingerprint: next.fingerprint,
                text: replyText.trim(), ...(workflow.detail.model_choice ? {model_choice: workflow.detail.model_choice} : {})});
            if (!replyPending.current) replyPending.current = {body, key: crypto.randomUUID()};
            try {sessionStorage.setItem(`${replyKey}.pending`,JSON.stringify(replyPending.current));}catch{/* memory key remains stable */}
            await api(`/agent/workflows/${workflow.id}/replies`, {method: "POST", body: replyPending.current.body, headers: {"Idempotency-Key": replyPending.current.key}});
            replyPending.current = null; setReplyText("");try{sessionStorage.removeItem(replyKey);sessionStorage.removeItem(`${replyKey}.pending`);}catch{/* job is durably accepted */} await refresh();
        } catch (err) { setError(err instanceof Error ? err.message : "Không gửi được câu trả lời."); }
        finally { setBusy(false); }
    }
    const sourceName=(id:string)=>catalogue.find(c=>c.canonical.id===id)?.name||"Nguồn đã chọn";
    const fieldName=(id:string,field:string)=>catalogue.find(c=>c.canonical.id===id)?.schema_definition.fields.find(f=>f.id===field)?.name||field;
    async function action(intent = review.reply_intent) {
        if (submitting.current || disabled) return;
        submitting.current = true;
        setBusy(true);
        setError("");
        try {
            const decision = review.kind === "MAPPING" ? { type: "MAPPING", draft, extraction_reviewed: extraction } :
                review.kind === "RECONCILIATION" ? { type: "RECONCILIATION", plan } : { type: "CLARIFICATION", intent };
            const body = JSON.stringify({ review_id: review.id, nonce: review.nonce,
                fingerprint: review.fingerprint, decision });
            if (pending.current?.body !== body)
                pending.current = { body, key: crypto.randomUUID() };
            await api(`/agent/workflows/${workflow.id}/decisions`, { method: "POST",
                headers: { "Idempotency-Key": pending.current.key }, body });
            if (alive.current) {
                pending.current = null;
                await refresh();
            }
        }
        catch (err) {
            if (alive.current)
                setError(err instanceof Error ? err.message : "Không lưu được quyết định.");
        }
        finally {
            submitting.current = false;
            if (alive.current)
                setBusy(false);
        }
    }
    const ready = review.kind === "MAPPING" ? !!assessment?.preflight_ready && assessmentSignature===draftSignature && !checking && (review.extraction_review_required!==true||extraction) && !!draft?.fields.every(f => f.data_type === "string" || (f.data_type === "decimal" ? f.locale && f.semantic_metric && f.amount_basis && f.currency && f.unit : f.date_format && f.timezone)) :
        review.kind === "RECONCILIATION" ? !!plan?.period_start && !!plan.period_end && !!plan.timezone && !!plan.effective_from && [plan.left, plan.right].every(s => s.date_field && s.time_basis && s.coverage_start && s.coverage_end && s.snapshot_at && s.completeness) : !!review.reply_intent;
    if (review.kind === "CLARIFICATION") return <section className="agent-clarification" aria-label="Câu hỏi bổ sung">
      <p>{review.question}</p>
      {error && <Notice tone="error">{error}</Notice>}
      {review.reply_questions.filter(q=>q!==review.question).map(q=><p key={q}>{q}</p>)}
      <div className="clarification-options">{review.options?.map(option=><button className="button secondary" key={option.id} disabled={disabled} onClick={()=>void action(option.intent)}>{option.label}</button>)}</div>
      {review.reply_intent && !review.options?.length && <button className="button secondary" disabled={disabled} onClick={()=>void action()}>Tiếp tục yêu cầu này</button>}
      {expired && <Notice>Thẻ đã hết thời hạn.<button type="button" disabled={busy || !canEdit || !!review.pending_reply_job_id} onClick={()=>void saveOrRenew(true)}>Mở lại thẻ xác nhận</button></Notice>}
      <button className="text-button" disabled={replyDisabled} onClick={()=>void requestReply()}>Trả lời bằng tiếng Việt</button>
      {review.pending_reply_job_id && <p role="status"><Spinner/> Đang đọc câu trả lời của bạn…</p>}
    </section>;
    return <section className="agent-review" aria-label="Quyết định cần xác nhận">{review.resource_label&&<strong>{review.resource_label}</strong>}<h4>{review.question}</h4><p>{review.reason}</p>
    {error && <Notice tone="error">{error}</Notice>}{review.reply_questions.map(q => <Notice key={q}>{q}</Notice>)}
    {draft && <>
      <p>Tôi đã phân tích dữ liệu và chuẩn bị đề xuất chuẩn hóa.</p>
      {checking && <p role="status"><Spinner/> Đang kiểm tra toàn bộ dữ liệu…</p>}
      {assessment && <>
        <p>{draft.fields.length} cột · {assessment.source_rows} dòng. {assessment.verified_fields} trường đã kiểm tra kỹ thuật; {assessment.pending_fields} trường cần xác nhận.</p>
        <details><summary>Đã xác định bằng bằng chứng</summary><ul>{assessment.checks.filter(c=>c.state==='VERIFIED').map(c=><li key={c.field_id}><strong>{c.name}</strong>{c.messages.map(m=><p key={m}>{m}</p>)}</li>)}</ul><p>Các phép kiểm kỹ thuật không tự xác nhận ý nghĩa nghiệp vụ. Bạn vẫn kiểm tra và duyệt đề xuất.</p></details>
        {assessment.questions.length>0 && <section aria-label="Thông tin cần xác nhận"><h4>Cần bạn xác nhận</h4><ul>{assessment.questions.map(q=><li key={q}>{q}</li>)}</ul></section>}
        <details open={assessment.checks.some(c=>c.affected_rows>0)}><summary>Dữ liệu bất thường</summary>{assessment.checks.filter(c=>c.affected_rows>0||c.messages.some(m=>m.includes('nhiều tiền tệ'))).map(c=><p key={c.field_id}>{c.name}: {c.affected_rows} dòng lỗi chuyển đổi. {Object.entries(c.error_counts).map(([code,count])=>`${errors[code]||code}: ${count}`).join('; ')}{c.messages.filter(m=>m.includes('nhiều tiền tệ')).map(m=><span key={m}> {m}</span>)}</p>)}</details>
        {!!assessment.related_keys?.length&&<details><summary>Quan hệ tiềm năng giữa các nguồn</summary>{assessment.related_keys.map((r,i)=><p key={`${r.table_id}:${i}`}>{r.source_name}: {r.fields.join(' + ')}; {r.shared_keys} khóa xuất hiện ở cả hai nguồn, {r.left_duplicate_rows}/{r.right_duplicate_rows} dòng trùng khóa, {r.missing_key_rows} dòng thiếu khóa. Cần xác nhận ý nghĩa mỗi dòng và quan hệ một/nhiều trước khi đối soát; không tự duyệt từ thống kê.</p>)}</details>}
        {assessment.preflight_ready && <Notice>Đã kiểm tra trước chuẩn hóa trên {assessment.source_rows} dòng; dự kiến {assessment.predicted_invalid_rows} dòng không hợp lệ. Dữ liệu gốc và bản cũ được giữ nguyên.</Notice>}
      </>}
      {draft.fields.some(f=>f.data_type==='date'&&!f.timezone)&&<label>Múi giờ của nguồn<select aria-label="Múi giờ của nguồn" disabled={disabled} defaultValue="" onChange={e=>{if(e.target.value)setDraft({...draft,fields:draft.fields.map(f=>f.data_type==='date'&&!f.timezone?{...f,timezone:e.target.value}:f)});}}><option value="">Chọn theo quy ước dữ liệu</option><option value="UTC">UTC</option><option value="Asia/Ho_Chi_Minh">Việt Nam (Asia/Ho_Chi_Minh)</option></select></label>}
      {draft.fields.some(f=>f.data_type==='decimal'&&!f.currency)&&<label>Tiền tệ cho số tiền trong nguồn<select aria-label="Tiền tệ cho số tiền trong nguồn" disabled={disabled} defaultValue="" onChange={e=>{if(e.target.value)setDraft({...draft,fields:draft.fields.map(f=>f.data_type==='decimal'&&!f.currency?{...f,currency:e.target.value,unit:f.unit||e.target.value}:f)});}}><option value="">Chọn phạm vi tiền tệ; giá trị khác giữ lỗi riêng</option>{(assessment?.currencies||[]).map(c=><option key={c} value={c}>{c}</option>)}</select></label>}
      {draft.fields.filter(f=>f.data_type==='decimal'&&(!f.amount_basis||!f.currency||!f.semantic_metric||!f.unit||!f.locale)).map(f=><fieldset key={f.source_field}><legend>{f.name} — quyết định về số tiền</legend>
        {!f.amount_basis&&<label>Cơ sở tiền của {f.name}<select disabled={disabled} value="" onChange={e=>setDraft({...draft,fields:draft.fields.map(x=>x.source_field===f.source_field?{...x,amount_basis:e.target.value||null}:x)})}><option value="">Chưa xác định</option><option value="gross">Trước khấu trừ / gross</option><option value="net">Sau khấu trừ / net</option><option value="expected">Dự kiến phải thu / expected</option><option value="paid">Đã thanh toán / paid</option><option value="fee">Phí / fee</option></select></label>}
        {!f.currency&&<label>Tiền tệ cho {f.name}<input disabled={disabled} placeholder="VND / USD; kiểm tra cảnh báo tiền tệ" maxLength={3} onBlur={e=>{const value=e.target.value.toUpperCase();if(value)setDraft({...draft,fields:draft.fields.map(x=>x.source_field===f.source_field?{...x,currency:value,unit:x.unit||value}:x)});}}/></label>}
        {(!f.semantic_metric||!f.unit||!f.locale)&&<p>Mở phần chỉnh sửa để xác nhận ý nghĩa, đơn vị hoặc định dạng còn thiếu.</p>}
      </fieldset>)}
      <p>Loại dữ liệu: {draft.entity_kind}. Mỗi dòng: {draft.grain}. Khóa đề xuất: {draft.fields.filter(f=>f.business_key).map(f=>f.name).join(', ')||'chưa chọn; cần kiểm tra grain và quan hệ nguồn'}.</p>
      <details className="agent-review-editor"><summary>Xem và chỉnh các lựa chọn</summary><p>Chỉnh sửa chi tiết chỉ khi đề xuất chưa đúng. Các thay đổi được kiểm tra lại trước khi duyệt.</p><MappingReview draft={draft} disabled={disabled} onChange={v=>setDraft(v)}/></details>
    </>}
    {plan && <><p>Nguồn A: {sourceName(plan.left.canonical_id)} · Nguồn B: {sourceName(plan.right.canonical_id)}</p><p>Kỳ {plan.period_start||"chưa chọn"} → {plan.period_end||"chưa chọn"} · {plan.timezone||"chưa rõ múi giờ"}</p><p>Khóa: {plan.join_keys.map(k=>`${fieldName(plan.left.canonical_id,k.left)} ↔ ${fieldName(plan.right.canonical_id,k.right)}`).join(", ")}. {label(plan.cardinality)} · {label(plan.aggregation)}</p>{plan.comparison_metrics.map(m=><p key={m.metric_id}>{fieldName(plan.left.canonical_id,m.left)} · {m.amount_basis} · {m.currency} · sai số {m.absolute_tolerance}</p>)}<details className="agent-review-editor"><summary>Kiểm tra phạm vi và chỉnh quy tắc</summary><PlanReview plan={plan} disabled={disabled} onChange={v => { setPlan(v); }}/></details></>}
    {review.kind === "RECONCILIATION" && !plan && <Notice>Cần bổ sung kỳ, múi giờ và độ đầy đủ. Chưa có quy tắc đủ điều kiện chạy.</Notice>}
    {expired && <Notice>Thẻ đã hết thời hạn. Nếu nguồn còn nguyên, bạn có thể mở lại để tiếp tục.<button type="button" className="text-button" disabled={busy || !canEdit || !!review.pending_reply_job_id} onClick={()=>void saveOrRenew(true)}>Mở lại thẻ xác nhận</button></Notice>}
    <button className="text-button" disabled={replyDisabled} onClick={()=>void requestReply()}>Bổ sung bằng tiếng Việt</button>
    {replyOpen && <form onSubmit={e=>{e.preventDefault();void sendInlineReply();}}><label>Câu trả lời cho thẻ này<textarea value={replyText} disabled={replyDisabled || !!replyPending.current} maxLength={2000} onChange={e=>{setReplyText(e.target.value);try{sessionStorage.setItem(replyKey,e.target.value);}catch{/* optional local recovery */}}}/></label><button type="submit" className="button secondary" disabled={replyDisabled || !replyText.trim()}>Gửi câu trả lời để xem trước</button></form>}
    <button type="button" className="text-button" disabled={disabled} onClick={()=>void saveOrRenew()}>Lưu bản nháp</button>
    {review.pending_reply_job_id && <Spinner />}<p className="muted">Câu trả lời được diễn giải để bạn kiểm tra; hệ thống chưa phê duyệt thay bạn.</p>
    {draft && review.extraction_review_required!==false && <label><input type="checkbox" checked={extraction} disabled={disabled} onChange={e => setExtraction(e.target.checked)}/>Tôi đã kiểm tra cảnh báo/vùng bảng nguồn nếu có.</label>}
    {!ready && <p className="muted">Mở phần chỉnh sửa hoặc bổ sung bằng tiếng Việt để hoàn tất các điều kiện còn thiếu.</p>}
    <p className="muted">{review.kind === "MAPPING" ? "Khi duyệt, hệ thống sẽ lưu cách ghép cột và chuẩn hóa theo các lựa chọn này." : "Khi duyệt, hệ thống sẽ lưu quy tắc và bắt đầu đối soát trong phạm vi trên."}</p>
    <button className="button primary" disabled={disabled || !ready} onClick={() => void action()}>{review.kind === "MAPPING" ? "Duyệt cách ghép cột và chuẩn hóa" : "Duyệt quy tắc và đối soát"}</button>
  </section>;
}
