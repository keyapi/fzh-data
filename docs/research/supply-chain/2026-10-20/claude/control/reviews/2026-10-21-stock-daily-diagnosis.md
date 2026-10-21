---
okf: v0.1
type: Review
title: 每日通途库存备份：只读诊断、逐文件对账与历史入库方案（v2）
date: 2026-10-21
reviewer: claude
status: diagnostic-only-v2
---

# 每日通途库存备份 — 诊断与入库方案 v2

> v2 按 Codex 复审意见修订：增加按 run_id 留存、批次表、同日补跑原子切换、
> 改名/冲突规则与更完整的可执行验收；纠正对 05:17 运行归属的过度断言。

## 结论

- 任务真实存在：Windows 计划任务 `FZH-TongtuStockApiDaily`，每天 **05:17**，
  执行 `D:\Work\fzh-stock-backup\run_stock_daily_backup.cmd` →
  `stock_daily_backup.py`，输出 `D:\Work\库存备份\YYYY-MM-DD\*.jsonl + manifest.json`。
- **历史只有 2 天，且 10-20 不完整**：
  - 2026-10-20：14 仓，13 完整；`美中-FZH-DANEEY-退货产品仓` URLError 10060，
    文件有 400 行部分数据，manifest 标 `complete=false`；总文件行 5,192，
    manifest 计数 4,792，差 400 正好是该仓。
  - 2026-10-21：manifest `snapshot_at=09:46:23`、`complete=true`、14/14、
    5,314 行 = 5,314 行，无重复、无坏 JSON。**可证事实**是 09:46 有一次完整运行；
    **不能**仅凭现存文件证明它“是手动补跑”或“05:17 没有产出后被覆盖”。
    `LastTaskResult=1` 来自协调器对计划任务的查询；复审环境未能独立复核该结果。
    运行归属与 05:17 根因均标为 **unknown**，不写成结论。
- 这些数据**没有进入** `D:/Work/fzh-order-store/order_store.duckdb`：
  该库的 `tongtool_stock` 只有 4 个 2026-10-21 的手动快照；R290 与 DN/WO/JC/SE
  用的是“最新库存”，不是每日历史。
- 因此：**“每日记录”已开始，但尚不可靠、未形成可分析的历史序列。**
  两天不足以做删失校正；且每日快照无法定位日内断货，零库存不等于零需求。

## 输入与方法

- 文件：`D:\Work\库存备份\2026-10-20/`、`2026-10-21/`（各 14 个 `warehouse=*.jsonl` + manifest）；
- 脚本：`D:\Work\fzh-stock-backup\stock_daily_backup.py`、`run_stock_daily_backup.cmd`；
- 日志：`D:\Work\fzh-inventory\stock_daily_backup.log`（追加，无逐行时间戳）；
- 只读：未访问通途/EN，未改脚本、未改计划任务、未写 DuckDB。

## 逐文件对账

| 日期 | manifest complete | 仓数 | 文件行 | manifest 行 | 重复 | 坏行 | 差异 |
|---|---|---:|---:|---:|---:|---:|---|
| 2026-10-20 | false | 14 | 5,192 | 4,792 | 0 | 0 | 400（退货仓部分抓取） |
| 2026-10-21 | true | 14 | 5,314 | 5,314 | 0 | 0 | 0 |

失败仓：`美中-FZH-DANEEY-退货产品仓`
（`URLError: [WinError 10060] 连接方一段时间未答复`），manifest 中该仓
`rows=null`、`complete=false`、带 `error`；文件仍有 400 行，属**部分批次**，
必须标 `batch_complete=false`，不能当完整日。

## 字段与口径

单行 JSONL 字段（实际观测）：

```json
{"goodsSku":"...","warehouseName":"...","availableStockQuantity":0,
 "intransitStockQuantity":0,"defectsStockQuantity":0,
 "waitingShipmentStockQuantity":0,"goodsIdKey":"...","warehouseIdKey":"..."}
```

- 粒度：仓库 × `goodsSku`（通途 SKU，不是 EN 物料号）。
- **没有 UOM 字段**；数量按通途当前口径，跨品类不可直接相加。
- 时间：manifest 有 `snapshot_date`、`snapshot_at`（本地时间，无时区偏移）；
  日志无逐行时间戳。入库时显式按 Asia/Shanghai 解释，并保留原始字符串。
- 来源：`tongtool erp2_stocks_stocksquery`（manifest）。
- `defects`、`waitingShipment` 与 `available` 是独立桶；不能默认相加。
- `goodsSku=TEST-1` 是测试商品，入库时标记并从分析视图排除。

## 故障诊断（只列可证事实）

- 10-20：单仓 URLError 10060；脚本对单仓失败不阻断其他仓，manifest 汇总为
  `complete=false`，退出码 1（`return 0 if manifest["complete"] else 1`）。
- 10-21 09:46：完整运行，14/14；是否由定时触发、05:17 是否另有运行，
  现有文件不足以证明（同日补跑会覆盖 manifest/JSONL）。
- 计划任务 Principal：`zhang`、`RunLevel=Limited`、`LogonType=Interactive`
  → 只在用户交互登录会话存在时运行；注销/未登录不会跑。
- 日志开头有 `✗ 缺少通途凭证`，随后有多次 `[526] 限流，等待 60s`；
  日志无时间戳，无法把这些行归属到某一次运行。**根因未证实**。
- 未查到 TaskScheduler 事件日志（查询无结果，可能是权限/日志未开启）。

## 历史入库方案 v2（本轮只设计，不落盘）

### 1. 原始留存：按 run_id，不覆盖

```
D:\Work\库存备份\runs\YYYY-MM-DD\<run_id>\
  manifest.json
  warehouse=<id>_<name>.jsonl
  run_meta.json   # run_id, scheduled_or_manual=unknown, started_at/ended_at(+08:00),
                  # exit_code, manifest_sha256, file_sha256[]
```

- `run_id` = `YYYYMMDDTHHMMSS+0800-<6位随机>`；每次运行独立目录，**同日补跑不覆盖**。
- 现有 `YYYY-MM-DD/` 兼容保留为“最近一次发布”的快捷视图，或改为软链；
  历史分析只读 `runs/`。
- 每次运行写 `run_meta.json`，包含计划任务/手动标识（若脚本无法区分，写 `unknown`）、
  起止时间（带时区）、退出码、manifest 与每个 JSONL 的 SHA256。

### 2. 表结构：运行、仓批次、发布历史分离

```sql
CREATE TABLE stock_run (
  run_id VARCHAR PRIMARY KEY,
  snapshot_date DATE,          -- Asia/Shanghai
  started_at TIMESTAMPTZ,
  ended_at   TIMESTAMPTZ,
  exit_code  INTEGER,
  manifest_sha256 VARCHAR,
  run_complete BOOLEAN,        -- 所有仓完整
  source VARCHAR,
  ingested_at TIMESTAMPTZ
);

CREATE TABLE stock_run_warehouse (
  run_id VARCHAR,
  warehouse_id VARCHAR,
  warehouse_name VARCHAR,
  rows INTEGER,
  bad_rows INTEGER,
  complete BOOLEAN,
  error VARCHAR,
  file_sha256 VARCHAR,
  PRIMARY KEY (run_id, warehouse_id)
);

CREATE TABLE stock_history (
  snapshot_date DATE,
  run_id VARCHAR,              -- 该日被选中的完整运行
  warehouse_id VARCHAR,
  warehouse_name VARCHAR,
  goods_sku VARCHAR,
  goods_id VARCHAR,
  available DOUBLE,
  intransit DOUBLE,
  defects DOUBLE,
  waiting_shipment DOUBLE,
  batch_complete BOOLEAN,      -- 该仓批次是否完整
  stockout_observed BOOLEAN,   -- 仅完整批且 available=0
  ingested_at TIMESTAMPTZ,
  PRIMARY KEY (snapshot_date, warehouse_id, goods_sku)
);

CREATE TABLE stock_id_history (  -- 改名/ID 变更，不覆盖旧名
  entity_type VARCHAR,           -- warehouse | goods
  entity_id VARCHAR,
  name VARCHAR,
  first_seen DATE,
  last_seen DATE,
  PRIMARY KEY (entity_type, entity_id, name)
);
```

- 用 `warehouseIdKey` / `goodsIdKey` 作为稳定 ID；`goodsSku`/`warehouseName` 只作展示，
  改名写入 `stock_id_history`，不覆盖历史。
- 同一 run 内 `(warehouse_id, goods_sku)` 重复且数值一致 → 去重并计数；
  **数值冲突 → 整个 run 拒绝发布**，保留原始文件并报错，不静默取一条。

### 3. 同日补跑的原子发布

1. 先写 staging（`stock_history_staging_<run_id>`），完成全部校验；
2. 选择该日“最新且 `run_complete=true`”的运行；
3. 单事务内：删除该 `snapshot_date` 的旧 published 行 → 插入新 run 行 → 更新
   `stock_run` 的 published 标记；
4. **不完整 run 永不覆盖完整 run**；若当日只有不完整 run，写入 `unknown` 批，
   不删除已有完整 published 行；
5. 反序补跑（先完整后不完整）不得让完整数据消失；需保留 published_run_id 以便审计。

### 4. 断货与未知

- `stockout_observed=true` 仅当：该仓 `complete=true`、`available=0`、
  且该 run 被发布为完整日。
- 缺失仓/失败仓/缺文件 → `unknown`，不写 0，不进入断货统计。
- `TEST-1` → `is_test=true`，默认视图排除。

## 可执行验收（离线，读现有文件/合成副本）

1. 同一 run 重复导入两次 → `stock_history` 行数不变；重复计数一致。
2. 10-20 导入 → 退货仓 400 行 `batch_complete=false`；其余 13 仓完整；
   该日不发布为完整日。
3. 10-21 导入 → 5,314 行、14 仓 `complete=true`；内容与 manifest 对账一致。
4. **完整 → 不完整** 反序补跑 → 完整 published 数据仍在，不完整 run 只留审计。
5. 不完整 → 完整 补跑 → 原子切换，旧完整行不残留。
6. 缺文件/空仓/失败仓 → `unknown`，不写 0；断货统计不包含。
7. 仓库/商品改名 → 稳定 ID 不变，`stock_id_history` 记录旧名；历史查询可追溯。
8. 同一 run 重复键数值冲突 → 整 run 拒绝发布，保留文件与错误。
9. manifest/JSONL 哈希异常 → 拒绝发布并报警。
10. 跨日补跑 → 按 `snapshot_at` 的 Asia/Shanghai 日期归属，不按导入日。
11. `TEST-1` → 标记并从分析视图排除。
12. 验收核对**内容 + 完整标志 + 哈希**，不能只比行数。

## 未决

- 05:17 定时失败的**根因**未证实；需日志加时间戳、记录每次运行的 exit/阶段，
  并按 run_id 留存 manifest，才能区分计划任务与手动补跑。
- 只有 2 天，且 10-20 不完整；不足以做删失/断货校正。
- 每日快照无法定位日内断货；后续需要订单/库存事件或更高频采样。
- `goodsSku` → EN 物料/仓库映射仍依赖 `sku_map`/`warehouse_map`，未在此任务内验证。
- 本方案未落盘、未启动任务、未访问生产；需复审通过后再实施。
