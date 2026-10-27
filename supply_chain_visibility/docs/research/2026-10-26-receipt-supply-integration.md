---
okf: v0.1
type: Plan
title: PO / 库存 / 在途 / 实际入库的供应整合设计
date: 2026-10-26
module: supply_chain_visibility
tags: [supply-chain, receipt, reconciliation, integration, po, in-transit]
---

# Supply Integration Design

## Context

已完成：通途采购入库只读适配器（`tongtool_api/purchase_receipts.py`）、重叠窗口采集器（`receipt_collector.py`）、覆盖/对账聚合（`receipt_coverage.py`）、W1/SC14 的 7 阶段与 B_min/B_max 口径。

本轮实测确认：PO 头 `purchaseArrivalDate` 不能代表逐条入库时间（PO021704 头 2026-10-14，50 行实际分为 38 行 10-14 + 12 行 10-19）；入库响应无稳定 `receipt_id/line_id/uom`，时间无时区；采集覆盖、单位、身份都未证。因此整合设计必须先保证“不重复、不漏计、不伪造”，再谈可承诺供给。

## Invariants（不可破坏）

1. **未知不写 0**：缺数量、单位、时区、身份时保留 `null`/`unknown`，不参与合计。
2. **单位不可混加**：UOM 未证时保留逐行证据与计数，不进入 B_min/B_max，也不产生 `(unknown)` 数量总和。
3. **不静默去重**：无稳定 ID 时只做重叠窗口去重，并显式标 `overlap_duplicate` / `possible_duplicate` / `dedup_assumed`。
4. **不自动回放库存**：receipt 事件不直接加到 available；库存仍以采集快照为准。
5. **不自动抵扣在途**：未证前只保留证据与风险，不把 receipt 增量从 in-transit 扣掉。
6. **窗口外可见**：采集窗口外的行标 `not_collected`，不能当成 `after` 或“无事件”。
7. **同一批只计一次**：PO 与通途在途、DN trace 与通途在途、外部 FBA 与自营仓，都必须按批次/范围去重。
8. **时间要同基准**：比较前先对齐 `as_of`；不同基准的库存、PO 剩余、入库事件不能直接相加。

## Canonical Row

在 W1/SC14 行上增加以下字段（聚合输出默认不含行级数量）：

| 字段 | 含义 |
|---|---|
| `source_layer` | `inventory_snapshot` / `po_open` / `in_transit` / `receipt_event` / `work_order` / `dn_trace` / `demand` |
| `source_as_of` | 该来源的基准时间（库存快照日、PO 查询时点、入库查询窗口等） |
| `snapshot_window` | 库存采集窗口（start/end）；无每仓窗口时用批次区间 |
| `collection_window` | 入库采集窗口（start/end） |
| `not_collected` | 该行是否因窗口未覆盖而不可用 |
| `identity_confidence` | `proven` / `weak_identity` / `unproven` |
| `weak_event_key` | 仅审计用的弱键；不当作业务主键 |
| `possible_duplicate` / `dedup_assumed` | 同窗口疑似重复 / 重叠窗口去重假设 |
| `overlap_status` | `unknown` / `same_batch_suspected` / `proven` / `distinct` |
| `uom` / `uom_proven` | 单位及是否已证 |
| `timezone_status` | `verified` / `unverified` |
| `b_min_eligible` / `b_max_eligible` | 是否进入 B_min/B_max |
| `exclusion_reason` | `cover_conversion_unproven` / `po_not_counted` / `b_max_only` / `unmapped` / `external_fba` / `not_collected` / `qty_unknown` / `uom_unknown` 等 |

## Source-by-Source Rules

下表数量资格均以 SourceProof 已证单位、身份、完整来源为前提；未证时只保留证据，不产生任何单位未知的数量总和。

| 来源 | 时间基准 | 身份/单位 | B_min | B_max | 说明 |
|---|---|---|---|---|---|
| 库存快照（on_hand） | 05:17 起，尽量用每仓窗口 | 仓×SKU；UOM 未证 | 只放 finished/component；cover 排除 | 含 cover（`conversion_assumed`） | 不叠加 receipt 增量 |
| PO 开放量（po_open） | PO 查询 as_of | PO 号 + SKU + 仓 | 排除同批/疑似重叠、状态未证、时点不齐与未映射 | 含全部开放 PO（含 status=4，语义未证） | 与在途两本账，先判重叠 |
| 通途在途（in_transit） | 库存快照 as_of | 仓×SKU；UOM 未证 | 未与 PO 同批时可放 | 放 | 无独立批次证据时保守保留一侧；不能用数量不等证明独立 |
| 实际入库（receipt_event） | `warehousingDate`（秒，时区未证） | 无稳定 ID/UOM | 不计（unknown） | 不计（unknown） | 只作桥接/证据，不直接加 available |
| 在产（work_order） | WO as_of | WO + 物料；UOM 个 | 只放已证转换 | 含 cover 估算 | `produced_qty` 只作 remaining |
| DN trace（dn_trace） | DN posting date | DN + 行；trace_only | 0 | 0 | 前瞻供给用通途在途，避免重复 |
| 需求（SO） | SO 行交期 | SO 行 + 物料 | 不进供给 | 不进供给 | 单独 `demand_context.csv` |

## Time Reconciliation（防漏计/防重复）

库存快照 `snapshot_window` 是判断 receipt 是否已入账的唯一时间锚；PO 剩余量必须带自己的 `source_as_of`。

| receipt 事件位置 | 处理 |
|---|---|
| 严格早于快照窗口 | `before`：可能已在 on_hand；**不加** receipt；不重复加到可用 |
| 窗口内/边界 | `uncertain`：不自动加；保留证据 |
| 严格晚于快照窗口 | `after`：不在 on_hand；作为 `receipt_delta_candidate`，但仍不自动加 available |
| 不在采集窗口 | `not_collected`：不可推断“无事件”；必须补采 |
| 同一 PO 跨多日 | 以逐条 `warehousingDate` 为准；**PO 头日期不能定窗** |

**PO 剩余量 vs 入库事件**：

- 若 `po_as_of` 晚于入库事件，PO 剩余量可能已扣减该入库；若库存仍早于该事件，会出现漏计风险（`receipt_gap_risk`）。在桶覆盖未证前仍不自动加到 available。
- 若 `po_as_of` 早于入库事件，而库存采集晚于入库，则旧 PO 开放量与新库存可能重复（`receipt_overlap_risk`）；只标风险，不自动抵扣。
- 两种情形都输出 `po_remaining_at_as_of`、`receipt_after_po_as_of`、`inventory_at_snapshot` 三个数，供人工/下游看到差额来源。

## PO / In-Transit Overlap

- `same_batch_suspected`：同 `(sku, warehouse)` 且 `open_po_qty == intransit`（只是嫌疑）。
- `proven` 需 `batch_key`（单据号/批次号）；没有则保持 `suspected`。
- 疑似/未知重叠：B_min 保守排除 PO 侧，B_max 情景可保留两侧但标状态；已证同批同量时两种界限都只计一侧，已证同批异量则隔离冲突。
- 若后续 receipt 事件能把 PO 与库存变动连起来，可升级为 `proven`；未证前不升级。

## Unit & Identity Rules

- **UOM**：`uom` 为空或未证时不进入任一数量上下限；保留单行原值和未知计数，不能跨 SKU 合成一个未知单位总量。
- **稳定身份**：响应无 `receipt_id/line_id` → `identity_confidence=weak_identity`；弱键只用于审计与重叠去重，不作为业务主键。
- **部分入库**：当前样本无多批行，`warehousingNum` 是“本次量”还是“累计量”未证；在证前不把多行相加、不按累计解释。
- **重复拉取**：重叠窗口同弱键 → `overlap_duplicate`；同一窗口同弱键 → 保留并标 `possible_duplicate`；不按内容哈希吞掉。

## Committable Supply（暂不发布）

在以下 gate 全部通过前，只输出 B_min/B_max 与 unknown，不宣称“可承诺供给”：

1. 采集覆盖：无 `truncated_windows`、无未解释 `not_collected`。
2. 单位：所有进入数量上下限的 SKU×仓 UOM 必须有独立证据；其余仅展示未知证据。
3. 身份/时间：至少能证明 receipt 与 PO/库存的关联，或明确保持 unknown。
4. 重叠：PO/在途、DN/在途、FBA/自营的去重规则已应用。
5. 基准：库存、PO、入库三类来源的 `as_of` 已对齐。

通过后建议口径：

- **B_min**：on_hand（finished/component）+ 已证在途 + 未同批 PO + 已证 receipt 桥接 − 明确排除项。
- **B_max**：on_hand（含 cover）+ 全部开放 PO + 在途 + 在产（含 cover）+ 假设性转换。
- **Committable**：B_min/B_max 与 demand 分开呈现；unknown 单列；不做单一“确定值”。

## Implementation Phases

| 阶段 | 内容 | 产出 |
|---|---|---|
| P1 | 扩展 W1/SC14 行字段：`source_layer/source_as_of/snapshot_window/collection_window/not_collected/weak_event_key/dedup*` | 行 schema + 单测 |
| P2 | 入库桥接：PO 剩余 vs receipt vs 库存快照；输出三数差额 | `receipt_bridge.py` + 合成用例 |
| P3 | 重叠与单位 gate：PO/在途、DN/在途、FBA；UOM 未证分桶 | 规则测试 |
| P4 | 接入 Supply Timeline / W3 预览：只读、未知可见、无自动写回 | 报表字段/说明 |
| P5 | 性能与发布：过滤下推、批量关联；必要时 Prepared/派生快照 | 性能记录 |

## Acceptance Tests

- PO 跨日入库：头日期窄窗漏行 → `not_collected`/覆盖警告；宽窗/重叠窗取全。
- PO 与在途同量：B_min 只计一次；B_max 两侧保留并标 `same_batch_suspected`。
- receipt 早于/晚于快照：分别 `before`/`after`；都不直接加到 available。
- PO as_of 与 receipt as_of 不同：输出三数差额，不直接相加。
- UOM 未证：两种数量上下限均排除；不产生未知单位总量。
- 重复拉取：重叠窗口去重标 `overlap_duplicate`；同窗口保留并标 `possible_duplicate`。
- 无稳定 ID：全部 `unknown`，不伪造 ID/单位/时区。
- 外部 FBA：两边都不计。
- 部分入库合成样本：只保留证据，不自动抵扣在途。

## Review Corrections（2026-10-26，本节覆盖前文旧实现说明）

- `SourceProof` 默认全部未证：必须显式传入单位、身份、完整来源、仓库映射、物料角色和来源键；非空 UOM 字符串不能自动成为已证单位。status=4 仍只允许已证来源的 B_max 情景；已证 closed/cancelled 不进供给。
- B_min 还要求已证角色/仓库与有效来源时点，同组可计来源时点不一致则不合成下限。库存的 as_of 必须在有效采集窗口内；不同库存版本或同 PO 同 SKU 的多个版本不相加。
- 等量仅表示疑似重叠，不等量不证明 distinct。distinct 要求已证、互不相交的批次键；已证同批同量只保留一侧进入两种界限，同批异量标 `batch_quantity_conflict`，等待分配证据。
- 逐 receipt 按其 PO 号匹配 as_of，禁止取组内最大时点冒充全部 PO 时点。无 PO/库存输入为 null；混合 PO 时点不生成一个总开放量。已证稳定入库身份才允许去重；冲突跨 SKU 也隔离，未证入库量不合成桥接总量。
- 弱键跨窗重放仅在完整键、相交窗口和相同完整响应下处理；保留最大观测重数，重数变化或内容冲突保留疑似重复。去重假设通过 `dedup_assumed` 传到后续，不能变成已证事件身份。
- coverage 默认接入实际完整请求窗口，截断窗口不作为完整覆盖。请求窗口按 API 查询时区解释，绝不替来源事件补时区。`query_range_complete` 不等于业务覆盖；业务覆盖仍为 unverified，not_collected=0 也不能证明没有漏采。
- 缓存必须提供账号 namespace；默认 live 模式刷新开放窗口、对历史缓存使用 TTL，损坏/旧格式/截断缓存重新查询；只有显式 frozen 才做冻结重放。CLI 以本机账号标识的摘要隔离缓存，不保存凭证。
- 报表的 `qty_status` 描述 qty，另以 `evidence_qty_status` 描述原始证据；未上报/仓库范围未知用独立 source_layer。报表仍只接库存快照，全部 B 资格为 false，不调用外部 API。
- 数据层保持 `bounds_complete=false`、`committable=false`。验证失败拒绝返回数量汇总；summary 的 B_min/B_max_only/excluded 分区与输入行数对账。纯函数修复不代表完整七阶段已经接入。

## Implementation Status

- **P1 已实现**：`supply_chain_visibility/supply_row.py` 提供统一行 dataclass 与校验（未知不写 0、未知日期不可用、`not_collected`/未知数量/未证 UOM 不得进 B_min/B_max）。
- **P2 已实现**：`supply_chain_visibility/receipt_bridge.py` 输出 PO 剩余 / 库存 / 入库三数与差额，分类 `before_snapshot` / `after_snapshot` / `uncertain` / `unknown_time` / `not_collected`，并给 `po_remaining_may_reflect_receipts`、`receipts_may_be_in_inventory`、`timezone_unverified` 等 flags；不自动调整库存或在途。
- **P3 已实现**：`supply_chain_visibility/overlap_gates.py` 对 PO/在途同批、DN trace、外部 FBA、未映射、未知 UOM、cover 转换做有序 gate；`receipt_bridge.py` 增加 `transit_qty` / `overlap_status` / `same_batch_suspected`。疑似重叠时 B_min 只留一侧、B_max 保留两侧情景；已证同批仅计一次，数量冲突隔离。
- **P4 已实现（数据层）**：`supply_chain_visibility/supply_integration.py` 组装 canonical rows + gates + bridge + 聚合；`report_only()` 只返回聚合/flag，供报表调用；未改 key_test 入口。
- **P5 已实现（本地基线 + 清单）**：`scripts/bench_supply_integration.py` + [发布前检查清单](2026-10-26-supply-integration-release-checklist.md)；合成 4k/20k/40k 行构建 0.76/3.63/7.90 秒，peak 12.6/62.4/124.6 MB；生产未部署。

## Open Decisions（需业务/证据）

1. `status=4` 的 PO 语义（是否等同关闭）。
2. `warehousingNum` 本次量 vs 累计量（需部分/多批真实样本）。
3. 入库时间绝对时区（需独立时钟或生产 Parquet/SSH 证据）。
4. `stock_change.parquet` 的凭证类型/号与库存桶覆盖。
5. 部分入库、换货/替代（`isReplace`）如何归属。
6. 是否把 native Supply Timeline 从“库存证据”升级为完整七阶段/W3。

## Verification Contract

- 数量守恒：来源量 = 纳入量 + 明确排除量 + 未知/待核对量；join 不放大。
- 不跨单位合计；未知不写 0。
- 行级原始响应只留仓库外；公开仓库只放聚合计数与规则。
- 生产只读；不自动入库、不改主数据、不改调度。

相关：[原生报表计划](2026-10-26-en-native-report-plan.md)、[PO 入库参考](../../../tongtool_api/docs/reference/purchase-receipts.md)、[JACK_QA 交接](../../../docs/research/supply-chain/2026-10-20/claude/control/handoffs/JACK_QA.md)。
