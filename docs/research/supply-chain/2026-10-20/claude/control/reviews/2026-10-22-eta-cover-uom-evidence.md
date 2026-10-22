---
okf: v0.1
type: Review
title: 10 SKU 的 ETA / Cover / UOM / 在途证据梳理（B，只读）
date: 2026-10-22
owner: claude-worker
verdict: 6-blockers-eta
scope: expand10 10 SKU × 4 维度
---

# 10 SKU 的 ETA / Cover / UOM / 在途证据梳理

> **结论：10 个 SKU 中，在途与 BOM/UOM 均有可追溯证据；6 个 SKU 的 ETA 是硬 blocker
> （`will_arrive_date` 全库 0/524 非空）；Cover 对 6 个 SKU 是可观测的 0，对 4 个 SKU
> 属于「无桶映射」的 scenario。**
> 本轮只读：0 次通途/EN 网络请求，`order_store.duckdb` 以 `read_only=True` 打开，未写入、未改表。

## 1. 范围判定（必须先说清楚）

任务书写「10 个 SKU 的 trace：`D:/Work/fzh-order-store/trace_examples.json/md`」，
但**该 trace 只有 5 个 SKU**（KS0001-QDKTR-100-DEEPGREY、KS0230-WGMSRKQCLG-60-WHITE、
KS0153-KQCLG-78-WHITEKHAKI、KS0316-HLR-55-LINEPURPLE、KS0249-QRJL-153-QIRUOJINLAN），
其中**只有 KS0001-QDKTR-100-DEEPGREY 与本轮 10 SKU 重叠**。

本轮 10 SKU 取自任务书同时点名的 EN 快照输入：
`experiments/g1_contract/out/g1b_en_top_1..9.json` + `g1b_en_rr2.json`（即 G1B expand10），
经 `sku_map.tongtool_sku` 唯一映射到 10 个 KS item_code：

| # | 客户码（任务书 10 SKU） | item_code | 来源快照 |
|---:|---|---|---|
| 1 | CENCord995-DKGrey-97 | KS0001-QDKTR-100-DEEPGREY | top_1 |
| 2 | CEN003-DPBLUE-100 | KS0001-QDKTR-100-DEEPBLUE | top_2 |
| 3 | C/Linen-Natural-100-688-wow | KS0001-XMMBS-100-HEMPNATURAL | top_3 |
| 4 | C/Cord-DKBlue-100-713-wow | KS0001-CMKTR-100-DEEPBLUE | top_4 |
| 5 | C/Linen-Natural-153-688-wow | KS0001-XMMBS-153-HEMPNATURAL | top_5 |
| 6 | C/Velvet-Grey-100-705-wow | KS0001-PR-100-GREY | top_6 |
| 7 | C/Cord-Grey-100-710-wow | KS0001-CMKTR-100-GREY | top_7 |
| 8 | C/Linen-White-100-662-WOW | KS0001-CMM-100-WHITE | top_8 |
| 9 | TT0000671K0063721 | KS0001-HLR-100-OFFWHITE | top_9 |
| 10 | C/Linen-Natural-194-688-wow | KS0001-XMMBS-194-HEMPNATURAL | rr2 |

trace 包里另外 4 个 SKU 的现状见附录（不计入 10×4 矩阵）。
**没有自行补 5 个 trace SKU 来凑 10**；若项目要的确实是 trace 口径，需要重新下任务书。

## 2. 判定口径

| 判定 | 含义 |
|---|---|
| `evidence_present` | 有名表/字段/行且非空，直接回答该维度，使用它不需要未证假设 |
| `scenario` | 有可引用值，但使用它需要一条**写明的假设**，假设可被业务接受或推翻 |
| `blocker` | 关键字段/行缺失或全空，本地数据无法给出该维度值，必须外部输入 |

引用格式统一为 `表.字段 = 值`。所有数字均可由 `out/eta_cover_uom/evidence.json` 复算。

## 3. 10 × 4 判定矩阵

| # | SKU | ETA | 在途 | Cover | UOM |
|---:|---|---|---|---|---|
| 1 | KS0001-QDKTR-100-DEEPGREY | ✅ evidence_present（无未结 PO，不需 ETA） | ✅ evidence_present（0） | ✅ evidence_present（-Cover 桶 0） | ⚠️ scenario |
| 2 | KS0001-QDKTR-100-DEEPBLUE | ✅ evidence_present（无未结 PO） | ✅ evidence_present（0） | ✅ evidence_present（-Cover 桶 0） | ⚠️ scenario |
| 3 | KS0001-XMMBS-100-HEMPNATURAL | ⛔ **blocker**（1 行 / 121 件无日期） | ✅ evidence_present（121） | ⚠️ scenario（无 cover 桶） | ⚠️ scenario |
| 4 | KS0001-CMKTR-100-DEEPBLUE | ⛔ **blocker**（2 行 / 240 件无日期） | ✅ evidence_present（120） | ✅ evidence_present（-Cover 桶 0） | ⚠️ scenario |
| 5 | KS0001-XMMBS-153-HEMPNATURAL | ⛔ **blocker**（3 行 / 223 件无日期） | ✅ evidence_present（215） | ✅ evidence_present（-Cover 桶 0） | ⚠️ scenario |
| 6 | KS0001-PR-100-GREY | ✅ evidence_present（无未结 PO） | ✅ evidence_present（0） | ✅ evidence_present（-Cover 桶 0） | ⚠️ scenario |
| 7 | KS0001-CMKTR-100-GREY | ⛔ **blocker**（3 行 / 318 件无日期） | ✅ evidence_present（165） | ✅ evidence_present（-Cover 桶 0） | ⚠️ scenario |
| 8 | KS0001-CMM-100-WHITE | ⛔ **blocker**（2 行 / 73 件无日期） | ✅ evidence_present（73） | ⚠️ scenario（无 cover 桶） | ⚠️ scenario |
| 9 | KS0001-HLR-100-OFFWHITE | ⛔ **blocker**（2 行 / 490 件无日期） | ✅ evidence_present（490） | ⚠️ scenario（无 cover 桶） | ⚠️ scenario |
| 10 | KS0001-XMMBS-194-HEMPNATURAL | ✅ evidence_present（无未结 PO） | ✅ evidence_present（0） | ⚠️ scenario（无 cover 桶） | ⚠️ scenario |

计数：ETA blocker **6**、evidence_present 4；在途 evidence_present 10（其中 6 个的
「在途↔PO 逐笔关系」另判 scenario）；Cover evidence_present 6 / scenario 4；
UOM scenario 10（无 blocker，也无纯 evidence_present）。

### 逐 SKU 证据索引（表.字段 = 值）

| # | SKU | ETA | 在途 | Cover | UOM |
|---:|---|---|---|---|---|
| 1 | QDKTR-100-DEEPGREY | `tongtool_po`: 0 行 → `open_qty=0` | `stock_latest.intransit=0`（5 行） | `stock_latest[TT0000995K0010982-Cover].available=0` | `bom.uom=个`；`bom_item.uom=个`×2 |
| 2 | QDKTR-100-DEEPBLUE | `tongtool_po`: 1 行且 `open_qty=0` | `stock_latest.intransit=0`（4 行） | `stock_latest[KZ0001005K0001291-Cover].available=0` | `bom.uom=个`；`bom_item.uom=个`×2 |
| 3 | XMMBS-100-HEMPNATURAL | `open_qty=121`，`will_arrive_date=NULL` | `stock_latest.intransit=121`（美东） | `item_cover_stock`: 0 行；无 `-Cover` 别名 | `bom.uom=个`；`bom_item.uom=个`×2 |
| 4 | CMKTR-100-DEEPBLUE | `open_qty=240`，`will_arrive_date=NULL` | `stock_latest.intransit=120`（美东） | `stock_latest[C/Cord-DKBlue-100-713-wow-Cover].available=0` | `bom.uom=个`；`bom_item.uom=个`×2 |
| 5 | XMMBS-153-HEMPNATURAL | `open_qty=223`，`will_arrive_date=NULL` | `stock_latest.intransit=215`（美东） | `stock_latest[C/Linen-Natural-153-688-wow-Cover].available=0` | `bom.uom=个`；`bom_item.uom=个`×2 |
| 6 | PR-100-GREY | `tongtool_po`: 3 行且 `open_qty=0` | `stock_latest.intransit=0`（3 行） | `stock_latest[C/Velvet-Grey-100-705-wow-Cover].available=0` | `bom.uom=个`；`bom_item.uom=个`×2 |
| 7 | CMKTR-100-GREY | `open_qty=318`，`will_arrive_date=NULL` | `stock_latest.intransit=165`（美东） | `stock_latest[C/Cord-Grey-100-710-wow-Cover].available=0` | `bom.uom=个`；`bom_item.uom=个`×2 |
| 8 | CMM-100-WHITE | `open_qty=73`，`will_arrive_date=NULL` | `stock_latest.intransit=73`（美东） | `item_cover_stock`: 0 行；无 `-Cover` 别名 | `bom.uom=个`；`bom_item.uom=个`×2 |
| 9 | HLR-100-OFFWHITE | `open_qty=490`，`will_arrive_date=NULL` | `stock_latest.intransit=490`（美中） | `item_cover_stock`: 0 行；无 `-Cover` 别名 | `bom.uom=个`；`bom_item.uom=个`×2 |
| 10 | XMMBS-194-HEMPNATURAL | `tongtool_po`: 4 行且 `open_qty=0` | `stock_latest.intransit=0`（3 行） | `item_cover_stock`: 0 行；无 `-Cover` 别名 | `bom.uom=个`；`bom_item.uom=个`×2 |

> UOM 列的 `stock_latest` 侧无 uom 字段、`stock_history.uom_basis='unknown'`，
> 这是 10 个 SKU 共同的 scenario 依据，不在每行重复。

## 4. 逐维度证据

### 4.1 ETA

**全局字段完整性（`tongtool_po`，524 行）**

- `will_arrive_date` 非空 **0 / 524**（`count(will_arrive_date)=0`）。
  该字段存在但整列为空，不是「部分缺失」。
- `purchase_date` 非空 524/524（如本次 13 条未结行为 2026-09-09～2026-10-13 的采购时间），
  但**采购时间不是到货时间**；用采购时间 + 假设提前期推算属于估计，本轮不做。
- `item_attr.lead_days = 14`（10/10 SKU，15,230 行中 3,344 行 > 0）。
  这是**提前期属性，不是到货日期**，且 10 个 SKU 全为同一个 14 天值，不能当逐 PO 承诺；
  本轮没有用它推算任何 ETA。若业务书面确认「采购日期 + lead_days = 计划到货」，
  可作为 scenario 路径（见 B1），但仍不等于供应商确认的 ETA。
- 全库检索 `information_schema.columns`：除 `tongtool_po.will_arrive_date` 外，
  **没有任何表含到货日期字段**（`item_attr.lead_days` 是提前期；其余日期字段只有
  `en_orders/gs_orders.sale_date`、`despatch_date`、`stock_history.snapshot_date` 等出库/快照日期）。
- EN 快照（10 个）只有 SO/DN/WO/PP/SE 单据，**无采购单**；`so_delivery_date` 是客户交期，
  `wos.planned_end_date` 是工单计划完工，均不能当采购 ETA。

**本轮 10 SKU 的未结 PO**

- `tongtool_po` 关联 `sku_map` 共 **32** 条 PO 记录；其中 `open_qty > 0` 的 **13 行**，
  合计 **1,465 件**，分属 **6 个 PO**。
- 这 13 行的 `will_arrive_date` **0 行非空**；`purchase_date` 13/13 非空。
- 6 个 SKU 因此判 blocker；4 个 SKU 未结行 = 0（`open_qty` 合计 0），ETA 不适用，
  判 evidence_present。

| SKU | 未结行 | 未结数量 | 涉及 PO | 未结行有 ETA |
|---|---:|---:|---|---:|
| KS0001-XMMBS-100-HEMPNATURAL | 1 | 121 | PO021717 | 0/1 |
| KS0001-CMKTR-100-DEEPBLUE | 2 | 240 | PO021733, PO021735 | 0/2 |
| KS0001-XMMBS-153-HEMPNATURAL | 3 | 223 | PO021717, PO021733, PO021735 | 0/3 |
| KS0001-CMKTR-100-GREY | 3 | 318 | PO021717, PO021733, PO021735 | 0/3 |
| KS0001-CMM-100-WHITE | 2 | 73 | PO021717, PO021726 | 0/2 |
| KS0001-HLR-100-OFFWHITE | 2 | 490 | PO021716, PO021727 | 0/2 |

> 逐 PO 数量不在此展开（避免落原始订单明细）；各 SKU 的数量已与
> `replenishment_pool.on_order` 逐仓对平（见 §6）。

### 4.2 在途

- 证据表：`stock_latest`（`warehouse, sku, available, intransit`），
  经 `sku_map.tongtool_sku` 关联到 item_code，共 34 行（含 6 行 `-Cover` 别名）。
- 有在途（`intransit > 0`）的只有 6 个 SKU×仓：121 / 120 / 215 / 165 / 73 / 490；
  其余 4 个 SKU 所有行 `intransit = 0`（这也是观测值，不是缺失）。
- 与 pool 对平：13 个 `replenishment_pool` 行的 `intransit_all` 与
  `sum(stock_latest.intransit)` 逐行相等（例：KS0001-CMKTR-100-GREY 美东 165 = 165）。
- **PO 关系**：`stock_latest` 没有 PO 号/发运批次键，`tongtool_po` 也没有库存行键，
  **无法逐笔关联**。可按仓比较的是「同仓 `sum(open_qty) >= intransit`」，
  本轮 6 个有未结 PO 的仓全部成立（240≥120、318≥165、223≥215、73=73、490=490、121=121）。
  因此 `supply_basis = available + max(intransit, PO)` 在这 10 个 SKU 上取到的是 PO 值，
  **不会重复计数**；但「intransit 是 open PO 的子集」仍是逻辑假设，判 scenario。

### 4.3 Cover

- 证据表 1：`item_cover_stock`（`item_code, warehouse, cover_available`），
  全表 155 行，但**这 10 个 item_code 一行都没有**。
- 证据表 2：`stock_latest` 中 6 个 SKU 存在 `-Cover` 别名行
  （CMKTR-100-DEEPBLUE、CMKTR-100-GREY、PR-100-GREY、QDKTR-100-DEEPBLUE、
  QDKTR-100-DEEPGREY、XMMBS-153-HEMPNATURAL），
  这些行 `available = 0`、`intransit = 0`（观测值）。
- 证据表 3：`replenishment_pool.cover_available = 0`（13/13 行），
  `supply_basis = "available + max(intransit, PO)"`；即本轮 **cover 没有进入供给公式**。
- 判定拆分：
  - **6 个有 `-Cover` 桶的 SKU = evidence_present**：桶存在且观测值为 0，未计入供给。
  - **4 个无 `-Cover` 桶的 SKU = scenario**：`item_cover_stock` 无行、`sku_map` 无别名，
    「没有 cover 池」是推断；`absence ≠ 0` 未证。它们分别是
    XMMBS-100、CMM-WHITE、HLR-OFFWHITE、XMMBS-194。
- 全局仍成立：cover 与不带后缀库存是否实物同池/可替代**未证**（R290 遗留）。
  本轮的所有 SKU 都不依赖 cover 替代，所以该假设不影响本矩阵的数值，只影响将来启用 cover 供给时。

### 4.4 UOM

- `bom.uom = '个'`（10/10 SKU，`bom.quantity = 1.0`）。
- `bom_item.uom = '个'`（20/20 子件行），且 `qty = 1.0`（皮壳 PK# + 内胆 ND# 各 1）。
- 需求侧：10 个 EN 快照的 `so_rows.uom = '个'`（215/215 行）。
- 供给侧：`stock_latest` **没有 uom 列**；`stock_history.uom_basis = 'unknown'`
  **15,820 / 15,820 行全为 unknown**。
- 结论：BOM 与需求侧都有 `个`，且 1:1，**不需要换算**；
  但「通途库存单位也是 `个`」没有字段证据，判 **scenario**。
  这是低风险假设（1:1、成品/皮壳、库存数为整数件），不是 blocker。
- 无 SKU 出现 BOM 缺失或单位冲突；若出现，那才是 blocker。

## 5. Blocker 清单与最小可验证输入

### B1. ETA 缺失（6 个 SKU，13 条未结行，6 个 PO）

- **缺什么**：每条未结 PO 行的预计到货日期。
- **证据**：`tongtool_po.will_arrive_date` 全库 0/524 非空；本轮未结行 0/13 有值。
  另有 `item_attr.lead_days = 14`（10/10），但它是提前期属性、不是到货日期。
- **最小可验证输入**（任一）：
  1. 采购/业务（Jack）按 PO 行提供「预计到货日期」——只需 6 个 PO：
     `PO021716`、`PO021717`、`PO021726`、`PO021727`、`PO021733`、`PO021735`；
  2. 通途采购单/采购 API 中对应的 ETA 字段导出（按 PO 号即可，不需要全量）；
  3. 若业务确认「采购日期 + `item_attr.lead_days`(14) = 计划到货」规则，
     可把 ETA 从 blocker 降为 **scenario**（需书面确认；本轮未计算任何 ETA）。
     **不能由 Agent 自行用 purchase_date 推算**，也不能把 14 天当供应商承诺。
- **验收**：13/13 未结行有日期或明确标注「无 ETA」，且来源可指到 PO 行。

### B2. Cover 桶缺失（4 个 SKU：XMMBS-100 / CMM-WHITE / HLR-OFFWHITE / XMMBS-194）

- **缺什么**：确认这些 SKU 是否存在共享 Cover 池。
- **证据**：`item_cover_stock` 对这 4 个 item_code 0 行；`sku_map` 无 `-Cover` 别名。
- **最小可验证输入**：业务确认「无 cover 池」；或 EN `Bin` / PK# 皮壳库存快照
  （同仓、同 item_group）证明有/无。只需要这 4 个 item_code 的结果，不需要全量。

### B3. 在途↔PO 逐笔归属（6 个有在途的 SKU，仅 scenario，不阻塞数值）

- **缺什么**：PO 行 ↔ 发运批次/在途分录的单据键。
- **证据**：`stock_latest` 只有 sku×warehouse 汇总，`tongtool_po` 只有 PO 行；
  两表无共同键；同仓 `open_qty >= intransit` 全部成立。
- **最小可验证输入**：通途采购单的「已发/在途/入库」分录或发运批次号；
  若业务接受「在途是未入库 PO 的子集」，则本条直接关闭为 scenario-accepted。
- **影响**：只影响「按 PO 分配 ETA」；不影响当前 `max(intransit, PO)` 的取值。

### B4. 库存单位（10 个 SKU，scenario）

- **缺什么**：通途库存 SKU 的计量单位。
- **证据**：`stock_latest` 无 uom 列；`stock_history.uom_basis` 全 unknown。
- **最小可验证输入**：确认这 10 个通途 SKU 的单位 = `个`（或提供带 uom 的库存快照）。
  由于 BOM 1:1、EN SO 全为 `个`，只需业务/数据侧一句确认。

## 6. 计数对账

| 项 | 数量 | 说明 / 出处 |
|---|---:|---|
| SKU | 10 | §1 映射表 |
| pool 行 | 13 | 3 个 SKU 跨 2 仓（QDKTR-100-DEEPGREY、QDKTR-100-DEEPBLUE、HLR-100-OFFWHITE） |
| pool 仓 | 3 | 美东-CENTRADE、美中-FZH-DANEEY、波兰-FZHPoland-covers |
| PO 关联记录 | 32 | `tongtool_po` ⋈ `sku_map`（含已入库行） |
| 未结 PO 行 | 13 | `open_qty > 0`，合计 1,465 |
| 不同未结 PO | 6 | PO021716/717/726/727/733/735 |
| BOM 行 | 10 | `bom.item` 命中 10/10 |
| BOM 子件行 | 20 | `bom_item`，每 SKU 2 行，全 `qty=1`、`uom=个` |
| stock 行 | 34 | `stock_latest` ⋈ `sku_map`；含 6 行 `-Cover` |
| `item_cover_stock` 行 | 0 | 10 个 item_code 均无 |
| `stock_history` 行 | 15,820 | 全部 `uom_basis=unknown`；10-22 最新快照 |
| EN 快照 | 10 个 | 215 SO 行，`uom` 全 `个` |

对账等式（逐仓成立）：

- `replenishment_pool.on_order` = `sum(tongtool_po.open_qty)`；
- `replenishment_pool.available_all` = `sum(stock_latest.available)`；
- `replenishment_pool.intransit_all` = `sum(stock_latest.intransit)`。

**没有静默丢弃的行**：32 条 PO 记录 = 13 未结 + 19 已入库（`open_qty = 0`）。

## 7. 可用于扩样的最小条件

1. **ETA**：不要求 10 个 SKU 全有 ETA，但**有未结 PO 的 SKU 必须逐 PO 拿到日期**，
   否则预测/补货模型只能把到达时间当 unknown，不能宣称「含 ETA」。
   当前 6/10 卡在这里；4/10 无未结 PO，不受影响。
   若业务接受 `purchase_date + item_attr.lead_days(14)` 作为计划到货，可降为 scenario，
   但必须书面确认，且不能与真实 ETA 混用。
2. **UOM**：这 10 个 SKU 全为 BOM 1:1、单位 `个`，**不需要换算**；
   扩样到其他品类时必须先验证 UOM，否则不能跨品类合并。
3. **Cover**：本轮 cover 不进入供给，6 个 SKU 可证为 0；
   若要启用「cover 计入供给」，先解决同池/可替代证据（B2 + R290 全局遗留）。
4. **在途**：`max(intransit, PO)` 在这 10 个 SKU 上安全（PO ≥ intransit），
   但只能按 SKU×仓，不能按 PO 逐笔分配到达时间。

## 8. 已知限制

- **trace 包与任务书不符**：声称 10 个 SKU，实际 5 个，且只 1 个与 expand10 重叠（§1）。
- **库存时点**：`replenishment_pool`/`stock_latest` 是 2026-10-21 13:48 抓取；
  `stock_history` 已有 2026-10-22 快照。4 个 SKU 的 available 有 1–6 件差异
  （CMM-WHITE 57→54、XMMBS-153 338→336、XMMBS-194 319→313、XMMBS-100 21→20），
  intransit 无差异。本轮引用 pool 口径，故与 pool 对平；换成 10-22 快照会小幅变动。
- **pool 只覆盖 3 个仓**（美东-CENTRADE / 美中-FZH-DANEEY / 波兰-FZHPoland-covers）；
  `stock_latest` 另有 WayfairCG-Cranbury 等仓库行（如 CMKTR-100-GREY 该仓 available=6），
  这些不在 `replenishment_pool` 口径内，本轮的供给/在途不并入，也不代表它们不存在。
- **`item_cover_stock` 来源不可考**：本地仓库没有生成该表的代码，
  「无行 = 无 cover」只能作为假设，不能作为观测结论。
- **EN 快照是 2026-10-20/21 离线抓取**，不是本轮实时数据；本轮 0 次生产访问。

## 附录：trace 5 个 SKU 的现状（不计入 10×4 矩阵）

| SKU | 仓 | ETA | 在途 | Cover | UOM |
|---|---|---|---:|---|---|
| KS0001-QDKTR-100-DEEPGREY | 波兰 / 美中 | 无未结 PO | 0 | -Cover 桶 0 | 个 |
| KS0230-WGMSRKQCLG-60-WHITE | 波兰 / 美中 | 无未结 PO | 0 | 无 cover 桶 | 个 |
| KS0153-KQCLG-78-WHITEKHAKI | 波兰 / 美中 | 无未结 PO | 0 | 无 cover 桶 | 个 |
| KS0316-HLR-55-LINEPURPLE | 波兰 / 美中 | ⛔ **blocker**：PO021715 未结 10，`will_arrive_date` NULL | 波兰 10 | `item_cover_stock` 波兰 15 / 美中 28；`-Cover` 库存 15/28，未计入供给 | 个 |
| KS0249-QRJL-153-QIRUOJINLAN | 美东 | 无未结 PO | 0 | 无 cover 桶 | 个 |

> KS0316 是附录里唯一有未结 PO 的例子，且正是 R290 的 `cover_only` scenario；
> 它的 PO 也在波兰仓，与本轮矩阵无交集。

## 运行信息

- DB：`D:/Work/fzh-order-store/order_store.duckdb`
  `sha256=25579c5dcd802c7e67f610432a19d08f8e6952696bd50d43bdfa47d6b9241ae9`
  `bytes=51,654,656` `mtime=2026-10-22 07:50:35`
- 访问方式：`duckdb.connect(..., read_only=True)`；无通途/EN 网络调用；无写入。
- 证据 JSON：`out/eta_cover_uom/evidence.json`（聚合/字段值，不含原始订单明细）。
  同一份字节也放在项目既有的 `experiments/g1_contract/out/eta_cover_uom/evidence.json`；
  两处 `sha256=ad8cc8873ca37df08cec95e3a20dfebccda66cc3a0628c3f9d42f2d06966fc23`（35,228 bytes）。
- 用时：约 **6 分钟**（09:21–09:27，含只读查询、对账与报告），在 90 分钟时间盒内。
