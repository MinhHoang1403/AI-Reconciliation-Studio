import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext } from "@playwright/test";

// Kiểm luồng Dữ liệu trên dịch vụ thật: tải tệp mẫu, xem bảng, đổi sheet, hồ sơ cột, xóa.
// E2E chạy trên container chính, nơi có thể có dữ liệu của người dùng, nên mỗi bài chỉ xóa
// đúng bộ dữ liệu do chính nó tạo ra; nếu tệp mẫu đã có sẵn từ trước thì bỏ qua bài đó.

const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../tests/fixtures/sales");

type Dataset = { id: string; original_filename: string };

async function existingNames(request: APIRequestContext): Promise<Set<string>> {
  const reply = await request.get("/api/datasets");
  return new Set(((await reply.json()) as Dataset[]).map((dataset) => dataset.original_filename));
}

/** Xóa các bộ dữ liệu mang tên tệp mẫu mà trước bài kiểm chưa có. */
async function removeCreated(request: APIRequestContext, before: Set<string>, names: string[]) {
  const reply = await request.get("/api/datasets");
  for (const dataset of (await reply.json()) as Dataset[]) {
    if (names.includes(dataset.original_filename) && !before.has(dataset.original_filename)) {
      await request.delete(`/api/datasets/${dataset.id}`);
    }
  }
}

test("tải tệp Excel nhiều sheet, xem dữ liệu, đổi sheet và hồ sơ cột", async ({ page, request }) => {
  const name = "sao-ke-ngan-hang.xlsx";
  const before = await existingNames(request);
  test.skip(before.has(name), "Tệp mẫu đã có sẵn trong dữ liệu của người dùng");
  try {
    await page.goto("/du-lieu");
    await page.getByLabel("Chọn tệp").setInputFiles(path.join(FIXTURES, name));
    await expect(page.getByText("Đã tải lên, đang đọc dữ liệu.")).toBeVisible();
    const item = page.getByRole("listitem").filter({ hasText: "sao-ke-ngan-hang" });
    await expect(item.getByText("Đã đọc")).toBeVisible();

    await item.getByRole("link", { name: "sao-ke-ngan-hang" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "sao-ke-ngan-hang" })).toBeVisible();
    await expect(page.getByRole("tab", { name: /TK chinh/ })).toHaveAttribute("aria-selected", "true");
    // Dòng tiêu đề tự nhận ở dòng 5 (dưới các dòng tên báo cáo), dữ liệu bắt đầu từ dòng gốc 6.
    await expect(page.getByLabel("Dòng tiêu đề")).toHaveValue("5");
    await expect(page.getByRole("columnheader", { name: "Nội dung" })).toBeVisible();
    await expect(page.getByRole("rowheader", { name: "6", exact: true })).toBeVisible();

    await page.getByRole("tab", { name: /TK san/ }).click();
    await expect(page.getByText(/SAN TMDT THANH TOAN DOANH THU/).first()).toBeVisible();

    await page.getByRole("button", { name: "Hồ sơ cột" }).click();
    const content = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: "Nội dung" }) });
    await expect(content.getByText("Chữ", { exact: true })).toBeVisible();
  } finally {
    await removeCreated(request, before, [name]);
  }
});

test("tải CSV giữ số 0 đầu mã, nhận ra tệp trùng, xóa có xác nhận", async ({ page, request }) => {
  const name = "don-hang-cua-hang.csv";
  const before = await existingNames(request);
  test.skip(before.has(name), "Tệp mẫu đã có sẵn trong dữ liệu của người dùng");
  try {
    await page.goto("/du-lieu");
    const file = path.join(FIXTURES, name);
    await page.getByLabel("Chọn tệp").setInputFiles(file);
    const item = page.getByRole("listitem").filter({ hasText: "don-hang-cua-hang" });
    await expect(item.getByText("Đã đọc")).toBeVisible();
    await expect(item.getByText("222 dòng")).toBeVisible();

    await page.getByLabel("Chọn tệp").setInputFiles(file);
    await expect(page.getByText(/Tệp này đã có/)).toBeVisible();

    await item.getByRole("link", { name: "don-hang-cua-hang" }).click();
    await expect(page.getByRole("cell", { name: "HD000101" })).toBeVisible();

    // Ánh xạ cột: tự gợi ý sau khi đọc (quy tắc, và Gemini nếu container có khóa).
    await page.getByRole("button", { name: /^Ánh xạ/ }).click();
    // Gemini trả lời mất vài giây tới hơn chục giây (đo thật 1,7–19 giây), nên chờ tối đa 60 giây.
    await expect(page.getByLabel("MaHD")).toHaveValue("order_id", { timeout: 60_000 });
    await expect(page.getByLabel("ThanhToan")).toHaveValue("payment_method");
    await expect(page.getByText(/Gợi ý bởi quy tắc và Gemini|Chỉ dùng quy tắc/)).toBeVisible();

    await page.getByRole("link", { name: "Dữ liệu" }).first().click();
    await page.getByRole("button", { name: "Xóa bộ dữ liệu don-hang-cua-hang" }).click();
    const dialog = page.getByRole("dialog", { name: "Xóa bộ dữ liệu?" });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Xóa hẳn" }).click();
    await expect(page.getByRole("link", { name: "don-hang-cua-hang" })).toHaveCount(0);
  } finally {
    await removeCreated(request, before, [name]);
  }
});

test("tệp sai định dạng bị từ chối với thông báo rõ ràng", async ({ page }) => {
  await page.goto("/du-lieu");
  await page.getByLabel("Chọn tệp").setInputFiles({
    name: "bao-cao.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4"),
  });
  await expect(page.getByText(/Chỉ nhận tệp CSV hoặc Excel/)).toBeVisible();
});

test("Tổng quan đánh dấu bước Đọc tệp đã xong khi có dữ liệu", async ({ page, request }) => {
  const name = "giao-dich-cong-thanh-toan.csv";
  const before = await existingNames(request);
  try {
    await request.post("/api/datasets", {
      multipart: {
        file: { name, mimeType: "text/csv", buffer: fs.readFileSync(path.join(FIXTURES, name)) },
      },
    });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Đã đọc \d+ bộ dữ liệu/ })).toBeVisible();
    await expect(page.getByRole("listitem").filter({ hasText: "Đọc tệp" })).toContainText(/Đã đọc \d+ bộ/);
  } finally {
    await removeCreated(request, before, [name]);
  }
});
