import { expect, test } from "@playwright/test";

// Kiểm khung ứng dụng trên dịch vụ thật: điều hướng, trạng thái hệ thống, trang chưa có chức năng.

test("Tổng quan hiển thị bước tiếp theo, quy trình và trạng thái hệ thống", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Tổng quan" })).toBeVisible();
  // Nội dung phụ thuộc container đã có dữ liệu hay chưa, nên chấp nhận cả hai trạng thái.
  await expect(page.getByRole("heading", { name: /Tải bộ dữ liệu đầu tiên|Đã đọc \d+ bộ dữ liệu/ })).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "Đọc tệp" })).toContainText(/Đang chờ tệp|Đã đọc/);
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

test("Thu gọn và mở rộng thanh bên, nhớ trạng thái khi tải lại", async ({ page, isMobile }) => {
  test.skip(isMobile, "Trên điện thoại thanh bên là thanh tab ở đáy, không có nút thu gọn");
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Điều hướng chính" });
  const widthBefore = (await nav.boundingBox())?.width ?? 0;

  await page.getByRole("button", { name: "Thu gọn thanh bên" }).click();
  await expect(page.getByRole("button", { name: "Mở rộng thanh bên" })).toHaveAttribute("aria-expanded", "false");
  await expect(nav.getByText("Dữ liệu", { exact: true })).toBeHidden();
  // Chữ ẩn nhưng liên kết vẫn có tên để bấm và để trình đọc màn hình đọc.
  await nav.getByRole("link", { name: "Dữ liệu" }).click();
  await expect(page).toHaveURL("/du-lieu");
  await expect.poll(async () => (await nav.boundingBox())?.width ?? 0).toBeLessThan(widthBefore / 2);

  await page.reload();
  await expect(page.getByRole("button", { name: "Mở rộng thanh bên" })).toBeVisible();
  await page.getByRole("button", { name: "Mở rộng thanh bên" }).click();
  await expect(nav.getByText("Dữ liệu", { exact: true })).toBeVisible();
});

test("Nút ở bước tiếp theo dẫn tới trang Dữ liệu", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Đến trang Dữ liệu|Xem dữ liệu/ }).click();
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
