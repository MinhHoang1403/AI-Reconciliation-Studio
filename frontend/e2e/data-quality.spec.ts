import { expect } from "@playwright/test";
import { test } from "./project-selection";

for (const [width, decision] of [[390, "REPLACE"], [1440, "REPLACE"], [390, "EXCLUDE"], [390, "KEEP_PENDING"]] as const) {
  test(`[MOCK CONTRACT] ${decision} keeps the exact Chat row at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const context = { project_id: "quality-project" };
    const createdAt = "2026-11-02T00:00:00Z";
    const conversation = { id: "quality-conversation", context, title: "Kiểm tra dữ liệu", created_at: createdAt };
    const issue = {
      field: "gross_amount", target_label: "Doanh thu gộp", source_label: decision === "EXCLUDE" ? null : "Gross amount",
      raw_value: "invalid", code: "INVALID_DECIMAL", editable: true,
    };
    const draft = { source_row_id: "row-id-12", field: issue.field, code: issue.code,
      value: "1250.25", reason: "Theo chứng từ", row_index: 0 };
    const block = { type: "dataset_summary", name: "Doanh thu thử nghiệm.csv", dataset_id: "quality-dataset",
      table_id: "quality-table", transformations: ["parse_decimal"], rows: 11 };
    let requests = 0;
    let finished = false;
    const reason = "Theo chứng từ";
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
        id: "quality-workflow", conversation_id: conversation.id, context, state: finished && decision === "REPLACE" ? "COMPLETED" : "PARTIAL",
        updated_at: finished ? "2026-11-02T00:00:01Z" : createdAt,
        detail: { intent: { intent: "PREPARE_NORMALIZATION" }, reviews: [], steps: [],
          blocks: [finished ? { ...block, canonical_id: "fixed", status: decision === "REPLACE" ? "READY" : "PARTIAL", invalid_rows: decision === "KEEP_PENDING" ? 1 : 0 } :
            { ...block, canonical_id: "initial", status: "PARTIAL", invalid_rows: 1, quality_draft: draft }],
        },
      } });
      if (path.endsWith("/quality-issues")) return route.fulfill({ json: {
        dataset: block.name, sheet: "CSV", current: true, total: finished && decision !== "KEEP_PENDING" ? 0 : 1,
        items: finished && decision !== "KEEP_PENDING" ? [] : [{ source_row_id: draft.source_row_id, source_row: 12, pending_reason: finished ? reason : null, issues: [issue] }],
        valid_records: finished && decision === "REPLACE" ? 11 : 10,
        invalid_records: finished && decision !== "KEEP_PENDING" ? 0 : 1,
        excluded_source_rows: finished && decision === "EXCLUDE" ? 1 : 0,
        excluded_amounts: [], excluded_amounts_unavailable: finished && decision === "EXCLUDE",
        decision_history: finished ? [{ source_row: 12, field: issue.source_label, original_value: issue.raw_value,
          replacement: decision === "REPLACE" ? draft.value : null, action: decision, reason, revision: 1 }] : [],
        latest_id: finished ? "fixed" : "initial", job: null,
      } });
      if (path.endsWith("/quality-decisions")) {
        requests++;
        expect(route.request().headers()["idempotency-key"]).toBeTruthy();
        expect(route.request().postDataJSON()).toEqual({
          canonical_id: "initial", source_row_id: "row-id-12", field: issue.field, code: issue.code,
          action: decision, replacement: decision === "REPLACE" ? "1250.25" : null, reason,
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
    await expect(page.getByRole("heading", { name: "Dòng nguồn 12 — Số tiền không hợp lệ" })).toBeVisible();
    if (decision === "EXCLUDE") {
      await expect(page.getByText("Nhiều cột nguồn", { exact: true })).toBeVisible();
      await expect(page.getByText("Trường đích Doanh thu gộp", { exact: true })).toBeVisible();
    }
    await expect(page.getByLabel("Giá trị đã kiểm tra")).toHaveValue("1250.25");
    expect(requests).toBe(0);
    await page.reload();
    await expect(page.getByLabel("Lý do")).toHaveValue("Theo chứng từ");
    if (decision !== "REPLACE") {
      await page.getByLabel("Lý do").press("Escape");
      const trigger = page.getByRole("button", { name: /Xử lý lỗi Doanh thu gộp · dòng 12/ });
      await trigger.press("Enter");
      await expect(page.getByLabel("Quyết định")).toBeFocused();
      await page.getByLabel("Lý do").press("Escape");
      await expect(trigger).toBeFocused();
      await trigger.press("Enter");
      await page.getByLabel("Quyết định").selectOption(decision);
      await page.getByLabel("Lý do").fill(reason);
    }
    const action = page.getByRole("button", { name: {
      REPLACE: "Xác nhận và kiểm tra lại", EXCLUDE: "Xác nhận loại trừ", KEEP_PENDING: "Xác nhận giữ để kiểm tra sau",
    }[decision] });
    await action.focus();
    await expect(action).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.keyboard.press("Enter");
    await expect(page.getByLabel("Quyết định")).toHaveCount(0);
    if (decision === "REPLACE") {
      await expect(page.getByText("Đã chuẩn hóa 11 dòng.", { exact: false })).toBeVisible();
      await page.getByText("Quyết định gần đây trong bản này", { exact: true }).click();
      await expect(page.getByText("Đã lưu chỉnh sửa", { exact: false })).toBeVisible();
    } else if (decision === "EXCLUDE") {
      await expect(page.getByRole("heading", { name: "Đã loại trừ khỏi phạm vi" })).toBeVisible();
      await expect(page.getByText("Chưa xác định được số tiền loại trừ.")).toBeVisible();
      await expect(page.getByText("Dòng 12 · Theo chứng từ")).toBeVisible();
    } else {
      await expect(page.getByText("Đã ghi nhận quyết định — Vẫn cần kiểm tra.")).toBeVisible();
      await expect(page.getByText("Đã ghi nhận quyết định giữ lại. Dòng vẫn cần kiểm tra.")).toBeVisible();
    }
    expect(requests).toBe(1);
  });
}
