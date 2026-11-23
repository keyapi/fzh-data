---
okf: v0.1
type: Report
title: 2026-10-29 广范围自发货补货决策包
description: 每个 SKU×仓×UOM 键单一去向、UOM 组内合计、两档库存服务情景、可追溯审核清单
tags: [decision-pack, replenishment, forecast, netting, review]
date: 2026-10-29
status: verified
---

# 2026-10-29 广范围补货决策包

供人工审核，**不是采购指令**，也不代表供应功能验收。
入口：`uv run python -m supply_netting.decision_pack`。

## 1. 输入与版本

| 输入 | 版本 / 位置 |
|---|---|
| 供应净额 | r5 `run-2026-10-26-r5`（最终代码 `2dcf0ba5`，冻结提交 `cafc4169`），仅条件情景 |
| 刷新预测 | `forecast-20261027-r2`（commit `6a7d56bd`，accept-with-findings） |
| 需求历史 | `canonical-r2/demand_netting.parquet`（数据截止 **2026-10-26**） |
| 库存快照 | `_inputs/en_stock-2026-10-26-backup.parquet`（as_of `2026-10-26T05:17:34+08:00`） |
| 本包代码 | `85b5302b`（`git_dirty=false`） |

## 2. 方法

### 键与去向（互斥，不静默丢弃）

输入键 = r5 净额键 ∪ 有库存但无预测需求的键 ∪ 预测键（未过资格/未进净额）。

| 去向 | 判定 | 数量口径 |
|---|---|---|
| **建议补货** | 模型化缺口 > 0 | `qty_high = ceil(缺口)`；`qty_low = ceil(max(0, 缺口 − 条件供应))` |
| **无需补货** | 期初覆盖已知需求 | 0；高服务档仅给缓冲补货量 |
| **不可算** | 无库存基准 / 期初未证 | `null`（不写 0） |
| **待核** | 有库存无预测覆盖 / 预测键未过资格 / 预测键未进净额 | `null` + 原因 |

覆盖对账：`输入键数 = 四类去向之和`，不符直接抛错（`_reconcile`）。

### UOM 与资格

- 一切数量都绑定 `SKU × 仓 × UOM`；**合计只在 UOM 组内做**，跨 UOM 不相加。
- 需求侧只用预测的窗口 p50 换算（UOM 已证）；净额资格沿用 r5 的
  `demand_netting.netting_allowed` 逐行过滤；**预测资格（`netting_eligible`）与
  净额资格是两套字段**，不互相替代。
- 供应侧只用 r5 条件情景：已证到货 = 0，条件供应（在途/PO 无 ETA）单列、不抵缺口。

### 两档库存服务情景

| 情景 | 定义 | 数量（建议补货键） |
|---|---|---:|
| `current_policy` | 覆盖模型化缺口 | **495** |
| `higher_service_flat95` | 缺口 + 历史 σ × √14 天参考缓冲 | **777** |
| 差额（额外占用） | 缓冲 | **282** |

`current_policy` 的模型化残差缺口 = 0，但**未覆盖需求波动**（未覆盖波动 282）；
高服务档把它补上。缓冲是参考量，**不是 95% 覆盖率承诺**，未含提前期。

## 3. 结果

| 指标 | 值 |
|---|---:|
| 输入键（SKU×仓×UOM） | **4,014** |
| 建议补货键 | **91** |
| 无需补货键 | 452 |
| 不可算键 | 2 |
| 待核键 | 3,469 |
| r5 保护期缺口（建议补货键） | **34.867936 / 71 键** |
| 模型化缺口合计（视界末，建议补货键） | **449.966544** |
| 建议量（current / higher） | 495 / 777 |
| UOM 拆分 | 个：3,997 键（91 建议）；套：17 键（0 建议） |

待核原因：预测键未过资格且无库存基准 1,473；预测键未过资格 1,174；
无预测覆盖（仅库存）818；无预测覆盖且无库存基准 4。
不可算 2 键：`no_snapshot_basis`（逐桶 opening/gap 均为 null）。

## 4. 审核清单字段（每行可追溯）

`canonical_sku / canonical_warehouse / canonical_uom`、`destination / destination_reason`、
`opening / opening_lower_bound`、`horizon_demand / protect_demand`、`gap_today / gap_date`、
`qty_low / qty_high / qty_current / qty_higher / extra_holding / buffer_reference`、
`conditional_supply`、`service_tier`、`status`、`to_verify`、`human_review`（留空待填）、
`forecast_run_id / forecast_window / netting_run_id / netting_as_of / basis_forecast /
basis_supply / data_cutoff`。

## 5. 产物

目录：`D:/Work/fzh-order-store/en-demand-v1/supply-netting/decision-pack-2026-10-29/`

| 文件 | 内容 |
|---|---|
| `decision_pack_2026-10-29.xlsx` | 6 个 sheet：决策清单(4,014) / 去向对账 / 情景对照 / UOM 分组 / 数据与限制 / Manifest |
| `decision_pack_2026-10-29.parquet` | 同上主表，30 列，机器可读 |
| `decision_pack_2026-10-29.json` | 逐行 JSON |
| `decision_pack_manifest.json` | 截止日、决策日、旧报告日期、使用范围、输入/输出哈希、覆盖对账、两档情景、7 条限制 |

## 6. 使用范围与限制

1. 数据截止 **2026-10-26**；决策日 **2026-10-29**；上一版报告日期 2026-10-27。
2. 历史订单全部早于 as_of，净额需求来自预测；as_of 到预测起点 2.779 天无需求数据。
3. 在途/PO 无逐行 ETA，r5 已证到货全桶为 0；条件供应不能直接抵缺口。
4. 未履约 SO 未接入。
5. 预测仅覆盖通过预测资格的 582 个销售键；未覆盖键不等于零需求（列为待核）。
6. 服务水平缓冲用历史 σ 与 14 天窗口，未含提前期，不是覆盖率承诺。
7. 无库存基准键保持 unknown；待核键需人工补证据。
8. `partial=true`（r5 六条原因随包保留）。本包**不得直接生成采购单**，
   也不构成供应功能验收。
