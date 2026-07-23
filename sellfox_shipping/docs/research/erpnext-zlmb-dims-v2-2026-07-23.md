---
okf: v0.1
type: Research
title: EN ZLMB# 重尺借用逻辑 V2
description: ErpnextDimsLookupV2 — 跨面料 sibling 借用 + weight/dims 独立决策
tags: [sellfox-shipping, erpnext, zlmb, dims, carton, routing-engine]
timestamp: 2026-07-24
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

## UI 集成（2026-07-24 更新）

### 包裹详情页

- 重尺字段（重量/长/宽/高）嵌入「商品行」表格子表，每行显示对应 SKU 的重尺数据
- 单个 `<form>` 包裹整表，底部统一「保存全部重尺」按钮
- 重尺来源标签：
  - `EN ZLMB` — 自动从 ERPNext 查询（带 sibling 借用）
  - `本地补录` — 人工覆盖（写入 `shipping_carton_overrides` 表）
  - `缺失` — EN 无数据且无补录

### 后端批量保存

- `POST /packages/{sn}/carton-override` 支持多行提交
- `form.getlist("commodity_sku")` 逐行处理，`_form_val_at()` 按索引取字段值
- 兼容旧版单行提交（`form.get()` 回退）

## 暂不实现

- 多 SKU 重尺合并（每个 SKU 独立展示）
- 数据库持久化缓存表（EN 查询结果仅内存缓存）
