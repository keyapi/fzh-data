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

### 各报告列结构详表

以下为 6 种可获取报告（4 API + 2 Console-only）的关键列。首次接入新报告类型时无需重新搜索官网。

#### 1. Purchased Product Report（✅ API + Console）

> 光环效应核心数据源。显示点击广告后用户实际购买了哪些商品（含非广告 ASIN）。

| 列名 (EN) | 预计中文后台列名 | 含义 |
|-----------|----------------|------|
| `advertisedAsin` | 已推广的 ASIN | 被点击的广告商品 ASIN |
| `advertisedSku` | 已推广的 SKU | 被点击的广告商品 SKU |
| `campaignName` / `campaignId` | 广告活动名称/ID | |
| `adGroupName` / `adGroupId` | 广告组名称/ID | |
| `impressions` | 展示量 | |
| `clicks` | 点击量 | |
| `cost` | 花费 | |
| `purchases1d` / `7d` / `14d` / `30d` | X天总订单数 | 归因窗口内广告 ASIN 的订单 |
| `sales1d` / `7d` / `14d` / `30d` | X天总销售额 | 归因窗口内广告 ASIN 的销售额 |
| `unitsSoldOtherSku1d` ~ `30d` | X天内其他SKU销售量 | **光环效应**：买了别的 SKU |
| `salesOtherSku1d` ~ `30d` | X天内其他SKU销售额 | **光环效应**：别的 SKU 销售额 |
| `purchasesOtherSku1d` ~ `30d` | X天内其他SKU订单数 | **光环效应**：别的 SKU 订单数 |

> 配置：`groupBy: ["asin"]`，归因窗口 1d/7d/14d/30d，数据保留 ~65-95 天
> 已知坑：API 输出和 Console UI 导出可能有小幅差异（Amazon 官方确认属正常）

#### 2. Search Term Impression Share Report（⚠️ Console only）

> 每个搜索词上你的展示占比和排名。**API 不支持，只能 Console 手动导出**。

| 列名 | 含义 |
|------|------|
| `searchTermImpressionShare` | 搜索词展示份额 — 你的广告在该搜索词上获得的展示占所有广告主总展示的百分比 |
| `searchTermImpressionRank` | 搜索词展示排名 — 你在该搜索词上的排名（1=第一） |
| 其他列 | 同搜索词报告的标准列（impressions, clicks, cost, sales 等） |

> API 中有类似指标 `topOfSearchImpressionShare`（v4 keyword recommendations API），但仅覆盖 Top of Search 位置，不等同于此报告

#### 3. Performance Over Time Report（⚠️ Console only）

> 每日趋势视图。Console 专用格式，但等效数据可通过 API 获取。

| 列名 | 含义 |
|------|------|
| `date` | 日期 |
| `clicks` | 点击量 |
| `cpc` | 单次点击成本 |
| `spend` | 花费 |

> 等效 API 方案：调用 `spCampaigns`（或 `spAdGroups`）report type，设置 `timeUnit: DAILY` — 底层指标完全一致，只是展示格式不同。Console 回溯 90 天。

#### 4. Advertised Product Report（✅ API v3）

> 按 ASIN/SKU 的广告表现。当前项目中无等效数据。

| 列名 (EN) | 预计中文后台列名 | 含义 |
|-----------|----------------|------|
| `advertisedAsin` | 已推广的 ASIN | |
| `advertisedSku` | 已推广的 SKU | |
| `campaignId` / `adGroupId` / `adId` | 活动/组/广告 ID | 三级层级 |
| `impressions` | 展示量 | |
| `clicks` | 点击量 | |
| `cost` | 花费 | |
| `purchases1d` / `7d` / `14d` / `30d` | X天总订单数 | |
| `sales1d` / `7d` / `14d` / `30d` | X天总销售额 | |
| `acosClicks7d` / `acosClicks14d` | ACOS | |
| `roasClicks7d` / `roasClicks14d` | ROAS | |

> 配置：`groupBy: ["advertiser"]`，`timeUnit: SUMMARY 或 DAILY`，最大 31 天范围，保留 95 天

#### 5. Gross and Invalid Traffic Report（✅ API + Console）

> 无效点击/展示监控。Amazon 只对有效事件收费。

| 列名 (EN) | 预计中文后台列名 | 含义 |
|-----------|----------------|------|
| `grossImpressions` | 总展示量 | 含无效 |
| `grossClicks` | 总点击量 | 含无效 |
| `invalidImpressions` | 无效展示量 | Amazon 过滤掉的展示 |
| `invalidClicks` | 无效点击量 | Amazon 过滤掉的点击（不收费） |
| `invalidImpressionRate` | 无效展示率 | |
| `invalidClickRate` | 无效点击率 | |

> 回溯 365 天。SP/SB/SD 三种广告类型各有独立变体。

#### 6. Audience Report（✅ API + Console）

> 受众定向表现。需要 campaign 层面开启 audience bid adjustments 才有数据。

| 列名 (EN) | 预计中文后台列名 | 含义 |
|-----------|----------------|------|
| `audienceId` / `audienceName` | 受众 ID/名称 | AMC 创建或 Amazon 内置受众 |
| `impressions` | 展示量 | |
| `clicks` | 点击量 | |
| `ctr` | 点击率 | |
| `cpc` | 单次点击成本 | |
| `cost` | 花费 | |
| `roas` | 广告投资回报率 | |
| `sales` | 销售额 | |
| `orders` | 订单数 | |
| `unitsSold` | 销售量 | |

> 仅 SP，回溯 90 天。SD 有独立版本（`sdAudience`），SB 无标准受众报告。

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
