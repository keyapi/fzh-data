---
okf: v0.1
type: Reference
title: PB 对账月度工作流参考
tags: [pb, reconciliation, workflow, columns, formulas]
timestamp: 2026-08-14
resource: ../reconcile_pb.py
---

# PB 对账月度工作流参考

## 1. 月度步骤

1. 复制上一版对账表 → 改名 `PB Remittance Advice Payment Date 20240430-<最新付款日期>.xlsx`。
2. 跑邮件脚本得到当月付款批次（`来自Email Payment Remittance Advice_..._CheckDate ....xlsx`）。
3. 确认发票 CSV 文件夹（钉钉审批后收集的月份文件夹；当月是根目录每日文件夹）。
4. 改脚本顶部常量（`FINANCE_FILE` / `EMAIL_FILE` / `SCAN_FOLDERS` / `REMAP` / `UNPAID_NOTES`）。
5. `--dry-run` 核对报告 → `--write` 生成时间戳新文件。
6. 对"本轮未付"发票做 UPS 核查（见 ups-delivery-check.md），更新 `UNPAID_NOTES` 重新生成。
7. Notes 详细说明用户手写；LibreOffice 重算验证；交付给财务。

## 2. 表格列映射

**邮件付款批次 → PB Remittance Advice**：列 A–J 直接复制（A 付款单号、B 付款日期、C 发票号、D PO号、E 发票日期、F 币种、G 发票金额、H 折扣、I 实付金额、J 转账总额），K 写 `=VLOOKUP(C{r},'Invoice to PB'!A:H,2,FALSE)`，L 用于特殊备注（双开票等）。

**发票 CSV → Invoice to PB**：`CSV col i → Excel col i+1`（A..CF 共 84 列），日期保持文本 `MM/DD/YYYY`，`NUMERIC_COLS` 里的列转数字。CG/CH 公式：
- CG（Check Payment Amount）=`=_xlfn.IFNA(VLOOKUP(A{r},'PB Remittance Advice'!C:I,7,FALSE),0)`（IFNA 回退 0）
- CH（Check If Same）=`=CA{r}-CG{r}`（0=对平，≠0=未付/多付）

## 3. 截止判定

- 扫描 `SCAN_FOLDERS` 内所有 `invoice*.csv`（递归，**排除 NotUsed** 子文件夹），按"日文件夹"分组排序。
- 从最早一天开始，检查该天发票是否出现在付款批次（`REMAP` 后）；**首个 0 付款的日文件夹及其后全部停止**。
- 例：2026-08 批次覆盖到 0713（全付），0716 起 0 付款 → 截止 0713。

## 4. 不重不漏硬校验（任一失败即退出不写）

1. 付款批次发票号 ∩ 现付款表 = 空（付款不重）。
2. 批次每张发票 ∈ (旧表 ∪ 新加)（付款不漏，双开票映射后必须 100% 命中）。
3. 新加发票 ∩ 旧表 = 空；同一发票不出现在多个 CSV 文件（发票不重）。
4. 全部纳入文件夹读入、发票数符合预期。

## 5. 颜色约定

| 颜色 | 值 | 含义 |
|------|-----|------|
| 黄 | `FFFFFF00` | 本轮未付 |
| 绿（浅） | `FF92D050` | 之前未付，本轮已付 |

- Invoice to PB：黄/绿标在 H 头行的 27 个信息列（`FILL_COLS`）。
- Notes：已付区块（上轮未付本轮已付）绿底、未付区块（本轮未付）黄底、异常无填充。
- 颜色由数据推导：绿 = 批次∩旧表；黄 = 新加未付。

## 6. 关键陷阱（踩过）

- **openpyxl 写公式无缓存值**：`wb.calculation.fullCalcOnLoad = True` 强制 Excel 打开重算（G2/H2/H86、K/CG/CH）。
- **样式继承被清空**：先捕获单元格引用再清空单元格，会连带清掉 fill。必须**显式**给区块填色，不靠继承。
- **CSV 数值是文本**：按 `NUMERIC_COLS` 转数字，否则 `SUMIF`/CH 公式把文本当 0。
- **NotUsed 文件夹**：递归 glob 会扫到 `NotUsed/invoice*.csv`（作废/重复），必须排除。
- **发票日期错位**：批次 E 列是 PB 侧发票日期（按 UPS 实际发货确认），**只可能等于或晚于我方 SPS 发票日期，不可能早**；判定按 CSV 侧（SPS 发货日）。
- **PayPal/银行到账 vs 表格**：财务拿对账单查银行流水，表里只做账证一致性。

## 7. 参数配置（脚本顶部）

| 常量 | 说明 |
|------|------|
| `FINANCE_FILE` | 上一版对账表（只读源） |
| `EMAIL_FILE` | 当月邮件付款批次 |
| `SCAN_FOLDERS` | 待扫描月份/每日文件夹列表 |
| `REMAP` | 双开票映射 `{批次发票号: CSV留用号}` |
| `UNPAID_NOTES` | 本轮未付发票备注（UPS 核查结果） |
| `DIFF_NOTE` | 差额说明模板（含历史多付常数） |

## 8. TM 佣金结算表（tm_commission.py）

每月 19-18 号账期给中间人 TM 结算 5% 佣金（英文 Excel）。从给财务表生成：

- **PB Remittance Advice**：过滤 `Payment Date ∈ [账期]`（A-J + K 公式）。
- **Invoice to PB**：发票日范围 = [首个有付款的发票日, 最后一个]（**含整天无付款日**）；取范围内 H 行发票号的**全部 H/D 行**（勿只按日期过滤，D 行日期列为空）。
- **Notes**：A2-F2 日期、G2/H2 金额、I2=5%、J2=`=H2*I2`、K2 英文说明、E3/F3 Actual PB Payment Start/End（=账期首末付款日）、两个未付区块 + Difference。
- **未付区块**：`Unpaid in last period, paid in this period`（上轮 TM 文件未付且本账期已付，空时 Total=0 勿写 SUM 空范围）；`Unpaid in this period`（范围内未付）。
- **硬校验**：付款总额须与财务确认一致（`EXPECTED`）。
- 关键事实：PB 邮件发票日期（E 列）按 UPS 实际发货确认，只可能等于或晚于我方，不可能早。

