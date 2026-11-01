import {test,expect} from "@playwright/test";

test("Agent landing without a project does not create metadata or call cloud",async({page})=>{
  await page.addInitScript(()=>{if(!sessionStorage.getItem("agent-test-initialized")){localStorage.clear();sessionStorage.clear();sessionStorage.setItem("agent-test-initialized","1");}});
  const mutations:string[]=[];page.on("request",r=>{if(r.method()==="POST"||r.method()==="PATCH")mutations.push(new URL(r.url()).pathname);});
  await page.goto("/");
  await expect(page.getByRole("heading",{name:"Bạn muốn làm gì với dữ liệu hôm nay?"})).toBeVisible();
  await expect(page.getByText("Chọn hoặc tạo dự án để xem dữ liệu.",{exact:false})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Đính kèm CSV hoặc Excel"})).toBeEnabled();
  await page.getByLabel("Câu hỏi cho Trợ lý",{exact:true}).fill("Đối soát giúp tôi");
  await page.getByRole("button",{name:"Gửi câu hỏi",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("Tải CSV/Excel lên");
  expect(mutations).toEqual([]);
});

test("Agent inline upload bootstraps once, profiles real files and reopens without cloud",async({page})=>{
  test.setTimeout(90000);
  await page.addInitScript(()=>{if(!sessionStorage.getItem("agent-test-initialized")){localStorage.clear();sessionStorage.clear();sessionStorage.setItem("agent-test-initialized","1");}});
  await page.goto("/");
  await expect(page.getByRole("heading",{name:"Bạn muốn làm gì với dữ liệu hôm nay?"})).toBeVisible();
  const before=await(await page.request.get("/api/settings")).json();
  const marker=crypto.randomUUID();
  await page.locator('.assistant-composer input[type="file"]').setInputFiles([
    {name:`Ledger-${marker}.csv`,mimeType:"text/csv",buffer:Buffer.from("voucher,amount\n000701,25.00\n000702,12.75\n")},
    {name:`Vouchers-${marker}.csv`,mimeType:"text/csv",buffer:Buffer.from("voucher,amount\n000701,25.00\n000702,10.00\n")},
  ]);
  const attachment=page.waitForResponse(r=>r.url().endsWith("/agent/attachments")&&r.request().method()==="POST");
  await page.getByRole("button",{name:"Gửi câu hỏi",exact:true}).click();
  const receipt=await(await attachment).json();expect(receipt.items).toHaveLength(2);expect(receipt.scope_confirmed).toBe(false);
  const pid=receipt.project_id;
  await expect(page.getByRole("region",{name:"Công việc của Trợ lý",exact:true})).toContainText("Đã hoàn thành",{timeout:45000});
  await expect(page.locator(".agent-table")).toHaveCount(2);
  await expect(page.locator(".agent-table").first()).toContainText("000701");
  await expect(page.locator(".agent-table").first()).toContainText("000702");
  const project=await(await page.request.get(`/api/projects/${pid}`)).json();
  expect(project.business_scope).toBe(`UNCONFIRMED:${pid}`);expect(project.classification).toBe("UNKNOWN");
  const classified=await page.request.patch(`/api/projects/${pid}/classification`,{headers:{Origin:"http://127.0.0.1:18180"},data:{classification:"TEST",expected_classification:"UNKNOWN"}});
  expect(classified.status()).toBe(200);
  await page.locator(".agent-table").first().getByRole("button",{name:"Xem dòng gốc"}).first().click();
  await expect(page.getByRole("dialog",{name:"Dòng dữ liệu nguồn"})).toContainText("000701");
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(page.locator(".agent-table")).toHaveCount(2);
  const after=await(await page.request.get("/api/settings")).json();expect(after.gemini_requests_used).toBe(before.gemini_requests_used);
  const datasets=await(await page.request.get(`/api/datasets?project_id=${pid}`)).json();expect(datasets.total).toBe(2);
});

for(const width of [390,768,1366,1440,1920]){
  test(`Agent empty composer responsive ${width}px and keyboard`,async({page})=>{
    await page.setViewportSize({width,height:900});
    await page.addInitScript(()=>{localStorage.clear();sessionStorage.clear();});
    await page.goto("/");
    await expect(page.getByLabel("Câu hỏi cho Trợ lý",{exact:true})).toBeVisible();
    await page.getByLabel("Câu hỏi cho Trợ lý",{exact:true}).focus();
    await expect(page.getByLabel("Câu hỏi cho Trợ lý",{exact:true})).toBeFocused();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
    await page.locator('.assistant-composer input[type="file"]').setInputFiles({name:"wrong.pdf",mimeType:"application/pdf",buffer:Buffer.from("synthetic only")});
    await expect(page.getByRole("alert")).toContainText("CSV/XLSX");
    await expect(page.locator(".agent-file-chips")).toHaveCount(0);
  });
}
