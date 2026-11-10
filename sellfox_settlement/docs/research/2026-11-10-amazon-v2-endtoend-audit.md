---
okf: v0.1
type: Research
title: Amazon V2（Settlement）端到端处理逐步审核（2026-10）
description: 对照业界成熟工具与 Amazon 官方报表口径，逐步审核本项目从 V2 取数到 SKU 利润的每个环节，列出符合项、缺口、风险与修复建议，供与 Cursor 讨论
tags: [amazon, settlement-v2, audit, profit, cogs, deferred, returns, pnl]
timestamp: 2026-11-10
last_updated: 2026-11-10
resource: sellfox_settlement/docs/research/2026-11-10-v2-settlement-to-order-matching.md
---

# Amazon V2 端到端处理逐步审核（2026-10）

> 目的：把"我们怎么用 V2 算运营利润"与**业界成熟做法**逐步对照，指出哪里对、哪里偏、哪里缺。供用户与 Cursor 复核。不是申报依据。

## 1. 业界标准链路（Settlement 视角）

成熟工具（A2X / InventoryLab / Sellerboard / Finaloop / Nova / Link My Books）的共识链路：

1. **取数**：Settlement（Financial Events / Flat File V2），按 **posted date**；与订单系统的 **order date** 不能混用。
2. **币种**：按**原币**记，再按财务确认的月汇率折算；不要用平台当日汇率混算。
3. **费用归类**：40+ `amount-description` → 6 个 P&L 块（销售额、促销、退款、佣金、FBA 费、其他调整）。
4. **账户级费用**：仓储/长期仓储/订阅等**无 SKU 无订单号**，必须单列，不能按"有 SKU"过滤掉（否则毛利虚高 1–3 点）。
5. **预留金/转账**：reserve 是**资产负债表项**，不是费用；只影响现金，不进 P&L。
6. **退款**：可**归到原销售月**（Nova 默认）或退款月（现金口径），需财务定；**可售退货冲回 COGS 并恢复库存**，不可售转损失。
7. **赔偿/拒付/调整**：单独桶；reimbursement 是**其他收入**，不冲 COGS。
8. **Deferred（DD+7）**：2025 起延迟交易；权责发生制按**履约（发货）日**确认收入，不按放款日；2026 起报表增强。
9. **COGS**：Settlement 只是费用真相，**不是 COGS 真相**；COGS=货值+头程+关税+入仓，按 SKU 配；退货按可售性处理。
10. **广告**：on-account 在结算里；**off-account 不在** → 基于结算的 TACoS 低估。
11. **分摊**：账户级费用/广告按销售额/件数/体积分摊到 账号/SKU/运营。
12. **输出**：SKU/ASIN 与运营的贡献毛利、退款率、平台费率、真实 ACOS。

来源：<https://novadata.io/resources/blog/amazon-settlement-report-guide>、<https://www.a2xaccounting.com/blog/include-refunds-in-cogs-postings-beta>、<https://help.finaloop.com/en/articles/10499774-amazon-deferred-transactions-what-changed-for-your-books>、<https://linkmybooks.com/blog/amazon-deferred-transactions>、<https://help.sellerboard.com/2-1-8-reports>、<https://thefbaguys.com/blog/how-to-read-amazon-settlement-report>

## 2. 逐步审核

| # | 环节 | 我们的做法 | 业界标准 | 结论 | 缺口/风险 |
|---|---|---|---|---|---|
| 1 | 取数期间 | V2 detail 按 **posted 日期** 2026-10 | Settlement=posted date；Business/订单=order date，不混 | ✅ 对 | 未拉 deferred/放款状态 |
| 2 | 币种 | `currency` 是折算目标币；按结算组原生币种取原值，再×202610 | 原币记账+财务月汇率 | ✅ 对（已修正） | 15 行回退 |
| 3 | 费用归类 | 销售额/促销/退款/佣金/FBA/其他调整/代扣税/赔偿 | 40+→6 块 | ✅ 大体对 | `其他调整 -14.3万` 是**混合桶**，未拆 chargeback/清算/调整 |
| 4 | 账户级费用 | 单列，不分摊 | 单列、不可丢 | ✅ 单列 | ❌ **未分摊**（48.9万；分摊后贡献约 -42.5万） |
| 5 | 预留/转账 | 未纳入 P&L | reserve 不上 P&L | ✅ 对 | 未取 reserve 行比对（现金层） |
| 6 | 退款 | 计入**退款月**（posted），不冲 COGS | 可归原销售月；可售退货冲 COGS | ⚠️ 口径需定 | ❌ 未按原月归集；❌ 未冲 COGS（V2 退款行件数=0） |
| 7 | 赔偿/拒付 | 赔偿单列但**未计入贡献** | reimbursement=其他收入，应计入 | ⚠️ 偏差 | 赔偿 +5,811 未进贡献；chargeback 混在其他调整 |
| 8 | Deferred/DD+7 | 未处理 | 按履约日确认；deferred 单列 | ❌ **缺** | 10 月收入/费用可能跨月错配 |
| 9 | 订单匹配 | FBM→通途 4 月 99.4%；FBA→EN 95.8% | order id+SKU，未匹配保留 | ✅ 对 | 84 单缺（百纳美国 FBA 62，未发货 FBM 17） |
| 10 | COGS | FBM 通途行合计 + FBA EN BOM 单价×件 | 货值+头程+关税+入仓，按 SKU | ✅ 结构对 | 当前 BOM 非历史；退货未冲；226 FBA 条无物料号 |
| 11 | 头程/加工/尾程 | 头程/加工/尾程按行合计相加 | 同 | ✅ 对 | **尾程 71% 是 EN 预估**，非通途实际 |
| 12 | 广告 | V2 `Cost of Advertising` 账号层 | on-account 在结算；off-account 另取 | ⚠️ 部分 | ❌ off-account 广告缺失 |
| 13 | 分摊 | 未分摊 | 账户级/广告按规则分摊 | ❌ 缺 | 影响 SKU/运营真实贡献 |
| 14 | 输出 | 账号→运营、SKU 表，与账号版勾稽 | SKU/ASIN P&L | ✅ 已出 | 依赖上面口径 |
| 15 | 对账控制 | settlement 组 107/106；PDF vs V2 未逐份对 | total-amount 对账、PDF 控制数 | ⚠️ 部分 | 未做 Settlement total vs 明细合计的对账 |

## 3. 结论分级

**符合业界标准**：原币+月汇率、费用六分块、账户级费用单列、预留不进 P&L、订单+SKU 连接、COGS 结构、SKU/账号勾稽。

**高风险缺口（必须先解决再定稿）**：
1. **Deferred/DD+7 未处理** → 10 月收入/费用跨月错配。
2. **退款月份归属未定**（退款月 vs 原销售月），且**未冲 COGS**（需 Inventory Ledger）。
3. **账户级费用未分摊**（48.9 万）。
4. **off-account 广告缺失** → 真实 ACOS/TACoS 低估。
5. **尾程 71% 为预估**。

**中风险**：其他调整混合桶、赔偿未计入贡献、FBA 226 条无物料号 + 百纳 64 行、当前 BOM 非历史、特殊规则业绩成本待对齐。

**低风险**：15 行汇率回退、94 条成本缺失行、1 个未匹配店铺。

## 4. 给 Cursor 的待办清单

1. 拉 **Deferred/DD+7** 明细（按履约日），做 10 月权责调整方案。
2. 定退款口径（原月 vs 退款月），并接 **Inventory Ledger/退货报告** 做可售退货冲 COGS。
3. 账户级费用（仓储/订阅）与 ads 按 销售额/件数/体积 分摊到 账号/SKU/运营。
4. 拆 `其他调整`（chargeback/清算/调整/赔偿）。
5. 取 **off-account 广告**（Amazon Ads）补 TACoS。
6. 尾程改为通途实际（当前 EN 预估 71%）。
7. 成本源做成可切换：EN BOM（会计） vs 特殊规则（运营业绩）。
8. 补 226 条无 `erp_item_code` 的 FBA 明细 + 百纳美国 64 行。
9. 增加对账页：Settlement total-amount = 各科目合计；PDF 控制数 vs V2。

## 6. Cursor 评审结论（Orca worker `v2-audit-review`）

- **-42.6万 是 posted-date 的现金月贡献，不是 10 月权责利润**；+6.4万（含广告）与 -42.6万（再摊账户级费用）是同一条路径，**广告只算一次**，非重复。
- 抬高利润的缺口：226 条 FBA 无 `erp_item_code`、百纳美国 62 单缺 EN、17 单 FBM 未发货；退款无 COGS 冲回；赔偿 +5,811 未进贡献；`其他调整 -14.3万` 混合未拆；Settlement total 未与明细对平（107 vs 106 组）。
- 需确认：BOM 单价是否已含头程（我们又在旁边加了头程，可能重复）；BOM 为当前值非 10 月历史。
- **分摊**：按同店销售额分摊**不改变公司总额**；订阅费可用销售额，**仓储应按体积/库龄、广告应按 Sponsored Products SKU 报表**分摊；单店统一费率会让每个 SKU 同 TACoS，**运营排名是分摊结果**。
- **Cursor 给的优先级**：① 对账（Settlement total=明细合计）+ 拆其他调整 + 一条从 +6.4万 到 -42.6万 的桥；② 补 DD+7 递延滚动；③ 尾程换承运商实际；④ Inventory Ledger 冲可售退货 COGS、未发货 FBM 不结成本、百纳/226 缺口用历史 BOM 补；⑤ 补 off-account 广告，仓储按体积、广告按 SP SKU 报表分摊。

## 7. V2 全科目映射与校验

- V2 detail 共 **100 个（transactionType×amountType×amountDescription）组合 / 26,381 行 / 净额 1,107,645.40 CNY**；映射到 **Summary 分区（Income/Expenses/Tax/Transfers）+ P&L 桶**，**未映射 0 个**，桶汇总=总额（`V2科目全表_202610_*.xlsx`）。
- 之前"6 块"确实漏项：仓储/长期仓储、订阅、Deal、优惠券、数字服务、入库配置、退货运单、债务调整、准备金、代收税、赔偿明细等，现已全部落桶。
- **官方依据**：SP-API Settlement 报表只定义 `amount-type/amount-description/amount` 三列；Amazon 未公开逐描述字典。官方分类以 Seller Central **Summary/Account activity** 报表为准。**第三方标准字典**：A2X《Amazon Seller Fees & Transactions》全量表、Entriwise 132 项费用词典（明确取自 settlement/reimbursement/returns 的 amount-type/amount-description/reason code）、Sellerboard《Amazon Seller Fees》指南。本映射按这些字典 + Summary 科目核对，逐条标 `官方依据/置信度`；**最终完整性 = 每店 V2 汇总与当月 Summary PDF 对平**。
  - <https://www.a2xaccounting.com/ecommerce-accounting-hub/amazon-transaction-types-and-fees>
  - <https://www.entriwise.com/blog/amazon-seller-fees-quickbooks-glossary>
  - <https://blog.sellerboard.com/2023/07/12/a-comprehensive-guide-to-amazon-seller-fees>

## 8. 退货与库存数据源（赛狐 API 已具备）

- `销售/退货报告/FBA退货报告查询`、`销售/退货报告/FBM退货报告查询` → 退货件数与明细。
- `仓库/库存流水/获取库存流水`（Inventory Ledger）、`仓库/库存明细/查询库存明细`、`仓库/FBA库存/查询FBA库存明细` → 库存增减与处置。
- 结论：**可售退货冲 COGS、不可售转损失**所需数据，赛狐 API 能取。OpenAPI 路径（出自本仓库 `SELLFOX_API/docs` 镜像）：
  - FBA 退货：`/api/order/api/report/fbaReturn/pageList.json`
  - FBM 退货：`/api/order/api/report/fbm/return/order/pageList.json`
  - 库存流水：`/api/warehouseInOut/inOutRecords.json`
- **实调确认（2026-11，非推测）**：
  - FBA 退货接口可用：传 `returnStartDate/returnEndDate` 即返回；10 月 **146 件**，字段含 `detailedDisposition`（可售/买家损坏/承运人损坏/不可售）与 `status`（商品已退回库存/立即清货/已赔偿/自动捐赠）。分布：**可售 52、买家损坏 91、承运人损坏 1、不可售 2** → **仅 52 件可冲 COGS**。
  - 库存流水接口存在，但当前 API Key **无权限**（`code=40021 访问的接口暂无权限`），需在赛狐开通"仓库/库存流水"权限。

## 9. BOM 成本标准（解决"头程是否重复"）

- **用的是哪个表**：`EN上传Cost Review预估尾程 通途非FBA订单202610 202611020918.xlsx` —— 即把通途非FBA订单上传到 EN「上传通途订单Excel（`process_order_excel_for_costs`）」后**回出的成本表**；字段 `商品成本/绍兴发货成本/头程费用/加工成本/最终尾程` 均来自 EN 成本引擎。它是**某一时点的输出**，不是历史成本；EN 侧成本会修正，**口径待与另一对话对齐后才算定稿**。
- 项目标准（`docs/bom_cost_explanation.md`）：**尾程前成本 = 绍兴发货成本 + 头程 + 加工**；再加尾程 = 全成本。
- 此前用 `商品成本 + 头程 + 加工`，若 `商品成本` 已含头程/加工会**重复**（实测 `商品成本` 77.84 vs `绍兴发货成本` 55.71，确非同一字段）。
- 已改为 **绍兴发货成本(按发货数量) + 头程(按发货数量) + 加工(按发货数量) + 尾程**。分摊后贡献由 -42.6万 修正为 **-32.1万（-13.2%）**；**成本口径一旦调整需重算**。

## 10. 首轮 V2 ↔ Summary PDF 对平（Income 分区，2026-10）

| 币种 | PDF income | V2 income | 差额 | PDF 文件数 |
|---|---:|---:|---:|---:|
| USD | 302,401.93 | 308,347.69 | -5,945.76 | 14 |
| EUR | 39,547.73 | 46,629.79 | -7,082.06 | 33 |
| SEK | 3,237.97 | 1,728.93 | +1,509.04 | 4 |
| GBP | 12.10 | 0 | +12.10 | 6 |
| CAD | 0 | 78.92 | -78.92 | 5 |
| MXN / PLN | 0 | 0 | 0 | 10 |

- **结论：未对平。** USD 约差 2%，EUR 差 18%，不能当"已校验"。
- **官方原因是设计使然**（不是我们算错）：Settlement 报表**按放款/释放时间**；Transaction/Summary 报表**按 posted date**；**deferred 在释放前不在结算报表**；2026 起报表同时含 deferred+released 并以 posted date 索引。来源：<https://sellercentral.amazon.ie/help/hub/reference/external/G200989190>、<https://sellercentral.amazon.com/help/hub/reference/external/GLRNLZDAKHDBBVBY>、<https://linkmybooks.com/blog/amazon-deferred-transactions>
- **组件级自查（DANEEY 美国，同店）**：毛销售 V2 19,698.90 vs PDF 20,711.02；退款 -3,328.65 vs -3,363.65；促销 -1,309.90 vs -993.10；代收税 1,287.56 vs 1,205.90；礼品包装 0 vs 5.99 —— **既有时间差，也有分类差**。
- 注意：PDF 的 `totals` 是**转账净额**（DANEEY 美国 income 16,925.95、totals -40.64），不能拿来比 V2 净额；只能用 Income/Expenses/Tax/Transfers 分区对。
- 待查原因：deferred/DD+7、退货与费用跨期、PDF income 与 V2 分区的定义差、JPY 币种未识别、每店映射（自动候选 41/73，需账户交叉表确认）。
- **逐店对平（改进匹配后）**：73 份 PDF **匹配 50 份**（品牌+国家前缀匹配；`DANEEY` 已与 `TOODDLY-Daneey` 区分）。**差额按店看、各店原币，不跨币种相加**。**转账分区二者不同义**（V2 Transfers 含预留/债务/现金，PDF transfers 是银行转账），不可直接对。剩 23 份多为 **V2 无该店（0 活动）** 或需账户交叉表定死。

## 11. 中国报税用哪张报表（业界经验）

- **平台报送（2025Q3 起，季度）**：亚马逊向中国税局报送 10 项——卖家记号、站点、公司名、统一社会信用代码、季度、**收入总额、退款金额、收入净额、佣金服务费合计、交易数量**。税局拿它和卖家申报比对。
- **中国申报口径（业界/税局）**：按**权责发生制、全额销售额**（含未回款），按**订单/发货时间**；**回款金额不能替代销售额**（回款=销售额−佣金−广告等，只作到账凭证）。
- **业界实际用哪张**：
  - **日期范围报告 / Transaction（Summary）** = 申报与"差异解释"的**核心证据**（活动/发货口径，含退款、税、运费、促销）。
  - **Settlement 报表** = **回款凭证 + 费用明细**（佣金/广告/FBA/仓储等，有税务认可电子签章），不直接当销售额。
  - 出口免税/退税另需**报关单 + 收汇 + 物流单据**。
- **"哪个更有利"不能选低报**：应按真实销售额（Date Range）申报，用结算单证明回款与费用；平台收入总额若**含 VAT/TAX 代收**、或汇率/日期口径不同，差异要能解释并剔除代收代缴税（需税务顾问确认）。卖家反馈"平台收入总额高 25–30%，主要是税被算进收入"。
- **对本项目**：**V2 用于费用/回款/利润**；**Date Range/Summary 用于申报销售额**；两者并用、互相解释，不能只用一个。
- 来源：<https://mydidadi.com/亚马逊披露的报税数据引发争议！数据对不上怎么办/>、<https://www.anl-cn.com/mobile/newsdetail/29.html>、<https://www.eccang.com/news/4990>

## 12. 来源

- Nova 结算指南（六块、账户级费用、预留、off-account 广告）：<https://novadata.io/resources/blog/amazon-settlement-report-guide>
- A2X 退款冲 COGS（仅退回库存时）：<https://www.a2xaccounting.com/blog/include-refunds-in-cogs-postings-beta>
- Finaloop Deferred/DD+7 权责调整：<https://help.finaloop.com/en/articles/10499774-amazon-deferred-transactions-what-changed-for-your-books>
- Link My Books Deferred：<https://linkmybooks.com/blog/amazon-deferred-transactions>
- The FBA Guys 结算与 P&L 边界：<https://thefbaguys.com/blog/how-to-read-amazon-settlement-report>
- Sellerboard 报表结构（费用/退款成本/COGS 拆分）：<https://help.sellerboard.com/2-1-8-reports>
