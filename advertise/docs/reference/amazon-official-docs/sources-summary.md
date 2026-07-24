---
okf: v0.1
type: Reference
title: Amazon SP 广告报告字段来源汇总
description: 所有找到的 Amazon SP 官方/权威文档源及其内容摘要
created: 2026-07-02
parent: sp-report-column-reference.md
---

# Amazon SP 广告报告字段来源汇总

本文件汇总了在调研 Amazon SP 广告报告字段定义过程中找到的所有权威来源。

---

## 1. Amazon 官方 API 文档

### 1.1 Ads API v3 Report Types Overview
- **URL**: https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview
- **状态**: JavaScript 渲染，无法直接抓取内容
- **内容**: 所有 SP/SB/SD 报告类型的完整列表，包括 reportTypeId、groupBy 选项、columns 参数
- **关键 reportTypeId**: `spCampaigns`, `spTargeting`, `spSearchTerm`, `spAdvertisedProduct`, `spPurchasedProduct`, `spPlacement`

### 1.2 Ads API v3 Reporting FAQ
- **URL**: https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/faq
- **状态**: JavaScript 渲染，无法直接抓取
- **内容**: 归因窗口说明、数据延迟、报告类型对比

### 1.3 Amazon Marketing Stream - SP Performance Datasets
- **URL**: https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sp-performance
- **状态**: JavaScript 渲染，无法直接抓取
- **内容**: sp-traffic (流量) 和 sp-conversion (转化) 数据集的所有字段定义
- **关键字段**: impressions, clicks, cost, purchases, sales, units

### 1.4 Placement Report Help
- **URL**: https://advertising.amazon.ca/help/G89VFUTQUWFFN2VU
- **状态**: 可通过 WebSearch 获取内容
- **内容**: 三种广告位 (Top of Search, Product Pages, Rest of Search) 的定义和特征
- **关键发现**:
  - Top of Search: 搜索结果第一页顶部，CPC 最高，CTR 最高
  - Product Pages: 商品详情页，转化率通常最高
  - Rest of Search: 搜索结果其余位置，CPC 最低

### 1.5 Performance Metrics Definitions
- **URL**: https://advertising.amazon.com/help/GG44RFW942U9F6F5
- **状态**: 仅返回 tracking pixel
- **内容**: 据描述是 "Performance Metrics Definitions"，提供了所有广告指标的官方定义

### 1.6 ACoS Help Page
- **URL**: https://advertising.amazon.com/help/G96BDERJLNQGW2Y3
- **状态**: 可通过 WebSearch 获取内容
- **内容**: ACoS 官方定义
- **公式**: ACoS = (ad spend / ad revenue) * 100
- **归因窗口**: Sellers 7 天，Vendors 14 天

### 1.7 GitHub: Amazon Ads API Discussion #173
- **URL**: https://github.com/amzn/ads-advanced-tools-docs/discussions/173
- **状态**: 可完整抓取
- **内容**: spPurchasedProduct 报告的完整字段列表 (API v3 请求示例)
- **关键字段**: date, portfolioId, campaignId, campaignName, adGroupId, adGroupName, keywordId, keyword, keywordType, advertisedAsin, purchasedAsin, advertisedSku, campaignBudgetCurrencyCode, matchType, unitsSoldClicks1d/7d/14d/30d, sales1d/7d/14d/30d, purchases1d/7d/14d/30d, unitsSoldOtherSku1d/7d/14d/30d, salesOtherSku1d/7d/14d/30d, purchasesOtherSku1d/7d/14d/30d, kindleEditionNormalizedPagesRead14d, kindleEditionNormalizedPagesRoyalties14d
- **官方回复**: "v3 版本的报告类型对比表尚未更新，正在 backlog 中"

---

## 2. 第三方权威来源 (引用官方 API)

### 2.1 Scaleleap Amazon Ads SDK
- **URL**: https://amazon-advertising-api-sdk.scaleleap.org/interfaces/sponsoredproductsasinsreportparams
- **状态**: 可完整抓取
- **内容**: SP ASINs 报告的 24 个可用 metrics 字段完整列表
- **字段分组**: Entity identifiers (campaignId, campaignName, adGroupId, adGroupName, keywordId, keywordText, matchType, asin, sku, otherAsin), Units ordered (1d/7d/14d/30d for same/other SKU), Sales (1d/7d/14d/30d for other SKU)
- **注意**: ASINs 报告没有 impressions, clicks, cost 等流量指标

### 2.2 Two Minute Reports - Amazon Ads Metrics and Dimensions
- **URL**: https://twominutereports.com/amazon-ads-metrics-and-dimensions/
- **状态**: 可完整抓取
- **内容**: 123 个字段 (包含 metrics 和 dimensions)，按类别组织:
  - PERFORMANCE: impressions, clicks, cost, CPC, CTR, CVR, ACOS, ROAS (含 1/7/14/30 天归因窗口)
  - CONVERSIONS: 12 个转化指标 (total/sameSKU/otherSKU x 1d/7d/14d/30d)
  - SALES: 12 个销售指标 (对应关系同上)
  - CAMPAIGN: 13 个维度
  - AD GROUP: 10 个维度
  - 其他: TIME, PROFILE, ACCOUNT, PORTFOLIO, PLACEMENT, KEYWORDS, TARGETING, SEARCH TERM
- **SP 独有字段标注**: 1d/7d/30d 归因窗口和 sameSKU/otherSKU 拆分仅 SP 可用

### 2.3 Supermetrics - Amazon Ads Fields
- **URL**: https://docs.supermetrics.com/docs/amazon-ads-fields
- **状态**: 可完整抓取 (部分截断)
- **内容**: 85+ 字段的完整定义、数据类型、描述 (总计 108 metrics + 58 dimensions)
- **关键字段类型**:
  - impressions: int.number.value
  - clicks: int.number.value
  - cost: float.currency.value (注: 字段 ID 为 `cost`，标签为 "Spend")
  - cpc: float.currency.value
  - ctr: float.number.percentage
  - acos: float.number.percentage
  - roas: float.number.ratio
- **2024年10月废弃字段**: 1d/7d/14d/30d 窗口的 ACOS, ROAS, Orders, Conversion Rate, Sales, Sales same SKU, Units ordered other SKU, Sales other SKU

### 2.4 Openbridge - Amazon Advertising Attribution Metrics
- **URL**: https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics
- **状态**: 可完整抓取
- **内容**: 归因指标的精确定义和完整示例:
  - attributedConversions = 买家点击广告后购买的商品订单数 (不管是不是广告商品)
  - attributedConversionsSameSKU = 仅统计包含广告商品的订单
  - attributedUnitsOrdered = 所有归因订单中的商品总件数
  - attributedUnitsOrderedSameSKU = 仅广告商品的件数
  - attributedUnitsOrderedOtherSKU = "品牌光环" (Brand Halo)，非广告商品
  - attributedSales = 归因订单的总销售额
  - attributedSalesSameSKU = 广告商品自身的销售额
- **归因窗口**: SP Sellers 7天, SP Vendors 14天, SB 14天, SD 14天, DSP 14天(含展示归因)
- **关键区别**: UI 只显示总量，可下载报告提供 SameSKU/OtherSKU 拆分

### 2.5 Sellegr8 - Ads Performance Report Column Description
- **URL**: https://docs.sellegr8.com/article/35-ads-performance-report-column-description
- **状态**: 可完整抓取
- **内容**: 9 个报告标签页的所有列定义:
  - Campaign Types: 聚合指标
  - Products: 按产品
  - Campaigns: 按广告活动
  - Ad Groups: 按广告组
  - Ad Items: 按广告产品
  - Placements: 按广告位
  - Keywords: 按关键词
  - Manual Search Terms: 手动广告搜索词
  - Auto Search Terms: 自动广告搜索词
- **关键定义**: Impression Share = 捕获的可用展示量百分比，Impression Rank = 平均展示排名

### 2.6 Supermetrics - Amazon Ads Field Changes Oct 2024
- **URL**: https://docs.supermetrics.com/docs/amazon-ads-field-changes-october-31-2024
- **状态**: 可完整抓取
- **内容**: 20+ 个废弃字段列表，均为带归因窗口后缀的旧版字段
- **废弃模式**: 1 day / 7 day / 30 day 变体被废弃，统一到基础字段或 14 day

### 2.7 Reason Automation - SP Purchased Products
- **URL**: https://help.reasonautomation.com/sponsored-advertising/sp-purchased-products
- **状态**: 可部分抓取
- **内容**: SP Purchased Product 表的说明
- **关键说明**: 此表没有 "total sales"，不应用于聚合报告。数据有 30 天回溯更新。
- **归因窗口**: 1, 7, 14, 30 天滚动窗口

### 2.8 Ad Badger - B2B Ads
- **URL**: https://www.adbadger.com/blog/why-amazon-b2b-ads-are-a-game-changer-for-sellers/
- **状态**: 可完整抓取
- **内容**: Amazon Business B2B 广告位的说明
- **关键发现**: Business 是 Placement 报告中的一个独立 placement 行，显示更低 spend、更高 sales、更低 ACoS (12% vs 24%)

### 2.9 Threecolts - Amazon Ad Placements
- **URL**: https://www.threecolts.com/blog/amazon-advertising-placements/
- **状态**: 通过 WebSearch 获取
- **内容**: 三种广告位的详细定义和策略，包括出价调整范围 (+/-900%)

---

## 3. 无法访问但已知存在的来源

以下来源被多个第三方引用但无法直接访问:
- Amazon Seller Central 报告中心帮助页面
- Amazon Ads Console 内建报告文档
- Amazon Ads API v3 完整 Reference (需要认证)

---

## 4. API v2 vs v3 字段名映射

| API v2 字段名 | API v3 字段名 | 说明 |
|--------------|--------------|------|
| `cost` | `cost` | 一致 |
| `impressions` | `impressions` | 一致 |
| `clicks` | `clicks` | 一致 |
| `attributedSales1d` | `sales1d` | 简化 |
| `attributedConversions1d` | `purchases1d` | 简化 |
| `attributedUnitsOrdered1d` | `unitsSoldClicks1d` | 重命名 |
| `attributedSales1dSameSKU` | `attributedSalesSameSKU1d` | 字段名重排 |
| `1 day ACos` | `acos1d` | 格式统一 |

---

## 5. 当前搜索范围外 (未包含在本轮调研)

- Amazon DSP 报告字段
- Sponsored Brands (SB) 完整字段
- Sponsored Display (SD) 完整字段
- AMC (Amazon Marketing Cloud) 数据集
- Seller Central Business Reports 字段
- Brand Analytics 字段
