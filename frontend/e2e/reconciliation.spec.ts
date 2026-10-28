import {test,expect} from "@playwright/test";
import {readFile,mkdir} from "node:fs/promises";

type State={project_id:string;sources:Record<string,{canonical_id:string}>;runs:Record<string,{run_id:string;contract_id:string;plan:unknown;snapshot:{monetary:{absolute_variance:string}[]}}>};
async function state(){return JSON.parse(await readFile("../runtime/reconciliation-acceptance.json","utf8")) as State;}
test("T35: manual rule builder, approval, verified dashboard, exception review, exports and reopen",async({page})=>{
  test.setTimeout(120000);
  const s=await state();
  await page.goto("/");
  await expect(page.getByText("Hệ thống đã kết nối")).toBeAttached();
  await page.locator("#project-select").selectOption(s.project_id);
  await page.getByRole("button",{name:"Đối soát",exact:true}).click();
  await page.getByLabel("Nguồn tham chiếu",{exact:true}).selectOption(s.sources["shipments.csv"].canonical_id);
  await page.getByLabel("Nguồn đối ứng",{exact:true}).selectOption(s.sources["delivery-confirmations.csv"].canonical_id);
  for(const side of ["nguồn trái","nguồn phải"]){
    await page.getByRole("group",{name:`Coverage ${side}`,exact:true}).getByRole("combobox",{name:"Độ đầy đủ",exact:true}).selectOption("CONFIRMED");
  }
  await page.getByRole("button",{name:"Kiểm tra điều kiện",exact:true}).click();
  await expect(page.getByText("Đã kiểm tra schema, scope, grain, metric, thời gian và khóa. Trùng khóa được giữ để review.")).toBeVisible();
  await page.getByRole("button",{name:"Lưu đề xuất thủ công",exact:true}).click();
  await page.getByRole("button",{name:"Xác nhận quy tắc và dấu số tiền",exact:true}).click();
  await page.getByRole("button",{name:"Chạy đối soát đã duyệt",exact:true}).click();
  await expect(page.getByText("Giá trị lệch tuyệt đối",{exact:true})).toBeVisible();
  const rid=await page.getByLabel("Lần đối soát",{exact:true}).inputValue();
  const before=await (await page.request.get(`/api/runs/${rid}/metrics`)).json();
  expect(before.monetary[0].absolute_variance).toBe("2.75");
  await page.getByRole("button",{name:"Ngoại lệ",exact:true}).click();
  await page.getByLabel("Lần đối soát",{exact:true}).selectOption(rid);
  const row=page.getByRole("row").filter({has:page.getByRole("cell",{name:"Lệch tiền",exact:true})});
  await row.getByRole("button",{name:"Xem ngoại lệ",exact:true}).click();
  const dialog=page.getByRole("dialog");
  await expect(dialog.getByText("delivery_charge: 12.75 − 10.00 = 2.75 VND",{exact:true})).toBeVisible();
  await dialog.getByRole("combobox",{name:"Trạng thái xử lý",exact:true}).selectOption("RESOLVED");
  await dialog.getByLabel("Lý do / ghi chú",{exact:true}).fill("Đã xem bằng chứng tổng hợp; không sửa số tiền.");
  await dialog.getByRole("button",{name:"Lưu xem xét",exact:true}).click();
  await expect(dialog).not.toBeVisible();
  expect(await (await page.request.get(`/api/runs/${rid}/metrics`)).json()).toEqual(before);
  await page.getByRole("button",{name:"Xuất XLSX",exact:true}).click();
  await expect(page.getByRole("link",{name:"Tải báo cáo",exact:true})).toBeVisible();
  const download=await page.request.get(await page.getByRole("link",{name:"Tải báo cáo",exact:true}).getAttribute("href")||"");
  expect(download.status()).toBe(200);
  expect(download.headers()["content-type"]).toContain("spreadsheetml");
  await page.reload();
  await page.getByRole("button",{name:"Báo cáo",exact:true}).click();
  await expect(page.getByLabel("Lần đối soát",{exact:true})).toHaveValue(rid);
  await expect(page.getByRole("img",{name:"Phân bố trạng thái đối soát"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Xem bằng chứng",exact:true}).first()).toBeVisible();
  await mkdir("../runtime/screenshots",{recursive:true});
  await page.screenshot({path:"../runtime/screenshots/reconciliation-dashboard.png",fullPage:true});
});

for(const size of [{width:390,height:844},{width:768,height:1024},{width:1366,height:768},{width:1920,height:1080}]){
  test(`reconciliation results responsive ${size.width}`,async({page})=>{
    const s=await state();await page.setViewportSize(size);await page.goto("/");
    await page.locator("#project-select").selectOption(s.project_id);
    if(size.width<=768)await page.getByRole("button",{name:"Mở điều hướng",exact:true}).click();
    await page.getByRole("button",{name:"Báo cáo",exact:true}).click();
    await page.getByLabel("Lần đối soát",{exact:true}).selectOption(s.runs.delivery.run_id);
    await expect(page.getByText("Giá trị lệch tuyệt đối",{exact:true})).toBeVisible();
    await expect(page.getByRole("button",{name:"Xem bằng chứng",exact:true}).first()).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
    await page.screenshot({path:`../runtime/screenshots/reconciliation-${size.width}.png`,fullPage:true});
  });
}
