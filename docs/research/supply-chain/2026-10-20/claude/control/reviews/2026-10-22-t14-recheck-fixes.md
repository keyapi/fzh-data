---
okf: v0.1
type: Review
title: T14 复审修正记录（M01 共同切点 / M02 抽样母集 / M03 零需求评分）
date: 2026-10-22
owner: claude-worker
status: 完成；离线只读修正，未改主表与 T2 选模
artifacts:
  - experiments/business_phase/forecast_eval/attribute_errors.py
  - experiments/business_phase/forecast_eval/error_attribution.csv
  - experiments/business_phase/forecast_eval/error_attribution.json
  - experiments/business_phase/forecast_eval/attribution_report.md
  - experiments/business_phase/forecast_eval/nested_eval.py
  - experiments/business_phase/forecast_eval/nested_eval.csv
  - experiments/business_phase/forecast_eval/nested_eval.json
  - experiments/business_phase/forecast_eval/nested_report.md
  - experiments/business_phase/forecast_eval/forward_shadow.py
  - out/business_phase/summary_v3.md
---

# T14 复审修正记录

> 按 #301 T12-RECHECK 的三项 major（M01–M03）修正，只改三个脚本、其产物/报告、
> `summary_v3.md` 与新增本记录。**未动主表 `replenishment_v2.csv`**，未动
> T3–T6/T11/T13 产物与 V1 冻结产物，未动 `control/` 下 HANDOFF/state/DECISIONS/
> NIGHT_PLAN/CONTROL/RESEARCH_ADOPTION。DB 只读（脚本前后 sha256 自检）。

## 1. M01 — 共同子集不是共同切点

**问题**：旧版按方法各自累计误差（`per[m].append(...)`），再按“五方法都有均值”过滤 SKU。
某方法在 3 个切点中只有 2 个可行时，它的均值来自 2 个窗口，而普通方法来自 3 个窗口——
比较的不是同一批切点。三个反例（`CENPTQiRuoJinLan-100/-153/-194`）的 peer 可用性为
否/是/是。

**修复**：`attribute_errors.py:398` 改为 `per[method][origin] = abs_error`；
`:442-450` **先取五方法共同 origin 的交集**（`common_o`），`:456` 只在 `common_o` 上求均值。
JSON/报告同时给出各自窗口数（上下文）与比对窗口数（正式口径）。

**证据（重生成后）**：

| SKU | 各自窗口 naive/ses/tsb/combo2/借力 | **比对窗口** | 是否相同 |
|---|---|---:|---|
| `CENPTQiRuoJinLan-100` | 3/3/3/3/**2** | **2** | ✅ |
| `CENPTQiRuoJinLan-153` | 3/3/3/3/**2** | **2** | ✅ |
| `CENPTQiRuoJinLan-194` | 3/3/3/3/**2** | **2** | ✅ |

- `short_history.alignment.recheck_all_windows_equal = true`；五方法共同窗口总数均为
  **446**（`aligned_window_total`），证明聚合窗口完全一致。
- 旧版存在各自窗口数不一致的序列 **244 条**（`own_window_mismatch_skus`），现仅影响
  “各自子集”这一上下文列，不再进入正式比较。
- 重算后**正式共同子集 MAE**（n=151）：

| 方法 | T12 旧值 | **T14 修正后** |
|---|---:|---:|
| naive | 14.275 | **14.299** |
| ses | 12.662 | **12.694** |
| tsb | 12.030 | **12.063** |
| combo2 | 12.756 | **12.786** |
| category_borrowed | 13.118 | **13.118** |

排序不变（tsb < ses < combo2 < 类目借力 < naive）；低置信 139/392、对齐 21/151 不变。

## 2. M02 — 抽样母集前视

**问题**：`series` 用截至 2026-09 的全集构造，所有键一起排序抽样；2025-10 块样本里有
**28 个**、2026-01 块样本里有 **11 个** SKU 当时尚无首单（`first > 块起点`），等于用未来
才出现的序列回填早期样本。

**修复**：`nested_eval.py:205-228` 每个外层块先取
`mother = [s for s in series if series[s]["first"] <= O]`，再在母集内排名、算步长、抽样；
同时记录母集大小、被剔除的未首单数、样本内最晚首单、以及**旧规则样本中当时未首单的数量**
与新旧样本差异，便于复核。

**证据（重生成后）**：

| 块 | 母集 | 剔除未首单 | 样本首单 ≤ 块起点 | 样本内最晚首单 | 旧规则样本中未首单 | 新旧样本差异 |
|---|---:|---:|---|---:|---:|---:|
| 2025-10 | 1,027 | 210 | ✅ | 2025-09 | **28** | 332 |
| 2026-01 | 1,134 | 103 | ✅ | 2025-12 | **11** | 332 |
| 2026-06 | 1,206 | 31 | ✅ | 2026-06 | 0 | 0 |

- 旧规则计数 **28 / 11** 与复审给出的反例完全一致。
- 早期块样本变化后，块内指标随之重算（块间仍不可比）：

| 外层块 | 选择流程 | MA3 | naive | 有效/共同可评 | 零需求保留 |
|---|---:|---:|---:|---:|---:|
| 2025-10（T12 旧） | 0.4630 | 0.5312 | 0.4823 | 172/170 | 22 |
| **2025-10（T14）** | **0.7210** | **0.7408** | **0.5918** | 200/197 | 21 |
| 2026-01（T12 旧） | 0.7722 | 0.7713 | 0.5779 | 181/176 | 26 |
| **2026-01（T14）** | **0.6515** | **0.6711** | **0.5553** | 200/192 | 25 |
| 2026-06（两版相同） | 0.5255 | 0.4978 | 0.5016 | 198/197 | 22 |

- 最后一个可评估块（2026-07..09）**数字未变**：该块旧样本中未首单 SKU = 0，新旧样本一致
  （差异 0），因此 `summary_v3 §6` 的主结论与 bootstrap 不变：
  选择流程 − MA3 均值 **+0.0346**、5–95% **[−0.1052, +0.1672]**；
  选择流程 − naive **+0.0294**、**[−0.1114, +0.1654]**（仍跨 0）。
- 内层选模分布更新为 naive 136 / ma6 103 / seasonal_naive 99 / autoets 92 / ma3 89 /
  combo_ew 79；拟合次数 9,820 → 10,688（上限 14,400）。

## 3. M03 — 前向评分漏掉零需求

**问题**：`forward_shadow.py` 评分只遍历“预存预测 ∩ 目标窗有订单记录”的 SKU，
目标窗无订单的 SKU 被静默跳过；它们的预测误差既不进分子也不进分母。

**修复**：`forward_shadow.py:285-370` 抽出 `build_score()`：

- **母集 = 预存样本** `sample.skus`（`:354`），不按目标窗订单记录收缩；
- 标签覆盖完整时，无订单 = **零需求**，`actual=0.0`（`:315`），`|F|` 进入 WAPE 分子；
- 覆盖率检查按目标月逐个确认（`:303`）：任一目标月无标签 → 整窗 `labels_incomplete`，
  逐 SKU 写入排除原因（`:303-305`），绝不静默消失；
- 聚合总实际量为 0 时 `status=undefined_denominator`，不参与计算；
- 记录 `n_sample / n_scored / n_zero_demand_retained / n_excluded / excluded` 与
  `mother_set`，评分子集完全可追溯。

**合成反例（`--mode selftest`，不读 DB、不落文件）**：

```text
预存 A=15（目标窗无订单）   B=100（实际 100）
selected WAPE（保留零需求）= (15 + 0) / 100 = 0.15
若剔除零需求            = 0.00
```

实际输出：`status=scored, denominator=100.0, wape_with_zero=0.15,
wape_excluding_zero=0.0, zero_demand_retained=1,
labels_incomplete_status=labels_incomplete`。断言在脚本内，失败即中止。

**真实链路冒烟**（系统临时目录，跑完删除）：`--data-cutoff 2026-02`
→ presave 200 条；score 结果 `n_sample=200, n_scored=199, n_zero_demand_retained=25,
n_excluded=1`（原因 `incomplete_forecast:ma3`），WAPE selected/naive/MA3 =
0.5252/0.4494/0.6297。25 个零需求 SKU 在旧版会被整批丢弃，现在全部进入分子。

## 4. 修正后指标汇总（可见数）

| 项 | 值 |
|---|---|
| T9 正式共同子集 | n=151，五方法共用 **446** 个 (SKU, origin) 窗口 |
| T9 正式共同子集 MAE | TSB 12.063 / SES 12.694 / 组合 12.786 / 类目借力 13.118 / naive 14.299 |
| T9 反例比对窗口 | 100=2、153=2、194=2（全相同） |
| T10 三块样本首单约束 | 全部 `first <= 块起点`；旧规则混入 28 / 11 / 0 条 |
| T10 最后可评估块 | 选择流程 0.5255 / MA3 0.4978 / naive 0.5016 |
| T10 bootstrap | MA3 +0.0346 [−0.1052,+0.1672]；naive +0.0294 [−0.1114,+0.1654] |
| M03 合成反例 | 保留零需求 0.15，剔除 0.0 |

## 5. 复现

```bash
# T9（约 140 s，只读 DB，前后 sha256 自检）
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/attribute_errors.py

# T10（约 37 s）
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/nested_eval.py

# M03 合成反例（不读 DB）
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/forward_shadow.py --mode selftest

uv run python scripts/check_secrets.py   # 无 finding、退出码 0（成功时打印一行 OK）
```

## 6. 残留与边界

1. `control/reviews/2026-10-22-t12-audit-fixes.md` 中 M01 相关的对齐 MAE 与 M02 相关的
   早期块指标已被本记录取代（该文件不在本次 ownership 内，未修改）。
2. `forward_shadow_plan.md`（T13 已对齐零分母口径）未改；其评分母集细节以
   `forward_shadow.py` 的 `mother_set` 字段为准。
3. 主表 `replenishment_v2.csv` 未改；AutoETS 默认仍只是裁定 A 的规则默认，模型选择未定。
4. 根索引 `index.md` 未同步（本次 ownership 仅限上述文件；索引在本次之前已落后于多篇
   T 系列记录）。

## 7. 约束自检

| 约束 | 结果 |
|---|---|
| 只本地离线、DB 只读 | ✅ 两脚本 read_only + 前后 sha256 |
| 未访问生产、未扩样、未下单、未删数据、未合并 PR | ✅ |
| 未改主表 CSV、T3–T6/T11/T13 与 V1 冻结产物 | ✅（提交仅本记录列出的文件） |
| 未改 control 下 HANDOFF/state/DECISIONS/NIGHT_PLAN/CONTROL/RESEARCH_ADOPTION | ✅ |
| 禁止 `git add -A`；只提交自己改动文件；不 push | ✅ 显式列文件 |
| 未提交原始明细与凭证 | ✅ |
| `check_secrets.py` 无 finding | ✅ |
| 不留临时文件 | ✅ 冒烟目录与 `__pycache__` 已删除 |
