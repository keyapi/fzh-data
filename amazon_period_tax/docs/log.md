---
okf: v0.1
type: Log
title: amazon_period_tax 变更日志
---

# log

## 2026-11-09

- **新增**: Phase3 本地 `run_period_phase3.py` / `phase3_merge.py` / `phase3_gsheet.py`；`PHASE3_SPREADSHEET_ID` 纠正为 Google 表 id（非 Colab notebook）。
- **验证**: 202608–202610 Tax + Phase3 五 worksheet 写回；WFUK 渠道别名对账。

## 2026-11-04

- 新建子项目：Colab「税账期TXT 挂载Gdrive」Tax 主线本地移植（read + df6 + gsheet + 可选 NAS 上传 xlsx）。
