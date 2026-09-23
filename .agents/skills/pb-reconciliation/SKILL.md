---
name: pb-reconciliation
description: >
  Pottery Barn (PB) 对账月度更新。每月把 PB 邮件付款批次 + 发票 CSV 整理成
  给财务的对账表，校验不重不漏，并用 UPS 批量核查未付原因（迟发 / PB 漏结算 / 我们没发货）。
  当用户提到"PB对账"、"Pottery Barn 对账"、"remittance"、"payment advice"、
  "给财务"、"付款转账"、"对账单"、"Invoice to PB"、"PB Remittance Advice"、
  "未付发票"、"UPS 交付核查"、"We Have Your Package"、"TM 佣金"、"Tracy Miller"、
  "PB invoice 合并"等时触发。
  不要用于 OSTKUS / Wayfair / Walmart 账期对账（那是 platform-account-reconciliation）。
compatibility: >
  需要 openpyxl, pandas。从 pb_reconciliation/ 目录运行，Windows 中文路径。
  数据文件在仓库外 D:\Work\美国\Tracy Miller\PB orders\。
  UPS 批量核查用 ups_track 模块（官方 Track API），凭证在父仓库 .env。
metadata:
  module: pb_reconciliation
  scripts: reconcile_pb.py, tm_commission.py, merge_invoices.py, visual_check.py
  updated: 2026-09-23
---

# Pottery Barn (PB) 对账月度更新

每月把 PB 付款和对账数据整理成给财务的对账表（PB 收款对账），并给中间人 TM 出 5% 佣金结算表。
数据文件在仓库外 `D:\Work\美国\Tracy Miller\PB orders\`（对账表在 `payment advice\给财务\`）。

## 新对话必读

1. `pb_reconciliation/AGENT_HANDOFF.md` —— 唯一默认入口（背景 / 文件位置 / 运行 / 交接清单）
2. `pb_reconciliation/docs/reference/workflow.md` —— 月度步骤、列映射、校验、陷阱
3. `pb_reconciliation/docs/reference/ups-delivery-check.md` —— 未付原因判定（迟发 vs PB 漏结算）
4. 已解决坑：`docs/solutions/workflow-issues/pb-reconciliation-monthly-update.md`
5. 扫目录取输入的通用防线：`docs/solutions/best-practices/scanner-silent-data-loss-guard.md`
6. 核对 Excel 产出金额：`docs/solutions/tooling-decisions/excel-formula-cells-and-recalc-verification.md`

## 快速启动

```bash
cd pb_reconciliation
python reconcile_pb.py --dry-run   # 给财务表：只读+校验+打印报告
python reconcile_pb.py --write     # 生成时间戳新文件（不覆盖源）
python tm_commission.py --dry-run  # TM 佣金表：只读+报告+付款总额硬校验
python tm_commission.py --write    # 生成 To Tracy Miller 账期文件
python merge_invoices.py --month YYYYMM --dry-run   # 月度 invoice 合并（给财务的收款附件）
```

每月复用：改脚本顶部常量（`FINANCE_FILE` 上一版、`EMAIL_FILE` 当月邮件批次、
`SCAN_FOLDERS` 发票文件夹、`REMAP` 双开票映射、`UNPAID_NOTES_FILE` UPS 备注 JSON）→
`--dry-run` 核对报告 → `--write`。TM 佣金：改 `PERIODS`/`EXPECTED`/`PREV_SOURCE`。

## 关键点

- **表结构**：Notes / PB Remittance Advice（付款）/ Invoice to PB（发票，H 头行 + D 明细行）。
- **纳入范围 = 整月口径**（2026-09 起）：锚点 = 基准文件 `Notes!B2`（已入表的最大发票日期）；
  锚点之前的日文件夹跳过（并逐日校验发票都已在表内，否则报错），其余全部纳入——不再「首个 0 付款即停」。
  财务要整月，代价是未付张数变多（还没到账期的也算）。
- **扫码硬校验**：`<日文件夹>/invoice/` 里有 csv 却无一匹配 `invoice*.csv` → 报错退出。
  20260730 曾把 `invoice` 拼成 `invocie`，静默漏掉 37 张 / $2,232.28，还连带丢掉整个 202608。
- **不重不漏硬校验**：批次 vs 现表 0 重叠、批次每张发票可命中（双开票映射后）、发票无重复。
- **颜色**：本轮未付黄底 `FFFFFF00`，之前未付本轮已付绿底 `FF92D050`。
- **双开票**：SPS 一单 2 个 invoice 号，CSV 留 1 个、PB 付另一个 → `REMAP` 把付款行发票号改成留用号 + L 列备注。
  对账核对时要用它归一化，否则会误报「漏记」。
- **对账单 vs 台账双向核对**：正向逐条对齐（发票号+付款日+金额）、反向行数相等、
  完整性（该账期内除「无货未发/迟发」外不应还有未付）。这是回答财务「截至某账期应付是否已付」的依据。
- **未付核查走 `ups_track` 批量**（官方 Track API，不是浏览器逐单）：
  invoice CSV H 行拿 PO → `shipment*.csv` 拿跟踪号 → 查「We Have Your Package」（仓库实际发货日，PB 按此付款）。
  交付晚于账期截止 = 迟发顺延；停在 "Shipper created a label, UPS has not received the package yet" = 我们没发货。
- **openpyxl 陷阱**：`fullCalcOnLoad` 强制重算；显式填色（勿靠样式继承）；CSV 数值列转数字；
  Notes 区块行号必须动态算（未付多时会把「异常」区块推下去，写死行号会被差额覆盖）。

## 相关 skill

- 平台账期对账（OSTKUS / Wayfair / Walmart）：`platform-account-reconciliation`
- UPS/FedEx/GLS 统一跟踪：`parcel-track`、`ups-track`、`fedex-track`、`gls-track`
