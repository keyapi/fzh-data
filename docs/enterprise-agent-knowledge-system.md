# 企业多用户 AI Agent + 知识自动沉淀系统：可行性分析

> 问题：能否搞一个项目，组合网关 + Agent 运行时 + 知识库，实现多用户管理 + 经验自动积累？
>
> 最后更新：2026-06-05

---

## 一、结论

**方向正确，但网关模式优于端点模式。** 对 5 人非技术团队，LiteLLM 做 API 网关 + 日志 → 知识提取脚本，是最务实的。

---

## 二、网关到底能看到什么

### 2.1 能捕获的

| 数据类型 | 是否经过网关 | 前提 |
|----------|:---:|------|
| 用户文字输入 | ✅ | 在 HTTP messages 中 |
| LLM 输出（代码/文本/工具调用） | ✅ | 在 HTTP response 中 |
| 被 Agent 读入上下文的文件内容 | ✅ | Agent 回传给 LLM 的消息中 |
| Token 用量/延迟/错误 | ✅ | response headers |
| 用户身份 | ✅ | API Key → UserID |

### 2.2 不能捕获的

| 数据类型 | 原因 |
|----------|------|
| 工具执行结果（bash 输出等） | 在 Agent 本地执行，不经过 HTTP |
| 本地文件操作 | 只在 Agent 进程内，网关不可见 |
| Agent 不传给 LLM 的文件内容 | 如果 Agent 读了但不放进对话，网关看不到 |

**核心约束**：网关是网络层代理，只能捕获 HTTP 流量。本地 Agent 的操作（文件读写、bash 执行、浏览器截图）不在网络路径上。

### 2.3 被否定过的错误认知

| 错误 | 实际情况 | 验证方式 |
|------|---------|---------|
| `hermes proxy` 能捕获对话日志 | 只是 OAuth credential forwarder，一行日志都不记 | 读源码 `server.py`，docstring 明确写了"does NOT log" |
| new-api 能存对话全文 | 只记 Token 计数，`Content` 字段是"消费 500 tokens" | 读源码 `model/log.go` |
| Shopify River 是本地 Agent 方案 | 是纯集中式 Slack bot + cloud LLM | ZenML 案例研究原文 |
| LiteLLM Agent Platform 给本地 Agent 用 | 在 K8s 上跑 Agent 容器，不涉及本地电脑 | GitHub README |

---

## 三、网关选型：LiteLLM

| 属性 | 值 |
|------|-----|
| GitHub | [BerriAI/litellm](https://github.com/BerriAI/litellm) |
| Stars | **49,247**（`gh repo view` 验证） |
| 最后更新 | 2026-06-04 |
| 协议 | MIT |

### 3.1 为什么是 LiteLLM 而不是 new-api

| 需求 | new-api（36,958⭐） | LiteLLM（49,247⭐） |
|------|:---:|:---:|
| 多用户配额（Org→Team→User→Key） | ✅ | ✅ + USD 预算 |
| 请求/响应**全文**存储 | ❌ 只有 Token 计数 | ✅ `messages` + `response` JSON |
| Agent 长会话不截断 | ❌ | ✅ `WorkflowMessage` 表（PR #26793） |
| Anthropic 原生协议 | ✅ | ✅ |

### 3.2 代码级验证

| 证据 | 来源 | 内容 |
|------|------|------|
| `messages` Json 字段 | [`schema.prisma`](https://raw.githubusercontent.com/BerriAI/litellm/main/schema.prisma) | `messages Json? @default("{}")` |
| `response` Json 字段 | 同上 | `response Json? @default("{}")` |
| payload 构造 | [`spend_tracking_utils.py`](https://raw.githubusercontent.com/BerriAI/litellm/main/litellm/proxy/spend_tracking/spend_tracking_utils.py) | `get_logging_payload` 从 `StandardLoggingPayload` 提取 |

### 3.3 限制

| 限制 | 影响 | 解决方案 |
|------|------|---------|
| `MAX_STRING_LENGTH` 截断 | 长会话被截断（保留头 35% + 尾 65%） | `WorkflowMessage` 表（不截断） |
| messages 仅 `_arealtime` 类型 | 部分调用类型不存 messages | 需验证你用的 Agent 是否产生 `_arealtime` 调用 |
| `store_prompts_in_spend_logs` 需开启 | 默认开，但需确认 | 部署时检查 |

---

## 四、可行架构设计

### 4.1 推荐方案（网关模式）

```
┌─────────────────────────────────────────────────────┐
│              网关层 (LiteLLM, Docker)                 │
│                                                      │
│  DeepSeek Key → N 条 Virtual Key，每人独立配额        │
│  messages + response → PostgreSQL                   │
│  WorkflowMessage 表（长会话不截断）                   │
│  支持 Anthropic 协议（Claude Desktop 直接连）         │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│           知识提取层（半自动，~200 行 Python）         │
│                                                      │
│  每周跑一次：                                         │
│  1. LLM 扫描 LiteLLM 的 request_logs / WorkflowMessage│
│  2. 提取：新规律 / 踩坑 / 成功模式                    │
│  3. 频率 ≥2 次的标记为候选规则                         │
│  4. 生成 AGENTS.md 补丁草稿 → 人工审核 → 合并         │
│                                                      │
│  参考：IBM ALTK-Evolve（频率+影响+置信度）             │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│              知识存储层 (Git + AGENTS.md)             │
│                                                      │
│  fzh-data/                                          │
│  ├── AGENTS.md          ← 审核过的团队规则            │
│  ├── docs/lessons/      ← 踩坑记录                   │
│  └── .agents/skills/    ← 可复用的技能                │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│         回馈层 (git pull → Agent 自动加载)            │
│                                                      │
│  每人 git pull → Agent 自动读 AGENTS.md               │
│  新同事 clone → 自动获得所有团队经验                    │
└─────────────────────────────────────────────────────┘
```

### 4.2 为什么不用端点模式（Beacon）

[Beacon](https://github.com/Asymptote-Labs/agent-beacon)（145⭐，v0.0.41）理论上能捕获更全面的数据（文件读写、bash 输出），但：
- **必须每台电脑安装**（端点代理），非技术同事无法自行部署
- 145 星，v0.0.41，早期阶段
- 输出 JSONL 到本地文件，需要额外搭建转发管道才能集中分析

**对 5 人非技术团队，网关模式（Docker 一行部署）比端点模式（每台电脑装代理）更务实。**

### 4.3 被评估过但否决的方案

| 方案 | 否决原因 |
|------|---------|
| **Hermes + Claude Code 双栈** | 单人深度定制方案，5 个故障模式（SSH 隧道脆弱、不支持并发、Skill 不兼容） |
| **Shopify River 模式** | 纯集中式 Slack bot，不涉及本地 Agent |
| **LiteLLM Agent Platform** | 在 K8s 上跑 Agent 容器，不涉及本地电脑 |
| **Beacon 端点模式** | 每台电脑装代理，对非技术同事不现实 |

---

## 五、被验证的生产案例

### 5.1 Corellis — 28 Agent 舰队学习

[GitHub](https://github.com/CorellisOrg/corellis) + [dev.to 原文](https://dev.to/jay_wong_45c807c6799b4fb7/how-we-ran-28-ai-agents-on-a-single-server-and-what-broke-1pbf) | MIT | 基于 OpenClaw

- **架构**：Controller（宿主机） + 28 Lobster（Docker 容器，每个~2GB RAM）
- **四层记忆**：Personal（5KB cap）→ Member → Channel（embeddings）→ Company（审核过）
- **纠错晋升管道**：同一错误 2 次 → Agent 规则 → 全队规则（人工确认）
- **8 周**：500+ 纠正 → 47 条全队规则；API 成本 $2,400→$800/月

### 5.2 MCP Gateway Registry — Agent 的 StackOverflow

[GitHub Issue #665](https://github.com/agentic-community/mcp-gateway-registry/issues/665) | 2026 年 3-4 月

- Agent 自报解决方案 → 其他 Agent 验证 → 置信度升降 → Token 节省 60-80%
- 三级信任：平台认证 → 社区签名 → 自行报告

### 5.3 Hermes v0.13.0 — 多 Agent Kanban

[Release Notes](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.5.7)

- Kanban 看板 + 黑板架构：多 Worker 认领同一看板任务
- 交接合同 + 幻觉门禁：防止 AI 团队空转
- 自动 Skill 生成：同类任务重复后工具调用减 60%+
- **注意**：自进化 Skill 有安全隐患（V2EX 实测第 7 天自动合入半成品 PR）

---

## 六、各组件成熟度

| 组件 | 状态 | 需自建 |
|------|:---:|:---:|
| LiteLLM 网关（多用户+日志） | ✅ 49K⭐, Docker | - |
| PostgreSQL 日志存储 | ✅ LiteLLM 自带 | - |
| 日志→知识提取脚本 | ❌ | ~200 行 Python |
| Git + AGENTS.md 知识库 | ✅ | - |
| Agent 自动加载 AGENTS.md | ✅ 已经在用 | - |
| 自动知识闭环 | ❌ 2026 行业缺口 | IBM 论文已验证可行 |

---

## 七、调研日志

1. 推荐 new-api → 用户质疑 → 查源码确认只记 Token → 废弃
2. 推荐 Squirrel + AgentLens → 57⭐/2⭐ → 废弃
3. 发现 LiteLLM → 49K⭐ → schema + 源码验证 → 确认
4. 误判 `hermes proxy` → 查源码发现只是 credential forwarder → 修正
5. 误判 LiteLLM Agent Platform → 确认是 K8s 云端方案 → 不适用
6. 误判 Shopify River → 确认是集中式 Slack bot → 不适用
7. 评估 Beacon → 需每台电脑装代理 → 对非技术团队不现实
8. 评估 Hermes + Claude Code 双栈 → 单人方案，5 个故障模式 → 不适用
9. **最终方案**：LiteLLM 网关 + 自建知识提取脚本

---

## 八、数据源索引

| 引用 | 链接 | 可信度 | 验证方式 |
|------|------|--------|---------|
| LiteLLM | [GitHub](https://github.com/BerriAI/litellm) | ⭐⭐⭐⭐⭐ | `gh repo view` + `schema.prisma` + `spend_tracking_utils.py` |
| LiteLLM WorkflowMessage PR #26793 | [GitHub PR](https://github.com/BerriAI/litellm/pull/26793) | ⭐⭐⭐⭐⭐ | PR + schema |
| `hermes proxy` 源码 | [server.py](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/hermes_cli/proxy/server.py) | ⭐⭐⭐⭐⭐ | docstring |
| new-api `model/log.go` | [GitHub](https://github.com/QuantumNous/new-api) | ⭐⭐⭐⭐⭐ | 源码 |
| Hermes + Claude Code 双栈 | [dev.to](https://dev.to/akaranjkar08/i-built-the-hermes-claude-code-dual-stack-orchestrator-meets-coder-heres-the-full-architecture-228a) | ⭐⭐⭐⭐ | 完整教程+配置 |
| Corellis 28 Agent | [GitHub](https://github.com/CorellisOrg/corellis) + [dev.to](https://dev.to/jay_wong_45c807c6799b4fb7/how-we-ran-28-ai-agents-on-a-single-server-and-what-broke-1pbf) | ⭐⭐⭐⭐ | 开源+长篇实测 |
| Hermes v0.13.0 | [GitHub Releases](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.5.7) | ⭐⭐⭐⭐ | 官方 Release |
| MCP Registry #665 | [GitHub Issue](https://github.com/agentic-community/mcp-gateway-registry/issues/665) | ⭐⭐⭐ | 设计讨论 |
| Beacon | [GitHub](https://github.com/Asymptote-Labs/agent-beacon) | ⭐⭐⭐ | 145⭐, v0.0.41 |
| Shopify River | [ZenML](https://www.zenml.io/llmops-database/building-a-public-ai-agent-workspace-for-organizational-learning) | ⭐⭐⭐⭐ | 案例研究 |
| IBM ALTK-Evolve | [ibm.com](https://www.ibm.com/new/announcements/altk-evolve-on-the-job-learning-for-ai-agents) | ⭐⭐⭐⭐ | 官方公告 |
| IBM Agent Mentor | [arXiv 2604.10513](https://arxiv.org/html/2604.10513v1) | ⭐⭐⭐⭐⭐ | 同行评审 |
