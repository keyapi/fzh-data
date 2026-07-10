---
okf: v0.1
type: Research
title: Google AI — 知识库管理方案调研（OKF 替代方案 + 银行级知识库设计）
date: 2026-07-10
tags: [okf, knowledge-management, ai-agent, monorepo, documentation, rag, banking]
source: https://share.google/aimode/yFq00aWTlGPFQov3X
---

# Google AI 知识库管理调研对话

> 完整对话记录。来源：Google AI Mode shared conversation.
> 关键结论已落地到 `AGENTS.md` 规则 11 + `scripts/update_index.py` + 三层路由架构。

---

## Q1: OKF 标准有没有更好的替代？

OKF（开放知识格式）提供了一套极简的「Markdown + YAML」标准，方便 AI Agent 读取。然而，它缺乏深度的语义结构。根据你的具体使用场景，目前有以下几种更专业或更普及的替代方案：

### 1. 知识图谱标准（适合强逻辑、复杂关系的知识管理）

- **RDF / SPARQL**: 语义网的黄金标准。能够精准定义实体与实体之间的关系，适合合规要求高、逻辑严密的专业领域。
- **Knowledge Graph (图数据)**: 如 Neo4j 标准，适合多跳推理（Hop），避免 Agent 在文件间漫游导致逻辑跑偏。

### 2. 传统企业文档标准（适合需要人类深度阅读的场景）

- **DITA**: 结构化信息标准标记语言。历史悠久，在制造业和大型科技公司非常成熟。非常适合传统文档管理，但对 AI 原生支持不如 OKF。

### 3. AI Agent 指令/上下文标准（适合给特定 AI 喂系统级 Prompt）

- **AICodingRules** (.ai.yml / AICodingRules.org): 专门针对编程智能体（AI Coding Agent）的代码规范和行为约束标准，比零散的 OKF 文件更有针对性。
- **AGENT.md / SPEC.md**: 许多开发者社区推广的单文件 Agent 配置文件，比 OKF 更加轻量，专注于"如何使用该代码库"。

### 4. 高级文档整理工具（直接对标 OKF 的想法）

- **LLM Wiki (Karpathy 原型)**: 由 AI 先驱 Andrej Karpathy 提出，通过大模型自我编译，自动去重、更新和连接 Markdown 维基。
- **Markform**: 使用带特定注释的 Markdown 格式管理数据架构、文档和表单，也是 Agent 生态中常用的替代方案。

### 5. 什么时候该用什么？

- 如果要给企业业务系统（如 BigQuery）定义规则，推荐继续使用 **OKF** 或企业级知识框架 (EKF)。
- 如果是复杂的行业本体论和术语表，**RDF** 是更好的替代。
- 如果是 AI 编程助手或工作流配置，使用 **.ai.yml** 标准更加高效。

---

## Q2: Claude 操作软件 + 写代码 + 沉淀企业知识库，三合一场景如何设计？

针对这种多合一混合场景，建议采用**"三层分离、相互联动"**的架构标准：

### 1. 软件操作层（替代 OKF 定义 API 和工具）

- **OpenAPI / Swagger 标准 (JSON/YAML)**：Claude 等主流大模型对 OpenAPI 的原生解析能力远超 OKF，能自动生成准确的工具调用参数。
- **MCP (Model Context Protocol)**：由 Anthropic 推出的模型上下文协议。搭建 MCP 服务端，封装内部软件查询功能。

### 2. 代码编程层（替代 OKF 的规则约束）

- **MDC / .cursorrules 文件**：AI 编码时自动加载，避免重复犯错。
- **AI_RULES.md / SPEC.md**：仓库根目录的 AI 指引文件，只写代码生成的"硬性约束"。

### 3. 企业内部知识库层（替代 OKF 的文档管理）

- **双链 Markdown (Obsidian / Logseq 规范)**：引入 `[[知识点]]` 双向链接。图谱结构可以让 Claude 在检索时顺着链接找到相关的所有上下游经验。
- **Front Matter 元数据规范**：标准 YAML 格式标注元数据（category, tags, last_updated, status）。

### 最佳实践落地建议

```
your-project/
├── .cursorrules               # 代码层
├── mcp-server/                # 操作层
└── docs-knowledge/            # 知识层
    ├── README.md              # 总索引
    └── 01-erpnext-auth.md     # 带 YAML 头部的经验文档
```

---

## Q3: 不用 API 的纯手工操作 + 用户需求背景 + bug 分析 + 安装踩坑经验 + 带代码？

核心诉求：轻量、实用、基于 Git 仓库，像传统图书馆一样清晰、条理化地管理。

### OKF 支持代码引用

OKF 标准原生支持代码引用。OKF 的本质就是「YAML 元数据 + Markdown 文本」，完全可以在其中自由嵌入 Markdown 代码块（\`\`\`python）。

### 推荐的图书馆式 Git 知识库结构

```
company-knowledge-base/
├── README.md                  # 知识库总目录（图书大厅索引）
├── 01_User_Demands/           # 1号柜：用户需求与背景调研
├── 02_Bug_Analysis/           # 2号柜：Bug 分析与排查全记录
├── 03_Dev_Environment/        # 3号柜：安装、依赖与踩坑经验
└── 04_Manual_Operations/      # 4号柜：纯人工无API的操作指南
```

### 单个文档的编写规范（SOP 断言式）

每篇文档包含完整的：业务背景 → 调研过程 → 依赖教训 → 核心代码 → 人工校验步骤。

**关键原则**：文档从"日记体"改为"断言式（SOP）"——不要写碎碎念和故事背景，用 `核心强约束` 框起来，让 AI 一眼抓到关键。

---

## Q4: 我创建的文档 Agent 读取没问题，但新开对话或别人 git clone 之后跑不顺？

核心痛点：**上下文漂移**与**知识无法泛化**。

你当前的 Agent 跑得顺是因为你和它在同一个 Context 里。新 Agent 面对一堆"操作手册"，只知道"发生过什么"，却不知道"现在遇到这个问题，我该去哪个抽屉里拿哪本书"。

### 解决方案

**1. 建立"图书大厅索引"（README.md 的特殊写法）**

在 README.md 里写明"寻宝指南"，告诉新 Agent 在什么场景下、去读哪个目录的什么文件。

**2. 文档从"日记体"改为"断言式（SOP）"**

直接在文档最显眼的地方，用 `⚠️ 核心强约束` 框起来。

**3. 利用元数据（YAML Front Matter）进行"硬检索"**

写一个 Python 脚本，扫描所有 .md 文件的 YAML 头部，自动生成一个 JSON 字典（知识地图）。

---

## Q5: 我维护很多子项目，上层 index 是否及时更新？

这是整个对话中**最重要的一段调研**，直接催生了我们项目的三层架构：

### 核心发现

1. **Agent 的"近视眼"特性**：AI 工具没有全局"实时向量预索引"机制，Agent 默认不会主动跳出当前文件夹去修改根目录的 index。
2. **上下文的层级继承**：Agent 启动时从子文件夹向上遍历加载 CLAUDE.md/AGENTS.md，但不会主动维护上层总索引。

### 三种解决方案

| 方案 | 描述 | 我们采用 |
|------|------|---------|
| **A: 联动双写指令** | 在 AGENTS.md 写入强约束规则，要求 Agent 完成子项目后同步更新根索引 | ✓ 规则 11 |
| **B: 自动化脚本** | `update_index.py` 扫描 OKF YAML 自动生成 index.md | ✓ 已实现 |
| **C: 去中心化** | 放弃上层 Index，每个子文件夹完全自治 | 部分采用 |

---

## Q6: 银行科技子公司运营部门如何设计知识库？

### 四层演进设计

**一、知识源头层**：结构化断言 OKF/SOP 规范，对 YAML 字段进行金融场景定制：
- `id`, `type`, `domain`, `trigger_condition`, `impact_level`, `last_verified`

**二、存储与检索层**：图书馆式 Git 仓库 + 本地轻量向量化（BGE-Large + Milvus/PGVector）

**三、消费与发现层**（最核心）：
1. 静态代码扫描阶段：Agent 对比当前上下文与知识库 `trigger_condition`
2. 动态运行监控阶段：Log Agent 拿着错误日志去向量知识库模糊检索
3. 需求实施前置调研阶段：Agent 读取 index.json 主动提醒相关历史教训

**四、运营与防腐层**：
- 引入"知识半衰期"机制：`status: verified` + `review_due`
- 每半年 AI 审计 Agent 扫描过期文档，自动归档到 `09_Archive_History/`

### 第一步建议

1. 先开内网 GitLab 仓库
2. 规定所有排故复盘、实施准备、规则变更统一用 Markdown + YAML 头部
3. 有了结构化数据资产后，再接入 RAG/Agent

---

## Q7: 敏感数据脱敏 + 旧文档处理 + 无工单系统如何记录经验？

### 1. 敏感数据脱敏

- 制定"替换字典"规范，写入 AGENTS.md
- 用 Claude/Codex 自动洗数据（卡号→622202\*\*\*\*\*\*1234，行名→某国有大行，IP→10.x.x.x，人名→张工/李工）
- Git 权限隔离：main 分支脱敏公开版，dev-raw 分支核心骨干可见

### 2. 旧规范文档的结构化升级

三步法：
1. **分段切片**：大手册拆成独立的小 SOP 文件
2. **AI 加装 OKF 铠甲**：让 Claude 批量读取，自动生成 YAML 头部（`trigger_condition` 等）
3. 旧规范从"死文件"变成"带有触发标签、能被 Agent 检索到"的活资产

### 3. 无工单系统的经验沉淀

三种无痛机制：
1. **"复盘式聊天"**（最推荐）：员工下班前跟 Claude 口头复盘，AI 自动生成 OKF 文档
2. **定期捕获群聊**：每周把排故群聊记录丢给 Claude 梳理
3. **"有奖挑刺"**：高质量文档 = 绩效加分

---

## 分析总结

### 与我们项目的对照

| Google AI 建议 | 我们已实现 | 差距 |
|---------------|-----------|------|
| OKF 标准 (YAML + MD) | ✓ 全项目采用 | — |
| 方案 A：联动双写指令 | ✓ AGENTS.md 规则 11 | — |
| 方案 B：自动化索引脚本 | ✓ `scripts/update_index.py` | — |
| 图书馆式目录结构 | ✓ 每个模块 `docs/` bundle | — |
| 图书大厅索引 (README) | ✓ AGENTS.md 模块索引 | — |
| 断言式 SOP 文档 | 部分 | 旧文档仍是日记体 |
| 知识半衰期/审计 | 无 | 可考虑 |
| 旧文档 AI 加装 OKF 铠甲 | 无 | advertise/ 29 篇可批量升级 |
| 敏感数据脱敏机制 | 无 | 暂无金融数据 |

### 关键启示

1. **三层路由架构被验证正确**：AGENTS.md 路由表 + Skill 触发引擎 + index.md 全貌浏览，正对 Google AI 推荐的方案 A+B 组合
2. **下一步自然演进**：旧文档批量升级 + 引入知识半衰期（定期审计过期文档）
3. **对银行场景**：OKF + 结构化 YAML 足以起步，RDF/EKF 是过度设计
