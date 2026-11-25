import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext } from "@playwright/test";

import { horizontalOverflow } from "./layout";

// Kiểm luồng Đối soát trên dịch vụ thật: hai tệp mẫu → chạy đối soát → ngoại lệ → ghi chú →
// nhật ký kiểm toán. Như data.spec.ts, chỉ xóa đúng bộ dữ liệu do bài này tạo; tệp mẫu đã có
// sẵn từ trước thì bỏ qua để không đụng dữ liệu của người dùng.

const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../tests/fixtures/sales");
const POS_FILE = "don-hang-cua-hang.csv";
const GATEWAY_FILE = "giao-dich-cong-thanh-toan.csv";
const FILES = [POS_FILE, GATEWAY_FILE];

type Dataset = { id: string; original_filename: string; tables: { id: string }[] };

// Đọc tệp gọi Gemini thật để gợi ý ánh xạ, nên cho mỗi bài tối đa 120 giây.
test.describe.configure({ timeout: 120_000 });

async function datasets(request: APIRequestContext): Promise<Dataset[]> {
  return (await (await request.get("/api/datasets")).json()) as Dataset[];
}

test("đối soát đơn cửa hàng với cổng thanh toán, ghi chú ngoại lệ, xem lịch sử", async ({ page, request }) => {
  const before = new Set((await datasets(request)).map((item) => item.original_filename));
  test.skip(FILES.some((name) => before.has(name)), "Tệp mẫu đã có sẵn; không đụng dữ liệu người dùng.");
  try {
    for (const name of FILES) {
      await request.post("/api/datasets", {
        multipart: { file: { name, mimeType: "text/csv", buffer: fs.readFileSync(path.join(FIXTURES, name)) } },
      });
    }
    // Chờ đọc, ánh xạ và làm sạch xong: cả hai bảng có mặt trong danh sách đối soát.
    const ids: Record<string, string> = {};
    await expect(async () => {
      for (const dataset of await datasets(request)) {
        if (FILES.includes(dataset.original_filename) && dataset.tables[0]) ids[dataset.original_filename] = dataset.tables[0].id;
      }
      const ready = (await (await request.get("/api/recon/tables")).json()) as { tables: { id: string }[] };
      expect(FILES.every((name) => ready.tables.some((table) => table.id === ids[name]))).toBe(true);
    }).toPass({ timeout: 90_000 });

    await page.goto("/doi-soat");
    await page.getByLabel("Bên A").selectOption(ids[POS_FILE] ?? "");
    await page.getByLabel("Bên B").selectOption(ids[GATEWAY_FILE] ?? "");
    await page.getByRole("button", { name: /Chạy đối soát|Chạy lại/ }).click();

    await expect(page.getByRole("heading", { name: "Cần bạn xem 4 ca" })).toBeVisible();
    await expect(page.getByRole("img", { name: "Kiểm chứng đạt" })).toBeVisible();
    const mismatch = page.locator(".recon-group").filter({ hasText: "Lệch tiền" });
    await expect(mismatch).toContainText("B thiếu 20.000đ");

    await mismatch.getByRole("button", { name: "Ghi chú" }).click();
    await mismatch.getByLabel("Ghi chú").fill("Khách được giảm giá tại quầy");
    await mismatch.getByRole("button", { name: "Lưu" }).click();
    await expect(page.getByRole("heading", { name: "Cần bạn xem 3 ca" })).toBeVisible();
    await page.getByRole("button", { name: /Đã ghi chú/ }).click();
    await expect(page.getByText("Khách được giảm giá tại quầy")).toBeVisible();

    await page.goto("/lich-su");
    await expect(page.getByText(/Ghi chú cho Lệch tiền/).first()).toBeVisible();
    await expect(page.getByText(/Chạy đối soát\./).first()).toBeVisible();

    const width = await horizontalOverflow(page);
    expect(width).toBeLessThanOrEqual(0);
  } finally {
    for (const dataset of await datasets(request)) {
      if (FILES.includes(dataset.original_filename) && !before.has(dataset.original_filename)) {
        await request.delete(`/api/datasets/${dataset.id}`);
      }
    }
  }
});
