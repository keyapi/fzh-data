---
title: 账期/收款核算 生态地图（各平台账期 → 汇率/税/附加费 → 回款归属/回款率 → 归集给财务）
date: 2026-09-09
category: architecture-patterns
module: account-period-reconciliation
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - 需要理解「销售额/平台账期费用/回款」这条财务核算链路的整体拼图和每块数据源
  - 新增一个平台/渠道的账期对账，或改动某块账期数据源（如赛狐、钉钉、通途、汇率）时
tags: ["account-period", "reconciliation", "revenue", "settlement", "回款", "账期", "财务核算", "ecosystem", "map"]
related_components: [tooling]
---

# 账期/收款核算 生态地图

> **赛狐只是其中一块拼图。** 本条把「平台账期 → 汇率/税/附加费 → 回款归属/回款率 → 归集给财务/报税」整条链路的**各数据源、公共口径、现有资产**画成一张地图，放在 `docs/solutions/` 顶层作为该领域的**canonical 入口**，其它对账/账期文档都应该能被它索引到。

## 1. 背景 / 为什么
财务每月要把各平台回款整理成费用（销售额、佣金、广告、FBA、税、附加费…）、算回款率、报税（2026 跨境电商税收收紧）。数据散在：**通途订单**（销售额）、**各平台账期**（Amazon 结算/多平台账单）、**汇率**、**Tax/附加费**、**运营提交的钉钉审批**、**NAS 归桶**。赛狐只是 Amazon（部分多平台）账期的一个自动数据源。

## 2. 生态地图（拼图 → 数据源 → 资产指针）

| 拼图 | 说明 | 数据源 / 资产 |
|---|---|---|
| **销售额** | 订单/销售口径 | 通途订单导出(`tongtool_order_cost`、`tongtool-api` skill)；有些平台要**减去账期费用**得到净 |
| **Amazon 账期(结算)** | payout 打款口径，amount-description 行式 | 赛狐「结算中心V2」(`sellfox_settlement`、`sellfox-api` skill)；官方=SP-API `GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2` |
| **Amazon 账期(列式)** | activity/posted 口径、原币、列式 | 赛狐 `getPlugPageList type=3`(紫鸟插件已抓)；财务按月下载的 Custom Summary/Transaction |
| **其它平台账期** | 各平台对账 | Overstock/OSTKUS(`platform-account-reconciliation`)、PB(`pb-reconciliation`)、Wayfair(未来)、Temu/TikTok/Walmart/eBay/AliExpress/MercadoLibre/SHEIN/Shopify(赛狐有账单)、Home24/Mano等(无) |
| **汇率** | 固定月汇率 | 谷歌表「和财务部共享-汇率」(`colab 用 202607 列)；colab 用固定月汇率，**不用赛狐当日变动汇率** |
| **税(Tax)** | Amazon 代收代缴税 | 赛狐 `amountDescription Tax/MarketplaceFacilitator*`；旧解析只取 tax；`附加费&Tax` 表 `Tax{YYYYMM}` |
| **附加费** | 平台另计费用 | `附加费&Tax` 表 `附加费{YYYYMM}`（`tongtool-order-cost` 特殊规则/账期差异） |
| **回款归属** | 渠道账号 → 收款归属(欧洲公司/绍兴工厂…) | 渠道账号表(`en-channel-account-gsheet-sync`、`gsheet-access-and-channel-account.md`) |
| **回款率** | 应收金额/销售额 | 钉钉收款单的 `收款比例`；`approval_filter` 只留 完成/审批中 且 非拒绝 |
| **运营提交** | 钉钉「销售收款确认单」 | 审批流；`approval_filter=(审批状态∈[完成,审批中]) & 审批结果≠拒绝`；`账期迟交审计` |
| **归集/NAS** | 按发起时间 4号~下月3号 归桶 | NAS `账期YYYYMMDD-YYYYMMDD`；文件名 `Amazon&新平台成本 …_合并汇率&账号_….xlsx` |
| **报税** | 给中国税务 | Custom Summary/Transaction(列式)；`amazon-account-period-late-submission-audit` |

## 3. 公共口径（跨拼图通用，别各自定义）
- **账期归属** = `账期日期` 所在**自然月**（1号~月末）（Amazon 也可按**结算周期结束日** `groupEndStr` 归属）。
- **账期提交窗口** = 该账期月 **4号 ~ 下月3号**（早先 8号~下月7号；多留 3 天处理月底）。
- **提交时间** = 收款确认单**发起时间**；文件标题 `YYYYMMDD-YYYYMMDD` = 导出发起时间窗。
- **两口径**：**结算报告(settlement)=payout**、**日期范围报告(date-range/transaction)=activity/posted(含 deferred)**，总额**不同**、别对等。**做费用/科目用列式，做回款率/打款用结算**。
- **回款率** = 应收金额/销售额；**税净≈0**(Amazon 代收代缴)；off-account 广告不进结算 → 结算口径 TACoS 低估。
- **币种/汇率**：取**原币** + **财务固定月汇率**折算（colab 用「和财务部共享-汇率」）；避免源系统当日变动汇率。

## 4. 现有资产（docs/solutions + 模块 + 技能）
| 类别 | 资产 |
|---|---|
| docs/solutions | `tooling-decisions/amazon-settlement-autofetch-sellfox.md`(赛狐)+`workflow-issues/amazon-account-period-late-submission-audit.md`(迟交审计)+`workflow-issues/ostkus-account-reconciliation.md`+`.../pb-reconciliation-monthly-update.md`+`.../en-channel-account-gsheet-sync.md`+`.../tongtu-warehouse-rename-reconciliation.md`+`conventions/tongtu-en-sellfox-instock-sku-mainline.md` |
| 模块 | `sellfox_settlement/`(Amazon 自动取回, OKF bundle, `AGENT_HANDOFF.md`)、`platform-account-reconciliation`(OSTKUS)、`pb_reconciliation`、`tongtool_order_cost`、`channel_account_sync` |
| 技能 | `sellfox-amazon-settlement`、`platform-account-reconciliation`、`pb-reconciliation`、`sellfox-api`、`tongtool-api`、`tongtool-order-cost`、`tongtool-warehouse-sync` |
| 谷歌表 | 「和运营部共享」(渠道账号)、「和财务部共享」(汇率)、「附加费&Tax」(附加费/Tax) |

## 5. 缺口 / 待办（后续可交给更强模型）
1. **其它平台自动取回**：Wayfair、Home24/Mano/Allegro/Cdiscount/EMAGRO/HOUZZ/Worten/ePrice 赛狐无账单 → 短中期仍人工；Temu/TikTok/Walmart 等赛狐有账单可复用本套方法。
2. **多口径对平**：date-range vs settlement 目前**不相等**，需要建立「按 settlementId 逐笔」的对平表与差异报告。
3. **汇率统一**：把 colab 的固定月汇率接入本套工具，避免源系统当日汇率。
4. **4 号前取全**：验证赛狐/钉钉在月结窗口（4号导出上月）能否取全上月结算。
5. **广告**：off-account 广告需另取 Amazon Ads API / SKU Economics（结算口径 ACoS/TACoS 低估）。

## Related
- 赛狐 Amazon 自动取回：`tooling-decisions/amazon-settlement-autofetch-sellfox.md`、`sellfox_settlement/AGENT_HANDOFF.md`
- 迟交审计：`workflow-issues/amazon-account-period-late-submission-audit.md`
- 各平台对账：`workflow-issues/ostkus-account-reconciliation.md`、`.../pb-reconciliation-monthly-update.md`
