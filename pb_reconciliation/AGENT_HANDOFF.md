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

**下月复用**：改脚本顶部常量——`FINANCE_FILE`（复制+改名上一版）、`EMAIL_FILE`（当月邮件批次）、`SCAN_FOLDERS`（当月文件夹）、`REMAP`（如再遇双开票）、`UNPAID_NOTES_FILE`（UPS 核查产出的备注 JSON）→ 依次 `--dry-run` 看报告 → `--write`。

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
- **硬校验**：付款总额须与财务确认一致（`EXPECTED`）。跨期合并结算时，`EXPECTED` 填两期之和。
- 2026-08-14 已生成：`PB Remittance Advice Payment Date 20260519-20260618.xlsx`（佣金 $709.29）、`...20260619-20260718.xlsx`（佣金 $442.14）、合并 `...20260519-20260718.xlsx`（佣金 $1,151.42）。
- **2026-09-24 已生成（两期合并）**：`...20260719-20260918.xlsx` —— 付款 508 行 / **$29,193.28**
  （= 07/19-08/18 $13,068.54 + 08/19-09/18 $16,124.74，财务已查银行流水确认到账），
  **佣金 $1,459.66**；发票区间 2026-06-09..2026-08-17；上轮未付结转 1 张已付（$34.99）、本账期未付 11 张（$700.40）。
  自洽校验：`G2 − H2 = 29,893.68 − 29,193.28 = 700.40` = 未付合计。
  注：合并成一个 `PERIODS` 条目即可（脚本按账期逐条出文件），无需要分别出两期再合并。

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

## 4e. 未付发票 UPS 批量核查（ups_track 模块）

整月口径下未付常有几十张，**不要**用浏览器逐单点，用 `ups_track` 批量查 UPS 官方 Track API。

```bash
# 做法：invoice*.csv 的 H 行（col 2 = PO）→ shipment*.csv（col 15 = PO #，col 4 = Carrier Tracking）
#       → ups_input.csv（首列跟踪号）→ 查询 → summary.csv 转 unpaid_notes.json
python -m ups_track.cli query --input ups_input.csv --env prod --out ups_result --workers 4
```

- 产物放业务数据目录（如 `payment advice\ups_YYYYMMDD\`），**不进仓库**；`UNPAID_NOTES_FILE` 指过去。
- 凭证 `UPS_CLIENT_ID` / `UPS_CLIENT_SECRET` / `UPS_API_ENV=prod` 在本仓库**父目录** `.env`。
  **不要 `source` 整个 `.env`**——里面有一行是 `Key: <值>` 形式，bash 会把值当命令回显出来；
  用 python 逐行取 `UPS_` 开头的键即可。
- 判定：UPS 停在 *"Shipper created a label, UPS has not received the package yet"* = **建了标签但仓库从没交运**
  （2026-09 的 INV…11890 即此，属无货未发），不是 PB 漏结算。

## 4f. 核对产出文件（LibreOffice 重算）

```bash
soffice --headless --norestore --convert-to xlsx --outdir <out> <产出文件>
```
再用 openpyxl `data_only=True` 读 `out/` 缓存值，拿到 G2 / H2 / 差额行 / 绿黄区块合计的真值。
**注意**：直接读未重算的产出文件拿不到公式缓存值，而 `I` 列有手写公式单元格，裸加会少 386.86（见 §5）。

## 5. 关键逻辑与校验（脚本内，改前必读）

- **纳入范围（整月口径）**：锚点 = 基准文件 `Notes!B2`（已入表的最大发票日期）。日期 ≤ 锚点的日文件夹**跳过**
  （并逐日校验其发票都已在表内，否则报错），其余**全部纳入**，不管当天有没有付款。
  2026-08 及以前是「首个 0 付款即停」；财务自 2026-09 起要整月，故改口径，未付张数因此明显变多。
- **扫描硬校验**：某日 `<日文件夹>/invoice/` 有 csv 但无一匹配 `invoice*.csv` → 报错退出并列出目录下所有 csv。
  （20260730 的 `invocie` 拼写曾让 37 张 / $2,232.28 被静默漏掉。）只看日文件夹的 `invoice/` 一层，
  `<日文件夹>/878/invoice/` 这类补充子目录不查（与主导出重复）。
- **不重不漏硬校验**（任一失败即退出不写）：付款批次 vs 现付款表 0 重叠；批次每张发票在 Invoice to PB 能命中（含双开票映射后）；CSV 发票与表内/CSV 相互不重复。
- **颜色**：本轮未付发票黄底（`FFFFFF00`）、之前未付本轮已付绿底（`FF92D050` 浅绿）；Notes 已付区块绿、未付区块黄。脚本按数据推导（绿=批次∩旧表，黄=新加未付）。
- **双开票**：SPS 里一个订单有时创建 2 个 invoice 号，CSV 只保留 1 个，PB 可能付另一个。用 `REMAP` 把付款行发票号改为 CSV 留用号 + L 列备注（例：`INV...1541→1530`，同 PO 137429262）。
- **数值列**：CSV 读到的是文本，`NUMERIC_COLS` 里的列写前转成数字（否则 SUMIF/CH 失效）。
- **发票日期错位**：批次 E 列是 PB 侧发票日期（按 UPS 实际发货确认），**只可能等于或晚于我方 SPS 发票日期，不可能早**，属正常。
- **Notes 区块行号必须动态算**：未付张数整月口径下达 87 张，旧代码把差额行写死在 R86 会被挤爆。
  现用 `diff_row = he + 2 + len(abn_rows)` 推导，清空循环上界同步。
- **Notes 差额**：`DIFF_NOTE` 模板含历史多付常数（-195、-32.5），自动填本轮未付合计。
  2026-09 实测 `差额 = -227.50 + 5042.50 = 4815.00`，与公式 `=G2-H2` 重算值一致。
- **核对 G2/H2 的坑**：`PB Remittance Advice!I` 有 2 个手写公式单元格（R6779/R6788，合计 386.86），
  openpyxl 无缓存值时读到公式字符串 → Python 裸加会正好少 386.86，误以为「差额对不上」。
  要核对就用 LibreOffice 重算后再读（见 §4f）。

## 6. 最近一次会话成果（2026-09-23，付款日截至 09/22）

- 基准 = 上月实发版 `…20240430-20260813_差5单未付 20260814_171350.xlsx`，复制改名为
  `…20240430-20260922.xlsx`；产出 `…20240430-20260922_20260923_164417.xlsx`（给财务目录）。
- 新批次 377 张 / $21,170.25（付款日 08/17–09/22）；纳入发票 **459 张 / 930 行**（202607 剩余 + 全部 202608 至 0831）。
- 上月 5 张未付**全部已付**（1507/1521/1528/1535 付于 08/18，1362 付于 08/20）→ 绿标；
  本轮未付 **87 张 / $5,042.50** → 黄标 + UPS 备注。差额 `-227.50 + 5042.50 = 4815.00`，与 `=G2-H2` 重算一致。
- **87 张未付一次全查 UPS**（`ups_track` + 官方 Track API）：86 张已交付、1 张未交运。
  未付多是因为整月口径 + 账期滞后（28 张 SPS 08/24→实际 08/25 发货，PB 约 09/24 才付；0827/0831 的 58 张更在下个账期）。
- **INV0580626000011890 是特例**：UPS 显示"建了标签但从未收件"——实为**无货未发**（11 月中到货，未定是否继续发），
  钉钉 8 月底已提交，暂不处理，Notes 里写文字备注即可。
- **顺带修复两处历史遗留**：
  1. `20260730\invoice\invocie x37 ….csv` 改名 → `invoice x37 ….csv`（拼写错误已被 glob 静默漏掉 37 张）。
  2. 重跑 `merge_invoices.py --month 202607 --write --force`：230 张 / $13,182.52 → **267 张 / $15,414.80**，
     9 天小计与各自 `invoice/*.txt` 全部对上；旧文件留证为 `PB invoice 合并 202607 缺37张作废.csv`（需重发给财务）。
- **脚本改造**：整月纳入口径 + 锚点跳过已入表文件夹（带校验）、`invoice/` 无 `invoice*.csv` 硬校验、
  Notes 差额行动态定位、`UNPAID_NOTES` → `UNPAID_NOTES_FILE`（JSON 侧载）。
- 核查过程中的教训：用 Python 裸加 `PB Remittance Advice!I` 核对 H2 会少 386.86（2 个手写公式单元格），
  一度误判「差额对不上」；必须用 LibreOffice 重算后读缓存值（§4f）。

## 7. 交接清单（下次/新 Agent 接手）

- [ ] 确认上一版对账表当前日期（PB Remittance 付款截止、Invoice to PB 发票截止 = 锚点 `Notes!B2`）
- [ ] 跑新邮件批次 → 更新 `EMAIL_FILE`、`SCAN_FOLDERS`；把上月实发版复制改名为 `…-<最新付款日期>.xlsx` 当 `FINANCE_FILE`
- [ ] `--dry-run` 核对报告（付款/发票数、跳过与纳入的日文件夹、未付清单、双开票）→ `--write`
- [ ] 对"本轮未付"发票做 UPS 批量核查（§4e），产出 `unpaid_notes.json` 指给 `UNPAID_NOTES_FILE`，重新生成
- [ ] 用户在 Notes 里写详细说明（历史多付、特殊案例、异常）
- [ ] LibreOffice 重算验证（§4f）：G2 / H2 / 差额行 / CG / CH
- [ ] 输出文件给财务；合并当月 invoice（`merge_invoices.py --month YYYYMM --write`）一并给财务
- [ ] 提交脚本与文档到分支 → PR
