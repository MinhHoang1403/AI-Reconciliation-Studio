import { test } from "./project-selection";
import {expect} from "@playwright/test";
import {mkdir, readFile} from "node:fs/promises";
import {createHash} from "node:crypto";

test('[MOCK CONTRACT] single-source context can explicitly return to project data without a write',async({page})=>{
  const context={project_id:'scope-project',dataset_id:'scope-b'};
  const conversation={id:'scope-conversation',context,title:'Hội thoại của nguồn B',created_at:'2026-11-05T00:00:00Z',archived:false};
  const writes:string[]=[];
  await page.addInitScript(()=>{if(!sessionStorage.getItem('scope-fixture-initialized')){localStorage.setItem('studio.project','scope-project');localStorage.setItem('studio.conversation.scope-project','scope-conversation');sessionStorage.setItem('scope-fixture-initialized','1');}});
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(route.request().method()!=='GET')writes.push(path);
    if(path==='/api/session')return route.fulfill({json:{workspace_id:'test',actor_id:'reader',role:'owner'}});
    if(path==='/api/settings')return route.fulfill({json:{workspace_name:'TEST scope',agent_cloud_enabled:false,assistant_cloud_enabled:false,policy:{allow_external_ai:false}}});
    if(path==='/api/projects/scope-project')return route.fulfill({json:{id:context.project_id,name:'TEST scope',business_scope:'Synthetic',classification:'TEST'}});
    if(path==='/api/datasets/scope-b')return route.fulfill({json:{id:'scope-b',name:'Chứng từ B.xlsx',project_id:context.project_id}});
    if(path==='/api/conversations')return route.fulfill({json:{items:[conversation],has_more:false}});
    if(path==='/api/conversations/scope-conversation')return route.fulfill({json:{conversation,items:[],has_more:false}});
    return route.fulfill({json:{items:[],total:0,has_more:false}});
  });
  await page.goto('/#page=assistant&project=scope-project&dataset_id=scope-b');
  const input=page.getByLabel('Câu hỏi cho AI Assistant',{exact:true});await expect(input).toBeEnabled();
  await input.fill('Bản nháp riêng của nguồn B');
  await page.getByRole('button',{name:'Đổi ngữ cảnh phân tích',exact:true}).click();
  const modal=page.getByRole('dialog',{name:'Đổi ngữ cảnh phân tích',exact:true});await expect(modal).toContainText('Chứng từ B.xlsx');
  await modal.getByRole('button',{name:'Dùng dữ liệu của dự án',exact:true}).click();await expect(modal).toBeHidden();
  await expect(page).not.toHaveURL(/dataset_id=/);await expect(input).toHaveValue('');
  expect(await page.evaluate(()=>Object.values(sessionStorage).includes('Bản nháp riêng của nguồn B'))).toBe(true);
  await page.reload();await expect(input).toBeEnabled();await expect(page).not.toHaveURL(/dataset_id=/);
  expect(writes).toEqual([]);
});

test('[LOCAL] composer reflows an unchanged draft when the viewport narrows and widens',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setViewportSize({width:1440,height:900});await page.goto('/');
  const input=page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true});
  await expect(input).toBeEnabled();
  const draft='Bản nháp nghiệm thu: giữ nguyên mã và bằng chứng';
  await input.fill(draft);
  const wide=(await input.boundingBox())!.height;
  await page.setViewportSize({width:390,height:900});
  await expect.poll(()=>input.evaluate(el=>el.scrollHeight<=el.clientHeight)).toBe(true);
  expect((await input.boundingBox())!.height).toBeGreaterThan(wide);
  await expect(input).toHaveValue(draft);
  await expect(page.getByRole('button',{name:'Gửi câu hỏi',exact:true})).toBeInViewport();
  await mkdir('../runtime/assistant-conversation/after/390',{recursive:true});
  await page.screenshot({path:'../runtime/assistant-conversation/after/390/reflow.png'});
  await page.setViewportSize({width:1440,height:900});
  await expect.poll(async()=>(await input.boundingBox())!.height).toBe(wide);
  await input.fill('');
  expect(errors).toEqual([]);
});

for(const width of [390,768,1366,1440,1920]){
  test(`[MOCK CONTRACT] clarification is a conversation and keeps approval separate at ${width}px`,async({page})=>{
    const context={project_id:'clarification-project'};
    let state='WAITING_REVIEW',replied=false,posted=0,release:()=>void=()=>{};
    let gate=Promise.resolve();
    const query={project_id:context.project_id,source_kind:'VERIFIED_RUN',source_id:'verified-run',select_fields:['delta'],metric_id:'approved-amount',filters:[],sort:[],group_by:[],aggregations:[],offset:0,limit:25,currency_field:null,null_policy:'PRESERVE',result_scope:'ALL_MATCHING'};
    const intent={intent:'QUERY_DATA',query};
    const review={id:'clarification-review',kind:'CLARIFICATION',resource_id:'clarification-workflow',question:'Bạn muốn xem giá trị đơn hàng hay tiền thực nhận?',reason:'Hai chỉ tiêu đã được duyệt.',state:'OPEN',nonce:'b'.repeat(32),fingerprint:'a'.repeat(64),expires_at:'2099-01-01T00:00:00Z',normalization_draft:null,plan:null,planning_request:null,suggestions:null,reply_intent:null,reply_questions:[],pending_reply_job_id:null,expected_effects:[],options:[{id:'approved-amount',label:'Giá trị đơn hàng · gross · VND',intent}]};
    const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
    await page.setViewportSize({width,height:900});
    await page.addInitScript(()=>{localStorage.setItem('studio.project','clarification-project');localStorage.setItem('studio.conversation.clarification-project','clarification-conversation');});
    await page.route('**/api/**',async route=>{
      const path=new URL(route.request().url()).pathname;
      if(path==='/api/session')return route.fulfill({json:{workspace_id:'synthetic',actor_id:'clarification-reader',role:'owner'}});
      if(path==='/api/settings')return route.fulfill({json:{policy:{allow_external_ai:false}}});
      if(path===`/api/projects/${context.project_id}`)return route.fulfill({json:{id:context.project_id,name:'Synthetic clarification',business_scope:'synthetic',classification:'TEST'}});
      if(path==='/api/conversations/clarification-conversation')return route.fulfill({json:{conversation:{id:'clarification-conversation',title:'Clarification',context},items:[{id:'first-response',role:'assistant',context,workflow_id:'clarification-workflow',created_at:'2026-11-03T00:00:00Z'},...(replied?[{id:'reply-user',role:'user',text:'Xem chênh lệch theo giá trị đơn hàng',context,created_at:'2026-11-03T00:00:01Z'},{id:'reply-response',role:'assistant',context,workflow_id:'clarification-workflow',created_at:'2026-11-03T00:00:02Z'}]:[])],has_more:false}});
      if(path==='/api/agent/workflows/clarification-workflow')return route.fulfill({json:{id:'clarification-workflow',conversation_id:'clarification-conversation',context,state,updated_at:`${state}-${replied}`,detail:{steps:[],reviews:state==='WAITING_REVIEW'?[review]:[],blocks:state==='COMPLETED'?[{type:'progress',text:'Có 19 nhóm chênh lệch theo chỉ tiêu đã chọn.'}]:[{type:'progress',text:review.question}],model_calls:0}}});
      if(path.endsWith('/decisions')){posted++;expect(route.request().postDataJSON().decision).toEqual({type:'CLARIFICATION',intent});state='COMPLETED';return route.fulfill({json:{}});}
      if(path.endsWith('/replies')){posted++;expect(route.request().postDataJSON()).toMatchObject({review_id:review.id,nonce:review.nonce,fingerprint:review.fingerprint});await gate;replied=true;state='COMPLETED';return route.fulfill({status:202,json:{job_id:'clarification-reply-job'}});}
      if(path==='/api/jobs/clarification-reply-job')return route.fulfill({json:{id:'clarification-reply-job',status:'SUCCEEDED'}});
      if(route.request().method()!=='GET')throw Error('Unexpected clarification write '+path);
      return route.fulfill({json:{items:[],total:0,has_more:false}});
    });
    await page.goto('/');
    const card=page.getByRole('region',{name:'Câu hỏi bổ sung',exact:true});
    await expect(card).toBeVisible();await expect(page.getByText(review.question,{exact:true})).toHaveCount(1);
    await expect(card.getByRole('checkbox')).toHaveCount(0);await expect(card.getByText(/Xác nhận và tiếp tục|QUERY_FIELD_INVALID|QUERY_DATA/)).toHaveCount(0);
    await expect(card.getByText('hệ thống chưa phê duyệt thay bạn',{exact:false})).toHaveCount(0);
    await mkdir(`../runtime/assistant-conversation/after/${width}`,{recursive:true});
    await page.screenshot({path:`../runtime/assistant-conversation/after/${width}/clarification.png`});
    await card.getByRole('button',{name:'Giá trị đơn hàng · gross · VND',exact:true}).click();
    await expect(page.locator('.agent-workflow')).toContainText('19 nhóm chênh lệch');expect(posted).toBe(1);
    state='WAITING_REVIEW';await page.reload();await expect(card).toBeVisible();
    await card.getByRole('button',{name:'Trả lời bằng tiếng Việt',exact:true}).click();
    const input=page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true});await expect(input).toBeFocused();
    await input.fill('Xem chênh lệch theo giá trị đơn hàng');await page.reload();await expect(input).toHaveValue('Xem chênh lệch theo giá trị đơn hàng');
    await expect(page.locator('.review-reply-binding')).toContainText(review.question);
    gate=new Promise<void>(resolve=>release=resolve);
    const send=page.getByRole('button',{name:'Gửi câu hỏi',exact:true});const before=await send.boundingBox();
    await input.press('Enter');await send.dispatchEvent('click');
    await expect(send).toBeDisabled();await expect(send).toHaveText('');await expect(send.locator('svg')).toBeVisible();
    const during=await send.boundingBox();expect(during?.height).toBe(before?.height);expect(during?.width).toBe(before?.width);
    await page.screenshot({path:`../runtime/assistant-conversation/after/${width}/sending.png`});
    release();await expect(input).toBeEnabled();await expect(input).toHaveValue('');await expect(input).toBeFocused();
    await expect(page.locator('.agent-workflow')).toHaveCount(1);await expect(page.locator('.agent-workflow')).toContainText('19 nhóm chênh lệch');
    expect(posted).toBe(2);expect(errors).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  });
}

for(const width of [390,768,1366,1440,1920]) {
  test(`Compact composer and user settings at ${width}px [LOCAL]`,async({page})=>{
    const errors:string[]=[]; page.on('pageerror',e=>errors.push(e.message));
    const writes:string[]=[];page.on('request',r=>{if(!['GET','HEAD'].includes(r.method()))writes.push(r.url());});
    await page.setViewportSize({width,height:900}); await page.goto('/');
    const input=page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true});
    await expect(input).toBeEnabled();
    const form=page.locator('.assistant-composer');
    const send=form.getByRole('button',{name:'Gửi câu hỏi',exact:true});
    const box=await form.boundingBox();
    expect(box!.height).toBeLessThanOrEqual(64);
    const model=page.getByRole('combobox',{name:'Trợ lý cho tin nhắn mới',exact:true});
    await expect(model).not.toBeVisible();
    await page.getByLabel('Tùy chọn hội thoại',{exact:true}).click();
    await expect(model.locator('option')).toHaveText(['Gemini 3.5 Flash Lite','Qwen 3:8B']);
    await page.keyboard.press('Escape');
    await expect(model).not.toBeVisible();
    await expect(send).toHaveText('');await expect(send).toBeDisabled();
    await input.click();
    await expect(page.locator('.app-shell')).toHaveAttribute('data-focus-mode','pointer');
    expect(await form.evaluate(el=>getComputedStyle(el).borderTopWidth)).toBe('1px');
    expect(await form.evaluate(el=>getComputedStyle(el).outlineStyle)).toBe('none');
    expect(await form.evaluate(el=>getComputedStyle(el).boxShadow)).not.toContain('inset');
    expect(await input.evaluate(el=>getComputedStyle(el).outlineStyle)).toBe('none');
    const contrast=await input.evaluate(el=>{
      const luminance=(color:string)=>{const channels=(color.match(/[\d.]+/g)||[]).slice(0,3).map(Number).map(v=>{const n=v/255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4;});return channels[0]*.2126+channels[1]*.7152+channels[2]*.0722;};
      const background=luminance(getComputedStyle(el.closest('form')!).backgroundColor);
      const foreground=luminance(getComputedStyle(el,'::placeholder').color);
      return (Math.max(background,foreground)+.05)/(Math.min(background,foreground)+.05);
    });
    expect(contrast).toBeGreaterThanOrEqual(4.5);
    await mkdir(`../runtime/minimal-interface/focus/${width}`,{recursive:true});
    await page.screenshot({path:`../runtime/minimal-interface/focus/${width}/pointer.png`});
    await input.press('Shift+Tab');await page.keyboard.press('Tab');await expect(input).toBeFocused();
    await expect(page.locator('.app-shell')).toHaveAttribute('data-focus-mode','keyboard');
    expect(await input.evaluate(el=>getComputedStyle(el).outlineStyle)).toBe('none');
    expect(await form.evaluate(el=>getComputedStyle(el).outlineStyle)).toBe('none');
    await expect.poll(()=>form.evaluate(el=>getComputedStyle(el).boxShadow)).toContain('inset');
    await page.screenshot({path:`../runtime/minimal-interface/focus/${width}/keyboard.png`});
    await mkdir(`../runtime/ui-refinement/after/${width}`,{recursive:true});
    await page.screenshot({path:`../runtime/ui-refinement/after/${width}/keyboard.png`});
    await input.click();await expect(page.locator('.app-shell')).toHaveAttribute('data-focus-mode','pointer');
    expect(await form.evaluate(el=>getComputedStyle(el).boxShadow)).not.toContain('inset');
    await input.fill(Array.from({length:12},(_,i)=>`Dòng ${i+1}: giữ nguyên dữ liệu`).join('\n'));
    expect((await input.boundingBox())!.height).toBeLessThanOrEqual(180);
    expect((await input.boundingBox())!.height).toBeGreaterThan(100);
    await expect(send).toBeInViewport();await input.fill('');
    const name='Dữ liệu tổng hợp 000702.csv';
    await form.locator('input[type=file]').setInputFiles({name,mimeType:'text/csv',buffer:Buffer.from('id,amount\n000702,12.75\n')});
    await expect(form).toContainText(name);await expect(send).toBeEnabled();
    await form.getByRole('button',{name:`Bỏ ${name}`,exact:true}).click();await expect(send).toBeDisabled();
    if(width<900)await page.getByRole('button',{name:'Mở điều hướng',exact:true}).click();
    await page.locator('.sidebar').getByRole('button',{name:'Cài đặt',exact:true}).click();
    const settings=page.getByRole('region',{name:'Cài đặt',exact:true});
    const dto=await(await page.request.get('/api/settings')).json();
    await expect(settings.getByRole('heading',{name:'Tài khoản và không gian làm việc'})).toBeVisible();
    await expect(settings).toContainText(`${dto.agent_max_upload_files} tệp mỗi lần`);
    await expect(settings.getByRole('heading',{name:'AI và quyền riêng tư',exact:true})).toBeVisible();
    await expect(settings.getByText('Model Gemini',{exact:true})).not.toBeVisible();
    await page.screenshot({path:`../runtime/ui-refinement/after/${width}/settings-basic.png`,fullPage:true});
    await expect(settings.getByText('Thông tin nâng cao',{exact:true})).toHaveCount(0);
    await expect(settings).not.toContainText(/Gemini|Qwen|model|hạn mức chung|Lượt AI đã ghi nhận/i);
    await expect(settings.getByText(dto.gemini_model,{exact:true})).toHaveCount(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
    expect(errors).toEqual([]);expect(writes).toEqual([]);
  });
}

test('[MOCK CONTRACT] Settings uses user-facing availability, privacy and roles without operator diagnostics',async({page})=>{
  let scenario='allowed', role='owner';
  await page.route('**/api/**',route=>{
    if(route.request().method()!=='GET')throw new Error('Unexpected settings write');
    return route.fulfill({json:{items:[],total:0,has_more:false}});
  });
  await page.route('**/api/settings',route=>route.fulfill({json:{workspace_name:'Synthetic privacy',
    agent_cloud_enabled:['allowed','taskbudget'].includes(scenario),assistant_cloud_enabled:false,gemini_configured:scenario!=='key',
    gemini_requests_remaining:scenario==='budget'?0:7,gemini_requests_used:3,gemini_model:'synthetic-model',
    ai_task_allowances:{agent:{remaining:scenario==='taskbudget'?0:7}},
    mapping_ai_provider:'GEMINI',cloud_live_status:'NOT VERIFIED',max_upload_bytes:3145728,max_upload_files:4,
    agent_max_upload_files:2,agent_upload_extensions:['.csv','.xlsx'],max_rows:1234,
    policy:{mode:scenario==='local'?'LOCAL_ONLY':'CLOUD_ALLOWED',allow_external_ai:scenario!=='local',allow_cloud_parsing:false}}}));
  await page.route('**/api/session',route=>route.fulfill({json:{role,workspace_id:'synthetic',actor_id:'settings-reader'}}));
  for(const [next,expected] of [['allowed','Có thể yêu cầu AI hỗ trợ'],['key','AI tạm thời chưa thể hỗ trợ'],['budget','AI tạm thời chưa thể hỗ trợ'],['task','AI tạm thời chưa thể hỗ trợ'],['taskbudget','AI tạm thời chưa thể hỗ trợ'],['local','Xử lý trong ứng dụng']]){
    scenario=next;await page.goto('/#page=settings');await page.reload();
    const settings=page.locator('.settings-page');await expect(settings).toContainText(expected);
    await expect(settings).not.toContainText(/Thông tin nâng cao|Gemini|Qwen|synthetic-model|Chưa cấu hình|kết nối chưa xác minh|Lượt AI đã ghi nhận/);
    await expect(settings.getByRole('heading',{name:'AI và quyền riêng tư',exact:true})).toBeVisible();
    await expect(settings).toContainText('2 tệp mỗi lần');await expect(settings).toContainText('3 MB');
    if(next==='local')await expect(settings).toContainText('Không gửi dữ liệu đến dịch vụ AI bên ngoài');
    else await expect(settings).toContainText('Cho phép sử dụng dịch vụ AI bên ngoài');
  }
  for(const [nextRole,title] of [['editor','Có thể chỉnh sửa'],['viewer','Chỉ xem']]){
    role=nextRole;await page.reload();await expect(page.locator('.settings-page')).toContainText(title);
    await expect(page.locator('.settings-page')).not.toContainText(/Thông tin nâng cao|Gemini|Qwen|synthetic-model/);
  }
  await expect(page.getByText('Thông tin nâng cao',{exact:true})).toHaveCount(0);
});

test('[LOCAL] Lost upload response survives refresh without a second bootstrap project',async({page})=>{
  await page.goto('/');await expect(page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true})).toBeEnabled();
  const original=await(await page.request.get('/api/settings')).json();
  const file={name:`Synthetic-upload-recovery-${crypto.randomUUID()}.csv`,mimeType:'text/csv',buffer:Buffer.from('id,amount\n000702,12.75\n')};
  const keys:string[]=[];const receipts:{project_id:string;items:{id:string}[]}[]=[];
  await page.route('**/api/agent/attachments',async route=>{
    keys.push(route.request().headers()['idempotency-key']);
    const response=await route.fetch();expect(response.status()).toBe(202);receipts.push(await response.json());
    if(keys.length===1)return route.abort('failed');
    return route.fulfill({response});
  });
  await page.locator('.assistant-composer input[type=file]').setInputFiles(file);
  await page.getByRole('button',{name:'Gửi câu hỏi',exact:true}).click();
  await expect(page.getByRole('alert')).toBeVisible();expect(receipts).toHaveLength(1);
  await page.reload();await expect(page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true})).toBeEnabled();
  await page.locator('.assistant-composer input[type=file]').setInputFiles(file);
  await page.getByRole('button',{name:'Gửi câu hỏi',exact:true}).click();
  await expect(page.locator('.agent-table')).toHaveCount(1);
  expect(receipts).toHaveLength(2);expect(keys[1]).toBe(keys[0]);
  expect(receipts[1].project_id).toBe(receipts[0].project_id);expect(receipts[1].items[0].id).toBe(receipts[0].items[0].id);
  const count=await(await page.request.get(`/api/datasets?project_id=${receipts[0].project_id}`)).json();expect(count.total).toBe(1);
  const classified=await page.request.patch(`/api/projects/${receipts[0].project_id}/classification`,{headers:{Origin:'http://127.0.0.1:18180'},data:{classification:'TEST',expected_classification:'UNKNOWN'}});expect(classified.status()).toBe(200);
  expect((await(await page.request.get('/api/settings')).json()).gemini_requests_used).toBe(original.gemini_requests_used);
});

test('[MOCK CONTRACT] IME composition does not submit a message',async({page})=>{
  let posts=0;await page.route('**/api/assistant/messages',route=>{posts++;return route.abort();});
  await page.goto('/');const input=page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true});
  await expect(input).toBeEnabled();await input.fill('Đối soát dữ liệu');
  await input.dispatchEvent('keydown',{key:'Enter',code:'Enter',isComposing:true,bubbles:true});
  await expect(input).toHaveValue('Đối soát dữ liệu');expect(posts).toBe(0);
});

test('[MOCK CONTRACT] Long chart categories remain readable on mobile with exact values',async({page})=>{
  const labels=Array.from({length:6},(_,i)=>`Nhóm ${i+1}: Chứng từ thanh toán cần kiểm tra và xác nhận dữ liệu`);
  const context={project_id:'long-chart-project'};
  await page.setViewportSize({width:390,height:900});
  await page.addInitScript(()=>{localStorage.setItem('studio.project','long-chart-project');localStorage.setItem('studio.conversation.long-chart-project','long-chart-conversation');});
  await page.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/session')return route.fulfill({json:{workspace_id:'synthetic',actor_id:'chart-reader',role:'viewer'}});
    if(path==='/api/settings')return route.fulfill({json:{policy:{allow_external_ai:false}}});
    if(path==='/api/projects/long-chart-project')return route.fulfill({json:{id:context.project_id,name:'Biểu đồ tổng hợp',business_scope:'synthetic',classification:'TEST'}});
    if(path==='/api/conversations/long-chart-conversation')return route.fulfill({json:{conversation:{id:'long-chart-conversation',title:'Biểu đồ tổng hợp',context},items:[{id:'chart-answer',role:'assistant',context,workflow_id:'long-chart-workflow',created_at:'2026-11-02T00:00:00Z'}],has_more:false}});
    if(path==='/api/agent/workflows/long-chart-workflow')return route.fulfill({json:{id:'long-chart-workflow',context,state:'COMPLETED',updated_at:'2026-11-02T00:00:00Z',detail:{intent:{intent:'CREATE_VISUALIZATION'},model_calls:0,steps:[],reviews:[],blocks:[{type:'chart',title:'Các nhóm chứng từ',unit:'VND',population:6,population_definition:'Toàn bộ nhóm tổng hợp',verification_status:'CANONICAL',completeness:'COMPLETE',points:labels.map((label,i)=>({label,value:i===0?'12.75':`${i+1}.00`})),source_refs:['synthetic-chart-ref']}]}}});
    return route.fulfill({json:{items:[],total:0,has_more:false}});
  });
  await page.goto('/');const chart=page.locator('.agent-chart .result-chart');await expect(chart.locator('svg')).toBeVisible();
  await mkdir('../runtime/ui-refinement',{recursive:true});await page.screenshot({path:'../runtime/ui-refinement/long-chart.png'});
  const text=await chart.locator('svg').textContent();
  for(const label of labels)expect(text!.replace(/\s/g,'')).toContain(label.replace(/\s/g,''));
  await expect(chart).toHaveAttribute('aria-label',/Các nhóm chứng từ.*12.75/);
  const scroll=page.getByRole('region',{name:'Các nhóm trong biểu đồ; cuộn để xem toàn bộ',exact:true});
  await scroll.focus();await page.keyboard.press('End');
  await expect.poll(()=>scroll.evaluate(el=>el.scrollTop)).toBeGreaterThan(0);
  await page.getByText('Giá trị chính xác và nguồn',{exact:true}).click();
  await expect(page.locator('.agent-chart')).toContainText('12.75 VND');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('[MOCK CONTRACT] identifiers resembling status enums remain exact source strings',async({page})=>{
  const context={project_id:'identifier-project'};
  await page.addInitScript(()=>{localStorage.setItem('studio.project','identifier-project');localStorage.setItem('studio.conversation.identifier-project','identifier-conversation');});
  await page.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/session')return route.fulfill({json:{workspace_id:'synthetic',actor_id:'identifier-reader',role:'owner'}});
    if(path==='/api/settings')return route.fulfill({json:{policy:{allow_external_ai:false}}});
    if(path==='/api/projects/identifier-project')return route.fulfill({json:{id:context.project_id,name:'Synthetic exact identifiers',business_scope:'synthetic',classification:'TEST'}});
    if(path==='/api/conversations/identifier-conversation')return route.fulfill({json:{conversation:{id:'identifier-conversation',context,title:'Exact identifiers'},items:[{id:'identifier-answer',role:'assistant',workflow_id:'identifier-workflow',context,created_at:'2026-11-03T00:00:00Z'}],has_more:false}});
    if(path==='/api/agent/workflows/identifier-workflow')return route.fulfill({json:{id:'identifier-workflow',context,state:'COMPLETED',updated_at:'2026-11-03T00:00:00Z',detail:{steps:[],reviews:[],blocks:[{type:'table',result:{query:{project_id:context.project_id,source_kind:'CANONICAL',source_id:'canonical',sort:[],filters:[]},fields:['transaction_id','state','amount'],field_labels:{transaction_id:'Mã giao dịch',state:'Vùng',amount:'Số tiền'},rows:[{transaction_id:'EQUAL',state:'OPEN',amount:'12.75'},{transaction_id:'000702',state:'PAID',amount:'0.00'}],total_count:2,input_count:2,offset:0,limit:25,truncated:false,evidence_complete:true,verification_status:'CANONICAL',warnings:[],source_refs:[]}}]}}});
    return route.fulfill({json:{items:[],total:0,has_more:false}});
  });
  await page.goto('/');const table=page.locator('.agent-table');
  for(const exact of ['EQUAL','OPEN','PAID','000702','12.75','0.00'])await expect(table.getByRole('cell',{name:exact,exact:true})).toBeVisible();
  await expect(table).not.toContainText('Khớp chính xác');
});

for(const width of [390,768,1366,1440,1920]){
  test(`Workspace navigation and history focus at ${width}px`,async({page})=>{
    const writes:string[]=[];page.on("request",r=>{if(!['GET','HEAD'].includes(r.method()))writes.push(r.url());});
    await page.setViewportSize({width,height:900});
    await page.goto('/');
    await expect(page.getByRole('heading',{name:'Bạn muốn xử lý dữ liệu gì?'})).toBeVisible();
    if(width<900)await page.getByRole('button',{name:'Mở điều hướng',exact:true}).click();
    const nav=page.locator('.sidebar');
    await expect(nav.locator('nav').getByRole('button')).toHaveText(['AI Assistant','Dữ liệu','Đối soát','Báo cáo','Lịch sử','Cài đặt']);
    if(width<900)await expect(nav.getByRole('button',{name:'Đóng điều hướng',exact:true})).toBeFocused();
    for(const name of ['Tổng quan','Ngoại lệ','Kết quả'])await expect(nav.getByRole('button',{name,exact:true})).toHaveCount(0);
    await mkdir('../runtime/assistant-experience',{recursive:true});
    await page.screenshot({path:`../runtime/assistant-experience/after-${width}.png`,fullPage:true});
    await nav.getByRole('button',{name:'Lịch sử',exact:true}).click();
    await expect(page.getByRole('dialog',{name:'Lịch sử',exact:true})).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(width<900?page.getByRole('button',{name:'Mở điều hướng',exact:true}):nav.getByRole('button',{name:'Lịch sử',exact:true})).toBeFocused();
    await expect(page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true})).toBeVisible();
    expect(writes).toEqual([]);
  });
}

test('[MOCK CONTRACT] composer Enter submits once, Shift+Enter preserves a newline',async({page})=>{
  let posted=0;
  await page.addInitScript(()=>{localStorage.setItem('studio.project','keyboard-project');});
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/session')return route.fulfill({json:{workspace_id:'mock',actor_id:'keyboard-owner',role:'owner'}});
    if(path==='/api/settings')return route.fulfill({json:{agent_cloud_enabled:false,assistant_cloud_enabled:false,policy:{allow_external_ai:false}}});
    if(path==='/api/projects/keyboard-project')return route.fulfill({json:{id:'keyboard-project',name:'Synthetic keyboard',workspace_id:'mock',business_scope:'synthetic',classification:'TEST'}});
    if(path==='/api/conversations'&&route.request().method()==='POST')return route.fulfill({json:{id:'keyboard-conversation',context:{project_id:'keyboard-project'},title:'Keyboard'}});
    if(path==='/api/conversations/keyboard-conversation')return route.fulfill({json:{conversation:{id:'keyboard-conversation',context:{project_id:'keyboard-project'},title:'Keyboard'},items:[],has_more:false}});
    if(path==='/api/assistant/messages'){posted++;return route.fulfill({status:202,json:{job_id:'keyboard-job'}});}
    if(path==='/api/jobs/keyboard-job')return route.fulfill({json:{id:'keyboard-job',status:'BLOCKED',error_code:'GEMINI_BUDGET_EXHAUSTED'}});
    if(route.request().method()!=='GET')throw Error('Unexpected write '+path);
    return route.fulfill({json:{items:[],total:0,has_more:false,dataset_count:0}});
  });
  await page.goto('/');
  const input=page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true});
  await expect(input).toBeEnabled();await input.fill('Tra cứu dữ liệu');await input.press('Shift+Enter');await input.press('x');
  await expect(input).toHaveValue('Tra cứu dữ liệu\nx');
  await input.press('Enter');await expect.poll(()=>posted).toBe(1);
  await expect(page.getByRole('alert')).toContainText('Lịch sử được giữ');
  expect(posted).toBe(1);
});

test('Chat files drawer previews and downloads original bytes without leaving conversation',async({page})=>{
  test.setTimeout(90000);
  await page.addInitScript(()=>{if(!sessionStorage.getItem('experience-started')){localStorage.clear();sessionStorage.clear();sessionStorage.setItem('experience-started','1');}});
  await page.goto('/');await expect(page.getByRole('heading',{name:'Bạn muốn xử lý dữ liệu gì?'})).toBeVisible();
  const before=await(await page.request.get('/api/settings')).json();
  const raw=Buffer.from('voucher,amount\n000701,25.00\n000702,12.75\n');const name=`Synthetic-source-${crypto.randomUUID()}.csv`;
  await page.locator('.assistant-composer input[type=file]').setInputFiles({name,mimeType:'text/csv',buffer:raw});
  const received=page.waitForResponse(r=>r.url().endsWith('/agent/attachments')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Gửi câu hỏi',exact:true}).click();const attachment=await(await received).json();
  await expect(page.locator('.agent-table')).toHaveCount(1);
  const classified=await page.request.patch(`/api/projects/${attachment.project_id}/classification`,{data:{classification:'TEST',expected_classification:'UNKNOWN'},headers:{Origin:'http://127.0.0.1:18180'}});expect(classified.status()).toBe(200);
  const input=page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true});await input.fill('Bản nháp cần giữ');
  const originalURL=page.url();await page.getByRole('button',{name:'Tệp đã tải',exact:true}).click();
  const drawer=page.getByRole('dialog',{name:'Tệp và dữ liệu',exact:true});await drawer.getByRole('button',{name:new RegExp(name)}).click();
  await expect(drawer.getByRole('table')).toContainText('000702');await expect(drawer.getByRole('table')).toContainText('12.75');
  const response=await page.request.get(`/api/datasets/${attachment.items[0].id}/download`);expect(response.status()).toBe(200);
  expect(createHash('sha256').update(await response.body()).digest('hex')).toBe(createHash('sha256').update(raw).digest('hex'));
  await expect(drawer.getByRole('link',{name:'Tải tệp gốc',exact:true})).toHaveAttribute('href',`/api/datasets/${attachment.items[0].id}/download`);
  await page.screenshot({path:test.info().outputPath('source-drawer.png'),fullPage:true});
  await page.keyboard.press('Escape');await expect(input).toHaveValue('Bản nháp cần giữ');expect(page.url()).toBe(originalURL);
  expect((await(await page.request.get('/api/settings')).json()).gemini_requests_used).toBe(before.gemini_requests_used);
});


async function deliveryFixture() {
  const s = JSON.parse(await readFile(
    process.env.STUDIO_RECONCILIATION_RECEIPT || "../runtime/reconciliation-acceptance.json", "utf8",
  ));
  return {
    project_id: s.project_id as string,
    run_id: s.runs.delivery.run_id as string,
    snapshot: s.runs.delivery.snapshot,
    sources: ["shipments.csv", "delivery-confirmations.csv"].map(name => ({
      id: s.sources[name].dataset_id as string, name,
    })),
  };
}

test('Persisted canonical and error previews stay inside the chat files drawer',async({page})=>{
  const s = await deliveryFixture();
  await page.addInitScript(id => localStorage.setItem("studio.project", id), s.project_id);
  await page.goto('/');
  const input=page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true});await expect(input).toBeEnabled();await input.fill('Giữ nguyên bản nháp kiểm tra nguồn');
  const before=page.url();await page.getByRole('button',{name:'Tệp đã tải',exact:true}).click();
  const drawer=page.getByRole('dialog',{name:'Tệp và dữ liệu',exact:true});
  await drawer.getByRole('button',{name:s.sources[0].name}).click();
  const artifacts=await(await page.request.get(`/api/datasets/${s.sources[0].id}/artifacts`)).json();
  await drawer.getByLabel('Phiên bản chuẩn hóa',{exact:true}).selectOption(artifacts.canonical_datasets[0].id);
  await expect(drawer.getByLabel('Phiên bản chuẩn hóa',{exact:true})).toHaveValue(artifacts.canonical_datasets[0].id);
  await drawer.getByRole('button',{name:s.sources[0].name}).click();
  await expect(drawer.getByLabel('Phiên bản chuẩn hóa',{exact:true})).toHaveValue(artifacts.canonical_datasets[0].id);
  await drawer.getByRole('button',{name:'Đã chuẩn hóa',exact:true}).click();
  await expect(drawer.getByRole('table')).toContainText('000702');
  await drawer.getByRole('button',{name:'Dòng lỗi',exact:true}).click();await expect(drawer).toContainText('0 dòng khớp điều kiện');
  await drawer.getByRole('button',{name:s.sources[1].name}).click();
  await expect(drawer.getByLabel('Phiên bản chuẩn hóa',{exact:true})).toHaveValue('');
  await expect(drawer.getByRole('button',{name:'Dữ liệu gốc',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(drawer.getByRole('table')).toContainText('000704');
  await page.keyboard.press('Escape');await expect(input).toHaveValue('Giữ nguyên bản nháp kiểm tra nguồn');expect(page.url()).toBe(before);
  await expect(page.getByRole('button',{name:'Tệp đã tải',exact:true})).toBeFocused();
});

test('[MOCK conversation, LIVE read] verified report opens in chat and preserves draft',async({page})=>{
  const s={...await deliveryFixture(),conversation_id:"overlay-conversation"};
  const context={project_id:s.project_id,run_id:s.run_id};
  await page.addInitScript(s=>{localStorage.setItem('studio.project',s.project_id);localStorage.setItem(`studio.conversation.${s.project_id}`,s.conversation_id);},s);
  await page.route(url=>url.pathname===`/api/conversations/${s.conversation_id}`,route=>route.fulfill({json:{conversation:{id:s.conversation_id,context,title:'Synthetic result overlay'},items:[{id:'overlay-answer',job_id:'overlay-job',role:'assistant',text:'',context,workflow_id:'overlay-workflow',created_at:'2026-11-02T00:00:00Z'}],has_more:false}}));
  await page.route('**/api/agent/workflows/overlay-workflow',route=>route.fulfill({json:{id:'overlay-workflow',conversation_id:s.conversation_id,context,state:'COMPLETED',updated_at:'2026-11-02T00:00:00Z',detail:{intent:{intent:'SUMMARIZE_RESULTS'},model_calls:0,error_code:null,reviews:[],steps:[],blocks:[{type:'facts',result:{tool:'get_run_summary',run:{metric_snapshot:s.snapshot}}}]}}}));
  await page.goto('/');const input=page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true});await expect(input).toBeEnabled();await input.fill('Bản nháp ở màn hình kết quả');
  const before=page.url();await expect(page.getByRole('region',{name:'Công việc của AI Assistant',exact:true})).toHaveCount(1);await page.getByRole('button',{name:'Mở kết quả và bằng chứng',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Chi tiết kết quả đã xác minh',exact:true});
  await dialog.locator(".result-analysis > summary").click();
  await expect(dialog).toContainText('33.33');await expect(dialog).toContainText('2.75');await expect(dialog.getByRole('img',{name:'Phân bố trạng thái đối soát'})).toBeVisible();
  await page.screenshot({path:test.info().outputPath('verified-result.png'),fullPage:true});
  await page.keyboard.press('Escape');await expect(input).toHaveValue('Bản nháp ở màn hình kết quả');expect(page.url()).toBe(before);
});
