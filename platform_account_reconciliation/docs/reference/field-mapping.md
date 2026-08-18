---
okf: v0.1
type: Reference
title: 账期与 EN/Tongtool Order 字段映射
description: OSTKUS 账期字段、EN Tongtool Order 字段与匹配方式
tags: [ostkus, en, tongtool, field-mapping]
timestamp: 2026-08-17
---

# 账期与 EN/Tongtool Order 字段映射

## 可直接匹配

| 账期字段 | EN 字段 | 说明 |
|----------|---------|------|
| `OS Order #` | `platform_order_id` / `name` | 原始号可能带 `_1/_2/_3` 或 `-1` 后缀；另一账号用 `OSFD-` |
| `Supplier SKU` | `order_items.platform_sku` / raw `webstoreSku` | 精确匹配，大小写敏感 |
| `Quantity` | raw `platformGoodsInfoList.quantity` | 不要用 `order_items.quantity`（内部组件行） |
| `Unit Price` / `Total` | `order_amount` / `products_total_price` | 销售金额合计已验证一致 |
| 仓库 | `warehouse_name` | 拆单可能发不同仓 |
| 发货时间 | `despatch_complete_time` | 等待配货订单为空 |
| P号 | `packages.package` | 可追物流/赛狐包裹 |

## 近似匹配

| 账期字段 | EN 字段 | 说明 |
|----------|---------|------|
| `Order Date` | `sale_time` | 实测账期下单日通常比 EN sale_time 早 0-2 天 |

## 不可直接匹配

| 账期字段 | 原因 |
|----------|------|
| `SOFS Order #` | EN `Tongtool Order` 主表和 raw_data 中均无该值 |
| `Invoice Date` | EN 无对应字段 |

## EN 金额字段口径

| 字段 | 口径 |
|------|------|
| `order_amount` / `products_total_price` | 订单商品额，用于对账 |
| `actual_total_price` | 已退款/退货订单可能为 0，不能当实收加总 |
| `platform_fee` | 平台费用，与账期营销扣点接近但不等 |
| `shipping_fee` | OSTKUS 当前为 0，账期运费纠正是账单级 |
| `gross_profit` | 收入-平台费-成本，按 EN 成本口径 |
| `order_items.transaction_price` | 组件行金额，可能重复，不能加总 |
