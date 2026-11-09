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
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Đến nội dung chính" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
  const prepare = page.getByRole("button", { name: /Chuẩn hóa dữ liệu/ });
  await prepare.focus();
  await expect(prepare).toBeFocused();
  await prepare.press("Enter");
  await expect(page.getByLabel("Câu hỏi cho AI Assistant", { exact: true })).toHaveValue(/đề xuất cách chuẩn hóa/);
  await page.getByLabel("Câu hỏi cho AI Assistant",{exact:true}).fill("Đối soát giúp tôi");
  await expect(prepare).toBeDisabled();
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

test(`[${process.env.STUDIO_LIVE_PROVIDER==='GEMINI'?'LIVE GEMINI':'LOCAL ORACLE'}] Date findings in Chat preserve raw values and source evidence`,async({page})=>{
  const live=process.env.STUDIO_LIVE_PROVIDER==='GEMINI';
  if(live)test.setTimeout(120000);
  await page.addInitScript(()=>{localStorage.clear();sessionStorage.clear();});
  await page.goto('/');
  await expect(page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true})).toBeEnabled();
  const before=await(await page.request.get('/api/settings')).json();
  const raw='ID,Date\n0001,2026-10-01\n0002,2026-02-29\n';
  await page.locator('.assistant-composer input[type=file]').setInputFiles({
    name:`date-check-${crypto.randomUUID()}.csv`,mimeType:'text/csv',buffer:Buffer.from(raw),
  });
  await page.getByRole('button',{name:'Gửi câu hỏi',exact:true}).click();
  const workflows=page.getByRole('region',{name:'Công việc của AI Assistant',exact:true});
  await expect(workflows).toHaveCount(1);
  await expect(workflows).toContainText('Đã đọc dữ liệu; chưa chuẩn hóa');
  await page.locator('#project-select').click();
  await page.getByText('Phân loại dự án hiện tại',{exact:true}).click();
  await page.getByLabel('Nhóm dự án',{exact:true}).selectOption('TEST');
  await page.getByRole('button',{name:'Xác nhận phân loại',exact:true}).click();
  await expect(page.getByText('Đã lưu phân loại. Dữ liệu và lịch sử vẫn được giữ nguyên.',{exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  if(live){
    await page.getByLabel("Tùy chọn hội thoại",{exact:true}).click();
    await page.getByRole('combobox',{name:'Trợ lý cho tin nhắn mới',exact:true}).selectOption('GEMINI');
    await page.keyboard.press('Escape');
  }
  await page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true}).fill(live
    ? 'Hãy kiểm tra giúp mình: trong tệp này, những hàng nào chứa ngày bị ghi sai?'
    : 'Những dòng lỗi ngày tháng nằm ở đâu?');
  const delivery=live?page.waitForResponse(response=>response.url().endsWith('/assistant/messages')&&response.request().method()==='POST'):null;
  await page.getByRole('button',{name:'Gửi câu hỏi',exact:true}).click();
  const accepted=delivery?await(await delivery).json():null;
  if(live)await writeFile(test.info().outputPath('live-receipt.json'),JSON.stringify({provider:'GEMINI',job_id:accepted.job_id,project_id:await page.locator('#project-select').getAttribute('data-project-id'),requests_before:before.gemini_requests_used},null,2));
  await expect(workflows).toHaveCount(2);
  const findings=workflows.last().getByRole('region',{name:'Kết quả truy vấn',exact:true});
  await expect(findings).toContainText('Chỉ gồm dòng có cảnh báo ngày',{timeout:live?90000:15000});
  await expect(findings).toContainText('0002');
  await expect(findings).toContainText('2026-02-29');
  await expect(findings.getByRole('cell',{name:'0001',exact:true})).toHaveCount(0);
  await findings.getByRole('button',{name:'Xem dòng gốc',exact:true}).click();
  const evidence=page.getByRole('dialog',{name:'Dòng dữ liệu nguồn',exact:true});
  await expect(evidence).toContainText('2026-02-29');
  await expect(evidence).toContainText('0002');
  await page.keyboard.press('Escape');
  expect((await(await page.request.get('/api/settings')).json()).gemini_requests_used).toBe(before.gemini_requests_used+(live?1:0));
});

const paymentJourney = process.env.STUDIO_JOURNEY_DATASET === 'PAYMENT';
for (const sharedReview of paymentJourney ? [true] : [false,true]) test(`[LOCAL ORACLE] Three new ${paymentJourney?'payment':process.env.STUDIO_JOURNEY_DATASET==='MAINTENANCE'?'maintenance':'inventory'} sources through Chat approval, reconciliation and export${sharedReview ? ' with shared business facts' : ''}`,async({page})=>{
  test.setTimeout(120000);
  const viewportWidth=Number(process.env.STUDIO_JOURNEY_WIDTH??1440);
  await page.setViewportSize({width:viewportWidth,height:900});
  const vietnameseHeaders=process.env.STUDIO_JOURNEY_HEADERS==='VI';
  const maintenance=process.env.STUDIO_JOURNEY_DATASET==='MAINTENANCE'
    ? JSON.parse(await readFile('../tests/fixtures/browser-maintenance-specifications.json','utf8')) as {
      headers:string[];names:string[];entity:string;grain:string;metric:string;values:string[][][];
      expected:{equal:number;mismatch:number;unmatched:number;signed:string;absolute:string;mismatch_id:string;left_amount:string;right_amount:string};
    } : null;
  const entity=maintenance?.entity??(paymentJourney?'payment':'inventory');
  const grain=maintenance?.grain??(paymentJourney?'payment_reference':'stock_item');
  const metric=maintenance?.metric??(paymentJourney?'settled_amount':'stock_value');
  const basis=paymentJourney?'paid':'gross';
  const headers=maintenance?.headers??(paymentJourney?['Mã thanh toán','Ngày ghi nhận','Tiền đã thanh toán','Đơn vị tiền tệ']:vietnameseHeaders
    ? ['Mã hàng','Ngày kiểm kê','Giá trị gộp','Đơn vị tiền tệ']
    : ['Stock ID','Snapshot Date','Gross Amount','Currency']);
  const [keyHeader,,moneyHeader]=headers;
  const suffix=crypto.randomUUID().slice(0,8);
  const names=(maintenance?.names??(paymentJourney?['Don-hang','Thanh-toan','Ngan-hang']:['So-ton','Kiem-ke','Ton-du-phong'])).map(name=>`${name}-${suffix}.csv`);
  const values=maintenance?.values??[
    [['0001','100.00'],['0002','250.00'],['0003','25.00']],
    [['0001','100.00'],['0002','200.00'],['0004','15.00']],
    [['0001','100.00'],['0002','200.00'],['0004','15.01']],
  ];
  const expected=maintenance?.expected??{equal:1,mismatch:1,unmatched:2,signed:'50.00',absolute:'50.00',mismatch_id:'0002',left_amount:'250.00',right_amount:'200.00'};
  const firstId=values[0][0][0];
  const receipts:Record<string,unknown>={names,headers,viewportWidth,sharedReview,entity,grain,metric,expected};
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
  await dialog.getByLabel('Tên dự án',{exact:true}).fill(`UAT ${paymentJourney?'thanh toán':maintenance?'bảo trì':'tồn kho'} ${suffix}`);
  await dialog.getByLabel('Phạm vi nghiệp vụ',{exact:true}).fill(paymentJourney?'Đối chiếu số tiền đã thanh toán theo mã thanh toán giữa đơn hàng, cổng thanh toán và ngân hàng. Dữ liệu tổng hợp.':maintenance?'Đối chiếu chứng từ bảo trì với khoản thu, có hoàn tiền và số không; dữ liệu tổng hợp.':'Đối chiếu số dư giá trị tồn theo mã hàng, dữ liệu tổng hợp.');
  await dialog.getByRole('combobox',{name:'Nhóm dự án',exact:true}).selectOption('TEST');
  await dialog.getByRole('button',{name:'Tạo dự án',exact:true}).click();
  await expect(dialog).not.toBeVisible();
  const projectId=(await page.locator('#project-select').getAttribute('data-project-id'))!;
  receipts.project_id=projectId;
  await expect(page.locator('#project-select')).toContainText('Thử nghiệm');
  await page.locator('.assistant-composer input[type=file]').setInputFiles(names.map((name,index)=>({name,mimeType:'text/csv',buffer:Buffer.from(
    headers.join(',')+'\n'+values[index].map(([id,amount])=>`${id},2026-11-01,${amount},VND\n`).join('')
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
  if(sharedReview){
    const common=page.getByRole('region',{name:'Thông tin chung cho các nguồn',exact:true});
    const apply=common.getByRole('button',{name:'Xác nhận và điền vào bản nháp',exact:true});
    await expect(apply).toBeDisabled();
    await common.getByLabel('Loại dữ liệu dùng chung',{exact:true}).fill(entity);
    await common.getByLabel('Mỗi dòng của các nguồn là gì?',{exact:true}).fill(grain);
    await common.getByLabel('Múi giờ dùng chung',{exact:true}).selectOption('UTC');
    await common.getByLabel('Cơ sở tiền dùng chung',{exact:true}).selectOption(basis);
    await common.getByLabel('Khoản tiền dùng chung là gì?',{exact:true}).fill(metric);
    await common.getByLabel('Cột khóa chung (tùy chọn)',{exact:true}).selectOption(keyHeader);
    await page.reload();
    await expect(common.getByLabel('Khoản tiền dùng chung là gì?',{exact:true})).toHaveValue(metric);
    await apply.click();
    manualFields+=6;
    for(const name of names){
      const card=cards.filter({hasText:name});
      await expect(card.getByRole('textbox',{name:'Loại giao dịch',exact:true})).toHaveValue(entity);
      await expect(card.getByRole('textbox',{name:'Mỗi dòng đại diện cho điều gì?',exact:true})).toHaveValue(grain);
      await expect(card.getByRole('checkbox',{name:keyHeader,exact:true})).toBeChecked();
    }
  }else{
  for(const name of names){
    const card=cards.filter({hasText:name});
    await card.getByRole('textbox',{name:'Loại giao dịch',exact:true}).fill(entity);
    await card.getByRole('textbox',{name:'Mỗi dòng đại diện cho điều gì?',exact:true}).fill(grain);
    await card.getByRole('checkbox',{name:keyHeader,exact:true}).check();
    await card.getByRole('combobox',{name:'Múi giờ của nguồn',exact:true}).selectOption('UTC');
    await card.getByRole('combobox',{name:`Cơ sở tiền của ${moneyHeader}`,exact:true}).selectOption('gross');
    const meaning=card.getByRole('textbox',{name:'Khoản tiền này là gì?',exact:true});
    await meaning.fill(metric);await meaning.press('Tab');
    manualFields+=6;
  }
  }
  await page.getByRole('button',{name:'Duyệt 3 nguồn và chuẩn hóa',exact:true}).click();
  await expect(cards).toHaveCount(0);
  const work=page.getByRole('region',{name:'Công việc của AI Assistant',exact:true}).last();
  await expect(work.getByRole('status').first()).toContainText('Đã hoàn thành');
  receipts.upload_to_canonical_ms=Date.now()-start;
  async function send(question:string){
    await page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true}).fill(question);
    await page.getByRole('button',{name:'Gửi câu hỏi',exact:true}).click();
    const message=page.getByRole('article',{name:'Tin nhắn của bạn',exact:true}).filter({
      has:page.getByText(question,{exact:true}),
    });
    await expect(message.locator('xpath=following-sibling::article[1]').getByRole('region',{
      name:'Công việc của AI Assistant',exact:true,
    })).toBeVisible();
  }
  await send(`Mở bảng gốc trong tệp “${names[0]}”`);
  await expect(work.locator('.agent-table')).toContainText(firstId);
  await send(`Mở bản tự chuẩn bị của tệp “${names[0]}”`);
  await expect(work).toContainText('Đây là bản tự chuẩn bị để xem và tìm kiếm');
  await expect(work.locator('.agent-table')).toContainText(firstId);
  async function reconcilePair(left:string,right:string){
    await send(`Đối soát “${left}” với “${right}”`);
    const scope=page.getByRole('group',{name:'Kỳ và phạm vi dữ liệu',exact:true});
    await scope.getByLabel('Tháng đối soát',{exact:true}).fill('2026-11');
    await expect(scope.getByLabel('Ngày đầu kỳ',{exact:true})).toHaveValue('2026-11-01');
    await expect(scope.getByLabel('Ngày sau cuối kỳ',{exact:true})).toHaveValue('2026-12-01');
    await scope.getByRole('combobox',{name:/^Múi giờ đối soát/}).selectOption('UTC');
    await scope.getByLabel('Thời điểm chốt dữ liệu (UTC)',{exact:true}).fill('2026-12-02T00:00');
    await scope.getByRole('checkbox').check();manualFields+=4;
    await scope.getByRole('button',{name:'Kiểm tra phạm vi và tìm khóa',exact:true}).click();
    await expect(cards.getByText('Phương án liên kết đã kiểm tra',{exact:true})).toBeVisible();
    const runRequest=page.waitForResponse(response=>response.url().endsWith('/decisions')&&response.request().method()==='POST');
    await cards.getByRole('button',{name:'Duyệt quy tắc và đối soát',exact:true}).click();
    expect((await runRequest).ok()).toBe(true);
    await expect(work.getByRole('status').first()).toContainText('Đã hoàn thành');
    const summary=await(await page.request.get(`/api/projects/${projectId}/summary`)).json();
    expect(summary.latest_verified_run_id).toBeTruthy();
    return summary.latest_verified_run_id as string;
  }
  const runId=await reconcilePair(names[0],names[1]);
  const snapshot=await(await page.request.get(`/api/runs/${runId}/metrics`)).json();
  expect(snapshot.comparison_counts.EQUAL).toBe(expected.equal);
  expect(snapshot.comparison_counts.AMOUNT_MISMATCH).toBe(expected.mismatch);
  expect(snapshot.linkage_counts.UNMATCHED).toBe(expected.unmatched);
  expect(snapshot.monetary[0].signed_variance).toBe(expected.signed);
  expect(snapshot.monetary[0].absolute_variance).toBe(expected.absolute);
  receipts.run_id=runId;receipts.upload_to_verified_ms=Date.now()-start;
  await send('Tính tổng chênh lệch tuyệt đối');
  await expect(work).toContainText('Chênh lệch tuyệt đối');
  await work.getByRole('button',{name:'Mở kết quả và bằng chứng',exact:true}).click();
  const reportName={name:'Chi tiết kết quả đã xác minh',exact:true};
  const report=page.getByRole('dialog',reportName).or(page.getByRole('complementary',reportName));
  const chart=report.getByRole('img',{name:'Phân bố trạng thái đối soát'});
  await chart.scrollIntoViewIfNeeded();
  await expect(chart).toBeVisible();
  await page.screenshot({path:test.info().outputPath(`${maintenance?'maintenance':'inventory'}-verified-chart.png`)});
  await page.keyboard.press('Escape');
  await expect(report).not.toBeVisible();
  await send('Hiển thị những nhóm UNMATCHED ở run đang mở.');
  await expect(work.locator('.agent-table')).toContainText(`${expected.unmatched} dòng trong trang`);
  await send('Tong quan ket qua nay va cac chi so chenh lech giup toi.');
  await expect(work).toContainText('Chênh lệch tuyệt đối');
  await send('Sắp hai giao dịch bị lệch tiền nhiều nhất theo mức lệch giảm dần.');
  await expect(work.locator('.agent-table')).toContainText(expected.absolute);
  const folder=`../runtime/automation-${paymentJourney?'payment':maintenance?'maintenance':'inventory'}/${suffix}`;
  await mkdir(folder,{recursive:true});
  await send('Lưu đúng các dòng vừa liệt kê thành tệp CSV.');
  const pageFile=page.waitForEvent('download');
  await work.getByRole('link',{name:'Tải bảng đang xem CSV',exact:true}).click();
  await (await pageFile).saveAs(`${folder}/displayed.csv`);
  const rows=(await readFile(`${folder}/displayed.csv`,'utf8')).split(/\r?\n/).filter(row=>row.startsWith('Displayed results,'));
  expect(rows).toHaveLength(2);
  expect(rows[1].split(',').slice(0,-1)).toEqual(['Displayed results','AMOUNT_MISMATCH',expected.left_amount,expected.right_amount,expected.signed,expected.absolute,'VND']);
  expect(rows[1].split(',').at(-1)).toMatch(/^[0-9a-f-]{36}$/);
  const groupId=rows[1].split(',').at(-1);
  await send('Giải thích mục thứ nhất của danh sách vừa trả, giữ nguyên phạm vi này.');
  await expect(work).toContainText(`${expected.left_amount} / ${expected.right_amount} / ${expected.signed}`);
  const evidenceResponse=page.waitForResponse(response=>response.url().endsWith(`/runs/${runId}/groups/${groupId}/evidence`));
  await work.getByRole('button',{name:'Mở kết quả và bằng chứng',exact:true}).click();
  expect((await evidenceResponse).ok()).toBe(true);
  const evidenceName={name:'Bằng chứng đối soát',exact:true};
  const evidence=page.getByRole('dialog',evidenceName).or(page.getByRole('complementary',evidenceName));
  await expect(evidence).toContainText(expected.mismatch_id);
  await page.keyboard.press('Escape');
  await expect(evidence).not.toBeVisible();
  await send('Xuất báo cáo Excel của lần đối soát này');
  const file=page.waitForEvent('download');
  await work.getByRole('link',{name:/Tải.*XLSX/i}).click();
  const download=await file;
  const exportFile=maintenance?'maintenance.xlsx':'inventory.xlsx';
  await download.saveAs(`${folder}/${exportFile}`);receipts.export_file=exportFile;
  await page.reload();
  await expect(work.getByRole('link',{name:/Tải.*XLSX/i})).toBeVisible();
  if(paymentJourney){
    const bankRun=await reconcilePair(names[1],names[2]);
    expect(bankRun).not.toBe(runId);
    const bank=await(await page.request.get(`/api/runs/${bankRun}/metrics`)).json();
    expect(bank.comparison_counts.EQUAL).toBe(2);
    expect(bank.comparison_counts.AMOUNT_MISMATCH).toBe(1);
    expect(bank.monetary[0].signed_variance).toBe('-0.01');
    expect(bank.monetary[0].absolute_variance).toBe('0.01');
    receipts.bank_run_id=bankRun;
    await send('Xuất báo cáo Excel của lần đối soát này');
    const bankFile=page.waitForEvent('download');
    await work.getByRole('link',{name:/Tải.*XLSX/i}).click();
    await (await bankFile).saveAs(`${folder}/bank.xlsx`);
    receipts.bank_export_file='bank.xlsx';
  }
  expect((await(await page.request.get('/api/settings')).json()).gemini_requests_used).toBe(before.gemini_requests_used);
  expect(errors).toEqual([]);
  await writeFile(`${folder}/receipt.json`,JSON.stringify({...receipts,clicks,manualFields,approvedResources:paymentJourney?5:4,approvalClicks:paymentJourney?3:2,pageErrors:errors},null,2));
});
