# Codex & Claude：网络搜索 / WebFetch 完全指南

> 让新同事进入项目后，无论用什么 Agent、什么模型，都能第一时间判断如何实现网络访问，不走弯路。
>
> 最后更新：2026-06-03

---

## 快速决策树

```
你用什么 Agent？
│
├─ Claude Desktop
│   └─ 内置 WebFetch，无需配置
│      └─ ⚠️ 中国网络：settings.json 加 "skipWebFetchPreflight": true
│
└─ Codex Desktop
    │
    ├─ OpenAI 官方账号（ChatGPT/API）
    │   └─ web_search 开箱即用，不需要任何配置 ✅
    │
    └─ 第三方模型（Codex++ / DeepSeek 等）
        │
        ├─ 方案 A：Playwright MCP（推荐，通用性最强）
        │   npm install -g @playwright/mcp
        │   npx playwright install chromium
        │   config.toml: [mcp_servers.playwright] command="npx" args=["@playwright/mcp"]
        │
        └─ 方案 B：free-web-tools MCP（搜索+抓取一体）
            pip install git+https://github.com/changcheng967/free-web-tools.git
            config.toml: [mcp_servers.free_web] command="python" args=["-m","mcp_server"]
```

---

## 方案详解

### Claude Desktop

**无需任何安装**。WebFetch 是 Claude 平台内置的 HTTP 客户端能力。

中国网络用户如果遇到 `Unable to verify if domain is safe to fetch`：

```json
// ~/.claude/settings.json
{ "skipWebFetchPreflight": true }
```

### Codex Desktop — OpenAI 官方账号

**无需任何配置**。Codex 内置的 `web_search` 工具直接可用，搜索后端由 ChatGPT 平台透明提供。

### Codex Desktop — 第三方模型（DeepSeek 等）

Codex 官方的 `web_search` 工具依赖两个条件，第三方模型都不满足：
1. **搜索后端**：需要 Brave Search API key
2. **安全审批**：Guardian Approval 调 `codex-auto-review` 模型，第三方代理不认识

**前置步骤**（两个方案都需要）：

> 左下角审批模式 → **"默认权限（手动审批）"**  
> 不要选"自动审批"——否则所有操作都被 `codex-auto-review` 拦截。

#### 方案 A：Playwright MCP（浏览器操控）

优势：完整浏览器，能搜任何网站、填表单、截图、抓取动态内容。

```powershell
npm install -g @playwright/mcp
npx playwright install chromium
```

```toml
# ~/.codex/config.toml
[mcp_servers.playwright]
command = "npx"
args = ["@playwright/mcp"]
startup_timeout_sec = 60
```

#### 方案 B：free-web-tools MCP（搜索抓取一体）

优势：16 个工具，`deep_search` 一步完成"搜索+抓取 TOP3 内容"，最接近 Claude WebFetch 体验。

```bash
pip install git+https://github.com/changcheng967/free-web-tools.git
# 或：uv pip install git+https://github.com/changcheng967/free-web-tools.git
```

```toml
# ~/.codex/config.toml
[mcp_servers.free_web]
command = "python"
args = ["-m", "mcp_server"]
startup_timeout_sec = 60
```

**free-web-tools 工具清单**：

| 工具 | 功能 |
|------|------|
| `deep_search` | 搜索 + 自动抓取 TOP3 完整内容（⭐⭐⭐ 最常用） |
| `web_search` | 多引擎搜索（DDG + Mojeek + Bing + Startpage 并行） |
| `fetch_url` | 抓取任意网页内容，智能路由（GitHub→API，StackExchange→API，arXiv→元数据） |
| `news_search` | 新闻搜索 |
| `instant_answer` | 事实/定义类一键查询 |
| `auto_answer` | 综合回答（即时答案 + Wikipedia + 搜索） |
| `wiki_summary` | Wikipedia 摘要 |
| `wiki_search` | Wikipedia 搜索 |
| `github_search_repos` | GitHub 仓库搜索 |
| `github_repo_info` | GitHub 仓库信息 |
| `github_issues` | GitHub Issue 查询 |
| `github_file_content` | GitHub 文件内容 |
| `code_search` | 代码搜索（grep.app） |
| `book_search` | 图书搜索（Open Library） |
| `package_info` | PyPI/npm/crates.io 包信息 |
| `related_searches` | 相关搜索建议 |

#### 方案 A+B 组合（当前项目配置）

两个 MCP 同时安装，互为补充：
- `free_web`：轻量搜索和抓取（首选，token 消耗低）
- `playwright`：需要浏览器交互时使用（登录、填表、动态页面）

---

## 架构差异：为什么 Claude 更丝滑

| 维度 | Claude Desktop | Codex Desktop（官方） | Codex Desktop（第三方） |
|------|:---|:---|:---|
| 搜索能力 | 平台内置 HTTP 客户端 | ChatGPT 后端透明提供 | 需自建（MCP） |
| 配置复杂度 | 0~1 行 | 0 行 | 3 行 config + 安装 |
| API key | 不需要 | 不需要 | 不需要（MCP 方案） |
| 体验 | 一步到位 | 一步到位 | 多步工具调用 |

**根因**：Claude 把搜索当作**平台能力**（模型提需求，平台去抓），Codex 把搜索当作**工具链**（你自己搭）。对官方用户无感，对第三方用户是门槛。

---

## 已知问题

1. **Guardian Approval 与第三方模型冲突**：`codex-auto-review` 模型名硬编码，第三方代理不认识 → 必须切"手动审批"模式
2. **`web_search` 工具需要搜索后端**：目前仅支持 Brave Search，需要 API key → 未配置时返回 `unsupported`
3. **`uvx free-web-tools` 不可用**：该包未发布到 PyPI → 需 `pip install git+...` 或 `uv pip install git+...`

---

## 相关链接

- [Playwright MCP](https://github.com/microsoft/playwright-mcp)
- [free-web-tools](https://github.com/changcheng967/free-web-tools)
- [Codex 网络搜索踩坑（本项目早期记录）](./codex_web_search_setup.md)
- [Codex 官方文档 — MCP Servers](https://developers.openai.com/codex/codex-manual)
