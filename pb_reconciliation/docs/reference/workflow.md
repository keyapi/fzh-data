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

1. 复制上一版对账表 → 改名 `PB Remittance Advice Payment Date 20240430-<最新付款日期>.xlsx`（放在 `给财务\`）。
2. 跑邮件脚本得到当月付款批次（`来自Email Payment Remittance Advice_..._CheckDate ....xlsx`）。
3. 确认发票 CSV 文件夹（钉钉审批后收集的月份文件夹；当月是根目录每日文件夹）。
4. 改脚本顶部常量（`FINANCE_FILE` / `EMAIL_FILE` / `SCAN_FOLDERS` / `REMAP` / `UNPAID_NOTES_FILE`）。
5. `--dry-run` 核对报告 → `--write` 生成时间戳新文件。
6. 对"本轮未付"发票做 UPS 核查（见 ups-delivery-check.md），把结果写成 `unpaid_notes.json`
   供 `UNPAID_NOTES_FILE` 指向，再重新生成。未付张数多时用 `ups_track` 模块批量查（见 §10）。
7. Notes 详细说明用户手写；LibreOffice 重算验证；交付给财务。
8. 合并当月 invoice CSV 交财务（收款附件）：`python merge_invoices.py --month YYYYMM --dry-run` 核对
   逐日小计与 `invoice/*.txt` → `--write` 产出 `<月份文件夹>/PB invoice 合并 YYYYMM.csv`。
   金额口径 = 过滤 `Record Type`(X) = H 后累加 `Invoice Total`(CA)；H+D 一起算会重复。详见 §9。

## 2. 表格列映射

**邮件付款批次 → PB Remittance Advice**：列 A–J 直接复制（A 付款单号、B 付款日期、C 发票号、D PO号、E 发票日期、F 币种、G 发票金额、H 折扣、I 实付金额、J 转账总额），K 写 `=VLOOKUP(C{r},'Invoice to PB'!A:H,2,FALSE)`，L 用于特殊备注（双开票等）。

**发票 CSV → Invoice to PB**：`CSV col i → Excel col i+1`（A..CF 共 84 列），日期保持文本 `MM/DD/YYYY`，`NUMERIC_COLS` 里的列转数字。CG/CH 公式：
- CG（Check Payment Amount）=`=_xlfn.IFNA(VLOOKUP(A{r},'PB Remittance Advice'!C:I,7,FALSE),0)`（IFNA 回退 0）
- CH（Check If Same）=`=CA{r}-CG{r}`（0=对平，≠0=未付/多付）

## 3. 纳入范围（整月口径）

- **锚点** = 基准文件 `Notes!B2`（已入表的最大发票日期），例如 2026-07-13。
- 扫描 `SCAN_FOLDERS` 内所有 `invoice*.csv`（递归，**排除 NotUsed**），按"日文件夹"分组排序。
  **日期 ≤ 锚点的日文件夹跳过**（其发票已在表内），**其余全部纳入**（不管当天有没有付款）= 整月口径。
- 跳过的日文件夹会**逐日校验其发票是否都已在 Invoice to PB 表内**；有不在的就报错退出——
  防止"跳过"变成"漏数"。
- 报告仍逐日打印「发票 N / 已付 / 未付」，方便核对。
- 例：2026-09 用 SCAN_FOLDERS=["202607","202608"]，跳过 0702/0706/0709/0713，纳入 0716 起至 0831。
- 历史规则（2026-08 及以前）是「首个 0 付款的日文件夹即停止」；财务自 2026-09 起要整月，
  故改为上述口径。副作用：未付张数会明显变多（0831 等还没到账期的也算未付），需在 Notes 里写清原因。

## 3b. 扫码硬校验（防静默漏数）

某日 `<日文件夹>/invoice/` 里有 csv、但一个都没匹配上 `invoice*.csv` → **报错退出**并列出目录下所有 csv。
20260730 的文件名把 `invoice` 拼成 `invocie`，递归 glob 静默漏掉 37 张 / $2,232.28，正是本检查的由来。

只看日文件夹的 `invoice/` 一层：`<日文件夹>/878/invoice/` 这类补充子目录不查（其内容与主导出重复，
见 20260727：878 子目录 8 张与当日主导出 100% 交集）。

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

- **openpyxl 写公式无缓存值**：`wb.calculation.fullCalcOnLoad = True` 强制 Excel 打开重算（G2/H2/差额行、K/CG/CH）。
- **样式继承被清空**：先捕获单元格引用再清空单元格，会连带清掉 fill。必须**显式**给区块填色，不靠继承。
- **CSV 数值是文本**：按 `NUMERIC_COLS` 转数字，否则 `SUMIF`/CH 公式把文本当 0。
- **NotUsed 文件夹**：递归 glob 会扫到 `NotUsed/invoice*.csv`（作废/重复），必须排除。
- **发票日期错位**：批次 E 列是 PB 侧发票日期（按 UPS 实际发货确认），**只可能等于或晚于我方 SPS 发票日期，不可能早**；判定按 CSV 侧（SPS 发货日）。
- **PayPal/银行到账 vs 表格**：财务拿对账单查银行流水，表里只做账证一致性。
- **Notes 区块行号不能写死**：未付张数随整月口径暴涨（2026-09 达 87 张），会把「异常」区块推过旧的第 86 行。
  差额行位置必须由 `he + 2 + len(abn_rows)` 动态算出，清空循环上界也跟着走；否则差额会覆盖异常表头。
- **核对 G2/H2 别用 Python 裸加**：`PB Remittance Advice!I` 里有**手写公式单元格**
  （R6779 `=75.65+71.96`、R6788 `=75.65+87.95+75.65`，合计 386.86），
  openpyxl 无缓存值时读到的是公式字符串 → 裸加会正好少 386.86，看上去像「差额对不上」。
  真要核对就用 LibreOffice 重算后再读缓存值（见 §10），或直接用 `--dry-run`/公式口径复算。

## 7. 参数配置（脚本顶部）

| 常量 | 说明 |
|------|------|
| `FINANCE_FILE` | 上一版对账表（只读源；本月是复制上月实发版改名为 `…-20260922.xlsx`） |
| `EMAIL_FILE` | 当月邮件付款批次 |
| `SCAN_FOLDERS` | 待扫描月份/每日文件夹列表（整月口径：锚点之后的日文件夹全纳入） |
| `REMAP` | 双开票映射 `{批次发票号: CSV留用号}` |
| `UNPAID_NOTES_FILE` | 本轮未付发票备注 JSON（发票号 → 备注）；由 UPS 核查产出，缺失视为无备注 |
| `DIFF_NOTE` | 差额说明模板（含历史多付常数 -195 / -32.5） |

## 8. TM 佣金结算表（tm_commission.py）

每月 19-18 号账期给中间人 TM 结算 5% 佣金（英文 Excel）。从给财务表生成：

- **PB Remittance Advice**：过滤 `Payment Date ∈ [账期]`（A-J + K 公式）。
- **Invoice to PB（结转模型）**：发票日范围 = [min(上轮未付结转日, 本账期首个付款日), 本账期最后付款日]（含整天无付款日），**排除上轮已付（已结算）的发票**；上轮未付结转的必须全保留。每周期只发一次，不重复列已结算发票。
- **Notes**：A2-F2 日期、G2/H2 金额、I2=5%、J2=`=H2*I2`、K2 英文说明、E3/F3 Actual PB Payment Start/End（=账期**实际首末付款日**，非边界）、两个未付区块 + Difference。
- **Notes 的日期是两套口径，别填成一样**：
  - **A/B「Invoice To PB Start/End Date」= 我方**操作发货生成 invoice 的日期（SPS 侧）。
  - **C/D「PB Invoice Start/End Date」= PB Remittance Advice 的 Invoice Date**（按 **UPS 实际收到包裹**确认）。
    仓库迟发/漏发会让它明显靠后，**只可能等于或晚于我方日期**；两者常不一致，是正常现象。
    参考 `20260319-20260418.xlsx`：`B2=3/16` 而 `D2=3/18`。
  - **A2 填"本期正常"起点**（剔除上期未付结转的那几张）；结转的日期写进 **A3 备注**，格式
    `plus Nx M/D/YYYY`（多天用 `, ` 连）。例：`20260319-20260418` 的 A3 = `plus 1x 2/12/2026`。
    由 `tm_commission.py` 自动生成，不必手填。
- **未付区块**：`Unpaid in last period, paid in this period`（上轮未付且本账期已付，空时 Total=0 勿写 SUM 空范围）；`Unpaid in this period`（账期内未付，含结转仍未付的，空时 Total=0）。
- **硬校验**：付款总额须与财务确认一致（`EXPECTED`）。
- 关键事实：PB 邮件发票日期（E 列）按 UPS 实际发货确认，只可能等于或晚于我方，不可能早。

## 9. 月度 invoice 合并（merge_invoices.py）

```bash
python merge_invoices.py --month YYYYMM --dry-run   # 报告：逐日 行数/H数/CA合计 vs 该日 invoice/*.txt
python merge_invoices.py --month YYYYMM --write     # -> <月份文件夹>/PB invoice 合并 YYYYMM.csv
```

- 源：`<月份>/<日>/invoice/invoice*.csv` 的**下一层**（不递归 → 变体子目录不纳入）。
- 输出：表头取列数最多的那份（SPS 新版 92 列），全部数据行（H+D）按日升序拼接，右侧补空到全局最大列数，
  UTF-8 带 BOM + CRLF，无引号。规格与 2026-08-24 手工版**逐字节一致**。
- 金额口径：只对 `Record Type` = H 的行累加 `Invoice Total`(CA)。H+D 都算会重复计数。
- 硬校验：日文件夹有 `invoice/` 却没有 `invoice*.csv` 命中 → 报错退出（防文件名错拼被静默漏掉）。
- 已存在同名输出默认不覆盖，改写 `_<时间戳>` 副本；`--force` / `--out` / `--base` 可覆盖行为。

## 10. 未付发票 UPS 批量核查（ups_track 模块）

未付张数多时（整月口径下常态几十张）不要用浏览器逐单点，直接批量查 UPS 官方 Track API。

```bash
# 1) 发票号 -> PO：各日 <日文件夹>/invoice/invoice*.csv 的 H 行（col 2 = PO or Vendor Number）
#    PO -> 跟踪号：同日 shipment*.csv（col 15 = PO #，col 4 = Carrier Tracking）
#    → 写成 ups_input.csv（首列跟踪号，其余列会被 ups_track 拼成备注）
# 2) 批量查询（凭证 UPS_CLIENT_ID/SECRET/UPS_API_ENV=prod，在本仓库父目录 .env 里）
python -m ups_track.cli query --input ups_input.csv --env prod --out ups_result --workers 4
# 3) ups_result.summary.csv -> unpaid_notes.json（发票号 -> "UPS实际发货MM/DD 交付MM/DD 跟踪…"）
```

- 产物放业务数据目录（如 `payment advice\ups_YYYYMMDD\`），**不进仓库**；`UNPAID_NOTES_FILE` 指过去。
- **不要 `source` 整个 `.env`**：里面有一行是 `Key: <值>` 形式，bash 会把值当命令回显到终端。
  用 python 逐行取 `UPS_` 开头即可。
- 判断口径：UPS 状态停在 *"Shipper created a label, UPS has not received the package yet"* =
  **标签建了但仓库从没交运**（2026-09 的 INV…11890 即此例，属无货未发），不是 PB 漏结算。
- 2026-09 实测：87 张未付一次全查成功，86 张已交付、1 张未交运。

## 11. 核对产出文件（LibreOffice 重算）

```bash
soffice --headless --norestore --convert-to xlsx --outdir <out> <产出文件>
```
再用 openpyxl `data_only=True` 读 `out/` 里的缓存值，可拿到 G2 / H2 / 差额行 / 绿黄区块合计的真值。
**注意**：直接读产出文件（未重算）拿不到公式缓存值；且 `I` 列有手写公式单元格，裸加会少 386.86（见 §6）。
