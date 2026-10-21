---
type: Reference
title: 预测与Agent来源及核实状态
date: 2026-10-20
status: research-source-ledger
---

# 供应链预测与 Agent 研究来源账本

访问日均为 2026-10-20。表中“核实”区分实际打开阅读与只读到索引/摘要；发布日期/版本写来源本身标示的信息，不等同本次核实内容。每条 URL 按一个主用途唯一计数；同一模型或基准的镜像不额外计数。

## 来源清单

| claim_id | 主用途 | URL | 位置 | 访问日 | 版本日期 | 短摘要 | 局限 | 核实状态 |
|---|---|---|---|---|---|---|---|---|
| F-01 | 间歇基线 | [Croston, Forecasting and stock control for intermittent demands](https://www.sciencedirect.com/science/article/pii/0169207094900213) | Abstract / 方法背景 | 2026-10-20 | 1994 网页重印；原法 1972 | Croston 对非零需求量和间隔分别平滑，是间歇需求的重要基线 | 后续研究指出偏差；需注意原文/重印日期 | 搜索结果与索引已核；未取全文 |
| F-02 | 间歇基线 | [Babai et al., Intermittency and obsolescence: a Croston method with linear updates](https://pure.rug.nl/ws/files/173756136/1_s2.0_S0925527314002771_main.pdf) | 引言、Croston/SBA/TSB 讨论 | 2026-10-20 | 2014 | 说明 Croston 偏差、SBA 修正与 TSB 对需求发生概率的更新 | 实证 SKU/行业非本公司 | 已打开；全文片段可读 |
| F-03 | 概率预测基线 | [Salinas et al., DeepAR](https://arxiv.org/abs/1704.04110) | Abstract、§1 | 2026-10-20 | 2017 / 后刊 2020 | 在相关序列上训练全局自回归概率预测器；面向规模化系列及不确定性 | 结果取决于相关序列数量、特征与需求分布 | 已打开；Abstract 与正文可读 |
| F-04 | 删失需求 | [Demand forecasting under lost sales stock policies](https://www.sciencedirect.com/science/article/pii/S0169207023000961) | Abstract / 引言 | 2026-10-20 | 2023 | 讨论 lost-sales 库存下销量删失和预测问题 | 本次目标站打开失败，依据搜索索引摘要；应再取全文核查具体方法 | 索引摘要已核；未打开全文 |
| F-05 | 统计/工程实践 | [AWS Demand Forecasting whitepaper](https://docs.aws.amazon.com/whitepapers/latest/demand-forecasting/demand-forecasting.html) | Abstract、数据与架构指南 | 2026-10-20 | 页面版本日期未清楚显示；截至访问日在线版 | 面向产品/材料预测，覆盖数据源、统计和 ML 方案及管道 | 厂商方案材料，非独立效果评估；面向 AWS 技术栈 | 已打开；摘要/目录内容可读 |
| M-01 | 时序基础模型 | [Chronos: Learning the Language of Time Series](https://arxiv.org/abs/2403.07815) | Abstract | 2026-10-20 | 2024-03；TMLR 2024 | 离散化时序并用语言模型训练概率预测，报告公开基准 zero-shot 能力 | 训练集重叠与行业迁移、长跨度及库存成本需本地重测 | 已打开；摘要可读 |
| M-02 | 时序基础模型 | [Chronos-2: From Univariate to Universal Forecasting](https://arxiv.org/abs/2510.15821) | Abstract、方法概述 | 2026-10-20 | 2025-10 | group attention 在相关目标/协变量序列间做 in-context 信息共享，支持未来已知和历史协变量 | 论文中的 benchmark 结果非独立复现；需按公司预测截止时点构造协变量 | 已打开；摘要、引言片段可读 |
| M-03 | 时序基础模型 | [Google Research: TimesFM-3](https://research.google/blog/timesfm-3-a-zero-shot-foundation-model-for-multivariate-forecasting/) | §Evaluation、促销协变量示例 | 2026-10-20 | 2026-08-31 | 官方报告多变量 zero-shot；未来促销协变量示例展示模型响应促销日 | 供应商自报的公开基准；示例不是公司结果，不等于强因果促销估计 | 已打开；评估和示例可读 |
| M-04 | 时序基础模型 | [Salesforce, Unified Training of Universal Time Series Forecasting Transformers (Moirai)](https://arxiv.org/abs/2402.02592) | Abstract | 2026-10-20 | 2024-02；ICML 2024 | Moirai 1 使用 LOTSA 预训练，关注跨频率/多变量 zero-shot | 早期版本；后续模型接口和权重条款需单独核验 | 已打开；摘要可读 |
| M-05 | 时序基础模型 | [Moirai 2.0: When Less Is More](https://arxiv.org/abs/2511.11698) | Abstract、§2、§5 | 2026-10-20 | 2025-11-12 | 以分位数损失、decoder-only 和多 token 预测改进效率；GIFT 上给出比较 | 论文自报；正文说明将多变量拆为独立 univariate，不建模跨变量依赖 | 已打开；摘要和限制可读 |
| M-06 | 模型代码/权重许可 | [Google Research TimesFM 官方仓库](https://github.com/google-research/timesfm) | README “Update—September 2026”“License notice for pretrained weights” | 2026-10-20 | 2026-09 README，TimesFM 3.0 | 明确区分代码 Apache-2.0、TimesFM 权重至 2.5 的 Apache-2.0，以及 TimesFM 3.0 自托管权重的非商用/非生产限制；另注明 Google Cloud 服务条款 | 官方仓库自述；具体模型卡/服务条款仍应按部署路径复核；代码许可证不能替代权重许可 | 已打开；许可与版本段落可读 |
| M-07 | 模型代码/权重发布 | [Salesforce uni2ts 官方仓库](https://github.com/SalesforceAIResearch/uni2ts) | README “Resources”“What’s New” | 2026-10-20 | 访问日仓库；Moirai-2.0-R-small 发布记录 2025-08 | 仓库代码标 Apache-2.0；README 链接 Moirai 2.0 权重并明确它们单独发布 | 代码许可不证明权重许可；本次未逐个读 Hugging Face checkpoint 的许可证 | 已打开；代码许可、发行说明可读 |
| M-08 | 模型代码/权重发布 | [Amazon Science Chronos 官方仓库](https://github.com/amazon-science/chronos-forecasting) | README “License”“News”“Available Models” | 2026-10-20 | 访问日仓库；Chronos-2 2025-10-20 | 仓库代码 Apache-2.0，列出 Chronos-2 的发布和模型 ID | Apache 是项目代码许可证；不同 checkpoint 的权重许可仍需读对应 model card | 已打开；许可和模型版本段落可读 |
| B-01 | 通用预测基准 | [GIFT-Eval](https://arxiv.org/abs/2410.10393) | Abstract、§3/4、失败案例与泄漏分析 | 2026-10-20 | 2024-10-14 | 23 数据集、144K 系列、177M 测试点；覆盖七领域和多频率；报告基础模型长跨度/尖峰失配以及预训练泄漏影响 | 数据是公开领域组合，非跨境 SKU 家族/促销/BOM/多仓业务损失；榜单版本继续变化 | 已打开；正文相关章节可读 |
| B-02 | 零售层级基准 | [M5 Accuracy competition: results, findings, conclusions](https://doi.org/10.1016/j.ijforecast.2021.11.013) | Abstract、低层级结果讨论 | 2026-10-20 | 2022（期刊在线版本 2021） | Walmart 商品×门店层级数据低层更间歇随机；促销与层级聚合构成零售挑战 | 日销量、美国门店、28 天跨度；与长头程、电商平台/基础件生产差别明显 | 搜索索引呈现正文摘要；出版页面打开失败 |
| B-03 | 基础模型对统计法反证 | [Foundation or Formula? A Simulation-Based Comparison of TimesFM-3 and Classical Time-Series Models](https://arxiv.org/abs/2610.00589) | Abstract、§3–7（预注册比较、模拟结果、局限） | 2026-10-20 | 2026-09-30 | 对 7,200 条生成序列、九类过程、12 步预测作预注册比较；两家族不统治；4+季节周期时 AutoARIMA 在若干季节过程领先，间歇数据简单历史基线不弱 | 新预印本；过程覆盖不是公司需求；主要 benchmark 外的部分分析为 post hoc；合成数据生成与过程熟悉效应仍可能影响结论 | 已打开；摘要及正文 §3–7 可读 |
| A-01 | Agent 库存基准 | [InventoryBench code and benchmark](https://github.com/TianyiPeng/InventoryBench) | README / benchmark summary | 2026-10-20 | 仓库当前页面；论文见 A-02 | 1,320 实例、4 种 Agent 策略、多期库存控制环境 | 仿真规则、可用动作/成本定义与公司经营差异；代码可核并不代表工业部署有效 | 已打开 README |
| A-02 | LLM+OR+人 | [AI Agents for Inventory Control: Human-LLM-OR Complementarity](https://arxiv.org/abs/2602.12631) | Abstract、研究设置 | 2026-10-20 | 2026-02-13 | 报告 OR 增强 LLM 与人工协作的互补性，并用库存基准和课堂实验研究 | 预印本；课堂参与者、仿真/benchmark 不能外推为公司收益 | 已打开；摘要/引言可读 |
| A-03 | Agent 作为语义界面 | [Ask, Clarify, Optimize](https://arxiv.org/abs/2601.00121) | Abstract | 2026-10-20 | 2026-01 | 报告端到端 LLM 求解有 hallucination tax；让 LLM 澄清参数、调用优化计算可降低实验库存成本 | 预印本、指定实验设计与基线；32.1% 是论文自身实验结果，不可直接外推 | 已打开；Abstract 可读 |
| A-04 | 工具与审批规范 | [OpenAI Programmatic Tool Calling](https://developers.openai.com/api/docs/guides/tools-programmatic-tool-calling) | 工具 schema、权限、HITL、Evaluate | 2026-10-20 | 官方在线文档；访问时页面未标单一发布日期 | 建议明确工具输入/输出 schema、应用端权限、幂等和高影响动作审批，并测质量/安全/延迟/成本 | 官方产品文档是实现指导，不是对库存系统正确率的研究；JSON 合法不等于语义正确 | 已打开；相关章节可读 |
| A-05 | 工具语义/策略执行 | [Open Policy Agent: Agent Tool Calling](https://www.openpolicyagent.org/docs/agent-tool-calling) | Policy enforcement flow、operational benefits | 2026-10-20 | 在线官方文档；访问日版本 | 把模型的工具调用当结构化请求，由 harness 在执行前以独立策略点检查工具名/参数；决策日志记录准/拒调用 | 是策略控制模式，不提供商品 SKU、BOM、库存状态的语义映射，也不保证业务数据正确 | 已打开；流程和日志能力可读 |
| C-01 | 大规模供应链案例 | [Amazon: AI makes holiday shopping more convenient](https://www.aboutamazon.com/news/operations/amazon-uses-ai-to-improve-shopping) | §Stocking the right products | 2026-10-20 | 2023-11 左右（页面日期） | Amazon 描述 SCOT 为数亿商品预测、分布库存与协调卖家货运的系统 | 公司自述，缺可复现外部指标；规模和数据不适用于小型跨境卖家 | 已打开；段落可读 |
| C-02 | 企业供应链决策支持 | [AWS Supply Chain announcement](https://press.aboutamazon.com/2022/11/aws-announces-aws-supply-chain) | 官方新闻稿 / 产品能力段 | 2026-10-20 | 2022-11-29 | 描述统一数据湖、ML shortage/delay insights、库存管理者创建 watchlists 并采取建议动作 | 厂商发布材料；不证明 Agent 自主决策有效，也非同行评审案例 | 搜索摘要已核；未打开正文 |
| C-03 | 生产环境供应链 Agent 案例 | [AWS customer case: OPLOG](https://aws.amazon.com/solutions/case-studies/oplog/) | Overview、Solution、Outcome | 2026-10-20 | 首个 production agent 于 2025-08 上线；案例页当前版本访问日 | AWS 报告 OPLOG 生产多 Agent 协调履约资源，称决策时间降 90%、运营成本降 30–40%、SLA +3.5pp | AWS/客户自报，没有独立对照评估；应用是履约运营资源分配，不是 SKU 需求预测、补货或 BOM 排产 | 已打开；部署时间、场景、结果可读 |

## 候选数与去重对账

按上表唯一 URL 的主用途互斥计数：

| 主用途 | 候选数 | 全文 | 章节/README 段落 | 摘要/目录 | 仅索引/摘要未打开 |
|---|---:|---:|---:|---:|---:|
| 统计/删失基线 F | 5 | 0 | 2 | 1 | 2 |
| 时序基础模型/许可 M | 8 | 0 | 6 | 2 | 0 |
| 预测基准 B | 3 | 0 | 2 | 0 | 1 |
| Agent/OR/工具 A | 5 | 0 | 4 | 1 | 0 |
| 真实供应链案例 C | 3 | 0 | 2 | 0 | 1 |
| **合计** | **24** | **0** | **16** | **4** | **4** |

URL 唯一计数，组间没有重复：5 + 8 + 3 + 5 + 3 = 24。没有一项是全文通读；16 项打开阅读了与主张相关的正文/README 段落，4 项只读到摘要或目录，4 项只核实到索引/搜索摘要且页面未打开。故“20 项已打开”不等于“20 篇全文研究”。两个目标期刊页面的访问器分别报错，保留条目并明确证据限度，不根据摘要捏造未读细节。

## 模型许可与基准适配核验

- 模型代码仓与权重许可链接已经分别纳入 M-06–M-08 来源行。TimesFM 官方 README 明确 TimesFM 2.5 权重仍 Apache-2.0，TimesFM 3.0 下载权重非商用/非生产；仓库另称经授权 Google Cloud 服务可商业生产使用，属于不同部署路径。不得把 3.0 限制倒推至 2.5，也不得把代码许可证自动套给权重。
- Salesforce uni2ts 和 Chronos 仓库可核代码项目许可与版本发行信息，不能单独证明所有公开 checkpoint 的权重许可；每个模型候选应以锁定版本的 model card/许可证为准。
- GIFT-Eval 是模型比较与任务覆盖证据，不是公司成效保证。其论文讨论泄漏会抬升结果且预测跨度增长时更明显。训练/测试地理、频率、稀疏率、促销信息、缺货机制、SKU 映射、BOM 和采购提前期都与公司问题存在潜在 mismatch；榜单需要记录评估版本、模型预训练重叠、切分和指标。
- M5 的商品/门店层级结构与 SKU 家族、多仓有启发，但 M5 销量并不编码我们的包裹拆分与基础件 BOM 变换，更不包含真实头程批次在途。因此它只能帮助构造分层问题与压力切片，不能代替本地回测。

## 本次核实边界

联网以原始论文、官方仓库/产品文档和官方案例为主；OpenAI 产品信息仅引用 OpenAI 官方文档。没有安装或运行模型，没有下载权重，没有运行模型/回测，没有访问 ERPNext/通途/赛狐生产数据与任何凭证。搜索结果只用于发现候选来源；正文中的量化性能陈述优先对应被打开的一手源，并标明论文/厂商自身结果。检索窗口截至 2026-10-20，但网页索引可能滞后；本清单不是对所有 2026 年预印本与 leaderboard 的穷尽证明。
