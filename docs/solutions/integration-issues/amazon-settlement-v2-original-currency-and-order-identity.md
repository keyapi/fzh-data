---
okf: v0.1
type: Reference
title: Amazon 结算 V2 原币取数与订单身份归一（踩坑）
date: 2026-11-10
category: integration-issues
module: sellfox_settlement
problem_type: integration_issue
component: tooling
severity: high
applies_when:
  - "从赛狐 Settlement V2 取原币金额（不想用当日汇率 CNY）"
  - "把 V2 交易行接到通途/EN 订单去取成本"
  - "覆盖率只有 20%/35% 之类异常低，怀疑订单号或期间"
tags: [amazon, settlement-v2, currency, order-id, tongtool, lookback]
---

# Amazon 结算 V2 原币取数与订单身份归一

## Context

用赛狐 Settlement V2 明细算 2026-10 的 Amazon 成本/利润时，连续踩了三个坑：币种被折成 CNY、通途订单号按前缀匹配失败、单月回看不够。三个都会让覆盖率或金额悄悄错掉。

## Guidance

1. **`currency` 是"折算目标币种"，不是过滤条件。**
   - `fetch` 明细默认 `CNY`（赛狐当日汇率）；传 `--currency USD` 会把**全部 26,381 行转成 USD**，不是只取 USD。
   - **取原币的正确做法**：`summary` 每个结算组有原生币种；在 `currency=该原生币种` 的那份明细里，**该组金额即原值**（identity，EUR/USD 已验证）。按 `settlementId → 币种 → 对应文件` 取。
   - 兜底：店铺单一币种（`storeName` 众数）；仍缺的极少，记录回退行数。
2. **通途 `订单号` 各账号前缀不同**：`CUS-`（Centrade）、`BJRYECLTUS-`（如泱）、`BNKCUS-`（百纳）、`DANEEYUS-`（Daneey）…。**必须用正则提取内嵌的 `\d{3}-\d{7}-\d{7}` Amazon 单号**，只去 `CUS-` 会误报 80% 缺失。
3. **多月份回看**：单月发货文件只覆盖约 **57%** 的 10 月-posted FBM 单；补 **9 月 → 99.4%**（8 月 +17、7 月 +0）。退款会引用更早订单，回看是必需项。
4. **FBA 不在"非FBA"导出**：用 EN `tabTongtool Order` 按订单号集合查；`item_cost` **实测全为 0**，改用 **EN BOM 单价×数量**。
5. **未匹配先查 EN 再下结论**：67 个 FBA 缺单里 **62 个是百纳美国未导入 EN**；17 个 FBM 是**未发货**（EN 有、发货表无）。扩更早月份补不回来。

## Why This Matters

- 币种错 → 金额口径错（CNY 当日汇率 vs 财务月汇率不可混）；
- 订单号错 → 覆盖率假低、成本被当成缺失；
- 回看不足 → 成本漏、利润虚高。
三者都会让"看起来能跑"的结果其实是错的。

## When to Apply

任何把 Settlement V2 接到订单/成本/利润的流程；尤其换月、换账号、换导出格式时。

## Examples

- 原币：USD 组 69.99（USD 文件）↔ CNY 468.45（CNY 文件）↔ EUR 62.58，三者同一个 Principal。
- 订单号：`CUS-114-…`、`BJRYECLTUS-113-…`、`BNKCUS-112-…` 都要还原成 `114-…`、`113-…`、`112-…`。
- 覆盖率：10 月单月 1,826/3,184（57%）→ 补 9 月 3,165/3,184（99.4%）。

## Related

- `sellfox_settlement/docs/research/2026-11-10-v2-settlement-to-order-matching.md`
- `sellfox_settlement/docs/research/2026-11-10-amazon-v2-endtoend-audit.md`
- `sellfox_settlement/reconcile_amazon.py`
