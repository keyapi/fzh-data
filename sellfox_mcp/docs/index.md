---
okf: v0.1
type: Index
title: sellfox_mcp
description: 赛狐官方托管 MCP 的接入参考与探测（新协议：sf_discover/sf_describe/sf_execute）
tags: [sellfox, mcp, index]
timestamp: 2026-11-24
---

# sellfox_mcp

赛狐**官方托管** MCP（`https://api-mcp.sellfox.com/mcp`）的接入参考与探测。

协议 `2025-06-18`、**无状态**、鉴权走请求头。
**3 个元工具 + 371 个业务工具**（发现目录；读约 317 / 写约 54）。

**最容易错的一点**：鉴权有**两条独立通道** —— 子账号 `X-MCP-Key`（**2026-11 起已开通，推荐**）
与 API 账号 `X-Sellfox-Client-Id`/`Secret`（可用）。两条都通到同一端点，不是二选一。

## 文档

| 你需要... | 读这个 |
|----------|--------|
| 端点、鉴权、工具面、调用链、契约分片、坑、能力矩阵、写干探测 | [reference/official-mcp.md](reference/official-mcp.md) |
| 决策背景（9 月：为什么接、当时为何只探测） | [../../docs/research/2026-09-20-sellfox-official-mcp-feasibility.md](../../docs/research/2026-09-20-sellfox-official-mcp-feasibility.md) |

## 脚本

| 做什么 | 命令 |
|--------|------|
| 验 API 账号凭据 + IP 白名单 | `uv run python sellfox_mcp/scripts/probe_mcp.py --check-token` |
| 列 3 个元工具 | `uv run python sellfox_mcp/scripts/probe_mcp.py --list-tools --auth mcp-key` |
| 翻业务工具目录（371） | `uv run python sellfox_mcp/scripts/probe_mcp.py --catalog --auth mcp-key` |
| 按问句发现 tool_id | `uv run python sellfox_mcp/scripts/probe_mcp.py --discover "查询亚马逊利润报表" --operation read` |
| 取契约 | `uv run python sellfox_mcp/scripts/probe_mcp.py --describe get_shop_page_list` |
| 只读冒烟 | `uv run python sellfox_mcp/scripts/probe_mcp.py --smoke-reads` |
| 写能力干探测（零变更） | `uv run python sellfox_mcp/scripts/probe_mcp.py --probe-writes` |

`--execute` 对写工具（`edit_*`/`create_*`/`save_*`/`update_*`…）**默认拒绝**（退出码 2），需显式 `--allow-write`。
