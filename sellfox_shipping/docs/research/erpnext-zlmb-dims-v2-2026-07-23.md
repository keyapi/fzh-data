---
okf: v0.1
type: Research
title: EN ZLMB# 重尺借用逻辑 V2
description: ErpnextDimsLookupV2 — 跨面料 sibling 借用 + weight/dims 独立决策
tags: [sellfox-shipping, erpnext, zlmb, dims, carton, routing-engine]
timestamp: 2026-07-23
---

# EN ZLMB# 重尺借用逻辑 V2

## 背景

`ErpnextZlmbDimsLookup` (V1) 仅精确匹配 ZLMB 模板，字段缺失直接返回 None。
V2 新增跨面料 sibling 借用：当精确匹配的模板数据不全时，查找同 KS 编号 + 同尺寸、不同面料的模板借用数据。

## 核心规则

### SKU → ZLMB 映射

```
commodity_sku: KS0001-DM-194-IVORY → 前三段 → key = KS0001-DM-194
ZLMB Item: ZLMB#KS0001-DM-194
```

### Weight 独立决策

```
Priority 1: current.custom_finish_good_weight_per_unit > 0  → ✅
Priority 2: 任一 sibling 的该字段 > 0                       → ✅
Priority 3: current.custom_fg_weight_per_unit > 0           → ✅
Priority 4: 任一 sibling 的该字段 > 0                       → ✅
           → ❌ weight = 0
```

### L/W/H 一体决策（三者缺一不可）

```
Priority 1: current.(FG L,W,H) 三者全 > 0                  → ✅
Priority 2: 任一 sibling 的 (FG L,W,H) 三者全 > 0           → ✅
Priority 3: current.(FTY L,W,H) 三者全 > 0                 → ✅
Priority 4: 任一 sibling 的 (FTY L,W,H) 三者全 > 0          → ✅
           → ❌ dims 不可用
```

### Sibling 搜索

EN API: `GET /api/resource/Item?filters=[["name","like","ZLMB#{style}-%-{size}"]]`

例：`KS0001-DM-194` 的 sibling = `ZLMB#KS0001-*-194`（* ≠ DM）

## 实现

- 文件：`sellfox_shipping/carriers/lizard/erpnext_dims_v2.py`
- 类：`ErpnextDimsLookupV2`
- 缓存：实例内存缓存（commodity_sku → CartonDims | None）+ sibling 池缓存（按 style+size）
- 刷新：`refresh(commodity_sku)` 强制重查

## 查找链

```
CascadingDimsLookup:
  1. RepositoryDimsLookup (shipping_carton_overrides 本地补录)
  2. ErpnextDimsLookupV2 (EN ZLMB# + sibling 借用)
  
（已移除 CommodityPageListDimsLookup — 需代理 SELLFOX_PROXY_API_KEY）
```

## 暂不实现

- 多 SKU 重尺合并（每个 SKU 独立展示）
- 数据库持久化缓存表
