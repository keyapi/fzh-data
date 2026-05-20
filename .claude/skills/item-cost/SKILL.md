---
name: item-cost
description: >
  赛狐采购成本导入。从 EN BOM 成本列表 → 计算绍兴发货成本 → 生成赛狐采购成本导入文件。
  当用户提到"采购成本"、"item_cost"、"BOM成本"、"item_cost_sx"、"绍兴发货成本"、
  "成本导入"、"采购单价"、"成本借用"等时触发。
  不要用于库存初始值导入(stock-init)或商品重尺(item-weight)。
compatibility: >
  需要 pandas, openpyxl。从 item_cost_sx/ 目录运行。BOM 源默认在 ../en_bom_cost_list/。
metadata:
  module: item_cost_sx
  script: bom_cost_to_saihu_item_cost.py
  updated: 2026-05-20
---

# 赛狐采购成本导入

ERPNext BOM 成本列表 → 计算绍兴发货成本 → 同前缀成本借用 → 生成赛狐采购成本导入。

## 快速启动

```bash
cd item_cost_sx
python bom_cost_to_saihu_item_cost.py
```

## 管道概要

BOM成本列表 → 去重保留末行 → 计算绍兴发货成本(皮壳/半成品/成品三种公式) → 同前缀成本借用(前3段SKU为键) → 标记赛狐是否存在 → 生成 3 列导入表(*SKU + 采购成本CNY + 采购备注)。

## 硬约束

- 工作表名必须 `商品`，列：`*SKU`、`采购成本(CNY)`、`采购备注`
- 采购成本=0 的行赛狐静默跳过不导入
- 发货方式为空的行排除（无法确定用哪种成本公式）

## 输出

- `赛狐_采购成本导入_{stamp}.xlsx` — 工作表 `商品`
- `BOM成本处理_问题报告_{stamp}.xlsx` — 问题汇总 + 对账(仅EN/仅赛狐)

## 参考

- [给人看的 README](../../item_cost_sx/README.md)
- [Agent 详细参考](../../item_cost_sx/AGENT_HANDOFF.md) — 成本计算公式、同前缀借用详则、命令行参数、函数表
