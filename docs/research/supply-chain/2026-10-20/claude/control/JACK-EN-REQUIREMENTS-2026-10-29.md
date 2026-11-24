---
okf: v0.1
type: Reference
title: 对 Jack 的 EN 供应链接口要求（按 2026-10-29 业务口径修正）
date: 2026-10-29
owner: claude-foreman
status: proposed-for-jack
---

# 对 Jack 的 EN 供应链接口要求

> 目的：让补货引擎能把 EN 的在产、出库、头程、到仓，和通途库存/PO **不重复、不混淆**地接起来。
> 不是要求 Jack 改业务流程，而是把已有事实以稳定字段暴露出来。

## 0. 先说业务事实（避免提错要求）

1. **目前没有启用扫外箱号收货。** 头程签收就默认“都到了”，不要求逐箱/逐件实收证明。
2. **签收后到通途 PO 入库还有时间差。** 如果不把这个时间差标出来，EN 在途、通途在途、通途库存会重复计算。
3. **Shipment 已有两条进度线**：物流商爬虫、人工维护。两条线可能不一致；**以进度更靠后的一条为准**，Jack 只需在 Shipment 里给出最终结论。
4. 我们不需要 Jack 提供爬虫原始报文，只要**最终状态 + 时间 + 来源 + 是否最终**。

## 1. 三件必须先做的事（按优先级）

### 1.1 头程最终进度（替代“实收行”）

**现有问题**：Shipment 有两条线、状态/备注/ETA 可能不一致；补货引擎无法判断哪条算数。

**要求**：在 Shipment（或 supply-facts 的 shipment 段）暴露：

| 字段 | 含义 |
|---|---|
| `latest_progress_status` | 最终状态（未发/已发/开船/到港/清关/派送/签收/异常） |
| `latest_progress_at` | 该状态对应的时间 |
| `progress_source` | `carrier_tracking` / `manual` / `other` |
| `progress_source_updated_at` | 该来源最后更新时间 |
| `is_final` | 是否已签收/已完结 |
| `eta_available_at` | 预计可售/到仓时间（如可得；没有就 null） |
| `conflict_flag` | 两线冲突时置 true，并保留两条的原值 |

**裁决规则**：业务已明确“哪条进度靠后，哪条为准”。系统按 `latest_progress_at` 取更晚的一条；若时间相同但状态不同，标 `conflict_flag`，不静默选。

### 1.2 签收 → 通途 PO 入库的时间差

**现有问题**：EN 头程签收后，通途 PO 入库可能晚几天；EN 在途、通途在途、通途库存三处容易重复。

**要求**：提供关联与时间戳：

| 字段 | 含义 |
|---|---|
| `shipment_signed_at` | 头程签收时间（签收即视为全部到达，`receipt_basis=signed_assumed`） |
| `tongtool_po_no` / `tongtool_po_line` | 对应通途 PO/行（若能关联） |
| `tongtool_receipt_at` | 通途入库时间（没有就 null） |
| `receipt_lag_days` | 签收→通途入库天数 |
| `stock_state` | `in_transit` / `signed_pending_tongtool_receipt` / `tongtool_received` |

**用途**：补货引擎只在一个状态里计一次：
- 未签收：算 EN 在途；
- 已签收但通途未入库：算“已到未入库”，**不再算在途**，也不并进通途库存；
- 通途已入库：只算通途库存。
**不要求**逐箱收货或数量证明；签收默认全到。

### 1.3 `supply-facts` 稳定只读契约

**现有问题**：filters/分页/字段版本/partial 标记不清；调用可能默默扩大范围。

**要求**：
- 明确 `filters` 白名单（sku、warehouse、stage、as_of、include_delivered 等）；未知参数报错，不静默忽略；
- 分页返回 `page/limit/exhausted/partial`，不能静默截断；
- 字段带 `schema_version`、`as_of`、`source_record`、`observed_at`、`confidence`、`evidence_level`；
- 每个数量带 `uom` 和 `qty_basis`；
- `partial=true` 时列出缺哪些来源（PO/入库/目的仓）。

## 2. “首工序/全工序/质检/入库”到底要什么（用人话）

我们不是要 Jack 暴露每道工序的明细，而是要知道**这个 SKU 现在处于哪一步、这一步的数量和时间是否可信**。建议只需四个里程碑，每个给“数量 + 日期 + 来源 + 是否已证”：

| 里程碑 | 大白话 | 用途 |
|---|---|---|
| `first_process_done` | 第一道工序做完多少 | 只代表“开始有产出”，**不能当可发** |
| `all_process_done` | 所有工序做完多少 | 接近可入库，但仍未质检/入库 |
| `qc_passed` | 质检通过多少 | 可进入可售候选 |
| `stock_in_posted` | 已提交入库多少 | 真正进入库存 |

如果 EN 只能给其中一部分，就给**当前最可信的里程碑**并标 `missing`；不要把首工序完成写成“生产完成”，也不要用 WO.status 代替。补货引擎只把 `qc_passed + stock_in_posted` 当可售候选；`first_process_done` 只作进度。

## 3. 明确不要求的事

- 不要求扫外箱号/逐件实收；
- 不要求爬虫原始报文；
- 不要求改 EN 业务流程；
- 不要求 Jack 做预测/补货决策。

## 4. 验收

1. 任取 5 张 Shipment，能返回 `latest_progress_status/at/source/is_final`，两线冲突有 `conflict_flag`；
2. 任取 5 张已签收 Shipment，能看出 `shipment_signed_at` 与 `tongtool_receipt_at` 的时间差/状态；
3. `supply-facts` 用未知 filter 会报错，分页有 `exhausted/partial`；
4. 任取 5 个在产 SKU，能区分 `first_process_done/all_process_done/qc_passed/stock_in_posted` 中至少两个，并标 missing；
5. 以上全部只读，不改 EN 业务数据。
