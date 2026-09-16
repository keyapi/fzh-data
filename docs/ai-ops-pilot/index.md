---
okf: v0.1
type: Index
title: AI 运营试点 — 文档索引
description: 对黄总《FZH AI运营试点计划 1.0》的评估与反提案；含与项目已有工作的对照
tags: [ai-pilot, assessment, ops, index]
---

# AI 运营试点 — 文档索引

> 针对老板 2026-09-15 提出的《FZH AI运营试点计划 1.0 — 30天落地行动方案》（原 PDF 存于 `D:\Work\AI\`）。

| 你需要… | 读这个 |
|---------|--------|
| **递给老板和老板 Agent 的（对外）** | [brief-for-boss.md](brief-for-boss.md) |
| 2026-09 企业助手/Agent 载体与架构调研 | [assistant-platform-research-2026-09.md](assistant-platform-research-2026-09.md) |
| **Workspace Agent 能力边界 + 与 Git 化方式逐项对比（工程细节）** | [workspace-agent-capability-boundary-2026-09.md](workspace-agent-capability-boundary-2026-09.md) |
| **聊天记录能否沉淀 / 谁能看 / Codex 算不算** | [chat-history-capture-2026-09.md](chat-history-capture-2026-09.md) |
| **买 2 个席位怎么分 / 账号与 workspace / 积分池与 5 小时限制** | [business-seat-account-and-usage-2026-09.md](business-seat-account-and-usage-2026-09.md) |
| **「15 条 Pro 消息/月」怎么算 / 个人账号共享 Project 能否替代 Business** | [pro-messages-and-personal-project-sharing-2026-09.md](pro-messages-and-personal-project-sharing-2026-09.md) |
| **离职怎么断权 / SSO 能不能像钉钉那样一键停用 / 域名验证管不管用** | [sso-offboarding-and-domain-2026-09.md](sso-offboarding-and-domain-2026-09.md) |
| **skill 怎么发给运营（GitHub 插件市场）/ 自托管方案对比** | [skill-distribution-and-selfhost-options-2026-09.md](skill-distribution-and-selfhost-options-2026-09.md) |
| **Work 还是 Codex？本地能不能自动跑脚本 / 定时任务** | [work-vs-codex-and-local-automation-2026-09.md](work-vs-codex-and-local-automation-2026-09.md) |
| **运营装不了软件时，纯网页 Workspace Agent 能否每日拉赛狐广告报告（决定性一问）** | [web-only-ad-report-feasibility-2026-09.md](web-only-ad-report-feasibility-2026-09.md) |
| 完整评估（逐章点评 + 项目现状证据） | [assessment.md](assessment.md) |
| 内部底稿（不上会） | [counter-proposal.md](counter-proposal.md) |
| 变更历史 | [log.md](log.md) |

## 本 bundle 与其他文档的关系

| 文档 | 关系 |
|------|------|
| `docs/research/2026-07-24-*`（统一 AI 接入调研 + 独立复审 + PoC 计划） | **上游历史裁决**。当时未评估 ChatGPT Business；其 C′ 门户融合方案现作为 PoC/备用与工程工具参考 |
| [assistant-platform-research-2026-09.md](assistant-platform-research-2026-09.md) | **当前平台复核**。核实 Workspace Agents、Company Knowledge、远程 MCP 与其他企业 Agent 平台，提出「ChatGPT 前台 + Git 真源 + FZH MCP 薄适配层」 |
| [workspace-agent-capability-boundary-2026-09.md](workspace-agent-capability-boundary-2026-09.md) | **同一复核的工程下钻**。回答 R1 点名的五问（创建/编辑形态、上传物与代码执行、工具接入与私网、权限治理、可维护性），逐项给出「留 Git / 放 Workspace」的可执行清单 |
| [work-vs-codex-and-local-automation-2026-09.md](work-vs-codex-and-local-automation-2026-09.md) | **本地优先的广告报告方案**。核实沙箱/网络/定时约束，给出「桌面 App 定时任务跑既有脚本」的架构 |
| [web-only-ad-report-feasibility-2026-09.md](web-only-ad-report-feasibility-2026-09.md) | **本地被排除后的下钻**。逐条核实「公网 MCP server + Workspace Agent + 每日 schedule」在 Business 上是否成立；含最硬的认证约束（平台不认 API key，密钥必须落在自有 MCP server） |
| [chat-history-capture-2026-09.md](chat-history-capture-2026-09.md) | **老板新提诉求的核实**。「聊天记录能否统一沉淀」→ Business 做不到自动收集；给出共享 Project / Plugin-Skill 两条官方替代路径；**含两份官方文档的口径冲突**（须上会前解决） |
| `ai_access_poc/`（壳 #113 + 板 #116 + portal） | **上游**。技术验收已绿，卡在运营审 |
| `docs/non-tech-team-agent-guide.md`、`docs/enterprise-agent-knowledge-system.md` | **上游**。非技术同事用 Agent 的已验证做法 |
| `docs/ai-for-amazon-ops-2026.md` | 2026-06-29 面向运营+管理层的分享稿；含一处与当前实际不符的表述（见 assessment 待核实清单） |

## 交叉验证

本文档的结论使用稳定编号（`C` 结论 / `P` 问题 / `R` 建议）。若另有独立评估（如 Cursor），用编号逐条比对分歧点，**分歧处优先复核证据而非取平均**。
