---
okf: v0.1
type: Index
title: E1 本地数据目录
description: 原始与月度 CSV 的生成方式；数据文件不入库；拉取日志含逐月读取审计计数
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

`pull_log.txt` 只含月表名、读取计数、坏数量计数与列长度，不含客户/员工信息，可入库。
每行包含：

- `source_rows`（sheet `row_count`，含表头）/ `extracted_rows`（对齐后读取的数据行数）/ `blank_tail`；
- `hits`（目标 SKU 且日期非空的行）、`empty_date`、`bad_date`；
- `bad_qty` 与 `bad_reasons`（empty / non_numeric / negative / non_finite / non_integer_pieces）；
- `col_mismatch` 与各列 `lengths`。

这些计数只证明月表被完整读取，**不能证明跨月发货行完整**。
