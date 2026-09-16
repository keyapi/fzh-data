---
okf: v0.1
type: Research
title: "Pro 消息 15 条/月" 到底指什么 + 个人账号能不能共享 Project
description: Standard 席位 15 条 Pro 消息的定义、月度与 5 小时窗的区别、用尽后的降级/阻断/积分三条路径，以及与 Plus/Pro 个人档的对齐；个人 Free/Go/Plus/Pro 共享 Project 的人数上限、跨账号邀请规则与账号共享条款红线
tags: [ai-pilot, chatgpt-business, pro-messages, projects, sharing, terms-of-use, governance]
timestamp: 2026-09-16
sources:
  - https://help.openai.com/en/articles/12003714-chatgpt-business-models-and-limits
  - https://help.openai.com/en/articles/20001354-gpt-56-and-gpt-6-pro-in-chatgpt
  - https://help.openai.com/en/articles/11481834-chatgpt-rate-card
  - https://help.openai.com/en/articles/11487671-flexible-pricing-for-the-enterprise-edu-and-business-plans
  - https://help.openai.com/en/articles/10169521-projects-in-chatgpt
  - https://help.openai.com/en/articles/9793128-about-chatgpt-pro-tiers
  - https://help.openai.com/en/articles/8792828-what-is-chatgpt-business
  - https://help.openai.com/en/articles/8542115-chatgpt-business-general-faq
  - https://chatgpt.com/pricing
  - https://openai.com/policies/terms-of-use/
  - https://openai.com/policies/services-agreement/
---

# 「Pro 消息 15 条/月」与个人账号共享 Project

> 调研日期：2026-09-16。为两组实操问题而写：① Business Standard 席位的「15 Pro messages/month」到底怎么算；② 能不能用个人账号（尤其个人 Pro）共享 Project 给小组用，替代 Business。
> 方法：`help.openai.com` 对自动化抓取返回 403，改用 reader 代理按原 URL 读正文。所有引文为原文英文。

---

## 第一部分：15 条 Pro 消息到底指什么

### 1.1 「Pro」是模型档位，不是席位名

官方在《ChatGPT Business models and limits》里专门写了一句防混淆：

> `Note that **Pro** is a model option, not another name for a Premium seat.`

模型选择器里的 **Pro** 档：`Uses GPT-5.6 Sol Pro or GPT-6 Pro.`

### 1.2 15 条计的是模型，不是功能

> `Business Standard includes 15 Pro messages per month, shared across GPT-6 Pro and GPT-5.6 Sol Pro. Business Premium includes 50 Pro messages per week, shared across the two models. Switching between them does not increase or reset that shared allowance.`

三个要点：
- **共用一份额度**：GPT-6 Pro 和 GPT-5.6 Sol Pro 同吃 15 条；换模型**既不重置也不增加**。
- **一条消息 = 一问一答**：rate card 明确 `One prompt and response form a single message.`
- **只管常规 Chat**：`These Chat allowances are separate from usage in Work and Codex.`

### 1.3 月度额度 vs 5 小时窗 —— 两套完全独立的系统

用户的两处困惑，正确答案是**两个都存在，但作用域不同**：

| | Chat 的 Pro 额度 | Work / Codex 的 5 小时窗 |
|---|---|---|
| 单位 | 固定条数 | 用量估算（非硬上限） |
| 周期 | **月度**（Standard） | **每 5 小时**滚动窗 |
| 对象 | Chat 里的 Pro 档消息 | Work/Codex 的**本地**消息 |
| 官方数字 | 15 条/月 | Astra 5–45、Sol 10–100、Terra 25–200、Luna 250–2,000 |

5 小时窗表的原文标题是 `Local-message estimates by seat type`，官方同时警告：`These estimates are not fixed message limits`、`a fixed number of messages is not a reliable measure of remaining usage`。

→ **不要把 15 和「5 小时」混为一谈**：15 是 Chat 的 Pro 消息月配额，与 5 小时窗无关。

### 1.4 用尽之后：不是降级，是「Pro 档不可选 + 三条出路」

官方**没有**为 Business Standard 写自动降级。可考的是《Flexible pricing》对 Business 的通用规则：

> `Business: Users see a banner when their included usage is exhausted. If no credits are available in the workspace pool, the feature is blocked and users can ask a workspace owner to add more.`

三条出路：
1. **走工作区 credits**（把额度接上）：rate card 给 Chat 模型定了每消息费率——`GPT-6 Pro | 1 message | 50 credits`、`GPT-5.6 Sol Pro | 1 message | 50 credits`。
2. **换模型**：GPT-5.6 Sol 的 Instant/Medium/High/Extra High 仍在（`Instant | 1 message | N/A — Unlimited`、Sol 10 credits/条）。
3. **等重置**：`wait for the applicable allowance to reset`。

⚠️ 官方**只对 Pro $200 个人档**写了自动降级：`On Pro $200, when you reach your GPT-6 Pro weekly limit, ChatGPT automatically switches to GPT-5.6 Thinking at Medium.` **Business Standard 是否会自动降级，官方未写 → 未核实。**

### 1.5 与个人档逐项对比（官方原表）

| 套餐 | Chat 里 GPT-6 Pro 额度 | GPT-5.6 Sol Pro 如何共用 |
|---|---|---|
| **Plus** | **无**（`Not included`） | 无 |
| Pro $100 | 50 条/**周** | 与 GPT-6 Pro 共用同一份 50 条/周 |
| Pro $200 | 200 条/**周** | Sol Pro 另有 170 条/天；两模型合计再限 200 条/天 |
| **Business Standard** | **15 条/月** | 共用同一份 15 条/月 |
| Business Premium | 50 条/**周** | 共用同一份 50 条/周 |

补充（定价对比页）：`GPT-5.6 Sol Pro` 一行为 **Plus `No` / Pro `Yes`**——**Plus 完全没有 Pro 档消息**。

**换算**：Business Standard 的 15 条/月 ≈ **3.5 条/周**。

### 1.6 15 条/月，一个团队现实中能干什么

把 15 条理解成**「每月 15 次『压箱底』的求助」**：

- 若 5 个人共用一个 Standard 席位 → 全队一个月 15 条 → **平均每人每月 3 条**，约每 10 天一次。
- 适合的用法：**低频、单次高价值**的硬骨头——一份复杂合同的条款推演、一次数据模型口径的反复推敲、一篇难写文案的定稿。
- **不适合**：日常排期、写 Listing、查资料、跑脚本。这些走 GPT-5.6 Sol（Instant/Medium/High），Standard 席位基本够用且不计入这 15 条。
- 实操建议：把 Pro 档当**稀缺资源**管理——事先约定「什么级别的难题才动 Pro」，并注意它是**月**度重置（月初归零），不是按周。

---

## 第二部分：个人账号能不能共享 Project

### 2.1 哪些套餐能共享 Project —— 已确认：全部都能

《Projects in ChatGPT》原文：

> `ChatGPT Free, Plus, Pro, and Go users can invite individuals by using the **Only those** setting in the sharing pane. ChatGPT Business, Enterprise, and Edu users can invite individuals or workspace groups.`

同文开头的更新说明：

> `Update as of October 22, 2025: project sharing is available to all ChatGPT users, including for Free, Plus, Pro, and Go users globally on web, iOS, and Android.`

定价对比页佐证：`Shared projects` 一行为 Free / Go / Plus / Pro **全部 Yes**。

⚠️ **发现一处同页自相矛盾**：同一篇文章的「Getting started with sharing」小节仍留着旧句 `You can only invite members within your workspace.`。这句与上面「Free/Plus/Pro/Go 可用 Only those 邀请个人」及「任何人凭链接可加入」**直接冲突**，判为 2025-10 放开前的残留文本（同段的 `Shared projects include a 4-week early access period until October 23, 2025` 也显示该段未更新）。

### 2.2 人数 / 文件上限 —— 用户的数字全部核实无误

官方 `Collaboration Limits` 原文逐条：

> - `Pro users: up to 40 files and 100 collaborators`
> - `Plus and Go users: up to 25 files and 10 collaborators`
> - `Free users: up to 5 files and 5 collaborators`

另有 `Plans and limits` 一节的每项目文件上限：Free 5 / Go·Plus 25 / **Edu·Pro·Business·Enterprise 40**。
项目数量无上限：`Users can create an unlimited amount of projects.`
Business/Enterprise/Edu 的**单项目**上限同为 100 人 / 40 文件。

→ **注意**：个人 **Pro 的协作数字（100 人 / 40 文件）与 Business 完全一致**。

### 2.3 跨账号共享 —— 可以，且不限同一 workspace

官方原文（`Inviting by a shared link`）：

> `If set to "Anyone with a link," any logged-in ChatGPT user who has the link can join the shared project.`

`any logged-in ChatGPT user` 是明确措辞——**不限于同工作区、不限于同套餐**。个人账号之间互邀（A 的 Plus 邀 B 的 Pro/Free）可行；两条路径：① `Only those` 按**邮箱**逐个邀请；② `Anyone with a link` 任何人凭链接加入。
另：邀请后双方收确认邮件：`both you and the invitee will receive an automated email confirming the invitation.`
权限两级：`Edit`（可改指令、传删文件、邀请他人）与 `Chat`（只能看和互动）。

### 2.4 全队共用一个个人 Pro 账号 —— 明确违规

三条独立条款，**没有解释空间**：

- **Terms of Use**（个人条款）：`You may not share your account credentials or make your account available to anyone else and are responsible for all activities that occur under your account.`
- **Services Agreement**（Business Terms）**3.1**：`Customer will not share Account access credentials or individual login credentials between multiple users.` `Customer may not resell or lease access to its Account or any End User Account.`
- **Services Agreement 3.2**：`End User Accounts may only be provisioned to, registered for, and used by, a single End User.`

帮助中心的后果提示：`Sharing your account credentials or making your account available to anyone else.` 列在被禁止行为中，且 `may occasionally involve a temporary restriction on your usage`。

→ **结论：不可行，不得采用。** 除条款风险外，实操上也无法交接（MFA 绑在个人手机、邮箱可自助改回密码），且会连带暴露持有者的个人工作区（详见 `business-seat-account-and-usage-2026-09.md` §3）。

### 2.5 现实做法：每人各自个人账号 + 互邀共享 Project

**技术上完全可行**（§2.3），且是「个人账号路线」唯一合规姿势。但代价明显：

| 维度 | 个人账号路线 | Business |
|---|---|---|
| 计费 | 各人自付，公司无法统一开票 | 公司统一账单，$25/月 或 $20/月（年付）/席位 |
| 账号归属 | 归个人，**离职即带不走** | 席位可回收再分配给继任者 |
| 管理台 / RBAC | **无** | 有（Owner/Admin/Analytics viewer/Member） |
| 用量可见性 | **无** | 有 usage 分析 + 支出控制（credit maximum、per-user override） |
| 数据训练 | `we may use information accessed from projects to train our models if your "Improve the model for everyone" setting is on` | `OpenAI won't train on your workspace's data.` |
| 合规审计 | **无**（需 Enterprise 才有 Compliance API） | 基础留存/驻留继承；完整审计仍需 Enterprise |
| 共享 Project 上限 | Pro 100 人 / 40 文件（与 Business 相同） | 100 人 / 40 文件 |
| 席位下限 | 无 | **最低 2 个付费席位** |

**核心治理缺口**：个人路线**没有管理员视角**——不知道谁在用、用了多少、有没有人把公司数据放进个人项目；也无法在离职时收回任何东西。而 Business 的共享项目**强制 project-only memory**（`Shared projects are automatically set to project-only memory`），个人路线则默认走各人自己的记忆与上下文。

→ **判断**：个人 Pro 路线在「共享能力」上与 Business **等价**，但在**归属、管理、合规、离职交接**四个维度上**全面缺失**。仅适合「临时、低敏感、人员稳定」的小组协作，不适合作为公司试点的承载方案。

---

## 未核实清单

1. **Business Standard 的 15 条 Pro 消息用尽后，Chat 是否自动降级到较弱模型**（官方只对 Pro $200 个人档写了自动降级）。
2. **「走 credits 续 Pro 消息」是否适用于 Chat**：rate card 给了 GPT-6 Pro 的 50 credits/**Chat message** 费率，Flexible pricing 也写了「用尽后 feature is blocked（若无 credits）」，但**没有一句话明说 Chat 的 15 条允许用量可由 credits 延续**。
3. **Plus / Go 的美元月费**：定价页因地区/货币识别，价格数字未在页面文本中渲染（Pro 档名称本身即含 $100 / $200）。Plus = $20/月 来自二手来源。
4. 个人 Pro 共享 Project 时，**owner 是否能看到成员把项目内对话移出/删除**（《Projects》只说明成员可移出、删除后他人不可见）。

## Sources

- [ChatGPT Business models and limits (12003714)](https://help.openai.com/en/articles/12003714-chatgpt-business-models-and-limits)
- [GPT-5.6 and GPT-6 Pro in ChatGPT (20001354)](https://help.openai.com/en/articles/20001354-gpt-56-and-gpt-6-pro-in-chatgpt)
- [ChatGPT Rate Card (11481834)](https://help.openai.com/en/articles/11481834-chatgpt-rate-card)
- [Flexible pricing for Enterprise, Edu, and Business (11487671)](https://help.openai.com/en/articles/11487671-flexible-pricing-for-the-enterprise-edu-and-business-plans)
- [Projects in ChatGPT (10169521)](https://help.openai.com/en/articles/10169521-projects-in-chatgpt)
- [About ChatGPT Pro tiers (9793128)](https://help.openai.com/en/articles/9793128-about-chatgpt-pro-tiers)
- [What is ChatGPT Business (8792828)](https://help.openai.com/en/articles/8792828-what-is-chatgpt-business)
- [ChatGPT Business: General FAQ (8542115)](https://help.openai.com/en/articles/8542115-chatgpt-business-general-faq)
- [ChatGPT pricing](https://chatgpt.com/pricing)
- [OpenAI Terms of Use](https://openai.com/policies/terms-of-use/)
- [OpenAI Services Agreement](https://openai.com/policies/services-agreement/)
- 二手（价格佐证，未作主要依据）：[ChatGPT GPT-5.6 Pricing 2026](https://www.aipricing.guru/chatgpt-subscription-pricing/)
