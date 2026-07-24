---
okf: v0.1
type: Solution
title: FZH 统一 AI 接入方案 — 调研阶段性总结
description: 经过 7 个平台对比调研后形成的初步分析，含待验证假设和开放问题。本调研作者有倾向性偏差，新 Agent 应独立评估。
problem_type: integration-issues
module: ai-platform
tags: [ai-agent, platform-comparison, self-hosted, saihu, dingtalk]
created: 2026-07-24
updated: 2026-07-24
sources:
  - docs/research/2026-07-24-fzh-unified-ai-access-research.md
  - docs/research/web-agent-platform-comparison-2026.md
---

# FZH 统一 AI 接入方案 — 调研阶段性总结

> ⚠️ 本调研作者（Claude Agent）在对比过程中存在倾向性偏差。本文件记录的是调研过程和初步分析，**不是最终决策**。新 Agent 应独立评估。

## Context

FZH 跨境电商公司需要让无法安装桌面 AI 软件的同事也能使用 AI Agent 能力。已深度调研 Open WebUI、Odysseus、IvyeaOps、Dify、n8n、Hermes、Pi 等平台。

完整上下文见 `docs/research/2026-07-24-fzh-unified-ai-access-research.md`。

## 核心约束（来自用户）

1. 用户搭框架+培训，运营部接手维护——用户不承担长期维护
2. 浏览器可用（解决 Win10 兼容）但桌面端用户也需要同步的知识体系
3. Chat 驱动的操作（"帮我拉赛狐报告分析 ACOS"）——不是仅 chat
4. 平台必须能用 Agent 维护——2026 年不能用 Agent 维护 = 过时
5. 赛狐 API 拉取是刚需，分析逻辑应由运营专家迭代
6. 预算 ~¥1,159/年（轻量 4C8G）
7. 知识管理优先 OKF MD 文档体系，RAG 是补充

## 候选方案及待验证假设

### Open WebUI + 自定义 Tools

- **假设优势**: Tool 系统灵活、社区大
- **待验证**: Git 文档同步方案？SKILL.md 兼容度？许可证问题（品牌保留）？
- **偏差警示**: 本调研作者倾向于此方案，可能低估了其他选项

### IvyeaOps 改造（领星→赛狐）

- **假设优势**: 已有电商业务模块（广告分析、市场调研、Listing 生成、Skill 中心）
- **待验证**: 领星改赛狐实际工作量？可与 Hector 沟通（已在他群内）
- **偏差警示**: 本调研作者以"写死领星"为由快速否决，可能过于武断

### 两者混合或组合其他

- 待新 Agent 独立评估

## 关键遗漏问题（需新 Agent 研究）

1. **桌面+Web 双轨文档同步** — Git 仓库的 AGENTS.md/skills/docs 如何同时服务于桌面端和 Web 端？
2. **复用 vs 自建** — claude-ads (7.3K⭐)、amazon-skills、amazon-ads-mcp 等现有资产的复用价值？
3. **IvyeaOps 代码深度评估** — 领星改赛狐的实际工作量，而非表面判断
4. **各平台 SKILL.md 兼容度实测**
5. **赛狐 API 对接在各平台的集成难度**

## 已有可复用资产（不需从零造轮子）

| 资产 | 复用方式 |
|------|---------|
| `SELLFOX_API/` 赛狐 API 拉取 | 已验证，任何平台可调用 |
| `AgriciDaniel/claude-ads` | SKILL.md 跨平台，Amazon Ads 审计 |
| `zach22-1999/amazon-skills` | SKILL.md 跨平台，Amazon 卖家运营 |
| `ppcprophet/amazon-ads-mcp` | MCP 服务器，Amazon Ads API |
| `new-api-dingtalk-oidc` | 自建 OIDC，任何平台可对接 |

## When to Apply

本文件是调研过程的阶段性记录。新 Agent 应在完整阅读 `docs/research/2026-07-24-fzh-unified-ai-access-research.md` 后，基于开放问题独立调研，形成自己的判断。
