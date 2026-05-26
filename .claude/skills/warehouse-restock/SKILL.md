---
name: warehouse-restock
description: >
  赛狐海外仓备货单导入。从 EN BOM 成本列表拆出绍兴发货成本/头程运费/国外加工成本，
  结合通途仓库分布，生成赛狐海外仓备货单导入 xlsx。
  当用户提到"海外仓备货单"、"warehouse_restock"、"备货单"、"采购入库"、
  "海外仓入库"、"stock_plan"、"成本拆分"、"绍兴发货成本"等时触发。
  不要用于期初库存导入(stock-init)或采购成本导入(item-cost)。
compatibility: >
  需要 pandas, openpyxl。从 warehouse_restock/ 目录运行。
  依赖 数据源/ 下的 EN BOM 成本列表 + 通途库存 + 赛狐商品导出。
  模板文件在 数据源样例/ 下。
metadata:
  module: warehouse_restock
  script: build_saihu_warehouse_restock.py
  updated: 2026-05-26
---

# 赛狐海外仓备货单导入

EN BOM Cost List → 三成本拆分（绍兴/头程/加工）→ 赛狐海外仓备货单模板。

## 快速启动

```bash
cd warehouse_restock
python build_saihu_warehouse_restock.py
```

## 管道概要

EN BOM成本列表 → 成本借用(同重量模板) → 三成本拆分 → 通途仓库映射 → 赛狐SKU白名单 → 填模板输出。

## 硬约束

- 通途仓库判定：SKU **只要出现过**就算（含库存=0），不只是可用库存>0
- 物流费用=头程运费×1000，其他费用=加工成本×1000（赛狐自动除以数量得单价）
- 成本缺失时同重量模板内借用（同 stock_init 逻辑）
- 输出模板含 hidden Data Validation sheet，不可删
- 头程/税费分摊方式统一填"自定义"

## 成本 → 模板列

| 列 | 值 |
|---|-----|
| `指定采购单价` | 绍兴发货成本 |
| `物流费用` | 头程运费 × 1000 |
| `其他费用` | 国外加工成本 × 1000 |
| `*备货数量` | 1000 |
| `*头程分摊方式` / `*税费分摊方式` | 自定义 |

## 输出

- `赛狐_海外仓备货单_导入_{stamp}.xlsx` — 可直接上传赛狐
- `warehouse_restock_问题报告_{stamp}.xlsx` — 跳过明细 + 成本借用记录

## 参考

- [给人看的 README](../../warehouse_restock/README.md)
- [Agent 详细参考](../../warehouse_restock/AGENT_HANDOFF.md)
- [BOM 成本拆解说明](../../docs/bom_cost_explanation.md)
