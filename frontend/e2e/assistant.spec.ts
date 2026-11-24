import { expect, test, type APIRequestContext } from "@playwright/test";

// Kiểm trang Assistant trên dịch vụ thật: màn hình đầu có gợi ý (không phải ô chat trống),
// gửi một câu hỏi chỉ đọc (gọi Gemini thật một lần), thấy các bước và câu trả lời, rồi xóa
// cuộc trò chuyện qua hộp xác nhận. Chỉ xóa đúng cuộc trò chuyện do bài này tạo.

test.describe.configure({ timeout: 150_000 });

type Thread = { id: string; title: string };

async function threads(request: APIRequestContext): Promise<Thread[]> {
  return (await (await request.get("/api/assistant/threads")).json()) as Thread[];
}

test("hỏi Assistant một câu chỉ đọc, xem các bước và câu trả lời, xóa cuộc trò chuyện", async ({ page, request }) => {
  const before = new Set((await threads(request)).map((item) => item.id));
  try {
    await page.goto("/assistant");
    await page.getByRole("button", { name: "Cuộc trò chuyện mới" }).click();
    await expect(page.getByRole("heading", { name: "Bắt đầu từ dữ liệu của bạn" })).toBeVisible();
    await expect(page.getByRole("list", { name: "Câu hỏi gợi ý" }).getByRole("button")).toHaveCount(4);

    const input = page.getByLabel("Câu hỏi cho AI Assistant");
    await input.fill("Tôi đã tải những tệp nào lên rồi?");
    await input.press("Enter");

    const answer = page.locator(".chat-message[data-role='assistant']").last();
    await expect(page.locator(".chat-message[data-role='user']").last()).toContainText("Tôi đã tải những tệp nào");
    // Câu trả lời xong (không còn "đang làm"), có ít nhất một bước đã chạy và có lời đáp.
    await expect(answer).toHaveAttribute("aria-busy", "false", { timeout: 120_000 });
    await expect(answer.locator(".chat-steps li").first()).toBeVisible();
    await expect(answer.locator(".chat-text, .chat-message__error")).toBeVisible();

    const width = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(width).toBeLessThanOrEqual(0);
    // Ô nhập nằm trong màn hình (không bị cắt ở đáy).
    const composer = await page.locator(".chat-composer").boundingBox();
    const viewport = page.viewportSize();
    if (composer && viewport && viewport.width > 760) {
      expect(composer.y + composer.height).toBeLessThanOrEqual(viewport.height);
    }

    // Máy tính: thu gọn cột cuộc trò chuyện cho khung chat rộng hơn, nhớ sau khi tải lại.
    const toggle = page.getByRole("button", { name: "Thu gọn danh sách cuộc trò chuyện" });
    if (await toggle.isVisible()) {
      const before = (await page.locator(".chat").boundingBox())?.width ?? 0;
      await toggle.click();
      await expect(page.getByRole("button", { name: "Mở danh sách cuộc trò chuyện" })).toBeVisible();
      await expect.poll(async () => (await page.locator(".chat").boundingBox())?.width ?? 0).toBeGreaterThan(before + 150);
      await page.reload();
      await page.getByRole("button", { name: "Mở danh sách cuộc trò chuyện" }).click();
      await expect(page.getByRole("button", { name: "Thu gọn danh sách cuộc trò chuyện" })).toBeVisible();
    }

    // Xóa cuộc trò chuyện vừa tạo qua hộp xác nhận.
    const created = (await threads(request)).find((item) => !before.has(item.id));
    expect(created).toBeTruthy();
    const list = page.locator(".chat-threads__wide:visible, .chat-threads__fold[open]");
    if (!(await page.locator(".chat-threads__wide").isVisible())) {
      await page.locator(".chat-threads__fold summary").click();
    }
    await list.getByRole("button", { name: `Xóa cuộc trò chuyện “${created?.title ?? ""}”` }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Xóa cuộc trò chuyện" }).click();
    await expect.poll(async () => (await threads(request)).some((item) => item.id === created?.id)).toBe(false);
  } finally {
    for (const item of await threads(request)) {
      if (!before.has(item.id)) await request.delete(`/api/assistant/threads/${item.id}`);
    }
  }
});
