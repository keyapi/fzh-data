# T9 误差归因与反转诊断报告

> 只诊断，不改主表与 T2 选模结论。

- 序列：1237 条（可训练 774 / 短历史 463），切点 6 验证 + 6 测试
- 误差行（AutoETS）：9016；总绝对误差 156074.5

## 1. 逐 SKU × 切点误差

`error_attribution.csv` 每行：forecast / actual / error / abs_error / abs_error_share / series_kind / n_history。
`series_kind` 先按 `warehouse_map` 统一仓库别名再判定（T12 修正）：

| `series_kind` | 行数 | SKU 数 | 含义 |
|---|---:|---:|---|
| `warehouse_level_true` | 4985 | 430 | 映射后该 SKU 期内只有一个真实仓 |
| `multi_warehouse_true_sum` | 4031 | 344 | 映射后多仓真实销量之和 |
| `proxy_current_primary` | 0 | 0 | 无仓库信息，需用主仓代理 |

- 原始仓库名 26 个 → 映射后 17 个；**518 条序列**因别名归一从“多仓”改判为“单仓”（例：`C/Cord-Black-100-707-wow-Cover`, `C/Cord-Black-138-707-wow`, `C/Cord-Black-138-707-wow-Cover`, `C/Cord-Black-153-707-wow`, `C/Cord-Black-153-707-wow-Cover`）。
- 未映射仓库名：无。

## 2. 误差贡献与集中度

> 销量占比口径（全表统一）：全历史（该 SKU 首单月..2026-09，标签覆盖内）；分母 = 全部 eligible 序列同期总销量。全文所有‘销量占比/覆盖’均用此口径，不混用近 6 个月。

| Top20 SKU | 绝对误差 | 占总误差 | 占总销量(全历史) |
|---|---:|---:|---:|
| `TT0031038K0062927` | 4930.12 | 3.16% | 1.56% |
| `TT0031085K0063341` | 3493.1 | 2.24% | 0.70% |
| `TT0031085K0063342` | 3473.57 | 2.23% | 0.67% |
| `CENCord995-DKGrey-97` | 2994.09 | 1.92% | 1.43% |
| `C/Cord-DKBlue-100-713-wow` | 2781.4 | 1.78% | 0.54% |
| `C/Cord-White-100-706-wow` | 2679.0 | 1.72% | 0.50% |
| `TT0000671K0063721` | 2478.06 | 1.59% | 0.51% |
| `C/Cord-Grey-100-710-wow` | 2463.47 | 1.58% | 0.43% |
| `CENKZ1323-LTGrey-97` | 2216.39 | 1.42% | 1.01% |
| `C/Cord-Black-100-707-wow` | 2157.04 | 1.38% | 0.41% |

- Top10 SKU 合计占总绝对误差 **19.01%**

| 集中度 | SKU 数 | 销量占比(全历史) | 误差占比 |
|---|---:|---:|---:|
| top_1pct | 12 | 15.04% | 11.90% |
| top_5pct | 62 | 44.73% | 42.89% |
| top_10pct | 124 | 62.23% | 58.37% |

## 3. 反转分解（验证 → 测试）

- 子集：共同验证 3031、共同测试 4644、测试中与验证同 SKU 3540

| 模型 | 验证(共同子集) | 测试(同 SKU) | 测试(全部) |
|---|---:|---:|---:|
| autoets | 0.5232 | 0.7 | 0.7108 |
| combo_dynamic_ew | 0.545 | 0.6037 | 0.61 |
| seasonal_naive | 0.6577 | 0.6403 | 0.6227 |

**两部分分解**：
- ① 同 SKU 跨期变化（A−B 的 Δval → Δtest_same_skus）：**0.1181**
- ② SKU 构成差异（Δtest_same_skus → Δtest_full）：**0.0045**
- 参考：验证 Δ(A−B)=-0.0218，测试同 SKU Δ=0.0963

> 只有 ①同 SKU 跨期变化 与 ②SKU 构成差异 两部分都量化后才能讨论“为什么反转”；季节不同只是背景，不是已证原因

## 4. fallback 去重与销量覆盖

- fallback 行数 **112**，去重 SKU **71**，全历史销量覆盖 **0.10%**（与 §2 同一口径）
- `tiny_datasets`：102 行 / 66 SKU / 销量（全历史）0.100%
- `KeyError:'fitted'`：10 行 / 5 SKU / 销量（全历史）0.000%

**KeyError 最小复现**：
- SKU `TT0312568K0064135`，序列长度 **1**，值 [1.0]
- 调用：`statsforecast.models.AutoETS(season_length=1).fit(y.astype(float32))`（statsforecast 2.1.1）
- 错误：`KeyError: 'fitted'`；位置 `KeyError: 'fitted'`
- 分类：interface/input-validation issue in the library —— AutoETS 在 `models.py:788` 用 self.model_['fitted'] 计算残差，但长度为 1 的序列不会生成 'fitted' → KeyError。这不是 tiny_datasets（那是库显式抛出的历史不足错误）。
- 建议：调用前 guard：len(y) < 3 时直接用 Naive/常数；或升级 statsforecast 并向上游报告该输入校验缺口

## 5. 短历史序列的多方法滚动

短历史 SKU 463 条。训练下限取 **3 个月**，目标窗必须是完整 90 天且落在标签覆盖内：**392 条可评估**、71 条不可评估。（放宽到 2 个月可纳入 403 条，不采用：2 个点无法估计波动。）
类目借力（category_borrowed）的 peer 形状**在同一历史切点截断**：peer 必须在该切点已有 ≥24 个月历史，形状只取截至该切点的 12 个月，不使用截至 2026-09 的最后 12 个月。

对齐后共同可评分子集：**151 条**（全部方法都可评估）。只在各自可行子集上并列排名是不可比的，故下表同时给出两列，正式比较看最后一列：

| 方法 | 可行 SKU 数（各自子集） | 各自子集 MAE | 对齐子集 MAE (n=151) |
|---|---:|---:|---:|
| naive | 392 | 10.272 | 14.275 |
| ses | 392 | 9.591 | 12.662 |
| tsb | 392 | 9.692 | 12.03 |
| combo2 | 392 | 9.593 | 12.756 |
| category_borrowed | 151 | 13.118 | 13.118 |

- 低置信标记（历史 <12 月或可用窗口 <3 个）：可评估集 **139 / 392**；对齐子集 21 / 151。
- 各方法在对齐子集外的缺失条数：naive 0，ses 0，tsb 0，combo2 0，category_borrowed 241。
- 对齐子集上的排序（低→高）：tsb < ses < combo2 < category_borrowed < naive。各方法在各自子集上的数字不可横向比较（子集不同、难度不同），因此“类目借力 14.0 比 naive 10.3 差”这类并列结论在修正后不再成立。
- 没有用任何默认值冒充实测；类目借力只在有合格 peer 的序列上出现，它是兜底而不是默认首选。

## 6. 计算规模

- 运行 **139.0 s**，tracemalloc 峰值 **154.1 MB**
- 范围：{'series': 1237, 'trainable': 774, 'short': 463, 'origins': 12, 'models': ['naive', 'seasonal_naive', 'ma3', 'ma6', 'ma12', 'autoets', 'combo_dynamic_ew']}

## 7. 结论（三条）

1. 误差高度集中：见 §2 的 Top10/Top20 与集中度——少数 SKU 贡献大部分绝对误差。
2. 反转不是单一原因：同 SKU 跨期变化 = 0.1181，SKU 构成差异 = 0.0045（两部分都已量化，季节不同只是背景）。
3. fallback 的 112 行只对应 71 个 SKU、全历史销量覆盖 0.10%；其中 KeyError 属库输入校验缺口（长度 1–2 的序列），与 tiny_datasets 不是一类。

