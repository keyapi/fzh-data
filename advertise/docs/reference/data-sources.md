---
okf: v0.1
type: Reference
title: 数据源全图
description: Amazon SP 13 种报告 + Seller Central + AMC + 第三方数据
tags: [amazon, advertising, reference, data-sources]
---
# 数据源全图 — Amazon 广告数据生态

> 何时读: 需要知道"我们还有什么数据没拿到"，规划下一阶段数据接入。
> 来源: Amazon Ads API v3 官方文档 + 6 维度调研

## 我们已有的 (4/13 种 SP 报告)

| 报告 | 文件 | 行数 | 粒度 |
|------|------|------|------|
| 广告活动 | `商品推广_广告活动_报告.csv` | ~37 | 活动级 |
| 投放 | `商品推广_投放_报告-30.xlsx` | ~180 | 关键词/ASIN 级 |
| 搜索词 | `商品推广_搜索词_报告-30.xlsx` | ~5,000 | 客户搜索词级 |
| 广告位 | `商品推广_广告位_报告-30.xlsx` | ~126 | 广告位级 |

## 我们缺失的 SP 相关报告 (9 种，经官方文档校验)

> ✅ = 官方确认存在 &nbsp; ⚠️ = 仅 Console 可导出（无 API）&nbsp; ❌ = 不存在/信息有误
>
> 校验时间：2026-06-30，来源均为 `advertising.amazon.com` 官方文档。

| # | 报告 | 原 API ID | 校验 | 实际获取方式 | 优先级 | 官方文档 URL |
|---|------|-----------|------|-------------|--------|-------------|
| 1 | Purchased Product | `spPurchasedProduct` | ✅ CONFIRMED | Ads Console + API v3 | 🔴 高 | [API docs](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) |
| 2 | Search Term Impression Share | `spSearchTermImpressionShare` | ⚠️ CONSOLE ONLY | Ads Console → 报告中心（API 不支持，社区呼吁多年仍未开放） | 🔴 高 | [What's New 2021](https://advertising.amazon.com/en-us/resources/whats-new/search-term-impression-report-sponsored-products) |
| 3 | Performance Over Time | — | ⚠️ CONSOLE ONLY | Ads Console → 报告中心。等效数据可通过 `spCampaigns` + `timeUnit: DAILY` 从 API 获取 | 🔴 高 | [Help](https://advertising.amazon.com/help/GEN8F92YG8C694HY) |
| 4 | Budget | — | ❌ NOT FOUND | 不存在独立的 Budget 报告。有 Budget Usage API (`/sp/campaigns/budget/usage`) 返回实时预算使用率，但无"建议预算"功能 | 🟡 中 | [Budget Usage API](https://advertising.amazon.com/API/docs/en-us/guides/budgets/usage/overview) |
| 5 | Advertised Product | `spAdvertisedProduct` | ✅ CONFIRMED | Ads API v3（`groupBy: advertiser`，按 ASIN/SKU 维度，最大 31 天） | 🟡 中 | [API docs](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/advertised-product) |
| 6 | Ad Group (SP) | `spAdGroups` | ❌ NOT FOUND for SP | SP 无独立 Ad Group 报告。用 `spCampaigns` + `groupBy: adGroup` 代替。仅 SB/SD 有 `sbAdGroup`/`sdAdGroup` | 🟢 低 | [API docs](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/ad-group) |
| 7 | Gross and Invalid Traffic | `spGrossAndInvalidTraffic` | ✅ CONFIRMED | Ads Console + API v2/v3（三广告类型 SP/SB/SD 各有变体，回溯 365 天） | 🟢 低 | [Help](https://advertising.amazon.com/help/GSH9JG8Q38TMWGL5) |
| 8 | Audience | `spAudience` | ✅ CONFIRMED | Ads Console + API（仅 SP，需开启 Audience bid adjustment，回溯 90 天） | 🟢 低 | [Help](https://advertising.amazon.ca/help/GA44MFEHYENPNK3D) |
| 9 | Video | `spVideo` | ❌ NOT FOUND | 不存在独立 Video 报告。SB Video 在标准 SB 报告中用 `creativeType: video` 过滤；SP Video (SPV) 为 beta 创意格式，数据含在标准 SP 报告中 | 🟢 低 | — |

## Seller Central 数据（独立于 Ads Console）

| 数据源 | 获取方式 | 关键字段 |
|--------|---------|---------|
| **Business Reports** | Seller Central → 业务报告 | 自然流量、Session%、Buy Box%、自然销售 |
| **Brand Analytics** | Brand Registry 后免费 | Search Query Performance、Demographics、Market Basket |
| **Product Performance Spotlight** | Seller Central | 30+ ASIN 指标 + 25th/50th/75th 百分位对比 |

## Amazon Marketing Cloud (AMC)

| 数据集 | 费用 | 内容 |
|--------|------|------|
| 广告归因事件 | 免费 | 展示/点击/转化/NTB 状态、全漏斗归因 |
| Flexible Shopping Insights | 付费 | 有机转化数据（30 天试用） |
| Retail Purchases 5-Year | $500/月 | CLV、队列分析、流失建模（60 天试用） |

## 第三方数据源

| 来源 | 内容 | API |
|------|------|-----|
| **优麦云** (在用) | 全量历史广告数据 + 销售/库存 | ❌ (仅 Excel 导出) |
| 卖家精灵 | 竞品关键词情报 | ✅ MCP (`open.sellersprite.com/mcp/22`) |
| Keepa | 价格历史 + BSR 趋势 | ✅ API |

## 官方文档 URL

| 资源 | URL |
|------|-----|
| Ads API v3 Report Types | `advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview` |
| 广告指标定义 | `advertising.amazon.com/help/GG44RFW942U9F6F5` |
| 广告位报告帮助 | `advertising.amazon.ca/help/G89VFUTQUWFFN2VU` |
| Brand Analytics | `sell.amazon.com/tools/amazon-brand-analytics` |

## See also
- [列名映射](column-mappings.md)
- [工具生态系统](tools-ecosystem.md)
- [资料来源 URL 索引](source-urls.md)
- [专家系统路线图](../roadmap.md)
