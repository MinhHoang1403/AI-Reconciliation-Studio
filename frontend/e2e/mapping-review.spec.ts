import {expect} from '@playwright/test';
import {test} from './project-selection';

test('[MOCK CONTRACT] mapping review confirms timezone once and cannot approve a changed or unchecked draft',async({page})=>{
  await page.setViewportSize({width:1440,height:1200});
  const context={project_id:'mapping-review-project'};
  const conversation={id:'mapping-review-conversation',context,title:'TEST kiểm chứng mapping',created_at:'2026-11-05T00:00:00Z',archived:false};
  const field={data_type:'date',business_key:false,semantic_metric:null,amount_basis:null,currency:null,unit:null,locale:null,date_format:'%Y-%m-%d',timezone:null as string|null,question:''};
  const draft={table_id:'table',entity_kind:'order',grain:'Một đơn hàng mỗi dòng',fields:[{...field,source_field:'c1',target_id:'event_date',name:'Ngày phát sinh'},{...field,source_field:'c2',target_id:'posted_date',name:'Ngày ghi nhận'}]};
  const review={id:'review',kind:'MAPPING',resource_id:'table',resource_label:'Dữ liệu tổng hợp.csv',question:'Kiểm tra đề xuất',reason:'Chưa suy đoán múi giờ.',state:'OPEN',nonce:'a'.repeat(32),fingerprint:'b'.repeat(64),expires_at:'2099-01-01T00:00:00Z',normalization_draft:draft,extraction_review_required:false,reply_questions:[],expected_effects:[],pending_reply_job_id:null};
  const decisions:Record<string,unknown>[]=[];
  let approved=false,preflights=0,saves=0,renewals=0,revision=0,release:()=>void=()=>{},gate:Promise<void>|null=null;
  const workflow=()=>({id:'workflow',context,state:approved?'COMPLETED':'WAITING_REVIEW',updated_at:new Date(Date.parse(conversation.created_at)+revision*1000).toISOString(),detail:{reviews:approved?[]:[review],blocks:[],steps:[],model_calls:0}});
  await page.addInitScript(()=>{localStorage.setItem('studio.project','mapping-review-project');localStorage.setItem('studio.conversation.mapping-review-project','mapping-review-conversation');});
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/session')return route.fulfill({json:{workspace_id:'test',actor_id:'owner',role:'owner'}});
    if(path==='/api/settings')return route.fulfill({json:{workspace_name:'TEST',agent_cloud_enabled:false,assistant_cloud_enabled:false,policy:{allow_external_ai:false}}});
    if(path==='/api/projects/mapping-review-project')return route.fulfill({json:{id:context.project_id,name:'TEST mapping',classification:'TEST',business_scope:'Synthetic'}});
    if(path==='/api/conversations')return route.fulfill({json:{items:[conversation],has_more:false}});
    if(path==='/api/conversations/mapping-review-conversation')return route.fulfill({json:{conversation,items:[{id:'reply',job_id:'job',role:'assistant',text:'',context,workflow_id:'workflow',created_at:conversation.created_at}],has_more:false}});
    if(path==='/api/agent/workflows/workflow')return route.fulfill({json:workflow()});
    if(path==='/api/agent/workflows/workflow/draft'){
      const body=route.request().postDataJSON();expect(body.nonce).toBe(review.nonce);expect(body.fingerprint).toBe(review.fingerprint);
      review.normalization_draft=body.draft;saves++;revision++;review.nonce=String(revision).padStart(32,'c');return route.fulfill({json:workflow()});
    }
    if(path==='/api/agent/workflows/workflow/renew-review'){
      expect(route.request().postDataJSON().nonce).toBe(review.nonce);renewals++;revision++;review.nonce=String(revision).padStart(32,'d');review.expires_at='2099-01-01T00:00:00Z';return route.fulfill({json:workflow()});
    }
    if(path==='/api/agent/mapping-preflight'){
      preflights++;if(gate)await gate;
      const candidate=route.request().postDataJSON();const ready=candidate.fields.every((f:{timezone:string|null;date_format:string|null})=>!!f.timezone&&f.date_format==='%Y-%m-%d');
      return route.fulfill({json:{draft:candidate,source_rows:2418,verified_fields:ready?2:0,pending_fields:ready?0:2,checks:candidate.fields.map((f:{source_field:string;name:string})=>({field_id:f.source_field,name:f.name,state:ready?'VERIFIED':'NEEDS_CONFIRMATION',messages:[],error_counts:{},affected_rows:0})),questions:ready?[]:['Xác nhận múi giờ của nguồn.'],preflight_ready:ready,predicted_invalid_rows:ready?2:null,error_counts:ready?{INVALID_DATE:2}:{},source_sha256:'c'.repeat(64)}});
    }
    if(path==='/api/agent/workflows/workflow/decisions'){decisions.push(route.request().postDataJSON());approved=true;return route.fulfill({json:{}});}
    if(route.request().method()!=='GET')throw Error('Unexpected write '+path);
    return route.fulfill({json:{items:[],has_more:false,total:0}});
  });
  await page.goto('/#page=assistant');const approve=page.getByRole('button',{name:'Duyệt cách ghép cột và chuẩn hóa',exact:true});
  await expect(page.getByText('2 cột · 2418 dòng.',{exact:false})).toBeVisible();await expect(approve).toBeDisabled();
  await page.getByRole('region',{name:'Quyết định cần xác nhận',exact:true}).screenshot({path:'../runtime/mapping-audit/review-ui-mock.png'});
  await expect(page.getByLabel('Tên trường',{exact:true}).first()).toBeHidden();await expect(page.getByLabel('Tôi đã kiểm tra cảnh báo/vùng bảng nguồn nếu có.',{exact:true})).toHaveCount(0);
  gate=new Promise<void>(resolve=>release=resolve);
  await page.getByLabel('Múi giờ của nguồn',{exact:true}).selectOption('UTC');
  await expect(approve).toBeDisabled();expect(decisions).toEqual([]);
  await expect.poll(()=>preflights).toBeGreaterThanOrEqual(2);release();gate=null;
  await expect(page.getByText('dự kiến 2 dòng không hợp lệ.',{exact:false})).toBeVisible();await expect(approve).toBeEnabled();
  await page.reload();await expect(approve).toBeEnabled(); // unsaved changes survive reload
  await page.getByRole('button',{name:'Lưu bản nháp',exact:true}).click();await expect.poll(()=>saves).toBe(1);
  await page.reload();await expect(approve).toBeEnabled(); // server saved preview, still no approval
  expect(decisions).toEqual([]);
  await page.getByText('Xem và chỉnh các lựa chọn',{exact:true}).click();
  const format=page.getByRole('combobox',{name:'Định dạng ngày',exact:true}).first();
  gate=new Promise<void>(resolve=>release=resolve);
  await format.selectOption('%d/%m/%Y');await expect(approve).toBeDisabled();
  await expect.poll(()=>preflights).toBeGreaterThanOrEqual(3);release();gate=null;
  await expect(approve).toBeDisabled();expect(decisions).toEqual([]);
  await format.selectOption('%Y-%m-%d');await expect(approve).toBeEnabled();
  review.expires_at='2020-01-01T00:00:00Z';revision++;await page.reload();await expect(approve).toBeDisabled();
  await page.getByRole('button',{name:'Mở lại thẻ xác nhận',exact:true}).click();await expect.poll(()=>renewals).toBe(1);await expect(approve).toBeEnabled();
  await approve.dblclick();await expect.poll(()=>decisions.length).toBe(1);
  const decision=decisions[0] as {nonce:string;fingerprint:string;decision:{draft:typeof draft}};
  expect(decision.nonce).toBe(review.nonce);expect(decision.fingerprint).toBe(review.fingerprint);
  expect(decision.decision.draft.fields.every(f=>f.timezone==='UTC')).toBe(true);
});
