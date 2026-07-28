---
okf: v0.1
type: Research
title: 验证 — campaign
description: 独立验证 campaign 列对账与 analyze
tags: [sellfox, verify]
timestamp: 2026-07-28
---

# 验证 — campaign

- **文件**: `advertise\data\Campaign_BJRYECLTD-US_2026-06-28_2026-07-27.xlsx`
- **行数**: 291；原始列 26；映射后 26
- **verdict**: PASS

## 列对账

- missing vs `column_maps.py`: 无
- unexpected: 无
- 全空映射列: 无

## 实际表头

```
店铺
日期
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
广告活动运行状态
广告组合ID
广告活动ID
```

## 关键指标样例（映射后）

```json
{
  "spend": {
    "sum": 1500.04,
    "null_pct": 0.0,
    "non_null": 291
  },
  "sales": {
    "sum": 5064.7300000000005,
    "null_pct": 0.0,
    "non_null": 291
  },
  "orders": {
    "sum": 25.0,
    "null_pct": 0.0,
    "non_null": 291
  },
  "clicks": {
    "sum": 1741.0,
    "null_pct": 0.0,
    "non_null": 291
  },
  "impressions": {
    "sum": 160348.0,
    "null_pct": 0.0,
    "non_null": 291
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
    "portfolio",
    "status_distribution",
    "winners",
    "problems",
    "thresholds"
  ],
  "out": "advertise\\out\\verify_2026-07-28\\campaign_analysis.json"
}
```
