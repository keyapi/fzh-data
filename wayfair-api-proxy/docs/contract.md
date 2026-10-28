---
okf: v0.1
type: Reference
title: Wayfair 上游契约（已探测）
description: 2026-10-28 从美国 VPS 实测的 OAuth、GraphQL operation、字段与当前授权状态（已脱敏）
tags: [wayfair, contract, graphql, oauth, castlegate]
---

# Wayfair 上游契约（已探测）

> 探测时间：2026-10-28（美国 Vultr VPS 发出）。只记录 schema、operation 与字段映射，
> 不记录 client id/secret、token、供应商 ID 值或完整业务 payload。

## 认证

| 项 | 值 |
|----|----|
| Token 端点 | `POST https://sso.auth.wayfair.com/oauth/token` |
| 请求体 | JSON：`grant_type=client_credentials`、`client_id`、`client_secret`、`audience=https://api.wayfair.com/` |
| 响应 | `access_token`、`token_type=Bearer`；实测 `expires_in=86400` |
| 使用 | `Authorization: Bearer <token>` |

实测结果：`200`，token 可用于后续 GraphQL 调用。文档对有效期存在 1h/12h/24h 多种说法，
以响应里的 `expires_in` 为准（本项目按响应值缓存，并提前 5 分钟刷新）。

## 库存查询

| 项 | 值 |
|----|----|
| 端点 | `https://api.wayfair.io/v1/supplier-order-api/graphql` |
| Operation | `inventorySummaryList` |
| 所需权限 | `read:inventory_visibility` |
| 参数 | `supplierId: Int!`、`filter: InventoryFilterInput`、`page: InventoryPageInput` |
| filter | `supplierPartNumbers: [String!]`（1–100 个）、`warehouseId: Int` |
| 分页 | `page.first` 1–100（默认 50）、`page.after` 游标；`pageInfo.hasNextPage/endCursor` |

响应结构：

```graphql
inventorySummaryList {
  pageInfo { hasNextPage endCursor }
  edges { node {
    supplierPartNumber
    sku
    productName
    inventoryPosition {
      castleGate {
        onHandQty
        onHand {
          allocatedQty
          unreconciledQty
          inStockQty
          inStock {
            fulfillableQty
            unfulfillableQty
            unfulfillable { expiredQty heldQty unpickableQty onTransferQty }
          }
        }
        warehouses { warehouseId onHandQty onHand { ...同结构 } }
      }
      physicalRetail { ...同结构 }
    }
  } }
}
```

字段含义（官方定义）：

- `onHandQty`：CastleGate 在库总量。
- `allocatedQty`：已被订单占用、尚未发货。
- `unreconciledQty`：已做调整但仍在处理缓冲区内。
- `inStockQty`：在库或在调拨中，不含占用/未对账。
- `fulfillableQty`：可拣货、可分配的库存。
- `unfulfillableQty`：不可拣（过期、冻结、待检、调拨中等的合计）。
- `unfulfillable` 细分：`expiredQty`、`heldQty`、`unpickableQty`、`onTransferQty`。
- `warehouses[].warehouseId`：Wayfair 仓库或 DropShip 子供应商 ID。

## 内部模型映射

| 内部字段 | 上游字段 |
|----------|----------|
| `sku` | `node.supplierPartNumber`（我们的物料号），缺失时回退 `node.sku` |
| `wayfair_sku` | `node.sku`（Wayfair 产品号，如 `WWMA…`） |
| `warehouse` | `castleGate.warehouses[].warehouseId`；无仓库明细时用 `CG` |
| `on_hand` | 仓库级 `onHandQty`；无仓库明细时用 CastleGate 聚合 `onHandQty` |
| `available` | `inStock.fulfillableQty` |
| `reserved` | `onHand.allocatedQty` |
| `unavailable` | `inStock.unfulfillableQty` |

数量为 `null` 表示上游未返回该维度，**不等于 0**。仓库级明细缺失时，不把聚合值重复摊到
各仓库，避免求和重复计算。

## 当前授权状态（阻塞点）

| 探测 | 结果 |
|------|------|
| 生产 token | `200` |
| 生产 GraphQL `{ __typename }` | `200` |
| 生产内省 | 明确拒绝（introspection not allowed） |
| 生产 `inventorySummaryList` | `200` + `The provided client is not authorized to use this operation` |
| 沙箱端点 + 生产 token | `401`（沙箱需要独立的 Sandbox Access Token） |

结论：operation 与字段存在且请求格式正确，**应用尚未获得 `read:inventory_visibility`
生产权限**。按官方流程，生产权限由 Developer Portal 的 sandbox 测试逐步解锁：

1. 拥有 Partner Home API 角色的管理员登录 `developer.wayfair.io`。
2. 在 Application Management → 对应应用 → Permissions 查看/勾选已解锁权限。
3. 在 Overview 选择 CastleGate Inventory On-Hand API → Test in Sandbox，用 Sandbox
   Access Token 跑通一次查询。
4. 通过后生产权限才会解锁；再重跑 `snapshot.py --account centrade` 验证真实数据。

具体操作与可直接运行的脚本见 [sandbox-test.md](sandbox-test.md)。

### 2026-10-28 后续验证（已解除）

- 改用新建的专用应用（Sandbox + Production），不再使用 Lingxing 命名的应用。
- 用 Sandbox 应用的 client 凭证向同一 SSO 换取 token，直接请求沙箱 URL，返回 8 个节点，
  说明 sandbox 测试可编程完成，不一定需要手工把 token 拷进 Postman。
- 用新 Production 应用凭证请求生产 `inventorySummaryList`，按真实 CG SKU 过滤返回
  在库、可售、不可售与分仓明细（`hasNextPage` 为真，说明需要分页）。
- 结论：Inventory Visibility 生产权限**已实际可用**。仍保持 capability 关闭，直到完成
  一次真实快照并与 Partner Home 对账。

## CastleGate 其他只读 operation（2026-10-28 实测）

| Operation | 粒度 | 已确认字段 | 生产可读 |
|-----------|------|-----------|----------|
| `inventorySummaryList` | SKU × 仓库 | 见上 | ❌ 缺 `read:inventory_visibility` |
| `getCastleGatePurchaseOrders` | PO 头 | `id`、`poNumber`、`poDate`、`orderType`、`orderId`、`scheduledDeliveryDate`、`supplierId`、`supplierName`、`supplierCity/State/Address1`、`warehouse { ... }`、`shipTo { ... }` | ✅ 返回真实 PO |
| `getCastleGateWarehouseShippingAdvice` | 运单/柜 | `wsaId`、`poNumber`、`clientNumber`、`retailerOrderNumber`、`totalQuantity`、`shipDate`、`actionDate`、`carrierCode`、`shipSpeed`、`warehouseId`、`shipTo/shipFrom`、`packages { packageWeight }` | ✅ 返回真实 WSA |
| `inboundStockPurchaseOrderStats` | 统计 | `id`、`suId`、`stockPurchaseOrderId`、`totalUnits`、`status`、`completedDate` | ✅ 可查，但当前返回空列表 |
| `purchaseOrders` | 通用/DropShip PO | `warehouse`、`scheduledDeliveryDate`、`supplierName/City/State/PostalCode` | ✅（与 CG 预测无关，未采用） |

结论：

- **PO / WSA 不需要新权限**，很可能正是领星当年 sandbox 测试覆盖的部分；可直接用于在途分析。
- PO 只有**头级**字段，WSA 只有**运单级**合计；两层都拿不到 SKU 级在途数量。
- `inboundStockPurchaseOrderStats` 是最接近 SKU 级在途的查询（字段含 `totalUnits`），但当前为空，
  可能需要筛选参数（参数名未确认）或只覆盖特定状态的 PO。
- `unfulfillable.onTransferQty` 是仓间调拨，不是供应商在途，不能当 inbound 用。

### 建议开通组合

一次性在 Developer Portal 检查/勾选：**Inventory Visibility (On-Hand) + CastleGate Purchase
Orders + CastleGate Warehouse Shipping Advice**。前两项已可用，只有 On-Hand 需要 sandbox 解锁。
不要开任何 acknowledge / inventory feed / ship 等写权限。

注意：PO 数据里的 `supplierId` 是 NJ/CA 等 CG 仓库的子供应商 ID；`inventorySummaryList`
需要的是 **parent supplier ID**（Partner Home 账号级），两者不能混用。

### 写权限的取舍（尚未实现）

| 未来场景 | 需要的写能力 | 判断 |
|----------|--------------|------|
| 我们系统自动向 CG 提交入库/发货（类 FBA） | WSA 提交 / ASN，可能含 PO 确认 | 需要时单独开、单独 sandbox；首期不做 |
| 自动化 CG 补货（SPO 创建/确认） | PO 创建/acknowledge | 需要时再评估，避免与 Partner Home 流程冲突 |
| DropShip 自发货（接单/发货/回传追踪） | 订单 acknowledge + ship | 仅做自发货才需要 |
| 非 CG 的自管库存同步 | inventory / productInventory feed | **CG 库存由 Wayfair 管理，不需要**；自管仓/自发货才需要 |

写操作一律不进首期；实现时按“一个 operation 一个 sandbox 测试”的粒度开权限。

### Sandbox 全量 schema 结论（2026-10-28）

在 sandbox 端点内省成功，确认：

- `inventoryAdjustmentList(supplierId, filter{supplierPartNumber, transactionDateInterval}, page{page,pageSize})`
  返回 `eventDate`、`adjustmentType`、`supplierPartNumber`、`quantity`（带符号）、
  `warehouse`、`description`。生产已可读，适合解释库存变动。
  **`page` 是 0 索引**；第一页要传 `page: 0`，否则会跳过首页。
- `inboundOrder(supplierId, status, paginate{limit,offset})`（CGF）返回
  `estimatedCargoReadyDate`、`lineItems{ supplierPartNumber, quantity }`、
  shipments（柜号、港口、legStops 里程碑）。**理论上含 SKU 级在途与 ETA**；
  但当前生产对 OPEN/COMPLETED/CANCELLED 都返回 `null`，`inboundOrderList` 未授权，
  判断 Centrade 目前没有 CGF 在途单或未使用 CGF。
- `inventoryTransferList` 是仓间调拨，不是供应商在途。
- 写 mutation 只有 `acknowledgeCastlegate`（PO）和
  `acknowledgeCastlegateWarehouseShippingAdvices`（WSA）；
  `inboundOrderMutationNotAvailable`、`adjustmentMutationNotAvailable` 明确不可用。
  **没有创建 SPO/补货计划或新建 WSA 的 mutation**，创建仍在 Partner Home PRO。

## 在途（inbound）

独立在途数据的现状：

- `getCastleGatePurchaseOrders`：PO 头级（下单日、计划到仓日、仓），无 SKU 级数量。
- `getCastleGateWarehouseShippingAdvice`：运单级 `totalQuantity` 与发货/动作日期，无 SKU 明细。
- `inboundStockPurchaseOrderStats`：字段最接近（`suId`、`stockPurchaseOrderId`、`totalUnits`、
  `status`、`completedDate`），但当前返回空，需登录 Portal 查文档确认筛选参数。

因此首期只能提供**运单级在途**；在拿到 SKU 级 operation 之前，`inbound_live` 保持关闭，
不把运单总量摊到 SKU，也不把 `onTransferQty` 当在途。

## 复现方式

探测脚本只从环境变量读取凭证，输出仅包含状态码与字段名，不打印 token 或业务数据。
真实采集用 `python snapshot.py --account centrade`；失败会写 `snapshot_runs` 且不覆盖
最后一次成功快照。
