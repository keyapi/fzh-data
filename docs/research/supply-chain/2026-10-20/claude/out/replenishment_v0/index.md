---
okf: v0.1
type: Index
title: G2+G3 V0 证据
description: 10 SKU 供需与补货 V0 的聚合证据 JSON；不含原始订单行
date: 2026-10-22
tags: [supply-chain, evidence, replenishment]
---

# G2+G3 V0 证据

| 文件 | 内容 |
|---|---|
| [evidence.json](evidence.json) | 10 SKU 的月度聚合需求、预测/回测、库存、PO/在产、A/B 情景、建议量、未知项；含查询定义与源哈希 |

证据边界：

- 只聚合，不含原始订单行；SO/WO/PO 标识是单据级键。
- 源 DB 以 `read_only=True` 打开；运行前后 sha256 记录在 `sources.db`。
- ETA 全空、在产日期全空、UOM/Cover/删失未证等内容在 `open_items` 与逐 SKU `unknowns` 单列。
- 报告：[../control/reviews/2026-10-22-supply-demand-replenishment-v0.md](../control/reviews/2026-10-22-supply-demand-replenishment-v0.md)
