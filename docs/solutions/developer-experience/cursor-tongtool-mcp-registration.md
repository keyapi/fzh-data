---
title: "Cursor 通途 MCP 不会自动出现，必须写用户级 mcp.json"
date: 2026-08-14
category: developer-experience
module: tongtool_api
problem_type: developer_experience
component: tooling
severity: high
applies_when:
  - "在 Cursor 里查通途 SKU / 订单 / 仓库，工具目录没有 tongtool"
  - "用户说给 Cursor 安装通途 MCP、Cursor 没有 tongtool MCP"
  - "Agent 想触发 Cursor 的 MCP 安装提示"
tags:
  - cursor
  - mcp
  - tongtool
  - erp2
  - setup
---

# Cursor 通途 MCP 不会自动出现，必须写用户级 mcp.json

## Context

通途官方 MCP 是自定义远程 HTTP（`https://mcp.tongtool.com/mcp` + `x-tongtool-*` 头），不在 Cursor Marketplace，Agent 也没有「弹出安装 MCP」的工具。此前 skill / `mcp-setup.md` / AGENTS.md 只写了 Codex：`setup_codex_mcp.ps1` → `~/.codex/config.toml`。Cursor 侧被写成「后续独立 PR」，Agent 就改走 `mcp_http.py`，从不安装。

仓库 `.cursor/` 整目录 gitignore，clone 不会带上项目级 `mcp.json`。这不是漏写一行配置，而是 Cursor 宿主根本收不到 git 里的 MCP 注册。

## Guidance

1. 先看当前会话工具目录是否已有 `user-tongtool_erp2_primary`（或 `erp2_product_goodsquery`）。有则直接 `CallMcpTool`，不要再用 HTTP 客户端重复打一枪（同一商户 5 次/分钟）。
2. 没有：告诉用户「Cursor 不会从 clone 自动装通途 MCP，也没有可点的安装提示」，然后运行：

```text
uv run python tongtool_api/setup_cursor_mcp.py
```

脚本读 `tongtool_api/.env`，合并写入 `%USERPROFILE%\.cursor\mcp.json`（Linux/macOS：`~/.cursor/mcp.json`），不把密钥打进终端。
3. 本机 2026-08-14 实测：写入后**同一会话**即可 `ready`。若未出现：Cursor **Customize → MCP** 打开 `tongtool_erp2_primary`，重载窗口或开新对话。
4. Cursor 工具名带 `user-` 前缀：`user-tongtool_erp2_primary`。Codex 仍是 `tongtool_erp2_primary`。
5. 日常只启用 **primary**。同一 URL 的 secondary 写入 mcp.json 后，本会话 Available servers 里没有出现；不要为加载它再打 ERP2 业务调用。
6. CLI / pytest 继续用 `tongtool_api/mcp_http.py`。只有 Agent 对话里的工具目录缺失时才需要安装步骤；安装前不要假装 MCP 已接通。

## Why This Matters

- 没有「安装提示」可触发。Agent 只能写用户级配置，再核对工具目录。
- 只写 Codex 安装路径时，Cursor 会话会永久 HTTP 回退，用户会以为 MCP 坏了。
- 密钥必须留在 `.env` 和用户主目录配置里，不能进 git。

## When to Apply

- 新机器或新同事用 Cursor 查通途
- 工具目录只有 `cursor-app-control` / `cursor-ide-browser` 等内置项
- 用户明确说「给 Cursor 安装通途 MCP」

## Examples

2026-08-14 本机：`setup_cursor_mcp.py` 注册 2 个 server 后，`user-tongtool_erp2_primary` 状态 `ready`。对 `BNFBAvelvetgray60` 调 `erp2_product_goodsquery`（`productType=0`）返回业务码 200，SKU 命中。证据见 [research](../../../tongtool_api/docs/research/2026-08-14-cursor-mcp-install.md)。

## Related

- [Tongtool MCP Setup](../../../tongtool_api/docs/reference/mcp-setup.md)
- [Tongtool ERP2 MCP 共享限流](../integration-issues/tongtool-erp2-mcp-shared-rate-limit.md)
