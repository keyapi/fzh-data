---
okf: v0.1
type: Review
title: Phase 1C 三段式交付（需求预测 / 分时供给 / 三态判定）— 生成与对账记录
date: 2026-10-22
owner: claude-worker
status: 完成；不出采购指令，本批 0 数量
inputs:
  - out/business_phase/ranking.json（d50310a6，只读）
  - out/business_phase/destinations.json（44def7f5，只读）
  - out/replenishment_v0/evidence.json / model_race.json（f9df4357，只读）
  - D:/Work/fzh-order-store/order_store.duckdb（read_only）
artifacts:
  - experiments/business_phase/build_plan.py
  - out/business_phase/plan.json
  - out/business_phase/plan.md
---

# Phase 1C：三段式交付

> 覆盖集合 = **Top50 ∪ 紧急履约例外**。脚本**重新计算**并集（不是抄清单）：
> 50 + 75 − 重叠 3 = **122**；其中母集内 84、母集外 38。
> 未访问生产、未扩样、未下单；DB 只读且前后 sha256 一致；
> Phase 1A/1B 产物与 V1 冻结产物**零改动**。

## 1. 需求预测（口径沿用 V1）

| 项 | 做法 |
|---|---|
| 训练 | Phase 1B 冻结的 6 个月净销量（2026-04..09，零填充） |
| 点模型 | `mean3`（最近 3 个月均值） |
| 地平线 | **90 天**（2026-10-22 → 2027-01-20），同形日历窗口 |
| 代码复用 | **直接 import `model_race.py`**（V1 冻结脚本，未改一行），调用 `window_calibration` / `forecast_candidate` / `calendar_window_weights` / `conf_q90` |
| `label_available_at` | 残差只在其最后触及月份**结束之后**才进入标定（V1 R3 口径），产物写入 `label_rule` 与 `n_window_ended_but_label_pending` |
| 表述 | `estimator=rolling_empirical_conformal_style`、`finite_sample_guarantee=false`；**不声称有限样本 90% 保证** |

**结果**：84 个 SKU 有可预测历史（区间状态：`conformal_empirical` 76、`estimate_small_sample` 6、
`estimate_pooled_peer_relative` 2）；38 个母集外 SKU **无 2026-09 前的发货历史** → 标
`not_calibrated` / `available=false`，不编造预测。

**断货与未履约不当零需求**：零填充月份若同时存在断货观测或待发订单，记入
`demand.censoring.zero_months_with_unfulfilled_signal`（本批 **12 行**）。规则明写：
「未履约/断货是可观测缺口，不是零需求」。
**退货/取消不可观测**（`gs_orders` 无状态字段、窗口内 0 条负数量行）→ 作为口径边界写入每一行。

## 2. 分时供给情景

时间桶（增量、不重叠）：`A 0–40d` / `B 41–71d` / `C 72–91d`（对齐 90 天地平线）/ `D >91d`。

每侧都带：`value / status / components[source, qty, documents, deduped, uom_converted, in_window, note] / blockers / missing_evidence`。

| 事实 | 值 |
|---|---|
| 窗口内已证在手（`supply_lower` 合计） | **7,020** |
| 记录之和（`supply_upper` 合计） | 19,336（含在途与未结 PO） |
| 有未结 PO 的行 | 31（248 条 open 行） |
| **有 `will_arrive_date` 的 open 行** | **0 / 248** |
| UOM 已换算的行 | 84 / 122（其余物料无 BOM 件/个/套行） |
| 供给下界已证行 | 84（其余 UOM 未证 → `unproven`） |
| 供给上界已证行 | **0** |

**关键规则**：
1. **没有 ETA 的到货不进任何下界**，因此**不能用来消除近期缺口**（在 A 桶只作为压力上界）。
2. **`supply_upper` 永远不能证明充足**：它是记录之和，`deduped=false`，且 Cover 未上账。
3. **生产/在产不在本快照**（`order_store.duckdb` 没有 WO 表；V1 的 10 SKU 在产是从 EN API 单独取的）
   → 上界可能**低估**，所以**短缺也不能据此定论**；该缺口写入 `blockers` 与 `missing_evidence`
   （生产/PMC）。例如 DEEPGREY 在这里只有在手 1 件，而 V1 证据里它有 152 件在产 —— 差别就来自这个源。

## 3. 三态判定

| 状态 | 行数 |
|---|---:|
| `no_replenish`（已证供给下界 ≥ 需求上界） | **0** |
| `replenish`（供给上界 < 需求下界） | **0** |
| `pending`（其余，数量留空） | **122** |

- **有数量的行：0**；所有 `quantity_baseline` / `quantity_stress` 为 **`null`**（不是 0，也不是空格）。
- 为什么全是 pending：需求上界目前是 **conformal-style 估计**（不是已证上界，G8 未提供业务界）；
  供给上界 `deduped=false` 且缺在产；UOM 38 行未证。按 R4 标准，两侧都不满足，不能出结论。
  这与 V1/R4 的判定完全一致，**不是脚本没跑通**。
- 方向性参考（明确标注 `screening_note`，**不是结论**）：`shortage_signal` 2 行、
  `sufficiency_signal` 12 行、`ambiguous` 108 行。`sufficiency_signal` 用的是「在手 ≥ P90」，
  只说明方向，不代表充足（P90 不是上界）。

## 4. 缺证据（逐行，含责任人）

每行 `missing_evidence[]` 至少 1 条，常见项：

| 缺口 | 责任人 |
|---|---|
| 物料件/个/套单位（UOM） | 商品主数据/仓储 |
| 映射到物料的 BOM 件/个/套行 | 商品主数据/工程BOM |
| 未结 PO / 在途到货日 | 采购/供应链；数据/系统 |
| PO/在途逐笔重叠键 | 数据/系统 |
| **在产 WO 剩余量与完工日** | 生产/PMC |
| Cover 等未上账替代供给的存在性 | 商品主数据/仓储 |
| 业务需求上下界（G8） | 业务/运营 |
| 该 SKU 的 EN 映射（母集外 38 行） | 商品主数据 |

## 5. 对账

| 项 | 值 |
|---|---|
| 覆盖集合 | **122**（可复算：Top50 50 ∪ 例外 75，重叠 3） |
| 入 / 出 | 122 / 122，`dropped=[]` |
| 四要素齐备 | 122/122 有 `demand`、`supply`、`decision`、`missing_evidence` |
| 待核实行数量 | 122/122 为空 |
| 两次运行 | 除 `generated_at` 外**逐字节一致** |
| 输入绑定 | ranking / destinations / evidence / model_race.py+json 的 sha256 全部记录 |
| DB | 只读；前后 sha256 一致，变则拒绝发布 |
| 凭证 | `uv run python scripts/check_secrets.py` 零输出 |
| 临时文件 | 仓库根与 `out/business_phase/` 均无残留 |

## 6. 已知边界

1. **生产在产缺失**：不是 122 行都没在产，而是本快照没有 WO 表；补 EN 在产后 `supply_upper` 会变大，
   短缺判定才有意义。
2. **需求上下界只有估计**：P50/P90 可以支撑情景与排序，但不能支撑「不补」结论。
3. **母集外 38 行**（紧急例外里没有 6 个月销量的 SKU）没有需求预测，只有供给与待发证据。
4. **退货/取消**不可观测，净销量=已发货；若退货另表记录，需求会被高估。
5. 分桶是增量式；90 天决策用 `supply.supply_lower/upper`，不是桶求和（JSON 有 `bucket_semantics`）。

## 7. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/build_plan.py
uv run python scripts/check_secrets.py
```

产物：`out/business_phase/plan.json`（1.5 MB，逐行三段式）与 `out/business_phase/plan.md`（摘要）。

DONE P1C
