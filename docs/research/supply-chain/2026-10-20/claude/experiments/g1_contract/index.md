---
okf: v0.1
type: Index
title: G1 契约回放
description: G1a 本地映射覆盖率；G1b 库存快照与 EN 生产只读 API
date: 2026-10-20
tags: [supply-chain, g1, mapping, index]
---

# G1 — 契约回放

| 文件 | 内容 |
|---|---|
| [README.md](README.md) | 复现命令与输入（G1a + G1b） |
| [mapping_process.md](mapping_process.md) | **G1 口径**：BOM 客户码精确匹配；出库消耗（含补发）；退货 5% 情境；3PL 供货归属 |
| [codex-sync.md](codex-sync.md) | 给 Codex 的 G1 增量同步（c854800e 之后） |
| [results.md](results.md) | G1a v1 映射覆盖率（历史记录，口径已被 mapping_process 更正） |
| [g1b_pilot.md](g1b_pilot.md) | G1b EN 单据只读试点（单个头部 SKU） |
| [g1b_results.md](g1b_results.md) | G1b 首版：出库消耗、库存快照、覆盖月数与 SKU 缺口 |
| [g1b_stock_snapshot.py](g1b_stock_snapshot.py) | 通途 family 库存快照（只读、分块节流） |
| [g1b_en_extract.py](g1b_en_extract.py) | EN SO/DN/WO/JC/PP 结构化导出（生产只读） |
| [g1b_coverage.py](g1b_coverage.py) | 出库消耗 vs 库存覆盖（历史 run-rate） |
| [g1_mapping_coverage.py](g1_mapping_coverage.py) | 只读本地映射覆盖率脚本 |
| [g1_missing_analysis.py](g1_missing_analysis.py) | 763 vs 155 未匹配归因（尾缀/平台SKU/P2 非 family） |
| [out/](out/mapping_coverage.json) | 聚合结果（不含 PII/原始行） |

G1b 进行中：库存快照已跑 CENTRADE / DANEEY；EN 单据已跑 1 个头部 SKU；
待把 top SKU 的结构化单据与覆盖结果汇总成报告。
