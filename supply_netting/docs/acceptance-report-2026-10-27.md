---
okf: v0.1
type: Report
title: 供给净额集成层 — 验收报告（2026-10-27）
description: 8 条必测场景、真实数据对账、案例、未知/阻断去向与剩余阻塞
tags: [acceptance, netting, reconciliation, supply-chain]
date: 2026-10-27
status: verified
---

# 供给净额集成层 — 验收报告

## 1. 任务与边界

把冻结的 `demand_netting.parquet`（849ba1b0）与 2026-10-20 通途库存快照/在途/开放 PO
按可售日期分桶净额，产出可人工审核的补货工作簿 + 同一底层批量供应事实。
不重做需求/供应管道，不预测，不写生产，不下单。

## 2. 复用与来源

| 组件 | 来源 | 状态 |
|---|---|---|
| `receipt_buckets.bucket_receipts` | `b08acc05` | `git show` 原样引入，11 个用例一并引入 |
| `supply_row.SupplyRow` / `apply_overlap_gates` | `6d374085` | 原样引入 |
| `bucket_gaps` / `assert_bucket_identities` / `allocate_so` | `aa93773b` `forward_net.py` | 原样引入到 `legacy_ledger.py` |
| `compute_row` / `harvest_total` | 同上 | **未引入**（首桶塞全部供应 / 运单号粗去重） |

来源说明见 [`../../supply_chain_visibility/docs/reference/upstream-port.md`](../../supply_chain_visibility/docs/reference/upstream-port.md)。

## 3. 8 条必测场景

| # | 要求 | 用例 | 结果 |
|---|---|---|---|
| 1 | 同 SKU 两仓不能互相抵消 | `test_1_same_sku_two_warehouses_do_not_offset` | 通过：W1 余量不外溢，W2 缺口 5 |
| 2 | 零预测仍保留未履约 SO | `test_2_zero_forecast_still_keeps_unfulfilled_so` | 通过：需求序列全 0，`allocate_so` 仍把 8 件放进保护期 |
| 3 | 增加需求时缺口相应变化 | `test_3_gap_moves_when_demand_increases` | 通过：3→8 需求，缺口 0→3 |
| 4 | 保护期后的供应不能覆盖之前缺口 | `test_4_later_supply_cannot_cover_earlier_gap` | 通过：11-01 到货不减少 10-28 的缺口 |
| 5 | FBA 已分配供应被排除 | `test_5_fba_allocated_supply_is_excluded` | 通过：`fba_allocated`，到货 0 |
| 6 | 同一批货跨阶段只计一次 | `test_6_same_batch_across_stages_counts_once` | 通过：PO+在途各 10，仅计 10 |
| 7 | 未知 ETA 保持条件态 | `test_7_unknown_eta_stays_conditional` | 通过：`date_unproven`，条件量 9，不计入到货 |
| 8 | 所有桶数量恒等式通过 | `test_8_every_bucket_identity_holds` | 通过：逐桶恒等式 + 供应数量账守恒 |

补充契约用例：无快照基准 → `unknown`（不写 0）；无未来供应证据 → `conditional`；
基准前需求只登记不计净额；无日期需求落最早桶；保守/预期情景只在证明上不同。

## 4. 测试数量

| 范围 | 数量 | 结果 |
|---|---|---|
| `supply_netting/tests`（净额 8 场景 + 8 契约边界 + 契约 §7 的 9 例 + 5 真实案例） | 35 | 全通过 |
| `supply_chain_visibility/tests`（引入的上游组件） | 23 | 全通过 |

## 4.1 供应决策契约 §7 的 8 个合成验收案例

| # | 契约案例 | 用例 | 结果 |
|---|---|---|---|
| 1 | 阶段例 100 = 10+30+20+25+5+10；累计完工/出库不再相加 | `test_1_stage_balances_are_mutually_exclusive_and_cumulative_is_not_supply` | 通过：合计 100，供给 80（未排产不算），终态 10 单独 |
| 2 | 一 DN 100、两运单；无分配证明不得各算 100 | `test_2_one_dn_two_shipments_needs_proven_allocation` | 通过：未证 → `allocation_unproven` 单条 100；有证 60/40 才分别配日 |
| 3 | PO 100 部分收 10，不得算 140 或重复补入 | `test_3_partial_receipt_does_not_create_140_or_double_count_stock` | 通过：60+30+10=100，已收标 `included_in_opening` |
| 4 | 同物料自发货/FBA；2 套不并入件 | `test_4_fba_reservation_excluded_and_units_do_not_mix` | 通过：FBA 8 排除，件 20 / 套 2 分账 |
| 5 | 到港 11/5、可售 11/8，11/6 缺口不被提前消除 | `test_5_sellable_after_arrival_does_not_clear_earlier_gap` | 通过：保护期缺口仍 1 |
| 6 | 分批 20/30/50，原 SO 不重复计入 | `test_6_split_tranches_only_fill_their_own_period` | 通过：拆分合计 100，11/20 的 50 不进保护期 |
| 7 | 单据取消但实物已生产 | `test_7_cancelled_order_keeps_physical_quantity_and_reason` | 通过：取消与实物各自留痕，未重新分配前不算供给 |
| 8 | Excel 与 Parquet 按稳定键一致；重跑不重复 | `test_8_parquet_and_excel_agree_and_rerun_is_stable` | 通过：tranche 键/数量/日期/排除原因一致，重跑结果相同 |

## 5. 真实数据对账（as_of 2026-10-21T00:00+08:00，快照 2026-10-20）

| 指标 | 数值 |
|---|---:|
| 默认序列需求行 / 数量 | 187,678 / 324,806 件 |
| 视界内有需求的键 | 426（其中保护期有需求 258） |
| 视界外键的需求行（历史，不净额） | 123,331 |
| 保护期需求 / 期初库存 / 条件供应量 | 602 / 25,199 / 9,954 件 |
| 保护期有缺口的键 / 缺口合计 | 10 / 16 件 |
| 视界末累计未满足 | 44 件 |
| 供应输入（`SupplyRow`）/ 无法归属的证据行 | 3,628 / 6,867 |
| 净额明细行 | 2,556 |
| 需求未归类数量（`quantity` − 默认 − 3PL） | 0 |

检查项（manifest `checks`）：四列重复 0、`netting_allowed` 全 true、逐桶恒等式通过、
供应数量账 `input_known = counted + excluded_known` 通过、每条需求/供应都有去向。

### 未知与阻断的去向

| 去向 | 行数 | 说明 |
|---|---:|---|
| `identity_unproven` | 6,711 | 开放 PO 多为物料 SKU + 未登记库存 SKU，无法映射成品物料 |
| `opening_basis` | 581 | 库存快照行，作为期初 |
| `uom_unproven` | 124 | 物料不在 `item_uom_cache` |
| `warehouse_unmapped` | 32 | 仓名未在别名表（如面料仓/辅材仓） |
| `eligibility_unproven`（保守） | 85 | 在途/SO 级供应未证资格 |
| `date_unproven`（预期） | 85 | 通途在途无逐行 ETA，条件态 |

需求侧：`demand_blocked.parquet` 只登记 sha256 与行数（57,088 行），**不参与**净额。

## 6. 真实案例

`KS0001-DM-100-GRASSGREEN × 美中-FZH-DANEEY × 个`：

| 桶 | 期初 | 到货 | 需求 | 缺口 | 条件供应 |
|---|---:|---:|---:|---:|---:|
| 保护期 10/21–10/24 | 0 | 0 | 1 | 1 | 291 |
| w1 10/24–10/31 | 0 | 0 | 2 | 2 | 291 |
| w2 10/31–11/07 | 0 | 0 | 2 | 2 | 291 |

该键在通途在途有 291 件，但没有逐行 ETA：保守情景判 `eligibility_unproven`，
预期情景判 `date_unproven`，两边都不计入到货，只出现在 `conditional_receipts`。
这正是「有量、无日期」的正确表达——不能因为 291 > 1 就宣布不缺货。

## 6.1 供应事实结构（契约 A/B/C）在真实数据上的落点

| 结构 | 真实数据 | 说明 |
|---|---|---|
| `stage_balances` | 172 条，全部 `shipped_in_transit` | 来自通途库存快照 `intransit`；校验错误 0，按订单对账全部 `balanced=true` |
| `milestones` | 0 条 | 结构就位；通途在途没有逐行原计划/预计/实际日期 |
| `availability_schedule` | 172 条 tranche，全部 `conditional` | 无 ETA，`date_confidence=unknown`；计入 172、排除 0 |
| 其他阶段 | 无本地源 | 未排产/在产/完工待发/到仓待上架需 EN 工单/DN 或 Jack 的 supply facts |

**这不是「供应功能已验收」**：只证明结构、校验与数量账可运行；阶段的真实覆盖仍 partial。

## 7. 剩余阻塞与待决

1. **未履约 SO 未接入**：`--backlog` 为空，未来桶需求为 0；需要 EN 开放 SO 的只读出口
   （不在本轮范围），否则 10/29 决策包不能用未来需求口径。
2. **供应覆盖未证**：只有通途库存快照/在途 + 开放 PO，manifest 恒 `partial=true`。
3. **子仓无快照**：`美中-FZH-DANEEY-皮壳仓库` 等 4 个键判 `unknown`。
4. **开放 PO 无法映射成品 SKU**：物料级 PO 与成品物料号不同，需主数据补登后再谈。
5. **日级→瞬间规则未经业务裁定**：当前按 `as_of` 时区当日 00:00，规则已入 manifest。
6. **两种情景在真实数据上无差异**：没有「有 ETA 但资格未证」的供应，属数据现实。
