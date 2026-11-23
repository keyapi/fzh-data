---
okf: v0.1
type: Reference
title: EN Tongtool Order 实测 schema 与读取口径
description: 2026-10-27 在生产 EN 实测的 doctype 字段、子表、raw_data 差异、分页与查询坑
tags: [erpnext, tongtool-order, schema, reference]
date: 2026-10-27
status: verified
---

# EN `Tongtool Order` 实测 schema

> 结论先行：EN **有**终端订单的 SKU 行（`order_items` 子表）与包裹（`packages` 子表），
> 可以支撑 10 月起的自发货需求增量；但 9 月以前的历史仍以 GS 月表为准（EN 只有 154,632 单，
> 且是 2025-12 起回填的）。**不要**把 `en_orders.parquet`（旧 2,733 行订单头抽样、
> 无 SKU 明细）当完整需求。

## 1. 规模与时间范围（2026-10-27 实测）

| 指标 | 值 |
|---|---|
| `Tongtool Order` 总数 | 154,632 |
| `order_type=自发货` | 120,808 |
| `order_type=FBA` | 33,824 |
| `order_type=未知` | 0 |
| `order_status=已发货` | 148,089 |
| `order_status=等待配货` | 5,615 |
| `order_status=缺货` | 15 |
| `order_status=已取消 / 已退款` | 0 / 0 |
| `invalid=1`（作废） | 5,745 |
| `sale_time` 最小值 / 最大值 | 2023-01-19 / 2026-10-26 23:58 |
| `creation` 最小值 | 2025-12-03（回填起点） |
| `modified` 最小值 / 最大值 | 2026-01-07 / 2026-10-27 |
| `modified >= 2026-10-01` | 27,503 |
| `sale_time >= 2026-10-01` | 6,800 |
| `sale_time ∈ [2026-09-20, 2026-10-01)` | 2,790 |

**取消语义**：状态枚举里有「已取消/已退款」，但实测为 0；取消/作废走 `invalid=1`
（原始 `raw_data.isInvalid=3`）。只看 `order_status` 会把作废单当待发需求。

## 2. 主表字段（已验证）

```
name                 = order_id_code（单据名；拆单带 _1/_2 后缀）
platform_order_id    平台单号（拆单也可能带 _1/_2）
order_type           自发货 | FBA | 未知
order_status         等待配货 / 等待打印 / 等待发货 / 已发货 / 未付款 / 已付款 /
                     分配仓库失败 / 错误状态 / 缺货 / 已取消 / 已退款 / 其他
invalid              作废（0/1）
suspended            需人工审核（0/1）
sale_time            销售时间
paid_time            付款时间
despatch_complete_time 发货时间
updated_time         源（Tongtool）更新时间
last_sync_time       EN 采集/同步时间
modified             EN 记录修改时间（增量水位）
creation             EN 记录创建时间（回填时间，不是业务时间）
warehouse_name       发货仓库名
package_id           包裹号（可能为空）
tracking_number      跟踪号（可能为空）
merchant_carrier_shortname 承运人
channel / account / sale_account / platform_code / channel_account_en
order_amount / order_amount_currency
raw_data             JSON 字符串（源订单原始载荷）
```

`raw_data` 与 `Tongtool Order` 字段的关系：

- 普通自发货订单：`raw_data.orderDetails[]` 带 `orderDetailsId`（稳定源行 ID）、
  `webstore_item_id`、`webstore_sku`、`goodsMatchedSku`、`quantity`、`isDeliverGoods`；
  `raw_data.packageInfoList[]` 带 `packageId`、`trackingNumber`；另有
  `isInvalid`、`isRefunded`、`refundedTime`、`parentOrderId`、`updatedTime`。
- **FBA 订单的 `raw_data` 是另一种结构**（Amazon FBA 报表：`purchaseDate`/`orderId`/
  `itemStatus` 等），**没有 `orderDetails`**；FBA 的行身份只能回退到子表 `idx`。

## 3. 子表

### `Tongtool Order Item`（`order_items`）

关键字段：`idx`、`platform_sku`、`tongtool_sku`、`erp_item_code`、`quantity`（Int）、
`is_deliver_good`（是否发货商品）、`shipping_method`（皮壳/成品/半成品）、
`match_status`、`web_store_item_id`、`asin`、`goods_detail_id`、成本类字段。

实测填充（2026-10 订单 300 行样本）：

- `goods_detail_id` 空 257/300 → **不能**当主键。
- `web_store_item_id` 空 65/300 → 也不能单独当主键。
- `shipping_method`：皮壳 219、半成品 33、成品 29、空 19 —— **多数订单发的是皮壳，
  不是成品**；组件数不能当成品需求。
- `is_deliver_good=0` 的行是随单组件（例如 Foam），不能并入成品需求。

### `Tongtool Order Package`（`packages`）

`package`（P 号）、`tracking_number`、`allocated_fee`、`currency`、
`allocated_carrier_fee`、`carrier_currency`。

**没有行→包裹的映射**（`order_items` 无 `package_id`）。一单多包裹时，无法从 EN 判断
哪一行进了哪个包裹；本模块记录 `packages` 与 `package_count`，但**不做行级包裹归属推断**。

## 4. REST 读取的实测坑

1. **子表不能单独列表查**（`Tongtool Order Item` 列表 403）；必须从父单读。
2. **带子表字段的列表查询会按「父字段 + 子字段」扁平成行**：
   `fields=["name","order_items.tongtool_sku"]` 返回的行是子行数，父字段重复。
3. **`limit_page_length` 作用于扁平行数，不是父单数**：一单两行会占两行配额，
   分页边界可能把一单的行切开 —— 必须跨页按单据聚合，不能中途覆盖。
4. **`order_by=modified` 在带子表字段时会报 `Column 'modified' in ORDER BY is ambiguous`**；
   带子表的查询用 `order_by=sale_time`（父表独有列）。
5. **`name like '%_1'` 极慢**（实测 33s+）；不要用名字模糊匹配找拆单，
   改为读 `platform_order_id` / 单据名后缀。
6. **`frappe.client.get_count` 每次约 33s**（疑似服务端缓存/限速），列表查询正常；
   计数只用于一次性摸底，不要放进日常循环。
7. 子表 `name` 是随机 10 位 Frappe 子行 ID，**父单重存会重建**，不能当业务主键。

## 5. 稳定键与拆单

| 概念 | 取值 | 说明 |
|---|---|---|
| 单据键 | `en_doc_name` | 完整单据名（含 `_N`），一单一行 |
| 拆单后缀 | `split_suffix` / `split_index` | 名字尾部 `_1`、`_2`… |
| 拆单族 | `base_order_id` | **单据名**去后缀（保留渠道前缀，与 GS 口径一致） |
| 平台单号族 | `platform_base_order_id` | `platform_order_id` 去后缀 |
| 行键 | `line_key` | 优先 `doc|src:<orderDetailsId>`；回退 `doc|idx|sku|qty` |
| 包裹键 | `(en_doc_name, package_index)` | 有则另存 P 号 |

GS 的 `order_id` 同样带 `_N` 后缀（实测 2026-09-20~30：1,816 行 / 1,796 单，其中 137 行带后缀），
所以跨源直接按 `order_id == en_doc_name` 行级对齐；`base_order_id` 只用于分组报告，
**绝不用于合并或覆盖**。

## 6. 时间戳分层

| 列 | 含义 | 来源 |
|---|---|---|
| `sale_time` | 销售时间 | Tongtool |
| `paid_time` | 付款时间 | Tongtool |
| `despatch_complete_time` | 发货时间 | Tongtool |
| `updated_time` | 源修改时间 | Tongtool |
| `last_sync_time` | EN 采集时间 | EN 同步任务 |
| `modified` | EN 记录修改时间 | EN（增量水位） |
| `first_seen_at` / `last_seen_at` | 本地首次/最近采集时间 | 本模块 |

所有时间都是**朴素本地时间**（无时区），本模块不做换算；跨时区消费需自行确认口径。
