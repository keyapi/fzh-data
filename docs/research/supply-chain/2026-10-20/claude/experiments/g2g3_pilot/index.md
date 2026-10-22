---
okf: v0.1
type: Index
title: G2+G3 窄范围试点（只读）
description: 10 SKU 需求预测 + 补货情景 V0 的构建脚本与 2-SKU 样例；证据 canonical 在 out/replenishment_v0/
date: 2026-10-22
tags: [supply-chain, forecast, replenishment, pilot]
---

# G2+G3 窄范围试点

只读构建：`build_v0.py` 从 `D:/Work/fzh-order-store/order_store.duckdb`（read_only）与
EN phase1 快照生成 2-SKU 样例、10-SKU 报告与证据 JSON。0 次生产访问、不下单、不扩样。

| 文件 | 内容 |
|---|---|
| [build_v0.py](build_v0.py) | 历史需求、seasonal naive / mean3 / ETS 候选、6 起点回测、库存/PO/在产、A/B 情景、报告生成 |
| [out/sample_2sku.json](out/sample_2sku.json) | 2 个代表 SKU 的端到端样例（聚合，不含原始订单行） |
| [../../control/reviews/2026-10-22-sample-2sku.md](../../control/reviews/2026-10-22-sample-2sku.md) | 2-SKU 样例报告 |
| [../../control/reviews/2026-10-22-supply-demand-replenishment-v0.md](../../control/reviews/2026-10-22-supply-demand-replenishment-v0.md) | 10-SKU V0 报告 |
| [../../out/replenishment_v0/evidence.json](../../out/replenishment_v0/evidence.json) | V0 聚合证据（canonical） |

重跑：

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/g2g3_pilot/build_v0.py --sample
```
