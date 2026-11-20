import { useId, useRef, useState } from "react";
import { CircleAlert, CircleCheck, FileUp, Info } from "lucide-react";

import { uploadDataset, type DatasetSummary } from "../api";

// Vùng tải tệp: kéo-thả hoặc bấm chọn; nhiều tệp được tải lần lượt, mỗi tệp có tiến độ riêng.

type Item = {
  key: string;
  name: string;
  progress: number;
  outcome?: { kind: "done" | "duplicate" | "error"; message: string };
};

type Props = { onUploaded: (dataset: DatasetSummary) => void };

const ACCEPT = ".csv,.xlsx";

export function UploadZone({ onUploaded }: Props) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [items, setItems] = useState<Item[]>([]);

  const update = (key: string, change: Partial<Item>) =>
    setItems((current) => current.map((item) => (item.key === key ? { ...item, ...change } : item)));

  async function uploadAll(files: FileList | File[]) {
    const queue = Array.from(files).map((file, index) => ({
      file,
      item: { key: `${Date.now()}-${index}-${file.name}`, name: file.name, progress: 0 },
    }));
    setItems((current) => [...queue.map(({ item }) => item), ...current].slice(0, 8));
    for (const { file, item } of queue) {
      try {
        const reply = await uploadDataset(file, (share) => update(item.key, { progress: share }));
        update(item.key, {
          progress: 1,
          outcome: reply.duplicate
            ? { kind: "duplicate", message: `Tệp này đã có, đang dùng lại bộ “${reply.dataset.name}”.` }
            : { kind: "done", message: "Đã tải lên, đang đọc dữ liệu." },
        });
        onUploaded(reply.dataset);
      } catch (error) {
        update(item.key, {
          outcome: { kind: "error", message: error instanceof Error ? error.message : "Tải lên thất bại." },
        });
      }
    }
  }

  return (
    <section className="upload" aria-labelledby={`${inputId}-title`}>
      <div
        className="upload__zone"
        data-dragging={dragging || undefined}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (event.dataTransfer.files.length) void uploadAll(event.dataTransfer.files);
        }}
      >
        <FileUp aria-hidden="true" size={28} strokeWidth={1.6} />
        <div>
          <h2 id={`${inputId}-title`}>Tải tệp dữ liệu</h2>
          <p>Kéo thả tệp vào đây hoặc chọn từ máy. CSV (UTF-8) hoặc Excel .xlsx, tối đa 50 MB mỗi tệp.</p>
        </div>
        <label className="button button--primary" htmlFor={inputId}>
          Chọn tệp
        </label>
        <input
          ref={inputRef}
          id={inputId}
          className="visually-hidden"
          type="file"
          accept={ACCEPT}
          multiple
          onChange={(event) => {
            if (event.target.files?.length) void uploadAll(event.target.files);
            event.target.value = "";
          }}
        />
      </div>
      {items.length > 0 && (
        <ul className="upload__list" aria-live="polite">
          {items.map((item) => (
            <li key={item.key} data-outcome={item.outcome?.kind}>
              {item.outcome?.kind === "error" ? (
                <CircleAlert aria-hidden="true" size={18} />
              ) : item.outcome?.kind === "duplicate" ? (
                <Info aria-hidden="true" size={18} />
              ) : (
                <CircleCheck aria-hidden="true" size={18} />
              )}
              <span className="upload__name">{item.name}</span>
              <span className="upload__message">
                {item.outcome?.message ?? `Đang tải lên ${Math.round(item.progress * 100)}%`}
              </span>
              {!item.outcome && (
                <progress max={1} value={item.progress} aria-label={`Tiến độ tải ${item.name}`} />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
