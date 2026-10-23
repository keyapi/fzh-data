---
okf: v0.1
type: Index
title: G2+G3 证据（V0.1 + V1 赛马）
description: 10 SKU 供需与补货 V0 证据 + V1 五候选赛马证据；均为聚合 JSON，不含原始订单行
date: 2026-10-22
tags: [supply-chain, evidence, replenishment, model-race]
---

# G2+G3 证据

| 文件 | 内容 |
|---|---|
| [evidence.json](evidence.json) | V0.1 冻结证据：10 SKU 的月度聚合需求、预测/回测、库存、PO/在产、A/B 情景、建议量、未知项；含查询定义与源哈希 |
| [model_race.json](model_race.json) | **V1 赛马 canonical**：5 候选（ETS 明确跳过）的逐 SKU 预测、6 起点回测、共形累计 P90、模型分歧、补货动作敏感性；输入哈希与行数对账 |
| [actions.json](actions.json) | **P90-free 暂行行动清单（机器可读）**：10 SKU 的 D1/D2、A/B 边界、T1–T4 判定、分类与证据优先级、需补证据与责任角色、启动条件；不读任何 P90 字段、不含数量 |

证据边界：

- 只聚合，不含原始订单行；SO/WO/PO 标识是单据级键。
- 源 DB 以 `read_only=True` 打开；运行前后 sha256 记录在 JSON `inputs`。
- V1 的 P90 用滚动累计误差的经验/共形分位，**不是** V0.1 的 √6 随机游走；
  V0.1 的 P90 与衍生补货结论按 D10 失效，`evidence.json` 只作冻结对照。
- ETA 全空、在产日期全空、UOM/Cover/删失未证等内容在 `open_items` 与逐 SKU `unknowns` 单列。
- 报告：[../../control/reviews/2026-10-22-supply-demand-replenishment-v0.md](../../control/reviews/2026-10-22-supply-demand-replenishment-v0.md)（V0.1）、
  [../../control/reviews/2026-10-22-model-race.md](../../control/reviews/2026-10-22-model-race.md)（V1 赛马）、
  [../../control/reviews/2026-10-22-replenishment-actions-v0.md](../../control/reviews/2026-10-22-replenishment-actions-v0.md)（P90-free 行动清单，对应 `actions.json`）。
