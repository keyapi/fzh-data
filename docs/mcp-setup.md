---
okf: v0.1
type: Reference
title: MCP 选型与安装指南
description: 各宿主（Claude Desktop 3P / Codex / Cursor）的 MCP 安装、启停、裁剪与排错；按需选装，不必全装
tags: [mcp, setup, claude-desktop, codex, cursor, 3p, onboarding]
timestamp: 2026-09-18
---

# MCP 选型与安装指南

> **你不需要装全部 MCP。** 按手头的任务选装 —— MCP 的工具定义**每轮对话常驻上下文**，装了不用是纯亏。

---

## 一、先选：我需要哪个？

| MCP | 干什么 | 需要凭证 | 谁该装 |
|---|---|---|---|
| **Tavily**（推荐） | AI 优化网页搜索，1000 次/月免费 | 自己的 Key（[app.tavily.com](https://app.tavily.com/home) 注册） | 几乎所有人 |
| **free-web-tools** | 网页搜索，免费无需 Key（质量次于 Tavily） | 无 | 不想注册 Key 的同事 |
| **Playwright** | 浏览器自动化（通途 / 赛狐网页操作） | 无 | 做网页自动化才装 |
| **通途 ERP2** | 查通途 SKU / 订单 / 仓库 | `tongtool_api/.env` | 做通途相关才装 |
| **FAC（ERPNext）** | 查改 ERPNext 数据、报表、工作流 | OAuth 账号 | 做 ERPNext 相关才装。⚠️ **仅测试环境** `ensh.vilavi.cn` |
| **Notion** | 读写 Notion 页面 / 数据库 | OAuth | 用 Notion 记事的同事 |

### 成本提醒（实测）

- **单 server 工具定义常驻上下文**：Notion 41 个工具 ≈ **18.6k token**
- **工具过多会降低准确率**：生态实测 12 个工具时首次调用正确率 92%，**61 个工具掉到 61%**
- 所以：**装你真正要用的**；用不上的用下面的「启停与裁剪」关掉

---

## 二、宿主差异（先确认你在哪个宿主下）

| 宿主 | 配置文件 | 改完怎么生效 |
|---|---|---|
| **Claude Desktop · 3P 模式** | `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude-3p\claude_desktop_config.json` | **托盘右键 → Quit 完全退出**，再打开 |
| Claude Desktop · 普通模式 | 同上，把 `Claude-3p\` 换成 `Claude\` | 同上 |
| **Codex** | `~/.codex/config.toml` | 完全退出再打开 |
| **Cursor** | `~/.cursor/mcp.json`（仓库 `.cursor/` 已 gitignore，clone 不带） | Customize → MCP 启用；未出现则重载窗口 |

> ⚠️ **最常见的坑**：Claude Desktop 的 3P 模式与普通模式是**两个独立文件**。
> 改错文件会**静默无效** —— 没有任何报错，只是不生效。

---

## 三、3P 模式的通用事实

> 本节是各 server 文档的**共同来源**。其他文档请引用本节，不要再各写一遍（重复会导致互相矛盾）。

### 远程 MCP 要走 `mcp-remote` 桥接

需要 OAuth 的远程 MCP（FAC、Notion 等）**不能只写 `url` 字段** —— `url` 是裸地址，不带授权流程，连不上。

```json
"<名字>": {
  "command": "npx",
  "args": ["-y", "mcp-remote", "<MCP URL>"]
}
```

- 参数顺序：显式传 `--transport` 时，**URL 必须在它之前**
- OAuth token 缓存在 `~/.mcp-auth/`（`mcp-remote-v1/` 子目录，跨版本共享）
- 同一 URL 要挂**多个账号/工作区**时，用 `MCP_REMOTE_CONFIG_DIR` 环境变量给其中一个指独立凭证目录

### 启停与裁剪

```bash
uv run python scripts/mcp_toggle.py              # 看当前状态
uv run python scripts/mcp_toggle.py <name> off   # 停用（保留配置，不删除）
uv run python scripts/mcp_toggle.py <name> on    # 启用
```

- 停用只是把条目移到 `_disabled_mcpServers`，**配置完整保留**；恢复后**无需重新授权**（token 不受影响）
- 改完**必须重启宿主**才生效

**裁工具省上下文**：在 `args` 里加 `--ignore-tool <工具名>`（可重复，支持 `*` 通配）。
计划里本来就用不了的工具建议直接裁掉（例：Notion 免费版的 `notion-ai-search` / `notion-query-meeting-notes`）。

---

## 四、安装命令

```bash
# Tavily（需先注册拿 Key）
uv pip install mcp-tavily
#   → Key 写进宿主配置的环境变量（Codex: .codex/config.toml；Claude Desktop: env.TAVILY_API_KEY）

# free-web-tools（免费）
uv pip install git+https://github.com/changcheng967/free-web-tools.git

# Playwright
npm install -g @playwright/mcp && npx playwright install chromium

# 通途 ERP2（填 tongtool_api/.env 后按宿主分别注册）
#   Codex:  powershell -File tongtool_api/setup_codex_mcp.ps1
#   Cursor: uv run python tongtool_api/setup_cursor_mcp.py
```

> **不要用全局 `pip`** —— 包必须装进项目 `.venv`（用 `uv pip install`）。

---

## 五、排错

| 症状 | 原因 | 解决 |
|---|---|---|
| 改了配置没反应 | 改错文件（3P vs 普通），或没完全退出 | 确认路径；**托盘 Quit** 再开 |
| `not a valid MCP server` / server 不出现 | 远程 MCP 没走 `mcp-remote` | 见 §三 |
| `Server disconnected` | OAuth 未完成 | 删 `~/.mcp-auth` → 重启重试 |
| `EADDRINUSE` | mcp-remote 回调端口冲突 | `taskkill /F /IM node.exe` → 删 `~/.mcp-auth` → 重启 |
| 连接器在，但工具列不出来 | MCP 工具**只在会话创建时**加载 | **开新对话** |
| 浏览器没弹 | mcp-remote 没拉起浏览器 | 日志里找 `Please authorize this client by visiting:` 链接手动访问 |
| 搜索/查询返回空 | OAuth 授权范围没覆盖该页面 | 回去补授权，**不是** MCP 配置问题 |

---

## 六、各 MCP 详细文档

| MCP | 详细文档 |
|---|---|
| Notion | [docs/lessons/notion-mcp-setup.md](lessons/notion-mcp-setup.md) — 含双工作区并存、上下文开销实测、两处已更正的错误结论 |
| Tavily | [docs/lessons/tavily-mcp-setup.md](lessons/tavily-mcp-setup.md) — 含 3P 路径陷阱与 PR #84 误诊复盘 |
| FAC（ERPNext） | [docs/fac-mcp-setup.md](fac-mcp-setup.md) |
| 通途 ERP2 | [tongtool_api/docs/reference/mcp-setup.md](../tongtool_api/docs/reference/mcp-setup.md)；Cursor 注册见 [solutions/developer-experience/cursor-tongtool-mcp-registration.md](solutions/developer-experience/cursor-tongtool-mcp-registration.md)；限流结论见 [solutions/integration-issues/tongtool-erp2-mcp-shared-rate-limit.md](solutions/integration-issues/tongtool-erp2-mcp-shared-rate-limit.md) |

### 相关经验教训

- [「先搜再造」](solutions/workflow-issues/search-first-before-implementing.md) — 配 MCP 前必须先查官方文档 + 项目文档。本项目已两次因此踩坑（PR #84 误诊、「3P 不支持 url」未复验断言）
- [docs/solutions/documentation-gaps/unverified-external-api-claims-in-docs.md](solutions/documentation-gaps/unverified-external-api-claims-in-docs.md) — 文档里的外部 API 断言必须标注验证状态
