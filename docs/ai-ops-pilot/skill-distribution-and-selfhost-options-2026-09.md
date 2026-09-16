---
okf: v0.1
type: Research
title: Skill 分发路径与自托管方案对比
description: 从 GitHub 发布 skill/plugin 到 ChatGPT 工作区的完整流程（含私有仓库）、Claude Code marketplace 兼容性、赛狐 API 类工具如何接入，以及 qm 与开源自托管方案对比
tags: [ai-pilot, plugin-marketplace, skills, github, claude-code, qm, self-hosted, open-webui, dify]
timestamp: 2026-09-16
sources:
  - https://learn.chatgpt.com/docs/enterprise/plugin-management
  - https://learn.chatgpt.com/docs/build-plugins
  - https://help.openai.com/en/articles/20001504-importing-and-syncing-plugin-marketplaces-from-github
  - https://developers.openai.com/plugins/guides/submit-claude-plugin
  - https://developers.openai.com/codex/plugins/build
  - https://code.claude.com/docs/en/plugin-marketplaces
  - https://github.com/yc-software/qm
  - https://github.com/openai/codex/issues/19372
  - https://help.openai.com/en/articles/10169521-projects-in-chatgpt
  - https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt-beta
---

# Skill 分发路径与自托管方案对比

> 调研日期：2026-09-16。回答两个问题：**① 我们 Git 里的 skill 怎么发给运营用？② 自建（qm 等开源方案）现实吗？**

## 1. 从 GitHub 发布到 ChatGPT 工作区：流程已跑通

### 1.1 操作路径

`Admin → Plugins → Add → Import marketplace`

- **Source**：只填**仓库 URL**，不带分支或目录（`Use the repository URL only, without a branch or folder URL.`）
- **Path**：填市场所在的**目录**（`Do not enter the manifest filename`）
- **Branch / tag / commit**：可选。`Use a branch to receive future commits. A fixed commit stays at that revision.` → **想冻结版本就 pin commit。**
- 新建市场**默认每日自动同步**，也可手动 `Sync now`；首次导入最长 1 小时。

### 1.2 三个可接受的清单文件（.claude 格式可用）

| 文件 | 用途 |
|------|------|
| `.agents/plugins/marketplace.json` | Codex 市场，含 `plugins` 数组 |
| **`.claude-plugin/marketplace.json`** | **Claude 兼容市场**（✅ 已核实，无需转换） |
| `.claude-plugin/plugin.json` | 无 marketplace 时的单插件 |

`source` 支持三种：仓库根（`url`）、本地路径字符串、`git-subdir`（可带 `ref` 指向分支/标签/40 位 sha）。

### 1.3 ✅ 私有仓库支持——但认证绑在「导入者个人 GitHub 账号」

**这是最关键的一条**：

- 官方原文：`Public and private GitHub repositories are supported.`
- 但认证**不是 GitHub App、不是 deploy key**：`Marketplace sync uses the GitHub connection of the admin who imported it. That account needs continued access to the marketplace repository and any referenced repositories.`
- → **导入者离职或撤权，同步就断。** 官方补救方式是让新管理员用同样的 Source/Path/ref **重新导入一次**。
- ⚠️ **绝不能删市场**：`Deleting the marketplace in ChatGPT deletes all plugins imported from it.`

**操作建议**：用一个**组织级的专用 GitHub 账号**（而非个人号）来导入，账号权限走 GitHub 组织成员管理，避免人走即断。

### 1.4 已知限制

- **仅支持 GitHub**：`Workspace import currently only supports GitHub repositories`（npm 与其他 Git 主机不支持）。
- **导入 ≠ 授权**：仓库里写的 `AVAILABLE` / `INSTALLED_BY_DEFAULT` 等策略**全部被忽略**，由管理员在工作区里按角色设 **Installation policy**（Available / Installed）。
- **声明了 MCP 的插件会被标 "Desktop only"，Web 端不可用**（即使 MCP 是远程 HTTPS）。
- 从源里删掉的条目只标 `No longer in source`，不会自动删除。

## 2. skills-only 插件：可以做，但有两个会卡住我们的约束

**最小形态（官方）**：

```
meeting-follow-up/
├── plugin.json
└── skills/meeting-follow-up/SKILL.md
```

`plugin.json` 用 `$schema: https://agent-plugins.org/schemas/1.0.0/plugin.schema.json` + `name/version/description`。**不需要 app，不需要 MCP。**

**但两条硬约束直接影响本仓库：**

1. **不能持久化凭证**：官方原文 `If a skills-only plugin needs a credential or a setting that must persist between conversations, add an MCP server.` 且不得使用 `${user_config.*}`。
   → 我们大量 skill 依赖 `sellfox / erpnext / tongtool` 的 API 凭证 + `uv run python` 本地执行，**这类 skill 无法以 skills-only 形态在 Web 端跑**。
2. **一旦为了凭证加 MCP，插件就被标 "Desktop only"，Web 端用不了。**
   → 结论：**带凭证、要真跑脚本的 skill，在 ChatGPT 里只能走桌面端 + MCP 路线**（而这又受 Business「只有 Admin/Owner 能开 developer mode / 发布 app」限制）。

**反过来，纯说明类的 skill（SOP、话术规范、输出模板、判断规则）没有这两条限制**，是可以 Web 端直接分发的。**分发策略应当按「是否需要凭证/执行」分成两拨。**

## 3. Claude Code marketplace 能不能给 ChatGPT 用？

**格式能复用，执行不能。结论：不能 as-is 当 ChatGPT 市场用。**

**能复用的部分**：
- 顶层文件名 `.claude-plugin/marketplace.json` 被 OpenAI 直接接受（见 §1.2）。
- `skills/<name>/SKILL.md` 结构通用。

**不能复用的部分**（OpenAI 明确列出的不支持项）：
`commands/`、`agents/`、`hooks/hooks.json`（须改写为 Codex hook runtime）、`userConfig`、`.claude/settings*.json`、`CLAUDE.md`、`outputStyles`、`lspServers`、Claude live artifacts。

**Anthropic 侧零文档**：`code.claude.com` 的插件文档中 **"ChatGPT"/"Codex"/"agent-plugins.org" 出现 0 次**——**没有官方互操作承诺，是 OpenAI 单向兼容**。OpenAI 反而有一篇官方指南《Submit your Claude Code plugin to OpenAI》。

**已知 schema 分叉（第三方实测）**：Claude 的 `skills` 是**路径数组**，Codex 只接受**单个路径字符串**（数组报 `missing or invalid plugin.json`）；Codex 复制插件时**丢弃 symlink**。

→ **所以：我们可以把「说明类 skill」按 OpenAI 的格式另做一份导出，但不能指望现有 Claude 插件原样搬到 ChatGPT。**

## 4. 赛狐 API 拉广告报告，在共享 Project 里可行吗

**先厘清 v2 那条限制的准确含义**：我用词不够精确。「共享项目里用不了 Google Drive / Slack 链接源」指的是 **ChatGPT 内置的项目「链接源」连接器**（官方文档说这些源在 **private project** 里打开）。**赛狐 API 不是 ChatGPT 的连接器**，所以它既不属于「能用」也不属于「不能用」——它是**另一条路**。

**实际可走的两条路**：

| 路线 | 可行性 | 代价 |
|------|--------|------|
| **离线跑脚本 → 把输出文件传进项目** | ✅ 可行。脚本在我们自己的机器/服务器跑，产物（CSV/Excel/MD）上传到共享 Project，ChatGPT 就能 `draw from` 它 | 手动或半自动，非实时 |
| **把赛狐包成自定义 MCP app** | ⚠️ 技术上可行，但 Business 下**只有 Admin/Owner 能开 developer mode、只能由 Admin/Owner 发布**；必须**远程 MCP**（内网走 Secure MCP Tunnel）；声明 MCP 的插件**仅桌面端** | 需要常驻隧道客户端 + 管理员操作 + 只读工具设计 |

→ **对试点的建议：先走第一条路。** 广告报告本来就是离线脚本产物，上传文件即可，不需要为了「实时」付出 MCP 的全部运维代价。

## 5. 自托管方案：qm 与替代品

### 5.1 qm 的真实情况

- **它是什么**：`Multiplayer agent harness for work`（TypeScript/Fastify + Postgres + 每个 scope 一个持久 sandbox）。YC 内部用于会计、法务、活动、工程。**无官方托管版**，必须部署进自己的云账号。
- **技能机制确实对口**：`SKILL.md` 按 scope 拥有、`shareable by grant`、管理员门控可提升到全组织、**支持从 git 仓库导入 skill pack**（pin 到 ref，bump ref 重新导入即幂等更新）。但 **docs 明说 Phase A 只支持 org scope，团队级 scope 还是 Phase D**。
- **部署**：`qm init . --org <slug> --target <fly|aws|docker>`。

**硬件要求：官方文档完全没有 CPU/RAM/磁盘规格 → 不能编造。** 可确认的是：

- **不能拿一台公司 PC 就跑**。`--target docker` 存在，但官方 deployment.md 明确说它是 `a quick local test drive only`、`never to be pitched for real deployments`；仓库里还有 local Docker sandbox 的开放故障 issue。
- 需要 **Docker + Buildx**、Node 24+、Git、openssl；**不需要 GPU**；**不强制公网域名/TLS**（邮件登录需验证发件域）。
- 唯一出现的资源数字来自 Helm chart（**非文档承诺**）：core 500m CPU / 1–2Gi 内存，其余各 100m / 256–512Mi。
- **运维负担重**：Postgres、对象存储、身份 broker、sandbox 基础设施、升级要跑 migration 且「回滚只恢复代码不恢复数据库」。

**第三方实测教训（非官方）**：

- HN 讨论热度集中在 `CONTRIBUTING.md`——**「不接受代码 PR，只收手写文本提案」**，评论吐槽一个 AI 项目却要求人手写提案。
- 评测定性：**`The bus factor is two`**、一个月新的仓库有 300+ open issue、**`the local path is not fully settled`**、目标用户是 **`a 5–50 person startup already living in Slack, with an engineer willing to own infrastructure`**；坏场景明确列出 **`teams lacking anyone to run Postgres plus a cloud account`**。原文：**`It is not a product you install this afternoon and forget.`**
- `SECURITY.md` 自称 `early, experimental software`，**不是加固的多租户边界**。

→ **判定：qm 的技能共享模型完全对口，但它是「需要一个专职基础设施工程师」的方案。** 老板要的「GPT 模式」（网页即用、无需运维）它给不了。**列入观察，不作为试点首选。**

### 5.2 其他自托管方案（stars 与推送时间为实测）

| 方案 | 面向运营的 UI | 版本化/可审计知识 | 维护负担 | 活跃度 |
|------|--------------|------------------|---------|--------|
| **LangSmith Context Hub** | **有**，明确为设计师/市场/客服设计，免代码 UI；commit + dev/staging/prod tag；原生支持 `AGENTS.md`/`SKILL.md` | **最强** | 低（托管） | 2026-05 发布 |
| **AnythingLLM** | 最高，无代码、按 workspace 隔离 | 弱（无 skill 版本化） | 最低，单条 docker | 66k stars，MIT |
| **Open WebUI** | 高，ChatGPT 式 + RBAC/SSO | 知识库有引用溯源，无 skill 版本化 | 低-中 | 152k stars |
| **Onyx** | 高，面向企业搜索/支持 | 连接器 + 权限继承较好 | 中-高 | 32k stars |
| **LibreChat** | 高 | 弱 | 低-中 | 44k stars，MIT |
| **Dify / n8n** | 低/无（开发者向） | 有 | 高 | 156k / 204k stars |

**关键发现**：**LangSmith Context Hub 在「非技术团队共享并累积 skill」这件事上最贴合**，但它是 **LangSmith 云功能**，官方博客**完全没提自托管/开源** → **是否有 on-prem 未核实**，与「自托管」前提冲突，需向 LangChain 确认企业版。

### 5.3 成本对照

- **ChatGPT Business**：≈ $20–25/席位/月，6–8 人约 **$120–200/月**，含界面、**无需运维**。
- **自托管**：服务器（云账号或内网机器）+ **按 token 付费**。qm 默认带预算闸：`BUDGET_USD_PER_WINDOW=25`（每人每天）、`ORG_BUDGET_USD_PER_WINDOW=100`（全组织每天）。
- **隐性成本更大**：一名工程师的持续运维时间（Postgres、云账号、升级、备份）。**这是自托管方案最容易被低估的一项。**

## 6. 建议

1. **分发按「是否要凭证/执行」分两拨**：
   - **说明类 skill**（SOP、规范、模板）→ 做一份 OpenAI 格式导出，走 **Import marketplace**，可 Web 端分发。
   - **执行类 skill**（要跑脚本、用凭证）→ 留在本地/服务器 + MCP，或继续走 Git + Claude Code，**不要指望搬进 ChatGPT Web**。
2. **私有仓库可以用**，但**用组织级专用 GitHub 账号导入**，不要用个人号。
3. **版本冻结用 commit pinning**；需要跟进更新再用 branch。
4. **赛狐报告先走「脚本产出 → 上传文件」**，不要为实时性先上 MCP + Tunnel。
5. **自托管（qm 等）暂不作为试点方案**：它解决的是「多人共享 skill」，付出的是一台常驻基础设施 + 专职运维。**等试点跑出真实需求轮廓再评估。**
6. **若要找托管版的对口方案**，先去看 **LangSmith Context Hub**（确认是否有企业自托管）。

## 7. 未核实清单

1. `.claude-plugin/marketplace.json` 是否必须含 Claude 自家 schema 的 `owner` 字段（OpenAI 示例省略）。
2. 导入时的文件体积/类型上限（官方只说「很大的市场」要 1 小时）。
3. ChatGPT **Business**（非 Enterprise）与 Enterprise 在插件管理权限上是否完全一致。
4. LangSmith Context Hub 是否有自托管/on-prem 版本。
5. qm 的具体硬件规格（官方无文档）。
6. 「共享 Project 上传的文件」是否会被工作区管理员统一导出。

## 8. Sources

### OpenAI

- [Plugin management (ChatGPT Learn)](https://learn.chatgpt.com/docs/enterprise/plugin-management)
- [Build plugins (ChatGPT Learn)](https://learn.chatgpt.com/docs/build-plugins)
- [Importing and syncing plugin marketplaces from GitHub](https://help.openai.com/en/articles/20001504-importing-and-syncing-plugin-marketplaces-from-github)
- [Submit your Claude Code plugin to OpenAI](https://developers.openai.com/plugins/guides/submit-claude-plugin)
- [Building Codex plugins](https://developers.openai.com/codex/plugins/build)
- [Developer mode and MCP apps in ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt-beta)
- [Projects in ChatGPT](https://help.openai.com/en/articles/10169521-projects-in-chatgpt)

### Anthropic

- [Create and distribute a plugin marketplace (Claude Code)](https://code.claude.com/docs/en/plugin-marketplaces)

### 开源与第三方（需打折）

- [yc-software/qm](https://github.com/yc-software/qm) · [deployment guide](https://github.com/yc-software/qm/blob/HEAD/cli/templates/deployment/deployment.md) · [SECURITY.md](https://github.com/yc-software/qm/blob/HEAD/SECURITY.md)
- [openai/codex Issue #19372](https://github.com/openai/codex/issues/19372)（Codex 自动镜像 `.claude-plugin/marketplace.json`）
- [QM Review — andrew.ooo](https://andrew.ooo/posts/qm-yc-multiplayer-agent-harness-review/)
- [Hacker News: qm](https://news.ycombinator.com/item?id=49126604)
- [LangSmith Context Hub](https://www.langchain.com/blog/introducing-context-hub)

### 本仓库

- [business-seat-account-and-usage-2026-09.md](business-seat-account-and-usage-2026-09.md) — 席位/账号/用量
- [chat-history-capture-2026-09.md](chat-history-capture-2026-09.md) — 聊天记录沉淀
- [workspace-agent-capability-boundary-2026-09.md](workspace-agent-capability-boundary-2026-09.md) — Agent 能力边界
