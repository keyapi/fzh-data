---
okf: v0.1
type: Reference
title: 供应分型与断货证据 — 先排费用/组件，再按角色分型；PJ 检查点不是每周
date: 2026-10-27
category: workflow-issues
module: supply_chain_visibility
problem_type: workflow_issue
component: supply-analytics
severity: high
applies_when:
  - "按正常/慢销/长尾/清仓给 SKU 设补货政策"
  - "用销量/库存检查点判断断货，或计算『断货损失』"
  - "分析 9 月促销/清仓异动，或判断某 SKU 是否要下架"
  - "把 Jeck 特殊规则表当促销/价格来源"
  - "对 item_attr 的 MOQ/装箱字段做补货规则"
tags: [sku-segmentation, stockout, promotion, clearance, product-role, data-quality, moq, amazon]
---

# 供应分型与断货证据：先排费用/组件，再按角色分型

## Context

2026-10-27 做 SKU 分型/9 月异动分析时，第一版有三个错误，都是口径问题，不是算法问题：

1. **把包装费当商品**：`497268621` 在通途商品查询里是
   “10in Mars Pillow礼盒包装费 ETSY”、分类“其他”，不是产品；第一版把它列进“有库存无销量”的死库存名单。
2. **把畅销皮壳判成长尾**：`CENKZ159410289-BLACK-153`、`CENKZ15389463-GREY-100`、
   `CENC/Linen-Ivory-60` 在**全渠道**数据里是 45/45 个月都有销量的皮壳畅销款；
   第一版用 `monthly_series`（只覆盖三个主仓）漏了其他渠道/仓，把它们判成“长尾/间歇”。
3. **把 PJ 检查点当每周**：PJ 只有 22 个日期，6 个间隔 >7 天，最大 38 天；
   不能用它证明“断货超过一周”。

## Guidance

### 1. 先排非商品，再分型

- 用通途 `erp2_product_goodsquery` 核对 `sku` 的 `productName/categoryName`；
  包装费、运费、服务费、无 `sku_item` 映射的 SKU 不进商品分型。
- `sku_item.ship_type` 分 **成品 / 半成品 / 皮壳**；`-COVER` 后缀先映射回基础 SKU。
- **皮壳/半成品不是独立成品**：补货要跟成品/BOM 走，不能按“近 6 月无销量”直接判死库存。
  例：`TT0031244K0064084` 映射 `KS0390-CTTM-120x120x70-CREAMYBEIGE`，是半成品；
  `TT0009009K0009483` / `TT0009006K0009477` 是星球系列皮壳，老产品，通常不再补。

### 2. 分型要用全渠道销量，并给“高销量间歇”单独一档

- 只用 `monthly_series`（三个主仓）会漏掉其他渠道/仓，把畅销款误判成长尾。
- 分型（产品 SKU，45 个月）：
  - **正常**：跨度≥12 月、零月<40%、ADI<2、月均≥5；
  - **正常（断货/季节干扰）**：零月≥40% 或 ADI≥2，但月均≥5；
  - **慢销**：非间歇、月均<5；
  - **长尾/间歇**：零月≥40% 或 ADI≥2，且月均<5；
  - **短史/新品**：跨度<12 月。
- 2026-10-27 修正后（2,253 个产品 SKU）：
  - 正常 557（24.7%）+ 断货/季节干扰 11（0.5%），合计销量约 **85.6%**；
  - 慢销 513（22.8%）、销量约 9.5%；
  - 长尾 509（22.6%）、销量约 2.6%；
  - 短史 663（29.4%）、销量约 2.3%。
- 角色：皮壳 1,810（80% SKU / 88% 销量）、成品 352（16% / 8%）、半成品 93（4% / 5%）。

### 3. 断货证据：30 天相关 ≠ 当天零库存还在卖

- 同 SKU 对照（PJ `sales_30d`）：696 个 SKU 同时有零/正库存观测，其中 455 个（65.4%）
  零库存时 30 天销量更低；平均 2.36 vs 5.29。**这是 30 天窗口，不是当天。**
- 当日口径（PJ 高置信、primary_sellable、available=0 且 physical=0）：
  2,918 条零库存观测中，只有 **37 条（1.3%）** 当天有销量；
  多数集中在同一快照日/多平台，可能是快照时点、仓库映射或库存不准，**不是 FBA**。
- **PJ 不是每周**：22 个日期，6 个间隔 >7 天，最大 38 天；WX 有 38 个但置信度 low，
  EN 只有 2026-10-20..26 七天。**不能证明“断货超过一周”**，需要每日快照或更密数据。
- 排除 FBA：本次只用 `warehouse_role='primary_sellable'` 的自发货/3PL 可售仓；
  `gs_orders.warehouse` 列表没有 FBA 仓。若怀疑“通途 0 但分公司有货”，
  按 PB 做法先发一单到分公司试，再决定是否标断货。

### 4. 9 月异动与促销：分“断货回补 / 降价清库存 / 非价格”

- 全渠道候选：9 月≥10 件且≥2× 6–8 月均，共 26 个；**Amazon-only 是 14 个**。
- 17/26 个在 8 月有零库存记录 → 9 月上涨可能只是补货后把积压订单发出去。
- 9 个“回补后降价 + 无在途 + 库存高” → 清库存嫌疑；2 个纯降价清库存；
  4 个价格平稳（非价格因素）；3 个待确认。
- **Jeck 表不是促销表**：“和财务部共享” → `Jeck特殊规则-订单改销售额成本`
  873 行里 `销售额系数` 全空，794 行只有皮壳/头程成本系数（0/0.5/0.75）；
  它是成本系数表，不能识别降价/促销。
- **赛狐 Amazon**：订单级有 `isPromotion`、`discountAmount`、`sellerProductDiscount`；
  财务有促销活动费；**没有未来促销日历端点**。当前阶段只用订单级标记做事后识别；
  促销日历留 EN 下一阶段，不塞 GSheet。

### 5. MOQ / 装箱字段：不要拿未维护字段当规则

- `item_attr` 是本地派生表；`moq` 非零只有 21/15,230，`min_pack` 全 0，
  `qty_per_outer` 非零 747；数据地图明确“MOQ/装箱有字段但未逐 SKU 验证”。
- `moq` 非零少 = **字段没人维护**，不是“工厂 MOQ=21 个”。
- 绍兴工厂没有硬 MOQ：只设软下限 `max(1, 装箱倍数, 7 天需求)`；
  慢销/长尾允许 1 箱/小批；清仓不补。

## Why This Matters

- **分型错 → 补货错**：把包装费/组件当成品死库存，会建议清仓或停补；
  把畅销皮壳判成长尾，会建议不自动补货，直接造成断货。
- **断货证据错 → 预测错**：零库存月不是真实需求 0；不标删失会让预测偏低。
- **促销识别错 → 政策错**：把成本系数表当促销表，会把成本调整误当降价，做出错误的清仓/补货决定。
- **PJ 间隔错 → 结论过度**：稀疏检查点不能证明断货持续时间，不能对外承诺“缺了一周”。

## When to Apply

- 给 SKU 设正常/慢销/长尾/清仓/停售政策前；
- 用销量/库存检查点算断货损失、可售覆盖、服务水平前；
- 分析月度销量异动、促销/清仓名单前；
- 看到 `item_attr.moq` / `qty_per_outer` / Jeck 表时。

## Examples

- **费用项**：`497268621` 通途品名“10in Mars Pillow礼盒包装费 ETSY”，排除。
- **半成品**：`TT0031244K0064084` → `KS0390-CTTM-120x120x70-CREAMYBEIGE`，按 BOM/成品需求补，不按独立成品清仓。
- **畅销皮壳**：`CENKZ159410289-BLACK-153` 全渠道 45/45 月有销量，月均约 57 件 → 正常，不是长尾。
- **老皮壳**：`TT0009009K0009483`、`TT0009006K0009477` 星球系列，通常不再补货，按清仓/停售处理。
- **断货**：PJ 零库存当天有销量的仅 1.3%；要证明“超过一周”需每日快照。

## Related

- [2026-10-27-sku-segmentation-stockout-promotion.md](../../research/supply-chain/2026-10-20/claude/control/reviews/2026-10-27-sku-segmentation-stockout-promotion.md) — 完整分析、名单、复现命令
- [pb-out-of-stock-notification-and-zero-stock-orders.md](pb-out-of-stock-notification-and-zero-stock-orders.md) — PB 断货/0 库存订单的既有做法
- [sellfox-incentive-cost-adjust-2026-09.md](sellfox-incentive-cost-adjust-2026-09.md) — Jeck 表的成本口径用法（不是促销）
- [search-first-before-implementing.md](search-first-before-implementing.md) — 先查分支/PR，再下“没有”的结论
- [2026-10-27-existing-assets-forecast-inventory.md](../../research/supply-chain/2026-10-20/claude/control/reviews/2026-10-27-existing-assets-forecast-inventory.md) — 预测/库存/交期/净额已有资产
