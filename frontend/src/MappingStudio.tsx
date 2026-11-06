import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Eye, Plus, Sparkles } from "lucide-react";
import { api, ApiError } from "./api";
import { ReviewCard } from "./ReviewCard";
import type { Workflow } from "./agentTypes";
import { Badge, Notice, Spinner } from "./components";
import type {
  DataType,
  Decision,
  Mapping,
  Profile,
  Schema,
  SchemaField,
  Table,
} from "./types";
import { warningText, statusText } from "./types";

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

function makeDraft(mapping: Mapping, profile: Profile): Draft[] {
  const decisions = mapping.decision?.decisions || mapping.proposal.decisions;
  const approved = ["APPROVED", "SUPERSEDED"].includes(mapping.status);
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
      locale: approved ? String(d?.transformation_candidate.locale || "") : "",
      metric: field?.semantic_metric || "",
      basis: field?.amount_basis || "",
      currency: field?.currency || "",
      unit: field?.unit || "",
      dateFormat: approved
        ? String(d?.transformation_candidate.format || "")
        : "",
      timezone: approved
        ? String(d?.transformation_candidate.timezone || "")
        : "",
      trim: approved && d?.transformation_candidate.op === "trim_if_approved",
      key: mapping.schema.business_key_fields.includes(
        d?.candidate_target || "",
      ),
    };
  });
}

function ManualMappingStudio({
  table,
  profile,
  mappings,
  busy,
  readOnly = false,
  run,
  onApproved,
  onEvidence,
  draftOwner,
}: {
  table: Table;
  profile: Profile;
  mappings: Mapping[];
  busy: boolean;
  readOnly?: boolean;
  run: (task: () => Promise<void>) => Promise<void>;
  onApproved: () => Promise<void>;
  onEvidence: (id: string) => void;
  draftOwner: string;
}) {
  const [selected, setSelected] = useState("");
  const mapping = mappings.find((m) => m.id === selected) || mappings[0];
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [entity, setEntity] = useState("");
  const [grain, setGrain] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const initialized = useRef("");
  const pendingApproval = useRef<{body: string; key: string} | null>(null);
  const approving = useRef(false);
  const [loadedKey, setLoadedKey] = useState("");
  const storageKey = `studio.manual-mapping.${draftOwner}.${table.id}.${mapping?.id || "none"}`;
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
      setEntity(
        saved ? saved.entity : mapping.schema.entity_kind === "unknown"
          ? ""
          : mapping.schema.entity_kind,
      );
      setGrain(saved ? saved.grain : mapping.schema.grain === "unknown" ? "" : mapping.schema.grain);
      setReviewed(saved?.reviewed || false);
      setLoadedKey(storageKey);
    }
  }, [mapping?.id, profile, table.id, storageKey]);
  useEffect(() => {
    if (loadedKey !== storageKey) return;
    try { sessionStorage.setItem(storageKey, JSON.stringify({drafts, entity, grain, reviewed})); }
    catch { /* Manual edits remain in memory if browser storage is unavailable. */ }
  }, [loadedKey, storageKey, drafts, entity, grain, reviewed]);

  function change(source: string, patch: Partial<Draft>) {
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
  return (
    <div className="mapping-studio">
      <div className="section-heading">
        <div>
          <span className="eyebrow">AI SMART SETUP</span>
          <h2>Hiểu dữ liệu, xác nhận ý nghĩa</h2>
          <p>
            Gợi ý được kiểm tra bởi backend. Bạn xác nhận trước khi chuẩn hóa.
          </p>
        </div>
        <button
          className="button secondary"
          disabled={busy || readOnly}
          onClick={() =>
            void run(async () => {
              await api(`/tables/${table.id}/mapping-proposals`, {
                method: "POST",
              });
              await onApproved();
            })
          }
        >
          <Sparkles size={17} /> Đề xuất lại
        </button>
      </div>
      <div className="mapping-toolbar">
        <label>
          Phiên bản ánh xạ
          <select
            value={mapping.id}
            onChange={(e) => setSelected(e.target.value)}
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
      <div className="form-grid">
        <label>
          Loại dữ liệu
          <input
            placeholder="Ví dụ: đơn hàng, vận đơn"
            value={entity}
            onChange={(e) => setEntity(e.target.value)}
          />
        </label>
        <label>
          Mỗi dòng đại diện cho điều gì?
          <input
            placeholder="Ví dụ: một dòng sản phẩm của đơn hàng"
            value={grain}
            onChange={(e) => setGrain(e.target.value)}
          />
        </label>
      </div>
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
              onChange={(e) => setReviewed(e.target.checked)}
            />
            Tôi đã kiểm tra các cảnh báo và vùng dữ liệu nguồn.
          </label>
        </Notice>
      )}
      <div className="mapping-help">
        <p>
          Chọn tên trường chuẩn cho từng cột. Để trống trường đích nếu chưa sử
          dụng; dữ liệu gốc vẫn được giữ.
        </p>
        <button
          className="text-button"
          onClick={() =>
            setDrafts((rows) =>
              rows.map((r) => ({
                ...r,
                target: r.target || `field_${r.source}`,
                type: r.target ? r.type : "string",
              })),
            )
          }
        >
          <Plus size={15} />
          Giữ các cột chưa chọn dưới dạng chuỗi
        </button>
      </div>
      {preflightError&&<Notice tone="error">{preflightError}</Notice>}
      {!invalid&&!preflight&&!preflightError&&<p role="status">Đang kiểm tra trước chuẩn hóa…</p>}
      {preflight&&<Notice>Đã kiểm tra {preflight.source_rows} dòng; dự kiến {preflight.predicted_invalid_rows} dòng không hợp lệ. {Object.entries(preflight.error_counts).map(([code,count])=>`${code}: ${count}`).join('; ')}. Dữ liệu gốc và bản cũ được giữ nguyên.</Notice>}
      <div className="mapping-rows">
        {drafts.map((d) => {
          const col = profile.columns.find((c) => c.column_id === d.source)!;
          const decision = mapping.proposal.decisions.find(
            (x) => x.source_field === d.source,
          );
          return (
            <article className="mapping-row" key={d.source}>
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
                  {col.null_count} null · {col.distinct_count} giá trị phân biệt
                </small>
                {decision && <Badge status={decision.decision} />}
              </div>
              <div className="target-column">
                <div className="mapping-fields">
                  <label>
                    Trường đích
                    <input
                      aria-label={`Trường đích ${col.name}`}
                      value={d.target}
                      placeholder="Ví dụ: reference_id"
                      onChange={(e) =>
                        change(d.source, { target: e.target.value })
                      }
                    />
                  </label>
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
            </article>
          );
        })}
      </div>
      <div className="approval-bar">
        <p>Quyết định được lưu theo revision, kèm người duyệt và nguồn gốc.</p>
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

export function MappingStudio(props: Parameters<typeof ManualMappingStudio>[0]) {
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
  return <div className="mapping-studio"><h2>Đề xuất đang chờ xác nhận</h2>
    <p>Đây là cùng bản nháp trong hội thoại. Lưu bản nháp để tiếp tục ở màn hình khác; dữ liệu chỉ được chuẩn hóa sau khi bạn duyệt.</p>
    {workflows.length > 1 && <label>Chọn bản nháp đang chờ<select value={workflow.id} onChange={e=>setChosen(e.target.value)}>{workflows.map((row,index)=><option key={row.id} value={row.id}>Bản nháp {index+1} · {new Date(row.updated_at).toLocaleString("vi-VN")}</option>)}</select></label>}
    {workflow.detail.reviews.filter(r=>r.kind==="MAPPING"&&r.resource_id===props.table.id&&r.state==="OPEN").map(review=><ReviewCard key={`${review.id}:${review.nonce}`} review={review} workflow={workflow} canEdit={!props.readOnly&&!props.busy} draftOwner={props.draftOwner} refresh={async()=>{const rows=await refresh();if(!rows.length)await props.onApproved();}}/>)}
    <details><summary>Tạo cách ghép cột thủ công riêng</summary><Notice>Đây là proposal độc lập. Nếu duyệt cách ghép thủ công, thẻ trong hội thoại phải được kiểm tra lại vì nguồn ánh xạ đã thay đổi.</Notice><ManualMappingStudio {...props}/></details>
  </div>;
}
