---
okf: v0.1
type: Reference
title: SP 广告报告字段权威参考
description: Amazon Sponsored Products 8 种报告的全部列定义，含官方来源链接
tags: [amazon, advertising, reference, data-dictionary, sponsored-products]
created: 2026-07-02
updated: 2026-07-02
sources:
  - https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview
  - https://advertising.amazon.com/help/GG44RFW942U9F6F5
  - https://advertising.amazon.ca/help/G89VFUTQUWFFN2VU
  - https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sp-performance
  - https://amazon-advertising-api-sdk.scaleleap.org/interfaces/sponsoredproductsasinsreportparams
  - https://twominutereports.com/amazon-ads-metrics-and-dimensions/
  - https://docs.supermetrics.com/docs/amazon-ads-fields
  - https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics
  - https://github.com/amzn/ads-advanced-tools-docs/discussions/173
  - https://www.adbadger.com/blog/why-amazon-b2b-ads-are-a-game-changer-for-sellers/
---

# SP 广告报告字段权威参考

> **目的**: 为赛狐 SP 广告报表系统提供每个字段的官方定义、计算方式和数据类型。
> **原则**: 每个定义均可追溯到 Amazon 官方来源。未找到官方来源的字段标注 `[推断]`。
> **数据来源**: `/tmp/report_headers.json` (赛狐实际导出的列名) + 10+ 官方/权威来源。

---

## 目录

1. [概述与术语](#1-概述与术语)
2. [通用字段定义 (所有报告共享)](#2-通用字段定义)
3. [广告活动报告 (Campaign)](#3-广告活动报告)
4. [投放报告 (Targeting)](#4-投放报告)
5. [搜索词报告 (Search Term)](#5-搜索词报告)
6. [广告位报告 (Placement)](#6-广告位报告)
7. [广告产品报告 (Advertised Product)](#7-广告产品报告)
8. [广告组报告 (Ad Group)](#8-广告组报告)
9. [已购产品报告 (Purchased Product)](#9-已购产品报告)
10. [企业购报告 (Business)](#10-企业购报告)
11. [公式速查](#11-公式速查)
12. [来源清单](#12-来源清单)

---

## 1. 概述与术语

### 1.1 归因窗口 (Attribution Window)

Amazon SP 广告使用 **点击归因模型** (last-click attribution):

| 窗口 | API 后缀 | 说明 | 适用账号 |
|------|----------|------|----------|
| 1 天 | `1d` | 点击后 24 小时内购买 | 仅 API |
| 7 天 | `7d` | 点击后 7 天内购买 | **Seller 默认** |
| 14 天 | `14d` | 点击后 14 天内购买 | Vendor 默认 |
| 30 天 | `30d` | 点击后 30 天内购买 | 仅 API |

> **Seller Central 后台导出**: 默认使用 **7 天归因窗口**。
> **Source**: [Amazon Ads API v3 FAQ](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/faq), [Openbridge Attribution Metrics](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics)

### 1.2 Same SKU vs Other SKU

| 概念 | 英文 | 含义 |
|------|------|------|
| 本广告产品 | Same SKU | 购买的商品与广告推广的商品相同 |
| 其他产品 | Other SKU | 购买的商品与广告推广的不同 (品牌光环/Brand Halo) |
| 广告产品合计 | Total | Same SKU + Other SKU |

> **Source**: [Openbridge Attribution Metrics](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics)

### 1.3 定位类型 (Targeting Type)

| 中文 | 英文 | API 值 | 说明 |
|------|------|--------|------|
| 自动 | Auto | `auto` | Amazon 自动匹配关键词和商品 |
| 手动 | Manual | `manual` | 卖家自行设置关键词/商品投放 |

> **Source**: [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/)

### 1.4 匹配类型 (Match Type)

| 中文 | 英文 | API 值 | 说明 |
|------|------|--------|------|
| 广泛匹配 | Broad | `BROAD` | 匹配搜索词的广泛变体 |
| 词组匹配 | Phrase | `PHRASE` | 匹配包含关键词词组的搜索 |
| 精确匹配 | Exact | `EXACT` | 精确匹配关键词或近似变体 |
| 紧密匹配 | Close Match | — | 自动广告: 与产品紧密相关的搜索词 |
| 松散匹配 | Loose Match | — | 自动广告: 与产品松散相关的搜索词 |
| 替代品 | Substitutes | — | 自动广告: 替代品匹配 |
| 互补品 | Complements | — | 自动广告: 互补品匹配 |
| 关联产品 | — | — | 自动广告: 关联产品投放 |

> **Source**: [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/), [Sellegr8](https://docs.sellegr8.com/article/35-ads-performance-report-column-description)

### 1.5 广告位 (Placement)

| 中文 | 英文 | 说明 |
|------|------|------|
| 搜索结果顶部 (首页) | Top of Search | 搜索结果第一页顶部的 SP 广告位 |
| 产品页面 | Product Pages | 商品详情页、加购页等位置的广告 |
| 搜索结果的其余位置 | Rest of Search | 第一页中下部及第二页之后的广告位 |
| 企业购广告位 | Amazon Business | B2B 采购场景下的广告位 |

> **Source**: [Amazon Placement Report Help](https://advertising.amazon.ca/help/G89VFUTQUWFFN2VU)

---

## 2. 通用字段定义

以下字段出现在多数或全部 SP 报告类型中，定义相同。

### 2.1 标识字段 (Dimensions)

| 官方字段名 (API v3) | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `date` | 日期 | 数据日期 (YYYY-MM-DD)，时区取决于 Profile 设置 | DATE | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `campaignName` | 广告活动 | 广告活动名称 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `campaignId` | 广告活动ID | 广告活动唯一标识 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `adGroupName` | 广告组 | 广告组名称 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `adGroupId` | 广告组ID | 广告组唯一标识 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `campaignStatus` | 广告活动运行状态 | 活动状态: `ENABLED`(已开启), `PAUSED`(已暂停), `ARCHIVED`(已归档) | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `startDate` | 广告活动开始时间 | 活动开始日期 | DATE | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `endDate` | 广告活动结束时间 | 活动结束日期 (无结束日期则显示"无结束日期") | DATE | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `portfolioName` | 广告组合名称 | Portfolio 名称 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `portfolioId` | 广告组合ID | Portfolio 唯一标识 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `currency` | 币种 | 货币代码 (如 USD) | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `campaignBudget` | 预算 | 广告活动日预算 | CURRENCY | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `campaignTargetingType` | 定位类型 | `Auto`(自动投放) 或 `Manual`(手动投放) | STRING | [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/) |
| `campaignBiddingStrategy` | 竞价策略 | 竞价策略类型 (固定/动态) | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |

### 2.2 流量指标

| 官方字段名 (API v3) | 赛狐中文名 | 定义 | 计算方式 | 数据类型 | 来源 |
|---|---|---|---|---|---|
| `impressions` | 广告曝光量 | 广告展示的总次数 | 计数器，每次广告在页面上渲染一次计 1 | INTEGER | [Amazon Marketing Stream](https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sp-performance), [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `clicks` | 广告点击量 | 广告被点击的总次数 | 计数器，每次用户点击广告计 1 | INTEGER | [Amazon Marketing Stream](https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sp-performance), [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `cost` | 广告花费 | 广告点击产生的总费用 | 所有点击产生的 CPC 之和。注: API v3 字段名为 `cost`，非 `spend` | CURRENCY | [Amazon Marketing Stream](https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sp-performance), [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `costPerClick` (CPC) | CPC | 平均单次点击成本 | `cost / clicks` | CURRENCY | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields), [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/) |
| `clickThroughRate` (CTR) | 广告点击率 | 广告被点击的概率 | `clicks / impressions` (小数，如 0.0049 = 0.49%) | DECIMAL | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields), [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/) |

### 2.3 转化指标

| 官方字段名 (API v3) | 赛狐中文名 | 定义 | 计算方式 | 数据类型 | 来源 |
|---|---|---|---|---|---|
| `purchases7d` / `attributedConversions7d` | 广告订单量 | 7天归因窗口内，广告点击带来的总订单数 | 点击后 7 天内产生的订单数，包括本广告产品和其他产品 | INTEGER | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `attributedConversions7dSameSKU` | 本广告产品订单量 | 7天归因窗口内，购买商品与广告商品相同的订单数 | 仅统计购买商品 = 广告商品的订单 | INTEGER | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `attributedConversions7dOtherSKU` | 其他产品广告订单量 | 7天归因窗口内，购买商品与广告商品不同的订单数 (品牌光环) | 统计购买商品 != 广告商品的订单 | INTEGER | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `sales7d` / `attributedSales7d` | 广告销售额 | 7天归因窗口内，广告点击带来的总销售额 | 归因订单的商品售价总和 | CURRENCY | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `attributedSales7dSameSKU` | 本广告产品销售额 | 7天归因窗口内，广告商品自身的销售额 | 仅本广告产品的销售金额 | CURRENCY | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `attributedSales7dOtherSKU` | 其他产品广告销售额 | 7天归因窗口内，非广告商品的销售额 (品牌光环) | 非广告产品的销售金额 | CURRENCY | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `unitsSoldClicks7d` / `attributedUnitsOrdered7d` | 广告销量 | 7天归因窗口内，广告点击带来的总销售件数 | 归因订单中所有商品的件数之和 | INTEGER | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics), [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `attributedUnitsOrdered7dSameSKU` | 本广告产品销量 | 7天归因窗口内，广告商品自身的销售件数 | 仅计算广告商品的件数 | INTEGER | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |
| `attributedUnitsOrdered7dOtherSKU` | 其他产品广告销量 | 7天归因窗口内，非广告商品的销售件数 (品牌光环) | 非广告商品的件数 | INTEGER | [Openbridge](https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics) |

### 2.4 效率指标

| 官方字段名 (API v3) | 赛狐中文名 | 定义 | 计算方式 | 数据类型 | 来源 |
|---|---|---|---|---|---|
| `acos7d` | ACoS | 广告销售成本比 (Advertising Cost of Sales) | `(cost / sales7d) * 100`，以百分比表示。衡量广告支出占广告带来销售额的比例 | DECIMAL | [Amazon ACoS Help](https://advertising.amazon.com/help/G96BDERJLNQGW2Y3), [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `roas7d` | ROAS | 广告投资回报率 (Return on Ad Spend) | `sales7d / cost`，表示每花 1 美元广告费带来的销售额 | DECIMAL | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields), [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/) |
| `conversionRate7d` | 广告转化率 | 点击转化为订单的比率 | `(purchases7d / clicks) * 100` | DECIMAL | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields), [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/) |

---

## 3. 广告活动报告 (Campaign Report)

- **API reportTypeId**: `spCampaigns`
- **粒度**: 按 `campaign` 聚合，可按 `DAILY` / `SUMMARY` 输出
- **赛狐导出文件**: `Campaign_*.xlsx` (26 列)

### 专属维度字段

| 官方字段名 | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `campaignName` | 广告活动 | 广告活动名称 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `campaignId` | 广告活动ID | 广告活动唯一 ID (数字字符串) | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `portfolioId` | 广告组合ID | 所属 Portfolio ID | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `campaignStatus` | 广告活动运行状态 | 已开启/已暂停/已归档 | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `startDate` | 广告活动开始时间 | 活动开始日期 | DATE | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |
| `endDate` | 广告活动结束时间 | 活动结束日期 (无结束日期则显示"无结束日期") | DATE | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |

### 赛狐 Campaign 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 数据类型 |
|---|-----------|----------------|------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 (赛狐平台拼接，非 Amazon 原生字段) | STRING |
| 2 | 日期 | `date` | 数据日期 | DATE |
| 3 | 广告活动 | `campaignName` | 广告活动名称 | STRING |
| 4 | 定位类型 | `campaignTargetingType` | 自动投放 / 手动投放 | STRING |
| 5 | 广告花费 | `cost` | 总广告花费 | CURRENCY |
| 6 | 广告曝光量 | `impressions` | 广告展示次数 | INTEGER |
| 7 | 广告点击量 | `clicks` | 广告点击数 | INTEGER |
| 8 | CPC | `costPerClick` | 平均单次点击成本 | CURRENCY |
| 9 | 广告点击率 | `clickThroughRate` | CTR = 点击/曝光 | DECIMAL |
| 10 | 广告转化率 | `conversionRate7d` | 转化率 = 订单/点击 | DECIMAL |
| 11 | ACoS | `acos7d` | 广告销售成本比 | DECIMAL |
| 12 | ROAS | `roas7d` | 广告投资回报率 | DECIMAL |
| 13 | 广告订单量 | `purchases7d` | 归因总订单数 | INTEGER |
| 14 | 本广告产品订单量 | `attributedConversions7dSameSKU` | 同SKU订单数 | INTEGER |
| 15 | 其他产品广告订单量 | `attributedConversions7dOtherSKU` | 其他SKU订单数 | INTEGER |
| 16 | 广告销售额 | `sales7d` | 归因总销售额 | CURRENCY |
| 17 | 本广告产品销售额 | `attributedSales7dSameSKU` | 同SKU销售额 | CURRENCY |
| 18 | 其他产品广告销售额 | `attributedSales7dOtherSKU` | 其他SKU销售额 | CURRENCY |
| 19 | 广告销量 | `unitsSoldClicks7d` | 归因总销售件数 | INTEGER |
| 20 | 本广告产品销量 | `attributedUnitsOrdered7dSameSKU` | 同SKU销售件数 | INTEGER |
| 21 | 其他产品广告销量 | `attributedUnitsOrdered7dOtherSKU` | 其他SKU销售件数 | INTEGER |
| 22 | 广告活动开始时间 | `startDate` | 活动开始日期 | DATE |
| 23 | 广告活动结束时间 | `endDate` | 活动结束日期 | DATE |
| 24 | 广告活动运行状态 | `campaignStatus` | 已开启/已暂停/已归档 | STRING |
| 25 | 广告组合ID | `portfolioId` | Portfolio ID | STRING |
| 26 | 广告活动ID | `campaignId` | 广告活动唯一标识 | STRING |

---

## 4. 投放报告 (Targeting Report)

- **API reportTypeId**: `spTargeting`
- **粒度**: 按 `adGroup` + `targeting` 聚合
- **赛狐导出文件**: `Targeting_*.xlsx` (30 列)

### 专属维度字段

| 官方字段名 | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `targeting` | 投放 | 投放目标: 关键词文本 (手动) 或 "紧密匹配"/"松散匹配"/"替代品"/"互补品"/"关联产品" (自动) | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `matchType` | 匹配类型 | 关键词匹配类型: 广泛匹配/词组匹配/精确匹配/紧密匹配/松散匹配/替代品/互补品/关联产品 | STRING | [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/) |
| `keywordId` / `targetId` | 广告投放ID | 投放目标唯一标识 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `keywordStatus` / `targetingStatus` | 投放运行状态 | 已开启/已暂停/已归档 | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |

### 赛狐 Targeting 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 数据类型 |
|---|-----------|----------------|------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | STRING |
| 2 | 日期 | `date` | 数据日期 | DATE |
| 3 | 投放 | `targeting` | 投放的关键词或匹配方式 | STRING |
| 4 | 匹配类型 | `matchType` | 广泛/词组/精确匹配等 | STRING |
| 5 | 广告组 | `adGroupName` | 广告组名称 | STRING |
| 6 | 广告活动 | `campaignName` | 广告活动名称 | STRING |
| 7 | 定位类型 | `campaignTargetingType` | 自动/手动 | STRING |
| 8 | 广告花费 | `cost` | 总广告花费 | CURRENCY |
| 9 | 广告曝光量 | `impressions` | 广告展示次数 | INTEGER |
| 10 | 广告点击量 | `clicks` | 广告点击数 | INTEGER |
| 11 | CPC | `costPerClick` | 平均单次点击成本 | CURRENCY |
| 12 | 广告点击率 | `clickThroughRate` | CTR | DECIMAL |
| 13 | 广告转化率 | `conversionRate7d` | 转化率 | DECIMAL |
| 14 | ACoS | `acos7d` | 广告销售成本比 | DECIMAL |
| 15 | ROAS | `roas7d` | 广告投资回报率 | DECIMAL |
| 16 | 广告订单量 | `purchases7d` | 归因总订单数 | INTEGER |
| 17 | 本广告产品订单量 | `attributedConversions7dSameSKU` | 同SKU订单数 | INTEGER |
| 18 | 其他产品广告订单量 | `attributedConversions7dOtherSKU` | 其他SKU订单数 | INTEGER |
| 19 | 广告销售额 | `sales7d` | 归因总销售额 | CURRENCY |
| 20 | 本广告产品销售额 | `attributedSales7dSameSKU` | 同SKU销售额 | CURRENCY |
| 21 | 其他产品广告销售额 | `attributedSales7dOtherSKU` | 其他SKU销售额 | CURRENCY |
| 22 | 广告销量 | `unitsSoldClicks7d` | 归因总销售件数 | INTEGER |
| 23 | 本广告产品销量 | `attributedUnitsOrdered7dSameSKU` | 同SKU销售件数 | INTEGER |
| 24 | 其他产品广告销量 | `attributedUnitsOrdered7dOtherSKU` | 其他SKU销售件数 | INTEGER |
| 25 | 广告活动开始时间 | `startDate` | 活动开始日期 | DATE |
| 26 | 广告活动结束时间 | `endDate` | 活动结束日期 | DATE |
| 27 | 投放运行状态 | `keywordStatus` | 已开启/已暂停 | STRING |
| 28 | 广告活动ID | `campaignId` | 广告活动ID | STRING |
| 29 | 广告组ID | `adGroupId` | 广告组ID | STRING |
| 30 | 广告投放ID | `keywordId` | 投放目标ID | STRING |

---

## 5. 搜索词报告 (Search Term Report)

- **API reportTypeId**: `spSearchTerm`
- **粒度**: 按 `searchTerm` + `targeting` 聚合
- **赛狐导出文件**: `SearchTerm_*.xlsx` (32 列)

搜索词报告与投放报告结构几乎相同，多出以下专属列:

### 搜索词报告独有列

| 官方字段名 | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `searchTerm` | 用户搜索词 | 买家在 Amazon 搜索框中实际输入的搜索词。注意: 搜索词 != 关键词，搜索词是买家输入内容，关键词是卖家设置的投放目标 | STRING | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |

### 搜索词报告额外维度

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 数据类型 |
|---|-----------|----------------|------|----------|
| 26 | 广告组合名称 | `portfolioName` | Portfolio 名称 | STRING |
| 27 | 币种 | `currency` | 货币代码 | STRING |

> 注: 搜索词报告包含第 3 节表格的所有指标列 (花费/曝光/点击/CPC/CTR/转化率/ACoS/ROAS/订单量/销售额/销量 及其 SameSKU/OtherSKU 拆分)，加上搜索词专有列。

### 搜索词报告额外指标 (部分报告含)

| 官方字段名 | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `searchTermImpressionRank` | 搜索词展示量排名 | 该搜索词在所有搜索词中的展示量排名 | INTEGER | [Amazon API](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| `searchTermImpressionShare` | 搜索词展示份额 | 该搜索词的展示量占该词总可用展示量的百分比。低份额 = 竞争激烈或出价不足 | DECIMAL | [Sellegr8](https://docs.sellegr8.com/article/35-ads-performance-report-column-description) |

---

## 6. 广告位报告 (Placement Report)

- **API reportTypeId**: `spPlacement` (通过 `spCampaigns` 或 `spTargeting` 的 `segment: placement` 获得) [推断]
- **粒度**: 按 `placement` 细分
- **赛狐导出文件**: `Placement_*.xlsx` (26 列)

### 广告位报告独有列

| 官方字段名 | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `placement` | 广告位 | 广告投放的具体位置分类。SP 取值: `Top of Search`(搜索结果顶部首页), `Product Pages`(产品页面), `Rest of Search`(搜索结果的其余位置) | STRING | [Amazon Placement Report Help](https://advertising.amazon.ca/help/G89VFUTQUWFFN2VU) |

### 广告位分类详解

| 赛狐中文值 | 英文官方值 | 位置描述 | 典型特征 |
|-----------|-----------|---------|----------|
| 搜索结果顶部 (首页) | Top of Search (First Page) | 搜索结果第一页顶部的前几个 SP 广告位，带 "Sponsored" 标签 | CPC 最高，CTR 最高，适用于高意向搜索词和品牌词 |
| 产品页面 | Product Pages | 商品详情页、加购页、同类商品推荐轮播 ("Sponsored products related to this item") | 转化率通常最高 (买家已在购物决策深处)，适用竞品截流 |
| 搜索结果的其余位置 | Rest of Search | 第一页中下部、第二页及之后的搜索广告位 | CPC 最低，适合低成本曝光 |

> **Source**: [Amazon Placement Report Help](https://advertising.amazon.ca/help/G89VFUTQUWFFN2VU), [Threecolts](https://www.threecolts.com/blog/amazon-advertising-placements/)

### 赛狐 Placement 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 数据类型 |
|---|-----------|----------------|------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | STRING |
| 2 | 日期 | `date` | 数据日期 | DATE |
| 3 | 广告位 | `placement` | Top of Search / Product Pages / Rest of Search | STRING |
| 4 | 广告活动 | `campaignName` | 广告活动名称 | STRING |
| 5 | 定位类型 | `campaignTargetingType` | 自动/手动 | STRING |
| 6-21 | (指标同 Campaign) | `cost`, `impressions`, `clicks`, `costPerClick`, `clickThroughRate`, `conversionRate7d`, `acos7d`, `roas7d`, `purchases7d`, `attributedConversions7dSameSKU`, `attributedConversions7dOtherSKU`, `sales7d`, `attributedSales7dSameSKU`, `attributedSales7dOtherSKU`, `unitsSoldClicks7d`, `attributedUnitsOrdered7dSameSKU`, `attributedUnitsOrdered7dOtherSKU` | 按广告位拆分的指标 | - |
| 22 | 广告活动开始时间 | `startDate` | 开始日期 | DATE |
| 23 | 广告活动结束时间 | `endDate` | 结束日期 | DATE |
| 24 | 广告活动运行状态 | `campaignStatus` | 已开启/已暂停 | STRING |
| 25 | 广告活动ID | `campaignId` | 广告活动ID | STRING |

> 注: Placement 报告不包含广告组ID列。

---

## 7. 广告产品报告 (Advertised Product Report)

- **API reportTypeId**: `spAdvertisedProduct` (groupBy: `advertiser`)
- **API recordType**: `productAds` (product-level) / `asins` (ASIN-level)
- **粒度**: 按 ASIN/SKU 维度，最大 31 天回溯
- **赛狐导出文件**: `AdvertisedProduct_*.xlsx` (30 列)

### 广告产品报告独有维度

| 官方字段名 | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `asin` | asin | 广告商品的 Amazon Standard Identification Number | STRING | [Scaleleap SDK](https://amazon-advertising-api-sdk.scaleleap.org/interfaces/sponsoredproductsasinsreportparams) |
| `sku` | sku | 广告商品的 Stock Keeping Unit (卖家定义的库存编码) | STRING | [Scaleleap SDK](https://amazon-advertising-api-sdk.scaleleap.org/interfaces/sponsoredproductsasinsreportparams) |
| `adId` | 广告产品ID | 广告产品的唯一标识 | STRING | [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/) |
| `adStatus` | 广告产品运行状态 | 已开启/已暂停/已归档 | STRING | [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields) |

### 赛狐 AdvertisedProduct 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 数据类型 |
|---|-----------|----------------|------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | STRING |
| 2 | 日期 | `date` | 数据日期 | DATE |
| 3 | asin | `asin` | 广告商品 ASIN | STRING |
| 4 | sku | `sku` | 广告商品 SKU | STRING |
| 5 | 广告组 | `adGroupName` | 广告组名称 | STRING |
| 6 | 广告活动 | `campaignName` | 广告活动名称 | STRING |
| 7 | 定位类型 | `campaignTargetingType` | 自动/手动 | STRING |
| 8-21 | (指标同 Campaign) | `cost`, `impressions`, `clicks`, `costPerClick`, `clickThroughRate`, `conversionRate7d`, `acos7d`, `roas7d`, `purchases7d`, `attributedConversions7dSameSKU`, `attributedConversions7dOtherSKU`, `sales7d`, `attributedSales7dSameSKU`, `attributedSales7dOtherSKU`, `unitsSoldClicks7d`, `attributedUnitsOrdered7dSameSKU`, `attributedUnitsOrdered7dOtherSKU` | 按ASIN拆分的指标 | - |
| 22 | 广告活动开始时间 | `startDate` | 开始日期 | DATE |
| 23 | 广告活动结束时间 | `endDate` | 结束日期 | DATE |
| 24 | 广告产品运行状态 | `adStatus` | 已开启/已暂停 | STRING |
| 25 | 广告活动ID | `campaignId` | 广告活动ID | STRING |
| 26 | 广告组ID | `adGroupId` | 广告组ID | STRING |
| 27 | 广告产品ID | `adId` | 广告产品ID | STRING |

---

## 8. 广告组报告 (Ad Group Report)

- **API**: 无独立的 `spAdGroups` 报告。等效数据通过 `spCampaigns` with `groupBy: adGroup` 获取。
- **赛狐导出文件**: `AdGroup_*.xlsx` (27 列)

> **重要说明**: 根据 [Amazon Ads API v3 文档](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview)，SP 没有独立的 Ad Group 报告类型。赛狐的 AdGroup 报告实质上是 Campaign 报告按 `adGroup` 聚合的版本 (赛狐从 Amazon Ads Console 导出)，数据内容与 Campaign 报告一致，仅粒度不同。

### 赛狐 AdGroup 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 数据类型 |
|---|-----------|----------------|------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | STRING |
| 2 | 日期 | `date` | 数据日期 | DATE |
| 3 | 广告组 | `adGroupName` | 广告组名称 (此报告的聚合维度) | STRING |
| 4 | 广告活动 | `campaignName` | 广告活动名称 | STRING |
| 5 | 定位类型 | `campaignTargetingType` | 自动/手动 | STRING |
| 6-21 | (指标同 Campaign) | `cost`, `impressions`, `clicks`, `costPerClick`, `clickThroughRate`, `conversionRate7d`, `acos7d`, `roas7d`, `purchases7d`, `attributedConversions7dSameSKU`, `attributedConversions7dOtherSKU`, `sales7d`, `attributedSales7dSameSKU`, `attributedSales7dOtherSKU`, `unitsSoldClicks7d`, `attributedUnitsOrdered7dSameSKU`, `attributedUnitsOrdered7dOtherSKU` | 按广告组拆分的指标 | - |
| 22 | 广告活动开始时间 | `startDate` | 开始日期 | DATE |
| 23 | 广告活动结束时间 | `endDate` | 结束日期 | DATE |
| 24 | 广告组运行状态 | `adGroupStatus` | 已开启/已暂停 | STRING |
| 25 | 广告活动ID | `campaignId` | 广告活动ID | STRING |
| 26 | 广告组ID | `adGroupId` | 广告组ID | STRING |

---

## 9. 已购产品报告 (Purchased Product Report)

- **API reportTypeId**: `spPurchasedProduct`
- **粒度**: 按 `advertisedAsin` + `purchasedAsin` 聚合 (展示广告拉动了哪些产品的购买)
- **赛狐导出文件**: `PurchasedItem_*.xlsx` (16 列)

### 已购产品报告独有维度

| 官方字段名 | 赛狐中文名 | 定义 | 数据类型 | 来源 |
|---|---|---|---|---|
| `advertisedAsin` | ASIN | 被点击的广告商品 ASIN | STRING | [GitHub Amazon API Discussion](https://github.com/amzn/ads-advanced-tools-docs/discussions/173) |
| `advertisedSku` | SKU | 被点击的广告商品 SKU | STRING | [GitHub Amazon API Discussion](https://github.com/amzn/ads-advanced-tools-docs/discussions/173) |
| `purchasedAsin` | 其他ASIN | 实际被购买的 ASIN (可能与广告 ASIN 相同或不同) | STRING | [GitHub Amazon API Discussion](https://github.com/amzn/ads-advanced-tools-docs/discussions/173) |
| `keyword` | 投放 | 关键词或投放方式 (对应自动广告的匹配类型如 "紧密匹配" 或手动广告的关键词) | STRING | [GitHub Amazon API Discussion](https://github.com/amzn/ads-advanced-tools-docs/discussions/173) |
| `matchType` / `keywordType` | 匹配类型 | 广泛/词组/精确匹配等 | STRING | [GitHub Amazon API Discussion](https://github.com/amzn/ads-advanced-tools-docs/discussions/173) |

### 已购产品报告独有指标

| 官方字段名 | 赛狐中文名 | 定义 | 计算方式 | 数据类型 | 来源 |
|---|---|---|---|---|---|
| `unitsSoldClicks1d/7d/14d/30d` | 其他SKU销量 | 其他 ASIN 的销售件数 | 广告点击后购买的非广告商品件数 | INTEGER | [GitHub Discussion](https://github.com/amzn/ads-advanced-tools-docs/discussions/173), [Reason Automation](https://help.reasonautomation.com/sponsored-advertising/sp-purchased-products) |
| `sales1d/7d/14d/30d` | 其他SKU销售额 | 其他 ASIN 的销售额 | 广告点击后购买的非广告商品销售额 | CURRENCY | [GitHub Discussion](https://github.com/amzn/ads-advanced-tools-docs/discussions/173), [Reason Automation](https://help.reasonautomation.com/sponsored-advertising/sp-purchased-products) |

> **注意**: 此报告中没有 `impressions`、`clicks`、`cost`、`CTR`、`ACoS` 等流量指标。它专注于回答 "广告拉动了哪些商品的购买"。

### 赛狐 PurchasedItem 报告完整列清单

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 数据类型 |
|---|-----------|----------------|------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | STRING |
| 2 | 日期 | `date` | 数据日期 | DATE |
| 3 | ASIN | `advertisedAsin` | 广告商品 ASIN | STRING |
| 4 | SKU | `advertisedSku` | 广告商品 SKU | STRING |
| 5 | 投放 | `keyword` | 投放目标关键词或匹配方式 | STRING |
| 6 | 匹配类型 | `matchType` | 匹配类型 | STRING |
| 7 | 其他ASIN | `purchasedAsin` | 实际购买的 ASIN | STRING |
| 8 | 广告组 | `adGroupName` | 广告组名称 | STRING |
| 9 | 广告活动 | `campaignName` | 广告活动名称 | STRING |
| 10 | 定位类型 | `campaignTargetingType` | 自动/手动 | STRING |
| 11 | 其他SKU销量 | `unitsSoldClicks7d` | 其他SKU销售件数 | INTEGER |
| 12 | 其他SKU销售额 | `sales7d` | 其他SKU销售额 | CURRENCY |
| 13 | 广告活动开始时间 | `startDate` | 开始日期 | DATE |
| 14 | 广告活动结束时间 | `endDate` | 结束日期 | DATE |
| 15 | 广告活动ID | `campaignId` | 广告活动ID | STRING |
| 16 | 广告组ID | `adGroupId` | 广告组ID | STRING |

---

## 10. 企业购报告 (Business Report)

- **API**: 通过 Placement Report 的 `placement: "Amazon Business"` 筛选获得 [推断]
- **赛狐导出文件**: `SP-BusinessReport_*.xlsx` (26 列)

> **说明**: Amazon Business (企业购/B2B) 是 SP 广告的一个特殊投放场景。在 Placement 报告中，Business 广告位显示为独立行，如 "产品页面(企业购广告位)"。企业购买家通常是批量采购，具有更高的转化率和客单价。

### 赛狐 Business 报告完整列清单

与 Placement 报告结构相同，但 Placement 维度仅显示企业购相关广告位:

| # | 赛狐中文名 | 官方 API 字段名 | 定义 | 数据类型 |
|---|-----------|----------------|------|----------|
| 1 | 店铺 | `[Sellfox 拼接]` | 店铺名称 | STRING |
| 2 | 日期 | `date` | 数据日期 | DATE |
| 3 | 广告位 | `placement` | 企业购广告位 (如 "产品页面(企业购广告位)") | STRING |
| 4-25 | (同 Placement 报告) | (同 Placement) | 企业购场景下的广告效果指标 | - |
| 25 | 广告活动ID | `campaignId` | 广告活动ID | STRING |

> **Source**: [Ad Badger - Why Amazon B2B Ads Are a Game Changer](https://www.adbadger.com/blog/why-amazon-b2b-ads-are-a-game-changer-for-sellers/)

---

## 11. 公式速查

### 11.1 核心计算公式

```
CTR (点击率)    = clicks / impressions
CVR (转化率)    = purchases7d / clicks
CPC (单次点击成本) = cost / clicks
ACoS            = (cost / sales7d) * 100
ROAS            = sales7d / cost
CPA             = cost / purchases7d
TACoS           = (cost / totalSales) * 100   [totalSales = ad + organic]
```

### 11.2 归因关系

```
purchases7d(total) = purchasesSameSKU + purchasesOtherSKU
sales7d(total)     = salesSameSKU     + salesOtherSKU
unitsSold7d(total) = unitsSoldSameSKU + unitsSoldOtherSKU
```

### 11.3 指标互推

```
sales7d = cost / acos7d * 100    (当 acos7d > 0 时)
sales7d = cost * roas7d
cost    = sales7d * acos7d / 100
```

> **Source**: [Amazon ACoS Help](https://advertising.amazon.com/help/G96BDERJLNQGW2Y3), [Two Minute Reports](https://twominutereports.com/amazon-ads-metrics-and-dimensions/), [Supermetrics](https://docs.supermetrics.com/docs/amazon-ads-fields)

---

## 12. 来源清单

### 12.1 官方来源 (Amazon)

| # | 来源 | URL | 内容 |
|---|------|-----|------|
| 1 | Amazon Ads API v3 Report Types | https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview | 所有报告类型、groupBy、配置参数 |
| 2 | Amazon Performance Metrics Definitions | https://advertising.amazon.com/help/GG44RFW942U9F6F5 | 指标官方定义 |
| 3 | Amazon Placement Report Help | https://advertising.amazon.ca/help/G89VFUTQUWFFN2VU | 广告位报告字段定义、三种广告位说明 |
| 4 | Amazon ACoS Help | https://advertising.amazon.com/help/G96BDERJLNQGW2Y3 | ACoS 定义、计算公式、行业指南 |
| 5 | Amazon Marketing Stream SP Performance | https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sp-performance | SP 流量和转化数据集 schema |
| 6 | Amazon Ads API Reporting FAQ | https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/faq | 报告常见问题、归因窗口说明 |
| 7 | Amazon Audience Report Help | https://advertising.amazon.ca/help/GA44MFEHYENPNK3D | SP 受众报告文档 |
| 8 | GitHub: Amazon Ads API Discussion #173 | https://github.com/amzn/ads-advanced-tools-docs/discussions/173 | spPurchasedProduct 字段列表、官方回复 |

### 12.2 权威第三方 (含官方数据引用)

| # | 来源 | URL | 内容 |
|---|------|-----|------|
| 9 | Scaleleap Amazon Ads SDK Docs | https://amazon-advertising-api-sdk.scaleleap.org/interfaces/sponsoredproductsasinsreportparams | SP ASINs 报告可用 metrics 完整列表 |
| 10 | Two Minute Reports - Amazon Ads Metrics | https://twominutereports.com/amazon-ads-metrics-and-dimensions/ | 123 个字段的完整定义、类型、归属报告 |
| 11 | Supermetrics - Amazon Ads Fields | https://docs.supermetrics.com/docs/amazon-ads-fields | 108 metrics + 58 dimensions 完整 schema |
| 12 | Openbridge - Amazon Attribution Metrics | https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics | SameSKU/OtherSKU 定义、各账号类型归因窗口 |
| 13 | Sellegr8 - Ads Performance Report Columns | https://docs.sellegr8.com/article/35-ads-performance-report-column-description | 9 个报告标签页的所有列定义 |
| 14 | Seller Labs - Data Hub Dictionary | https://www.sellerlabs.com/support/data-hub-data-dictionary/ | Amazon Ads 数据源和表结构 |
| 15 | Reason Automation - SP Purchased Products | https://help.reasonautomation.com/sponsored-advertising/sp-purchased-products | SP Purchased Product 报告 schema |
| 16 | Ad Badger - B2B Ads | https://www.adbadger.com/blog/why-amazon-b2b-ads-are-a-game-changer-for-sellers/ | Amazon Business 广告位、B2B 报告说明 |
| 17 | Supermetrics - Amazon Ads Field Changes 2024 | https://docs.supermetrics.com/docs/amazon-ads-field-changes-october-31-2024 | 2024年10月字段废弃清单 |
| 18 | Threecolts - Amazon Ad Placements | https://www.threecolts.com/blog/amazon-advertising-placements/ | 三种广告位的详细定义和策略 |

### 12.3 赛狐内部来源

| # | 来源 | 内容 |
|---|------|------|
| 19 | `/tmp/report_headers.json` | 赛狐实际导出的 16 种报告的全部中文列名 |
| 20 | `advertise/__init__.py` | CAMPAIGN_COLUMN_MAP / TARGETING_COLUMN_MAP 等英文映射 |

---

## 附录: 数据限制与注意事项

1. **Seller 默认归因为 7 天**: 赛狐导出的 Amazon Ads Console 报告对于 Seller 账号默认使用 7 天归因窗口。
2. **数据延迟**: 流量指标 (展示/点击) 约 12 小时延迟，转化指标约 24 小时延迟，且 Amazon 会在 28 天内持续修正数据。
3. **ACoS/ROAS 显示规则**: 当 `sales7d = 0` 或 `cost = 0` 时，ACoS 和 ROAS 为空 (不显示)。
4. **转化率为零的处理**: 当 `clicks = 0` 时，转化率为空。
5. **API v3 字段名与 Console 导出不同**: API v3 使用 `cost` (非 `spend`), `costPerClick` (非 `cpc`), `clickThroughRate` (非 `ctr`), `purchases7d` (非 `orders7d`)。
6. **SP Ad Group 报告不存在独立 API**: SP 没有独立的 `spAdGroups` 报告。赛狐的 AdGroup 报告是 `spCampaigns` 按 `groupBy: adGroup` 导出。
7. **Purchased Product 报告无流量指标**: 该报告不含 impressions/clicks/cost/CPC/CTR，仅含转化数据。
8. **Business 报告 = 企业购广告位**: 本质是 Placement 报告中 placement = Amazon Business 的子集。

---

## See also
- [列名映射参考](column-mappings.md) -- 中文列名到英文字段名的完整映射
- [数据源全图](data-sources.md) -- 所有 SP 报告类型及获取方式
- [资料来源 URL 索引](source-urls.md) -- 60+ 调研来源 URL
- [advertise/__init__.py](../../../advertise/__init__.py) -- 数据清洗和列映射代码
