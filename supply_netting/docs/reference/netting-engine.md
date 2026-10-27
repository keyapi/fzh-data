---
okf: v0.1
type: Reference
title: 供给净额引擎口径
description: 需求/供应入口、桶定义、两种情景、未知与排除的去向规则
tags: [netting, buckets, scenarios, unknown, replenishment]
date: 2026-10-27
status: implemented
---

# 供给净额引擎口径

## 1. 输入边界

```
demand_netting.parquet (四列唯一, netting_allowed=true)
        ×
SupplyRow（已过 apply_overlap_gates） + 库存快照期初
        ↓
bucket_receipts（按可售日分桶） + bucket_gaps（逐桶结转）
```

- 需求不为「预测」：本层只消费已发生的订单行。未来桶想有数，必须由上游提供
  未履约 SO 余额（`--backlog`）或后续预测层，本层不猜。
- 供应不为「报表摘要」：只吃 `SupplyRow` 级别的事实；字符串摘要不进入接口。

## 2. 桶定义

`build_buckets(as_of, protect_days, weeks)`：

- `protect`：`[as_of, as_of + protect_days)`
- `w1..wN`：紧随其后的 7 天桶，左闭右开、不重叠

`as_of` 必须带时区。日级数据按 **`as_of` 时区的当日 00:00** 落桶，这条规则写进
manifest 的 `date_adapter_rule`；`bucket_receipts` 本身不给日期补午夜。

## 3. 逐桶账

对每个 `sku × 仓 × 单位`：

```
opening   = 库存快照该仓该物料的 available（0 是有效观测，缺行才是未知）
receipts  = bucket_receipts 判定的「计入本桶」数量
demand    = 本期需求 + 上期未满足（结转）
fulfilled = min(demand, opening + receipts)
closing   = opening + receipts − fulfilled
unserved  = demand − fulfilled
gap       = max(0, unserved)
```

数学实现直接复用 `aa93773b` 的 `bucket_gaps`；每一行都过
`assert_bucket_identities`，不存在「差不多对」。

## 4. 两种情景

| 情景 | 是否要求分配已证 | 是否要求来源时点 | 用途 |
|---|---|---|---|
| `conservative` | B_min | 是 | 「已证按时可用」 |
| `expected` | B_max | 否（日期已证即可） | 「当前预计到货」 |

unknown ETA 的供应**两边都不计**，只进 `conditional_receipts` 与事实表；
这不是「缺 0」，而是「有量、无日期」。

## 5. 未知与排除的分类

| 去向 | 含义 | 是否条件态 |
|---|---|---|
| `opening_basis` | 库存快照行，作为期初 | 否 |
| `date_unproven` | 有数量、无可售日 | 是 |
| `eligibility_unproven` / `allocation_unproven` | 资格/自由分配未证 | 是 |
| `pre_asof_inclusion_unproven` | 早于/等于快照但未证已入账 | 是 |
| `outside_buckets` | 落在桶间空档 | 是 |
| `fba_allocated` | FBA 已占，不得重复分配 | 否（明确排除） |
| `same_batch_counted_once` | 同批跨阶段（PO/在途）只计一次 | 否 |
| `warehouse_unmapped` / `uom_unproven` / `identity_unproven` | 仓/单位/身份缺证据 | 否（明确排除） |
| `after_horizon` / `before_as_of` | 视界外 | 否 |

`gap` 只有在有快照基准时才给数值；无基准时为 `null` + `status=unknown`，
调用方必须区分「缺口 0」与「无法判断」。

## 6. 与上游契约的对应

| 契约要求 | 本层落点 |
|---|---|
| 需求只用四列唯一净额表 | `demand.load_demand_netting`（重复/阻断行直接抛错） |
| `in_default_series` ≠ `netting_allowed` | 分别用于序列选择与入口校验 |
| 3PL 保留、责任未知 | `third_party_demand.parquet`，`replenishment_owner=unknown` |
| FBA 不重复分配 | `fba_allocated`，两情景都排除 |
| 同批只计一次 | overlap gates + `same_batch_counted_once` |
| 未知不写 0 | `unknown` / `conditional` 状态 + `null` 数值 |
| 逐桶恒等式 | `assert_bucket_identities` + 供应数量账守恒 |

## 7. 不做

- 不做预测、不做补货量/MOQ/预算（决策层消费事实后处理）。
- 不做写回、不下单、不改主数据。
- 不做跨仓调拨假设：仓是硬边界，「美东有余、美中缺」不会被自动抵消。
