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
| 输出字段、文件路径、manifest 结构 | [reference/output-schema.md](reference/output-schema.md) |
| 本次真实数据对账、案例、剩余阻塞 | [acceptance-report-2026-10-27.md](acceptance-report-2026-10-27.md) |
| 引入的上游组件及来源 commit | [../../supply_chain_visibility/docs/reference/upstream-port.md](../../supply_chain_visibility/docs/reference/upstream-port.md) |
| 变更时间线 | [log.md](log.md) |

## 产物路径（本地，不进 git）

- 输出根：`D:/Work/fzh-order-store/en-demand-v1/supply-netting/<run>/`
- 本次样例：`run-2026-10-21/`（`as_of=2026-10-21T00:00+08:00`，快照 `2026-10-20`）
