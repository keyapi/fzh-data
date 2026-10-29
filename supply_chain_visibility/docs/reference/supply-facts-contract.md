---
okf: v0.1
type: Reference
title: 供应事实与数量—日期契约 v1 实现（批量入口 + 人工视图）
date: 2026-10-27
owner: claude-worker
status: 测试站已部署并完成功能验收；权限待验；生产未部署
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
- **物流阶段裁决（v2）**：终态粘性 + 实际优先 + 阶段顺序。到港/清关/转运/派送仍属
  `shipped_in_transit`；只有已签收/POD 才进入 `signed_pending_tongtool_receipt`；
  多运单全部签收时 DN 进入待入库但每条 Shipment 不复制 DN 数量；部分签收/状态未知保守留在途；
  冲突/异常/撤销 → `unknown` + `conflict_flag`。详见 STEP4。
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


### `shipment_progress`（最终物流状态，per Shipment）

`so`、`so_line_id`、`item_code`、`dn`、`shipment`、`logistic_number`、`tongtool_po`、
`warehouse`、`uom`、`status11`、`status4`、`status_semantics=unproven`、`eta/atd/ata/dlvr`、
`latest_progress_status`、`latest_progress_at`、`progress_source`、`is_final`、
`conflict_flag`、`conflict_reasons`、`progress_candidates`、`stage`、
`shipment_signed_at`、`tongtool_first/last/receipt_at`、`receipt_lag_days`、
`receipt_completion`、`received_qty/pending_qty`(+evidence_status)、
`receipt_basis=signed_assumed`、`identity_confidence`、`receipt_source_status`、
`inventory_inclusion_status`。

规则：证据等级 + 阶段顺序裁决；终态粘性；实际优先；`source_updated_at` 不提升阶段；
同时间冲突/异常/撤销/缺时间 → unknown+conflict 并保留候选。通途入库与库存未接入时
`receipt_completion=unknown`、`received/pending=null`、`receipt_source_status=not_integrated`、
`inventory_inclusion_status=unknown`。详见 STEP4/STEP5。

### `manifest`

`schema_version=supply-facts/v2`、`rule_version`（数量规则版本）、`implementation_version`（实现/构建版本，服务端返回与本地导出产物都携带）、`run_id`、`as_of`（快照日）、`as_of_kind=current_snapshot`、`observed_at`（采集时刻）、`generated_at`、`scope`、`coverage`（来源/权限/`restricted`/`source_status`（逐来源 `{available, reason}`）/`external_sources`）、`counts`、`partial`、`truncated`、`termination_reason`（`exhausted`/`page_limit`）、`pagination`、`partial_reasons`、`notes`、`files`（相对路径 + sha256）、`performance`。响应顶层同样返回 `source_status`。

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
- 当前 `implementation_version=key_test.supply_facts@2026-10-30.1`；`rule_version=2026-10-29.6`；接口/分页行为变更必须 bump，混合版本继续拒绝。
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
