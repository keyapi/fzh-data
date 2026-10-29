---
okf: v0.1
type: Spec
title: 第五步：签收→通途入库→库存快照防重防漏
date: 2026-10-29
updated: 2026-10-29
owner: claude-worker
status: implemented; tongtool/inventory runtime not integrated; production not deployed
scope: read-only; no tongtool writes; no business data writes
tags: [supply-chain, receipt, tongtool, inventory, reconciliation]
---

# 第五步：签收→通途入库→库存快照

## 1. 已证关联链

`Shipment/物流单号 → Delivery Note → DN.custom_tongtool_purchase_order → 通途 PO → 入库行（SKU/仓/UOM）`

没有已证 PO/DN/Shipment 关联时保持 `unknown`；不得用数量相等、日期接近或同 SKU 猜批次。

## 2. 签收→入库状态机

`in_transit → signed_pending_tongtool_receipt → tongtool_received`

- 未签收：`in_transit`；
- 已签收无/部分入库：`signed_pending_tongtool_receipt` + `receipt_completion=pending/partial`；
- 只有完整入库已证才进入 `tongtool_received`；
- 多 DN→一 PO、一 DN→多 Shipment、同 PO 同 SKU 多行：保留行级分配状态；无法唯一分配 →
  `receipt_allocation_unknown`，不计数量。

输出：`shipment_signed_at`、`tongtool_first_receipt_at`、`tongtool_last_receipt_at`、
`tongtool_receipt_at`（仅完整）、`receipt_lag_days`、`receipt_completion`、
`received_qty/pending_qty` 及 evidence_status、`receipt_basis=signed_assumed`、
`identity_confidence`、`exclusion_reason`。

## 3. 库存快照桥接

逐 receipt 输出：

`receipt_inclusion_status`（included / after_snapshot / uncertain / conflict / unknown）、
`inventory_snapshot_id`、`source_as_of`、`snapshot_window_start/end`、
`receipt_effective_at`、`inclusion_proof`、`post_snapshot_delta_qty`、`conditional_delta_qty`、
`eligible`、`exclusion_reason`。

规则：

- 严格晚于快照窗口 → `after_snapshot`，保留条件 delta，`eligible=false`；
- 早于快照不自动等于已包含，只有 `inclusion_proof` 才 `included`；
- 窗口内 → `uncertain`；
- 重复 → 计一次并保留审计行；载荷冲突 → `conflict`；
- included 只计库存、不再加 receipt；after_snapshot 保留 delta；uncertain 两边都不自动相加。

数量对账：`input = included + duplicate + conflict + unmatched + not_collected +
after_snapshot + uncertain`（比原始五分类多了后两类，因本轮必须显式保留它们），
`partition_total` 必须等于输入行数；未匹配行必须带原因。

## 4. 运行时边界

- 服务端 `source_status.tongtool_po / receipt / inventory = not_integrated`；
- 通途不在每个 SO 行实时调用；批量/分页/限速/缓存只能在本地导出层；
- 本轮导出新增 `receipt_reconciliation` 与 `inventory_bridge` 数据集，可由本地只读输入
  （`--receipt-state-json` / `--inventory-bridge-json`）填充；无输入时为空并标 `not_integrated`；
- `warehousingNum` 是本次量还是累计量、响应时区、稳定行身份未证 → 保持 unknown；
- `status=4` 语义未证 → `status_semantics=unproven`，不据此关闭或进入已证下限。

## 5. 海外可售

签收、通途入库、EN 入库、QC、工厂完工是不同证据，永不相加；通途入库不自动等于海外可售。
目标仓映射、SKU、UOM、库存桶、包含关系、用途/FBA 预留、来源新鲜度未证前 `eligible=false`，
`available_date=null` 或仅 `receipt_event_date`。
