---
name: gsheet-monthly-order
description: >
  把月度成品 xlsx（如「GS再次上传 通途非FBA订单YYYYMM …」）写回固定 Google Sheet 的月度 ws
  （如「通途订单202607」的「2026年7月订单」），归档旧 ws 为「弃用…」、只覆盖变化列、
  保证 ws 留在 FBA 表左侧。当用户提到"上传到 gsheet"、"写回 gsheet"、"更新 2026年X月订单"、
  "弃用旧 ws"、"通途订单2026XX 的月度 ws"、"Colab 要读的订单表"等时触发。
compatibility: >
  需 gspread；凭证 secrets/gsheets-service-account.json（父仓库，gitignore），
  用环境变量 GSPREAD_SERVICE_ACCOUNT_FILE 指过去。脚本在 tongtool_order_cost/scripts/。
metadata:
  module: tongtool_order_cost
  spreadsheet: 通途订单YYYYMM
  worksheet: YYYY年M月订单
  archive: 弃用YYYY年M月订单 YYYYMMDD
  script: tongtool_order_cost/scripts/upload_monthly_order_sheet.py
  doc: tongtool_order_cost/docs/reference/gsheet-monthly-sheet-upload.md
  updated: 2026-09-11
---

# 月度订单 ws 上传（GSheet）

## 用法

```bash
export GSPREAD_SERVICE_ACCOUNT_FILE='<父仓库>/secrets/gsheets-service-account.json'
export PYTHONPATH=tongtool_order_cost
uv run python tongtool_order_cost/scripts/upload_monthly_order_sheet.py --xlsx "<xlsx>" --month 202607 --dry-run
uv run python tongtool_order_cost/scripts/upload_monthly_order_sheet.py --xlsx "<xlsx>" --month 202607
# 只要覆盖列、不复制/不归档：
uv run python tongtool_order_cost/scripts/upload_monthly_order_sheet.py --xlsx "<xlsx>" --month 202607 --in-place
```

## 硬规则

1. **不要 `clear()` 整表**：用「复制旧 ws → 归档 → 只覆盖变化列（默认 `物流商运费`）」。
2. **旧 ws 只归档不删除**：`弃用<ws> <YYYYMMDD>`；重名自动加 `(2)`。
3. **表头必须与 xlsx 一致**（不一致直接拒绝，防错列）。
4. **不要动 `写回*` ws**（后续 Colab 处理）；脚本已内置拒绝。
5. **位置**：新 ws 用 `duplicate_sheet(insert_sheet_index=old.index)` 留原位（`YYYY年M月FBA订单` 左侧）。
6. **先 `--dry-run`** 看「变化行数」（数值归一化比较，避免 `0/0.0`、千分位误报）。
7. 写后**回读校验**（行数/表头/列合计）。

## 为什么不用旧 Colab 的整表 clear+update

整表 ~87 万格会超 Sheets API 单请求体积上限（约 10 MB），且 clear 后有丢数据窗口。
只覆盖变化列体积小、无空窗、且保留人工编辑。详见
[tongtool_order_cost/docs/reference/gsheet-monthly-sheet-upload.md](../../../tongtool_order_cost/docs/reference/gsheet-monthly-sheet-upload.md)。
