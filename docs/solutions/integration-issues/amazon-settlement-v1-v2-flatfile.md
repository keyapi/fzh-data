---
okf: v0.1
type: Reference
title: Amazon 结算报告 V1/V2 与 XML：旧格式会让 Tax/FBA 静默少算
date: 2026-11-19
category: integration-issues
module: amazon_period_tax
problem_type: integration_issue
component: tooling
severity: high
symptoms:
  - "某账号 Tax/FBA 为 0 或偏低，但 65 份附件全部读取成功、rows_mismatch=0"
  - "附件表头是 price-type/price-amount，不是 amount-type/amount-description"
  - "让运营下载 flat file，发来的却是 XML（AmazonEnvelope）"
root_cause: schema_unsupported_v1
resolution_type: code_fix
tags: [amazon-period, settlement-report, v1-schema, xml, tax, fba]
---

# Amazon 结算报告 V1/V2 与 XML：旧格式会让 Tax/FBA 静默少算

## Problem

Amazon 结算报告存在三种形态：V2 Flat File（`amount-type`/`amount-description`/`amount`）、
**V1 Flat File**（`price-type`/`price-amount`、`item-related-fee-*`、`shipment-fee-*`、
`order-fee-*`、`promotion-*`）以及 **XML**（`AmazonEnvelope`）。旧管道只按 V2 读，
V1 文件没有 amount 列 → 金额变 NaN，Tax/FBA 静默少算，且读取统计仍显示“成功”。

## Symptoms

2026-10 月三份 V1 附件（结算号 `27638132371` / `27753900801` / `27830798241`）：

- Tax 合计少 **2,131.31 USD = 14,357.996 元**；
- 第三份少一笔 `FBAPerUnitFulfillmentFee = -901.86 USD = -6,075.56 元`；
- 文件读取成功、行数对账通过、`verify` 仍 PASS——这是最危险的地方。

## What Didn't Work

- **按 V2 直接读**：V1 没有 `amount-type`，`amount` 全 NaN。
- **源行数 = 解析行数对账**：V1 一行会展开成多条金额行，对账反而把文件当异常丢掉。
- **只说“要 txt”**：运营可能下载到 XML，扩展名同样是 `.txt`。

## Solution

1. `read_amz_txt._normalize_v1_schema()`：检测 V1（有 `price-type`、无 `amount-type`）后按金额族
   展开成 V2 长表：`price-*→ItemPrice`、`item-related-fee/shipment-fee/order-fee→ItemFees`、
   `promotion-*→Promotion`；`MarketplaceFacilitator*` 归 `ItemWithheldTax`，不得混入 ItemPrice；
   展开前对 `currency`/`settlement-id` 做 ffill（汇总行会被展开过程丢掉）。
2. `expected_parsed_rows()`：V1 按“非空金额单元格”计数，V2 按行数，避免把展开行误判为异常。
3. 校验：三份 V1 的 Tax = 630.51 / 322.95 / 1177.85 USD（合计 2,131.31），
   第三份 FBA −901.86 USD；10 月 Tax 207,131.59、FBA 分类 13→14 行。
4. XML 不直接入管道：请提交人重新下载 **Flat File**（制表符 `.txt`），不要 XML。

## Why This Works

结算身份与金额科目都来自表头结构；按金额族展开后，Tax/FBA 的筛选规则（ItemPrice/Promotion +
描述含 Tax）与 V2 完全同口径，且行数对账能区分“展开”与“丢行”。

## Prevention

- 读取时先判 schema；未知结构直接 FAIL，不允许 NaN 成功。
- 要求提交人确认表头：`amount-type/amount-description` 才是新版 Flat File。
- **补交 V2 后必须把旧 V1 移出桶**（V1/V2 内容 md5 不同，会各算一遍导致翻倍）。
- 对“读取成功但金额为 0/偏低”的账号保持怀疑，按月做附件级 Tax 对账。

## Related

- `amazon_period_tax/read_amz_txt.py`（`_normalize_v1_schema` / `expected_parsed_rows`）
- `amazon_period_tax/tests/test_v1_schema.py`、`tests/verify_v1_independent.py`
- `docs/solutions/workflow-issues/amazon-period-source-corrections-and-e2e-gate.md`
- `docs/solutions/workflow-issues/amazon-period-cross-bucket-attachment-misfile.md`
