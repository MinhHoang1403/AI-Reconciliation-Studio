import { test } from "./project-selection";
import {expect} from '@playwright/test';

test('[MOCK CONTRACT] sparse Planner facts remain editable and submit valid reviewed defaults',async({page})=>{
  const context={project_id:'review-project'},cid='review-conversation';
  const fields=[{id:'reference',name:'reference',data_type:'string'},{id:'event_date',name:'event_date',data_type:'date'},{id:'amount',name:'amount',data_type:'decimal'}];
  const metric={left:'amount',right:'amount',metric_id:'gross_value',currency:'VND',unit:'VND',amount_basis:'gross',sign_convention:'SOURCE_SIGNED',absolute_tolerance:'0'};
  const slot=(id:string)=>({canonical_id:id,role:null,date_field:null,time_basis:null,currency_field:null,filters:null,coverage_start:null,coverage_end:null,completeness:null,snapshot_at:null,settlement_due_at:null});
  const review={id:'review-one',kind:'RECONCILIATION',question:'Kiểm tra quy tắc tổng hợp',reason:'New rule',state:'OPEN',reply_questions:[],expected_effects:[],evidence_refs:[],nonce:'b'.repeat(32),fingerprint:'a'.repeat(64),expires_at:'2099-01-01T00:00:00Z',normalization_draft:null,plan:null,planning_request:{left:slot('canonical-a'),right:slot('canonical-b'),period_start:null,period_end:null,timezone:null,effective_from:null,allow_partial:false},suggestions:{left_role:'reference',right_role:'counterpart',join_keys:[{left:'reference',right:'reference'}],comparison_metrics:[metric],comparison_grain:'transaction',cardinality:'ONE_TO_ONE',aggregation:'NONE',evidence_ids:['canonical-a','canonical-b']}};
  let submitted:Record<string,unknown>|null=null;
  await page.addInitScript(()=>{localStorage.setItem('studio.project','review-project');localStorage.setItem('studio.conversation.review-project','review-conversation');});
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/decisions')){submitted=route.request().postDataJSON();return route.fulfill({status:409,json:{code:'SYNTHETIC_STOP_AFTER_VALIDATION',message_vi:'Payload đã được kiểm tra trong test; không chạy dữ liệu thật.'}});}
    if(route.request().method()!=='GET')throw Error(`Unexpected mutation: ${path}`);
    if(path==='/api/session')return route.fulfill({json:{workspace_id:'synthetic',role:'owner'}});
    if(path==='/api/settings')return route.fulfill({json:{policy:{allow_external_ai:false}}});
    if(path==='/api/projects/review-project')return route.fulfill({json:{id:context.project_id,name:'Synthetic review',workspace_id:'synthetic',classification:'TEST',business_scope:'synthetic'}});
    if(path==='/api/conversations')return route.fulfill({json:{items:[],has_more:false}});
    if(path===`/api/conversations/${cid}`)return route.fulfill({json:{conversation:{id:cid,context,title:'Sparse review'},items:[{id:'review-message',created_at:'2026-11-02T00:00:00Z',role:'assistant',context,job_id:'review-job',workflow_id:'review-workflow'}],has_more:false}});
    if(path==='/api/agent/workflows/review-workflow')return route.fulfill({json:{id:'review-workflow',context,conversation_id:cid,state:'WAITING_REVIEW',updated_at:'2026-11-02T00:00:00Z',detail:{intent:{intent:'RECONCILE_DATASETS'},reviews:[review],steps:[],blocks:[],model_calls:0}}});
    if(path.endsWith('/canonical-catalogue'))return route.fulfill({json:{items:['canonical-a','canonical-b'].map(id=>({canonical:{id},schema_definition:{grain:'transaction',entity_kind:'event',fields}}))}});
    return route.fulfill({json:{items:[],total:0}});
  });
  await page.goto('/');const card=page.getByRole('region',{name:'Quyết định cần xác nhận',exact:true});await card.getByText('Kiểm tra phạm vi và chỉnh quy tắc',{exact:true}).click();
  await card.getByLabel('Bắt đầu kỳ',{exact:true}).fill('2026-10-01');await card.getByLabel('Kết thúc kỳ (không bao gồm)',{exact:true}).fill('2026-11-01');await card.getByLabel('Quy tắc có hiệu lực từ',{exact:true}).fill('2026-10-01');await card.getByLabel('Múi giờ',{exact:true}).fill('UTC');
  for(let i=0;i<2;i++){const scope=card.locator('fieldset').nth(i);await scope.getByLabel('Trường ngày',{exact:true}).fill('event_date');await scope.getByLabel('Ý nghĩa ngày',{exact:true}).fill('Ngày phát sinh');await scope.getByLabel('Dữ liệu đầy đủ từ (ISO và timezone)',{exact:true}).fill('2026-10-01');await scope.getByLabel('Dữ liệu đầy đủ đến (không bao gồm)',{exact:true}).fill('2026-11-01');await scope.getByLabel('Thời điểm chốt dữ liệu',{exact:true}).fill('2026-11-02T00:00:00Z');await scope.getByRole('combobox',{name:'Độ đầy đủ',exact:true}).selectOption('CONFIRMED');}
  await card.getByRole('button',{name:'Duyệt quy tắc và đối soát',exact:true}).click();await expect.poll(()=>submitted).not.toBeNull();
  const plan=(submitted as unknown as {decision:{plan:{left:{role:string;filters:object};right:{role:string;filters:object};allow_partial:boolean}}}).decision.plan;
  expect(plan.left.role).toBe('reference');expect(plan.right.role).toBe('counterpart');expect(plan.left.filters).toEqual({});expect(plan.right.filters).toEqual({});expect(plan.allow_partial).toBe(false);
});
