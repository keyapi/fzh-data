---
okf: v0.1
type: Reference
title: 供给净额输出 schema 与 manifest
description: 五个产物的字段、键与 manifest 结构；调用方与导出器按此消费
tags: [schema, parquet, manifest, outputs]
date: 2026-10-27
status: implemented
---

# 输出 schema 与 manifest

输出根：`--out <dir>`，全部由 CLI 一次写出；调用方也可以只调
`artifacts.build_tables()` 拿 DataFrame 自行落盘。

## 1. `supply_netting.parquet`（逐桶明细）

键：`canonical_sku × canonical_warehouse × canonical_uom × bucket_id × scenario`

| 字段 | 类型 | 说明 |
|---|---|---|
| `scenario` | str | `conservative` / `expected` |
| `bucket_id` | str | `protect` / `w1` / `w2` … |
| `opening` | float/null | 本期期初；首桶来自库存快照，其后承接上期 |
| `receipts` | float/null | 本期计入到货 |
| `demand` | float/null | 本期需求 + 上期未满足（结转，见 `bucket_gaps`） |
| `fulfilled` | float/null | `min(demand, opening + receipts)` |
| `closing` | float/null | 期末结余 |
| `unserved` | float/null | 累计未满足 |
| `gap` | float/null | `max(0, unserved)` |
| `conditional_receipts` | float/null | 该键条件态供应量（未知 ETA / 未证资格） |
| `has_unresolved` | bool | 供应侧仍有未决项 |
| `supply_evidence` | bool | 该键是否有任何未来供应证据 |
| `status` | str | `valued` / `conditional` / `unknown` |
| `unknown_reason` | str/null | `no_snapshot_basis` / `opening_qty_unproven` |

`status=unknown` 时数量列为 `null`——**不是 0**。

## 2. `supply_facts.parquet`（同一底层供应事实）

每条输入供应一行（含期初行与证据行），字段：

`event_id, source_layer, stage, qty, available_date, date_confidence, scope,
identity_confidence, warehouse_confidence, b_min_eligible, b_max_eligible,
batch_key, batch_proven, document_key, source_key, exclusion_reason,
disposition_reason, bucket_id, counted, conditional, scenario,
canonical_sku, canonical_warehouse, canonical_uom`

- `scenario=any` 的行是期初（`opening_basis`）或无法归属的证据行。
- 无法归到 SKU×仓×单位的输入保留 `raw_sku` / `raw_warehouse` 与原因
  （`identity_unproven` / `uom_unproven` / `warehouse_unmapped`），不静默丢弃。

## 3. `replenishment_review.parquet`（审核视图）

键：`canonical_sku × canonical_warehouse × canonical_uom`（`expected` 情景）

| 字段 | 说明 |
|---|---|
| `opening` | 基准库存 |
| `protect_demand` / `protect_gap` | 保护期需求与缺口 |
| `horizon_unserved` | 视界末累计未满足 |
| `conservative_protect_gap` | 保守情景的保护期缺口 |
| `conditional_supply_qty` | 条件供应量 |
| `status` / `needs_review` | 状态与需人工核实说明 |
| `demand_before_as_of` | 基准前的历史需求（不参与净额） |

## 4. `third_party_demand.parquet`

键同上；`quantity`、`replenishment_owner=unknown`、`note`。
3PL/代发需求保留，不并入自发货净额。

## 5. `replenishment_review.xlsx`

四个 sheet：`补货审核`、`逐桶明细`、`供应事实去向`、`Manifest`。
工作簿只是同一底层事实的呈现，不额外做计算。

## 6. `supply_netting_manifest.json`

| 段 | 内容 |
|---|---|
| `schema_version` / `rules_version` / `run_id` / `as_of` | 版本与时点 |
| `buckets` | 桶 id 与起止（ISO，带时区） |
| `scenarios` | 两种情景定义 |
| `date_adapter_rule` | 日级→瞬间的适配规则 |
| `inputs` | 需求/阻断/库存/PO/backlog 的路径、sha256、行数 |
| `contract` | 入口契约：只认净额表、字段不混用、复用组件名 |
| `checks` | 行数对账、四列重复、恒等式、供应数量账守恒、未归类数量 |
| `disposition_counts` | 每个情景下各类去向的条数 |
| `status_counts` | `valued/conditional/unknown` 行数 |
| `partial` / `partial_reasons` | 是否 partial 及原因（当前恒为 true） |
| `outputs` | 每个产物的路径与 sha256 |

重跑只会覆盖 `--out` 指定目录，不触碰输入。
