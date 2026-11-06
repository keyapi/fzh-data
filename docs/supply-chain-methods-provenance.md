---
type: Reference
title: 补货框架的方法来源：复用、标准算法与自建边界（2026-11-07）
date: 2026-11-07
---

# 补货框架的方法来源

结论：**预测/库存的核心算法是标准方法，不是自创；自建的是公司特有的身份、政策与排期层。**
但当前管道里多数模型是本地实现，没有直接接 `statsforecast` 等成熟库；这是下一步要补的复用点。

## 1. 直接采用的标准算法（本地实现，非发明）

| 层 | 方法 | 来源/性质 |
|---|---|---|
| 需求预测 | naive、MA3、seasonal naive、ETS(A,N,N) | 教科书级基线；Hyndman & Athanasopoulos《Forecasting: Principles and Practice》 |
| 间歇需求 | Croston、SBA、TSB | Croston (1972)、Syntetos-Boylan (2005)、Teunter-Syntetos-Babai (2011) |
| 区间 | p50/q95 两点 → 对数正态矩匹配 | 标准做法；不是完整概率校准 |
| 日需求拆分 | 总量按 Dirichlet 分日 | 标准单纯形分布；用于保留总量分位数 |
| 库存模拟 | Monte Carlo 逐日库存、cycle service vs fill rate | 标准库存理论；Silver/Pyke/Peterson |
| 服务目标 | 周期无断货概率 vs 总满足率 | 两种服务定义，不能混用 |
| 交期 | lead-time demand、p50/p90、pre-haul 单列 | 标准提前期分解 |
| 决策 | newsvendor 临界比思想（服务水平→分位数） | 标准报童模型；未做多级优化 |

## 2. 自建的公司特有层（没有现成轮子）

- **A/B/C 身份与 owner 重述**：A 活跃宇宙、B 当前实际负责人、C 物理库存；历史仓只作证据。
- **60cm 等价**：KS0001→KS0248 仅同面料同颜色，且目标必须是当前活跃键。
- **D6 补货沙盒**：补/不补/催已有/观察；CG 只抵扣一次；不跨仓。
- **春节停工排期**：1/24 停工、2/22 复工；按覆盖终点备货；首批/第二批整数拆分。
- **人工审核交付包**：可执行/风险隔离/零中位数/模型异常分桶；一致性校验。

这些规则来自公司实际流程（Jing 品类政策、波兰资格、PB/客户码、春节停工），不是通用框架能直接覆盖的。

## 3. 明确没有采用/尚未补齐的 SOTA

- **分层预测 reconciliation**：目前只有产品/市场池化校准，没有 MinT/OLS 分层协调。
- **完整概率校准**：只有 p50/q95 两点，没有 full predictive distribution / conformal。
- **多级库存优化/APS**：没有多级 echelon 优化、没有商业求解器；D6 是规则沙盒。
- **完整 S&OP/MEIO**：没有需求评审、供应评审、财务联动的闭环。

## 4. 下一步优先复用（不再手写）

1. `statsforecast` / Nixtla：模型选择、滚动回测、AutoETS/AutoARIMA/Croston 系列。
2. `HierarchicalForecast`：产品→市场→总体的分层协调。
3. `sktime` / `statsmodels`：概率校准与区间评估。
4. 现有 `demand_forecast` 子项目已用 statsforecast 2.1.1；优先把 D5 的本地实现迁到该库，而不是继续扩写本地模型。

## 5. 教训

- “先搜再造”应体现在**默认调用成熟库**，而不是“知道算法名字后自己重写”。
- 公司特有规则必须自建，但应把“标准层”和“业务层”分开；标准层尽量换成库，业务层保持薄。
