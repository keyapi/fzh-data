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

## 2026-10-27 — 独立复审返修 + r5

- 修 F1–F4：期初资格、阶段证明端到端传递、跨阶段同批额度与重复失败关闭、
  到仓待上架可售 tranche。
- 附带 F6–F9：需求/预测严格布尔、全输入哈希与代码版本、视界外供应逐条留痕、
  空事实表固定 schema。
- 新增 `forecast.py`：消费 forecast-20261027-r2，预测资格与需求净额资格分离。
- r5：545 键、保护期缺口 71 键共 34.87、视界末未满足 449.97、条件供应 11,305；
  全部恒等式通过，`git_dirty=false`。
- 测试 147 通过（F1–F4 回归 21 个、预测 9 个）。

## 2026-10-27 — 第二轮复审 R1–R3

- R1：拆分谱系（split_of / split_total / document_key split-quota）传到计数侧；
  合法 6+4 子额度各自计数（净额 10、gap 0），只有同一额度跨阶段重放才去重；
  拆分与整批观察并存时两侧保留并上报 batch_split_conflicts。
- R2：混合已知+未证期初 → opening=null + opening_lower_bound，gap 保持 null。
- R3：预测入口按上游 manifest 校验窗口 sha256 与行数，新增 --forecast-manifest-sha256。
- r5 复算：代码 d4fc0862（git_dirty=false），数字与上一轮完全一致；预测哈希已验证。
- 测试 159 通过（supply_netting 136 + 上游 23）。
