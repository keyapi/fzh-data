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
| [README.md](README.md) | 复现命令与输入 |
| [mapping_process.md](mapping_process.md) | **待确认**：只用 BOM 客户码精确匹配；base/-Cover/-out 与皮壳仓口径 |
| [codex-sync.md](codex-sync.md) | 给 Codex 的 G1 口径同步（皮壳 1:1、旧 v1 作废、C21–C25） |
| [results.md](results.md) | G1a v1 映射覆盖率（历史记录，口径已被 mapping_process 更正） |
| [g1_mapping_coverage.py](g1_mapping_coverage.py) | 只读本地映射覆盖率脚本 |
| [g1_missing_analysis.py](g1_missing_analysis.py) | 763 vs 155 未匹配归因（尾缀/平台SKU/P2 非 family） |
| [out/](out/mapping_coverage.json) | 聚合结果（不含 PII/原始行） |

下一步 G1b：两仓 cutoff 库存快照 + EN 生产只读 API（SO/PP/WO/JC/SE/DN）→ 守恒与异常报告。
