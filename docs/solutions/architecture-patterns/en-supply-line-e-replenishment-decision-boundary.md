---
okf: v0.1
type: Reference
title: EN「供给线 E」用于补货/下单决策的边界 — instock 是累计入库，库存与收货未接入
date: 2026-11-12
last_updated: 2026-11-12
category: architecture-patterns
module: supply_chain_visibility
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "准备把 key_test.so_chain 的返回值直接作为补货/下单/交期承诺的供给事实源"
  - "评审「整条供应链下单决策」是否需要接入 E，或需要给 E 补哪些字段"
  - "看到 instock / produced / open_qty / stage 字段，需要判断它到底代表什么"
tags: [erpnext, so-chain, replenishment, instock, availability, qc-gate, partial-data, decision-boundary]
related_components: [supply_chain_visibility, key_test, erpnext-wo-audit, fulfillment_query]
---

# EN「供给线 E」用于补货/下单决策的边界

## Context

`key_test.so_chain.get_so_chain`（下称「E」）已在**生产可用**：给定一个销售订单，返回行级
`stage/substate`、已发/未发、`produced/reported/instock`、DN 明细、`shipment_progress`、
`qc_status/completion_status`、`partial/source_status` 等。

2026-11-12 用三张真实 SO（`SO-26-00088` / `00103` / `00109`）核对出库与在途，并让独立
Codex worker 做只读复核。结论是：**E 作为 SO 级进度看板已经好用；作为整条供应链下单/补货
决策的供给事实源，还不能直接用。**

根因不是「字段少」，而是**几个字段的语义与决策需要的语义不一致**，且缺失的数据源不会阻断返回。

## Guidance

### 1. 先分两种用途，不要混

| 用途 | 判定 | 前提 |
|---|---|---|
| SO 级进度看板（卡在哪、发了多少、何时到） | **可用** | 加 §4 的护栏；把 `partial` 当作可见警示 |
| 整链下单/补货决策的**供给事实源** | **不应直接用** | 至少先完成 §5 的 P0 |

### 2. 先确认「线上版」而不是仓库快照

仓库里的 `key_test__so_chain.py` 是 v4，**线上版已经超过它**：线上额外返回
`shipment_progress`、`all_process_done`、`qc_*`、`completion_status`、`production_evidence`、
`evidence_conflicts`、`partial/source_status`。用仓库 v4 做静态评审会**误判线上能力**
（例如「E 不含在途」对线上不成立）。评审前先把线上源码同步回仓库。

### 3. 七个会直接影响补货决策的偏差（按危害排序）

1. **`instock` 是累计入库，不是可用库存。**
   线上 `instock = produced_sum`（本行物料的工单入库量）。实例 `PK#KS0001-CMKTR-100-BLACK`：
   `instock=72`、已发 72；实际 `半成品仓 = 0`（`reserved=45`）、`美东USNJ到货仓 = 481`。
   把它当可用，会**重复计已发**、又**漏掉真正在海外仓的 481**。
2. **库存与收货未接入。**
   线上返回 `source_status = {inventory: not_integrated, receipt: not_integrated}`、
   `tongtool_po = null`。补货需要「现有库存 / 在途入库 / 采购在途」三块，E 都没有。
3. **超发会错误抵扣需求。**
   `open_qty = qty - delivered` 可为负。三张 SO 实测超发 179（00103）与 45（00109）件；
   若按净额汇总，A 的溢出会抵掉 B 的缺口 → **少补**。需求必须**逐行截零**，超发单列。
4. **质检未放行可能被当成「完成待出库」。**
   全工序只差质检的行，如果只看工序完成就判可发，会承诺出运但实际发不出。
   实例：`WO-26-03113`（102 件/6 个菲号）缝制全完、质检 0、无 Manufacture 入库单，只有耗料单。
5. **Closed/死单落 `stage=3`。**
   仓库 v4 对 `doc.status='Closed'` 且未发的行返回 `stage 3 / substate "Closed未发(死单)"`；
   下游若只汇总 stage，会把死单算成履约完成，需求少算。必须独立 lifecycle 或剔除。
6. **`partial` / `source_status` 只是警示，不阻断。**
   数据缺失时仍返回结果；决策系统若不把 `partial=true` 或 `inventory/receipt=not_integrated`
   当阻断条件，就会拿不完整供给做决定。
7. **性能与权限未验证到组合级。**
   v4 每行约 8 次查库，154 行约千次；线上首张约 6.8 秒，千单级未压测。权限只校验 SO，
   关联 SQL 的权限未审计。

### 4. 如果先用 E 做看板，必须加的护栏

- 需求逐行 `max(0, qty - delivered)` 后再汇总；超发单独列。
- 「可发」只看 `入库（Stock Entry/purpose=Manufacture, docstatus=1）+ 质检放行 + 可用库存`，
  不看 `instock`，也不只看工序完成。
- `Closed/取消` 单剔除或单列，不并入履约完成。
- `partial=true` 或 `source_status != ok` 时，页面显式标红并**阻断「可下单」结论**。
- 展示 `signed_status_proven=false`、`status_semantics=unproven`、`conflict_flag`，不要把
  「货代回传签收」写成「客户已签收」。

### 5. 改进清单

**P0（不改不能用于补货决策）**

- 接入库存：按仓库、按时点返回 `actual / reserved / available`，并明确分配；
  `instock` 改名或改为「累计入库」。
- 接入收货/在途入库（receipt）与采购在途；当前 `not_integrated`。
- 提供 SKU×客户 维度的需求汇总：逐行截零、超发单列、Closed/取消剔除、跨 SO 去重。
- 「可发」判定 = 已入库 + 质检放行；与「已完工」「已入库」三层分开。
- `source_status` 不完整 / `partial` / `unproven` → **阻断**，不是提示。

**P1**

- 批量接口/报表替代每 SO 的 N+1；权限审计与缓存。
- 补 lifecycle（按客户）、UOM/套件、SKU↔通途别名映射。
- ETA 统一口径与置信度：同一票目前可能同时有 11/17、11/18、11/19 三个 ETA。

## Why This Matters

补货决策是「加/不加、今天/下周/空运/催」的二阶动作。供给量高估 → 少补、断货；
供给量低估或需求被错抵 → 多补、压库存；把未质检/未入库当可发 → 承诺交期后发不出。
E 的字段语义不统一，正好同时制造这三类错误。

## When to Apply

- 任何「用 E 的返回直接算供给/净需求/可下单量」的设计评审。
- 只做 SO 进度展示、不参与数量决策时，可按 §4 放宽。
- 与 `EN_API/fulfillment_query.py` 的 JSON 契约对接时同理：JSON 是权威输出，但数量口径仍需分层。

## Examples

三张 SO（2026-11-12 实测）：

| SO | 订单量 | 已出库 | 净未发 | 逐行正缺口 | 超发 |
|---|---|---|---|---|---|
| SO-26-00088 | 1,630 | 1,468 | 162 | 162 | 0 |
| SO-26-00103 | 13,348 | 8,870 | 4,478 | **4,657** | 179 |
| SO-26-00109 | 6,980 | 708 | 6,272 | **6,317** | 45 |

- 同一物料 `PK#KS0001-CMKTR-100-BLACK`：E 返回 `instock=72`、`delivered=72`；
  `Bin` 显示半成品仓 0（reserved 45）、美东 USNJ 到货仓 481。
- `WO-26-03113`：6 个菲号的缝制工序全部 Completed，质检 Job Card 全 Open、完成 0；
  `Stock Entry` 只有 `Material Consumption for Manufacture`，没有 `Manufacture` →
  `produced_qty=0` 是「未完工/未入库」，不是「可发」。
- 线上 `shipment_progress` 已能返回 `stage=shipped_in_transit`、`eta/atd/ata/dlvr`、
  `conflict_flag`，但 `signed_status_proven=false`、`receipt_source_status=not_integrated`。

## Related

- `docs/solutions/integration-issues/en-so-dn-forwarder-job-status-lookup.md` — SO→DN→货代 job→快照的查询链与字段坑
- `docs/solutions/workflow-issues/erpnext-so-closed-unshipped-and-unstarted-work-orders.md` — Closed 死单与工单状态不可信
- `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md` — 端到端履约模型与字段分层
- `supply_chain_visibility/docs/reference/en-produced-qty-vs-jobcard.md` — 工序/入库/可发三层口径
- `supply_chain_visibility/docs/reference/en-chain-cardinality.md` — 行级外键与基数
