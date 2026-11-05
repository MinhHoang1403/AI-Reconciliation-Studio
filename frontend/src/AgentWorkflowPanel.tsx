import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Notice, Spinner } from "./components";
import { AgentResultBlocks } from "./AgentResultBlocks";
import type { DraftField, NormalizationDraft, Review, Workflow, MappingAssessment } from "./agentTypes";
import type { AssistantContext, Suggestion } from "./assistantTypes";
import { label, type Plan, type Catalogue, type Slot } from "./reconciliationTypes";
import {errorText as errors,statusText} from "./types";
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
function ReviewCard({ review, workflow, canEdit, refresh, onReply }: {
    review: Review;
    workflow: Workflow;
    canEdit: boolean;
    refresh: () => Promise<void>;
    onReply: (workflowId:string,review:Review)=>void;
}) {
    const [draft, setDraft] = useState(review.normalization_draft);
    const [plan, setPlan] = useState(review.plan);
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
        if (review.kind !== "RECONCILIATION")
            return;
        const controller = new AbortController();
        void api<{
            items: Catalogue[];
        }>(`/projects/${workflow.context.project_id}/canonical-catalogue`, { signal: controller.signal })
            .then(data => { if (!controller.signal.aborted){
            setCatalogue(data.items);if(!review.plan)setPlan(proposedPlan(review, data.items));} })
            .catch(err => { if (!controller.signal.aborted)
            setError(String(err)); });
        return () => controller.abort();
    }, [review.id, review.nonce]);
    const disabled = busy || !canEdit || !!review.pending_reply_job_id;
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
      <button className="text-button" disabled={disabled} onClick={()=>onReply(workflow.id,review)}>Trả lời bằng tiếng Việt</button>
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
    <button className="text-button" disabled={disabled} onClick={()=>onReply(workflow.id,review)}>Bổ sung bằng tiếng Việt</button>
    {review.pending_reply_job_id && <Spinner />}<p className="muted">Câu trả lời được diễn giải để bạn kiểm tra; hệ thống chưa phê duyệt thay bạn.</p>
    {draft && review.extraction_review_required!==false && <label><input type="checkbox" checked={extraction} disabled={disabled} onChange={e => setExtraction(e.target.checked)}/>Tôi đã kiểm tra cảnh báo/vùng bảng nguồn nếu có.</label>}
    {!ready && <p className="muted">Mở phần chỉnh sửa hoặc bổ sung bằng tiếng Việt để hoàn tất các điều kiện còn thiếu.</p>}
    <p className="muted">{review.kind === "MAPPING" ? "Khi duyệt, hệ thống sẽ lưu cách ghép cột và chuẩn hóa theo các lựa chọn này." : "Khi duyệt, hệ thống sẽ lưu quy tắc và bắt đầu đối soát trong phạm vi trên."}</p>
    <button className="button primary" disabled={disabled || !ready} onClick={() => void action()}>{review.kind === "MAPPING" ? "Duyệt cách ghép cột và chuẩn hóa" : "Duyệt quy tắc và đối soát"}</button>
  </section>;
}
export function AgentWorkflowPanel({ id, canEdit, onNavigate, onContext, onReply }: {
    id: string;
    canEdit: boolean;
    onNavigate: (target: Suggestion, context: AssistantContext) => void;
    onContext: (context: AssistantContext) => void;
    onReply: (workflowId:string,review:Review)=>void;
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
    return <section className="agent-workflow" aria-label="Công việc của AI Assistant">{error && <Notice tone="error">{error}<button className="text-button" onClick={() => void refresh()}>Cập nhật</button></Notice>}
    {!workflow ? <Spinner /> : <><p className="agent-workflow-state" role="status">{["CREATED","RUNNING"].includes(workflow.state)&&<Spinner/>}<strong>{workflow.state==="WAITING_REVIEW"&&workflow.detail.reviews.some(r=>r.state==="OPEN"&&r.kind==="CLARIFICATION")?"Cần bạn bổ sung":workflow.state === "COMPLETED" && workflow.detail.intent?.intent === "EXPLORE_DATA" ? "Đã đọc dữ liệu; chưa chuẩn hóa" : states[workflow.state] || "Chưa có trạng thái xử lý"}</strong>{["CREATED", "RUNNING", "WAITING_REVIEW"].includes(workflow.state) && <button className="text-button" onClick={() => void cancel()}>Dừng bước tiếp theo</button>}</p>
      {workflow.detail.error_code && <Notice tone="warning">
        {errors[workflow.detail.error_code]||"Chưa đủ điều kiện để tiếp tục. Dữ liệu và kết quả đã lưu được giữ."}
        {workflow.detail.intent?.intent === "PREPARE_NORMALIZATION" && (
          <button type="button" className="text-button" onClick={() => onNavigate("OPEN_DATA", workflow.context)}>
            Mở dữ liệu để ghép cột thủ công
          </button>
        )}
        <details><summary>Chi tiết</summary><code>{workflow.detail.error_code}</code></details>
      </Notice>}
      {workflow.detail.steps.length>0&&<details className="agent-processing"><summary>Chi tiết xử lý</summary><ol className="agent-steps">{workflow.detail.steps.map((s, i) => <li key={i}>{tools[s.tool] || s.tool} · {statusText[s.status]||label(s.status)}</li>)}</ol></details>}
      {workflow.detail.reviews.filter(r => r.state === "OPEN").map(r => <ReviewCard key={`${r.id}:${r.nonce}`} review={r} workflow={workflow} canEdit={canEdit && workflow.state === "WAITING_REVIEW"} refresh={refresh} onReply={onReply}/>)}
      <AgentResultBlocks blocks={workflow.detail.blocks.filter((block,index,blocks)=>block.type!=="progress"||(!workflow.detail.reviews.some(r=>r.state==="OPEN"&&(r.question===block.text||r.reply_questions.includes(block.text)))&&!blocks.slice(0,index).some(previous=>previous.type==="progress"&&previous.text===block.text)))} context={workflow.context} onNavigate={onNavigate} workflowId={workflow.id} querySelection={workflow.detail.query_selection?.query}/>
    </>}</section>;
}
