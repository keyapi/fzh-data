---
okf: v0.1
type: Reference
title: PB 对账表月度更新 — 脚本自动化 + UPS 交付核查
date: 2026-08-14
last_updated: 2026-09-23
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

1. **一个可复用脚本 + 顶部常量**。`reconcile_pb.py` 每月只改 `FINANCE_FILE`/`EMAIL_FILE`/`SCAN_FOLDERS`/`REMAP`/`UNPAID_NOTES_FILE`，`--dry-run` 看报告 → `--write` 生成时间戳新文件（不覆盖源）。
2. **纳入范围按"日文件夹"**。发票 CSV 在 `YYYYMM\YYYYMMDD\invoice\`，扫描时排除 `NotUsed` 子文件夹，按日分组。2026-09 起改为**整月口径**：锚点（上一版 `Notes!B2` = 已入表的最大发票日期）之前的日文件夹跳过（并逐日校验发票都已在表内），其余全部纳入——不再"首个 0 付款即停"。财务要整月，代价是未付张数变多（还没到账期的也算）。
2b. **扫码要有硬校验**。`<日文件夹>/invoice/` 里有 csv 却无一匹配 `invoice*.csv` 就报错退出。20260730 曾把 `invoice` 拼成 `invocie`，glob 静默漏掉 37 张 / $2,232.28——静默丢弃比报错贵得多。只看日文件夹 `invoice/` 一层，`<日文件夹>/878/invoice/` 这类补充子目录与主导出重复，不查。
3. **不重不漏硬校验**（任一失败即退出不写）：批次 vs 现付款表 0 重叠；批次每张发票在 Invoice to PB 命中（双开票映射后 100%）；发票与表内/CSV 相互不重复。
4. **双开票映射**。SPS 一个订单有时创建 2 个 invoice 号，CSV 留 1 个、PB 付另一个。用 `REMAP` 把付款行发票号改成 CSV 留用号 + L 列备注（例 `INV...1541→1530`，同 PO 137429262）。
5. **openpyxl 陷阱**：
   - 写公式无缓存值 → `wb.calculation.fullCalcOnLoad = True` 强制重算（Notes G2/H2/H86、K/CG/CH）。
   - 先捕获单元格引用再清空会连带清掉 fill → 显式填色（本轮未付黄 `FFFFFF00`、已付绿 `FF92D050`）。
   - CSV 数值是文本 → `NUMERIC_COLS` 里转数字，否则 SUMIF/CH 把文本当 0。
6. **UPS 交付核查（批量，不用浏览器）**。批次 E 列是 PB 侧发票日期（按 UPS 实际发货确认，**只可能等于或晚于我方 SPS 发票日期**）。未付发票 → invoice CSV 的 H 行拿 PO（col 2）→ 同日 `shipment*.csv` 拿 UPS 跟踪号（col 15 = PO #，col 4 = Carrier Tracking）→ 用 `ups_track` 模块走官方 Track API **一次批量查**（87 张约 1 分钟）。"We Have Your Package" = 仓库实际发货，PB 按此付款；交付晚于账期截止 = 迟发顺延下账期，非 PB 漏结算。
7. **"对账单 vs 台账"双向核对（每次必做）**。PB 邮件里的 remittance advice 是**对账单**，我们的 `PB Remittance Advice` 表是**台账**，两边必须逐条对齐：
   - **正向**：对账单每一条（发票号 + 付款日 + 金额）都要在台账里找到完全一致的一行 —— 证明 PB 声明付的我们都记了。
   - **反向**：台账在该账期内的付款行数要等于对账单条数 —— 证明没有多记。
   - **完整性**：该账期内 SPS 发票日的发票里，除了"无货未发/迟发"这类已知原因，不应还有未付 —— 证明没有"该付没付"。
   - 唯一允许的正向失配是**双开票**：对账单上是被弃用的号（如 `INV...1541`），台账按留用号（`INV...1530`）记，两边同日期同金额。核对时要用 `REMAP` 归一化再比，否则会误报"漏记"。
   - 这套核对能一次性回答"截至某账期 PB 应付是否已付"，是给财务的口径依据（2026-09 实测：两个账期 0 差异）。

## Why This Matters

- 对账从"每周几小时手工复制粘贴"降到"改常量 + 两条命令"，且不重不漏校验杜绝重复/遗漏。
- UPS 交付核查能区分**迟发**（顺延下账期，无需催 PB）vs **PB 系统故障漏结算**（需邮件投诉），避免误判或漏催。
- 2026-08 实测：5 张未付发票经 UPS 核查全部是迟发（标签在发货日创建，但包裹 1-7 周后才交给 UPS，交付 07/23–08/04 晚于 8/13 账期截止），不是 PB 漏结算。
- 2026-09 实测：改整月口径后未付 87 张，改用 `ups_track` + UPS 官方 Track API **一次批量查完**（86 已交付 / 1 未交运），不再浏览器逐单。唯一异常是无货未发的 INV0580626000011890（我方原因）。另修掉两处历史遗留：20260730 拼写文件改名、202607 合并文件从 230 张补到 267 张。
- **核对金额的坑**：`PB Remittance Advice!I` 里有手写公式单元格（R6779/R6788，合计 386.86），用 openpyxl 无缓存值读法 Python 裸加会正好少这个数，看上去像"差额对不上"。要核对就用 LibreOffice 重算后读缓存值。详见 [Excel 交付物金额核对](../tooling-decisions/excel-formula-cells-and-recalc-verification.md)。
- **扫码防静默丢弃**是通用模式，不止 PB 用；沉淀在 [扫描类脚本防"静默丢数"](../best-practices/scanner-silent-data-loss-guard.md)。
- 2026-09 "对账单 vs 台账"双向核对实测：账期 2026-07-19~08-18（221 张 / $13,068.54）与 2026-08-19~09-18（287 张 / $16,124.74）**均 0 差异**；前者唯一的正向失配是双开票 `INV...1541`（台账按 `INV...1530` 记），确认不是漏记。

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
