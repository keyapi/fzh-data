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

## 2. 守恒等式

```text
valid_demand      = ordered − cancelled_or_amended
valid_demand      = factory_shipped + open_to_ship          (1)
factory_shipped   = unallocated + allocated                  (2)
allocated         = not_departed + in_transit + arrived_cleared + received  (3)
overseas_received = shelved + pending_processing + discrepancy (4)
purchase_ordered  = purchase_received + purchase_in_transit  (5)
order_kit_ready   = min over required lines(component_ready / qty_per)    (6)
```

- (1) `open_to_ship = qty − delivered_qty`，且 `delivered_qty` 必须已扣退货净额（**待验证**）。
- (2)(3) 头程在途与采购在途是**两条管道**，不能相加；必须先建 `headleg_allocation`。
- (4) 海外收货/上架无统一权威源；V1 只到「到港估算」。
- (5) 采购在途只认通途采购单；EN PO/请购链目前基本空白。
- (6) 已在 #291 `kit.py:25-99` 实现，但仅按 BOM 可选展开。

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
| `demand_line` | SO Item × 需求物料 | `Sales Order Item.name` | #291 `model.py:71-92` 已落地 |
| `production_fact` | WO × 工序 × 事件 | `Work Order.sales_order_item` | 优先用该字段关联 SO 行 |
| `factory_shipment_line` | DN Item | `DN Item.so_detail` | 已实现 |
| `inventory_snapshot` | SKU × 仓 × 快照时间 | `(snapshot_id, sku, warehouse)` | 见 05 §4.4；通途为源 |
| `purchase_order_line` | PO 行 | 通途 PO 号 + SKU + 仓 | 在途只认通途采购单 |
| `headleg_batch` | 一个头程批次 | `external_shipment_no` / `zm_no` | **未建模**；蓝图已设计 |
| `headleg_allocation` | 批次 × SO 行 × 数量 | 复合键 | **未实现；必须补** |
| `headleg_event` | 不可变事件 | `event_id` | **未实现** |
| `overseas_receipt` | 批次 × 物料 × 收货 | `(batch, item)` | 无统一源 |

## 4. 批次关联：三个「批次」不能混用

1. **生产跟踪号（菲号）**：WO 内的批次身份，不是发运批次。
   `supply_chain_visibility/docs/reference/en-tracking-number-semantics.md`（#291）。
2. **头程批次（ZM/批次号）**：与 SO 行多对多；批次号常只在合并单元格首行，须向下填充。
   `CONCEPTS.md:186-207`、蓝图 `:345-348`。
3. **通途采购单号 `PONum`**：通往钉钉物流表的钥匙，但不是头程批次。
   `docs/solutions/workflow-issues/cargo-location-tracking-source-reliability.md:51,85-88`。

**必须补的映射：** `headleg_allocation(headleg_batch_id, so_item_id, qty)` 和
`headleg_event(batch_id, event_type, event_time, source, confidence)`。
没有它们，拆批/拼柜后无法做数量对账，也无法把在途量摊到 SO 行。

**已知过期规则**：`cargo-location-tracking-source-reliability.md:73` 仍写「批次号 → SO 的 `po_no`」，
与 `CONCEPTS.md` 及蓝图 §5.1 冲突；`po_no` 是离职同事自编内部流转号，待废弃。

## 5. SKU / 单位 / 配套映射

| 映射 | 键 | 规则 | 风险 |
|---|---|---|---|
| 通途 SKU ↔ EN 物料 | 客户物料号 `customer_items.ref_code`；完整 SKU 精确匹配 | 剥已知后缀（`-淘汰/-out/-Cover/-Foam`）只用于候选 | 历史改名会断匹配 |
| 拆包/合并 | `split_group` + 行/包裹血缘 | 沿用 #294 `order_side_input.py`、#295 `group_split_rows`；歧义 fail-closed | 不保留血缘会双计 |
| BOM / Bundle / 配套 | `(parent, component, bom_version)` | 不靠前缀猜；Product Bundle 与 BOM 分开 | 套件展开错会污染需求 |
| 单位换算 | `(item, from_uom, to_uom, factor)` | 每张单据保留原 UOM | WO/SE/DN 单位不一致 |
| 仓库别名 | 仓名族（如 `美中-FZH-DANEEY` 家族） | 新仓/改名走三处登记 | 别名漏算库存/销量 |

## 6. 已有实现与缺口

**已实现：**
- #291：阶段 0–3、四层证据、数量阶梯、按输入物料保留命中/未命中（`stages.py:13-61`、`assemble.py:37-182`、`quantities.py:7-51`）。
- #294：拆单/补件/皮壳结构键与件数规则（`order_side_input.py:31-83,446-482`）。
- #295：`group_split_rows` 只产出候选组、不合并（`ustx_cost_compare.py:823-869`）；设计断言见 `cost-engine-spec/30-design-merge-split-no-double-count.md:29-51`。

**缺口：**
- 头程分配/事件/实收未建模；采购在途未进统一入口；
- 配套展开仅 BOM 路径；单位换算与套件映射无独立表；
- 海外仓实收/上架无权威源；`headleg_allocation` 是最大断点。

## 7. 未决项与最小验证（全部只读）

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

> 测试边界：V1–V10 全部只读；EN 测试环境优先，生产只读抽样需批准；**禁止写 EN 生产库存账**。
