---
okf: v0.1
type: Log
title: 供给净额集成层 — 变更日志
description: 2026-10-27 首版净额引擎、上游组件引入与真实数据对账
tags: [log, netting, supply-chain]
updated: 2026-10-27
---

# 变更日志

## 2026-10-27 — 首版

- 新建 `supply_netting/`：冻结需求净额 × 库存/供应事实 → 按可售日期分桶净额。
- 原样引入上游组件（`git show`，未改写）：
  - `supply_chain_visibility/receipt_buckets.py` + `tests/test_receipt_buckets.py`（`b08acc05`，11 用例）；
  - `supply_chain_visibility/supply_row.py`、`overlap_gates.py` + 用例（`6d374085`）；
  - 三个纯函数 `bucket_gaps` / `assert_bucket_identities` / `allocate_so`（`aa93773b`）。
- 引擎：`build_buckets` 保护期 + 周桶；`net_target` / `net_all`；保守/预期两种情景；
  未知 ETA 只进条件量；无快照基准判 `unknown`。
- 供应侧：通途库存快照（0 也作为有效观测）、在途（无 ETA）、开放 PO（多为物料仓）；
  无法映射的输入保留为证据行，不静默丢弃。
- 产物：`supply_netting.parquet`、`supply_facts.parquet`、`replenishment_review.parquet/xlsx`、
  `third_party_demand.parquet`、`supply_netting_manifest.json`。
- 实跑 `as_of=2026-10-21T00:00+08:00`（快照 2026-10-20）：426 个键、保护期需求 602 件、
  10 个键有缺口共 16 件、条件供应 9,954 件；恒等式与数量账全部通过。
- 契约 v1 升级：新增 `facts.py`，落地 `stage_balances`（阶段互斥、累计交付不算供给、
  订单差额单列）、`milestones`（计划/预计/实际分列）、`availability_schedule`
  （tranche 可售日、拆分守恒、已含期初/FBA 不再补入），并把在途经 tranche 接入净额。
- 真实数据：172 条在途阶段余额 → 172 条条件态 tranche；其他阶段无本地源，明确记为缺口。
- 测试：`supply_netting` 35 个（8 条必测场景 + 契约 §7 的 9 例 + 契约边界 + 真实案例），
  引入的上游组件 23 个，全部通过。
