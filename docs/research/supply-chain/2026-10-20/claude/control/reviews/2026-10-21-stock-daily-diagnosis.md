---
okf: v0.1
type: Review
title: 每日通途库存备份：只读诊断、逐文件对账与历史入库方案（v3）
date: 2026-10-21
reviewer: claude
status: diagnostic-only-v3
---

# 每日通途库存备份 — 诊断与入库方案 v3

> v3 按 Codex 第二轮复审修订：不可覆盖封存、稳定 ID、范围/全量完整分离、
> 同日多 run 规则与发布指针、空仓≠未知、可运行验收入口，并降级 05:17 表述。

## 结论

- 任务真实存在：Windows 计划任务 `FZH-TongtuStockApiDaily`，每天 **05:17**，
  执行 `D:\Work\fzh-stock-backup\run_stock_daily_backup.cmd` →
  `stock_daily_backup.py`，输出 `D:\Work\库存备份\YYYY-MM-DD\*.jsonl + manifest.json`。
- **历史只有 2 天，且 10-20 不完整**：
  - 2026-10-20：14 仓，13 完整；`美中-FZH-DANEEY-退货产品仓` URLError 10060，
    文件 400 行部分数据，manifest `complete=false`；总文件行 5,192，
    manifest 计数 4,792，差 400 正好是该仓。
  - 2026-10-21：manifest `snapshot_at=09:46:23`、`complete=true`、14/14、
    5,314 行 = 5,314 行，无重复、无坏 JSON。可证事实是 09:46 有一次完整运行；
    **05:17 是否运行、结果如何，待证**（同日文件可能被覆盖）。
    `LastTaskResult=1` 仅来自协调器查询，复审环境未独立复核。
- 这些数据**没有进入** `D:/Work/fzh-order-store/order_store.duckdb`：
  `tongtool_stock` 只有 4 个 2026-10-21 手动快照；R290 与 DN/WO/JC/SE
  用的是“最新库存”，不是每日历史。
- 因此：**“每日记录”已开始，但尚不可靠、未形成可分析的历史序列。**
  两天不足以做删失校正；每日快照无法定位日内断货，零库存不等于零需求。

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
（`URLError: [WinError 10060]`），manifest 中 `rows=null`、`complete=false`、
带 `error`；文件仍有 400 行，属**部分批次**，不能当完整日。

## 字段与口径

单行 JSONL 字段（实际观测）：

```json
{"goodsSku":"...","warehouseName":"...","availableStockQuantity":0,
 "intransitStockQuantity":0,"defectsStockQuantity":0,
 "waitingShipmentStockQuantity":0,"goodsIdKey":"...","warehouseIdKey":"..."}
```

- 粒度：仓库 × 通途 `goodsSku`；**无 UOM 字段**，跨品类不可相加。
- 时间：manifest 的 `snapshot_date/snapshot_at` 为本地时间、无时区偏移；
  入库按 Asia/Shanghai 解释，同时保留原始字符串。
- `defects`、`waitingShipment`、`available` 是独立桶，不能默认相加。
- `goodsSku=TEST-1` 是测试商品，`is_test=true`，默认视图排除。

## 故障诊断（只列可证事实）

- 10-20：单仓 URLError 10060；单仓失败不阻断其他仓；manifest `complete=false`，
  脚本退出码 1（`return 0 if manifest["complete"] else 1`）。
- 10-21 09:46：完整运行，14/14；**05:17 是否运行、是否被 09:46 覆盖，待证**。
- 计划任务 Principal：`zhang`、`RunLevel=Limited`、`LogonType=Interactive`
  → 只在用户交互登录会话存在时运行；注销/未登录不会跑。
- 日志有 `✗ 缺少通途凭证` 与多次 `[526] 限流`；无时间戳，不能归属到某次运行；
  **05:17 的根因待证**，不写成结论。
- 未查到 TaskScheduler 事件日志（可能是权限/日志未开启）。

## 历史入库方案 v3（本轮只设计，不落盘）

### 1. 不可覆盖封存（脚本改动，实施阶段才做）

```
D:\Work\库存备份\runs\<snapshot_date>\<run_id>\
  manifest.json
  warehouse=<id>_<name>.jsonl
  run_meta.json
  .sealed            # 最后写入；含全部文件 SHA256 与 manifest SHA256
```

- `run_id = YYYYMMDDTHHMMSS+0800-<6位随机>`；每次运行独立目录，**同日补跑不覆盖**。
- `run_meta.json`：`run_id, snapshot_date, started_at/ended_at(+08:00), exit_code,
  trigger`（无法区分时写 `unknown`）、`manifest_sha256`、`files[{path,sha256,rows}]`、
  `warehouse_scope[]`、`error`。
- **异常退出也要写 run_meta**（try/finally），`sealed=false`，保留已完成仓文件。
- `.sealed` 是原子封存标记；没有 `.sealed` 的 run 不进入发布流程。
- 现有 `YYYY-MM-DD/` 两天作为 **legacy** 导入：`source=legacy`，
  用当前文件计算 SHA256 写入 `stock_run`；不重写原文件。
- 发布快捷视图可保留为 `latest/` 软链，但分析只读 `runs/`。

### 2. 表结构（稳定 ID）

```sql
CREATE TABLE stock_run (
  run_id VARCHAR PRIMARY KEY,
  snapshot_date DATE,
  started_at TIMESTAMPTZ, ended_at TIMESTAMPTZ,
  exit_code INTEGER, trigger VARCHAR,
  manifest_sha256 VARCHAR,
  scope_complete BOOLEAN,     -- 请求的仓集合全部完整
  run_complete BOOLEAN,       -- 全量启用仓集合全部完整
  source VARCHAR,             -- scheduled | manual | legacy | unknown
  sealed BOOLEAN,
  ingested_at TIMESTAMPTZ
);

CREATE TABLE stock_run_warehouse (
  run_id VARCHAR, warehouse_id VARCHAR, warehouse_name VARCHAR,
  rows INTEGER, bad_rows INTEGER, complete BOOLEAN, error VARCHAR,
  file_sha256 VARCHAR,
  PRIMARY KEY (run_id, warehouse_id)
);

CREATE TABLE stock_history (
  snapshot_date DATE, run_id VARCHAR,
  warehouse_id VARCHAR, goods_id VARCHAR,
  goods_sku VARCHAR, warehouse_name VARCHAR,  -- 展示用，不参与键
  available DOUBLE, intransit DOUBLE, defects DOUBLE, waiting_shipment DOUBLE,
  batch_complete BOOLEAN, is_test BOOLEAN,
  stockout_observed BOOLEAN,
  uom_basis VARCHAR,          -- 固定 'unknown'，禁止跨 SKU 求和
  ingested_at TIMESTAMPTZ,
  PRIMARY KEY (snapshot_date, warehouse_id, goods_id)
);

CREATE TABLE stock_id_history (
  entity_type VARCHAR,        -- warehouse | goods
  entity_id VARCHAR, name VARCHAR,
  valid_from DATE, valid_to DATE,  -- 生效区间，不覆盖旧名
  source_run VARCHAR,
  PRIMARY KEY (entity_type, entity_id, name, valid_from)
);

CREATE TABLE stock_publish (
  snapshot_date DATE PRIMARY KEY,
  run_id VARCHAR, published_at TIMESTAMPTZ, previous_run_id VARCHAR
);
```

- 主键用稳定 ID：`warehouseIdKey` / `goodsIdKey`；`goodsSku` 只作展示与别名。
- 同一 run 内 `(warehouse_id, goods_id)` 重复：数值一致→去重计数；
  数值冲突→**整 run 拒绝发布**，保留文件与错误。
- 同一 `goods_id` 出现多个 `goodsSku` 别名：写入 `stock_id_history`；
  若同一天同 ID 同别名指向不同数值→拒绝发布。
- 跨日改名：旧名 `valid_to` 截止，新名 `valid_from` 开始；历史查询按 ID 聚合。

### 3. 完整性与同日多 run

- `scope_complete`：本次请求/抓取的仓集合是否全部完整；
  `run_complete`：全部启用仓是否完整。两者分开，不能用 scope 完整冒充 run 完整。
- 成功抓取的空仓（0 行）是**有效结果**，标 `complete=true`，
  **不是 unknown**；只有缺文件/失败仓才是 unknown。
- 同日多 run 选择顺序（确定性）：
  1) `run_complete=true` 优先；
  2) 否则 `scope_complete=true` 且覆盖目标仓集合最大者；
  3) 其次 `ended_at` 最晚；
  4) 平局按 `run_id` 字典序最大。
  该规则保证**反序导入结果一致**。
- 发布：staging 校验 → 单事务写 `stock_history`（仅该日期）→ 更新 `stock_publish`
  （记录 previous_run_id）→ 提交。回滚按 `stock_publish.previous_run_id` 重放。
- 并发：`stock_history.lock` 独占；第二个进程拒绝启动。
- schema 迁移：`schema_migrations` 表；版本化 SQL，不手工改表。

### 4. 断货与未知

- `stockout_observed=true` 仅当：该仓 `complete=true`、`available=0`、
  且该 run 被发布（`stock_publish.run_id` 指向它）。
- 缺失/失败/缺文件 → `unknown`，不写 0，不进入断货统计。
- `TEST-1` → `is_test=true`，默认视图排除。
- `uom_basis='unknown'`：视图禁止跨 SKU/品类直接求和。

## 可运行验收（固定样本 + 断言）

实施阶段提供一个可运行入口（本轮不实现）：

```
uv run python scripts/stock_history_ingest.py \
  --run-dir "D:/Work/库存备份/2026-10-20" --source legacy --dry-run
uv run python scripts/stock_history_ingest.py \
  --run-dir "D:/Work/库存备份/2026-10-21" --source legacy --dry-run
uv run python -m unittest test_stock_history_ingest.py
```

固定样本：复制上述两天到 `tests/fixtures/stock/{day}/`，并记录每个文件的 SHA256。
断言必须包含**内容、完整标志、哈希**：

1. 同一 run 重复导入两次 → 行数/内容不变，重复计数一致。
2. 10-20 → 退货仓 400 行 `batch_complete=false`，`scope_complete=false`、
   `run_complete=false`；其余 13 仓 complete；不发布为完整日。
3. 10-21 → 5,314 行、14 仓 complete，`run_complete=true`；内容与 manifest 对账。
4. 完整→不完整、反序导入 → 发布指针仍指向完整 run；不完整只留审计。
5. 不完整→完整 → 原子切换；旧完整行无残留（逐行内容比对）。
6. 成功空仓（0 行）→ complete，不是 unknown；缺文件/失败仓 → unknown。
7. 改名/别名 → 稳定 ID 不变，`stock_id_history` 有生效区间。
8. 同 run 重复键数值冲突 → 整 run 拒绝；哈希异常 → 拒绝并报警。
9. 跨日补跑按 `snapshot_at` 的 Asia/Shanghai 日期归属。
10. `TEST-1` 标记并从分析视图排除；`uom_basis='unknown'` 禁止跨 SKU 求和。

## 未决

- **05:17 是否运行、结果如何待证**；需日志时间戳、每次运行 exit/阶段、
  按 run_id 留存 manifest，才能区分定时与手动。
- 只有 2 天，且 10-20 不完整；不足以做删失/断货校正。
- 每日快照无法定位日内断货；后续需要订单/库存事件或更高频采样。
- `goodsSku` → EN 物料/仓库映射依赖 `sku_map`/`warehouse_map`，未在本任务验证。
- 本方案未落盘、未启动任务、未访问生产；需复审通过后再实施。
