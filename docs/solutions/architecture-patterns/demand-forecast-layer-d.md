---
okf: v0.1
type: Reference
title: D 需求预测层：状态分层、政策/数据/供给分离与 4 年历史
date: 2026-11-02
category: architecture-patterns
module: supply_chain
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "做 SKU×池×形态×单位的销量预测与净需求"
  - "D1 资格表出现大量 'market_unproven/no_forecast_row' 被误当阻碍"
  - "需要把 4 年订单、CG、套件、拆包、共享池接进预测"
tags: [demand-forecast, d-layer, status, censored-demand, cold-start, cg]
---

# D 需求预测层

## Context

D 不是「等 B/C 给齐了才算」的最后一层。D 的职责是：

- 对每个 `product × destination_pool × market × physical_form × canonical_uom × horizon` 估计需求分布；
- 识别删失/断货/清仓/新品/老产品；
- 自己产出预测或 fallback，不把「没有现成 forecast row」当外部阻碍。

A/B/C 已经拍板的政策（ND、HM、老产品、共享池、CG 渠道）不应在 D 里重新讨论；D 只标注 `policy_excluded`，继续算其他行。

## Guidance

### 1. 四个状态，不要一个 reason_code 混所有问题

| 字段 | 值 | 含义 |
|---|---|---|
| `decision_state` | `active / policy_excluded / data_gap` | 是否进入 D 决策候选 |
| `demand_state` | `observed / censored / estimated / no_demand` | 销量事实/删失/潜在需求/确无需求 |
| `forecast_state` | `observed_model / fallback_model / cold_start / not_estimable` | D 自己的预测方法 |
| `netting_state` | `eligible / policy_excluded / data_gap / supply_gap / observation` | 能否下游净额消费 |

- `policy_excluded`：ND、HM、老产品、共享池政策、TJ# 终端规则；不是数据坏，也不是待办。
- `data_gap`：真缺证据（无市场、无映射、form/UOM/owner 不可证、日期不闭合）。
- `supply_gap`：C 没有 `join_full` 供给，或 CG 只作 Wayfair 缓冲；需求仍可预测。
- `forecast_fallback`：没有现成 D forecast row → 用基线/池化/冷启动，不是「不能预测」。

### 2. 统一历史

- `orders_unified.parquet`：2022-12-20..2026-10-31，414,189 行；2026-10 通途 6,292 行已并入；FBA 10 月单独汇总。
- 历史归一是 D3b 的前置：大小写、`OLD_`、`-new/-Cover/-c/-1/-2`、客户物料号、别名、TJ# Product Bundle；只有证据一致且候选唯一才合并，共享/多候选/跨 form/UOM 仍隔离。
- 归一时保留 `history_bridge_refs`、`effective_from/to`；不能用一个名字相似就合并。

### 3. CG 不是第三个市场

- CG 只服务 Wayfair，但由固定分公司补货；**CG 销量计入该分公司需求，`channel=wayfair`**，不是 `demand_ineligible`。
- CG 库存是下游缓冲：只用 `warehouse_id='CG'` 汇总行，与 USNJ/USTX 物理库存分开列，不重复相加。
- `cg_wayfair_only` 是 `supply_channel_constraint`，不是需求排除。

### 4. 断货不是「标一下」

- 销量 = min(需求, 库存)；断货期 0 不是真实 0。
- D2b 必须输出 `estimated_demand` + p10/p50/p90 + 方法/假设/置信；估计值不覆盖 raw，不直接进净额。
- 方法候选：带库存上限的 Negative-Binomial EM + form×pool×uom 经验贝叶斯收缩；非删失月模拟遮断验证。
- 假设不成立时保留 `censor_unknown` 或扩大区间，不伪造点值。

### 5. 短史不是放弃

- 「短」按**有效观测月**，不是产品年龄；当前 <12 月是旧口径，归一后重算。
- 真新品/短史：同 form×pool×uom 池化、经验贝叶斯收缩、同族类比；状态分开 `new / stockout-short / clearance / old / uncertain`。
- 老产品是 `policy_excluded`，不是 short。

### 6. 模型选择

- naive/MA3/seasonal naive/ETS 是基线；Croston/SBA 只对间歇/块状，且回测 WAPE/MAE 不劣 + 至少一项改善≥5% 才采用；TSB 只在过时证据。
- 模型数量不是目标；每个序列保留 `adopted_model/best_baseline/selection_reason`。
- 促销/季节：用 2022-2026 历史自动识别 STL/Fourier/事件窗口；Jeck 清仓表只作旁证；广告历史缺失不让订单失效，广告只作可选近期解释。

## Why This Matters

- 把政策当 gap，会让 1,682 行看起来「未解决」，实际很多是 ND/HM/老产品/共享/CG 的既定规则。
- 把「没有 forecast row」当阻碍，会让 D 停摆；D 必须自己 fallback。
- 不归一历史，会把 4 年老品误判成 885 个 short；不估删失，会系统性低估断货品。

## When to Apply

- D1 资格、D2 清洗、D3 回测、D5 概率/服务、Top50 沙盒；
- 任何把销量→需求的建模；
- 业务问「为什么这个 SKU 不能预测」时。

## Examples

- 10 月原始订单 6,292 行/qty 6,973 已并入；D2 v3 的 202610 不再是全 `censor_unknown`；FBA 116 行/qty 1,550 单独 channel。
- 三角/平条靠枕有 2022-2026 历史，应先归一别名再用，而不是因为当前键只有 7 个月就判 short。
- 断货月 `stockout_censored` 用 NB-EM 估潜在需求；非删失月遮断回测验证。

## Related

- `docs/solutions/best-practices/censored-demand-cold-start-seasonality.md`
- `docs/solutions/architecture-patterns/supply-chain-a-b-c-data-pipeline.md`
- `docs/solutions/best-practices/sku-normalization-uom-sets-split-package.md`
