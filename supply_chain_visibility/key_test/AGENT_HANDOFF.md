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

- ✅ **测试机（`上海测试-阿里云-FZH-ERPNext-frappe`，站点 `erpnext.vilavi.cn`）已部署并验证（2026-10-13）**：
  - `so_chain.py` 语法 OK；`sales_order.js` 190→250 行；备份 `/tmp/sales_order.js.bak_*`。
  - `bench --site erpnext.vilavi.cn clear-cache`。
  - **方法验证**（REST）：`GET /api/method/key_test.so_chain.get_so_chain?sales_order=SO-24-00016`
    → HTTP 200，返回 6/2/1 行、stage/substate、工序进度、DN 净额均正确（抽样 SO-24-00002/00012/00016/00021）。
  - **JS 挂载验证**：`GET /api/method/frappe.desk.form.load.getdoctype?doctype=Sales Order`
    → `__js` 含 `so-chain-summary` 与 `so_chain.get_so_chain` ✅。
  - ⏳ **浏览器视觉未验证**（需登录 desk）；建议人工开一张 Sales Order 确认区块渲染。
- ⏳ **生产（`阿里云-FZH-ERPNext-frappe`）未部署**。

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
- ⏳ 生产未部署。

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
