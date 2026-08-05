---
okf: v0.1
type: Research
title: 验证 — ad_group
description: 独立验证 ad_group 列对账与 analyze
tags: [sellfox, verify]
timestamp: 2026-07-28
---

# 验证 — ad_group

- **文件**: `advertise\data\AdGroup_BJRYECLTD-US_2026-06-28_2026-07-27.xlsx`
- **行数**: 282；原始列 27；映射后 27
- **verdict**: PASS

## 列对账

- missing vs `column_maps.py`: 无
- unexpected: 无
- 全空映射列: 无

## 实际表头

```
店铺
日期
广告组
广告活动
定位类型
广告花费
广告曝光量
广告点击量
CPC
广告点击率
广告转化率
ACoS
ROAS
广告订单量
本广告产品订单量
其他产品广告订单量
广告销售额
本广告产品销售额
其他产品广告销售额
广告销量
本广告产品销量
其他产品广告销量
广告活动开始时间
广告活动结束时间
广告组运行状态
广告活动ID
广告组ID
```

## 关键指标样例（映射后）

```json
{
  "spend": {
    "sum": 1498.1100000000001,
    "null_pct": 0.0,
    "non_null": 282
  },
  "sales": {
    "sum": 5064.7300000000005,
    "null_pct": 0.0,
    "non_null": 282
  },
  "orders": {
    "sum": 25.0,
    "null_pct": 0.0,
    "non_null": 282
  },
  "clicks": {
    "sum": 1738.0,
    "null_pct": 0.0,
    "non_null": 282
  },
  "impressions": {
    "sum": 160179.0,
    "null_pct": 0.0,
    "non_null": 282
  }
}
```

## analyze 复跑

```json
{
  "ran": true,
  "ok": true,
  "error": null,
  "keys": [
    "summary",
    "ranking",
    "winners",
    "problems",
    "structural_diagnostics",
    "duplicate_names"
  ],
  "out": "advertise\\out\\verify_2026-07-28\\ad_group_analysis.json"
}
```
