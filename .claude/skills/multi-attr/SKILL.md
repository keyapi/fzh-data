---
name: multi-attr
description: >
  赛狐多属性商品导入 + 通途配对。将 ERPNext 纵向物料导出转为赛狐扁平多属性格式，
  并根据通途 SKU 别名生成配对导入文件。
  当用户提到"多属性"、"multi_attr"、"SPU"、"SKU生成"、"商品导入"、"通途配对"、
  "erpnext_to_saihu"、"erp_tongtu_bridge"、"物料导出"、"属性炸开"等时触发。
compatibility: >
  需要 pandas, openpyxl。从 multi_attr_saihu/ 目录运行。比其他模块更复杂，含 3 个脚本。
metadata:
  module: multi_attr_saihu
  scripts: erpnext_to_saihu.py + tongtu_sku_explode.py + erp_tongtu_bridge.py
  inputs: ERP物料导出 + 赛狐模板 + 通途普通商品 + EN物料属性
  outputs: 多属性商品导入(最多3个) + 通途配对导入(3个)
  updated: 2026-05-20
---

# 赛狐多属性商品导入 + 通途配对

## 一句话概括

3 个脚本组成流水线：
1. 通途 SKU 别名炸开
2. ERP 纵向物料 → 赛狐扁平多属性模板
3. ERP + 通途配对对齐

## 快速启动

```bash
cd multi_attr_saihu

# 步骤 1: 炸开通途 SKU 别名
python tongtu_sku_explode.py

# 步骤 2: ERP 物料 → 赛狐模板
python erpnext_to_saihu.py [物料导出.xlsx] [模板.xlsx] --spu-status "EN物料属性.xlsx"

# 步骤 3: ERP + 通途配对
python erp_tongtu_bridge.py [ERP通途SKU.xlsx] -t 通途SKU别名炸开.xlsx --spu-status "EN物料属性.xlsx"
```

## 流水线

```
通途普通商品 ──→ tongtu_sku_explode.py ──→ 通途SKU别名炸开.xlsx

ERP 纵向导出 ──→ erpnext_to_saihu.py ──→ 赛狐导入_在售/不在售有库存/不在售无库存.xlsx
    (+ 赛狐模板 + EN物料属性)

ERP 通途SKU导出 + 别名炸开 ──→ erp_tongtu_bridge.py ──→ 赛狐配对导入_*.xlsx (3个)
    (+ EN物料属性)
```

## 核心函数（跨脚本引用）

- `_default_spu_from_sku(sku)` → 取 SKU 第一段为款式ID
- `load_spu_status_maps(path)` → 读物料属性 `Sheet1`（在售、还有库存）
- 被 `category/` 动态导入（`importlib.util`）

## 输出

| 文件 | 条件 |
|------|------|
| `赛狐导入_在售_转换结果.xlsx` | 在售=1 |
| `赛狐导入_不在售有库存_转换结果.xlsx` | 在售=0 + 有库存 |
| `赛狐导入_不在售无库存_转换结果.xlsx` | 其余 |
| `赛狐配对导入_*.xlsx` | bridge 输出的配对版 |

## 参考

- [给人看的 README](../../multi_attr_saihu/README.md)
- [给 Agent 的详细参考](../../multi_attr_saihu/AGENT_HANDOFF.md)
