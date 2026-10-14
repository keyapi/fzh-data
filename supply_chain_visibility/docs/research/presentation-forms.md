---
okf: v0.1
type: Reference
title: 供应链可视化的呈现形式调研 + 需求头脑风暴 + 建议路线
description: 「从下单到出库」信息呈现能力该做成什么形式 —— ERPNext 原生 / 独立大屏 / AI 查询 / 嵌入单据 四类对比（带原始 URL）+ 本场景适配 + 头脑风暴 + 建议
date: 2026-10-13
category: architecture-patterns
module: en_api
problem_type: architecture_pattern
component: supply-chain-visibility-presentation
tags: [supply-chain, visibility, erpnext, frappe, dashboard, control-tower, nl2sql, mcp,
       otif, epcis, dcsa, brainstorm]
related_components: [item_shipment_status, fulfillment_query, en-end-to-end-supply-chain-fulfillment-visibility]
---

# 供应链可视化的呈现形式调研 + 需求头脑风暴 + 建议路线

> **背景**：EN 里已有「下单→生产→出库」的链路查询能力（`EN_API/fulfillment_query.py`）。
> 绍兴工厂负责人想把「整条链的信息呈现/查询」做到 EN 上，**形式未定**。
> 本文做三件事：① 对比四类呈现形式（带原始 URL）；② 梳理公认设计要素；③ 头脑风暴需求 + 给建议路线。
>
> 事实底盘见 `EN_API/docs/research/en-supply-chain-map.md`；目标架构见
> `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md`。
> **说明**：标「厂商引用」的数据来自厂商/咨询自证材料，需按本公司实际复核；标「一手」的是官方文档/标准/论文。

## 1. 四类呈现形式对比

### 1.1 ERPNext / Frappe 原生

**定位：适合「KPI 汇总 + 例外列表 + 导航入口」，不适合「事件级时间线 / 阶段状态机」的复杂交互。**

| 手段 | 能力 | 限制 |
|---|---|---|
| Report Builder | 零代码单表列表+分组 | 仅单表 |
| Query Report | 手写 SQL 可 join | 托管环境常被禁 |
| **Script Report** | Python+JS，可返回 `chart`（bar/line/pie/donut）与 `report_summary`（KPI 卡）| 需 Developer Mode；>10 万行/>30s 需 `prepared_report` |
| **Dashboard Chart** | 数据源含 **Custom（`dashboard_chart_source` hook 挂白名单 Python）** | 复杂交互弱 |
| **Number Card** | 聚合 / 取 Report 列 / **调自定义 Python 方法** | 同上 |
| Workspace | 12 栅格布局，`content` JSON 与子表须同步 | 组件须作 fixtures 发布 |
| Custom Page / Desk Page (island) | 自由布局屏 | 权限二元；**官方明说：适合看板/汇总屏，不适合替代表单做单据生命周期** |

> **打通点**：你们已有 Python 管道 —— 用 **Dashboard Chart 的 Custom source + Number Card 的 `function`** 可直接把管道结果喂进原生图表，零新前端。
> **原生做「供应链/生产看板」的硬伤（一手 issue/案例）**：ERPNext 核心制造无 OEE、无停机分类、无有限产能排程；核心团队在 [issue #49149](https://github.com/frappe/erpnext/issues/49149) 判定这类需求「本身就是一个独立产品」。[Floorgraph](https://cloud.frappe.io/marketplace/apps/floorgraph) 这类 MES 层因此存在。真实痛点案例：[Ksolves 精密工程](https://www.ksolves.com/case-studies/erpnext/manufacturing-erp-transformation-precision-engineering) —— 根因常是「数据录入时机」（Job Card 只在班末更新 → 只能给昨天的数字）。
> **实时**：`frappe.publish_realtime(event, msg, after_commit=True)`，房间 `doc:{dt}/{name}`；`frappe.ui.RealtimeChart`。[Frappe Realtime API](https://docs.frappe.io/framework/user/en/api/realtime)

### 1.2 独立 Web / 大屏（控制塔）

**定位：技术路径清晰；但「只做漂亮大屏」是被反复验证的坑 —— 价值在「决策/行动闭环」。**

- 现成前端：[Frappe UI（Vue 3 + Tailwind，官方）](https://ui.frappe.io/docs/getting-started/standalone) 可 standalone；社区 [frappe-ui-react](https://github.com/rtCamp/frappe-ui-react)；[Doppio CLI](https://github.com/NagariaHussain/doppio) `bench add-spa` 一键搭 SPA。
- 设计要素（可落地）：[LightSource 控制塔](https://lightsource.ai/glossary/supply-chain-control-tower) 的三层 **Sense–Evaluate–Respond**，其中 Evaluate（阈值化：1100 单周进货标 60 迟，但只有击穿库存天数的 9 单需处理）才是真价值；[Locus 决策延迟](https://locus.sh/blogs/control-tower-exception-lead-time-2026/) 指出核心是「lead-time gap」而非数据延迟。
- **反营销（重要，多条一致）**：[Shipsy：可见性从来不够](https://www.shipsy.ai/insights/system-of-action-why-visibility-isnt-enough) —— 多数控制塔建成「Systems of Visibility」，默认有人会行动，结果人头没减、毛利没收窄；[Logistics Management：控制塔的神话与现实](https://www.logisticsmgmt.com/article/the_supply_chain_control_tower_myth_and_reality/magazine_archive)。厂商引用数据（需复核）：仅 2/10 组织能实时看清 75–100% 供应链；一次中断平均 34 次手动系统更新、跨 6 个平台（Gartner）。

### 1.3 AI / 对话式查询（NL2SQL / MCP）

**定位：作「内部受监督的运维助手」可用；作「面向业务员的自助查询入口」在你们这种自定义 schema 上高风险。**

- **裸 NL2SQL 的风险（一手）**：[Stonebraker & Chen, CACM](https://cacm.acm.org/opinion/if-you-think-you-can-do-real-world-text-to-sql/) —— 生产系统会「生成语法正确但语义错误的查询时**静默失败**」；企业基准 **Beaver** 上纯 LLM 得分为**零**，加 RAG+agentic 才 10+%，给金标 join 才 30+%（公开 Spider/BIRD 80–90%+ 是假象）。供应链特有歧义：「订购数量」vs「占用体积」。
- **缓解**：**治理化语义层**先解析术语再让模型写 SQL（可 70% → 95–100%）；[AWS 供应链置信度评分论文](https://ar5iv.labs.arxiv.org/html/2506.17203) 给出可做低置信过滤的校准方法。
- **MCP 接入 ERPNext 的现成路径**：[frappe-mcp-server (PyPI)](https://pypi.org/project/frappe-mcp-server/)、[@casys/mcp-erpnext](https://jsr.io/@casys/mcp-erpnext)、[hatlabs/erpnext-mcp-server](https://github.com/hatlabs/erpnext-mcp-server)、[o-M7MD/erpnext-mcp](https://github.com/o-M7MD/erpnext-mcp)（白名单 DocType/方法 + 列表硬上限）。**安全共识**：受限专用只读账号 + 白名单，不用 System Manager 密钥。
- **AI 在供应链的真落地 vs 噱头（一手）**：[Gartner 2026-05](https://www.gartner.com/en/newsroom/press-releases/2026-05-06-gartner-survey-shows-ai-is-not-driving-supply-chain-operating-model-transformation) 调研 140 位高管：仅 17% 在做立即的变革性重构、83% 只做增量；[Zero100](https://zero100.com/insights/bold-vision-real-stories-pragmatic-action-takeaways-from-live-2025/) 74% 仍在试点。真落地是**窄域监督式**（报价自动化、异常检测、履约跟踪），不是端到端「自驾驶供应链」。

### 1.4 嵌入单据内（Sales Order 表单）

**定位：性价比最高、风险最低的「第一刀」。**

- 现成能力：`frm.dashboard.add_doctype_section(...)`（关联 DocType 计数）、`frm.dashboard.add_transactions({items:[...]})`（**关联单据链接 = connected documents**）、`frm.dashboard.add_section(body_html, ...)`（自定义 HTML 区块）。[Mastering Frappe Form Dashboards](https://dexciss.tech/blog/developer-posts/mastering-frappe-form-dashboards-a-developer%e2%80%99s-how-to-guide)
- HTML 字段是 **Layout 类、无数据库列（no_value_fields）**，只做展示；[Custom Field](https://docs.frappe.io/erpnext/custom-field)。
- 用 `doc:{dt}/{name}` 实时房间让打开者看到最新状态。
- **局限**：只宜只读摘要/链接，别塞完整时间线交互。

## 2. 供应链可视化设计要素（能落地版）

| 要素 | 要点 | 来源 |
|---|---|---|
| **事件数据模型** | 每次输入当**不可变事件** append-only；归一到 canonical schema；连接器优雅失败（静默停更的看板比没有更糟） | [Direlli](https://direlli.com/blog/supply-chain-visibility-software) |
| **事件时间线** | 以「今天」为中心，负=逾期/正=预期；区分 instant vs interval 事件 | [US20140098104A1](https://patentimages.storage.googleapis.com/8b/47/98/8426761a8d7f4a/US20140098104A1.pdf) |
| **阶段状态机 + 事件溯源** | 用 DDD+CQRS+ES，任意时刻可重建单元位置与历史；审计轨迹=系统记录本身 | [Axoniq 汽车厂商案例](https://www.axoniq.io/customer-stories/global-automotive-manufacturer) |
| **数量对账** | 三单匹配（PO↔收货↔发票）；**最大成因是单位不一致**（下单按箱/收货按件）；药方：强制收货六字段 + 显式完成状态 | [Zycus](https://www.zycus.com/blog/intake-management/three-way-match-supplier-requirements)、[pypi threeway](https://pypi.org/project/threeway/) |
| **例外管理** | 阈值化 + 按责任人路由；四级：描述→诊断→预测→**规范（建议/自动响应）** | [KPIPartners 案例 PDF](https://www.kpipartners.com/hubfs/GenAICase%20Study_Supply%20Chain%20Visibility.pdf) |
| **OTIF KPI** | 按时 ∧ 足量 同时成立；两锚点须先与客户对齐（「按时」锚到哪个日期、早到是否算 fail；「足量」容差常 ±10%/行） | [Orkestra OTIF](https://www.orkestrascs.com/resources/guides/otif)、[nShift](https://nshift.com/blog/otif-on-time-in-full) |
| **标准 schema 参照** | DCSA T&T（shipment/transport/equipment/IoT/reefer 五类事件，月处理 1.8 亿+ 集装箱事件）；GS1 EPCIS 2.0（WHAT/WHEN/WHERE/WHY/HOW；ObjectEvent/AggregationEvent/TransformationEvent/TransactionEvent） | [DCSA T&T 3.0.0](https://dcsa.org/newsroom/track-and-trace-3-0-0-iot-reefer-visibility)、[GS1 CBV](https://ref.gs1.org/standards/cbv/) |

## 3. 本场景适配度初判

> 场景：绍兴工厂 + 美国/波兰海外仓 + 跨境；已有 Python 数据管道；现场 ERPNext。

| 形式 | 适配 | 说明 |
|---|---|---|
| 嵌入单据内 | ★★★★★ | 零新前端、零跳转，把该 SO 相关 WO/采购/发货/追踪贴进表单。**先做这个。** |
| ERPNext 原生 KPI/例外 | ★★★★☆ | 用 Custom Chart/Number Card `function` 接 Python 管道，出 OTIF/例外数/阶段停留；定位为「聚合与导航」，别指望事件级交互 |
| 独立 Web/大屏 | ★★★☆☆ | 技术路径清晰（Frappe UI/Doppio），但**只做漂亮大屏会重演「看板淹没」**；若做，务必带阈值化的例外队列 + 责任人/playbook |
| AI/对话式 | ★★☆☆☆ | 仅作内部受监督助手（MCP + 只读受限账号 + 白名单）；**不要**做成面向业务员的自助入口；要做也必须先有治理语义层 |

## 4. 需求头脑风暴（按角色，供筛选）

**销售/客户服务**
- 「客户问 A 款什么时候能发」→ 一句结论 + 依据可信度（事实/推导/估算）
- 交期风险预警：哪些单交期已过/将过仍未发
- 一单多物料是否**齐套**、缺哪个件

**计划/生产**
- 未发需求是否已排产、有无工单、瓶颈工序是哪道、最后真实报工时间
- 超产/少产、工序停滞、工单头部滞后（`WO.status` 不可信）
- 开料/扫码进度（Cutting Task / Tracking Number 菲号）
- 物料需求/采购是否到位（MR/PO/PR）—— **当前 EN 侧空白**

**物流/国外仓**
- 工厂已出库未绑头程、ZM 批次、ETD/ATD/ETA/ATA、清关、签收、上架（**阶段 4–8 外置**）

**供应链负责人（控制塔）**
- 各阶段压了多少单/量/金额；哪些影响客户承诺或海外仓断货
- 异常是否有人负责；OTIF / 计划达成率 / 阶段停留时长

## 5. 建议路线（我的决定）

**分三档，从低风险到高价值；每档都可独立交付。**

1. **【先做】嵌入单据内**：给 Sales Order（可能还有 Work Order）表单加一个只读区块/HTML 字段，贴该单的链条摘要（阶段、已发/未发、工序瓶颈、齐套、异常）+ 链接到本仓库的查询脚本/报表。**零架构风险、立刻有用。**
2. **【再做】ERPNext 原生报表/看板**：把 `EN_API/fulfillment/` 的 JSON 结果经 Custom Chart/Number Card/`report_summary` 接进原生，出**角色化 KPI + 例外列表**。度量用**例外解决时长/阶段停留**，不是看板数量。
3. **【视需要】小范围独立屏**：只做「例外队列 + ETA + 责任人」，不做全量大屏；AI/MCP 仅作内部监督助手。

**先不做**：物料需求 / 采购订单 / 采购入库（EN 侧基本空白，且业务侧尚不明确）—— **按用户指示先记录、之后再做**；头程阶段 4–8 已决定暂缓。

## 6. 交给其他工具/模型的问题清单

供 Cursor/Codex 用别的模型平行研究（无唯一答案）：

1. 嵌入 SO 表单的「链条摘要」最小字段集是什么？哪些必须实时、哪些可 T+1？
2. 「齐套」的库存范围口径（工厂侧 vs 含国外仓）业务上怎么定？
3. ERPNext 原生能不能承载「阶段状态机 + 事件时间线」，还是必须独立屏？
4. 术语歧义（数量/体积、菲号/跟踪号）如何建语义层？
5. 例外队列的阈值与责任人路由规则如何定？
6. OTIF 的「按时」锚到哪个日期、「足量」容差多少？

## Related

- `EN_API/docs/research/en-supply-chain-map.md` — EN 全链路实体地图与仓库覆盖
- `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md` — 目标架构蓝图（阶段 0–9）
- `EN_API/docs/reference/en-order-to-shipment-chain.md` — 链路导航
- `docs/solutions/architecture-patterns/sellfox-shipping-research-and-architecture.md` — 上架后尾程
