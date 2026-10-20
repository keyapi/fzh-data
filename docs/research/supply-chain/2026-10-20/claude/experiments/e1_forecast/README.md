---
okf: v0.1
type: Reference
title: E1 预测基线回测 — 复现说明（修正版）
description: 数据拉取与回测命令、修正后的数据状态口径、训练/验证/测试切分与输出说明
date: 2026-10-20
tags: [supply-chain, forecasting, experiment, readme, revised]
---

# E1 预测基线回测 — 复现

```bash
cd docs/research/supply-chain/2026-10-20/claude/experiments/e1_forecast
uv run python pull_data.py
uv run python backtest.py --measure qty_daneey --mode censored
uv run python backtest.py --measure qty_all    --mode censored
uv run python backtest.py --measure qty_daneey --mode raw
```

## 输入

- `pull_data.py`：只读 Google Sheets 的 43 张 `通途订单YYYYMM` 月表，抽取 8 个楔形枕 SKU 的
  「发货日期 / 通途SKU / 发货数量 / 渠道 / 发货仓库」，输出 `data/wedge_raw.csv` 与 `data/wedge_monthly.csv`。
  **月份归属按发货日期解析**（支持 `YYYY-MM-DD`、`YYYY/M/D`、点号日期、datetime），失败行 `month` 置空并在
  `pull_log.txt` 记 `bad_date`，不会被当作 0 需求。凭证：父仓库 `secrets/gsheets-service-account.json`（不写入仓库）。
- `backtest.py` 直接读 `wedge_raw.csv`，再次按发货日期聚合，并与 `wedge_monthly.csv` 交叉校验。

## 回测设计（2026-10-20 修正）

| 参数 | 默认 | 说明 |
|---|---|---|
| `--min-train` | 18 | 至少 18 个已确认月（observed+zero_confirmed）才生成预测 |
| `--val-start/--val-end` | 2024-12 / 2025-06 | 验证期：用于选择方法 |
| `--test-start/--test-end` | 2025-07 / 2026-02 | 测试期：held-out，只报告 |
| `--start/--end` | 2024-06 / 2026-02 | 候选 origin 范围；训练不足的会被丢弃 |
| `--measure` | qty_daneey | `qty_daneey` / `qty_all` |
| `--mode` | censored | `censored` 剔除断货月目标窗 / `raw` 保留 |

数据状态：每个 SKU-月分为 `observed`、`zero_confirmed`、`pre_launch`（上市前，训练剔除）、
`missing`（月表拉取失败，不补 0、不进训练）。本次 43 张月表全部成功，missing=0。

TSB：z=需求概率、d=非零需求均值；非零期 `z=α+(1−α)z, d=αv+(1−α)d`，零需求期只 `z=(1−α)z`，d 不变；
预测 `z·d`，α=0.3。Croston：仅在非零期更新规模与间隔，间隔含零需求月、不含 missing。

## 输出

- `results_<measure>_<mode>.json`：`design`（含丢弃的 origin/SKU-原点清单）、
  `validation`、`test`、`combined_reported` 三段指标，以及 `selection`（验证期选中方法）。
- `data_status.json`：每个 SKU-月的 `status_qty_all` / `status_qty_daneey`、数量与删失标记；
  月表拉取状态、日期解析失败数、raw vs monthly CSV 不一致数。
  **含逐 SKU 数量，不入库**（由 `backtest.py` 本地生成）。

结论与限制见 [results.md](results.md)。
