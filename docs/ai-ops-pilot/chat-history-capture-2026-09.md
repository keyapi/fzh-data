---
okf: v0.1
type: Research
title: ChatGPT 聊天记录沉淀能力与团队知识方案调研
description: 核实 workspace 选择机制、Codex 数据归属、额度模型、Business vs Enterprise 的会话可见性、共享 Project 的真实限制，并比较 qm / 插件市场 / LangSmith 等替代方案
tags: [ai-pilot, chatgpt-business, workspace, chat-history, compliance-api, codex, shared-projects, credits, qm, plugin-marketplace]
timestamp: 2026-09-16
version: 2
sources:
  - https://help.openai.com/en/articles/8798634-managing-data-sharing-and-privacy-in-chatgpt-business
  - https://help.openai.com/en/articles/8542216-managing-members-seat-types-and-roles-in-chatgpt-business
  - https://help.openai.com/en/articles/8801890-managing-workspace-lifecycle-and-migration-in-chatgpt-business
  - https://help.openai.com/en/articles/20001155-managing-credits-and-spend-controls-in-chatgpt-business
  - https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
  - https://help.openai.com/en/articles/10169521-projects-in-chatgpt
  - https://help.openai.com/en/articles/8266418-data-retention-when-a-member-is-removed-from-a-workspace
  - https://help.openai.com/en/articles/8555545-file-uploads-faq
  - https://help.openai.com/en/articles/9261474-compliance-platform-for-enterprise-and-edu
  - https://help.openai.com/en/articles/20001407-managing-admin-api-keys
  - https://openai.com/enterprise-privacy/
  - https://openai.com/business/pricing/
  - https://developers.openai.com/codex/config-file/config-reference
  - https://github.com/yc-software/qm
  - https://github.com/garrytan/gstack
---

# ChatGPT 聊天记录沉淀能力与团队知识方案调研

> 调研日期：2026-09-16（v2）。缘起：老板希望「第一步把工作区里所有人的聊天记录都沉淀下来，之后整理成资料文档 / skill」。
> v2 补充：workspace 选择机制、Codex 数据归属、额度模型、Enterprise 实现细节与价格、共享 Project 的真实限制、以及若干替代方案。
> 只写能在官方资料中核验的结论；第三方报告单独标注；无法核实的标「未核实」。

## 1. 结论先行

### 1.1 对老板诉求的判定

> **「自动收集全员聊天」在 ChatGPT Business 上做不到。** 这不是配置问题，是档位问题——官方定价对比表上 Business 的 `Compliance API Logs Platform` 一栏直接标 **`No`**，Enterprise 才是 `Yes`。
>
> 更重要的是：**即使升到 Enterprise 能拿到全量会话，也不等于能得到 skill。** 聊天记录是「过程」不是「产物」；从一堆对话里蒸馏出可复用规则，本身是一份不比「直接写」更轻的人工工作。**方向应该从「收聊天」改成「收产出」。**

### 1.2 但有一条必须提前堵住的坑

**成员「加入了 Business 工作区」不等于「聊天落在 Business 工作区里」。** 工作区是按会话显式选择的，用户可以随时切回个人工作区聊天。**在个人工作区里产生的对话，公司看不到、也不算工作区数据。** 试点若不明确要求，很可能出现「以为在用公司账号、实际聊天都在个人空间」的情况。

## 2. workspace 到底是什么

### 2.1 必须显式选择，不是自动的

官方原文：`When logging into their ChatGPT accounts, users can select which workspace is active for the current session. On ChatGPT web, workspaces are available from the profile menu. On mobile, workspaces are available in the sidebar.`

- 工作区是**账号级容器**（`A workspace is a unique ChatGPT environment with its own settings, members, and resources`）。
- 用户**可同时属于多个工作区**（个人 + 公司），通过 profile menu / 侧边栏切换。**「选工作区」这个动作之所以存在，就是因为一个人可能属于多个。**
- **聊天归属「当前激活的那个工作区」**，按会话生效。
- **未核实**：不主动选择时默认激活哪个工作区（官方未写明）。

### 2.2 个人工作区与公司工作区可以合并——但不可逆，且要慎用

官方明确：`Merging workspaces is permanent and cannot be undone.`

- 合并后**个人工作区被删除**，聊天历史与 GPTs 迁入 Business 工作区。
- **`Plugins are deleted`、`Custom instructions are deleted`** —— 个人插件与自定义指令不迁移。
- 个人订阅被自动取消退款（移动端订阅需自行取消）。
- 合并后数据算公司的；**离开工作区即失去访问**。
- **Business 管理员不能强制员工合并，也不能强制删除员工的个人工作区。**

→ **对试点的含义**：如果想「保证大家的聊天都在公司工作区里」，**唯一可靠的办法是要求成员登录时切到公司工作区**，而不是指望合并（合并不可逆，不该轻率动员）。这也意味着**必须给运营一条明确的操作纪律**，否则数据会漏。

### 2.3 合并后成员的 GPTs/Projects 归属

官方（成员被移出工作区时）：`On removal, a member's projects and GPTs are reassigned to a workspace owner, and are not flagged for deletion.`

**但紧接一句很关键**：`Conversations held within projects and GPTs are flagged for deletion in accordance with the workspace's data-retention policy.` 且 `Conversations and files created by the removed member are not transferred, and are not visible to the workspace owner.`

→ **「项目被转交给 owner」不等于「项目里的对话也被保留」**。人一走，**项目容器留下了，对话内容按保留策略标记删除、且 owner 原本也看不见**。把团队知识押在某个成员的个人项目里是危险的。

## 3. Codex 的数据在哪

Codex 是本地软件，但**「在哪跑」和「在哪记账/管控」是两件事**：

| 维度 | 事实 |
|------|------|
| 登录 | 与 ChatGPT 同一个账号（`Sign in with your ChatGPT account`） |
| 执行位置 | Local = 你自己的设备；Cloud = OpenAI 托管环境。官方：`Managed workspaces can control Codex local use and Codex cloud tasks separately.` |
| **本地会话记录** | **存在本地**。官方配置项 `history.persistence = save-all \| none`，作用是 `Control whether Codex saves session transcripts to history.jsonl` → 会话记录落在成员机器上的 `history.jsonl` |
| 是否同时上云 | **未核实**（官方未明确说明本地会话是否同步到云端） |
| 管理员可见性 | 内容上：`Other members do not automatically see those chats or Codex activity.`（**看不到**）。治理上：可强制绑定工作区（`forced_chatgpt_workspace_id`）、可控制 Codex local 是否启用、用量进 Compliance API（Enterprise/Edu） |

→ **回答「本地 Codex 登录算不算」**：**算在管控和计费里，不算在可见内容里，而且它的会话记录本身就在成员自己的电脑上。**

### 3.1 「网页和本地 App 联动」——核实结论：存在，但大概率不是 Codex

用户描述「老板在网页上操作了什么，就转到本地 App 上了」。**这事是真的，但主角是 ChatGPT Work，不是 Codex。**

官方（ChatGPT Business release notes）：

> `Continue Work across devices: Cloud Work conversations now sync across web, mobile, and desktop, so you can start on one surface and continue on another. **Local conversations stay on your computer.**`

> `Cloud Work chats sync across web, mobile, and desktop. Work chats started on web or mobile appear in the desktop app... **Messages and task context may be stored in the cloud, even when work runs locally.**`

**普通 Chat 也跨端同步**：`Chats created in Chat sync between ChatGPT web and the desktop app.`

**但 Codex 是独立的，且不出现在网页上**：

> `Codex remains a separate view. Its workflows are unchanged, and **its history remains separate from ChatGPT history. Codex does not appear on web.**`

Codex 的 `local ↔ cloud` 交接确实存在，但**只在 Codex 内部**（会话里的 `/cloud`、`/local` 命令），**不会跨到 ChatGPT 的网页界面**。

→ **一句话**：老板看到的「网页 → 本地 App」联动，是 **ChatGPT Work 的云端会话同步**；Codex 那条线是独立且封闭的。

### 3.2 会话记录存放位置与可恢复性

| 类型 | 存在哪 | 公司能否取回 |
|------|--------|-------------|
| **本地 Codex**（CLI / IDE / 桌面 Local） | 本地 `$CODEX_HOME`（通常 `~/.codex/`）下的 **`history.jsonl`**；配置项 `history.persistence`（`save-all \| none`）、`history.max_bytes`、`sqlite_home` | ❌ **不能**。无云端副本、无管理端入口。**设备损坏或人离职即永久丢失。** |
| **Codex 云任务** | OpenAI 托管环境，见 chatgpt.com/codex | ⚠️ 服务端在，但 Business **无合规导出通道** → 实操上取不回 |
| **ChatGPT 侧内容**（含 Work） | 云端，Business 工作区 `retained indefinitely` | ⚠️ 数据在，但 `the workspace owner can't view that private content` |

**Business 工作区对 Codex 的可见性**：只有**用量/采用度**与**策略开关**（`Codex Local` / `Codex Cloud` 可分别控制）；**会话正文不可见**。审计日志记录的也只是 Codex「Policies & Configurations」的**变更**，且走 Compliance API（Enterprise/Edu）。

→ **对试点的硬结论**：**若要求「会话可归档、可追溯」，本地 Codex 模式不满足。** 要么让成员改用 **Codex 云任务**（chatgpt.com/codex），要么走 **ChatGPT Work 的云端会话**。

## 4. 额度模型：不是「一个席位固定额度」

用户的理解只对了一半。官方是**两层**：

1. **每席位包含额度**：`Included usage is evaluated for the paid ChatGPT seat assigned to each member.`
2. **超出后走工作区共享积分池**：`After that included usage is consumed, eligible activity may draw from the workspace credit pool...`
3. **共用口径**：`Codex, ChatGPT Work, ChatGPT for Excel, and Workspace Agents use a shared allowance and credit pool.` —— 也就是说，**广告复盘 Agent 跑得多，会消耗掉别人 Codex 的额度**。
4. 管理员可为按**席位类型**设置每月积分上限，并支持 **per-user override（优先级更高）**；`By default, all seats and users have no limits specified.`；仅 owner 可购买积分/自动充值。

→ **对试点的含义**：预算要按「一个共享池」来管，不能按「每人固定额度」估。而且**默认没有上限**，需要管理员主动设。

## 5. 谁能看到聊天：Business vs Enterprise

| 能力 | Business | Enterprise / Edu |
|------|----------|-----------------|
| 成员各自历史 | ✅ | ✅ |
| 其他成员看你的聊天 | ❌ 默认不可见 | ❌ 默认不可见 |
| 共享单个会话（成员主动） | ✅ 共享链接 | ✅ |
| **管理员读取全部会话** | ❌ **无此能力** | ✅ Compliance Platform |
| **数据导出** | ❌ `Data export is not available in a ChatGPT Business workspace.` | ✅ |
| 禁用共享链接（全员） | ❌ 明确没有该开关 | ✅ Enterprise 专属 |

**官方证据（最强的一条）**：官方定价对比页 [openai.com/business/pricing](https://openai.com/business/pricing/) 逐特性列出 `Compliance API Logs Platform` —— **Business: `No`；Enterprise: `Yes`**。

帮助中心旁证：`Because each user has their own chat history. A Business workspace allows collaboration, but chats are not automatically visible to other members.` / `Does usage analytics let admins read all user chats? No.`

### ⚠️ 仍存在一处口径冲突（v3 更新：已找到第三处来源）

官网 [enterprise-privacy](https://openai.com/enterprise-privacy/) 的 Business FAQ 写着管理员「**可以查看、访问、导出和删除**工作区中终端用户的会话」。这与上面帮助中心 + 定价页的证据**直接矛盾**。

**v3 又找到第三处，且它明列 Business**：《Data access for your managed ChatGPT account》(20001067) 称管理员 `may be able to access, export, audit, retain, delete and opt-in to share data tied to this account`，范围含 **`Conversation history and shared workspace content`**——但带限定语 **`where enabled by your organization's configuration and applicable law`**。

| 来源 | 性质 | 说法 |
|------|------|------|
| 帮助中心 8798634 / 11509118 + 官方定价对比页 | **产品能力文档** | 管理员**不能**看；`Compliance API Logs Platform` = **No** |
| Enterprise Privacy 页（Business FAQ） | **法务/承诺页** | 管理员**可以**查看、访问、导出、删除 |
| Managed Account Notice 20001067 | **法务/承诺页** | 管理员**可能可以**访问、导出、审计、保留、删除（含会话历史），**若组织配置与法律允许** |

**v4 结论（用户追问「网上肯定有标准答案」后，追加一轮取证）**：

> **判定：Business 的 owner 在后台看不到成员对话内容，也没有任何导出成员对话的途径。置信度约 85%。**
> 「管理员可查看/导出」的措辞**极可能是法律权利语言，而非已上线的产品功能**。

支撑「不能」的证据（更具体、更新）：

- **官方定价对比页** `Compliance API Logs Platform`：**Business = No / Enterprise = Yes**；同页 Business 为 No 的还有 **SCIM、RBAC、Analytics dashboard、IP allowlisting、数据驻留**——且**没有任何一行**涉及对话查看/导出。
- **`learn.chatgpt.com/work-admin-faq`**：`For **eligible Enterprise and Edu** workspaces, the Compliance Logs Platform provides Work user prompts and agent responses.`
- **微软 Purview 文档**（强旁证）：前置条件是 `**ChatGPT Enterprise plan** — the connector support applies to the enterprise version`，**未提 Business**。
- **17 家 eDiscovery/DLP 合作方**全部命名为「ChatGPT Enterprise」。
- **The Register（2026-07-23，独立媒体）**：`**Business users have no built-in alternative.**`

判定「能」的两条**只给结论、不给机制**：Enterprise Privacy 页（Business FAQ）与 Managed Account Notice 20001067。判为法律语言的四条理由：① 同页 Enterprise 条目**点名了机制**（Compliance API），Business 条目没有；② 20001067 是一揽子法务告知，必须覆盖 Enterprise，取最宽表述并加 `where enabled` 限定；③ 产品对比页明标 No，若是已上线功能不可能标 No；④ 媒体与工具商实测均无此功能。

**仍未闭环的一点（如实记录）**：社区（LINUX DO，2026-08-03）有人称在 Business 后台**看到过导出选项**（点了等邮件），但**无人确认邮件是否送达、也未确认导出的是否为成员对话**（可能只是自身数据或串味）。距 The Register 报道仅 11 天，**可能是灰度**。官方文档间的矛盾至今未澄清。

→ **行动建议**：按「不能」规划；若老板坚持，用 owner 账号**实测**一次导出路径即可闭环。

## 6. Enterprise 到底怎么实现（已核实）

### 6.1 机制

1. 在 Admin Console → **Credentials → Admin keys** 建**工作区级** Admin key（`Each Admin key applies to one ChatGPT workspace.`）。
2. **权限门槛高**：`Only a workspace owner can grant broad compliance access or the Conversation messages permission.` 普通 admin 只能拿单个日志类目（audit / auth / app）。
3. 调用（base `https://api.chatgpt.com/v1/compliance`）：
   - `GET /workspaces/{id}/logs?event_type=CONVERSATION_MESSAGE&limit=N&after=<ISO8601>`
   - `GET /workspaces/{id}/max_event_time`（新鲜度水位）
   - `GET /workspaces/{id}/logs/{log_file_id}`（下载 NDJSON）
4. **返回含消息正文**：`message.content.value`，另含 `conversation.id`、`message.author.type`、`tools_used`、`skills_used`、`annotations.urls` 等。
5. **旧的 stateful 查询路由已于 2026-06-05 下线**，现在只能走文件式日志。

### 6.2 工程现实（这是隐藏成本）

- **只保留 30 天**：`The Compliance Logs Platform retains data for 30 days. If longer retention is desired then consumers should implement a system to continuously download all logs and retain them according to their policies.`
- **删除不可恢复**：`Deleted data is not recoverable.`
- 所有调用本身被记录用于审计。
- **也就是说：要变成「长期知识资产」，必须自建定时轮询 + 下载 + 落库 + 去重**，这是一条真正的数据管道，不是开个开关。

### 6.3 官方定位是合规，不是知识管理

该能力官方定位为 **eDiscovery / DLP / SIEM**，并列了 Purview、CrowdStrike、Netskope、Zscaler、Relativity、Smarsh 等 18 家合作伙伴。**「把聊天蒸馏成内部文档/skill」在官方文档中既无背书也未禁止——属于灰区（未核实）。** 且审计请求全程留痕、删除不可恢复。

### 6.4 价格

- **Enterprise：不公开。** 定价页只写 `Custom pricing` / 联系销售，**无公开席位价与最低席位数**（是否有隐含门槛：未核实）。
- **Business（参考）**：Standard 席位 年报 **$20**/人/月、月报 **$25**/人/月；Premium 年报 $100、月报 $125；**至少要 2 个席位**；单订阅上限 **200** 个付费席位。

→ 结论：**「升级 Enterprise 换全量会话采集」是一条需求不明确、成本不透明、还要自建管道的路**，不建议作为试点第一步。

## 7. 共享 Project 深挖（用户重点质疑项）

### 7.1 机制

- **谁能建**：`Projects are available to all free and paid subscription types globally.` → **单人建、单人用完全可行**，不是必须多人。
- **能邀请谁**：`You can only invite members within your workspace.`（个人邮箱 / 工作区组 / 工作区链接）
- **装什么**：chats + 上传文件 + project instructions + project memory
- **能取用什么**：`ChatGPT can draw from anything in the shared project – including chats, uploaded files and custom instructions`
- **两级权限（原文）**：
  - **Edit** = `allows members to update instructions, upload or remove files, and invite others (but not remove existing members)`
  - **Chat** = `lets members see and interact with the project's chats, files, and instructions (but not invite others)`

### 7.2 限额（用户要求确认的数字）

| 项 | 数值 | 适用范围 |
|----|------|---------|
| **每项目文件数** | **40** | **Business / Enterprise / Edu / Pro**；Free 5、Go/Plus 25。且 `only 10 files can be uploaded at the same time` |
| **协作者上限** | **100** | Pro / Business / Enterprise / Edu；**Plus、Go 只有 10**；Free 5 |
| 项目数量 | **无上限** | `Users can create an unlimited amount of projects.` |
| 每项目 chat 数上限 | **未核实** | 官方未给出 |
| 单文件大小 | 512 MB/文件；文本/文档 2M tokens；CSV/XLSX 约 50MB；图片 20MB | 全计划 |
| 总存储 | 25 GB/人、100 GB/组织 | 全计划 |
| 上传速率 | 80 文件 / 3 小时 | 全计划 |

→ **用户看到的「40 文件」「100 人」两项均属实**，且 40 文件对 Business 适用（不是更少）。共享项目与个人项目**套用同一套数字**。

### 7.3 但是——几个会让人失望的限制

1. **没有同步协作**：`Chats in shared projects can be branched, not collaborated on synchronously.` 是「分叉」不是「共编」。
2. **项目里的对话可以被成员移出或删除，之后 owner 也看不到了**——「沉淀」的可靠性依赖成员不撤。
3. **共享后记忆被锁死**：一旦共享，强制 **project-only memory 且不可逆**，也访问不到成员个人 memory/自定义指令。
4. **共享项目里用不了 Google Drive / Slack 等链接源**：官方文档明确说这些源在 **private project** 里打开（`Open your private project`）。**这直接砍掉了「把公司资料接进来」的能力**——恰好是知识沉淀最需要的。
5. **无导出**：Business 工作区数据导出为 `No`，且没有「一键导出全部项目」。
6. **人的离开会伤到内容**：见 §2.3——项目转交给 owner，但**项目内对话按保留策略标记删除，且 owner 原本就看不见**。

### 7.4 第三方实测反馈（非官方，需打折看）

- 共享项目里 **app/custom connector 不工作**，社区帖直言 `Shared Projects in Business workspaces for team collaboration is essentially useless without the ability to access company knowledge layer and connected apps.`
- 共享即降级：**Work Mode 不可用、File Library 被禁**，官方支持回复「no timeline」。
- **无团队级记忆**：记忆是「按人」的，项目之间上下文不互通，只能靠重建项目/重贴指令硬撑。

→ **判定**：共享 Project 是「**一个团队在一个话题上持续协作**」的容器，**不是**可导出、可审计、跨项目复用的企业知识库。**适合试点初期做小范围沉淀点，不适合当作「全公司知识底座」。**

## 8. 更好的方案（用户要求）

### 8.1 Garry Tan 的那个项目：很可能是 `yc-software/qm`

**置信度：高（匹配到具体项目），但「by Garry Tan」是 likely 而非 confirmed。**

- 仓库：[yc-software/qm](https://github.com/yc-software/qm)，描述 `Multiplayer agent harness for work.`，MIT，**创建于 2026-07-29**（正合「上个月」），约 15,000 stars。
- README 明确支持多人**在同一个 project 内**协作：`collaborate with the agent in channels, group messages, and projects`；`Each person and each room has its own scoped memory, files, keychain view, permissions, crons, web apps, and durable sandbox`。
- 技能机制：**`Skills are scope-owned and shareable by grant`**，并有 `admin-gated promotion to the whole org and skill packs imported from git repositories`。
- 部署：**自托管**（`qm init . --target fly-or-aws`），跑在自己的云账号里。
- 归属说明：仓库挂在 **YC 官方 org `yc-software`** 下，**不在 Garry Tan 个人账号**；他的个人账号只有 18 个仓库，多为旧 Rails/JS fork。Garry Tan 作为 YC CEO 公开推荐过 QM（二手来源）。
- **注意**：README **未描述**技能版本化/审计；靠 grant 共享 + 管理员提升 + git 导入。

**顺带核实**：你们 `AGENTS.md` 里「工作流三原则 (adapted from gstack ETHOS.md)」的来源确为 [garrytan/gstack](https://github.com/garrytan/gstack)，其 **team mode**（`./setup --team`，提交 `.claude/` 与 `CLAUDE.md`，队友 clone 即得）与你们现在的做法几乎同构。**一处小出入**：gstack ETHOS.md 原文是 **"Boil the Ocean"**，你们译作「把湖煮干 (Boil the Lake)」——属改写，非错误。

**对 FZH 的适配性**：qm 在「多人同一空间协作 + skill 可共享 + 可导入 git skill 包」上**确实比 ChatGPT Projects 更贴近老板的诉求**。但它是**自托管 agent harness**，需要自己部署到 Fly/AWS，**面向的是工程团队**，6–8 名运营能否上手是最大问号。建议**列入观察，不作为试点首选**。

### 8.2 我们已有的 Git 化方式本身就是更优解

对照 [workspace-agent-capability-boundary-2026-09.md](workspace-agent-capability-boundary-2026-09.md) 的对比表：在版本控制、变更审批、多人合并、环境迁移、审计五个维度上，**Git 都强于平台内对象**。而下面的发现进一步说明**两者可以打通**。

### 8.3 OpenAI 工作区插件市场：**能直接吃我们现有的 Claude 插件格式**

- 路径：**Admin → Plugins → Import marketplace**，只填 GitHub 仓库 URL；子目录填 Path。
- **目录文件可复用 `.claude-plugin/marketplace.json`**（官方同时接受 `.agents/plugins/marketplace.json` 与 `.claude-plugin/marketplace.json`）。
- 支持 **branch / tag / commit pinning**（固定 commit 即不跟进更新）；**每日自动同步**；安装策略 `AVAILABLE` / `INSTALLED_BY_DEFAULT` / `NOT_AVAILABLE`。
- **限制**：导入**仅支持 GitHub**（不支持其他 Git host）；声明 MCP 的插件**仅桌面端**可用；**sync 绑定导入者本人的 GitHub 连接**（该人离职需重导）；公共目录自助发布仍为 "coming soon"。
- 另有 **Codex plugin sharing**：Business 用户可从 Codex app 把本地构建的插件分享给工作区成员（`Shared with you`），管理员可用 `plugin_sharing = false` 关闭。

→ **这是「Git 真源 + 平台分发」的现成桥**：Git 仓库仍是 canonical，运营在 ChatGPT/Codex 里以插件形式拿到能力。

### 8.4 其他值得知道的方案

- **Claude Code Plugin Marketplace**：`.claude-plugin/marketplace.json` 放 git 仓库；`.claude/settings.json` 的 `extraKnownMarketplaces` + `enabledPlugins` 可**全团队默认启用**；省略 `version` 即按 **commit SHA** 更新，可建 stable/latest 双通道；**git 原生审计**。缺点是面向 CLI，非技术同事不友好。
- **LangSmith Context Hub**（2026-05 上线）：AGENTS.md / SKILL.md 的**版本化 registry**，commit 不可变 + staging/production tag，`langsmith hub push/pull`，**明确面向「非工程师作者」**。最贴近诉求，代价是绑定 LangChain 生态。

## 9. 建议

1. **不要排期「自动收集全员聊天」。** Business 无此能力（定价页 `No`）；Enterprise 有但成本不透明、要自建 30 天滚动归档管道，且是合规工具挪用。
2. **把目标从「收聊天」改成「收产出」。** 聊天是过程，skill 是产物。让运营在**产出环节**留痕，比在聊天环节捞一遍再人工蒸馏便宜得多。
3. **试点第一周就定「聊天在哪发生」的纪律。** 明确要求登录时切到公司工作区；否则数据会漏进个人工作区且公司拿不到。
4. **共享 Project 用作「周沉淀点」，不作知识底座。** 记住它的三个硬伤：共享后不能用 Google Drive/Slack 源、成员可把对话移出、无导出。
5. **能力沉淀走 Git + 插件市场。** Git 仓库为真源；用 OpenAI 的 **Import marketplace**（可直接消费 `.claude-plugin/marketplace.json`）把它分发给非技术同事。注意 GitHub-only 与「绑定导入者 GitHub 连接」两个坑。
6. **观察 `yc-software/qm`。** 它最接近「多人同一空间 + skill 共享」的形态，但自托管、偏工程；等试点跑出需求轮廓再评估。

## 10. 未核实清单

1. Business 工作区实际有无「管理员查看成员会话」入口——两份官方文档冲突（§5），建议按「无」决策。
2. **不主动选择时默认激活哪个工作区。**
3. Codex 本地会话（`history.jsonl`）是否同步到云端。
4. 单个 Project 的 chat 数量上限。
5. 本地 Codex 记录进入 Compliance API 的粒度（内容还是仅元数据）。
6. 共享 Project 内的对话能否被管理员统一导出。
7. Enterprise 是否有隐含的最低席位数/年约门槛。
8. 「把聊天记录用于知识蒸馏」在合规条款下的边界（官方未背书也未禁止）。
9. `yc-software/qm` 与 Garry Tan 本人的关联（repos 挂在 YC org，非其个人账号）。

## 11. Sources

### OpenAI 帮助中心 / 官网

- [Managing data, sharing, and privacy in ChatGPT Business](https://help.openai.com/en/articles/8798634-managing-data-sharing-and-privacy-in-chatgpt-business)
- [Managing members, seat types, and roles in ChatGPT Business](https://help.openai.com/en/articles/8542216-managing-members-seat-types-and-roles-in-chatgpt-business)
- [Managing workspace lifecycle and migration in ChatGPT Business](https://help.openai.com/en/articles/8801890-managing-workspace-lifecycle-and-migration-in-chatgpt-business)
- [Managing credits and spend controls in ChatGPT Business](https://help.openai.com/en/articles/20001155-managing-credits-and-spend-controls-in-chatgpt-business)
- [Using Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)
- [Projects in ChatGPT](https://help.openai.com/en/articles/10169521-projects-in-chatgpt)
- [Data retention when a member is removed from a workspace](https://help.openai.com/en/articles/8266418-data-retention-when-a-member-is-removed-from-a-workspace)
- [File uploads FAQ](https://help.openai.com/en/articles/8555545-file-uploads-faq)
- [Compliance Platform for Enterprise and Edu](https://help.openai.com/en/articles/9261474-compliance-platform-for-enterprise-and-edu)
- [Managing Admin API keys](https://help.openai.com/en/articles/20001407-managing-admin-api-keys)
- [ChatGPT pricing & plan comparison](https://openai.com/business/pricing/)（Business vs Enterprise 能力矩阵）
- [Enterprise privacy at OpenAI](https://openai.com/enterprise-privacy/)（与帮助中心冲突的口径来源）

### 开发者文档

- [Codex config reference](https://developers.openai.com/codex/config-file/config-reference)（`history.persistence`、`forced_chatgpt_workspace_id`）
- [Building Codex plugins](https://developers.openai.com/codex/plugins/build)
- [Admin API reference](https://chatgpt.com/public/admin/api-reference)（Compliance / Projects 端点）

### 开源项目

- [yc-software/qm](https://github.com/yc-software/qm) — Multiplayer agent harness
- [garrytan/gstack](https://github.com/garrytan/gstack) — AGENTS.md 三原则来源

### 第三方（非官方，需打折）

- [OpenAI Developer Community: apps not working inside projects](https://community.openai.com/t/apps-custom-connectors-not-working-inside-projects/1369786/19)
- [Hjarni: Projects don't scale to a team](https://hjarni.com/blog/claude-and-chatgpt-projects-dont-scale-to-a-team)
- [Elastic: OpenAI ChatGPT Enterprise integration fields](https://docs-v3-preview.elastic.dev/elastic/integration-docs/tree/main/reference/openai_chatgpt_enterprise.md)

### 本仓库

- [workspace-agent-capability-boundary-2026-09.md](workspace-agent-capability-boundary-2026-09.md) — 姊妹篇，Agent 侧能力边界
- [brief-for-boss.md](brief-for-boss.md) — 对外件（本文**未修改**）
