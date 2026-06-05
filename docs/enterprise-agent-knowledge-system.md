# 企业多用户 AI Agent + 知识自动沉淀系统：可行性分析

> 问题：能否搞一个项目，组合网关 + Agent 运行时 + 知识库，实现多用户管理 + 经验自动积累？
>
> 最后更新：2026-06-05

---

## 一、结论先行：方向正确，已有先行者

我们的需求不是第一个。**多个公司和开源项目已经在 2026 年搭建了类似的架构**。核心拼图都已存在，知识自动提取仍是最大缺口。

---

## 二、网关到底能看到什么

### 2.1 Agent 读写文件时的数据流

**Agent 读取文件时**：内容被回传给 LLM → 出现在 HTTP 请求的 messages 中 → 网关可见
**Agent 写入文件时**：LLM 输出的代码 → 出现在 HTTP 响应中 → 网关可见
**Agent 不把内容传给 LLM 时**：网关看不到（本地操作不经过网络）

### 2.2 网关选型：LiteLLM（经代码验证）

| 属性 | 值 |
|------|-----|
| GitHub | [BerriAI/litellm](https://github.com/BerriAI/litellm) |
| Stars | **49,247**（`gh repo view` 验证） |
| 最后更新 | 2026-06-04 |
| 协议 | MIT |

**代码级验证过程**：

| 验证层 | 方法 | 证据 |
|--------|------|------|
| 数据库 schema | 直接读 `schema.prisma` | `LiteLLM_SpendLogs` 含 `messages Json` + `response Json` 字段 |
| payload 构造 | 读 `spend_tracking_utils.py` | `get_logging_payload` 从 `StandardLoggingPayload` 提取 |
| 仓库元数据 | `gh repo view --json stargazerCount,pushedAt` | 49,247 ⭐ |

**限制**：
- `SpendLogs.messages` 受 `MAX_STRING_LENGTH` 截断（保留头 35% + 尾 65%）
- 仅 `_arealtime` 类型调用会存储 messages
- 2026 年 4 月新增 `LiteLLM_WorkflowMessage` 表绕过截断（PR #26793）

### 2.3 `hermes proxy` 不是答案（代码验证）

`hermes proxy` 源码（`server.py`）的 docstring：

> *"intentionally minimal — does NOT mediate, log, transform, or rewrite request/response bodies."*

它只是一个 OAuth credential forwarder——剥离客户端 auth → 注入 OAuth token → 转发上游。不记录对话内容。

---

## 三、已有先行者：LiteLLM Agent Platform

**BerriAI（LiteLLM 团队）在 2026 年 5 月开源了 [litellm-agent-platform](https://github.com/BerriAI/litellm-agent-platform)**：

```
┌─────────────────────────────────────────────┐
│  Orchestrator (agent-deck / Hermes / Custom) │
│  - Task decomposition → DAG                  │
│  - Parallel scheduling                       │
│  - Cost tracking per agent                   │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│  LiteLLM Agent Platform (Kubernetes)          │
│  - Sandbox CRD per agent run                 │
│  - Vault proxy (stub→real credential swap)   │
│  - Postgres session persistence              │
│  - LiteLLM Gateway (routing, rate limits)    │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│  Harnesses (selectable per task)             │
│  Claude Code  │  Codex  │  Hermes  │  Aider  │
└─────────────────────────────────────────────┘
```

**与我们需求的对照**：

| 我们的需求 | LiteLLM Agent Platform |
|-----------|----------------------|
| 多用户 API 管理 | ✅ Vault proxy + stub tokens |
| 对话日志完整存储 | ✅ LiteLLM Gateway `messages` + `response` |
| 支持 Claude/Codex 本地执行 | ✅ 多 harness 可选 |
| 知识自动提取 | ❌ 仍未解决 |

---

## 四、Hermes + Claude Code 双栈架构（已验证的社区方案）

[完整教程](https://dev.to/akaranjkar08/i-built-the-hermes-claude-code-dual-stack-orchestrator-meets-coder-heres-the-full-architecture-228a) | 来源：dev.to 2026

```
Telegram → Hermes (VPS $5/月, 7×24)
              │  MCP over SSH tunnel (双向 stdio)
              ↓
           Claude Code (本地 MacBook)
```

**通信方式**：不是 HTTP 代理，是 **SSH stdio 隧道 + MCP 协议**。

```json
// 本地 Claude Code 注册远端 Hermes
"hermes": {
  "command": "ssh",
  "args": ["-T", "root@vps-ip", "hermes mcp serve"]
}
```

**角色分工**：
- Hermes（VPS）：编排、Telegram/钉钉 gateway、持久记忆（SQLite）、cron。**不写代码**
- Claude Code（本地）：编码、文件操作、git。**完整代码库访问**

**知识共享方式**：每小时 cron 导出 Hermes 记忆 → markdown → Claude Code 通过 CLAUDE.md 读取。不是自动对话提取。

**可靠性问题**：SSH 隧道是"整个方案中最脆弱的一环"，MCP 调用有 200-400ms 延迟。

---

## 五、实际落地案例

### 5.1 Shopify River（5,938 员工，2026）

- 部署在**公开 Slack 频道**（非私信）
- 30 天内 5,938 名员工使用，覆盖 4,450 个频道
- 12.5% 的合并 PR 由 River 编写
- **合并率从 36% → 77%**（2 个月内），靠的是**众包集体改进**，不是模型重训
- 核心机制：公开可见 → 员工观察他人提示词 → 有机知识扩散

### 5.2 MCP Gateway Registry #665（"Agent 的 StackOverflow"）

[GitHub Issue](https://github.com/agentic-community/mcp-gateway-registry/issues/665) | 2026 年 3-4 月 |

- Agent 自报问题/解决方案到共享知识库
- 解决方案验证循环：不同 Agent 验证 → 置信度上升；执行失败 → 置信度下降
- 三级信任：平台认证 → 社区签名 → 自行报告
- **Token 节省 60-80%**（已知方案被检索到时）
- KinthAI：31 个 Agent 共享同一知识库运行中

### 5.3 Corellis（28 Agent，8 周验证）

[GitHub](https://github.com/CorellisOrg/corellis) + [dev.to 原文](https://dev.to/jay_wong_45c807c6799b4fb7/how-we-ran-28-ai-agents-on-a-single-server-and-what-broke-1pbf)

- 基于 OpenClaw，单服务器 64GB RAM
- 四层记忆：Personal（5KB cap）→ Member → Channel（embeddings）→ Company（审核过）
- 纠错晋升管道：同一错误 2 次 → 晋升规则 → 推送全队
- 8 周：500+ 纠正 → 47 条全队规则；API 成本 $2,400→$800/月

### 5.4 Hermes 舰队学习能力（v0.13.0+）

[Hermes v0.13.0 Release](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.5.7)

- **Kanban 看板 + 黑板架构**：多 Worker 从同一看板认领任务
- **交接合同（Handoff Contracts）**：Agent 间定义输入/输出格式和验证门禁
- **幻觉门禁**：Worker 声称完成任务但未完成时自动触发
- **自动 Skill 生成**：同类型任务重复执行后工具调用减 60%+
- **风险**：自生成 Skill 有安全隐患（V2EX 用户：第 7 天自动合入半成品 PR）

---

## 六、知识自动提取：2026 最大缺口

| 项目 | 做了什么 | 成熟度 |
|------|---------|--------|
| **IBM ALTK-Evolve** | Agent 交互轨迹 → 自动挖掘通用规则 | 研究原型 +8.9% |
| **IBM Agent Mentor** | 聚类执行轨迹 → 自动生成纠正性提示词 | 论文 |
| **agent-triage** | 提取行为规则，回放对话找根因 | v0.2.0 开源 |
| **ai-knot** | 对话 → 结构化事实 → 衰减 + 检索 | v0.9.3 |
| **Dnotitia AKB** | Agent 原生知识库（对话/决策/输出） | 2026 年 6 月开源 |

**没有现成的"对话日志 → 团队知识"产品。** 2026 年 Agent 可观测性行业承认这是最大的缺口。

---

## 七、务实推荐

### 7.1 现在就做

```
LiteLLM Gateway (Docker, 49K⭐)
  ├── 多用户 Virtual Key + TPM/RPM/预算
  ├── messages + response → PostgreSQL
  └── WorkflowMessage 表（不截断，长会话友好）
```

### 7.2 需要自建

~200 行 Python 脚本：每周 LLM 扫描日志 → 提取候选规则（参考 IBM 频率+影响+置信度） → 生成 AGENTS.md 补丁 → 人工审核合入

### 7.3 可选扩展

- **Hermes VPS**（$5/月）：7×24 编排 + Telegram/钉钉 gateway
- **Hermes + 本地 Claude Code**：MCP over SSH 桥接（200-400ms 延迟）
- **Shopify 模式**：公开对话 → 众包知识扩散

---

## 八、调研日志

1. **初始推荐 new-api** → 用户质疑 → 查源码确认只记 Token 不记全文 → 废弃
2. **补充推荐 Squirrel + AgentLens** → 57 ⭐ / 2 ⭐ → 废弃
3. **发现 LiteLLM** → 49,247 ⭐ → 查 schema + payload 构造代码 → 确认
4. **误判 `hermes proxy`** → 查源码发现只是 credential forwarder → 修正
5. **发现 LiteLLM Agent Platform** → BerriAI 自己做了我们想做的事
6. **发现 Shopify River + MCP Registry + Dnotitia** → 企业级知识共享已有先行者
7. **Corellis + Hermes v0.13** → 舰队学习有可复用的架构模式
8. **知识自动提取仍是无解缺口** → IBM 论文+多个开源原型，但无产品化方案

---

## 九、数据源索引

| 引用 | 链接 | 可信度 | 验证方式 |
|------|------|--------|---------|
| LiteLLM | [GitHub](https://github.com/BerriAI/litellm) | ⭐⭐⭐⭐⭐ | `gh repo view` + `schema.prisma` + `spend_tracking_utils.py` |
| LiteLLM Agent Platform | [GitHub](https://github.com/BerriAI/litellm-agent-platform) | ⭐⭐⭐⭐ | 开源，pre-1.0 |
| `hermes proxy` 源码 | [server.py](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/hermes_cli/proxy/server.py) | ⭐⭐⭐⭐⭐ | docstring 确认功能边界 |
| Hermes + Claude Code 双栈 | [dev.to](https://dev.to/akaranjkar08/i-built-the-hermes-claude-code-dual-stack-orchestrator-meets-coder-heres-the-full-architecture-228a) | ⭐⭐⭐⭐ | 完整教程+配置代码 |
| Hermes v0.13.0 Release | [GitHub](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.5.7) | ⭐⭐⭐⭐ | 官方 Release Notes |
| Shopify River | [ZenML](https://www.zenml.io/llmops-database/building-a-public-ai-agent-workspace-for-organizational-learning) | ⭐⭐⭐⭐ | 生产数据 5,938 员工 |
| MCP Registry #665 | [GitHub Issue](https://github.com/agentic-community/mcp-gateway-registry/issues/665) | ⭐⭐⭐ | 设计讨论，未落地 |
| Corellis | [GitHub](https://github.com/CorellisOrg/corellis) + [dev.to](https://dev.to/jay_wong_45c807c6799b4fb7/how-we-ran-28-ai-agents-on-a-single-server-and-what-broke-1pbf) | ⭐⭐⭐⭐ | 开源+长篇实测 |
| IBM ALTK-Evolve | [ibm.com](https://www.ibm.com/new/announcements/altk-evolve-on-the-job-learning-for-ai-agents) | ⭐⭐⭐⭐ | 官方公告 |
| IBM Agent Mentor | [arXiv 2604.10513](https://arxiv.org/html/2604.10513v1) | ⭐⭐⭐⭐⭐ | 同行评审 |
| agent-triage | [GitHub](https://github.com/converra/agent-triage) | ⭐⭐⭐ | v0.2.0 |
| Dnotitia AKB | 新闻稿 | ⭐⭐ | 2026 年 6 月开源 |
