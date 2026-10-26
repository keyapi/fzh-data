---
okf: v0.1
type: Research
title: 通途历史库存用于销量预测 — 断货/停售/退货/手工调整的判定口径
description: 现有 stock_history 的 stockout_observed 是按仓 available=0 的朴素标记，不适合预测删失；提出 listing 级可售库存、≤5 停售阈值、持续时间、退货与手工调整、股票变动事件的多信号判定模型
date: 2026-10-23
tags: [supply-chain, inventory, stockout, censoring, demand-forecast, tongtool, duckdb]
---

# 通途历史库存用于销量预测 — 断货/停售判定口径

> 目的：用历史库存判断“哪些天是因为没货/停售而没有销量”，在预测销量时剔除或做删失处理。
> 结论：**不要用现有 `stockout_observed = (batch_complete AND available = 0)`**；它按仓、按 0、不看销量/停售/退货/手工调整，会把大量“这个仓本来就不放这个 SKU”误判为断货。
> 先建立 **listing 级、可售库存、持续时间、多信号** 的标签；同时开始每天抓库存变动明细。

## 1. 先看数据现实（很关键）

- EN Parquet 历史目前只有 **4 天**：10/20 5,192、10/21 5,314、10/22 5,314、10/23 5,316 行。
- 本地 DuckDB `order_store.duckdb` 的 `stock_history` 只有 **3 天**（10/20–10/22，15,820 行），`stockout_observed=true` 9,933 行（63%）。
- 现有 `stockout_observed` 定义（`stock_history_ingest.py`）：
  `(batch_complete AND available = 0)` —— **按仓、等于 0**，不聚合、不看销量、不看停售、不看退货/手工调整。
- 订单历史有 45 个月（407,898 单，PR #290），但**库存历史只有 4 天**。
  ⇒ 现在无法对过去 45 个月做回溯断货剔除；只能从有库存快照的时点开始标，或找回更早的库存快照（NAS/Excel/赛狐/3PL 报表）再补。

## 2. 业务规则（已确认/待确认）

- Paula（美东 Centrade）：**可用库存 ≤5 就由运营手动下架**；目前没有赛狐/通途自动同步库存到销售平台，也没有 Listing 自动同步配置。
- 因此断货不是“available=0”才开始；**实际停止销售可能发生在 ≤5**，而且取决于运营什么时候手动下架。
- 待确认：
  1. 每个 Listing/市场对应哪个/哪些仓？（美东 Listing 是否只吃美东库存，还是可以吃美中？）
  2. ≤5 是美东的规则，其他仓/市场阈值是否不同？
  3. 退货到的仓是否可售？退货仓/故障品仓的退货不应当作可售。
  4. 运营下架/恢复的日期是否有记录（哪怕手工表）？

## 3. 推荐判定模型

### 3.1 先把“可售库存”算对

按 **Listing / 市场 / SKU** 聚合，而不是按单仓：

```text
sellable_stock(listing, sku, day) =
  sum(available) over 能服务该 listing 的仓
  - 排除退货仓 / 故障品 / 停用仓
  - in-transit 不计入可售（可作恢复信号）
```

- 如果 Listing 绑定单仓（如美东 Listing 只吃美东），就只看该仓；
- 如果多仓可履约，必须跨仓汇总，否则单仓 0 会误判断货；
- 退货仓、故障品仓的库存不算可售。

### 3.2 每日状态与标签

对每个 listing × SKU × day 打标签：

| 标签 | 条件（建议初值） |
|---|---|
| `observed_sale` | 当天销量 > 0；即使库存 0/≤5 也先算“观察到销售”，不删失 |
| `low_stock` | 0 < sellable_stock ≤ 5（Paula 阈值）；只是预警，不直接删失 |
| `likely_unavailable` | sellable_stock ≤ 5 **且** 当天/连续 K 天销量 = 0，且无可售补货 |
| `censored` | `likely_unavailable` 持续 ≥ K 天（K=2–3） |
| `prolonged_stockout` | `censored` 连续 ≥ M 天（M=7 或 14，按业务） |
| `supply_blip` | 零星退货/调拨导致库存短暂回升，但未持续 > 阈值、销量未恢复 |
| `data_artifact` | 手工清零/盘点/改库存，或库存跳变与订单/退货/采购不匹配 |
| `unknown` | 快照缺失/批次不完整；**不写 0，不参与删失统计** |

**结束断货**：`sellable_stock > 5` 连续 K 天 **且** 销量恢复 >0；不是“某天退货 1 件”就结束。

### 3.3 关键判定规则

1. **不能只看 available=0**
   - Paula 的运营在 ≤5 就下架；断货窗口可能从 5 开始。
   - 单仓 0 但其他仓有货、Listing 仍可履约 → 不是断货。
2. **必须看销量**
   - 库存 ≤5 但仍有销量 → 还没真正停售，不要删失。
   - 库存 0 但有销量（报溢/先发货后补）→ 当天是观察到销售，不删失。
3. **必须看持续时间**
   - 单日 0 可能是手工修正/盘点/数据抖动；连续 ≥K 天才进入删失。
   - 用户关心“一段时间断货”，用 M 天定义 prolonged，短缺口单独标记。
4. **手工清零/改库存**
   - 用库存变动明细的凭证类型/操作人识别；若库存大幅下降/上升与订单/退货/采购不匹配，标 `data_artifact`，不要当断货，也不要当需求。
   - 手工调整后又恢复的，优先判为数据修正，不进入需求拟合。
5. **退货**
   - 退货仓/故障品仓的退货**不可售**，不结束断货。
   - 主仓的小额/零星退货是 `supply_blip`：1–2 件、没超过阈值、没恢复销量 → **仍按断货算**。
   - 只有可售库存持续 > 阈值 K 天且销量恢复，才结束断货。
6. **在途/采购**
   - 在途不是可售；但可作为“即将恢复”的信号，避免把恢复前的空窗误标为长期断货（或在报表里单独标注）。

## 4. 如何侦测退货/手工调整

好消息：通途有库存变动明细接口 `erp2_stocks_stockschangedetailquery`（`updatedDateFrom` 只能 7 天内），实测返回：

- `goodsSku`、`operateTime`、`operaterUserName`
- `relatedVoucherType` / `relatedVoucherTypeName`（如“包裹”）、`relatedVoucherNumber`
- `availableStockIncrease`、`defectsStockIncrease`、`intransitStockIncrease`、`waitingShipmentStockIncrease`
- 当前 `availableQuantity` / `defectsQuantity` / `intransitQuantity` / `waitingQuantity`

可以用它区分：

- 包裹/发货：销量出库；
- 退货/退货入库：正向 `available`/`defects` 增加；
- 盘点/库存调整/手工：操作人 + 调整类凭证；
- 调拨：仓间移动；
- 采购入库：补货。

**必须每天抓**（7 天窗口会过期），落到 `stock_change` 表/Parquet；否则单看每日库存水平，退货和手工调整无法可靠区分。

## 5. 建议的数据/管道改动

1. **统一库存历史**：把 EN 的 `stock.parquet` 每日并入现有 DuckDB `stock_history`（或让 `stock_history` 直接读 Parquet），不要维护两套历史。
2. **新增每日库存变动明细**：用 `erp2_stocks_stockschangedetailquery` 抓最近 1–2 天，存 `stock_change`（含凭证类型/单号/操作人/四个桶的 increase）。
3. **新增 `stock_status_daily`**：listing × SKU × day，字段：
   `sellable_stock, low_stock, sales_qty, has_sellable_replenishment, return_qty, manual_adjust, censored, stockout_start, stockout_end, confidence, evidence`。
4. **保留 unknown**：快照缺失/批次不完整时不要写 0，也不参与删失。
5. **运营日志**：请 Paula/运营提供下架/恢复日期（哪怕手工表），用于校准阈值和 K/M。
6. **Listing ↔ 仓映射**：先确认美东等市场的履约仓；不确定时按“可履约仓集合”聚合，而不是单仓。

## 6. 预测里怎么用

- 只用 `censored=false` 的日期拟合需求；`censored=true` 的 0 不当成 0 需求。
- 断货期可做：
  - 直接剔除（简单、保守）；
  - 或用 Tobit / 零膨胀 / 删失需求模型，把断货日作为“观测缺失”；
  - 记录断货前后销量、补货恢复后的销量，用于估计未观测需求。
- 短缺口/低库存但仍有销量的天，保留并标注，不强行剔除。
- 手工调整/数据异常天，从需求和断货两边都排除，或降权。

## 7. 分阶段落地

| 阶段 | 做什么 | 验收 |
|---|---|---|
| P0 | 每日抓库存变动明细（含凭证类型/操作人） | 每天有 `stock_change`；能识别包裹/退货/调整/调拨 |
| P1 | 建立 listing 级 `sellable_stock` + `stock_status_daily`（阈值 5、K=2–3、M=7） | 与 Paula 抽 20–30 个 SKU 人工核对 |
| P2 | 与订单历史 join，先做“剔除 censored 天”的基线预测 | 与不剔除的模型对比，检查断货期预测是否不再被 0 拉低 |
| P3 | 校准 K/M/阈值；评估 Tobit/删失模型；扩展到其他仓/市场 | 运营认可 + 回测稳定 |

## 8. 重要限制

- **库存历史只有 4 天**（EN Parquet）/ 3 天（DuckDB）；不能回溯修正 45 个月订单。
- 每日快照无法定位日内断货；库存变动明细有时刻，可用于日内/事件级判断。
- 没有平台 Listing 状态/库存同步配置；下架/恢复主要靠销量停止 + 库存 ≤5 + 运营日志推断。
- Paula 的“≤5 下架”是运营动作，不是系统事件；会有滞后，需人工样本校准。
- 现有 `stockout_observed` 只能当“单仓库存为 0 的观察”，不能直接当预测删失标签。

## 9. 相关

- `docs/research/supply-chain/2026-10-20/claude/control/reviews/2026-10-21-stock-daily-diagnosis.md` — 现有入库/完整性/断货判定限制
- `docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract/stock_history_ingest.py` — `stockout_observed=(batch_complete AND available=0)`
- `docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/build_plan.py` — 现有模型把删失当需求缺口
- `docs/reference/tongtool-stock-en-operations.md` — EN 每日同步操作手册
- `docs/solutions/architecture-patterns/order-history-duckdb-store.md` — 45 个月订单 DuckDB
