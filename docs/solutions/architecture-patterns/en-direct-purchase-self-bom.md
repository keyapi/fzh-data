---
okf: v0.1
type: Reference
title: EN 直接采购件用「自套 BOM」出成本的惯例 + 骨架缺口
date: 2026-10-12
category: architecture-patterns
module: EN_API
problem_type: architecture
component: erpnext
severity: medium
applies_when:
  - "某个 SKU 在 EN 成本报表里没有成本数字，要判断是不是漏了自套 BOM"
  - "新增/排查直接采购件（骨架、配件、成品外购）的成本维护方式"
  - "核对通途自发货订单的成本码为空（品类尺寸面料编码 缺映射）"
tags: [erpnext, bom, cost, self-bom, direct-purchase, 主体骨架, tongtu]
related_components: [EN_API, tongtool_order_cost]
---

# EN 直接采购件「自套 BOM」出成本惯例

> 背景：2026-10-12 排查通途 8 月订单里 96 条「只发主体骨架」(`WL-shape-frame`) 为什么成本是空的。
> 领域规则由用户（业务负责人）口述确认；数据为只读实测（EN 生产 REST + 财务共享 GS）。

## Context

有些 SKU 是**直接采购**来的（不是自己生产：没有皮壳/半成品/绍兴包装工序）。
这类件如果既没有 BOM、GS 成本表也没填，EN 各类成本报表里就**没有成本数字**。

## Guidance（惯例）

直接采购件维护成本的做法：

1. 维护**物料价格（采购价）** → EN `Item.valuation_rate` / `last_purchase_rate`。
2. 建一个**「自己套自己」的 BOM**：唯一组件就是该物料本身，`qty=1`，`rate=采购成本`。
3. 这种架构**没有皮壳 / 半成品**；`绍兴发货方式` 可写 `成品`；**国外不需要加工**（国外加工成本 = 0）；
   重量可能缺（重量用于头程）。

目的：**让 EN 成本报表里出现成本数字**（报表按 BOM 展开，没有 BOM 就不出数）。

### 自套 BOM 的结构特征（实测）

```
BOM-HM1510-YD2-135x152x80-WHITE-001
  item        = HM1510-YD2-135x152x80-WHITE
  items[0]    = HM1510-YD2-135x152x80-WHITE   qty=1  rate=721.05  amount=721.05
  total_cost  = 721.05
  is_active=1  is_default=1  docstatus=1(已提交)
```

### 规模（2026-10-12 全量扫描）

- EN 生产库 BOM 组件行 **20,543** 行；其中**自套 BOM 175 个**（父物料名 == 组件物料名）。
- 覆盖**很多组**的直接采购品，不只是骨架：如 印花石头抱枕(14)、长方形狗床（海绵）(12)、
  拐角狗床（PP棉）(12)、三角靠枕(6)、软包墙围(6) … 以及大量 1 件组。
- 扫描方法（REST，注意 Frappe 子表字段要写 `items.item_code`，且需去掉 `Expect` 头，否则 417）：

  ```
  GET /api/resource/BOM?fields=["name","item","items.item_code","items.qty"]
      &limit_start=0&limit_page_length=1000   # 分页扫，本地筛 item == items.item_code
  ```

## 已知缺口：主体骨架 `WL-shape-frame` 没有自套 BOM

- 通途独立售卖的骨架单：平台 SKU `WL-shape-frame`（Amazon `AMZCTRDUS`，ASIN `B0GYD4Z38F`，
  美东-CENTRADE 发，~$51/件）。8 月 96 条。
- EN 物料 `ZTGJ5525-SOFALSHAPEDBRACKET-IRON-55x45x45`（物料组 `主体骨架`，库存物料，
  `valuation_rate=22.5`，客户码 `TT0312701K0064561`）——**有采购价，但**：
  - GS `EN产品BOM成本列表20260202` 第 1939 行有它，但**皮壳成本/绍兴包装半成品成本/绍兴包装成品成本 三列全 0**，绍兴发货方式空；
  - `皮壳成本平均…` 表 **0 命中** → Colab `品类尺寸面料编码 → 皮壳平均` 映射落空 → 通途订单写回表**成本码为空**；
  - **不在 175 个自套 BOM 里**，也**不是任何 BOM 的组件** → 成本既没落表也没并入成品。
- 对照：`主体骨架` 组共 7 个物料，其中 3 个**是** `PK#`（皮壳）BOM 的组件
  （`SODASOFA-IRON-100x58x48`、`KTJDBYDY-IRON-60x50x36`、`LARGECUSHIONEDROCKINGCHAIR-…`）；
  单独售卖的 `SOFALSHAPEDBRACKET-IRON-55x45x45` 与 `MUFFINSOFABED-IRON-55x45x45` 都不是。

**结论**：`WL-shape-frame` 属于「该建自套 BOM 但没建」的漏项，成本报表里没有它的成本数字。

## When to Apply

- 某 SKU 在 EN 成本报表里没数字 → 先查它有没有自套 BOM（`item == items.item_code`）。
- 新增直接采购件 → 维护采购价 + 建自套 BOM，绍兴发货方式写成品、国外加工成本 0。
- 通途订单成本码为空 → 可能是物料既无自套 BOM 也不在皮壳平均表。

## Related

- [BOM Cost List Excel 成本读取说明](../../bom_cost_explanation.md)（三态成本拆解；发皮壳尾程前成本兼容皮壳/半成品）
- 自套 BOM 清单（运行时产物，不入库）：`tongtool_order_cost/out/en_self_boms.json`
