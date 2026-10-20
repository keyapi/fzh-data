---
okf: v0.1
type: Guide
title: E2 补货分配优化 — 复现说明
description: 用 OR-Tools CP-SAT 求解 8 SKU × 12 个月、单次下单、预算约束下的补货分配，并与业务 6 个月覆盖公式对比；一条命令复现全部表格。
date: 2026-10-20
tags: [supply-chain, replenishment, ortools, cp-sat]
---

# E2 补货分配优化 — 复现说明

本实验回答一个问题：在固定的下单预算下，把 8 个 SKU 的补货量重新分配，能否比业务“月需求 × 6 − 可用 − 在途”的公式更省钱或更少缺货。模型读取 `data/input.json` 中从本地补货决策信息包（2026-10-16）提取的 8 个 SKU 数值，建立 12 个月、交期 3 个月、单次下单的 CP-SAT 整数规划（MOQ 二值开关、预算约束、库存平衡、lost-sales 缺货变量），先最小化“持有 + 20 × 缺货 + 5 × 开单数”，再在最优成本下最小化时间加权缺货以打破并列，然后用独立仿真函数回读校验，并在 B=257 与 B=180 两个预算、base/low/high（×0.75/×1.00/×1.25）三种需求下与业务公式及同预算缩放对照。复现只需在仓库根目录执行 `uv pip install ortools`（若未安装，实测 9.15.6755）和 `uv run python docs/research/supply-chain/2026-10-20/claude/experiments/e2_replenishment/solve.py`；脚本会在控制台打印全部 Markdown 表格，把完整数值写入 `data/results.json`，6 个求解实例总耗时不到 0.5 秒。方法、逐 SKU 结果、结构性分析、判定与限制见 [results.md](results.md)。

## 文件

| 文件 | 用途 |
|---|---|
| [solve.py](solve.py) | 模型、独立仿真、基线与敏感性分析入口 |
| [data/input.json](data/input.json) | 8 个 SKU 的提取输入与假设 |
| [data/results.json](data/results.json) | 全部数值结果（含回读校验） |
| [results.md](results.md) | 方法、结果、判定、限制 |
