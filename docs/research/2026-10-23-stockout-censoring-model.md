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

### 1.1 已找到的历史数据（2026-10-23 核查）

| 数据 | 位置 | 覆盖 | 用途 |
|---|---|---|---|
| WX 库存动态 | 本地 WX 历史库存目录 | **8/24–10/19，27 个日期列**，5,083 行；美东/波兰/美中/美中退货/Wayfair Cranbury | 稀疏日度库存；趋势/检查点 |
| WX 6/26 库存 | 同目录 | 2026-06-26 全量 5,551 行（数据源/美东/波兰/美中/退货/Wayfair） | 6 月检查点 |
| WX 7 月销售/库存报表 | 同目录 | 7/10、7/16、7/22、7/24、7/28、7/29、7/30、7/31 | 7 月检查点（含销量/库存） |
| EN 每日快照 | `/home/frappe/fzh-inventory/stock.parquet` | 10/20–10/23（每日） | 之后每日累积 |
| PB `check0stock` / `checked0stock` | PB orders 本地历史目录 | **2023-08 至今，约 275 个文件** | PB/美中断货与零库存订单的地面真值（28 个涤麻三角靠枕） |
| PB 无货通知链 | 订单 → 中国运营 → 美中 → 中国运营 → 你 | 事件驱动 | 美中/PB 实际无货信号 |
| 钉钉盘点群 | 钉钉群 | — | **当前无读取/搜索权限，暂不可用** |

- WX 的“库存动态”是 **27 个日期列**（8/24、8/26、8/28…10/19），不是连续每日；6/26 和 7 月是检查点。
- PB 的 `check0stock`/`checked0stock` 是**订单级**零库存记录，不是库存水平；用 SKU 过滤到 28 个产品后，可生成断货窗口/受影响订单。
- 现有 DuckDB `stock_history` 只有 3 天，尚未导入 WX 这些文件；需要先做一次性入库。

## 2. 业务规则（已确认）

| 渠道 | 履约仓 | 停售阈值 | 主要风险 |
|---|---|---|---|
| 美东 Centrade / WOWMAX 等 | **美东-CENTRADE** | **5** | 运营在 ≤5 手动下架；手工改库存；退货入主仓可售 |
| 美中 USTX / 其他 | **美中-FZH-DANEEY** | 0 或按运营（待确认） | **系统库存可能虚高**：入库数量错、应出库未出库、报损/报溢未操作；系统有货但实际无货可发 |
| PB 历史 2023–2024 | 美东 → 2024 美中分公司后改美中 USTX | 5 / 0 | 时期切换；历史没有库存快照 |
| Wayfair CG | 美东调拨到 CG 仓 | 暂忽略 | 调拨出美东可能造成美东真实缺货 |

- **美东**：**先假定所有账号（Centrade / WOWMAX 等）都只吃美东-CENTRADE**；≤5 下架只影响美东发货仓。断货不是 `available=0` 才开始，而是运营在 ≤5 手动下架后销售停止。
- **美中**：停售阈值/负责人**不知道，也没人负责**；不套用美东的 5。PB 的流程是：订单 → 中国运营 → 美中 → 没货 → 美中通知中国运营 → 中国运营通知你。**非 PB 的美中 Listing 没有稳定无货信号，按 `stock_unknown` 处理**，不能因系统库存 >5 就当有货。
- **PB 历史**：2023–2024 美东；2024 美中分公司成立后改美中 USTX；偶发美中断货临时改美东，极少；Wayfair CG 从美东调拨，先忽略。**PB 本地 `check0stock`/`checked0stock` 2023-08 至今约 275 个文件，是 PB/美中断货的地面真值**。
- **退货**：退到主仓的退货可售；美东/波兰以前没有退货仓，现在有但可能没人操作入库；美中退货仓一直有，9 月仓库改名后不确定是否直接进正常品仓。**不能假设退货仓是唯一退货入口**。
- **下架通知**：美东运营会在钉钉盘点/通知群发；当前**没有钉钉群消息读取/搜索权限**，暂不可用。美东先用“销量停止 + ≤5”推断；PB/美中直接用 `check0stock` + 无货通知链，不依赖钉钉。

待确认：

1. 美东 WOWMAX 等是否与 Centrade 一样只吃美东 CENTRADE（先按“是”实现，之后可改）。
2. PB 的 28 个涤麻三角靠枕 SKU 清单/映射能否提供？用于过滤 2023 至今的 `check0stock`。
3. WX 历史文件的定义：`库存动态` 的 27 个库存列是否为“可用库存”；6/26 与 7 月报表是否同一口径、同一仓库映射。
4. 美中/PB 的无货通知能否稳定导出（邮件/钉钉/表格均可），作为 `check0stock` 之外的补充。

## 3. 推荐判定模型

### 3.1 先把“可售库存”算对

按 **Listing / 市场 / SKU** 聚合，而不是按单仓：

```text
sellable_stock(listing, sku, day) =
  sum(available) over 能服务该 listing 的仓
  - 排除退货仓 / 故障品 / 停用仓
  - in-transit 不计入可售（可作恢复信号）
```

- 美东 Listing（Centrade / WOWMAX）：只看 **美东-CENTRADE**；≤5 阈值只作用于这里。
- 美中 Listing（USTX 等）：看 **美中-FZH-DANEEY**；**系统库存可能虚高**，库存 >5 也不能自动认定“有货”。
- PB 按时期：2023–2024 美东；2024 后美中 USTX；偶发跨仓忽略。
- 退货仓、故障品仓的库存不算可售；**退到主仓的退货可售**。

### 3.2 每日状态与标签

| 标签 | 条件（建议初值） |
|---|---|
| `observed_sale` | 当天销量 > 0；即使库存 0/≤5 也先算“观察到销售”，不删失 |
| `low_stock` | 0 < sellable_stock ≤ threshold；**美东 threshold=5**；美中 0/待确认 |
| `stock_unknown` | 美中系统库存 >5 但销量=0 / 无货订单/客服反馈；**不能因库存 >5 就判定有货** |
| `likely_unavailable` | 美东：sellable ≤5 + 销量=0；美中：销量=0 +（sellable≤0 或无货订单/客服/运营确认） |
| `censored` | `likely_unavailable` 持续 ≥ K 天（K=2–3） |
| `prolonged_stockout` | `censored` 连续 ≥ M 天（M=7 或 14，按业务） |
| `supply_blip` | 零星退货/调拨导致库存短暂回升，但未持续 > 阈值、销量未恢复 |
| `data_artifact` | 手工清零/盘点/改库存（按操作人/凭证类型），或库存跳变与订单/退货/采购不匹配 |
| `unknown` | 快照缺失/批次不完整；**不写 0，不参与删失统计** |

**结束断货**：`sellable_stock > 5` 连续 K 天 **且** 销量恢复 >0；不是“某天退货 1 件”就结束。

### 3.3 关键判定规则

1. **不能只看 available=0**
   - 美东运营在 ≤5 就下架；断货窗口可能从 5 开始。
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

### 4.1 退货在本业务里的判定

- **退到主仓：可售**；但小额/零星退货（1–2 件）是 `supply_blip`，**不结束断货**，仍按断货算。
- **退到退货仓**：若退货仓未被运营使用/不可售，不结束断货；若之后调拨到主仓，调拨入库是新的可售供给事件。
- 美东/波兰以前没有退货仓、现在有但可能没人入库；美中退货仓 9 月改名后不确定是否直接进正常品仓 ⇒ **不要假设退货仓是唯一入口，按变动明细的实际仓 + 凭证类型判断**。
- 零散退货即使不在退货仓，也会体现在主仓 `availableStockIncrease`；用它识别，不要只看仓库名。
- 只有主仓可售库存持续 > threshold K 天且销量恢复，才结束断货。

### 4.2 手工调整

- 美东运营会改通途库存；中国运营会做报损/报溢；变动明细有 `operaterUserName` + 凭证类型。
- 与订单/退货/采购不匹配的大幅调整 → `data_artifact`；若调整后长期不恢复且销量停 → `manual_stockout`/`delist`，需运营确认。
- 美中“应该报损/报溢但没操作”的情况，变动明细里没有事件；只能靠销量停止、无货订单、客服反馈识别，标 `stock_unknown`，不能因系统库存 >5 就当作有货。

**必须每天抓**（7 天窗口会过期），落到 `stock_change` 表/Parquet；否则单看每日库存水平，退货和手工调整无法可靠区分。

## 5. 建议的数据/管道改动

1. **统一库存历史**：把 EN 的 `stock.parquet` 每日并入现有 DuckDB `stock_history`（或让 `stock_history` 直接读 Parquet），不要维护两套历史。
2. **新增每日库存变动明细**：用 `erp2_stocks_stockschangedetailquery` 抓最近 1–2 天，存 `stock_change`（含凭证类型/单号/操作人/四个桶的 increase）。
3. **新增 `stock_status_daily`**：listing × SKU × day，字段：
   `sellable_stock, low_stock, sales_qty, has_sellable_replenishment, return_qty, manual_adjust, censored, stockout_start, stockout_end, confidence, evidence`。
4. **保留 unknown**：快照缺失/批次不完整时不要写 0，也不参与删失。
5. **运营日志**：请美东/中国运营把下架/恢复/盘点调整记到共享表；盘点群消息可请中国运营转发/导出。没有日志时先用“销量停止 + ≤5”推断。
6. **Listing ↔ 仓 ↔ 时期映射**：美东 → 美东-CENTRADE；美中 → 美中-FZH-DANEEY；PB 2023–2024 → 美东，2024+ → 美中 USTX；Wayfair CG 暂忽略。
7. **PB 无货标签**：解析 `check0stock` / `checked0stock` 2023-08 至今约 275 个文件，按 28 个涤麻三角靠枕 SKU 过滤，生成断货窗口/受影响订单；作为 PB/美中的地面真值。
8. **美中非 PB**：没有稳定无货信号时按 `stock_unknown`，不能因系统库存 >5 就当有货；有客服/运营反馈再标。
9. **WX 历史库存入库**：6/26、7 月报表、库存动态 8/24–10/19（27 个日期列）→ `stock_checkpoint` / 长表；统一仓库名（美东仓 → 美东-CENTRADE 等），与 EN 10/20–23 对齐；6 月以前没有。
10. **钉钉**：当前没有群消息读取/搜索权限，不纳入自动化；需要时请运营导出或记共享表。

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
| P0 | 每日抓库存变动明细 + 解析 PB `check0stock`/`checked0stock` + WX 历史库存入库 | 每天有 `stock_change`；PB 28 SKU 有断货窗口；WX 6/26、7 月、8/24–10/19 有 `stock_checkpoint` |
| P1 | 建立 listing 级 `sellable_stock` + `stock_status_daily`（美东阈值 5、K=2–3、M=7；美中 `stock_unknown`） | 美东抽 20–30 SKU 用 ≤5/销量停核对；PB 28 SKU 用 `check0stock` 核对；美中非 PB 用客服/运营反馈 |
| P2 | 与订单历史 join，先做“剔除 censored 天”的基线预测 | 与不剔除的模型对比，检查断货期预测是否不再被 0 拉低 |
| P3 | 校准 K/M/阈值；评估 Tobit/删失模型；扩展到其他仓/市场 | 运营认可 + 回测稳定 |

## 8. 重要限制

- **库存历史**：EN 10/20–10/23 每日；WX 8/24–10/19 有 27 个日期列（稀疏）、6/26 + 7 月多个检查点；6 月以前没有。不能回溯修正 45 个月订单。
- **PB 真值**：`check0stock` / `checked0stock` 2023-08 至今约 275 个文件，是**订单级零库存记录**，不是库存水平；按 28 个 SKU 过滤后用于断货标签。
- **美中系统库存可能虚高**（入库数量错、应出库未出库、报损/报溢未操作）；**没有统一停售阈值/负责人**，非 PB 只能 `stock_unknown`，不能只用库存水平判断。
- 美东“≤5 下架”是运营动作，不是系统事件；会有滞后，需人工样本校准。
- 退货仓使用情况不确定：美东/波兰新设但可能没人入库；美中 9 月改名后不确定是否进正常仓 ⇒ 用变动明细里的**实际仓 + 凭证类型**判断，不要假设退货仓是唯一入口。
- 盘点群/下架通知没有接入系统；需要运营日志或导出，否则用“销量停止 + ≤5”代理。
- 现有 `stockout_observed=(batch_complete AND available=0)` 只是“单仓库存为 0 的观察”，不能直接当预测删失标签。
- 每日快照无法定位日内断货；库存变动明细有 `operateTime`，可用于日内/事件级判断。

## 9. 相关

- `docs/research/supply-chain/2026-10-20/claude/control/reviews/2026-10-21-stock-daily-diagnosis.md` — 现有入库/完整性/断货判定限制
- `docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract/stock_history_ingest.py` — `stockout_observed=(batch_complete AND available=0)`
- `docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/build_plan.py` — 现有模型把删失当需求缺口
- `docs/reference/tongtool-stock-en-operations.md` — EN 每日同步操作手册
- `docs/solutions/architecture-patterns/order-history-duckdb-store.md` — 45 个月订单 DuckDB
