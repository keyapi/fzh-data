# 企业多用户 AI Agent + 知识自动沉淀系统：可行性分析

> 问题：能否搞一个项目，组合网关 + Agent 运行时 + 知识库，实现多用户管理 + 经验自动积累？
>
> 最后更新：2026-06-04

---

## 一、网关到底能看到什么

### 1.1 先厘清 Agent 读写文件时的数据流

用户对"网关能不能看到 Agent 本地读写的文件"存疑。实际流程如下：

**Agent 读取文件时：**
```
1. Agent 调 Read("数据源/通途导出.xlsx") → 本地执行，得到内容
2. Agent 把内容放进下一条发给 LLM 的消息:
   "我读了 Excel，表头是 SKU/仓库/数量，前5行是..."
3. → 网关在步骤 2 的 HTTP 请求中捕获到文件内容 ✅
```

**Agent 写入文件时：**
```
1. LLM 输出: "请在 analyze.py 中写入: import pandas as pd\n..."
2. → 网关在步骤 1 的 HTTP 响应中捕获到完整代码 ✅
3. Agent 本地执行 Write("analyze.py", "import pandas...")
4. Agent 告诉 LLM "文件已写入" → 确认消息也经过网关
```

**结论：网关不碰本地文件系统，但只要文件内容和代码出现在 Agent 与 LLM 的对话中，就能被网关记录。** 网关是网络层代理，看到的是 HTTP 请求/响应的全部内容。

### 1.2 网关能捕获的

| 数据类型 | 是否在请求/响应中 | 能否被网关捕获 |
|----------|:---:|:---:|
| 用户的文字输入 | ✅ messages 数组 | ✅ |
| Agent 的系统提示词（含 AGENTS.md） | ✅ system prompt | ✅ |
| 上传的图片 | ✅ base64 编码在 messages 中 | ✅（但体积大，存储成本高） |
| 被读取的文件内容 | ✅ Agent 回传给 LLM 的消息中 | ✅ |
| LLM 输出的代码/文本 | ✅ response choices | ✅ |
| 工具调用请求（名称+参数） | ✅ tool_calls | ✅ |
| Token 用量/延迟/错误 | ✅ response headers | ✅ |
| 用户身份 | ✅ API Key → UserID | ✅ |

**前提条件**：网关必须实际存储请求体和响应体，而不只是计费摘要。

### 1.3 网关不能捕获的

| 数据类型 | 为什么 |
|----------|--------|
| 工具执行的具体结果 | bash 输出、浏览器截图在 Agent 本地产生，不经过网关 HTTP |
| 文件是否成功写入磁盘 | Agent 告诉 LLM "写好了"≠文件真实存在，网关无法验证 |
| Agent 内部推理链 | 模型输出"我需要先理解数据"→后面的决策过程只有模型自己知道 |

---

## 二、网关选型：调研过程与最终推荐

### 2.1 第一次调研（已废弃）

最初推荐 `new-api`（36,958 ⭐）作为 API 网关。但经用户质疑后，核查代码发现：

**new-api `model/log.go` 真实字段：**
```go
Id, UserId, CreatedAt, Type, Content,      // Content 是文本描述如"消费500 tokens"
Username, TokenName, ModelName, Quota,       // 不是对话全文
PromptTokens, CompletionTokens, UseTime,     // Token 计数
ChannelId, TokenId, Group, Ip, RequestId     // 追踪信息
```

**没有 `request_body`，没有 `response_body`。** new-api 的日志是为计费设计的，不是为知识提取设计的。能回答"张三 14:32 用了多少 tokens"，不能回答"张三问了什么、模型答了什么"。

### 2.2 第二次调研（已废弃）

补充推荐了 Squirrel LLM Gateway（57 ⭐）和 AgentLens（2 ⭐）。但两者都是小型项目，不成熟。

### 2.3 最终推荐：LiteLLM

| 属性 | 值 |
|------|-----|
| GitHub | [BerriAI/litellm](https://github.com/BerriAI/litellm) |
| Stars | **49,247**（经 `gh repo view` 验证） |
| 最后更新 | **2026-06-04（今天）** |
| 定位 | Python SDK + Proxy Server（AI Gateway），调用 100+ LLM |
| 协议 | MIT |

**为什么 LiteLLM 是唯一正确选择**：

| 需求 | new-api | LiteLLM |
|------|:---:|:---:|
| 多用户配额（Org→Team→User→Key） | ✅ | ✅ 同样三级 + USD 预算 |
| 请求/响应**全文**存储 | ❌ 只有 Token 计数 | ✅ `messages` + `response` JSON 存 PostgreSQL/Supabase |
| 流式捕获 | ❌ | ✅ `StandardLoggingPayload` |
| Agent 长会话全文（不截断） | ❌ | ✅ 2026年4月 `WorkflowMessage` 表 |
| Anthropic 原生协议（非 OpenAI 格式） | ✅ | ✅ |
| Docker 一行部署 | ✅ | ✅ |

**LiteLLM 实际存储的字段**（来自代码和文档）：

```yaml
StandardLoggingPayload:
  model: "deepseek-v4-pro"
  messages: [{"role":"user","content":"帮我分析这个Excel的品类汇总..."}]   # 完整对话
  response: {"choices":[{"message":{"content":"..."}}]}                     # 模型完整输出
  end_user: "zhangsan"
  total_cost: 0.023
  response_time: 1.2
  status: "success"
  litellm_call_id: "uuid"
```

配置示例（Supabase/PostgreSQL 存储）：
```yaml
# config.yaml
general_settings:
  database_url: "postgresql://..."

litellm_settings:
  success_callback: ["supabase"]
  failure_callback: ["supabase"]

model_list:
  - model_name: deepseek-v4-pro
    litellm_params:
      model: openai/deepseek-chat
      api_base: https://api.deepseek.com/v1
      api_key: os.environ/DEEPSEEK_API_KEY
```

**结论**：多用户 API 管理 + 全量对话日志存储，**LiteLLM 一个项目全包了**。不需要 new-api + Squirrel 拼凑。

---

## 三、其他拼图

### 3.1 知识提取层：有论文和原型，无现成产品

**这是整个系统最薄弱的环节。** 2026 年 Agent 可观测性行业共识：**trace → 知识自动提取是最大缺口。** 没有一个工具能自动把对话日志转成可复用的知识点。

最接近的：

| 项目 | 做了什么 | 成熟度 |
|------|---------|--------|
| **IBM ALTK-Evolve** | 从 Agent 交互轨迹中自动挖掘通用规则，评估频率/影响/置信度 | 研究原型（+8.9% 任务完成率） |
| **IBM Agent Mentor** | 聚类执行轨迹，识别"好"vs"坏"结果，自动生成纠正性提示词 | 论文（arXiv 2604.10513） |
| **Capital One 对话摘要管线** | 6 个 Agent 协作从对话中提取结构化知识 | 生产级（用于客服场景，非编程 Agent） |
| **Elastic Knowledge Indicators** | 从日志自动提取实体/依赖/模式，7 天自清理 | 生产级（用于基础设施可观测性，非 Agent 知识） |

### 3.2 知识存储层：有成熟方案

| 方案 | 适合场景 | 成熟度 |
|------|---------|--------|
| **Obsidian + Git** | 团队知识库，Markdown 原生，Agent 可读写 | 成熟（Open Second Brain, Obsidian Second Brain） |
| **Corellis 四层记忆** | Agent 舰队，纠错晋升管道（经项目实测验证） | 生产验证（28 Agent，MIT 开源） |
| **Mem0**（57,665 ⭐） | 开发者 SDK，给 App 嵌入记忆功能 | 成熟，但不适合直接给团队用 |
| **RAG + 向量数据库** | 语义搜索 | 成熟 |

### 3.3 反馈回馈层：最弱

**怎么让 Agent 在后续对话中自动用到积累的知识？** 现有做法：

| 方式 | 例子 | 自动化程度 |
|------|------|:---:|
| Agent 启动时加载 AGENTS.md | 已经在用 | 自动 |
| Agent 对话中说"请读 docs/xxx" | 手动但有效 | 手动 |
| 系统提示词注入（IBM Agent Mentor 论文做法） | 自动但研究阶段 | 自动 |

---

## 四、可行的务实架构

### 4.1 推荐版（核心组件已成熟）

```
┌─────────────────────────────────────────────────────┐
│                网关层 (LiteLLM)                       │
│                                                      │
│  - DeepSeek Key → N 条 Virtual Key，每人独立配额      │
│  - 全量 messages + response → PostgreSQL JSON        │
│  - TPM/RPM 限流 + USD 预算上限                        │
│  - 支持 Anthropic 原生协议（Claude Desktop 直接连）    │
│                                                      │
│  一行部署: docker run -p 4000:4000 litellm           │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│              知识提取层（半自动，需自建）               │
│                                                      │
│  每周/每两周跑一次 Python 脚本：                        │
│  1. LLM 扫描 LiteLLM 的 request_logs 表               │
│  2. 提取：新发现的规律、踩过的坑、成功的模式            │
│  3. 统计频率 → 出现 ≥2 次的标记为候选规则               │
│  4. 生成 AGENTS.md 补丁草稿 → 人工审核 → 合并          │
│                                                      │
│  参考：IBM ALTK-Evolve（频率+影响+置信度筛选）          │
│        Corellis（同一错误 2 次 → 晋升规则）            │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│              知识存储层 (Obsidian / Git)              │
│                                                      │
│  fzh-data/                                          │
│  ├── AGENTS.md          ← 审核过的团队规则            │
│  ├── docs/lessons/      ← 踩坑记录（按日期）          │
│  ├── docs/patterns/     ← 成功模式（按场景）          │
│  └── .agents/skills/    ← 可复用的技能                │
│                                                      │
│  参考：Corellis 四层记忆 + Obsidian Second Brain      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│              回馈层 (AGENTS.md 自动加载)              │
│                                                      │
│  每人 git pull → Agent 自动读 AGENTS.md               │
│  新同事 clone → 自动获得所有团队经验                    │
│                                                      │
│  参考：Corellis"新 Agent 启动时自动加载全队规则"        │
└─────────────────────────────────────────────────────┘
```

### 4.2 各组件成熟度

| 组件 | 状态 | 说明 |
|------|:---:|------|
| LiteLLM 网关（多用户+全量日志） | ✅ 成熟 | 49,247 ⭐，一行 Docker |
| PostgreSQL 日志存储 | ✅ LiteLLM 自带 | Supabase 或自建 PG |
| 日志→知识提取脚本 | ❌ 需自建 | ~200 行 Python，核心难点是 LLM prompt 设计 |
| Obsidian/Git 知识库 | ✅ 成熟 | |
| AGENTS.md 自动加载 | ✅ 已经在用 | |

### 4.3 网关能否捕获 Agent 生成的文件？

**直接捕获：不能。** 文件在同事本地电脑上，网关是网络层代理。

**间接方案**：
- Agent 生成的代码/分析结果**在对话中已经出现过**（LLM 输出 → 网关捕获）
- 让 Agent 对话结束时生成"会话摘要"→ 自动记录关键文件和结论
- 约定 Agent 把重要输出同时写入 Git（`git add && git commit`）

### 4.4 Cursor 式蒸馏（不同话题，仅作对比）

Cursor 的"实时 RL"做的不是知识提取，而是用用户交互作为训练信号来**微调模型权重**：
- 收集数十亿 token 用户交互 → 提取隐式信号（编辑保留？追问？） → RL 更新权重 → 每 5 小时部署新检查点
- 需要万卡 GPU + 自研 RL 管线，与团队知识沉淀是两层不同的问题

---

## 五、Honest Assessment

**成熟的**：多用户 API 管理 + 全量对话日志 → LiteLLM 一个项目完美解决。49,247 星，今天还在更新，Docker 一行起。

**需要自建的**：日志 → 知识提取脚本。IBM 和 Capital One 有论文和原型，但没有任何开源产品能直接使用。2026 年整个 Agent 可观测性行业承认这是一个未解决的缺口。

**务实的**：写一个 ~200 行 Python 脚本，用 LLM 每周扫描 LiteLLM 的 `request_logs` 表，提取候选规则，生成 AGENTS.md 补丁草稿，人工审核后合并。这把你现在"手动更新 Lessons Learned"变成了"每周审核 AI 自动生成的草稿"——效率提升但不需要全自动。

**不现实的**：全自动闭环（Agent 犯错 → 系统自动学 → 下次自动避免）。IBM 论文验证了方向可行，但未产品化。

---

## 六、调研日志（保留中间讨论过程）

1. **初始推荐 new-api** → 用户质疑 → 核查代码发现只记 Token 不记对话全文 → 废弃
2. **补充推荐 Squirrel + AgentLens** → 用户指出 57 ⭐ / 2 ⭐ → 不成熟 → 废弃
3. **发现 LiteLLM** → 49,247 ⭐ → 同时覆盖配额管理 + 全量日志 → 最终推荐
4. **网关能否捕获本地文件 I/O** → 分析确认：文件内容出现在对话消息中就能捕获，但网关不碰本地磁盘
5. **Agent 读写文件内容验证** → Read 结果回传 LLM → 网关可见。Write 内容来自 LLM 输出 → 网关可见
6. **Monet/Mem0/Letta 定位澄清** → Monet 6⭐ 原型；Mem0 开发者 SDK；Letta Agent 平台。都不是团队知识库现成产品
7. **28 Agent 案例详解** → Corellis 开源，四层记忆+纠错晋升管道，不是可下载产品而是自己搭的系统

---

## 七、数据源索引

| 引用 | 链接 | 可信度 | 验证方式 |
|------|------|--------|---------|
| LiteLLM | [GitHub](https://github.com/BerriAI/litellm) | ⭐⭐⭐⭐⭐ | `gh repo view` 49,247 ⭐ |
| LiteLLM StandardLoggingPayload | [DeepWiki](https://deepwiki.com/BerriAI/litellm/6-observability-and-logging) | ⭐⭐⭐⭐⭐ | 代码级文档 |
| new-api 日志模型 | [model/log.go](https://github.com/QuantumNous/new-api) | ⭐⭐⭐⭐⭐ | 直接读源码 |
| IBM ALTK-Evolve | [ibm.com](https://www.ibm.com/new/announcements/altk-evolve-on-the-job-learning-for-ai-agents) | ⭐⭐⭐⭐ | 官方公告 |
| IBM Agent Mentor | [arXiv 2604.10513](https://arxiv.org/html/2604.10513v1) | ⭐⭐⭐⭐⭐ | 同行评审论文 |
| Capital One 对话摘要 | [EACL 2026](https://aclanthology.org/2026.eacl-industry.41/) | ⭐⭐⭐⭐⭐ | 顶会论文 |
| Corellis 28 Agent | [GitHub](https://github.com/CorellisOrg/corellis) + [dev.to](https://dev.to/jay_wong_45c807c6799b4fb7/how-we-ran-28-ai-agents-on-a-single-server-and-what-broke-1pbf) | ⭐⭐⭐⭐ | 开源+长篇实测 |
| Obsidian Second Brain | [GitHub](https://github.com/eugeniughelbur/obsidian-second-brain) | ⭐⭐⭐ | 开源项目 |
| 2026 Agent 可观测性报告 | [futureagi.com](https://futureagi.com/blog/best-ai-agent-observability-tools-2026/) | ⭐⭐⭐⭐ | 行业评测 |
| 知识自动提取是最大缺口 | [dev.to](https://dev.to/utibe_okodi_339fb47a13ef5/i-evaluated-every-ai-agent-observability-tool-on-the-market-heres-whats-actually-missing-54c) | ⭐⭐⭐ | 独立评测 |
| Monet（已弃用推荐） | [GitHub](https://github.com/team-monet/monet) | ⭐ | 6 ⭐ 原型 |
| Squirrel LLM Gateway（已弃用推荐） | [GitHub](https://github.com/mylxsw/llm-gateway) | ⭐⭐ | 57 ⭐ |
| AgentLens（已弃用推荐） | [GitHub](https://github.com/farzanhossan/agentlens) | ⭐ | 2 ⭐ |
