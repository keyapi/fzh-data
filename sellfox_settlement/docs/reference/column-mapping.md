---
okf: v0.1
type: Reference
title: 科目映射（列式报表 & 结算 amount-description → 钉钉列）
description: Amazon 账期明细如何拆分到「钉钉销售收款确认单」各科目；两套口径（列式 vs 结算 amount-description）方向一致
resource: sellfox_settlement/reconcile_amazon.py
tags: [sellfox, amazon, settlement, subject-mapping, reference]
---

# 科目映射

> 两种报表底层同源，只是投影不同：**列式 Custom Transaction**（每订单/SKU 一行、每种费一列、原币）最直观；**结算 amount-description**（每交易一行、amount-type/amount-description、默认 CNY/可原币）是行式。映射方向一致。

## A. 列式 CustomTransaction（推荐做费用/科目；`getPlugPageList type=3` → 32 列 csv）

| 钉钉科目 | CustomTransaction 列 / 规则 |
|---|---|
| 销售额 | `product sales`（Refund 行取负）+ `promotional rebates` |
| 税 | `product sales tax + shipping credits tax + giftwrap credits tax + Tax On Regulatory Fee + marketplace withheld tax` |
| 佣金 | `selling fees` |
| FBA/仓库费 | `fba fees` |
| 广告费 | `description=='Cost of Advertising'` 行 |
| 退款 | `type in (Refund, Refund_Retrocharge)` 行 |
| 其他费用 | `other transaction fees + other` |
| 净额 | `total` |

列（32）：`date/time, settlement id, type, order id, sku, description, quantity, marketplace, account type, fulfillment, order city/state/postal, tax collection model, product sales, product sales tax, shipping credits, shipping credits tax, gift wrap credits, giftwrap credits tax, Regulatory Fee, Tax On Regulatory Fee, promotional rebates, promotional rebates tax, marketplace withheld tax, selling fees, fba fees, other transaction fees, other, total, Transaction Status, Transaction Release Date`。

## B. 结算 centerV2 amount-description（payout 口径）

| 钉钉科目 | 结算 amountType / amountDescription |
|---|---|
| 销售额 | `amountDescription=='Principal'`（Order，正值）；促销另见 `amountType=='Promotion'` |
| 佣金 | `Commission` / `RefundCommission` |
| 广告费 | `amountType=='Cost of Advertising'` |
| 税 | amountDescription ∈ {Tax, MarketplaceFacilitatorTax-Principal, MarketplaceFacilitatorTax-Shipping, MarketplaceFacilitatorVAT-Principal, MarketplaceFacilitatorVAT-Shipping, TaxDiscount, ShippingTax} |
| FBA/仓库费 | `FBAPerUnitFulfillmentFee`、`Storage Fee`、`StorageRenewalBilling`、`FBA Inbound Placement Service Fee`、`FBA Pick & Pack Fee` 等 |
| 平台月租 | `Subscription Fee` |
| 退款 | `transactionType in (Refund, Refund_Retrocharge)` |
| 其他/未识别 | 其余（量大，需表驱动补全） |

## C. 要点 / 坑
- **税净≈0**：MarketplaceFacilitator 下 Amazon 代收代缴——`product sales tax`(收集) ≈ `marketplace withheld tax`(代扣)，净为 0。报税别把「收到的税」当利润。
- **两表总额不等**：sql=payout、Custom=activity/posted(含 deferred)；做费用用列式、做回款率用结算，**别同一口径对等**。
- **符号**：结算 `amount` 有符号（正=收入、负=费用/退款）；钉钉各列多为绝对值，映射后按方向取值。
- **广告**：on-account 广告在结算（`Cost of Advertising`）；off-account 不进结算 → 结算口径 TACoS 低估。
