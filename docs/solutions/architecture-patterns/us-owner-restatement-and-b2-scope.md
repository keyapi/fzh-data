---
okf: v0.1
type: Reference
title: 美国需求按当前 owner 重述与 B2 品类范围
date: 2026-11-03
category: architecture-patterns
module: supply_chain
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "美国历史订单仓库与当前责任分公司不一致（USNJ/USTX 迁移）"
  - "需要把美国看成一个市场预测总需求，再分到两个补货目的仓"
  - "Jing 的品类/面料/老品范围需要进入补货决策"
tags: [current-owner, usnj, ustx, b2-scope, demand-restatement]
---

# 美国需求按当前 owner 重述与 B2 品类范围

## Context

D3b v3.2 之前，美国需求按历史订单仓库归池（USNJ/USTX）；后来发现很多产品历史在 USNJ、当前责任已迁到 USTX（或反向），直接按历史仓预测会把需求错配。

实测 owner-known 美国需求 281,490 件：

- 历史池 USNJ 152,410 / USTX 129,080；
- 当前 owner USNJ 69,837 / USTX 211,653；
- 迁移 84,343 件 / 181 产品（USNJ→USTX 83,458；USTX→USNJ 885）；
- 178 个产品两池都有历史；53 个当前 USNJ、历史含 USTX 的特例；
- 31,033 件无唯一 owner，单列 `US_unassigned`。

## Guidance

1. **美国看成一个市场**：先按产品预测美国总需求，再按已证唯一 current owner 分到 USNJ/USTX。
2. **A/B/C 三方案保留**：
   - A：历史 as-of 仓池分别预测，仅作 evidence/备选；
   - B：total demand × current owner 1/0，生产候选；
   - C90/C180：total demand × 近期仓份额，仅用于真实双仓责任产品。
3. **只重述派生需求**：不改原始订单、库存、供应；历史仓保留 `historical_pool`、`owner_migration`、`both_pools`、`exception`。
4. **弱 owner 不猜**：无唯一 owner → `US_unassigned`，不补 0、不分摊。
5. **当前责任重述 vs as-of 回测分开**：current-owner 用于预测，as-of 只用于历史回测；B 的回测比较有前视风险，只能作证据。
6. **B2 业务范围**：
   - 新棉麻本色/HEMP → 纯棉麻；三角平绒 → 纯棉平绒；
   - 弧形PP棉印花只保留森林乐章、蓝蝴蝶两个花色；
   - 星球/石头/泰迪为老品 `old_no_replenish`；
   - 其余非清单/旧花色/碎海绵走观察。

## Why This Matters

- 按历史仓直接预测会把 84,343 件需求放到错误的分公司。
- 按当前 owner 重述后，D3b 从 1,853 键收敛到 1,749；B 合计 WAPE 0.5262，优于 A 的 0.5468，与 C 持平。
- B2 范围把“补货范围”与“需求证据”分开，避免把非清单/老品/旧花色错误补货。

## When to Apply

- 美国需求归属、D3b 键迁移、D5 预测、D6 补货范围；
- 业务问“历史在美东、现在归美中怎么算”；
- 新品类/面料/老品范围变更时。

## Examples

- 某产品历史 USNJ 3,289、当前 owner USTX：需求全归 USTX；USNJ 历史保留为 evidence。
- 53 个 current USNJ / hist USTX 特例逐条列在 `us_owner_migration_20261102.csv`。
- `business_category_scope_20261103.csv`：USNJ_continue 238、old_no_replenish 110、observe_* 等。

## Related

- `docs/solutions/architecture-patterns/demand-forecast-layer-d.md`
- `docs/solutions/best-practices/censored-demand-cold-start-seasonality.md`
- `docs/solutions/architecture-patterns/end-to-end-supply-chain-strategy-s1-s2.md`
