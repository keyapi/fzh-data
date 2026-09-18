---
okf: v0.1
type: Log
title: 经验教训变更日志
description: docs/lessons 目录变更历史
tags: [lessons, log]
---

# 变更日志

## 2026-09-18

- **更新**: [notion-mcp-setup.md](notion-mcp-setup.md) — 新增「三、多工作区并存」小节。Notion 托管 MCP 一次 OAuth 只绑定一个工作区；用 `MCP_REMOTE_CONFIG_DIR` 给其中一个 Server 指独立凭证目录即可并存多个工作区。代码级依据（mcp-remote v0.14.2）：`const baseConfigDir = process.env.MCP_REMOTE_CONFIG_DIR || path.join(os.homedir(), ".mcp-auth")`。**未给 Notion 授权服务器发送任何额外参数，零兼容风险。**
- **排除**: 不用 `--resource` 做区分。它虽参与 token 缓存 hash（`getServerUrlHash(serverUrl, authorizeResource, headers, authorizeParams, clientMetadataUrl, tokenEndpoint)`），但 Notion 的 `oauth-protected-resource` 明确发布 `{"resource":"https://mcp.notion.com"}` 并对其校验，传非标准值有 `invalid_target` 风险。
- **落地**: 3P 配置 `mcpServers` 现为 `playwright` / `fac` / `tavily-mcp` / `notion-company` / `notion-personal`；`notion-company` 复用已有 token（免重新授权），`notion-personal` 走独立凭证目录需首次 OAuth。
- **实测记录**: 首次授权（2026-09-18 08:57）连通 `Notion MCP v1.2.0`，工作区为 `mxdeals1023@gmail.com` 名下新建工作区，其内容仅 Notion 模板示例数据（「你的第一个项目」「你的第一个文档」等）。免费版限制：`ai_search` / `query_meeting_notes` 需 Business，`query_multiple_data_sources` 需 full version；`search` / `fetch` / `create_pages` / `update_page` 均可用。

## 2026-09-17

- **新增**: [notion-mcp-setup.md](notion-mcp-setup.md) — Notion 托管 MCP 在 Claude Desktop 3P 模式的接入记录。要点：① 本环境 MCP 配置来源是 `Claude-3p\claude_desktop_config.json`（非 `~/.claude.json`、非仓库 `.mcp.json`，后两者 `mcpServers` 均为空）；② 生效的三个 MCP（playwright/fac/tavily-mcp）**全是 stdio**，`url` 类型从未在 3P 配置里测试过；③ Notion 托管 MCP 只支持交互式 OAuth，裸 `url` 完成不了授权流程，故必须走 `mcp-remote` → 配置 `{"command":"npx","args":["-y","mcp-remote","https://mcp.notion.com/mcp"]}`。
- **更正**: [../fac-mcp-setup.md](../fac-mcp-setup.md) 故障排除表原记「3P 模式不支持 `url` 字段」，经复查**降级为未验证断言**并补「更正说明」小节。反证：`CONCEPTS.md`「3P 模式」词条与 [tavily-mcp-setup.md](tavily-mcp-setup.md) 踩坑 5 均写「配置格式与普通模式相同，唯一区别是路径」；该行无日期无版本；`logs/main.log`/`main1.log` 搜 `not a valid` 零命中。更可能的真实原因是 fac endpoint 需要 OAuth 而裸 `url` 不携带授权流程 —— 与 PR #84 误诊同类（见 tavily 踩坑 5）。
- **背景**: 该断言在接入 Notion 时曾被当作既定事实引用，经用户要求全量核查所有已装 MCP 配置与踩坑记录后发现矛盾。
