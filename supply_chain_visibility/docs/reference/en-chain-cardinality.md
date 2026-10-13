---
okf: v0.1
type: Reference
title: EN 供应链各环节基数（一对多/多对多）实测与连接键铁律
description: 用生产真实数据核实的基数表 + 「按 sales_order_item 挂工单」的修正结论（复合键会重复挂 1464 张/漏挂 139 张）
date: 2026-10-13
category: reference
module: supply_chain_visibility
tags: [erpnext, cardinality, sales-order-item, work-order, tracking-number, delivery-note,
       join-key, many-to-many]
---

# EN 供应链各环节基数（实测）

> 2026-10-13 用**生产** `erpnext.vilavi.cn` 只读 SQL 核实。规模：SO Item 9696 / WO 9372(ds1 8552) /
> Tracking Number 4887 / Stock Entry 29380 / DN Item 13625 / Initial Work Order 750 / PP Item 9697。

## 1. 基数表

| 关系 | 实测基数 | 备注 |
|---|---|---|
| SO ↔ SO Item | 1:N | — |
| **SO 内同 `item_code` 多行** | **674 组、2905/9696 行；单组最多 40 行** | 重复行 `custom_label_combination` 全 NULL，非变体 |
| SO Item ↔ Work Order（**`Work Order.sales_order_item`**） | **1:N（正确）** 一行→最多 5 张；**悬空 0** | ERPNext **原生**精确外键 |
| SO Item ↔ Work Order（复合键 `sales_order+production_item`） | **N:M（错）** 509 键重复、单键最多 20 张 | **1464 张会重复挂 + 漏挂 139/19** |
| WO 未关联 SO | ds1 中 `sales_order` 空 **2074**、`sales_order_item` 空 1989 | 备库/无 SO 生产，本不该挂 |
| WO ↔ Tracking Number(菲号) | 1:N 一 WO 最多 **56** 个 | `work_order` vs `finished_product_work_order` **1397 条不同，勿混用** |
| WO ↔ Stock Entry | 1:N 一 WO 最多 **166** 张 | `Manufacture` ds1 11581 |
| **DN Item ↔ SO Item** | 多:1 一行最多 117 条 DN 行 | `so_detail` **悬空 0**；**DN 不直接绑工单**，只绑 SO 行（+`stock_tracking_number`） |
| Initial Work Order ↔ WO | **N:M** 一开料单最多覆盖 9 张 WO；一 WO 被最多 9 条开料明细引用 | 真多对多 |
| `Woker Order Allocation.(work_order,tracking_number,job_card)` | 三元组有 32 组重复 | `tracking_number` 全局唯一；**三元组不能当主键** |
| PP Item ↔ SO Item | 多:1 一行最多 30 条 PP 行 | `sales_order_item` **悬空 0** |

## 2. 连接键铁律（修正前 vs 修正后）

**修正前（错的）**：`Work Order.production_item == SO Item.item_code 且 sales_order == 本 SO`。
→ 因「同 SO 内同 item_code 多行」而**重复挂 1464 张、漏挂 139 张（头字段为空）**。

**修正后（对的）**：
```
SO 行的工单 = Work Order.sales_order_item == Sales Order Item.name
兜底（sales_order_item 为空的老工单）：
  ① Work Order.production_plan_item → Production Plan Item.sales_order_item == 行 name
  ② Work Order.fg_sales_order_item == 行 name
无 SO 行绑定的工单（约 1989 张）单列「未绑定生产」，不要用 item_code 反推。
```

**连带修正**：出库绑 `DN Item.so_detail`（不是工单）；菲号走 `TN.work_order`（**不是** `finished_product_work_order`）。

## 3. 落地

- `supply_chain_visibility/key_test/key_test__so_chain.py`、`...__report__so_chain_overview__so_chain_overview.py`：工单归属改行级外键 + 兜底。
- `EN_API/item_shipment_status.py` 的 `wos_for_line`：**同样 bug，已改**（优先 `sales_order_item`，`WO_FIELDS` 加该字段，`enrich_so_rows` 传 `line_id`）；单测 `test_wos_for_line_prefers_line_level_foreign_key` 锁定。
- 实测验证（测试机 SO-24-00012 两条重复 `ND#` 行）：修正后各挂**自己**的那张工单（修复前会各挂 2 张）。

## 5. 成品(KS)行的工单结构 + 工序分母（2026-10-13 生产实测补）

**一条卖成品(KS)的 SO 行 → 最多 3 张工单，两把键挂接**：
```
SO Item (KS…)
├─ 成品(KS) WO :  Work Order.sales_order_item    = 行 name
├─ 皮壳(PK#) WO:  Work Order.fg_sales_order_item = 行 name   ← 不是 sales_order_item！
└─ 内胆(ND#) WO:  同上
```
实测：883 行只有 1 张成品 WO（未拆皮壳/内胆）、199 行 1+1+1、不少行 0 张（库存发货）。
**老数据的 `fg_sales_order_item` 多为空**（7761/8188 PK/ND 工单），近月才补齐。

**工序进度分母必须排除返工分支**：`Operation.is_corrective_operation = 1` 的只有两道
（**质检发现问题 / 通用返工**），正常批永不执行（完成数 0）。**不要**用 sequence_id 判（会误伤 翻面/质检）。
`X/Y` 的 Y = `is_corrective_operation = 0` 的工序数。

**「成品是否完工」判据**：主用 `Work Order.status='Completed'`（≈ produced_qty≥qty，实测 1212 张仅 1 张不一致）；
探测「忘点完工」看同行皮壳/内胆兄弟工单是否全 Completed。**菲号数量/入库单不能单独当完工信号**。

## 6. 「忘点完工」异常（2026-10-13 落地）

判据：**成品(KS)工单未完工，但同行（同 SO 行）的皮壳/内胆工单全部已完成** → 疑似忘记点完工。
- 实现：`so_chain.py` 返回每行 `forgot_complete[wo…]`（成品 WO status≠Completed 且 produced<qty，且所有 皮壳/内胆 `completed`）；
  前端在主表「链条」列与弹窗/行内展开的该工单头 **标黄「忘点完工?」**。
- 依据：成品 WO `status='Completed'` 可信（=produced≥qty，1212 张仅 1 张不一致）；成品 WO 本身无工序/无菲号，活都在皮壳/内胆上，
  故「兄弟全完成而自己没完工」是强信号。生产实测仅 `WO-26-01176`、`WO-26-01205` 命中。

## 7. 生产计划 ↔ 工单（2026-10-13 生产实测更正）

**`Work Order.production_plan_item` 100% 指向 `Production Plan Item`**（生产实测 PK# 3770/3770 全部在 `Production Plan Item`，`Production Plan Sub Assembly Item` 命中 0）。
即：**PP 里为 皮壳/内胆 也建了计划行**，工单挂到各自的计划行。

**挂接情况**（docstatus=1 生产实测）：成品 KS 1113/1118 有 `production_plan_item`；**皮壳 PK# 3770/4810（78%）**；内胆 ND# 2010/2598（77%）。→ **大多数皮壳/内胆工单是有计划的**。

⚠️ **查法陷阱**：解析「工单属于哪个 PP」**不能**只查 `Production Plan Item.sales_order_item = 本 SO 行` —— **皮壳/内胆的计划行通常不带 SO 行**，那样会得到空。
**正确**：`Work Order.production_plan_item`（计划行 name）→ `Production Plan Item.parent`（PP 名）。

（更正：先前据**测试库**稀疏样本误判「皮壳/内胆无计划」；测试库该字段多为空，生产库多已填。）
