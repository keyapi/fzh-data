---
okf: v0.1
type: Report
title: Phase 1C 三段式交付（需求预测 / 分时供给 / 三态判定）
date: 2026-10-22
owner: claude-worker
status: delivery only; no purchase instruction
inputs:
  - out/business_phase/ranking.json（d50310a6，只读）
  - out/business_phase/destinations.json（44def7f5，只读）
  - out/replenishment_v0/evidence.json / model_race.json（f9df4357，只读）
  - D:/Work/fzh-order-store/order_store.duckdb（read_only）
artifacts:
  - experiments/business_phase/build_plan.py
  - out/business_phase/plan.json
---

# Phase 1C：三段式交付

> 覆盖集合 = **Top50 ∪ 紧急履约例外** = 122 个 SKU（Top50 50 + 例外 75 − 重叠 3）。
> 本文件不出采购指令、不判补/不补之外的任何动作；数量只为“证据充分”行保留，本批为 0。

## 1. 需求口径

- 训练：Phase 1B 冻结的 6 个月净销量（2026-04..09，零填充）；点模型 `mean3`。
- 预测地平线：90 天（2026-10-22 → 2027-01-20），同形日历窗口。
- **沿用 V1 已确立口径**：rolling-origin 同形残差、`label_available_at` 过滤、conformal-style 分位；产物明写 `finite_sample_guarantee=false`，**不声称 90% 保证**。
- **断货/未履约不当零需求**：零填充月份若同时有断货或待发证据，标为需求缺口。
- **退货/取消不可观测**：`gs_orders` 无状态字段，窗口内 0 条负数量行 —— 口径边界，已写明。

## 2. 分时供给情景

| 桶 | 区间 | supply_lower | supply_upper | 说明 |
|---|---|---|---|---|
| A_0_40d | 2026-10-22..2026-11-30 | 240 (ok) | 1239 (unproven) | arrivals without ETA are excluded from t |
| B_41_71d | 2026-12-01..2026-12-31 | 0 (ok) | 0 (unproven) | no proven arrival in this bucket |
| C_72_91d | 2027-01-01..2027-01-20 | 0 (ok) | 0 (unproven) | no proven arrival in this bucket |
| D_beyond_91d | 2027-01-21..以后 | 0 (ok) | 0 (ok) | no proven arrival in this bucket |

（上表以供给最大的 `TT0031085K0063342` 为例；每行各自的数值见 `plan.json → rows[].supply.buckets`。）

- **下界只含已证窗口内在手**；`tongtool_po` 的 open 行 **0 条有 `will_arrive_date`**，故所有到货都不进下界，也**不能用来消除近期缺口**。
- **上界=记录之和**（在手 + 在途 + 未结 PO），且 `deduped=false`、UOM/未上账供给未证 —— 按 R4 规则，它**永远不能证明充足**。

## 3. 三态判定（本批结果）

| 状态 | 行数 |
|---|---:|
| no_replenish | 0 |
| replenish | 0 |
| pending | 122 |

- 有数量的行：**0**（规则要求只有证据充分行才给数量）。
- 因此本批全部为 `pending`，`quantity_baseline` / `quantity_stress` 均为 `null`（不是 0）。
- 原因不是脚本没跑通：需求上下界目前只有估计值（P50/P90），供给上界的去重与“无未上账替代供给”未证，UOM 也未全证 —— 与 R4 的判定标准一致。
- 供给下界已证行：84；供给上界已证行：0。

## 4. 缺证据（每行逐条，见 `rows[].missing_evidence`）

常见缺口与责任人：UOM（商品主数据/仓储）、BOM 件/个/套行（商品主数据/工程BOM）、PO/在途到货日（采购/供应链、数据系统）、逐笔重叠键（数据系统）、Cover 缺席证明（商品主数据/仓储）、业务需求上下界（业务/运营）。

## 5. 对账

| 项 | 值 |
|---|---|
| 覆盖集合 | 122（可复算：Top50 50 ∪ 例外 75，重叠 3） |
| 入 / 出 | 122 / 122，0 丢弃 |
| 有需求预测 | 84；无历史 38（母集外待发 SKU） |
| 母集内 / 母集外 | 84 / 38 |
| 两次运行 | 除 `generated_at` 外逐字节一致 |

## 6. 本阶段不做

- 不下采购/生产指令，不给补货数量，不判「补」与「不补」（本批无行达到门槛）。
- 不把 `B_max`/记录之和当作充足证据；不把晚到供应算进近期缺口。

