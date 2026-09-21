---
okf: v0.1
type: Index
title: sellfox_mcp
description: 赛狐官方托管 MCP 的接入参考与只读探测
tags: [sellfox, mcp, index]
timestamp: 2026-09-20
---

# sellfox_mcp

赛狐**官方托管** MCP（`https://api-mcp.sellfox.com/mcp`）的接入参考与**只读**探测。

协议 `2025-06-18`；鉴权走**请求头**、不需要 OAuth。
**23 个工具 = 13 只读 + 1 非破坏性写 + 9 个会改线上广告的写。**

**最容易错的一点**：鉴权有**两条独立通道** —— API 账号凭证（`X-Sellfox-Client-Id`/`Secret`，**当前可用**）
与后台 MCP管理页的 `X-MCP-Key`（**当前 `40027` 未启用**）。混为一谈会得出错误结论。

## 文档

| 你需要... | 读这个 |
|----------|--------|
| 接这个 MCP：端点、两条鉴权路径、23 个工具清单、实测证据、脚本用法 | [reference/official-mcp.md](reference/official-mcp.md) |
| 决策背景：为什么接、结论怎么变的（三版修订轨迹） | [../../docs/research/2026-09-20-sellfox-official-mcp-feasibility.md](../../docs/research/2026-09-20-sellfox-official-mcp-feasibility.md) |

## 脚本

| 做什么 | 命令 |
|--------|------|
| 验凭据 + IP 白名单 | `uv run python sellfox_mcp/scripts/probe_mcp.py --check-token` |
| 列工具（三分类） | `uv run python sellfox_mcp/scripts/probe_mcp.py --list-tools` |
| 调只读工具 | `uv run python sellfox_mcp/scripts/probe_mcp.py --call get_shop_page_list --args '{...}'` |

写工具与白名单外工具**默认拒绝**（退出码 2），需显式 `--allow-write`。
