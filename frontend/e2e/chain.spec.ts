import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext } from "@playwright/test";

import { horizontalOverflow } from "./layout";

// Kiểm luồng đối soát theo kỳ trên dịch vụ thật: bốn tệp kỳ 1 → một nút chạy cả chuỗi →
// "Tất cả cần xử lý" gộp ngoại lệ của các cặp → chọn cặp đúng cho ca mơ hồ → xem chờ tiền về.
// Chỉ xóa đúng bộ dữ liệu do bài này tạo; tệp mẫu đã có sẵn thì bỏ qua để không đụng dữ liệu
// của người dùng.

const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../tests/fixtures/sales");
const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const FILES: Record<string, string> = {
  "don-hang-cua-hang.csv": "text/csv",
  "giao-dich-cong-thanh-toan.csv": "text/csv",
  "don-hang-san-tmdt.xlsx": XLSX,
  "sao-ke-ngan-hang.xlsx": XLSX,
};
const NAMES = Object.keys(FILES);

type Dataset = { id: string; original_filename: string };
type Period = { tables: { id: string }[] };

// Đọc tệp gọi Gemini thật để gợi ý ánh xạ (bốn tệp), nên cho bài tối đa 180 giây.
test.describe.configure({ timeout: 180_000 });

async function datasets(request: APIRequestContext): Promise<Dataset[]> {
  return (await (await request.get("/api/datasets")).json()) as Dataset[];
}

test("đối soát cả chuỗi của một kỳ, chọn cặp cho ca mơ hồ", async ({ page, request }) => {
  const before = new Set((await datasets(request)).map((item) => item.original_filename));
  test.skip(NAMES.some((name) => before.has(name)), "Tệp mẫu đã có sẵn; không đụng dữ liệu người dùng.");
  try {
    for (const name of NAMES) {
      await request.post("/api/datasets", {
        multipart: {
          file: { name, mimeType: FILES[name] ?? "text/csv", buffer: fs.readFileSync(path.join(FIXTURES, name)) },
        },
      });
    }
    // Chờ đọc, ánh xạ, làm sạch xong: kỳ của tệp sao kê có đủ 5 bảng (sao kê có hai sheet).
    await expect(async () => {
      const periods = (await (await request.get("/api/recon/periods")).json()) as Period[];
      expect(periods.some((period) => period.tables.length >= 5)).toBe(true);
    }).toPass({ timeout: 150_000 });

    await page.goto("/doi-soat");
    await page.getByRole("button", { name: /Đối soát cả chuỗi|Chạy lại cả chuỗi/ }).click();

    // Bộ mẫu kỳ 1: 4 cặp nối được, 10 ca cần xem, mọi cặp đạt kiểm chứng.
    await expect(page.getByRole("heading", { name: "Cần bạn xem 10 ca" })).toBeVisible({ timeout: 60_000 });
    await expect(page.locator(".chain__pair")).toHaveCount(4);
    await expect(page.getByText("Cả 4 cặp đều đạt bốn phép kiểm độc lập.")).toBeVisible();

    // Ca mơ hồ: hai đơn cùng tên "Minh Hoàng", cùng số tiền với một dòng sao kê. Không tự chọn.
    const ambiguous = page.locator(".recon-group").filter({ hasText: "Cần bạn chọn" });
    await expect(ambiguous).toContainText("CHU HOANG CHUYEN");
    await ambiguous.getByRole("button", { name: "Chọn" }).first().click();
    await expect(page.locator(".recon-group").filter({ hasText: "Cần bạn chọn" })).toHaveCount(0, {
      timeout: 60_000,
    });
    // Đơn không được chọn trở thành "Chỉ có ở A".
    const onlyA = page.locator(".recon-group").filter({ hasText: "Chỉ có ở A" });
    await expect(onlyA).toContainText("HD000119");

    // Ghép tay: đơn HD000142 (cổng thanh toán không có giao dịch) ghép với một dòng chưa ghép.
    const lonely = onlyA.locator(".result").filter({ hasText: "HD000142" });
    await lonely.getByRole("button", { name: "Ghép tay" }).click();
    const picker = lonely.locator(".match-picker");
    await picker.getByRole("checkbox").first().check();
    await picker.getByRole("button", { name: /^Ghép 1 dòng/ }).click();
    const manual = page.locator(".result").filter({ hasText: "HD000142" }).filter({ hasText: "Bạn đã chọn cặp này" });
    await expect(manual).toBeVisible({ timeout: 60_000 });

    // Gỡ ghép lại qua hộp xác nhận: đơn trở về "Chỉ có ở A".
    await manual.locator(".result__actions").getByRole("button", { name: "Gỡ ghép" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Gỡ ghép" }).click();
    await expect(onlyA.locator(".result").filter({ hasText: "HD000142" })).toBeVisible({ timeout: 60_000 });

    // Cặp sàn TMĐT ↔ sao kê: các đơn cuối kỳ nằm trong tab "Chờ tiền về".
    await page.locator(".chain__pair").filter({ hasText: "TK san" }).click();
    await page.getByRole("button", { name: /^Chờ tiền về/ }).click();
    await expect(page.getByText(/Kỳ sau sẽ tự ghép lại/).first()).toBeVisible();

    const width = await horizontalOverflow(page);
    expect(width).toBeLessThanOrEqual(0);
  } finally {
    for (const dataset of await datasets(request)) {
      if (NAMES.includes(dataset.original_filename) && !before.has(dataset.original_filename)) {
        await request.delete(`/api/datasets/${dataset.id}`);
      }
    }
  }
});
