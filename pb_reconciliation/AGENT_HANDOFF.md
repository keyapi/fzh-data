---
okf: v0.1
type: Handoff
title: Pottery Barn (PB) 对账月度更新 — 子项目交接
tags: [pb, potterybarn, reconciliation, remittance, invoice, ups, handoff]
timestamp: 2026-08-14
---

# Pottery Barn (PB) 对账月度更新

> 每月把 PB 的付款和对账数据整理成给财务的对账表，财务拿着它去查银行流水实际到账。本子项目用 `reconcile_pb.py` 自动化大部分工作。

> **先读**：[工作流参考](docs/reference/workflow.md) 和 [UPS 交付核查](docs/reference/ups-delivery-check.md)。
> 本文件是入口：背景、文件位置、运行方式、本次会话成果、交接清单。

## 1. 业务背景

- **客户**：Pottery Barn (PB)，通过 SPS Commerce 系统下单/发货/对账。我们是供应商 Daneey LLC。
- **账期**：PB 按 **UPS 实际发货日**（UPS "We Have Your Package" 日期，即仓库实际交给 UPS 的时间）后约 1 个月付款。PB 系统会看 UPS 跟踪记录确定发货日。
- **结果**：一批订单可能不是同一天发出，PB 按实际发货+账期付款，两边经常错位，一个账期不完全付清有漏掉的；也有 PB 系统故障忘生成账单的情况（需邮件询问投诉）。
- **月度流程**：每月跑脚本拉 PB 邮件付款 → 更新给财务对账表 → 补录发票 CSV → 用 UPS 核查未付原因。

## 2. 文件位置（Windows，均在仓库外）

| 角色 | 路径 |
|------|------|
| 给财务对账表（目标） | `D:\Work\美国\Tracy Miller\PB orders\payment advice\给财务\PB Remittance Advice Payment Date 20240430-YYYYMMDD.xlsx`（每月复制上一版+改名） |
| 邮件付款批次（脚本输出） | `...\payment advice\来自Email Payment Remittance Advice_PaymentDate ..._CheckDate ....xlsx` |
| 发票 CSV | `D:\Work\美国\Tracy Miller\PB orders\YYYYMM\YYYYMMDD\invoice\invoice*.csv`（钉钉审批后收集成月份文件夹；当月未收集时在根目录 `YYYYMMDD\invoice\`） |
| 发货 CSV | `...\YYYYMM\YYYYMMDD\shipment*.csv`（含 PO # 和 Carrier Tracking = UPS 跟踪号） |

## 3. 对账表结构（3 个 sheet）

- **Notes**：汇总起止日期/金额 + 佣金说明 + "上轮未付 本轮已付"/"本轮未付" 两个区块 + 异常 + 差额。
- **PB Remittance Advice**（A1:L*）：收款明细。A 付款单号、B 付款日期、C 发票号、D PO号、E 发票日期、F 币种、G 发票金额、H 折扣、I 实付金额、J 转账总额、K=`VLOOKUP(C,'Invoice to PB'!A:H,2)` 回查发票日期、L 特殊备注。
- **Invoice to PB**（A1:CH*）：发票明细，每张发票 H 头行 + D 明细行。A–CF 与发票 CSV 列 **1:1 映射**（CSV col i → Excel col i+1）。CG="Check Payment Amount"=`_xlfn.IFNA(VLOOKUP(A,'PB Remittance Advice'!C:I,7,FALSE),0)`；CH="Check If Same"=`=CA-CG`（=0 对平，≠0 未付/多付）。

## 4. 运行方式

```bash
cd pb_reconciliation
python reconcile_pb.py --dry-run   # 只读+校验+打印报告（付款/发票/截止/未付清单/双开票映射）
python reconcile_pb.py --write     # 校验通过后写入时间戳新文件（不覆盖源）
```

**下月复用**：改脚本顶部常量——`FINANCE_FILE`（复制+改名上一版）、`EMAIL_FILE`（当月邮件批次）、`SCAN_FOLDERS`（当月文件夹）、`REMAP`（如再遇双开票）、`UNPAID_NOTES`（UPS 核查结果备注）→ 依次 `--dry-run` 看报告 → `--write`。

## 5. 关键逻辑与校验（脚本内，改前必读）

- **截止判定**：按日文件夹日期序扫描发票 CSV，**首个 0 付款的文件夹即停止**（自动）；8 月发票未收集在 `202608` 文件夹时，下月收集后再扫描。
- **不重不漏硬校验**（任一失败即退出不写）：付款批次 vs 现付款表 0 重叠；批次每张发票在 Invoice to PB 能命中（含双开票映射后）；CSV 发票与表内/CSV 相互不重复。
- **颜色**：本轮未付发票黄底（`FFFFFF00`）、之前未付本轮已付绿底（`FF92D050` 浅绿）；Notes 已付区块绿、未付区块黄。脚本按数据推导（绿=批次∩旧表，黄=新加未付）。
- **双开票**：SPS 里一个订单有时创建 2 个 invoice 号，CSV 只保留 1 个，PB 可能付另一个。用 `REMAP` 把付款行发票号改为 CSV 留用号 + L 列备注（例：`INV...1541→1530`，同 PO 137429262）。
- **数值列**：CSV 读到的是文本，`NUMERIC_COLS` 里的列写前转成数字（否则 SUMIF/CH 失效）。
- **发票日期错位**：批次 E 列是 PB 侧日期（按 UPS 实际发货），与 CSV 发货日可能差 1-2 天到数周，属正常。
- **Notes 差额**：`DIFF_NOTE` 模板含历史多付常数（-195、-32.5），自动填本轮未付合计。

## 6. 本次会话成果（2026-08-14）

- 生成 `...20260813_20260814_171350.xlsx`（给财务目录）：
  - 付款追加 507 行（06/04–08/13），发票追加 999 行（202605/06/07 至 0713，487 张）。
  - 25 张上轮未付本轮已付改**绿底**，5 张本轮未付标**黄底**并写 UPS 备注（实际发货/交付/跟踪号）。
  - Notes 两个区块重写、差额更新（H86=-47.56）。
- **5 张未付发票 UPS 核查结论**：不是 PB 漏结算，是我们**迟发**——标签在发货日创建，但包裹 1-7 周后才交给 UPS（07/20–07/30），交付 07/23–08/04 晚于 8/13 账期截止，顺延下账期（~09/13）。详见 [ups-delivery-check.md](docs/reference/ups-delivery-check.md)。
- git：分支 `claude/quirky-thompson-8f788b`，提交 `b77861c` `da494c5` `46f00df` `2465b21`。

## 7. 交接清单（下次/新 Agent 接手）

- [ ] 确认上一版对账表当前日期（PB Remittance 付款截止、Invoice to PB 发票截止）
- [ ] 跑新邮件批次 → 更新 `EMAIL_FILE`、`SCAN_FOLDERS`
- [ ] `--dry-run` 核对报告（付款/发票数、截止文件夹、未付清单、双开票）→ `--write`
- [ ] 对"本轮未付"发票做 UPS 核查（见 reference），把结果填 `UNPAID_NOTES` 重新生成
- [ ] 用户在 Notes 里写详细说明（历史多付、特殊案例、异常）
- [ ] LibreOffice 重算验证公式（G2/H2/H86、CG/CH）
- [ ] 输出文件给财务；提交脚本到分支 → PR
