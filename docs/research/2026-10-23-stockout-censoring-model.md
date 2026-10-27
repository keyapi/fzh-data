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

- EN Parquet 历史目前 **7 天**：10/20 5,192、10/21 5,314、10/22 5,314、10/23 5,316、10/24 5,316、10/25 5,316、10/26 5,316 行。10/24–10/26 为生产 05:17 定时自动运行，均 `complete=true`（14 仓，约 14 分钟）。
- 本地 DuckDB `order_store.duckdb` 的 `stock_history` 只有 **3 天**（10/20–10/22，15,820 行），`stockout_observed=true` 9,933 行（63%）。
- 现有 `stockout_observed` 定义（`stock_history_ingest.py`）：
  `(batch_complete AND available = 0)` —— **按仓、等于 0**，不聚合、不看销量、不看停售、不看退货/手工调整。
- 订单历史有 45 个月（407,898 单，PR #290），但**EN 库存历史只有 7 天**（WX 另有 38 个稀疏检查日）。
  ⇒ 现在无法对过去 45 个月做回溯断货剔除；只能从有库存快照的时点开始标，或找回更早的库存快照（NAS/Excel/赛狐/3PL 报表）再补。

### 1.1 已找到的历史数据（2026-10-23 核查）

| 数据 | 位置 | 覆盖 | 用途 |
|---|---|---|---|
| WX 库存动态 | 本地 WX 历史库存目录 | **8/24–10/19，27 个日期列**，5,083 行；美东/波兰/美中/美中退货/Wayfair Cranbury | 稀疏日度库存；趋势/检查点 |
| WX 6/26 库存 | 同目录 | 2026-06-26 全量 5,550 行（数据源/美东/波兰/美中/退货/Wayfair） | 6 月检查点 |
| WX 6/9、6/11 + 7 月销售/库存报表 | 同目录 | 6/9、6/11、7/10、7/16、7/22、7/24、7/28、7/29、7/30、7/31 | 6–7 月检查点（含销量/库存） |
| EN 每日快照 | `/home/frappe/fzh-inventory/stock.parquet` | 10/20–10/26（每日，7 天） | 之后每日累积 |
| PB `check0stock` / `checked0stock` | PB orders 本地历史目录 | **2023-09-08 至 2026-10-22，81 个 `checked0stock` CSV / 68 个检查日 / 2,145 条阻塞明细；35 个 Vendor Style：24 个大号 Wedge + 3 个 Personal Wedge + 8 个 Gap Filler** | PB/美中断货与零库存订单的地面真值（SPS 目录 39 个；Coffee 4 色未在 PB 订单出现） |
| 同事通途报表备份 | `D:/Work/彭建/通途库存记录 彭建下载备份 20261026.zip` | **2026-04-14–10-09，22 天 / 48 快照 / 42,577 行**；70 个「销售及库存报表」+ 47 个「商品销量分析报表」 | 仓级库存检查点：显式 0 + **以前出现过、后来消失**可作断货负证据；从未出现=unknown |
| PB 无货通知链 | 订单 → 中国运营 → 美中 → 中国运营 → 你 | 事件驱动 | 美中/PB 实际无货信号 |
| 钉钉盘点群 | 钉钉群 | — | **当前无读取/搜索权限，暂不可用** |

- WX 的“库存动态”是 **27 个日期列**（8/24、8/26、8/28…10/19），不是连续每日；6/26 和 7 月是检查点。
- PB 的 `check0stock`/`checked0stock` 是**订单级**零库存记录，不是库存水平。经配对核验：**`checked0stock` 是 `check0stock` 的子集**（前者才是真正没通过库存检查的订单；后者还包含已通过检查的订单），因此**只把 `checked0stock` 当阻塞证据**，`check0stock` 只用于补 SKU 清单。
- 4 个检查日只有 `check0stock`、没有 `checked0stock`（2024-04-09、2024-07-09、2024-08-14、2025-07-17），这 4 天**不产生断货标签**（无法区分“没货”与“检查通过”），按 `unknown` 处理。
- 现有 DuckDB `stock_history` 只有 3 天（10/20–10/22）；WX/PB 历史已按独立 schema 入库（见 1.3），**不覆盖也不补齐** 每日 `stock_history`。

### 1.2 SPS Item Sourcing × PB 实际订单（2026-10-25）

- SPS 目录 **39 个**：28 个大号 `Wedge Pillow, Linen` + 3 个 `Personal Wedge Pillow`（60cm）+ 8 个 `Gap Filler Pillow`（2026-03 起新增楔形）。
- 2023-08 至今真实 PB 订单出现 **35 个 Vendor Style**：24 个大号 Wedge（**Coffee 4 色未出现**）+ 3 个 Personal + 8 个 Gap。
- 结论：以 **35 个实际销售 SKU** 为准。Coffee 4 色只在 SPS 目录、历史订单没有，**暂不纳入**（没有历史需求可拟合；如运营确认要卖，作为新品单独处理）。
- 8 个 Gap Filler 的 SKU/断货窗口已在 `楔形枕 补货决策信息包 20261016.md/xlsx`。

### 1.3 P0 一次性入库结果（2026-10-26）

**WX 历史库存**（`wx_inventory_history.duckdb`，已附加到 `order_store.duckdb` 的 `wx_inventory` schema）

- 12 个 xlsx、**38 个日期**、198,363 条观测：6/9、6/11、6/26；7/10、7/16、7/22、7/24、7/28、7/29、7/30、7/31；8/24–10/19 的 27 个日期列。
- **两套仓库口径，不能直接合并**：
  - 6–7 月：12 个明细仓（CENTRADE、FZH-DANEEY 成品/半成品/皮壳/退货、FZHPoland-covers、WayfairCG×3、多渠道、大件云仓、星链海外仓）。
  - 8–10 月：5 个汇总仓（美东仓、美中仓、美中-FZH-DANEEY-退货产品仓、波兰仓、WayfairCG-Cranbury仓）。
- 状态：`positive_observed` 54,376；`nonpositive_observed` 130,648；`low_stock_1_3` 12,411；`unknown` 928。**非正库存只代表系统登记值，不等于物理断货。**
- 脚本 `D:/Work/fzh-order-store/wx_inventory_ingest.py`，报告 `wx_inventory_import_report.json`，测试 `test_wx_inventory_ingest.py`。

**PB 零库存订单**（`pb_stockout_history.duckdb`，已附加到 `order_store.duckdb` 的 `pb_stockout` schema）

- 扫描 1,669 个 CSV：590 个订单导出（471 普通订单 / 81 `checked0stock` / 38 `check0stock`），885 个非订单导出，194 个 `NotUsed` 跳过。
- 去重后 **12,857 条不同订单行**，覆盖 **35 个 Vendor Style**（24 大号 + 3 Personal + 8 Gap），与真实订单一致；Coffee 4 色未出现。
- **2,145 条阻塞明细**（另折叠同一天重复导出 462 条），落在 **68 个检查日**、2023-09-08 至 2026-10-22；按年：2023 100、2024 735、2025 469、2026 841。
- 阻塞量：大号 Wedge 1,756 条 / 1,831 件；Personal 286 / 328 件；Gap 103 / 108 件。**每张 PB 订单多为 1–2 件**，订单数比件数更有信息量。
- **覆盖空档 = 没有报告断货（负证据），不是 unknown**。业务流程：怀疑断货 → 订单发美中 → 美中通知 → 在下次来货前持续 `check0stock`；来货后停止检查。因此：
  - 有 `checked0stock` 阻塞记录 = 当天观察到断货；
  - 没有检查记录 = 没有怀疑/没有报告断货；
  - 4 个只有 `check0stock`、没有 `checked0stock` 的日期（2024-04-09、2024-07-09、2024-08-14、2025-07-17）是**检查跑了但结果文件缺失**，标 `check_result_missing`，不当作断货也不当作有货；
  - 2023-09-08 之前没有数据，不外推。
- `stockout_windows` 共 159 段（同一 SKU 在连续检查日出现、且相邻检查日间隔 ≤7 天才并段）；**窗口只表示“这些检查日观察到阻塞”，不表示区间内连续断货**。
- `shortage_calendar`（35 SKU × 1,141 天 = 39,935 行）：`reported_shortage` 938 个 SKU-日（68 个检查日）；`no_reported_shortage` 38,857；`check_result_missing` 140（35 × 4 个结果缺失日）。**没有检查记录的日期按业务口径归入“没有报告断货”。**
- 脚本 `D:/Work/fzh-order-store/pb_stockout_ingest.py`，报告 `pb_stockout_import_report.json`，测试 `test_pb_stockout_ingest.py`（2 项通过）。

**同事报表检查点（PJ 20261026）**

- 70 个「销售及库存报表」、**22 个日期**（2026-04-14→10-09）、42,577 行、6 个仓；已入 `pengjian_inventory` schema。
- `sku_status_daily` 59,559 行：逐日 × 仓 × SKU 的 `present_positive` / `present_zero` / `absent_after_presence`，带 `prior_status`。
- 2026-10-09：美东 283 正 / 87 显式 0 / 153 消失（139 在售 + 14 清仓）；波兰 732 / 18 / 619；美中 573 / 29 / 123。
- 报表勾了“隐藏所有库存为0”，所以大部分零库存 SKU 是**消失**而不是显式 0；对以前出现过的 SKU，消失按该仓 0 处理；从未出现过的不算。美中 9 月仓库合并前后要分开。

**EN 每日库存（截至 2026-10-26）**

- 生产 05:17 定时：10/24、10/25、10/26 连续 3 天 Success，14 仓、5,316 行、`complete=true`，约 14 分钟。
- 历史 Parquet 10/20–10/26 共 7 天；`get_stock_history` 实测可回读。
- **库存变动**（app PR #8，**2026-10-26 已部署生产**）：生产单仓验证通过后，14 仓 3 天回填 **653 行**（与测试站一致）；事件类型包裹 461 / 订单 117 / 拆包 63 / 报溢 9 / 报损 2 / 买家退货 1；`enable_stock_change=1`，05:47 起每日增量。
- 原始 WX/PB 文件与 DuckDB 体积大且有业务明细，**不入公开仓库**；仓库只保留方法与结果。


### 1.4 P1 `stock_status_daily`（2026-10-26）

**存放位置**：本地分析 DuckDB `D:/Work/fzh-order-store/order_store.duckdb` 的 `stock_status` schema。
**不写进 EN 的 `stock.parquet` / `stock_change.parquet`**：这两个是原始每日事实，派生状态表混进去会破坏 schema、回滚和增量写入。EN 生产（2C/3.5G）也不跑重分析；以后若 EN 页面要展示，再单独输出一个小的只读状态 Parquet。

**表**：

| 表/视图 | 内容 |
|---|---|
| `stock_status.daily_observation` | 三源原始观测：EN 日快照 / PJ 检查点 / WX 检查点 |
| `stock_status.sales_daily` | `gs_orders` 日销量（按日期+仓+SKU） |
| `stock_status.daily` | 每日期×仓×SKU 一行，按 EN > PJ > WX 优先级取一条 |
| `stock_status.pb_daily` | PB `shortage_calendar`（35 个 Vendor Style × 日期） |

**`stock_status.daily` 关键列**：`d, warehouse, sku, source, stock_state, available, waiting_shipment, intransit, physical_on_hand, current_status, prior_status, sales_qty, sales_7d, sales_30d, confidence, evidence, warehouse_role, likely_unavailable, review_candidate, pb_reported_shortage, low_stock`。

**规模（2026-10-26 实测）**：

- **287,274 行**，日期 2026-04-14 → 2026-10-26。
- 来源：EN 37,084（7 天）、PJ 59,559（22 天）、WX 190,631（38 天）。
- 状态：`present_positive` 110,881；`present_zero` 156,569；`absent_after_presence` 18,900；`unknown` 924。
- **`likely_unavailable` 46,355**：EN 24,307 + PJ 22,048；**WX 不计入**（宽表 0 多为“不在该仓”）。
- **`review_candidate` 127,342**：WX 的 0，只作低置信复核。
- **`pb_reported_shortage` 162 行**：仅加在美中-FZH-DANEEY 行，PB 渠道级证据。
- **`physical_on_hand` 77,743 行**：`available + waiting_shipment`，**不含 defects**（次品发不了货）；WX 缺 waiting 列为 NULL。
- **`low_stock` 16,496 行**：美东-CENTRADE 可用 ≤5，只算 EN/PJ；WX 的低置信 0 不计入。**K 天删失 / M 天 prolonged 还没算**。
- 仓角色：`primary_sellable` 220,336；`returns` 29,557；`components` 29,055；`other` 8,326。

**已知限制**：

- `gs_orders` 只到 **2026-09-30**，所以 10 月的 `sales_qty` 是 NULL（不是 0）；要补 10 月销量需接 EN/Tongtool 订单。
- WX 非正库存只作 `review_candidate`，不作断货；WX 每日库存是宽表，0 可能只是“没在这个仓”。
- PJ 的 `absent_after_presence` 只在 `prior_status=在售` 时进 `likely_unavailable`；清仓/停售算下架。
- PB Vendor Style 与通途 SKU 忽略大小写 **35/35 匹配**；PB 是渠道级断货，不等于该仓库存为 0。
- 美中 2026-09 合并前后仓库口径不同，分析要按时期分开。

**常用查询**：

```sql
-- 高置信断货候选
SELECT d, warehouse, sku, stock_state, sales_qty, confidence
FROM stock_status.daily
WHERE likely_unavailable AND warehouse_role = 'primary_sellable'
ORDER BY d DESC, warehouse, sku;

-- 某 SKU 的时间线
SELECT d, warehouse, source, stock_state, available, sales_qty, prior_status
FROM stock_status.daily
WHERE upper(sku) = upper('CENKZ1323-LTGrey-153')
ORDER BY d, warehouse;
```

脚本 `D:/Work/fzh-order-store/build_stock_status.py`，报告 `stock_status_report.json`。

### 1.5 Wayfair CG 数据源（2026-10-23）

通途里的 `WayfairCG-Cranbury/Perris/Romeoville` 数量不准；同事 YTQ 从 Wayfair 后台导出的 `AllInventoryExport_2026-10-23` 更完整：

- 文件：`D:/Work/尹/wayfair/AllInventoryExport_2026-10-23 (1)(1).csv`
- 2,333 行、**1,009 个 Part Number**（就是通途 SKU）、11 个仓：
  - 2 个 Dropship：CENTRADE INC. NJ 07936 / TX 77099（各 1,009 行，是公司自有 dropship，不是 CG）
  - 9 个 **Castlegate**（CG）：NJ-Cranbury 103、FL-Jacksonville 45、GA-McDonough 38、TX-Lancaster 36、IL-Romeoville 29、MD-Aberdeen 23、CA-Lathrop 16、CA-Perris 14、GA-Port Wentworth 11
- Castlegate 合计 **315 行 / 103 SKU / 可用 401 件**。
- 对比通途 10/23：Cranbury 92 SKU / 860 件、Perris 4 / 0、Romeoville 2 / 0；SKU 交集只有 **56**，Wayfair 独有 47、通途独有 36。**通途 CG 不能作为可信来源。**
- 已入库：`wayfair_cg.inventory`（明细，仅供审计）+ `wayfair_cg.sku_daily`（**按 SKU 汇总所有 Castlegate 仓**：`available_castlegate` / `in_stock_castlegate`），在 `order_store.duckdb`。
- **CG 像 FBA 多仓，不按单仓细分**：业务上一个 SKU 汇总所有 Castlegate 仓即可；明细表保留单仓只是为了核对。Dropship 行（CENTRADE NJ/TX）是自有仓，不要混进 CG。
- 局限：这是**单日快照**；Wayfair 的 `In Stock Update` 是每行更新时间（跨度数月），不是导出时间。后续需要 YTQ 定期导出（每周/每天）或走 Wayfair API。

### 1.6 操作时点（6 天实测，2026-10-21→10-27）

**数据**：`erp2_stocks_stockschangedetailquery` 6 天，3,134 条（去重后）。凭证构成：包裹 2,300、订单 504、拆包 234、采购单 40、报溢 39、报损 11、买家退货 4。

**订单（配货/占用）按星期 × 小时**：

| 星期 | 小时分布 |
|---|---|
| 周三（半天） | 13:6、14:35 |
| 周四 | 10:13、13:4、14:13、15:14、17:18 |
| 周五 | 9:13、11:20、14:35、16:4 |
| **周一** | **9:78、13:31、14:46、15:107、16:3、17:41** |
| 周二（半天） | 10:23 |

- 08–10 点占订单的 **25.2%**，13–15 点占 **57.7%**；09 点 18.1%、14 点 25.6%。
- **不是固定的 09:00/14:00 两个尖峰**：上午欧洲在 09:00–11:00 分散，下午美国在 13:00–17:00 分散，**周一明显更重、拖到 15:00/17:00**。

**包裹（发货）按星期 × 小时**：

| 星期 | 小时分布 |
|---|---|
| 周三 | 14:50、15:144 |
| 周四 | 9:148、10:28、14:35、15:98、16:41、18:1 |
| 周五 | 9:176、11:20、14:68、15:64、16:87 |
| 周六 | 13:149 |
| **周一** | **9:86、13:165、14:146、15:225、17:5** |
| 周二 | **9:528**、10:26（周一积压，周二早上补发） |

- 发货集中在 **13:00–16:00**，15:00 最大；周一更重。
- **周二 09:00 的 528 条是周一积压补发**，所以周二 05:17 的“开门库存”仍包含周一未发的待发库存。

**拆包/调整**：拆包 14:00 63、15:00 126、16:00 38；报损/报溢 09:00–11:00 与 14:00–15:00 少量。

**结论（最终快照时点）**：

| 时间（北京） | 范围 | 依据 |
|---|---|---|
| 05:17 | 全量 | 开门库存；但周二早上会先补发周一积压，物理库存要等 09:00 后 |
| **12:00–12:30** | 波兰 | DSY 11 点多处理完欧洲；上午订单 09:00–11:00 |
| **17:30–18:00** | 美东+美中 | WXY 15:00 分配、17:00 发货；周一拖到 17:00，18:00 更稳 |
| 周一可选 19:00 | 美东+美中 | 周一 15:00/17:00 订单明显更多 |

- 欧洲和美国必须分开：18:00 北京是欧洲中午，抓不到欧洲收盘；12:00 北京是美国凌晨，抓不到美国分配。**要两个市场都准，至少 3 个时点：05:17 + 12:00 + 18:00**。
- 如果只取 2 个：12:00（欧洲）+ 18:00（美国），放弃 05:17 开门基线。
- 05:17 仍有意义：早上下单时，前一天的分配/发货已反映；但周二 09:00 的补发不在里面。

✅ 已实现（app PR #10）：独立 `stock_intraday.parquet`（`slot=eu/us`），12:00 波兰 / 18:00 美东+美中；05:17 的 `stock.parquet` 不变。测试站 EU 1,371 行 / US 3,096 行，复跑不追加。**生产 2026-10-27 已部署启用**：EU 冒烟 1,371 行 / 3m04，18:00 首次自动。**周一 19:00 作为后续建议，当前统一 18:00**，等有需求再按操作记录调整。







| 渠道 | 履约仓 | 停售阈值 | 主要风险 |
|---|---|---|---|
| 美东 Centrade / WOWMAX 等 | **美东-CENTRADE** | **5** | 运营在 ≤5 手动下架；手工改库存；退货入主仓可售 |
| 美中 USTX / 其他 | **美中-FZH-DANEEY** | 0/无统一负责人（已确认没人负责） | **系统库存可能虚高**：入库数量错、应出库未出库、报损/报溢未操作；系统有货但实际无货可发 |
| PB 历史 2023–2024 | 美东 → 2024 美中分公司后改美中 USTX | 5 / 0 | 时期切换；历史没有库存快照 |
| Wayfair CG | 美东调拨到 CG 仓 | 暂忽略 | 调拨出美东可能造成美东真实缺货 |

- **美东**：**先假定所有账号（Centrade / WOWMAX 等）都只吃美东-CENTRADE**；≤5 下架只影响美东发货仓。断货不是 `available=0` 才开始，而是运营在 ≤5 手动下架后销售停止。
- **美中**：停售阈值/负责人**不知道，也没人负责**；不套用美东的 5。PB 的流程是：订单 → 中国运营 → 美中 → 没货 → 美中通知中国运营 → 中国运营通知你。**非 PB 的美中 Listing 没有稳定无货信号，按 `stock_unknown` 处理**，不能因系统库存 >5 就当有货。
- **PB 历史**：2023–2024 美东；2024 美中分公司成立后改美中 USTX；偶发美中断货临时改美东，极少；Wayfair CG 从美东调拨，先忽略。**PB 本地 `check0stock`/`checked0stock` 2023-08 至今约 275 个文件，是 PB/美中断货的地面真值**；SPS 目录 39 个，PB 实际订单 35 个（24 大号 Wedge + 3 Personal + 8 Gap），Coffee 4 色未出现；以 35 个实际销售 SKU 为准。
- **退货**：退到主仓的退货可售；美东/波兰以前没有退货仓，现在有但可能没人操作入库；美中退货仓一直有，9 月仓库改名后不确定是否直接进正常品仓。**不能假设退货仓是唯一退货入口**。
- **下架通知**：美东运营会在钉钉盘点/通知群发；当前**没有钉钉群消息读取/搜索权限**，暂不可用。美东先用“销量停止 + ≤5”推断；PB/美中直接用 `check0stock` + 无货通知链，不依赖钉钉。

待确认：

1. 美东 WOWMAX 等是否与 Centrade 一样只吃美东 CENTRADE（先按“是”实现，之后可改）。
2. PB SKU 集合：SPS 39 / 实际销售 35；Coffee 4 色是否纳入，请运营确认。
3. WX 历史文件：已按“27 个库存列=可用库存”处理；6/26 与 7 月报表的仓库映射按 `美东仓→美东-CENTRADE` 等对齐，待抽样核对。
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
| `reported_shortage` | PB：当天有 `checked0stock` 阻塞记录（订单级地面真值） |
| `no_reported_shortage` | PB：当天没有阻塞记录。按业务流程（怀疑断货才 check，来货后停止）视为**没有报告断货**，不是 unknown |
| `check_result_missing` | PB：当天有 `check0stock`、没有 `checked0stock`（检查跑了但结果缺失） |
| `present_zero_checkpoint` | PJ 报表显式 `可用库存数量=0`（仓级，可信） |
| `absent_after_presence` | PJ 报表中该 SKU 以前在该仓出现过、本日消失；按 `prior_status` 区分在售=断货候选 / 清仓停售=下架 |
| `stock_unknown` | **仅美中非 PB**：系统库存 >5 但销量=0 / 无货订单/客服反馈；**不能因库存 >5 就判定有货** |
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
7. **PB 用“有没有检查记录”做负证据**
   - 有 `checked0stock` 阻塞记录 = `reported_shortage`；
   - 没有检查记录 = `no_reported_shortage`（业务流程决定：怀疑断货才 check，来货后不再 check）；
   - 只有 `check0stock`、没有结果文件 = `check_result_missing`，不参与需求拟合；
   - 该负证据只适用于 PB；**美中非 PB 仍按 `stock_unknown`**。
8. **PJ 稀疏检查点用“显式 0 + 消失”做仓级负证据**
   - 报表有行且可用=0 = `present_zero_checkpoint`；
   - 以前在该仓出现过、本日无行 = `absent_after_presence`：`prior_status=在售` 才算断货候选，`清仓/停售` 算下架；
   - 从未在该仓出现 = `not_carried/unknown`，不当 0；
   - 同一天消失的 SKU 可能转到了别的仓（如美东→美中）；对**当前渠道仓**仍不可售，但对全局 SKU 不是 0；
   - **美中 2026-09 仓库合并**：之前 4 个子仓、之后 1 个 `美中-FZH-DANEEY`，分析要按时期分开，别把改名当断货。

## 4. 如何侦测退货/手工调整

好消息：通途 ERP2 官方库存变动明细接口 `erp2_stocks_stockschangedetailquery`（`updatedDateFrom` 只能 7 天内），实测返回：

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

**必须每天抓**（6 天窗口会过期；通途严格 7 天，正好 7 天会报 527），落到 `stock_change` 表/Parquet；否则单看每日库存水平，退货和手工调整无法可靠区分。
✅ 已接入 EN：`tongtool_integration/sync/stock_change_sync.py`，每日 **05:47** 抓 14 仓，写 `/home/frappe/fzh-inventory/stock_change.parquet`；窗口从上次成功 -1 天开始、上限 7 天，事件级去重。测试站 14 仓 3 天实测 653 行（包裹 461 / 订单 117 / 拆包 63 / 报溢 9 / 报损 2 / 买家退货 1），重跑不翻倍。

## 5. 建议的数据/管道改动

1. **统一库存历史**：把 EN 的 `stock.parquet` 每日并入现有 DuckDB `stock_history`（或让 `stock_history` 直接读 Parquet），不要维护两套历史。
2. **新增每日库存变动明细**：✅ 用 `erp2_stocks_stockschangedetailquery` 每日抓 14 仓（05:47），存单个 `stock_change.parquet`（含凭证类型/单号/操作人/四个桶的 increase）；窗口上限 7 天，从上次成功 -1 天开始，重跑按事件去重。
3. **新增 `stock_status_daily`**：listing × SKU × day，字段：
   `sellable_stock, low_stock, sales_qty, has_sellable_replenishment, return_qty, manual_adjust, censored, stockout_start, stockout_end, confidence, evidence`。
4. **保留 unknown**：快照缺失/批次不完整时不要写 0，也不参与删失。
5. **运营日志**：请美东/中国运营把下架/恢复/盘点调整记到共享表；盘点群消息可请中国运营转发/导出。没有日志时先用“销量停止 + ≤5”推断。
6. **Listing ↔ 仓 ↔ 时期映射**：美东 → 美东-CENTRADE；美中 → 美中-FZH-DANEEY；PB 2023–2024 → 美东，2024+ → 美中 USTX；Wayfair CG 暂忽略。
7. **PB 无货标签**：✅ 已解析 `checked0stock`（`check0stock` 的超集关系已核验）→ 68 个检查日 / 2,145 条阻塞明细 / 35 个 Vendor Style（24 大号 Wedge + 3 Personal + 8 Gap；Coffee 4 未销售）；生成 `blocked_observations` / `sku_block_daily` / `stockout_windows`。**空档期按业务口径 = 没有报告断货（负证据），不是 unknown；4 个只有 check0stock 的日期标 `check_result_missing`。**
8. **美中非 PB**：没有稳定无货信号时按 `stock_unknown`，不能因系统库存 >5 就当有货；有客服/运营反馈再标。
9. **WX 历史库存入库**：✅ 已把 6/9、6/11、6/26、7 月 8 个检查点、库存动态 8/24–10/19（27 个日期列）共 38 个日期 / 198,363 条观测入 `wx_inventory` schema；两套仓库命名（6–7 月 12 明细仓 / 8–10 月 5 汇总仓）**尚未合并**，需按 `美东仓 → 美东-CENTRADE` 等映射后再与 EN 10/20–26 对齐。
10. **钉钉**：`qyapi_chat_read` 只读群信息/成员，**不返回消息历史**；当前没有群消息读取/搜索权限，不纳入自动化；需要时请运营导出或记共享表。会话存档是另一套企业能力，暂不启动。
11. **PJ 报表检查点**：✅ 70 个销售及库存报表 → `pengjian_inventory.observations` / `daily_snapshot` / `sku_status_daily`（59,559 行）；22 个日期，2026-04-14→10-09。按 §3.3 第 8 条使用：显式 0 + 曾出现后消失（在售）作仓级断货证据；从未出现/清仓/停售不算。

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
| P0 | 每日抓库存变动明细 + 解析 PB `check0stock`/`checked0stock` + WX 历史库存入库 | ✅ WX 38 日期 / 198,363 行；✅ PB 68 检查日 / 2,145 阻塞明细 / 35 SKU；✅ PJ 22 天 / 42,577 行 / `sku_status_daily`；✅ EN 每日 `stock_change`（05:47，生产 653 行） |
| P1 | 建立 listing 级 `sellable_stock` + `stock_status_daily`（美东阈值 5、K=2–3、M=7；美中 `stock_unknown`） | 美东抽 20–30 SKU 用 ≤5/销量停核对；PB 35 SKU 用 `checked0stock` 核对；美中非 PB 用客服/运营反馈 |
| P2 | 与订单历史 join，先做“剔除 censored 天”的基线预测 | 与不剔除的模型对比，检查断货期预测是否不再被 0 拉低 |
| P3 | 校准 K/M/阈值；评估 Tobit/删失模型；扩展到其他仓/市场 | 运营认可 + 回测稳定 |

## 8. 重要限制

- **库存历史**：EN 10/20–10/26 每日（7 天）；WX 38 个日期（6/9–10/19，稀疏）、6/26 + 7 月多个检查点；6 月以前没有。不能回溯修正 45 个月订单。
- **PB 真值**：81 个 `checked0stock` CSV / 68 个检查日 / 2,145 条阻塞明细，2023-09-08 至 2026-10-22；是**订单级零库存记录**，不是库存水平。**没有检查记录的日期按业务流程视为“没有报告断货”**（怀疑断货才 check，来货后停止）；4 个只有 `check0stock` 的日期结果缺失，按 `check_result_missing`；2023-09-08 之前无数据。
- **美中系统库存可能虚高**（入库数量错、应出库未出库、报损/报溢未操作）；**没有统一停售阈值/负责人**，非 PB 只能 `stock_unknown`，不能只用库存水平判断。
- 美东“≤5 下架”是运营动作，不是系统事件；会有滞后，需人工样本校准。
- 退货仓使用情况不确定：美东/波兰新设但可能没人入库；美中 9 月改名后不确定是否进正常仓 ⇒ 用变动明细里的**实际仓 + 凭证类型**判断，不要假设退货仓是唯一入口。
- 盘点群/下架通知没有接入系统；需要运营日志或导出，否则用“销量停止 + ≤5”代理。
- 现有 `stockout_observed=(batch_complete AND available=0)` 只是“单仓库存为 0 的观察”，不能直接当预测删失标签。
- 每日快照无法定位日内断货；库存变动明细有 `operateTime`，可用于日内/事件级判断。
- **PJ 报表是稀疏检查点**（22 天），且勾了“隐藏所有库存为0”：零库存 SKU 多为“消失”，只对**以前出现过**的 SKU 按该仓 0 处理；从未出现过的不算。美中 9 月仓库合并前后不可直接比较。

## 9. 相关

- `docs/reference/tongtool-stock-en-operations.md` — EN 每日同步操作手册（配置、Run/Latest、Parquet、历史 API）
- `docs/handoffs/2026-10-23-jack-en-stock-sync.md` — EN 通途库存每日同步落地清单
- `docs/research/2026-10-23-inventory-history-storage-architecture.md` — 当前/历史库存存储架构
- 现有入库与模型（在 supply-chain 分支，未合入本分支）：`docs/research/supply-chain/2026-10-20/claude/control/reviews/2026-10-21-stock-daily-diagnosis.md`、`.../experiments/g1_contract/stock_history_ingest.py`（`stockout_observed=(batch_complete AND available=0)`）、`.../experiments/business_phase/build_plan.py`
- 45 个月订单 DuckDB 文档（demand_forecast 分支）：`docs/solutions/architecture-patterns/order-history-duckdb-store.md`
- P0 入库产物（不入公开仓库，在本机 `D:/Work/fzh-order-store`）：`wx_inventory_ingest.py` / `wx_inventory_history.duckdb` / `wx_inventory_import_report.json`；`pb_stockout_ingest.py` / `pb_stockout_history.duckdb` / `pb_stockout_import_report.json`；两套测试 `test_wx_inventory_ingest.py`、`test_pb_stockout_ingest.py`
