import { expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { assistantPanel, openLegacyPage, selectProject, test } from "./project-selection";

test("semantic source reporting executes canonical SQL and exports the visible table", async ({ page }, info) => {
  const path = process.env.STUDIO_PROCESSING_REPORT_FIXTURE;
  test.skip(!path, "Requires the two isolated source fixture projects");
  test.setTimeout(120000);
  const { project, issueProject, workspace } = JSON.parse(await readFile(path!, "utf8"));
  await page.goto("/");
  if ((await (await page.request.get("/api/session")).json()).workspace_id !== workspace) {
    await page.getByRole("button", { name: "Quản lý không gian làm việc", exact: true }).click();
    const picker = page.getByRole("dialog", { name: "Quản lý không gian làm việc", exact: true });
    await picker.getByLabel("Không gian có quyền truy cập").selectOption(workspace);
    await picker.getByRole("button", { name: "Chuyển không gian", exact: true }).click();
    await expect(picker).not.toBeVisible();
  }
  await selectProject(page, project);
  await page.getByRole("button", { name: "AI Assistant", exact: true }).click();
  await page.getByRole("button", { name: "Hội thoại mới", exact: true }).click();
  const start = (await (await page.request.get("/api/settings")).json()).gemini_requests_used;
  const input = page.getByRole("textbox", { name: "Câu hỏi cho AI Assistant", exact: true });
  const work = page.getByRole("region", { name: "Công việc của AI Assistant", exact: true }).last();
  const ask = async (question: string, expectedState = "COMPLETED") => {
    await input.fill(question);
    const pending = page.waitForResponse(r => r.url().endsWith("/api/assistant/messages") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
    const response = await pending;
    expect(response.ok()).toBe(true);
    const { job_id } = await response.json();
    let flow;
    await expect.poll(async () => {
      const job = await (await page.request.get(`/api/jobs/${job_id}`)).json();
      if (job.result?.workflow_id) flow = await (await page.request.get(`/api/agent/workflows/${job.result.workflow_id}`)).json();
      return flow?.state;
    }).toBe(expectedState);
    const detail = flow!.detail;
    expect(detail.model_calls).toBe(0);
    if (expectedState === "COMPLETED") expect(detail.reviews).toEqual([]);
    return detail.blocks;
  };
  const ledger = await ask("Cho tôi biết tổng số tiền của bộ dữ liệu sổ kế toán.");
  expect(ledger[0].result.rows[0].sum_decimal_net_revenue_excluding_vat_0).toBe("30959967000.00");
  await expect(work.getByText("30.959.967.000 VND", { exact: true })).toBeVisible();
  await expect(work).toContainText("của Kế toán là");
  await expect(work).toContainText("01–31/10/2026");
  await expect(work.locator(".agent-table .notice.warning")).toHaveCount(0);
  const table = work.getByRole("region", { name: "Kết quả truy vấn", exact: true });
  const hint = table.locator(".notice-transient").filter({ hasText: "Bằng chứng hiển thị có giới hạn" });
  await expect(hint).toBeVisible();
  await expect(hint).toHaveCSS("animation-delay", "5s");
  const tableHeight = (await table.boundingBox())!.height;
  const hintHeight = (await hint.boundingBox())!.height;
  const composerTop = (await input.boundingBox())!.y;
  await page.screenshot({ path: info.outputPath("source-result-hint.png") });
  await expect(hint).toHaveCount(0, { timeout: 6500 });
  expect(tableHeight - (await table.boundingBox())!.height).toBeGreaterThanOrEqual(hintHeight);
  expect((await input.boundingBox())!.y).toBe(composerTop);
  await expect(work.getByText("Độ đầy đủ của kỳ chưa được xác nhận.", { exact: true })).toBeVisible();
  await work.getByText("Điều kiện và nguồn", { exact: true }).click();
  await expect(work.getByText("Bằng chứng hiển thị có giới hạn.", { exact: false }).last()).toBeVisible();
  await work.getByText("Điều kiện và nguồn", { exact: true }).click();
  await work.getByText("Xem truy vấn", { exact: true }).click();
  await expect(work).toContainText('SUM("net_revenue_excluding_vat")');
  await page.screenshot({ path: info.outputPath("source-total.png") });
  await ask("Còn Bán hàng?");
  const pair = await ask("Hai nguồn chênh nhau bao nhiêu?");
  expect(pair[0].text).toContain("Các tổng tiền bằng nhau");
  const october = await ask("Chỉ lấy tháng 10.");
  expect(october).toHaveLength(2);
  expect(october[0].result.query.filters[0].value).toEqual(["2026-10-01", "2026-11-01"]);
  const twoDaily = await ask("Hiển thị theo từng ngày.");
  expect(twoDaily.map((b: { result: { total_count: number } }) => b.result.total_count)).toEqual([31, 31]);
  const sales = await ask("Tổng số tiền của bộ dữ liệu báo cáo bán hàng.");
  expect(sales[0].result.source_evidence.source_name).toBe("01_bao_cao_ban_hang_5000.csv");
  const totals = await ask("Tổng doanh thu thuần chưa VAT của từng nguồn trong dự án hiện tại.");
  expect(totals).toHaveLength(3);
  expect(totals.every((b: { result: { rows: Record<string, string>[] } }) => b.result.rows[0].sum_decimal_net_revenue_excluding_vat_0 === "30959967000.00")).toBe(true);
  const compared = await ask("Ba nguồn có tổng tiền bằng nhau không?");
  expect(compared[0].text).toContain("Các tổng tiền bằng nhau");
  const distinct = await ask("Có bao nhiêu mã đơn duy nhất trong Bán hàng?");
  expect(distinct[0].result.rows[0].count_distinct_order_reference_0).toBe(5000);
  const daily = await ask("Doanh thu Bán hàng theo từng ngày tháng 10/2026.");
  expect(daily[0].result.total_count).toBe(31);
  const dailyValue = work.getByRole("cell", { name: "1.075.744.000", exact: true });
  await expect(dailyValue).toBeVisible();
  await expect(dailyValue).toHaveCSS("text-align", "end");
  const top = await ask("Hiển thị 10 đơn hàng doanh thu cao nhất.");
  expect(top[0].result.rows).toHaveLength(10);
  expect(top[0].result.total_count).toBe(10);
  const oraclePath = process.env.STUDIO_SOURCE_ORACLE;
  if (oraclePath) {
    const oracle = JSON.parse(await readFile(oraclePath, "utf8"));
    const original = oracle.clean["01_bao_cao_ban_hang_5000.csv"];
    expect(top[0].result.rows.map((row: { order_reference: string }) => row.order_reference))
      .toEqual(original.top.map((row: string[]) => row[0]));
    for (const [half, start, end] of [["đầu", 1, 16], ["sau", 16, 32]] as const) {
      const totals = await ask("Tổng doanh thu Bán hàng trong nửa " + half + " tháng 10/2026.");
      const expected = Object.entries(original.days as Record<string, string>)
        .filter(([day]) => Number(day.slice(-2)) >= start && Number(day.slice(-2)) < end)
        .reduce((sum, [, value]) => sum + BigInt(value.split(".")[0]), 0n);
      expect(totals[0].result.rows[0].sum_decimal_net_revenue_excluding_vat_0)
        .toBe(String(expected) + ".00");
    }
    await ask("Tổng doanh thu Bán hàng tại chi nhánh Hà Nội.", "WAITING_REVIEW");
    await expect(work).toContainText("cột phù hợp để lọc theo chi nhánh");
    await expect(work.getByRole("region", { name: "Kết quả truy vấn" })).toHaveCount(0);
    await ask("Tổng doanh thu Bán hàng tháng 10/2026.");
  }
  const found = await ask("Tìm mã ORD2610-000001.");
  expect(found[0].result.rows[0].order_reference).toBe("ORD2610-000001");
  await expect(work.getByRole("button", { name: "Xem dòng gốc", exact: true }).first()).toBeVisible();
  const negative = await ask("Có những giao dịch doanh thu âm nào?");
  expect(negative[0].result.total_count).toBe(0);
  const narrowed = await ask("Chỉ lấy giao dịch từ 05/10/2026 đến hết 10/10/2026.");
  expect(narrowed[0].result.query.filters).toEqual([{ field_id: "event_date", op: "between", value: ["2026-10-05", "2026-10-11"] }]);
  const regroup = await ask("Tiếp tục nhóm kết quả này theo ngày.");
  expect(regroup[0].result.total_count).toBe(6);
  await ask("Xuất Excel cho bảng đang xem.");
  const link = work.getByRole("link", { name: "Tải bảng đang xem XLSX", exact: true });
  await expect(link).toBeVisible();
  const downloading = page.waitForEvent("download");
  await link.click();
  await (await downloading).saveAs(info.outputPath("daily.xlsx"));
  await page.reload();
  await expect(link).toBeVisible();
  await expect(work.locator(".notice-transient")).toHaveCount(0);
  await selectProject(page, issueProject);
  const issue = await ask("Tổng doanh thu thuần chưa VAT của từng nguồn trong dự án hiện tại.");
  expect(issue.map((b: {result: { rows: Record<string, string>[] } }) => b.result.rows[0].sum_decimal_net_revenue_excluding_vat_0))
    .toEqual(["30765657000.00", "30768000000.00", "30758520000.00"]);
  expect(issue.map((b: { result: { source_evidence: { quality_counts: Record<string, number> } } }) =>
    b.result.source_evidence.quality_counts)).toEqual(Array(3).fill({
      invalid_amount: 3, missing_amount: 2, invalid_date: 2,
      missing_key: 2, currency_mismatch: 2, other: 0,
    }));
  expect((await (await page.request.get("/api/settings")).json()).gemini_requests_used).toBe(start);
});

test("financial snapshot agrees in Chat, Reports and downloaded files", async ({ page }, info) => {
  const fixturePath = process.env.STUDIO_PROCESSING_REPORT_FIXTURE;
  const runPath = process.env.STUDIO_FINANCIAL_RUN_FIXTURE;
  test.skip(!fixturePath || !runPath, "Requires verified TEST runs and raw-file oracle");
  test.setTimeout(120000);
  const { workspace } = JSON.parse(await readFile(fixturePath!, "utf8"));
  const runs = JSON.parse(await readFile(runPath!, "utf8")) as { kind: string; run: string; project: string }[];
  await page.goto("/");
  if ((await (await page.request.get("/api/session")).json()).workspace_id !== workspace) {
    await page.getByRole("button", { name: "Quản lý không gian làm việc", exact: true }).click();
    const picker = page.getByRole("dialog", { name: "Quản lý không gian làm việc", exact: true });
    await picker.getByLabel("Không gian có quyền truy cập").selectOption(workspace);
    await picker.getByRole("button", { name: "Chuyển không gian", exact: true }).click();
    await expect(picker).not.toBeVisible();
  }
  const usage = async () => (await (await page.request.get("/api/settings")).json()).gemini_requests_used;
  const before = await usage();
  for (const item of [runs.find(r => r.kind === "clean")!, runs.find(r => r.kind === "issues")!]) {
    const snapshot = await (await page.request.get(`/api/runs/${item.run}/metrics`)).json();
    const sum = item.kind === "clean" ? "30.959.967.000" : "30.765.657.000";
    await selectProject(page, item.project);
    await openLegacyPage(page, "reports");
    await page.setViewportSize(item.kind === "clean" ? { width: 1440, height: 900 } : { width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: item.kind === "issues" ? "reduce" : "no-preference" });
    await page.goto(`/#page=reports&project=${item.project}&run_id=${item.run}`);
    const report = page.getByRole("region", { name: "Tổng quan tài chính", exact: true });
    await expect(report.getByRole("row", { name: /Tổng tiền đủ điều kiện/ })).toContainText(sum);
    const quality = page.getByText("Chất lượng và phạm vi", { exact: true });
    const overview = page.getByRole("region", { name: "Phạm vi lần đối soát" });
    const partialNotice = overview.locator(".notice-transient").filter({ hasText: "Kết quả đã xác minh một phần." });
    await expect(partialNotice).toBeVisible();
    await expect(partialNotice).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    const scopeButton = partialNotice.getByRole("button", { name: "Xem phạm vi và nhóm bị loại" });
    await scopeButton.focus();
    await expect(partialNotice).toHaveCSS("animation-play-state", "paused");
    await overview.scrollIntoViewIfNeeded();
    await overview.screenshot({ path: info.outputPath(`${item.kind}-overview-with-notice.png`) });
    const noticeHeight = (await partialNotice.boundingBox())!.height;
    const overviewHeight = (await overview.boundingBox())!.height;
    await scopeButton.press("Enter");
    await expect(quality).toBeFocused();
    const qualityDetails = quality.locator("..");
    await expect(qualityDetails).toContainText("Độ đầy đủ chưa được xác nhận");
    const kpiBox = await page.getByRole("region", { name: "Chỉ số đối soát" }).boundingBox();
    const qualityBox = await qualityDetails.boundingBox();
    const reportBox = await report.boundingBox();
    expect(reportBox!.y).toBeGreaterThanOrEqual(kpiBox!.y + kpiBox!.height - 1);
    expect(qualityBox!.y).toBeGreaterThanOrEqual(reportBox!.y + reportBox!.height - 1);
    await expect(partialNotice).toHaveCount(0, { timeout: 6500 });
    expect(overviewHeight - (await overview.boundingBox())!.height).toBeGreaterThan(noticeHeight);
    await expect(overview.getByText("Đã xác minh một phần", { exact: true })).toBeVisible();
    await expect(overview.getByLabel("Phạm vi chỉ số")).toBeVisible();
    await overview.scrollIntoViewIfNeeded();
    await overview.screenshot({ path: info.outputPath(`${item.kind}-overview-collapsed.png`) });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(() => innerWidth));
    await report.scrollIntoViewIfNeeded();
    await page.screenshot({ path: info.outputPath(`${item.kind}-financial.png`) });
    const format = item.kind === "clean" ? "CSV" : "XLSX";
    const queued = page.waitForResponse(r => r.url().includes("/exports?format=") && r.request().method() === "POST");
    await page.getByRole("button", { name: `Xuất ${format}`, exact: true }).click();
    const { job_id } = await (await queued).json();
    await expect.poll(async () => (await (await page.request.get(`/api/jobs/${job_id}`)).json()).status, { timeout: 45000 }).toBe("SUCCEEDED");
    const link = page.getByRole("link", { name: "Tải báo cáo", exact: true });
    await expect(link).toBeVisible();
    const download = page.waitForEvent("download");
    await link.click();
    await (await download).saveAs(info.outputPath(`financial-${item.kind}.${format.toLowerCase()}`));
    await page.goto(`/#page=assistant&project=${item.project}&run_id=${item.run}&from=reports`);
    const input = page.getByRole("textbox", { name: "Câu hỏi cho AI Assistant", exact: true });
    for (const goal of ["Tổng giá trị đối soát của Bán hàng với Thu ngân là bao nhiêu?",
      "Hai nguồn của lượt đối soát có tổng tiền là bao nhiêu?", "Tổng tiền của nhóm khớp và tổng chênh lệch là bao nhiêu?"]) {
      await input.fill(goal);
      const submitted = page.waitForResponse(r => r.url().endsWith("/api/assistant/messages") && r.request().method() === "POST");
      await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
      const { job_id: assistantJob } = await (await submitted).json();
      await expect.poll(async () => {
        const job = await (await page.request.get(`/api/jobs/${assistantJob}`)).json();
        if (!job.result?.workflow_id) return null;
        const flow = await (await page.request.get(`/api/agent/workflows/${job.result.workflow_id}`)).json();
        const facts = flow.detail.blocks.find((b: { type: string }) => b.type === "facts");
        return { state: flow.state, calls: flow.detail.model_calls, snapshot: facts?.result.run?.metric_snapshot?.id };
      }).toEqual({ state: "COMPLETED", calls: 0, snapshot: snapshot.id });
      await expect(page.getByRole("region", { name: "Tổng quan tài chính", exact: true }).last()).toContainText(sum);
    }
    if (item.kind === "clean") {
      const checks = [
        ["Tổng chênh lệch tuyệt đối của lượt đối soát trong nửa đầu tháng 10/2026", "một kỳ đối soát"],
        ["Tóm tắt kết quả đối soát tại chi nhánh Hà Nội", "chưa lọc được theo địa điểm"],
        ["Xuất báo cáo đối soát tháng trước thành Excel", "một kỳ đối soát"],
      ];
      for (const [goal, clarification] of checks) {
        await input.fill(goal);
        const submitted = page.waitForResponse(r => r.url().endsWith("/api/assistant/messages") && r.request().method() === "POST");
        await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
        const { job_id } = await (await submitted).json();
        await expect.poll(async () => {
          const job = await (await page.request.get(`/api/jobs/${job_id}`)).json();
          if (!job.result?.workflow_id) return null;
          const flow = await (await page.request.get(`/api/agent/workflows/${job.result.workflow_id}`)).json();
          const hasResult = flow.detail.blocks.some((b: { type: string }) =>
            ["facts", "table", "export"].includes(b.type));
          return { state: flow.state, calls: flow.detail.model_calls, hasResult };
        }).toEqual({ state: "WAITING_REVIEW", calls: 0, hasResult: false });
        await expect(page.getByText(new RegExp(clarification)).last()).toBeVisible();
      }
      await page.screenshot({ path: info.outputPath("run-scope-clarification.png") });
    }
  }
  expect(await usage()).toBe(before);
});

test("new schemas keep both calendar and branch restrictions through Chat and export", async ({ page }, info) => {
  const path = process.env.STUDIO_QUERY_RELIABILITY_FIXTURE;
  test.skip(!path, "Requires the isolated CSV/XLSX fixture and independent Decimal oracle");
  test.setTimeout(100000);
  const fixture = JSON.parse(await readFile(path!, "utf8"));
  await page.goto("/");
  await selectProject(page, fixture.project);
  await page.getByRole("button", { name: "AI Assistant", exact: true }).click();
  await page.getByRole("button", { name: "Hội thoại mới", exact: true }).click();
  const input = page.getByRole("textbox", { name: "Câu hỏi cho AI Assistant" });
  const result = page.getByRole("region", { name: "Công việc của AI Assistant" }).last();
  const receipts = [];
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  async function ask(goal: string, expected = "COMPLETED") {
    await input.fill(goal);
    const submitted = page.waitForResponse(r => r.url().endsWith("/api/assistant/messages") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
    const response = await submitted;
    const { job_id } = await response.json();
    let workflow;
    await expect.poll(async () => {
      const job = await (await page.request.get("/api/jobs/" + job_id)).json();
      if (job.result?.workflow_id) {
        workflow = await (await page.request.get("/api/agent/workflows/" + job.result.workflow_id)).json();
      }
      return workflow?.state;
    }).toBe(expected);
    expect(workflow!.detail.model_calls).toBe(0);
    const table = workflow!.detail.blocks.find((block: { type: string }) => block.type === "table")?.result;
    receipts.push({ goal, state: expected, job_id, query: table?.query, rows: table?.rows, sql: table?.source_evidence?.sql });
    return table;
  }
  const source = 'của "Luân chuyển kho.csv"';
  const measure = "doanh thu thuần chưa VAT";
  const period = "tháng 2/2024";
  const first = await ask('Tổng ' + measure + ' ' + source + ' tại chi nhánh "Hà Nội" trong nửa đầu ' + period + ' là bao nhiêu?');
  expect(first.rows[0].sum_decimal_recognized_0).toBe(fixture.oracle.hanoi_first);
  const second = await ask('Tổng ' + measure + ' ' + source + ' tại chi nhánh "Hà Nội" trong nửa sau ' + period);
  expect(second.rows[0].sum_decimal_recognized_0).toBe(fixture.oracle.hanoi_second);
  const changed = await ask('Còn chi nhánh "Đà Nẵng" thì sao?');
  expect(changed.rows[0].sum_decimal_recognized_0).toBe(fixture.oracle.danang_second);
  const exactValue = "X' OR '1'='1";
  const literal = await ask('Tổng ' + measure + ' ' + source + ' tại chi nhánh "' + exactValue + '"');
  expect(literal.rows[0].sum_decimal_recognized_0).toBe("6.00");
  expect(literal.source_evidence.sql).not.toContain(exactValue);
  await ask('Tổng số tiền ' + source, "WAITING_REVIEW");
  await expect(result.getByRole("region", { name: "Kết quả truy vấn" })).toHaveCount(0);
  await ask('Tổng ' + measure + ' của "Sổ ghi nhận độc lập.xlsx" tại chi nhánh "Hà Nội"', "WAITING_REVIEW");
  const february = await ask('Tổng ' + measure + ' ' + source + ' ' + period);
  expect(february.rows[0].sum_decimal_recognized_0).toBe(fixture.oracle.feb);
  const top = await ask("Cho tôi Top 5 nhưng giữ bộ lọc ngày trước đó.");
  expect(top.query.filters).toEqual(february.query.filters);
  expect(top.rows.map((row: Record<string, string>) => [row.order_reference, row.booked_on, row.recognized]))
    .toEqual(fixture.oracle.top5);
  const ties = await ask("Có bao nhiêu giao dịch đồng hạng tại vị trí thứ 5?");
  expect(ties.source_evidence.ranking_ties).toBe(fixture.oracle.tie_amount_count);
  await result.getByText("Điều kiện và nguồn", { exact: true }).click();
  await expect(result).toContainText("vị trí dòng nguồn");
  for (const width of [390, 768, 1440, 1920]) {
    await page.setViewportSize({ width, height: 920 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath("query-" + width + ".png") });
  }
  await ask("Xuất Excel cho bảng đang xem.");
  const download = page.waitForEvent("download");
  await result.getByRole("link", { name: "Tải bảng đang xem XLSX", exact: true }).click();
  await (await download).saveAs(info.outputPath("top5.xlsx"));
  await page.reload();
  await expect(result.getByRole("link", { name: "Tải bảng đang xem XLSX", exact: true })).toBeVisible();
  await writeFile(info.outputPath("query-receipts.json"), JSON.stringify(receipts, null, 2));
  expect(errors).toEqual([]);
});

test("observed reconciliation uses the requested pairs and retains evidence and exports", async ({ page }, info) => {
  const path = process.env.STUDIO_PROCESSING_REPORT_FIXTURE;
  test.skip(!path, "Requires the two isolated 5,000-row fixture projects");
  test.setTimeout(120000);
  const fixture = JSON.parse(await readFile(path!, "utf8")) as {
    project: string; issueProject: string; workspace: string;
  };
  const question = "Đối soát Bán hàng với Thu ngân, sau đó Thu ngân với Kế toán. "
    + "Sử dụng mã đơn hàng và doanh thu thuần chưa VAT bằng VND. "
    + "Chỉ kết luận trên dữ liệu quan sát được.";
  await page.goto("/");
  if ((await (await page.request.get("/api/session")).json()).workspace_id !== fixture.workspace) {
    await page.getByRole("button", { name: "Quản lý không gian làm việc", exact: true }).click();
    const picker = page.getByRole("dialog", { name: "Quản lý không gian làm việc", exact: true });
    await picker.getByLabel("Không gian có quyền truy cập").selectOption(fixture.workspace);
    await picker.getByRole("button", { name: "Chuyển không gian", exact: true }).click();
    await expect(picker).not.toBeVisible();
  }
  const usage = async () => (await (await page.request.get("/api/settings")).json()).gemini_requests_used;
  const before = await usage();
  const receipts = [];
  for (const [kind, project] of [["clean", fixture.project], ["issues", fixture.issueProject]]) {
    await selectProject(page, project);
    await page.getByRole("button", { name: "AI Assistant", exact: true }).click();
    await page.getByRole("button", { name: "Hội thoại mới", exact: true }).click();
    const input = page.getByRole("textbox", { name: "Câu hỏi cho AI Assistant", exact: true });
    await input.fill(question);
    const accepted = page.waitForResponse(response => response.url().endsWith("/api/assistant/messages")
      && response.request().method() === "POST");
    await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
    const { job_id } = await (await accepted).json();
    const work = page.getByRole("region", { name: "Công việc của AI Assistant", exact: true }).last();
    await expect(work.getByText("Đã đối soát hai cặp trên dữ liệu quan sát được.", { exact: true })).toBeVisible();
    const { result } = await (await page.request.get(`/api/jobs/${job_id}`)).json();
    const workflow = await (await page.request.get(`/api/agent/workflows/${result.workflow_id}`)).json();
    expect(workflow.state).toBe("COMPLETED");
    expect(workflow.detail.model_calls).toBe(0);
    expect(workflow.detail.reviews).toEqual([]);
    const pairs = ["Bán hàng ↔ Thu ngân", "Thu ngân ↔ Kế toán"];
    const facts = workflow.detail.blocks.filter((block: { type: string }) => block.type === "facts");
    expect(facts.map((block: { observation: { pair: string } }) => block.observation.pair)).toEqual(pairs);
    const expectations = kind === "clean"
      ? [[5000, 0, 0, 0, "0.00", "0.00"], [5000, 0, 0, 0, "0.00", "0.00"]]
      : [[4936, 12, 64, 6, "-60000.00", "60000.00"], [4908, 29, 83, 7, "-144000.00", "264000.00"]];
    for (const [index, pair] of pairs.entries()) {
      const [equal, mismatch, pending, duplicate, signed, absolute] = expectations[index];
      const block = facts[index];
      const run = block.result.run;
      expect(run.status).toBe("PARTIAL_VERIFIED");
      expect(run.checks.every((check: { passed: boolean }) => check.passed)).toBe(true);
      expect(run.metric_snapshot.comparison_counts.EQUAL).toBe(equal);
      expect(run.metric_snapshot.comparison_counts.AMOUNT_MISMATCH ?? 0).toBe(mismatch);
      expect(run.metric_snapshot.linkage_counts.PENDING ?? 0).toBe(pending);
      expect(block.observation.duplicate_keys).toBe(duplicate);
      expect(run.metric_snapshot.monetary[0]).toMatchObject({ signed_variance: signed, absolute_variance: absolute });
      const section = work.getByRole("region", { name: pair, exact: true });
      await expect(section.getByRole("row", { name: `Nhóm khớp ${Number(equal).toLocaleString("vi-VN")}` })).toBeVisible();
      await section.getByText("Phạm vi kiểm tra", { exact: true }).click();
      await expect(section).toContainText("Độ đầy đủ của kỳ kế toán chưa được xác nhận.");
      const scope = block.observation;
      expect([scope.observed_start, scope.observed_end]).toEqual(kind === "clean"
        ? ["2026-10-01", "2026-10-31"] : ["2026-11-01", "2026-11-12"]);
      const localDate = (value: string) => value.split("-").reverse().join("/");
      await expect(section).toContainText(`Từ ${localDate(scope.observed_start)} đến ${localDate(scope.observed_end)}.`);
      await expect(section).toContainText(`${kind === "clean" ? "5.000" : "4.989"} dòng dùng được trong phạm vi`);
    }
    await page.screenshot({ path: info.outputPath(`${kind}-observed.png`) });
    await work.getByRole("region", { name: pairs[0], exact: true })
      .getByRole("button", { name: "Xem giao dịch, bằng chứng và xuất báo cáo", exact: true }).click();
    const report = assistantPanel(page, "Chi tiết kết quả đã xác minh");
    await expect(report.getByLabel("Lần đối soát", { exact: true })).toHaveValue(facts[0].result.run.id);
    let mismatchKey: string | undefined;
    if (kind === "issues") {
      const result = await page.request.get(`/api/runs/${facts[0].result.run.id}/matches`, {
        params: { comparison: "AMOUNT_MISMATCH", limit: 25 },
      });
      expect(result.ok()).toBe(true);
      const mismatches = await result.json();
      expect(mismatches.total).toBe(12);
      mismatchKey = mismatches.items[0].key.join(" / ");
      await report.getByLabel("Tìm kiếm", { exact: true }).fill(mismatchKey!);
    }
    const groups = report.getByRole("table", { name: "Chi tiết đối soát", exact: true });
    const matchedRows = mismatchKey ? groups.getByRole("row").filter({ hasText: mismatchKey }) : groups;
    await matchedRows.getByRole("button", { name: "Xem bằng chứng", exact: true }).first().click();
    const evidence = assistantPanel(page, "Bằng chứng đối soát");
    await evidence.getByRole("button", { name: "Xem nguồn net_revenue_excluding_vat", exact: true }).first().click();
    await expect(evidence.getByRole("region", { name: "Chi tiết giá trị nguồn", exact: true })).toBeVisible();
    await evidence.getByRole("button", { name: "Đóng", exact: true }).click();
    const format = kind === "clean" ? "CSV" : "XLSX";
    const exporting = page.waitForResponse(response => response.url().includes("/exports?format=")
      && response.request().method() === "POST");
    await report.getByRole("button", { name: `Xuất ${format}`, exact: true }).click();
    const exportResponse = await exporting;
    expect(exportResponse.ok()).toBe(true);
    const exportJob = (await exportResponse.json()).job_id;
    await expect.poll(async () => (await (await page.request.get(`/api/jobs/${exportJob}`)).json()).status, {
      timeout: 45000,
    }).toBe("SUCCEEDED");
    const link = report.getByRole("link", { name: "Tải báo cáo", exact: true });
    await expect(link).toBeVisible();
    const downloaded = page.waitForEvent("download");
    await link.click();
    await (await downloaded).saveAs(info.outputPath(`${kind}.${format.toLowerCase()}`));
    await report.getByRole("button", { name: "Đóng", exact: true }).click();
    await page.reload();
    await expect(page.getByText(question, { exact: true })).toBeVisible();
    for (const pair of pairs) await expect(work.getByRole("region", { name: pair, exact: true })).toBeVisible();
    receipts.push({ kind, workflow: workflow.id, runs: facts.map((block: {result: {run: {id: string}}}) => block.result.run.id) });
  }
  expect(await usage()).toBe(before);
  await writeFile(info.outputPath("observed-receipts.json"), JSON.stringify(receipts, null, 2));
});

test("processing report reads current sources through the real website", async ({ page }, info) => {
  const fixture = process.env.STUDIO_PROCESSING_REPORT_FIXTURE;
  test.skip(!fixture, "Requires the isolated clean and issue fixture projects");
  test.setTimeout(120000);
  const { project, issueProject, workspace, names, pinned } = JSON.parse(await readFile(fixture!, "utf8")) as {
    project: string; issueProject: string; workspace: string; names: string[]; pinned: string;
  };
  await page.goto("/");
  const session = await (await page.request.get("/api/session")).json();
  if (session.workspace_id !== workspace) {
    await page.getByRole("button", { name: "Quản lý không gian làm việc", exact: true }).click();
    const picker = page.getByRole("dialog", { name: "Quản lý không gian làm việc", exact: true });
    await picker.getByLabel("Không gian có quyền truy cập").selectOption(workspace);
    await picker.getByRole("button", { name: "Chuyển không gian", exact: true }).click();
    await expect(picker).not.toBeVisible();
  }
  await selectProject(page, project);
  await page.goto(`/#page=data&project=${project}&dataset_id=${pinned}`);
  await expect(page.getByRole("heading", { name: names[2], exact: true })).toBeVisible();
  await page.getByRole("button", { name: "AI Assistant", exact: true }).click();
  await page.getByRole("button", { name: "Tệp đã tải", exact: true }).click();
  const sources = assistantPanel(page, "Tệp và dữ liệu");
  await sources.getByRole("button").filter({ hasText: names[2] }).first().click();
  await sources.getByRole("button", { name: "Hỏi riêng về tệp này", exact: true }).click();
  await expect(page.getByRole("button", { name: "Đổi ngữ cảnh phân tích", exact: true }))
    .toHaveAttribute("data-dataset-id", pinned);
  const composer = page.getByRole("textbox", { name: "Câu hỏi cho AI Assistant", exact: true });
  const send = page.getByRole("button", { name: "Gửi câu hỏi", exact: true });
  const work = page.getByRole("region", { name: "Công việc của AI Assistant", exact: true });
  const settings = async () => (await (await page.request.get("/api/settings")).json()).gemini_requests_used;
  const before = await settings();
  const ask = async (question: string, expectedDataset?: string) => {
    await composer.fill(question);
    const response = page.waitForResponse(r => r.url().endsWith("/api/assistant/messages") && r.request().method() === "POST");
    await send.click();
    const accepted = await response;
    expect(accepted.ok()).toBe(true);
    if (expectedDataset) expect(accepted.request().postDataJSON().context.dataset_id).toBe(expectedDataset);
    const { job_id } = await accepted.json();
    let workflowId = "";
    await expect.poll(async () => {
      const job = await (await page.request.get(`/api/jobs/${job_id}`)).json();
      workflowId = job.result?.workflow_id || "";
      return job.status;
    }).toBe("SUCCEEDED");
    await expect.poll(async () =>
      (await (await page.request.get(`/api/agent/workflows/${workflowId}`)).json()).state,
    ).toBe("COMPLETED");
    const workflow = await (await page.request.get(`/api/agent/workflows/${workflowId}`)).json();
    expect(workflow.detail.model_calls).toBe(0);
    expect(workflow.detail.reviews).toEqual([]);
    return { workflow, latest: work.last() };
  };
  const combined = "Ba nguồn trong dự án này đã tự chuẩn bị xong chưa? Mỗi nguồn có bao nhiêu dòng gốc, hợp lệ và lỗi?";
  for (const question of [
    combined,
    "Ba nguồn trong dự án này đã tự chuẩn bị xong chưa?",
    "Mỗi nguồn có bao nhiêu dòng gốc, hợp lệ và lỗi?",
  ]) {
    const { workflow, latest } = await ask(question, question === combined ? pinned : undefined);
    expect(workflow.detail.blocks[0].totals).toMatchObject({
      original_rows: 15000, valid_rows: 15000, invalid_rows: 0,
    });
    const report = latest.getByRole("region", { name: "Thống kê chuẩn bị dữ liệu", exact: true });
    await expect(report.getByRole("row", { name: /Tổng 15\.000 15\.000 0/ })).toBeVisible();
    for (const name of names) await expect(report.getByRole("rowheader", { name, exact: true })).toBeVisible();
  }
  const inventory = await ask("Liệt kê tất cả nguồn dữ liệu trong dự án này.");
  await expect(inventory.latest).toContainText("Dự án có 3 nguồn dữ liệu");
  for (const [question, index, kind] of [
    ["Cho mình xem 10 dòng dữ liệu gốc của Bán hàng.", 0, "RAW_PREVIEW"],
    ["Cho mình xem 10 dòng dữ liệu sau chuẩn hóa của Thu ngân.", 1, "CANONICAL"],
  ] as const) {
    const { workflow, latest } = await ask(question);
    const tables = workflow.detail.blocks.filter((b: {type: string}) => b.type === "table");
    expect(tables).toHaveLength(1);
    expect(tables[0].title).toContain(names[index]);
    expect(tables[0].result.source_kind).toBe(kind);
    expect(tables[0].result.rows).toHaveLength(10);
    await expect(latest.getByRole("region", { name: "Kết quả truy vấn" })).toBeVisible();
  }
  const compare = await ask("Hãy kiểm tra dòng 805 của Bán hàng trước và sau chuẩn hóa khác nhau thế nào?");
  expect(compare.workflow.detail.blocks[0]).toMatchObject({
    type: "source_comparison", name: names[0], row: 805, scope: "CANONICAL",
  });
  for (const [label, index] of [["Bán hàng", 0], ["Thu ngân", 1], ["Kế toán", 2]] as const) {
    const item = await ask(`${label} đã tự chuẩn bị xong chưa?`);
    expect(item.workflow.detail.blocks[0].items).toEqual([expect.objectContaining({
      name: names[index], original_rows: 5000, valid_rows: 5000, invalid_rows: 0,
    })]);
  }
  const reports = page.getByRole("region", { name: "Thống kê chuẩn bị dữ liệu", exact: true });
  await expect(reports).toHaveCount(6);
  await reports.first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath("processing-report.png") });
  const desktop = page.viewportSize()!;
  await page.setViewportSize({ width: 390, height: desktop.height });
  const scroll = reports.first().getByLabel("Số dòng theo nguồn", { exact: true });
  await scroll.focus();
  await expect(scroll).toBeFocused();
  await expect.poll(() => scroll.evaluate(element =>
    element.clientWidth < document.documentElement.clientWidth && element.scrollWidth > element.clientWidth,
  )).toBe(true);
  await reports.first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath("processing-report-mobile.png") });
  await page.setViewportSize(desktop);
  await page.reload();
  await expect(page.getByText(combined, { exact: true })).toBeVisible();
  await expect(reports).toHaveCount(6);
  await expect(page.getByText("Cần bạn bổ sung", { exact: true })).toHaveCount(0);

  await selectProject(page, issueProject);
  const bad = await ask(combined);
  expect(bad.workflow.detail.blocks[0].totals).toMatchObject({
    original_rows: 15000, valid_rows: 14967, invalid_rows: 33, excluded_rows: 0,
  });
  await ask("Mỗi nguồn có những lỗi gì?");
  const errors = await ask("Cho xem 10 dòng lỗi của từng nguồn.");
  expect(errors.workflow.detail.blocks).toHaveLength(3);
  expect(errors.workflow.detail.blocks.every((b: {show_issue_rows?: boolean}) => b.show_issue_rows)).toBe(true);
  const issueTables = errors.latest.getByRole("region", { name: "Dòng cần xử lý", exact: true });
  await expect(issueTables).toHaveCount(3);
  for (const section of await issueTables.all()) {
    await expect(section.getByRole("heading", { level: 5, name: /^Dòng nguồn \d+/ })).toHaveCount(10);
    await expect(section.getByText("Trang 1 / 2", { exact: true })).toBeVisible();
  }
  const invalid = await ask("Dòng 805 của Bán hàng trước và sau chuẩn hóa khác nhau thế nào?");
  expect(invalid.workflow.detail.blocks[0].fields).toEqual(expect.arrayContaining([
    expect.objectContaining({ original: "khong_ro", processed: null }),
  ]));
  const count = await ask("Có bao nhiêu dòng bị lỗi số tiền và ngày?");
  expect(count.workflow.detail.blocks.map((b: {text: string}) => b.text)).toEqual(
    expect.arrayContaining(names.map(name =>
      expect.stringMatching(new RegExp(`${name}.*7 dòng có lỗi số tiền hoặc ngày`)),
    )),
  );
  const foreign = await ask("Những dòng USD đang được xử lý thế nào?");
  expect(foreign.workflow.detail.blocks.every((b: {text: string}) => b.text.includes("2 dòng USD"))).toBe(true);
  const match = await ask("Đối soát Bán hàng với Thu ngân rồi Thu ngân với Kế toán trên phần dữ liệu đủ điều kiện.");
  const results = match.workflow.detail.blocks.filter((b: {type: string}) => b.type === "facts");
  expect(results.map((b: {result: {run: {status: string}}}) => b.result.run.status))
    .toEqual(["PARTIAL_VERIFIED", "PARTIAL_VERIFIED"]);
  expect(results.map((b: {result: {run: {metric_snapshot: unknown}}}) => b.result.run.metric_snapshot))
    .toEqual([
      expect.objectContaining({
        comparison_counts: expect.objectContaining({ EQUAL: 4936, AMOUNT_MISMATCH: 12 }),
        linkage_counts: expect.objectContaining({ PENDING: 64, INVALID: 22 }),
        monetary: [expect.objectContaining({ signed_variance: "-60000.00", absolute_variance: "60000.00" })],
      }),
      expect.objectContaining({
        comparison_counts: expect.objectContaining({ EQUAL: 4908, AMOUNT_MISMATCH: 29 }),
        linkage_counts: expect.objectContaining({ PENDING: 83, INVALID: 22 }),
        monetary: [expect.objectContaining({ signed_variance: "-144000.00", absolute_variance: "264000.00" })],
      }),
    ]);
  const afterRun = await ask(combined);
  expect(afterRun.workflow.detail.blocks[0].totals.invalid_rows).toBe(33);
  await selectProject(page, project);
  const returned = await ask(combined);
  expect(returned.workflow.detail.blocks[0].totals.valid_rows).toBe(15000);
  expect(await settings()).toBe(before);
});

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
  const send = page.getByRole("button", { name: "Gửi câu hỏi", exact: true });
  const reviews = page.getByRole("region", { name: "Quyết định cần xác nhận", exact: true });
  let workflowId = process.env.STUDIO_SOURCE_SCOPE_WORKFLOW || "";
  if (workflowId) {
    expect((await page.request.get("/api/session")).ok()).toBe(true);
    const stored = await (await page.request.get(`/api/agent/workflows/${workflowId}`)).json();
    expect(stored.context.project_id).toBe(project);
    await page.goto(`/#page=assistant&project=${project}&conversation=${stored.conversation_id}`);
  } else {
    const options = page.getByLabel("Tùy chọn hội thoại", { exact: true });
    await options.click();
    await page.getByLabel("Trợ lý cho tin nhắn mới", { exact: true }).selectOption("GEMINI");
    await options.click();
    await composer.fill("Hãy đối soát ba nguồn doanh thu quý III/2026. "
      + "Dùng nguồn A là sổ doanh thu nội bộ làm tham chiếu, đối chiếu A với B và A với C.");
    const accepted = page.waitForResponse(response =>
      response.url().endsWith("/api/assistant/messages") && response.request().method() === "POST");
    await send.click();
    const { job_id: jobId } = await (await accepted).json();
    await expect.poll(async () => {
      const job = await (await page.request.get(`/api/jobs/${jobId}`)).json();
      workflowId = job.result?.workflow_id || "";
      return workflowId;
    }, { timeout: 40000 }).not.toBe("");
  }
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

  if (!process.env.STUDIO_SOURCE_SCOPE_WORKFLOW) {
    await composer.fill("Hãy tự kiểm tra dữ liệu hiện hành.");
    await send.click();
    await expect(page.getByText("Đã kiểm tra lại bản chuẩn hóa. Xem dữ kiện trên thẻ đang chờ.", { exact: true })).toBeVisible();
    await first.getByRole("button", { name: "Bổ sung bằng tiếng Việt", exact: true }).click();
    await expect(page.getByRole("button", { name: "Hủy trả lời xác nhận", exact: true })).toBeVisible();
    await composer.fill("Hãy tự kiểm tra dữ liệu hiện hành.");
    const reply = page.waitForResponse(response =>
      response.url().endsWith("/replies") && response.request().method() === "POST");
    await send.click();
    const { job_id: inspectionJob } = await (await reply).json();
    await expect.poll(async () => {
      const job = await (await page.request.get(`/api/jobs/${inspectionJob}`)).json();
      return job.status;
    }).toBe("SUCCEEDED");
  }
  expect((await current()).detail.model_calls).toBe(1);
  await first.getByRole("combobox", { name: "Múi giờ đối soát", exact: true }).selectOption("Asia/Ho_Chi_Minh");
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
  await expect(next.getByRole("combobox", { name: "Múi giờ đối soát", exact: true })).toHaveCount(0);
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
