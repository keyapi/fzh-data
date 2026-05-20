---
name: category
description: >
  赛狐商品 4 级分类导入。交叉校验 EN 物料属性 + 赛狐分类导出 → 生成分类导入 xlsx。
  当用户提到"商品分类"、"category"、"四级分类"、"分类导入"、"分类树"、
  "款式分类"、"类目"等时触发。
compatibility: >
  需要 pandas, openpyxl。从 category/ 目录运行。依赖 multi_attr_saihu/erpnext_to_saihu.py（动态导入）。
metadata:
  module: category
  script: build_saihu_category_import.py
  updated: 2026-05-20
---

# 赛狐商品 4 级分类导入

EN 物料属性（款式ID→分类） + 赛狐分类导出（分类树） → 交叉校验 → 生成 4 sheet 分类导入 xlsx。

## 快速启动

```bash
cd category
python build_saihu_category_import.py
```

## 管道概要

EN物料属性(款式ID→赛狐分类 map) + 赛狐分类导出(末级名→4级路径) + 赛狐商品导出(SKU/spu) → 逐 SKU 校验 → ok / not_leaf / ambiguous_leaf / unknown → 4 sheet 输出。

## 硬约束

- 款式ID = SKU 第一个 `-` 前的前缀（通过 `_default_spu_from_sku` 动态导入 `multi_attr` 模块）
- 物料表中「赛狐分类」必须与「商品分类导出」末级类名**完全一致**（含空格）
- 输出用 `shutil.copy` + `pd.ExcelWriter(mode='a')`，不破坏模板

## 输出

4 sheet：`商品`(导入用) + `核对`(逐行状态) + `错误报告`(需处理行) + `款式_赛狐分类校验`(款式对照)

## 参考

- [给人看的 README](../../category/README.md)
- [Agent 详细参考](../../category/AGENT_HANDOFF.md) — CategoryIndex 类、核心函数、状态码、数据路径
