---
okf: v0.1
type: Reference
title: Walmart 账期走赛狐 API 直拉；平台费口径结案（差额=沃尔玛补贴×15%）
category: workflow-issues
module: platform_account_reconciliation
problem_type: workflow_issue
component: finance_reconciliation
severity: high
date: 2026-09-21
applies_when:
  - "要做 Walmart/沃尔玛 账期对账，或判断某平台能否从赛狐 API 拿账期数据"
  - "EN platform_fee 与平台账期费用对不上，怀疑是口径差异而非漏单"
  - "需要从赛狐拉结算明细/账期数据，或按账期而非自然月取数"
tags: [walmart, sellfox, reconciliation, platform-fee, en, finance, account-period]
related_components: [EN_API, SELLFOX_API, platform_account_reconciliation]
---

# Walmart 账期走赛狐 API 直拉；平台费口径结案

## Context

`platform-account-reconciliation` 原先只覆盖 Overstock OSTKUS，数据源是**财务同事手工提供的账期 xlsx**。
问题：赛狐 API 能不能直接把 Walmart 账期拉出来？

实测结论：**能**。Walmart 是赛狐里唯一带账期字段的结算端点族，且是**公开 OpenAPI**（非私有接口，不需 cookie）。
由此新增了一条不依赖人工导出的数据路径，并在对账过程中把长期悬而未决的**平台费口径差额查清了**。

完整调研（端点原文、逐单证据、踩坑）见
[`docs/research/2026-09-21-sellfox-walmart-settlement-api.md`](../../research/2026-09-21-sellfox-walmart-settlement-api.md)。

## Guidance

### 1. 端点与连接键

`POST /api/financial/walmartReport/queryStatementDetail.json`（公开 OpenAPI，App 权限实测已开通）。
返回行含 `periodStartDate`/`periodEndDate`（账期）、`transactionPostedDate`（结算时间）、
`amountType`/`transactionType`/`amount`/`currency`、`purchaseOrder`、`partnerItemId`、`fulfillmentType`。

| 赛狐 | EN |
|---|---|
| `purchaseOrder` | `Tongtool Order.platform_order_id`（100% 命中） |
| `partnerItemId` | `Item.platform_sku` |
| — | EN `platform_code = walmart_api`，`name = WM-{platform_order_id}` |

### 2. ★ 必须按账期取数，不要按自然月

**Walmart 是双周账期（14 天）**。用 `periodStartDate`/`periodEndDate` 当作 `transactionPosted` 区间去查，
并且**跨账期合并比对** —— 同一 PO 的销售行与后续退货/费用行常落在相邻账期，
按单账期聚合去比 EN 必然错位（实测 58 单里 12 单如此，会误判成"金额不一致"）。

### 3. ★ 平台费口径（已结案，不要再当未解问题排查）

```
赛狐 Commission on Product = (商品价 + Total Walmart Funded Savings) × 15%
EN   platform_fee          =  商品价 × 15%
                             差额 = 沃尔玛补贴 × 15%
```

逐单 **64/64 命中**（残差全 ±0.00），汇总差 **28.28** vs 补贴合计×15% = **28.32**。
**赛狐对，EN 的 `platform_fee` 漏算了补贴基数。** 类目佣金率就是恒定 15% ——
先前观察到的「费率在 15%~17% 之间飘」是**基数差异造成的假象**。

另一类差异不是错误：**佣金已退货冲平** —— 赛狐本期佣金净额为 0（销售佣金被退货冲回），
而 EN `platform_fee` 是订单发生时的原值、不随退货调整，属时点口径差。

### 4. 取数机制的三个坑

- **分页无元信息**：响应 `data` 只有 `rows`，**没有 `totalSize`/`totalPage`**；只能翻到某页条数 < `pageSize` 为止。
- **限流有两种形态**：`client.py` 的 `is_rate_limited_response()` 只认 `code == 40019`，
  实际还会遇到 HTTP 层 `{"detail": "Global rate limited. Retry after 0.3s"}`（**无 `code` 字段**），必须两种都识别。
- **不要用 `requests.Session()` 查 EN**：整批查 `Tongtool Order` 时 `Session()` 会静默返回 0 条，
  换裸 `requests.get` 立刻 100% 命中（与 `reconcile_ostkus.py` 保持一致）。

### 5. 平台覆盖边界 —— 别把这条经验外推

- **Wayfair 走不通**：赛狐里 WAYFAIR 只作为店铺/订单平台码存在，**没有任何 Wayfair 财务结算端点**。
- **Overstock 完全没有**：赛狐平台枚举里不存在 ostk/overstock，OSTKUS 只能继续走财务手工 xlsx。
- 即：**Walmart 走得通，Wayfair 走不通** —— 与模块原设计文档「扩展 Wayfair」的假设相反。

## Why This Matters

1. **销售额 3 个账期分毫不差**（1317.28 / 1511.75 / 4346.60，差异均 0.00），订单级 73/77 精确一致
   —— 这同时证明 **EN 的 Tongtool Order 快照对通途是忠实的**，
   所以**不需要动用通途 API 去复核**（通途限速 5 次/分钟，代价高且无必要）。
2. 口径结案让财务第一次能**解释**而不只是**标记**平台费差额；
   同一方法（找 EN 少算的那个基数项）可直接回头复查 OSTKUS 那笔至今未结案的差额。
3. 新增了不依赖人工导出的账期数据路径，抵消了原流程对财务同事手工导出的依赖。

## When to Apply

- 用户提到 Walmart/沃尔玛 账期、Walmart 结算、`platform_fee`、平台费、账期费用核对。
- 要把某个平台接进 `platform-account-reconciliation` 前，先判断赛狐有没有该平台的财务端点。
- 看到「EN 平台费与账期费用对不上」时，**先怀疑基数口径，不要先怀疑漏单**。

## Examples

```bash
# 1) 摸账期节奏（翻全窗口，列出各账期起止与行数）——约 6 次调用翻完 9 个月
uv run python SELLFOX_API/probe_walmart_settlement.py \
  --shop-id 598030 --start 2026-01-01 --end 2026-09-21 --discover-periods

# 2) 按账期整期拉全量行
uv run python SELLFOX_API/probe_walmart_settlement.py \
  --shop-id 598030 --pull-period 2026-08-08:2026-09-05

# 3) 跨账期合并勾稽（输出 账期总览/订单级勾稽/账期费用分类/账期明细 四个 sheet）
uv run python platform_account_reconciliation/scripts/reconcile_walmart.py \
  --sellfox-json "<repo_root>/out/sellfox_walmart_probe/period_598030_*.json" \
  --out "Walmart账期勾稽.xlsx"
```

最近 3 个账期结果：

| 账期 | 赛狐销售额 | EN 商品额 | 差异 |
|---|---|---|---|
| 2026-07-11 → 07-25 | 1,317.28 | 1,317.28 | 0.00 |
| 2026-07-25 → 08-08 | 1,511.75 | 1,511.75 | 0.00 |
| 2026-08-08 → 09-05 | 4,346.60 | 4,346.60 | 0.00 |

## Related

- 同模块兄弟文档：[OSTKUS 账期与 EN Tongtool Order 对账](ostkus-account-reconciliation.md)
- 调研全记录（端点、逐单证据、原始 URL）：[`docs/research/2026-09-21-sellfox-walmart-settlement-api.md`](../../research/2026-09-21-sellfox-walmart-settlement-api.md)
- 模块接手入口：[`platform_account_reconciliation/AGENT_HANDOFF.md`](../../../platform_account_reconciliation/AGENT_HANDOFF.md) §10
- 赛狐 API 两套调用面与鉴权：[`sellfox-api` skill](../../../.agents/skills/sellfox-api/SKILL.md)
