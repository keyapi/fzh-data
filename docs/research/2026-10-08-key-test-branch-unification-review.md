---
type: Research
title: key_test 生产线 vs 测试线 逐文件评审清单（合并到新 main 前的取舍表）
description: 生产线(production-backup) 与测试线(main) 分叉已久；22 个双边都改的文件按「纯格式 / 测试侧变薄(功能已搬到别 app) / 测试侧领先 / 需人工看」分档，附体量、最后改动、证据与待决策点
---

# key_test 生产线 vs 测试线：逐文件评审清单

> 2026-10-08。母文档：`docs/solutions/workflow-issues/key-test-login-hook-and-prod-test-divergence.md`（隐患 3 / 评估）。
> 目的：为「以生产为基线建 main-new、再把测试侧仍需要的改动 port 过去」提供可直接过会的清单。

## 数据来源与方法

本地 `git clone --bare git@github.com:keyapi/key_test.git`（含全部 GitHub 分支）后：

- 生产线已补齐并推送：`production-backup` @ `c87759a`（含本次 `on_session_creation` 修复）；测试线备份为 `backup/test-main-20261008` @ `132c1d0`。
- 分叉度量：`git rev-list --left-right --count production-backup...backup/test-main-20261008` → 生产独有 **28** / 测试独有 **73**；共同祖先仅 1 个旧提交（`33b7012`）。
- 区分「格式噪声 vs 真实改动」：用 `git diff --ignore-all-space --numstat`；输出 `0/0` 的判为纯格式。
- 功能是否已迁走：在 `work_order_task`（GitHub `keyapi/work_order_task` @ main）里反查同名函数。

## 全局结论

- 两棵树：**41 个文件只在测试**、**22 个两边都改过**、**0 个只在生产**。
- **不能机械二选一**：22 个里至少有 2 个是「测试侧删掉了本地实现、改成引用 `work_order_task`」，若取生产侧会把已迁走的功能又抄一份回来；另有若干文件测试侧已加改进。
- 测试侧独有的 41 个文件里，约 20 个是试验件、约 11 个是 QR/批号功能的「另一套实现」。

## 分档表（22 个双边都改的文件）

### A. 纯格式差异 —— 取任一侧即可（建议生产侧，零风险）· 3 个

| 文件 | 依据 |
|---|---|
| `key_test/doc_events/work_order.py` | 忽略空白后 diff 为 0 |
| `key_test/key_test/doctype/logistic_price_list/logistic_price_list.json` | 同上 |
| `key_test/key_test/report/bom_cost_list/bom_cost_list.json` | 同上 |

### B. 测试侧「变薄」—— 生产侧代码更多，但可能是历史遗留 · 6 个

| 文件 | 生产行/测试行 | 生产侧独占的最后改动 | 说明 |
|---|---|---|---|
| `key_test/production_utils.py` | 1973 / 627 | 2025-08-20 修正…删除没用的引用 | **已证实**：测试侧 import 了 `work_order_task`，把本地实现删掉了 |
| `key_test/overrides.py` | 629 / 76 | 2025-08-14 | **已证实**：生产侧那份是 ERPNext Work Order / Production Plan 的方法猴补丁（`make_work_order`、`get_sub_assembly_items`…），这些现在在 `work_order_task/work_order_task/overrides/production_plan_override.py`（测试侧只留 1 个函数） |
| `key_test/bom_cost_updater.py` | 567 / 338 | 2025-08-14 | 待确认（`work_order_task` 里没找到同名实现） |
| `key_test/add_item_semi.py` | 556 / 392 | 2025-11-21 | 两边同一天同名提交（手工拷贝同步的痕迹）；两侧顶层 def 数相同(6)，差在函数体 → 需逐段比对 |
| `key_test/public/js/item_group.js` | 298 / 191 | 2025-08-14 | 待确认 |
| `key_test/bom_utils.py` | 637 / 554 | 2025-08-14 | 待确认 |

> **B 档的判定口径**：先问「这段代码是不是已经搬去 `work_order_task`/`light_mes` 等 app」——
> 是 → 取测试侧（薄版，避免双份维护）；否 → 才考虑保留生产侧并排期搬迁。

### C. 测试侧领先/更全 —— 逐个 review 后 port · 12 个

| 文件 | 生产→测试 | 要点 |
|---|---|---|
| `key_test/hooks.py` | +79/-22 | 含本次 `on_session_creation` 修复；其余差异是测试侧启用了 `doc_events` 的 Batch / Purchase Receipt 等 |
| `key_test/setup.py` | +69/-62 | 测试侧多 QR 相关字段（`qrcode_section`/`qrcode_image`/`qrcode_display`/`batch_qrcode_image`）——与生产侧走 `erpnext_qrcode` app 是**两套实现**（见决策 1） |
| `key_test/key_test/report/work_order_merge_same_material.py` | +641/-944 | 大幅重写，需人工比对（测试侧 2025-07-29「测试修改EN原生报表」） |
| `key_test/key_test/report/work_order_merge_same_material.js` | +147/-11 | 同上 |
| `key_test/sales_order_utils.py` | +47/-0 | 测试侧新增的是**注释掉的死代码**（`# def get_sales_orders_with_items()`）→ 可不带 |
| `key_test/monkey_patches/report_patches.py` | +23/-0 | 测试侧多 light_mes 补丁（已注释）→ 可不带 |
| `key_test/key_test/doctype/logistic_price/logistic_price.js` | +31/-0 | 物流价格表单扩展 |
| `key_test/commands/__init__.py` | +19/-5 | 测试侧多 `setup_weight_template_fields(site=None)`（重量模板字段的站点安装助手） |
| `key_test/api/batch_qrcode.py` | +12/-0 | QR/批号两套实现的一部分（决策 1） |
| `key_test/item_alternative.py` | +1/-0 | 1 行 |
| `key_test/key_test/doctype/logistic_price/__init__.py` | +1/-0 | 1 行 |
| `key_test/key_test/doctype/logistic_price_list/__init__.py` | +1/-0 | 1 行 |

### D. 两边都改、体量相同 —— 人工看 · 1 个

| 文件 | 生产→测试 | 说明 |
|---|---|---|
| `key_test/public/js/bom_list.js` | +33/-33 | 356/356 行，改动量对称，非空白差异 |

## 测试侧独有的 41 个文件（分类）

| 类别 | 约数 | 处置建议 |
|---|---|---|
| QR / 批号功能一套（`qr_utils/`、`doc_events/batch.py`、`doc_events/purchase_receipt.py`、`commands/*qrcode*`、`public/js/purchase_receipt_qrcode.js`、`public/qrcodes/`） | ~11 | **两套实现二选一**（决策 1） |
| 试验/未启用（`doctype/excel_processing`、`doctype/item_cost`、`report/bom_cost`、`overrides/light_mes`） | ~20 | 不带（`report/bom_cost` 在测试 DB 里连 Report 记录都没有；`light_mes` 补丁已注释；`item_cost` 1 行数据、`excel_processing` 2 行数据） |
| 文档与生成物（`file_structure.md`、`key_test/README.md`、`docs/bom_cost_excel_cost_logic_for_claude.md`、`update_file_structure.sh`、`item.py`、`www/__init__.py`） | ~6 | 文档可留；`file_structure.md` 建议 gitignore（脚本产物） |
| 真实功能但仍少用（`report/bom_item_lead_time_days`） | ~3 | 需你定是否上生产 |
| fixtures（`fixtures/custom_field.json`、`fixtures/property_setter.json`） | 2 | 见下方事实 3 |

## QR/批号：四套实现，生产实际用的是哪套（2026-10-08 核对）

| # | 实现 | 性质 | 谁在用 |
|---|---|---|---|
| 1 | `work_order_task/api/batch_qrcode.py` → `generate_batch_qr_code` | **活**（包装 #2 的生成器） | **生产与测试各 10 个打印格式**用它现算：`{{ frappe.call('work_order_task.api.batch_qrcode.generate_batch_qr_code', batch_no=...) }}` |
| 2 | `erpnext_qrcode`（第三方 app "ERPNEXT QR Code"，两台都装） | **活**（提供 Jinja 方法 `generate_qr_code`） | 被 #1 调用 |
| 3 | 测试侧 in-house：`qr_utils/` + `doc_events/batch.py` + `doc_events/purchase_receipt.py` + `public/js/purchase_receipt_qrcode.js` + 2 个 bench 命令 + **7 个字段** | **旧实现**（PNG 落盘 + 写字段） | **无消费方**：0 个打印格式引用这些存盘字段。测试机 `public/files/qrcodes/` 74 个文件（最新 **2026-04-24**）；`Batch.qrcode_image` 28/129、`Purchase Receipt.qrcode_image` 43/247、`Purchase Receipt Item.batch_qrcode_image` **0**（该分支代码已注释） |
| 4 | `key_test/api/batch_qrcode.py`（两条线同内容，9 行包装） | 旧调用点 | 测试还剩 **1 个**打印格式 `采购入库jinjia带子表批次二维码`（启用中）在调它；**生产 0 个** |

**结论**：生产用的是 **#1 + #2**（打印格式里现算，不落库）——生产 DB 里没有任何 QR 自定义字段，`key_test` 侧唯一 QR 文件在生产是死代码。测试那套存量方案是**历史遗留**（4 月停写、无消费方、子表批次码从未产出），**不需要 port**；代码与数据留在 `backup/test-main-20261008`。

留在统一线里的 #4 让测试那 1 个打印格式仍可用；若要和生产彻底一致，把它改成 `work_order_task.api.batch_qrcode.generate_batch_qr_code` 即可（同一份生成器的包装，一行）。

## 更正：「测试在跑、生产没跑」的还有一项活功能（不是 QR 遗留）

| 项 | 测试 | 生产 |
|---|---|---|
| `key_test.tasks.update_bom_update_log_status`（每 5 分钟：把卡住的 `BOM Update Log`（Update Cost / In Progress）按子表批次状态收尾） | hooks 里**启用** | hooks 里**注释掉** |
| 卡在 `In Progress` 的 `BOM Update Log` | **0** 条 | **3** 条（总量 1173） |

⇒ 这是真正「测试在跑、生产没跑」的活功能（上一版把 QR/批号说成"唯一"，不准确）。生产那 3 条卡住与这个任务缺席的表现一致（未证实因果）。**已处理，见下节。**

## 统一后的收尾（2026-10-08，已完成并验证）

**① 5 分钟 BOM Update Log 收尾任务：已恢复**

- 发现：**生产那条线根本没有 `tasks.py`**（所以那边 hooks 里只能写成注释）——更正上一版"生产主动注释"的说法。
- 动作：把 `tasks.py`（27 行、仅此一个函数）从备份的测试线迁入统一线，并解开 hooks 里的 cron（`*/5 * * * *`）。
- 踩坑：只解开注释不够——Frappe 的 cron 要先 `bench migrate` 同步成 `Scheduled Job Type` 记录才会跑；第一次没 migrate，16:45:45 那次执行是 `Failed: No module named 'key_test.tasks'`（文件当时还没进 main）。
- 验证（生产）：`bench migrate` 后 Job Type 注册（`*/5 * * * *`, stopped=0）；16:50:18 执行 **Complete**；
  **3 条卡住的日志（BOM-UPDT-LOG-00046/00086/00121，2024-12 与 2025-02）全部变 Completed**，两台 In Progress = 0。
  这三条各只有 1 个子批次且都已 Completed —— 卡住纯粹是因为这个任务从没跑过。

**② 打印格式指向统一**（测试独占的那张）

`采购入库jinjia带子表批次二维码`（仅测试有，生产 0 张）原本调 `key_test.api.batch_qrcode.generate_batch_qr_code`，已改为
`work_order_task.api.batch_qrcode.generate_batch_qr_code`：

- 改后测试：调 work_order_task 的打印格式 11 张（原 10）、仍调 key_test 的 **0** 张（原 1）；生产 10/0。
- 新目标实测可用：`/api/method/work_order_task.api.batch_qrcode.generate_batch_qr_code?batch_no=00020` → 200，返回 `data:image/png;base64,...`。

**③ 清掉过期 DB 对象**

切换后测试剩 3 个「代码已删、DB 记录还在」的对象，生产一个都没有：

| 对象 | 处置 |
|---|---|
| `Report: BOM Item Lead Time Days` | **已删**（模块文件随切换移除，打开必报 ImportError） |
| `DocType: Item Cost` / `Excel Processing` | **未动**（各 1~2 行试验数据；DB 驱动，打开不报错，只是没有 controller）。要清可随时说 |

**④ 测试侧独有的 6 条 hook 全部有了结论**

| hook | 结论 |
|---|---|
| `commands.generate_batch_qrcodes.execute`、`commands.reset_qrcode_fields.execute`、`doc_events.batch.after_save`、`doc_events.purchase_receipt.after_save`、`doc_events.purchase_receipt.on_submit`（后两者确认只做 QR） | **放弃**（生产用 `work_order_task` + `erpnext_qrcode` 现算；测试那套无消费方） |
| `tasks.update_bom_update_log_status` | **已恢复**（见 ①） |

## 被引用/在跑的实测判定（2026-10-08）

### 测试侧独有的东西：哪些真在跑、哪些是死代码

| 判定 | 文件 | 依据 |
|---|---|---|
| **真在跑**（hooks 挂着） | `doc_events/batch.py` | hooks：`Batch.after_save` → 测试每次保存批次都会跑 |
| | `doc_events/purchase_receipt.py` | hooks：`Purchase Receipt.after_save` + `on_submit` |
| | `public/js/purchase_receipt_qrcode.js` | hooks：`app_include_js`（测试全站加载） |
| | `commands/generate_batch_qrcodes.py`、`commands/reset_qrcode_fields.py` | hooks：`commands` 注册了 2 个 bench 命令 |
| | `qr_utils/` | 被上述 3 处引用（QR 生成实现） |
| | `tasks.py` | hooks：6 处 scheduler 引用 |
| **死代码/试验** | `doctype/item_cost` | 0 处引用，测试仅 1 行数据 |
| | `doctype/excel_processing` | 0 处引用，测试仅 2 行数据 |
| | `report/bom_cost` | 0 处引用，测试 DB 里连 Report 记录都没有 |
| | `report/bom_item_lead_time_days` | 0 处代码引用（报表现存，是否有人用需另查工作台） |
| | `overrides/light_mes/*` | 唯一引用是 `report_patches.py` 里已注释的那行 |
| | `api/batch_qrcode.py` | **0 处引用**（测试也是死的） |

### 生产侧「多出来的代码」：是活代码，且被 work_order_task 的新前端调用

`work_order_task`（前端已迁过去的那个 app）**仍在调 key_test 的后端**：

```
work_order_task/public/js/work_order.js → key_test.production_utils.check_stock_for_work_order / create_job_cards_for_operations
work_order_task/public/js/bom.js        → key_test.add_item_semi.create_supporting_items_and_variants（一键生成配套物料）
work_order_task/public/js/bom.js, routing.js → key_test.search_item_by_item_group_and_name.*
key_test/public/js/bom.js               → key_test.bom_utils.*（deep_update_bom_cost / check_bom_update_chain）
key_test/public/js/bom_list.js, item_group.js → key_test.bom_cost_updater.*
```

⇒ **B 档必须取生产侧**（生产侧是"被调用方"的完整实现）；取测试侧的薄版本会打断这些按钮。

补充：`overrides.py`（生产 629 行 / 测试 76 行）**两边都是死代码** —— 它被同目录的 `overrides/` 包遮蔽（`key_test.overrides.bom_list` 才是真被 hooks 用的），且其中的 `CustomProductionPlan` 只在注释掉的 `override_doctype_class` 里出现过。清理候选，不急。

### 「生产能跑 ≠ 生产没问题」——生产 Error Log 里的真 bug

近 30 天生产 Error Log 有 **6 条** key_test 报错，最近 2026-09-19，方法名「检查工单库存出错」：

```
File "apps/key_test/key_test/production_utils.py", line 255, in check_stock_for_work_order
    "stock_uom": item.stock_uom
AttributeError: 'WorkOrderItem' object has no attribute 'stock_uom'
```

- 触发者：工单页的「检查库存」按钮（`key_test.production_utils.check_stock_for_work_order`）。
- 该 bug **两条线同源**（测试侧 `production_utils.py` 第 258 行是同一句），只是测试上没人点这个按钮（测试 Error Log 里无此报错）。
- 所以：主链路能跑，但按钮级报错被 Error Log 收着；「能跑」掩盖了它。

## 三个决策 → 实测结论

1. **QR / 批号留哪套？** 默认**按生产来**（生产在跑、且它不依赖测试侧那些 hooks）；测试侧那套（`qr_utils` + 两个 doc_events + 全局 JS + 2 个命令）**单独议**——如果一并 port 进 main-new，生产会在下次 `git pull` 后开始在每次采购入库保存/提交时跑新的 QR 钩子，风险未经评估，故不作为默认。
2. **B 档怎么取？** 已用证据定：**取生产侧**（理由见上「被 work_order_task 的新前端调用」）。例外是 `overrides.py`（两边都死）——取任一侧皆可，建议留生产侧保持与生产一致。
3. **已搬走的功能是否留双份？** 不留（`work_order_task` 里已有 `overrides/` 全套；key_test 侧只保留被调用的后端）。

## 已完成的动作（2026-10-08）

| 动作 | 结果 |
|---|---|
| 备份测试线 | GitHub `backup/test-main-20261008` = `132c1d0`（测试侧那 41 个文件/QR 一套都在这条线上） |
| 备份 GitHub 旧 main | `backup/github-main-20261008` = `2612db4` |
| **统一线落到 `main`** | `main` = `6f0940d`（= 生产线基线 + 登录 hook 修复 + 下方 stock_uom 修复 + 删带点空文件），强制更新（旧 main 已备份） |
| 两台服务器切到 `main` | 测试 + 生产均已 `git checkout -B main origin/main` + `clear-cache` + `bench restart`，验证通过（补丁仍在、登录 0.1x s、登录不再写元数据） |
| 生产 remote 改 SSH | `git remote set-url origin git@github.com:keyapi/key_test.git`（原来 HTTPS 无凭证，`git pull` 会卡） |
| 修复「检查工单库存出错」 | 见下节 |
| 删掉 `key_test/sales_order_utils.py.` | 文件名带**结尾点**、0 字节 → 该路径在 Windows 上非法，会让 Windows 克隆/检出直接失败（Linux 无感） |
| 清理测试机 Error Log 噪音 | 删掉 7 条探针报错（已复查 0 残留） |

**切换的副作用（已知、可回退）**：测试机切到 `main` 后，那 41 个测试独有文件被移除、QR/批号那套 hooks 停用（生产版 hooks 里本来就是注释状态）。要恢复测试侧那套 QR，从 `backup/test-main-20261008` 取码，并按「单独一次改动」评估（带上它会让生产下次 pull 后也开始跑新钩子）。

**遗留分支**（都可留可删）：`production-backup`（= `c87759a`，比 main 少一处修复）、`main-new`（= `c87759a`）、`fix/remove-on-session-creation`（测试线那版 hook 修复）、`fix/wo-item-stock-uom`（即当前 main）。

## 「检查工单库存出错」的修复（跨版本字段差异）

**根因**：`production_utils.py:255` 在库存不足时直接取子表字段 `WorkOrderItem.stock_uom`，而该字段是 ERPNext **新版本**才有的：

| 环境 | ERPNext | `Work Order Item.stock_uom` | 结果 |
|---|---|---|---|
| 测试 | 15.59.0 | **存在** | 一直正常 |
| 生产 | 15.43.3 | **不存在** | `AttributeError`（Error Log：9/8 十条 + 9/19 六条） |

命中条件：`skip_transfer` + `from_wip_warehouse` 且库存不足——所以只有生产、只在部分工单上炸，属于「能跑但按钮报错」。
（与本仓库 `docs/solutions/workflow-issues/erpnext-version-api-compatibility.md` 同一类坑。）

**修法**：改为从 Item 查 UOM——`frappe.db.get_value("Item", item.item_code, "stock_uom")`，两个版本都成立。

**验证**：

| 环境 | 方法 | 结果 |
|---|---|---|
| 测试 | console 跑 151 个 WIP 工单 | 0 异常；库存不足条目 UOM 正常带出（米/条） |
| 生产 | 切换后 console 跑 300 个 WIP 工单 | **0 报错**；UOM 正常带出（米）；此后无新增「检查工单库存出错」 |

## 核对过的事实（避免重复调查）

1. **测试侧 `key_test/fixtures/custom_field.json` 只含 Purchase Receipt 字段**，不含 2026-10-08 弹窗事故的那 6 个字段 → 弹窗修复**不会**因 key_test fixtures 复发（复发源是 `work_order_task` 的 fixtures，已修并合并）。
2. 生产侧 `key_test/fixtures/` 目录是空的，但 `hooks.py` 里声明了 fixtures → `bench migrate` 时是 no-op（无害，但也意味着生产这些字段只靠 `after_migrate` 钩子安装）。
3. 生产 remote 是 HTTPS 且服务器上无凭证 → `git push origin` 会卡 `could not read Username`；本次用显式 URL `git push git@github.com:keyapi/key_test.git <branch>` 推成功，随后已把生产 remote 正式改成 SSH。
4. 测试机上 `file_structure.md` 常驻未提交改动（`update_file_structure.sh` 的产物）——2026-10-08 差点被卷进我的提交，已拆出；切换分支前把内容备份到测试机 `/tmp/file_structure.md.bak` 后丢弃（该文件在统一线里不存在）。
5. 生产线里有个 `key_test/sales_order_utils.py.`（结尾带点、0 字节）——Windows 上非法路径，任何 Windows 克隆/检出该分支都会失败（`error: invalid path`）。统一线已删除。**结论：key_test 之前无法在 Windows 上克隆，就是它。**
6. 测试机上另有别人的 `zz_json_probe`（API Server Script）在反复报 `module has no attribute 'parse_json'` / `__import__ not found`——不是本次改动引起；按仓库「`zz_` 用完即删」的约定，建议提醒对方清理。
