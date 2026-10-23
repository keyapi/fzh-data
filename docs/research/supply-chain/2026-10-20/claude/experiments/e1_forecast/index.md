---
okf: v0.1
type: Index
title: E1 预测基线回测（R01/R02 修正版）
description: 43 个月通途月表、8 个楔形枕 SKU 的统计基线回测；含标签可知性切分与数据质量闸门
date: 2026-10-20
tags: [supply-chain, forecasting, experiment]
---

# E1 — 预测基线回测

| 文件 | 内容 |
|---|---|
| [README.md](README.md) | 复现命令、标签可知性切分、数据质量与输入输出 |
| [results.md](results.md) | 方法与结论、R01/R02 修正记录、Pass/Falsify、限制 |
| `pull_data.py` | 只读拉取 43 张月表；按发货日期归月；非法数量标记不转 0；列对齐与逐月读取计数 |
| `backtest.py` | 滚动原点回测（最小训练 18 月；label lag；验证期选择 / 测试期报告；`--self-test`） |
| `data_status.json` | 每个 SKU-月的 observed / zero_confirmed / pre_launch / missing / bad_data 状态（不入库） |
| `data/` | 原始/月度 CSV 与拉取日志（CSV 不入库）；`results_*.json` |

本轮要点：验证与测试目标月零重叠（`label_overlap_check.pass=true`）；
测试期 TSB 0.511、ens5 0.520、naive 0.602；验证期选 Croston/MA3，测试仍不如 ens5。
