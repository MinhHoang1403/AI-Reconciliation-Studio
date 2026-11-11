import { expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { assistantPanel, test } from "./project-selection";

test("[LIVE] Assistant discovers three 3000-row sources and keeps project scope", async ({ page }) => {
  test.skip(process.env.STUDIO_SCOPE_LIVE !== "1", "Explicit live provider acceptance on synthetic sources");
  test.setTimeout(240000);
  await page.setViewportSize({ width: 1920, height: 1000 });
  const base = new URL((await page.request.get("/api/live")).url()).origin;
  const headers = () => ({ Origin: base, "Idempotency-Key": crypto.randomUUID() });
  await page.goto("/#page=home");
  expect((await page.request.get("/api/session")).ok()).toBe(true);
  const marker = crypto.randomUUID().slice(0, 8);
  const created = await page.request.post("/api/projects", {
    headers: headers(),
    data: { name: `TEST Assistant project scope ${marker}`, business_scope: "synthetic shipments", classification: "TEST" },
  });
  expect(created.status()).toBe(201);
  const { id } = await created.json();
  const evidence = "../runtime/assistant-project-scope";
  await mkdir(evidence, { recursive: true });
  await writeFile(`${evidence}/project-${id}.json`, JSON.stringify({ id, marker }));
  const names = ["Shipment register.csv", "Carrier ledger.xlsx", "Payment register.csv"];
  const makeCsv = (offset: number, size = 3000) => Buffer.from(
    "Tracking ID,Shipment date,Gross amount,Currency\n" +
    Array.from({ length: size }, (_, i) =>
      `${String(i + 1 + offset).padStart(7, "0")},2026-10-03,${(i % 127 + 1).toFixed(2)},VND\n`,
    ).join(""),
  );
  const xlsx = `${evidence}/carrier-${marker}.xlsx`;
  execFileSync("../.venv/Scripts/python.exe", [
    "-c",
    "from openpyxl import Workbook; import sys; w=Workbook(write_only=True); s=w.create_sheet('Shipments'); s.append(['Tracking ID','Shipment date','Gross amount','Currency']); [s.append([f'{i+5000:07d}','2026-10-03',f'{i%127+1}.00','VND']) for i in range(3000)]; w.save(sys.argv[1])",
    xlsx,
  ]);
  await page.goto(`/#page=data&project=${id}`);
  await page.getByRole("button", { name: "Tải dữ liệu", exact: true }).click();
  const upload = page.getByRole("dialog", { name: "Tải nguồn dữ liệu", exact: true });
  await upload.getByLabel("Chọn tệp dữ liệu").setInputFiles([
    { name: names[0], mimeType: "text/csv", buffer: makeCsv(0) },
    { name: names[1], mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: await readFile(xlsx) },
    { name: names[2], mimeType: "text/csv", buffer: makeCsv(10000) },
  ]);
  await upload.getByText("Tùy chọn đọc nâng cao", { exact: true }).click();
  await upload.getByLabel("Dùng AI đề xuất cách đọc cột").uncheck();
  await upload.getByRole("button", { name: "Tải 3 tệp", exact: true }).click();
  await expect(upload).not.toBeVisible();
  const list = async (): Promise<{ id: string; name: string; status: string }[]> =>
    (await (await page.request.get(`/api/datasets?project_id=${id}`)).json()).items;
  await expect.poll(async () => (await list()).filter(source => source.status === "NEEDS_MAPPING_REVIEW").length,
    { timeout: 45000 }).toBe(3);
  const sources = await list();
  for (const source of sources) {
    const result = await (await page.request.get(`/api/datasets/${source.id}/tables`)).json();
    expect(result.items.map((table: { row_count: number }) => table.row_count)).toEqual([3000]);
  }

  // Mở từ một tệp trong Data như tình huống người dùng đã gặp.
  await page.goto(`/#page=data&project=${id}&dataset_id=${sources[0].id}`);
  await expect(page.getByRole("heading", { name: sources[0].name, exact: true })).toBeVisible();
  // Mô phỏng localStorage của phiên bản cũ từng lưu chung con trỏ một nguồn.
  const legacy = await page.request.post("/api/conversations", {
    headers: headers(), data: { context: { project_id: id, dataset_id: sources[0].id } },
  });
  expect(legacy.status()).toBe(201);
  await page.evaluate(({ key, value }) => localStorage.setItem(key, value),
    { key: `studio.conversation.${id}`, value: (await legacy.json()).id });
  await page.getByRole("button", { name: "AI Assistant", exact: true }).click();
  const chip = page.getByRole("button", { name: "Đổi ngữ cảnh phân tích", exact: true });
  await expect(chip).toHaveAttribute("data-dataset-id", "");
  await page.goto(`/#page=assistant&project=${id}&from=data&dataset_id=${sources[0].id}`);
  await page.reload();
  await expect(chip).toHaveAttribute("data-dataset-id", "");
  const composer = page.getByRole("textbox", { name: "Câu hỏi cho AI Assistant" });
  async function send(question: string, expectedDataset: string | null = null) {
    await expect(composer).toBeEnabled();
    await composer.fill(question);
    const response = page.waitForResponse(value => value.url().endsWith("/api/assistant/messages")
      && value.request().method() === "POST");
    await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
    const accepted = await response;
    expect(accepted.status()).toBe(202);
    expect(accepted.request().postDataJSON().context.dataset_id ?? null).toBe(expectedDataset);
    return accepted;
  }
  const workflows = page.getByRole("region", { name: "Công việc của AI Assistant", exact: true });
  const inventory = "Dự án này có những tệp nào?";
  await send(inventory);
  await expect(workflows.last()).toContainText("Dự án có 3 nguồn dữ liệu.");
  for (const name of names) await expect(workflows.last()).toContainText(name);
  await expect(chip).toHaveAttribute("data-dataset-id", "");

  await page.getByRole("button", { name: "Tệp đã tải", exact: true }).click();
  const panel = assistantPanel(page, "Tệp và dữ liệu");
  await expect(panel).toContainText("3 tệp trong dự án");
  await panel.getByRole("button", { name: new RegExp(names[1].replace(".", "\\.")) }).click();
  await expect(panel.getByLabel("Bảng nguồn")).toContainText("3000 dòng");
  await panel.getByRole("button", { name: "Đóng", exact: true }).click();
  await send(inventory);
  await expect(workflows.last()).toContainText("Dự án có 3 nguồn dữ liệu.");
  await send(`Tệp "${names[1]}" đã chuẩn hóa chưa?`);
  await expect(workflows.last()).toContainText(names[1]);
  await expect(workflows.last()).not.toContainText(names[0]);
  await expect(workflows.last()).not.toContainText(names[2]);

  const preparation = await send("Hãy kiểm tra và chuẩn hóa cả ba nguồn dữ liệu");
  const cards = workflows.last().getByRole("region", { name: "Quyết định cần xác nhận", exact: true });
  await expect(cards).toHaveCount(3, { timeout: 120000 });
  for (const name of names) await expect(cards.filter({ hasText: name })).toHaveCount(1);
  const initial = await preparation.json();
  const replay = await page.request.post("/api/assistant/messages", {
    headers: { Origin: base, "Idempotency-Key": preparation.request().headers()["idempotency-key"] },
    data: preparation.request().postDataJSON(),
  });
  expect((await replay.json()).job_id).toBe(initial.job_id);
  await page.reload();
  await expect(cards).toHaveCount(3);

  await page.getByRole("button", { name: "Tệp đã tải", exact: true }).click();
  await expect(panel).toContainText("3 tệp trong dự án");
  await page.locator('.assistant-composer input[type="file"]').setInputFiles({
    name: "Later upload.csv", mimeType: "text/csv", buffer: makeCsv(20000, 3),
  });
  await send(inventory);
  await expect(workflows.last()).toContainText("Dự án có 4 nguồn dữ liệu.");
  await expect(workflows.last()).toContainText("Later upload.csv");
  await expect(panel).toContainText("4 tệp trong dự án");
  const jobs = (await (await page.request.get(`/api/jobs?project_id=${id}`)).json()).items;
  expect(jobs.filter((job: { kind: string }) => job.kind === "agent_prepare")).toHaveLength(3);
  const explicit = sources.find(source => source.name === names[1])!;
  await panel.getByRole("button").filter({ hasText: explicit.name }).first().click();
  await panel.getByRole("button", { name: "Hỏi riêng về tệp này", exact: true }).click();
  await expect(chip).toHaveAttribute("data-dataset-id", explicit.id);
  await expect(page).toHaveURL(/source_scope=1/);
  await page.reload();
  await expect(chip).toHaveAttribute("data-dataset-id", explicit.id);
  await send("Nguồn đang xem đã chuẩn hóa chưa?", explicit.id);
  await expect(workflows.last()).toContainText(explicit.name);
  await expect(workflows.last()).not.toContainText(names[0]);
  await writeFile(`${evidence}/verified-${id}.json`, JSON.stringify({
    id, original: names, rowCount: 3000, totalAfterUpload: 4, mappingReviews: 3, reusedJob: initial.job_id,
  }));
});
