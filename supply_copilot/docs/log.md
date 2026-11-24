---
okf: v0.1
type: Log
title: 变更日志
description: Supply Copilot 的时序变更记录
tags: [supply-copilot, changelog]
---

# 变更日志

## 2026-11-24

- **新增整分公司批量刷新**：`refresh --all --out <私有目录>` 输出不可变快照
  `refresh_<branch>_<as_of>_<sha>.json` + `report.json`；单 SKU `--sku` 用法保持兼容。
- **期间语义**：D5 的 97/157 天标为 `full_period`，不得当剩余期；缺显式期间一律
  `暂不能判断`，只有显式等长期间（`--period-start/--period-end`）才给确定建议。
  实现见 `period.py`（docstring 说明整期/剩余期边界）。
- **W1 SO 去重**：`demand_collaboration.so_evidence.load_deduped` 按 `(so, so_line)`
  折叠重复行并回报折叠数/重复开放量；`load()` 保持原行为。三段（近期/历史/创建日未知）
  合计等于开放总量，SO 恒不计入已证供给。
- **W1 阶段余额**：`so_stage.py` 汇总 `stage_balances`，unknown 阶段原样保留，
  与开放量非同一度量、不可相加、不进 proven。
- **测试**：`supply_copilot/tests/test_refresh_batch.py`（21 条，合成数据）。
