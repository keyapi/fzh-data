---
okf: v0.1
type: Reference
title: 需求预测接口 — 决策包消费 schema（en-demand-forecast-v1）
description: 2026-10-29 补货决策包所需的 SKU/仓库级预测产物、字段语义、未知与不足月口径；2026-11-24 增补 classified 选型与 q85/q90/q95
tags: [forecast, demand, schema, decision-pack, reference]
date: 2026-11-24
status: verified
---

# 需求预测接口（en-demand-forecast-v1）

> 本文件只描述**输出契约**。实现与口径见
> [`../../forecast.py`](../../forecast.py)；运行记录见
> [`../reports/2026-10-27-forecast-refresh.md`](../reports/2026-10-27-forecast-refresh.md)。

## 1. 位置与版本

```
D:/Work/fzh-order-store/en-demand-v1/forecast/
├── CURRENT                      # 上一次成功 run 的目录名
└── <run_id>/                    # 例：forecast-20261027
    ├── forecast_manifest.json
    ├── forecast_report.md
    ├── forecast_sku_summary.parquet | .csv
    ├── forecast_sku_monthly.parquet
    ├── forecast_sku_windows.parquet
    ├── forecast_sku_warehouse_monthly.parquet
    ├── forecast_sku_warehouse_windows.parquet
    └── forecast_uom_totals.parquet   # 按已证 UOM 分组的总量；组间禁止相加
```

- 下游**只看 `CURRENT` 指向的目录**；不要跨 run 混读。
- `schema_version = en-demand-forecast-v1`。字段语义变更必须升级版本。
  2026-11-24 的 classified 选型与 q85/q90/q95 是**纯新增列**（旧列一个不删、
  默认 `--model-policy autoets` 行为逐字不变），因此不升版本。
- `forecast_manifest.json` 记录：输入文件路径 + sha256、日期范围、完整月/不足月、
  模型规则与参数、依赖版本、代码 git HEAD / 模块哈希、生成时间、行数对账、校验项。

复跑：

```bash
uv run python -m self_fulfilled_demand.forecast --run-id <new_run_id>
# 断货删失（默认关闭；独立验证 run 不改 CURRENT）
uv run python -m self_fulfilled_demand.forecast --run-id <id> --censoring \
  --censoring-mode conservative --no-current
# 只校验已有产物
uv run python -m self_fulfilled_demand.forecast --validate-only <run_dir>
# 分型选型（可选；默认 autoets 不变）
uv run python -m self_fulfilled_demand.forecast --run-id <id> --no-current \
  --model-policy classified --model-map <model_map.parquet|csv>
```

`--model-map` 的必需列：`product_id`（= `canonical_sku`）、`adopted_model`、
`demand_pattern`；可选 `pool` / `physical_form` / `canonical_uom` / `hist_avg_3y`。
同一 `product_id` 多行（多 pool/形态）时折叠为一条：
已知模型 > 非 `none` > `hist_avg_3y` 大 > 原顺序；折叠情况记在 manifest
`model.model_map.ambiguous_products`。模型名规范：`ets_ann→autoets`、
`croston_sba→sba` 等；不认识的名字按 `demand_pattern` 回退。

## 2. 主键与单位

| 表 | 主键 |
|---|---|
| `forecast_sku_summary` | `tongtool_sku` |
| `forecast_sku_monthly` | `tongtool_sku × forecast_month` |
| `forecast_sku_windows` | `tongtool_sku × lead_days` |
| `forecast_sku_warehouse_monthly` | `tongtool_sku × canonical_warehouse × forecast_month` |
| `forecast_sku_warehouse_windows` | `tongtool_sku × canonical_warehouse × lead_days` |
| `forecast_uom_totals` | `uom_group × lead_days` |

- **单位**：订单行件数（原始销售 SKU 单位）。不是 EN 物料库存单位。
  - 每行带 `canonical_uom` / `uom_status` / `uom_group` / `uom_totals_allowed`。
  - **只允许在 `uom_totals_allowed=true` 的同一 UOM 组内合计**；
    `uom_group=unknown` 是原始行计数（UOM 未证），不是「件」，不得与任何组合计。
  - 任何"全 SKU 总量"都必须在**单一 UOM 组内**给出；跨组数字没有业务含义。
- 预测 SKU = 通途 SKU；`canonical_sku` 只作映射参考，映射歧义不阻断预测，
  但会阻断净额（见 `netting_eligible`）。

## 3. 两张资格，不许混用

| 字段 | 含义 | 用途 |
|---|---|---|
| `forecast_eligible` | 有足够完整月历史，按规则能出预测 | 决定 `p50/p10/p90` 是否有值 |
| `netting_eligible` | canonical 层 SKU/UOM/仓库证据的 **SKU 级保守汇总**：任一历史行被阻断即整 SKU 记阻断 | 决定能否与该 SKU 的当前库存/在途相减；当前行仍须逐行检查 `netting_allowed` |

四种组合都合法：

| 预测 | 净额 | 含义 |
|---|---|---|
| ✅ | ✅ | 可直接进补货净算 |
| ✅ | ❌ | 有预测，但当前身份/单位未证 → 只作参考，不得与库存相减 |
| ❌ | ✅ | 历史太短；不拿 0 代替，标 `not_forecastable` |
| ❌ | ❌ | 两端都缺证据 |

`netting_block_reason` 原样来自 canonical `sku_coverage.block_reasons`；
`netting_evidence_missing` 表示该 SKU 不在 canonical 覆盖表里。
> `netting_eligible` 是**历史 canonical 行的 SKU 级汇总**，不是逐笔放行；
> 当前供应行必须继续按 `netting_allowed` 判断。

## 4. 关键字段

### 4.1 `forecast_sku_summary`

| 字段 | 语义 |
|---|---|
| `forecast_status` | `ok_autoets` / `ok_fallback_ma3` / `ok_short_ma3` / `ok_short_naive` / `not_forecastable_no_complete_month`；classified 额外 `ok_classified` / `ok_classified_pattern` / `ok_classified_no_demand` / `ok_classified_fallback` |
| `forecast_method` | 实际执行的模型：`autoets` / `snaive` / `naive` / `naive_last` / `ma3` / `sba` / `tsb` / `croston` / `none` |
| `forecast_method_reason` | 逐 SKU 的选型/回退原因（含异常摘要） |
| `selected_model` | classified 选中的模型（`map` 或分型回退的结果）；`autoets` policy 恒为 `autoets` |
| `selection_source` | `map` / `pattern` / `guard` / `default`；`guard` = T20 短史或 AutoETS 默认守卫 |
| `selection_reason` | 选型来源的一句话依据（map 行、分型、短史等） |
| `selected_demand_pattern` | map 里的 `demand_pattern`（无则空） |
| `model_map_product_id` | 参与 map 匹配的 `canonical_sku`（无则空） |
| `model_failure_reason` | 所选模型不可用并已回退时的原因；未回退为空 |
| `quantile_method` | `own_rolling_residual_quantile` / `pooled` / `insufficient_backtest` |
| `history_first_month` / `history_last_month` / `history_months` | 拟合用的**完整月**范围与样本量 |
| `history_nonzero_months` | 有正销量的完整月数 |
| `backtest_window` | 滚动回测覆盖的真实月份范围 |
| `backtest_origins` / `backtest_scored_cells` | 回测原点数 / 一步预测评分格数 |
| `backtest_wape` / `backtest_bias` | 所选方法在滚动原点上的 WAPE / 偏差（不是准确率） |
| `backtest_wape_ma3` / `_naive` / `_seasonal_naive` / `_autoets` | 同窗口对照模型 WAPE；不适用为 null |
| `backtest_underforecast_origins` / `backtest_overforecast_origins` | 回测原点中 actual>pred / actual<pred 的个数（方向诊断） |
| `backtest_residual_q10` / `backtest_residual_q90` | 需求残差 actual−pred 的实际下/上分位（已截断到含点预测；方向审计用） |
| `backtest_residual_upper_q85` / `_q90` / `_q95` | 需求残差的单侧上分位（>=0），q85/q90/q95 的估计来源；`quantile_method=pooled` 时为 null |
| `canonical_uom` / `uom_status` | 来自 canonical 覆盖表；`known_piece` 才是已证件类单位 |
| `uom_group` | `个` / `套` / `not_piece` / `unknown` |
| `uom_totals_allowed` | 只有已证件类单位为 true；`unknown` 一律 false |
| `interval_basis` | `own_rolling_residual_quantile` / `pooled_relative_error` / `insufficient_backtest` |
| `censoring_applied` | 该 SKU 是否应用了断货删失补值（默认关闭时为 false） |
| `censored_months` / `censored_zero_months` | 训练序列中标记为删失的月数 / 其中销量=0 的月数 |
| `censoring_replaced_months` / `censoring_added_units` | 实际补值月数 / 补值增加的观测单位（不是损失销量） |
| `censoring_mode` | `conservative` / `aggressive`；关闭时为空 |
| `p50_l60` / `p10_l60` / `p90_l60` | 从决策日起 L60 日历窗口的预测与区间（件） |
| `q85_l60` / `q90_l60` / `q95_l60` | L60 窗口的 85/90/95 分位；构造上 `q85<=q90<=q95` 且 `p50<=q90` |
| 同上 `_l90` / `_l120` / `_l180` | L90 / L120 / L180（L180 仅情景，需 7 个月预测覆盖） |
| `zero_forecast` | 预测真为 0（**不是**不可算） |
| `negative_clipped` | AutoETS 出现负值并已截零 |
| `data_cutoff` | 本次输入最后一天（`YYYY-MM-DD`） |
| `complete_month_max` | 最后一个完整月 |
| `partial_month` | 决策相关不足月（当前 `2026-10`） |
| `partial_month_observed_units` | 该不足月已观测件数 |
| `partial_month_days` / `partial_month_month_days` | 已观测天数 / 自然月天数 |
| `partial_month_implied_full_rate` | 线性折算整月率（**仅参考，不是可比月**） |

> 启用删失时：补值只改**训练序列**；回测评分真值仍用原始 actual。
> 每个回测原点只用 `y[:i]` 重算补值（含 P90 截顶），并使用当时可见库存重建的 flags
> （`rebuild_flags_as_of`，不再用全期 flags），不使用未来月份。
> `allowed_skus=0` 或回测实际补值=0 → 直接报错，不静默通过。
> `allowed_skus` 严格按 UOM-CANONICAL：个 + 仅 TJ# 套（is_stock_item=0）；
> 非 TJ# 的 stock_uom=套 记 `uom_conflict`、不进 allowed。
> 回测补值统计只给 `by_uom`（个/套），不跨 UOM 求和；月点按 origin 累计，
> 同一训练月可能重复，**不是独立新增销量**。
> 窗口求和若发现加权月不在预测数组内（如 L180 缺 2027-04）→ 直接报错，不静默截断。
> `added_units` 按 UOM 分列（manifest `model.censoring.by_uom`），不跨 UOM 合计。

> 不可预测的 SKU：以上 `p50/p10/p90` 全为 **null**，不是 0。
> 区间缺失时 `interval_basis=insufficient_backtest`，不伪造区间。

### 4.2 `forecast_sku_monthly`

| 字段 | 语义 |
|---|---|
| `forecast_month` | 预测月（当前 2026-10 … 2027-04，覆盖 L180；180 仅情景） |
| `horizon_index` | 从 1 开始的月序号 |
| `p50` / `p10` / `p90` | 该月预测与区间（件） |
| `q85` / `q90` / `q95` | 该月 85/90/95 分位；与区间同源（滚动有符号残差），不是已校准分位 |
| `selected_model` / `selection_source` | 该 SKU 的选型结果与来源（与 summary 一致） |
| `is_history_partial_month` | 该预测月正好是不足月（如 2026-10）时 true；此月的**历史观测**不参与拟合 |
| `month_note` | 不足月说明 |

### 4.3 `forecast_sku_windows` / `forecast_sku_warehouse_windows`

| 字段 | 语义 |
|---|---|
| `lead_days` | 60 / 90 / 120 / **180（仅情景，不承诺精度）** |
| `window_start` / `window_end` | 决策日起算的日历窗口 |
| `p50` / `p10` / `p90` | 窗口累计预测（= 月度预测按日历天数加权求和） |
| `q85` / `q90` / `q95` | 窗口累计分位（= 月度 q 的日历加权和，校验与 p50 同口径） |
| `selected_model` / `selection_source` / `quantile_method` | 选型与分位方法溯源 |
| `canonical_uom` / `uom_group` / `uom_totals_allowed` | 单位证据，必须随窗口一起读；跨组不得相加 |

窗口权重公式与 T5 一致（`window_weights`）；月度表可复算窗口表。

### 4.5 `forecast_uom_totals`（禁止跨组相加）

| 字段 | 语义 |
|---|---|
| `uom_group` | `个` / `套` / `not_piece` / `unknown` |
| `lead_days` | 60 / 90 / 120 / **180（仅情景，不承诺精度）** |
| `skus` / `forecastable_skus` | 该组 SKU 数 / 可预测数 |
| `p50_sum` / `p10_sum` / `p90_sum` | **组内**合计；`unknown` 组是原始行计数 |
| `netting_eligible_skus` / `netting_blocked_skus` | 组内净额通过 / 阻断 SKU 数 |
| `p50_sum_netting_eligible` / `p50_sum_netting_blocked` | 组内按净额资格拆分的 P50 |
| `netting_blocked_share_within_uom` | **组内**阻断占比；分母是该组 P50，不是全表 |
| `totals_allowed` | 只有已证件类组为 true；`unknown`/`not_piece` 为 false |

- 本表**没有**全 SKU 统一合计行；下游不得自己把不同 `uom_group` 的 `p50_sum` 相加。
- `unknown` 组只能说明"原始行计数"，不能叫「件」。

### 4.4 仓库分配

| 字段 | 语义 |
|---|---|
| `canonical_warehouse` | canonical 仓名（旧名已按证据合并） |
| `allocation_share` | 该仓在 SKU 最近 3 个完整月销量中的占比 |
| `allocation_basis` | `last_3_complete_months(2026-07..2026-09)` |
| `allocation_status` | `allocated_by_recent_share` / `zero_recent_share` / `no_recent_sales` |

- 有近 3 月销量时，**同一 SKU 同月各仓 `allocation_share` 之和 = 1**。
- 没有近 3 月销量时，`allocation_share` 与分配后的 `p50` 都是 **null**（未知，不写 0）；
  SKU 级预测仍保留在 summary / monthly。
- 仓库分配是**假设**，不是已证的履约分配。

## 5. 不足月口径（硬约束）

- `2026-10` 只有 26 天（数据截止 2026-10-26），**不进入拟合、不参与同比/趋势**。
- 它在月度表里以 `is_history_partial_month=true` 出现，表示「这是整月预测」，
  不是「用部分月当真值」。
- summary 里单列 `partial_month_observed_units` / `partial_month_implied_full_rate`；
  `implied_full_rate` 只是线性折算，任何比较都应改用完整月。
- 同理，数据首月 `2022-12`（12 天）也被排除；manifest 的 `partial_months` 列全。

## 6. 模型口径（不要误读）

- 默认 AutoETS（statsforecast），失败或短史按 T20 guard 回退：
  `len<3 → naive 末值`、`3<=len<7 → MA3`、`len>=7 → AutoETS`。
- 选型**不按回测切换**：DECISIONS D19 明确没有干净留出块，现有证据不支持
  「选择流程 / AutoETS 更好」；回测只用于透明度和区间尺度。
- 区间是滚动经验/共形式：own ≥ 3 个原点时，用**需求残差 actual−pred** 的
  10/90 分位（`run_backtest` 存 `pred−actual`，生成区间时取反），
  截断到包含点预测且下界非负；否则用池化相对误差系数（截顶 3×）。
  - 历史持续**低估** → 需求上界扩张；持续**高估** → 下界扩张。方向写反属于缺陷。
  - **不是已标定分位**，不承诺 80% 覆盖率；名义水平记录在 `interval_level_nominal`。
- 零预测：`zero_forecast=true` 是模型输出 0，**不是未知**（未知写 null），
  也**不是「确认没有需求」**。零预测的 P90 可能仍 >0，必须逐 SKU 看区间，
  不得用"零"批量推断无需求。
- 本模块不产生补货量、不净额、不下单。

## 7. 已知限制

1. GS 历史是**发货口径**（despatch_date），EN 增量是**销售口径**（sale_date）；
   边界月按既有 consumer 规则拼接，不做额外换算。
2. 预测在原始销售 SKU 上建模，不证明历史 BOM/发货形态；因此不得把预测直接
   当成成品/皮壳/半成品需求拆分。
3. 仓库分配依赖最近 3 个完整月；新品/换仓当月会落到 `no_recent_sales` 或
   `zero_recent_share`，需人工确认，不得当 0 需求。
4. `backtest_wape` 对实际量为 0 的 SKU 无定义（null），不是 0 误差。
5. **跨 UOM 的数字没有业务含义**：只读 `forecast_uom_totals` 的组内合计；
   `unknown` 组是原始行计数，不是件。
6. 旧产物（SC09 M1-TRIAL-v1、T5 `replenishment_v2.csv`、V1 `model_race.json`）
   的数据截止均早于本次；见 manifest `supersedes`，不要混用。
