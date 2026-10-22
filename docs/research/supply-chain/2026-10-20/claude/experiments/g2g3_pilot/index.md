---
okf: v0.1
type: Index
title: G2+G3 窄范围试点（V0 + V1 模型赛马，只读）
description: 10 SKU 需求预测 + 补货情景 V0 与 V1 五候选赛马；证据 canonical 在 out/replenishment_v0/
date: 2026-10-22
tags: [supply-chain, forecast, replenishment, pilot, model-race]
---

# G2+G3 窄范围试点

只读构建：`build_v0.py` 从 `D:/Work/fzh-order-store/order_store.duckdb`（read_only）与
EN phase1 快照生成 2-SKU 样例、10-SKU 报告与证据 JSON。0 次生产访问、不下单、不扩样。

V1 赛马：`model_race.py` 只读同一 DB 与 V0.1 `evidence.json`，比较 5 个候选
（seasonal naive / mean3 / seasonal×YoY / ETS 明确跳过 / peer shape），
最近 6 起点 1/3 月回测，累计 P90 用滚动误差的经验/共形分位（不用 √6），
输出补货动作敏感性。不修改 `build_v0.py` 或 V0.1 报告。

| 文件 | 内容 |
|---|---|
| [build_v0.py](build_v0.py) | 历史需求、seasonal naive / mean3 / ETS 候选、6 起点回测、库存/PO/在产、A/B 情景、报告生成（V0.1） |
| [model_race.py](model_race.py) | V1 五候选赛马：滚动 6 起点、共形累计 P90、模型分歧、补货动作敏感性（只读） |
| [out/sample_2sku.json](out/sample_2sku.json) | 2 个代表 SKU 的端到端样例（聚合，不含原始订单行） |
| [../../control/reviews/2026-10-22-sample-2sku.md](../../control/reviews/2026-10-22-sample-2sku.md) | 2-SKU 样例报告 |
| [../../control/reviews/2026-10-22-supply-demand-replenishment-v0.md](../../control/reviews/2026-10-22-supply-demand-replenishment-v0.md) | 10-SKU V0 报告 |
| [../../control/reviews/2026-10-22-model-race.md](../../control/reviews/2026-10-22-model-race.md) | V1 赛马报告（候选比较、6 SKU 8%–20% 分解、White 峰值、动作敏感性） |
| [../../out/replenishment_v0/evidence.json](../../out/replenishment_v0/evidence.json) | V0 聚合证据（canonical） |
| [../../out/replenishment_v0/model_race.json](../../out/replenishment_v0/model_race.json) | V1 赛马聚合证据（逐 SKU 候选/回测/标定/动作） |

重跑：

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/g2g3_pilot/build_v0.py --sample
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/g2g3_pilot/model_race.py
```
