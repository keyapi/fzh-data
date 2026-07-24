---
okf: v0.1
type: Research
title: FZH 统一 AI 接入方案 — 完整调研报告与 Agent 交接文档
description: 面向未来 Agent 的完整上下文：公司背景、现有基础设施、需求约束、调研过程、所有候选平台对比、引用 URL、结论与推荐方案
tags: [ai-agent, self-hosted, browser-based, amazon-advertising, saihu, erpnext, dingtalk, platform-comparison]
created: 2026-07-24
updated: 2026-07-24
sources:
  - https://github.com/open-webui/open-webui
  - https://github.com/odysseus-dev/odysseus
  - https://github.com/Hector-xue/IvyeaOps
  - https://github.com/langgenius/dify
  - https://github.com/n8n-io/n8n
  - https://github.com/NousResearch/hermes-agent
  - https://github.com/AgriciDaniel/claude-ads
  - https://github.com/zach22-1999/amazon-skills
  - https://github.com/ppcprophet/amazon-ads-mcp
  - https://github.com/QuantumNous/new-api
  - https://developer.aliyun.com/article/1724308
---

# FZH 统一 AI 接入方案 — 完整调研报告

> **面向读者**: 未来的 AI Agent（Claude Code / Codex / Cursor / ChatGPT 等）
> **目的**: 让你完全了解这个项目的背景、需求、调研过程和结论，能够独立继续调研或实施
> **使用方法**: 通读本文后，你可以直接开始工作，无需重新询问用户基本信息

## ⚠️ 作者偏差声明（必读）

**本文作者是 Claude Agent，在整个调研过程中存在以下已识别的偏差**：

1. **倾向 Open WebUI**：当发现 Lobe Chat 缺少代码执行能力后，作者快速转向 Open WebUI，但在后续对比中没有给予 IvyeaOps 和 Odysseus 同等深度的优势分析。下文已标注具体偏差位置。

2. **对 OIDC 和 RAG 的过度重视**：作者将「钉钉 OIDC 原生支持」和「RAG 知识库」作为核心差异点，但用户反馈指出：OIDC 他们已能自建、RAG 在 2026 年已非第一优先级（MD 文档 + OKF 标准才是）。

3. **对 IvyeaOps 的武断否决**：作者以「领星写死」为由快速否决 IvyeaOps，但未充分评估：其电商业务模块的复用价值、领星改赛狐的实际工作量、AI 生成 Skill 的独特优势。

4. **未交叉验证**：所有平台对比由单一 Agent 完成，没有让另一个独立 Agent 做平行评估。

**每个有偏差的具体位置在下文中用 `[偏差标注 N]` 标记，详见对应段落的脚注。**

---

## 一、公司背景

### 1.1 FZH 公司

- **行业**: 跨境电商，北美+欧洲销售**家居纺织品**（PP棉/海绵填充的靠枕、沙发等）
- **销售平台**: Amazon（北美+欧洲）、Wayfair、Home24、Shopify
- **供应链**: 绍兴工厂 → USNJ(美东)/USTX(美中)/POLAND(波兰) 仓库 → Amazon FBA
- **团队规模**: 小团队，含运营部（女同事居多）、供应链部（男同事）

### 1.2 现有系统

| 系统 | 用途 | 接口 |
|------|------|------|
| **赛狐 SailFox** | Amazon ERP，管理商品/广告/库存 | OpenAPI (`https://openapi.sellfox.com/`) |
| **ERPNext** | 供应链+财务 (生产 `erpnext.vilavi.cn`, 测试 `ensh.vilavi.cn`) | REST API |
| **通途 Tongtu** | WMS 仓库管理 | 导出 |
| **钉钉 DingTalk** | 企业 IM | OAuth / Bot API |

### 1.3 赛狐仓库映射

| 公司仓库 | 赛狐仓库名 |
|----------|-----------|
| USNJ 美东仓 | CENTRADE |
| USTX 美中仓 | DANEEY |
| POLAND 波兰仓 | POLAND |

---

## 二、现有 AI 基础设施

### 2.1 api.vilavi.cn（上海阿里云）

```
api.vilavi.cn (nginx :443)
├── /          → new-api:3000        (AI API 网关)
├── /oidc/*    → oidc-bridge:8086    (钉钉 OAuth → OIDC)
├── /sellfox/* → sellfox-proxy:8400  (赛狐 API 代理)
└── /v1/*      → DeepSeek V4 Flash/Pro (上游模型)
```

**核心组件**:
- **new-api** (`QuantumNous/new-api`): Docker 部署，SQLite，多用户配额管理，订阅套餐
- **new-api-dingtalk-oidc**: 自建 FastAPI 桥接器，标准 OIDC 协议，钉钉扫码登录 → 自动创建 new-api Token
- **订阅系统**: Monthly Basic (500K) / 5Min-0.10RMB / Daily-20RMB
- **自动入职**: 钉钉登录 → 自动绑套餐 + 建令牌
- **自动离职**: Stream 实时 + 每日兜底检查，user_leave_org → 即刻封号

### 2.2 同事使用的 AI 客户端

| 客户端 | 使用者 | 对接方式 |
|--------|--------|---------|
| **Codex Desktop + Codex++** | 部分同事 | `api.vilavi.cn` → DeepSeek |
| **WorkBuddy (腾讯)** | 部分同事 | `api.vilavi.cn` |
| **Claude Desktop (旧版 2026.4)** | 用户本人 | 3P 模式 + 模型 ID 伪装 → DeepSeek |
| **Cursor** | 用户本人 | API 对接 |

### 2.3 fzh-data 项目

- **仓库**: `github.com/keyapi/fzh-data`
- **核心模块**: `multi_attr_saihu/`, `category/`, `item_cost_sx/`, `item_weight_size/`, `stock_init/`, `warehouse_restock/`, `other_outbound/`, `advertise/`
- **赛狐 API 脚本**: `SELLFOX_API/fetch_ad_reports.py` (7 种 SP 报告拉取已验证)
- **广告分析**: `advertise/` 目录有 7 个分析脚本 (campaign/targeting/search_term/placement/ad_group/advertised_product/purchased_item) + 跨报告集成 + 否定词生成
- **⚠️ 这些脚本未经过充分验证**: 用户自述只花了不到半天快速测试，有 bug 未修复，不是广告专家无法判断输出准确性
- **Skill 系统**: `.agents/skills/` 下有 11 个 SKILL.md，Codex/Cursor 自动加载
- **Agent 配置**: `AGENTS.md` (项目总纲) + `CLAUDE.md` (symlink)

---

## 三、核心问题与需求

### 3.1 问题

1. **部分同事 Win10 无法升级 Win11** — 装不了 Codex/ChatGPT Desktop
2. **部分攒机 Win10 版本特殊** — 装不了任何 AI 桌面软件
3. **培训效果分化严重**:
   - 供应链男同事：快速上手，能自己用 Agent+API 操作 ERPNext/赛狐/钉钉
   - 运营女同事(4人)：仅 1 人自己爱琢磨能上手，其余连安装 Codex/填 API Key 都觉得困难
4. **老板关注 Amazon 广告优化** — 认为能快速带来收益，想更多人更简易落地 AI
5. **老板本人习惯 ChatGPT 网页界面** — 虽然装了 Codex 也只是用 chat 用法
6. **老板举的例子**: "10 几句话帮'我'优化一个 listing" — 本质是把 Prompt 模板固化给小白用

### 3.2 需求分级

| 级别 | 描述 | 用户群 | 优先级 |
|------|------|--------|:---:|
| **A: 模板操作** | 选模板 → 上传 Excel → 点按钮 → 等结果 | 运营小白 | 🔴 现在 |
| **B: Chat 驱动** | 聊天框里说"帮我分析 ACOS"→ AI 执行 | 进阶运营 | 🟡 后续 |
| **C: 规则自定义** | 自己调整 ACOS 阈值、分析策略 | 运营负责人 | 🟢 未来 |

### 3.3 关键约束

1. **用户(张克勇)不想成为长期维护者** — 搭框架+培训后，运营部接手
2. **必须浏览器可用** — 解决 Win10 装不了桌面端的硬伤
3. **必须有"手脚"** — 不仅是 Chat，要能调赛狐 API、执行代码、分析数据
4. **必须能 Chat 操作执行拉取并分析** — "帮我拉取赛狐广告报告并分析 ACOS"
5. **运营负责人要能自己维护规则** — 用他们自己的 Agent 改配置和 SOP 文档
6. **预算敏感** — 阿里云轻量 4C8G ~¥1,159/年 可接受
7. **平台必须能用 Agent 维护** — 用户认为"如果不能用 Agent 维护，2026 年就是过时了"
8. **SKILL.md 跨平台兼容** — 现有项目已用，Codex/Cursor/Claude Code 都支持

---

## 四、调研过程

### 4.1 已否决的方案

| 方案 | 否决原因 |
|------|---------|
| **纯 Chat (Lobe Chat / NextChat)** | 只有聊天没有"手脚"，无法执行代码/调 API |
| **new-api 自带 Chat** | 玩具级别，已被用户关闭 |
| **OpenClaw** | 用户明确拒绝。138 个 CVE (63天内)，7 个 Critical。安全灾难 |
| **Hermes Agent** | API 剧变(42天4版本)、自进化 Skill 危险(V2EX 实测第7天自动合并半成品 PR)、代码执行有限(编排器不是编码器) |
| **Pi Agent** | 纯 CLI 无 Web UI，非技术同事无法使用。定位是 SDK 不是产品 |
| **Dify** | 不能用 Agent 维护(无外部管理 API)、相比 Hermes 缺少 Agent 原生能力、"2025 年流行但 2026 年不是最前沿"。虽然 150K stars + $30M 融资，但定位是 LLM 应用开发平台 |
| **n8n** | 工作流强大 (184K stars, MCP Server 2026.4) 但交互式 Chat 需要自己搭。更适合自动化后台 |

### 4.2 深度调研的三个项目

#### Open WebUI
- **GitHub**: `open-webui/open-webui`, 146K+ stars, 17K+ commits, 166 releases
- **技术栈**: Python 后端 + Svelte 前端 + SQLite/PostgreSQL
- **工具系统**: 5 种插件类型 — Tools (Python 进程内运行)、Pipelines、Filters、Actions、Skills + MCP + OpenAPI
- **代码执行**: Open Terminal (Docker 沙箱)
- **RAG**: 9 种向量数据库 + 混合搜索 (BM25+向量+重排)
- **认证**: OIDC/OAuth/LDAP/SCIM — 可对接钉钉
- **部署**: 单 Docker 容器
- **许可证**: 自定义(需保留 "Open WebUI" 品牌)
- **关键优势**: 最成熟、社区最大、Tools 系统可直接写 Python 调赛狐 API、OIDC 现成
- **URL**: https://github.com/open-webui/open-webui
- **文档**: https://docs.openwebui.com

#### Odysseus (PewDiePie 项目)
- **GitHub**: `odysseus-dev/odysseus`, 69K+ stars
- **发布**: 2026年5月31日
- **技术栈**: Python FastAPI + 原生 JS + SQLite + ChromaDB
- **部署**: 4 个 Docker 容器 (App + ChromaDB + SearXNG + ntfy)
- **许可证**: AGPL-3.0
- **关键不足**: 无 OIDC (仅密码+Google OAuth)、无 Docker 沙箱(直接 bash)、4 容器部署重、无社区插件商店
- **URL**: https://github.com/odysseus-dev/odysseus

#### IvyeaOps
- **GitHub**: `Hector-xue/IvyeaOps`
- **创建者**: Hector-xue，深圳跨境电商**运营负责人**，用 vibe coding 打造
- **定位**: 自托管 Amazon 运营工作台
- **技术栈**: Python FastAPI + React+Vite + SQLite
- **已有功能**: 领星 ERP 对接、广告分析、市场调研、Listing 生成、Skill 中心、GBrain 知识库
- **部署**: Docker Compose 或 Windows x64 预构建包 (免 Python/Node)
- **许可证**: AGPL-3.0 (因移植了 claudecodeui)
- **关键参考价值**: 验证了"Web UI + Agent + ERP + 知识库"模式在跨境电商场景完全成立。由运营人员而非专业程序员打造
- **关键不足**: 写死领星需改为赛狐、社区极小、无 OIDC、纯中文
- **URL**: https://github.com/Hector-xue/IvyeaOps
- **官网**: https://www.ivyea.com

### 4.3 相关开源项目（Amazon 广告方向）

| 项目 | Stars | 说明 | URL |
|------|-------|------|-----|
| `AgriciDaniel/claude-ads` | 7.3K | 12 广告平台 Skill，含 Amazon Ads 审计(250+检查) | https://github.com/AgriciDaniel/claude-ads |
| `zach22-1999/amazon-skills` | 121 | 中文 Amazon 卖家 Skill，产品调研/广告搜索词/CVR 诊断 | https://github.com/zach22-1999/amazon-skills |
| `zach22-1999/lingxing-mcp` | 28 | 领星 ERP MCP 服务器 | https://github.com/zach22-1999/lingxing-mcp |
| `ppcprophet/amazon-ads-mcp` | 4 | Amazon Ads MCP 服务器 | https://github.com/ppcprophet/amazon-ads-mcp |
| `nospicyplease/amazon-ppc-advanced-skills` | 10 | Amazon PPC Agent Skills | https://github.com/nospicyplease/amazon-ppc-advanced-skills |
| `itallstartedwithaidea/advertising-hub` | 27 | 14 平台 + 25+ AI Agent | https://github.com/itallstartedwithaidea/advertising-hub |
| `nexscope-ai/awesome-amazon-seller-tools` | 133 | Amazon 卖家工具清单 | https://github.com/nexscope-ai/awesome-amazon-seller-tools |
| `smart-seller/awesome-amazon-seller-tools` | 133 | Amazon 卖家工具清单 | https://github.com/smart-seller/awesome-amazon-seller-tools |

### 4.4 代码沙箱方案

| 方案 | 隔离技术 | 启动速度 | URL |
|------|---------|---------|-----|
| E2B | Firecracker microVM | ~150ms | https://github.com/e2b-dev/e2b |
| Daytona | Docker + 可选 Kata | ~90ms | https://github.com/daytonaio/daytona |
| DifySandbox | seccomp + chroot | 极快 | Dify 内置 |
| OpenSandbox (阿里) | K8s + 容器 | 快 | https://github.com/alibaba/OpenSandbox |

---

## 五、平台对比矩阵

> **[偏差标注 1]** 本矩阵由单一 Agent（倾向 Open WebUI）制作，v2 和 ❌ 标记可能带有主观色彩。建议新 Agent 重新独立制作对比矩阵，或至少用另一个 Agent 交叉验证。

| 维度 | Open WebUI | Odysseus | IvyeaOps | Dify | n8n | Hermes |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| **GitHub Stars** | 146K | 69K | 较新 | 150K | 184K | 150K |
| **Web UI** | ✅ Svelte | ✅ 原生JS | ✅ React | ✅ | ✅ | ✅ |
| **Chat 操作** | ✅ 原生 | ✅ | ⚠️ 偏终端 | ✅ | ⚠️ Chat Builder | ✅ |
| **代码执行** | ✅ Docker沙箱 | ⚠️ 直接bash | ⚠️ PTY终端 | ✅ seccomp沙箱 | ⚠️ 需配置 | ⚠️ 有限 |
| **自定义 API 对接** | ✅ Python Tool | ⚠️ MCP封装 | ❌ 写死领星 | ✅ 工作流 | ✅ HTTP节点 | ⚠️ Skill |
| **RAG 知识库** | ✅ 9向量库+混合搜索 | ✅ ChromaDB | ⚠️ 文件级 | ✅ 成熟 | ❌ | ⚠️ 记忆系统 |
| **钉钉 OIDC** | ✅ | ❌ | ❌ | ✅ OAuth | ❌ | ⚠️ IM集成 |
| **多用户** | ✅ RBAC | ⚠️ 简单密码 | ⚠️ 密码 | ✅ RBAC | ✅ | ✅ |
| **Agent 维护** | ⚠️ 部分API | ✅ MCP | ✅ CLI Agent | ❌ 无管理API | ✅ MCP Server | ✅ CLI |
| **部署复杂度** | ⭐ 1容器 | ⭐⭐⭐ 4容器 | ⭐ 1进程 | ⭐⭐ 多容器 | ⭐⭐ | ⭐⭐ |
| **许可证** | 自定义(品牌保留) | AGPL-3.0 | AGPL-3.0 | Apache 2.0+限制 | Sustainable Use | MIT |

---

## 六、SKILL.md 跨平台标准（重要发现）

2026年，SKILL.md 已成为跨 20+ Agent 的开放标准：

```
同一个 SKILL.md 文件可运行于:
  Codex CLI      → ~/.codex/skills/
  Cursor         → ~/.cursor/skills/
  Claude Code    → ~/.claude/skills/
  GitHub Copilot → ~/.copilot/skills/
  Gemini CLI     → ~/.gemini/skills/
  OpenClaw       → ~/.openclaw/skills/
  Hermes Agent   → 也支持
```

**fzh-data 项目已在使用** (`.agents/skills/` 下 11 个 skill)。这意味着 `AgriciDaniel/claude-ads` 的 Amazon Ads Skill，用 Codex 或 Cursor 就能跑，不需要 Claude Code CLI。

---

## 七、分析：关键权衡维度

以下不是结论，而是需要新 Agent 独立判断的几个核心权衡。本调研文档作者（Claude Agent）有倾向性，请新 Agent 独立评估。

### 7.1 钉钉 OIDC — 不应作为核心差异点

> **[偏差标注 2]** 作者最初将 OIDC 作为选择 Open WebUI 的核心理由之一，但用户明确指出：他们已自建 OIDC 桥接器，可以为任何平台提供钉钉登录。OIDC 是加分项，不是决定性因素。

**背景澄清**：FZH 已经自建了 `new-api-dingtalk-oidc` 桥接器（FastAPI，标准 OIDC 协议），可以为任何支持 OIDC 的平台提供钉钉登录。因此 OIDC 支持不是选平台的硬门槛——如果平台不支持 OIDC 但有其他压倒性优势，可以评估自建 OIDC 对接的工作量。

**实际权重**：OIDC 是"加分项"而非"决定性因素"。部署便捷性应该用"裸平台部署 + OIDC 对接工作量"来综合评估，而非只看平台是否原生支持。

### 7.2 RAG 知识库 — 2026 年趋势已从 RAG 转向 MD 文档

> **[偏差标注 3]** 作者最初将「RAG 知识库最成熟」作为选择 Open WebUI 的核心理由之一，但用户指出：2026 年趋势是回归 MD 文档 + Obsidian / OKF 标准，RAG 是补充而非核心需求。FZH 项目已在用 OKF v0.1 记录文档。

**趋势变化**：
- 2025 年 RAG（向量检索增强生成）被视为必需品
- 2026 年多个平台（Hermes、Odysseus、IvyeaOps）回归简单 MD 文件 + 全文搜索，部分配合 Obsidian
- FZH 项目已在使用 **OKF v0.1** 标准记录和更新文档（Markdown + YAML frontmatter + Git）
- RAG 作为 MD 文档之上的**补充**是有价值的（语义搜索跨文档），但不应该是第一优先级

**对选型的影响**：知识管理方案应优先考虑「现有 OKF 文档如何被 AI 读取」，其次才是 RAG。桌面端用户（Codex/Cursor）通过 `AGENTS.md` + `.agents/skills/` 加载知识，Web 端用户也需要相同的文档体系。

### 7.3 桌面端与 Web 端的文档同步 — 核心架构挑战

**当前状态**：
- 桌面端用户（Codex/WorkBuddy/Cursor）通过 Git 仓库的 `AGENTS.md` + `.agents/skills/` + `docs/` 获取项目知识
- 如果部署 Web 平台（Open WebUI 或其他），这些文档如何同步？

**可选方案**：
| 方案 | 描述 | 优劣 |
|------|------|------|
| **Git 仓库共享** | Web 平台直接挂载 fzh-data Git 仓库目录 | 单一真相源，但需要平台支持外部文件系统读取 |
| **双向 Webhook 同步** | Git push → webhook → 平台更新知识库 | 实时性好，但增加复杂度 |
| **手动/定时同步** | 定期从 Git 拉取到平台 | 最简单但有延迟 |
| **平台内置 Git** | 平台直接 clone Git 仓库 | 理想方案，需平台支持 |

**关键问题**：无论选哪个 Web 平台，必须回答「运营部在 Web 端更新的 SOP 文档，如何让桌面端 Codex/WorkBuddy 用户也能用到？」以及反向：「Git 仓库里的 AGENTS.md 更新，Web 平台如何感知？」

### 7.4 复用现有开源业务逻辑 vs 从零自建

**已有的可复用资产**（非自建）：

| 资产 | 来源 | 可直接用？ | 适配工作量 |
|------|------|:---:|------|
| 领星 ERP 对接 | IvyeaOps `server/` | ❌ 写死领星 | 改 API 端点为赛狐，中-高 |
| 广告分析模块 | IvyeaOps 广告分析 | ⚠️ 依赖领星 API | 抽取分析逻辑，中 |
| Listing 生成 | IvyeaOps Listing 工作台 | ⚠️ | 低-中 |
| 市场调研 | IvyeaOps 市场调研 | ⚠️ | 中 |
| Skill 中心 | IvyeaOps Skill 中心 | ⚠️ 依赖 IvyeaOps 框架 | 中 |
| Amazon Ads 审计 | `AgriciDaniel/claude-ads` (7.3K⭐) | ✅ SKILL.md 可跨平台 | 极低 |
| Amazon 卖家 Skill | `zach22-1999/amazon-skills` (121⭐) | ✅ SKILL.md 可跨平台 | 极低 |
| 领星 MCP | `zach22-1999/lingxing-mcp` (28⭐) | ⚠️ 领星非赛狐 | 参考架构 |
| Amazon Ads MCP | `ppcprophet/amazon-ads-mcp` (4⭐) | ⚠️ 直接调 Amazon Ads API | 需改成通过赛狐 API |
| 赛狐 API 拉取 | FZH 项目 `SELLFOX_API/` | ✅ 已验证 | 无 |
| FZH 广告分析 | FZH 项目 `advertise/` | ⚠️ 未充分验证 | 需要运营专家审核逻辑 |

**策略思考**：理想情况下，不应该从零写广告分析逻辑——那是运营专家的领域。更好的路径可能是：
1. 用 `claude-ads` + `amazon-skills` 的 SKILL.md 做分析指导
2. 用 `SELLFOX_API/` 做数据拉取（已验证）
3. 运营专家通过 Agent 迭代分析规则（而非开发者硬编码）
4. IvyeaOps 提供「电商运营工作台应该长什么样」的 UX 参考

---

## 八、待独立调研的开放问题

以下问题本调研未能充分回答，需要新 Agent 独立研究：

### 8.1 桌面+Web 双轨同步架构

- 如何让 Git 仓库的 `AGENTS.md` / `.agents/skills/` / `docs/` 同时服务于桌面端和 Web 端？
- Open WebUI 能否直接挂载 Git 仓库作为知识源？
- IvyeaOps 是否支持外部 Git 仓库的知识导入？
- 如果桌面端用户改了 SKILL.md 并 git push，Web 端如何自动感知？

### 8.2 赛狐 API 对接的难易度

- Open WebUI Python Tool 能否直接复用 `SELLFOX_API/` 的认证代码（OAuth + HMAC-SHA256）？
- IvyeaOps 的领星对接有哪些可以抽象为通用 ERP 对接层的部分？
- 赛狐 API 和领星 API 的数据模型差异有多大？

### 8.3 运营专家如何参与规则迭代

- `claude-ads` / `amazon-skills` 的分析逻辑是否适合 FZH 的类目（家居纺织品）？
- 运营专家（非技术）能否通过 Agent（Codex/Cursor）修改 SKILL.md 来调整分析规则？
- 如何设计「规则配置」（JSON/YAML）让运营容易修改？

### 8.4 各平台对 SKILL.md 的兼容性

- Open WebUI 如何加载和触发 SKILL.md？（通过 Skills 功能还是 Tools？）
- IvyeaOps 的 Skill 中心和 SKILL.md 标准的兼容度？
- Odysseus 对 SKILL.md 的支持程度？

### 8.5 是否需要"定时拉取 vs Chat 触发拉取"

- 用户明确说"不一定非要定时，chat 操作执行拉取并分析"
- 但自动化（定时）是否有独立价值？比如每天早上自动拉报告并推送钉钉摘要

---

## 九、各候选方案在本场景下的优劣（待独立验证）

> ⚠️ 以下是本调研作者的初步判断，**可能带有偏见**。新 Agent 应基于上述开放问题独立评估。

### 方案 A：Open WebUI + 自定义 Tools

**假设优势**：Tool 系统灵活、社区大、OIDC 现成
**需验证**：能否挂载 Git 仓库 MD 文档？能否直接加载 SKILL.md？与桌面端的文档同步方案？
**关键风险**：单维护者（1人+兼职贡献者）、许可证限制（品牌保留）

### 方案 B：IvyeaOps 改造（领星→赛狐）

> **[偏差标注 4]** 作者在调研过程中曾以「领星写死、社区极小、无 OIDC」等理由快速否决 IvyeaOps，但未充分评估：其电商业务模块（广告分析、市场调研、Listing 生成、Skill 中心）的复用价值、AI 一句话生成 Skill 的独特能力、Win 免环境 exe 对非技术同事的便利性。此外，IvyeaOps 作者 Hector 也是深圳跨境电商运营负责人，他的实际使用经验可能比技术评估更有价值。
>
> **[偏差标注 5]** 作者之前将「领星写死」作为否决 IvyeaOps 的核心理由，但犯了一个关键错误：**没有对比「改 API 端点的工作量」和「从零造电商业务逻辑的工作量」**。后者的隐性成本远高于前者。

**工作量对比（需新 Agent 独立验证）**：

| 工作项 | 方案 A: Open WebUI 从零建 | 方案 B: Fork IvyeaOps 改 API |
|--------|:---:|:---:|
| 部署 | 1 Docker 命令 | Docker Compose 或 Win exe |
| 赛狐 API 调用 | Python Tool ~200行 (可复用 SELLFOX_API/) | 替换领星 API → 赛狐 API (有限、机械) |
| 数据模型映射 | 从零设计 | 领星字段 → 赛狐字段 (有限) |
| 认证 | 无（OIDC 现成） | 领星 OAuth → 赛狐 OAuth+HMAC (可复用 SELLFOX_API/) |
| **广告分析 UI + 逻辑** | **从零设计+开发** | **已有**（搜索词诊断/ACOS报表/5桶分类） |
| **市场调研模块** | **从零设计+开发** | **已有**（关键词/竞品/类目洞察） |
| **Listing 生成** | **从零设计+开发** | **已有** |
| **Skill 中心** | Open WebUI 有 Skills 功能但无「AI 自动生成 Skill」 | **已有**（一句话→AI 生成 Skill） |
| **安全护栏（写操作）** | **从零设计+开发** | **已有**（双开关+三重复核+回滚快照+熔断） |
| **Win 免环境部署** | ❌ 需要 Docker | **已有**（Win x64 exe，免 Python/Node） |
| OIDC | ✅ 原生 | ❌ 需自建（但他们已有 OIDC 桥接器） |
| 社区支持 | 大（146K stars） | 极小 |

**关键结论**：「领星写死」是**有限、可计量的 API 替换工作**。而从零建电商运营平台是**开放式、需要运营领域知识的工作**——用户（张克勇）明确表示他不是广告专家，无法判断分析逻辑是否准确。Hector（IvyeaOps 作者）作为运营负责人已经把自己日常工作的分析逻辑做进了代码里，这些逻辑可能是本方案最大的隐性价值。

**假设优势**：已有电商业务模块、Windows 免环境 exe、AI 生成 Skill
**需验证**：领星改赛狐的实际工作量？社区支持？OIDC 对接方案？
**关键风险**：AGPL-3.0、社区极小、代码质量（vibe coding）

### 方案 C：两者混合

**假设**：IvyeaOps 的电商业务逻辑 + Open WebUI 的 Chat/Tools/OIDC
**需验证**：两个系统如何集成？各自维护什么？

### 方案 D：Odysseus

**假设**：AGPL-3.0、集成工作空间
**需验证**：4 容器部署在 4C8G 上是否可行？OIDC 对接？
**关键风险**：太新（2026.5 发布）、无社区商店

---

## 十、关键 URL 索引

### 基础设施
- new-api: https://github.com/QuantumNous/new-api
- new-api 部署文档: `new-api-deployment/AGENT_HANDOFF.md` (项目内)
- new-api-dingtalk-oidc: `new-api-dingtalk-oidc/` (项目内)
- api.vilavi.cn 后台: https://api.vilavi.cn/

### 对比平台
- Open WebUI: https://github.com/open-webui/open-webui | https://docs.openwebui.com
- Odysseus: https://github.com/odysseus-dev/odysseus
- IvyeaOps: https://github.com/Hector-xue/IvyeaOps | https://www.ivyea.com
- Dify: https://github.com/langgenius/dify
- n8n: https://github.com/n8n-io/n8n
- Hermes Agent: https://github.com/NousResearch/hermes-agent

### Amazon 广告生态
- claude-ads: https://github.com/AgriciDaniel/claude-ads
- amazon-skills (zach): https://github.com/zach22-1999/amazon-skills
- lingxing-mcp: https://github.com/zach22-1999/lingxing-mcp
- amazon-ads-mcp: https://github.com/ppcprophet/amazon-ads-mcp
- amazon-ppc-advanced-skills: https://github.com/nospicyplease/amazon-ppc-advanced-skills
- advertising-hub: https://github.com/itallstartedwithaidea/advertising-hub
- awesome-amazon-seller-tools: https://github.com/nexscope-ai/awesome-amazon-seller-tools
- awesome-amazon-seller-tools (mirror): https://github.com/smart-seller/awesome-amazon-seller-tools

### 代码沙箱
- E2B: https://github.com/e2b-dev/e2b
- Daytona: https://github.com/daytonaio/daytona
- OpenSandbox: https://github.com/alibaba/OpenSandbox

### 参考项目
- claudecodeui (IvyeaOps 移植源): https://github.com/claudecodeui/claudecodeui
- SKILL.md 标准: https://www.agensi.io/learn/ai-agent-interoperability

### 服务器
- 阿里云轻量活动: https://www.aliyun.com/daily-act/ecs/activity_selection
- 4C8G 轻量: ¥99/月, ¥1,159/年, 70G ESSD, 200M 带宽, 不限流量
- 4C8G ECS 通用算力型 u2i: ¥1,252/年 (1M 带宽起步)

### 本调研的已有文档（项目内）
- AI Agent 桌面端对比: `docs/ai-agent-desktop-comparison.md`
- Codex 安装指南: `docs/codex-desktop-setup-guide.md`
- 非技术团队 Agent 指南: `docs/non-tech-team-agent-guide.md`
- 企业 Agent 知识系统: `docs/enterprise-agent-knowledge-system.md`
- Amazon 广告调研: `advertise/docs/research/2026-06-16-amazon-advertising-analysis-research.md`
- Amazon 广告总体规划: `advertise/docs/specs/2026-07-02-ad-analysis-master-plan.md`
- Web Agent 平台调研: `docs/research/web-agent-platform-comparison-2026.md`
- AI for Amazon Ops 2026: `docs/ai-for-amazon-ops-2026.md`
- FZH 选型结论: `docs/solutions/integration-issues/fzh-unified-ai-access-conclusion.md`

---

## 十一、给未来 Agent 的独立调研指南

本调研文档作者（Claude Agent）在对比过程中**有倾向于 Open WebUI 的偏差**，原因包括：被其 Tools 系统和社区规模吸引，可能低估了 IvyeaOps 业务模块的复用价值，对 RAG 和 OIDC 的重要性可能有过度强调。

**你需要独立判断的事项**：

1. **不要直接接受本调研的倾向** — 基于你自己的分析重新评估
2. **桌面+Web 双轨同步** — 这是本调研遗漏的核心架构问题，请重点研究
3. **赛狐 API 对接** — 亲自阅读 `SELLFOX_API/` 代码，评估在各平台的集成难度
4. **IvyeaOps 代码深度审计** — 判断领星改赛狐的实际工作量，而不仅仅是"写死领星"的表面判断
5. **与 zach (amazon-skills 作者) 和 Hector (IvyeaOps 作者) 沟通** — 他们是深圳跨境电商运营实战者，可以问他们实际使用体验
6. **验证各平台对 SKILL.md 的兼容性** — 这决定了能否统一桌面端和 Web 端的知识体系
7. **不要假设"一个大平台解决一切"** — 可能需要组合方案

**操作步骤**：
1. 通读本文 + 本调研引用的所有已有文档
2. 亲自访问各平台 GitHub 仓库，Read 代码和文档
3. 针对"开放问题"（第八节）逐项研究
4. 形成你自己的独立判断
5. 向用户（张克勇）汇报你的发现，而不是重复本调研的结论

