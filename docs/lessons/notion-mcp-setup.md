---
okf: v0.1
type: Lesson
title: Notion MCP 接入全记录 — 3P 模式配置与「url 字段」断言核查
description: 在 Claude Desktop 3P 模式下接入 Notion 托管 MCP；附对「3P 不支持 url 字段」这一未复验断言的核查结论
tags: [notion, mcp, setup, claude-desktop-3p, mcp-remote, oauth, fact-check]
timestamp: 2026-09-17
---

# Notion MCP 接入全记录 — 3P 模式配置与「url 字段」断言核查

> **阅读对象**：技术开发 + Agent 辅助操作
> **前置条件**：Claude Desktop 3P 模式（外接第三方模型）已可用

---

## 背景

需要在 Notion 里读取和操作任务，但环境中此前没有任何 Notion 接入。本记录包含两部分：

1. Notion MCP 的接入方法（3P 模式）
2. 复查中发现的一条**未复验断言**及其更正

---

## 环境事实（先确认，否则会改错文件）

本环境跑在 **Claude Desktop 3P 模式**（第三方模型，非 Anthropic 官方直连）。可通过环境变量识别：

```
CLAUDE_CODE_ENTRYPOINT=claude-desktop-3p
CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=1
```

**MCP 配置来源**：`Claude-3p\claude_desktop_config.json`。

> ⚠️ 不是 `~/.claude.json`，也不是仓库 `.mcp.json` —— 本环境中后两者的 `mcpServers` 均为空。宿主（Claude Desktop 3P）把自己的 MCP 配置注入给内置的 Claude Code。

配置文件路径：

```
%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude-3p\claude_desktop_config.json
```

（`Claude_*` 是随机串，本机为 `Claude_pzs8sxrjxfjjc`；普通模式对应 `Roaming\Claude\`）

---

## 一、3P 模式下实际生效的 MCP

复查时点了全部三个已装 server，**传输方式全是 stdio（`command` + `args`）**：

| MCP | 配置 | 传输 |
|---|---|---|
| `playwright` | `npx @playwright/mcp@latest` | stdio |
| `fac` | `npx -y mcp-remote <url> --transport http-first` | stdio → 远程 |
| `tavily-mcp` | `npx -y tavily-mcp@0.1.2` + `env.TAVILY_API_KEY` | stdio |

验证方式（比看 UI 可靠）：查 `Roaming\Claude-3p\logs\mcp.log`

```
[info] [playwright] Server started and connected successfully
[info] [fac] Server started and connected successfully
[info] [tavily-mcp] Server started and connected successfully
```

---

## 二、Notion 接入

### 为什么用 `mcp-remote` 而不是 `url` 字段

Notion 托管 MCP（`mcp.notion.com`）**只支持交互式 OAuth**（官方明确：非交互鉴权尚未提供）。`url` 字段是一个不携带授权流程的裸地址，**完成不了 OAuth 授权**。

`mcp-remote` 负责 OAuth 全流程（动态客户端注册 DCR + PKCE + token 缓存），是 Notion 官方文档**明确列出**的桥接方案。

### 配置

在 `Claude-3p\claude_desktop_config.json` 的 `mcpServers` 中新增（**改动前先备份**）：

```json
"notion": {
  "command": "npx",
  "args": ["-y", "mcp-remote", "https://mcp.notion.com/mcp"]
}
```

保留现有 `playwright` / `fac` / `tavily-mcp` / `deploymentMode` / `preferences` 不动。

> 不显式传 `--transport`，用 mcp-remote 默认的 `http-first`。若显式传，**URL 必须在 `--transport` 之前**（见 [fac-mcp-setup.md](../fac-mcp-setup.md) 踩坑）。

### 操作步骤

1. **完全退出** Claude Desktop：系统托盘 → 右键 → **Quit**（不是关窗口）。MCP 不热加载。
2. 重新打开 → 首次启动时 `mcp-remote` **自动弹出浏览器** → Notion 登录 → **选择授权范围** → 授权
   - 建议**只勾目标页面/数据库**，不要全工作区
   - token 缓存到 `~/.mcp-auth/mcp-remote-v1/`
3. 验证：`logs/mcp.log` 出现 `[notion] Server started and connected successfully`
4. **开新对话**（MCP 工具只在对话创建时加载）
5. 用 `notion-fetch` 的 self 标识确认连到的**工作区与用户身份**，再 `notion-search` 检索任务

### 故障排除

| 症状 | 原因 | 解决 |
|---|---|---|
| `notion` 不出现 | 改错了配置文件（改成普通模式的 `Claude\`） | 必须改 `Claude-3p\`；查 `logs/mcp.log` 有无 `[notion]` 行 |
| `Server disconnected` | OAuth 未完成 | 删 `~/.mcp-auth` → 重启重试 |
| `EADDRINUSE` 端口冲突 | mcp-remote 回调端口被占（fac 已用一个） | `taskkill /F /IM node.exe` → 删 `~/.mcp-auth` → 重启 |
| 连接器在但工具不出现 | 当前对话创建时尚未连上 | **开新对话** |
| 浏览器没弹出 | mcp-remote 未能拉起浏览器 | 从日志找 `Please authorize this client by visiting:` 链接手动访问 |
| `notion-search` 返回空 | OAuth 授权范围没覆盖该页面 | 回去补授权，**不是** MCP 配置问题 |

---

## 三、多工作区并存（公司 + 个人）

Notion 托管 MCP **一次 OAuth 只绑定一个工作区**（授权时在工作区选择器里选定）。要同时挂两个工作区、随时切换，用 `MCP_REMOTE_CONFIG_DIR` 给其中一个指定独立凭证目录：

```json
"notion-company": {
  "command": "npx",
  "args": ["-y", "mcp-remote", "https://mcp.notion.com/mcp"]
},
"notion-personal": {
  "command": "npx",
  "args": ["-y", "mcp-remote", "https://mcp.notion.com/mcp"],
  "env": {
    "MCP_REMOTE_CONFIG_DIR": "C:\\Users\\zhang\\.mcp-auth-notion-personal"
  }
}
```

**原理（代码级确认，mcp-remote v0.14.2）**：

```js
const baseConfigDir = process.env.MCP_REMOTE_CONFIG_DIR || path.join(os.homedir(), ".mcp-auth")
```

凭证目录不同 → OAuth 会话与 token 存储完全独立 → 可各自绑定不同工作区。工具前缀分别为 `notion-company-*` 与 `notion-personal-*`。

未改 URL、未加任何 OAuth 参数 —— **不给 Notion 授权服务器发送任何它可能拒绝的东西**，零兼容风险。

### 为什么不用 `--resource` 区分

`mcp-remote` 文档把 `--resource` 列为多会话隔离手段，它也**确实参与 token 缓存 hash**：

```js
function getServerUrlHash(serverUrl, authorizeResource, headers, authorizeParams, clientMetadataUrl, tokenEndpoint)
```

但 Notion 的公开 `oauth-protected-resource` 明确发布：

```json
{"resource":"https://mcp.notion.com","authorization_servers":["https://mcp.notion.com"], ...}
```

即 Notion 对 `resource` 做校验，传非标准值有被 `invalid_target` 拒绝的风险。另有 `--disable-resource-parameter` 用于拒绝该参数的服务器 —— 但那会使隔离失效。**故改用凭证目录隔离。**

### 代价与注意事项

- **上下文开销**：Notion MCP 工具定义很大（实测 `tools/list` 响应约 237KB）。挂两个 = 两套工具常驻上下文。如需压减，可用 mcp-remote 的 `--ignore-tool`（支持 `*` 通配）裁剪工具集
- **回调端口**：两个 entry 的 URL 相同，mcp-remote 回调端口按 URL 派生（`3335`–`49150`），首选值相同；但仅在 OAuth 期间短暂占用，被占会自动往上找端口，正常不冲突
- **加挂新工作区**：再加一个 entry + 再指一个独立 `MCP_REMOTE_CONFIG_DIR` 即可，不动已有条目

### 验证

对每个 Server 分别 `notion-fetch` self，确认两边的 `Workspace ID` / `User email` 确实不同：

| Server | `notion-fetch` self 期望 |
|---|---|
| `notion-company` | 公司工作区（如 `mxdeals1023@gmail.com`） |
| `notion-personal` | 你的个人工作区 |

### 停用某个 Server 但保留配置

Claude Desktop **没有**原生的 per-connector 停用开关（配置里只有 `mcpServers` + `preferences`，无 enable 标志）。通行做法是把条目移到旁边的 `_disabled_mcpServers` 键 —— Claude Desktop 只读 `mcpServers`，不认识的顶层键直接忽略：

```json
{
  "mcpServers": {
    "notion-personal": { ... }
  },
  "_disabled_mcpServers": {
    "notion-company": { ... }
  }
}
```

- **不加载，但配置原样保留**（含全部 args）
- 恢复 = 把条目挪回 `mcpServers` + 重启 Claude Desktop
- 改完**需要重启**才生效（MCP 不热加载）
- OAuth token 不受影响 —— 仍在原凭证目录里，恢复后无需重新授权

**用脚本切**（免手改 JSON，自动备份 + 回读校验）：

```bash
uv run python scripts/mcp_toggle.py                      # 查看状态
uv run python scripts/mcp_toggle.py notion-company off   # 停用（保留配置）
uv run python scripts/mcp_toggle.py notion-company on    # 启用
```

`scripts/mcp_toggle.py` 是通用的，任何 server 都能切；`--normal` 改普通模式配置，`--config <path>` 直接指定文件。

> 这是社区标准做法，`KalinYorgov/mcp-server-manager`、`eversonl/claude-config-manager`、`@wyattjoh/mcp-manager` 三个独立工具用的都是这一招（键名 `_disabled_mcpServers` / `disabledMcpServers`）。

**本项目的用法**：`notion-personal` 常用，常驻 `mcpServers`；`notion-company` 仅测试用，放在 `_disabled_mcpServers` 里备用。

**实测效果**（重启后用 `/context` 验证）：

| | 停用前 | 停用后 |
|---|---|---|
| MCP tools | 57.3k | **39.0k** |
| MCP 工具数 | 168 | **127** |
| Free space | 883.3k | 901.7k (90.2%) |

工具数正好少 41 个（`notion-company` 的全部工具），token 少 18.3k（估算 18.5k），其余 4 个 server 无影响。停用后 `notion-personal` 占 18.6k / 39k（48%）。

---

## 四、更正：「3P 模式不支持 `url` 字段」是未复验断言

### 原始说法

[docs/fac-mcp-setup.md](../fac-mcp-setup.md) 故障排除表原有一行：

> `fac` 不出现 / `not a valid MCP server` → 原因「**3P 模式不支持 `url` 字段**」→ 解决「必须用 `mcp-remote` 桥接，不能直接写 `"url"`」

接入 Notion 时该说法被当作既定事实引用，复查后**不成立为事实**。

### 反证

| 类型 | 证据 |
|---|---|
| **权威文档冲突** | [CONCEPTS.md](../../CONCEPTS.md)「3P 模式」词条 + [tavily-mcp-setup.md](tavily-mcp-setup.md) 踩坑 5 都写「**MCP 服务器的配置格式与普通模式相同**」，唯一区别是**配置文件路径** |
| **元数据缺失** | 该行**无日期、无 app 版本、无复验记录** |
| **日志无佐证** | `logs/main.log` / `main1.log`（覆盖至 2026-09-09）搜 `not a valid` **零命中** |
| **无生效反例** | 3P 配置中三个生效 MCP **全是 stdio**；`url` 类型从未真正放进 3P 配置测试过 |

### 更可能的真实原因

`fac` 的 endpoint（`ensh.vilavi.cn`）**需要 OAuth 2.0**，而 `url` 字段是裸地址、不携带授权流程。失败原因很可能是「**该 endpoint 要 OAuth**」，被记成了「3P 不支持 `url`」。

这与项目已记录的 **PR #84 误诊**属同一类 —— 详见 [tavily-mcp-setup.md](tavily-mcp-setup.md) 踩坑 5「元教训：反复犯同样低级错误的原因」。

### 已做处理

- 修正 `docs/fac-mcp-setup.md` 故障排除表该行，并补「更正说明」小节
- 结论：**3P 是否支持 `url` 未被验证。** 对需要 OAuth 的 endpoint（fac、Notion）而言，`mcp-remote` 是必需且已被长期验证的路径

### 可选：一次性查实

往 3P 配置放一个**不需要 OAuth** 的远程 MCP（带 `"url"`），重启后看 `logs/mcp.log`：

- 出现 `connected successfully` → 原断言是误诊，应删除
- 出现 `not a valid MCP server` → 断言成立，应补上日期与 app 版本

---

## 五、上下文开销实测与减压结论

### 实测 ground truth（`/context`）

168 个 MCP 工具 = **57.3k token**，占 1M 上下文 **5.7%**：

| Server | 工具数 | token | 占比 |
|---|---|---|---|
| `notion-company` | 41 | ~18.5k | 32% |
| `notion-personal` | 41 | ~18.5k | 32% |
| `Claude_in_Chrome` | 24 | ~7.0k | 12% |
| `playwright` | 26 | ~4.4k | 8% |
| `fac` | 17 | ~4.0k | 7% |
| `Claude_Preview` | 13 | ~2.1k | 4% |
| `scheduled-tasks` / `ccd_*` / `tavily-mcp` | 7 | ~3.2k | 5% |

**两个 Notion 站合计 37k = 1M 上下文的 3.7%** —— 不构成问题，且 free space 仍有 88%。

### ⚠️ 方法论教训：`tools/list` 的 JSON 字节数 ≠ 上下文 token 数

排查时曾用原始 `tools/list` JSON 的字节数排序，得出「`notion-query-data-sources` 占 77.8KB 是大头」的结论 —— **完全错误**。两者排序对不上：

| 工具 | 原始 JSON | 实际 token | 名次变化 |
|---|---|---|---|
| `notion-query-data-sources` | 77.8 KB（第 1） | **630**（跌出前十） | ↓↓↓ |
| `notion-update-page` | 15.7 KB（第 4） | **1.8k**（第 1） | ↑ |
| `notion-create-pages` | 13.9 KB（第 5） | 1.5k（第 2） | ↑ |
| `notion-search` | 6.3 KB（第 9） | 1.3k（第 3） | ↑ |

原因：原始 JSON 里每个参数都带完整 JSON Schema，而模型实际收到的是**精简渲染版**。单站 232 KB 原始 JSON 换算成上下文只有 **~18.5k token**（约 6 倍差距）。

> **铁律**：判断 MCP 上下文开销，用 `/context` 的实测 token，**不要用 `tools/list` 的字节数换算**。

### Tool Search 在本环境不可用（已 A/B 验证）

Claude Code v2.1.7+ 的 MCP Tool Search（按需加载工具 schema，官方称省 85%）在 `ANTHROPIC_BASE_URL` 指向非官方主机时**默认关闭**，且是**客户端侧判断**（请求还没发到代理就决定了，代理 header 改不回来）。v2.1.72 起可通过 `ENABLE_TOOL_SEARCH` 强制启用。

**本环境实测无效**：

| `ENABLE_TOOL_SEARCH` | MCP tools |
|---|---|
| `true` | 57.3k / 168 |
| `false` | 57.3k / 168 |

两次完全一致 → 被 `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` 挡住（该变量大概率是刻意设的，DeepSeek 代理 `api.vilavi.cn` 可能不支持 beta header）。**不建议为它去动这个变量** —— 收益仅 ~4.8%（57.3k 的 85%），风险是会话起不来。

### 结论

- **不做进一步减压**。37k / 1M = 3.7%，加上缓存按 ~10% 计价，钱和窗口都不构成问题
- 保留 `--ignore-tool` 裁掉计划不可用的 3 个工具（`notion-ai-search` / `notion-query-meeting-notes` / `notion-query-multiple-data-sources`），约省 1.4k/站，纯赚（本来调用就会失败）
- 若将来移到官方 `api.anthropic.com` 或去掉 `DISABLE_EXPERIMENTAL_BETAS`，可重新评估 Tool Search

---

## 相关文档

- [docs/fac-mcp-setup.md](../fac-mcp-setup.md) — FAC MCP 部署（3P 路径 + mcp-remote 桥接 + 本次更正）
- [docs/lessons/tavily-mcp-setup.md](tavily-mcp-setup.md) — Tavily MCP 踩坑（3P 路径陷阱 + PR #84 误诊复盘）
- [CONCEPTS.md](../../CONCEPTS.md) — 「3P 模式」词条
- [docs/solutions/workflow-issues/search-first-before-implementing.md](../solutions/workflow-issues/search-first-before-implementing.md) — 「先搜再造」铁律

## 原始链接

- [Connect to Notion MCP — Notion Docs](https://developers.notion.com/guides/mcp/get-started-with-mcp) — 官方配置步骤 + mcp-remote 桥接推荐
- [anthropics/claude-code#52961 — Notion MCP OAuth fails with "Invalid redirect_uri for OAuth client"](https://github.com/anthropics/claude-code/issues/52961) — 已 CLOSED；2026-04-27 有用户确认修复后可正常认证。该 bug 仅影响 Claude Code 内置远程 MCP 客户端，**`mcp-remote` 路径不受影响**
- [mcp-remote GitHub](https://github.com/geelen/mcp-remote)
