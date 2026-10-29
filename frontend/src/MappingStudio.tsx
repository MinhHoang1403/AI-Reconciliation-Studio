import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Eye, Plus, Sparkles } from "lucide-react";
import { api } from "./api";
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

export function MappingStudio({
  table,
  profile,
  mappings,
  busy,
  readOnly = false,
  run,
  onApproved,
  onEvidence,
}: {
  table: Table;
  profile: Profile;
  mappings: Mapping[];
  busy: boolean;
  readOnly?: boolean;
  run: (task: () => Promise<void>) => Promise<void>;
  onApproved: () => Promise<void>;
  onEvidence: (id: string) => void;
}) {
  const [selected, setSelected] = useState("");
  const mapping = mappings.find((m) => m.id === selected) || mappings[0];
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [entity, setEntity] = useState("");
  const [grain, setGrain] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const initialized = useRef("");
  useEffect(() => {
    if (mapping) {
      // Mapping revisions and parsed tables are immutable. A refreshed DTO for the
      // same revision must not erase edits or source-review acknowledgement.
      const identity = `${table.id}:${mapping.id}`;
      if (initialized.current === identity) return;
      initialized.current = identity;
      setDrafts(makeDraft(mapping, profile));
      setEntity(
        mapping.schema.entity_kind === "unknown"
          ? ""
          : mapping.schema.entity_kind,
      );
      setGrain(mapping.schema.grain === "unknown" ? "" : mapping.schema.grain);
      setReviewed(false);
    }
  }, [mapping?.id, profile, table.id]);

  function change(source: string, patch: Partial<Draft>) {
    setDrafts((rows) =>
      rows.map((r) => (r.source === source ? { ...r, ...patch } : r)),
    );
  }
  async function approve() {
    if (!mapping) return;
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
    await api(`/mappings/${mapping.id}/approve`, {
      method: "POST",
      body: JSON.stringify({
        schema_definition: schema,
        decisions,
        extraction_reviewed: reviewed,
      }),
    });
    await onApproved();
  }
  const invalid =
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
              invalid ||
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
