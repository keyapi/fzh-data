---
okf: v0.1
type: Reference
title: 供应链整合 — 端到端事实契约草案
description: 生产数量四分法、实体/键/粒度、数量守恒等式、批次关联、SKU/单位/配套映射与缺口
date: 2026-10-20
status: draft
tags: [supply-chain, fact-contract, quantity, batch, sku-mapping]
---

# 08 — 端到端事实契约草案

> **G0 基线**：本文件已随标签 `supply-chain-g0-baseline-20261020` 冻结；
> 版本清单与 G1 进入条件见 [11-common-baseline.md](11-common-baseline.md)。
> 变更必须新增版本并写明原因/影响/验证，不得静默修改。

> 回应 Codex 评审第 1、4 项。目标：把「需求 → 生产 → 出库 → 采购在途 → 头程 → 实收」
> 的实体、键、数量与守恒关系写成可实现的契约，**不重写已有事实层**（优先扩展 #291/#294）。
> 本文是草案；标注「待验证」的条目必须在 EN 测试环境或只读抽样中确认。

## 1. 生产数量四分法（V1 规范）

**四个量必须分开，禁止互相替代：**

| # | 概念 | 定义 | 性质 | 用途 |
|---|---|---|---|---|
| P1 | **首道报工量** | 首个 required 工序各 Job Card `total_completed_qty` 之和；**不跨工序求和** | 进度事实（派生） | 生产进度、WIP、异常 |
| P2 | **末道报工量** | 最大 sequence 的 required 工序报工；批量卡与菲号卡取 `max(batch, per_tn)` | 接近产出（派生/估计） | **仅用于估算待入库** |
| P3 | **已提交入库量** | 已提交 Manufacture Stock Entry 的成品行数量（`work_order` + `is_finished_item=1`） | 产出事实 | 成品库存增加、齐套 |
| P4 | **已出库量** | 已提交 Delivery Note 的签名数量（退货为负向抵扣） | 发运事实 | 订单交付、在途起点 |

来源与冲突：

- P1：`EN_API/item_shipment_status.py:636-641,653-691`；PR #291 `EN_API/fulfillment/quantities.py:7-12`、`stages.py:49-56`。
- P2：`supply_chain_visibility/docs/reference/en-produced-qty-vs-jobcard.md:55-81,94-105`（分支 #291）。
- P3：`en-produced-qty-vs-jobcard.md:28-32`；`erpnext/docs/work-order-investigation-methodology.md:115-125` 有反例（`produced_qty 285` vs SE 216）。
- P4：PR #291 `item_shipment_status.py:720-747`；蓝图 `en-end-to-end-supply-chain-fulfillment-visibility.md:230`。
- **冲突**：PR #291 的 `en-produced-qty-vs-jobcard.md:21-24` 主张「主口径 = `produced_qty`/入库，末道为副」，
  但同一 PR 的 `quantities.py`/`stages.py` 与旧蓝图明确 `WO.status/produced_qty` 不可信、进度读首道 JC。
  **V1 定稿：P1 进度；P3 产出；P4 发运；`WO.produced_qty` 仅作展示代理，不能当进度或产出事实。**
  建议把该文档的「主口径」改名为「库存入库口径」。

## 2. 守恒等式（按 cutoff 与需求类型限定）

### 2.1 需求冲减（R05 + G0 桶内已发订单）

```text
net_forecast        = max(0, forecast_qty − consumed_order_qty)
bucket_total_demand = consumed_order_qty + net_forecast
remaining_to_fulfill = open_order_qty + net_forecast
internal_replenishment_so  → 不计入 bucket_total_demand（单独标记）
```

四个量必须分开，且同范围/同 cutoff：

| 量 | 定义 |
|---|---|
| `forecast_qty` | 服务池 × 计划桶 × 版本的预测总量 |
| `consumed_order_qty` | 落在该桶匹配窗口内、且被该预测覆盖的终端订单总量（**含已发、部分发、未发**） |
| `open_order_qty` | 这些订单当前仍未交的量（只用于“还要发多少”） |
| `net_forecast` | 预测扣除桶内已覆盖订单后的净预测 |

- **桶内已发订单继续冲减预测**：预测 100、订单 30 已全部发完 → `consumed=30`、`net=70`、
  `bucket_total_demand=100`，不能因为 `open=0` 又把预测当成 100。
- 部分发运：订单 30 已发 10、未发 20 → `consumed=30`、`open=20`、`net=70`；
  `remaining_to_fulfill=90`（20 未发 + 70 净预测）。
- 交付**不能**让已冲减的需求重新长出来；不能用 `open_order_qty` 代替 `consumed_order_qty` 做冲减。
- 匹配范围：订单类型、承诺日期窗口、渠道/仓、版本必须一致；内部补货 SO 排除。
- 取消、跨桶、超额订单（`consumed > forecast`）规则由业务确认；超额部分进异常/下一桶，
  不得静默丢弃或把 `net_forecast` 变成负数。

### 2.2 交付与反向流

```text
valid_demand      = positive_shipped + open_to_ship          (1)
positive_shipped  = Σ submitted DN 正向签名数量
net_delivered     = positive_shipped − returned
open_to_ship      = valid_demand − positive_shipped
return_reopen     = 仅当业务明确批准补发，才增加新的履约义务
```

- 退货**不自动重开**未交义务；返运是独立流。
- 例：下单 100、取消 20、正向发运 70、退货 10 → 有效 80 = 正向 70 + 原未发 10；
  净交付 60；返运 10 另记。

### 2.3 同 cutoff 的互斥供应余额（R06 + G0）

**不要用一条加法公式把所有状态相加**；先按 `(cutoff, item, warehouse, UOM)` 定义互斥状态，
再对状态求和。同一件货在任一 cutoff 只能落在一个状态。

| 状态 | 含义 | 互斥/来源规则 |
|---|---|---|
| `on_hand_available` | 已在该库存快照中的可用量 | 同一快照里已扣预留后的余额 |
| `allocated_to_open_orders` | 同一快照中已预留/分配 | 与 `on_hand_available` 互斥；不能扣两次 |
| `wip_unfinished` | 未完成工序部分（按成品当量/UOM） | 只含未完成部分；不与 `produced_pending_stock_in` 重叠 |
| `produced_pending_stock_in` | 已完成但尚未提交入库 | 与 `wip_unfinished` 互斥；已完成部分 |
| `in_transit_reconciled` | 采购/头程经 crosswalk 后的**单一**在途余额 | 两个来源视图只保留一个余额；未对齐/冲突进异常 |
| `arrived_pending_receipt` | 已到港/到仓但未收货 | 已到但未进入收货行 |
| `received_pending_putaway` | 已收货但尚未进入可用快照 | 只有“已收但未进快照”的余量可单列 |

规则：

- **新收货是来源事件**：若 `on_hand_available` 已包含新收 20，不得再加 `received_available 20`；
  只把“已收但尚未进入该库存快照”的余量列为 `received_pending_putaway`。
- **采购/头程在途**：保留两种来源视图，经同一批次 crosswalk 得到一个 `in_transit_reconciled`；
  未对齐或数量冲突进异常，**不直接相加、不取 max、不取平均**。
- **WIP 与已生产待入库**：WIP 只含未完成部分；两者按相同规范物料/UOM 对账；
  不要把不同组件件数和成品件数强加成一个“供给总件数”。
- 累计里程碑（发运 100 → 在途 100 → 到港 100 → 实收 100）只用于审计，
  **不能相加成 400**。
- 没有实际来源的状态标 `unknown`，不要当 0。

### 2.4 收货与海外实收（R04 + G0）

```text
overseas_gross      = accepted + damaged + rejected
qualified_received  = accepted                 # 合格实收，不等于可用
available_after_putaway = accepted − pending_inspection − pending_processing − pending_shelving
unreceived          = ordered − accepted − damaged − rejected
```

- 字段命名固定：`gross`（总收）、`accepted`（合格）、`damaged`（损坏）、`rejected`（拒收）。
- `accepted` 是**合格实收**指标；合格品仍可能待检、待加工、待上架，**不能直接等同可用库存**。
- 无实际来源时，`pending_*` 与 `available_after_putaway` 标 `unknown`，不要当 0。
- 收货行有 `source_receipt_id + source_receipt_line_id + revision`；
  新 revision **替换**旧 revision，不累计。
- 一行收货可分摊到多个 DN 行/供应批次；`qualified_received` 只算 `accepted`，
  不把 discrepancy 当已实收。
- 其余管道：

```text
purchase_ordered  = purchase_received + purchase_in_transit  (5)
order_kit_ready   = min over required lines(component_ready / qty_per)    (6)
```

**派生辅助式（仅估算）：**

```text
pending_stock_in = last_op_reported − stock_in_produced
```

> P1/P2/P3/P4 之间不是等式关系；只能按上述差额解释。把首道报工直接当产出，是最常见的数量错误。

## 3. 实体、粒度与键

| 事实表 | 一行 = | 主键 / 连接键 | 现状 |
|---|---|---|---|
| `item_master` / `item_alias` | 物料的一个别名 | EN `item_code`、通途 SKU、客户码 | 三系统定义不同；需后缀规则 |
| `bom_edge` | 父件 × 子件 | `(parent, component, bom_version)` | BOM/Bundle/已确认配套要区分，禁止靠前缀猜 |
| `demand_line` | SO Item × 需求物料 | `Sales Order Item.name` + `demand_type` | #291 `model.py:71-92` 已落地；需区分终端/内部补货 |
| `forecast_bucket` | 商品 × 服务池 × 计划桶 × 版本 | 复合键；含 `forecast_qty`、`included_order_qty`、`net_forecast` | **新增**；匹配窗口/类型必须落表 |
| `production_fact` | WO × 工序 × 事件 | `Work Order.sales_order_item` | 优先用该字段关联 SO 行 |
| `factory_shipment_line` | DN Item | **`Delivery Note Item.name`（自身 ID）**；`parent`=DN 头；`so_detail`=SO 行外键；`against_sales_order`=SO 头外键 | 已实现；**不能用 `so_detail` 当 DN 行主键** |
| `inventory_snapshot` | SKU × 仓 × 快照时间 | `(snapshot_id, sku, warehouse)` | 见 05 §4.4；通途为源 |
| `purchase_order_line` | PO 行 | 通途 PO 号 + SKU + 仓 | 在途只认通途采购单 |
| `headleg_batch` | 一个头程批次 | `external_shipment_no` / `zm_no` | **未建模**；蓝图已设计 |
| `headleg_allocation` | 批次 × **DN 行** × 数量 | `(headleg_batch_id, dn_line_id)`，保留 `so_item_id` 追溯 | **未实现；必须补**；只到 SO 行会在拆票时丢失 |
| `headleg_event` | 不可变事件 | `event_id` | **未实现** |
| `overseas_receipt_line` | 原始收货行 × revision | `(source_receipt_id, source_receipt_line_id, revision)` | **新增**；`(batch,item)` 不能唯一标识多次实收 |
| `receipt_allocation` | 收货行 → DN 行/供应批次 | `(receipt_line_id, target_type, target_id)` | **新增**；支持一行收货分给多个 DN 行 |
| `supply_balance` | cutoff × 状态桶 | `(as_of, bucket, item, warehouse)` | **新增**；同一件货只能在一个桶 |

## 4. 批次关联：三个「批次」不能混用

1. **生产跟踪号（菲号）**：WO 内的批次身份，不是发运批次。
   `supply_chain_visibility/docs/reference/en-tracking-number-semantics.md`（#291）。
2. **头程批次（ZM/批次号）**：与 SO 行多对多；批次号常只在合并单元格首行，须向下填充。
   `CONCEPTS.md:186-207`、蓝图 `:345-348`。
3. **通途采购单号 `PONum`**：通往钉钉物流表的钥匙，但不是头程批次。
   `docs/solutions/workflow-issues/cargo-location-tracking-source-reliability.md:51,85-88`。

**必须补的映射：** `headleg_allocation(headleg_batch_id, dn_line_id, qty)`（保留 `so_item_id` 追溯）、
`headleg_event(batch_id, event_type, event_time, source, confidence)`、
`receipt_allocation(receipt_line_id, dn_line_id, qty, category)`。
没有它们，拆票/拼柜/分批实收后无法做数量对账，也无法把在途量摊到 DN/SO 行。

**已知过期规则**：`cargo-location-tracking-source-reliability.md:73` 仍写「批次号 → SO 的 `po_no`」，
与 `CONCEPTS.md` 及蓝图 §5.1 冲突；`po_no` 是离职同事自编内部流转号，待废弃。

## 5. 需求冲减与需求类型（R05）

| 需求类型 | 是否进入终端需求 | 去重/冲减规则 |
|---|---|---|
| 终端订单（客户/平台） | 是 | 按订单行 + 承诺日期 + 渠道/仓；取消/改量保留版本 |
| 预测 | 是（净额） | `net_forecast = max(0, forecast − included_orders)`；只冲减匹配窗口内的终端订单 |
| 内部补货 SO | 否 | 单独标记；否则同一需求被下单两次 |
| 退货/返运 | 否（独立流） | 只在业务批准补发时生成新履约义务 |
| 样品/一次性 | 按业务标注 | 默认不进入补货预测，需显式例外 |

**冲减流程**：先确定服务池（商品 × 渠道/仓）、计划桶（月/周）、版本；
再把落在匹配窗口内的终端订单标记为 `included_order_qty`；最后输出 `net_forecast`。
**禁止**把 forecast 与所有 SO 直接相加；也禁止把内部补货 SO 当终端需求。

---

## 6. SKU / 单位 / 配套映射

| 映射 | 键 | 规则 | 风险 |
|---|---|---|---|
| 通途 SKU ↔ EN 物料 | 客户物料号 `customer_items.ref_code`；完整 SKU 精确匹配 | 剥已知后缀（`-淘汰/-out/-Cover/-Foam`）只用于候选 | 历史改名会断匹配 |
| 拆包/合并 | `split_group` + 行/包裹血缘 | 沿用 #294 `order_side_input.py`、#295 `group_split_rows`；歧义 fail-closed | 不保留血缘会双计 |
| BOM / Bundle / 配套 | `(parent, component, bom_version)` | 不靠前缀猜；Product Bundle 与 BOM 分开 | 套件展开错会污染需求 |
| 单位换算 | `(item, from_uom, to_uom, factor)` | 每张单据保留原 UOM | WO/SE/DN 单位不一致 |
| 仓库别名 | 仓名族（如 `美中-FZH-DANEEY` 家族） | 新仓/改名走三处登记 | 别名漏算库存/销量 |

## 7. 已有实现与缺口

**已实现：**
- #291：阶段 0–3、四层证据、数量阶梯、按输入物料保留命中/未命中（`stages.py:13-61`、`assemble.py:37-182`、`quantities.py:7-51`）。
- #294：拆单/补件/皮壳结构键与件数规则（`order_side_input.py:31-83,446-482`）。
- #295：`group_split_rows` 只产出候选组、不合并（`ustx_cost_compare.py:823-869`）；设计断言见 `cost-engine-spec/30-design-merge-split-no-double-count.md:29-51`。

**缺口：**
- 头程分配/事件/实收未建模；采购在途未进统一入口；
- 配套展开仅 BOM 路径；单位换算与套件映射无独立表；
- 海外仓实收/上架无权威源；`headleg_allocation` 是最大断点。

## 8. 未决项与最小验证（全部只读）

| # | 待验证 | 方法 | 影响 |
|---|---|---|---|
| V1 | `SO Item.delivered_qty` 是否已扣退货 | 取一张有退货 DN 的 SO，比较 `delivered_qty` 与 `Σ signed DN` | 守恒式 (1) 是否成立 |
| V2 | 退货 DN 是否带 `against_sales_order/so_detail` | 抽样 1–2 张退货 DN | 行级净额是否可做 |
| V3 | 草稿退货是否冲减 `draft_dn` | 检查草稿 DN 语义 | 草稿是否计入 |
| V4 | `produced_qty` 是否等于已提交 Manufacture SE | 抽查 5–10 张 WO（已知 WO-26-00082 反例） | P3 是否可信 |
| V5 | 一键完工虚拟 JC/SE 是否虚增 | 查 SE 备注/employee=HR-EMP-00001 | P1/P3 是否被污染 |
| V6 | 返工/并行工序是否被排除 | 抽查含返工 WO | P1 是否高估 |
| V7 | 取消/改单/草稿 WO 是否重复计数 | 核对 docstatus 过滤 | 需求/产出是否重复 |
| V8 | UOM 换算与「首道恒为裁剪」 | 抽查 routing/UOM | 跨单位数量是否错 |
| V9 | `WO.status='Completed'` 可靠性 | 按事件而非状态判断 | 进度口径 |
| V10 | `factory_shipped` 取 `delivered_qty` 还是 `shipped_dn` | 二选一并加对账断言 | 守恒式 (1) |
| V11 | `Delivery Note Item.name` 是否唯一；同一 `so_detail` 是否对应多张 DN 行 | 取一张拆票 DN，检查行 ID 与 `so_detail` | R03：DN 行身份 |
| V12 | 收货行是否带原始凭证/行/revision；一行能否分给多个 DN 行 | 取一张部分收货单 | R04：收货分摊 |
| V13 | 预测 100 是否已含订单 30；内部补货 SO 是否被重复计入 | 取一个预测版本 + 当期 SO | R05：需求冲减 |
| V14 | 同一 cutoff 下各供应桶是否互斥 | 对同一批货取发运/在途/到港/实收 | R06：余额不重复 |
| V15 | 退货是否自动重开未交义务 | 取一张退货 + 补发记录 | R06：反向流 |
| V16 | 累计里程碑是否被误加总 | 检查报表 SQL / 视图 | R06：事件 vs 余额 |

> 测试边界：V1–V16 全部只读；EN 测试环境优先，生产只读抽样需批准；**禁止写 EN 生产库存账**。
