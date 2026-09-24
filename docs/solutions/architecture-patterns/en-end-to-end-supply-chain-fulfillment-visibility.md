---
okf: v0.1
type: Reference
title: EN 端到端供应链履约可视化蓝图 — 从销售订单到国外仓上架
date: 2026-09-15
last_updated: 2026-09-15
category: architecture-patterns
module: en_api
problem_type: architecture_pattern
component: supply-chain-fulfillment-visibility
severity: high
applies_when:
  - "按一个或多个客户物料号或 EN 物料号查询订单、生产、出库和头程状态"
  - "销售或供应链负责人需要判断货物卡在哪里、何时可交付、下一步由谁处理"
  - "需要把 EN、内部海运登记表和未来物流轨迹统一为端到端履约视图"
tags: [erpnext, sales-order, production-plan, work-order, job-card, delivery-note,
       ocean-freight, overseas-warehouse, supply-chain-visibility, control-tower, exception-management]
related_components: [item_shipment_status, dn_trace_report, warehouse_restock, erpnext-wo-audit]
---

# EN 端到端供应链履约可视化蓝图

## Context

当前 `EN_API/item_shipment_status.py` 已能按客户物料号或 EN 物料号，串联：

`Sales Order → Production Plan → Work Order → Job Card → Delivery Note`

它可靠回答了“有没有销售订单、生产到哪里、工厂有没有销售出库”，但不能回答销售和供应链最终关心的完整问题：

- 工厂已出库的货是待装柜、海运途中、已到港，还是已被国外仓签收？
- 什么时候能在美东、美中或波兰仓上架可售？
- 同一销售订单中的皮壳、内胆、成品或套件是否已经齐套？
- 延误发生在哪一段，由哪个岗位采取什么行动？

现阶段 EN 尚未形成头程运输闭环。业务人员需要用销售订单 `po_no` 到内部登记表查 ZM 海运号及人工更新；查不到时只能用“销售订单下单日期 + 3 个月”粗估国外分公司可用时间。这个估算不能和 ERP 事实、承运人 ETA 或仓库签收混为一谈。

因此，下一步不应只是给现有 Excel 增加更多列，而应先建立一套统一的**供应链履约查询模型**。CLI、Excel、ERPNext Report、Workspace 和未来 Web 驾驶舱都消费同一个模型，避免每接一个数据源就重写一套口径。

## 1. 角色真正需要回答的问题

### 1.1 销售与运营

销售需要的是可以直接回复客户的结论，而不是 ERP 单据列表：

1. 客户订了什么、多少、在哪张 PO/SO、承诺日期是什么？
2. 已经发了多少，剩余多少；是全部出库还是部分出库？
3. 已出库货物现在处于工厂外、海上、港口还是国外仓？
4. 最可信的可交付/可上架日期是什么，依据是什么，可信度多高？
5. 如果会晚，晚在哪一段、预计晚多久、当前由谁跟进？
6. 今天应该怎样回复客户，哪些日期只能表述为估算？

默认输出应先给一句业务结论，例如：

> 40 件已生产 44 件但尚未工厂出库；预计 2026-11-17 可到国外仓属于业务粗估，当前没有 ZM 航次证据，需计划确认出库并由物流补登记。

### 1.2 计划与生产

1. 未出库需求是否已进入生产计划？
2. 是否有对应 `(Sales Order Item × production_item)` 的工单？
3. 计划量、开料量、各工序完成量、工单完成量分别是多少？
4. 当前瓶颈工序是哪一道，最后一次真实扫码发生在何时？
5. 是真的未开工，还是 `Work Order.status` 没有回写？
6. 是否超产、少产、工序断流或使用了一键完工虚拟数据？
7. 订单需要的各配套件是否齐套，缺哪一个组件？

### 1.3 物流与国外仓

1. 哪些工厂出库尚未绑定头程批次/ZM 号？
2. 一个 ZM 批次包含哪些 SO 行、物料和数量？是否存在拼柜、拆单或部分装运？
3. 订舱、装柜、离厂、开船、转运、预计到港、实际到港、清关、提柜分别在何时？
4. ETA 最近是否变化，变化多少天，原因是什么？
5. 国外仓是否预约、签收、清点、完成二次加工并上架？
6. 出库量、装运量、签收量、上架量能否逐段对账？差异在哪里？

### 1.4 供应链负责人

供应链负责人需要“控制塔”视角，而不是只看跟踪位置：

- 每个阶段压了多少订单、数量和金额；
- 哪些订单会影响客户承诺或海外仓断货；
- 哪些异常已有人负责，哪些无人处理；
- 各订单的当前事实、预计结果和证据可信度；
- 生产、工厂待发、待装柜、海运在途、清关、待上架的停留时长；
- 计划达成率、按时足量交付率（OTIF）、ETA 偏差和数据完整率；
- 能否调拨、拆分、加急、替代生产或调整客户承诺。

## 2. 统一履约主键与粒度

### 2.1 最小事实粒度

主记录应以 **Sales Order Item × 需求物料** 为核心，而不是只以 SO 或物料号为核心：

```text
fulfillment_line_id = Sales Order Item.name
需求上下文         = Sales Order.name + customer + po_no + delivery_date
需求物料           = Sales Order Item.item_code
生产执行           = Work Order.sales_order + Work Order.production_item
工厂出库           = Delivery Note Item.so_detail
头程分配           = shipment_allocation(fulfillment_line_id, shipment_batch_id, qty)
国外仓接收         = receipt_allocation(shipment_batch_id, item_code, qty)
```

原因：一张 SO 可以有多种物料；一行可以分多次出库；一个头程批次可以拼多张 SO；同一 SO 行也可能拆到多个航次。如果只在 SO 头部放一个 ZM 号，后续数量无法对账。

### 2.2 三种查询模式

| 模式 | 目的 | 默认范围 |
|------|------|----------|
| **输入物料模式** | 回答“这个 SKU 的货到哪了” | 只查输入的客户码/EN 物料精确命中的订单行 |
| **生产展开模式** | 回答“这个成品或交付形态生产到哪了” | 从成品/BOM/配套规则显式展开皮壳、内胆等生产件 |
| **整单齐套模式** | 回答“这张订单能不能完整交付” | 查相关 SO 的所有有效交付行和必需组件，按最慢项判定 |

查询时必须显示范围，禁止静默自动扩大：

```text
查询范围: 输入物料 2 个 → 命中订单行 7 行 → 生产展开 11 个物料 → 头程分配 3 个批次
未匹配: 1 个客户码（未在 Item Customer Detail / SO 行命中）
```

多个输入物料应分别保留匹配结果和未匹配原因，不能先合成一个集合后丢失输入来源。

### 2.3 客户码与 EN 物料解析

解析结果不能只返回一个 `item_code`，而应返回候选及关系：

```text
input_code
input_type: customer_code | en_item_code
registered_finished_items[]   # 客户码登记在 KS 成品上的候选
ordered_items[]               # SO 行实际交付物料，如 PK#
production_items[]            # 可选展开出的 PK#/ND#/成品
relation: exact | customer_registration | supporting_item | bom_component
confidence
```

EN `item_code` 必须大小写不敏感的精确匹配；只有客户物料号允许 `like`/子串搜索。成品 `KS` 不能因为它是 `PK#KS...` 的子串而误命中皮壳。

## 3. 端到端阶段状态机

统一状态不是照搬任一系统的 `status`，而是根据数量和事件证据推导。建议保留“大阶段 + 子状态”：

| 阶段 | 子状态示例 | 进入证据 | 完成证据 |
|------|------------|----------|----------|
| 0 销售需求 | 草稿、已确认、行政关闭、已改单、已取消 | SO 行有效 | 需求取消或全部履约 |
| 1 待计划 | 未排产、部分排产 | 有效未发量 > 0 | PP 覆盖需求量 |
| 2 生产中 | 未开工、部分工序完成、待质检、待入库、生产完成 | WO/Job Card | 可信完成量达到计划/需求量 |
| 3 工厂待出库 | 待拣货、DN 草稿、部分出库 | 可发数量 > 0 | DN 已提交数量完成 |
| 4 待头程 | 待订舱、待绑定 ZM、待装柜、已装柜待开船 | 工厂已出库或备货确认 | 已绑定批次且实际开船 |
| 5 头程在途 | 已开船、转运中、ETA 变更、延误 | 实际离港/开船事件 | 实际到港 |
| 6 到港清关 | 已到港、清关中、已放行、待提柜 | 实际到港 | 清关放行并提柜 |
| 7 国外仓收货 | 待预约、运输至仓、部分签收、差异待查 | 提柜/末端转运 | 仓库签收并完成数量核对 |
| 8 加工与上架 | 待填充、待包装、部分上架、可售 | 仓库收货 | 上架/可售库存事件 |
| 9 下游履约 | 海外仓待发、尾程在途、已交付 | 海外订单/调拨需求 | 最终交付 |

当前 V1 只应把阶段 0–3 标为“EN 事实覆盖”；阶段 4–8 在接入登记表前标为“外部数据缺失/人工核实”，不能用三个月估算冒充阶段事件。

### 3.1 数量必须分层，而不是只有一个状态

每个订单行至少维护以下数量：

```text
ordered_qty
cancelled_or_amended_qty
valid_demand_qty
planned_qty
work_order_qty
credible_produced_qty
factory_shipped_qty
head_leg_allocated_qty
loaded_qty
departed_qty
arrived_port_qty
customs_released_qty
overseas_received_qty
shelved_qty
```

核心对账：

```text
有效需求 = 已工厂出库 + 工厂未出库
工厂出库 = 未绑定头程 + 已绑定头程
已绑定头程 = 待开船 + 在途 + 已到港/清关 + 已签收
国外仓签收 = 已上架 + 待加工/待上架 + 收货差异
```

允许部分数量处于不同阶段。主状态取“最大风险的未履约数量所在阶段”，同时展示数量分布，不能把 20 件已发、20 件未发压成一个模糊的 `Partly Delivered`。

## 4. 字段分层：事实、推导、估算和人工判断

每个展示值必须带来源类别，建议统一结构：

```json
{
  "value": "2026-11-17",
  "kind": "estimate",
  "source": "business_rule",
  "source_record": "order_date + 3 calendar months",
  "observed_at": "2026-09-15T10:00:00+08:00",
  "confidence": "low"
}
```

| 类别 | 含义 | 示例 | 展示要求 |
|------|------|------|----------|
| **事实 fact** | 来自已提交单据或可验证事件 | SO 日期、DN 数量、实际开船、仓库签收 | 显示来源单号和事件时间 |
| **推导 derived** | 由事实按稳定规则计算 | 未发量、工序瓶颈、阶段停留天数 | 显示公式/口径版本 |
| **估算 estimate** | 对未来日期或状态的预测 | 下单 + 3 月、货代 ETA、预测上架日 | 显示估算来源和置信度 |
| **人工判断 assertion** | 人工确认但暂无系统证据 | “此 Closed 单实际作废” | 显示确认人角色、时间和备注 |

日期优先级建议：

1. 国外仓实际上架时间；
2. 国外仓确认的预约/预计上架时间；
3. 实际到港 + 清关/入仓经验时长；
4. 货代或承运人 ETA + 入仓经验时长；
5. 已开船后的航线基线 ETA；
6. 当前临时口径“下单日期 + 3 个月”。

系统应同时保留原始日期，不要让新 ETA 覆盖旧 ETA，否则无法分析延误变化。

## 5. 数据来源矩阵

| 数据域 | 当前来源 | 已有关键字段/对象 | 覆盖度 | 下一步 |
|--------|----------|-------------------|--------|--------|
| 销售需求 | EN ERPNext | SO、SO Item、`transaction_date`、`delivery_date`、`po_no`、qty | 高；`po_no` 已随 V1 输出，但**填写质量是瓶颈**（见 5.1） | V1 起输出并统计填写率 |
| 生产计划 | EN ERPNext | Production Plan Item、`sales_order_item`、计划/待产量 | 高 | 保留逐行连接键 |
| 生产执行 | EN ERPNext | WO、operations、Job Card | 中高；状态与虚拟报工需辨真 | 沿用工序卡可信度规则 |
| 工厂出库 | EN ERPNext | DN Item、`so_detail`、posting_date、qty | 高 | 支持部分出库与退货净额 |
| 待装柜/海运 | **钉钉表**（2026年下单表 / 发货信息总表） | `2026年度订单明细`(SO编号、工厂四件套)、`物流信息表`(通途采购单号→`ZMT…`)、`物流跟踪Tracking`(批次号→离港/到港/入库) | **可读**（`dingtalk/dingtalk_sheet` 已打通） | V2 按 SO 编号精确匹配 + 未匹配报告 |
| 船期轨迹 | 货代/船司/AIS/港口 | ETD/ATD/ETA/ATA、转运、异常 | 当前无 | V3 接 API/EDI 或结构化人工事件 |
| 清关提柜 | 内部/货代 | 放行、提柜时间、异常原因 | 当前无 | V3 纳入事件模型 |
| 国外仓收货/上架 | 国外仓/WMS/人工登记 | receipt、差异、加工、shelved | 当前无统一闭环 | V3/V4 建接收与上架事件 |
| 海外仓成本/库存影子 | 赛狐/通途/备货单 | 仓库映射、头程成本、海外仓备货 | 不能作为真实履约事实 | 仅辅助，不反推已签收/已上架 |
| 尾程交付 | parcel_track/FedEx/GLS 等 | trackNo、首次扫描、交付、迟发/卡件 | 已有独立能力 | V4 在上架后的下游阶段接入 |

特别注意：当前赛狐库存使用安全冗余且不追求与通途数量一致，不能把赛狐库存或海外仓备货单反推为“某批头程已签收上架”。

### 5.1 头程的真实入口：EN 销售订单编号 × 钉钉表（不是 `po_no`）

**2026-09-15 更正。** 本蓝图初稿把 EN 的 `po_no` 当作「查头程的候选键」，这是错的：

- 经计划物流同事核实，`po_no` / 行级 `purchase_order` 是**离职同事自编的内部流转号**，
  **不是客户给的采购订单号**。当年用途是「一张 SO 对应多个客户 PO 时区分下单日期 / 仓库」。
- 现在 SO 自身已有下单日期和仓库，所以该字段意义有限、**之后可能弃用**。
  报表保留但标注为「内部流转号(非客户PO,待废弃)」，不得对外称客户 PO，不得用作头程键。

**真实头程数据在两张钉钉表里**（人工维护，读取方式见 `dingtalk/dingtalk_sheet/`）：

| 文档 | 关键 sheet | 作用 |
|------|-----------|------|
| 2026年下单表 | `2026年度订单明细` | 一行 = (EN销售订单编号 × 通途SKU)；含**工厂四件套** |
| 2026年下单表 | `物流信息表` | 通途采购单号 → `ZMT…` 物流号（即业务说的「ZM 海运号」） |
| 发货信息总表 | `物流跟踪Tracking` | **批次号** → 离港 / 到港 / 入库 / 时效 |
| 发货信息总表 | 美东·美中·欧洲·FBA 下单表与发货明细 | 批次 → 箱号级明细；美东明细含「美国签收日期/到货数量」 |

**join key = `EN销售订单编号` == `Sales Order.name`** —— 正如计划同事所说
「现在 SO 反正有下单日期和仓库，之后有个表格匹配就行了」。

**「工厂四件套」是判断卡在哪一步的直接证据**：
`工厂确认交期` → `包装完成日期` → `实际包装完成量` → `物流发票编号`，逐级为空 = 尚未进入头程。
实测 `SO-26-00101` 本物料那行四件套全空（目的仓库 美中仓、下单量 40），
同表另一行备注写着 `SO-26-00099作废`。

**对 V2 的影响**：数据源从「未知结构的内部海运登记表」变成了**已知结构、且已能机器读取**的
钉钉表，V2 的可行性大幅提高；前置工作不再是「补 `po_no`」，而是：

```text
V2 步骤（修订）:
  V2.0  已打通: dingtalk/dingtalk_sheet 只读客户端 + 结构文档
  V2.1  EN SO 编号 ↔ 2026年度订单明细 精确匹配 + 未匹配报告（含一单多行聚合）
  V2.2  接「工厂四件套」→ 阶段 4「待头程」判定
  V2.3  接 物流跟踪Tracking 批次 → 阶段 5–8（离港/到港/入库）
  V2.4  头程批次与 SO 行多对多分摊（一 PO 多 ZM、一 ZM 多 PO）
```

仍要保留的匹配质量问题：`SO-26-00099` 这类作废单以**备注文字**形式存在，
不是状态字段；批次号在明细表里只有首行有值（合并单元格），必须向下填充。

## 6. 头程运输数据模型

### 6.1 不要把 ZM 号直接塞进 SO 头部

建议未来在 EN 或独立服务建立三个核心对象：

#### `First Leg Shipment`（头程批次）

```text
name / external_shipment_no / zm_no
origin / destination_warehouse
forwarder / carrier / mode
booking_no / bill_of_lading / container_nos[]
planned_etd / actual_departure
current_eta / actual_arrival
customs_release_at / pickup_at
status / last_event_at / data_source
```

#### `First Leg Allocation`（需求与批次分摊）

```text
shipment_batch
sales_order
sales_order_item
item_code
factory_delivery_note
factory_delivery_note_item
allocated_qty / loaded_qty / received_qty / shelved_qty
```

#### `Supply Chain Event`（不可变事件）

```text
event_id / shipment_batch / event_type
event_time / location / quantity
source_system / source_record / captured_at
is_estimated / confidence / raw_status / note
```

事件至少覆盖：`BOOKED`、`LOADED`、`GATE_OUT`、`DEPARTED`、`TRANSSHIPMENT`、`ETA_UPDATED`、`ARRIVED_PORT`、`CUSTOMS_RELEASED`、`PICKED_UP`、`WAREHOUSE_RECEIVED`、`SHELVED`。

这种事件模型借鉴了 GS1 EPCIS 的“什么、何时、何地、为何/业务步骤”思想，但不要求第一期完整实施 EPCIS 或 GS1 编码。

### 6.2 钉钉头程表的 V2 接入原则

数据源结构已确认（见 5.1），适配器按 **EN 销售订单编号** 查：

```python
class HeadLegSource:
    def lookup_by_sales_order(self, so_names: list[str]) -> HeadLegLookupResult: ...
```

返回必须包含：

- 输入 SO 数；
- 精确匹配、重复匹配、未匹配数量；
- 原始 sheet 名 + 行号；
- 「工厂四件套」（工厂确认交期 / 包装完成日期 / 实际包装完成量 / 物流发票编号）；
- 目的仓库、下单量、需求交货日期；
- 关联批次号 → 离港 / 到港 / 入库 / 时效；
- 数量是否可分配到 SO 行；
- 数据新鲜度和冲突。

**匹配注意**：`2026年度订单明细` 一行 = (SO × 通途SKU)，一张 SO 会有几十行，
按 SO 查必须聚合；批次号只在批次首行有值（合并单元格），要向下填充；
作废信息以**备注文字**出现（如 `SO-26-00099作废`），不是状态字段。
第一期只允许精确匹配 SO 编号；模糊候选必须人工确认，不能自动归属。

## 7. 工序与齐套口径

### 7.1 单工单进度

继续沿用已验证规则：

- 0 Job Card 且所有工序 Pending 才算真正未开工；
- `Work Order.status`/`produced_qty` 只能作为头部状态，不能覆盖 Job Card 事实；
- 完成数量按工序分别算，不能跨工序求和；
- “做了多少件”优先取第一道工序的 `total_completed_qty`，为空再用 `for_quantity`；
- 一键完工数据应带可信度标记，必要时结合员工、Version、Stock Entry 和开料量审计。

### 7.2 整单齐套

齐套不是“所有工单都 Completed”，而是每个必需需求项的**可信可用量**都覆盖待发量：

```text
line_ready_qty = min(
  可信生产/库存可用量,
  包装与加工能力覆盖量,
  其他必需配套件可用量
)
order_kit_ready_qty = min(all required line/component ready quantities)
```

产品展开必须来自 BOM、Product Bundle 或已确认的配套关系。不能仅靠 `KS`、`PK#`、`ND#` 字符串前缀猜整套关系；前缀只用于分类和候选提示。

返工分支 Pending 不应在正常质检已通过时让整体进度永久停在 7/9。路由需区分：

- 必经工序；
- 条件分支/返工工序；
- 已触发的返工；
- 未触发且不阻塞完工的返工。

## 8. 异常、风险与下一行动

每条异常采用统一结构：

```text
severity / code / affected_qty
fact / impact / evidence
owner_role / recommended_action / due_at
first_seen_at / last_seen_at / acknowledged_at / resolved_at
```

### 8.1 V1 必做规则

| 异常 | 条件 | 责任角色 | 建议行动 |
|------|------|----------|----------|
| Closed 仍未发 | SO Closed 且有效未发量 > 0 | 计划 | 确认剩余量作废、重复或仍需交付 |
| 已改单未排除 | Cancelled 有 amended 后继但仍计需求 | 销售/系统 | 关联后继单并排除原单 |
| 无生产计划 | 未发且无 PP | 计划 | 排产或确认库存交付 |
| 有计划无工单 | PP 已有但未建 WO，超过阈值 | 计划 | 下达工单 |
| 真未开工 | 0 Job Card + 工序全 Pending | 生产 | 确认开工日期 |
| 工单头部滞后 | 有完成 Job Card 但头部未开始/产量落后 | 生产/系统 | 修正回写或按工序卡展示 |
| 工序停滞 | 在产且最后真实工序事件超过阈值 | 生产 | 查瓶颈、缺料或异常 |
| 超产/少产 | 可信完成量偏离 WO/需求量 | 计划/生产 | 确认补产或余量归属 |
| DN 草稿停留 | 有草稿出库超过阈值 | 仓库 | 审核、提交或取消 |
| 工厂出库未闭环 | DN 已提交但无头程事实来源 | 物流 | 用 PO 查 ZM/批次并补登记 |

### 8.2 V2/V3 头程规则

| 异常 | 条件 | 建议行动 |
|------|------|----------|
| 未绑定头程 | 工厂出库后 N 天仍无 shipment allocation | 物流补 ZM/批次 |
| 装运数量差异 | DN 出库量 ≠ 批次分配/装柜量 | 核实留仓、拆批或漏登记 |
| 未开船 | 计划 ETD 已过且无 ATD | 催货代并更新原因 |
| ETA 大幅后移 | 新 ETA 比基线晚超过阈值 | 评估断货/客户承诺，制定调拨方案 |
| 轨迹陈旧 | 在途且最后事件超过阈值 | 查船司/货代/港口第二来源 |
| 到港未放行 | ATA 后清关停留超阈值 | 处理单证/查验/税费 |
| 放行未入仓 | 放行或提柜后未签收 | 催派送与仓库预约 |
| 签收差异 | received_qty ≠ expected_qty | 建收货差异单并定位短少/破损 |
| 签收未上架 | 收货后加工/上架停留超阈值 | 国外仓排加工和上架 |

告警必须基于“异常管理”而不是把所有状态变化都推送。供应链可视化的价值在于说明风险和可执行动作，而不是制造更多通知噪音。

## 9. 统一查询结果

### 9.1 顶部业务摘要

```text
查询: 客户码 A + EN 物料 B（输入物料模式）
需求: 7 张 SO / 420 件；有效 400；已改单 20
阶段分布: 生产中 80 | 工厂待出库 40 | 待头程 60 | 海运在途 120 | 已到仓上架 100
风险: 高 2 / 中 4；最早客户交期 2026-09-25
预计可用: 事实 100 | 货代 ETA 推导 120 | 三个月粗估 180
下一行动: 计划 2 项、工厂 1 项、物流 3 项、国外仓 1 项
```

### 9.2 标准结果分区

1. **订单总览**：客户 PO、SO、订单行、数量、交期、状态、改单链；
2. **阶段数量分布**：每行有多少在计划、生产、待发、在途、清关、待上架；
3. **生产进度**：PP、WO、工序瓶颈、各工序完成量和时间、可信度；
4. **工厂出库**：DN、部分出库、草稿、退货和数量差异；
5. **头程与国外仓**：ZM/批次、装柜、ETD/ATD/ETA/ATA、清关、签收、上架；
6. **时间线**：按事件时间排列事实和 ETA 修订；
7. **风险与下一行动**：按严重度、影响数量和承诺日期排序；
8. **证据与数据缺口**：每个结论对应来源单据，单列未匹配、陈旧和估算数据。

### 9.3 Excel 建议

V1 可从现有 3 Sheet 演进为：

1. `履约总览`
2. `订单行与阶段数量`
3. `生产计划与工单`
4. `工序卡明细`
5. `工厂出库明细`
6. `头程与国外仓`（V1 先留外部匹配结果）
7. `事件时间线`
8. `异常与下一行动`
9. `未匹配与数据质量`

不要在一个 Sheet 横向堆到几十个重复单号列；总览用于决策，明细用于取证和对账。

## 10. 技术架构

```text
                    ┌─ ERPNextSource (SO/PP/WO/JC/DN/Item/BOM)
QueryRequest ──────┼─ HeadLegSheetSource (V2, po_no → ZM/事件)
                    ├─ Carrier/ForwarderSource (V3)
                    ├─ OverseasWarehouseSource (V3)
                    └─ TailTrackingSource (V4)
                              │
                              ▼
                 Normalized Facts + Immutable Events
                              │
                  Quantity Reconciliation Engine
                              │
            Stage Resolver + ETA Resolver + Risk Rules
                              │
                 FulfillmentQueryResult (统一模型)
                    ┌─────────┼──────────┐
                   CLI       Excel    ERPNext/Web/MCP
```

核心层应是无 UI 的 Python 服务/领域模块；现有 `item_shipment_status.py` 可先作为数据探针和验收基线，但不适合继续承载全部业务。重构时优先抽出：

- ERPNext REST 客户端与稳定分页；
- 输入码解析；
- 订单行事实获取；
- 生产进度聚合；
- 数量对账；
- 阶段判定；
- 风险规则；
- 输出适配器。

对外接口建议：

```python
query_fulfillment(
    codes=[...],
    code_type="auto",
    scope="input_items",  # input_items | production_expanded | full_order_kit
    destination=None,
    as_of=None,
) -> FulfillmentQueryResult
```

第一期不需要引入消息队列、数字孪生或购买企业控制塔平台。先把事件、数量和证据模型做对，再逐步增加自动同步和主动告警。

## 11. KPI 与数据质量

### 11.1 运营 KPI

- 按时足量交付率（OTIF）；
- 客户交期风险数量；
- 生产计划覆盖率；
- 工序停滞时长；
- 工厂出库至实际开船时长；
- 海运 ATD→ATA 时长与 ETA 偏差；
- 到港→清关放行、放行→仓库签收、签收→上架时长；
- 部分出库、部分签收和收货差异率。

### 11.2 数据质量 KPI

- 有效 SO 中 `po_no` 填写率；
- DN 到 SO 行连接率；
- 工厂出库到头程批次分配率；
- 在途批次最近事件新鲜度；
- 批次数量对账率；
- 国外仓签收/上架回写率；
- 估算日期占比及各估算层级分布；
- 无责任人异常数量。

## 12. 分阶段实施

### V1 — EN 内履约查询统一化

目标：把“单物料排查脚本”升级为可查询多个物料的事实层和决策报表。

- 支持多个客户码/EN 物料，逐输入保留命中与未命中；
- 输出 SO `po_no`（**实为内部流转号，非客户 PO**，见 5.1）—— 已实现并改标注为待废弃；
  改单链与部分出库已有，退货净额待做；
- 实现输入物料模式，预留生产展开/整单齐套接口但不擅自展开；
- 输出事实/推导/估算/人工判断类型；
- 统一阶段 0–3、异常、责任角色和下一行动；
- 继续把“下单 + 3 个月”标为低置信度业务估算；
- 建立 JSON 中间结果，使 Excel 不再是唯一接口。

验收：每一步输出入 N、出 M、未匹配及原因；SO、PP、WO、JC、DN 数量可追溯；现有 fixture 和单测继续通过。

### V2 — 只读接入钉钉头程表

目标：填补“工厂出库以后去了哪里”的最大盲区。**数据源已确认并可读**（见 5.1）。

- **V2.0 已完成**：`dingtalk/dingtalk_sheet/` 只读客户端（列 sheet / 读区域）+ 结构文档；
  读通「2026年下单表」15 张 sheet 与「发货信息总表」9 张 sheet；
- 按 **EN 销售订单编号** 精确匹配 `2026年度订单明细`，输出重复/未匹配/冲突
  （注意该表一行 = SO × 通途SKU，需按 SO 聚合）；
- 接「工厂四件套」判定阶段 4「待头程」；
- 按 **批次号** 接 `物流跟踪Tracking` 的离港/到港/入库，落阶段 5–8；
- 建立头程批次与 SO 行分摊，支持一 PO 多 ZM、一 ZM 多 PO、拆批与拼柜；
- 将登记表状态规范化为事件，不覆盖原始值；
- 用实际离港/到港/入库替代粗估，但保留来源与历史修订。
- 建立头程批次与 SO 行分摊，支持一 PO 多 ZM、一 ZM 多 PO、拆批与拼柜；
- 将登记表状态规范化为事件，不覆盖原始值；
- 用货代 ETA 替代部分三个月粗估，但保留来源与历史修订。

验收：工厂出库量 = 未绑定量 + 各批次分配量；无法对账的数量全部进入问题报告。

### V3 — EN 头程与国外仓闭环

目标：从人工表升级为可维护的业务对象和事件流。

- 在 EN 自定义 App 或独立服务建立 Shipment、Allocation、Event；
- 接货代/船司/API/EDI/AIS，人工更新作为兜底；
- 建清关、提柜、仓库签收、差异和上架事件；
- 国外仓按收货批次和物料回写数量；
- 建 ETA 优先级、路线基线和异常升级规则。

写操作必须有权限、幂等键、审计和人工确认，不能由查询脚本直接修改生产单据。

### V4 — 控制塔与主动协同

目标：为销售、计划、物流和供应链负责人提供不同视角。

- ERPNext Query/Script Report 或独立 Web 驾驶舱；
- 角色化首页、保存查询、事件时间线和数量瀑布；
- 钉钉/邮件只推需要行动的异常；
- 异常认领、备注、截止时间、关闭原因；
- 接海外库存与尾程跟踪，形成上架后履约链；
- 基于实际历史重新估计生产、海运和上架时长。

## 13. 当前明确边界

1. EN 的 `Closed`、`Work Order.status`、`produced_qty` 不能直接当履约事实。
2. 工序完成量不能跨工序求和；虚拟报工与真实扫码需要区分。
3. 赛狐安全冗余库存和海外仓备货单不是国外仓真实签收证据。
4. EN 的 `po_no` **不是客户 PO 号**（离职同事自编的内部流转号，待废弃），
   不得对外称客户 PO，也不得用作头程键；头程一律走 **EN 销售订单编号 × 钉钉表**（见 5.1）。
5. “下单 + 3 个月”只是最低层级粗估；有 DN、ATD、ETA、ATA 或签收事实后应逐级替代。
   钉钉表已能提供离港/到港/入库与「工厂四件套」，应优先于粗估。
6. 单物料查询和整单齐套是不同问题；默认不自动扩到 SO 全部 98 行或数百张无关工单。
7. 头程批次与 SO 行必须多对多建模，不能在 SO 头部只存一个字符串。
8. 任何自动化都必须保留原始来源、事件时间、抓取时间和计算口径，支持历史回放。

## Research Notes

本蓝图参考当前仓库的真实业务和脚本，并用行业资料校正了三个方向：

- 供应链可视化要从“位置查询”升级到“风险、影响和下一行动”；
- 头程数据通常来自货代/船司 API、AIS、港口和人工伙伴更新的组合，单一来源不足；
- 事件数据宜表达 what/when/where/business step，先做轻量事件模型，不必第一期完整实施企业级 EPCIS 或控制塔。

外部资料：

- [DCSA — Track & Trace standards](https://dcsa.org/standards/track-and-trace)
- [GS1 — EPCIS and CBV](https://www.gs1.org/standards/epcis)
- [Infor — Supply chain transformation trends for 2026](https://www.infor.com/blog/supply-chain-transformation-trends-2026)
- [Slimstock — Supply chain trends 2026](https://www.slimstock.com/blog/supply-chain-trends-2026)

## Related

- `EN_API/item_shipment_status.py` — 当前阶段 0–3 的单物料查询实现
- `EN_API/AGENT_HANDOFF_物料发货状态.md` — ERPNext 查询链和限制
- `dingtalk/dingtalk_sheet/AGENT_HANDOFF.md` — 头程数据源只读客户端（阶段 4–8 的数据入口）
- `dingtalk/dingtalk_sheet/docs/reference/dingtalk-sheet-api.md` — 两张供应链钉钉表的结构与 API
- `docs/solutions/workflow-issues/erpnext-so-closed-unshipped-and-unstarted-work-orders.md` — 已验证的订单/工单口径
- `erpnext/docs/work-order-investigation-methodology.md` — 真实生产进度辨别方法
- `docs/company-context.md` — 绍兴工厂、海外分公司和三系统 SKU 背景
- `warehouse_restock/AGENT_HANDOFF.md` — 海外仓备货单和头程成本；注意它不是运输轨迹
- `docs/solutions/architecture-patterns/sellfox-shipping-research-and-architecture.md` — 上架后的尾程打单架构
