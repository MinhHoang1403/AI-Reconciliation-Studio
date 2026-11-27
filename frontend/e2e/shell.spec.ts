import { expect, test } from "@playwright/test";

import { horizontalOverflow } from "./layout";

// Kiểm khung ứng dụng trên dịch vụ thật: điều hướng, trạng thái hệ thống, trang chưa có chức năng.

test("Dashboard hiển thị bước tiếp theo, quy trình và trạng thái hệ thống", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
  // Nội dung phụ thuộc container đã có dữ liệu hay chưa, nên chấp nhận cả hai trạng thái.
  await expect(
    page.getByRole("heading", {
      name: /Tải bộ dữ liệu đầu tiên|Đã đọc \d+ bộ dữ liệu|Cần bạn (xem|xử lý) \d+|\d+ bộ dữ liệu đã sạch/,
    }),
  ).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "Đọc tệp" })).toContainText(/Đang chờ tệp|Đã đọc/);
  // Con dấu theo lần đối soát gần nhất của máy: chưa có thì "Chưa kiểm chứng".
  await expect(page.getByRole("img", { name: /Chưa kiểm chứng|Kiểm chứng đạt|Kiểm chứng không đạt/ })).toBeVisible();
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
    ["AI Assistant", "/assistant"],
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

test("Nút ở bước tiếp theo dẫn tới đúng trang của việc cần làm", async ({ page }) => {
  // Môi trường duy nhất (R8) có thể đang có dữ liệu Owner thử: tùy tình trạng, bước tiếp theo
  // là Dữ liệu, Đối soát hoặc Báo cáo; nút phải dẫn tới đúng trang nó ghi.
  await page.goto("/");
  const button = page.locator(".next-step .button--primary");
  await expect(button).toBeEnabled(); // hết "Đang tải dữ liệu…"
  const label = (await button.textContent()) ?? "";
  const target = /báo cáo/i.test(label) ? "/bao-cao" : /đối soát/i.test(label) ? "/doi-soat" : "/du-lieu";
  await button.click();
  await expect(page).toHaveURL(target);
});

test("Dashboard không nháy \"chưa có dữ liệu\" khi đang có dữ liệu", async ({ page, request }) => {
  const datasets = (await (await request.get("/api/datasets")).json()) as unknown[];
  test.skip(datasets.length === 0, "Hệ thống đang trống");
  const seen: string[] = [];
  await page.route("**/api/recon/runs?limit=1", async (route) => {
    // Làm chậm lần đọc đối soát để chụp được trạng thái đang tải.
    seen.push((await page.locator("#next-step-title").textContent().catch(() => "")) ?? "");
    await route.continue();
  });
  await page.goto("/");
  await expect(page.locator("#next-step-title")).not.toHaveText("Tải bộ dữ liệu đầu tiên");
  expect(seen.join("|")).not.toContain("Tải bộ dữ liệu đầu tiên");
});

test("Không trang nào bị cuộn ngang hay bị thu nhỏ", async ({ page }) => {
  for (const path of ["/", "/assistant", "/du-lieu", "/doi-soat", "/bao-cao", "/lich-su"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    expect(await horizontalOverflow(page), path).toBeLessThanOrEqual(0);
  }
});

test("AI Assistant: ô nhập luôn nằm trong màn hình, trên thanh tab, trang không cuộn", async ({ page }) => {
  await page.goto("/assistant");
  const composer = page.locator(".chat-composer");
  await expect(composer).toBeVisible();
  const box = await composer.boundingBox();
  const rail = await page.getByRole("navigation", { name: "Điều hướng chính" }).boundingBox();
  const viewport = page.viewportSize();
  expect(box && viewport).toBeTruthy();
  if (!box || !viewport || !rail) return;
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
  // Điện thoại: thanh tab ở đáy; ô nhập phải nằm trên nó (dải chọn phiên ở đầu trang không
  // được đẩy ô nhập xuống dưới thanh tab).
  if (rail.y > viewport.height / 2) expect(box.y + box.height).toBeLessThanOrEqual(rail.y);
  const scroll = await page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
  expect(scroll).toBeLessThanOrEqual(1);
});

test("Trang không nhúng được vào trang khác và chỉ chạy script của chính ứng dụng", async ({ page, request }) => {
  for (const path of ["/", "/assets/does-not-matter.js", "/doi-soat"]) {
    const headers = (await request.get(path)).headers();
    expect(headers["x-frame-options"], path).toBe("DENY");
    expect(headers["content-security-policy"], path).toContain("frame-ancestors 'none'");
    expect(headers["x-content-type-options"], path).toBe("nosniff");
  }
  // CSP không chặn chính ứng dụng: các trang vẫn chạy, không có lỗi vi phạm CSP.
  const violations: string[] = [];
  page.on("console", (message) => {
    if (/Content Security Policy/i.test(message.text())) violations.push(message.text());
  });
  for (const path of ["/", "/assistant", "/du-lieu", "/doi-soat", "/bao-cao", "/lich-su"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
  }
  expect(violations).toEqual([]);
});

test("API trạng thái không trả khóa bí mật", async ({ request }) => {
  const reply = await request.get("/api/status");
  expect(reply.ok()).toBeTruthy();
  const body = await reply.json();
  expect(Object.keys(body.gemini)).toEqual(["name", "model", "state"]);
});
