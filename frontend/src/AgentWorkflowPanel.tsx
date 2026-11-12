import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Notice } from "./components";
import { AgentResultBlocks } from "./AgentResultBlocks";
import { ReviewCard } from "./ReviewCard";
import type { Review, Workflow, SharedMappingFacts } from "./agentTypes";
import type { AssistantContext, Suggestion } from "./assistantTypes";
import { label } from "./reconciliationTypes";
import { errorText as errors, statusText } from "./types";
const states: Record<string, string> = { CREATED: "Đã nhận yêu cầu", RUNNING: "Đang thực hiện",
    WAITING_REVIEW: "Cần bạn xác nhận", COMPLETED: "Đã hoàn thành", PARTIAL: "Hoàn thành một phần",
    FAILED: "Xử lý thất bại", BLOCKED: "Chưa thể tiếp tục", CANCELLED_BEFORE_NEXT_STEP: "Đã dừng các bước tiếp theo" };
const tools: Record<string, string> = { parse: "Đọc dữ liệu", propose_mapping: "Chuẩn bị đề xuất",
    reuse_mapping: "Kiểm tra mẫu đã duyệt",
    run_normalization: "Chuẩn hóa", prepare_reconciliation_plan: "Đề xuất quy tắc đối soát",
    run_approved_reconciliation: "Đối soát và kiểm chứng", start_export: "Tạo báo cáo",
    query_dataset: "Tra cứu dữ liệu", read_verified_facts: "Đọc kết quả đã xác minh" };

function CommonMappingFacts({reviews, storageKey, disabled, onApply}: {
    reviews:Review[];storageKey:string;disabled:boolean;onApply:(facts:Omit<SharedMappingFacts,"revision">)=>void;
}) {
    const empty={entity_kind:"",grain:"",timezone:"",amount_basis:"",semantic_metric:"",business_key:""};
    const [fields,setFields]=useState(()=>{
        try {const saved=JSON.parse(sessionStorage.getItem(storageKey)||"null");
            if(saved && Object.keys(empty).every(key=>typeof saved[key]==="string" ||
                (key==="business_key" && saved[key]===undefined))) return {...empty,...saved} as typeof empty;
        }catch{/* A malformed local draft cannot supply business facts. */}
        return empty;
    });
    useEffect(()=>{try{sessionStorage.setItem(storageKey,JSON.stringify(fields));}catch{/* Private storage may be unavailable. */}},[fields,storageKey]);
    const keyNames=reviews.map(review=>(review.normalization_draft?.fields??[])
        .filter(field=>field.data_type==="string").map(field=>field.name));
    const commonKeys=[...new Set(keyNames[0])].filter(name=>keyNames.every(names=>
        names.filter(candidate=>candidate===name).length===1));
    const {business_key,...required}=fields;
    const selectedKey=commonKeys.includes(business_key)?business_key:"";
    const ready=Object.values(required).every(value=>value.trim()&&value.trim().toLowerCase()!=="unknown");
    function edit(key:keyof typeof fields,value:string){setFields(previous=>({...previous,[key]:value}));}
    return <details className="agent-shared-facts" open><summary>Nhập một lần cho các nguồn có cùng nghiệp vụ</summary>
        <section aria-label="Thông tin chung cho các nguồn">
            <p>Chỉ dùng khi mỗi dòng, ý nghĩa khoản tiền và múi giờ giống nhau. Lựa chọn đã có trong từng thẻ được giữ nguyên.</p>
            <ul>{reviews.map(review=><li key={review.id}>{review.resource_label}: {review.normalization_draft?.fields.filter(field=>field.data_type==="decimal").map(field=>field.name).join(", ")}</li>)}</ul>
            <div className="agent-form-grid">
            <label>Loại dữ liệu dùng chung<input value={fields.entity_kind} maxLength={100} disabled={disabled} onChange={event=>edit("entity_kind",event.target.value)}/></label>
            <label>Mỗi dòng của các nguồn là gì?<input value={fields.grain} maxLength={200} disabled={disabled} onChange={event=>edit("grain",event.target.value)}/></label>
            <label>Múi giờ dùng chung<select aria-label="Múi giờ dùng chung" value={fields.timezone} disabled={disabled} onChange={event=>edit("timezone",event.target.value)}><option value="">Chọn theo quy ước nguồn</option><option value="UTC">UTC</option><option value="Asia/Ho_Chi_Minh">Việt Nam</option></select></label>
            <label>Cơ sở tiền dùng chung<select aria-label="Cơ sở tiền dùng chung" value={fields.amount_basis} disabled={disabled} onChange={event=>edit("amount_basis",event.target.value)}><option value="">Chưa xác định</option><option value="gross">Trước khấu trừ / gross</option><option value="net">Sau khấu trừ / net</option><option value="paid">Đã thanh toán / paid</option><option value="expected">Dự kiến / expected</option><option value="fee">Phí / fee</option></select></label>
            <label>Khoản tiền dùng chung là gì?<input value={fields.semantic_metric} maxLength={100} disabled={disabled} onChange={event=>edit("semantic_metric",event.target.value)}/></label>
            {commonKeys.length>0&&<label>Cột khóa chung (tùy chọn)<select aria-label="Cột khóa chung (tùy chọn)" value={selectedKey} disabled={disabled} onChange={event=>edit("business_key",event.target.value)}>
                <option value="">Chọn khóa riêng trong từng nguồn</option>{commonKeys.map(name=><option key={name}>{name}</option>)}
            </select></label>}
            </div>
            <p>Dùng nút bên dưới khi bạn đã xác nhận thông tin đúng cho các nguồn liệt kê. Sau đó, xem từng nguồn trước khi duyệt chuẩn hóa.</p>
            <button type="button" className="button secondary" disabled={disabled||!ready} onClick={()=>onApply({...fields,business_key:selectedKey,reviewKeys:reviews.map(review=>`${review.id}:${review.nonce}:${review.fingerprint}`)})}>Xác nhận và điền vào bản nháp</button>
        </section>
    </details>;
}
export function AgentWorkflowPanel({ id, canEdit, draftOwner, onNavigate, onContext, onReply }: {
    id: string;
    canEdit: boolean;
    draftOwner: string;
    onNavigate: (target: Suggestion, context: AssistantContext) => void;
    onContext: (context: AssistantContext) => void;
    onReply: (workflowId:string,review:Review)=>void;
}) {
    const [workflow, setWorkflow] = useState<Workflow | null>(null);
    const [error, setError] = useState("");
    const [batchDrafts, setBatchDrafts] = useState<Record<string, string>>({});
    const [batchBusy, setBatchBusy] = useState(false);
    const [resumeVersion, setResumeVersion] = useState(0);
    const qualityPublished = useRef("");
    const resumeLock = useRef(false);
    const [sharedFacts,setSharedFacts]=useState<SharedMappingFacts|null>(null);
    const batchLock = useRef(false);
    const batchDraft = useCallback((id: string, payload: string | null) => {
        setBatchDrafts(previous => {
            if ((previous[id] || null) === payload) return previous;
            const next = {...previous};
            if (payload) next[id] = payload;
            else delete next[id];
            return next;
        });
    }, []);
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
        const poll = async () => {
            await refresh();
            const changed = current.current?.detail.blocks.some(
                block => block.type === "dataset_summary" && block.canonical_id === qualityPublished.current,
            );
            if (changed || attempts >= 8) qualityPublished.current = "";
            if (alive.current && (qualityPublished.current || !['COMPLETED', 'BLOCKED', 'FAILED', 'PARTIAL', 'CANCELLED_BEFORE_NEXT_STEP'].includes(current.current?.state || '')))
                timer = setTimeout(() => void poll(), Math.min(4000, 800 + attempts++ * 150));
        };
        void poll();
        return () => { alive.current = false; sequence.current++; controller.current.abort(); clearTimeout(timer); };
    }, [id, resumeVersion]);
    async function resumeProvider() {
        if (resumeLock.current) return;
        resumeLock.current = true;
        try {
            await api(`/agent/workflows/${id}/resume-provider`, { method: "POST" });
            if (alive.current) setResumeVersion(value => value + 1);
        } catch (err) {
            if (alive.current) setError(err instanceof Error ? err.message : "Chưa thể tiếp tục.");
        } finally {
            resumeLock.current = false;
        }
    }
    async function cancel() { try {
        await api(`/agent/workflows/${id}/cancel`, { method: "POST" });
        await refresh();
    }
    catch (err) {
        if (alive.current)
            setError(String(err));
    } }
    const openReviews = workflow?.detail.reviews.filter(review => review.state === "OPEN") ?? [];
    const openMappings = openReviews.filter(review => review.kind === "MAPPING");
    const resultBlocks = workflow?.detail.blocks.filter((block, index, blocks) =>
        block.type !== "progress" || (
            !openReviews.some(review=>review.question === block.text || review.reply_questions.includes(block.text)) &&
            !blocks.slice(0, index).some(previous=>previous.type === "progress" && previous.text === block.text)
        ),
    ) ?? [];
    const compactPreviews = openReviews.length > 0 || resultBlocks.some(block=>block.type === "dataset_summary" || block.type === "facts");
    const canBatch = canEdit && openMappings.length >= 2 && openMappings.every(review => !!batchDrafts[review.id]);
    async function approveBatch() {
        if (!canBatch || batchLock.current) return;
        batchLock.current = true; setBatchBusy(true);
        try {
            await api(`/agent/workflows/${id}/decisions/batch`, {method: "POST", body: JSON.stringify({
                decisions: openMappings.map(review => JSON.parse(batchDrafts[review.id])),
            })});
            await refresh();
        } catch (err) {
            if (alive.current) setError(err instanceof Error ? err.message : "Không lưu được các quyết định.");
        } finally {
            batchLock.current = false;
            if (alive.current) setBatchBusy(false);
        }
    }
    return <section className="agent-workflow" aria-label="Công việc của AI Assistant" aria-busy={!workflow && !error}>{error && <Notice tone="error"><p>{error}</p><button className="text-button" onClick={() => void refresh()}>Cập nhật</button></Notice>}
    {workflow && <><div className="agent-workflow-state" data-state={workflow.state}>
      <strong role="status">{workflow.state === "WAITING_REVIEW" && openReviews.some(review=>review.kind === "CLARIFICATION")
        ? "Cần bạn bổ sung" : workflow.state === "COMPLETED" && workflow.detail.intent?.intent === "EXPLORE_DATA"
        ? "Đã đọc dữ liệu, chưa chuẩn hóa" : states[workflow.state] || "Chưa có trạng thái xử lý"}</strong>
      {["CREATED", "RUNNING", "WAITING_REVIEW"].includes(workflow.state) && <button className="text-button" onClick={() => void cancel()}>Dừng bước tiếp theo</button>}
    </div>
      {workflow.detail.error_code && <Notice tone="warning">
        <p>{errors[workflow.detail.error_code]||"Chưa đủ điều kiện để tiếp tục. Dữ liệu và kết quả đã lưu được giữ."}</p>
        {canEdit && workflow.detail.resumable_job_id &&
          <button type="button" className="text-button" onClick={() => void resumeProvider()}>Tiếp tục công việc</button>}
        {workflow.detail.intent?.intent === "PREPARE_NORMALIZATION" && (
          <button type="button" className="text-button" onClick={() => onNavigate("OPEN_DATA", workflow.context)}>
            Mở dữ liệu để ghép cột thủ công
          </button>
        )}
      </Notice>}
      {workflow.detail.prepare_upload && openMappings.length>=2 && openMappings.every(review=>review.normalization_draft?.fields.filter(field=>field.data_type==="decimal").length===1) && <CommonMappingFacts
        key={openMappings.map(review=>`${review.id}:${review.nonce}`).join("|")}
        reviews={openMappings} storageKey={`studio.common-mapping.${draftOwner}.${id}.${openMappings.map(review=>`${review.id}:${review.nonce}:${review.fingerprint}`).join("|")}`}
        disabled={!canEdit||batchBusy||!["WAITING_REVIEW","RUNNING"].includes(workflow.state)} onApply={facts=>{setBatchDrafts({});setSharedFacts(previous=>({...facts,revision:(previous?.revision||0)+1}));}}/>}
      {openReviews.map(r => <ReviewCard key={`${r.id}:${r.nonce}`} review={r} workflow={workflow} draftOwner={draftOwner} canEdit={canEdit && !batchBusy && ["WAITING_REVIEW", "RUNNING"].includes(workflow.state)} refresh={refresh} onReply={onReply} onBatchDraft={workflow.detail.prepare_upload ? batchDraft : undefined} sharedFacts={sharedFacts}/>)}
      {(canBatch || batchBusy) && <section aria-label="Duyệt các nguồn đang hiển thị">
        <p>Áp dụng các lựa chọn trong thẻ của {openMappings.map(review => review.resource_label || "nguồn đã chọn").join(", ")}.</p>
        <button type="button" className="button primary" disabled={batchBusy} onClick={()=>void approveBatch()}>Duyệt {openMappings.length} nguồn và chuẩn hóa</button>
      </section>}
      {resultBlocks.length > 0 && <AgentResultBlocks blocks={resultBlocks} compactPreviews={compactPreviews} context={workflow.context} onNavigate={onNavigate} workflowId={workflow.id} querySelection={workflow.detail.query_selection?.query} onQualityPublished={id => {
        qualityPublished.current = id;
        setResumeVersion(value => value + 1);
      }}/>}
      {workflow.detail.steps.length>0&&<details className="agent-processing"><summary>Chi tiết xử lý</summary><ol className="agent-steps">{workflow.detail.steps.map((s, i) => <li key={i}>{tools[s.tool] || s.tool} · {statusText[s.status]||label(s.status)}</li>)}</ol></details>}
    </>}</section>;
}
