# EN 通途订单/包裹同步 —— 覆盖体检结论与待查项（交接）

> 日期：2026-10-09 · 来源：主线「旧 Colab 成本链 Phase B」只读排查 → 转交「排查修复 EN 通途订单/包裹同步漏数据」任务
> 目的：让接手方不必重跑，直接从这里继续。**结论分「已实测 / 待查」**，未标注者为已实测。

## 一、已实测结论（EN 侧，只读）

### 1. 订单号覆盖 = 100%，**不能用时间口径判漏单**
| 月 | 通途月表唯一订单号 | EN `Tongtool Order` 缺 |
|---|---|---|
| 202606 | 7644 | **0** |
| 202607 | 9406 | **0** |

方法：不带时间窗，按 `order_id_code in [...]` 分块（每块 40）问 EN 是否存在（结果缓存在运行机 `/tmp/enexists_202606.json` / `_202607.json`）。

> ⚠ **第一版按 `sale_time` 落在当月比对，得出"缺 412/320"，抽样 15/15 全是假漏**：EN `sale_time` 是**下单时间**，通途那张月表是**账期（发货）**口径。例：`BBdaneeyUS-BBY03-807178158842-A` 在 7 月表里、EN `sale_time=2026-05-11`。
> ⇒ **要判"某月漏没漏"，必须用发货口径（如 `despatch_complete_time`），不要用 `sale_time`。**

### 2. 通途月表里**没有"原始单"，只有 `_N` 拆单**；裸单只在 EN
- 含 `_N` 的订单号：202606 = 497 个（基号 215）、202607 = 483 个（217）
- 这些**基号（裸单）在通途月表里 100% 不存在**；EN 里都有
⇒ "一个原始单装了哪些件"**只能从 EN 拿**（这也是成本链要"以 EN 为准"的理由）。

### 3. 内容完整度（每月随机抽 25 单）
- 202606：**25/25 完整**（`order_items` 非空、`erp_item_code`/`shipping_method` 有值、`quantity>0`、`sx_shipping_cost` 非全 0）
- 202607：**24/25 完整**；1 单全空

### 4. "空壳单"成因 = **EN `warehouse_name` 为 null**（实例已定位）
`WOM-1436`（Shopify 独立站，`platform_code=shopify_api`，显示账号 `sale_account=WOWMAXDUUS` ↔ 通途 `accountCode=WOM`）：

| 侧 | 关键字段 |
|---|---|
| 通途（`erp2_orders_ordersquery`，accountCode=WOM） | **`warehouseName = 美东-CENTRADE`**、`warehouseIdKey=6464013595201610250000002538`、`orderStatus=despatched`、`despatchCompleteTime=2026-07-28`、有 `packageInfoList` |
| EN（`/api/resource/Tongtool Order/WOM-1436`） | **`warehouse_name = null`**、`order_status=已发货`、`match_status=完全匹配`、`last_sync_time=2026-09-24` ⇒ 子表 `shipping_method=''`、成本全 0 |

⇒ **EN 没把通途的 `warehouseName` 落库** ⇒ 没有仓库 → 没有成本来源编码 → 交付形态与成本全空。
**待查**：`warehouse_name is null` 的占比与分布（按平台/仓库/时间）；根因是"平台特例（如 `shopify_api`）"、"仓库映射缺失"，还是"同步时该字段为空"。

## 二、尾程 / 包裹（`Tongtool Package`）—— 用户补充的背景，**待查**

- 通途里**一个订单前后可能出现多个包裹（含之前作废的）**；大多数是"1 单 1 包裹"或"1 单多包裹"，**少数是"1 包裹多订单"**。
- **尾程运费由同事 WXP 手动导入通途**。另有对话记录：下载「通途订单详情统计 202607」查尾程缺失，**前天导入了一批 7 月尾程、昨天 WXP 导入了一批 8 月尾程费用**。
- **通途第二天导出才能看出结果**；EN 是否随之更新**未知**。
⇒ 待查：① EN `Tongtool Package` 对通途包裹的覆盖率（按 `despatchTimeFrom/To` 或 `updateTimeFrom/To` 窗口）；② **"后导入的尾程"是否更新到 EN**（对比同一包裹在通途与 EN 的尾程金额/时间）；③ 多包裹 / 包裹作废 / 1 包裹多订单 这几类在 EN 里的表达。

## 三、查询入口与实测坑

| 用途 | 调用 |
|---|---|
| 通途订单 | MCP `erp2_orders_ordersquery`；**必填 `accountCode`**（短业务码，如 `WOM`，不是显示名）；`orderId` 可传完整号；`saleDateFrom/To` **必须 `yyyy-MM-dd HH:mm:ss`**，否则返回 `code=525 格式错误` |
| 通途包裹 | MCP `erp2_packages_packagesquery`；用 `assignTimeFrom/To` 或 `despatchTimeFrom/To`（`updateTime*` 支持未证实） |
| 通途 MCP | `https://mcp.tongtool.com/mcp`；凭证在**父仓库** `tongtool_api/.env`（`TONGTOOL_ERP2_PRIMARY_KEY/SECRET`）；客户端骨架 `tongtool_api/mcp_http.py`（`McpClient(key, secret).call(name, args)`）；**商户合计限流 5 次/分钟** |
| EN | `https://erpnext.vilavi.cn`；凭证父仓库 `EN_API/.env`（`ERP_API_KEY/SECRET`，头 `Authorization: token k:s`）；**DocType 名带空格要 `%20`**；**`fields=` 里放不存在的字段名会 HTTP 417** |

## 五、仓库改名（2026-08-19）疑似相关 —— 需评估受影响订单量与是否重算

用户补充：**8 月通途给自发货仓库加了前缀**（`CENTRADE` → `美东-CENTRADE`，美中/波兰同理），**EN `Tongtu Shipping Warehouse` 当时没及时登记、后来才补上，但晚了一段时间（2026-08-19）**。

- 这**很可能就是"空壳单"（`warehouse_name` 为 null）的一个来源**：同步时 EN 侧尚无该仓库记录（或名字对不上）⇒ 仓库解析不出来 ⇒ 交付形态/成本全空。
- 相关既有记录：`docs/solutions/workflow-issues/tongtu-warehouse-rename-reconciliation.md`（同一次改名的三处对账与登记过程：通途 → 生产 ERPNext `Tongtu Shipping Warehouse` → 财务共享表「订单发货仓库对应成本来源」）。
- ⚠ **但要小心别把成因单一化**：实测 `WOM-1436` 的 `last_sync_time = 2026-09-24`（**在 8-19 补登记之后**）却仍是 `warehouse_name=null` ⇒ 除改名外**可能还有**别的成因（平台特例 `shopify_api`？导入器未落 `warehouseName`？）。

**待查（本任务应覆盖）**
1. **受影响订单量**：`warehouse_name is null` 的订单按 `creation`/`last_sync_time` 与 `platform_code` 的分布 —— 是否集中在 8 月中下旬、是否集中在某些平台。
2. **是否需要重算**：EN 侧应有"重算订单成本"的按钮/函数（用户口述存在）。**重算属写生产数据** ⇒ 先出受影响范围 + 让用户确认，再动；不要全量盲重算。
3. 对照 `Tongtu Shipping Warehouse` 的记录创建/修改时间，确认"改名时间线"与"空壳单时间分布"是否吻合。

## 六、建议接手顺序
1. **Package 覆盖 + 尾程是否更新到 EN**（尾程直接影响利润）。
2. **空壳单普查**：`warehouse_name` 为 null 的比例/分布（全量需逐单取；子表 `Tongtool Order Item` 不能直查）。
3. **`warehouse_name` 为 null 的根因**（平台特例？仓库映射缺失？同步时字段为空？）→ 再谈修法（按 EN 自定义 app 标准发布链路）。

> 约束：任何**写生产数据**的动作（补单/补包裹/改字段）**先与用户确认范围**；不要把真实订单/买家信息写进 git（本文件已刻意不含 PII）。
