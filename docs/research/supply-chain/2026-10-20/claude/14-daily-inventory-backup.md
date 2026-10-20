---
okf: v0.1
type: Reference
title: 每日库存备份 — 现状、冲突与落库形式建议
description: 通途每日备份是浏览器导出；EN 三个通途同步任务的时刻；DuckDB/Parquet 与 EN DocType 的取舍
date: 2026-10-20
tags: [supply-chain, inventory, backup, scheduling, duckdb, erpnext]
---

# 每日库存备份 — 现状、冲突与落库形式建议

## 1. 现在是什么

| 项 | 结论 |
|---|---|
| `FZH-TongtuAutoExport-stock` | **Windows 浏览器导出**，不是通途 API |
| 实现 | `web_automation/legacy-compatible/tongtu_auto_export.py`（`tongtu.stock.export`，BROWSER_ONLY） |
| 实际产物 | `通途导入_头程运费_其他费用.xlsx`：列只有 `SKU/SKU别名`、`安全库存`、头程报关费、头程运费、其他费用；**没有 available/intransit** |
| 结论 | **它是成本/头程导入模板，不是库存数量快照**；不能当每日库存备份 |
| 触发 | 每日 **02:17**（已注册，NextRunTime 2026-10-21 02:17） |
| 首跑状态 | 手工 `--auto-login` 测试成功，生成 PL/CENTRADE/DANEEY 三个 xlsx；**内容是成本模板** |
| 历史 | 本机此前没有该任务、没有日志、没有 output/stock 文件；`stock_alert` 只写低库存行，不是全量归档 |

> 所以“没动静”不是任务挂了，而是**从未在本机注册/登录**。现在成本模板任务已注册；
> 但**库存数量**需要另走 API 备份（见 §3–§4）。

## 2. 与 EN 三个通途 API 同步任务的关系

EN 生产 `Scheduled Job Type` 实测（2026-10-20）：

| 任务 | 方法 | 时刻 |
|---|---|---|
| `order_sync.sync_multi_day_orders` | `tongtool_integration.sync.order_sync.sync_multi_day_orders` | 每日 **01:00** |
| `order_sync.daily_update_sync` | `tongtool_integration.sync.order_sync.daily_update_sync` | 每日 **02:45** |
| `package_sync.auto_sync_packages` | `tongtool_integration.sync.package_sync.auto_sync_packages` | 每日 **04:30** |

- 浏览器成本导出走通途 **网页会话**，三个同步任务走 **通途 API**；两者不共享 5 次/分钟 API 限流。
- 但 02:17 的浏览器导出如果跑过 28 分钟，会与 02:45 的订单同步在 CPU/浏览器上重叠。
- **API 库存备份**必须避开三个同步窗口；已注册 `FZH-TongtuStockApiDaily` 每日 **05:17**
  （04:30 之后），不抢 01:00/02:45/04:30 的 API 额度。
- 浏览器成本导出保持 02:17 可以接受；它只产成本模板，不产库存数量。

## 3. 推荐落库形式：DuckDB/Parquet，不是 EN Bin

| 方案 | 结论 | 理由 |
|---|---|---|
| **Parquet 日分区 + DuckDB 视图** | **推荐，长期主库** | 库存是 append-only 时间序列；按日/仓分区、不可变、易回溯；与另一条线 43 个月订单 DuckDB 可直接 join |
| EN `Bin` / `Stock Ledger Entry` | **禁止** | 会污染账务与库存账；通途库存不是 EN 事务库存 |
| EN 自定义 `Inventory Snapshot` DocType | **可选，只读展示** | 仅在需要 EN UI/审批时；存 header + 明细，不写 Bin/GL；全量日快照行数大，优先 Parquet |
| CSV/xlsx 直接当主库 | 不推荐 | 无类型、无分区、易覆盖、难做 as-of |

### 3.1 建议表结构

```sql
-- DuckDB / Parquet
CREATE TABLE inventory_snapshot (
  snapshot_date   DATE        NOT NULL,  -- 业务日
  snapshot_at     TIMESTAMP   NOT NULL,  -- 采集完成时间
  capture_start   TIMESTAMP,             -- 该仓/该批开始
  capture_end     TIMESTAMP,             -- 该仓/该批结束
  warehouse_id    VARCHAR     NOT NULL,
  warehouse_name  VARCHAR     NOT NULL,
  sku             VARCHAR     NOT NULL,
  available       DOUBLE,
  intransit       DOUBLE,
  defects         DOUBLE,
  waiting         DOUBLE,
  source          VARCHAR,               -- tongtool_api / browser_export
  complete        BOOLEAN,               -- 分页/仓是否完整
  page_no         INTEGER,
  raw_hash        VARCHAR                -- 行/页哈希，便于去重审计
);
```

Parquet 路径：

```text
data/inventory/snapshot_date=2026-10-21/warehouse=6464013595202309080001023362.parquet
data/inventory/snapshot_date=2026-10-21/manifest.json
```

`manifest.json`：每个仓的 `request_pages`、`last_page_len`、`complete`、`bad_rows`、
`duplicate_conflicts`、`captured_start/end`、文件 sha256。保留 13 个月。

### 3.2 每日作业形态

1. 取当前启用仓列表（`erp2_basedata_warehousequery`，status=1）。
2. 逐仓分页拉 `erp2_stocks_stocksquery`（pageSize 100，13 秒节流；526 退避）。
3. 写当日 Parquet 分区 + manifest；失败/不完整的仓标 `complete=false`，不写 0。
4. DuckDB 视图：

```sql
CREATE VIEW v_inventory_latest AS
SELECT * FROM read_parquet('data/inventory/**/*.parquet')
QUALIFY row_number() OVER (PARTITION BY warehouse_id, sku ORDER BY snapshot_at DESC) = 1;

CREATE VIEW v_inventory_asof AS
SELECT * FROM read_parquet('data/inventory/**/*.parquet')
WHERE snapshot_date <= ?;
```

## 4. 放哪台服务器

| 选项 | 可行性 | 建议 |
|---|---|---|
| **本机 Windows 任务（当前）** | 已注册成本模板任务 02:17；**API 库存任务 `FZH-TongtuStockApiDaily` 05:17**；PC 关机/未登录不跑 | 过渡可用；不适合长期唯一来源 |
| **EN 测试服务器 `ensh.vilavi.cn`** | Linux + Python/uv；需能出网到 `mcp.tongtool.com`；可写 NAS/本地 Parquet | **推荐试点**：只跑 API 快照，写 Parquet/JSONL，不写 EN 数据库；先确认出网与磁盘 |
| EN 生产服务器 | 能跑但会与订单同步抢 API 额度/资源 | 不建议把每日全量库存快照放生产；除非单独配额/独立进程 |
| 独立常开 Linux 小机/cron | 最干净 | **长期推荐**：与 EN 解耦，DuckDB/Parquet 落 NAS |

### 4.1 已注册的 API 库存任务

- 任务名：`FZH-TongtuStockApiDaily`
- 触发：每日 **05:17**
- 脚本：`stock_daily_backup.py`（本目录）
- 输出：`D:/Work/库存备份/YYYY-MM-DD/warehouse=<id>_<name>.jsonl` + `manifest.json`
- 日志：`D:/Work/库存备份/stock_daily_backup.log`
- 说明：按启用仓全量分页，13 秒/页；526 退避；`complete=false` 不写 0。
- 过渡期任务指向 worktree；合并后应把脚本移到主仓库并重注册任务。

### 4.1 如果放 EN 测试服务器

- 只部署 `stock_daily_backup.py`（API 版）+ cron/systemd timer；输出到 NAS 挂载或 `/opt/fzh-data/inventory`。
- **不写** EN 的 `Bin`、`Stock Ledger Entry`；如确需 EN 内查看，再建只读 `Inventory Snapshot` DocType。
- 排程避开 01:00 / 02:45 / 04:30；建议 **03:17**（或 00:17）。
- 首次先手工跑一天，核对 `manifest.complete=true`、仓数、总行数，再开 timer。

## 5. 与订单 DuckDB 的关系

另一条线把 43 个月 GSheet 订单落到本地 DuckDB；每日库存用同一套 `snapshot_date` / `sku` 维度，
可直接：

```sql
SELECT d.snapshot_date, d.sku, d.available, d.intransit, o.outbound_qty
FROM v_inventory_latest d
LEFT JOIN order_monthly o USING (sku);
```

- 库存是 **as-of 快照**，订单是 **出库/消耗**；不要用 EN Bin 或赛狐库存替代。
- 平台库存（<=2 视为无货）另表记录，标 `censored/manual_low`，不要混进通途 `available`。

## 6. 仍未完成

- **API 库存备份已做冒烟测试**：`stock_daily_backup.py --warehouses 美东-CENTRADE --max-pages 2`
  返回 2 页/200 行/`complete=false`（预期，因 max-pages 截断），JSONL+manifest 正常落盘。
- **全量 API 备份已完成一次**（2026-10-20）：CENTRADE 2,072 行/21 页、DANEEY 1,024/11、
  PL 1,369/14、WayfairCG-Cranbury 92/1，均 `complete=true`；
  DANEEY 退货仓一次连接超时，单仓 `complete=false`，整体 manifest `complete=false`、命令 exit 1。
  主仓完整，可用于 G1b 覆盖；超时仓下次重跑补齐。
- **G1b 覆盖已用完整快照重算**：USNJ 5.86、USTX 5.48、PL 10.24 个月（含在途名义）；
  131 个 branch×SKU 有需求无供给、194 个 <2 月、127 个 unknown（3PL/退货仓不计缺口）。
- **浏览器成本导出**：手工测试已生成 PL/CENTRADE/DANEEY 三个 `通途导入_头程运费_其他费用.xlsx`；
  它只产成本模板，不是库存数量，不能替代 API 备份。
- EN 测试服务器出网/磁盘/uv 环境未验证；需技术确认后再部署。
