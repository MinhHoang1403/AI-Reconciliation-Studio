import { selectProject } from "./project-selection";
import {test,expect} from "@playwright/test";
import {readFile,mkdir,writeFile} from "node:fs/promises";
import {createHash} from "node:crypto";

type State={project_id:string;sources:Record<string,{canonical_id:string}>;runs:Record<string,{run_id:string;contract_id:string;plan:unknown;snapshot:{monetary:{absolute_variance:string}[]}}>};
async function state(){return JSON.parse(await readFile("../runtime/reconciliation-acceptance.json","utf8")) as State;}
test("T35: manual rule builder, approval, verified dashboard, exception review, exports and reopen",async({page})=>{
  test.setTimeout(120000);
  const s=await state();
  await page.goto("/");
  await expect(page.getByText("Hệ thống đã kết nối")).toBeAttached();
  await selectProject(page, s.project_id);
  await page.getByRole("button",{name:"Đối soát",exact:true}).click();
  await page.getByLabel("Nguồn tham chiếu",{exact:true}).selectOption(s.sources["shipments.csv"].canonical_id);
  await page.getByLabel("Nguồn đối ứng",{exact:true}).selectOption(s.sources["delivery-confirmations.csv"].canonical_id);
  await expect(page.getByLabel("Từ ngày",{exact:true})).toHaveValue("");
  await expect(page.getByLabel("Timezone",{exact:true})).toHaveValue("");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await page.screenshot({path:"../runtime/screenshots/reconciliation-setup-1440.png",fullPage:true});
  await page.getByLabel("Từ ngày",{exact:true}).fill("2026-10-01");
  await page.getByLabel("Đến ngày (không gồm)",{exact:true}).fill("2026-11-01");
  await page.getByLabel("Timezone",{exact:true}).fill("UTC");
  for(const side of ["nguồn trái","nguồn phải"]){
    const coverage=page.getByRole("group",{name:`Coverage ${side}`,exact:true});
    await coverage.getByLabel("Đầu kỳ nguồn",{exact:true}).fill("2026-10-01");
    await coverage.getByLabel("Cuối kỳ nguồn (không gồm)",{exact:true}).fill("2026-11-01");
    await coverage.getByRole("combobox",{name:"Độ đầy đủ",exact:true}).selectOption("CONFIRMED");
  }
  await page.getByLabel("Tôi xác nhận kỳ, múi giờ và phạm vi nguồn",{exact:true}).check();
  await page.getByRole("button",{name:"Kiểm tra điều kiện",exact:true}).click();
  await expect(page.getByText("Đã kiểm tra schema, scope, grain, metric, thời gian và khóa. Trùng khóa được giữ để review.")).toBeVisible();
  await page.getByRole("button",{name:"Lưu đề xuất thủ công",exact:true}).click();
  await page.getByRole("button",{name:"Xác nhận quy tắc và dấu số tiền",exact:true}).click();
  const acceptedResponse=page.waitForResponse(response=>new URL(response.url()).pathname==="/api/reconciliation-runs"&&response.request().method()==="POST");
  await page.getByRole("button",{name:"Chạy đối soát đã duyệt",exact:true}).click();
  const accepted=await (await acceptedResponse).json();
  await expect(page.getByLabel("Lần đối soát",{exact:true})).toHaveValue(accepted.run_id);
  await expect(page.getByText("Giá trị lệch tuyệt đối",{exact:true})).toBeVisible();
  const rid=await page.getByLabel("Lần đối soát",{exact:true}).inputValue();
  expect(rid).toBe(accepted.run_id);
  expect((await (await page.request.get(`/api/runs/${rid}`)).json()).status).toBe("VERIFIED");
  const before=await (await page.request.get(`/api/runs/${rid}/metrics`)).json();
  expect(before.monetary[0].absolute_variance).toBe("2.75");
  expect(before.full_match_rate).toEqual({numerator:1,denominator:3,percent:"33.33"});
  expect(before.eligible_units).toBe(3);
  const originalGroups=await (await page.request.get(`/api/runs/${rid}/matches`)).json();
  const mismatch=originalGroups.items.find((g:{comparison_state:string})=>g.comparison_state==="AMOUNT_MISMATCH");
  expect(mismatch.key).toContain("000702");
  expect(mismatch.linkage_state).toBe("LINKED");
  expect(mismatch.members).toHaveLength(2);
  expect(mismatch.comparisons[0]).toMatchObject({left_amount:"12.75",right_amount:"10.00",delta:"2.75"});
  expect(originalGroups.items.filter((g:{comparison_state:string})=>g.comparison_state==="EQUAL")).toHaveLength(1);
  expect(originalGroups.items.filter((g:{linkage_state:string})=>g.linkage_state==="UNMATCHED")).toHaveLength(2);
  expect((await (await page.request.get(`/api/runs/${rid}/exceptions`)).json()).total).toBe(3);
  await page.getByRole("button",{name:"Ngoại lệ",exact:true}).click();
  await page.getByLabel("Lần đối soát",{exact:true}).selectOption(rid);
  const row=page.getByRole("row").filter({has:page.getByRole("cell",{name:"Lệch tiền",exact:true})});
  await row.getByRole("button",{name:"Xem ngoại lệ",exact:true}).click();
  const dialog=page.getByRole("dialog");
  await expect(dialog.getByText("delivery_charge: 12.75 − 10.00 = 2.75 VND",{exact:true})).toBeVisible();
  const sourceRequest=page.waitForRequest(r=>decodeURIComponent(r.url()).includes(":c4?row=")&&r.method()==="GET");
  await dialog.getByRole("button",{name:"Xem nguồn delivery_charge",exact:true}).first().click();
  await sourceRequest;
  const sourceDetail=dialog.getByRole("region",{name:"Chi tiết giá trị nguồn"});
  await expect(sourceDetail.getByRole("cell",{name:"12.75",exact:true})).toBeVisible();
  await expect(sourceDetail.getByRole("cell",{name:"delivery_charge (c4)",exact:true})).toBeVisible();
  await expect(sourceDetail.getByRole("cell",{name:"CSV",exact:true})).toBeVisible();
  await expect(sourceDetail.getByRole("cell",{name:"3",exact:true})).toBeVisible();
  await page.screenshot({path:"../runtime/screenshots/reconciliation-field-evidence.png",fullPage:true});
  await dialog.getByRole("combobox",{name:"Trạng thái xử lý",exact:true}).selectOption("RESOLVED");
  await dialog.getByLabel("Lý do / ghi chú",{exact:true}).fill("Đã xem bằng chứng tổng hợp; không sửa số tiền.");
  await dialog.getByRole("button",{name:"Lưu xem xét",exact:true}).click();
  await expect(dialog).not.toBeVisible();
  expect(await (await page.request.get(`/api/runs/${rid}/metrics`)).json()).toEqual(before);
  expect(await (await page.request.get(`/api/runs/${rid}/matches`)).json()).toEqual(originalGroups);
  await mkdir("../runtime",{recursive:true});
  const exports:Record<string,unknown>={};
  for(const format of ["csv","xlsx"]){
    const infoResponse=page.waitForResponse(response=>/^\/api\/exports\/[^/]+$/.test(new URL(response.url()).pathname)&&response.request().method()==="GET");
    await page.getByRole("button",{name:format==="csv"?"Xuất CSV":"Xuất XLSX",exact:true}).click();
    const info=await (await infoResponse).json();
    await expect(page.getByRole("link",{name:"Tải báo cáo",exact:true})).toHaveAttribute("href",info.download_url);
    await expect(page.getByText(/File bất biến từ lần tạo đầu/)).toBeVisible();
    const download=await page.request.get(info.download_url);
    expect(download.status()).toBe(200);
    expect(download.headers()["content-type"]).toContain(format==="csv"?"text/csv":"spreadsheetml");
    const bytes=await download.body();
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(info.sha256);
    expect(info.review_state_scope).toBe("FIRST_GENERATION");
    expect(info.review_state_as_of).toBeTruthy();
    await writeFile(`../runtime/ui-reconciliation.${format}`,bytes);
    exports[format]=info;
  }
  await writeFile("../runtime/ui-reconciliation-evidence.json",JSON.stringify({run_id:rid,snapshot:before,groups:originalGroups,exports},null,2));
  await page.reload();
  await page.getByRole("button",{name:"Báo cáo",exact:true}).click();
  await expect(page.getByLabel("Lần đối soát",{exact:true})).toHaveValue(rid);
  await expect(page.getByRole("img",{name:"Phân bố trạng thái đối soát"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Xem bằng chứng",exact:true}).first()).toBeVisible();
  await mkdir("../runtime/screenshots",{recursive:true});
  await page.screenshot({path:"../runtime/screenshots/reconciliation-dashboard.png",fullPage:true});
});

test("Planner UI accepts sources with no common key and presents review-only suggestions (MOCK)",async({page})=>{
  const s=await state();let proposalRequests=0;
  const left=s.sources["shipments.csv"].canonical_id,right=s.sources["delivery-confirmations.csv"].canonical_id;
  await page.route("**/api/projects/*/canonical-catalogue",async route=>{
    const response=await route.fetch();const data=await response.json();
    const source=data.items.find((c:{canonical:{id:string}})=>c.canonical.id===right);
    source.schema_definition.fields.forEach((f:{id:string;name:string})=>{if(f.id==="tracking_id"){f.id="external_tracking";f.name="External tracking";}});
    source.schema_definition.business_key_fields=["external_tracking"];
    // Remove common key candidates only in this UI mock, never from stored artifacts.
    const reference=data.items.find((c:{canonical:{id:string}})=>c.canonical.id===left);
    reference.schema_definition.business_key_fields=["tracking_id"];
    await route.fulfill({response,json:data});
  });
  await page.route("**/api/reconciliation-plans/ai",async route=>{
    const body=route.request().postDataJSON();proposalRequests++;
    expect(body.request.left.canonical_id).toBe(left);expect(body.request.right.canonical_id).toBe(right);
    expect(body.request.join_keys).toBeUndefined();expect(body.plan).toBeUndefined();
    expect(body.request.timezone).toBeUndefined();expect(body.request.period_start).toBeUndefined();
    await route.fulfill({status:202,json:{job_id:"mock-planning",status:"QUEUED"}});
  });
  await page.route("**/api/jobs/mock-planning",route=>route.fulfill({json:{id:"mock-planning",status:"SUCCEEDED",result:{plan_id:"mock-proposal"}}}));
  await page.route("**/api/reconciliation-plans/mock-proposal",route=>route.fulfill({json:{id:"mock-proposal",origin:"GEMINI",contract_id:null,proposal:{status:"NEEDS_REVIEW",plan:null,reasoning:"Different field IDs refer to the same tracking identifier",missing_requirements:["Confirm reporting period and coverage"],suggestions:{left_role:"reference",right_role:"counterpart",join_keys:[{left:"tracking_id",right:"external_tracking"}],comparison_metrics:[],cardinality:"ONE_TO_ONE",comparison_grain:"delivery",aggregation:"NONE",evidence_ids:[left,right]}}}}));
  await page.goto("/");await selectProject(page, s.project_id);
  await page.getByRole("button",{name:"Đối soát",exact:true}).click();
  await page.getByLabel("Nguồn tham chiếu",{exact:true}).selectOption(left);
  await page.getByLabel("Nguồn đối ứng",{exact:true}).selectOption(right);
  await page.getByRole("button",{name:"AI đề xuất kế hoạch (có dùng quota)",exact:true}).click();
  await expect(page.getByText("Confirm reporting period and coverage",{exact:true})).toBeVisible();
  await expect(page.getByText(/tracking_id ↔ external_tracking/)).toBeVisible();
  await expect(page.getByRole("button",{name:"Xác nhận quy tắc và dấu số tiền",exact:true})).toBeDisabled();
  await expect(page.getByLabel("Từ ngày",{exact:true})).toHaveValue("");
  expect(proposalRequests).toBe(1);
  await page.route("**/api/jobs/mock-planning",route=>route.fulfill({json:{id:"mock-planning",status:"BLOCKED",error_code:"CLOUD_BUDGET_EXHAUSTED"}}));
  await page.getByRole("button",{name:"AI đề xuất kế hoạch (có dùng quota)",exact:true}).click();
  await expect(page.getByText(/CLOUD_BUDGET_EXHAUSTED.*Có thể tạo rule thủ công/)).toBeVisible();
  await page.getByText("Chỉnh khóa và chỉ tiêu thủ công",{exact:true}).click();
  await expect(page.getByRole("group",{name:"Khóa liên kết đã xác nhận",exact:true})).toBeVisible();
  expect(proposalRequests).toBe(2); // Both HTTP endpoints are intercepted; no provider/job was invoked.
});

for(const size of [{width:390,height:844},{width:768,height:1024},{width:1366,height:768},{width:1920,height:1080}]){
  test(`reconciliation results responsive ${size.width}`,async({page})=>{
    const s=await state();await page.setViewportSize(size);await page.goto("/");
    await selectProject(page, s.project_id);
    if(size.width<=768)await page.getByRole("button",{name:"Mở điều hướng",exact:true}).click();
    await page.getByRole("button",{name:"Báo cáo",exact:true}).click();
    await page.getByLabel("Lần đối soát",{exact:true}).selectOption(s.runs.delivery.run_id);
    await expect(page.getByText("Giá trị lệch tuyệt đối",{exact:true})).toBeVisible();
    await expect(page.getByRole("button",{name:"Xem bằng chứng",exact:true}).first()).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
    await page.screenshot({path:`../runtime/screenshots/reconciliation-${size.width}.png`,fullPage:true});
    if(size.width<=768)await page.getByRole("button",{name:"Mở điều hướng",exact:true}).click();
    await page.getByRole("button",{name:"Đối soát",exact:true}).click();
    await page.getByLabel("Nguồn tham chiếu",{exact:true}).selectOption(s.sources["shipments.csv"].canonical_id);
    await page.getByLabel("Nguồn đối ứng",{exact:true}).selectOption(s.sources["delivery-confirmations.csv"].canonical_id);
    await expect(page.getByLabel("Từ ngày",{exact:true})).toHaveValue("");
    await expect(page.getByRole("button",{name:"AI đề xuất kế hoạch (có dùng quota)",exact:true})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
    await page.screenshot({path:`../runtime/screenshots/reconciliation-setup-${size.width}.png`,fullPage:true});
  });
}
