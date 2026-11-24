import { Fragment, type ReactNode } from "react";
import { AlertCircle, ArrowRight, Check, CircleSlash, FileSpreadsheet, X } from "lucide-react";

import type { ChatAction, ChatMessage, ChatStep } from "../api";
import { linkTo } from "../navigation";

// Một tin nhắn trong khung chat. Câu của người dùng là khối xanh nhạt bên phải; câu trả lời
// của Assistant chiếm cả chiều ngang, gồm: các bước đã làm (bước đang chạy màu tím tờ
// 50.000đ, xong màu xanh lá), lời trả lời, thẻ xác nhận cho thao tác thay đổi, nút dẫn trang.

type Props = {
  message: ChatMessage;
  busy: boolean;
  onDecide: (message: ChatMessage, action: ChatAction, decision: "CONFIRM" | "CANCEL") => void;
};

/** Đậm **…**, nghiêng *…*, mã `…` trong một dòng (React tự thoát ký tự, không chèn HTML). */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`)/g).map((part, index) => {
    if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.length > 2 && part.startsWith("*") && part.endsWith("*")) {
      return <em key={index}>{part.slice(1, -1)}</em>;
    }
    if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

/** Đoạn văn và danh sách gạch đầu dòng / đánh số từ câu trả lời dạng markdown đơn giản. */
export function RichText({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const items = list.items.map((item, index) => <li key={index}>{inline(item)}</li>);
    blocks.push(list.ordered ? <ol key={blocks.length}>{items}</ol> : <ul key={blocks.length}>{items}</ul>);
    list = null;
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const bullet = /^[-*•]\s+(.*)$/.exec(line);
    const numbered = /^\d+[.)]\s+(.*)$/.exec(line);
    if (bullet?.[1] !== undefined || numbered?.[1] !== undefined) {
      const ordered = Boolean(numbered);
      if (list && list.ordered !== ordered) flush();
      list ??= { ordered, items: [] };
      list.items.push((bullet?.[1] ?? numbered?.[1]) as string);
      continue;
    }
    flush();
    if (line) blocks.push(<p key={blocks.length}>{inline(line.replace(/^#+\s*/, ""))}</p>);
  }
  flush();
  return <div className="chat-text">{blocks}</div>;
}

function Steps({ steps }: { steps: ChatStep[] }) {
  return (
    <ol className="chat-steps" aria-label="Các bước AI Assistant đã làm">
      {steps.map((step, index) => (
        <li key={index} data-status={step.status}>
          {step.status === "RUNNING" ? (
            <span className="chat-steps__pulse" aria-hidden="true" />
          ) : step.status === "DONE" ? (
            <Check aria-hidden="true" size={15} strokeWidth={2.2} />
          ) : (
            <X aria-hidden="true" size={15} strokeWidth={2.2} />
          )}
          <span>
            {step.label}
            {step.status === "RUNNING" && "…"}
            {step.status === "FAILED" && <span className="visually-hidden"> (lỗi)</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}

const CARD_STATUS: Record<Exclude<ChatAction["status"], "PENDING">, string> = {
  DONE: "Đã thực hiện",
  CANCELLED: "Đã bỏ qua",
  FAILED: "Không thực hiện được",
};

function ActionCard({ action, onDecide, busy }: { action: ChatAction; busy: boolean; onDecide: (decision: "CONFIRM" | "CANCEL") => void }) {
  return (
    <section className="chat-card" data-status={action.status} aria-label={`Thẻ xác nhận: ${action.title}`}>
      <h3>{action.title}</h3>
      <p>{action.detail}</p>
      {action.status === "PENDING" ? (
        <div className="chat-card__actions">
          <button className="button button--primary" type="button" disabled={busy} onClick={() => onDecide("CONFIRM")}>
            <Check aria-hidden="true" size={16} /> Đồng ý
          </button>
          <button className="button button--quiet" type="button" disabled={busy} onClick={() => onDecide("CANCEL")}>
            Bỏ qua
          </button>
        </div>
      ) : (
        <p className="chat-card__outcome">
          {action.status === "DONE" ? (
            <Check aria-hidden="true" size={15} />
          ) : action.status === "CANCELLED" ? (
            <CircleSlash aria-hidden="true" size={15} />
          ) : (
            <AlertCircle aria-hidden="true" size={15} />
          )}
          {CARD_STATUS[action.status]}
          {action.result && `: ${action.result}`}
        </p>
      )}
    </section>
  );
}

export function ChatMessageView({ message, busy, onDecide }: Props) {
  if (message.role === "user") {
    return (
      <li className="chat-message" data-role="user">
        <div className="chat-message__bubble">
          {message.attachments.length > 0 && (
            <ul className="chat-files" aria-label="Tệp đính kèm">
              {message.attachments.map((file) => (
                <li key={file.dataset_id}>
                  <FileSpreadsheet aria-hidden="true" size={15} /> {file.name}
                </li>
              ))}
            </ul>
          )}
          <p>{message.text}</p>
        </div>
      </li>
    );
  }
  const thinking = message.status === "RUNNING" && !message.steps.some((step) => step.status === "RUNNING");
  return (
    <li className="chat-message" data-role="assistant" data-status={message.status} aria-busy={message.status === "RUNNING"}>
      <span className="chat-message__who">AI Assistant</span>
      {message.steps.length > 0 && <Steps steps={message.steps} />}
      {thinking && (
        <p className="chat-message__thinking">
          <span className="chat-steps__pulse" aria-hidden="true" /> Đang suy nghĩ…
        </p>
      )}
      {message.text &&
        (message.status === "FAILED" ? (
          <p className="chat-message__error">
            <AlertCircle aria-hidden="true" size={16} /> {message.text}
          </p>
        ) : (
          <RichText text={message.text} />
        ))}
      {message.actions.map((action) => (
        <ActionCard key={action.id} action={action} busy={busy} onDecide={(decision) => onDecide(message, action, decision)} />
      ))}
      {message.links.length > 0 && message.status !== "RUNNING" && (
        <div className="chat-links">
          {message.links.map((link) => (
            <a key={link.path + link.label} className="button button--quiet" {...linkTo(link.path)}>
              {link.label} <ArrowRight aria-hidden="true" size={15} />
            </a>
          ))}
        </div>
      )}
    </li>
  );
}
