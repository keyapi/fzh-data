---
okf: v0.1
type: Research
title: 验证 — purchased_item
description: 独立验证 purchased_item 列对账与 analyze
tags: [sellfox, verify]
timestamp: 2026-07-28
---

# 验证 — purchased_item

- **文件**: `advertise\data\PurchasedItem_BJRYECLTD-US_2026-06-28_2026-07-27.xlsx`
- **行数**: 14；原始列 16；映射后 16
- **verdict**: PASS

## 列对账

- missing vs `column_maps.py`: 无
- unexpected: 无
- 全空映射列: ['match_type']

## 实际表头

```
店铺
日期
ASIN
SKU
投放
匹配类型
其他ASIN
广告组
广告活动
定位类型
其他SKU销量
其他SKU销售额
广告活动开始时间
广告活动结束时间
广告活动ID
广告组ID
```

## 关键指标样例（映射后）

```json
{}
```

## analyze 复跑

```json
{
  "ran": true,
  "ok": true,
  "error": null,
  "keys": [
    "summary",
    "by_advertised_asin",
    "cross_sell_map",
    "gateway_asins"
  ],
  "out": "advertise\\out\\verify_2026-07-28\\purchased_item_analysis.json"
}
```
