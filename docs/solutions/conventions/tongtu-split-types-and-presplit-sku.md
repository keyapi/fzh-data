---
okf: v0.1
type: Reference
title: 通途拆单类型与拆单前 SKU 位置（自动拆单 / 手动拆单 / TikTok 跨账号）
date: 2026-11-09
category: conventions
module: tongtool_order_cost
problem_type: convention
component: tooling
severity: medium
applies_when:
  - "要判断一个合并组是通途自动拆单、手动拆单还是 TikTok 跨账号拆单"
  - "想知道拆单前组合 SKU 能不能在 EN/表里显示"
  - "做拆单合并、销量预估、分公司下单时，要回答“对应哪个产品/哪个 SKU”"
tags: [tongtu, split-orders, platform-sku, tiktok, order-mapping]
---

## Context

通途订单的“拆单”不是一种：有时是通途自动把平台组合 SKU 拆成组件，有时是人工把原单作废后重新拆成子单，TikTok 还有跨账号手动补单。三者订单痕迹不同，**拆单前 SKU 的位置也不同**。把三者混为一谈会得出“原始订单一定存在/一定不存在”“拆单前 SKU 不能用”这类错误结论。

## Guidance（本学习沉淀的做法）

| 类型 | 订单痕迹 | 拆单前 SKU 在哪 | 典型例子 |
|---|---|---|---|
| **通途自动拆单** | 订单号无 `_N`；**没有** `invalid=1` 原单；EN 组件行 `tongtool_sku` 是组件 | **EN `Tongtool Order Item.platform_sku` 保留原组合 SKU**（同一单的组件行 platform_sku 相同） | `JYWM-119122574963497`：`platform_sku=Curve-Pillow-Linen-PPCotton-Yellow-50`，`tongtool_sku=-Cover` / `Curve-Pillow-50-PPCotton` |
| **手动拆单** | 原单存在后作废（`invalid=1`），再生成 `_1/_2` 子单 | 原单/子单 `platform_sku` 通常是**产品基号**（如 `TT0031244K0064084`）；描述型组合 SKU 只在通途捆绑商品主数据 | `Cds-260812130757QFL`、`KFLDE-MBU14K5`（后者 `_2` 顾客取消未发） |
| **TikTok 跨账号手动拆单** | 不同前缀、数字主体相同；无 invalid 原单 | 没有统一原单；靠数字主体配对 | `TTDaneeyGo-…` + `TTDaneeyUS-…_2` |

结论：

1. **成本与写回键仍用组件 SKU**（结构判据、模板匹配都依赖它）。
2. 若要在表里显示「拆单前 SKU」：
   - 自动拆单：直接取 EN `Tongtool Order Item.platform_sku`；
   - 手动拆单：取原单 `platform_sku`（基号），或从通途捆绑商品主数据按组件集合匹配；
   - **新增展示列**，不要替换写回键。
3. 做订单→产品映射/销量预估时：自动拆单优先看 `platform_sku`（组合 SKU），手动拆单看基号；组件行只是组合的一部分。

## Why This Matters

- 同一笔交易在 EN 里有两种表示：组件行（`tongtool_sku`）和原组合（`platform_sku`）。只看 `tongtool_sku` 会得出“没有原始订单”的错误结论。
- 手动拆单的原单虽然 `invalid=1`，但它是**产品身份/件数的锚**，不能当普通作废行删掉。
- 展示层如果替换写回键，会让下一次写回匹配不到；必须“键用组件、展示另加列”。

## When to Apply

- 合并组自查、成本写回、GS 展示列设计；
- 历史订单→产品映射、销量预估、给分公司下单（先确定“对应哪个成品/哪个组件”）；
- TikTok 订单配对与跨账号补单。

## Examples

- 自动拆单（202608）：`JYWM-119122574963497`；EN 两条组件行的 `platform_sku` 都是 `Curve-Pillow-Linen-PPCotton-Yellow-50`，`erp_item_code` 分别指向皮壳行/填充行。
- 手动拆单（202608）：`Cds-260812130757QFL` 原单 `invalid=1`，子单 `_1/_2`；原单/子单 `platform_sku` 都是 `TT0031244K0064084`。
- TikTok（202608）：`TTDaneeyGo-577511764556747219`（Cover）+ `TTDaneeyUS-…_2`（Foam），按数字主体配对。
- 数量分布（202608 / 202609）：自动 71 / 33；手动 11 / 9；TikTok 1 / 0。

## Related

- `docs/reference/tongtool-order-canon/02-grouping-and-merge.md` §3（拆单判据）、§3.1（TikTok）、§3.2（自动/手动）
- `docs/reference/tongtool-order-canon/01-order-universe.md`
- `docs/solutions/workflow-issues/tongtu-split-merge-writeback-cost-rules.md`
- `tongtool_order_cost/tongtu_cost_engine/domain/split_merge.py`（`order_common_part`、`_pair_tiktok_cross_prefix`）
