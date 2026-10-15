---
okf: v0.1
type: Reference
title: EN「绍兴发货方式」取值域 · 36 个无 PP棉绍兴 BOM 画像 · 成品→国外加工成本应为 0 核实
description: 只读调查 ERPNext 生产库：「绍兴发货方式」到底是什么字段、取值域与推导链路；36 个无 PP棉绍兴 BOM 的逐张行明细与发货方式；「绍兴发货方式=成品 ⇒ 国外加工成本=0」在数据与代码中的落实程度；是否存在过「国外加工成品 BOM」；三种绍兴发货情况能否区分
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, ustx, shipping-method, bom, item-group, erpnext, reference, read-only]
---

# EN「绍兴发货方式」取值域 · 36 个无 PP棉绍兴 BOM · 成品→国外加工成本应为 0

> 数据口径：ERPNext **生产库**（`erpnext.vilavi.cn`，SSH 别名 `阿里云-FZH-ERPNext-frappe`，bench 根 `/home/frappe/frappe-bench`），**全程只读**（只 SELECT；未 INSERT/UPDATE/DELETE，未 migrate / restart / build，临时 SQL 只落服务器 `/tmp`）。
> 输入清单：`tongtool_order_cost/out/ustx_wage_sim/sheet_ustx_items.csv`（340 行 USTXBZCP# SKU；`bom_status` 含 96 行 `NO_BOM`）。
> 相关前作：[en-ustx-no-bom-items-spec.md](en-ustx-no-bom-items-spec.md)（96 无 BOM 物料画像）、[en-ustx-bom-wage-rate-spec.md](en-ustx-bom-wage-rate-spec.md)（工资率链路）、[ustx-cost-caliber-note.md](ustx-cost-caliber-note.md)（口径变更）。

## 结论摘要

1. **「绍兴发货方式」不是物料组名，而是物料组上的自定义字段 `Item Group.custom_shipment_type_to_branch`**（label `Shipment Type To Branch`，类型 `Select`，选项逐字为 `皮壳 / 成品 / 半成品`）。推导链路：物料代码 → 抽 KS 号 → 找 `custom_model_id == KS号` 的物料组 → 读该字段。
2. **取值域就是 `{皮壳, 成品, 半成品}` 三值 + 空**。在 401 个 `custom_model_id LIKE 'KS%'` 的物料组里：成品 165、皮壳 156、半成品 62、NULL 12、空串 6。
3. **36 个「绍兴 BOM 无 PP棉行」的物料**：34 个 `成品` + 2 个 `皮壳`（KS0018 两规格）。它们的绍兴 BOM 只含**填充（海绵/碎海绵）+ 包装（内/外纸箱、真空袋、自封袋、PO袋、扣胚、春亚纺）**，PP棉 行数**逐张为 0**。其中 6 张是**单行自引用 BOM**（BOM 的子件就是它自己，物料组 `绍兴包装成品#…`），形态正是「绍兴直接采购的成品/皮壳」。
4. **「绍兴发货方式=成品 ⇒ 国外加工成本应为 0」既未在数据上普遍成立、也未在代码里实现。** 代码里**没有任何一处**把「发货方式=成品」翻译成「加工成本置 0」；唯一近似是一条**通途 SKU 后缀特例**（含 `-COVER` → 加工成本 0）。数据上：USTX 成品 96 个物料里仍有 1 个非零（`USTXBZCP#KS0524-140` = 100.79，且已停用）；PL 侧成品有 16 个非零（合计 1621.70）。
5. **不存在「国外加工成品 BOM」这个概念。** 代码里只有「**国外分公司 BOM 复制**」（把绍兴 `SXBZCP#` 的 BOM 复制成 `PLBZCP# / USNJBZCP# / USTXBZCP#`）；前缀映射只有「波兰PL包装成品# / 美东USNJ包装成品# / 美中USTX包装成品#」三种**包装成品**，没有任何「加工成品 / 国外加工」字样或对应 BOM。
6. **三种绍兴发货情况（(a) 绍兴直接采购成品 / (b) 绍兴不用加工 / (c) 绍兴仍需加工后发成品）无法区分**——数据模型只到 `{皮壳, 成品, 半成品}` 这一层，「成品」是**单一桶**；没有「是否自采购 / 是否需要二次加工」的字段或标记。唯一的旁证是 BOM **内容启发式**：BOM 自引用（物料店自采）、或 BOM 只含填充+包装。

## 「绍兴发货方式」的定义与取值域

### 它是什么

**不是** Item Group 的名称，也**不是**从物料名推断；它是挂在 **Item Group** 文档上的自定义字段：

| 项 | 值 |
|----|----|
| 自定义字段名 | `Item Group-custom_shipment_type_to_branch` |
| fieldname | `custom_shipment_type_to_branch` |
| 类型 | `Select` |
| options（逐字） | `\n皮壳\n成品\n半成品` |
| label | `Shipment Type To Branch` |

### 在 `bom_cost_list_v2.py` 里怎么算出来

报告 `work_order_task/work_order_task/work_order_task/report/bom_cost_list_v2/bom_cost_list_v2.py`：

| 位置 | 内容 |
|------|------|
| `:621` | `extract_ks_code_from_item_code(item_code)` —— 去掉 `PK#` 前缀，找 `KS`，收集其后连续的字母数字 → 返回如 `KS0001`（例：`PK#KS0001-HLR-120-PINK → KS0001`） |
| `:723` | `get_shipment_type_by_ks_code(ks_code)` —— `frappe.db.get_value("Item Group", {"custom_model_id": ks_code}, "name")` 找到物料组，再读其 `custom_shipment_type_to_branch` |
| `:1383-1389` | 行构建：`ks_code = extract_ks_code_from_item_code(item_fg)`；`shipping_method = get_shipment_type_by_ks_code(ks_code)` |
| `:1254` / `:1628` | 列声明：`{"label": "绍兴发货方式", "fieldname": "shipping_method", "fieldtype": "Data", "width": 120}` |

关键：**同一 KS 号下的所有规格共享一个发货方式**（因为它按 `custom_model_id` 命中物料组）。KS 号取不到 / 物料组没有 `custom_model_id` / 字段为空 → `shipping_method` 为空串。

### 取值域（实测枚举）

对全库 `Item Group.custom_model_id LIKE 'KS%'`（401 个）统计：

| 值 | 数量 |
|----|------|
| 成品 | 165 |
| 皮壳 | 156 |
| 半成品 | 62 |
| NULL | 12 |
| 空串 | 6 |

即取值域**严格等于** `{皮壳, 成品, 半成品}` 三值（外加「未维护」的空/NULL），与 Select options 逐字一致。

## 36 个无 PP棉绍兴 BOM 的画像

### 口径与来源

清单来源为 96 个 `NO_BOM` 的 USTX SKU 的**绍兴对应变体**（`USTXBZCP#X → SXBZCP#X`）。96 个里 **89 个**绍兴变体存在；其中 **36 个**拥有「已提交 + 默认 + 启用」的绍兴 BOM，**且这 36 张的 PP棉 行数逐张 = 0**。

### 36 张的发货方式

| 发货方式 | 张数 | 备注 |
|----------|------|------|
| 成品 | 34 | |
| 皮壳 | 2 | KS0018-25cm / KS0018-44cm |

其中 **31 个有对应的 `USTXBZCP#` 物料**，**5 个没有**（`USTXBZCP#KS0020-L/M/XL/XXL`、`USTXBZCP#KS0360-153x20x65`；绍兴侧与 sheet 里都有，EN 里没建）。

### 36 张 BOM 的全部行内容（按物料组分桶）

对这 36 个绍兴物料的**所有已提交 BOM**（含非默认版）统计 190 行，物料组分布：

| 物料组 | 行数 |
|--------|------|
| 真空袋 | 52 |
| 海绵 | 42 |
| 外包装纸箱 | 39 |
| 内包装纸箱 | 35 |
| 扣胚 | 5 |
| 自封袋 | 5 |
| 绍兴包装成品#长方形狗床（海绵） | 4 |
| 碎海绵 | 3 |
| 绍兴包装成品#印花石头抱枕 | 2 |
| 春亚纺 | 2 |
| PO袋 | 1 |
| **PP棉** | **0** |

结论：这 36 张是**「填充（海绵/碎海绵）+ 包装（内/外纸箱、真空袋、自封袋、PO袋、扣胚、春亚纺）」**的成品包装 BOM，**没有一件 PP棉**。

### 逐张明细（36 张，sx_item | KS | 发货方式 | BOM | 总行数）

| sx_item | KS | 发货方式 | BOM | 行数 |
|---------|----|---------|-----|------|
| SXBZCP#KS0006-45 | KS0006 | 成品 | BOM-SXBZCP#KS0006-45-001 | 4 |
| SXBZCP#KS0006-60 | KS0006 | 成品 | BOM-SXBZCP#KS0006-60-001 | 4 |
| SXBZCP#KS0018-25cm | KS0018 | 皮壳 | BOM-SXBZCP#KS0018-25cm-001 | 1 |
| SXBZCP#KS0018-44cm | KS0018 | 皮壳 | BOM-SXBZCP#KS0018-44cm-001 | 1 |
| SXBZCP#KS0020-L | KS0020 | 成品 | BOM-SXBZCP#KS0020-L-001 | 1 |
| SXBZCP#KS0020-M | KS0020 | 成品 | BOM-SXBZCP#KS0020-M-001 | 1 |
| SXBZCP#KS0020-XL | KS0020 | 成品 | BOM-SXBZCP#KS0020-XL-001 | 1 |
| SXBZCP#KS0020-XXL | KS0020 | 成品 | BOM-SXBZCP#KS0020-XXL-001 | 1 |
| SXBZCP#KS0190-35 | KS0190 | 成品 | BOM-SXBZCP#KS0190-35-001 | 4 |
| SXBZCP#KS0213-120 | KS0213 | 成品 | BOM-SXBZCP#KS0213-120-001 | 3 |
| SXBZCP#KS0216-180 | KS0216 | 成品 | BOM-SXBZCP#KS0216-180-001 | 5 |
| SXBZCP#KS0219-70 | KS0219 | 成品 | BOM-SXBZCP#KS0219-70-002 | 4 |
| SXBZCP#KS0236-35.5 | KS0236 | 成品 | BOM-SXBZCP#KS0236-35.5-001 | 3 |
| SXBZCP#KS0238-45 | KS0238 | 成品 | BOM-SXBZCP#KS0238-45-002 | 5 |
| SXBZCP#KS0240-45 | KS0240 | 成品 | BOM-SXBZCP#KS0240-45-002 | 5 |
| SXBZCP#KS0241-50 | KS0241 | 成品 | BOM-SXBZCP#KS0241-50-003 | 5 |
| SXBZCP#KS0242-60 | KS0242 | 成品 | BOM-SXBZCP#KS0242-60-001 | 5 |
| SXBZCP#KS0243-60 | KS0243 | 成品 | BOM-SXBZCP#KS0243-60-003 | 5 |
| SXBZCP#KS0310-60 | KS0310 | 成品 | BOM-SXBZCP#KS0310-60-001 | 3 |
| SXBZCP#KS0317-153 | KS0317 | 成品 | BOM-SXBZCP#KS0317-153-003 | 4 |
| SXBZCP#KS0327-68x56x34 | KS0327 | 成品 | BOM-SXBZCP#KS0327-68x56x34-002 | 4 |
| SXBZCP#KS0342-50 | KS0342 | 成品 | BOM-SXBZCP#KS0342-50-002 | 5 |
| SXBZCP#KS0360-153x20x65 | KS0360 | 成品 | BOM-SXBZCP#KS0360-153x20x65-001 | 3 |
| SXBZCP#KS0457-124x87x74 | KS0457 | 成品 | BOM-SXBZCP#KS0457-124x87x74-001 | 6 |
| SXBZCP#KS0458-60x48x40 | KS0458 | 成品 | BOM-SXBZCP#KS0458-60x48x40-001 | 5 |
| SXBZCP#KS0470-50x22x55 | KS0470 | 成品 | BOM-SXBZCP#KS0470-50x22x55-002 | 3 |
| SXBZCP#KS0479-74x48x15 | KS0479 | 成品 | BOM-SXBZCP#KS0479-74x48x15-003 | 4 |
| SXBZCP#KS0480-68x80x76 | KS0480 | 成品 | BOM-SXBZCP#KS0480-68x80x76-001 | 3 |
| SXBZCP#KS0482-155x90x50 | KS0482 | 成品 | BOM-SXBZCP#KS0482-155x90x50-001 | 3 |
| SXBZCP#KS0487-90x40x50 | KS0487 | 成品 | BOM-SXBZCP#KS0487-90x40x50-001 | 2 |
| SXBZCP#KS0488-54x40x10 | KS0488 | 成品 | BOM-SXBZCP#KS0488-54x40x10-001 | 3 |
| SXBZCP#KS0489-100x90x8 | KS0489 | 成品 | BOM-SXBZCP#KS0489-100x90x8-001 | 3 |
| SXBZCP#KS0492-280x142x8 | KS0492 | 成品 | BOM-SXBZCP#KS0492-280x142x8-001 | 2 |
| SXBZCP#KS0524-100 | KS0524 | 成品 | BOM-SXBZCP#KS0524-100-001 | 5 |
| SXBZCP#KS0524-153 | KS0524 | 成品 | BOM-SXBZCP#KS0524-153-001 | 5 |
| SXBZCP#KS0524-194 | KS0524 | 成品 | BOM-SXBZCP#KS0524-194-001 | 5 |

### 像不像「(a) 绍兴直接采购的成品」

**6/36 是单行自引用 BOM**——BOM 的子件就是它自己（qty=1, rate=0），物料组是 `绍兴包装成品#…`：

| BOM | 子件（=自身） | 物料组 | qty | rate | 发货方式 |
|-----|--------------|--------|-----|------|---------|
| BOM-SXBZCP#KS0018-25cm-001 | SXBZCP#KS0018-25cm | 绍兴包装成品#印花石头抱枕 | 1 | 0 | 皮壳 |
| BOM-SXBZCP#KS0018-44cm-001 | SXBZCP#KS0018-44cm | 绍兴包装成品#印花石头抱枕 | 1 | 0 | 皮壳 |
| BOM-SXBZCP#KS0020-L-001 | SXBZCP#KS0020-L | 绍兴包装成品#长方形狗床（海绵） | 1 | 0 | 成品 |
| BOM-SXBZCP#KS0020-M-001 | SXBZCP#KS0020-M | 绍兴包装成品#长方形狗床（海绵） | 1 | 0 | 成品 |
| BOM-SXBZCP#KS0020-XL-001 | SXBZCP#KS0020-XL | 绍兴包装成品#长方形狗床（海绵） | 1 | 0 | 成品 |
| BOM-SXBZCP#KS0020-XXL-001 | SXBZCP#KS0020-XXL | 绍兴包装成品#长方形狗床（海绵） | 1 | 0 | 成品 |

这就是「绍兴直接采购的成品/皮壳」的形态（自己引用自己，等于「买来即发」）。报告本身也把这种形态当**自采购**识别（`bom_cost_list_v2.py:1518`，见下）。其余 30 张是「填充+包装」的成品包装 BOM。

## 成品 → 国外加工成本应为 0（核实结果）

### (7) 计数：按物料 / 按 sheet 行

| 口径 | 成品数量 |
|------|---------|
| USTX 侧发货方式=成品的物料（`custom_model_id` 命中且字段=成品） | **96** |
| sheet（`sheet_ustx_items.csv`）里发货方式=成品的行 | **55** / 340 |

### (8) 是否非零：分布 + 合计

对海外三分公司**成品**物料统计 `Item.valuation_rate`（≠0 计为非零），并给出合计：

| 分公司 | 成品物料数 | 非零个数 | 非零合计 | 备注 |
|--------|-----------|---------|---------|------|
| USTX | 96 | **1** | **100.79** | 唯一非零 = `USTXBZCP#KS0524-140`（`disabled=1`） |
| USNJ | 85 | **1** | **187.04** | 唯一非零 = `USNJBZCP#KS0524-140`（`disabled=1`） |
| PL | 233 | **16** | **1621.70** | 含 `PLBZCP#KS0524-140`（`disabled=1`，158.53）+ 15 个启用项（合计 1463.17） |

**sheet 侧：55 个成品行 `sheet_cost` 全部 = 0**（这与 USTX 侧 92/96 成品压根没有 BOM、valuation_rate=0 一致；唯一的 `KS0524-140` 因 `disabled=1` 被报告置空）。

### (9) 这些成品有没有 `USTXBZCP#` BOM

USTX 侧按发货方式统计「有 BOM 的物料数」：

| 发货方式 | 物料数 | 有任意已提交 BOM | 有「默认+启用」BOM |
|----------|--------|-----------------|-------------------|
| 皮壳 | 373 | 198 | 198 |
| 半成品 | 125 | 62 | 62 |
| **成品** | **96** | **4** | **1** |

4 个有 BOM 的成品：`KS0101-45`、`KS0344-70`、`KS0501-160x85x70`（都只有**非默认** BOM）、`KS0524-140`（有**默认** BOM → 因此 valuation_rate=100.79）。**92/96 的成品完全没有 BOM。**

### (10) 代码证据：规则是否实现

**未实现。** 两处成本链路都没有「发货方式=成品 ⇒ 加工成本=0」：

- **报告 `bom_cost_list_v2.py`**：`destination_processing_cost`（`:1551-1557`）直接取目的分公司 `valuation_rate`，然后在 `:1568`（半成品路径）与 `:1572`（非半成品路径）**无条件加进 `pllc_cover`**；分支只按「是否半成品」划分，**成品落进「非半成品（皮壳/成品/空值）」那一支**，没有任何成品清零逻辑。
  - 报告里唯一与「成品」相关的一条是**自采购识别**（`:1497` 注释、`:1518` 判断）：`if shipping_method == "成品" and cost_fg != 0 and cost_sxbzcp == 0 and BOM 自引用 → sx_cost_all = cost_fg`。它影响的是**绍兴总成本**，**不是**加工成本。
- **`tongtool_integration/.../sync/order_sync.py`**：`shipping_mode == '成品'` 分支（`:2959-3008`）的 **else（无后缀）**只设 `sx_shipping_cost` 与 `first_freight`，**不动 `item.valuation_rate`**；只有 **`-COVER` 后缀特例**（`:2966-2969`）才 `item.valuation_rate = 0`。也就是说「成品 → 加工成本 0」目前**只以通途 SKU 后缀特例存在**，未按「发货方式=成品」普遍实施。

## 是否存在过「国外加工成品 BOM」

**没有证据表明存在过。**

- 全库代码搜 `加工成品` / `国外加工` → **0 命中**（命中的都是「**国外分公司**成品包装长/宽/高」「**国外分公司**BOM复制」这类包装/复制语境）。
- 复制链路的前缀映射只有三种，全是「**包装成品**」（`work_order_task/.../utils/bom.py:25-29`）：

  ```
  波兰PL包装成品# → PLBZCP#
  美东USNJ包装成品# → USNJBZCP#
  美中USTX包装成品# → USTXBZCP#
  ```

- ERPNext 侧没有名为「*加工成品* / *国外加工*」的 Item 或 BOM；概念链路是「**复制绍兴 BOM → 海外包装成品 BOM**」（`copy_bom_for_supporting_items` / `bom_batch_process`），不存在独立的「国外加工成品 BOM」实体。
- 现有 309 张 USTX BOM 的物料前缀清一色 `USTXBZCP#`，无第二种命名。

## 三种绍兴发货情况能否区分

问：能否区分 (a) 绍兴直接采购的成品、(b) 绍兴不用加工、(c) 绍兴仍需加工后发成品？

**不能。数据模型上没有这个维度。**

- 唯一相关字段是 `custom_shipment_type_to_branch`，取值只有 `{皮壳, 成品, 半成品}`。**「成品」是一个单一桶**，(a)/(b)/(c) 全被塞进「成品」。全库 `Item Group` 上**没有**任何「是否自采购」「是否需要二次加工」「加工工序」之类的标记字段。
- **物料组命名也提供不了线索**：KS 物料组按**产品线**命名（如 `三角靠枕类`、`平条靠枕类`、`长方形狗床（海绵）`），不按采购/加工模式命名。
- **唯一可用的区分手段是 BOM 内容启发式**（且不可靠、需人工判断）：
  - **BOM 自引用** → 强烈指向 (a) 绍兴直接采购（报告正是这么当自采购处理的，`bom_cost_list_v2.py:1518`）。本批 36 张里 6 张属此类。
  - **BOM 只含「填充+包装」**（海绵/纸箱/袋）→ 指向「这边只做包装填充」，但分不清 (b) 与 (c)。
- **缺失的字段**：若要机器可判，需要在 `Item Group`（或 `Item`）上新增「采购/加工模式」维度，例如 `是否绍兴自采购` + `是否需海外二次加工` 两个字段（或给「成品」再拆子类）。

## 对成本口径的影响（带数字）

- **USTX**：96 个成品物料里只有 **1 个**非零（`KS0524-140` = **100.79**，且 `disabled=1`）。sheet 上 55 个成品行**全 0**。→ 在 USTX 口径下，「成品应为 0」**事实已基本满足**；强制置 0 只多减 100.79（对一个停用件）。
  - **独立复核（按 sheet 行，由美中对比侧完成）**：`绍兴发货方式=成品` 的 **639 行**，`美中加工成本, USTX` **非 0 行数 = 0**；
    对照 `皮壳` 2853 行中 2760 行非 0（合计 333,645.86）、`半成品` 167 行中 166 行非 0（18,352.87）。
    → **结论：现有美中成本对比（B2/B3）对成品行没有高估**，「成品→0」这条对本项目的美中口径**无影响**（主要影响 PL）。
- **USNJ**：成品 85 个，非零 **1 个**（`KS0524-140` = **187.04**，`disabled=1`）。
- **PL**：成品 233 个，非零 **16 个**，合计 **1621.70**（= 15 个启用项 1463.17 + `KS0524-140` 158.53）。→ **PL 是唯一「成品加工成本大面积非零」的分公司**，若要落实「成品=0」，需清零这 15 个启用项（1463.17）。
- **口径含义**：只要「成品」桶里混着「绍兴直接采购 / 不用加工」的款，它们本不该带国外加工成本；现在靠的是**恰好没建 BOM / 没回写 valuation_rate** 来「碰巧为 0」，一旦给它们补 BOM，就会**冒出不正确的加工成本**。PL 的 15 个非零就是这种漏网（多为手工填报的 valuation_rate，无 BOM）。
- **一致性与 `KS0524-140`**：`成品 + disabled=1` 却在三个分公司都带非零 valuation_rate，是「成品=0」规则的**反例**；成因未查（见「未证实」）。

## 未证实 / 存疑

1. **`KS0524-140`（成品、停用）为何三分公司都带非零 valuation_rate**（USTX 100.79 / USNJ 187.04 / PL 158.53）——**已由用户说明定性（2026-10-15）**：
   `KS0524` 是**三角靠枕·碎海绵填充**款（即「填充物由 PP棉 改海绵」那批）。它**目前只发 FBA**；国外分公司**没有海绵、也不做填充海绵**，
   所以**国外加工成本本就应为 0**。`USTXBZCP#KS0524-140` 被**禁用**很可能正与此相关（不参与国外包装 BOM 链路）。
   注：PL 侧的 `KS0524-140 = 158.53` 是该物料**自身 BOM 的 total_cost**（与本页其余 15 个「无 BOM、手工 valuation_rate」不同源，详见
   [en-pl-finished-processing-nonzero-spec.md](en-pl-finished-processing-nonzero-spec.md)）。仍有未证实项：为什么脚本/流程当时仍给它建了 BOM 并回写。
2. **PL 15 个启用成品的非零 valuation_rate 来源未证实**（合计 1463.17）。已确认它们多数没有 BOM，值更像人工填报，但未逐个回溯。
3. **「绍兴发货方式」的自动来源（物料组字段由谁维护）未查**——本次只证实了**取值与推导**，没查这个 Select 字段是谁、在什么流程里填的。
4. **本报告未把 96 个 `NO_BOM` 之外的全量 USTX 成品逐一比对 sheet**；「成品 96 个 / sheet 55 行」的差集（41 个成品未进 sheet）未展开原因。
5. **「36」是「绍兴对应变体有已提交+默认+启用 BOM」的全集**；若把「非默认 / 已取消」的绍兴 BOM 也算进来，或有更多无 PP棉 的源（未统计）。
6. **`Item Group.custom_model_id` 与 KS 号的唯一性未逐条校验**（存在同 `custom_model_id` 多物料组的可能；本次按「取第一个命中的物料组」处理，与报告 `get_value` 同语义）。
7. **未实测**：把 `shipping_mode='成品'` 的 else 分支改成 `item.valuation_rate = 0` 会产生多大的账期差异（本次只做静态核实与计数）。

## 证据清单

### 代码（EN 生产库 `/home/frappe/frappe-bench/apps/`）

| 位置 | 内容 |
|------|------|
| `work_order_task/.../report/bom_cost_list_v2/bom_cost_list_v2.py:621` | `extract_ks_code_from_item_code()` —— 去 `PK#`、抽 `KS` 号 |
| 同上 `:723-758` | `get_shipment_type_by_ks_code()` —— `Item Group{custom_model_id=ks}` → `custom_shipment_type_to_branch` |
| 同上 `:1383-1389` | 行构建：`shipping_method = get_shipment_type_by_ks_code(ks_code)` |
| 同上 `:1254` / `:1628` | 列「绍兴发货方式」定义 |
| 同上 `:541-560` | `get_item_valuation_rate()` —— 优先「激活+默认」BOM 的 `total_cost`，否则回退 `Item.valuation_rate` |
| 同上 `:1197-1203` | `ustx_valuation_rate` 取值（`is_disabled` 时置 None） |
| 同上 `:1497-1529` | 自采购识别：`成品 & cost_fg≠0 & cost_sxbzcp==0 & BOM 自引用 → sx_cost_all = cost_fg` |
| 同上 `:1551-1573` | `destination_processing_cost` 无条件进 `pllc_cover`；仅按「半成品」分支，**无成品清零** |
| `work_order_task/.../utils/bom.py:25-29` | 前缀映射（只有三种「包装成品」，无「加工成品」） |
| 同上 `:183-200` | `copy_bom_with_new_item` 只保留 `item_group='PP棉'` 的行；PP棉→海绵换料 |
| `tongtool_integration/.../sync/order_sync.py:2959-3008` | `shipping_mode=='成品'` 分支：无后缀不动 `valuation_rate`；仅 `-COVER` 置 0（`:2966-2969`） |
| 同上 `:2934-2960` | `shipping_mode=='皮壳'`：`-PPCOTTON` 清绍兴成本/头程，保留加工成本 |

### SQL / 快照（均为只读；临时文件落服务器 `/tmp` 与仓库 `out/`（已 gitignore））

- **字段定义** —— `SELECT name,fieldname,fieldtype,options,label FROM \`tabCustom Field\` WHERE dt='Item Group' AND fieldname LIKE 'custom_shipment%'` → `custom_shipment_type_to_branch` / `Select` / options `\n皮壳\n成品\n半成品`。
- **取值域** —— `SELECT custom_shipment_type_to_branch,COUNT(*) FROM \`tabItem Group\` WHERE custom_model_id LIKE 'KS%' GROUP BY 1` → 成品 165 / 皮壳 156 / 半成品 62 / NULL 12 / 空 6（共 401）。
- **36 张清单** —— 96 个 `NO_BOM` USTX SKU 的 `SXBZCP#` 对应变体（89 个存在）中，`tabBOM(docstatus=1 AND is_default=1 AND is_active=1)` 命中 36 张，PP棉 行数逐张 = 0（`SELECT COUNT(*) FROM \`tabBOM Item\` bi JOIN tabItem it ON it.name=bi.item_code WHERE bi.parent=<bom> AND it.item_group='PP棉'`）。
- **36 张全部行** —— 190 行物料组分布见上（`out/q36rows_out.tsv`）。
- **海外成品 valuation** —— 三分公司按 `custom_shipment_type_to_branch` 聚合（`out/q_ship_agg.sql`）：USTX 成品 96/1 非零/100.79；USNJ 85/1/187.04；PL 233/16/1621.70。
- **BOM 覆盖** —— 按发货方式统计「有默认 BOM 的物料数」（成品 1、半成品 62、皮壳 198；`out/q_bom_presence.sql`）。
- **非零明细** —— 三分公司成品非零物料的 `name/valuation_rate/disabled`（`out/q_fin_nz.sql`）。
- **sheet 侧** —— `out/ustx_wage_sim/sheet_ustx_items.csv`（340 行；按 ship 分桶：皮壳 216 / 半成品 63 / 成品 55 / 空 6；成品 55 行 `sheet_cost` 全 0）。

### 本地复算脚本（scratch，`out/` 已 gitignore）

- `out/q36.sql` / `out/q36_out.tsv`（96 个 USTX 侧发货方式 + BOM）
- `out/q36b.sql` / `out/q36b_out.tsv`（绍兴侧默认 BOM + PP棉 行数）
- `out/q36rows.sql` / `out/q36rows_out.tsv`（36 张全部 BOM 行）
- `out/q_ship_agg.sql`（三分公司按发货方式聚合）、`out/q_bom_presence.sql`、`out/q_fin_nz.sql`、`out/ks_ig.tsv`（401 个 KS 物料组字段）
