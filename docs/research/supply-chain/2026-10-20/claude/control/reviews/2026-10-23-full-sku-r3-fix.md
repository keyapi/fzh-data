---
okf: v0.1
type: Review
title: 全 SKU R3 窄返修：A 包归因 + 措辞边界 + 冻结 hash
date: 2026-10-23
owner: claude-worker
status: 完成；仅改文案/机器边界/新增冻结证据；数值未变；未 commit
artifacts:
  - out/business_phase/frozen_artifacts.json
  - experiments/business_phase/forecast_eval/full_sku_selfaudit.py（仅文案）
  - experiments/business_phase/forecast_eval/full_sku_routing.py（仅文案）
---

# R3 窄返修（M01 / N01 / N02 / N03）

> **数值未变**：未重跑 bootstrap、未重新训练；所有 WAPE / Bias / CI / 计数与返修前逐位一致
> （复算见文末「数值未变核验」）。本轮只改文案、机器可读边界字段，并新增冻结证据文件。
> 未 commit、未 push；未跑 `update_index.py`。

## M01（major）· A 包树模型差异归因

**改前**：`global_tree 的 −0.0002 是取整差`。
**改后**：`不是取整差，而是训练母集从 1,237 扩到 1,328 后全局模型重训造成的预测变化；同评分单元 ≠ 同预测模型`。

四处同步修改：

| # | 位置 | 改前 | 改后 |
|---|---|---|---|
| 1 | `full_sku_selfaudit.py:363` | 「取整差」 | 训练母集扩大导致重训预测变化 + 消融数字 |
| 2 | `out/business_phase/full_sku_selfaudit.md:79` | 同上 | 同上 |
| 3 | `control/reviews/2026-10-23-full-sku-selfaudit.md:80` | 同上 | 同上 |
| 4 | `out/business_phase/full_sku_selfaudit.json` → `a_consistency.note`（机器字段） | 「差异来自集合口径」 | 三处差异逐条 + 新增 `training_pool_ablation` 块 |

写进报告的 301 训练池消融证据：

| 实验（同算法/超参/切点/评分单元） | 树 WAPE |
|---|---|
| A 固定产物（`2b44cdbd`） | 0.49354508379541745 |
| 1,328 全母集训练，仅在 A 的 2,763 单元评分 | 0.49333642687199925 |
| 精确差 | −0.00020865692341820452 |
| 训练母集限回 A 的 1,237 mapped_eligible | 0.49354508379541745（精确恢复 A 值） |

未把两个全局树说成同一拟合模型；未改任何数值。

## N01（minor）· 分型时点措辞统一

**统一口径**：分型表 = **截至 2026-09 的现状描述（`as_of=2026-09`）**，对历史评估切点
**`not_point_in_time`**；规则本身可在训练窗内计算；该列只用于 C 边注、不参与评估。

| # | 位置 | 改前 | 改后 |
|---|---|---|---|
| 1 | `out/business_phase/full_sku_eval.json` → `boundaries[0]` | 「分型只用训练窗内特征」 | 现状描述 + as_of + not_point_in_time；另加 `classification_as_of` / `classification_point_in_time` |
| 2 | `full_sku_routing.py:270`（boundary 生成串） | 同上 | 同上 |
| 3 | `out/business_phase/full_sku_routing.md:75` | 「只描述训练窗内」 | 同上 |
| 4 | `control/reviews/2026-10-23-full-sku-routing.md:92` | 同上 | 同上 |

**C 边注措辞**（`full_sku_routing.py` + `final_bundle_routing.csv` 2,309 行 +
两份报告 + `full_sku_eval.json` / `full_sku_selfaudit.json` 的计数键）：

| 改前 | 改后 | 行数 |
|---|---|---:|
| 支持充足（本批已评分） | **曾进入本批评估（仅覆盖）** | 1,366 |
| 支持不足（未进入共同单元） | **未进入本批评估（未覆盖）** | 943 |

并在两份报告里明写：该标记只表示「曾进入共同评分单元」，**不是** SKU 级路由准确性、
供给证据或采购/效果证据。

## N02（minor）· 受控本地冻结证据

新增 `out/business_phase/frozen_artifacts.json`（只放 hash / 元数据，**不含行级数据**）：

| 产物 | 行数 | 列数 | sha256（前 16） |
|---|---:|---:|---|
| `full_sku_classification.csv` | 1,328 | 11 | `90afb1eda50a6793` |
| `final_bundle_routing.csv` | 2,309 | 36 | `65f28600d1f880e0` |

输入 manifest：

| 输入 | sha256（前 16） |
|---|---|
| `order_store.duckdb`（231 MB） | `0919dd8c852df51e` |
| `destinations.json` | `720b478809128156` |
| `final_bundle.csv`（C 产物，未改） | `3bb860a67f2be72e` |

复现命令也写进该 JSON。这样任何人可验证「本地这份 CSV 就是当时那份」，无需提交业务数据。

## N03（minor）· 「树 Bias 最接近 0」不实

**改前**（`control/reviews/2026-10-23-full-sku-routing.md:54`）：
「全局树在本批单元上 WAPE 最低、Bias 最接近 0」。

**改后**：`全局树 WAPE 最低（0.494）；Bias 最接近 0 的是 naive（+0.009），全局树为 −0.052。
WAPE 与 Bias 分开陈述，不构成「单一最优模型」或「多指标最优」的结论。`

## 数值未变核验

| 项 | 返修前 | 返修后 |
|---|---|---|
| full_sku_eval metrics WAPE | naive 0.6059 / ma3 0.6311 / tsb 0.5901 / seasonal_naive 0.5981 / combo 0.5237 / global_tree 0.4939 | **完全相同** |
| bootstrap Δ CI（combo） | [+0.0037, +0.0580] | **完全相同**（未重跑） |
| 计数闭合 | 2,820 + 3,820 = 6,640；1,366 + 943 = 2,309 | **完全相同** |
| C 原始列逐行 | — | 2,309 行、原始列逐行值 **完全一致**（只改了 `routing_support` 文案） |

## 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/full_sku_routing.py     # 如需重生成（数值不变）
uv run python scripts/check_secrets.py
```

未新增依赖；未跑 `update_index.py`；未 commit / push。

---

## R3-N04（301 复审唯一 minor）· 生成逻辑与已修 JSON 同步

**问题**：上一轮只改了固定产物 JSON，生成逻辑没同步——按 `frozen_artifacts.json` 的复现命令重跑会丢掉新增字段。

| # | 生成器 | 改前 | 改后 |
|---|---|---|---|
| 1 | `full_sku_routing.py` payload（原 `:259-274`） | 无分型时点字段 | 新增 `classification_as_of="2026-09"`、`classification_point_in_time=False` |
| 2 | `full_sku_selfaudit.py` payload（原 `:282-287`） | `note` 仍写「差异来自集合口径」；无消融块 | `note` 改为三处差异说明；新增 `training_pool_ablation`（A 产物 / 1,328 训练仅 A 单元评分 / 精确差 / 限回 1,237 恢复 / attribution） |

**验证方式（按要求重生成到临时路径比对，未动冻结产物）**：把两个生成器的 `OUT` 指向
`tempfile.mkdtemp()`（selfaudit 额外把 `final_bundle.csv` / `final_bundle_routing.csv`
复制进临时目录供读取），执行后与冻结 JSON 做结构比对：

| 比对项 | full_sku_eval.json | full_sku_selfaudit.json |
|---|---|---|
| 新增字段 | `classification_as_of` / `classification_point_in_time` **一致** | `note` / `training_pool_ablation` **一致** |
| 顶层键集合 | 无缺失、无多余 | 无缺失、无多余 |
| 数值块 | `metrics`、`reconciliation` **逐位一致** | `bootstrap.rows`、`reconciliation`、`verification`、`purity` **逐位一致** |
| 允许差异 | `elapsed_s`（7.1 s） | `elapsed_s`（6.7 vs 7.3 s） |

- **未重训模型语义、未改任何统计数值**：重生成结果与冻结 JSON 除 `elapsed_s` 外完全一致
  （`max_abs_delta` 仍为 0.0，bootstrap 2000 次的结果逐位相同）。
- 冻结产物（`full_sku_eval.json` / `full_sku_selfaudit.json` / 两份 CSV）**未被本轮写入**；
  验证输出只落在系统临时目录。
