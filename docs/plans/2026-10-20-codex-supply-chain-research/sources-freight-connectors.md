---
okf: v0.1
type: Reference
title: 头程连接器调研来源与核验边界
timestamp: 2026-10-20
tags: [freight, ocean, sources, API, EDI]
---

# 来源与核验记录

访问日：2026-10-20。下列 12 个官方来源 URL 均实际尝试打开：8 个可读取正文、2 个仅有搜索摘要而原文待核、1 个直接访问失败、1 个登录受限。搜索结果摘要不当作正文核实。发布日期未显示时明确记为未知/未标，不把文档访问日当发布日期。搜索智美通未找到可归属唯一主体的官方开发者页，这不是已确认 API 不存在的证据。

| ID | Claim / 来源 | URL 与定位 | 页面版本/发布日期 | 核验状态与限制 |
|---|---|---|---|---|
| R1 | DCSA Track & Trace 实施方式 | [DCSA Implementing Track & Trace](https://reference.dcsa.org/content/standards/guidelines/implementation-guides/implementing-track-and-trace)，段落 4–26 | 标准版本 2.2；访问 2026-10-20，页面未见发布日期 | 正文已打开。明确 T&T 是采用方实施的 API 标准，事件发布方需实现 OpenAPI，消费者实现 client；提供 conformance sandbox 思路。不是“DCSA 提供可直接查询任意柜的免费 API”。页面文件 Apache-2.0 声明不代表 carrier 数据许可。 |
| R2 | DCSA Subscription Callback | [DCSA 2.2 发布公告](https://dcsa.org/newsroom/dcsa-releases-track-trace-interface-standard-version-2-2)，第 8–14 行 | 2021-10-26；Interface Standard 2.2 | 正文已打开。提到 shippers/consignees 可订阅 carrier shipment events、subscription ID / notification signature headers、文档事件类别。具体当前 OpenAPI 字段/事件表需看版本化规范及发布方实现。 |
| R3 | 船司多承运人可视化/事件 API 与 entitlement（待核线索） | [Maersk Visibility Studio API](https://developer.maersk.com/api-catalogue/maersk-visibility-studio)，API overview / onboarding 与 Webhook 段 | 搜索索引称 API v2.0.3 / OpenAPI 3.1.1；direct page release notes 搜索结果有 2.0.0 / 2025-12-01 条目；访问 2026-10-20 | 直接打开返回空正文；仅搜索索引有摘要。正文与实际授权待核，不作为字段或本账号 entitlement 的证据。 |
| R4 | Maersk Web Services REST/SOAP tracking 与 webhook | [Maersk Web Services developer guide](https://myfreight.maersk.io/developer/)，Tracking API / Webhook Events | 页面当前版未显示；访问 2026-10-20 | 官方门户说明有 SOAP/REST tracking、shipment-based JSON webhook，并须联络销售代表获取集成详情；实际单号范围及具体字段未在首页确认。接口存在不等于账户开通。 |
| R5 | project44 海运批次创建与追踪 | [Ocean Unified Arrangements](https://developers.project44.com/guides/shippers/visibility/ocean/ocean-unified-arrangements)，L66–83、POST/PUT schema | 文档最近更新时间页面称 5 days ago；访问 2026-10-20 | 正文已打开。FCL/LCL/RoRo，统一 shipment `id`/`identifiers`/`events`，支持 `plan.scope`/`arrangements` 与 carrier/forwarder role。要求 client ID/secret、tenant permission、地区 endpoint；forwarder-managed 需额外权限。异步处理，不承诺新建即有追踪。 |
| R6 | SeaRates Container Tracking API | [官方 Container Tracking API v3](https://docs.searates.com/reference/tracking/general-information)，GET `/tracking` | API version 3；访问 2026-10-20，页面未显示发布日期 | 直接打开返回 502；搜索摘要不作为正文核实。SLA、覆盖、授权与价格未知。 |
| R7 | GoFreight forwarder API 与 Webhook（待核线索） | [GoFreight API Documentation](https://api.gofreight.com/)，Webhook、Visibility schema sections | 搜索索引显示文档标 API 1.0.0；访问 2026-10-20，正文未读，未显示可核发布日期 | 直接打开返回空正文；搜索索引摘要称有 API/Webhook，属于待核线索，不核实字段、授权、限额或事件。需获取账号级可读文档后再评估。 |
| R8 | CargoWise Carrier Connectivity | [CargoWise 官方 Carrier Connectivity](https://www.cargowise.com/solutions/cargowise-carrier/carrier-connectivity/)，“Global connectivity for ocean carriers” | 现行产品页；访问 2026-10-20，未标具体版本/发布日期 | 正文已打开。公开描述船司可通过 API、EDI schedules 或 spreadsheet 提供日程，booking、VGM、tracking event updates 可互联。它是平台能力介绍，不是开放的客户级 eAdaptor schema/API key/tenant endpoint。 |
| R9 | OpenBoxes API/WMS 接入边界 | [OpenBoxes Lift Custom Integrations](https://openboxes.cloud/docs/integrations/custom-integrations)，L59–103、146–153 | Hosted Lift 文档，访问 2026-10-20，未标 release | 正文已打开。REST `/api/v1`、X-API-Key、stock movements/purchase orders/putaways；列 `shipment.created`/`shipment.shipped` 等 webhook。库存变化需轮询；这是 OpenBoxes hosted API 行为，不等于所有自托管开源版本 webhook 一样。开源本体许可可另查其仓库。 |
| R10 | ERPNext Delivery Note 内部库存/出库语义 | [ERPNext 官方 Delivery Note 文档](https://docs.frappe.io/erpnext/delivery-note)，L2146–2190、2226–2239、2330–2346 | 当前文档；last updated 页面称 8 months ago；访问 2026-10-20 | 正文已打开。DN 代表公司仓库向客户发货，基于 SO、可分批创建 DN，提交后更新库存；支持 Product Bundle packing list。未提供海运多 leg shipment/event 追踪模型。现用自定义字段/生产版本须另外核。 |
| R11 | 开源 AIS 采集/查询组件 | [DMA AIS AisTrack GitHub](https://github.com/dma-ais/AisTrack)，README 与 LICENSE | master；Apache-2.0，页面未标 release；访问 2026-10-20 | 正文已打开。可接多来源 AIS streams，提供 Java/REST JSON vessel-track 查询；源码是组件，不提供 AIS 数据权利、柜/提单/EN 关联或货运事件。运行时数据授权独立检查。 |
| R12 | FourKites developer portal 可公开性 | [FourKites API Developer Portal](https://developer.fourkites.com/) | 访问 2026-10-20 | 页面仅显示登录/注册壳，无法读接口对象、字段、授权和更新时间；计为访问受限，不用 search snippet 或第三方资料推断 schema。需现有客户/供应商提供账户级文档。 |

## 互斥计数

- 来源 URL 总数：**12**。
- 正文可核实：**8**（R1、R2、R4、R5、R8、R9、R10、R11）。
- 仅摘要/正文待核：**2**（R3、R7；直接打开为空，摘要只作线索）。
- 访问失败：**1**（R6 SeaRates 直接打开 502；搜索摘要不作正文核实）。
- 访问受限：**1**（R12 FourKites 登录墙）。互斥校验：**8 + 2 + 1 + 1 = 12**。
- “智美通”没有可确认主体与官方开发文档 URL；这是候选身份待辨认，不在 URL 数内，不断言其不存在接口。

## 当前未能核实

实际智美通法人/产品和其客户账户是否有 API/EDI；PJ/Jack 接触的各头程供应商名单与每家使用的 TMS；能否按 MBL/HBL/booking/container 查询并返回稳定事件 ID；是否含供应商工厂提货、起运港进场、ETD/ATD、中转、ETA/ATA、清关、拆柜、末端交付和仓库上架；更新时间和修订历史；Webhook 重试/签名；API rate limit 和历史回溯窗口；商业授权/订阅、数据留存及导出条款。这些都须由供应商或客户管理员给出可审查材料后验证。

## 本地上下文来源（不计入 12 个外部 URL）

| ID | Claim / 定位 | 本地路径与位置 | 核验边界 |
|---|---|---|---|
| L1 | 头程关联需用 EN Sales Order.name 查登记表；po_no 是内部流转号 | `EN_API/AGENT_HANDOFF_物料发货状态.md`，§关键设计第 8 条；访问 2026-10-20 | 本轮只读文档，没有连 EN 验证生产字段；po_no 不应默认为唯一头程键，供应商映射需样例验证。 |
| L2 | 工厂出库按 DN Item / `so_detail` 追溯 SO 行，头程分配多对多并保存事件与 ETA 修订 | `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md`，行 99、§5–6；访问 2026-10-20 | 本地蓝图不是已部署集成或供应商接口证据；仅复用数据粒度与外部 ID 语义。 |

本次没有使用真实账号、调用 API、查询真实货件或处理凭证；没有安装 AisTrack、OpenBoxes 或 ERPNext app；没有把末端快递 tracking 当作海运来源。
