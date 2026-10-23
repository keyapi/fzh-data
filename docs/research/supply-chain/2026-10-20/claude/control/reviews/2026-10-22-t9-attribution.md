---
okf: v0.1
type: Review
title: T9 误差归因与反转诊断
date: 2026-10-22
owner: claude-worker
status: 完成；只诊断，不改主表与 T2 选模
artifacts:
  - experiments/business_phase/forecast_eval/attribute_errors.py
  - experiments/business_phase/forecast_eval/error_attribution.csv
  - experiments/business_phase/forecast_eval/error_attribution.json
  - experiments/business_phase/forecast_eval/attribution_report.md
---

# T9 误差归因与反转诊断

> 只做诊断：未改主表、未改 T2 选模结论、未改任何既有产物。
> 数据：`order_store.duckdb`（只读）、`destinations.json`、`explanations.csv`。

## 0. 规模

| 项 | 值 |
|---|---|
| 序列 | 1,237（可训练 774 / 短历史 463） |
| 切点 | 验证 6（2025-01..06）+ 测试 6（2025-10..2026-03） |
| 误差行（AutoETS） | **9,016** |
| 运行 | **157 s**；tracemalloc 峰值 **153 MB** |
| 模型 | naive / seasonal_naive / MA3 / MA6 / MA12 / AutoETS / combo_dynamic_ew（无无休止赛马） |

## 1. 逐 SKU × 切点误差与序列类型

`error_attribution.csv` 每行：`forecast / actual / error / abs_error /
abs_error_share / series_kind / n_history`。

| `series_kind` | 行数 | 含义 |
|---|---:|---|
| `warehouse_level_true` | 1,104 | 该 SKU 期内只有一个真实仓，SKU 序列≡该仓序列 |
| `multi_warehouse_true_sum` | 7,912 | 多仓真实销量之和（订单行仓库名齐全） |
| `proxy_current_primary` | **0** | 无需代理：`gs_orders.warehouse` 无空值 |

## 2. 误差贡献与集中度

- **Top10 SKU 占总绝对误差 19.01%**（Top20 逐个在 JSON `top20`）。
- Top20 中误差最大的：`TT0031038K0062927`（4,930.1 绝对误差，占 3.16%，销量占 1.56%）、
  `TT0031085K0063341`（3,493.1 / 2.24%）、`TT0031085K0063342`（3,473.6 / 2.23%）。

| 集中度 | SKU 数 | 销量占比 | 误差占比 |
|---|---:|---:|---:|
| 前 1% | 12 | 15.04% | 11.90% |
| 前 5% | 62 | 44.73% | 42.89% |
| 前 10% | 124 | 62.23% | 58.37% |

误差基本随销量走（前 5% 销量 44.7% / 误差 42.9%），**没有异常的“小销量大误差”集中**。

## 3. 反转分解（验证 → 测试）

| 模型 | 验证（共同子集 3,031） | 测试（同 SKU） | 测试（全部 4,644） |
|---|---:|---:|---:|
| AutoETS | 0.5232 | 0.7000 | 0.7108 |
| combo_dynamic_ew | 0.5450 | 0.6037 | 0.6100 |
| seasonal_naive | 0.6577 | 0.6403 | 0.6227 |

**两部分分解**（Δ = AutoETS − combo_dynamic_ew）：

| 部分 | 值 | 含义 |
|---|---:|---|
| ① **同 SKU 跨期变化** | **+0.1181** | 同一批 SKU 从验证期到测试期，AutoETS 相对变差 0.118 |
| ② **SKU 构成差异** | **+0.0045** | 测试全集的 SKU 构成本身只贡献 0.0045 |
| 参考 | 验证 Δ −0.0218；测试同 SKU Δ +0.0963 | — |

**结论**：反转**主要来自同一批 SKU 的跨期表现变化（0.1181），SKU 构成差异可忽略（0.0045）**。
季节不同只是背景；两部分已分别量化后，才可以说“不是换了一批 SKU 造成的”。

## 4. fallback 去重与销量覆盖

| 项 | 值 |
|---|---:|
| fallback 行数（商品×仓） | 112 |
| **去重 SKU 数** | **71 / 1,237** |
| 该集合 6 个月销量覆盖 | **0.1%** |
| `tiny_datasets`（历史不足，库显式错误） | 102 行 / 66 SKU / 销量 0.1% |
| `KeyError:'fitted'`（实现/接口） | 10 行 / 5 SKU / 销量 0.0% |

**KeyError 最小复现**（statsforecast **2.1.1**）：

- SKU `TT0312568K0064135`，序列长度 **1**（2026-09 单月，值 `[1.0]`）；
- 调用 `statsforecast.models.AutoETS(season_length=1).fit(y.astype(float32))`；
- 报错 `KeyError: 'fitted'`，位置 `statsforecast/models.py:788`：
  `self.model_["actual_residuals"] = y - self.model_["fitted"]`；
- **分类：库的输入校验缺口**（长度 1–2 的序列不生成 `fitted`），**不是 tiny_datasets**
  （后者是库对历史不足的显式异常）；
- 修复建议：调用前 guard `len(y) < 3` 时用 Naive/常数；或升级 statsforecast 并向上游报告。

## 5. 短历史序列（<24 月）多方法滚动

短历史 **463** 条中 **392** 条可评估、**71** 条不可评估（历史过短，找不到
“≥2 个月训练 + 完整 90 天目标窗”的起点；不填默认值）。

| 方法 | 可行 SKU 数 | 平均绝对误差 |
|---|---:|---:|
| naive | 392 | 10.272 |
| **SES** | 392 | **9.591** |
| TSB | 392 | 9.692 |
| 类目借力（同物料组形状 × 自身水平） | **158**（需组内有 ≥24 月的 peer） | 14.002 |
| 简单组合（naive/SES/TSB 等权） | 392 | 9.593 |

- **低置信标记**：历史 <12 月或可用窗口 <3 个 → `low_confidence=True`，共 **139 / 392**。
- 短历史序列**不应一律用 MA3**：SES/TSB 在可获得样本上均优于 naive，类目借力只在
  158 条有 peer 的序列上可行且误差更高（14.0）——它是“兜底”而不是默认首选。
- 全程未用默认值冒充实测。

## 6. 三条诊断结论

1. **误差集中但不畸形**：Top10 SKU 占 19.0% 绝对误差，前 5% SKU 的销量与误差占比几乎相同
   （44.7% vs 42.9%），误差主要跟随销量规模。
2. **验证→测试反转是“同 SKU 跨期变化”为主（+0.1181），构成差异仅 +0.0045**；
   不能把反转归因于“换了一批 SKU”，季节差异只是背景，真实原因仍需按 SKU 的
   促销/断货/上架事件进一步查（本报告只做分解，不宣布原因）。
3. **fallback 影响面很小**：112 行只对应 **71 个 SKU、0.1% 销量**；其中 5 个 SKU 的
   `KeyError:'fitted'` 是库对 1–2 个月序列的输入校验缺口，与历史不足（tiny_datasets）
   是两类问题，需在调用层加长度 guard。

## 7. 校验与复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/attribute_errors.py
uv run python scripts/check_secrets.py
```

- 输出：`error_attribution.csv`（9,016 行）、`error_attribution.json`、`attribution_report.md`。
- DB 只读，前后 sha256 一致；脚本确定性（固定切点、固定模型参数）。
- 未改主表 / T2 选模 / T3–T6 与 V1 产物；`check_secrets.py` 零输出。
