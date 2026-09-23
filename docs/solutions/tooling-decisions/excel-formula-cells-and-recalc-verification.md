---
okf: v0.1
type: Reference
title: Excel 交付物金额核对——公式单元格与 LibreOffice 重算
date: 2026-09-23
category: tooling-decisions
module: pb_reconciliation
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - "用 openpyxl 读一个含公式的 xlsx 去核对金额/合计"
  - "要验证脚本写出的 xlsx 表单里的 SUMIF/VLOOKUP 是否算对"
  - "数据列里混有手写公式单元格（历史人工补录）"
tags:
  - openpyxl
  - libreoffice
  - xlsx
  - recalc
  - formula-cache
---

# Excel 交付物金额核对——公式单元格与 LibreOffice 重算

## Context

本仓库交付物很多是 xlsx：PB 对账表、TM 佣金表、赛狐各种导入文件、报表导出。
脚本用 openpyxl 写文件，人要拿它对账，所以"脚本算的数"和"Excel 打开后显示的数"
必须一致——**核对方式本身**就容易出错。

2026-09 在 PB 对账上踩了坑：用 Python 裸加 `PB Remittance Advice!I` 列去核对
`Notes!H2 = SUM('PB Remittance Advice'!I:I)`，算出 $602,319.52，
而 LibreOffice 重算得到 $602,706.38，**正好差 386.86**。
一度据此推断"表里有个 386.86 的历史差额对不上"，是错的。

## Guidance

### 1. openpyxl 读公式单元格拿到的是公式，不是值

```python
ws.cell(r, 9).value          # -> '=75.65+71.96'   （公式字符串）
ws.cell(r, 9).value          # data_only=True 时才返回缓存值
```

`data_only=True` **只在文件被 Excel / LibreOffice 保存过**时才有缓存值。
openpyxl 自己写出来的文件**没有**缓存值——`data_only=True` 返回 `None`。

### 2. 数据列里可能混着手写公式单元格

PB 表的 `I` 列有两行是人工补录的公式：

| 单元格 | 内容 | 值 |
|---|---|---|
| `I6779` | `=75.65+71.96` | 147.61 |
| `I6788` | `=75.65+87.95+75.65` | 239.25 |
| | | **386.86** |

`isinstance(v, (int, float))` 过滤会把它们全部丢掉 → 裸加**正好少 386.86**。
这个数不大不小、看着像"一笔历史差额"，很容易被误读成业务问题。

**先找出公式单元格，再决定怎么处理**：

```python
formulas = [r for r in range(2, ws.max_row + 1)
            if isinstance(ws.cell(r, col).value, str)
            and str(ws.cell(r, col).value).startswith("=")]
```

### 3. 核对产出文件：先 LibreOffice 重算，再读缓存值

```bash
soffice --headless --norestore --convert-to xlsx --outdir <out> <产出文件>
```

```python
wb = openpyxl.load_workbook(f"{out}/<文件>", data_only=True)   # 拿到的才是真值
```

脚本写文件时会设 `wb.calculation.fullCalcOnLoad = True`，
LibreOffice 打开即重算，转换出来的副本就带上了缓存值。
这是本仓库唯一可靠的"脚本产出 → 人看到的数"验证路径
（`pb_reconciliation/visual_check.py` 走的是同一套 LibreOffice 渲染）。

### 4. 口径先定死，再谈数字

同一张表里多个列/行代表不同口径，加错就是错：

- **行口径**：`Record Type` = `H` 是头行、`D` 是明细行。H+D 一起加会重复计数。
- **列口径**：PB 表 `I` = 实付金额（`Payment Amount`）；`J` = 该付款单号的**转账总额**，
  同一单号下每行都是同一个值，直接 `sum(J)` 会成倍放大。要按单号去重后再加。
- **条件**：`SUMIF` 的判据列（`X` 列）和求和列（`CA` 列）要对准。

## Why This Matters

- 核对方法本身出错，会得出**貌似有据的错误结论**。这次差点让用户去查一个不存在的历史差额。
- 与真实业务问题难以区分：386.86 这种量级完全像"一笔漏付款"，
  但它是"两个单元格是公式"这个纯技术事实。
- 差异点稳定复现（上个月也是 386.86）更容易让人确信是业务问题——恰恰相反，
  稳定的差通常意味着**系统性口径/工具问题**，而不是偶发的业务异常。

## When to Apply

- 用 openpyxl 读含公式的 xlsx 做任何金额核对。
- 要证明脚本产出的 SUMIF / VLOOKUP / 差额公式算得对。
- 数据列里有历史人工补录的行（这类行最可能写成公式）。

## Examples

**错（裸加，少 386.86）**

```python
h2 = sum(pws.cell(r, 9).value for r in range(2, pws.max_row + 1)
         if isinstance(pws.cell(r, 9).value, (int, float)))
# -> 602319.52   ✗
```

**对（LibreOffice 重算后读缓存值）**

```bash
soffice --headless --norestore --convert-to xlsx --outdir /tmp/recalc <产出.xlsx>
```
```python
nws = openpyxl.load_workbook("/tmp/recalc/<产出>.xlsx", data_only=True)["Notes"]
nws["G2"].value     # 607521.38
nws["H2"].value     # 602706.38
nws["H148"].value   # 4815.00  = G2-H2，与文字说明 -227.50 + 5042.50 一致 ✔
```

顺带验证了另一件事：**差额公式与文字说明本来就该相等**，
所以"两者不等"本身就是"我读错了"的信号，而不是"业务有历史差额"。

## Related

- [扫描类脚本防"静默丢数"](../best-practices/scanner-silent-data-loss-guard.md) —— 同一轮排查的另一个学习
- [PB 对账表月度更新](../workflow-issues/pb-reconciliation-monthly-update.md) —— 实例来源；§4f 有同样的核对步骤
- `pb_reconciliation/visual_check.py` —— 同一套 LibreOffice 渲染路径，用于视觉自查
