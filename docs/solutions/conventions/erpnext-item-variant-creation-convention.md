---
okf: v0.1
type: Reference
title: EN 物料/变体创建惯例 — 四层属性体系与配套物料
description: ERPNext 从底层值表到物料属性、模板物料、变体、配套物料（皮壳#/内胆#/重量模板# 等 9 类）的创建惯例，含 API 创建链条与已知坑
tags: [erpnext, item, variant, item-attribute, supporting-items, convention, 物料, 变体, 配套物料]
module: en_item_create
timestamp: 2026-08-07
---

# EN 物料/变体创建惯例

## Context

通途库存 → EN → 赛狐 缺口分析中需要补建缺失物料 `KS0001-CMM-153-PURPLE`（三角靠枕-纯棉麻-153-紫色）。逆向还原了 ERPNext 物料/属性/配套物料的完整体系。此前 `docs/solutions/` 无任何文档记录此惯例，导致每次建物料都要重新摸索。

本文档固化这套惯例，供后续创建缺失物料、评估通途有库存但 EN 未登记时使用。

## 四层结构

```
底层值表 (Item Attribute Value All X, [Stock] 模块)
   ├─ Item Attribute Value All Fabric (FAB-*: abbr + attribute_value)
   ├─ Item Attribute Value All Color  (CLR-*: abbr + attribute_value + supplier_color_number)
   └─ 其他 (Size / Foam Size / Fiber Pad Size 等 48+ 个，按需)
        │  物料属性.custom_select_doctype 引用
        ▼
物料属性 (Item Attribute, 如「三角靠枕面料」)
   ├─ custom_item_group = "三角靠枕"          # 归属物料组
   ├─ custom_select_doctype = "Item Attribute Value All Fabric/Color"  # 面料/颜色引用底层表
   ├─ custom_select_from_all_attribute_values = 1 | 0   # 1=引用底层表, 0=独立(尺寸)
        │  模板物料.attributes 引用
        ▼
模板物料 (has_variants=1)  →  变体 Item (variant_of=模板)
```

### custom_select_from_all_attribute_values 惯例

| 属性类型 | 引用底层表? | 说明 |
|---------|------------|------|
| 面料 | ✅ 引用 All Fabric | 面料通用性强，跨产品复用 |
| 颜色 | ✅ 引用 All Color | 颜色通用性强，跨产品复用 |
| 尺寸 | ❌ 独立 | 尺寸通用性不强，各产品独立定义 |

## 配套物料完整列表（9 类）

模板物料右上角「一键创建配套物料及变体」按钮（Client Script「物料 一键创建配套物料及变体 多选菜单」）可勾选创建以下配套物料。**不一定每个 SPU 都用全部 9 类**（如三角靠枕无「绍兴包装半成品#」）。

| # | 配套物料 | 模板 item_code | item_group | 属性组合 | 说明 |
|---|---------|---------------|-----------|---------|------|
| 1 | 产品 | KS0001 | 三角靠枕 | 面料+尺寸+颜色 | 成品 |
| 2 | 皮壳# | PK#KS0001 | 皮壳#三角靠枕 | 面料+尺寸+颜色（同产品）| 半成品 |
| 3 | 内胆# | ND#KS0001 | 内胆#三角靠枕 | 尺寸+内胆#面料+内胆#颜色 | 几乎单一面料+产品尺寸颜色 |
| 4 | 绍兴包装皮壳# | SXBZPK#KS0001 | 绍兴包装皮壳#三角靠枕 | 尺寸 | 包装 |
| 5 | 绍兴包装成品# | SXBZCP#KS0001 | 绍兴包装成品#三角靠枕 | 尺寸 | 包装 |
| 6 | 绍兴包装半成品# | SXBZBCP#KS0001 | (三角靠枕无此模板) | 尺寸 | 部分产品才有 |
| 7 | 波兰PL包装成品# | PLBZCP#KS0001 | 波兰PL包装成品#三角靠枕 | 尺寸 | 包装 |
| 8 | 美东USNJ包装成品# | USNJBZCP#KS0001 | 美东USNJ包装成品#三角靠枕 | 尺寸 | 包装 |
| 9 | 美中USTX包装成品# | USTXBZCP#KS0001 | 美中USTX包装成品#三角靠枕 | 尺寸 | 包装 |
| 10 | 重量模板# | ZLMB#KS0001 | 重量模板#三角靠枕 | 面料+尺寸 | 减维护 |

> 规律：皮壳# 与产品同属性；内胆# 用产品尺寸 + 内胆专属面料/颜色；各包装# 仅用尺寸；重量模板# 用面料+尺寸（无颜色，减维护）。

## API 创建链条（手动补建缺失变体）

以 `KS0001-CMM-153-PURPLE` 为例，完整链条：

### 1. 校验/新增面料属性值
```http
GET  /api/resource/Item Attribute/纯棉麻颜色
```
若缺 `紫色`，PUT 追加 `item_attribute_values`。**必须先保证属性值存在**，否则创建变体会报错。

### 2. 创建面料变体
```http
POST /api/resource/Item
{
  "item_code": "CMM2020-PURPLE-142-260",
  "item_name": "纯棉麻-紫色-142cm-260g/m2",
  "variant_of": "CMM2020",
  "item_group": "纯棉麻",
  "stock_uom": "米",
  "valuation_rate": 23.5,           # 复制同面料其他颜色
  "attributes": [
    {"attribute": "纯棉麻颜色", "attribute_value": "紫色"},
    {"attribute": "纯棉麻门幅", "attribute_value": "142cm"},
    {"attribute": "纯棉麻克重", "attribute_value": "260g/m2"}
  ]
}
```

### 3. 创建皮壳 item
```http
POST /api/resource/Item
{
  "item_code": "PK#KS0001-CMM-153-PURPLE",
  "item_name": "皮壳#三角靠枕-纯棉麻-153-紫色",
  "item_group": "皮壳#三角靠枕",
  "stock_uom": "个",
  "is_stock_item": 1,
  "include_item_in_manufacturing": 1,
  "is_sales_item": 0
}
```

### 4. 创建皮壳 BOM（复制同尺寸变体，换面料）
```http
POST /api/resource/BOM
{
  "item": "PK#KS0001-CMM-153-PURPLE",
  "routing": "皮壳工艺路线#重量模板#三角靠枕-纯棉麻-153-001",  # 复用
  "items": [
    {"item_code": "CMM2020-PURPLE-142-260", "qty": 2.31, "uom": "米"},  # 换面料
    {"item_code": "NL1010-5#-156-WHITE-PAIR", "qty": 1.0, "uom": "条"}   # 辅材不变
  ],
  "operations": [ ... 复制参照 BOM 的 10 道工序含 workstation ... ]
}
```
参照 BOM：`BOM-PK#KS0001-CMM-153-DEEPBLUE-001`。**operations 必须带 workstation/workstation_type**，否则 417 报「Workstation mandatory」。

### 5. 创建成品 BOM（套皮壳+内胆）
```http
POST /api/resource/BOM
{
  "item": "KS0001-CMM-153-PURPLE",
  "items": [
    {"item_code": "PK#KS0001-CMM-153-PURPLE", "qty": 1, "uom": "个"},
    {"item_code": "ND#KS0001-153-CYF-WHITE", "qty": 1, "uom": "个"}
  ]
}
```
参照 BOM：`BOM-KS0001-CMM-153-DEEPBLUE-001`。

### 6. 创建成品 Item + 客户物料号
```http
POST /api/resource/Item
{
  "item_code": "KS0001-CMM-153-PURPLE",
  "variant_of": "KS0001",
  "item_group": "三角靠枕",
  "stock_uom": "个",
  "attributes": [
    {"attribute": "三角靠枕面料", "attribute_value": "纯棉麻"},
    {"attribute": "三角靠枕尺寸", "attribute_value": "153"},
    {"attribute": "三角靠枕颜色", "attribute_value": "紫色"}
  ],
  "customer_items": [
    {"customer_group": "美国公司", "ref_code": "CEN1608NLinen-Purple-153"}
  ]
}
```
客户物料号在 `customer_items` 子表（doctype `Item Customer Detail`），字段 `ref_code`。

### 7. BOM 成本列表新增行
复制同尺寸变体行（如 `KS0001-CMM-153-DEEPBLUE`），改产品编号/客户物料号/产品名称/产品BOM。

### 提交 BOM
创建 BOM 后需 PUT `{"docstatus": 1}` 提交。

## 命名规律

- 面料 abbr 来自 `Item Attribute Value All Fabric` 的 `abbr`（如 `CMM` = 纯棉麻）
- 颜色 abbr 来自 `Item Attribute Value All Color` 的 `abbr`（如 `PURPLE` = 紫色）
- 产品 item_code = `{模板}-{面料abbr}-{尺寸}-{颜色abbr}`（如 `KS0001-CMM-153-PURPLE`）
- 皮壳 item_code = `PK#{产品SPU}-{面料abbr}-{尺寸}-{颜色abbr}`
- 内胆 item_code = `ND#{产品SPU}-{尺寸}-{内胆面料abbr}-{内胆颜色abbr}`
- 重量模板 item_code = `ZLMB#{产品SPU}-{面料abbr}-{尺寸}`
- 包装# item_code = `{前缀}#{产品SPU}-{尺寸}`

> ⚠️ **item_code 必须用 abbr，不能用中文属性值**（如颜色段用 `LIGHTGREY1` 不是 `浅灰1号`）。赛狐 SKU 只能英文+英文符号，且库存同步需三端编号一致。**反例教训**：石头 12 单石曾用 `KS0018-LSRBS-25cm-浅灰1号`（中文），已用服务器 `frappe.rename_doc` 改为 `KS0018-LSRBS-25cm-LIGHTGREY1` 等。
> ⚠️ **注意**：REST API 不能直接改 item_code（`frappe.rename_doc` 未白名单），需 **SSH + `frappe.rename_doc('Item', old, new)`**（自动更新 BOM/ItemPrice 引用）。改前先移除客户码（客户码全局唯一），改后重加。

## 一键创建配套物料（Client Script + key_test app）

模板物料右上角按钮「一键创建配套物料及变体」，逻辑：
1. 仅模板物料（`has_variants=1`）显示
2. 仅角色 `Item Supporting Material Manager` / `System Manager`（佳佳/高晴）可见
3. 调 `key_test.update_variant_valuation_rate.get_item_groups_descendants`，参数 `parent_item_group_names: ['产品']`，确认当前物料组是产品后代
4. 弹窗勾选 9 类配套物料
5. 调 `key_test.add_item_semi.create_supporting_items_and_variants`，参数：`item_group`、`item_template_name`、`custom_model_id`、`attributes`(JSON)、`prefixes`(JSON)

> 服务器端函数在 `key_test` app（`add_item_semi.py` / `update_variant_valuation_rate.py`）。生产服务器 SSH 不可达（IP 白名单），无法直接读源码；本逻辑由 Client Script + 手动流程推断。

## 已知坑

1. **属性值必须先行**：创建变体前，物料属性里必须已有该属性值（如颜色 `紫色`），否则报错
2. **BOM operations 需 workstation**：皮壳 BOM 复制时 operations 必须带 `workstation`/`workstation_type`，否则 417
3. **stock_uom 用「个」/「米」**：不是 `Nos`；面料用 `米`，成品/皮壳/内胆用 `个`
4. **URL 中文/特殊字符**：Item Group、BOM name 含 `#`/中文，REST API 需 URL 编码（`urllib.parse.quote` 或 requests params）
5. **所有面料名仅用于建产品物料**：`Item Attribute Value All Fabric` 的 `attribute_value` 用于创建产品物料；因历史原因，皮壳 BOM 里的真实面料名与产品面料名、以及产品颜色与 BOM 主面料颜色可能不完全一致（维护在两个地方，历史/人员原因）
6. **⚠️ 属性集完整性（重要）**：产品有颜色，变体**必须含颜色属性**。大多数产品族属性集 = 面料+尺寸+颜色；重量模板# 用 面料+尺寸（减维护）；包装# 仅尺寸。若目标产品族缺颜色属性（历史不完整），**必须先补颜色属性再建变体**，不能接受不完整属性集。**反例**：KS0013 宽边正方形枕头原本只有 面料+尺寸，建方形枕套（咖啡色）时直接建了无颜色变体 `KS0013-HLR-80`，是错误；正确做法是先补 `宽边正方形枕头颜色` 属性再建 `KS0013-HLR-80-COFFEE`。
7. **客户码全局唯一**：一个客户物料号只能登记在一个 EN 物料（自定义 app 校验「客户物料号已存在于其他物料」）。重建/移动时先移除旧物料上的客户码，再登记到新物料。
8. **加属性值必须带 abbr**：ERPNext Server Script 校验 `abbr.lower()`，不带报 500。abbr 来自 All Fabric/All Color 的 `abbr`（如 荷兰绒=HLR, 咖啡色=COFFEE）。
9. **变体命名规律**：`{模板}-{面料abbr}-{尺寸abbr}-{颜色abbr}`；尺寸 abbr 来自属性值（如 41cm=41, 80*80*18=80）。

## When to Apply

- 通途有库存但 EN 未登记客户物料号，需评估是否创建产品物料
- 赛狐需新增多属性商品，但 EN 缺对应变体
- 补建缺失的配套物料（皮壳#/内胆#/重量模板#/包装#）
- 理解 EN 物料四层体系的任意操作

## 已审计确认（2026-08-10）

2026-08-10 创建的老产品物料（星球 7、石头 14、张嘴熊 1、方形枕套 1）已全部审计，**仅 KS0013-HLR-80 缺颜色（已删）**，其余均含完整 面料+尺寸+颜色。教训：创建后应做属性完整性审计（每变体查 `attributes` 是否含 面料/尺寸/颜色）。
