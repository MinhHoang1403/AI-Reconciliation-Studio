import { useEffect, useRef, useState } from "react";
import { api, apiPages } from "./api";
import { Notice, Spinner } from "./components";
import type { DraftField, NormalizationDraft, Review, Workflow, MappingAssessment, SharedMappingFacts } from "./agentTypes";
import { label, type Plan, type Catalogue, type Slot } from "./reconciliationTypes";
import { errorText as errors, qualityText } from "./types";
function proposedPlan(review: Review, catalogue: Catalogue[]): Plan | null {
    const request = review.planning_request, s = review.suggestions;
    if (!request || !s || !s.join_keys.length || !s.comparison_metrics.length || !s.cardinality || !s.aggregation || !s.comparison_grain)
        return null;
    const left = catalogue.find(c => c.canonical.id === request.left.canonical_id);
    const right = catalogue.find(c => c.canonical.id === request.right.canonical_id);
    if (!left || !right)
        return null;
    const slot = (side: "left" | "right"): Slot => ({ ...{ canonical_id: request[side].canonical_id,
            role: side === "left" ? s.left_role : s.right_role, date_field: "", time_basis: "", currency_field: null,
            filters: {}, coverage_start: "", coverage_end: "", completeness: "", snapshot_at: "", settlement_due_at: null },
        // Missing optional facts can be explicit null; keep editable defaults.
        // Explicit false, zero and filters remain part of the reviewed proposal.
        ...Object.fromEntries(Object.entries(request[side]).filter(([, value]) => value !== null && value !== undefined)) });
    return { name: "Đối soát hai nguồn", entity_kind: left.schema_definition.entity_kind,
        left: slot("left"), right: slot("right"), join_keys: s.join_keys, comparison_metrics: s.comparison_metrics,
        attributes: [], comparison_grain: s.comparison_grain, cardinality: s.cardinality, aggregation: s.aggregation,
        period_start: request.period_start || "", period_end: request.period_end || "", timezone: request.timezone || "",
        effective_from: request.effective_from || "", effective_to: request.effective_to || null,
        allow_partial: request.allow_partial || false, duplicate_policy: "REVIEW", fuzzy_fields: [], fuzzy_block_keys: [],
        fuzzy_min_score: 85, fuzzy_top_k: 3, evidence_ids: s.evidence_ids };
}
function MappingReview({ draft, onChange, disabled }: {
    draft: NormalizationDraft;
    onChange: (draft: NormalizationDraft) => void;
    disabled: boolean;
}) {
    function field(index: number, patch: Partial<DraftField>) { onChange({ ...draft, fields: draft.fields.map((f, i) => i === index ? { ...f, ...patch } : f) }); }
    return <div className="agent-review-fields"><label>Loại dữ liệu<input value={draft.entity_kind} disabled={disabled} onChange={e => onChange({ ...draft, entity_kind: e.target.value })}/></label>
    <label>Mỗi dòng thể hiện điều gì?<input value={draft.grain} disabled={disabled} onChange={e => onChange({ ...draft, grain: e.target.value })}/></label>
    {draft.fields.map((f, i) => <details key={f.source_field} className="agent-field">
      <summary>{f.name} · {f.data_type === "decimal" ? "Số tiền" : f.data_type === "date" ? "Ngày" : "Giữ nguyên văn bản"}</summary>
      {f.question && <p>{f.question}</p>}<div className="agent-form-grid">
      <label>Tên trường<input value={f.name} disabled={disabled} onChange={e => field(i, { name: e.target.value })}/></label>
      <label>Kiểu dữ liệu<select value={f.data_type} disabled={disabled} onChange={e => field(i, { data_type: e.target.value as DraftField["data_type"] })}><option value="string">Văn bản, giữ nguyên mã</option><option value="decimal">Số tiền chính xác</option><option value="date">Ngày và múi giờ</option></select></label>
      <label><input type="checkbox" checked={f.business_key} disabled={disabled} onChange={e => field(i, { business_key: e.target.checked })}/>Trường khóa nghiệp vụ</label>
      {f.data_type === "decimal" && <>
        <label>Ý nghĩa số tiền<input value={f.semantic_metric || ""} disabled={disabled} placeholder="Ví dụ: delivery_charge" onChange={e => field(i, { semantic_metric: e.target.value || null })}/></label>
        <label>Cơ sở số tiền<select value={f.amount_basis || ""} disabled={disabled} onChange={e => field(i, { amount_basis: e.target.value || null })}><option value="">Chưa xác định</option>{Array.from(new Set([...Object.keys(amountBases), ...(f.amount_basis ? [f.amount_basis] : [])])).map(v => <option key={v} value={v}>{amountBases[v] || v}</option>)}</select></label>
        <label>Tiền tệ<input value={f.currency || ""} disabled={disabled} placeholder="VND / USD" maxLength={3} onChange={e => field(i, { currency: e.target.value.toUpperCase() || null })}/></label>
        <label>Đơn vị<input value={f.unit || ""} disabled={disabled} placeholder="VND" onChange={e => field(i, { unit: e.target.value || null })}/></label>
        <label>Định dạng số<select value={f.locale || ""} disabled={disabled} onChange={e => field(i, { locale: (e.target.value || null) as DraftField["locale"] })}><option value="">Cần xác nhận</option><option value="en-US">1,234.56</option><option value="vi-VN">1.234,56</option></select></label>
      </>}
      {f.data_type === "date" && <><label>Định dạng ngày<select value={f.date_format || ""} disabled={disabled} onChange={e => field(i, { date_format: e.target.value || null })}><option value="">Cần xác nhận</option>{Array.from(new Set(["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", ...(f.date_format ? [f.date_format] : [])])).map(v => <option value={v} key={v}>{({ "%Y-%m-%d": "2026-10-31", "%d/%m/%Y": "31/10/2026", "%m/%d/%Y": "10/31/2026" } as Record<string, string>)[v] || v}</option>)}</select></label>
        <label>Múi giờ<input value={f.timezone || ""} disabled={disabled} placeholder="Asia/Ho_Chi_Minh / UTC" onChange={e => field(i, { timezone: e.target.value || null })}/></label></>}
      {f.data_type === "string" && <label>Ý nghĩa trạng thái (nếu có)<select value={f.semantic_metric || ""} disabled={disabled} onChange={e => field(i, { semantic_metric: e.target.value || null })}><option value="">Văn bản / chưa xác nhận</option><option value="payment_status">Trạng thái thanh toán, có bằng chứng</option>{f.semantic_metric && f.semantic_metric !== "payment_status" && <option value={f.semantic_metric}>{f.semantic_metric}</option>}</select></label>}
      </div></details>)}
  </div>;
}
function PlanReview({ plan, onChange, disabled }: {
    plan: Plan;
    onChange: (plan: Plan) => void;
    disabled: boolean;
}) {
    return <div className="agent-review-fields"><p>Khóa: {plan.join_keys.map(k => `${k.left} ↔ ${k.right}`).join(", ")}</p><p>{plan.comparison_grain} · {label(plan.cardinality)} · {label(plan.aggregation)}</p>
    {plan.comparison_metrics.map(m => <p key={m.metric_id}>{m.metric_id} · {m.amount_basis} · {m.currency} · sai số {m.absolute_tolerance}</p>)}
    <div className="agent-form-grid">{(["period_start", "period_end", "effective_from"] as const).map(k => <label key={k}>{{ period_start: "Bắt đầu kỳ", period_end: "Kết thúc kỳ (không bao gồm)", effective_from: "Quy tắc có hiệu lực từ" }[k]}<input type="date" value={plan[k]} disabled={disabled} onChange={e => onChange({ ...plan, [k]: e.target.value })}/></label>)}
    <label>Quy tắc có hiệu lực đến (không bao gồm)<input type="date" value={plan.effective_to ?? ""} disabled={disabled} onChange={e => onChange({ ...plan, effective_to: e.target.value || null })}/></label>
    <label>Múi giờ<input value={plan.timezone} disabled={disabled} onChange={e => onChange({ ...plan, timezone: e.target.value })}/></label></div>
    {(["left", "right"] as const).map(side => <fieldset key={side}><legend>{side === "left" ? "Nguồn trái" : "Nguồn phải"} · {plan[side].role}</legend><div className="agent-form-grid">
      <label>Trường ngày<input value={plan[side].date_field} disabled={disabled} onChange={e => onChange({ ...plan, [side]: { ...plan[side], date_field: e.target.value } })}/></label>
      <label>Ý nghĩa ngày<input value={plan[side].time_basis} disabled={disabled} onChange={e => onChange({ ...plan, [side]: { ...plan[side], time_basis: e.target.value } })}/></label>
      {(["coverage_start", "coverage_end", "snapshot_at"] as const).map(key => <label key={key}>{{ coverage_start: "Dữ liệu đầy đủ từ (ISO và timezone)", coverage_end: "Dữ liệu đầy đủ đến (không bao gồm)", snapshot_at: "Thời điểm chốt dữ liệu" }[key]}<input value={plan[side][key]} disabled={disabled} onChange={e => onChange({ ...plan, [side]: { ...plan[side], [key]: e.target.value } })}/></label>)}
      <label>Độ đầy đủ<select value={plan[side].completeness} disabled={disabled} onChange={e => onChange({ ...plan, [side]: { ...plan[side], completeness: e.target.value } })}><option value="">Chưa xác nhận</option><option value="CONFIRMED">Đã xác nhận đầy đủ</option><option value="INCOMPLETE">Chưa đầy đủ</option><option value="UNKNOWN">Chưa xác định</option></select></label></div></fieldset>)}
    <details><summary>Thông số quy tắc</summary><p>Khóa, chỉ tiêu, cardinality và sai số ở trên là đề xuất; trả lời bằng tiếng Việt để chỉnh lại trước khi duyệt.</p><p>Bộ lọc trái: {JSON.stringify(plan.left.filters)} · phải: {JSON.stringify(plan.right.filters)}</p></details>
  </div>;
}
const amountBases: Record<string, string> = {
    gross: "Trước khấu trừ", net: "Sau khấu trừ", expected: "Dự kiến phải thu", paid: "Đã thanh toán",
    due: "Đến hạn", fee: "Phí", excluding_tax: "Chưa gồm thuế", tax: "Tiền thuế",
    including_tax: "Đã gồm thuế", net_excluding_tax: "Doanh thu thuần chưa thuế",
};
const unknownFact = (value: string | null) => !value || ["", "unknown", "ambiguous", "n/a", "none", "needs_review"].includes(value.trim().toLowerCase());
const dateExamples: Record<string, string> = {
    "%Y-%m-%d": "2026-07-15", "%d/%m/%Y": "15/07/2026", "%m/%d/%Y": "07/15/2026",
    "%Y-%m-%dT%H:%M:%S%z": "2026-07-15T09:30:00+07:00", "%Y-%m-%d %H:%M": "2026-07-15 09:30",
    "%Y-%m-%d %H:%M:%S": "2026-07-15 09:30:00",
};

function SmartMapping({ draft, assessment, onChange, disabled }: {
    draft: NormalizationDraft;
    assessment: MappingAssessment | null;
    onChange: (draft: NormalizationDraft) => void;
    disabled: boolean;
}) {
    const [editing, setEditing] = useState("");
    const money = draft.fields.filter(f => f.data_type === "decimal");
    const dates = draft.fields.filter(f => f.data_type === "date");
    const checkByField = new Map(assessment?.checks.map(check => [check.field_id, check]));
    const dateKind = (f: DraftField) => checkByField.get(f.source_field)?.date_kind;
    const needsZone = (f: DraftField) => !!f.date_format && !f.timezone && dateKind(f) === "local";
    const zoneFields = dates.filter(needsZone);
    const invalidDateFields = dates.filter(f => !f.date_format || (!dateKind(f) && checkByField.has(f.source_field)));
    const pendingMoney = money.filter(f => editing === f.source_field ||
        [f.semantic_metric, f.amount_basis, f.locale].some(unknownFact) || (!!f.currency && unknownFact(f.unit)));
    const keyFields = draft.fields.filter(f => f.business_key);
    const candidates = (assessment?.key_candidates || []).filter(candidate =>
        draft.fields.some(f => f.source_field === candidate.field_id && f.data_type === "string"));
    const references = candidates.filter(candidate => candidate.reference && !keyFields.some(f => f.source_field === candidate.field_id));
    const observed = assessment?.currencies || [];
    const selectedCurrencies = [...new Set(money.map(f => f.currency).filter(Boolean))];
    const currency = selectedCurrencies.length === 1 ? selectedCurrencies[0] : null;
    const needsCurrency = money.some(f => unknownFact(f.currency));
    const currencyOptions = [...new Set(["VND", ...observed, ...selectedCurrencies, "USD"].filter((value): value is string => !!value && /^[A-Z]{3}$/.test(value)))];
    const currenciesOutside = currency ? Object.entries(assessment?.currency_counts || {}).filter(([code]) => code !== currency) : [];
    const changeField = (id: string, patch: Partial<DraftField>) =>
        onChange({ ...draft, fields: draft.fields.map(f => f.source_field === id ? { ...f, ...patch } : f) });
    const changeCurrency = (value: string) => {
        if (value) onChange({ ...draft, fields: draft.fields.map(f => f.data_type === "decimal" && (!needsCurrency || unknownFact(f.currency))
            ? { ...f, currency: value, unit: unknownFact(f.unit) || f.unit === f.currency ? value : f.unit } : f) });
    };
    const currencyControl = <label>{observed.length > 1 ? "Tiền tệ trong phạm vi chuẩn hóa" : "Tiền tệ của nguồn"}
        <select value={needsCurrency ? "" : currency || ""} disabled={disabled} onChange={e => changeCurrency(e.target.value)}>
            <option value="">Chọn tiền tệ</option>{currencyOptions.map(code => <option key={code} value={code}>
                {code === "VND" && observed.includes("VND") && needsCurrency ? "VND (phạm vi đề xuất)" : code}
            </option>)}
        </select>
    </label>;
    const facts = [
        { id: "entity_kind", label: "Loại giao dịch", max: 100 },
        { id: "grain", label: "Mỗi dòng đại diện cho điều gì?", max: 200 },
    ] as const;
    const completeMoney = money.filter(f => !pendingMoney.includes(f));
    return <div className="smart-mapping">
        {facts.map(({id, label, max}) => (unknownFact(draft[id]) || editing === id) &&
            <label key={id}>{label}<input value={unknownFact(draft[id]) ? "" : draft[id]} maxLength={max} disabled={disabled}
                onFocus={() => setEditing(id)} onBlur={() => setEditing("")}
                onChange={e => onChange({ ...draft, [id]: e.target.value || "unknown" })}/></label>)}
        <div className="smart-mapping-facts">
            {facts.every(({id}) => !unknownFact(draft[id])) && editing !== "grain" && editing !== "entity_kind" &&
                <p><strong>{draft.entity_kind}</strong> · {draft.grain}</p>}
            <p><strong>Khóa nhận diện dòng</strong> · {keyFields.map(f => f.name).join(" + ") || "Chưa chọn"}</p>
            {references.length > 0 && <p className="muted">Mã liên kết · {references.map(f => f.name).join(", ")}</p>}
            {candidates.length > 0 && <details>
                <summary>{keyFields.length ? "Đổi khóa nhận diện" : "Chọn khóa nhận diện"}</summary>
                <div className="smart-mapping-options">{candidates.map(candidate => <label key={candidate.field_id}>
                    <input type="checkbox" checked={keyFields.some(f => f.source_field === candidate.field_id)} disabled={disabled}
                        onChange={e => changeField(candidate.field_id, {business_key: e.target.checked})}/>
                    <span>{candidate.name}<small>{candidate.reference && "Mã liên kết · "}
                        {candidate.missing_rows} ô thiếu · {candidate.duplicate_rows} giá trị lặp</small></span>
                </label>)}</div>
            </details>}
        </div>
        {invalidDateFields.map(f => <label key={f.source_field}>Định dạng ngày của {f.name}
            <select value={f.date_format || ""} disabled={disabled} onChange={e => changeField(f.source_field, { date_format: e.target.value || null })}>
                <option value="">Chọn định dạng</option>{[...new Set([...(checkByField.get(f.source_field)?.date_formats || []), ...Object.keys(dateExamples), ...(f.date_format ? [f.date_format] : [])])]
                    .map(fmt => <option value={fmt} key={fmt}>{dateExamples[fmt] || fmt}</option>)}
            </select>
        </label>)}
        {zoneFields.length > 0 && <label>Múi giờ nguồn của {zoneFields.map(f => f.name).join(", ")}
            <select aria-label="Múi giờ của nguồn" value="" disabled={disabled} onChange={e => {
                const timezone = e.target.value;
                if (timezone) onChange({ ...draft, fields: draft.fields.map(f => needsZone(f) ? { ...f, timezone } : f) });
            }}>
                <option value="">Chọn múi giờ gốc</option><option value="UTC">UTC (đề xuất)</option>
                <option value="Asia/Ho_Chi_Minh">Việt Nam (Asia/Ho_Chi_Minh)</option>
            </select>
        </label>}
        {!!dates.length && !zoneFields.length && !invalidDateFields.length && dates.every(f => dateKind(f)) &&
            <details><summary>{dates.every(f => dateKind(f) === "calendar") ? "Ngày lịch · Giữ nguyên ngày nguồn" : "Múi giờ xử lý · UTC"}</summary>
                {dates.map(f => <p key={f.source_field}>{f.name} · {dateKind(f) === "calendar" ? "Ngày lịch" : dateKind(f) === "offset" ? "Theo offset gốc" : f.timezone}</p>)}
                {dates.some(f => dateKind(f) === "local") && <p>Đổi múi giờ gốc trong phần chỉnh sửa chi tiết.</p>}
            </details>}
        {needsCurrency ? currencyControl : !!money.length && <details><summary>Tiền tệ · {currency || "Theo từng chỉ tiêu"}</summary>{currencyControl}</details>}
        {observed.length > 1 && <p className="smart-mapping-warning">{currenciesOutside.length
            ? currenciesOutside.map(([code, count]) => `${count.toLocaleString("vi-VN")} dòng ngoài phạm vi ${currency} · ${code}`).join(" · ")
            : `Nguồn có nhiều tiền tệ · ${observed.join(", ")}`}. Dữ liệu gốc được giữ để xử lý sau chuẩn hóa.</p>}
        {!!money.length && <section className="smart-mapping-money" aria-label="Chỉ tiêu tiền">
            {pendingMoney.length > 0 && <h5>Chỉ tiêu tiền cần bổ sung</h5>}
            {pendingMoney.map(f => <fieldset key={f.source_field}><legend>{f.name}</legend>
                {unknownFact(f.semantic_metric) || editing === f.source_field ? <label>Khoản tiền này là gì?<input value={f.semantic_metric || ""}
                    maxLength={100} disabled={disabled} onFocus={() => setEditing(f.source_field)} onBlur={() => setEditing("")}
                    onChange={e => changeField(f.source_field, {semantic_metric: e.target.value || null})}/></label> : null}
                {unknownFact(f.amount_basis) && <label>Cơ sở tiền của {f.name}<select value="" disabled={disabled}
                    onChange={e => changeField(f.source_field, {amount_basis: e.target.value || null})}>
                    <option value="">Chọn cơ sở tiền</option>{Object.entries(amountBases).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                </select></label>}
                {!f.locale && <label>Cách ghi số của {f.name}<select value="" disabled={disabled}
                    onChange={e => changeField(f.source_field, {locale: (e.target.value || null) as DraftField["locale"]})}>
                    <option value="">Chọn cách ghi</option><option value="en-US">1,234.56</option><option value="vi-VN">1.234,56</option>
                </select></label>}
                {unknownFact(f.unit) && f.currency && <button type="button" className="text-button" disabled={disabled}
                    onClick={() => changeField(f.source_field, {unit: f.currency})}>Dùng đơn vị {f.currency}</button>}
            </fieldset>)}
            {completeMoney.length > 0 && <details><summary>{completeMoney.length} chỉ tiêu tiền đã có đề xuất</summary>
                <ul>{completeMoney.map(f => <li key={f.source_field}>{f.name} · {amountBases[f.amount_basis || ""] || f.amount_basis} {f.currency && `· ${f.currency}`}</li>)}</ul>
            </details>}
        </section>}
    </div>;
}

type PlanningScope = NonNullable<Review["planning_request"]>;

const planningSides = ["left", "right"] as const;
type PlanningSide = typeof planningSides[number];

function ScopeConfirmation({ request, catalogue, evidence, disabled, onConfirm }: {
    request: PlanningScope;
    catalogue: Catalogue[];
    evidence: NonNullable<Review["source_evidence"]>;
    disabled: boolean;
    onConfirm: (scope: PlanningScope) => void;
}) {
    const [scope, setScope] = useState(request);
    const sources = planningSides.map(side => catalogue.find(source => source.canonical.id === request[side].canonical_id));
    const dateFields = sources.map(source => source?.schema_definition.fields.filter(field => field.data_type === "date") || []);
    const dateFor = (side: PlanningSide, index: number) =>
        scope[side].date_field || (dateFields[index].length === 1 ? dateFields[index][0].id : "");
    const [timeBasis, setTimeBasis] = useState(request.left.time_basis || request.right.time_basis || "");
    const firstDate = dateFor("left", 0);
    const secondDate = dateFor("right", 1);
    const commonBasis = timeBasis || (firstDate === secondDate ? firstDate : "");
    const updateSlot = (side: PlanningSide, change: Partial<PlanningScope["left"]>) =>
        setScope(previous => ({ ...previous, [side]: { ...previous[side], ...change } }));
    const needsPartial = planningSides.some((side, index) => {
        const slot = scope[side];
        const source = evidence.find(item => item.canonical_id === slot.canonical_id);
        return !!source?.excluded_rows || sources[index]?.canonical.quality_status === "PARTIAL" ||
            ["INCOMPLETE", "UNKNOWN"].includes(slot.completeness || "") ||
            (!!scope.period_start && !!slot.coverage_start && slot.coverage_start > scope.period_start) ||
            (!!scope.period_end && !!slot.coverage_end && slot.coverage_end < scope.period_end);
    });
    const slots = planningSides.map((side, index) => ({
        ...scope[side],
        date_field: dateFor(side, index),
        time_basis: scope[side].time_basis || commonBasis,
        currency_field: scope[side].currency_field ??
            sources[index]?.schema_definition.fields.find(field => field.id === "currency" && field.data_type === "string")?.id,
        coverage_start: scope[side].coverage_start || scope.period_start,
        coverage_end: scope[side].coverage_end || scope.period_end,
    }));
    const ready = scope.period_start && scope.period_end && scope.period_start < scope.period_end &&
        scope.timezone && commonBasis && sources.every(Boolean) && (!needsPartial || scope.allow_partial) &&
        slots.every((slot, index) => slot.role && slot.date_field && slot.snapshot_at && slot.completeness &&
            slot.coverage_start && slot.coverage_end && slot.coverage_start < slot.coverage_end &&
            !(slot.completeness === "CONFIRMED" && !!sources[index]?.canonical.excluded_source_rows));

    return <fieldset className="agent-form-grid">
        <legend>Thông tin cần xác nhận</legend>
        {!request.period_start && <label>Ngày đầu kỳ<input type="date" value={scope.period_start || ""} disabled={disabled}
            onChange={event => setScope({ ...scope, period_start: event.target.value })}/></label>}
        {!request.period_end && <label>Ngày sau cuối kỳ<input type="date" value={scope.period_end || ""} disabled={disabled}
            onChange={event => setScope({ ...scope, period_end: event.target.value })}/></label>}
        {!request.timezone && <label>Múi giờ đối soát<select value={scope.timezone || ""} disabled={disabled}
            onChange={event => setScope({ ...scope, timezone: event.target.value })}>
            <option value="">Chọn múi giờ</option><option value="Asia/Ho_Chi_Minh">Việt Nam</option><option value="UTC">UTC</option>
        </select></label>}
        {request.period_start && request.period_end && <p>Kỳ đối soát từ {request.period_start} đến trước {request.period_end}
            {request.timezone && ` · ${request.timezone}`}.</p>}
        {!request.left.time_basis && !request.right.time_basis && firstDate && secondDate && firstDate !== secondDate &&
            <label>Ý nghĩa chung của hai cột ngày<select value={timeBasis} disabled={disabled}
                onChange={event => setTimeBasis(event.target.value)}>
                <option value="">Chọn ý nghĩa ngày</option><option value="event_date">Ngày phát sinh</option>
                <option value="posting_date">Ngày hạch toán</option><option value="invoice_date">Ngày hóa đơn</option>
                <option value="settlement_date">Ngày quyết toán</option>
            </select></label>}
        {planningSides.map((side, index) => {
            const existing = request[side];
            const slot = scope[side];
            const name = sources[index]?.name || (index ? "Nguồn đối ứng" : "Nguồn tham chiếu");
            const excluded = !!sources[index]?.canonical.excluded_source_rows;
            const isComplete = existing.date_field && existing.time_basis && existing.coverage_start &&
                existing.coverage_end && existing.snapshot_at &&
                !(excluded && existing.completeness === "CONFIRMED") &&
                (existing.completeness === "CONFIRMED" || (request.allow_partial && existing.completeness));
            if (isComplete) return <p key={side}><strong>{name}</strong> · Đã có xác nhận phạm vi và thời điểm chốt.</p>;
            return <fieldset className="agent-form-grid" key={side}>
                <legend>{name}</legend>
                {!existing.date_field && dateFields[index].length === 1 && <p>Cột ngày nghiệp vụ · {dateFields[index][0].name}</p>}
                {!existing.date_field && dateFields[index].length !== 1 && <label>Cột ngày nghiệp vụ<select aria-label={`Cột ngày nghiệp vụ của ${name}`}
                    value={dateFor(side, index)} disabled={disabled} onChange={event => updateSlot(side, { date_field: event.target.value })}>
                    <option value="">Chọn cột ngày</option>{dateFields[index].map(field => <option value={field.id} key={field.id}>{field.name}</option>)}
                </select></label>}
                {!existing.coverage_start && <label>Phạm vi nguồn từ ngày<input type="date" value={slot.coverage_start || scope.period_start || ""}
                    disabled={disabled} onChange={event => updateSlot(side, { coverage_start: event.target.value })}/></label>}
                {!existing.coverage_end && <label>Phạm vi nguồn đến trước ngày<input type="date" value={slot.coverage_end || scope.period_end || ""}
                    disabled={disabled} onChange={event => updateSlot(side, { coverage_end: event.target.value })}/></label>}
                {!existing.snapshot_at && <label>Thời điểm nghiệp vụ chốt nguồn (UTC)<input type="datetime-local"
                    aria-label={`Thời điểm nghiệp vụ chốt nguồn ${name} (UTC)`} value={slot.snapshot_at?.slice(0, 16) || ""}
                    disabled={disabled} onChange={event => updateSlot(side, {
                        snapshot_at: event.target.value ? `${event.target.value}:00Z` : "",
                    })}/></label>}
                {(!existing.completeness || (existing.completeness === "UNKNOWN" && !request.allow_partial) ||
                    (excluded && existing.completeness === "CONFIRMED")) &&
                    <label>Mức độ đầy đủ<select aria-label={`Mức độ đầy đủ của ${name}`} value={slot.completeness || ""}
                        disabled={disabled} onChange={event => updateSlot(side, { completeness: event.target.value })}>
                        <option value="">Chọn mức độ đầy đủ</option>
                        {!excluded && <option value="CONFIRMED">Đã xác nhận đầy đủ trong phạm vi trên</option>}
                        <option value="INCOMPLETE">Biết nguồn còn thiếu</option>
                        <option value="UNKNOWN">Chưa có bằng chứng về độ đầy đủ</option>
                    </select></label>}
            </fieldset>;
        })}
        {needsPartial && !request.allow_partial && <label>
            <input type="checkbox" checked={!!scope.allow_partial} disabled={disabled}
                onChange={event => setScope({ ...scope, allow_partial: event.target.checked })}/>
            Đề xuất đối soát một phần trên dữ liệu dùng được.
        </label>}
        <button className="button secondary" type="button" disabled={disabled || !ready} onClick={() => onConfirm({
            ...scope, effective_from: scope.effective_from || scope.period_start,
            left: slots[0], right: slots[1],
        })}>Kiểm tra phạm vi và tìm khóa</button>
    </fieldset>;
}

function storedDraft(key: string, review: Review) {
    try {
        const saved = JSON.parse(sessionStorage.getItem(key) || "null");
        if (!saved || saved.base !== JSON.stringify([review.normalization_draft, review.plan, review.planning_request, review.suggestions])) return null;
        if (saved.draft && (!review.normalization_draft || typeof saved.draft.entity_kind !== "string" || typeof saved.draft.grain !== "string" || saved.draft.table_id !== review.resource_id ||
            !Array.isArray(saved.draft.fields) || saved.draft.fields.length !== review.normalization_draft.fields.length ||
            !saved.draft.fields.every((f: DraftField, i: number) => f && f.source_field === review.normalization_draft?.fields[i].source_field && f.target_id === review.normalization_draft.fields[i].target_id && typeof f.name === "string" && typeof f.data_type === "string"))) return null;
        if (saved.plan && (!saved.plan.left || !saved.plan.right || !Array.isArray(saved.plan.join_keys) || !Array.isArray(saved.plan.comparison_metrics) ||
            saved.plan.left.canonical_id !== review.planning_request?.left.canonical_id || saved.plan.right.canonical_id !== review.planning_request?.right.canonical_id)) return null;
        return saved as {draft: NormalizationDraft | null; plan: Plan | null; extraction: boolean};
    } catch { return null; }
}

export function ReviewCard({ review, workflow, canEdit, draftOwner, refresh, onReply, onBatchDraft, sharedFacts }: {
    review: Review;
    workflow: Workflow;
    canEdit: boolean;
    draftOwner: string;
    refresh: () => Promise<void>;
    onReply?: (workflowId:string,review:Review)=>void;
    onBatchDraft?: (id: string, payload: string | null) => void;
    sharedFacts?: SharedMappingFacts | null;
}) {
    const storageKey = `studio.review-draft.${draftOwner}.${workflow.id}.${review.id}.${review.nonce}.${review.fingerprint}`;
    const cached = useRef(storedDraft(storageKey, review)).current;
    const [draft, setDraft] = useState(cached?.draft ?? review.normalization_draft ?? null);
    const appliedSharedRevision=useRef(0);
    useEffect(() => {
        if (!sharedFacts || !canEdit || review.kind !== "MAPPING" || review.state !== "OPEN" ||
            sharedFacts.revision<=appliedSharedRevision.current ||
            !sharedFacts.reviewKeys.includes(`${review.id}:${review.nonce}:${review.fingerprint}`)) return;
        appliedSharedRevision.current=sharedFacts.revision;
        setDraft(previous => {
            if (!previous) return previous;
            const key = previous.fields.some(field=>field.business_key) ? "" : sharedFacts.business_key;
            return {
                ...previous,
                entity_kind: unknownFact(previous.entity_kind) && !unknownFact(sharedFacts.entity_kind) ? sharedFacts.entity_kind.trim() : previous.entity_kind,
                grain: unknownFact(previous.grain) && !unknownFact(sharedFacts.grain) ? sharedFacts.grain.trim() : previous.grain,
                fields: previous.fields.map(field => ({...field,
                    ...(key && field.data_type === "string" && field.name === key ? {business_key:true} : {}),
                    ...(field.data_type === "date" && !field.timezone && sharedFacts.timezone ? {timezone:sharedFacts.timezone} : {}),
                    ...(field.data_type === "decimal" ? {
                        amount_basis: field.amount_basis || sharedFacts.amount_basis || null,
                        semantic_metric: field.semantic_metric || (unknownFact(sharedFacts.semantic_metric) ? null : sharedFacts.semantic_metric.trim()),
                    } : {}),
                })),
            };
        });
    }, [sharedFacts, canEdit, review.id, review.nonce, review.fingerprint, review.kind, review.state]);
    const [plan, setPlan] = useState(cached?.plan ?? review.plan ?? null);
    const [assessment,setAssessment]=useState<MappingAssessment|null>(null);
    const [checking,setChecking]=useState(false);
    const [suggesting, setSuggesting] = useState(false);
    const [assessmentSignature,setAssessmentSignature]=useState('');
    const draftSignature=JSON.stringify(draft);
    useEffect(()=>{
      if(!draft)return;
      const controller=new AbortController();
      setChecking(true);
      const timer=setTimeout(()=>{
        void api<MappingAssessment>('/agent/mapping-preflight',{method:'POST',body:draftSignature,signal:controller.signal})
        .then(result=>{if(!controller.signal.aborted){setAssessment(result);setAssessmentSignature(draftSignature);setError('');}})
        .catch(err=>{if(!controller.signal.aborted)setError(err instanceof Error?err.message:'Không kiểm tra được đề xuất.');})
        .finally(()=>{if(!controller.signal.aborted)setChecking(false);});
      },250);
      return()=>{clearTimeout(timer);controller.abort();};
    },[draftSignature]);
    const [catalogue,setCatalogue]=useState<Catalogue[]>([]);
    const submitting = useRef(false);
    const [extraction, setExtraction] = useState(cached?.extraction || false);
    const [invalidRowsReviewed, setInvalidRowsReviewed] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [expired, setExpired] = useState(Date.now() >= Date.parse(review.expires_at));
    const [replyOpen, setReplyOpen] = useState(false);
    const replyKey = `studio.inline-review-reply.${draftOwner}.${workflow.id}.${review.id}`;
    const [replyText, setReplyText] = useState(() => {try{return sessionStorage.getItem(replyKey) || "";}catch{return "";}});
    const replyPending = useRef<{body: string; key: string} | null>((() => {try{
        const saved=JSON.parse(sessionStorage.getItem(`${replyKey}.pending`)||"null");
        return saved&&typeof saved.body==="string"&&typeof saved.key==="string"?saved:null;
    }catch{return null;}})());
    useEffect(() => {
        let timer: ReturnType<typeof setTimeout>;
        function tick() {
            const remaining=Date.parse(review.expires_at)-Date.now();
            if(remaining<=0)setExpired(true);
            else timer=setTimeout(tick,Math.min(remaining+20,2147483647));
        }
        tick();
        return () => clearTimeout(timer);
    }, [review.expires_at]);
    useEffect(() => {
        try { sessionStorage.setItem(storageKey, JSON.stringify({
            base: JSON.stringify([review.normalization_draft, review.plan, review.planning_request, review.suggestions]),
            draft, plan, extraction,
        })); } catch { /* Server save stays available when browser storage is full. */ }
    }, [storageKey, draft, plan, extraction]);
    const alive = useRef(true);
    const pending = useRef<{
        body: string;
        key: string;
    } | null>(null);
    useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
    useEffect(() => {
        if (review.kind !== "RECONCILIATION")
            return;
        const controller = new AbortController();
        const sources=review.plan || review.planning_request;
        const selected=sources ? new URLSearchParams([
            ["canonical_ids",sources.left.canonical_id],["canonical_ids",sources.right.canonical_id],
        ]).toString() : "";
        void apiPages<Catalogue>(`/projects/${workflow.context.project_id}/canonical-catalogue${selected ? `?${selected}` : ""}`, { signal: controller.signal })
            .then(data => { if (!controller.signal.aborted){
            setCatalogue(data);if(!review.plan&&!cached?.plan)setPlan(proposedPlan(review, data));} })
            .catch(err => { if (!controller.signal.aborted)
            setError(String(err)); });
        return () => controller.abort();
    }, [review.id, review.nonce]);
    const disabled = busy || suggesting || !canEdit || expired || !!review.pending_reply_job_id;
    const replyDisabled = disabled || workflow.state !== "WAITING_REVIEW";
    const changed = JSON.stringify(draft) !== JSON.stringify(review.normalization_draft ?? null) ||
        JSON.stringify(plan) !== JSON.stringify(review.plan || proposedPlan(review, catalogue));
    async function suggestMapping() {
        setSuggesting(true);
        setError("");
        try {
            const next = await api<MappingAssessment>("/agent/mapping-preflight?suggest=true", {method: "POST", body: draftSignature});
            if (alive.current) setDraft(next.draft);
        } catch (err) {
            if (alive.current) setError(err instanceof Error ? err.message : "Không lấy được đề xuất mới.");
        } finally {
            if (alive.current) setSuggesting(false);
        }
    }
    function preserveLocal(next: Review) {
        const key=`studio.review-draft.${draftOwner}.${workflow.id}.${next.id}.${next.nonce}.${next.fingerprint}`;
        try { sessionStorage.setItem(key,JSON.stringify({
            base:JSON.stringify([next.normalization_draft,next.plan,next.planning_request,next.suggestions]),
            draft,plan,extraction,
        })); } catch { /* server draft remains the durable source */ }
    }
    async function savePreview() {
        const base = {review_id: review.id, nonce: review.nonce, fingerprint: review.fingerprint};
        if (review.kind === "CLARIFICATION") return review;
        if (!changed) return review;
        const facts = plan && {
            ...Object.fromEntries(["period_start", "period_end", "timezone", "effective_from", "effective_to", "allow_partial"].map(k => {const value=plan[k as keyof Plan];return [k,value===""?null:value??null];})),
            ...Object.fromEntries((["left", "right"] as const).map(side => [side, Object.fromEntries(Object.entries(plan[side]).map(([k,v]) => [k, v === "" ? null : v]))])),
        };
        const body = {...base, ...(draft ? {draft} : ready && plan ? {plan} : {planning_request: facts || review.planning_request})};
        const saved = await api<Workflow>(`/agent/workflows/${workflow.id}/draft`, {method: "POST", body: JSON.stringify(body)});
        try { sessionStorage.removeItem(storageKey); } catch { /* server draft was saved */ }
        const next = saved.detail.reviews.find(r => r.id === review.id);
        if (!next) throw new Error("Không tìm thấy bản nháp vừa lưu.");
        preserveLocal(next);
        return next;
    }
    async function saveOrRenew(renew = false) {
        if (busy || !canEdit || review.pending_reply_job_id) return;
        setBusy(true); setError("");
        try {
            if (renew) {
                const row=await api<Workflow>(`/agent/workflows/${workflow.id}/renew-review`, {method: "POST", body: JSON.stringify({review_id: review.id, nonce: review.nonce, fingerprint: review.fingerprint})});
                const next=row.detail.reviews.find(r=>r.id===review.id);if(next)preserveLocal(next);
            }
            else await savePreview();
            await refresh();
        } catch (err) { setError(err instanceof Error ? err.message : "Không lưu được bản nháp."); }
        finally { setBusy(false); }
    }
    async function requestReply() {
        if (replyDisabled) return;
        if (!onReply) { setReplyOpen(true); return; }
        setBusy(true); setError("");
        try { const next = await savePreview(); onReply(workflow.id, next); await refresh(); }
        catch (err) { setError(err instanceof Error ? err.message : "Không lưu được bản nháp."); }
        finally { setBusy(false); }
    }
    async function sendInlineReply() {
        if (replyDisabled || !replyText.trim()) return;
        setBusy(true); setError("");
        try {
            const next = replyPending.current ? review : await savePreview();
            const body = JSON.stringify({review_id: next.id, nonce: next.nonce, fingerprint: next.fingerprint,
                text: replyText.trim(), ...(workflow.detail.model_choice ? {model_choice: workflow.detail.model_choice} : {})});
            if (!replyPending.current) replyPending.current = {body, key: crypto.randomUUID()};
            try {sessionStorage.setItem(`${replyKey}.pending`,JSON.stringify(replyPending.current));}catch{/* memory key remains stable */}
            await api(`/agent/workflows/${workflow.id}/replies`, {method: "POST", body: replyPending.current.body, headers: {"Idempotency-Key": replyPending.current.key}});
            replyPending.current = null; setReplyText("");try{sessionStorage.removeItem(replyKey);sessionStorage.removeItem(`${replyKey}.pending`);}catch{/* job is durably accepted */} await refresh();
        } catch (err) { setError(err instanceof Error ? err.message : "Không gửi được câu trả lời."); }
        finally { setBusy(false); }
    }
    const sourceName=(id:string)=>catalogue.find(c=>c.canonical.id===id)?.name||"Nguồn đã chọn";
    const planSources = plan ? [plan.left.canonical_id, plan.right.canonical_id]
        .map(id => catalogue.find(item => item.canonical.id === id)) : [];
    const partialSources = planSources.filter(item => item?.canonical.quality_status === "PARTIAL");
    const scope = review.planning_request;
    const needsScope = scope && scope.left.role && scope.right.role && (review.scope_check_pending ||
        !scope.period_start || !scope.period_end || !scope.timezone || !scope.effective_from ||
        [scope.left, scope.right].some(slot => !slot.date_field || !slot.time_basis || !slot.coverage_start ||
            !slot.coverage_end || !slot.snapshot_at || !slot.completeness ||
            (slot.completeness === "UNKNOWN" && !scope.allow_partial))
    );
    async function checkScope(planningRequest: PlanningScope) {
        if (disabled || submitting.current) return;
        submitting.current = true;
        setBusy(true); setError("");
        try {
            await api(`/agent/workflows/${workflow.id}/draft`, {method: "POST", body: JSON.stringify({
                review_id: review.id, nonce: review.nonce, fingerprint: review.fingerprint,
                planning_request: planningRequest, check_planning_scope: true,
            })});
            await refresh();
        } catch (err) { setError(err instanceof Error ? err.message : "Không kiểm tra được phạm vi."); }
        finally { submitting.current = false; if (alive.current) setBusy(false); }
    }
    const fieldName=(id:string,field:string)=>catalogue.find(c=>c.canonical.id===id)?.schema_definition.fields.find(f=>f.id===field)?.name||field;
    async function action(intent = review.reply_intent) {
        if (submitting.current || disabled) return;
        submitting.current = true;
        setBusy(true);
        setError("");
        try {
            const decision = review.kind === "MAPPING" ? { type: "MAPPING", draft, extraction_reviewed: extraction } :
                review.kind === "RECONCILIATION" ? { type: "RECONCILIATION", plan, invalid_rows_reviewed: invalidRowsReviewed } : { type: "CLARIFICATION", intent };
            const body = JSON.stringify({ review_id: review.id, nonce: review.nonce,
                fingerprint: review.fingerprint, decision });
            if (pending.current?.body !== body)
                pending.current = { body, key: crypto.randomUUID() };
            await api(`/agent/workflows/${workflow.id}/decisions`, { method: "POST",
                headers: { "Idempotency-Key": pending.current.key }, body });
            if (alive.current) {
                pending.current = null;
                await refresh();
            }
        }
        catch (err) {
            if (alive.current)
                setError(err instanceof Error ? err.message : "Không lưu được quyết định.");
        }
        finally {
            submitting.current = false;
            if (alive.current)
                setBusy(false);
        }
    }
    const ready = review.kind === "MAPPING" ? !!assessment?.preflight_ready && assessmentSignature===draftSignature && !checking && (review.extraction_review_required!==true||extraction) :
        review.kind === "RECONCILIATION" ? !!plan?.period_start && !!plan.period_end && !!plan.timezone && !!plan.effective_from && planSources.every(Boolean) && [plan.left, plan.right].every(s => s.date_field && s.time_basis && s.coverage_start && s.coverage_end && s.snapshot_at && s.completeness) : !!review.reply_intent;
    const batchPayload = review.kind === "MAPPING" && ready && !disabled ? JSON.stringify({
        review_id: review.id, nonce: review.nonce, fingerprint: review.fingerprint,
        decision: {type: "MAPPING", draft, extraction_reviewed: extraction},
    }) : null;
    useEffect(() => {
        onBatchDraft?.(review.id, batchPayload);
        return () => onBatchDraft?.(review.id, null);
    }, [batchPayload, onBatchDraft, review.id]);
    if (review.kind === "CLARIFICATION") return <section className="agent-clarification" aria-label="Câu hỏi bổ sung">
      <div className="review-heading"><h4>{review.question}</h4></div>
      {error && <Notice tone="error">{error}</Notice>}
      {review.reply_questions.filter(q=>q!==review.question).map(q=><p key={q}>{q}</p>)}
      <div className="clarification-options">{review.options?.map(option=><button className="button secondary" key={option.id} disabled={disabled} onClick={()=>void action(option.intent)}>{option.label}</button>)}</div>
      {review.reply_intent && !review.options?.length && <button className="button secondary" disabled={disabled} onClick={()=>void action()}>Tiếp tục yêu cầu này</button>}
      {expired && <Notice>Thẻ đã hết thời hạn.<button type="button" disabled={busy || !canEdit || !!review.pending_reply_job_id} onClick={()=>void saveOrRenew(true)}>Mở lại thẻ xác nhận</button></Notice>}
      <button className="text-button" disabled={replyDisabled} onClick={()=>void requestReply()}>Trả lời bằng tiếng Việt</button>
      {review.pending_reply_job_id && <p role="status"><Spinner/> Đang đọc câu trả lời của bạn…</p>}
    </section>;
    return <section className={draft ? "agent-review smart-mapping-review" : "agent-review"} aria-label="Quyết định cần xác nhận">
    <header className="review-heading">
      <h4>{draft ? review.resource_label || "Đề xuất ghép cột" : review.question}</h4>
      {draft ? assessment && <p className="muted">{assessment.source_rows.toLocaleString("vi-VN")} dòng · {draft.fields.length} cột · {assessment.verified_fields} trường đã kiểm tra
        {!!assessment.pending_fields && ` · ${assessment.pending_fields} trường cần xem`}</p> : <>
        {review.resource_label && <p><strong>{review.resource_label}</strong></p>}
        <p>{review.reason}</p>
      </>}
    </header>
    {error && <Notice tone="error">{error}</Notice>}{review.reply_questions.map(q => <Notice key={q}>{q}</Notice>)}
    {draft && <>
      <SmartMapping draft={draft} assessment={assessment} onChange={setDraft} disabled={disabled}/>
      {!assessment && checking && <p role="status"><Spinner/> Đang kiểm tra dữ liệu…</p>}
      {assessment && assessmentSignature === draftSignature && <>
        {assessment.preflight_ready && !!assessment.predicted_invalid_rows &&
            <p className="smart-mapping-warning">{assessment.predicted_invalid_rows.toLocaleString("vi-VN")} dòng cần xử lý sau chuẩn hóa.</p>}
        {assessment.checks.filter(check => check.state === "BLOCKED").map(check =>
            <Notice key={check.field_id} tone="warning">{check.name} · {check.messages.join(" ")}</Notice>)}
        <details><summary>Kiểm tra cột và bằng chứng</summary>
          {assessment.questions.length > 0 && <ul>{assessment.questions.map(q => <li key={q}>{q}</li>)}</ul>}
          <ul>{assessment.checks.map(check => <li key={check.field_id}><strong>{check.name}</strong>
              {check.messages.map(message => <p key={message}>{message}</p>)}
              {Object.entries(check.error_counts).length > 0 && <p>{Object.entries(check.error_counts)
                  .map(([code,count]) => `${qualityText[code] || errors[code] || code} (${count})`).join(" · ")}</p>}
          </li>)}</ul>
          {!!assessment.related_keys?.length && <><h5>Quan hệ tiềm năng giữa các nguồn</h5>
              {assessment.related_keys.map((r,i) => <p key={`${r.table_id}:${i}`}>{r.source_name} · {r.fields.join(" + ")}
                  {" · "}{r.shared_keys} khóa chung · {r.left_duplicate_rows}/{r.right_duplicate_rows} dòng lặp · {r.missing_key_rows} dòng thiếu khóa.</p>)}</>}
        </details>
      </>}
      <details className="agent-review-editor"><summary>Xem và chỉnh các lựa chọn</summary>
        <button type="button" className="text-button" disabled={disabled || suggesting} onClick={() => void suggestMapping()}>
            {suggesting ? "Đang cập nhật đề xuất…" : "Lấy lại đề xuất từ dữ liệu"}
        </button>
        <MappingReview draft={draft} disabled={disabled} onChange={setDraft}/>
      </details>
    </>}
    {review.kind === "RECONCILIATION" && !!review.planning_candidates?.length && <fieldset>
      <legend>Phương án liên kết đã kiểm tra</legend>
      {review.planning_candidates.map(candidate => <label key={candidate.id}>
        <input type="radio" name={`planning-candidate-${review.id}`} disabled={disabled}
          checked={!!plan && JSON.stringify(plan.join_keys) === JSON.stringify(candidate.plan.join_keys)}
          onChange={() => setPlan(candidate.plan)}/>
        {candidate.plan.join_keys.map(key => `${fieldName(candidate.plan.left.canonical_id,key.left)} ↔ ${fieldName(candidate.plan.right.canonical_id,key.right)}`).join(', ')}
        {` · ${candidate.overlap} khóa có đối ứng (${candidate.left_distinct_keys} khóa nguồn A, ${candidate.right_distinct_keys} khóa nguồn B) · ${label(candidate.plan.cardinality)}`}
        {(candidate.left_rows > candidate.left_distinct_keys || candidate.right_rows > candidate.right_distinct_keys) &&
          " · Các nhóm trùng khóa được đưa vào rà soát."}
      </label>)}
    </fieldset>}
    {review.kind === "RECONCILIATION" && !!review.source_evidence?.length && <div className="review-source-evidence">
      <h4>Dữ kiện đã kiểm tra</h4>
      {review.source_evidence.map(source => <section key={source.canonical_id}>
        <h5>{source.name}</h5>
        <p>{source.valid_rows.toLocaleString("vi-VN")} dòng dùng được trong bản chuẩn hóa
          {!!source.invalid_rows && <> · {source.invalid_rows} dòng chưa hợp lệ</>}
          {!!source.excluded_rows && <> · {source.excluded_rows} dòng đã loại</>}.</p>
        {source.excluded_amounts.map(item => <p key={item.field + item.currency}>
          Số tiền đã loại {item.amount} {item.currency} · {fieldName(source.canonical_id, item.field)}
        </p>)}
        {source.excluded_amounts_unavailable && <p>Chưa xác định được một phần số tiền đã loại.</p>}
        {source.exclusion_reasons?.map(reason => <p key={reason}>Lý do loại dòng · {reason}</p>)}
        {source.observed_dates.map(range => <p key={range.field}>
          {fieldName(source.canonical_id, range.field)} quan sát được từ {range.first} đến {range.last} ({source.observation_timezone}).
        </p>)}
        <details><summary>Phiên bản nguồn</summary>
          <p>Tệp tải lần đầu {source.uploaded_at
            ? new Date(source.uploaded_at).toLocaleString("vi-VN", { timeZone: "UTC" }) + " UTC"
            : "chưa có thời điểm lưu"} · Phiên bản nguồn {source.dataset_revision} · Ánh xạ {source.mapping_revision}
            {source.quality_revision > 0 && <> · Lần xử lý chất lượng {source.quality_revision}</>}</p>
        </details>
      </section>)}
      {needsScope && <p>Khoảng ngày quan sát được giúp kiểm tra kỳ. Thời điểm chốt và mức độ đầy đủ cần xác nhận theo nghiệp vụ.</p>}
    </div>}
    {plan && <>
      <dl className="decision-facts">
        <div><dt>Nguồn A</dt><dd>{sourceName(plan.left.canonical_id)}</dd></div>
        <div><dt>Nguồn B</dt><dd>{sourceName(plan.right.canonical_id)}</dd></div>
        <div><dt>Kỳ đối soát</dt><dd>{plan.period_start || "Chưa chọn"} đến trước {plan.period_end || "ngày chưa chọn"} · {plan.timezone || "chưa rõ múi giờ"}</dd></div>
        <div><dt>Hiệu lực của quy tắc</dt><dd>{plan.effective_from || "Chưa chọn"}{plan.effective_to ? ` đến trước ${plan.effective_to}` : " · chưa đặt ngày kết thúc"}</dd></div>
        <div><dt>Đơn vị so sánh</dt><dd>{plan.comparison_grain} · {label(plan.cardinality)} · {label(plan.aggregation)}</dd></div>
        <div><dt>Khóa liên kết</dt><dd>{plan.join_keys.map(k => `${fieldName(plan.left.canonical_id, k.left)} ↔ ${fieldName(plan.right.canonical_id, k.right)}`).join(", ")}</dd></div>
      </dl>
      <div className="review-metrics"><strong>Chỉ tiêu so sánh</strong>
        {plan.comparison_metrics.map(m => <p key={m.metric_id}>{fieldName(plan.left.canonical_id, m.left)} ↔ {fieldName(plan.right.canonical_id, m.right)} · {m.amount_basis} · {m.currency} · sai số {m.absolute_tolerance}</p>)}
      </div>
      <details><summary>Phiên bản và độ phủ dữ liệu</summary>
        {([plan.left, plan.right] as const).map((slot, index) => <p key={index}>
          Nguồn {index === 0 ? "A" : "B"} · {slot.coverage_start || "Chưa xác định"} đến trước {slot.coverage_end || "ngày chưa xác định"} · {slot.completeness ? label(slot.completeness) : "Chưa xác định độ phủ"}<br />
          Bản chuẩn hóa {slot.canonical_id}
        </p>)}
      </details>
      <details className="agent-review-editor"><summary>Kiểm tra phạm vi và chỉnh quy tắc</summary><PlanReview plan={plan} disabled={disabled} onChange={setPlan}/></details>
    </>}
    {review.kind === "RECONCILIATION" && !plan && scope && needsScope && <ScopeConfirmation
        request={scope} catalogue={catalogue} evidence={review.source_evidence || []}
        disabled={disabled} onConfirm={value=>void checkScope(value)}/>}
    {review.kind === "RECONCILIATION" && !plan && !needsScope && !review.planning_candidates?.length && <Notice>
      Cần xác nhận khóa, chỉ tiêu hoặc phạm vi trước khi chạy.
      {" "}<a className="text-button" href={`#${new URLSearchParams({page: "reconcile", project: workflow.context.project_id})}`}>
        Mở Đối soát để thiết lập quy tắc
      </a>
    </Notice>}
    {expired && <Notice><p>Thẻ đã hết thời hạn. Nếu nguồn còn nguyên, bạn có thể mở lại để tiếp tục.</p><button type="button" className="text-button" disabled={busy || !canEdit || !!review.pending_reply_job_id} onClick={()=>void saveOrRenew(true)}>Mở lại thẻ xác nhận</button></Notice>}
    <div className="review-secondary-actions">
      <button className="text-button" disabled={replyDisabled} onClick={()=>void requestReply()}>Bổ sung bằng tiếng Việt</button>
      <button type="button" className="text-button" disabled={disabled || !changed} onClick={()=>void saveOrRenew()}>Lưu bản nháp</button>
    </div>
    {replyOpen && <form onSubmit={e=>{e.preventDefault();void sendInlineReply();}}><label>Câu trả lời cho thẻ này<textarea value={replyText} disabled={replyDisabled || !!replyPending.current} maxLength={2000} onChange={e=>{setReplyText(e.target.value);try{sessionStorage.setItem(replyKey,e.target.value);}catch{/* optional local recovery */}}}/></label><button type="submit" className="button secondary" disabled={replyDisabled || !replyText.trim()}>Gửi câu trả lời để xem trước</button></form>}
    {review.pending_reply_job_id && <p role="status">Đang đọc câu trả lời của bạn…</p>}
    {draft && review.extraction_review_required===true && <label><input type="checkbox" checked={extraction} disabled={disabled} onChange={e => setExtraction(e.target.checked)}/>Tôi đã kiểm tra cảnh báo và vùng bảng nguồn.</label>}
    {!ready && !draft && <p className="muted">Mở phần chỉnh sửa hoặc bổ sung bằng tiếng Việt để hoàn tất các điều kiện còn thiếu.</p>}
    {partialSources.length > 0 && <Notice>
      <p>Dòng lỗi chuẩn hóa đã được tách riêng trong {partialSources.map(source => `${source?.name} (${source?.canonical.invalid_count} dòng)`).join(", ")}.</p>
      {partialSources.map(source => !!source?.canonical.excluded_source_rows &&
        <p key={source.canonical.id}>{source.name} có {source.canonical.excluded_source_rows} dòng nguồn đã loại.</p>)}
      <label><input type="checkbox" checked={invalidRowsReviewed} disabled={disabled} onChange={event => setInvalidRowsReviewed(event.target.checked)}/>
        {partialSources.some(source => source?.canonical.excluded_source_rows)
          ? "Tôi đã xem các dòng còn lỗi hoặc đã loại và xác nhận đối soát phần dữ liệu hợp lệ."
          : "Tôi đã kiểm tra dòng lỗi và xác nhận đối soát phần dữ liệu hợp lệ."}
      </label>
    </Notice>}
    <footer className="review-approval">
      {review.kind === "RECONCILIATION" && <p>Khi duyệt, hệ thống lưu quy tắc và bắt đầu đối soát trong phạm vi trên.</p>}
      <button className="button primary" disabled={disabled || !ready || (partialSources.length > 0 && !invalidRowsReviewed)} onClick={() => void action()}>{review.kind === "MAPPING" ? "Duyệt cách ghép cột và chuẩn hóa" : "Duyệt quy tắc và đối soát"}</button>
    </footer>
  </section>;
}
