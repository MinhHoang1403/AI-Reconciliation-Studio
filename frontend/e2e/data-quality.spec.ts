import { expect } from "@playwright/test";
import { test } from "./project-selection";

for (const width of [390, 1440]) {
  test(`quality correction keeps the exact Chat row at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const context = { project_id: "quality-project" };
    const createdAt = "2026-11-02T00:00:00Z";
    const conversation = { id: "quality-conversation", context, title: "Kiểm tra dữ liệu", created_at: createdAt };
    const issue = {
      field: "gross_amount", target_label: "Doanh thu gộp", source_label: "Gross amount",
      raw_value: "invalid", code: "INVALID_DECIMAL", editable: true,
    };
    const draft = { source_row_id: "row-id-12", field: issue.field, code: issue.code,
      value: "1250.25", reason: "Theo chứng từ", row_index: 0 };
    const block = { type: "dataset_summary", name: "Doanh thu thử nghiệm.csv", dataset_id: "quality-dataset",
      table_id: "quality-table", transformations: ["parse_decimal"], rows: 11 };
    let requests = 0;
    let finished = false;
    await page.addInitScript(() => {
      localStorage.setItem("studio.project", "quality-project");
      localStorage.setItem("studio.conversation.quality-project", "quality-conversation");
    });
    await page.route("**/api/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/session") return route.fulfill({ json: { workspace_id: "quality", actor_id: "owner", role: "owner" } });
      if (path === "/api/settings") return route.fulfill({ json: { workspace_name: "Kiểm thử", agent_cloud_enabled: false, policy: { allow_external_ai: false } } });
      if (path === "/api/projects/quality-project") return route.fulfill({ json: { id: context.project_id, name: "Kiểm tra", workspace_id: "quality", business_scope: "synthetic" } });
      if (path === "/api/conversations") return route.fulfill({ json: { items: [conversation], has_more: false } });
      if (path === "/api/conversations/quality-conversation") return route.fulfill({ json: { conversation, has_more: false, items: [{
        id: "message", job_id: "agent-job", role: "assistant", text: "", context, answer: null,
        workflow_id: "quality-workflow", created_at: createdAt,
      }] } });
      if (path === "/api/agent/workflows/quality-workflow") return route.fulfill({ json: {
        id: "quality-workflow", conversation_id: conversation.id, context, state: finished ? "COMPLETED" : "PARTIAL",
        updated_at: finished ? "2026-11-02T00:00:01Z" : createdAt,
        detail: { intent: { intent: "PREPARE_NORMALIZATION" }, reviews: [], steps: [],
          blocks: [finished ? { ...block, canonical_id: "fixed", status: "READY", invalid_rows: 0 } :
            { ...block, canonical_id: "initial", status: "PARTIAL", invalid_rows: 1, quality_draft: draft }],
        },
      } });
      if (path.endsWith("/quality-issues")) return route.fulfill({ json: {
        dataset: block.name, sheet: "CSV", current: !finished, total: finished ? 0 : 1,
        items: finished ? [] : [{ source_row_id: draft.source_row_id, source_row: 12, pending_reason: null, issues: [issue] }],
        valid_records: finished ? 11 : 10, invalid_records: finished ? 0 : 1, excluded_source_rows: 0,
        excluded_amounts: [], excluded_amounts_unavailable: false, decision_history: [],
        latest_id: finished ? "fixed" : "initial", job: null,
      } });
      if (path.endsWith("/quality-decisions")) {
        requests++;
        expect(route.request().headers()["idempotency-key"]).toBeTruthy();
        expect(route.request().postDataJSON()).toEqual({
          canonical_id: "initial", source_row_id: "row-id-12", field: issue.field, code: issue.code,
          action: "REPLACE", replacement: "1250.25", reason: "Theo chứng từ",
        });
        return route.fulfill({ status: 202, json: { job_id: "quality-normalization" } });
      }
      if (path === "/api/jobs/quality-normalization") {
        finished = true;
        return route.fulfill({ json: { id: "quality-normalization", status: "SUCCEEDED", result: { canonical_id: "fixed" } } });
      }
      return route.fulfill({ json: { items: [], total: 0 } });
    });
    await page.goto("/#page=assistant");
    await expect(page.getByRole("heading", { name: "Dòng nguồn 12 · 1 lỗi" })).toBeVisible();
    await expect(page.getByLabel("Giá trị đã kiểm tra")).toHaveValue("1250.25");
    expect(requests).toBe(0);
    await page.reload();
    await expect(page.getByLabel("Lý do")).toHaveValue("Theo chứng từ");
    const action = page.getByRole("button", { name: "Xác nhận và kiểm tra lại" });
    await action.focus();
    await expect(action).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `../runtime/data-foundation/chat-quality-${width}.png`, fullPage: true });
    await page.keyboard.press("Enter");
    await expect(page.getByText("Đã chuẩn hóa 11 dòng.", { exact: false })).toBeVisible();
    expect(requests).toBe(1);
  });
}
