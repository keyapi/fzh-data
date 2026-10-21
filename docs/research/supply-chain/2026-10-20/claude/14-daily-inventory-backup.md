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
| 原始库存 | **`web_automation/downloads/*_库存结存清单*.xlsx`**；每次运行再合并为 `output/通途合并库存结存清单*.xlsx`（19 列，含 SKU/仓库/可用/在途/待发/故障品/成本） |
| 派生成本模板 | `output/*_通途导入_头程运费_其他费用.xlsx`（SKU/安全库存/头程费用），**只是派生文件** |
| 结论 | **浏览器导出本身是有效的库存结存备份**；成本模板不是唯一产物 |
| 触发 | 每日 **02:17**（已注册） |
| 2026-10-21 首跑 | **成功**：4/6 仓导出，2 个空退货仓跳过；合并 **4,575 行**；日志 `status=READY reason=success` |
| 登录 | 使用 `chrome-profile`，02:17 无弹窗；`TONGTU_USER/PASSWORD` 在 `fzh-web-automation/.env`，两个浏览器脚本已加载该路径，cookie 过期可走 ddddocr 自动登录 |

> 更正：之前说“浏览器导出只有成本模板”不完整——`downloads/` 有原始库存结存，
> `output/` 同时有合并库存和派生成本模板。浏览器导出可以作每日库存备份；
> 但它依赖 Windows 浏览器会话，服务器化不如 API。

### 1.1 库存结存 vs 销售及库存报表 vs API

| 口径 | 行数 | family SKU | 含销量 | 含库存 | 含状态/别名 | 结论 |
|---|---:|---:|---|---|---|---|
| 库存结存（浏览器合并） | 4,575 | 1,527 | 否 | available/intransit/waiting/defects | 是 | **完整库存备份首选** |
| 销售及库存报表（浏览器） | 1,954 | 568 | 7/15/30/90 天 | available/waiting/intransit（无 defects） | 是 | **销量/周转搭档，不是完整库存** |
| 通途 API 全仓 | 5,192（含其他仓） | 1,140（三主仓） | 否 | available/intransit/defects/waiting | 否 | 服务器化首选；零库存 SKU 更全 |

- 库存结存 vs 销售报表：961 个 family 键只在库存结存、2 个只在销售报表；
  67 个数量差异，主要是 `waiting`（库存结存有值、销售报表为 0）。**销售报表不能替代库存结存。**
- 库存结存 vs API：PL 完全一致（1,369 行）；CENTRADE 1,686 vs 2,072、DANEEY 998 vs 1,024，
  **API 多出的 386/26 个 SKU 中 343/25 个是零库存**——库存结存会漏零库存 SKU，API 更全；
  重叠 SKU 数量基本一致；DANEEY 退货仓 522 vs API 400（API 那次超时不全）。
  API 无状态/别名，库存结存有；建议 API 数量 + 库存结存状态/别名合并。
- **建议**：每日归档 **库存结存合并文件 + 销售及库存报表**；如需服务器化，再加 API 全仓 JSONL。
  只用一份时：库存用库存结存，销售/周转用销售报表。
- **“API 1,140”是 family/三主仓口径**，不是 API 只取了三个仓：2026-10-21 API 实际覆盖
  CENTRADE/DANEEY/DANEEY 退货/PL/WayfairCG 5 仓/多渠道/大件/星链等所有启用仓；
  1,140 是过滤 family 客户码并只取三主仓后的唯一 SKU 数。

## 2. 与 EN 三个通途 API 同步任务的关系

EN 生产 `Scheduled Job Type` 实测（2026-10-20）：

| 任务 | 方法 | 时刻 |
|---|---|---|
| `order_sync.sync_multi_day_orders` | `tongtool_integration.sync.order_sync.sync_multi_day_orders` | 每日 **01:00** |
| `order_sync.daily_update_sync` | `tongtool_integration.sync.order_sync.daily_update_sync` | 每日 **02:45** |
| `package_sync.auto_sync_packages` | `tongtool_integration.sync.package_sync.auto_sync_packages` | 每日 **04:30** |

- 浏览器成本导出走通途 **网页会话**，三个同步任务走 **通途 API**；两者不共享 5 次/分钟 API 限流。
- 但 02:17 的浏览器导出如果跑过 28 分钟，会与 02:45 的订单同步在 CPU/浏览器上重叠。
- 浏览器库存导出 02:17 已成功（4/6 仓，合并 4,575 行）；它同时产成本模板。
- **库存 API 备份**已改为每日 05:17（04:30 之后），避开三个同步窗口。

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
| **本机 Windows 任务（当前）** | 浏览器库存+成本任务 02:17；**API 库存任务 `FZH-TongtuStockApiDaily` 05:17**；PC 关机/未登录不跑 | 过渡可用；不适合长期唯一来源 |
| **EN 测试服务器 `ensh.vilavi.cn`** | Linux + Python/uv；需能出网到 `mcp.tongtool.com`；可写 NAS/本地 Parquet | **推荐试点**：只跑 API 快照，写 Parquet/JSONL，不写 EN 数据库；先确认出网与磁盘 |
| EN 生产服务器 | 能跑但会与订单同步抢 API 额度/资源 | 不建议把每日全量库存快照放生产；除非单独配额/独立进程 |
| 独立常开 Linux 小机/cron | 最干净 | **长期推荐**：与 EN 解耦，DuckDB/Parquet 落 NAS |

### 4.1 已注册的 API 库存任务

- 任务名：`FZH-TongtuStockApiDaily`
- 触发：每日 **05:17**
- 任务 action：`D:\Work\fzh-stock-backup\run_stock_daily_backup.cmd`（**ASCII 路径**；
  脚本/`tongtool_api`/`.env` 已复制到该目录，避免 Task Scheduler 对中文路径编码错误）
- 输出：`D:\Work\库存备份\YYYY-MM-DD\warehouse=<id>_<name>.jsonl` + `manifest.json`
  （另有 ASCII junction `D:\Work\fzh-inventory` 指向同一目录）
- 日志：`D:\Work\库存备份\stock_daily_backup.log`
- 说明：按启用仓全量分页，13 秒/页；526 退避；`complete=false` 不写 0。
- **2026-10-21 05:17 首跑失败**：旧任务 action 含中文路径，Task Scheduler 存储为乱码，
  命令未执行；已把 wrapper 移到 `D:\Work\fzh-stock-backup` 并重注册。
- 2026-10-21 09:2x 手工补跑，**09:46 完成 `complete=True`**：
  CENTRADE 2,072/21、DANEEY 1,024/11、DANEEY 退货仓 522/6、PL 1,369/14、
  WayfairCG-Cranbury 92、Perris 4、Romeoville 2；空退货仓 0 行按 complete 跳过。
  次日 05:17 起自动运行。

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
- 全 family/全 SKU 的批量 ETL 方向见 [15-full-family-etl.md](15-full-family-etl.md)：
  按物料组/物料码批量 + 水位线 + 幂等事实表，不逐客户码查。

## 6. 仍未完成

- **2026-10-21 API 补跑完成**：`D:\Work\库存备份\2026-10-21\manifest.json` `complete=True`；
  CENTRADE 2,072/21、DANEEY 1,024/11、DANEEY 退货仓 522/6、PL 1,369/14、
  WayfairCG-Cranbury 92/1、Perris 4、Romeoville 2；次日 05:17 自动。
- **浏览器 02:17 首跑成功**：4/6 仓，2 个空退货仓跳过，合并 4,575 行；
  `downloads/` 原始库存 + `output/通途合并库存结存清单` + 成本模板。
- **销售及库存报表已导出**：1,954 行/8 仓；family 568，不能替代库存结存（1,527）。
- **API 全量备份（2026-10-20）**：CENTRADE 2,072/21、DANEEY 1,024/11、PL 1,369/14、
  WayfairCG-Cranbury 92/1；DANEEY 退货仓一次连接超时，主仓完整。
- **G1b 覆盖已用完整快照重算**：USNJ 5.86、USTX 5.48、PL 10.24 个月（含在途名义）；
  129 观测零供给 / 2 missing / 192 <2 月 / 127 unknown（missing 不记 0）。
- **DANEEY 退货仓超时原因**：2026-10-20 18:06 全量跑，不在 01:00/02:45/04:30 的 QDY/通途
  API 同步窗口内；是到 `mcp.tongtool.com` 的 **TCP 连接超时**（WinError 10060），不是同步任务抢占。
  2026-10-21 09:2x 补跑该仓已成功（160KB JSONL）；脚本已加 3 次网络重试（10/20s）。
- EN 测试服务器出网/磁盘/uv 环境未验证；需技术确认后再部署。
