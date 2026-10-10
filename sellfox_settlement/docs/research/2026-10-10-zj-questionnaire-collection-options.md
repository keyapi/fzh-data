---
okf: v0.1
type: Research
title: 让财务 ZJ 填写问卷的渠道选型（Notion / 自建局域网 / Google）
description: 调研让财务 ZJ 填写 Amazon 报税问卷的可行渠道：Notion 公开页与表单、自建局域网表单、Google 表单/表格、钉钉，比较权限、隐私、可回读与维护成本并给出建议
tags: [sellfox, amazon, tax, questionnaire, notion, form, workflow]
timestamp: 2026-10-10
last_updated: 2026-10-10
resource: sellfox_settlement/docs/research/2026-10-09-amazon-non-v2-monthly-tax-analysis.md
---

# 让财务 ZJ 填写问卷的渠道选型

## 1. 问题

底稿 [2026-10-09-amazon-non-v2-monthly-tax-analysis.md](2026-10-09-amazon-non-v2-monthly-tax-analysis.md) 第 2 节是给财务负责人 ZJ 的填写清单（F01—F20 等）。问题是：**能不能做一个局域网可访问的网页让她填？或者放到 Notion 上对外公开让她填？**

先给结论（第 2 节展开依据）：

- **"Notion 公开页 + 允许编辑"不推荐**——它要么需要登录、要么把**敏感的公司/银行/税口径**暴露在公开链接上，且被明确警告有 prompt-injection 风险。
- **自建局域网表单可行但最重**：要服务器 + 数据库 + 长期维护；主流建议是"非技术团队别自建"。
- **最贴合现状的是 Google 表单 → Google 表格**：本仓库已有 Google 服务账号和 `gsheets` 读取能力，ZJ 也会用表格，AI 可直接读回。
- **如果 ZJ 愿意用 AI 工具，则不需要任何新系统**——继续用 Git 里的 MD + PR（本仓库既定流程）。
- **Notion 若要用于填写，走"访客邀请 + 可编辑"单页**，而不是"对外公开"。

## 2. Notion 的三条路（容易混，分开看）

Notion 有**三种互不相同**的机制，很多人把它们当成一回事：

### 2.1 公开页 + "允许编辑"（Publish to web / 允许编辑）

- 公开链接**任何人不用账号就能看**；但要**编辑或评论必须登录 Notion 账号**（官方帮助原文：page visitors will need to be logged into Notion if they want to comment on or edit your page）。
- "允许编辑"一旦打开，**任何有 Notion 账号的人拿到链接都能改**。第三方指南明确警告：在启用了 AI Agent 的工作区里，这会造成 **prompt-injection 风险**，并建议"永远不要开"。
- 对本项目：问卷含**法人归属、收款主体、出口主体、关联交易、税务口径**，属于敏感信息。把它放在公开可编辑链接上**不可接受**。

来源：<https://www.notion.com/help/share-your-work>、<https://www.notion.com/help/sharing-and-permissions>、<https://thomasjfrank.com/notion-sharing-permissions-the-ultimate-guide>

### 2.2 访客邀请 + "可编辑"（Guest invite）

- 把 ZJ 的邮箱作为 **Guest** 邀请到**单个页面**，权限选 `Can edit`。她**只看到被分享的那一页**，看不到工作区其他内容。
- 需要她**注册一个免费 Notion 账号**并接受邮件邀请（首次会有通知）。
- Guest 免费，但每个套餐有 guest 数量上限。
- 这是"让 ZJ 直接编辑 Notion 文档"的**安全做法**，但她是编辑一整套长表格，Notion 里填长表不如表格软件顺手。

来源：<https://www.notion.com/help/add-members-admins-guests-and-groups>

### 2.3 Notion 原生表单（Forms）

- 建一个表单，分享设置选 `Anyone on the web with link` → **非 Notion 用户、无账号也能提交**；回答落到一个 **Notion 数据库**里（一行一条）。
- **关键限制**（直接决定它是否适合）：
  - 公开表单的回答**一律记为匿名**（`Respondent` 显示 Anonymous），**分不清是谁填的**。
  - "让回答者能编辑自己的提交（Access to submission: Can edit）"**只对内部表单有效，公开表单不支持**——即"填完还想改"做不到。
  - 官方称条件逻辑"coming soon"，且无非技术向的高级校验、文件、防刷。
- 它能被程序读回：本机 Notion MCP 的 `query_data_sources` 可用（`query_multiple_data_sources` 需更高套餐），可用于把回答抓回 Git。
- 数据库上限：1 万行 / 50 列；页面 1000 block。

来源：<https://www.notion.com/help/forms>、<https://www.notion.com/help/guides/use-forms-to-collect-organize-and-act-on-responses-in-notion>、<https://www.notion.com/product/forms>、<https://matthiasfrank.de/en/notion-updates/give-respondents-access-to-their-notion-forms-submission>

## 3. 自建局域网表单

- 可选开源方案：**OpnForm**（通用、无代码，但小团队 bus-factor 需权衡）、**HeyForm**（AGPL-3.0、UI 现代）、**Formbricks**（面向产品内调研，栈重：Postgres+Redis/Valkey+Cube，重度过杀）、**Typebot**（对话式，FSL 许可）、**LimeSurvey**（逻辑强但陈旧）、**Budibase**（自带库+表单）、**SurveyJS**（组件库，需开发者授权）。
- 它们都要**服务器 + 数据库 + 升级维护**，且多份评测都提醒：**非技术团队不宜自建**。
- "局域网"另有一个现实约束：**只有 ZJ 在办公室/VPN 内才够得着**。如果她在家或外出，Notion / Google 才随处可用。

来源：<https://fomr.io/blog/best-open-source-form-builders>、<https://extendedforms.io/blog/7-best-open-source-form-builders-in-2026-self-hosted>、<https://budibase.com/blog/open-source-form-builder>

## 4. Google 表单 → Google 表格（与本仓库最契合）

- **Google 表单**：表单/问题/回答数不限，回答**自动汇入一个 Google 表格**；17 模板、11 种题型、基础跳转逻辑。
- 已能程序读回：本仓库已有 Google 服务账号（`secrets/gsheets-service-account.json`）与 `tongtool_order_cost.gsheets` 读取器；读一个 Sheet 是**现成能力**，不用新建任何服务。
- ZJ 很可能**本就在用 Google 表格**（渠道账号表、汇率表都在这套体系里），学习成本最低。
- 注意：Google 把回答数据存在**美国基础设施**（合规上要知晓）。

来源：<https://www.smartsurvey.co.uk/blog/top-8-alternatives-to-google-forms-paid-and-free>、<https://www.sheetgo.com/blog/google-sheets-features/how-to-connect-google-forms-to-google-sheets>、<https://developers.google.com/sheets/api/overview>

## 5. 钉钉（候选，未深入验证）

公司已在用钉钉（仓库有 `dingtalk/dingtalk_oa_approval/` 与钉钉机器人）。钉钉表单/审批是**实名内部**工具，天然契合国内公司，但本次**未深入调研其表单能力与 API 读回**，如需采用应先单独验证。

## 6. 对比与建议

| 方案 | ZJ 需要账号 | 隐私 | AI 读回 | 维护成本 | 备注 |
|---|---|---|---|---|---|
| **Git MD + PR（现状）** | 无（用 AI 工具） | 最高（私有仓） | 天然，就是源 | 无新增 | 前提是她肯用 AI 工具 |
| **Google 表单 → 表格** | Google 账号 | 中（美国存储） | 现成（gsheets SA） | 低 | **最贴合现状** |
| Notion **访客可编辑**单页 | 需注册 Notion | 高（限定单页） | 可（MCP） | 低 | Notion 里填长表不顺手 |
| Notion **公开表单 → 数据库** | 不需要 | **公开链接+匿名** | 可（MCP） | 低 | 匿名、不能改自己的回答 |
| Notion **公开页+允许编辑** | 需登录 | **差（公开可编辑）** | 可 | 低 | **不推荐**，有注入风险 |
| **自建局域网表单** | 不需要 | 最高（本地） | 需自写抓取 | **高** | 仅当必须数据不出门 |

**建议（按优先级）**：

1. **若 ZJ 会用 AI 工具** → 就用 Git 里的 MD（已设计好），**不引入任何新系统**。
2. **若她想要熟人 UI** → **Google 表单 → Google 表格**：她填表，AI 用现成 SA 把回答读回并入 Git。
3. Notion 党 → **访客邀请单页（可编辑）**，**不要**用公开页+允许编辑，也不要用公开表单（匿名+不可改）。
4. **只有当"数据一个字都不能离开内网"时**才上自建（OpnForm/HeyForm 之类），并接受长期维护与"仅内网可达"的限制。

**共同前提**：无论走哪条，**Git 仍是唯一事实源**；外部工具只做"回答通道"，回答再由 AI 合并回 MD。

## 7. 待用户决定

1. 优先走哪条：Git MD / Google 表单 / Notion 访客单页 / 自建？
2. ZJ 是否愿意用 AI 工具（决定第 1 条是否可行）？
3. 问卷内容是否允许离开内网（决定自建是否必需）？

## 8. 原始来源

- Notion 分享页面（General access / 需登录才能编辑）：<https://www.notion.com/help/share-your-work>
- Notion 分享与权限（各访问级别 / 企业可禁用公开链接）：<https://www.notion.com/help/sharing-and-permissions>
- Thomas Frank《Notion Sharing & Permissions》（公开页 Can Edit 的 prompt-injection 警告）：<https://thomasjfrank.com/notion-sharing-permissions-the-ultimate-guide>
- Notion 成员/管理员/访客：<https://www.notion.com/help/add-members-admins-guests-and-groups>
- Notion 表单（对外公开、匿名、Access to submission）：<https://www.notion.com/help/forms>
- Notion 表单使用指南：<https://www.notion.com/help/guides/use-forms-to-collect-organize-and-act-on-responses-in-notion>
- Notion Forms 产品页：<https://www.notion.com/product/forms>
- 让回答者编辑自己的提交（仅限内部表单）：<https://matthiasfrank.de/en/notion-updates/give-respondents-access-to-their-notion-forms-submission>
- Notion 数据库上限：<https://ones.com/blog/maximizing-efficiency-notion-database-limits-workarounds>
- 自建表单开源方案（2026）：<https://fomr.io/blog/best-open-source-form-builders>
- 自建表单开源方案（2026，含维护性提醒）：<https://extendedforms.io/blog/7-best-open-source-form-builders-in-2026-self-hosted>
- Budibase 开源表单对比：<https://budibase.com/blog/open-source-form-builder>
- Google 表单能力与限制：<https://www.smartsurvey.co.uk/blog/top-8-alternatives-to-google-forms-paid-and-free>
- Google 表单连接 Google 表格：<https://www.sheetgo.com/blog/google-sheets-features/how-to-connect-google-forms-to-google-sheets>
- Google Sheets API：<https://developers.google.com/sheets/api/overview>

> 外部链接与各平台权限规则会变动，落地前请按当前版本复核。
