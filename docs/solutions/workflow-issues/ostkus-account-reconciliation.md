---
okf: v0.1
type: Reference
title: OSTKUS 账期与 EN Tongtool Order 对账
category: workflow-issues
module: platform_account_reconciliation
problem_type: workflow_issue
component: finance_reconciliation
severity: high
date: 2026-08-17
applies_when:
  - "财务提供 OSTKUS/Overstock 账期文件，需要核对与订单数据的关系"
  - "需要按订单/费用级别核对 Payment Summary、Returns、Adjustments 与 EN Tongtool Order"
  - "需要扩展 Wayfair/WFUS 账期对账"
tags: [ostkus, overstock, reconciliation, tongtool, en, finance, wayfair]
related_components: [EN_API, tongtool_api]
---

# OSTKUS 账期与 EN Tongtool Order 对账

## Context

Overstock `OSTKUS-*.xlsx` 是含 `Payment Summary`、`Detail`、`Mozart Reports` 的结算文件，不是订单导出。财务需要确认账期订单与 EN 生产系统 `Tongtool Order` 是否全部对上，以及金额/费用口径。

## Guidance

1. **先判断文件类型**：`Payment Summary + Detail` 是账期文件；平台订单 CSV 可能是另一批订单，日期不一定相同。
2. **不要用原始 `OS Order #` 直接精确查 EN**：多 SKU/多件会拆成 `_1/_2/_3`，`platform_order_id` 保留后缀；另一账号 `OSTK02US` 用 `OSFD-` 前缀。
3. **排除重复主单**：部分订单同时存在无后缀主单和拆分后缀子单，且金额相同；汇总时把主单标记为重复并排除，避免双算。
4. **金额用 `order_amount`**：`order_items.transaction_price` 是组件行，可能重复，不能加总。
5. **数量用 raw 平台数量**：`order_items.quantity` 是内部组件行；用 `raw_data.goodsInfo.platformGoodsInfoList.quantity`。
6. **`SOFS Order #` 在 EN 不可用**，不要假装能匹配。
7. **`actual_total_price` 在退货订单上可能为 0**，不能直接当实收加总。

## Why This Matters

财务对账如果不处理后缀和重复主单，会出现“订单丢失”或金额双算；如果直接加 `transaction_price`，金额会虚高。固化 OSTKUS 规则后，Wayfair/WFUS 可以直接复用同一套匹配流程。

## When to Apply

- 用户提到 OSTKUS/Overstock 账期、Payment Summary、营销扣点、平台费、退货费用。
- 后续 Wayfair/WFUS 账期文件需要同样的对账。

## Examples

```bash
uv run python platform_account_reconciliation/scripts/reconcile_ostkus.py \
  --account "D:/Work/尹/OSTKUS-2026-07-01.xlsx" \
  --account "D:/Work/尹/OSTKUS-2026-07-16.xlsx"
```

2026-08-17 结果：350 个基础 OS 订单全部覆盖；07-01/07-16 销售金额差异均为 0；4 个跨期退单；EN 平台费与账期营销扣点差异待财务确认。
