---
okf: v0.1
type: Research
title: 把 Settlement V2（账期/活动）接到 FBM/FBA 订单：对齐口径调研（2026-10）
description: 论证 Settlement V2 的结算轴与活动轴要分开、订单必须按 orderId 多月份回看、FBM 走通途非FBA多月份导出、FBA 以 EN 订单同步为主并保留通途缺口，给出可落地的匹配规则与下一步
tags: [amazon, settlement-v2, fbm, fba, order-matching, cost, reconciliation]
timestamp: 2026-11-10
last_updated: 2026-11-10
resource: sellfox_settlement/reconcile_amazon.py
---

# 把 Settlement V2 接到 FBM/FBA 订单：对齐口径调研

## 1. 问题

要算 10 月 Amazon 的成本/利润，不能把"账期"直接对"某一个月通途订单文件"。需要回答三件事：

1. Settlement V2 的**结算轴**和**活动轴**怎么分？
2. 账期里的交易既有 10 月也有更早月份的单，订单该怎么回看？
3. FBM 和 FBA 分别从哪取订单/成本？EN 是否更全？

## 2. 实测数据（2026-10）

赛狐 Settlement V2（10 月窗口）：

- **汇总 groupPage**：107 个结算组，`groupEndStr` 全在 2026/10；按账期 10/4–11/3 口径已完成的审计是 **106 组 / 63 paid**。
- **明细 detailPage**：26,381 行，`postedDateTimeStr` **全部 2026-10**（`siteTimeStr` 有 133 行落在 9/30 时区边界）。
- 明细里 **MFN(FBM) 15,862 行 / 3,184 单**，**AFN(FBA) 9,513 行 / 1,651 单**，另有少量未标 fulfillment。
- 交易类型：Order 23,165 / Refund 2,190 / 其他-交易 461 / 清算 152 / 服务费 136 / AmazonFees 102 / FBAFees 94。

通途"202610 非FBA订单 尾程成品"文件：

- 6,292 行，**混有 WFUS/OSTKUS/…（Wayfair/Overstock 等）**；只保留 `渠道账号` 以 `AMZ` 开头的才是 Amazon。
- `订单号` 形如 `CUS-113-XXXXXXX-XXXXXXX`（`CUS-` + Amazon 订单号），子单可能带 `_1/-1` 后缀。
- `发货日期` 覆盖 2026-10-01~10-31，**只含 FBM**。

关键交叉结果（按"从订单号里提取 3-7-7 Amazon 单号"归一后）：

- **各账号的通途 `订单号` 前缀不同**：Centrade 是 `CUS-…`，如泱是 `BJRYECLTUS-…`，百纳是 `BNKCUS-…`，Daneey 是 `DANEEYUS-…`。只去 `CUS-` 会漏掉其他店；必须用正则从任意前缀里取出 `\d{3}-\d{7}-\d{7}`。
- 按上述归一后，V2 的 **MFN 活动单 3,184** 中 **3,165（99.4%）**能在 202607–202610 的通途非FBA文件里找到，**仅 19 单缺失**。
- 但**单看 10 月发货文件只覆盖 1,826 单**；补上 **9 月再加 1,322 单**（8 月仅 +17、7 月 +0）。**即约 42% 的 10 月记账 FBM 单是 9 月发货的**——多月份回看是必需项。
- V2 的 **AFN(FBA) 1,652 单**在非FBA文件里 **0 命中**；改用订单号集合直查 EN `tabTongtool Order`（`platform_code=amazon`，单次只读扫描约 34s）：**1,583 命中（95.8%，`order_type` 全为 FBA），缺 69**。
- **合并覆盖率**：FBM 3,165/3,184 + FBA 1,583/1,652 = **4,748/4,836（98.2%）**可在订单侧定位；缺口约 88 单进入异常清单。

结论：**"10 月账期明细"和"10 月发货订单"不是同一批单**。账期按打款/记账时间，订单按发货/下单时间；卖货发生在 9 月、费用/退款在 10 月入账是常态。

## 3. 项目已有的正确做法（别另起炉灶）

Codex 那套 `sellfox_settlement` 已经明确分开两套窗口：

- `payout_activity_bridge.py`：*"distinct settlement and activity windows remain distinct"* —— 活动 CSV 行与 payout V2 事件按 settlementId/siteTime/postedTime 建立**证据链**，不合并成同一期间。
- `account_cost_bridge.py`：订单→成本的连接用 **`base_order_id` + 归一化 SKU**，并声明"唯一订单/SKU 连接才算证据，不做全局成本兜底"。
- `cost_validation.base_order_id`：负责 `CUS-` 前缀与 `_1/-1` 子单的归一。

## 4. 建议口径

1. **两层分开，不混轴**：
   - **结算层（回款/银行桥）**：用 groupPage 的结算组（10/4–11/3、106 组/63 paid），只回答"钱什么时候到账/预留"。
   - **活动层（成本/交易连接）**：用 detailPage 的 posted 交易（26,381 行），按 `orderId` 接订单。
2. **连接键**：`base_order_id（去 CUS-、去 _1/-1 → 3-7-7 订单号） + 归一化 SKU`；**未匹配一律保留**，不按行位置、不按总额兜底。
3. **多月份回看**：订单查询窗口至少覆盖 **2026-09 ~ 2026-10**（建议 08–11）。原因是约 **42% 的 10 月记账 FBM 单是 9 月发货的**，10 月单月发货文件只覆盖 1,826/3,184；补 9 月后达 99.4%。
4. **FBM**：通途非FBA导出按**多个月份**拉（每份按发货日期），过滤 `AMZ*`，按上面连接键接成本/尾程。
5. **FBA**：
   - 商品成本用 **EN BOM / Tongtool Cost Review**；
   - Amazon 的 FBA 履约/仓储费**已在 Settlement V2 / 月度报表里**，不要再用内部尾程重复计；
   - FBA 订单明细**以 EN 订单同步为主**（比通途更全），通途 FBA 作补充；
   - 通途 FBA 已知缺口要保留：**FBA SKU 未及时登记、同步比实际晚几天、SKU 改名导致精确匹配漏行**（见 `tongtool_order_cost/docs/research/2026-08-14-june-fba-sku-remap.md`）。
6. **EN 是否"更全"**：对 FBA 是（同步覆盖/明细更完整），但 EN 的数据本身也源自通途，不是独立源；必须**实测覆盖率**，不能假设全。

## 5. 下一步（可执行）

1. 拉通途非FBA **2026-08/09/10/11** 四个月导出（按发货日期），过滤 AMZ，建 `orderId→包裹/尾程` 索引。
2. 拉 EN 订单 **2026-08 ~ 2026-11**（FBA+FBM），建 `orderId→SKU/数量/成本` 索引。
3. **（已实测）三向覆盖**：FBM 单 → 通途（202607–10，99.4%）；FBA 单 → EN（95.8%）；合计 98.2%。缺口约 88 单进异常清单，不补猜数。
4. 只有覆盖率达标后，才把成本/交易连接写进十表工作簿的第 7、9 表；不足的标"输入缺失"，不补猜数。

## 6. 执行进度（2026-11-10）

- 赛狐 V2 已拉：`sellfox_v2_202610/summary.csv`（107 组）、`detail.csv`（26,381 行）。
- 通途非FBA 202607–202610 建索引：FBM 覆盖 **99.4%（3,165/3,184）**，缺 19。
- EN `tabTongtool Order` 按订单号集合直查：FBA 覆盖 **95.8%（1,583/1,652）**，缺 69。
- EN FBA 明细已拉：**1,583 单 / 1,595 条明细，全部含 `item_cost`；FBA 无包裹号**（Amazon 履约）。
- 待做：FBM 侧从通途文件取尾程/成本字段；把 V2 交易行按 `订单号+SKU` 连到成本证据；再填十表的第 7（成本覆盖）、9（V2交易连接）表。缺口约 88 单进异常清单，不补猜数。

## 7. 参考

- `sellfox_settlement/docs/research/2026-10-09-amazon-non-v2-monthly-tax-analysis.md`（十表口径与分层）
- `tongtool_order_cost/docs/research/2026-08-14-june-fba-sku-remap.md`（FBA 缺口/SKU 改名）
- `sellfox_settlement/reconcile_amazon.py`（V2 拉取）
- `sellfox_settlement/account_cost_bridge.py`、`payout_activity_bridge.py`（订单+SKU 证据链、结算/活动分窗）
