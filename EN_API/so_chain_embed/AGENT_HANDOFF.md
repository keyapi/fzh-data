# SO 表单「供应链链条摘要」内嵌 — Agent Handoff

> **目标**：在 ERPNext 销售订单表单里直接看到该单的链条摘要（阶段/已发/未发/工序进度），
> 零跳转。这是「呈现形式建议路线」的第 1 档（见
> `docs/solutions/architecture-patterns/supply-chain-visibility-forms-research.md` §5）。

## 1. 做了什么（Stage 1：嵌入单据）

**载体 = `key_test` app**（house app；EN 自定义 app 是各自独立仓库 `keyapi/*`，见
`EN_API/docs/research/en-supply-chain-map.md` §1）。

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
**反营销红线**（`supply-chain-visibility-forms-research.md` §1.2）：只做漂亮看板会「看板淹没」；
必须带阈值化 + 责任人路由。**度量**用例外解决时长/阶段停留，不是看板数量。
阶段 4–8（头程）数据仍外置（钉钉表/智美通），**本屏先只覆盖阶段 0–3**。

## 6. 关联

- `EN_API/docs/research/en-supply-chain-map.md` — EN 全链路实体地图（**已更正**：Cutting Plan/Task、Work Order Split、Wip Transfer 生产 0 条；真实车辆是 Initial Work Order / Tracking Number / Job Card 自定义字段）
- `docs/solutions/architecture-patterns/supply-chain-visibility-forms-research.md` — 四类形式调研 + 建议路线
- `EN_API/so_item_special_mark/README.md` — SO 表单定制的既有先例（Client Script→app 文件、hooks doctype_js、部署缓存要点）
