---
okf: v0.1
type: Reference
title: 分公司补货与皮壳/内胆业务规则（原型已核实，待 #300/#301 验收）
date: 2026-10-21
category: conventions
module: demand_forecast
problem_type: convention
component: domain-rules
severity: high
applies_when:
  - "给分公司补货，判断发成品/皮壳/半成品"
  - "销售订单上传皮壳后，内胆该不该加、加哪一条"
  - "通途 -Cover 库存与不带后缀的通途 SKU 怎么合并"
  - "通途 intransit 与采购未入库是否重复"
tags: [demand-forecast, replenishment, bom, cover, inner, tongtool, erpnext]
related_components: [demand_forecast, warehouse_restock, sellfox_cover_inventory]
---

# 分公司补货与皮壳/内胆业务规则

状态：**原型阶段已用 EN/通途实测核实，尚未经 #300 实施主线 / #301 评审验收**。可用于解释和演示，**不得直接用于下单**。

## 1. 产品结构与发货形态

- **典型配置**：成品 `KS` = 皮壳 `PK#` + 内胆 `ND#` + 充棉（PP 棉/海绵）；但**不是所有商品的通式**——有些产品没有内胆。**实际配置按有效 BOM 与发货形态确定**。
- 半成品只有皮壳/内胆；`PK#`/`ND#` 是 EN 半成品，不是“组件”这个内部业务分类。
- 发什么由 EN **物料组** `custom_shipment_type_to_branch` 决定：`皮壳` / `半成品` / `成品`。
- 分公司（USNJ/CENTRADE、USTX/DANEEY、POLAND）收到后做填充/压缩/包装/发货；绍兴主要发皮壳。

## 2. 内胆：以 BOM 为准

- **BOM 有 `ND#` 就发，BOM 没有就是该产品没有内胆。**
- 销售订单 Excel 上传只生成 `PK#` 行；内胆由按钮 `为所有行增加配套物料`（Client Script + `key_test.item_utils.get_supporting_item`）添加。按钮按**物料组+尺寸**查找，不读 BOM，因此会误加。
- 实测 1,811 个含皮壳的成品 BOM：
  - BOM 与按钮一致 1,531（84.5%）；
  - **BOM 无内胆但按钮会加 82**：BOM 正确，产品没有内胆；按钮误加，执行层应拦截；
  - **BOM 有内胆但按钮找不到 62**：其中 61 个是 **BOM 仍挂已停用的内胆物料** → 标记为“**待清理核实**”，由业务确认该产品是否还需要内胆；**不能仅凭停用状态自动删 BOM**；1 个是尺寸属性取错。
- 清单与处置：`D:/Work/fzh-order-store/nd_button_gaps.csv`（`status` + `reason` + `action`），生成脚本 `scripts/nd_button_gap_report.py`。

## 3. 皮壳 `-Cover` 与不带后缀的通途 SKU

- 两者在通途是**两个独立 SKU 数量桶**：卖哪个只扣哪个，变动不镜像；cover 销量约占 4.4%。
- **当前原型按“两者相加”作为情景假设**，用于展示可能的可售总量；这**不是已批准规则**。
- **未验证**：两者物理上是否同一堆货（可能是同一批货按渠道拆账，也可能两堆）；成品与皮壳是否可替代；cover PO 能否当成品供给。需调拨单/盘点/运营确认。
- 赛狐的 `PK# -> KS x1` 组合代理是**销售层**共享扣减，不代表通途合并了两个 SKU。
- `-Cover` 还用于大件拆包裹、同一皮壳配不同填充物（PP 棉/海绵），与 EN `PK#` 未必一一对应；只做物料级合并，不强行映射到单个 EN 变体。

## 4. EN BOM 的拆分

- KS BOM 只有 `PK# + ND#`。
- PP 棉/海绵、压缩包装在另一套「绍兴包装成品」BOM：`SXBZCP#`（393 条，含 PP 棉/碎海绵 + 纸箱 + 真空袋 + 扣胚）、`PLBZCP#` / `USTXBZCP#`（各 262 条，主要是 PP 棉）。
- 这些 BOM **不含 KS 子件**，是附加的填充/包装 BOM。分公司补货按 KS BOM 拆分是对的；算成品/FBA 完整用料必须叠加包装 BOM。

## 5. 库存供给口径

- **EN Bin 不可作可用库存**：EN 不扣减通途，`Bin.actual_qty` 只是账面。
- 分公司库存用通途按仓快照；同一物料的多个通途 SKU 合并为物料×仓池。
- **intransit 与 PO 未入库不能直接相加**：实测 173 个 SKU×仓同时有两者，146 个相差 ≤1；`SUM(LEAST(intransit, PO)) = 13,118` 等于全部 intransit，说明两者很可能重叠。
- **但 `MAX(intransit, PO)` 只是临时假设，不是已验证的去重规则**：没有逐笔订单/包裹关联，不能证明包含关系；248 条未结 PO 的 `will_arrive_date` **全部为空**，无法判断到货时点。真正风险是把尚未发货、到货过晚的 PO 当作近期供给，从而低估近期补货缺口。应保留“在途 / 未发采购 / 重叠未知”三个状态，最终按订单关联 + 预计可售日期裁定。详见 `D:/Work/fzh-order-store/RECONCILIATION_2026-10-21.md`。
- 3PL（WayfairCG）库存 API 可查但只有 Cranbury 有量（92 SKU / 880 件），权威仍是 Wayfair 后台导出；按库存数量单独展示，不并入分公司 ROP。

## 6. 缺数与未知

- 缺表/缺数不能静默转 0：`input_health` 记录库存/PO/映射/预测/发货形态的行数与快照时间；`data_flags` 标 `po_missing` / `stock_missing` / `ship_type_missing` / `no_stock_row`；PO 或库存源缺失时建议量置 NULL。
- 原型结果统一带“未验收、不用于下单”标签。

## 7. 规则状态

| 规则 | 状态 |
|---|---|
| 内胆以 BOM 为准；BOM 无内胆=无内胆 | 已核实（代码+SO 数据） |
| 按钮按物料组+尺寸会误加内胆 | 已核实（82 个反例） |
| BOM 挂停用内胆 | 待清理核实（停用≠应删） |
| EN Bin 不可作可用库存 | 已核实（PR #300） |
| intransit 与 PO 大量重叠 | 已观测 |
| `MAX(intransit, PO)` 去重 | **假设，未验证** |
| cover 与不带后缀 SKU 相加为可售 | **情景假设，未验证** |
| 3PL 库存以通途为准 | 未采用（权威仍是 Wayfair 后台） |

## Related

- [销售历史分析库（DuckDB）——GS 月表 + EN 并集](../architecture-patterns/order-history-duckdb-store.md) — 数据来源、预测、补货 v3 与发货形态拆解
- [三角类皮壳在通途与赛狐并行期的共享库存代理](sellfox-cover-shared-inventory-transition.md) — 赛狐组合代理的边界
- [EN 物料/变体创建惯例](erpnext-item-variant-creation-convention.md) — 配套物料与 BOM
