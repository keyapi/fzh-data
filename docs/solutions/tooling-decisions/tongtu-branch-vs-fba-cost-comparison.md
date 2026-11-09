---
okf: v0.1
type: Reference
title: 分公司发货 vs FBA 成本对比口径（共同成本 + 差异块，不夸大节省）
date: 2026-11-09
category: tooling-decisions
module: tongtool_order_cost
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - "财务问“自发货订单如果改走 FBA，成本差多少”"
  - "要解释分公司发货与 FBA 的成本差异来自哪几块"
  - "准备把差额当节省汇报前"
tags: [tongtu, fba, branch-cost, finance, cost-comparison]
---

## Context

财务问题：2026-07/08/09 月由美东 USNJ / 美中 USTX / 波兰 PL 三个分公司发货的订单，如果全部改走 FBA，成本如何变化。直接拿“分公司四列合计 vs FBA 四列合计”会重复计算共同成本，也会把不可比的部分混在一起。

## Guidance（本学习沉淀的做法）

### 拆分口径

| 块 | 分公司 | FBA |
|---|---|---|
| 共同成本（两条路相同，不产生差额） | 皮壳成本、绍兴包装半成品成本 | 同左 |
| 绍兴二次加工 | 分公司的“绍兴二次加工成本” | 成品包装成本 − 半成品包装成本 |
| 国外二次加工 | 分公司目的地的二次加工（valuation_rate） | 0（FBA 不做目的地加工） |
| 头程 | 按绍兴发货方式的头程 | 成品 FBA 头程（USFBA / DEFBA） |

- 分公司合计 = 皮壳 + 绍兴包装半成品 + 分公司绍兴二次 + 国外二次 + 分公司头程
- FBA 合计 = 皮壳 + 绍兴包装半成品 + FBA绍兴二次 + FBA头程
- 差额 = FBA 合计 − 分公司合计

### 必排项

- 单独卖 `-Cover/-Foam/-PPCotton` 的行（皮壳口径不同）；
- 无 FBA 头程的行（多为铁架/配件）；
- BOM 缺失行；
- 排除清单单独成表，不能静默丢。

### 必写边界（否则高估节省）

- 不含尾程/物流商运费；
- 不含 Amazon FBA 仓储/配送费（改 FBA 后是新增成本）；
- 同一 BOM 快照（三个月同版本，避免月间 BOM 差异）；
- 波兰 → 欧洲 FBA（DEFBA）是假设，实际国家/VAT/仓储费需业务确认；
- 非 Amazon 平台（WF/OS/PB/HOME24/Mirakl/Allegro 等）用 FBA 实际是 Amazon MCF，属商业/运营决策；
- 不是财务入账口径，正式采用前需财务/业务确认。

## Why This Works

- 共同成本在两条路都存在，放进任何一侧都会把差额算大或算小；
- 把差异拆成「绍兴二次 vs 国外二次」「头程成品 vs 按发货方式头程」两块，业务能看懂钱花在哪；
- 明确排除项和边界，避免把“未计入的 FBA 费用”当成节省。

## When to Apply

- 同类“分公司发货 vs FBA”对比；
- 需要给财务/运营解释成本结构变化；
- 评估某个仓库/产品线改 FBA 的可行性。

## Examples

2026-11-09 重算（按修正后的件数/产品族，202607-09 同口径）：

| 月份 | 分公司 | 分公司合计 | FBA合计 | 差额 | 差额% |
|---|---|---|---:|---:|---:|
| 202607 | PL | 213,181.93 | 167,101.75 | -46,080.18 | -21.62% |
| 202607 | USNJ | 1,057,063.02 | 559,120.15 | -497,942.87 | -47.11% |
| 202607 | USTX | 756,152.42 | 566,979.19 | -189,173.24 | -25.02% |
| 202608 | PL | 288,221.43 | 224,912.64 | -63,308.80 | -21.97% |
| 202608 | USNJ | 1,005,091.59 | 526,414.41 | -478,677.17 | -47.63% |
| 202608 | USTX | 923,106.70 | 687,858.08 | -235,248.62 | -25.48% |
| 202609 | PL | 259,113.10 | 201,221.44 | -57,891.67 | -22.34% |
| 202609 | USNJ | 557,626.72 | 304,650.51 | -252,976.22 | -45.37% |
| 202609 | USTX | 529,402.53 | 414,124.26 | -115,278.27 | -21.78% |

财务交付件：`tongtool_order_cost/out/fba_vs_branch/通途订单_分公司发货_vs_FBA_成本对比_202607-09.xlsx`
（7 个表：说明 / 结论摘要 / 按发货方式 / 重要边界 / 平台清单 / 排除清单 / 明细）。
生成脚本：`tongtool_order_cost/out/_fba_finance_excel.py`（工作脚本，未纳入 git；重算前先重跑 `merge-shadow` 的 Phase2）。

## Related

- `docs/solutions/workflow-issues/tongtu-split-merge-writeback-cost-rules.md`（件数/产品族修正会影响本表）
- `docs/reference/tongtool-order-canon/03-price-matrix.md`、`04-cost-sources.md`
- `docs/reference/cost-engine-spec/32-38`
