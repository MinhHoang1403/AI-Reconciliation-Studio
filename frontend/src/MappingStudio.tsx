import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, Eye, Sparkles } from "lucide-react";
import { api, ApiError } from "./api";
import { ReviewCard } from "./ReviewCard";
import type { Workflow } from "./agentTypes";
import { Badge, Modal, Notice, Spinner } from "./components";
import type {
  DataType,
  Decision,
  Job,
  Mapping,
  Profile,
  Schema,
  SchemaField,
  Table,
} from "./types";
import { errorText, warningText, statusText } from "./types";

interface Draft {
  source: string;
  target: string;
  label: string;
  type: DataType;
  required: boolean;
  locale: string;
  metric: string;
  basis: string;
  currency: string;
  unit: string;
  dateFormat: string;
  timezone: string;
  trim: boolean;
  key: boolean;
}

const typeLabels: Record<DataType, string> = {
  string: "Văn bản hoặc mã",
  decimal: "Số tiền chính xác",
  date: "Ngày và thời gian",
  enum: "Danh mục",
};
const keepSourceLabel = "Giữ nguyên trong nguồn gốc";
const fold = (value: string) => value.toLocaleLowerCase("vi").normalize("NFD")
  .replace(/\p{M}/gu, "").replace(/đ/g, "d");

function MappingTargetPicker({ column, draft, fields, occupied, suggestion, readOnly, onSelect }: {
  column: string;
  draft: Draft;
  fields: SchemaField[];
  occupied: Map<string, string>;
  suggestion?: string | null;
  readOnly: boolean;
  onSelect: (field: SchemaField | null) => void;
}) {
  const trigger = useRef<HTMLButtonElement>(null);
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const term = fold(query.trim()).replaceAll("_", " ");
  const options = [null, ...fields].filter(field => fold(field
    ? `${field.name} ${field.id} ${typeLabels[field.data_type]}`
    : keepSourceLabel).replaceAll("_", " ").includes(term));
  const assignedTo = (id: string) => id === draft.target ? undefined : occupied.get(id);
  const enabled = options.filter(field => !field || !assignedTo(field.id));
  const highlighted = enabled[active];
  const customId = fold(query.trim()).replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  const canAdd = /^[a-z][a-z0-9_]{0,63}$/.test(customId) &&
    query.trim().length <= 120 && !fields.some(field =>
      field.id === customId || fold(field.name).replaceAll("_", " ") === term);
  function choose(field: SchemaField | null) {
    onSelect(field);
    setOpen(false);
  }
  useEffect(() => {
    if (open && highlighted !== undefined)
      document.getElementById(`${listId}-${highlighted?.id || "source"}`)
        ?.scrollIntoView({ block: "nearest" });
  }, [highlighted, listId, open]);
  return <div>
    <span className="mapping-target-label">Trường đích</span>
    <button type="button" ref={trigger} className="mapping-target-trigger"
      aria-label={`Trường đích ${column}`} aria-haspopup="dialog" aria-expanded={open}
      disabled={readOnly} onClick={() => { setQuery(""); setActive(0); setOpen(true); }}>
      <span>{draft.target ? draft.label : keepSourceLabel}</span><ChevronDown size={15} aria-hidden="true" />
    </button>
    <Modal title={`Chọn trường cho ${column}`} open={open} onOpenChange={setOpen} returnFocus={trigger}>
      <input autoFocus role="combobox" aria-label="Tìm trường đích" aria-expanded={open}
        aria-controls={listId} aria-autocomplete="list"
        aria-activedescendant={highlighted !== undefined ? `${listId}-${highlighted?.id || "source"}` : undefined}
        maxLength={120} value={query} placeholder="Tìm theo tên, ví dụ: Mã tham chiếu"
        onChange={event => { setQuery(event.target.value); setActive(0); }}
        onKeyDown={event => {
          if (event.nativeEvent.isComposing) return;
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setActive(index => Math.max(0, Math.min(enabled.length - 1, index + (event.key === "ArrowDown" ? 1 : -1))));
          } else if (event.key === "Enter" && highlighted !== undefined) {
            event.preventDefault();
            choose(highlighted);
          }
        }} />
      <div id={listId} role="listbox" aria-label="Trường đích hợp lệ" className="project-options">
        {options.map(field => {
          const id = field?.id || "";
          const takenBy = assignedTo(id);
          return <div key={id} id={`${listId}-${id || "source"}`} role="option"
            data-target-id={id}
            aria-selected={draft.target === id} aria-disabled={Boolean(takenBy)}
            className={`project-option${highlighted === field ? " highlighted" : ""}`}
            onMouseDown={event => event.preventDefault()} onClick={() => { if (!takenBy) choose(field); }}>
            <strong>{field?.name || keepSourceLabel}</strong>
            <span>{takenBy ? `Đã gán cho cột ${takenBy}` : field ? typeLabels[field.data_type] : "Cột vẫn xem được trong dữ liệu gốc."}
              {id && id === suggestion && !takenBy ? " · AI đề xuất" : ""}</span>
          </div>;
        })}
      </div>
      {!options.length && <p role="status">Không tìm thấy trường trong cấu trúc hiện tại.</p>}
      {canAdd && <button type="button" className="button secondary mapping-add-field" onClick={() => choose({
        id: customId, name: query.trim(), data_type: "string", required: false,
        semantic_metric: null, amount_basis: null, currency: null, unit: null,
      })}>Thêm trường “{query.trim()}” vào cấu trúc</button>}
    </Modal>
  </div>;
}

function makeDraft(mapping: Mapping, profile: Profile): Draft[] {
  const decisions = mapping.decision?.decisions || mapping.proposal.decisions;
  const configured = ["APPROVED", "SUPERSEDED"].includes(mapping.status) ||
    Boolean(mapping.template_mapping_id);
  return profile.columns.map((col) => {
    const d = decisions.find((d) => d.source_field === col.column_id);
    const field = mapping.schema.fields.find(
      (f) => f.id === d?.candidate_target,
    );
    return {
      source: col.column_id,
      target: d?.candidate_target || "",
      label: field?.name || col.name,
      type: field?.data_type || "string",
      required: field?.required || false,
      locale: configured ? String(d?.transformation_candidate.locale || "") : "",
      metric: field?.semantic_metric || "",
      basis: field?.amount_basis || "",
      currency: field?.currency || "",
      unit: field?.unit || "",
      dateFormat: configured
        ? String(d?.transformation_candidate.format || "")
        : "",
      timezone: configured
        ? String(d?.transformation_candidate.timezone || "")
        : "",
      trim: configured && d?.transformation_candidate.op === "trim_if_approved",
      key: mapping.schema.business_key_fields.includes(
        d?.candidate_target || "",
      ),
    };
  });
}

function mappingFacts(mapping: Mapping) {
  const entity = mapping.schema.entity_kind === "unknown" ? mapping.proposal.entity_kind : mapping.schema.entity_kind;
  const grain = mapping.schema.grain === "unknown" ? mapping.proposal.grain : mapping.schema.grain;
  return {
    entity: ["unknown", "ambiguous"].includes(entity.toLowerCase()) ? "" : entity,
    grain: ["unknown", "ambiguous"].includes(grain.toLowerCase()) ? "" : grain,
  };
}

function ManualMappingStudio({
  table,
  profile,
  mappings,
  latestJob,
  busy,
  readOnly = false,
  run,
  onReload,
  onProposalAvailable,
  onApproved,
  onEvidence,
  draftOwner,
  canManageReuse = false,
}: {
  table: Table;
  profile: Profile;
  mappings: Mapping[];
  latestJob: Job | null;
  busy: boolean;
  readOnly?: boolean;
  run: (task: () => Promise<void>) => Promise<void>;
  onReload: () => Promise<void>;
  onProposalAvailable: (message: string) => void;
  onApproved: () => Promise<void>;
  onEvidence: (id: string) => void;
  draftOwner: string;
  canManageReuse?: boolean;
}) {
  const selectionKey = `studio.manual-mapping-selection.${draftOwner}.${table.id}`;
  const [selected, setSelected] = useState(() => {
    try { return sessionStorage.getItem(selectionKey) || ""; }
    catch { return ""; }
  });
  const mapping = mappings.find((m) => m.id === selected) || mappings[0];
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [entity, setEntity] = useState("");
  const [grain, setGrain] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const initialized = useRef("");
  const pendingApproval = useRef<{body: string; key: string} | null>(null);
  const approving = useRef(false);
  const [loadedKey, setLoadedKey] = useState("");
  const [submittedJobId, setSubmittedJobId] = useState("");
  const [finishedJob, setFinishedJob] = useState<Job | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [proposalError, setProposalError] = useState("");
  const [watchError, setWatchError] = useState(false);
  const [retryWatch, setRetryWatch] = useState(0);
  const [offeredRevision, setOfferedRevision] = useState("");
  const acceptedRevision = useRef("");
  const submitKey = useRef("");
  const storageKey = `studio.manual-mapping.${draftOwner}.${table.id}.${mapping?.id || "none"}`;
  const jobId = submittedJobId || latestJob?.id || "";
  const currentJob = finishedJob?.id === jobId
    ? finishedJob : !submittedJobId && latestJob?.id === jobId ? latestJob : null;
  const activeJob = !currentJob || ["QUEUED", "RUNNING", "RETRYABLE_FAILURE"].includes(currentJob.status)
    ? jobId : "";
  const jobError = currentJob && ["BLOCKED", "FAILED", "CANCELLED"].includes(currentJob.status)
    ? errorText[currentJob.error_code || ""] || "Kiểm tra nguồn và thử lại, hoặc tiếp tục xác nhận thủ công."
    : "";
  useEffect(() => {
    if (mapping) {
      // Mapping revisions and parsed tables are immutable. A refreshed DTO for the
      // same revision must not erase edits or source-review acknowledgement.
      const identity = storageKey;
      if (initialized.current === identity) return;
      initialized.current = identity;
      pendingApproval.current = null;
      let saved: {drafts: Draft[]; entity: string; grain: string; reviewed: boolean} | null = null;
      try {
        const value = JSON.parse(sessionStorage.getItem(storageKey) || "null");
        if (value && Array.isArray(value.drafts) && value.drafts.length === profile.columns.length &&
            value.drafts.every((d: Draft, i: number) => d?.source === profile.columns[i].column_id) &&
            typeof value.entity === "string" && typeof value.grain === "string") saved = value;
      } catch { /* Use the immutable proposal if the tab cache is unavailable. */ }
      setDrafts(saved?.drafts || makeDraft(mapping, profile));
      const facts = mappingFacts(mapping);
      setEntity(saved ? saved.entity : facts.entity);
      setGrain(saved ? saved.grain : facts.grain);
      setReviewed(saved?.reviewed || false);
      setLoadedKey(storageKey);
    }
  }, [mapping?.id, profile, table.id, storageKey]);
  useEffect(() => {
    if (loadedKey !== storageKey) return;
    try { sessionStorage.setItem(storageKey, JSON.stringify({drafts, entity, grain, reviewed})); }
    catch { /* Manual edits remain in memory if browser storage is unavailable. */ }
  }, [loadedKey, storageKey, drafts, entity, grain, reviewed]);

  useEffect(() => {
    if (!activeJob) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const job = await api<Job>(`/jobs/${activeJob}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (["QUEUED", "RUNNING", "RETRYABLE_FAILURE"].includes(job.status)) {
          timer = setTimeout(() => void poll(), 800);
          return;
        }
        if (job.status === "SUCCEEDED") await onReload();
        if (!controller.signal.aborted) {
          setFinishedJob(job);
          setWatchError(false);
        }
      } catch {
        if (!controller.signal.aborted) setWatchError(true);
      }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [activeJob, onReload, retryWatch]);

  function chooseRevision(id: string) {
    setSelected(id);
    try { sessionStorage.setItem(selectionKey, id); } catch { /* Optional tab preference. */ }
  }
  const baseline = mapping ? mappingFacts(mapping) : null;
  const dirty = mapping && loadedKey === storageKey && (
    reviewed || entity !== baseline?.entity || grain !== baseline?.grain ||
    JSON.stringify(drafts) !== JSON.stringify(makeDraft(mapping, profile))
  );
  const publishedJob = currentJob;
  const published = publishedJob?.status === "SUCCEEDED" &&
    mappings.find(item => item.id === publishedJob.result?.mapping_id);
  useEffect(() => {
    if (!mapping || !published || loadedKey !== storageKey || acceptedRevision.current === published.id) return;
    if (published.revision < mapping.revision) return;
    acceptedRevision.current = published.id;
    if (published.id !== mapping.id && dirty) {
      setOfferedRevision(published.id);
      return;
    }
    setSelected(published.id);
    try { sessionStorage.setItem(selectionKey, published.id); } catch { /* Optional tab preference. */ }
    if (finishedJob && published.proposal.decisions.some(decision => decision.candidate_target))
      onProposalAvailable("Đã có đề xuất mới.");
  }, [published, mapping, dirty, loadedKey, storageKey, selectionKey, finishedJob, onProposalAvailable]);

  async function requestProposal() {
    if (submitting || activeJob) return;
    setSubmitting(true);
    setProposalError("");
    setWatchError(false);
    submitKey.current ||= crypto.randomUUID();
    try {
      const job = await api<{job_id: string}>(`/tables/${table.id}/mapping-proposals`, {
        method: "POST", headers: {"Idempotency-Key": submitKey.current},
        signal: AbortSignal.timeout(30000),
      });
      submitKey.current = "";
      setFinishedJob(null);
      setSubmittedJobId(job.job_id);
    } catch (error) {
      if (error instanceof ApiError && !["API_TIMEOUT", "NETWORK_ERROR"].includes(error.code))
        submitKey.current = "";
      setProposalError("Chưa nhận được trạng thái yêu cầu. Bạn có thể thử lại hoặc chỉnh ánh xạ hiện tại.");
    } finally { setSubmitting(false); }
  }

  function change(source: string, patch: Partial<Draft>) {
    if (mapping) chooseRevision(mapping.id);
    setDrafts((rows) =>
      rows.map((r) => (r.source === source ? { ...r, ...patch } : r)),
    );
  }
  function approvalBody() {
    if (!mapping) return null;
    const used = drafts.filter((d) => d.target);
    const fields: SchemaField[] = used.map((d) => ({
      id: d.target,
      name: d.label,
      data_type: d.type,
      required: d.required,
      semantic_metric: d.metric || null,
      amount_basis: d.basis || null,
      currency: d.currency || null,
      unit: d.unit || null,
    }));
    const schema: Schema = {
      ...mapping.schema,
      name: "Cấu trúc đã xác nhận",
      revision: mapping.schema.revision + 1,
      entity_kind: entity,
      grain,
      fields,
      business_key_fields: used.filter((d) => d.key).map((d) => d.target),
    };
    const decisions: Decision[] = used.map((d) => ({
      source_field: d.source,
      candidate_target: d.target,
      decision: "APPROVED",
      evidence_ids: [`${table.id}:${d.source}`],
      grain_assumption: grain,
      transformation_candidate:
        d.type === "decimal"
          ? { op: "parse_decimal", locale: d.locale }
          : d.type === "date"
            ? { op: "parse_date", format: d.dateFormat, timezone: d.timezone }
            : d.trim
              ? { op: "trim_if_approved", approved: true }
              : { op: "cast_string_preserve" },
      reasoning: "Người dùng xác nhận sau khi xem nguồn.",
      unresolved_questions: [],
    }));
    return {schema_definition:schema,decisions,extraction_reviewed:reviewed};
  }
  async function approve() {
    if(approving.current||!mapping||!preflight||preflightSignature!==bodySignature)return;
    const receiptKey = `${storageKey}.approval`;
    const body = JSON.stringify(approvalBody());
    let request = pendingApproval.current;
    if (!request) try { request = JSON.parse(sessionStorage.getItem(receiptKey) || "null"); } catch { /* optional */ }
    if (request && request.body !== body) throw new Error("Lần duyệt trước chưa rõ kết quả. Hãy cập nhật dữ liệu và kiểm tra bản đã duyệt trước khi đổi nội dung.");
    request ||= {body, key: crypto.randomUUID()};
    pendingApproval.current = request;
    approving.current = true;
    try { sessionStorage.setItem(receiptKey, JSON.stringify(request)); } catch { /* same mounted form below still has its key */ }
    try {
      await api(`/mappings/${mapping.id}/approve`, {method:'POST',body,headers:{"Idempotency-Key":request.key}});
      pendingApproval.current = null;
      try { sessionStorage.removeItem(receiptKey);sessionStorage.removeItem(storageKey); } catch { /* server receipt remains durable */ }
      setSelected("");
      try { sessionStorage.removeItem(selectionKey); } catch { /* Optional tab preference. */ }
      await onApproved();
    } catch (err) {
      if (err instanceof ApiError && !["NETWORK_ERROR", "API_TIMEOUT"].includes(err.code)) {
        pendingApproval.current = null;
        try { sessionStorage.removeItem(receiptKey); } catch { /* optional cache */ }
      }
      throw err;
    } finally { approving.current = false; }
  }
  const invalid =
    loadedKey !== storageKey ||
    !entity.trim() ||
    !grain.trim() ||
    !drafts.some((d) => d.target) ||
    drafts.some(
      (d) =>
        d.target &&
        ((d.type === "decimal" &&
          (!d.locale || !d.metric || !d.basis || !d.currency || !d.unit)) ||
          (d.type === "date" && (!d.dateFormat || !d.timezone))),
    ) ||
    (table.parsed.warnings.length > 0 && !reviewed);
  const [preflight,setPreflight]=useState<{source_rows:number;predicted_invalid_rows:number;error_counts:Record<string,number>}|null>(null);
  const [preflightError,setPreflightError]=useState('');
  const [preflightSignature,setPreflightSignature]=useState('');
  const bodySignature=JSON.stringify(approvalBody());
  useEffect(()=>{
    setPreflight(null);setPreflightError('');
    if(invalid)return;
    const controller=new AbortController();
    const timer=setTimeout(()=>{void api<{source_rows:number;predicted_invalid_rows:number;error_counts:Record<string,number>}>(`/tables/${table.id}/mapping-preflight`,{method:'POST',body:bodySignature,signal:controller.signal})
    .then(result=>{if(!controller.signal.aborted){setPreflight(result);setPreflightSignature(bodySignature);}})
    .catch(err=>{if(!controller.signal.aborted)setPreflightError(err instanceof Error?err.message:'Không kiểm tra được đề xuất.');});},400);
    return()=>{clearTimeout(timer);controller.abort();};
  },[bodySignature,invalid,table.id]);
  if (!mapping)
    return (
      <Notice>
        Ánh xạ thủ công sẽ xuất hiện sau khi phân tích bảng hoàn tất.
      </Notice>
    );
  const fields = new Map(mapping.schema.fields.map(field => [field.id, field]));
  const columnsById = new Map(profile.columns.map(column => [column.column_id, column]));
  const occupied = new Map(drafts.filter(draft => draft.target)
    .map(draft => [draft.target, columnsById.get(draft.source)?.name || draft.source]));
  for (const draft of drafts) {
    if (draft.target && !fields.has(draft.target)) fields.set(draft.target, {
      id: draft.target, name: draft.label, data_type: draft.type, required: draft.required,
      semantic_metric: draft.metric || null, amount_basis: draft.basis || null,
      currency: draft.currency || null, unit: draft.unit || null,
    });
  }
  const aiSuggested = ["GEMINI", "QWEN"].includes(mapping.proposal_source || "");
  const needsReview = ["PROPOSED", "AMBIGUOUS"].includes(mapping.status);
  return (
    <div className="mapping-studio">
      <div className="section-heading">
        <div>
          <h2>Hiểu dữ liệu, xác nhận ý nghĩa</h2>
          <p>
            Kiểm tra loại dữ liệu, ý nghĩa từng dòng và các cột trước khi duyệt.
          </p>
        </div>
        <button
          className="button secondary"
          disabled={busy || readOnly || submitting || Boolean(activeJob)}
          onClick={() => void requestProposal()}
        >
          <Sparkles size={17} /> Đề xuất lại
        </button>
      </div>
      {(activeJob || submitting) && !watchError && <Notice>Đang phân tích dữ liệu…</Notice>}
      {proposalError && <Notice tone="error">{proposalError}</Notice>}
      {watchError && <Notice tone="error">Chưa cập nhật được trạng thái đề xuất.{" "}
        <button type="button" className="text-button" onClick={() => {
          setWatchError(false);
          setRetryWatch(value => value + 1);
        }}>Cập nhật trạng thái</button>
      </Notice>}
      {jobError && !activeJob && !proposalError && <Notice tone="error">Không thể tạo đề xuất. {jobError}</Notice>}
      {offeredRevision && <Notice tone="warning">
        Đã có đề xuất mới. Bản nháp đang chỉnh được lưu theo phiên bản này.{" "}
        <button type="button" className="text-button" onClick={() => {
          chooseRevision(offeredRevision);
          setOfferedRevision("");
        }}>Mở đề xuất mới</button>
      </Notice>}
      <div className="mapping-toolbar">
        <label>
          Phiên bản ánh xạ
          <select
            value={mapping.id}
            onChange={(e) => { chooseRevision(e.target.value); setOfferedRevision(""); }}
          >
            {mappings.map((m) => (
              <option key={m.id} value={m.id}>
                Lần {m.revision} · {statusText[m.status] || m.status}
              </option>
            ))}
          </select>
        </label>
        <Badge status={mapping.status} />
      </div>
      {needsReview && <p className="muted">{aiSuggested ? `${mapping.proposal_source === "GEMINI" ? "Gemini" : "Qwen"} đã đề xuất ánh xạ. ` : ""}Cần bạn xác nhận các trường trước khi chuẩn hóa.</p>}
      {aiSuggested && !mapping.proposal.decisions.some(decision => decision.candidate_target) &&
        <Notice tone="warning">AI chưa xác định được trường phù hợp. Bạn có thể chọn trường thủ công sau khi xem nguồn.</Notice>}
      {mapping.template_mapping_id && (
        <Notice>Đã điền thông tin từ một mẫu từng được duyệt. Hãy kiểm tra trước khi dùng cho tệp này.</Notice>
      )}
      {canManageReuse && (mapping.reuse_eligible || mapping.reuse_enabled) && (
        <details>
          <summary>Tự áp dụng cho lần tải tương thích</summary>
          <p>Áp dụng cho tệp cùng tên trong dự án này. Hệ thống kiểm tra cấu trúc, định dạng, khóa và tất cả các dòng trước khi chuẩn hóa theo mẫu đã duyệt.</p>
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={() => void run(async () => {
              const enabled = Boolean(mapping.reuse_enabled);
              await api(`/mappings/${mapping.id}/reuse-policy`, {
                method: "PATCH",
                body: JSON.stringify({enabled: !enabled, expected_enabled: enabled}),
              });
              await onApproved();
            })}
          >
            {mapping.reuse_enabled ? "Tắt tự áp dụng mẫu" : "Cho phép tự áp dụng mẫu"}
          </button>
        </details>
      )}
      <fieldset className="mapping-facts">
        <legend>Ý nghĩa của bảng</legend>
        <div className="form-grid">
        <label>
          Loại dữ liệu
          <input
            placeholder="Ví dụ: đơn hàng, vận đơn"
            value={entity}
            onChange={(e) => { chooseRevision(mapping.id); setEntity(e.target.value); }}
          />
        </label>
        <label>
          Mỗi dòng đại diện cho điều gì?
          <input
            placeholder="Ví dụ: một dòng sản phẩm của đơn hàng"
            value={grain}
            onChange={(e) => { chooseRevision(mapping.id); setGrain(e.target.value); }}
          />
        </label>
        </div>
      </fieldset>
      {mapping.proposal.unresolved_questions.map((q, i) => (
        <Notice key={i} tone="warning">
          {q}
        </Notice>
      ))}
      {table.parsed.warnings.length > 0 && (
        <Notice tone="warning">
          <ul>
            {table.parsed.warnings.map((w) => (
              <li key={w}>{warningText[w] || w}</li>
            ))}
          </ul>
          <label className="check-label">
            <input
              type="checkbox"
              checked={reviewed}
              onChange={(e) => { chooseRevision(mapping.id); setReviewed(e.target.checked); }}
            />
            Tôi đã kiểm tra các cảnh báo và vùng dữ liệu nguồn.
          </label>
        </Notice>
      )}
      <div className="mapping-help">
        <p>
          Chọn tên trường theo ý nghĩa của cột. Cột chưa ánh xạ vẫn xem được trong dữ liệu gốc.
        </p>
      </div>
      {preflightError&&<Notice tone="error">{preflightError}</Notice>}
      {!invalid&&!preflight&&!preflightError&&<p role="status">Đang kiểm tra trước chuẩn hóa…</p>}
      {preflight&&<Notice>Đã kiểm tra {preflight.source_rows} dòng; dự kiến {preflight.predicted_invalid_rows} dòng không hợp lệ. {Object.entries(preflight.error_counts).map(([code,count])=>`${code}: ${count}`).join('; ')}. Dữ liệu gốc và bản đã tạo được giữ lại.</Notice>}
      <div className="mapping-rows" aria-label="Các cột trong bảng">
        {drafts.map((d) => {
          const col = columnsById.get(d.source)!;
          const decision = mapping.proposal.decisions.find(
            (x) => x.source_field === d.source,
          );
          return (
            <details className="mapping-row mapping-register-row" key={d.source}>
              <summary aria-label={`Chỉnh cột ${col.name}`}>
                <span>{col.name}</span>
                <span>{d.target ? d.label : "Giữ cột gốc"}{d.key && <small> · Khóa</small>}</span>
                {decision && <Badge status={decision.decision} />}
              </summary>
              <div className="mapping-register-editor">
              <div className="source-column">
                <div className="source-title">
                  <strong>{col.name}</strong>
                  <button
                    className="icon-button"
                    aria-label={`Bằng chứng ${col.name}`}
                    onClick={() => onEvidence(`${table.id}:${d.source}`)}
                  >
                    <Eye size={17} />
                  </button>
                </div>
                <div className="sample-values">
                  {col.samples.slice(0, 3).map((s, i) => (
                    <code key={i}>
                      {s === null ? "NULL" : s === "" ? "Chuỗi rỗng" : s}
                    </code>
                  ))}
                </div>
                <small>
                  {col.null_count} giá trị thiếu · {col.distinct_count} giá trị phân biệt
                </small>
              </div>
              <div className="target-column">
                <div className="mapping-fields">
                  <MappingTargetPicker column={col.name} draft={d} fields={[...fields.values()]}
                    occupied={occupied}
                    suggestion={aiSuggested ? decision?.candidate_target : null}
                    readOnly={readOnly || busy}
                    onSelect={field => {
                      if ((field?.id || "") === d.target) return;
                      change(d.source, {
                        target: field?.id || "", label: field?.name || col.name, type: field?.data_type || "string",
                        required: field?.required || false, key: Boolean(field && mapping.schema.business_key_fields.includes(field.id)),
                        metric: field?.semantic_metric || "", basis: field?.amount_basis || "",
                        currency: field?.currency || "", unit: field?.unit || "",
                        locale: "", dateFormat: "", timezone: "", trim: false,
                      });
                    }} />
                  <label>
                    Kiểu dữ liệu
                    <select
                      aria-label={`Kiểu ${col.name}`}
                      value={d.type}
                      onChange={(e) =>
                        change(d.source, { type: e.target.value as DataType })
                      }
                    >
                      <option value="string">Chuỗi / mã định danh</option>
                      <option value="decimal">Số tiền chính xác</option>
                      <option value="date">Ngày và thời gian</option>
                    </select>
                  </label>
                </div>
                {d.target && (
                  <>
                    <div className="inline-options">
                      <label className="check-label">
                        <input
                          type="checkbox"
                          checked={d.required}
                          onChange={(e) =>
                            change(d.source, { required: e.target.checked })
                          }
                        />
                        Bắt buộc
                      </label>
                      <label className="check-label">
                        <input
                          type="checkbox"
                          checked={d.key}
                          onChange={(e) =>
                            change(d.source, { key: e.target.checked })
                          }
                        />
                        Thành phần khóa
                      </label>
                      {d.type === "string" && (
                        <label className="check-label">
                          <input
                            type="checkbox"
                            checked={d.trim}
                            onChange={(e) =>
                              change(d.source, { trim: e.target.checked })
                            }
                          />
                          Duyệt bỏ khoảng trắng đầu/cuối
                        </label>
                      )}
                    </div>
                    {d.type === "decimal" && (
                      <div className="decimal-fields">
                        <label>
                          Cách viết số
                          <select
                            aria-label={`Locale ${col.name}`}
                            value={d.locale}
                            onChange={(e) =>
                              change(d.source, { locale: e.target.value })
                            }
                          >
                            <option value="">Cần xác nhận</option>
                            <option value="vi-VN">1.234,50 (vi-VN)</option>
                            <option value="en-US">1,234.50 (en-US)</option>
                          </select>
                        </label>
                        <label>
                          Ý nghĩa chỉ tiêu
                          <input
                            aria-label={`Chỉ tiêu ${col.name}`}
                            placeholder="Ví dụ: sales_before_discount"
                            value={d.metric}
                            onChange={(e) =>
                              change(d.source, { metric: e.target.value })
                            }
                          />
                        </label>
                        <label>
                          Cơ sở số tiền
                          <select
                            aria-label={`Cơ sở ${col.name}`}
                            value={d.basis}
                            onChange={(e) =>
                              change(d.source, { basis: e.target.value })
                            }
                          >
                            <option value="">Cần xác nhận</option>
                            <option value="gross">
                              Trước giảm trừ (gross)
                            </option>
                            <option value="net">Sau giảm trừ (net)</option>
                            <option value="user_defined">
                              Định nghĩa theo chỉ tiêu đã nhập
                            </option>
                          </select>
                        </label>
                        <label>
                          Tiền tệ
                          <input
                            aria-label={`Tiền tệ ${col.name}`}
                            placeholder="Ví dụ: VND"
                            value={d.currency}
                            onChange={(e) =>
                              change(d.source, { currency: e.target.value })
                            }
                          />
                        </label>
                        <label>
                          Đơn vị
                          <input
                            aria-label={`Đơn vị ${col.name}`}
                            placeholder="Ví dụ: VND"
                            value={d.unit}
                            onChange={(e) =>
                              change(d.source, { unit: e.target.value })
                            }
                          />
                        </label>
                      </div>
                    )}
                    {d.type === "date" && (
                      <div className="form-grid">
                        <label>
                          Định dạng ngày
                          <input
                            placeholder="%Y-%m-%d"
                            value={d.dateFormat}
                            onChange={(e) =>
                              change(d.source, { dateFormat: e.target.value })
                            }
                          />
                        </label>
                        <label>
                          Múi giờ đã xác nhận
                          <input
                            placeholder="Asia/Ho_Chi_Minh"
                            value={d.timezone}
                            onChange={(e) =>
                              change(d.source, { timezone: e.target.value })
                            }
                          />
                        </label>
                      </div>
                    )}
                  </>
                )}
                {decision?.reasoning && (
                  <details>
                    <summary>
                      Lý do đề xuất <ChevronDown size={12} />
                    </summary>
                    <p>{decision.reasoning}</p>
                    {decision.unresolved_questions.map((q, i) => (
                      <p key={i}>{q}</p>
                    ))}
                  </details>
                )}
              </div>
              </div>
            </details>
          );
        })}
      </div>
      <div className="approval-bar">
        <p>Mỗi lần xác nhận lưu một phiên bản kèm người duyệt và nguồn dữ liệu.</p>
        <div className="actions">
          <button
            className="button secondary"
            disabled={
              busy ||
              readOnly ||
              ["APPROVED", "SUPERSEDED", "REJECTED"].includes(mapping.status)
            }
            onClick={() =>
              void run(async () => {
                await api(`/mappings/${mapping.id}/reject`, { method: "POST" });
                await onApproved();
              })
            }
          >
            Từ chối đề xuất
          </button>
          <button
            className="button primary"
            disabled={
              busy ||
              readOnly ||
              invalid || !preflight || preflightSignature!==bodySignature ||
              ["SUPERSEDED", "REJECTED"].includes(mapping.status)
            }
            onClick={() => void run(approve)}
          >
            {busy ? (
              <Spinner />
            ) : (
              <>
                <Check size={18} />
                Xác nhận ánh xạ
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export function MappingStudio({onOpenConversation, ...props}: Parameters<typeof ManualMappingStudio>[0] & {
  onOpenConversation: (id: string) => void;
}) {
  const [workflows, setWorkflows] = useState<Workflow[] | null>(null);
  const [error, setError] = useState("");
  const [chosen, setChosen] = useState("");
  const alive = useRef(true);
  const requestSequence = useRef(0);
  async function refresh() {
    const sequence = ++requestSequence.current;
    const rows = await api<Workflow[]>(`/agent/tables/${props.table.id}/mapping-reviews`);
    if (alive.current && sequence === requestSequence.current) {
      setWorkflows(rows); setError("");
    }
    return rows;
  }
  useEffect(() => {
    alive.current = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try { await refresh(); } catch (err) {
        if (alive.current) setError(err instanceof Error ? err.message : "Không tải được thẻ xác nhận.");
      }
      if (alive.current) timer = setTimeout(() => void poll(), 4000);
    }
    void poll();
    return () => { alive.current = false; requestSequence.current++; clearTimeout(timer); };
  }, [props.table.id]);
  if (error) return <Notice tone="error">{error}<button onClick={()=>void refresh().catch(err=>setError(String(err)))}>Cập nhật thẻ xác nhận</button></Notice>;
  if (workflows === null) return <Spinner />;
  if (!workflows.length) return <ManualMappingStudio {...props}/>;
  const workflow = workflows.find(row => row.id === chosen) || workflows[0];
  return <div className="mapping-studio">
    <header className="section-heading">
      <div>
        <h2>Đề xuất đang chờ xác nhận</h2>
        <p>Bảng <strong>{props.table.sheet}</strong> · {props.table.row_count.toLocaleString("vi-VN")} dòng</p>
      </div>
      <button type="button" className="text-button" onClick={() => onOpenConversation(workflow.conversation_id)}>Mở trong hội thoại</button>
    </header>
    <p>Đây là cùng bản nháp trong hội thoại. Lưu bản nháp để tiếp tục ở màn hình khác. Dữ liệu được chuẩn hóa sau khi bạn duyệt.</p>
    {workflows.length > 1 && <label>Chọn bản nháp đang chờ<select value={workflow.id} onChange={e=>setChosen(e.target.value)}>{workflows.map((row,index)=><option key={row.id} value={row.id}>Bản nháp {index+1} · {new Date(row.updated_at).toLocaleString("vi-VN")}</option>)}</select></label>}
    {workflow.detail.reviews.filter(r=>r.kind==="MAPPING"&&r.resource_id===props.table.id&&r.state==="OPEN").map(review=><ReviewCard key={`${review.id}:${review.nonce}`} review={review} workflow={workflow} canEdit={!props.readOnly&&!props.busy} draftOwner={props.draftOwner} refresh={async()=>{const rows=await refresh();if(!rows.length)await props.onApproved();}}/>)}
    <details><summary>Tạo cách ghép cột thủ công riêng</summary><Notice>Đây là proposal độc lập. Nếu duyệt cách ghép thủ công, thẻ trong hội thoại phải được kiểm tra lại vì nguồn ánh xạ đã thay đổi.</Notice><ManualMappingStudio {...props}/></details>
  </div>;
}
