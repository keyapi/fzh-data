---
okf: v0.1
type: Reference
title: 供应事实与数量—日期契约 v1 实现（批量入口 + 人工视图）
date: 2026-10-27
owner: claude-worker
status: 测试站已部署并验收；生产未部署
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
| `stage` | `not_planned` / `in_production` / `produced_pending_dn` / `shipped_in_transit` / `arrived_not_sellable` / `delivered_sellable` / `cancelled` / `returned` / `draft_dn` / `over_produced` / `unknown` |
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
- **到货判定**：只有全部关联运单状态齐全且均为到港/签收/POD 时才判 `arrived_not_sellable`；任一运单缺状态时保留在途并标注原因，不按已知子集判定整单到港。
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

### `manifest`

`schema_version=supply-facts/v1`、`rule_version`（数量规则版本）、`implementation_version`（实现/构建版本，服务端返回与本地导出产物都携带）、`run_id`、`as_of`（快照日）、`as_of_kind=current_snapshot`、`observed_at`（采集时刻）、`generated_at`、`scope`、`coverage`（来源/权限/`restricted`/`external_sources`）、`counts`、`partial`、`truncated`、`termination_reason`（`exhausted`/`page_limit`）、`pagination`、`partial_reasons`、`notes`、`files`（相对路径 + sha256）、`performance`。

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
- 当前 `implementation_version=key_test.supply_facts@2026-10-29.1`；接口/分页行为变更必须 bump，混合版本继续拒绝。
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

输出：`EN_API/out/supply_facts/runs/run-<ts>-<id>/` 下 5 个 JSON + `supply_facts.xlsx` + `manifest.json`；
`latest.json` 原子指针指向最后一次成功版本。写失败不切换指针，旧版本保持可读；`partial` 显式标记缺源。多批次合并前校验 `schema_version` / `rule_version` / `implementation_version` / `as_of`，任一不一致即拒绝该批次并终止导出，不写新版本，`latest.json` 仍指向上次成功版本。

## 3. 人工视图

SO Chain Overview 的链条弹窗新增「数量阶段 / 节点 / 分批可售」三段，调用与批量导出相同的
`key_test.supply_facts.get_supply_facts`（按 SO + 订单行）。弹窗按具体订单行请求时携带
`include_delivered=1`，已发完订单行仍展示历史事实，与机器导出范围一致。
工单数/菲号数仍只作导航，数量以阶段余额为准。

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
