---
okf: v0.1
type: Reference
title: 从 Claude Code CLI 直接调用 Notion MCP —— 复用 Claude-3p 的 OAuth 缓存
date: 2026-10-26
category: developer-experience
module: tooling
problem_type: developer_experience
component: tooling
severity: medium
applies_when:
  - "当前会话的工具列表里没有 notion-personal，但需要读写 Notion"
  - "想用脚本/CLI 批量查 Notion 数据库或改页面属性"
  - "把缓存的 OAuth token 打 Notion REST API 返回 401"
  - "需要确认 Notion MCP 到底配在哪个宿主、凭证缓存在哪"
tags: [notion, mcp, oauth, claude-3p, cli, remote-mcp, cloudflare]
---

# 从 Claude Code CLI 直接调用 Notion MCP

## Context

Notion 的读写在这个仓库里走 **`notion-personal`** 远程 MCP。它不在项目 `.mcp.json`、
也不在 `~/.claude.json`，所以 Claude Code CLI 会话的工具列表里经常看不到它。此前遇到过两种误判：

- 以为「本会话没有 Notion 工具 = 写不了 Notion」，去让用户手动代劳；
- 把 Claude Desktop 缓存里的 OAuth token 直接打 **Notion REST API**（`api.notion.com`），得到 **401**。

实际可行路径是：**直接调用远程 MCP `https://mcp.notion.com/mcp`**，复用 Claude Desktop 3P
已经缓存的 OAuth token。2026-10-26 用这条路径完成了 PB 取消台账两行更新并回读验证。

## Guidance

### 1. 先确认配置与凭证在哪

| 项 | 位置 |
|---|---|
| 3P 模式宿主配置 | `%APPDATA%\Claude-3p\claude_desktop_config.json` |
| 普通模式宿主配置 | `%APPDATA%\Claude\claude_desktop_config.json`（与 3P 是**两个独立文件**） |
| `notion-personal` 条目 | `npx -y mcp-remote https://mcp.notion.com/mcp ...`，`env.MCP_REMOTE_CONFIG_DIR` 指向 OAuth 缓存目录 |
| OAuth 缓存 | `%USERPROFILE%\.mcp-auth-notion-personal\mcp-remote-v1\*_tokens.json` |
| CLI 侧配置 | `claude mcp list` / 项目 `.mcp.json` / `~/.claude.json` —— 通常**没有**它 |

`*_tokens.json` 里是 `access_token` / `refresh_token` / `expires_at`。**不要把 token 写进仓库或日志。**

### 2. 直接调远程 MCP（JSON-RPC over Streamable HTTP）

```text
POST https://mcp.notion.com/mcp
Authorization: Bearer <access_token>
Content-Type: application/json
Accept: application/json, text/event-stream
User-Agent: node
MCP-Protocol-Version: 2025-06-18
```

步骤：

1. `initialize`（`protocolVersion: "2025-06-18"`，`capabilities: {}`，`clientInfo`），
   从响应头取 **`mcp-session-id`**；
2. 发 `notifications/initialized`；
3. 之后每次 `tools/call` 都带 `Mcp-Session-Id`；
4. 响应是 **SSE**：按行取 `data:` 后面的 JSON 再解析。

> **必须设 `User-Agent`**（`node` 即可）。用 Python `urllib` 默认 UA 会被 Cloudflare
> 以 `Error 1010: browser_signature_banned` 拦截，返回 403 —— 此时不是 token 失效。

### 3. 常用工具调用

| 目的 | 工具 | 参数要点 |
|---|---|---|
| 查数据库 | `notion-query-data-sources` | `{"data":{"mode":"sql","data_source_urls":["collection://<id>"],"query":"SELECT * FROM [...] WHERE ..."}}` |
| 改页面属性 | `notion-update-page` | `{"command":"update_properties","page_id":"...","properties":{...}}` |
| 新建页面 | `notion-create-pages` | `data_source_id` + `pages[]` |
| 读页面 | `notion-fetch` | `id` / URL |

属性键名注意：

- 日期属性是 **`date:<列名>:start`** / `:end`；
- select 直接传选项名字符串；
- checkbox 传布尔；
- **富文本换行要用真换行符**，不要写字面量 `\n`（Notion 会把它存成两个字符）；写完回读一次。

### 4. Token 过期与刷新

`expires_at` 是毫秒时间戳。快过期/已过期时：

- 优先让 `npx -y mcp-remote ...` 起一次，它会用 `refresh_token` 自动刷新并回写缓存；
- 或直接走 `https://mcp.notion.com` 的 OAuth token endpoint 刷新（`grant_type=refresh_token`，
  `client_id` 取自同目录 `*_client_info.json`）；
- 任何情况下都不要把 token 提交进仓库。

### 5. 写完必须回读

`notion-update-page` 返回的 `page_id` 只代表请求被接受。用 `notion-query-data-sources`
重新查那几行，确认：值变了、换行是真的换行、没有覆盖掉旧备注。

## Why This Matters

- **CLI/Agent 不必依赖用户手动代劳**：批量台账更新、跨会话收尾都能自动化。
- **REST 401 不是能力缺失**：Notion MCP 的 OAuth token 只对 MCP 端点有效；走对端点就能用。
- **不配 User-Agent 的 403 很容易被误判成 token 失效**，会浪费一轮重新授权。
- **写完不回读**：换行被存成字面量 `\n`、或覆盖旧备注，是这类远端 MCP 最容易静默出错的两处。

## When to Apply

- 当前会话没有 `notion-personal`，但要查/改 Notion。
- 需要在脚本里批量更新 Notion 数据库（本仓库的「PB 无货未发」台账就是典型）。
- 用户说「Notion MCP 在别的对话里一直能用」时 —— 先按本文找配置与缓存，不要直接说不可用。

## Examples

**2026-10-26 PB 取消台账更新**

1. 从 `%USERPROFILE%\.mcp-auth-notion-personal\mcp-remote-v1\*_tokens.json` 取 access token；
2. `initialize` → 拿到 `mcp-session-id`；
3. `notion-query-data-sources` 查 `collection://fa2f272d-...` 中两个 PO，确认当前
   `打单=未打单`、`状态=待到货`、`invoice=不适用`；
4. 对两个 page 各调一次 `notion-update-page`：
   `备注`（追加操作记录）、`状态=顾客取消`、`顾客=取消`、`date:通知Diane:start=2026-10-26`；
5. 再查一次，确认两行字段已变、备注换行正常、旧备注未被覆盖。

## Related

- [../workflow-issues/pb-cancel-request-email-closed-loop.md](../workflow-issues/pb-cancel-request-email-closed-loop.md) —— 本次实际使用场景（PB CANCEL 邮件闭环）
- [cursor-tongtool-mcp-registration.md](cursor-tongtool-mcp-registration.md) —— 另一类「宿主没自动注册 MCP」的问题
- [windows-codex-powershell-utf8.md](windows-codex-powershell-utf8.md) —— Windows 上跑 Node/CLI 的编码约定
