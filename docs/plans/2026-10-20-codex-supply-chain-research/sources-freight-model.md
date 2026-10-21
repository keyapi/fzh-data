---
type: Reference
title: 头程事件与多式联运模型来源账本
updated: 2026-10-20
---

# 来源账本

访问日：2026-10-20。计数口径为不重复 URL。实际打开并有正文可读的一手官方规范/官方文档 11 项；另试图打开 UNECE 一份 BRS PDF 和官网入口，工具返回 403/抓取失败，未作为可读证据。没有把公开标准表述成供应商已经实现。

| claim_id | 一手来源 / URL | 位置 | 版本 / 日期 | 支持的主张 | 局限 |
|---|---|---|---|---|---|
| F-01 | [DCSA Track & Trace](https://dcsa.org/standards/track-and-trace) | “A common language”与五类事件 | 在线文档，页面未标固定版本，访问 2026-10-20 | DCSA 将可见性事件分为 shipment、transport、equipment、IoT、reefer 五类，并统一描述海运集装箱旅程 | DCSA 自述其标准范围；不证明所有货代/头程供应商提供 API |
| F-02 | [DCSA implementation guide](https://reference.dcsa.org/content/standards/guidelines/implementation-guides/implementing-track-and-trace) | “Event Publisher/Consumer Implementation” | 在线实施指南，访问 2026-10-20 | 供应商作为 publisher、我方作为 consumer 都需各自实现标准 API/OpenAPI；可用 DCSA sandbox/conformance 场景验证 | 指南不提供我方供应商的连接权限/支持情况 |
| F-03 | [DCSA Information Model 3.0](https://developer.dcsa.org/documentation/information_models/information_model/3.0) | 页面入口/版本历史（当前重定向到 reference 页面） | 3.0 发布 2020-12-08；访问 2026-10-20 | DCSA 信息模型用于整理行业流程中的信息实体和关系，版本 3.0 增加 eBL 域 | 该页面目前重定向且正文无行；此条依据工具读取到的页面简介/版本历史，细节需通过最新 developer portal 再核。未计入 11 项实质阅读候选 |
| F-04 | [UN/CEFACT Web Vocabulary documentation](https://vocab.unece.org/docs/) | Introduction、Organization、Usage | 文档页最后更新 2026-09-30，访问 2026-10-20 | Web Vocabulary 纳入 BSP-RDM 语义和代码表，源码是受治理 ontology；可做词汇映射/术语字典，不是 API | 官方文档页；不代表每个专用模式都有实时数据交换 API |
| F-05 | [UN/CEFACT Transport vocabulary](https://test.uncefact.org/vocabulary/module/transport) | Classes/Properties/Code lists | 网站运输域在线词汇，访问 2026-10-20 | 提供 Booking、Consignment、TransportLeg/Event/Equipment/Movement、carrier、freightForwarder、mode/location 等概念和运输状态代码集 | 词汇站点在 `test.uncefact.org` host；语义参考页面不等于正式消息 profile/供应商实现 |
| F-06 | [UN/CEFACT all classes](https://test.uncefact.org/vocabulary/classes) | Booking、Consignment、ConsignmentItem、Event、Party/PartyRole、Shipment 等定义 | 网站在线词汇，访问 2026-10-20 | 明确 Booking 是运输服务预约，Consignment 是一个运输合同下发/收双方间可识别货物集合，ConsignmentItem 是运单最低层货物项；Event 含时间/实体/通常有地点；Party 与 PartyRole 分离 | 是规范词汇定义，不规定企业内部主键或 DN 关联规则 |
| F-07 | [GS1 EPCIS Standard 2.0](https://ref.gs1.org/standards/epcis/2.0.0/) | §7.4 Event Types、eventTime/recordTime；§8 query | Release 2.0 ratified 2022-06 | Object/Aggregation/Transaction/Transformation/Association 等事件类型；event/record time 可分开；支持事件业务交易和多类检索 | 标准覆盖可追溯事件交换，采用需准确标识和数据采集，非供应商进度产品 |
| F-08 | [GS1 EPCIS/CBV Implementation Guideline 2.0](https://ref.gs1.org/guidelines/epcis-cbv/2.0.0/) | §2（标准适用）、§4.4–4.5（事件选择/建模）、§5.11.3（多式运输例）、§6.1–6.2（查询） | Release 2.0 ratified 2023-03 | 建议按需选择可见事件；事件时间与记录时间不同；示例用 Aggregation 记录货物在卡车、柜、船的物理装载层级；CBV business step 可供事件查询 | 指南仍需实现者定义唯一标识、伙伴映射；过度跟踪会增加采集成本 |
| F-09 | [OTM5 Transport order profile](https://www.opentripmodel.org/docs/profiles/transport_order/) | Overview、Profile structure、example | Version 5.x，在线 profile，访问 2026-10-20 | Transport order 是 shippers 与 carrier 的初始委托，可包括多个 consignments；Consignment 管理实际 goods；可为货物建 load/unload actions 与地点 | 规范profile不是市场供应商功能声明；profile规则需要伙伴双方选定 |
| F-10 | [OTM5 API Specification](https://www.opentripmodel.org/docs/developers/api_specification/) | JSON、Communication protocol、Updating Transport Orders、Actions vs Events | Version 5.x，访问 2026-10-20 | OTM5 使用 JSON/REST；没有固定端点；多 Consignment 可以全量更新或逐项更新；Action 是动态装卸交互，Event 是对实体/实时变化的更新 | 文档明确端点由实施方约定；采用标准不能自动取得供应商数据 |
| F-11 | [OTM Shipping Goods](https://opentripmodel.github.io/documentation/docs/examples/shipping_goods/) | Introduction / Hierarchy examples | OTM 文档页面（当前公开示例），访问 2026-10-20 | 多式运输中从逐件陆运到港口装柜的粒度会变化；可区分 Goods item 与 Transport equipment，并嵌套包装/托盘/柜/船 | 示例解释模型能力，不等于所有整合都需要 EPC 级标识 |
| F-12 | [OTM5 Entities](https://www.opentripmodel.org/docs/next/fundamentals/entities/) | “Connecting all entities” | Next 版文档，页面标“next”/开发文档，访问 2026-10-20 | TransportOrder 组织多个 administrative Consignment；Consignment 含 Goods；Trip 承载 Consignment；Actors 有 shipper/carrier/consignee；Stop/Load/Unload/Handover 等动作和 UpdateEvents/关联事件可表达变更 | `next` 可能代表开发版，落地前需锁定具体 OTM5 release/profile；不作为兼容性承诺 |
| F-13 | [UN/CEFACT Integrated Track and Trace for Multi-Modal Transportation BRS](https://unece.org/sites/default/files/2022-09/BRS-IntegratedTrackandTraceforMulti-ModalTransportationv0.1-Final.pdf) | 尝试打开；PDF正文抓取 403 | 公开页面搜索摘要显示 Final / 2022-09 | 只作为待查候选，不从摘要引用具体主张 | 访问失败，不计入实际已读数 |
| F-14 | [UNECE standards publication entry](https://unece.org/media/trade/uncefact/press/365096) | 尝试打开，工具 internal error | 新闻稿日期 2022-02-11（搜索结果有页面摘要） | 只用于发现多模式标准包条目 | 未成功打开正文，不计入实际已读数 |

## 核验统计

- 实际打开并阅读的一手官方来源：11 个（F-01、02、04–12；F-03 有重定向无正文，不计入实读）。
- 待核实：1 个（F-03，DCSA Information Model 重定向后版本/细节需回门户确认）。
- 访问失败：2 个（F-13、F-14）。
- 来源总登记数：14 项；其中 F-03 为已识别候选但抓取未核实，失败 2 项；其余 11 项已核实。11+1+2=14。
