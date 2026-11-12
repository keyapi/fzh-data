---
okf: v0.1
type: Reference
title: SO → 出库 → 货代 job → 在途快照的查询链 — ZMT Snapshot 用 job 不是 tracking
date: 2026-11-12
last_updated: 2026-11-12
category: integration-issues
module: supply_chain_visibility
problem_type: integration_issue
component: tooling
severity: medium
applies_when:
  - "要回答某张 SO 已发多少、还有哪些货在途、什么时候到港/签收"
  - "查 ZMT Shipment Snapshot 按 tracking 过滤返回 0 行"
  - "看到 Shipment.status 全是 Draft，怀疑在途状态没同步"
tags: [erpnext, sales-order, delivery-note, shipment, zmt, forwarder-job, in-transit, eta]
related_components: [supply_chain_visibility, key_test, fulfillment_query]
---

# SO → 出库 → 货代 job → 在途快照的查询链

## Context

2026-11-12 要回答三张 SO 的「生产 / 出库 / 在途」状态。EN 里的关联不是一条外键直线，
中间有多张表、两个字段名撞车，第一次查时踩了两个坑，得出过「ZMT 快照没有数据」的错误结论。
这篇把可复用的链路与字段固定下来。

## Guidance

### 1. 查询链

```
Sales Order
  └─ Sales Order Item.name（订单行主键，so_detail）
       └─ Delivery Note Item.against_sales_order = SO, so_detail = 行 name
            └─ Delivery Note（docstatus 0/1/2 都要看；退货行 qty 为负）
                 ├─ custom_zmt_logistic_numbers[].logistic_number  ← 货代 job 号
                 └─ Shipment Delivery Note.delivery_note
                      └─ Shipment
                           ├─ custom_zmt_events[]（事件表：event_date / description）
                           └─ Shipment Delivery Note → 货代 job 号
                                └─ ZMT Shipment Snapshot.job = 货代 job 号
```

- 子表（`Delivery Note Item` / `Delivery Plan Item`）**直接 GET 会 403**；用父单 +
  子表过滤：`GET /api/resource/Delivery Note?filters=[["Delivery Note Item","against_sales_order","in",[...]]]`。
  父单结果会因 join 出现重复行，按 `name` 去重。
- `Delivery Note` 默认可能只回已提交；要连草稿/取消一起看时显式加 `["docstatus","in",[0,1,2]]`，
  再把非 1 的排除在「已发」之外。

### 2. 两个字段坑

1. **`ZMT Shipment Snapshot` 的 `job` 才是货代单号，`tracking` 是尾程单号。**
   按 `tracking in [9992609...]` 查会得到 0 行；正确是 `job in [...]`。
   主要字段：`source`（智美通/云交天下/众包物流）、`status_raw`、`status11`、`status4`、
   `etd/eta/atd/ata/dlvr/appt`、`snap_date/collected_at`。同一 job 可能多行，按
   `collected_at` 取最新。
2. **`Shipment.status` 长期是 Draft，不代表没发。**
   在途状态看 `custom_zmt_events`（事件文案）或 Snapshot 的 `status11/status4`；
   `Shipment` 表头字段（carrier/awb/tracking_status）可能为空。

### 3. 数量对账

- SO 行 `delivered_qty`（SO 存储字段）应与 DN 明细按 `against_sales_order` 的带符号求和一致。
  三张 SO 实测：8,870 / 708 / 1,468，两边全符；`so_detail` 全都有值，未发现关联错账。
- 但已知存在 `so_detail` 为空、DN 行合并（`merge_so_detail_rows_in_dn`）的情况；此时按
  `item_code` 回退，跨 SO 行合并会分摊不清。做逐行未发时必须校验「DN 净额 = SO delivered」。
- `open_qty` 可为负（超发）。给补货用时逐行截零，超发单列。

### 4. 签收与 ETA 的语义

- 「已签收」来自货代回传（智美通/云交天下），**不是客户 POD 入库确认**；
  E 对同一票也标 `signed_status_proven=false`、`status_semantics=unproven`。
  只有 Snapshot `status11=已上传POD` 时证据更强。
- 同一票的 ETA 可能多源冲突：事件表写 11/17、Snapshot `eta` 写 11/19、E 的
  `carrier_eta` 写 11/18。行动前以最新 Snapshot 为准并找货代确认。

## Why This Matters

- 用错字段（`tracking`）会得到空结果，容易下「没有在途数据」的错误结论。
- 看 `Shipment.status=Draft` 会误判「还没发」，实际货已在海上。
- 把货代回传签收当客户签收，会在客诉/对账时站不住脚。
- 不核对 DN 净额，会在 SO↔DN 关联不完美的历史数据上算出错误未发量。

## When to Apply

- 按 SO / 客户码查「已发多少、在途多少、何时到」。
- 做 SO 履约报表、客户交期回复、在途异常表。
- 与 `docs/solutions/architecture-patterns/en-supply-line-e-replenishment-decision-boundary.md`
  的供给判断一起使用时，先按本篇拿到事实，再按那篇决定能不能当供给。

## Examples

三张 SO（2026-11-12）：

| SO | DN 张数 | 本单已发 | 货代 job | 最新状态 |
|---|---|---|---|---|
| SO-26-00088 | 3 | 1,468 | ZMT26081353 / 999260908002745 / 999260928001552 | 全部已签收（10/13、11/04、11/04） |
| SO-26-00103 | 5 | 8,870 | — | 2 票签收；3 票在途（4,740 到港、1,451 到港、819 海上） |
| SO-26-00109 | 4 | 708 | — | 1 票签收；3 票在途（482、62、131） |

实测字段：`ZMT Shipment Snapshot` 按 `job` 查得到
`status_raw=已签收 / status11=已签收 / status4=签收 / dlvr=2026-11-04`；
按 `tracking` 查为 0 行。

## Related

- `docs/solutions/architecture-patterns/en-supply-line-e-replenishment-decision-boundary.md` — E 的补货决策边界
- `docs/solutions/workflow-issues/erpnext-so-closed-unshipped-and-unstarted-work-orders.md` — 子表反查父单的 API 铁律
- `supply_chain_visibility/docs/reference/en-produced-qty-vs-jobcard.md` — 工序/入库/可发三层口径
