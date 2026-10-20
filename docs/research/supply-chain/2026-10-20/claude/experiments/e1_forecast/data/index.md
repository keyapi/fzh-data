---
okf: v0.1
type: Index
title: E1 本地数据目录
description: 原始与月度 CSV 的生成方式；数据文件不入库
date: 2026-10-20
tags: [supply-chain, forecasting, experiment, data]
---

# E1 本地数据目录

`wedge_raw.csv` 与 `wedge_monthly.csv` 含 SKU 级发货明细，**不入库**（仓库规则禁止提交数据文件）。

重新生成：

```bash
cd ..
uv run python pull_data.py
```

`pull_log.txt` 只含月表名与命中行数，可入库。
