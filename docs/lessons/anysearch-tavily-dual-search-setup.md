---
okf: v0.1
type: Lesson
title: AnySearch + Tavily — 双搜索平台接入（Claude Desktop / Codex / Claude Code）
description: >
  两个 Agent 专用搜索引擎的完整接入方案。Codex 用户 MCP 开箱即用，
  Claude Desktop 用户因兼容性问题需用 curl 直调 API。
  含 API Key、端点、curl 模板、对比分析、经验教训。
tags: [anysearch, tavily, mcp, search, claude-desktop, codex, api, lesson, onboarding]
timestamp: 2026-07-14
---

# AnySearch + Tavily — 双搜索平台接入

> **一句话**：Codex 用户装完依赖重启即可用；Claude Desktop 用户用 curl 命令直调 API。

---

## 账号与 API Key

| 服务 | 注册地址 | API Key | 免费额度 |
|------|---------|---------|---------|
| **AnySearch** | [anysearch.com](https://anysearch.com/console/api-keys) | `as_sk_afc76f7fea4554ccaa95ca4fe258c2b9` | 1000次/天 |
| **Tavily** | [app.tavily.com](https://app.tavily.com) | `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` | 1000次/月 |


# 方案 A：Codex 用户 — MCP 开箱即用

> `.codex/config.toml` 已预配置好，装完依赖重启即可。

## 安装

```bash
# Tavily（Python 包）
uv pip install mcp-tavily

# AnySearch（无需额外安装，npx mcp-remote 自动下载）
# 首次启动时会自动从 npm 拉取
```

## 验证

重启 Codex（完全退出 → 重新打开），新对话中应能看到：

```
mcp__tavily__tavily_search
mcp__tavily__tavily_extract
mcp__anysearch__search
mcp__anysearch__batch_search
mcp__anysearch__extract
mcp__anysearch__get_sub_domains
```

## Codex 配置详情（`.codex/config.toml`）

### AnySearch
```toml
[mcp_servers.anysearch]
command = "npx"
args = ["-y", "mcp-remote", "https://api.anysearch.com/mcp",
  "--header", "X-Anysearch-Client: mcp/1.0.0",
  "--header", "Authorization: Bearer as_sk_afc76f7fea4554ccaa95ca4fe258c2b9"]
startup_timeout_sec = 60
```

### Tavily
```toml
[mcp_servers.tavily]
command = "uv"
args = ["run", "python", "-m", "mcp_server_tavily"]
startup_timeout_sec = 60

[mcp_servers.tavily.env]
TAVILY_API_KEY = "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"
```


# 方案 B：Claude Desktop 用户 — curl 直调 API

> ⚠️ 当前 Claude Desktop 版本只支持纯 `url` 格式 MCP 配置，无法加载 `command` + `args` 格式的服务器。AnySearch 和 Tavily 都需要认证参数，因此无法通过 `claude_desktop_config.json` 加载。
>
> **替代方案**：在对话中直接用 bash/curl 调用 API，效果完全等同。

## AnySearch 搜索

```bash
curl -s --max-time 20 -X POST "https://api.anysearch.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer as_sk_afc76f7fea4554ccaa95ca4fe258c2b9" \
  -H "X-Anysearch-Client: mcp/1.0.0" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search","arguments":{"query":"<搜索关键词>"}}}' \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['result']['content'][0]['text'])"
```

## AnySearch 批量搜索（最多 5 个并行）

```bash
curl -s --max-time 30 -X POST "https://api.anysearch.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer as_sk_afc76f7fea4554ccaa95ca4fe258c2b9" \
  -H "X-Anysearch-Client: mcp/1.0.0" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"batch_search","arguments":{"queries":["查询1","查询2"]}}}' \
  | python -c "import sys,json; d=json.load(sys.stdin); [print(c['text'][:500]) for c in d['result']['content']]"
```

## AnySearch URL 提取

```bash
curl -s --max-time 20 -X POST "https://api.anysearch.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer as_sk_afc76f7fea4554ccaa95ca4fe258c2b9" \
  -H "X-Anysearch-Client: mcp/1.0.0" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"extract","arguments":{"url":"<目标URL>"}}}' \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['result']['content'][0]['text'])"
```

## Tavily 搜索

```bash
curl -s --max-time 20 "https://api.tavily.com/search" \
  -H "Content-Type: application/json" \
  -d '{"api_key":"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","query":"<搜索关键词>","max_results":5,"search_depth":"basic"}' \
  | python -c "import sys,json; d=json.load(sys.stdin); [print(f'[{r[\"score\"]:.2f}] {r[\"title\"]}\n  {r[\"url\"]}\n  {r[\"content\"][:300]}...\n') for r in d['results']]"
```


# 方案 C：Claude Code CLI 用户

> `.mcp.json` 已配置在 `C:\Users\zhang\.mcp.json`，Claude Code CLI 重启后自动加载。如未生效，用以下 curl 命令。


# 三款搜索对比

| 维度 | AnySearch | Tavily | 内置 WebSearch | free-web-tools |
|------|-----------|--------|---------------|----------------|
| 垂直领域 | 20+（代码/法律/金融/安全等） | 无 | 无 | 无 |
| 中文搜索 | ✅ 优 | ⚠️ 偏英文 | ✅ | ✅ |
| 结构化输出 | Markdown 全文 | 链接+摘要 | 链接+摘要 | 链接+摘要 |
| 延迟 | ~1.6s | ~0.8s | 不定 | 较慢 |
| 意图路由 | ✅ 自动选最优数据源 | 无 | 无 | 无 |
| 国内数据 | ✅ 工商/司法/平台公示 | ❌ 缺失 | ⚠️ 部分 | ⚠️ 部分 |
| 免费额度 | 1000次/天 | 1000次/月 | 无限制 | 无限制 |
| 安装方式 | npx mcp-remote (自动) | uv pip install | 内置 | uv pip install |
| Codex MCP | ✅ 已配置 | ✅ 已配置 | N/A | ✅ 已配置 |
| Claude Desktop MCP | ❌ 不兼容 | ❌ 不兼容 | N/A | ❌ 不兼容 |

## 使用建议

| 场景 | 推荐工具 |
|------|---------|
| 中文内容、国内企业/司法查询 | **AnySearch** |
| 英文技术文档、学术论文 | **Tavily**（更快）或 AnySearch |
| 快速事实核查 | **Tavily**（延迟最低） |
| 需要读整篇网页内容 | **AnySearch extract** |
| 多角度交叉验证 | **AnySearch batch_search**（并行 5 路） |
| 兜底/无需 API Key | **WebSearch**（内置）或 **free-web-tools**（Codex） |


# 服务可用性验证记录

## AnySearch
| 测试项 | 结果 |
|--------|------|
| MCP initialize | ✅ `SentiSearch v1.0.0`, `2025-03-26` |
| tools/list | ✅ `search`, `batch_search`, `extract`, `get_sub_domains` |
| 搜索测试 | ✅ 10 条结果，~1.6s，Markdown 格式 |
| 匿名模式 | ✅ 无需 Key 可用（额度更低）|
| Bearer 认证 | ✅ 正常 |

## Tavily
| 测试项 | 结果 |
|--------|------|
| MCP initialize (remote) | ✅ `https://mcp.tavily.com/mcp/`, `2025-03-26` |
| MCP initialize (local npx) | ✅ `tavily-mcp v0.2.21`, `2025-03-26` |
| API 搜索 | ✅ 0.79s, 5 条结果, 相关性 0.49–0.83 |
| TAVILY_API_KEY 环境变量 | ✅ 正常 |


# Claude Desktop MCP 集成失败记录

配置目标：`C:\Users\zhang\AppData\Roaming\Claude\claude_desktop_config.json`

已尝试的 5 种格式全部失败：

| # | 格式 | 结果 |
|---|------|------|
| 1 | `type: streamable-http` + `headers` | 不出现 |
| 2 | 纯 `url`（匿名 / key 在 URL query） | 不出现（Tavily URL 路径错误） |
| 3 | `url` + `env` / `url` + `auth` | 不出现 |
| 4 | `command: npx` + `mcp-remote` | 不出现 |
| 5 | `command: npx` + `tavily-mcp@latest` + `env` | 不出现 |

**根因**：当前 Claude Desktop 版本**只认纯 `url` 字段**（无任何附加字段），FAC 能工作纯粹因为它不需要认证参数。

**结论**：不要继续尝试 Claude Desktop MCP 集成。最新版 Claude Desktop 可能已修复（参考 [AnySearch 文档](https://www.anysearch.com/docs) 中 Streamable HTTP 方案），升级后重新测试。


# 经验教训

1. **先验证 MCP 本身，再排查客户端**：用 `curl` 直接发 MCP JSON-RPC（initialize → tools/list → tools/call），确认服务端无问题后再排查 Claude Desktop / Codex 的配置格式问题。本次 AnySearch 和 Tavily 的服务端均完全正常。

2. **`url` 格式能工作只是巧合**：FAC 用 `url` 格式成功加载，不代表所有 MCP 都能这样配。它只是因为 FAC 的 OAuth 由 `mcp-remote` 独立处理、不需要在配置里传认证参数。

3. **不同平台配置格式不通用**：
   - **Claude Desktop**: `claude_desktop_config.json`，仅支持纯 `url`
   - **Codex**: `.codex/config.toml`，支持 `command` + `args` + `env`
   - **Claude Code CLI**: `.mcp.json`，支持 `url` / `type: streamable-http` / `command` + `args`

4. **curl 直调 API 是万能的 fallback**：当 MCP 配置不通时，curl + API endpoint 永远可用。文档里写死完整的可执行 curl 命令（含 API Key），接手者无需任何配置。

5. **交接文档写死 API Key**：不要用占位符 `<your-key-here>`。项目团队共享的 Key，文档里写死即可，确保新对话的 Agent 打开文档就能直接用。

6. **AGENTS.md 是自动发现的入口**：新 Agent 启动时必读 AGENTS.md，从这里 → 搜索工具配置文档 → curl 命令，全链路可达。不需要"记住"任何东西。


# 相关链接

- [AnySearch 官网](https://anysearch.com)
- [AnySearch MCP Server GitHub](https://github.com/anysearch-ai/anysearch-mcp-server)
- [AnySearch 文档](https://www.anysearch.com/docs)
- [Tavily 官网](https://tavily.com)
- [Tavily MCP GitHub](https://github.com/tavily-ai/tavily-mcp)
- [FAC MCP 部署指南](../fac-mcp-setup.md)
- [Tavily MCP 踩坑记录（Codex 视角）](tavily-mcp-setup.md)
- [AGENTS.md](../../AGENTS.md) — 项目总纲，新 Agent 入口
