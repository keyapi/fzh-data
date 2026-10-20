---
okf: v0.1
type: Experiment-Results
title: G1b top10 EN 单据抽取（修复后）
description: 9 个头部 family SKU 的 SO/DN/WO/JC/SE 抽取；未发量互斥分解全部对平
date: 2026-10-20
tags: [supply-chain, g1b, erpnext, top10, reconciliation]
---

# G1b top10 EN 单据抽取（修复后）

> 目的：验证 G1B05–07 修复能跨 SKU 工作；不是全 family 结果。
> 输入：2026-04..09 family 出库前 10 个 SKU（9 个客户码 + 1 个 TT 码）。
> 输出：`out/g1b_en_top_*.json`（本地，含单据号；不入库）。

## 1. 已完成（8/9）

| # | 客户码 | SO | SE | open 对平差 | field_issues |
|---|---|---:|---:|---:|---:|
| 1 | CENCord995-DKGrey-97 | 19 | 87 | 0.0 | 0 |
| 2 | CEN003-DPBLUE-100 | 15 | 101 | 0.0 | 0 |
| 3 | C/Linen-Natural-100-688-wow | 19 | 49 | 0.0 | 0 |
| 4 | C/Cord-DKBlue-100-713-wow | 16 | 47 | 0.0 | 0 |
| 5 | C/Linen-Natural-153-688-wow | 28 | 66 | 0.0 | 0 |
| 6 | C/Velvet-Grey-100-705-wow | 15 | 36 | 0.0 | 0 |
| 7 | C/Cord-Grey-100-710-wow | 18 | 63 | 0.0 | 0 |
| 8 | C/Linen-White-100-662-WOW | 17 | 40 | 0.0 | 0 |
| 9 | TT0000671K0063721 | 运行中 | — | — | — |

- 全部 8 个 SKU 的 `open_breakdown.difference = 0`：死单 + 在产 + 无计划 + 超发 = `totals.open_qty`。
- 全部 `se_query_error = None`，已提交 Manufacture SE 正常抽出。
- 全部 `field_issues = 0`（open 行都有交货日/仓/UOM）。

## 2. 结构观察

- **死单不是个例**：top5 中 `SO-26-00098` 在不同 SKU 上分别留下 110–120 件死单；
  `SO-24-00033-1` 等也有 Closed 未发。
- **超发普遍**：多个 SKU 有 -11 到 -217 的超发（delivered > ordered），
  不能把 `open_qty` 直接截成 0；必须保留负值并单列。
- **无计划单常见**：`SO-26-00035`、`SO-26-00036`、`SO-26-00037` 等未发但无 WO/PP。
- **同一 SO 跨多个 SKU**：同一 SO 号在多个客户码下出现，说明一张 SO 多行；
  不能按 SO 头去重后只算一次，必须按 SO 行/物料行。

## 3. 结论

- G1B05–07 修复可跨 SKU 复现：按工序 JC、DN 行键、SE、未发互斥分解都成立。
- 仍不能宣布 G1 契约通过：库存完整快照/覆盖重算、WayfairCG 实盘、仓池证据仍未闭合。
- 下一步：等第 9 个 SKU 完成；用完整 API 库存快照重算覆盖；再交 Codex 复审。
