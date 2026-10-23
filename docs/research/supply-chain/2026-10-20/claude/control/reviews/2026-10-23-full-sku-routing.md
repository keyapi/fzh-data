---
okf: v0.1
type: Review
title: 全 SKU 分型 + 全局 LightGBM 对照 + 接回 C（只读）
date: 2026-10-23
owner: claude-worker
status: 完成；只读离线；未 commit（工头唯一提交者）
artifacts:
  - experiments/business_phase/forecast_eval/full_sku_routing.py
  - out/business_phase/full_sku_classification.csv
  - out/business_phase/full_sku_eval.json
  - out/business_phase/final_bundle_routing.csv
  - out/business_phase/full_sku_routing.md
---

# 全 SKU 分型 + 全局 LightGBM 对照 + 接回 C

> **只读离线**：DB `read_only=True`；复用 A（`2b44cdbd`，直接 import 其助手函数，不重跑）、
> B（`bf8b19c0`）、C（`b02fd083`）的产物；**未安装任何新依赖**（mlforecast / lightgbm 已在环境）；
> 按本任务要求**未 commit、未 push**。

## 1. 分型表（母集 1,328 SKU）

规则（训练窗内可算，绝不用外层评估结果定型）：
`<12 月` → 证据不足；`12–23 月` → 新品短史；`零占比≥0.4 或 ADI≥2.0` → 间歇；`季节强度≥0.3` → 季节；其余 → 平滑。

| 类型 | SKU |
|---|---:|
| 季节 | 311 |
| 证据不足 | 276 |
| 平滑 | 264 |
| 新品短史 | 262 |
| 间歇 | 215 |

- 逐 SKU 证据（历史长度、零占比、ADI、CV²、季节强度、累计需求、destination）在
  `out/business_phase/full_sku_classification.csv`。
- 分型是**截至 2026-09 的现状描述**（全历史算特征）；下面的评估是滚动切点、与分型表独立，
  没有用分型去挑模型。

## 2. 同单元同指标对照

切点 2025-03 / 2025-06 / 2025-09 / 2025-12 / 2026-03（与 A 相同），90 天窗口，最少训练 18 个月。
共同子集 **2,820 单元 / 790 SKU**。

| 方法 | n | WAPE | Bias | MAE |
|---|---:|---:|---:|---:|
| naive | 2,820 | 0.606 | 0.009 | 16.10 |
| ma3 | 2,820 | 0.631 | 0.086 | 16.77 |
| tsb | 2,820 | 0.590 | 0.119 | 15.68 |
| seasonal_naive | 2,820 | 0.598 | 0.174 | 15.89 |
| combo（四法等权） | 2,820 | 0.524 | 0.097 | 13.91 |
| **global_tree（MLForecast+LightGBM）** | 2,820 | **0.494** | −0.052 | **13.12** |

> 全局树在本批单元上 WAPE 最低、Bias 最接近 0；这是**本批 SKU 与切点上的观测**，
> 不构成「单一最优模型」的结论（A 包同样声明过）。

## 3. 覆盖对账（入 N 出 M）

| 项 | 数 |
|---|---:|
| 入：母集 SKU | 1,328 |
| 有月度序列 | 1,328 |
| 已判型（非证据不足） | 1,052 |
| 证据不足（<12 月） | 276 |
| 候选单元（1,328×5 切点） | 6,640 |
| 已评分单元 | 2,820 |
| 未评分跳过（SKU×切点） | 3,820，原因全部 `history_lt_min_train` |
| 评估评分 SKU | 790 |
| 出：C 行数（带边注） | 2,309 |

**对账闭环**：2,820 + 3,820 = 6,640；1,328 SKU 全部有月度序列，未评分只来自历史不足，没有静默丢弃。

> 与 A 对照：A 在 1,237 个合格 SKU 上评分 774；本次母集扩到 1,328、评分 790
> （多出的来自 A 未纳入的 91 个非合格 SKU）。

## 4. 接回 C（只加边注，不改数字）

`out/business_phase/final_bundle_routing.csv` = C 的 `final_bundle.csv` 全列原样 + 两列
`routing_type` / `routing_support`。

| routing_support | 行数 |
|---|---:|
| 支持充足（本批已评分） | 1,366 |
| 支持不足（未进入共同单元） | 943 |

- 「支持充足」= 该 SKU 进入本批共同单元且分型非证据不足；「支持不足」= 未进入共同单元或证据不足。
  两类都**不外推**。
- C 的任何数量、状态、blockers 字段都未被修改。

## 5. 可外推边界

- 分型只描述训练窗内的可观测形态，不预测促销/改款/上新。
- 证据不足（<12 月）的 SKU 不进入评估，映射到 C 时标「支持不足」。
- 全局树与基线在同一批单元上比较，结论限于本批 SKU、这批切点与 90 天窗口。
- 未用任何外层评估结果反向定型；也没有用插补需求充当真值。

## 6. 复现与耗时

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/full_sku_routing.py
```

- 耗时 9–55 秒（受机器负载影响），远低于任务预算。
- 连续两次运行：`full_sku_classification.csv` md5 `5f1245f0b0adea6f56cbc91a3448fced`、
  `final_bundle_routing.csv` md5 `229a008ff6c558405adffe9e341ceb93`，指标完全一致。
