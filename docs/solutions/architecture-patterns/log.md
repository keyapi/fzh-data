---
okf: v0.1
type: Log
title: architecture-patterns — 变更日志
tags: [solutions, architecture-patterns, log]
---

# architecture-patterns 变更日志

## 2026-11-12

- **新增**: `en-supply-line-e-replenishment-decision-boundary.md` — 线上 `key_test.so_chain`（E）用于补货/下单决策的边界。两种用途分开：SO 级看板可用（加护栏），供给事实源不可直接使用。七个偏差：① `instock` = 累计入库不是可用库存（实例：instock 72、已发 72、半成品仓 0/reserved 45、美东仓 481）；② `inventory/receipt=not_integrated`；③ 超发负 `open_qty`（179/45）会错抵其他 SKU；④ 质检未放行可能被当完成待出库；⑤ Closed 落 stage 3；⑥ `partial` 只警示不阻断；⑦ 154 行约千次查询、首张约 6.8s、千单未压测。P0 改进：接入库存/收货、逐行截零、QC 门、unknown 阻断。仓库 v4 ≠ 线上版，评审前先同步源码。

## 2026-10-14

- **新增**: `ustx-cost-caliber-comparison.md` — 美中仓库由 `2CJG-SX` 改走当地 USTX 加工的 A/B1/B2 三口径只读对比方法论：先验「测算表是手填还是公式」再定等价闸门（本例人工测算 B1 与 import 重建 B2 在 57 个共有键上无一相等 → **差异即结论**）；歧义维表键 fail-closed（同键不同重量模板 → 摘除索引、对应行记 `ambiguous_shell_key` 排除，不猜首/末行）；闸门分级（阻断级 vs 告警级）；只读快照 `render_option` 值/公式双冻结。

## 2026-09-22

- **新增**: `public-private-agent-knowledge-split.md` — 公开仓、私有 Markdown 知识仓与 secret manager 三层分离；普通 clone + bootstrap 代替 submodule，保留 Agent 检索和非技术同事使用体验。

## 2026-11-05

- **新增**: `tongtu-cost-engine-local-migration.md` — Colab 成本引擎迁移本地包：合并成一件成品 + 月末 BOM 单位成本 × 件数；四列（皮壳/头程/目的地加工/绍兴侧加成）语义与恒等式；套件/FBA 分支；canary 旧值必须取目标写回表。
