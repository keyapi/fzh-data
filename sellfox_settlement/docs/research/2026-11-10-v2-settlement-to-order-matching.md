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
- **V2→成本连接已跑**（`十表V2成本连接_202610_*.xlsx`）：交易行 **FBM 99.1%（15,713/15,862）、FBA 95.8%（9,116/9,513）**；订单级 **FBM 99.4%（3,067/3,084）、FBA 95.9%（1,556/1,623）**；未匹配订单 84 个进异常。无 fulfillmentId 的 1,006 行是费用/调整/转账，不参与订单连接。
- **账号→运营贡献毛利（修正版）**（`Amazon运营利润_202610_*.xlsx`）：修正两处成本口径 —— ① 通途 `商品成本` 是**行合计**、不能乘数量（先前重复计入）；② EN FBA `item_cost` **全为 0**，FBA 商品成本暂缺（**FBA 占销售 24.8%**）。修正后：净销售 242.8万、平台费 -112.0万、成本 112.7万、**贡献 +18.1万（+7.5%，因 FBA 成本未计而偏高）**。按运营：井海坡 +32.0万、荆春雨 +0.4万、刘小菁 -5.9万、陈立彬 -2.8万、苏燕星 -2.1万…。**下一步用 EN BOM 补 FBA 成本再定稿。**
- 待做：结算银行桥（缺银行到账输入）、账号法人（待 ZJ 法人表），其余表可从 PDF/V2 汇总后合成十表。

## 7. 84 个未匹配订单：原因（已核到 EN）

- **FBA 67**：EN 里**完全没有**该订单 → 通途 FBA 未导入。其中 **62 个集中在 `百纳-BNCKTRD-US`**，`Daneey-LELEFIDO-NL` 3、`FZH深圳-Strusery-US` 1、`北京如森-Rucener-DE` 1。扩更早月份**无效**（不是回看不够，是没导入）。
- **FBM 17**：EN 里有（`order_type=自发货`），销售时间 9/8–9/22（10 个）或 10 月（7 个），**`despatch_complete_time` 多为空（14 个未发货）、3 个 11 月才发** → 不在"按发货日期"的通途导出。属**未发货/晚发**，不是丢数。

**结论：84 个不是"月份不够"，扩到 8 月或更早不会改善。** FBA 缺是导入缺口（先查百纳美国），FBM 缺是未发货。

**这 67 单影响多大 / 能不能补成本**：145 件、销售额约 $23.3k、平台费约 $10.5k（约占美国站销售 7%）。V2 明细已给 `msku + 数量 + 销售日`；13 个 msku 中 **11 个能在 EN `Item Customer Detail.ref_code` 映射到物料**（如 `BNvelvetblack-138fba → KS0001-HLR-140-BLACK`），**成本可按 EN BOM 取，不必依赖订单行**；余 2 个补别名。赛狐订单可选、不阻塞。

## 8. 退款：V2 里有、且大量跨月

- V2 10 月 `Refund` 行 **2,190 行 / 393 个订单**。
- 按原单发货/销售月：**2026-08 20、2026-09 197、2026-10 160、未知 16** → **约 55% 的 10 月退款来自 8/9 月的单**。
- 退款**确实在 V2 里**（含退款本金、税、佣金退回等），必须按 `orderId` 连回原单，并保留"原单月 vs 记账月"两列。冲减原月还是计入退款月，是会计口径，待 ZJ 确认。

## 9. 订单主数据：EN / 通途导出 / 通途 API 的分工

- **EN `tabTongtool Order`**：按**销售时间**同步，**未发货的也在**（`despatch_complete_time` 为空）→ 适合"订单存在性/销售归属"主数据。
- **通途非FBA导出**：按**发货日期**，只有已发货 → 适合取**尾程/发货成本**；未发货单不在。
- **通途 API**：可实时查订单（含 FBA），补 EN 未导入的（如百纳美国 62 单）。
- 结论：**订单存在性以 EN/通途 API 为准，发货与尾程以通途导出为准**；FBA 同理。

## 10. 行业做法（外部调研）

- Settlement report 是**现金与费用的唯一真相**（posted-date），**不是 COGS 真相**；贡献毛利要另配各 SKU 成本。
- 勾稽按 `order id + posted date + 时区`；退款、费用纠正、赔偿都可能**跨期**。
- **账户级费用**（仓储、长期仓储、订阅等）**没有 SKU/订单号**；按"有 SKU"过滤会把它们丢掉，毛利率虚高 1–3 个点。
- **预留金（reserve）是资产负债表项**，不是费用；不要当亏损。
- **站外广告不在结算里** → 基于结算的 TACoS 会低估。
- 40+ `amount-description` 归 6 个 P&L 块：销售额、促销、退款、佣金、FBA 费、其他调整；赔偿/chargeback 单列。
- 来源：<https://www.datadoe.com/blog-posts/amazon-settlement-reports-reconciliation>、<https://novadata.io/resources/blog/amazon-settlement-report-guide>、<https://thefbaguys.com/blog/how-to-read-amazon-settlement-report>、<https://www.neonpanel.com/blog/amazon-seller-reconciliation-payments-fees-inventory>

## 11. 修订后的规划：V2 如何用于"运营利润业绩"

1. **费用真相层**：V2 逐行按 amount-type/description 归 6 块；**保留无 SKU 的账户级费用**，单列"未分摊费用池"。
2. **订单层**：EN 为订单主数据（含未发货）；通途导出取发货/尾程；通途 API 补 FBA。
3. **成本层**：SKU 成本（EN BOM/Cost Review）+ 头程 + 尾程（通途运费/EN 预估）+ FBA 履约费（V2）。
4. **退款/退货**：退款按 orderId 连原单，原单月/记账月双列；退货入库与不可售另记。
5. **分摊**：账户级费用、站外广告、赔偿/chargeback 单列，再按 销售额/件数/仓储体积 分摊到 账号/SKU/运营。
6. **业绩口径**：账号 → 运营 → SKU/ASIN 的 毛销售、退款率、平台费、广告、COGS、贡献毛利；预留金只做现金层。
7. **必查项**：百纳美国 FBA 未导入 62 单；FBM 未发货 14 单是否在途；站外广告缺失；账户级费用未分摊。

**口径（已解决）**：赛狐 V2 `detailPage` 的 `currency` 是**折算目标币种**（传 USD 会把 26,381 行全转成 USD），不是过滤。取原币的正确做法：**每个结算组在 summary 里有原生币种；在 `currency=该原生币种` 的那份明细里，该组金额即原值**（已验证 EUR/USD 为 identity）。据此重建「V2费用真相_原币202610_*.xlsx」：26,381 行仅 15 行回退，**按币种原币合计×202610 汇率与门店 RMB 合计精确勾稽**（USD 338,174×6.7367 + EUR 53,222×7.5404 + CAD/SEK/CNY）。不再用赛狐当日汇率。

## 12. 参考

- `sellfox_settlement/docs/research/2026-10-09-amazon-non-v2-monthly-tax-analysis.md`（十表口径与分层）
- `tongtool_order_cost/docs/research/2026-08-14-june-fba-sku-remap.md`（FBA 缺口/SKU 改名）
- `sellfox_settlement/reconcile_amazon.py`（V2 拉取）
- `sellfox_settlement/account_cost_bridge.py`、`payout_activity_bridge.py`（订单+SKU 证据链、结算/活动分窗）
