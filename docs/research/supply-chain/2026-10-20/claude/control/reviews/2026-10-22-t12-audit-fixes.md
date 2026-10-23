---
okf: v0.1
type: Review
title: T12 审核修正记录（T9 四项 + T10 四项）
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

# T12 审核修正记录

> 按 #301 对 T9/T10 的 FAIL 逐条修正：只改两个脚本、其产物/报告、`summary_v3.md`
> 与新增本记录。**未动主表 `replenishment_v2.csv`**，未动 T3/T4/T5/T6/T11 与 V1
> 冻结产物，未动 `control/` 下 HANDOFF/state/DECISIONS/NIGHT_PLAN/CONTROL/RESEARCH_ADOPTION。
> 数据源 `order_store.duckdb` 只读（脚本前后 sha256 自检）。

## 1. T9 四项

| # | 审核问题 | 修正 | 证据（文件:行） | 修正后数字 |
|---|---|---|---|---|
| T9-1 | 仓库别名误标：`series_kind` 用原始仓库名判定 | 先按 `warehouse_map` 归一，再判定单仓/多仓 | `attribute_errors.py:125`（读 map）、`:144-145`（按映射计数）、`:197-203`（判定） | 原始 26 名 → 映射后 17 名；**518 条序列**由“多仓”改判“单仓”；CSV 行数 `warehouse_level_true` 1,104 → **4,985**、`multi_warehouse_true_sum` 7,912 → **4,031**、proxy 0 |
| T9-2 | 销量占比口径不一致：正文称“近 6 个月”，计算用全历史 | 全表统一为**全历史（首单月..2026-09）**，并在 JSON/报告显式写口径；所有“销量占比/覆盖”同源 | `attribute_errors.py:61-62`（`SALES_CALIBER`）、`:495`（写入 JSON）、`:546`（报告口径行）、`:557-564`（fallback 同一口径） | 分母 346,086；fallback 销量覆盖 **0.10%**（旧文本写“6 个月覆盖”，数值本身即全历史） |
| T9-3 | 短历史类目借力泄漏：peer 形状用截至 2026-09 的最后 12 个月 | peer 必须**在该切点**已有 ≥24 个月历史，形状只取**截至该切点**的 12 个月；按日历年月映射 | `attribute_errors.py:355-383`（`borrowed_shape`，切点截断）、`:424`（逐切点调用） | 有 peer 的序列 158 → **151**；类目借力自己子集 MAE 14.002 → **13.118** |
| T9-4 | 子集不一致：158 与 392 并列比较；训练下限口径 2/3 个月混写 | 各自可行子集只作上下文，正式比较用**对齐的共同可评分子集**；训练下限显式取 **3 个月**（放宽到 2 个月为 403，不采用） | `attribute_errors.py:58`（常量）、`:390`、`:396`（下限）、`:443-447`（对齐子集）、`:460-472`（`alignment` 全量说明）、`:590-601`（报告双列表） | 可评估 **392**（2 个月则 403）；对齐子集 **151**；低置信 **139/392**（对齐 21/151） |

**T9 修正后可评数字（对齐子集 n=151，MAE）**：
TSB **12.03** < SES **12.662** < 组合 **12.756** < 类目借力 **13.118** < naive **14.275**。
各自子集列仍给出（naive 10.272 / SES 9.591 / TSB 9.692 / 组合 9.593），但**不可横向比较**。
因此旧报告“类目借力误差更高（14.0 vs naive 10.3）”的并列结论**作废**：在可比子集上它优于
naive、劣于 TSB/SES。反转分解（0.1181 / 0.0045）与 fallback 计数（112 行 / 71 SKU）不变。

## 2. T10 四项

| # | 审核问题 | 修正 | 证据（文件:行） | 修正后数字 |
|---|---|---|---|---|
| T10-1 | 最终块泄漏：抽样 / tier / 主仓用了截至 2026-09 的总销量或最终块实际值 | 三者一律只用**各自外层训练窗**：抽样按 `first..origin` 总销量；tier 按训练窗 `train_total`；主仓按训练窗内各仓销量 | `nested_eval.py:140-157`（训练窗助手）、`:197-203`（每块独立抽样）、`:257`/`:279`（主仓）、`:338-349`（tier） | 三块样本与首块重合 200 / **32** / **41** 条（旧版三块共用同一批 200）；CSV 新增 `train_total`、`tier` 列；主仓分层变为 美东 54 / 美中 60 / 波兰 83 / 休斯顿 1（旧 67/58/71/2） |
| T10-2 | “未使用块”不成立：T2 的 2026-03 切点 90 天目标窗已到 2026-07 | 块性质改名 `last_evaluable_no_clean_holdout`；报告/JSON 明写“当前标签覆盖内**不存在干净留出块**，唯一干净证据来自前向影子” | `nested_eval.py:63-64`（块标签）、`:392-398`（`rules.r6_final` 事实说明）、`nested_report.md`（“它不是干净留出块”段） | 仍评估 2026-07..09，但不再称“未使用/干净留出” |
| T10-3 | 零需求误差被删除（既不计分子也不计分母） | WAPE 分子**保留**零需求单元格的 `|F|`，分母对零需求贡献 0；三种方法在同一共同可评分子集上比较 | `nested_eval.py:305-317`（`common_rows` + `wape`）、`:319-327`（`block_stats` 单列 `zero_retained`）、`:362-371`（bootstrap 同样保留）、`:383-393`（`metric_definition`） | 见 §3；旧样本复现审计参考值 0.4961 / 0.5637 / 0.4458，bootstrap 仍跨 0 |
| T10-4 | 缺失预测写 0（17 条受影响，如旧 CSV 第 65 行） | 缺失预测写 **null**（CSV 为空），并明确共同可评分子集 | `nested_eval.py:287-289`（null）、`:387`（共同子集定义写入 JSON）、`:415-419`（每块 n_common / 缺失数） | 新样本 valid 缺失 2 / 5 / 1 条（合计 8），加 49 条无历史行，CSV 空值共 57；旧第 65 行 `TT0312678K0064345`（n_train=2）当时写 `0`，现同规则写空 |

### 2.1 前向影子脚本（参数化）

新增 `experiments/business_phase/forecast_eval/forward_shadow.py`：

| 要求 | 落实 | 证据 |
|---|---|---|
| 不写死截止期/外层切点 | `--data-cutoff` 默认取 DB 最大月份；`--origin` 默认 = cutoff；目标月、评分日（目标末月次月 4 日）都由参数推导 | `forward_shadow.py:70-72`、`:144-152`、`:231` |
| 执行前保存样本 | `sample.skus` 含 SKU、训练窗月数、训练窗总量；抽样规则写死为“仅训练窗排序” | `:236-242` |
| 保存选模结果 | `selection` 每 SKU 一条理由（内层 mean\|err\|/A） | `:196-210`、`:243` |
| 保存预测 | 每 SKU 各候选逐月预测 + `selected` | `:220-222`、`:243` |
| 保存生成时间 | `generated_at`（带时区 ISO） | `:227` |
| 不可覆盖（预注册） | 已存在则拒绝，除非显式 `--force` | `:264-268` |
| 标签可用后评分、不重选 | `--mode score` 要求 DB 已覆盖目标末月，直接读预存预测；共同子集、零需求保留、300 次 SKU 重抽 | `:275-355` |

**冒烟测试**（在系统临时目录、跑完即删，未留在仓库）：`--data-cutoff 2026-02
--origin 2026-02` → targets 2026-03..05、`scoring_due 2026-06-04`；随后 score
得到 n=175、零需求 1、WAPE selected 0.5069 / naive 0.4426 / MA3 0.614。
该组数字只是脚本连通性验证，**不是证据**，已删除临时产物。

## 3. 修正后指标与对账

### 3.1 最后一个可评估块（2026-07..09，非干净留出）

| 口径 | 选择流程 | MA3 | naive | 共同可评 | 零需求保留 |
|---|---:|---:|---:|---:|---:|
| **修正后（每块独立抽样）** | **0.5255** | **0.4978** | **0.5016** | 197 | 22 |
| 旧样本上仅修零需求口径（对账用） | 0.4961 | 0.5637 | 0.4458 | 198 | 25 |

- 审计给出的参考值 **0.4961 / 0.5637 / 0.4458** 可在旧 200 序列样本上**精确复现**
  （命令见 §5），证明零需求口径已按要求改对。
- 但由于 T10-1 同时修正了抽样泄漏，全流程重跑的样本不同，正式数字取**修正后**一行。
  两行不可混用；`summary_v3.md §6` 只用修正后数字。

### 3.2 不确定性（300 次 SKU 重抽）

| 样本 | 选择流程 − MA3 | 选择流程 − naive |
|---|---|---|
| **修正后** | 均值 +0.0346，5–95% **[−0.1052, +0.1672]** | 均值 +0.0294，5–95% **[−0.1114, +0.1654]** |
| 旧样本·仅修零需求 | −0.0646，[−0.2019, +0.0468] | +0.0528，[−0.0671, +0.1604] |

**两种口径下区间都跨 0**，方向不稳定；不构成任何方向的证据。

### 3.3 其它修正后数字

- 内层选模分布：naive 146 / seasonal_naive 91 / autoets 87 / ma6 85 / ma3 76 / combo_ew 66。
- 失败保留：`seasonal_naive:ValueError` 318、`autoets:NotImplementedError` 131、
  `outer:insufficient_history` 49、`outer:autoets:NotImplementedError` 45、
  `autoets:ValueError` 25、`autoets:KeyError` 2。
- 计算：9,820 次拟合（上限 14,400）、32.5 s、峰值 130 MB。

## 4. 措辞核对

| 检查 | 结果 |
|---|---|
| 不再把 2026-07..09 称“未使用块” | ✅ 键名改为 `last_evaluable_no_clean_holdout`；正文写“不存在干净留出块” |
| 不使用“改进/稳健/干净留出”作为结论 | ✅ 仅以否定句式出现（“不是干净留出块”“不使用…等说法”） |
| 明确模型选择仍未定 | ✅ `nested_report.md` 结论、`summary_v3.md §6` 末段 |
| summary 数字与正文一致 | ✅ 0.5255 / 0.4978 / 0.5016，区间与 §3.2 一致；短历史表与 T9 报告一致 |
| WAPE 定义写明“不是准确率/无通用阈值” | ✅ T9、T10 报告与 summary §6 |

## 5. 复现

```bash
# T9（约 140 s，只读 DB，前后 sha256 自检）
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/attribute_errors.py

# T10（约 33 s）
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/nested_eval.py

# 前向影子：预存（当前应拒绝覆盖已存在文件）与评分
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/forward_shadow.py --help

# 旧样本零需求口径复现（审计参考值 0.4961 / 0.5637 / 0.4458）
git show HEAD~1:docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/nested_eval.csv > /tmp/old_nested.csv
uv run python - <<'PY'
import csv
rows = [r for r in csv.DictReader(open("/tmp/old_nested.csv", encoding="utf-8-sig"))
        if r["outer"] == "2026-06" and r["valid"] == "True" and float(r["n_train"]) >= 3]
den = sum(float(r["actual"]) for r in rows)          # zero-demand rows add 0
for k in ("sel_forecast", "ma3_forecast", "naive_forecast"):
    print(k, round(sum(abs(float(r[k]) - float(r["actual"])) for r in rows) / den, 4))
PY

uv run python scripts/check_secrets.py   # 无 finding、退出码 0（成功时打印一行 OK）
```

## 6. 残留与边界

1. `out/business_phase/forward_shadow_plan.md`（T11 产物，本次**禁止修改**）§2 仍写
   “零分母单元格单列，不计入分母”，与新口径（零需求保留在分子）不一致。建议 T11
   下一次修订时同步改写；本次以脚本与 T10 报告为准。
2. `control/reviews/2026-10-22-t9-attribution.md`、`2026-10-22-t10-nested.md` 是被审记录，
   未修改；其中“158 条”“未使用块”“0.4629 / 0.4260 / 0.5253”等表述由本记录与
   重生成的报告取代。
3. 旧样本对账数字（0.4961 等）仅用于证明口径修正，**不得**引用为正式结果；
   两套样本不可混算。
4. 主表 `replenishment_v2.csv` 未改，主表所用 AutoETS 默认仍只是裁定 A 的规则默认。

## 7. 约束自检

| 约束 | 结果 |
|---|---|
| 只本地离线、DB 只读 | ✅ 两个脚本 connect(read_only=True) + 前后 sha256 |
| 未访问生产、未扩样、未下单、未删数据、未合并 PR | ✅ |
| 未改主表 CSV、T3/T4/T5/T6/T11 与 V1 冻结产物 | ✅（`git status` 仅本记录列出的文件） |
| 未改 control 下 HANDOFF/state/DECISIONS/NIGHT_PLAN/CONTROL/RESEARCH_ADOPTION | ✅（工作区里 HANDOFF/NIGHT_PLAN 的改动是本次之前已有的，未纳入提交） |
| 禁止 `git add -A`；只提交自己改动文件；不 push | ✅（显式列文件提交） |
| 未提交原始明细与凭证 | ✅ |
| `uv run python scripts/check_secrets.py` 通过（无 finding，退出码 0） | ✅ 输出仅 `OK: 扫了 N 个文件，没有明文凭证。` |
| 不留临时文件 | ✅ 冒烟测试目录已删除 |
