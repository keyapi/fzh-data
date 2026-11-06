---
okf: v0.1
type: Index
title: 2026-11-05/11-06 供应链库存核对
description: 单 SKU 库存节点核对与 CG 多件套/在途缺口
date: 2026-11-06
tags: [supply-chain, inventory, index]
---

# 2026-11-05/11-06 供应链库存核对

| 文档 | 内容 |
|---|---|
| [TT0031038K0062927 节点核对](tt0031038k0062927-node-reconciliation.md) | 美中/波兰/通途 CG 账/Wayfair CG API 数量；91 到货与 102 出库；120 不可核实；CG 多件套映射与在途缺口；补货系统数据契约 |
| [Wayfair CG 入仓/在途 API 调研](wayfair-cg-inbound-api-research.md) | 逐个验证入仓/在途 operation；WSA 实为 CG→客户出库；PO 为客户订单；给出 `Δ在库+WSA出库` 反推收货的间接口径与实测 |

## 说明

- 数据 as_of：通途 2026-11-06 05:17；CG API 2026-11-06 07:00:58；实时复核 09:06。
- 只读核对，未修改任何生产数据。
