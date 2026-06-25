---
okf: v0.1
type: Reference
title: Amazon Ads API 与数据基础设施 — 2026年6月
description: Ads API v3/v4、AMC、数据集成架构、认证安全、速率限制、数据保留、事件驱动
tags: [amazon, advertising, API, AMC, data-pipeline, authentication, 2026]
timestamp: 2026-06-24
---

# Amazon Ads API 与数据基础设施 — 2026年6月

## 1. API Version Status & Migration Timeline

Amazon Ads API 在 2026 年上半年经历了重大版本变革。来源：[Amazon Ads API Release Notes](https://advertising.amazon.com/API/docs/en-us/release-notes/index)

| API / 组件 | 状态 | 关键日期 |
|------------|------|----------|
| V3 API | 当前主版本 | 持续更新中 |
| V2 Keyword API | 已关闭 | 2026年6月1日 |
| PA-API v5 | 已退役 | 2026年5月15日 |
| Unified Reporting | 正式发布 (GA) | 2026年6月8日 |
| 旧版报告 API | 标记退役 | 退役截止 2026年12月31日 |
| Refresh Token | 365天有效期 | 2026年6月30日生效 |

**关键迁移要点：**
- V2 Keyword API 关闭意味着所有关键词操作必须通过 V3 执行
- PA-API v5 退役要求所有联盟营销集成迁移至 Creators API
- Unified Reporting GA 后旧版报告 API 有 6 个月过渡期
- Refresh Token 从 60 天延长至 365 天但需要重新授权

## 2. New 2026 API Capabilities

2026 年新增的 API 能力大幅扩展了广告覆盖面。来源：[ppc.land](https://ppc.land/amazon-ads-may-2026-benchmarks-go-global-mmm-exits-beta-gia-reaches-ga/)、[Amazon Ads What's New](https://advertising.amazon.com/en-us/resources/whats-new/amazon-ads-introduced-enhanced-targeting-capabilities/)

| 能力 | 状态 | 详情 |
|------|------|------|
| Audio Ad Campaigns | 新增 | 16 个专用指标 |
| Benchmark Reports | 全球扩展 | 18 个市场，8 个指标 |
| MMM API | 退出 Beta | 14 个国家可用 |
| GIA (Geo Insights) | GA 正式发布 | Zip-code 级别粒度 |
| Enhanced Targeting | 增强 | 更精细的受众定向 |

**Audio Ad Campaigns：** 新增音频广告类型，16 个指标覆盖播放率、完播率、品牌回想等。

**Benchmark Reports：** 18 个市场提供 8 个竞争基准指标（CTR、CVR、CPC、ACOS 等），帮助广告主了解自己在同行中的位置。

**MMM API：** Marketing Mix Model 退出 Beta，支持 14 个国家的跨渠道归因建模。

**GIA：** Geographic Insights Analysis 正式发布，支持 Zip-code 级别的地理效果分析。

## 3. AMC Deep Dive

Amazon Marketing Cloud (AMC) 是 Amazon 广告数据基础设施的核心组件。来源：[ppc.land](https://ppc.land/amazon-now-lets-amc-users-query-1p-paid-features-for-free-until-end-of-2026/)、[Amazon Ads AMC SQL Basics](https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-cloud/amc-sql/basics)

**关键特性：**
- **免费化（2025年9月起）：** 所有 Sponsored Ads 广告主可免费使用
- **数据回溯：** 25 个月历史数据
- **1P 付费功能：** 免费使用至 2026年12月31日
- **无代码模板：** 预制 SQL 查询模板，降低使用门槛
- **AI 辅助 SQL：** 自然语言生成 SQL 查询
- **家庭级洞察：** 基于家庭（Household）的用户行为分析

**AMC 核心数据表：**

| 表名 | 描述 |
|------|------|
| amazon_retail_purchases | 零售渠道购买记录 |
| conversions_all | 全渠道转化数据 |
| sponsored_ads_traffic | 广告流量（曝光+点击） |
| dsp_impressions | DSP 曝光数据 |
| dsp_clicks | DSP 点击数据 |
| amazon_attributed_events_by_conversion_time | 按转化时间的归因事件 |

AMC 从仅限 DSP 用户的封闭系统变为面向所有广告主的开放平台，是 Amazon 数据战略的最大转变之一。1P 付费功能（自定义受众、高级归因、增量分析）的免费窗口截止 2026 年底，建议尽早利用。

## 4. Data Integration Architecture

Amazon 数据集成架构在 2026 年 5 月因 ADM 发布而重构。来源：[Zonflip](https://zonflip.com/amazon-marketing-stream-the-infrastructure-first-guide-to-real-time-ppc-optimization/)

**三层架构：**

**第一层 — ADM (Amazon Data Manager，2026年5月发布)：**
- Manager Accounts → Data Rooms → Datasets → Activation
- 集中管理跨账号数据共享与激活
- 替代早期的点对点数据共享模式

**第二层 — Marketing Stream（推送层）：**
- 实时推送广告数据流
- 时效性：30-90 分钟（基于小时推送）
- 通过 SQS/SNS/Firehose 投递
- 适合实时竞价优化

**第三层 — AMC（分析层）：**
- 数据洁净室环境
- 跨渠道归因与受众分析
- SQL 查询接口
- 适合深度分析和受众构建

## 5. Authentication & Security

Amazon Ads API 认证体系的关键变化。来源：[Adweek](https://www.adweek.com/commerce/exclusive-amazon-scraps-planned-api-fees-after-backlash-from-tech-firms/)

**OAuth 2.0 LwA (Login with Amazon) 流程：**
- 标准授权码流程
- Refresh Token 有效期延长至 365 天（2026年6月30日起）
- 旧 Token 迁移截止日同步

**安全最佳实践：**

| 实践 | 说明 |
|------|------|
| Per-Request Token 注入 | 每次请求动态获取 Token |
| 5 分钟安全缓冲 | Token 过期前 5 分钟刷新 |
| 401 自动重试 | 过期 Token 触发自动刷新后重试 |
| 共享 Token 缓存 | 多进程共享 Redis 缓存 |

**SP-API 费用取消：**
Amazon 在 2026 年初宣布取消原定的 SP-API 使用费，此举源于开发者社区的强烈反对。这对依赖 SP-API 的所有第三方工具和集成商是一个重大利好。

## 6. Rate Limiting

API 速率限制策略与最佳实践。来源：[Hosni Blog](https://blog.hosni.me/2026/05/amazon-ads-api-at-scale-rate-limiting.html)

**限制机制：**
- 基于每个 Profile 的 Token Bucket 算法
- 不同端点有不同的速率配额
- Report API 限制更严格
- Bulk 端点单次请求上限 1000 条记录

**推荐策略：**

| 策略 | 实现 |
|------|------|
| Exponential Backoff | 1s → 2s → 4s → 8s → 16s... |
| Jitter | 随机抖动避免羊群效应 |
| 请求队列 | 全局优先级队列管理 |
| 429 快速响应 | 立即停止并按 Retry-After 等待 |

报告生成类 API 的速率限制最为严格，建议使用异步报告模式（提交 → 轮询 → 下载）而非同步等待。

## 7. Data Retention Windows

Amazon Ads 数据的保留期限因访问方式而异。来源：[ppc.land](https://ppc.land/amazon-ads-unified-reporting-exits-beta-and-takes-two-old-tools-with-it/)

| 数据源 | 保留期限 | 备注 |
|--------|----------|------|
| Console 界面 | 60 天 | 广告活动控制台 |
| API（实时） | 60-95 天 | 视端点而定 |
| Unified Reporting — 日粒度 | 15 个月 | 2026年6月8日起 |
| Unified Reporting — 月粒度 | 6 年 | 长期趋势分析 |
| AMC | 25 个月 | 数据洁净室 |

**关键含义：**
- 构建自己的数据仓库至关重要——API 无法获取 60-95 天之前的数据
- Unified Reporting 的 15 个月/6 年窗口是历史分析的唯一可靠来源
- AMC 的 25 个月窗口覆盖了两个完整年度周期

## 8. Event-Driven Architecture

Amazon Ads 的事件驱动集成方案。来源：[Epinium](https://epinium.com/en/blog/amazon-marketing-stream-guide/)

**Marketing Stream：**
- 通过 SQS（Simple Queue Service）推送广告事件
- 也支持 SNS（Simple Notification Service）和 Firehose
- 按小时推送，延迟 30-90 分钟
- 事件类型：impression、click、attributed conversion

**SP-API Notifications：**
- 通过 SQS 或 EventBridge 推送
- 覆盖订单、库存、商品变更等事件
- 无标准 HTTP Webhook——必须使用 AWS 服务接收

**重要限制：**
Amazon Ads 生态中**没有标准的 HTTP Webhook**。所有事件驱动集成必须通过 AWS 服务（SQS/SNS/EventBridge/Firehose）接收。这意味着构建实时响应系统需要 AWS 基础设施。

## 9. Attribution API Changes

归因 API 在 2026 年初有重大更新。来源：[Amazon Ads View Attribution](https://advertising.amazon.com/en-ca/resources/whats-new/view-attribution-updates-for-amazon-store-ads)

**View Attribution 收紧（2026年1月）：**
- 曝光归因窗口缩短，减少无效归因
- 仅计入可见曝光（≥50% 像素在视口内 ≥1 秒）
- 适用于 Amazon Store Ads 和其他展示广告

**MTA Beta 指标：**
- Multi-Touch Attribution 进入 Beta
- 支持线性、时间衰减、U 型、W 型等模型
- 替代传统的 Last-Touch Attribution
- 更精确地分配转化功劳到各触点

## 10. Reference Data Architecture

AWS 推荐的 Amazon Ads 数据集成参考架构。来源：[AWS Solutions](https://aws.amazon.com/cn/solutions/guidance/ingesting-amazon-vendor-central-and-amazon-ads-data-on-aws/)

```
┌─────────────┐     ┌──────────────────┐     ┌────────────┐
│  Ingestion  │────▶│ Stream Processing│────▶│  Storage   │
│             │     │                  │     │            │
│ Amazon Ads  │     │ Lambda / Kinesis │     │ S3 /       │
│ API + SP-API│     │ / Glue Streaming │     │ Redshift   │
│ + AMC       │     │                  │     │            │
└─────────────┘     └──────────────────┘     └─────┬──────┘
                                                   │
                                                   ▼
┌─────────────┐     ┌──────────────────┐
│ Application │◀────│   Analytics      │
│             │     │                  │
│ BI / ML /   │     │ Athena /         │
│ Dashboard   │     │ QuickSight /     │
│             │     │ SageMaker        │
└─────────────┘     └──────────────────┘
```

**各层说明：**
- **Ingestion：** Amazon Ads API（报告）、SP-API（零售）、AMC（分析）、Marketing Stream（实时）
- **Stream Processing：** Lambda 用于轻量转换，Kinesis 用于实时流，Glue Streaming 用于 ETL
- **Storage：** S3 作为数据湖，Redshift 作为数据仓库
- **Analytics：** Athena 用于即时查询，QuickSight 用于可视化，SageMaker 用于 ML 模型
- **Application：** BI 仪表盘、ML 驱动的竞价引擎、自动化告警

## 11. Limitations & Counter-Arguments

当前 Amazon Ads 生态的关键局限与批判性分析。

| 局限 | 影响 | 缓解方案 |
|------|------|----------|
| 无直接 Review API | 无法程序化管理评论 | 需第三方爬虫方案 |
| 无标准 HTTP Webhooks | 事件驱动需 AWS 基础设施 | SQS→Lambda→自建 Webhook 桥 |
| Audio Ads 不含 Podcast | 音频广告覆盖不完整 | 等待后续更新 |
| Refresh Token 仍有过期 | 需定期重新授权 | 构建 Token 监控与告警 |
| Report API 速率严格 | 大规模数据获取受限 | 多 Profile 分片 + 异步模式 |

**当前体系的批判性分析：**

> 截至 2026 年中，Amazon Ads 数据生态虽然大幅改善，但仍存在结构性局限：
> - **60 天 API 窗口**意味着没有自主数据仓库就无法做长期分析
> - **静态快照报告**（即使是 Unified Reporting）缺乏实时交互性
> - **没有实时竞价反馈**——Marketing Stream 的 30-90 分钟延迟对于 Dayparting 不够
> - **AMC 仍非默认开启**——虽然免费化进程加速，但许多广告主仍未激活
> - **Unified Reporting 强制迁移**——2026 年 12 月 31 日前必须完成，不容忽视

## See also

- [2026-tools-comparison.md](2026-tools-comparison.md) — Amazon 广告工具与开源对比
- [Amazon Ads API Release Notes](https://advertising.amazon.com/API/docs/en-us/release-notes/index)
- [AMC SQL Basics](https://advertising.amazon.com/API/docs/en-us/guides/amazon-marketing-cloud/amc-sql/basics)
- [Marketing Stream Guide (Epinium)](https://epinium.com/en/blog/amazon-marketing-stream-guide/)
- [Marketing Stream Guide (Zonflip)](https://zonflip.com/amazon-marketing-stream-the-infrastructure-first-guide-to-real-time-ppc-optimization/)
- [Amazon Ads Rate Limiting (Hosni)](https://blog.hosni.me/2026/05/amazon-ads-api-at-scale-rate-limiting.html)
- [AWS Data Ingestion Solution](https://aws.amazon.com/cn/solutions/guidance/ingesting-amazon-vendor-central-and-amazon-ads-data-on-aws/)
- [Airbyte Amazon Ads Connector](https://airbyte.com/connectors/amazon-ads)
