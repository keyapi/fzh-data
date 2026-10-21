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
| [g1b_round2_response.md](g1b_round2_response.md) | 对 Codex `fd1029b4` 的 RR01–RR08 修复记录 |
| [g1b_round3_response.md](g1b_round3_response.md) | 对 Codex `93e6bd1f` 的 T01–T06 修复与 E01–E04 契约 |
| [g1b_round4_response.md](g1b_round4_response.md) | 对 Codex `c6275051` 的 U01、15 统一与 family PoC |
| [g1b_round5_response.md](g1b_round5_response.md) | 对 Codex `862f77d1` 的 S01–S04 与同窗 SO 重跑 |
| [g1b_round6_response.md](g1b_round6_response.md) | 对 Codex `run_86b2a4645f21` 的 S02/S04：变体证据门、逐行审计、详情闸门与守恒 |
| [g1b_evidence_producer.md](g1b_evidence_producer.md) | 有界 Item/BOM 证据 producer（20 变体样本，current_structure_only） |
| [g1b_dn_wo_jc_se.md](g1b_dn_wo_jc_se.md) | **DN/WO/JC/SE 关联与同单位守恒 v2**（5 快照；C1 逐行全精度 / C2 覆盖完整 / C3 / C4 原始行账 + 逐行去向；produced_qty 不可作完工账） |
| [g1b_dn_wo_jc_se.py](g1b_dn_wo_jc_se.py) | 快照离线关联/守恒 + 有界 SE 明细补齐与异常 WO 探针（UOM 分区、SE 元数据校验、请求级预算） |
| [test_g1b_dn_wo_jc_se.py](test_g1b_dn_wo_jc_se.py) | DN/WO/JC/SE 契约离线单测（78 条，不联网；含 9 项复审反例） |
| [en_variant_evidence.py](en_variant_evidence.py) | Item/BOM 只读采样 → variant evidence manifest（预算/分页/单并发） |
| [g1b_top10.md](g1b_top10.md) | 修复后 top10 SKU 抽取；未发分解全部对平 |
| [g1b_warehouse_evidence.md](g1b_warehouse_evidence.md) | 2026-09 仓名统一，旧皮壳并入美中（用户确认+脚本注释）；旧仓 ID/余额审计 pending |
| [g1b_stock_snapshot.py](g1b_stock_snapshot.py) | 通途 family 库存快照（只读、分块节流） |
| [stock_daily_backup.py](stock_daily_backup.py) | 每日全仓 API 库存备份（JSONL + manifest） |
| [g1b_from_daily_backup.py](g1b_from_daily_backup.py) | 每日备份 JSONL → G1b 快照 JSON |
| [g1b_en_extract.py](g1b_en_extract.py) | EN SO/DN/WO/JC/SE/PP 结构化导出（生产只读） |
| [en_family_poc.py](en_family_poc.py) | Family SO 批量只读 PoC（证据门 + 逐行审计 + 详情守恒） |
| [test_en_family_poc.py](test_en_family_poc.py) | 变体证据契约离线单测（45 条，不联网） |
| [test_en_variant_evidence.py](test_en_variant_evidence.py) | producer 离线单测（21 条，不联网） |
| [g1b_coverage.py](g1b_coverage.py) | 出库消耗 vs 库存覆盖（历史 run-rate） |
| [g1_mapping_coverage.py](g1_mapping_coverage.py) | 只读本地映射覆盖率脚本 |
| [g1_missing_analysis.py](g1_missing_analysis.py) | 763 vs 155 未匹配归因（尾缀/平台SKU/P2 非 family） |
| [out/](out/mapping_coverage.json) | 聚合结果（不含 PII/原始行） |

G1b 状态：EN 单据试点与 top10 已修 DN 行键/JC 跨工序/SE/未发分解，9/9 对平；
完整 API 库存快照已重算（131 有需求无供给 / 194 <2 月 / 127 unknown）；
旧 450/501 撤回；2026-09 仓名统一，旧皮壳并入美中（系统审计 pending）。
