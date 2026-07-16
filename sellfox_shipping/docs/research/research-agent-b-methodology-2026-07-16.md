---
module: sellfox_shipping
date: 2026-07-16
problem_type: architecture_pattern
component: tooling
severity: medium
tags:
  - sellfox-shipping
  - multi-carrier
  - agent-interface
  - research-methodology
  - excel-template
  - "cli-vs-mcp"
applies_when:
  - "Designing multi-carrier systems with Chinese logistics providers lacking public APIs"
  - "Evaluating CLI vs MCP for AI Agent interfaces in small-team contexts"
  - "Planning phased architecture with mixed API and Excel-based carrier integration"
  - "Conducting independent research to validate or challenge existing architecture conclusions"
---

# 赛狐尾程打单 P1 独立调研：方法论与关键分歧

> 本调研于 2026-07-16 独立执行，未参考已有 `sellfox-shipping-research-and-architecture.md`。
> 两个调研独立到达相似结论（Karrio 借鉴、ERPNext Shipping 不可用、Excel 模板必要），
> 但在 **Agent 界面选型**上存在关键分歧。
> 调研文档见 `sellfox_shipping/docs/research/research-agent-b-2026-07-16.md`。

## Context

赛狐尾程打单系统需要对接 5 家跨境物流承运人生成发货标签。已有 Agent 做过一轮调研，
ONBOARDING.md 要求新 Agent 完全屏蔽已有结论独立执行第二轮，以获取多样性视角。

这种"隔离调研 + 后期对比"刻意制造认知多样性——两个 Agent 独立从零出发，
各自搜索、各自判断，最终交叉验证。

## 调研方法

遵循 ONBOARDING.md 六步开局 + 两阶段深度优先：

1. **Phase 0 — 广域搜索（5 路并行 tavily）**：多承运人开源方案、中国物流 API、MCP vs CLI benchmark、承运人抽象模式、后台任务队列
2. **Area 1 — 多承运人核心架构**：Karrio（30+ carriers, Django）、ERPNext Shipping（仅欧洲聚合商）、Saleor/Medusa.js/Sylius
3. **Area 2 — AI Agent 界面设计**：MCP vs CLI vs REST API 实证对比，2026 年 benchmark 数据
4. **Grilling 验证**：逐项确认关键决策，5 个结论在用户反馈中修正

关键技术：所有外部搜索保留原始 URL（36 条来源），GitHub 直接访问验证，商业平台提取架构模式而非照搬。

## 架构决策

### P1 只做 Excel，API 放 P2

5 家承运人中仅 FedEx（P2）和 GLS 有可用 REST API。Vite/亿龙达有 API 文档（用户确认，2026-06 与赛狐谈判中），但 P1 不依赖。
所有 5 家都需要 Excel 兜底——API 接入后，物流商后台仍接受 Excel 上传。

API 和 Excel 不是 fallback 关系，而是互斥的集成模式。

### CLI + REST API，暂不引入 MCP（关键分歧）

**独立调研证据**：
- CLI 比 MCP 便宜 10-35x token 消耗（Intune 实测：4,150 vs 145,000 tokens）
- MCP 可靠性 72% vs CLI 100%（75 次 benchmark）
- Perplexity 2026-03 缩减 MCP，飞书/钉钉发布 CLI toolkit
- 用户当前生产环境：Claude Desktop + REST API，无 MCP，完全不影响使用
- DeepSeek（主力模型）不原生支持 MCP

**实践方案**：CLI（Typer --json）给 Agent + REST API（FastAPI）给 Web UI，共享 Service Layer。
后期用 `fastapi-mcp`（11.6k stars, MIT）一键暴露 MCP。

### YAML 配置 + AI 辅助生成 Excel 规则

每家承运人的 Excel 模板通过 YAML 配置定义（列映射、kg→lb 转换、电话号填充、文本截断）。
AI 从示例 Excel 推断规则，人工审核后落地。参考：DataFlowMapper AI-copilot 模式、GoRules ZEN Engine（Rust+Python, MIT）。

### Excel 转换做成可复用模块

转换逻辑可从 sellfox_shipping 和其他项目 import，而非嵌入打单系统内部。
这是"能力思维"而非"功能思维"——可复用 Excel 转换能力 > 一次性打单功能。

### 不建大一统承运人抽象

API 承运人和 Excel 承运人的交互模型根本不同。2 个 API 承运人时不需要 Plugin/Registry。
等第 3 个 API 承运人真正接入时再抽象（YAGNI），与 sellfox-api-proxy 既有策略一致。

### SQLite + FastAPI BackgroundTasks

3-5 个物流同事，零运维成本。Docker Compose 单机部署，避免引入 Redis。
后期需要完整队列时用 SAQ（比 ARQ 快 8x）。

## Grilling 修正记录

| 原始结论 | 修正 |
|----------|------|
| Vite/亿龙达 无公开 API | 有 API 文档（用户微信群） |
| P1 API + Excel 双线 | P1 只做 Excel |
| API 失败降级 Excel | API 和 Excel 互斥，不存在降级 |
| 嵌入 sellfox_shipping | 做成可复用模块 |

## 与已有方案的差异点

本独立调研与 `sellfox-shipping-research-and-architecture.md`（2026-07-15）在以下方面一致：
- Karrio 架构借鉴价值
- ERPNext Shipping 不可用
- Excel 模板转换必要
- SQLite + Docker Compose 部署

以下方面存在差异或补充：
- **Agent 界面**：已有调研推荐 FastAPI + FastMCP + Typer 三界面；本调研推荐 CLI-first + REST API，MCP 推迟到 P2+
- **Vite API 确认**：已有调研标注为 "可能有 API"；本调研经用户确认有 API 文档
- **Grilling 修正**：提炼了 5 条被用户纠正的假设，防止后续 Agent 重复同类型错误
