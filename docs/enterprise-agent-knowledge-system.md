# 企业多用户 AI Agent + 知识自动沉淀系统：可行性分析

> 问题：能否搞一个项目，组合网关 + Agent 运行时 + 知识库，实现多用户管理 + 经验自动积累？

---

## 一、网关能看到什么

API 网关在 Agent 和大模型之间做代理，**天然能捕获所有经过它的数据**。

### 能捕获的

| 数据类型 | 示例 | 已有实现 |
|----------|------|---------|
| 用户输入（prompts） | "帮我把这个 Excel 按品类汇总" | ✅ 所有 LLM 网关 |
| 模型输出（responses） | 生成的代码、分析结果 | ✅ 所有 LLM 网关 |
| 工具调用请求 | `web_fetch("url")`、`bash("python script.py")` | ✅ 流式也支持 |
| Token 用量 | 输入 3,421 / 输出 892 | ✅ 所有网关 |
| 延迟、错误 | 429 rate limit、超时 | ✅ 所有网关 |
| 用户身份 | 哪个 Token/用户发起的 | ✅ new-api 有 |

**已验证的成熟网关**：[Squirrel LLM Gateway](https://github.com/mylxsw/llm-gateway)（Go，2026年4月）——请求/响应分开存储，流式也支持；[AgentLens](https://github.com/farzanhossan/agentlens)（零代码改动，改 base_url 就行）；[MLflow AI Gateway](https://mlflow.org/blog/mlflow-ai-gateway)（自动生成 trace）。

### 不能捕获的

| 数据类型 | 为什么 | 影响 |
|----------|--------|------|
| 工具执行结果 | `bash("python script.py")` 的输出在 Agent 本地执行 | 网关看不到脚本运行结果、Excel 内容、浏览器截图 |
| 本地文件操作 | Agent 用 Read 工具读 Excel → 网关只知道"调了 Read"，不知道 Excel 里有什么 | 丢失了大量业务上下文 |
| Agent 内部推理链 | 模型输出"我需要先理解数据"→ 然后做了什么，网关只知道模型的文本输出 | 丢失了决策过程 |

**核心矛盾**：网关能捕获"说了什么"，但捕获不了"做了什么"和"为什么这么做"。

---

## 二、已有哪些拼图

### 2.1 网关层：成熟

| 拼图 | 产品 |
|------|------|
| API 网关 + 多用户配额 | [new-api](https://github.com/QuantumNous/new-api)（36,958 ⭐） |
| 全量请求/响应日志 | [Squirrel LLM Gateway](https://github.com/mylxsw/llm-gateway)、[AgentLens](https://github.com/farzanhossan/agentlens) |
| Trace/可观测性 | [LangFuse](https://langfuse.com)（22.9k ⭐）、[LangSmith](https://smith.langchain.com) |

### 2.2 知识提取层：有论文和原型，无现成产品

**这是整个系统最薄弱的环节。** 2026 年的可观测性市场共识是：**trace → 知识自动提取，是最大的缺口。** 没有一个工具能自动把失败的 trace 转成可复用的教训。

最接近的：

| 项目 | 做了什么 | 成熟度 |
|------|---------|--------|
| **IBM ALTK-Evolve** | 从 Agent 交互轨迹中自动挖掘通用规则，评估频率/影响/置信度 | 研究原型（+8.9% 任务完成率） |
| **IBM Agent Mentor** | 聚类执行轨迹，识别"好"vs"坏"结果，自动生成纠正性提示词 | 论文（arXiv 2604.10513） |
| **Capital One 对话摘要管线** | 6 个 Agent 协作从对话中提取结构化知识 | 生产级（但用于客服场景，非编程 Agent） |
| **Elastic Knowledge Indicators** | 从日志自动提取实体/依赖/模式，7 天自清理 | 生产级（但用于基础设施可观测性，非 Agent 知识） |

### 2.3 知识存储层：有成熟方案

| 方案 | 适合场景 | 成熟度 |
|------|---------|--------|
| **Obsidian + Git** | 团队知识库，Markdown 原生，Agent 可读写 | 成熟（多个开源项目：Open Second Brain, Obsidian Second Brain） |
| **Corellis 四层记忆** | 人工 Agent 舰队，纠错晋升管道 | 生产验证（28 Agent，8 周，MIT 开源） |
| **Mem0**（57,665 ⭐） | 开发者 SDK，嵌入式记忆 | 成熟，但是给应用开发者用的 |
| **RAG + 向量数据库** | 语义搜索 | 成熟 |

### 2.4 反馈回馈层：最弱

**怎么让 Agent 在后续对话中自动用到积累的知识？** 现有的做法：

| 方式 | 例子 |
|------|------|
| Agent 启动时加载 AGENTS.md | 你已经在用了 |
| Agent 对话中说"请读 docs/xxx" | 手动，但有效 |
| MCP memory server（Monet/Mem0） | 半自动，但需要 Agent 主动查询 |
| 系统提示词注入（IBM Agent Mentor 的做法） | 自动，但还在研究阶段 |

---

## 三、可行的混合方案

### 3.1 务实版：现在就能搭

```
┌─────────────────────────────────────────────────────┐
│                   网关层 (new-api)                    │
│  DeepSeek Key → N 条 Token，每人独立配额              │
│  全量请求/响应日志 → JSONL 文件或 PostgreSQL          │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│              知识提取层（半自动）                      │
│                                                      │
│  每周/每两周跑一次：                                   │
│  1. LLM 扫描本周所有对话日志                           │
│  2. 提取：新发现的规律、踩过的坑、成功的模式            │
│  3. 生成 AGENTS.md 补丁 / Lessons Learned 草稿         │
│  4. 人工审核 → 合并到主 AGENTS.md                      │
│                                                      │
│  参考：IBM ALTK-Evolve 的"频率+影响+置信度"筛选逻辑     │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│              知识存储层 (Obsidian + Git)              │
│                                                      │
│  fzh-data/                                          │
│  ├── AGENTS.md          ← 审核过的团队规则           │
│  ├── docs/lessons/      ← 踩坑记录（按日期）         │
│  ├── docs/patterns/     ← 成功模式（按场景）         │
│  └── .agents/skills/    ← 可复用的技能               │
│                                                      │
│  参考：Corellis 四层记忆 + Obsidian Second Brain     │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│              回馈层 (AGENTS.md 自动加载)              │
│                                                      │
│  每人 git pull → Agent 自动读 AGENTS.md               │
│  新同事 clone → 自动获得所有团队经验                    │
│                                                      │
│  参考：Corellis"新 Agent 启动时自动加载全队规则"       │
└─────────────────────────────────────────────────────┘
```

**这个方案的关键瓶颈**：第 2 层（LLM 扫描日志 → 提取知识）现在需要你自己写。2026 年的可观测性工具只做到了"告诉你哪里出错了"，做不到"从错误中提炼教训"。

### 3.2 要多久、要什么

| 组件 | 现在就能用 | 需要自己写 |
|------|-----------|-----------|
| new-api 网关（多用户+日志） | ✅ Docker 一行部署 | - |
| 网关日志存储（PostgreSQL） | ✅ new-api 自带 | - |
| 日志→知识提取脚本 | ❌ 没有现成的 | **核心缺口**，需要写一个 LLM 驱动的分析 pipeline |
| Obsidian/Git 知识库 | ✅ | - |
| AGENTS.md 自动加载 | ✅ 你已经在用 | - |

"日志→知识提取"这个脚本的核心逻辑可以参考 IBM ALTK-Evolve：

```
1. 读取本周所有 conversation JSONL
2. 用 LLM 分析每条对话 → 提取 "新发现/踩坑/成功模式" 
3. 统计频率 → 出现 ≥2 次的标记为候选规则
4. 评估影响 → 如果规则被违反会造成什么后果
5. 生成 AGENTS.md 补丁草稿 → 人工审核 → 合并
```

这个脚本本身不复杂（~200 行 Python），关键在于**设计好 LLM prompt** 让它能准确从对话日志中识别有价值的知识。

### 3.3 网关能否捕获 Agent 生成的文件？

**不能直接捕获**——文件在同事的本地电脑上，网关是网络层的代理。

**间接方案**：
- 让 Agent 把重要输出（脚本、分析结果）**同时写入一个共享目录**（NAS 或 Git）
- 或者在对话结束时让 Agent 生成一个"会话摘要"，包含本次生成的关键文件路径和内容摘要
- 这是 Agent prompt 层面的约定，不是网关的自动能力

---

## 四、Honest Assessment

好的：多用户 API 管理 + 日志记录 → new-api 已完美解决，一行 Docker。

还需要自己做的：日志 → 知识的自动提取。IBM 和 Capital One 有论文和原型，但没有任何开源产品能直接拿来用。2026 年的整个 Agent 可观测性行业都承认这是一个未解决的缺口。

可以做但需要投入的：写一个"对话日志 → AGENTS.md 补丁"的 Python 脚本（~200 行），每周跑一次，人工审核后合并。这是目前最务实的路径——把"每周手动更新 Lessons Learned"变成"每周审核 AI 自动生成的草稿"。

不现实的部分：全自动闭环（Agent 犯错 → 系统自动学 → 下次自动避免）。IBM 的论文验证了这条路的可行性（+8.9% 任务完成率），但还没到产品化阶段。

---

## 五、数据源索引

| 引用 | 链接 | 可信度 |
|------|------|--------|
| IBM ALTK-Evolve (Agent 在职学习) | [ibm.com](https://www.ibm.com/new/announcements/altk-evolve-on-the-job-learning-for-ai-agents) | ⭐⭐⭐⭐ |
| IBM Agent Mentor (轨迹分析+自动纠正) | [arXiv 2604.10513](https://arxiv.org/html/2604.10513v1) | ⭐⭐⭐⭐⭐ |
| Capital One 对话摘要管线 | [EACL 2026](https://aclanthology.org/2026.eacl-industry.41/) | ⭐⭐⭐⭐⭐ |
| Corellis 28 Agent 舰队 | [GitHub](https://github.com/CorellisOrg/corellis) + [dev.to](https://dev.to/jay_wong_45c807c6799b4fb7/how-we-ran-28-ai-agents-on-a-single-server-and-what-broke-1pbf) | ⭐⭐⭐⭐ |
| Squirrel LLM Gateway | [GitHub](https://github.com/mylxsw/llm-gateway) | ⭐⭐⭐⭐ |
| AgentLens (零代码 LLM 代理) | [GitHub](https://github.com/farzanhossan/agentlens) | ⭐⭐⭐ |
| Obsidian Second Brain (33 命令) | [GitHub](https://github.com/eugeniughelbur/obsidian-second-brain) | ⭐⭐⭐ |
| Open Second Brain (Agent 自维护知识库) | [GitHub](https://github.com/itechmeat/open-second-brain) | ⭐⭐⭐ |
| 2026 Agent 可观测性行业报告 | [futureagi.com](https://futureagi.com/blog/best-ai-agent-observability-tools-2026/) | ⭐⭐⭐⭐ |
| "知识自动提取"是最大缺口 | [dev.to 可观测性总结](https://dev.to/utibe_okodi_339fb47a13ef5/i-evaluated-every-ai-agent-observability-tool-on-the-market-heres-whats-actually-missing-54c) | ⭐⭐⭐ |
