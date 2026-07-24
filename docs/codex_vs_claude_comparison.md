# Codex vs Claude Desktop：小白用户功能对比

> 面向刚接触 AI 编程助手的新同事。重点标注了 Claude 用户转 Codex 时的"坑"。
> 最后更新：2026-06-03

---

## 核心差异一览

| 功能 | Claude Desktop | Codex Desktop | 谁更友好 |
|------|:---|:---|:---:|
| **网络搜索** | WebFetch 开箱即用 | 官方用户开箱即用；第三方需装 MCP | Claude |
| **网页抓取** | 一键抓取，返回 Markdown | 同上，第三方走 MCP | Claude |
| **上下文显示** | 实时百分比进度条 | 无可见指示器 | Claude |
| **记忆系统** | 对话中主动记录偏好 | 有框架但基本空置 | Claude |
| **项目配置传播** | `.mcp.json` 可提交 git | `.codex/config.toml` 可提交 git | 持平 |
| **多模型支持** | 支持第三方模型代理 | 需 Codex++ 等工具 | Claude |
| **线程管理** | 简洁的对话列表 | 支持 Fork、项目分组 | Codex |
| **MCP 生态** | 成熟，社区活跃 | 兼容 MCP，但第三方模型有坑 | Claude |
| **Skills** | `.claude/skills/` | `.agents/skills/` | 持平 |
| **审批系统** | 简单权限弹窗 | Guardian Approval（第三方需手动模式） | Claude |
| **桌面端** | macOS + Windows | macOS + Windows | 持平 |

---

## 详细对比

### 1. 网络搜索 / WebFetch

**这是两个产品最大的差距。**

| | Claude | Codex（官方账号） | Codex（第三方模型） |
|---|---|---|---|
| 配置量 | 0～1 行 | 0 行 | ~10 行 + 安装两个包 |
| 原理 | 平台 HTTP 客户端 | ChatGPT 后端 | 自建 MCP server |
| 体验 | "帮我搜一下 X"→ 直接返回 | 同左 | 多步工具调用 |
| 中国网络 | `skipWebFetchPreflight: true` | 无影响 | 同左 |

> ⚠️ 如果你用 Codex++ + DeepSeek，项目已配置好 `.codex/config.toml`，Agent 会自动引导安装。

### 2. 上下文窗口

- **Claude**：对话顶部显示 `上下文 35%` 这样的百分比，用户随时知道还剩多少空间
- **Codex**：没有可见的上下文指示器。只能通过 `get_goal` 工具查看（需要手动创建 goal）

> 这对小白用户很重要——Claude 让你"看见"对话会不会溢出，Codex 让你"猜"。

### 3. 记忆系统

- **Claude**：在对话中主动说"记住我喜欢用 tab 缩进"，Claude 会写入记忆并在后续对话中使用。`CLAUDE.md` 中也常有记忆段落。
- **Codex**：有 `~/.codex/memories/` 目录（`MEMORY.md` + `memory_summary.md` + `raw_memories.md`），但目前是空框架，不主动积累对话记忆。

> 当前项目中，实际的项目知识都在 `AGENTS.md` 里手动维护，两个 Agent 共享同一份。

### 4. 线程 / 对话管理

- **Claude**：简单的对话列表，无分组，无 fork
- **Codex**：支持 Fork（从历史消息分支新对话）、项目分组、归档。但也更复杂——我们刚刚花了半天修复一个"Fork 线程从侧边栏消失"的 bug

> Codex 的线程管理功能更强，但出问题时也难排查。

### 5. 审批 / 权限

- **Claude**：操作需要权限时弹窗，点"允许"即可。简单直接。
- **Codex**：有 Guardian Approval 系统，审批模式分"自动"和"手动"。**第三方模型用户必须选手动模式**，否则所有操作被 `codex-auto-review` 拦截。

> Codex 的权限系统更精细，但对第三方模型用户是个陷阱。

### 6. 项目级配置

两个都支持项目级配置文件，可以提交到 git：

| | Claude | Codex |
|---|---|---|
| 文件 | `.mcp.json` | `.codex/config.toml` |
| 内容 | MCP 服务器定义 | MCP + 审批 + 更多 |
| git 提交 | ✅ | ✅ |
| 优先级 | 项目 > 全局 | 项目 > 全局 |

### 7. Skills

两个都支持 Skills（可复用的指令模块），但目录名不同：

- Claude：`.claude/skills/<name>/SKILL.md`
- Codex：`.agents/skills/<name>/SKILL.md`

> 本项目已将 Skills 统一放在 `.agents/skills/`，两个 Agent 通过触发词自动加载。

---

## 小白用户选哪个？

| 你的情况 | 推荐 |
|----------|------|
| 用 OpenAI 官方账号 | 两个都行，Codex 原生体验更好 |
| 用第三方模型（DeepSeek 等） | **Claude Desktop**（WebFetch 开箱即用） |
| 需要 Fork 线程管理 | Codex |
| 在意上下文可见性 | Claude |
| 需要社区 MCP 生态 | Claude（更成熟） |

---

## 本项目当前配置

| 能力 | Claude Desktop | Codex Desktop |
|------|:---:|:---:|
| 项目指令 | `CLAUDE.md` → symlink → `AGENTS.md` | `AGENTS.md` |
| Skills | `.agents/skills/` | `.agents/skills/` |
| 网络搜索 | WebFetch（内置） | free-web-tools MCP + Playwright MCP |
| MCP 配置 | 全局 `settings.json` | 项目级 `.codex/config.toml`（已提交 git） |
| 审批模式 | 默认 | 手动审批（第三方模型必须） |
