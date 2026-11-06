import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Notice, Spinner } from "./components";
import { AgentResultBlocks } from "./AgentResultBlocks";
import { ReviewCard } from "./ReviewCard";
import type { Review, Workflow } from "./agentTypes";
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
      {workflow.detail.reviews.filter(r => r.state === "OPEN").map(r => <ReviewCard key={`${r.id}:${r.nonce}`} review={r} workflow={workflow} draftOwner={draftOwner} canEdit={canEdit && ["WAITING_REVIEW", "RUNNING"].includes(workflow.state)} refresh={refresh} onReply={onReply}/>)}
      <AgentResultBlocks blocks={workflow.detail.blocks.filter((block,index,blocks)=>block.type!=="progress"||(!workflow.detail.reviews.some(r=>r.state==="OPEN"&&(r.question===block.text||r.reply_questions.includes(block.text)))&&!blocks.slice(0,index).some(previous=>previous.type==="progress"&&previous.text===block.text)))} context={workflow.context} onNavigate={onNavigate} workflowId={workflow.id} querySelection={workflow.detail.query_selection?.query}/>
    </>}</section>;
}
