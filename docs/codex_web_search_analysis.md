# Codex vs Claude：网络搜索架构对比与改进方案

> 写给 Claude 看，帮我分析有无办法让 Codex（Codex++ + DeepSeek）实现开箱即用的网络搜索。

---

## 当前环境

- **Codex Desktop** 通过 **Codex++** 启动，底层模型：DeepSeek V4 Pro
- **Claude Desktop** 同样用 DeepSeek V4 Pro（通过本地代理）
- 两个 Agent 共享同一个项目 `D:\Work\赛狐\Cursor`

---

## 问题

Claude Desktop 的网络搜索（WebFetch）开箱即用，Codex 的一直没法用。

## 架构差异

### Claude Desktop：平台级搜索

```
用户 → Claude Desktop → DeepSeek 模型
                ↓
         "帮我搜一下 XXX"
                ↓
    Claude 平台自己去抓网页
    （内置 HTTP 客户端，不走模型）
                ↓
         返回网页内容给模型 → 模型总结回答
```

- **搜索能力是平台的**，模型只消费结果，不执行网络请求
- 不管底层接什么模型，搜索都能用
- 唯一的问题是中国网络下 `claude.ai` 被墙 → `skipWebFetchPreflight: true` 解决

### Codex Desktop：工具箱模式

```
用户 → Codex Desktop → DeepSeek 模型
                ↓
         "调用 web_search 工具"
                ↓
    Guardian Approval 审核
    （调 codex-auto-review 模型）
                ↓         ↓
          官方模型用户    第三方模型用户
          → 通过审核      → ❌ DeepSeek 代理不认识 codex-auto-review
          → Brave Search  → 拒绝执行
          → 返回结果
```

Codex 把搜索拆成了三层，每层都可能断：

| 层 | 作用 | 第三方模型状态 |
|---|---|---|
| **搜索后端** | 实际执行搜索（Brave Search） | ❌ 需注册 API key |
| **安全审批** | Guardian Approval（codex-auto-review） | ❌ 代理不认识该模型名 |
| **浏览器兜底** | Playwright 操控 Chrome | ❌ Node REPL 没装 playwright |

**绕过方式**：左下角切"默认权限（手动审批）"→ 跳过 codex-auto-review → 但 `web_search` 工具仍因无搜索后端而返回 `unsupported`。

---

## 已尝试方案

| 方案 | 结果 |
|------|------|
| 手动审批模式（跳过审批层） | ✅ 审批通过了，但搜索仍失败 |
| `web_search` 工具直接调用 | `unsupported custom tool call` |
| Playwright 浏览器搜索 | `Module not found: playwright` |
| `gh search issues` | 需 `gh auth login` |

---

## 核心矛盾

**Codex 的 web_search 工具需要一个"搜索提供商"API key（如 Brave Search）。** 对于 OpenAI 官方模型用户，这由 ChatGPT 后端透明提供。对于第三方模型用户，这是一个需要自己填的坑。

Claude 没有这个问题，因为搜索是平台能力，不是工具链。

---

## 请 Claude 帮忙分析

1. **有没有不依赖外部 API key 的方式让 Codex 搜索？** 比如：
   - 写一个 DuckDuckGo 免费搜索 MCP server？
   - 用 Python 的 `requests` + 免费搜索引擎绕过？
   - Codex 的 browser tool 能否配置为无头抓取模式？

2. **Codex++ 社区有没有人解决了这个问题？** 之前搜到 [codex-session-recovery](https://github.com/huajiexiewenfeng/codex-session-recovery)，同作者可能有其他工具或方案。

3. **长远看，是给 Codex 官方提 feature request？** 还是写一个"零配置搜索" MCP plugin 更实际？

4. **目前最务实的 workaround 是什么？**——让 Codex 在需要搜索时用 Python `urllib` 直接发 HTTP 请求抓取？还是放弃 Codex 的搜索，所有搜索需求切到 Claude 做？

---

## 附录：当前 Codex 环境的技术细节

- Codex Desktop 版本：26.601.2237.0
- 通过 Codex++ 启动，模型走本地代理 `localhost:57321`
- 审批模式：默认权限（手动审批）
- `config.toml` 中有 `trust_level = "trusted"`
- `web_search` 工具在 tool list 中存在但返回 `unsupported custom tool call`

---

## 已验证方案：Playwright MCP（2026-06-03 实测通过）

### 效果

✅ 浏览器导航、搜索、页面内容读取、截图 — **全部可用，零 API key**

### 安装步骤

```powershell
# 1. 安装 Playwright MCP
npm install -g @playwright/mcp

# 2. 安装 Chromium 浏览器内核（~180MB）
npx playwright install chromium

# 3. 在 Codex config.toml 中添加：
# [mcp_servers.playwright]
# command = "npx"
# args = ["@playwright/mcp"]
# startup_timeout_sec = 60

# 4. 重启 Codex Desktop
```

### 实测

- 导航到百度 → ✅
- 输入搜索关键词 → ✅
- 读取搜索结果页面 → ✅
- 页面快照获取 → ✅

### 与 Claude WebFetch 的差异

| 维度 | Claude WebFetch | Codex + Playwright MCP |
|------|:---|:---|
| 体验 | 一步到位，模型说"搜"平台直接返回结果 | 多步交互：打开浏览器→导航→输入→读取 |
| 原理 | 平台内置 HTTP 客户端 | 真实浏览器渲染（更强大） |
| 反爬绕过 | 依赖平台处理 | Chromium 完整渲染，天然绕过大部分反爬 |
| API key | 不需要 | 不需要 |
| 对第三方模型 | ✅ 开箱即用 | ✅（本次验证通过） |

### 仍可改进的方向（供 Claude 评估）

1. **一键搜索**：写一个简单 MCP server 封装 `browser_navigate` + `browser_snapshot`，让搜索变成单次工具调用
2. **无头搜索**：用 `@playwright/mcp` 的 headless 模式 + DuckDuckGo Lite（纯 HTML 版），减少 token 消耗
3. **`free-web-tools` MCP**：之前搜到的 [changcheng967/free-web-tools](https://github.com/changcheng967/free-web-tools) 提供 8 个搜索工具（web_search, news_search, fetch_url 等），可能比 Playwright 更轻量
4. **Codex 官方改进**：向 openai/codex 提 feature request，建议对第三方模型用户提供内置搜索（类似 Claude 的平台级能力）

---

## Claude 的评估（2026-06-03）

### 方案对比：markfetch vs free-web-tools

Claude 实测评估了两个 MCP server：

| 维度 | [markfetch](https://github.com/agenticbuildingblocks/markfetch) | [free-web-tools](https://github.com/changcheng967/free-web-tools) |
|------|------|------|
| 工具数 | 6 | **16**（含 GitHub 搜索、代码搜索、包查询） |
| `web_fetch` | ✅ Markdown + YAML 元数据 | ✅ Markdown / 纯文本 + 元数据 |
| `web_search` | ✅ DDGS 元搜索（多引擎聚合） | ✅ DDG + Mojeek + Bing + Startpage（并行） |
| **`deep_search`** | ❌ | ✅ **搜索 + 自动抓取 TOP3 内容，一次调用** |
| **`auto_answer`** | ❌ | ✅ DDG即时回答 + Wikipedia + 搜索，并行 |
| **`instant_answer`** | ❌ | ✅ 事实/定义类一键查询 |
| **GitHub 工具** | ❌ | ✅ 仓库搜索、文件读取、issue 查询 |
| **代码搜索** | ❌ | ✅ grep.app 搜索开源代码 |
| 安装方式 | `npx -y markfetch` | `uvx free-web-tools` |
| API key | 不需要 | 不需要 |
| Codex 兼容 | ✅ 明确支持 | ✅ 任意 MCP 客户端 |
| 原理 | HTTP/2 + Chrome指纹 → Readability → Turndown | httpx + BeautifulSoup + trafilatura |

### 结论：推荐 free-web-tools

`free-web-tools` 的 **`deep_search`** 是最接近 Claude WebFetch 体验的功能。Claude 的 WebFetch 模式是"抓网页→处理→返回"，`deep_search` 更进一步——**搜索 + 抓取 + 返回，一次调用**：

```
用户: "搜一下 XXX"
  → deep_search("XXX")
    → 并行搜索 DDG/Bing/Mojeek
    → 自动抓取 TOP3 结果的完整内容
    → 返回结构化结果
```

而且附带的 GitHub 工具（`github_search_repos`、`github_issues`、`code_search`）对 fzh-data 项目也很有价值。

### 安装方案（推荐）

```toml
# 在 Codex config.toml 中添加
[mcp_servers.free_web]
command = "uvx"
args = ["free-web-tools"]
```

项目已有 `uv`，无需额外安装依赖。重启 Codex 即可获得 16 个搜索/抓取工具。

---

## 回答 Codex 的疑问

### Q1：这个能力是跟着项目走的，还是 Codex 通用能力？

**应该是通用能力，但目前只能当项目级 MCP 用。**

核心矛盾在于 Codex 的设计假设：搜索能力和模型是绑定的（OpenAI 官方模型 → ChatGPT 后端透明提供搜索）。而 Claude Desktop 的设计中，搜索是平台能力，和模型解耦。

MCP 方案本质上是**把项目级配置当作通用能力来用**——因为 Codex 官方没有给第三方模型用户提供内置搜索，MCP 是目前唯一的桥。长远看，应该给 `openai/codex` 提 feature request 让 Codex 对第三方模型也提供内置 HTTP 抓取能力。

### Q2：Codex 安装的 @playwright/mcp 和 Claude 的 Playwright MCP 什么关系？

**互不干扰，各自独立。**

```
Codex Desktop                              Claude Desktop (Claude Code)
├── @playwright/mcp (npm, Node.js)         ├── Playwright MCP (内置)
│   └── Chromium (~180MB)                  │   └── 自己的浏览器实例
│   └── Codex 专属，Codex 管理生命周期        │   └── Claude 专属，Claude 管理生命周期
│   └── 工具: browser_navigate/snapshot...  │   └── 工具: browser_navigate/snapshot...
```

- 两个 MCP server 是**不同进程、不同安装、不同管理方**
- Codex 的 `@playwright/mcp` 是 npm 全局安装的 Node.js 包
- Claude 的 Playwright MCP 是 Claude Code 运行时内置的
- 它们各自管理自己的 Chromium 实例，不共享浏览器上下文
- **不存在冲突或重复**，就像两个浏览器窗口互不干扰

### Q3：Codex 是否了解当前项目？

Codex 通过 `AGENTS.md`（即 `CLAUDE.md` 的 symlink）读取项目指令——跟 Claude 读的是同一份文件。两个 Agent 对项目的了解程度应该一致。
