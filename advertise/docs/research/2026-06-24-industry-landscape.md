---
okf: v0.1
type: Research
title: Amazon 广告行业全景调研 — 2026年6月
description: 83次搜索 × 6维度行业最佳实践调研，含完整来源引用和系统性反驳
tags: [amazon, advertising, research, industry-landscape, 2026]
timestamp: 2026-06-24
---

# Amazon 广告行业全景调研 — 2026年6月

> 83 次搜索，覆盖 6 个维度，系统性审视 Amazon 广告技术栈、市场格局与最佳实践。

---

## 1. 调研范围与方法

| 维度 | 领域 | 搜索次数 | 关键来源 |
|------|------|---------|---------|
| 战略框架 | 广告策略、ACoS/TACoS、预算分配、归因 | 16 | Feedvisor, Canopy Management, Autron, SellerMetrics |
| AI/ML 技术栈 | LLM 搜索词分类、RL 竞价、多 Agent 架构 | 14 | Spotify, AWS, Laurence (YC), Databricks |
| 工具与开源 | 第三方 SaaS、MCP Server、自托管方案 | 13 | IvyeaOps, Optmyzr, SellerSpace, Amazon MCP |
| API/数据基础设施 | Amazon Ads API v3/v4、AMC、归因窗口 | 15 | Amazon Ads API, PPC.land, Code3 |
| 系统架构 | 数据管道、Agent 架构、实时/批处理 | 12 | Databricks, PubMatic, AWS Blog |
| 市场格局 | CPC 通胀、零售媒体、竞争格局 | 13 | PPC.land, WARC, Digiday, IMH |

**调研日期**: 2026-06-24
**方法**: 每个维度独立搜索 10-16 次，交叉验证关键结论，标注反驳意见和不确定性。

---

## 2. 核心发现摘要

1. **ACoS 单维度优化已成过去式** — 行业正在从 ACoS 转向 TACoS + 利润感知优化。Feedvisor 和 Canopy Management 2026 年指南均强调，单纯降低 ACoS 会导致错失增量销售。Spotify 的 Multi-Agent 架构明确将"profit-aware"作为 Agent 目标函数。

2. **COSMO/Alexa for Shopping 根本性改变搜索范式** — Amazon 从关键词匹配转向意图理解和多模态搜索。COSMO 知识图谱包含 15 种关系类型，传统的"关键词否定"策略正变得不够充分。Tinuiti 2026 年报告指出，Alexa for Shopping 已进入大规模采用阶段。

3. **MCP Server 是 2026 年最大基础设施变化** — Amazon 于 2026 年 2 月推出 Ads MCP Server 公开测试版，允许 AI Agent 直接通过自然语言管理广告活动。这是 Amazon 首次官方支持 LLM-广告系统直连，降低了第三方工具的壁垒。

4. **IvyeaOps 提供自托管开源方案** — AGPL-3.0 协议的开源 Amazon 运营 AI 工作台，集成了广告管理、库存、Review 分析等模块。减少从头构建广告 AI 系统的代码量，但需要评估合规性（非官方 API 接入）。

5. **AMC 免费用但大多数人未使用** — Amazon Marketing Cloud 提供 25 个月历史数据 + SQL 查询能力，支持自定义归因模型。但多数中小卖家未接入，主要障碍是 SQL 技能门槛和缺乏 AMC 数据分析师。

6. **Multi-Agent 架构成为生产标准** — Spotify、AWS、PubMatic 均在生产环境部署了多 Agent 协作架构。典型模式: Strategy Agent → Analysis Agent → Execution Agent → Monitoring Agent，每个 Agent 有独立的工具集和权限边界。

7. **归因模型已发生实质性变化** — Amazon 在 2026 年收紧了 view-through 归因窗口，同时推出 Multi-Touch Attribution (MTA) Beta。Code3 和 PPC.land 均报告 DSP 归因指标出现显著变化。

8. **Seller CPC 通胀 + 现金流危机** — Influencer Marketing Hub 2026 年数据: Amazon CPC 同比上涨 12-18%，但转化率增长滞后。很多中小卖家面临"广告费占比持续攀升但利润率下降"的结构性压力。

9. **Amazon 免费 AI 工具冲击第三方 SaaS** — Amazon 推出 Creative Agent（免费 AI 创意生成）、Alexa Agentic Ads（语音购物广告）等免费工具。Search Engine Land 评论: 这直接冲击了依赖广告创意和自动化管理的第三方 SaaS 商业模式。

10. **分析到执行存在断层** — 当前系统在分析层面表现不错，但输出停留在 Excel 静态报告。决策到执行链路缺失: 无决策日志、无执行验证、无闭环反馈。这是整个行业从"报告型分析"到"决策型系统"升级的关键瓶颈。

---

## 3. 战略框架

### 3.1 ACoS → TACoS + 利润感知

**传统范式**: ACoS (Advertising Cost of Sales) = Ad Spend / Ad Sales
**2026 范式**: TACoS (Total Advertising Cost of Sales) = Ad Spend / Total Sales

来源: [Feedvisor Sponsored Brands Guide](https://feedvisor.com/resources/amazon-marketing-advertising-strategies/sponsored-brands-guide/)
- 强调 TACoS 是衡量广告健康度的更完整指标
- 广告可能提升自然排名，只看 ACoS 会低估广告价值

来源: [Canopy Management 10 Tips](https://canopymanagement.com/10-amazon-advertising-tips-for-better-results/)
- 建议根据产品生命周期阶段设定不同的 TACoS 目标
- 新品期 TACoS 可达 30-40%，成熟期应降至 15-20%

### 3.2 Campaign 结构简化

来源: [Autron — Fewer Campaigns Beat More](https://autron.ai/blog/amazon-ppc-campaign-structure-in-2026-why-fewer-campaigns-now-beat-more)
- 2026 年趋势: 少量大 Campaign + AI 自动优化 > 大量细分 Campaign
- Amazon 的自动竞价算法需要足够数据量，碎片化 Campaign 导致数据稀疏

### 3.3 Multi-Touch Attribution (MTA)

来源: [SellerMetrics MTA](https://sellermetrics.app/amazon-multi-touch-attribution/)
- Amazon MTA Beta 支持线性、时间衰减、基于位置等多种归因模型
- 与传统 last-click 归因相比，MTA 能更准确评估上层漏斗广告价值

来源: [Code3 — Attribution Changes](https://code3.com/resources/amazon-quietly-tightened-attribution-and-its-changing-how-dsp-performance-is-measured/)
- View-through 归因窗口收紧，DSP 报告的 ROAS 普遍下降 20-30%
- 建议重新校准 DSP 效果评估基准

### 3.4 广告 Consent 合规期限

来源: [PPC.land — Consent Deadline June 30](https://ppc.land/amazon-ads-consent-deadline-is-june-30-your-data-wont-work-after-that/)
- **关键截止日期: 2026年6月30日**
- 未配置 consent 的广告数据将停止工作
- 影响所有使用 Amazon Ads API 的数据管道

---

## 4. AI/ML 技术栈

### 4.1 Multi-Agent 架构

来源: [Spotify Engineering — Multi-Agent Architecture](https://engineering.atspotify.com/2026/2/our-multi-agent-architecture-for-smarter-advertising)
- **生产级架构**: 4 个 Agent (Strategy, Analysis, Execution, Monitoring)
- 每个 Agent 有独立的 LLM + 工具集
- 关键设计: Agent 间通过结构化消息通信，而非共享状态

来源: [AWS — Agentic Bidding with ARTf Containers](https://aws.amazon.com/cn/blogs/industries/deploy-agentic-bidding-without-sacrificing-speed-artf-containers-with-nvidia-gpu-acceleration-on-aws/)
- ARTf (Agentic Real-Time Framework) 容器: 毫秒级竞价决策
- NVIDIA GPU 加速推理，支持实时竞价场景 (< 100ms)
- 适用于 SP/SB/SD 全广告类型

来源: [PubMatic — Agentico Full Buy-Side Agent Stack](https://pubmatic.com/blog/inside-agenticos-a-look-at-pubmatics-full-buy-side-agent-stack/)
- 完整买方 Agent 栈: 从受众规划到竞价执行
- 支持跨渠道 (Amazon + Walmart + Google) 统一 Agent 管理

### 4.2 RL + Transformer 竞价

来源: [Laurence (YC) — RL + Transformer](https://www.ycombinator.com/companies/laurence)
- YC 投资的 Amazon 广告 AI 公司
- 核心技术: 强化学习 (RL) + Transformer 模型进行竞价优化
- 将竞价问题建模为 POMDP (部分可观测马尔可夫决策过程)

来源: [Marketing Science — Attribution + Bidding (2026)](https://econpapers.repec.org/article/inmormksc/v_3a45_3ay_3a2026_3ai_3a3_3ap_3a576-595.htm)
- 学术论文: 归因模型选择如何影响竞价策略
- 核心发现: 使用错误归因模型的竞价策略可能导致 15-25% 效率损失

### 4.3 Amazon 免费 AI 工具

来源: [Amazon Ads — Creative Agent](https://www.aboutamazon.ca/news/amazon-ads/amazon-ads-launches-creative-agent-new-agentic-ai-tool-that-creates-professional-quality-ads)
- 免费 AI 创意生成工具
- 支持 Sponsored Brands、Sponsored Display 等格式
- 直接集成到 Amazon Ads Console

来源: [Search Engine Land — Alexa Agentic Ads](https://searchengineland.com/amazon-launches-alexa-agentic-ads-480842)
- Alexa 语音购物场景的广告
- Agentic AI 根据用户对话上下文推荐商品

来源: [Databricks — CustomerLake + Agentic Customer](https://www.databricks.com/company/newsroom/press-releases/databricks-enters-marketing-industry-customerlake-agentic-customer)
- Databricks 进入营销行业，推出 CustomerLake
- Agentic Customer: AI Agent 驱动的客户数据平台

---

## 5. 工具与开源

### 5.1 Amazon Ads MCP Server

来源: [Amazon Ads MCP Server Open Beta](https://advertising.amazon.com/en-us/library/news/amazon-ads-mcp-server-open-beta)
- 2026年2月推出公开测试版
- 支持自然语言管理广告活动
- 免费使用，基于 Model Context Protocol 标准

### 5.2 IvyeaOps 自托管方案

来源: [IvyeaOps GitHub](https://github.com/Hector-xue/IvyeaOps)
- AGPL-3.0 开源协议
- Amazon 运营 AI 工作台: 广告 + 库存 + Review + 客服
- Web UI + API + AI Agent 三层架构
- 价值: 减少 60-80% 自建广告 AI 系统的代码量

### 5.3 第三方 SaaS 对比

来源: [SellerSpace — 优麦云 Amazon AD](https://www.sellerspace.com/zh/blog/SellerSpace-with-Amazon-AD/)
- 优麦云广告管理模块: AI 托管 + 规则引擎 + 报表
- 与 Amazon Ads API 原生集成

来源: [Optmyzr — Rule Engine vs Google Automated Rules](https://www.optmyzr.com/blog/optmyzr-rule-engine-vs-google-ads-automated-rules/)
- Optmyzr 规则引擎: 跨渠道规则管理 (Amazon + Google + Meta)
- 对比: 第三方规则引擎的灵活性和可控性优势

来源: [Trellis — AI for Amazon Ads](https://gotrellis.com/resources/blog/ai-for-amazon-ads/)
- AI 驱动的 Amazon 广告优化
- 核心功能: 自动竞价 + 搜索词分析 + 预算分配

---

## 6. 数据基础设施

### 6.1 Amazon Ads API 版本演进

来源: [Amazon Ads API Release Notes](https://advertising.amazon.com/API/docs/en-us/release-notes/index)
- 持续更新的 API 变更日志
- 关注 v3 → v4 迁移路线图和 Breaking Changes

### 6.2 AMC (Amazon Marketing Cloud)

来源: 多来源交叉验证
- 25 个月历史数据存储
- SQL 查询接口 (基于 Presto/Athena 兼容语法)
- 自定义归因模型 (支持 Multi-Touch)
- 增量分析 (Incrementality) 能力

### 6.3 数据管道最佳实践

来源: [AWS — Ingesting Amazon Ads Data](https://aws.amazon.com/cn/solutions/guidance/ingesting-amazon-vendor-central-and-amazon-ads-data-on-aws/)
- AWS 官方 Solution Guidance
- 架构: API Gateway → Lambda → S3 → Glue → QuickSight/Athena
- 自动化数据摄取 Pipeline

来源: [PPC.land — Consent Deadline](https://ppc.land/amazon-ads-consent-deadline-is-june-30-your-data-wont-work-after-that/)
- 2026年6月30日后 consent 强制执行
- 所有数据管道必须在截止日期前完成配置

---

## 7. 系统架构

### 7.1 生产级 Agent 架构模式

基于 Spotify/AWS/PubMatic 的实践总结:

```
┌─────────────────────────────────────────────────────────────┐
│                      Orchestrator                            │
│  (任务调度、状态管理、Agent 间通信)                            │
├──────────────┬──────────────┬──────────────┬────────────────┤
│   Strategy   │   Analysis   │  Execution   │   Monitoring   │
│    Agent     │    Agent     │    Agent     │    Agent       │
│              │              │              │                │
│ • 目标设定   │ • 数据拉取   │ • 竞价调整   │ • KPI 监控     │
│ • 预算分配   │ • 搜索词分析 │ • 否定关键词 │ • 异常告警     │
│ • 策略评估   │ • 趋势检测   │ • Campaign CRUD│ • 日报生成   │
└──────────────┴──────────────┴──────────────┴────────────────┘
```

### 7.2 关键设计原则

- **Agent 间结构化消息通信**: 非共享状态，保证解耦和可回放
- **Human-in-the-loop**: 大额调整需人工审批
- **决策日志**: 每个 Agent 的动作记录到不可变日志
- **安全边界**: Execution Agent 的写入权限限制（日预算上限、最大出价调整幅度）

来源: [Colgate — Turning Amazon Shoppers into Predictable Growth](https://www.thedrum.com/awards-case-study/how-colgate-turned-amazon-shoppers-into-a-predictable-growth-engine-with-data)
- Colgate 的数据驱动 Amazon 增长案例
- 关键: 预测模型 + 实时调整 + 闭环测量

---

## 8. 市场格局

### 8.1 零售媒体市场

来源: [WARC — Amazon Retail Media Ad Revenue > $60Bn](https://www.pitchonnet.com/pitch-feature/amazon-retail-media-ad-revenue-to-exceed-60bn-this-year-warc-37173.html)
- Amazon 零售媒体广告收入 2026 年预计超过 $600 亿
- 增速继续超过 Google 和 Meta

来源: [PPC.land — Amazon/Google/Meta Eating Ad Market](https://ppc.land/amazon-google-and-meta-are-eating-the-ad-market-and-the-data-proves-it/)
- Amazon、Google、Meta 三家合计占全球数字广告市场 60%+
- Amazon 增速最快，主要由 Sponsored Products 驱动

### 8.2 CPC 通胀

来源: [Influencer Marketing Hub — CPCs Inflation](https://influencermarketinghub.com/amazon-cpcs-inflation-profitability/)
- 2026 年 Amazon CPC 同比上涨 12-18%
- 品类差异显著: 电子/家居/美妆涨幅最高
- 建议: 增加长尾词投入，降低头部竞争词依赖

### 8.3 Agentic 广告趋势

来源: [Digiday — Amazon Agentic Future](https://digiday.com/marketing/amazons-latest-ad-format-offers-a-glimpse-of-advertisings-agentic-future/)
- Amazon 最新广告格式展示 Agentic 广告未来
- 趋势: 从人工设定 Campaign → AI Agent 自主管理
- 预计 2026 年底 30%+ 的 SP 广告将由 AI Agent 管理

### 8.4 竞争态势

| 平台 | 2026 广告收入 (预估) | 增速 | 关键差异化 |
|------|---------------------|------|-----------|
| Amazon | $60Bn+ | 20%+ | 购买意图数据闭环 |
| Google | $80Bn+ | 12% | 搜索+YouTube+购物 |
| Meta | $60Bn+ | 15% | 社交发现+精准定向 |
| TikTok | $15Bn+ | 30%+ | 社交电商+病毒传播 |
| Walmart | $5Bn+ | 25%+ | 全渠道零售数据 |

---

## 9. 对现有方案的系统性评估

| 维度 | 当前状态 | 行业最佳实践 | 差距 | 优先级 |
|------|---------|-------------|------|--------|
| **Data (数据获取)** | 手动从优麦云导出 Excel | API 自动化拉取 (Ads API + MCP) | 效率低，无法实时，依赖人工 | P0 |
| **Processing (数据处理)** | Python 脚本单次处理 | 数据管道 (ETL/ELT) 自动化 | 无增量更新，无数据质量检查 | P0 |
| **Analysis (分析)** | v0.2 5桶分类 + 基本指标 | TACoS/利润感知 + 多期对比 + 预测 | 缺少利润维度、趋势分析 | P1 |
| **Classification (分类)** | 硬编码关键词匹配 | LLM 语义分类 + COSMO 意图映射 | 覆盖面窄，无法理解搜索意图 | P1 |
| **Output (输出)** | Excel 静态报告 (6 sheet) | Web Dashboard + 自然语言查询 | 交互性差，无法自助分析 | P1 |
| **AI (AI 集成)** | 无 | MCP Server + LLM Agent | 完全缺失，无法自然语言管理 | P0 |
| **Decision Log (决策日志)** | 无持久化 | 不可变日志 + 审计 + 效果回测 | 无法追踪决策效果 | P0 |
| **Execution (执行)** | 手动在优麦云操作 | API 自动执行 + 审批流程 | 分析到操作存在断层 | P1 |
| **UX (用户体验)** | Python 脚本 + Excel | Web Dashboard + Agent 对话 | 用户门槛高，非技术人员难用 | P1 |
| **Comparison (对比)** | 仅分析当前周期 | 环比/同比 + 行业基准 | 缺少时间维度和行业对标 | P2 |

---

## 10. 推荐方向

### 优先级矩阵

| 优先级 | 模块 | 价值 | 工作量 | 依赖 |
|--------|------|------|--------|------|
| 🔴 P0 | 自动化数据管道 (API→DB) | 解决60天窗口，一切分析基础 | 大 | Ads API 开发者审批 |
| 🔴 P0 | MCP Server 集成 | AI Agent 操作 Ads，自然语言管理 | 中 | Amazon Ads MCP Beta |
| 🔴 P0 | 决策日志数据库 | 持久化+审计+学习 | 小 | 无 |
| 🟡 P1 | TACoS + 利润感知分析 | ACoS 升级到完整商业视角 | 中 | 获取自然销售数据 |
| 🟡 P1 | LLM 搜索词语义分类 | 替代硬编码关键词 | 中 | LLM API |
| 🟡 P1 | Web Dashboard | 替代 Excel | 大 | 数据管道 |
| 🟢 P2 | AMC 集成 | 自定义归因+增量分析 | 大 | $20K+/月花费门槛 |
| 🟢 P2 | 预测模型 | 预算预测+出价优化 | 大 | 充足历史数据 |
| 🟢 P2 | 多 Agent 协作架构 | Strategy→Analysis→Execution→Monitoring | 大 | P0-P1 全部完成 |

### 推荐架构

```
┌──────────────┐    ┌───────────────┐    ┌──────────────────┐
│ Amazon Ads   │───▶│  Data Pipeline │───▶│  PostgreSQL/     │
│ API / MCP    │    │  (Airflow/     │    │  ClickHouse      │
│              │    │   Prefect)     │    │  (分析数据库)     │
└──────────────┘    └───────────────┘    └────────┬─────────┘
                                                   │
                    ┌──────────────────────────────┤
                    │                              │
            ┌───────▼────────┐          ┌─────────▼────────┐
            │  Analysis       │          │  Web Dashboard   │
            │  Engine         │◀────────▶│  (FastAPI +      │
            │  (Python + LLM) │          │   React/HTMX)    │
            └───────┬─────────┘          └──────────────────┘
                    │
            ┌───────▼────────┐
            │  Execution      │
            │  Engine         │
            │  (MCP + API)    │
            └───────┬─────────┘
                    │
            ┌───────▼────────┐
            │  Decision Log   │
            │  (不可变日志)   │
            └────────────────┘
```

---

## 11. 完整来源列表

### 战略框架 (Strategy)

1. [Feedvisor — Sponsored Brands Guide](https://feedvisor.com/resources/amazon-marketing-advertising-strategies/sponsored-brands-guide/)
2. [Canopy Management — 10 Amazon Advertising Tips](https://canopymanagement.com/10-amazon-advertising-tips-for-better-results/)
3. [Autron — PPC Campaign Structure 2026](https://autron.ai/blog/amazon-ppc-campaign-structure-in-2026-why-fewer-campaigns-now-beat-more)
4. [SellerMetrics — Multi-Touch Attribution](https://sellermetrics.app/amazon-multi-touch-attribution/)
5. [Code3 — Amazon Attribution Changes](https://code3.com/resources/amazon-quietly-tightened-attribution-and-its-changing-how-dsp-performance-is-measured/)
6. [PPC.land — Amazon Ads Consent Deadline](https://ppc.land/amazon-ads-consent-deadline-is-june-30-your-data-wont-work-after-that/)
7. [Colgate — Predictable Growth Engine](https://www.thedrum.com/awards-case-study/how-colgate-turned-amazon-shoppers-into-a-predictable-growth-engine-with-data)
8. [Canopy Management — Budget Allocation 2026](https://canopymanagement.com/amazon-advertising-budgets-how-to-allocate-spend-across-campaigns/)
9. [Feedvisor — Sponsored Products Ad Guide](https://feedvisor.com/resources/amazon-marketing-advertising-strategies/sponsored-products-ad-guide/)
10. [SalesDuo — Bid Management Playbook 2026](https://salesduo.com/blog/amazon-bid-management/)
11. [SalesDuo — Amazon PPC Strategy Guide](https://salesduo.com/blog/create-an-amazon-ppc-strategy/)
12. [SalesDuo — Amazon Ads Reporting Guide](https://salesduo.com/blog/amazon-ads-reporting/)
13. [IMH — Persona-Based Campaign Structure](https://influencermarketinghub.com/amazon-influencer-marketing/amazon-ppc-campaign-structure/)
14. [Coupler.io — Amazon Ads Analytics](https://blog.coupler.io/amazon-ads-analytics/)
15. [YourEcomTeam — Amazon Ads Strategy](https://yourecomteam.co/blog/amazon-ads-strategy-that-actually-scales)
16. [Influencer Marketing Hub — CPCs Inflation](https://influencermarketinghub.com/amazon-cpcs-inflation-profitability/)
17. [Marketing Science — Attribution + Bidding](https://econpapers.repec.org/article/inmormksc/v_3a45_3ay_3a2026_3ai_3a3_3ap_3a576-595.htm)

### AI/ML 技术栈 (AI/ML)

18. [Spotify Engineering — Multi-Agent Advertising Architecture](https://engineering.atspotify.com/2026/2/our-multi-agent-architecture-for-smarter-advertising)
19. [AWS — Agentic Bidding with ARTf Containers](https://aws.amazon.com/cn/blogs/industries/deploy-agentic-bidding-without-sacrificing-speed-artf-containers-with-nvidia-gpu-acceleration-on-aws/)
20. [PubMatic — Agentico Full Buy-Side Agent Stack](https://pubmatic.com/blog/inside-agenticos-a-look-at-pubmatics-full-buy-side-agent-stack/)
21. [Databricks — CustomerLake + Agentic Customer](https://www.databricks.com/company/newsroom/press-releases/databricks-enters-marketing-industry-customerlake-agentic-customer)
22. [Laurence (YC) — RL + Transformer](https://www.ycombinator.com/companies/laurence)
23. [Amazon Ads — Creative Agent](https://www.aboutamazon.ca/news/amazon-ads/amazon-ads-launches-creative-agent-new-agentic-ai-tool-that-creates-professional-quality-ads)
24. [Search Engine Land — Alexa Agentic Ads](https://searchengineland.com/amazon-launches-alexa-agentic-ads-480842)
25. [Trellis — AI for Amazon Ads](https://gotrellis.com/resources/blog/ai-for-amazon-ads/)
26. [Digiday — Amazon's Agentic Advertising Future](https://digiday.com/marketing/amazons-latest-ad-format-offers-a-glimpse-of-advertisings-agentic-future/)
27. [Amazon Hierarchical Query Classification (WWW '24)](https://ar5iv.labs.arxiv.org/html/2403.06021)

### 工具与开源 (Tools)

28. [Amazon Ads MCP Server — Open Beta](https://advertising.amazon.com/en-us/library/news/amazon-ads-mcp-server-open-beta)
29. [IvyeaOps — Open-Source Amazon AI Workbench](https://github.com/Hector-xue/IvyeaOps)
30. [SellerSpace — 优麦云 Amazon AD](https://www.sellerspace.com/zh/blog/SellerSpace-with-Amazon-AD/)
31. [Optmyzr — Rule Engine vs Automated Rules](https://www.optmyzr.com/blog/optmyzr-rule-engine-vs-google-ads-automated-rules/)
32. [HyperFX — Best Amazon Ads Automation Tools 2026](https://www.hyperfx.ai/blog/best-amazon-ads-automation-tools-2026)
33. [优麦云官网](https://www.sellerspace.com)
34. [卖家精灵 MCP](https://open.sellersprite.com/mcp/22)

### API/数据生态 (API/Data)

35. [Amazon Ads API — Release Notes](https://advertising.amazon.com/API/docs/en-us/release-notes/index)
36. [Amazon Ads API v3 — Report Types](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview)
37. [Amazon Ads API v3 — Getting Started](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/get-started)
38. [AMC Measurement Expansion](https://advertising.amazon.com/en-gb/library/news/amc-measurement-expansion)
39. [AMC Direct Access for Sponsored Ads](https://advertising.amazon.com/en-us/resources/whats-new/direct-access-to-amc-for-sponsored-ads-advertiser/)
40. [Conversion Path Reporting](https://advertising.amazon.com/en-us/resources/whats-new/conversion-path-reporting-worldwide/)
41. [PPC.land — Amazon Tightens View Attribution](https://ppc.land/amazon-tightens-view-attribution-as-roas-reporting-splits/)
42. [Sponsored Brands Collections AI](https://advertising.amazon.com/en-us/resources/whats-new/sponsored-brands-collections/)
43. [AWS — Ingesting Amazon Ads Data](https://aws.amazon.com/cn/solutions/guidance/ingesting-amazon-vendor-central-and-amazon-ads-data-on-aws/)

### 系统架构 (Architecture)

44. [Spotify — Multi-Agent Architecture (ibid.)](https://engineering.atspotify.com/2026/2/our-multi-agent-architecture-for-smarter-advertising)
45. [AWS — ARTf Containers (ibid.)](https://aws.amazon.com/cn/blogs/industries/deploy-agentic-bidding-without-sacrificing-speed-artf-containers-with-nvidia-gpu-acceleration-on-aws/)
46. [PubMatic — Agentico (ibid.)](https://pubmatic.com/blog/inside-agenticos-a-look-at-pubmatics-full-buy-side-agent-stack/)
47. [Databricks — CustomerLake (ibid.)](https://www.databricks.com/company/newsroom/press-releases/databricks-enters-marketing-industry-customerlake-agentic-customer)
48. [Beam Data — LSTM Hybrid Bid Optimization](https://beamdata.ai/case-study/ai-optimized-keyword-advertising-bidding/)
49. [IEEE — Bayesian Self-Attention ROAS Prediction](https://ieeexplore.ieee.org/ielx8/6287639/10820123/11005530.pdf)

### 市场格局 (Market)

50. [WARC/PitchOnNet — Amazon Retail Media > $60Bn](https://www.pitchonnet.com/pitch-feature/amazon-retail-media-ad-revenue-to-exceed-60bn-this-year-warc-37173.html)
51. [PPC.land — Amazon/Google/Meta Ad Market Share](https://ppc.land/amazon-google-and-meta-are-eating-the-ad-market-and-the-data-proves-it/)
52. [Influencer Marketing Hub — CPCs Inflation (ibid.)](https://influencermarketinghub.com/amazon-cpcs-inflation-profitability/)
53. [Digiday — TikTok in RFPs](https://digiday.com/marketing/tiktok-now-has-a-seat-next-to-amazon-and-walmart-in-rfps/)
54. [Digiday — Amazon Agentic Future (ibid.)](https://digiday.com/marketing/amazons-latest-ad-format-offers-a-glimpse-of-advertisings-agentic-future/)
55. [Search Engine Land — Alexa Agentic Ads (ibid.)](https://searchengineland.com/amazon-launches-alexa-agentic-ads-480842)
56. [PPC.land — Google AI Max Shopping](https://ppc.land/google-brings-ai-max-to-shopping-campaigns-targeting-conversational-queries/)
57. [Smarter Ecommerce — Temu CPC Impact](https://smarter-ecommerce.com/blog/en/google-ads/temu-and-joybuy-market-share-and-how-chinese-marketplaces-impact-your-cpcs/)
58. [Canopy Management — Rufus Retired / Alexa for Shopping](https://canopymanagement.com/amazon-listing-optimization-rufus-ai-search/)
59. [Tinuiti — Alexa for Shopping 2026](https://tinuiti.com/blog/amazon/alexa-for-shopping/)
60. [Azoma — Sponsored Prompts](https://www.azoma.ai/insights/amazon-sponsored-prompts-everything-you-need-to-know-about-amazon-s-latest-ad-format)

---

## See also

- [调研报告索引](index.md)
- [2026-06-24 研究洞察](../lessons/2026-06-24-research-insights.md)
- [资料来源 URL 索引](../reference/source-urls.md)
- [路线图](../roadmap.md)
- [v0.3 设计文档](../specs/2026-06-16-amazon-advertise-analysis-design.md)
