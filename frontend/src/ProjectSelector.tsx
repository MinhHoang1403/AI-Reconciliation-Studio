import { useEffect, useId, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FolderOpen,
} from "lucide-react";
import { api } from "./api";
import { Modal, Notice, Spinner } from "./components";
import type { Project, ProjectClassification } from "./types";

const PAGE_SIZE = 20;

/** Search one bounded page at a time. Selection remains independent of search results. */
export function ProjectSelector({
  project,
  onSelect,
  disabled = false,
  canClassify = false,
  onClassificationChange,
}: {
  project: Project | null;
  onSelect: (project: Project) => void;
  disabled?: boolean;
  canClassify?: boolean;
  onClassificationChange?: (project: Project) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<Project[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [active, setActive] = useState(0);
  const [retry, setRetry] = useState(0);
  const [includeTest, setIncludeTest] = useState(false);
  const [classification, setClassification] = useState<ProjectClassification>(
    project?.classification || "UNKNOWN",
  );
  const [saving, setSaving] = useState(false);
  const [classificationError, setClassificationError] = useState("");
  const [classificationSuccess, setClassificationSuccess] = useState("");
  const projectRef = useRef(project);
  const alive = useRef(true);
  projectRef.current = project;
  const listId = useId();
  const searchRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const queryRef = useRef("");
  const sequence = useRef(0);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const request = ++sequence.current;
    const timer = setTimeout(
      () => {
        const params = new URLSearchParams({
          search: query,
          offset: String(offset),
          limit: String(PAGE_SIZE),
          include_test: String(includeTest),
        });
        void api<{ items: Project[]; total: number }>(`/projects?${params}`, {
          signal: controller.signal,
        })
          .then((result) => {
            if (controller.signal.aborted || request !== sequence.current)
              return;
            setItems(result.items);
            setTotal(result.total);
            setActive(0);
            setLoading(false);
          })
          .catch((err) => {
            if (controller.signal.aborted || request !== sequence.current)
              return;
            setError(
              err instanceof Error
                ? err.message
                : "Không tải được danh sách dự án.",
            );
            setLoading(false);
          });
      },
      query ? 250 : 0,
    );
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [open, query, offset, retry, includeTest]);

  useEffect(() => {
    setClassification(project?.classification || "UNKNOWN");
  }, [project?.classification]);
  useEffect(() => {
    setClassificationError("");
    setClassificationSuccess("");
    setClassification(projectRef.current?.classification || "UNKNOWN");
  }, [project?.id]);

  useEffect(() => {
    document
      .getElementById(`${listId}-${active}`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active, listId]);

  function invalidate() {
    sequence.current += 1;
    setItems([]);
    setLoading(true);
    setError("");
  }
  function select(item: Project) {
    onSelect(item);
    setOpen(false);
  }
  async function saveClassification() {
    if (!project || !canClassify || saving) return;
    const id = project.id;
    setSaving(true);
    setClassificationError("");
    setClassificationSuccess("");
    try {
      const updated = await api<Project>(`/projects/${id}/classification`, {
        method: "PATCH",
        body: JSON.stringify({
          classification,
          expected_classification: project.classification || "UNKNOWN",
        }),
      });
      // The parent guards its current ID. Retain a confirmed metadata change
      // even if the selector was closed/unmounted while the write completed.
      onClassificationChange?.(updated);
      if (!alive.current || projectRef.current?.id !== id) return;
      invalidate();
      setOffset(0);
      setRetry((n) => n + 1);
      setClassificationSuccess(
        "Đã lưu phân loại. Dữ liệu và lịch sử vẫn được giữ nguyên.",
      );
    } catch (err) {
      if (!alive.current || projectRef.current?.id !== id) return;
      const message =
        err instanceof Error ? err.message : "Không lưu được phân loại.";
      // Refresh metadata without switching project/resetting drafts or retrying writes.
      try {
        const current = await api<Project>(`/projects/${id}`);
        if (alive.current && projectRef.current?.id === id)
          onClassificationChange?.(current);
      } catch {
        /* Preserve the selection and original write error. */
      }
      if (alive.current && projectRef.current?.id === id)
        setClassificationError(message);
    } finally {
      if (alive.current) setSaving(false);
    }
  }
  return (
    <>
      <button
        ref={triggerRef}
        id="project-select"
        className="project-trigger"
        disabled={disabled}
        data-project-id={project?.id || ""}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`Dự án: ${project?.name || "Chọn dự án"}`}
        onClick={() => {
          invalidate();
          setOpen(true);
        }}
      >
        <FolderOpen size={17} />
        <span>
          <strong>{project?.name || "Chọn dự án"}</strong>
          <small>
            {project?.business_scope || "Tìm theo tên hoặc phạm vi nghiệp vụ"}
          </small>
        </span>
        {project?.classification === "TEST" && (
          <span className="project-test-badge">TEST</span>
        )}
        <ChevronDown size={16} />
      </button>
      <Modal
        title="Chọn dự án"
        open={open}
        onOpenChange={setOpen}
        returnFocus={triggerRef}
      >
        <label className="project-search-label" htmlFor={`${listId}-search`}>
          Tìm dự án theo tên hoặc phạm vi
        </label>
        <input
          id={`${listId}-search`}
          ref={searchRef}
          autoFocus
          role="combobox"
          aria-label="Tìm dự án"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={
            !loading && items[active] ? `${listId}-${active}` : undefined
          }
          value={query}
          maxLength={200}
          placeholder="Ví dụ: Đơn hàng, miền Nam…"
          onChange={(e) => {
            queryRef.current = e.target.value;
            invalidate();
            setQuery(e.target.value);
            setOffset(0);
          }}
          onKeyDown={(e) => {
            if (loading || queryRef.current !== query) return;
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              setActive((old) =>
                Math.max(
                  0,
                  Math.min(
                    items.length - 1,
                    old + (e.key === "ArrowDown" ? 1 : -1),
                  ),
                ),
              );
            } else if (e.key === "Enter" && items[active]) {
              e.preventDefault();
              select(items[active]);
            } else if (e.key === "Home") {
              e.preventDefault();
              setActive(0);
            } else if (e.key === "End") {
              e.preventDefault();
              setActive(Math.max(0, items.length - 1));
            }
          }}
        />
        <label className="check-label project-test-filter">
          <input
            type="checkbox"
            checked={includeTest}
            onChange={(event) => {
              invalidate();
              setOffset(0);
              setIncludeTest(event.target.checked);
            }}
          />
          Hiển thị dự án kiểm thử
        </label>
        {loading && (
          <div role="status">
            <Spinner />
          </div>
        )}
        {error && (
          <Notice tone="error">
            {error}{" "}
            <button
              className="text-button"
              onClick={() => {
                invalidate();
                setRetry((n) => n + 1);
              }}
            >
              Thử lại
            </button>
          </Notice>
        )}
        <div
          id={listId}
          role="listbox"
          aria-label="Danh sách dự án"
          aria-busy={loading}
          className="project-options"
        >
          {!loading &&
            !error &&
            items.map((item, index) => (
              <div
                key={item.id}
                id={`${listId}-${index}`}
                role="option"
                aria-selected={project?.id === item.id}
                tabIndex={-1}
                className={`project-option ${active === index ? "highlighted" : ""}`}
                onMouseMove={() => setActive(index)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => select(item)}
              >
                <strong>{item.name}</strong>
                <span>{item.business_scope}</span>
                <small>Mã {item.id.slice(0, 8)}</small>
                {item.classification === "TEST" && (
                  <span className="project-test-badge">Kiểm thử</span>
                )}
              </div>
            ))}
        </div>
        {!loading && !error && (
          <>
            <p className="subtle" role="status">
              {items.length
                ? `${offset + 1}–${offset + items.length} / ${total} dự án`
                : "Không có dự án phù hợp. Thử tên, phạm vi khác hoặc bật hiển thị dự án kiểm thử."}
            </p>
            <div className="pagination">
              <span>Dùng ↑ ↓ và Enter để chọn · Esc để đóng</span>
              <div>
                <button
                  className="icon-button"
                  aria-label="Trang dự án trước"
                  disabled={offset === 0}
                  onClick={() => {
                    invalidate();
                    setOffset(Math.max(0, offset - PAGE_SIZE));
                    searchRef.current?.focus();
                  }}
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  className="icon-button"
                  aria-label="Trang dự án sau"
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => {
                    invalidate();
                    setOffset(offset + PAGE_SIZE);
                    searchRef.current?.focus();
                  }}
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
          </>
        )}
        {project && canClassify && (
          <details className="project-classification">
            <summary>Phân loại dự án hiện tại</summary>
            <p>
              <strong>{project.name}</strong> · {project.business_scope}
            </p>
            <p className="subtle">Mã dự án: {project.id}</p>
            <label>
              Nhóm dự án
              <select
                aria-label="Nhóm dự án"
                value={classification}
                disabled={saving}
                onChange={(event) =>
                  setClassification(event.target.value as ProjectClassification)
                }
              >
                <option value="WORK">Đang làm việc</option>
                <option value="TEST">Kiểm thử</option>
                <option value="UNKNOWN">Chưa phân loại</option>
              </select>
            </label>
            <p className="subtle">
              Xác nhận chỉ đổi nhóm hiển thị, không xóa dữ liệu hoặc đổi quyền
              truy cập.
            </p>
            <button
              className="button secondary"
              disabled={
                saving ||
                classification === (project.classification || "UNKNOWN")
              }
              onClick={() => void saveClassification()}
            >
              {saving ? "Đang lưu…" : "Xác nhận phân loại"}
            </button>
          </details>
        )}
        {classificationError && (
          <Notice tone="error">{classificationError}</Notice>
        )}
        {classificationSuccess && (
          <Notice tone="success">{classificationSuccess}</Notice>
        )}
      </Modal>
    </>
  );
}
