---
okf: v0.1
type: Review
title: 每日通途库存备份：只读诊断、逐文件对账与历史入库方案
date: 2026-10-21
reviewer: claude
status: diagnostic-only
---

# 每日通途库存备份 — 诊断与入库方案

## 结论

- 任务真实存在：Windows 计划任务 `FZH-TongtuStockApiDaily`，每天 **05:17**，
  执行 `D:\Work\fzh-stock-backup\run_stock_daily_backup.cmd` →
  `stock_daily_backup.py`，输出 `D:\Work\库存备份\YYYY-MM-DD\*.jsonl + manifest.json`。
- **但历史只有 2 天，且 10-20 不完整、10-21 的定时那次没有产出 manifest**：
  - 2026-10-20：14 仓，13 完整；`美中-FZH-DANEEY-退货产品仓` URLError 10060，
    文件有 400 行部分数据，manifest 标 `complete=false`；总文件行 5,192，
    manifest 计数 4,792，差 400 正好是该仓。
  - 2026-10-21：manifest `snapshot_at=09:46:23`、`complete=true`、14/14、
    5,314 行 = 5,314 行，无重复、无坏 JSON；这是一次**手动/补跑**，
    不是 05:17 定时那次（定时那次 LastTaskResult=1，未留下 05:17 manifest）。
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
  日志无逐行时间戳。入库时应显式按 Asia/Shanghai 解释，并保留原始字符串。
- 来源：`tongtool erp2_stocks_stocksquery`（manifest）。
- `defects`、`waitingShipment` 与 `available` 是独立桶；不能默认相加。
- `goodsSku` 为 `TEST-1` 的行是测试商品，入库时应标记而非当真实库存。

## 故障诊断（只列可证事实）

- 10-20：单仓 URLError 10060；脚本对单仓失败不阻断其他仓，manifest 汇总为
  `complete=false`，退出码 1（`return 0 if manifest["complete"] else 1`）。
- 10-21 定时 05:17：LastTaskResult=1，且没有 05:17 的 manifest；
  09:46 的 manifest 是一次成功补跑（`complete=true`）。
- 计划任务 Principal：`zhang`、`RunLevel=Limited`、`LogonType=Interactive`
  → 只在用户交互登录会话存在时运行；注销/未登录不会跑。
- 日志开头有 `✗ 缺少通途凭证`，随后有多次 `[526] 限流，等待 60s`；
  但日志**没有时间戳**，无法证明这些行属于 05:17 那次还是更早的手动尝试。
  **根因未证实**：可能是凭证文件当时不可读、网络/限流、或任务会话问题；
  不把“缺少凭证”当成 05:17 的唯一结论。
- 未查到 TaskScheduler 事件日志（查询无结果，可能是权限/日志未开启）。

## 历史入库方案（本轮只设计，不落盘）

建议新增 `stock_history`，与现有 `stock_latest` 分开：

```sql
CREATE TABLE stock_history (
  snapshot_date DATE,          -- Asia/Shanghai
  snapshot_at   TIMESTAMP,     -- 原始采集时间，保留
  warehouse_id  VARCHAR,
  warehouse_name VARCHAR,
  goods_sku     VARCHAR,
  available     DOUBLE,
  intransit     DOUBLE,
  defects       DOUBLE,
  waiting_shipment DOUBLE,
  source_file   VARCHAR,
  batch_complete BOOLEAN,      -- 当日该仓是否完整
  ingested_at   TIMESTAMP,
  PRIMARY KEY (snapshot_date, warehouse_id, goods_sku)
);
```

规则：

1. **幂等**：按主键 upsert；重复导入不增行。
2. **不完整批次**：`batch_complete=false`；缺失仓/失败仓写“未知”，不写 0。
3. **不覆盖**：不回写/删除手动快照 `tongtool_stock`；历史表独立。
4. **断货标记**：只在 `available=0` 且 `batch_complete=true` 时置
   `stockout_observed=true`；其余为 `unknown`，不推断需求为 0。
5. **去重与排序**：同 SKU 重复行按 `goods_sku` 去重并报计数；
   不静默丢弃，差异可追溯。
6. **测试商品**：`goodsSku=TEST-1` 单独标记，默认不进入分析视图。
7. **时区**：`snapshot_date` 用本地日期；跨零点补跑要按 `snapshot_at` 归属。

## 离线验收用例（可复现）

- 同一日重复导入两次 → 行数不变、`ingested_at` 更新、重复计数为 0。
- 10-20 导入 → 退货仓 400 行为 `batch_complete=false`，其余 13 仓完整；
  汇总不把 400 当完整日。
- 10-21 导入 → 5,314 行全量、14 仓 complete。
- 缺失文件/失败仓 → `unknown`，不写 0。
- `goodsSku=TEST-1` → 标记并从分析视图排除。
- 两次导入的 `stock_history` 行数与 manifest 对账一致。

## 未决

- 05:17 定时失败的**根因**（凭证/网络/会话）未证实；需要给日志加时间戳、
  记录每次运行的 exit/阶段，并保留每次 manifest 的独立副本（现在同日补跑会覆盖）。
- 只有 2 天，且 10-20 不完整；不足以做删失/断货校正。
- 每日快照无法定位日内断货；后续需要订单/库存事件或更高频采样。
- `goodsSku` → EN 物料/仓库映射仍依赖 `sku_map`/`warehouse_map`，未在此任务内验证。
- 本方案未落盘、未启动任务、未访问生产；需复审后再实施。
