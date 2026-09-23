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

## 4b. TM 佣金结算表（To Tracy Miller）

每月 19-18 号账期按 PB 到账的 **5%** 给中间人 TM 结算佣金，发全英文 Excel。

```bash
cd pb_reconciliation
python tm_commission.py --dry-run   # 只读+报告+硬校验（付款总额 vs 财务确认）
python tm_commission.py --write     # 生成 To Tracy Miller 目录账期文件
```

- 数据源：给财务表（过滤账期付款 + 按天截止发票）。`FINANCE_FILE`/`PERIODS`/`EXPECTED`/`PREV_SOURCE` 在脚本顶部。
- **Invoice to PB 结转模型**：发票范围 = [min(上轮未付结转日, 本账期首个付款日), 本账期最后付款日]（含整天无付款日），**排除上轮已付（已结算）发票**；上轮未付结转全保留。每周期只发一次，不重复列已结算发票。
- 未付区块：上轮未付本轮已付、本轮未付（含结转仍未付，空时 Total 0）。
- **硬校验**：付款总额须与财务确认一致（当前账期：05/19-06/18 = $14,185.71，06/19-07/18 = $8,842.75）。
- 2026-08-14 已生成：`PB Remittance Advice Payment Date 20260519-20260618.xlsx`（佣金 $709.29）、`...20260619-20260718.xlsx`（佣金 $442.14）、合并 `...20260519-20260718.xlsx`（佣金 $1,151.42）。

## 4c. 视觉自查（visual_check.py）

非多模态模型（如 deepseek-v4-flash）下，用项目视觉模型自查 Excel 渲染格式：
```bash
set DASHSCOPE_API_KEY=sk-...   # 或 AI_API_KEY（sk-or-v1- 走 OpenRouter）
python visual_check.py <xlsx> [sheet名] ["自定义提示"]
```
渲染 sheet → PNG → qwen-vl-plus 描述背景色/字体/换行/截断。需 openai 包 + LibreOffice + PyMuPDF。**API key 不提交 git，需会话环境变量**。

## 4d. 月度 invoice 合并（merge_invoices.py）

每月把 `YYYYMM\YYYYMMDD\invoice\invoice*.csv` 拼成**一个**文件交给财务，作为 PB 收款对账附件。

```bash
cd pb_reconciliation
python merge_invoices.py --month 202608 --dry-run   # 只读+报告+校验
python merge_invoices.py --month 202608 --write     # 输出 <月份文件夹>/PB invoice 合并 <月份>.csv
```

- **规格**（逆向自 2026-08-24 手工产出，逐字节复现）：表头取列数最多的那份（SPS 新版 92 列）；
  数据行 = 各日 CSV 的**全部**行（H 头行 + D 明细行都保留，不筛选不去重），按日文件夹日期升序拼接；
  每行补齐到全局最大列数；UTF-8 带 BOM + CRLF。
- **为什么 H+D 都留**：文件是给人看/存档的明细；**算金额时**必须过滤 `Record Type` = H 再累加
  `Invoice Total`(CA)，H+D 一起算会重复（见根目录《Pottery Barn 收款附件 invoice csv文件 累加金额操作 202403.docx》）。
  脚本报告就是这个口径。
- **只扫 `invoice/` 下一层**：`invoice/截至YYYYMMDD尚未取消/` 之类的**变体子目录**天然不纳入
  （如 20260814 里"去掉无货的…x17"那份），避免同一批发票重复进文件。
- **硬校验**：某日文件夹有 `invoice/` 子目录、但一层内没有任何 `invoice*.csv` 命中 → 报错退出并列出目录下
  所有 `.csv`。**踩过的坑**：`20260730` 的文件名把 `invoice` 拼成 `invocie`，被 glob 静默漏掉，
  当月合并文件少了 37 张 / $2,232.28——不报错的静默丢弃比报错贵得多。
- **交叉核对**：每天与 `invoice/*.txt` 文件名里的小计（人手写的当日合计）比对，打印 `txt ✔ / ✘`。
- 已存在同名输出时**默认不覆盖**，改写 `_<时间戳>` 副本（`--force` 覆盖；`--out` 指定路径；
  `--base` 指向副本做回归验证）。

## 5. 关键逻辑与校验（脚本内，改前必读）

- **截止判定**：按日文件夹日期序扫描发票 CSV，**首个 0 付款的文件夹即停止**（自动）；8 月发票未收集在 `202608` 文件夹时，下月收集后再扫描。
- **不重不漏硬校验**（任一失败即退出不写）：付款批次 vs 现付款表 0 重叠；批次每张发票在 Invoice to PB 能命中（含双开票映射后）；CSV 发票与表内/CSV 相互不重复。
- **颜色**：本轮未付发票黄底（`FFFFFF00`）、之前未付本轮已付绿底（`FF92D050` 浅绿）；Notes 已付区块绿、未付区块黄。脚本按数据推导（绿=批次∩旧表，黄=新加未付）。
- **双开票**：SPS 里一个订单有时创建 2 个 invoice 号，CSV 只保留 1 个，PB 可能付另一个。用 `REMAP` 把付款行发票号改为 CSV 留用号 + L 列备注（例：`INV...1541→1530`，同 PO 137429262）。
- **数值列**：CSV 读到的是文本，`NUMERIC_COLS` 里的列写前转成数字（否则 SUMIF/CH 失效）。
- **发票日期错位**：批次 E 列是 PB 侧发票日期（按 UPS 实际发货确认），**只可能等于或晚于我方 SPS 发票日期，不可能早**，属正常。
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
- [ ] 输出文件给财务；合并当月 invoice（`merge_invoices.py --month YYYYMM --write`）一并给财务
- [ ] 提交脚本到分支 → PR
