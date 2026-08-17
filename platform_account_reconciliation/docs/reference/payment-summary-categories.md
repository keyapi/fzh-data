---
okf: v0.1
type: Reference
title: Payment Summary 费用分类
description: OSTKUS Payment Summary 类别与 Detail 描述归类规则
tags: [ostkus, payment-summary, categories]
timestamp: 2026-08-17
---

# Payment Summary 费用分类

## 退货分类

| Payment Summary 类别 | Detail 描述特征 |
|----------------------|-----------------|
| First Cost | 描述以 `First Cost` 开头 |
| Others | 描述含 `Customer to Bed Bath & Beyond/Supplier Shipping Cost` 等未归入其他类的退货行 |
| Return-Related Customer Service Cost | 描述含 `Return-Related Customer Service Cost` |
| Supplier to Customer Shipping Cost | 描述含 `Supplier to Customer Shipping Cost` |

## 调整分类

| Payment Summary 类别 | Detail 描述特征 |
|----------------------|-----------------|
| Marketing Allowance 8.25% | 描述以 `Marketing Allowance 8.25%` 开头 |
| 其他调整合计 | `Total Adjustments` 行；明细包含 BBB Sponsored Product Ads、Audit Fee、运费纠正、Overbill Charge-Back 等 |
| 调整合计 | `Total` 行，等于营销扣点 + 其他调整 |

## Supplier Oasis Fees

- Payment Summary：`Supplier Oasis Transaction Fees`
- Detail：`Line Type = Supplier Oasis Fees` 单行

## 对账校验

- `Payment Summary Check Total = Sales + Returns + Adjustments + Fees`
- `Detail` 按行类型和描述归类后的合计应与 Payment Summary 对应类别一致。
