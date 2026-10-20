---
okf: v0.1
type: Reference
title: E1 预测基线回测 — 复现说明
description: 数据拉取与回测命令、输入输出、口径与断货删失说明
date: 2026-10-20
tags: [supply-chain, forecasting, experiment, readme]
---

# E1 预测基线回测 — 复现

```bash
cd docs/research/supply-chain/2026-10-20/claude/experiments/e1_forecast
uv run python pull_data.py
uv run python backtest.py --measure qty_daneey --mode censored
```

- `pull_data.py`：只读 Google Sheets 的 43 张 `通途订单YYYYMM` 月表，抽取 8 个楔形枕 SKU 的
  「发货日期 / 通途SKU / 发货数量 / 渠道 / 发货仓库」，输出 `data/wedge_raw.csv` 与 `data/wedge_monthly.csv`。
  凭证：父仓库 `secrets/gsheets-service-account.json`（不写入仓库）。
- `backtest.py`：滚动原点回测（h=3），支持 `--measure qty_daneey|qty_all` 与 `--mode censored|raw`；
  断货月定义见 `results.md` §2。
- 输出：`results_<measure>_<mode>.json`。

结论与限制见 [results.md](results.md)。
