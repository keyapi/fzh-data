# T10 嵌套滚动评估报告

> 只做评估：不改主表、不改 T2 选模结论。

## 规则执行（七条）

- **r1_strata**：strata use each training window only (final block uses its own training data)
- **r2_inner**：model chosen on inner cut points inside each outer training window
- **r3_outer**：outer refits every candidate and compares with fixed MA3/naive on the same sample
- **r4_window**：monthly cumulative h=3, step 3, labels available at the time (label_available_at), refit per window
- **r5_fallback**：pre-registered short-history rules; failures kept; zero-denominator cells listed separately
- **r6_final**：old T2 test period is exploratory; final evaluation uses the unused 2026-07..09 block; a forward shadow plan covers months whose labels do not exist yet
- **r7_budget**：{"candidates": 6, "series": 200, "outer": 3, "inner": 3, "fit_cap": 14400, "time_cap_s": 1800}

## 计算规模

- 实际拟合 **9525** 次（上限 14400）；运行 **30.9 s**，tracemalloc 峰值 **127.0 MB**
- 样本 200 序列 × 外层 3 × 内层 3，候选 6

## 同样本对比（WAPE，零分母单元格单列）

| 外层 | 性质 | n | 计分 | 零分母 | 选择流程 | MA3 | naive |
|---|---|---:|---:|---:|---:|---:|---:|
| 2025-10 | exploratory | 200 | 149 | 45 | 0.6461 | 0.755 | 0.5297 |
| 2026-01 | exploratory | 200 | 159 | 28 | 0.5973 | 0.6633 | 0.5454 |
| 2026-06 | final_unused | 200 | 173 | 25 | 0.4629 | 0.5253 | 0.426 |

- 最终评估块：**2026-06|final_unused**（2026-07..09，T2 未用作测试期）；更早两块是探索性（旧测试期）。

## 内层选模分布

| 被选中模型 | 次数 |
|---|---:|
| naive | 136 |
| ma6 | 94 |
| autoets | 92 |
| seasonal_naive | 86 |
| combo_ew | 74 |
| ma3 | 68 |

## 最终块分层指标（分层只用该外层训练窗的数据）

| 层 | n | 计分 | 零分母 | 选择流程 | MA3 | naive |
|---|---:|---:|---:|---:|---:|---:|
| tier:high | 66 | 66 | 0 | 0.4324 | 0.5098 | 0.3998 |
| warehouse:美东-CENTRADE | 67 | 60 | 7 | 0.3473 | 0.5033 | 0.357 |
| intermittent:no | 153 | 139 | 14 | 0.4566 | 0.5208 | 0.4139 |
| warehouse:美中-FZH-DANEEY | 58 | 48 | 10 | 0.701 | 0.6009 | 0.5646 |
| warehouse:波兰-FZHPoland-covers | 71 | 63 | 8 | 0.5286 | 0.4216 | 0.4839 |
| tier:mid | 66 | 66 | 0 | 0.9043 | 0.637 | 0.7651 |
| warehouse:星链海外仓 | 2 | 2 | 0 | 0.1111 | 0.6296 | 0.1111 |
| tier:low | 66 | 41 | 25 | 1.8924 | 1.9556 | 1.9111 |
| intermittent:yes | 45 | 34 | 11 | 0.9583 | 0.878 | 1.378 |

## 不确定性（最终块，重抽 SKU 300 次）

- 选择流程 − MA3：均值 -0.0589，5–95% [-0.1928, 0.05]
- 选择流程 − naive：均值 0.039，5–95% [-0.0847, 0.1455]
- range across resampled SKUs; describes uncertainty of the difference on unseen samples, not a significance test

## 失败与边界

- 失败（保留，不删序列）：`seasonal_naive:ValueError` × 333；`autoets:NotImplementedError` × 162；`outer:insufficient_history` × 50；`outer:autoets:NotImplementedError` × 39；`autoets:ValueError` × 35；`outer:autoets:KeyError` × 1；`autoets:KeyError` × 1
- 零分母单元格按外层单列（见上表 `零分母` 列），不计入 WAPE 分母。

## 前向影子方案（未使用月份）

- 每月 4 日（上月标签闭合后）；执行人：数据分析 worker（离线，只读 order_store）
- 记录内容：用同一脚本、同一 200 序列样本与同一内层规则，重跑上一个连续 3 个月的累积 h=3 评估，记录各候选 WAPE、被选中模型、零分母单元格数、失败原因与 fallback 次数
- 状态：2026-10..12 的标签尚不存在，故本轮只交付 2026-07..09 的最终评估与影子方案；下一窗口：2026-10..12（标签可得后执行）

## 措辞纪律

- WAPE 是加权绝对百分比误差，不是“错 SKU 比例”或“准确率”，也没有通用阈值；本报告只陈述“在未见样本上的差异与不确定性”，不使用评价性结论，也不把探索性时段称作留出验证。

## 结论

- 在最终未使用块（2026-07..09）上，选择流程与 MA3 / naive 的 WAPE 分别为 0.4629 / 0.5253 / 0.426；差异的 SKU 重抽区间见上节。
- 内层选模分布显示没有单一候选占绝对多数，选模本身带来方差；本报告不据此宣布任何候选更好。

