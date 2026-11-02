import {test,expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';

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
    await page.goto('/');await expect(page.getByLabel('Câu hỏi cho AI Assistant',{exact:true})).toBeEnabled();
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
