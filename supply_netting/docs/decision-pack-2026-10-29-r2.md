---
okf: v0.1
type: Report
title: 10-29 决策包 F1–F7 终审返修（r2）
description: null 语义、严格 JSON、按 UOM、独立对账、输入锁定、反事实标注、桶起点
tags: [decision-pack, review-fix, null-semantics, json, uom]
date: 2026-10-29
status: verified
---

# 10-29 决策包终审返修（r2）

针对 `final-review-e1ea2bbb.md`（verdict: reject）逐项修复。
原包 `decision-pack-2026-10-29/` **未覆盖**；新包在
`decision-pack-2026-10-29-r2/`，manifest 记录原包 manifest 哈希
`aeacad90a2f3fe57fcc2ac2a24cd1e2598a12ea2eaa4f365972e29894234b84f`（supersedes）。

代码提交：`9f3285e3`（`git_dirty=false`）；测试 **192 通过**（新增 14 条 F1–F7 回归）。

## 1. 逐项修复

| 项 | 修复位置 | 改法 | 回归 |
|---|---|---|---|
| **F1** | `decision_pack._decide` | 不可算/待核键的 `gap_today / horizon_demand / protect_gap / qty_*` 全部 `null`，不再临时补 0；新增 `demand_evidence_status`、`gap_evidence_status`（`known/unknown/not_covered`）；`value_status` 增 `measured_zero` 区分真实零 | `test_unknown_and_not_covered_are_null_in_all_three_outputs`（Parquet/JSON/xlsx 三处）、`test_evidence_status_columns`、`test_measured_zero_is_not_confused_with_null` |
| **F2** | `_json_safe` / `_strict_json` | 序列化前 NaN/NaT→`null`；`json.dumps(allow_nan=False)`；写后 `json.loads(parse_constant=报错)` 严格回读 | `test_strict_json_rejects_nan_and_emits_null`、`test_exported_json_has_no_nan_tokens_and_parses_strictly` |
| **F3** | `_per_uom_buffers` / `_reconcile` | ABC 与全部数量汇总按 `canonical_uom` 分组；多 UOM 时顶层情景标量为 `null`，只给 `scenarios_by_uom`；组内第一名恒为 A | `test_mixed_uom_has_no_unscaled_scalar`（10 个 + 3 套 → 不出现 13）、`test_abc_tiers_are_computed_within_each_uom` |
| **F4** | `_reconcile` / `_map_forecast_keys` | 独立重建规范化输入键集合，与唯一输出键集合比对（missing/unexpected/duplicate），失败抛错；输出 255 行无法规范化预测源行明细（CSV + sheet + manifest 账） | `test_missing_input_key_fails_reconciliation`、`test_forecast_source_rows_are_fully_accounted` |
| **F5** | `_verify_r5_outputs` / `load_inputs` | 消费前核验 r5 三个产物哈希；预测窗口/manifest 与 r5 冻结值不符即拒绝；记录并校验历史需求与 `sku_map.tsv` 的路径+sha256；`forecast_generated_by` 与 `reviewed_commit` 分列；`verified=true` 只用于实际校验通过项 | `test_manifest_records_history_and_sku_map_hashes`、`test_history_hash_mismatch_is_refused`、`test_r5_output_hash_mismatch_is_refused` |
| **F6** | `_decide` | 改名 `qty_low_counterfactual`，并写 `qty_low_semantics`（“假设无 ETA 条件供应可用，未获证据前不可采用”）；`qty_high` 不扣条件供应 | `test_qty_high_ignores_conditional_and_low_is_marked` |
| **F7** | `build_pack` / `_decide` | `first_gap_bucket_start` + `first_gap_bucket_end` + `bucket_granularity`；`gap_today_note` 明示“净额视界末累计未满足量，不是某天缺口” | `test_bucket_fields_and_notes` |

未修项：无。F5 提到的“旧报告日期/预测版本”已在 manifest 分开记录
（`previous_report_date`、`forecast.run_id`、`forecast_generated_by`）。

## 2. 真实数据结果（r2）

| 指标 | 值 |
|---|---|
| 输入键 / 输出键 | 4,014 / 4,014（missing 0、unexpected 0、duplicate 0） |
| 去向 | 建议补货 91 / 无需补货 452 / 不可算 2 / 待核 3,469 |
| `value_status` | measured 543 / not_covered 3,469 / unknown 2 |
| 不可算 2 键 | `gap_today`、`horizon_demand`、`protect_gap`、`qty_*` 全为 null |
| 待核 3,469 键 | `gap_today`、`horizon_demand` 全为 null（不再写 0） |
| UOM | 个：建议 91 / 待核 3,452 / 不可算 2 / 无需 452；套：待核 17 |
| 保护期缺口（建议键） | 34.867936 / 71 键 |
| 视界末未满足 | 449.966544（个） |
| 情景 | current 495 / higher 777 / 差额 282（**全部为「个」**，单 UOM 标量） |
| `qty_low_counterfactual` 合计 | 340（个，反事实口径，不用于决策） |
| 预测源行 | 4,518 = 规范化 4,263 + 排除 255（全部 `sku_mapping_missing_or_ambiguous`） |
| 严格 JSON | 0 个 `NaN`/`Infinity` 标记，`parse_constant` 严格解析通过 |

## 3. 产物

目录：`D:/Work/fzh-order-store/en-demand-v1/supply-netting/decision-pack-2026-10-29-r2/`

| 文件 | SHA-256（前 12 位） |
|---|---|
| `decision_pack_2026-10-29.parquet` | `f489aa4fac3e` |
| `decision_pack_2026-10-29.json` | `375ff16c657c` |
| `decision_pack_2026-10-29.xlsx` | `7cbcde1b331e` |
| `forecast_source_excluded.csv` | `a32bab34c835` |
| `decision_pack_manifest.json` | 见文件 |

工作簿 sheet：决策清单 / 去向对账 / 源行对账 / 情景对照 / 数据与限制 / 预测源行排除 / Manifest。

## 4. 使用范围与限制（与 r1 相同，另补两项）

- 条件情景，不是采购指令；数据截止 2026-10-26，决策日 2026-10-29；净额视界止于 2026-11-30。
- 历史订单全部早于 as_of；2.779 天预测起点盲区；已证到货全桶为 0（无 ETA）。
- 未履约 SO 未接入；预测仅覆盖 582 个销售输入行（545 canonical 键）；255 行未规范化，明细随包。
- **待核/不可算的数量字段为 null，禁止按 0 筛选或汇总。**
- **`qty_low_counterfactual` 是反事实量，不得直接采用**；`gap_today` 是视界末累计未满足，不是当日缺口；
  缺口日期只是桶起点。
- 缓冲按 UOM 分组、未含提前期，不是覆盖率承诺；495/777/282 只针对 91 个「个」键。
