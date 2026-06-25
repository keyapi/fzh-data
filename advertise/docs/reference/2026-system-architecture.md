---
okf: v0.1
type: Reference
title: 广告系统架构设计 — 2026年6月
description: 多Agent架构、参考架构、数据架构、UX模式、规则引擎、基础设施、多租户设计
tags: [amazon, advertising, architecture, multi-agent, UX, rule-engine, 2026]
timestamp: 2026-06-24
---

# 广告系统架构设计 — 2026年6月

## 1. Multi-Agent 架构（2026 年主流范式）

2026 年广告系统中，Multi-Agent 架构取代单体 Agent 成为行业标准。Spotify 工程团队和 IAB Tech Lab 先后公布了其多 Agent 架构设计。[source](https://engineering.atspotify.com/2026/2/our-multi-agent-architecture-for-smarter-advertising)[source](https://iabtechlab.com/the-architecture-behind-trustworthy-ai-agents-in-advertising/)

### 五层架构

```
+------------------------------------------------------------------+
|                        L5: 用户交互层                              |
|   Chat Interface  |  Dashboard  |  Visual Report  |  Alert/Notify  |
+------------------------------------------------------------------+
|                        L4: 协调层（Orchestrator）                   |
|   意图解析 → 任务分解 → Agent 调度 → 结果聚合 → 冲突解决              |
+------------------------------------------------------------------+
|                        L3: 专业 Agent 层                           |
|  +----------+  +----------+  +----------+  +----------+           |
|  | Campaign |  | Bidding  |  | Creative |  | Audience |  ...       |
|  |  Agent   |  |  Agent   |  |  Agent   |  |  Agent   |           |
|  +----------+  +----------+  +----------+  +----------+           |
+------------------------------------------------------------------+
|                        L2: 协议 / 通信层                            |
|   MCP  |  AdCP  |  A2A  |  AAMP  |  Event Bus  |  Shared Memory   |
+------------------------------------------------------------------+
|                        L1: 平台 API 层                              |
|   Amazon Ads API  |  Google Ads API  |  Meta Ads API  |  DSP APIs |
+------------------------------------------------------------------+
```

### 为什么从单体迁移到 Agent 分解

- **可组合性**：Bidding Agent 可独立升级而不影响 Reporting Agent
- **故障隔离**：Creative Agent 的故障不会导致出价系统崩溃
- **专业化**：每个 Agent 可使用最适合其任务的模型和架构（RL Agent 用于出价，Transformer Agent 用于搜索词分析）
- **并行执行**：多个 Agent 可同时工作，Campaign Setup 时间从 15-30 分钟降至 5-10 秒 [source](https://engineering.atspotify.com/2026/2/our-multi-agent-architecture-for-smarter-advertising)

---

## 2. 参考架构

### AWS Bedrock 广告 Agent 参考架构

AWS 官方解决方案 [Guidance for Advertising Agents on AWS](https://github.com/aws-solutions-library-samples/guidance-for-advertising-agents-on-aws) 提供了一套完整的参考实现：[source](https://docs.aws.amazon.com/solutions/advertising-agents-on-aws/)

**架构组成**：
- **4 个 Orchestrator Agent**：Campaign Orchestrator、Creative Orchestrator、Analytics Orchestrator、Governance Orchestrator
- **17 个 Specialist Agent**：覆盖关键字、出价、预算、受众、Placement、报表、合规等子领域
- **月运营成本**：约 $329.86/月（按 us-east-1 计价）

**关键组件**：
- Amazon Bedrock Agents（Agent 托管与编排）
- Amazon Bedrock Knowledge Bases（RAG 知识检索）
- Amazon Bedrock Guardrails（内容安全与合规）
- AWS Lambda / Step Functions（业务流程）
- Amazon DynamoDB（Agent 状态持久化）
- Amazon S3（数据湖、报表存储）

### PubMatic AgenticOS

PubMatic 的 AgenticOS 提供了买方全栈 Agent 参考架构：[source](https://investors.pubmatic.com/news-releases/news-release-details/pubmatic-launches-agenticos-operating-system-agent-agent)

**三层架构**：
1. **Engagement Layer**：自然语言交互界面，意图解析和结果可视化
2. **Agent Fabric Layer**：Agent 注册、发现、调度、监控
3. **Execution Layer**：与 Ad Servers、DSP、SSP、Data Providers 的 API 集成

**成果**：Campaign Setup 时间减少 87%，人工介入仅需异常场景

---

## 3. 数据架构

### Lakehouse-Native 架构

2026 年 6 月 Databricks 推出了 **CustomerLake**，专为营销和广告行业设计的 Lakehouse 平台：[source](https://www.databricks.com/company/newsroom/press-releases/databricks-enters-marketing-industry-customerlake-agentic-customer)

- **统一存储**：广告数据、客户数据、行为数据、Attribution 数据全部存入 Lakehouse
- **Agentic Customer Intelligence**：AI Agent 直接在 Lakehouse 上运行，无需数据搬运
- **Delta Sharing**：跨组织数据协作（Advertiser ↔ Agency ↔ Publisher）

### 实时处理

Apache Spark Real-Time Mode 的引入重塑了广告归因（Ad Attribution）的数据处理方式：[source](https://www.databricks.com/blog/why-apache-spark-real-time-mode-game-changer-ad-attribution)

- **Spark Structured Streaming** 实现 < 1 秒延迟的 Ad Event Processing（Impression、Click、Conversion）
- 替代传统 Lambda 架构，统一 Batch 和 Streaming 处理逻辑

### Alibaba 妈妈：Flink + Paimon

阿里巴巴妈妈广告平台采用 Apache Flink + Paimon（流式数据湖格式）的实时数仓架构：[source](https://www.alibabacloud.com/blog/602446)

- Flink 处理百万 QPS 的实时竞价（RTB）数据流
- Paimon 提供流批一体的存储层，支持 Changelog 和 Time Travel
- 实时特征工程 → 在线模型推断 → 出价决策 < 10ms

---

## 4. UX / UI 设计模式

### 5-Second Rule

广告 Dashboard 的核心设计原则：**5 秒内必须能回答"我的广告现在表现如何"**。[source](https://sagum.com/2026/05/12/dashboards-that-drive-better-ads/) 超过 5 秒无法识别关键信息的设计导致 Dashboard 弃用率 > 60%。

### 六大认知设计法则

1. **Proximity（邻近性）**：相关指标（Impression、Click、CTR）必须物理靠近
2. **Common Region（共同区域）**：用 Card / Panel 分组语义相关的数据
3. **Similarity（相似性）**：同类型数据用相同的 Visual Encoding（颜色、图表类型）
4. **Closure（闭合性）**：趋势图用浅色填充区域增强可读性
5. **Continuity（连续性）**：时序数据用线图，避免离散的柱状图
6. **Figure-Ground（图形-背景）**：异常数据用对比色突出，正常数据低调退后

### 推荐 4 行布局

```
Row 1: [ACP]    [Total Spend]  [Total Sales]  [ACoS]     [ROAS]    [Orders]
Row 2: [Spend Trend Line Chart ───────────────────────────────────────────]
Row 3: [Campaign Table (sortable, filterable) ──────────────────────────]
Row 4: [Search Term Cloud / Table ──]  [Keyword Performance Bar Chart ──]
```

### Two Truths 原则

AI-Native 广告 UI 的核心设计原则（来自 Nexxen DSP 设计团队）：[source](https://nexxen.com/nexxen-launches-ai-native-dsp-ui/)
1. **Truth 1**：用户永远可以一键看到"AI 做了什么的摘要"
2. **Truth 2**：用户永远可以一键看到"AI 为什么这样做"的解释

---

## 5. 规则引擎（Rule Engines）

### Optmyzr 三层规则引擎

[Optmyzr](https://www.optmyzr.com/blog/optmyzr-rule-engine-vs-google-ads-automated-rules/) 是目前最成熟的广告规则引擎之一，采用三层架构：
- **L1 条件层**：Metric thresholds（ACoS > 30%、CTR < 0.1%、Spend = 0）
- **L2 动作层**：Actions（Pause、Adjust Bid ±X%、Add Negative KW、Change Budget、Notify）
- **L3 策略层**：将 L1+L2 组合为可复用的 Strategy Template

### 双进程架构：PID + Decision Transformer

阿里巴巴健康团队在 arXiv 2603.04920 中提出了 PID 控制器 + Decision Transformer 的双进程架构：[source](https://ar5iv.labs.arxiv.org/html/2603.04920)

- **PID Controller**（快速进程）：实时响应 ACoS 波动，做出 < 100ms 的快速出价调整
- **Decision Transformer**（慢速进程）：基于长时间序列的上下文学习（In-Context Learning），每天 1-2 次进行策略层面的出价参数重校准
- **双进程协同**：PID 确保实时稳定，Decision Transformer 确保长期最优

### 开源规则引擎

| 项目 | 平台 | 描述 |
|------|------|------|
| **KonQuest** | Meta Ads (MCP) | MCP-based Meta 广告自动化，支持自然语言规则定义 [source](https://github.com/brandu-mos/konquest-meta-ads-mcp) |
| **Lanbow** | Amazon Ads | 社区开发的 Amazon Ads Rule Engine，Python 实现 |
| **Amazon DTE (Demand Tailored Engine)** | Amazon Ads | Amazon 内部规则引擎，支持 Campaign-level 自动规则 |

---

## 6. 开源广告服务器（Open Source Ad Servers）

| 项目 | 描述 | 适用场景 |
|------|------|----------|
| **OpenAdServer** | 全栈开源广告服务器，支持 RTB、Direct Deal、Ad Pod | 中小型 Ad Network、私有 Marketplace |
| **Linny** | 轻量级 Ad Server，Go 语言实现，专注于 Server-Side Ad Insertion (SSAI) | 视频广告、Podcast 广告 |
| **IAB Trusted Server** | IAB Tech Lab 的参考实现，提供标准化的广告投放和计数 | 行业合规参考、标准验证 |

---

## 7. 基础设施

### 计算层

- **Kubernetes（EKS / GKE / AKS）**：广告系统事实上的编排标准，支撑百万 QPS 的实时出价服务
- **AWS Graviton**：ARM 架构处理器在 AdTech 工作负载中实现 20-40% 性价比提升
- **Spot Instances**：用于离线报表生成、模型训练、数据 ETL 等非延迟敏感任务

### 低延迟存储

实时竞价（RTB）场景要求 < 50ms 的端到端延迟，对存储层提出极高要求：[source](https://aerospike.com/resources/white-papers/fueling-real-time-adtech/)

| 技术 | 延迟 | 适用场景 |
|------|------|----------|
| **Aerospike** | < 1ms (P99) | 用户 Profile、频率上限（Frequency Cap）、预算消耗追踪 |
| **Redis** | < 1ms (P99) | 实时计数（Impression Count）、Rate Limiting、短期缓存 |
| **DynamoDB (DAX)** | < 5ms (P99) | Campaign 状态、Bid Modifier、持久化配置 |

以上技术组合可支撑每秒数百万次 Ad Auction 的峰值负载。

---

## 8. 端到端参考技术栈

```
                          +---------------------+
                          |   Client (Web/App)   |
                          +----------+----------+
                                     |
                          +----------v----------+
                          | Agent Orchestration |
                          | (Brain/Coordinator) |
                          +----------+----------+
                                     |
              +----------------------+----------------------+
              |                      |                      |
     +--------v--------+  +---------v---------+  +---------v---------+
     |  Campaign Agent  |  |  Analytics Agent   |  |  Creative Agent   |
     |  (Plan/Execute)  |  |  (Insight/Report)  |  |  (Generate/Test)  |
     +--------+--------+  +---------+---------+  +---------+---------+
              |                      |                      |
              +----------------------+----------------------+
                                     |
                          +----------v----------+
                          |   MCP Server        |
                          | (Amazon Ads / Meta) |
                          +----------+----------+
                                     |
              +----------------------+----------------------+
              |                      |                      |
     +--------v--------+  +---------v---------+  +---------v---------+
     | Stream Processing|  |   Data Lakehouse  |  |  ML Training       |
     | (Kafka/Flink)    |  |   (Delta/Iceberg) |  |  (SageMaker/GPU)   |
     +-----------------+  +-------------------+  +--------------------+
              |                      |                      |
              +----------------------+----------------------+
                                     |
                          +----------v----------+
                          | Governance & Audit  |
                          | (Log/Policy/Explain)|
                          +---------------------+
```

---

## 9. 多租户设计 + 反方论点

### 多租户策略

| 策略 | 描述 | 优势 | 劣势 |
|------|------|------|------|
| **Pooled（共享）** | 所有租户共享同一套基础设施和应用实例 | 成本最低，运维简单 | 隔离性差，Noisy Neighbor 问题 |
| **Siloed（独享）** | 每个租户独立的 Deployment | 最强隔离，可定制 | 成本高，运维复杂 |
| **Bridge（混合）** | 敏感组件独享（数据存储、密钥），共享组件 Pooled（计算、Agent） | 平衡成本和隔离 | 架构复杂，需要精细的权限控制 |

### 对当前系统的反思

审视当前广告系统的架构局限：

- **JSON 文件作为数据交换媒介**：缺少 Event Bus / Message Queue（Kafka、NATS），数据流通过文件传递而非事件驱动，延迟高、可靠性差
- **Excel 输出作为唯一报表**：缺少可视化 Dashboard 和实时数据 API，数据可操作性弱
- **缺少事件总线（Event Bus）**：组件间耦合紧密，无法支持事件溯源（Event Sourcing）、异步处理和独立扩展
- **无规则引擎**：决策逻辑硬编码，无法实现可配置、可组合的自动化策略
- **缺少冷却期（Cool-down）**：对出价调整无冷却机制，可能导致震荡（Oscillation）——频繁的 Bid 调整反而降低系统稳定性
- **缺少状态管理（State Management）**：Campaign 变更无事务性保证，出错后难以回滚

这些局限性意味着系统在从一个"辅助工具"向"自动化广告管理平台"演进时，需要系统性的架构重构而非渐进式修补。

---

## See also

- [AI/ML 在 Amazon 广告中的应用 — 2026年6月](2026-ai-ml-landscape.md)
- [AWS Guidance for Advertising Agents on AWS](https://docs.aws.amazon.com/solutions/advertising-agents-on-aws/)
- [GitHub: aws-solutions-library-samples/guidance-for-advertising-agents-on-aws](https://github.com/aws-solutions-library-samples/guidance-for-advertising-agents-on-aws)
- [Spotify Engineering: Multi-Agent Architecture for Smarter Advertising](https://engineering.atspotify.com/2026/2/our-multi-agent-architecture-for-smarter-advertising)
- [IAB Tech Lab: Trustworthy AI Agents in Advertising](https://iabtechlab.com/the-architecture-behind-trustworthy-ai-agents-in-advertising/)
- [Databricks CustomerLake](https://www.databricks.com/company/newsroom/press-releases/databricks-enters-marketing-industry-customerlake-agentic-customer)
- [Sagum: Dashboards That Drive Better Ads](https://sagum.com/2026/05/12/dashboards-that-drive-better-ads/)
- [Aerospike: Fueling Real-Time AdTech](https://aerospike.com/resources/white-papers/fueling-real-time-adtech/)
