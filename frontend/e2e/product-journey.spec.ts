import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";

test("new project CSV/XLSX through verified exceptions, Assistant page, exports and reopening", async ({
  page,
}) => {
  test.setTimeout(180000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const marker = crypto.randomUUID();
  await page.goto("/");
  await expect(page.locator("#project-select")).toBeVisible();
  const quota = await (await page.request.get("/api/settings")).json();
  await page.getByRole("button", { name: "+ Tạo dự án", exact: true }).click();
  const create = page.getByRole("dialog", { name: "Tạo dự án", exact: true });
  await create
    .getByLabel("Tên dự án", { exact: true })
    .fill(`Hành trình tổng hợp ${marker.slice(0, 8)}`);
  await create
    .getByLabel("Phạm vi nghiệp vụ", { exact: true })
    .fill(`synthetic-product-journey-${marker}`);
  await create.getByRole("button", { name: "Tạo dự án", exact: true }).click();
  await expect(create).not.toBeVisible();
  const projectId = (await page
    .locator("#project-select")
    .getAttribute("data-project-id"))!;
  // This newly created, explicitly synthetic fixture is classified by its owner through the real UI.
  await page.locator("#project-select").click();
  await page.getByText("Phân loại dự án hiện tại", { exact: true }).click();
  await page.getByLabel("Nhóm dự án", { exact: true }).selectOption("TEST");
  await page
    .getByRole("button", { name: "Xác nhận phân loại", exact: true })
    .click();
  await expect(
    page.getByText(
      "Đã lưu phân loại. Dữ liệu và lịch sử vẫn được giữ nguyên.",
      { exact: true },
    ),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await mkdir("../runtime/product-journey", { recursive: true });
  const xlsxPath = "../runtime/product-journey/counterpart.xlsx";
  execFileSync("../.venv/Scripts/python.exe", [
    "-c",
    "import csv,sys;from openpyxl import Workbook;w=Workbook();s=w.active;s.title='Deliveries';[s.append(r) for r in csv.reader(open('../tests/fixtures/delivery-confirmations.csv',encoding='utf-8'))];w.save(sys.argv[1])",
    xlsxPath,
  ]);
  const names = [`reference-${marker}.csv`, `counterpart-${marker}.xlsx`];
  for (let i = 0; i < 2; i++) {
    await page
      .getByRole("button", { name: "Tải dữ liệu", exact: true })
      .click();
    const upload = page.getByRole("dialog", {
      name: "Tải nguồn dữ liệu",
      exact: true,
    });
    await upload.getByLabel("Chọn tệp dữ liệu").setInputFiles({
      name: names[i],
      mimeType: i
        ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        : "text/csv",
      buffer: await readFile(i ? xlsxPath : "../tests/fixtures/shipments.csv"),
    });
    await upload.getByText("Tùy chọn đọc nâng cao", { exact: true }).click();
    await upload.getByLabel("Dùng AI đề xuất ánh xạ trong hạn mức").uncheck();
    await upload
      .getByRole("button", { name: "Tải 1 tệp", exact: true })
      .click();
    await expect(upload).not.toBeVisible();
    await expect(
      page.getByRole("cell", { name: "000702", exact: true }),
    ).toBeVisible();
    await page.getByText("Thống kê dữ liệu nguồn", { exact: true }).click();
    await expect(page.locator(".profile-grid")).toContainText("tracking_id");
    await page
      .getByRole("tab", { name: "AI Smart Setup", exact: true })
      .click();
    await page.getByLabel("Loại dữ liệu", { exact: true }).fill("delivery");
    await page
      .getByLabel("Mỗi dòng đại diện cho điều gì?", { exact: true })
      .fill("shipment");
    for (const field of [
      "carrier",
      "tracking_id",
      "event_date",
      "delivery_charge",
      "currency",
      "description",
    ]) {
      const row = page.locator(".mapping-row").filter({
        has: page.getByLabel(`Trường đích ${field}`, { exact: true }),
      });
      await row.getByLabel(`Trường đích ${field}`, { exact: true }).fill(field);
      await row
        .getByLabel(`Kiểu ${field}`, { exact: true })
        .selectOption(
          field === "delivery_charge"
            ? "decimal"
            : field === "event_date"
              ? "date"
              : "string",
        );
      if (["carrier", "tracking_id"].includes(field))
        await row.getByLabel("Thành phần khóa", { exact: true }).check();
      if (field === "event_date") {
        await row
          .getByLabel("Định dạng ngày", { exact: true })
          .fill("%Y-%m-%d");
        await row
          .getByLabel("Múi giờ đã xác nhận", { exact: true })
          .fill("UTC");
      }
      if (field === "delivery_charge") {
        await row
          .getByLabel(`Locale ${field}`, { exact: true })
          .selectOption("en-US");
        await row
          .getByLabel(`Chỉ tiêu ${field}`, { exact: true })
          .fill("delivery_charge");
        await row
          .getByLabel(`Cơ sở ${field}`, { exact: true })
          .selectOption("gross");
        await row.getByLabel(`Tiền tệ ${field}`, { exact: true }).fill("VND");
        await row.getByLabel(`Đơn vị ${field}`, { exact: true }).fill("VND");
      }
    }
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
      .poll(
        async () =>
          (
            await (
              await page.request.get(
                `/api/projects/${projectId}/canonical-catalogue`,
              )
            ).json()
          ).items.length,
      )
      .toBe(i + 1);
    await page
      .getByRole("button", { name: "Cập nhật kết quả", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Xem kết quả", exact: false })
      .click();
    await expect(
      page.getByRole("cell", { name: i ? "10.00" : "12.75", exact: true }),
    ).toBeVisible();
  }
  const catalogue = (
    await (
      await page.request.get(`/api/projects/${projectId}/canonical-catalogue`)
    ).json()
  ).items;
  await page.getByRole("button", { name: "Đối soát", exact: true }).click();
  await page
    .getByLabel("Nguồn tham chiếu", { exact: true })
    .selectOption(
      catalogue.find((c: { name: string }) => c.name === names[0]).canonical.id,
    );
  await page
    .getByLabel("Nguồn đối ứng", { exact: true })
    .selectOption(
      catalogue.find((c: { name: string }) => c.name === names[1]).canonical.id,
    );
  await page.getByLabel("Từ ngày", { exact: true }).fill("2026-10-01");
  await page
    .getByLabel("Đến ngày (không gồm)", { exact: true })
    .fill("2026-11-01");
  await page.getByLabel("Múi giờ", { exact: true }).fill("UTC");
  for (const side of ["nguồn trái", "nguồn phải"]) {
    const scope = page.getByRole("group", {
      name: `Phạm vi ${side}`,
      exact: true,
    });
    await scope.getByLabel("Đầu kỳ nguồn", { exact: true }).fill("2026-10-01");
    await scope
      .getByLabel("Cuối kỳ nguồn (không gồm)", { exact: true })
      .fill("2026-11-01");
    await scope
      .getByRole("combobox", { name: "Độ đầy đủ", exact: true })
      .selectOption("CONFIRMED");
  }
  await page
    .getByLabel("Tôi xác nhận kỳ, múi giờ và phạm vi nguồn", { exact: true })
    .check();
  await page
    .getByRole("button", { name: "Kiểm tra điều kiện", exact: true })
    .click();
  await expect(
    page.getByText(
      "Đã kiểm tra schema, scope, grain, metric, thời gian và khóa. Trùng khóa được giữ để review.",
      { exact: true },
    ),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Lưu đề xuất thủ công", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "Xác nhận quy tắc và dấu số tiền",
      exact: true,
    })
    .click();
  const accepted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/reconciliation-runs") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Chạy đối soát đã duyệt", exact: true })
    .click();
  const runId = (await (await accepted).json()).run_id;
  await expect(page.locator(".run-toolbar .badge-verified")).toBeVisible();
  const snapshot = await (
    await page.request.get(`/api/runs/${runId}/metrics`)
  ).json();
  expect(snapshot.full_match_rate).toEqual({
    numerator: 1,
    denominator: 3,
    percent: "33.33",
  });
  expect(snapshot.monetary[0]).toMatchObject({
    absolute_variance: "2.75",
    signed_variance: "2.75",
    currency: "VND",
  });
  await page.getByRole("button", { name: "Ngoại lệ", exact: true }).click();
  const mismatch = page
    .getByRole("row")
    .filter({ hasText: "000702" })
    .filter({ hasText: "Lệch tiền" });
  await mismatch
    .getByRole("button", { name: "Xem ngoại lệ", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "12.75 − 10.00 = 2.75 VND",
  );
  await page.keyboard.press("Escape");
  await mismatch
    .getByRole("button", { name: "Hỏi vì sao lệch", exact: true })
    .click();
  await page
    .getByLabel("Câu hỏi cho Trợ lý", { exact: true })
    .fill("Vì sao lệch?");
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
  const answer = page.locator(".assistant-message.assistant").last();
  await expect(answer).toContainText("12.75 / 10.00 / 2.75 / 0 VND");
  await answer
    .getByRole("button", { name: "Xem bằng chứng", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Xem nguồn delivery_charge", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("region", { name: "Chi tiết giá trị nguồn", exact: true }),
  ).toContainText("12.75");
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(page.locator(".assistant-message.assistant")).toContainText(
    "2.75",
  );
  await page
    .getByRole("button", { name: "← Trở về trang trước", exact: true })
    .click();
  await expect(mismatch).toBeVisible();
  await page.getByRole("button", { name: "Báo cáo", exact: true }).click();
  const downloads: string[] = [];
  for (const format of ["CSV", "XLSX"]) {
    const response = page.waitForResponse(
      (r) =>
        /^\/api\/exports\/[^/]+$/.test(new URL(r.url()).pathname) &&
        r.request().method() === "GET",
    );
    await page
      .getByRole("button", { name: `Xuất ${format}`, exact: true })
      .click();
    const info = await (await response).json();
    await expect(
      page.getByRole("link", { name: "Tải báo cáo", exact: true }),
    ).toHaveAttribute("href", info.download_url);
    const download = page.waitForEvent("download");
    await page.getByRole("link", { name: "Tải báo cáo", exact: true }).click();
    const path = `../runtime/product-journey/report.${format.toLowerCase()}`;
    await (await download).saveAs(path);
    downloads.push(path);
  }
  const exported = JSON.parse(
    execFileSync(
      "../.venv/Scripts/python.exe",
      [
        "-c",
        "import csv,json,sys;from openpyxl import load_workbook;r=list(csv.reader(open(sys.argv[1],encoding='utf-8-sig')));a=json.loads(next(x[2] for x in r if x[:2]==['Summary','Snapshot JSON']));w=load_workbook(sys.argv[2],data_only=False);b=json.loads(next(r[1].value for r in w['Summary'] if r[0].value=='Snapshot JSON'));assert a==b;assert all(c.data_type!='f' for s in w for r in s for c in r);print(json.dumps(a))",
        ...downloads,
      ],
      { encoding: "utf8" },
    ),
  );
  expect(exported).toEqual(snapshot);
  expect(
    (await (await page.request.get("/api/settings")).json())
      .gemini_requests_used,
  ).toBe(quota.gemini_requests_used);
  const conversationId = await page.evaluate(
    (id) => localStorage.getItem(`studio.conversation.${id}`),
    projectId,
  );
  await writeFile(
    "../runtime/product-journey.json",
    JSON.stringify(
      { projectId, runId, conversationId, snapshot, downloads },
      null,
      2,
    ),
  );
  expect(errors).toEqual([]);
});
