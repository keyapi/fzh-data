---
okf: v0.1
type: Reference
title: EN 销售订单「已关闭未发货」死单与工单进度不可信 — 子表反查父单的 API 铁律
date: 2026-09-14
last_updated: 2026-09-14
category: workflow-issues
module: en_api
problem_type: workflow_issue
component: erpnext-api-query
severity: high
applies_when:
  - "客户物料号 / EN 物料号 → 查该物料所有生产销售订单的发货与未发状态"
  - "排查 ERPNext 里 Closed/Cancelled 却仍有未发数量的死单"
  - "判断某张在产工单的真实进度（Work Order.status 显示 Not Started 但实际已开工）"
  - "需要按子表字段（客户物料号）反查父单，但子表 403 / 父单 417"
tags: [erpnext, sales-order, delivery-note, work-order, production-plan, job-card,
       child-table-filter, api-403, api-417, 死单, 未开工, 工单状态未回写]
related_components: [dn_trace_report, erpnext-wo-audit, missing_products]
---

# EN 销售订单「已关闭未发货」死单与工单进度不可信

## Context

排查美中公司（DANEEY）客户物料号 `CENKZ1325-Yellow-138` 的销售订单发货情况：
这个码在 EN 生产系统里对应 **10 张销售订单**，用户想知道哪些已发货、哪些没发。
用户还提示要结合**销售出库单**、**生产计划**、**生产工单**，以及「下单日期 + 3 个月」的
交付约定（计划同事口径）。

排查过程中发现两件事推翻了「看状态字段就够」的直觉：

1. **ERPNext 的 `Closed` ≠ 已发完** —— 10 张 SO 里有 **3 张** `Closed` 却仍有未发量。
   只按 `status` 过滤的看板会把它们当成已完成。
2. **`Work Order.status` / `produced_qty` 不可信** —— `WO-26-02609` 头部写
   `Not Started`、`produced_qty = 0`，但工序卡显示 **44 件（2 批 × 22）**。
   截至 2026-09-14 的 fixture 下界是 `裁剪 / 皮壳整件 / 锁扣眼 / 拷边`；当天 `翻面`
   从 Pending 变为 Completed，所以「4 道 / 5 道」是同一工单的两个时刻，不是口径矛盾。

## Guidance

### 1. 子表不能直接查，必须用「子表过滤父单」的四元组形式

三条硬约束（实测）：

| 约束 | 现象 |
|------|------|
| 子表不能直接 list | `GET /api/resource/Sales Order Item` → **403 PermissionError** |
| 父单直查子字段 | `[["customer_item_code","like","%码%"]]` on `Sales Order` → **417** `Field not permitted in query` |
| 正解 | `[["Sales Order Item","customer_item_code","like","%码%"]]` → **200**，frappe 展开成子查询 |

**但这个正解有个陷阱：结果"一行一匹配子行"** —— 同一张 SO 有多少行命中就出现多少次。
必须**先按父单 `name` 去重，再** `get_single` 扇出，否则同一张单会被拉 N 次。

### 2. `fields` 只能是父单字段

传未知字段直接 417（实测 `Item.has_bom` 被拒）。子表值必须 `get_single` 后读
`doc["items"]` / `doc["po_items"]` / `doc["operations"]`。

### 3. `in` 列表不能太长 —— nginx 有 4094 字节的请求行上限

把 308 个 `work_order` 塞进 `Job Card` 过滤 → `400 Request Line is too large (6737 > 4094)`。
所有 `in` 查询必须分块（实测每块 ≤ 40 安全）。`dn_trace_report.py` 早就记录过同一问题
（那里是「不按 work_order 过滤，全量拉取后 Python 侧过滤」）。

### 4. 分页要强制稳定排序 + 按实收行数前移

ERPNext 无 `order_by` 时会用默认排序（`modified desc` 类），**MariaDB 不保证跨 `LIMIT/OFFSET`
请求的全序稳定** —— 多页查询可能漏行或重复。所以：`order_by="name asc"`（name 唯一），
且按 `start += len(data)` 而不是 `page * page_size`（服务端返回不足一页时会跳行）。

### 5. DN 与 SO 行的匹配口径

**出库单必须按 `item_code` 匹配，不能用 `customer_item_code`** —— 实测 SO-25-00067 的出库行
`customer_item_code = NULL`（老单据没带出来），只按客户码匹配会漏 20 件。
更精确的逐行连接键是 `Delivery Note Item.so_detail` == `Sales Order Item.name`。

### 6. SO 行 → 生产计划行的连接键

`Sales Order Item.name` == `Production Plan Item.sales_order_item`。
**不要用 `Production Plan Item.work_order`** —— 这些行的该字段实测为空。

### 7. 工序卡才是真实进度，完成件数不能各工序求和

- 报「**工单状态未回写**」：`WO.status ∈ {Not Started, Draft, Pending}` 但**已有已完成工序卡**。
- 报「**工单未开工**」：**0 张工序卡** + 工序全 Pending（如 `WO-26-03264`）。
- **完成件数取第一道工序（裁剪/开料）的 `total_completed_qty`**（空则退回 `for_quantity`）。
  每道工序都有自己的工序卡，求和会把同一批件数按工序数重复累加 —— `WO-26-02609`
  会算成 4×44=176，实际就是 **44**（2 批 × 22）。超产跟这个数比 `WO.qty`，不要用会停在 0
  的头部 `produced_qty`。
- 工单按 `(sales_order, production_item)` 挂到订单行；`docstatus>=2` / `Cancelled` 不计入进度。
- **订单行 `item_code` 必须精确匹配**。`KS0001-…` 是 `PK#KS0001-…` 的子串，子串匹配会把
  皮壳/内胆行算进成品查询。

### 8. `amended_from` 用来区分「改单作废」和「死单」

`docstatus == 2` 且存在 `amended_from == 本单` 的后继单 → 判为「已改单，不计入未发」；
没有后继单的才是「单纯取消」。不区分的话总数对不上（本例 `SO-26-00053` 被 `SO-26-00053-1`
取代，20 件必须排除）。

### 9. 客户码注册在成品 `KS` 上，订单行卖的是 `PK#` 皮壳

实测 `CENKZ1325-Yellow-138` 注册在 **`KS0001-DM-140-YELLOW`**（成品，item_group 三角靠枕），
而订单行卖的是 **`PK#KS0001-DM-140-YELLOW`**（皮壳）。所以「订单行物料自身
`customer_items` 为空」是**常态不是数据缺失**。反查客户码归属要走
`[["Item Customer Detail","ref_code","like","%码%"]]`（实测 200 可用）。

## Why This Matters

本次实测数字（`CENKZ1325-Yellow-138` / `PK#KS0001-DM-140-YELLOW`，客户 美中公司 DANEEY）：

- 10 张 SO / 330 件 = 有效 310 + 已改单(作废) 20
- 已发 **126** / 未发 **184**
  - **死单(Closed未发) 64** — SO-26-00099 40 + SO-26-00003 20 + SO-25-00198 4
  - 在产/待发 **120** — SO-26-00101 40 + SO-26-00110 80

具体异常：

| 异常 | 事实 | 含义 |
|------|------|------|
| 死单 | `SO-26-00099` Closed、40 件未发、交货日 2026-08-30、**无工单无生产计划** | 行政关闭，剩余量不是已发完；疑似重复，建议确认后改 Cancelled |
| 死单 | `SO-26-00003` Closed、20 件未发、交货日 2026-01-09 | 已挂 8 个月，无任何生产动作 |
| 尾数 | `SO-25-00198` Closed、4 件未发（30 发 26） | 缺尾数 |
| 疑似重复 | `SO-26-00099`(下单 08-13) 与 `SO-26-00101`(下单 08-17) 同物料同量 40、交货日同为 08-30、金额完全一致 | 后者多出配套内胆 `ND#` 行；**只有后者有 `PP-26-00033` + `WO-26-02609`**，前者没有任何计划引用 → 实际生效的是 -00101，-00099 疑似作废但状态是 `Closed` 而非 `Cancelled` |
| 工单状态未回写 | `WO-26-02609` 头 `Not Started`/`produced=0`，实际 44 件已过 5 道工序（皮壳整件 2026-09-14 11:56 完工），剩 `检查皮壳扭筋 / 翻面 / 质检` | 8/30 交货的这 40 件**皮壳部分已过半**，不能报"未开工" |
| 工单未开工 | `WO-26-03264`（SO-26-00110，交货 2026-09-25）**0 张工序卡**，9 道工序全 Pending，计划 09-08 开工 | 80 件确实一件没动 |

**交付预估（下单 + 3 个月，业务口径非系统字段）**：`SO-26-00101` 08-17 → **2026-11-17**；
`SO-26-00110` 09-02 → 2026-12-02；`SO-26-00099` 08-13 → 2026-11-13（但无计划，不会发）；
`SO-26-00003` 01-09 → 2026-04-09（逾期 5 个月）。

**另一个反直觉点**：`SO-26-00053-1` 已于 2026-06-04 出库，距今 3 个月余 —— 按业务经验
美中早已到货售完，属收尾单。**「出库了」和「客户收到了」之间还有一个月级的时间差**，
判断"是否还有在途风险"时要把这一段算进去。

## When to Apply

- 客户/运营问「这个客户物料号还有哪些没发」时，跑
  `uv run python EN_API/item_shipment_status.py --customer-code <码>`。
- 做 EN 销售订单看板/报表时：**不要只用 `status` 过滤**
  （`Closed`、`Cancelled`、`Not Started` 三个字段本次都骗过人）。
- 判断某个 SKU 的在途风险时，看**工序卡进度**而不是 `WO.status`。
- 需要按任何子表字段反查父单时，直接套用本节的四元组过滤形式。

## Examples

```bash
uv run python EN_API/item_shipment_status.py --customer-code CENKZ1325-Yellow-138
uv run python EN_API/item_shipment_status.py --item "PK#KS0001-DM-140-YELLOW" --no-excel
uv run python EN_API/item_shipment_status.py --customer-code CENKZ1325-Yellow-138 --assert-fixture
```

控制台摘要（节选）：

```
── 订单发货状态 (10 行 / 10 张 SO) ──
SO             状态                 交货日期    订单量 已发 未发 出库单       工单          工序进度
SO-25-00198    Closed               2025-11-18      30   26    4 DN-26-00003  WO-25-07642   WO-25-07642 3/3工序完(30件)
SO-26-00003    Closed               2026-01-09      20    0   20 -            -             -
SO-26-00099    Closed               2026-08-30      40    0   40 -            -             -
SO-26-00101    To Deliver and Bill  2026-08-30      40    0   40 -            WO-26-02609   WO-26-02609 5/9工序完(44件)
SO-26-00110    To Deliver and Bill  2026-09-25      80    0   80 -            WO-26-03264   WO-26-03264 未开工(0工序卡)

订单量 330 = 有效 310 + 已改单(作废) 20
已发 126 / 未发 184
  ├ 死单(Closed未发)  64   SO-25-00198 4 + SO-26-00003 20 + SO-26-00099 40
  ├ 在产/待发        120   SO-26-00101 40 + SO-26-00110 80
DN 实算未发 184 vs ERP delivered_qty 口径 184  ✓

── 异常 ──
[死单] SO-26-00099 Closed 但未发 40 (交货日 2026-08-30, -)
[工单状态未回写] WO-26-02609 头部 Not Started/produced=0, 但 44 件已完成 拷边/皮壳整件/翻面/裁剪/锁扣眼
[工单未开工] WO-26-03264 0 张工序卡, 工序全 Pending (交货日 2026-09-25)
[疑似重复] SO-26-00099 与 SO-26-00101 同物料同量 40, 交货日差 0 天
```

## Related

- `EN_API/AGENT_HANDOFF_物料发货状态.md`（脚本的完整查询链与口径）
- `EN_API/item_shipment_status.py`（本次建成的脚本，单物料颗粒度）
- `EN_API/dn_trace_report.py`（姊妹脚本：DN→SO→WO→SE 物料移动追溯；nginx 请求行上限问题同源）
- `.agents/skills/erpnext-wo-audit/SKILL.md`（工单"一键完工"稽查；本节第 7 条与之互补）
- `docs/solutions/conventions/erpnext-product-cover-variant-pairing.md`（`KS` 成品 ↔ `PK#` 皮壳 1:1 配对规则）
- `docs/solutions/conventions/tongtu-en-sellfox-instock-sku-mainline.md`（客户码注册在 `KS` 上、`PK#` 不能替代）
