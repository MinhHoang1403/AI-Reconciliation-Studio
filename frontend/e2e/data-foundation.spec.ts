import { test, expect, type Page } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";

test.describe.configure({ mode: "serial" });
const projectName = `Dữ liệu tổng hợp · ${Date.now()}`;
const expectGemini = process.env.STUDIO_EXPECT_AI_PROVIDER === "GEMINI";
const expectManual = (process.env.STUDIO_EXPECT_AI_PROVIDER || "MANUAL") === "MANUAL";
let projectId = "";
let datasetId = "";
let tableId = "";

async function openApp(page: Page) {
  await page.goto("/");
  await expect(page.getByText("Hệ thống đã kết nối")).toBeAttached();
  await expect(page.locator("#project-select")).toBeVisible();
}

test("A/C/D: create project, upload, review mapping with explicit provider, normalize invalid data", async ({
  page,
}) => {
  test.setTimeout(expectGemini ? 180000 : 60000);
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(err.message));
  await openApp(page);
  const configured = await page.request.get("/api/settings");
  expect((await configured.json()).mapping_ai_provider).toBe(expectGemini || expectManual ? "GEMINI" : "QWEN");
  await page.getByRole("button", { name: "+ Tạo dự án", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Tên dự án", { exact: true }).fill(projectName);
  await dialog
    .getByLabel("Phạm vi nghiệp vụ")
    .fill(`${projectName} · kiểm tra đơn hàng`);
  await dialog.getByRole("button", { name: "Tạo dự án", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  projectId = await page.locator("#project-select").inputValue();
  await page.getByRole("button", { name: "Tải dữ liệu", exact: true }).click();
  await page.getByLabel("Chọn tệp dữ liệu").setInputFiles({
    name: "synthetic-orders.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Order ID,Gross amount\n000123,1234.50\n000124,invalid\n000125,\n000126,0\n",
    ),
  });
  if (expectManual) {
    await dialog.locator("summary", {hasText: "Tùy chọn đọc nâng cao"}).click();
    await dialog.getByLabel("Dùng AI đề xuất ánh xạ trong hạn mức").uncheck();
  }
  await dialog.getByRole("button", { name: "Tải 1 tệp" }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("tab", { name: "AI Smart Setup" })).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "000123", exact: true }),
  ).toBeVisible();
  const datasets = await page.request.get(
    `/api/datasets?project_id=${projectId}`,
  );
  datasetId = (await datasets.json()).items[0].id;
  const tables = await page.request.get(`/api/datasets/${datasetId}/tables`);
  tableId = (await tables.json()).items[0].id;
  if (expectGemini) {
    await expect.poll(async () => {
      const response = await page.request.get(`/api/jobs?project_id=${projectId}`);
      const job = (await response.json()).items.find((j: {kind: string}) => j.kind === "mapping");
      return job?.status;
    }, {timeout: 120000}).toBe("SUCCEEDED");
    const response = await page.request.get(`/api/jobs?project_id=${projectId}`);
    const job = (await response.json()).items.find((j: {kind: string}) => j.kind === "mapping");
    expect(job.result.source).toBe("GEMINI");
    const mappings = await page.request.get(`/api/tables/${tableId}/mappings`);
    const proposal = (await mappings.json()).items[0];
    expect(proposal.status).not.toBe("APPROVED");
    expect(proposal.proposal.decisions.some((d: {source_field: string; candidate_target: string}) =>
      d.source_field === "c1" && d.candidate_target === "reference_id")).toBeTruthy();
    await page.getByRole("button", {name: "Cập nhật", exact: true}).click();
    await expect(page.getByRole("button", {name: "Cập nhật", exact: true})).toBeEnabled();
  }
  await page.getByRole("tab", { name: "AI Smart Setup" }).click();
  await expect(
    page.getByRole("heading", { name: "Hiểu dữ liệu, xác nhận ý nghĩa" }),
  ).toBeVisible();
  await page.getByLabel("Loại dữ liệu", { exact: true }).fill("order");
  await page
    .getByLabel("Mỗi dòng đại diện cho điều gì?")
    .fill("Một đơn hàng từ nguồn tổng hợp");
  await page
    .getByLabel("Trường đích Order ID", { exact: true })
    .fill("reference_id");
  await page
    .getByLabel("Trường đích Gross amount", { exact: true })
    .fill("gross_amount");
  await page
    .getByLabel("Kiểu Gross amount", { exact: true })
    .selectOption("decimal");
  await page
    .getByLabel("Locale Gross amount", { exact: true })
    .selectOption("en-US");
  await page
    .getByLabel("Chỉ tiêu Gross amount", { exact: true })
    .fill("synthetic_gross");
  await page
    .getByLabel("Cơ sở Gross amount", { exact: true })
    .selectOption("gross");
  await page.getByLabel("Tiền tệ Gross amount", { exact: true }).fill("VND");
  await page.getByLabel("Đơn vị Gross amount", { exact: true }).fill("VND");
  await page.getByRole("button", {name: "Cập nhật", exact: true}).click();
  await expect(page.getByRole("button", {name: "Cập nhật", exact: true})).toBeEnabled();
  await expect(page.getByLabel("Loại dữ liệu", {exact: true})).toHaveValue("order");
  await expect(page.getByLabel("Locale Gross amount", {exact: true})).toHaveValue("en-US");
  await expect(page.getByRole("button", {name: "Xác nhận ánh xạ", exact: true})).toBeEnabled();
  await page
    .getByRole("button", { name: "Xác nhận ánh xạ", exact: true })
    .click();
  await expect(
    page.getByText("Đã cập nhật ánh xạ.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Chuẩn hóa", exact: true }).click();
  await page
    .getByRole("button", { name: "Chuẩn hóa dữ liệu", exact: true })
    .click();
  await expect
    .poll(async () => {
      const response = await page.request.get(
        `/api/datasets/${datasetId}/artifacts`,
      );
      return (await response.json()).canonical_datasets.length;
    })
    .toBe(1);
  await page
    .getByRole("button", { name: "Cập nhật kết quả", exact: true })
    .click();
  await page.getByRole("button", { name: "Xem kết quả", exact: false }).click();
  await expect(
    page.getByRole("cell", { name: "1234.50", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "000123", exact: true }),
  ).toBeVisible();
  let releaseSearch: (() => void) | undefined;
  const delayedSearch = /\/api\/tables\/.*\/preview\?.*search=000123/;
  await page.route(delayedSearch, async (route) => {
    await new Promise<void>((resolve) => {
      releaseSearch = resolve;
    });
    await route.continue();
  });
  await page.getByLabel("Tìm trong bảng").fill("000123");
  await expect.poll(() => typeof releaseSearch).toBe("function");
  expect(
    await page.getByRole("cell", { name: "000124", exact: true }).count(),
  ).toBe(0);
  releaseSearch?.();
  await expect(
    page.getByRole("cell", { name: "000123", exact: true }),
  ).toBeVisible();
  await page.unroute(delayedSearch);
  await page.getByLabel("Tìm trong bảng").fill("");
  await expect(
    page.getByRole("cell", { name: "000124", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Cảnh báo / lỗi", exact: true })
    .click();
  await expect(
    page.getByRole("cell", { name: "invalid", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Số tiền không hợp lệ", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "Chưa có giá trị", exact: true }).first(),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Xem nguồn", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("dialog", { name: "Bằng chứng nguồn" }),
  ).toBeVisible();
  await expect(
    page.getByRole("dialog").getByRole("cell", { name: "000124", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Đóng", exact: true }).click();
  if (expectManual) {
    const response = await page.request.get(`/api/jobs?project_id=${projectId}`);
    expect((await response.json()).items.some((job: {kind: string}) => job.kind === "mapping")).toBe(false);
  } else await expect
    .poll(async () => {
      const r = await page.request.get(`/api/jobs?project_id=${projectId}`);
      const j = (await r.json()).items.find(
        (j: { kind: string }) => j.kind === "mapping",
      );
      return j?.status;
    })
    .toBe(expectGemini ? "SUCCEEDED" : "BLOCKED");
  if (!expectGemini && !expectManual) await expect(page.getByText(/Qwen từ chối IP truy cập/)).toBeVisible();
  expect(errors).toEqual([]);
});

test("B: returning user retains project, approved mapping and canonical refs", async ({
  page,
}) => {
  await openApp(page);
  await page.locator("#project-select").selectOption(projectId);
  await page.getByRole("button", { name: /synthetic-orders.csv/ }).click();
  await page.getByRole("tab", { name: "AI Smart Setup" }).click();
  await expect(
    page.getByLabel("Locale Gross amount", { exact: true }),
  ).toHaveValue("en-US");
  await page.getByRole("tab", { name: "Chuẩn hóa", exact: true }).click();
  await page
    .getByRole("button", { name: "Cập nhật kết quả", exact: true })
    .click();
  await expect(page.getByRole("button", { name: "Xem kết quả" })).toBeVisible();
  const response = await page.request.get(`/api/tables/${tableId}/mappings`);
  expect(
    (await response.json()).items.some(
      (m: { status: string }) => m.status === "APPROVED",
    ),
  ).toBeTruthy();
});

test("E/F: same-origin session, CSRF, public host rejection, no external browser requests", async ({
  page,
  request,
}) => {
  const external: string[] = [];
  page.on("request", (r) => {
    if (!r.url().startsWith("http://127.0.0.1:18180")) external.push(r.url());
  });
  await openApp(page);
  const cookies = await page.context().cookies();
  const session = cookies.find((c) => c.name === "studio_session");
  expect(session?.httpOnly).toBeTruthy();
  expect(session?.sameSite).toBe("Strict");
  const csrf = await page.request.post("/api/projects", {
    headers: { Origin: "https://evil.example" },
    data: { name: "forbidden", business_scope: "synthetic" },
  });
  expect(csrf.status()).toBe(403);
  const anonymous = await request.get("/api/projects");
  expect(anonymous.status()).toBe(401);
  const spoofed = await request.get("/api/session", {
    headers: { Host: "evil.example" },
  });
  expect(spoofed.status()).toBe(403);
  expect(external).toEqual([]);
});

for (const size of [
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
  { width: 1366, height: 768 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
]) {
  test(`visual and overflow ${size.width}x${size.height}`, async ({ page }) => {
    await page.setViewportSize(size);
    await openApp(page);
    await page.locator("#project-select").selectOption(projectId);
    await expect(
      page.getByRole("heading", { name: "Nền tảng dữ liệu của bạn" }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    await mkdir("../runtime/screenshots", { recursive: true });
    await page.screenshot({
      path: `../runtime/screenshots/dashboard-${size.width}.png`,
      fullPage: true,
    });
    await page.getByRole("button", { name: /synthetic-orders.csv/ }).click();
    await page.getByRole("tab", { name: "AI Smart Setup" }).click();
    await expect(
      page.getByLabel("Trường đích Gross amount", { exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: `../runtime/screenshots/mapping-${size.width}.png`,
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Tải dữ liệu", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toBeVisible();
    expect(
      await page
        .getByRole("dialog")
        .evaluate((el) => el.scrollWidth <= el.clientWidth),
    ).toBeTruthy();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).not.toBeVisible();
  });
}

test("cached document evidence remains readable after parser allowance is closed", async ({page}) => {
  let state: {project_id: string} | undefined;
  try {
    state = JSON.parse(await readFile("../runtime/document-acceptance/acceptance.json", "utf8"));
  } catch {
    test.skip(true, "Run the separately authorized two-document acceptance before this cached-only check");
    return;
  }
  await openApp(page);
  await page.locator("#project-select").selectOption(state!.project_id);
  for (const [extension, id, amount] of [["pdf", "000123", "1234.50"], ["docx", "000701", "1.234,50"]]) {
    await page.getByRole("button", {name: new RegExp(`synthetic-transactions\\.${extension}`)}).click();
    await expect(page.getByText("Bản trích xuất chưa được xác minh.", {exact:false})).toBeVisible();
    await expect(page.getByRole("cell", {name:id,exact:true})).toBeVisible();
    await expect(page.getByRole("cell", {name:amount,exact:true})).toBeVisible();
    await expect(page.getByRole("button", {name:"Chuẩn hóa dữ liệu",exact:true})).toHaveCount(0);
  }
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
