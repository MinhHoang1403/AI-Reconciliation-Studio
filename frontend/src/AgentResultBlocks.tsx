import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { AriaComponent, GridComponent, TooltipComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import { api } from "./api";
import { Badge, DataTable, formatDecimal, Modal, Notice, sourceDisplayName, Spinner } from "./components";
import { DataQualityPanel } from "./DataQualityPanel";
import { FinancialSummary } from "./FinancialSummary";
import { label } from "./reconciliationTypes";
import {statusText} from "./types";
import type { AgentBlock, Chart, Query, QueryResult, SourceStatusLine } from "./agentTypes";
import type { AssistantContext, Suggestion } from "./assistantTypes";
import type { ColumnDef } from "@tanstack/react-table";
echarts.use([BarChart, AriaComponent, GridComponent, TooltipComponent, SVGRenderer]);
type SourceRef = {source_table_id:string;row:number;sheet:string};
const transformLabels:Record<string,string>={cast_string_preserve:"Giữ nguyên văn bản và mã",parse_decimal:"Đọc số tiền theo định dạng đã duyệt",parse_date:"Đọc ngày hoặc thời điểm theo múi giờ đã duyệt",parse_calendar_date:"Giữ nguyên ngày lịch",parse_offset_timestamp:"Chuẩn hóa thời điểm có offset về UTC",trim_if_approved:"Bỏ khoảng trắng theo quy tắc đã duyệt",normalize_enum:"Chuẩn hóa trạng thái theo quy tắc đã duyệt",coalesce_with_rule:"Chọn giá trị theo quy tắc đã duyệt",add_fields:"Cộng trường theo quy tắc đã duyệt",subtract_fields:"Trừ trường theo quy tắc đã duyệt",aggregate_by:"Gom nhóm theo quy tắc đã duyệt"};
const queryLabels:Record<string,string>={linkage_state:"Liên kết",comparison_state:"Kết quả so sánh",left_member_count:"Số dòng nguồn A",right_member_count:"Số dòng nguồn B",left_amount:"Số tiền nguồn A",right_amount:"Số tiền nguồn B",delta:"Chênh lệch có dấu",absolute_variance:"Chênh lệch tuyệt đối",tolerance:"Sai số cho phép",currency:"Tiền tệ",unit:"Đơn vị",type:"Loại ngoại lệ",state:"Xử lý ngoại lệ",notes:"Ghi chú"};
const comparisonMoney = ["left_amount", "right_amount", "delta", "absolute_variance", "tolerance"];
const countFields = ["left_member_count", "right_member_count"];
const localDay = (value: string) => value.split("-").reverse().join("/");
const localCount = (value: number) => value.toLocaleString("vi-VN");
function observedDays(first: string, last: string): string {
    if (first === last) return localDay(first);
    if (first.slice(0, 7) === last.slice(0, 7)) return `${first.slice(8)}–${localDay(last)}`;
    return `${localDay(first)} đến ${localDay(last)}`;
}
const coverageNote = "Dữ liệu đã được kiểm tra trong phạm vi quan sát. Độ đầy đủ của kỳ chưa được xác nhận.";
const evidenceNote = "Bằng chứng hiển thị có giới hạn. Bạn có thể xem dòng nguồn trong chi tiết.";
function QueryTable({ initial, workflowId, selection, title, showResultHints }: {
    initial: QueryResult;
    workflowId?: string;
    selection?: Query | null;
    title?: string;
    showResultHints: boolean;
}) {
    const [data, setData] = useState(initial);
    const [busy, setBusy] = useState(false);
    const [expanded, setExpanded] = useState(false);
    const expandTrigger = useRef<HTMLButtonElement>(null);
    const evidenceTrigger = useRef<HTMLElement | null>(null);
    const [error, setError] = useState("");
    const [source, setSource] = useState<Record<string, unknown>[] | null>(null);
    const [sourceRefs,setSourceRefs]=useState<SourceRef[]>([]);
    const [sourceIndex,setSourceIndex]=useState(0);
    const restoreSelection = selection?.source_id===initial.source_id &&
        JSON.stringify({...selection,offset:0,sort:[]})===JSON.stringify({...initial.query,offset:0,sort:[]}) &&
        (selection.offset!==initial.query.offset || JSON.stringify(selection.sort)!==JSON.stringify(initial.query.sort));
    const [restoring,setRestoring]=useState(!!restoreSelection);
    const scope = useRef(0);
    const alive = useRef(true);
    useEffect(() => { alive.current = true; return () => { alive.current = false; scope.current++; }; }, []);
    async function page(offset: number, sort = data.query.sort) {
        const seq = ++scope.current;
        setBusy(true);
        setError("");
        try {
            const next = await api<QueryResult>(workflowId?`/agent/workflows/${workflowId}/query-pages`:"/agent/queries", { method: "POST",
                body: JSON.stringify({ ...data.query, offset, sort }) });
            if (alive.current && seq === scope.current)
                setData(next);
        }
        catch (err) {
            if (alive.current && seq === scope.current)
                setError(String(err));
        }
        finally {
            if (alive.current && seq === scope.current)
                setBusy(false);
        }
    }
    async function evidence(record: Record<string, unknown>, index=0) {
        const refs = record.source_provenance as SourceRef[] | undefined;
        const ref = refs?.[index];
        if (!ref)
            return;
        const seq = ++scope.current;
        setBusy(true);
        setError("");
        try {
            const result = await api<{
                rows: Record<string, unknown>[];
            }>("/agent/source-rows", { method: "POST",
                body: JSON.stringify({ project_id: data.query.project_id, table_id: ref.source_table_id, row: ref.row }) });
            if (alive.current && seq === scope.current)
                {setSource(result.rows);setSourceRefs(refs||[]);setSourceIndex(index);}
        }
        catch (err) {
            if (alive.current && seq === scope.current)
                setError(String(err));
        }
        finally {
            if (alive.current && seq === scope.current)
                setBusy(false);
        }
    }
    useEffect(()=>{
        if(restoreSelection && selection) void page(selection.offset,selection.sort).finally(()=>{if(alive.current)setRestoring(false);});
    },[]);
    if(restoring)return <Spinner/>;
    const visibleFields=data.fields.filter(field=>!['group_id','case_id','canonical_record_id','metric_id'].includes(field));
    const groupKey=data.query.source_kind==='VERIFIED_RUN'&&data.rows.some(row=>row.business_key!=null);
    const grouped = (data.query.group_by?.length || 0) > 0 || (data.query.aggregations?.length || 0) > 0;
    const previewRows = data.rows.slice(0, 10);
    const aggregate = data.query.aggregations[0];
    const scopeEvidence = data.source_evidence;
    const countOnly = !data.query.group_by?.length && data.query.aggregations?.length === 1 && ["count", "count_distinct"].includes(aggregate.op);
    const singleAmount = scopeEvidence?.measure && !data.query.group_by.length && data.query.aggregations.length === 1 && ["sum_decimal", "min", "max"].includes(aggregate.op);
    const amount = singleAmount ? data.rows[0]?.[data.fields[0]] : undefined;
    const measure = scopeEvidence?.measure;
    const metric = measure && (label(measure.semantic_metric) === measure.semantic_metric ? measure.name : label(measure.semantic_metric));
    const sourceName = scopeEvidence?.source_name || title;
    const sourceTitle = sourceName && sourceDisplayName(sourceName);
    const moneyFields = new Set([
        ...Object.keys(data.measure_units ?? {}),
        ...(measure ? [measure.field_id] : []),
        ...(data.query.source_kind === "VERIFIED_RUN" ? comparisonMoney : []),
    ]);
    const numericQueryFields = new Set([...countFields, ...moneyFields]);
    const showEvidenceHint = showResultHints && !initial.evidence_complete;
    const countUnit = aggregate?.op === "count_distinct" ? "mã đơn duy nhất" : data.query.source_kind === "VERIFIED_RUN" ? "nhóm giao dịch" : "dòng dữ liệu";
    const count = countOnly && data.rows[0] ? data.rows[0][data.fields[0]] : null;
    const columns: ColumnDef<Record<string, unknown>>[] = [{id:'position',header:'Vị trí trong trang',cell:info=>info.row.index+1},...(groupKey?[{id:'business_key',accessorKey:'business_key',header:'Khóa giao dịch'}]:[]),...visibleFields.map<ColumnDef<Record<string, unknown>>>(field => ({ id: field, accessorKey: field,
        header: () => <button className="text-button" disabled={busy} onClick={() => void page(0, [{ field_id: field, descending: !data.query.sort.find(s => s.field_id === field)?.descending }])}>{data.field_labels?.[field] || (countOnly ? `Số ${countUnit}` : queryLabels[field] || field)} ↕</button>,
        cell: info => info.getValue() == null ? "—" :
          ['VERIFIED_RUN','EXCEPTIONS'].includes(data.query.source_kind)&&['linkage_state','comparison_state','state','type'].includes(field)?label(String(info.getValue())):
          moneyFields.has(field) ? formatDecimal(String(info.getValue())) : String(info.getValue()) })), {
        id: "evidence", header: () => <span>Nguồn</span>, cell: info => <button className="text-button" disabled={busy || !Array.isArray(info.row.original.source_provenance)} onClick={event => { evidenceTrigger.current = event.currentTarget; void evidence(info.row.original); }}>Xem dòng gốc</button>,
    }];
    const pagination = <div className="agent-pagination"><button className="button secondary" disabled={busy || !data.offset} onClick={() => void page(Math.max(0, data.offset - data.limit))}>Trước</button>
      <span>Trang {Math.floor(data.offset / data.limit) + 1} · {data.rows.length} dòng trong trang</span>
      <button className="button secondary" disabled={busy || !data.truncated} onClick={() => void page(data.offset + data.limit)}>Tiếp</button>{busy && <Spinner />}</div>;
    return <section className="agent-table" aria-label="Kết quả truy vấn">
    {singleAmount && metric && measure && (amount == null
      ? <p className="agent-answer-lead">Chưa có số tiền phù hợp cho chỉ tiêu {metric} của {sourceTitle}.</p>
      : <p className="agent-answer-lead">{aggregate.op === "sum_decimal" ? "Tổng" : aggregate.op === "min" ? "Mức thấp nhất của" : "Mức cao nhất của"} {metric.charAt(0).toLocaleLowerCase("vi-VN") + metric.slice(1)} của {sourceTitle} là <strong>{formatDecimal(String(amount))} {measure.currency}</strong>.</p>)}
    {!singleAmount && title && <h4>{scopeEvidence ? sourceTitle : title}</h4>}
    {countOnly && count != null && <p className="agent-answer-lead">Có <strong>{typeof count === "number" ? localCount(count) : String(count)} {countUnit}</strong>{sourceTitle ? ` trong ${sourceTitle}` : ""} phù hợp với điều kiện đã chọn.</p>}
    {!countOnly && !singleAmount && <p><strong>{data.total_count.toLocaleString("vi-VN")} {grouped ? "nhóm kết quả" : "dòng dữ liệu"}</strong>{data.total_count === 0 ? ". Chưa tìm thấy dữ liệu phù hợp với điều kiện bạn chọn." : ". Bạn có thể xem dữ liệu và mở từng dòng gốc bên dưới."}</p>}
    {scopeEvidence && <p className="agent-answer-context">{localCount(scopeEvidence.counted_rows)} dòng được tính{scopeEvidence.observed_first && scopeEvidence.observed_last ? ` trong phạm vi ${observedDays(scopeEvidence.observed_first, scopeEvidence.observed_last)}` : ""}. {scopeEvidence.invalid_rows === 0 && scopeEvidence.excluded_rows === 0
      ? "Không có dòng lỗi hoặc dòng bị loại theo quyết định."
      : `Nguồn có ${localCount(scopeEvidence.invalid_rows)} dòng lỗi và ${localCount(scopeEvidence.excluded_rows)} dòng bị loại theo quyết định.`}</p>}
    {!countOnly && !singleAmount && data.rows.length > 0 && <p className="muted">Đang xem {previewRows.length} dòng trong trang {Math.floor(data.offset / data.limit) + 1}{data.rows.length > 10 ? `; trang này có ${data.rows.length} dòng.` : "."}</p>}
    {data.query.source_kind === "RAW_PREVIEW" && <p>Đây là dữ liệu gốc đã đọc từ tệp. Ý nghĩa các cột chưa được xác nhận; dữ liệu chưa được chuẩn hóa.</p>}
    {data.query.source_kind === "PREPARED" && <p>Đây là bản tự chuẩn bị để xem và tìm kiếm. Cần xác nhận ý nghĩa nghiệp vụ trước khi dùng để đối soát.</p>}
    {data.query.source_kind === "PREPARED_FINDINGS" && <p>Chỉ gồm dòng có cảnh báo ngày trong bản tự chuẩn bị. Bảng giữ nguyên giá trị nguồn và vị trí dòng.</p>}
    {data.query.source_kind === "PREPARED_ISSUES" && <p>Các dòng có cảnh báo định dạng, kèm giá trị gốc.</p>}
    {data.verification_status === "PARTIAL_VERIFIED" && <p className="agent-answer-note">Kết quả được kiểm chứng một phần. Xem phạm vi trước khi kết luận.</p>}
    {scopeEvidence && <p className="agent-answer-note">Độ đầy đủ của kỳ chưa được xác nhận.</p>}
    {!countOnly && data.warnings.map(w => <p className="muted" key={w}>{w}</p>)}
    {showEvidenceHint && <p className="agent-answer-note agent-result-hint" role="status">{evidenceNote}</p>}
    {error && <Notice tone="error">{error}</Notice>}
    {!singleAmount && (!countOnly || count == null) && <>
      <DataTable rows={previewRows} columns={columns} numericColumns={numericQueryFields}/>
      {pagination}
      {data.rows.length > 0 && <button ref={expandTrigger} className="text-button" onClick={()=>setExpanded(true)}>Xem đầy đủ dữ liệu</button>}
    </>}
    <Modal title="Dữ liệu chi tiết" wide open={expanded} onOpenChange={setExpanded} returnFocus={expandTrigger}>
      <p>{data.total_count.toLocaleString("vi-VN")} {grouped ? "nhóm kết quả" : "dòng dữ liệu"} phù hợp. Mỗi trang tối đa {data.limit} dòng; số liệu tổng hợp tính trên toàn bộ dữ liệu phù hợp.</p>
      {error && <Notice tone="error">{error}</Notice>}
      <DataTable rows={data.rows} columns={columns} numericColumns={numericQueryFields}/>{pagination}
    </Modal>
    <details className="agent-answer-details"><summary>Điều kiện và nguồn</summary>
      {scopeEvidence && <><p>Tệp nguồn <span className="agent-source-file">{scopeEvidence.source_name}</span></p>
        <p>{localCount(scopeEvidence.source_rows)} dòng gốc. {scopeEvidence.grain}.</p></>}
      <p>{data.query.filters.map(f => `${f.field_id} ${f.op} ${JSON.stringify(f.value)}`).join("; ") || "Toàn bộ nguồn"}</p>
      <p>{localCount(data.input_count)} dòng được dùng trước khi phân nhóm và phân trang. <Badge status={data.verification_status}/></p>
      {scopeEvidence && <p className="agent-answer-note">{coverageNote}</p>}
      {!data.evidence_complete && <p className="agent-answer-note">{evidenceNote}</p>}
      {countOnly && data.warnings.map(w => <p key={w}>{w}</p>)}<small>{data.source_refs.join(" · ")}</small>
    </details>
    {scopeEvidence && <details><summary>Xem truy vấn</summary><p>SQL do Backend tạo. Các giá trị lọc được truyền riêng.</p><pre className="table-scroll">{scopeEvidence.sql}</pre></details>}
    <Modal title="Dòng dữ liệu nguồn" returnFocus={evidenceTrigger} open={source !== null} onOpenChange={open => {if(!open){scope.current++;setBusy(false);setSource(null);}}}>
      <p>{sourceRefs.length} dòng nguồn trong bằng chứng hiển thị. Chọn từng dòng để xem chính xác.</p>
      <div className="agent-pagination">{sourceRefs.map((ref,i)=><button className="button secondary" key={`${ref.source_table_id}:${ref.row}:${i}`} disabled={busy||i===sourceIndex} onClick={()=>void evidence({source_provenance:sourceRefs},i)}>{ref.sheet} · dòng {ref.row}</button>)}</div>
      {source && <DataTable rows={source} columns={Object.keys(source[0] || {}).map(k => ({ accessorKey: k, header: k, cell: i => String(i.getValue() ?? "—") }))}/>}</Modal>
  </section>;
}
function ResultChart({ data }: {
    data: Chart;
}) {
    const root = useRef<HTMLDivElement>(null);
    const [narrow, setNarrow] = useState(false);
    const horizontal = narrow || data.points.length > 5 || data.points.some(p => label(p.label).length > 18);
    // Nhãn dài được xuống dòng, mỗi nhóm đủ chỗ; chỉ đổi cách vẽ, không tính lại số liệu.
    const rowHeight = Math.max(48, ...data.points.map(p => Math.ceil(label(p.label).length / 16) * 16 + 20));
    const height = horizontal ? Math.max(285, data.points.length * rowHeight + 50) : 285;
    useEffect(() => {
        if (!root.current)
            return;
        const chart = echarts.init(root.current, undefined, { renderer: "svg" });
        chart.setOption({ aria: { enabled: true, label: { description: `${data.title}. ${data.unit}. ${data.population_definition}. ${data.points.map(p => `${label(p.label)}: ${p.value}`).join("; ")}` } }, grid: { left: 8, right: 24, bottom: 32, top: 20, containLabel: true },
            tooltip: { trigger: "axis", renderMode: "richText", formatter: (params: unknown) => {
                    const first = (params as {
                        dataIndex: number;
                    }[])[0];
                    const point = data.points[first?.dataIndex];
                    return point ? `${label(point.label)}: ${point.value} ${data.unit}` : "";
                } }, xAxis: horizontal ? { type: "value", splitNumber: narrow ? 3 : 5, axisLabel: { hideOverlap: true } } : { type: "category", data: data.points.map(p => label(p.label)), axisLabel: { hideOverlap: true } },
            yAxis: horizontal ? { type: "category", inverse: true, data: data.points.map(p => label(p.label)), axisLabel: { interval: 0, width: 120, overflow: "break", lineHeight: 16 } } : { type: "value" }, series: [{ type: "bar", color: "#2563eb", data: data.points.map(p => ({ value: Number(p.value), name: p.value })) }] });
        const observer = new ResizeObserver(entries => {
            setNarrow(entries[0].contentRect.width < 520);
            chart.resize();
        });
        observer.observe(root.current);
        return () => { observer.disconnect(); chart.dispose(); };
    }, [data, horizontal, narrow]);
    return <section className="agent-chart"><h4>{data.title}</h4><p>{data.unit} · {data.population_definition} ({data.population}) · {statusText[data.verification_status]||label(data.verification_status)}</p>
    {data.period_start && <p>{data.period_start} → {data.period_end} · {data.timezone}</p>}
    {data.completeness !== "COMPLETE" && <Notice tone="warning">Biểu đồ chỉ hiển thị các nhóm đã tải.</Notice>}
    {!data.points.length && <p>Chưa có nhóm dữ liệu để vẽ biểu đồ.</p>}
    <div className="agent-chart-scroll" tabIndex={horizontal ? 0 : undefined} role={horizontal ? "region" : undefined} aria-label={horizontal ? "Các nhóm trong biểu đồ; cuộn để xem toàn bộ" : undefined}>
      <div className="result-chart" style={{height}} ref={root} role="img" aria-label={data.title}/>
    </div>
    <details><summary>Giá trị chính xác và nguồn</summary><ul>{data.points.map(p => <li key={p.label}>{label(p.label)}: {p.value} {data.unit}</li>)}</ul><small>{data.source_refs.join(" · ")}</small></details></section>;
}
function ResultChartDetails({ data }: { data: Chart }) {
    const [opened, setOpened] = useState(false);
    return <details onToggle={event=>{ if (event.currentTarget.open) setOpened(true); }}>
      <summary>Xem biểu đồ · {data.title}</summary>
      {opened && <ResultChart data={data}/>}
    </details>;
}
function DatasetResult({ block, openSource, onQualityPublished, projectId }: {
    block: Extract<AgentBlock, { type: "dataset_summary" }>;
    openSource: () => void;
    projectId: string;
    onQualityPublished?: (id: string) => void;
}) {
    const ready = block.status === "READY";
    const [keepQuality, setKeepQuality] = useState(false);
    const [detailsOpened, setDetailsOpened] = useState(false);
    const qualityVisible = keepQuality || !ready;
    const qualityPanel = <DataQualityPanel tableId={block.table_id} canonicalId={block.canonical_id} sourceName={block.name}
      draft={block.quality_draft} followLatest={qualityVisible} chatProjectId={projectId} showIssueRows={block.show_issue_rows} onPublished={id=>{
        if (!ready) setKeepQuality(true);
        onQualityPublished?.(id);
      }}/>;
    return <section className="agent-dataset">
      {qualityVisible
        ? qualityPanel
        : <p className="agent-answer-lead">Đã chuẩn hóa <strong>{localCount(block.rows)} dòng</strong> từ {sourceDisplayName(block.name)}.</p>}
      <details onToggle={event=>{ if (event.currentTarget.open) setDetailsOpened(true); }}>
        <summary>Chi tiết chuẩn hóa{ready && !qualityVisible ? " và quyết định về dữ liệu" : ""}</summary>
        {ready && !qualityVisible && <p className="agent-source-file">{block.name}</p>}
        <p>{Array.from(new Set(block.transformations)).map(t=>transformLabels[t]||t).join(" · ")}</p>
        {!qualityVisible && detailsOpened && qualityPanel}
      </details>
      <button type="button" className="text-button" onClick={openSource}>Kiểm tra dữ liệu trước/sau</button>
    </section>;
}

function SourceStatus({block}: {block: Extract<AgentBlock, {type: "source_status"}>}) {
    const fields = [
      ["original_rows", "Dòng gốc"], ["valid_rows", "Hợp lệ"], ["invalid_rows", "Dòng lỗi"],
      ["canonical_rows", "Đã chuẩn hóa"], ["excluded_rows", "Đã loại"],
    ] as const;
    const states: Record<string, string> = {
      READY: "Đã chuẩn hóa", PARTIAL: "Có ngoại lệ", STALE: "Bản cũ hết hiệu lực",
      EXPLORATION_ONLY: "Chỉ để xem", MAPPED: "Chờ chuẩn hóa", MAPPING_REVIEW: "Chờ xác nhận cột",
      PARSE_FAILED: "Đọc tệp thất bại", FAILED: "Chuẩn hóa thất bại", PARSED: "Đã đọc tệp",
    };
    const showDetails = block.items.some(row =>
      (row.excluded_rows ?? 0) > 0 || (row.canonical_rows !== null && row.canonical_rows !== row.original_rows)
    );
    const columns = fields.slice(0, showDetails ? fields.length : 3);
    const complete = block.ready_count === block.source_count;
    const noErrors = complete && (block.totals?.invalid_rows ?? block.items[0]?.invalid_rows) === 0;
    const counts = (row: SourceStatusLine) => columns.map(([field]) => (
      <td className="numeric-cell" key={field}>{row[field]?.toLocaleString("vi-VN") ?? "—"}</td>
    ));
    return <section className="agent-source-status" aria-label="Thống kê chuẩn bị dữ liệu">
      <p className="agent-answer-lead"><strong>{complete ? `Cả ${block.source_count} nguồn` :
        `${block.ready_count}/${block.source_count} nguồn`}</strong> đã chuẩn bị xong.
        {noErrors && " Không phát hiện dòng lỗi."}</p>
      <div className="table-scroll" tabIndex={0} aria-label="Số dòng theo nguồn">
        <table>
          <thead><tr><th scope="col">Nguồn</th>{columns.map(([field, title]) =>
            <th scope="col" className="numeric-cell" key={field}>{title}</th>
          )}<th scope="col">Trạng thái</th></tr></thead>
          <tbody>{block.items.map((row, index) => <tr key={index}>
            <th scope="row">{row.name}{row.sheet && <small>{row.sheet}</small>}</th>
            {counts(row)}
            <td>{states[row.status] || statusText[row.status] || "Đang kiểm tra"}</td>
          </tr>)}</tbody>
          {block.totals && <tfoot><tr><th scope="row">Tổng</th>{counts(block.totals)}<td /></tr></tfoot>}
        </table>
      </div>
      {block.items.some(row=>row.valid_rows === null) && <p className="muted">Dấu — là số liệu chưa xác định từ bản hiện hành.</p>}
    </section>;
}

function ObservedResult({block, open}: {block: Extract<AgentBlock, {type: "facts"}>; open: (id: string) => void}) {
    const run = block.result.run;
    const snapshot = run?.metric_snapshot;
    const scope = block.observation;
    if (!run || !snapshot || !scope) return null;
    const count = (value: number | undefined) => value?.toLocaleString("vi-VN") ?? "—";
    const money = snapshot.monetary[0];
    const stats = [
      ["Nhóm khớp", count(snapshot.comparison_counts.EQUAL ?? 0)],
      ["Nhóm lệch tiền", count(snapshot.comparison_counts.AMOUNT_MISMATCH ?? 0)],
      ["Nhóm chưa thấy đối ứng", count(snapshot.linkage_counts.PENDING ?? 0)],
      ["Mã đơn trùng", count(scope.duplicate_keys)],
      ["Chênh lệch có dấu", money ? `${formatDecimal(money.signed_variance)} ${money.currency}` : "—"],
      ["Chênh lệch tuyệt đối", money ? `${formatDecimal(money.absolute_variance)} ${money.currency}` : "—"],
    ];
    return <section className="agent-facts" aria-label={scope.pair}>
      <header><h4>{scope.pair}</h4><p className="agent-answer-note">Đã xác minh một phần trên dữ liệu quan sát được.</p></header>
      <div className="table-scroll" tabIndex={0} aria-label="Số liệu đối chiếu">
        <table><tbody>{stats.map(([title, value]) => <tr key={title}>
          <th scope="row">{title}</th><td className="numeric-cell">{value}</td>
        </tr>)}</tbody></table>
      </div>
      <details><summary>Phạm vi kiểm tra</summary>
        <p>Từ {localDay(scope.observed_start)} đến {localDay(scope.observed_end)}. Độ đầy đủ của kỳ kế toán chưa được xác nhận.</p>
        {scope.source_names.map((name, index) => {
          const partition = run.partition_counts?.[index === 0 ? "left" : "right"];
          const excluded = run.source_refs?.[index]?.excluded_source_rows ?? 0;
          return <p key={index}>{name}{partition && <> · {count(partition.IN_SCOPE ?? 0)} dòng dùng được trong phạm vi
            {" · "}{count(partition.INVALID ?? 0)} dòng lỗi · {count(partition.OUT_OF_SCOPE ?? 0)} dòng ngoài khoảng kiểm tra</>}
            {excluded > 0 && ` · ${count(excluded)} dòng có quyết định loại`}</p>;
        })}
      </details>
      <button className="text-button" onClick={() => open(run.id)}>Xem giao dịch, bằng chứng và xuất báo cáo</button>
      {snapshot.financial?.length ? <FinancialSummary snapshot={snapshot} names={scope.source_names} /> : null}
    </section>;
}

export function AgentResultBlocks({ blocks, context, onNavigate, workflowId, querySelection, onQualityPublished, compactPreviews, mappingReview, showResultHints }: {
    blocks: AgentBlock[];
    context: AssistantContext;
    onNavigate: (target: Suggestion, context: AssistantContext) => void;
    workflowId?: string;
    querySelection?: Query | null;
    onQualityPublished?: (id: string) => void;
    compactPreviews?: boolean;
    mappingReview?: boolean;
    showResultHints: boolean;
}) {
    const sources = blocks.filter(block=>block.type === "dataset_summary");
    const hasFacts = blocks.some(block=>block.type === "facts");
    const observedPairs = blocks.filter(block => block.type === "facts" && block.observation).length;
    const readySources = sources.filter(block=>block.status === "READY").length;
    const remainingSources = sources.length - readySources;
    const mappingProgress = mappingReview ? blocks.filter(block => block.type === "progress") : [];
    const showPreview = (block: AgentBlock) => compactPreviews && block.type === "table" && block.result.query.source_kind === "RAW_PREVIEW";
    const previews = blocks.flatMap((block, i) => showPreview(block) && block.type === "table"
      ? [<QueryTable key={i} initial={block.result} title={block.title} workflowId={workflowId} selection={querySelection} showResultHints={false}/>] : []);
    return <div className="agent-results">
        {observedPairs > 0 && <p className="agent-answer-lead">
          Đã đối soát <strong>{observedPairs === 1 ? "một cặp" : "hai cặp"}</strong> trên dữ liệu quan sát được.
        </p>}
        {sources.length > 1 && <p className="agent-conclusion">
          {readySources > 0 && <strong>{readySources} nguồn sẵn sàng lập quy tắc đối soát.</strong>}
          {remainingSources > 0 && <>{readySources > 0 && " "}{remainingSources} nguồn còn cần xem lại.</>}
        </p>}
        {blocks.map((block, i) => {
            if (showPreview(block)) return null;
            if (block.type === "progress")
                return mappingReview ? null : <p key={i}>{block.text}</p>;
            if (block.type === "table")
                return <QueryTable key={i} initial={block.result} title={block.title} workflowId={workflowId} selection={querySelection} showResultHints={showResultHints}/>;
            if (block.type === "source_status")
                return <SourceStatus key={i} block={block}/>;
            if (block.type === "source_comparison") {
                const columns: ColumnDef<Record<string, unknown>>[] = [
                    {accessorKey:"field", header:"Trường"},
                    {accessorKey:"original", header:"Giá trị gốc", cell: cell=>String(cell.getValue() ?? "Ô trống")},
                    {accessorKey:"processed", header:"Sau xử lý", cell: cell=>String(cell.getValue() ?? "—")},
                    {accessorKey:"outcome", header:"Trạng thái"},
                ];
                return <section className="agent-table" key={i}>
                  <h4>{block.name} · Dòng {block.row}</h4>
                  {block.scope === "PREPARED" && <p>Bản chuẩn bị để xem. Ngữ nghĩa tài chính còn cần kiểm chứng.</p>}
                  {block.scope === "RAW" && <p>Nguồn hiện chỉ có dữ liệu gốc.</p>}
                  <DataTable rows={block.fields.slice(0, 6)} columns={columns}/>
                  {block.fields.length > 6 && <details><summary>Các trường còn lại</summary>
                    <DataTable rows={block.fields.slice(6)} columns={columns}/>
                  </details>}
                </section>;
            }
            if (block.type === "chart")
                return hasFacts ? <ResultChartDetails key={i} data={block}/> : <ResultChart key={i} data={block}/>;
            if (block.type === "download")
                return <div className="agent-download" key={i}>
                  {typeof block.displayed_query === "boolean" && <p className="muted">{block.discrepancies_only
                    ? "Tệp chỉ liệt kê giao dịch chênh lệch. Các chỉ số vẫn bao quát lượt đối soát đã xác minh."
                    : block.displayed_query
                    ? "Tệp chứa đúng trang kết quả đã được chọn khi yêu cầu xuất."
                    : "Tệp chứa toàn bộ lần đối soát được yêu cầu."}</p>}
                  <a className="button secondary" href={block.source_table ? `/api/agent/workflows/${block.export_id}/source-export` : `/api/exports/${block.export_id}/download`}>Tải {block.discrepancies_only ? "giao dịch chênh lệch " : block.displayed_query ? "bảng đang xem " : ""}{block.format.toUpperCase()}</a>
                </div>;
            if (block.type === "dataset_summary")
                return <DatasetResult key={block.table_id} block={block} onQualityPublished={onQualityPublished} projectId={context.project_id}
                  openSource={()=>onNavigate("OPEN_DATA", { project_id: context.project_id, dataset_id: block.dataset_id })}/>;
            if (block.observation)
                return <ObservedResult key={i} block={block} open={run_id => onNavigate("OPEN_REPORT", {project_id: context.project_id, run_id})}/>;
            const snapshot = block.result.snapshot || block.result.run?.metric_snapshot;
            const reportRunId = snapshot?.run_id || block.result.run?.id;
            const observed = block.result.run?.observed_scope;
            const pairNames = snapshot?.source_canonical_ids?.map(id=>sources.find(source=>source.canonical_id === id)?.name);
            const otherGroups = [["PENDING", "đang chờ"], ["AMBIGUOUS", "cần xem lại liên kết"], ["INVALID", "dữ liệu lỗi"]]
              .flatMap(([state, description])=>{
                if (observed && state === "PENDING") return [];
                const count = snapshot?.linkage_counts?.[state];
                return count ? [`${count.toLocaleString("vi-VN")} nhóm ${description}`] : [];
              });
            return <section className="agent-facts" key={i}>
              {snapshot && <>
                <header>
                  <h4>{observed ? "Đối chiếu dữ liệu quan sát được" : block.result.run?.status === "PARTIAL_VERIFIED" ? "Kết quả đã xác minh một phần" : "Kết quả đã xác minh"}</h4>
                  {pairNames?.length === 2 && pairNames.every(Boolean) && <p className="muted">{pairNames.join(" ↔ ")}</p>}
                </header>
                <p className="agent-answer-lead"><strong>{localCount(snapshot.comparison_counts?.EQUAL ?? 0)} nhóm khớp chính xác</strong>{", "}
                  {(snapshot.comparison_counts?.AMOUNT_MISMATCH ?? 0).toLocaleString("vi-VN")} nhóm lệch tiền và {" "}
                  {(snapshot.linkage_counts?.[observed ? "PENDING" : "UNMATCHED"] ?? 0).toLocaleString("vi-VN")} nhóm {observed ? "chưa thấy đối ứng trong dữ liệu" : "thiếu đối ứng"}.</p>
                {observed && <p className="agent-answer-note">Đã kiểm chứng trên phần đủ điều kiện. Độ đầy đủ của kỳ chưa được xác nhận.</p>}
                {!!snapshot.comparison_counts?.WITHIN_TOLERANCE && <p>{snapshot.comparison_counts.WITHIN_TOLERANCE} nhóm trong sai số đã duyệt.</p>}
                {otherGroups.length > 0 && <p>{otherGroups.join(" · ")}</p>}
                {snapshot.monetary.map(m => <p key={m.metric_id}>
                  {observed && <>{m.comparable_groups.toLocaleString("vi-VN")} nhóm so sánh được · </>}
                  {snapshot.monetary.length > 1 && <><strong>{label(m.metric_id)}</strong> · </>}
                  Chênh lệch tuyệt đối <strong>{formatDecimal(m.absolute_variance)} {m.currency}</strong> · Có dấu {formatDecimal(m.signed_variance)} {m.currency}
                </p>)}
                <FinancialSummary snapshot={snapshot} names={pairNames?.filter((name): name is string => !!name)} />
                <details><summary>Phạm vi và cách tính tỷ lệ</summary>
                  <p>Tỷ lệ khớp {snapshot.full_match_rate.percent ?? "N/A"}{snapshot.full_match_rate.percent !== null ? "%" : ""} ({snapshot.full_match_rate.numerator}/{snapshot.full_match_rate.denominator})</p>
                  <p>Kỳ {snapshot.period_start} → {snapshot.period_end} · {snapshot.timezone}</p>
                  <p>{snapshot.eligible_definition}</p>
                  <p>Đơn vị so sánh · {snapshot.comparison_unit}</p>
                  {observed && block.result.run?.source_refs?.map((source, index)=>{
                      const partition = block.result.run?.partition_counts?.[index === 0 ? "left" : "right"];
                      return <p key={index}>{pairNames?.[index] ?? (index === 0 ? "Nguồn trái" : "Nguồn phải")} · {source.source_row_count ?? source.row_count} dòng gốc
                        {partition && <>{" · "}{partition.IN_SCOPE ?? 0} dòng trong phạm vi · {partition.INVALID ?? 0} dòng lỗi</>}
                        {!!source.excluded_source_rows && ` · ${source.excluded_source_rows} dòng có quyết định loại`}</p>;
                  })}
                  {Object.entries(snapshot.excluded_counts || {}).map(([name, count])=><p key={name}>{label(name)} · {count}</p>)}
                </details>
              </>}
              {(!snapshot || block.result.group) && block.answer?.lines.map((line, j)=><p key={j}>{line.text}</p>)}
              {block.result.group && <>
                <p>{label(block.result.group.linkage_state)} · {label(block.result.group.comparison_state)}</p>
                <p>Nguyên nhân nghiệp vụ chưa được chứng minh nếu thiếu chứng từ hoặc quy định.</p>
              </>}
              <button className="text-button" onClick={()=>onNavigate(block.result.group ? "OPEN_EVIDENCE" : "OPEN_REPORT",
                reportRunId && !block.result.group ? {project_id: context.project_id, run_id: reportRunId} : context)}>Mở kết quả và bằng chứng</button>
            </section>;
        })}
        {previews.length > 0 && <details className="agent-previews"><summary>Dữ liệu gốc đã đọc ({previews.length} bảng)</summary>{previews}</details>}
        {mappingProgress.length > 0 && <details><summary>Tiến độ đọc dữ liệu</summary>
          {mappingProgress.map((block, i) => <p key={i}>{block.text}</p>)}
        </details>}
    </div>;
}
