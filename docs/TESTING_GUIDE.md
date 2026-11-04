# Hướng dẫn kiểm thử

Chạy từ repository root. Các lệnh bên dưới không tạo Compose project hoặc database server thứ hai. Chỉ dùng fixtures tổng hợp; không sửa hoặc xóa dữ liệu dự án khác.

## Giao diện tối giản và đồng bộ runtime — 04/11/2026

Trước sửa, đối chiếu build từ Git với asset trong Nginx, HTTP và Chromium profile mới/disabled cache; kiểm service worker registrations, computed styles khi pointer và Tab. Baseline composer có border 1px + outline 2px cả khi click vì textarea vẫn `:focus-visible`; đây là lỗi CSS khi hashes đã khớp. Sau sửa phải xác minh lại trên asset production, không chỉ fixture dist.

Các ca `Compact composer` tại năm widths giữ toàn bộ kiểm tra upload/draft/Settings và thêm: empty height ≤64px; pointer không border/outline/inset focus; Tab có underline nhìn thấy, textarea không outline riêng; quay lại pointer bỏ underline; placeholder contrast ≥4,5:1 trên nền computed. Không xóa focus bàn phím hoặc nới oracle để PASS. Giữ 117 browser cases; các screenshot mới trong approval, data drawer và verified report là evidence, không cases mới. Các states khác dùng layout matrix 23×5, kèm clarification/loading/IME/unknown-delivery/reload/manual fallback. Baseline/failure/after images và hash receipts nằm tại `runtime/minimal-interface/`, ngoài Git.

Full regression đã tái hiện focus sau gửi bị mất trên390px: `requestAnimationFrame` có thể chạy trước React commit bật lại textarea. Phục hồi focus bằng `useLayoutEffect` sau commit, giữ guard component còn mounted và sequence request hiện hành; không đổi HTTP/approval contracts. Cơ sở: [React useLayoutEffect](https://react.dev/reference/react/useLayoutEffect), đã kiểm04/11/2026. Giữ assertion focus cũ, kiểm lại năm widths nhiều lượt và full suite; không tăng timeout/retry để che lỗi. Pointer/Tab phân biệt tại App Shell vì Chromium vẫn coi textarea click chuột là focus-visible; chỉ composer dùng chỉ báo inset, controls khác giữ focus outline.

Sau quality gates, build/recreate frontend qua Compose hiện có rồi kiểm cache sạch/CSS computed/hash, regression nghiệp vụ, persistence và ledger. Cleanup chỉ sau deploy gate; inventory phải gồm OCI source/revision, refs từ mọi container kể cả stopped, cùng image IDs/volumes ngoài Studio để so trước/sau. Giữ rollback `dac8dd1`; không global prune hoặc dọn shared build cache. Sau cleanup chạy lại full browser/backend gate phù hợp và checksums/health, báo đúng dung lượng Docker đo được thay vì cộng virtual sizes. Không gọi AI mới hoặc mở thêm allowance.

Kết quả runtime04/11: source18706a7, chỉ frontend recreate;8/8checks sau deployPASS trước cleanup. Sau xóa8image theoID:302/302Backend/PostgreSQLPASS (116,39giây),117/117browserPASS (14,8phút),0FAIL/SKIP/retry. Bảy HTML/assets và42Backend files khớp,24bảng gốc/2.709file checksums không đổi,4serviceshealthy/API200/queue0/ledger203→203. Ảnh sau tại `runtime/minimal-interface/after/`, gồm5widths/layout/settings/native; bản trước ở`before/`. Chi tiết identity/cleanup/failures/giới hạn tại [báo cáo mục Z](IMPLEMENTATION_STATUS.md#z-giao-diện-tối-giản-sourceruntime-và-docker-cleanup--04112026), không cộng các lượt chạy lại thành test cases mới.

## Hội thoại, clarification và metric — 03/11/2026

Gate source hiện hành: **302Backend/PostgreSQL và117Playwright PASS**, gồm231offline+71PG, toàn bộ browser regression/UAT/financial oracle/export/reload. Browser chạy một worker, retries0, dist cố định tại cùng origin/API; không build hoặc chạy Playwright khác đồng thời. Bằng chứng postdeploy và source/runtime identity ghi tại [IMPLEMENTATION_STATUS mục Y](IMPLEMENTATION_STATUS.md#y-hội-thoại-clarification-và-natural-language-reliability--03112026); các số ở mục lịch sử bên dưới không thay kết quả hiện hành.

Regression PostgreSQL tái hiện money fields thiếu metric (`QUERY_FIELD_INVALID` trước sửa), kiểm unique metric/Decimal2,75VND, nhiều/không metric, reply clarification tiếp tục đúng workflow, ambiguous giữ chờ, dữ kiện coverage do model bịa bị chặn, mapping mới vẫn cần approval. Follow-up theo vị trí dùng trang/sort đã lưu, run/case được kiểm lại; bảng gốc không bị sửa và conversation khác không kế thừa lựa chọn. Public fields additive/defaults, không migration/dependency mới.

`assistant-experience.spec.ts` có năm viewport kiểm clarification không checkbox/enum/approval, chọn tùy chọn, trả lời qua composer/reload, một panel cho workflow sau reply, đồng thời Enter/click chỉ gửi một request và spinner không thay kích thước. Bộ layout cũ giữ23trạng thái; bổ sung screenshots hỏi bổ sung/loading. Keyboard viewport mô phỏng không chứng minh thiết bị di động vật lý hoặc screen-reader certification. Focus được chuyển sang bề mặt composer, theo [W3C Focus Visible](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html); controlled textarea và accessible label đối chiếu [React textarea](https://react.dev/reference/react-dom/components/textarea), đã mở03/11/2026.

Regression đổi1440→390→1440với draft không thay đổi kiểm textarea tăng/giảm chiều cao, không cuộn nội bộ trước180px, giữ text/nút gửi và không pageerror. Đã FAIL trên source1ac2139trước sửa; width observer không phản ứng với height-only notifications để tránh vòng lặp đo kích thước.

Guard tests phân biệt yêu cầu thật với “không/đừng bỏ qua tiền tệ”, “đừng lấy nguồn tên gần giống”, kể cả Unicode decomposed. Không bỏ dấu trước khi phân biệt “đừng”/“dùng”; câu phủ định rồi có yêu cầu vượt gate thật vẫn bị chặn. Đây là guard hẹp, không thay thế xác minh source/currency/FX/approval ở Backend.

Trước thay release, có thể chạy UI dist candidate với API hiện hành, cùng origin/Compose, không dựng app/server thứ hai:

```powershell
npm --prefix frontend run build
$env:STUDIO_FRONTEND_DIST='1'
$env:STUDIO_EXPECT_AI_PROVIDER='MANUAL'
npm --prefix frontend run test:e2e
Remove-Item Env:STUDIO_FRONTEND_DIST
```

Fixture trong `e2e/project-selection.ts` chỉ đọc dist đã build và intercept HTML/assets tại browser; API thật/mocks vẫn theo từng test, không có cloud request để test CSS. Sau deploy chạy lại trên assets/runtime thật, không dùng cờ candidate.

Runtime `dac8dd1` đã chốt thêm38browser smoke và1UAT1000PASS trên assets thật; nguồn/API/persistence/read-back/backup checks ghi tại mụcY.Ibáo cáo. Đây là replay của các trường hợp trong bộ117, không cộng thành156cases. Backup sau nghiệm thu restore24tables/2.709filesPASS và host checksumsPASS; dữ liệu public không overwrite. Một full run bị gián đoạn dài có1timeout được giữFAIL; ca đóPASS riêng và trong full117liên tục, không tăng timeout/retries để che.

`tests/fixtures/assistant-conversation-cases.json` bổ sung24câu mới/24chủ đề, giữ nguyên80gold và24variants cũ. Benchmark dùng cùng rubric/ledger production, mở rộng kiểm UNPAID và định dạng export, không đổi oracle cũ. Bộ câu mới có thể chạy bằng `benchmark-agent.py --suite variants --gold <fixture-mới> ...` do cùng shape24/8negative; đây là tập conversation mới, không đổi tên thành24variants lịch sử trong báo cáo. Routing LIVE không là workflow completion; cached revalidation không là inference mới. Kiểm multiple metrics/absence/mixed currency còn có deterministic/PG guards riêng.

## Nghiệm thu demo và khôi phục môi trường — 02/11/2026

Sau khi mất interpreter trong AppData, khôi phục đúng Python3.12.14 và rebind `.venv` hiện có bằng `uv venv .venv --allow-existing --python <interpreter-đã-kiểm-tra>`, rồi `uv sync --locked`/`uv pip check`. Không dùng `--clear`, không xóa lockfiles/venv data hoặc tạo Compose thứ hai. Máy hiện tại còn Python3.11.9 cho alias cũ; không thay project `requires-python`3.12. Node/npm và `npm --prefix frontend ls --depth=0`, Chromium Playwright được kiểm riêng. AppData có thể chứa môi trường của phần mềm khác không có manifest; không tự đoán package của chúng.

`tools/create-uat-fixtures.py` sinh11scenarios/24files/2131transaction rows cùng manifest/oracle Decimal vào runtime/demo-acceptance/data. Oracle không import Matcher/Verifier/LLM. `frontend/e2e/user-acceptance.spec.ts` upload qua Chat, phân loại TEST, review mapping/contract qua UI, kiểm rawSHA/từnggroup/membership/partition/Decimal, CSV/XLSX snapshot và reload; nhãn LOCAL manual fallback, không gọi là NLlive. Hai fixtures hỏng/quá20MiB kiểm reject; formula warnings phải được review. `history-readiness.spec.ts` phân biệt MOCK UI ở năm widths và context sau failedturn; `agent-plan-review.spec.ts` bảo vệ optionalnull/false/filter defaults trước submit.

Người dùng đã yêu cầu để công cụ runtime bật. Regression không được dựa vào deployment cloudOFF: các test default config phải cô lập env, unsafe legacy request phải reserve0call khi cloudON, kiểm UI dùng MOCK chỉ tại test. Quota ledger không reset. Lượt người dùng/Codex được phân loại bằng project/job/trace, không suy từ globaldelta trong lúc người dùng có thể tự thử.

BenchmarkNL chỉ đo router/typed dispatch, không giả lập workflow thành công. Tùy chọn `--evaluate-completed-cases` chỉ chấm typed candidates có receiptHTTP200/STOP, cùng productionvalidator, giữ failure trong mẫu số và giữ job/batch gốcBLOCKED; unknown delivery không được resend. Full gold80/variants24 giữ nguyên rubric; CACHED revalidation và requestLIVE được báo riêng. Các kết quả nguồn/slot/NLP không là tỷ lệ đúng mọi dữ liệu. Kết quả mới nhất và knownlimits ở [mục V](IMPLEMENTATION_STATUS.md#v-nghiệm-thu-demo-và-khôi-phục-môi-trường--02112026); các hướng dẫn quota/OFF theo mốc bên dưới là lịch sử.

## Kiểm tra Assistant và Settings — 02/11/2026

Phạm vi mới: composer gọn/tự giãn, icon gửi có accessible name, không outline xanh quanh composer khi click, focus bàn phím, Settings theo người dùng và giới hạn chat từ API. `assistant-experience.spec.ts` bổ sung năm widths 390/768/1366/1440/1920, các trạng thái quyền/cấu hình/hạn mức AI mô phỏng, IME, upload mất phản hồi rồi refresh và biểu đồ tên nhóm dài. Các test mới giữ nguyên số tiền/oracle; không bật provider để kiểm giao diện.

Regression upload dùng POST thật tới Backend nhưng browser chủ động bỏ phản hồi đầu: đính kèm lại cùng bytes sau refresh phải có cùng key/project/dataset, không tạo bootstrap thứ hai. Regression biểu đồ dùng DTO MOCK sáu tên nhóm dài, kiểm đủ nhãn SVG, exact values, accessible description và cuộn bàn phím. Backend thêm một PG test giới hạn chat thay theo cấu hình và được server thực thi. Xem kết quả nghiệm thu mới nhất tại IMPLEMENTATION_STATUS; các số liệu theo mốc ở phần dưới là lịch sử.

Nghiệm thu bổ sung **30/10/2026**, [mục R](IMPLEMENTATION_STATUS.md): trước cleanup190 backend/59 E2E PASS; sau sửa công cụ và cleanup **191 backend PASS (153 offline + 38 PostgreSQL), 59 E2E MANUAL PASS, 0 FAIL/SKIP/flaky**. Backend55,45giây, E2E192,85giây. Không cộng các replays. Regression mới kiểm payload CLI qua đúng `AIPlanInput.request` và bảo toàn source IDs/period/timezone/coverage; PostgreSQL harness copy helper vào `/tmp` hiện có. Lỗi cũ được tái hiện bằng missing request/extra plan, không gửi cloud.

Hai live attempts được cấp phép riêng: Assistant `assistant-grounded-1` PASS LIVE; Planner `reconciliation-planning-2` FAIL LIVE vì JSON không đạt Pydantic. Mock/schema/semantic tests PASS không phủ định FAIL LIVE. Giữ ngân sách9/10, còn1; không bật Assistant cloud hoặc dùng `--planner-live` để thử lại. Công cụ đọc cached proposal ghi PASS CACHED, không nhận là live mới. Merge/main release BLOCKED; không chạy regression trên merge result hoặc image main mới khi chưa có chúng.

Lượt E2E đầu bị chặn bởi `LOCAL_DEMO_NOT_VERIFIED` sau gián đoạn/restart; lượt này không PASS. Dùng công cụ verify-local hiện có rồi chạy lại59/59, không bỏ auth hoặc nới timeout. Browser7trang ×5viewport và12state captures MOCK GET được phân biệt với authorization thật trong PG/E2E. Worker SIGKILL75k, ba phép persistence/fail-closed, backup/restore23bảng/488files và đọc lại live conversation đều PASS LOCAL, không gọi cloud mới.

Đợt **Product UX & Reliability ngày 30/10/2026**, source `446d0312048cb0fe70052944e6972d28cf7bf773`, có bằng chứng mới ở [mục Q](IMPLEMENTATION_STATUS.md#q-product-ux-và-reliability--nhiệm-vụ-ngày-30102026): **190 backend PASS (152 offline + 38 PostgreSQL), 59 E2E PASS (9 foundation + 25 interface + 7 reconciliation + 17 Assistant + 1 hành trình dự án mới), 0 FAIL/SKIP**. Backend runtime 63,08 giây; E2E MANUAL 200,11 giây. Các con số bên dưới thuộc mốc lịch sử.

Regression mới kiểm Assistant là trang trong AppShell, bản nháp giữ theo actor/scope khi Back/Forward/reload/đổi project, run nằm ngoài trang lịch sử, mất message response rồi reload không nhân job, navigation hủy delayed Back restore, quay về đúng case và workflow hai cặp có partial failure/retry cùng keys. Hành trình riêng tạo project tổng hợp qua UI, owner phân loại TEST, upload CSV/XLSX, profiling/mapping/normalization, duyệt rule, verified run, evidence/citation, Assistant, CSV/XLSX tải qua trình duyệt rồi đọc lại và đối chiếu oracle literal 12.75 − 10.00 = 2.75 VND, tỷ lệ 1/3 = 33.33%. Không thay oracle, không gọi cloud và không xóa fixtures sau kiểm tra.

Backend bổ sung 12 câu hỏi về facts/thiếu bằng chứng và cap nhóm 100/101 thành viên trên Parquet thật; bảy tools đều từ chối workspace lạ. Case page trả `groups` summary bằng một truy vấn ID tham số hóa, chỉ đúng case của trang; `case_id` được ràng buộc cùng run/workspace. Số liệu tiền được đọc từ kết quả đã xác minh, không tính lại ở frontend. T01–T40 nằm trong các suite được replay, không cộng catalogue hoặc replay vào số test mới. Provider transports trong regression là MOCK; không dùng các helper có `--planner-live`, document live hoặc provider live trong nhiệm vụ này.

Đợt Final UX hardening ngày **30/10/2026** có [inventory và bằng chứng ở mục N](IMPLEMENTATION_STATUS.md#n-final-ux-hardening--phân-loại-project-và-dữ-liệu-gần-đây): **149 backend PASS (120 offline+29PG), 41 E2E MANUAL PASS (9foundation+25interface+7reconciliation), 0 FAIL/SKIP**. Ruff/mypy28/TypeScript/ESLint/build PASS. Full backend38,26s; full browser~1,4phút. Sau khi làm chặt assertion chờ nội dung Dashboard trước screenshot, replay foundation9PASS/31,1s trên image8789940; catalogue vẫn41. Regression mới: phân loại owner/viewer/editor/scope/conflict/concurrent writes, UNKNOWN visible và filter-before-pagination; recent5/30/80nguồn độc lập page2, refresh nguồn mới, delayed/error/retry/project switching; giữ draft khi đổi nhóm và khi rời selector đang lưu. Không cộng replay vào số cases.

Foundation E2E mặc địnhMANUAL tìm lại một project TEST theo exactname/scope, tạo TEST explicit qua API nếu chưa có; bộ chọn thật bật toggle để chọn project này. Tạo project WORK qua UI có browsercontract regression riêng và API PG authorization/default test. Các helper document/reconciliation/recovery cũng khai báo TEST khi tạo mới; không gọi các helper live trong đợt regression này. Chỉ đo retention/delta, không xóa project/artifacts lịch sử hoặc thêm cleanup job.

Quality hardening trước đó ngày 29–30/10/2026 trên `codex/interface-quality`: xem [mục M](IMPLEMENTATION_STATUS.md#m-hoàn-thiện-frontend-và-ux-giai-đoạn-12). Kết quả lịch sử: **145 backend PASS (120offline+25PG), 34 E2E MANUAL PASS (9foundation+18interface+7reconciliation), 0 FAIL/SKIP**; Ruff/mypy31/TypeScript/ESLint/build PASS. Full backend44,02s; full browser ~1,2phút trên image sourceac44915. Baseline143/15 tăng2PG+19browser cases; không cộng replays thành cases mới. Những số liệu bên dưới thuộc các mốc lịch sử.

Bằng chứng Final Acceptance lịch sử ngày **29/10/2026** ở [mục L của báo cáo](IMPLEMENTATION_STATUS.md#l-final-acceptance-hợp-nhất-và-vận-hành--29102026): 120 offline/143 tổng backend và 15 E2E MANUAL PASS, không cloud. T35 hiện xuất cả CSV/XLSX qua UI, đợi đúng export URL của từng format, kiểm SHA256/timestamp và lưu downloads/snapshot dưới runtime để đọc lại. Không đổi oracle hoặc timeout. Những số 91/9 ở phần nền tảng bên dưới là lịch sử Giai đoạn 1.

UI regressions mới dùng control hiển thị thật, không hidden select. Search/restore/race/counts/polling và next action có cả PostgreSQL scoped tests lẫn browser mocked GET fixtures; Planner UI là MOCK. Năm responsive cases đo bounds dialog/focus outline và4mẫu contrast từ computed colors, kiểm keyboard/Enter/Escape/focus-return/mobile drawer. Không suy rộng thành toàn bộ WCAG/screen-reader PASS. Tất cả cases kiểm0uncaught pageerrors; luồng foundation/T35 thành công còn kiểm0console errors. Delayed evidence regression giữ đúng run/project. Các lỗi503/auth mock được kiểm bằng thông báo thật.

Đối chiếu runtime/source khi release: từ tracked application source sạch, đặt build-only `$env:BUILDX_GIT_LABELS='full'` rồi `docker compose build backend frontend`, kiểm OCI revision/source của images trước `up`, `tools/verify-local.ps1` và so source/served assets SHA256. Label base image Nginx không phải revision của ứng dụng; cached Created timestamp không chứng minh commit. Không cần thêm biến runtime, service hoặc thay Dockerfile.

Final Acceptance theo phạm vi mới ngày 28/10/2026 đã chạy lại: **91 backend PASS, 0 FAIL/SKIP** (79 offline + 12 PostgreSQL), Ruff/mypy và frontend TypeScript/lint/build PASS, **9 E2E MANUAL PASS, 0 FAIL/SKIP trong 19,6 giây**. T01–T16 và security nằm trong các suite này, không cộng thêm vào tổng. Baseline 87 backend/8 E2E tăng do bốn backend regression và một case document cached. Gemini live 9 E2E PASS là bằng chứng của lần chạy trước chỉ dẫn thu hẹp; không gọi lại cloud ở lượt này, quota vẫn 6/10. LlamaParse đọc lại hai kết quả live đã lưu, không tạo job mới. Chỉ nghiệm thu Giai đoạn 1, chờ prompt riêng trước Giai đoạn 2.

## Backend offline

```powershell
uv sync --frozen
uv run pytest -q -m 'not integration'
uv run ruff check backend tests tools
uv run mypy backend/studio
```

Ngày 28/10/2026: **79 tests offline PASS**, 12 integration deselected; Ruff/mypy PASS. Có một cảnh báo deprecation từ Starlette về TestClient/httpx; không phải lỗi ứng dụng. Chưa chuyển test client transport trong đợt này vì contract tests hiện chạy đúng với lock đã chọn.

| Catalogue | Bằng chứng thực thi |
| --- | --- |
| T01 | size, extension/MIME/signature, archive/XML entity và tên path không hợp lệ bị từ chối |
| T02 | hash/raw bytes không đổi; integration kiểm tra upload scoped dedup và project khác không reuse dataset |
| T03 | route document/cloud OFF và mock transport khẳng định 0 HTTP cloud calls |
| T04 | XLSX nhiều sheet, header lệch, sheet ẩn và physical source rows |
| T05 | text/numeric zero-format `000123`; document adapter luôn UNVERIFIED_EXTRACTION. OCR live chưa kiểm tra |
| T06 | giữ formula/cache metadata và warning, không tính lại công thức hoặc sửa cache |
| T07 | null/empty/distinct/key candidates đúng fixture độc lập; số `0.00` không bị nhận nhầm thành ID |
| T08 | alias tên Việt/Anh → shortlist field IDs thật, chưa tự approve |
| T09 | Qwen malformed JSON, HTTP/timeout, bounded retries, classification/grain/mapping/transformation tasks qua mock |
| T10 | Total mơ hồ, UNKNOWN/AMBIGUOUS giữ review; currency/metric thiếu hoặc UNKNOWN không được approve |
| T11 | type/transform/rule chưa duyệt bị chặn |
| T12 | PostgreSQL viewer approve → 403, có audit denial |
| T13 | approval mới tạo revision, canonical cũ stale, raw/parsed refs/hash giữ nguyên |
| T14 | discriminated DSL từ chối exec/eval/SQL và extra params; không chạy mã AI |
| T15 | `1.234,50` → Decimal `1234.50` dưới locale đã duyệt; zero/negative/exponent/precision và property tests |
| T16 | raw invalid/null/zero tách riêng, error artifact, không mất dòng, Parquet roundtrip và lineage |
| T36/T37 | cloud OFF, hallucinated evidence, AI không được tự APPROVED |

Operator tests bao phủ trim được duyệt, enum, coalesce phân biệt null/empty, arithmetic có rule/semantics, date timezone/DST, grouping signed Decimal và đầy đủ lineage. Đây là dữ liệu tổng hợp có oracle, không phải đánh giá precision/recall mapping trên dữ liệu đại diện.

## PostgreSQL và worker

```powershell
./tools/test-postgres.ps1
./tools/test-postgres.ps1 -All
```

Script copy tests vào `/tmp` của backend hiện có, cài test tooling tạm tại `/tmp/studio-checks` và chạy pytest. Mỗi test tạo schema `test_<UUID>`, chạy migration snapshot, dùng riêng metadata và storage temp, rồi drop đúng schema này. Bộ đầy đủ hiện đạt **91 PASS (79 offline + 12 PostgreSQL integration), 0 FAIL/SKIP**. Worker production không thể claim jobs trong schema test. Kiểm tra Gemini concurrency/quota và document reservation/artifact/reuse sau thu hồi quyền; transport đều mock. Upload explicit manual không enqueue AI hoặc tiêu quota.

Kiểm tra pipeline/ref/policy, migrations, same-key enqueue, scoped reuse/template proposal, viewer/CSRF/host/workspace isolation, `SKIP LOCKED`, expired lease fencing, attempts/recovery, parse failure và crash trước publish canonical. Snapshot DDL không phụ thuộc ORM của migration tương lai. Destructive downgrade bị chặn.

Test harness không đưa secret vào output. Nếu không thể tạo schema an toàn, dừng và báo BLOCKED; không chuyển sang SQLite hoặc tạo Compose test project.

## Frontend và E2E

```powershell
npm --prefix frontend ci
npm --prefix frontend run check
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend run test:e2e
```

Playwright chạy trên Nginx production tại `127.0.0.1:18180`, một Chromium worker. Foundation reuse đúng một project có tên/scope E2E rõ ràng theo provider mode; nếu không có mới tạo qua UI, nhiều matches thì dừng. Mỗi run dùng CSV bytes/filename mới với UUID ở một ID tổng hợp không thuộc oracle tiền; giữ các mẫu zero-prefix/invalid/null/zero và đáp án cũ. Không approve lại table cũ, không invalidate artifact lịch sử. Không xóa project/dữ liệu cũ, không thêm delete API. Project count được kiểm trước/sau lần replay để chứng minh không tăng tiếp; artifacts/jobs tổng hợp vẫn tăng có chủ đích, cần chủ dự án quyết định retention về sau. UI contract tests search120projects/80datasets chỉ intercept GET và không tạo dữ liệu production. Mặc định MANUAL bỏ chọn yêu cầu AI, không gọi Gemini/Qwen; có thể đặt `STUDIO_EXPECT_AI_PROVIDER=MANUAL` explicit. Khi kiểm tra Gemini live phải chỉ định explicit trước khi chạy:

```powershell
$env:STUDIO_EXPECT_AI_PROVIDER='GEMINI'
npm --prefix frontend run test:e2e
```

Chế độ này có thể tiêu thụ tối đa hai HTTP attempts cho một bảng tổng hợp, vẫn chịu trần global/workspace; test kiểm tra provider trước khi upload để không gọi cloud nhầm chế độ. Chờ job Gemini SUCCEEDED, kiểm tra source GEMINI, reference mapping theo oracle độc lập và chưa AI tự duyệt rồi thực hiện luồng review/normalization. Nghiệm thu lại: **9 PASS ở Gemini LIVE (20,3 giây)** và **9 PASS ở MANUAL (16,2 giây)**, không cộng thành 18 case khác nhau. Regression xác minh refresh cùng revision giữ draft/grain/locale. Case document đọc hai artifact cached khi quyền parser đã đóng, kiểm tra IDs/amounts, không có nút normalize và không overflow ở mobile. Không hạ validator để làm test PASS. Provider failure/cloud OFF tiếp tục được kiểm tra bằng mock.

Các thời gian 20,3/16,2 giây là lần chạy trước chỉ dẫn thu hẹp. Lần chạy lại cuối cùng chỉ MANUAL, 9 PASS/19,6 giây. Trước HTTP/E2E, dùng `./tools/verify-local.ps1` khi proof local không hợp lệ; 403 trước xác minh là fail-closed theo thiết kế, không tắt auth để chạy tests.

Kịch bản: tạo project → upload → xem `000123` → xác nhận metric/locale/currency → approve → normalize → canonical/errors → evidence. Người quay lại thấy mapping/artifacts. Session HttpOnly/SameSite, CSRF và Host spoof rejection, 0 external browser requests được kiểm tra. Regression trì hoãn request tìm kiếm xác nhận UI không trình bày preview cũ dưới query/phiên bản mới.

Responsive: 1440×900, 1920×1080, 1366×768, 768×1024 và 390×844; chờ nội dung thực trước khi kiểm tra overflow, chụp Dashboard/Mapping và mở/đóng upload modal bằng Escape. Screenshots chỉ có dữ liệu tổng hợp, lưu ở `runtime/screenshots` bị Git ignore. Kiểm tra tự động và xem ảnh chưa tương đương audit toàn bộ WCAG 2.2 AA.

## Persistence và deployment

```powershell
./tools/check-persistence.ps1
```

Đợi hết jobs đang chạy. Công cụ snapshot metadata/approvals/canonical refs và kiểm tra SHA256 từng artifact, restart rồi force-recreate đủ bốn service và recreate riêng frontend trong project hiện tại, xác nhận auto-session bị chặn trước re-verification và so lại dữ liệu. Bao gồm workspace policy, reservations, document JSON và raw/Parquet; quota không reset. Không xóa volumes hoặc raw. Snapshot kiểm tra nằm trong volume, không vào Git. Snapshot nghiệm thu lại gồm 17 datasets, 12 canonical, 42 jobs/45 attempts và 58 artifact refs.

Snapshot lần Final Acceptance cuối: 19 datasets/versions, 14 canonical, 46 jobs/50 attempts, 48 audits, 15 traces và 66 artifact refs. Metadata/checksums và quyền parser OFF giữ nguyên sau cả ba kiểu restart/recreate; chỉ dùng project Compose hiện có. Các số 17/12/42/45/58 phía trên là mốc trước khi tạo thêm fixtures E2E/recovery, không phải dữ liệu bị thay thế hoặc mất.

## Worker bị dừng đột ngột

```powershell
uv run python tools/check-worker-recovery.py
```

Đã chạy SIGKILL thật khi worker chuẩn hóa 75.000 dòng tổng hợp, sau khi xác minh không có job khác đang xử lý. Job riêng của phép thử được đặt lease hết hạn ngay sau kill để không phải chờ 300 giây; worker được khởi động lại bằng Compose hiện tại. Kết quả: hai attempts, đúng một canonical được công bố, đủ 75.000 dòng, raw hash và parsed ref giữ nguyên. Không xóa dữ liệu hoặc dừng container dự án khác. Dự án tổng hợp được giữ lại làm bằng chứng.

## Benchmark cục bộ

```powershell
uv run python tools/benchmark-foundation.py
```

Đã đo trên Windows/Ryzen 5 7535HS, 16 GB RAM, Python 3.12.14, hai Polars threads; không dùng GPU. Mỗi cỡ chạy ba subprocess mới, CSV hai cột tổng hợp, mỗi 1.000 dòng có một invalid amount. Không gọi AI. Kết quả đo trong phiên nghiệm thu:

| Dòng | Parse p50 / p95 ms | Profile p50 / p95 ms | Normalize + write p50 / p95 ms | Peak process MiB |
| ---: | ---: | ---: | ---: | ---: |
| 1.000 | 22,53 / 96,36 | 2,93 / 16,26 | 38,36 / 81,17 | 77,59 |
| 10.000 | 35,00 / 36,93 | 14,13 / 14,89 | 232,91 / 234,77 | 92,84 |
| 50.000 | 57,87 / 58,77 | 65,14 / 65,28 | 1.228,25 / 1.420,63 | 172,71 |

p95 là nội suy inclusive trên ba quan sát, không phải cam kết tail latency. Đây là benchmark cục bộ hẹp, không đo SQL/API/network/browser, mapping AI, workload nhiều cột, 100k dòng hoặc matching. Artifact đo chi tiết ở `runtime/benchmarks.json`, không commit runtime data. Không tuyên bố mapping precision ≥98% hoặc khả năng xử lý mọi file từ các số đo này.

## Qwen live và kiểm tra source

```powershell
uv run python tools/check_repository.py
git diff --check
```

Qwen được hoãn chính thức: `BLOCKED_EXTERNAL_DEPENDENCY — IP allowlist`, không probe lại trong nhiệm vụ này. Tool probe vẫn được giữ cho khi chủ dự án cấp quyền sau. Gemini mapping live và oracle đã PASS, prompt `schema-understanding-2` giữ nguyên. Sau nghiệm thu lại dùng 6/10 requests, còn 4; không reset/tăng để chạy tiếp.

## LlamaParse live có allowance riêng

Đã kiểm tra đúng một PDF và một DOCX tổng hợp, mỗi tài liệu 1 trang/3 credits, tổng 2 trang/6 credits. Raw ID/amount/date/blank cells khớp oracle literal trong `tools/check-document-acceptance.py`; HTML table và Markdown table chỉ là hai cách biểu diễn cells, không tự sửa số. Tier cost_effective, server cap 2 trang/job, two-SHA allowlist, durable reservations: tối đa 2 docs/4 trang/12 credits theo giá đã xác minh, không vượt 20 được cấp. Trước thử API account xác nhận credits đủ; không dùng POST để thăm dò.

Lỗi thật được giữ regression: upstream job ID là opaque `pjb-*`, không bắt buộc UUID. PDF đã được nhận, được tìm lại receipt duy nhất rồi resume GET, không POST lại; attempt lỗi và reservation cũ vẫn còn. Sau thử đã thu hồi quyền tạo job toàn hệ thống/workspace, giữ key/history/artifacts. Chạy lại `uv run python tools/check-document-acceptance.py` hiện chỉ đọc cached refs; không tự mở allowance. Parser contracts có success/error/cloud OFF, page cap, resume không reserve/POST và prefixed ID.

PDF fixture đã render/kiểm tra hình ảnh. Renderer DOCX bundled trên Windows thiếu LibreOffice, nên không tuyên bố visual QA Word local; nội dung và số trang đã kiểm tra bằng kết quả provider có page cap và oracle, cùng UI cached. Hai fixtures là dữ liệu kiểm thử, không phải tuyên bố OCR tài chính đại diện hoặc artifact đã READY. UI không thực thi provider HTML và không tự normalize document.

Repository checker rà known local credentials trong source candidates/Git history, các pattern secret phổ biến, runtime/binary candidates và đường dẫn Markdown. Kết hợp rà nội dung/diff trước public push; đây không phải bảo đảm đã audit mọi kiểu secret hoặc toàn bộ bảo mật hệ thống.

## Reconciliation acceptance

Các mốc số liệu ở phần trên là lịch sử Giai đoạn 1. Suite hiện thêm contracts/golden/property/reporting và PostgreSQL tests. `tools/test-postgres.ps1` làm mới đúng `/tmp/studio-tests` trước copy để không tạo `tests/tests` rồi chạy nhầm bản cũ; chỉ xóa cây source test tạm cố định trong backend, không chạm volume/storage. Bản pytest/hypothesis tạm dùng chung container, không tạo server/Compose test khác.

```powershell
uv run pytest -q -m 'not integration'
./tools/test-postgres.ps1 -All
uv run ruff check backend tests tools
uv run mypy backend/studio
npm --prefix frontend run check
npm --prefix frontend run lint
npm --prefix frontend run build
$env:STUDIO_EXPECT_AI_PROVIDER='MANUAL'
uv run python tools/check-reconciliation.py
npm --prefix frontend run test:e2e
./tools/check-persistence.ps1
uv run python tools/benchmark-reconciliation.py
uv run python tools/check_repository.py
```

| Golden catalogue | Evidence |
| --- | --- |
| T17–T20 | Invented source/field/evidence/AI APPROVED rejected; gross/net/stale/wrong scope/expired dates/cardinality blocked; incomplete coverage explicit partial; unapproved ID cannot execute |
| T21–T24 | Manual oracle Internal/Shopee partition 11 = 1 invalid + 5 outside + 5 inside; zero-prefix/composite linkage; duplicate reviews; same ID amount diff LINKED/AMOUNT_MISMATCH |
| T25–T26 | TikTok 1:N 20+30=50 with both members; inverse N:1; mixed currency NOT_COMPARABLE, no delta; signed refund retained |
| T27–T28 | Near rigid IDs not auto-fuzzy; approved text blocking, bounded score/top-k, all ties/competing edges review-only; four synthetic admissible labelled pairs retained (not a representative blocking recall benchmark) |
| T29–T30 | Exact/within/beyond boundary; null versus real zero; no null/invalid coercion; explicit date cutoff/coverage/due date |
| T31–T33 | Corrupt amount or reused membership fails independent verifier; fault after draft write leaves no official metrics; retry publishes one logical run; failed verification has no metrics/exports |
| T34–T35 | Zero denominator N/A; manual count/Decimal oracle; immutable snapshot identical API/CSV/XLSX; UI uses DTO; review leaves original snapshot equal; formula injection, numeric negatives, exact XML values, IDs checked by opening outputs |

PostgreSQL migration test first creates approved canonical with historical migration, then upgrades head and compares artifact DTO/preview/counts; stale source/viewer/cross-project evidence/foreign group rejected. Template reuse returns PROPOSED with no contract ID and requires fresh approval. Existing Giai đoạn 1 tests remain in the same suite.

Playwright adds manual rule builder → validate → save → approve → run → verified dashboard → exception evidence/review → XLSX download → reload/run selection, plus result layouts 390/768/1366/1920; combined with prior 1440 and Giai đoạn 1 flow. Screenshots wait for real detail rows, not loading placeholders. It never presses paid planner. Backend/API demo covers upload/manual mapping/normalization for all five labelled source files.

Benchmark measures simple exact match on **total input records across both sources**: 1k (500/source), 10k (5k/source), 50k (25k/source), three new Windows processes/size. Matching p50/p95 ms: 31,57/37,58; 268,01/433,78; 1723,77/1792,43. Verification p50/p95: 17,06/19,02; 230,28/257,09; 1315,23/1521,31. Peak process MiB: 38,68 / 89,10 / 317,06. 500/5k/25k exact groups, zero fuzzy/review/cloud. Ryzen 5 7535HS/16 GB, no GPU. Excludes API/network/load/write/export/render and snapshot's additional verification pass; p95 is inclusive interpolation over 3 observations. Not a calibrated accuracy/throughput claim or 50k rows per source.

Actual final PASS/FAIL/SKIP and persistent object counts are recorded in [implementation status](IMPLEMENTATION_STATUS.md); do not add historical/live/mock replays into one inflated test count.

## Kiểm toán bổ sung Giai đoạn 2 — 28/10/2026

Giữ nguyên oracle và matcher/verifier. Thêm regression vào các suite có sẵn:

- Planner: request không join keys, schema khác field IDs, typed suggestions khi thiếu coverage; giả field/evidence/basis/cardinality hoặc đổi facts đã xác nhận bị từ chối. Context sai refs/workspace/stale bị chặn trước reservation. PostgreSQL quota hết dùng MockTransport, xác nhận 0 provider calls và manual proposal vẫn hoạt động; không thêm reservation trong ứng dụng thật.
- Readiness: cùng ID hai tháng không trùng trong kỳ; duplicate thật trong kỳ, filter carrier/platform, missing date/invalid key và incomplete coverage. Đối chiếu cùng định nghĩa partition của engine, không sửa verifier.
- Evidence: workbook tổng hợp nhiều sheet, ID ở c1/tiền ở c3/zero-prefix; 1:N nhiều source members mở đúng ô của từng dòng. Viewer đọc được, không review; group project khác bị từ chối. Playwright bấm trường tiền thật và kiểm raw value/cột thực tế c4 của CSV demo, không hardcode c1.
- KPI: giữ numerator/denominator cũ; oracle 5 eligible CU, 2 full match, 4 automatically classified, 1 review. RESOLVED không đổi comparison/snapshot.
- Export CSV/XLSX: export trước review → RESOLVED → export lại cùng revision phải cùng export ID/bytes. Summary/API timestamp và FIRST_GENERATION scope khớp; financial snapshot vẫn nguyên. Report-1 lịch sử giữ nguyên.
- UI: period/timezone ban đầu trống, cần scope confirmation; Planner có thể hỏi trước keys, hiển thị review-only suggestions/lý do và chặn approve; provider budget error vẫn mở chỉnh thủ công. Planner E2E mới intercept endpoints hoàn toàn, **PASS MOCK**, không gọi Gemini.

Lệnh chuẩn ở trên chạy cùng Docker project. Sau recreate phải chạy `tools/verify-local.ps1`; nếu proof bị mất trong phiên gián đoạn, UI bị chặn LOCAL_DEMO_NOT_VERIFIED là fail-closed đúng thiết kế, cần xác minh deployment rồi chạy lại E2E. Không bỏ kiểm tra auth hoặc tăng timeout để che lỗi.

So sánh baseline 121 backend/14 E2E với kết quả thật ở mục K của báo cáo; không cộng các lần replay hoặc PASS LIVE lịch sử vào số cases hiện tại. Prompt planner sửa đổi chưa test live theo chỉ định 0 cloud requests.

## Assistant contracts và hội thoại

`tools/test-postgres.ps1 -All -Source` chạy nguồn feature trong thư mục tạm của Backend hiện có và UUID schema trên PostgreSQL hiện có; không sửa `/app`, không tạo Compose/server riêng. Khi đã deploy đúng image dùng `-All` để kiểm runtime thực. Suite bổ sung T36–T40, privacy actor/project/run, ID giả, KPI thiếu, idempotency, concurrent pending requests, cache FactSet, xóa hội thoại đang chờ, lease/fencing và durable task reservation. Transport provider dùng MOCK; không dùng quota live.

Frontend Assistant thêm contextual panel, citations/source evidence, khôi phục và phân trang hội thoại, workflow hai/ba nguồn qua API reuse hiện có. Idempotency-Key explicit được giữ khi retry; reuse trả PROPOSED cần người dùng duyệt. Nguồn/kỳ/coverage/mẫu không được suy ra từ câu nói thiếu năm hoặc thiếu nguồn.

Nguồn candidate đã replay toàn bộ: **176 backend (138 offline/38 PostgreSQL)** và **54 Playwright (9 foundation/25 interface/7 reconciliation/13 Assistant)**; bằng chứng và revision cụ thể tại mục P của [báo cáo](IMPLEMENTATION_STATUS.md). T36–T40 nằm trong các suite, không cộng thêm số cases. Backend ở `9c565a6` không đổi byte sang `9802545`; E2E cuối chạy trên images `9802545` đã đối chiếu source và assets.

| Catalogue | Bằng chứng Assistant |
| --- | --- |
| T36 | LOCAL_ONLY/task OFF không reserve/gọi cloud; adapter Qwen HTTP 403 MOCK vẫn giữ tests cũ, không fallback live |
| T37 | fake FactSet/fact/evidence, extra amount/prose và claim không hỗ trợ bị reject |
| T38 | context/project/workspace/actor/run/case/group và cursor sai bị từ chối; E2E chặn response hội thoại muộn sau đổi project |
| T39 | metric ngoài snapshot trả thiếu bằng chứng, không tính lại hoặc gọi provider |
| T40 | oracle delivery 12.75 − 10.00 = 2.75 VND; Shopee delta 10.00; TikTok EQUAL không bị gọi là mismatch; đúng run/snapshot/rule/evidence và không bịa phí |

Luồng ba file dùng upload thật trên UI, approval/normalization qua API có auth cho fixtures tổng hợp mới, rồi UI đề xuất hai cặp → xác nhận → kiểm tra/lưu/duyệt rule → chạy verified → hỏi chênh lệch → export. Bộ foundation riêng tiếp tục kiểm Smart Setup/mapping/normalization trên UI; Planner dùng MOCK, không dùng quota live. Không thay oracle để ép TikTok có mismatch; không bỏ validation READY cho fixtures chứa lỗi.

Benchmark: `uv run python tools/benchmark-foundation.py`, `uv run python tools/benchmark-reconciliation.py`; `benchmark-assistant.py` copy/chạy trong Backend hiện có để đo Parquet evidence và read-only SQL. Không tạo service/container mới. Kết quả là samples tổng hợp; không suy ra precision/recall đại diện hoặc SLA. `check-worker-recovery.py` kiểm SIGKILL normalization thật; PG tests kiểm stale claim/fencing/không duplicate Assistant response và unknown delivery. `check-persistence.ps1` kiểm cả ConversationRow/MessageRow sau restart/recreate và frontend-only recreate. Backup/restore commands tại [README](../README.md); backup codec có regression chống JSON giả type tags.

## Agent-first — kết quả và cách kiểm chứng mốc S ngày 02/11/2026

Kết quả mới nhất: **248 backend/PostgreSQL PASS, 0 FAIL/SKIP**, 52,45 giây; **72 Playwright PASS, 0 FAIL/SKIP/flaky**, 226,72 giây trên app source `95d2956`. Ruff, mypy 42 modules, ESLint, TypeScript/build và repository/secrets/history/Markdown paths PASS. Các con số ngày 28–30/10 ở trên là lịch sử, không thay số mới. Full MVP chưa nghiệm thu do NLP quality và hết Gemini quota.

- `tests/test_agent.py`: typed intent/tool bounds, IDs/authority, cloud OFF không HTTP/reservation, cardinality, source column exactness, PAID khác COMPLETED, enum/grouping/all-status population, known-repair guards và rubric độc lập.
- `tests/test_agent_postgres.py`: queue/worker/API/mapping/normalizer/verifier thật, provider MOCK có nhãn; review -> atomic rollback -> approve -> resume, expiry/nonce/stale/viewer/cancel, bootstrap/dedup, approved-rule reuse/new-period review, tombstone/NL reply publish/context và durable blocked.
- `tests/test_data_query_postgres.py`: count/tổng 3 dòng 25+12,75+5=42,75 VND, ALL_MATCHING/paging/group provenance/currency/null/Decimal, verified immutable member/comparison values, missing-side filtering và authorization.
- Catalogue T01–T40, golden/property/security cũ tiếp tục chạy. Không cộng replay hoặc catalogue IDs thành số tests mới.

Chạy trong source/backend và UUID schema của PostgreSQL hiện có, không tạo Compose hoặc DB server mới:

```powershell
./tools/test-postgres.ps1 -All -Source
uv run ruff check backend tests tools
uv run mypy backend
npm --prefix frontend run lint
npm --prefix frontend run check
npm --prefix frontend run build
$env:STUDIO_EXPECT_AI_PROVIDER='MANUAL'
npm --prefix frontend run test:e2e
uv run python tools/check_repository.py
```

Không recreate container trong lúc PG source tests đang dùng `/tmp` của container đó. Sau restart/recreate, verify-local phải PASS trước UI checks; 403 trước proof là fail-closed mong đợi, không tắt auth/CSRF. Provider trong regression MOCK không phải Gemini LIVE.

### Browser và visual

72 cases gồm 59 cũ + 7 Agent + 1 delayed report/Back regression + 5 layout cases. `frontend/e2e/assistant-layout.spec.ts` kiểm **18 states × 5 widths = 90 screenshots**, MOCK CONTRACT: empty, short, long, upload, running, review, completed, wide table, chart, evidence, history, multiline, keyboard, sidebar, delete, error, permission, loading. Kiểm one composer, review binding/cancel giữ draft, delayed old workflow không đổi run chip, delete confirmation/focus và không page overflow/error. Không cộng ảnh thành tests.

Ảnh trước `runtime/agent-ui/empty-{width}.png`, sau `runtime/assistant-layout/{width}/{state}.png`; đã xem ảnh trọng yếu mobile/tablet/desktop. Không nhận được hai sketches trong attachment nên exact sketch match NOT VERIFIED. Keyboard viewport mô phỏng không chứng minh thiết bị vật lý hoặc WCAG/screen-reader certification.

### Gold và Gemini LIVE

`tests/fixtures/agent-intents.json`: 60 câu/2 miền + 20 negative, oracle độc lập. `tools/benchmark-agent.py` đo routing, **không execute tools**; inferred dispatch khác workflow completion. Lịch sử prompt 5: **80 measured, intent 68/80, source 53/60, slots 21/34, inferred dispatch 70/80, safe abstention 20/20**. Strict negative intent 18/20. Rubric D27 đã sửa population và chấm stored replies bằng 0 HTTP, không đổi gold để ép PASS.

Tám batch đầu và ba known completed failed batches đo lại một lần: tổng 11 HTTP, năm batch thành công cached. Flag `--repair-known payment-status-grouping` chỉ cho HTTP 200/STOP semantic/JSON fail đã biết, giữ original job và repair_of; không cho HTTP error/timeout/unknown delivery/truncation. Các lỗi lịch sử không bị ghi đè bằng success mới.

**Không chạy lại live hiện tại:** global/demo workspace **50/50 còn 0**, Agent 33/33, Planner 10/10. Full 80-case gold trên prompt 6 **NOT VERIFIED/BLOCKED**, không lấy prompt 5 thay thế. Representative live journeys có receipts riêng ở mục S báo cáo; 16 parent workflows qua các rounds gồm 9 COMPLETED/5 BLOCKED/2 WAITING_REVIEW. Không báo 100% automation hoặc production readiness.

Native read-back sau live: 2 domains giữ raw SHA/canonical/snapshot; paid/missing/variance/explanation đúng oracle; count 3/sum 42,75 VND/full lineage. Export XLSX 15.837 bytes/8 sheets/4 groups/6 members, snapshot full match 1/3=33,33%, variance 2,75 VND, zero-prefix và unmatched null đúng. Reload/native evidence mở đúng cell, không cloud. Receipts local ngoài Git, không tạo request để làm đẹp số live.

### Recovery, persistence và performance

- `tools/check-worker-recovery.py`: cùng worker, fixture TEST 75k, SIGKILL/lease reclaim -> 2 attempts/1 canonical -> Agent resume COMPLETED, model_calls 0, raw SHA nguyên, 13,797 giây cả hành trình. Native query 75k trả 50/allmatching 75k, 132,09 ms một sample.
- `tools/check-persistence.ps1`: 3/3 metadata/file comparisons và 3/3 fail-closed PASS qua restart/recreate/frontend recreate, gồm workflow/review.
- `tools/check-backup-restore.py`: cùng PG, UUID restore schema, 24 tables/764 files, backup SHA/corruption/traversal checks; public không overwrite, host copy đủ SHA. Không tự gọi lại nếu đã có receipt hợp lệ và không thay dữ liệu.
- `tools/rollback.ps1`: accepted 5f358c4 trên additive schema hiện tại, chặn active jobs/workflows, giữ volumes/schema/reviews; legacy không resume Agent mới. Đã drill full snapshot/report/export rồi trở về candidate và kiểm lại source/assets/products.
- 3 samples/mốc 1k/10k/50k trên Ryzen 5 7535HS, khoảng 16 GB/Polars 2 threads, không GPU/AI. Foundation 50k normalize+write p50/p95 1.153,76/1.260,90 ms, peak 166,42 MiB; exact recon 50k total match 1.473,57/1.474,98 ms, verify 1.192,72/1.214,17 ms, peak 319,06 MiB. Chi tiết đủ stages/mốc ở `runtime/benchmarks.json`, `reconciliation-benchmark.json`; không suy SLA hoặc fuzzy/100k/production load.

Bảng PASS LOCAL/MOCK/LIVE/FAIL/BLOCKED/NOT VERIFIED/DEFERRED, Git/Docker identity và paths receipts ở [IMPLEMENTATION_STATUS mục S](IMPLEMENTATION_STATUS.md). Merge/release/image cleanup chỉ sau quality gates, không dựa riêng số tests PASS.

## Assistant Experience — kết quả hiện hành, mục T

- `tools/test-postgres.ps1 -All`: **259 PASS, 0 FAIL/SKIP**, 72,00 giây trên deployed source dc8fcc5. Bao gồm foundation, engine/verifier/financial oracle, Agent/query/review/auth/security/backup contracts. Một Starlette/httpx deprecation warning từ dependency; không đổi dependency để che warning.
- Ruff PASS; mypy **47 source files PASS**; frontend check/lint/build PASS.
- Full Playwright **81 PASS, 0 FAIL/SKIP/flaky**, 269,23 giây. 72 regression cũ + 9 ca Assistant experience; giữ assertions/oracle. Legacy navigation tests dùng deep links/manual fallback; run cũ ngoài trang đầu được chọn qua nút phân trang thực.
- Visual MOCK CONTRACT **23 states × 5 widths = 115 ảnh**, gồm PARTIAL/FAILED/Gemini unavailable/export/long filename. Kiểm keyboard/focus/history/review/composer, source/canonical/errors/download/result overlay, URL/draft retention; 5 ảnh trước và 5 ảnh sau sidebar. Đã xem ảnh mobile và desktop; keyboard viewport mô phỏng không là kiểm chứng thiết bị thật/WCAG certification.
- Gold Gemini LIVE routing 15 **79/80 intent, 59/60 nguồn, 34/34 slots, 79/80 inferred dispatch, 20/20 safe và strict negatives**. Variants riêng **24/24, 16/16, 10/10, 24/24 dispatch, 8/8 negatives**. Ca D04 hỏi lại không cần thiết được giữ FAIL ở receipt, không sửa rubric.
- Native LIVE **10/10**: chuẩn hóa reuse hai miền, reuse contract hai miền, paid query, exact-key explanation, XLSX export, chart tổng theo currency, chart PAID/UNPAID giữ đủ population và clarification thiếu paid semantics. **9 COMPLETED + 1 WAITING_REVIEW đúng kỳ vọng**, mỗi request đúng 1 model call, không thêm approval cho facts đã duyệt. Native oracle được so riêng với gold router.

Các receipts mới: `runtime/assistant-experience-backend-final.log`, `assistant-experience-e2e-resumed.json`, `assistant-experience-gold-final.json`, `assistant-experience-variants-final.json`, `assistant-experience-native-workflows.json`, `assistant-experience-usage.json`. Runtime receipts/synthetic data không vào Git. Theo dõi recovery/persistence/backup/rollback và Git/Docker cuối tại IMPLEMENTATION_STATUS mục T.

Final reliability source dc8fcc5: recovery 75k/2 attempts/1 canonical/Agent COMPLETED/0 cloud/12,984 s; backup 24 tables/981 files, UUID restore + host SHA verified; accepted rollback and return full snapshot/source/assets PASS. Variants đã tham gia chẩn đoán, không là blind holdout. Chi tiết/hash/receipts ở mục T.

Main release f1ad9f1 có application diff rỗng so với dc8fcc5 đã full regression; build mới, identity/health/full snapshot và read-back 10 workflows + financial/evidence/export PASS, 0 AI calls thêm. Các commit sau release chỉ tài liệu, không suy healthcheck thay functional acceptance.
