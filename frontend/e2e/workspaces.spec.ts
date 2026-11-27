import { expect, test, type APIRequestContext } from "@playwright/test";

import { horizontalOverflow } from "./layout";

// Kiểm phiên làm việc trên dịch vụ thật: tạo phiên mới là trang trắng, đổi qua lại giữa các
// phiên, đổi tên, xóa qua hộp xác nhận. Chỉ xóa đúng phiên do bài này tạo.

type Workspace = { id: string; name: string };

async function workspaces(request: APIRequestContext): Promise<Workspace[]> {
  return (await (await request.get("/api/workspaces")).json()) as Workspace[];
}

test("tạo phiên trống, đổi phiên, đổi tên và xóa phiên", async ({ page, request, isMobile }) => {
  const before = new Set((await workspaces(request)).map((item) => item.id));
  const name = `Phiên E2E ${isMobile ? "điện thoại" : "máy tính"} ${Date.now()}`;
  const switcher = page.locator(`.workspace-switch[data-variant="${isMobile ? "bar" : "rail"}"]`);
  try {
    await page.goto("/");
    const original = (await switcher.locator(".workspace-switch__name").textContent()) ?? "";

    // Tạo từ bộ chọn phiên: sang trang Quản lý phiên, ô tên có sẵn con trỏ.
    await switcher.getByRole("button", { name: /Đổi phiên/ }).click();
    await page.getByRole("button", { name: "Tạo phiên mới" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Phiên làm việc" })).toBeVisible();
    await expect(page.getByLabel("Tên phiên mới")).toBeFocused();
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    await page.getByLabel("Tên phiên mới").fill(name);
    await page.getByRole("button", { name: "Tạo và mở phiên" }).click();

    // Phiên mới là trang trắng: chưa có tệp, chưa có cuộc trò chuyện, nhật ký chỉ có lần tạo.
    await expect(page).toHaveURL("/");
    await expect(switcher.locator(".workspace-switch__name")).toHaveText(name);
    await expect(page.locator("#next-step-title")).toHaveText("Tải bộ dữ liệu đầu tiên");
    const nav = page.getByRole("navigation", { name: "Điều hướng chính" });
    await nav.getByRole("link", { name: "Dữ liệu" }).click();
    await expect(page.getByText(/Chưa có bộ dữ liệu nào|Chưa có tệp/)).toBeVisible();
    await nav.getByRole("link", { name: "Lịch sử" }).click();
    await expect(page.locator(".history__item")).toHaveCount(1);

    // Đổi về phiên cũ bằng bộ chọn phiên.
    await switcher.getByRole("button", { name: /Đổi phiên/ }).click();
    await page.locator(".workspace-switch__item", { hasText: original }).click();
    await expect(switcher.locator(".workspace-switch__name")).toHaveText(original);

    // Đổi tên rồi xóa phiên vừa tạo ở trang Quản lý phiên.
    await page.goto("/phien");
    await page.getByRole("button", { name: `Đổi tên phiên ${name}` }).click();
    await page.getByLabel(`Tên mới cho phiên ${name}`).fill(`${name} (đã đổi)`);
    await page.getByRole("button", { name: "Lưu" }).click();
    await page.getByRole("button", { name: `Xóa phiên ${name} (đã đổi)` }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Xóa phiên" }).click();
    await expect(page.getByRole("button", { name: `Xóa phiên ${name} (đã đổi)` })).toHaveCount(0);
    expect((await workspaces(request)).some((item) => !before.has(item.id))).toBe(false);
  } finally {
    for (const item of await workspaces(request)) {
      if (!before.has(item.id)) await request.delete(`/api/workspaces/${item.id}`);
    }
  }
});
