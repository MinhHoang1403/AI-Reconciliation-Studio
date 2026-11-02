import { expect, type Page } from "@playwright/test";

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
