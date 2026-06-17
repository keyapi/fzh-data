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

## 我们缺失的 SP 报告 (9 种)

| # | 报告 | API ID | 优先级 | 用途 |
|---|------|--------|--------|------|
| 1 | Purchased Product | `spPurchasedProduct` | 🔴 高 | 光环效应: 点击广告后买了哪些其他商品 |
| 2 | Search Term Impression Share | `spSearchTermImpressionShare` | 🔴 高 | 每个搜索词 vs 竞品的展示份额 |
| 3 | Performance Over Time | (时间序列) | 🔴 高 | 按日/周趋势，环比/同比基础 |
| 4 | Budget | (beta) | 🟡 中 | 预算利用率 + 建议预算 |
| 5 | Advertised Product | `spAdvertisedProduct` | 🟡 中 | 按 ASIN/SKU 的表现 |
| 6 | Ad Group | `spAdGroups` | 🟢 低 | 广告组级表现 |
| 7 | Gross and Invalid Traffic | `spGrossAndInvalidTraffic` | 🟢 低 | 无效点击/展示监控 |
| 8 | Audience | `spAudience` | 🟢 低 | 受众定向表现 |
| 9 | Video | `spVideo` | 🟢 低 | 视频广告效果 |

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
