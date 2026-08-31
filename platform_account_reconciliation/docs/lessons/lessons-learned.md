---
okf: v0.1
type: Lesson
title: 平台账期对账经验教训
description: OSTKUS 对账中的字段、拆单、重复主单与金额口径教训
tags: [ostkus, en, tongtool, reconciliation, lessons]
timestamp: 2026-08-17
---

# 平台账期对账经验教训

1. **账期文件不是订单文件**：`OSTKUS-*.xlsx` 是 Payment Summary + Detail 结算文件；平台订单 CSV 是另一类数据，日期可能完全不同期。
2. **原始订单号精确查会漏拆单**：多 SKU/多件订单在通途/EN 会拆成 `_1/_2/_3`，`platform_order_id` 保留后缀。
3. **不同账号有不同前缀**：`OSTKUS` 使用 `OS-`，`OSTK02US` 使用 `OSFD-`，不能假设前缀唯一。
4. **同时存在主单和子单**：部分订单 EN 同时有无后缀主单和拆分后缀子单，金额相同；汇总前必须标记重复主单并排除。
5. **数量匹配用 raw 平台数量**：`order_items.quantity` 是内部组件行，同一 SKU 可能多行；用 `raw_data.goodsInfo.platformGoodsInfoList.quantity`。
6. **金额匹配用 order_amount**：`order_items.transaction_price` 是组件行金额，可能重复，不能加总。
7. **SOFS Order # 在 EN 不可用**：EN `Tongtool Order` 主表和 raw_data 都没有该值。
8. **actual_total_price 在退货订单上可能为 0**：不能直接作为实收加总。
9. **EN platform_fee 与账期营销扣点口径不同**：金额接近但不等，需要财务确认，不能强行拉平。
10. **跨期退单需要合并看**：同订单可能在 07-01 销售、07-16 退货，只按单期看会误判。
