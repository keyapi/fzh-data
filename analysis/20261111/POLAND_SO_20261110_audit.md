# 波兰 SO / 彭建 Excel / A-B-C 口径审计（2026-11-11）

## 1. 昨天到底下了几张 SO

EN `Sales Order`，2026-11-10：

| SO | 创建时间 | 客户 | 交付日 | 件数 |
|---|---|---|---:|---:|
| **SO-26-00135** | 09:22 | 波兰公司 | 2026-12-05 | 1,334 |
| **SO-26-00136** | 15:14 | 波兰公司 | 2026-12-15 | 2,320 |

**昨天 2 张，合计 3,654 件。**

今天 2026-11-11 又新增：

| SO | 创建时间 | 客户 | 交付日 | 件数 |
|---|---|---|---:|---:|
| SO-26-00137 | 08:45 | 波兰公司 | 2026-12-05 | 20 |

三张合计 **3,674 件**（原始 88 行；按 product+pool 去重 71 行）。

## 2. 禁用的物料与皮壳

11/10 修改且当前 `disabled=0` 的关键物料：

| 物料 | 类型 | 修改时间 | 对应 SO |
|---|---|---|---|
| `KS0307-KQC-26-WHITE` | 成品：绑带款膝盖腿枕 | 11-10 09:20 | SO-135（50 件） |
| `PK#KS0307-KQC-26-WHITE` | 皮壳 | 11-10 09:20 | SO-135 |
| `KS0198-DRKQC-116-GREY` | 成品：组合式侧睡枕 | 11-10 15:13 | SO-136（50 件） |
| `PK#KS0198-DRKQC-116-GREY` | 皮壳 | 11-10 15:14 | SO-136 |

另有 4 个复合斜纹雪尼尔面料在 09:40 修改为 `disabled=0`；是否与本次 SO 直接相关未逐一证明。

**结论**：确实存在“为了上传 SO 把成品+皮壳重新启用”的痕迹；`disabled` 是技术开关，不是业务“停售/清仓”标记。

## 3. 彭建发来的 Excel

钉钉单聊，2026-11-10 09:25，彭建发来：

`Priority products Table.xlsx`（3.78 MB）

已下载到：`D:/Work/fzh-order-store/analysis/dingtalk_pj_20261110/Priority products Table.xlsx`

关键 sheet：`Priority Products（整理)`：

- 56 行 `REQUEST QTY > 0`，合计 **2,991 件**；
- 库存列是 **Available stocks (2026,10,28)**；
- 销售列是 **SEP(2025) / OCT(2025) / NOV(2025) / DEC(2025) / JAN(2026)**；
- 没有 current owner、没有当前库存 11/10、没有停售/禁用状态、没有我们的 A/B/C 目标。

### 与我们的 v5.3 对比

56 行里 55 行能映射到我们的波兰键（2,946 件）；按 v5.3 口径：

| 我们的状态 | 行数 | 请求件数 | 我们的建议量 |
|---|---:|---:|---:|
| 不用补 | 8 | 260 | 0 |
| 继续观察 | 2 | 130 | 0 |
| 催已有 | 3 | 120 | 0 |
| 催已有+新增 | 22 | 850 | 771 |
| 补-下单日已过-需重排 | 11 | 1,036 | 1,761 |
| 补-待排期 | 9 | 550 | 659 |

**至少 510 件是“波兰要下、我们的 A/B/C 认为不用下/先观察/只催”**。例子：

- `KS0001-DM-60-GREY`：请求 100，库存 0；我们“继续观察”。
- `KS0248-DM-45-ANTHRACITE`：请求 50，库存 58；我们“不用补”。
- `KS0248-HLR-45-BLACK`：请求 50，库存 16；我们“不用补”。
- `KS0007-DM-160-GREY`：请求 30，库存 33；我们“不用补”。
- `KS0455-FHXWXNE-92x56x75-GREY`：请求 50，库存 0；我们“催已有”。

**判断**：老板/波兰的下单决策更像“波兰商业优先清单 + 请求量”，不是我们的 A/B/C/D5/D6 计算结果。它可能包含市场判断、促销、上新、历史客户关系；但从我们的口径看，**无法用 A/B/C 复算，也不保证不会多下或漏下**。

## 4. A/B/C 受什么影响

- **A SKU 宇宙**：目前靠 2026 有销售 / 2025 下单 / current owner；没有硬性的“在售/停售/清仓/停产”字段。
- **disabled**：只是 EN 的技术禁用；为了上传 SO 可以临时启用，不能当“业务恢复销售”。
- **B 归属**：如果 A 把禁用/停售键算进来，B 会给出 owner，但不代表应该补。
- **C 库存**：有库存的死 SKU 仍会被看到；如果没有 lifecycle，C 无法区分“可售库存”与“待清库存”。
- **D5/D6**：A 的键集合变了，D5 历史序列和 D6 动作都会跟着变；所以 A 的 lifecycle 规则必须先定。

### 建议的硬规则

1. 在 EN Item / Item Group 增加 `lifecycle_status`：`active / seasonal / clearance / discontinued / blocked`。
2. A 宇宙只保留 `active`；`seasonal` 只在季节窗口；`clearance` 不进补货；`discontinued/blocked` 排除。
3. `disabled` 只做技术开关；禁用/启用必须同时更新 `lifecycle_status`，并留原因。
4. 停售 SKU 要能指向 `replacement_sku`，避免用旧库存继续补。
5. 对“波兰请求但 A/B/C 不建议”的 510 件，单独列 `business_override`，由波兰/老板签字，不混进算法建议。

## 5. 对当前版本的影响

- v5.4 已纳入 **00135 + 00136 + 00137** 三张 SO 作为待发供给；
- 49 个波兰键 / 2,064 件匹配 D6；
- 但 SO 到 12/05–12/15，只有部分按时：按时供给约 +230、净需求约 -183；
- 5 键仍补 409（对应 SO 220）、31 键催已有/新增 1,070（对应 SO 1,324）；
- **不能把 2,064 件全当“已解决”。**

## 6. 结论

- 昨天 **2 张 SO**，今天 1 张；三张合计 3,674 件。
- 老板的订单来源很可能是 **彭建 11/10 09:25 发的波兰 Priority Products Excel**，不是我们 11/07 的 v2。
- 这份 Excel 是商业优先清单，不是 A/B/C 补货计算；它与我们的建议有 510 件方向性差异。
- A 的 lifecycle 规则缺失是根因；`disabled` 不能替代停售标记。建议尽快加 `lifecycle_status`，否则 A/B/C 永远会在“有销售、有库存、但已停售”的 SKU 上打架。

---

## 7. 波兰独立账号 `Poland Order`（2026-11-11 补查）

已打开 Google Sheet：`Poland Order`（ID `1XxPdJs6PkLClAmb6ABEYV4XtbLkMdVX27uR2nPQ2yrk`）。

工作表：`Order Details（202512` 到 `Order Details（202609）`，另有 `Payee account` / `Sales Receipts Breakdown`。**没有 202610**，与用户说“暂未加 10 月”一致。

解析结果：

- 1,163 行 / **1,217 件**；日期 2025-12-17 到 2026-09-30。
- 映射到 D3b product：1,051 行 / 1,122 件。
- **与 `orders_unified`（通途订单）交集 = 0 行 / 0 件**。
- 平台：Allegro 716 行/763 件、Kaufland 115/115、Pillowpalette.pl 115/124、Empik 64/68、Home24 28/32 等。
- 2026 年 1–9 月合计约 1,150 件；同期通途波兰仓销售约 11,873 件，**独立账号约再加 10%**。
- Top 产品：`KS0455-FHXWXNE-92x56x75-GREY` 79、`KS0455-...-BEIGE` 56、`KS0174-WGMSR-45-BROWN` 49、`KS0248-MH-45-FLAXGREY` 40、`KS0212-QMZZML-54-DEEPGREY` 37、`KS0234-KJB-45-BROWN` 32。

**结论**：波兰独立账号是**真实终端销售**（Allegro/Empik/Kaufland 等，带单价/金额），不是波兰向 FZH 的采购单。当前 A/D3b/D5 **没有纳入**这 1,217 件，因此波兰需求被低估；某些“波兰请求 vs 我们不用补”的差异，可能其实是独立账号的真实销量。

## 8. 王弦 9/10 月手动扣减库存：证据状态

已尝试三条路径（2026-11-11 更正：上一版说“MCP 524 = App 未开通”是错的）：

- EN `Stock Ledger Entry`：按 `成品 - 波兰PL`、`仓库 - 波兰PL`、`在途物料 - 波兰PL` 等查 2026-09-01 至 11-11，**0 行**；波兰库存不在 EN 台账。
- **直连通途 open API（非 MCP）**：
  - `POST /openapi/tongtool/stocksQuery` **可用**，过滤参数是 `warehouseName`（`warehouseId` 会被忽略）；返回 `availableStockQuantity / intransitStockQuantity / waitingShipmentStockQuantity / defectsStockQuantity / syncPendingStockQuantity`。
  - `POST /openapi/tongtool/stocksChangeDetailQuery` **已授权**（返回 527“`updatedDateFrom` 只能是距当前时间 7 天内的值”，不是 524）；因此 **9–10 月的库存变动无法通过该接口回溯**。
  - `POST /openapi/tongtool/specialStocksQuery` **已授权**（返回 525“`type` 参数错误”，说明是参数问题，不是接口未开通）；有效 `type` 枚举待确认。
  - 之前 MCP 返回的 `524 unknown 不在白名单列表里` 是 **MCP 工具层的授权映射问题**，不代表直连 API 未授权；库存查询应以直连 API 为准。
- **重要更正（2026-11-11 晚）**：
  - 直连 `available=10,112,699` 与 EN 镜像 `10,112,641` 的 58 件差异，是**今天早上通途有 PO 入库**造成的，不是口径不一致。
  - `FZHPoland-finished` 成品仓**已弃用**，不属于供给线范围；仓内仍有 22 个 SKU / 614 件残量，**仅作记录，备用时再查**，不补进 C/E。
  - 波兰供给线只认 **`波兰-FZHPoland-covers`** 一个仓；退货仓、京东波兰仓不在本项目范围内。

因此：

- **直连 API 可以拿到当前波兰皮壳仓库存快照；9–10 月历史可以用每天的通途库存备份/变动备份回放**（`wx_inventory_history.duckdb`、`pengjian_inventory_history.duckdb`、`en_stock_change.parquet`），不必只依赖 API 的 7 天窗口。
- 波兰外部订单（Allegro/Empik 等）**不走通途订单**，所以通途的正常订单扣减不包含它们；需要波兰每周报给彭建，由彭建在通途里手动扣减（王弦离职前是她做）。
- `Poland Order` 与 `orders_unified` 交集为 0，正好印证这一点。
- 2026-11-05 11:04 彭建的一张“其他出库”凭证（110 SKU / −195 件）**极可能就是 10 月波兰外部订单的批量扣减**；10 月 `Poland Order` 还没收到，暂不能逐单核对。
- 这种“每周人工批量扣减”很容易出错；后续应把波兰外部订单直接接进库存扣减链路（程序化生成其他出库单），不再靠人手。

建议：
1. 用每天的库存备份做 Sep–Oct 逐 SKU 库存差，减去同期通途正常订单销量，得到“非订单扣减”残差，再与 `Poland Order` 月度销量对比，验证彭建的批量扣减是否完整；
2. 让彭建提供 9–10 月“其他出库”凭证清单（或从通途 仓储管理 > 出入库明细 导出，仓库选 `波兰-FZHPoland-covers`，操作时间最近 3 个月）；
3. 后续把 `Poland Order` 接入自动扣减：按周生成“其他出库”草稿，人工只做确认。

### 8b. 近 7 天库存变动台账（2026-11-11 直连实测）

`stocksChangeDetailQuery` 能返回：`operaterUserName`、`relatedVoucherTypeName`、`relatedVoucherNumber`、`operateTime`、`availableStockIncrease / intransitStockIncrease / waitingShipmentStockIncrease / defectsStockIncrease`。

波兰皮壳仓（`波兰-FZHPoland-covers`）2026-11-05 至 11-10 共 **694 条**变动：

| 凭证类型 | 条数 | 操作人 |
|---|---:|---|
| 包裹 | 428 | 邓思怡 |
| 订单 | 133 | 邓思怡 |
| **其他出库** | **110** | **彭建** |
| 报溢 | 13 | 邓思怡 |
| 采购单 | 5 | — |
| 拆包 | 3 | 邓思怡 |
| 报损 | 2 | 邓思怡 |

关键点：

- **手动扣减确实存在，且台账可审计**：2026-11-05 11:04:18，彭建用一张“其他出库”凭证（`6464013595202611050074356849`）一次性扣了 **110 个 SKU / −195 件**（其中 103 个成品 SKU −185 件、7 个 `-Cover` −10 件），全部发生在皮壳仓。
- **王弦（WX）未出现在近 7 天操作人里**；当前订单/包裹扣减由邓思怡执行，批量手工扣减由彭建执行。
- 这 110 个 SKU 与彭建 11/10 Excel 的 56 个优先 SKU **有 18 个交集**；但不含 SO-135/136 的 `KS0307/KS0198`。
- `FZHPoland-finished` 近 7 天 **0 条变动**；该仓在通途里 `status=0`（停用），但仍有 22 个 SKU / **614 件**可用库存——EN 镜像与 C 都没读它。
- 因此“没有台账”的说法不成立；真实约束是**接口只能回溯 7 天**，9–10 月历史需要通途网页导出或业务方提供凭证清单。

## 9. 对 A / B / C 的具体影响

### A SKU 宇宙

- 当前 A 只看 2026 通途销量 / 2025 下单 / current owner；**漏掉 Poland Order 的 1,217 件**。
- `KS0307-KQC-26-WHITE`：A 有（2026 销量 120、库存 55）；D1b active/PL；但 D3b current-owner 分类是 `no_demand` / `eligible=False`。**A 与 D3b 不一致**。
- `KS0198-DRKQC-116-GREY`：A 有（2026 销量 79、库存 0）；D1b PL active/完整，另有 USNJ/USTX mismatch 行；D3b PL `smooth/eligible=True`，owner 行为 PL。
- 两件都在 A/B/C，不是“因为重新启用才进 A”；重新启用只解决 SO 上传。

### B 归属

- 波兰独立订单应归 **波兰公司**，不能进 USNJ/USTX；当前 B 对波兰 owner 多为空/own90，需补“波兰独立账号”这个 owner 证据。
- `KS0198` 在 D1b 有 USNJ/USTX 的 mismatch 行，必须保留“不跨仓/不混 owner”。

### C 库存

- 波兰仓库存与 Poland Order 销量必须对账：若 9/10 月手动扣减未入账，C 高估；若已扣减但无台账，C 不可审计。
- 建议新增 `poland_stock_adjustment` 明细（日期、SKU、数量、原因、操作人），或直接把波兰独立订单作为出库事实。

### 建议的数据整合顺序

1. **先加订单事实**：Poland Order → `orders_unified`，字段 `source='poland_order_gsheet'`、`source_order_id`、`channel`、`sale_date`、`sku_tongtool`、`product_id`、`qty`、`currency`、`amount`；不要写入 EN Sales Order（EN SO 是生产/补货单，不是平台零售单）。
2. **再重建 D3b/D5**：把波兰独立销量并入 Poland 需求；A 的“2026 销量”同步加上；B owner=波兰。
3. **再对 C**：用 Poland Order 出库事实或王弦调整台账扣减波兰仓库存；两者只能取一个，避免双扣。
4. **最后才判断波兰请求是否合理**：现在 v5.4 只纳入了 3 张 SO，**没有纳入 Poland Order 的 1,217 件**，所以还不能对 510 件差异下最终结论。

## 10. 当前版本状态

- v5.4 已纳入 SO-00135/00136/00137 共 3,674 件；49 个波兰键/2,064 件匹配。
- 但 **v5.4 仍未纳入 Poland Order 独立销量 1,217 件**；因此它只是“SO 修正版”，不是“波兰全量需求版”。
- 下一版 v5.5 应先把 Poland Order 并入 orders_unified，再重跑 D3b/D5/D6/CNY。

