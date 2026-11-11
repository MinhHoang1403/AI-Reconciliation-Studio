import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ArrowRight,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Database,
  FileSpreadsheet,
  FolderOpen,
  Layers3,
  LayoutDashboard,
  History,
  MoreHorizontal,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Search,
  Settings2,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import { api, ApiError, setApiWorkspace } from "./api";
import { WorkspaceManager, WorkspaceSettings as WorkspaceSettingsPanel } from "./WorkspaceSettings";
import { ProjectSelector } from "./ProjectSelector";
import { ProjectHistory } from "./ProjectHistory";
import { ResourceManagement, type ManagedResource } from "./ResourceManagement";
import { DataOverview } from "./DataOverview";
import {
  Badge,
  DataTable,
  formatValue,
  Modal,
  Notice,
  Spinner,
} from "./components";
import { MappingStudio } from "./MappingStudio";
import { useNativeDropdowns } from "./Dropdown";
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
  type ProjectClassification,
  type ProjectSummary,
  type Table,
  type WorkspaceSettings,
} from "./types";

type Tab = "explore" | "mapping" | "normalize";
type View = "raw" | "prepared" | "prepared_findings" | "canonical" | "errors";

export function App() {
  const [location, setLocation] = useState(readLocation);
  const { page, context: assistantContext } = location;
  const [assistantHistoryOpen, setAssistantHistoryOpen] = useState(false);
  const [openActivityProject, setOpenActivityProject] = useState("");
  const assistantHistoryTrigger = useRef<HTMLElement | null>(null);
  const locationRef = useRef(location);
  const navigationSequence = useRef(0);
  locationRef.current = location;
  const [restoringLocation, setRestoringLocation] = useState(false);
  function navigate(
    next: Page,
    context: AssistantContext | null = null,
    selectedProject = projectId,
    replace = false,
    conversationId?: string,
  ) {
    navigationSequence.current++;
    setRestoringLocation(false);
    const nextLocation: Location = {
      page: next,
      projectId: selectedProject,
      context,
      origin: page === "assistant" ? location.origin : page,
      conversationId,
    };
    locationRef.current = nextLocation;
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
  const [manage, setManage] = useState<ManagedResource | null>(null);
  const manageTrigger = useRef<HTMLElement | null>(null);
  function openManagement(target: ManagedResource, trigger: HTMLElement | null) {
    manageTrigger.current = trigger;
    setManage(target);
  }
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
  const [datasetSearch, setDatasetSearch] = useState("");
  const [sourceListOpen, setSourceListOpen] = useState(() => !location.context?.dataset_id);
  const [datasetTotal, setDatasetTotal] = useState(0);
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectError, setProjectError] = useState("");
  const [projectAccessDenied, setProjectAccessDenied] = useState(false);
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
  const [tableRequest, setTableRequest] = useState({ datasetId: "", loading: false, error: "" });
  const tableRequestSequence = useRef(0);
  const detailRequest = useRef<AbortController | null>(null);
  const [documentState, setDocumentState] = useState<{
    datasetId: string;
    items: DocumentArtifact[];
  }>({ datasetId: "", items: [] });
  const [tableId, setTableId] = useState("");
  const restoredDataView = useRef<{datasetId: string; tableId: string} | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [detailScope,setDetailScope]=useState("");
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [mappingJob, setMappingJob] = useState<Job | null>(null);
  const [canonicals, setCanonicals] = useState<Canonical[]>([]);
  const [canonicalId, setCanonicalId] = useState("");
  const [view, setView] = useState<View>("raw");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewQuery, setPreviewQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [workspace, setWorkspace] = useState<WorkspaceSettings | null>(null);
  const [ready, setReady] = useState(false);
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0);
  const [bootstrapError, setBootstrapError] = useState<{
    code: string;
    message: string;
  } | null>(null);
  const [focusMode, setFocusMode] = useState<"pointer" | "keyboard">("pointer");
  useNativeDropdowns(setFocusMode);
  const [actorRole, setActorRole] = useState("");
  const [tableDensity, setTableDensity] = useState<"comfortable" | "compact">(
    () => localStorage.getItem("studio.table-density") === "compact" ? "compact" : "comfortable",
  );
  useEffect(() => {
    document.documentElement.dataset.tableDensity = tableDensity;
    localStorage.setItem("studio.table-density", tableDensity);
    return () => { delete document.documentElement.dataset.tableDensity; };
  }, [tableDensity]);
  const [draftOwner, setDraftOwner] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccessNotice] = useState<{ message: string } | null>(null);
  const setSuccess = useCallback((message: string) => setSuccessNotice(message ? { message } : null), []);
  useEffect(() => {
    if (!success) return;
    const timer = setTimeout(() => setSuccessNotice(null), 5000);
    return () => clearTimeout(timer);
  }, [success]);
  const [busy, setBusy] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [projectOpen, setProjectOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newClassification, setNewClassification] = useState<ProjectClassification>("WORK");
  const [newScope, setNewScope] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [encoding, setEncoding] = useState("utf-8-sig");
  const [delimiter, setDelimiter] = useState("");
  const [headerRow, setHeaderRow] = useState("");
  const [requestAiMapping, setRequestAiMapping] = useState(true);
  const [sidebar, setSidebar] = useState(false);
  const [compactNavigation, setCompactNavigation] = useState(
    () => localStorage.getItem("studio.navigation-compact") === "true",
  );
  const navigationToggleLabel = compactNavigation ? "Mở rộng thanh điều hướng" : "Thu gọn thanh điều hướng";
  function toggleNavigation() {
    const next = !compactNavigation;
    setCompactNavigation(next);
    localStorage.setItem("studio.navigation-compact", String(next));
  }
  const [evidenceId, setEvidenceId] = useState("");
  const [evidenceRow, setEvidenceRow] = useState<number | undefined>();
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(
    null,
  );
  const scopeRef = useRef({ projectId, datasetId, tableId, datasetOffset, datasetSearch });
  scopeRef.current = { projectId, datasetId, tableId, datasetOffset, datasetSearch };
  const fileInput = useRef<HTMLInputElement>(null);
  const modalFocus = useRef<HTMLElement | null>(null);
  const navigation = useRef<HTMLElement | null>(null);
  const pageScroll = useRef<HTMLDivElement>(null);
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
  const activeJobs = jobs.filter(job => ["QUEUED", "RUNNING", "RETRYABLE_FAILURE"].includes(job.status)).length;

  useLayoutEffect(() => {
    if (pageScroll.current) pageScroll.current.scrollTop = 0;
  }, [page, projectId]);

  useEffect(() => {
    if (page !== "assistant") return;
    const viewport = window.visualViewport;
    const resize = () =>
      document.documentElement.style.setProperty(
        "--assistant-viewport-height",
        `${viewport?.height || window.innerHeight}px`,
      );
    resize();
    window.addEventListener("resize", resize);
    viewport?.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
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
    navigation.current?.querySelector<HTMLElement>(".sidebar-close")?.focus();
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
    if (!projectId || projectAccessDenied) {
      const selector = document.getElementById("project-select");
      selector?.focus();
      selector?.click();
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
  }, [setSuccess]);

  useEffect(() => {
    let mounted = true;
    const controller = new AbortController();
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]);
    void (async () => {
      try {
        const actor = await api<{
          role: string;
          actor_id?: string;
          workspace_id?: string;
        }>("/session", { signal });
        if (!mounted) return;
        setApiWorkspace(actor.workspace_id);
        const s = await api<WorkspaceSettings>("/settings", { signal });
        const explicitScope = new URLSearchParams(window.location.hash.slice(1)).has("project");
        const savedId = locationRef.current.projectId ||
          (!explicitScope ? localStorage.getItem("studio.project") : null);
        let restored: Project | null = null;
        try {
          restored = savedId
            ? await api<Project>(`/projects/${encodeURIComponent(savedId)}`, { signal })
            : explicitScope || ["home", "assistant"].includes(locationRef.current.page) ? null : (
                await api<{ items: Project[] }>(
                  "/projects?include_test=false&limit=1", { signal },
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
            restored
              ? { ...(initial.context || {}), project_id: restored.id }
              : null,
        };
        locationRef.current = next;
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
        if (mounted) {
          const code = err instanceof ApiError ? err.code : "NETWORK_ERROR";
          setBootstrapError({
            code,
            message: code === "LOCAL_DEMO_NOT_VERIFIED"
              ? "Ứng dụng cần xác minh lại môi trường local sau khi khởi động. Dữ liệu của bạn vẫn được giữ nguyên."
              : ["NETWORK_ERROR", "API_TIMEOUT", "HTTP_ERROR"].includes(code)
                ? "Không thể kết nối tới dịch vụ xử lý dữ liệu. Hãy kiểm tra trạng thái ứng dụng."
                : err instanceof Error ? err.message : "Chưa thể xác minh phiên làm việc. Hãy thử kết nối lại.",
          });
        }
      }
    })();
    return () => {
      mounted = false;
      controller.abort();
    };
  }, [bootstrapAttempt]);

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
          `/datasets?project_id=${projectId}&offset=${datasetOffset}&limit=25&search=${encodeURIComponent(datasetSearch)}`,
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
        scopeRef.current.datasetOffset !== datasetOffset ||
        scopeRef.current.datasetSearch !== datasetSearch
      )
        return;
      setDatasets(d.items);
      setDatasetTotal(d.total);
      setJobs(j.items);
      setSummary(s);
      setProjectAccessDenied(false);
    } catch (err) {
      if (!controller.signal.aborted && sequence === projectSequence.current) {
        if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {
          setProjectAccessDenied(true);
          setSummary(null);
          setDatasets([]);
          setJobs([]);
          setSelectedSource(null);
          setPreview(null);
          setEvidenceId("");
          setEvidence(null);
          setAssistantHistoryOpen(false);
        }
        setProjectError(
          err instanceof Error ? err.message : "Không tải được dữ liệu dự án.",
        );
      }
    } finally {
      if (!controller.signal.aborted && sequence === projectSequence.current)
        setProjectLoading(false);
    }
  }, [projectId, datasetOffset, datasetSearch]);
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
    const requested = location.context?.dataset_id;
    if (!ready || page !== "data" || !projectId || !requested || requested === scopeRef.current.datasetId) return;
    const controller = new AbortController();
    setSelectedSource(null); setDatasetId(""); setTables([]); setTableId("");
    setProfile(null); setMappings([]); setCanonicals([]); setPreview(null);
    void api<Dataset>(`/datasets/${encodeURIComponent(requested)}`, {signal: controller.signal})
      .then(dataset => {
        if (controller.signal.aborted || scopeRef.current.projectId !== projectId ||
            locationRef.current.context?.dataset_id !== requested) return;
        if (dataset.project_id !== projectId) throw new Error("Nguồn không thuộc dự án đang mở.");
        let saved: {tableId?: string; tab?: string} | null = null;
        try { saved=JSON.parse(sessionStorage.getItem(`studio.data-view.${draftOwner}.${projectId}.${requested}`)||"null"); } catch { /* optional tab context */ }
        restoredDataView.current={datasetId:requested,tableId:typeof saved?.tableId==="string"?saved.tableId:""};
        setPendingTarget(null); setSelectedSource(dataset); setDatasetId(dataset.id); setSourceListOpen(false);
        setTab(saved?.tab==="mapping"||saved?.tab==="normalize"?saved.tab:"explore");
      })
      .catch(err=>{if(!controller.signal.aborted)setError(err instanceof Error?err.message:"Không khôi phục được nguồn dữ liệu.");});
    return()=>controller.abort();
  }, [ready, page, projectId, location.context?.dataset_id, draftOwner]);
  useEffect(() => {
    if (!ready || page!=="data" || !datasetId || !tableId || !tables.some(t=>t.id===tableId)) return;
    try {sessionStorage.setItem(`studio.data-view.${draftOwner}.${projectId}.${datasetId}`,JSON.stringify({tableId,tab}));}
    catch { /* API authorization and the source identifier in the URL remain available. */ }
  }, [ready,page,draftOwner,projectId,datasetId,tableId,tab,tables]);
  useEffect(() => {
    if (!ready) return;
    void refreshProject();
    return () => {
      refreshController.current?.abort();
    };
  }, [ready, refreshProject]);
  useEffect(() => {
    if (!ready || !projectId || !summary?.dataset_count || page !== "home") return;
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
    const sequence = ++tableRequestSequence.current;
    if (!datasetId) {
      setTables([]);
      setTableRequest({ datasetId: "", loading: false, error: "" });
      return;
    }
    setTableRequest({ datasetId, loading: true, error: "" });
    try {
    const result = await api<{ items: Table[] }>(
      `/datasets/${datasetId}/tables`,
    );
    if (scopeRef.current.datasetId !== datasetId || sequence !== tableRequestSequence.current) return;
    setTables(result.items);
    const restored = restoredDataView.current;
    setTableId((old) =>
      pendingTarget?.table_id &&
      result.items.some((t) => t.id === pendingTarget.table_id)
        ? pendingTarget.table_id
        : restored?.datasetId === datasetId && result.items.some(t=>t.id===restored.tableId)
          ? restored.tableId
        : result.items.some((t) => t.id === old)
          ? old
          : result.items[0]?.id || "",
    );
    if(restored?.datasetId===datasetId)restoredDataView.current=null;
    setTableRequest({ datasetId, loading: false, error: "" });
    } catch (err) {
      if (scopeRef.current.datasetId !== datasetId || sequence !== tableRequestSequence.current) return;
      setTableRequest({ datasetId, loading: false, error: err instanceof Error ? err.message : "Không tải được bảng dữ liệu." });
    }
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
    detailRequest.current?.abort();
    const controller = new AbortController();
    detailRequest.current = controller;
    const options = { signal: controller.signal };
    const details = await Promise.all([
      api<Profile>(`/tables/${tableId}/profile`, options),
      api<{ items: Mapping[]; job?: Job | null }>(`/tables/${tableId}/mappings?include_archived=true`, options),
      api<{ canonical_datasets: Canonical[] }>(
        `/datasets/${datasetId}/artifacts`, options,
      ),
    ]).catch(error => {
      if (controller.signal.aborted) return null;
      throw error;
    });
    if (
      !details || controller.signal.aborted ||
      scopeRef.current.tableId !== tableId ||
      scopeRef.current.datasetId !== datasetId
    )
      return;
    const [p, m, a] = details;
    setProfile(p);
    setDetailScope(`${datasetId}:${tableId}`);
    setMappings(m.items);
    setMappingJob(m.job ?? null);
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
    setView(pendingTarget?.canonical_id ? "errors" : "raw");
    setPreview(null);
  }, [tableId, datasetId, pendingTarget?.canonical_id]);
  useEffect(() => {
    void loadDetails().catch((err) => setError(err.message));
    return () => detailRequest.current?.abort();
  }, [loadDetails, selectedDataset?.status]);

  useEffect(() => {
    if (!tableId || (["canonical", "errors"].includes(view) && !canonicalId)) {
      setPreview(null);
      return;
    }
    const controller = new AbortController();
    const params = new URLSearchParams({
      kind: view,
      offset: String(offset),
      limit: "25",
      search,
    });
    if (canonicalId) params.set("canonical_id", canonicalId);
    void api<Preview>(`/tables/${tableId}/preview?${params}`, { signal: controller.signal })
      .then((p) => {
        if (!controller.signal.aborted) {
          setPreview(p);
          setPreviewQuery(
            JSON.stringify([tableId, view, canonicalId, offset, search]),
          );
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(err.message);
      });
    return () => controller.abort();
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
    navigate("data", {project_id: projectId, dataset_id: d.id});
    setTab("explore");
    setSourceListOpen(false);
    setSidebar(false);
  }
  function chooseProject(selected: Project | null, recordHistory = true) {
    const nextId = selected?.id ?? "";
    if (nextId === projectId) return;
    if (!nextId) localStorage.removeItem("studio.project");
    scopeRef.current = {
      projectId: nextId,
      datasetId: "",
      tableId: "",
      datasetOffset: 0,
      datasetSearch: "",
    };
    projectSequence.current += 1;
    refreshController.current?.abort();
    setProjectLoading(false);
    setProjectError("");
    setProjectAccessDenied(false);
    setRunNavigation(null);
    setSelectedSource(null);
    setPendingTarget(null);
    setProject(selected);
    setProjectId(nextId);
    setDatasets([]);
    setRecent({ projectId: nextId, items: [], loading: !!nextId, error: "" });
    setDatasetTotal(0);
    setDatasetOffset(0);
    setDatasetSearch("");
    setSourceListOpen(true);
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
        page === "assistant" && nextId ? { project_id: nextId } : null,
        nextId,
      );
  }
  useEffect(() => {
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
        if (!next.projectId && (next.page === "home" ||
          new URLSearchParams(window.location.hash.slice(1)).has("project"))) {
          chooseProject(null, false);
        }
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
      if (!ready) {
        // Liên kết vừa mở là đích cần khôi phục, kể cả lúc đang tải phiên.
        // Cùng dự án chỉ đổi ngữ cảnh; đổi dự án phải hủy lần đọc cũ.
        const next = readLocation();
        const changedProject = next.projectId !== locationRef.current.projectId;
        locationRef.current = next;
        setLocation(next);
        if (changedProject) setBootstrapAttempt((attempt) => attempt + 1);
        return;
      }
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
      setOpenActivityProject(projectId);
      setPage("data");
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
    setView(action.canonical_id ? "errors" : "raw");
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
        classification: actorRole === "owner" ? newClassification : "WORK",
      }),
    });
    chooseProject(p);
    setProjectOpen(false);
    setNewName("");
    setNewClassification("WORK");
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
    if(result.items[0])chooseDataset(result.items[0]);
    else setPage("data");
    setTab("explore");
    setSuccess(
      result.items.every((x) => x.reused)
        ? "Đã tìm thấy dữ liệu cùng nội dung và cấu hình trong dự án; tái sử dụng kết quả hiện có."
        : "Đã lưu tệp gốc. Đang đọc dữ liệu.",
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
            _preparation_flags: "Cần kiểm tra",
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
    <div
      className={`app-shell${compactNavigation ? " is-navigation-compact" : ""}`}
      data-focus-mode={focusMode}
      onPointerDownCapture={() => setFocusMode("pointer")}
      onKeyDownCapture={event => {
        const activation = (event.key === "Enter" || event.key === " ") &&
          event.target instanceof HTMLElement &&
          event.target.closest("button, a, summary, select, input[type='checkbox'], input[type='radio']");
        const dropdownNavigation = (event.key === "ArrowDown" || event.key === "ArrowUp") &&
          event.target instanceof HTMLElement &&
          event.target.closest("select, [role='combobox'], .dropdown-trigger");
        if (event.key === "Tab" || event.key === "Escape" || activation || dropdownNavigation) setFocusMode("keyboard");
      }}
    >
      <a className="skip-to-work" href="#main-content" inert={sidebar || undefined} onClick={event => {
        event.preventDefault();
        document.getElementById("main-content")?.focus();
      }}>Đến nội dung chính</a>
      {sidebar && (
        <button
          className="sidebar-scrim"
          aria-label="Đóng thanh điều hướng"
          tabIndex={-1}
          onClick={() => setSidebar(false)}
        />
      )}
      <aside
        id="studio-sidebar"
        ref={navigation}
        className={`sidebar ${sidebar ? "sidebar-open" : ""}`}
        role={sidebar ? "dialog" : undefined}
        aria-modal={sidebar || undefined}
        aria-label={sidebar ? "Điều hướng" : undefined}
      >
        <div className="sidebar-heading">
          <button type="button" className="brand" title="Reconciliation Studio"
            aria-label="Reconciliation Studio – về Dashboard"
            onClick={() => { if (page !== "home") setPage("home"); setSidebar(false); }}>
            <span className="brand-symbol"><Layers3 size={17} aria-hidden="true" /></span>
            <span className="brand-label">Reconciliation Studio</span>
          </button>
          {sidebar ? <button className="icon-button sidebar-close" aria-label="Đóng điều hướng" onClick={() => setSidebar(false)}>
            <X size={20} aria-hidden="true" />
          </button> : <button
            className="icon-button navigation-toggle"
            aria-label={navigationToggleLabel}
            title={navigationToggleLabel}
            aria-controls="studio-sidebar"
            aria-expanded={!compactNavigation}
            onClick={toggleNavigation}
          >
            {compactNavigation ? <PanelLeftOpen size={18} aria-hidden="true" /> : <PanelLeftClose size={18} aria-hidden="true" />}
          </button>}
        </div>
        <nav aria-label="Điều hướng chính">
          <button type="button" aria-label="Dashboard" title="Dashboard"
            className={page === "home" ? "active" : ""}
            aria-current={page === "home" ? "page" : undefined}
            onClick={() => { if (page !== "home") setPage("home"); setSidebar(false); }}>
            <LayoutDashboard size={18} aria-hidden="true" />
            <span>Dashboard</span>
          </button>
          <button
            aria-label="AI Assistant"
            title="AI Assistant"
            className={page === "assistant" ? "active" : ""}
            aria-current={page === "assistant" ? "page" : undefined}
            disabled={!ready}
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
            <Sparkles size={18} aria-hidden="true" />
            <span>AI Assistant</span>
          </button>
          {([
            ["data", "Dữ liệu", Database],
            ["reconcile", "Đối soát", Layers3],
            ["reports", "Báo cáo", FileSpreadsheet],
          ] as const).map(([target, label, Icon]) => (
            <button
              key={target}
              aria-label={label}
              title={label}
              className={page === target || (target === "reconcile" && page === "exceptions") ? "active" : ""}
              aria-current={page === target || (target === "reconcile" && page === "exceptions") ? "page" : undefined}
              disabled={!ready}
              onClick={() => {
                setPage(target);
                setSidebar(false);
              }}
            >
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
          <span className="navigation-group-label navigation-group-secondary" aria-hidden="true">Quản lý</span>
          <button disabled={!ready} aria-label="Lịch sử" title="Lịch sử" aria-expanded={assistantHistoryOpen} onClick={event => {
            assistantHistoryTrigger.current = window.matchMedia("(max-width: 900px)").matches
              ? document.querySelector<HTMLElement>(".menu-button") : event.currentTarget;
            setSidebar(false);
            setAssistantHistoryOpen(true);
          }}><History size={18} aria-hidden="true" /><span>Lịch sử</span></button>
          <button
            className={page === "settings" ? "active" : ""}
            aria-label="Cài đặt"
            title="Cài đặt"
            aria-current={page === "settings" ? "page" : undefined}
            onClick={() => {
              setPage("settings");
              setSidebar(false);
            }}
          >
            <Settings2 size={18} aria-hidden="true" />
            <span>Cài đặt</span>
          </button>
        </nav>
        <div className="sidebar-bottom">
          <div className="profile" title="Người dùng local">
            <span aria-hidden="true">LC</span>
            <div className="profile-label">
              <strong>Người dùng local</strong>
              <small>
                {actorRole === "viewer" ? "Chỉ xem" : actorRole === "editor" ? "Có quyền chỉnh sửa" :
                  actorRole === "owner" ? "Chủ không gian" : bootstrapError ? "Chưa xác minh phiên" : "Đang xác minh quyền"}
              </small>
            </div>
          </div>
        </div>
      </aside>
      <header className="topbar studio-masthead" inert={sidebar || undefined}>
        <button
          className="icon-button menu-button"
          aria-label="Mở điều hướng"
          aria-controls="studio-sidebar"
          aria-expanded={sidebar}
          onClick={() => setSidebar(true)}
        >
          <Menu size={20} aria-hidden="true" />
        </button>
        <div className="masthead-scope" role="group" aria-label="Phạm vi làm việc">
          {ready && workspace?.workspace_id && <WorkspaceManager key={workspace.workspace_id}
            returnToDashboard={page === "home"}
            current={{ id: workspace.workspace_id, name: workspace.workspace_name, role: actorRole }}
            onRename={name => setWorkspace(current => current ? { ...current, workspace_name: name } : current)} />}
          {ready && <ProjectSelector
            project={projectAccessDenied ? null : project} onSelect={chooseProject}
            disabled={busy} canClassify={actorRole === "owner"}
            onCreate={canEdit ? openNewProject : undefined}
            onManage={actorRole === "owner" ? () => openManagement({ kind: "projects" }, document.getElementById("project-select")) : undefined}
            onClassificationChange={value => setProject(current => current?.id === value.id ? value : current)}
          />}
        </div>
        <div className="topbar-end">
          <span className={`connection ${ready ? "connected" : bootstrapError ? "disconnected" : "connecting"}`} role="status" aria-label="Trạng thái kết nối"
            title={ready ? "Hệ thống đã kết nối" : bootstrapError ? "Chưa kết nối" : "Đang kết nối"}>
            <span aria-hidden="true" />
            <span className="connection-label">{ready ? "Đã kết nối" : bootstrapError ? "Chưa kết nối" : "Đang kết nối"}</span>
          </span>
        </div>
      </header>
      <div className="main-shell" ref={pageScroll} inert={sidebar || undefined}>
        <main
          id="main-content"
          tabIndex={-1}
          className={page === "assistant" ? "assistant-main" : ""}
          inert={restoringLocation || undefined}
        >
          {page !== "assistant" && page !== "home" && (!["reconcile", "exceptions", "reports"].includes(page) || !ready || !projectId || projectAccessDenied) && <div className="page-heading">
            <div>
              <h1>
                {page === "data"
                    ? "Quản lý dữ liệu"
                    : page === "reconcile"
                      ? "Đối soát có kiểm chứng"
                      : page === "exceptions"
                        ? "Ngoại lệ và bằng chứng"
                        : page === "reports"
                          ? "Báo cáo đối soát"
                          : "Cài đặt không gian làm việc"}
              </h1>
            </div>
            <div className="heading-actions">
              {page === "data" && ready && projectId && <button
                className="icon-button" aria-label="Cập nhật dự án" title="Cập nhật dự án"
                disabled={busy || projectLoading} onClick={() => void run(changed)}>
                <RefreshCw size={17} className={projectLoading ? "spin" : ""} />
              </button>}
              {page === "data" && (
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
          </div>}
          {bootstrapError && (
            <Notice tone="error">
              <div className="notice-content">
                <div>
                  <p>{bootstrapError.message}</p>
                  {page !== "home" && bootstrapError.code === "LOCAL_DEMO_NOT_VERIFIED" && (
                    <details>
                      <summary>Hướng dẫn cho người vận hành local</summary>
                      <p>Chạy <code>tools/verify-local.ps1</code> nếu các dịch vụ đang chạy. Sau đó thử kết nối lại.</p>
                    </details>
                  )}
                </div>
                <button className="text-button" onClick={() => {
                  setBootstrapError(null);
                  setBootstrapAttempt(attempt => attempt + 1);
                }}>Thử kết nối lại</button>
              </div>
            </Notice>
          )}
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
          {success && <Notice tone="success">{success.message}</Notice>}
          {!ready && !bootstrapError && <Spinner />}
          {ready && !projectId && !["home","settings","assistant"].includes(page) && (
            <Notice>
              Chọn hoặc tạo dự án để xem dữ liệu. Dự án chưa được chọn; không
              hiển thị số liệu của dự án khác.
            </Notice>
          )}
          {ready && projectId && projectError && (
            <Notice tone="error">
              {projectAccessDenied ? "Bạn không còn quyền xem dự án này. Chọn dự án khác hoặc thử lại nếu quyền đã được khôi phục." : `${projectError} Dữ liệu chưa cập nhật.`}
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
            !projectAccessDenied &&
            [
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
                    onSetup={() => { setRunNavigation(null); setPage("reconcile"); }}
                    onOpenExceptions={id => {
                      setRunNavigation({ id, request: Date.now() });
                      navigate("exceptions", { project_id: projectId, run_id: id });
                    }}
                    onRunSelected={(id, caseId) => {
                      const current = locationRef.current;
                      const actual = readLocation();
                      if (current.page === "assistant" || actual.page !== current.page ||
                          actual.projectId !== current.projectId) return;
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
            page === "assistant" &&
            !projectAccessDenied &&
            (!projectId || !assistantContext || assistantContext.project_id === projectId) && (
              <section className="assistant-page" aria-label="AI Assistant">
                {projectId && ["data","exceptions","reports"].includes(location.origin) && <button
                  className="text-button assistant-return"
                  onClick={() => {
                    const current = readLocation().context || assistantContext || {project_id:projectId};
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
                </button>}
                <Suspense fallback={<Spinner />}>
                  <AssistantStudio
                    key={JSON.stringify([assistantContext, location.conversationId])}
                    initialContext={assistantContext || {project_id:projectId}}
                    projectName={project?.name || "Chưa chọn dự án · tải file để bắt đầu"}
                    draftOwner={draftOwner}
                    initialConversationId={location.conversationId}
                    onContextChange={(context) => {
                      const current = readLocation();
                      if (
                        current.page === "assistant" &&
                        current.projectId === context.project_id
                      )
                        writeLocation({ ...current, context, conversationId: undefined }, true);
                    }}
                    agentEnabled={!!workspace?.agent_cloud_enabled}
                    uploadLimits={workspace?.agent_max_upload_files && workspace.agent_upload_extensions ? {
                      maxBytes: workspace.max_upload_bytes, maxFiles: workspace.agent_max_upload_files,
                      extensions: workspace.agent_upload_extensions,
                    } : undefined}
                    historyOpen={assistantHistoryOpen}
                    setHistoryOpen={setAssistantHistoryOpen}
                    historyReturnFocus={assistantHistoryTrigger}
                    onUploadProject={async id=>{const selected=await api<Project>(`/projects/${id}`);chooseProject(selected);}}
                    onScopeDenied={() => { void refreshProject(); }}
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
                        // Chat uploads update server state independently of the cached project list.
                        // Resolve the selected source by ID as well, including sources outside its page.
                        void run(async () => {
                          await refreshProject();
                          if (context.dataset_id)
                            await openPreparation({
                              kind: "REVIEW_DATA",
                              dataset_id: context.dataset_id,
                              table_id: null,
                              canonical_id: null,
                            });
                          else setPage("data");
                        });
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
          {page === "home" && (
            <DataOverview
              project={projectAccessDenied ? null : project}
              summary={projectAccessDenied ? null : summary}
              datasets={recent.projectId === projectId ? recent.items : []}
              recentLoading={recent.projectId !== projectId || recent.loading}
              recentError={recent.projectId === projectId ? recent.error : ""}
              onRecentRetry={() => setRecentRetry((value) => value + 1)}
              ready={ready}
              busy={busy}
              canEdit={canEdit}
              projectLoading={projectLoading}
              onCreate={openNewProject}
              onRefresh={() => void run(changed)}
              onAction={(action) => void run(() => openPreparation(action))}
              onResults={(id) => {
                setRunNavigation({ id, request: Date.now() });
                navigate("reports", { project_id: projectId, run_id: id });
              }}
              onNavigate={(target) => target === "assistant"
                ? openAssistant({ project_id: projectId })
                : setPage(target)}
              chooseDataset={chooseDataset}
            />
          )}
          {ready && projectId && summary && page === "data" && (
            <>
              <div className={`source-workspace${selectedDataset && !sourceListOpen ? " has-source-detail" : ""}`}>
                  <section className="source-inventory" aria-label="Danh mục nguồn" aria-busy={projectLoading}>
                    <div className="panel-heading">
                      <h2>
                        Nguồn dữ liệu{" "}
                        <span className="count">{datasetTotal}</span>
                      </h2>
                      {actorRole === "owner" && <button type="button" className="text-button" id="manage-sources"
                        onClick={event => openManagement({ kind: "datasets", projectId }, event.currentTarget)}>Quản lý nguồn</button>}
                    </div>
                    <label className="search-input inventory-search">
                      <Search size={17} aria-hidden="true" />
                      <input id="source-search" type="search" aria-label="Tìm nguồn dữ liệu" placeholder="Tìm nguồn theo tên…" maxLength={200}
                        value={datasetSearch} onChange={event => { setDatasetSearch(event.target.value); setDatasetOffset(0); }} />
                    </label>
                    {projectLoading && <Spinner />}
                    {datasets.length ? <ul className="inventory-rows dataset-list">
                      {datasets.map(source => <li key={source.id} className="inventory-row">
                        <button className="source-name" aria-current={selectedDataset?.id === source.id ? "true" : undefined}
                          onClick={event => {
                            const inventory = event.currentTarget.closest(".source-inventory");
                            chooseDataset(source);
                            requestAnimationFrame(() => {
                              if (inventory?.getClientRects().length === 0) {
                                document.getElementById("source-title")?.focus();
                              }
                            });
                          }}>
                          <FileSpreadsheet size={18} aria-hidden="true" /><span>{source.name}</span>
                        </button>
                        <Badge status={source.status} />
                        <time dateTime={source.created_at}>{new Date(source.created_at).toLocaleDateString("vi-VN")}</time>
                        {actorRole === "owner" && selectedDataset?.id !== source.id && <button className="icon-button" aria-label={`Quản lý ${source.name}`}
                          onClick={event => openManagement({ kind: "datasets", projectId, id: source.id }, event.currentTarget)}><MoreHorizontal size={18} /></button>}
                      </li>)}
                    </ul> : !projectLoading && <div className="empty-state">
                      <Database size={28} aria-hidden="true" />
                      <h3>{datasetSearch.trim() ? "Không tìm thấy nguồn phù hợp" : "Chưa có nguồn dữ liệu"}</h3>
                      {datasetSearch.trim() ? <button className="text-button" onClick={() => setDatasetSearch("")}>Xóa tìm kiếm</button> : <p>Tải tệp để bắt đầu.</p>}
                    </div>}
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
                  {selectedDataset && !sourceListOpen && (
                    <section className="detail-panel source-sheet">
                      <button type="button" className="text-button source-back" onClick={() => {
                        setSourceListOpen(true);
                        setSelectedSource(null);
                        setDatasetId("");
                        navigate("data", null);
                        requestAnimationFrame(() => document.getElementById("source-search")?.focus());
                      }}>
                        <ChevronLeft size={16} /> Về danh mục nguồn
                      </button>
                      <div className="panel-heading">
                        <div className="source-title">
                          <h2 id="source-title" tabIndex={-1}>{selectedDataset.name}</h2>
                          <Badge status={selectedDataset.status} />
                        </div>
                        {actorRole === "owner" && <button className="icon-button" aria-label={`Quản lý ${selectedDataset.name}`}
                          onClick={event => openManagement({ kind: "datasets", projectId, id: selectedDataset.id }, event.currentTarget)}><MoreHorizontal size={18} /></button>}
                      </div>
                      {selectedDataset.status === "PARTIAL" && (
                        <div className="source-warning" role="status">
                          {currentCanonical ? `Dữ liệu cần kiểm tra · ${currentCanonical.invalid_count} / ${currentCanonical.row_count} dòng` : "Có dòng cần kiểm tra"}
                          {currentCanonical && (
                            <button
                              className="text-button"
                              onClick={() => {
                                setTab("explore");
                                setView("errors");
                                setOffset(0);
                              }}
                            >
                              Xem lỗi
                            </button>
                          )}
                        </div>
                      )}
                      {tableRequest.datasetId !== datasetId || tableRequest.loading && !tables.length ? <Spinner />
                        : tableRequest.error ? <Notice tone="error">{tableRequest.error}
                          <button className="text-button" onClick={() => void loadTables()}>Tải lại bảng dữ liệu</button>
                        </Notice> : tables.length === 0 ? (
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
                              Bảng dữ liệu
                              <select
                                value={tableId}
                                onChange={(e) => {
                                  if (e.target.value === tableId) return;
                                  setProfile(null);
                                  setMappings([]);
                                  setCanonicals([]);
                                  setPreview(null);
                                  setPendingTarget(null);
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
                            {canEdit && tab !== "normalize" && detailScope === `${datasetId}:${tableId}` &&
                              activeMapping?.status === "APPROVED" && !canonicals.some(c =>
                                c.mapping_revision_id === activeMapping.id && !c.stale
                              ) && (
                                <button className="button primary" disabled={busy}
                                  onClick={() => { setTab("normalize"); void run(normalize); }}>
                                  <Layers3 size={17} aria-hidden="true" /> Chuẩn hóa dữ liệu
                                </button>
                              )}
                          </div>
                          <div
                            className="source-workflow"
                            role="group"
                            aria-label="Công việc với nguồn"
                          >
                            {(
                              [
                                ["explore", "Xem dữ liệu"],
                                ["mapping", "Xác nhận cột"],
                                ["normalize", "Tạo bản chuẩn hóa"],
                              ] as const
                            ).map(([key, label]) => (
                              <button
                                aria-pressed={tab === key}
                                className={`button ${tab === key ? "secondary selected" : "secondary"}`}
                                key={key}
                                onClick={() => setTab(key)}
                              >
                                {label}
                              </button>
                            ))}
                          </div>
                          <div className="tab-content">
                            {tab === "mapping" && table && profile && detailScope===`${datasetId}:${tableId}` && (
                              <MappingStudio
                                key={table.id}
                                draftOwner={draftOwner}
                                readOnly={!canEdit}
                                canManageReuse={actorRole === "owner"}
                                table={table}
                                profile={profile}
                                mappings={mappings}
                                latestJob={mappingJob}
                                busy={busy}
                                run={run}
                                onReload={loadDetails}
                                onRevisionChange={changed}
                                onProposalAvailable={setSuccess}
                                onApproved={async () => {
                                  await changed();
                                  setSuccess("Đã cập nhật ánh xạ.");
                                }}
                                onEvidence={showEvidence}
                                onOpenConversation={(id) => navigate("assistant", {project_id: projectId}, projectId, false, id)}
                              />
                            )}
                            {tab === "normalize" && (
                              <>
                                <div className="section-heading">
                                  <div>
                                    <h2>Chuẩn hóa theo ánh xạ đã duyệt</h2>
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
                                      Xác nhận cột <ArrowRight size={14} />
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
                                              Phiên bản cũ · không dùng cho xử lý
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
                                  <label className="source-view">
                                    <span>Lớp dữ liệu</span>
                                    <select value={view === "prepared_findings" ? "errors" : view}
                                      onChange={event => {
                                        const next = event.target.value as View;
                                        setView(next === "errors" && !canonicalId ? "prepared_findings" : next);
                                        setOffset(0);
                                      }}>
                                      <option value="raw">Giá trị gốc</option>
                                      <option value="prepared" disabled={!table?.prepared}>Tự chuẩn bị</option>
                                      <option value="canonical" disabled={!canonicalId}>Đã chuẩn hóa</option>
                                      <option value="errors" disabled={!canonicalId && !table?.prepared}>Cảnh báo / lỗi</option>
                                    </select>
                                  </label>
                                  <label className="search-input">
                                    <Search size={17} aria-hidden="true" />
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
                                      hóa lại theo cách đọc cột hiện hành.
                                    </Notice>
                                  )}
                                {view === "raw" && (
                                  <Notice>
                                    Các giá trị được đọc từ ô nguồn. Tệp gốc được giữ nguyên
                                    và công thức Excel không được thực thi.
                                  </Notice>
                                )}
                                {["prepared", "prepared_findings"].includes(view) && table?.prepared && (
                                  <>
                                    <Notice>
                                      Đã tự chuẩn bị để xem và tìm kiếm. Cần xác nhận ý nghĩa
                                      nghiệp vụ trước khi dùng để đối soát.
                                    </Notice>
                                    {table.prepared.quality_summary
                                      .filter((column) => column.invalid_date_count > 0)
                                      .map((column) => (
                                        <Notice tone="warning" key={column.column_id}>
                                          {table.parsed.columns.find((source) => source.id === column.column_id)?.name}
                                          {" · "}{column.invalid_date_count} giá trị ngày cần kiểm tra
                                        </Notice>
                                      ))}
                                    {table.prepared.quality_summary.some((column) => column.invalid_date_count > 0) && (
                                      <button
                                        className="button secondary compact"
                                        onClick={() => {
                                          setView(view === "prepared" ? "prepared_findings" : "prepared");
                                          setOffset(0);
                                        }}
                                      >
                                        {view === "prepared" ? "Xem dòng cần kiểm tra" : "Xem toàn bộ dòng"}
                                      </button>
                                    )}
                                  </>
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
              </div>
            </>
          )}
          {ready && page === "settings" && workspace && (
            <WorkspaceSettingsPanel settings={workspace} role={actorRole}
              tableDensity={tableDensity} onDensityChange={setTableDensity}
              onManageProjects={actorRole === "owner" ? trigger => openManagement({ kind: "projects" }, trigger) : undefined} />
          )}
          {ready &&
            jobs.length > 0 &&
            page !== "home" &&
            page !== "settings" &&
            page !== "assistant" && (
              <section className="panel jobs-panel" aria-label="Hoạt động xử lý">
                <div className="jobs-panel-bar">
                  <button
                    className="jobs-disclosure"
                    aria-expanded={openActivityProject === projectId}
                    aria-controls="project-jobs"
                    onClick={() => setOpenActivityProject(current => current === projectId ? "" : projectId)}
                  >
                    <ChevronDown size={15} aria-hidden="true" />
                    <strong>Hoạt động xử lý</strong>
                    <span>{activeJobs ? `${activeJobs} đang xử lý` : `${Math.min(jobs.length, 6)} hoạt động gần đây`}</span>
                  </button>
                  <button
                    className="icon-button"
                    title="Cập nhật trạng thái xử lý"
                    aria-label="Cập nhật trạng thái xử lý"
                    disabled={busy}
                    onClick={() => void run(changed)}
                  >
                    <RefreshCw size={16} aria-hidden="true" />
                  </button>
                </div>
                <div id="project-jobs" hidden={openActivityProject !== projectId}>
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
                </div>
              </section>
            )}
        </main>
      </div>
      {page !== "assistant" && assistantHistoryOpen && <ProjectHistory key={projectId}
        projectId={projectId} projectName={project?.name || "Dự án"} returnFocus={assistantHistoryTrigger}
        onClose={() => setAssistantHistoryOpen(false)} onOpen={id => {
          setAssistantHistoryOpen(false);
          navigate("assistant", { project_id: projectId }, projectId, false, id);
        }} />}
      {manage && actorRole === "owner" && <ResourceManagement target={manage} returnFocus={manageTrigger} onClose={() => setManage(null)}
        onChanged={(id, parent, state, name) => {
          if (parent !== projectId) return;
          if (manage.kind === "projects" && state !== "active") {
            chooseProject(null);
            return;
          }
          if (manage.kind === "datasets" && id === datasetId && state !== "active") {
            setDatasetId(""); setSelectedSource(null); setSourceListOpen(true);
            navigate("data", null, projectId, true);
          }
          if (manage.kind === "datasets" && name) {
            setSelectedSource(source => source?.id === id ? { ...source, name } : source);
            setDatasets(sources => sources.map(source => source.id === id ? { ...source, name } : source));
          }
          if (manage.kind === "datasets" && state !== "active") {
            requestAnimationFrame(() => {
              manageTrigger.current = document.getElementById("manage-sources") ?? document.getElementById("project-select");
            });
          }
          void refreshProject();
        }} />}
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
          {actorRole === "owner" && <label>
            Nhóm dự án
            <select value={newClassification} onChange={event => setNewClassification(event.target.value as ProjectClassification)}>
              <option value="WORK">Công việc</option>
              <option value="TEST">Thử nghiệm</option>
            </select>
          </label>}
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
              Dùng AI đề xuất cách đọc cột
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
