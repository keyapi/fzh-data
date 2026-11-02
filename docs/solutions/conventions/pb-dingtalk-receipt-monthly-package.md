---
okf: v0.1
type: Reference
title: PB 月度钉钉销售收款确认单——日行 + 日 CSV，月合并只当最后附件
date: 2026-11-02
category: conventions
module: pb_reconciliation
problem_type: convention
component: tooling
severity: medium
applies_when:
  - "每月替运营交 Pottery Barn 的钉钉销售收款确认单"
  - "新财务要一个月合并的 invoice CSV"
  - "纠结月度合计要不要写成表单里的一行"
tags: [pb, dingtalk, oa, invoice, merge, convention]
---

# PB 月度钉钉销售收款确认单：日行 + 日 CSV，月合并只当最后附件

## Context

PB（Pottery Barn）账期按 UPS 实发日后约一个月、一周两结（常见周一/周四）。运营每月在钉钉「销售收款确认单」交一组日行：平台新平台、账户 PotteryBarnUS、收款 CENTRADE 对公、归属美国公司、币种美元，销售额 = 当天 `invoice*.csv` 的 H 行 Invoice Total，费用占比 0、回款率 1；「账期明细」挂当天那份 CSV（`invoice/` 一层，不用 `NotUsed`）。

2026-10 起财务还要一份**整月合并 CSV**（与 `YYYYMM/PB invoice 合并 YYYYMM.csv` 同规格）。合并金额是给财务看的附件，**不是表单里多出来的一行**。

## Guidance（本学习沉淀的做法）

1. **表单只写账期日行**。一行一个结日；不要加「月合计」行。回款额已经按日拆开，合计让财务用合并 CSV 自己加（H 行 Invoice Total）。
2. **附件顺序**：各日 `invoice*.csv`（按账期日升序）→ **最后一份** `PB invoice 合并 YYYYMM.csv`。
3. **先收进月份文件夹再合并**。`merge_invoices.py --month YYYYMM` 只扫 `<PB orders>/<YYYYMM>/<YYYYMMDD>/invoice/invoice*.csv`。日文件夹还在根目录时先归进 `YYYYMM/`（与 9 月目录同结构），再 `--dry-run` 对 txt，再 `--write`。
4. **金额口径三边一致**：各日 H 行合计 = 各日 txt 文件名小计 = 合并文件 H 行合计。去无货单后，用的是 `invoice/` 里那份已剔除文件，不是 `NotUsed` 里的原件。
5. **读 CSV 必须认表头**。缺表头时把第一张票当列名丢掉，且若那张票金额碰巧等于被剔除的无货单，会误报「多删了一张」。程序侧：首行 `Record Type` 或 `Invoice Number` 才当表头；否则整文件当数据。摘单事故正文在 PR #297 的 `pb-invoice-csv-header-loss.md`，不要在这里重写。
6. **提交窗**：账期自然月对应 4 号～下月 3 号那桶。例如 10 月账期在 10/4–11/3 交。同一内容上一张若已撤销（`TERMINATED`）才能重交。

## Why This Matters

- 新财务要整月一份文件做收款附件，但核算仍按「一行一个账期日期」。把月合计写进表单会和 Amazon/其它平台的一行一账期口径打架，也会让「销售额」被算两次。
- 合并文件垫底，DRM/财务从钉钉一单就能下齐「按日原件 + 整月拼件」，不必再找网盘。

## When to Apply

- 每月 PB 钉钉收款确认单。
- 用户说「再交一份月合并 CSV / 不要填月度总金额」。
- 日文件夹刚从 `PB orders/YYYYMMDD` 收到 `PB orders/YYYYMM/`。

## Examples

```text
# 日文件夹已在 YYYYMM/ 下
uv run python pb_reconciliation/merge_invoices.py --month 202610 --dry-run
uv run python pb_reconciliation/merge_invoices.py --month 202610 --write
# → <PB orders>/202610/PB invoice 合并 202610.csv
```

表单示例结构（金额来自各日 H 行，不是合并文件多写一行）：

| 账期日期 | 平台 | 账户 | 币种 | 销售额 |
|---------|------|------|------|--------|
| 该月各结日 | 新平台 | PotteryBarnUS | 美元(USD) | 当日 CSV H 合计 |

附件：`invoice xN <日>_….csv` × N，最后 `PB invoice 合并 YYYYMM.csv`。

## Related

- 合并脚本与规格：`pb_reconciliation/AGENT_HANDOFF.md` §4d、`pb_reconciliation/merge_invoices.py`
- 用 API 发起（权限 / OSS PUT / 撤销后再交）：`docs/solutions/integration-issues/dingtalk-oa-create-receipt-with-attachments.md`
- 摘单丢表头：PR #297 `docs/solutions/workflow-issues/pb-invoice-csv-header-loss.md`
- 对账月度更新：`docs/solutions/workflow-issues/pb-reconciliation-monthly-update.md`
