import { expect, test, type Page } from "@playwright/test";

type Project = {
  id: string;
  name: string;
  business_scope: string;
  workspace_id: string;
};
const projects = (count: number): Project[] =>
  Array.from({ length: count }, (_, i) => ({
    id: `project-${String(i).padStart(3, "0")}`,
    name: "Đối soát đơn hàng",
    business_scope: `Kho miền Nam ${String(i).padStart(3, "0")}`,
    workspace_id: "synthetic",
  }));

/** Browser-only API contract fixtures never create production projects or jobs. */
async function fixture(page: Page, items: Project[], saved?: string) {
  await page.addInitScript((id) => {
    localStorage.clear();
    if (id) localStorage.setItem("studio.project", id);
  }, saved);
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (route.request().method() !== "GET")
      throw new Error(`Unexpected mutation: ${path}`);
    if (path === "/api/session")
      return route.fulfill({
        json: { workspace_id: "synthetic", role: "owner" },
      });
    if (path === "/api/settings")
      return route.fulfill({
        json: {
          workspace_name: "Synthetic",
          mapping_ai_provider: "GEMINI",
          policy: { allow_external_ai: false },
          max_upload_bytes: 20971520,
          max_upload_files: 10,
          max_rows: 100000,
        },
      });
    if (path === "/api/projects") {
      const search = (url.searchParams.get("search") || "").toLocaleLowerCase(
        "vi",
      );
      const matches = items.filter((p) =>
        `${p.name} ${p.business_scope}`
          .toLocaleLowerCase("vi")
          .includes(search),
      );
      const offset = Number(url.searchParams.get("offset") || 0);
      const limit = Number(url.searchParams.get("limit") || 50);
      return route.fulfill({
        json: {
          items: matches.slice(offset, offset + limit),
          total: matches.length,
        },
      });
    }
    if (/^\/api\/projects\/[^/]+$/.test(path)) {
      const project = items.find((p) => p.id === path.split("/").at(-1));
      return route.fulfill(
        project
          ? { json: project }
          : { status: 404, json: { code: "RESOURCE_NOT_FOUND" } },
      );
    }
    if (path.endsWith("/summary"))
      return route.fulfill({
        json: {
          dataset_count: 0,
          table_count: 0,
          mapping_review_count: 0,
          ready_canonical_count: 0,
          active_job_count: 0,
        },
      });
    return route.fulfill({ json: { items: [], total: 0 } });
  });
}

for (const count of [1, 10, 50, 120]) {
  test(`project picker: ${count} projects, bounded pagination and keyboard selection`, async ({
    page,
  }) => {
    const items = projects(count);
    await fixture(page, items);
    await page.goto("/");
    const trigger = page.locator("#project-select");
    await trigger.click();
    const search = page.getByRole("combobox", {
      name: "Tìm dự án",
      exact: true,
    });
    await expect(search).toBeFocused();
    await expect(page.getByRole("option")).toHaveCount(Math.min(20, count));
    if (count > 20) {
      await page
        .getByRole("button", { name: "Trang dự án sau", exact: true })
        .click();
      await expect(page.getByRole("option").first()).toContainText(
        "miền Nam 020",
      );
    }
    await search.fill(items.at(-1)!.business_scope.toLocaleUpperCase("vi"));
    await expect(page.getByRole("option")).toHaveCount(1);
    await search.press("ArrowDown");
    await search.press("Enter");
    await expect(trigger).toHaveAttribute("data-project-id", items.at(-1)!.id);
    await expect(trigger).toBeFocused();
    await trigger.click();
    await search.fill("không tồn tại");
    await expect(
      page.getByText("Không có dự án phù hợp.", { exact: false }),
    ).toBeVisible();
    await search.press("Escape");
    await expect(trigger).toBeFocused();
  });
}

test("restore saved off-page project; unavailable saved ID never silently selects another", async ({
  page,
}) => {
  const items = projects(120);
  await fixture(page, items, items[119].id);
  await page.goto("/");
  await expect(page.locator("#project-select")).toHaveAttribute(
    "data-project-id",
    items[119].id,
  );
  await page.reload();
  await expect(page.locator("#project-select")).toHaveAttribute(
    "data-project-id",
    items[119].id,
  );
  items.pop();
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("không còn tồn tại");
  await expect(page.locator("#project-select")).toHaveAttribute(
    "data-project-id",
    "",
  );
});

test("project search discards delayed results and exposes loading and retry errors", async ({
  page,
}) => {
  await fixture(page, projects(120));
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/projects?**", async (route) => {
    const search = new URL(route.request().url()).searchParams.get("search");
    if (search === "old") {
      await delayed;
      return route.fulfill({
        json: {
          items: [{ ...projects(1)[0], name: "Old response" }],
          total: 1,
        },
      });
    }
    if (search === "error")
      return route.fulfill({
        status: 503,
        json: { message_vi: "Không tải được dự án tổng hợp" },
      });
    return route.fallback();
  });
  await page.goto("/");
  await page.locator("#project-select").click();
  const search = page.getByRole("combobox", { name: "Tìm dự án", exact: true });
  const oldRequest = page.waitForRequest(
    (r) => new URL(r.url()).searchParams.get("search") === "old",
  );
  await search.fill("old");
  await expect(page.getByRole("listbox")).toHaveAttribute("aria-busy", "true");
  await oldRequest;
  await search.fill("miền Nam 119");
  await expect(page.getByRole("option")).toContainText("119");
  release();
  await expect(page.getByText("Old response")).toHaveCount(0);
  await search.fill("error");
  await expect(page.getByRole("alert")).toContainText("Không tải được");
  await expect(
    page.getByRole("button", { name: "Thử lại", exact: true }),
  ).toBeVisible();
});

const emptySummary = {
  dataset_count: 0,
  table_count: 0,
  mapping_review_count: 0,
  ready_canonical_count: 0,
  partial_canonical_count: 0,
  stale_canonical_count: 0,
  failed_canonical_count: 0,
  active_job_count: 0,
  latest_verified_run_id: null,
};

test("dashboard uses server totals, distinguishes PARTIAL and opens the exact off-page table errors", async ({
  page,
}) => {
  const items = projects(1);
  await fixture(page, items);
  const source = {
    id: "old-source",
    project_id: items[0].id,
    name: "synthetic-orders.csv",
    status: "PARTIAL",
    created_at: "2026-10-01",
  };
  const canonical = {
    id: "partial-canonical",
    source_table_id: "table-errors",
    mapping_revision_id: "approved",
    row_count: 4,
    valid_count: 2,
    invalid_count: 2,
    quality_status: "PARTIAL",
    stale: false,
  };
  const target = {
    kind: "REVIEW_DATA",
    dataset_id: source.id,
    table_id: canonical.source_table_id,
    canonical_id: canonical.id,
  };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/summary"))
      return route.fulfill({
        json: {
          ...emptySummary,
          dataset_count: 80,
          table_count: 81,
          partial_canonical_count: 1,
          stale_canonical_count: 2,
          preparation_action: target,
        },
      });
    if (path === "/api/datasets")
      return route.fulfill({
        json: {
          items: Array.from({ length: 25 }, (_, i) => ({
            ...source,
            id: `recent-${i}`,
            name: `Recent ${i}.csv`,
          })),
          total: 80,
        },
      });
    if (path === `/api/datasets/${source.id}`)
      return route.fulfill({ json: source });
    if (path.endsWith("/tables"))
      return route.fulfill({
        json: {
          items: [
            {
              id: "other-sheet",
              sheet: "Other",
              row_count: 4,
              parsed: { columns: [], warnings: [], header_row: 1 },
            },
            {
              id: "table-errors",
              sheet: "Errors sheet",
              row_count: 4,
              active_mapping_id: "approved",
              parsed: { columns: [], warnings: [], header_row: 1 },
            },
          ],
        },
      });
    if (path.endsWith("/artifacts"))
      return route.fulfill({ json: { canonical_datasets: [canonical] } });
    if (path.endsWith("/profile"))
      return route.fulfill({ json: { columns: [], row_count: 4 } });
    if (path.endsWith("/preview"))
      return route.fulfill({
        json: {
          view: "errors",
          columns: ["code", "raw_value"],
          total: 1,
          items: [{ code: "INVALID_DECIMAL", raw_value: "invalid" }],
        },
      });
    return route.fallback();
  });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: /^Dữ liệu\s*80$/ }),
  ).toBeVisible();
  const ready = page
    .locator(".stat-card")
    .filter({ hasText: "Kết quả sẵn sàng sử dụng" });
  await expect(ready.locator("strong")).toHaveText("0");
  await expect(ready).toContainText("1 cần kiểm tra · 2 đã cũ");
  await expect(
    page.locator(".stat-card").filter({ hasText: "Nguồn dữ liệu" }),
  ).toContainText("81 bảng / sheet");
  await page
    .getByRole("button", { name: "Kiểm tra lỗi dữ liệu", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: source.name })).toBeVisible();
  await expect(page.getByLabel("Bảng / sheet")).toHaveValue("table-errors");
  await expect(
    page.getByRole("button", { name: "Cảnh báo / lỗi", exact: true }),
  ).toHaveClass(/chosen/);
  await expect(
    page.getByRole("cell", { name: "invalid", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: "Dữ liệu cần kiểm tra" }),
  ).toContainText("2 / 4");
  expect(errors).toEqual([]);
});

test("project switch discards delayed old summary/data/error and clears the previous run", async ({
  page,
}) => {
  const items = projects(2);
  await fixture(page, items);
  let release!: () => void;
  const delay = new Promise<void>((resolve) => {
    release = resolve;
  });
  let started!: () => void;
  const loading = new Promise<void>((resolve) => {
    started = resolve;
  });
  await page.route("**/api/projects/*/summary", async (route) => {
    if (route.request().url().includes(items[0].id)) {
      started();
      await delay;
      return route.fulfill({
        status: 503,
        json: { message_vi: "Old project failure" },
      });
    }
    return route.fulfill({ json: { ...emptySummary, dataset_count: 80 } });
  });
  await page.goto("/");
  await loading;
  await expect(
    page.getByText("Đang tải dữ liệu dự án…", { exact: false }),
  ).toBeVisible();
  await expect(page.locator(".stat-card")).toHaveCount(0);
  await page.locator("#project-select").click();
  await page
    .getByRole("option")
    .filter({ hasText: items[1].business_scope })
    .click();
  await expect(page.locator(".stat-card").first().locator("strong")).toHaveText(
    "80",
  );
  release();
  await expect(page.getByText("Old project failure")).toHaveCount(0);
  await expect(page.locator("#project-select")).toHaveAttribute(
    "data-project-id",
    items[1].id,
  );
});

for (const kind of ["REVIEW_MAPPING", "NORMALIZE"] as const) {
  test(`next action ${kind} opens the matching table/tab without mutation`, async ({
    page,
  }) => {
    const items = projects(1);
    await fixture(page, items);
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/summary"))
        return route.fulfill({
          json: {
            ...emptySummary,
            dataset_count: 1,
            preparation_action: {
              kind,
              dataset_id: "source",
              table_id: "table",
              canonical_id: null,
            },
          },
        });
      const source = {
        id: "source",
        project_id: items[0].id,
        name: "Synthetic.csv",
        status: "PROFILED",
        created_at: "2026-10-01",
      };
      if (path === "/api/datasets/source")
        return route.fulfill({ json: source });
      if (path === "/api/datasets")
        return route.fulfill({ json: { items: [source], total: 1 } });
      if (path.endsWith("/tables"))
        return route.fulfill({
          json: {
            items: [
              {
                id: "table",
                sheet: "CSV",
                row_count: 1,
                parsed: { columns: [], warnings: [] },
              },
            ],
          },
        });
      if (path.endsWith("/profile"))
        return route.fulfill({ json: { columns: [], row_count: 1 } });
      if (path.endsWith("/artifacts"))
        return route.fulfill({ json: { canonical_datasets: [] } });
      return route.fallback();
    });
    await page.goto("/");
    await page
      .getByRole("button", {
        name:
          kind === "REVIEW_MAPPING" ? "Kiểm tra ánh xạ" : "Chuẩn hóa dữ liệu",
        exact: true,
      })
      .click();
    await expect(page.getByLabel("Bảng / sheet")).toHaveValue("table");
    await expect(
      page.getByRole("tab", {
        name: kind === "REVIEW_MAPPING" ? "AI Smart Setup" : "Chuẩn hóa",
        exact: true,
      }),
    ).toHaveAttribute("aria-selected", "true");
  });
}
