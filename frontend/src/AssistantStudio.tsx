import { HistoryRows } from "./ProjectHistory";
import { useEffect, useLayoutEffect, useRef, useState, lazy, Suspense, type RefObject } from "react";
import { ArrowRight, ArrowUp, ChartNoAxesColumn, Files, FileSpreadsheet, Layers3, LoaderCircle, MessageSquarePlus, MoreHorizontal, Plus, Search, SlidersHorizontal, Trash2, X } from "lucide-react";
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
import {errorText as jobErrors, type Job} from "./types";
import type {
  AssistantAnswer,
  AssistantContext,
  AssistantMessage,
  AssistantModelOption,
  AssistantRule,
  Conversation,
  ConversationPage,
  FactReference,
  ModelChoice,
  Suggestion,
} from "./assistantTypes";

const AssistantDataDrawer = lazy(() => import("./AssistantDataDrawer").then(m => ({default:m.AssistantDataDrawer})));
const ReconciliationStudio = lazy(() => import("./ReconciliationStudio").then(m => ({default:m.ReconciliationStudio})));

const starterTasks = [
  { title: "Chuẩn hóa dữ liệu", description: "Kiểm tra cột và chuẩn bị bảng", prompt: "Kiểm tra các nguồn đã chọn và đề xuất cách chuẩn hóa dữ liệu.", command: "PREPARE_NORMALIZATION", icon: FileSpreadsheet },
  { title: "Đối soát các tệp", description: "Xác định nguồn, kỳ và quy tắc", prompt: "Tôi muốn đối soát các nguồn trong dự án. Hãy làm rõ nguồn và kỳ cần so sánh.", command: null, icon: Layers3 },
  { title: "Tra cứu thông tin", description: "Tìm giá trị trong nguồn đã chọn", prompt: "Tra cứu dữ liệu trong nguồn đang chọn.", command: null, icon: Search },
  { title: "Phân tích kết quả", description: "Đọc chỉ số và ngoại lệ đã xác minh", prompt: "Tóm tắt kết quả đối soát đang xem và những ngoại lệ cần kiểm tra.", command: "SUMMARIZE_RESULTS", icon: ChartNoAxesColumn },
];

const composerModels = [
  { id: "GEMINI", name: "Gemini 3.5 Flash Lite" },
  { id: "QWEN_8B", name: "Qwen 3:8B" },
] as const;
const historicalModelLabel = (id: ModelChoice) =>
  composerModels.find(model => model.id === id)?.name ?? "Qwen 27B";

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
  OLLAMA: "Qwen Local",
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

function sameRequestExceptModel(previous: string, next: string, reuseUploadedScope = false) {
  try {
    const before = JSON.parse(previous);
    const after = JSON.parse(next);
    delete before.model_choice;
    delete after.model_choice;
    // Receipt cũ vẫn gửi lại đúng body và key ban đầu khi người dùng thử lại.
    if (after.mode === "AUTO" && (before.mode === "AGENT" || before.mode === "LEGACY")) {
      after.mode = before.mode;
      if (before.mode === "LEGACY" && after.command === null) delete after.command;
    }
    if (reuseUploadedScope && !after.dataset_ids) {
      if (before.command === "PREPARE_UPLOAD" && after.command === null) after.command = before.command;
      delete before.dataset_ids;
    }
    return JSON.stringify(before) === JSON.stringify(after);
  } catch {
    return false;
  }
}

function MessageInfo({createdAt, model}: {createdAt: string; model?: string}) {
  return <details className="message-metadata" onKeyDown={event=>{if(event.key==="Escape"){event.preventDefault();event.currentTarget.open=false;event.currentTarget.querySelector("summary")?.focus();}}}><summary aria-label="Thông tin tin nhắn"><MoreHorizontal size={16} aria-hidden="true"/></summary><small>{new Date(createdAt).toLocaleString("vi-VN")}{model && ` · Mô hình đã chọn: ${model}`}</small></details>;
}

/** Chỉ lưu chữ ký, không lưu bytes; hash tuần tự để giới hạn bộ nhớ khi nhiều tệp. */
async function attachmentSignature(files: File[]): Promise<string> {
  const hex = (bytes: ArrayBuffer) => Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, "0")).join("");
  const members: string[][] = [];
  for (const file of files) {
    members.push([file.name, hex(await crypto.subtle.digest("SHA-256", await file.arrayBuffer()))]);
  }
  return hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(JSON.stringify(members))));
}

/** Mỗi mount thuộc một project/context; abort và sequence chặn response cũ sau chuyển scope. */
export function AssistantStudio({
  initialContext,
  onNavigate,
  canEdit,
  onReview,
  projectName,
  draftOwner,
  initialConversationId,
  onContextChange,
  onUploadProject,
  agentEnabled = false,
  historyOpen, setHistoryOpen, historyReturnFocus,
  uploadLimits, onScopeDenied,
}: {
  initialContext: AssistantContext;
  onNavigate: (target: Suggestion, context: AssistantContext) => void;
  canEdit: boolean;
  onReview: (planId: string) => void;
  projectName: string;
  draftOwner: string;
  initialConversationId?: string;
  onContextChange: (context: AssistantContext) => void;
  onUploadProject: (id: string) => Promise<void>;
  onScopeDenied: () => void;
  agentEnabled?: boolean;
  uploadLimits?: { maxBytes: number; maxFiles: number; extensions: string[] };
  historyOpen: boolean;
  setHistoryOpen: (open: boolean) => void;
  historyReturnFocus: RefObject<HTMLElement | null>;
}) {
  const modelStorageKey = `studio.assistant-model.${draftOwner}`;
  const [modelChoice, setModelChoice] = useState<ModelChoice | null>(() => {
    const saved = localStorage.getItem(modelStorageKey);
    return saved === "GEMINI" || saved === "QWEN_8B" ? saved : null;
  });
  const [models, setModels] = useState<AssistantModelOption[]>([]);
  const toolbarOptions = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !toolbarOptions.current?.contains(event.target) && toolbarOptions.current)
        toolbarOptions.current.open = false;
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);
  const [context, setContext] = useState(initialContext);
  const [modelRefresh, setModelRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const query = context.project_id ? `?project_id=${encodeURIComponent(context.project_id)}` : "";
    void api<AssistantModelOption[]>(`/assistant/models${query}`, {signal: controller.signal})
      .then(options => {
        if (controller.signal.aborted) return;
        const choices = Array.isArray(options) ? options : [];
        setModels(choices);
        const preferred = choices.find(option => option.preferred && option.available &&
          composerModels.some(model => model.id === option.id));
        if (preferred) setModelChoice(previous => previous || preferred.id);
      })
      .catch(() => { if (!controller.signal.aborted) setModels([]); });
    return () => controller.abort();
  }, [context.project_id, modelRefresh]);
  const selectedModel = modelChoice || "GEMINI";
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [history, setHistory] = useState<Conversation[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [moreHistory, setMoreHistory] = useState(false);
  const [moreMessages, setMoreMessages] = useState(false);
  const [runs, setRuns] = useState<Run[]>([]);
  const [runTotal, setRunTotal] = useState(0);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [command, setCommand] = useState<string | null>(null);
  type ReplyBinding=Pick<Review,"id"|"nonce"|"fingerprint"|"question">&{workflowId:string};
  const [reviewReply,setReviewReply]=useState<ReplyBinding|null>(null);
  const replyKeyFor=(scope:AssistantContext,id:string)=>`studio.review-reply.${draftOwner}.${scope.project_id}.${id}`;
  const fileInput = useRef<HTMLInputElement>(null);
  const [activeWorkflowContext,setActiveWorkflowContext]=useState<AssistantContext|null>(null);
  const latestWorkflowId=messages.slice().reverse().find(m=>m.role==="assistant"&&m.workflow_id)?.workflow_id;
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const sendLock = useRef(false);
  const focusAfterSend = useRef<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [pendingJob, setPendingJob] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmWorkflow, setConfirmWorkflow] =
    useState<AssistantAnswer | null>(null);
  const [evidence, setEvidence] = useState<SourceEvidence | null>(null);
  const [rule, setRule] = useState<(AssistantRule & { run_id: string }) | null>(
    null,
  );
  const [dataContext,setDataContext] = useState<AssistantContext|null>(null);
  const [resultContext,setResultContext] = useState<{context:AssistantContext;mode:"reports"|"exceptions"}|null>(null);
  const detailTrigger = useRef<HTMLElement|null>(null);
  const [contextOpen,setContextOpen]=useState(false);
  const [sourceLabel,setSourceLabel]=useState<{id:string;name:string}|null>(null);
  useEffect(()=>{
    const controller=new AbortController();
    if(context.dataset_id)void api<{id:string;name:string}>(`/datasets/${context.dataset_id}`,{signal:controller.signal})
      .then(data=>{if(!controller.signal.aborted)setSourceLabel(data);})
      .catch(()=>{});
    return()=>controller.abort();
  },[context.project_id,context.dataset_id]);
  const [historySearch,setHistorySearch]=useState("");
  const historyTrigger=historyReturnFocus;
  const deleteTrigger=useRef<HTMLElement|null>(null);
  const composerInput=useRef<HTMLTextAreaElement>(null);
  const transcript=useRef<HTMLDivElement>(null);
  const transcriptContent=useRef<HTMLDivElement>(null);
  const layout = useRef<HTMLDivElement>(null);
  const [canDock, setCanDock] = useState(false);
  useLayoutEffect(() => {
    const element = layout.current;
    if (!element) return;
    // Chừa khoảng đọc, ngăn chi tiết và khoảng cách theo vùng thực sau zoom.
    const measure = () => setCanDock(element.clientWidth >= 1184);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const docked = canDock && !!(dataContext || resultContext || evidence);
  const followTail=useRef(true);
  const forceTail=useRef(false);
  const prependAnchor=useRef<{height:number;top:number}|null>(null);
  const prependedHeight=useRef<number|null>(null);
  const loadingOlder=useRef(false);
  const [olderLoading,setOlderLoading]=useState(false);
  const [newContent,setNewContent]=useState(false);
  const lastMessageId=messages.at(-1)?.id;
  function scrollToTail(smooth=false){
    const pane=transcript.current;
    followTail.current=true;
    setNewContent(false);
    if(pane)pane.scrollTo({top:pane.scrollHeight,behavior:smooth&&!matchMedia("(prefers-reduced-motion: reduce)").matches?"smooth":"instant"});
  }
  useLayoutEffect(()=>{
    const pane=transcript.current;
    if(!pane)return;
    if(prependAnchor.current){
      const anchor=prependAnchor.current;
      pane.scrollTop=anchor.top+pane.scrollHeight-anchor.height;
      prependedHeight.current=transcriptContent.current?.getBoundingClientRect().height??null;
      prependAnchor.current=null;
    }else if(forceTail.current||followTail.current){
      pane.scrollTop=pane.scrollHeight;
      forceTail.current=false;
    }
  });
  useEffect(()=>{
    const pane=transcript.current,content=transcriptContent.current;
    if(!pane||!content)return;
    let lastHeight=content.getBoundingClientRect().height;
    let lastPaneHeight=pane.clientHeight;
    const observer=new ResizeObserver(()=>{
      const height=content.getBoundingClientRect().height;
      if(height===lastHeight&&pane.clientHeight===lastPaneHeight)return;
      const grew=height>lastHeight;
      lastHeight=height;
      lastPaneHeight=pane.clientHeight;
      const olderContent=height===prependedHeight.current;
      prependedHeight.current=null;
      if(olderContent)return;
      if(prependAnchor.current||loadingOlder.current)return;
      if(followTail.current)pane.scrollTop=pane.scrollHeight;
      else if(grew)setNewContent(true);
    });
    observer.observe(content);
    observer.observe(pane);
    return()=>observer.disconnect();
  },[]);
  useEffect(()=>{if(lastMessageId&&!followTail.current)setNewContent(true);},[lastMessageId]);
  useEffect(()=>{
    const input=composerInput.current;
    if(!input)return;
    const resize = () => {
      // Placeholder có thể xuống dòng khi bộ chọn thu hẹp ô nhập trên mobile.
      input.style.height = "";
      if (input.value) input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
    };
    resize();
    let width=0;
    // Reflow saved drafts on orientation/sidebar changes too. Ignore height-only
    // notifications so resizing the textarea cannot trigger an observer loop.
    const observer=new ResizeObserver(([entry])=>{
      if(entry&&entry.contentRect.width!==width){width=entry.contentRect.width;resize();}
    });
    observer.observe(input);
    return()=>observer.disconnect();
  },[text]);
  const [draftNotice, setDraftNotice] = useState("");
  const draftKeyFor = (scope: AssistantContext, id = "new") =>
    `studio.assistant-draft.${draftOwner}.${JSON.stringify([scope.project_id, scope.run_id || "", scope.dataset_id || "", scope.group_id || "", scope.case_id || "", id])}`;
  const draftKey = useRef(draftKeyFor(initialContext));
  function restoreDraft(scope: AssistantContext, id?: string) {
    draftKey.current = draftKeyFor(scope, id);
    const draft = sessionStorage.getItem(draftKey.current) || "";
    const draftTask = sessionStorage.getItem(`${draftKey.current}.task`);
    setText(draft);
    setCommand(starterTasks.find(task => task.title === draftTask && task.prompt === draft)?.command ?? null);
    setReviewReply(null);
    if(id){try{const saved=JSON.parse(sessionStorage.getItem(replyKeyFor(scope,id))||"null");
      if(saved&&typeof saved.id==="string"&&typeof saved.nonce==="string"&&typeof saved.fingerprint==="string"&&typeof saved.workflowId==="string")setReviewReply(saved);
    }catch{/* Server xác minh lại mọi binding trước khi ghi. */}}
    try {
      const saved=JSON.parse(sessionStorage.getItem(`studio.assistant-request.${draftOwner}.${scope.project_id}`)||"null");
      const body=saved?.body?JSON.parse(saved.body):null;
      if(body?.conversation_id===id){setCommand(body.command||null);}
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
  useLayoutEffect(() => {
    if (busy || loading || focusAfterSend.current === null) return;
    const request = focusAfterSend.current;
    focusAfterSend.current = null;
    // Focus only after React has committed the enabled textarea. An animation
    // frame can run before that commit when concurrent rendering is delayed.
    if (alive.current && request === sequence.current)
      composerInput.current?.focus({ preventScroll: true });
  }, [busy, loading]);
  useEffect(() => {
    if (!initialConversationId || conversation) onContextChange(context);
  }, [context, conversation]);

  async function loadHistory(append = false) {
    if (!initialContext.project_id) return;
    const request = ++historySequence.current;
    setHistoryLoading(true);setHistoryError("");
    const before =
      append && history.length ? `&before_id=${history.at(-1)!.id}` : "";
    try {
    const page = await api<{ items: Conversation[]; has_more: boolean }>(
      `/conversations?project_id=${initialContext.project_id}&limit=20${before}`,
      getOptions(),
    );
    if (!alive.current || request !== historySequence.current) return;
    setHistory((old) => (append ? [...old, ...page.items] : page.items));
    setMoreHistory(page.has_more);
    } catch(err) {
      if (alive.current && request === historySequence.current) {
        if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {
          setHistory([]);
          setMoreHistory(false);
          onScopeDenied();
        }
        setHistoryError(errorText(err));
      }
    } finally {
      if(alive.current && request===historySequence.current)setHistoryLoading(false);
    }
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
    // A slow accepted job remains observable beyond the initial 30-second burst.
    // These are GETs only; leaving/changing the conversation cancels the monitor.
    for (let attempt = 0; alive.current && request === sequence.current; attempt++) {
      const job = await api<Job>(`/jobs/${jobId}`, getOptions());
      if (!alive.current || request !== sequence.current) return;
      if (
        ["SUCCEEDED", "BLOCKED", "FAILED", "CANCELLED"].includes(job.status)
      ) {
        setPendingJob("");
        const page=await refreshMessages(id, request);
        if (alive.current && request === sequence.current) setModelRefresh(value => value + 1);
        if (job.status !== "SUCCEEDED"&&!page?.items.some(message=>message.job_id===jobId&&(message.role==="assistant"||message.error_code)))
          setError(
            `${jobErrors[job.error_code||""]||"Yêu cầu chưa có kết quả hợp lệ."} Lịch sử được giữ; không tự gửi lại nhà cung cấp AI.`,
          );
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, attempt < 60 ? 500 : 2000));
    }
  }
  async function openConversation(id: string, cached?: ConversationPage) {
    followTail.current=true;
    forceTail.current=true;
    setNewContent(false);
    const request = ++sequence.current;
    evidenceSequence.current++;
    setEvidence(null);
    setDataContext(null);
    setResultContext(null);
    setRule(null);
    setMessages([]);
    setActiveWorkflowContext(null);
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
    const initialSequence = sequence.current;
    const initialSignal = controller.current.signal;
    restoreDraft(initialContext);
    void (async () => {
      try {
        await Promise.all([loadHistory(), loadRuns()]);
        if (initialSignal.aborted || !alive.current || sequence.current !== initialSequence) return;
        if (initialConversationId) {
          await openConversation(initialConversationId);
          return;
        }
        const saved = localStorage.getItem(storageKey);
        if (saved) {
          // A contextual link may resume only the exact same scope, never another run/case.
          const savedPage = await api<ConversationPage>(
            `/conversations/${saved}?limit=20`,
            getOptions(),
          );
          if (initialSignal.aborted || !alive.current || sequence.current !== initialSequence) return;
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
        if (alive.current && !initialSignal.aborted) {
          setError(errorText(err));
          if (
            err instanceof ApiError &&
            ["RESOURCE_NOT_FOUND", "FORBIDDEN"].includes(err.code)
          )
            localStorage.removeItem(storageKey);
        }
      } finally {
        if (alive.current && !initialSignal.aborted) setLoading(false);
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
    followTail.current=true;
    forceTail.current=true;
    setNewContent(false);
    sequence.current++;
    evidenceSequence.current++;
    setEvidence(null);
    setDataContext(null);
    setResultContext(null);
    setRule(null);
    setContext(next);
    setConversation(null);
    setMessages([]);
    setActiveWorkflowContext(null);
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
    if ((!text.trim() && !files.length) || busy || pendingJob || sendLock.current) return;
    sendLock.current = true;
    forceTail.current=true;
    followTail.current=true;
    setNewContent(false);
    const request = sequence.current;
    setBusy(true);
    setError("");
    let bootstrapProject="";
    let uploadedDatasetIds: string[] | undefined;
    try {
      if(reviewReply&&conversation){
        if(!canEdit)throw new Error("Cần quyền chỉnh sửa để trả lời yêu cầu xác nhận.");
        let body=JSON.stringify({review_id:reviewReply.id,nonce:reviewReply.nonce,
          fingerprint:reviewReply.fingerprint,text:text.trim(), ...(modelChoice ? {model_choice:modelChoice} : {})});
        const storage=replyKeyFor(context,conversation.id);
        let previous:{body:string;key:string}|null=null;
        try{previous=JSON.parse(sessionStorage.getItem(storage+".request")||"null");}catch{/* Invalid cache is not authority. */}
        if (previous && sameRequestExceptModel(previous.body, body)) body = previous.body;
        const key=previous?.body===body?previous.key:crypto.randomUUID();
        sessionStorage.setItem(storage+".request",JSON.stringify({body,key}));
        const accepted=await api<{job_id:string}>(`/agent/workflows/${reviewReply.workflowId}/replies`,{method:"POST",body,headers:{"Idempotency-Key":key}});
        if(!alive.current||request!==sequence.current)return;
        sessionStorage.removeItem(storage);sessionStorage.removeItem(storage+".request");
        sessionStorage.removeItem(draftKey.current);
        sessionStorage.removeItem(`${draftKey.current}.task`);
        setReviewReply(null);setText("");
        await refreshMessages(conversation.id,request);await waitForAnswer(accepted.job_id,conversation.id,request);return;
      }
      if(files.length){
        const storage = `studio.attachment-request.${draftOwner}.${context.project_id || "new"}`;
        const signature = await attachmentSignature(files);
        if(!alive.current||request!==sequence.current)return;
        let key = crypto.randomUUID();
        try {
          const pending = JSON.parse(sessionStorage.getItem(storage) || "null");
          if(pending?.signature === signature && typeof pending.key === "string") key = pending.key;
        } catch { /* Server vẫn kiểm bytes/scope; cache không cấp quyền. */ }
        sessionStorage.setItem(storage, JSON.stringify({signature, key}));
        const body=new FormData();files.forEach(file=>body.append("files",file));
        if(context.project_id)body.append("project_id",context.project_id);
        const uploaded=await api<{project_id:string; items?: {id:string}[]}>("/agent/attachments",{method:"POST",body,
          headers:{"Idempotency-Key":key}});
        uploadedDatasetIds = uploaded.items?.map(item => item.id);
        if(!alive.current||request!==sequence.current)return;
        setFiles([]);sessionStorage.removeItem(storage);
        if(!context.project_id){
          bootstrapProject=uploaded.project_id;
          localStorage.setItem("studio.project",uploaded.project_id);
          const next={project_id:uploaded.project_id};
          const created=await api<Conversation>("/conversations",{method:"POST",body:JSON.stringify({context:next}),
            headers:{"Idempotency-Key":createKey.current}});
          localStorage.setItem(`studio.conversation.${uploaded.project_id}`,created.id);
          const question=text.trim()||"Chuẩn bị dữ liệu vừa tải";
          const body=JSON.stringify({conversation_id:created.id,context:created.context,text:question,
            mode:"AUTO",command:command||(!text.trim()&&uploadedDatasetIds?.length?"PREPARE_UPLOAD":null),
            ...(uploadedDatasetIds?.length ? {dataset_ids:uploadedDatasetIds} : {}),
            ...(modelChoice && (text.trim() || command || !uploadedDatasetIds?.length) ? {model_choice:modelChoice} : {})});
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
        const draftTask = sessionStorage.getItem(`${previousDraft}.task`);
        if (draftTask) sessionStorage.setItem(`${draftKey.current}.task`, draftTask);
        sessionStorage.removeItem(`${previousDraft}.task`);
        sessionStorage.removeItem(previousDraft);
        sessionStorage.removeItem(`${previousDraft}.create`);
      }
      let body = JSON.stringify({
        conversation_id: active.id,
        context: active.context,
        text: text.trim() || "Chuẩn bị dữ liệu vừa tải",
        mode: "AUTO",
        ...(modelChoice && (text.trim() || command || !uploadedDatasetIds?.length) ? {model_choice:modelChoice} : {}),
        ...(uploadedDatasetIds?.length ? {dataset_ids:uploadedDatasetIds} : {}),
        command: command||(!text.trim()&&uploadedDatasetIds?.length?"PREPARE_UPLOAD":null),
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
      if (previous && sameRequestExceptModel(previous.body, body, !uploadedDatasetIds?.length))
        body = previous.body;
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
      sessionStorage.removeItem(`${draftKey.current}.task`);
      await refreshMessages(active.id, request);
      await loadHistory();
      await waitForAnswer(accepted.job_id, active.id, request);
    } catch (err) {
      if(bootstrapProject&&alive.current){await onUploadProject(bootstrapProject);return;}
      if (alive.current && request === sequence.current)
        setError(errorText(err));
    } finally {
      sendLock.current = false;
      if (alive.current && request === sequence.current) {
        focusAfterSend.current = request;
        setBusy(false);
      }
    }
  }
  async function olderMessages() {
    if (!conversation || !messages.length || loadingOlder.current) return;
    loadingOlder.current=true;
    setOlderLoading(true);
    followTail.current=false;
    const request = sequence.current;
    try {
      const page = await api<ConversationPage>(
        `/conversations/${conversation.id}?limit=20&before_id=${messages[0].id}`,
        getOptions(),
      );
      if (!alive.current || request !== sequence.current) return;
      if(transcript.current)prependAnchor.current={height:transcript.current.scrollHeight,top:transcript.current.scrollTop};
      setMessages((old) => [...page.items, ...old]);
      setMoreMessages(page.has_more);
    } catch (err) {
      if (alive.current) setError(errorText(err));
    } finally {
      loadingOlder.current=false;
      if(alive.current)setOlderLoading(false);
    }
  }
  async function openCitation(
    answer: AssistantAnswer,
    reference: FactReference,
  ) {
    if (!reference.group_id) {
      openDetail("OPEN_REPORT", answer.fact_set.context);
      return;
    }
    await openEvidence(reference.run_id, reference.group_id);
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
    openDetail(target, answer.fact_set.context);
  }
  async function deleteConversation() {
    if (!conversation) return;
    setBusy(true);
    try {
      await api(`/conversations/${conversation.id}`, { method: "DELETE" });
      if (alive.current) {
        sessionStorage.removeItem(draftKey.current);
        sessionStorage.removeItem(`${draftKey.current}.task`);
        newConversation();
        await loadHistory();
      }
    } catch (err) {
      if (alive.current) setError(errorText(err));
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  const displayContext=activeWorkflowContext||context;
  const selectedRun = runs.find((r) => r.id === displayContext.run_id);
  async function agentNavigate(target:Suggestion,next:AssistantContext){
    if(target!=="OPEN_EVIDENCE"||!next.run_id||!next.group_id){openDetail(target,next);return;}
    if (next.project_id === context.project_id) await openEvidence(next.run_id, next.group_id);
  }
  async function openEvidence(runId: string, groupId: string) {
    setDataContext(null);
    setResultContext(null);
    setError("");
    const request = ++evidenceSequence.current;
    const trigger = document.activeElement as HTMLElement | null;
    try {
      const result = await api<SourceEvidence>(
        `/runs/${runId}/groups/${groupId}/evidence`, getOptions(),
      );
      if (alive.current && request === evidenceSequence.current) {
        citationTrigger.current = trigger;
        setEvidence(result);
      }
    } catch (err) {
      if (alive.current && request === evidenceSequence.current) setError(errorText(err));
    }
  }
  function openDetail(target:Suggestion,next:AssistantContext){
    evidenceSequence.current++;
    setEvidence(null);
    setDataContext(null);
    setResultContext(null);
    if(next.project_id!==context.project_id)return;
    detailTrigger.current=document.activeElement as HTMLElement;
    if(target==="OPEN_DATA")setDataContext(next);
    else if(target==="OPEN_REPORT"||target==="OPEN_EXCEPTIONS"){
      if(!next.run_id){setContextOpen(true);return;}
      setResultContext({context:next,mode:target==="OPEN_REPORT"?"reports":"exceptions"});
    }else onNavigate(target,next);
  }
  function attach(selected:FileList | File[] | null){
    if(reviewReply){setError("Hãy gửi hoặc hủy trả lời xác nhận trước khi đính kèm tệp.");return;}
    if(!selected)return;
    const next=[...files,...Array.from(selected)];
    if(!uploadLimits){setError("Chưa tải được giới hạn tệp. Hãy tải lại trang trước khi đính kèm.");return;}
    if(next.length>uploadLimits.maxFiles||next.some(f=>!uploadLimits.extensions.some(ext=>f.name.toLowerCase().endsWith(ext))||f.size>uploadLimits.maxBytes)){
      setError(`Đính kèm tối đa ${uploadLimits.maxFiles} tệp ${uploadLimits.extensions.map(ext=>ext.slice(1).toUpperCase()).join("/")}, mỗi tệp tối đa ${uploadLimits.maxBytes/1048576} MB.`);return;
    }
    setError("");setFiles(next);
  }
  return (
    <section className={`assistant-studio ${messages.length?"has-conversation":"is-welcome"}`} aria-label="Hội thoại AI Assistant">
      <div className="assistant-toolbar" aria-label="Công cụ hội thoại">
        <h1>AI Assistant</h1>
        <div className="assistant-toolbar-actions">
          {context.project_id&&<button className="icon-button" aria-label="Tệp đã tải" title="Tệp đã tải" onClick={()=>openDetail("OPEN_DATA",displayContext)}><Files size={18}/></button>}
          {context.project_id&&<button className="icon-button context-chip" data-run-id={displayContext.run_id||""} data-dataset-id={displayContext.dataset_id||""} aria-label="Đổi ngữ cảnh phân tích" title={displayContext.run_id?`${selectedRun?.metric_snapshot?.period_start||"Kết quả đang xem"} · ${selectedRun?.status==="PARTIAL_VERIFIED"?"Xác minh một phần":"Kết quả đối soát"}`:displayContext.dataset_id?(sourceLabel?.id===displayContext.dataset_id?sourceLabel.name:"Nguồn đang xem"):"Chọn dữ liệu phân tích"} onClick={()=>setContextOpen(true)}><SlidersHorizontal size={18}/><span className="visually-hidden">{displayContext.dataset_id&&sourceLabel?.id===displayContext.dataset_id?sourceLabel.name:"Chọn dữ liệu phân tích"}</span></button>}
          {context.project_id&&<button className="icon-button" aria-label="Hội thoại mới" title="Hội thoại mới" disabled={busy||loading} onClick={()=>newConversation()}><MessageSquarePlus size={18}/></button>}
          <details ref={toolbarOptions} className="assistant-policy assistant-menu" onKeyDown={event=>{if(event.key==="Escape"){event.preventDefault();event.currentTarget.open=false;event.currentTarget.querySelector('summary')?.focus();}}}>
            <summary aria-label="Tùy chọn hội thoại" title="Tùy chọn hội thoại"><MoreHorizontal size={18}/></summary>
            <div className="assistant-options">
              <strong>Tùy chọn hội thoại</strong>
              {selectedModel === "GEMINI" && !agentEnabled &&
                <p>Bạn vẫn có thể hỏi về các kết quả đã xác minh hoặc dùng Đối soát thủ công.</p>}
              {(models.length > 0 || modelChoice) && <label>Trợ lý<select
              aria-label="Trợ lý cho tin nhắn mới"
              value={selectedModel}
              disabled={busy && !pendingJob}
              onFocus={() => setModelRefresh(value => value + 1)}
              onChange={event => {
                const choice = models.find(option => option.id === event.target.value && option.available);
                if (!choice) return;
                localStorage.setItem(modelStorageKey, choice.id);
                setModelChoice(choice.id);
              }}
            >
              {composerModels.map(model => (
                <option key={model.id} value={model.id}
                  disabled={!models.some(option => option.id === model.id && option.available)}>
                  {model.name}
                </option>
              ))}
            </select></label>}
              {context.project_id&&<button className="text-button" onClick={()=>onNavigate("OPEN_RECONCILIATION",displayContext)}>Thiết lập đối soát thủ công</button>}
              {conversation&&<button className="text-button" disabled={busy||!!pendingJob} onClick={event=>{deleteTrigger.current=event.currentTarget;setConfirmDelete(true);}}><Trash2 size={15}/>Xóa hội thoại</button>}
            </div>
          </details>
        </div>
      </div>
      <div ref={layout} className={`assistant-layout${docked ? " has-context" : ""}`}>

        <div className="assistant-conversation">
          <div className="assistant-scroll" ref={transcript} onScroll={()=>{
            const pane=transcript.current;
            if(!pane||loadingOlder.current||prependAnchor.current)return;
            followTail.current=pane.scrollHeight-pane.scrollTop-pane.clientHeight<64;
            if(followTail.current)setNewContent(false);
          }}>
            <div ref={transcriptContent}>

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
                  disabled={olderLoading}
                  onClick={() => void olderMessages()}
                >
                  Xem tin nhắn cũ hơn
                </button>
              )}
              {!loading && !messages.length && (
                <div className="agent-empty">
                  <h2>Bạn muốn xử lý dữ liệu gì?</h2>
                  <p>{context.project_id
                    ? "Chọn một việc để bắt đầu, hoặc đính kèm tệp CSV/XLSX và nhập yêu cầu của bạn."
                    : "Đính kèm CSV/XLSX để bắt đầu. Chọn dự án để tra cứu dữ liệu hoặc đọc kết quả đã lưu."}</p>
                </div>
              )}
              {messages.filter((message,index)=>message.role!=="assistant"||!message.workflow_id||!messages.slice(index+1).some(next=>next.role==="assistant"&&next.workflow_id===message.workflow_id)).map((message) => (
                <article
                  className={`assistant-message ${message.role}`}
                  key={message.id}
                  aria-label={message.role === "user" ? "Tin nhắn của bạn" : "Phản hồi của trợ lý"}
                >
                  {message.role==="user"&&<MessageInfo createdAt={message.created_at}/>}
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
                  {message.role==="assistant"&&message.workflow_id&&<AgentWorkflowPanel id={message.workflow_id} canEdit={canEdit} draftOwner={draftOwner} onNavigate={(target,next)=>void agentNavigate(target,next)} onContext={next=>{if(message.workflow_id===latestWorkflowId&&next.project_id===context.project_id)setActiveWorkflowContext(old=>JSON.stringify(old)===JSON.stringify(next)?old:next);}} onReply={(workflowId,review)=>{if(!conversation)return;
                    if(files.length){setError("Bỏ tệp đính kèm trước khi bổ sung xác nhận.");return;}
                    const binding={workflowId,id:review.id,nonce:review.nonce,fingerprint:review.fingerprint,question:review.question};
                    setReviewReply(binding);sessionStorage.setItem(replyKeyFor(context,conversation.id),JSON.stringify(binding));composerInput.current?.focus();}}/>}
                  {message.role==="assistant"&&!message.answer&&!message.workflow_id&&<p>{message.text}</p>}
                  {message.role==="user"&&message.error_code&&["FAILED","BLOCKED","CANCELLED"].includes(message.job_status||"")&&!messages.some(m=>m.role==="assistant"&&m.job_id===message.job_id)&&<Notice tone="error">{jobErrors[message.error_code]||"Yêu cầu này chưa hoàn tất. Hãy kiểm tra dữ liệu và kết quả đã lưu trước khi tạo yêu cầu mới."}<details><summary>Chi tiết hỗ trợ</summary>{message.error_code} · {message.job_id}</details></Notice>}
                  {message.role==="assistant"&&<MessageInfo createdAt={message.created_at} model={message.model_choice ? historicalModelLabel(message.model_choice) : undefined}/>}
                </article>
              ))}
            </div>
            {rule && (
              <section className="card" aria-label="Quy tắc áp dụng">
                <h3>{rule.plan.name}</h3>
                <p>Lượt đối soát {rule.run_id.slice(0, 8)}</p>
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
            {pendingJob && (
              <Notice>
                Đang xử lý yêu cầu. Bạn có thể mở lại kết quả từ Lịch sử.
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
          </div>
          {newContent&&<button type="button" className="assistant-jump text-button" onClick={()=>scrollToTail(true)}>Tin nhắn mới · Xuống cuối</button>}
          {draftNotice && (
            <p className="draft-notice" role="status">
              {draftNotice}
            </p>
          )}
          {!loading && !messages.length && (
            <ul className="agent-prompts" aria-label="Việc có thể làm với Assistant">
              {starterTasks.map(({ title, description, prompt, command: action, icon: Icon }, index) => (
                <li key={title}>
                  <button type="button" className="assistant-task"
                    disabled={busy || !!reviewReply || (!context.project_id && index > 1)
                      || (!!text.trim() && !starterTasks.some(task => task.prompt === text))}
                    onClick={() => {
                      setText(prompt);
                      setCommand(action);
                      sessionStorage.setItem(draftKey.current, prompt);
                      sessionStorage.setItem(`${draftKey.current}.task`, title);
                      composerInput.current?.focus();
                    }}>
                    <Icon size={20} aria-hidden="true" />
                    <span><strong>{title}</strong><small>{description}</small></span>
                    <ArrowRight size={16} aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
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
            <button type="button" className="icon-button" aria-label="Đính kèm CSV hoặc Excel" disabled={!canEdit||busy||!!reviewReply} onClick={()=>fileInput.current?.click()}><Plus size={22}/></button>
            {files.length>0&&<div className="agent-file-chips">{files.map((file,i)=><span key={`${file.name}:${i}`}>{file.name} · {Math.ceil(file.size/1024)}KB<button type="button" className="icon-button" aria-label={`Bỏ ${file.name}`} disabled={busy} onClick={()=>setFiles(files.filter((_,n)=>n!==i))}><X size={14}/></button></span>)}</div>}
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
                  sessionStorage.removeItem(`${draftKey.current}.task`);
                }}
                onKeyDown={event=>{
                  if(event.key==="Enter"&&!event.shiftKey&&!event.nativeEvent.isComposing){
                    event.preventDefault();
                    if(!busy&&!loading&&!pendingJob&&(text.trim()||files.length))void send();
                  }
                }}
                maxLength={2000}
                rows={1}
                placeholder={reviewReply?"Bổ sung thông tin…":"Nhập yêu cầu…"}
                disabled={busy||loading}
              />
            </label>
            <div className="composer-actions">
            <button
              className="composer-send"
              aria-label="Gửi câu hỏi"
              title="Gửi câu hỏi"
              disabled={busy || loading || !!pendingJob || (!text.trim()&&!files.length)}
            >
              {busy ? (
                <LoaderCircle size={18} className="spin" aria-label="Đang gửi" />
              ) : (
                <ArrowUp size={20} aria-hidden="true" />
              )}
            </button>
            </div>
          </form>
        </div>
        {dataContext && <Suspense fallback={<Spinner />}>
          <AssistantDataDrawer key={`${dataContext.project_id}:${dataContext.dataset_id || ""}`}
            context={dataContext} docked={docked} onClose={() => setDataContext(null)}
            returnFocus={detailTrigger} onManual={next => {
              setDataContext(null);
              onNavigate("OPEN_DATA", next);
            }} />
        </Suspense>}
        {resultContext && <Suspense fallback={<Spinner />}>
            <ReconciliationStudio key={`${resultContext.context.run_id}:${resultContext.mode}`}
              projectId={context.project_id} canEdit={canEdit} mode={resultContext.mode}
              requestedPlan={null} requestedRun={{ id: resultContext.context.run_id!, caseId: resultContext.context.case_id, request: 1 }}
              panel={{ docked, onClose: () => setResultContext(null), returnFocus: detailTrigger }}
              onRunSelected={() => {}}
              onAsk={next => { setResultContext(null); newConversation(next); }}
              onSetup={() => { setResultContext(null); onNavigate("OPEN_RECONCILIATION", resultContext.context); }} />
          </Suspense>}
        {evidence && <ReconciliationEvidence key={evidence.group.id} evidence={evidence} currentCase={null}
          canEdit={false} docked={docked} returnFocus={citationTrigger}
          onClose={() => { evidenceSequence.current++; setEvidence(null); }} onReviewed={async () => {}} />}
      </div>
      <Modal title="Xác nhận xóa hội thoại" open={confirmDelete} onOpenChange={setConfirmDelete} returnFocus={deleteTrigger}>
        <p>Xóa nội dung hội thoại này? Lượt đối soát, quy tắc, nguồn dữ liệu và báo cáo được giữ nguyên.</p>
        <div className="modal-actions"><button className="button secondary" disabled={busy} onClick={()=>setConfirmDelete(false)}>Hủy</button><button className="button primary" disabled={busy} onClick={()=>void deleteConversation()}>Xác nhận xóa hội thoại</button></div>
      </Modal>
      <Modal title="Lịch sử" open={historyOpen} onOpenChange={setHistoryOpen} returnFocus={historyTrigger}>
        <div
          id="assistant-history-panel"
          className="assistant-history"
          aria-label="Lịch sử hội thoại"
        >
          <p className="muted"><strong>{projectName}</strong></p>
          <label>Tìm trong hội thoại đã tải<input value={historySearch} onChange={e=>setHistorySearch(e.target.value)}/></label>
          <button className="button secondary" disabled={busy||!context.project_id} onClick={()=>{newConversation();setHistoryOpen(false);}}>Hội thoại mới</button>
          <h3>
            Lịch sử hội thoại ({history.length}
            {moreHistory ? "+" : ""})
          </h3>
          {historyLoading && <Spinner/>}
          {historyError && <Notice tone="error">Không tải được lịch sử: {historyError}<button className="text-button" onClick={()=>void loadHistory()}>Tải lại lịch sử</button></Notice>}
          {!historyLoading && !historyError && !history.length && <p>Chưa có hội thoại trong dự án này.</p>}
          {!historyLoading && !historyError && history.length>0 && !history.some(item=>item.title.toLocaleLowerCase().includes(historySearch.toLocaleLowerCase())) && <p>Không có hội thoại phù hợp trong danh sách đã tải.</p>}
          <HistoryRows items={history.filter(item => item.title.toLocaleLowerCase().includes(historySearch.trim().toLocaleLowerCase()))}
            current={conversation?.id} busy={busy} onOpen={id => void openConversation(id)} />
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
                  value={displayContext.run_id || ""}
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
                  {displayContext.run_id && !selectedRun && (
                    <option value={displayContext.run_id}>
                      Run {displayContext.run_id.slice(0, 8)} · ngữ cảnh hội thoại
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
            {displayContext.dataset_id && <>
              <p className="muted">Nguồn đang xem: {sourceLabel?.id===displayContext.dataset_id?sourceLabel.name:"Tệp đang chọn"}. Phạm vi này chỉ gồm một nguồn.</p>
              <button className="button secondary" disabled={busy||!!pendingJob||loading} onClick={()=>{newConversation({project_id:context.project_id});setContextOpen(false);}}>Dùng dữ liệu của dự án</button>
            </>}
      </Modal>
    </section>
  );
}
