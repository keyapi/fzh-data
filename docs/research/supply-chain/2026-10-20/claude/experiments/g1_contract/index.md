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
| [g1b_results.md](g1b_results.md) | G1b 首版：出库消耗、库存快照、覆盖与假设 |
| [g1b_review_response.md](g1b_review_response.md) | 对 Codex `d9a11557` 的 G1B01–09 修复记录 |
| [g1b_warehouse_evidence.md](g1b_warehouse_evidence.md) | 旧皮壳仓/当前美中仓证据；合并 `unverified` |
| [g1b_stock_snapshot.py](g1b_stock_snapshot.py) | 通途 family 库存快照（只读、分块节流） |
| [stock_daily_backup.py](stock_daily_backup.py) | 每日全仓 API 库存备份（JSONL + manifest） |
| [g1b_from_daily_backup.py](g1b_from_daily_backup.py) | 每日备份 JSONL → G1b 快照 JSON |
| [g1b_en_extract.py](g1b_en_extract.py) | EN SO/DN/WO/JC/SE/PP 结构化导出（生产只读） |
| [g1b_coverage.py](g1b_coverage.py) | 出库消耗 vs 库存覆盖（历史 run-rate） |
| [g1_mapping_coverage.py](g1_mapping_coverage.py) | 只读本地映射覆盖率脚本 |
| [g1_missing_analysis.py](g1_missing_analysis.py) | 763 vs 155 未匹配归因（尾缀/平台SKU/P2 非 family） |
| [out/](out/mapping_coverage.json) | 聚合结果（不含 PII/原始行） |

G1b 状态：EN 单据试点已修 DN 行键/JC 跨工序/SE/未发分解；库存完整快照重跑中；
旧 450/501 缺口撤回，待 complete 快照重算；top10–20 扩样等修复重跑通过后再做。
