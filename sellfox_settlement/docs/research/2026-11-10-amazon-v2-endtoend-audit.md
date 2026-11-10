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

## 5. 来源

- Nova 结算指南（六块、账户级费用、预留、off-account 广告）：<https://novadata.io/resources/blog/amazon-settlement-report-guide>
- A2X 退款冲 COGS（仅退回库存时）：<https://www.a2xaccounting.com/blog/include-refunds-in-cogs-postings-beta>
- Finaloop Deferred/DD+7 权责调整：<https://help.finaloop.com/en/articles/10499774-amazon-deferred-transactions-what-changed-for-your-books>
- Link My Books Deferred：<https://linkmybooks.com/blog/amazon-deferred-transactions>
- The FBA Guys 结算与 P&L 边界：<https://thefbaguys.com/blog/how-to-read-amazon-settlement-report>
- Sellerboard 报表结构（费用/退款成本/COGS 拆分）：<https://help.sellerboard.com/2-1-8-reports>
