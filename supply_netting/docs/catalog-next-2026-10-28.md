---
okf: v0.1
type: Reference
title: 目录覆盖后续动作（2026-10-28）
description: 4,949 未进包物料的四类动作与责任角色、64 个有库存 UOM 未证的优先清单、全目录边界声明
tags: [catalog, coverage, uom, mapping, sku-lifecycle, action-plan]
date: 2026-10-28
status: implemented
---

# 目录覆盖后续动作（FULL-CATALOG-NEXT）

基于 [`catalog-coverage-2026-10-28`](https://github.com/keyapi/fzh-data)
（6,573 目录 / 1,627 进包 / 4,949 未进包）做的**动作层**：只给动作与责任角色，
不改任何数字、不建 SKU、不 push。

- 脚本：[`../scripts/catalog_next.py`](../scripts/catalog_next.py)（`--fetch-en` 只读拉 EN 单位快照）
- 测试：[`../tests/test_catalog_next.py`](../tests/test_catalog_next.py)（8 条）
- 产物（本地，不进 git）：
  `D:/Work/fzh-order-store/en-demand-v1/supply-netting/catalog-next-2026-10-28/`
  —— `report.md`、`coverage_actions.csv`、`uom_unproven_priority.csv`、
  `en_items_stock_uom.json`、`manifest.json`

## 1. 四类未覆盖 → 动作与责任角色

| 优先级 | 原因 | 物料 | 库存件 | 动作 | 责任角色 | 复核 |
|---|---|---:|---:|---|---|---|
| **P0** | `stock_without_uom_evidence` | 64 | 1,324 | 刷新 EN `stock_uom` 缓存 → 重跑净额 | 供应链数据层（本层/Agent） | EN 主数据 |
| P1 | `unmapped_no_evidence` | 761 | 0 | 通途侧确认停用/在售；在售则建配对（`missing-products`） | 运营（通途配对） | 业务 |
| P1 | `mapped_no_stock_no_sales` | 284 | 0 | 停售确认；在售则补订货与销量证据 | 业务（SKU 生命周期） | 运营 |
| P2 | `component_or_cover` | 3,840 | 0 | 口径确认：组件/皮壳**不建**独立可售 SKU（维持 PK#→KS 1:1、ND# 不计独立可售） | 业务（SKU 生命周期） | 本层 |

红线：不因缺需求就删有货项；不凭名称相似硬绑映射；不把「无销量」写成「零需求」；
不为凑覆盖率建成品 SKU。

## 2. 64 项「有库存但 UOM 未证」= 缓存覆盖问题，不是主数据问题

实查 EN `Item.stock_uom`：**64/64 都有单位（全为「个」）**。

- 本层 UOM 缓存 1,627 条与进包物料 1,627 个**完全一致**——缓存是按决策键建的，
  没覆盖「有库存但没进包」的物料。所以这 64 个不是 EN 缺数据。
- 63 项刷新缓存即可进**库存侧事实**（有货不再被当成没有）；1 项 EN `disabled=1`
  转停售确认。
- 64 项合计 1,324 件，库存中位 17 件；**12 个月销量全为 0**——补单位后得到的是
  库存证据，不是需求证据，仍不能拿库存当销量。
- 物料组 Top 5：印花石头抱枕 13、三角靠枕无扣 12、弧形PP棉靠枕-拉链款 5、
  三角靠枕 3、材质方墩 2。

## 3. 边界（写进报告，任何时候都成立）

- **4,014 个决策键 ≠ 公司全目录**：只覆盖 1,627 个 EN 物料，目录 6,573 个。
- **未覆盖 ≠ 零需求**：有库存/有映射的必须单列；本层不把未覆盖项并入任何缺口或服务档。
- 皮壳/内胆是否按组件售卖由业务定；本层不裁定也不建 SKU。
- 不改 `decision_pack` / `supply_netting` / r6 / h180 任何数字；不 push。

## 4. 复现

```bash
uv run python -m supply_netting.scripts.catalog_next --fetch-en   # 只读拉 64 项 EN 单位
uv run python -m supply_netting.scripts.catalog_next              # 出动作表与优先清单
```
