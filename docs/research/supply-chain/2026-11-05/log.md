---
okf: v0.1
type: Log
title: 2026-11-05/11-06 库存核对变更日志
date: 2026-11-06
---

# 变更记录

## 2026-11-13

- **官方答复**：Wayfair ticket GSCIEXE-103969 确认 GraphQL **不提供 SKU 级入仓/在途/ETA**，也没有对应权限；`inboundOrderList` 属 CGF Container Milestones 且无 SKU 级收货明细；推荐 **Partner Home CastleGate 入仓报表/导出**；`getCastleGatePurchaseOrders` 仅用于出库客户订单。API 侧 Δ 公式降为 fallback。

## 2026-11-06

- **新增**：`TT0031038K0062927` 节点核对（数据 as_of 11-05，11-06 09:06 复核）。
- **核实**：11-05 09:09:50 采购单 +91（仓库操作人，凭证 `6464013595202611050000897094`）；17:34:00 其他出库 -102（凭证 `6464013595202611050074374170`）→ 美中可用 0、在途 405。
- **核实**：通途 CG 账 133 无 +102 入库；CG 仓 11-04 起 56 行变动无该 SKU。
- **核实**：直接 CG API（snapshot）base SKU `null`（无 Castlegate 仓位）；`-2PCS` 5 套、`-3PCS` 0 套。
- **结论**：运营同事的 10/5 120 无法核实（数据最早 10/20-10/21）；91 与 120 不是同一批；CG 在途无 SKU 级来源。
- **调研（11-06）**：Wayfair CG 入仓/在途 API 逐项实测：WSA 是 CG→客户出库（SKU 级），`getCastleGatePurchaseOrders` 是客户订单；`inboundOrder` 全 null、`inboundOrderList`/BOL 权限 102、`castlegatePurchaseOrders` 上游 null。可行替代为 `ΔCG on_hand + WSA 出库` 反推收货。10-29→11-06 实测无 91/102 级别入仓。
