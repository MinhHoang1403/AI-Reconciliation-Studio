import { expect, test } from "@playwright/test";

// Kiểm trang Báo cáo trên dịch vụ thật, chỉ ĐỌC (không đối soát, không bấm nhận xét AI nên
// không tốn phí, không đổi dữ liệu). Cần sẵn ít nhất một kỳ đã đối soát cả chuỗi; chưa có thì
// bỏ qua (bài chain.spec.ts tạo được kỳ đó trên máy trống).

type Period = { chain_id: string; label: string; verified: boolean; kpis: { open_count: number } | null };

test("báo cáo kỳ mới nhất: số chính, biểu đồ, bảng dữ liệu, tải tệp", async ({ page, request }) => {
  const { periods } = (await (await request.get("/api/reports")).json()) as { periods: Period[] };
  const latest = periods.at(-1);
  test.skip(!latest?.kpis, "Chưa có kỳ nào được đối soát cả chuỗi.");
  if (!latest?.kpis) return;

  await page.goto("/bao-cao");
  await expect(page.getByRole("heading", { level: 1, name: "Báo cáo" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Đã khớp .+ số tiền cần đối chiếu$/ })).toBeVisible();
  await expect(page.getByText(latest.label).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Cần xử lý trước" })).toBeVisible();
  for (const title of ["Theo ngày", "Theo cặp đối soát", "Tuổi ngoại lệ còn mở", "Theo loại kết quả"]) {
    await expect(page.getByRole("region", { name: title })).toBeVisible();
  }

  // Biểu đồ nào cũng có bảng dữ liệu tương ứng.
  const byDay = page.getByRole("region", { name: "Theo ngày" });
  await byDay.getByText("Xem dạng bảng").click();
  await expect(byDay.getByRole("table")).toBeVisible();

  // Kỳ đã kiểm chứng: hai nút tải trả đúng tệp; chưa kiểm chứng: nút tải bị khóa.
  if (latest.verified) {
    const excel = page.getByRole("link", { name: /Tải Excel/ });
    const csv = page.getByRole("link", { name: "Tải CSV" });
    await expect(excel).toBeVisible();
    const xlsx = await request.get((await excel.getAttribute("href")) ?? "");
    expect(xlsx.status()).toBe(200);
    expect(xlsx.headers()["content-type"]).toContain("spreadsheetml");
    const text = await (await request.get((await csv.getAttribute("href")) ?? "")).text();
    expect(text.split("\n")[0]).toContain("Cặp đối soát");
  } else {
    await expect(page.getByRole("button", { name: /Tải Excel/ })).toBeDisabled();
  }

  // Dashboard hiện số chính của kỳ mới nhất và dẫn sang trang Báo cáo.
  await page.goto("/");
  const kpis = page.getByRole("region", { name: latest.label });
  await expect(kpis.getByText("Khớp theo số tiền")).toBeVisible();
  await kpis.getByRole("button", { name: "Xem báo cáo" }).click();
  await expect(page).toHaveURL(/\/bao-cao$/);

  // Không cuộn ngang ở bất kỳ khổ màn hình nào.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
