---
okf: v0.1
type: Plan
title: 10 SKU 暂行补货行动清单（不依赖 P90）
date: 2026-10-22
owner: claude-worker
---

# 10 SKU 暂行补货行动清单

## 依据

Codex2 decision10：V0.1 冻结在 98e1c664；P90 算法交 V1；
可出**不依赖 P90** 的 10 SKU 暂行清单。供给只有总池边界，预测与 SO 重叠未证。

## 输入（只读）

固定 commit `98e1c664` 的：
- `out/replenishment_v0/evidence.json`
- `control/reviews/2026-10-22-supply-demand-replenishment-v0.md`
不得使用后续工作区改动。

## 口径

- 需求：点预测 P50（日历窗口已积分）+ 正向 live SO 两种视图：
  - D1 = P50 预测（不含 SO）
  - D2 = P50 + 正向 live SO（标注“重叠未证”）
- 供给：A 下/上、B_min/B_max；**不使用 P90，不给建议量**。
- 行动分类：
  1. `always_replenish`：即使 A 上界 / B_max 仍低于 D1，且身份/单位可核实；
  2. `depends_on_arrival`：A 与 B 结论不同，取决于 PO/在产/在途是否到货；
  3. `insufficient_evidence`：UOM/身份/Cover/重叠未证，不能下结论。
- 每项列：SKU、供需数字、分类、依据、需补什么证据、责任角色、启动条件。
- 不输出采购数量、不写“下单”；不访问生产、不改 EN/sku_map、不扩样。

## 交付

- `control/reviews/2026-10-22-replenishment-actions-v0.md`
- `out/replenishment_v0/actions.json`
- 提交固定 commit 并推送；报告计数对账（10 SKU 全覆盖）与残余未知。
