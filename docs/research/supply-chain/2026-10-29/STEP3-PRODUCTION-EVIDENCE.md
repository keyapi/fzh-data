---
okf: v0.1
type: Spec
title: 第三步：四类生产证据的权威来源、数量推导与验收矩阵（只读设计 v2）
date: 2026-10-29
updated: 2026-10-29
owner: claude-worker
status: batch-1-evidence-layer-implemented-locally; consumers not switched; no production deploy; step-2 permission acceptance still pending
scope: read-only; test-station evidence only; no business data writes; no permission expansion
tags: [supply-chain, production-evidence, job-card, stock-entry, quality-inspection, work-order, acceptance]
---

# 第三步：生产证据拆分（只读设计 v2）

> 本文件只回答一个问题：**每个“完成”究竟由什么证据支持**。不修改业务算法、不部署生产、
> 不写业务数据、不扩大权限、不新增业务流程。第二步权限待验项仍独立追踪，不因本文件改写为通过。

## 0. v2 修订说明（对应 Codex 六项）

| # | 修订 | v2 口径 |
|---|---|---|
| 1 | 批次身份与完成量 | 不再把无菲号记录统一归入 `(WO,'__batch__')` 的“已证”池；无共同实物身份时只能 `estimated/unknown`，不得作为已证 `all_process_done`。并行首工序同理，只有共同身份交集才算已证。 |
| 2 | 经验 `max` 的资格 | 保留 TN 池/批卡池两个原始分量；`max` 只是经验估算，**不得抬高已证完成量**。已证值只来自有共同身份的交集。 |
| 3 | 完成时间 | `first_process_done` 的完成事件取**完成记录的结束时间**；开工时间另列。`creation/modified` 是来源记录的创建/修改时间，不是采集时间；采集时间用 `observed_at`。 |
| 4 | 入库退货公式 | 拆成「非退货入库毛额 − 规范化退货量」；逐行只处理一次；保留毛额、退货额、净额与冲突。`+10` 与 `-10` 原始退货都规范化为 10，净额都只能是 90（毛额 100 时）。 |
| 5 | QI 关联与覆盖量 | 测试站 `Quality Inspection.reference_type` 真实选项为 `Purchase Receipt / Purchase Invoice / Subcontracting Receipt / Delivery Note / Sales Invoice / Stock Entry / Job Card`，**没有 Work Order**。按真实类型关联并校验物料/覆盖身份；`Accepted + sample_size` 不能推出通过数量，`qc_passed.qty` 仍为 unknown。 |
| 6 | 取消与独立实物证据 | 取消 WO 只排除其计划/进度；仍有效的已提交 SE 保留为入库事实并单列冲突。父单取消不能自动作废另一张有效库存凭证。 |

## 0.1 结论速览

1. **四类证据互相独立，不能替代。** 测试站实测：
   - `WO-25-00277`：批卡口径估算全工序/已检 36，但无共同实物身份（未证）；入库只有草稿 36，已提交 0；
   - `WO-26-00024`：入库已提交 6，但全工序 0、质检仍 `Work In Progress`；
   - `WO-25-00276`：已证全工序 3（菲号身份），入库 5，入库领先于工序证据。
2. **`qc_passed` 在当前数据上不可证。** `Quality Inspection` 0 条；`Job Card.quality_inspection` 0/676；
   质检卡只证明“已检”（`qc_performed`），不证明“通过”。`sample_size` 不是通过数量。
3. **`Work Order.produced_qty` 不是工序完工量。** 它是已提交 `Manufacture` 入库单的回写缓存；
   G1b 已实测 2 例无法由可见单据解释（739/103、812/100），入库以 Stock Entry 明细为准。
4. **`Work Order Operation.completed_qty` 不是实际完工的权威。** 工单重建/孤儿报工会让它为 0，
   而 Job Card 仍有完工量；返工工序也会 op=0 但 JC>0。routing 只作分母/计划结构。
5. **数量必须按共同实物身份取交集。** 禁止跨工序求和；禁止仅取最小工序量宣称整批完成；
   禁止把整批卡与逐菲号卡相加；无身份依据的 `max/min` 只能标 `estimated`。
6. **时间缺失是常态。** 测试站有“已完成但无实际时间”的裁剪切；缺失一律 `null/missing`，
   不用 WO 状态、`creation` 或过账日期推断。

## 0.2 已证 / 估算 / 未知（汇总资格）

| 置信度 | 定义 | 进入阶段余额的资格 |
|---|---|---|
| `proven`（已证） | 有共同实物身份（菲号，或明确的 `batch_no`/`serial_and_batch_bundle`/`stock_tracking_number`）且满足全部状态/数量/单位条件 | 可进入阶段余额的 **known** 部分；可作为 `produced_pending_dn`、`over_produced` 等事实 |
| `estimated`（估算） | 经验 `max/min`、无身份批卡池、并行首工序无共同身份、缓存交叉值等 | 只能进入**单独的 estimated 披露**；**不得与 proven 相加**，不得抬高已证完成量，不得作为已证待出库 |
| `unknown`（未知） | 缺来源、权限受限、单位不一致、身份冲突、QI 覆盖量缺失、取消/歧义 | 进入 `unknown` 阶段并给原因；**不得当作 0** |

> 阶段余额实现时应区分 `qty_proven` / `qty_estimated` / `qty_unknown`（或 `qty_status` + `evidence_confidence`）；
> 三者不得混合求和。`produced_pending_dn` 的 known 部分只来自 `proven`。

## 1. 四类证据来源表

### 1.1 总表

| 证据类 | 权威单据 | 关键字段 | 关联键 | 数量与置信度 | 单位 | 时间 | 有效状态 | 不能证明 |
|---|---|---|---|---|---|---|---|---|
| `first_process_done` | `Job Card`（事件）+ `Work Order Operation`（路由/分母） | JC: `work_order`, `operation`, `operation_id`, `status`, `docstatus`, `total_completed_qty`, `tracking_number`; WOO: `sequence_id`, `operation` | `WOO.parent = WO.name`；`JC.work_order + JC.operation`（+`operation_id` 防孤儿）；`JC.tracking_number = TN.name` | 首阶段（最小 `sequence_id`）必经工序完成量；同序并行工序只有**共同身份交集**才算 proven；无共同身份 → estimated；批卡/菲号不得相加 | `WO.stock_uom`；须与 `SO Item.uom` 一致，否则 unknown | **完成事件**取完成记录 `actual_end_date`/Time Log `to_time`；开工时间另列；缺失 null | JC `docstatus=1` 且 `status='Completed'`；排除 corrective | 不能证明全工序完成、质检通过或入库 |
| `all_process_done` | 全部必经 `Work Order Operation` + 对应已提交 Job Card | 同上；逐工序 `operation`/`sequence_id`/`total_completed_qty` | 同上；批卡要求明确共同身份键 | 按共同实物身份取交集：菲号池；有身份批卡池；两池同时存在且重叠未知时，`all_proven` 为 null，只给两个分量；无身份批卡只能 estimated | 同上 | 完成单位的最晚必经工序 `actual_end`；开工另列；缺失 null | 同上；排除 corrective / 取消 | 不能证明质检通过或入库 |
| `qc_passed` | `Quality Inspection`（若启用）；`Job Card` 质检仅证明“已检” | QI: `status`, `docstatus`, `reference_type`, `reference_name`, `item_code`, `sample_size`, `stock_tracking_number`; JC: `operation='质检'`, `status`, `docstatus`, `total_completed_qty`, `quality_inspection` | **真实类型**：`QI.reference_type='Job Card'` → `reference_name=JC.name`；`QI.reference_type='Stock Entry'` → `reference_name=SE.name`；或 `JC.quality_inspection=QI.name`。**没有 Work Order 选项** | QI `Accepted` 只给状态；`sample_size` 不是通过量；无显式覆盖数量 → `qc_passed.qty=unknown`；JC 质检量只作 `qc_performed` | `WO.stock_uom` | QI `report_date`；JC `actual_end_date`；缺失 null | QI `docstatus=1` 且 `status='Accepted'`；JC `docstatus=1` 且 `status='Completed'` 仅“已检” | 不能证明全部实物通过；当前测试站无法证明任何 `qc_passed.qty` |
| `stock_in_posted` | `Stock Entry`（`purpose='Manufacture'`）+ `Stock Entry Detail` | SE: `work_order`, `purpose`, `stock_entry_type`, `docstatus`, `posting_date/time`, `is_return`, `outgoing_stock_entry`; SED: `is_finished_item`, `item_code`, `qty`, `uom`, `stock_uom`, `t_warehouse`, `batch_no`, `stock_tracking_number`, `against_stock_entry` | `SE.work_order = WO.name`；`SED.item_code = WO.production_item`；`SED.uom = WO.stock_uom`；退货引用 `outgoing_stock_entry`/`against_stock_entry` | **非退货毛额 − 规范化退货量**：`gross=Σ(is_return=0)`，`return=Σabs(qty)(is_return=1)`，`net=gross-return`；逐行一次；保留毛/退/净/冲突 | SED `uom/stock_uom`；按 `(WO, UOM)` 分桶；混单位 → unknown | `SE.posting_date + posting_time`；`creation/modified` 只算来源记录时间 | `docstatus=1`；`is_finished_item=1`；退货单独规范化 | 不能证明工序完成或质检通过 |

### 1.2 字段级说明

#### first_process_done

- **分母**：`Work Order Operation` 中 `Operation.is_corrective_operation = 0` 的工序；返工分支
  （测试站：`缝制返工`、`裁剪返工`、`通用返工`、`质检发现问题`）**不计入**。
- **首阶段**：`sequence_id` 最小的必经工序；同一 `sequence_id` 有多道并行工序时，**全部都是首阶段工序**。
- **已证条件**：同一实物身份（菲号，或有明确批号/序列号的批卡）在**每道**首阶段工序都有
  `Completed` 且 `docstatus=1` 的 Job Card，且完成量 ≥ 该身份数量；只有这些身份的数量才算 `proven`。
- **无共同身份**：只把各首阶段工序的 `max`/`min` 作为 `estimated`，不得标为已证首工序完成。
- **完成时间**：取对应完成记录的 `actual_end_date` / Time Log `to_time`；`actual_start_date` / `from_time`
  另列 `started_at`，**不能**把开工时间当完成时间。

#### all_process_done

- **必经工序全集**：`Operation.is_corrective_operation = 0` 的所有 `Work Order Operation`；
  并行工序也算必经，不能只取最大 `sequence_id` 的末道。
- **共同身份**：
  - 菲号：`Tracking Number` 是已证身份；每个菲号在每个必经工序都要有 Completed JC 且完成量 ≥ 菲号数量。
  - 批卡：只有带明确身份键（`batch_no`、`serial_and_batch_bundle`、`stock_tracking_number`、
    `custom_batch_no`）的整批卡才能形成“有身份批卡池”；无这些键的整批卡只是同一 WO 下的多条无身份记录，
    **不能**证明是同一批实物。
- **已证计算**：
  - `tn_all_proven` = 满足全工序条件的菲号数量之和；
  - `batch_all_proven` = 有身份批卡池中，各必经工序同一身份完成量的最小值（且每道工序都有该身份）；
  - 只有一个池有值时，`all_proven` = 该池；
  - **两池同时有值且重叠关系未知**：`all_proven = null`，只输出 `tn_all_proven`、`batch_all_proven`、
    `overlap_status='unknown'`；`max(两池)` 只能作为 `all_estimated_max`，**不得**升级为 proven。
- **无身份批卡池**：`batch_all_estimated = min(各工序整批卡量)`；它与 TN 池的 `max` 也只是 estimated。
- **聚合最小量的地位**：`min(各工序完成量)` 只是在同一身份池内的诊断值；没有身份交集时，
  不能把聚合 min 当成“同一批实物全部完成”。
- **无工序工单（成品 KS）**：`all_process_done = null/not_applicable`，不得用入库反推工序完成。

#### qc_passed

- **测试站事实**：`Quality Inspection` 0 条；`Job Card.quality_inspection` 0/676；
  `Quality Inspection.reference_type` 选项只有 `Purchase Receipt / Purchase Invoice /
  Subcontracting Receipt / Delivery Note / Sales Invoice / Stock Entry / Job Card`，**没有 Work Order**；
  `status` 只有 `Accepted / Rejected`；`sample_size` 是抽样数，不是通过量。
- **关联**：优先 `Job Card.quality_inspection = QI.name`；否则 `QI.reference_type='Job Card'` +
  `reference_name=JC.name`；或 `reference_type='Stock Entry'` + `reference_name=SE.name`。
  必须校验 `QI.item_code` 与成品一致、`stock_tracking_number`/批次身份能对上；挂不上 → `unallocated`，不摊量。
- **已检 ≠ 通过**：`Job Card.operation='质检'` 且 `status='Completed'` 只证明质检动作执行，
  只能输出 `qc_performed`；没有 pass/fail 结果字段。
- **Accepted ≠ 覆盖量**：QI `Accepted` 只表示检验结论；`sample_size` 不是通过数量；
  没有显式覆盖数量时，`qc_passed.status='Accepted'`、`qc_passed.qty=unknown`，
  原因 `coverage_qty_not_available`。**不能**用 QI 推导整单通过量。
- **业务假设**：若业务确认“质检 Job Card Completed 即视为通过”，属于需要书面确认的口径变更；
  必须 bump `RULE_VERSION` 并在契约中显式标注，不能由实现默认。

#### stock_in_posted

- **入库权威**：`Stock Entry.purpose='Manufacture'` 且 `docstatus=1`，成品行
  `Stock Entry Detail.is_finished_item=1`；数量取 `SED.qty`，单位取 `SED.uom`（须等于 `WO.stock_uom`）。
- **毛额/退货/净额**：
  - `gross_qty` = 已提交 Manufacture、`is_return=0`、finished 行的 `qty` 合计；
  - `return_qty` = 已提交 Manufacture、`is_return=1`、finished 行的 `abs(qty)` 合计；
  - `net_qty` = `gross_qty - return_qty`；
  - **逐行只处理一次**：退货行不得再计入 `gross_qty`；原始 `+10` 与 `-10` 都规范化为 10；
    例：入库 100、退货原始 `+10` 或 `-10`，`gross=100`、`return=10`、`net=90`。
  - 保留 `gross_qty`、`return_qty`、`net_qty`、`return_rows`、`conflicts`，不得只输出一个净数。
- **退货归属**：`outgoing_stock_entry` / `against_stock_entry` 指向的原单、物料、单位、WO 必须能对上；
  对不上 → `return_unallocated` 冲突，不从本 WO 扣除；缺引用但物料/单位/WO 能对上 → 扣除并标
  `return_reference_missing`；同一退货行只扣一次。
- **`produced_qty` 只是缓存**：只作 `produced_qty_cross_check`，不作为入库证据。
- **`fg_completed_qty` 只作交叉核对**：已提交单通常与明细合计一致（G1b C3 425/425），
  草稿单可能不一致（测试站 `STE-25-00092`：`fg_completed_qty=3`、成品明细=2）；数量以明细为准。
- **状态**：草稿是候选/未生效，不是证据；取消排除；退货按上式计算。

## 2. 数量推导规则

### 2.1 身份、去重与置信度

| 问题 | 规则 |
|---|---|
| 菲号身份 | `Tracking Number` + `JC.tracking_number` 是已证身份；每个菲号每工序应有 1 张 Completed JC；数量取 `TN.qty` 与实际完成量的较小值，且必须 ≥ 身份数量才计为完成 |
| 无菲号批卡 | 只有带明确 `batch_no`/`serial_and_batch_bundle`/`stock_tracking_number`/`custom_batch_no` 的批卡才有共同身份；否则只能 estimated |
| 工序内重复报工 | 同一 `(WO, operation, tracking_number)` 出现多张 Completed JC → 冲突，该身份该工序 `unknown`，不求和、不静默取 max |
| 整批卡 + 逐菲号卡 | 分别汇总 `batch_qty` 与 `tn_qty`，保留两个原始分量；有身份时分别计算；无身份时 `max` 只是 estimated；**不得相加** |
| 两个池同时存在 | 输出 `tn_all_proven`、`batch_all_proven`、`overlap_status`；重叠未证时 `all_proven=null`，`max` 只作 estimated |
| 多个工单 | 每张 WO 独立记账；按 SO 行汇总只带 `batch_key=WO`；不得把多张 WO 合成一个“同一批实物” |
| 拆分工单（`-S###`） | 视为独立 WO；父子字段只用于展示；合并需菲号/批次身份证据，否则 `allocation_unknown` |
| 同一菲号跨 WO | 菲号全局唯一；只计一次，标记 `cross_wo_tracking_conflict` |
| 返工/纠正工序 | 不计入必经工序分母；若返工发生在质检之后，受影响单元 `qc_passed` 置 `review_required/unknown`，除非之后有新的通过证据 |
| 取消 | 取消 WO 只排除其计划/进度；已提交且仍有效的 SE 保留为入库事实，并单列 `wo_cancelled_with_valid_stock_in` 冲突；取消 JC/SE 排除 |
| 草稿 | JC docstatus=0、SE docstatus=0 不是完成/入库证据；只作候选提示 |
| 超产 | 保留原始完工/入库量；按订单分配时最多按订单量，超出部分单独 `excess`，不截断原始证据 |
| 单位 | 只在同一 UOM 内求和；`WO.stock_uom` 缺失或与 `SO Item.uom` 不一致 → `unknown`，不做换算 |
| 权限 | 任一来源不可读 → `unknown` + `reason=permission`，**不得当作 0** |

补充：

- `Job Card.total_completed_qty` 是完成量权威；Completed 但为 0 的卡记 `qty_missing`，
  **不得用 `for_quantity` 回填**（`for_quantity` 是计划量）。
- `Tracking Number.qty` 缺失时，该菲号不能判定为 `all_process_done`，也不得用 Job Card 数量回填。
- `creation/modified` 只是来源记录创建/修改时间，不是事件或采集时间。

### 2.2 计算公式（伪代码）

```text
required_ops(wo) = [op for op in WorkOrderOperation[wo] if not op.is_corrective_operation]

# —— 菲号池（已证身份）——
tn_op_done(wo, op, tn) = has_CompletedSubmittedJC(wo, op, tn) and jc_qty >= tn.qty
tn_first_proven(wo)    = sum(tn.qty for tn in TNs if all(tn_op_done(wo, op, tn)
                          for op in required_ops with min_sequence))
# 无菲号时：只有带明确身份键的批卡才能形成 first proven；
# 无身份批卡的首阶段量只能 first_estimated。
first_proven(wo) = tn_first_proven(wo) if TNs else batch_first_proven(wo)  # 后者需身份键
first_estimated(wo) = min(各首阶段工序的无身份批卡量)  # 仅估算
tn_all_proven(wo)      = sum(tn.qty for tn in TNs if all(tn_op_done(wo, op, tn)
                          for op in required_ops))

# —— 批卡池 ——
# 只有带明确身份键的批卡才可形成 batch_identity；无身份只能 estimated。
batch_identity_qty(wo, op, id) = sum(CompletedSubmittedJC qty where identity=id and tn="")
batch_all_proven(wo) = min(batch_identity_qty(wo, op, id) for op in required_ops)
                       if same id exists in every required op else None
batch_all_estimated(wo) = min(sum(CompletedSubmittedJC batch qty) for op in required_ops)
                          # 无共同身份；仅估算

# —— 汇总 ——
if only TN pool:      all_proven = tn_all_proven
elif only batch pool: all_proven = batch_all_proven   # 仅当有身份键
else:                 all_proven = None                # 重叠未证
                      overlap_status = "unknown"
all_estimated_max = max(tn_all_proven or 0, batch_all_proven or 0,
                        batch_all_estimated or 0)      # 只作估算，不得升级

qc_performed_proven(wo) = TN-based Completed 质检 JC qty（有身份）
qc_performed_estimated(wo) = batch-based 质检 JC qty（无身份，仅估算）
qc_passed(wo) = QualityInspection Accepted 且显式覆盖数量；否则 qty=unknown

stock_in_gross(wo) = sum(SED.qty for submitted Manufacture finished, is_return=0)
stock_in_return(wo) = sum(abs(SED.qty) for submitted Manufacture finished, is_return=1)
stock_in_net(wo) = stock_in_gross - stock_in_return   # 逐行只处理一次
```

### 2.3 测试站反例（已证 vs 估算）

| WO | WO 量 | first proven / est | all proven / est | qc_perf proven / est | qc_passed | stock gross/return/net | 说明 |
|---|---:|---|---|---|---|---|---|
| WO-25-00264-1 | 54 | 8 / 0 | 0 / 0 | 0 / 0 | unknown | 0/0/0 | 首工序部分完成，后续未开工 |
| WO-25-00270 | 35 | 54 / 0 | 4 / 0 | 4 / 0 | unknown | 4/0/4 | 首工序 54、后续仅 4；不可宣称 35 完成 |
| WO-25-00272 | 36 | 70 / 0 | 11 / 0 | 16 / 0 | unknown | 4.5/0/4.5 | 聚合 min=12，但菲号交集只有 11；QC 已检 16 > 全工序 11 |
| WO-25-00276 | 5 | 10 / 0 | 3 / 0 | 3 / 2 | unknown | 5/0/5 | 已证全工序 3；批卡 2 仅 estimated；入库 5 |
| WO-25-00277 | 36 | 36 / 36 | unknown / 36 | 0 / 36 | unknown | 0/0/0 | 批卡无共同身份 → all 仅 est 36，proven unknown；入库只有草稿 36 |
| WO-25-00281 | 20 | 25 / 0 | 10 / 0 | 10 / 0 | unknown | 0/0/0 | 质检只完成 10，不能算 20 完成 |
| WO-26-00024 | 10 | 10 / 0 | 0 / 0 | 0 / 0 | unknown | 6/0/6 | 入库已提交 6，但质检仍 WIP |

> `WO-25-00272` 的聚合最小工序量是 12，但按共同菲号身份取交集只有 **11**；直接取聚合 min 会多算 1 件。
> `WO-25-00277` 的批卡池 36 只是估算，不能升级为已证全工序完成。
> 表头 `proven / est` 的 `est` 是无共同身份的原始估算分量（批卡池/并行首工序），**可能与 proven 重叠**；
> 不得相加，也不得用 est 抬高 proven。`unknown` 表示没有足够身份/状态/覆盖证据，**不是 0**。
> 这些数字只用于证明口径；不是订单履约结论，也不写入业务系统。

## 3. 时间与证据边界

| 时间类 | 字段 | 用途 | 缺失处理 |
|---|---|---|---|
| 计划时间 | `WO.planned_start_date/planned_end_date`；`WOO.planned_start_time/planned_end_time`；`JC.expected_start_date/expected_end_date` | 计划/延期分析 | 缺失 null，不推断 |
| 实际开工时间 | `JC.actual_start_date`；`Job Card Time Log.from_time`；`WOO.actual_start_time` | 开工事件（**不是完成**） | 缺失 `started_at=null` |
| 实际完成时间 | `JC.actual_end_date`；`Job Card Time Log.to_time`；`WOO.actual_end_time`；`QI.report_date`；`SE.posting_date+posting_time` | 完成/质检/入库事件 | 缺失 `completed_at=null`、`time_status=missing` |
| 来源记录时间 | `creation`、`modified` | 记录创建/修改时间 | 不得当事件时间或采集时间 |
| 采集时间 | `manifest.observed_at`、`generated_at` | 何时取数 | 不得当事件时间 |

规则：

- `first_process_done.completed_at` = 完成首阶段工序的 Job Card/Time Log **结束时间**；
  `started_at` = 同一记录/首阶段的最早开始时间。**不能用开工时间当完成时间**。
  例：08:00 开工、17:00 完成 → `started_at=08:00`、`completed_at=17:00`。
- `all_process_done.completed_at` = 完成单元的最晚必经工序结束时间；`started_at` = 首选工序最早开始。
- `qc_performed.completed_at` = 质检 JC 结束；`qc_passed.reported_at` = QI `report_date`；两者不可混用。
- `stock_in_posted.posted_at` = SE `posting_date + posting_time`。
- **测试站反例**：`WO-25-00270` 裁剪 22 张 Completed JC 的 `actual_start/end` 全为 NULL、无 Time Log →
  `first_process_done` 数量 54 但 `completed_at=null`；`WO-25-00277` 裁剪菲号卡同样有 NULL 时间。
- **一键完成的合成时间**：`production_utils.py` 的一键完成会创建 1 秒间隔的 Time Log
  （`production_utils.py:143-186`），只能标 `time_basis=job_card_time_log`，不能据此推断真实生产节拍。

## 4. 现有入口影响清单

| 入口 | 当前解释 | 问题 | 兼容方式 | 版本变化 |
|---|---|---|---|---|
| `supply_facts.build_stage_balances` / `_wo_produced` | `produced` 取首工序 JC 或 `WO.produced_qty`；`produced_pending_dn` 文案“合格完工待出库” | 首工序 ≠ 全工序；`produced_qty` = 入库，不是完工；无质检证据却写“合格” | 保留 stage 枚举；每行增加 `production_evidence`（四类 qty/status/confidence/time/source）；`produced_pending_dn` 的 known 部分只取 `proven all_process_done`；`estimated` 单独披露，不抬高 known；`unknown` 进 unknown；`qc_passed` 单列 | `RULE_VERSION` bump；`IMPLEMENTATION_VERSION` bump 到 `key_test.supply_facts@2026-10-29.2`；schema 仍 `supply-facts/v1`（只增字段）；导出器继续拒绝混合版本 |
| `supply_facts` 的 `in_production` / `over_produced` | 在产来自已开工覆盖；超产来自 `produced_total` | 首工序完成被当作在产/完工边界；超产用缓存 `produced_qty` | `in_production` 的 known 只含“首工序 proven 但未全工序”；estimated 首工序单列；`over_produced` 以 `stock_in_net` 为硬证据；`cumulative_excess_qty` 保留全工序口径并注明；WO 取消但 SE 有效 → 冲突/unknown，不丢入库事实 | 同上 |
| `supply_facts.milestones.production_end` | 取任意 JC 最大 `actual_end` | 某道中间工序完成即当“完工” | 改为 `all_process_done` 的 `completed_at`；另增 `qc_performed`/`qc_passed`/`stock_in` 证据字段（不新增 milestone node，避免破坏枚举）；开工/完成分开 | 同上 |
| `so_chain.get_so_chain` | `line_produced` 取首工序；`stage=3 "生产完成待出库"` 由首工序量触发；`reported` 取末道 `max`；`instock` 取 `produced_qty` | 首工序完成即宣称生产完成；末道报工 ≠ 全工序；`produced_qty` 是入库缓存 | `line_produced` 改为 `all_process_done` proven；首工序只进“生产中”；`all_proven=null/unknown` 时 `completed` 不得为 true；`reported` 保留“末道报工”文案；`instock` 改用 Stock Entry 净额；新增 `all_process_done`/`qc_performed`/`qc_passed`/`stock_in_posted` 及 confidence；`completed` 对 KS 用入库、对 PK/ND 用全工序 proven | API 字段只增不减；文档注明语义变化 |
| `sales_order.js` 链条视图 | “报工/入库”两列 + 差异高亮 + “忘点完工?” | 报工=末道，易被理解为全工序；入库=缓存 | 增加“全工序(已证/估算)/已检/质检通过/入库净额”列或 tooltip；保留“忘点完工?”启发式但加“非事实”说明 | 前端字段只增 |
| `so_chain_overview` 报表 | “生产中/待发”粗粒度；`prod_chain` 只数工单/菲号 | 不展示证据缺口 | 增加 flags：全工序未证、质检结果未记录、入库草稿、WO 取消但 SE 有效；主表数量不变 | 只增列 |
| `supply_query.get_report_data` | 权限感知的 WO/TN 计数；无完工计算 | 新证据需要 Job Card/Stock Entry/QI 权限 | 复用 `_permitted_names`/`_permitted_rows`；新增权限标志；缺失 → unknown + partial | 只增字段 |
| `supply_timeline_query` | 库存快照 | 与生产证据无关 | 不改 | — |
| `item_shipment_status.wos_for_line` | 工单归属 | 只做关联，不做完工 | 不改关联键；不引入完工字段 | — |
| `en-produced-qty-vs-jobcard.md` | 已说明 `produced_qty`=入库、JC 不作守恒 | 尚未拆四类证据与置信度 | 实现阶段追加四类证据、置信度与去重规则链接 | 文档更新 |

**阶段余额的置信度映射（实现必须显式）**：

| 置信度 | 进入 `stage_balances` 的方式 |
|---|---|
| `proven` | `qty_status=known`；可作为 `produced_pending_dn` / `over_produced` 的 known 部分 |
| `estimated` | `qty_status=estimated` + `evidence_confidence=estimated`；单独披露；**不得**与 known 相加；`produced_pending_dn` 的 known 不含它 |
| `unknown` | `qty_status=unknown`，进 `unknown` 阶段并给原因；**不得当作 0** |

**兼容原则**：

- 只增字段、不改已有字段名；但 `produced_pending_dn` 的**数量语义**会变（首工序 → 全工序 proven），
  属于语义变更，必须 bump `RULE_VERSION` + `IMPLEMENTATION_VERSION`，并在 manifest notes 中说明。
- 旧批次与新批次不能混合；导出器已有版本校验，继续保留。
- 权限：新增 `job_card`、`stock_entry`、`quality_inspection` 到 `manifest.coverage.sources` 与 `restricted`；
  任一不可读 → `partial=true`，相关证据 `unknown`，不得解释为 0。

## 5. 验收矩阵

| # | 场景 | 测试站样本 | 期望（proven / estimated / unknown） | 断言 |
|---|---|---|---|---|
| 1 | 首工序完成、后续未完成 | `WO-25-00264-1`（qty 54；裁剪 8；缝制 0；质检 0；入库 0） | first proven 8；all proven 0；qc 0；stock 0 | 不得产出 `produced_pending_dn`；阶段为在产；时间缺失不得推断 |
| 2 | 部分全工序完成 | `WO-25-00270`（qty 35；裁剪 54；缝制 4；质检 4；入库 4） | first 54；all proven 4；qc_perf 4；stock 4 | 不得宣称 35 完成；只承认 4 个整菲号单元；超订单量单列 |
| 3 | 部分全工序完成（QC 先行） | `WO-25-00272`（qty 36；裁剪 70；缝制 21；质检 16；包装 12；入库 4.5） | first 70；all proven 11；all est 0；qc_perf 16；stock 4.5 | all=11 不得被 qc_perf=16 抬高；不得用聚合 min=12 |
| 4 | 质检未完成 | `WO-26-00024`（qty 10；非质检 10；质检 WIP 6；入库 6） | first 10；all proven 0；qc_perf 0；stock 6 | WIP 质检不得算已检/通过；入库已提交不等于工序完成 |
| 5 | 质检缺失/通过不可证 | QI 0；`JC.quality_inspection` 0/676；若连质检卡也无 → `qc_performed=0` | qc_performed 按卡；qc_passed 一律 unknown（`qc_result_not_recorded` / `coverage_qty_not_available`） | 不得把 Completed 质检卡默认成通过；不得用 all_process 代替 qc_passed；Accepted+sample_size 不推出通过量 |
| 6 | 入库草稿 | `WO-25-00277`（qty 36；批卡无身份；入库草稿 36、已提交 0） | all proven unknown；all est 36；qc_perf est 36；stock 0 | 草稿不得计入；批卡池 36 只是 estimated，不得升级为 proven |
| 7 | 入库已提交 | `WO-25-00270`（4）、`WO-25-00272`（4.5）、`WO-25-00276`（5） | 各自 stock gross/return/net 如上 | 只计 `docstatus=1` + `is_finished_item=1`；`fg_completed_qty` 仅交叉核对 |
| 8 | 入库取消 | `WO-25-00012-S009`（已提交 3、草稿 2、取消 1）；`WO-25-00272`（取消 12.5） | stock net=3 / 4.5 | 取消单排除；不得把取消量计入 |
| 9 | 整批卡 + 菲号卡重复 | `WO-25-00277` 裁剪 batch 36 + tn 36；`WO-25-00276` 包装 batch 1 + tn 6 | 36 不得变 72；6 不得变 7；两池原始分量保留 | 每工序不得相加；有身份 TN 才算 proven；无身份批卡只 estimated |
| 10 | 返工/纠正工序 | `WO-25-00276`：`缝制返工` 5 Completed；`通用返工`/`质检发现问题` JC 3 但 op=0 | 返工不计入分母；若返工在质检后 → qc_passed `review_required/unknown` | corrective 不参与全工序判定；op 与 JC 不一致要标记 |
| 11 | 多工单同一 SO 行 | SO 行 `mbj8u51rki` 5 张 WO；`vbn5gpoubt` 2 张 KS WO | 每 WO 独立；SO 行汇总只带 `batch_key=WO` | 不得把多 WO 合成一个实物批次；无菲号分配证据时 `allocation_unknown` |
| 12 | 取消记录 | 测试站 JC 取消 144、SE 取消 34、WO 取消 21 | 取消 JC/SE 排除；取消 WO 的进度排除，但有效 SE 保留 | 已取消但状态仍 Completed 的 JC 不得计入 |
| 13 | 单位不一致/缺失 | 测试站 0 例（WO vs SO UOM 不一致 0；WO 缺 UOM 0） | 全部证据 qty=unknown | 不做换算；矩阵用本地构造数据覆盖；生产查询必要性见 §7 |
| 14 | 权限受限 | `metacognition@dingtalk.com`：SO/DN 可读，WO/PP/Shipment 不可读；新来源 JC/SE/QI 同样需校验 | 相关证据 unknown；`manifest.partial=true`；Shipment links 为空 | 不得泄露无权数据；不得把不可见当 0；Guest 403 |
| 15 | 时间缺失 | `WO-25-00270` 裁剪 22 张 Completed JC 无 actual/time log；`WO-25-00277` 裁剪菲号卡同样 | started_at/completed_at 均 null、`time_status=missing` | 不用 WO 状态/creation/过账日推断 |
| 16 | 入库与工序不一致 | `WO-25-00276` all=3/stock=5；`WO-26-00024` all=0/stock=6；`WO-25-00272` all=11/stock=4.5 | 各自独立输出；差值显式 | 不得强制相等；不得用入库反推工序完成 |
| 17 | 同 WO 不同实物完成不同工序 | `WO-25-00272`（不同菲号的裁剪/缝制/质检/包装完成量不同） | all proven=11；聚合 min=12 只作诊断 | 不能因聚合 min 得到已证全工序完成；必须按菲号交集 |
| 18 | 批卡/菲号池身份关系未知 | `WO-25-00277`（批卡全工序 36；菲号仅裁剪 36；批卡无共同身份） | all proven unknown；tn proven 0；batch proven unknown；batch est 36；max est 36 | 经验 max 不得升级为已证数量；两池原始分量必须并列 |
| 19 | 首工序 08:00 开工、17:00 完成 | 构造/本地单测（测试站时间可能缺失） | `started_at=08:00`；`completed_at=17:00` | 完成事件取结束时间；不得用开工时间 |
| 20 | 入库 100、退货 ±10 | 构造/本地单测（测试站 Manufacture 退货 0） | gross=100；return=10；net=90（+10 与 −10 相同） | 退货行不得计入 gross；逐行只扣一次 |
| 21 | QI Accepted 但覆盖量不明 | 构造/本地单测（测试站 QI 0） | `qc_passed.status='Accepted'`；`qc_passed.qty=unknown` | 不得用 sample_size 或整单数量推导通过量；需显式覆盖证据 |
| 22 | 取消 WO + 有效已提交 SE | 测试站无该样本（查询 0 行）；构造/本地单测 | stock-in 保留（gross/return/net 照算）；`wo_cancelled_with_valid_stock_in` 冲突 | 不得把入库事实一起丢掉；不得把取消 WO 自动当 0；冲突单列 |

**不通过条件（实现阶段单测必须覆盖）**：

- 把各工序数量相加当全工序完成；
- 只取最小工序数量就宣称整批完成；
- 把整批卡 + 菲号卡相加；
- 无身份批卡的 `max` 被标成 proven；
- 把草稿/取消入库计入 `stock_in_posted`；
- 退货行同时进入毛额和扣减（+10/−10 得到 80 或 90 不一致）；
- 用 `WO.produced_qty` / `WO.status` 替代 Stock Entry / Job Card；
- 把 Completed 质检卡或 QI Accepted + sample_size 默认成 `qc_passed.qty`；
- 权限缺失返回 0；
- 时间缺失用 `creation`/过账日填充；
- 取消 WO 时把有效 SE 一起排除；
- 多工单无证据直接相加。

## 6. 测试站取证（只读）

**环境**：`ensh.vilavi.cn` / `erpnext.vilavi.cn`，测试站 `erpnext.vilavi.cn`，app `key_test@dccd6e8`；
所有查询只读，未写业务数据。

**计数**：

| 对象 | 数量 |
|---|---:|
| `Quality Inspection` | **0** |
| `Job Card` | 676（Completed 463、Open 136、Work In Progress 72、Material Transferred 4、Cancelled 1；另 docstatus=2 共 144） |
| `Work Order Operation` | 572（Completed 104、Pending 393、Work in Progress 75） |
| `Stock Entry`（Manufacture） | 113（draft 16、submitted 63、cancelled 34；`is_return=1` 0） |
| `Job Card` 质检 | 179 |
| `Job Card.quality_inspection` 非空 | **0** |
| `Work Order` | 98 submitted、50 draft、21 cancelled |
| `WO.stock_uom` vs `SO Item.uom` 不一致 | **0** |
| `WO.stock_uom` 缺失 | **0** |
| 取消 WO 且存在已提交 Manufacture SE | **0**（验收案例 22 用构造数据） |

**QI 真实元数据（测试站）**：

| 字段 | 值/选项 |
|---|---|
| `reference_type` | `Purchase Receipt / Purchase Invoice / Subcontracting Receipt / Delivery Note / Sales Invoice / Stock Entry / Job Card`；**没有 Work Order** |
| `status` | `Accepted / Rejected` |
| `sample_size` | Float；只是抽样数，不是通过数量 |
| `reference_name` | Dynamic Link（按 `reference_type`） |

**取数命令（只读；不要在生产执行）**：

```bash
ssh dev01@8.133.254.66
cd /home/frappe/frappe-bench
sudo -n -u frappe /usr/local/bin/bench --site erpnext.vilavi.cn mariadb --table <<'SQL'
-- 四类计数
select 'Quality Inspection' t, count(*) c from `tabQuality Inspection`
union all select 'Job Card', count(*) from `tabJob Card`
union all select 'WO Operation', count(*) from `tabWork Order Operation`
union all select 'SE Manufacture', count(*) from `tabStock Entry` where purpose='Manufacture';

-- 按菲号计算“每个必经工序都完成”的交集
select x.wo, sum(case when x.done_ops=x.req_ops then x.tn_qty else 0 end) all_done_tn
from (
 select w.name wo, tn.name tn, tn.qty tn_qty,
  count(distinct o.operation) req_ops,
  count(distinct case when j.status='Completed' and j.docstatus=1
        and j.total_completed_qty >= tn.qty then o.operation end) done_ops
 from `tabWork Order` w
 join `tabTracking Number` tn on tn.work_order=w.name
 join `tabWork Order Operation` o on o.parent=w.name
 join `tabOperation` op on op.name=o.operation and op.is_corrective_operation=0
 left join `tabJob Card` j on j.work_order=w.name and j.operation=o.operation
      and j.tracking_number=tn.name
 where w.name='WO-25-00272'
 group by w.name, tn.name, tn.qty
) x group by x.wo;

-- 入库毛额/退货/净额
select se.work_order, se.docstatus,
 sum(case when sed.is_finished_item=1 and ifnull(se.is_return,0)=0 then sed.qty else 0 end) gross,
 sum(case when sed.is_finished_item=1 and ifnull(se.is_return,0)=1 then abs(sed.qty) else 0 end) ret
from `tabStock Entry` se left join `tabStock Entry Detail` sed on sed.parent=se.name
where se.purpose='Manufacture' and se.work_order in ('WO-25-00277','WO-26-00024')
group by se.work_order, se.docstatus;
SQL
```

> 生产未执行任何查询；生产新增查询需求见 §7。

## 7. 生产新增查询需求（先列样本与必要性，不在本轮执行）

| 需求 | 样本 | 必要性 |
|---|---|---|
| `Quality Inspection` 使用情况 | 生产 `count(*)`、`reference_type` 分布、`status` 分布、是否有显式覆盖数量 | 测试站 0；若生产也 0，`qc_passed.qty` 只能 unknown 或由业务确认；若生产有 QI，需确认覆盖量字段 |
| `WO.stock_uom` vs `SO Item.uom` 不一致 | 生产 WO 与 SO Item 连接样本 | 测试站 0；确认是否存在单位不一致，决定是否需要换算/拒绝 |
| Job Card 实际时间缺失率 | 生产 Completed JC 的 `actual_start/end` 为空比例、Time Log 缺失比例 | 测试站已见缺失；确认是否普遍，决定 `time_status=missing` 的展示权重 |
| 批卡身份键使用率 | `batch_no`/`serial_and_batch_bundle`/`stock_tracking_number`/`custom_batch_no` 的填充率 | 决定有多少批卡可从 estimated 升级为 proven；无填充则只能估算 |
| 拆分工单/菲号重叠 | `custom_parent_work_order`/`custom_split_reference` 样本、同菲号跨 WO 样本 | 测试站有 `-S###` 与 5 WO 同行样本；确认合并/去重规则 |
| 取消 WO + 有效 SE | 生产 `WO.docstatus=2` 且 `SE.docstatus=1` 的样本 | 测试站 0；确认冲突处理与订单归属 |
| 受限角色对 JC/SE/QI 的可见性 | 已有受限用户（独立于第二步权限待验项） | 决定 `partial`/权限提示；未取得凭证前不执行 |

> 以上均为只读；需要生产授权与样本清单后再执行，不阻塞本设计的本地实现。

## 8. 待业务确认 / 未决

1. **质检 Job Card Completed 是否等于“通过”？** 当前无 QI、无结果字段；不得默认。
2. **QI Accepted 的覆盖数量从哪来？** 测试站无显式字段；若无，`qc_passed.qty` 永远 unknown。
3. **批卡是否需要强制录入共同身份键？** 若无，批卡池只能 estimated，不能作为已证全工序完成。
4. **拆分工单（S###）与父子工单的数量合并**：是否需要按菲号/批次合并，还是保持独立。
5. **返工在质检之后**：是否自动作废先前 QC；本设计建议 `review_required`，不自动改判。
6. **入库早于全工序/质检**（`WO-26-00024`）：业务上是否允许；阶段语义不得假设严格顺序。
7. **取消 WO 但 SE 有效**：入库事实归属哪条订单行/是否进 conflict bucket；本设计保留事实并单列冲突。
8. **单位换算**：测试站无样本；若生产存在不一致，需业务确认换算规则。

## 9. 下一步

1. 本设计 v2 交 Codex 复审；复审通过后再实现。
2. 实现范围（后续）：新增只读证据字段与查询、单测覆盖 §5 矩阵；不改业务流程、不扩权、不部署生产。
3. 第二步权限待验项继续独立跟踪；在其完成前，第二步不作为生产发布验收依据。
4. 第三步只做四类生产证据拆分；第四至第六步不启动。

## 10. 参考依据

- [G1b DN/WO/JC/SE 关联与数量守恒 v4](../2026-10-20/claude/experiments/g1_contract/g1b_dn_wo_jc_se.md) —
  `produced_qty` 不可作完工账、JC 只作进度证据、SE 按 (WO, UOM) 分桶。
- [EN「已生产」口径：工单入库 vs 工序卡报工](../../../../supply_chain_visibility/docs/reference/en-produced-qty-vs-jobcard.md) —
  `produced_qty` = 入库回写；批卡+菲号卡去重；末道确认护栏。
- [供应事实契约 v1](../../../../supply_chain_visibility/docs/reference/supply-facts-contract.md) —
  现有 `stage_balances` / `qty_status` / `partial` 口径。
- [第二步接口与分页契约](STEP2-INTERFACE-SCOPING.md) — filters/分页/版本一致性；权限待验项独立追踪。

## 11. 实现状态（第一批，2026-10-29）

- key_test 提交 `b0ccc6b`（初版）、`0b45144`（第一轮复审）、`3819db1`（第二轮复审）：
  新增 `key_test/production_evidence.py` 与 `key_test/tests/test_production_evidence.py`。
- 测试：新证据层 **57 passed + 6 subtests**；key_test 全量 **178 passed / 3 skipped**。
- 复审修正：有效记录筛选统一用于已证/估算池；批卡与菲号共用缺量/非有限数校验；
  冲突结果转 `unknown`（不再 proven 0）；退货原单必须有效已提交、非退货、非自身且物料/单位/WO 匹配；
  权限门槛覆盖数量、时间、来源、分量与冲突详情；重复菲号载荷同值去重、异值冲突且与输入顺序无关；
  QI 不求和、覆盖量保持 unknown；完成时间只跟随有效贡献记录；每类证据补
  `source_records` 与注入式 `observed_at`。
- 第一批只实现只读证据层：`supply_facts` / `so_chain` / 人工视图**未切换**，规则/实现版本未 bump。
- 差异报告（本地 gitignore，不提交）：
  `EN_API/out/supply_facts/_acceptance/step3_evidence_diff.md`。
- 未部署生产、未写业务数据、未扩权；第二步权限待验项独立保留。
- 下一批（待 Codex 审核）：接入阶段余额/旧查询/人工视图，bump 规则与实现版本，
  回归第二步接口、分页与导出保护；保持 `qc_passed.qty=unknown`。
