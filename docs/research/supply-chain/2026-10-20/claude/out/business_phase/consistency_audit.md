# T21 交付物一致性巡检

> 只读已有 CSV/JSON/MD，不跑数据库、不改任何数字；FAIL 只列差异与建议。

## 总览

- 检查项 **8**：PASS **6** / FAIL **2**
- FAIL 项：7, 8

| # | 检查 | 结果 | 差异数 |
|---:|---|---|---:|
| 1 | replenishment_v2.csv ↔ summary_v3.md | **PASS** | 0 |
| 2 | model_sensitivity.csv ↔ model_sensitivity.md | **PASS** | 0 |
| 3 | wo_dn_coverage.csv ↔ wo_dn_coverage.md | **PASS** | 0 |
| 4 | explanations.csv ↔ decision_v2.csv（异常计数） | **PASS** | 0 |
| 5 | diff_v1_v2.csv ↔ replenishment_all.csv / replenishment_v2.csv | **PASS** | 0 |
| 6 | evidence_request.md 责任方行数 ↔ decision_v2.csv（T3） | **PASS** | 0 |
| 7 | summary_v3 §6 ↔ nested_eval / short_history_eval | **FAIL** | 1 |
| 8 | forward_shadow_plan.md ↔ forward_shadow.py | **FAIL** | 4 |

## 1. replenishment_v2.csv ↔ summary_v3.md — **PASS**

- replenishment_v2.csv 无 6 个月销量列；占比按 summary_v3 自身原始值验算，并与 summary.md 的 48,001/543 一致（可复核但不能从 CSV 重算）。

## 2. model_sensitivity.csv ↔ model_sensitivity.md — **PASS**

- CSV 分类/子类计数与 md 表一致；销量覆盖按去重 SKU 近 6 月值重算。

## 3. wo_dn_coverage.csv ↔ wo_dn_coverage.md — **PASS**

- 三态合计与 CSV/JSON 一致；关联键按 JSON 的 total/linked/missing 比对。

## 4. explanations.csv ↔ decision_v2.csv（异常计数） — **PASS**

- 八类标签按「；」拆分计数；与 T4 评审表逐项比对，缺失标签计 0。

## 5. diff_v1_v2.csv ↔ replenishment_all.csv / replenishment_v2.csv — **PASS**

- 475 unchanged 由行数差额核对（1,328 − 602 − 154 − 6 − 91）；文档未单独写 475。

## 6. evidence_request.md 责任方行数 ↔ decision_v2.csv（T3） — **PASS**

- 文档另写“248 条 open 行 0 条有日期”；本地 CSV/JSON 无该口径，未纳入本轮核对。

## 7. summary_v3 §6 ↔ nested_eval / short_history_eval — **FAIL**

| 文件 | 字段 | 表/脚本值 | 文档值 |
|---|---|---|---|
| summary_v3.md | guard 阈值建议 | `len<7（T20，short_history_eval.py:69）` | `guard len(y) < 3` |
- T16 short_history_eval 的组合 MAE 9.928 未写入 §6；§6 的短历史数字来自 T9/T14（attribute_errors），两者口径不同（对齐方式/窗口集），不构成数字矛盾，但若要求并列需补一句说明。
- 模型数字逐项与 nested_eval.json / short_history_eval.json / error_attribution.json 比对。

## 8. forward_shadow_plan.md ↔ forward_shadow.py — **FAIL**

| 文件 | 字段 | 表/脚本值 | 文档值 |
|---|---|---|---|
| forward_shadow_plan.md / forward_shadow.py | 各候选 WAPE | `只算 selected / naive / ma3` | `每个候选 1 个值` |
| forward_shadow_plan.md / forward_shadow.py | 各候选 Bias | `未实现` | `每个候选 1 个值` |
| forward_shadow_plan.md / forward_shadow.py | 上限列覆盖率 | `未实现` | `每个候选 1 个值` |
| forward_shadow_plan.md / forward_shadow.py | 零分母数量与占比 | `仅 n_zero_demand_retained，无占比` | `数量与占比` |
- §3 连续 3 个月/区间不含 0 是人工判定流程，脚本只产出单次评分，文档未声称脚本自动判定，故不计失败。
- 已确认脚本保留 `--data-cutoff/--origin` 参数化、预存清单与 --force 防覆盖。

## superseded（不逐字比对）

| 文档 | 替代 | 原因 |
|---|---|---|
| `control/reviews/2026-10-22-t17-sensitivity.md` | `control/reviews/2026-10-22-t18-sensitivity-fix.md` | T17 正文“五口径一致 1,536 行全部全零、无全正量行”与数据矛盾，T18 已重分五类并更正。 |
| `control/reviews/2026-10-22-t16-short-history.md` | `control/reviews/2026-10-22-t20-guard.md` | T16 称 len 3–6 的 tiny_datasets 仍抛错；T20 已将 guard 扩到 len<7。 |
| `control/reviews/2026-10-22-t12-audit-fixes.md` | `control/reviews/2026-10-22-t14-recheck-fixes.md` | T12 的 M01 对齐 MAE 与 M02 早期块指标已被 T14 取代。 |

## 处置建议

- 数字 FAIL 只列差异，**不改数**；由 coordinator 决定是否回改生成脚本后重跑。
- 文档措辞/路径不一致（check 8）建议改文档或脚本，但本轮 ownership 不含这些文件。
- 所有输入 sha256 见 JSON，可复现。

## 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/audit_consistency.py
uv run python scripts/check_secrets.py
```

