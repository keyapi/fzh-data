---
okf: v0.1
type: Reference
title: 账期 Tax 必须用「每个收款币种一行」的汇率表，别名拆开表会把税额乘多遍
date: 2026-11-11
category: integration-issues
module: amazon_period_tax
problem_type: integration_issue
component: tooling
severity: high
symptoms:
  - "Tax{YYYYMM} 人民币合计约为 Colab「账号Tax汇总」的两倍出头"
  - "同一批 txt、同一列汇率，本地 run_period_tax 与 Colab df6 对不上"
root_cause: wrong_fx_table
resolution_type: code_fix
tags: [amazon-period, tax, exchange-rate, gspread]
---

# 账期 Tax：别名拆开的汇率表不能按收款币种合并

## Problem

`load_exchange_rate_table` 返回两张表：第一张每个收款币种一行；第二张把「货币别名」拆开，同一 `收款币种` 出现多行（USD/EUR 为 2，SEK/CAD 等为 4）。`run_period_tax.py` 曾把第二张交给 `enrich_with_fx`，而合并键是 `收款币种`。一行结算明细配上多行汇率，Tax 人民币被加了多遍。

## Symptoms

2026-11-11 用同一批桶内 txt 对照：

| 月份 | 别名表合并（已写入过 GSheet 的旧数） | 每个币种一行 |
|------|--------------------------------------|--------------|
| 202608 | 793,981.68 | 396,601.69 |
| 202609 | 585,746.89 | 292,240.89 |
| 202610 | 385,647.58 | 192,773.60 |

396,601.69 × 2 = 793,203.38，与 793,981.68 差 778.30。差额来自别名个数不是一律为 2 的币种（SEK、CAD 为 4）。Colab「税账期」notebook 合并的是未拆开的汇率表，与「每个币种一行」一致。

## What Didn't Work

把差额理解成「行数在对话里加了两次」或「云端 txt 少了一半」。逐文件对过 8 月桶：67 个 `AMZ*.txt`、47,705 行，外币 Tax 合计与 Colab Excel 相同。行数没丢，错在汇率合并。

## Solution

`run_period_tax.py` 使用第一张表（每个收款币种一行）。`enrich_with_fx` 在合并前按 `收款币种` 去重。2026-11-11 已用修正后的脚本重写 `附加费&Tax` 的 `Tax202608` / `Tax202609` / `Tax202610`。

Phase3 合并汇率走的是拆开表上的 `货币中文名`（该列已去重），不受这条影响。但 `人民币{账期区间}` 若是在修正 Tax 之前写的，里面的 Tax 列仍是旧数，需要重跑 `run_period_phase3.py`。

## Why This Works

合并键上每个币种只留一行汇率，明细行数不再随别名个数膨胀。去重放在 `enrich_with_fx` 里，调用方再传错表也不会乘进去。

## Prevention

- 解包写成 `df_fx, _aliases = load_exchange_rate_table(...)`。按 `收款币种` 合并只用第一张。
- 验收：`tax_rmb` 与 Colab `账号Tax汇总` 的 `Tax amount人民币` 合计一致，而不是大约两倍。

## Related

- `amazon_period_tax/exchange_rate.py`
- `amazon_period_tax/tax_aggregate.py`
- `docs/solutions/workflow-issues/amazon-period-tax-rerun-without-agent.md`
- `amazon_period_tax/AGENT_HANDOFF.md`
