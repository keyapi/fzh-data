---
name: multi-attr
description: >
  赛狐多属性商品导入 + 通途配对。将 ERPNext 纵向物料导出转为赛狐扁平多属性格式，
  并根据通途 SKU 别名生成配对导入文件。
  当用户提到"多属性"、"multi_attr"、"SPU"、"SKU生成"、"商品导入"、"通途配对"、
  "erpnext_to_saihu"、"erp_tongtu_bridge"、"物料导出"、"属性炸开"等时触发。
compatibility: >
  需要 pandas, openpyxl。从 multi_attr_saihu/ 目录运行。含 3 个脚本有执行顺序。
metadata:
  module: multi_attr_saihu
  scripts: erpnext_to_saihu.py + tongtu_sku_explode.py + erp_tongtu_bridge.py
  updated: 2026-05-20
---

# 赛狐多属性商品导入 + 通途配对

3 个脚本组成流水线：通途别名炸开 → ERP 纵向转赛狐扁平 → 配对对齐。

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

## 管道概要

通途普通商品 → tongtu_sku_explode.py → 通途SKU别名炸开(3列)。ERP纵向物料 → erpnext_to_saihu.py → 赛狐导入_在售/不在售有库存/不在售无库存(3个)。ERP通途SKU导出 + 别名炸开 → erp_tongtu_bridge.py → 赛狐配对导入_*(3个) + 冲突检验。

## 硬约束

- 属性分类必须**先按后缀**匹配（颜色/尺寸/面料），再回退子串（避免"大尺寸"误判）
- 属性列固定顺序：面料 → 尺寸 → 颜色
- 输出按 `*SKU` 纯字符串序（非自然数序）
- 安全库存和头程报关费**留空( None )**，禁止填 0（0 会覆盖通途现有数据）

## 输出

每个脚本的输出不同，全量见 AGENT_HANDOFF.md §4-6。核心是赛狐导入最多 6 个文件（3 在售拆分 + 3 配对拆分）。

## 参考

- [给人看的 README](../../multi_attr_saihu/README.md)
- [Agent 详细参考](../../multi_attr_saihu/AGENT_HANDOFF.md) — 3 脚本各有完整函数表、自动选文件规则、命令行参数、踩坑记录
