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
- **Notion 若要用于填写，走"访客邀请 + 可编辑"单页**，而不是"对外公开"。该路**已核实可行**：完整 MD 可导入成页面、简单表格能转、ZJ 用 Google/微软账号免费登录、免费版 10 个访客够用；但**填 9 列大表较别扭**（建议填区改数据库），且**国内访问不稳定、需翻墙兜底**，**MCP 不能替你发访客邀请**（须在界面手动分享）。详见 2.4。

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

### 2.4 直接把Notion 访客单页用起来的可行性（重点核实）

针对"**能不能把一个完整 MD 文档发到 Notion 让 ZJ 填**"，逐条核实：

**① 能不能放完整文档？能。** 用 Notion 的 **`Settings → Import → Text & Markdown`（拖入 `.md` 文件）**导入，整个文档变成一个页面。比"复制粘贴"可靠得多（粘贴对复杂表格/代码块容易出错）。

**② 表格会不会坏？大体可以。** 官方与多篇指南都指出：**简单 GFM 表格能转**，但 Notion 对表格格式很挑（分隔行必须规范），且**不支持列对齐、单元格内换行、合并单元格**；复杂表格会降级，导入后**通常需要少量手工清理**。此外 HTML 会被丢弃、脚注不支持、GitHub 式 `> [!NOTE]` 会退化成普通引用块。
- 对底稿的影响：第 2.2 节那张 **9 列大表**（编号/主题/建议/答复/证据/主体/期间/状态/备注）在 Notion 里填起来**很别扭**。更顺的是把它做成 **Notion 数据库**（一行一个问题，属性当列），填充体验远好于长表——但那样就不是纯 MD 了。

**③ 能不能"填写提交"？能填，但不是"提交表单"。** 给 ZJ 的访客页面开 `Can edit`，她就能**直接在被分享的页面上编辑表格单元格**——这是"协作编辑"，不是"提交"。若非要"提交式"体验，只能走 2.3 的 Notion 表单，但那是**结构化行 + 公开即匿名**，放不下完整文档。**「完整文档 + 可填写」= 访客可编辑单页**。

**④ 账号怎么来？Google/Apple/Microsoft 登录都行。** Notion 官方登录方式含 `Continue with Google`、`Continue with Apple`、**`Continue with Microsoft`**、Passkey、邮箱验证码。ZJ 有 Google 账号即可直接注册登录（前提是能翻墙）。

**⑤ 免费版够不够？够。** 免费的 Free 计划允许 **10 个访客**；付费版（2026 起）访客不限。只给 ZJ 一人用绰绰有余。

**⑥ 国内能访问吗？不稳，需要翻墙兜底。** GreatFire 实测 `notion.so` 为 **Mixed**（24 个被测地址里 6 blocked / 1 accessible），主页当前"未封锁"但会在不同时段失效；另有实测显示可从阿里云国内节点打开但慢（首字节约 1.5s、首屏约 3.5s）。**结论：Notion 在国内时好时坏，不能假设一定通**。既然 ZJ 用 Google 本就要翻墙，Notion 一并走翻墙即可——但这也说明"跨墙依赖"是这个方案绕不开的前提。

**⑦ 本项目 MCP 能做/不能做什么（重要）。** 本机 Notion MCP 有 `create_pages`、`update_page`、`fetch`、`query_data_sources` 等，**能建/读页面内容**；但**没有任何"分享/邀请访客"的工具**——所以：**页面内容可由 AI 建/改，但"邀请 ZJ 为访客并给可编辑权限"必须在 Notion 界面里手动做**。另需注意：由集成（bot）创建的页面归属集成，直接分享给人类访客可能要多一步；**更稳妥的是你自己在 Notion App 里手动导入 `.md` 建页，再分享给 ZJ**。

**⑧ 隐私**：Notion 是境外云（数据出境）；页面内容含法人/银行/税务口径，**只可私享给 ZJ 这一个访客，绝不能发布公开链接**。

**推荐落地流程**：

1. AI 产出一份**导入友好的填充版 MD**（保留完整正文；把要填的部分整理成好填的表格或数据库结构）。
2. **你**在 Notion App 里 `Import → Text & Markdown` 导入成页面（比 MCP 建页更稳，页归你所有）。
3. **你**在该页 `Share` 里把 ZJ 邮箱加为 **Guest、权限 `Can edit`**（免费版够用）。
4. ZJ 用 Google 账号登录后直接填写。
5. AI 用 MCP `fetch` 把该页内容读回，合并进 Git（Git 仍是唯一事实源）。

来源：<https://www.notion.com/help/log-in-and-out>、<https://www.notion.com/help/import-data-into-notion>、<https://blog.markdowntools.com/posts/markdown-for-notion-what-actually-works>、<https://www.goinsight.ai/blog/markdown-to-notion>、<https://en.greatfire.org/https/notion.so>、<https://www.21cloudbox.com/support/notion-china.html>、<https://tinycommand.com/blogs/notion-pricing-2026>

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
2. **ZJ 暂时不用 AI 工具、且接受翻墙 → 用 Notion 访客可编辑单页**（用户倾向）：完整文档导入成页面，分享 `Can edit` 给她直接填（详见 2.4）。**这是"发完整文档给她填"最省事的路**。
3. **不想依赖翻墙** → 自建/内网（Google 表单走 Google 也需翻墙，因此排在这里之后）：把同一份文档用 OpnForm/HeyForm 之类放内网，或干脆走钉钉表单。
4. Notion 若用，**务必**：只私享给 ZJ 一个访客，**绝不**用公开页+允许编辑，也不用公开表单（匿名+不可改）。

**共同前提**：无论走哪条，**Git 仍是唯一事实源**；外部工具只做"填写通道"，内容再由 AI 合并回 MD。

**如果选 Notion，落地要点**（已在 2.4 展开）：你自己在 App 里导入 `.md` 建页并由你拥有 → 手动把 ZJ 加为 Guest(`Can edit`) → 她用 Google 登录填写 → AI 用 MCP `fetch` 读回并入 Git。MCP **不能**替你发访客邀请。9 列大表在 Notion 里不好填，考虑把填写区改成 Notion 数据库。

## 7. 待用户决定

1. 采用 **Notion 访客可编辑单页**（用户倾向），还是 Google 表单 / 自建 / 继续 Git MD？
2. 填写区做成 **纯 MD 表格**（与仓库一致，但 Notion 里填 9 列大表别扭）还是 **Notion 数据库**（好填，但非纯 MD）？
3. 是否要我产出**一份导入友好的"填充版 MD"**（保留完整正文，重排填写区）供你直接导入 Notion？
4. ZJ 是否愿意用 AI 工具（若愿意，可省掉外部系统）？
5. 问卷内容是否允许离开内网（决定是否必须自建）？

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
- Notion 登录方式（Google/Apple/Microsoft/Passkey/邮箱）：<https://www.notion.com/help/log-in-and-out>
- Notion 导入数据（支持 .md，复杂表格会降级）：<https://www.notion.com/help/import-data-into-notion>
- Markdown 转 Notion 实测（表格/代码块/脚注等保真度）：<https://blog.markdowntools.com/posts/markdown-for-notion-what-actually-works>
- Markdown 到 Notion 的丢失项（不支持表格/嵌套列表等）：<https://www.goinsight.ai/blog/markdown-to-notion>
- Notion 免费版访客额度（Free 10 访客；付费不限）：<https://tinycommand.com/blogs/notion-pricing-2026>、<https://21notion.com/en/blog/notion-workspace-guest-limit>
- Notion 免费版各项上限：<https://www.usecarly.com/blog/notion-free-plan-limits>
- notion.so 在中国大陆的可达性（GreatFire 实测 Mixed）：<https://en.greatfire.org/https/notion.so>
- Notion 在中国大陆访问实测：<https://www.21cloudbox.com/support/notion-china.html>

> 外部链接与各平台权限规则会变动，落地前请按当前版本复核。
