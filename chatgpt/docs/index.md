---
okf: v0.1
type: Index
title: chatgpt
description: ChatGPT 作为 Agent 宿主的接入知识 — 自定义连接器接 MCP 服务器
timestamp: 2026-09-20
---

# chatgpt

把 ChatGPT（网页版自定义连接器 / 智能体应用）接到我们自己的 MCP 服务器上。

**与 Claude Desktop 的根本差异**：ChatGPT 是 **OpenAI 服务端直连** MCP endpoint，本机不起任何进程。
所以 Claude 侧的 `mcp-remote` 桥接、`~/.mcp-auth` token 缓存、端口冲突那套排错**全部不适用**。

身份验证**只能走 OAuth**。已接入：[FAC（ERPNext 测试站）](reference/fac-mcp-oauth-connect.md)。

## 文档

| 你需要... | 读这个 |
|----------|--------|
| 知道 ChatGPT 连接器对 MCP 服务器有什么硬性要求（换任何服务器都先看这篇） | [reference/connector-requirements.md](reference/connector-requirements.md) |
| 把 FAC / ERPNext 接到 ChatGPT：表单填什么、哪些已实测、报错怎么定位 | [reference/fac-mcp-oauth-connect.md](reference/fac-mcp-oauth-connect.md) |

## 前置（ChatGPT 侧）

- 付费档位 —— 自定义 MCP 不对免费用户开放
- **开发者模式**（设置 → 应用和连接器 → 高级设置）
