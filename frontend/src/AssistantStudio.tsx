import { useEffect, useRef, useState } from "react";
import { MessageSquarePlus, Send, Trash2, MessagesSquare } from "lucide-react";
import { api, ApiError } from "./api";
import { Notice, Spinner } from "./components";
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
}: {
  initialContext: AssistantContext;
  onNavigate: (target: Suggestion, context: AssistantContext) => void;
  cloudEnabled?: boolean;
  canEdit: boolean;
  onReview: (planId: string) => void;
  projectName: string;
  draftOwner: string;
  onContextChange: (context: AssistantContext) => void;
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
  const [historyOpen, setHistoryOpen] = useState(
    () => window.innerWidth > 1100,
  );
  const [draftNotice, setDraftNotice] = useState("");
  const draftKeyFor = (scope: AssistantContext, id = "new") =>
    `studio.assistant-draft.${draftOwner}.${JSON.stringify([scope.project_id, scope.run_id || "", scope.dataset_id || "", scope.group_id || "", scope.case_id || "", id])}`;
  const draftKey = useRef(draftKeyFor(initialContext));
  function restoreDraft(scope: AssistantContext, id?: string) {
    draftKey.current = draftKeyFor(scope, id);
    setText(sessionStorage.getItem(draftKey.current) || "");
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
    if (window.innerWidth <= 1100) setHistoryOpen(false);
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
    if (!text.trim() || busy || pendingJob) return;
    const request = sequence.current;
    setBusy(true);
    setError("");
    try {
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
        text: text.trim(),
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
      sessionStorage.removeItem(draftKey.current);
      await refreshMessages(active.id, request);
      await loadHistory();
      await waitForAnswer(accepted.job_id, active.id, request);
    } catch (err) {
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
  return (
    <section className="assistant-studio" aria-label="Hội thoại có bằng chứng">
      <div className="assistant-toolbar">
        <button
          className="button secondary compact"
          aria-expanded={historyOpen}
          aria-controls="assistant-history-panel"
          onClick={() => setHistoryOpen(!historyOpen)}
        >
          <MessagesSquare size={16} />
          Lịch sử hội thoại
        </button>
        <details className="assistant-policy">
          <summary>
            {cloudEnabled
              ? "AI theo chính sách workspace"
              : "Chế độ dữ kiện · Không gọi AI cloud"}
          </summary>
          <p>
            Dữ kiện lấy từ backend đã xác minh.{" "}
            {cloudEnabled
              ? "Suy luận cloud cần policy và reservation riêng cho từng request."
              : "Suy luận cloud của Trợ lý đang tắt; không dùng quota Gemini còn lại."}
          </p>
        </details>
      </div>
      <div className={`assistant-layout ${historyOpen ? "history-open" : ""}`}>
        <aside
          id="assistant-history-panel"
          className="assistant-history"
          aria-label="Lịch sử hội thoại"
          hidden={!historyOpen}
        >
          <h3>
            Lịch sử hội thoại ({history.length}
            {moreHistory ? "+" : ""})
          </h3>
          {!history.length && <p>Chưa có hội thoại trong dự án này.</p>}
          {history.map((item) => (
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
        </aside>
        <div className="assistant-conversation">
          <div className="assistant-scroll">
            <p className="assistant-project">{projectName}</p>
            <div className="assistant-controls">
              <label>
                Run làm ngữ cảnh
                <select
                  aria-label="Run làm ngữ cảnh"
                  value={context.run_id || ""}
                  disabled={loading || busy || !!pendingJob}
                  onChange={(event) =>
                    newConversation({
                      project_id: initialContext.project_id,
                      run_id: event.target.value || null,
                    })
                  }
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
              <div className="assistant-actions">
                <button
                  className="button secondary"
                  disabled={busy || loading}
                  onClick={() => newConversation()}
                >
                  <MessageSquarePlus size={16} />
                  Hội thoại mới
                </button>
                <button
                  className="text-button"
                  disabled={!conversation || busy || !!pendingJob}
                  onClick={() => setConfirmDelete(true)}
                >
                  <Trash2 size={15} />
                  Xóa hội thoại
                </button>
              </div>
            </div>
            {(context.group_id || context.case_id) && (
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
                <p>
                  Chọn run hoặc mở từ một ngoại lệ để hỏi “Vì sao lệch?”. Bạn
                  cũng có thể yêu cầu kiểm tra chuẩn bị đối soát.
                </p>
              )}
              {messages.map((message) => (
                <article
                  className={`assistant-message ${message.role}`}
                  key={message.id}
                >
                  <strong>{message.role === "user" ? "Bạn" : "Trợ lý"}</strong>
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
            className="assistant-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            <label>
              Câu hỏi
              <textarea
                aria-label="Câu hỏi cho Trợ lý"
                value={text}
                onChange={(event) => {
                  setText(event.target.value);
                  sessionStorage.setItem(draftKey.current, event.target.value);
                }}
                maxLength={2000}
                rows={2}
                placeholder="Vì sao lệch? / Tóm tắt kết quả đối soát / Đối soát ba file tháng 10"
                disabled={busy}
              />
            </label>
            <button
              className="button primary"
              disabled={busy || loading || !!pendingJob || !text.trim()}
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
        </div>
      </div>
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
