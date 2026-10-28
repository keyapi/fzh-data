---
okf: v0.1
type: Explanation
title: EN 接入建议（CG 库存备份）
description: CG 快照如何落到 EN/DuckDB；为什么不复用 stock_latest；原始层与统一层的分阶段设计
tags: [wayfair, en, duckdb, parquet, inventory, integration]
---

# EN 接入建议（CG 库存备份）

## 先厘清现有资产

- `stock_latest` / `stock_history` / `stock_run` 在 **本机 DuckDB**
  `D:/Work/fzh-order-store/order_store.duckdb`，不是 ERPNext DocType。
- 通途每日备份是 `D:\Work\库存备份\YYYY-MM-DD\warehouse=<id>_<name>.jsonl`
  + `manifest.json`，由通途 API 拉取。
- 因此 CG 不需要新建 ERPNext DocType；应沿用 DuckDB + 每日原始文件的分析模式。
  ERPNext 的 Stock Ledger 记录的是 EN 自己的出入库，不能承载 Wayfair 外部库存。

## 核心建议：原始层先独立，统一层后做

**不要直接把 CG 写进 `stock_latest`。** 原因：

1. 仓库语义不同：CG 是 Wayfair 履约仓（NJ/CA/PA/GA…），不是通途的美东/美中仓；
2. SKU 码空间不同：CG 的 `supplierPartNumber`（如 `C/…-wow`、`OLD_…`）需要与
   EN 物料、通途 SKU 单独建映射；
3. 数量口径不同：CG 有 `on_hand`、`available`、`reserved`、`unavailable`，
   且 `null` 表示上游未返回，不能当 0；
4. 直接混入会污染现有下单决策模型，且无法回滚。

推荐分三层：

```text
原始层（先做）      D:\Work\库存备份\wayfair-cg\YYYY-MM-DD\centrade.jsonl + manifest.json
分析层（先做）      DuckDB: cg_stock_run / cg_stock_latest / cg_stock_history
统一层（后做）      cg_sku_map + cg_warehouse_dim → inventory_unified 视图
```

## 原始层

- 路径与通途分开，避免混目录：`D:\Work\库存备份\wayfair-cg\YYYY-MM-DD\centrade.jsonl`
- 一行一个仓位；保留 API 原样字段（`sku`、`wayfair_sku`、`warehouse`、`on_hand`、
  `available`、`reserved`、`unavailable`）。
- `manifest.json` 至少包含：

```json
{
  "snapshot_date": "2026-10-28",
  "account": "centrade",
  "run_id": "…",
  "fetched_at": "2026-10-28T07:00:03Z",
  "rows": 1255,
  "distinct_skus": 1007,
  "warehouses": 11,
  "null_on_hand": 904,
  "null_available": 904,
  "sha256": "…",
  "complete": true,
  "source": "wayfair-api-proxy"
}
```

先保原始、不强行和通途统一格式；后续口径确定后可重放，不必重新拉 API。

## 分析层（DuckDB）

镜像现有 `stock_*` 的用法，但独立命名：

- `cg_stock_run`：`run_id, snapshot_date, fetched_at, rows, distinct_skus, warehouses,
  null_on_hand, null_available, complete, sha256`
- `cg_stock_latest`：每 `(account, sku, warehouse)` 最新一行；
  `snapshot_date, run_id, account, sku, wayfair_sku, warehouse_id, warehouse_name,
  on_hand, available, reserved, unavailable`
- `cg_stock_history`：按日追加同一结构；只追加完整批次。
- 不完整批次：只写 `cg_stock_run(complete=false)`，**不覆盖 latest/history**。

## 通途 `stock_latest` 里的 CG 仓（2026-10-28 实测）

现有 DuckDB `stock_latest` **确实包含** CG 仓，但只是部分：

- `WayfairCG-Cranbury仓`：92 个 SKU
- `WayfairCG-Perris仓`：4 个
- `WayfairCG-Romeoville仓`：2 个

同一天 Wayfair API 的 Cranbury（warehouse 323004）有 103 行，全量 1255 行 / 11 仓。
即通途只覆盖了 CG 的一小部分 SKU/仓。

与 Wayfair Cranbury 逐 SKU 对比（去掉 `OLD_` 前缀后）：

- 交集 76 个；Wayfair 独有 27，通途独有 16；
- 其中 45 个完全相同；75/76 满足“通途 >= Wayfair 在库”（通途备份更早，方向合理）；
- 中位数差异 0，但均值 +4.36，最大 +104——存在明显陈旧/偏高；
- 命名还有 `-WF` 后缀、`OLD_` 前缀等差异；`sku_item` 覆盖 Wayfair 76/103、通途 92/92。

结论：**通途 CG 数据不能作为权威源**。它覆盖不全、部分严重偏离，且码空间未完全对齐。
可能原因：CG 仓由人工/旧流程维护、同步不全、备份时点更早。

使用规则：

1. CG 库存以 Wayfair API 快照为准；
2. 计算“通途自有库存”时排除 `WayfairCG-*` 仓，避免与 Wayfair 数据重复计数；
3. 通途 CG 行只作历史参考/异常告警（例如与 Wayfair 偏差超过阈值时提示同步问题）；
4. 统一层按 EN 物料码归并，不以原始 SKU 直接相加。

## 统一层（后续，另一个对话）

- `cg_warehouse_dim`：`warehouse_id, warehouse_name, region_us`。
  先把 NJ/PA/GA 等映射到美东、CA/中西部映射到美中/美西；映射需业务确认，不猜。
- `cg_sku_map`：`supplier_part_number, wayfair_sku, en_item_code, tongtool_sku`。
  现有 `sku_item` 只覆盖通途↔EN，不覆盖 CG 的 `C/…-wow`、`OLD_…` 码。
- `inventory_unified`：按 `(en_item_code, region_us, warehouse)` 合并
  `source in ('tongtool','wayfair_cg')`；在映射与区域确认前不建，避免错误汇总。

## 库存变动（Transactions）

EN 已有通途库存操作记录的每日备份，可同构：

- 原始：`D:\Work\库存备份\wayfair-cg-txn\YYYY-MM-DD\centrade.jsonl`
- 字段：`event_date, adjustment_type, sku, quantity, warehouse_id, warehouse_name, description`
- 分析表：`cg_stock_txn`（按 `run_id + event_date + sku + warehouse_id + quantity` 去重）。
- CG 接口的 `page` 是 **0 索引**，按日期增量拉取即可，不要拉全历史重跑。

## 拉取时间与网络

- 快照：北京 07:00 生成；EN 07:20 后拉 `GET /v1/accounts/centrade/inventory/snapshot`。
- 变动：可同批或在 07:20 后按日期区间拉取。
- 网络：公网 HTTPS（推荐给 EN 与同事）或 Tailscale；SSH 隧道仅作应急。
- 每次拉取用独立 key，权限只给 `inventory:snapshot:read` / `inventory:transactions:read`。

## 不要做的事

- 不要把 CG 行直接塞进 `stock_latest` 或当成通途仓库。
- 不要把 `null` 可售写成 0。
- 不要在 SKU/区域映射确认前做跨源合计。
- 不要用不完整批次更新 latest 或进入下单决策。
