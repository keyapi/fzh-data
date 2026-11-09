---
okf: v0.1
type: Reference
title: 产品改版后平台订单仍带旧 SKU：显式映射 + 平台料号交叉校验 + 出件前自动转换
date: 2026-11-06
category: workflow-issues
module: pb_orders
problem_type: workflow_issue
component: tooling
severity: high
applies_when:
  - "产品改版/换尺寸后，平台料号不变，但新订单仍带旧供应商 SKU"
  - "旧 SKU 已零库存、新 SKU 有货，出件前必须自动换算且不能错颜色"
  - "平台后台的料号与供应商 SKU 映射曾经被人工写反过"
tags: [pb-orders, sku-migration, sps, tongtu, fail-closed]
---

# 产品改版后平台订单仍带旧 SKU：显式映射 + 平台料号交叉校验 + 出件前自动转换

## Context

一个产品改版（尺寸、颜色、包装变化）后，**平台侧的料号往往不变**。平台新下的订单仍然带
2024 年登记的旧供应商 SKU；而仓库里旧 SKU 已经零库存，有货的是 2025 年新建的改版 SKU。
同时，历史人工维护的映射表出现过**颜色写反**（同一平台料号被配到另一种颜色的旧 SKU）。

如果出件流程直接按订单里的 `Vendor Style` 生成通途导入单和标签，会出现两种事故：

1. 旧 SKU 零库存 → 通途导入后无货、整单卡住；
2. 映射颜色写反 → 发错颜色，平台罚款/退货。

## Guidance（本学习沉淀的做法）

1. **以平台料号为锚，不以 SKU 名称为锚**。配对键是
   `(平台料号, 颜色)`，例如 PB `5938375` 只允许 Grey；`4020032` 只允许 Ivory。
2. **映射落成数据文件，不写成代码分支**。每个 SKU 三态：
   - `confirmed`：旧→新，可自动转换；
   - `unconfirmed`：未报价/未登记（例如新增深蓝色），出现即中止；
   - `blocked`：明确不可用（例如未进平台 SKU Worksheet 的菱形绒布）。
3. **平台料号 × Vendor Style 硬校验**。订单里 `Buyers Catalog or Stock Keeping #` 与
   `Vendor Style` 必须命中同一组允许配对；配错直接失败，不允许“先出件后人工看”。
4. **在最后责任点转换**：在生成通途 xlsx / 标签 / 背贴之前改 `Vendor Style`，
   并把转换后的 CSV 作为产物保留（审计用），不要改原始上传文件。
5. **失败关闭（fail closed）**：未确认 SKU、冲突配对一律 `PBJobError`，
   不生成任何正式产物；页面显示行号与允许值。
6. **断货清单与 ASN 核对也要别名化**：旧/新 SKU 互为别名，
   否则“断货清单写新 SKU、订单还是旧 SKU”会漏判有货。
7. **名称缓存双写**：背贴名称缓存在服务器是只读挂载，直接补宿主文件；
   同时必须补它的来源 Google Sheet，否则下次刷新会被覆盖。

## Why This Matters

- 旧 SKU 零库存不是“少发一件”，而是整单无法从美中仓出库；上线首周会被平台判迟发。
- 平台料号不变时，仓库/客服看不出“这是同一产品的两代 SKU”，人工核对极易漏。
- 历史映射表颜色写反是**已经发生过的事实**，只靠“看一下”挡不住；必须有机器校验。

## When to Apply

- 产品改版、换尺寸/面料/包装，但平台料号不变。
- 供应商 SKU 重新编号（旧码停用、新码建档），订单仍带旧码。
- 平台后台的 Vendor Part Number 暂时无法修改，需要用中间层换算。
- 任何“平台订单 → 仓库 SKU”的出件流水线（PB/SPS、Wayfair、其他 Dropship）。

## Examples

确认映射（示意）：

| 平台料号 | 颜色 | 旧 SKU（订单里） | 新 SKU（有货） |
|---|---|---|---|
| `5938375` | Grey | `TT0031058K0062965` | `TT0312672K0064328` |
| `4020032` | Ivory | `TT0031059K0062966` | `TT0312673K0064329` |
| 未登记 | Deep Blue | — | `TT0312674K0064330`（出现即中止） |

出件前转换与校验：

```bash
uv run python pb_orders/arc_sku_migration.py check <order.csv>
uv run python pb_orders/arc_sku_migration.py map-order <order.csv> -o <order_新SKU.csv>
```

Web 出件默认开启转换；任务报告会列出每个旧→新 SKU 的转换行数，转换后 CSV 可下载。

## Related

- 产品与报价明细：`pb_orders/docs/reference/pb-arc-foam-cylinder-sku-migration.md`
- 代码：`pb_orders/arc_sku_migration.py`、`pb_orders/service.py`、`pb_orders/sku_maps/pb_arc_foam_cylinder.json`
- 同类平台映射：`docs/solutions/conventions/sellfox-combo-sku-create-pairing-workflow.md`
- PR #336
