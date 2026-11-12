---
okf: v0.1
type: Decision
title: 预测计划窗、服务分档、模型选择与春节 bridge 的 ADR
description: P0 决策记录：H_key 公式、98/154/161/91/112 标准桶、A/B/C/D 服务先验、rolling-origin 选择协议、adopted 单一事实源、春节 bridge 原则
tags: [forecast, planning-horizon, service-level, model-selection, cny, adr]
date: 2026-11-12
status: accepted
---

# 预测计划窗、服务分档、模型选择与春节 bridge 的 ADR

> 状态：**accepted（P0）**。适用范围：D5/D6 的预测与补货口径。本文只定规则，不改 D5/D6 代码。
> 依据：Codex + Claude 两份独立调研及合并稿
> `D:/Work/fzh-order-store/analysis/FORECAST_RESEARCH_SYNTHESIS_20261112.md`；
> 原始来源 URL 见 `FORECAST_RESEARCH_CLAUDE_20261112.md` / `FORECAST_RESEARCH_CODEX_20261112.md`。

## 1. 背景

当前 D5 v6.8 固定用 **97 / 157 天**，没有文档依据；97 天对波兰（累计交期约 100.6 天）不够；157 天到 2027-04-08，仍早于春节后首批复工货到货。D6 对所有键统一用 **q95**，但 q95 只有在“分位窗口 = 风险窗（L+R）”时才对应 95% CSL。D3b 的 `3_分类.adopted_model` 与 `4_回测_asof.adopted` 出现不一致。

本 ADR 定六件事：计划窗、服务分档、模型选择、单一事实源、春节 bridge、趋势诊断。

## 2. 决策

### D1 计划窗：按每键 L+R 定，不用固定 97/157

**规则**

```
H_key = ceil((L_p90 + R + buffer) / 7) × 7
R       = 复盘周期，默认 7 天
buffer  = 安全/季节缓冲，默认 ≥ 7 天
下限    = 8 周（56 天）
```

- `L_p90`：该键从下单到可售的 p90 累计交期（生产 + 头程 + 入仓），按链路分别取；波兰与美东/美中不得共用一个 L。
- **H_key 是计划/汇总窗**；**分位窗是 L_key + R**，不是 H_key。q95 必须取“风险窗 L+R 上的需求分位”，不能取固定 97 天。
- 标准展示桶：**98（14 周）/ 154（22 周）/ 161（23 周）/ 91（13 周）/ 112（16 周）**。
  - 98：默认短窗（14 周）。
  - 154：默认长窗（22 周）；需要 23 周时用 161。
  - 91：季度口径（13 周，对齐零售 4-4-5 季度）。
  - 112：波兰长交期专用（16 周；100.6+7=107.6 → 向上取整周）。
- **97 / 157 废弃**：不是 7 的倍数，按周汇总末周不完整；157 的 3 天余量没有分析含义。
- 周桶必须完整；月桶用日历月末，不用固定 30 天。

**依据**：Oracle JD Edwards 计划窗须覆盖累计交期；Infor 物料计划窗 ≥ total COLT；Microsoft coverage time fence 须长于总交期、按日历日计。来源见调研报告 S1–S4。

### D2 服务分档：A/B/C/D 是可校准的政策先验，不是“业界标准”

**先验**

| 档 | CSL 先验 | 适用 |
|---|---|---|
| A | 97.5–98% | 高毛利/高周转/断货代价高 |
| B | 95% | 常规主销 |
| C | 90% | 低周转/可替代 |
| D | 85% 或 fill-rate 目标 | 长尾/块状/慢销 |

- 95/90/85 只是**政策先验**；公开资料能支持的是“90–98% 常见、85% 对 C/Z 慢销合理”，没有“95/90/85 是业界标准”的来源。
- 有 Cu/Co 时用 newsvendor 临界比 `CSL* = Cu/(Cu+Co)` 校准；`Cu` 至少含毛利，可含平台惩罚/广告位/CLV；`Co` 含 L+R 内持有成本与过季跌价。
- **CSL ≠ fill rate**：95% CSL 通常对应更高的 fill rate；给业务必须写清指标。
- **禁止** cap `q95/p50` 或 sigma（p50=0 时无定义，且会掩盖模型误差）；改用业务上限（A 类安全库存 ≤8–12 周均值、C 类 ≤16–20 周）或金额上限。
- 校准：rolling-origin 的 PIT/覆盖率，按 class 要求 ±3pp；不达标调 α，不调 sigma cap。

### D3 模型选择：rolling-origin + FVA 门槛

**协议**

1. **Rolling origin、expanding window**；每个 origin 只用该时点前数据、重拟合；按 horizon 分别评估；禁止随机 CV。
2. **Selection 在 validation 上做，final 用最后 6 个月 holdout 只评估不选择**；报告按 horizon 给 WAPE + pinball loss + 覆盖率。
3. 候选集：
   - 基线族：`naive`、`ma3`、`snaive`、`ets_ann`、`ets_aadn`、`ets_aaa`（加性季节分解 + 阻尼 Holt / STL+ETS）、`theta`（简化 Theta：线性趋势与 SES 各 50%）。
   - 间歇族（挑战者）：`croston`、`sba`；`tsb` 仅 `obsolescent`。
4. 采用规则：先在同一条“有正销、共同可评估”的测试窗上取最佳基线；挑战者须 **WAPE/MAE 均不劣 + 至少一项改善 ≥5%（FVA）** 才采用，否则回退最佳基线。并列时按固定顺序取最简模型，保证确定性。
5. 对“看起来更好”的模型做显著性检验（Diebold–Mariano 或 block bootstrap），避免把噪声当改进。
6. 区间：经验残差分位或 split/online conformal；不要假设正态，尤其不要用正态外推 Croston/SBA 的 97 天分位。

**naive 不是病**：FVA 的逻辑就是打不过 naive 就用 naive；要修的是“adopted 写回不一致”，不是强行降低 naive 占比。

### D4 单一事实源：`4_回测_asof` → `3_分类`

- **唯一权威**：`4_回测_asof` 的 `adopted` 标记与 `3a_分类_asof.adopted_model`；两者必须一一对应。
- `3_分类`（current-owner，预测口径）**不再按产品历史量另选模型**；只 join as-of 采用结果：
  1. 单源键（`len(current_multi_from[key]) == 1`）：`adopted_model` 必须等于该 as-of 键的 adopted（精确 join）。
  2. 多源键（USNJ/USTX 合并）：源键模型一致 → 直接采用；不一致 → 取历史量最大的源键（确定性 tie-break），并在 `adopted_sources` 留痕。
  3. 无源键 adopted → `none`，不得凭空生成模型。
- **断言 fail closed**：源键缺失、同键多条 adopted、`3_分类` 模型不在源键模型集合、非 adopted 却带模型 → 直接抛错，不静默降级。
- **回退后必须重 join**：采用门槛复核可能把新方法回退成基线；`3_分类` 必须在回退后重建，不能沿用回退前的 as-of 模型。
- 输出 `model_source`：`asof_join` / `asof_join_multi_agree` / `asof_join_multi_maxqty` / `asof_join_none`，便于审计。

### D5 春节：供给日历 + bridge 窗，不拉大常规需求窗

**原则**：春节是**临时交期延长**，不是需求尖峰。

1. **供给日历**（参数先用本厂 2024–2026 实际曲线校准）：
   - 1/24–2/22 产能 0；
   - 2/22–3/8 爬坡 30–50%；
   - 3/15 后 100%。
2. **Bridge 窗** = 停工开始 → **首批复工货到目的地 + 1 个复盘期**。
   - 2027 波兰：2/22 + 43.6 + 2 + 55 ≈ **2027-06-02**，约 **212 天**；
   - 2027 中国线：2/22 + 71.5 ≈ **2027-05-04**，约 **183 天**。
3. **Pre-build 量** = `q_α(bridge 需求) − 停工开始时在手 − 停工前可到在途 − 停工前已确认 PO`；α 按 Q4 服务档。
4. **两批排产**：节前 bridge 批 + 节后补货批；节后批预留产能与原料。
5. **下单节奏**：最终生产单 11 月中前；12 月中前确认出货。
6. **不替代常规窗**：bridge 窗只用于春节 pre-build；常规 D5 仍按 D1 的 98/154（波兰 112）。
7. 若卖季在复工前结束（Q4 圣诞），需求窗覆盖到卖季结束，剩余按清货处理。

### D6 趋势诊断：逐产品证据，不做一刀切

**输出（每个 current-owner 键）**

- `yoy_pct`：2026-01..10 / 2025-01..10，只计已观测月。
- `slope_3m / slope_6m / slope_12m`：最近 3/6/12 个已观测月的 OLS 斜率（件/月）。
- `structural_break`：最近 12 个已观测月对半，或 2026 vs 2025 年均值；`|z| ≥ 2` 且相对变化 ≥30% 才标记 `up/down`（工程启发式，不是正式检验）。
- `trend_bucket`：`down>30` / `down10-30` / `stable` / `up10-30` / `up>30` / `no_2025_base` / `no_data`。

**用法**：趋势是**模型/情景选择的证据**，不是自动覆盖模型的规则。情景按 segment 生成 base/upside/downside + 概率 + 触发条件；触发看近 4–8 周 sell-through、同比、weeks of cover、广告转化；不统一砍 -20/-30%。

## 3. 影响

- D5 的 97/157 与统一 q95 需要 P2 改；本 ADR 只定规则，D5/D6 代码未动。
- D3b v3.11 已按 D3/D4/D6 落地：新增 3 个模型、单一事实源、趋势诊断；输出 `analysis/D3b-v3_11-20261112/`。
  P1 **未**实现 Diebold–Mariano/block bootstrap 显著性检验（ADR 列为 P2 的选择增强）；P1 的采用门槛仍是 WAPE/MAE 均不劣 + ≥5%。
- 下游 D5 消费 `3_分类` 时，`adopted_model` 的含义变成“as-of 回测采用结果的 join”，不再包含 current-owner 独立选择。

## 4. 验收

| 项 | 验收 |
|---|---|
| D1 | 每个键有 L、R、H、class；无键缺失；波兰 H ≥112 |
| D2 | A/B/C/D 分档表评审通过；覆盖率校准方案明确 |
| D3 | 候选集与 FVA 门槛评审通过；selection/reporting 分离 |
| D4 | `3_分类` 与 `4_回测_asof` 单源精确一致率 100%；多源 100% 可留痕；断言 0 违规 |
| D5 | bridge 窗与 pre-build 公式评审通过；2027 日期复核 |
| D6 | 趋势表覆盖全部 current 键；桶分布可解释；突变标记有抽样复核 |

## 5. 非目标

- 不改 D5/D6 代码、不改 CNY 排期、不下单、不写 EN/通途。
- 不引入 statsforecast/statsmodels 新依赖；三个新模型用 numpy 在 D3b 内实现。
- P2（分位窗/分档）、P3（CNY bridge 落地）、P4（情景/监控）、P5（全局 ML）不在本 ADR 实施范围。
