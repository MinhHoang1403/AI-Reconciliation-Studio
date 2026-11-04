import { test } from "./project-selection";
import {expect} from "@playwright/test";
import {mkdir} from "node:fs/promises";

const context={project_id:"visual-project"};
const conversation={id:"visual-conversation",context,title:"Hội thoại tổng hợp để kiểm tra bố cục",created_at:"2026-11-02T00:00:00Z",archived:false};
const field=(extra:Record<string,unknown>)=>({source_field:"c1",target_id:"transaction_id",name:"Mã giao dịch",data_type:"string",business_key:true,semantic_metric:null,amount_basis:null,currency:null,unit:null,locale:null,date_format:null,timezone:null,question:"",...extra});
const review={id:"visual-review",kind:"MAPPING",resource_id:"visual-table",resource_label:"Sổ cái tổng hợp.csv · Sheet1",question:"Xác nhận ý nghĩa số tiền",reason:"Khoản tiền chưa rõ gross/net và định dạng số. Dữ liệu gốc được giữ nguyên.",fingerprint:"a".repeat(64),nonce:"b".repeat(32),expires_at:"2099-01-01T00:00:00Z",state:"OPEN",expected_effects:[],normalization_draft:{table_id:"visual-table",entity_kind:"voucher",grain:"Mỗi dòng là một chứng từ",fields:[field({}),field({source_field:"c2",target_id:"amount",name:"Số tiền",data_type:"decimal",business_key:false,question:"Đây là gross hay net?"})]},plan:null,suggestions:null,planning_request:null,reply_intent:null,reply_questions:[],pending_reply_job_id:null};
const query={project_id:context.project_id,source_kind:"CANONICAL",source_id:"visual-canonical",select_fields:["transaction_id","amount","description"],filters:[],sort:[],group_by:[],aggregations:[],offset:0,limit:25,null_policy:"PRESERVE",result_scope:"ALL_MATCHING",currency_field:"currency"};
function table(wide=false){const fields=["transaction_id","amount","description",...(wide?Array.from({length:15},(_,i)=>`Trường kiểm tra dài ${i+1}`):[])];return {type:"table",result:{query:{...query,select_fields:fields},source_id:"visual-canonical",fields,rows:Array.from({length:25},(_,i)=>Object.fromEntries([...fields.map((key,n)=>[key,n===0?`000${701+i}`:n===1?"12.75":"Nội dung tổng hợp có độ dài để kiểm tra hiển thị rõ ràng"]),["source_provenance",[{source_table_id:"visual-table",row:i+2,sheet:"Sheet1"}]]])),total_count:75,input_count:75,offset:0,limit:25,truncated:true,evidence_complete:true,verification_status:"CANONICAL",quality_status:"READY",source_refs:["visual-artifact"],warnings:["Tổng/đếm áp dụng toàn bộ dữ liệu khớp điều kiện, không chỉ trang hiện tại."]}};}
const chart={type:"chart",title:"Giá trị tổng hợp theo nhóm",unit:"VND",population:3,population_definition:"Toàn bộ dòng khớp điều kiện",completeness:"COMPLETE",points:[{label:"Nhóm A",value:"25.00"},{label:"Nhóm B",value:"12.75"}],source_refs:["visual-artifact"],verification_status:"CANONICAL",period_start:null,period_end:null,timezone:null};

for(const width of [390,768,1366,1440,1920]){
  test(`[MOCK CONTRACT] Assistant 23 states, focus and layout at ${width}px`,async({page})=>{
    test.setTimeout(120000);await page.setViewportSize({width,height:900});
    await mkdir(`../runtime/assistant-layout/${width}`,{recursive:true});
    const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
    let scenario="empty";let release:()=>void=()=>{};let gate=Promise.resolve();
    await page.addInitScript(()=>{localStorage.setItem("studio.project","visual-project");localStorage.setItem("studio.conversation.visual-project","visual-conversation");});
    await page.route("**/api/**",async route=>{
      const path=new URL(route.request().url()).pathname;
      if(path==="/api/session")return route.fulfill({json:{workspace_id:"visual",actor_id:"visual-owner",role:scenario==="permission"?"viewer":"owner"}});
      if(path==="/api/settings")return route.fulfill({json:{workspace_name:"Visual contract only",assistant_cloud_enabled:false,agent_cloud_enabled:false,mapping_ai_provider:"GEMINI",gemini_requests_used:0,gemini_requests_remaining:0,max_upload_bytes:20971520,max_upload_files:5,agent_max_upload_files:5,agent_upload_extensions:[".csv",".xlsx"],max_rows:100000,policy:{allow_external_ai:false}}});
      if(path==="/api/projects/visual-project")return route.fulfill({json:{id:context.project_id,name:"Dự án tổng hợp kiểm tra giao diện",business_scope:"synthetic visual fixture",workspace_id:"visual",classification:"TEST"}});
      if(path.endsWith("/summary"))return route.fulfill({json:{dataset_count:2,table_count:2,mapping_review_count:0,ready_canonical_count:2,active_job_count:0}});
      if(path==="/api/conversations")return route.fulfill({json:{items:[conversation],has_more:false}});
      if(path==="/api/conversations/visual-conversation"){
        if(scenario==="loading")await gate;
        if(scenario==="error")return route.fulfill({status:503,json:{code:"VISUAL_PROVIDER_UNAVAILABLE",message_vi:"Chưa tải được hội thoại. Dữ liệu đã lưu vẫn được giữ."}});
        const text="Nội dung hội thoại tổng hợp dùng để kiểm tra bố cục và khả năng đọc.";
        const items=scenario==="empty"||scenario==="upload"||scenario==="multiline"||scenario==="keyboard"||scenario==="sidebar"||scenario==="history"?[]:
          [...(scenario==="completed"?[{id:"older-workflow",job_id:"old-job",role:"assistant",text:"",context:{...context,run_id:"old-run"},answer:null,workflow_id:"old-visual-workflow",created_at:conversation.created_at}]:[]),...(scenario==="long"?Array.from({length:18},(_,i)=>({id:`old-${i}`,job_id:`job-${i}`,role:i%2?"assistant":"user",text:text.repeat(4),context,answer:null,created_at:conversation.created_at})):[]),
           {id:"visual-user",job_id:"visual-job",role:"user",text:"Kiểm tra dữ liệu và chỉ hỏi phần cần xác nhận",context,answer:null,created_at:conversation.created_at},
           {id:"visual-assistant",job_id:"visual-job",role:"assistant",text:"",context,answer:null,workflow_id:"visual-workflow",created_at:conversation.created_at}];
        return route.fulfill({json:{conversation,items,has_more:false}});
      }
      if(path==="/api/agent/workflows/old-visual-workflow"){await new Promise(resolve=>setTimeout(resolve,75));return route.fulfill({json:{id:"old-visual-workflow",conversation_id:conversation.id,context:{...context,run_id:"old-run"},state:"COMPLETED",updated_at:conversation.created_at,detail:{intent:{intent:"SUMMARIZE_RESULTS"},model_calls:0,error_code:null,steps:[],reviews:[],blocks:[{type:"progress",text:"Kết quả cũ giữ nguyên ngữ cảnh riêng."}]}}});}
      if(path==="/api/agent/workflows/visual-workflow")return route.fulfill({json:{id:"visual-workflow",conversation_id:conversation.id,context:scenario==="completed"?{...context,run_id:"visual-run"}:context,state:scenario==="review"||scenario==="permission"?"WAITING_REVIEW":scenario==="running"?"RUNNING":scenario==="partial"?"PARTIAL":scenario==="failed"?"FAILED":scenario==="unavailable"?"BLOCKED":"COMPLETED",updated_at:conversation.created_at,detail:{intent:{intent:"QUERY_DATA"},model_calls:0,error_code:scenario==="unavailable"?"GEMINI_UNAVAILABLE":scenario==="failed"?"NORMALIZATION_FAILED":null,steps:scenario==="running"?[{tool:"run_normalization",resource_id:"visual-table",job_id:"visual-job",status:"RUNNING"}]:[],reviews:scenario==="review"||scenario==="permission"?[review]:[],blocks:scenario==="export"?[{type:"download",export_id:"visual-export",format:"xlsx"}]:scenario==="longfilename"?[{type:"dataset_summary",dataset_id:"visual-dataset",table_id:"visual-table",canonical_id:"visual-canonical",name:"Synthetic ledger with long descriptive filename ".repeat(5)+".csv",rows:75,invalid_rows:2,status:"PARTIAL",transformations:["parse_decimal"]}]:scenario==="partial"?[{type:"progress",text:"Một phần dữ liệu cần kiểm tra; kết quả đã lưu được giữ."}]:scenario==="running"?[{type:"progress",text:"Worker đang xử lý nguồn dữ liệu. Kết quả chưa được công bố."}]:scenario==="table"||scenario==="evidence"?[table(true)]:scenario==="chart"?[chart]:scenario==="completed"?[{type:"dataset_summary",dataset_id:"visual-dataset",table_id:"visual-table",canonical_id:"visual-canonical",name:"Sổ cái tổng hợp.csv",rows:75,invalid_rows:0,status:"READY",transformations:["cast_string_preserve","parse_decimal"]},table(),chart]:[{type:"progress",text:"Đây là dữ liệu tổng hợp kiểm tra UI; không phải nghiệm thu suy luận live."}]}}});
      if(path==="/api/agent/source-rows")return route.fulfill({json:{rows:[{"Mã giao dịch (c1)":"000701","Số tiền (c2)":"25.00","Nội dung (c3)":"Dòng tổng hợp bất biến"}]}});
      if(path==="/api/agent/attachments"){await gate;return route.fulfill({status:422,json:{code:"VISUAL_UPLOAD_ERROR",message_vi:"Kiểm tra hiển thị lỗi upload tổng hợp; không có file thật được lưu."}});}
      if(route.request().method()!=="GET")throw new Error(`Unexpected visual mutation: ${path}`);
      return route.fulfill({json:{items:[],total:0}});
    });
    async function shot(name:string){
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      await page.screenshot({path:`../runtime/assistant-layout/${width}/${name}.png`,fullPage:true});
    }
    const input=page.getByLabel("Câu hỏi cho AI Assistant",{exact:true});
    for(const name of ["empty","short","long","upload","running","review","completed","table","chart","evidence","history","multiline","keyboard","sidebar","delete","error","permission","loading","partial","failed","unavailable","export","longfilename"]){
      scenario=name;gate=new Promise<void>(resolve=>release=resolve);
      await page.goto("/");await expect(page.getByText("Hệ thống đã kết nối",{exact:true})).toBeAttached();
      if(name==="loading"){await expect(input).toBeDisabled();await shot(name);release();await expect(input).toBeEnabled();continue;}
      if(name==="error"){await expect(page.getByRole("alert")).toContainText("Chưa tải được hội thoại");await shot(name);continue;}
      await expect(input).toBeEnabled();
      if(name==="empty"){
        await expect(page.getByRole("heading",{name:"Bạn muốn xử lý dữ liệu gì?"})).toBeVisible();
        await expect(page.getByRole("dialog",{name:"Lịch sử",exact:true})).toHaveCount(0);
        await expect(page.getByLabel("Chọn kết quả phân tích",{exact:true})).toHaveCount(0);
        await expect(page.getByRole("button",{name:"← Trở về trang trước",exact:true})).toHaveCount(0);
      }
      if(name==="upload"){
        await page.locator('.assistant-composer input[type="file"]').setInputFiles({name:"Synthetic ledger with a long descriptive filename.csv",mimeType:"text/csv",buffer:Buffer.from("id,amount\n000701,25.00\n")});
        await page.getByRole("button",{name:"Gửi câu hỏi",exact:true}).click();await expect(input).toBeDisabled();
        await shot(name);release();await expect(page.getByRole("alert")).toContainText("lỗi upload");continue;
      }
      if(name==="history"){
        const menu=page.getByRole("button",{name:"Mở điều hướng",exact:true});if(await menu.isVisible())await menu.click();
        await page.getByRole("button",{name:"Lịch sử",exact:true}).click();
        await expect(page.getByRole("dialog",{name:"Lịch sử",exact:true})).toContainText(conversation.title);
        await shot(name);await page.keyboard.press("Escape");await expect(width<=900?page.getByRole("button",{name:"Mở điều hướng",exact:true}):page.getByRole("button",{name:"Lịch sử",exact:true})).toBeFocused();continue;
      }
      if(name==="multiline"||name==="keyboard"){
        await input.fill(Array.from({length:12},(_,i)=>`Dòng yêu cầu ${i+1}: giữ nguyên mã và kiểm tra dữ liệu.`).join("\n"));await input.focus();
        if(name==="keyboard"){await page.setViewportSize({width,height:540});await expect(input).toBeInViewport({ratio:1});await expect(page.getByRole("button",{name:"Gửi câu hỏi",exact:true})).toBeInViewport({ratio:1});}
      }
      if(name==="sidebar"){
        const menu=page.getByRole("button",{name:"Mở điều hướng",exact:true});if(await menu.isVisible())await menu.click();
        await expect(page.locator('.sidebar').getByRole('button')).toHaveText(['AI Assistant','Lịch sử','Cài đặt']);
        await page.locator('.sidebar').getByRole('button',{name:'Lịch sử',exact:true}).focus();
        await expect(page.locator('.sidebar').getByRole('button',{name:'Lịch sử',exact:true})).toBeFocused();
      }
      if(name==="evidence"){await page.getByRole("button",{name:"Xem dòng gốc",exact:true}).first().click();await expect(page.getByRole("dialog",{name:"Dòng dữ liệu nguồn",exact:true})).toContainText("000701");}
      if(name==="delete"){
        await page.locator('.assistant-menu summary').click();
        await page.getByRole("button",{name:"Xóa hội thoại",exact:true}).click();
        const confirmation=page.getByRole("dialog",{name:"Xác nhận xóa hội thoại",exact:true});
        await expect(confirmation).toContainText("nguồn dữ liệu và báo cáo được giữ nguyên");
        await shot(name);await page.keyboard.press("Escape");
        await expect(page.getByRole("button",{name:"Xóa hội thoại",exact:true})).toBeFocused();continue;
      }
      if(name==="completed"){
        await expect(page.getByRole("region",{name:"Công việc của AI Assistant",exact:true}).first()).toContainText("Kết quả cũ giữ nguyên ngữ cảnh riêng.");
        await expect(page.getByRole("button",{name:"Đổi ngữ cảnh phân tích",exact:true})).toHaveAttribute("data-run-id","visual-run");
      }
      if(name==="permission")await expect(page.getByRole("button",{name:"Đính kèm CSV hoặc Excel",exact:true})).toBeDisabled();
      if(name==="review"){
        await expect(page.locator("textarea")).toHaveCount(1);
        await expect(page.getByLabel("Ý nghĩa số tiền",{exact:true})).not.toBeVisible();
        await page.getByText("Xem và chỉnh các lựa chọn",{exact:true}).click();
        await expect(page.getByLabel("Ý nghĩa số tiền",{exact:true})).toBeVisible();
        await page.getByText("Xem và chỉnh các lựa chọn",{exact:true}).click();
        await page.getByRole("button",{name:"Bổ sung bằng tiếng Việt",exact:true}).click();
        await expect(input).toBeFocused();
        await expect(page.getByRole("button",{name:"Đính kèm CSV hoặc Excel",exact:true})).toBeDisabled();
        await input.fill("Số tiền gross, VND; giữ nguyên mã có số 0 đầu.");
        await page.getByRole("button",{name:"Hủy trả lời xác nhận",exact:true}).click();
        await expect(input).toHaveValue("Số tiền gross, VND; giữ nguyên mã có số 0 đầu.");
        await expect(page.locator("textarea")).toHaveCount(1);
      }
      if(["short","long","running","review","completed","table","chart","permission"].includes(name))await expect(page.getByRole("region",{name:"Công việc của AI Assistant",exact:true}).last()).toContainText(name==="running"?"Đang thực hiện":name==="review"||name==="permission"?"Cần bạn xác nhận":"Đã hoàn thành");
      if(name==="partial")await expect(page.getByRole("region",{name:"Công việc của AI Assistant",exact:true})).toContainText("Hoàn thành một phần");
      if(name==="failed")await expect(page.getByRole("region",{name:"Công việc của AI Assistant",exact:true})).toContainText("Xử lý thất bại");
      if(name==="unavailable")await expect(page.getByRole("region",{name:"Công việc của AI Assistant",exact:true})).toContainText("Chưa thể tiếp tục");
      if(name==="export")await expect(page.getByRole("link",{name:"Tải XLSX",exact:true})).toHaveAttribute("href","/api/exports/visual-export/download");
      if(name==="longfilename")await expect(page.getByRole("heading",{name:/Synthetic ledger/})).toBeVisible();
      await shot(name);if(name==="keyboard")await page.setViewportSize({width,height:900});
      release();
    }
    expect(errors).toEqual([]);
  });
}


for (const width of [390, 768, 1366, 1440, 1920]) {
  test(`[MOCK CONTRACT] product reading: open responses and white question bubbles, exact preview and full page preserve source at ${width}px`, async ({page}) => {
    await page.setViewportSize({width,height:900});
    const writes:string[]=[];
    let selectedOffset=0;
    await page.addInitScript(()=>{
      localStorage.setItem("studio.project","visual-project");
      localStorage.setItem("studio.conversation.visual-project","visual-conversation");
    });
    const block=table();block.result.query.source_kind="RAW_PREVIEW";
    block.result.verification_status="UNVERIFIED";
    block.result.rows[0].transaction_id="000701";
    block.result.rows[0].amount=null;
    block.result.rows[1].amount="0";
    let countMode=false;
    const aggregate={...block,result:{...block.result,query:{...block.result.query,aggregations:[{op:'count',field_id:null}]},fields:['count_rows_0'],field_labels:{count_rows_0:'Số dòng'},rows:[{count_rows_0:75}],total_count:1,truncated:false}};
    const short="Xem dữ liệu nguồn A";
    const multiline="Giữ nguyên mã 000701\nĐây là dòng thứ hai, có đủ dấu tiếng Việt.";
    await page.route('**/api/**', async route=>{
      const path=new URL(route.request().url()).pathname;
      if(route.request().method()!=="GET")writes.push(path);
      if(path==='/api/session')return route.fulfill({json:{workspace_id:'synthetic',actor_id:'reader',role:'owner'}});
      if(path==='/api/settings')return route.fulfill({json:{policy:{mode:'LOCAL_ONLY',allow_external_ai:false},gemini_requests_remaining:null}});
      if(path==='/api/projects/visual-project')return route.fulfill({json:{id:'visual-project',name:'Dữ liệu tổng hợp',business_scope:'synthetic',classification:'TEST'}});
      if(path==='/api/conversations/visual-conversation')return route.fulfill({json:{conversation,has_more:false,items:[{id:'short',role:'user',text:short,context,created_at:conversation.created_at},{id:'long',role:'user',text:multiline,context,created_at:conversation.created_at},{id:'response',role:'assistant',workflow_id:'reading-workflow',context,created_at:conversation.created_at}]}});
      if(path==='/api/agent/workflows/reading-workflow')return route.fulfill({json:{id:'reading-workflow',conversation_id:conversation.id,context,state:'COMPLETED',updated_at:'reading',detail:{intent:{intent:'EXPLORE_DATA'},reviews:[],steps:[],blocks:[countMode?aggregate:block]}}});
      if(path.endsWith('/query-pages')){
        const q=route.request().postDataJSON();selectedOffset=q.offset;
        return route.fulfill({json:{...block.result,query:q,offset:q.offset,rows:block.result.rows.map((r,i)=>({...r,transaction_id:`000${726+i}`,source_provenance:[{source_table_id:'visual-table',row:q.offset+i+2,sheet:'Sheet1'}]}))}});
      }
      if(path==='/api/agent/source-rows'){
        const body=route.request().postDataJSON();expect(body.row).toBe(selectedOffset+2);
        return route.fulfill({json:{rows:[{reference:'000726',amount:'0'}]}});
      }
      if(route.request().method()!=='GET')throw Error('Unexpected product write '+path);
      return route.fulfill({json:{items:[],total:0,has_more:false}});
    });
    await page.goto('/');
    const toolbar=page.getByLabel('Công cụ hội thoại',{exact:true});
    expect((await toolbar.boundingBox())!.height).toBeLessThanOrEqual(44);
    const transcript=page.locator('.assistant-scroll');
    const beforeMenu=(await transcript.boundingBox())!;
    expect(beforeMenu.y).toBeLessThanOrEqual(130);
    if(width>=1366)expect(beforeMenu.width).toBeGreaterThanOrEqual(Math.min(1100,width-320));
    await page.getByLabel('Tùy chọn hội thoại',{exact:true}).click();
    await expect(page.getByLabel('Chế độ hội thoại',{exact:true})).toBeVisible();
    expect(await transcript.boundingBox()).toEqual(beforeMenu);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.getByLabel('Tùy chọn hội thoại',{exact:true}).press('Escape');
    await expect(page.getByLabel('Chế độ hội thoại',{exact:true})).not.toBeVisible();
    await expect(page.getByLabel('Tùy chọn hội thoại',{exact:true})).toBeFocused();
    await page.getByLabel('Tùy chọn hội thoại',{exact:true}).click();
    await page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true}).click();
    await expect(page.getByLabel('Chế độ hội thoại',{exact:true})).not.toBeVisible();
    expect(await transcript.boundingBox()).toEqual(beforeMenu);
    const user=page.getByRole('article',{name:'Tin nhắn của bạn'}).first();
    await expect(user).toContainText(short);
    const typography=await user.locator('p').evaluate(el=>{const s=getComputedStyle(el);return{height:el.getBoundingClientRect().height,line:parseFloat(s.lineHeight),text:el.textContent};});
    if(width>=768)expect(typography.height).toBeLessThanOrEqual(typography.line+1);
    await expect(page.getByRole('article',{name:'Tin nhắn của bạn'}).nth(1).locator('p')).toHaveText(multiline);
    expect(await user.evaluate(el=>getComputedStyle(el).backgroundColor)).toBe('rgb(255, 255, 255)');
    const composer=page.locator('.assistant-composer');expect(await composer.evaluate(el=>getComputedStyle(el).backgroundColor)).toBe('rgb(255, 255, 255)');
    const response=page.getByRole('article',{name:'Phản hồi của trợ lý'});
    for(const text of [user.locator('p'),composer.locator('textarea')])expect(await text.evaluate(el=>getComputedStyle(el).fontSize)).toBe('16px');
    for(const surface of [user,composer]){
      const appearance=await surface.evaluate(el=>{const s=getComputedStyle(el);return{background:s.backgroundColor,border:s.borderTopWidth,color:s.borderTopColor,shadow:s.boxShadow};});
      expect(appearance.background).toBe('rgb(255, 255, 255)');
      expect(appearance.border).toBe('1px');expect(appearance.color).not.toBe('rgb(255, 255, 255)');
      expect(appearance.shadow).not.toBe('none');
    }
    expect(await response.evaluate(el=>getComputedStyle(el).borderTopWidth)).toBe('0px');
    expect(await response.evaluate(el=>getComputedStyle(el).boxShadow)).toBe('none');
    const contentBox=(await response.locator('.agent-workflow').boundingBox())!;
    const metadataBox=(await response.locator('.message-metadata').boundingBox())!;
    expect(metadataBox.y).toBeGreaterThanOrEqual(contentBox.y+contentBox.height-1);
    expect(await user.locator('.message-metadata').evaluate(el=>getComputedStyle(el).float)).toBe('none');
    const userTextBefore=await user.locator('p').boundingBox();
    await user.getByLabel('Thông tin tin nhắn',{exact:true}).click();
    await expect(user.locator('.message-metadata small')).toBeVisible();
    expect(await user.locator('p').boundingBox()).toEqual(userTextBefore);
    const timestamp=(await user.locator('.message-metadata small').boundingBox())!;
    expect(timestamp.x).toBeGreaterThanOrEqual(0);expect(timestamp.x+timestamp.width).toBeLessThanOrEqual(width);
    await user.getByLabel('Thông tin tin nhắn',{exact:true}).press('Escape');
    await expect(user.locator('.message-metadata small')).not.toBeVisible();
    await expect(user.getByLabel('Thông tin tin nhắn',{exact:true})).toBeFocused();

    await expect(page.locator('.agent-workflow-state')).toHaveText('Đã đọc dữ liệu; chưa chuẩn hóa');
    const result=page.getByRole('region',{name:'Kết quả truy vấn',exact:true});
    await expect(result).toContainText('75 dòng dữ liệu');await expect(result).toContainText('Đang xem 10 dòng');
    await expect(result).toContainText('Ý nghĩa các cột chưa được xác nhận');
    expect(await result.locator('table').evaluate(el=>getComputedStyle(el).fontSize)).toBe('14px');
    await expect(result.locator('tbody tr')).toHaveCount(10);
    await expect(result.locator('tbody tr').first()).toContainText('000701');
    await expect(result.locator('tbody tr').first()).toContainText('—');
    await expect(result.locator('tbody tr').nth(1)).toContainText('0');
    await result.getByRole('button',{name:'Xem đầy đủ dữ liệu',exact:true}).click();
    const modal=page.getByRole('dialog',{name:'Dữ liệu chi tiết',exact:true});
    expect(await modal.locator('table').evaluate(el=>getComputedStyle(el).fontSize)).toBe('14px');
    await expect(modal.locator('tbody tr')).toHaveCount(25);expect(writes).toEqual([]);
    await modal.getByRole('button',{name:'Tiếp',exact:true}).click();await expect(modal).toContainText('Trang 2');
    await modal.getByRole('button',{name:'Xem dòng gốc',exact:true}).first().click();
    const source=page.getByRole('dialog',{name:'Dòng dữ liệu nguồn',exact:true});await expect(source).toContainText('000726');
    await page.keyboard.press('Escape');await expect(modal).toContainText('Trang 2');
    await page.keyboard.press('Escape');await expect(result).toContainText('Trang 2');
    expect(writes).toEqual(['/api/agent/workflows/reading-workflow/query-pages','/api/agent/source-rows']);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await mkdir(`../runtime/product-polish/candidate/${width}`,{recursive:true});
    await page.screenshot({path:`../runtime/product-polish/candidate/${width}/reading.png`,fullPage:true});
    countMode=true;await page.reload();
    await expect(result).toContainText('Kết quả đếm: 75 dòng dữ liệu');
    await expect(result).not.toContainText('1 nhóm kết quả');
    aggregate.result.rows[0].count_rows_0=0;await page.reload();
    await expect(result).toContainText('Kết quả đếm: 0 dòng dữ liệu');

  });
}
