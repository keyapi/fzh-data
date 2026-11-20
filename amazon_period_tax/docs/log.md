---
okf: v0.1
type: Log
title: amazon_period_tax 变更日志
---

# log

## 2026-11-19

- **修复**: 币种字符串先归一化（去零宽/格式字符、NFKC 全角转半角）再和汇率表 join；新增 `find_unmatched_currency()` 对「外币有值但汇率为空」告警。根因：OA 表单币种选项 `匈牙利福林（HUF）` 带 U+200C + 全角括号。
- **回填**: `20260704-20260803`、`20261004-20261103` 两期 AllegroHU 相关单元格（汇总/原始/人民币/收款比例×2）逐格回填并复读校验，未整表重写。

## 2026-11-11

- **修复**: Tax 汇率合并改用每个收款币种一行，`enrich_with_fx` 按收款币种去重。重写 `Tax202608` 396,601.69、`Tax202609` 292,240.89、`Tax202610` 192,773.60。

## 2026-11-09

- **新增**: Phase3 本地 `run_period_phase3.py` / `phase3_merge.py` / `phase3_gsheet.py`；`PHASE3_SPREADSHEET_ID` 纠正为 Google 表 id（非 Colab notebook）。
- **验证**: 202608–202610 Tax + Phase3 五 worksheet 写回；WFUK 渠道别名对账。

## 2026-11-04

- 新建子项目：Colab「税账期TXT 挂载Gdrive」Tax 主线本地移植（read + df6 + gsheet + 可选 NAS 上传 xlsx）。
