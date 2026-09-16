---
okf: v0.1
type: Research
title: ChatGPT Business 聊天记录沉淀能力调研
description: 核实 Business 工作区里成员聊天记录谁能看到、能否导出、Codex 是否计入，以及官方支持的「聊天沉淀为资料/skill」路径；含两份官方文档的口径冲突
tags: [ai-pilot, chatgpt-business, chat-history, retention, compliance-api, codex, shared-projects, plugins]
timestamp: 2026-09-16
sources:
  - https://help.openai.com/en/articles/8798634-managing-data-sharing-and-privacy-in-chatgpt-business
  - https://openai.com/enterprise-privacy/
  - https://help.openai.com/en/articles/9261474-compliance-platform-for-enterprise-and-edu
  - https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
  - https://help.openai.com/en/articles/10169521-projects-in-chatgpt
  - https://help.openai.com/en/articles/12289294-managing-your-tenant-in-admin-console
  - https://help.openai.com/en/articles/8542216-managing-members-seat-types-and-roles-in-chatgpt-business
  - https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business
  - https://help.openai.com/en/articles/11391654-chatgpt-business-release-notes
  - https://developers.openai.com/codex/plugins/build
---

# ChatGPT Business 聊天记录沉淀能力调研

> 调研日期：2026-09-16。缘起：老板希望「第一步把工作区里所有人的聊天记录都沉淀下来，之后整理成资料文档 / skill」。
> 结论对**该设想的可行性**做了直接回答，并指出**两份官方文档在关键问题上口径冲突**——这一冲突必须在上会前解决，不能取平均。

## 1. 结论先行

### 1.1 直接回答老板的设想

> **「所有人的聊天记录自动沉淀到一处」在 Business 档位下，按产品文档的口径是做不到的。**
> 不是配置问题，是档位能力问题：**成员之间默认互相看不到聊天；管理员没有「读取全部成员会话」的产品入口；Business 工作区没有数据导出**。

能做的是另外三件事，都需要**成员主动配合**，而不是管理员后台收：

| 想要的效果 | 官方可行路径 | 需要谁动手 |
|-----------|-------------|-----------|
| 把有价值的讨论**沉淀成团队资料** | **共享 Project**（Business 可用，可放 chats + 文件 + instructions） | 成员主动把内容放进共享项目 |
| 把沉淀的东西**变成可复用的能力** | 打包成 **Plugin / Skill**，由工作区管理员发布到工作区（按角色授权） | 工程打包 + 管理员发布 |
| 事后**审计追溯**（合规用途） | **Compliance API** —— **仅 Enterprise/Edu** | 需升级档位 |

### 1.2 三个具体问题的答案

| 问题 | 答案 |
|------|------|
| 一个 workspace 里聊天，网页端都自动算在这个 workspace 里吗？ | **是。** 工作区是账号级容器：登录时选择工作区，在该工作区里产生的 Chat 与 Codex 记录都归属该工作区，跨网页/桌面/移动/Codex 一致。**但「归属工作区」≠「别人看得见」**。 |
| 别人（含管理员）能看到吗？ | **默认看不到。** 官方原文：每个用户有自己的 chat 与 Codex 历史，「其他成员不会自动看到这些聊天或 Codex 活动」。用量分析与花费控制**不等于**会话访问权（官方 FAQ 明确回答 `No`）。 |
| 用本地 Codex 登录就不算了吗？ | **算在治理与计量内，但内容同样不共享。** Codex local（CLI / IDE 扩展 / 桌面）受工作区开关管控、计费进工作区额度，其使用记录进 **Compliance API（Enterprise/Edu）**；但**其他成员看不到 Codex 活动**。 |

## 2. 最重要的发现：两份官方文档口径冲突

这是本次调研**最需要提请注意**的一点。同一个问题上，OpenAI 两处官方页面说法不一致：

| 来源 | 表述 |
|------|------|
| **A. 帮助中心**《Managing data, sharing, and privacy in ChatGPT Business》 | 「在一个 ChatGPT Business 工作区里，**每个用户有自己的 chat 与 Codex 历史。其他成员不会自动看到这些聊天或 Codex 活动**。」FAQ：`Does usage analytics let admins read all user chats?` → **`No.`** / `Can I export my data from a Business workspace?` → **`No. Data export is not available in a ChatGPT Business workspace.`** |
| **B. 官方隐私页** [openai.com/enterprise-privacy](https://openai.com/enterprise-privacy/)（Business FAQ） | 「在工作区内，终端用户可查看自己的会话。**工作区管理员对工作区有控制权，可以查看、访问、导出和删除工作区中终端用户的会话**（`can view, access, export, and delete end user conversations in the workspace`）。」 |

**两处都是 OpenAI 官方域名，但一个说「不能看、不能导出」，另一个说「能看、能导出、能删」。**

几点观察（不做平均，只陈述事实）：

1. **B 的 Enterprise 条目点名了具体机制**（`workspace admins can access an audit log of conversations and GPTs through the Enterprise Compliance API`），而 **B 的 Business 条目只说「能」，没给任何机制**。而 Compliance API 官方明确是 Enterprise/Edu 专属（§3.2）。**一个没有机制支撑的能力声明，不该被当作可依赖的产品功能。**
2. **A 是产品行为文档**（告诉管理员界面里有什么），**B 是法律/承诺文档**（界定数据权属与责任）。两者层级不同：B 更可能在陈述「数据归工作区所有、管理方有权处置」的**法律立场**，而非「今天界面上有这个按钮」。
3. 有第三方政策追踪站记录该页在 **2026-05-28** 前后有过措辞改动，并指出存在歧义。

**处置建议（不要取平均）**：

- **不要把「管理员能导出全员聊天」当作既定前提去排期。** 若要依赖它，必须**在真实工作区里实测**（owner 账号登录 → 找有无会话访问/导出入口），或向 OpenAI 销售/支持书面确认。
- 上会时应当把这条**单列为「待确认风险」**，而不是写进「能实现」清单。

## 3. 逐项核实

### 3.1 workspace 是什么：账号级容器

- 工作区是账号级的独立环境（有自己的设置、成员、资源）；用户登录时**选择当前会话用哪个工作区**，可在个人工作区与 Business 工作区之间切换，也可以合并。
- 该工作区内的 Chat 与 Codex 记录都归属该工作区。
- **关键区分**：「数据归属工作区」与「成员可见性」是两件事。前者成立，后者默认不成立。

### 3.2 谁能看到会话：Business vs Enterprise

| 能力 | Business | Enterprise / Edu | 依据 |
|------|----------|------------------|------|
| 成员各自的历史 | ✅ 各自可见 | ✅ 各自可见 | A |
| 其他成员看你的聊天 | ❌ 默认不可见 | ❌ 默认不可见 | A |
| 共享单个会话 | ✅ 共享链接（用户主动） | ✅ 共享链接 | A |
| **管理员读取全部会话** | ❌ 产品文档无此入口（隐私页有相反声明，见 §2） | ✅ **Compliance API**（需 Admin key + `Conversation messages` 权限，仅 owner 可授予） | A / 9261474 |
| **数据导出** | ❌ **明确不支持** | ✅ Compliance Logs Platform | A / 9261474 |
| 禁用共享链接（全员） | ❌ 明确没有该开关 | ✅ Enterprise 专属开关 | A |
| 合规日志保留期 | — | **30 天**，要更长须自行持续下载 | 9261474 |

补充：Compliance Logs Platform 为不可变 JSONL、约 10 分钟窗口、p99 < 30 分钟、至少一次投递、`event_id` 去重；日志保留 **30 天**，**过期不可恢复**，需自建持续下载才能长期留存。

### 3.3 Codex 的情况

- 官方原文：**「每个用户有自己的 chat 与 Codex 历史。其他成员不会自动看到这些聊天或 Codex 活动。」** → **Codex 内容同样不共享。**
- 但 Codex **在治理范围内**：`The Codex app follows the same admin controls as Codex local and Codex cloud. Codex local must be enabled for members to use the Codex app.` 管理员可在 工作区设置 → Permissions & roles 控制 Codex 访问。
- Codex 的**使用记录**（含 local CLI / IDE 扩展 / 云端）进 **Compliance API**（Enterprise/Edu）。另有 `Codex Enterprise Analytics`（Enterprise）。
- Codex 的**策略与配置变更**记录在工作区审计日志，管理员可在 Admin Console 查看。
- **未核实**：Codex 本地会话文件在成员机器上的存储位置与生命周期（官方本次核验页面未描述）。

### 3.4 Business 的管理入口在哪里

- **成员与组管理**：Business 的成员/组在 **ChatGPT 里**管理（`Manage Enterprise and Edu workspace members and groups in Admin Console, Business workspace members and groups in ChatGPT`）。
- 全局 Admin Console 的多数能力面向 Enterprise/Edu；工作区审计日志「仅对有资格的 workspace owner 或 admin 开放」，具体检索走 Compliance Platform（Enterprise/Edu）。
- Business 能拿到的是**用量与活动分析**（含 `exportable activity`、Codex 用量、credits），**不是会话正文**。

## 4. 官方支持的「沉淀」路径（这才是能落地的）

### 4.1 共享 Project —— 聊天沉淀的正解

官方原文要点：

- `Business, Enterprise and Edu users can additionally share projects with teammates` → **Business 可用**。
- `ChatGPT can draw from anything in the shared project – including chats, uploaded files and custom instructions` → 共享项目本身就是「活的上下文中心」。
- 权限两级：**Edit**（改 instructions、增删文件、邀请他人）/ **Chat**（可看可聊，不能邀请）。
- Business 可按**个人邮箱、工作区组、工作区链接**邀请；用工作区链接加入的**默认是 chat 权限**，不能对全员默认给 edit。
- 限额：单个工作区项目**最多 100 人**；**Business/Enterprise/Edu 单个项目最多 40 个文件**。

→ **对老板诉求的映射**：所谓「把聊天沉淀下来」，在 Business 下等价于**让成员把有价值的会话留在共享 Project 里**（共享项目内的 chats 对成员可见）。这是**主动协作容器**，不是**后台自动收集**。

### 4.2 Plugin / Skill —— 能力沉淀的正解

这条和我们上一份调研（[workspace-agent-capability-boundary-2026-09.md](workspace-agent-capability-boundary-2026-09.md)）的结论接得上：**Skill/Plugin 是文件形态**，可以进 Git。

- 官方插件结构是**文件系统布局**：`skills/<skill-name>/SKILL.md` + `.codex-plugin/plugin.json` 清单 + 可选 `.mcp.json` / `.app.json`。
- **发布到工作区需要管理员**：`You must be a workspace admin to publish a plugin to your workspace.` 发布时可**指定可访问的工作区角色**。
- 工作区发布的插件**留在工作区与组织边界内**，未登录该工作区的账号访问不到。
- Codex 侧另有 **Plugin sharing**：Business 用户可从 Codex app 把**本地构建的插件**分享给工作区成员，出现在 `Shared with you` 下，且管理员可用 `plugin_sharing = false` 关闭。

→ **这条是「把沉淀变成能力」的官方路径**，而且它的产物是**可进 Git 的目录结构**，不是平台内孤本。

## 5. 对试点计划的建议

1. **修正老板的第一步设想。** 目标从「管理员把所有人聊天记录收上来」改为「**用共享 Project 建 1–2 个团队沉淀点**」，明确谁往里放、放什么。
2. **不要把自动采集写进验收口径。** Business 没有该能力（A 口径）；B 口径的能力声明**无机制支撑且与 A 冲突**，须先实测或书面确认再谈。
3. **合规/审计需求要早说。** 若「聊天留痕」是合规刚需（而非资料整理），那 Business 档位不够——Compliance API 是 Enterprise/Edu 专属，且日志只留 30 天、需自建归档。这是**档位决策**，不是配置决策。
4. **沉淀的产物要落到 Git。** 聊天→共享 Project 是「存」，Project 里的结论要**人工提炼成 `docs/` 或 Skill 文件**才谈得上「变成 skill」。共享 Project 本身不产出 Skill。
5. **成员要知道默认不共享。** 若不明确说清，会出现「以为团队看得到、实际只有自己看得到」的落差；共享链接与共享项目都需要成员主动使用。

## 6. 未核实清单

1. **Business 工作区实际有没有「管理员查看成员会话」入口**——两份官方文档冲突（§2），必须实测。
2. **Business 的「数据保留期」是否真由管理员控制**——隐私页称「管理员可控制保留时长」，但本次未找到 Business 侧的对应设置入口。
3. **Codex 本地会话文件在成员机器上的存储位置与生命周期**。
4. **本地 Codex 的使用记录究竟以何种粒度进入 Compliance API**（是否含会话内容，还是仅元数据/用量）。
5. **共享 Project 内聊天是否可被工作区管理员统一导出**（未找到相应说明）。
6. **「Plugin sharing」在 Business 的实际可用范围**（发布说明为 2026 年条目，需在真实工作区确认）。

## 7. Sources

### OpenAI 帮助中心

- [Managing data, sharing, and privacy in ChatGPT Business](https://help.openai.com/en/articles/8798634-managing-data-sharing-and-privacy-in-chatgpt-business)
- [OpenAI Compliance Platform for Enterprise and Edu customers](https://help.openai.com/en/articles/9261474-compliance-platform-for-enterprise-and-edu)
- [Using Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)
- [Projects in ChatGPT](https://help.openai.com/en/articles/10169521-projects-in-chatgpt)
- [Managing your tenant in Admin Console](https://help.openai.com/en/articles/12289294-managing-your-tenant-in-admin-console)
- [Managing members, seat types, and roles in ChatGPT Business](https://help.openai.com/en/articles/8542216-managing-members-seat-types-and-roles-in-chatgpt-business)
- [ChatGPT Workspace Agents for Enterprise and Business](https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business)
- [ChatGPT Business release notes](https://help.openai.com/en/articles/11391654-chatgpt-business-release-notes)

### OpenAI 官网 / 开发者文档

- [Enterprise privacy at OpenAI](https://openai.com/enterprise-privacy/)（与帮助中心冲突的口径来源）
- [Building Codex plugins](https://developers.openai.com/codex/plugins/build)（`skills/` + `.codex-plugin/plugin.json` 文件布局与工作区发布）

### 本仓库

- [workspace-agent-capability-boundary-2026-09.md](workspace-agent-capability-boundary-2026-09.md) — 姊妹篇，Agent 侧能力边界
- [brief-for-boss.md](brief-for-boss.md) — 对外件（本文**未修改**）
