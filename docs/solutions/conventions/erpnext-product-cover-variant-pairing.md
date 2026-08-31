---
okf: v0.1
type: Lesson
title: EN 成品与皮壳 1:1 配对审计与孤儿皮壳重建
description: 按 suffix 审计 KS 成品变体与 PK# 皮壳；补缺失皮壳必须挂模板；variant_of 不可 PUT 须重建；cover-only 暂缓不补成品；一键配套是复制已有变体而非笛卡尔积。
date: 2026-08-20
category: conventions
module: missing_products
problem_type: convention
component: development_workflow
severity: medium
applies_when:
  - "API 核验某 SPU 成品变体与皮壳配套是否 1:1"
  - "成品在、对应 PK# 皮壳变体缺失，需要补建配套物料"
  - "皮壳已存在但 variant_of 为空，PUT 报 CannotChangeConstantError"
  - "看到 cover-only 皮壳、怀疑一键创建配套做了全笛卡尔积"
  - "新对话要复用本审计原则、脚本、skill 与 handoff"
tags:
  - erpnext
  - missing-products
  - variant-of
  - cover-variant
  - supporting-items
  - ks0001
  - pairing-audit
  - cannot-change-constant
related_components:
  - tooling
  - documentation
timestamp: 2026-08-20
---

# EN 成品与皮壳 1:1 配对审计与孤儿皮壳重建

## Context

三角靠枕族（`KS0001` 三角靠枕、`KS0248` 三角靠枕无扣）成品变体与皮壳#（`PK#`）变体必须按 **item_code 后缀**一一配对：成品 `KS0001-CMM-153-PURPLE` 对应皮壳 `PK#KS0001-CMM-153-PURPLE`，属性从成品变体复制，皮壳挂在 `PK#{SPU}` 模板上。

2026-08-20 在生产 `erpnext.vilavi.cn` 用 REST 全量列出 `variant_of` 后对账，再补齐「成品缺皮壳」的 6 条。REST 创建链的食谱仍以 [erpnext-item-variant-creation-convention.md](erpnext-item-variant-creation-convention.md) 为准；本文记录**审计方法、一键配套原理、独立皮壳重建、cover-only 暂缓**，给新开对话和后续 Agent 复用。

此前缺口会用 REST 直接 POST 皮壳 Item。2026-08-07 补 `KS0001-CMM-153-PURPLE` 时，按当时惯例示例建成了无 `variant_of`、无 `attributes` 的独立物料 `PK#KS0001-CMM-153-PURPLE`。产品要求多规格：成品挂 `KS0001`，皮壳挂 `PK#KS0001`。独立皮壳违反规则。ERPNext 上 `variant_of` 是创建后不可改的常量——PUT 会撞 `CannotChangeConstantError`，必须走删除重建。

另一条常见误判：看到「只有皮壳没有成品」就以为是「一键创建配套物料及变体」笛卡尔积多造了 SKU，于是想补成品。一键按钮的 Client Script **并不传具体 SKU、也不做属性值全展开**；cover-only 应记录成因并暂缓。

本工作在分支 `feature/triangle-wedge-cover-audit` 上完成生产写入；合入 main 之前不要当成已发布惯例。

## Guidance

### 后缀配对审计

配对键不是 BOM 行、不是物料组扫表，而是 **去掉模板前缀后的后缀**（面料 abbr + 尺寸 + 颜色 abbr）。

规则在 `missing_products/cover_variant_rules.py`：

- `cover_item_code`：成品 `item_code` 必须以 `{product_template}-` 开头，皮壳码 = `{cover_template}-` + 后缀。
- `cover_item_name`：成品名不加「皮壳#」前缀则补上。
- `classify_cover_gap`：成品没有 `variant_of` → 抛错；皮壳不存在 → `CREATE_VARIANT`；皮壳存在但 `variant_of` 不是皮壳模板或 `attributes` 为空 → `ATTACH_TO_TEMPLATE`；否则 `OK`。

分别列出 `variant_of = 产品模板` 与 `variant_of = 皮壳模板` 的变体，按后缀做集合差：

| 集合差 | 含义 | 本次处理 |
|--------|------|----------|
| 成品后缀 − 皮壳后缀 | 成品缺皮壳 | 按 allowlist 补皮壳变体 |
| 皮壳后缀 − 成品后缀 | 只有皮壳没有成品（cover-only） | **不建产品**，只记录 |
| 独立 `PK#`（`variant_of` 空） | 不算已配对皮壳 | 走挂模板 / 重建 |

独立皮壳不会出现在 `variant_of = PK#{SPU}` 列表里，因此成品侧仍显示「缺皮壳」。`KS0001-CMM-153-PURPLE` 就是这种情况：物料组里已有独立 `PK#KS0001-CMM-153-PURPLE`，后缀审计仍计为 missing cover。

`item_code like PK#{SPU}-%` 只能当辅助：用来抓独立物料或挂错模板的孤儿码，不能替代 `variant_of` 列表。双方都存在时，皮壳 `item_name` 应等于「皮壳#」+ 成品 `item_name`。

### 一键配套物料：复制已有变体，不是笛卡尔积

业务要求的主路径：物料属性齐全 → 创建**成品模板**（`has_variants=1`）→ 在模板页点「一键创建配套物料及变体」。

生产 Client Script「物料 一键创建配套物料及变体 多选菜单」只在 `has_variants=1` 且物料组属于「产品」后代时显示。它把 `item_group`、`item_template_name`、`custom_model_id`、**属性名列表** JSON、勾选的配套 **前缀** JSON 传给 `key_test.add_item_semi.create_supporting_items_and_variants`，**不传具体 SKU**。

数量对账（2026-08-20 生产）：`KS0001` 属性值全组合约 26×12×65 = 20280；`PK#KS0001` 变体 987、成品变体 814、配对后缀 811。一键创建按产品模板 **已有变体复制** 配套变体，不是「属性值全展开」。测试环境另有停用脚本「物料 检查新建 配套物料组 物料模板 复制变体」，语义同样是复制。

因此「只有皮壳没有成品」**不是**一键按钮的正常产物。更可能是：有人在 `PK#` 模板上用系统自带「生成变体」多做了组合，或成品变体被删、皮壳留下。补皮壳缺口时只复制成品已有 `attributes`，不要从底层值表自己做笛卡尔。

### 禁止独立 PK#；`variant_of` 只写一次 → 重建

`validate_supporting_item_payload`：`item_code` 以 `PK#` 开头且不是模板时，必须 `variant_of` 以 `PK#` 开头，且必须带 `attributes`。`create_en_materials.py` 的 `ensure_item` 在 POST 前调用同一校验。

ERPNext 创建后不能改 `variant_of`。`fix_missing_cover_variants.py` 对 `ATTACH_TO_TEMPLATE` 先 PUT；若响应含 `CannotChangeConstantError` 或 `Variant Of`，走 `_recreate_as_variant`：

1. 列出该皮壳 **以及对应成品** 的 BOM，用 `strip_bom_for_recreate` 剥掉元数据、保留工序与 `workstation`。
2. 已提交 BOM 先 cancel（`docstatus=2`）再删除。
3. 删除独立 Item（先确认 Bin / Stock Ledger / Work Order 为空）。
4. 按合法 payload POST 成皮壳模板变体。
5. 按保存的 BOM 重建并提交。

成品 BOM 也要拆，因为它引用皮壳码。无库存才允许这条路径。

### 暂缓的 cover-only（不补成品）

2026-08-20 生产后缀审计：

| 族 | 成品变体 | 皮壳变体 | 配对后缀 | 成品缺皮壳 | 只有皮壳没有成品 |
|----|----------|----------|----------|------------|------------------|
| KS0001 | 814 | 987 | 811 | 3（已补） | **176**（暂缓） |
| KS0248 | 155 | 179 | 152 | 3（已补） | **27**（暂缓） |

KS0001 cover-only 按面料 abbr：TR 78、HLR 29、DM 27、CMM 23、MM 13、YMBL 5、JDTHLH 1。KS0248 的 27 条里包括 `PK#KS0248-CMYH-100-BLUEBUTTERFLY`（无对应成品；同色 60 尺寸成品存在）。

**不为这 176/27 条补成品。** 没有销售/库存/通途主线需求时，补成品会把历史误生成组合固化进产品族。需要时另开范围，先确认客户码与赛狐 SKU，不要从皮壳反推「应该有这个成品」。

### 脚本与测试

- 规则（纯函数）：`missing_products/cover_variant_rules.py`
- 生产补齐：`missing_products/fix_missing_cover_variants.py`（默认 dry-run；`--apply` 才写；allowlist 在 `GAPS`；结束后回读 `variant_of` + 非空 `attributes`）
- 测试：`tests/missing_products/test_cover_variant_rules.py`

```text
uv run python missing_products/fix_missing_cover_variants.py
uv run python missing_products/fix_missing_cover_variants.py --apply
uv run pytest tests/missing_products/test_cover_variant_rules.py -q
```

本脚本只动 EN 皮壳 Item/BOM，不创建赛狐商品、不补 cover-only 成品。赛狐导入前仍须确认范围。

## Why This Matters

独立 `PK#` 不能当多规格皮壳用：一键配套、变体属性、BOM 成本列表都假设皮壳挂在 `PK#{SPU}` 上。`variant_of` 只写一次；只 PUT、不重建，生产上仍是独立物料。把 cover-only 当成一键按钮事故去补成品，会把误生成组合写进产品主数据。

惯例文档一旦写成「独立 POST 皮壳」，后续 Agent 会照抄进生产。校验必须在脚本里，不能只写在 Markdown。

## When to Apply

- 审计某 SPU 成品变体与 `PK#` 皮壳是否一对一（先做后缀差集，再查独立 `PK#`）。
- REST/脚本补皮壳：payload 必须 `variant_of=PK#{SPU}` 且 `attributes` 从成品复制。
- 已存在的独立皮壳：允许先 PUT；失败则在无库存前提下 cancel/delete BOM → delete Item → POST 变体 → 恢复 BOM。
- 解释「皮壳数 > 成品数」：对照一键按钮入参与笛卡尔数量，不要默认补成品。
- 用户只要「成品缺的那几条皮壳」时：扩 `GAPS` allowlist，先 dry-run 再 `--apply`。

## Examples

### 成品缺皮壳：后缀 → 皮壳码

`cover_item_code("KS0001-CMM-153-PURPLE", "KS0001", "PK#KS0001")` → `PK#KS0001-CMM-153-PURPLE`。`item_name` `三角靠枕-纯棉麻-153-紫色` → `皮壳#三角靠枕-纯棉麻-153-紫色`。

### 独立皮壳必须重建（2026-08-07 反例）

`PK#KS0001-CMM-153-PURPLE` 创建于 2026-08-07 17:58，无 `variant_of`、无 `attributes`；成品同日已是 `KS0001` 变体。PUT `variant_of` 触发常量错误后重建。2026-08-20 生产回读：`variant_of=PK#KS0001`，3 个属性。无库存、无工单。皮壳 BOM 与成品 BOM 一并恢复。

### 本次已在生产纠正的 6 条皮壳变体（erpnext.vilavi.cn，2026-08-20）

- `PK#KS0001-CMM-153-PURPLE`（重建）
- `PK#KS0001-DM-140-SKYBLUE`（新建）
- `PK#KS0001-TR-100-ROSERED`（新建）
- `PK#KS0248-DM-153-RED`（新建）
- `PK#KS0248-QDKTR-45-DEEPBLUE`（新建）
- `PK#KS0248-QDKTR-45-GREY`（新建）

`KS0248` 皮壳物料组是 `皮壳#三角靠枕无扣`。

### 暂缓：cover-only 不建产品

`PK#KS0248-CMYH-100-BLUEBUTTERFLY` 有皮壳、无成品。这是 27 条 KS0248 cover-only 之一。记录即可，不要为它对齐去 POST 成品。

## Related

- [EN 物料/变体创建惯例](erpnext-item-variant-creation-convention.md) — REST 创建链、配套 9 类、一键按钮入参、坑 10
- [通途有库存 SKU 三方主线](tongtu-en-sellfox-instock-sku-mainline.md) — 完整通途码登记到 **KS 成品**；`PK#` 客户码不能替代
- [三角类皮壳共享库存代理](sellfox-cover-shared-inventory-transition.md) — 赛狐销售层 `PK# -> KS x1`，不是 EN 生产配对
- `missing_products/AGENT_HANDOFF.md`、`.agents/skills/erpnext-item-create/SKILL.md`、`.agents/skills/missing-products/SKILL.md`
- `missing_products/cover_variant_rules.py`、`missing_products/fix_missing_cover_variants.py`、`tests/missing_products/test_cover_variant_rules.py`
- `CONCEPTS.md`「模板物料」「配套物料」
