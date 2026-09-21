---
okf: v0.1
type: Index
title: nas_mcp
description: 只读把群晖 NAS 暴露给 MCP 客户端（含 ChatGPT）
tags: [nas, synology, mcp, index]
timestamp: 2026-09-21
---

# nas_mcp

把公司群晖 NAS **只读**暴露给 MCP 客户端（Claude / Cursor / **ChatGPT 连接器**）。

**只读、路径锁死在 `NAS_ROOT_FOLDER`、Bearer 鉴权（已在 ChatGPT 实测可用）。**
**没有创建/移动/删除能力 —— 这是刻意设计。**

## 文档

| 你需要... | 读这个 |
|----------|--------|
| 概览、三条硬安全约束、本地怎么跑 | [../README.md](../README.md) |
| 部署到上海 VPS：Docker、nginx 反代、外部验证、接 ChatGPT | [reference/deploy.md](reference/deploy.md) |
| 为什么部署在 VPS 而不是 NAS、为什么自建而不是用第三方 | [../../docs/research/2026-09-21-nas-mcp-chatgpt-feasibility.md](../../docs/research/2026-09-21-nas-mcp-chatgpt-feasibility.md) |

## 工具（只读）

`nas_health` / `nas_list_folder` / `nas_file_info` / `nas_read_text`
