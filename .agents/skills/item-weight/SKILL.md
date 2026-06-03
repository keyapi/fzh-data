---
name: item-weight
description: >
  赛狐商品重尺导入。从重量模板（手工维护）匹配赛狐 SKU，填入国外发货包装尺寸重量。
  当用户提到"商品重尺"、"重量"、"尺寸"、"item_weight"、"重尺数据"、"包装长宽高"、
  "装箱量"、"单箱重量"、"物流运费"、"weight_size"等时触发。
  不要用于采购成本(item-cost)或库存(stock-init)。
compatibility: >
  需要 pandas, openpyxl。从 item_weight_size/ 目录运行。重量模板含手填字段，由同事维护。
metadata:
  module: item_weight_size
  script: build_saihu_weight_import.py
  updated: 2026-05-20
---

# 赛狐商品重尺导入

同一品类-面料-尺寸的 SKU（仅颜色不同）重尺一致 → 人工维护重量模板(ZLMB#前缀) → 脚本匹配赛狐 SKU 填充。

## 快速启动

```bash
cd item_weight_size
python build_saihu_weight_import.py
```

## 管道概要

重量模板(798行) → 去ZLMB#前缀得键 → 与赛狐SKU(2214行, 取前3段为键)匹配 → 长宽高三者校验 → 填充输出。

## 硬约束

- 长宽高必须三者全部有值才填充
- 装箱量缺省→1（仅在长宽高都有值时生效）
- 输出用 `pd.ExcelWriter(sheet_name='商品')`，不复用模板（openpyxl 会破坏 Data Validation）

## 输出

- `赛狐_重尺导入_{stamp}.xlsx` — 工作表 `商品`
- `重尺_问题报告_{stamp}.xlsx` — 4 sheet（汇总、长宽高不全、模板未匹配、赛狐未匹配）

## 参考

- [给人看的 README](../../item_weight_size/README.md)
- [Agent 详细参考](../../item_weight_size/AGENT_HANDOFF.md) — MappedRow 数据类、字段映射全表、校验规则、列名常量
