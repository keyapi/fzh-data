---
okf: v0.1
type: Review
title: T25 分候选指标真正实现（WAPE/Bias/上限覆盖/样本量/零分母）
date: 2026-10-22
owner: claude-worker
status: 完成；巡检 8/8 PASS，且 #8 由实现而非注释支撑
artifacts:
  - experiments/business_phase/forecast_eval/forward_shadow.py
  - out/business_phase/forward_shadow_plan.md
  - out/business_phase/consistency_audit.json（复跑覆盖）
  - out/business_phase/consistency_audit.md（复跑覆盖）
---

# T25 分候选指标

> 修正 T24 的过宽口径：T24 的 `candidate_metrics` 是**各候选各自可用单元格**，
> 样本量不等；T24 的 selftest 只打印 selected，容易被读成“只有 selected 分项”。
> 本轮改为**同一共同子集**上的分候选完整指标，并让文档与实现逐字段对应。

## 1. 实现（`forward_shadow.py`）

| 字段 | 位置 | 定义 |
|---|---|---|
| 候选集合 | `:309` | `selected / naive / ma3 / ma6 / seasonal_naive / autoets / combo_ew`（固定七个） |
| 共同子集 | `:330` | `common = [sku for sku in included if 七个候选均在该 SKU 有预存预测]` |
| `n_cells` | `:341-366` | 共同子集单元格数；七候选**必须相等**（运行时断言 `_sizes`） |
| `wape_with_zero` | `:356` | `Σ|F−A| / ΣA`，零需求单元格的 `|F|` 保留在分子 |
| `wape_excluding_zero` | 同函数 | 仅非零实际量单元格（分子分母都排除）的对照口径 |
| `bias` | `:362` | `Σ(F−A)/ΣA`；读作方向，不读作准确率 |
| `upper_coverage` | `:364` | 实际 ≤ 点预测（单边上界）的单元格占比；只作观察、不构成保证 |
| `zero_count` / `zero_share` | `:366` | 按候选的零分母数量与占比（分母为该块共同可评格数） |
| `unavailable_candidates` | `:422` | 某候选缺哪些 SKU 的预存预测 + 原因（“该候选在该块不可评”），不猜 |

- 顶层 `wape`（selected/naive/ma3）保留，但改为共同子集口径；`bias`/`upper_coverage`
  为七候选字典；`n_scored = n_common`。
- 评分口径未变：母集=预存样本、无订单按零需求、缺标签 `labels_incomplete`、
  不重新选模、`--data-cutoff/--origin` 参数化、`--force` 防覆盖。
- schema 升为 `t10_forward_shadow_score/4`。

## 2. 测试输出（注入数据，无数据库）

**selftest**（2 SKU；A 预存 15 无订单、B 实际 100）：

```json
{"status":"scored","denominator":100.0,"wape_with_zero":0.15,
 "wape_excluding_zero":0.0,"bias_selected":0.15,
 "upper_coverage_selected":1.0,"zero_demand_retained":1,
 "zero_demand_share":0.5,"n_common":2,
 "candidates":["autoets","combo_ew","ma3","ma6","naive","seasonal_naive","selected"],
 "per_candidate":{
   "selected":{"n_cells":2,"wape_with_zero":0.15,"bias":0.15,"upper_coverage":1.0},
   "naive":{"n_cells":2,"wape_with_zero":0.15,"bias":0.15,"upper_coverage":1.0},
   "ma3":{"n_cells":2,"wape_with_zero":0.12,"bias":0.12,"upper_coverage":1.0},
   "ma6":{"n_cells":2,...},"seasonal_naive":{"n_cells":2,...},
   "autoets":{"n_cells":2,...},"combo_ew":{"n_cells":2,...}},
 "labels_incomplete_status":"labels_incomplete"}
```

- 断言：7 个候选的 `wape_with_zero/wape_excluding_zero/bias/upper_coverage` 均有限；
  `n_cells` 全部 = 2；`zero_count=1`、`zero_share=0.5`；`n_common=2`；
  共同子集大小唯一；`unavailable_candidates={}`；缺标签路径 7 候选 `n_cells=0`。

**entrytest**（真实入口）：

```json
{"entry_missing_last_month":"labels_incomplete","missing_months":["2026-12"],
 "excluded":2,"retry_after":"2027-01-04","entry_complete_labels":"scored",
 "wape_when_complete":0.15,"bias_when_complete":0.15,
 "upper_coverage_when_complete":1.0,"zero_demand_share":0.5,"n_common":2,
 "per_candidate_n":{"selected":2,"naive":2,"ma3":2,"ma6":2,
                    "seasonal_naive":2,"autoets":2,"combo_ew":2}}
```

- 缺最后目标月不再退出，返回 `labels_incomplete`；完整标签正常评分且分项齐全。

## 3. `forward_shadow_plan.md` 据实更新

- 记录项表改为字段名：`candidate_metrics.<候选>.wape_with_zero / wape_excluding_zero /
  bias / upper_coverage / n_cells / zero_count / zero_share`；新增“各候选样本量必须相等”。
- **删除全部“待扩/未实现”表述**（`grep -c 待扩` = 0）；不可评候选改写为
  “该候选在该块不可评（原因）”。
- §2 零分母口径第 3 条改为“脚本已输出 `.zero_count/.zero_share`”。
- §3 判定阈值（连续 3 月同向、5–95% 区间不含 0、记录完整）**未改**。

## 4. 巡检复跑（8/8 PASS）与证据

| # | 检查 | 结果 |
|---:|---|---|
| 1–6 | 主表/敏感性/WO-DN/explanations/diff/evidence | PASS |
| 7 | summary §6 ↔ 模型产物 | PASS |
| 8 | forward_shadow_plan ↔ forward_shadow.py | **PASS（实现已存在）** |

**#8 的对应证据（文档 → 脚本）**：

| 文档要求（plan §2） | 脚本实现 |
|---|---|
| 各候选 WAPE（`.wape_with_zero` / `.wape_excluding_zero`） | `cand_stats` `forward_shadow.py:341-357` |
| 各候选 Bias（`.bias`） | `:362` |
| 各候选上限覆盖率（`.upper_coverage`） | `:364`（metric_definition 也写明口径） |
| 零分母数量与占比（`.zero_count/.zero_share`） | `:366` |
| 各候选样本量相等（`.n_cells`） | `:330`（共同交集）+ 运行时断言 `_sizes` |
| 不可评候选写原因 | `unavailable_candidates` `:422` |
| 候选集合 7 个 | `:309` |

- 复跑覆盖 `consistency_audit.json/md`（允许项）；**未修改 `audit_consistency.py` 判据**。
- 8/8 PASS 不是靠注释换来的：上述字段在 selftest 输出中逐候选可见且数值有限。

## 5. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/forward_shadow.py --mode selftest
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/forward_shadow.py --mode entrytest
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/audit_consistency.py
uv run python scripts/check_secrets.py   # 无 finding、退出码 0
```

- 无数据库访问；测试用注入数据；临时目录自动删除；脚本确定性。

## 6. 约束自检

| 约束 | 结果 |
|---|---|
| 只改 `forward_shadow.py`、`forward_shadow_plan.md`、`consistency_audit.*` + 新增本记录 | ✅ |
| 未改 `audit_consistency.py` 判据 | ✅ |
| 未跑数据库；未访问生产、未下单、未删数据、未合并 PR | ✅ |
| 未改主表、T2–T24 其他产物与 V1 冻结产物 | ✅ |
| 未改 control 下 HANDOFF/state/DECISIONS/NIGHT_PLAN/CONTROL/RESEARCH_ADOPTION | ✅ |
| 未 push；只提交自己改动文件 | ✅ |
| 未提交原始明细与凭证；`check_secrets.py` 无 finding | ✅ |
| 不留临时文件（含 `__pycache__`） | ✅ |
