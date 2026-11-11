import { test } from "./project-selection";
import {expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';

test("[MOCK CONTRACT] report history stays in place and clears denied conversation pages", async ({ page }) => {
  const context = { project_id: "history-project" };
  const title = "Hội thoại tổng hợp chỉ hiển thị khi có quyền";
  await page.addInitScript(() => localStorage.setItem("studio.project", "history-project"));
  await page.route("**/api/**", route => {
    const url = new URL(route.request().url());
    const fixtures = {
      "/api/session": { workspace_id: "synthetic", role: "owner" },
      "/api/settings": { workspace_name: "TEST", policy: { allow_external_ai: false } },
      "/api/projects/history-project": { id: context.project_id, name: "Dự án TEST", classification: "TEST", business_scope: "synthetic" },
    };
    if (url.pathname === "/api/conversations") {
      if (url.searchParams.has("before_id")) return route.fulfill({
        status: 403, json: { code: "FORBIDDEN", message_vi: "Quyền đã được thu hồi." },
      });
      return route.fulfill({ json: { items: [{
        id: "conversation-one", title, context, created_at: "2026-10-12T00:00:00Z", archived: false,
      }], has_more: true } });
    }
    return route.fulfill({ json: fixtures[url.pathname as keyof typeof fixtures] ?? { items: [], total: 0 } });
  });
  await page.goto("/#page=reports&project=history-project");
  await expect(page.getByRole("heading", { name: "Báo cáo đối soát" })).toBeVisible();
  const reportURL = page.url();
  await page.getByRole("button", { name: "Lịch sử", exact: true }).click();
  const modal = page.getByRole("dialog", { name: "Lịch sử", exact: true });
  await expect(modal.getByText(title)).toBeVisible();
  await expect(page).toHaveURL(reportURL);
  await modal.getByRole("button", { name: "Tải thêm hội thoại" }).click();
  await expect(modal.getByRole("alert")).toContainText("Quyền đã được thu hồi.");
  await expect(modal.getByText(title)).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(page).toHaveURL(reportURL);
});

for(const width of [390,768,1366,1440,1920]){
  test(`[MOCK CONTRACT] History loading, retry, scope and loaded search at ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:900});
    let state='error';
    let release:()=>void=()=>{};
    const gate=new Promise<void>(resolve=>release=resolve);
    const context={project_id:'history-project'};
    const conversation={id:'history-one',title:'Thu ngân ngày 12 — tổng hợp',context,created_at:'2026-10-12T00:00:00Z',archived:false};
    await page.addInitScript(()=>localStorage.setItem('studio.project','history-project'));
    await page.route('**/api/**',async route=>{
      const path=new URL(route.request().url()).pathname;
      if(route.request().method()!=='GET')throw new Error(`Unexpected history write: ${path}`);
      if(path==='/api/session')return route.fulfill({json:{workspace_id:'synthetic',role:'owner'}});
      if(path==='/api/settings')return route.fulfill({json:{workspace_name:'Synthetic',policy:{allow_external_ai:false},max_upload_bytes:20971520,agent_max_upload_files:5,agent_upload_extensions:['.csv','.xlsx']}});
      if(path==='/api/projects/history-project')return route.fulfill({json:{id:context.project_id,name:'Dự án thử nghiệm lịch sử',workspace_id:'synthetic',classification:'TEST',business_scope:'synthetic'}});
      if(path==='/api/conversations'){
        if(state==='loading')await gate;
        return state==='error'
        ?route.fulfill({status:503,json:{code:'SYNTHETIC_HISTORY_FAILURE',message_vi:'Lỗi kết nối tổng hợp để kiểm tra retry'}})
        :route.fulfill({json:{items:[conversation],has_more:false}});
      }
      if(path==='/api/conversations/history-one')return route.fulfill({json:{conversation,items:[],has_more:false}});
      return route.fulfill({json:{items:[],total:0,has_more:false}});
    });
    await page.goto('/#page=assistant');await expect(page.getByLabel('Câu hỏi cho AI Assistant',{exact:true})).toBeEnabled();
    if(width<900)await page.getByRole('button',{name:'Mở điều hướng',exact:true}).click();
    await page.locator('.sidebar').getByRole('button',{name:'Lịch sử',exact:true}).click();
    const dialog=page.getByRole('dialog',{name:'Lịch sử',exact:true});
    await expect(dialog).toContainText('Dự án thử nghiệm lịch sử');
    await expect(dialog.getByRole('alert')).toContainText('Không tải được lịch sử');
    await expect(dialog.getByText('Chưa có hội thoại trong dự án này.',{exact:true})).toHaveCount(0);
    state='loading';await dialog.getByRole('button',{name:'Tải lại lịch sử',exact:true}).click();
    await expect(dialog.locator('.busy')).toBeVisible();state='loaded';release();
    await expect(dialog.getByRole('button').filter({hasText:conversation.title})).toBeVisible();
    await dialog.getByLabel('Tìm trong hội thoại đã tải',{exact:true}).fill('không có trong dữ liệu');
    await expect(dialog).toContainText('Không có hội thoại phù hợp trong danh sách đã tải.');
    await dialog.getByLabel('Tìm trong hội thoại đã tải',{exact:true}).fill('Thu ngân');
    await dialog.getByRole('button').filter({hasText:conversation.title}).click();
    await expect(dialog).not.toBeVisible();
    await expect(page.getByLabel('Câu hỏi cho AI Assistant',{exact:true})).toBeEnabled();
    if(width<900)await page.getByRole('button',{name:'Mở điều hướng',exact:true}).click();
    await page.locator('.sidebar').getByRole('button',{name:'Lịch sử',exact:true}).click();
    await expect(dialog.locator('[aria-current=true]')).toContainText(conversation.title);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
    await mkdir('../runtime/demo-acceptance/history',{recursive:true});
    await page.screenshot({path:`../runtime/demo-acceptance/history/${width}.png`,fullPage:true});
  });
}

test('[MOCK CONTRACT] a failed user turn keeps the last visible workflow run after reload',async({page})=>{
  const project_id='history-project',run_id='verified-run',cid='saved-conversation';
  await page.addInitScript(()=>{localStorage.setItem('studio.project','history-project');localStorage.setItem('studio.conversation.history-project','saved-conversation');});
  await page.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(route.request().method()!=='GET')throw Error('Unexpected context write');
    if(path==='/api/session')return route.fulfill({json:{role:'owner',workspace_id:'synthetic'}});
    if(path==='/api/settings')return route.fulfill({json:{policy:{allow_external_ai:false}}});
    if(path==='/api/projects/history-project')return route.fulfill({json:{id:project_id,name:'Synthetic context',workspace_id:'synthetic',classification:'TEST'}});
    if(path===`/api/conversations/${cid}`)return route.fulfill({json:{conversation:{id:cid,context:{project_id},title:'Saved'},items:[{id:'completed',role:'assistant',created_at:'2026-11-02T00:00:00Z',context:{project_id,run_id},workflow_id:'visible-workflow'},{id:'failed',role:'user',text:'Yêu cầu thất bại đã lưu',created_at:'2026-11-02T00:01:00Z',context:{project_id},workflow_id:'unrendered-failed-workflow'}],has_more:false}});
    if(path==='/api/agent/workflows/visible-workflow')return route.fulfill({json:{id:'visible-workflow',context:{project_id,run_id},state:'COMPLETED',updated_at:'2026-11-02T00:01:00Z',detail:{steps:[],reviews:[],blocks:[],model_calls:0}}});
    return route.fulfill({json:{items:[],total:0,has_more:false}});
  });
  await page.goto('/#page=assistant');const chip=page.getByRole('button',{name:'Đổi ngữ cảnh phân tích',exact:true});await expect(chip).toHaveAttribute('data-run-id',run_id);await page.reload();await expect(chip).toHaveAttribute('data-run-id',run_id);
});
