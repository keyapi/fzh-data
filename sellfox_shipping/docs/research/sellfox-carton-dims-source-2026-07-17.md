---
okf: v0.1
type: Research
title: 赛狐重尺来源 — 商品 pageList（非包裹 API）
description: 确认包裹 API 无重尺；用 commoditySku 调 /api/commodity/pageList.json（isGroup=0）取 cartonWeight/LWH；试转换 8/10 命中
timestamp: 2026-07-17
tags: [sellfox-shipping, lizard, cartonWeight, commodity]
---

# 赛狐重尺来源 — 商品 pageList（2026-07-17）

## 结论

| 来源 | 重尺？ | 说明 |
|------|--------|------|
| 包裹 `getPackagePage` / `logistics` | **无** | `packageWeight` 等字段缺失；网页订单下载亦无可靠尺寸（赛狐未开发） |
| **`POST /api/commodity/pageList.json`** | **有** | `cartonWeight`(kg)、`cartonLength/Width/Height`(cm) |
| 商品详情 V2 `commoditySizeVOList` | 有（冗余） | 列表已够用时不必调 |
| ERPNext 重量模板 | 兜底 | 列表为 0 / 未维护时 |

官方查询参数名为 **`isGroup`**（`0`=普通 SKU），不是 `skuType`（Claude 口述别名；带 `skus` 时两者实测均可，实现请用文档字段 `isGroup`）。

## 推荐链路

```
包裹 API → items[].commoditySku
  → pageList { skus: [...], isGroup: "0" }
  → cartonWeight(kg) × 1000 × qty → 上传「重量」(克级)
  → cartonLength/Width/Height → 长/宽/高 (cm)
  → carton 为 0 / 未命中
       → ERPNext Item ZLMB#{style-fabric-size}
            1) custom_finish_good_weight_per_unit + custom_fg_package_length/width/height
            2) custom_fg_weight_per_unit + custom_package_length/width/height
       （重量字段单位：克 → ÷1000 得 kg）
  → 仍未命中 → skipped，人工补录
```

凭证：`EN_API/.env` 的 `ERP_API_KEY` / `ERP_API_SECRET`（或 `PROD_ERP_*`），默认 `https://erpnext.vilavi.cn`。实现：`CascadingDimsLookup(CommodityPageListDimsLookup, ErpnextZlmbDimsLookup)`。

详见 Lesson 17：`SELLFOX_API/docs/lessons/2026-06-25-sellfox-integration-lessons.md`。

## 试转换复核（同 10 单）

`trial-sellfox-to-lizard-upload-10.xlsx` 已按上式重生成：

- **8/10** 有重尺  
- **2/10** 空：`KS0002-DL-194-IVORY` / `KS0002-DL-194-GREY`（SKU 存在但 carton* 为 0）→ 符合「老系列未维护」

## 发货编码

- 当前固定 **`S0143`**（蜴国际子账号/结算号）  
- 日后可能按仓拆：美东 `USNJ` / 美中 `USTX` → 不同发货编码（待业务确认后再做映射）
