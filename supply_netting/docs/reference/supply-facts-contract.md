---
okf: v0.1
type: Reference
title: 供应事实三类结构与可售 tranche
description: stage_balances / milestones / availability_schedule 的最小可运行结构、校验与与净额的衔接
tags: [supply-chain, stage-balances, availability-schedule, milestones, tranche]
date: 2026-10-27
status: implemented
---

# 供应事实三类结构（契约 v1 的 A/B/C）

入口：`supply_netting.facts`。对应供应决策契约
[`supply-decision-contract.md`](../../../supply_chain_visibility/docs/reference/supply-decision-contract.md)（88947665）。

## A. stage_balances —— 订单执行数量归属

一条 `StageBalance` = 某个订单行在某阶段还剩多少，阶段**互斥**：

| 阶段 | 含义 | 能否成为未来供给 |
|---|---|---|
| `unreleased` | 未排产 | 否（还不是供给） |
| `in_production` | 在产 | 是 |
| `finished_waiting_shipment` | 合格完工待发 | 是 |
| `shipped_in_transit` | 运输中 | 是 |
| `arrived_waiting_receipt` | 到仓待验收/上架 | 是（到仓 ≠ 可售） |
| `completed_sellable_delivery` | 累计已完成可售交付 | **否**（终态，不能当新供应） |
| `cancelled` / `loss` / `unattributed` | 取消 / 损耗 / 无法归属 | 否（单列，可追溯） |

校验（`validate_stage_balances`）：

- 阶段必须在枚举内；同 `订单 × 物料 × 仓 × 单位 × 阶段` 不得重复；
- 数量非负有限；`qty=null` 必须 `qty_status=unknown`；
- `summarize_stage_balances` 按 **订单 × 物料 × 单位** 对账：阶段合计 vs 净订单量，
  差额 `delta` 单列并标 `balanced=false`，**不塞进任何阶段**；
- 累计完工/累计出库只是进度，不得另起一行再当供给。

## B. milestones —— 计划 / 当前预计 / 实际

`StageBalance` 携带 `planned_at`（原计划）、`expected_at`（当前预计）、`actual_at`（实际），
外加 `observed_at`（何时取得）与 `source`。`milestones_frame()` 只输出确实有时间的行。
三者分列，不用列名覆盖：没有实际就不填实际；当前预计改版不覆盖原计划。

## C. availability_schedule —— 分批可售计划

`build_availability_schedule(balances)` 把每条阶段余额变成 **1 条或多条** `Tranche`：

| 字段 | 说明 |
|---|---|
| `tranche_id` | 稳定 ID（余额 ID@阶段；拆分后带批号） |
| `qty` | 该批数量 |
| `available_at` | 可售时刻（不是到港/POD） |
| `date_confidence` | `confirmed` / `estimated` / `unknown` |
| `allocation_status` | `free` / `fba` / `unknown` |
| `scenario` | `base` / `conditional` |
| `included_in_opening` | 已含期初库存 → 不再补入 |
| `exclusion_reason` | 明确排除原因，空串表示计入 |

规则：

- `sellable_at` 优先；缺失退回 `actual_at`，再退回 `expected_at`；都没有就 `unknown`。
- 拆分必须精确等于原余额（`split_balance` 会抛错，不顺从凑数）。
- 排除原因：`not_released` / `already_delivered` / `order_cancelled` / `loss` /
  `unattributed` / `included_in_opening` / `fba_allocated` / `allocation_unproven` /
  `quantity_unproven`。
- 每条余额做数量账：`input_known = scheduled + excluded`，逐条断言。

## 与净额的衔接

```
StageBalance ──build_availability_schedule──▶ Tranche ──tranches_to_supply_rows──▶ SupplyRow
                                                                                    │
inventory_snapshot（期初） ─────────────────────────────────────────────────────────┴─▶ net_target → bucket_receipts
```

- tranche 转 `SupplyRow` 后仍要过 `apply_overlap_gates` 与 `bucket_receipts`，
  不绕过任何 gate。
- 未知日期的 tranche 转成 `date_confidence=unknown` 的 SupplyRow，最终是
  `date_unproven` 条件态——**不是 0**。
- `fba_allocated` / `already_delivered` / `included_in_opening` 在 tranche 阶段就被排除，
  不会进入分桶，也不会被重复分配。

## 真实数据现状

| 结构 | 本地可用来源 | 缺口 |
|---|---|---|
| stage_balances | 通途库存快照的 `intransit` → `shipped_in_transit` 172 条 | 未排产/在产/完工待发/到仓待上架没有本地源 |
| milestones | 结构就位 | 无逐行原计划/当前预计/实际日期 |
| availability_schedule | 由上述在途派生 172 条 tranche，全部 `conditional`（无 ETA） | 生产/出运批次的可售日需 Jack 的 supply facts 或 EN 工单/DN |

这不是「供应功能已验收」：只证明结构、校验与守恒可运行，覆盖仍 partial。
