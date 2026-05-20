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
  inputs: EN物料属性 + 赛狐商品分类导出 + 赛狐商品导出
  outputs: 赛狐分类导入（4 sheet）
  updated: 2026-05-20
---

# 赛狐商品 4 级分类导入

## 一句话概括

EN 物料属性（款式ID→分类） + 赛狐分类导出（分类树） → 交叉校验 → 生成分类导入 xlsx（4 sheet）。

## 快速启动

```bash
cd category
python build_saihu_category_import.py
```

## 管道

```
EN物料属性(款式ID→赛狐分类map)
赛狐分类导出 → CategoryIndex(末级名→4级路径)
赛狐商品导出(SKU/spu)
  → 逐SKU校验 → ok / not_leaf / ambiguous_leaf / unknown → 4 sheet 输出
```

## 关键逻辑

- 款式ID = SKU 第一个 `-` 前的前缀（通过 `_default_spu_from_sku` 动态导入）
- 物料表中的「赛狐分类」必须与「商品分类导出」末级类名完全一致（含空格）
- CategoryIndex 做末级名→4级路径映射，处理唯一/歧义/非末级/未知四种情况

## 输出（4 sheet）

| Sheet | 受众 | 内容 |
|-------|------|------|
| `商品` | 赛狐导入 | `*SKU` + 4 级分类 |
| `核对` | 运营核对 | 逐行状态 |
| `错误报告` | 运营修正 | 需处理行 |
| `款式_赛狐分类校验` | 运营修正 | 款式级对照 |

## 参考

- [给人看的 README](../../category/README.md)
- [给 Agent 的详细参考](../../category/AGENT_HANDOFF.md)
