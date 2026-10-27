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
| `stage` | `not_planned` / `in_production` / `produced_pending_dn` / `shipped_in_transit` / `arrived_not_sellable` / `delivered_sellable` / `cancelled` / `returned` / `draft_dn` / `unknown` |
| `qty`, `qty_status`, `qty_basis` | 数量、证据状态（known/estimated/unknown）、依据（job_card_first_op / wo_produced_qty / dn_submitted / …） |
| `batch_key`, `source_record` | DN / 工单 / 来源单据 |
| `exclusion_reason`, `included_in_stock` | 不可计入原因、是否已含库存（未证一律 unknown） |
| `scope`, `role` | `in_house`/`external_fba`、物料角色 |

规则：同一订单行的已执行片段互斥；历史累计完工/出库**不**再相加；草稿 DN 只列数量为空的提示行；差额进 `unknown` 并给原因；取消订单单独成段，实物另列。

### `milestones`（原计划 / 承诺 / 最新预计 / 实际）

| 字段 | 说明 |
|---|---|
| `node` | `order_placed` / `promised_delivery` / `production_start` / `production_end` / `dispatch` / `departure` / `arrival` / `delivery` |
| `baseline_planned_at`, `committed_due_at`, `latest_expected_at`, `actual_at` | 四类时间，缺证留 null |
| `qty`, `qty_status` | 节点数量与证据 |
| `observed_at`, `date_precision`, `timezone_status` | 观测时间、日精度、时区是否已证 |
| `source_record`, `note`, `rule_version` | 来源字段、口径说明、规则版本 |

规则：未发生不填实际；ETA 只进 `latest_expected_at`；POD/签收不等于可售；原计划保留供延期分析。

### `availability_schedule`（分批可售片段）

| 字段 | 说明 |
|---|---|
| `tranche_id` | 稳定片段 ID（`DN::单号` 或 `SO行::阶段`） |
| `qty`, `qty_status`, `uom` | 片段数量与证据 |
| `available_date`, `latest_expected_at`, `date_kind`, `date_confidence` | 可售日（当前无入库/上架证据，恒为 null）与 ETA |
| `scenario` | `conditional` / `unknown` / `allocation_unknown` |
| `eligible`, `exclusion_reason` | 是否可进入补货计算（v1 全部 false），原因 |
| `batch_key`, `source_record` | 片段来源 |

规则：多运单 DN 不给数量（`allocation_unknown`），不复制 DN 全量；到港/签收不生成可售日；未证一律 null。

### `links`（来源与分配证据）

`so / so_line_id / source_doctype / source_name / source_line_id / relation / target_doctype / target_name / qty / uom / proof / allocation`。
覆盖 SO→Item、SO 行→PP、SO 行→WO、WO→菲号、SO 行→DN、DN→Shipment（多运单时 `allocation=unknown` 且 qty=null）。

### `manifest`

`schema_version=supply-facts/v1`、`rule_version`、`run_id`、`as_of`、`generated_at`、`scope`、`coverage`（来源/权限）、`counts`（输入/输出/各数据集）、`partial`、`notes`、`files`（sha256）、`performance`。

## 2. 批量入口

```bash
# 单 SO
uv run python EN_API/supply_facts_export.py --so SO-26-00026 --test

# 客户码/物料码（自动判型）
uv run python EN_API/supply_facts_export.py --codes "TT0031038K0062927,CENCord995-DKGrey-97" --test

# 全范围（分页）
uv run python EN_API/supply_facts_export.py --all --test --page-size 500
```

输出：`EN_API/out/supply_facts/runs/run-<ts>-<id>/` 下 5 个 JSON + `supply_facts.xlsx` + `manifest.json`；
`latest.json` 原子指针指向最后一次成功版本。写失败不切换指针，旧版本保持可读；`partial` 显式标记缺源。

## 3. 人工视图

SO Chain Overview 的链条弹窗新增「数量阶段 / 节点 / 分批可售」三段，调用与批量导出相同的
`key_test.supply_facts.get_supply_facts`（按 SO + 订单行）。工单数/菲号数仍只作导航，数量以阶段余额为准。

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

- 契约单测：10 项（8 类案例 + 草稿不重复计量 + `wo_produced_qty` 标 estimated），本地全绿。
- 单 SO `SO-26-00026`：3 行 / 8 阶段余额 / 16 里程碑 / 6 可售片段 / 17 关联；查询 0.63s。
  三行阶段余额守恒 10 / 5 / 8（草稿不计数量；KS 无工序卡时用 produced_qty 标 estimated）。
- 全范围：278 行 / 294 阶段余额 / 628 里程碑 / 287 片段 / 390 关联；查询 0.28s，总计 0.72s。
- 9 SKU：生产只读解析出 99 张 SO；测试站无该样本数据，**待生产授权后验收**（本任务未授权生产部署）。
- 普通角色权限：当前只验证 doctype 级权限（缺源时标 partial）；行级角色/字段权限待补。

## 6. 待业务确认

1. 到仓验收/上架/可售的权威来源（当前 EN 无，导致可售日恒为未知）。
2. 承诺日期字段（当前无独立字段，暂用 SO 交期）。
3. FBA/自发货预留量与自由供给的权威口径。
4. 多运单 DN 的物料行级分配规则（无证据前不摊量）。
5. 刷新频率与陈旧阈值（30 分钟为候选，未部署）。
6. 9 SKU 验收所需的生产只读部署授权。
