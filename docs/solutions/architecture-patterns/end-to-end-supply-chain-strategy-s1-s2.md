---
okf: v0.1
type: Reference
title: 端到端供应链策略层 S1/S2：三运输大类、联合模拟与例外队列
date: 2026-11-03
category: architecture-patterns
module: supply_chain
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "需要把 D 需求、C/EN 供给、生产交期、头程与下单时点连成一条可解释链路"
  - "决定按普船/快船/空运哪种方式补、什么时候下单、补多少"
  - "有人把单键 95 分位当整段 95% 不断货保证时"
  - "要区分可执行候选、人工复核、无路线、催后 ETA 未证、服务风险"
tags: [supply-chain, s1, s2, transport-class, monte-carlo, exception-queue, service-level]
---

# 端到端供应链策略层 S1/S2

## Context

D 层只回答「需求分布是多少」；真正决定补不补、什么时候补、走什么方式、补多少，
还缺一条从 `as_of → 下单 → 生产 → 头程 → 到仓 → 需要日` 的链路。S1 先做逐键节点
时间线与模式选择，S2 把它升级成需求 × 生产 × 头程的联合蒙特卡洛，再从模拟结果里
拆出「可执行候选 / 人工复核 / 例外队列」。

关键背景：

- 运输方式不再等外部字段定义。按已签收运单实际数据自己分三类：
  普船 ~50/64 天（p50/p90）、快船（美森/Matson 系）~31/32 天、空运 ~13/14 天；
  规划默认值 55/30/14 天。
- 生产交期按分公司（pool）用 SO→DN 实际样本：2026-05..10 约 PL 21.5/36.8、
  USNJ 21/33.5、USTX 21.5/32.6 天（p50/p90），并在 p95 处 winsorize。
- 不跨仓直发；成品 MOQ = n/a（绍兴自有工厂）；CG 只观察、不补货、不抵扣。
- 模型通过 ≠ 可下单。S2 全程 `auto_order=false`，输出只是人工审核候选。

## Guidance

### 1. S1：先画节点，不要先算一个数

每个键一条时间线：`as_of → 建议下单日 → 生产交期 → 头程交期 → 预计到仓 → 需要日`。
缺少路线或催后 ETA 的键，明确标 `route_pending` / `expedite_eta_unknown`，
**不能**仍然给出一个「推荐空运」。这是 S1 被独立复审 REJECT 的直接原因：
506 条无路线仍给推荐、85 条催已有全给空运、把分位数直接相加当总交期。

### 2. 三运输大类自己定义，成本用相对代理

| 大类 | 判定（已完成运单） | p50/p90 | 规划默认 |
|---|---|---|---|
| 普船 | 普通海运承运人 | ~50/64 天 | 55 天 |
| 快船 | 美森 / Matson / 快线 / 蛟龙 | ~31/32 天 | 30 天 |
| 空运 | 空运承运人 | ~13/14 天 | 14 天 |

成本用相对代理 `1 / 1.8 / 6` + 持有成本 + 缺货罚，仅用于同键内比模式，
**不是**实际运价，不得对外当报价。

### 3. S2：联合模拟，模式可行性看总交期

- 生产与头程各自 bootstrap（阶段独立假设），`lead = production + head_haul`；
- 模式可行：`P(lead <= need_days) >= 95%`，在可行模式里选相对成本最低；
- `Q = 95th percentile(demand_over_lead - available)`，`available` 为可发 + 能在需要日前到的在途/PO；
- 无模式达标时不再「默认空运」，而是标 `no_mode_service_95` 并进入例外。

### 4. 例外队列优先于推荐

S2.3 起先分流，再谈可执行：

- `actionable_candidate`：有路线、无服务/范围例外；
- `exception_route_pending`：无路线，等运输分类/物流商；
- `exception_expedite_eta_unknown`：催后 ETA 未证；
- `exception_human_review`：Top100 要求复核；
- `exception_service_risk`：模拟服务概率 < 95%；
- `exception_b2_scope`：B2 范围外；
- `no_action_or_observe`：不补/观察。

### 5. 分位需求 ≠ 全程服务率

S2.4 对可执行候选做逐日库存模拟后：332 个候选只有 **154** 个真正达到 95% 无断货，
178 个失败；平均无断货概率 0.774、平均断货 10.05 天。结论：Q95 净需求分位
不等于未来 95% 不断货，快船尤其不足。S2.5/S2.6 加大量/升舱搜索后仍只修好个位数，
S2.7 才把失败拆成结构性原因：`upgrade_still_below` 67 / `q_zero` 50 /
`air_no_upgrade` 32 / `impossible_by_date` 27 / other 2。

### 6. 决策包分层，不伪造未知

S2.8：154 键冻结为 `model_pass_pending_human`，178 键 `unresolved`；50 个 q_zero
单列深度诊断；`impossible_by_date` 不靠加量硬救。E 的行级单据/催后 ETA 未知时
保留 unknown，不补造。

## Why This Matters

- 把 D 的 q95 直接当补货量，会系统性高估服务：332 个候选里一半以上达不到 95%。
- 不先分流例外，会把 506 条无路线、73 条催后 ETA 未证也算成「可执行」，误导下单。
- 分位数相加不是联合分布；交期必须按阶段 bootstrap，否则 24/62 天会被算成 16/41。
- 用相对成本代理可以比较模式，但若不说清不是实际运价，就会被当成采购依据。

## When to Apply

- D6 之后的下单时点/运输方式/补货量决策；
- 业务问「为什么不直接按 q95 补」「为什么这么多空运」；
- 接入 E（运单/催货）或真实运价后重跑策略；
- 给管理层解释「模型通过」与「可下单」的边界。

## Examples

- S2.2：1,749 键，可模拟 478；补 135 快船 / 1 普船 / 342 空运；494 路线待确认、
  73 催后 ETA 未证。
- S2.3：可执行候选 332（1,485 件）/ 人工复核 89（3,184 件）/ 无路线 506 /
  催后 ETA 未证 73 / 服务风险 57（762 件）/ 不补或观察 692。
- S2.4：空运 246 候选仅 139 达标（平均 0.839）；快船 85 仅 14 达标（平均 0.586）。
- S2.8：154 冻结待人工 / 178 未决；S2.9 对 50 个 q_zero 做可用/在途/PO/ETA/
  p50/q95/首缺货/缺口逐项诊断。

## Related

- `docs/solutions/architecture-patterns/demand-forecast-layer-d.md`
- `docs/solutions/architecture-patterns/us-owner-restatement-and-b2-scope.md`
- `docs/solutions/workflow-issues/supply-chain-review-and-human-escalation.md`
