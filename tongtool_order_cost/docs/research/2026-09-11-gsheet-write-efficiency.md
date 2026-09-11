---
okf: v0.1
type: Research
title: Google Sheet 大批量写入：旧 Colab 写法 vs 现行更优做法（2026-09 调研）
description: 对比 clear+整表 update 与「只写变化列 / 服务端 copy / Drive 转换导入」，附官方限制与配额出处，给出月表更新的推荐方案
tags: [gsheet, gspread, sheets-api, performance, research]
resource: tongtool_order_cost/scripts/upload_monthly_order_sheet.py
---

# Google Sheet 大批量写入调研（2026-09-11）

## TL;DR 结论

- **单/少列更新**（本项目月表实际场景）：**只写变化的列**（`values.update`，RAW）最省、最快，1 次写请求、远小于建议体积。
- **整表替换**（多列都变 / 整月重导）：**服务端复制**最优 —— `duplicate_sheet`（同文件内复制）或 **Drive 转换 xlsx→Google 表格 + `spreadsheets.sheets.copyTo`**（跨文件整表拷入），而不是 `clear()`+整表 `values.update`。
- **读**：`values_batch_get(UNFORMATTED_VALUE)` 批量读（旧 Colab cell#19 已经是这个写法，属最佳实践）。
- 避免 **`clear()` 后再写**：虽然单请求是原子的，但 clear 与 update 是**两次请求**，中间是空表窗口，失败即丢数据。

## 官方事实（2026-09 核实）

| 事实 | 出处 |
|---|---|
| Sheets API **无硬性请求体积上限**，但官方**建议 payload ≤ 2 MB**；单请求处理超 **180s** 会超时 | [Usage limits](https://developers.google.com/workspace/sheets/api/limits) |
| 读写配额均 **300/分钟/项目**、**60/分钟/用户/项目**；配额每分钟回填，超限 429，建议指数退避 | 同上 |
| **batch 请求（含子请求）只计 1 次**；配额内无每日上限 | 同上 |
| **所有请求原子应用**：任一部分非法则整体失败、不产生任何更改 | 同上 |
| **2026 起：超出配额请求拟按 Google Cloud 计费**（常规使用仍免费） | 同上 |
| `spreadsheets.sheets.copyTo`：把一个 sheet 拷到**另一个电子表格**，返回新 sheet 属性；计入 1 次写请求 | [copyTo](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.sheets/copyTo) / [python 库文档](https://developers.google.com/resources/api-libraries/documentation/sheets/v4/python/latest/sheets_v4.spreadsheets.sheets.html) |
| Drive 上传可**转换**为原生 Google 表格：创建文件时指定 `mimeType=application/vnd.google-apps.spreadsheet`（v3 用 MIME 驱动转换；v2 为 `convert=true`） | [Manage uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads) |
| Apps Script `setValues` 在数据量变大后会超时；改用 Sheets 高级服务（`batchGet`+`update`/batch）明显更快 | [SO: setValues timing out](https://stackoverflow.com/questions/75899518/google-script-using-setvalues-timing-out) |

> 注：社区常见的「10 MB 硬上限」**非官方口径**（官方是“无硬上限、建议 2 MB”）。实际写入仍建议按 ≤2MB 分块或改为服务端复制。

## 写法对比

| 方案 | 请求数/体积 | 空窗/风险 | 适用 |
|---|---|---|---|
| 旧 Colab：`clear()` + 整表 `update(USER_ENTERED)` | 2 次；87 万格 → 远超 2MB 建议 | **有**：clear 后为空的窗口，失败丢数据 | 小表可；大表不宜 |
| `values.update(RAW)` 分批 | N 次（按 ≤2MB 分块） | 无空窗（直接覆盖），但**中途表不完整**（外部读到会不完整） | 通用兜底 |
| `values.batchUpdate` 多范围一次 | 1 次（体积受限） | 无 | 分散多段的少量改动 |
| **`duplicate_sheet` + 只补变化列**（本项目采用） | 复制=1 次；补列=1..N 次（<2MB） | 无 | **同月固定格式、只改少数列** ✅ |
| **Drive 转换 + `sheets.copyTo`** | 转换=1 次上传；copyTo=1 次 | 无（服务端整表拷入） | 整表替换/多列大变 ✅ |
| `gspread_dataframe.set_with_dataframe` | 底层仍是一次 `values.update` | 同 values.update | 便捷封装，不解决体积 |
| Apps Script `setValues` | —— | 大数据易超时 | Colab 内的替代，不优于 API |

## 对本项目月表的推荐（已固化）

- 日常：`scripts/upload_monthly_order_sheet.py` —— `duplicate_sheet`（留原索引，FBA 左侧）+ 归档旧 ws + **只覆盖变化列**（默认 `物流商运费`）+ 回读校验。
- 何时 `--in-place`：目标 ws 名与位置已正确、只需覆盖列、不想产生新 ws/归档时（本分支已支持）。
- 何时改用 copyTo（未实现，按需加）：某月多列同时变化 / 想“像手工导入一样整表替换”。实现路径 = Drive 把 xlsx 转临时 Google 表格 → `sheets.copyTo` 到目标表 → 改名/定索引 → 删临时表。

## 注意

- 配额按**用户**计：service account 算 1 个用户（60 写/分钟）；批处理时别用多线程狂发。
- 2026 起超配额可能计费；本项目量级（每月 1~2 次写入）远低于配额。
