---
okf: v0.1
type: Spec
title: 第五步：签收→通途入库→库存快照防重防漏
date: 2026-10-29
updated: 2026-10-30
owner: claude-worker
status: implemented locally (Codex rework); tongtool/inventory runtime not integrated; test-station re-verification pending
scope: read-only; no tongtool writes; no business data writes
tags: [supply-chain, receipt, tongtool, inventory, reconciliation]
---

# 第五步：签收→通途入库→库存快照

## 1. 已证关联链

`Shipment/物流单号 → Delivery Note → DN.custom_tongtool_purchase_order → 通途 PO → 入库行（SKU/仓/UOM）`

没有已证 PO/DN/Shipment 关联时保持 `unknown`；不得用数量相等、日期接近或同 SKU 猜批次。
导出层优先从服务端 `shipment_progress` + `stage_balances` 自动构造该链，减少手工 link JSON
不一致；显式 `links` 仍接受但走同一严格校验。

## 2. 采集覆盖（collection coverage）——本轮的硬前提

`reconcile_signed_receipts` 的输入必须携带覆盖 envelope：

```text
coverage = {
  query_range_complete: bool,
  requested_windows: [{start, end}],   # 非空；start<=end
  truncated: bool,
  not_collected: [{start, end}] | bool,
  source_as_of: 带时区时间,             # 必须 >= 每个 window.end
  covered_po_codes: [str],              # 本次查询实际覆盖的 PO 身份
  coverage_mode: time_range | po_full_history
}
# po_full_history 时另需：
#   po_full_history_proven: true
#   po_full_history_source: 非空来源名
#   po_full_history_as_of: 带时区时间
```

- 覆盖必须能证明**当前 link 的全部 po_codes** 都在 `covered_po_codes` 内；
- **时间闭环**：`time_range` 模式的窗口并集必须连续覆盖
  `[shipment_signed_at, source_as_of]`；窗口间空档即不完整；
- `receipt.effective_at` 必须落在覆盖窗口内；窗口外记录标
  `receipt_outside_coverage`，不计入关闭数量；时间缺失/无时区无法定位的记录标
  `receipt_time_unverified`，同样不计入关闭；
- 若来源是 **PO 全历史**而非时间范围，必须显式 `coverage_mode=po_full_history`
  并提供上述证明字段；**禁止**用无关时间窗口冒充完整覆盖；
- **只有 link-specific coverage 完整时，“无 receipt 行”才允许 `received_qty=0` known**；
- 覆盖缺失/截断/未采集/scope 不匹配/时间不闭环时：
  - 已观察到的合法 `received_qty` 可保留 known；
  - `pending_qty` 必须 unknown；
  - **不得** `receipt_completion=complete`、不得进入 `tongtool_received`、
    不得输出作为关闭依据的 `tongtool_receipt_at`；
  - 已观察量仍超过 `link.qty` 时照常报 `over_receipt` conflict；
- 每行输出 `coverage` 原值与 `coverage_status`
  （complete/incomplete/invalid/missing/scope_mismatch），以及
  `receipts_outside_coverage`、`outside_coverage_qty`、`receipts_time_unverified`。

## 3. 签收→入库状态机

`in_transit → signed_pending_tongtool_receipt → tongtool_received`

- 未签收：`in_transit`；
- **签收状态与时间解耦**：`ShipmentLink.signed_status_proven=true` 且 `signed_at=null`
  时必须保持 `signed_pending_tongtool_receipt`，不得回退 `in_transit`；时间缺失只影响
  lag、`receipt_before_signed` 判断和时间字段，不推翻签收状态；
- 已签收无/部分入库：`signed_pending_tongtool_receipt` + `receipt_completion=pending/partial`；
- 只有完整入库已证**且 link-specific coverage 完整**才进入 `tongtool_received`；
  不完整覆盖下即使 observed qty 等于 link qty 也只能 `coverage_incomplete` + pending；
- **超收**：`received > link.qty` → 不进入 `tongtool_received`；输出
  `receipt_completion=over_receipt`、`over_receipt_qty`、`receipt_conflict=true`，
  状态留在 pending；覆盖不完整时 `pending_qty=null`，但超收冲突照常成立；
- **receipt 早于签收** → `status=unknown`、`receipt_conflict=true`、
  `exclusion_reason=receipt_before_signed`；
- **时区**：所有时间先显式校验；naive/非法时间不得当作 UTC。naive/aware 混用不崩；
- **lag 精确化**：`receipt_lag_seconds`（总秒）、`receipt_lag_hours`（3 位小数）、
  `receipt_lag_days`（整日）三者同时输出，不再只用 `.days` 静默截断；
- **缺有效 receipt 时间**：不得伪造 `tongtool_receipt_at`（保持 null），输出
  `receipt_time_status`；`signed_time_status` 同理；时间不完整时 lag 为 null +
  `receipt_lag_status`；
- 多 DN→一 PO、一 DN→多 Shipment、同 PO 同 SKU 多行：保留行级分配状态；无法唯一分配 →
  `receipt_allocation_unknown`，不计数量。

输出：`shipment_signed_at`、`signed_status_proven`、`signed_time_status`、
`tongtool_first_receipt_at`、`tongtool_last_receipt_at`、
`tongtool_receipt_at`（仅完整且有有效时间）、`receipt_lag_seconds/hours/days`、
`receipt_completion`、`received_qty/pending_qty`(+evidence_status)、
`receipt_basis=signed_assumed`、`identity_confidence`、`coverage_status`、
`receipts_outside_coverage`、`outside_coverage_qty`、`receipts_time_unverified`、
`exclusion_reason`。

## 4. 库存快照桥接

逐 receipt 输出：

`receipt_inclusion_status`（included / after_snapshot / uncertain / conflict / unknown）、
`inventory_snapshot_id`、`source_as_of`、`snapshot_window_start/end`、
`snapshot_candidates`、`receipt_effective_at`、结构化 `inclusion_proof`、
`inclusion_proof_type`、`post_snapshot_delta_qty`、`conditional_delta_qty`、
`eligible`、`exclusion_reason`。

规则：

- **一次计算只能绑定一张明确 snapshot**：快照身份 (`inventory_snapshot_id`,
  `as_of`, `window_start`, `window_end`) 去重后 >1 → 所有 receipt `conflict` +
  `multiple_snapshot_versions`，输出候选，禁止 `min(start)+max(end)` 拼接；
- proof 必须是逐 receipt 结构化凭证：`proof_type`、`source_record`、
  `receipt_identity`、`snapshot_id`、`source_as_of`；
  `receipt_identity`/`snapshot_id`/`source_as_of` 与绑定对象不一致 → `conflict` +
  `inclusion_proof_identity_mismatch`；
- 禁止用 SnapshotRow 的一个布尔值覆盖同组全部 receipt；
- 严格晚于快照窗口 → `after_snapshot`，保留条件 delta，`eligible=false`；
- 早于快照不自动等于已包含，只有匹配的结构化 proof 才 `included`；
- 窗口内 → `uncertain`；
- 重复 → 计一次并保留审计行；载荷冲突 → `conflict`；
- included 只计库存、不再加 receipt；after_snapshot 保留 delta；uncertain 两边都不自动相加。

数量对账：`input = included + duplicate + conflict + unmatched + not_collected +
after_snapshot + uncertain`，`partition_total` 必须等于输入行数；未匹配行必须带原因。

**post-snapshot delta 按 `SKU×仓×UOM` 分组输出**（`summary.post_snapshot_delta`），
禁止跨单位求和。

## 5. 本地只读输入（严格 schema + coverage）

`--receipt-state-json` / `--inventory-bridge-json` 必须带 `schema_version` 与完整
coverage envelope：

```text
receipt-state:      {"schema_version":"supply-facts/receipt-state/v1",
                     "coverage":{...},"links":[...],"receipts":[...]}
inventory-bridge:   {"schema_version":"supply-facts/inventory-bridge/v1",
                     "coverage":{...},"snapshots":[...],"receipts":[...]}
```

- 布尔字段只接受 JSON `true/false`；字符串 `"true"/"false"` 拒绝；
- 拒绝未知字段、缺字段、schema/版本不一致、重复身份异载荷、无时区/非法时间；
- 拒绝空 `requested_windows`（`time_range` 模式）、`start > end`、`source_as_of < window.end`；
- 拒绝 `covered_po_codes` 未覆盖任一 link 的 `po_codes`（PO scope 不匹配）；
- `po_full_history` 必须显式提供 `po_full_history_proven=true`、非空来源与带时区
  `po_full_history_as_of`；`time_range` 模式禁止携带这些证明字段；
- link 的 `signed_status_proven`（可选）只接受 JSON 布尔；`signed_at` 可为 null；
- 校验失败：不创建成功 run、不切换 `latest.json`；manifest 标记
  `receipt_reconciliation.links_source = server_auto | local_input | none`。

## 6. 运行时边界

- 服务端 `source_status.tongtool_po / receipt / inventory = not_integrated`；
- 通途不在每个 SO 行实时调用；批量/分页/限速/缓存只能在本地导出层；
- `warehousingNum` 是本次量还是累计量、响应时区、稳定行身份未证 → 保持 unknown；
- `status=4` 语义未证 → `status_semantics=unproven`，不据此关闭或进入已证下限。

## 7. 海外可售

签收、通途入库、EN 入库、QC、工厂完工是不同证据，永不相加；通途入库不自动等于海外可售。
目标仓映射、SKU、UOM、库存桶、包含关系、用途/FBA 预留、来源新鲜度未证前 `eligible=false`，
`available_date=null` 或仅 `receipt_event_date`。
