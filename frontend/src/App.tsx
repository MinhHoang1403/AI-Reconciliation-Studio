import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  BellRing,
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
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import { api, ApiError } from "./api";
import { ProjectSelector } from "./ProjectSelector";
import { DataOverview } from "./DataOverview";
import {
  Badge,
  DataTable,
  DatasetList,
  formatValue,
  Modal,
  Notice,
  Spinner,
} from "./components";
import { MappingStudio } from "./MappingStudio";
import type { AssistantContext } from "./assistantTypes";
import {
  readLocation,
  writeLocation,
  type Page,
  type Location,
} from "./navigation";
const AssistantStudio = lazy(() =>
  import("./AssistantStudio").then((m) => ({ default: m.AssistantStudio })),
);
const ReconciliationStudio = lazy(() =>
  import("./ReconciliationStudio").then((m) => ({
    default: m.ReconciliationStudio,
  })),
);
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
  type PreparationAction,
  type Profile,
  type Project,
  type ProjectSummary,
  type Table,
  type WorkspaceSettings,
} from "./types";

type Tab = "explore" | "mapping" | "normalize";
type View = "parsed" | "raw" | "canonical" | "errors";

export function App() {
  const [location, setLocation] = useState(readLocation);
  const { page, context: assistantContext } = location;
  const locationRef = useRef(location);
  const navigationSequence = useRef(0);
  locationRef.current = location;
  const [restoringLocation, setRestoringLocation] = useState(false);
  function navigate(
    next: Page,
    context: AssistantContext | null = null,
    selectedProject = projectId,
    replace = false,
  ) {
    navigationSequence.current++;
    setRestoringLocation(false);
    const nextLocation: Location = {
      page: next,
      projectId: selectedProject,
      context,
      origin: page === "assistant" ? location.origin : page,
    };
    writeLocation(nextLocation, replace);
    setLocation(nextLocation);
  }
  function setPage(next: Page) {
    navigate(next);
  }
  function openAssistant(context: AssistantContext) {
    if (page === "assistant") {
      navigate("assistant", assistantContext);
      setSidebar(false);
      return;
    }
    navigate("assistant", context);
    setSidebar(false);
  }
  const [tab, setTab] = useState<Tab>("explore");
  const [project, setProject] = useState<Project | null>(null);
  const [projectId, setProjectId] = useState("");
  const [planNavigation, setPlanNavigation] = useState<{
    id: string;
    projectId: string;
    request: number;
  } | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [recent, setRecent] = useState<{
    projectId: string;
    items: Dataset[];
    loading: boolean;
    error: string;
  }>({ projectId: "", items: [], loading: true, error: "" });
  const [recentRetry, setRecentRetry] = useState(0);
  const [datasetOffset, setDatasetOffset] = useState(0);
  const [datasetTotal, setDatasetTotal] = useState(0);
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectError, setProjectError] = useState("");
  const [runNavigation, setRunNavigation] = useState<{
    id: string;
    request: number;
    caseId?: string | null;
  } | null>(null);
  const [selectedSource, setSelectedSource] = useState<Dataset | null>(null);
  const [pendingTarget, setPendingTarget] = useState<PreparationAction | null>(
    null,
  );
  const [jobs, setJobs] = useState<Job[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [tables, setTables] = useState<Table[]>([]);
  const [documentState, setDocumentState] = useState<{
    datasetId: string;
    items: DocumentArtifact[];
  }>({ datasetId: "", items: [] });
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
  const [actorRole, setActorRole] = useState("");
  const [draftOwner, setDraftOwner] = useState("");
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
  const modalFocus = useRef<HTMLElement | null>(null);
  const navigation = useRef<HTMLElement | null>(null);
  const projectSequence = useRef(0);
  const refreshController = useRef<AbortController | null>(null);
  const selectedDataset =
    datasets.find((d) => d.id === datasetId) ||
    (selectedSource?.id === datasetId && selectedSource.project_id === projectId
      ? selectedSource
      : undefined);
  const table = tables.find((t) => t.id === tableId);
  const currentCanonical = canonicals.find((c) => c.id === canonicalId);
  const activeMapping = mappings.find((m) => m.id === table?.active_mapping_id);

  useEffect(() => {
    if (page !== "assistant") return;
    const viewport = window.visualViewport;
    const resize = () =>
      document.documentElement.style.setProperty(
        "--assistant-viewport-height",
        `${viewport?.height || window.innerHeight}px`,
      );
    resize();
    viewport?.addEventListener("resize", resize);
    return () => {
      viewport?.removeEventListener("resize", resize);
      document.documentElement.style.removeProperty(
        "--assistant-viewport-height",
      );
    };
  }, [page]);

  useEffect(() => {
    if (!sidebar) return;
    const previous = document.activeElement as HTMLElement | null;
    const items = () =>
      Array.from(
        navigation.current?.querySelectorAll<HTMLElement>(
          "a[href], button:not(:disabled)",
        ) || [],
      );
    items()[0]?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setSidebar(false);
      }
      if (event.key === "Tab") {
        const controls = items();
        if (event.shiftKey && document.activeElement === controls[0]) {
          event.preventDefault();
          controls.at(-1)?.focus();
        } else if (
          !event.shiftKey &&
          document.activeElement === controls.at(-1)
        ) {
          event.preventDefault();
          controls[0]?.focus();
        }
      }
    }
    const viewport = window.matchMedia("(max-width: 900px)");
    const resized = () => {
      if (!viewport.matches) setSidebar(false);
    };
    document.addEventListener("keydown", keydown);
    viewport.addEventListener("change", resized);
    return () => {
      document.removeEventListener("keydown", keydown);
      viewport.removeEventListener("change", resized);
      if (previous?.isConnected) previous.focus();
    };
  }, [sidebar]);

  const canEdit = actorRole === "owner" || actorRole === "editor";

  function openUpload() {
    if (!canEdit) {
      setError("Bạn chỉ có quyền xem. Cần quyền chỉnh sửa để tải dữ liệu.");
      return;
    }
    modalFocus.current = document.activeElement as HTMLElement | null;
    setUploadOpen(true);
  }
  function openNewProject() {
    if (!canEdit) {
      setError("Bạn chỉ có quyền xem. Cần quyền chỉnh sửa để tạo dự án.");
      return;
    }
    modalFocus.current = document.activeElement as HTMLElement | null;
    setProjectOpen(true);
  }

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
        const actor = await api<{
          role: string;
          actor_id?: string;
          workspace_id?: string;
        }>("/session");
        const s = await api<WorkspaceSettings>("/settings");
        const savedId =
          locationRef.current.projectId ||
          localStorage.getItem("studio.project");
        let restored: Project | null = null;
        try {
          restored = savedId
            ? await api<Project>(`/projects/${encodeURIComponent(savedId)}`)
            : (
                await api<{ items: Project[] }>(
                  "/projects?include_test=false&limit=1",
                )
              ).items[0] || null;
        } catch (err) {
          if (!mounted) return;
          if (
            err instanceof ApiError &&
            ["RESOURCE_NOT_FOUND", "FORBIDDEN"].includes(err.code)
          ) {
            setError(
              "Dự án đã lưu không còn tồn tại hoặc bạn không còn quyền truy cập. Hãy chọn dự án khác.",
            );
            localStorage.removeItem("studio.project");
          } else throw err;
        }
        if (!mounted) return;
        setProject(restored);
        setProjectId(restored?.id || "");
        const initial = locationRef.current;
        const next = {
          ...initial,
          projectId: restored?.id || "",
          context:
            restored && initial.page === "assistant"
              ? { ...(initial.context || {}), project_id: restored.id }
              : null,
        };
        setLocation(next);
        writeLocation(next, true);
        if (initial.context?.run_id && restored)
          setRunNavigation({
            id: initial.context.run_id,
            caseId: initial.context.case_id,
            request: Date.now(),
          });
        setWorkspace(s);
        setActorRole(actor.role);
        setDraftOwner(
          `${actor.workspace_id || "local"}.${actor.actor_id || "demo"}`,
        );
        setReady(true);
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
    if (!projectId) return;
    const sequence = ++projectSequence.current;
    refreshController.current?.abort();
    const controller = new AbortController();
    refreshController.current = controller;
    setProjectLoading(true);
    setProjectError("");
    try {
      const [d, j, s] = await Promise.all([
        api<{ items: Dataset[]; total: number }>(
          `/datasets?project_id=${projectId}&offset=${datasetOffset}&limit=25`,
          { signal: controller.signal },
        ),
        api<{ items: Job[] }>(`/jobs?project_id=${projectId}`, {
          signal: controller.signal,
        }),
        api<ProjectSummary>(`/projects/${projectId}/summary`, {
          signal: controller.signal,
        }),
      ]);
      if (
        controller.signal.aborted ||
        sequence !== projectSequence.current ||
        scopeRef.current.projectId !== projectId ||
        scopeRef.current.datasetOffset !== datasetOffset
      )
        return;
      setDatasets(d.items);
      setDatasetTotal(d.total);
      setJobs(j.items);
      setSummary(s);
    } catch (err) {
      if (!controller.signal.aborted && sequence === projectSequence.current)
        setProjectError(
          err instanceof Error ? err.message : "Không tải được dữ liệu dự án.",
        );
    } finally {
      if (!controller.signal.aborted && sequence === projectSequence.current)
        setProjectLoading(false);
    }
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
    if (ready && projectId) localStorage.setItem("studio.project", projectId);
    setDatasetId("");
    setTableId("");
    setTables([]);
    setProfile(null);
    setMappings([]);
    setPreview(null);
    setDatasetOffset(0);
  }, [projectId, ready]);
  useEffect(() => {
    if (!ready) return;
    void refreshProject();
    return () => {
      refreshController.current?.abort();
    };
  }, [ready, refreshProject]);
  useEffect(() => {
    if (!ready || !projectId || !summary || page !== "home") return;
    const controller = new AbortController();
    setRecent({ projectId, items: [], loading: true, error: "" });
    void api<{ items: Dataset[] }>(
      `/datasets?project_id=${projectId}&offset=0&limit=5`,
      { signal: controller.signal },
    )
      .then((result) => {
        if (
          !controller.signal.aborted &&
          scopeRef.current.projectId === projectId
        )
          setRecent({
            projectId,
            items: result.items,
            loading: false,
            error: "",
          });
      })
      .catch((err) => {
        if (
          !controller.signal.aborted &&
          scopeRef.current.projectId === projectId
        )
          setRecent({
            projectId,
            items: [],
            loading: false,
            error:
              err instanceof Error
                ? err.message
                : "Không tải được dữ liệu gần đây.",
          });
      });
    return () => controller.abort();
  }, [ready, projectId, page, summary, recentRetry]);
  useEffect(() => {
    if (
      !ready ||
      page === "settings" ||
      !summary?.active_job_count ||
      projectLoading ||
      projectError
    )
      return;
    const timer = setTimeout(() => void refreshProject(), 3000);
    return () => clearTimeout(timer);
  }, [ready, page, summary, projectLoading, projectError, refreshProject]);

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
      pendingTarget?.table_id &&
      result.items.some((t) => t.id === pendingTarget.table_id)
        ? pendingTarget.table_id
        : result.items.some((t) => t.id === old)
          ? old
          : result.items[0]?.id || "",
    );
  }, [datasetId, pendingTarget]);
  useEffect(() => {
    void loadTables().catch((err) => setError(err.message));
  }, [loadTables, selectedDataset?.status]);
  useEffect(() => {
    if (!datasetId || !/\.(pdf|docx)$/i.test(selectedDataset?.name || ""))
      return;
    let current = true;
    void api<DocumentArtifact[]>(`/datasets/${datasetId}/documents`)
      .then((items) => {
        if (current) setDocumentState({ datasetId, items });
      })
      .catch((err) => {
        if (current) setError(err.message);
      });
    return () => {
      current = false;
    };
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
      pendingTarget?.canonical_id &&
      candidates.some((c) => c.id === pendingTarget.canonical_id)
        ? pendingTarget.canonical_id
        : candidates.some((c) => c.id === old && !c.stale)
          ? old
          : candidates.filter((c) => !c.stale).at(-1)?.id ||
            candidates.at(-1)?.id ||
            "",
    );
  }, [tableId, datasetId, pendingTarget]);
  useEffect(() => {
    setOffset(0);
    setSearch("");
    setView(pendingTarget?.canonical_id ? "errors" : "parsed");
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
    setPendingTarget(null);
    setSelectedSource(d);
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
  function chooseProject(selected: Project, recordHistory = true) {
    if (selected.id === projectId) return;
    scopeRef.current = {
      projectId: selected.id,
      datasetId: "",
      tableId: "",
      datasetOffset: 0,
    };
    projectSequence.current += 1;
    refreshController.current?.abort();
    setProjectLoading(false);
    setProjectError("");
    setRunNavigation(null);
    setSelectedSource(null);
    setPendingTarget(null);
    setProject(selected);
    setProjectId(selected.id);
    setDatasets([]);
    setRecent({ projectId: selected.id, items: [], loading: true, error: "" });
    setDatasetTotal(0);
    setDatasetOffset(0);
    setJobs([]);
    setSummary(null);
    setDatasetId("");
    setTables([]);
    setTableId("");
    setProfile(null);
    setMappings([]);
    setCanonicals([]);
    setCanonicalId("");
    setPreview(null);
    setDocumentState({ datasetId: "", items: [] });
    setEvidenceId("");
    setEvidence(null);
    setError("");
    setSuccess("");
    setTab("explore");
    setPlanNavigation(null);
    if (recordHistory)
      navigate(
        page,
        page === "assistant" ? { project_id: selected.id } : null,
        selected.id,
      );
  }
  useEffect(() => {
    if (!ready) return;
    const controller = new AbortController();
    const restore = async () => {
      const current = ++navigationSequence.current;
      const next = readLocation();
      setRestoringLocation(true);
      setSidebar(false);
      try {
        if (next.projectId && next.projectId !== scopeRef.current.projectId) {
          const selected = await api<Project>(
            `/projects/${encodeURIComponent(next.projectId)}`,
            { signal: controller.signal },
          );
          if (
            controller.signal.aborted ||
            current !== navigationSequence.current
          )
            return;
          chooseProject(selected, false);
        }
        if (controller.signal.aborted || current !== navigationSequence.current)
          return;
        if (next.context?.run_id)
          setRunNavigation({
            id: next.context.run_id,
            caseId: next.context.case_id,
            request: Date.now(),
          });
        setLocation(next);
      } catch (err) {
        if (
          !controller.signal.aborted &&
          current === navigationSequence.current
        ) {
          setError(
            err instanceof Error ? err.message : "Không khôi phục được trang.",
          );
          writeLocation(locationRef.current, true);
        }
      } finally {
        if (
          !controller.signal.aborted &&
          current === navigationSequence.current
        )
          setRestoringLocation(false);
      }
    };
    const listener = () => {
      void restore();
    };
    window.addEventListener("popstate", listener);
    return () => {
      controller.abort();
      window.removeEventListener("popstate", listener);
    };
  }, [ready, projectId, page]);
  async function openPreparation(action: PreparationAction) {
    if (action.kind === "UPLOAD") {
      openUpload();
      return;
    }
    if (action.kind === "WAIT") {
      await changed();
      return;
    }
    if (action.kind === "RECONCILE") {
      setPage("reconcile");
      return;
    }
    if (!action.dataset_id) return;
    const selectedProject = projectId;
    const dataset = await api<Dataset>(`/datasets/${action.dataset_id}`);
    if (
      scopeRef.current.projectId !== selectedProject ||
      dataset.project_id !== selectedProject
    )
      return;
    chooseDataset(dataset);
    setPendingTarget(action);
    setTab(
      action.kind === "REVIEW_MAPPING"
        ? "mapping"
        : action.kind === "NORMALIZE"
          ? "normalize"
          : "explore",
    );
    setView(action.canonical_id ? "errors" : "parsed");
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
      body: JSON.stringify({
        name: newName,
        business_scope: newScope,
        classification: "WORK",
      }),
    });
    chooseProject(p);
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
      <aside
        ref={navigation}
        className={`sidebar ${sidebar ? "sidebar-open" : ""}`}
        role={sidebar ? "dialog" : undefined}
        aria-modal={sidebar || undefined}
        aria-label={sidebar ? "Điều hướng" : undefined}
      >
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
            <strong>Không gian làm việc</strong>
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
            Dữ liệu
            <span className="nav-count">
              {projectId ? (summary ? datasetTotal : "…") : "—"}
            </span>
          </button>
          <button
            className={page === "reconcile" ? "active" : ""}
            onClick={() => {
              setPage("reconcile");
              setSidebar(false);
            }}
          >
            <GitCompareArrows size={19} />
            <span>Đối soát</span>
          </button>
          <button
            className={page === "exceptions" ? "active" : ""}
            onClick={() => {
              setPage("exceptions");
              setSidebar(false);
            }}
          >
            <BellRing size={19} />
            <span>Ngoại lệ</span>
          </button>
          <button
            className={page === "reports" ? "active" : ""}
            onClick={() => {
              setPage("reports");
              setSidebar(false);
            }}
          >
            <ArrowDownToLine size={19} />
            <span>Báo cáo</span>
          </button>
          <button
            className={page === "assistant" ? "active" : ""}
            aria-current={page === "assistant" ? "page" : undefined}
            disabled={!ready || !projectId}
            onClick={() =>
              openAssistant({
                project_id: projectId,
                ...(page === "data" && selectedDataset?.project_id === projectId
                  ? { dataset_id: selectedDataset.id }
                  : {}),
                ...(["reconcile", "exceptions", "reports"].includes(page) &&
                localStorage.getItem(`studio.run.${projectId}`)
                  ? { run_id: localStorage.getItem(`studio.run.${projectId}`) }
                  : {}),
              })
            }
          >
            <Sparkles size={19} />
            <span>Trợ lý AI</span>
          </button>
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
              <small>
                {(
                  {
                    owner: "Chủ không gian",
                    editor: "Có quyền chỉnh sửa",
                    viewer: "Chỉ xem",
                  } as Record<string, string>
                )[actorRole] || "Đang xác minh quyền"}
              </small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-shell" inert={sidebar || undefined}>
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button menu-button"
              aria-label="Mở điều hướng"
              onClick={() => setSidebar(true)}
            >
              <Menu size={22} />
            </button>
            <span>Không gian làm việc</span>
            <ChevronRight size={14} />
            <strong>
              {page === "home"
                ? "Tổng quan"
                : page === "data"
                  ? "Dữ liệu"
                  : page === "reconcile"
                    ? "Đối soát"
                    : page === "exceptions"
                      ? "Ngoại lệ"
                      : page === "reports"
                        ? "Báo cáo"
                        : page === "assistant"
                          ? "Trợ lý AI"
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
        <main
          id="main-content"
          className={page === "assistant" ? "assistant-main" : ""}
          inert={restoringLocation || undefined}
        >
          <div className="page-heading">
            <div>
              <span className="eyebrow">AI RECONCILIATION STUDIO</span>
              <h1>
                {page === "home"
                  ? "Nền tảng dữ liệu của bạn"
                  : page === "data"
                    ? "Quản lý dữ liệu"
                    : page === "reconcile"
                      ? "Đối soát có kiểm chứng"
                      : page === "exceptions"
                        ? "Ngoại lệ và bằng chứng"
                        : page === "reports"
                          ? "Báo cáo đối soát"
                          : page === "assistant"
                            ? "Trợ lý AI"
                            : "Cài đặt không gian làm việc"}
              </h1>
              <p>
                {page === "home"
                  ? "Từ tệp nguồn đến dữ liệu chuẩn hóa — rõ ràng ở từng bước."
                  : page === "data"
                    ? "Khám phá nguồn, kiểm tra đề xuất và chuẩn bị dữ liệu đáng tin cậy."
                    : page === "assistant"
                      ? "Hỏi từ dữ kiện, kiểm tra bằng chứng và chọn bước tiếp theo."
                      : page === "settings"
                        ? "Chính sách xử lý và giới hạn đang áp dụng từ backend."
                        : "Quy tắc được duyệt, kết quả bất biến và bằng chứng từ dữ liệu nguồn."}
              </p>
            </div>
            <div className="heading-actions">
              {(page === "home" || page === "data") && (
                <button
                  className={`button ${page === "data" && datasetId && tab !== "explore" ? "secondary" : "primary"}`}
                  disabled={!ready || busy || !canEdit}
                  onClick={() => (projectId ? openUpload() : openNewProject())}
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
                {!ready && (
                  <button
                    className="text-button"
                    onClick={() => window.location.reload()}
                  >
                    Kết nối lại
                  </button>
                )}
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
              <ProjectSelector
                project={project}
                onSelect={chooseProject}
                disabled={busy}
                canClassify={actorRole === "owner"}
                onClassificationChange={(value) =>
                  setProject((current) =>
                    current?.id === value.id ? value : current,
                  )
                }
              />
              {projectId && (
                <button
                  className="icon-button"
                  aria-label="Cập nhật dự án"
                  title="Cập nhật dự án"
                  disabled={busy || projectLoading}
                  onClick={() => void run(changed)}
                >
                  <RefreshCw
                    size={17}
                    className={projectLoading ? "spin" : ""}
                  />
                </button>
              )}
              <button
                className="text-button"
                disabled={!canEdit}
                onClick={() => openNewProject()}
              >
                + Tạo dự án
              </button>
            </div>
          )}
          {ready && !projectId && page !== "settings" && (
            <Notice>
              Chọn hoặc tạo dự án để xem dữ liệu. Dự án chưa được chọn; không
              hiển thị số liệu của dự án khác.
            </Notice>
          )}
          {ready && projectId && projectError && (
            <Notice tone="error">
              {projectError} Dữ liệu chưa cập nhật.
              <button
                className="text-button"
                onClick={() => void refreshProject()}
              >
                Thử tải lại dự án
              </button>
            </Notice>
          )}
          {ready && projectId && !summary && !projectError && (
            <div role="status">
              <Spinner /> Đang tải dữ liệu dự án…
            </div>
          )}
          {ready &&
            projectId &&
            [
              "home",
              "reconcile",
              "exceptions",
              "reports",
              "assistant",
            ].includes(page) && (
              <div hidden={page === "assistant"}>
                <Suspense fallback={<Spinner />}>
                  <ReconciliationStudio
                    key={projectId}
                    projectId={projectId}
                    canEdit={canEdit}
                    onAsk={openAssistant}
                    requestedPlan={
                      planNavigation?.projectId === projectId
                        ? planNavigation
                        : null
                    }
                    requestedRun={runNavigation}
                    mode={
                      (page === "assistant"
                        ? [
                            "home",
                            "reconcile",
                            "exceptions",
                            "reports",
                          ].includes(location.origin)
                          ? location.origin
                          : "home"
                        : page) as
                        | "home"
                        | "reconcile"
                        | "exceptions"
                        | "reports"
                    }
                    onSetup={() => setPage("reconcile")}
                    onRunSelected={(id, caseId) => {
                      const current = locationRef.current;
                      if (current.page === "assistant") return;
                      const next = {
                        ...current,
                        context: {
                          project_id: projectId,
                          run_id: id,
                          ...(caseId ? { case_id: caseId } : {}),
                        },
                      };
                      writeLocation(next, true);
                      locationRef.current = next;
                    }}
                  />
                </Suspense>
              </div>
            )}
          {ready &&
            projectId &&
            page === "assistant" &&
            assistantContext?.project_id === projectId && (
              <section className="assistant-page" aria-label="Trợ lý AI">
                <button
                  className="text-button assistant-return"
                  onClick={() => {
                    const current = readLocation().context || assistantContext;
                    if (current.run_id)
                      setRunNavigation({
                        id: current.run_id,
                        caseId: current.case_id,
                        request: Date.now(),
                      });
                    navigate(location.origin, current);
                  }}
                >
                  ← Trở về trang trước
                </button>
                <Suspense fallback={<Spinner />}>
                  <AssistantStudio
                    key={JSON.stringify(assistantContext)}
                    initialContext={assistantContext}
                    projectName={project?.name || "Dự án hiện tại"}
                    draftOwner={draftOwner}
                    onContextChange={(context) => {
                      const current = readLocation();
                      if (
                        current.page === "assistant" &&
                        current.projectId === context.project_id
                      )
                        writeLocation({ ...current, context }, true);
                    }}
                    cloudEnabled={!!workspace?.assistant_cloud_enabled}
                    canEdit={canEdit}
                    onReview={(id) => {
                      setPlanNavigation({ id, projectId, request: Date.now() });

                      setPage("reconcile");
                    }}
                    onNavigate={(target, context) => {
                      if (context.project_id !== projectId) return;

                      if (context.run_id)
                        setRunNavigation({
                          id: context.run_id,
                          caseId: context.case_id,
                          request: Date.now(),
                        });
                      if (target === "OPEN_DATA") {
                        if (context.dataset_id)
                          setDatasetId(context.dataset_id);
                        setPage("data");
                      } else
                        setPage(
                          target === "OPEN_REPORT"
                            ? "reports"
                            : target === "OPEN_EXCEPTIONS"
                              ? "exceptions"
                              : "reconcile",
                        );
                    }}
                  />
                </Suspense>
              </section>
            )}
          {ready && page === "home" && projectId && summary && (
            <DataOverview
              summary={summary}
              datasets={recent.projectId === projectId ? recent.items : []}
              recentLoading={recent.projectId !== projectId || recent.loading}
              recentError={recent.projectId === projectId ? recent.error : ""}
              onRecentRetry={() => setRecentRetry((value) => value + 1)}
              workspace={workspace}
              busy={busy}
              onAction={(action) => void run(() => openPreparation(action))}
              onResults={(target) => {
                if (summary.latest_verified_run_id)
                  localStorage.setItem(
                    `studio.run.${projectId}`,
                    summary.latest_verified_run_id,
                  );
                if (summary.latest_verified_run_id)
                  setRunNavigation((old) => ({
                    id: summary.latest_verified_run_id!,
                    request: (old?.request || 0) + 1,
                  }));
                setPage(target);
              }}
              onData={() => setPage("data")}
              chooseDataset={chooseDataset}
            />
          )}
          {ready && projectId && summary && page === "data" && (
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
                      {selectedDataset.status === "PARTIAL" && (
                        <Notice tone="warning">
                          Dữ liệu cần kiểm tra.{" "}
                          {currentCanonical
                            ? `${currentCanonical.invalid_count} / ${currentCanonical.row_count} dòng cần kiểm tra trong kết quả đang chọn.`
                            : "Mở bảng và xem kết quả hoặc hoạt động xử lý để tìm nguyên nhân; trạng thái này không tự cho biết ánh xạ đã được duyệt hay chưa."}
                          {currentCanonical && (
                            <button
                              className="text-button"
                              onClick={() => {
                                setTab("explore");
                                setView("errors");
                                setOffset(0);
                              }}
                            >
                              Xem cảnh báo / lỗi dữ liệu
                            </button>
                          )}
                        </Notice>
                      )}
                      {tables.length === 0 ? (
                        <div className="empty-state">
                          {/\.(pdf|docx)$/i.test(selectedDataset.name) ? (
                            <div>
                              <Notice tone="warning">
                                Bản trích xuất chưa được xác minh. Không tự dùng
                                số tiền trong tài liệu để đối soát.
                              </Notice>
                              {documentState.datasetId === datasetId && (
                                <DocumentPreview
                                  documents={documentState.items}
                                />
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
                                  Chưa có bảng được công bố. Kiểm tra trạng thái
                                  tác vụ bên dưới.
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
                                readOnly={!canEdit}
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
                                      !canEdit ||
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
                  <dd>
                    {workspace.policy.mode === "LOCAL_ONLY"
                      ? "Xử lý nội bộ"
                      : "Theo chính sách workspace"}
                  </dd>
                  <dt>Gemini cloud</dt>
                  <dd>
                    {workspace.policy.allow_external_ai ? "Có quyền" : "Tắt"} ·{" "}
                    {workspace.gemini_requests_remaining} request còn lại ·{" "}
                    {workspace.gemini_requests_used} đã dùng
                  </dd>
                  <dt>Trợ lý cloud</dt>
                  <dd>
                    {workspace.assistant_cloud_enabled
                      ? "Được cấp phép theo từng tác vụ"
                      : "Tắt · chế độ dữ kiện"}
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
                  <dt>Mỗi tệp</dt>
                  <dd>{workspace.max_upload_bytes / 1048576} MB</dd>
                  <dt>Mỗi lần tải</dt>
                  <dd>{workspace.max_upload_files} tệp</dd>
                  <dt>Mỗi bảng</dt>
                  <dd>{workspace.max_rows.toLocaleString("vi-VN")} dòng</dd>
                </dl>
                <details className="settings-advanced">
                  <summary>Thông tin AI nâng cao</summary>
                  <dl>
                    <dt>Qwen</dt>
                    <dd>
                      {workspace.qwen_configured
                        ? `Đã cấu hình · ${workspace.qwen_model}`
                        : "Chưa cấu hình"}
                    </dd>
                    <dt>Provider đề xuất ánh xạ</dt>
                    <dd>
                      {workspace.mapping_ai_provider === "GEMINI"
                        ? "Gemini"
                        : "Qwen"}
                    </dd>
                    <dt>Gemini</dt>
                    <dd>
                      {workspace.gemini_configured
                        ? workspace.gemini_model
                        : "Chưa cấu hình khóa"}
                    </dd>
                  </dl>
                </details>
                <Notice>
                  Khóa và địa chỉ provider chỉ được quản lý trên backend. Mỗi
                  lần gọi Gemini tiêu thụ ngân sách, kể cả lỗi hoặc thử lại.
                  Parser cloud có quyền riêng.
                </Notice>
              </div>
            </section>
          )}
          {ready &&
            jobs.length > 0 &&
            page !== "settings" &&
            page !== "assistant" && (
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
                    Cập nhật trạng thái xử lý
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
          {page !== "assistant" && (
            <footer>
              <ShieldCheck size={14} />
              Tệp gốc bất biến · Ánh xạ có phê duyệt · Dữ liệu có nguồn gốc
              <span>Kết quả có kiểm chứng</span>
            </footer>
          )}
        </main>
      </div>
      <Modal
        title="Tạo dự án"
        open={projectOpen}
        onOpenChange={setProjectOpen}
        returnFocus={modalFocus}
      >
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
              disabled={busy || !canEdit || !newName.trim() || !newScope.trim()}
            >
              {busy ? <Spinner /> : "Tạo dự án"}
            </button>
          </div>
        </form>
      </Modal>
      <Modal
        returnFocus={modalFocus}
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
              <input
                type="checkbox"
                checked={requestAiMapping}
                onChange={(event) => setRequestAiMapping(event.target.checked)}
              />
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
              disabled={busy || !canEdit || files.length === 0}
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

function DocumentPreview({ documents }: { documents: DocumentArtifact[] }) {
  return documents.map((doc) => (
    <article key={doc.artifact.id}>
      <h3>{doc.source_file.filename}</h3>
      {doc.extraction.pages.map((page) => {
        const tables = page.items.filter(
          (item) =>
            item.type === "table" &&
            Array.isArray(item.rows) &&
            item.rows.every(
              (row) =>
                Array.isArray(row) &&
                row.every((cell) => typeof cell === "string"),
            ),
        );
        return (
          <section key={page.page_number}>
            <h4>Trang {page.page_number}</h4>
            {tables.map((table, index) => {
              const rows = table.rows as string[][];
              return (
                <div className="table-scroll" key={index}>
                  <table className="document-table">
                    <tbody>
                      {rows.map((row, ri) => (
                        <tr key={ri}>
                          {row.map((value, ci) =>
                            ri === 0 ? (
                              <th key={ci}>{value}</th>
                            ) : (
                              <td key={ci}>{value}</td>
                            ),
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
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
