import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  BellRing,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Database,
  FileSpreadsheet,
  FolderOpen,
  GitCompareArrows,
  Layers3,
  LayoutDashboard,
  Menu,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import { api } from "./api";
import {
  Badge,
  DataTable,
  formatValue,
  Modal,
  Notice,
  Spinner,
} from "./components";
import { MappingStudio } from "./MappingStudio";
import {
  errorText,
  jobKind,
  warningText,
  qualityText,
  statusText,
  type Canonical,
  type Dataset,
  type DocumentArtifact,
  type Job,
  type Mapping,
  type Preview,
  type Profile,
  type Project,
  type ProjectSummary,
  type Table,
  type WorkspaceSettings,
} from "./types";

type Page = "home" | "data" | "settings";
type Tab = "explore" | "mapping" | "normalize";
type View = "parsed" | "raw" | "canonical" | "errors";

export function App() {
  const [page, setPage] = useState<Page>("home");
  const [tab, setTab] = useState<Tab>("explore");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState(
    localStorage.getItem("studio.project") || "",
  );
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetOffset, setDatasetOffset] = useState(0);
  const [datasetTotal, setDatasetTotal] = useState(0);
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [tables, setTables] = useState<Table[]>([]);
  const [documentState, setDocumentState] = useState<{
    datasetId: string;
    items: DocumentArtifact[];
  }>({datasetId: "", items: []});
  const [tableId, setTableId] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [canonicals, setCanonicals] = useState<Canonical[]>([]);
  const [canonicalId, setCanonicalId] = useState("");
  const [view, setView] = useState<View>("parsed");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewQuery, setPreviewQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [workspace, setWorkspace] = useState<WorkspaceSettings | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [projectOpen, setProjectOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newScope, setNewScope] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [encoding, setEncoding] = useState("utf-8-sig");
  const [delimiter, setDelimiter] = useState("");
  const [headerRow, setHeaderRow] = useState("");
  const [requestAiMapping, setRequestAiMapping] = useState(true);
  const [sidebar, setSidebar] = useState(false);
  const [evidenceId, setEvidenceId] = useState("");
  const [evidenceRow, setEvidenceRow] = useState<number | undefined>();
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(
    null,
  );
  const scopeRef = useRef({ projectId, datasetId, tableId, datasetOffset });
  scopeRef.current = { projectId, datasetId, tableId, datasetOffset };
  const fileInput = useRef<HTMLInputElement>(null);
  const selectedDataset = datasets.find((d) => d.id === datasetId);
  const table = tables.find((t) => t.id === tableId);
  const project = projects.find((p) => p.id === projectId);
  const currentCanonical = canonicals.find((c) => c.id === canonicalId);
  const activeMapping = mappings.find((m) => m.id === table?.active_mapping_id);

  const run = useCallback(async (task: () => Promise<void>) => {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await task();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Không thể thực hiện thao tác.",
      );
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        await api("/session");
        const [p, s] = await Promise.all([
          api<{ items: Project[] }>("/projects"),
          api<WorkspaceSettings>("/settings"),
        ]);
        if (!mounted) return;
        setProjects(p.items);
        setWorkspace(s);
        setReady(true);
        setProjectId((old) =>
          p.items.some((p) => p.id === old) ? old : p.items[0]?.id || "",
        );
      } catch (err) {
        if (mounted)
          setError(
            err instanceof Error ? err.message : "Không kết nối được backend.",
          );
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const refreshProject = useCallback(async () => {
    if (!projectId) {
      setDatasets([]);
      setJobs([]);
      return;
    }
    const [d, j, s] = await Promise.all([
      api<{ items: Dataset[]; total: number }>(
        `/datasets?project_id=${projectId}&offset=${datasetOffset}&limit=25`,
      ),
      api<{ items: Job[] }>(`/jobs?project_id=${projectId}`),
      api<ProjectSummary>(`/projects/${projectId}/summary`),
    ]);
    if (
      scopeRef.current.projectId !== projectId ||
      scopeRef.current.datasetOffset !== datasetOffset
    )
      return;
    setDatasets(d.items);
    setDatasetTotal(d.total);
    setJobs(j.items);
    setSummary(s);
  }, [projectId, datasetOffset]);
  useEffect(() => {
    if (!ready || page !== "settings") return;
    let current = true;
    void api<WorkspaceSettings>("/settings")
      .then((value) => {
        if (current) setWorkspace(value);
      })
      .catch((err) => {
        if (current) setError(err.message);
      });
    return () => {
      current = false;
    };
  }, [ready, page]);
  useEffect(() => {
    localStorage.setItem("studio.project", projectId);
    setDatasetId("");
    setTableId("");
    setTables([]);
    setProfile(null);
    setMappings([]);
    setPreview(null);
    setDatasetOffset(0);
  }, [projectId]);
  useEffect(() => {
    if (!ready) return;
    void refreshProject().catch((err) => setError(String(err.message)));
    const timer = setInterval(
      () => void refreshProject().catch((err) => setError(String(err.message))),
      3000,
    );
    return () => clearInterval(timer);
  }, [ready, refreshProject]);

  const loadTables = useCallback(async () => {
    if (!datasetId) {
      setTables([]);
      return;
    }
    const result = await api<{ items: Table[] }>(
      `/datasets/${datasetId}/tables`,
    );
    if (scopeRef.current.datasetId !== datasetId) return;
    setTables(result.items);
    setTableId((old) =>
      result.items.some((t) => t.id === old) ? old : result.items[0]?.id || "",
    );
  }, [datasetId]);
  useEffect(() => {
    void loadTables().catch((err) => setError(err.message));
  }, [loadTables, selectedDataset?.status]);
  useEffect(() => {
    if (!datasetId || !/\.(pdf|docx)$/i.test(selectedDataset?.name || "")) return;
    let current = true;
    void api<DocumentArtifact[]>(`/datasets/${datasetId}/documents`)
      .then((items) => { if (current) setDocumentState({datasetId, items}); })
      .catch((err) => { if (current) setError(err.message); });
    return () => { current = false; };
  }, [datasetId, selectedDataset?.name, selectedDataset?.status]);

  const loadDetails = useCallback(async () => {
    if (!tableId || !datasetId) return;
    const [p, m, a] = await Promise.all([
      api<Profile>(`/tables/${tableId}/profile`),
      api<{ items: Mapping[] }>(`/tables/${tableId}/mappings`),
      api<{ canonical_datasets: Canonical[] }>(
        `/datasets/${datasetId}/artifacts`,
      ),
    ]);
    if (
      scopeRef.current.tableId !== tableId ||
      scopeRef.current.datasetId !== datasetId
    )
      return;
    setProfile(p);
    setMappings(m.items);
    setCanonicals(a.canonical_datasets);
    const candidates = a.canonical_datasets.filter(
      (c) => c.source_table_id === tableId,
    );
    setCanonicalId((old) =>
      candidates.some((c) => c.id === old && !c.stale)
        ? old
        : candidates.filter((c) => !c.stale).at(-1)?.id ||
          candidates.at(-1)?.id ||
          "",
    );
  }, [tableId, datasetId]);
  useEffect(() => {
    setOffset(0);
    setSearch("");
    setView("parsed");
    setPreview(null);
    void loadDetails().catch((err) => setError(err.message));
  }, [loadDetails]);

  useEffect(() => {
    if (!tableId || (["canonical", "errors"].includes(view) && !canonicalId)) {
      setPreview(null);
      return;
    }
    let current = true;
    const params = new URLSearchParams({
      kind: view,
      offset: String(offset),
      limit: "25",
      search,
    });
    if (canonicalId) params.set("canonical_id", canonicalId);
    void api<Preview>(`/tables/${tableId}/preview?${params}`)
      .then((p) => {
        if (current) {
          setPreview(p);
          setPreviewQuery(
            JSON.stringify([tableId, view, canonicalId, offset, search]),
          );
        }
      })
      .catch((err) => {
        if (current) setError(err.message);
      });
    return () => {
      current = false;
    };
  }, [tableId, view, canonicalId, offset, search]);

  useEffect(() => {
    if (!evidenceId) return;
    let current = true;
    setEvidence(null);
    void api<Record<string, unknown>>(
      `/evidence/${evidenceId}${evidenceRow ? `?row=${evidenceRow}` : ""}`,
    )
      .then((value) => {
        if (current) setEvidence(value);
      })
      .catch((err) => {
        if (current) setError(err.message);
      });
    return () => {
      current = false;
    };
  }, [evidenceId, evidenceRow]);

  function chooseDataset(d: Dataset) {
    if (datasetId !== d.id) {
      setTables([]);
      setTableId("");
      setProfile(null);
      setMappings([]);
      setCanonicals([]);
      setPreview(null);
    }
    setDatasetId(d.id);
    setPage("data");
    setTab("explore");
    setSidebar(false);
  }
  function showEvidence(id: string, row?: number) {
    setEvidenceRow(row);
    setEvidenceId(id);
  }
  async function changed() {
    await Promise.all([refreshProject(), loadTables(), loadDetails()]);
  }
  async function createProject() {
    const p = await api<Project>("/projects", {
      method: "POST",
      body: JSON.stringify({ name: newName, business_scope: newScope }),
    });
    setProjects((old) => [p, ...old]);
    setDatasets([]);
    setJobs([]);
    setSummary(null);
    setProjectId(p.id);
    setProjectOpen(false);
    setNewName("");
    setNewScope("");
    setSuccess("Đã tạo dự án. Bạn có thể tải dữ liệu đầu tiên.");
  }
  async function upload() {
    const form = new FormData();
    form.append("project_id", projectId);
    form.append("request_ai_mapping", String(requestAiMapping));
    files.forEach((f) => form.append("files", f));
    form.append(
      "parse_options",
      JSON.stringify({
        encoding,
        delimiter: delimiter || null,
        header_row: headerRow ? Number(headerRow) : null,
      }),
    );
    const result = await api<{ items: (Dataset & { reused: boolean })[] }>(
      "/datasets/uploads",
      { method: "POST", body: form },
    );
    await refreshProject();
    setUploadOpen(false);
    setFiles([]);
    setTables([]);
    setTableId("");
    setProfile(null);
    setMappings([]);
    setCanonicals([]);
    setPreview(null);
    setDatasetId(result.items[0]?.id || "");
    setPage("data");
    setTab("explore");
    setSuccess(
      result.items.every((x) => x.reused)
        ? "Đã tìm thấy dữ liệu cùng nội dung và cấu hình trong dự án; tái sử dụng kết quả hiện có."
        : "Đã lưu tệp gốc. Worker đang đọc và phân tích dữ liệu.",
    );
  }
  async function normalize() {
    if (!activeMapping || !selectedDataset) return;
    await api(`/datasets/${selectedDataset.id}/normalize`, {
      method: "POST",
      body: JSON.stringify({ mapping_id: activeMapping.id }),
    });
    await refreshProject();
    setSuccess("Đã xếp hàng chuẩn hóa. Bấm cập nhật kết quả khi job hoàn tất.");
  }

  const previewMatchesView =
    preview?.view === (view === "raw" ? "parsed_raw_values" : view) &&
    previewQuery ===
      JSON.stringify([tableId, view, canonicalId, offset, search]);
  const previewRows = useMemo(
    () =>
      (previewMatchesView ? preview?.items || [] : []).map((row) =>
        view === "canonical"
          ? {
              ...(row.record_payload as Record<string, unknown>),
              _quality:
                (row.quality_flags as string[])
                  .map((flag) => qualityText[flag.split(":")[0]] || flag)
                  .join(", ") || "Hợp lệ",
              _source_row_id: row.source_row_id,
              _lineage: row.source_provenance,
            }
          : row,
      ),
    [preview, view, previewMatchesView],
  );
  const columns = useMemo<ColumnDef<Record<string, unknown>>[]>(() => {
    const keys =
      view === "canonical"
        ? Object.keys(previewRows[0] || {}).filter(
            (k) => !["_lineage", "_source_row_id"].includes(k),
          )
        : (preview?.columns || []).filter(
            (k) => !["_source_row_id", "source_row_id"].includes(k),
          );
    const cols: ColumnDef<Record<string, unknown>>[] = keys.map((key) => ({
      accessorKey: key,
      header:
        table?.parsed.columns.find((c) => c.id === key)?.name ||
        mappings
          .find((m) => m.id === currentCanonical?.mapping_revision_id)
          ?.schema.fields.find((f) => f.id === key)?.name ||
        (
          {
            _source_row: "Dòng nguồn",
            source_row: "Dòng nguồn",
            field: "Trường dữ liệu",
            _quality: "Chất lượng",
            raw_value: "Giá trị gốc",
            value_state: "Loại giá trị",
            code: "Mã cảnh báo",
          } as Record<string, string>
        )[key] ||
        key,
      cell: (info) => (
        <span
          className={info.getValue() === null ? "null-value" : ""}
          title={formatValue(info.getValue())}
        >
          {["code", "value_state"].includes(key)
            ? qualityText[String(info.getValue())] ||
              formatValue(info.getValue())
            : formatValue(info.getValue())}
        </span>
      ),
    }));
    if (table)
      cols.push({
        id: "evidence",
        header: "Nguồn gốc",
        cell: (info) => (
          <button
            className="text-button"
            onClick={() => {
              const row = info.row.original;
              const lineage = row._lineage as { row: number }[] | undefined;
              showEvidence(
                `${table.id}:${table.parsed.columns[0].id}`,
                Number(
                  row._source_row || row.source_row || lineage?.[0]?.row,
                ) || undefined,
              );
            }}
          >
            <FolderOpen size={15} />
            Xem nguồn
          </button>
        ),
      });
    return cols;
  }, [previewRows, preview, view, table, mappings, currentCanonical]);

  return (
    <div className="app-shell">
      {sidebar && (
        <button
          className="sidebar-scrim"
          aria-label="Đóng thanh điều hướng"
          onClick={() => setSidebar(false)}
        />
      )}
      <aside className={`sidebar ${sidebar ? "sidebar-open" : ""}`}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("home");
          }}
        >
          <span className="brand-symbol">
            <Layers3 size={23} />
          </span>
          <span>
            Reconciliation<span className="brand-sub">STUDIO</span>
          </span>
        </a>
        <div className="workspace-switch">
          <span className="workspace-icon">LS</span>
          <div>
            <strong>Local workspace</strong>
            <small>Dữ liệu của bạn · lưu bền vững</small>
          </div>
          <ShieldCheck size={16} />
        </div>
        <span className="nav-caption">KHÔNG GIAN LÀM VIỆC</span>
        <nav aria-label="Điều hướng chính">
          <button
            className={page === "home" ? "active" : ""}
            onClick={() => {
              setPage("home");
              setSidebar(false);
            }}
          >
            <LayoutDashboard size={19} />
            Tổng quan
          </button>
          <button
            className={page === "data" ? "active" : ""}
            onClick={() => {
              setPage("data");
              setSidebar(false);
            }}
          >
            <Database size={19} />
            Dữ liệu<span className="nav-count">{datasets.length}</span>
          </button>
          <div className="future-nav">
            <GitCompareArrows size={19} />
            <span>Đối soát</span>
            <small>Sắp có</small>
          </div>
          <div className="future-nav">
            <BellRing size={19} />
            <span>Ngoại lệ</span>
            <small>Sắp có</small>
          </div>
          <div className="future-nav">
            <ArrowDownToLine size={19} />
            <span>Báo cáo</span>
            <small>Sắp có</small>
          </div>
          <div className="future-nav">
            <Sparkles size={19} />
            <span>Trợ lý AI</span>
            <small>Sắp có</small>
          </div>
        </nav>
        <div className="sidebar-bottom">
          <div className="local-card">
            <ShieldCheck size={20} />
            <strong>Dữ liệu được kiểm soát</strong>
            <p>
              Cloud đang{" "}
              {workspace?.policy.allow_external_ai ? "được cấp phép" : "tắt"}.
              AI đề xuất, bạn xác nhận.
            </p>
          </div>
          <button
            className={`settings-nav ${page === "settings" ? "active" : ""}`}
            onClick={() => {
              setPage("settings");
              setSidebar(false);
            }}
          >
            <Settings2 size={18} />
            Cài đặt
          </button>
          <div className="profile">
            <span>LC</span>
            <div>
              <strong>Người dùng local</strong>
              <small>Workspace owner</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button menu-button"
              aria-label="Mở điều hướng"
              onClick={() => setSidebar(true)}
            >
              <Menu size={22} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>
              {page === "home"
                ? "Tổng quan"
                : page === "data"
                  ? "Dữ liệu"
                  : "Cài đặt"}
            </strong>
          </div>
          <div className="topbar-end">
            <span className="connection">
              <span />
              {ready ? "Hệ thống đã kết nối" : "Đang kết nối"}
            </span>
            <span className="avatar">LC</span>
          </div>
        </header>
        <main id="main-content">
          <div className="page-heading">
            <div>
              <span className="eyebrow">AI RECONCILIATION STUDIO</span>
              <h1>
                {page === "home"
                  ? "Nền tảng dữ liệu của bạn"
                  : page === "data"
                    ? "Quản lý dữ liệu"
                    : "Cài đặt không gian làm việc"}
              </h1>
              <p>
                {page === "home"
                  ? "Từ tệp nguồn đến dữ liệu chuẩn hóa — rõ ràng ở từng bước."
                  : page === "data"
                    ? "Khám phá nguồn, kiểm tra đề xuất và chuẩn bị dữ liệu đáng tin cậy."
                    : "Chính sách xử lý và giới hạn đang áp dụng từ backend."}
              </p>
            </div>
            <div className="heading-actions">
              {page !== "settings" && (
                <button
                  className={`button ${page === "data" && datasetId && tab !== "explore" ? "secondary" : "primary"}`}
                  disabled={!ready || busy}
                  onClick={() =>
                    projectId ? setUploadOpen(true) : setProjectOpen(true)
                  }
                >
                  <Upload size={17} />
                  {projectId ? "Tải dữ liệu" : "Tạo dự án đầu tiên"}
                </button>
              )}
            </div>
          </div>
          {error && (
            <Notice tone="error">
              <div className="notice-content">
                {error}
                <button
                  className="icon-button"
                  aria-label="Ẩn thông báo lỗi"
                  onClick={() => setError("")}
                >
                  <X size={16} />
                </button>
              </div>
            </Notice>
          )}
          {success && <Notice tone="success">{success}</Notice>}
          {!ready && !error && <Spinner />}
          {ready && page !== "settings" && (
            <div className="project-bar">
              <label htmlFor="project-select">
                <FolderOpen size={17} />
                Dự án
              </label>
              <select
                id="project-select"
                value={projectId}
                onChange={(e) => {
                  setDatasets([]);
                  setJobs([]);
                  setSummary(null);
                  setDatasetId("");
                  setTables([]);
                  setTableId("");
                  setProfile(null);
                  setMappings([]);
                  setCanonicals([]);
                  setPreview(null);
                  setProjectId(e.target.value);
                }}
              >
                <option value="" disabled>
                  Chọn dự án
                </option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <button
                className="text-button"
                onClick={() => setProjectOpen(true)}
              >
                + Tạo dự án
              </button>
              {project && (
                <span className="scope-label">{project.business_scope}</span>
              )}
            </div>
          )}
          {ready && page === "home" && (
            <>
              {datasets.length === 0 ? (
                <section className="welcome-card">
                  <div className="welcome-copy">
                    <span className="pill">
                      <Sparkles size={14} />
                      AI SMART SETUP
                    </span>
                    <h2>
                      Khởi đầu từ dữ liệu.
                      <br />
                      <span>Sẵn sàng cho điều tiếp theo.</span>
                    </h2>
                    <p>
                      Tải CSV hoặc Excel lên. Hệ thống đọc cấu trúc, phân tích
                      chất lượng và dùng{" "}
                      {workspace?.mapping_ai_provider === "GEMINI" ? "Gemini" : "Qwen"}{" "}
                      để đề xuất ánh xạ. Quyết định cuối
                      cùng luôn thuộc về bạn.
                    </p>
                    <div className="welcome-points">
                      <span>
                        <CheckCheck size={16} />
                        Giữ nguyên tệp nguồn
                      </span>
                      <span>
                        <CheckCheck size={16} />
                        Truy vết từng dòng
                      </span>
                      <span>
                        <CheckCheck size={16} />
                        Lưu quyết định đã duyệt
                      </span>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => {
                        setPage("data");
                      }}
                    >
                      Tìm hiểu quy trình chuẩn bị dữ liệu{" "}
                      <ArrowRight size={16} />
                    </button>
                  </div>
                  <div
                    className="flow-illustration"
                    aria-label="Quy trình từ tệp nguồn đến dữ liệu chuẩn hóa"
                  >
                    <div className="flow-node">
                      <span className="node-icon">
                        <FileSpreadsheet size={23} />
                      </span>
                      <div>
                        <strong>Tệp nguồn</strong>
                        <small>CSV · XLSX</small>
                      </div>
                      <ShieldCheck size={18} />
                    </div>
                    <div className="flow-line" />
                    <div className="flow-node flow-ai">
                      <span className="node-icon">
                        <Sparkles size={23} />
                      </span>
                      <div>
                        <strong>AI Smart Setup</strong>
                        <small>Đề xuất · kiểm tra · xác nhận</small>
                      </div>
                    </div>
                    <div className="flow-line" />
                    <div className="flow-node">
                      <span className="node-icon mint">
                        <Database size={23} />
                      </span>
                      <div>
                        <strong>Dữ liệu chuẩn hóa</strong>
                        <small>Có kiểu · có nguồn gốc</small>
                      </div>
                      <CheckCheck size={18} />
                    </div>
                  </div>
                </section>
              ) : (
                <section className="stats-grid">
                  <Stat
                    icon={<FileSpreadsheet />}
                    value={summary?.dataset_count ?? 0}
                    label="Nguồn dữ liệu"
                  />
                  <Stat
                    icon={<Layers3 />}
                    value={summary?.mapping_review_count ?? 0}
                    label="Bảng cần xác nhận"
                  />
                  <Stat
                    icon={<CheckCheck />}
                    value={summary?.ready_canonical_count ?? 0}
                    label="Bảng đã chuẩn hóa"
                  />
                  <Stat
                    icon={<Sparkles />}
                    value={summary?.active_job_count ?? 0}
                    label="Tác vụ đang xử lý"
                  />
                </section>
              )}
              <div className="section-heading">
                <div>
                  <h2>Quy trình chuẩn bị dữ liệu</h2>
                  <p>
                    Một luồng thống nhất, từ bản gốc đến dữ liệu có thể sử dụng.
                  </p>
                </div>
                <span className="subtle">3 bước rõ ràng</span>
              </div>
              <section className="steps-grid">
                {[
                  {
                    title: "Tải nguồn dữ liệu",
                    icon: <Upload size={21} />,
                    text: "CSV, Excel nhiều sheet. Tệp gốc được lưu bất biến trong workspace.",
                  },
                  {
                    title: "Kiểm tra ánh xạ",
                    icon: <Sparkles size={21} />,
                    text: "Xem đề xuất AI, dữ liệu mẫu và xác nhận những trường cần sử dụng.",
                  },
                  {
                    title: "Chuẩn hóa & khám phá",
                    icon: <Database size={21} />,
                    text: "Xem kết quả có kiểu dữ liệu, lỗi chuyển đổi và nguồn gốc từng dòng.",
                  },
                ].map((s, i) => (
                  <article className="step-card" key={s.title}>
                    <div className="step-top">
                      <span>{s.icon}</span>
                      <small>0{i + 1}</small>
                    </div>
                    <h3>{s.title}</h3>
                    <p>{s.text}</p>
                  </article>
                ))}
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Dữ liệu gần đây</h2>
                    <p>Tiếp tục công việc từ nơi bạn đã dừng.</p>
                  </div>
                  <button
                    className="text-button"
                    onClick={() => setPage("data")}
                  >
                    Xem tất cả <ArrowRight size={15} />
                  </button>
                </div>
                {datasets.length ? (
                  <DatasetList
                    items={datasets.slice(0, 5)}
                    onSelect={chooseDataset}
                  />
                ) : (
                  <div className="empty-state">
                    <FileSpreadsheet size={31} />
                    <h3>Chưa có nguồn dữ liệu</h3>
                    <p>Tạo dự án và tải tệp đầu tiên để bắt đầu.</p>
                    <span className="supported">
                      CSV & XLSX · Tối đa{" "}
                      {workspace ? workspace.max_upload_bytes / 1048576 : 20}{" "}
                      MB/tệp
                    </span>
                  </div>
                )}
              </section>
            </>
          )}
          {ready && page === "data" && (
            <>
              {datasets.length === 0 ? (
                <section className="panel empty-state">
                  <Database size={36} />
                  <h2>Mọi nguồn dữ liệu, trong một nơi</h2>
                  <p>
                    Chọn Tải dữ liệu để thêm CSV hoặc XLSX. PDF/DOCX cần quyền
                    và allowance riêng; bản trích xuất luôn cần kiểm tra.
                  </p>
                </section>
              ) : (
                <>
                  <section className="panel dataset-panel">
                    <div className="panel-heading">
                      <h2>
                        Nguồn trong dự án{" "}
                        <span className="count">{datasetTotal}</span>
                      </h2>
                    </div>
                    <DatasetList
                      items={datasets}
                      onSelect={chooseDataset}
                      selected={datasetId}
                    />
                    {datasetTotal > 25 && (
                      <div className="pagination list-pagination">
                        <span>
                          Nguồn {datasetOffset + 1}–
                          {Math.min(datasetOffset + 25, datasetTotal)} /{" "}
                          {datasetTotal}
                        </span>
                        <div>
                          <button
                            className="icon-button"
                            aria-label="Trang nguồn trước"
                            disabled={datasetOffset === 0}
                            onClick={() =>
                              setDatasetOffset(Math.max(0, datasetOffset - 25))
                            }
                          >
                            <ChevronLeft size={18} />
                          </button>
                          <button
                            className="icon-button"
                            aria-label="Trang nguồn sau"
                            disabled={datasetOffset + 25 >= datasetTotal}
                            onClick={() => setDatasetOffset(datasetOffset + 25)}
                          >
                            <ChevronRight size={18} />
                          </button>
                        </div>
                      </div>
                    )}
                  </section>
                  {selectedDataset && (
                    <section className="panel detail-panel">
                      <div className="panel-heading">
                        <div>
                          <span className="eyebrow">NGUỒN ĐANG CHỌN</span>
                          <h2>{selectedDataset.name}</h2>
                        </div>
                        <Badge status={selectedDataset.status} />
                      </div>
                      {tables.length === 0 ? (
                        <div className="empty-state">
                          {/\.(pdf|docx)$/i.test(selectedDataset.name) ? (
                            <div>
                              <Notice tone="warning">
                                Bản trích xuất chưa được xác minh. Không tự dùng số tiền trong tài liệu để đối soát.
                              </Notice>
                              {documentState.datasetId === datasetId && (
                                <DocumentPreview documents={documentState.items} />
                              )}
                            </div>
                          ) : (
                          <>
                          {["UPLOADED", "PARSING"].includes(
                            selectedDataset.status,
                          ) ? (
                            <Spinner />
                          ) : (
                            <Notice tone="warning">
                              Chưa có bảng được công bố. Kiểm tra trạng thái tác
                              vụ bên dưới.
                            </Notice>
                          )}
                          </>
                          )}
                        </div>
                      ) : (
                        <>
                          <div className="table-picker">
                            <label>
                              Bảng / sheet
                              <select
                                value={tableId}
                                onChange={(e) => {
                                  setProfile(null);
                                  setMappings([]);
                                  setCanonicals([]);
                                  setPreview(null);
                                  setTableId(e.target.value);
                                }}
                              >
                                {tables.map((t) => (
                                  <option key={t.id} value={t.id}>
                                    {t.sheet} · {t.row_count} dòng
                                  </option>
                                ))}
                              </select>
                            </label>
                            <span>
                              {table?.parsed.columns.length} cột · Tiêu đề ở
                              dòng {table?.parsed.header_row}
                            </span>
                          </div>
                          <div
                            className="tabs"
                            role="tablist"
                            aria-label="Xử lý dữ liệu"
                          >
                            {(
                              [
                                ["explore", "Khám phá dữ liệu"],
                                ["mapping", "AI Smart Setup"],
                                ["normalize", "Chuẩn hóa"],
                              ] as const
                            ).map(([key, label]) => (
                              <button
                                role="tab"
                                aria-selected={tab === key}
                                className={tab === key ? "selected" : ""}
                                key={key}
                                onClick={() => setTab(key)}
                              >
                                {key === "mapping" && <Sparkles size={15} />}
                                {label}
                              </button>
                            ))}
                          </div>
                          <div className="tab-content">
                            {tab === "mapping" && table && profile && (
                              <MappingStudio
                                table={table}
                                profile={profile}
                                mappings={mappings}
                                busy={busy}
                                run={run}
                                onApproved={async () => {
                                  await changed();
                                  setSuccess("Đã cập nhật ánh xạ.");
                                }}
                                onEvidence={showEvidence}
                              />
                            )}
                            {tab === "normalize" && (
                              <>
                                <div className="section-heading">
                                  <div>
                                    <h2>Chuẩn hóa theo ánh xạ đã duyệt</h2>
                                    <p>
                                      Số tiền được xử lý bằng Decimal; giá trị
                                      lỗi và null được lưu riêng.
                                    </p>
                                  </div>
                                  <button
                                    className="button primary"
                                    disabled={
                                      busy ||
                                      !activeMapping ||
                                      activeMapping.status !== "APPROVED"
                                    }
                                    onClick={() => void run(normalize)}
                                  >
                                    <Layers3 size={17} />
                                    Chuẩn hóa dữ liệu
                                  </button>
                                </div>
                                {!activeMapping && (
                                  <Notice>
                                    Cần xác nhận ánh xạ trước.{" "}
                                    <button
                                      className="text-button"
                                      onClick={() => setTab("mapping")}
                                    >
                                      Mở AI Smart Setup <ArrowRight size={14} />
                                    </button>
                                  </Notice>
                                )}
                                <button
                                  className="button secondary compact"
                                  onClick={() => void run(changed)}
                                  disabled={busy}
                                >
                                  Cập nhật kết quả
                                </button>
                                <div className="canonical-list">
                                  {canonicals
                                    .filter(
                                      (c) => c.source_table_id === tableId,
                                    )
                                    .map((c) => (
                                      <article
                                        key={c.id}
                                        className="canonical-card"
                                      >
                                        <div>
                                          <Badge status={c.quality_status} />
                                          {c.stale && (
                                            <span className="stale">
                                              Revision cũ · không dùng cho xử lý
                                              mới
                                            </span>
                                          )}
                                          <p>
                                            {c.row_count} dòng · {c.valid_count}{" "}
                                            hợp lệ · {c.invalid_count} cần kiểm
                                            tra
                                          </p>
                                        </div>
                                        <button
                                          className="button secondary"
                                          onClick={() => {
                                            setCanonicalId(c.id);
                                            setView("canonical");
                                            setTab("explore");
                                            setOffset(0);
                                          }}
                                        >
                                          Xem kết quả <ArrowRight size={15} />
                                        </button>
                                      </article>
                                    ))}
                                </div>
                              </>
                            )}
                            {tab === "explore" && (
                              <>
                                <div className="explorer-tools">
                                  <div
                                    className="view-toggle"
                                    role="group"
                                    aria-label="Lớp dữ liệu"
                                  >
                                    {(
                                      [
                                        ["parsed", "Đã đọc"],
                                        ["raw", "Giá trị gốc"],
                                        ["canonical", "Chuẩn hóa"],
                                        ["errors", "Cảnh báo / lỗi"],
                                      ] as const
                                    ).map(([key, label]) => (
                                      <button
                                        key={key}
                                        disabled={
                                          ["canonical", "errors"].includes(
                                            key,
                                          ) && !canonicalId
                                        }
                                        className={view === key ? "chosen" : ""}
                                        onClick={() => {
                                          setView(key);
                                          setOffset(0);
                                        }}
                                      >
                                        {label}
                                      </button>
                                    ))}
                                  </div>
                                  <label className="search-input">
                                    <Search size={17} />
                                    <input
                                      aria-label="Tìm trong bảng"
                                      placeholder="Tìm giá trị…"
                                      value={search}
                                      onChange={(e) => {
                                        setSearch(e.target.value);
                                        setOffset(0);
                                      }}
                                    />
                                  </label>
                                </div>
                                {["canonical", "errors"].includes(view) && (
                                  <label className="canonical-select">
                                    Phiên bản kết quả
                                    <select
                                      value={canonicalId}
                                      onChange={(e) => {
                                        setCanonicalId(e.target.value);
                                        setOffset(0);
                                      }}
                                    >
                                      {canonicals
                                        .filter(
                                          (c) => c.source_table_id === tableId,
                                        )
                                        .map((c, i) => (
                                          <option key={c.id} value={c.id}>
                                            Kết quả {i + 1} ·{" "}
                                            {statusText[c.quality_status] ||
                                              c.quality_status}
                                            {c.stale ? " · Đã cũ" : ""}
                                          </option>
                                        ))}
                                    </select>
                                  </label>
                                )}
                                {currentCanonical?.stale &&
                                  ["canonical", "errors"].includes(view) && (
                                    <Notice tone="warning">
                                      Kết quả lịch sử thuộc ánh xạ cũ. Cần chuẩn
                                      hóa lại theo revision hiện hành.
                                    </Notice>
                                  )}
                                {view === "raw" && (
                                  <Notice>
                                    Giá trị đọc trực tiếp từ ô nguồn; tệp bytes
                                    gốc được giữ bất biến. Không chạy công thức
                                    Excel.
                                  </Notice>
                                )}
                                {table?.parsed.warnings.map((w) => (
                                  <Notice tone="warning" key={w}>
                                    {warningText[w] || w}
                                  </Notice>
                                ))}
                                {preview && previewMatchesView ? (
                                  <>
                                    <DataTable
                                      rows={previewRows}
                                      columns={columns}
                                    />
                                    <div className="pagination">
                                      <span>
                                        {preview.total === 0
                                          ? "0 dòng"
                                          : `Dòng ${offset + 1}–${Math.min(offset + 25, preview.total)} / ${preview.total}`}
                                      </span>
                                      <div>
                                        <button
                                          className="icon-button"
                                          aria-label="Trang trước"
                                          disabled={offset === 0}
                                          onClick={() =>
                                            setOffset(Math.max(0, offset - 25))
                                          }
                                        >
                                          <ChevronLeft size={18} />
                                        </button>
                                        <button
                                          className="icon-button"
                                          aria-label="Trang sau"
                                          disabled={
                                            offset + 25 >= preview.total
                                          }
                                          onClick={() => setOffset(offset + 25)}
                                        >
                                          <ChevronRight size={18} />
                                        </button>
                                      </div>
                                    </div>
                                  </>
                                ) : (
                                  <Spinner />
                                )}
                                {profile && (
                                  <details className="profile-details">
                                    <summary>
                                      <CircleHelp size={16} />
                                      Thống kê dữ liệu nguồn
                                    </summary>
                                    <div className="profile-grid">
                                      {profile.columns.map((c) => (
                                        <div key={c.column_id}>
                                          <strong>{c.name}</strong>
                                          <span>
                                            {c.null_count} null ·{" "}
                                            {c.empty_count} chuỗi rỗng
                                          </span>
                                          <span>
                                            {c.distinct_count} giá trị khác nhau
                                            · {c.duplicate_count} lặp
                                          </span>
                                          <small>
                                            {c.identifier_candidate
                                              ? "Ứng viên định danh — giữ nguyên chuỗi"
                                              : c.type_candidates.join(", ")}
                                          </small>
                                        </div>
                                      ))}
                                    </div>
                                  </details>
                                )}
                              </>
                            )}
                          </div>
                        </>
                      )}
                    </section>
                  )}
                </>
              )}
            </>
          )}
          {ready && page === "settings" && workspace && (
            <section className="settings-grid">
              <div className="panel">
                <div className="panel-heading">
                  <ShieldCheck size={23} />
                  <h2>Chính sách dữ liệu</h2>
                </div>
                <dl>
                  <dt>Workspace</dt>
                  <dd>{workspace.workspace_name}</dd>
                  <dt>Chế độ mặc định</dt>
                  <dd>{workspace.policy.mode}</dd>
                  <dt>Gemini cloud</dt>
                  <dd>
                    {workspace.policy.allow_external_ai ? "Có quyền" : "Tắt"} ·{" "}
                    {workspace.gemini_requests_remaining} request còn lại ·{" "}
                    {workspace.gemini_requests_used} đã dùng
                  </dd>
                  <dt>Parser cloud</dt>
                  <dd>
                    {workspace.policy.allow_cloud_parsing ? "Có quyền" : "Tắt"}{" "}
                    · {workspace.policy.parser_request_budget} request
                  </dd>
                </dl>
                <Notice>
                  Thay đổi quyền cloud cần cấu hình và phê duyệt của chủ
                  workspace. Không tự chuyển provider khi Qwen lỗi.
                </Notice>
              </div>
              <div className="panel">
                <div className="panel-heading">
                  <Settings2 size={23} />
                  <h2>Giới hạn xử lý</h2>
                </div>
                <dl>
                  <dt>Qwen</dt>
                  <dd>
                    {workspace.qwen_configured
                      ? `Đã cấu hình · ${workspace.qwen_model}`
                      : "Chưa cấu hình"}
                  </dd>
                  <dt>Provider đề xuất ánh xạ</dt>
                  <dd>
                    {workspace.mapping_ai_provider === "GEMINI" ? "Gemini" : "Qwen"}
                  </dd>
                  <dt>Gemini</dt>
                  <dd>
                    {workspace.gemini_configured ? workspace.gemini_model : "Chưa cấu hình khóa"}
                  </dd>
                  <dt>Mỗi tệp</dt>
                  <dd>{workspace.max_upload_bytes / 1048576} MB</dd>
                  <dt>Mỗi lần tải</dt>
                  <dd>{workspace.max_upload_files} tệp</dd>
                  <dt>Mỗi bảng</dt>
                  <dd>{workspace.max_rows.toLocaleString("vi-VN")} dòng</dd>
                </dl>
                <Notice>
                  Khóa và địa chỉ provider chỉ được quản lý trên backend.
                  Mỗi lần gọi Gemini tiêu thụ ngân sách, kể cả lỗi hoặc thử lại. Parser cloud có quyền riêng.
                </Notice>
              </div>
            </section>
          )}
          {ready && jobs.length > 0 && page !== "settings" && (
            <section className="panel jobs-panel">
              <div className="panel-heading">
                <div>
                  <h2>Hoạt động xử lý</h2>
                  <p>Trạng thái thực tế từ worker.</p>
                </div>
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() => void run(changed)}
                >
                  Cập nhật
                </button>
              </div>
              {jobs.slice(0, 6).map((j) => (
                <div className="job-row" key={j.id}>
                  <span className="job-icon">
                    {j.kind === "mapping" ? (
                      <Sparkles size={17} />
                    ) : (
                      <Layers3 size={17} />
                    )}
                  </span>
                  <div>
                    <strong>
                      {j.kind === "mapping" &&
                      j.result?.source === "APPROVED_TEMPLATE"
                        ? "Gợi ý từ mẫu đã duyệt"
                        : jobKind[j.kind] || j.kind}
                    </strong>
                    {j.error_code && (
                      <p className="job-error">
                        {errorText[j.error_code] ||
                          `Xử lý bị chặn: ${j.error_code}`}
                      </p>
                    )}
                  </div>
                  <Badge status={j.status} />
                </div>
              ))}
            </section>
          )}
          <footer>
            <ShieldCheck size={14} />
            Tệp gốc bất biến · Ánh xạ có phê duyệt · Dữ liệu có nguồn gốc
            <span>Data Foundation</span>
          </footer>
        </main>
      </div>
      <Modal title="Tạo dự án" open={projectOpen} onOpenChange={setProjectOpen}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(createProject);
          }}
        >
          <p className="modal-description">
            Nhóm các nguồn cùng mục đích trong một phạm vi rõ ràng.
          </p>
          <label>
            Tên dự án
            <input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Ví dụ: Đơn hàng tháng 10"
              required
              maxLength={200}
            />
          </label>
          <label>
            Phạm vi nghiệp vụ
            <input
              value={newScope}
              onChange={(e) => setNewScope(e.target.value)}
              placeholder="Ví dụ: cửa hàng A · dữ liệu bán hàng"
              required
              maxLength={200}
            />
          </label>
          <p className="field-help">
            Mẫu ánh xạ chỉ được gợi ý tái sử dụng trong cùng phạm vi tương
            thích.
          </p>
          {error && <Notice tone="error">{error}</Notice>}
          <div className="modal-actions">
            <button
              type="button"
              className="button secondary"
              onClick={() => setProjectOpen(false)}
            >
              Hủy
            </button>
            <button
              className="button primary"
              disabled={busy || !newName.trim() || !newScope.trim()}
            >
              {busy ? <Spinner /> : "Tạo dự án"}
            </button>
          </div>
        </form>
      </Modal>
      <Modal
        title="Tải nguồn dữ liệu"
        open={uploadOpen}
        onOpenChange={setUploadOpen}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(upload);
          }}
        >
          <p className="modal-description">
            Tệp được lưu trong dự án <strong>{project?.name}</strong>. CSV và
            XLSX được đọc nội bộ.
          </p>
          <input
            ref={fileInput}
            className="file-input"
            type="file"
            accept=".csv,.xlsx,.pdf,.docx"
            multiple
            onChange={(e) => setFiles(Array.from(e.target.files || []))}
            aria-label="Chọn tệp dữ liệu"
          />
          <button
            type="button"
            className="dropzone"
            onClick={() => fileInput.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              setFiles(Array.from(e.dataTransfer.files));
            }}
          >
            <span>
              <Upload size={27} />
            </span>
            <strong>Kéo thả tệp vào đây</strong>
            <small>hoặc bấm để chọn từ máy tính</small>
            <em>
              CSV · XLSX · Tối đa{" "}
              {workspace ? workspace.max_upload_bytes / 1048576 : 20} MB/tệp
            </em>
          </button>
          <div className="selected-files">
            {files.map((f, i) => (
              <div key={`${f.name}-${i}`}>
                <FileSpreadsheet size={18} />
                <span>{f.name}</span>
                <small>{(f.size / 1024).toFixed(1)} KB</small>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Bỏ ${f.name}`}
                  onClick={() =>
                    setFiles((rows) => rows.filter((_, n) => n !== i))
                  }
                >
                  <X size={15} />
                </button>
              </div>
            ))}
          </div>
          <details>
            <summary>Tùy chọn đọc nâng cao</summary>
            <label className="check-label">
              <input type="checkbox" checked={requestAiMapping}
                onChange={(event) => setRequestAiMapping(event.target.checked)} />
              Dùng AI đề xuất ánh xạ trong hạn mức
            </label>
            <div className="form-grid">
              <label>
                Encoding CSV
                <select
                  value={encoding}
                  onChange={(e) => setEncoding(e.target.value)}
                >
                  <option value="utf-8-sig">UTF-8 / UTF-8 BOM</option>
                  <option value="cp1258">Windows-1258 (chọn rõ)</option>
                </select>
              </label>
              <label>
                Dấu phân cách
                <select
                  value={delimiter}
                  onChange={(e) => setDelimiter(e.target.value)}
                >
                  <option value="">Tự phát hiện</option>
                  <option value=",">Dấu phẩy</option>
                  <option value=";">Chấm phẩy</option>
                  <option value={"\t"}>Tab</option>
                  <option value="|">Gạch đứng</option>
                </select>
              </label>
              <label>
                Dòng tiêu đề
                <input
                  type="number"
                  min={1}
                  placeholder="Tự phát hiện"
                  value={headerRow}
                  onChange={(e) => setHeaderRow(e.target.value)}
                />
              </label>
            </div>
          </details>
          <Notice>
            PDF/DOCX chỉ được đọc khi có allowance riêng. Kết quả đã lưu được
            tái sử dụng; bản trích xuất không tự trở thành dữ liệu chuẩn.
          </Notice>
          {error && <Notice tone="error">{error}</Notice>}
          <div className="modal-actions">
            <button
              type="button"
              className="button secondary"
              onClick={() => setUploadOpen(false)}
            >
              Hủy
            </button>
            <button
              className="button primary"
              disabled={busy || files.length === 0}
            >
              {busy ? (
                <Spinner />
              ) : (
                <>
                  <Upload size={17} />
                  Tải {files.length || ""} tệp
                </>
              )}
            </button>
          </div>
        </form>
      </Modal>
      <Modal
        title="Bằng chứng nguồn"
        open={!!evidenceId}
        onOpenChange={(open) => {
          if (!open) setEvidenceId("");
        }}
        wide
      >
        {evidence ? (
          <>
            <div className="evidence-meta">
              <span>
                Sheet: <strong>{String(evidence.sheet)}</strong>
              </span>
              <span>Tiêu đề: dòng {String(evidence.header_row)}</span>
            </div>
            <DataTable
              rows={evidence.items as Record<string, unknown>[]}
              columns={Object.keys(
                (evidence.items as Record<string, unknown>[])[0] || {},
              ).map((key) => ({
                accessorKey: key,
                header:
                  key === "_source_row"
                    ? "Dòng nguồn"
                    : key === "_source_row_id"
                      ? "Định danh dòng"
                      : key,
                cell: (info) => formatValue(info.getValue()),
              }))}
            />
            <details>
              <summary>Chi tiết công thức / vùng dữ liệu</summary>
              <pre>
                {JSON.stringify(
                  {
                    cell_metadata: evidence.cell_metadata,
                    preamble: evidence.preamble,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </>
        ) : (
          <Spinner />
        )}
      </Modal>
    </div>
  );
}

function Stat({
  icon,
  value,
  label,
}: {
  icon: React.ReactNode;
  value: number;
  label: string;
}) {
  return (
    <article className="stat-card">
      <span>{icon}</span>
      <strong>{value}</strong>
      <p>{label}</p>
    </article>
  );
}
function DocumentPreview({ documents }: { documents: DocumentArtifact[] }) {
  return documents.map((doc) => (
    <article key={doc.artifact.id}>
      <h3>{doc.source_file.filename}</h3>
      {doc.extraction.pages.map((page) => {
        const tables = page.items.filter((item) => item.type === "table" &&
          Array.isArray(item.rows) && item.rows.every((row) => Array.isArray(row) &&
            row.every((cell) => typeof cell === "string")));
        return (
          <section key={page.page_number}>
            <h4>Trang {page.page_number}</h4>
            {tables.map((table, index) => {
              const rows = table.rows as string[][];
              return <div className="table-scroll" key={index}>
                <table className="document-table"><tbody>
                  {rows.map((row, ri) => <tr key={ri}>
                    {row.map((value, ci) => ri === 0
                      ? <th key={ci}>{value}</th> : <td key={ci}>{value}</td>)}
                  </tr>)}
                </tbody></table>
              </div>;
            })}
            <details>
              <summary>Nội dung trích xuất nguyên gốc</summary>
              <pre className="document-text">{page.markdown}</pre>
            </details>
          </section>
        );
      })}
    </article>
  ));
}

function DatasetList({
  items,
  onSelect,
  selected,
}: {
  items: Dataset[];
  onSelect: (dataset: Dataset) => void;
  selected?: string;
}) {
  return (
    <div className="dataset-list">
      {items.map((d) => (
        <button
          className={`dataset-item ${selected === d.id ? "dataset-selected" : ""}`}
          key={d.id}
          onClick={() => onSelect(d)}
        >
          <span className="file-type">
            <FileSpreadsheet size={22} />
          </span>
          <span className="dataset-name">
            <strong>{d.name}</strong>
            <small>{new Date(d.created_at).toLocaleString("vi-VN")}</small>
          </span>
          <Badge status={d.status} />
          <ChevronRight size={18} />
        </button>
      ))}
    </div>
  );
}
