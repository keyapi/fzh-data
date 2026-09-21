---
okf: v0.1
type: Guide
title: chatgpt — ChatGPT 作为 Agent 宿主的接入知识
description: 把 ChatGPT（网页版自定义连接器 / 智能体应用）接到自己的 MCP 服务器上；含 FAC（ERPNext）实测记录与通用要求
timestamp: 2026-09-20
---

# chatgpt

记录 **ChatGPT 当 Agent 宿主**这条线：把 ChatGPT 接到我们自己的 MCP 服务器上。

与 `docs/mcp-setup.md` 里 Claude Desktop / Codex / Cursor 那三家的接入方式**根因不同**，不能照搬：
ChatGPT 是 **OpenAI 服务端直连**你的 MCP endpoint，**本机不起任何进程**。

## 一句话

ChatGPT 自定义连接器的身份验证**只能走 OAuth**。选「访问令牌/API 密钥」那条路对 FAC 无效
（FAC 只有 OAuth 2.0+PKCE，没有静态 token 方案），选「无身份验证」会直接 401。

## 当前接入

| MCP 服务器 | 状态 | 文档 |
|---|---|---|
| FAC（ERPNext `ensh.vilavi.cn` 测试站） | 服务端能力已实测通过；ChatGPT 侧端到端待人工点授权 | [docs/reference/fac-mcp-oauth-connect.md](docs/reference/fac-mcp-oauth-connect.md) |

## 前置

- ChatGPT **付费档位** —— 自定义 MCP 不对免费用户开放
- ChatGPT **开发者模式**（设置 → 应用和连接器 → 高级设置）
- 目标 MCP 服务器**公网可达**（ChatGPT 从 OpenAI 侧发起，没有本地回环可用）

## 非目标

- 不记录 Codex Desktop —— 那是另一条线，见 `docs/ai-agent-desktop-comparison.md` / `docs/codex_vs_claude_comparison.md`
- 不记录 ChatGPT 订阅档位/额度的运营口径 —— 见 `docs/solutions/integration-issues/chatgpt-edu-cliproxyapi-429-rate-limit.md`
- 不把 ChatGPT 当模型供应商（我们的模型接入见 `CONCEPTS.md` 与 `docs/research/2026-07-24-fzh-unified-ai-access-research.md`）

## 目录

- [docs/index.md](docs/index.md) — OKF 文档索引
- [docs/reference/connector-requirements.md](docs/reference/connector-requirements.md) — ChatGPT 连接器对 MCP 服务器的硬性要求（通用，换服务器也看这篇）
- [AGENT_HANDOFF.md](AGENT_HANDOFF.md) — Agent 交接
