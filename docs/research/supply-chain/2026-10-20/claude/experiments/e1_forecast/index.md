---
okf: v0.1
type: Index
title: E1 预测基线回测
description: 43 个月通途月表、8 个楔形枕 SKU 的统计基线回测
date: 2026-10-20
tags: [supply-chain, forecasting, experiment]
---

# E1 — 预测基线回测

| 文件 | 内容 |
|---|---|
| [README.md](README.md) | 复现命令与输入输出 |
| [results.md](results.md) | 方法与结论、Pass/Falsify、限制 |
| `pull_data.py` | 只读拉取 43 张月表（按发货日期归月） |
| `backtest.py` | 滚动原点回测（最小训练 18 月；验证期选择 / 测试期报告） |
| `data_status.json` | 每个 SKU-月的 observed / zero_confirmed / pre_launch / missing 状态 |
| `data/` | 原始/月度 CSV 与拉取日志（CSV 不入库）；`results_*.json` |
