---
okf: v0.1
type: Research
title: ChatGPT Business 席位、账号与用量模型
description: 买席位到底得到什么、一个账号有几个 workspace、merge 选项、离职交接，以及积分池三层模型、5 小时限制与 Astra/Sol 模型
tags: [ai-pilot, chatgpt-business, seat, workspace, onboarding, offboarding, credits, rate-limits, astra, sol]
timestamp: 2026-09-16
sources:
  - https://help.openai.com/en/articles/8542216-managing-members-seat-types-and-roles-in-chatgpt-business
  - https://help.openai.com/en/articles/8792828-what-is-chatgpt-business
  - https://help.openai.com/en/articles/8801890-managing-workspace-lifecycle-and-migration-in-chatgpt-business
  - https://help.openai.com/en/articles/10479654-onboarding-employees-with-existing-chatgpt-accounts
  - https://help.openai.com/en/articles/9047883-identity-and-access-management-getting-started
  - https://help.openai.com/en/articles/8792536-managing-billing-and-seats-in-chatgpt-business
  - https://help.openai.com/en/articles/20001067-data-access-for-your-managed-chatgpt-account
  - https://help.openai.com/en/articles/20001155-managing-credits-and-spend-controls-in-chatgpt-business
  - https://help.openai.com/en/articles/12003714-chatgpt-business-models-and-limits
  - https://help.openai.com/en/articles/11481834-chatgpt-rate-card
  - https://help.openai.com/en/articles/8542115-chatgpt-business-general-faq
  - https://openai.com/enterprise-privacy/
---

# ChatGPT Business 席位、账号与用量模型

> 调研日期：2026-09-16。为「买 2 个席位，怎么分配」这一组实操问题而写。全部结论来自官方文档，逐条给源。

## 1. 买 2 个席位，你到底得到什么

**得到的不是 2 组用户名密码，而是「一个工作区 + 2 个可分配的名额」。**

流程是**邀请邮箱**制：

1. 公司买下 Business 工作区（最低 2 个付费席位）。
2. 在 工作区设置 → Members → Invite member 邀请**邮箱**（可 CSV 批量）。
3. 被邀请人**接受邀请**时才真正占席位。

官方原文：`Sending an invitation does not purchase or reserve a seat. Seat availability is checked when the invitation is accepted.`

**被邀请人没有 ChatGPT 账号会怎样？**
`New users who do not have ChatGPT accounts will have one created for them as a part of joining the ChatGPT Business workspace.` → **账号自动创建，不需要你先去注册。**

**被邀请人已有个人账号会怎样？**
用**同一个邮箱**接受即可。`One OpenAI account can have separate personal and work ChatGPT workspaces.`
⚠️ **不要另建账号**：`Creating a replacement account or using a different address can make the expected workspace or existing history appear missing.`

### 回答「Business 只是给 2 人用的权限，还是自带 2 个账号？」

准确说法是**两者都不完全对**，三层要分清：

| 层 | 是什么 | 数量 |
|----|--------|------|
| **账号（account）** | 登录凭证，一个人一个 | 每人 1 个（可能原本就有个人账号） |
| **工作区（workspace）** | 数据容器，公司在里面 | 公司 1 个 |
| **席位（seat）** | 付费名额，可分配给一个账号 | 买 2 个 |

→ **Business 不是「给个人账号加权限」，而是「同一个登录账号下多了一个公司工作区」。** 席位决定谁能进这个工作区。

## 2. 一个账号有几个 workspace

- 接受 Business 席位后，**默认有 2 个**：个人工作区 + 公司工作区，可用切换器来回切。
- 官方：`On ChatGPT web, workspaces are available from the profile menu. On mobile, workspaces are available in the sidebar.`
- 若选择**合并**，则**只剩 1 个**：`After the merge is complete, the Personal workspace no longer appears in the account. Only the Business workspace remains.`
- **一个账号最多能拥有几个 workspace：官方未写 → 未核实。**（官方只给了「账号切换器每会话最多 2 个账号」的限制，那是账号数不是工作区数。）

你看到的 **merge 选项**就是这件事：

| | 保留独立 | 合并 |
|---|---|---|
| 结果 | 账号下有 2 个工作区 | 只剩公司工作区 |
| 个人聊天/GPTs | 留在个人工作区 | **迁入公司工作区** |
| 个人插件 | 保留 | **删除**（`Plugins are deleted`） |
| 个人自定义指令 | 保留 | **删除**（`Custom instructions do not migrate`） |
| 可逆性 | — | **不可逆**（`Merging workspaces is permanent and cannot be undone.`） |
| 订阅 | — | 自动取消并退余款（移动端需自行取消） |

另有官方风险提示：`In rare cases, long-running or historical chats may not be retrievable after a merge.`
且**管理员不能强制员工合并**：`ChatGPT Business admins cannot require someone to merge or delete a personal workspace.`

## 3. 离职与席位交接

**不是改密码，也不是「新建账号再转席位」。** 官方流程是：

> **移除成员 → 席位空出 → 邀请新邮箱进该席位。**

- `Removing a member from your workspace makes their seat available for assignment to another member, but it does not automatically reduce the number of paid seats.`
- **席位可复用**；若要少付钱，需在 Manage seats 排定降席位，**下个账期生效**。
- 权限：Owner 可移除任何人；Admin 只能移除比它低的角色。
- 离职者**立即失去访问**：`after you leave a workspace, you cannot access data in that workspace unless you are invited back.`
- 数据留在工作区（Business 数据 `retained indefinitely`），但**Business 无数据导出**。
- **把离职者的私有聊天转给别人：无已文档化的流程 → 未核实。**
- 官方另明确：**转移项目所有权 ≠ 转移私有对话**。`Reassigning a project or GPT doesn't transfer the former member's private conversations or files, and the workspace owner can't view that private content through the ownership change.`

→ **落到 2 席试点的操作**：谁走，就移除他、把他的席位分配给新人的邮箱。**离职者聊过的内容不会自动交给接手的人**，所以关键结论必须**主动沉淀**（写进共享 Project 或 `docs/`），别指望事后从账号里捞。

## 4. Notion 类比

- **账号** ≈ Notion 账号（登录）。
- **工作区** ≈ Notion 的 workspace：一个人可以同时属于多个，用切换器切换。
- **席位** ≈ Notion 的付费 member 名额：由 owner 购买、分配、**可回收再分配给别人**。

**两处关键差异**：
1. Notion **没有「合并」这个概念**；OpenAI 的个人→公司合并**不可逆且会删插件与自定义指令**，要慎重。
2. Notion 页面按共享设置可见；**OpenAI 的成员私聊默认对管理员不可见**（这一点见 §6 但注意那里有冲突）。

## 5. 用量模型：三层 + 5 小时限制

### 5.1 三层是**严格串行**的

1. **每席位内含用量（included usage）**——绑在付费席位上：`Included usage is evaluated for the paid ChatGPT seat assigned to each member.`
2. **工作区共享积分池（workspace credit pool）**——工作区级共享余额，**不是每席位独立**：`Credits can be used across all seat types, after included usage is exhausted.` / `Changing a member's paid seat type can change included usage, but it does not create a separate credit pool.`
3. **购买的 credits**——就是往 (2) 这个池子充值，12 个月有效。

扣费顺序：`Standard and Premium seats use their included allowance before eligible activity draws from workspace credits.`

**共享范围（对 2 席工作区的含义）**：`Codex, ChatGPT Work, ChatGPT for Excel, and Workspace Agents use a shared allowance and credit pool.`
→ **两个席位各有独立内含额度，但只有一个共享池**；任一席位超限就开始吃同一个池。**常规 Chat 单独计量**（`Chat usage is metered separately from Astra usage in Work and Codex`）。

### 5.2 「5 小时限制」到底是什么

- 它是**滚动时间窗内的用量额度，不是消息条数硬上限**。官方：`These estimates are not fixed message limits`、`a fixed number of messages is not a reliable measure of remaining usage`。也**存在每周限制**（`Weekly limits may also apply`）。
- **Standard Business 席位 = Plus 同档，有 5 小时窗。**
- **Premium 席位没有 5 小时限制**——这是官方明确的差异点：`Premium includes 5x more usage than Standard seats, no 5-hour usage limit.`

### 5.3 买 credits 能不能解决「上班 8 小时只能跑 2 波」？

**部分能，但不解决 5 小时窗本身。**

- 官方确认 credits 可以**延续超出内含额度的用量**：`purchase workspace credits that extend usage beyond the included rate limits`；`If you reach an included limit, eligible usage can continue with purchased workspace credits when credits are available and your workspace's spending controls allow it. Otherwise, wait for the applicable allowance to reset.`
- **但「credits 直接重置/豁免 5 小时滚动窗」这句话官方没有明说 → 未核实。**
- **官方给出的「消除 5 小时窗」手段是换 Premium 席位，而不是买 credits。**

→ **如果试点重度依赖 Astra/Sol 且要连续 8 小时用，正解是把关键席位换成 Premium（$100–125/席位/月），而不是靠 credits 硬扛。**

### 5.4 用尽之后会发生什么

**是被阻断，不是降级、也不是自动超支计费**：
`Users see a banner when their included usage is exhausted. If no credits are available in the workspace pool, the feature is blocked and users can ask a workspace owner to add more.`
（系统自动路由到 mini 模型的那部分不计 credits。）

管理员可对 Standard/Premium **分别设月度 credit 上限**，并支持 per-user override；`By default, all seats and users have no limits specified.` → **默认无闸，需要主动设。**

**每席位内含额度的具体数值：官方未发布。** 官方解释：`There is no single credit or dollar equivalent`（因为消耗取决于模型与任务）。**credits 的美元单价也未公布。**

### 5.5 Astra 与 Sol 是真实存在的模型

| 模型 | 定位 | credits / 1M tokens（输入 / 缓存 / 输出） |
|------|------|------|
| **GPT-6 Astra** | 最强推理；Chat 里经 **GPT-6 Pro** 入口调用（`GPT-6 Pro is powered by GPT-6 Astra.`） | 250 / 25 / 1,250 |
| **GPT-5.6 Sol** | `built for the hardest work—complex reasoning, ambiguous problems, advanced coding, and high-stakes decisions` | 100 / 10 / 500 |
| Terra | 日常主力 | 50 / 5 / 300 |
| Luna | 高频轻量 | 5 / 0.5 / 30 |

**席位差异**：`Standard seats include limited Astra usage within their existing Work and Codex allowance. Premium seats can use their full existing allowance for Astra.`

## 6. ⚠️ 对上一份调研的重要修正：新增第三个冲突来源

v2 里我报告了两份官方文档在「Business 管理员能否看成员会话」上冲突。本次又找到**第三处**，且它**明列 Business**：

**《Data access for your managed ChatGPT account》(20001067)**：管理员 `may be able to access, export, audit, retain, delete and opt-in to share data tied to this account`，数据范围含 **`Conversation history and shared workspace content`**——但带限定语 **`where enabled by your organization's configuration and applicable law`**。

三处证据现状：

| 来源 | 性质 | 说法 |
|------|------|------|
| 帮助中心 8798634 / 11509118 + 定价对比页 | **产品能力文档** | 管理员**不能**看成员会话；Business 的 `Compliance API Logs Platform` = **No** |
| Enterprise Privacy 页（Business FAQ） | **法务/承诺页** | 管理员**可以**查看、访问、导出、删除 |
| Managed Account Notice 20001067 | **法务/承诺页** | 管理员**可能可以**访问、导出、审计、保留、删除（含会话历史），**若组织配置与法律允许** |

**结论（不取平均）**：
- **产品文档说「不会自动可见」，法务文档说「有权利」——两者层级不同，后者带「where enabled」的限定语。**
- **Business 后台是否真的有可点的「查看成员会话」入口：官方文档未描述 → 未核实。**
- **行动项：采购前把这个问题书面提给 OpenAI 销售/支持，拿到明确答复再决定。** 不要靠推测排期。

## 7. 未核实清单

1. **不主动选择时默认激活哪个工作区。**
2. **一个账号最多能拥有几个 workspace。**
3. Business 后台**是否存在**管理员查看/导出成员会话的实际入口（§6 三方冲突）。
4. credits 是否**豁免/重置 5 小时滚动窗**（官方只说「延续超出内含额度的用量」）。
5. 每席位内含额度的数值、credits 的美元单价（官方均未公布）。
6. 离职者私有聊天的转移流程。

## 8. Sources

- [Managing members, seat types, and roles in ChatGPT Business](https://help.openai.com/en/articles/8542216-managing-members-seat-types-and-roles-in-chatgpt-business)
- [What is ChatGPT Business](https://help.openai.com/en/articles/8792828-what-is-chatgpt-business)
- [Managing workspace lifecycle and migration in ChatGPT Business](https://help.openai.com/en/articles/8801890-managing-workspace-lifecycle-and-migration-in-chatgpt-business)
- [Onboarding employees with existing ChatGPT accounts](https://help.openai.com/en/articles/10479654-onboarding-employees-with-existing-chatgpt-accounts)
- [Identity and access management getting started](https://help.openai.com/en/articles/9047883-identity-and-access-management-getting-started)
- [Managing billing and seats in ChatGPT Business](https://help.openai.com/en/articles/8792536-managing-billing-and-seats-in-chatgpt-business)
- [Data access for your managed ChatGPT account](https://help.openai.com/en/articles/20001067-data-access-for-your-managed-chatgpt-account)
- [Managing credits and spend controls in ChatGPT Business](https://help.openai.com/en/articles/20001155-managing-credits-and-spend-controls-in-chatgpt-business)
- [ChatGPT Business models and limits](https://help.openai.com/en/articles/12003714-chatgpt-business-models-and-limits)
- [ChatGPT rate card](https://help.openai.com/en/articles/11481834-chatgpt-rate-card)
- [ChatGPT Business general FAQ](https://help.openai.com/en/articles/8542115-chatgpt-business-general-faq)
- [Enterprise privacy at OpenAI](https://openai.com/enterprise-privacy/)
