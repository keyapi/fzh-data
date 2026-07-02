---
okf: v0.1
type: Reference
title: SB/SD 广告报告调研来源
description: Sponsored Brands 和 Sponsored Display 报告字段调研过程中使用的来源汇总
created: 2026-07-02
parent: sb-sd-report-column-reference.md
---

# SB/SD 广告报告调研来源

本文件汇总了 SB (Sponsored Brands) 和 SD (Sponsored Display) 广告报告字段定义调研中使用的来源。

---

## 1. SB/SD 相关的 Amazon 官方来源

### 1.1 Amazon Marketing Stream -- SB Performance Dataset
- **URL**: https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sb-performance
- **状态**: JavaScript 渲染，需浏览器认证
- **内容**: SB 广告的实时流量和转化数据集。包含 impressions, clicks, cost, viewableImpressions, newToBrandMetrics, videoMetrics 等字段定义。
- **相关报告**: SB Campaign, AdGroup, AdProduct

### 1.2 Amazon Marketing Stream -- SD Performance Dataset
- **URL**: https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-stream/datasets/sd-performance
- **状态**: JavaScript 渲染，需浏览器认证
- **内容**: SD 广告的实时数据集 schema。包含 costType, bidOptimization, viewableImpressions 等 SD 独有字段。
- **相关报告**: SD Campaign, AdGroup, AdProduct, Targeting

### 1.3 Amazon Ads API v3 Report Types
- **URL**: https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview
- **状态**: JavaScript 渲染，需浏览器认证
- **内容**: SB/SD 报告类型列表:
  - SB: sbCampaigns, sbAdGroups, sbTargeting, sbSearchTerm, sbAdvertisedProduct, sbPurchasedProduct, sbPlacement
  - SD: sdCampaigns, sdAdGroups, sdTargeting, sdAdvertisedProduct, sdPurchasedProduct

### 1.4 Amazon Ads API v3 Reporting FAQ
- **URL**: https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/faq
- **状态**: JavaScript 渲染，需浏览器认证
- **内容**: SB 14天归因窗口说明、SD 展示归因说明

### 1.5 Amazon Performance Metrics Definitions
- **URL**: https://advertising.amazon.com/help/GG44RFW942U9F6F5
- **状态**: WebSearch 返回 tracking pixel，内容不可直接获取
- **内容**: (据描述) 所有广告指标官方定义，含 SB/SD 独有指标

### 1.6 GitHub: Amazon Ads API Discussion #173
- **URL**: https://github.com/amzn/ads-advanced-tools-docs/discussions/173
- **状态**: 可完整抓取
- **内容**: sbPurchasedProduct 和 sdPurchasedProduct API v3 请求示例，含完整字段列表
- **官方回复**: "v3 版本的 SB/SD 报告类型文档在 backlog 中"

---

## 2. 第三方权威来源 (含 SB/SD 独有字段)

### 2.1 Adverity Amazon Ads Fields Reference
- **URL**: https://docs.adverity.com/reference/amazon-ads-fields.html
- **状态**: 通过 WebSearch 确认存在
- **内容**: SD 独有字段的精确描述:
  - `costType`: The pricing model; VCPM or CPC
  - `bidOptimization`: SD_REACH (optimized for reach) or SD_CONVERSION (optimized for conversions)
  - `costPerAcquisition` (CPA): Total cost divided by attributed purchases
  - `advertisedCostOfTotalSales` (ACoTS): Advertising cost as percentage of total sales (including organic)
  - `advertisedShareOfTotalSales` (ASoTS): Advertised sales as percentage of total sales

### 2.2 Supermetrics Amazon Ads Fields
- **URL**: https://docs.supermetrics.com/docs/amazon-ads-fields
- **状态**: 可完整抓取 (部分截断)
- **内容**: SB/SD 特有字段:
  - `newToBrandPurchases14d`: New-to-brand purchases in the 14-day attribution window
  - `newToBrandSales14d`: New-to-brand sales in the 14-day window
  - `newToBrandUnitsSold14d`: New-to-brand units sold
  - `newToBrandPurchasesPercentage14d`: Percentage of purchases from new-to-brand customers
  - `viewableImpressions`: MRC-compliant viewable impressions
  - `costPerThousandViewableImpressions` (VCPM): Cost per 1000 viewable impressions
  - `detailPageViews` (DPV): Detail page views from ad clicks
  - `videoFirstQuartileViews`: 25% video completions
  - `videoMidpointViews`: 50% video completions
  - `videoThirdQuartileViews`: 75% video completions
  - `videoCompleteViews`: 100% video completions
  - `video5sViews`: 5-second video views
  - `videoUnmutes`: Unmute events
  - `videoClickThroughRate` (VCTR): Video click-through rate
  - `videoThroughRate` (VTR): Video completion rate

### 2.3 Two Minute Reports -- Amazon Ads Metrics and Dimensions
- **URL**: https://twominutereports.com/amazon-ads-metrics-and-dimensions/
- **状态**: 可完整抓取
- **内容**: 按报告类型分组的字段:
  - SB metrics: brandSearchCount, video3SecondViews, viewableImpressions
  - SD metrics: costType, bidOptimization, CPA, ACoTS, ASoTS
  - 标注 SP-only, SB-only, SD-only 的字段归属

### 2.4 Openbridge -- Amazon Advertising Attribution Metrics
- **URL**: https://docs.openbridge.com/en/articles/5575121-understanding-amazon-advertising-attribution-metrics
- **状态**: 可完整抓取
- **内容**: SB/SD 归因窗口说明:
  - SB: 14天点击归因
  - SD: 14天点击归因 + 展示归因 (view-through)
  - NTB 指标定义: 过去12个月未购买该品牌的客户

### 2.5 Sellegr8 -- Ads Performance Report Column Description
- **URL**: https://docs.sellegr8.com/article/35-ads-performance-report-column-description
- **状态**: 可完整抓取
- **内容**: 9 个报告标签页含 SB/SD 各类型报告的列定义

---

## 3. 搜索词展示份额相关来源

### 3.1 Search Term Impression Share and Rank
- **来源**: Amazon API v3 SearchTerm report columns
- **SB 独有**: SB SearchTerm 报告比 SP SearchTerm 多了搜索词展示排名和展示份额
- **定义** (来自 Sellegr8 交叉验证):
  - `searchTermImpressionRank`: 该搜索词在所有搜索词中的展示量排名
  - `searchTermImpressionShare`: 该搜索词捕获的可用展示量百分比

---

## 4. NTB (New-to-Brand) 指标来源

### 4.1 NTB 定义的多源交叉验证
- Amazon 官方帮助页 (搜索 "new-to-brand metrics amazon advertising")
- Supermetrics: 7 个 NTB 字段 (含 orders/sales/units + percentages + conversion rate)
- Two Minute Reports: NTB 指标仅 SB/SD 可用，SP 不含
- Openbridge: "New-to-brand customers are those who haven't purchased from the brand in the last 12 months"

---

## 5. 无法直接访问但被多方引用的来源

- Amazon Sponsored Brands Campaign Creation Guide (需要 Seller/Vendor 账号登录)
- Amazon Sponsored Display Help Hub (需要 Seller Central 登录)
- Amazon Ads Console 内建报告文档 (需要有效的广告账号)
- Amazon Ads API v3 SB/SD Report Schema (需要 API 认证 token)

---

## 6. 交叉验证方法

由于 SB/SD 官方文档多数需要认证，本调研采用以下方法确保字段定义的准确性:

1. **赛狐实际导出验证**: 从 `/tmp/report_headers.json` 获取所有报告的实际列名
2. **多源交叉引用**: 每个字段至少在 2 个独立来源 (Supermetrics + Two Minute Reports + Adverity) 中得到一致定义
3. **API v3 GitHub 讨论验证**: 利用 amazon-ads-advanced-tools-docs GitHub 仓库的公开 issue/discussion 验证字段
4. **标记推断**: 无法找到明确官方定义的字段标注 `[推断]`

---

## 7. 2024年10月字段废弃 (仅 SP，不影响 SB/SD)

Supermetrics 记录的 2024年10月字段废弃清单仅影响 SP 广告的旧版归因窗口字段。SB/SD 的 14天窗口字段未受影响。

- **来源**: https://docs.supermetrics.com/docs/amazon-ads-field-changes-october-31-2024

---

## See also
- [SP 调研来源](sources-summary.md) -- SP 报告字段调研的完整来源汇总
- [SB/SD 报告字段权威参考](../sb-sd-report-column-reference.md) -- 基于本来源文档编写的字段定义
