---
okf: v0.1
type: Research
title: ChatGPT Work 与 Codex 的产品关系及本地自动化能力
description: 核实 Work/Codex 是否为同一产品、桌面端结构、本地代码执行与网络沙箱约束、定时任务能力，并据此给出广告报告自动化的可行架构
tags: [ai-pilot, chatgpt-work, codex, desktop, sandbox, automation, scheduled-tasks, sellfox]
timestamp: 2026-09-16
sources:
  - https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex
  - https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
  - https://help.openai.com/en/articles/11391654-chatgpt-business-release-notes
  - https://learn.chatgpt.com/docs/automations
  - https://learn.chatgpt.com/codex/config-file/config-reference
  - https://developers.openai.com/codex/pricing
---

# ChatGPT Work 与 Codex 的产品关系及本地自动化能力

> 调研日期：2026-09-16。起因：用户认为「ChatGPT Work 就是 Codex 改名」，并质疑「脚本产出→手动上传文件」不配叫 Agent。
> **结论：前半句是误解，后半句是对的——本地桌面路径确实能跑，而且失败点在配置，不在能力。**

## 1. 先纠正：Work 不是 Codex 改名

官方原文（[20001275](https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex)）：

> `ChatGPT includes Chat and Work, plus Codex in the desktop app.`
> `**Codex remains a separate view in the ChatGPT desktop app.** Select Codex from the top-left menu. **Its workflows are unchanged, and its history remains separate from ChatGPT history.**`

**桌面端是三个并列体验：Chat / Work / Codex。** 切换方式：

> `Select ChatGPT or Codex from the top-left menu. In ChatGPT, select Chat or Work from the toggle at the top of the page.`

→ **Work 那个 toggle 只在 ChatGPT 视图内切 Chat↔Work，跟 Codex 没关系。**

**用户说对的那部分**：原来那个独立的 **Codex App 确实被并进了新的 ChatGPT 桌面应用**（2026-07-09：`If you already use the Codex app, update it as usual to move to the new ChatGPT desktop app`）。所以「桌面端只剩一个 App」是事实，但**里面是三个东西，不是把 Codex 改名成 Work**。

管理侧也是三个独立开关：**Work Cloud / Work Local / Codex Local** 分别控制。

| | 定位 | 执行位置 |
|---|---|---|
| **Chat** | 对话 | 云端 |
| **Work（web/mobile）** | 通用知识工作 | 云端：`ChatGPT Work runs in a managed cloud environment` |
| **Work（桌面 Local）** | 通用知识工作 | **本机**，可用本地文件/应用/浏览器 |
| **Codex（桌面/CLI/IDE）** | 编码 | **本机** |
| **Codex Cloud** | 编码 | `isolated OpenAI-managed containers` |

**Work 是通用知识工作 agent**（`Research a topic, analyze information, or create a document, spreadsheet, presentation, report, or Site.`），不是编码 agent，但官方说它与 Codex **能力同源**：`ChatGPT Work gives you the same core capabilities with an experience designed for everyday work.`

## 2. 本地到底能跑什么——能跑脚本、能调 API

用户判断正确：**桌面 App 的本地模式可以在本机执行命令**。

- 沙箱三档：`read-only` / `workspace-write` / `danger-full-access`。
- 权限预设：「Ask for approval」= `workspace-write` + `on-request`；「Full access」= `danger-full-access` + `never`。
- 文件边界：`write permissions limited to the active workspace`（含当前目录与 `/tmp`）。
- 官方明确：`run routine local commands inside that boundary` → **可跑任意 shell 命令与脚本**。
- Windows 用原生沙箱（`[windows] sandbox = "elevated"`），非 WSL。

### ⚠️ 但有三处硬约束——不配好必卡

| # | 约束 | 官方原文 / 配置 |
|---|------|----------------|
| 1 | **网络默认是关的** | `By default, the agent runs with network access turned off.` / `the default workspace-write sandbox mode keeps network access turned off unless you enable it in your configuration`。开法：config 里 `[sandbox_workspace_write] network_access = true`；Work 走 UI：**Settings → Data controls → Work network access** |
| 2 | **目录必须标记为 trusted** | 未信任目录会降级为 `read-only`（`Codex may start in read-only until you explicitly trust the working directory`）→ **脚本写不出输出文件**。用 `[projects."路径"] trust_level = "trusted"` |
| 3 | **无人值守时不能留审批** | 定时任务 `run unattended and use your default sandbox settings`。若留 `on-request`，半夜的网络请求会挂起等人点确认 → 需 `approval_policy = "never"`（且组织策略允许） |

**另有两个风险点**：
- 若启用 `network_proxy`，`allow_local_binding = false` 会 `blocks loopback, link-local, and private destinations`。**赛狐 API 若是公网域名则无碍；若走内网私有 IP/内网域名，需实测** ——「未核实」。
- Windows `elevated` 沙箱依赖**防火墙规则**且需管理员/UAC 初始化，文档明示 `Some enterprise-managed devices block the required setup steps`、部分模式 `Sandboxed commands cannot reach the network`。**内网端点是否放行，文档未说明 → 未核实。**

## 3. 定时任务：本地执行可用

官方（[automations](https://learn.chatgpt.com/docs/automations)）：

> `Desktop app tasks can work with local projects, running in the project directory or an isolated worktree.`
> `Keep the computer on and the app running when a scheduled task needs local files.`
> `The selected project must still be available on disk when the task is scheduled to run.`

- 频率：付费计划最高**每小时**；支持精确时刻与 RRULE（如 `RRULE:FREQ=MONTHLY;BYMONTHDAY=1;BYHOUR=9;BYMINUTE=0`）。
- **Business 活跃定时任务上限 10 个。**
- 云端任务不依赖开机；**本地任务依赖电脑开着且 App 在跑**。
- ⚠️ **事件触发（Gmail/Slack/GitHub webhook）仅云端**：`They aren't available in the ChatGPT desktop app, Codex CLI, or the IDE extension.`
- ⚠️ 一个反直觉的坑：**建在 Project 里的定时任务读不到该 Project 的上传文件**（`it cannot access uploaded files or files stored in that project`）。

## 4. 所以广告报告该怎么做——本地优先

**用户的原话是对的：「脚本产出 → 手动上传进共享 Project」不叫自动化。** 那条路只在「数据必须给人看」时才需要，不该当成主路径。

**正确架构（全部为官方支持的机制）**：

```text
每天/每小时（桌面 App 定时任务，本地执行）
  └─ 在受信任的项目目录里跑既有 Python 脚本
       ├─ 从本机环境变量 / .env 读赛狐凭证
       ├─ 调赛狐 API 拉广告报告
       └─ 产出文件落到项目目录
            └─ 需要给人看时：再进共享 Project 或 docs/
```

**要配的四件事**：
1. `network_access = true`（否则脚本出不了网）
2. 项目目录 `trust_level = "trusted"`（否则写不出文件）
3. `approval_policy = "never"`（否则半夜挂起等确认）
4. 跑任务的机器**保持开机 + App 运行**

**这套的限制**：绑定在**某台机器**上（`Keep the computer on and the app running`），不是服务端常驻。**「每天自动拉十几个报告」可行；「7×24 无人值守」不行。**

## 5. 与另外两条路的关系

| 路径 | 自动化程度 | 适用 | 代价 |
|------|-----------|------|------|
| **本地桌面 + 定时任务** | 高（每日本机自动跑） | ✅ **广告报告首选** | 依赖某台机器开机 |
| **云端 MCP server（公网）** | 高（workspace 级、无需开机） | 要多人共用同一能力时 | 需公网 HTTPS；Business 下 app 发布后**不能原地改只能重建** |
| **手动上传文件进 Project** | 无 | 只作「给人看的交付物」 | 不叫自动化 |

## 6. 未核实

1. Windows `elevated` 沙箱下，**内网/私有网段端点**能否被本机脚本访问。
2. 赛狐 API 若走内网域名（非公网），在默认 `network_proxy` 下是否被 `allow_local_binding = false` 阻断。
3. 桌面端定时任务在**锁屏但未休眠**状态下是否照常执行。
4. 「Work Local」与「Codex Local」在**执行能力上的实际差异**（官方只给了定位差异，未逐项对比沙箱能力）。

## 7. Sources

- [ChatGPT Work and Codex](https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex)
- [Using Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)
- [ChatGPT Business release notes](https://help.openai.com/en/articles/11391654-chatgpt-business-release-notes)
- [Automations (ChatGPT Learn)](https://learn.chatgpt.com/docs/automations)
- [Codex config reference](https://learn.chatgpt.com/codex/config-file/config-reference)
- [Codex pricing](https://developers.openai.com/codex/pricing)

### 本仓库

- [skill-distribution-and-selfhost-options-2026-09.md](skill-distribution-and-selfhost-options-2026-09.md) — MCP / 隧道 / 凭证机制
- [business-seat-account-and-usage-2026-09.md](business-seat-account-and-usage-2026-09.md) — 席位与额度
