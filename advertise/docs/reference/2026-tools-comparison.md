---
okf: v0.1
type: Reference
title: Amazon 广告工具与开源对比 — 2026年6月
description: 商业SaaS、开源方案、MCP Server生态、SDK库、数据管道、优麦云深度分析
tags: [amazon, advertising, tools, saas, open-source, MCP, comparison, 2026]
timestamp: 2026-06-24
---

# Amazon 广告工具与开源对比 — 2026年6月

## 1. Enterprise SaaS

企业级 Amazon 广告工具市场由四家主导。以下对比基于公开定价与功能矩阵。来源：[SmartScout](https://www.smartscout.com/amazon-software-comparison/best-enterprise-amazon-advertising-software-tools-for-amazon-ppc-skai-perpetua-quartile-feedvisor-and-pacvue)、[Canopy Management](https://canopymanagement.com/amazon-advertising-tools-worth-paying-for/)

| 产品 | 起价 | AI 竞价 | 多市场 | AMC | DSP | 评分 | 最佳场景 |
|------|------|---------|--------|-----|-----|------|----------|
| Perpetua | $695/月 | 是 | 是 | 是 | 部分 | 4.7 | 品牌增长 + 全漏斗 |
| Pacvue | ~$500/月 | 是 | 是 | 是 | 是 | 4.5 | 企业多渠道 |
| Skai | $7,500/月 | 是 | 是 | 是 | 是 | 4.3 | 大型代理机构 |
| Quartile | $895/月 | 是 | 是 | 部分 | 否 | 4.4 | 中小企业优化 |

Perpetua 在 AI 自动化方面最强，Pacvue 在 DSP 和零售媒体覆盖面最广，Skai 适合需要跨渠道（Amazon + Walmart + Google）的顶级代理商，Quartile 在性价比方面最佳。

## 2. Mid-Market SaaS

中端工具覆盖面广，从免费增值到数百美元。来源：[atom11](https://www.atom11.co/blog/best-amazon-ppc-software)、[Profasee](https://profasee.com/best-amazon-ppc-software/)

| 产品 | 起价 | 特色 |
|------|------|------|
| Helium 10 Ads | $129/月 | 全栈（关键词 + 广告 + 分析） |
| Teikametrics | $179/月 | AI 驱动 Flywheel 引擎 |
| atom11 | $499/月 | 英国开发，规则引擎为核心 |
| Scale Insights | $78/月 | 性价比之王，自动化规则 |
| BQool | $99/月 | 自动调价 + 广告 |
| SellerApp | 免费增值 | 入门数据分析 |
| AdLabs | $40/月 | 低价全功能 |

Scale Insights 以 $78/月提供最完整的自动化，AdLabs 以 $40/月成为价格最低的全功能工具，Helium 10 Ads 适合已使用 Helium 10 生态的用户。

## 3. Feature Comparison Matrix

全维度对比矩阵。来源：[SmartScout](https://www.smartscout.com/amazon-software-comparison/best-enterprise-amazon-advertising-software-tools-for-amazon-ppc-skai-perpetua-quartile-feedvisor-and-pacvue)、[atom11](https://www.atom11.co/blog/best-amazon-ppc-software)

| 工具 | 定价 | AI 竞价 | 多市场 | AMC | DSP | 规则引擎 | 自助托管 | 评分 |
|------|------|---------|--------|-----|-----|----------|----------|------|
| Perpetua | $695/月 | 强 | 是 | 是 | 部分 | 有限 | 否 | 4.7 |
| Pacvue | ~$500/月 | 强 | 是 | 是 | 是 | 可定制 | 否 | 4.5 |
| Skai | $7,500/月 | 强 | 是 | 是 | 是 | 可定制 | 否 | 4.3 |
| Quartile | $895/月 | 强 | 是 | 部分 | 否 | 有限 | 否 | 4.4 |
| Teikametrics | $179/月 | 中等 | 是 | 否 | 否 | 有限 | 否 | 4.2 |
| Scale Insights | $78/月 | 基础 | 是 | 否 | 否 | 强 | 否 | 4.3 |
| atom11 | $499/月 | 中等 | 是 | 否 | 否 | 强 | 否 | 4.0 |
| AdLabs | $40/月 | 基础 | 是 | 否 | 否 | 中等 | 否 | 4.0 |
| Helium 10 Ads | $129/月 | 基础 | 是 | 否 | 否 | 中等 | 否 | 4.1 |
| IvyeaOps | 免费 | LLM | 部分 | 否 | 否 | 强 | 是 | — |
| 优麦云 | ¥499起 | 3 AI | 是 | 否 | 否 | 强(6引擎) | 否 | 4.0 |

## 4. Open Source — IvyeaOps（最重要）

IvyeaOps 是当前最完整的开源 Amazon 广告管理工具。来源：[GitHub](https://github.com/Hector-xue/IvyeaOps)

**核心信息：**
- **许可证：** AGPL-3.0
- **版本：** v1.0.64
- **技术栈：** FastAPI + React + Vite + SQLite
- **部署：** 自托管，提供 Windows EXE 一键安装包

**功能模块：**
- **广告仪表盘：** 多账号数据聚合展示
- **搜索词诊断：** 自动识别低效搜索词
- **规则引擎 + LLM 引擎：** 规则与 AI 双重优化策略
- **否定关键词管理：** 自动添加/移除否定关键词
- **竞价优化：** 基于规则的自动竞价调整
- **AI 代理：** 多个专业 Agent 协同工作
- **市场调研：** 竞争分析 + 关键词研究
- **Listing 生成：** AI 辅助编写产品文案

IvyeaOps 代表了"自托管 Amazon 广告工具"的最完整形态，是商业 SaaS 的唯一真正开源替代方案。

## 5. Other Open Source

除 IvyeaOps 外，还有三个重要的开源项目。来源：[claudesdk-amazon-skills-chat](https://github.com/liangdabiao/claudesdk-amazon-skills-chat)、[guidance-for-advertising-agents-on-aws](https://github.com/aws-solutions-library-samples/guidance-for-advertising-agents-on-aws)、[ads-advanced-tools-docs](https://github.com/amzn/ads-advanced-tools-docs)

| 项目 | 描述 | 技术栈 |
|------|------|--------|
| AmazonSkillsChat | 54 个技能，基于 Claude SDK | Claude SDK + TypeScript |
| AWS Advertising Agents | 21+ 广告 Agent，基于 Bedrock | AWS Bedrock + CDK |
| Amazon Ads Advanced Tools Docs | Amazon 官方高级工具文档 | 文档 + 示例代码 |

AmazonSkillsChat 将广告操作封装为 Claude 可调用的技能，AWS Advertising Agents 是 AWS 官方解决方案库中的广告 Agent 参考架构，Ads Advanced Tools Docs 是 Amazon 官方维护的高级工具文档仓库。

## 6. MCP Server Ecosystem

MCP (Model Context Protocol) Server 生态在 2026 年爆发，已有 6 个 Amazon 广告相关服务器。来源：[LobeHub](https://lobehub.com/mcp/kuudoai-amazon-ads-mcp)、[Synter-Media-AI](https://github.com/Synter-Media-AI/mcp-server)、[npm @cesteral/amazon-dsp-mcp](https://www.npmjs.com/package/@cesteral/amazon-dsp-mcp)

| MCP Server | 许可证 | 平台覆盖 | 特色 |
|------------|--------|----------|------|
| Amazon Official MCP | 专有 | Amazon Ads API | 官方维护，覆盖核心 Ads API |
| KuudoAI Amazon Ads MCP | MIT | Amazon Ads API | 开源，社区驱动 |
| Synter-Media-AI MCP | MIT | 9+ 广告平台 | 多平台聚合（Amazon + Meta + Google + TikTok） |
| marketplaceadpros MCP | 专有 | Amazon Ads API | 商业级 MCP |
| adspirer MCP | 免费 | Amazon Ads API | 免费使用 |
| @cesteral/amazon-dsp-mcp | npm 包 | Amazon DSP | JS 生态专用，DSP 操作 |

Synter-Media-AI 以覆盖 9+ 平台领先，KuudoAI 以 MIT 许可证开源，@cesteral/amazon-dsp-mcp 是唯一专攻 DSP 的 MCP Server。

## 7. API/SDK Libraries

主要 SDK 库与 API 迁移动态。来源：[PA-API v5 迁移](https://dev.to/th3nate/amazon-pa-api-v5-is-shutting-down-april-30-2026-here-is-what-changes-at-the-auth-layer-22ek)

**python-amazon-ad-api (v0.8.2)：**
- 用于 Amazon Advertising API 的 Python 库
- 支持 SP/SB/SD 全类型广告
- 报告、关键词、竞价操作

**PA-API v5 → Creators API 迁移：**
- PA-API v5 于 2026 年 4 月 30 日正式退役
- 认证层迁移至 Amazon Creators API
- 开发者需更新 OAuth 流程和端点

## 8. Data Pipeline Tools

数据管道工具用于将 Amazon Ads 数据集成到数据仓库。来源：[Airbyte](https://airbyte.com/connectors/amazon-ads)

| 工具 | 描述 |
|------|------|
| Airbyte | Amazon Ads 连接器 v7.2.3，600+ 目标端 |
| dbt | 数据转换层，Amazon Ads 数据建模 |
| Airflow / Prefect | 调度引擎，管理数据管道执行 |

Airbyte 的 Amazon Ads 连接器 v7.2.3 支持 Sponsored Ads、Brand Analytics、DSP 报告，可同步至 BigQuery、Snowflake、Redshift 等 600+ 目标端。

## 9. 优麦云 (Youmaiyun) 深度分析

优麦云是中文市场领先的 Amazon 广告 SaaS。来源：[SellerSpace 帮助文档](https://www.sellerspace.com/zh/help/doc/ppc-campaign-guide/)、[SellerSpace 博客](https://www.sellerspace.com/zh/blog/SellerSpace-with-Amazon-AD/)

**数据连接：**
- 通过 SP-API 连接 SP/SB/SD 广告数据
- 同步周期：30-60 分钟

**Ad GPS 功能：**
- 广告活动地理可视化
- 排名追踪与竞品分析

**规则引擎：**
- 6 个规则引擎（关键词、竞价、预算、搜索词、否定、时段）
- 12 种触发条件
- 3 个 AI 模型优化（收取 3% 服务费）

**定价层次：**
| 版本 | 价格 | 适用场景 |
|------|------|----------|
| Viewer | ¥0/月 | 只读查看 |
| Startup | ¥499/月 | 小卖家 |
| Enterprise | ¥1,299/月 | 中大型卖家 |
| Premium | ¥2,999/月 | 大卖/多账号 |

## 10. Free Tools

Amazon 官方的免费 AI 工具矩阵。来源：[mi-3.com.au](https://www.mi-3.com.au/10-06-2026/amazon-ads-expands-ai-powered-campaign-management-tool-australia)

| 工具 | 费用 | 描述 |
|------|------|------|
| Amazon Ads Agent | 免费 | AI 驱动的广告活动管理 |
| Creative Agent | 免费 | AI 生成广告创意素材 |
| Native Console | 免费 | Amazon Ads 管理控制台 |

Amazon 在 2026 年 6 月将 Ads Agent 扩展到澳大利亚，标志着其 AI 工具全球化的加速。免费工具的持续强化给第三方 SaaS 带来了显著竞争压力。

## 11. Selection Guide by Spend

按广告花费分级推荐。来源：[SmartScout](https://www.smartscout.com/amazon-software-comparison/best-enterprise-amazon-advertising-software-tools-for-amazon-ppc-skai-perpetua-quartile-feedvisor-and-pacvue)、[Profasee](https://profasee.com/best-amazon-ppc-software/)

| 月广告费 | 推荐工具 |
|----------|----------|
| < $5,000 | Amazon Native Console + 关键词工具 |
| $5,000 - $20,000 | Teikametrics / Scale Insights |
| > $20,000 | Perpetua / Quartile / Pacvue |
| 代理商 | Pacvue / AdLabs |

小额预算建议先用免费原生工具 + 关键词分析，中等预算可选择 Scale Insights（$78/月，最佳性价比）或 Teikametrics（$179/月，AI 引擎），高预算企业按需求选择 Perpetua（AI）、Quartile（性价比）或 Pacvue（全渠道）。

## 12. 2026 Trends

2026 年 Amazon 广告工具的十大趋势：

1. **MCP 生态主导：** MCP Server 成为 AI Agent 与广告 API 的标准桥接层，6+ 服务器覆盖全场景。来源：[LobeHub](https://lobehub.com/mcp/kuudoai-amazon-ads-mcp)
2. **Amazon 免费 AI 攻势：** Ads Agent + Creative Agent 免费化，挤压第三方 SaaS 生存空间。来源：[mi-3.com.au](https://www.mi-3.com.au/10-06-2026/amazon-ads-expands-ai-powered-campaign-management-tool-australia)
3. **AI > 规则引擎：** LLM 驱动的竞价优化逐步取代传统规则引擎，Perpetua 和 IvyeaOps 为代表。来源：[SmartScout](https://www.smartscout.com/amazon-software-comparison/best-enterprise-amazon-advertising-software-tools-for-amazon-ppc-skai-perpetua-quartile-feedvisor-and-pacvue)
4. **自托管运动：** IvyeaOps (AGPL-3.0) 引领开源自托管趋势，打破 SaaS 锁定。来源：[GitHub](https://github.com/Hector-xue/IvyeaOps)
5. **AMC 扩展：** 1P 付费功能免费至 2026 年底，SQL 模板化，25 个月回溯，用户覆盖面快速扩大。来源：[ppc.land](https://ppc.land/amazon-now-lets-amc-users-query-1p-paid-features-for-free-until-end-of-2026/)
6. **利润感知优化：** 工具从"只看 ACOS"转向"利润感知"综合优化。
7. **PA-API v5 退役：** 2026 年 4 月 30 日下线，强制迁移到 Creators API。来源：[dev.to](https://dev.to/th3nate/amazon-pa-api-v5-is-shutting-down-april-30-2026-here-is-what-changes-at-the-auth-layer-22ek)
8. **零售感知自动化：** 库存 + 价格 + 广告联动优化。
9. **混合 SaaS + 代理商模式：** Pacvue、Skai 同时提供工具 + 托管服务。
10. **按花费分层选择：** 从"一刀切推荐"转向基于广告花费的精准分层推荐。

## See also

- [2026-api-data-ecosystem.md](2026-api-data-ecosystem.md) — Amazon Ads API 与数据基础设施
- [SmartScout Enterprise Tools Comparison](https://www.smartscout.com/amazon-software-comparison/best-enterprise-amazon-advertising-software-tools-for-amazon-ppc-skai-perpetua-quartile-feedvisor-and-pacvue)
- [Canopy Management: Tools Worth Paying For](https://canopymanagement.com/amazon-advertising-tools-worth-paying-for/)
- [atom11 Best PPC Software](https://www.atom11.co/blog/best-amazon-ppc-software)
- [Profasee Best Amazon PPC Software](https://profasee.com/best-amazon-ppc-software/)
- [IvyeaOps GitHub](https://github.com/Hector-xue/IvyeaOps)
- [AmazonSkillsChat](https://github.com/liangdabiao/claudesdk-amazon-skills-chat)
- [AWS Advertising Agents](https://github.com/aws-solutions-library-samples/guidance-for-advertising-agents-on-aws)
- [Amazon Ads Advanced Tools Docs](https://github.com/amzn/ads-advanced-tools-docs)
- [Synter-Media-AI MCP Server](https://github.com/Synter-Media-AI/mcp-server)
