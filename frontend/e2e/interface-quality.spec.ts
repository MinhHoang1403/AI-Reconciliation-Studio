import { test } from "./project-selection";
import { openLegacyPage } from "./project-selection";
import { expect, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const uncaughtErrors = new WeakMap<Page, string[]>();
test.beforeEach(({ page }) => {
  const errors: string[] = [];
  uncaughtErrors.set(page, errors);
  page.on("pageerror", (error) => errors.push(error.message));
});
test.afterEach(({ page }) => {
  expect(uncaughtErrors.get(page)).toEqual([]);
});

type Project = {
  id: string;
  name: string;
  business_scope: string;
  workspace_id: string;
  classification?: "WORK" | "TEST" | "UNKNOWN";
};
const projects = (count: number): Project[] =>
  Array.from({ length: count }, (_, i) => ({
    id: `project-${String(i).padStart(3, "0")}`,
    name: "Đối soát đơn hàng",
    business_scope: `Kho miền Nam ${String(i).padStart(3, "0")}`,
    workspace_id: "synthetic",
  }));

test("[MOCK CONTRACT] desktop shell holds navigation and account while long data scrolls", async ({ page }) => {
  await fixture(page, projects(1), "project-000");
  await page.route("**/api/datasets?**", route => route.fulfill({ json: {
    total: 25,
    items: Array.from({ length: 25 }, (_, index) => ({
      id: `shell-source-${index}`, project_id: "project-000",
      name: `Nguồn tổng hợp ${index}.csv`, status: index === 0 ? "NEEDS_MAPPING_REVIEW" : "PARSED",
      created_at: "2026-11-03",
    })),
  } }));
  await page.route("**/api/jobs?**", route => route.fulfill({ json: {
    items: [{ id: "shell-job", kind: "report", status: "RUNNING" }],
  } }));
  await page.goto("/#page=data");
  await expect(page.getByText("Nguồn tổng hợp 24.csv", { exact: true })).toBeAttached();
  const rows = page.locator(".inventory-row");
  for (const column of [".badge", "time", ".icon-button"]) {
    const first = await rows.nth(0).locator(column).boundingBox();
    const second = await rows.nth(1).locator(column).boundingBox();
    expect(first?.x).toBe(second?.x);
  }
  const sidebar = page.locator(".sidebar");
  const account = sidebar.getByText("Người dùng local", { exact: true });
  const header = page.getByRole("banner");
  const scroll = page.locator(".main-shell");
  const initial = await sidebar.boundingBox();
  const headerPosition = await header.boundingBox();
  const accountPosition = await account.boundingBox();
  expect(initial?.y).toBe(0);
  expect(initial?.height).toBe(900);
  await expect(sidebar.getByText("Reconciliation Studio", { exact: true })).toBeVisible();
  await expect(header.getByText("Reconciliation Studio", { exact: true })).toHaveCount(0);
  const toggle = sidebar.locator(".navigation-toggle");
  await expect(toggle).toHaveAccessibleName("Thu gọn thanh điều hướng");
  await expect(toggle).toHaveAttribute("aria-controls", "studio-sidebar");
  await expect(header.locator(".navigation-toggle")).toHaveCount(0);
  const brand = (await sidebar.locator(".brand").boundingBox())!;
  const toggleBox = (await toggle.boundingBox())!;
  expect(brand.x + brand.width).toBeLessThan(toggleBox.x);
  expect(brand.y + brand.height / 2).toBeCloseTo(toggleBox.y + toggleBox.height / 2, 0);
  for (const portion of [0.5, 1, 0]) {
    const moved = await scroll.evaluate((element, ratio) => {
      const range = element.scrollHeight - element.clientHeight;
      element.scrollTop = range * ratio;
      return { range, scrolled: element.scrollTop, body: window.scrollY };
    }, portion);
    expect(moved.range).toBeGreaterThan(0);
    expect(Math.abs(moved.scrolled - moved.range * portion)).toBeLessThanOrEqual(1);
    expect(moved.body).toBe(0);
    expect(await sidebar.boundingBox()).toEqual(initial);
    expect(await account.boundingBox()).toEqual(accountPosition);
    expect(await header.boundingBox()).toEqual(headerPosition);
  }
  const activity = page.getByRole("button", { name: /Hoạt động xử lý.*1 đang xử lý/ });
  await expect(activity).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("button", { name: "Cập nhật trạng thái xử lý" })).toBeVisible();
  await activity.click();
  await expect(activity).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator("#project-jobs")).toBeVisible();
  await scroll.evaluate(element => { element.scrollTop = element.scrollHeight; });
  await sidebar.getByRole("button", { name: "Báo cáo", exact: true }).click();
  await expect(page).toHaveURL(/page=reports/);
  expect(await scroll.evaluate(element => element.scrollTop)).toBe(0);
  await toggle.press("Enter");
  await expect(toggle).toBeFocused();
  await expect(toggle).toHaveAccessibleName("Mở rộng thanh điều hướng");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(toggle).toHaveAttribute("title", "Mở rộng thanh điều hướng");
  await expect(sidebar.getByRole("button", { name: "Dữ liệu", exact: true })).toHaveAttribute("title", "Dữ liệu");
  await expect(sidebar.getByRole("button", { name: "Báo cáo", exact: true })).toHaveAttribute("aria-current", "page");
  expect(await sidebar.boundingBox()).toMatchObject({ width: 64, height: 900 });
  expect((await header.boundingBox())?.x).toBe(64);
  await toggle.press("Space");
  await expect(toggle).toBeFocused();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(await sidebar.boundingBox()).toEqual(initial);
  for (const [name, target] of [["AI Assistant", "assistant"], ["Đối soát", "reconcile"], ["Cài đặt", "settings"]]) {
    const item = sidebar.getByRole("button", { name, exact: true });
    await item.click();
    await expect(page).toHaveURL(new RegExp(`page=${target}`));
    await expect(item).toHaveAttribute("aria-current", "page");
    expect(await sidebar.boundingBox()).toEqual(initial);
    expect(await account.boundingBox()).toEqual(accountPosition);
  }
  await page.setViewportSize({ width: 1366, height: 340 });
  const accountAtShortHeight = await account.boundingBox();
  const headingAtShortHeight = await toggle.boundingBox();
  const menuOffset = await sidebar.locator("nav").evaluate(element => {
    element.scrollTop = element.scrollHeight;
    return element.scrollTop;
  });
  expect(menuOffset).toBeGreaterThan(0);
  expect(await account.boundingBox()).toEqual(accountAtShortHeight);
  expect(await toggle.boundingBox()).toEqual(headingAtShortHeight);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(sidebar).toBeHidden();
  const menu = page.getByRole("button", { name: "Mở điều hướng", exact: true });
  await menu.press("Enter");
  await expect(sidebar.getByRole("button", { name: "Đóng điều hướng" })).toBeFocused();
  await expect(sidebar.getByText("Reconciliation Studio", { exact: true })).toBeVisible();
  await expect(toggle).toHaveCount(0);
  await page.keyboard.press("Shift+Tab");
  await expect(sidebar.getByRole("button", { name: "Cài đặt", exact: true })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(sidebar.getByRole("button", { name: "Đóng điều hướng" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(menu).toBeFocused();
});

test("[MOCK CONTRACT] long scope names stay accessible and picker focus returns across the header", async ({ page }) => {
  const [project] = projects(1);
  project.name = "Dự án đối chiếu dài của bộ phận kiểm soát doanh thu và thanh toán";
  project.classification = "TEST";
  const workspace = "Không gian đối chiếu của các bộ phận tài chính và vận hành";
  await fixture(page, [project], project.id);
  await page.route("**/api/settings", route => route.fulfill({ json: {
    workspace_id: "synthetic", workspace_name: workspace,
    mapping_ai_provider: "GEMINI",
    policy: { allow_external_ai: false },
    max_upload_bytes: 20971520, max_upload_files: 10, max_rows: 100000,
  } }));
  await page.route("**/api/workspaces", route => route.fulfill({ json: [
    { id: "synthetic", name: workspace, role: "owner" },
  ] }));
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/#page=settings");
  const workspaceButton = page.getByRole("button", { name: "Quản lý không gian làm việc" });
  const projectButton = page.getByRole("button", { name: `Dự án: ${project.name}` });
  await expect(workspaceButton).toHaveAttribute("title", workspace);
  await expect(projectButton).toHaveAttribute("title", project.name);
  expect((await workspaceButton.boundingBox())?.height).toBe(44);
  expect((await projectButton.boundingBox())?.height).toBe(44);
  await workspaceButton.press("Enter");
  await expect(page.getByRole("dialog").locator(".workspace-selected-name")).toHaveText(workspace);
  await page.keyboard.press("Escape");
  await expect(workspaceButton).toBeFocused();
  await projectButton.press("Enter");
  await expect(page.getByRole("combobox", { name: "Tìm dự án" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(projectButton).toBeFocused();
  await expect(projectButton).toHaveAttribute("data-project-id", project.id);
  for (const width of [320, 390, 1366]) {
    await page.setViewportSize({ width, height: 800 });
    const workspaceBox = (await workspaceButton.boundingBox())!;
    const projectBox = (await projectButton.boundingBox())!;
    const statusBox = (await page.locator(".topbar-end").boundingBox())!;
    expect(workspaceBox.x + workspaceBox.width).toBeLessThan(projectBox.x);
    expect(projectBox.x + projectBox.width).toBeLessThan(statusBox.x);
    expect(workspaceBox.height).toBe(width <= 900 ? 44 : 38);
    expect(projectBox.height).toBe(workspaceBox.height);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
  }
});

test("[MOCK CONTRACT] keyboard focus stays visible when a long mobile dialog wraps", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page, projects(25), "project-000");
  await page.goto("/#page=settings");
  const trigger = page.getByRole("button", { name: "Quản lý dự án", exact: true });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Quản lý dự án" });
  const close = dialog.getByRole("button", { name: "Đóng", exact: true });
  const next = dialog.getByRole("button", { name: "Trang sau", exact: true });
  await expect(next).not.toBeInViewport();
  await close.focus();
  await page.keyboard.press("Shift+Tab");
  await expect(next).toBeFocused();
  await expect(next).toBeInViewport();
  await page.keyboard.press("Tab");
  await expect(close).toBeFocused();
  await expect(close).toBeInViewport();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
});

for (const width of [390, 1440]) {
  test(`source search separates click and keyboard focus at ${width}px`, async ({ page }) => {
    await fixture(page, projects(1), "project-000");
    await page.setViewportSize({ width, height: 620 });
    await page.goto("/#page=data");
    const search = page.getByRole("searchbox", { name: "Tìm nguồn dữ liệu" });
    await expect(search).toBeVisible();
    const before = await search.boundingBox();
    const background = await search.evaluate(element => getComputedStyle(element).backgroundColor);
    const spacing = await search.evaluate(element => {
      const field = element.getBoundingClientRect();
      const icon = element.previousElementSibling!.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        textGap: field.left + parseFloat(style.borderLeftWidth) + parseFloat(style.paddingLeft) - icon.right,
        centerDelta: Math.abs(field.top + field.height / 2 - icon.top - icon.height / 2),
      };
    });
    expect(spacing.textGap).toBeGreaterThanOrEqual(6);
    expect(spacing.centerDelta).toBeLessThanOrEqual(1);
    await search.click();
    await expect(search).toBeFocused();
    await expect(search).toHaveCSS("outline-style", "none");
    await expect(search).toHaveCSS("box-shadow", "none");
    await expect(search).toHaveCSS("background-color", background);
    expect(await search.boundingBox()).toEqual(before);
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    await expect(search).toBeFocused();
    await expect(search).toHaveCSS("box-shadow", /0px -2px 0px 0px inset/);
    expect(await search.boundingBox()).toEqual(before);
    await search.click();
    await expect(search).toHaveCSS("box-shadow", "none");
  });
}

test("[MOCK CONTRACT] long workspace list searches and closes before its management panel", async ({ page }) => {
  await fixture(page, projects(1), "project-000");
  await page.setViewportSize({ width: 390, height: 620 });
  await page.route("**/api/settings", route => route.fulfill({ json: {
    workspace_id: "synthetic", workspace_name: "Synthetic",
    policy: { allow_external_ai: false },
    max_upload_bytes: 20971520, max_upload_files: 10, max_rows: 100000,
  } }));
  await page.route("**/api/workspaces", route => route.fulfill({ json: [
    { id: "synthetic", name: "Synthetic", role: "owner" },
    ...Array.from({ length: 12 }, (_, index) => ({
      id: `workspace-${index}`, name: `Đối soát chi nhánh ${index}`, role: "editor",
    })),
  ] }));
  await page.goto("/#page=settings");
  const header = page.locator(".workspace-picker");
  const anchor = (await header.boundingBox())!;
  await header.click();
  const dialog = page.getByRole("dialog", { name: "Quản lý không gian làm việc", exact: true });
  const bounds = (await dialog.boundingBox())!;
  expect(bounds.y - anchor.y - anchor.height).toBeCloseTo(4, 0);
  const trigger = dialog.getByRole("button", { name: "Không gian có quyền truy cập", exact: true });
  await trigger.press("ArrowDown");
  const search = dialog.getByRole("combobox", { name: "Tìm không gian làm việc" });
  await expect(search).toBeFocused();
  const list = dialog.getByRole("listbox");
  expect(await list.evaluate(element => element.scrollHeight)).toBeGreaterThan(
    (await list.boundingBox())!.height,
  );
  await search.fill("doi soat chi nhanh 11");
  await expect(list.getByRole("option")).toHaveCount(1);
  await search.press("Enter");
  await expect(trigger).toBeFocused();
  await expect(trigger).toContainText("Đối soát chi nhánh 11");
  await trigger.press("Enter");
  await search.press("Escape");
  await expect(search).not.toBeVisible();
  await expect(dialog).toBeVisible();
  await expect(trigger).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(header).toBeFocused();
});

test("[MOCK CONTRACT] project lifecycle previews impact and restores the hidden project", async ({ page }) => {
  const [sample] = projects(1);
  sample.classification = "TEST";
  await fixture(page, [sample], sample.id);
  let state = "active";
  let version = 0;
  const writes: unknown[] = [];
  await page.route(`**/api/projects/${sample.id}/lifecycle`, async route => {
    if (route.request().method() === "POST") {
      const request = route.request().postDataJSON();
      writes.push(request);
      state = request.action === "restore" ? "active" : "deleted";
      version++;
    }
    return route.fulfill({ json: {
      id: sample.id, project_id: sample.id, name: sample.name,
      state, version, references: {}, running_jobs: 0, open_work: 0,
      allowed: state === "active" ? ["archive", "delete"] : ["restore"],
    } });
  });
  await page.route("**/api/projects?**", route => {
    const filter = new URL(route.request().url()).searchParams.get("lifecycle");
    if (!filter) return route.fallback();
    return route.fulfill({ json: { items: filter === state ? [sample] : [], total: filter === state ? 1 : 0 } });
  });
  await page.goto("/#page=settings");
  const trigger = page.getByRole("button", { name: "Quản lý dự án", exact: true });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Quản lý dự án" });
  await dialog.getByRole("button", { name: `Quản lý ${sample.name}`, exact: true }).click();
  await expect(dialog.getByRole("region", { name: "Tác động" })).toContainText(sample.name);
  await dialog.getByRole("button", { name: "Đưa vào Thùng rác", exact: true }).click();
  const confirm = dialog.getByRole("button", { name: "Xác nhận xóa", exact: true });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel("Nhập lại tên dự án").fill(sample.name);
  await confirm.click();
  await expect(dialog.getByText("Đã xóa khỏi danh sách.", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Danh sách dự án" }).click();
  await dialog.getByRole("combobox", { name: "Danh sách" }).selectOption("deleted");
  await dialog.getByRole("button", { name: `Quản lý ${sample.name}`, exact: true }).click();
  await dialog.getByRole("button", { name: "Khôi phục", exact: true }).click();
  await dialog.getByRole("button", { name: "Xác nhận khôi phục", exact: true }).click();
  await expect(dialog.getByText("Đã khôi phục.", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Đóng", exact: true }).click();
  await expect(trigger).toBeFocused();
  expect(writes).toEqual([
    { action: "delete", expected_state: "active", expected_version: 0, confirmation: sample.name },
    { action: "restore", expected_state: "deleted", expected_version: 1, confirmation: "" },
  ]);
});

test("[MOCK CONTRACT] permanent deletion confirms the exact name and waits for verified completion", async ({ page }) => {
  const [sample] = projects(1);
  const fingerprint = "a".repeat(64);
  const writes: unknown[] = [];
  let finish = false;
  await fixture(page, [sample], sample.id);
  await page.route("**/api/permanent-deletion-capability", route =>
    route.fulfill({ json: { enabled: true, workspace_id: null } }));
  await page.route(`**/api/projects/${sample.id}/lifecycle`, route => route.fulfill({ json: {
    id: sample.id, project_id: sample.id, name: sample.name, state: "active",
    version: 0, references: {}, running_jobs: 0, open_work: 0, allowed: ["archive"],
  } }));
  await page.route(`**/api/permanent-deletion/project/${sample.id}`, route => {
    if (route.request().method() === "POST") {
      writes.push(route.request().postDataJSON());
      return route.fulfill({ json: { id: fingerprint, status: "DELETING" } });
    }
    return route.fulfill({ json: {
      name: sample.name, fingerprint, counts: { datasets: 2, run_exports: 1, files: 9 },
      missing_files: 0,
    } });
  });
  await page.route(`**/api/permanent-deletion-receipts/${fingerprint}`, route =>
    route.fulfill({ json: { id: fingerprint, status: finish ? "DELETED" : "DELETING" } }));
  await page.goto("/#page=settings");
  await page.getByRole("button", { name: "Quản lý dự án", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Quản lý dự án" });
  await dialog.getByRole("button", { name: `Quản lý ${sample.name}`, exact: true }).click();
  await dialog.getByRole("button", { name: "Xóa vĩnh viễn", exact: true }).click();
  const confirm = dialog.getByRole("button", { name: "Xác nhận xóa vĩnh viễn" });
  await expect(confirm).toBeDisabled();
  await expect(dialog.getByText("Tệp sẽ xóa", { exact: true })).toBeVisible();
  await expect(dialog.getByLabel("Nhập đúng tên dự án")).toBeFocused();
  await dialog.getByLabel("Nhập đúng tên dự án").fill(sample.name);
  await confirm.click();
  await expect(dialog.getByText(/Đang xóa dự án/)).toBeVisible();
  await expect(dialog.getByText("Đã xóa vĩnh viễn.", { exact: true })).toHaveCount(0);
  finish = true;
  await expect(dialog.getByText("Đã xóa vĩnh viễn.", { exact: true })).toBeVisible();
  expect(writes).toEqual([{ confirmation: sample.name, fingerprint }]);
});

test("mapping form never exposes a previous sheet while the next profile is delayed",async({page})=>{
  await fixture(page,projects(1),'project-000');
  let release:()=>void=()=>{};
  const gate=new Promise<void>(resolve=>release=resolve);
  const columns=[{column_id:'c1',name:'Mã giao dịch',null_count:0,empty_count:0,distinct_count:1,duplicate_count:0,samples:['000701'],type_candidates:['string'],identifier_candidate:true,evidence_ids:[]}];
  const mapping=(id:string)=>({id:`mapping-${id}`,revision:1,status:'UNKNOWN',decision:null,proposal:{decisions:[],unresolved_questions:[],grain:'unknown',entity_kind:'unknown',status:'UNKNOWN'},schema:{id:`schema-${id}`,name:'Synthetic',revision:1,entity_kind:'unknown',grain:'unknown',fields:[],business_key_fields:[]}});
  const source={id:'mapping-source',project_id:'project-000',name:'Synthetic two sheets.xlsx',status:'NEEDS_MAPPING_REVIEW',created_at:'2026-11-03'};
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/datasets')return route.fulfill({json:{items:[source],total:1}});
    if(path==='/api/datasets/mapping-source')return route.fulfill({json:source});
    if(path.endsWith('/tables'))return route.fulfill({json:{items:['sheet-a','sheet-b'].map(id=>({id,sheet:id,row_count:1,active_mapping_id:null,parsed:{columns:[{id:'c1',name:'Mã giao dịch',source_index:0}],warnings:[],header_row:1}}))}});
    if(path.endsWith('/profile')){if(path.includes('sheet-b'))await gate;return route.fulfill({json:{columns,row_count:1,key_candidates:[]}});}
    if(path.endsWith('/mappings')){if(path.includes('sheet-b'))await gate;return route.fulfill({json:{items:[mapping(path.split('/')[3])]}});}
    if(path.endsWith('/artifacts'))return route.fulfill({json:{canonical_datasets:[]}});
    if(path.endsWith('/preview'))return route.fulfill({json:{items:[{c1:'000701'}],columns:['c1'],total:1}});
    return route.fallback();
  });
  await page.goto('/#page=data');await page.getByRole('button').filter({hasText:source.name}).click();
  await page.getByRole('button',{name:'Xác nhận cột',exact:true}).click();
  const entity=page.getByLabel('Loại dữ liệu',{exact:true});await entity.fill('Ý nghĩa của nguồn A');
  await page.getByRole('combobox',{name:'Bảng dữ liệu',exact:true}).selectOption('sheet-b');
  await expect(entity).toHaveCount(0);
  release();await expect(entity).toBeVisible();await expect(entity).toHaveValue('');
  await entity.fill('Ý nghĩa của nguồn B');
  await page.getByRole('combobox',{name:'Bảng dữ liệu',exact:true}).selectOption('sheet-b');
  await expect(entity).toHaveValue('Ý nghĩa của nguồn B');
});

test("[MOCK CONTRACT] mapping jobs publish revisions, keep edited drafts and expire success only", async ({ page }) => {
  await fixture(page, projects(1), "project-000");
  await page.setViewportSize({ width: 390, height: 844 });
  const source = { id: "smart-source", project_id: "project-000", name: "Nguồn tổng hợp.csv", status: "NEEDS_MAPPING_REVIEW", created_at: "2026-11-10" };
  const columns = ["Mã nghiệp vụ", "Ghi chú"].map((name, index) => ({
    name, column_id: `c${index + 1}`, samples: ["0007"], row_count: 1, null_count: 0,
    empty_count: 0, distinct_count: 1, duplicate_count: 0, type_candidates: ["string"],
    identifier_candidate: index === 0, evidence_ids: [],
  }));
  const mapping = (revision: number) => ({
    id: `revision-${revision}`, revision, status: revision === 1 ? "UNKNOWN" : "PROPOSED",
    proposal_source: revision === 1 ? null : "GEMINI", decision: null,
    proposal: {
      status: "PROPOSED", entity_kind: revision === 1 ? "unknown" : "Giao dịch", grain: "unknown",
      unresolved_questions: [], decisions: revision === 1 ? [] : [{
        source_field: "c1", candidate_target: "reference_id", decision: "PROPOSED",
        transformation_candidate: { op: "cast_string_preserve" }, unresolved_questions: [],
      }],
    },
    schema: { id: "smart-schema", entity_kind: "unknown", grain: "unknown", business_key_fields: [],
      fields: [
        { id: "reference_id", name: "Mã tham chiếu", data_type: "string" },
        { id: "description", name: "Mô tả", data_type: "string" },
      ] },
  });
  let revision = 1;
  let submissions = 0;
  let status = "RUNNING";
  const job = () => ({
    id: `proposal-${submissions}`, status, kind: "mapping", attempts: 1,
    error_code: status === "BLOCKED" ? "AI_CANNOT_APPROVE" : null,
    result: status === "SUCCEEDED" ? { mapping_id: `revision-${revision}`, source: "GEMINI" } : null,
  });
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/datasets") return route.fulfill({ json: { items: [source], total: 1 } });
    if (path === "/api/datasets/smart-source") return route.fulfill({ json: source });
    if (path.endsWith("/tables")) return route.fulfill({ json: { items: [{
      id: "smart-table", sheet: "CSV", row_count: 1, active_mapping_id: null,
      parsed: { columns: [], warnings: [], header_row: 1 },
    }] } });
    if (path.endsWith("/profile")) return route.fulfill({ json: { columns, row_count: 1, key_candidates: [] } });
    if (path.endsWith("/mappings")) return route.fulfill({ json: {
      items: Array.from({ length: revision }, (_, index) => mapping(revision - index)),
      job: submissions ? job() : null,
    } });
    if (path.endsWith("/mapping-proposals")) {
      submissions++;
      status = "RUNNING";
      return route.fulfill({ status: 202, json: { job_id: job().id, status } });
    }
    if (path.startsWith("/api/jobs/proposal-")) return route.fulfill({ json: job() });
    if (path.endsWith("/artifacts")) return route.fulfill({ json: { canonical_datasets: [] } });
    if (path.endsWith("/preview")) return route.fulfill({ json: { items: [], total: 0, columns: [] } });
    return route.fallback();
  });
  await page.goto("/#page=data&project=project-000&dataset_id=smart-source");
  await page.getByRole("button", { name: "Xác nhận cột", exact: true }).click();
  const button = page.getByRole("button", { name: "Đề xuất lại" });
  const picker = page.getByRole("combobox", { name: "Phiên bản ánh xạ", exact: true });
  await button.click();
  await expect(page.getByText("Đang phân tích dữ liệu…")).toBeVisible();
  await expect(button).toBeDisabled();
  await expect(picker).toHaveValue("revision-1");
  await expect(page.getByText("Đã có đề xuất mới.", { exact: true })).toHaveCount(0);
  revision = 2;
  status = "SUCCEEDED";
  await expect(picker).toHaveValue("revision-2");
  const success = page.getByText("Đã có đề xuất mới.", { exact: true });
  await expect(success).toBeVisible();
  const visibleAt = Date.now();
  await expect(success).toHaveCount(0, { timeout: 6500 });
  expect(Date.now() - visibleAt).toBeGreaterThan(4400);

  await page.setViewportSize({ width: 1440, height: 900 });
  const register = page.getByRole("group", { name: "Các cột trong bảng" });
  const heading = register.locator(".mapping-register-heading");
  const summaries = register.locator("details > summary").filter({ has: page.locator(".mapping-register-status") });
  await expect(summaries.nth(1).locator(".mapping-register-status")).toHaveText("—");
  const tracks = await heading.locator("span").evaluateAll(cells =>
    cells.map(cell => cell.getBoundingClientRect().x));
  const align = () => summaries.evaluateAll(rows => rows.map(row =>
    [...row.children].map(cell => cell.getBoundingClientRect().x)));
  expect(await align()).toEqual([tracks, tracks]);
  await page.getByLabel("Chỉnh cột Mã nghiệp vụ", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Trường đích Mã nghiệp vụ", exact: true })).toBeVisible();
  expect(await align()).toEqual([tracks, tracks]);
  await page.getByLabel("Chỉnh cột Mã nghiệp vụ", { exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });

  await page.getByLabel("Chỉnh cột Ghi chú", { exact: true }).click();
  const target = page.getByRole("button", { name: "Trường đích Ghi chú", exact: true });
  await target.click();
  const dialog = page.getByRole("group", { name: "Chọn trường cho Ghi chú", exact: true });
  const search = dialog.getByRole("combobox");
  const dialogBounds = (await dialog.boundingBox())!;
  const anchorBounds = (await target.boundingBox())!;
  expect(dialogBounds.x).toBeGreaterThanOrEqual(0);
  expect(dialogBounds.x + dialogBounds.width).toBeLessThanOrEqual(390);
  expect(dialogBounds.y - anchorBounds.y - anchorBounds.height).toBeCloseTo(4, 0);
  await search.fill("ma tham chieu");
  await expect(dialog.getByRole("option")).toHaveAttribute("aria-disabled", "true");
  await expect(dialog.getByText("Đã gán cho cột Mã nghiệp vụ")).toBeVisible();
  await dialog.getByText("Thêm trường tùy chỉnh", { exact: true }).click();
  await expect(dialog.getByRole("button", { name: /^Thêm trường/ })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(target).toBeFocused();
  await expect(target).toContainText("Giữ nguyên trong nguồn gốc");
  await target.press("ArrowDown");
  await expect(search).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByText("Thêm trường tùy chỉnh", { exact: true })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog).not.toBeVisible();
  await target.click();
  await expect(search).toBeFocused();
  await target.click();
  await expect(dialog).not.toBeVisible();
  await target.press("ArrowDown");
  await search.press("Shift+Tab");
  await expect(dialog).not.toBeVisible();
  await expect(target).toBeFocused();
  await target.click();
  await page.getByText("Ý nghĩa của bảng", { exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await target.click();
  await search.fill("mo ta");
  await search.press("Enter");
  await expect(target).toBeFocused();
  await expect(target).toContainText("Mô tả");
  const type = page.getByRole("combobox", { name: "Kiểu Ghi chú", exact: true });
  await type.click();
  await expect.poll(() => type.evaluate(element => element.matches(":open"))).toBe(true);
  const nativePicker = await type.evaluate(element => {
    const select = element as HTMLSelectElement;
    return {
      top: select.options[0].getBoundingClientRect().top,
      triggerBottom: select.getBoundingClientRect().bottom,
      background: getComputedStyle(select, "::picker(select)").backgroundColor,
    };
  });
  expect(nativePicker.top).toBeGreaterThan(nativePicker.triggerBottom);
  expect(nativePicker.background).toBe("rgb(255, 255, 255)");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(type).toHaveValue("decimal");
  await expect(type).toBeFocused();
  await type.selectOption("string");
  const bounds = await target.boundingBox();
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);

  await button.click();
  await expect(button).toBeDisabled();
  revision = 3;
  status = "SUCCEEDED";
  await expect(page.getByRole("button", { name: "Mở đề xuất mới" })).toBeVisible();
  await expect(picker).toHaveValue("revision-2");
  await expect(target).toContainText("Mô tả");
  await page.reload();
  await expect(picker).toHaveValue("revision-2");
  await page.getByRole("button", { name: "Mở đề xuất mới" }).click();
  await expect(picker).toHaveValue("revision-3");
  await picker.selectOption("revision-2");
  await page.getByLabel("Chỉnh cột Ghi chú", { exact: true }).click();
  await expect(target).toContainText("Mô tả");
  await button.click();
  await expect(button).toBeDisabled();
  status = "BLOCKED";
  const alert = page.getByRole("alert").filter({ hasText: "Không thể tạo đề xuất" });
  await expect(alert).toContainText("AI trả về trạng thái không hợp lệ");
  await expect(alert).not.toContainText("AI_CANNOT_APPROVE");
  await expect(picker).toHaveValue("revision-2");
  await page.waitForTimeout(5100);
  await expect(alert).toBeVisible();
  expect(submissions).toBe(3);
});

/** Browser-only API contract fixtures never create production projects or jobs. */
async function fixture(page: Page, items: Project[], saved?: string) {
  await page.addInitScript((id) => {
    localStorage.clear();
    if (id) localStorage.setItem("studio.project", id);
  }, saved);
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (route.request().method() !== "GET")
      throw new Error(`Unexpected mutation: ${path}`);
    if (path === "/api/session")
      return route.fulfill({
        json: { workspace_id: "synthetic", role: "owner" },
      });
    if (path === "/api/settings")
      return route.fulfill({
        json: {
          workspace_name: "Synthetic",
          mapping_ai_provider: "GEMINI",
          policy: { allow_external_ai: false },
          max_upload_bytes: 20971520,
          max_upload_files: 10,
          max_rows: 100000,
        },
      });
    if (path === "/api/projects") {
      const search = (url.searchParams.get("search") || "").toLocaleLowerCase(
        "vi",
      );
      const matches = items.filter(
        (p) =>
          (url.searchParams.get("include_test") !== "false" ||
            p.classification !== "TEST") &&
          `${p.name} ${p.business_scope}`
            .toLocaleLowerCase("vi")
            .includes(search),
      );
      const offset = Number(url.searchParams.get("offset") || 0);
      const limit = Number(url.searchParams.get("limit") || 50);
      return route.fulfill({
        json: {
          items: matches.slice(offset, offset + limit),
          total: matches.length,
        },
      });
    }
    if (/^\/api\/projects\/[^/]+$/.test(path)) {
      const project = items.find((p) => p.id === path.split("/").at(-1));
      return route.fulfill(
        project
          ? { json: project }
          : { status: 404, json: { code: "RESOURCE_NOT_FOUND" } },
      );
    }
    if (path.endsWith("/summary"))
      return route.fulfill({
        json: {
          dataset_count: 0,
          table_count: 0,
          mapping_review_count: 0,
          ready_canonical_count: 0,
          active_job_count: 0,
        },
      });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
}

test("[MOCK CONTRACT] explicit project denial clears visible data and allows recovery", async ({ page }) => {
  await fixture(page, projects(1), "project-000");
  let denied = false;
  const source = { id: "private-source", project_id: "project-000", name: "Dữ liệu từng được cấp quyền.csv", status: "PARSED", created_at: "2026-10-01" };
  await page.route("**/api/datasets?**", route => route.fulfill({ json: { items: [source], total: 1 } }));
  await page.route("**/api/projects/project-000/summary", route => {
    if (!denied) return route.fallback();
    return route.fulfill({ status: 403, json: { code: "FORBIDDEN", message_vi: "Quyền đã thu hồi." } });
  });
  await page.goto("/#page=data&project=project-000");
  const sourceRow = page.getByRole("button", { name: source.name, exact: true });
  await expect(sourceRow).toBeVisible();
  denied = true;
  await page.getByRole("button", { name: "Cập nhật dự án", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Bạn không còn quyền xem dự án này");
  await expect(sourceRow).toHaveCount(0);
  denied = false;
  await page.getByRole("button", { name: "Thử tải lại dự án", exact: true }).click();
  await expect(sourceRow).toBeVisible();
});

for (const count of [5, 30, 80]) {
  test(`recent datasets stay newest after list pagination: ${count} sources`, async ({
    page,
  }) => {
    await fixture(page, projects(1));
    const sources = Array.from({ length: count }, (_, i) => ({
      id: `recent-${i}`,
      project_id: "project-000",
      workspace_id: "synthetic",
      name: `Latest-${String(i).padStart(3, "0")}.csv`,
      status: "PARSED",
      created_at: "2026-10-01T00:00:00Z",
    }));
    let recentRequests = 0;
    await page.route("**/api/datasets?**", (route) => {
      const url = new URL(route.request().url());
      const offset = Number(url.searchParams.get("offset") || 0);
      const limit = Number(url.searchParams.get("limit") || 25);
      if (limit === 5) {
        expect(offset).toBe(0);
        recentRequests += 1;
      }
      return route.fulfill({
        json: { items: sources.slice(offset, offset + limit), total: count },
      });
    });
    await page.route("**/api/projects/project-000/summary", (route) =>
      route.fulfill({
        json: {
          dataset_count: count,
          table_count: count,
          mapping_review_count: count,
          ready_canonical_count: 0,
          active_job_count: 0,
        },
      }),
    );
    await page.goto("/#page=home");
    const recent = page.locator("section").filter({
      has: page.getByRole("heading", {
        name: "Dữ liệu gần đây",
        exact: true,
      }),
    });
    await expect(
      recent.getByText("Latest-000.csv", { exact: true }),
    ).toBeVisible();
    await openLegacyPage(page, "data");
    if (count > 25) {
      await page
        .getByRole("button", { name: "Trang nguồn sau", exact: true })
        .click();
      await expect(
        page.getByText("Latest-025.csv", { exact: true }),
      ).toBeVisible();
    }
    await openLegacyPage(page, "home");
    await expect(
      recent.getByText("Latest-000.csv", { exact: true }),
    ).toBeVisible();
    await expect(
      recent.getByText("Latest-025.csv", { exact: true }),
    ).toHaveCount(0);
    await expect(recent.locator(".dataset-item")).toHaveCount(5);
    expect(recentRequests).toBe(2);
    sources.unshift({
      ...sources[0],
      id: "uploaded",
      name: "Uploaded-now.csv",
    });
    await page
      .getByRole("button", { name: "Cập nhật dự án", exact: true })
      .click();
    await expect(
      recent.getByText("Uploaded-now.csv", { exact: true }),
    ).toBeVisible();
    expect(recentRequests).toBe(3);
  });
}

test("test visibility and owner classification preserve the current project and rule draft", async ({
  page,
}) => {
  const items = projects(3);
  items[0].classification = "WORK";
  items[1].classification = "UNKNOWN";
  items[2].classification = "TEST";
  await fixture(page, items, items[2].id);
  await page.route("**/api/projects/*/canonical-catalogue", (route) =>
    route.fulfill({
      json: {
        items: ["left", "right"].map((id) => ({
          project_id: items[2].id,
          name: `Synthetic ${id}`,
          canonical: {
            id,
            stale: false,
            quality_status: "READY",
            row_count: 1,
          },
          schema_definition: {
            id: `schema-${id}`,
            grain: "one record",
            fields: [],
            business_key_fields: [],
          },
        })),
      },
    }),
  );
  let fail = false;
  const changes: unknown[] = [];
  await page.route("**/api/projects/*/classification", async (route) => {
    expect(route.request().method()).toBe("PATCH");
    const body = route.request().postDataJSON();
    changes.push(body);
    if (fail)
      return route.fulfill({
        status: 503,
        json: {
          code: "TEMPORARY",
          message_vi: "Chưa lưu phân loại; thử lại sau.",
        },
      });
    expect(body.expected_classification).toBe(items[2].classification);
    items[2].classification = body.classification;
    return route.fulfill({ json: items[2] });
  });
  await page.goto("/#page=home");
  const trigger = page.locator("#project-select");
  await expect(trigger).toHaveAttribute("data-project-id", items[2].id);
  await expect(
    page.locator("#project-select .project-test-badge"),
  ).toHaveText("Thử nghiệm");
  await openLegacyPage(page, "reconcile");
  await page
    .getByLabel("Nguồn tham chiếu", { exact: true })
    .selectOption("left");
  const period = page.getByLabel("Từ ngày", { exact: true });
  await period.fill("2026-10-01");
  await trigger.click();
  await expect(
    page
      .getByRole("listbox", { name: "Danh sách dự án", exact: true })
      .getByRole("option"),
  ).toHaveCount(2);
  const toggle = page.getByRole("checkbox", {
    name: "Hiển thị dự án kiểm thử",
    exact: true,
  });
  await toggle.check();
  await expect(
    page
      .getByRole("listbox", { name: "Danh sách dự án", exact: true })
      .getByRole("option"),
  ).toHaveCount(3);
  await expect(
    page
      .getByRole("option")
      .filter({ hasText: "Mã project-" })
      .filter({ hasText: "Kiểm thử" }),
  ).toHaveCount(1);
  await toggle.uncheck();
  await expect(
    page
      .getByRole("listbox", { name: "Danh sách dự án", exact: true })
      .getByRole("option"),
  ).toHaveCount(2);
  await page.getByText("Phân loại dự án hiện tại", { exact: true }).click();
  await expect(
    page.getByText(`Mã dự án: ${items[2].id}`, { exact: true }),
  ).toBeVisible();
  const category = page.getByLabel("Nhóm dự án", { exact: true });
  await category.selectOption("WORK");
  await page
    .getByRole("button", { name: "Xác nhận phân loại", exact: true })
    .click();
  await expect(
    page.getByText(
      "Đã lưu phân loại. Dữ liệu và lịch sử vẫn được giữ nguyên.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page
      .getByRole("listbox", { name: "Danh sách dự án", exact: true })
      .getByRole("option"),
  ).toHaveCount(3);
  await category.selectOption("TEST");
  await page
    .getByRole("button", { name: "Xác nhận phân loại", exact: true })
    .click();
  await expect(
    page
      .getByRole("listbox", { name: "Danh sách dự án", exact: true })
      .getByRole("option"),
  ).toHaveCount(2);
  fail = true;
  await category.selectOption("UNKNOWN");
  await page
    .getByRole("button", { name: "Xác nhận phân loại", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Chưa lưu phân loại" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(trigger).toHaveAttribute("data-project-id", items[2].id);
  await expect(period).toHaveValue("2026-10-01");
  expect(changes).toHaveLength(3);
  await page.reload();
  await expect(trigger).toHaveAttribute("data-project-id", items[2].id);
  await expect(
    page.locator("#project-select .project-test-badge"),
  ).toBeVisible();
});

test("confirmed classification remains in app metadata when the picker unmounts during save", async ({
  page,
}) => {
  const items = projects(1);
  items[0].classification = "TEST";
  await fixture(page, items, items[0].id);
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  let started: () => void = () => {};
  const requestStarted = new Promise<void>((resolve) => {
    started = resolve;
  });
  await page.route("**/api/projects/*/classification", async (route) => {
    started();
    await pending;
    items[0].classification = "WORK";
    return route.fulfill({ json: items[0] });
  });
  await page.goto("/#page=home");
  await page.locator("#project-select").click();
  await page.getByText("Phân loại dự án hiện tại", { exact: true }).click();
  await page.getByLabel("Nhóm dự án", { exact: true }).selectOption("WORK");
  await page
    .getByRole("button", { name: "Xác nhận phân loại", exact: true })
    .click();
  await requestStarted;
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Cài đặt", exact: true }).click();
  release();
  await openLegacyPage(page, "home");
  await expect(page.locator("#project-select .project-test-badge")).toHaveCount(
    0,
  );
  await expect(page.locator("#project-select")).toHaveAttribute(
    "data-project-id",
    items[0].id,
  );
  await page.locator("#project-select").click();
  await page.getByText("Phân loại dự án hiện tại", { exact: true }).click();
  await expect(page.getByLabel("Nhóm dự án", { exact: true })).toHaveValue(
    "WORK",
  );
});

test("viewer can reveal test projects but cannot classify; user creation explicitly uses WORK", async ({
  page,
}) => {
  const items = projects(2);
  items[0].classification = "TEST";
  await fixture(page, items, items[0].id);
  await page.route("**/api/session", (route) =>
    route.fulfill({ json: { workspace_id: "synthetic", role: "viewer" } }),
  );
  await page.goto("/#page=home");
  await page.locator("#project-select").click();
  await page
    .getByRole("checkbox", { name: "Hiển thị dự án kiểm thử", exact: true })
    .check();
  await expect(
    page
      .getByRole("listbox", { name: "Danh sách dự án", exact: true })
      .getByRole("option"),
  ).toHaveCount(2);
  await expect(
    page.getByText("Phân loại dự án hiện tại", { exact: true }),
  ).toHaveCount(0);
  await page.keyboard.press("Escape");
  await page.route("**/api/session", (route) =>
    route.fulfill({ json: { workspace_id: "synthetic", role: "editor" } }),
  );
  await page.reload();
  await page.locator("#project-select").click();
  await page.getByRole("button", { name: "Tạo dự án mới", exact: true }).click();
  await page.route("**/api/projects", (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = route.request().postDataJSON();
    expect(body).toEqual({
      name: "Dự án mới",
      business_scope: "Phạm vi mới",
      classification: "WORK",
    });
    const created = { ...items[1], ...body, id: "created-work" };
    items.push(created);
    return route.fulfill({ status: 201, json: created });
  });
  const modal = page.getByRole("dialog");
  await modal.getByLabel("Tên dự án", { exact: true }).fill("Dự án mới");
  await modal
    .getByLabel("Phạm vi nghiệp vụ", { exact: true })
    .fill("Phạm vi mới");
  await modal.getByRole("button", { name: "Tạo dự án", exact: true }).click();
  await expect(page.locator("#project-select")).toHaveAttribute(
    "data-project-id",
    "created-work",
  );
});

test("recent data reports loading/error/empty and discards delayed results after switching project", async ({
  page,
}) => {
  const items = projects(2);
  await fixture(page, items);
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  let delay = true;
  let failed = false;
  await page.route("**/api/datasets?**", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("limit") !== "5")
      return route.fulfill({ json: { items: [], total: 0 } });
    if (url.searchParams.get("project_id") === items[0].id) {
      await pending;
      return route.fulfill({
        json: {
          items: [
            {
              id: "old-source",
              name: "Old-project.csv",
              status: "PARSED",
              created_at: "2026-10-01T00:00:00Z",
            },
          ],
          total: 1,
        },
      });
    }
    if (delay) {
      await pending;
      delay = false;
    }
    if (!failed) {
      failed = true;
      return route.fulfill({
        status: 503,
        json: {
          code: "RECENT_UNAVAILABLE",
          message_vi: "Tạm thời không đọc được danh sách.",
        },
      });
    }
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.goto("/#page=home");
  const recent = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Dữ liệu gần đây", exact: true }),
  });
  await expect(recent.getByRole("status")).toContainText("Đang tải");
  await page.locator("#project-select").click();
  await page
    .getByRole("listbox", { name: "Danh sách dự án", exact: true })
    .getByRole("option")
    .nth(1)
    .click();
  await expect(recent.getByRole("status")).toContainText("Đang tải");
  release();
  await expect(recent.getByRole("alert")).toContainText(
    "Không tải được dữ liệu gần đây",
  );
  await expect(
    recent.getByText("Old-project.csv", { exact: true }),
  ).toHaveCount(0);
  await expect(
    recent.getByRole("heading", { name: "Chưa có nguồn dữ liệu", exact: true }),
  ).toHaveCount(0);
  await recent
    .getByRole("button", { name: "Tải lại dữ liệu gần đây", exact: true })
    .click();
  await expect(
    recent.getByRole("heading", { name: "Chưa có nguồn dữ liệu", exact: true }),
  ).toBeVisible();
  await expect(page.locator("#project-select")).toHaveAttribute(
    "data-project-id",
    items[1].id,
  );
});

for (const count of [1, 10, 50, 120]) {
  test(`project picker: ${count} projects, bounded pagination and keyboard selection`, async ({
    page,
  }) => {
    const items = projects(count);
    await fixture(page, items);
    await page.goto("/#page=home");
    const trigger = page.locator("#project-select");
    await trigger.click();
    const search = page.getByRole("combobox", {
      name: "Tìm dự án",
      exact: true,
    });
    await expect(search).toBeFocused();
    await expect(
      page
        .getByRole("listbox", { name: "Danh sách dự án", exact: true })
        .getByRole("option"),
    ).toHaveCount(Math.min(20, count));
    if (count > 20) {
      await page
        .getByRole("button", { name: "Trang dự án sau", exact: true })
        .click();
      await expect(
        page
          .getByRole("listbox", { name: "Danh sách dự án", exact: true })
          .getByRole("option")
          .first(),
      ).toContainText("miền Nam 020");
    }
    await search.fill(items.at(-1)!.business_scope.toLocaleUpperCase("vi"));
    await expect(
      page
        .getByRole("listbox", { name: "Danh sách dự án", exact: true })
        .getByRole("option"),
    ).toHaveCount(1);
    await search.press("ArrowDown");
    await search.press("Enter");
    await expect(trigger).toHaveAttribute("data-project-id", items.at(-1)!.id);
    await expect(trigger).toBeFocused();
    await trigger.click();
    await search.fill("không tồn tại");
    await expect(
      page.getByText("Không có dự án phù hợp.", { exact: false }),
    ).toBeVisible();
    await search.press("Escape");
    await expect(trigger).toBeFocused();
  });
}

test("restore saved off-page project; unavailable saved ID never silently selects another", async ({
  page,
}) => {
  const items = projects(120);
  await fixture(page, items, items[119].id);
  await page.goto("/#page=home");
  await expect(page.locator("#project-select")).toHaveAttribute(
    "data-project-id",
    items[119].id,
  );
  await page.reload();
  await expect(page.locator("#project-select")).toHaveAttribute(
    "data-project-id",
    items[119].id,
  );
  items.pop();
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("không còn tồn tại");
  await expect(page.locator("#project-select")).toHaveAttribute(
    "data-project-id",
    "",
  );
});

test("project search discards delayed results and exposes loading and retry errors", async ({
  page,
}) => {
  await fixture(page, projects(120));
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/projects?**", async (route) => {
    const search = new URL(route.request().url()).searchParams.get("search");
    if (search === "old") {
      await delayed;
      return route.fulfill({
        json: {
          items: [{ ...projects(1)[0], name: "Old response" }],
          total: 1,
        },
      });
    }
    if (search === "error")
      return route.fulfill({
        status: 503,
        json: { message_vi: "Không tải được dự án tổng hợp" },
      });
    return route.fallback();
  });
  await page.goto("/#page=home");
  await page.locator("#project-select").click();
  const search = page.getByRole("combobox", { name: "Tìm dự án", exact: true });
  const oldRequest = page.waitForRequest(
    (r) => new URL(r.url()).searchParams.get("search") === "old",
  );
  await search.fill("old");
  await expect(page.getByRole("listbox")).toHaveAttribute("aria-busy", "true");
  await oldRequest;
  await search.fill("miền Nam 119");
  await expect(
    page
      .getByRole("listbox", { name: "Danh sách dự án", exact: true })
      .getByRole("option"),
  ).toContainText("119");
  release();
  await expect(page.getByText("Old response")).toHaveCount(0);
  await search.fill("error");
  await expect(page.getByRole("alert")).toContainText("Không tải được");
  await expect(
    page.getByRole("button", { name: "Thử lại", exact: true }),
  ).toBeVisible();
});

const emptySummary = {
  dataset_count: 0,
  table_count: 0,
  mapping_review_count: 0,
  ready_canonical_count: 0,
  partial_canonical_count: 0,
  stale_canonical_count: 0,
  failed_canonical_count: 0,
  active_job_count: 0,
  latest_verified_run_id: null,
};

test("project polling runs only while jobs are active and manual refresh remains available", async ({
  page,
}) => {
  await fixture(page, projects(1));
  let requests = 0;
  let active = false;
  await page.route("**/api/projects/*/summary", (route) => {
    requests += 1;
    return route.fulfill({
      json: {
        ...emptySummary,
        dataset_count: 1,
        active_job_count: active ? 1 : 0,
        preparation_action: { kind: active ? "WAIT" : "UPLOAD" },
      },
    });
  });
  await page.clock.install();
  await page.goto("/#page=home");
  await expect(
    page.getByRole("button", { name: "Cập nhật dự án", exact: true }),
  ).toBeEnabled();
  const idle = requests;
  await page.clock.fastForward(15000);
  expect(requests).toBe(idle);
  active = true;
  await page
    .getByRole("button", { name: "Cập nhật dự án", exact: true })
    .click();
  await expect(
    page
      .locator(".stat-card")
      .filter({ hasText: "Tác vụ đang xử lý" })
      .locator("strong"),
  ).toHaveText("1");
  const beforePoll = requests;
  active = false;
  await page.clock.fastForward(3100);
  await expect.poll(() => requests).toBe(beforePoll + 1);
  await expect(
    page
      .locator(".stat-card")
      .filter({ hasText: "Tác vụ đang xử lý" })
      .locator("strong"),
  ).toHaveText("0");
  const completed = requests;
  await page.clock.fastForward(20000);
  expect(requests).toBe(completed);
});

test("summary API error is visible with retry, not empty data or zero statistics", async ({
  page,
}) => {
  await fixture(page, projects(1));
  let fail = true;
  await page.route("**/api/projects/*/summary", (route) =>
    fail
      ? route.fulfill({
          status: 503,
          json: { message_vi: "Dịch vụ tổng hợp tạm thời lỗi" },
        })
      : route.fulfill({ json: emptySummary }),
  );
  await page.goto("/#page=home");
  await expect(page.getByRole("alert")).toContainText(
    "Dịch vụ tổng hợp tạm thời lỗi",
  );
  await expect(page.locator(".stat-card")).toHaveCount(0);
  await expect(
    page.getByText("Chưa có nguồn dữ liệu", { exact: true }),
  ).toHaveCount(0);
  fail = false;
  await page
    .getByRole("button", { name: "Thử tải lại dự án", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Chưa có nguồn dữ liệu", exact: true }),
  ).toBeVisible();
});

test("viewer role is truthful and write actions are disabled while navigation remains available", async ({
  page,
}) => {
  await fixture(page, projects(1));
  await page.route("**/api/session", (route) =>
    route.fulfill({ json: { role: "viewer", workspace_id: "synthetic" } }),
  );
  await page.route("**/api/projects/*/canonical-catalogue", (route) =>
    route.fulfill({
      json: {
        items: ["left", "right"].map((id) => ({
          project_id: "project-000",
          name: `Synthetic ${id}`,
          canonical: {
            id,
            stale: false,
            quality_status: "READY",
            row_count: 1,
          },
          schema_definition: {
            id: `schema-${id}`,
            grain: "one synthetic record",
            fields: [],
            business_key_fields: [],
          },
        })),
      },
    }),
  );
  await page.goto("/#page=home");
  await expect(page.getByText("Chỉ xem", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Tải dữ liệu", exact: true }),
  ).toBeDisabled();
  await page.locator("#project-select").click();
  await expect(page.getByRole("button", { name: "Tạo dự án mới", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Quản lý dự án", exact: true })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await openLegacyPage(page, "reconcile");
  await expect(
    page.getByLabel("Nguồn tham chiếu", { exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByLabel("Nguồn đối ứng", { exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("status").filter({ hasText: "Bạn có quyền xem dữ liệu" }),
  ).toBeVisible();
  await expect(page.locator("#project-select")).toBeEnabled();
});

for (const width of [390, 768, 1366, 1440, 1920]) {
  test(`project dialog responsive and keyboard focus at ${width}`, async ({
    page,
  }) => {
    await fixture(page, projects(120));
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/#page=home");
    const trigger = page.locator("#project-select");
    await trigger.focus();
    await trigger.press("Enter");
    const search = page.getByRole("combobox", {
      name: "Tìm dự án",
      exact: true,
    });
    await expect(search).toBeFocused();
    await expect(
      page
        .getByRole("listbox", { name: "Danh sách dự án", exact: true })
        .getByRole("option"),
    ).toHaveCount(20);
    const dialog = page.getByRole("dialog", {
      name: "Chọn dự án",
      exact: true,
    });
    const bounds = (await dialog.boundingBox())!;
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.y).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(900);
    await expect(search).toHaveCSS("outline-style", "none");
    await expect(search).toHaveCSS("box-shadow", /0px -2px 0px 0px inset/);
    const searchBounds = await search.boundingBox();
    await search.click();
    await expect(search).toHaveCSS("box-shadow", "none");
    expect(await search.boundingBox()).toEqual(searchBounds);
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    await expect(search).toBeFocused();
    await expect(search).toHaveCSS("box-shadow", /0px -2px 0px 0px inset/);
    const contrast = await dialog.evaluate((element) => {
      const luminance = (color: string) => {
        const channels = color
          .match(/[\d.]+/g)!
          .slice(0, 3)
          .map(Number)
          .map((value) => {
            const channel = value / 255;
            return channel <= 0.04045
              ? channel / 12.92
              : ((channel + 0.055) / 1.055) ** 2.4;
          });
        return (
          channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
        );
      };
      return [
        ".project-option.highlighted strong",
        ".project-option.highlighted span",
        ".project-option.highlighted small",
        "input",
      ].map((selector) => {
        const target = element.querySelector(selector)!;
        let surface: Element | null = target;
        while (
          surface &&
          getComputedStyle(surface).backgroundColor === "rgba(0, 0, 0, 0)"
        )
          surface = surface.parentElement;
        const foreground = luminance(
          getComputedStyle(
            target,
            selector === "input" ? "::placeholder" : null,
          ).color,
        );
        const background = luminance(
          getComputedStyle(surface!).backgroundColor,
        );
        return {
          selector,
          ratio:
            (Math.max(foreground, background) + 0.05) /
            (Math.min(foreground, background) + 0.05),
        };
      });
    });
    for (const sample of contrast)
      expect(sample.ratio, sample.selector).toBeGreaterThanOrEqual(4.5);
    await mkdir("../runtime/screenshots", { recursive: true });
    await page.screenshot({
      path: `../runtime/screenshots/project-selector-${width}.png`,
      fullPage: true,
    });
    await search.press("End");
    await search.press("Enter");
    await expect(trigger).toHaveAttribute("data-project-id", "project-019");
    await expect(trigger).toBeFocused();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    if (width < 900) {
      const menu = page.getByRole("button", {
        name: "Mở điều hướng",
        exact: true,
      });
      await menu.click();
      const navigation = page.getByRole("dialog", {
        name: "Điều hướng",
        exact: true,
      });
      await expect(navigation.getByRole("button", { name: "Đóng điều hướng", exact: true })).toBeFocused();
      await page.keyboard.press("Shift+Tab");
      await expect(
        navigation.getByRole("button", { name: "Cài đặt", exact: true }),
      ).toBeFocused();
      await page.keyboard.press("Escape");
      await expect(menu).toBeFocused();
      await expect(navigation).toHaveCount(0);
    }
    const upload = page.getByRole("button", {
      name: "Tải dữ liệu",
      exact: true,
    });
    await upload.click();
    await expect(
      page.getByRole("dialog", { name: "Tải nguồn dữ liệu", exact: true }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(upload).toBeFocused();
  });
}

test("dashboard uses server totals, distinguishes PARTIAL and opens the exact off-page table errors", async ({
  page,
}) => {
  const items = projects(1);
  await fixture(page, items);
  const source = {
    id: "old-source",
    project_id: items[0].id,
    name: "synthetic-orders.csv",
    status: "PARTIAL",
    created_at: "2026-10-01",
  };
  const canonical = {
    id: "partial-canonical",
    source_table_id: "table-errors",
    mapping_revision_id: "approved",
    row_count: 4,
    valid_count: 2,
    invalid_count: 2,
    quality_status: "PARTIAL",
    stale: false,
  };
  const target = {
    kind: "REVIEW_DATA",
    dataset_id: source.id,
    table_id: canonical.source_table_id,
    canonical_id: canonical.id,
  };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/summary"))
      return route.fulfill({
        json: {
          ...emptySummary,
          dataset_count: 80,
          table_count: 81,
          partial_canonical_count: 1,
          stale_canonical_count: 2,
          preparation_action: target,
        },
      });
    if (path === "/api/datasets")
      return route.fulfill({
        json: {
          items: Array.from({ length: 25 }, (_, i) => ({
            ...source,
            id: `recent-${i}`,
            name: `Recent ${i}.csv`,
          })),
          total: 80,
        },
      });
    if (path === `/api/datasets/${source.id}`)
      return route.fulfill({ json: source });
    if (path.endsWith("/tables"))
      return route.fulfill({
        json: {
          items: [
            {
              id: "other-sheet",
              sheet: "Other",
              row_count: 4,
              parsed: { columns: [], warnings: [], header_row: 1 },
            },
            {
              id: "table-errors",
              sheet: "Errors sheet",
              row_count: 4,
              active_mapping_id: "approved",
              parsed: { columns: [], warnings: [], header_row: 1 },
            },
          ],
        },
      });
    if (path.endsWith("/artifacts"))
      return route.fulfill({ json: { canonical_datasets: [canonical] } });
    if (path.endsWith("/profile"))
      return route.fulfill({ json: { columns: [], row_count: 4 } });
    if (path.endsWith("/preview"))
      return route.fulfill({
        json: {
          view: "errors",
          columns: ["code", "raw_value"],
          total: 1,
          items: [{ code: "INVALID_DECIMAL", raw_value: "invalid" }],
        },
      });
    return route.fallback();
  });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/#page=home");
  await expect(page.locator(".stat-card").filter({hasText:"Nguồn dữ liệu"}).locator("strong")).toHaveText("80");
  const ready = page
    .locator(".stat-card")
    .filter({ hasText: "Kết quả sẵn sàng sử dụng" });
  await expect(ready.locator("strong")).toHaveText("0");
  await expect(ready).toContainText("1 cần kiểm tra · 2 đã cũ");
  await expect(
    page.locator(".stat-card").filter({ hasText: "Nguồn dữ liệu" }),
  ).toContainText("81 bảng / sheet");
  await page
    .getByRole("button", { name: "Kiểm tra lỗi dữ liệu", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: source.name })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Bảng dữ liệu", exact: true })).toHaveValue(
    "table-errors",
  );
  await expect(
    page.getByRole("combobox", { name: "Lớp dữ liệu", exact: true }),
  ).toHaveValue("errors");
  await expect(
    page.getByRole("cell", { name: "invalid", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: "Dữ liệu cần kiểm tra" }),
  ).toContainText("2 / 4");
  expect(errors).toEqual([]);
});

test("project switch discards delayed old summary/data/error", async ({
  page,
}) => {
  const items = projects(2);
  await fixture(page, items);
  let release!: () => void;
  const delay = new Promise<void>((resolve) => {
    release = resolve;
  });
  let started!: () => void;
  const loading = new Promise<void>((resolve) => {
    started = resolve;
  });
  await page.route("**/api/projects/*/summary", async (route) => {
    if (route.request().url().includes(items[0].id)) {
      started();
      await delay;
      return route.fulfill({
        status: 503,
        json: { message_vi: "Old project failure" },
      });
    }
    return route.fulfill({ json: { ...emptySummary, dataset_count: 80 } });
  });
  await page.goto("/#page=home");
  await loading;
  await expect(
    page.getByText("Đang tải dữ liệu dự án…", { exact: false }),
  ).toBeVisible();
  await expect(page.locator(".stat-card")).toHaveCount(0);
  await page.locator("#project-select").click();
  await page
    .getByRole("option")
    .filter({ hasText: items[1].business_scope })
    .click();
  await expect(page.locator(".stat-card").first().locator("strong")).toHaveText(
    "80",
  );
  release();
  await expect(page.getByText("Old project failure")).toHaveCount(0);
  await expect(page.locator("#project-select")).toHaveAttribute(
    "data-project-id",
    items[1].id,
  );
});

for (const kind of ["REVIEW_MAPPING", "NORMALIZE"] as const) {
  test(`next action ${kind} opens the matching table/tab without mutation`, async ({
    page,
  }) => {
    const items = projects(1);
    await fixture(page, items);
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/summary"))
        return route.fulfill({
          json: {
            ...emptySummary,
            dataset_count: 1,
            preparation_action: {
              kind,
              dataset_id: "source",
              table_id: "table",
              canonical_id: null,
            },
          },
        });
      const source = {
        id: "source",
        project_id: items[0].id,
        name: "Synthetic.csv",
        status: "PROFILED",
        created_at: "2026-10-01",
      };
      if (path === "/api/datasets/source")
        return route.fulfill({ json: source });
      if (path === "/api/datasets")
        return route.fulfill({ json: { items: [source], total: 1 } });
      if (path.endsWith("/tables"))
        return route.fulfill({
          json: {
            items: [
              {
                id: "table",
                sheet: "CSV",
                row_count: 1,
                parsed: { columns: [], warnings: [] },
              },
            ],
          },
        });
      if (path.endsWith("/profile"))
        return route.fulfill({ json: { columns: [], row_count: 1 } });
      if (path.endsWith("/artifacts"))
        return route.fulfill({ json: { canonical_datasets: [] } });
      return route.fallback();
    });
    await page.goto("/#page=home");
    await page
      .getByRole("button", {
        name:
          kind === "REVIEW_MAPPING" ? "Kiểm tra ánh xạ" : "Chuẩn hóa dữ liệu",
        exact: true,
      })
      .click();
    await expect(page.getByRole("combobox", { name: "Bảng dữ liệu", exact: true })).toHaveValue(
      "table",
    );
    await expect(
      page.getByRole("button", {
        name: kind === "REVIEW_MAPPING" ? "Xác nhận cột" : "Tạo bản chuẩn hóa",
        exact: true,
      }),
    ).toHaveAttribute("aria-pressed", "true");
  });
}


test("[MOCK CONTRACT] local proof recovery preserves draft and reloads project and history without mutation", async ({ page }) => {
  await fixture(page, projects(1), "project-000");
  const draftKey = 'studio.assistant-draft.synthetic.demo.["project-000","","","","","new"]';
  await page.addInitScript(({key}) => sessionStorage.setItem(key, "Bản nháp được giữ nguyên"), {key:draftKey});
  let historyReads = 0;
  await page.route("**/api/conversations?**", route => {
    historyReads++;
    return route.fulfill({json:{items:[{id:"saved-history",title:"Hội thoại trước khi khởi động lại",context:{project_id:"project-000"},created_at:"2026-11-04T00:00:00Z"}],has_more:false}});
  });
  let verified = false;
  let documents = 0;
  page.on("request", request => { if(request.isNavigationRequest() && request.frame()===page.mainFrame()) documents++; });
  await page.route("**/api/session", route => verified ? route.fallback() : route.fulfill({status:403,json:{code:"LOCAL_DEMO_NOT_VERIFIED",message_vi:"technical operator detail"}}));
  await page.goto("/");
  const status = page.getByRole("status", {name:"Trạng thái kết nối"});
  await expect(status).toHaveText("Chưa kết nối");
  await expect(page.getByText("Ứng dụng cần xác minh lại môi trường local sau khi khởi động. Dữ liệu của bạn vẫn được giữ nguyên.")).toBeVisible();
  await expect(page.getByRole("button", {name:"AI Assistant",exact:true})).toBeDisabled();
  const operatorCommand = page.locator("code", { hasText: "tools/verify-local.ps1" });
  await expect(operatorCommand).not.toBeVisible();
  await page.getByText("Hướng dẫn cho người vận hành local", {exact:true}).click();
  await expect(operatorCommand).toBeVisible();
  expect(await status.locator("span:first-child").evaluate(el=>getComputedStyle(el).backgroundColor)).not.toBe("rgb(22, 163, 74)");
  verified = true;
  await page.getByRole("button", {name:"Thử kết nối lại",exact:true}).click();
  await expect(status).toHaveText("Đã kết nối");
  await expect(page.locator("#project-select")).toHaveAttribute("data-project-id","project-000");
  await expect(page.getByRole("textbox",{name:"Câu hỏi cho AI Assistant",exact:true})).toHaveValue("Bản nháp được giữ nguyên");
  await page.getByRole("button", {name:"Lịch sử",exact:true}).click();
  await expect(page.getByRole("dialog",{name:"Lịch sử",exact:true}).getByText("Hội thoại trước khi khởi động lại",{exact:false})).toBeVisible();
  expect(historyReads).toBeGreaterThan(0);
  expect(await page.evaluate(key=>sessionStorage.getItem(key),draftKey)).toBe("Bản nháp được giữ nguyên");
  expect(documents).toBe(1);
});

for (const failure of ["network", "timeout", "settings"] as const) {
  test(`[MOCK CONTRACT] bootstrap ${failure} stops loading and recovers with a GET-only retry`, async ({ page }) => {
    await fixture(page, projects(1));
    let failed = true;
    if(failure==="timeout") await page.addInitScript(()=>{
      const original = AbortSignal.timeout.bind(AbortSignal);
      AbortSignal.timeout = ms => original(ms===30000?1000:ms);
    });
    await page.route(failure==="settings"?"**/api/settings":"**/api/session", async route=>{
      if(!failed)return route.fallback();
      if(failure==="network")return route.abort("connectionrefused");
      if(failure==="timeout") { await new Promise(resolve=>setTimeout(resolve,1600)); return route.fulfill({json:{workspace_id:"synthetic",role:"owner"}}).catch(()=>{}); }
      return route.fulfill({status:503,body:"unavailable"});
    });
    await page.goto("/");
    const status=page.getByRole("status",{name:"Trạng thái kết nối"});
    await expect(status).toHaveText("Chưa kết nối");
    await expect(page.getByText("Không thể kết nối tới dịch vụ xử lý dữ liệu. Hãy kiểm tra trạng thái ứng dụng.")).toBeVisible();
    await expect(page.getByText("Hướng dẫn cho người vận hành local",{exact:true})).toHaveCount(0);
    await expect(page.getByText("Đang xác minh quyền",{exact:false})).toHaveCount(0);
    failed=false;
    await page.getByRole("button",{name:"Thử kết nối lại",exact:true}).click();
    await expect(status).toHaveText("Đã kết nối");
    await expect(page.getByRole("textbox",{name:"Câu hỏi cho AI Assistant",exact:true})).toBeEnabled();
    await page.reload();
    await expect(status).toHaveText("Đã kết nối");
  });
}
