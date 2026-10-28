---
okf: v0.1
type: Reference
title: Wayfair CastleGate 库存 API——契约、权限与分页坑
date: 2026-10-28
category: integration-issues
module: wayfair-api-proxy
problem_type: integration_issue
component: api-gateway
severity: high
applies_when:
  - "要从 Wayfair 读 CastleGate（CG）库存、PO、WSA 或在途"
  - "排查 Wayfair 客户端 'not authorized'、空分页、SKU 对不上或数量为 0"
tags: [wayfair, castlegate, graphql, oauth, pagination, inventory]
---

# Wayfair CastleGate 库存 API：契约、权限与分页坑

## Context

销量预测/下单决策需要 Centrade 账号的 CastleGate 库存，且请求必须从美国固定出口发出，
避免中国 IP 直接访问 Wayfair 触发风控。实现为 `wayfair-api-proxy/`：美国 VPS 上的只读网关，
下游只调用固定业务 API，不接触 Wayfair 凭证。

## Guidance

### 认证

- Token：`POST https://sso.auth.wayfair.com/oauth/token`，JSON body：
  `grant_type=client_credentials`、`client_id`、`client_secret`、
  `audience=https://api.wayfair.com/`。
- 实测 `expires_in=86400`；以响应值为准，不要按网上 1h/12h 的说法硬编码。
- Bearer token 同时可用于 `api.wayfair.com` 与 `api.wayfair.io` 的 Supplier GraphQL。

### 端点与 operation

- 库存：`https://api.wayfair.io/v1/supplier-order-api/graphql`，
  `inventorySummaryList(supplierId, filter, page)`。
  - `supplierId` 是 **parent supplier ID**（账号级），不是 CG 子仓 ID；
  - `filter.supplierPartNumbers` 1–100 个；`page.first` 1–100，游标 `page.after`。
- 变动流水：同端点 `inventoryAdjustmentList(supplierId, filter, page)`，
  `filter.transactionDateInterval{from,to}`、`filter.supplierPartNumber`。
- PO/WSA：`https://api.wayfair.com/v1/graphql` 的
  `getCastleGatePurchaseOrders` 与 `getCastleGateWarehouseShippingAdvice`（列表）。
- CGF 在途：`inboundOrder(supplierId, status, paginate)`，含
  `lineItems.quantity` 与 shipment/legStop 里程碑；但实测当前账号所有状态返回 null，
  `inboundOrderList` 未授权。不要据此假设有 SKU 级在途。

### 字段映射

- `sku` 用 `node.supplierPartNumber`（我们的物料号），保留 `node.sku` 为
  `wayfair_sku`（Wayfair 产品号）。反过来会把多个物料压成同一个 Wayfair SKU。
- `on_hand=onHandQty`；`available=inStock.fulfillableQty`；
  `reserved=onHand.allocatedQty`；`unavailable=inStock.unfulfillableQty`。
- 仓库级 `onHand` 缺失时数量保持 `null`，**不能写 0**。`null` 是“上游未返回”。
- `onTransferQty` 是仓间调拨，不是供应商在途。

### 权限与 sandbox

- 生产权限按供应商账号、按 API 逐步解锁；`Application Management → Permissions` 里
  锁图标表示未解锁。
- Sandbox 应用默认拥有全部权限；用它的 client 凭证向同一 SSO 换 token，即可直接请求
  sandbox URL，不一定要手工生成 Sandbox Access Token。
- sandbox 端点允许 GraphQL 内省（生产不允许）。用内省确认 operation/字段/分页输入，
  比猜字段快且不会误调写接口。
- 写 mutation 目前只有 `acknowledgeCastlegate`（PO）与
  `acknowledgeCastlegateWarehouseShippingAdvices`（WSA）；
  `inboundOrderMutationNotAvailable`、`adjustmentMutationNotAvailable` 明确不可用。
  **没有创建 SPO/补货计划或新建 WSA 的接口**，创建仍在 Partner Home PRO。

### 分页坑（两条不同的规则）

- `inventorySummaryList`：游标分页；`hasNextPage=true` 但 `endCursor` 为空时必须报错，
  否则会把部分数据当成功快照发布，覆盖最后一次完整 run。
- `inventoryAdjustmentList`：`page` 是 **0 索引**，第一页传 `page: 0`；
  从 1 开始会跳过首页。不要因为“第 2 页为空”就判定上游 pageSize 有 bug。

### 数据源权威性

通途 `stock_latest` 里也有 `WayfairCG-*` 仓，但实测只覆盖 3 个仓、92/4/2 个 SKU；
与 Wayfair 同仓交集 76、45 个值完全一致，存在最大 +104 的偏差，且 `OLD_` / `-WF`
命名不一致。结论：CG 以 Wayfair API 为准；通途 CG 行排除出自有库存合计，只作交叉校验。

## Why This Matters

- 用错 SKU 键会把多物料合并、下游按物料查不到；
- 把 `null` 当 0 会造成虚假断货与错误补货；
- 缺游标静默成功会发布不完整快照，且很难在事后发现；
- 调整流水分页从 1 开始会永久丢失首页，审计结论偏差却不报错。

## When to Apply

- 任何新接 Wayfair Supplier API、增加 Castlegate operation、或排查“未授权/空数据”时；
- 设计快照/增量同步、决定是否用通途 CG 数据时。

## Examples

```graphql
query($supplierId: Int!, $filter: InventoryFilterInput, $page: InventoryPageInput) {
  inventorySummaryList(supplierId: $supplierId, filter: $filter, page: $page) {
    pageInfo { hasNextPage endCursor }
    edges { node {
      supplierPartNumber
      sku
      inventoryPosition { castleGate {
        onHandQty
        onHand { allocatedQty inStockQty inStock { fulfillableQty unfulfillableQty } }
        warehouses { warehouseId onHandQty }
      } }
    } }
  }
}
```

## Related

- `wayfair-api-proxy/docs/contract.md` — 已冻结的字段与探测记录
- `wayfair-api-proxy/docs/sandbox-test.md` — sandbox 测试步骤
- `wayfair-api-proxy/docs/en-integration.md` — EN/DuckDB 接入与通途 CG 对比
