import { useEffect, useState } from "react";
import { ArrowRight, Check, CircleHelp, RotateCw, Sparkles } from "lucide-react";

import {
  chooseMappingField,
  confirmMapping,
  getMapping,
  suggestMappingAgain,
  type ColumnMapping,
  type MappingSource,
  type TableMapping,
} from "../api";

// Ánh xạ cột: mỗi cột của tệp → một cột chuẩn. Cột hệ thống chắc chắn đã tự áp dụng;
// chỉ cột chưa chắc được gom lên đầu để người dùng đồng ý một lần.

const SOURCE_LABELS: Record<MappingSource, string> = {
  RULE_AI: "Quy tắc + AI",
  AI: "AI",
  RULE: "Quy tắc",
  MEMORY: "Đã nhớ",
  USER: "Bạn chọn",
};

const STATUS_LABELS = { AUTO: "Tự áp dụng", SUGGESTED: "Cần xem", CONFIRMED: "Đã xác nhận" } as const;

type Props = { tableId: string; mappingStatus: string; onChanged: () => void };

export function MappingView({ tableId, mappingStatus, onChanged }: Props) {
  const [mapping, setMapping] = useState<TableMapping | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getMapping(tableId, controller.signal)
      .then((data) => {
        setMapping(data);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Lỗi không rõ.");
      });
    return () => controller.abort();
  }, [tableId, mappingStatus]);

  async function run(action: () => Promise<TableMapping>) {
    setBusy(true);
    try {
      setMapping(await action());
      setError(null);
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không lưu được.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !mapping) return <p className="notice notice--error" role="alert">{error}</p>;
  if (!mapping || mapping.status === "NONE") return <p className="notice">Đang chuẩn bị ánh xạ…</p>;
  if (mapping.status === "MAPPING") {
    return (
      <p className="notice notice--busy">
        <Sparkles aria-hidden="true" size={16} /> Đang gợi ý ánh xạ cột, trang sẽ tự cập nhật…
      </p>
    );
  }

  const pending = mapping.columns.filter((column) => column.status === "SUGGESTED");
  const unconfirmed = mapping.columns.some((column) => column.status === "AUTO");
  const ordered = [...pending, ...mapping.columns.filter((column) => column.status !== "SUGGESTED")];

  return (
    <div className="mapping">
      <div className="mapping__summary">
        {mapping.table_kind_label && <span className="kind">{mapping.table_kind_label}</span>}
        <AiState mapping={mapping} />
        <button
          className="button button--quiet mapping__again"
          type="button"
          disabled={busy}
          onClick={() => void run(() => suggestMappingAgain(tableId))}
        >
          <RotateCw aria-hidden="true" size={16} />
          Gợi ý lại
        </button>
      </div>

      {error && <p className="notice notice--error" role="alert">{error}</p>}

      {pending.length > 0 ? (
        <section className="mapping__review" aria-labelledby="review-title">
          <div>
            <h3 id="review-title">Cần bạn xem {pending.length} cột</h3>
            <p>Hệ thống đã chọn sẵn gợi ý tốt nhất. Đồng ý nếu đúng, hoặc đổi ở ô chọn của cột đó.</p>
          </div>
          <button
            className="button button--primary"
            type="button"
            disabled={busy}
            onClick={() => void run(() => confirmMapping(tableId))}
          >
            <Check aria-hidden="true" size={18} />
            Đồng ý tất cả
          </button>
        </section>
      ) : (
        unconfirmed && (
          <section className="mapping__review mapping__review--calm" aria-labelledby="review-title">
            <div>
              <h3 id="review-title">Mọi cột đã được ánh xạ</h3>
              <p>Xác nhận để hệ thống ghi nhớ; tệp cùng cấu trúc lần sau sẽ tự ánh xạ, không cần hỏi lại.</p>
            </div>
            <button
              className="button button--quiet"
              type="button"
              disabled={busy}
              onClick={() => void run(() => confirmMapping(tableId))}
            >
              Xác nhận và ghi nhớ
            </button>
          </section>
        )
      )}

      <ul className="mapping__list">
        {ordered.map((column) => (
          <MappingRow
            key={column.position}
            column={column}
            fields={mapping.fields}
            disabled={busy}
            onChoose={(fieldKey) => void run(() => chooseMappingField(tableId, column.position, fieldKey))}
          />
        ))}
      </ul>
    </div>
  );
}

function AiState({ mapping }: { mapping: TableMapping }) {
  if (mapping.ai_state === "AI") return <span className="mapping__ai">Gợi ý bởi quy tắc và Gemini</span>;
  if (mapping.ai_state === "MEMORY") return <span className="mapping__ai">Dùng lại ánh xạ đã xác nhận</span>;
  return (
    <span className="mapping__ai mapping__ai--warn">
      Chỉ dùng quy tắc{mapping.ai_message ? `: ${mapping.ai_message}` : ""}
    </span>
  );
}

type RowProps = {
  column: ColumnMapping;
  fields: TableMapping["fields"];
  disabled: boolean;
  onChoose: (fieldKey: string | null) => void;
};

function MappingRow({ column, fields, disabled, onChoose }: RowProps) {
  const selectId = `map-${column.position}`;
  return (
    <li className="mapping__row" data-status={column.status}>
      <div className="mapping__source">
        <label htmlFor={selectId}>{column.column_name}</label>
        <ArrowRight aria-hidden="true" size={16} />
      </div>
      <select
        id={selectId}
        value={column.field_key ?? ""}
        disabled={disabled}
        onChange={(event) => onChoose(event.target.value || null)}
      >
        <option value="">Không ánh xạ</option>
        {fields.map((field) => (
          <option key={field.key} value={field.key}>
            {field.label}
          </option>
        ))}
      </select>
      <div className="mapping__meta">
        <span className="mapping__status" data-status={column.status}>
          {column.status === "SUGGESTED" ? (
            <CircleHelp aria-hidden="true" size={14} />
          ) : (
            <Check aria-hidden="true" size={14} />
          )}
          {STATUS_LABELS[column.status]}
        </span>
        <span className="mapping__by">{SOURCE_LABELS[column.source]}</span>
      </div>
      {column.reason && <p className="mapping__reason">{column.reason}</p>}
    </li>
  );
}
