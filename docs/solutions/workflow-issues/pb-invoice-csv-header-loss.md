---
okf: v0.1
type: Reference
title: PB invoice CSV 摘单后丢了表头 —— 行筛选必须保留第 1 行，并用程序断言
date: 2026-10-29
category: workflow-issues
module: pb_orders
problem_type: workflow_issue
component: tooling
severity: medium
applies_when:
  - "从 PB 批次 invoice CSV 里摘掉无货单的 H+D 行"
  - "用脚本按行过滤/改写 CSV，之后要交给财务或做月度合计"
  - "下游会用 pandas 默认 header=0 读这份 CSV"
tags: [pb, invoice, csv, header, byte-faithful, pandas, verification]
related_components: [pb_orders, pb_reconciliation]
---

# PB invoice CSV 摘单后丢了表头

## Problem

2026-10-19 批次打单后发现 1 单无货，按惯例要从当批 `invoice x31 …csv` 里摘掉该 PO 的
H+D 两行。清理脚本为了从数据行开始扫描，写成了 `i = 1`（跳过表头），把保留行 append 到
`keep`，最后 `"".join(keep)` 写回 —— **表头行从未加入 `keep`**。当时的校验只数了 H/D
行数与 H 行总额（30 张 / 2,048.14 都对），因此交付时没有发现。

## Symptoms

- 两周后月度审计用 pandas 默认 `header=0` 读这份文件：**第一行数据被当成列名**，
  第一张剩余票凭空消失 → 报告「29 张 / $2,013.15」「有 2 张 $34.99 被剔」。
- 实际只剔了 1 张；文件真实内容 30 张 / $2,048.14，与 txt 完全一致。
- 巧合放大了误导：第一张剩余票与被删票**金额相同**（都是 $34.99），看起来像删了两张。

## What Didn't Work

- **只校验 H/D 行数与 H 行总额** —— 丢表头不影响这两个数，校验必过。
- **按文件名 `x30` 判断张数** —— 文件名是对的，但文件结构已经坏了。
- **用 D 行总额求和校验** —— SPS 的 D 行会重复整票总额（一票多明细时 `H ≠ ΣD` 是正常），
  不能当结构校验。
- **相信审计工具的「2 张被剔」结论** —— 审计脚本同样被缺表头骗了，不能当事实。

## Solution

1. 从 `NotUsed/` 的原始 31 张 CSV 取表头字节，原样补回当前文件（数据行不动）：
   ```python
   header = orig_bytes.partition(b"\n")[0]
   cur.write_bytes(header + b"\n" + cur_bytes)
   ```
2. 把缺表头的那版复制到 `NotUsed/invoice x30 …（缺表头）….csv` 留证。
3. 重新断言：首格是 `Invoice Number`、30 张、总额 2,048.14 = txt、数据行与
   「原始 − 被删票」逐行相等。
4. 顺带扫全 10 月 9 个批次：表头与参照表头一致、无 BOM/CRLF、张数 = 文件名 `xN`、
   金额 = txt；**只有 10/19 中招**。

## Why This Works

- 摘单只应改「数据行集合」；表头是文件契约的一部分。逐行筛选 + 原样写回，是既不重新
  序列化、又能保持其余字节不变的做法。
- 金额校验有盲区：**两张同额票会让「总数正确」与「少一张」同时成立**。
- 结构校验必须独立于业务数值：首行身份、行列数、H→D 成组关系。

## Prevention

**写回模板**（表头永远先放进 `keep`）：

```python
keep = [lines[0]]          # 表头
for i in range(1, len(lines)):
    ...
    keep.append(lines[i])
```

**交付前用程序断言**（不是目测）：

1. `rows[0][0].strip() == "Invoice Number"`，且与源文件表头**逐字节相等**；
2. `len(data) == H + D`；文件名 `xN == H 数`；
3. `sum(H 行 Invoice Total) == txt 文件名金额`；
4. 有 `NotUsed` 原件时：`current_rows == [r for r in orig.body if invoice not in removed]`；
5. 无 BOM、无 CRLF。

**下游读文件**（审计/对账脚本）先判表头：若首格像 `INV…` 而不是 `Invoice Number`，
说明文件缺表头，应按 `header=None` 读并立即报警 —— 别让 pandas 静默吃掉第一行。

**别把正常现象当异常**：D 行比 H 行多是「一票多明细」；SPS 的 D 行重复整票总额，
不要用 `ΣD` 做校验。

## Related

- `pb_orders/docs/reference/stockout-closed-loop.md` §2 第 1 步（invoice 惯例与核验）
- `.agents/skills/pb-orders/SKILL.md`（铁律与相关经验）
- `docs/solutions/workflow-issues/pb-out-of-stock-notification-and-zero-stock-orders.md`
