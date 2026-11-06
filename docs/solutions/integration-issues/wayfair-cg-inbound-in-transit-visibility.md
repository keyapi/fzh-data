---
okf: v0.1
type: Solution
title: Wayfair CG 在途不可直接查 —— WSA 是出库，用「Δ在库 + WSA 出库」反推收货
description: Wayfair Castlegate 的 WSA 是 CG 发往客户的出库建议（EDI 945），不是供应商入仓单；入仓/在途没有可用的 SKU 级 API。用每日 CG 在库快照 + WSA 出库量反推收货，再与通途发往 CG 的发出量比较，得到可复核的在途估计。
module: platform_account_reconciliation
date: 2026-11-06
last_updated: 2026-11-06
category: integration-issues
problem_type: integration_issue
component: api-gateway
severity: high
symptoms:
  - "CG API 只有在库，看不到已发往 CG、尚未入仓的在途"
  - "WSA 被误当成入仓单：实际 shipFrom=CG、shipTo=客户，单量 1–2 件"
  - "inboundOrderList / consolidatedBolDocument 返回 PERMISSION_DENIED 102"
  - "castlegatePurchaseOrders 上游返回 null；getCastleGatePurchaseOrders 无 poNumbers 报 101"
root_cause: api_capability_gap
resolution_type: workaround
tags: [wayfair, castlegate, wsa, inbound, in-transit, inventory, api]
related_components: [wayfair-api-proxy, tongtool_integration]
---

# Wayfair CG 在途不可直接查

## Problem

补货系统需要回答：**已经发往 Wayfair CG、但 CG 还没入仓的货还有多少？** CG API 的 `inventorySummaryList` 只给当前 on-hand / available，看不到“在途”。如果直接按 0 处理，会低估供给；如果拿通途 `WayfairCG-Cranbury仓` 的 133 当 CG 在库，又会把履约池记账当成真实库存。两种都会把补货判断带偏。

## Symptoms

- CG API 的 on-hand 与通途 CG 账长期对不上：实测 CG API 只有 `-2PCS` 5 套（10 件）+ `-3PCS` 0 套，base SKU 无 CG 仓位；通途 CG 账显示 133。
- 把 WSA 当入仓单会得到相反结论：WSA 的 `shipFrom` 是 CG 仓、`shipTo` 是客户，单量都是 1–2 件，属于客户发货。
- 入仓类 operation 要么无数据、要么无权限：`inboundOrder` 三状态全 null；`inboundOrderList` / `consolidatedBolDocument` 返回 102。
- PO 类 operation 也不可用：`castlegatePurchaseOrders` 上游返回 null；`getCastleGatePurchaseOrders` 不带 `poNumbers` 报 `ErrorCode 101`。

## What Didn't Work

逐项在 Wayfair Supplier GraphQL（生产，supplierId=80197）实测：

| Operation | 结果 |
|---|---|
| `inventorySummaryList` | 只有在库；base 无 CG 仓位 |
| `inventoryAdjustmentList` | 2026 全年 17 条，本 SKU 家族 0 条；看不到入仓收货 |
| `getCastleGateWarehouseShippingAdvice` (WSA) | **SKU 级出库**：`products{sku,partNumber,quantityOrdered,quantityShipped}`；`shipFrom=CG`、`shipTo=客户`；不是入仓 |
| `getCastleGatePurchaseOrders` | `CS...` 是客户订单（与 WSA 同一张单）；无 `poNumbers` 时 101 |
| `castlegatePurchaseOrders`（新版） | 上游 null（NonNull 违约），多种过滤仍失败 |
| `inboundOrder`（CGF） | OPEN/COMPLETED/CANCELLED 全 null |
| `inboundOrderList` | `PERMISSION_DENIED` 102 |
| `consolidatedBolDocument` | `PERMISSION_DENIED` 102 |
| `findSpoMovementsEvents` | null |
| `inboundStockPurchaseOrderStats` | 生产 schema 不存在 |
| `inventoryTransferList` | 仓间调拨，不是供应商在途 |

结论：**当前没有可直接使用的 SKU 级入仓在途 API**。

## Solution

用三本账做可复核的推断：

```text
当日入仓收货 ≈ (当日 CG on_hand − 前一日 CG on_hand) + 当日 WSA 出库量
累计在途估计 = 累计通途发往 CG 数量 − 累计入仓收货
```

- `on_hand` 取 Wayfair CG API（用 on_hand，不用 available，避免 reserved 干扰）。
- WSA 取 `getCastleGateWarehouseShippingAdvice.products[].quantityShipped`，按 `wsaId` 去重后按日汇总。
- 通途发出量取「其他出库 / 调拨」到 CG 的数量；06 其他出库凭证不写目的仓，必须人工确认是发 CG。
- 结果标 `confidence=inferred`，不能冒充 API 在途；未知就写 unknown，不要写 0。

实测校验（2026-10-29 → 11-06）：

| 项 | 2PCS | 3PCS | 合计 |
|---|---:|---:|---:|
| CG on_hand 10-29 | 8 | 4 | 12 |
| CG on_hand 11-06 | 5 | 0 | 5 |
| Δ on_hand | -3 | -4 | **-7** |
| 同期 WSA 出库 | 3 | 3 | **6** |
| 反推入仓收货 | 0 | -1 | **≈ -1** |

反推收货接近 0，没有 91/102 件级别的入仓。若 102 件按 2PCS 套入仓约 51 套、按 3PCS 套约 34 套；91 件约 45/30 套，on_hand 应明显跳升，实际没有。因此这批货要么还在途，要么挂在别的 part/仓，要么去了非 Castlegate 的 CG 仓；不能算成 CG 在库。

## Why This Works

这是一个库存守恒式：期末在库 = 期初在库 + 入仓收货 − 出库。WSA 是完整的 SKU 级出库账，CG 每日快照给出期末在库，两者相减就是入仓收货。它不依赖缺失的入仓 API，也不依赖通途 CG 履约池账；代价是只能给推断值，且需要每日快照与 WSA 都完整。

## Prevention

- 不要把 WSA 当入仓单：先看 `shipFrom/shipTo`，再看单量是否为客户订单级别。
- 不要把通途 `WayfairCG-Cranbury仓` 的余额当 Wayfair 在库；它只能标 `source=tongtool_cg_ledger`。
- 补货系统按 part 分开记：base 无 CG 仓位标 unknown；`-2PCS` / `-3PCS` 按套数记，折件要乘 2/3。
- 在途未知不要写 0；写 `inferred` 或 `unknown`，并保留每日快照 / WSA 的 run id。
- 向 Wayfair 申请 `inboundOrderList` 与 `consolidatedBolDocument` 只读权限并复测；同时让运营/仓库提供 CG 收货凭证、WSA 或 ASN。

## Related

- [TT0031038K0062927 库存节点核对](../../research/supply-chain/2026-11-05/tt0031038k0062927-node-reconciliation.md)
- [Wayfair CG 入仓/在途 API 调研](../../research/supply-chain/2026-11-05/wayfair-cg-inbound-api-research.md)
- `wayfair-api-proxy/docs/contract.md`（早期探测记录；“WSA 只有总量”已被本次实测修正为 SKU 级出库）
- `docs/solutions/architecture-patterns/wayfair-cg-stock-table-and-parquet-grain.md`
