import { expect, test } from "@playwright/test";

// Kiểm khung ứng dụng trên dịch vụ thật: điều hướng, trạng thái hệ thống, trang chưa có chức năng.

test("Tổng quan hiển thị bước tiếp theo, quy trình và trạng thái hệ thống", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Tổng quan" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tải bộ dữ liệu đầu tiên" })).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "Đọc tệp" })).toContainText("Đang chờ tệp");
  await expect(page.getByRole("img", { name: "Chưa kiểm chứng" })).toBeVisible();
  await expect(page.getByText("Hoạt động")).toBeVisible();
  // Gemini chỉ hiện tên model viết hoa từng phần (hoặc báo thiếu khóa), không kèm chữ "Đã cấu hình".
  const status = page.getByRole("region", { name: "Trạng thái hệ thống" });
  await expect(status).toContainText(/Gemini-3\.5-Flash-Lite|Chưa có khóa GEMINI_API_KEY/);
  await expect(status).not.toContainText("Đã cấu hình");
});

test("Điều hướng tới từng trang và giữ đúng trang khi tải lại", async ({ page }) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Điều hướng chính" });
  for (const [label, path] of [
    ["Assistant", "/assistant"],
    ["Dữ liệu", "/du-lieu"],
    ["Đối soát", "/doi-soat"],
    ["Báo cáo", "/bao-cao"],
  ] as const) {
    await nav.getByRole("link", { name: label }).click();
    await expect(page).toHaveURL(path);
    await expect(page.getByRole("heading", { level: 1, name: label })).toBeVisible();
    await expect(nav.getByRole("link", { name: label })).toHaveAttribute("aria-current", "page");
  }
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Báo cáo" })).toBeVisible();
});

test("Nút ở bước tiếp theo dẫn tới trang Dữ liệu", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Đến trang Dữ liệu" }).click();
  await expect(page).toHaveURL("/du-lieu");
});

test("Trang không bị cuộn ngang", async ({ page }) => {
  await page.goto("/");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("API trạng thái không trả khóa bí mật", async ({ request }) => {
  const reply = await request.get("/api/status");
  expect(reply.ok()).toBeTruthy();
  const body = await reply.json();
  expect(Object.keys(body.gemini)).toEqual(["name", "model", "state"]);
});
