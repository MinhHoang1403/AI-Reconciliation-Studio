import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { AriaComponent, GridComponent, TooltipComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import { api } from "./api";
import { Badge, DataTable, formatDecimal, Modal, Notice, Spinner } from "./components";
import { label } from "./reconciliationTypes";
import {statusText} from "./types";
import type { AgentBlock, Chart, Query, QueryResult } from "./agentTypes";
import type { AssistantContext, Suggestion } from "./assistantTypes";
import type { ColumnDef } from "@tanstack/react-table";
echarts.use([BarChart, AriaComponent, GridComponent, TooltipComponent, SVGRenderer]);
type SourceRef = {source_table_id:string;row:number;sheet:string};
const transformLabels:Record<string,string>={cast_string_preserve:"Giữ nguyên văn bản và mã",parse_decimal:"Đọc số tiền theo định dạng đã duyệt",parse_date:"Đọc ngày theo định dạng và múi giờ đã duyệt",trim_if_approved:"Bỏ khoảng trắng theo quy tắc đã duyệt",normalize_enum:"Chuẩn hóa trạng thái theo quy tắc đã duyệt",coalesce_with_rule:"Chọn giá trị theo quy tắc đã duyệt",add_fields:"Cộng trường theo quy tắc đã duyệt",subtract_fields:"Trừ trường theo quy tắc đã duyệt",aggregate_by:"Gom nhóm theo quy tắc đã duyệt"};
const queryLabels:Record<string,string>={linkage_state:"Liên kết",comparison_state:"Kết quả so sánh",left_member_count:"Số dòng nguồn A",right_member_count:"Số dòng nguồn B",left_amount:"Số tiền nguồn A",right_amount:"Số tiền nguồn B",delta:"Chênh lệch có dấu",absolute_variance:"Chênh lệch tuyệt đối",tolerance:"Sai số cho phép",currency:"Tiền tệ",unit:"Đơn vị",type:"Loại ngoại lệ",state:"Xử lý ngoại lệ",notes:"Ghi chú"};
function QueryTable({ initial, workflowId, selection }: {
    initial: QueryResult;
    workflowId?: string;
    selection?: Query | null;
}) {
    const [data, setData] = useState(initial);
    const [busy, setBusy] = useState(false);
    const [expanded, setExpanded] = useState(false);
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
    const countOnly = !data.query.group_by?.length && data.query.aggregations?.length === 1 && data.query.aggregations[0].op === "count";
    const count = countOnly && data.rows[0] ? data.rows[0][data.fields[0]] : null;
    const columns: ColumnDef<Record<string, unknown>>[] = [{id:'position',header:'Vị trí trong trang',cell:info=>info.row.index+1},...(groupKey?[{id:'business_key',accessorKey:'business_key',header:'Khóa giao dịch'}]:[]),...visibleFields.map<ColumnDef<Record<string, unknown>>>(field => ({ id: field, accessorKey: field,
        header: () => <button className="text-button" disabled={busy} onClick={() => void page(0, [{ field_id: field, descending: !data.query.sort.find(s => s.field_id === field)?.descending }])}>{data.field_labels?.[field]||queryLabels[field]||field} ↕</button>,
        cell: info => info.getValue() == null ? "—" :
          ['VERIFIED_RUN','EXCEPTIONS'].includes(data.query.source_kind)&&['linkage_state','comparison_state','state','type'].includes(field)?label(String(info.getValue())):String(info.getValue()) })), {
        id: "evidence", header: () => <span>Nguồn</span>, cell: info => <button className="text-button" disabled={busy || !Array.isArray(info.row.original.source_provenance)} onClick={() => void evidence(info.row.original)}>Xem dòng gốc</button>,
    }];
    const pagination = <div className="agent-pagination"><button className="button secondary" disabled={busy || !data.offset} onClick={() => void page(Math.max(0, data.offset - data.limit))}>Trước</button>
      <span>Trang {Math.floor(data.offset / data.limit) + 1} · {data.rows.length} dòng trong trang</span>
      <button className="button secondary" disabled={busy || !data.truncated} onClick={() => void page(data.offset + data.limit)}>Tiếp</button>{busy && <Spinner />}</div>;
    return <section className="agent-table" aria-label="Kết quả truy vấn">
    {countOnly && count !== null && <p>Kết quả đếm: <strong>{typeof count === "number" ? count.toLocaleString("vi-VN") : String(count)} {data.query.source_kind === "VERIFIED_RUN" ? "nhóm giao dịch" : "dòng dữ liệu"}</strong> phù hợp với điều kiện bạn chọn.</p>}
    {!countOnly && <p><strong>{data.total_count.toLocaleString("vi-VN")} {grouped ? "nhóm kết quả" : "dòng dữ liệu"}</strong>{data.total_count === 0 ? ". Chưa tìm thấy dữ liệu phù hợp với điều kiện bạn chọn." : ". Bạn có thể xem dữ liệu và mở từng dòng gốc bên dưới."}</p>}
    <p className="muted">Đang xem {previewRows.length} dòng trong trang {Math.floor(data.offset / data.limit) + 1}{data.rows.length > 10 ? `; trang này có ${data.rows.length} dòng.` : "."}</p>
    {data.query.source_kind === "RAW_PREVIEW" && <p>Đây là dữ liệu gốc đã đọc từ tệp. Ý nghĩa các cột chưa được xác nhận; dữ liệu chưa được chuẩn hóa.</p>}
    {data.query.source_kind === "PREPARED" && <p>Đây là bản tự chuẩn bị để xem và tìm kiếm. Cần xác nhận ý nghĩa nghiệp vụ trước khi dùng để đối soát.</p>}
    {data.verification_status === "PARTIAL_VERIFIED" && <Notice tone="warning">Kết quả chỉ được kiểm chứng một phần. Hãy kiểm tra các dữ liệu chưa đủ điều kiện trước khi kết luận.</Notice>}
    {data.warnings.map(w => <p className="muted" key={w}>{w}</p>)}
    {!data.evidence_complete && <Notice tone="warning">Chỉ hiển thị một phần bằng chứng; thông tin nguồn đầy đủ vẫn được lưu.</Notice>}
    {error && <Notice tone="error">{error}</Notice>}
    <DataTable rows={previewRows} columns={columns}/>
    {pagination}
    {data.rows.length > 0 && <button className="text-button" onClick={()=>setExpanded(true)}>Xem đầy đủ dữ liệu</button>}
    <Modal title="Dữ liệu chi tiết" wide open={expanded} onOpenChange={setExpanded}>
      <p>{data.total_count.toLocaleString("vi-VN")} {grouped ? "nhóm kết quả" : "dòng dữ liệu"} phù hợp. Mỗi trang tối đa {data.limit} dòng; số liệu tổng hợp tính trên toàn bộ dữ liệu phù hợp.</p>
      {error && <Notice tone="error">{error}</Notice>}
      <DataTable rows={data.rows} columns={columns}/>{pagination}
    </Modal>
    <details><summary>Điều kiện và nguồn</summary><p>{data.query.filters.map(f => `${f.field_id} ${f.op} ${JSON.stringify(f.value)}`).join("; ") || "Toàn bộ nguồn"}</p><p>{data.input_count.toLocaleString("vi-VN")} dòng được dùng trước khi phân nhóm và phân trang. <Badge status={data.verification_status}/></p><small>{data.source_refs.join(" · ")}</small></details>
    <Modal title="Dòng dữ liệu nguồn" open={source !== null} onOpenChange={open => {if(!open){scope.current++;setBusy(false);setSource(null);}}}>
      <p>{sourceRefs.length} dòng nguồn trong bằng chứng hiển thị. Chọn từng dòng để xem chính xác.</p>
      <div className="agent-pagination">{sourceRefs.map((ref,i)=><button className="button secondary" key={`${ref.source_table_id}:${ref.row}:${i}`} disabled={busy||i===sourceIndex} onClick={()=>void evidence({source_provenance:sourceRefs},i)}>{ref.sheet} · dòng {ref.row}</button>)}</div>
      {source && <DataTable rows={source} columns={Object.keys(source[0] || {}).map(k => ({ accessorKey: k, header: k, cell: i => String(i.getValue() ?? "—") }))}/>}</Modal>
  </section>;
}
function ResultChart({ data }: {
    data: Chart;
}) {
    const root = useRef<HTMLDivElement>(null);
    const horizontal = data.points.length > 5 || data.points.some(p => label(p.label).length > 18);
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
                } }, xAxis: horizontal ? { type: "value" } : { type: "category", data: data.points.map(p => label(p.label)), axisLabel: { interval: 0 } },
            yAxis: horizontal ? { type: "category", inverse: true, data: data.points.map(p => label(p.label)), axisLabel: { interval: 0, width: 120, overflow: "break", lineHeight: 16 } } : { type: "value" }, series: [{ type: "bar", color: "#2563eb", data: data.points.map(p => ({ value: Number(p.value), name: p.value })) }] });
        const observer = new ResizeObserver(() => chart.resize());
        observer.observe(root.current);
        return () => { observer.disconnect(); chart.dispose(); };
    }, [data]);
    return <section className="agent-chart"><h4>{data.title}</h4><p>{data.unit} · {data.population_definition} ({data.population}) · {statusText[data.verification_status]||label(data.verification_status)}</p>
    {data.period_start && <p>{data.period_start} → {data.period_end} · {data.timezone}</p>}
    {data.completeness !== "COMPLETE" && <Notice tone="warning">Biểu đồ chỉ hiển thị các nhóm đã tải.</Notice>}
    {!data.points.length && <p>Chưa có nhóm dữ liệu để vẽ biểu đồ.</p>}
    <div className="agent-chart-scroll" tabIndex={horizontal ? 0 : undefined} role={horizontal ? "region" : undefined} aria-label={horizontal ? "Các nhóm trong biểu đồ; cuộn để xem toàn bộ" : undefined}>
      <div className="result-chart" style={{height}} ref={root} role="img" aria-label={data.title}/>
    </div>
    <details><summary>Giá trị chính xác và nguồn</summary><ul>{data.points.map(p => <li key={p.label}>{label(p.label)}: {p.value} {data.unit}</li>)}</ul><small>{data.source_refs.join(" · ")}</small></details></section>;
}
export function AgentResultBlocks({ blocks, context, onNavigate, workflowId, querySelection }: {
    blocks: AgentBlock[];
    context: AssistantContext;
    onNavigate: (target: Suggestion, context: AssistantContext) => void;
    workflowId?: string;
    querySelection?: Query | null;
}) {
    return <div className="agent-results">{blocks.map((block, i) => {
            if (block.type === "progress")
                return <p key={i}>{block.text}</p>;
            if (block.type === "table")
                return <QueryTable key={i} initial={block.result} workflowId={workflowId} selection={querySelection}/>;
            if (block.type === "chart")
                return <ResultChart key={i} data={block}/>;
            if (block.type === "download")
                return <a className="button secondary" key={i} href={`/api/exports/${block.export_id}/download`}>Tải {block.displayed_query ? "bảng đang xem " : ""}{block.format.toUpperCase()}</a>;
            if (block.type === "dataset_summary")
                return <section className="agent-dataset" key={i}><h4>{block.name}</h4><Badge status={block.status}/><p>{block.status === "READY" ? "Đã chuẩn hóa" : "Đã xử lý"} {block.rows.toLocaleString("vi-VN")} dòng. {block.invalid_rows > 0 ? `${block.invalid_rows.toLocaleString("vi-VN")} dòng cần bạn kiểm tra; chưa thể dùng như dữ liệu đầy đủ.` : "Bạn có thể xem dữ liệu trước và sau khi chuẩn hóa."}</p><details><summary>Phép biến đổi đã duyệt</summary><p>{Array.from(new Set(block.transformations)).map(t=>transformLabels[t]||t).join("; ")}</p></details><button className="text-button" onClick={() => onNavigate("OPEN_DATA", { project_id: context.project_id, dataset_id: block.dataset_id })}>Kiểm tra dữ liệu trước/sau</button></section>;
            const snapshot = block.result.snapshot || block.result.run?.metric_snapshot;
            return <section className="agent-facts" key={i}>{snapshot && <><h4>{block.result.run?.status==="PARTIAL_VERIFIED"?"Kết quả đã xác minh một phần":"Kết quả đã xác minh"}</h4><p>{(snapshot.comparison_counts?.EQUAL??0).toLocaleString("vi-VN")} nhóm khớp chính xác, {(snapshot.comparison_counts?.AMOUNT_MISMATCH??0).toLocaleString("vi-VN")} nhóm lệch tiền và {(snapshot.linkage_counts?.UNMATCHED??0).toLocaleString("vi-VN")} nhóm chưa tìm thấy đối ứng.</p>{!!snapshot.comparison_counts?.WITHIN_TOLERANCE&&<p>{snapshot.comparison_counts.WITHIN_TOLERANCE} nhóm trong sai số đã duyệt.</p>}<p>Tỷ lệ khớp: {snapshot.full_match_rate.percent ?? "N/A"}{snapshot.full_match_rate.percent !== null ? "%" : ""} ({snapshot.full_match_rate.numerator}/{snapshot.full_match_rate.denominator})</p>{snapshot.monetary.map(m => <p key={m.metric_id}>Chênh lệch tuyệt đối: {formatDecimal(m.absolute_variance)} {m.currency} · có dấu: {formatDecimal(m.signed_variance)} {m.currency}</p>)}<details><summary>Phạm vi và cách tính tỷ lệ</summary><p>Kỳ {snapshot.period_start} → {snapshot.period_end} · {snapshot.timezone}</p><p>{snapshot.eligible_definition}</p><p>Đơn vị so sánh: {snapshot.comparison_unit}</p>{Object.entries(snapshot.excluded_counts||{}).map(([name,count])=><p key={name}>{label(name)}: {count}</p>)}{snapshot.monetary.map(m=><p key={m.metric_id}>Chỉ tiêu: {m.metric_id} · {m.currency}</p>)}</details></>}
      {(!snapshot||block.result.group)&&block.answer?.lines.map((line, j) => <p key={j}>{line.text}</p>)}
      {block.result.group && <><p>{label(block.result.group.linkage_state)} · {label(block.result.group.comparison_state)}</p><p>Nguyên nhân nghiệp vụ chưa được chứng minh nếu thiếu chứng từ hoặc quy định.</p></>}
      <button className="text-button" onClick={() => onNavigate(block.result.group ? "OPEN_EVIDENCE" : "OPEN_REPORT", context)}>Mở kết quả và bằng chứng</button></section>;
        })}</div>;
}
