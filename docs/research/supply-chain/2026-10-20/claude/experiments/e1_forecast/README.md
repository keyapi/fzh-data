---
okf: v0.1
type: Reference
title: E1 预测基线回测 — 复现说明（R01/R02 修正版）
description: 数据拉取与回测命令、标签可知性切分、数据质量闸门、训练/验证/测试设计与输出说明
date: 2026-10-20
tags: [supply-chain, forecasting, experiment, readme, revised]
---

# E1 预测基线回测 — 复现

```bash
cd docs/research/supply-chain/2026-10-20/claude/experiments/e1_forecast
uv run python pull_data.py
uv run python backtest.py --self-test
uv run python backtest.py --measure qty_daneey --mode censored
uv run python backtest.py --measure qty_all    --mode censored
uv run python backtest.py --measure qty_daneey --mode raw
```

## 输入

- `pull_data.py`：只读 Google Sheets 的 43 张 `通途订单YYYYMM` 月表，抽取 8 个楔形枕 SKU 的
  「发货日期 / 通途SKU / 发货数量 / 渠道 / 发货仓库」，输出 `data/wedge_raw.csv` 与 `data/wedge_monthly.csv`。
  **月份归属按发货日期解析**（支持 `YYYY-MM-DD`、`YYYY/M/D`、点号日期、datetime），失败行 `month` 置空并在
  `pull_log.txt` 记 `bad_date`，不会被当作 0 需求。凭证：父仓库 `secrets/gsheets-service-account.json`（不写入仓库）。
- 非法发货数量（空 / 非数字 / 负数 / 非有限值 / 非整数件数）**不再转 0**：行保留，`qty` 留空，
  `qty_status=bad`，`qty_reason` 记原因；`pull_log.txt` 逐月输出 `bad_qty` 与 `bad_reasons`。
- 列对齐：`batch_get` 各列长度可能不同，脚本先取最大长度、短列补 `""` 再逐行处理，
  不静默 `zip` 截断；每张月表记录 `col_mismatch` 与各列 `lengths`。
- 每张月表同时记录 `source_rows`（sheet `row_count`，含表头）、`extracted_rows`（对齐后读取的数据行数）
  与 `blank_tail`（表尾选中列全空的行）。**成功读取≠跨月发货行完整**，这些计数只用于人工核对。
- `backtest.py` 直接读 `wedge_raw.csv`，再次按发货日期聚合，并与 `wedge_monthly.csv` 交叉校验。

## 回测设计（R01/R02 修正）

| 参数 | 默认 | 说明 |
|---|---|---|
| `--label-lag` | 1 | 月份 m 的标签在 m+lag 的 1 日可用；origin t 的决策时点 = t+lag |
| `--min-train` | 18 | 至少 18 个已确认月（observed+zero_confirmed）才生成预测 |
| `--val-start/--val-end` | 2024-12 / 2025-04 | 验证期：用于选择方法；`val_end` 自动钳制到 `test_start − H` |
| `--test-start/--test-end` | 2025-07 / 2026-02 | 测试期：held-out，只报告 |
| `--start/--end` | 2024-06 / 2026-02 | 候选 origin 范围；训练不足的会被丢弃 |
| `--data-end` | 自动 | 最后一张月表月（本次 2026-07）；决定标签可用上限 |
| `--measure` | qty_daneey | `qty_daneey` / `qty_all` |
| `--mode` | censored | `censored` 剔除断货月目标窗 / `raw` 保留 |

**标签可知性（R01）**：label_lag=1 时，2025-07 的销量在 2025-08-01 才知道。
因此验证期最晚 origin 取 2025-04（目标 2025-05..07，最晚可用 2025-08-01），
测试期从 2025-07 起（目标 2025-08..10，决策时点 2025-08-01）。
`results_*.json` 的 `label_overlap_check` 记录验证/测试目标月、交集（必须为空）、
`max_validation_available_at` 与 `min_test_decision_at`，并给出 `pass`。
评估只使用标签已可用的目标月；h 仍为 3，不足时只评可用部分（本次所有单元均 h=3）。

数据状态：每个 SKU-月分为 `observed`、`zero_confirmed`、`pre_launch`（上市前，训练剔除）、
`missing`（月表拉取失败，不补 0、不进训练）、`bad_data`（存在非法数量行，训练与评估都剔除）。
本次 43 张月表全部成功，missing=0、bad_data=0（闸门存在但未被真实坏行触发）。

TSB 初始化（沿用既有实现，不作为新 bug）：`z0 = 非零期数/已确认期数`，
`d0 = 非零需求量均值`（全训练历史），之后非零期 `z=α+(1−α)z, d=αv+(1−α)d`，
零需求期只 `z=(1−α)z`、d 不变，预测 `z·d`，α=0.3。
`backtest.py --self-test` 跑 golden 短序列：
`[0,5,0,10]→4.38046125`、`[3]→3.0`、`[0,0]→0.0`；Croston `[0,5,0,10]→3.25`。

## 输出

- `results_<measure>_<mode>.json`：`design`（切分、钳制记录、丢弃清单）、
  `label_overlap_check`、`data_quality`、`self_test`、`validation`、`test`、
  `combined_reported`，以及 `selection`（验证期选中方法）。
- `data_status.json`：每个 SKU-月的 `status_qty_all` / `status_qty_daneey`、数量与删失标记；
  `data_quality`（bad 行数、逐月 source/extracted 计数、完整性 caveat）、
  月表拉取状态、日期解析失败数、raw vs monthly CSV 不一致数。
  **含逐 SKU 数量，不入库**（由 `backtest.py` 本地生成）。
- `data/pull_log.txt`：逐月读取计数，只含表名与行数，可入库。

结论与限制见 [results.md](results.md)。
