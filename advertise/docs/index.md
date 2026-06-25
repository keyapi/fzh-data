---
okf: v0.1
type: Index
title: Amazon 广告分析模块 — 文档索引
description: 渐进式加载入口
tags: [amazon, advertising, index]
---
# Amazon 广告分析模块 — 文档索引

> 渐进式加载。Agent 接手时只需读 `advertise/AGENT_HANDOFF.md`（入口），需要细节时按下面索引深入。

## 快速导航

| 你需要... | 读这个 |
|----------|--------|
| 快速了解模块 + 开始工作 | [`../AGENT_HANDOFF.md`](../AGENT_HANDOFF.md) |
| 了解怎么运行脚本 | [`../README.md`](../README.md) |
| 查看调研来源和方法论 | [research/](research/) |
| 查看设计决策和架构 | [specs/](specs/) |
| 查阅列名映射、数据源、工具对比 | [reference/](reference/) |
| 查阅经验教训 | [lessons/](lessons/) |

## 目录结构

```
advertise/docs/                         ← OKF v0.1 bundle
├── index.md                           ← 你在这里
├── log.md                             ← 变更历史 (OKF 规范)
├── roadmap.md                         ← 路线图 + 阶段状态
├── research/                          ← 调研报告
├── specs/                             ← 设计文档
├── reference/                         ← 参考资料（按需加载）
│   ├── column-mappings.md
│   ├── data-sources.md
│   ├── tools-ecosystem.md
│   ├── skills-mcp-catalog.md
│   └── source-urls.md
└── lessons/                           ← 经验教训
    └── lessons-learned.md
```

## 2026-06-24 行业全景调研

> 83 次搜索 x 6 维度行业最佳实践调研，含完整来源引用和系统性反驳。

| 你需要... | 读这个 |
|----------|--------|
| 完整行业全景报告 (含来源、Gap分析、优先矩阵) | [research/2026-06-24-industry-landscape.md](research/2026-06-24-industry-landscape.md) |
| 10 大关键洞察 (精炼版) | [lessons/2026-06-24-research-insights.md](lessons/2026-06-24-research-insights.md) |
| 2026 广告策略框架 (ACoS→TACoS, COSMO, 三桶架构) | [reference/2026-strategy-frameworks.md](reference/2026-strategy-frameworks.md) |
| 2026 AI/ML 技术栈 (Multi-Agent, RL, LLM) | [reference/2026-ai-ml-landscape.md](reference/2026-ai-ml-landscape.md) |
| 2026 工具对比 (MCP Server, IvyeaOps, 优麦云) | [reference/2026-tools-comparison.md](reference/2026-tools-comparison.md) |
| 2026 API/数据生态 (Ads API v3/v4, AMC, Consent) | [reference/2026-api-data-ecosystem.md](reference/2026-api-data-ecosystem.md) |
| 2026 系统架构 (数据管道, Multi-Agent, 决策日志) | [reference/2026-system-architecture.md](reference/2026-system-architecture.md) |
| 2026 市场情报 (零售媒体, CPC通胀, 竞争格局) | [reference/2026-market-intelligence.md](reference/2026-market-intelligence.md) |
| 已验证的关键来源 (8 个来源逐一验证) | [reference/verified-sources.md](reference/verified-sources.md) |
| 多账号防关联安全 (Amazon检测机制 + 风险评估) | [reference/2026-security-multi-account.md](reference/2026-security-multi-account.md) |
| SP-API 开发者模型 (私人vs公共 + SPN认证) | [reference/2026-sp-api-developer-model.md](reference/2026-sp-api-developer-model.md) |
| 赛狐 API 实践指南 (接入信息 + Sellfox MCP评估) | [reference/2026-sellfox-api-guide.md](reference/2026-sellfox-api-guide.md) |

## 2026-06-25 赛狐 API 接入

| 你需要... | 读这个 |
|----------|--------|
| 了解赛狐 API 接入踩坑记录 (10条教训) | [lessons/2026-06-25-sellfox-integration-lessons.md](lessons/2026-06-25-sellfox-integration-lessons.md) |
| 查看赛狐 API 探索完整过程 (Playwright+Python) | [research/2026-06-25-sellfox-api-exploration.md](research/2026-06-25-sellfox-api-exploration.md) |
| 获取完整上下文 + 凭证位置 (新对话入口) | [../AGENT_HANDOFF.md](../AGENT_HANDOFF.md) |

## 设计原则

- **渐进披露**: `AGENT_HANDOFF.md` 只放高频信息 + 导航，细节在 `reference/`
- **Diátaxis 四象限**: Tutorial (README) / How-to (AGENT_HANDOFF) / Reference (reference/) / Explanation (research/, specs/)
- **每个文件独立可读**: 不依赖上下文，有 "为什么读这个" 说明
- **交叉引用**: 每页底部有 "See also" 链接
