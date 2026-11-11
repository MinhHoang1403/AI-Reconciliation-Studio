import type { AssistantContext } from "./assistantTypes";

export type Page =
  | "home"
  | "data"
  | "settings"
  | "reconcile"
  | "exceptions"
  | "reports"
  | "assistant";
export type Location = {
  page: Page;
  projectId: string;
  context: AssistantContext | null;
  origin: Exclude<Page, "assistant">;
  conversationId?: string;
};
const pages: Page[] = [
  "home",
  "data",
  "settings",
  "reconcile",
  "exceptions",
  "reports",
  "assistant",
];

/** URLs contain identifiers only. The API still authorizes every restored resource. */
export function readLocation(): Location {
  const query = new URLSearchParams(window.location.hash.slice(1));
  const requestedPage = pages.find((p) => p === query.get("page")) || "home";
  const id = (key: string) => {
    const value = query.get(key) || "";
    return /^[a-zA-Z0-9_-]{1,64}$/.test(value) ? value : "";
  };
  const projectId = id("project");
  // Older Home URLs could include an exact run selected in the embedded results.
  const page = requestedPage === "home" && projectId && id("run_id") ? "reports" : requestedPage;
  const context: AssistantContext = { project_id: projectId };
  for (const key of ["run_id", "dataset_id", "group_id", "case_id"] as const)
    if (id(key)) context[key] = id(key);
  const origin =
    pages.find((p) => p !== "assistant" && p === query.get("from")) || "home";
  return {
    page,
    projectId,
    context: projectId ? context : null,
    origin: origin as Location["origin"],
    ...(page === "assistant" && id("conversation") ? { conversationId: id("conversation") } : {}),
  };
}

export function writeLocation(location: Location, replace = false) {
  const query = new URLSearchParams({ page: location.page, project: location.projectId });
  if (location.page === "assistant") query.set("from", location.origin);
  if (location.page === "assistant" && location.conversationId)
    query.set("conversation", location.conversationId);
  for (const key of ["run_id", "dataset_id", "group_id", "case_id"] as const)
    if (location.context?.[key]) query.set(key, location.context[key]!);
  window.history[replace ? "replaceState" : "pushState"](null, "", `#${query}`);
}
