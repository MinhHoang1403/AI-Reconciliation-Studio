import { useEffect, useRef, useState } from "react";
import { MessageSquarePlus, Send, Trash2, MessagesSquare, Paperclip, MoreHorizontal, Sparkles, X } from "lucide-react";
import { AgentWorkflowPanel } from "./AgentWorkflowPanel";
import type { Review } from "./agentTypes";
import { api, ApiError } from "./api";
import { Modal, Notice, Spinner } from "./components";
import { ReconciliationEvidence } from "./ReconciliationEvidence";
import { AssistantWorkflow } from "./AssistantWorkflow";
import {
  reconciliationLabels,
  type Run,
  type SourceEvidence,
} from "./reconciliationTypes";
import type { Job } from "./types";
import type {
  AssistantAnswer,
  AssistantContext,
  AssistantMessage,
  AssistantRule,
  Conversation,
  ConversationPage,
  FactReference,
  Suggestion,
} from "./assistantTypes";

const labels: Record<string, string> = {
  VERIFIED_FACT: "Dữ kiện đã xác minh",
  SUPPORTED_INTERPRETATION: "Diễn giải có bằng chứng",
  HYPOTHESIS: "Giả thuyết cần kiểm tra",
  UNKNOWN: "Chưa xác định",
  INSUFFICIENT_EVIDENCE: "Thiếu bằng chứng",
  ANSWERED: "Có bằng chứng",
  PROVIDER_UNAVAILABLE: "Suy luận cloud chưa khả dụng",
  REVIEW_REQUIRED: "Cần bạn xác nhận",
  DETERMINISTIC: "Backend xác định",
  CACHE: "Tái sử dụng facts",
  GEMINI: "Gemini",
  MOCK: "Kiểm thử mô phỏng",
  OPEN_EXCEPTIONS: "Mở ngoại lệ",
  OPEN_EVIDENCE: "Xem bằng chứng",
  OPEN_RULE: "Xem rule đã duyệt",
  OPEN_DATA: "Kiểm tra dữ liệu",
  OPEN_REPORT: "Mở báo cáo",
  OPEN_RECONCILIATION: "Xem và duyệt kế hoạch",
};
const errorText = (error: unknown) =>
  error instanceof Error ? error.message : "Không tải được hội thoại.";

/** Mỗi mount thuộc một project/context; abort và sequence chặn response cũ sau chuyển scope. */
export function AssistantStudio({
  initialContext,
  onNavigate,
  cloudEnabled = false,
  canEdit,
  onReview,
  projectName,
  draftOwner,
  onContextChange,
  onUploadProject,
  agentEnabled = false,
}: {
  initialContext: AssistantContext;
  onNavigate: (target: Suggestion, context: AssistantContext) => void;
  cloudEnabled?: boolean;
  canEdit: boolean;
  onReview: (planId: string) => void;
  projectName: string;
  draftOwner: string;
  onContextChange: (context: AssistantContext) => void;
  onUploadProject: (id: string) => Promise<void>;
  agentEnabled?: boolean;
}) {
  const [context, setContext] = useState(initialContext);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [history, setHistory] = useState<Conversation[]>([]);
  const [moreHistory, setMoreHistory] = useState(false);
  const [moreMessages, setMoreMessages] = useState(false);
  const [runs, setRuns] = useState<Run[]>([]);
  const [runTotal, setRunTotal] = useState(0);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [command, setCommand] = useState<string | null>(null);
  const [mode, setMode] = useState<"AGENT" | "LEGACY">("AGENT");
  type ReplyBinding=Pick<Review,"id"|"nonce"|"fingerprint"|"question">&{workflowId:string};
  const [reviewReply,setReviewReply]=useState<ReplyBinding|null>(null);
  const replyKeyFor=(scope:AssistantContext,id:string)=>`studio.review-reply.${draftOwner}.${scope.project_id}.${id}`;
  const uploadKey = useRef(crypto.randomUUID());
  const fileInput = useRef<HTMLInputElement>(null);
  const workflowContext = useRef<AssistantContext | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pendingJob, setPendingJob] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmWorkflow, setConfirmWorkflow] =
    useState<AssistantAnswer | null>(null);
  const [evidence, setEvidence] = useState<SourceEvidence | null>(null);
  const [rule, setRule] = useState<(AssistantRule & { run_id: string }) | null>(
    null,
  );
  const [historyOpen, setHistoryOpen] = useState(false);
  const [contextOpen,setContextOpen]=useState(false);
  const [historySearch,setHistorySearch]=useState("");
  const historyTrigger=useRef<HTMLElement|null>(null);
  const composerInput=useRef<HTMLTextAreaElement>(null);
  useEffect(()=>{const input=composerInput.current;if(input){input.style.height="auto";input.style.height=`${Math.min(input.scrollHeight,180)}px`;}},[text]);
  const [draftNotice, setDraftNotice] = useState("");
  const draftKeyFor = (scope: AssistantContext, id = "new") =>
    `studio.assistant-draft.${draftOwner}.${JSON.stringify([scope.project_id, scope.run_id || "", scope.dataset_id || "", scope.group_id || "", scope.case_id || "", id])}`;
  const draftKey = useRef(draftKeyFor(initialContext));
  function restoreDraft(scope: AssistantContext, id?: string) {
    draftKey.current = draftKeyFor(scope, id);
    setText(sessionStorage.getItem(draftKey.current) || "");
    setReviewReply(null);
    if(id){try{const saved=JSON.parse(sessionStorage.getItem(replyKeyFor(scope,id))||"null");
      if(saved&&typeof saved.id==="string"&&typeof saved.nonce==="string"&&typeof saved.fingerprint==="string"&&typeof saved.workflowId==="string")setReviewReply(saved);
    }catch{/* Server xác minh lại mọi binding trước khi ghi. */}}
    try {
      const saved=JSON.parse(sessionStorage.getItem(`studio.assistant-request.${draftOwner}.${scope.project_id}`)||"null");
      const body=saved?.body?JSON.parse(saved.body):null;
      if(body?.conversation_id===id&&(body?.mode==="AGENT"||body?.mode==="LEGACY")){setMode(body.mode);setCommand(body.command||null);}
    }catch{/* Chỉ khôi phục bản nháp hợp lệ, server vẫn kiểm lại mọi request. */}
  }
  const alive = useRef(true);
  const controller = useRef(new AbortController());
  const sequence = useRef(0);
  const evidenceSequence = useRef(0);
  const historySequence = useRef(0);
  const citationTrigger = useRef<HTMLElement | null>(null);
  const pendingRequest = useRef<{ body: string; key: string } | null>(null);
  const createKey = useRef<string>(crypto.randomUUID());
  const storageKey = `studio.conversation.${initialContext.project_id}`;
  const requestStorageKey = `studio.assistant-request.${draftOwner}.${initialContext.project_id}`;
  const getOptions = () => ({ signal: controller.current.signal });
  useEffect(() => {
    onContextChange(context);
  }, [context]);

  async function loadHistory(append = false) {
    if (!initialContext.project_id) return;
    const request = ++historySequence.current;
    const before =
      append && history.length ? `&before_id=${history.at(-1)!.id}` : "";
    const page = await api<{ items: Conversation[]; has_more: boolean }>(
      `/conversations?project_id=${initialContext.project_id}&limit=20${before}`,
      getOptions(),
    );
    if (!alive.current || request !== historySequence.current) return;
    setHistory((old) => (append ? [...old, ...page.items] : page.items));
    setMoreHistory(page.has_more);
  }
  async function loadRuns(append = false) {
    if (!initialContext.project_id) return;
    const page = await api<{ items: Run[]; total: number }>(
      `/runs?project_id=${initialContext.project_id}&offset=${append ? runs.length : 0}&limit=50`,
      getOptions(),
    );
    if (!alive.current) return;
    setRuns((old) => (append ? [...old, ...page.items] : page.items));
    setRunTotal(page.total);
  }
  async function refreshMessages(
    id: string,
    request = sequence.current,
    cached?: ConversationPage,
  ) {
    const page =
      cached ||
      (await api<ConversationPage>(
        `/conversations/${id}?limit=20`,
        getOptions(),
      ));
    if (!alive.current || request !== sequence.current) return null;
    if (page.conversation.context.project_id !== initialContext.project_id)
      throw new Error("Hội thoại không thuộc dự án đang chọn.");
    setConversation(page.conversation);
    setContext(page.conversation.context);
    setMessages(page.items);
    setMoreMessages(page.has_more);
    localStorage.setItem(storageKey, id);
    return page;
  }
  async function waitForAnswer(jobId: string, id: string, request: number) {
    setPendingJob(jobId);
    for (let attempt = 0; attempt < 60; attempt++) {
      const job = await api<Job>(`/jobs/${jobId}`, getOptions());
      if (!alive.current || request !== sequence.current) return;
      if (
        ["SUCCEEDED", "BLOCKED", "FAILED", "CANCELLED"].includes(job.status)
      ) {
        setPendingJob("");
        await refreshMessages(id, request);
        if (job.status !== "SUCCEEDED")
          setError(
            `Câu hỏi chưa có kết quả: ${job.error_code || job.status}. Lịch sử được giữ; không tự gửi lại provider.`,
          );
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    if (alive.current && request === sequence.current)
      setError(
        "Câu hỏi còn xử lý. Bấm Cập nhật hội thoại để tiếp tục xem, không cần gửi lại.",
      );
  }
  async function openConversation(id: string, cached?: ConversationPage) {
    const request = ++sequence.current;
    evidenceSequence.current++;
    setEvidence(null);
    setRule(null);
    setMessages([]);
    setConversation(null);
    setPendingJob("");
    setError("");
    setLoading(true);
    setHistoryOpen(false);
    try {
      const page = await refreshMessages(id, request, cached);
      if (!page) return;
      restoreDraft(page.conversation.context, id);
      const last = page.items.at(-1);
      if (last?.role === "user") await waitForAnswer(last.job_id, id, request);
    } catch (err) {
      if (alive.current && request === sequence.current) {
        if (
          err instanceof ApiError &&
          ["RESOURCE_NOT_FOUND", "FORBIDDEN"].includes(err.code) &&
          localStorage.getItem(storageKey) === id
        )
          localStorage.removeItem(storageKey);
        restoreDraft(initialContext);
        setError(errorText(err));
      }
    } finally {
      if (alive.current && request === sequence.current) setLoading(false);
    }
  }
  useEffect(() => {
    alive.current = true;
    controller.current = new AbortController();
    restoreDraft(initialContext);
    void (async () => {
      try {
        await Promise.all([loadHistory(), loadRuns()]);
        if (!alive.current || sequence.current !== 0) return;
        const saved = localStorage.getItem(storageKey);
        if (saved) {
          // A contextual link may resume only the exact same scope, never another run/case.
          const savedPage = await api<ConversationPage>(
            `/conversations/${saved}?limit=20`,
            getOptions(),
          );
          if (!alive.current || sequence.current !== 0) return;
          const scoped = [
            "run_id",
            "dataset_id",
            "group_id",
            "case_id",
          ] as const;
          if (
            (!initialContext.run_id && !initialContext.dataset_id) ||
            scoped.every(
              (key) =>
                (initialContext[key] || null) ===
                (savedPage.conversation.context[key] || null),
            )
          )
            await openConversation(saved, savedPage);
        }
      } catch (err) {
        if (alive.current) {
          setError(errorText(err));
          if (
            err instanceof ApiError &&
            ["RESOURCE_NOT_FOUND", "FORBIDDEN"].includes(err.code)
          )
            localStorage.removeItem(storageKey);
        }
      } finally {
        if (alive.current) setLoading(false);
      }
    })();
    return () => {
      alive.current = false;
      controller.current.abort();
      sequence.current++;
      evidenceSequence.current++;
    };
    // Component key binds this lifecycle to its initial project/run/case context.
  }, []);

  function newConversation(next = context) {
    sequence.current++;
    evidenceSequence.current++;
    setEvidence(null);
    setRule(null);
    setContext(next);
    setConversation(null);
    setMessages([]);
    setMoreMessages(false);
    setPendingJob("");
    setError("");
    restoreDraft(next);
    setDraftNotice(
      "Bản nháp chưa gửi được giữ riêng theo dự án, lượt đối soát và hội thoại trong tab này.",
    );
    setConfirmDelete(false);
    setConfirmWorkflow(null);
    pendingRequest.current = null;
    createKey.current = crypto.randomUUID();
    sessionStorage.removeItem(`${draftKey.current}.create`);
    localStorage.removeItem(storageKey);
  }
  async function send() {
    if ((!text.trim() && !files.length) || busy || pendingJob) return;
    const request = sequence.current;
    setBusy(true);
    setError("");
    let bootstrapProject="";
    try {
      if(reviewReply&&conversation){
        if(!canEdit)throw new Error("Cần quyền chỉnh sửa để trả lời yêu cầu xác nhận.");
        const body=JSON.stringify({review_id:reviewReply.id,nonce:reviewReply.nonce,
          fingerprint:reviewReply.fingerprint,text:text.trim()});
        const storage=replyKeyFor(context,conversation.id);
        let previous:{body:string;key:string}|null=null;
        try{previous=JSON.parse(sessionStorage.getItem(storage+".request")||"null");}catch{/* Invalid cache is not authority. */}
        const key=previous?.body===body?previous.key:crypto.randomUUID();
        sessionStorage.setItem(storage+".request",JSON.stringify({body,key}));
        const accepted=await api<{job_id:string}>(`/agent/workflows/${reviewReply.workflowId}/replies`,{method:"POST",body,headers:{"Idempotency-Key":key}});
        if(!alive.current||request!==sequence.current)return;
        sessionStorage.removeItem(storage);sessionStorage.removeItem(storage+".request");
        sessionStorage.removeItem(draftKey.current);setReviewReply(null);setText("");
        await refreshMessages(conversation.id,request);await waitForAnswer(accepted.job_id,conversation.id,request);return;
      }
      if(files.length){
        const body=new FormData();files.forEach(file=>body.append("files",file));
        if(context.project_id)body.append("project_id",context.project_id);
        const uploaded=await api<{project_id:string}>("/agent/attachments",{method:"POST",body,
          headers:{"Idempotency-Key":uploadKey.current}});
        if(!alive.current||request!==sequence.current)return;
        setFiles([]);uploadKey.current=crypto.randomUUID();
        if(!context.project_id){
          bootstrapProject=uploaded.project_id;
          localStorage.setItem("studio.project",uploaded.project_id);
          const next={project_id:uploaded.project_id};
          const created=await api<Conversation>("/conversations",{method:"POST",body:JSON.stringify({context:next}),
            headers:{"Idempotency-Key":createKey.current}});
          localStorage.setItem(`studio.conversation.${uploaded.project_id}`,created.id);
          const question=text.trim()||"Kiểm tra các file vừa tải lên";
          const body=JSON.stringify({conversation_id:created.id,context:created.context,text:question,
            mode:"AGENT",command:command||(!text.trim()?"EXPLORE_DATA":null)});
          const key=createKey.current+"-message";
          const pendingKey=`studio.assistant-request.${draftOwner}.${uploaded.project_id}`;
          sessionStorage.setItem(pendingKey,JSON.stringify({body,key}));
          sessionStorage.setItem(draftKeyFor(next,created.id),question);
          await api("/assistant/messages",{method:"POST",body,headers:{"Idempotency-Key":key}});
          sessionStorage.removeItem(pendingKey);sessionStorage.removeItem(draftKeyFor(next,created.id));
          if(!alive.current||request!==sequence.current)return;
          await onUploadProject(uploaded.project_id);
          return;
        }
      }
      if(!context.project_id){setError("Tải CSV/Excel lên để chọn nguồn dữ liệu cho yêu cầu này.");return;}
      let active = conversation;
      if (!active) {
        const savedCreateKey = sessionStorage.getItem(
          `${draftKey.current}.create`,
        );
        if (savedCreateKey) createKey.current = savedCreateKey;
        sessionStorage.setItem(`${draftKey.current}.create`, createKey.current);
        active = await api<Conversation>("/conversations", {
          method: "POST",
          body: JSON.stringify({ context }),
          headers: { "Idempotency-Key": createKey.current },
        });
        if (!alive.current || request !== sequence.current) return;
        setConversation(active);
        localStorage.setItem(storageKey, active.id);
        const previousDraft = draftKey.current;
        draftKey.current = draftKeyFor(context, active.id);
        sessionStorage.setItem(draftKey.current, text);
        sessionStorage.removeItem(previousDraft);
        sessionStorage.removeItem(`${previousDraft}.create`);
      }
      const body = JSON.stringify({
        conversation_id: active.id,
        context: active.context,
        text: text.trim() || "Kiểm tra các file vừa tải lên",
        mode,
        ...(mode==="AGENT"?{command:command||(!text.trim()?"EXPLORE_DATA":null)}:{}),
      });
      let previous = pendingRequest.current;
      if (!previous) {
        try {
          const saved = JSON.parse(
            sessionStorage.getItem(requestStorageKey) || "null",
          );
          if (typeof saved?.body === "string" && typeof saved?.key === "string")
            previous = saved;
        } catch {
          /* A malformed local draft is never authority to send a request. */
        }
      }
      const key = previous?.body === body ? previous.key : crypto.randomUUID();
      pendingRequest.current = { body, key };
      sessionStorage.setItem(requestStorageKey, JSON.stringify({ body, key }));
      const accepted = await api<{ job_id: string }>("/assistant/messages", {
        method: "POST",
        body,
        headers: { "Idempotency-Key": key },
      });
      if (!alive.current || request !== sequence.current) return;
      pendingRequest.current = null;
      sessionStorage.removeItem(requestStorageKey);
      setText("");
      setCommand(null);
      sessionStorage.removeItem(draftKey.current);
      await refreshMessages(active.id, request);
      await loadHistory();
      await waitForAnswer(accepted.job_id, active.id, request);
    } catch (err) {
      if(bootstrapProject&&alive.current){await onUploadProject(bootstrapProject);return;}
      if (alive.current && request === sequence.current)
        setError(errorText(err));
    } finally {
      if (alive.current && request === sequence.current) setBusy(false);
    }
  }
  async function olderMessages() {
    if (!conversation || !messages.length) return;
    const request = sequence.current;
    try {
      const page = await api<ConversationPage>(
        `/conversations/${conversation.id}?limit=20&before_id=${messages[0].id}`,
        getOptions(),
      );
      if (!alive.current || request !== sequence.current) return;
      setMessages((old) => [...page.items, ...old]);
      setMoreMessages(page.has_more);
    } catch (err) {
      if (alive.current) setError(errorText(err));
    }
  }
  async function openCitation(
    answer: AssistantAnswer,
    reference: FactReference,
  ) {
    if (!reference.group_id) {
      onNavigate("OPEN_REPORT", answer.fact_set.context);
      return;
    }
    const request = ++evidenceSequence.current;
    citationTrigger.current = document.activeElement as HTMLElement;
    setError("");
    try {
      const result = await api<SourceEvidence>(
        `/runs/${reference.run_id}/groups/${reference.group_id}/evidence`,
        getOptions(),
      );
      if (alive.current && request === evidenceSequence.current)
        setEvidence(result);
    } catch (err) {
      if (alive.current && request === evidenceSequence.current)
        setError(errorText(err));
    }
  }
  async function suggestion(target: Suggestion, answer: AssistantAnswer) {
    if (target === "OPEN_EVIDENCE") {
      const ref = answer.fact_set.references.find((r) => r.group_id);
      if (ref) await openCitation(answer, ref);
      return;
    }
    if (target === "OPEN_RULE" && answer.fact_set.context.run_id) {
      const request = ++evidenceSequence.current;
      try {
        const result = await api<{ rule: AssistantRule }>("/assistant/tools", {
          method: "POST",
          body: JSON.stringify({
            name: "get_rule",
            context: answer.fact_set.context,
          }),
        });
        if (alive.current && request === evidenceSequence.current)
          setRule({ ...result.rule, run_id: answer.fact_set.context.run_id });
      } catch (err) {
        if (alive.current && request === evidenceSequence.current)
          setError(errorText(err));
      }
      return;
    }
    onNavigate(target, answer.fact_set.context);
  }
  async function deleteConversation() {
    if (!conversation) return;
    setBusy(true);
    try {
      await api(`/conversations/${conversation.id}`, { method: "DELETE" });
      if (alive.current) {
        sessionStorage.removeItem(draftKey.current);
        newConversation();
        await loadHistory();
      }
    } catch (err) {
      if (alive.current) setError(errorText(err));
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  const selectedRun = runs.find((r) => r.id === context.run_id);
  async function agentNavigate(target:Suggestion,next:AssistantContext){
    if(target!=="OPEN_EVIDENCE"||!next.run_id||!next.group_id){onNavigate(target,next);return;}
    const request=++evidenceSequence.current;citationTrigger.current=document.activeElement as HTMLElement;
    try{const result=await api<SourceEvidence>(`/runs/${next.run_id}/groups/${next.group_id}/evidence`,getOptions());
      if(alive.current&&request===evidenceSequence.current)setEvidence(result);
    }catch(err){if(alive.current&&request===evidenceSequence.current)setError(errorText(err));}
  }
  function attach(selected:FileList | File[] | null){
    if(reviewReply){setError("Hãy gửi hoặc hủy trả lời xác nhận trước khi đính kèm tệp.");return;}
    if(!selected)return;
    const next=[...files,...Array.from(selected)];
    if(next.length>5||next.some(f=>!(/\.(csv|xlsx)$/i).test(f.name)||f.size>20*1024*1024)){
      setError("Đính kèm tối đa5file CSV/XLSX, mỗi file tối đa20MB.");return;
    }
    setError("");setFiles(next);uploadKey.current=crypto.randomUUID();
  }
  return (
    <section className={`assistant-studio ${messages.length?"has-conversation":"is-welcome"}`} aria-label="Hội thoại AI Assistant">
      <div className="assistant-toolbar">
        <button
          className="button secondary compact"
          aria-expanded={historyOpen}
          aria-controls="assistant-history-panel"
          onClick={(event) => {historyTrigger.current=event.currentTarget;setHistoryOpen(!historyOpen);}}
        >
          <MessagesSquare size={16} />
          Lịch sử
        </button>
        <div className="assistant-toolbar-actions">
          {context.project_id&&<button className="context-chip" data-run-id={context.run_id||""} aria-label="Đổi ngữ cảnh phân tích" onClick={()=>setContextOpen(true)}>{context.run_id?`${selectedRun?.metric_snapshot?.period_start||"Kết quả đang xem"} · ${selectedRun?.status==="PARTIAL_VERIFIED"?"Xác minh một phần":"Kết quả đối soát"}`:"Dữ liệu dự án"}</button>}
          {context.project_id&&<button className="icon-button" aria-label="Hội thoại mới" title="Hội thoại mới" disabled={busy||loading} onClick={()=>newConversation()}><MessageSquarePlus size={18}/></button>}
          {conversation&&<details className="assistant-menu"><summary aria-label="Tùy chọn hội thoại"><MoreHorizontal size={18}/></summary><button className="text-button" disabled={busy||!!pendingJob} onClick={()=>setConfirmDelete(true)}><Trash2 size={15}/>Xóa hội thoại</button></details>}
        <details className="assistant-policy">
          <summary>
            {(mode==="AGENT"?agentEnabled:cloudEnabled)
              ? "Gemini theo chính sách"
              : "Chế độ dữ kiện"}
          </summary>
          <p>
            Dữ kiện lấy từ backend đã xác minh.{" "}
            {(mode==="AGENT"?agentEnabled:cloudEnabled)
              ? "Suy luận cloud cần policy và reservation riêng cho từng request."
              : "Suy luận cloud của AI Assistant đang tắt; không dùng quota Gemini còn lại."}
          </p>
          <label>Xử lý yêu cầu<select aria-label="Chế độ hội thoại" value={mode} disabled={busy||!!pendingJob} onChange={e=>setMode(e.target.value as "AGENT"|"LEGACY")}><option value="AGENT">Thực hiện tác vụ dữ liệu</option><option value="LEGACY">Chỉ hỏi dữ kiện đã xác minh</option></select></label>
        </details>
        </div>
      </div>
      <div className="assistant-layout">

        <div className="assistant-conversation">
          <div className="assistant-scroll">

            {error && (
              <Notice tone="error">
                {error}
                <button
                  className="text-button"
                  onClick={() =>
                    conversation
                      ? void openConversation(conversation.id)
                      : void loadHistory().catch((err) =>
                          setError(errorText(err)),
                        )
                  }
                >
                  Cập nhật hội thoại
                </button>
              </Notice>
            )}
            {loading && <Spinner />}
            <div
              className="assistant-messages"
              role="log"
              aria-label="Nội dung hội thoại"
              aria-live="polite"
            >
              {moreMessages && (
                <button
                  className="text-button"
                  onClick={() => void olderMessages()}
                >
                  Xem tin nhắn cũ hơn
                </button>
              )}
              {!loading && !messages.length && (
                <div className="agent-empty"><Sparkles size={25} aria-hidden="true"/><h2>Bạn muốn xử lý dữ liệu gì?</h2><p>Tải file lên hoặc giao việc cho AI bằng tiếng Việt.</p></div>
              )}
              {messages.map((message) => (
                <article
                  className={`assistant-message ${message.role}`}
                  key={message.id}
                >
                  <strong>{message.role === "user" ? "Bạn" : "AI Assistant"}</strong>
                  <small>
                    {new Date(message.created_at).toLocaleString("vi-VN")} ·{" "}
                    {message.context.run_id?.slice(0, 8) || "Chuẩn bị dữ liệu"}
                  </small>
                  {message.role === "user" ? (
                    <p>{message.text}</p>
                  ) : (
                    message.answer && (
                      <>
                        <details className="assistant-mode">
                          <summary>
                            {labels[message.answer.status] ||
                              message.answer.status}
                          </summary>
                          <p>
                            {labels[message.answer.mode] || message.answer.mode}{" "}
                            · Không phải bằng chứng gọi AI live.
                          </p>
                        </details>
                        {message.answer.lines.map((line, index) => (
                          <div className="assistant-claim" key={index}>
                            <span
                              className={`claim-label ${line.classification.toLowerCase()}`}
                            >
                              {labels[line.classification] ||
                                line.classification}
                            </span>
                            <p>
                              {line.text.replace(
                                /\b[A-Z_]+\b/g,
                                (value) => reconciliationLabels[value] || value,
                              )}
                            </p>
                            {line.text.replace(
                              /\b[A-Z_]+\b/g,
                              (value) => reconciliationLabels[value] || value,
                            ) !== line.text && (
                              <details>
                                <summary>Thuật ngữ gốc</summary>
                                <p>{line.text}</p>
                              </details>
                            )}
                            {line.reference_ids.slice(0, 3).map((id) => {
                              const ref =
                                message.answer!.fact_set.references.find(
                                  (r) => r.id === id,
                                );
                              return ref ? (
                                <button
                                  className="text-button"
                                  key={id}
                                  onClick={() =>
                                    void openCitation(message.answer!, ref)
                                  }
                                >
                                  {ref.source_table_id
                                    ? `${ref.sheet} · dòng ${ref.row}`
                                    : ref.group_id
                                      ? "Nhóm đối soát"
                                      : "MetricSnapshot"}
                                </button>
                              ) : null;
                            })}
                            {line.reference_ids.length > 3 && (
                              <small>
                                Hiển thị 3/{line.reference_ids.length} tham
                                chiếu; mở bằng chứng để xem thêm.
                              </small>
                            )}
                          </div>
                        ))}
                        {message.answer.fact_set.rule_id && (
                          <details>
                            <summary>Chi tiết quy tắc và phiên bản</summary>
                            <p className="muted">
                              Rule {message.answer.fact_set.rule_id.slice(0, 8)}{" "}
                              · revision {message.answer.fact_set.rule_revision}{" "}
                              · snapshot{" "}
                              {message.answer.fact_set.snapshot?.id.slice(0, 8)}
                            </p>
                          </details>
                        )}
                        <div className="assistant-actions">
                          {message.answer.suggestions.map((target) => (
                            <button
                              className="text-button"
                              key={target}
                              disabled={
                                target === "OPEN_EVIDENCE" &&
                                !message.answer!.fact_set.references.some(
                                  (r) => r.group_id,
                                )
                              }
                              onClick={() =>
                                void suggestion(target, message.answer!)
                              }
                            >
                              {labels[target]}
                            </button>
                          ))}
                        </div>
                        {message.answer.proposal && (
                          <button
                            className="button primary"
                            onClick={() => setConfirmWorkflow(message.answer)}
                          >
                            Xem đề xuất đối soát
                          </button>
                        )}
                      </>
                    )
                  )}
                  {message.role==="assistant"&&message.workflow_id&&<AgentWorkflowPanel id={message.workflow_id} canEdit={canEdit} onNavigate={(target,next)=>void agentNavigate(target,next)} onContext={next=>{workflowContext.current=next;}} onReply={(workflowId,review)=>{if(!conversation)return;
                    if(files.length){setError("Bỏ tệp đính kèm trước khi bổ sung xác nhận.");return;}
                    const binding={workflowId,id:review.id,nonce:review.nonce,fingerprint:review.fingerprint,question:review.question};
                    setReviewReply(binding);sessionStorage.setItem(replyKeyFor(context,conversation.id),JSON.stringify(binding));composerInput.current?.focus();}}/>}
                  {message.role==="assistant"&&!message.answer&&!message.workflow_id&&<p>{message.text}</p>}
                </article>
              ))}
            </div>
            {rule && (
              <section className="card" aria-label="Rule được viện dẫn">
                <h3>{rule.plan.name}</h3>
                <p>Rule của run {rule.run_id.slice(0, 8)}</p>
                <p>
                  Revision {rule.revision} · {rule.plan.period_start} →{" "}
                  {rule.plan.period_end} · {rule.plan.timezone}
                </p>
                <p>
                  Khóa:{" "}
                  {rule.plan.join_keys
                    .map((p) => `${p.left} ↔ ${p.right}`)
                    .join(", ")}
                </p>
                <p>Đơn vị so sánh: {rule.plan.comparison_grain}</p>
                <button className="text-button" onClick={() => setRule(null)}>
                  Ẩn rule
                </button>
              </section>
            )}
            {confirmWorkflow && (
              <AssistantWorkflow
                answer={confirmWorkflow}
                canEdit={canEdit}
                onReview={onReview}
                onCancel={() => setConfirmWorkflow(null)}
                onManual={() =>
                  onNavigate(
                    "OPEN_RECONCILIATION",
                    confirmWorkflow.fact_set.context,
                  )
                }
              />
            )}
            {confirmDelete && (
              <section
                className="notice warning"
                aria-label="Xác nhận xóa hội thoại"
              >
                <div>
                  <p>
                    Xóa nội dung hội thoại này? Runs, rules, nguồn và báo cáo
                    đối soát được giữ nguyên.
                  </p>
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() => void deleteConversation()}
                  >
                    Xác nhận xóa hội thoại
                  </button>
                  <button
                    className="text-button"
                    onClick={() => setConfirmDelete(false)}
                  >
                    Hủy
                  </button>
                </div>
              </section>
            )}
            {pendingJob && (
              <Notice>
                Đang xử lý câu hỏi trong queue. Rời trang rồi quay lại vẫn xem
                được kết quả.
                <button
                  className="text-button"
                  disabled={busy || loading}
                  onClick={() =>
                    conversation && void openConversation(conversation.id)
                  }
                >
                  Cập nhật hội thoại
                </button>
              </Notice>
            )}
          </div>
          {draftNotice && (
            <p className="draft-notice" role="status">
              {draftNotice}
            </p>
          )}
          <form
            className={`assistant-composer ${reviewReply?"is-review-reply":""}`}
            onDragOver={event=>{event.preventDefault();}}
            onDrop={event=>{event.preventDefault();if(canEdit&&!busy&&!reviewReply)attach(event.dataTransfer.files);}}
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            {reviewReply&&<div className="review-reply-binding" role="status">Đang bổ sung: {reviewReply.question}<button type="button" className="icon-button" aria-label="Hủy trả lời xác nhận" onClick={()=>{setReviewReply(null);if(conversation)sessionStorage.removeItem(replyKeyFor(context,conversation.id));}}><X size={14}/></button></div>}
            <input ref={fileInput} type="file" accept=".csv,.xlsx" multiple hidden onChange={e=>{attach(e.target.files);e.target.value="";}}/>
            <button type="button" className="icon-button" aria-label="Đính kèm CSV hoặc Excel" disabled={!canEdit||busy||!!reviewReply} onClick={()=>fileInput.current?.click()}><Paperclip size={20}/></button>
            {files.length>0&&<div className="agent-file-chips">{files.map((file,i)=><span key={`${file.name}:${i}`}>{file.name} · {Math.ceil(file.size/1024)}KB<button type="button" className="icon-button" aria-label={`Bỏ ${file.name}`} disabled={busy} onClick={()=>{setFiles(files.filter((_,n)=>n!==i));uploadKey.current=crypto.randomUUID();}}><X size={14}/></button></span>)}</div>}
            <label>
              <span className="visually-hidden">Giao việc cho AI Assistant</span>
              <textarea
                ref={composerInput}
                aria-label="Câu hỏi cho AI Assistant"
                value={text}
                onChange={(event) => {
                  setText(event.target.value);
                  setCommand(null);
                  sessionStorage.setItem(draftKey.current, event.target.value);
                }}
                maxLength={2000}
                rows={2}
                placeholder={reviewReply?"Bổ sung thông tin để AI diễn giải; bạn sẽ kiểm tra lại trước khi xác nhận...":"Ví dụ: Chuẩn hóa các file này rồi đối soát giúp tôi..."}
                disabled={busy}
              />
            </label>
            <button
              className="button primary"
              disabled={busy || loading || !!pendingJob || (!text.trim()&&!files.length)}
            >
              {busy ? (
                <Spinner />
              ) : (
                <>
                  <Send size={16} />
                  Gửi câu hỏi
                </>
              )}
            </button>
          </form>
          {!messages.length&&<div className="agent-prompts">{[["Chuẩn hóa dữ liệu","PREPARE_NORMALIZATION"],["Đối soát các file",null],["Tra cứu thông tin",null],["Phân tích kết quả","SUMMARIZE_RESULTS"]].map(([title,action])=><button className="text-button" key={title} onClick={()=>{setText(title!);setCommand(action);composerInput.current?.focus();}}>{title}</button>)}</div>}
        </div>
      </div>
      <Modal title="Lịch sử" open={historyOpen} onOpenChange={setHistoryOpen} returnFocus={historyTrigger}>
        <div
          id="assistant-history-panel"
          className="assistant-history"
          aria-label="Lịch sử hội thoại"
        >
          <label>Tìm trong hội thoại đã tải<input value={historySearch} onChange={e=>setHistorySearch(e.target.value)}/></label>
          <button className="button secondary" disabled={busy||!context.project_id} onClick={()=>{newConversation();setHistoryOpen(false);}}>Hội thoại mới</button>
          <h3>
            Lịch sử hội thoại ({history.length}
            {moreHistory ? "+" : ""})
          </h3>
          {!history.length && <p>Chưa có hội thoại trong dự án này.</p>}
          {history.filter(item=>item.title.toLocaleLowerCase().includes(historySearch.toLocaleLowerCase())).map((item) => (
            <button
              key={item.id}
              className={`history-item ${conversation?.id === item.id ? "selected" : ""}`}
              aria-current={conversation?.id === item.id ? "true" : undefined}
              disabled={busy}
              onClick={() => void openConversation(item.id)}
            >
              {item.title} · {new Date(item.created_at).toLocaleString("vi-VN")}{" "}
              · {item.context.run_id ? "Đối soát" : "Chuẩn bị dữ liệu"}
            </button>
          ))}
          {moreHistory && (
            <button
              className="text-button"
              onClick={() =>
                void loadHistory(true).catch((err) => setError(errorText(err)))
              }
            >
              Tải thêm hội thoại
            </button>
          )}
        </div>      </Modal>
      <Modal title="Đổi ngữ cảnh phân tích" open={contextOpen} onOpenChange={setContextOpen}>
        <p>{projectName}. Chỉ chọn kết quả thuộc dự án này.</p>
            <div className="assistant-controls">
              <label>
                Kết quả phân tích
                <select
                  aria-label="Chọn kết quả phân tích"
                  value={context.run_id || ""}
                  disabled={loading || busy || !!pendingJob}
                  onChange={(event) => {
                    newConversation({
                      project_id: initialContext.project_id,
                      run_id: event.target.value || null,
                    });setContextOpen(false);
                  }}
                >
                  <option value="">
                    Chưa chọn run — chỉ kiểm tra chuẩn bị dữ liệu
                  </option>
                  {context.run_id && !selectedRun && (
                    <option value={context.run_id}>
                      Run {context.run_id.slice(0, 8)} · ngữ cảnh hội thoại
                    </option>
                  )}
                  {runs
                    .filter((r) =>
                      ["VERIFIED", "PARTIAL_VERIFIED"].includes(r.status),
                    )
                    .map((run) => (
                      <option key={run.id} value={run.id}>
                        Run {run.id.slice(0, 8)} ·{" "}
                        {run.status === "VERIFIED"
                          ? "Đã xác minh"
                          : "Xác minh một phần"}{" "}
                        · {run.metric_snapshot?.period_start}
                      </option>
                    ))}
                </select>
              </label>
              {runs.length < runTotal && (
                <button
                  className="text-button"
                  onClick={() =>
                    void loadRuns(true).catch((err) => setError(errorText(err)))
                  }
                >
                  Tải thêm runs
                </button>
              )}
            </div>            {(context.group_id || context.case_id) && (
              <details>
                <summary>Ngữ cảnh ngoại lệ · giữ đúng lượt đối soát</summary>
                <p className="muted">
                  Đang xem nhóm {context.group_id?.slice(0, 8)}
                  {context.case_id
                    ? ` · ngoại lệ ${context.case_id.slice(0, 8)}`
                    : ""}
                  . Câu trả lời giữ đúng run này.
                </p>
              </details>
            )}
            {context.dataset_id && (
              <p className="muted">
                Nguồn đang xem: {context.dataset_id.slice(0, 8)}. Chọn run đã
                xác minh để hỏi số liệu đối soát.
              </p>
            )}
      </Modal>
      {evidence && (
        <ReconciliationEvidence
          evidence={evidence}
          currentCase={null}
          canEdit={false}
          returnFocus={citationTrigger}
          onClose={() => setEvidence(null)}
          onReviewed={async () => {}}
        />
      )}
    </section>
  );
}
