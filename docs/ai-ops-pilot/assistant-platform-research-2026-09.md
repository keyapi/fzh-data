---
okf: v0.1
type: Research
title: 2026-09 企业 AI 助手与 Agent 载体调研
description: 核实 ChatGPT Business、Workspace Agents、MCP、Dify、n8n、Copilot Studio、Gemini Agent Platform 与 Open WebUI 的能力边界，并给出 FZH 分级架构建议
tags: [ai-pilot, chatgpt-business, workspace-agents, mcp, enterprise-agent, architecture]
timestamp: 2026-09-16
sources:
  - https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business
  - https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt-beta
  - https://help.openai.com/en/articles/12628342-company-knowledge-in-chatgpt
  - https://help.openai.com/en/articles/8798878-building-and-publishing-a-gpt
  - https://help.openai.com/en/articles/20001519-custom-gpt-retirement-and-migration-faq
  - https://docs.dify.ai/en/guides/workflow/node/code
  - https://docs.dify.ai/en/guides/workflow/node/http-request
  - https://docs.dify.ai/en/guides/knowledge-base
  - https://docs.dify.ai/en/guides/application-publishing/launch-your-webapp-quickly
  - https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/
  - https://docs.n8n.io/code/code-node/
  - https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-langchain.mcptrigger/
  - https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-mcp
  - https://cloud.google.com/products/agent-builder
  - https://docs.openwebui.com/features/workspace/knowledge/
---

# 2026-09 企业 AI 助手与 Agent 载体调研

> 调研日期：2026-09-16。产品变化很快，本文只把官方资料中能核验的能力写成结论；厂商宣传中的 ROI 数字不作为 FZH 选型依据。

## 1. 结论先行

### 1.1 ChatGPT Business 已不只是「聊天 + 上传文档」

截至 2026-09，ChatGPT Business 已有三层可用能力：

1. **公司知识 / 文件层**：Company Knowledge、连接应用、上传知识文件；适合问答、查资料、生成表达。
2. **共享任务层**：Workspace Agents 可配置可复用流程，接应用与工具，发布到团队目录，可在 ChatGPT/Slack 使用、定时运行或由 API 触发。
3. **外部工具层**：Business 管理员可用 developer mode 创建、测试和发布远程 MCP app；MCP 可暴露搜索、读取、交互 UI 与写操作。

因此，老板所说的「一个 Workspace、4 个标准助手」在产品层面**可以实现**。但「能实现」不等于「把仓库拖进去就会执行」。

### 1.2 外部 `skills + docs + scripts` 不能原样装进 ChatGPT

仓库工具箱的三类内容要分别处理：

| 仓库资产 | ChatGPT 中的对应方式 | 是否直接复用 |
|---|---|---|
| `docs/`、SOP、模板、事实资料 | Company Knowledge、插件/Agent 参考资料，或 MCP 的 search/fetch | **内容可复用**，但需抽取、清洗、版本与权限治理 |
| `SKILL.md` 中的任务说明、判断规则、输出格式 | Workspace Agent / 插件的可复用 instructions/skill | **语义可迁移**，不是直接执行仓库文件 |
| Python/CLI 脚本、赛狐/ERPNext 客户端 | 封装成远程 HTTPS API、MCP tool，或由 n8n/Dify 等执行层调用 | **不能直接上传后运行**；必须服务化 |

OpenAI 的迁移方向也印证了这一分层：其 Custom GPT 退休说明把 GPT instructions 迁为插件中的 skill，把 connected apps 迁为 apps。也就是说，「技能说明 + 工具」正在成为平台原生结构，但**本地 Git 仓库不会自动成为运行时**。

### 1.3 对 FZH 最合适的不是重新押注一个大平台，而是「ChatGPT 前台 + Git 真源 + MCP 薄适配层」

推荐架构：

```text
运营人员
  └─ ChatGPT Business Workspace Agent（统一入口，低门槛）
       ├─ Company Knowledge / curated docs（只读知识）
       └─ FZH MCP app（只读工具，首期）
            ├─ sellfox.search_terms / ad_report
            ├─ erpnext.item / inventory（按需）
            ├─ nas.product_material_index（先返回目录/元数据）
            └─ 调用仓库内已验证脚本或 n8n 工作流

Git 仓库 = instructions、schemas、脚本、测试、版本记录的 source of truth
NAS = 原始产品资料库，不直接整盘复制到模型
```

这条路能利用老板已经决定购买的 GPT Workspace，又保留用户熟悉的 Git 化治理与既有赛狐 PoC。Open WebUI/IvyeaOps 不必立即废弃，但从「主入口候选」降为：

- ChatGPT 原生 Agent/MCP 达不到的隔离执行、批处理或专用看板；
- 供应商锁定、成本或数据驻留出现问题时的备用前台；
- 工程人员调试工具，而不是首批运营入口。

## 2. 先统一「助手」的三种成熟度

| 等级 | 本质 | 能做什么 | 做不到什么 | FZH 例子 |
|---|---|---|---|---|
| **L1 知识助手** | 指令 + 经整理的知识 + 固定输出模板 | 查资料、写 Listing、按模板复盘、引用来源 | 不能稳定获取实时赛狐数据；不能执行仓库脚本 | 产品表达助手 V1 |
| **L2 工具助手** | L1 + 只读 API/MCP | 实时取数、运行确定性计算、返回结构化结果 | 若无外部执行服务，仍不能任意跑仓库代码 | 广告复盘助手 V1 |
| **L3 业务 Agent** | L2 + 多步工作流、代码执行、计划/触发、人工审批 | 跨系统流程、批处理、监控、生成待执行动作 | 需要权限、日志、幂等、错误恢复和长期运维 | 库存风险/经营 Agent；未来才做 |

**30 天试点应只承诺 L1 + L2。** L3 是第二阶段工程，不应塞进「4 个助手 V1」里。

## 3. ChatGPT Business 能力核验

### 3.1 Workspace Agents

官方说明显示，Workspace Agents 面向 Business 和 Enterprise：

- 为重复任务和工作流创建 Agent；
- 发布前测试；
- 选择模型与 reasoning effort；
- 连接 apps/tools；
- 分享给团队或发布到团队目录；
- 在 ChatGPT 与 Slack 中使用；
- 支持 schedule 与 API trigger；
- Agent builder 可限制每个 app 可执行的动作，管理员可查看活动与用量。

这比 2025 年的 Custom GPT 更接近老板想要的「团队标准助手」。但它仍是**编排与交互层**，业务系统能力来自连接的 app/MCP/API。

### 3.2 Company Knowledge 与文件知识

Company Knowledge 对 Business、Enterprise、Edu 可用，可从支持的连接应用和自建 MCP app 取企业知识。它解决的是检索与引用，不是完整知识治理：

- 源系统权限仍生效；安装插件不会自动授予数据权限；
- 适合查资料与综合回答；
- 自定义 app 在 Company Knowledge 场景主要使用 search/fetch；
- 写操作应放到明确的工具动作，而非知识检索里。

对 NAS 的含义：**先建目录与元数据索引，不要把 `/产品信息` 全量上传。** 现有 `nas_itemgroup_folders/` 已证明 `/产品信息/{物料组}/调研报告|设计稿|图片|视频` 的结构和扫描能力存在，可扩成只读索引服务。

### 3.3 外部 API 与 MCP

Business 已支持 full MCP beta，但有重要边界：

- 只能直接连接**远程 MCP server**；本地 stdio server 不能直接连。私网/本机服务需 Secure MCP Tunnel 或部署为可达服务。
- Business 仅管理员/Owner 能启用 developer mode、创建测试并发布 app；成员不能自行发布。
- MCP 可提供读、写、交互 UI；重要写操作可能要求确认，高风险动作可能被阻断。
- Business 在当前版本中，app 发布后不能原地更新工具/元数据，需要重新创建并发布；Enterprise/Edu 才有更细 RBAC、动作开关与刷新 diff。
- Agent mode 不使用自定义 app；Deep Research 对自定义 app 只读。Workspace Agents 则有独立的 per-agent action controls。
- 移动端当前不支持 MCP app，网页端为主。

**FZH 结论**：技术上可把赛狐、ERPNext、NAS 索引封成一个 `FZH Ops` MCP app，供多个 Workspace Agent 复用。首期只发布只读工具，既符合赛狐广告无写 API的事实，也降低 Business 治理较弱的风险。

### 3.4 上传脚本与代码执行的准确说法

- 上传 `.py` 文件给知识助手，最多是让模型阅读/解释，不等于在公司环境中部署运行。
- ChatGPT 的数据分析沙箱可对会话文件做 Python 分析，但它不是仓库的长期运行环境：依赖、凭证、网络、版本和审计均不同。
- 生产脚本应留在受控服务、容器、n8n/Dify 工作流或现有 PoC 中，通过 MCP/API 暴露**窄接口**。
- 不要给 Agent 一个「任意 shell」作为首期能力；应把脚本包装成 `pull_search_terms(shop, date_range)`、`build_ad_review(dataset_id)` 这类有 schema 的工具。

## 4. 其他平台在 2026-09 的定位

### 4.1 Dify：最适合做「表单/聊天前台 + RAG + 轻量工作流」

官方能力：知识库、外部知识 API、HTTP Request、Python/JavaScript Code node、Web App、批处理与结果管理。

边界：Code node 沙箱禁止文件系统、网络请求和系统命令；外部访问要走 HTTP node；它不是直接运行现有仓库脚本的通用服务器。

适合 FZH 的场景：如果不采用 ChatGPT Workspace，Dify 可快速给运营一个表单化广告复盘或产品表达 Web App。但它不能复用老板的 ChatGPT Business 席位，等于再引入一个前台与账号体系。

### 4.2 n8n：最适合做「确定性执行层 / MCP 网关」

官方能力：AI Agent 调工具、HTTP/大量连接器、JS 与原生 Python Code node、自托管、MCP Server Trigger，可把 n8n workflows 暴露给 MCP 客户端。

适合 FZH 的场景：

- 把赛狐取数、格式校验、固定计算、结果落盘做成确定性工作流；
- 通过 MCP Server Trigger 暴露给 ChatGPT Workspace Agent；
- 给每次执行留下日志、重试与输入输出。

它不应作为运营人员直接使用的聊天前台，而应藏在 ChatGPT 后面。

### 4.3 Microsoft Copilot Studio / Google Agent Platform

两者都已有 MCP、企业连接器、治理与发布体系，适合已经深度绑定各自云/办公套件的大企业。Google 的官方案例包括 PayPal 用 Agent Builder 的 ADK、可视化追踪和多 Agent 工作流。

对 FZH：当前无证据表明公司已标准化在 Microsoft Power Platform 或 Google Cloud Agent 体系。30 天内引入会增加采购、身份、开发和治理面，不优于利用现有 ChatGPT 决策。

### 4.4 Open WebUI

2026 文档显示 Open WebUI 的知识层已明显增强：混合检索、多种 OCR/抽取、目录同步、Git/S3 等远程同步、agentic retrieval 与实验性 `kb_exec`。它依然适合自托管、模型可替换和知识库主权。

但它的主要价值仍是**自有 AI 前台**。既然老板已经选 ChatGPT Business，短期再让 6–8 名新手学习 Open WebUI，会形成两个入口、两套助手与两套知识发布流程。故不宜作为本次试点主入口。

### 4.5 IvyeaOps / 专用板

专用板的价值不是替代聊天，而是把高频、确定、需审核的动作做成表格、筛选、批注和导出。广告候选的运营审就更适合板，而不是长对话。保留 `/ops` 思路，但先让 ChatGPT Agent 通过 MCP 调取同一数据，再按实际使用决定是否启动完整门户。

## 5. 「成熟案例」能证明什么，不能证明什么

公开成熟案例主要集中在两类：

1. **大规模企业知识检索**：如 Morgan Stanley 的顾问研究知识助手。这证明「受控资料 + 检索 + 专业人员判断」成熟，但不证明 Agent 可替代经营判断。
2. **深度绑定既有企业栈的流程 Agent**：如 PayPal 在 Google Agent Builder 上做可追踪的多 Agent 与支付流程。这证明大企业可把 Agent 放进生产流程，但前提是专门平台、工程团队、追踪和治理。

这些案例共同支持的不是「先造 4 个万能助手」，而是：

- 选一个窄流程；
- 接到真实且有权限的数据；
- 输出可审核；
- 保留人工决策；
- 用日志和业务指标验证。

## 6. FZH 推荐落地方案

### 6.1 30 天只做两个 Agent

#### A. 产品表达 Agent（L1）

- 前台：ChatGPT Workspace Agent。
- 知识：选 1–2 个产品族，从 NAS 中人工确认过的产品设计、调研、优秀 Listing 与表达规范。
- 输入：SKU/物料组、站点、目标人群、已有素材。
- 输出：固定模板，明确事实来源与待确认项。
- 不做：自动抓竞品规模；没有外部付费数据时不声称市场容量。

#### B. 广告复盘 Agent（L2）

- 前台：ChatGPT Workspace Agent。
- 工具：FZH MCP 只读调用既有赛狐报告拉取和确定性预处理。
- 输出：数据摘要 + 异常项 + 候选动作 + 证据行；最终由运营判断。
- 不做：写回赛狐、自动否词、自动改价；`advertise/` 规则不作真理。

### 6.2 Git 与平台各自负责什么

| 资产 | 权威位置 | 发布方式 |
|---|---|---|
| 工具代码、API schema、测试、阈值配置 | Git | CI/人工审查后部署 MCP/n8n 服务 |
| Agent instructions / skills | Git 为真源 | 经过评审后同步到 Workspace Agent/Plugin |
| 业务原始资料 | NAS/源系统 | 只读索引或选择性同步 |
| 面向模型的整理稿 | Git `docs/` 或受控知识库 | 带 Owner、版本、来源、失效日期 |
| 运行日志与运营反馈 | Agent/admin 日志 + 试点记录 | 每周复盘，回写修订单 |

### 6.3 首周资料盘点应怎么做

现有项目已确认：

- `nas_itemgroup_folders/` 已在 NAS `/产品信息/` 下按 ERPNext 物料组建 404 个目录；
- 标准子目录是「调研报告 / 设计稿 / 图片 / 视频」；
- 已有只读扫描脚本，可统计文件数、大小、最后修改并保存快照；
- 但这只证明**容器与扫描能力存在**，不证明资料完整、最新、可抽取或可作为事实源。

W1 应交付「资料资产清单」，字段至少包括：物料组/路径、文件类型、文件数、Owner、最后更新、是否可解析、是否重复、是否含敏感信息、是否可进知识库、缺失项。先抽样 1–2 个产品族，不做全盘 OCR。

## 7. 决策表

| 方案 | 新手体验 | 复用老板 GPT | Git/脚本复用 | 30 天可行 | 建议 |
|---|---:|---:|---:|---:|---|
| ChatGPT Workspace Agent + curated docs | 高 | 是 | 低到中 | 高 | 产品表达首选 |
| ChatGPT Workspace Agent + FZH MCP | 高 | 是 | 高 | 中高 | 广告复盘首选 |
| Dify 一体化 | 高 | 否（模型 API 另计） | 中 | 高 | 备选前台/表单任务 |
| n8n 直接给运营 | 低 | 间接 | 高 | 中 | 只做后台执行层 |
| Open WebUI + 工具 | 中 | 否 | 高 | 中 | 暂不作为本次主入口 |
| Copilot Studio / Google Agent Platform | 高 | 否 | 中 | 低 | 有云栈战略后再评估 |
| 直接让运营用 Git/CLI Agent | 低 | 否 | 最高 | 低 | 仅技术人员使用 |

## 8. 对老板计划的直接修订意见

1. 把「4 个标准 AI 助手」改为「首批 2 个 Workspace Agent：一个 L1、一个 L2」。
2. 每个 Agent 必须写清：载体、知识源、工具、输入输出、Owner、审批点、验收指标。
3. W1 不再假设产品资料为空，也不承诺一次导入 30–50 份；先对 NAS/ERPNext 路径做抽样盘点与可解析性评估。
4. 「市场与竞品研究」在没有采购数据源前，只能作为研究流程模板，不承诺市场容量等数据型结论。
5. 技术底座优先做一个只读 FZH MCP app，而不是重启一个新的综合门户。
6. 第 30 天同时验收：运营采用率、事实正确率、耗时变化，以及至少一个业务指标；不能只验收「发布了几个助手」。

## 9. 风险与止损线

- **产品变化风险**：Workspace Agents、Plugins、Custom GPT 正处于迁移期；instructions 和工具必须在 Git 留真源，避免平台内孤本。
- **Business 治理上限**：与 Enterprise 相比，RBAC、连接器动作控制、发布后更新流程较弱。首期只读、少管理员、窄工具。
- **Prompt injection / MCP 风险**：只接自有可信 server；工具参数白名单；服务端再次鉴权，不信任模型传来的店铺、时间或文件路径。
- **知识质量风险**：NAS 有文件不等于有知识。未经 Owner 确认的旧稿不得进入「事实资料」。
- **维护人绑定风险**：AI 负责人维护平台和发布机制，业务 Owner 维护内容与规则；不得由一人长期包办四个 Agent。

## 10. Sources

### OpenAI

- [ChatGPT Workspace Agents for Enterprise and Business](https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business)
- [Developer mode and MCP apps in ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt-beta)
- [Company knowledge in ChatGPT](https://help.openai.com/en/articles/12628342-company-knowledge-in-chatgpt)
- [Sharing and publishing GPTs](https://help.openai.com/en/articles/8798878-building-and-publishing-a-gpt)
- [Custom GPT retirement and migration FAQ](https://help.openai.com/en/articles/20001519-custom-gpt-retirement-and-migration-faq)

### Platforms

- [Dify Code node](https://docs.dify.ai/en/guides/workflow/node/code)
- [Dify HTTP Request node](https://docs.dify.ai/en/guides/workflow/node/http-request)
- [Dify Knowledge](https://docs.dify.ai/en/guides/knowledge-base)
- [Dify Workflow Web Apps](https://docs.dify.ai/en/guides/application-publishing/launch-your-webapp-quickly)
- [n8n AI Agent node](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/)
- [n8n Code node](https://docs.n8n.io/code/code-node/)
- [n8n MCP Server Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-langchain.mcptrigger/)
- [Microsoft Copilot Studio MCP](https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-mcp)
- [Google Gemini Enterprise Agent Platform](https://cloud.google.com/products/agent-builder)
- [Open WebUI Knowledge](https://docs.openwebui.com/features/workspace/knowledge/)
