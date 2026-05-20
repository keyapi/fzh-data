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
  inputs: EN BOM 成本列表 + 赛狐商品导出
  outputs: 赛狐采购成本导入 + 问题报告
  updated: 2026-05-20
---

# 赛狐采购成本导入

## 一句话概括

ERPNext BOM 成本列表 → 计算绍兴发货成本 → 同前缀成本借用 → 生成赛狐采购成本导入。

## 快速启动

```bash
cd item_cost_sx
python bom_cost_to_saihu_item_cost.py
```

可选参数：
```bash
python bom_cost_to_saihu_item_cost.py --bom-dir ../en_bom_cost_list --out-dir out
python bom_cost_to_saihu_item_cost.py --saihu-commodities "商品导出.xlsx"
python bom_cost_to_saihu_item_cost.py --skip-saihu-match  # 不过滤赛狐 SKU
```

## 管道

```
BOM成本列表 → _read_bom_excel → _process_bom_dataframe(去重+计算绍兴发货成本)
  → _apply_sku_borrow(同前缀借用) → 标记赛狐是否存在
  → _saihu_import_frame(*SKU + 采购成本CNY + 采购备注) → 输出
```

## 成本计算

| 发货方式 | 公式 |
|---------|------|
| 皮壳 | `皮壳成本` |
| 半成品 | `皮壳成本 + 绍兴包装半成品成本` |
| 成品 | `绍兴总成本` |
| 其它/空 | 无法计算，排除 |

## 同前缀成本借用

SKU 按 `-` 分段，≥4段取前 3 段（品类-面料-尺寸）为键。同键下 0→非零 借用，一轮。

## 关键约束

- 工作表名必须 `商品`，非 `Sheet1`
- 采购成本=0 的行赛狐静默跳过不导入
- 列：`*SKU`、`采购成本(CNY)`、`采购备注`

## 输出

- `赛狐_采购成本导入_{stamp}.xlsx` — 工作表 `商品`
- `BOM成本处理_问题报告_{stamp}.xlsx` — 问题汇总 + 对账(仅EN/仅赛狐)

## 参考

- [给人看的 README](../../item_cost_sx/README.md)
- [给 Agent 的详细参考](../../item_cost_sx/AGENT_HANDOFF.md)
