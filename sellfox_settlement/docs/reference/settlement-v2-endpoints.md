---
okf: v0.1
type: Reference
title: 赛狐 Amazon 结算 / 列式报表 端点与字段
description: 赛狐 OpenAPI「财务/结算中心V2」与「报告中心/插件获取报告」的端点、请求体、响应字段与踩坑
resource: sellfox_settlement/reconcile_amazon.py
tags: [sellfox, amazon, settlement, reference, api]
---

# 赛狐 Amazon 结算 / 列式报表 端点与字段

## 1. 结算中心V2（= Amazon 官方 `GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2`，payout 口径）

### 结算汇总
`POST /api/financial/v2/settlementSummary/groupPage.json`
- **必填** `timeType`(settlementStartTime/settlementEndTime/transferTime) + `startTime`/`endTime`(yyyy-MM-dd)；`pageNo`/`pageSize` 为**字符串**、`pageSize≤200`。
- 响应字段：`settlementId`、`groupId`、`storeName`、`sellerId`、`marketplaceId/Name`、`currency`(站点币)、`region`、`accountType`、`groupStartStr/groupEndStr`(结算周期)、`siteGroupStartStr/EndStr`、`beginningBalance`(期初)、`endingBalance`(预留金)、`accountIncome`(销售额)、`accountRefund`(退款)、`accountExpenditure`(支出)、`accountNetIncome`(净收入=收入+支出+退款)、`transferAmount`、`accountTail`(支付账户尾号)、`utcFundTransferDateStr/siteFundTransferDateStr`、`fundTransferStatus/Str`、`processingStatus/Str`、`arrivalStatus/Str`、`arrivalAmount`、`convertedTotalCurrency`。

### 结算明细
`POST /api/financial/v2/settlementSummary/detailPage.json`
- 必填 `startTime`/`endTime`；`pageNo`/`pageSize` 字符串、`pageSize≤200`。
- 响应字段（= 结算报表 amount-description 行式）：`id`、`settlementId`、`marketplaceId`、`storeName`、`sellerId`、`orderId`、`currency`、`postedDateTimeStr`(UTC)/`siteTimeStr`、`reportType`、`msku`、`fulfillmentId`、`transactionType`(Order/Refund/AmazonFees/FBAFees/ServiceFee/other-transaction)、`amountType`(ItemPrice/ItemFees/ItemWithheldTax/Promotion/Cost of Advertising)、`amountDescription`(Principal/Commission/Tax/MarketplaceFacilitatorTax-Principal/FBAPerUnitFulfillmentFee/Subscription Fee…)、`amount`(有符号)、`quantityPurchased`、`updateTimeStr`、`isDel`。

### 关键踩坑（实测）
- **明细 `currency` 默认 CNY**（赛狐按当日汇率折算）；**传 `currency=USD`(或站点币) 返回原币**。要原币需**按币种分别拉**。
- `groupEndStr` 格式为**斜杠** `2026/06/16 06:16:48`；解析日期先 `replace('/','-')`。
- `pageSize>200` 报 `分页数量不能超过200`；`reportTypeList` **一次传一个**（传多个报「报告类型参数错误」）。

## 2. 报告中心 / 插件获取报告（紫鸟/赛狐插件已抓的列式报表）
`POST /api/report/center/task/getPlugPageList.json`
- 请求：`reportTypeList`(一次一个) 、`statusList`([1]=已成功)、`startTime`/`endTime`(≤1年)、`pageNo`/`pageSize`；可选 `shopIdList`。
- `reportTypeList`：**3=Transaction、4=Summary、5=Deferred transaction、6=FBAInboundConvenience**。
- 响应 `rows`：`shopName`、`marketplaceName`、`reportDayType`(月度 `yyyy-MM`，reportType=6 为日期范围)、`updateTime`、`fileUrls`(列表, COS 下载 URL, **ZIP**, 内含 `<月>MonthlyTransaction.csv`)。
- 只能**列已抓文件**，不能主动生成新日期范围；需先由紫鸟+赛狐插件抓取。已实测 `reportType=3` → ZIP→CSV（32 列）。
