import { expect, test, type Page } from "@playwright/test";

type Project = { id: string; name: string; business_scope: string; workspace_id: string };
const projects = (count: number): Project[] => Array.from({ length: count }, (_, i) => ({
  id: `project-${String(i).padStart(3, "0")}`,
  name: "Đối soát đơn hàng",
  business_scope: `Kho miền Nam ${String(i).padStart(3, "0")}`,
  workspace_id: "synthetic",
}));

/** Browser-only API contract fixtures never create production projects or jobs. */
async function fixture(page: Page, items: Project[], saved?: string) {
  await page.addInitScript(id => {
    localStorage.clear();
    if (id) localStorage.setItem("studio.project", id);
  }, saved);
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (route.request().method() !== "GET") throw new Error(`Unexpected mutation: ${path}`);
    if (path === "/api/session") return route.fulfill({ json: { workspace_id: "synthetic", role: "owner" } });
    if (path === "/api/settings") return route.fulfill({ json: {
      workspace_name: "Synthetic", mapping_ai_provider: "GEMINI", policy: { allow_external_ai: false },
      max_upload_bytes: 20971520, max_upload_files: 10, max_rows: 100000,
    } });
    if (path === "/api/projects") {
      const search = (url.searchParams.get("search") || "").toLocaleLowerCase("vi");
      const matches = items.filter(p => `${p.name} ${p.business_scope}`.toLocaleLowerCase("vi").includes(search));
      const offset = Number(url.searchParams.get("offset") || 0);
      const limit = Number(url.searchParams.get("limit") || 50);
      return route.fulfill({ json: { items: matches.slice(offset, offset + limit), total: matches.length } });
    }
    if (/^\/api\/projects\/[^/]+$/.test(path)) {
      const project = items.find(p => p.id === path.split("/").at(-1));
      return route.fulfill(project ? { json: project } : { status: 404, json: { code: "RESOURCE_NOT_FOUND" } });
    }
    if (path.endsWith("/summary")) return route.fulfill({ json: { dataset_count: 0, table_count: 0,
      mapping_review_count: 0, ready_canonical_count: 0, active_job_count: 0 } });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
}

for (const count of [1, 10, 50, 120]) {
  test(`project picker: ${count} projects, bounded pagination and keyboard selection`, async ({ page }) => {
    const items = projects(count);
    await fixture(page, items);
    await page.goto("/");
    const trigger = page.locator("#project-select");
    await trigger.click();
    const search = page.getByRole("combobox", { name: "Tìm dự án", exact: true });
    await expect(search).toBeFocused();
    await expect(page.getByRole("option")).toHaveCount(Math.min(20, count));
    if (count > 20) {
      await page.getByRole("button", { name: "Trang dự án sau", exact: true }).click();
      await expect(page.getByRole("option").first()).toContainText("miền Nam 020");
    }
    await search.fill(items.at(-1)!.business_scope.toLocaleUpperCase("vi"));
    await expect(page.getByRole("option")).toHaveCount(1);
    await search.press("ArrowDown");
    await search.press("Enter");
    await expect(trigger).toHaveAttribute("data-project-id", items.at(-1)!.id);
    await expect(trigger).toBeFocused();
    await trigger.click();
    await search.fill("không tồn tại");
    await expect(page.getByText("Không có dự án phù hợp.", { exact: false })).toBeVisible();
    await search.press("Escape");
    await expect(trigger).toBeFocused();
  });
}

test("restore saved off-page project; unavailable saved ID never silently selects another", async ({ page }) => {
  const items = projects(120);
  await fixture(page, items, items[119].id);
  await page.goto("/");
  await expect(page.locator("#project-select")).toHaveAttribute("data-project-id", items[119].id);
  await page.reload();
  await expect(page.locator("#project-select")).toHaveAttribute("data-project-id", items[119].id);
  items.pop();
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("không còn tồn tại");
  await expect(page.locator("#project-select")).toHaveAttribute("data-project-id", "");
});

test("project search discards delayed results and exposes loading and retry errors", async ({ page }) => {
  await fixture(page, projects(120));
  let release!: () => void;
  const delayed = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/projects?**", async route => {
    const search = new URL(route.request().url()).searchParams.get("search");
    if (search === "old") {
      await delayed;
      return route.fulfill({ json: { items: [{ ...projects(1)[0], name: "Old response" }], total: 1 } });
    }
    if (search === "error") return route.fulfill({ status: 503, json: { message_vi: "Không tải được dự án tổng hợp" } });
    return route.fallback();
  });
  await page.goto("/");
  await page.locator("#project-select").click();
  const search = page.getByRole("combobox", { name: "Tìm dự án", exact: true });
  const oldRequest = page.waitForRequest(r => new URL(r.url()).searchParams.get("search") === "old");
  await search.fill("old");
  await expect(page.getByRole("listbox")).toHaveAttribute("aria-busy", "true");
  await oldRequest;
  await search.fill("miền Nam 119");
  await expect(page.getByRole("option")).toContainText("119");
  release();
  await expect(page.getByText("Old response")).toHaveCount(0);
  await search.fill("error");
  await expect(page.getByRole("alert")).toContainText("Không tải được");
  await expect(page.getByRole("button", { name: "Thử lại", exact: true })).toBeVisible();
});
