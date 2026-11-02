import { useEffect, useRef, useState, type RefObject } from "react";
import { api } from "./api";
import { Badge, DataTable, formatValue, Modal, Notice, Spinner } from "./components";
import type { AssistantContext } from "./assistantTypes";
import type { Canonical, Dataset, Preview, Table } from "./types";

/** Chỉ đọc refs có quyền; đóng/đổi nguồn hủy request, không thay draft hội thoại. */
export function AssistantDataDrawer({ context, onClose, onManual, returnFocus }: {
  context: AssistantContext;
  onClose: () => void;
  onManual: (context: AssistantContext) => void;
  returnFocus: RefObject<HTMLElement | null>;
}) {
  const [list, setList] = useState<{items:Dataset[];total:number}|null>(null);
  const [offset,setOffset] = useState(0);
  const [datasetId,setDatasetId] = useState(context.dataset_id || "");
  const [tables,setTables] = useState<Table[]>([]);
  const [tableId,setTableId] = useState("");
  const [canonicals,setCanonicals] = useState<Canonical[]>([]);
  const [canonicalId,setCanonicalId] = useState("");
  const [kind,setKind] = useState<"raw"|"canonical"|"errors">("raw");
  const [page,setPage] = useState(0);
  const [search,setSearch] = useState("");
  const [preview,setPreview] = useState<Preview|null>(null);
  const [error,setError] = useState("");
  const [retry,setRetry] = useState(0);
  const [loading,setLoading] = useState(false);
  const active = useRef(datasetId);
  active.current = datasetId;
  useEffect(()=>{
    const controller=new AbortController(); setList(null);setError("");
    void api<{items:Dataset[];total:number}>(`/datasets?project_id=${encodeURIComponent(context.project_id)}&offset=${offset}&limit=20`,{signal:controller.signal})
      .then(result=>{if(!controller.signal.aborted)setList(result);})
      .catch(e=>{if(!controller.signal.aborted)setError(String(e));});
    return()=>controller.abort();
  },[context.project_id,offset,retry]);
  useEffect(()=>{
    const controller=new AbortController();setTables([]);setCanonicals([]);setTableId("");setCanonicalId("");setPreview(null);setError("");
    if(datasetId){setLoading(true);void (async()=>{
      // GET theo ID cũng bảo vệ nguồn nằm ngoài trang danh sách hiện tại.
      const dataset=await api<Dataset>(`/datasets/${datasetId}`,{signal:controller.signal});
      if(dataset.project_id!==context.project_id)throw new Error("Nguồn không thuộc dự án đang xem.");
      const [t,a]=await Promise.all([
        api<{items:Table[]}>(`/datasets/${datasetId}/tables`,{signal:controller.signal}),
        api<{canonical_datasets:Canonical[]}>(`/datasets/${datasetId}/artifacts`,{signal:controller.signal}),
      ]);
      if(!controller.signal.aborted){setTables(t.items);setTableId(t.items[0]?.id||"");setCanonicals(a.canonical_datasets);}
    })().catch(e=>{if(!controller.signal.aborted)setError(String(e));}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});}
    return()=>controller.abort();
  },[context.project_id,datasetId,retry]);
  const candidates=canonicals.filter(c=>c.source_table_id===tableId);
  useEffect(()=>{setCanonicalId("");setKind("raw");setPage(0);setSearch("");},[tableId]);
  useEffect(()=>{
    const controller=new AbortController();setPreview(null);
    if(!tableId||(kind!=="raw"&&!canonicalId))return()=>controller.abort();
    setLoading(true);setError("");
    const params=new URLSearchParams({kind,offset:String(page),limit:"25",search});
    if(canonicalId)params.set("canonical_id",canonicalId);
    void api<Preview>(`/tables/${tableId}/preview?${params}`,{signal:controller.signal})
      .then(result=>{if(!controller.signal.aborted)setPreview(result);})
      .catch(e=>{if(!controller.signal.aborted)setError(String(e));})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[tableId,canonicalId,kind,page,search,retry]);
  const rows=(preview?.items||[]).map(row=>kind==="canonical"?{...(row.record_payload as Record<string,unknown>),source_provenance:row.source_provenance}:row);
  const fields=kind==="canonical"?Object.keys(rows[0]||{}):preview?.columns||[];
  const selected=candidates.find(c=>c.id===canonicalId);
  return <Modal title="Tệp và dữ liệu" wide open onOpenChange={open=>{if(!open)onClose();}} returnFocus={returnFocus}>
    <p>Xem nguồn gốc, bản chuẩn hóa và lỗi tại đây. Tệp gốc được giữ nguyên.</p>
    {error&&<Notice tone="error">{error}<button className="text-button" onClick={()=>setRetry(n=>n+1)}>Thử lại</button></Notice>}
    {list?<><p>{list.total} tệp trong dự án</p><div className="assistant-source-list">{list.items.map(d=><button className={`button secondary ${d.id===datasetId?"selected":""}`} key={d.id} aria-pressed={d.id===datasetId} onClick={()=>{setDatasetId(d.id);setKind("raw");}}>{d.name} <Badge status={d.status}/></button>)}</div>
      <div className="agent-pagination"><button className="button secondary" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-20))}>Tệp trước</button><span>{list.total?offset+1:0}–{Math.min(offset+20,list.total)} / {list.total}</span><button className="button secondary" disabled={offset+20>=list.total} onClick={()=>setOffset(offset+20)}>Tệp tiếp</button></div>
      {!list.total&&<Notice>Chưa có tệp. Đóng bảng này và đính kèm CSV/XLSX trong ô giao việc.</Notice>}</>:!error&&<Spinner/>}
    {datasetId&&<>
      <div className="agent-form-grid"><label>Bảng nguồn<select value={tableId} onChange={e=>setTableId(e.target.value)}>{tables.map(t=><option value={t.id} key={t.id}>{t.sheet} · {t.row_count} dòng</option>)}</select></label>
      <label>Phiên bản chuẩn hóa<select aria-label="Phiên bản chuẩn hóa" value={canonicalId} onChange={e=>{setCanonicalId(e.target.value);setPage(0);if(!e.target.value)setKind("raw");}}><option value="">Chọn bản chuẩn hóa đã lưu</option>{candidates.map(c=><option value={c.id} key={c.id}>{c.quality_status} · {c.row_count} dòng{c.stale?" · đã cũ":""} · {c.id.slice(0,8)}</option>)}</select></label></div>
      <div className="agent-pagination">{([['raw','Dữ liệu gốc'],['canonical','Đã chuẩn hóa'],['errors','Dòng lỗi']] as const).map(([value,name])=><button className="button secondary" key={value} disabled={value!=="raw"&&!canonicalId} aria-pressed={kind===value} onClick={()=>{setKind(value);setPage(0);}}>{name}</button>)}
        <a className="text-button" href={`/api/datasets/${datasetId}/download`}>Tải tệp gốc</a>
      </div>
      {selected&&<p><Badge status={selected.quality_status}/> {selected.row_count} dòng · {selected.invalid_count} dòng lỗi{selected.stale?" · Phiên bản đã cũ, chỉ dùng để kiểm tra lịch sử":""}</p>}
      {tables.find(t=>t.id===tableId)?.parsed.warnings.map(w=><Notice key={w} tone="warning">{w}</Notice>)}
      <label>Tìm trong dữ liệu<input value={search} onChange={e=>{setSearch(e.target.value);setPage(0);}}/></label>
      {loading?<Spinner/>:preview&&<><p>{preview.total} dòng khớp điều kiện; hiển thị {preview.items.length} dòng.</p>
        <DataTable rows={rows} columns={fields.filter(f=>!f.startsWith('_')&&f!=="source_provenance"&&f!=="source_row_id").map(field=>({accessorKey:field,header:tables.find(t=>t.id===tableId)?.parsed.columns.find(c=>c.id===field)?.name||field,cell:info=>formatValue(info.getValue())}))}/>
        <div className="agent-pagination"><button className="button secondary" disabled={!page} onClick={()=>setPage(Math.max(0,page-25))}>Dòng trước</button><span>Trang {Math.floor(page/25)+1}</span><button className="button secondary" disabled={page+25>=preview.total} onClick={()=>setPage(page+25)}>Dòng tiếp</button></div></>}
      <details><summary>Kiểm tra thủ công khi cần</summary><p>Dùng khi cần tự chỉnh ánh xạ hoặc xem các lựa chọn nâng cao; không gọi AI chỉ để mở.</p><button className="button secondary" onClick={()=>onManual({...context,dataset_id:active.current})}>Mở kiểm tra và ánh xạ thủ công</button></details>
    </>}
  </Modal>;
}
