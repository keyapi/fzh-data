---
type: Experiment-Results
title: 需求预测方法首轮影子对照（2026-11-07）
date: 2026-11-07
---

# 首轮影子对照：MA3 / SeasonalNaive / AutoETS / CrostonSBA / TSB / ADIDA

## 目的与边界

- 目的：**方法适配性筛查**，不宣布“换库胜出”。
- 输入冻结：D3b v3.8 current 月序列、D5 v6.6 p50/q95、owner/60cm 规则不变。
- 样本：零中位数 30、稳定 10、短历史 10（去重后 50 键）。
- 验证：月度滚动，h=4/6，两个 origin；**不是 97/157 天逐日**。
- 指标：WAPE、bias；零中位数段另看 MAE（actual 可能为 0）。
- 未覆盖：q95 区间校准、补货库存/缺货指标、全量 SKU。

## 结果（WAPE，越低越好）

### 稳定品（10 键）

| 模型 | h=4 | h=6 |
|---|---:|---:|
| ADIDA | **0.3796** | 0.3737 |
| AutoETS | 0.3828 | 0.3848 |
| CrostonSBA | 0.4082 | 0.4171 |
| MA3 | 0.4363 | **0.3699** |
| SeasonalNaive | 0.5123 | 0.4721 |

### 零中位数（30 键）

| 模型 | h=4 | h=6 |
|---|---:|---:|
| CrostonSBA | **0.7245** | 0.6619 |
| AutoETS | 0.8017 | 0.6411 |
| ADIDA | 0.8247 | 0.6318 |
| MA3 | 0.8545 | **0.6278** |
| SeasonalNaive | 0.8485 | 0.8807 |

零中位数段所有模型都是**正偏差**（预测高于实际），CrostonSBA 的 bias 最低（h=6 为 0.0533），但仍不能据此恢复执行。

## 解读

1. **没有单一模型全面胜出。** 稳定品 h=4 ADIDA 最好，h=6 MA3 最好；AutoETS 不是默认赢家。
2. **MA3 是有竞争力的基线，不应被“成熟库”直接替换。**
3. **零中位数是真正的难点。** CrostonSBA 短窗口最好，但 WAPE 仍 0.72；MA3 长窗口最好但不稳定。66 键继续隔离是正确处置。
4. **下一步不应直接换库，而应补：**
   - 97/157 天逐日验证（对齐 D5 目标）；
   - q95 区间校准/覆盖率；
   - 补货层指标：缺货天数/件数、满足率、平均/期末库存；
   - 零膨胀/hurdle 模型（含零概率）单独处理 66 键。

## 复现

```bash
"C:/Users/zhang/orca/workspaces/Cursor/forecast-refresh-oct27/.venv/Scripts/python.exe" \
  scripts/benchmark_forecast_methods_20261107.py
```

输出：`analysis/forecast_benchmark_20261107.xlsx`、`forecast_benchmark_20261107_detail.csv`、`forecast_benchmark_20261107_sample.csv`。

## 结论

**值得试用成熟实现，但不能今天宣布换库。** 先保留当前 D5/业务框架，把 97/157 天与补货指标补齐，再做第二轮。
