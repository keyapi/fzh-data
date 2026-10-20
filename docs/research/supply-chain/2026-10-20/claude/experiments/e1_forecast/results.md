---
okf: v0.1
type: Experiment-Results
title: E1 预测基线回测（R01/R02 修正版）— PB 楔形枕 8 SKU
description: 加入标签可知性切分（label lag）与数据质量闸门后重跑；验证/测试目标月零重叠，held-out 测试期 TSB 0.511、ens5 0.520、naive 0.602；验证期改选 Croston/MA3，测试期仍逊于 ens5，选择规则依旧不可外推。
date: 2026-10-20
tags: [supply-chain, forecasting, backtest, intermittent-demand, experiment, revised]
---

# E1 预测基线回测（R01/R02 修正版）— PB 楔形枕 8 SKU

> 数据：通途订单月表 `通途订单202301`–`202607`（43 张），按**发货日期**解析到 SKU × 月。
> 切片：8 个床楔形枕头 SKU；主口径 `qty_daneey`（Daneey 仓族），敏感性口径 `qty_all`。
> 只读；原始数据与汇总数据见 `data/wedge_{raw,monthly}.csv`（不入库），
> 逐 SKU-月数量状态见本地生成的 `data_status.json`（含数量，不入库）；汇总计数见本文。

## 1. 结论先行

1. **R01 修正后，测试期数字未变，独立性问题已消除**：验证目标月 2025-01..2025-07，
   测试目标月 2025-08..2026-05，交集为空；验证最晚目标可用时点 2025-08-01 ≤
   最早测试决策时点 2025-08-01，`label_overlap_check.pass=true`。
2. **held-out 测试期（2025-07→2026-02，60 个 SKU-原点）**：TSB 0.511、ens5 0.520、naive 0.602；
   TSB 比 naive 低 15.1%，ens5 低 13.6%。另两种口径同样达标（`qty_all` ens5 0.416 vs 0.497；
   `qty_daneey/raw` TSB 0.503 vs 0.601）。
3. **验证期改选 Croston（主口径）后，测试期仍只有 0.530**，差于 TSB（0.511）与 ens5（0.520）；
   `qty_all` 口径选 MA3，测试 0.488，远差于 ens5 0.416。**选择规则依旧不可外推**。
4. **验证样本变小**：切到 2024-12..2025-04 后，有效样本 5 个 origin / 34 个 SKU-原点
   （原 7 个 origin / 50 个），选择噪声更大，不能据此宣称任何单一模型最优。
5. **R02 数据质量闸门已实现但未被触发**：43 张月表 `bad_qty=0`、`bad_date=0`、
   `empty_date=0`、列长度不一致=0；`bad_data` SKU-月为 0。闸门存在，但没有真实坏行可验证其效果。
6. **诚实结论**：仍支持「简单统计组合显著优于 naive」，不支持「存在稳定最优模型」，
   也不支持「验证期选单一模型可直接上线」。ens5/TSB 可作候选，naive 必须保留为守门。

## 2. R01/R02 修正记录

| Review 项 | 处理方式 | 证据 / 位置 |
|---|---|---|
| R01 标签重叠 / 不可知 | 新增 `--label-lag`（默认 1）：月 m 标签在 m+lag 的 1 日可用；origin t 决策时点 = t+lag | `backtest.py:label_available_month()` / `decision_at()` |
| R01 验证目标晚于测试决策 | 验证 origin 收紧为 2024-12..2025-04（目标 2025-01..07）；规则 `val_end ≤ test_start − H`，越界自动钳制 | `design.split_rule` / `split_adjustment` |
| R01 缺重叠检查 | 结果 JSON 新增 `label_overlap_check`：两侧目标月、交集、验证最晚可用时点、测试最早决策时点、pass | 三份结果 JSON 均 `pass=true`，交集 `[]` |
| R01 评分用了不可知标签 | 只评 `m+label_lag ≤ 拉取时点` 的目标月；h 仍为 3，不足只评可用部分 | 本次所有单元 `n_scored_h=3`；`scored_h_hist` 记录 |
| R01 TSB 初始化 | 文档化 z0=非零占比、d0=非零均值（全训练历史），零需求 d 不变；新增 golden 自测；**不声称新 bug** | `tsb()` docstring；`--self-test` 4 例全 PASS |
| R02 非法数量转 0 | 行保留，`qty` 留空，`qty_status=bad`，`qty_reason` ∈ {empty, non_numeric, negative, non_finite, non_integer_pieces}；逐月计数 | `pull_data.py:parse_qty()`；`pull_log.txt` 的 `bad_qty/bad_reasons` |
| R02 列长度静默 zip | 取最大长度、短列补 `""` 后对齐；记录 `col_mismatch` 与各列长度 | `pull_data.py:align_columns()`；本次 mismatch=0 |
| R02 无法核对读取完整性 | 逐月记录 `source_rows`（含表头）/`extracted_rows`/`blank_tail` | `pull_log.txt`；43 月 source=390,763、extracted=390,718（差 43 表头 + 2 表尾空行） |
| R02 坏行不得当 0 | `backtest.py` 跳过 bad/空 qty，构建 `bad_rows`；任一坏行 → SKU-月 `bad_data`，训练/评估都剔除 | `load_raw()` / `measure_status()`；本次 0 坏行 |
| R02 数据质量落盘 | `data_status.json` 与结果 JSON 均写入 `data_quality`（坏行数、SKU-月、逐月计数、完整性 caveat） | `data_quality` 段；`gate_exercised=false` |
| R02 完整性表述 | 明确「月表读取成功 ≠ 跨月发货行完整」，逐月计数仅供人工核对，不声称数据完整 | `data_quality.completeness_caveat`；本文 §6 |

## 3. 数据状态与回测设计

| 项 | 设置 |
|---|---|
| SKU | 2870/2871/2876/2877/2878/2879/2880/2881 |
| 月表范围 | 2023-01 → 2026-07（43 张，全部拉取成功） |
| 状态（qty_all） | observed 264、zero_confirmed 26、pre_launch 54、missing 0、bad_data 0 |
| 状态（qty_daneey） | observed 239、zero_confirmed 51、pre_launch 54、missing 0、bad_data 0 |
| 上市月 | 2870/2876/2877=2023-07；2871/2879/2880/2881=2023-08；2878=2023-09 |
| 滚动原点 | 2024-06 → 2026-02，共 21 个；h=3 |
| label lag | 1 个月；决策时点 = origin+1（1 日），标签可用时点 = 月份+1（1 日） |
| 最小训练 | ≥18 个已确认月（observed+zero_confirmed，剔除 missing/bad_data/pre_launch/删失） |
| 验证期 | 2024-12 → 2025-04（5 个 origin，34 个 SKU-原点，442 格/方法） |
| 测试期 | 2025-07 → 2026-02（8 个 origin；删失后 60 个 SKU-原点，780 格/方法） |
| 断货删失 | 2880：2026-03/04/05；2878：2026-06/07；2876：2026-05（censored 模式） |

**标签可知性（R01）**：以默认 label_lag=1 为例，2025-07 的销量在 2025-08-01 才可用。
验证期最晚 origin 2025-04 的目标是 2025-05..07，最晚 2025-08-01 可用；
测试期最早 origin 2025-07 的决策时点也是 2025-08-01。因此验证期选择所依赖的标签，
在最开始做测试决策时已经全部可知，且两侧目标月没有交集。结果 JSON 的
`label_overlap_check` 记录并断言这两点；本次 `pass=true`、`intersection=[]`。

**数据质量（R02）**：`qty_status=bad` 的行不会转 0；若某 SKU-月存在任何坏行，
该月标记 `bad_data`，既不进训练也不参与评估。本次 43 张月表全部干净（bad_qty=0），
因此该项只验证了代码路径，未验证真实坏行的处理效果。

**分类口径**：2023-01–06 所有 SKU 尚未上市，记为 `pre_launch`——这是「确认没有可发需求」，
不是 missing，也不等同于正常需求期的 0，因此训练时剔除。上市后月表成功拉取但该口径为 0 的月份才是
`zero_confirmed`。`missing` 用于月表打不开/读取失败/缺列；`bad_data` 用于存在非法数量行。

**方法**：naive、seasonal_naive、MA3/6/12、M1（=MA12）、M2、M3、M3b、
Croston（经典：仅非零期更新规模与间隔，间隔含零需求月、不含 missing）、TSB（α=0.3）、
`ens3=median(MA6,Croston,TSB)`、`ens5=median(MA3,MA6,MA12,Croston,TSB)`。

**TSB 初始化与 golden**：`z0 = 非零期数 / 已确认期数`，`d0 = 非零需求量均值`（全训练历史）；
非零期 `z=α+(1−α)z, d=αv+(1−α)d`，零需求期只 `z=(1−α)z`、d 不变；预测 `z·d`。
`uv run python backtest.py --self-test` 输出：
`[0,5,0,10]→4.38046125`、`[3]→3.0`、`[0,0]→0.0`、Croston `[0,5,0,10]→3.25`，4/4 PASS。

## 4. 结果

### 4.1 验证期（用于选方法，qty_daneey/censored，34 个 SKU-原点）

| 方法 | WAPE | Bias | 方法 | WAPE | Bias |
|---|---:|---:|---|---:|---:|
| **Croston（选中）** | **0.448** | −0.271 | MA6 | 0.471 | −0.301 |
| MA3 | 0.453 | −0.201 | MA12 / M1 | 0.502 | −0.341 |
| **ens5** | **0.463** | −0.277 | seasonal naive | 0.511 | −0.364 |
| ens3 | 0.463 | −0.276 | M3 | 0.513 | −0.215 |
| TSB | 0.468 | −0.266 | M3b | 0.515 | −0.368 |
|  |  |  | M2 | 0.616 | −0.000 |
|  |  |  | naive | 0.638 | −0.089 |

2026-10-20 更新：切分收紧后验证期只剩 5 个 origin / 34 个 SKU-原点，选择的是 Croston；
上一版 7 个 origin / 50 个样本时选的是 MA3。**有效样本减少，选择更不稳定。**

### 4.2 测试期（held-out，qty_daneey/censored，60 个 SKU-原点）

| 方法 | WAPE | Bias | 相对 naive |
|---|---:|---:|---:|
| **TSB** | **0.511** | −0.029 | −15.1% |
| MA12 / M1 | 0.518 | −0.053 | −14.0% |
| **ens5** | **0.520** | −0.014 | **−13.6%** |
| Croston（验证期选中） | 0.530 | +0.002 | −12.0% |
| MA6 | 0.565 | +0.025 | −6.1% |
| MA3 | 0.575 | −0.032 | −4.5% |
| naive | 0.602 | −0.086 | — |

测试期 oracle 最佳单方法为 TSB；ens5 与其只差 0.009。验证期选中的 Croston 测试 0.530，
仍差于 ens5——**选择规则在独立测试集上没有通过**。

### 4.3 三口径/模式重跑（测试期）

| 口径 / 模式 | 测试最佳 | WAPE | naive | ens5 | 选中方法（验证期） | 选中方法测试 WAPE |
|---|---|---:|---:|---:|---|---:|
| qty_daneey / censored | TSB | 0.511 | 0.602 | 0.520 | Croston | 0.530 |
| qty_all / censored | ens5 | 0.416 | 0.497 | 0.416 | MA3 | 0.488 |
| qty_daneey / raw | TSB | 0.503 | 0.601 | 0.507 | Croston | 0.511 |

三种口径下，验证期选中的方法在测试期都不如 ens5（qty_daneey 两模式差 0.010，
qty_all 差 0.072）。测试期 ens5 相对 naive 分别改善 13.6% / 16.3% / 15.6%。

### 4.4 修正前后对照

| 版本 | 验证切分 | 验证样本 | 测试样本 | ens5（test） | naive（test） |
|---|---|---|---:|---:|---:|
| R01 前 | 2024-12→2025-06 | 50 SKU-原点 | 60 | 0.520 | 0.602 |
| R01/R02 后 | 2024-12→2025-04 | 34 SKU-原点 | 60 | 0.520 | 0.602 |

测试期单元未变（目标月不重叠后，测试起点仍为 2025-07），因此测试数字相同；
变化在验证期有效样本与选中方法（MA3 → Croston/MA3）。旧的「验证选 MA3」结论作废，
新结论是「验证选 Croston（主口径）/ MA3（qty_all），测试仍不如 ens5」。

### 4.5 分 SKU（测试期 qty_daneey/censored）

| SKU | naive | MA3 | Croston | TSB | ens5 | 说明 |
|---|---:|---:|---:|---:|---:|---|
| 2870 | 1.000 | 0.726 | 0.562 | 0.560 | **0.525** | 低量，组合/TSB 明显好 |
| 2871 | **0.739** | 0.957 | 0.852 | 0.908 | 0.889 | naive 最好 |
| 2876 | **1.230** | 1.378 | 1.312 | 1.125 | 1.213 | 低量噪声大 |
| 2877 | **1.267** | 1.500 | 1.306 | 1.204 | 1.287 | 低量噪声大 |
| 2878 | 0.469 | 0.383 | 0.371 | 0.368 | **0.366** | 组合略优 |
| 2879 | 0.596 | 0.566 | 0.438 | 0.454 | **0.439** | TSB/组合好 |
| 2880 | **0.162** | 0.279 | 0.288 | 0.286 | 0.288 | 高销量，naive 反而最好 |
| 2881 | 0.439 | **0.299** | 0.319 | 0.318 | 0.326 | MA3 最好 |

## 5. Pass / Falsify

| 判据 | 结果 | 判定 |
|---|---|---|
| 验证/测试目标月零重叠，验证标签在测试决策时可知 | 交集空；2025-08-01 ≤ 2025-08-01 | **PASS** |
| 最佳方法测试期 WAPE 比 naive 低 ≥10% | TSB/ens5 三种口径均达标（−15.1%…−16.3%） | **PASS** |
| 验证期选择规则可外推 | 选中 Croston/MA3，测试期均差于 ens5 | **FAIL** |
| 存在一个稳定的单一最优模型 | 验证选 Croston，测试 TSB/ens5 更优；分 SKU 各有赢家 | **FAIL** |
| 非法数量不被当 0，坏 SKU-月被剔除 | 代码路径已实现；本次 0 坏行，闸门未被真实触发 | **未验证**（不是 PASS） |
| TSB 初始化与 golden 一致 | 4/4 自测通过 | **PASS** |

## 6. 限制

1. **验证样本进一步变小**：34 个 SKU-原点、5 个 origin，选择噪声大；本轮不能证明任何单一模型长期最优。
2. **标签可用性假设**：默认 label_lag=1，即月表在次月 1 日完整可用；若实际取数更晚，
   应增大 `--label-lag` 重跑。切分只检查「目标月不重叠」与「验证标签在测试决策前可用」。
3. **坏行闸门未被触发**：本次 43 张月表 `bad_qty=0`、`bad_data` SKU-月=0；
   非法数量与列长度不一致的处理路径只做了代码层面验证。
4. **完整性未证明**：逐月 `source_rows/extracted_rows` 只能证明当月表被完整读取
   （43 月 source 390,763 行、extracted 390,718 行，差值为 43 个表头 + 2023-04 的 2 个表尾空行）；
   不能证明跨月发货行都存在。
5. 只有 8 个 SKU、测试期 60 个 SKU-原点；结论不能直接外推到全品类。
6. 2026 年之前的断货窗口没有三源标签，未删失，可能低估历史需求；2026 年断货月已删失。
7. `qty_daneey` 仍包含 `FZH-DANEEY-半成品仓/皮壳仓库/退货产品仓` 的少量发货（全部 8 SKU 合计约 19 件），
   口径未在本轮改动，属既有定义。
8. 销量用发货量代理需求；PO 下单量、平台结算口径不同。无促销/节假日/价格特征；
   未测 TSFM/LightGBM；未做显著性检验。

## 7. 复现

```bash
cd docs/research/supply-chain/2026-10-20/claude/experiments/e1_forecast
uv run python pull_data.py            # 只读拉取（需父仓库 secrets）
uv run python backtest.py --self-test
uv run python backtest.py --measure qty_daneey --mode censored
uv run python backtest.py --measure qty_all    --mode censored
uv run python backtest.py --measure qty_daneey --mode raw
```

可选参数：`--min-train 18`、`--label-lag 1`、`--val-start/--val-end`、
`--test-start/--test-end`、`--data-end`。输出 `results_<measure>_<mode>.json`
（含 `label_overlap_check` / `data_quality` / `self_test` / validation/test/combined 与丢弃清单）
和本地 `data_status.json`（不入库）。

## 8. 对 V1 的建议

- 预测器：保留 **naive 守门**；候选用 **TSB** 或 **ens5**（测试期两者只差 0.009，
  ens5 对单方法失误更稳）。不要用验证期「选一个最优单方法」直接上线：
  本轮选 Croston/MA3 在三种口径下都跑输 ens5。
- 若要做选择，至少用 expanding-origin、只依赖决策时点前已知的标签（本轮的 label_lag 机制），
  并设最小样本；当前 34 个验证 SKU-原点仍太少。
- 偏差：测试期 ens5 bias −1.4%，验证期 −27.7%；需持续监控。
- 推进顺序：先把滚动回测、缺失/bad_data 状态、标签可用时点和数据完整性审计做扎实，
  再考虑深度模型/TSFM。
