---
okf: v0.1
type: Research-Notes
title: Wayfair CG 入仓/在途 API 调研（2026-11-06）
description: 逐个验证 Castlegate 入仓与在途 operation；WSA 实为 CG 出库；给出可落地的间接在途口径与实测校验
date: 2026-11-06
tags: [wayfair, castlegate, inbound, in-transit, api, research, inventory]
---

# Wayfair CG 入仓/在途 API 调研

> **问题**：Wayfair CG API 能查现有库存，但能不能查“在途/入仓”？如果查不到，补货系统怎么拿到可信的在途？
> **方法**：Wayfair Supplier GraphQL（生产，supplierId=80197）schema introspection + 真实查询；只读，不改任何生产数据。
> **时间**：2026-11-06。

## 0. 结论（TL;DR）

1. **当前没有可直接使用的 SKU 级“入仓在途”API。** 逐个实测：`inboundOrder`（CGF）三状态全 null；`inboundOrderList` 与 `consolidatedBolDocument` 权限 102；`castlegatePurchaseOrders` 上游返回 null 错误；`findSpoMovementsEvents` null；`inboundStockPurchaseOrderStats` 不在生产 schema。
2. **WSA 不是入仓，是 CG→客户的出库。** `getCastleGateWarehouseShippingAdvice` 实际有 SKU 级 `products{sku, partNumber, quantityOrdered, quantityShipped}`；实测 `shipFrom=CG 仓`、`shipTo=客户`，单量都是 1–2 件，属于客户发货（EDI 945），不是补货入仓。
3. **`getCastleGatePurchaseOrders` 也不是入仓 PO。** 它的 `CS...` 单号是 CG 履约的客户订单：`shipFrom=CG`、`shipTo=客户`，`products` 是客户订单行；不是供应商补货 PO。
4. **`inventoryAdjustmentList` 看不到这批货的入仓。** 2026 全年 17 条调整（Cycle Count / Transfer），本 SKU 家族 0 条；不能用它证明 102/91 已收货。
5. **可行的替代口径**：`入仓收货 ≈ ΔCG 在库 + WSA 出库量`。用每日 CG 在库快照 + WSA 日发货量反推；再和通途“发往 CG”的发出量比较，得到**在途估计**（不是 API 直接值）。
6. **实测校验（10-29 → 11-06）**：CG 在库 12 → 5（Δ=-7）；同期 WSA 出库 6；反推收货 ≈ -1（无大额入仓）。**91/102 没有在 CG Castlegate 形成库存**；通途 CG 账的 133 不能当 Wayfair 在库。
7. **建议**：补货系统用“CG API 在库 + WSA 出库 + 通途发出量”三本账；向 Wayfair 申请 `inboundOrderList` / BOL 权限并复测；同时让仓库同事提供 CG 收货凭证 / WSA / ASN。不要把“在途未知”写成 0。

## 1. Operation 实测矩阵

| Operation | 实测结果 | 粒度 | 方向 | 能否给在途 |
|---|---|---|---|---|
| `inventorySummaryList` | ✅ 可用 | SKU × 仓 | 在库 | ❌ 只有在库 |
| `inventoryAdjustmentList` | ✅ 可用但 2026 全年 17 条，本 SKU 0 条 | SKU × 事件 | 调整 | ❌ 无本 SKU 收货记录 |
| `getCastleGateWarehouseShippingAdvice` | ✅ 可用；有 `products` SKU 级 | SKU × 运单 | **CG → 客户（出库）** | ❌ 不是入仓 |
| `getCastleGatePurchaseOrders` | ✅ 带 `poNumbers` 可用；无 `poNumbers` 时上游 101 | SKU × 客户订单 | **CG 客户订单** | ❌ 不是入仓 PO |
| `castlegatePurchaseOrders`（新版） | ❌ 上游返回 null（NonNull 违约） | 理论上 PO × SKU | 未知 | ❌ 不可用 |
| `inboundOrder`（CGF） | ✅ 可调；OPEN/COMPLETED/CANCELLED 全 **null** | CGF 柜 × SKU | 入仓（海运柜） | ❌ 无数据 |
| `inboundOrderList` | ❌ `PERMISSION_DENIED` 102 | 入仓单 | 入仓 | ❌ 未授权 |
| `consolidatedBolDocument` | ❌ `PERMISSION_DENIED` 102 | BOL | 运输单 | ❌ 未授权 |
| `findSpoMovementsEvents` | ✅ 可调但返回 null | SPO 事件 | 入仓/库存变动 | ❌ 无数据 |
| `inboundStockPurchaseOrderStats` | ❌ 生产 schema 不存在 | — | 统计 | ❌ 不可用 |
| `inventoryTransferList` | ✅ 可用 | 仓间调拨 | 仓间 | ❌ 不是供应商在途 |

## 2. 关键证据

### 2.1 WSA 是出库，不是入仓

`getCastleGateWarehouseShippingAdvice(wsaIds:"4AB21C63-...")` 的真实返回：

```json
{
  "wsaId": "4AB21C63-0C73-5C9A-AAAC-C9FDA62BC0D4",
  "poNumber": "CS688432482",
  "shipDate": "2026-10-26 08:05:42.186+00:00",
  "warehouseId": 323011,
  "totalQuantity": 1,
  "carrierCode": "FDEG",
  "shipFrom": {"name": "CG warehouse (GA)", "city": "Port Wentworth", "state": "GA"},
  "shipTo": {"name": "customer", "city": "<redacted>", "state": "MS"},
  "products": [{"sku": null, "partNumber": "TT0031038K0062927-3PCS",
                "quantityOrdered": 1, "quantityShipped": 1}]
}
```

- `shipFrom` 是 CG 仓，`shipTo` 是客户 → **出库**。
- `products` 是 SKU 级，含 ordered/shipped；可用于 CG 销量/消耗，不是入仓在途。
- 本 SKU 家族 2026-09-01 至 11-06 共 265 个唯一 WSA，单量全部是 1–2 件，没有 ≥10 件的补货批次。

### 2.2 `getCastleGatePurchaseOrders` 是客户订单

`getCastleGatePurchaseOrders(poNumbers:["CS688432482"])` 返回：

```json
{"poNumber":"CS688432482","poDate":"2026-10-25 19:40:06+00:00",
 "warehouse":{"name":"CastleGate GA WH25"},
 "products":[{"sku":"WWMA1260","partNumber":"TT0031038K0062927-3PCS","quantity":"1","isCancelled":false}]}
```

- 与上一节 WSA 是同一张单：客户订单从 CG 仓发往客户。
- `orderType`/`scheduledDeliveryDate` 为 null；不是补货 PO。
- 无 `poNumbers` 时上游返回 `ErrorCode 101`；带 `poNumbers` 才可用。

### 2.3 入仓入口全部不可用

- `inboundOrder(supplierId:80197,status:OPEN|COMPLETED|CANCELLED)` → 三者都 `null`；判断 Centrade 没有 CGF（CastleGate Forwarding 海运柜）入仓单。
- `inboundOrderList` → `PERMISSION_DENIED` 102；这是最接近“入仓单”的入口，但当前 key 无权。
- `consolidatedBolDocument` → `PERMISSION_DENIED` 102。
- `castlegatePurchaseOrders` → 上游 `SupplierCastlegatePurchaseOrdersPagedConnection` 返回 null（NonNull 违约），试了多个 warehouseIds / hasResponse / 日期窗 / sortBy 仍失败。
- `findSpoMovementsEvents` → null（无论 supplierId / supplierPartNumber 是否有值）。
- `inventoryAdjustmentList` 2026 全年仅 17 条，且本 SKU 家族 0 条 → 没有可用的入仓收货流水。

## 3. 可行的间接在途口径

### 3.1 公式

对每个 CG part（`-2PCS` / `-3PCS`；base 无 CG 仓位）：

```text
当日入仓收货 ≈ (当日 on_hand - 前一日 on_hand) + 当日 WSA 出库量
累计在途估计 = 累计通途发往 CG 数量 - 累计入仓收货
```

- `on_hand` 取 Wayfair CG API（不是 available，避免 reserved 干扰）。
- `WSA 出库量` 取 `getCastleGateWarehouseShippingAdvice.products[].quantityShipped`，按 `wsaId` 去重后按日汇总。
- `通途发往 CG` 取通途「其他出库 / 调拨」到 CG 的发出量；若凭证类型是 06 其他出库，**目的地不在凭证里**，必须人工确认是发 CG。
- 结果标 `confidence=inferred`，不能冒充 API 在途。

### 3.2 实测校验（2026-10-29 → 11-06）

| 项 | 2PCS | 3PCS | 合计 |
|---|---:|---:|---:|
| CG on_hand 10-29 | 8 | 4 | 12 |
| CG on_hand 11-06 | 5 | 0 | 5 |
| Δ on_hand | -3 | -4 | **-7** |
| 同期 WSA 出库 | 3 | 3 | **6** |
| 反推入仓收货 | 0 | -1 | **≈ -1** |

- 反推收货接近 0（-1 属时间边界/盘点误差），**没有 91 或 102 件级别的入仓**。
- 如果 102 件按 2PCS 套入仓 ≈51 套、按 3PCS 套入仓 ≈34 套；91 件 ≈45/30 套。on_hand 会明显跳升，实际没有。
- 因此：**91/102 没有在 CG Castlegate 形成库存**；它们要么还在途，要么挂在别的 part/仓，要么去了非 Castlegate 的 CG 仓。
- 通途 CG 账 133 是履约池记账，不是 Wayfair Castlegate 在库；不能用于补货净额。

> 注意：base SKU `TT0031038K0062927` 在 CG 无仓位（`has_cg_position=0`，API 返回 null）。如果 91/102 以 base 件入仓，Castlegate 应当出现 base 仓位；现在没有，说明也没有以 base 件入 Castlegate。

## 4. 对补货系统的建议

1. **CG 在库**：用 CG API 的 `on_hand/available`，按 part 分开：
   - base：`null/unknown`；
   - `-2PCS`：5 套（10 件）；
   - `-3PCS`：0 套。
2. **CG 出库/销量**：用 WSA `quantityShipped`，按日汇总；这是 SKU 级、可信的 CG 销售/消耗，不是在途。
3. **CG 入仓收货**：用 `Δon_hand + WSA出库` 反推；标 `inferred`，并保留每日快照与 WSA 原始 run id。
4. **CG 在途**：`累计通途发往 CG − 累计反推收货`；当前对 102 件应标 `in_transit_to_cg≈102, evidence=pending`，不要记为 CG 在库。
5. **不要用通途 CG 账 133** 作为 Wayfair 在库；它只能作为“通途侧履约池”参考。
6. **权限/人工兜底**：向 Wayfair 申请 `inboundOrderList` 与 `consolidatedBolDocument` 权限并复测；同时让运营/仓库同事提供 CG 收货凭证、WSA 或 ASN。若 Wayfair 仍不开放，Partner Home 的入仓/收货报表需人工定期导出。

## 5. 复现与数据点

- 生产 GraphQL：`https://api.wayfair.io/v1/supplier-order-api/graphql`，supplierId `80197`。
- Token：Wayfair SSO client_credentials（凭证在代理 VPS `/etc/wayfair-api-proxy/env`，不落库）。
- WSA：`getCastleGateWarehouseShippingAdvice(limit, offset, sortOrder:DESC)`；无 `fromDate` 时可分页；`fromDate` 当前触发上游 101，不要用。
- PO：`getCastleGatePurchaseOrders(poNumbers:[...])`；无 `poNumbers` 触发 101。
- 入仓：`inboundOrder(supplierId:80197,status:ENUM,paginate:{limit,offset})`；`inboundOrderList` 102。
- CG 在库快照：`Wayfair CG Stock Latest` / `wayfair_cg_stock_total.parquet`（10-29 起）。
- 本 SKU WSA 聚合：2026-09-01 至 11-06，265 个唯一 WSA；2PCS 7 件、3PCS 18 件。

## 6. 来源

- [Truto — Connect Wayfair to ChatGPT: Sync Catalog, Orders, and Inventory](https://www.truto.one/blog/connect-wayfair-to-chatgpt-sync-catalog-orders-and-inventory/)（WSA 含 ordered vs shipped；CastleGate 用 WSA 代替 dropship ASN）
- [Truto — Handle Multi-Channel Fulfillment and WSAs](https://www.truto.one/blog/connect-wayfair-to-claude-handle-multi-channel-fulfillment-and-wsas/)（WSA 的 fulfillment item / tracking）
- [Endless Commerce — Wayfair EDI Requirements (2026)](https://endlesscommerce.com/edi/requirements/wayfair/)（945 Warehouse Shipping Advice；CastleGate 出库口径）
- [Wayfair API 开发集成（微信公众号）](http://mp.weixin.qq.com/s?__biz=MzY4NTMwODYyNA==&mid=2247483809&idx=1&sn=3285f92016da6f2f962b39f3ee78b305)（`getCastleGateWarehouseShippingAdvice` 用于确认 CG 订单发货）
- [Odoo wayfair_store_management](https://apps.odoo.com/apps/modules/17.0/wayfair_store_management)（Wayfair operation 列表）
- 本地契约：`wayfair-api-proxy/docs/contract.md`（CGF inbound / PO / WSA 的早期探测记录；其中“WSA 只有总量”已被本次实测修正为 SKU 级出库）
