---
okf: v0.1
type: Research
title: ChatGPT Workspace Agent 能力边界与 Git 化方式对比
description: 逐项核实 Workspace Agent 的创建/编辑形态、上传物、工具接入、权限治理与可维护性，并与仓库现有 Git + docs + skills + scripts + PR 方式对比，给出「哪些留 Git、哪些放 Workspace」的结论
tags: [ai-pilot, chatgpt-business, workspace-agents, mcp, governance, maintainability, version-control, git]
timestamp: 2026-09-16
sources:
  - https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business
  - https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt-beta
  - https://help.openai.com/en/articles/12628342-company-knowledge-in-chatgpt
  - https://help.openai.com/en/articles/20001066-skills-in-chatgpt
  - https://help.openai.com/en/articles/20001256-plugins-in-chatgpt-and-codex
  - https://help.openai.com/en/articles/11509118-admin-controls-security-and-compliance-for-plugins-and-apps
  - https://help.openai.com/en/articles/8542216-managing-members-seat-types-and-roles-in-chatgpt-business
  - https://help.openai.com/en/articles/20001519-custom-gpt-retirement-and-migration-faq
  - https://help.openai.com/en/articles/11391654-chatgpt-business-release-notes
  - https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
  - https://developers.openai.com/blog/connect-private-mcp-servers-to-openai-products
  - https://developers.openai.com/plugins/deploy/connect-chatgpt
  - https://cdn.openai.com/business-guides-and-resources/workspace-agents-security-overview.pdf
  - https://github.com/openai/tunnel-client
  - https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/chatgpt/workspace_agents/workspace-agents-api-trigger.ipynb
---

# ChatGPT Workspace Agent 能力边界与 Git 化方式对比

> 调研日期：2026-09-16。对象是老板《FZH AI运营试点计划 1.0》里 4 个「标准 AI 助手」的拟定载体。
> 本文只写能**在 OpenAI 官方资料中逐条核验**的结论；官方文档未提及的，一律标注「**未核实**」，不用厂商宣传补空。
> 本文承接 [assistant-platform-research-2026-09.md](assistant-platform-research-2026-09.md) 的高层核实（该文已确认支持 Workspace Agents / Company Knowledge / 远程 MCP app），**只回答该文没有回答的工程问题**。

## 1. 结论先行

### 1.1 五个问题的直接答案

| # | 问题 | 结论 | 证据强度 |
|---|------|------|---------|
| Q1 | 创建与编辑形态 | **纯平台内表单 + 对话式生成**。没有官方导入/导出定义文件的路径，**进不了版本控制**。唯一例外是 **Skill**（可上传/下载为文件）和 **GitHub 插件市场**（JSON 目录 + 每日同步） | 强（官方文档逐条） |
| Q2 | 上传的是什么 | 文档（Files）、Skill（**含 code**）、MCP 工具定义。**上传的代码能否执行、在何沙箱执行，官方未记载 → 未核实** | 文档/限额=强；代码执行=**未核实** |
| Q3 | 工具接入 | 必须 **MCP**，且必须 **远程**。自有 HTTPS 接口要包成 MCP server 才行。私网服务可用 **Secure MCP Tunnel**（出站单向，不用开公网）。Business 档位 **只有 Admin/Owner** 能开 developer mode 和发布 | 强 |
| Q4 | 权限与治理 | Business 有 4 个 Agent 角色开关（默认开）；Agent **可原地更新**（草稿→发布），有版本历史可回滚；**MCP app 在 Business 不能原地改，只能重建**。完整审计日志（Compliance Platform/API）**只给 Enterprise/Edu** | 强（另有 1 处口径不一致，见 §7） |
| Q5 | 可维护性 | **多人协作无实时合并**（Save conflict 靠人工刷新，且会覆盖本地草稿）；**定义不可导出**导致环境迁移=手工重建；**供应商锁定风险高** | 强 |

### 1.2 一句话结论

> **Workspace Agent 是合格的「运营前台」，不是合格的「工程真源」。**
> 它的可维护性在三个点上明显弱于现有 Git 化方式：**定义不可导出、协作无合并、审计分档位**。
> 因此建议维持 [assistant-platform-research-2026-09.md](assistant-platform-research-2026-09.md) §6.2 已提出的分工——**Git 留真源，Workspace 做前台**——但本文把该分工从「原则」细化为 §6 的可执行清单，并新增一条此前没有的抓手：**用 Skill 文件做 Git ↔ 平台的同步物**（因为它是唯一能双向进出的载体）。

### 1.3 一个时间敏感项

Custom GPT 的退役时间表**正落在试点窗口内**（今日 2026-09-16）：

- **2026-09-11**：管理员通知
- **2026-09-17**：迁移入口与用户横幅目标日（就是明天）
- **2026-09-25**：**停止创建新的 custom GPT**
- **2026-12-11**：正式退役，GPT 停止运行

且迁移是**有损**的：官方明说「GPT 的 instructions 变成 plugin 里的 skill」「connected apps 作为 app 加进去」，但 **custom actions 不迁移**、**所选模型不带过去**。这既是平台自身「助手定义格式」在 3 个月窗口内翻新的直接证据，也是 §5.4 供应商锁定判断的实测样本。

## 2. 调研方法与证据等级

- 官方资料集中在 `help.openai.com`、`developers.openai.com`、`cdn.openai.com` 三个 OpenAI 域名。**`help.openai.com` 对自动化抓取返回 403**，本文涉及该站的页面通过公开的 reader 代理（`r.jina.ai`）按原 URL 读取正文；结论只采用正文中可直接逐句引用的表述。
- 官方文档之间**存在一处口径不一致**（Business 档位的 RBAC 粒度），已在 §7 单列，不做平均。
- 「未核实」= 在本次检索到的官方页面中**没有找到**相应表述。它不等于「不支持」，只等于「不能作为依据」。

## 3. Q1 — 创建与编辑是什么形态

### 3.1 创建：平台内表单 + 对话式生成

入口是 ChatGPT 侧边栏的 **Agents**（官方原文：`You can access ChatGPT workspace agents by clicking on Agents on the left-hand sidebar`）。两条官方路径：

1. **模板**：`Browse templates` → 选模板 → `Use template` → 选工具 → `Create Agent` → 在 builder 里细化 → `Create`。
2. **Agent builder**：`Create` → 用一句话描述任务（或 `Start blank`）→ 审阅生成的 draft plan → `Build this agent` → 细化 → `Create`。可随时 `Skip to builder`。

Builder 里可配置的对象（官方列出）：名称、描述、**instructions**、模型与 reasoning effort、图标、tagline、分类、starter prompts、**文件**、**skills**、**apps/自定义 MCP**、channels（ChatGPT / Slack / API）、**schedules**。

**关键判断：这是一个「对话式低代码表单」，产物是平台内对象，不是可 diff 的文本文件。**

### 3.2 程序化创建：Codex 插件（beta），但边界很硬

官方有 **Workspace Agents plugin in Codex**（beta），`Codex acts as the agent builder: it updates agent configuration, but it does not run the agent itself.` 它能做：查找/检索 agent、查看草稿与已发布配置、创建/更新草稿（含 name/description/instructions/model 等）、配置 Memory、web search、app actions、write approvals、schedules、API triggers、Slack channels，**并且只在被显式要求时发布**（`Codex only publishes an agent when you explicitly ask it to publish`）。

官方同时列出**它做不到**的（`Limitations`）：

- 不能 preview / 运行 agent，不能看 analytics
- 不能改 sharing / access controls
- **不能编辑、替换、重命名、删除、分离已有的文件或 skill 文件**
- 不能创建 Workspace Agent access token
- **不能取回 API 触发的 agent 响应**
- 且 `The plugin can upload ordinary files to new paths, but it does not overwrite existing files.`

> 对提需求的人的直接影响：「用 Codex 管 agent 版本」这条路**官方只支持到「改草稿」**，文件与 skill 仍要回 Agent Studio 手工维护。

### 3.3 能不能进版本控制

**Agent 定义：不能。** 在本次核验的全部官方页面中，**没有任何** agent 定义的导入/导出（export/import）路径。没有导出，就没有进 Git 的入口。

**但有三条官方通道值得单独记：**

| 通道 | 官方表述 | 对 Git 化的意义 |
|------|---------|----------------|
| **Skill 文件上传/下载** | 创建 skill 可 `Upload from your computer`；管理员在 admin **Skills** 页可对 skill 点 `Download` | ✅ **唯一可双向进出的载体**：可在 Git 写 SKILL.md 再上传 |
| **GitHub 插件市场** | `Workspace admins can import a plugin marketplace from a public or private GitHub repository and keep its plugins up to date with daily sync. A marketplace is a JSON catalog that lists the plugins to import.` | ⚠️ 只同步**插件包**（skills + apps），**不是 agent 定义**；且路径是「GitHub → 平台」单向、以天为单位 |
| **插件目录 Export CSV** | `Admin > Plugins > Export CSV`；含 plugin/app/skill 详情、开发者、版本、日期、验证状态；**不含工作区内自建插件**；每日快照、最长滞后 48 小时 | ⚠️ 只导出**公共目录**，不覆盖自建内容 |

**平台内的版本控制能力（替代品，不等价）：**

- **草稿/发布分离**：`Creating or updating an agent changes its draft configuration. Existing users continue using the latest published version until you publish the draft.`
- **版本历史**：`You can review earlier versions of an agent, preview a previous version, and republish an earlier version.` → **有回滚能力**。
- **没有**：分支、并行版本、逐行 diff、blame、revert 单个字段。**Business 档位尤其没有 diff**（Enterprise/Edu 的 MCP app 才有 `changes to existing actions are shown as a diff`）。

## 4. Q2 — 上传的是什么，脚本能不能跑

### 4.1 三类可上传物

1. **Files（知识）**：官方限额 **512 MB/文件、10 GB/agent**；并明确警告 `Performance may decline as more files and larger amounts of data are added, and very large file collections may prevent the agent from running.` 官方建议拆小、按目录组织、只放需要的文件。
2. **Skills**：`A skill can include instructions, examples, and code.` / `Skills can include instructions, supporting files, and code.` 上传时平台会扫描：多数扫描后即可用；可能有 **Needs Review**；**Blocked** 的不可用。官方提示 `The scan should not replace your own review, policies, or judgment`。
3. **自定义 MCP**：见 §5，上传的是**端点与元数据**，不是代码。

### 4.2 「脚本能不能真的执行」——官方没有给答案

这是本次调研**最需要标红的一处**：

- 官方确认 Skill **可以包含 code**，也确认 agent `can run in the cloud, work on schedules`（Workspace Agents Security Overview）。
- 但本次核验的 **Workspace Agents 帮助页、Skills 页、Plugins 页均未描述**「附件或 skill 中的代码会被执行」的执行模型，也**未描述**沙箱、依赖安装、网络出口、凭证注入与执行审计。
- 已知的相反证据：Codex 侧 `it does not run the agent itself`；ChatGPT 侧 agent 的确定性能力被官方描述为来自 **connected apps 与 custom MCP**，而非上传文件。

**结论：`上传 .py 就能跑` 目前无法在官方资料中核验。应假定「不能」，并按 §5 走服务化。**

> 实务推论：仓库里 `uv run python <script.py>` 的执行语义（真实凭证、真实网络、真实依赖）**无法复制到一个对话式沙箱里**。凡是要动赛狐/ERPNext/NAS 真实数据的动作，都必须落在 Git 侧的 MCP server 上。

## 5. Q3 — 工具接入：只能 MCP，且必须远程

### 5.1 官方明确「不支持本地，只能远程」

> `Can I connect to a local MCP server? Not directly. ChatGPT connects to remote MCP servers. If your MCP server runs on a private network, on-premises, or on a developer machine, use Secure MCP Tunnel to connect it to supported OpenAI products without exposing the server to the public internet.`

另有：`Requires a remote MCP server`（自定义 connector 条目）；**MCP app 仅网页端**（`Are MCP apps available on mobile? No - web only.`）。

### 5.2 私网 / 内网 / Tailscale：Secure MCP Tunnel 是官方答案

官方提供 **Secure MCP Tunnel**，要点（来自 `developers.openai.com` 与 `openai/tunnel-client` 开源仓库）：

| 项 | 官方表述 |
|----|---------|
| 形态 | **出站单向**：客户侧跑 `tunnel-client`，主动连 OpenAI 拉取排队的 MCP 请求，转发给内网 MCP server |
| 是否需要公网 | **不需要**。`The private MCP server does not need a public listener.` / `tunnel-client does not need inbound internet access.` |
| 网络要求 | 出站到 `api.openai.com:443` 的 `/v1/tunnel/*`；配 mTLS 时另需 `mtls.api.openai.com:443`；本机可达 MCP server |
| 协议 | **stdio 与 HTTP 都支持**（`--mcp-command` / `--mcp-server-url`） |
| 前置权限 | 建/改隧道需 **Tunnels Read + Manage**；跑 client 或选隧道需 **Tunnels Read + Use**。`Tunnel permissions are organization-level, not project-level.`，由 org owner 或 RBAC admin 授予 |
| 关联 | 隧道须**关联到目标 workspace**；只挂个人 Platform org 的隧道 `doesn't automatically appear in an Enterprise/Edu workspace` |
| 不支持 | `It does not support public plugin submission or distribution.`（公开分发要稳定公网 HTTPS 端点） |
| 已知坑 | OAuth 授权服务器**不会**被自动隧道化；`requests through the tunnel fail until tunnel-client reconnects`（client 掉线即断） |

> **对本仓库的映射**：如果走隧道，`tunnel-client` 需要长期常驻在一个能访问内网服务的机器上（官方给了 K8s sidecar / 独立 Deployment / VM+systemd 三种部署形态）。这是一台**新增的常驻组件**，不是一次性配置。

### 5.3 「接我们自己的 HTTPS 接口」的正确理解

- 我们能接的不是「任意 HTTPS 接口」，而是 **MCP server**。自带 REST API 要先包一层 MCP。
- 官方开发者博客另提到 **Harpoon** 可把模型扩展到「已登记的 REST 目标」（`bounded by customer-owned target registration, allowed methods, response-size limits, timeouts`，并明确 `labels are not a general-purpose network bridge`）。这在 Platform 侧，**在 Business 工作区是否可用未核实**。

### 5.4 Business 档位的额外限制（对试点很关键）

- `Only admins/owners can enable developer mode and deploy an app. Admins cannot enable developer mode for individual members in their workspace.` / `Only Admins and Owners can publish apps.` → **运营同学自己接不了工具**。
- `For Business plans, apps cannot be updated after publishing at launch. To change tools or metadata after publishing, you must recreate and republish.` → **改一个工具要重建整个 app**。
- **冻结快照**：`ChatGPT uses a "frozen" snapshot of its available tools and inputs. Changes made later by the app's developer are not applied until an admin reviews and publishes an update.` 若线上 app 与快照不一致，`tool calls can error`；且 `admins are not proactively notified when an app needs review`。
- `Agent mode will not use custom apps.`；Deep Research 对自定义 app **只读**；Company Knowledge 只纳入 **search/fetch** 类 app，**不支持交互 UI**。

## 6. Q4 — 权限与治理

### 6.1 Business 档位：谁能创建、谁能发布

**内置角色**（官方《Managing members, seat types, and roles in ChatGPT Business》）：**Owner / Admin / Analytics Viewer / Member** 四种。

**Agent 的 4 个管理员开关**（官方 Workspace Agents 页，明确写 `Workspace admins can control how ChatGPT workspace agents are used in Business and Enterprise workspaces`）：

| 开关 | 放开的动作 |
|------|-----------|
| Enable agents | 成员浏览与运行 agent |
| Enable agent building | 成员创建、编辑、复制 agent |
| Enable agent publishing | 成员把 agent 发布到 workspace 目录 |
| Enable agent publishing with agent-owned connections | 成员发布使用「自有/共享认证连接」的 agent |

官方对最后一项有醒目告警：开启后 creator 能用**自己的账号凭证**发布 agent，所有使用者都可能通过该连接访问数据或执行动作。

**默认值**：`ChatGPT workspace agents are on by default at launch.`（Business 默认开；对照：**Enterprise 默认关**，需管理员启用。另有 `connectors remain default off for Enterprise plans, and default on for Business plans.`）

**Agent 自身的访问级别**：`Private to me` / `Anyone at [organization] with the link` / `Publish to [organization] directory`。协作者分 **Can chat / Can edit / Owner** 三级，其中 **`Can edit` 即可编辑共享草稿并发布新版本**。

### 6.2 发布后能否原地更新

| 对象 | Business | 依据 |
|------|----------|------|
| **Workspace Agent** | ✅ **可以**。`Edit agent` → 改 → `Update`；改动先进草稿，发布后生效 | 官方 Workspace Agents 页 |
| **MCP app / connector** | ❌ **不可以**。`recreate and republish to update tools or metadata` | 官方 MCP 页 FAQ |
| **Agent 的工具/元数据** | ⚠️ 走 MCP app 的，受上一条约束 | — |

### 6.3 diff / 审批 / 回滚

- **回滚**：Agent 有 `Version history`——可回看、可预览、**可重新发布历史版本**。
- **审批**：写动作默认 `Always ask`；可在 app 层调为 `Never ask` 或对特定动作 `Custom`。管理员可做**工作区级**动作控制（全动作 / 仅读 / 自定义）。Builder 还能配 **Connector Action Constraints**——但官方特别声明：**约束的是「动作的输入参数」，不过滤「动作返回的数据」**（`They do not filter or restrict the data a connector returns in response.`）。
- **diff**：**Business 档位无 diff**。Enterprise/Edu 在 MCP app 的 action control 里 `Refresh` 才会看到 `changes to existing actions are shown as a diff`，且新动作默认禁用。
- **审计**：官方《Workspace agents security overview》写明 **Compliance Platform / Compliance API** 提供 `the full configuration of every agent, audit logs for every change to every agent, and traces for every run of every agent`，日志为不可变 JSONL、约 10 分钟窗口、p99 < 30 分钟、至少一次投递、`event_id` 去重。
  ⚠️ **但该安全白皮书通篇以 Enterprise/Edu 为对象**（`Workspace agents in ChatGPT Enterprise and Edu help teams...`），MCP 页亦写 `available in the Compliance API for Enterprise/Edu customers`，Skills 页的合规段同样只列 Enterprise/Edu。
  → **Business 档位能否拿到等价审计，未核实，且现有证据倾向「不能」。** 这是本次调研对试点最重要的治理缺口。

### 6.4 平台内的可见性（Business 可用的部分）

- **Agent analytics**（builder 可见）：唯一用户数、运行次数趋势。
- **admin console（admin.openai.com）的 Agents 区**：管理员可看 Agent ID、最近活动、已连 apps、memory 文件、schedules、agent analytics，或直接进 Builder 编辑。
- **admin Skills 页**：每个 skill 的 Owner / Access / Users / Invocations (30d) / Created / Updated。
- 管理员可经 **Workspace agents API（经 Compliance Platform）或 admin console** unpublish/delete agent。

## 7. 官方文档的一处口径不一致（不做平均）

| 文档 | 表述 |
|------|------|
| Workspace Agents 页 | `Workspace admins can control how ChatGPT workspace agents are used in **Business and Enterprise** workspaces.` → 暗示 Business 也有 agent 的角色开关 |
| Admin controls 页（11509118） | `Role-based access control: **Enterprise and Edu** workspaces may assign eligible plugins to custom roles...` / `Role-specific app access in this section applies to **Enterprise and Edu** workspaces. ChatGPT Business administrators manage whether an app is enabled for the workspace.` |

**读法**：Business 的 **Agent** 层有角色开关（前者），但 **plugin/app** 层只到「工作区级开关」，**没有按角色的细粒度**（后者）。两者不矛盾，但 Business 的 RBAC 粒度到底到哪一层，**未核实**——若试点需要「按人分配不同 agent 权限」，须先在工作区实测。

## 8. Q5 — 可维护性（提需求的人最关心的一项）

### 8.1 多人协作：有共享，无合并

官方明说：`Multiplayer editing uses a shared draft, but it does not merge simultaneous changes in real time.` 冲突时出现 **Save conflict**，提示 `Refresh agent` 加载最新版本——而**刷新会用最新版本替换你本地的草稿**，官方因此建议先手工复制未保存的工作。官方给出的缓解办法是**人为协调**：`coordinate with other editors when making substantial changes to the same agent`。

对照 Git：冲突是可解决的合并，且**不会丢工作**。这里的冲突是**覆盖式**的。

### 8.2 权限与职责绑在「Owner」身上

Editors（含 Can edit、含 group 级）**不能**：给他人 Can edit、改工作区级可见性、转移所有权、删除 agent、管理 owner-only 配置（**channel setup、shared ChatGPT skills、custom MCP setup**）。官方还注明 `Some dependencies remain associated with the agent owner. For example, collaborators may only attach certain connector accounts or shared skills that belong to the owner.`

→ 与 [brief-for-boss.md](brief-for-boss.md) R4 想解决的问题（责任落到人名）方向相反：**平台的默认形态会把 agent 的维系绑在单一 Owner 上**，人一走就要转移所有权。

### 8.3 环境迁移：没有导出，就没有迁移

| 迁移对象 | 官方能力 | 结论 |
|---------|---------|------|
| Agent 定义 | 无导入/导出；`Duplicate an agent` 只在同工作区内产生草稿副本 | ❌ 只能手工重建 |
| Skill | ✅ 上传 + 管理员 Download | ✅ 可进 Git |
| MCP app | 注册的是端点与元数据；Business 改配置要重建 | ❌ 无配置导出 |

→ 「测试工作区验证 → 生产工作区上线」这条常规路径，**在 agent 定义层面走不通**。

### 8.4 供应商锁定：高，且有实测样本

- **定义锁定**：instructions/skills/apps 配置都以平台内对象存在，**不可导出**。迁出即重写。
- **格式漂移实测**：Custom GPT 三周内从「宣布退役」走到「停止创建」（见 §1.3），且迁移**不带走 custom actions 与模型选择**。平台自己的助手格式尚在迁移期。
- **执行锁定**：确定性能力必须落在平台外的 MCP server 上——这部分**反而留在我们手里**（这是好消息：真正的资产不会被锁）。
- **成本锁定**：`Workspace agents use credits when they run`，自 2026-07-06 起按 token 计费；`Cumulative credit usage across all workspace agents is visible in ChatGPT Workspace Settings`，**per-agent credit usage 官方称「available soon」**；且 `Agent-specific budget caps or alerts are not currently exposed as a distinct product surface.` → **做不了按 agent 的预算硬闸**。

### 8.5 其他运维细节

- **删了就没了**：`Deleting an agent permanently removes it. This action cannot be undone.`
- **Slack 部署抬高门槛**：agent 进 Slack 后，**所有 app 连接必须改成共享认证**（`all app connections for that agent must use shared authentication`），且 `While an active Slack channel deployment exists, only the owner can add or update the agent's apps and connectors.`
- **换 Slack 工作区会重置**：已配的 channel 被移除、bot 连接重置。

## 9. 逐项对比：Git 化方式 vs Workspace

「Git 化方式」= 本仓库现状：`AGENTS.md`（唯一指令源，`CLAUDE.md` 为 symlink）+ `.agents/skills/*/SKILL.md`（40 个 skill）+ `docs/`（OKF：每目录 `index.md`、每 bundle `log.md`）+ `uv run python` 脚本 + 各模块 `AGENT_HANDOFF.md` + PR 审批（AGENTS.md 第 8 条）+ 提交前 4 条凭证扫描（第 9 条）+ `scripts/update_index.py` 索引联动（第 11 条）。

| 维度 | Git 化（当前仓库） | ChatGPT Workspace | 谁更强 |
|------|-------------------|-------------------|--------|
| **载体** | 文本文件，可读可 diff | 平台内对象（表单 + 对话生成） | **Git** |
| **版本控制** | 分支 / merge / blame / revert / tag | 草稿-发布 + 版本历史（可回滚），**无分支、Business 无 diff** | **Git** |
| **变更审批** | PR review + 4 条凭证扫描，**强制** | 角色开关 + Can edit 可自行发布，**无强制审批点** | **Git** |
| **多人协作** | 分支 + 可解冲突合并 | 共享草稿，**不实时合并**，Save conflict 覆盖本地 | **Git** |
| **能否圈定改动范围** | 行级 diff + review | 无 diff（Business） | **Git** |
| **环境迁移** | `git clone` + `uv sync` 即复制 | **无定义导出，手工重建** | **Git** |
| **审计** | `git log`/`blame` 全量、永久 | 产品内 version history + admin console；**完整审计仅 Enterprise/Edu** | **Git** |
| **上手门槛** | 高（需 Git/CLI，非技术同事要 Agent 代跑） | 低（对话式，运营可自助） | **Workspace** |
| **触达面** | 本地终端 / IDE | ChatGPT 网页 + Slack + 定时 + API 触发 | **Workspace** |
| **权限/分享** | GitHub 仓库权限 | 目录发布 + Can chat/Can edit + group 共享 | 平（各有取舍） |
| **工具执行** | `uv run python`，任意依赖/网络/凭证 | **无文档化代码执行**；工具必须 MCP 服务化 | **Git** |
| **数据边界** | 仓库内文件 + `.env` 凭证 | 只读索引 + 源系统权限继承（Company Knowledge `respects existing permissions`） | 平 |
| **成本** | 近乎零边际成本 | credits 计费，**无 per-agent 预算闸** | **Git** |

**读法**：除「上手门槛」和「触达面」两项外，**Workspace 在所有工程维度上都不如 Git**。这正是「哪些留 Git、哪些放 Workspace」应该按能力类型而非按人群来切的理由。

## 10. 结论：哪些留 Git，哪些放 Workspace

### 10.1 留在 Git（真源）

| 资产 | 理由 |
|------|------|
| **工具代码、MCP server 实现、API schema、测试、阈值** | 平台无代码执行路径，确定性能力只能落在我们自己的服务上 |
| **凭证与 `.env`** | 平台侧只存端点与授权，密钥不进 Agent 配置 |
| **Skill 源文件（SKILL.md）** | **平台支持上传与下载** → 唯一可双向同步的载体，必须 Git 为主 |
| **Agent 的 instructions 文本** | 平台不导出 → **以文本形式在 Git 存一份**，平台改动后回写，避免「平台内孤本」 |
| **面向模型的整理稿（`docs/`）** | 带 Owner、版本、来源、失效日期；上传前经人工确认 |
| **PR 审批 + 凭证扫描** | 平台没有等价的强制审批点 |

### 10.2 放 Workspace

| 能力 | 理由 |
|------|------|
| 面向运营的**交互入口**（含 Slack） | 唯一明显优于 Git 的两项之一 |
| **调度与 API 触发** | 平台原生，且 API 触发有官方 access token + scope 体系 |
| **Agent 级访问控制与目录发布** | 4 个管理员开关 + Can chat/Can edit，运营可自助 |
| **只读工具调用编排** | 通过 MCP 调我们自己的只读服务，符合赛狐广告无写 API 的硬约束 |
| **会话内的临时文件分析** | Files 限额明确（512 MB / 10 GB），适合资料类任务 |

### 10.3 三条可执行的操作约束（本调研新增）

1. **用 Skill 当同步物**。凡是要跨「Git ↔ 平台」的指令，优先落成 Skill 文件（可上传、可下载），而非只写进 Agent instructions。
2. **Agent instructions 必须双写**。平台无导出 → 每次在平台改完，回写一份文本进 `docs/ai-ops-pilot/`（或别的受控目录），否则该 agent 一旦重建即丢失全部调优。
3. **首期只发只读 MCP 工具**。理由有三：Business 档位 MCP app 改不了只能重建；冻结快照不一致会导致 tool call 报错且不通知管理员；完整审计只在 Enterprise/Edu。

### 10.4 对 `brief-for-boss.md` R1 的直接回填

R1 要求「补四要素：载体形式 / 输入输出边界 / 业务 Owner（落到人名）/ 验收口径」中的前两项，现在可以给出确定答案：

- **载体形式**：ChatGPT Business 工作区内的 **Workspace Agent**（Business 默认已开）。
- **输入输出边界**：输入 = 平台内 Files（≤512 MB/文件、≤10 GB/agent）+ Skill + 只读 MCP 工具；输出 = 对话/Slack 消息，**不写回赛狐**。
- **发布权限**：Business 下 **只有 Admin/Owner 能接 MCP 工具并发布 app**；agent 本身可由被授予 `Enable agent building` / `Enable agent publishing` 的成员创建与发布。

## 11. 未核实清单

以下**不能**作为决策依据，需要实测或等官方补文档：

1. **Business 档位的 RBAC 粒度**到底到哪一层（agent 层 vs plugin/app 层的官方表述不一致，见 §7）。
2. **Agent 定义是否有官方导入/导出**——本次核验的全部官方页面均未提及。倾向「没有」，但不排除未公开路径。
3. **上传到 Files 或 Skill 的代码是否执行、在何沙箱、依赖与网络策略**（见 §4.2）。这是本次最重要的空白。
4. **Business 档位能否获得 Compliance Platform / Compliance API 的 agent 日志**（现有证据倾向不能）。
5. **Secure MCP Tunnel 在 ChatGPT Business 档位的可用性**——隧道文档以 Enterprise/Edu 表述为主，而 Business 的 developer mode 仅 Admin/Owner 可开。
6. **Harpoon 的 REST 目标注册是否在 Business 工作区可用**（官方博客为 Platform 侧表述）。
7. **Workspace Agent 的模型与 reasoning effort 在 Business 的可选范围**。
8. **Credits 的具体换算与 per-agent 预算控制**（官方称 per-agent 用量「available soon」）。

## 12. Sources

### OpenAI Help Center

- [ChatGPT Workspace Agents for Enterprise and Business](https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business)
- [Developer mode and MCP apps in ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt-beta)
- [Company knowledge in ChatGPT](https://help.openai.com/en/articles/12628342-company-knowledge-in-chatgpt)
- [Skills in ChatGPT](https://help.openai.com/en/articles/20001066-skills-in-chatgpt)
- [Plugins in ChatGPT and Codex](https://help.openai.com/en/articles/20001256-plugins-in-chatgpt-and-codex)
- [Admin controls, security, and compliance for plugins and apps](https://help.openai.com/en/articles/11509118-admin-controls-security-and-compliance-for-plugins-and-apps)
- [Managing members, seat types, and roles in ChatGPT Business](https://help.openai.com/en/articles/8542216-managing-members-seat-types-and-roles-in-chatgpt-business)
- [Custom GPT retirement and migration FAQ](https://help.openai.com/en/articles/20001519-custom-gpt-retirement-and-migration-faq)
- [ChatGPT Business release notes](https://help.openai.com/en/articles/11391654-chatgpt-business-release-notes)

### OpenAI Developers

- [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [Making private MCP servers reachable without making them public](https://developers.openai.com/blog/connect-private-mcp-servers-to-openai-products)
- [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- [openai/tunnel-client](https://github.com/openai/tunnel-client)
- [Workspace Agents API trigger notebook (openai-cookbook)](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/chatgpt/workspace_agents/workspace-agents-api-trigger.ipynb)

### OpenAI 白皮书

- [Workspace agents security overview](https://cdn.openai.com/business-guides-and-resources/workspace-agents-security-overview.pdf)（Current as of April 29, 2026，Enterprise/Edu 口径）

### 本仓库

- [assistant-platform-research-2026-09.md](assistant-platform-research-2026-09.md) — 上游高层核实
- [brief-for-boss.md](brief-for-boss.md) — 对外件，R1 为此调研的需求来源（**本次未修改**）
- `AGENTS.md`、`.agents/skills/`、`scripts/update_index.py` — 对比基准
