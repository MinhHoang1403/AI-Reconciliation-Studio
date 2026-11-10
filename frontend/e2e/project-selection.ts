import { test as base, expect, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { resolve, sep } from "node:path";

// Candidate UI uses the same browser origin and existing API. This opt-in asset
// fixture validates dist before replacing the accepted Compose release.
export const test = base.extend({
  page: async ({ page }, use) => {
    if (process.env.STUDIO_FRONTEND_DIST === "1") {
      const dist = resolve("dist");
      await page.route(url => url.pathname === "/" || url.pathname.startsWith("/assets/"), async route => {
        const path = new URL(route.request().url()).pathname;
        const file = resolve(dist, path === "/" ? "index.html" : `.${path}`);
        if (!file.startsWith(dist + sep)) throw Error("Candidate asset outside dist");
        const contentType = file.endsWith(".html") ? "text/html" : file.endsWith(".css") ? "text/css" : "text/javascript";
        await route.fulfill({ body: await readFile(file), contentType });
      });
    }
    await use(page);
  },
});

export function assistantPanel(page: Page, name: string) {
  const label = { name, exact: true };
  return page.getByRole("dialog", label).or(page.getByRole("complementary", label));
}

/** Pick an existing field or explicitly extend the schema for business-specific fixtures. */
export async function chooseMappingTarget(page: Page, column: string, id: string) {
  await page.getByRole("button", { name: `Trường đích ${column}`, exact: true }).click();
  const picker = page.getByRole("dialog", { name: `Chọn trường cho ${column}`, exact: true });
  await picker.getByRole("combobox", { name: "Tìm trường đích" }).fill(id);
  const field = picker.getByRole("option").and(picker.locator(`[data-target-id="${id}"]`));
  if (await field.count()) await field.click();
  else await picker.getByRole("button", { name: `Thêm trường “${id}” vào cấu trúc`, exact: true }).click();
  await expect(picker).not.toBeVisible();
}

/** Các trang cũ là deep links dự phòng, không còn là menu chính của Assistant. */
export async function openLegacyPage(page: Page, target: "home"|"data"|"reconcile"|"reports"|"exceptions") {
  await expect(page.getByRole('button',{name:'AI Assistant',exact:true,includeHidden:true})).toBeEnabled();
  if(await page.locator('.sidebar[aria-modal="true"]').isVisible())await page.keyboard.press('Escape');
  await page.evaluate(next=>{
    const query=new URLSearchParams(window.location.hash.slice(1));
    const selected=document.querySelector('#project-select')?.getAttribute('data-project-id');
    if(selected&&selected!==query.get('project')){
      for(const key of ['run_id','dataset_id','group_id','case_id'])query.delete(key);
    }
    if(selected)query.set('project',selected);
    query.set('page',next);window.location.hash=query.toString();
  },target);
  await expect(page).toHaveURL(new RegExp(`page=${target}`));
  if(target==="reconcile")await page.getByRole("button",{name:"Thiết lập đối soát",exact:true}).click();
  const headings={home:'Dữ liệu sẵn sàng cho quyết định chính xác',data:'Không gian dữ liệu',reconcile:'Đối soát có kiểm chứng',reports:'Báo cáo đối soát',exceptions:'Ngoại lệ và bằng chứng'};
  if(target==='reports'||target==='exceptions')await expect(page.getByRole('heading',{name:headings[target],exact:true})).toBeVisible();
}

/** Exercise the real visible picker, including server search for off-page IDs. */
export async function selectProject(page: Page, id: string) {
  await expect(page.locator("#project-select")).toBeVisible();
  const response = await page.request.get(`/api/projects/${id}`);
  expect(response.ok()).toBe(true);
  const project = (await response.json()) as {
    name: string;
    business_scope: string;
    classification?: string;
  };
  await page.locator("#project-select").click();
  if (project.classification === "TEST")
    await page
      .getByRole("checkbox", { name: "Hiển thị dự án kiểm thử", exact: true })
      .check();
  await page
    .getByRole("combobox", { name: "Tìm dự án", exact: true })
    .fill(project.name);
  await page
    .getByRole("option")
    .filter({ hasText: `Mã ${id.slice(0, 8)}` })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Chọn dự án" }),
  ).not.toBeVisible();
  await expect(page.locator("#project-select")).toHaveAttribute(
    "data-project-id",
    id,
  );
}
