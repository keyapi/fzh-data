# T16 短历史方法对照报告

> **开发期验证**：全部数据均已见过，**不是独立留出**；任何差值都不构成“改进已证实”。措辞只说“在已见数据上的差异”。

## 0. 范围与预先注册的方案

- 短历史（<24 月）：**463** 条；可评分 SKU **403**、共同交集 SKU **151**、共同交集单元格 **685**（全部单元格 1457）。
- 窗口：月度累计 h=3（origin+1..origin+3），步长 **3**，目标窗必须完全落在标签覆盖（≤2026-09）内。
- 对齐：先取五方法 **(SKU, origin)** 共同交集，再聚合；不使用各方法各自子集。
- 类目借力：peer 必须在该切点已有 ≥24 个月历史，形状只取截至该切点的 12 个月。
- 组合：naive/SES/TSB 固定等权；低置信：历史 <12 月或共同窗口 <3 个。
- AutoETS guard（T20）：**len<7 直接 fallback，不尝试 AutoETS**；阈值来自 statsforecast 2.1.1 实测（§3）。

## 1. 各方法指标（共同交集）

| 方法 | MAE | WAPE | Bias | 单元格 | SKU |
|---|---:|---:|---:|---:|---:|
| naive | 10.778 | 0.6422 | -0.1279 | 685 | 151 |
| ses | 10.095 | 0.6015 | -0.1272 | 685 | 151 |
| tsb | 10.104 | 0.602 | -0.1319 | 685 | 151 |
| category_borrowed | 11.687 | 0.6963 | -0.0022 | 685 | 151 |
| combo_ew | 9.928 | 0.5915 | -0.129 | 685 | 151 |

按历史长度分组（同一对齐口径）：

| 组 | 单元格 | 方法 | MAE | WAPE | Bias |
|---|---:|---|---:|---:|---:|
| 3<=n<13 | 53 | naive | 7.868 | 1.118 | 0.3351 |
| 3<=n<13 | 53 | ses | 6.625 | 0.9414 | 0.2949 |
| 3<=n<13 | 53 | tsb | 6.33 | 0.8994 | 0.2146 |
| 3<=n<13 | 53 | category_borrowed | 7.649 | 1.0868 | 0.2774 |
| 3<=n<13 | 53 | combo_ew | 6.726 | 0.9557 | 0.2816 |
| 13<=n<24 | 632 | naive | 11.022 | 0.6262 | -0.1435 |
| 13<=n<24 | 632 | ses | 10.386 | 0.5901 | -0.1414 |
| 13<=n<24 | 632 | tsb | 10.421 | 0.592 | -0.1435 |
| 13<=n<24 | 632 | category_borrowed | 12.026 | 0.6832 | -0.0116 |
| 13<=n<24 | 632 | combo_ew | 10.196 | 0.5793 | -0.1428 |

## 2. fallback 可靠性（AutoETS 失败 → MA3 的现规则）

- 对齐子集内 AutoETS 失败单元格 **289**（涉及 147 SKU）：`fallback_MA3(3<=len<7)` × 289
- 全部候选单元格（1457）上的失败计数：`fallback_MA3(3<=len<7)` × 763

失败单元格上各规则的差异（tr<7 是 AutoETS 不可用的主要区间）：

| 规则 | 单元格 | MAE | WAPE | Bias |
|---|---:|---:|---:|---:|
| rule_current | 289 | 10.567 | 0.7329 | -0.1704 |
| rule_tsb | 289 | 11.014 | 0.7639 | -0.1789 |
| rule_ses | 289 | 10.529 | 0.7302 | -0.184 |
| rule_naive | 289 | 10.606 | 0.7355 | -0.2268 |

差值（相对现规则，MAE）：rule_tsb_minus_current_mae +0.447，rule_ses_minus_current_mae -0.038，rule_naive_minus_current_mae +0.039

SKU 重抽 300 次的 MAE 差（alt − 现规则）：

| 替代 | 均值 | 5–95% | 区间含 0 |
|---|---:|---|---|
| rule_tsb | +0.459 | [-0.697, +1.980] | 是 |
| rule_ses | -0.026 | [-0.710, +0.613] | 是 |
| rule_naive | +0.064 | [-1.680, +1.510] | 是 |

## 3. KeyError/tiny-dataset guard 前后对照

规则：len(y) < 7 → 不尝试 AutoETS，直接 fallback（len<3→naive，3<=len<7→MA3）；len>=7 才尝试 AutoETS
阈值依据：statsforecast 2.1.1 实测：len=1 抛 KeyError('fitted')；len=2..6 抛 NotImplementedError('tiny datasets')；len=7 起可拟合。阈值 7 由此预先注册，未按评估效果调参。

| 历史长度 | 条数 | 修复前（raw AutoETS） | 修复后（len<7→fallback） |
|---|---:|---|---|
| n<3 | 15 | {'NotImplementedError': 10, 'KeyError': 5} | {'fallback_naive(len<3)': 15} |
| 3<=n<13 | 203 | {'ok': 147, 'NotImplementedError': 56} | {'ok': 147, 'fallback_MA3(3<=len<7)': 56} |
| 13<=n<24 | 245 | {'ok': 245} | {'ok': 245} |

按精确长度拆分：

| len | 条数 | 修复前 | 修复后 |
|---:|---:|---|---|
| 1 | 4 | {'KeyError': 4} | {'fallback_naive(len<3)': 4} |
| 2 | 11 | {'NotImplementedError': 10, 'KeyError': 1} | {'fallback_naive(len<3)': 11} |
| 3 | 16 | {'NotImplementedError': 16} | {'fallback_MA3(3<=len<7)': 16} |
| 4 | 16 | {'NotImplementedError': 16} | {'fallback_MA3(3<=len<7)': 16} |
| 5 | 13 | {'NotImplementedError': 13} | {'fallback_MA3(3<=len<7)': 13} |
| 6 | 11 | {'NotImplementedError': 11} | {'fallback_MA3(3<=len<7)': 11} |
| 7 | 11 | {'ok': 11} | {'ok': 11} |

- len<7 全部走 fallback：len=1–2 用 naive，len=3–6 用 MA3；不再尝试 AutoETS，因此不再触发 tiny_datasets/KeyError
- len=1–2 的序列首单在 2026-08/09，当前没有完整 3 个月目标窗，故不进入计分；guard 只保证不再抛错，不伪造评分
- 阈值 7 来自库的实测行为（见 threshold_basis），不是按效果挑选；len>=7 的行为与扩展前完全一致
- 断言：len<7 共 71 条全部走 fallback、预测有限；未捕获异常 0 条（463 条短历史逐条检查）。

## 4. 同类异常（计数与处理）

| 异常 | 数量 | 处理 |
|---|---:|---|
| 单点序列（len=1） | 4 | naive 常数预测；无完整目标窗，本轮不计分 |
| 两点序列（len=2） | 11 | naive 末值；无完整目标窗，本轮不计分 |
| 全零序列 | 0 | 全零序列：所有方法预测 0；若出现在可评分子集则保留（分子 0） |
| 常数序列 | 1 | 常数序列：正常评分，不做特殊剔除 |
| 零需求单元格 | 102 | 零需求单元格保留在 WAPE 分子，对分母贡献 0 |
| AutoETS 非 ok 单元格 | 289 | 按原因保留并回退 MA3 |

## 5. 低置信标记

- 判定：历史 <12 个月，或共同可评分子集内窗口数 <3
- 数量：**337 / 463**（其中进入对齐子集 25 条）。

## 6. 结论与建议（开发期，非独立留出）

- 在已见的 685 个共同交集单元格上，MAE 最低的是 **combo_ew**（9.928），最高的是 **category_borrowed**（11.687）；这只是已见数据上的差异，不是独立验证。
- fallback（tr<7，289 格）相对现规则的 MAE 差：tsb +0.459（[-0.697, +1.980]），ses -0.026（[-0.710, +0.613]），naive +0.064（[-1.680, +1.510]）。
- 判定（区间是否跨 0）：更差且区间不含 0 = 无；与现规则不可区分 = tsb, ses, naive；明确更优 = 无。
- **结论：不建议**仅凭本表改用 TSB/SES——没有任何替代方法的区间整体更优；tsb、ses、naive 与现规则不可区分（区间跨 0）；现规则（AutoETS 失败→MA3）保留。
- 计算规模：1457 个候选单元格、5.9 s。

## 7. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/short_history_eval.py
uv run python scripts/check_secrets.py
```

DB 只读（前后 sha256 一致）；脚本确定性（固定切点、固定方法参数）。

