---
okf: v0.1
type: Reference
title: 通途库存口径与分时快照——可用/待发/物理，以及美欧市场的读取时点
date: 2026-10-27
category: architecture-patterns
module: tongtool_integration
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - "设计库存快照、断货判定或补货决策"
  - "决定每天读几次通途库存、什么时间读"
  - "解释 physical 与 available 的差异"
tags: [tongtool, inventory, available-stock, physical-stock, snapshot-timing, timezone]
---

# 通途库存口径与分时快照

## Context

EN 每天 05:17 把通途库存写入 `stock.parquet`。业务问题是：

- 备份的到底是“物理库存”还是“可用库存”？
- 跨境电商主要卖美国和欧洲，有时差；每天读 1–2 次，什么时间点最准？
- 05:17 是否已经覆盖前一天操作的影响？

## Guidance（本学习沉淀的做法）

### 1. 四个桶与物理在库

通途 `erp2_stocks_stocksquery` 返回四个数量：

| 字段 | 含义 |
|---|---|
| `availableStockQuantity` | **可用**（可售、未被订单占用） |
| `waitingShipmentStockQuantity` | **待发**（已分配、未出库） |
| `intransitStockQuantity` | 在途（不在仓，不算物理） |
| `defectsStockQuantity` | 次品 |

业务口径：**物理在库 = available + waiting_shipment**，**不算 defects**（次品发不了货）。`intransit` 也不计入。

### 2. 库存事件流（用 `stock_change` 验证）

| 凭证 | 动作 | 影响 |
|---|---|---|
| `订单` | 导入后人工配货/占用 | available −N，waiting +N，物理不变 |
| `包裹` | 发货出库 | 物理减少 |
| `拆包` | 订单取消/释放 | available +N，waiting −N |
| `采购单` | 采购入库 | 物理增加 |
| `报损/报溢` | 手工调整 | available 增减 |

所以“物理 100、90 单占用、可用 10”是正常状态：可用先降，物理等发货才降。

### 3. 操作节奏（6 天实测，北京时间）

- **欧洲运营**：上午 09:00–11:00 分散占用，11 点多处理完。
- **美国运营**：13:00–17:00 分散占用，15:00 左右分配、17:00 左右发货；**周一明显更重**。
- **周二 09:00** 常有周一的积压补发（实测 528 条包裹）。
- 因此 09:00/14:00 不是唯一的两个尖峰，不能只按两个点设计。

### 4. 快照时点

| 时间（北京） | 范围 | 作用 |
|---|---|---|
| 05:17 | 全量 | 开门库存；早上下单基线；已覆盖前一天分配/发货（但周二 09:00 补发不在内） |
| 12:00–12:30 | 波兰 | 欧洲收盘后、运营处理完 |
| 17:30–18:00 | 美东+美中 | 美国收盘后、分配/发货基本完成 |

- **要两个市场都准，至少 3 个时点**：18:00 北京是欧洲中午，抓不到欧洲收盘；12:00 北京是美国凌晨，抓不到美国分配。
- 只取 2 个：12:00（欧洲）+ 18:00（美国），放弃 05:17 开门基线。
- 周一若 18:00 仍赶不上，可后续加 `0 19 * * 1` 美国槽（当前统一 18:00）。

### 5. 文件与存储

- **`stock.parquet` 只保留 05:17 一份**，schema 不变；不要用盘中数据覆盖它。
- 盘中写独立的 `stock_intraday.parquet`，加 `slot`（`eu`/`us`），按 `(snapshot_date, slot)` 覆盖，重跑不追加。
- slot 名不绑定时间：改 12:00/18:00 只改 `hooks.py` 两行 cron + restart。
- 派生分析（`stock_status.daily`）放**本地 DuckDB**，不写进 EN 的原始 Parquet；EN 生产 2C/3.5G，不适合跑重分析。

### 6. API 成本

- 全量 14 仓约 60 次调用 / 14 分钟；
- 波兰单仓约 15 次 / 3 分钟；
- 美东+美中约 33 次 / 7 分钟；
- 商户级 5 次/分钟，任务是串行节流；分时快照要错开，不要并发。

## Why This Matters

- 用错口径（只看 physical 或只看 defects）会把“已被订单占用”当成可售，导致超卖。
- 只用一个时点无法同时覆盖美欧两个收盘；05:17 只看得到开门状态，看不到当天分配后的可用。
- 把盘中数据写进日快照会破坏“一天一行”的语义和历史对比。

## When to Apply

- 设计库存快照/补货/断货标签时；
- 解释“为什么库存 100 但可用只有 10”时；
- 决定新增定时任务、评估 API 限流与服务器负载时。

## Examples

```sql
-- 物理在库（业务口径，不含次品/在途）
SELECT available + waiting_shipment AS physical_on_hand
FROM stock_history
WHERE warehouse_name = '美东-CENTRADE';
```

```bash
# 盘中快照（手动）
bench --site <site> execute tongtool_integration.sync.stock_intraday.run_stock_intraday \
  --kwargs '{"slot": "eu", "source": "manual"}'
```

## Related

- `docs/reference/tongtool-stock-en-operations.md` — 配置、Run 日志、Parquet、手动补跑
- `docs/handoffs/2026-10-23-jack-en-stock-sync.md` — §12/§13
- `docs/research/2026-10-23-stockout-censoring-model.md` — §1.6 操作节奏与断货标签
