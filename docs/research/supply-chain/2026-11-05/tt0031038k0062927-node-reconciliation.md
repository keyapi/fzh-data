---
okf: v0.1
type: Investigation-Results
title: TT0031038K0062927 库存节点核对（2026-11-05 / 11-06 复核）
description: 美中/CG/在途节点数量、91 到货与 102 出库、运营同事的 120 的可核实性、CG 多件套映射与在途缺口
date: 2026-11-06
tags: [supply-chain, inventory, reconciliation, tongtool, wayfair, cg]
---

# TT0031038K0062927 库存节点核对

> **范围**：通途 美中-FZH-DANEEY、通途 CG 账（WayfairCG-Cranbury仓）、Wayfair CG 权威 API、在途。
> **性质**：只读核对；未修改通途 / 赛狐 / ERPNext 任何数据。
> **SKU**：`TT0031038K0062927` ↔ EN `KS0156-NYBDSFH-52x52x5-BLACK`（成品）。
> **复核时点**：2026-11-06 09:06（北京时间）；通途快照 05:17；CG API 快照 07:00:58（UTC `2026-11-05T23:00:58Z`，age≈2.1h，`stale=false`）。

## 1. 结论（TL;DR）

1. **美中 2026-11-06 早上：可用 0，在途 405。** 11-05 日终已归零；11-06 00:00 起至 09:06 **无新增流水**。
2. **仓库同事的 91 是真的，但 11-05 出库是 102（不是 91）。** 09:09:50「采购单 +91」；17:34:00「其他出库 -102」（91 + 原有 11）。
3. **102 没有在通途 CG 账登记入库**（CG 仓 11-04 起 56 行变动，无该 SKU；CG 账仍 133）。**这是“找不到”的直接原因。**
4. **通途 CG 账 133 ≠ Wayfair CG 在库。** 直接查 CG API：base SKU 返回 `available=null / on_hand=null`（**无 Castlegate 仓位**）；有仓位的只有多件套：
   - `TT0031038K0062927-2PCS`：**5 套**（Cranbury 0、McDonough 2、Perris 2、Romeoville 1），折 10 件；
   - `TT0031038K0062927-3PCS`：**0 套**（11-05 还有 1 套，11-06 已归零）。
5. **运营同事的 10/5「120」无法核实。** 本机库存备份最早 2026-10-20、流水最早 2026-10-21、Wayfair 导出只有 2026-10-23；10-22 美中只有 36 可用 + 4 待发，在途 201。
6. **CG 在途：没有可直接用的 SKU 级入仓 API。** 实测 WSA 是 **CG→客户的出库**（`products` 有 SKU 级 `quantityShipped`，但 `shipFrom=CG`、`shipTo=客户`）；`getCastleGatePurchaseOrders` 是客户订单；`inboundOrder` 三状态全 null，`inboundOrderList` 未授权。可行替代：`ΔCG在库 + WSA出库` 反推收货。详见 [Wayfair CG 入仓/在途 API 调研](wayfair-cg-inbound-api-research.md)。`mode=live` 本轮 90 秒内未返回，实际使用每日快照。

## 2. 当前节点表（2026-11-06 09:06）

| 节点 | 口径 | 数量 | 时点 / 来源 |
|---|---|---:|---|
| 美中-FZH-DANEEY | available | **0** | 11-06 05:17 快照；11-06 09:06 前无新增流水 |
| 美中-FZH-DANEEY | intransit（通途聚合） | **405** | 同上 |
| 美中-FZH-DANEEY | waiting_shipment / defects | 0 / 0 | 11-06 05:17 |
| 美中-FZH-DANEEY-退货产品仓 | available | 0 | 11-06 05:17 |
| 波兰-FZHPoland-covers | available | 121 件 + 2PCS 10 套 + 3PCS 10 套（折 171 件） | 11-06 05:17（11-05 为 125） |
| 通途 WayfairCG-Cranbury仓（**通途账**） | available / intransit | **133 / 0** | 通途 stocksQuery 实时（11-06 09:06） |
| **Wayfair CG API — base SKU** | on_hand / available | **null / null（无 CG 仓位）** | 直接 API，快照 11-06 07:00:58 |
| **Wayfair CG API — `-2PCS`** | on_hand / available | **5 / 5 套**（Cranbury 0、McDonough 2、Perris 2、Romeoville 1） | 同上 |
| **Wayfair CG API — `-3PCS`** | on_hand / available | **0 / 0 套** | 同上 |
| CG 在途 | SKU 级 | **不可得** | 见 §6 |

> 套装折件仅作参考：`-2PCS` 5 套 = 10 件，`-3PCS` 0 套 = 0 件；这是换算值，不是上游给的件数。
> **CG 真正可售的是 5 套 2PCS（10 件）**；不是通途 CG 账的 133。

## 3. 2026-11-05 两笔关键流水（通途，操作人：仓库操作人）

| 时间 | 凭证类型 | 变动 | 结余 | 凭证号 |
|---|---|---|---:|---|
| 2026-11-05 09:09:50 | 采购单（02） | available **+91**；intransit **−91** | available 11→102；intransit 496→405 | `6464013595202611050000897094` |
| 2026-11-05 17:34:00 | 其他出库（06） | available **−102** | available 102→0 | `6464013595202611050074374170` |

对账：

- `11 + 91 − 102 = 0`（美中可用）
- `496 − 91 = 405`（美中在途）
- 91 的数量与历史 PO `PO021716`（91 件）一致；但该凭证字段只给通途入库凭证号，**未直接写 PO 号**，PO 归属需 `purchaseOrderQuery` 再证。
- **11-06 复核**：11-06 00:00 起，美中与 CG 账均无该 SKU 的新增流水；11-05 日终状态保持。

**102 的去向**：凭证类型是「其他出库」，不携带目的仓；CG 通途账没有 +102 入库，CG 账仍 133。因此只能确认“出了美中”，**不能在系统内确认“进了 CG”**；需要仓库/运营同事提供 CG 收货凭证或 Wayfair WSA 号。

## 4. 时间线（同 SKU）

| 日期 | 美中 available | 美中 intransit | 通途 CG 账 | Wayfair Castlegate（base / 套装） | 来源 |
|---|---:|---:|---:|---|---|
| 2026-10-22 05:17 | 36 + 待发 4 | 201 | 153 | base 无 Castlegate 行；导出仅 Dropship TX 31 | 10-22 库存备份；10-23 AllInventoryExport |
| 2026-10-23 05:17 | 34 | 496 | 153 | base 无 Castlegate 行；2PCS 9、3PCS 5 | 10-23 库存备份；10-23 AllInventoryExport |
| 2026-10-26（实时） | — | 496 | — | — | 2026-10-26 答复（R1） |
| 2026-11-05 05:17 | 11 | 496 | 133 | base 无仓位；2PCS 5、3PCS 1 | EN 快照 / CG API |
| 2026-11-05 日终 | **0** | **405** | 133 | base 无仓位；2PCS 5、3PCS 1 | 通途流水 |
| **2026-11-06 09:06** | **0** | **405** | **133** | **base null；2PCS 5、3PCS 0** | 11-06 快照 + 直接 CG API |

补充：`2026-10-22 10:32:23` 有一笔「采购单」把 **intransit +295**（201→496），采购操作人，凭证 `6464013595202610220001059276`。这是**在途增加**，不是实物入库；当前 405 是在 496 基础上扣掉 11-05 到货 91。

## 5. 运营同事的 120 与仓库同事的 91：不是同一批

- **91 已证**：2026-11-05 09:09:50 到美中，流水、结余、操作人、凭证齐全。
- **120 不可证**：
  - 本机通途库存备份最早 `2026-10-20`；库存变动抓取最早 `2026-10-21 13:48:41`；Wayfair `AllInventoryExport` 只有 `2026-10-23`。
  - `2026-10-22` 冻结快照：美中 36 可用 + 4 待发，在途 201，**没有 120 可用**。
  - 因此 10/5 的 120 既不能证明、也不能否定；它发生在所有保留数据之前。
- **CG 侧的旁证是负向的**：10-23 的 Wayfair 导出里，base SKU 只有 **Dropship**（Dropship TX 31），**没有任何 Castlegate 行**。如果 10/5 那 120 是发到 Castlegate 且挂在这个 part 下，Wayfair 自己的导出应当能看到；现在看不到，说明至少存在以下之一：
  1. 120 没有按这个 part 收货；
  2. 120 挂在别的 part / 别的池；
  3. 120 是 Dropship 或其他非 Castlegate 口径；
  4. 通途 CG 账的 153/133 是履约池记账，不是 Wayfair Castlegate 实际在库。

> 不能把「通途 CG 账 133」直接当作「Wayfair CG 在库」。两个口径在 10-23、11-05、11-06 都对不上。

## 6. CG 多件套与在途

### 6.1 CG API 的多件套映射（回应用户“可能是几件套、别的 SKU”）

`Wayfair CG Part` 中，MPLID `WWMA1260` 对应 **3 个供应商 part**：

| part_key | has_cg_position | warehouse_count | 11-06 CG API |
|---|---:|---:|---|
| TT0031038K0062927 | 0 | 0 | `available=null / on_hand=null`（无仓位） |
| TT0031038K0062927-2PCS | 1 | 4 | 5 套（Cranbury 0、McDonough 2、Perris 2、Romeoville 1） |
| TT0031038K0062927-3PCS | 1 | 6 | 0 套（全部仓 0） |

- EN 侧套装定义：`TJ#KS0156x2-001` = 2×`KS0156-NYBDSFH-52x52x5-BLACK`；`TJ#KS0156x3-001` = 3×。
- 直接拿 `WWMA1260`、`KS0156-NYBDSFH-52x52x5-BLACK`、`TJ#KS0156x2-001`、`TJ#KS0156x3-001` 作为 `skus` 查 CG API，**不返回 items**；CG 的 supplier part 是上面 3 个 TT 码。
- 因此：**CG 侧这个产品只看这 3 个 part，没有第 4 个多件套 SKU**；base 无 CG 仓位，套装才是 Castlegate 的实际持有单位。

### 6.2 通途在途

- **可得**：`erp2_stocks_stocksquery` / `stocksQuery` 的 `intransitStockQuantity`，按仓返回；当前美中 **405**。
- 这是**通途聚合在途**，不等于某张 PO 的未收量；PO 明细需 `purchaseOrderQuery` / `purchaseStockQuery` 另查。
- 历史证据：10-22 为 201；10-22 10:32 一笔「采购单」+295 到 496；11-05 09:09 到货扣 91 到 405。

### 6.3 Wayfair CG 在途

**当前拿不到 SKU 级在途**，依据：

| 上游 operation | 粒度 | 结论 |
|---|---|---|
| `inventorySummaryList` | SKU × 仓（仅已有 CG 仓位的 part） | base 无仓位，返回 null |
| `getCastleGateWarehouseShippingAdvice` | SKU × 运单 | **实测是 CG→客户出库**：`products{sku,partNumber,quantityOrdered,quantityShipped}`；`shipFrom=CG`、`shipTo=客户`；不是入仓 |
| `getCastleGatePurchaseOrders` | SKU × 客户订单 | 有 `products`（SKU/qty），但 `CS...` 是客户订单；无 `poNumbers` 时上游 101 |
| `inboundOrder`（CGF） | 理论上 SKU + 数量 + ETA | 生产 OPEN/COMPLETED/CANCELLED 全 null；无 CGF 入仓单 |
| `inboundOrderList` | 入仓单 | `PERMISSION_DENIED` 102；需向 Wayfair 申请权限 |
| `consolidatedBolDocument` | BOL | `PERMISSION_DENIED` 102 |
| `castlegatePurchaseOrders`（新版） | 理论上 PO × SKU | 上游返回 null（NonNull 违约），当前不可用 |
| `findSpoMovementsEvents` | SPO 事件 | null；本 SKU 无数据 |
| `inventoryAdjustmentList` | SKU × 事件 | 2026 年 17 条，本 SKU 家族 0 条；看不到 91/102 收货 |
| `inventoryTransferList` | 仓间调拨 | 不是供应商在途 |

> **2026-11-06 修正**：早期契约说 WSA“只有运单总量、无 SKU 明细”；实测 `products` 是 SKU 级，但方向是 **CG→客户出库**，不是入仓。入仓入口 `inboundOrderList`/BOL 当前无权限。完整调研见 [wayfair-cg-inbound-api-research](wayfair-cg-inbound-api-research.md)。

- 代理的 `/v1/accounts/{account}/inbound/query` 固定返回 `501 capability_unavailable`。
- EN 的 `wayfair_cg_txn.parquet` 目前只有 **2 行、2026-09-29、无本 SKU**；实时 `inventoryAdjustmentList` 对本 SKU 家族也是 0 条，不能用来验证 10/5 的 120 或 11-05 的 102。
- 可行替代：`当日入仓收货 ≈ ΔCG on_hand + 当日 WSA 出库`；再与通途发往 CG 的发出量比较得到在途估计（详见调研文档 §3）。

## 7. 给补货系统的数据契约

建议每个库存节点统一成一行：

```text
sku / node / basis(available|intransit|po_open|cg_on_hand) / qty / as_of / source / run_id
```

必须遵守：

1. **通途 `intransit` 是聚合口径**，不要和 `available` 直接相加当作“可发”；在途与 PO 开单量按 B_min/B_max 双账，不直接相加（沿用 2026-10-23 结论）。
2. **通途 CG 账 ≠ Wayfair CG 权威**。`WayfairCG-Cranbury仓` 的 133 只能标 `source=tongtool_cg_ledger`，不能标 `cg_on_hand`。
3. **CG 必须按多件套 part 查**：base `has_cg_position=0` 要标 `null/unknown`，**不能填 0**；实际持有单位是 `-2PCS` / `-3PCS`。11-06 可售 = 5 套 2PCS（10 件）+ 0 套 3PCS。
4. **不要混算 base 件与套装**：套装的 `qty` 是套数，折件要乘 2 / 3，并保留 `uom=set` 与 `pieces=2|3`。
5. **CG 入仓无 SKU 级在途**。WSA 是 CG→客户出库（SKU 级），不是入仓；不要把 WSA 当在途。入仓在途只能标 `inferred`，或 `cg_transit_unknown`。
6. **同日流水要覆盖 05:17 快照**。11-05 的 C refresh xlsx（美中 11 / 在途 496 / CG 账 133）是 05:17 口径；11-05 17:34 后美中已是 0 / 405。
7. 11-05 的 **102** 建议先记为 `in_transit_to_cg(qty=102, source=manual_claim, evidence=pending)`，**不要**记成 CG 在库，也**不要**只用 91（原有 11 也被一起出库了）。

## 8. 证据与复现

### 8.1 EN REST（生产 `erpnext.vilavi.cn`，只读）

- `Tongtool Stock Latest`，`sku like TT0031038K0062927%`；run_id `20261106T051740`，snapshot_at `2026-11-06 05:17:40`。
- `Wayfair CG Stock Latest`，`sku like %TT0031038K0062927%`；run_id `20261106T072058`，snapshot_at `2026-11-06 07:20:59`。
- `Wayfair CG Part`，`part_key like %TT0031038%`，返回 3 行（见 §6.1）。

### 8.2 直接 Wayfair CG API（通过 `https://wayfair-api.vilavi.cn`）

- `POST /v1/accounts/centrade/inventory/query`，`mode=snapshot`，`skus=[base,-2PCS,-3PCS,WWMA1260,KS0156...,TJ#...]`。
- `meta`：`source=snapshot`，`fetched_at=2026-11-05T23:00:58Z`，`age_seconds≈7603`，`stale=false`，`snapshot_run_id=774f6c9340f9de927dc1563dbb15e3b5`。
- `items`：base `available=null/on_hand=null`；2PCS 5 套；3PCS 0 套；其余 SKU 无 item。
- `mode=live` 本轮 90 秒内未返回（不降级、不伪报实时），因此以每日快照为准。

### 8.3 EN 服务器 parquet

- `/home/frappe/fzh-inventory/stock_change.parquet`：范围 `2026-10-21 13:48:41` → `2026-11-04 18:20:55`，7,443 行；本 SKU 98 行。
- `/home/frappe/fzh-inventory/wayfair_cg_stock_total.parquet`：`2026-10-29` 起按日快照。
- `/home/frappe/fzh-inventory/wayfair_cg_stock_warehouse.parquet`：同上的分仓明细。
- `/home/frappe/fzh-inventory/wayfair_cg_txn.parquet`：只有 2 行（`2026-09-29`），无本 SKU。

### 8.4 实时通途（在 EN 服务器执行，本机 IP 未进白名单）

- `stocksChangeDetailQuery`，`warehouseName=美中-FZH-DANEEY`，`updatedDateFrom=2026-11-04 00:00:00`：命中 4 行（含 §3 两笔）。
- `stocksChangeDetailQuery`，美中 / CG，`updatedDateFrom=2026-11-06 00:00:00`：均无本 SKU 命中。
- `stocksQuery`，`warehouseName=WayfairCG-Cranbury仓`，第 1 页：本 SKU `available=133`、`intransit=0`。

### 8.5 本地参考

- `D:/Work/fzh-order-store/analysis/C-refresh-20261105/通途库存_A337_v14_refresh_2026-11-05_v2.xlsx`（as_of 11-05 05:17）。
- `D:/Work/尹/wayfair/AllInventoryExport_2026-10-23 (1)(1).csv`（base 仅 Dropship TX 31；Castlegate 只有套装）。
- `D:/Work/库存备份/2026-10-22`、`2026-10-23`（14 仓 JSONL）。

## 9. 限制与未核实

1. **10/5 的 120 不可核实**：所有保留数据从 10/20–10/21 开始；10/22 美中已只有 40（含待发）。
2. **CG API 历史只到 10/29**：之前只有 10/23 的手工 `AllInventoryExport`；CG 交易流水抓取为空。
3. **「其他出库 -102」的目的地不在凭证里**：只能确认离开美中；是否到 CG、是否已收货，需要外部凭证（WSA/收货单）。
4. **base SKU 在 Wayfair 无 Castlegate 仓位**：是无仓位、未上架 Castlegate、还是 part 口径变化，当前数据无法区分。
5. **CG API live 模式本轮未返回**：只能使用每日快照；快照 age≈2.1h。
6. **本机不能直连通途 API**（524 未白名单）：实时查询必须在 EN 服务器或已白名单机器执行；商户级限流 5 次/分钟。

## 10. 建议的下一步（需业务确认）

1. 让仓库/运营同事提供 **102 件**的 CG 收货凭证或 Wayfair WSA 号；拿到后把 102 落到 CG 在库或在途，闭环。
2. 让运营同事提供 **10/5 的 120** 的发货凭证 / WSA / 目的仓；没有凭证就只能标 `unverified`，不能进补货净额。
3. 补货系统按多件套口径取 CG：base 标 unknown；`-2PCS` 5 套、`-3PCS` 0 套；**不要**把 91 和 120 相加，也**不要**把通途 CG 账 133 当 Wayfair 在库。
4. 若要长期解决 CG 在途，需新增 **WSA 运单级探测**（仍无 SKU 级），或推动 Wayfair 开放 `inboundOrder` 的 lineItems；在此之前 `cg_transit` 只能标 unknown。
