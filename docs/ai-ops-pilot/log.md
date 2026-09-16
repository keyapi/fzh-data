---
okf: v0.1
type: Log
title: AI 运营试点评估变更日志
description: docs/ai-ops-pilot 目录变更历史
---

# 变更日志

## 2026-09-16 v7 — 新增 SSO / 域名验证 / 离职回收调研

**背景**：公司准备买 ChatGPT Business（2 席位），唯一顾虑是**离职没法干净断权**，并明确说「要是能像 new-api 的钉钉 SSO 那样就好了」。

**新增 `sso-offboarding-and-domain-2026-09.md`**：

- **结论：做不到「IdP 停用即断权」**。Business **支持** SAML + OIDC：`SSO and domain verification are included with ChatGPT Business. Business supports Security Assertion Markup Language (SAML) and OpenID Connect (OIDC).` 但 SSO 只管登录：`SSO controls how someone signs in; it does not invite them to your workspace ... Workspace owners or admins must manage invitations, members, and available seats separately in ChatGPT.`
- **最关键的一句**：`A user added to the workspace can consume a seat even if their identity-provider access prevents sign-in.` → IdP 停用只挡登录，成员与席位都还在。
- **无 SCIM（双重证据）**：help/11489188 `A standalone ChatGPT Business plan does not include SCIM, synchronized groups, or automatic directory provisioning.`；help/10011769 适用范围表把 Business 列为 `Not available`；定价对比表 `SCIM` Business=No/Enterprise=Yes。生命周期文档能力表：`Directory synchronization through SCIM | ChatGPT Enterprise, Edu, and Healthcare`。
- **IdP 清单无固定名单**：设置流程为 `Choose one of the providers shown, such as Okta, Entra, or Custom SAML when available.` SCIM 的长名单（含 Google Workspace）**不可外推到 Business SSO**。
- **域名验证 ≠ 认领域名**：`Domain verification and domain claiming are different. Verifying a domain does not claim it. Domain claiming is available only for approved use cases and requires a separate request through OpenAI Support or your account team.` → 「验证后员工就不能用公司邮箱开个人号」在 Business 上**不成立**。
- **会话不可控**：`Active sessions ... is not available for accounts linked to an organization's SSO sign-in, including SAML or OIDC.` 官方只说「改 SSO 策略会踢人」，不说「IdP 停用会踢人」。
- **真正的即时断权**：`Removing a member ends their workspace access immediately, but will not remove their ChatGPT seat from the workspace's billable seat count.` → 手动两步：移除成员 + 释放席位。另需单独吊销 Codex access token（`suspends existing tokens but doesn't revoke them`）。
- **「改密码」担忧可放下**：SSO/社交登录建号的账号本就无 OpenAI 密码可改。
- **3 项未核实**：IdP 停用后已有会话的存活时长；Google Workspace 是否为 Business SSO 原生选项；个人密码账号加入 SSO 工作区后是否仍保留密码登录路径。
- **旧引文已失效**：搜索引擎缓存的 `No SCIM / AD group sync on the Business plan, so all user provisioning and de-provisioning is manual.` 已不在现行 11489188 页面，**勿再引用**。

## 2026-09-16 v6 — 新增「15 条 Pro 消息」与「个人账号共享 Project」调研

**背景**：用户对两件事提出澄清要求 —— ① `Business Standard includes 15 Pro messages per month` 中的「Pro 消息」指哪个模型、是月度还是 5 小时窗、用尽后降级还是阻断；② 能否用个人账号（尤其个人 Pro）共享 Project 替代 Business 给小组用。

**新增 `pro-messages-and-personal-project-sharing-2026-09.md`**：

- **定义**：`Note that Pro is a model option, not another name for a Premium seat.` Pro 档 = `GPT-5.6 Sol Pro or GPT-6 Pro`，两者**共用**同一份 15 条/月：`Switching between them does not increase or reset that shared allowance.` 一条消息 = 一问一答（`One prompt and response form a single message.`）。
- **澄清用户的困惑**：`月度额度` 与 `5 小时窗` **两套系统并存但作用域不同**。15 条/月是 **Chat 的 Pro 档**配额；5 小时窗（Astra 5–45 / Sol 10–100 / Terra 25–200 / Luna 250–2,000）是 **Work/Codex 的本地消息估算**，官方标注 `These estimates are not fixed message limits`。二者官方明确分开：`These Chat allowances are separate from usage in Work and Codex.`
- **用尽后**：**不是自动降级**（官方只为 Pro $200 个人档写了自动降至 `GPT-5.6 Thinking at Medium`）。Business 通用规则是 `If no credits are available in the workspace pool, the feature is blocked`；三条出路 = 走 credits（rate card：GPT-6 Pro / Sol Pro 均 `50 credits` per Chat message）、换 Sol、等重置。
- **与个人档对齐**（官方原表）：Plus **无 Pro 档**（`Not included`）；Pro $100 = 50 条/周；Pro $200 = 200 条/周 + Sol Pro 170 条/天；Business Standard = **15 条/月 ≈ 3.5 条/周**。
- **个人共享 Project 全部核实**：`ChatGPT Free, Plus, Pro, and Go users can invite individuals by using the **Only those** setting.`；上限 **Pro 40 文件·100 人 / Plus·Go 25·10 / Free 5·5**（用户给的数字**全部正确**）。
- **跨账号可行**：`If set to "Anyone with a link," any logged-in ChatGPT user who has the link can join` → 不限同工作区、不限同套餐。
- **⚠️ 同页自相矛盾**：同一篇《Projects in ChatGPT》仍留着旧句 `You can only invite members within your workspace.`，与上两条**直接冲突**；判为 2025-10 放开共享前的残留文本（同段还留着 `until October 23, 2025` 的早期访问表述）。
- **账号共享红线**：Terms of Use `You may not share your account credentials or make your account available to anyone else`；Services Agreement 3.1 `will not share Account access credentials or individual login credentials between multiple users`；3.2 `End User Accounts may only be provisioned to, registered for, and used by, a single End User.` → **全队共用一个个人 Pro 账号明确违规，不可采用。**
- **结论**：个人 Pro 路线**共享能力上与 Business 等价**（同为 100 人/40 文件），但在**账号归属、管理台、数据训练、离职交接**四维全面缺失，**不作为试点承载方案**。
- **4 项未核实**：Business Standard 用尽是否自动降级；credits 能否续 Chat 的 Pro 消息（费率已公布但无明文）；Plus/Go 美元月费（定价页价格未在文本渲染）；个人 Pro 共享项目里 owner 对成员移出对话的可见性。

## 2026-09-16（下午）v5 — 新增纯网页路径可行性判定

**背景**：用户把问题收敛成一个决定性判断——**大部分运营装不了本地工具**（Win10 装不上 Codex、`git clone` 都难、退回 workbuddy），**本地桌面方案对本团队不可接受**。于是要回答：本地被排除后，老板的「网页 + Workspace Agent」架构到底能不能做「每日拉赛狐广告报告」。

### 新增 `web-only-ad-report-feasibility-2026-09.md`

六问逐一给判定：

1. **能调自有 HTTPS API，但必须包成 MCP server 且公网可达**。Business 上隧道这条路已排除（本次补充两条硬证据：隧道文档**全文未出现 Business**、以 `Enterprise/Edu` 工作区表述；changelog 只写 `for enterprise customers`）。官方对"服务要保持私有"给的合法形态是 **公网 HTTPS 反代 + OpenAI 托管 mTLS + 出口 IP 白名单**。
2. **执行在云端**（白皮书 `They can run in the cloud, work on schedules`），运营纯网页、零安装。
3. **代价**：Business 下**只有 Admin/Owner** 能开 developer mode 与发布 app；**app 发布后不能原地改只能重建**（`recreate and republish`）+ 冻结快照；**认证是本次最关键发现**——官方原文 `ChatGPT does not support machine-to-machine OAuth grants such as client credentials, service accounts, or JWT bearer assertions, nor can it present custom API keys or customer-provided mTLS certificates.` → **赛狐密钥必须藏在自有 MCP server**，`securitySchemes` 只有 `noauth` / `oauth2` 两种。
4. **定时支持**（`Add schedule` / `run every`），云端调度不依赖开机；API trigger 只能点火（`202 Accepted`，`the agent's response cannot currently be retrieved through the API`）。
5. **产出**：对话 + Slack + artifacts（`documents, slides, or spreadsheets`），Files 512 MB/10 GB。
6. **底线**：架构成立；要新增的唯一组件是**我们自己服务器上的只读 MCP server**（包住赛狐广告 API，服务端持有凭证，对外只开一个 `/mcp`）。运营侧动作 = 打开网页看结果。另提示 credits 已于 **2026-07-06** 开始计费，每日定时是持续成本。

**与既有文档的关系**：不推翻 [work-vs-codex-and-local-automation-2026-09.md](work-vs-codex-and-local-automation-2026-09.md) 的本地优先结论，而是补齐其被排除后的替代路径，并把该文 §5 表格里「云端 MCP server」一行从"可选"提升为**本团队的主路径**。

## 2026-09-16（凌晨）v4 — 修正三处、新增本地自动化方案

**背景**：用户对 v3 提出多组追问（离职能否保席位改密码、Work 是不是 Codex 改名、额度到底共不共享、手动上传不叫 Agent、MCP/隧道/Desktop only 是什么、Business 管理员能不能看会话到底有没有标准答案）。用 5 个并行 subagent 核实。

### 修正的三处（都是我此前说得不准）

1. **额度不是「跨席位共享」**。`shared allowance and credit pool` 里的 shared 指**同一席位内跨产品共用**（Codex/Work/Excel/Agents 共用一份，用爆 Codex 就没 Work）；**每席位的内含额度不跨席位共享**。工作区 credit pool 是另一回事，**订阅不含免费余额，只能买**。→ 用户「2 个席位 = 2 份额度」的直觉**是对的**。
2. **「脚本产出→手动上传」不该作为主路径**。用户指出这不算自动化，**成立**。正确路径是**本地桌面 + 定时任务**（详见下）。v1/v2 的建议已作废。
3. **Secure MCP Tunnel 在 Business 上不可用**。官方 changelog 只说 `Released Secure MCP Tunnel for **enterprise** customers`，Business 发布说明全文 0 次提及；社区实测下拉为空/403。v1 把它列为可选路径是错的。

### 新增 `work-vs-codex-and-local-automation-2026-09.md`

- **Work ≠ Codex 改名**：`ChatGPT includes Chat and Work, plus Codex in the desktop app`；桌面端是**三个并列体验**，Codex 仍是独立视图、独立历史、独立管理开关（Work Cloud / Work Local / Codex Local）。用户说对的是**独立 Codex App 确实并入了新桌面应用**。
- **本地能跑脚本、能调 API**（沙箱三档，可 `run routine local commands`）；但**三处硬约束**：① 网络**默认关闭**，需 `network_access = true`；② 目录须 `trust_level = "trusted"`，否则降级只读、写不出文件；③ 无人值守需 `approval_policy = "never"`，否则半夜挂起等人确认。
- **定时任务支持本地执行**（最高每小时，Business 上限 10 个），但 `Keep the computer on and the app running`。**限制是绑定某台机器，不是服务端常驻。**
- 给出广告报告的正确架构（本地优先），并替换掉此前的手动上传建议。

### 更新 `business-seat-account-and-usage-2026-09.md`

- **§3 离职交接大幅扩写**：「保席位改密码」**不可行且违规**——账号归个人不归公司（官方无 workspace 拥有账号的表述）；Owner **没有改密码/强制登出能力**；Business Terms 3.1/3.2 明文禁止共享凭证，帮助中心警告可能 `workspace deactivation or account suspension`。即便硬做，MFA 在离职者手机上、邮箱能改回密码、还会连带暴露其个人工作区。
- 明确**唯一合规路径**：移除成员 + 席位转继任者 + **离职前要求本人整理交接文档**。补充 **SCIM 不含在 Business 内**。
- **§5.4/5.5 重写**：credits **完全可选**，不买则用尽即 block、等重置；无强制超额扣费；autoreload 默认关；**可把 credit maximum 设为 0**（物理零超支）。补上公开数字（Standard 含 **15 Pro messages/月**；5 小时窗口估算 Astra 5–45 / Sol 10–100）。

### 更新 `chat-history-capture-2026-09.md`

- **§5 给出判定**：Business owner **看不到**成员对话、**无导出途径**，置信度 ~85%。「管理员可查看/导出」的措辞判为**法律权利语言而非已上线功能**（四条理由）。新增旁证：定价页 Business 的 SCIM/RBAC/Analytics/IP allowlisting/数据驻留**同为 No**；微软 Purview 要求 Enterprise；17 家 eDiscovery 合作方全为 Enterprise；The Register 报道。**如实保留未闭环项**（LINUX DO 社区有人称见过导出选项，未证实，可能是灰度）。

### 更新 `skill-distribution-and-selfhost-options-2026-09.md`

- **§4 重写**：三条路准确比较（本地优先 / 公网 MCP / 隧道不可用 / 手动上传不算自动化）；解释 **Desktop only** 触发条件（声明 MCP 的导入插件，**即使远程 HTTPS 也标**）；**凭证机制**（平台 `nor can it present custom API keys`，ChatGPT 只认 OAuth；桌面侧才可用 `bearer_token_env_var` 从环境变量读）——用户 `.env` 类比**一半对**（位置是反的）。
- **新增已排除项**：Open WebUI（用户已测过、老板不关心 skill、DeepSeek 效果打折、官方 GPT API 贵、非正规渠道不敢用）→ 试点起点就是 ChatGPT Business。

## 2026-09-16（深夜）新增席位/账号模型与 skill 分发调研（v3）

**背景**：用户准备买 2 个 Business 席位，提出一组实操问题（怎么分配、要不要先有个人账号、默认几个 workspace、离职怎么交接、积分池与 5 小时限制、Astra/Sol、GitHub 发布 skill、qm 硬件）。用 5 个并行 subagent 分头核实。

**新增 `business-seat-account-and-usage-2026-09.md`**：
- **买席位=邀请邮箱**，不是发账号密码；没账号的会自动创建；已有账号用**同一邮箱**接受即可，**不要另建**。三层区分：账号（登录）/ 工作区（容器）/ 席位（付费名额）。
- 接受后**默认 2 个 workspace**（个人 + 公司）；**merge 不可逆**，会删个人插件与自定义指令；管理员**不能强制**员工合并。
- **离职**：移除成员 → 席位空出 → 邀请新邮箱。**不是改密码，也不是新建账号转移**。席位可复用；降席位下账期生效。**转移项目所有权 ≠ 转移私有对话。**
- **积分池三层串行**：每席位内含额度 → 工作区共享池 → 购买的 credits。`Codex, ChatGPT Work, ChatGPT for Excel, and Workspace Agents` 共用同一池；**常规 Chat 单独计量**。
- **5 小时限制**是滚动窗用量额度而非消息条数。**Standard = Plus 同档，有 5 小时窗；Premium 席位无 5 小时限制**——这才是官方的解法。credits 能延续超额用量，但**是否豁免 5 小时窗未核实**。用尽即**阻断**（非降级、非自动超支）。
- **Astra/Sol 确认为真实模型**：GPT-6 Astra（经 GPT-6 Pro 入口）、GPT-5.6 Sol；另附 credits/1M tokens 费率与席位差异。

**新增 `skill-distribution-and-selfhost-options-2026-09.md`**：
- **Import marketplace 全流程**：`Admin → Plugins → Add → Import marketplace`；**私有仓库官方支持**，但认证是**导入者个人 GitHub OAuth**（人走同步断，建议用组织级专用账号）；支持 commit pinning + 每日同步；**仅支持 GitHub**；**声明 MCP 的插件仅桌面端**。
- **`.claude-plugin/marketplace.json` 被官方接受**（已核实）。
- **skills-only 插件可用**，但**不能持久化凭证** → 我们依赖赛狐/EN/通途凭证的 skill **无法在 Web 端跑**；加 MCP 则被限桌面端。**分发需按「是否需要凭证/执行」分两拨。**
- **Claude Code marketplace 不能 as-is 给 ChatGPT 用**：仅顶层 JSON 文件名与 `SKILL.md` 可复用，执行模型不共享；Anthropic 侧**零互操作文档**。
- **赛狐广告报告**：可走「脚本产出 → 上传共享 Project」（推荐），或包成 MCP app（Business 仅 Admin/Owner 可发）。
- **qm 判定**：技能共享模型对口，但**官方无硬件规格**、Docker target 明确「仅供本地试跑，不得用于真实部署」、需 Postgres + 云账号等重运维；第三方评测定性 `The bus factor is two`、目标用户是「有工程师愿意兜基础设施的 5–50 人团队」。**不作为试点首选。**

**更新 `chat-history-capture-2026-09.md`（v3）**：
- **新增 §3.1「网页↔本地联动」核实**：确认存在，但主角是 **ChatGPT Work 云端会话同步**（`Cloud Work conversations now sync across web, mobile, and desktop`），**不是 Codex**——`Codex does not appear on web`。Codex 的 local↔cloud 只在 Codex 内部（`/cloud`、`/local`）。
- 新增会话存放表：本地 Codex 在 `~/.codex/history.jsonl`，**设备损坏或离职即永久丢失、公司无恢复手段**。
- **口径冲突升级为三处**：新增《Data access for your managed ChatGPT account》(20001067)，明列 Business 且称管理员 `may be able to access, export, audit, retain, delete`（含会话历史），限定 `where enabled by your organization's configuration and applicable law`。**行动项：采购前书面问 OpenAI 销售。**

**索引**：`docs/ai-ops-pilot/index.md` 增两行；`scripts/update_index.py` 已跑且幂等。

## 2026-09-16（深夜）聊天记录调研 v2 — 补机制细节、修正两处、新增替代方案

**背景**：用户指出 v1 结论过于压缩（workspace 为何要选、Codex 本地记录如何、额度是不是按席位固定），并要求深挖共享 Project 的实际限制与替代方案。用 4 个并行 subagent 分头核实。

- **新增 workspace 机制**：工作区是**按会话显式选择**的（`users can select which workspace is active for the current session`）；个人与公司工作区可**合并但不可逆**，且会**删除个人插件与自定义指令**。→ **新增一条试点风险：成员不切换工作区，聊天就留在个人空间，公司拿不到。**
- **新增 Codex 数据位置**：本地会话存在成员机器上的 `history.jsonl`（配置项 `history.persistence`）；管理员可强制绑定工作区（`forced_chatgpt_workspace_id`），用量进 Compliance API，但**内容不共享**。
- **修正 v1 的额度说法**：不是「一个席位固定额度」，而是**两层**——每席位包含额度 + **工作区共享积分池**；且 `Codex, ChatGPT Work, ChatGPT for Excel, and Workspace Agents use a shared allowance and credit pool`（跨功能共用），默认**无上限**需管理员主动设。
- **强化 Enterprise 判据**：官方**定价对比页**逐特性标出 `Compliance API Logs Platform` —— **Business `No` / Enterprise `Yes`**，比 v1 的证据更硬。补充实现机制（Admin key + `Conversation messages` 权限仅 owner 可授；`/logs` NDJSON 端点；旧 stateful 路由已于 2026-06-05 下线）、30 天滚动留存须自建归档、Enterprise 价格不公开。
- **共享 Project 深挖（用户质疑项，均已确认）**：**40 文件/项目**对 Business 适用（Free 5 / Go·Plus 25）；**100 人**仅 Pro·Business·Enterprise·Edu（Plus·Go 仅 10）；项目数无上限；单文件 512MB。
  **新增四个硬伤**：① `branched, not collaborated on synchronously`（无同步共编）；② 成员可把对话移出/删除，owner 之后也看不到；③ **共享项目内用不了 Google Drive/Slack 等链接源**（仅 private project 可用）；④ 成员离职时项目转交 owner，但**项目内对话按保留策略标记删除且 owner 原本看不见**。
- **新增替代方案**：`yc-software/qm`（Multiplayer agent harness，2026-07-29 建，≈15k stars，**挂在 YC org 而非 Garry Tan 个人账号**；`Skills are scope-owned and shareable by grant`；自托管）；**OpenAI 工作区插件市场可直接消费 `.claude-plugin/marketplace.json`**（GitHub-only、支持 commit pinning、每日同步、绑定导入者 GitHub 连接）——这是「Git 真源 + 平台分发」的现成桥；另有 Claude Code Plugin Marketplace 与 LangSmith Context Hub。
- **顺带核实**：`AGENTS.md` 三原则来源 `garrytan/gstack` 确认存在；其 team mode 与本仓库做法同构；ETHOS.md 原文为 **"Boil the Ocean"**，本仓库译作「把湖煮干 (Boil the Lake)」属改写。
- **建议重心转移**：从「收聊天」改为「收产出」——聊天是过程、skill 是产物。
- **未核实清单扩至 9 项**。

## 2026-09-16（夜）新增聊天记录沉淀能力调研

- **背景**：老板 2026-09-16 会上提出「第一步把工作区里所有人的聊天记录都沉淀下来，之后整理成资料 / skill」。用户问：workspace 里的聊天是否自动算在工作区内、本地 Codex 登录算不算。
- **新增 `chat-history-capture-2026-09.md`**：回答该诉求的可行性，并给出官方支持的替代路径。
- **核心结论**：**Business 档位做不到「自动收集全员聊天」**——成员间默认互不可见（`Other members do not automatically see those chats or Codex activity`），用量分析 ≠ 会话访问（官方 FAQ 明确 `No`），且 **Business 工作区没有数据导出**（`Data export is not available`）。管理员读全部会话 + 导出是 **Compliance API**，**仅 Enterprise/Edu**，且日志只留 30 天需自建归档。
- **发现一处官方口径冲突（本次最重要）**：帮助中心说管理员**不能**看/导出成员会话；而官网 [enterprise-privacy](https://openai.com/enterprise-privacy/) 的 Business FAQ 说管理员**可以**查看、访问、导出、删除。**两处均为 OpenAI 官方域名，结论相反。** 已在文档中单列并给出处置建议（不取平均、须实测或书面确认、上会列为待确认风险）。
- **workspace 归属问题**：确认 workspace 是**账号级容器**，Chat 与 Codex 记录都归属该工作区，跨网页/桌面/移动/Codex 一致；但「归属工作区」≠「他人可见」。
- **Codex 问题**：Codex 内容同样不与他人共享；但受工作区开关管控与计费，其使用记录进 Compliance API（Enterprise/Edu）。Codex local 需管理员启用。
- **给出两条可落地路径**：① **共享 Project**（Business 可用，chats + 文件 + instructions，Edit/Chat 两级权限，工作区项目≤100 人、≤40 文件）——聊天沉淀；② **Plugin/Skill**（`skills/<name>/SKILL.md` + `.codex-plugin/plugin.json` 文件布局，发布到工作区需管理员）——能力沉淀，且产物可进 Git。
- **6 项「未核实」**，其中第 1 项即上述口径冲突，必须实测。

## 2026-09-16（夜）新增 Workspace Agent 能力边界调研（工程下钻）

- **新增 `workspace-agent-capability-boundary-2026-09.md`**：回答 `brief-for-boss.md` **R1** 点名的五个工程问题——创建/编辑形态、上传物与代码执行、工具接入（含私网）、权限治理、可维护性，并逐项与仓库 Git 化方式对比。
- **方法**：`help.openai.com` 对自动化抓取返回 403，改用公开 reader 代理按原 URL 读正文；另从 `developers.openai.com`、`cdn.openai.com`（安全白皮书 PDF，经 PyMuPDF 抽取）直取。结论只取可逐句引用的官方表述。
- **五项结论**：
  1. **创建/编辑 = 平台内表单 + 对话式生成，无可导入/导出的定义文件**，进不了版本控制。程序化路径只有 Codex Workspace Agents 插件（beta），且**不能碰已有文件与 skill 文件**。
  2. **唯一可双向进出的载体是 Skill**（可上传、管理员可 Download）；**GitHub 插件市场**是「GitHub → 平台」单方向、按天同步的 JSON 目录，且只同步插件包、不同步 agent 定义。
  3. **工具必须 MCP 且必须远程**；私网走 **Secure MCP Tunnel**（出站单向、不用开公网、需常驻 `tunnel-client`）。Business 档位**只有 Admin/Owner** 能开 developer mode 与发布 app，且 **app 发布后不能原地改，只能重建**。
  4. Agent **可原地更新**（草稿→发布）且有**版本历史可回滚**；但 **Business 无 diff**，**完整审计（Compliance Platform/API）只在 Enterprise/Edu**。
  5. **多人协作无实时合并**（Save conflict 覆盖本地草稿）；**定义不可导出 → 环境迁移=手工重建**；**锁定风险高**。
- **对 R1 的回填**：给出「载体形式 / 输入输出边界 / 发布权限」的确定答案（见新文档 §10.4）。
- **新增三条操作约束**：① 用 Skill 当 Git↔平台的同步物；② Agent instructions 必须回写 Git（平台无导出，否则重建即丢失）；③ 首期只发只读 MCP 工具。
- **时间敏感项**：Custom GPT 退役时间表（09-25 停止创建、12-11 退役）**正落在试点窗口内**，且迁移不带走 custom actions 与模型选择。
- **发现 1 处官方口径不一致**（Business 档位 RBAC 粒度：agent 层 vs plugin/app 层），已单列不做平均。
- **8 项明示「未核实」**，其中最关键的是「上传的代码是否执行、在何沙箱」——官方文档未记载，故不作「上传脚本即可运行」的假设。
- **未修改 `brief-for-boss.md`**：逐条核对后未发现与该调研冲突的事实错误。

## 2026-09-16（夜）对外件 v1.3.1 — 删去 Q3

- **删除 Q3（席位按月/按年、能否退出）**：用户确认席位「肯定能退」，ChatGPT Business 每席 $25/月 或 $20/年。这不是问题。
- **不再提退出条款**：第 30 天的 C 选项（暂停试点）疑为老板 Agent 生成的填充内容，不值得追。用户的判断是——**不要对 Agent 补充的示例性内容做过度解读**。此点记入方法：回核计划时，区分「计划真实意图」与「Agent 补齐的模板化内容」，后者不宜当作议题。
- Q 条目由 3 条减为 2 条，第 1 节第四点由「3 处」改为「2 处」，相关编号同步更新。
- 「会上十分钟能定完」一类对耗时的预估措辞不再出现（v1.3 已删，本版确认无残留）。

## 2026-09-16（夜）对外件 v1.3 — 全文回核计划原文，补齐模糊点

**方法**：把计划 10 页全文重新抽出（PyMuPDF；该 PDF 字体无 ToUnicode，pdftoppm 不可用，抽出后经 `plan_text.txt` 阅读）后逐节回核。

- **补上 4 个助手名称**：v1.2 只说「4 个助手」，默认收件人记得自己 Agent 写过什么。现已在第 1 节列出全部四个名称及各自业务负责人，并在 R1 重述。
- **英文词加中文**：`业务 Owner` → `业务 Owner（业务负责人）`；`Workspace Agent` → 加「工作区智能体」；`MCP` → 加「一种让 AI 调用外部工具的标准接口」。考虑老板英文一般。
- **第 1 节从 3 点扩为 4 点**，新增「四、另外 3 处小口径」：席位是否含产品/视觉协同、经营助手的成本数据口径由谁授权、席位按月还是按年采购（第 30 天暂停能否退出）。三处均出自计划原文中的真实模糊地带。
- **R2 判断修正**：v1.2 说第 07 节「表述偏粗」，不准确。原文写的是重新评估时点「**第 30 天后**；优先评估只读、小范围接口」。真正的冲突是：**第 3 周两个数据侧助手就要吃真实数据，而只读接口被排到第 30 天后**。R2 据此重写，并补上「不存在先做系统后找需求的风险」的论证。
- **R2 表述修正**：v1.2 写「仓库里已有可复用实现」——指向了 `ai_access_poc/`，与「对外不提该 PoC」的约定冲突，已删。改为陈述技术事实（赛狐有读无写）与「只读导出属确定性脚本，不需接口开发」。
- **两处「照计划填表」的发现**：计划第 09 节启动会确认页**本就有**「首批资料 目录 Owner + 目标数量」与「4 个 AI 助手 业务 Owner 分别为 ____」两栏。故 R3/R4 从「建议」改写为「按该栏填写」——是执行计划既有设计，不是额外要求。
- **R1 明确待调研**：不展开 Workspace Agent 能力（能接哪些接口、能否接自有接口、编辑与版本管理方式），改为一句话说明将出对比调研，并点明调研须对比 Git 仓库方式的**后期可维护性 / 可编辑性 / 版本控制**，而非只看上手门槛。
- **新增第 3 节「待确认口径 Q1–Q3」**，与 R 条目分离：R 给处置（接受/需讨论/不接受），Q 直接填答复。

## 2026-09-16（傍晚）对外件 v1.2 — 去掉「质疑计划」的语气，并修正一处事实错误

- **修正事实错误（重要）**：v1.1 写「W1 交清单、W2 导入校验的排期不成立」。重读计划第 4 页原文后发现**这是错的**：
  - 6 类资料的**验收要点**本身就说明它们是规范类——③「字段统一，可复用」、④「指标口径一致」、⑤「含正反例与禁区」、⑥「动作、阈值、责任清楚」；只有 ① 产品资料、② 优秀 Listing 案例是内容类
  - 6 类**每一类都标了责任人**（产品 / 运营 / 广告 / 视觉负责人）
  - 第 1 周的本职动作就是「**盘点**首批知识资料」，交付物是「清单含 Owner/版本」
  - 第 03 节末已写明「AI 负责人维护核心指令与知识版本；业务 Owner 负责专业口径验收」
  - → 计划并未要求一周整理完内容，也未遗漏责任分工。原判断不成立，已改。
- **删除全部「质疑计划」的表述**：`计划里没有写`、`没有定义就无法验收`、`排期不成立` 一律清除。计划是框架，细节本就是下一步工作——用「需要先定」代替「计划缺了」。R 条目的「问题」行改为中性的「现状」行。
- **新增一个真正的开放问题**（替代原来的错误判断）：① 产品资料要的是**格式模板**（之后按模板逐个产品补），还是 **30 天内整理完内容**？这是计划里确实没区分的点，改为向黄总**请教意图**，而非指出缺陷。
- **R4 相应改写**：不再说「业务 Owner 无人负责」（计划已指定），改为「把责任角色**落到具体人名**」。
- **三点定调改为**「都不涉及改计划，启动前把口径定一下，会上十分钟能定完」，收尾改为「定完不影响框架和排期，第二周就能正常推进」。

## 2026-09-16（下午）对外件 v1.1 修订

- **删除全部跨文件引用**：对外件里不再出现 `assessment.md`、`assistant-platform-research-2026-09.md`、`Git 仓库 docs/ai-ops-pilot/` 等指向。**递给别人的文件应当是自足的**——收件人手上没有这些文件，指过去只会让人困惑。同时去掉 frontmatter 的 `depends_on`（递给老板的是原文，元数据同样可见）。
- **取消 PDF**：一页纸相对 md 没有额外信息量，且 md 可直接读/转给 Agent。已删除生成的 PDF 与临时 HTML/PNG。交付形式收敛为**单一 Markdown**。
- **第 1 节改写为口语**：
  - `G1–G4` 首次出现补中文说明「四道检查关口（计划里叫 G1–G4，分别在第 5、10、20、30 天）」
  - `G2` 补「第 10 天那道关口」；`W1`/`W2` 补「第一周 / 第二周」
  - 去掉第 03/04/08 节这类章节号（人读页不引编号）
  - 「一个 Business Workspace」→「一个 ChatGPT 工作区」；「Owner」→「指定负责人」
- **竞品数据改为软表述**：不再写「数据要花钱，得先定谁出」「要么补预算」，改为「外部数据可能是个缺口 / 这类能力通常需要单独开通，并有一定费用 / 建议先列为待确认项」，并给出「先做成研究流程模板」的下台阶——陈述事实，不向老板要预算。
- **第 2 节保留精确编号**：结构化条目面向 Agent，`第 03 节`、`G2` 等引用保留，便于逐条定位。

## 2026-09-16（下午）对外件

- **新增对外件**：`brief-for-boss.md`（v1.0）——「双层单文件」格式：第 1 节人读（打印版只有这一节，已出 A4 一页 PDF），第 2 节起为 R1–R4 编号条目供老板的 Agent 逐条核对，第 3 节为回执协议（接受 / 需讨论 / 不接受）。
- **口径转变**：从「反提案（挑错）」改为「配套建议（让计划自己的 G2/G4 关口能判达标）」。同一批事实，不同立场。
- **对外版剔除三处**（经用户判断）：
  - 不提项目既有 `ai_access_poc/`（老板倾向重新搭建）
  - 不提「AI 负责人专职/兼职、助手 4 个降到 2 个」（无实益）
  - 不提「第 30 天绑定可量化业务指标」（对 AI 负责人不利，赛狐无写 API 时无法达成）
- **责任边界改写**：不再用「我不认领」的表述，改为 R4「每个助手要有业务 Owner，且落到具体的人」，通过治理设计自然划出边界。
- **`counter-proposal.md` 降级为内部底稿**：加醒目警示，frontmatter 标注「不上会」，对外改指 `brief-for-boss.md`。
- **交付形式依据**（2026 业界现状）：Markdown + YAML frontmatter 是 Agent 原生格式（AGENTS.md 2025-12 已捐入 Linux Foundation 的 Agentic AI Foundation；Vercel 基准：内联文档通过率 100% vs 工具检索 53%）；llms.txt 面向网站爬虫、97% 零抓取，不适用单 Agent 交付。PDF 仅用于人读。
- **PDF 不入库**：受 AGENTS.md 第 9 条限制，一页纸输出到仓库外的 `D:\Work\AI\`（与老板原计划 PDF 同目录）。

## 2026-09-16

- **新增平台调研**：`assistant-platform-research-2026-09.md`，基于官方资料复核 ChatGPT Business Workspace Agents、Company Knowledge、远程 MCP app，以及 Dify、n8n、Copilot Studio、Google Agent Platform、Open WebUI 的能力边界。
- **修正载体判断**：Workspace Agent 并非天然不能连接赛狐；可通过远程 MCP/API 调用只读窄工具。但 Git 仓库和上传的 Python 脚本不能直接作为生产运行时，必须服务化。
- **形成分级方案**：30 天只承诺 L1 知识助手 + L2 工具助手；推荐产品表达 Agent（L1）与广告复盘 Agent（L2），L3 业务 Agent 留待第二阶段。
- **修正资料现状**：NAS `/产品信息/` 已按 ERPNext 物料组建立 404 个目录，并有「调研报告 / 设计稿 / 图片 / 视频」标准子目录和只读扫描能力。历史资料可能存在，但尚未盘点 Owner、时效、格式、重复、可解析性与事实可信度。
- **更新落地架构**：推荐「ChatGPT Workspace Agent 前台 + Git 真源 + FZH 只读 MCP 薄适配层」；Open WebUI/IvyeaOps 保留为专用板、隔离执行、工程调试或备用前台。
- **同步修订**：更新 `assessment.md` 与 `counter-proposal.md`，删除「四类资料为空」「平台助手连不上赛狐」等不再成立的表述；W1 改为抽样的「资料资产与缺口表」。

## 2026-09-15

- **新增 bundle**: `docs/ai-ops-pilot/`（`index.md` / `log.md` / `assessment.md` / `counter-proposal.md`）。
- **背景**: 黄总 2026-09-15 出《FZH AI运营试点计划 1.0 — 30天落地行动方案》（10 页 PDF）。用户 2026-09-16 与老板面谈可行性，需完整评估 + A4 一页纸反提案两份材料。
- **写作过程中的关键发现**（决定了文档结构）:
  - 项目已有 `docs/research/2026-07-24-*` 统一 AI 接入调研 + 独立复审，已对载体选型做过证据加权裁决（C′ 门户融合）；老板计划未引用。
  - `docs/research/2026-07-24-unified-ai-access-independent-review.md` §8.1 **已撤销「advertise/ 已验证」论据**；本评估据此不再主张 advertise/ 为可靠资产。
  - 同文档 §8.2：**赛狐广告无写 API**（用户确认 + 文档核对）→「不做写回」是硬约束而非选择。
  - `ai_access_poc/` 壳 #113 + 板 #116 技术验收已绿，**卡在运营审**（`board/docs/specs/ops-review-brief.md`）。
  - 既有裁决**从未评估 ChatGPT Business / OpenAI Workspace**（全库检索零命中）→ 本评估将其明确标为真空，不引用上游作为支持或反对。
  - 外部市场/竞品数据源为付费门槛：卖家精灵 MCP 未开通、Sorftime 仅个人试用一个月已到期、优麦云仅 Excel 无 API。
