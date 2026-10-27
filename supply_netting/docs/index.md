---
okf: v0.1
type: Index
title: 供给净额集成层 — 文档索引
description: 冻结需求净额 × 库存/供应事实 → 按可售日期分桶净额、Parquet/manifest 与补货审核工作簿
tags: [supply-chain, netting, buckets, parquet, replenishment]
updated: 2026-10-27
---

# 供给净额集成层 — 文档索引

> Agent 入口先读 [`../AGENT_HANDOFF.md`](../AGENT_HANDOFF.md) 与 [`../README.md`](../README.md)。

| 你需要… | 读这个 |
|---|---|
| 引擎口径、两种情景、未知怎么保留 | [reference/netting-engine.md](reference/netting-engine.md) |
| 阶段余额 / 里程碑 / 可售 tranche 结构 | [reference/supply-facts-contract.md](reference/supply-facts-contract.md) |
| 输出字段、文件路径、manifest 结构 | [reference/output-schema.md](reference/output-schema.md) |
| 刷新预测怎么接入、资格怎么分 | [reference/forecast-input.md](reference/forecast-input.md) |
| 本次真实数据对账、案例、剩余阻塞 | [acceptance-report-2026-10-27.md](acceptance-report-2026-10-27.md) |
| 独立复审 F1–F4 返修与 r5 结果 | [review-fix-r5-2026-10-27.md](review-fix-r5-2026-10-27.md) |
| 第二轮复审 R1–R3 返修与 r5 复算 | [review-fix-r1-r3-2026-10-27.md](review-fix-r1-r3-2026-10-27.md) |
| 第三轮复审 R3 元数据收口（行数/pin 状态） | [review-fix-r3-metadata-2026-10-27.md](review-fix-r3-metadata-2026-10-27.md) |
| **10-29 广范围补货决策包**（去向对账 / 两档情景 / 审核清单） | [decision-pack-2026-10-29.md](decision-pack-2026-10-29.md) |
| 决策包终审返修 r2（F1–F7：null/JSON/UOM/对账/锁定/反事实/桶起点） | [decision-pack-2026-10-29-r2.md](decision-pack-2026-10-29-r2.md) |
| 引入的上游组件及来源 commit | [../../supply_chain_visibility/docs/reference/upstream-port.md](../../supply_chain_visibility/docs/reference/upstream-port.md) |
| **同日快照一条命令 runbook**（快照→需求→净额→决策包→动作） | [runbook-same-day.md](runbook-same-day.md) |
| **180 天视界 vs 35 天**（r4 预测、春节统计） | [horizon-180-vs-35-2026-10-29.md](horizon-180-vs-35-2026-10-29.md) |
| 变更时间线 | [log.md](log.md) |

## 产物路径（本地，不进 git）

- 输出根：`D:/Work/fzh-order-store/en-demand-v1/supply-netting/<run>/`
- 历史样例：`run-2026-10-21/`（`as_of=2026-10-21T00:00+08:00`，快照 `2026-10-20`）
- 当前样例：`run-2026-10-26-r5/` + `pack-2026-10-26-r5/`（快照 2026-10-26，预测 forecast-20261027-r2）
