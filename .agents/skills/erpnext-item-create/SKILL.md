---
name: erpnext-item-create
description: >
  EN (ERPNext) 物料/变体创建。从底层值表 → 物料属性 → 模板物料 → 变体 → 配套物料(皮壳#/内胆#/重量模板#/包装#)
  的完整创建链条，含 REST API 创建、BOM 复制、客户物料号登记。
  当用户提到"物料创建"、"新建物料"、"item create"、"创建变体"、"配套物料"、"皮壳#"、
  "内胆#"、"重量模板#"、"新建多规格物料"、"物料属性"等时触发。
  不要用于采购成本(item-cost)、商品重尺(item-weight)、库存(stock-init)、图片上传(en-image-upload)。
compatibility: >
  需要 requests。通过 ERPNext REST API (erpnext.vilavi.cn) 操作，凭证在 EN_API/.env
  (PROD_ERP_API_KEY / PROD_ERP_API_SECRET)。
metadata:
  module: en_item_create
  app: key_test
  updated: 2026-08-07
---

# EN 物料/变体创建

ERPNext 物料创建完整链条：底层值表 → 物料属性 → 模板物料 → 变体 → 配套物料 → BOM → 成本列表。

## 快速启动

```bash
cd EN_API
uv run python -c "..."   # 参考 docs/solutions/conventions/erpnext-item-variant-creation-convention.md
```

## 四层结构速查

```
底层值表 (Item Attribute Value All Fabric/Color, FAB-*/CLR-*)
   └─ 物料属性 (custom_select_doctype 引用; 面料/颜色=1, 尺寸=0)
        └─ 模板物料 (has_variants=1) → 变体 (variant_of=模板)
```

## 创建链条（7 步）

1. **校验属性值** — `GET /api/resource/Item Attribute/{属性名}`，缺值先 PUT 追加 `item_attribute_values`
2. **创建面料变体** — `POST /api/resource/Item`（`variant_of`=面料模板，复制同面料其他颜色 `valuation_rate`）
3. **创建皮壳 item** — `PK#{SPU}-{面料abbr}-{尺寸}-{颜色abbr}`，`item_group=皮壳#{物料组}`
4. **创建皮壳 BOM** — 复制同尺寸变体 BOM，换面料，**operations 必须带 workstation**
5. **创建成品 BOM** — 套 `皮壳#` + `内胆#`
6. **创建成品 Item** — `variant_of`=产品模板 + `customer_items`（客户物料号）
7. **BOM 成本列表新增行** — 复制同尺寸变体行

创建 BOM 后需 PUT `{"docstatus": 1}` 提交。

## 配套物料属性规律

| 配套物料 | 属性组合 |
|---------|---------|
| 产品 | 面料+尺寸+颜色 |
| 皮壳# | 面料+尺寸+颜色（同产品）|
| 内胆# | 尺寸+内胆#面料+内胆#颜色 |
| 绍兴包装皮壳#/成品#/半成品# | 尺寸 |
| 波兰PL/美东USNJ/美中USTX包装成品# | 尺寸 |
| 重量模板# | 面料+尺寸（无颜色）|

> 不一定每个 SPU 都用全部 9 类。各 SPU 属性组合可能不同，需先查模板 attributes。

## 硬约束

- 属性值必须先存在，否则创建变体报错
- BOM operations 必须带 `workstation`/`workstation_type`，否则 417
- `stock_uom`：面料用 `米`，成品/皮壳/内胆用 `个`（不是 `Nos`）
- URL 含中文/`#` 需 URL 编码
- 生产服务器 SSH 不可达（IP 白名单），改从 REST API 操作
- 一键生成按钮：模板物料页「一键创建配套物料及变体」→ `key_test.add_item_semi.create_supporting_items_and_variants`（角色 Item Supporting Material Manager/System Manager）

## 详细文档

参见 `docs/solutions/conventions/erpnext-item-variant-creation-convention.md`（含 API payload 示例、命名规律、已知坑）。
