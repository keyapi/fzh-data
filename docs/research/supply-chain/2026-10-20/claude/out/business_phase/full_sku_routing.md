---
okf: v0.1
type: Report
title: 全 SKU 分型 + 全局 LightGBM 对照 + 接回 C
date: 2026-10-23
owner: claude-worker
status: 只读离线；复用 A/B/C；未 commit
artifacts:
  - experiments/business_phase/forecast_eval/full_sku_routing.py
  - out/business_phase/full_sku_classification.csv
  - out/business_phase/full_sku_eval.json
  - out/business_phase/final_bundle_routing.csv
---

# 全 SKU 分型 + 全局 LightGBM 对照 + 接回 C

> 只读离线：DB `read_only`，复用 A（`routing_eval.py` 助手函数）、B、C 的产物，不重跑；未安装任何新依赖（mlforecast / lightgbm 已在环境里）。

## 1. 分型表（母集 1,328 SKU）

规则（训练窗内可算，绝不用外层结果定型）：
`<12 月` → 证据不足；`12–23 月` → 新品短史；`零占比≥0.4 或 ADI≥2.0` → 间歇；`季节强度≥0.3` → 季节；其余 → 平滑。

> 分型表是**截至 2026-09 的现状描述**（用全历史算特征）；下面的评估是滚动切点、与分型表独立，不用分型结果选模型。

| 类型 | SKU 数 |
|---|---:|
| 季节 | 311 |
| 证据不足 | 276 |
| 平滑 | 264 |
| 新品短史 | 262 |
| 间歇 | 215 |

## 2. 同单元同指标对照（共同子集）

- 切点：2025-03, 2025-06, 2025-09, 2025-12, 2026-03；最少训练 18 个月；90 天窗口；共同单元 **2820** 个、**790** 个 SKU。

| 方法 | n | WAPE | Bias | MAE |
|---|---:|---:|---:|---:|
| naive | 2820 | 0.606 | 0.009 | 16.10 |
| ma3 | 2820 | 0.631 | 0.086 | 16.77 |
| tsb | 2820 | 0.590 | 0.119 | 15.68 |
| seasonal_naive | 2820 | 0.598 | 0.174 | 15.89 |
| combo | 2820 | 0.524 | 0.097 | 13.91 |
| global_tree | 2820 | 0.494 | -0.052 | 13.12 |

> 全局树可用：**True**。本表只作同口径对照，不宣称单一最优模型。

## 3. 覆盖对账（入 N 出 M）

| 项 | 数 |
|---|---:|
| 入：母集 SKU | 1328 |
| 有月度序列 | 1328 |
| 无月度序列 → 证据不足 | 0 |
| 已判型（非证据不足） | 1052 |
| 证据不足 | 276 |
| 评估评分 SKU | 790 |
| 候选单元 SKU×切点 | 6640 |
| 已评分单元 | 2820 |
| 未评分跳过（SKU×切点） | 3820（{'history_lt_min_train': 3820}） |
| 出：C 行数（带边注） | 2309 |

## 4. 接回 C 的映射统计（只加边注，不改数字）

| routing_support | 行数 |
|---|---:|
| 支持充足（本批已评分） | 1366 |
| 支持不足（未进入共同单元） | 943 |

> `final_bundle_routing.csv` = C 的 `final_bundle.csv` 全列原样 + `routing_type` / `routing_support` 两列；C 的任何数字都未被修改。

## 5. 可外推边界

- 分型只描述**训练窗内**的可观测形态，不预测未来是否有促销/改款。
- 证据不足（<12 月）的 SKU 不进入评估，映射到 C 时标「支持不足」，不外推。
- 全局树与基线在同一批单元上比较，结论限于本批 SKU 与切点。

## 6. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/full_sku_routing.py
```

耗时 **16.5 s**。
