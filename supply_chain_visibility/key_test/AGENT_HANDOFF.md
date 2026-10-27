# SO 表单「供应链链条摘要」内嵌 — Agent Handoff

> **目标**：在 ERPNext 销售订单表单里直接看到该单的链条摘要（阶段/已发/未发/工序进度），
> 零跳转。这是「呈现形式建议路线」的第 1 档（见
> `../docs/research/presentation-forms.md` §5）。

## 1. 做了什么（Stage 1：嵌入单据）

**载体 = `key_test` app**（house app；EN 自定义 app 是各自独立仓库 `keyapi/*`，见
`../docs/reference/en-supply-chain-map.md` §1）。

| 产物 | 落点 | 说明 |
|---|---|---|
| 服务端方法 | `key_test/key_test/so_chain.py`（新增） | `@frappe.whitelist()` `get_so_chain(sales_order)`，返回每行 stage/已发/未发/工单工序 |
| 前端 | `key_test/key_test/public/js/sales_order.js`（**追加**） | `refresh` 钩子 → 调方法 → `frm.dashboard.add_section` 渲染 |

**为什么 JS 要追加而不是新建**：`hooks.py` 的 `doctype_js` 对 Sales Order 只允许**一个**文件
（`"Sales Order": "public/js/sales_order.js"`）。Frappe 允许对同一 doctype 多次
`frappe.ui.form.on(...)`，所以并进该文件末尾。

**服务端口径**（与 `EN_API/item_shipment_status.py` / `fulfillment/` 一致）：订单行主键 `Sales Order Item.name`；
工单按 `production_item == 行 item_code 且 sales_order == 本 SO`；**工序进度取第一道工序（sequence_id 最小）完成量，不跨工序求和**；
**已发 = 出库单按 item_code 匹配的带符号 qty 之和（退货行负数自动抵扣）**；`WO.status/produced_qty` 不作事实。

## 2. 状态

> 本节以下为 2026-10-13 早期验证记录；既有功能已经生产发布，详见 §13–14。2026-10-26 新增过滤/权限与供应查询仍走 feature 分支测试，尚未生产发布。

- ✅ **测试机（`上海测试-阿里云-FZH-ERPNext-frappe`，站点 `erpnext.vilavi.cn`）已部署并验证（2026-10-13）**：
  - `so_chain.py` 语法 OK；`sales_order.js` 190→250 行；备份 `/tmp/sales_order.js.bak_*`。
  - `bench --site erpnext.vilavi.cn clear-cache`。
  - **方法验证**（REST）：`GET /api/method/key_test.so_chain.get_so_chain?sales_order=SO-24-00016`
    → HTTP 200，返回 6/2/1 行、stage/substate、工序进度、DN 净额均正确（抽样 SO-24-00002/00012/00016/00021）。
  - **JS 挂载验证**：`GET /api/method/frappe.desk.form.load.getdoctype?doctype=Sales Order`
    → `__js` 含 `so-chain-summary` 与 `so_chain.get_so_chain` ✅。
  - ⏳ **浏览器视觉未验证**（需登录 desk）；建议人工开一张 Sales Order 确认区块渲染。
- ✅ **既有版本生产已部署**：见 §13 的发布记录与 §14 的后续修复；新增 feature 功能单独验收。

## 3. 部署到生产（需确认后执行）

```bash
H=阿里云-FZH-ERPNext-frappe   # 生产
B=/home/frappe/frappe-bench/apps/key_test/key_test
# 0) 备份
ssh $H "cp $B/public/js/sales_order.js /tmp/sales_order.js.bak_$(date +%Y%m%d_%H%M%S)"
# 1) 传两个文件（so_chain.py 新增；sales_order.js 追加）
#    ⚠️ 生产 sales_order.js 可能与测试**基线不同**（分支割裂史）——先 diff 再加，别整个覆盖
# 2) 语法自检
ssh $H "python3 -c \"import ast; ast.parse(open('$B/so_chain.py',encoding='utf-8').read())\""
# 3) 只改 JS → clear-cache；改了 .py/hooks → restart
ssh $H "cd /home/frappe/frappe-bench && sudo -n -u frappe bench --site erpnext.vilavi.cn clear-cache"
#    （新增 .py 属新模块，Frappe 按点路径惰性 import，通常无需 restart；保险起见可 bench restart）
```

**回滚**：删 `so_chain.py` + 用备份还原 `sales_order.js` + clear-cache。

## 4. 做了什么（Stage 2：原生报表）

**Script Report「SO Chain Overview」**：每个「还未发完」的订单行一行（阶段 / 已发 / 未发 / 异常），
顶部出 KPI 卡（行数·未发总量·交期已过·死单）+ 阶段分布柱图。

- 文件落点 **`key_test/key_test/key_test/report/so_chain_overview/so_chain_overview.{py,json,js}`**
  ⚠️ **多一层 `key_test`**！模块名 == app 名，Frappe 的 report 路径 = `<app>.<module>.report.<name>.<name>`
  → 磁盘 `apps/key_test/key_test/**key_test**/report/<name>/`。放少一层 Frappe 找不到（会由 migrate 生成
  返回 `([],[])` 的桩）。
- Report 记录（DocType `Report`，`is_standard=Yes`/`report_type=Script Report`/`module=key_test`）需存在；
  可用 `bench --site X console` 建，或靠 migrate。
- **改/加 `.py` 后必须 `bench restart`** —— `clear-cache` 不重载 Python 模块（报错表现为端点返回 0 行、耗时 ~0）。

### 状态
- ✅ **测试机已部署并验证（2026-10-13）**：`query_report.run` 返回 **10 列 / 107 行 / KPI / 柱图**（耗时 0.10s）。
  文件已搬到正确路径；`bench restart` 后生效。
- ✅ 既有版本生产已部署（见 §13）；新增 feature 功能不随本状态自动获发布许可。

### 生产部署补丁（Stage 2）
```bash
H=阿里云-FZH-ERPNext-frappe
D=/home/frappe/frappe-bench/apps/key_test/key_test/key_test/report/so_chain_overview
ssh $H "mkdir -p $D" && 传 3 个文件
ssh $H "cd /home/frappe/frappe-bench && sudo -n -u frappe bench --site erpnext.vilavi.cn console <<< '<建 Report 记录的脚本>'"
ssh $H "cd /home/frappe/frappe-bench && sudo -n -u frappe /usr/local/bin/bench restart"
```

## 5. Stage 3 设计：小范围独立屏（暂缓）

不做全量大屏。只做「**例外队列 + ETA + 责任人**」小屏（Frappe UI(Vue) / 独立 SPA 走 REST）。
**反营销红线**（`presentation-forms.md` §1.2）：只做漂亮看板会「看板淹没」；
必须带阈值化 + 责任人路由。**度量**用例外解决时长/阶段停留，不是看板数量。
阶段 4–8（头程）数据仍外置（钉钉表/智美通），**本屏先只覆盖阶段 0–3**。

## 6. 关联

- `../docs/reference/en-supply-chain-map.md` — EN 全链路实体地图（**已更正**：Cutting Plan/Task、Work Order Split、Wip Transfer 生产 0 条；真实车辆是 Initial Work Order / Tracking Number / Job Card 自定义字段）
- `../docs/research/presentation-forms.md` — 四类形式调研 + 建议路线
- `EN_API/so_item_special_mark/README.md` — SO 表单定制的既有先例（Client Script→app 文件、hooks doctype_js、部署缓存要点）

---

## 7. Stage 1 v2：一对多的展示设计（2026-10-13）

**问题**：一条 SO 行下游是 `0..1 生产计划 → 1..N 工单 → 每工单 N 道工序(裁剪/…) + N 个菲号`，
**多层一对多**。旧版把「工单/工序」硬塞进一格（`|` 分隔），列不够、也没生产计划/菲号。

**调研结论（业界成熟 ERP + Frappe 能力）**：
- **Frappe 原生子表只有 2 层**（父→子），做不了「工单→工序→菲号」3 层；`Dialog` 里放 child table 还有已知只读 bug（frappe#17533）。
- 主流做法（SAP Fiori / Dynamics sub-grid / Cloudscape 等）= **摘要 + 可下钻**；Cloudscape 明确告诫「深层嵌套塞进表格会牺牲可读性与性能」。
- 结论：**主表只放摘要，多层结构放弹窗里自渲染只读 HTML 表**。

**v2 实现**：
- 主表一行 = 一条 SO 行：`物料 | 客户码 | 订单量 | 已发 | 未发 | 阶段 | 生产计划 | 工单 | 菲号`。
  生产计划列显示 PP 号(+计划量)；「工单」「菲号」是**可点 chip**（`N 张 ▸` / `M 个 ▸`）。
- 点开 = `frappe.ui.Dialog(size:'extra-large')` + HTML 字段，渲染 **工单 → 逐道工序(状态+完成量) → 菲号(数量+**开料工单**+交付物料)**。
  菲号「开料工单」非空 = **已开料**（用户要的「已开料就显示跟踪单号」）。
- 取数 `key_test.so_chain.get_so_chain` 扩展：按 `Sales Order Item.name` 挂 `Production Plan Item.sales_order_item`；
  工单 `production_item+so`；逐道工序完成量取 Job Card；菲号 `Tracking Number.work_order`（+`initial_work_order`/`so_materials`）。
- **状态**：测试机部署并 Playwright 验证（主表含新列、弹窗渲染 WO→工序/菲号层级）。

**业界依据（原始 URL）**：Frappe Connections https://docs.frappe.io/framework/user/en/basics/doctypes/actions-and-links.md ；
Frappe Dialog https://docs.frappe.io/framework/user/en/api/dialog ；Script Report 下钻 https://docs.frappe.io/framework/user/en/guides/reports-and-printing/how-to-make-script-reports.md ；
Cloudscape nested-table 告诫 https://cloudscape.design/patterns/resource-management/view/table-with-nested-resources/ ；
Dynamics sub-grid https://learn.microsoft.com/en-us/dynamics365/customerengagement/on-premises/customize/sub-grid-properties-legacy ；
SAP Fiori Tree Table https://help.sap.com/docs/ABAP_PLATFORM_NEW/468a97775123488ab3345a0c48cadd8f/7cf7a31fd1ee490ab816ecd941bd2f1f.html 。
**备选（用户提到）**：自定义报表渲染 / `vilavi_pim` 的「产品物料库」= **标准 Frappe Desk Page**（`item-group-browser`，jQuery+模板串+whitelist 取数，见 `docs/reference/en-custom-apps-and-deploy.md`）—— 要做「独立链条屏/树」时可抄它的 Page 四件套。

## 8. 连接键修正（2026-10-13，务必）

**旧键 `(sales_order, production_item)` 有冲突**：同 SO 内同 `item_code` 最多 40 行（674 组），
生产实测会让 **1464 张工单重复挂、139 张漏挂**。
**新键 = ERPNext 原生行级外键 `Work Order.sales_order_item == Sales Order Item.name`**（悬空 0，一行→最多 5 张），
兜底 `production_plan_item→PP.sales_order_item` / `fg_sales_order_item`。
完整基数表 + 铁律见 [../docs/reference/en-chain-cardinality.md](../docs/reference/en-chain-cardinality.md)。
改动的三处：`key_test/so_chain.py`、`key_test__report__so_chain_overview__*`、`EN_API/item_shipment_status.py: wos_for_line`（+ `WO_FIELDS` 加 `sales_order_item`）。

## 9. Stage 1 v3：可点链接 + 工序卡明细 + 交期逾期（2026-10-13）

- **全加单据跳转链接**（`/app/<doctype-slug>/<name>`，新标签页）：主表 `物料→Item`、`生产计划→Production Plan`；
  弹窗 `工单→Work Order`、`工序卡→Job Card`、`菲号→Tracking Number`、`开料工单→Initial Work Order`、`交付物料→Item`。
- **工序卡明细**：弹窗每道工序下直接列出其 Job Card（名称可点 + 状态/数量）。
- **交期 + 逾期**：主表新增「交期」列，逾期标红「(超 N 天)」；弹窗同步。
- **阶段色块**（indicator-pill：灰/橙/蓝/绿）+ **合计行**（未发合计）。
- 服务端扩展：`Job Card` 明细（**注意 Job Card 无 `employee` 列**——员工在 `time_logs` 子表，列表查不到，会 500）、行 `delivery_date`/`overdue_days`、工单 `last_end`。
- 测试机已部署 + Playwright 验证：主表 10 个链接、弹窗 3+ 链接（Item/PP/WO）均正确。

## 10. 两处提交账（务必要遵守的双轨约定）

**每次阶段性结果，两处都要提交**（用户明确要求）：

| 处 | 内容 | 本次状态 |
|---|---|---|
| **EN app 仓库** `keyapi/key_test`（服务器 `~/frappe-bench/apps/key_test`） | `key_test/so_chain.py`、`key_test/public/js/sales_order.js`、`key_test/key_test/report/so_chain_overview/` | **已提交**：分支 `feature/so-chain-embed`，commit **`80de553`**，已 push 到 origin（测试机） |
| **本仓库 `fzh-data`** | 产物副本（本目录）+ 文档 + 记录 | 已提交（PR #291） |

> ⚠️ 之前 stage 完成时只在 fzh-data 提交，**服务器 app 仓库留着一堆未提交改动**（有丢失风险）——已补交。
> 以后：在 EN 上改完并验证 → **先在服务器 git 提交 + push** → 再把产物/记录提交进 fzh-data。
> 测试机先行；生产待确认后 `git pull` + `migrate` + `restart`。

## 11. Stage 1 v4：弹窗层级 = 工单 → 菲号 → 工序卡（2026-10-13）

**为什么改**：生产实测 **菲号 = 一批(组)皮壳/半成品实物流的身份证**（开料按组生成，`<皮壳WO>-NNN`），
**贯穿该工单全部工序（6–9 道）**；**每个菲号在每个工序恰 1 张 Job Card** → 唯一键 `(菲号, 工序)`。
原「工单→工序→工序卡」是**转置投影**，把一个菲号撕到多个工序节点、丢了菲号这层物证（车间扫的码、打印的标签、出库/耗料的键都是菲号）。
完整语义 + 基数见 [../docs/reference/en-tracking-number-semantics.md](../docs/reference/en-tracking-number-semantics.md)。

**服务端**：`so_chain.py` 返回 `work_orders[].tracking_numbers[].steps[]`（每 step = 一道工序的一张 Job Card）+ `unassigned[]`（无菲号的报工）。
**前端**：弹窗 = 工单头 → 每个菲号一个 `<details>`（菲号链接 / 数量 / 工序完成 N/M / 开料工单链接）→ 展开逐工序 Job Card 表（工序|序|工序卡链接|状态|数量|完工时间）。**状态/选择值一律过 `__()`**（否则显示英文 `In Process`/`Work in Progress`/`Pending`/`Completed`）。
**验证**（测试库 `SO-26-00023`）：2 个菲号 `WO-26-00028-001/002`，分别完成 4/5、1/5 道工序，开料 324，逐工序工序卡全中文正常。

**EN app 提交账**（keyapi/key_test）：`feature/so-chain-embed` 分支，commit `80de553`(v1–3) → `2568a55`(v4)，均已 push（测试机）。

## 12. Stage 1 v5：合并列 + 行内展开（2026-10-13）

**问题**：① 「工单」「菲号」两列点开是**同一个弹窗**（冗余）；② 只有弹窗→不直观；③ 菲号应默认展开。
**调研结论**（见 [../docs/research/presentation-forms.md] 与本轮 Web 调研）：**不做 hover**（触屏失效；WCAG 1.4.13 三重约束；Frappe **v15 无官方 HoverCard**，新 Tooltip 只允许纯文本）；**不用树表**（Salesforce/SAP：父子字段异构别用 tree grid）。**正解 = 摘要 + 行内展开 + 弹窗深钻**。

**实现**：
- 主表列合并为 **「链条」**：`N 张 · M 菲号  工序 d/t ▸`；点它 **就地展开**（`<tr class="so-chain-inline">` accordion），不弹窗。
- 弹窗保留（「弹窗」列）做深度查看；**菲号在两处都用 `<details open>` 默认展开**。
- 每工单补 `ops_done/ops_total`（摘要的 d/t）。
- **验证**（测试库 SO-26-00023）：点「链条」→ 行内出现 WO→2 菲号(默认展开)→逐工序工序卡，全中文。

**EN app 提交账**：`feature/so-chain-embed` → `2568a55`(v4) → 本次 v5。

## 13. 生产发布记录（2026-10-13）

按惯例走链路：**测试机改 → 合并 main → push → 生产 pull → migrate → restart → clear-cache**。

| 步骤 | 结果 |
|---|---|
| 测试机 `feature/so-chain-embed` → `main` | **快进合并**（origin/main 无他人提交），push：`ab3cdc0..2c11464` |
| 生产 `keyapi/key_test` `git pull` | main → `2c11464`，`so_chain.py` + `report/so_chain_overview/` 到位 |
| 生产 `bench --site erpnext.vilavi.cn migrate` | Report 记录 **SO Chain Overview**（Script Report / is_standard=Yes）已建 |
| 生产 `bench restart` + `clear-cache` | 完成（新增 .py 必须 restart） |
| **验证** | 方法 `key_test.so_chain.get_so_chain` HTTP 200（SO-25-00169 → 82 行）；报表 12 列 / **4520 行**；浏览器实测皮壳工单显示 `计划 PP-25-00057` |

**两处提交**：EN app `keyapi/key_test`（合并到 main = `2c11464`）；本仓库 fzh-data 产物/记录。

## 14. 事故与教训：生产表单空白（2026-10-14）

**现象**：生产打开任何销售订单 → **整个表单空白**（sales_order.js 抛 `SyntaxError: Identifier 'SO_CHAIN_COLS' has already been declared`）。

**三个叠加原因**：
1. v31 我新增 `const SO_CHAIN_COLS = SO_CHAIN_DEF_COLS.length;`，但**忘了删文件里原有的 `const SO_CHAIN_COLS = 9;`** → 重复声明 → 整块脚本挂 → 表单渲染失败。
2. **部署基线被污染**：部署脚本用 `cp <最新?…>` 的 `/tmp/sales_order.js.bak_*` 做「干净基线」再追加；结果文件里**累计了两份**我的代码块（旧的 `=9` 一份 + 新的），重复声明来自这里。
3. **生产的 `git pull` 静默失败**：此前回滚用的 `git checkout <旧commit> -- <file>` 把旧文件**放进了索引** → 之后 `git pull` 被脏改动挡住、**未真正更新**（HEAD 仍是旧的 `84104cc`），于是「修了但没生效」。

**处置**：生产 JS 回滚到 v30(`b29d801`) 恢复 → 测试机修好并**完整验证**（无报错/列正确/拖拽+缓存）→ 合并 main(`7947a1d`) → 生产 `git fetch && git reset --hard origin/main` 强制对齐 → clear-cache → 验证通过。

**后续（v33 列宽）**：`5a3c9ef` 再发布 —— 「订单行物料」弹性列 + 数字列锁 54px。生产 SO-25-00169 实测 `wrapW=tblW=scrollW=1003` 一屏放下、0 控制台报错、82 行渲染正常；服务端 `grep -c 'const SO_CHAIN_COLS'` = **1**（无重复声明）。

**必须遵守的教训**：
- **改 JS 后必须确认文件里声明唯一**：`grep -c '^const ' <file>`、以及每个关键标识符只声明一次。
- **部署前先 `git status` 干净 + 用真·原始基线**（`/tmp/sales_order.js.bak_20261013_112137`，190 行、不含 `SO_CHAIN_DEF_COLS`）；或直接用整份文件部署，别「基线+追加」累计。
- **部署后必须验证服务端真值**：`getdoctype?doctype=Sales Order` 的 `__js` 是否含新代码、且无重复声明；再看浏览器 **console 无 error**。
- **先在测试机验证无误，再动生产**（用户明确要求）。


## 2026-10-26 复审后的库存证据字段

Supply Timeline 的 qty_status 仅描述 qty；原始数量状态在 evidence_qty_status，未上报与仓库范围未知使用各自 source_layer。当前仍只读取库存证据，所有 B 资格为 false；无实时通途 API 调用，也不接入本仓库纯函数供给汇总。app 与扁平副本同时提交，测试站以已提交版本核对；生产不发布。本轮完整修复和测试记录见 JACK_QA 的 P0-REVIEW-FIX-2026-10-26。


## 2026-10-27 测试部署已完成

用户已授权同步测试系统：key_test 测试分支 Git HEAD 为 c34fa53，两个报表功能 .py 与提交一致、工作区干净。测试机已通过定向 sudo 权限执行完整路径 `/usr/local/bin/bench restart` 和 clear-cache。服务器标准库 unittest 的 41 项测试通过，真实 REST 验证 evidence_qty_status、qty_status 与缺失来源均已生效；报表页面 HTTP 200。生产未更新，PR 保持 draft。备份与回滚凭据路径、聚合验收记录见 JACK_QA 的 P0-TEST-DEPLOY-2026-10-27。
