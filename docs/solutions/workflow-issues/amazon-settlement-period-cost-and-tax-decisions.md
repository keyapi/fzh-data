---
okf: v0.1
type: Reference
title: Amazon 结算口径与成本的四个决策（期间/退款/成本/税务）
date: 2026-11-10
category: workflow-issues
module: sellfox_settlement
problem_type: workflow_issue
component: tooling
severity: high
applies_when:
  - "决定用 settlement/posted/打款 哪个期间做利润或业绩"
  - "处理退款退货、尾程、预留金、Deferred 的会计口径"
  - "确定 Amazon 成本字段与 FBA 商品成本来源"
  - "回答中国报税用哪张报表、运营业绩怎么算"
tags: [amazon, settlement, profit, refund, cogs, china-tax, operator-kpi]
---

# Amazon 结算口径与成本的四个决策

## Context

Amazon 卖家常把"结算/回款/销售额"混在一起。实际上它们对应不同期间与用途；成本也有多个字段来源。这些问题不定死，指标就会忽高忽低、对不上税局。

## Guidance

1. **三种期间轴，别混**
   - **Settlement 结算组**：按放款/结算周期；`transferAmount`(打款) 已扣 Amazon 费用与**预留**。
   - **posted 记账日**：V2 明细的收入/费用口径；用于经营/会计。
   - **履约/发货日**：权责发生制、运营业绩的销售时点。
   - **预留金是资产负债表项**，不是费用；Deferred(DD+7) 在释放前不在结算报表里。
2. **退款/退货**
   - 可售退货：**冲回 COGS、库存恢复**；不可售/损坏：COGS 留损失。
   - **尾程/出库运费是沉没成本，不冲回**；Amazon 退佣金冲减费用；赔偿 = 其他收入。
   - 判可售靠 **FBA/FBM 退货报告的 `detailedDisposition` + `status`**（赛狐 API 有，实测 10 月 146 件中仅 52 件可售）。
3. **EN 成本字段**
   - 通途 Cost Review 回出的 `商品成本` 是**行合计**；`绍兴发货成本` 是**单价**。
   - 标准：**尾程前成本 = 绍兴发货成本 + 头程 + 加工**，再 + 尾程；别"商品成本 + 头程 + 加工"（可能重复）。
   - EN FBA 的 `item_cost` 实测全 0 → 用 **BOM 单价×数量**。
4. **中国报税与运营业绩**
   - 中国申报用 **Date Range / Transaction（订单/发货、全额销售额）**；Settlement 作**回款/费用凭证**；平台报送收入总额常含代收代缴税，差异要能解释。
   - 运营业绩可用**结算期贡献**：`accountNetIncome（剔除预留变动） − 订单明细匹配的产品/头程/尾程 − 其他`；**不要用打款 transferAmount**；退款回看原单成本。
   - 账户级费用/广告分摊：订阅按销售额、仓储按体积/库龄、广告按 SP SKU 报表；销售分成不改变公司总额。

## Why This Matters

口径混用会产生三种误导：把打款当销售额（月份错位）、把预留当费用（低估利润）、把行合计当单价（成本翻倍）。对税局，申报基数错会触发比对异常。

## When to Apply

月结、税务申报、运营考核、任何"收入 − 成本 = 利润"的口径设计。

## Examples

- 打款 ≠ 销售：DANEEY 美国 Summary income 16,925.95，而 totals（转账净额）只有 -40.64。
- 成本字段：`商品成本` 77.84 vs `绍兴发货成本` 55.71，乘数量会重复。
- 退款：10 月 2,190 行/393 单，约 55% 来自 8/9 月。

## Related

- `sellfox_settlement/docs/research/2026-11-10-amazon-v2-endtoend-audit.md`
- `sellfox_settlement/docs/research/2026-11-10-v2-settlement-to-order-matching.md`
- `docs/bom_cost_explanation.md`
