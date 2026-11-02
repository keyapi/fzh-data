---
okf: v0.1
type: Reference
title: 供应事实与数量—日期契约 v1 + full facts v3 发布/reader/ABC/复跑
date: 2026-11-02
owner: claude-worker
status: full facts v3 本地实现与 361 项测试通过；真实 A/B/C 与受限 HTTP 待验；生产未部署
tags: [supply-chain, replenishment, facts, manifest, so-chain]
---

# 供应事实批量入口 v1

> 同一份事实服务，两个消费者：SO Chain Overview 的人工下钻 + 可重跑的批量 JSON/Excel 导出。
> 只读；不写库、不下单、不扩权；行级数据留本地。

## 1. 数据契约

三个逻辑数据集 + 关联边 + manifest；字段以 JSON 为准。

### `stage_balances`（互斥的当前阶段余额）

| 字段 | 说明 |
|---|---|
| `so`, `so_line_id`, `item_code`, `warehouse`, `uom` | 订单行身份 |
| `stage` | `not_planned` / `in_production` / `produced_pending_dn` / `shipped_in_transit` / `arrived_not_sellable`（legacy，仅过滤兼容） / `signed_pending_tongtool_receipt` / `tongtool_received` / `delivered_sellable` / `cancelled` / `returned` / `draft_dn` / `over_produced` / `unknown` |
| `qty`, `qty_status`, `qty_basis` | 数量、证据状态（known/estimated/unknown）、依据（job_card_first_op / wo_produced_qty / dn_submitted / …） |
| `cumulative_excess_qty` | 仅 `over_produced` 行：累计超订单完工量（异常指标）；该行 `qty` 为当前超订单现存实物 |
| `batch_key`, `source_record` | DN / 工单 / 来源单据 |
| `exclusion_reason`, `included_in_stock` | 不可计入原因、是否已含库存（未证一律 unknown） |
| `demand_status` | `active` / `cancelled` / `excess`（`excess`=超订单完工的未分配实物，不计入本订单余额与可售供给） |
| `scope`, `role` | `in_house`/`external_fba`、物料角色 |

规则：
- 同一订单行的已执行片段互斥；历史累计完工/出库**不**再相加；草稿 DN 只列数量为空的提示行；差额进 `unknown` 并给原因。
- **超产**：订单内分配最多按订单量；`over_produced` 的 `qty` 表示**当前超订单实物现存**（来源完工 − max(已出库, 订单量)），`cumulative_excess_qty` 保留累计超订单完工量（来源完工 − 订单量），二者分开；`demand_status=excess`，不计入订单阶段守恒与可售供给，取消订单同样保留；无现存实物时仍保留该异常行（qty=0 + 累计字段）。`milestones` 的开工/完工节点数量保留来源数量，并在 `note` 标注超出订单量。
- **阶段分配**：工单覆盖量 `wo_coverage=min(Σ工单数量, 订单量)`；实际在产只按有开工证据的工单计算（工序卡有实际开工时间或已完工），`在产量=min(余额, max(0, 已开工覆盖-已完工))`；已下达但无开工记录的工单覆盖只证明计划，进 `unknown`；超出覆盖的余额进 `not_planned`。工单单位与订单单位不一致时完工量不可归一，生产类阶段整体进 `unknown`。已提交生产计划（同物料）覆盖但尚未建工单的部分进 `unknown`（不判为未计划）；计划不可读时同样进 `unknown`；计划单位缺失或与订单单位不一致时不计覆盖量，剩余余额整体进 `unknown`（不计算未覆盖差额）。
- **行级权限**：SO/DN/WO/PP/Shipment 均先取当前用户可读单据集合再取数；受限来源写入 `coverage.restricted` 并置 `partial=true`；因受限无法判断的阶段一律 `unknown`，不得解释为「没有」。
- **单位**：出库单位与订单单位不一致**或缺失**且无换算证据时，不归一运算；输出「数量归属未知」+ 原单位实物片段；缺失单位标 `qty_status=unknown`。`milestones` 与 `links` 中的派生数量同样只在来源单位与订单单位一致时输出，否则 qty=null 并给原因。
- **物流阶段裁决（v2）**：status11 + status4（显式 normalization map）+ Shipment
  Logistics Event 三来源；终态粘性 + 实际优先 + 阶段顺序。到港/清关/转运/派送仍属
  `shipped_in_transit`（仅 actual）；只有已签收/POD 才进入 `signed_pending_tongtool_receipt`；
  ETA-only 只能是预计证据；终态缺 `dlvr` → `shipment_signed_at=null`；阶段回退 →
  unknown+conflict；同号多 Shipment → identity conflict；
  多运单全部签收时 DN 进入待入库但每条 Shipment 不复制 DN 数量；部分签收/状态未知保守留在途；
  冲突/异常/撤销/未映射人工值 → unknown/conflict。详见 STEP4。
- **退货**：按 `return_against` 锁定原出库单，再**按原出库明细（`dn_detail`）逐条校验身份与剩余可抵扣量**，匹配量汇总到 DN；读取时不同原明细的退货行不合并，聚合组同时保留逐明细数量（`item_qty`）。`dn_detail` 指向的明细不存在于原单 → **明细引用冲突**，不抵扣、不做单行兜底，单独报冲突；缺 `dn_detail` 时只有原单**恰好一条原始明细**才按该明细剩余容量兜底——原单有多条原始明细（即使同仓同单位聚合成一组）一律视为归属未知、不抵扣；未参与冲突的其他明细保留已证净额。所有路径共用同一份按原始明细记账的容量账本：结果与退货处理顺序无关，且每条明细累计抵扣不超过其原始数量。`returned` 行按来源拆分：实际抵扣、超退（超出该明细可抵扣量）、明细引用冲突、未关联原单 / 无法归属；各项之和等于退货原值，不得把超退或冲突描述为已抵扣。退货缺口 `min(退货量, 需求余额)` 记 `unknown`，不得推断为「待出库」或「在产」，扣除后余额再分配在产/未计划。
- **取消**：需求取消与已生产/已发实物分开记录；实物片段带 `demand_status=cancelled`，不随订单状态删除。
- **as_of**：服务端只支持当前快照；历史 `as_of` 直接拒绝（HTTP 错误），不能由客户端校验替代。
- **空结果**：无匹配/全部受限也保留 `coverage`、`external_sources`、`empty_reason`，`partial=true`，不得声称完整；`empty_reason` 区分 `no_matching_lines`（无匹配）与 `all_restricted`（有匹配但全部不可读）。

### `milestones`（原计划 / 承诺 / 最新预计 / 实际）

| 字段 | 说明 |
|---|---|
| `node` | `order_placed` / `promised_delivery` / `production_start` / `production_end` / `dispatch` / `departure` / `arrival` / `delivery` |
| `baseline_planned_at`, `committed_due_at`, `latest_expected_at`, `actual_at` | 四类时间，缺证留 null |
| `qty`, `qty_status` | 节点数量与证据 |
| `observed_at`, `date_precision`, `timezone_status` | 观测时间、日精度、时区是否已证 |
| `source_record`, `note`, `rule_version` | 来源字段、口径说明、规则版本 |

规则：未发生不填实际；ETA 只进 `latest_expected_at`；POD/签收不等于可售；原计划保留供延期分析；节点数量只在来源单位（DN/工单）与订单单位一致时给出，否则 `qty=null`、`qty_status=unknown` 并在 `note` 说明。`dispatch` 按每张出库单拆成一行（`actual_at` 为该单过账日，`qty` 为该单过账数量，退货在阶段余额中净额抵扣），不把多张单的数量累加到最早日期。

### `availability_schedule`（分批可售片段）

| 字段 | 说明 |
|---|---|
| `tranche_id` | 稳定片段 ID：`<SO行>::<DN>::<仓库>::<DN明细行>::<单号>`（多运单末段为 `multi`）或 `<SO行>::<阶段>::<批次>`（跨订单行/跨仓库不重复） |
| `qty`, `qty_status`, `uom` | 片段数量与证据 |
| `available_date`, `latest_expected_at`, `date_kind`, `date_confidence` | 可售日（当前无入库/上架证据，恒为 null）与 ETA |
| `scenario` | `conditional` / `unknown` / `allocation_unknown` |
| `eligible`, `exclusion_reason` | 是否可进入补货计算（v1 全部 false），原因 |
| `batch_key`, `source_record` | 片段来源 |

规则：多运单 DN 不给数量（`allocation_unknown`），不复制 DN 全量；部分运单缺状态时不判到港；到港/签收不生成可售日；`over_produced` 超产实物不生成可售片段；未证一律 null。

### `links`（来源与分配证据）

`so / so_line_id / source_doctype / source_name / source_line_id / relation / target_doctype / target_name / target_is_record / qty / uom / proof / allocation`。
覆盖 SO→Item、SO 行→PP、SO 行→WO、WO→菲号、SO 行→DN、DN→Shipment（多运单时 `allocation=unknown` 且 qty=null；来源单位缺失或与订单单位不一致时 qty=null）。
`target_is_record=false` 表示 `target_name` 只是运单号/占位，不是已匹配的实体记录；覆盖数只统计 `target_is_record=true` 的 Shipment。

### `production_evidence`（四类生产证据，per SO line）

每行一条：`so`、`so_line`、`line_item_code`、`work_orders[]`、`subassemblies[]`、`all_process_done`、`first_process_done`、`qc_performed`、`qc_passed`、`stock_in_posted`、`conflicts`、`observed_at`。
每个类：`qty_proven`、`qty_estimated`、`confidence`（`proven/estimated/mixed/unknown`）、`qty_status`（`known/estimated/unknown`）、`started_at`、`completed_at`、`time_status`、`components`、`source_records`、`reasons`、`conflicts`。

规则：

- **资格**：只有 `confidence ∈ {proven, mixed}` 时 `qty_proven` 才可用于完成/阶段 3/待出库/known 里程碑；`estimated` 可披露但不触发完成。
- **物料**：行级数量只汇总 `production_item == SO 行 item_code` 的 WO；`PK#/ND#/DKND#` 子装配件进入 `subassemblies`，**不并入成品数量**。
- **单位**：UOM 缺失或与订单单位不一致 → 不求和，`qty_*=null` + `unit_missing/unit_mismatch`。
- **物理身份**：`confidence ∈ {proven, mixed}` 的行均可贡献其 `qty_proven` 子集；`estimated` 余量独立保留，不并入已证。
  多 WO 行级 proven 仅当各自 `proven_tracking_numbers` 两两不相交时成立；身份重叠 → `null` + `tracking_identity_overlap`，保留 per-WO 明细。
  WO 重放同载荷幂等，异载荷 `duplicate_wo_evidence_payload` → unknown。
- **取消工单**：不参与计划/工序进度；其已提交 Manufacture 入库净额作为独立事实保留，并输出 `wo_cancelled_with_valid_stock_in`。
- **时间**：优先取 Job Card 顶层 `actual_start_date/actual_end_date`；缺失时回退 `Job Card Time Log`
  的 `from_time/to_time`。仅当所有贡献记录时间完整时输出 `started_at=min` / `completed_at=max`，
  否则 null + `time_incomplete`；行级 proven 不成立时不输出行级时间。
- **QC**：`qc_passed.status` 按状态集合判定（全 Accepted / 全 Rejected；混合为冲突）；`qty` 保持 null/unknown，覆盖量不当作通过数量。
- **权限**：SO/PP/WO/JC/Tracking Number/DN/SE/QI 均先取 `get_list` 可读集合，受限单据不进入响应；
  JC 受限不影响 Stock Entry 入库事实；多行状态保守聚合（unavailable 不被后续成功覆盖）；
  查询失败写 `source_status` + `partial_reasons`，`partial` 在全部来源检查后重算。


### `shipment_progress`（最终物流状态，per DN×运单）

`so`、`so_line_id`、`item_code`、`dn`、`shipment`、`shipment_candidates`、
`identity_conflict`、`logistic_number`、`tongtool_po`、`warehouse`、`uom`、
`status11`、`status4`、`status4_normalized`、`status4_normalization`、
`status_semantics=unproven`、`eta/atd/ata/dlvr`、
`latest_progress_status`、`latest_progress_at`、`latest_progress_kind`
（actual/estimated）、`progress_source`、`is_final`、`conflict_flag`、
`conflict_reasons`、`progress_candidates`（含 status11/status4/事件原值）、`stage`、
`shipment_signed_at`、`tongtool_first/last/receipt_at`、`receipt_lag_days`、
`receipt_completion`、`received_qty/pending_qty`(+evidence_status)、
`receipt_basis=signed_assumed`、`identity_confidence`、`receipt_source_status`、
`inventory_inclusion_status`。

规则：status11（fine）+ status4（coarse，经 `status4-manual/v1` 映射）+ Shipment
Logistics Event 三来源；终态粘性；实际优先；`source_updated_at` 不提升阶段；
终态缺 `dlvr` → `shipment_signed_at=null`（不得用 `ata`）；ETA-only 不得证明实际在途；
阶段回退/同时间冲突/异常/撤销/人工值未映射 → unknown 或 conflict 并保留候选；
naive/date-only 时间不按 UTC 假定，若终态选择、阶段回退或同刻判断依赖未证时区 →
`time_order_unknown` + `timezone_unverified`，不伪造先后；
同号多 Shipment → `shipment_identity_conflict`，禁止 last-write-wins；
同 DN/物流号/Shipment 去重，退货 DN 不生成进度行。通途入库与库存未接入时
`receipt_completion=unknown`、`received/pending=null`、`receipt_source_status=not_integrated`、
`inventory_inclusion_status=unknown`。详见 STEP4/STEP5。

### `receipt_reconciliation`（签收→通途入库）

`shipment/dn/po_codes/sku/warehouse/uom/status/status_semantics/shipment_signed_at/
signed_status_proven/signed_time_status/tongtool_first|last|receipt_at/
receipt_time_status/receipt_lag_seconds|hours|days/receipt_lag_status/
receipt_completion/received_qty/pending_qty/over_receipt_qty/
received_evidence_status/pending_evidence_status/receipt_conflict/receipt_basis/
identity_confidence/coverage_status/receipts_outside_coverage/outside_coverage_qty/
receipts_time_unverified/exclusion_reason/receipt_duplicates/unmatched_receipt_rows`。

规则：输入必须带 link-specific collection coverage
（`query_range_complete`、非空且 `start<=end<=source_as_of` 的 `requested_windows`、
`truncated`、`not_collected`、`covered_po_codes`、`coverage_mode`）。`time_range`
模式的窗口并集必须连续覆盖 `[shipment_signed_at, source_as_of]`（检测窗口空档）；
`receipt.effective_at` 必须在窗口内，否则 `receipt_outside_coverage` 不计关闭量；
时间缺失/无时区无法定位的记录标 `receipt_time_unverified`，也不计关闭量。
来源按 PO 全历史时须显式 `coverage_mode=po_full_history` + `po_full_history_proven`
+ 来源 + `po_full_history_as_of`，且该截止必须等于 `source_as_of`；其早于
`shipment_signed_at` 时覆盖不完整；晚于该截止的 receipt 不计关闭量；
禁止用无关时间窗口冒充完整覆盖。早于签收的检查在窗口过滤前执行：全部身份匹配且
时间有效的 receipt 只要早于 signed_at 即 `receipt_before_signed` conflict（窗口外也成立），
同时保留 outside_coverage 审计。混合有效/无时区 receipt 时，窗口内有效数量仍汇总为
known，无时区行单独审计，`pending_qty` unknown 且禁止 complete/tongtool_received。
`ShipmentLink.signed_status_proven=true` 且 `signed_at=null` 时保持
`signed_pending_tongtool_receipt`，不得回退 `in_transit`。
**只有该覆盖完整时无 receipt 行才等于 0**；覆盖缺失/截断/scope 不匹配/时间不闭环 →
已观察 `received_qty` 可 known，但 `pending_qty` unknown、不得 `complete`、
不得进入 `tongtool_received`、不得输出关闭用 `tongtool_receipt_at`；
observed qty 超过 link qty 仍报 `over_receipt`；receipt 早于签收 → conflict；
时区显式校验；lag 输出秒/小时/天；缺有效时间不伪造 `tongtool_receipt_at`。
详见 STEP5。

### `inventory_bridge`（快照包含关系）

`receipt_id/line_id/po_code/po_line_id/dn_line_id/shipment_id/sku/warehouse/uom/qty/
receipt_effective_at/receipt_inclusion_status/inclusion_proof（结构化字典或 null）/
inclusion_proof_type/post_snapshot_delta_qty/conditional_delta_qty/eligible/
count_in_inventory/inventory_snapshot_id/source_as_of/snapshot_window_start|end/
snapshot_candidates/exclusion_reason/duplicate_of`。

规则：一次计算只绑定唯一快照身份，多快照/版本 → conflict（禁止 min(start)+max(end)）；
proof 逐 receipt 结构化（proof_type/source_record/receipt_identity/snapshot_id/
source_as_of），身份不一致 → conflict；summary 的 post-snapshot delta 按
SKU×仓×UOM 分组，禁止跨单位求和；input = included + duplicate + conflict +
unmatched + not_collected + after_snapshot + uncertain。详见 STEP5。

### 本地只读输入（严格 schema）

`--receipt-state-json` = `{schema_version:"supply-facts/receipt-state/v1", coverage, links, receipts}`；
`--inventory-bridge-json` = `{schema_version:"supply-facts/inventory-bridge/v1", coverage, snapshots, receipts}`。
coverage 必含 `query_range_complete`、`requested_windows`、`truncated`、`not_collected`、
`source_as_of`（带时区）、`covered_po_codes`；可选 `coverage_mode`（time_range 默认 /
po_full_history + `po_full_history_proven/source/as_of`，且 history as_of 必须严格等于
source_as_of）。布尔只接受 JSON true/false；
拒绝未知/缺字段、schema 不一致、重复身份异载荷、无时区时间、空 `requested_windows`
（time_range）、`start>end`、`source_as_of<window.end`、link `po_codes` 超出覆盖 scope、
time_range 携带 full-history 证明字段；`signed_at` 可为 null，`signed_status_proven`
为可选布尔；失败不创建 run、不切换 `latest.json`。

### `delivery_lines` / SO 关联边 / 三本账（v3.1，DN 明细为锚）

入口：`key_test.delivery_facts.get_delivery_facts(filters, scope)`，schema `supply-facts/v3`。
**scope 必须由 warehouse_restock 注入**（`source/version/hash/items`，API 校验 hash）；
服务端对客户端传入的 `status=provided` 也重新计算并比对 hash，不信任客户端结论；
hash 校验只证明内容完整一致，**不证明清单来自权威业务来源**（权威 scope 接入仍 pending）；
冻结 9-SKU 仅验收 fixture，不是业务批准全集；无 scope → relevance 全 unknown、E pending。

`delivery_lines` 稳定身份 `source_instance + delivery_note + delivery_note_item`；保留：
原始 DN/明细、docstatus、is_return、return_against、amended_from、source_modified；
`raw_signed_qty`（ERPNext 负数 qty 原值）与 `qty_magnitude`、uom/stock_qty/换算依据；
客户/公司/来源仓/目标仓及证据状态；过账时间/时区、observed_at；
SO/so_line/association_status 与候选 SO；relevance/scope；物流/PO/receipt/inventory；
数量方向、冲突与未知原因。仅提交 DN 计入实际交付；草稿/取消留痕不累加。

退货：`return_against + dn_detail` 必须匹配原 DN 明细；原单必须提交且
item/UOM/customer/warehouse 一致；负数与正数 qty 均按 magnitude 处理；
原行 actual 保持毛额、退货行 actual 为负，净额只扣一次；超退单独记 excess。
未匹配/身份冲突/原单不可读的退货 `actual_qty=null`、`quantity_status=unknown`，
计入未知行，不落成 0。

`association_status`：linked 必须同时满足 so_detail parent = against_sales_order、
SO 提交、item/UOM/customer 一致；否则 conflict；restricted 不泄露 SO 名称。
`candidate_so_lines` 仅人工审核。

三本账：`so_fulfillment` 只输出 so_open/unresolved_demand，**不输出 confirmed
additional supply**；`ambiguity_pools` 按 item×UOM×customer×warehouse×channel
做组级 min(open,pool)，不贪心分配、顺序无关；`supply_ledger` 只含 linked filled、
unresolved demand、unlinked delivery；`physical_chain` 多运单 qty=null、PO code_only、
receipt/inventory not_integrated。

API filters：`sales_order`、`customer`、`item_code`、日期、关联/范围状态、
`include_unlinked`（默认 true）、`include_inactive`、limit/offset。
筛选/分页同步裁剪全部六类数据集与 counts；`coverage.global` 为全量、
`coverage.query` 为当前筛选/页面（`aggregation_scope=query_page`）。
数量守恒只按 item×UOM×customer×warehouse×channel 分组；每组校验
`gross - matched_return == actual`（`arithmetic_ok`），`ok` 需无未知行且算术一致；
全局只报行数。

导出：`--delivery-all [--delivery-include-inactive --delivery-scope-json]`；
跨页校验 schema/rule/implementation/scope/hash/as_of/source status/snapshot_id；
`snapshot_id` 为全部过滤行的内容指纹：商品身份/范围、单位资格、SO 基准与派生汇总、
仓/客户/关联/物流/退货状态均参与；排除 observed_at，无变更重跑稳定，任一业务判定变化
都会改变 ID；混版本、漂移、重复键、写盘失败不创建 run、不切 latest。

### `supply_position`（第二批，PO 创建清单 × 状态 → 消费表）

模块：`supply_chain_visibility/supply_position.py`，schema `supply-position/v1`，
规则/实现版本 `2026-11-02.1`。导出器参数：`--po-manifests-json`、
`--po-statuses-json`、`--inventory-positions-json`、`--demand-positions-json`。

**行粒度**：`item_code × uom × warehouse × scope(in_house/external_fba) × branch × batch_key`，
一阶段一行；不跨批次或日期求和，全局不输出跨商品数量总和。

| 阶段 | 含义 |
|---|---|
| `po_open` | 状态 0，按创建清单 included 行计入开放供应 |
| `po_partial_allocation_unknown` | 状态 1/2，qty=null，禁止按 SKU 分摊 |
| `po_completed` | 状态 3，只关闭 included 行；不声称逐件实收 |
| `po_voided` | 状态 4，贡献 0 |
| `po_status_unknown` | 未知码/来源错误/未查询 |
| `po_in_snapshot` | 库存快照声明已包含该 PO，贡献 0，避免双计 |
| `dn_goods_unclosed` | mapping_failed / outcome_pending / error，PO 完成也不关闭 |
| `on_hand` | 库存快照；来源不可用时 qty=null + `inventory_source_unavailable` |
| `received_proven` / `receipt_unproven` | 有结构化纳入证明才计 receipt |
| `demand` | 需求；来源不可用时 qty=null |

**要点**
- 全部到货只关闭 included 行；遗漏行保持 unknown 并继续提示。
- 部分到货不分摊；状态来源错误不当“没有供给”。
- 历史 PO 无创建清单 → 列入 `legacy`（`no_creation_audit_manifest`），不伪造行，不阻塞其他商品。
- PO 完成晚于库存快照 → `post_snapshot_completion` + `completed_not_in_snapshot` 显式标记。
- `net.rows` 提供 on_hand/po_open/in_transit/demand 与 net_min/net_max 分键结果，供主线 A/B/C/D 净额；最终 `replenishment_decisions` 仍由主线负责。

**PO 状态刷新**：`po_status_refresh.refresh_po_statuses` 按 10 个/批、可断点续跑；
`rate_limited/partial/missing` 一律记 `unqueried`，不以 partial 当成功；SKU→PO 先去重。

### `full_supply_facts` v4（DN/PO + SO/生产/库存/在途/签收 + 本地 A/B/C）

模块：`supply_chain_visibility/full_supply_facts.py`，schema
`full-supply-facts/v4`，`RULE=2026-11-02.6`，
`IMPLEMENTATION=fzh.full_supply_facts@2026-11-02.6`。发布/读取：
`supply_chain_visibility/publication.py`（`supply-publication/v3`）。
ABC 归因：`supply_chain_visibility/abc_inputs.py`（`abc-frozen/v3`）。
流水线：`supply_chain_visibility/supply_pipeline.py`（`supply-pipeline/v4`）。

**主消费入口是 `full_supply_facts.parquet`；JSON 是逐行追溯副本；
`supply_position` 是同一次发布中的独立数据集，schema/粒度不同。**

#### 唯一键与身份

- 唯一键：`item_code × uom × warehouse × purpose × tt_sku × branch`；重复键直接失败。
- 非权威业务来源（SO/生产/库存/在途/签收）**只按完整键精确挂接**，不得填补缺失的
  branch/tt_sku。只有 B/A 的显式身份可以在**完整候选集合唯一**时填补 DN/PO 空维度；
  多个候选保持未归属并标 `target_key_ambiguous`。
- 缺失身份的数量留在未归属池（branch/tt_sku 为空），标明原因；不得因“当前只有一个
  候选”被后续来源认领。SO/生产/库存/签收/ABC 输入任意排列，业务结果一致。
- ABC 补齐命中**已有目标键**时禁止覆盖：不同已证 DN 明细来源合并求和并保留两段来源/
  时间片段；同源重放去重；无法证明则两行都保留并标 `abc_identity_key_conflict`。
  同一 ABC 键的库存载荷冲突标 `abc_inventory_key_conflict`，可信/当前数量清空，
  原始观察片段保留。

#### A/B/C 四层资格（不可混同）

1. **观察事实**：`inventory_observed_qty` + `inventory_observed_uom` +
   `observed_status` 始终保留 C 的原始数量与单位；真零保留 0。
2. **归属资格**：`attribution_status` / `attribution_eligible` / `inventory_qty` /
   `inventory_trusted`。C 必须 `join_class=join_full`、有 `source_ref`、有 UoM 与数量；
   否则 `c_not_qualified`，`inventory_qty=null`（即使 B 身份完整）。
   - B 必须同时给出 UOM；B/C 单位不一致或缺失 → `uom_mismatch`，观察量保留，
     `inventory_qty=null`、当前可用量 null。
   - 同商品同池多个 B 单位 → 每个 B 单位保留独立去向行；C 观察量只出现一次；
     `b_multi_uom_ambiguous`，不归入任何单一行。
   - A 不活跃 → `a_inactive`；B 身份冲突 → `b_identity_conflict`；
     B/C 版本冲突 → `version_conflict`；缺维度 → `partial_identity`；
     以上都不得升级为 `inventory_qty`。
   - 同一物理 CG 池被多个 branch 认领 → 每个身份一行、数量 null；另生成唯一池级
     未归因行承载观察量 + `cg_pool_shared_by_multiple_attributions`。
3. **当前可用**：`inventory_current_available_qty` / `current_available_eligible`
   仅在**归属资格成立 + 时间已证 + fresh（非 future）**时给出。
4. **下单资格**：`order_eligibility`（blocked/unknown）+ `order_blockers`，保留 B 原
   `可进净额`/限制原因、独立需求、C 资格、时间证明、单位冲突等阻断依据。
   `netting_ready=false`、`auto_order=false` 恒成立；当前库存可观测不等于允许下单。
   原因中已报告不合格（如 `c_not_qualified_for_netting`）时，不得同时保留可信或
   当前可用数量。

#### 时间证明与当前可用

- 只有带 offset/Z 的精确时间才 `inventory_time_proven=true`；date-only/naive 保留
  `inventory_date_age_days` 与 `inventory_as_of_raw`，但 `inventory_freshness=unknown_time`，
  当前可用量 null。
- 同一天内的未来时间按精确 `as_of` 识别为 `future`；陈旧按精确时间或日期级年龄判断。
- `inventory_current_available_qty` 仅在 **归属资格成立 + 时间已证 + fresh（非 future）**
  时给出；库存观察量、可信归属量、当前可用量三列分开。
- 时间字段 Parquet 为 `timestamp('us', tz='UTC')`；date-only/naive 不假定 UTC。

#### 来源身份、重放与冲突

- **来源身份与目标归属分开**：来源身份 = `source_ref`/`work_order`/单据明细 +
  `item_code`+`uom`；`warehouse`/`branch`/`purpose`/`tt_sku` 只是目标归属。
  同一物理来源跨目标出现且无分配证明 → `source_target_conflict`，每个目标行数量
  null；不得仅因目标键不同输出两份确定供应。
- 合法拆分必须提供 `allocation_id`（或 `line_id`）+ `allocated_qty` + `source_qty`；
  行内实际数量必须严格等于 `allocated_qty`，同一物理来源的 `source_qty` 声明必须一致，
  按 allocation 身份去重后的分配总量不得超过来源量。相同 allocation 同载荷重放只计一次；
  同 allocation 异载荷、实际量与分配量不一致、容量声明冲突、超容量或缺证明均标
  `source_allocation_conflict` 并将该来源的聚合量降为 null。该校验同样适用于同一目标内
  的多条 allocation，不能靠落入同一目标绕过。
- 每层定义稳定来源键：
  - SO：`source_ref`/`so+so_line` + 商品/UOM；
  - 生产：`source_ref`/`work_order|wo|name` + 商品/UOM；
  - 库存：`source_ref`/`snapshot_id` + 商品/UOM；
  - 签收：`source_ref`/`receipt_id`/`shipment` + 商品/UOM；
  - 物流：DN 明细 + 商品/UOM + Shipment/运单；目标仓/分公司/用途不同不构成新来源。
- 同身份同载荷 → 重放只计一次（`stage_quantities[].replay=true`）；
  同身份异载荷 → `source_payload_conflict`，数量 null，保留每个候选片段；
  不同身份即使数量/日期相同也各自保留。
- 缺来源身份 → `source_identity_missing`，汇总数量 unknown，不宣称可靠去重。
- DN/PO 的物理交付身份固定为 `instance + Delivery Note + Delivery Note Item`；
  创建审计、通途 PO 号和状态桶属于关系证据，不得进入物理身份。相同 DN 明细因 PO
  作废重建或审计重放再次出现时只计一次并保留全部关系证据；部分重叠集合按物理明细
  求并集。相同物理 DN 明细数量/状态桶冲突时标 `dn_physical_payload_conflict`，相关
  DN/PO 聚合量全部为 null，不得选择旧值或新值。
  上述规则也适用于单个 position 行内部：同一物理明细同载荷重放按并集重建聚合量；
  行内载荷冲突或明细不能完整解释聚合量时保留来源、聚合量降为 null。
- 物流同一运单跨多个 DN 行/目的仓/分公司 → 无分配证明时数量 null +
  `multi_waybill_allocation_unknown`/`multi_assignment_allocation_unknown` + 候选；
  冲突不取第一条作为代表归属；具备分配证明才允许拆分。
- `sources[]` 与 `stage_quantities[]` 携带 `source_identity`（单据/明细/批次/仓/分支等），
  可下钻到具体 WO/DN/C 记录；`summary.source_reconciliation` 给出每层
  输入行/物理身份数/重放/冲突/目标冲突/合法分配/缺身份/有效行。

#### 发布、manifest 与 reader

- 一次 run 输出 `full_supply_facts.parquet`（主）+ JSON（追溯）+
  `supply_position.parquet/json`（独立）+ `timeline.json` + `manifest.json`。
- 数量 `decimal128(38,6)`（JSON 规范化字符串）；`null` 与 `0` 严格不同；
  JSON 列（阶段片段/来源/未知原因/b_units/order_blockers 等）按声明契约保存。
- 空结果保留完整固定 schema；JSON/Parquet 逐字段回读、SHA、行数、唯一键全部通过
  才原子切换 `latest.json`；失败/截断/混版/重复键/写盘/回读失败不切旧 latest。
- manifest 每个数据集声明文件/格式/schema/rule/implementation/grain/unique_key/
  rows/SHA/source versions+hashes/as_of/observed_at/freshness/stale/stats/relations；
  `source_versions.ABC` 含 A/B/C 版本、SHA、行数、as_of、依赖关系、
  `c_declared_b_version`、`c_dependency_source`。
- 顶层 `inputs[]` 声明 role/path/sha256/rows/version/version_status/as_of/observed_at/
  time_status/completeness/truncated/partial_reason/temporal/status/
  required_for_closure/reason；`input_summary` 区分 provided/not_provided/
  version_unknown/contract_incomplete 与冻结输入副本。
- 动态业务来源缺时间 → freshness unknown（不被当作静态参考跳过）；reader 每次读取都
  按**本次读取时间**从已校验事实行的 `sources[].observed_at` 重算行级
  stale/unknown/future，不沿用发布时的 `row_level` 快照；文件级时间与行级时间任一
  stale/unknown/future → `stale`，新文件头不能掩盖旧业务行。一个月后读取旧快照不会
  是 healthy。`allow_stale` 仅在显式放行时使 stale/partial/refresh-failed 可读，
  不改变 freshness 状态；corrupted/incompatible 永远不可读。

#### 输入完整性契约

- 多页 audit/status：**缺版本页 + 有版本页直接拒绝**（`mixed_input_versions:*:missing_version`）。
- SO/生产/库存/在途/签收：必须为对象且含行数组；**真正的分页截断**
  （`truncated=true`、`pagination.exhausted=false`、`pagination.partial=true`）→
  拒收（`input_truncated:<role>`）。**合法业务 partial**（`partial=true` 且分页已
  exhausted）→ 不拒收：该层已知片段与来源保留、汇总数量 unknown，manifest/
  `output_summary`/reader 的 `partial_reason` 含 `business_partial`，其他独立层照常输出。
  缺版本/时间 → `completeness=incomplete`，该层汇总 unknown，不得包装成完整快照。
- audit/status 分页 partial → 保留事实但标 partial（`partial_reason` 区分
  `pagination_not_exhausted`/`business_partial`/`truncated_flag`），DN 数量不被清空。
- 来源状态保守聚合：unavailable/conflict/partial 不会被后到的 known 覆盖。
- A/B/C 输入契约：source/version/sha256/row_count/as_of；哈希/行数不符拒收；
  C 的 workbook 显式依赖与命令行声明冲突 → `c_dependency_conflict`；
  多个依赖标记 → `c_dependency_ambiguous`；命令行不得覆盖原件声明。

#### 冻结输入与复跑

- 发布时把所有**参与计算**的输入（非 `not_provided`）复制到 `run_dir/inputs/`，记录
  `frozen_path`/`frozen_sha256`/`frozen_size`；`provided_count` 必须等于
  `frozen_count`，否则不能声明可复跑。
- 已参与计算的输入在冻结时缺失、provided 但无 path、解析后内容改变、复制/权限失败
  → **终止发布**，保留旧 `latest.json`，不留下成功 run；只有 `not_provided` 才是
  “本来没有的可选来源”。源文件后续修改/删除不影响已冻结副本。
- manifest `rerun.argv` 使用 `{run_dir}`/`{out}` 模板；`rerun.command` 是可直接执行的
  PowerShell 命令（`--replay-run`）；`rerun.effective_args` 含默认参数与版本。
- `python -m supply_chain_visibility.supply_pipeline --replay-run <run_dir> --out <new_out>`
  先校验冻结输入字节，再从副本复跑；业务内容 SHA 稳定，run_id/generated_at 可变。
  含空格/中文路径已测试。

#### 可执行链路

```bash
uv run --with pyarrow --with openpyxl python -m supply_chain_visibility.supply_pipeline   --delivery-json ... [--mapping-json ...]   [--audit-json ...] [--status-json ...]   [--so-json/--production-json/--inventory-json/--transit-json/--receipt-json]   [--a-workbook ... --b-workbook ... --c-workbook    --a-version ... --b-version ... --c-version [--c-declared-b-version ...]]   --as-of <aware> --out <private>
```

**真实 A/B/C 冻结工作簿链路验收仍 pending**：本机暂不可用；不得用合成数据冒充。

### `manifest`

`schema_version=supply-facts/v3`（并保留 `supply_facts_schema_version` 与
`delivery_schema_version`）、`rule_version`、`implementation_version`、`run_id`、`as_of`（快照日）、`as_of_kind=current_snapshot`、`observed_at`（采集时刻）、`generated_at`、`scope`、`coverage`（来源/权限/`restricted`/`source_status`（逐来源 `{available, reason}`，
含 `shipment_logistics_event`）/`external_sources`/`delivery_scope`/`delivery_pagination`）、`counts`、`partial`、`truncated`、`termination_reason`、`pagination`、`partial_reasons`、`notes`、`files`（相对路径 + sha256）、`performance`。

## 2. 批量入口

```bash
# 单 SO
uv run python EN_API/supply_facts_export.py --so SO-26-00026 --test

# 客户码/物料码（自动判型）
uv run python EN_API/supply_facts_export.py --codes "TT0031038K0062927,CENCord995-DKGrey-97" --test

# 全范围（分页）
uv run python EN_API/supply_facts_export.py --all --test --page-size 500
```

### 2.1 filters 白名单与分页契约（2026-10-29）

```text
GET/POST /api/method/key_test.supply_facts.get_supply_facts
filters = JSON object
```

允许的 filters：`sales_order`、`so_line`、`customer`、`item_code`、`customer_item_code`、`warehouse`、`stage`、`from_date`、`to_date`、`as_of`、`include_delivered`、`limit`、`offset`。

- **未知 filter**、**顶层误传参数**（如 `?sales_order=...` 不在 `filters` 内）直接 `ValidationError`，不再静默忽略或扩大为全量。
- Frappe 分发注入的 `cmd` / `csrf_token` / `_` 由服务端忽略；除它们之外的其他顶层参数一律报错。
- 当前 `implementation_version=key_test.supply_facts@2026-10-30.6`；`rule_version=2026-10-30.1`；
  delivery facts 使用 `schema=supply-facts/v3`、`implementation=key_test.delivery_facts@2026-10-30.2`；
  接口/分页行为变更必须 bump，混合版本继续拒绝。
- 排序：SQL `order by so.name, soi.name`，响应 `sort=["so","so_line"]`、唯一键 `so_line`，两者必须一致。
- `sales_order` / `so_line` / `customer` / `item_code` / `customer_item_code` / `warehouse` / 日期 / `include_delivered` 是**行选择**；`warehouse` 指 SO 行目标仓。
- `stage` 是**事实层**过滤（裁剪 `stage_balances` / `availability_schedule`），不改变行分页。
- `limit` 默认 500、最大 2000；`offset` ≥ 0。
- 响应新增 `applied_filters` 与 `pagination`：`limit/offset/returned/total/next_offset/next_cursor/exhausted/partial/termination_reason/sort/unique_key`。
- `pagination.partial` 只表示本页被 limit 截断；`manifest.partial` 表示业务来源不完整（权限受限/通途 PO/入库/目的仓未接入）。**`exhausted=true` 时 `manifest.partial` 仍可为 true。**
- 排序固定 `so, so_line`，唯一键 `so_line`；两页不重不漏。
- 单 SO 请求只返回该 SO；`so_line` 已在 SQL 层限制。

```bash
# 单 SO，第二页
filters={"sales_order":"SO-26-00103","limit":50,"offset":50}

# 仓库 + 阶段
filters={"sales_order":"SO-26-00103","warehouse":"美中-FZH-DANEEY","stage":"in_production"}

# 错误示例：unknown / 顶层参数
filters={"bogus":1}                 # Unknown filter(s)
?sales_order=SO-26-00103            # Unknown parameter(s)
```

输出：`EN_API/out/supply_facts/runs/run-<ts>-<id>/` 下 9 个 JSON（含 `production_evidence.json`、`shipment_progress.json`、`receipt_reconciliation.json`、`inventory_bridge.json`）+ `supply_facts.xlsx` + `manifest.json`；
`latest.json` 原子指针指向最后一次成功版本。写失败不切换指针，旧版本保持可读；`partial` 显式标记缺源。多批次合并前校验 `schema_version` / `rule_version` / `implementation_version` / `as_of`，任一不一致即拒绝该批次并终止导出，不写新版本，`latest.json` 仍指向上次成功版本。

## 3. 人工视图

SO Chain Overview 的链条弹窗新增「数量阶段 / 节点 / 分批可售」三段，调用与批量导出相同的
`key_test.supply_facts.get_supply_facts`（按 SO + 订单行）。弹窗按具体订单行请求时携带
`include_delivered=1`，已发完订单行仍展示历史事实，与机器导出范围一致。
工单数/菲号数仍只作导航，数量以阶段余额为准。

SO 表单链条面板（`sales_order.js`）另展示生产证据：全工序（proven/estimated/unknown）、入库净额、
QC 状态、confidence、主要原因/冲突，以及子装配件（PK#/ND#）独立证据；仅两侧 `known` 才做差异标黄。

> **范围声明（2026-10-29）**：`SO Chain Overview` **原生报表**仍是 legacy 数量口径
> （`supply_query.get_report_data`，首工序/出库），**不在第三步统一证据范围**；其数量列不得用于
> 证明生产完成。统一生产证据仅见 SO 表单链条面板与批量导出。


## 4. 产品要求 → 已复用 → 缺口 → 本周交付

| 产品要求 | 已复用实现 | 本轮交付 | 缺口 / 限制 |
|---|---|---|---|
| 供应数量归属（互斥阶段余额） | `supply_facts.build_stage_balances`、工序卡首工序、DN 净额、Shipment 14 态 | 六阶段 + 取消/退货/草稿/未知；守恒差额显式 | 到仓验收/上架无 EN 证据，`delivered_sellable` 不产出；PO/入库未并入 EN 事实 |
| 节点数量与日期 | WO 计划日期、JC 实际、DN 过账、Shipment atd/ata/dlvr/eta | 8 类节点 × 原计划/承诺/最新预计/实际 | 无独立承诺字段；ETA 未证；时区未证 |
| 分批可售 | DN/运单、Shipment ETA、批次键 | 稳定 tranche_id、数量/日期/资格/排除原因 | 无入库/上架证据 → `eligible=false`；多运单不摊量 |
| 用途及预留 | `scope`（in_house/external_fba）、`role` | 片段携带用途与角色，FBA 不可进补货边界 | 预留量无 EN 来源；自由量未扣预留 |
| 多运单 1:N | `Delivery Note Logistics Number` + Shipment 映射 | links 保留 1:N；无分配证据 qty=null | 无物料行级分配证据 |
| 机器消费 | 一个批量方法 + 本地 CLI | JSON/Excel + manifest + sha256 + latest 指针 | Parquet 未生成；刷新任务未部署 |
| 人工查链路 | SO Chain Overview 弹窗 | 阶段余额/节点/可售片段下钻 | 主表未加数量列（弹窗展开，符合契约） |

## 5. 验收（测试站）

- 契约单测：49 项（8 类案例 + 草稿 + estimated + 单位校验/继承 + 退货原明细归属/容量账本/顺序不变性/超退/引用冲突/无法归属/同仓聚合 + 退货逐明细读取贯穿 + 工单覆盖/开工证据 + 生产计划覆盖/单位校验 + 超产现存与累计 + 取消实物 + 片段仓库/ID + 运单状态齐全性 + 出库节点拆分 + 已发完行 include_delivered + 弹窗参数 + 行级权限 + 全部受限 + 版本字段 + 历史 as_of 拒绝 + 空结果完整性），另有 7 项批次合并/版本一致性测试；本地全绿。
- **2026-10-29 第二批复审整改（本地）**：key_test 全量 238 passed / 3 skipped / 4 subtests；导出器 27 passed；`supply_chain_visibility` 104 passed / 5 subtests；Node 渲染 8 项。覆盖：真实 `get_so_chain` 不报错、KS/PK#/ND# 不串量、跨 UOM 不求和、重叠/重复 WO 不重复、mixed 行保留已证子集、unknown/estimated 不触发 complete/阶段 3/known、Job Card Time Log 补足时间且失败只降级时间、PP/DN/JC/TN 行级权限不泄露、多行来源状态保守聚合且保留 reason、取消 WO 入库事实可达、导出 JSON/Excel/manifest 行数与 SHA-256 一致且失败不切换 `latest.json`。版本 `RULE=2026-10-29.5` / `IMPL=key_test.supply_facts@2026-10-29.4`。
- **2026-10-29 测试站部署与真实验收**：测试站 key_test `dd66b08` → `36b016f`（表尾文案修复），`bench restart` + `clear-cache`；bench app 测试 **241 OK / 9 skipped**。真实 HTTP：合法 GET/POST 200；未知 filter/顶层参数/非法 stage/limit/offset 均 417 ValidationError；分页 3 页无重无漏、越界页 `offset_out_of_range`。`get_so_chain`：SO-26-00026（proven/unknown/入库净额/QC 已检/子装配件）、SO-24-00011（estimated 显示估算）、SO-26-00021（双 known 差异标黄）；浏览器无持久控制台错误；真实 Time Log 记录级回退通过、注入查询失败不影响已证数量；全量导出 293 行 / 6 JSON + Excel + manifest，production_evidence 290 行一致、SHA-256 全对、版本正确、exhausted，失败保护通过。**普通受限用户 HTTP 权限验收仍 pending：缺少合法受限用户凭证（现行 TEST key 为 System Manager），未获豁免、不作为通过项。** 生产未部署。
- 单 SO `SO-26-00026`：3 行 / 8 阶段余额 / 16 里程碑 / 6 可售片段 / 17 关联；查询约 0.8s。
  三行阶段余额守恒 10 / 5 / 8（草稿不计数量；KS 无工序卡时用 produced_qty 标 estimated）。
- 全范围（含取消订单）：292 行 / 308 阶段余额 / 656 里程碑 / 287 片段 / 404 关联；查询 0.30s，总计 0.85s。
- manifest：`partial=true`（PO/入库/可售来源未接入）、`external_sources`/`restricted` 可见、`observed_at` 与 `as_of` 分离、文件路径为相对路径且逐个存在、`termination_reason=exhausted`；空结果/全部受限保留 `empty_reason`。
- 服务端历史 `as_of` 拒绝（REST 验证）；批次合并：`restricted` 按 OR、`sources` 按 AND、外部来源保守保留 `not_integrated`、时间戳取最早。
- 9 SKU：生产只读解析出 99 张 SO；测试站无该样本数据，**待生产授权后验收**（本任务未授权生产部署）。
- 普通角色权限：已改为按 `get_list` 可读集合取数，并有受限角色单测；线上普通角色端到端仍待验证。

## 6. 待业务确认

1. 到仓验收/上架/可售的权威来源（当前 EN 无，导致可售日恒为未知）。
2. 承诺日期字段（当前无独立字段，暂用 SO 交期）。
3. FBA/自发货预留量与自由供给的权威口径。
4. 多运单 DN 的物料行级分配规则（无证据前不摊量）。
5. 刷新频率与陈旧阈值（30 分钟为候选，未部署）。
6. 9 SKU 验收所需的生产只读部署授权。
