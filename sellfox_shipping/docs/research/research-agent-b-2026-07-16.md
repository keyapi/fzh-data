---
type: research
module: sellfox_shipping
created: 2026-07-16
updated: 2026-07-16
status: complete
agent: research-agent-b
method: >
  完全独立调研，未参考已有 P1 调研结论。
  两阶段：Phase 0 广域搜索（5路并行tavily）→ Area 1（多承运人架构）+ Area 2（AI Agent界面）。
  随后 /grill-me 与用户逐项确认关键决策。

---

## Grilling 修正记录

以下结论在 grilling 中被用户纠正或明确：

| 原始结论 | Grilling 修正 |
|----------|--------------|
| Vite/亿龙达 无公开 API | **有 API 文档**，用户在微信群里有资料。P1 先不纠结细节 |
| P1 API + Excel 双线 | **P1 只做 Excel 模式**，API 在 P2 |
| Excel 模板规则 YAML 配置 | YAML + **AI 辅助生成规则** + 人工兜底 |
| 嵌入 sellfox_shipping 实现 | 做成**可复用模块**，通途等场景也能 import |
| API 失败降级 Excel | **不成立**——API 和 Excel 是互斥的，不是 fallback 关系 |
---

# 赛狐尾程打单 — 独立调研文档

> 本调研完全独立执行，未阅读 `comprehensive-research-2026-07-15.md` 或已有架构决策文档。
> 所有结论基于独立搜索和源码阅读，如有与已有方案一致之处纯属巧合。

---

## 1. 调研方法

### 1.1 执行策略

深度优先，聚焦 2 个方向：
- **Area 1**：多承运人系统核心架构
- **Area 2**：AI Agent 友好界面设计

### 1.2 搜索工具

- tavily-search (advanced depth, 10 results/query)
- tavily-extract (GitHub repos + 文档)
- GitHub 直接访问 (Saleor, Medusa.js, ERPNext)

---

## 2. Area 1：多承运人核心架构

### 2.1 开源多承运人系统全景

#### Karrio（唯一成熟的开源多承运人方案）

- 30+ 承运人，Python/Django，Apache 2.0
- 架构：`Gateway → Proxy → Mapper` 三层，每个承运人独立 Python 包
- 定价：自托管免费，managed $499/月，商用 license $50,000/年
- 源码：<https://github.com/karrioapi/karrio>

**但 Karrio 不适合直接使用的原因**：
1. Django 全栈，与项目现有 FastAPI 生态不兼容
2. 不支持中国承运人（Vite/亿龙达、蜥国际、七条）
3. 商用 license $50k/年超出预算
4. 引入 Django ORM + GraphQL 会显著增加项目复杂度

**借鉴价值**：Proxy + Mapper 模式可以参考，但不直接使用。

#### ERPNext Shipping

- 仅支持 3 个欧洲聚合商：Packlink、LetMeShip、SendCloud
- Shipment doctype 只是个追踪记录文档，无内置标签生成
- 社区 fork (volkswagner/erpnext-shipping) 增加了 US 承运人但未合入主线
- eShipz 是商业 ERPNext 集成（需付费）
- 源码：<https://github.com/frappe/erpnext-shipping>
- 官方文档：<https://docs.erpnext.com/erpnext-shipping>

**结论**：ERPNext Shipping 对 FZH 场景无效。

#### Saleor (Django E-commerce)

- Shipping 模块侧重运费计算方法（ShippingMethod），不处理标签生成
- 适合理解电商中 shipping 的领域建模，但不是打单系统参考
- 源码：<https://github.com/saleor/saleor/tree/main/saleor/shipping>

#### Medusa.js (Node.js Headless Commerce)

- Fulfillment Provider 接口设计简洁：`createShipment()`, `getFulfillmentDocuments()`, `cancelFulfillment()`
- 插件式注册，第三方 provider 通过 npm 包扩展
- 参考价值：fulfillment 生命周期建模

#### 商业平台架构参考

| 平台 | 承运人数 | 借鉴点 |
|------|---------|--------|
| ShippyPro | 181+ | 中性模式（只用用户自己的承运人合同），与 FZH 需求一致 |
| PluginHive | 50+ | Shopify/WooCommerce 插件，多承运人标签生成的 UI 流程 |
| EasyPost | 100+ | Python SDK 的 Service Registry 模式 |

### 2.2 用户承运人 API 现状（独立验证）

| 承运人 | API 状态 | 证据 | 集成策略 |
|--------|---------|------|---------|
| **FedEx** | REST API + OAuth 2.0 | developer.fedex.com | P2 API 对接 |
| **Vite/亿龙达** | **无公开 API** | 官网仅有 WMS 功能介绍，未找到开发者文档 | **Excel 模板** |
| **GLS** | REST Shipping API | gls-group.com | API 对接 |
| **蜥国际/蜥蜴集团** | **无公开 API** | 搜索仅找到公司信息 | **Excel 模板** |
| **七条** | **未搜索到** | 网上无相关信息 | **Excel 模板，待确认** |

Vite/亿龙达官网：<https://www.vitedirect.com>、<https://www.viteusa.com>

**关键发现**：5 个承运人中，仅 FedEx (P2) 和 GLS 有可用 API。其余 3 个必须走 Excel 流程。

### 2.3 架构模式综合评估

#### 核心洞察：Excel vs API 是两种根本不同的交互模式

```
API 模式： 订单数据 → 调用承运人 API → 获取标签+追踪号 → 回写赛狐
Excel 模式：订单数据 → 按物流商模板格式化 → 导出 xlsx → 用户上传物流商后台
```

这意味着传统的"统一承运人接口"设计在此场景下有根本性局限——API 承运人和 Excel 承运人的交互模型完全不同。

#### 推荐方案：双模架构

```
┌─────────────────────────────────────────┐
│            Service Layer                 │
│  (订单获取、追踪回写、规则引擎)           │
├─────────────────────────────────────────┤
│  API Carrier Adapter  │  Excel Exporter  │
│  ├─ FedEx (P2)        │  ├─ Vite 模板    │
│  └─ GLS               │  ├─ 蜥国际 模板   │
│                       │  └─ 七条 模板    │
└─────────────────────────────────────────┘
```

**设计原则**：
1. **不建"大一统"抽象**：API 和 Excel 是两类东西，不需要统一接口
2. **Adapter 仅用于 API 承运人**：2 个 API 承运人不需要 Plugin/Registry 模式。两个独立 adapter 类即可
3. **Excel 模板系统**：每个物流商的 Excel 格式不同，用配置驱动模板（列映射 + 格式转换）
4. **YAGNI**：2 个 API 承运人时不要建框架。等第 3 个 API 承运人真正接入时再抽象

#### 与已有基础设施的契合

sellfox-api-proxy 已证明的策略：**"不要为 2 个 provider 建插件框架"**。对 shipping 系统同样适用。

### 2.4 中文物流 API 生态

- **快递鸟 (KDNiao)**：2500+ 物流商，商业 API（非开源）。<http://www.kdniao.com>
- **快递100**：50+ 快递公司面单打印。<https://m.kuaidi100.com>
- **菜鸟**：15 家快递公司，淘宝生态。<https://cloud.cainiao.com>
- **Gitee/GitHub**：未发现成熟的中文开源多承运人打单项目

**结论**：中文物流聚合均为商业 API，无开源方案可用。

---

## 3. Area 2：AI Agent 友好界面设计

### 3.1 MCP vs CLI：2026 年的结论

这是本次调研最具颠覆性的发现。

#### 实证数据（2026 年多个独立 benchmark）

| 指标 | CLI | MCP |
|------|-----|-----|
| Token 成本 | baseline | **10-35x 更高** |
| 可靠性 | 100% | 72% |
| Token 效率得分 | 202.1 | 152.3 |
| 浏览器自动化 | 28% 更高任务完成率 | baseline |
| Intune 合规检查 | 4,150 tokens | **145,000 tokens (35x)** |

来源：
- <https://devgent.org/en/2026/03/17/mcp-vs-cli-ai-agent-comparison-en>
- <https://www.scalekit.com/blog/mcp-vs-cli-use> (75 次 benchmark runs)
- <https://vensas.de/en/blog/mcp-vs-cli-cost-comparison>

#### 行业动向（2026 年 3 月）

- **Perplexity** 宣布缩减 MCP 支持，转向 CLI，原因："token 成本低效"和"连接不稳定"
- **飞书/钉钉** 发布 Agent CLI toolkits（不是 MCP servers）
- **Andrej Karpathy** (Feb 2026)：CLI 之所以好，正因为是 "legacy" 技术，Agent 天生就会用
- **OpenClaw** (250K+ stars)：整个 Agent 框架基于 skills-and-CLI，不用 MCP
- 社区共识：**"CLI first, MCP as complement"**

来源：
- <https://lalatenduswain.medium.com/cli-based-agents-vs-mcp-the-2026-showdown>
- <https://xpander.ai/resources/mcp-vs-cli-for-ai-agents>
- <https://vibekk.com/archives/mcp-vs-cli-ai-agents-command-line-winning>

#### MCP 安全态势

- 2026 年初：20 个 CVE，其中 CVE-2026-32211 是 CVSS 9.1（SSE transport 认证缺失导致租户接管）
- MCP 安全仍在快速演进中，生产部署需谨慎
- 对 3-5 人小团队而言，MCP 的安全运维成本过高

来源：
- <https://obot.ai/resources/learning-center/mcp-security>
- <https://labs.cloudsecurityalliance.org/agentic/agentic-mcp-security-best-practices-v1>

### 3.2 DeepSeek + MCP 兼容性

- DeepSeek API 支持标准 tool calling（`POST /chat/completions` with `tools`）
- **不原生支持 MCP**。需要社区 bridge：<https://github.com/DMontgomery40/deepseek-mcp-server>
- 用户团队使用 DeepSeek（Codex Desktop），MCP 需要额外适配层

### 3.3 推荐方案：REST API + CLI，暂不引入 MCP

#### CLI vs MCP 通俗解释（给非技术背景）

用户当前已经在用的模式：

```
Claude Desktop → 调用 ERPNext REST API → 查数据
```

生产 ERPNext 没装 FAC MCP，但不影响 Agent 工作。这证明 MCP 不是必须的。

**三种对接方式**（以"获取赛狐未发货订单"为例）：

| 方式 | Agent 怎么用 | 你写什么 |
|------|------------|---------|
| **CLI** | 执行 `uv run sellfox list-orders --status Unshipped --json` | 一个 Python 函数 + Typer 装饰器 |
| **REST API** | function calling：`GET /api/orders?status=Unshipped` | FastAPI 路由 |
| **MCP** | Agent 自动发现有 `list_orders` 工具 | MCP 服务器进程 |

**关键认识**：
- CLI 不是"简化版 MCP"。CLI 是 Agent 最省钱、最可靠的操作方式
- MCP 的价值在"自动发现"——几十个工具时才有意义
- 三种方式**不冲突**。同一个 Service Layer 上面挂 CLI + REST，后期用 `fastapi-mcp`（11.6k stars, MIT）可一键转 MCP

**推荐演进**：
```
P1：CLI (Typer --json) + REST API (FastAPI)
    ↑ 给 Agent 用     ↑ 给 Web UI + 脚本用
    共享 Service Layer（核心业务逻辑写一次）

P2+：fastapi-mcp 一键暴露 MCP（如果需要）
```

#### MCP vs CLI 实证数据

**三界面架构**：

```
┌──────────────────────────────────────┐
│          Service Layer               │
├──────────────────────────────────────┤
│  REST API    │  CLI (Typer) │ Web UI │
│  (FastAPI)   │  --json      │ (Vue)  │
│  ↑ App 调用   │  ↑ Agent 调用 │  ↑ 人类  │
└──────────────────────────────────────┘
```

**理由**（基于独立调研证据）：

1. **CLI 比 MCP 便宜 10-35x token**：Agent 每次操作节省显著，对 DeepSeek API 费用有直接影响
2. **CLI 可靠性 100% vs MCP 72%**：小团队没有精力排查 MCP 连接问题
3. **DeepSeek 不原生支持 MCP**：如果主力模型不支持，MCP 的"生态互通"优势不存在
4. **REST API 不会消失**：给 Web UI 和脚本调用提供稳定接口
5. **CLI 是 AI Agent 的"母语"**：LLM 训练数据中有大量 CLI 用法，不需要额外 schema 描述

**后期可加 MCP**：如果未来需要 MCP，可以通过 `fastapi-mcp` (11.6k stars，MIT) 一键将 FastAPI 端点暴露为 MCP tools，无需重写业务逻辑。

---

## 4. 其他技术决策

### 4.1 部署架构

**推荐**：Docker Compose 单机部署，与 sellfox-api-proxy 共享上海测试服务器。

- 2-3 个容器：app (FastAPI + CLI)、worker (后台任务)、nginx (已存在)
- SQLite (WAL mode)：3-5 用户，无并发写入瓶颈，零运维成本
- 后期可迁移 PostgreSQL（如移植到 ERPNext）

### 4.2 后台任务

**推荐**：FastAPI BackgroundTasks + SQLite 失败重试，不引入 Redis。

- 标签生成（调用承运人 API）是主要异步任务
- 对于 3-5 用户的小规模场景，FastAPI 内置 BackgroundTasks 足够
- 失败任务写入 SQLite，定时轮询重试
- 避免引入 Redis 增加运维复杂度

如果需要更完善的任务队列，SAQ (Simple Async Queue) 是最佳选择：
- async-native，比 ARQ 快 8x
- 支持 Redis 或 PostgreSQL backend
- 内置 Web UI 监控
- <https://github.com/tobymao/saq>

### 4.3 标签打印

- **ZPL**：Zebra 热敏打印机原生格式
- **PDF 4x6"**：通用兜底格式
- **Labelary API**：ZPL → PNG 在线预览 (<https://labelary.com>)

---

## 5. 分阶段建议

### P1（当前）
- 赛狐订单获取（列表 + 详情）
- Excel 模板系统（Vite、蜥国际、七条）
- SQLite 数据存储
- REST API + CLI（Typer --json）
- Web UI 基础页面

### P2
- GLS API 对接
- FedEx API 对接（需要 API Key + MFA）
- 追踪号回写赛狐

### P3
- 规则引擎（YAML 配置 → 后期 Web UI）
- 标签打印集成

---

## 6. 全量来源 URL

### 多承运人系统
- <https://github.com/karrioapi/karrio> — Karrio 开源多承运人平台
- <https://www.karrio.io/platform> — Karrio 平台介绍
- <https://github.com/frappe/erpnext-shipping> — ERPNext Shipping app
- <https://docs.erpnext.com/erpnext-shipping> — ERPNext Shipping 文档
- <https://docs.frappe.io/erpnext/shipment> — ERPNext Shipment doctype
- <https://github.com/saleor/saleor/tree/main/saleor/shipping> — Saleor shipping 模块
- <https://github.com/karrioapi/karrio> (HN discussion 2023)

### 物流商
- <https://www.vitedirect.com> — 亿龙达中文官网
- <https://www.viteusa.com> — VITE USA 官网
- <https://www.kdniao.com> — 快递鸟
- <https://m.kuaidi100.com> — 快递100
- <https://cloud.cainiao.com> — 菜鸟物流云

### 商业平台
- <https://www.cargoson.com/en/blog/top-multi-carrier-shipping-software-mcs-providers>
- <https://elextensions.com/best-multi-carrier-shipping-api-developers>
- <https://www.pluginhive.com/shopify-multi-carrier-shipping-label-app>

### MCP vs CLI
- <https://devgent.org/en/2026/03/17/mcp-vs-cli-ai-agent-comparison-en> — CLI 10-35x cheaper benchmarks
- <https://www.scalekit.com/blog/mcp-vs-cli-use> — 75 benchmark runs
- <https://vensas.de/en/blog/mcp-vs-cli-cost-comparison> — MCP vs CLI cost comparison
- <https://xpander.ai/resources/mcp-vs-cli-for-ai-agents> — CLI-first vendors (2026)
- <https://vibekk.com/archives/mcp-vs-cli-ai-agents-command-line-winning> — Chinese ecosystem CLI

### MCP 生态
- <https://mcpsuperhero.com/blog-mcp-vs-api-integration.html> — MCP vs REST comparison
- <https://atlan.com/know/when-to-use-mcp-vs-api> — MCP vs API decision framework
- <https://jamwithai.substack.com/p/when-to-use-mcp-vs-api-vs-functiontool> — MCP vs Function calling
- <https://www.nordicapis.com/model-context-protocol-mcp-vs-universal-tool-calling-protocol-utcp> — MCP vs UTCP
- <https://github.com/DMontgomery40/deepseek-mcp-server> — DeepSeek MCP bridge

### MCP 安全
- <https://obot.ai/resources/learning-center/mcp-security> — MCP security best practices
- <https://labs.cloudsecurityalliance.org/agentic/agentic-mcp-security-best-practices-v1>
- <https://dev.to/peytongreen_dev/fastapi-mcp-adding-real-oauth-21-auth-to-your-python-mcp-server> — FastAPI MCP OAuth

### 工具
- <https://github.com/tobymao/saq> — SAQ task queue
- <https://github.com/fastapi/typer> — Typer CLI
- <https://labelary.com> — ZPL label preview
