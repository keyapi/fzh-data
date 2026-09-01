---
okf: v0.1
type: Reference
title: PB 对账表月度更新 — 脚本自动化 + UPS 交付核查
date: 2026-08-14
category: workflow-issues
module: pb_reconciliation
problem_type: workflow_issue
component: excel-automation
severity: medium
applies_when:
  - "每月把 PB 邮件付款批次 + 发票 CSV 整理成给财务的对账表"
  - "判断某批发票未付是迟发（交付晚于账期截止）还是 PB 忘记结算"
  - "openpyxl 批量写 Excel 时公式不重算、样式/数值类型踩坑"
tags: [pb, reconciliation, openpyxl, remittance, invoice, ups, tracking, workflow]
related_components: [pb_reconciliation, finance, ups]
---

# PB 对账表月度更新 — 脚本自动化 + UPS 交付核查

## Context

Pottery Barn (PB) 通过 SPS 系统下单/发货。每月需要把 PB 邮件付款批次 + 各发货日的发票 CSV 整理成给财务的对账表（`D:\Work\美国\Tracy Miller\PB orders\payment advice\给财务\`），财务拿着查银行流水。此前纯手工：复制付款行、补录发票、算差额、核对未付——易错且重复。本次把它做成可复用脚本 `pb_reconciliation/reconcile_pb.py`，并建立 UPS 交付核查流程判断未付原因。

## Guidance

1. **一个可复用脚本 + 顶部常量**。`reconcile_pb.py` 每月只改 `FINANCE_FILE`/`EMAIL_FILE`/`SCAN_FOLDERS`/`REMAP`/`UNPAID_NOTES`，`--dry-run` 看报告 → `--write` 生成时间戳新文件（不覆盖源）。
2. **截止判定按"日文件夹"**。发票 CSV 在 `YYYYMM\YYYYMMDD\invoice\`，扫描时排除 `NotUsed` 子文件夹，按日分组，**首个 0 付款的日文件夹即停止**（8 月发票未收集时在根目录每日文件夹，下月收集后再扫）。
3. **不重不漏硬校验**（任一失败即退出不写）：批次 vs 现付款表 0 重叠；批次每张发票在 Invoice to PB 命中（双开票映射后 100%）；发票与表内/CSV 相互不重复。
4. **双开票映射**。SPS 一个订单有时创建 2 个 invoice 号，CSV 留 1 个、PB 付另一个。用 `REMAP` 把付款行发票号改成 CSV 留用号 + L 列备注（例 `INV...1541→1530`，同 PO 137429262）。
5. **openpyxl 陷阱**：
   - 写公式无缓存值 → `wb.calculation.fullCalcOnLoad = True` 强制重算（Notes G2/H2/H86、K/CG/CH）。
   - 先捕获单元格引用再清空会连带清掉 fill → 显式填色（本轮未付黄 `FFFFFF00`、已付绿 `FF92D050`）。
   - CSV 数值是文本 → `NUMERIC_COLS` 里转数字，否则 SUMIF/CH 把文本当 0。
6. **UPS 交付核查**。批次 E 列是 PB 侧发票日期（按 UPS 实际发货确认，**只可能等于或晚于我方 SPS 发票日期**）。未付发票 → invoice CSV 拿 PO → 日文件夹 `shipment*.csv` 拿 UPS 跟踪号 → 浏览器查 `ups.com/track`（"We Have Your Package" = 仓库实际发货，PB 按此付款）→ 校验交付地址与收货地址一致 → 交付晚于账期截止 = 迟发顺延下账期，非 PB 漏结算。

## Why This Matters

- 对账从"每周几小时手工复制粘贴"降到"改常量 + 两条命令"，且不重不漏校验杜绝重复/遗漏。
- UPS 交付核查能区分**迟发**（顺延下账期，无需催 PB）vs **PB 系统故障漏结算**（需邮件投诉），避免误判或漏催。
- 2026-08 实测：5 张未付发票经 UPS 核查全部是迟发（标签在发货日创建，但包裹 1-7 周后才交给 UPS，交付 07/23–08/04 晚于 8/13 账期截止），不是 PB 漏结算。

## When to Apply

- 每月 PB 对账更新（改常量重跑）。
- 任何"openpyxl 批量写 Excel + 公式/样式/数值"的场景（陷阱通用）。
- 判断外贸客户未付款项是"我们迟发"还是"客户漏付"的核查（UPS/承运商跟踪记录）。

## Examples

```python
# 双开票映射（脚本顶部配置）
REMAP = {"INV0580626000011541": "INV0580626000011530"}

# 本轮未付备注（UPS 核查结果，写入 Notes N 列）
UNPAID_NOTES = {
    "INV0580626000011362": "UPS实际发货07/30 交付08/04 跟踪1ZC0019E0301406005",
}

# 截止判定：首个 0 付款文件夹停止（自动）
# 2026-08 批次覆盖到 0713（全付），0716 起 0 付款 → 截止 0713

# 关键公式
# Invoice to PB CG: =_xlfn.IFNA(VLOOKUP(A2,'PB Remittance Advice'!C:I,7,FALSE),0)
# Invoice to PB CH: =CA2-CG2   (0=对平)
# Notes H86:        =G2-H2     (差额)
```

完整文档见 `pb_reconciliation/AGENT_HANDOFF.md`（交接）与 `pb_reconciliation/docs/`（OKF）。

活动供货价未恢复（另一工作流）：[pb-2025-promo-cost-not-restored.md](pb-2025-promo-cost-not-restored.md)。
