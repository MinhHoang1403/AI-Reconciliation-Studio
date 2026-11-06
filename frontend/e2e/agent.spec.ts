import { test } from "./project-selection";
import {expect} from "@playwright/test";
import {mkdir,readFile,writeFile} from "node:fs/promises";

test("Agent landing without a project does not create metadata or call cloud",async({page})=>{
  await page.addInitScript(()=>{if(!sessionStorage.getItem("agent-test-initialized")){localStorage.clear();sessionStorage.clear();sessionStorage.setItem("agent-test-initialized","1");}});
  const mutations:string[]=[];page.on("request",r=>{if(r.method()==="POST"||r.method()==="PATCH")mutations.push(new URL(r.url()).pathname);});
  await page.goto("/");
  await expect(page.getByRole("heading",{name:"Bạn muốn xử lý dữ liệu gì?"})).toBeVisible();
  await expect(page.getByText("Chọn hoặc tạo dự án để xem dữ liệu.",{exact:false})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Đính kèm CSV hoặc Excel"})).toBeEnabled();
  await page.getByLabel("Câu hỏi cho AI Assistant",{exact:true}).fill("Đối soát giúp tôi");
  await page.getByRole("button",{name:"Gửi câu hỏi",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("Tải CSV/Excel lên");
  expect(mutations).toEqual([]);
});

test("Agent inline upload bootstraps once, profiles real files and reopens without cloud",async({page})=>{
  test.setTimeout(90000);
  await page.addInitScript(()=>{if(!sessionStorage.getItem("agent-test-initialized")){localStorage.clear();sessionStorage.clear();sessionStorage.setItem("agent-test-initialized","1");}});
  await page.goto("/");
  await expect(page.getByRole("heading",{name:"Bạn muốn xử lý dữ liệu gì?"})).toBeVisible();
  const before=await(await page.request.get("/api/settings")).json();
  const marker=crypto.randomUUID();
  await page.locator('.assistant-composer input[type="file"]').setInputFiles([
    {name:`Ledger-${marker}.csv`,mimeType:"text/csv",buffer:Buffer.from("voucher,amount\n000701,25.00\n000702,12.75\n")},
    {name:`Vouchers-${marker}.csv`,mimeType:"text/csv",buffer:Buffer.from("voucher,amount\n000701,25.00\n000702,10.00\n")},
  ]);
  const attachment=page.waitForResponse(r=>r.url().endsWith("/agent/attachments")&&r.request().method()==="POST");
  const message=page.waitForRequest(r=>r.url().endsWith("/assistant/messages")&&r.method()==="POST");
  await page.getByRole("button",{name:"Gửi câu hỏi",exact:true}).click();
  const receipt=await(await attachment).json();expect(receipt.items).toHaveLength(2);expect(receipt.scope_confirmed).toBe(false);
  const sent=(await message).postDataJSON();
  expect(sent.dataset_ids).toEqual(receipt.items.map((item:{id:string})=>item.id));
  expect(sent.command).toBe('PREPARE_UPLOAD');
  const pid=receipt.project_id;
  await expect(page.getByRole("region",{name:"Công việc của AI Assistant",exact:true})).toContainText("Đã đọc dữ liệu; chưa chuẩn hóa",{timeout:45000});
  await expect(page.locator(".agent-table")).toHaveCount(2);
  await expect(page.locator(".agent-table").first()).toContainText("000701");
  await expect(page.locator(".agent-table").first()).toContainText("000702");
  const cards=page.getByRole('region',{name:'Quyết định cần xác nhận',exact:true});
  await expect(cards).toHaveCount(2);
  await expect(cards.first().getByRole('button',{name:'Duyệt cách ghép cột và chuẩn hóa'})).toBeDisabled();
  const project=await(await page.request.get(`/api/projects/${pid}`)).json();
  expect(project.business_scope).toBe(`UNCONFIRMED:${pid}`);expect(project.classification).toBe("UNKNOWN");
  const classified=await page.request.patch(`/api/projects/${pid}/classification`,{headers:{Origin:"http://127.0.0.1:18180"},data:{classification:"TEST",expected_classification:"UNKNOWN"}});
  expect(classified.status()).toBe(200);
  await page.locator(".agent-table").first().getByRole("button",{name:"Xem dòng gốc"}).first().click();
  await expect(page.getByRole("dialog",{name:"Dòng dữ liệu nguồn"})).toContainText("000701");
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(page.locator(".agent-table")).toHaveCount(2);
  await expect(cards).toHaveCount(2);
  const card=cards.filter({hasText:`Ledger-${marker}.csv`});
  await card.getByRole('textbox',{name:'Loại giao dịch',exact:true}).fill('ledger');
  await card.getByRole('textbox',{name:'Mỗi dòng đại diện cho điều gì?',exact:true}).fill('ledger_entry');
  await card.getByRole('checkbox',{name:'voucher',exact:true}).check();
  await card.getByRole('combobox',{name:'Cơ sở tiền của amount',exact:true}).selectOption('gross');
  await card.getByRole('textbox',{name:'Khoản tiền này là gì?',exact:true}).fill('recorded_amount');
  await card.getByRole('textbox',{name:'Tiền tệ cho amount',exact:true}).fill('VND');
  await card.getByRole('textbox',{name:'Tiền tệ cho amount',exact:true}).press('Tab');
  const decision=page.waitForResponse(r=>r.url().endsWith('/decisions')&&r.request().method()==='POST');
  await card.getByRole('button',{name:'Duyệt cách ghép cột và chuẩn hóa',exact:true}).click();
  expect((await decision).ok()).toBe(true);
  await expect(card).toHaveCount(0);
  await expect(cards).toHaveCount(1);
  const after=await(await page.request.get("/api/settings")).json();expect(after.gemini_requests_used).toBe(before.gemini_requests_used);
  const datasets=await(await page.request.get(`/api/datasets?project_id=${pid}`)).json();expect(datasets.total).toBe(2);
});

for(const width of [390,768,1366,1440,1920]){
  test(`Agent empty composer responsive ${width}px and keyboard`,async({page})=>{
    await page.setViewportSize({width,height:900});
    await page.addInitScript(()=>{localStorage.clear();sessionStorage.clear();});
    await page.goto("/");
    await expect(page.getByLabel("Câu hỏi cho AI Assistant",{exact:true})).toBeVisible();
    await page.getByLabel("Câu hỏi cho AI Assistant",{exact:true}).focus();
    await expect(page.getByLabel("Câu hỏi cho AI Assistant",{exact:true})).toBeFocused();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
    await page.locator('.assistant-composer input[type="file"]').setInputFiles({name:"wrong.pdf",mimeType:"application/pdf",buffer:Buffer.from("synthetic only")});
    await expect(page.getByRole("alert")).toContainText("CSV/XLSX");
    await expect(page.locator(".agent-file-chips")).toHaveCount(0);
  });
}

test('[LOCAL ORACLE] Three new inventory sources through Chat approval, reconciliation and export',async({page})=>{
  test.setTimeout(120000);
  const suffix=crypto.randomUUID().slice(0,8);
  const names=[`So-ton-${suffix}.csv`,`Kiem-ke-${suffix}.csv`,`Ton-du-phong-${suffix}.csv`];
  const values=[
    [['0001','100.00'],['0002','250.00'],['0003','25.00']],
    [['0001','100.00'],['0002','200.00'],['0004','15.00']],
    [['0001','100.00'],['0002','200.00'],['0004','15.01']],
  ];
  const receipts:Record<string,unknown>={names,expected:{equal:1,mismatch:1,unmatched:2,signed:'50.00',absolute:'50.00'}};
  const errors:string[]=[];
  let clicks=0,manualFields=0;
  await page.exposeFunction('recordJourneyClick',()=>{clicks++;});
  await page.addInitScript(()=>document.addEventListener('click',event=>{if(event.isTrusted)void (window as unknown as {recordJourneyClick:()=>Promise<void>}).recordJourneyClick();},true));
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true})).toBeEnabled();
  const before=await(await page.request.get('/api/settings')).json();
  await page.locator('#project-select').click();
  await page.getByRole('button',{name:'Tạo dự án mới',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Tạo dự án',exact:true});
  await dialog.getByLabel('Tên dự án',{exact:true}).fill(`UAT tồn kho ${suffix}`);
  await dialog.getByLabel('Phạm vi nghiệp vụ',{exact:true}).fill('Đối chiếu số dư giá trị tồn theo mã hàng, dữ liệu tổng hợp.');
  await dialog.getByRole('button',{name:'Tạo dự án',exact:true}).click();
  await expect(dialog).not.toBeVisible();
  const projectId=(await page.locator('#project-select').getAttribute('data-project-id'))!;
  receipts.project_id=projectId;
  await page.locator('#project-select').click();
  await page.getByText('Phân loại dự án hiện tại',{exact:true}).click();
  await page.getByLabel('Nhóm dự án',{exact:true}).selectOption('TEST');
  await page.getByRole('button',{name:'Xác nhận phân loại',exact:true}).click();
  await expect(page.getByText('Đã lưu phân loại. Dữ liệu và lịch sử vẫn được giữ nguyên.',{exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  await page.locator('.assistant-composer input[type=file]').setInputFiles(names.map((name,index)=>({name,mimeType:'text/csv',buffer:Buffer.from(
    'Stock ID,Snapshot Date,Gross Amount,Currency\n'+values[index].map(([id,amount])=>`${id},2026-11-01,${amount},VND\n`).join('')
  )})));
  const upload=page.waitForResponse(response=>response.url().endsWith('/agent/attachments')&&response.request().method()==='POST');
  const start=Date.now();
  await page.getByRole('button',{name:'Gửi câu hỏi',exact:true}).click();
  const attachment=await(await upload).json();
  const uploadedIds=attachment.items.map((item:{id:string})=>item.id);
  receipts.datasets=uploadedIds;
  await expect(page.locator('.agent-table')).toHaveCount(3);
  receipts.upload_to_raw_visible_ms=Date.now()-start;
  const cards=page.getByRole('region',{name:'Quyết định cần xác nhận',exact:true});
  await expect(cards).toHaveCount(3);
  receipts.upload_to_reviews_ms=Date.now()-start;
  for(const name of names){
    const card=cards.filter({hasText:name});
    await card.getByRole('textbox',{name:'Loại giao dịch',exact:true}).fill('inventory');
    await card.getByRole('textbox',{name:'Mỗi dòng đại diện cho điều gì?',exact:true}).fill('stock_item');
    await card.getByRole('checkbox',{name:'Stock ID',exact:true}).check();
    await card.getByRole('combobox',{name:'Múi giờ của nguồn',exact:true}).selectOption('UTC');
    await card.getByRole('combobox',{name:'Cơ sở tiền của Gross Amount',exact:true}).selectOption('gross');
    const meaning=card.getByRole('textbox',{name:'Khoản tiền này là gì?',exact:true});
    await meaning.fill('stock_value');await meaning.press('Tab');
    manualFields+=6;
  }
  await page.getByRole('button',{name:'Duyệt 3 nguồn và chuẩn hóa',exact:true}).click();
  await expect(cards).toHaveCount(0);
  const work=page.getByRole('region',{name:'Công việc của AI Assistant',exact:true}).last();
  await expect(work.getByRole('status').first()).toContainText('Đã hoàn thành');
  receipts.upload_to_canonical_ms=Date.now()-start;
  async function send(question:string){
    await page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true}).fill(question);
    await page.getByRole('button',{name:'Gửi câu hỏi',exact:true}).click();
  }
  await send(`Đối soát “${names[0]}” với “${names[1]}”`);
  const scope=page.getByRole('group',{name:'Kỳ và phạm vi dữ liệu',exact:true});
  await scope.getByLabel('Ngày đầu kỳ',{exact:true}).fill('2026-11-01');
  await scope.getByLabel('Ngày sau cuối kỳ',{exact:true}).fill('2026-12-01');
  await scope.getByRole('combobox',{name:/^Múi giờ đối soát/}).selectOption('UTC');
  await scope.getByLabel('Thời điểm chốt dữ liệu (UTC)',{exact:true}).fill('2026-12-02T00:00');
  await scope.getByRole('checkbox').check();manualFields+=5;
  await scope.getByRole('button',{name:'Kiểm tra phạm vi và tìm khóa',exact:true}).click();
  await expect(cards.getByText('Phương án liên kết đã kiểm tra',{exact:true})).toBeVisible();
  const runRequest=page.waitForResponse(response=>response.url().endsWith('/decisions')&&response.request().method()==='POST');
  await cards.getByRole('button',{name:'Duyệt quy tắc và đối soát',exact:true}).click();
  expect((await runRequest).ok()).toBe(true);
  await expect(work.getByRole('status').first()).toContainText('Đã hoàn thành');
  const runs=await(await page.request.get(`/api/projects/${projectId}/summary`)).json();
  expect(runs.latest_verified_run_id).toBeTruthy();
  const runId=runs.latest_verified_run_id;
  const snapshot=await(await page.request.get(`/api/runs/${runId}/metrics`)).json();
  expect(snapshot.comparison_counts.EQUAL).toBe(1);
  expect(snapshot.comparison_counts.AMOUNT_MISMATCH).toBe(1);
  expect(snapshot.linkage_counts.UNMATCHED).toBe(2);
  expect(snapshot.monetary[0].signed_variance).toBe('50.00');
  expect(snapshot.monetary[0].absolute_variance).toBe('50.00');
  receipts.run_id=runId;receipts.upload_to_verified_ms=Date.now()-start;
  await send('Cho tôi xem một nhóm lệch tiền lớn nhất');
  await expect(work.locator('.agent-table')).toContainText('50');
  const folder=`../runtime/automation-inventory/${suffix}`;
  await mkdir(folder,{recursive:true});
  await send('Xuất danh sách trên CSV');
  const pageFile=page.waitForEvent('download');
  await work.getByRole('link',{name:'Tải bảng đang xem CSV',exact:true}).click();
  await (await pageFile).saveAs(`${folder}/displayed.csv`);
  const rows=(await readFile(`${folder}/displayed.csv`,'utf8')).split(/\r?\n/).filter(row=>row.startsWith('Displayed results,'));
  expect(rows).toHaveLength(2);
  expect(rows[1]).toMatch(/^Displayed results,AMOUNT_MISMATCH,250\.00,200\.00,50\.00,50\.00,VND,[0-9a-f-]{36}$/);
  const groupId=rows[1].split(',').at(-1);
  await send('Giải thích nhóm thứ một');
  await expect(work).toContainText('250.00 / 200.00 / 50.00');
  const evidenceResponse=page.waitForResponse(response=>response.url().endsWith(`/runs/${runId}/groups/${groupId}/evidence`));
  await work.getByRole('button',{name:'Mở kết quả và bằng chứng',exact:true}).click();
  expect((await evidenceResponse).ok()).toBe(true);
  const evidence=page.getByRole('dialog',{name:'Bằng chứng đối soát',exact:true});
  await expect(evidence).toContainText('0002');
  await page.keyboard.press('Escape');
  await expect(evidence).not.toBeVisible();
  await send('Xuất báo cáo Excel của lần đối soát này');
  const file=page.waitForEvent('download');
  await work.getByRole('link',{name:/Tải.*XLSX/i}).click();
  const download=await file;
  await download.saveAs(`${folder}/inventory.xlsx`);
  await page.reload();
  await expect(work.getByRole('link',{name:/Tải.*XLSX/i})).toBeVisible();
  expect((await(await page.request.get('/api/settings')).json()).gemini_requests_used).toBe(before.gemini_requests_used);
  expect(errors).toEqual([]);
  await writeFile(`${folder}/receipt.json`,JSON.stringify({...receipts,clicks,manualFields,approvedResources:4,approvalClicks:2,pageErrors:errors},null,2));
});
