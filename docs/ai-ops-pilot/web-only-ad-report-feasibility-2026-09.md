---
okf: v0.1
type: Research
title: 纯网页路径可行性判定 — Workspace Agent 每日拉赛狐广告报告
description: 针对「运营不能装任何本地软件」这一硬约束，逐项核实 ChatGPT Business 的 Workspace Agent 能否经 MCP 调我们自有 HTTPS API 并每日定时出报告；给出六问的定性答案、必须新建的组件、以及认证/发布/更新的具体代价
tags: [ai-pilot, chatgpt-business, workspace-agents, mcp, oauth, scheduling, sellfox, ads-report, web-only]
timestamp: 2026-09-16
sources:
  - https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business
  - https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt
  - https://help.openai.com/en/articles/12628342-company-knowledge-in-chatgpt
  - https://help.openai.com/en/articles/11391654-chatgpt-business-release-notes
  - https://developers.openai.com/plugins/build/mcp-server
  - https://developers.openai.com/plugins/build/auth
  - https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
  - https://developers.openai.com/workspace-agents/trigger-runs
  - https://cdn.openai.com/business-guides-and-resources/workspace-agents-security-overview.pdf
---

# 纯网页路径可行性判定 — Workspace Agent 每日拉赛狐广告报告

> 调研日期：2026-09-16。**这是决定试点成败的一问**：老板的拟定架构是「ChatGPT Business 工作区 + Workspace Agent + 运营从网页用」；
> 硬约束是**大部分运营装不了也跑不了本地工具**（Win10 装不上 Codex、`git clone` 都难、只能退回 workbuddy），**所以本地桌面方案对本团队不可接受**。
> 承接 [workspace-agent-capability-boundary-2026-09.md](workspace-agent-capability-boundary-2026-09.md) 与 [work-vs-codex-and-local-automation-2026-09.md](work-vs-codex-and-local-automation-2026-09.md)（后者结论是「本地优先」，**本文回答的是本地被排除后剩下的那条路**）。
> 结论只采用可在官方正文中逐句引用的表述；官方没写的标「**未核实**」。

## 1. 结论先行

| # | 问题 | 判定 |
|---|------|------|
| Q1 | Workspace Agent 能否调我们自有 HTTPS API | **能，但必须先包成 MCP server，且该 server 必须公网可达。** 没有「Business 直达内网」的官方路径 |
| Q2 | 在哪执行 | **OpenAI 云端**。运营纯网页可用，**零本地安装** |
| Q3 | 前置与代价 | **只有 Admin/Owner** 能开 developer mode 与发布 app；**Business 上 app 发布后不能原地改，只能重建**；ChatGPT **不认 API key，只认 OAuth 2.1 或匿名** → 赛狐密钥必须藏在**我们自己的 MCP server 里** |
| Q4 | 定时 | **支持**。Agent 自带 schedule（`run every`），且可跑在云端 |
| Q5 | 产出 | 对话内回答 + **Slack 推送 + 生成文档/表格/幻灯片等 artifact**；Files 限额 512 MB/文件、10 GB/agent |
| Q6 | 底线 | **老板的架构成立**。要建的是一个**公网可达的只读 MCP server**（包住赛狐广告 API），跑在我们的服务器上，不是运营的电脑上 |

## 2. Q1 — 能不能调我们自己的内部 API

### 2.1 官方只接 MCP，且只接远程

- 帮助中心 FAQ：`Can I connect to a local MCP server? Not directly. ChatGPT connects to remote MCP servers.`
- Agent builder 的工具列表明确含**自定义 MCP**：`You can add tools, apps, custom MCPs, skills, and files in the agent builder.`；可添加项为 `apps, such as Google Calendar, Google Drive, Slack, and SharePoint` / `your own custom MCPs` / `additional tools, such as image generation and web search`。
- Business 发布说明同样写明：`Add skills, files, and custom MCP servers.`

**读法**：赛狐 API 不能"直接接"。**中间必须有一层 MCP server**，把「拉广告报告」暴露成 tool。

### 2.2 必须公网可达（Business 上没有隧道）

- 部署要求原文：`For public plugin submission, deploy the MCP server at a stable, publicly reachable HTTPS endpoint.` 端口形态、传输方式、保活要求另有：`Support the MCP streamable HTTP transport.` / `Respond at a stable URL, typically ending in /mcp.`
- 如果服务必须保持私有，官方给的方案是**公网反代 + mTLS**：`If the MCP server must remain private, deploy a public HTTPS proxy that forwards MCP requests to the private server. Use OpenAI-managed mTLS to authenticate ChatGPT as the MCP client`。并明确 `Use the published ChatGPT connectors IP ranges... An IP allowlist does not replace authentication or authorization.`
- **隧道这条路在 Business 上已排除**（另见 [log.md](log.md) v4 修正 3 与 [skill-distribution-and-selfhost-options-2026-09.md](skill-distribution-and-selfhost-options-2026-09.md) §4）。本次复核补充两条硬证据：隧道文档全文**未出现 Business**，且其表述以 `Enterprise/Edu` 工作区为对象（`A tunnel associated only with a personal Platform organization doesn't automatically appear in an Enterprise/Edu workspace.`）；官方 changelog 亦只写 `for enterprise customers`。
- 隧道文档另提到 **Harpoon**（`tunnel-client includes an embedded MCP server, Harpoon, that exposes configured HTTP targets by label... Use this when you need to reach a small set of private REST endpoints without exposing them publicly.`），但 `Harpoon is not a general-purpose proxy`，且同样在隧道体系内 → **Business 上不可依赖，未核实**。

**结论**：**公网 HTTPS 是 Business 上唯一的正式路径**。我们的 MCP server 要做反向代理/网关设计，但**它可以自己部署在内网，对外只暴露一个受控的 HTTPS 入口**（官方明说"公网代理转发到私有 server"是被支持的形态）。

## 3. Q2 — 在哪执行，运营要不要装东西

**云端，纯网页，零安装。** 官方安全白皮书原文：

> `They can run in the cloud, work on schedules, use connected apps and files, ask for approval when needed, and improve over time as teams use them.`

> `Workspace agents run inside the managed ChatGPT workspace, so access is governed through the same workspace identity, role, app, and connector controls admins already use.`

入口是网页侧边栏：`Every agent automatically includes a ChatGPT entry point accessible from the left-hand sidebar.` 运营两种用法：`type @ and the agent name in a regular ChatGPT conversation` 或 `open the agent from Agents`。

MCP app 本身也是网页限定：`Are MCP apps available on mobile? No - web only.`

**对硬约束的直接回答：运营端不需要装任何东西，只需要浏览器。**

## 4. Q3 — 前置条件与代价

### 4.1 谁能建、谁能发

| 动作 | Business 上的权限 |
|------|------------------|
| 开 developer mode | `Business: Only Admins can use developer mode.` / `Only admins/owners can enable developer mode and deploy an app. Admins cannot enable developer mode for individual members in their workspace.` |
| 发布 MCP app | `Only Admins and Owners can publish apps.` |
| 建/发 Agent（非 MCP 部分） | 走 4 个角色开关：`Enable agents` / `Enable agent building` / `Enable agent publishing` / `Enable agent publishing with agent-owned connections` |

**判定：运营同学接不了工具。**「把赛狐包成 MCP」这件事**只能由 Admin/Owner 做**，这是本项目必须由技术侧承担的固定工作量。

### 4.2 改一个工具要多大代价

- **Business 上不能原地改**：`For Business plans, apps cannot be updated after publishing at launch. To change tools or metadata after publishing, you must recreate and republish.`
- **冻结快照**：`After an admin first approves an MCP app for the workspace, ChatGPT uses a "frozen" snapshot of its available tools and inputs. Changes made later by the app's developer are not applied until an admin reviews and publishes an update.`
- 快照对不上会**报错且无人被通知**：若线上与快照不一致 `tool calls can error`；`admins are not proactively notified when an app needs review.`

**推论**：**首期只发只读、且尽量少的工具**。每加一个 tool 都要重建 app + 重新挂到 agent，运营侧会看到中断。

### 4.3 认证 —— 本调研最关键的一条

官方原文（`developers.openai.com/plugins/build/auth`）：

> `ChatGPT does not support machine-to-machine OAuth grants such as client credentials, service accounts, or JWT bearer assertions, nor can it present custom API keys or customer-provided mTLS certificates.`

MCP 侧可声明的只有两种 `securitySchemes`：`noauth`（`The tool is callable anonymously; ChatGPT can run it immediately.`）与 `oauth2`（`The tool needs an OAuth 2.0 access token`）。另一处：`Many plugin MCP servers can operate in a read-only, anonymous mode, but anything that exposes customer-specific data or write actions should authenticate users.`

**这条决定了架构**：

1. **赛狐的 API key / token 绝不能"交给 ChatGPT 保管"** —— 平台根本不支持这个通道。
2. **密钥必须落在我们自己的 MCP server 上**（server-side secret），由 server 去调赛狐。ChatGPT 看到的是一个匿名或 OAuth 保护的工具端点。
3. 若用 `noauth`，等于**把公网端点敞开** → 必须用官方给的两道补充控制：**OpenAI 托管的客户端证书（mTLS）** `ChatGPT presents an OpenAI-managed client certificate when connecting to MCP servers, so you can verify the client at the transport layer with mTLS`，以及 **ChatGPT 出口 IP 白名单**（`You can also allowlist ChatGPT's published egress IP ranges`）。
4. 若用 `oauth2`，要有自己的授权服务器（OIDC，须支持 `offline_access`/refresh token；`If OAuth is configured without offline_access, ChatGPT may lose access after the original authorization expires`）——**对首期是明显过重**。

**Agent 侧的账号模式**（决定能不能无人值守）：
- `End-user account - each person running the agent authenticates with their own account.`
- `Agent-owned account - the agent uses a shared connection, so people running the agent do not need to authenticate during the run.` 官方并建议 `use a service account when possible`，且发布这类 agent 需单独开关 `Enable agent publishing with agent-owned connections`。

**推荐组合**：**MCP server 自带赛狐凭证 + 工具端 `noauth` + mTLS/IP 白名单收口 + 只读**。这样定时任务不依赖任何人登录。

## 5. Q4 — 定时是否支持

**支持，且是官方一等公民。** 帮助中心：

> `On the ChatGPT channel page, select Add schedule.` → `Choose the channel.` / `Choose the schedule type and frequency (run every).` / `Add any additional instructions.` / `Select Add schedule.`

release notes 亦确认 Workspace Agents `can be created, previewed before publishing, shared within a workspace, and run on a schedule.`

**关于"没人点击也会跑"**：白皮书明说 `They can run in the cloud, work on schedules`——**云端调度，不依赖任何人的电脑开机**。这正是本文与「本地优先」方案的分水岭。

补充路径（若需要由外部系统触发）：**API trigger**。原文限制很硬：

> `The API queues the agent run and returns 202 Accepted with no response body. It does not return a run ID, and the agent's response cannot currently be retrieved through the API.`

→ **只能"点火"，取不回结果**。故结果投递应依赖 ChatGPT 会话或 Slack 渠道，而不是回调。

## 6. Q5 — 产出形态

- **对话内回答**（默认）。
- **Slack**：`You can also select Add channel to connect a Slack workspace and add this agent to a channel.`（注意：进 Slack 后**所有 app 连接必须改为共享认证** `all app connections for that agent must use shared authentication`）
- **生成文件**：白皮书列 `generated artifacts/files where applicable`，并在成本章节举例 `create artifacts like documents, slides, or spreadsheets`；release notes 新增 `Speech output: Agents can now create audio files as part of their responses.`
- **写动作需批准**：`By default, write actions for apps and connectors are set to Always ask during an agent run.`
- **约束的边界**（易被误读）：`Connector Action Constraints govern what the agent can ask a connector to do. They do not filter or restrict the data a connector returns in response.`

## 7. Q6 — 底线：要建什么，跑在哪

**老板的架构成立**，且是唯一满足"运营不能装软件"的架构。需要新增的组件只有一个：

```text
【我们的服务器 / 内网】                        【OpenAI 云端】
  Sellfox 广告 API                              Workspace Agent（Business）
        ▲                                              │  每日 schedule
        │ 服务端持有赛狐凭证（.env / secret mgr）        │
  ┌─────┴──────────────────┐                          │
  │  MCP server（只读）     │ ◄── 公网 HTTPS /mcp ─────┘
  │  tools:               │      传输层 mTLS
  │   get_ad_report(...)  │      + ChatGPT 出口 IP 白名单
  │   list_campaigns(...) │      工具端 securityScheme = noauth
  └───────────────────────┘
        对外只暴露这一个入口；内网其余服务不暴露
```

**必做清单**：

1. **写一个只读 MCP server**，暴露赛狐广告报告的 1–3 个 tool（`streamable HTTP`，路径 `/mcp`）。代码进 Git，走现有 PR 流程。
2. **部署到公网可达的 HTTPS 端点**（反代到内网即可，官方认可 `public HTTPS proxy that forwards MCP requests to the private server`）。
3. **在 ChatGPT Business 管理后台**（`Workspace settings → Apps → Create`）由 **Admin** 建 app、`Scan Tools`、发布。
4. **建 Workspace Agent**，挂这个自定义 MCP，配 **schedule**（`run every`，每日），发布到工作区目录。
5. **收口**：只读工具 + mTLS + IP 白名单 + 服务端最小权限凭证（`We recommend limiting access to only what the agent needs.`）。

**运营侧的动作：打开 ChatGPT 网页，看结果。** 没有任何安装步骤。

**成本提示**：`Workspace agents use credits when they run`，且 `Agents may also use more credits when they run on schedules`；免费期已于 **2026-07-06** 结束（`We've extended the free period for workspace agents until July 6, 2026. Credit-based pricing will begin on that date.`）。每日定时运行是**持续计费**项。

## 8. 未核实

1. **定时任务的频率下限**（能否到"每小时"、能否指定时区/具体时刻）——Workspace Agent 帮助页只写 `schedule type and frequency`，未给枚举值。**未核实**。
2. **ChatGPT 渠道的定时运行结果如何呈现在运营面前**（是否生成一条会话/通知）——官方未描述。**未核实**。
3. **自定义 MCP app 在 Business 是否占用"工作区 app 数量"上限**。**未核实**。
4. **Harpoon 在 Business 工作区是否可用**（沿用前文结论，倾向不可用）。**未核实**。
5. **赛狐广告类接口的具体端点与限流**，须以 `SELLFOX_API/` 镜像文档为准，本文未核。

## 9. Sources

### OpenAI Help Center
- [ChatGPT Workspace Agents for Enterprise and Business](https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business)
- [Developer mode and MCP apps in ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt)
- [Company knowledge in ChatGPT](https://help.openai.com/en/articles/12628342-company-knowledge-in-chatgpt)
- [ChatGPT Business release notes](https://help.openai.com/en/articles/11391654-chatgpt-business-release-notes)

### OpenAI Developers
- [Build an MCP server](https://developers.openai.com/plugins/build/mcp-server)
- [Authentication](https://developers.openai.com/plugins/build/auth)
- [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [Trigger workspace agent runs](https://developers.openai.com/workspace-agents/trigger-runs)

### OpenAI 白皮书
- [Workspace agents security overview](https://cdn.openai.com/business-guides-and-resources/workspace-agents-security-overview.pdf)（Current as of April 29, 2026）

### 本仓库
- [workspace-agent-capability-boundary-2026-09.md](workspace-agent-capability-boundary-2026-09.md) — 能力边界与 Git 化对比
- [work-vs-codex-and-local-automation-2026-09.md](work-vs-codex-and-local-automation-2026-09.md) — 本地优先方案（本文回答其被排除后的替代路）
- [skill-distribution-and-selfhost-options-2026-09.md](skill-distribution-and-selfhost-options-2026-09.md) — 三条分发路对比
- `SELLFOX_API/` — 赛狐 OpenAPI 端点镜像（本文未核广告端点细节）
