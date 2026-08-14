---
okf: v0.1
type: Reference
title: 通途订单 SKU 旧名→新名
description: 井维护新 SKU；订单 Google Sheet 替换旧名；通途 goodsQuery 校验
tags: [sku, remap, tongtool, google-sheet]
resource: tongtool_order_cost/tongtool_order_cost/sku_map.py
timestamp: 2026-08-14
---

# 订单 SKU 旧名 → 新名

通途主档允许改 SKU 字符串。历史订单导出保留**导出当时的名字**；井的特殊规则只填**当前主档名**。1.7.0 对 `通途SKU` 精确匹配，两边不一致就会漏规则。

## 方向

改 **订单 Google Sheet / 1.4 导出** 的旧名，使它等于井的新名。不要把规则表改回旧名。

## 2026-06 AMZBAINAUS FBA Velvet（已确认）

见 `sku_map.py` 中 `OLD_TO_NEW`。

## 例外

| SKU | 处理 |
|-----|------|
| `BNFBAvelvetgray60` | 通途主档存在（60CM 无扣）。不替换。 |
| `FoamFBAKZ159410287-BLACK-97` | 规则笔误。应改为 `...-BLACK-100`。订单里已是 100。 |
| `CENKZ159410287-BLACK-97` | 自发货 CEN，与 Foam FBA 不是同一货。 |

## 替换范围

只改 SKU 列。销量汇总表列名是 `SKU`；写回 FBA+非FBA 表是 `通途SKU`。不改 MSKU。

## 校验

```bash
uv run python tongtool_order_cost/scripts/lookup_tongtool_sku.py BNFBAvelvetgray60 BNFBAvelvetgray-100
```

`goodsQuery` 一次最多 10 个 SKU，且算 1 次 ERP2 商户配额。
