---
okf: v0.1
type: Index
title: pb_stockout 实验脚本状态
date: 2026-10-23
owner: claude-worker-2
---

# pb_stockout 实验脚本状态

**只按本表使用；标 ❌ 的脚本数字不可用。**

| 脚本 | 状态 | 用途 | 产物 |
|---|---|---|---|
| `pb_cross_source.py` | ✅ 可用（口径需配合 v2 措辞） | 三源交叉 + 信号簇 | `pb_30sku_list.csv`、`stockout_intervals.csv`、`cross_source_report.md` |
| `audit_pb_censored.py` | ✅ 可用 | R1 核查：信号日重建、三量拆分、时点检查、bootstrap | `stockout_intervals_decomposed.csv`、`censored_audit.json` |
| `censored_r2.py` | ✅ 可用（**当前权威**） | 修正后的单侧下限损失 + 逐切点冻结 + 集合差异 | `censored_r2.json`、`stockout_intervals_v2.csv`、`sku_set_diff.csv`、`ratio_zero_denominator_cells.csv` |
| `test_censored_loss.py` | ✅ 可用 | M01 回归测试（含 301 反例 `y=[0,0,10]`） | 终端 `ALL PASS` |
| `censored_compare.py` | ❌ **废止**（commit `e1b9b5d7`） | — | 其 `censored` 路线把"预测低于下限"当成免责，损失方向相反；`censored_compare.*` 的结论与数字不得再引用 |

## 口径要点（引用本目录任何数字前先读）

- `signal_cluster_span_days` 是**跨度**，不是连续受阻时长；连续时长与恢复日期为 `unknown`。
- `lower_bound_month` = 该月至少有 1 个已观测信号日；跨度与假设性扩展窗口**不参与打标签**。
- `forecast_above_shipment_ratio` 是中性描述统计，不是缺货率、不是积压、不是服务水平。
- 一切结论限定在冻结的 26 个 SKU；这是**回顾性同批 SKU 实验**，不是部署回测。
- 详见 `../../control/reviews/2026-10-23-censored-r2-fix.md`。
