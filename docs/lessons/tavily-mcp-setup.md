---
okf: v0.1
type: Lesson
title: Tavily MCP 接入全记录 — 踩坑与修复
description: 从代码错误到成功配置 Tavily MCP 的经验教训，供非技术同事 clone 项目后顺利安装参考
tags: [tavily, mcp, setup, onboarding, bugfix]
timestamp: 2026-06-29
---

# Tavily MCP 接入全记录 — 踩坑与修复

> **阅读对象**：技术开发 + 非技术同事（Agent 辅助操作）
> **前置条件**：已按 [AGENTS.md](../../AGENTS.md) 完成 clone 后的基础环境搭建

---

## 背景

为提升 Codex 的网页搜索质量，从免费 `free-web-tools`（基于 DuckDuckGo）升级到专为 AI Agent 优化的 Tavily 搜索引擎。
- Tavily 提供合成回答、内容提取、网页爬取等能力
- 1000 次/月免费额度，注册方式：[app.tavily.com](https://app.tavily.com)
- 官方 MCP server: `mcp-tavily` (pip) 或 `tavily-mcp` (npx)

---

## 踩坑 1：用全局 pip 安装包 = 项目找不到模块

### 错误做法

```powershell
pip install mcp-tavily
```

包被装到了全局 Python / conda 环境（`C:\Users\zhang\anaconda3\lib\site-packages`），而项目用的是 `uv` 管理的 venv。

### 现象
Codex 启动 MCP server 时报告 `ModuleNotFoundError: No module named 'mcp_server_tavily'`。

### 正确做法

```powershell
uv pip install mcp-tavily
```

> **铁律**：本项目所有 Python 包必须通过 `uv pip install` 或 `uv add` 安装到项目 venv。绝对不要用全局 `pip`。

---

## 踩坑 2：`.codex/config.toml` 里硬编码 `python` 路径

### 错误做法

```toml
[mcp_servers.tavily]
command = "python"
args = ["-m", "mcp_server_tavily"]
```

`python` 指向的是环境变量 PATH 里找到的第一个 Python，在不同机器/用户上结果不同（可能是 conda、系统 Python、或根本没有）。

### 现象
A 机器能跑，B 机器 `python` 找不到项目 venv 里的包 → Codex 启动失败。

### 正确做法

```toml
[mcp_servers.tavily]
command = "uv"
args = ["run", "python", "-m", "mcp_server_tavily"]
```

`uv run python` 确保使用项目 venv 的 Python，与 clone 路径无关。

> **铁律**：`.codex/config.toml` 中所有 MCP server 的 Python 命令必须以 `"uv"` + `"run"` 启动。

---

## 踩坑 3：API Key 硬编码在 `.codex/config.toml` 中

### 错误做法

```toml
[mcp_servers.tavily.env]
TAVILY_API_KEY = "tvly-dev-..."
```

### 风险
- Key 泄露到 Git 历史 → 即使后续删除，`git log` 仍可见
- 同事 clone 后看到的是别人的 Key，需要手动改
- 违反项目 `CONTRIBUTING.md` 安全检查规则

### 正确做法

```toml
[mcp_servers.tavily]
command = "uv"
args = ["run", "python", "-m", "mcp_server_tavily"]

[mcp_servers.tavily.env]
# 【用户必填】在 https://app.tavily.com/home 注册，获取自己的 API Key
# 注册后修改此处为你的 Key
TAVILY_API_KEY = "<your-tavily-api-key-here>"
```

或使用环境变量（用户在自己的 `~/.codex/config.toml` 中覆盖）。

> **铁律**：API Key、Token、密码不得硬编码在共享配置中。用占位符 `<your-key-here>` 或环境变量替代。

---

## 踩坑 4：MCP 配置语法错误导致整个 Codex 无法启动

### 现象
修改 `.codex/config.toml` 后 Codex 完全启动失败，不是某个 MCP server 不可用，而是整个 app 无法加载。

### 根因
TOML 文件如果有语法错误（如非法字符、编码问题、重复 section），Codex 在解析配置阶段就崩溃，不会降级到跳过出错的部分。

### 预防措施
- 修改 `.codex/config.toml` 后，立即重启 Codex 验证
- 不要在一个 commit 里同时改多段 MCP 配置
- BOM 头（`\ufeff`，由某些编辑器添加）会导致 TOML 解析失败

> Claude 的修复分支 `origin/fix/mcp-config-path-and-docs` 已处理了 `free_web` 部分的类似问题，务必参考。

---

## 同事 clone 后的操作清单

非技术同事 clone 项目后，Agent 应按以下顺序完成：

1. `uv sync` — 安装项目依赖
2. `node --version` — 检查 Node.js，没有则 `winget install OpenJS.NodeJS.LTS`
3. `uv pip install git+https://github.com/changcheng967/free-web-tools.git` — 免费搜索 MCP
4. `npm install -g @playwright/mcp && npx playwright install chromium` — 浏览器自动化 MCP
5. `uv pip install mcp-tavily` — **Tavily MCP（需先注册获取 Key）**
6. 修改 `.codex/config.toml` 中的 `TAVILY_API_KEY` 为自有 Key
7. 重启 Codex → 新建对话，工作目录设为项目根目录

> **注意**：步骤 6 一定不能跳过 — 共享的 Key 会触发 Tavily 风控（不同 IP 用同一 Key 像滥用）。

---

## 相关文档

- [AGENTS.md](../../AGENTS.md) — 项目总纲 + 环境搭建
- [.codex/config.toml](../../.codex/config.toml) — Codex MCP 服务器配置
- [Claude-3p config](../../../AppData/Local/Packages/Claude_*/LocalCache/Roaming/Claude-3p/claude_desktop_config.json) — Claude Desktop 3P MCP 配置
- [docs/fac-mcp-setup.md](../fac-mcp-setup.md) — FAC MCP 配置（记录了 3P 模式路径差异）
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — 安全检查
- [docs/onboarding.md](../onboarding.md) — 非技术同事上手

---

## 踩坑 5：Claude Desktop 3P 模式配置路径不同（2026-07-14 新增）

> **教训等级**：⚠️ 重要 — 之前 PR #84 曾错误断言 "Claude Desktop cannot load command+args MCP"，实为没找到正确的 3P 配置文件路径。

### 背景

PR #84 尝试在 Claude Desktop（3P 模式，外接 DeepSeek）配置 Tavily MCP，但修改了 `Claude\claude_desktop_config.json` 后无效果。当时错误地总结为 "Claude Desktop cannot load `command`+`args` format MCP servers"，并在 `docs/lessons/anysearch-tavily-dual-search-setup.md` 中建议用 curl 替代。

**实际根因**：3P 模式有自己的独立配置文件路径：

| 模式 | 配置文件 |
|------|---------|
| 普通模式 | `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json` |
| **3P 模式** | `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude-3p\claude_desktop_config.json` |

### 现象
- 修改了 `Claude\claude_desktop_config.json`，重启后 Tavily 不出现
- Settings → Developer → Connector 中只有 `fac` 和 `playwright`，没有 `tavily-mcp`
- `main.log` 显示 `LocalMcpServerManager Closing all (0 servers)` — 本地 MCP server 数量为 0

### 正确做法

编辑 **3P 模式**的配置文件，添加：

```json
{
  "deploymentMode": "3p",
  "mcpServers": {
    "tavily-mcp": {
      "command": "npx",
      "args": ["-y", "tavily-mcp@0.1.2"],
      "env": {
        "TAVILY_API_KEY": "<your-api-key>"
      }
    }
  }
}
```

关键字段（来自 [Tavily 官方文档](https://docs.tavily.com/documentation/mcp#configuring-mcp-clients)）：
- `"tavily-mcp"` — key 名**必须**与 npm 包名 `tavily-mcp` 一致，不能简写为 `"tavily"`
- `"tavily-mcp@0.1.2"` — **固定版本号**，不要用 `@latest`。`@latest` 会安装最新版 `@0.2.21`，其依赖 `@modelcontextprotocol/sdk@1.26.0` 可能与 2026年4月版的 Claude Desktop 不兼容

### 关于"Claude Desktop 不支持 command+args"的错误结论

PR #84 在多次尝试失败后错误地总结为不支持。实际验证表明：
- Claude Desktop 3P 模式**完全支持** `command`+`args` 格式的本地 MCP server
- 项目中 `playwright` 和 `fac` MCP 都使用 `command`+`args` 格式，运行正常
- 唯一的区别是**配置文件路径**，不是配置格式

### 元教训：反复犯同样低级错误的原因

这次 Tavily MCP 配置是一个典型案例，暴露了 Agent 工作流中的系统性缺陷：

1. **官方文档没有成为第一步**：Tavily 官方文档明确写了正确的 key 名和版本号，但 Agent 没有主动搜索，是靠用户贴过来的
2. **项目已有文档被忽视**：`docs/fac-mcp-setup.md` 早已记录了 3P 模式的配置路径差异（`Claude-3p\` vs `Claude\`），Agent 没有搜索就动手
3. **错误的结论被固化**：PR #84 中 "Claude Desktop cannot load command+args MCP" 的错误断言留在了另一个 lesson 文档里，形成了错误的知识

**改进措施**（已写入 `docs/solutions/workflow-issues/search-first-before-implementing.md`）：
- 任何配置/MCP/工具安装任务，第一步搜索官方文档
- 第二步搜索项目 `docs/` 下的已有记录（`grep -r "关键词" docs/`）
- 只在确认没有现成方案后，才动手修改

> **铁律**："先搜再造" — 官方文档 → 项目 `docs/` → 再动手。AGENTS.md Workflow Principle ①。
