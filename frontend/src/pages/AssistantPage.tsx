import { useCallback, useEffect, useRef, useState, type DragEvent, type FormEvent, type KeyboardEvent } from "react";
import {
  FileSpreadsheet,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Paperclip,
  SendHorizontal,
  Trash2,
  Upload,
  X,
} from "lucide-react";

import {
  createThread,
  decideAction,
  deleteThread,
  getThread,
  listDatasets,
  listThreads,
  sendChat,
  uploadDataset,
  type ChatAction,
  type ChatMessage,
  type ChatThread,
  type ChatThreadSummary,
} from "../api";
import { ChatMessageView } from "../components/ChatMessageView";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { formatCount, formatDateTime } from "../format";

// Trang AI Assistant (docs/DECISIONS.md 2026-11-23): danh sách cuộc trò chuyện bên trái,
// khung chat bên phải. Tệp kéo-thả hoặc đính kèm được tải lên bằng đúng API của trang Dữ
// liệu rồi gửi kèm câu chat; Assistant chờ đọc, ánh xạ, làm sạch xong mới trả lời. Câu trả
// lời đang soạn được hỏi lại mỗi giây để hiện từng bước (không streaming).

const POLL_MS = 1000;
const LAST_THREAD = "assistant.thread";
const THREADS_COLLAPSED = "assistant.threads-collapsed";
const ACCEPT = ".csv,.xlsx";
const SUGGESTIONS = [
  "Còn ca nào cần tôi xử lý?",
  "Đối soát kỳ mới nhất giúp tôi.",
  "Dữ liệu nào còn lỗi cần sửa?",
  "Có khoản tiền nào về mà không rõ của đơn nào không?",
];

type Attachment = { key: string; name: string; progress: number; datasetId?: string; error?: string };

const message = (reason: unknown, fallback: string) => (reason instanceof Error ? reason.message : fallback);

function remember(id: string | null) {
  try {
    if (id) window.localStorage.setItem(LAST_THREAD, id);
    else window.localStorage.removeItem(LAST_THREAD);
  } catch {
    // Trình duyệt chặn lưu trữ: chỉ mất việc nhớ cuộc trò chuyện gần nhất.
  }
}

function stored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function store(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Trình duyệt chặn lưu trữ: chỉ mất việc nhớ lựa chọn giữa các lần mở trang.
  }
}

function recalled(): string | null {
  try {
    return window.localStorage.getItem(LAST_THREAD);
  } catch {
    return null;
  }
}

export function AssistantPage() {
  const [threads, setThreads] = useState<ChatThreadSummary[] | null>(null);
  const [thread, setThread] = useState<ChatThread | null>(null);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<Attachment[]>([]);
  const [dragging, setDragging] = useState(false);
  // Cột cuộc trò chuyện thu gọn được để khung chat rộng hơn; nhớ lựa chọn trong trình duyệt.
  const [collapsed, setCollapsed] = useState(() => stored(THREADS_COLLAPSED) === "1");
  const [sending, setSending] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [removing, setRemoving] = useState<ChatThreadSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dataSummary, setDataSummary] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refreshList = useCallback(() => {
    listThreads().then(setThreads).catch(() => undefined);
  }, []);

  // Lần đầu: danh sách cuộc trò chuyện, mở lại cuộc gần nhất; tóm tắt dữ liệu hiện có.
  useEffect(() => {
    const controller = new AbortController();
    listThreads(controller.signal)
      .then((found) => {
        setThreads(found);
        const wanted = found.find((item) => item.id === recalled()) ?? found[0];
        if (wanted) return getThread(wanted.id, controller.signal).then(setThread);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(message(reason, "Không tải được cuộc trò chuyện."));
      });
    listDatasets(controller.signal)
      .then((datasets) => {
        const tables = datasets.flatMap((item) => item.tables).filter((table) => table.status !== "NO_DATA");
        const clean = tables.filter((table) => table.clean_status === "READY").length;
        const busy = tables.length - clean;
        setDataSummary(
          datasets.length === 0
            ? "Chưa có tệp nào. Kéo tệp CSV hoặc Excel vào đây để bắt đầu."
            : `Đang có ${formatCount(datasets.length)} tệp, ${formatCount(clean)} bảng đã làm sạch sẵn sàng đối soát` +
                (busy > 0 ? `, ${formatCount(busy)} bảng đang xử lý hoặc chưa ánh xạ.` : "."),
        );
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  // Câu trả lời đang soạn: hỏi lại mỗi giây để hiện từng bước. Một lần hỏi lỗi (mạng chập
  // chờn, backend khởi động lại) thì vẫn hỏi lại lần sau, không đứng hình ở "đang suy nghĩ".
  const [pollMiss, setPollMiss] = useState(0);
  useEffect(() => {
    if (!thread?.running) return;
    const timer = window.setTimeout(() => {
      getThread(thread.id)
        .then((next) => {
          setThread(next);
          if (!next.running) refreshList();
        })
        .catch(() => setPollMiss((value) => value + 1));
    }, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [thread, pollMiss, refreshList]);

  // Cuộn xuống tin mới nhất khi có thay đổi.
  const lastMessage = thread?.messages.at(-1);
  const scrollKey = `${thread?.messages.length ?? 0}:${lastMessage?.steps.length ?? 0}:${lastMessage?.status ?? ""}`;
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [scrollKey]);

  async function open(id: string) {
    try {
      setThread(await getThread(id));
      remember(id);
      setError(null);
    } catch (reason) {
      setError(message(reason, "Không mở được cuộc trò chuyện."));
    }
  }

  function startNew() {
    setThread(null);
    remember(null);
    setText("");
    setFiles([]);
    inputRef.current?.focus();
  }

  function attach(list: FileList | File[]) {
    for (const file of Array.from(list)) {
      const key = `${file.name}:${file.size}:${Date.now()}:${Math.random()}`;
      setFiles((current) => [...current, { key, name: file.name, progress: 0 }]);
      uploadDataset(file, (progress) =>
        setFiles((current) => current.map((item) => (item.key === key ? { ...item, progress } : item))),
      )
        .then((reply) =>
          setFiles((current) =>
            current.map((item) => (item.key === key ? { ...item, progress: 1, datasetId: reply.dataset.id } : item)),
          ),
        )
        .catch((reason: unknown) =>
          setFiles((current) =>
            current.map((item) => (item.key === key ? { ...item, error: message(reason, "Tải lên thất bại.") } : item)),
          ),
        );
    }
  }

  const uploading = files.some((file) => !file.datasetId && !file.error);
  const ready = files.filter((file) => file.datasetId);
  const canSend = !sending && !thread?.running && !uploading && (text.trim().length > 0 || ready.length > 0);

  async function send(question: string) {
    if (sending || thread?.running || uploading) return;
    const datasetIds = ready.map((file) => file.datasetId as string);
    if (!question.trim() && datasetIds.length === 0) return;
    setSending(true);
    try {
      const target = thread ?? (await createThread());
      const next = await sendChat(target.id, question.trim(), datasetIds);
      setThread(next);
      remember(next.id);
      setText("");
      setFiles([]);
      setError(null);
      refreshList();
    } catch (reason) {
      setError(message(reason, "Không gửi được câu hỏi."));
    } finally {
      setSending(false);
    }
  }

  async function decide(target: ChatMessage, action: ChatAction, decision: "CONFIRM" | "CANCEL") {
    setDeciding(true);
    try {
      setThread(await decideAction(target.id, action.id, decision));
      setError(null);
    } catch (reason) {
      setError(message(reason, "Không thực hiện được."));
    } finally {
      setDeciding(false);
    }
  }

  async function remove(item: ChatThreadSummary) {
    try {
      await deleteThread(item.id);
      if (thread?.id === item.id) startNew();
      setRemoving(null);
      refreshList();
    } catch (reason) {
      setError(message(reason, "Không xóa được cuộc trò chuyện."));
      setRemoving(null);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void send(text);
  }

  function onKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(text);
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length) attach(event.dataTransfer.files);
  }

  const threadList = (
    <ul className="chat-threads__list">
      {threads?.map((item) => (
        <li key={item.id}>
          <button
            type="button"
            className="chat-threads__item"
            aria-current={thread?.id === item.id ? "true" : undefined}
            onClick={() => void open(item.id)}
          >
            <span className="chat-threads__title">{item.title}</span>
            {item.updated_at && <span className="chat-threads__time">{formatDateTime(item.updated_at)}</span>}
          </button>
          <button
            type="button"
            className="icon-button chat-threads__remove"
            aria-label={`Xóa cuộc trò chuyện “${item.title}”`}
            onClick={() => setRemoving(item)}
          >
            <Trash2 aria-hidden="true" size={16} strokeWidth={1.8} />
          </button>
        </li>
      ))}
      {threads?.length === 0 && <li className="chat-threads__empty">Chưa có cuộc trò chuyện nào.</li>}
    </ul>
  );

  return (
    <div className="assistant">
      <header className="page__header">
        <h1>AI Assistant</h1>
        <p>Hỏi bằng tiếng Việt: kiểm tra dữ liệu, chạy đối soát, giải thích ca lệch. Mọi thay đổi đều chờ bạn bấm đồng ý.</p>
      </header>

      <div className="assistant__layout" data-threads={collapsed ? "collapsed" : "expanded"}>
        {/* Khi thu gọn, cả cột (kể cả nút "Cuộc trò chuyện mới") ẩn hẳn; visibility trong CSS
            đưa cột ra khỏi thứ tự phím Tab sau khi hiệu ứng đóng chạy xong. */}
        <nav className="chat-threads" id="chat-threads" aria-label="Các cuộc trò chuyện">
          <div className="chat-threads__head">
            <button className="button button--quiet chat-threads__new" type="button" onClick={startNew}>
              <MessageSquarePlus aria-hidden="true" size={17} />
              Cuộc trò chuyện mới
            </button>
          </div>
          <details className="chat-threads__fold">
            <summary>Các cuộc trò chuyện trước ({formatCount(threads?.length ?? 0)})</summary>
            {threadList}
          </details>
          <div className="chat-threads__wide">
            {threadList}
          </div>
        </nav>

        <section
          className="chat"
          data-dragging={dragging || undefined}
          aria-label="Trò chuyện với AI Assistant"
          onDragOver={(event) => {
            if (!event.dataTransfer.types.includes("Files")) return;
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
          }}
          onDrop={onDrop}
        >
          {/* Thanh đầu khung chat (chỉ trên màn hình rộng): nút ẩn/hiện danh sách và tên cuộc
              trò chuyện đang mở. Nút nằm cố định một chỗ dù cột đang mở hay đóng. */}
          <div className="chat__bar">
            <button
              className="icon-button chat__toggle"
              type="button"
              aria-controls="chat-threads"
              aria-expanded={!collapsed}
              aria-label={collapsed ? "Mở danh sách cuộc trò chuyện" : "Thu gọn danh sách cuộc trò chuyện"}
              title={collapsed ? "Mở danh sách cuộc trò chuyện" : "Thu gọn danh sách cuộc trò chuyện"}
              onClick={() => {
                setCollapsed((value) => {
                  store(THREADS_COLLAPSED, value ? "0" : "1");
                  return !value;
                });
              }}
            >
              {collapsed ? (
                <PanelLeftOpen aria-hidden="true" size={18} strokeWidth={1.8} />
              ) : (
                <PanelLeftClose aria-hidden="true" size={18} strokeWidth={1.8} />
              )}
            </button>
            <span className="chat__title">{thread?.title || "Cuộc trò chuyện mới"}</span>
          </div>
          <div className="chat__scroll">
            {!thread || thread.messages.length === 0 ? (
              <div className="chat-empty">
                <h2>Bắt đầu từ dữ liệu của bạn</h2>
                {dataSummary && <p>{dataSummary}</p>}
                <ul className="chat-empty__suggestions" aria-label="Câu hỏi gợi ý">
                  {SUGGESTIONS.map((suggestion) => (
                    <li key={suggestion}>
                      <button type="button" className="button button--quiet" onClick={() => void send(suggestion)}>
                        {suggestion}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <ol className="chat__messages" aria-live="polite">
                {thread.messages.map((item) => (
                  <ChatMessageView key={item.id} message={item} busy={deciding} onDecide={(target, action, decision) => void decide(target, action, decision)} />
                ))}
              </ol>
            )}
            <div ref={endRef} />
          </div>

          {dragging && (
            <div className="chat__drop" aria-hidden="true">
              <Upload size={22} /> Thả tệp CSV hoặc Excel để gửi kèm câu hỏi
            </div>
          )}

          <form className="chat-composer" onSubmit={onSubmit}>
            {error && <p className="notice notice--error" role="alert">{error}</p>}
            {files.length > 0 && (
              <ul className="chat-composer__files" aria-label="Tệp sẽ gửi kèm">
                {files.map((file) => (
                  <li key={file.key} data-state={file.error ? "error" : file.datasetId ? "ready" : "uploading"}>
                    <FileSpreadsheet aria-hidden="true" size={15} />
                    <span className="chat-composer__name">{file.name}</span>
                    <span className="chat-composer__state">
                      {file.error ?? (file.datasetId ? "Đã tải lên" : `${Math.round(file.progress * 100)}%`)}
                    </span>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Bỏ tệp ${file.name}`}
                      onClick={() => setFiles((current) => current.filter((item) => item.key !== file.key))}
                    >
                      <X aria-hidden="true" size={15} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="chat-composer__row">
              <button
                type="button"
                className="icon-button chat-composer__attach"
                aria-label="Đính kèm tệp CSV hoặc Excel"
                title="Đính kèm tệp CSV hoặc Excel"
                onClick={() => fileRef.current?.click()}
              >
                <Paperclip aria-hidden="true" size={19} strokeWidth={1.8} />
              </button>
              <input
                ref={fileRef}
                type="file"
                accept={ACCEPT}
                multiple
                hidden
                onChange={(event) => {
                  if (event.target.files) attach(event.target.files);
                  event.target.value = "";
                }}
              />
              <label className="visually-hidden" htmlFor="chat-input">Câu hỏi cho AI Assistant</label>
              <textarea
                id="chat-input"
                ref={inputRef}
                rows={1}
                value={text}
                maxLength={4000}
                placeholder={thread?.running ? "AI Assistant đang trả lời…" : "Hỏi AI Assistant về dữ liệu, đối soát…"}
                onChange={(event) => setText(event.target.value)}
                onKeyDown={onKey}
              />
              <button className="button button--primary chat-composer__send" type="submit" disabled={!canSend}>
                <SendHorizontal aria-hidden="true" size={17} />
                <span>Gửi</span>
              </button>
            </div>
          </form>
        </section>
      </div>

      <ConfirmDialog
        open={removing !== null}
        title="Xóa cuộc trò chuyện?"
        message="Chỉ xóa nội dung trò chuyện. Dữ liệu, kết quả đối soát và nhật ký kiểm toán vẫn giữ nguyên."
        confirmLabel="Xóa cuộc trò chuyện"
        onConfirm={() => removing && void remove(removing)}
        onCancel={() => setRemoving(null)}
      />
    </div>
  );
}
