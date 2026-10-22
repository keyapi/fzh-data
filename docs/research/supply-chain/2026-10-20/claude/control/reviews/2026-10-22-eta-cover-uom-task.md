---
okf: v0.1
type: Plan
title: 10 SKU 的 ETA / Cover / UOM / 在途证据梳理（B）
date: 2026-10-22
owner: claude-worker
---

# 10 SKU 的 ETA / Cover / UOM / 在途证据梳理

## 目标

只梳理现有证据，**不估填、不外推**；明确哪些可算、哪些是 scenario、哪些是 blocker。
为扩样/预测清障，不做预测、不改生产。

## 输入（只读）

- `D:/Work/fzh-order-store/order_store.duckdb`：
  `tongtool_po`、`tongtool_po_open`、`stock_latest`、`stock_history`、
  `item_cover_stock`、`replenishment_pool`、`bom`、`bom_item`、`sku_map`、
  `three_pl_stock`、`trace_examples`（若为表）/`trace_examples.json`
- 10 个 SKU 的 trace：`D:/Work/fzh-order-store/trace_examples.json/md`
- EN 快照（只读）：`out/g1b_en_top_*.json`、`out/g1b_en_rr2.json`（仅用于订单/工单上下文，不查生产）

## 每个 SKU 输出

1. **ETA**：未结 PO 行、`will_arrive_date`/任何日期字段、来源；有/无/空。
2. **在途**：`intransit` 行、仓库、数量、与 PO 的关系（是否可逐笔关联）。
3. **Cover**：`item_cover_stock`/`replenishment_pool` 的 cover 数量、是否计入供给、假设。
4. **UOM**：BOM 行 UOM、库存/需求单位、是否需要换算；无单位的明确标 unknown。
5. **判定**：`evidence_present` / `scenario` / `blocker`，每项附字段=值与来源表。
6. **缺口**：需要谁提供什么（Jack/业务/EN/通途），不自行补数。

## 汇总

- 10 个 SKU × 四项的矩阵；blocker 清单；可用于扩样的最小条件。
- 对每个 blocker 给出“最小可验证输入”，不写“大概/估计”。

## 交付

- `control/reviews/2026-10-22-eta-cover-uom-evidence.md`
- `out/eta_cover_uom/evidence.json`（本地证据，聚合/字段值，不含原始订单明细）
- 不提交原始数据；不改 `order_store.duckdb`；不访问通途/EN；不合并 PR。

## 验收

- 10 个 SKU 全部覆盖；四项都有判定；每条证据可追溯到表/字段/行。
- 缺失就是缺失，不写 0/不猜；scenario 与 blocker 分清。
- 计数对账：SKU 数、PO 行、cover 行、BOM 行均可追溯。
- 时间盒 90 分钟；超时交缺口表。
