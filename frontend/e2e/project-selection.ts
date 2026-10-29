import { expect, type Page } from "@playwright/test";

/** Exercise the real visible picker, including server search for off-page IDs. */
export async function selectProject(page: Page, id: string) {
  await expect(page.locator("#project-select")).toBeVisible();
  const response = await page.request.get(`/api/projects/${id}`);
  expect(response.ok()).toBe(true);
  const project = await response.json() as { name: string; business_scope: string };
  await page.locator("#project-select").click();
  await page.getByRole("combobox", { name: "Tìm dự án", exact: true }).fill(project.name);
  await page.getByRole("option").filter({ hasText: `Mã ${id.slice(0, 8)}` }).click();
  await expect(page.getByRole("dialog", { name: "Chọn dự án" })).not.toBeVisible();
  await expect(page.locator("#project-select")).toHaveAttribute("data-project-id", id);
}
