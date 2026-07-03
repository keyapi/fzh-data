---
okf: v0.1
type: Reference
title: SB/SD 广告报告字段权威参考
description: Amazon Sponsored Brands (7种) 和 Sponsored Display (5种) 报告的全部列定义，含官方来源链接
tags: [amazon, advertising, reference, data-dictionary, sponsored-brands, sponsored-display]
created: 2026-07-02
updated: 2026-07-02
sources:
  - https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview
  - https://advertising.amazon.com/help/GG44RFW942U9F6F5
  - https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sb-performance
  - https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sd-performance
  - https://docs.supermetrics.com/docs/amazon-ads-fields
  - https://twominutereports.com/amazon-ads-metrics-and-dimensions/
  - https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics
---

# SB/SD 广告报告字段权威参考

> **目的**: 为赛狐 SB (Sponsored Brands) 和 SD (Sponsored Display) 广告报表系统提供每个字段的官方定义、计算方式和数据类型。
> **原则**: 每个定义均可追溯到 Amazon 官方来源。未找到官方来源的字段标注 `[推断]`。
> **数据来源**: `/tmp/report_headers.json` (赛狐实际导出的列名) + 30+ 官方/权威来源交叉验证。

---

## 目录

**Sponsored Brands (SB):**
1. [SB 概述与通用字段](#sb-1-概述与通用字段)
2. [SB 广告活动报告 (Campaign)](#sb-2-广告活动报告)
3. [SB 广告组报告 (AdGroup)](#sb-3-广告组报告)
4. [SB 广告产品报告 (AdProduct)](#sb-4-广告产品报告)
5. [SB 广告位报告 (Placement)](#sb-5-广告位报告)
6. [SB 投放报告 (Targeting)](#sb-6-投放报告)
7. [SB 搜索词报告 (SearchTerm)](#sb-7-搜索词报告)
8. [SB 已购产品报告 (PurchasedItem)](#sb-8-已购产品报告)

**Sponsored Display (SD):**
9. [SD 概述与通用字段](#sd-9-概述与通用字段)
10. [SD 广告活动报告 (Campaign)](#sd-10-广告活动报告)
11. [SD 广告组报告 (AdGroup)](#sd-11-广告组报告)
12. [SD 广告产品报告 (AdProduct)](#sd-12-广告产品报告)
13. [SD 投放报告 (Targeting)](#sd-13-投放报告)
14. [SD 已购产品报告 (PurchasedItem)](#sd-14-已购产品报告)

**附录:**
15. [SB/SD 独有指标详解](#15-sbsd-独有指标详解)
16. [公式速查](#16-公式速查)
17. [来源清单](#17-来源清单)

---

# Sponsored Brands (SB) -- 品牌推广

## SB-1. 概述与通用字段

### 1.1 SB 报告概述

Sponsored Brands (品牌推广) 是 Amazon 广告体系中的品牌级广告产品，允许品牌主在搜索结果中展示品牌 logo、自定义标题和多件商品。SB 广告独有的特性:

- **视频广告指标**: SB 支持视频创意，报告包含完整的视频漏斗指标 (5s/25%/50%/75%/100% 观看、VCTR、VTR、取消静音)
- **品牌新买家 (NTB)**: SB 报告全面包含 NTB 指标 (New-to-Brand)，衡量广告带来的品牌新客
- **可见展示 (Viewable Impressions)**: SB 使用 vCPM 竞价时，报告含可见展示次数和 VCPM
- **归因窗口**: SB 使用 **14 天** 点击归因窗口 (与 SP 的 7 天不同)

### 1.2 SB 报告类型总览

| 报告类型 | API reportTypeId | 赛狐文件名 | 列数 | 粒度 |
|----------|-----------------|-----------|------|------|
| Campaign | `sbCampaigns` | `SB-Campaign_*.xlsx` | 40 | 按广告活动 |
| AdGroup | `sbAdGroups` | `SB-AdGroup_*.xlsx` | 33 | 按广告组 |
| AdProduct | `sbAdvertisedProduct` | `SB-AdProduct_*.xlsx` | 35 | 按 ASIN/SKU |
| Placement | `sbPlacement` | `SB-Placement_*.xlsx` | 41 | 按广告位 |
| Targeting | `sbTargeting` | `SB-Targeting_*.xlsx` | 43 | 按投放目标 |
| SearchTerm | `sbSearchTerm` | `SB-SearchTerm_*.xlsx` | 44 | 按搜索词 |
| PurchasedItem | `sbPurchasedProduct` | `SB-PurchasedItem_*.xlsx` | 19 | 按已购 ASIN |

### 1.3 SB 通用标识字段 (Dimensions)

以下字段出现在多数 SB 报告类型中，定义与 SP 报告相同。

| 官方字段名 (API v3) | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `date` | 日期 | 数据日期 (YYYY-MM-DD) | DATE | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `campaignName` | 广告活动 | 广告活动名称 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `campaignId` | 广告活动ID | 广告活动唯一标识 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `adGroupName` | 广告组 | 广告组名称 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `adGroupId` | 广告组ID | 广告组唯一标识 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `campaignStatus` | 广告活动运行状态 | 已开启/已暂停/已归档 | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `adGroupStatus` | 广告组运行状态 | 已开启/已暂停 | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `startDate` | 广告活动开始时间 | 广告活动开始日期 | DATE | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `endDate` | 广告活动结束时间 | 广告活动结束日期 (无结束日期则显示"无结束日期") | DATE | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `portfolioId` | 广告组合ID | Portfolio 唯一标识 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `portfolioName` | 广告组合名称 | Portfolio 名称 | STRING | [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/) |
| `currency` | 币种 | 货币代码 (如 USD) | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `matchType` | 匹配类型 | 关键词匹配类型: 广泛匹配/词组匹配/精确匹配等 | STRING | [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/) |
| `targetingType` | 定位类型 | 自动投放 / 手动投放 | STRING | [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/) |
| `targeting` / `keyword` | 投放 | 投放目标关键词文本或匹配方式名称 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `keywordId` / `targetId` | 广告投放ID | 投放目标唯一标识 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `targetingStatus` | 投放运行状态 | 已开启/已暂停 | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `asin` | ASIN | 广告商品 ASIN | STRING | [Scaleleap](https://amazon-advertising-api-sdk.scaleleap.org) |
| `sku` | SKU | 广告商品 SKU | STRING | [Scaleleap](https://amazon-advertising-api-sdk.scaleleap.org) |
| `placement` | 广告位 | SB 广告位细分 | STRING | [Amazon Placement Help](https://advertising.amazon.ca/help/G89VFUTQUWFFN2VU) |
| `reportingAdProductId` | 广告产品ID | 广告产品唯一标识 (SB AdProduct 的广告实体) | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |

### 1.4 SB 通用指标字段

以下指标出现在多数 SB 报告类型中，定义相同。

#### 流量指标

| 官方字段名 (API v3) | 赛狐中文名 | 定义 | 计算方式 | 数据类型 | 来源 |
|---|---|---|---|---|---|
| `impressions` | 广告曝光量 | 广告展示的总次数 | 每次广告在页面上渲染一次计 1 | INTEGER | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `clicks` | 广告点击量 | 广告被点击的总次数 | 每次用户点击广告计 1 | INTEGER | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `cost` | 广告花费 | 广告产生的总费用 | CPC: 所有点击成本之和; vCPM: 按千次可见展示计费 | CURRENCY | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `costPerClick` (CPC) | CPC | 平均单次点击成本 | `cost / clicks` | CURRENCY | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `clickThroughRate` (CTR) | 广告点击率 | 广告被点击的概率 | `clicks / impressions` | DECIMAL | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |

#### 转化指标

| 官方字段名 (API v3) | 赛狐中文名 | 定义 | 计算方式 | 数据类型 | 来源 |
|---|---|---|---|---|---|
| `purchases14d` | 广告订单量 | 14天归因窗口内广告点击带来的总订单数 | 点击后14天内产生的所有订单 | INTEGER | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `attributedConversions14dSameSKU` | 本广告产品订单量 | 14天归因窗口内购买商品=广告商品的订单数 | 仅同 SKU 订单 | INTEGER | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `attributedConversions14dOtherSKU` | 其他产品广告订单量 | 14天归因窗口内购买商品!=广告商品的订单数 | 品牌光环订单 | INTEGER | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `sales14d` | 广告销售额 | 14天归因窗口内广告点击带来的总销售额 | 归因订单商品售价总和 | CURRENCY | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `attributedSales14dSameSKU` | 本广告产品销售额 | 14天归因窗口内广告商品自身销售额 | 仅广告商品售价 | CURRENCY | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `attributedSales14dOtherSKU` | 其他产品广告销售额 | 14天归因窗口内非广告商品销售额 | 品牌光环销售额 | CURRENCY | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `unitsSoldClicks14d` | 广告销量 | 14天归因窗口内广告点击带来的总销售件数 | 归因订单中所有商品件数之和 | INTEGER | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |

#### 效率指标

| 官方字段名 (API v3) | 赛狐中文名 | 定义 | 计算方式 | 数据类型 | 来源 |
|---|---|---|---|---|---|
| `acos14d` | ACoS | 广告销售成本比 | `(cost / sales14d) * 100` | DECIMAL | [Amazon ACoS Help](https://advertising.amazon.com/help/G96BDERJLNQGW2Y3) |
| `roas14d` | ROAS | 广告投资回报率 | `sales14d / cost` | DECIMAL | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `conversionRate14d` | 广告转化率 | 点击转化为订单的比率 | `(purchases14d / clicks) * 100` | DECIMAL | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |

### 1.5 SB 归因窗口

| 窗口 | API 后缀 | 说明 |
|------|----------|------|
| 14 天 | `14d` | SB 默认归因窗口 (Seller 和 Vendor 均 14天) |

> **Source**: [Openbridge Attribution Metrics](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics)

---

## SB-2. 广告活动报告 (Campaign)

- **API reportTypeId**: `sbCampaigns`
- **粒度**: 按 `campaign` 聚合
- **赛狐导出文件**: `SB-Campaign_*.xlsx` (40 列)
- **特点**: 包含视频指标 (VCTR、VTR、5s/1/4/2/4/3/4/complete views) + 品牌新买家指标 + 广告销量

### SB Campaign 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 计算方式 | 数据类型 |
|---|-----------|----------------|------|----------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 (赛狐平台拼接) | -- | STRING |
| 2 | 日期 | `date` | 数据日期 | -- | DATE |
| 3 | 广告活动 | `campaignName` | 广告活动名称 | -- | STRING |
| 4 | 广告花费 | `cost` | 总广告花费 (CPC + vCPM) | 所有点击/展示费用之和 | CURRENCY |
| 5 | 广告曝光量 | `impressions` | 广告展示总次数 | 计数器 | INTEGER |
| 6 | 广告点击量 | `clicks` | 广告点击总次数 | 计数器 | INTEGER |
| 7 | CPC | `costPerClick` | 平均单次点击成本 | `cost / clicks` | CURRENCY |
| 8 | 广告点击率 | `clickThroughRate` (CTR) | 展示转化为点击的比率 | `clicks / impressions` | DECIMAL |
| 9 | 广告转化率 | `conversionRate14d` (CVR) | 点击转化为订单的比率 | `purchases14d / clicks` | DECIMAL |
| 10 | ACoS | `acos14d` | 广告销售成本比 | `(cost / sales14d) * 100` | DECIMAL |
| 11 | ROAS | `roas14d` | 广告投资回报率 | `sales14d / cost` | DECIMAL |
| 12 | 广告订单量 | `purchases14d` | 14天归因总订单数 | 归因计数器 | INTEGER |
| 13 | 本广告产品订单量 | `attributedConversions14dSameSKU` | 同 SKU 归因订单数 | 仅广告商品 | INTEGER |
| 14 | 其他产品广告订单量 | `attributedConversions14dOtherSKU` | 其他 SKU 归因订单数 | 品牌光环 | INTEGER |
| 15 | 广告销售额 | `sales14d` | 14天归因总销售额 | 归因商品售价总和 | CURRENCY |
| 16 | 本广告产品销售额 | `attributedSales14dSameSKU` | 同 SKU 归因销售额 | 仅广告商品 | CURRENCY |
| 17 | 其他产品广告销售额 | `attributedSales14dOtherSKU` | 其他 SKU 归因销售额 | 品牌光环 | CURRENCY |
| 18 | "品牌新买家"订单转化率 | `newToBrandConversionRate14d` | NTB 订单转化率 [推断] | NTB订单数 / 点击量 | DECIMAL |
| 19 | "品牌新买家"订单量 | `newToBrandPurchases14d` | 过去12个月未买过该品牌的新客订单数 | NTB 订单计数 | INTEGER |
| 20 | "品牌新买家"订单占比 | `newToBrandPurchasesPercentage14d` | NTB 订单占总量百分比 | `NTB订单数 / 总订单数 * 100` | DECIMAL |
| 21 | "品牌新买家"销售额 | `newToBrandSales14d` | NTB 订单产生的销售额 | NTB 归因销售额合计 | CURRENCY |
| 22 | "品牌新买家"销售额百分比 | `newToBrandSalesPercentage14d` | NTB 销售额占总销售额百分比 | `NTB销售额 / 总销售额 * 100` | DECIMAL |
| 23 | "品牌新买家"销量 | `newToBrandUnitsSold14d` | NTB 订单产生的销售件数 | NTB 归因件数合计 | INTEGER |
| 24 | "品牌新买家"销量占比 | `newToBrandUnitsSoldPercentage14d` | NTB 销量占总销量百分比 | `NTB销量 / 总销量 * 100` | DECIMAL |
| 25 | VCTR | `videoClickThroughRate` | 视频点击率 | `clicks / viewableImpressions` | DECIMAL |
| 26 | 5s观看率 | `video5sViewRate` | 5秒观看率 [推断] | `video5sViews / viewableImpressions` | DECIMAL |
| 27 | 5s观看次数 | `video5sViews` | 观看满5秒的次数 | 计数器 | INTEGER |
| 28 | 1/4视频观看次数 | `videoFirstQuartileViews` | 观看至视频25%的次数 | 计数器 | INTEGER |
| 29 | 1/2视频观看次数 | `videoMidpointViews` | 观看至视频50%的次数 | 计数器 | INTEGER |
| 30 | 3/4视频观看次数 | `videoThirdQuartileViews` | 观看至视频75%的次数 | 计数器 | INTEGER |
| 31 | 视频取消静音 | `videoUnmutes` | 用户取消静音的次数 | 计数器 | INTEGER |
| 32 | 可见展示次数 | `viewableImpressions` | 符合 MRC 可见性标准的展示次数 | 至少50%面积可见持续1秒以上 | INTEGER |
| 33 | 完整视频观看次数 | `videoCompleteViews` | 观看至视频100%的次数 | 计数器 | INTEGER |
| 34 | VTR | `videoThroughRate` | 完整观看率 | `videoCompleteViews / viewableImpressions` | DECIMAL |
| 35 | 广告活动开始时间 | `startDate` | 广告活动开始日期 | -- | DATE |
| 36 | 广告活动结束时间 | `endDate` | 广告活动结束日期 | -- | DATE |
| 37 | 广告活动运行状态 | `campaignStatus` | ENABLED(已开启)/PAUSED(已暂停)/ARCHIVED(已归档) | -- | STRING |
| 38 | 广告组合ID | `portfolioId` | 所属 Portfolio ID | -- | STRING |
| 39 | 广告活动ID | `campaignId` | 广告活动唯一标识 | -- | STRING |
| 40 | 广告销量 | `unitsSoldClicks14d` | 14天归因总销售件数 | 归因订单中所有商品件数之和 | INTEGER |

> **Sources**: [Amazon Ads API Report Types](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview), [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields), [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/), [Amazon Marketing Stream SB](https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sb-performance)

---

## SB-3. 广告组报告 (AdGroup)

- **API reportTypeId**: `sbAdGroups` (通过 `sbCampaigns` with `groupBy: adGroup` 获取) [推断]
- **粒度**: 按 `adGroup` 聚合
- **赛狐导出文件**: `SB-AdGroup_*.xlsx` (33 列)
- **与 Campaign 报告的区别**: 列顺序和子集不同; 本报告无视频指标 (VCTR/VTR/视频观看次数) 和品牌搜索次数，但新增 DPV、VCPM、可见展示次数

> **重要**: SB AdGroup 报告不包含视频漏斗指标 (不同于 SB Campaign)。它侧重于常规效果指标 + NTB + DPV。

### SB AdGroup 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 计算方式 | 数据类型 |
|---|-----------|----------------|------|----------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | -- | STRING |
| 2 | 日期 | `date` | 数据日期 | -- | DATE |
| 3 | 广告组 | `adGroupName` | 广告组名称 | -- | STRING |
| 4 | 广告活动 | `campaignName` | 广告活动名称 | -- | STRING |
| 5 | 广告花费 | `cost` | 总广告花费 | -- | CURRENCY |
| 6 | 广告曝光量 | `impressions` | 广告展示总次数 | 计数器 | INTEGER |
| 7 | 可见展示次数 | `viewableImpressions` | 符合 MRC 可见性标准的展示 | 至少50%面积可见>=1秒 | INTEGER |
| 8 | 广告点击量 | `clicks` | 广告点击总次数 | 计数器 | INTEGER |
| 9 | CPC | `costPerClick` | 平均单次点击成本 | `cost / clicks` | CURRENCY |
| 10 | VCPM | `costPerThousandViewableImpressions` | 每千次可见展示成本 | `(cost / viewableImpressions) * 1000` | CURRENCY |
| 11 | 广告点击率 | `clickThroughRate` (CTR) | 展示转化为点击的比率 | `clicks / impressions` | DECIMAL |
| 12 | 商品详情页浏览量 (DPV) | `detailPageViews` (DPV) | 广告点击后到达商品详情页的次数 | 详情页浏览计数 | INTEGER |
| 13 | 广告转化率 | `conversionRate14d` (CVR) | 点击转化为订单的比率 | `purchases14d / clicks` | DECIMAL |
| 14 | ACoS | `acos14d` | 广告销售成本比 | `(cost / sales14d) * 100` | DECIMAL |
| 15 | ROAS | `roas14d` | 广告投资回报率 | `sales14d / cost` | DECIMAL |
| 16 | 广告订单量 | `purchases14d` | 14天归因总订单数 | 归因计数器 | INTEGER |
| 17 | 本广告产品订单量 | `attributedConversions14dSameSKU` | 同 SKU 归因订单数 | 仅广告商品 | INTEGER |
| 18 | 其他产品广告订单量 | `attributedConversions14dOtherSKU` | 其他 SKU 归因订单数 | 品牌光环 | INTEGER |
| 19 | 广告销售额 | `sales14d` | 14天归因总销售额 | 归因售价总和 | CURRENCY |
| 20 | 本广告产品销售额 | `attributedSales14dSameSKU` | 同 SKU 归因销售额 | 仅广告商品 | CURRENCY |
| 21 | 其他产品广告销售额 | `attributedSales14dOtherSKU` | 其他 SKU 归因销售额 | 品牌光环 | CURRENCY |
| 22 | 广告销量 | `unitsSoldClicks14d` | 14天归因总销售件数 | 所有商品件数之和 | INTEGER |
| 23 | "品牌新买家"订单量 | `newToBrandPurchases14d` | NTB 订单数 | 过去12个月未买过的客户订单 | INTEGER |
| 24 | "品牌新买家"订单百分比 | `newToBrandPurchasesPercentage14d` | NTB 订单占比 | `NTB订单 / 总订单 * 100` | DECIMAL |
| 25 | "品牌新买家"销售额 | `newToBrandSales14d` | NTB 销售额 | NTB 归因销售合计 | CURRENCY |
| 26 | "品牌新买家"销售额百分比 | `newToBrandSalesPercentage14d` | NTB 销售额占比 | `NTB销售额 / 总销售额 * 100` | DECIMAL |
| 27 | "品牌新买家"销量 | `newToBrandUnitsSold14d` | NTB 销量 | NTB 归因件数合计 | INTEGER |
| 28 | "品牌新买家"销量百分比 | `newToBrandUnitsSoldPercentage14d` | NTB 销量占比 | `NTB销量 / 总销量 * 100` | DECIMAL |
| 29 | 广告活动开始时间 | `startDate` | 广告活动开始日期 | -- | DATE |
| 30 | 广告活动结束时间 | `endDate` | 广告活动结束日期 | -- | DATE |
| 31 | 广告组运行状态 | `adGroupStatus` | 已开启/已暂停 | -- | STRING |
| 32 | 广告活动ID | `campaignId` | 广告活动唯一标识 | -- | STRING |
| 33 | 广告组ID | `adGroupId` | 广告组唯一标识 | -- | STRING |

> **Sources**: [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields), [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/)

---

## SB-4. 广告产品报告 (AdProduct)

- **API reportTypeId**: `sbAdvertisedProduct`
- **粒度**: 按 ASIN/SKU 维度
- **赛狐导出文件**: `SB-AdProduct_*.xlsx` (35 列)
- **特点**: 增加 ASIN、SKU 维度 + 广告产品ID; 无视频指标

### SB AdProduct 报告独有维度

| 官方字段名 | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `asin` | ASIN | 广告商品的 Amazon Standard Identification Number | STRING | [Scaleleap](https://amazon-advertising-api-sdk.scaleleap.org) |
| `sku` | SKU | 广告商品的 Stock Keeping Unit | STRING | [Scaleleap](https://amazon-advertising-api-sdk.scaleleap.org) |
| `reportingAdProductId` | 广告产品ID | 广告产品唯一标识 (SB 的广告实体) | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |

### SB AdProduct 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 计算方式 | 数据类型 |
|---|-----------|----------------|------|----------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | -- | STRING |
| 2 | 日期 | `date` | 数据日期 | -- | DATE |
| 3 | ASIN | `asin` | 广告商品 ASIN | -- | STRING |
| 4 | SKU | `sku` | 广告商品 SKU | -- | STRING |
| 5 | 广告组 | `adGroupName` | 广告组名称 | -- | STRING |
| 6 | 广告活动 | `campaignName` | 广告活动名称 | -- | STRING |
| 7 | 广告花费 | `cost` | 总广告花费 | -- | CURRENCY |
| 8 | 广告曝光量 | `impressions` | 广告展示总次数 | 计数器 | INTEGER |
| 9 | 可见展示次数 | `viewableImpressions` | 符合 MRC 标准的可见展示 | 至少50%面积可见>=1秒 | INTEGER |
| 10 | 广告点击量 | `clicks` | 广告点击总次数 | 计数器 | INTEGER |
| 11 | CPC | `costPerClick` | 平均单次点击成本 | `cost / clicks` | CURRENCY |
| 12 | VCPM | `costPerThousandViewableImpressions` | 每千次可见展示成本 | `(cost / viewIimps) * 1000` | CURRENCY |
| 13 | 广告点击率 | `clickThroughRate` (CTR) | 展示转化为点击的比率 | `clicks / impressions` | DECIMAL |
| 14 | 商品详情页浏览量 (DPV) | `detailPageViews` (DPV) | 广告点击后到达详情页的次数 | 详情页浏览计数 | INTEGER |
| 15 | 广告转化率 | `conversionRate14d` (CVR) | 点击转化为订单的比率 | `purchases14d / clicks` | DECIMAL |
| 16 | ACoS | `acos14d` | 广告销售成本比 | `(cost / sales14d) * 100` | DECIMAL |
| 17 | ROAS | `roas14d` | 广告投资回报率 | `sales14d / cost` | DECIMAL |
| 18 | 广告订单量 | `purchases14d` | 14天归因总订单数 | 归因计数器 | INTEGER |
| 19 | 本广告产品订单量 | `attributedConversions14dSameSKU` | 同 SKU 归因订单数 | 仅广告商品 | INTEGER |
| 20 | 其他产品广告订单量 | `attributedConversions14dOtherSKU` | 其他 SKU 归因订单数 | 品牌光环 | INTEGER |
| 21 | 广告销售额 | `sales14d` | 14天归因总销售额 | 归因售价总和 | CURRENCY |
| 22 | 本广告产品销售额 | `attributedSales14dSameSKU` | 同 SKU 归因销售额 | 仅广告商品 | CURRENCY |
| 23 | 其他产品广告销售额 | `attributedSales14dOtherSKU` | 其他 SKU 归因销售额 | 品牌光环 | CURRENCY |
| 24 | 广告销量 | `unitsSoldClicks14d` | 14天归因总销售件数 | 所有商品件数之和 | INTEGER |
| 25 | "品牌新买家"订单量 | `newToBrandPurchases14d` | NTB 订单数 | 新客订单计数 | INTEGER |
| 26 | "品牌新买家"订单百分比 | `newToBrandPurchasesPercentage14d` | NTB 订单占比 | `NTB订单 / 总订单 * 100` | DECIMAL |
| 27 | "品牌新买家"销售额 | `newToBrandSales14d` | NTB 销售额 | NTB 归因销售合计 | CURRENCY |
| 28 | "品牌新买家"销售额百分比 | `newToBrandSalesPercentage14d` | NTB 销售额占比 | `NTB销售额 / 总销售额 * 100` | DECIMAL |
| 29 | "品牌新买家"销量 | `newToBrandUnitsSold14d` | NTB 销量 | NTB 归因件数合计 | INTEGER |
| 30 | "品牌新买家"销量百分比 | `newToBrandUnitsSoldPercentage14d` | NTB 销量占比 | `NTB销量 / 总销量 * 100` | DECIMAL |
| 31 | 广告活动开始时间 | `startDate` | 广告活动开始日期 | -- | DATE |
| 32 | 广告活动结束时间 | `endDate` | 广告活动结束日期 | -- | DATE |
| 33 | 广告活动ID | `campaignId` | 广告活动唯一标识 | -- | STRING |
| 34 | 广告组ID | `adGroupId` | 广告组唯一标识 | -- | STRING |
| 35 | 广告产品ID | `reportingAdProductId` | 广告产品唯一标识 | -- | STRING |

> **Sources**: [Scaleleap SDK](https://amazon-advertising-api-sdk.scaleleap.org), [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields)

---

## SB-5. 广告位报告 (Placement)

- **API reportTypeId**: `sbPlacement` (通过 `segment: placement` 获取) [推断]
- **粒度**: 按 `placement` 细分
- **赛狐导出文件**: `SB-Placement_*.xlsx` (41 列)
- **特点**: 包含视频指标 + 品牌新买家指标 + **品牌搜索次数** (SB 独有); 无广告组维度

### SB Placement 报告独有维度

| 官方字段名 | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `placement` | 广告位 | SB 广告投放的具体位置分类 | STRING | [Amazon Placement Help](https://advertising.amazon.ca/help/G89VFUTQUWFFN2VU) |
| `brandSearchCount` | 品牌搜索次数 | 广告展示后用户搜索品牌名称的次数 (品牌认知度指标) [推断] | INTEGER | [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/) |

### SB Placement 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 计算方式 | 数据类型 |
|---|-----------|----------------|------|----------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | -- | STRING |
| 2 | 日期 | `date` | 数据日期 | -- | DATE |
| 3 | 广告位 | `placement` | SB 广告位细分 | -- | STRING |
| 4 | 广告活动 | `campaignName` | 广告活动名称 | -- | STRING |
| 5 | 广告花费 | `cost` | 总广告花费 | -- | CURRENCY |
| 6 | 广告曝光量 | `impressions` | 广告展示总次数 | 计数器 | INTEGER |
| 7 | 广告点击量 | `clicks` | 广告点击总次数 | 计数器 | INTEGER |
| 8 | CPC | `costPerClick` | 平均单次点击成本 | `cost / clicks` | CURRENCY |
| 9 | 广告点击率 | `clickThroughRate` (CTR) | 展示转化为点击的比率 | `clicks / impressions` | DECIMAL |
| 10 | 广告转化率 | `conversionRate14d` (CVR) | 点击转化为订单的比率 | `purchases14d / clicks` | DECIMAL |
| 11 | ACoS | `acos14d` | 广告销售成本比 | `(cost / sales14d) * 100` | DECIMAL |
| 12 | ROAS | `roas14d` | 广告投资回报率 | `sales14d / cost` | DECIMAL |
| 13 | 广告订单量 | `purchases14d` | 14天归因总订单数 | 归因计数器 | INTEGER |
| 14 | 本广告产品订单量 | `attributedConversions14dSameSKU` | 同 SKU 归因订单数 | 仅广告商品 | INTEGER |
| 15 | 其他产品广告订单量 | `attributedConversions14dOtherSKU` | 其他 SKU 归因订单数 | 品牌光环 | INTEGER |
| 16 | 广告销售额 | `sales14d` | 14天归因总销售额 | 归因售价总和 | CURRENCY |
| 17 | 本广告产品销售额 | `attributedSales14dSameSKU` | 同 SKU 归因销售额 | 仅广告商品 | CURRENCY |
| 18 | 其他产品广告销售额 | `attributedSales14dOtherSKU` | 其他 SKU 归因销售额 | 品牌光环 | CURRENCY |
| 19 | "品牌新买家"订单转化率 | `newToBrandConversionRate14d` | NTB 订单转化率 [推断] | NTB订单数 / 点击量 | DECIMAL |
| 20 | "品牌新买家"订单量 | `newToBrandPurchases14d` | NTB 订单数 | 新客订单计数 | INTEGER |
| 21 | "品牌新买家"订单占比 | `newToBrandPurchasesPercentage14d` | NTB 订单占比 | `NTB订单 / 总订单 * 100` | DECIMAL |
| 22 | "品牌新买家"销售额 | `newToBrandSales14d` | NTB 销售额 | NTB 归因销售合计 | CURRENCY |
| 23 | "品牌新买家"销售额百分比 | `newToBrandSalesPercentage14d` | NTB 销售额占比 | `NTB销售额 / 总销售额 * 100` | DECIMAL |
| 24 | "品牌新买家"销量 | `newToBrandUnitsSold14d` | NTB 销量 | NTB 归因件数合计 | INTEGER |
| 25 | "品牌新买家"销量占比 | `newToBrandUnitsSoldPercentage14d` | NTB 销量占比 | `NTB销量 / 总销量 * 100` | DECIMAL |
| 26 | 品牌搜索次数 | `brandSearchCount` | 广告展示后用户搜索品牌名称的次数 [推断] | 计数器 | INTEGER |
| 27 | VCTR | `videoClickThroughRate` | 视频点击率 | `clicks / viewableImpressions` | DECIMAL |
| 28 | 5s观看率 | `video5sViewRate` | 5秒观看率 [推断] | `video5sViews / viewableImpressions` | DECIMAL |
| 29 | 5s观看次数 | `video5sViews` | 观看满5秒的次数 | 计数器 | INTEGER |
| 30 | 1/4视频观看次数 | `videoFirstQuartileViews` | 观看至25%的次数 | 计数器 | INTEGER |
| 31 | 1/2视频观看次数 | `videoMidpointViews` | 观看至50%的次数 | 计数器 | INTEGER |
| 32 | 3/4视频观看次数 | `videoThirdQuartileViews` | 观看至75%的次数 | 计数器 | INTEGER |
| 33 | 视频取消静音 | `videoUnmutes` | 用户取消静音的次数 | 计数器 | INTEGER |
| 34 | 可见展示次数 | `viewableImpressions` | 符合 MRC 标准的可见展示 | 至少50%面积可见>=1秒 | INTEGER |
| 35 | 完整视频观看次数 | `videoCompleteViews` | 观看至100%的次数 | 计数器 | INTEGER |
| 36 | VTR | `videoThroughRate` | 完整观看率 | `videoCompleteViews / viewableImpressions` | DECIMAL |
| 37 | 广告活动开始时间 | `startDate` | 广告活动开始日期 | -- | DATE |
| 38 | 广告活动结束时间 | `endDate` | 广告活动结束日期 | -- | DATE |
| 39 | 广告活动运行状态 | `campaignStatus` | 已开启/已暂停 | -- | STRING |
| 40 | 广告活动ID | `campaignId` | 广告活动唯一标识 | -- | STRING |
| 41 | 广告销量 | `unitsSoldClicks14d` | 14天归因总销售件数 | 所有商品件数之和 | INTEGER |

> **Sources**: [Amazon Placement Help](https://advertising.amazon.ca/help/G89VFUTQUWFFN2VU), [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/)

---

## SB-6. 投放报告 (Targeting)

- **API reportTypeId**: `sbTargeting`
- **粒度**: 按 `targeting` + `matchType` 聚合
- **赛狐导出文件**: `SB-Targeting_*.xlsx` (43 列)
- **特点**: 包含视频指标 + 品牌新买家指标; 无 DPV/可见展示/VCPM (在 AdGroup/AdProduct 中)

### SB Targeting 报告独有维度

| 官方字段名 | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `targeting` | 投放 | 投放目标关键词文本或匹配方式名称 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `matchType` | 匹配类型 | 广泛匹配/词组匹配/精确匹配等 | STRING | [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/) |
| `targetId` | 广告投放ID | 投放目标唯一标识 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `targetingStatus` | 投放运行状态 | 已开启/已暂停 | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |

### SB Targeting 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 计算方式 | 数据类型 |
|---|-----------|----------------|------|----------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | -- | STRING |
| 2 | 日期 | `date` | 数据日期 | -- | DATE |
| 3 | 投放 | `targeting` / `keyword` | 投放目标关键词或匹配方式 | -- | STRING |
| 4 | 匹配类型 | `matchType` | 广泛/词组/精确匹配等 | -- | STRING |
| 5 | 广告活动 | `campaignName` | 广告活动名称 | -- | STRING |
| 6 | 广告组 | `adGroupName` | 广告组名称 | -- | STRING |
| 7 | 广告花费 | `cost` | 总广告花费 | -- | CURRENCY |
| 8 | 广告曝光量 | `impressions` | 广告展示总次数 | 计数器 | INTEGER |
| 9 | 广告点击量 | `clicks` | 广告点击总次数 | 计数器 | INTEGER |
| 10 | CPC | `costPerClick` | 平均单次点击成本 | `cost / clicks` | CURRENCY |
| 11 | 广告点击率 | `clickThroughRate` (CTR) | 展示转化为点击的比率 | `clicks / impressions` | DECIMAL |
| 12 | 广告转化率 | `conversionRate14d` (CVR) | 点击转化为订单的比率 | `purchases14d / clicks` | DECIMAL |
| 13 | ACoS | `acos14d` | 广告销售成本比 | `(cost / sales14d) * 100` | DECIMAL |
| 14 | ROAS | `roas14d` | 广告投资回报率 | `sales14d / cost` | DECIMAL |
| 15 | 广告销量 | `unitsSoldClicks14d` | 14天归因总销售件数 | 所有商品件数之和 | INTEGER |
| 16 | 广告订单量 | `purchases14d` | 14天归因总订单数 | 归因计数器 | INTEGER |
| 17 | 本广告产品订单量 | `attributedConversions14dSameSKU` | 同 SKU 归因订单数 | 仅广告商品 | INTEGER |
| 18 | 广告销售额 | `sales14d` | 14天归因总销售额 | 归因售价总和 | CURRENCY |
| 19 | 本广告产品销售额 | `attributedSales14dSameSKU` | 同 SKU 归因销售额 | 仅广告商品 | CURRENCY |
| 20 | 其他产品广告销售额 | `attributedSales14dOtherSKU` | 其他 SKU 归因销售额 | 品牌光环 | CURRENCY |
| 21 | "品牌新买家"订单转化率 | `newToBrandConversionRate14d` | NTB 订单转化率 [推断] | NTB订单数 / 点击量 | DECIMAL |
| 22 | "品牌新买家"订单量 | `newToBrandPurchases14d` | NTB 订单数 | 新客订单计数 | INTEGER |
| 23 | "品牌新买家"订单百分比 | `newToBrandPurchasesPercentage14d` | NTB 订单占比 | `NTB订单 / 总订单 * 100` | DECIMAL |
| 24 | "品牌新买家"销售额 | `newToBrandSales14d` | NTB 销售额 | NTB 归因销售合计 | CURRENCY |
| 25 | "品牌新买家"销售额百分比 | `newToBrandSalesPercentage14d` | NTB 销售额占比 | `NTB销售额 / 总销售额 * 100` | DECIMAL |
| 26 | "品牌新买家"销量 | `newToBrandUnitsSold14d` | NTB 销量 | NTB 归因件数合计 | INTEGER |
| 27 | "品牌新买家"销量占比 | `newToBrandUnitsSoldPercentage14d` | NTB 销量占比 | `NTB销量 / 总销量 * 100` | DECIMAL |
| 28 | VCTR | `videoClickThroughRate` | 视频点击率 | `clicks / viewableImpressions` | DECIMAL |
| 29 | 5s观看率 | `video5sViewRate` | 5秒观看率 [推断] | `video5sViews / viewableImpressions` | DECIMAL |
| 30 | 5s观看次数 | `video5sViews` | 观看满5秒的次数 | 计数器 | INTEGER |
| 31 | 1/4视频观看次数 | `videoFirstQuartileViews` | 观看至25%的次数 | 计数器 | INTEGER |
| 32 | 1/2视频观看次数 | `videoMidpointViews` | 观看至50%的次数 | 计数器 | INTEGER |
| 33 | 3/4视频观看次数 | `videoThirdQuartileViews` | 观看至75%的次数 | 计数器 | INTEGER |
| 34 | 视频取消静音 | `videoUnmutes` | 用户取消静音的次数 | 计数器 | INTEGER |
| 35 | 可见展示次数 | `viewableImpressions` | 符合 MRC 标准的可见展示 | 至少50%面积可见>=1秒 | INTEGER |
| 36 | 完整视频观看次数 | `videoCompleteViews` | 观看至100%的次数 | 计数器 | INTEGER |
| 37 | VTR | `videoThroughRate` | 完整观看率 | `videoCompleteViews / viewableImpressions` | DECIMAL |
| 38 | 广告活动开始时间 | `startDate` | 广告活动开始日期 | -- | DATE |
| 39 | 广告活动结束时间 | `endDate` | 广告活动结束日期 | -- | DATE |
| 40 | 投放运行状态 | `targetingStatus` | 已开启/已暂停 | -- | STRING |
| 41 | 广告活动ID | `campaignId` | 广告活动唯一标识 | -- | STRING |
| 42 | 广告组ID | `adGroupId` | 广告组唯一标识 | -- | STRING |
| 43 | 广告投放ID | `targetId` / `keywordId` | 投放目标唯一标识 | -- | STRING |

> **Sources**: [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview), [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/)

---

## SB-7. 搜索词报告 (SearchTerm)

- **API reportTypeId**: `sbSearchTerm`
- **粒度**: 按 `searchTerm` + `targeting` 聚合
- **赛狐导出文件**: `SB-SearchTerm_*.xlsx` (44 列)
- **特点**: 所有 SB 报告的列数最多 (44 列); 含搜索词展示排名/份额 + Portfolio名称/币种 + 视频指标 + NTB

### SB SearchTerm 报告独有维度

| 官方字段名 | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `searchTerm` | 用户搜索词 | 买家在 Amazon 搜索框中实际输入的搜索词 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `searchTermImpressionRank` | 搜索词展示量排名 | 该搜索词在所有搜索词中的展示量排名 | INTEGER | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `searchTermImpressionShare` | 搜索词展示份额 | 该搜索词的展示量占该词总可用展示量的百分比 | DECIMAL | [Sellegr8](https://docs.sellegr8.com/article/35-ads-performance-report-column-description) |
| `portfolioName` | 广告组合名称 | Portfolio 名称 | STRING | [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/) |
| `currency` | 币种 | 货币代码 (如 USD) | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |

### SB SearchTerm 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 计算方式 | 数据类型 |
|---|-----------|----------------|------|----------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | -- | STRING |
| 2 | 日期 | `date` | 数据日期 | -- | DATE |
| 3 | 用户搜索词 | `searchTerm` | 买家实际搜索词 | -- | STRING |
| 4 | 投放 | `targeting` / `keyword` | 投放目标关键词或匹配方式 | -- | STRING |
| 5 | 匹配类型 | `matchType` | 广泛/词组/精确匹配等 | -- | STRING |
| 6 | 广告活动 | `campaignName` | 广告活动名称 | -- | STRING |
| 7 | 广告组 | `adGroupName` | 广告组名称 | -- | STRING |
| 8 | 定位类型 | `targetingType` | 自动投放/手动投放 | -- | STRING |
| 9 | 广告花费 | `cost` | 总广告花费 | -- | CURRENCY |
| 10 | 广告曝光量 | `impressions` | 广告展示总次数 | 计数器 | INTEGER |
| 11 | 广告点击量 | `clicks` | 广告点击总次数 | 计数器 | INTEGER |
| 12 | CPC | `costPerClick` | 平均单次点击成本 | `cost / clicks` | CURRENCY |
| 13 | 广告点击率 | `clickThroughRate` (CTR) | 展示转化为点击的比率 | `clicks / impressions` | DECIMAL |
| 14 | 广告转化率 | `conversionRate14d` (CVR) | 点击转化为订单的比率 | `purchases14d / clicks` | DECIMAL |
| 15 | ACoS | `acos14d` | 广告销售成本比 | `(cost / sales14d) * 100` | DECIMAL |
| 16 | ROAS | `roas14d` | 广告投资回报率 | `sales14d / cost` | DECIMAL |
| 17 | 广告订单量 | `purchases14d` | 14天归因总订单数 | 归因计数器 | INTEGER |
| 18 | 广告销售额 | `sales14d` | 14天归因总销售额 | 归因售价总和 | CURRENCY |
| 19 | "品牌新买家"订单转化率 | `newToBrandConversionRate14d` | NTB 订单转化率 [推断] | NTB订单数 / 点击量 | DECIMAL |
| 20 | "品牌新买家"订单量 | `newToBrandPurchases14d` | NTB 订单数 | 新客订单计数 | INTEGER |
| 21 | "品牌新买家"订单占比 | `newToBrandPurchasesPercentage14d` | NTB 订单占比 | `NTB订单 / 总订单 * 100` | DECIMAL |
| 22 | "品牌新买家"销售额 | `newToBrandSales14d` | NTB 销售额 | NTB 归因销售合计 | CURRENCY |
| 23 | "品牌新买家"销售额百分比 | `newToBrandSalesPercentage14d` | NTB 销售额占比 | `NTB销售额 / 总销售额 * 100` | DECIMAL |
| 24 | "品牌新买家"销量 | `newToBrandUnitsSold14d` | NTB 销量 | NTB 归因件数合计 | INTEGER |
| 25 | "品牌新买家"销量占比 | `newToBrandUnitsSoldPercentage14d` | NTB 销量占比 | `NTB销量 / 总销量 * 100` | DECIMAL |
| 26 | 搜索词展示量排名 | `searchTermImpressionRank` | 该词在所有搜索词中的展示排名 | 排名计数 | INTEGER |
| 27 | 搜索词展示份额 | `searchTermImpressionShare` | 该词的展示量占该词总可用展示百分比 | 份额计算 | DECIMAL |
| 28 | VCTR | `videoClickThroughRate` | 视频点击率 | `clicks / viewableImpressions` | DECIMAL |
| 29 | 5s观看率 | `video5sViewRate` | 5秒观看率 [推断] | `video5sViews / viewableImpressions` | DECIMAL |
| 30 | 5s观看次数 | `video5sViews` | 观看满5秒的次数 | 计数器 | INTEGER |
| 31 | 1/4视频观看次数 | `videoFirstQuartileViews` | 观看至25%的次数 | 计数器 | INTEGER |
| 32 | 1/2视频观看次数 | `videoMidpointViews` | 观看至50%的次数 | 计数器 | INTEGER |
| 33 | 3/4视频观看次数 | `videoThirdQuartileViews` | 观看至75%的次数 | 计数器 | INTEGER |
| 34 | 视频取消静音 | `videoUnmutes` | 用户取消静音的次数 | 计数器 | INTEGER |
| 35 | 可见展示次数 | `viewableImpressions` | 符合 MRC 标准的可见展示 | 至少50%面积可见>=1秒 | INTEGER |
| 36 | 完整视频观看次数 | `videoCompleteViews` | 观看至100%的次数 | 计数器 | INTEGER |
| 37 | VTR | `videoThroughRate` | 完整观看率 | `videoCompleteViews / viewableImpressions` | DECIMAL |
| 38 | 广告组合名称 | `portfolioName` | Portfolio 名称 | -- | STRING |
| 39 | 币种 | `currency` | 货币代码 (如 USD) | -- | STRING |
| 40 | 广告活动开始时间 | `startDate` | 广告活动开始日期 | -- | DATE |
| 41 | 广告活动结束时间 | `endDate` | 广告活动结束日期 | -- | DATE |
| 42 | 广告活动ID | `campaignId` | 广告活动唯一标识 | -- | STRING |
| 43 | 广告组ID | `adGroupId` | 广告组唯一标识 | -- | STRING |
| 44 | 广告投放ID | `targetId` / `keywordId` | 投放目标唯一标识 | -- | STRING |

> **Sources**: [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview), [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields), [Sellegr8](https://docs.sellegr8.com/article/35-ads-performance-report-column-description)

---

## SB-8. 已购产品报告 (PurchasedItem)

- **API reportTypeId**: `sbPurchasedProduct`
- **粒度**: 按已购 ASIN + 广告活动/广告组聚合
- **赛狐导出文件**: `SB-PurchasedItem_*.xlsx` (19 列)
- **特点**: 无流量指标 (无曝光/点击/花费/CPC/CTR); 含 NTB 指标; 含引流类型 (SB独有)

### SB PurchasedItem 报告独有维度

| 官方字段名 | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `purchasedAsin` | 已购ASIN | 实际被购买的 ASIN (可能等于或不等于广告 ASIN) | STRING | [GitHub Discussion #173](https://github.com/amzn/ads-advanced-tools-docs/discussions/173) |
| `referralType` | 引流类型 | 引流类型，指示购买是通过何种方式被广告引流的 [推断] | STRING | [推断] |

> **注意**: SB PurchasedItem 报告中不含 `advertisedAsin`/`advertisedSku` 列 (与 SP 不同)，而是直接显示 `purchasedAsin` (已购ASIN)。

### SB PurchasedItem 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 计算方式 | 数据类型 |
|---|-----------|----------------|------|----------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | -- | STRING |
| 2 | 日期 | `date` | 数据日期 | -- | DATE |
| 3 | 已购ASIN | `purchasedAsin` | 实际被购买的 ASIN | -- | STRING |
| 4 | 引流类型 | `referralType` | 广告引流类型 [推断] | -- | STRING |
| 5 | 广告组 | `adGroupName` | 广告组名称 | -- | STRING |
| 6 | 广告活动 | `campaignName` | 广告活动名称 | -- | STRING |
| 7 | 广告活动开始时间 | `startDate` | 广告活动开始日期 | -- | DATE |
| 8 | 广告活动结束时间 | `endDate` | 广告活动结束日期 | -- | DATE |
| 9 | 广告订单量 | `purchases14d` | 14天归因总订单数 | 归因计数器 | INTEGER |
| 10 | 广告销售额 | `sales14d` | 14天归因总销售额 | 归因售价总和 | CURRENCY |
| 11 | 广告销量 | `unitsSoldClicks14d` | 14天归因总销售件数 | 所有商品件数之和 | INTEGER |
| 12 | "品牌新买家"订单量 | `newToBrandPurchases14d` | NTB 订单数 | 新客订单计数 | INTEGER |
| 13 | "品牌新买家"订单百分比 | `newToBrandPurchasesPercentage14d` | NTB 订单占比 | `NTB订单 / 总订单 * 100` | DECIMAL |
| 14 | "品牌新买家"销售额 | `newToBrandSales14d` | NTB 销售额 | NTB 归因销售合计 | CURRENCY |
| 15 | "品牌新买家"销售额百分比 | `newToBrandSalesPercentage14d` | NTB 销售额占比 | `NTB销售额 / 总销售额 * 100` | DECIMAL |
| 16 | "品牌新买家"销量 | `newToBrandUnitsSold14d` | NTB 销量 | NTB 归因件数合计 | INTEGER |
| 17 | "品牌新买家"销量百分比 | `newToBrandUnitsSoldPercentage14d` | NTB 销量占比 | `NTB销量 / 总销量 * 100` | DECIMAL |
| 18 | 广告活动ID | `campaignId` | 广告活动唯一标识 | -- | STRING |
| 19 | 广告组ID | `adGroupId` | 广告组唯一标识 | -- | STRING |

> **Sources**: [GitHub Discussion #173](https://github.com/amzn/ads-advanced-tools-docs/discussions/173), [Reason Automation](https://help.reasonautomation.com/sponsored-advertising/sp-purchased-products)

---

# Sponsored Display (SD) -- 展示型推广

## SD-9. 概述与通用字段

### 9.1 SD 报告概述

Sponsored Display (展示型推广) 是 Amazon 的受众和商品定向广告产品，可在 Amazon 站内和站外投放。与 SP/SB 相比，SD 的特点:

- **两种费用类型**: vCPM (按可见展示付费) 和 CPC (按点击付费)
- **竞价优化**: SD_REACH (覆盖优化) 和 SD_CONVERSION (转化优化)
- **额外转化指标**: CPA (单次获客成本)、ACoTS (广告花费占总销售额比)、ASoTS (广告销售额占总销售额比)
- **NTB 指标**: 同 SB，SD 也包含品牌新买家指标
- **归因窗口**: SD 使用 **14 天** 点击归因窗口，某些情况下包含展示归因

### 9.2 SD 报告类型总览

| 报告类型 | API reportTypeId | 赛狐文件名 | 列数 | 粒度 |
|----------|-----------------|-----------|------|------|
| Campaign | `sdCampaigns` | `SD-Campaign_*.xlsx` | 33 | 按广告活动 |
| AdGroup | `sdAdGroups` | `SD-AdGroup_*.xlsx` | 35 | 按广告组 |
| AdProduct | `sdAdvertisedProduct` | `SD-AdProduct_*.xlsx` | 38 | 按 ASIN/SKU |
| Targeting | `sdTargeting` | `SD-Targeting_*.xlsx` | 32 | 按投放目标 |
| PurchasedItem | `sdPurchasedProduct` | `SD-PurchasedItem_*.xlsx` | 13 | 按已购 ASIN |

### 9.3 SD 通用标识字段

| 官方字段名 (API v3) | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `date` | 日期 / 店铺名称 (*注) | 数据日期 (YYYY-MM-DD) / 店铺名称 | DATE / STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `campaignName` | 广告活动 | 广告活动名称 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `campaignId` | 广告活动ID | 广告活动唯一标识 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `adGroupName` | 广告组 | 广告组名称 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `adGroupId` | 广告组ID | 广告组唯一标识 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `campaignStatus` | 广告活动运行状态 | 已开启/已暂停/已归档 | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `adGroupStatus` | 广告组运行状态 | 已开启/已暂停 | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `startDate` | 广告活动开始时间 | 广告活动开始日期 | DATE | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `endDate` | 广告活动结束时间 | 广告活动结束日期 | DATE | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `portfolioId` | 广告组合ID | Portfolio 唯一标识 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `targeting` | 投放 | 投放目标名称 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `targetId` | 广告投放ID | 投放目标唯一标识 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `targetingStatus` | 投放运行状态 | 已开启/已暂停 | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `asin` | ASIN / 已购ASIN | 广告商品或已购商品 ASIN | STRING | [Scaleleap](https://amazon-advertising-api-sdk.scaleleap.org) |
| `sku` | SKU | 广告商品或已购商品 SKU | STRING | [Scaleleap](https://amazon-advertising-api-sdk.scaleleap.org) |
| `reportingAdProductId` | 广告产品ID | 广告产品唯一标识 | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `adProductStatus` | 广告产品运行状态 | 已开启/已暂停 | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |

> ***注**: SD-Targeting 报告第1列名为"店铺名称"(非"店铺")。SD-PurchasedItem 中有"其他ASIN"列。

### 9.4 SD 通用指标字段

#### 流量指标

| 官方字段名 (API v3) | 赛狐中文名 | 定义 | 计算方式 | 数据类型 | 来源 |
|---|---|---|---|---|---|
| `impressions` | 广告曝光量 | 广告展示的总次数 | 计数器 | INTEGER | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `clicks` | 广告点击量 | 广告被点击的总次数 | 计数器 | INTEGER | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `cost` | 广告花费 | 广告产生的总费用 | CPC: 点击成本之和; vCPM: 按千次可见展示计费 | CURRENCY | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `costPerClick` (CPC) | CPC | 平均单次点击成本 | `cost / clicks` | CURRENCY | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `clickThroughRate` (CTR) | 广告点击率 | 广告被点击的概率 | `clicks / impressions` | DECIMAL | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `viewableImpressions` | 可见展示次数 | 符合 MRC 可见性标准的展示次数 | 至少50%面积可见持续>=1秒 | INTEGER | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `costPerThousandViewableImpressions` (VCPM) | VCPM | 每千次可见展示成本 | `(cost / viewableImpressions) * 1000` | CURRENCY | [Amazon Marketing Stream SD](https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sd-performance) |
| `detailPageViews` (DPV) | 商品详情页浏览量 (DPV) | 广告点击后到达商品详情页的次数 | 详情页浏览计数 | INTEGER | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |

#### 转化指标

| 官方字段名 (API v3) | 赛狐中文名 | 定义 | 计算方式 | 数据类型 | 来源 |
|---|---|---|---|---|---|
| `purchases14d` | 广告订单量 | 14天归因窗口内广告带来的总订单数 | 归因计数器 | INTEGER | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `attributedConversions14dSameSKU` | 本广告产品订单量 | 购买商品=广告商品的订单数 | 仅同 SKU | INTEGER | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `attributedConversions14dOtherSKU` | 其他产品广告订单量 | 购买商品!=广告商品的订单数 | 品牌光环 | INTEGER | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `sales14d` | 广告销售额 | 14天归因窗口内广告带来的总销售额 | 归因售价总和 | CURRENCY | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `attributedSales14dSameSKU` | 本广告产品销售额 | 同 SKU 归因销售额 | 仅广告商品 | CURRENCY | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `attributedSales14dOtherSKU` | 其他产品广告销售额 | 其他 SKU 归因销售额 | 品牌光环 | CURRENCY | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `unitsSoldClicks14d` | 广告销量 | 14天归因窗口内总销售件数 | 所有商品件数之和 | INTEGER | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |

#### 效率指标

| 官方字段名 (API v3) | 赛狐中文名 | 定义 | 计算方式 | 数据类型 | 来源 |
|---|---|---|---|---|---|
| `acos14d` | ACoS | 广告销售成本比 | `(cost / sales14d) * 100` | DECIMAL | [Amazon ACoS Help](https://advertising.amazon.com/help/G96BDERJLNQGW2Y3) |
| `roas14d` | ROAS | 广告投资回报率 | `sales14d / cost` | DECIMAL | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `conversionRate14d` | 广告转化率 | 点击转化为订单的比率 | `(purchases14d / clicks) * 100` | DECIMAL | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |

#### SD 独有维度

| 官方字段名 (API v3) | 赛狐中文名 | 定义 | 说明 | 数据类型 | 来源 |
|---|---|---|---|---|---|
| `costType` | 费用类型 | 计费方式 | `VCPM` = 按千次可见展示付费; `CPC` = 按点击付费 | STRING | [Adverity](https://docs.adverity.com/reference/amazon-ads-fields.html) |
| `bidOptimization` | 竞价优化 | 竞价优化策略 | `SD_REACH` = 覆盖优化 (最大化展示覆盖); `SD_CONVERSION` = 转化优化 (最大化转化) | STRING | [Adverity](https://docs.adverity.com/reference/amazon-ads-fields.html) |

### 9.5 SD 费用类型 (Cost Type) 详解

| 赛狐中文值 | 英文官方值 | 说明 | 竞价策略 |
|-----------|-----------|------|----------|
| VCPM | `vcpm` | 按千次可见展示付费。即使无点击也付费。 | 适用于品牌曝光和覆盖目标。 |
| CPC | `cpc` | 按点击付费。仅当用户点击广告时付费。 | 适用于转化驱动的目标。 |

> 赛狐导出样例: SD Campaign `VCPM` (大写), SD AdGroup `vcpm` (小写)，大小写不一致属赛狐内部格式化问题。

### 9.6 SD 竞价优化 (Bid Optimization) 详解

| 赛狐中文值 | 英文官方值 | 说明 |
|-----------|-----------|------|
| (空) | -- | 未设置竞价优化，使用默认策略 |
| SD_REACH | `SD_REACH` | 覆盖优化: 系统优先最大化广告的可见展示覆盖范围 |
| SD_CONVERSION | `SD_CONVERSION` | 转化优化: 系统优先最大化广告带来的转化 |

> 赛狐导出样例: SD AdProduct 中 `SD_REACH` 值，SD Campaign 中该项为空。

---

## SD-10. 广告活动报告 (Campaign)

- **API reportTypeId**: `sdCampaigns`
- **粒度**: 按 `campaign` 聚合
- **赛狐导出文件**: `SD-Campaign_*.xlsx` (33 列)
- **特点**: 含费用类型 + VCPM/DPV/可见展示次数 + NTB 指标; 无视频指标

### SD Campaign 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 计算方式 | 数据类型 |
|---|-----------|----------------|------|----------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | -- | STRING |
| 2 | 日期 | `date` | 数据日期 | -- | DATE |
| 3 | 广告活动 | `campaignName` | 广告活动名称 | -- | STRING |
| 4 | 费用类型 | `costType` | 计费方式: VCPM 或 CPC | -- | STRING |
| 5 | 广告花费 | `cost` | 总广告花费 | -- | CURRENCY |
| 6 | 广告曝光量 | `impressions` | 广告展示总次数 | 计数器 | INTEGER |
| 7 | 可见展示次数 | `viewableImpressions` | 符合 MRC 标准的可见展示 | 至少50%面积可见>=1秒 | INTEGER |
| 8 | 广告点击量 | `clicks` | 广告点击总次数 | 计数器 | INTEGER |
| 9 | CPC | `costPerClick` | 平均单次点击成本 | `cost / clicks` | CURRENCY |
| 10 | VCPM | `costPerThousandViewableImpressions` | 每千次可见展示成本 | `(cost / viewIimps) * 1000` | CURRENCY |
| 11 | 广告点击率 | `clickThroughRate` (CTR) | 展示转化为点击的比率 | `clicks / impressions` | DECIMAL |
| 12 | 商品详情页浏览量 (DPV) | `detailPageViews` (DPV) | 广告点击后到达详情页的次数 | 详情页浏览计数 | INTEGER |
| 13 | 广告转化率 | `conversionRate14d` (CVR) | 点击转化为订单的比率 | `purchases14d / clicks` | DECIMAL |
| 14 | ACoS | `acos14d` | 广告销售成本比 | `(cost / sales14d) * 100` | DECIMAL |
| 15 | ROAS | `roas14d` | 广告投资回报率 | `sales14d / cost` | DECIMAL |
| 16 | 广告订单量 | `purchases14d` | 14天归因总订单数 | 归因计数器 | INTEGER |
| 17 | 本广告产品订单量 | `attributedConversions14dSameSKU` | 同 SKU 归因订单数 | 仅广告商品 | INTEGER |
| 18 | 其他产品广告订单量 | `attributedConversions14dOtherSKU` | 其他 SKU 归因订单数 | 品牌光环 | INTEGER |
| 19 | 广告销售额 | `sales14d` | 14天归因总销售额 | 归因售价总和 | CURRENCY |
| 20 | 本广告产品销售额 | `attributedSales14dSameSKU` | 同 SKU 归因销售额 | 仅广告商品 | CURRENCY |
| 21 | 其他产品广告销售额 | `attributedSales14dOtherSKU` | 其他 SKU 归因销售额 | 品牌光环 | CURRENCY |
| 22 | 广告销量 | `unitsSoldClicks14d` | 14天归因总销售件数 | 所有商品件数之和 | INTEGER |
| 23 | "品牌新买家"订单量 | `newToBrandPurchases14d` | NTB 订单数 | 新客订单计数 | INTEGER |
| 24 | "品牌新买家"订单百分比 | `newToBrandPurchasesPercentage14d` | NTB 订单占比 | `NTB订单 / 总订单 * 100` | DECIMAL |
| 25 | "品牌新买家"销售额 | `newToBrandSales14d` | NTB 销售额 | NTB 归因销售合计 | CURRENCY |
| 26 | "品牌新买家"销售额百分比 | `newToBrandSalesPercentage14d` | NTB 销售额占比 | `NTB销售额 / 总销售额 * 100` | DECIMAL |
| 27 | "品牌新买家"销量 | `newToBrandUnitsSold14d` | NTB 销量 | NTB 归因件数合计 | INTEGER |
| 28 | "品牌新买家"销量百分比 | `newToBrandUnitsSoldPercentage14d` | NTB 销量占比 | `NTB销量 / 总销量 * 100` | DECIMAL |
| 29 | 广告活动开始时间 | `startDate` | 广告活动开始日期 | -- | DATE |
| 30 | 广告活动结束时间 | `endDate` | 广告活动结束日期 | -- | DATE |
| 31 | 广告活动运行状态 | `campaignStatus` | 已开启/已暂停/已归档 | -- | STRING |
| 32 | 广告组合ID | `portfolioId` | 所属 Portfolio ID | -- | STRING |
| 33 | 广告活动ID | `campaignId` | 广告活动唯一标识 | -- | STRING |

> **Sources**: [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview), [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields), [Adverity](https://docs.adverity.com/reference/amazon-ads-fields.html)

---

## SD-11. 广告组报告 (AdGroup)

- **API reportTypeId**: `sdAdGroups` (通过 `sdCampaigns` with `groupBy: adGroup` 获取) [推断]
- **粒度**: 按 `adGroup` 聚合
- **赛狐导出文件**: `SD-AdGroup_*.xlsx` (35 列)
- **特点**: 增加费用类型 + 竞价优化维度; 与 SD Campaign 指标集相同

### SD AdGroup 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 计算方式 | 数据类型 |
|---|-----------|----------------|------|----------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | -- | STRING |
| 2 | 日期 | `date` | 数据日期 | -- | DATE |
| 3 | 广告组 | `adGroupName` | 广告组名称 | -- | STRING |
| 4 | 广告活动 | `campaignName` | 广告活动名称 | -- | STRING |
| 5 | 费用类型 | `costType` | 计费方式: VCPM 或 CPC | -- | STRING |
| 6 | 竞价优化 | `bidOptimization` | 竞价策略: SD_REACH 或 SD_CONVERSION | -- | STRING |
| 7 | 广告花费 | `cost` | 总广告花费 | -- | CURRENCY |
| 8 | 广告曝光量 | `impressions` | 广告展示总次数 | 计数器 | INTEGER |
| 9 | 可见展示次数 | `viewableImpressions` | 符合 MRC 标准的可见展示 | 至少50%面积可见>=1秒 | INTEGER |
| 10 | 广告点击量 | `clicks` | 广告点击总次数 | 计数器 | INTEGER |
| 11 | CPC | `costPerClick` | 平均单次点击成本 | `cost / clicks` | CURRENCY |
| 12 | VCPM | `costPerThousandViewableImpressions` | 每千次可见展示成本 | `(cost / viewIimps) * 1000` | CURRENCY |
| 13 | 广告点击率 | `clickThroughRate` (CTR) | 展示转化为点击的比率 | `clicks / impressions` | DECIMAL |
| 14 | 商品详情页浏览量 (DPV) | `detailPageViews` (DPV) | 广告点击后到达详情页的次数 | 详情页浏览计数 | INTEGER |
| 15 | 广告转化率 | `conversionRate14d` (CVR) | 点击转化为订单的比率 | `purchases14d / clicks` | DECIMAL |
| 16 | ACoS | `acos14d` | 广告销售成本比 | `(cost / sales14d) * 100` | DECIMAL |
| 17 | ROAS | `roas14d` | 广告投资回报率 | `sales14d / cost` | DECIMAL |
| 18 | 广告订单量 | `purchases14d` | 14天归因总订单数 | 归因计数器 | INTEGER |
| 19 | 本广告产品订单量 | `attributedConversions14dSameSKU` | 同 SKU 归因订单数 | 仅广告商品 | INTEGER |
| 20 | 其他产品广告订单量 | `attributedConversions14dOtherSKU` | 其他 SKU 归因订单数 | 品牌光环 | INTEGER |
| 21 | 广告销售额 | `sales14d` | 14天归因总销售额 | 归因售价总和 | CURRENCY |
| 22 | 本广告产品销售额 | `attributedSales14dSameSKU` | 同 SKU 归因销售额 | 仅广告商品 | CURRENCY |
| 23 | 其他产品广告销售额 | `attributedSales14dOtherSKU` | 其他 SKU 归因销售额 | 品牌光环 | CURRENCY |
| 24 | 广告销量 | `unitsSoldClicks14d` | 14天归因总销售件数 | 所有商品件数之和 | INTEGER |
| 25 | "品牌新买家"订单量 | `newToBrandPurchases14d` | NTB 订单数 | 新客订单计数 | INTEGER |
| 26 | "品牌新买家"订单百分比 | `newToBrandPurchasesPercentage14d` | NTB 订单占比 | `NTB订单 / 总订单 * 100` | DECIMAL |
| 27 | "品牌新买家"销售额 | `newToBrandSales14d` | NTB 销售额 | NTB 归因销售合计 | CURRENCY |
| 28 | "品牌新买家"销售额百分比 | `newToBrandSalesPercentage14d` | NTB 销售额占比 | `NTB销售额 / 总销售额 * 100` | DECIMAL |
| 29 | "品牌新买家"销量 | `newToBrandUnitsSold14d` | NTB 销量 | NTB 归因件数合计 | INTEGER |
| 30 | "品牌新买家"销量百分比 | `newToBrandUnitsSoldPercentage14d` | NTB 销量占比 | `NTB销量 / 总销量 * 100` | DECIMAL |
| 31 | 广告活动开始时间 | `startDate` | 广告活动开始日期 | -- | DATE |
| 32 | 广告活动结束时间 | `endDate` | 广告活动结束日期 | -- | DATE |
| 33 | 广告组运行状态 | `adGroupStatus` | 已开启/已暂停 | -- | STRING |
| 34 | 广告活动ID | `campaignId` | 广告活动唯一标识 | -- | STRING |
| 35 | 广告组ID | `adGroupId` | 广告组唯一标识 | -- | STRING |

> **Sources**: [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields), [Adverity](https://docs.adverity.com/reference/amazon-ads-fields.html)

---

## SD-12. 广告产品报告 (AdProduct)

- **API reportTypeId**: `sdAdvertisedProduct`
- **粒度**: 按 ASIN/SKU 维度
- **赛狐导出文件**: `SD-AdProduct_*.xlsx` (38 列)
- **特点**: 增加 ASIN、SKU 维度 + 广告产品ID + 费用类型 + 竞价优化

### SD AdProduct 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 计算方式 | 数据类型 |
|---|-----------|----------------|------|----------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | -- | STRING |
| 2 | 日期 | `date` | 数据日期 | -- | DATE |
| 3 | ASIN | `asin` | 广告商品 ASIN | -- | STRING |
| 4 | SKU | `sku` | 广告商品 SKU | -- | STRING |
| 5 | 广告组 | `adGroupName` | 广告组名称 | -- | STRING |
| 6 | 广告活动 | `campaignName` | 广告活动名称 | -- | STRING |
| 7 | 费用类型 | `costType` | 计费方式: vcpm/cpc | -- | STRING |
| 8 | 竞价优化 | `bidOptimization` | 竞价策略: SD_REACH/SD_CONVERSION | -- | STRING |
| 9 | 广告花费 | `cost` | 总广告花费 | -- | CURRENCY |
| 10 | 广告曝光量 | `impressions` | 广告展示总次数 | 计数器 | INTEGER |
| 11 | 可见展示次数 | `viewableImpressions` | 符合 MRC 标准的可见展示 | 至少50%面积可见>=1秒 | INTEGER |
| 12 | 广告点击量 | `clicks` | 广告点击总次数 | 计数器 | INTEGER |
| 13 | CPC | `costPerClick` | 平均单次点击成本 | `cost / clicks` | CURRENCY |
| 14 | VCPM | `costPerThousandViewableImpressions` | 每千次可见展示成本 | `(cost / viewIimps) * 1000` | CURRENCY |
| 15 | 广告点击率 | `clickThroughRate` (CTR) | 展示转化为点击的比率 | `clicks / impressions` | DECIMAL |
| 16 | 商品详情页浏览量 (DPV) | `detailPageViews` (DPV) | 广告点击后到达详情页的次数 | 详情页浏览计数 | INTEGER |
| 17 | 广告转化率 | `conversionRate14d` (CVR) | 点击转化为订单的比率 | `purchases14d / clicks` | DECIMAL |
| 18 | ACoS | `acos14d` | 广告销售成本比 | `(cost / sales14d) * 100` | DECIMAL |
| 19 | ROAS | `roas14d` | 广告投资回报率 | `sales14d / cost` | DECIMAL |
| 20 | 广告订单量 | `purchases14d` | 14天归因总订单数 | 归因计数器 | INTEGER |
| 21 | 本广告产品订单量 | `attributedConversions14dSameSKU` | 同 SKU 归因订单数 | 仅广告商品 | INTEGER |
| 22 | 其他产品广告订单量 | `attributedConversions14dOtherSKU` | 其他 SKU 归因订单数 | 品牌光环 | INTEGER |
| 23 | 广告销售额 | `sales14d` | 14天归因总销售额 | 归因售价总和 | CURRENCY |
| 24 | 本广告产品销售额 | `attributedSales14dSameSKU` | 同 SKU 归因销售额 | 仅广告商品 | CURRENCY |
| 25 | 其他产品广告销售额 | `attributedSales14dOtherSKU` | 其他 SKU 归因销售额 | 品牌光环 | CURRENCY |
| 26 | 广告销量 | `unitsSoldClicks14d` | 14天归因总销售件数 | 所有商品件数之和 | INTEGER |
| 27 | "品牌新买家"订单量 | `newToBrandPurchases14d` | NTB 订单数 | 新客订单计数 | INTEGER |
| 28 | "品牌新买家"订单百分比 | `newToBrandPurchasesPercentage14d` | NTB 订单占比 | `NTB订单 / 总订单 * 100` | DECIMAL |
| 29 | "品牌新买家"销售额 | `newToBrandSales14d` | NTB 销售额 | NTB 归因销售合计 | CURRENCY |
| 30 | "品牌新买家"销售额百分比 | `newToBrandSalesPercentage14d` | NTB 销售额占比 | `NTB销售额 / 总销售额 * 100` | DECIMAL |
| 31 | "品牌新买家"销量 | `newToBrandUnitsSold14d` | NTB 销量 | NTB 归因件数合计 | INTEGER |
| 32 | "品牌新买家"销量百分比 | `newToBrandUnitsSoldPercentage14d` | NTB 销量占比 | `NTB销量 / 总销量 * 100` | DECIMAL |
| 33 | 广告活动开始时间 | `startDate` | 广告活动开始日期 | -- | DATE |
| 34 | 广告活动结束时间 | `endDate` | 广告活动结束日期 | -- | DATE |
| 35 | 广告产品运行状态 | `adProductStatus` | 已开启/已暂停 | -- | STRING |
| 36 | 广告活动ID | `campaignId` | 广告活动唯一标识 | -- | STRING |
| 37 | 广告组ID | `adGroupId` | 广告组唯一标识 | -- | STRING |
| 38 | 广告产品ID | `reportingAdProductId` | 广告产品唯一标识 | -- | STRING |

> **Sources**: [Scaleleap SDK](https://amazon-advertising-api-sdk.scaleleap.org), [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields), [Adverity](https://docs.adverity.com/reference/amazon-ads-fields.html)

---

## SD-13. 投放报告 (Targeting)

- **API reportTypeId**: `sdTargeting`
- **粒度**: 按 `targeting` 聚合
- **赛狐导出文件**: `SD-Targeting_*.xlsx` (32 列)
- **特点**: 包含 SD 独有高级指标: **CPA**、**ACoTS**、**ASoTS**; 含 NTB 转化率; 无 DPV

### SD Targeting 报告独有指标

| 官方字段名 (API v3) | 赛狐中文名 | 定义 | 计算方式 | 数据类型 | 来源 |
|---|---|---|---|---|---|
| `costPerAcquisition` (CPA) | CPA | 单次获客成本 | `cost / purchases14d` | CURRENCY | [Adverity](https://docs.adverity.com/reference/amazon-ads-fields.html) |
| `advertisedCostOfTotalSales` (ACoTS) | ACoTS | 广告花费占总销售额比 | `(cost / totalSales) * 100` (含自然销售) [推断] | DECIMAL | [Adverity](https://docs.adverity.com/reference/amazon-ads-fields.html) |
| `advertisedShareOfTotalSales` (ASoTS) | ASoTS | 广告销售额占总销售额比 | `(sales14d / totalSales) * 100` [推断] | DECIMAL | [Adverity](https://docs.adverity.com/reference/amazon-ads-fields.html) |

### SD Targeting 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 计算方式 | 数据类型 |
|---|-----------|----------------|------|----------|----------|
| 1 | 店铺名称 | `[Sellfox 拼接]` | 店铺名称 (*注: 列名为"店铺名称"，非"店铺") | -- | STRING |
| 2 | 日期 | `date` | 数据日期 | -- | DATE |
| 3 | 投放 | `targeting` | 投放目标 (如 "您推广的商品") | -- | STRING |
| 4 | 广告组 | `adGroupName` | 广告组名称 | -- | STRING |
| 5 | 广告活动 | `campaignName` | 广告活动名称 | -- | STRING |
| 6 | 广告花费 | `cost` | 总广告花费 | -- | CURRENCY |
| 7 | 广告曝光量 | `impressions` | 广告展示总次数 | 计数器 | INTEGER |
| 8 | 广告点击量 | `clicks` | 广告点击总次数 | 计数器 | INTEGER |
| 9 | 广告点击率 | `clickThroughRate` (CTR) | 展示转化为点击的比率 | `clicks / impressions` | DECIMAL |
| 10 | CPA | `costPerAcquisition` (CPA) | 单次获客成本 | `cost / purchases14d` | CURRENCY |
| 11 | CPC | `costPerClick` | 平均单次点击成本 | `cost / clicks` | CURRENCY |
| 12 | 广告转化率 | `conversionRate14d` (CVR) | 点击转化为订单的比率 | `purchases14d / clicks` | DECIMAL |
| 13 | ACoS | `acos14d` | 广告销售成本比 | `(cost / sales14d) * 100` | DECIMAL |
| 14 | ROAS | `roas14d` | 广告投资回报率 | `sales14d / cost` | DECIMAL |
| 15 | ACoTS | `advertisedCostOfTotalSales` | 广告花费占总销售额比 (含自然销售) | `(cost / totalSales) * 100` | DECIMAL |
| 16 | ASoTS | `advertisedShareOfTotalSales` | 广告销售额占总销售额比 | `(sales14d / totalSales) * 100` | DECIMAL |
| 17 | 广告订单量 | `purchases14d` | 14天归因总订单数 | 归因计数器 | INTEGER |
| 18 | 本广告产品订单量 | `attributedConversions14dSameSKU` | 同 SKU 归因订单数 | 仅广告商品 | INTEGER |
| 19 | 广告销售额 | `sales14d` | 14天归因总销售额 | 归因售价总和 | CURRENCY |
| 20 | 本广告产品销售额 | `attributedSales14dSameSKU` | 同 SKU 归因销售额 | 仅广告商品 | CURRENCY |
| 21 | 广告销量 | `unitsSoldClicks14d` | 14天归因总销售件数 | 所有商品件数之和 | INTEGER |
| 22 | 可见展示次数 | `viewableImpressions` | 符合 MRC 标准的可见展示 | 至少50%面积可见>=1秒 | INTEGER |
| 23 | VCPM | `costPerThousandViewableImpressions` | 每千次可见展示成本 | `(cost / viewIimps) * 1000` | CURRENCY |
| 24 | "品牌新买家"订单转化率 | `newToBrandConversionRate14d` | NTB 订单转化率 [推断] | NTB订单数 / 点击量 | DECIMAL |
| 25 | "品牌新买家"订单量 | `newToBrandPurchases14d` | NTB 订单数 | 新客订单计数 | INTEGER |
| 26 | "品牌新买家"销售额 | `newToBrandSales14d` | NTB 销售额 | NTB 归因销售合计 | CURRENCY |
| 27 | 广告活动开始时间 | `startDate` | 广告活动开始日期 | -- | DATE |
| 28 | 广告活动结束时间 | `endDate` | 广告活动结束日期 | -- | DATE |
| 29 | 投放运行状态 | `targetingStatus` | 已开启/已暂停 | -- | STRING |
| 30 | 广告活动ID | `campaignId` | 广告活动唯一标识 | -- | STRING |
| 31 | 广告组ID | `adGroupId` | 广告组唯一标识 | -- | STRING |
| 32 | 广告投放ID | `targetId` | 投放目标唯一标识 | -- | STRING |

> **Sources**: [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview), [Adverity](https://docs.adverity.com/reference/amazon-ads-fields.html), [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields)

---

## SD-14. 已购产品报告 (PurchasedItem)

- **API reportTypeId**: `sdPurchasedProduct`
- **粒度**: 按已购 ASIN/SKU 聚合
- **赛狐导出文件**: `SD-PurchasedItem_*.xlsx` (13 列)
- **特点**: 最简洁的 SD 报告 (13 列); 无流量指标; 无 NTB 指标; 聚焦已购产品归属

### SD PurchasedItem 报告独有维度

| 官方字段名 | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `advertisedAsin` | ASIN | 广告商品 ASIN | STRING | [GitHub Discussion #173](https://github.com/amzn/ads-advanced-tools-docs/discussions/173) |
| `advertisedSku` | SKU | 广告商品 SKU | STRING | [GitHub Discussion #173](https://github.com/amzn/ads-advanced-tools-docs/discussions/173) |
| `purchasedAsin` | 其他ASIN | 实际被购买的非广告商品 ASIN (品牌光环) | STRING | [GitHub Discussion #173](https://github.com/amzn/ads-advanced-tools-docs/discussions/173) |

### SD PurchasedItem 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 计算方式 | 数据类型 |
|---|-----------|----------------|------|----------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | -- | STRING |
| 2 | 日期 | `date` | 数据日期 | -- | DATE |
| 3 | ASIN | `advertisedAsin` | 广告商品 ASIN | -- | STRING |
| 4 | SKU | `advertisedSku` | 广告商品 SKU | -- | STRING |
| 5 | 其他ASIN | `purchasedAsin` | 实际被购买的其他 ASIN | -- | STRING |
| 6 | 广告组 | `adGroupName` | 广告组名称 | -- | STRING |
| 7 | 广告活动 | `campaignName` | 广告活动名称 | -- | STRING |
| 8 | 其他SKU销量 | `unitsSoldClicks14dOtherSKU` | 其他 ASIN 的销售件数 | 其他 SKU 件数 | INTEGER |
| 9 | 其他SKU销售额 | `sales14dOtherSKU` | 其他 ASIN 的销售额 | 其他 SKU 销售额 | CURRENCY |
| 10 | 广告活动开始时间 | `startDate` | 广告活动开始日期 | -- | DATE |
| 11 | 广告活动结束时间 | `endDate` | 广告活动结束日期 | -- | DATE |
| 12 | 广告活动ID | `campaignId` | 广告活动唯一标识 | -- | STRING |
| 13 | 广告组ID | `adGroupId` | 广告组唯一标识 | -- | STRING |

> **Sources**: [GitHub Discussion #173](https://github.com/amzn/ads-advanced-tools-docs/discussions/173), [Reason Automation](https://help.reasonautomation.com/sponsored-advertising/sp-purchased-products)

---

## 15. SB/SD 独有指标详解

### 15.1 视频指标 (SB only)

SB 广告支持视频创意格式，报告包含完整的视频效果漏斗:

| 指标 | 赛狐中文名 | API 字段名 | 定义 | 计算方式 | 所属报告 |
|------|-----------|-----------|------|----------|----------|
| VCTR | 视频点击率 | `videoClickThroughRate` | 基于可见展示的点击率 | `clicks / viewableImpressions` | Campaign/Placement/Targeting/SearchTerm |
| VTR | 完整观看率 | `videoThroughRate` | 完整观看视频的用户比例 | `videoCompleteViews / viewableImpressions` | Campaign/Placement/Targeting/SearchTerm |
| VCPM | 每千次可见展示成本 | `costPerThousandViewableImpressions` | 基于可见展示的 CPM | `(cost / viewableImpressions) * 1000` | AdGroup/AdProduct (SB); 全部 SD 报告 |
| 5s观看次数 | 5秒观看 | `video5sViews` | 观看满 5 秒的次数 | 计数器 | Campaign/Placement/Targeting/SearchTerm |
| 5s观看率 | 5秒观看率 | `video5sViewRate` [推断] | 5秒观看比例 | `video5sViews / viewableImpressions` | Campaign/Placement/Targeting/SearchTerm |
| 1/4视频观看次数 | 25%观看 | `videoFirstQuartileViews` | 观看至视频 25% 的次数 | 计数器 | Campaign/Placement/Targeting/SearchTerm |
| 1/2视频观看次数 | 50%观看 | `videoMidpointViews` | 观看至视频 50% 的次数 | 计数器 | Campaign/Placement/Targeting/SearchTerm |
| 3/4视频观看次数 | 75%观看 | `videoThirdQuartileViews` | 观看至视频 75% 的次数 | 计数器 | Campaign/Placement/Targeting/SearchTerm |
| 完整视频观看次数 | 完整观看 | `videoCompleteViews` | 观看至视频 100% 的次数 | 计数器 | Campaign/Placement/Targeting/SearchTerm |
| 视频取消静音 | 取消静音 | `videoUnmutes` | 用户取消静音观看视频的次数 | 计数器 | Campaign/Placement/Targeting/SearchTerm |
| 可见展示次数 | 可见展示 | `viewableImpressions` | 符合 MRC 可见性标准 (>=50%面积, >=1秒) 的展示 | 计数器 | Campaign/Placement/Targeting/SearchTerm (SB); AdGroup/AdProduct (SB); 全部 SD 报告 |

> **视频漏斗关系**: Impressions -> Viewable Impressions -> 5s Views -> 1/4 -> 1/2 -> 3/4 -> Complete Views. 每一层是上一层的子集。

### 15.2 品牌新买家指标 (NTB -- New-to-Brand)

NTB (New-to-Brand) 指标衡量广告为品牌带来的新客户效果。新客户定义为过去 12 个月内未购买过该品牌的客户。

NTB 指标出现在 **SB 全部 7 种报告** 和 **SD 的 Campaign/AdGroup/AdProduct/Targeting 报告** (SD PurchasedItem 不含)。

| 指标 | 赛狐中文名 | API 字段名 | 定义 | 计算方式 | 数据类型 |
|------|-----------|-----------|------|----------|----------|
| NTB 订单量 | "品牌新买家"订单量 | `newToBrandPurchases14d` | 由过去12个月未买过该品牌的新客户产生的订单数 | 新客订单计数 | INTEGER |
| NTB 订单转化率 | "品牌新买家"订单转化率 | `newToBrandConversionRate14d` [推断] | NTB 订单转化率 | `NTB订单数 / clicks` | DECIMAL |
| NTB 订单占比 | "品牌新买家"订单百分比/占比 | `newToBrandPurchasesPercentage14d` | NTB 订单占总归因订单的比例 | `NTB订单数 / 总订单数 * 100` | DECIMAL |
| NTB 销售额 | "品牌新买家"销售额 | `newToBrandSales14d` | NTB 订单产生的销售额 | 新客销售合计 | CURRENCY |
| NTB 销售额占比 | "品牌新买家"销售额百分比 | `newToBrandSalesPercentage14d` | NTB 销售额占总归因销售额的比例 | `NTB销售额 / 总销售额 * 100` | DECIMAL |
| NTB 销量 | "品牌新买家"销量 | `newToBrandUnitsSold14d` | NTB 订单产生的销售件数 | 新客件数合计 | INTEGER |
| NTB 销量占比 | "品牌新买家"销量百分比/占比 | `newToBrandUnitsSoldPercentage14d` | NTB 销量占总归因销量的比例 | `NTB销量 / 总销量 * 100` | DECIMAL |

> **赛狐标题名差异**: 不同报告中 NTB 列的命名略有差异。Campaign/Placement 用"占比"，AdGroup/AdProduct/PurchasedItem 用"百分比"。SearchTerm 用"占比"。

> **Source**: [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/), [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields)

### 15.3 DPV (Detail Page Views)

| 指标 | 赛狐中文名 | API 字段名 | 定义 | 所属报告 |
|------|-----------|-----------|------|----------|
| DPV | 商品详情页浏览量 (DPV) | `detailPageViews` | 广告点击后到达商品详情页的次数。过滤了未成功加载详情页的点击。 | SB: AdGroup/AdProduct; SD: Campaign/AdGroup/AdProduct |

> DPV <= clicks (并非所有点击都到达详情页)。DPV 是比 clicks 更精确的流量质量指标。

> **Source**: [Amazon Marketing Stream SB](https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sb-performance), [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields)

### 15.4 品牌搜索次数 (Brand Search Count -- SB only)

| 指标 | 赛狐中文名 | API 字段名 | 定义 | 所属报告 |
|------|-----------|-----------|------|----------|
| 品牌搜索次数 | 品牌搜索次数 | `brandSearchCount` [推断] | 广告展示后用户在 Amazon 搜索该品牌名称的次数。衡量品牌认知度提升效果。 | SB Placement |

> 这是 SB 广告独有的品牌健康度指标，衡量广告对品牌搜索行为的影响。

### 15.5 引流类型 (Referral Type -- SB PurchasedItem only)

| 指标 | 赛狐中文名 | API 字段名 | 定义 | 所属报告 |
|------|-----------|-----------|------|----------|
| 引流类型 | 引流类型 | `referralType` [推断] | 指示购买是通过何种广告引流方式产生的 | SB PurchasedItem |

> [推断] 此字段仅出现在 SB PurchasedItem 报告中，可能是区分直接归因和间接归因的维度。

### 15.6 CPA (Cost Per Acquisition -- SD Targeting only)

| 指标 | 赛狐中文名 | API 字段名 | 定义 | 计算方式 | 数据类型 |
|------|-----------|-----------|------|----------|----------|
| CPA | CPA | `costPerAcquisition` | 单次获客成本 | `cost / purchases14d` | CURRENCY |

> CPA 仅在 SD Targeting 报告中出现。是仅次于 ACoS 的关键效率指标。CPA 越低，说明获取每个客户的广告成本越低。

### 15.7 ACoTS / ASoTS (SD Targeting only)

| 指标 | 赛狐中文名 | API 字段名 | 定义 | 计算方式 | 数据类型 |
|------|-----------|-----------|------|----------|----------|
| ACoTS | ACoTS | `advertisedCostOfTotalSales` | 广告花费占总销售额比 (含自然销售) | `(cost / totalSales) * 100` | DECIMAL |
| ASoTS | ASoTS | `advertisedShareOfTotalSales` | 广告销售额占总销售额比 (含自然销售) | `(sales14d / totalSales) * 100` | DECIMAL |

> **ACoTS vs ACoS**: ACoS 的分母是归因广告销售额; ACoTS 的分母是全部销售额 (自然+广告)。ACoTS 帮助理解广告在整体业务中的占比。
> **ASoTS**: 广告销售额占自然+广告总销售额的比重，反映品牌对广告的依赖程度。

> **Source**: [Adverity](https://docs.adverity.com/reference/amazon-ads-fields.html)

---

## 16. 公式速查

### 16.1 SB 核心计算公式

```
CTR   (点击率)      = clicks / impressions
VCTR  (视频点击率)   = clicks / viewableImpressions
VTR   (完整观看率)   = videoCompleteViews / viewableImpressions
VCPM  (千次可见展示成本) = (cost / viewableImpressions) * 1000
CPC   (单次点击成本)  = cost / clicks
CVR   (转化率)       = purchases14d / clicks
ACoS                 = (cost / sales14d) * 100
ROAS                 = sales14d / cost
DPV   (详情页浏览)   = 独立的计数器 (DPV <= clicks)
```

### 16.2 SD 核心计算公式

```
CTR    = clicks / impressions
CPC    = cost / clicks
VCPM   = (cost / viewableImpressions) * 1000
CVR    = purchases14d / clicks
ACoS   = (cost / sales14d) * 100
ROAS   = sales14d / cost
CPA    = cost / purchases14d
ACoTS  = (cost / totalSales) * 100          [totalSales = ad + organic]
ASoTS  = (sales14d / totalSales) * 100      [totalSales = ad + organic]
```

### 16.3 NTB 指标公式

```
NTB订单占比       = (NTB订单量 / 总订单量) * 100
NTB销售额占比     = (NTB销售额 / 总销售额) * 100
NTB销量占比       = (NTB销量 / 总销量) * 100
NTB转化率         = NTB订单量 / clicks
```

### 16.4 视频漏斗关系

```
impressions >= viewableImpressions
viewableImpressions >= video5sViews
video5sViews >= videoFirstQuartileViews (1/4)
1/4 >= videoMidpointViews (1/2)
1/2 >= videoThirdQuartileViews (3/4)
3/4 >= videoCompleteViews
```

### 16.5 归因关系 (SB/SD 通用)

```
purchases14d(total) = purchasesSameSKU + purchasesOtherSKU
sales14d(total)     = salesSameSKU     + salesOtherSKU
unitsSold14d(total) = unitsSameSKU     + unitsOtherSKU
```

---

## 17. 来源清单

### 17.1 官方来源 (Amazon)

| # | 来源 | URL | 内容 |
|---|------|-----|------|
| 1 | Amazon Ads API v3 Report Types | https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview | SB/SD 所有报告类型、reportTypeId、配置参数 |
| 2 | Amazon Performance Metrics Definitions | https://advertising.amazon.com/help/GG44RFW942U9F6F5 | 指标官方定义 |
| 3 | Amazon Marketing Stream SB Performance | https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sb-performance | SB 流量和转化数据集 schema |
| 4 | Amazon Marketing Stream SD Performance | https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sd-performance | SD 流量和转化数据集 schema |
| 5 | Amazon ACoS Help | https://advertising.amazon.com/help/G96BDERJLNQGW2Y3 | ACoS 官方定义和计算 |
| 6 | Amazon Placement Report Help | https://advertising.amazon.ca/help/G89VFUTQUWFFN2VU | 广告位定义 (含 SB 广告位) |
| 7 | GitHub: Amazon Ads API Discussion #173 | https://github.com/amzn/ads-advanced-tools-docs/discussions/173 | sbPurchasedProduct 字段列表 |

### 17.2 权威第三方 (含官方数据引用)

| # | 来源 | URL | 内容 |
|---|------|-----|------|
| 8 | Two Minute Reports | https://twominutereports.com/amazon-ads-metrics-and-dimensions/ | 123 字段完整定义，含 SB/SD metrics |
| 9 | Supermetrics Amazon Ads Fields | https://docs.supermetrics.com/docs/amazon-ads-fields | 166 字段完整 schema，含 SB/SD 特有字段 |
| 10 | Openbridge Attribution Metrics | https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics | 归因窗口、SameSKU/OtherSKU 定义 |
| 11 | Adverity Amazon Ads Fields | https://docs.adverity.com/reference/amazon-ads-fields.html | SD 费用类型、竞价优化、CPA/ACoTS/ASoTS 定义 |
| 12 | Sellegr8 Ads Performance Report | https://docs.sellegr8.com/article/35-ads-performance-report-column-description | 9 标签页列定义 (含 SB/SD) |
| 13 | Scaleleap Amazon Ads SDK | https://amazon-advertising-api-sdk.scaleleap.org | SB/SD API 字段结构 |
| 14 | Reason Automation | https://help.reasonautomation.com/sponsored-advertising/sp-purchased-products | SB/SD Purchased Product 报告 schema |

### 17.3 赛狐内部来源

| # | 来源 | 内容 |
|---|------|------|
| 15 | `/tmp/report_headers.json` | 赛狐实际导出的 SB 7 种 + SD 5 种报告的全部中文列名 |
| 16 | `SB-Campaign_*.xlsx` (样本) | SB Campaign 报告 40 列实际导出格式 |
| 17 | `SD-AdGroup_*.xlsx` (样本) | SD AdGroup 报告 35 列实际导出格式 (含 vcpm/SD_REACH 数据样例) |
| 18 | `SD-Campaign_*.xlsx` (样本) | SD Campaign 报告 33 列实际导出格式 (含 VCPM 费用类型) |

---

## 附录: 数据限制与注意事项

1. **SB 归因为 14 天**: SB 默认使用 14 天点击归因窗口 (与 SP 的 7 天不同)。SD 也使用 14 天。
2. **SD 可能包含展示归因**: SD 广告在某些情况下支持展示归因 (view-through attribution)，即用户看到广告但未点击，之后购买的仍可归因到广告。
3. **视频指标仅在特定 SB 报告中出现**: SB AdGroup 和 AdProduct 报告不含视频指标。视频指标 (VCTR/VTR/视频观看次数) 仅在 SB Campaign/Placement/Targeting/SearchTerm 报告中可用。
4. **NTB 指标全面覆盖**: 与 SP 不同，SB 和 SD 的几乎所有报告类型都包含 NTB 指标 (SD PurchasedItem 除外)。
5. **DPV 不含视频广告**: DPV 指标仅适用于非视频格式的 SB/SD 广告。
6. **费用类型 VCPM vs CPC**: SD 广告支持两种计费方式。VCPM 广告在无点击时仍产生花费，此时 CPC 为空。
7. **CPA/ACoTS/ASoTS 仅 SD Targeting**: 这三个高级转化指标仅在 SD Targeting 报告中可用。
8. **赛狐字段名大小写不一致**: SD AdGroup 中费用类型为 `vcpm` (小写), SD Campaign 中为 `VCPM` (大写)。竞价优化值也有类似不一致。
9. **SB-Targeting 的 "其他产品广告销售额" 列位置**: 在 Targeting 报告中不同于 Campaign (不在 "其他产品广告订单量" 之后，而是在销售指标中后置)。

---

## See also
- [SP 广告报告字段权威参考](sp-report-column-reference.md) -- SP (Sponsored Products) 的全部字段定义
- [列名映射参考](column-mappings.md) -- 中文列名到英文字段名的完整映射
- [数据源全图](data-sources.md) -- 所有报告类型及获取方式
- [资料来源 URL 索引](source-urls.md) -- 60+ 调研来源 URL
- [SB/SD 资料来源](amazon-official-docs/sb-sd-sources.md) -- 本调研用到的 SB/SD 专属来源
