---
okf: v0.1
type: Reference
title: Tongtool ERP2.0 Purchase Order API
description: Purchase-order endpoints, required fields, and the EN Delivery Note mapping chain used to create a Tongtu purchase order.
tags: [tongtool, erp2, purchase-order, delivery-note]
timestamp: 2026-09-15
---

# 通途 ERP2.0 采购单 API

本文记录通途 ERP2.0 采购单接口的字段口径。直接调用（非 MCP）走
`https://open.tongtool.com/api-service`，认证见
[authentication-and-errors.md](authentication-and-errors.md)。

字段口径来源：官方文档 + 社区 Go SDK `github.com/hiscaler/tongtool`
（`erp2/purchase.order.go`、`erp2/supplier.go`、`erp2/warehouse.go`，
其注释直接引用官方 apiDoc 的 docId）。**尚未用本商户账号逐个实测**，
首次联调请按"验证清单"确认。

## 创建采购单

```
POST {api_base_url}/openapi/tongtool/purchaseOrderCreate
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `currency` | 是 | 币种 |
| `goodsDetail[]` | 是 | 采购货品明细，至少一条 |
| `goodsDetail[].goodsDetailId` | 是 | **通途货品 ID**，不是 SKU |
| `goodsDetail[].quantity` | 是 | 采购数量，≥1 |
| `goodsDetail[].unitPrice` | 否 | 采购单价 |
| `purchaseUserId` | 是 | 通途采购员 ID |
| `supplierId` | 是 | 通途供应商 ID |
| `warehouseIdKey` | 是 | 通途仓库 ID |
| `externalNumber` | 否 | 外部流水号（可放 EN 单号做幂等/回溯） |
| `remark` | 否 | 采购备注 |
| `shippingFee` | 否 | 运费 |
| `trackingNumber` | 否 | 跟踪号 |

`merchantId` 由请求方注入（取 partnerOpenId）。成功返回 `code=200`，
**`datas` 就是新建的采购单号**（字符串）。

### `goodsDetailId` ≠ SKU

`goodsSku` 才是 SKU 字符串；`goodsDetailId` 是通途货品主键。接口只认后者，
所以必须先拿 SKU 去 `goodsQuery` 换 ID。

## 配套接口（同一个 base，均为 POST）

| 用途 | 路径 | 关键字段 |
|---|---|---|
| SKU → 货品 ID | `/openapi/tongtool/goodsQuery` | 返回 `datas.array[].goodsDetail[]`，每项含 `goodsDetailId`、`goodsSku`、`goodsAveCost`；商品级含 `purchaserId`、`purchaseName`、`supplierName`。`skus` 每批**最多 10 个** |
| 供应商列表 | `/openapi/tongtool/supplierQuery` | `supplierId`、`corporationFullname`、`supplierCode` |
| 仓库列表 | `/openapi/tongtool/warehouseQuery` | `warehouseId`、`warehouseCode`、`warehouseName` |
| 采购单列表 | `/openapi/tongtool/purchaseOrderQuery` | 状态 `delivering / pReceivedAndWaitM / partialReceived / Received / cancel / …` |
| 采购入库记录 | `/openapi/tongtool/purchaseStockQuery` | 按入库时间查 |
| 采购入库 | `/openapi/tongtool/purchaseOrderStockIn` | `purchaseOrderId` + `arrivalInfoList[]` |
| 采购到货 | `/openapi/tongtool/purchaseArrival` | `purchaseOrderCode` + `arrivalGoodsList[]` |

## 约束

- 同一商户**所有 App 共享 5 次/分钟**限流，MCP 不绕开。见
  [../research/2026-08-13-rate-limit-experiment.md](../research/2026-08-13-rate-limit-experiment.md)。
- 错误码：`524` 未授权该接口、`525` 参数不合法、`526` 超频、`519` 签名错、`523` token 过期。

## EN 侧映射链路

销售出库单（Delivery Note）明细行上**没有**通途 SKU 字段
（标准字段 `customer_item_code` 在生产实际为空）。映射要走 Item：

```
DN 明细 item_code
  → tabItem Customer Detail.ref_code     （客户物料号 = 通途 SKU，如 TT0031085K0063341）
  → goodsQuery
  → goodsDetailId
```

`tabItem Customer Detail` 里一个 Item 可能有多行，本仓库既有口径是
`customer_name='通途'` 优先、其次 `customer_group='电商平台'`、再次空白行
（见 `tongtool_integration` 的 `api/test_client.py` 与 `tongtool_order_item.py`）。

## 消费方

- `tongtool_integration/api/purchase.py` —— 服务端三方法
  （`get_purchase_options` / `preview_purchase_order` / `create_purchase_order`）
- `EN_API/tongtool_purchase/` —— EN 侧 Client Script 与下发脚本

## 验证清单（首次联调逐条确认）

1. `supplierQuery` 返回字段名确实是 `supplierId` / `corporationFullname`
2. `warehouseQuery` 的 `warehouseId` 直接当 `warehouseIdKey` 传是否被接受
3. `goodsQuery` 的 `datas.array[].goodsDetail[]` 结构是否如文档
4. `goodsQuery` 返回的 `purchaserId` 能否直接当 `purchaseUserId`（可能不是同一 ID 空间）
5. 采购单价口径：留空 vs 传 BOM 成本
