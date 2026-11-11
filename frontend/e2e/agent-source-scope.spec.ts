import { expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { test } from "./project-selection";

test("[LIVE] confirm only missing facts and prepare two pairs without executing", async ({ page }) => {
  const receipt = process.env.STUDIO_SOURCE_SCOPE_RECEIPT;
  test.skip(!receipt, "Requires a disposable TEST project with three approved canonical sources");
  test.setTimeout(150000);
  const { project, sources } = JSON.parse(await readFile(receipt!, "utf8")) as {
    project: string;
    sources: { name: string; canonical: string }[];
  };
  expect(sources).toHaveLength(3);
  await page.goto(`/#page=assistant&project=${project}`);
  const composer = page.getByRole("textbox", { name: "Câu hỏi cho AI Assistant", exact: true });
  const options = page.getByLabel("Tùy chọn hội thoại", { exact: true });
  await options.click();
  await page.getByLabel("Trợ lý cho tin nhắn mới", { exact: true }).selectOption("GEMINI");
  await options.click();
  const send = page.getByRole("button", { name: "Gửi câu hỏi", exact: true });
  const workflow = page.getByRole("region", { name: "Công việc của AI Assistant", exact: true }).first();
  const reviews = workflow.getByRole("region", { name: "Quyết định cần xác nhận", exact: true });
  await composer.fill("Hãy đối soát ba nguồn doanh thu quý III/2026. "
    + "Dùng nguồn A là sổ doanh thu nội bộ làm tham chiếu, đối chiếu A với B và A với C.");
  const accepted = page.waitForResponse(response =>
    response.url().endsWith("/api/assistant/messages") && response.request().method() === "POST");
  await send.click();
  const { job_id: jobId } = await (await accepted).json();
  let workflowId = "";
  await expect.poll(async () => {
    const job = await (await page.request.get(`/api/jobs/${jobId}`)).json();
    workflowId = job.result?.workflow_id || "";
    return workflowId;
  }, { timeout: 40000 }).not.toBe("");
  const current = async () => (await (await page.request.get(`/api/agent/workflows/${workflowId}`)).json());

  const first = reviews.filter({ hasText: sources[1].name });
  await expect(first.getByText("Dữ kiện đã kiểm tra", { exact: true })).toBeVisible({ timeout: 45000 });
  await expect(first).toContainText("Phiên bản nguồn 1");
  await expect(first).toContainText("quan sát được từ");
  const firstRecord = (await current()).detail.reviews.find((review: { state: string }) => review.state === "OPEN");
  expect(firstRecord.source_evidence).toHaveLength(2);
  expect(firstRecord.source_evidence.every((item: { uploaded_at: string; observed_dates: unknown[] }) =>
    !!item.uploaded_at && item.observed_dates.length === 1)).toBe(true);
  expect(firstRecord.planning_request.left.snapshot_at).toBeNull();
  expect(firstRecord.planning_request.right.completeness).toBeNull();

  await composer.fill("Hãy tự kiểm tra dữ liệu hiện hành.");
  await send.click();
  const verifiedCopy = "Đã kiểm tra lại bản chuẩn hóa. Xem dữ kiện trên thẻ đang chờ.";
  await expect(page.getByText(verifiedCopy, { exact: true })).toHaveCount(1);
  await first.getByRole("button", { name: "Bổ sung bằng tiếng Việt", exact: true }).click();
  await expect(page.getByRole("button", { name: "Hủy trả lời xác nhận", exact: true })).toBeVisible();
  await composer.fill("Hãy tự kiểm tra dữ liệu hiện hành.");
  await send.click();
  await expect(page.getByText(verifiedCopy, { exact: true })).toHaveCount(2);
  expect((await current()).detail.model_calls).toBe(1);
  await first.getByLabel("Múi giờ đối soát", { exact: true }).selectOption("Asia/Ho_Chi_Minh");
  for (const source of sources.slice(0, 2)) {
    await first.getByLabel(`Thời điểm nghiệp vụ chốt nguồn ${source.name} (UTC)`, { exact: true }).fill("2026-10-02T04:00");
    await first.getByLabel(`Mức độ đầy đủ của ${source.name}`, { exact: true }).selectOption("CONFIRMED");
  }
  await first.getByRole("button", { name: "Kiểm tra phạm vi và tìm khóa", exact: true }).click();

  const next = reviews.filter({ hasText: sources[2].name });
  await expect(next.getByText("Dữ kiện đã kiểm tra", { exact: true })).toBeVisible({ timeout: 30000 });
  await expect(next).toContainText("2.999 dòng dùng được");
  await expect(next).toContainText("1 dòng đã loại");
  await expect(next).toContainText("USD");
  await expect(next).toContainText("Chưa xác định được một phần số tiền đã loại.");
  await expect(next.getByLabel(`Thời điểm nghiệp vụ chốt nguồn ${sources[0].name} (UTC)`, { exact: true })).toHaveCount(0);
  await expect(next.getByLabel("Múi giờ đối soát", { exact: true })).toHaveCount(0);
  const pendingC = (await current()).detail.reviews.find((review: { state: string; scope_check_pending?: boolean }) =>
    review.state === "OPEN" && review.scope_check_pending);
  expect(pendingC.planning_request.left.snapshot_at).toBe("2026-10-02T04:00:00Z");
  const evidenceC = pendingC.source_evidence.find((item: { canonical_id: string }) => item.canonical_id === sources[2].canonical);
  expect(evidenceC).toMatchObject({ valid_rows: 2999, excluded_rows: 1, excluded_amounts: [], excluded_amounts_unavailable: true });
  expect(evidenceC.observed_dates).toEqual([{ field: "event_date", first: "2026-07-02", last: "2026-08-26" }]);
  await next.getByLabel(`Thời điểm nghiệp vụ chốt nguồn ${sources[2].name} (UTC)`, { exact: true }).fill("2026-10-03T04:00");
  await next.getByLabel(`Mức độ đầy đủ của ${sources[2].name}`, { exact: true }).selectOption("UNKNOWN");
  await next.getByLabel("Đề xuất đối soát một phần trên dữ liệu dùng được.", { exact: true }).check();
  await next.getByRole("button", { name: "Kiểm tra phạm vi và tìm khóa", exact: true }).click();
  await expect.poll(async () => (await current()).detail.reviews.filter((review: { state: string; plan: unknown; planning_candidates: unknown[] }) =>
    review.state === "OPEN" && (review.plan || review.planning_candidates.length)).length, { timeout: 30000 }).toBe(2);
  await page.reload();
  await expect(reviews).toHaveCount(2);
  const result = await current();
  expect(result.state).toBe("WAITING_REVIEW");
  const plans = result.detail.reviews.filter((review: { state: string }) => review.state === "OPEN")
    .map((review: { plan: unknown; planning_candidates: { plan: unknown }[] }) => review.plan || review.planning_candidates[0].plan);
  expect(plans.map((plan: { left: { canonical_id: string }; right: { canonical_id: string } }) =>
    [plan.left.canonical_id, plan.right.canonical_id])).toEqual([
      [sources[0].canonical, sources[1].canonical], [sources[0].canonical, sources[2].canonical],
    ]);
  expect(plans[1]).toMatchObject({ allow_partial: true, right: { completeness: "UNKNOWN" } });
  const jobs = (await (await page.request.get(`/api/jobs?project_id=${project}`)).json()).items;
  expect(jobs.filter((job: { kind: string }) => job.kind === "reconcile")).toHaveLength(0);
  expect(result.detail.model_calls).toBe(1);
  await page.screenshot({ path: "../runtime/agent-source-scope/two-proposals.png" });
  await writeFile("../runtime/agent-source-scope/chromium-result.json", JSON.stringify({
    project, workflowId, sources: sources.map(source => source.name),
    proposals: plans.length, modelCalls: result.detail.model_calls, reconcileJobs: 0, evidenceC,
  }, null, 2));
});
