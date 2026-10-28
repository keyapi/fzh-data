---
okf: v0.1
type: Reference
title: FRONTIER-DEDUP：frontier_v2 与既有评估器的差异与去重结论
description: 实测 R=1 逐项相等（核心语义同一套）、周复核差异来自相位、α≠CSL、backorder 仅资产支持；frontier_v2 冻结，后续只包既有评估器
tags: [frontier, inventory-policy, dedup, beta, alpha, backorder, asset-reuse]
date: 2026-10-28
status: implemented
---

# FRONTIER-DEDUP（A1/A2/A3 落地）

审计结论（[asset-reuse-audit-2026-10-28.md](asset-reuse-audit-2026-10-28.md) A1/A2/A3）：
`frontier.py` / `frontier_v2.py` 自写 base-stock 回放，未复用
`experiments/business_phase/inventory_policy.py`（`simulate_flow` / `simulate_policy` /
`metrics` / `bisect_order_up_to`）；服务缓冲还用正态 CV，与 sc08 的比率经验分位不同（名义 95%
实际 0.54–0.70）。

本篇是**核查与定规**，不改任何数字、不重写已验收产物、不 push。

- 检查脚本：[`../scripts/frontier_dedup_check.py`](../scripts/frontier_dedup_check.py)（从 git 取资产，只读）
- 测试：[`../tests/test_frontier_dedup.py`](../tests/test_frontier_dedup.py)（9 条）
- 产物（本地，不进 git）：
  `D:/Work/fzh-order-store/en-demand-v1/supply-netting/frontier-dedup-2026-10-28/`
  —— `report.md`、`comparison.json`、`manifest.json`

## 1. 结论

1. **核心语义是同一套，不是两套算法**：逐日复核（R=1）时，既有评估器与 `frontier_v2.simulate`
   在同一需求、同一 S/L/R 下**满足量、缺货量、β、平均库存完全相等**（两组案例，差 = 0）。
2. **但不能直接替换**：差异全部落在**数据管道与指标口径**——复核相位（期初 vs 期末）、
   暖机与在途预置、目标水平来源（分位假设 vs 目标反解）、`α` 与 `CSL`、backorder 缺位。
3. **frontier_v2 冻结**：已验收产物（`service-inventory-frontier-2026-10-28-v2/`）保持原样，
   **不再扩写**；后续政策实验**只包既有评估器**。

## 2. 逐项差异

| 维度 | `inventory_policy`（既有，e3727683） | `frontier_v2`（本层） | 结论 |
|---|---|---|---|
| **β / α** | β=fill rate 为主、α=CSL 次之；无需求周期时 α **不计算**；需求周期数/零需求周期数单列 | fill_rate 公式同 β；CSL 按**复核周期**计，且暖机段短缺会泄漏进首个评分周期 | β 同口径；**α ≠ CSL** |
| **L+R** | 复核周期 R、提前期 L；保护期 = R+L，S 由调用方给；`bisect_order_up_to` 按目标 β 反解，暖机取 L+R | 同 R、L；target = (L+R) 天滚动销量和的**经验分位** × 倍数 | 保护期概念一致，**目标来源不同** |
| **政策** | order-up-to 参照政策；`position = 库存 + 在途` | base-stock target；`position = 现库存 + 未来到货` | 同一族（实测 R=1 相等） |
| **lost_sales / backorder** | `semantics` 显式参数，二选一、不混；backorder 欠单结转且不重复计损 | **只有 lost_sales**（`take=min(on_hand, want)`，未满足即消失） | **不可替换**：缺 backorder |
| **复核相位** | 期末复核：`t % R == R−1` 下单，t+L 到货 | 期初复核：`t % R == 0` 下单，t+L 到货 | 短提前期差异最大（实测 L=7 差 36 件） |
| **暖机 / 在途** | 无内置暖机（调用方切片 `[warmup:]`）；无在途预置 | 暖机 L+R 天 + 稳态在途按 `seed_rate` 预置 | 管道差异，不是算法 |
| **数据管道** | 任意序列或显式 `receipts` | 真实观测销售、统一评估截止、无订单日补 0、ABC/UOM 组内分档 | 本层独有，**这才是不能直接换的原因** |
| **网格** | L=60/90/120、R=7/30、β=90/95/99%（探索值，非批准） | L=60/90/120、level=90/95/98%、×1.0/1.5/2.0、R=7 | 可对齐 |

### 指标定义（最容易混的两处）

- **β ≡ fill_rate**：都等于 `满足量 / 需求量`。检查脚本对两边各自验算公式（本次均为 True），
  但同一组参数下数值会因复核相位而不同（不是定义不同）。
- **α ≠ CSL**：
  - α（既有）= 有需求期间中「完全满足」的占比；本次有需求期间 198 个。
  - CSL（本层）= 复核周期中「无任何短缺」的占比；本次复核周期 29 个。
  - 同一次回放实测 **α=0.8586 vs CSL=0.2759** —— 相差一个数量级，**不能互相翻译**。

## 3. 数值证据（同一需求、同一 R/L/S，seed 固定）

| R | L | S | 既有满足 | 本层满足 | 差 | 既有 β | 本层 fill_rate |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 7 | 60 | 1001 | 1001 | 0 | 1.0000 | 1.0000 |
| 1 | 30 | 100 | 671 | 671 | 0 | 0.6703 | 0.6703 |
| 7 | 7 | 60 | 914 | 878 | −36 | 0.9131 | 0.8771 |
| 7 | 30 | 100 | 600 | 599 | −1 | 0.5994 | 0.5984 |
| 7 | 60 | 200 | 625 | 622 | −3 | 0.6244 | 0.6214 |

- R=1 两组**完全相等** → 核心回放等价；R=7 的差异随提前期拉长被稀释（36 → 1 → 3），
  符合「期初 vs 期末复核」的相位解释。
- backorder 对照（L=30、R=7、S=25，故意缺货）：既有评估器 lost_sales 丢 935 件、期末欠单 0；
  backorder 丢 0 件、期末欠单 935。**frontier_v2 没有这个分支。**

## 4. 决策与后续规则（后续任务必须遵守）

1. **不替换、不重写**：frontier v2 的已验收产物与数字保持原样。
2. **frontier_v2 冻结**：不得再新增模拟/评估入口。冻结面 = `global_series / target_from /
   simulate / build / summarise / main`；测试 `test_public_surface_is_frozen` 会在新增函数时失败。
3. **后续政策实验只包既有评估器**：不同 β 目标、R、backorder 情景一律调用
   `inventory_policy.simulate_policy` + `metrics` + `bisect_order_up_to`；本层最多在外面包一层
   数据管道（把需求/日历/资格喂进去），**不再复制回放逻辑**。
4. **口径披露**：引用本层 CSL 必须写「按复核周期计」；引用 SC08 的 α 必须写「按有需求期间计」。
   服务率承诺优先用**比率经验分位**（sc08），不用正态 CV。
5. **backorder 情景**只能在既有评估器上跑。

## 5. 复现与检查

```bash
uv run python -m supply_netting.scripts.frontier_dedup_check    # 出 report/comparison/manifest
uv run python -m pytest supply_netting/tests/test_frontier_dedup.py -q
```

检查脚本从 git（默认 `<当前仓库>:e3727683`）取回资产，导入到临时目录执行，**不落盘到仓库、
不改资产文件**。测试共 9 条：冻结面、`simulate` 无 semantics、fill_rate 公式、R=1 相等、
R=7 有相位差、α≠CSL、backorder 仅资产支持、缺资产时显式失败、落盘只写 out 目录。
（没有资产历史的环境会 `skip` R=1/R=7 等资产对比用例，并在原因里写明，不会假装通过。）

## 6. 边界

- 只读：未改 `frontier_v2`、`frontier.py`、`policy_options*`、决策包与任何已验收产物。
- 不 push；不重跑 r6/h180。
- 本层与资产的数字差异**如实保留**，不为了「看起来一致」去调参。
