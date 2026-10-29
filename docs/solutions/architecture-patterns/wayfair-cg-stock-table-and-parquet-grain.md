---
okf: v0.1
type: Reference
title: Wayfair CG 库存表与 Parquet 粒度设计——总量与分仓怎么放
date: 2026-10-29
category: architecture-patterns
module: wayfair-api-proxy
problem_type: architecture_pattern
component: data-pipeline
severity: medium
applies_when:
  - "设计渠道库存快照表：既要看总量又要保留分仓明细"
  - "决定 Parquet 该一张表混合粒度还是按粒度拆文件"
  - "排查库存总量与分仓合计不一致、或 SUM 结果翻倍"
tags: [wayfair, castlegate, erpnext, parquet, data-model]
---

# Wayfair CG 库存表与 Parquet 粒度设计

## Context

EN 的 `tongtool_integration` 每天 07:20 拉 Centrade CastleGate 库存。业务真正关心的是
**每个 SKU 的 CG 总数量**，分仓明细只用于下钻。上游 1007 个 supplier part 中只有 104 个
有 CG 库存位置，其余 903 个 `castleGate=null`。最初把“无位置”的 part 也写成 `CG:sku`
占位行，导致库存表 72% 是空行；后来又差点为“总计”和“分仓”各建一个 DocType。

## Guidance

### 一张 DocType，两种粒度

`Wayfair CG Stock Latest` 同时保存：

- **总计行**：每个有 CG 位置的 SKU 一行，`warehouse_id = CG`、
  `warehouse_name = CastleGate 合计`，数量为各仓合计。
- **分仓行**：每个 SKU × 仓一行，`warehouse_id = 323xxx`，仓名来自映射表。

`stock_key = {account}:{warehouse_id}:{sku}`；总计行即 `{account}:CG:{sku}`。
唯一键带账号，为多账号留口子；真实仓 ID 都是数字，不会与 `CG` 冲突。

查询约定：

```text
总数：warehouse_id = 'CG'
分仓：warehouse_id != 'CG'（或指定仓）
任何 SUM/聚合前必须先限定粒度 —— 两种行混加会翻倍。
```

不做单独的分仓 DocType，也不再新增 `scope` 字段；`warehouse_id='CG'` 就是判别符。
前提是**必须在文档和列表视图里讲清楚**，否则后来者容易直接 `SUM(on_hand)`。

### 无 CG 位置的 part 进目录，不进库存表

`Wayfair CG Part` 保存全部 supplier part（约 1000 行）：`wayfair_sku`、
`has_cg_position`、`warehouse_count`、`first_seen/last_seen`。
`castleGate=null` 只说明“Wayfair 有这个 part，但没有 CG 库存位置”，
既不是 0 库存，也不是汇总行。需要查“在不在 Wayfair / 对应哪个 Wayfair SKU”时查目录。

### 仓库名靠事件积累

`Wayfair CG Warehouse` 保存 `warehouseId → name`，来源是调拨/变动记录（上游没有仓库清单
接口）。代理提供 `GET /v1/accounts/{account}/inventory/warehouses`（回看 3 年调拨，缓存 6h），
每日变动同步顺带刷新；新仓在第一次调拨/盘点事件后出现。

### Parquet 一表一粒度

```text
wayfair_cg_stock_total.parquet       每个 SKU 一行（含 account/sku/四项数量）
wayfair_cg_stock_warehouse.parquet   每个 SKU×仓一行（含仓名）
```

- 拆开的好处：从结构上避免重复计数；两张表 schema 各自干净；按 `snapshot_date` 追加、
  按维度过滤/join 都直接；BI/Excel/Pandas 读取无需过滤。
- 旧的 `wayfair_cg_stock.parquet`（v1，混合分仓+历史 CG 占位）保留归档，不再写入。
- 嵌套 `list<struct>` 技术上可行，但查仓要先 `UNNEST`，BI 支持参差，不适合分析表。

### 总计怎么算

对分仓行求和；上游外层 `castleGate` 与逐仓合计已实测完全相同（1007 个 part，0 处不一致），
所以客户端求和无需改代理。严格处理 null：任一参与求和的值为 null，总计记为 null +
`*_missing=1`，**不把 null 当 0**。

### 发布与对账

- DocType：`delete` + `bulk_insert` 放在同一事务，最后一次 commit；失败回滚保留上一批。
- Parquet：先写 `*.tmp.parquet`，成功后原子替换，并保留 `*.prev.parquet`。
- Run 记 `row_count`（总计+分仓）、`sku_count`（有 CG 位置的 SKU）、`warehouse_count`、
  `part_count`、`no_cg_position_parts`，五者能互相对账。

## Why This Matters

- 混合粒度最危险的不是存储，而是下游把两种行一起 SUM，导致库存翻倍且不报错；
- 为总计单独建表会持续增加 DocType/字段，而业务真正需要的只是“过滤一次”；
- 把 `castleGate=null` 写成 0 会制造假断货，写进库存表则制造 72% 的空行噪声；
- Parquet 按粒度拆文件让“用错粒度”变成显式选择，而不是隐含错误。

## When to Apply

- 新增渠道库存快照（Wayfair / Amazon / 其他海外仓）时；
- 需要在同一张表里放“总量 + 明细”两种粒度时；
- 设计 Parquet 历史层，决定单文件混合还是按粒度拆分时。

## Examples

Frappe 列表过滤：

```text
# 总数
[["Wayfair CG Stock Latest","warehouse_id","=","CG"]]
# 分仓
[["Wayfair CG Stock Latest","warehouse_id","!=","CG"]]
```

DuckDB：

```sql
-- 每个 SKU 的 CG 总计（已拆文件，无需过滤）
select sku, on_hand, available, reserved, unavailable
from read_parquet('wayfair_cg_stock_total.parquet')
where snapshot_date = current_date;

-- 某仓明细
select sku, warehouse_name, on_hand
from read_parquet('wayfair_cg_stock_warehouse.parquet')
where snapshot_date = current_date and warehouse_id = '323004';
```

## Related

- [Wayfair CastleGate API 契约与分页坑](../integration-issues/wayfair-castlegate-inventory-api.md)
- [ERPNext 每日同步的时区与批量写入坑](../developer-experience/erpnext-wayfair-sync-timezone-pitfalls.md)
- `wayfair-api-proxy/docs/api.md` — 仓库名接口
- `tongtool_integration/docs/wayfair_cg_stock_sync.md` — EN 侧配置、调度与字段
