---
okf: v0.1
type: Log
title: architecture-patterns — 变更日志
tags: [solutions, architecture-patterns, log]
---

# architecture-patterns 变更日志

## 2026-10-14

- **新增**: `ustx-cost-caliber-comparison.md` — 美中仓库由 `2CJG-SX` 改走当地 USTX 加工的 A/B1/B2 三口径只读对比方法论：先验「测算表是手填还是公式」再定等价闸门（本例人工测算 B1 与 import 重建 B2 在 57 个共有键上无一相等 → **差异即结论**）；歧义维表键 fail-closed（同键不同重量模板 → 摘除索引、对应行记 `ambiguous_shell_key` 排除，不猜首/末行）；闸门分级（阻断级 vs 告警级）；只读快照 `render_option` 值/公式双冻结。

## 2026-09-22

- **新增**: `public-private-agent-knowledge-split.md` — 公开仓、私有 Markdown 知识仓与 secret manager 三层分离；普通 clone + bootstrap 代替 submodule，保留 Agent 检索和非技术同事使用体验。

## 2026-11-05

- **新增**: `tongtu-cost-engine-local-migration.md` — Colab 成本引擎迁移本地包：合并成一件成品 + 月末 BOM 单位成本 × 件数；四列（皮壳/头程/目的地加工/绍兴侧加成）语义与恒等式；套件/FBA 分支；canary 旧值必须取目标写回表。
