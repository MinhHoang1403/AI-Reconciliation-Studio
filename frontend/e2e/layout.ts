import type { Page } from "@playwright/test";

/**
 * Số điểm ảnh trang tràn ra ngoài bề ngang màn hình (≤ 0 là không cuộn ngang).
 *
 * So với bề ngang khung nhìn ĐÃ ĐẶT cho thiết bị (375px trên điện thoại), không so với
 * `window.innerWidth`: khi có phần tử ép trang rộng hơn, trình duyệt điện thoại nới luôn khung
 * nhìn (innerWidth thành 466px) và thu nhỏ cả trang, nên phép so cũ luôn ra 0 dù chữ bị cắt.
 */
export async function horizontalOverflow(page: Page): Promise<number> {
  const viewport = page.viewportSize();
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  return width - (viewport?.width ?? width);
}
