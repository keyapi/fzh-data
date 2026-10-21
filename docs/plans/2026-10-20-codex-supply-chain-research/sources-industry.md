---
type: Reference
title: 跨境供应链整合独立研究来源与证据登记
description: 记录实际打开阅读的一手官方/学术来源及其支持结论、局限和访问状态。
updated: 2026-10-20
---

# 来源与证据登记

访问日均为 2026-10-20。候选计数只把有实质文本可读、直接支撑某个方法判断的来源列为“已核实”；厂商文档只证明该产品/方法的机制或功能描述，不证明业务效果。

| claim_id | URL | 位置/版本日期 | 摘要 | 证据类别与局限 | 状态 |
|---|---|---|---|---|---|
| C1 | https://jobs.ascm.org/career-resources/find-the-job-1/demand-planning-careers-2026-41 | “The monthly rhythm” §，页面未标清版本，访问 2026-10-20 | S&OP通常月度跨商业、供应、财务与领导达成计划；需求评审后做供应可行性，再由有决策权的人解决需求、供应、财务差距。 | ASCM行业协会职业说明，支持流程/角色模式；不是实证研究或标准强制要求。 | 已核实 |
| C2 | https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26b/fausp/overview-of-constraint-based-supply-planning.html | “Constraint-Based Supply Planning Behavior”“Prioritization of Demand”，Oracle Fusion SCM 26B，访问 2026-10-20 | 约束计划考虑物料/产能；订单优先级规则明确；产能是软约束，最后可能超载，采购/生产提前期通常视为硬约束。 | 厂商产品文档，说明实现机制与边界；不是算法跨产品比较或性能验证。 | 已核实 |
| C3 | https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26b/fausp/plan-considering-resource-constraints-in-a-constrained-supply.html | “Order in Which Capacity Constraints Are Applied” §§，Oracle Fusion SCM 26B，访问 2026-10-20 | 示例顺序为提前生产、替代资源、再超载；非瓶颈资源可不纳入容量约束。 | 厂商示例，不代表贵司路由、工时和软约束参数存在或完整。 | 已核实 |
| C4 | https://learn.microsoft.com/en-us/dynamics365/supply-chain/master-planning/safety-stock-replenishment | “How master planning handles the safety stock constraint”“Minimum key”，更新 2026-03-26，访问 2026-10-20 | 安全库存作为需求类型；需求可消耗缓冲并触发补货；按仓/产品维度设置并可按季节变化。 | 厂商产品文档；证明策略行为，不证明合适安全水平。 | 已核实 |
| C5 | https://learn.microsoft.com/en-us/dynamics365/supply-chain/master-planning/planning-optimization/replenishment-methods-quantity-modification | “Coverage codes”“Impact of the order quantity” §§，更新 2026-07-01，访问 2026-10-20 | Period、Requirement、Min/Max、Manual分别支持批次周期、间歇/按单、高跑量、人工控制；MOQ/倍数会改变数量。 | 厂商文档；用于策略分层候选，分类阈值仍需本地回测。 | 已核实 |
| C6 | https://learn.microsoft.com/en-us/dynamics365/supply-chain/master-planning/planning-optimization/plan-filters | “Run planning for a subset of items”“Combine plan filters and runtime filters”，更新 2023-09-29，访问 2026-10-20 | 规划范围可用固定/运行时过滤限定商品和 BOM 层级，过滤器交集控制范围。 | 厂商功能说明，支持小范围计划/范围闸门设计；特定功能有版本依赖和限制。 | 已核实 |
| C7 | https://upcommons.upc.edu/server/api/core/bitstreams/6f14bac9-af9c-4f1f-baf6-855513bf03b6/content | §4.2–4.3.2，Journal of Industrial Engineering and Management，2021，DOI 10.3926/jiem.3331，访问 2026-10-20 | 系统综述认为未证明 DDMRP 适合所有工业情境；文献主要是教学案例，真实复杂环境/多产品与复杂 BOM 证据不足，缓冲点研究有限。 | 同行评审系统综述；文献覆盖截止/纳入标准可能限制外推。是反对全量预设 DDMRP 的重要证据。 | 已核实 |
| C8 | https://journals.sagepub.com/doi/10.1111/poms.13824 | 摘要与 Introduction §§，Yang & Shi, Production and Operations Management, 2023，访问 2026-10-20 | 失销需求被库存截断，只有销售历史时需求分布难以识别；是否能观察售罄后的额外请求会改变算法适用性。 | 同行评审理论/算法研究，非跨境电商案例；支持删失数据风险，不提供可直接套用的实务修复精度。 | 已核实 |
| C9 | https://arxiv.org/abs/2403.11010 | 摘要，作者版本 2024-03-16，访问 2026-10-20 | 仿真研究指出周期性预测更新会扰动标准 MRP 订单；某安全库存启发式缓解影响。 | 原始研究预印本/仿真，未经此处独立复现；结果取决于建模假设。 | 已核实 |
| C10 | https://arxiv.org/abs/2306.10961 | 摘要，作者版本 2023-06-19，访问 2026-10-20 | MEIO 保证服务模型扩展考虑复核期、制造节点、混合节点、MOQ、不同服务指标，并通过模拟验证案例。 | 原始研究预印本，领域为制药/方法模型；说明 MEIO 复杂性与可处理因素，不是本公司方案验证。 | 已核实 |
| C11 | https://arxiv.org/abs/1901.00090 | 摘要与方法，作者版本 2019-01-01，访问 2026-10-20 | 多级库存模拟优化以 bootstrap 保留需求和交期变化，给定网点服务水平下优化库存；报告集中库存池化在其试验中的偏好。 | 原始研究预印本/特定仿真；库存池化效果依赖网络、服务/运输约束、成本模型。 | 已核实 |
| C12 | https://help.sap.com/docs/SAP_INTEGRATED_BUSINESS_PLANNING/252c83bbf8184915a56d4cdd0917ef06/cdbbdf46dc8d4212b97d0255f0af93a9.html | SAP IBP Feature Scope Description 2605（搜索摘要可见）；页面打开时 0 行正文，访问 2026-10-20 | 搜索索引摘要声称 IBP 多阶段库存优化考虑需求/供应波动、交期、成本和服务目标。 | 厂商页面正文抓取失败，尚未独立核对章节原文；暂不作为强证据。 | 待核实 |
| C13 | https://www.sciencedirect.com/science/article/pii/S092552731300203X | 搜索结果摘要；访问 2026-10-20 | 搜索摘要提到 censored sales、新品/促销等因素下估计未观测失销量。 | 页面正文访问返回 403，摘要不可替代论文阅读。暂不引用为已验证证据。 | 访问失败 |
| C14 | https://docs.frappe.io/erpnext/work-order | “Work Order”“Required Items”“Operations table”“Capacity Planning in Work Order” §§，页面最近更新 2026-10-15（相对访问日显示 5 days ago），访问 2026-10-20 | WO 可由 Production Plan/SO 生成；BOM 产生物料需求；Job Card 更新实际操作时间；工作站基于可用时段排程，且页面描述 operation 要同日完成。 | ERPNext 官方产品手册，支持用现有执行实体映射计划；不同部署版本与定制需核验，不能据此声称任意 APS 能力。 | 已核实 |
| C15 | https://docs.frappe.io/erpnext/bill-of-materials | “BOM”“BOM with Operations”“BOM Template” §§，访问 2026-10-20 | BOM 含买/制物料、子装配与工序并支持多层；需要准确 BOM 才能算准采购请求；BOM 变更有版本/治理成本。 | ERPNext 官方手册；具体字段、有效版本及公司自定义仍待抽样核验。 | 已核实 |
| C16 | https://docs.frappe.io/erpnext/capacity-planning | “Capacity Planning based on Work Order” §§，页面最近更新约 2026-02，访问 2026-10-20 | ERPNext 的工位能力规划把 Operation/Workstation 通过 BOM/WO 安排，按工位工时处理，页面要求操作在一天内完成或拆小/允许加班。 | ERPNext 官方手册；可能随版本变化，实机计划能力未验证。 | 已核实 |
| C17 | https://docs.frappe.io/erpnext/auto-creation-of-material-request | “Reorder Level”“Auto Creation” §§，页面最近更新约 2026-02，访问 2026-10-20 | ERPNext 可按商品/仓库 Reorder Level 与 Qty 自动生成 Material Request，也可以设定采购或仓间调拨；比较 projected qty。 | ERPNext 官方手册；阈值触发不能替代带预测、长交期、跨系统/多级 BOM 的总体计划。 | 已核实 |
| C18 | https://aas.net.cn/cn/article/doi/10.1360/aas-007-0181 | 搜索摘要为中文摘要，自动化学报 2007, 33(2):181–187，DOI 10.1360/aas-007-0181；页面打开 2026-10-20 返回 internal error | 检索结果摘要描述协同多级库存多目标优化同时考虑需求满足率、时间、成本、复杂网络、库容与生产能力约束。 | 中文原始论文的元数据/摘要可见，但全文页面无法打开；未纳入核实候选，作为访问失败。 | 访问失败 |
## 来源数量对账

- 不重复计算的来源页面共 18 个：15 个已核实候选 + 1 个待核实 + 0 个排除 + 2 个访问失败，算式为 `18 = 15 + 1 + 0 + 2`。
- 有实质正文且实际阅读：15 个（C1–C11、C14–C17）。SAP 页面打开但正文 0 行，计为待核实 C12；ScienceDirect 的英语论文和《自动化学报》的中文论文页面打开失败，分别计为 C13、C18。
- 已核实候选不是厂商效果验证：C1 是 ASCM 行业协会流程说明；C2–C6、C14–C17 是 Oracle、Microsoft、ERPNext 官方功能文档；C7–C11 是系统综述、同行评审研究/仿真或原始研究预印本，各自适用范围见局限列。中文来源有检索，但此次未获得可读的一手中文全文，故诚实记为访问失败。
## 范围外来源

- DDMRP 厂商/协会自我介绍类页面可说明方法原理，但在已有系统综述情况下不作为独立绩效证据。
- 供应商产品营销页只适合用于盘点模块/宣称能力；没有进入主要证据候选，避免把厂商主张写成实测效果。