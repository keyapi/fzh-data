---
okf: v0.1
type: Reference
title: 全 family / 全 SKU 供应链 ETL — 方向修正
description: 从逐客户码试点转为按物料组/物料码批量的增量 ETL；事实表、幂等键、水位线与验收
date: 2026-10-21
tags: [supply-chain, etl, full-family, architecture, duckdb, erpnext]
---

# 全 family / 全 SKU 供应链 ETL — 方向修正

> 结论：**逐客户码 1,486 次查询只适合契约试点，不能作为供应链系统的主链路。**
> 主链路应改为 **按物料组/物料码批量 + 增量水位线 + 幂等事实表**；库存用通途 API 全仓快照，
> 生产/出库用 EN 单据批量抽取，3PL 用后台实盘。

## 1. 已验证：批量查询可行

只读探针（EN 生产，2026-10-21）：

```text
Sales Order Item.item_group in ("三角靠枕","三角靠枕无扣")
→ 333 行 / 56 张 SO（未加日期过滤）
```

说明不需要按 1,486 个客户码逐个查；按 **物料组** 一次可拉出整族 SO，再按日期/仓/状态过滤。
另外可按 `production_item in (item_code chunks)` 拉 WO，按 WO/SO chunks 拉 JC/SE/DN。

## 2. 目标架构（轻量、可增量）

```text
通途 API 全仓库存 ─┐
浏览器库存结存/销售报表 ├─→ 原始层 raw（JSONL/xlsx 原样归档）
EN SO/DN/WO/JC/SE ───┘        ↓
                         标准化层 staging（DuckDB/Parquet）
                              ↓
                         事实/维度层 fact/dim（幂等 upsert）
                              ↓
                         语义层 metrics（覆盖/缺货/建议）
```

### 2.1 事实表与幂等键

| 事实 | 来源 | 幂等键 |
|---|---|---|
| `float_sales_order_line` | SO + SO Item | `Sales Order Item.name` |
| `fact_delivery_note_line` | DN + DN Item | `Delivery Note Item.name` |
| `fact_work_order` | Work Order | `Work Order.name` |
| `fact_job_card` | Job Card | `Job Card.name` |
| `fact_stock_entry_line` | Manufacture SE + Detail | `Stock Entry Detail.name` |
| `fact_inventory_snapshot` | 通途 API/浏览器 | `(snapshot_date, warehouse_id, sku)` |
| `fact_in_transit` | 通途 `intransit` / PO / 头程 | `(source, doc_id, line_id, sku, eta_bucket)` |
| `fact_3pl_inventory` | Wayfair 后台手工 | `(as_of, 3pl_warehouse, sku)` |

### 2.2 增量策略

- **EN**：按 `modified`/`transaction_date`/`posting_date` 水位线拉增量；每日一次，周度全量对账。
- **SO 批量**：`item_group in (family groups)` + 日期窗口；一次拉父单，再按父单 `order_items` 展开。
- **WO/JC/SE**：按 `production_item in (item_code chunks, ≤40)`；JC/SE 按 WO chunks。
- **DN**：按 `against_sales_order in (SO chunks)` 或 `posting_date` + item group。
- **库存**：通途 API 全仓分页（13 秒/页，526 退避），每仓保存 `complete/page/hash`。
- **幂等**：所有事实表按主键 upsert；重复快照同键按 `snapshot_at` 取最新，冲突不静默 first-wins。

### 2.3 零库存 vs 缺失（必须分开）

- API 返回该 SKU/仓且数量为 0 → `observed_zero`（真的 0）。
- API 没返回该 SKU/仓 → `missing/unknown`，**不能补 0**；可能是未铺货、停售、漏拉或接口截断。
- 库存结存可能省略零库存 SKU（实测 API 比 CENTRADE 多 386 个、其中 343 个零；
  DANEEY 多 26 个、其中 25 个零），所以零库存以 API 为准，状态/别名用库存结存补。
- 建议加 `sku_presence(snapshot_date, warehouse_id, sku, presence, qty_status, source)`：
  `presence=observed|missing`，`qty_status=positive|observed_zero|bad|unknown`。

### 2.4 验收

- 每个输入行有 disposition：`used / pending / unmatched / conflict / unknown`。
- 数量守恒：SO→DN→SE、库存→覆盖、在途→实收；不把跨层累加当余额。
- 每批有 `run_id`、输入文件 hash、页数、行数、`complete`、异常清单。
- 全 family 跑通后再扩到全 SKU；全 SKU 以 `item_group`/`item` 分片，不按客户码。

## 3. 与业界做法的对齐

- **ODS → DWD/事实层 → 语义层**，不直接在 ERP 事务表上算指标。
- **增量 CDC/水位线 + 周期全量对账**，避免每天全表扫。
- **幂等 upsert + 异常队列**，重复/冲突/未知不静默丢弃。
- **事实/派生/估算/断言分层**（与 08 契约一致），LLM/报表只引用语义层。
- 这些都是供应链数据平台的基本操作；不需要重写研究，只需要把现有试点适配器升级为批量 ETL。

## 4. 下一步

1. 新增 `en_bulk_extract.py`：先跑 family 的 SO→DN→WO→JC→SE，按物料组/物料码 chunks。
2. 用 2026-04..09 全 family 重跑，输出 manifest/hash/逐行 disposition。
3. 库存继续用每日 API 全仓 JSONL；浏览器库存结存/销售报表作为对照与销量补充。
4. 全 family 验收通过后，把 `item_group` 参数扩到全品类/全 SKU。
5. WayfairCG 后台实盘/调拨归属独立 pending；不阻塞批量 ETL。
