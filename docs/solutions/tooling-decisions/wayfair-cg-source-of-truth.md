---
okf: v0.1
type: Reference
title: Wayfair CG 库存以后台 AllInventoryExport 为准，不用通途 CG
date: 2026-10-27
category: tooling-decisions
module: wayfair_cg
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - "要用 Wayfair CG/Castlegate 库存做补货或断货判断"
  - "发现通途 WayfairCG-* 的数量与 Wayfair 后台不一致"
tags: [wayfair, castlegate, inventory, tongtool, data-source]
---

# Wayfair CG 库存以后台 AllInventoryExport 为准

## Context

通途里有 `WayfairCG-Cranbury/Perris/Romeoville` 三个 CG 仓，但运营反馈数量不准。2026-10-23 从 Wayfair 后台导出的 `AllInventoryExport` 与通途同日数据对比：

- 通途：Cranbury 92 SKU / 860 件；Perris 4 / 0；Romeoville 2 / 0。
- Wayfair：Castlegate **103 SKU / 315 仓-SKU / 401 件**，覆盖 **9 个 Castlegate 仓**（Cranbury、Jacksonville、McDonough、Lancaster、Romeoville、Aberdeen、Lathrop、Perris、Port Wentworth）。
- SKU 交集只有 **56**；Wayfair 独有 47、通途独有 36。

结论：**通途 CG 不能作为可信来源**。

## Guidance（本学习沉淀的做法）

1. **CG 用 Wayfair 后台的 `AllInventoryExport_YYYY-MM-DD.csv`**，不用通途 `WayfairCG-*`。
2. **只看 `Warehouse Type = Castlegate`**；`Dropship` 行是公司自有 NJ/TX 仓，不是 CG。
3. **按 SKU 汇总所有 Castlegate 仓**，不按单仓细分——CG 像 FBA 多仓，业务只关心一个 SKU 的总可用/在库。
4. `Part Number` 就是通途 SKU，可直接 join（大小写不敏感）。
5. 这是**单日快照**；`In Stock Update` 是每行的更新时间（跨度数月），不是导出时间。后续需要运营定期导出（每周/每天）或走 Wayfair API。
6. 入库表：`wayfair_cg.inventory`（明细，仅供审计）+ `wayfair_cg.sku_daily`（按 SKU 汇总：`available_castlegate` / `in_stock_castlegate` / `order_past_90d` / `castlegate_warehouses`）。

## Why This Matters

- 用通途 CG 会低估/高估 SKU 数（103 vs 98）和数量（401 vs 860），补货和断货判断都会错。
- 按单仓细分会把同一个 SKU 拆散，业务上无意义；按 SKU 汇总才是可用口径。
- 把 Dropship 行混进 CG 会把公司自有仓的量算进 CG。

## When to Apply

- 计算 Wayfair CG 可售/补货时；
- 发现通途 CG 与后台对不上时；
- 设计 CG 库存导入/对账时。

## Examples

```sql
-- CG 总可用（按 SKU，所有 Castlegate 仓）
SELECT part_number, available_castlegate, in_stock_castlegate, castlegate_warehouses
FROM wayfair_cg.sku_daily
WHERE export_date = DATE '2026-10-23'
ORDER BY available_castlegate DESC;
```

```sql
-- 只取 Castlegate 明细
SELECT * FROM wayfair_cg.inventory
WHERE warehouse_type = 'Castlegate';
```

## Related

- `docs/research/2026-10-26-pengjian-inventory-backup-review.md`
- `docs/research/2026-10-23-stockout-censoring-model.md` — §1.5
- 脚本 `D:/Work/fzh-order-store/wayfair_cg_ingest.py`（不入公开仓库）
