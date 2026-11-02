---
okf: v0.1
type: Reference
title: 删失需求、短史冷启动与季节/促销识别：D 的可复用方法
date: 2026-11-02
category: best-practices
module: supply_chain
problem_type: best_practice
component: tooling
severity: high
applies_when:
  - "销量在断货月为 0，但不能当真实 0"
  - "大量 SKU 历史不足 12 个月或被别名拆散"
  - "需要自动识别季节/促销，而不是让人手填日期"
tags: [censored-demand, cold-start, seasonality, promotion, croston]
---

# 删失需求、短史冷启动与季节/促销识别

## Context

电商销量不是需求：**销量 = min(需求, 库存)**。断货时需求被截断，0 不代表没人买。短史也常常不是新品，而是 SKU 改名/前后缀/大小写/客户码把历史拆散了。促销日期不需要人逐条填：4 年历史足够自动识别主要季节和事件。

## Guidance

### 1. 删失需求：估计，不只标注

- 非删失月：观测销量 = 需求。
- 删失月：观测销量是上限（库存），真实需求 ≥ 销量。
- 推荐方法：带库存上限的 Negative-Binomial EM + `form×pool×uom` 经验贝叶斯收缩；库存只给区间时跑 lower/base/upper 三情景。
- 输出：`observed_demand`、`estimated_demand`、p10/p50/p90、`censor_method`、`censor_assumption`、`censor_confidence`、`source_refs`。
- 验证：在非删失月人为遮断 1/2/3 个月，隐藏真实销量，比较「只标删失 / 速率上界 / NB-EM」的 WAPE/MAE/pinball、区间 coverage、上偏率；按 smooth/intermittent/lumpy/short 分层。
- 失败回退：库存上限不可靠、结构变化、需求转移无法排除时，保留 `censor_unknown` 或扩大区间，不伪造点值。

### 2. 短史：先归一，再冷启动

- 先按 A/B 规则做历史归一：casefold、`OLD_`、`-new/-Cover/-c/-1/-2`、客户物料号、别名、Product Bundle；保留 `history_bridge_refs`、`effective_from/to`。
- 归一时只有证据一致且候选唯一才合并；共享/多候选/跨 form/UOM 仍隔离，标 ambiguous。
- 归一后按**有效观测月**分：`<3`、`3–5`、`6–11`、`≥12`；不是按产品创建日期。
- 真短史/新品：同 `form×pool×uom` 池化、Gamma-Poisson/NB 经验贝叶斯收缩、同族类比（尺寸/面料/价格/品类）；类比只作候选，不直接复制。
- 状态分开：`new / stockout-short / clearance / old / uncertain`；老产品是政策排除，不是短史。

### 3. 模型选择：适配优先，不是越先进越好

- 基线：naive、MA3、seasonal naive、ETS。
- 间歇/块状：Croston/SBA；过时风险：TSB。
- 采用门槛：WAPE 与 MAE 均不劣于最佳基线，且至少一项改善≥5%；否则用基线。
- 每个序列保留 `adopted_model/best_baseline/selection_reason`；模型失败给 `fallback_model`，不是「不能预测」。
- 4 年历史归一后重新分类/回测；不要用旧 12 个月截断的数字下结论。

### 4. 季节/促销：自动识别，不等人填日期

- 用 2022-2026 月/周序列做 STL/稳健分解、Fourier 年季节项、固定节假日前后窗口（Prime Day/返校季/圣诞）、历史异常峰值。
- 清仓（Jeck 特殊规则表）只作 `clearance_evidence` 旁证，不直接当需求基准；FBA SKU 不直接适用。
- 回测对比：无特征 / 自动季节 / 季节+清仓 三组，指标 WAPE/MAE/pinball/coverage；不提升就回退。
- 广告：赛狐只有近期报表，历史广告缺失**不使历史订单失效**；广告暂不作前置，只作可选近期解释变量，单独报告完整覆盖子集。

## Why This Matters

- 不估删失：断货品被系统性低估，越缺越不补。
- 不归一历史：4 年老品被当新品，预测退化成池均值。
- 不自动识别季节：促销月被当正常需求，非促销月被高估。
- 广告历史不全是常态；把广告当预测前置会让大部分历史不可用。

## When to Apply

- D2b 删失估计、D3b 历史归一/冷启动、D5b 季节/促销；
- 任何按销量做补货/库存的模型；
- 业务问「断货了还能不能预测」「新品怎么估」时。

## Examples

- 某 SKU 2026-07..10 连续断货：不能把 4 个月 0 当需求；用 NB-EM 估计潜在需求并给区间，非删失月遮断回测验证。
- 三角靠枕当前键只有 7 个月，但 2022-2026 有同物历史：先归一别名再接长，不判 short。
- Prime Day/返校季/圣诞：用历史月度峰值自动识别窗口，不需要用户给日期；Jeck 清仓月单独标记，不混正常需求。

## Related

- `docs/solutions/architecture-patterns/demand-forecast-layer-d.md`
- `docs/solutions/best-practices/sku-normalization-uom-sets-split-package.md`
- `docs/solutions/architecture-patterns/supply-chain-a-b-c-data-pipeline.md`
