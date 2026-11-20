---
okf: v0.1
type: Reference
title: 账期币种匹配：全角括号与零宽字符让币种/汇率变空、人民币全 0
date: 2026-11-19
category: integration-issues
module: amazon_period_tax
problem_type: integration_issue
component: tooling
severity: high
symptoms:
  - "某渠道账号（如 AllegroHU）在 {账期}/原始/人民币 三张表的 货币中文名/收款币种/汇率 全空"
  - "该账号 收款费用累加人民币 / 应收金额_人民币 / 销售额_人民币 为 0 或空"
  - "收款比例收款归属、收款比例运营人员 的合计偏小（该账号按 0 计入）"
root_cause: currency_label_not_normalized
resolution_type: code_fix
tags: [amazon-period, exchange-rate, gsheet, unicode, phase3]
---

# 账期币种匹配：全角括号与零宽字符让币种/汇率变空、人民币全 0

## Problem

Phase3（本地 `amazon_period_tax/phase3_merge.py`，与 Colab 同名 notebook 一致）用 `df.merge(df_rate_explode[["货币中文名","收款币种","汇率"]], on="货币中文名")` 把 OA 的币种接到汇率表。这是**精确字符串连接**：汇率表只登记 `匈牙利福林` 和 `匈牙利福林(HUF)` 两种写法，而钉钉 OA 表单里那个币种选项实际是 `‌匈牙利福林（HUF）`——开头一个零宽不连字符（U+200C），括号是全角（U+FF08 / U+FF09）。匹配必然失败。

## Symptoms

2026-11 排查 `钉钉OA收款费用Amazon多平台&附加费&Tax` 的 `20260704-20260803`、`20261004-20261103` 两期：

| 账期 | 账号 | 外币金额 | 修复前 | 应得人民币 |
|------|------|----------|--------|-----------|
| 202607 | AllegroHU | 应收 74,623 / 销售 109,015 / 科目 34,392 HUF | 币种、汇率、人民币全 0 | 1,626.78 / 2,376.53 / 749.75 |
| 202610 | AllegroHU | 应收 226,353 / 销售 354,990 / 科目 128,637 HUF | 同上 | 4,640.24 / 7,277.30 / 2,637.06 |

`收款比例运营人员` 里宋唯一应收少算约 5.2%（7 月）/ 7.1%（10 月）。全量扫描同期所有 `{账期}` 汇总 tab，只有这两个账号命中「外币有值但币种/汇率空」。

## What Didn't Work

- 先怀疑汇率表缺 HUF：`和财务部共享 / 汇率` 里 HUF 每月都有（202607=0.0218、202610=0.0205），不是缺数。
- 再怀疑「货币符号不统一」：Colab notebook 与该本地移植都没有任何全角/零宽归一化代码，只做了 `astype(str)`、逗号拆分和 `strip()`，所以 `（HUF）` 与 `(HUF)` 永远对不上。

## Solution

1. `exchange_rate.py` 新增 `normalize_currency_label()`：正则去零宽/格式字符（U+00AD、U+200B–200F、U+202A–202E、U+2060–2064、U+FEFF）+ `unicodedata.normalize("NFKC")` 把全角括号/逗号转半角 + `strip()`。汇率表的 `货币中文名`/`货币别名` 两侧都先归一化再炸开。
2. `phase3_merge.build_row_level_df()` 在 merge 前对 `货币中文名` 做同样归一化。
3. 新增 `find_unmatched_currency()`：汇率仍为空但金额非 0 的行写入 `Phase3Report.warnings` 并打到 stderr，避免再次静默变 0。

历史两期不回写整表（重跑会因渠道总表新增账号而多出空行、并重新序列化日期列），改为**只回填受影响单元格**：汇总 9 格、原始 32 格、人民币 3 格、收款归属 3 格、运营人员 10–11 格，写后复读逐格校验。

## Prevention

- 任何按中文字符串做 join 的取数，先用 `normalize_currency_label()`（或同等的 NFKC + 去不可见字符）统一两侧。
- 已把钉钉 OA「收款确认单 / 币种」选项改为半角 `匈牙利福林(HUF)`；历史单靠代码兜底。
- 重跑历史期前先比对「输入定稿 vs 现有原始表」的审批编号多集，确认没有被后补的单据（202610 就有 1 条 11-05 补交的 WM 行不在 11-04 定稿里）。

## Related

- `amazon_period_tax/exchange_rate.py`
- `amazon_period_tax/phase3_merge.py`
- `docs/solutions/integration-issues/amazon-period-tax-fx-alias-multiplies.md`
- `amazon_period_tax/AGENT_HANDOFF.md`
