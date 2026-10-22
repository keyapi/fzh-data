---
okf: v0.1
type: Plan
title: V1 候选模型赛马（10 SKU，滚动回测）
date: 2026-10-22
owner: claude-worker
---

# V1 候选模型赛马

## 目标

不做“选一个模型”的空谈；用同一批数据、同一批历史切点，比较候选，回答：
- 不同合理预测下，补货动作是否一致；
- 6 个 SKU 的去年同期预测为何只有近期水平的 8%–20%；
- Linen-White 2026-08 峰值 280 如何处理；
- 累计 P90 不再用随机游走 √6 假设。

## 输入

`D:/Work/fzh-order-store/order_store.duckdb` 只读；10 个 EN 链完整 SKU；销量截止 2026-09；
库存 10-22；EN phase1 单据。不得访问生产。

## 候选（同一滚动切点）

1. seasonal naive：去年同月；
2. 近期均值/简单指数平滑（近 3 月）；
3. seasonal naive × 近期同比水平修正（去年近零/断货/异常月必须保护，不能除小分母）；
4. AutoETS/ETS（若 statsmodels/statsforecast 可用；不可用则明确跳过）；
5. 同类产品季节形状 × 本 SKU 近期水平（短历史借力）。

## 回测

- 最近 6 个起点，1 月与 3 月累计；禁止泄漏；
- WAPE、bias、P90 覆盖率；零实际单元格保留；零总量分母单独处理；
- **累计 P90 用滚动累计误差的经验分位数/共形校准**，不要用 √6 或 √14 的随机游走假设；样本不足标 estimate；
- 目标 90% 与实际覆盖分开记录。

## 口径

- 需求是“已发货量”（despatch_date），不是完整需求；缺货未成交未恢复，明确标注；
- 已知 SO 与预测不得盲目相加；先判断是否重复计需求；
- 90 天慢船作为明确情景；不把无 ETA 的 PO 当近期必然可用。

## 输出

- `experiments/g2g3_pilot/model_race.py`（只读）
- `control/reviews/2026-10-22-model-race.md`
- `out/replenishment_v0/model_race.json`（聚合）
- 每个 SKU：候选预测、回测、模型分歧原因、补货动作敏感性（总是需补/取决于到货假设/证据不足）。
- 解释 6 个 SKU 的 8%–20% 现象与 White 峰值；给出建议（保留情景/修正/需数据）。
- 提交固定 commit；不访问生产、不下单、不扩样、不合并 PR。
