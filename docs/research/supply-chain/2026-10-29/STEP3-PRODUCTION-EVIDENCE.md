---
okf: v0.1
type: Spec
title: 第三步：四类生产证据的权威来源、数量推导与验收矩阵（只读设计）
date: 2026-10-29
owner: claude-worker
status: design-only; no implementation; no production deploy; step-2 permission acceptance still pending
scope: read-only; test-station evidence only; no business data writes; no permission expansion
tags: [supply-chain, production-evidence, job-card, stock-entry, quality-inspection, work-order, acceptance]
---

# 第三步：生产证据拆分（只读设计）

> 本文件只回答一个问题：**每个“完成”究竟由什么证据支持**。不修改业务算法、不部署生产、
> 不写业务数据、不扩大权限、不新增业务流程。第二步的权限验收仍独立追踪，不因本文件改写为通过。

## 0. 结论速览

1. **四类证据互相独立，不能替代。** 测试站实测存在：
   - 全工序完成 + 质检操作完成，但入库仍是草稿（`WO-25-00277`：入库 0）；
   - 入库已提交，但全工序/质检未完成（`WO-26-00024`：入库 6，质检 `Work In Progress`）；
   - 全工序完成 3、入库 5（`WO-25-00276`：入库领先于工序证据）。
2. **`qc_passed` 在当前数据上不可证。** 测试站 `Quality Inspection` **0 条**；`Job Card.quality_inspection` **0/676**；
   质检证据只有 `Job Card.operation='质检'` 且 `status='Completed'`，它只证明**已检**，不证明**通过**。
   因此本设计区分 `qc_performed`（已检）与 `qc_passed`（通过）；后者返回 `null/unknown`，原因 `qc_result_not_recorded`。
3. **`Work Order.produced_qty` 不是工序完工量。** 它是已提交 `Manufacture` 入库单的回写缓存；
   G1b 已实测 2 例 `produced_qty` 无法由可见单据解释（739/103、812/100），**入库以 Stock Entry 明细为准**。
4. **`Work Order Operation.completed_qty` 不是实际完工的权威。** 工单重建/孤儿报工会让它为 0，
   而 Job Card 仍有完工量；返工工序也会出现 op=0 但 JC>0。routing 只作**分母/计划结构**，实际事件以 Job Card 为准。
5. **数量必须按身份去重。** 禁止跨工序求和；禁止仅取最小工序量宣称整批完成；
   禁止把整批卡与逐菲号卡相加；入库草稿/取消不得当作证据。
6. **时间缺失是常态。** 测试站存在“已完成但无实际时间”的裁剪切（22 张 Completed、actual_start/end 为 NULL）；
   缺失一律 `null/missing`，不用 WO 状态、`creation` 或过账日期推断。

## 1. 四类证据来源表

### 1.1 总表

| 证据类 | 权威单据 | 关键字段 | 关联键 | 数量口径 | 单位 | 时间 | 有效状态 | 不能证明 |
|---|---|---|---|---|---|---|---|---|
| `first_process_done` | `Job Card`（事件）+ `Work Order Operation`（路由/分母） | JC: `work_order`, `operation`, `operation_id`, `status`, `docstatus`, `total_completed_qty`, `tracking_number`; WOO: `sequence_id`, `operation` | `WOO.parent = WO.name`；`JC.work_order + JC.operation`（+`operation_id` 防孤儿）；`JC.tracking_number = TN.name` | 最小 `sequence_id` 的必经工序完成量；同序并行工序取 `min`；批卡/菲号卡按 `max` 去重 | `WO.stock_uom`；须与 `SO Item.uom` 一致，否则 null | `JC.actual_start_date` / `Job Card Time Log.from_time`；缺失 null | JC `docstatus=1` 且 `status='Completed'`；排除 corrective | 不能证明全工序完成、质检通过或入库 |
| `all_process_done` | 全部必经 `Work Order Operation` + 对应已提交 Job Card | 同上；逐工序 `operation`/`sequence_id`/`total_completed_qty` | 同上 | 按 TN/批次身份：每个必经工序都有 Completed JC；TN 池 + 批卡池，总量 `max(两池)`；逐工序内部也按 `max(批卡, 菲号卡)` | 同上 | 完成单位的最晚必经工序 `actual_end`；缺失 null | 同上；排除 corrective / 取消 | 不能证明质检通过或入库 |
| `qc_passed` | `Quality Inspection`（若启用）；`Job Card` 质检仅证明“已检” | QI: `status`, `docstatus`, `reference_type`, `reference_name`, `item_code`, `sample_size`, `stock_tracking_number`; JC: `operation='质检'`, `status`, `docstatus`, `total_completed_qty`, `quality_inspection` | `QI.reference_name = WO.name` 或 `JC.quality_inspection = QI.name`；JC work_order/operation/TN | QI `Accepted` 覆盖量；无 QI → null/unknown；JC 质检量只作 `qc_performed` | `WO.stock_uom` | QI `report_date`；JC `actual_end_date`；缺失 null | QI `docstatus=1` 且 `status='Accepted'`；JC `docstatus=1` 且 `status='Completed'` 仅“已检” | 不能证明全部实物通过；当前测试站无法证明任何 `qc_passed` |
| `stock_in_posted` | `Stock Entry`（`purpose='Manufacture'`）+ `Stock Entry Detail` | SE: `work_order`, `purpose`, `stock_entry_type`, `docstatus`, `posting_date/time`, `is_return`; SED: `is_finished_item`, `item_code`, `qty`, `uom`, `stock_uom`, `t_warehouse`, `batch_no`, `stock_tracking_number` | `SE.work_order = WO.name`；`SED.item_code = WO.production_item`；`SED.uom = WO.stock_uom` | Σ 已提交 finished 行 `qty`；退货按 `abs(qty)` 扣减一次；排除 draft/cancelled | SED `uom/stock_uom`；按 `(WO, UOM)` 分桶；混单位 → null | `SE.posting_date + posting_time`；`creation/modified` 只算采集时间 | `docstatus=1`；`is_finished_item=1`；`is_return` 单独处理 | 不能证明工序完成或质检通过 |

### 1.2 字段级说明

#### first_process_done

- **分母**：`Work Order Operation` 中 `Operation.is_corrective_operation = 0` 的工序；返工分支
  （测试站：`缝制返工`、`裁剪返工`、`通用返工`、`质检发现问题`）**不计入**。
- **首工序**：`sequence_id` 最小的必经工序；同一 `sequence_id` 有多道并行工序时（测试站
  `WO-25-00276` 的 `缝制`/`包装` 都在 seq 2，`WO-25-00277` 的 `缝制`/`质检` 都在 seq 2），
  **全部都是首阶段工序**，首阶段完成量取它们的最小值。
- **事件**：优先用 `Job Card.status='Completed'` 且 `docstatus=1` 的 `total_completed_qty`；
  `Work Order Operation.completed_qty` 只作诊断，不作为实际完工。
- **边界**：`first_process_done` 只证明“首阶段完成”，**永远不能**用它宣称整批完成。

#### all_process_done

- **必经工序全集**：`Operation.is_corrective_operation = 0` 的所有 `Work Order Operation`；
  **并行工序也算必经**，不能只取最大 `sequence_id` 的末道。
- **身份**：以 `(WO, tracking_number)` 为一个实物单元；无菲号的整批报工以 `(WO, '__batch__')` 为一个池。
- **完成条件**：
  - 菲号池：该菲号在**每个**必经工序都有 `Completed` 且 `docstatus=1` 的 Job Card，且每道工序完成量 ≥ 该菲号数量；
    只有这样的菲号才整单元计入 `all_process_done`；部分工序完成的菲号**不计**入，留在在产/未知。
  - 整批池：每个必经工序都有整批卡（`tracking_number` 为空），整批完成量 = 各工序整批卡量的 `min`；
    只有**所有**必经工序都有整批卡时才成立，否则整批池为 0。
  - 总量：`max(菲号池, 整批池)`，并同时输出 `tn_pool_qty` / `batch_pool_qty` / `dedupe_rule='empirical_max'`。
- **为什么不能取最小工序量**：聚合最小量可能来自不同实物单元。必须先按菲号/整批池判定，
  再取池内最小；聚合最小值只作诊断字段，不作为公开 `all_process_done_qty`。
- **无工序工单（成品 KS）**：`all_process_done = null/not_applicable`，不得用入库反推工序完成。

#### qc_passed

- **测试站事实**：`Quality Inspection` 0 条；`Job Card.quality_inspection` 0/676；
  `Operation` 中 `质检` 是非返工工序，`质检发现问题` 是返工分支（`is_corrective_operation=1`）。
- **已检 ≠ 通过**：`Job Card.operation='质检'` 且 `status='Completed'` 只能证明质检动作执行，
  没有 pass/fail 结果字段；因此当前只能输出 `qc_performed`，`qc_passed` 必须 `null/unknown`，
  原因 `qc_result_not_recorded`。
- **若未来启用 Quality Inspection**：以 `docstatus=1` 且 `status='Accepted'` 为通过；
  `Rejected` 不计通过；`reference_type`/`reference_name` 必须能精确挂到 WO 或 Job Card；
  挂不上则 `unallocated`，不摊量。
- **业务假设**：若业务确认“质检 Job Card Completed 即视为通过”，属于**需要书面确认的口径变更**，
  必须 bump `RULE_VERSION` 并在契约中显式标注，不能由实现默认。

#### stock_in_posted

- **入库权威**：`Stock Entry.purpose='Manufacture'` 且 `docstatus=1`，成品行
  `Stock Entry Detail.is_finished_item=1`；数量取 `SED.qty`，单位取 `SED.uom`（须等于 `WO.stock_uom`）。
- **`produced_qty` 只是缓存**：`Work Order.produced_qty` 是已提交入库的回写；G1b 发现 2 例无法解释，
  只作 `produced_qty_cross_check`，不作为入库证据。
- **`fg_completed_qty` 只作交叉核对**：已提交单通常与明细合计一致（G1b C3 425/425），
  但草稿单可能不一致（测试站 `STE-25-00092`：`fg_completed_qty=3`、成品明细=2）；
  数量以明细合计为准。
- **状态**：草稿（docstatus=0）是候选/未生效，不是证据；取消（docstatus=2）排除；
  `is_return=1` 的 Manufacture 单按 `abs(qty)` 扣减一次（测试站 Manufacture 退货 0 条，规则由 G1b 单测覆盖）。
- **单位**：同一 WO 的已提交入库按 `(WO, UOM)` 分桶；跨单位不求和，`stock_in_posted_qty=null` 并给原因。

## 2. 数量推导规则

### 2.1 身份与去重

| 问题 | 规则 |
|---|---|
| 工序内重复报工 | 同一 `(WO, operation, tracking_number)` 出现多张 Completed Job Card → **冲突**，该身份该工序 `null/unknown`，不求和、不静默取 max |
| 整批卡 + 逐菲号卡并存 | 同一工序分别汇总 `batch_qty`（`tracking_number` 为空）与 `tn_qty`（非空），该工序完成量 = `max(batch_qty, tn_qty)`，并保留两个分量；**不得相加** |
| 多个工单 | 每张 WO 独立记账；按 SO 行汇总时只做带 `batch_key=WO` 的展示汇总，**不得**把多张 WO 的数量合成一个“同一批实物” |
| 拆分工单（`-S###`） | 视为独立 WO；若同属 `custom_parent_work_order`/`custom_split_reference`，只用于展示父子，不自动合并数量；合并需有菲号/批次证据，否则 `allocation_unknown` |
| 同一菲号跨 WO | 菲号全局唯一；若异常出现跨 WO，只按菲号计一次，并标记 `cross_wo_tracking_conflict` |
| 返工/纠正工序 | 不计入必经工序分母；若返工发生在质检之后，受影响单元的 `qc_passed` 置 `review_required/unknown`，除非之后有新的通过证据 |
| 取消 | `docstatus=2` 的 JC/SE/WO 一律排除；**已完成但已取消**的 JC（测试站 144 条）也不得计入 |
| 草稿 | JC docstatus=0、SE docstatus=0 不是完成/入库证据；只作候选提示 |
| 超产 | 保留原始完工/入库量；按订单分配时最多按订单量，超出部分单独 `excess`，不截断原始证据 |
| 单位 | 只在同一 UOM 内求和；`WO.stock_uom` 缺失或与 `SO Item.uom` 不一致 → `null/unknown`，不做换算 |
| 权限 | 任一来源不可读 → `null/unknown` + `reason=permission`，**不得当作 0** |

补充：

- `Job Card.total_completed_qty` 是完成量权威；Completed 但为 0 的卡记 `qty_missing`，
  **不得用 `for_quantity` 回填**（`for_quantity` 是计划量）。
- `Tracking Number.qty` 缺失时，该菲号不能判定为 `all_process_done`，也不得用 Job Card 数量回填菲号数量。

### 2.2 计算公式（伪代码）

```text
required_ops(wo) = [op for op in WorkOrderOperation[wo] if not op.is_corrective_operation]

op_qty(wo, op):
    batch = sum(jc.total_completed_qty for jc in CompletedSubmittedJC(wo, op, tn=""))
    per_tn = sum(jc.total_completed_qty for jc in CompletedSubmittedJC(wo, op, tn!=""))
    return max(batch, per_tn)          # 只用于展示；分量必须同时保留

first_qty(wo):
    first_seq = min(op.sequence_id for op in required_ops(wo))
    return min(op_qty(wo, op) for op in required_ops(wo) if op.sequence_id == first_seq)

tn_all_done(wo, tn):
    return all(has_CompletedSubmittedJC(wo, op, tn) and jc_qty(wo, op, tn) >= tn.qty
               for op in required_ops(wo))

all_done_tn(wo)    = sum(tn.qty for tn in TrackingNumbers(wo) if tn_all_done(wo, tn))
all_done_batch(wo) = min(batch_qty(wo, op) for op in required_ops(wo))
                     if every required op has a completed batch card else 0
all_done(wo)       = max(all_done_tn(wo), all_done_batch(wo))   # 经验去重，两池都披露

qc_performed(wo)   = 同上，但只统计 operation == "质检" 的 Completed 卡
qc_passed(wo)      = QualityInspection Accepted 覆盖量，若不存在则 null（qc_result_not_recorded）

stock_in(wo)       = sum(sed.qty for submitted Manufacture SE finished lines)
                     - sum(abs(sed.qty) for is_return lines)
```

### 2.3 测试站反例（证明四类不可替代）

| WO | WO 量 | first | all_process | qc_performed | qc_passed | stock_in | 说明 |
|---|---:|---:|---:|---:|---|---:|---|
| WO-25-00264-1 | 54 | 8 | 0 | 0 | unknown | 0 | 首工序部分完成，后续未开工 |
| WO-25-00270 | 35 | 54（原值，超订单） | 4 | 4 | unknown | 4 | 首工序 54、后续仅 4；不可宣称 35 完成 |
| WO-25-00272 | 36 | 70（原值，超订单） | 11 | 16 | unknown | 4.5 | QC 已检 16 > 全工序 11；入库 4.5 |
| WO-25-00276 | 5 | 10（原值，超订单） | 3 | 3 | unknown | 5 | 入库 5 领先于全工序 3；返工分支存在 |
| WO-25-00277 | 36 | 36 | 36 | 36 | unknown | 0 | 全工序/已检 36，但入库只有草稿 36 |
| WO-25-00281 | 20 | 25（原值，超订单） | 10 | 10 | unknown | 0 | 质检只完成 10，不能算 20 完成 |
| WO-26-00024 | 10 | 10 | 0 | 0 | unknown | 6 | 入库已提交 6，但质检仍 `Work In Progress` |

> 表中 `all_process` 是**按菲号逐单元**计算后取 TN 池/整批池的 `max`，不是聚合最小工序量。
> 反例：`WO-25-00272` 的聚合最小工序量是 12，但“每个必经工序都完成”的菲号交集只有 **11**；
> 若直接取聚合 min 会多算 1 件 —— 这正是“仅取最小工序数量就宣称整批完成”的错误。
> 这些数字只用于证明口径；不是订单履约结论，也不写入业务系统。

## 3. 时间与证据边界

| 时间类 | 字段 | 用途 | 缺失处理 |
|---|---|---|---|
| 计划时间 | `WO.planned_start_date/planned_end_date`；`WOO.planned_start_time/planned_end_time`；`JC.expected_start_date/expected_end_date` | 计划/延期分析 | 缺失 null，不推断 |
| 实际事件时间 | `JC.actual_start_date/actual_end_date`；`Job Card Time Log.from_time/to_time`；`WOO.actual_start_time/actual_end_time`；`SE.posting_date/posting_time`；`QI.report_date` | 实际开工/完工/质检/入库 | 缺失 `time_status=missing`，**不用状态/创建时间替代** |
| 采集时间 | `manifest.observed_at`、`generated_at`、`creation`、`modified` | 只表示何时取数/录入 | 不得当作事件时间 |

规则：

- `first_process_done` 时间取首阶段工序的 `actual_start_date`/Time Log 最早值；缺失 → null。
- `all_process_done` 时间取“完成单元的最晚必经工序 `actual_end_date`/Time Log 最晚值”；
  不能用 `WO.actual_end_date` 或 `WO.status='Completed'` 替代。
- `qc_performed` 时间取质检 JC 的实际完成；`qc_passed` 时间取 QI `report_date`；两者不可混用。
- `stock_in_posted` 时间取 SE 的 `posting_date + posting_time`；`creation` 只是录入时间。
- **测试站反例**：`WO-25-00270` 裁剪 22 张 `Completed` JC 的 `actual_start/end` 全为 NULL、无 Time Log →
  `first_process_done` 数量 54 但时间 `missing`；`WO-25-00277` 裁剪菲号卡同样有 NULL 时间。
- **一键完成生成的合成时间**：`production_utils.py` 的一键完成会创建 1 秒间隔的 Time Log
  （`production_utils.py:143-186`），这类实际时间可能只是系统生成；只能标记 `time_basis=job_card_time_log`，
  不能据此推断真实生产节拍。

## 4. 现有入口影响清单

| 入口 | 当前解释 | 问题 | 兼容方式 | 版本变化 |
|---|---|---|---|---|
| `supply_facts.build_stage_balances` / `_wo_produced` | `produced` 取首工序 JC 或 `WO.produced_qty`；`produced_pending_dn` 文案“合格完工待出库” | 首工序 ≠ 全工序；`produced_qty` = 入库，不是完工；无质检证据却写“合格” | 保留 stage 枚举；新增每行 `production_evidence`（四类 qty/status/time/source）；`produced_pending_dn` 改用 `all_process_done`，文案改“全工序完成待出库”，不再称“合格”；`qc_passed` 单列，缺失时 `unknown` | `RULE_VERSION` bump；`IMPLEMENTATION_VERSION` bump 到 `key_test.supply_facts@2026-10-29.2`；schema 仍 `supply-facts/v1`（只增字段）；导出器继续拒绝混合版本 |
| `supply_facts` 的 `in_production` / `over_produced` | 在产来自已开工覆盖；超产来自 `produced_total` | 首工序完成被当作在产/完工边界；超产用缓存 `produced_qty` | `in_production` 覆盖“首工序完成但未全工序”；`over_produced` 以 `stock_in_posted` 为硬证据，`cumulative_excess_qty` 保留全工序口径并注明 | 同上 |
| `supply_facts.milestones.production_end` | 取任意 JC 最大 `actual_end` | 某道中间工序完成即当“完工” | 改为 `all_process_done` 实际时间；另增 `qc_performed`/`qc_passed`/`stock_in` 证据字段（不新增 milestone node，避免破坏枚举） | 同上 |
| `so_chain.get_so_chain` | `line_produced` 取首工序；`stage=3 "生产完成待出库"` 由首工序量触发；`reported` 取末道 `max`；`instock` 取 `produced_qty` | 首工序完成即宣称生产完成；末道报工 ≠ 全工序；`produced_qty` 是入库缓存 | `line_produced` 改为 `all_process_done`；首工序只进“生产中”；`reported` 保留“末道报工”文案；`instock` 改用 Stock Entry 汇总；新增 `all_process_done`/`qc_performed`/`qc_passed`/`stock_in_posted`；`completed` 对 KS 用入库、对 PK/ND 用全工序 | API 字段只增不减；文档注明语义变化 |
| `sales_order.js` 链条视图 | “报工/入库”两列 + 差异高亮 + “忘点完工?” | 报工=末道，易被理解为全工序；入库=缓存 | 增加“全工序/已检/质检通过/入库”四列或 tooltip；保留“忘点完工?”启发式但加“非事实”说明 | 前端字段只增 |
| `so_chain_overview` 报表 | “生产中/待发”粗粒度；`prod_chain` 只数工单/菲号 | 不展示证据缺口 | 增加 flags：全工序未完成、质检结果未记录、入库草稿；主表数量不变 | 只增列 |
| `supply_query.get_report_data` | 权限感知的 WO/TN 计数；无完工计算 | 新证据需要 Job Card/Stock Entry/QI 权限 | 复用 `_permitted_names`/`_permitted_rows`；新增权限标志；缺失 → null + partial | 只增字段 |
| `supply_timeline_query` | 库存快照 | 与生产证据无关 | 不改 | — |
| `item_shipment_status.wos_for_line` | 工单归属 | 只做关联，不做完工 | 不改关联键；不引入完工字段 | — |
| `en-produced-qty-vs-jobcard.md` | 已说明 `produced_qty`=入库、JC 不作守恒 | 尚未拆四类证据 | 实现阶段追加四类证据与去重规则链接 | 文档更新 |

**兼容原则**：

- 只增字段、不改已有字段名；但 `produced_pending_dn` 的**数量语义**会变（首工序 → 全工序），
  属于语义变更，必须 bump `RULE_VERSION` + `IMPLEMENTATION_VERSION`，并在导出 manifest 的 notes 中显式说明。
- 旧批次与新批次不能混合；导出器已有 `schema_version/rule_version/implementation_version/as_of` 校验，继续保留。
- 权限：新增 `job_card`、`stock_entry`、`quality_inspection` 到 `manifest.coverage.sources` 与 `restricted`；
  任一不可读 → `partial=true`，相关证据 `null/unknown`，不得解释为 0。

## 5. 验收矩阵

| # | 场景 | 测试站样本 | 期望 first / all / qc_performed / qc_passed / stock_in | 断言 |
|---|---|---|---|---|
| 1 | 首工序完成、后续未完成 | `WO-25-00264-1`（qty 54；裁剪 8；缝制 0；质检 0；入库 0） | 8 / 0 / 0 / unknown / 0 | 不得产出 `produced_pending_dn`；阶段为在产；时间缺失不得推断 |
| 2 | 部分全工序完成 | `WO-25-00270`（qty 35；裁剪 54；缝制 4；质检 4；入库 4） | 54（原始，超订单）/ 4 / 4 / unknown / 4 | 不得宣称 35 完成；只承认 4 个整单元；超订单量单列 |
| 3 | 部分全工序完成（QC 先行） | `WO-25-00272`（qty 36；裁剪 70；缝制 21；质检 16；包装 12；入库 4.5） | 70 / 11 / 16 / unknown / 4.5 | all=11 不得被 qc_performed=16 抬高；入库 4.5 单列 |
| 4 | 质检未完成 | `WO-26-00024`（qty 10；非质检 10；质检 WIP 6；入库 6） | 10 / 0 / 0 / unknown / 6 | WIP 质检不得算已检/通过；入库已提交不等于工序完成 |
| 5 | 质检缺失/通过不可证 | 全测试站 `Quality Inspection` 0 条；`Job Card.quality_inspection` 0/676；若某工单连质检卡也没有 → `qc_performed=0` | qc_passed 一律 `null/unknown`，原因 `qc_result_not_recorded` | 不得把 Completed 质检卡默认成通过；不得用 `all_process_done` 代替 `qc_passed`；需业务书面确认或 QI 启用 |
| 6 | 入库草稿 | `WO-25-00277`（qty 36；全工序/已检 36；入库草稿 36、已提交 0） | 36 / 36 / 36 / unknown / 0 | 草稿不得计入；全工序完成但未入库要显式披露 |
| 7 | 入库已提交 | `WO-25-00270`（入库 4）、`WO-25-00272`（4.5）、`WO-25-00276`（5） | 各自 stock_in 如上 | 只计 `docstatus=1` + `is_finished_item=1`；`fg_completed_qty` 仅交叉核对 |
| 8 | 入库取消 | `WO-25-00012-S009`（已提交 3、草稿 2、取消 1）；`WO-25-00272`（取消 12.5） | stock_in=3 / 4.5 | 取消单排除；不得把取消量计入 |
| 9 | 整批卡 + 菲号卡重复 | `WO-25-00277` 裁剪 batch 36 + tn 36；`WO-25-00276` 包装 batch 1 + tn 6 | 36（非 72）/ 6（非 7） | 每工序 `max(batch, per_tn)`，两分量披露；不得相加 |
| 10 | 返工/纠正工序 | `WO-25-00276`：`缝制返工` 5 Completed；`通用返工`/`质检发现问题` JC 3 但 op=0 | 返工不计入分母；若返工在质检后 → qc_passed `review_required/unknown` | corrective 不参与全工序判定；op 与 JC 不一致要标记 |
| 11 | 多工单同一 SO 行 | SO 行 `mbj8u51rki` 5 张 WO；`vbn5gpoubt` 2 张 KS WO | 每 WO 独立；SO 行汇总只带 `batch_key=WO` | 不得把多 WO 合成一个实物批次；无菲号分配证据时 `allocation_unknown` |
| 12 | 取消记录 | 测试站 JC 取消 144、SE 取消 34、WO 取消 21 | 全部排除 | 已取消但状态仍 Completed 的 JC 不得计入 |
| 13 | 单位不一致/缺失 | 测试站 0 例（`WO.stock_uom` vs `SO Item.uom` 不一致 0；WO 缺 UOM 0） | 全部证据 qty=null、`qty_status=unknown` | 不做换算；矩阵用本地构造数据覆盖；生产查询必要性见 §7 |
| 14 | 权限受限 | `metacognition@dingtalk.com`：SO/DN 可读，WO/PP/Shipment 不可读；新来源 JC/SE/QI 同样需校验 | 相关证据 null/unknown；`manifest.partial=true`；Shipment links 为空 | 不得泄露无权数据；不得把不可见当 0；Guest 403 |
| 15 | 时间缺失 | `WO-25-00270` 裁剪 22 张 Completed JC 无 actual/time log；`WO-25-00277` 裁剪菲号卡同样 | 时间 null、`time_status=missing` | 不用 WO 状态/creation/过账日推断 |
| 16 | 入库与工序不一致 | `WO-25-00276` all=3/stock=5；`WO-26-00024` all=0/stock=6；`WO-25-00272` all=11/stock=4.5 | 各自独立输出，差值显式 | 不得强制相等；不得用入库反推工序完成 |

**不通过条件（实现阶段单测必须覆盖）**：

- 把各工序数量相加当全工序完成；
- 只取最小工序数量就宣称整批完成；
- 把整批卡 + 菲号卡相加；
- 把草稿/取消入库计入 `stock_in_posted`；
- 用 `WO.produced_qty` 或 `WO.status` 替代 Stock Entry / Job Card；
- 把 Completed 质检卡默认成 `qc_passed`；
- 权限缺失返回 0；
- 时间缺失用 `creation`/过账日填充；
- 多工单无证据直接相加。

## 6. 测试站取证（只读）

**环境**：`ensh.vilavi.cn` / `erpnext.vilavi.cn`，测试站 `erpnext.vilavi.cn`，app `key_test@dccd6e8`；
所有查询只读，未写业务数据。

**计数**：

| 对象 | 数量 |
|---|---:|
| `Quality Inspection` | **0** |
| `Job Card` | 676（Completed 463、Open 136、Work In Progress 72、Material Transferred 4、Cancelled 1；另有 docstatus=2 共 144） |
| `Work Order Operation` | 572（Completed 104、Pending 393、Work in Progress 75） |
| `Stock Entry`（Manufacture） | 113（draft 16、submitted 63、cancelled 34；`is_return=1` 0） |
| `Job Card` 质检 | 179 |
| `Job Card.quality_inspection` 非空 | **0** |
| `Work Order` | 98 submitted、50 draft、21 cancelled |
| `WO.stock_uom` vs `SO Item.uom` 不一致 | **0** |
| `WO.stock_uom` 缺失 | **0** |

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

-- 样本：工序 + Job Card 完成量（按身份拆分 batch/tn）
select w.name wo, w.qty, o.sequence_id seq, o.operation, op.is_corrective_operation corr,
       o.status, o.completed_qty,
       sum(case when j.docstatus=1 and j.status='Completed' then j.total_completed_qty else 0 end) done
from `tabWork Order` w
join `tabWork Order Operation` o on o.parent=w.name
left join `tabOperation` op on op.name=o.operation
left join `tabJob Card` j on j.work_order=w.name and j.operation=o.operation
where w.name='WO-25-00270'
group by w.name,w.qty,o.sequence_id,o.operation,op.is_corrective_operation,o.status,o.completed_qty
order by o.sequence_id;

-- 样本：入库三态
select se.work_order, se.docstatus, count(*) entries,
       sum(case when sed.is_finished_item=1 then sed.qty else 0 end) fin_qty
from `tabStock Entry` se left join `tabStock Entry Detail` sed on sed.parent=se.name
where se.purpose='Manufacture' and se.work_order in ('WO-25-00277','WO-26-00024')
group by se.work_order, se.docstatus;
SQL
```

> 生产未执行任何查询；生产新增查询需求见 §7。

## 7. 生产新增查询需求（先列样本与必要性，不在本轮执行）

| 需求 | 样本 | 必要性 |
|---|---|---|
| `Quality Inspection` 使用情况 | 生产 `count(*)`、`reference_type` 分布、`status` 分布 | 测试站 0；若生产也 0，则 `qc_passed` 无法从 QI 取得，只能保持 unknown 或由业务确认“质检卡=通过” |
| `WO.stock_uom` vs `SO Item.uom` 不一致 | 生产 WO 与 SO Item 连接样本 | 测试站 0；确认是否存在单位不一致，决定是否需要换算/拒绝 |
| Job Card 实际时间缺失率 | 生产 Completed JC 的 `actual_start/end` 为空比例、Time Log 缺失比例 | 测试站已见缺失；确认是否普遍，决定 `time_status=missing` 的展示权重 |
| 拆分工单/菲号重叠 | `custom_parent_work_order`/`custom_split_reference` 样本、同菲号跨 WO 样本 | 测试站有 `-S###` 与 5 WO 同行样本；确认合并/去重规则 |
| 受限角色对 JC/SE/QI 的可见性 | 已有受限用户（独立于第二步权限待验项） | 决定 `partial`/权限提示；未取得凭证前不执行 |

> 以上均为只读；需要生产授权与样本清单后再执行，不阻塞本设计的本地实现。

## 8. 待业务确认 / 未决

1. **质检 Job Card Completed 是否等于“通过”？** 当前无 QI、无结果字段；不得默认。
2. **`produced_pending_dn` 是否必须以 QC 通过为门槛？** 本设计建议以 `all_process_done` 为过程门槛、
   `qc_passed` 单列；若业务要求 QC 门槛，则 QC 未过的量进 `unknown`。
3. **拆分工单（S###）与父子工单的数量合并**：是否需要按菲号/批次合并，还是保持独立。
4. **返工在质检之后**：是否自动作废先前 QC；本设计建议 `review_required`，不自动改判。
5. **入库早于全工序/质检**（`WO-26-00024`）：业务上是否允许；阶段语义不得假设严格顺序。
6. **单位换算**：测试站无样本；若生产存在不一致，需业务确认换算规则。

## 9. 下一步

1. 本设计交 Codex 复审；复审通过后再实现。
2. 实现范围（后续）：新增只读证据字段与查询、单测覆盖 §5 矩阵；不改业务流程、不扩权、不部署生产。
3. 第二步权限待验项继续独立跟踪；在其完成前，第二步不作为生产发布验收依据。
4. 第三步只做四类生产证据拆分；第四至第六步不启动。

## 10. 参考依据

- [G1b DN/WO/JC/SE 关联与数量守恒 v4](../2026-10-20/claude/experiments/g1_contract/g1b_dn_wo_jc_se.md) —
  `produced_qty` 不可作完工账、JC 只作进度证据、SE 按 (WO, UOM) 分桶。
- [EN「已生产」口径：工单入库 vs 工序卡报工](../../../../supply_chain_visibility/docs/reference/en-produced-qty-vs-jobcard.md) —
  `produced_qty` = 入库回写；批卡+菲号卡去重 `max`；末道确认护栏。
- [供应事实契约 v1](../../../../supply_chain_visibility/docs/reference/supply-facts-contract.md) —
  现有 `stage_balances` / `qty_status` / `partial` 口径。
- [第二步接口与分页契约](STEP2-INTERFACE-SCOPING.md) — filters/分页/版本一致性；权限待验项独立追踪。
