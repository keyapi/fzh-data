# 可复用 Skills/MCP 目录

> 何时读: 需要评估"哪些功能可以直接用现成的，不需要从零开发"。
> 调研日期: 2026-06-17

## MCP Servers（最低门槛 — 直接接入 Claude）

| 名称 | 端点/安装 | 覆盖范围 |
|------|----------|---------|
| [Two Minute Reports MCP](https://github.com/twominutereports/twominutereports-mcp) | `mcp.twominutereports.com/mcp` | 22+ 营销源含 Amazon Ads + Seller Central |
| [Amazon 官方 Ads MCP](https://advertising.amazon.com) | 公测中 (2026.2) | 自然语言→Ads API 调用 |
| [Agent Central MCP](https://github.com/agentcentral-to/agent-central-mcp) | `mcp.agentcentral.to/mcp` | 144 工具: Ads + Seller Central + 库存 |
| [DataDoe Amazon MCP](https://www.datadoe.com/connect/amazon/mcp) | 托管 | SP-API + 利润基元，无需开发者审批 |

## Agent Skills（SKILL.md 文件）

| 名称 | 安装 | 功能 |
|------|------|------|
| [LaunchFast PPC Research](https://github.com/BlockchainHB/launchfastmcp-skills) | `npx skills add ...` | 15 ASIN 竞品关键词→批量 CSV |
| [ads-audit / ads-amazon](https://github.com/AgriciDaniel/claude-ads) | GitHub | 250+ 检查跨 Google/Meta/Amazon/LinkedIn/TikTok |
| [claudesdk-amazon-skills-chat](https://github.com/liangdabiao/claudesdk-amazon-skills-chat) | GitHub | 54 个中文 Amazon 卖家 Skill（参考架构） |

## 开源 Python 工具

| 名称 | 用途 |
|------|------|
| [amz-ppc-optimizer](https://github.com/ehsanmqn/amz-ppc-optimizer) | 搜索词报告分析 + ACoS 过滤 + 出价调整 |
| [AmazonFBA Dashboard](https://github.com/Joao-M-Silva/AmazonFBA) | 全产品生命周期 + PPC 模块 |
| [dbt_ad_reporting](https://github.com/simon-stepper/dbt_ad_reporting) | 多平台广告数据建模 (dbt + SQL) |

## API 库

| 语言 | 包名 | 状态 |
|------|------|------|
| Python | `python-amazon-ad-api` v0.6.4 | 活跃 (12.6K/月) |
| Node.js | `@amazon-sp-api-release/sp-api-dev-mcp` v1.0.3 | Amazon 官方 (2026.5) |

## Skill 发现平台

| 平台 | 规模 |
|------|------|
| [SkillsMP](https://skillsmp.com) | 120 万+ SKILL.md 文件 |
| [awesome-claude-code](https://github.com/subinium/awesome-claude-code) | 精选 Skills/MCP |
| [antigravity-awesome-skills](https://github.com/zebbern/antigravity-awesome-skills) | 1,493+ Skills |
| OpenSkills CLI | `npm i -g openskills` |

## 结论

**可复用的**: API 层 (python-amazon-ad-api) 和 MCP 层 (Two Minute Reports / Amazon 官方) 有现成方案。
**需要自建**: 定制 Excel 报告管道 + 中文卖家特有业务逻辑 + 优麦云 Excel 导入适配。

## See also
- [工具生态系统](tools-ecosystem.md)
- [数据源全图](data-sources.md)
- [专家系统路线图](../roadmap.md)
