import { expect, type Page } from "@playwright/test";
import { test } from "./project-selection";

async function chatFixture(page:Page,{long=true,failed=false,withModels=false}={}){
  const context={project_id:"scroll-project"};
  const conversation={id:"scroll-chat",context,title:"TEST cuộn hội thoại",created_at:"2026-11-04T00:00:00Z",archived:false};
  const message=(id:string,role:string,text:string,extra={})=>({id,job_id:id,role,text,context,answer:null,created_at:conversation.created_at,...extra});
  let messages=long?Array.from({length:24},(_,i)=>message(`history-${i}`,i%2?"assistant":"user",`Đoạn lịch sử ${i}. `+"Nội dung tổng hợp để kiểm tra vị trí đọc. ".repeat(12))):[];
  let accepted=0,settled=false,stage=0,jobPolls=0;
  const modelChoices: string[] = [];
  let terminalError=false;
  let review:Record<string,unknown>|null=null;
  let blocks:Record<string,unknown>[]=[{type:"progress",text:"Đang kiểm tra nguồn dữ liệu tổng hợp."}];
  if(failed)messages=[message("historical-failure","user","Yêu cầu cũ thất bại",{job_status:"FAILED",error_code:"INSUFFICIENT_EVIDENCE"})];
  await page.addInitScript(()=>{localStorage.setItem("studio.project","scroll-project");localStorage.setItem("studio.conversation.scroll-project","scroll-chat");});
  await page.route("**/api/**",async route=>{
    const url=new URL(route.request().url()),path=url.pathname;
    if(path==="/api/agent/mapping-preflight"){const draft=route.request().postDataJSON();const pending=draft.fields.filter((f:{question?:string})=>!!f.question);return route.fulfill({json:{draft,source_rows:1,verified_fields:draft.fields.length-pending.length,pending_fields:pending.length,checks:draft.fields.map((f:{source_field:string;name:string;question?:string})=>({field_id:f.source_field,name:f.name,state:f.question?'NEEDS_CONFIRMATION':'VERIFIED',messages:f.question?[f.question]:[],error_counts:{},affected_rows:0})),questions:pending.map((f:{question:string})=>f.question),preflight_ready:!pending.length,predicted_invalid_rows:pending.length?null:0,error_counts:{},source_sha256:'a'.repeat(64)}});}
    if(path==="/api/session")return route.fulfill({json:{workspace_id:"demo",actor_id:"scroll-owner",role:"owner"}});
    if(path==="/api/settings")return route.fulfill({json:{workspace_name:"TEST",agent_cloud_enabled:false,assistant_cloud_enabled:false,max_upload_bytes:20971520,max_upload_files:5,agent_max_upload_files:5,agent_upload_extensions:[".csv",".xlsx"],max_rows:100000,policy:{allow_external_ai:false}}});
    if(path==="/api/assistant/models"&&withModels)return route.fulfill({json:[
      {id:"GEMINI",label:"Gemini",available:true,status:"UNAVAILABLE"},
      {id:"QWEN_27B",label:"Qwen 27B",available:true,status:"UNVERIFIED",preferred:true},
    ]});
    if(path==="/api/projects/scroll-project")return route.fulfill({json:{id:context.project_id,name:"TEST scroll",business_scope:"Synthetic",workspace_id:"demo",classification:"TEST"}});
    if(path.endsWith("/summary"))return route.fulfill({json:{dataset_count:0,table_count:0,mapping_review_count:0,ready_canonical_count:0,active_job_count:0}});
    if(path==="/api/conversations")return route.fulfill({json:{items:[conversation],has_more:false}});
    if(path==="/api/conversations/scroll-chat"){
      if(url.searchParams.has("before_id"))return route.fulfill({json:{conversation,items:Array.from({length:8},(_,i)=>message(`older-${i}`,"assistant","Lịch sử bổ sung. ".repeat(30))),has_more:false}});
      return route.fulfill({json:{conversation,items:messages,has_more:long}});
    }
    if(path==="/api/assistant/messages"){
      accepted++;
      modelChoices.push(route.request().postDataJSON().model_choice);
      messages=[...messages,message("new-user","user",route.request().postDataJSON().text,{job_id:"new-job"})];
      return route.fulfill({status:202,json:{job_id:"new-job"}});
    }
    if(path==="/api/jobs/new-job"){
      jobPolls++;
      if(settled&&!messages.some(m=>m.id==="new-assistant"))messages=[...messages,message("new-assistant","assistant",terminalError?"Dịch vụ AI đang giới hạn yêu cầu. Dữ liệu của bạn được giữ.":"",{job_id:"new-job",workflow_id:terminalError?null:"scroll-workflow",error_code:terminalError?"GEMINI_RATE_LIMITED":null})];
      return route.fulfill({json:{id:"new-job",kind:"agent",status:terminalError?"BLOCKED":settled?"SUCCEEDED":"RUNNING",error_code:terminalError?"GEMINI_RATE_LIMITED":null}});
    }
    if(path==="/api/jobs/historical-failure")return route.fulfill({json:{id:"historical-failure",status:"FAILED",error_code:"INSUFFICIENT_EVIDENCE"}});
    if(path==="/api/agent/workflows/scroll-workflow/decisions"){
      review=null;stage++;blocks=[...blocks,{type:"progress",text:"Đã nhận xác nhận và tiếp tục công việc."}];
      return route.fulfill({json:{status:"RUNNING"}});
    }
    if(path==="/api/agent/workflows/scroll-workflow")return route.fulfill({json:{id:"scroll-workflow",conversation_id:conversation.id,context,state:review?"WAITING_REVIEW":stage===9?"COMPLETED":"RUNNING",updated_at:`2026-11-04T00:00:${String(stage).padStart(2,"0")}Z`,detail:{intent:{intent:"QUERY_DATA"},error_code:null,model_calls:0,reviews:review?[review]:[],steps:[],blocks}}});
    if(route.request().method()!=="GET")throw Error(`Unexpected mutation ${path}`);
    return route.fulfill({json:{items:[],total:0}});
  });
  await page.goto("/");
  await expect(page.getByLabel("Câu hỏi cho AI Assistant",{exact:true})).toBeEnabled();
  return {
    modelChoices,
    count:()=>accepted,
    polls:()=>jobPolls,
    finish:()=>{settled=true;},
    fail:()=>{terminalError=true;settled=true;},
    review:(kind:"CLARIFICATION"|"MAPPING")=>{stage++;review={id:"review",kind,question:"Bạn muốn tiếp tục với nguồn đã chọn?",reason:"Dữ liệu tổng hợp kiểm tra cuộn.",resource_id:"table",fingerprint:"a".repeat(64),nonce:"a".repeat(32),expires_at:"2099-01-01T00:00:00Z",state:"OPEN",expected_effects:[],reply_questions:[],pending_reply_job_id:null,reply_intent:null,plan:null,suggestions:null,planning_request:null,normalization_draft:kind==="MAPPING"?{table_id:"table",entity_kind:"test",grain:"Một dòng tổng hợp",fields:[{source_field:"c1",target_id:"reference",name:"Mã giao dịch",data_type:"string",business_key:true,semantic_metric:null,amount_basis:null,currency:null,unit:null,locale:null,date_format:null,timezone:null,question:""}]}:null,options:kind==="CLARIFICATION"?[{id:"selected",label:"Nguồn đã chọn",intent:{intent:"EXPLORE_DATA",dataset_ids:[]}}]:[]};},
    grow:(text:string)=>{stage++;blocks=[...blocks,{type:"progress",text}];},
    table:()=>{stage++;blocks=[...blocks,{type:"table",result:{query:{project_id:context.project_id,source_kind:"RAW_PREVIEW",source_id:"table",select_fields:["reference"],sort:[],filters:[],group_by:[],aggregations:[],limit:25,offset:0,null_policy:"PRESERVE",result_scope:"ALL_MATCHING",currency_field:null},fields:["reference"],rows:Array.from({length:25},(_,i)=>({reference:`000${i}`})),total_count:25,input_count:25,offset:0,limit:25,truncated:false,evidence_complete:true,verification_status:"RAW_UNVERIFIED",source_refs:["table"],warnings:[]}}];},
  };
}

test("[MOCK CONTRACT] switching model preserves draft, queued request and history after reload",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  const fixture=await chatFixture(page,{long:false,withModels:true});
  await page.getByLabel("Tùy chọn hội thoại",{exact:true}).click();
  const model=page.getByLabel("Trợ lý cho tin nhắn mới");
  const composer=page.getByLabel("Câu hỏi cho AI Assistant",{exact:true});
  await expect(model).toHaveValue("QWEN_27B");
  await expect(model.locator("option")).toHaveText(["Gemini 3.5 Flash Lite", "Qwen 3:8B"]);
  await expect(model.locator("optgroup")).toHaveCount(0);
  await expect(model).not.toHaveAttribute("title", /.+/);
  await expect(composer).toBeInViewport({ratio:1});
  expect((await composer.boundingBox())?.width).toBeGreaterThan(220);
  await composer.fill("Kiểm tra đúng nguồn của hội thoại này");
  await model.selectOption("QWEN_27B");
  await expect(composer).toHaveValue("Kiểm tra đúng nguồn của hội thoại này");
  expect(fixture.count()).toBe(0);
  await composer.press("Enter");
  await expect.poll(fixture.count).toBe(1);
  await expect(model).toBeEnabled();
  await model.selectOption("GEMINI");
  expect(fixture.modelChoices).toEqual(["QWEN_27B"]);
  fixture.finish();
  await expect(page.getByText("Đang kiểm tra nguồn dữ liệu tổng hợp.",{exact:true})).toBeVisible();
  await composer.fill("Bản nháp tiếp theo");
  await page.reload();
  await page.getByLabel("Tùy chọn hội thoại",{exact:true}).click();
  await expect(model).toHaveValue("GEMINI");
  await expect(composer).toHaveValue("Bản nháp tiếp theo");
  await expect(page.getByText("Kiểm tra đúng nguồn của hội thoại này",{exact:true})).toBeVisible();
  expect(fixture.count()).toBe(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

const gap=(page:Page)=>page.locator(".assistant-scroll").evaluate(e=>e.scrollHeight-e.scrollTop-e.clientHeight);
async function readEarlier(page:Page){
  await page.locator(".assistant-scroll").evaluate(e=>{e.scrollTop=200;e.dispatchEvent(new Event("scroll"));});
  await expect.poll(()=>gap(page)).toBeGreaterThan(100);
}

for(const width of [390,1440,1920]){
  test(`[MOCK CONTRACT] send, delayed answer, growing table and user reading at ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:900});
    const fixture=await chatFixture(page);
    await expect.poll(()=>gap(page)).toBeLessThan(10);
    await readEarlier(page);
    const input=page.getByLabel("Câu hỏi cho AI Assistant",{exact:true});
    await input.fill("Kiểm tra nguồn và giữ vị trí hội thoại");
    await input.press("Enter");
    await expect(page.getByText("Kiểm tra nguồn và giữ vị trí hội thoại",{exact:true})).toBeInViewport();
    await expect.poll(()=>gap(page)).toBeLessThan(10);
    fixture.finish();
    await expect(page.getByText("Đang kiểm tra nguồn dữ liệu tổng hợp.",{exact:true})).toBeVisible();
    fixture.grow("Phản hồi chậm được cập nhật. ".repeat(35));
    await expect(page.getByText(/Phản hồi chậm được cập nhật/)).toBeAttached();
    await expect.poll(()=>gap(page)).toBeLessThan(10);
    fixture.table();
    await expect(page.getByRole("table")).toBeAttached();
    await expect.poll(()=>gap(page)).toBeLessThan(10);
    await readEarlier(page);
    const before=await page.locator(".assistant-scroll").evaluate(e=>e.scrollTop);
    fixture.grow("Nội dung đến sau khi người dùng cuộn lên.");
    await expect(page.getByRole("button",{name:"Tin nhắn mới · Xuống cuối",exact:true})).toBeVisible();
    expect(await page.locator(".assistant-scroll").evaluate(e=>e.scrollTop)).toBeCloseTo(before,0);
    await page.getByRole("button",{name:"Tin nhắn mới · Xuống cuối",exact:true}).click();
    await expect.poll(()=>gap(page)).toBeLessThan(10);
    await expect(input).toBeEnabled();
    expect(fixture.count()).toBe(1);
    expect(await page.evaluate(()=>window.scrollY)).toBe(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  });
}

test("[MOCK CONTRACT] prepending history preserves its visual anchor; reload restores latest",async({page})=>{
  await chatFixture(page);
  await page.locator(".assistant-scroll").evaluate(e=>{e.scrollTop=0;e.dispatchEvent(new Event("scroll"));});
  const anchor=page.getByText(/^Đoạn lịch sử 0\./);
  const before=await anchor.boundingBox();
  await page.getByRole("button",{name:"Xem tin nhắn cũ hơn",exact:true}).click();
  await expect(page.getByRole("button",{name:"Xem tin nhắn cũ hơn",exact:true})).toHaveCount(0);
  expect(Math.abs((await anchor.boundingBox())!.y-before!.y)).toBeLessThan(3);
  await expect(page.getByRole("button",{name:"Tin nhắn mới · Xuống cuối",exact:true})).toHaveCount(0);
  await page.reload();
  await expect(page.getByLabel("Câu hỏi cho AI Assistant",{exact:true})).toBeEnabled();
  await expect.poll(()=>gap(page)).toBeLessThan(10);
});

test("[MOCK CONTRACT] short send and historical failed job stay visible after reopen",async({page})=>{
  const fixture=await chatFixture(page,{long:false,failed:true});
  await expect(page.getByRole("alert")).toContainText("Chưa đủ bằng chứng");
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("Chưa đủ bằng chứng");
  const input=page.getByLabel("Câu hỏi cho AI Assistant",{exact:true});
  await input.fill("Câu hỏi mới có kết quả rõ ràng");
  await page.getByRole("button",{name:"Gửi câu hỏi",exact:true}).dblclick();
  fixture.finish();
  await expect(page.getByText("Đang kiểm tra nguồn dữ liệu tổng hợp.",{exact:true})).toBeVisible();
  expect(fixture.count()).toBe(1);
  await expect.poll(()=>gap(page)).toBeLessThan(10);
});

for(const kind of ["CLARIFICATION","MAPPING"] as const){
  test(`[MOCK CONTRACT] ${kind} continuation remains at the transcript tail`,async({page})=>{
    const fixture=await chatFixture(page);
    await page.getByLabel("Câu hỏi cho AI Assistant",{exact:true}).fill("Kiểm tra quyết định đang chờ");
    await page.getByRole("button",{name:"Gửi câu hỏi",exact:true}).click();fixture.finish();
    await expect(page.getByText("Đang kiểm tra nguồn dữ liệu tổng hợp.",{exact:true})).toBeVisible();
    fixture.review(kind);
    await expect(page.getByText("Bạn muốn tiếp tục với nguồn đã chọn?",{exact:true})).toBeAttached();
    await expect.poll(()=>gap(page)).toBeLessThan(10);
    if(kind==="CLARIFICATION")await page.getByRole("button",{name:"Nguồn đã chọn",exact:true}).click();
    else{
      await page.getByLabel("Tôi đã kiểm tra cảnh báo/vùng bảng nguồn nếu có.",{exact:true}).check();
      await page.getByRole("button",{name:"Duyệt cách ghép cột và chuẩn hóa",exact:true}).click();
    }
    await expect(page.getByText("Đã nhận xác nhận và tiếp tục công việc.",{exact:true})).toBeVisible();
    await expect.poll(()=>gap(page)).toBeLessThan(10);
  });
}

test("[MOCK CONTRACT] terminal provider error arrives visibly at the transcript tail",async({page})=>{
  const fixture=await chatFixture(page);
  await readEarlier(page);
  await page.getByLabel("Câu hỏi cho AI Assistant",{exact:true}).fill("Yêu cầu kiểm tra lỗi dịch vụ");
  await page.getByRole("button",{name:"Gửi câu hỏi",exact:true}).click();fixture.fail();
  await expect(page.getByText("Dịch vụ AI đang giới hạn yêu cầu. Dữ liệu của bạn được giữ.",{exact:true})).toBeInViewport();
  await expect.poll(()=>gap(page)).toBeLessThan(10);
  await expect(page.getByLabel("Câu hỏi cho AI Assistant",{exact:true})).toBeEnabled();
  expect(fixture.count()).toBe(1);
});

test("[MOCK CONTRACT] accepted slow job remains observable after the initial polling burst",async({page})=>{
  const fixture=await chatFixture(page,{long:false});
  await page.clock.install();
  await page.getByLabel("Câu hỏi cho AI Assistant",{exact:true}).fill("Yêu cầu xử lý nền chậm");
  await page.getByRole("button",{name:"Gửi câu hỏi",exact:true}).click();
  for(let i=0;i<63;i++){
    const previous=fixture.polls();
    await page.clock.runFor(i<60?600:2100);
    await expect.poll(()=>fixture.polls()).toBeGreaterThan(previous);
  }
  fixture.finish();
  await page.clock.runFor(2100);
  await expect(page.getByText("Đang kiểm tra nguồn dữ liệu tổng hợp.",{exact:true})).toBeVisible();
  await expect(page.getByLabel("Câu hỏi cho AI Assistant",{exact:true})).toBeEnabled();
  expect(fixture.count()).toBe(1);
});
