# T10 嵌套滚动评估报告

> 只做评估：不改主表、不改 T2 选模结论。

## 规则执行（七条）

- **r1_strata**：sample mother set, tier, dominant warehouse and intermittent labels use THIS block's training window only; the mother set also requires the first order month <= the outer origin (no not-yet-started SKUs)
- **r2_inner**：model chosen on inner cut points inside each outer training window
- **r3_outer**：outer refits every candidate and compares with fixed MA3/naive on the same sample
- **r4_window**：monthly cumulative h=3, step 3, labels available at the time (label_available_at), refit per window
- **r5_fallback**：pre-registered short-history rules; failures kept; missing predictions kept as null
- **r6_final**：旧 T2 测试期只作探索。当前标签覆盖（≤2026-09）内**不存在干净留出块**：T2 的 2026-03 外层切点其 90 天目标窗已触及 2026-07，故 2026-07..09 只是“最后一个可评估块”，不是“未使用块”。唯一干净证据来自前向影子（参数化脚本 forward_shadow.py；目标月标签闭合后按每月 4 日评分）。
- **r7_budget**：{"candidates": 6, "series": {"2025-10": 200, "2026-01": 200, "2026-06": 200}, "outer": 3, "inner": 3, "fit_cap": 14400, "time_cap_s": 1800}

## 计算规模

- 实际拟合 **10688** 次（上限 14400）；运行 **36.4 s**，tracemalloc 峰值 **130.1 MB**
- 每块样本 {'2025-10': 200, '2026-01': 200, '2026-06': 200} 序列 × 外层 3 × 内层 3，候选 6；样本按各块训练窗销量抽取（块间不同）
- 母集按块起点限制（**首单 ≤ 块起点**）：2025-10 母集 1027、剔除未首单 210、样本内最晚首单 2025-09、旧规则样本中当时未首单 28、新旧样本差异 332；2026-01 母集 1134、剔除未首单 103、样本内最晚首单 2025-12、旧规则样本中当时未首单 11、新旧样本差异 332；2026-06 母集 1206、剔除未首单 31、样本内最晚首单 2026-06、旧规则样本中当时未首单 0、新旧样本差异 0

## 同样本对比（WAPE，零需求单元格保留）

口径：`Σ|F−A| / ΣA`，三种方法都在**同一共同可评分子集**上（该块 valid 且三个预测均非 null）。零需求单元格保留在分子中（|F| 计为误差），对分母贡献 0；缺失预测为 null，不写 0。

| 外层 | 性质 | n | 有效 | 共同可评 | 计分(非零) | 零需求(保留) | 缺失预测 | 选择流程 | MA3 | naive |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025-10 | exploratory | 200 | 200 | 197 | 176 | 21 | 3 | 0.721 | 0.7408 | 0.5918 |
| 2026-01 | exploratory | 200 | 200 | 192 | 167 | 25 | 8 | 0.6515 | 0.6711 | 0.5553 |
| 2026-06 | last_evaluable_no_clean_holdout | 200 | 198 | 197 | 175 | 22 | 1 | 0.5255 | 0.4978 | 0.5016 |

- 最后一个可评估块：**2026-06|last_evaluable_no_clean_holdout**（目标窗 2026-07..09）。**它不是干净留出块**：T2 的 2026-03 外层切点其 90 天目标窗已触及 2026-07，因此该块已被部分使用；更早两块是探索性（旧测试期）。当前标签覆盖内**不存在干净留出块**，唯一干净证据来自前向影子。

## 内层选模分布

| 被选中模型 | 次数 |
|---|---:|
| naive | 136 |
| ma6 | 103 |
| seasonal_naive | 99 |
| autoets | 92 |
| ma3 | 89 |
| combo_ew | 79 |

## 最后一个可评估块的分层指标（tier/主仓/间歇均只用该块训练窗）

| 层 | n | 共同可评 | 零需求(保留) | 选择流程 | MA3 | naive |
|---|---:|---:|---:|---:|---:|---:|
| intermittent:no | 149 | 148 | 10 | 0.517 | 0.4887 | 0.4895 |
| intermittent:yes | 49 | 49 | 12 | 0.8593 | 0.8561 | 0.9773 |
| tier:high | 66 | 66 | 1 | 0.4935 | 0.4676 | 0.4567 |
| tier:low | 66 | 65 | 13 | 0.7667 | 0.7542 | 0.8517 |
| tier:mid | 66 | 66 | 8 | 0.7656 | 0.7073 | 0.8316 |
| warehouse:休斯顿1号仓 | 1 | 1 | 0 | 1.0 | 1.0 | 1.0 |
| warehouse:波兰-FZHPoland-covers | 82 | 82 | 16 | 0.5313 | 0.4211 | 0.5647 |
| warehouse:美东-CENTRADE | 54 | 54 | 2 | 0.4211 | 0.4882 | 0.5202 |
| warehouse:美中-FZH-DANEEY | 61 | 60 | 4 | 0.6563 | 0.532 | 0.4558 |

## 不确定性（最后一个可评估块，重抽 SKU 300 次）

- 选择流程 − MA3：均值 0.0346，5–95% [-0.1052, 0.1672]
- 选择流程 − naive：均值 0.0294，5–95% [-0.1114, 0.1654]
- range across resampled SKUs; describes uncertainty of the difference on unseen samples, not a significance test; zero-demand cells retained

## 失败与边界

- 失败（保留，不删序列）：`seasonal_naive:ValueError` × 343；`autoets:NotImplementedError` × 153；`outer:autoets:NotImplementedError` × 35；`autoets:ValueError` × 24；`outer:insufficient_history` × 2；`autoets:KeyError` × 1；`outer:autoets:KeyError` × 1
- 零需求单元格保留在 WAPE 分子中；`零需求(保留)` 列单独给出数量，缺失预测为 null（不进共同可评分子集，也不按 0 计分）。

## 前向影子（唯一干净证据路径）

- 每月 4 日（上月标签闭合后）；执行人：数据分析 worker（离线，只读 order_store）
- 预存内容：用 forecast_eval/forward_shadow.py（参数化：--data-cutoff/--origin，无写死截止期）预存样本、内层选模结果、各候选预测与生成时间；标签可得后再用同一文件评分
- 状态：当前标签覆盖内没有干净留出块；2026-10..12 的标签尚不存在，故本轮只交付最后一个可评估块（2026-07..09）与前向影子预存方案；下一窗口：2026-10..12（该窗口标签闭合后按预存文件评分）

## 措辞纪律

- WAPE 是加权绝对百分比误差，不是“错 SKU 比例”或“准确率”，也没有通用阈值；本报告只陈述“在（部分）未见样本上的差异与不确定性”，不使用“改进/稳健/干净留出”等说法，也不把探索性时段称作留出验证；模型选择仍未定。

## 结论

- 在最后一个可评估块（2026-07..09，非干净留出）上，选择流程与 MA3 / naive 的 WAPE 分别为 0.5255 / 0.4978 / 0.5016（共同可评 n=197，零需求保留 22 条）；差异的 SKU 重抽区间见上节。
- 内层选模分布显示没有单一候选占绝对多数，选模本身带来方差；本报告不据此宣布任何候选更好，模型选择仍未定。

