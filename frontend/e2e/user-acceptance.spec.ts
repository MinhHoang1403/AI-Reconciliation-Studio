import { test } from "./project-selection";
import {expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import {openLegacyPage} from './project-selection';

type Row=Record<string,string>;
type Scenario={name:string;files:{name:string;headers:string[];order:string[];locale:string;rows:number;sha256:string}[];cardinality:string;tolerance:string;raw:{left:Row[];right:Row[]};oracle:{groups:{key:string[];linkage:string;comparison:string;left_rows:number[];right_rows:number[];delta:string|null}[];signed_variance:string;absolute_variance:string;partitions:Record<string,{input:number;invalid:number[];out_of_scope:number[];in_scope:number[]}>}};
const data='../runtime/demo-acceptance/data';
const python=resolve('../.venv/Scripts/python.exe');
execFileSync(python,['../tools/create-uat-fixtures.py']);
const manifest=JSON.parse(await readFile(`${data}/manifest.json`,'utf8')) as {datasets:Scenario[]};

for(const scenario of manifest.datasets){
  test(`[UAT LOCAL manual fallback] ${scenario.name}: Chat uploads to independent oracle and export`,async({page})=>{
    test.setTimeout(300000);
    const start=Date.now(), errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto('/');await expect(page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true})).toBeEnabled();
    const initial=await(await page.request.get('/api/settings')).json();
    await page.locator('#project-select').click();await page.getByRole('button',{name:'Tạo dự án mới',exact:true}).click();
    const create=page.getByRole('dialog',{name:'Tạo dự án',exact:true});
    const name=`UAT ${scenario.name} ${crypto.randomUUID().slice(0,8)}`;
    await create.getByLabel('Tên dự án',{exact:true}).fill(name);
    await create.getByLabel('Phạm vi nghiệp vụ',{exact:true}).fill(`Tổng hợp độc lập ${scenario.name}; giá trị báo cáo gross; kỳ 10/2026 UTC`);
    await create.getByRole('button',{name:'Tạo dự án',exact:true}).click();await expect(create).not.toBeVisible();
    const projectId=(await page.locator('#project-select').getAttribute('data-project-id'))!;
    await page.locator('#project-select').click();await page.getByText('Phân loại dự án hiện tại',{exact:true}).click();
    await page.getByLabel('Nhóm dự án',{exact:true}).selectOption('TEST');await page.getByRole('button',{name:'Xác nhận phân loại',exact:true}).click();
    await expect(page.getByText('Đã lưu phân loại. Dữ liệu và lịch sử vẫn được giữ nguyên.',{exact:true})).toBeVisible();await page.keyboard.press('Escape');
    await page.locator('.assistant-composer input[type=file]').setInputFiles(scenario.files.map(f=>`${data}/${f.name}`));
    const received=page.waitForResponse(r=>r.url().endsWith('/agent/attachments')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Gửi câu hỏi',exact:true}).click();const attachments=await(await received).json();
    await expect(page.getByRole('region',{name:'Công việc của AI Assistant',exact:true}).last()).toContainText('Đã hoàn thành');
    const uploadMs=Date.now()-start;
    for(let i=0;i<2;i++){
      const f=scenario.files[i],dataset=attachments.items[i];
      const raw=await page.request.get(`/api/datasets/${dataset.id}/download`);
      expect(createHash('sha256').update(await raw.body()).digest('hex')).toBe(f.sha256);
      await page.getByRole('button',{name:'Tệp đã tải',exact:true}).click();
      const drawer=page.getByRole('dialog',{name:'Tệp và dữ liệu',exact:true});await drawer.getByRole('button').filter({hasText:f.name}).click();
      await drawer.getByText('Kiểm tra thủ công khi cần',{exact:true}).click();await drawer.getByRole('button',{name:'Mở kiểm tra và ánh xạ thủ công',exact:true}).click();
      await expect(drawer).not.toBeVisible();
      const tables=await(await page.request.get(`/api/datasets/${dataset.id}/tables`)).json();
      const table=tables.items.find((t:{sheet:string})=>t.sheet==='Giao dịch')||tables.items[0];
      await page.getByRole('combobox',{name:'Bảng / sheet',exact:true}).selectOption(table.id);
      await page.getByRole('tab',{name:'AI Smart Setup',exact:true}).click();
      await page.getByLabel('Loại dữ liệu',{exact:true}).fill('reported_transaction');
      await page.getByRole('combobox',{name:'Bảng / sheet',exact:true}).selectOption(table.id);
      await expect(page.getByLabel('Loại dữ liệu',{exact:true})).toHaveValue('reported_transaction');
      const detail=scenario.cardinality==='ONE_TO_MANY'?i===1:scenario.cardinality==='MANY_TO_ONE'?i===0:false;
      await page.getByLabel('Mỗi dòng đại diện cho điều gì?',{exact:true}).fill(detail?'transaction_part':'transaction');
      for(let n=0;n<f.headers.length;n++){
        const header=f.headers[n],field=f.order[n];
        const row=page.locator('.mapping-row').filter({has:page.getByLabel(`Trường đích ${header}`,{exact:true})});
        await row.getByLabel(`Trường đích ${header}`,{exact:true}).fill(field);
        await row.getByLabel(`Kiểu ${header}`,{exact:true}).selectOption(field==='amount'?'decimal':field==='event_date'?'date':'string');
        if(['scope','reference'].includes(field))await row.getByLabel('Thành phần khóa',{exact:true}).check();
        if(field==='event_date'){
          await row.getByLabel('Định dạng ngày',{exact:true}).fill('%Y-%m-%d');await row.getByLabel('Múi giờ đã xác nhận',{exact:true}).fill('UTC');
        }
        if(field==='amount'){
          await row.getByLabel(`Locale ${header}`,{exact:true}).selectOption(f.locale);
          await row.getByLabel(`Chỉ tiêu ${header}`,{exact:true}).fill('reported_transaction_amount');
          await row.getByLabel(`Cơ sở ${header}`,{exact:true}).selectOption('gross');
          await row.getByLabel(`Tiền tệ ${header}`,{exact:true}).fill(scenario.name.startsWith('E ')&&i===1?'USD':'VND');
          await row.getByLabel(`Đơn vị ${header}`,{exact:true}).fill(scenario.name.startsWith('E ')&&i===1?'USD':'VND');
        }
      }
      const warningReview=page.getByLabel('Tôi đã kiểm tra các cảnh báo và vùng dữ liệu nguồn.',{exact:true});
      if(await warningReview.isVisible())await warningReview.check();
      await page.getByRole('button',{name:'Xác nhận ánh xạ',exact:true}).click();await expect(page.getByText('Đã cập nhật ánh xạ.',{exact:true})).toBeVisible();
      await page.getByRole('tab',{name:'Chuẩn hóa',exact:true}).click();await page.getByRole('button',{name:'Chuẩn hóa dữ liệu',exact:true}).click();
      await expect.poll(async()=>{const a=await(await page.request.get(`/api/datasets/${dataset.id}/artifacts`)).json();return a.canonical_datasets.length;}).toBeGreaterThan(0);
      const artifacts=await(await page.request.get(`/api/datasets/${dataset.id}/artifacts`)).json();
      expect(artifacts.canonical_datasets[0].row_count).toBe(f.rows);
      await page.locator('.sidebar').getByRole('button',{name:'AI Assistant',exact:true}).click();
      await expect(page.getByRole('textbox',{name:'Câu hỏi cho AI Assistant',exact:true})).toBeEnabled();
    }
    const normalizeMs=Date.now()-start-uploadMs;
    const catalogue=await(await page.request.get(`/api/projects/${projectId}/canonical-catalogue`)).json();
    await page.locator('.assistant-policy summary').click();await page.getByRole('button',{name:'Thiết lập đối soát thủ công',exact:true}).click();
    await page.getByLabel('Nguồn tham chiếu',{exact:true}).selectOption(catalogue.items.find((c:{name:string})=>c.name===scenario.files[0].name).canonical.id);
    await page.getByLabel('Nguồn đối ứng',{exact:true}).selectOption(catalogue.items.find((c:{name:string})=>c.name===scenario.files[1].name).canonical.id);
    await page.getByRole('combobox',{name:'Quan hệ',exact:true}).selectOption(scenario.cardinality);
    await page.getByLabel('Đơn vị đối soát (mỗi nhóm đại diện cho)',{exact:true}).fill('transaction');
    await page.getByLabel('Từ ngày',{exact:true}).fill('2026-10-01');await page.getByLabel('Đến ngày (không gồm)',{exact:true}).fill('2026-11-01');await page.getByLabel('Múi giờ',{exact:true}).fill('UTC');
    await page.getByLabel('Sai số tuyệt đối',{exact:true}).fill(scenario.tolerance);
    for(const side of ['nguồn trái','nguồn phải']){
      const scope=page.getByRole('group',{name:`Phạm vi ${side}`,exact:true});
      await scope.getByRole('combobox',{name:'Trường ngày',exact:true}).selectOption('event_date');
      await scope.getByLabel('Đầu kỳ nguồn',{exact:true}).fill('2026-10-01');await scope.getByLabel('Cuối kỳ nguồn (không gồm)',{exact:true}).fill('2026-11-01');
      await scope.getByRole('combobox',{name:'Độ đầy đủ',exact:true}).selectOption('CONFIRMED');
    }
    await page.getByLabel('Cho phép kết quả một phần; nguồn thiếu kỳ sẽ ở trạng thái đang chờ',{exact:false}).check();
    await page.getByLabel('Tôi xác nhận kỳ, múi giờ và phạm vi nguồn',{exact:true}).check();
    await page.getByRole('button',{name:'Kiểm tra điều kiện',exact:true}).click();
    await mkdir('../runtime/demo-acceptance/results',{recursive:true});
    if(scenario.name.startsWith('E ')){
      await expect(page.locator('[role=alert]').last()).toContainText(/tiền tệ|currency|đơn vị/i);
      const runs=await(await page.request.get(`/api/runs?project_id=${projectId}`)).json();expect(runs.total).toBe(0);
      await writeFile(`../runtime/demo-acceptance/results/${scenario.name}.json`,JSON.stringify({projectId,name,status:'PASS_SAFE_BLOCK',reason:'mixed currencies without FX'}));return;
    }
    await expect(page.getByText('Đã kiểm tra schema, scope, grain, metric, thời gian và khóa. Trùng khóa được giữ để review.',{exact:true})).toBeVisible();
    await page.getByRole('button',{name:'Lưu đề xuất thủ công',exact:true}).click();await page.getByRole('button',{name:'Xác nhận quy tắc và dấu số tiền',exact:true}).click();
    const accepted=page.waitForResponse(r=>r.url().endsWith('/reconciliation-runs')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Chạy đối soát đã duyệt',exact:true}).click();const runId=(await(await accepted).json()).run_id;
    await expect.poll(async()=>(await(await page.request.get(`/api/runs/${runId}`)).json()).status).toMatch(/^(VERIFIED|PARTIAL_VERIFIED)$/);
    const run=await(await page.request.get(`/api/runs/${runId}`)).json(),snapshot=await(await page.request.get(`/api/runs/${runId}/metrics`)).json();
    const matchMs=Date.now()-start-uploadMs-normalizeMs;
    expect(run.checks.every((c:{passed:boolean})=>c.passed)).toBe(true);
    const groups=[];
    for(let offset=0;;offset+=100){const p=await(await page.request.get(`/api/runs/${runId}/matches?offset=${offset}&limit=100`)).json();groups.push(...p.items);if(groups.length>=p.total)break;}
    await writeFile(`../runtime/demo-acceptance/results/${scenario.name}-observed.json`,JSON.stringify({projectId,name,runId,run,snapshot,groups},null,2));
    for(const side of ['left','right'] as const){
      const rowsFor=(state?:string)=>groups.filter(g=>!state||g.linkage_state===state).flatMap(g=>g.members.filter((m:{side:string})=>m.side===side).flatMap((m:{evidence:{row:number}[]})=>m.evidence.map(e=>e.row))).sort((a:number,b:number)=>a-b);
      const part=scenario.oracle.partitions[side];
      expect(rowsFor()).toEqual(Array.from({length:part.input},(_,i)=>i+2));
      expect(rowsFor('INVALID')).toEqual(part.invalid);
      expect(rowsFor('OUT_OF_SCOPE')).toEqual(part.out_of_scope);
    }
    for(const expected of scenario.oracle.groups){
      const actual=groups.filter(g=>JSON.stringify(g.key)===JSON.stringify(expected.key));
      expect(actual.length,JSON.stringify(expected.key)).toBeGreaterThan(0);
      expect(actual.map(g=>g.linkage_state),JSON.stringify({expected,actual})).toEqual(actual.map(()=>expected.linkage));
      if(expected.linkage==='LINKED'){
        expect(actual).toHaveLength(1);expect(actual[0].comparison_state).toBe(expected.comparison);
        for(const side of ['left','right'] as const)expect(actual[0].members.filter((m:{side:string})=>m.side===side)).toHaveLength(expected[`${side}_rows`].length);
      }
    }
    // Decimal assertions are independent of the application, with no binary float conversion.
    execFileSync(python,['-c',
      'import json,sys;from decimal import Decimal as D;x=json.load(sys.stdin);s=x["snapshot"]["monetary"][0];o=x["oracle"];assert D(s["signed_variance"])==D(o["signed_variance"]);assert D(s["absolute_variance"])==D(o["absolute_variance"]);g={tuple(v["key"]):v for v in x["groups"] if v["linkage_state"]=="LINKED"};assert all(D(g[tuple(e["key"])]["comparisons"][0][field])==D(e[field]) for e in o["groups"] if e["linkage"]=="LINKED" and e["delta"] is not None for field in ("left_amount","right_amount","delta"))'
    ],{input:JSON.stringify({snapshot,oracle:scenario.oracle,groups}),encoding:'utf8'});
    await openLegacyPage(page,'reports');
    for(const format of ['CSV','XLSX']){
      const response=page.waitForResponse(r=>/^\/api\/exports\/[^/]+$/.test(new URL(r.url()).pathname)&&r.request().method()==='GET',{timeout:90000});
      await page.getByRole('button',{name:`Xuất ${format}`,exact:true}).click();const info=await(await response).json();const link=page.getByRole('link',{name:'Tải báo cáo',exact:true});await expect(link).toHaveAttribute('href',info.download_url);
      const download=page.waitForEvent('download');await link.click();await(await download).saveAs(`../runtime/demo-acceptance/results/${scenario.name}.${format.toLowerCase()}`);
    }
    const exported=JSON.parse(execFileSync(python,['-c',
      "import csv,json,sys;from openpyxl import load_workbook;r=list(csv.reader(open(sys.argv[1],encoding='utf-8-sig')));a=json.loads(next(x[2] for x in r if x[:2]==['Summary','Snapshot JSON']));w=load_workbook(sys.argv[2],data_only=False);b=json.loads(next(r[1].value for r in w['Summary'] if r[0].value=='Snapshot JSON'));assert a==b;assert all(c.data_type!='f' for s in w for r in s for c in r);print(json.dumps(a))",
      `../runtime/demo-acceptance/results/${scenario.name}.csv`,`../runtime/demo-acceptance/results/${scenario.name}.xlsx`
    ],{encoding:'utf8'}));expect(exported).toEqual(snapshot);
    await page.reload();await expect(page.getByRole('heading',{name:'Báo cáo đối soát',exact:true})).toBeVisible();
    expect(await(await page.request.get(`/api/runs/${runId}/metrics`)).json()).toEqual(snapshot);
    const final=await(await page.request.get('/api/settings')).json();
    expect(errors).toEqual([]);
    await writeFile(`../runtime/demo-acceptance/results/${scenario.name}.json`,JSON.stringify({projectId,name,runId,status:'PASS_LOCAL',snapshot,timings:{uploadMs,normalizeMs,matchMs,totalMs:Date.now()-start},groups:groups.length,globalLedgerObserved:{before:initial.gemini_requests_used,after:final.gemini_requests_used,note:'Concurrent owner requests are not attributed to UAT; project traces are authoritative.'}},null,2));
  });
}

test('[UAT LOCAL] Oversized and corrupt uploads are rejected before processing',async({page})=>{
  await page.goto('/');await expect(page.getByLabel('Câu hỏi cho AI Assistant',{exact:true})).toBeEnabled();
  const writes:string[]=[];page.on('request',r=>{if(r.method()==='POST')writes.push(new URL(r.url()).pathname);});
  await page.locator('.assistant-composer input[type=file]').setInputFiles(`${data}/Tệp quá giới hạn.csv`);
  await expect(page.getByRole('alert')).toContainText(/20|giới hạn|dung lượng/i);
  expect(writes).toEqual([]);
  await page.locator('.assistant-composer input[type=file]').setInputFiles(`${data}/Tệp hỏng.xlsx`);
  const rejected=page.waitForResponse(r=>r.url().endsWith('/agent/attachments')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Gửi câu hỏi',exact:true}).click();expect((await rejected).status()).toBe(422);
  await expect(page.getByRole('alert')).toBeVisible();
  expect(writes).toEqual(['/api/agent/attachments']);
});
