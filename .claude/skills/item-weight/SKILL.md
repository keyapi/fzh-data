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
  inputs: 重量模板（手工填写） + 赛狐商品导出 + 赛狐重尺模板
  outputs: 赛狐重尺导入 + 问题报告（4 sheet）
  updated: 2026-05-20
---

# 赛狐商品重尺导入

## 一句话概括

同一品类-面料-尺寸的 SKU（仅颜色不同）重尺一致 → 人工维护重量模板 → 脚本匹配赛狐 SKU 填充。

## 快速启动

```bash
cd item_weight_size
python build_saihu_weight_import.py
```

## 管道

```
重量模板(798行, ZLMB#前缀) → _weight_match_key(去ZLMB#得键)
赛狐商品(2214行) → _saihu_match_key(前3段)
  → 按键匹配 → 长宽高校验 → 填充字段 → 输出
```

## 匹配规则

- 赛狐 SKU 前 3 段为键（≥4取[:3], =3全串, <3 无匹配）
- 重量模板去 `ZLMB#` 前缀得键
- 长宽高必须三者全部有值才填充

## 输出

- `赛狐_重尺导入_{stamp}.xlsx` — 工作表 `商品`
- `重尺_问题报告_{stamp}.xlsx` — 4 sheet（汇总、长宽高不全、模板未匹配、赛狐未匹配）

## 参考

- [给人看的 README](../../item_weight_size/README.md)
- [给 Agent 的详细参考](../../item_weight_size/AGENT_HANDOFF.md)
