---
okf: v0.1
type: Reference
title: 月度订单 xlsx → 固定 Google Sheet 月度 ws（patch 写入）
description: 把月度成品 xlsx 写回「通途订单YYYYMM」的「YYYY年M月订单」ws：复制-归档-只覆盖变化列；含与旧 Colab 写法的对比与 API 限制说明
tags: [gsheet, gspread, tongtu, monthly, upload, reference]
resource: tongtool_order_cost/scripts/upload_monthly_order_sheet.py
---

# 月度订单 xlsx → 固定 Google Sheet 月度 ws

## 背景 / 约定

- 电子表格：`通途订单YYYYMM`（如 `通途订单202607`）
- 月度固定 ws：`YYYY年M月订单`（如 `2026年7月订单`），**位置固定在 `YYYY年M月FBA订单` 左侧**（Colab 依赖）
- 每月更新方式：把「GS再次上传 …（已替换 `物流商运费`）」的成品写回该 ws；旧 ws 归档为
  `弃用YYYY年M月订单 YYYYMMDD`（**不删除历史**）
- **不要动** `写回*` 系列 ws（由后续 Colab 处理）

## 用法（脚本）

```bash
export GSPREAD_SERVICE_ACCOUNT_FILE='<父仓库>/secrets/gsheets-service-account.json'
export PYTHONPATH=tongtool_order_cost

# 只看计划（不改动）
uv run python tongtool_order_cost/scripts/upload_monthly_order_sheet.py \
    --xlsx "D:\Work\王忠于\成本核算\GS再次上传 …20260911.xlsx" --month 202607 --dry-run

# 执行：复制旧 ws → 归档 → 只覆盖「物流商运费」列 → 回读校验
uv run python tongtool_order_cost/scripts/upload_monthly_order_sheet.py \
    --xlsx "…20260911.xlsx" --month 202607
```

可选：`--sheet/--ws`（默认由 `--month` 推导）、`--columns`（默认 `物流商运费`，可逗号多列）、
`--archive`、`--chunk`（默认 5000 行/次）。
`--in-place`：目标 ws 名与位置已正确、只需覆盖列时，**不复制/不归档**，直接覆盖该 ws 的指定列（本次 202607 即用此模式）。

> 写法对比与官方限制出处见 [research/2026-09-11-gsheet-write-efficiency.md](../research/2026-09-11-gsheet-write-efficiency.md)：
> 官方**无硬上限、建议 payload ≤2MB**；读写 300/min/项目、60/min/用户；batch 计 1 次；请求原子。

## 为什么这样做（vs 旧 Colab 写法）

旧 Colab（`20250409 合并en成本 …` notebook）的写法：
- 读：自家 `gsheet2df`（`get_all_values`）；单表批量读用 `values_batch_get(UNFORMATTED_VALUE)`（这点已是最佳实践）
- 写：`ws.clear()` → `ws.update(all_values, value_input_option='USER_ENTERED')` **一次性整表写**

对**大表**这套有两个问题：
1. **体积**：Sheets API `values.update` 单请求上限约 **10 MB**；本表 9604×91 ≈ **87 万格**，整表一般超限或极易失败，所以要么分批（中途表不完整）、要么改用服务端方案。
2. **clear-then-write 有丢数据窗口**：`clear()` 后到 `update` 成功前，表是空的；中途失败 = 数据没了。

本脚本（patch 模式）改为：
- **`duplicate_sheet(old_id, insert_sheet_index=old.index)`**：服务端瞬时复制旧 ws（保留格式、批注、数据验证、人工编辑），且**天然留在原索引**（FBA 左侧）
- 旧 ws 改名归档（不删除）
- **只覆盖要变的列**（默认 1 列 ≈ 9.6k 格，单次 `update(RAW)` 即可），不触碰其它列与人工改动
- 回读校验（行数/表头/数值列合计）

### 若确实要“整表替换”（多列都变）
最接近手工「文件 → 导入」的 API 做法是**服务端转换 + 拷贝**：
Drive 把 xlsx 转成临时 Google 表格 → `spreadsheets.sheets.copyTo` 把那张 sheet 拷进目标表 → 改名/定索引 → 删临时表。
一次服务端操作、无中间态，也避免逐格写入；代价是依赖 `google-api-python-client`（当前脚本未实现，需要时再补）。

## 安全提醒

- 旧 Colab notebook 把 service account 私钥**明文写在 cell 0**（`credentials = {…"private_key":…}`）。文件在 Google Drive 内流转，建议改用 Colab Secrets / 环境变量存放，并考虑轮换该 SA 密钥。
- 本地统一用 `secrets/gsheets-service-account.json`（gitignore）+ 环境变量 `GSPREAD_SERVICE_ACCOUNT_FILE` 指向父仓库路径；worktree 内没有该文件。

## 校验 / 失败处理

- 表头与 xlsx 不一致 → 直接拒绝（防错列错表）
- `写回*` ws → 直接拒绝
- `--dry-run` 打印「变化行数」（数值按归一化比较，避免 `0` vs `0.0`、千分位误报）
