---
okf: v0.1
type: Reference
title: EN 物料字段 default_material_request_type 调查（是否被挪作业务标记 · 与「绍兴发货方式」是否冲突 · 填写正确性）
description: 只读调查 ERPNext 生产库：Item.default_material_request_type 的字段定义与取值域；全库/按前缀的数据分布（尤其是否有「采购 Purchase」值）；哪些 app 代码读或写它；与 Item Group.custom_shipment_type_to_branch（绍兴发货方式）的交叉分布与冲突；能否用于区分三种绍兴发货情况；填写正确性自查（BOM/工单/采购单计数）
date: 2026-10-15
module: tongtool_order_cost
tags: [erpnext, item, material-request, production-plan, ship-method, reference, read-only]
---

# EN 物料字段 `default_material_request_type` 调查

> 数据口径：ERPNext **生产库**（`erpnext.vilavi.cn`，SSH 别名 `阿里云-FZH-ERPNext-frappe`，bench 根 `/home/frappe/frappe-bench`），**全程只读**（只 SELECT；未 INSERT/UPDATE/DELETE，未 migrate / restart / build，临时 SQL 只落服务器 `/tmp`）。
> 背景：怀疑该标准字段被「挪作他用」（当「绍兴是否直接采购 / 要不要工单加工」的标记）。相关前作：[en-shaoxing-ship-method-taxonomy-spec.md](en-shaoxing-ship-method-taxonomy-spec.md)（「绍兴发货方式」= `Item Group.custom_shipment_type_to_branch` 的取值与推导，本文不重复）。
> 规模：全库 `tabItem` **15,210** 行；`tabBOM(docstatus=1)` 7,481 张；`tabWork Order(docstatus=1)` 8,552 张。

## 结论摘要

1. **它是什么**：ERPNext **标准**字段，挂在 **`Item`** 上（不是 `Item Group`）。`fieldname=default_material_request_type`，类型 `Select`，label `Default Material Request Type`，**标准默认值 `Purchase`**，标准选项 5 个：`Purchase / Material Transfer / Material Issue / Manufacture / Customer Provided`。
2. **有没有「采购 Purchase」：有，而且是多数——10,124 个（66.6%）**；`Manufacture`（工单入库）5,086 个（33.4%）。**全库只出现这两个值**，没有任何 `Phantom / Material Transfer / Material Issue / Customer Provided`。所以「大部分是工单入库」的记忆与现状**相反**：现在多数是 `Purchase`。
3. **哪些是 Purchase**：`美中/美东/波兰包装成品` 三类（`USTXBZCP#` 609 / `USNJBZCP#` 583 / `PLBZCP#` 772）**100% 是 Purchase**；`ZLMB#`（重量模板）1,228 全 Purchase；`PK#` 皮壳 1,032 Purchase（另有 1,951 Manufacture）；`SXBZCP#` 415 Purchase / 506 Manufacture；其余 6,991。
4. **不是代码「挪作他用」**：没有任何已装 app 把该字段当业务标记写。**唯一读它的活代码**是 ERPNext 核心 Production Plan（+ `work_order_task` 覆盖里一段与核心同义的拷贝）——用法就是**标准语义**（决定物料需求的类型、是否展开子件）。唯一的非标痕迹是一个**残留 Property Setter**：给 Select 选项加了第 6 个 `Phantom`（由已卸载的 `zelin_pp` 带入），但**数据里 0 个 Phantom**。
5. **与「绍兴发货方式」不冲突，也无关**：二者是**正交维度**。每个发货方式桶里都同时有 Purchase 和 Manufacture（如 `成品`：Purchase 1,838 + Manufacture 1,424）。该字段**不能**推断发货方式。
6. **不能区分三种绍兴情况**（(a) 绍兴直接采购成品 / (b) 绍兴不用加工 / (c) 绍兴仍需加工后发成品）：字段是**按物料**存的、只用了两值、且「Purchase」多数是「建物料时没改的默认值」；`SXBZCP#` 下 Purchase 与 Manufacture 的 BOM 结构几乎一样（自引用 BOM 各 2 / 4 张）。**缺一个专门的「采购/加工模式」维度**。
7. **填写正确性无法自证为「对」**：`Manufacture` 物料有 BOM 的比例（57.7%）确实约是 `Purchase`（27.1%）的两倍；但 **42% 的 Manufacture 物料根本没有 BOM**，**604 个 Purchase 物料却有已提交工单**，`SXBZCP#` 的 **506 个 Manufacture 物料工单数为 0**。→ 该字段**不是**「做了工单 / 只做采购」的可靠记录。
8. **时间线是主要成因**：按建物料年份，2024 年 Manufacture 4,567 > Purchase 3,176；**2025 年 Manufacture 骤降到 495、Purchase 6,198**；2026 年 Manufacture 仅 24。→ 2025 年起**该字段基本不再被主动维护**，新料一律吃默认值 `Purchase`。

## 字段定义与取值域

### 标准定义（`tabDocField`）

| 项 | 值 |
|----|----|
| DocType（parent） | `Item` |
| fieldname | `default_material_request_type` |
| fieldtype | `Select` |
| label | `Default Material Request Type` |
| options（逐字） | `Purchase\nMaterial Transfer\nMaterial Issue\nManufacture\nCustomer Provided` |
| default | `Purchase` |
| 字段位置 | Item 表单第 33 位（`idx=33`） |

### 被 Property Setter 改过（残留）

`tabProperty Setter` 里有一条 `Item-default_material_request_type_options`：

```
doc_type=Item  field_name=default_material_request_type  property=options
value = Purchase\nMaterial Transfer\nMaterial Issue\nManufacture\nCustomer Provided\nPhantom
```

这条来自 **`zelin_pp`** 这个 app 的 fixture 文件（`apps/zelin_pp/zelin_pp/fixtures/property_setter.json`，`"modified": 2023-08-20`），**多加了第 6 个选项 `Phantom`**。但：

- `zelin_pp` **当前未安装**（`bench list-apps` 无此项）；
- **数据里 0 个 `Phantom`**（全库只出现 Purchase / Manufacture 两种值）。

→ 这是一条**没被回滚的派生痕迹**：Item 下拉框在 ERPNext 标准 5 值之外，还会多显示一个 `Phantom`（是否真正可见未实测）。

### 标准语义（字段做什么用）

它是「为这个物料生成的**物料需求（Material Request）默认用哪种类型**」：`Purchase`→采购类 MR，`Manufacture`→生产类 MR（进而喂工单），另有转仓/领料/客供。核心影响面（供 Q6）：

| 位置 | 用法 |
|------|------|
| `erpnext/.../production_plan/production_plan.py:861` | `material_request_type = item.material_request_type or item_doc.default_material_request_type` —— 生产计划生成 MR 时取此值 |
| 同上 `:1249` | `d.default_material_request_type in ["Manufacture","Purchase"] and not d.is_sub_contracted` —— 只有这两类才**展开子件** |
| 同上 `:1311` | `row.get("default_material_request_type") == "Purchase"` 时按 `purchase_uom` 做单位换算 |
| 同上 `:1155 / :1213 / :1337 / :1593 / :1864` | 取该字段填充/判断（标准链路） |
| `erpnext/.../item/item.js:266` | `var type = frm.doc.default_material_request_type; row.material_request_type = type=="Material Transfer"?"Transfer":type` —— **Item Reorder 行**继承该字段（Reorder Level 自动补货生成的 MR 类型随它） |
| `erpnext/.../item/item.py:236` | `if is_customer_provided_item: self.default_material_request_type = "Customer Provided"` —— 唯一的**代码写入点** |

## 数据分布（全库 / 按前缀 / 采购值）

### 全库（15,210 行）

| 值 | 数量 | 占比 |
|----|------|------|
| `Purchase` | **10,124** | 66.6% |
| `Manufacture` | **5,086** | 33.4% |
| 其它（Phantom / Material Transfer / Material Issue / Customer Provided / NULL） | **0** | — |

按是否库存：`is_stock_item=1` → Purchase 9,846 / Manufacture 5,081；`is_stock_item=0` → Purchase 278 / Manufacture 5。

### 按前缀 × 值（全库 15,210）

| 前缀 | Purchase | Manufacture |
|------|----------|-------------|
| `SXBZCP#`（绍兴包装成品） | 415 | 506 |
| `USTXBZCP#`（美中包装成品） | **609** | **0** |
| `USNJBZCP#`（美东包装成品） | **583** | **0** |
| `PLBZCP#`（波兰包装成品） | **772** | **0** |
| `PK#`（皮壳） | 1,032 | 1,951 |
| 其它（含 `ZLMB#` 1,228、`ND#`、无前缀 KS 等） | 6,713 | 2,629 |

> 三个海外「包装成品」前缀**清一色 Purchase**；`ZLMB#` 重量模板 1,228 全 Purchase（它们既无 BOM 也无工单/采购单——纯模板，见下）。

### 「采购-Purchase」值的物料是哪些

- **数量**：10,124 个（其中库存物料 9,846）。
- **构成**：三分公司包装成品（`USTXBZCP# 609 + USNJBZCP# 583 + PLBZCP# 772 = 1,964`）+ `ZLMB# 1,228` + `PK# 1,032` + `SXBZCP# 415` + 其它 5,485。
- **样例（近期新建）**：`PK#KS0455-DM-92x56x75-IVORY`、`KS0455-...-GREY`（无前缀基料）、`ZLMB#KS0455-DM-92x56x75` —— 均为 2026 年新建、字段保持默认。

## 代码里谁读谁写

**读取者（已在服务器 `apps/` 全量 grep）**

| app | 位置 | 状态 | 做什么 |
|-----|------|------|--------|
| `erpnext`（核心） | `erpnext/manufacturing/doctype/production_plan/production_plan.py:861,1155,1213,1249,1311,1337,1593,1864` | **活** | 生产计划：MR 类型、是否展开子件、单位换算 |
| `erpnext`（核心） | `erpnext/stock/doctype/item/item.js:266` | **活** | Reorder 行继承该字段 |
| `erpnext`（核心） | `erpnext/accounts/doctype/pos_settings/pos_settings.js:20` | 活 | 仅列名 |
| `work_order_task` | `.../overrides/production_plan_override.py:560` | **活**（hooks.py:185 覆盖 Production Plan） | `material_request_type = item.material_request_type or item_doc.default_material_request_type` —— 与核心 `:861` 同义 |
| `key_test` | `key_test/key_test/overrides.py:23,31,45,206,313,315,500,554` | **死代码** | 该文件的 `CustomProductionPlan` 依赖 `from zelin_pp.utils import ...`（zelin_pp 未装 → 导入即失败），且 `hooks.py:197-198` 已把 Production Plan 覆盖**注释掉** |
| `zelin_pp` | `overrides.py:23,31,45,256,258,443,497`、`monkey_patches/production_plan.py:155,159,204,258,270,300,309` | **未安装** | 曾按 Manufacture/Phantom 分桶；`monkey_patches/production_plan.py:159` 有 `if default_material_request_type != 'Customer Provided'` 之类判断 |

**写入者**

- 全 app grep `default_material_request_type\s*=` 只命中 **`erpnext/stock/doctype/item/item.py:236`**（`is_customer_provided_item` → `Customer Provided`）。
- 另有一处 `zelin_pp/monkey_patches/production_plan.py:155`（未安装）。
- **数据库内脚本**（`tabServer Script` 15 条 / `tabClient Script` / `tabCustom Script`）**均无** `default_material_request_type` 命中。
- → **没有任何已装 app 的自动逻辑把值写成 `Manufacture` 或 `Purchase`**。现有值只能是：**建物料时手填 / 线下导入 / 建料默认**。

**所有者线索（`owner`，即建档人）**

| 值 | owner Top3 |
|----|-----------|
| Manufacture | `Administrator` 3,914、`wangzhongyu9295@dingtalk.com` 591、`ch3-70i0lr3f2@dingtalk.com` 488 |
| Purchase | `ch3-70i0lr3f2@dingtalk.com` 5,879、`wangzhongyu9295@dingtalk.com` 1,511、`Administrator` 1,431 |

（`ch3-...@dingtalk.com` 形态像共享/集成账号；`Administrator` 建档 3,914 个 Manufacture 更像批量导入。**均未证实**。）

## 与「绍兴发货方式」的交叉与冲突

把每张物料的 KS 号（`REGEXP_SUBSTR(item_code,'KS[0-9]+')`）→ 命中 `Item Group.custom_model_id` → 取 `custom_shipment_type_to_branch`，与 `default_material_request_type` 交叉（全库 15,210）：

| 绍兴发货方式 | Purchase | Manufacture |
|--------------|----------|-------------|
| 皮壳 | 3,925 | 3,352 |
| 成品 | 1,838 | 1,424 |
| 半成品 | 1,080 | 260 |
| （空串） | 116 | 0 |
| 取不到 KS 物料组 | 3,165 | 50 |

**结论：不冲突，也无关——二者正交。** 每个发货方式桶里**同时**有 Purchase 和 Manufacture（连 `成品` 都有 1,424 个 Manufacture）。所以：

- 该字段**推不出**发货方式；发货方式**推不出**该字段。
- 不存在「发货方式=成品 ⇒ 需求类型=工单入库」这种被担心的错配——因为**本来就没有映射关系**，混在一起是常态而非冲突。

**KS 物料组上是否还有相关自定义字段**（`tabCustom Field WHERE dt='Item Group'`，全 21 个）：与本议题相关的**只有** `custom_shipment_type_to_branch`；其余是 `custom_model_id`、`custom_developer_name`、`custom_product_release_date`、`custom_for_sale`、`custom_product_develop_method`、`custom_replaced_by_other_item_group`、`is_leaf_group`、`custom_pdc_*`（PIM/NAS）等——**没有任何**「是否自采购 / 是否需二次加工 / 采购模式」字段。

## 能否区分三种绍兴发货情况

问：能否用 `default_material_request_type` 区分 (a) 绍兴直接采购成品 / (b) 绍兴不用加工 / (c) 绍兴仍需加工后发成品？

**不能。** 理由：

1. **粒度不对**：该字段在 **`Item`** 上（逐规格），而三种情况是 **KS 级/批次级**的业务判断；同一 KS 下不同规格的取值也可不同，无稳定口径。
2. **值域太窄且默认驱动**：只用了 `Purchase / Manufacture` 两值，而 `Purchase` 大多是**建料时没改的默认值**（2025 年起 Manufacture 几乎归零），不承载「自采购/不加工/需二次加工」这第三种语义。
3. **数据上不分离**：`SXBZCP#` 里 Manufacture 与 Purchase 的 **BOM 结构几乎一致**——自引用 BOM 分别 4 张 / 2 张，普通行 1,129 / 1,171；「成品」桶下 Manufacture 270（81 有 BOM）、Purchase 102（49 有 BOM），都约三成有 BOM，无区分度。
4. **缺什么**：要机器可判，需要在 `Item Group`（或 `Item`）上**新增专门的采购/加工模式维度**（如「是否绍兴自采购」+「是否需海外二次加工」两个字段，或把现有「成品」再拆子类）。现状下唯一可用手段仍是 **BOM 内容启发式**（自引用 BOM → 疑似直接采购），见前作 en-shaoxing-ship-method-taxonomy-spec.md。

## 填写正确性自查（带数字）

### 用「有没有 BOM / 工单 / 采购单」反推（库存物料）

| 值 | 库存物料 | 有已提交 BOM | 有已提交工单 | 上过采购单 | 上过采购入库 |
|----|---------|-------------|-------------|-----------|-------------|
| `Purchase` | 9,846 | 2,666 (27.1%) | **604** | 1,520 (15.4%) | 1,642 |
| `Manufacture` | 5,081 | 2,933 (57.7%) | 788 (15.5%) | **4** | **7** |

读法：
- **方向对**：`Manufacture` 有 BOM 的比例（57.7%）约为 `Purchase`（27.1%）的两倍；`Purchase` 里几乎没人上采购单之外还去造工单（上过采购单 1,520 vs Manufacture 仅 4）——**大体朝着标准语义走**。
- **但不干净**：`Manufacture` 里 **2,148/5,081（42.3%）没有 BOM**；`Purchase` 里 **604 个有已提交工单**；`Purchase` 里**只有 15.4% 上过采购单**（说明「Purchase」并不等于「真的采购过」，很大一部分是**从未被动过的默认值**）。

### 按前缀细看（库存物料：n / 有BOM / 有工单 / 上过PO / 上过PR）

| 前缀 | 值 | n | 有BOM | 有工单 | 上过PO | 上过PR |
|------|----|---|-------|--------|--------|--------|
| `PK#` | Manufacture | 1,951 | 1,247 | **544** | 0 | 0 |
| `PK#` | Purchase | 1,032 | 645 | **354** | 0 | 0 |
| `SXBZCP#` | Manufacture | 506 | 196 | **0** | 0 | 0 |
| `SXBZCP#` | Purchase | 415 | 196 | **0** | 0 | 0 |
| `USTXBZCP#` | Purchase | 609 | 264 | 0 | 0 | 0 |
| `USNJBZCP#` | Purchase | 583 | 264 | 0 | 0 | 0 |
| `PLBZCP#` | Purchase | 772 | 264 | 0 | 0 | 0 |
| `ZLMB#` | Purchase | 1,228 | 0 | 0 | 0 | 0 |
| 其它 | Manufacture | 2,624 | 1,490 | 244 | 4 | 7 |
| 其它 | Purchase | 5,207 | 1,033 | 250 | 1,520 | 1,642 |

关键反常：
- **`SXBZCP#` 的 506 个 Manufacture 物料，工单数 = 0**——若字段意在「要不要工单入库」，这里完全没兑现（这批绍兴包装成品在 EN 里**从不走工单**）。
- **`PK#`（皮壳）**：Manufacture 与 Purchase **都有大量工单**（544 / 354），工单并不看这个字段；`PK#` **从不走采购单**（0/0）。
- 全库 Work Order 的 `production_item` 只落在 **`PK#`（4,914 张）和「其它」（4,518 张，多为 `ND#... / 无前缀 KS`）**——**三个「包装成品」前缀工单数全为 0**。

### 时间线（建物料年份 × 值）

| 年份 | Manufacture | Purchase |
|------|-------------|----------|
| 2024 | 4,567 | 3,176 |
| 2025 | **495** | **6,198** |
| 2026 | 24 | 750 |

细分：2024 `PK#` M 1,611 / P 323，`SXBZCP#` M 492 / P 122；2025 `PK#` M 331 / **P 641**（翻转），`SXBZCP#` M 14 / P 262；2025 起新建的三个分公司前缀与 `ZLMB#` **100% Purchase**。

→ **2024 年有人主动把 PK#/绍兴物料标成 Manufacture；2025 年起基本不再标，新料吃默认 Purchase。** 这解释了「为何现在多数是 Purchase」——是**约定/流程断了**，不是业务本意变了。

## 未证实 / 存疑

1. **谁在 2024 年把值设成 `Manufacture`、2025 年为何不再设**：只查到 `owner` 线索（`Administrator` 3,914 / `ch3-70i0lr3f2@dingtalk.com` 5,879）与年份断层，**没有任何 app / 数据库脚本的写入痕迹**，因此推断为「手填或线下导入」，但**具体人/流程/场合未证实**——即用户记忆中「绍兴有人问过我和 Jack、让先用这个字段记录」这件事，**在 EN 与本仓库里都没有留下可核对的记录**。
2. **`ch3-70i0lr3f2@dingtalk.com` 等账号是共享账号还是集成账号**未查。
3. **残留 Property Setter 的 `Phantom` 选项当前是否在 UI 可见 / 是否曾被用过**未实测（数据里确为 0 条 Phantom，但下拉是否显示未验证）。
4. **`SXBZCP#` 的 506 个 `Manufacture` 是否曾经有过操作含义**未证实（当前工单数为 0；这批料如何入库/是否入库均未追）。
5. **只查了生产库**；测试库（`ensh.vilavi.cn`）取值分布未比对。
6. **「绍兴直接采购成品」的判定**仍只能靠 BOM 自引用启发式（本文与前作一致），未找到任何直接字段。

## 证据清单

### 代码（EN 生产库 `/home/frappe/frappe-bench/apps/`，均为只读 grep/sed）

| 位置 | 内容 |
|------|------|
| `erpnext/erpnext/stock/doctype/item/item.json:335` | `default_material_request_type` 字段定义（Select，5 选项，default `Purchase`） |
| `erpnext/erpnext/stock/doctype/item/item.py:236` | 唯一代码写入：`is_customer_provided_item` → `Customer Provided` |
| `erpnext/erpnext/stock/doctype/item/item.js:266` | Reorder 行继承该字段 |
| `erpnext/erpnext/manufacturing/doctype/production_plan/production_plan.py:861,1249,1311` | 标准读取：MR 类型 / 子件展开 / 单位换算 |
| `work_order_task/work_order_task/work_order_task/overrides/production_plan_override.py:560` | 活覆盖里与核心同义的读取（`hooks.py:185` 注册 Production Plan 覆盖） |
| `key_test/key_test/key_test/overrides.py:23,31,45,206,313,500,554` | 死代码（依赖未安装的 `zelin_pp.utils`；`hooks.py:197-198` 注释） |
| `zelin_pp/zelin_pp/fixtures/property_setter.json`（`Item-default_material_request_type_options`） | 给 Select 加 `Phantom` 选项的来源（2023-08-20） |
| `zelin_pp/zelin_pp/overrides.py`、`zelin_pp/zelin_pp/monkey_patches/production_plan.py:155` | 未安装 app 的旧逻辑 |

### SQL / 快照（均为只读；临时文件落服务器 `/tmp/q_*.sql`）

- **字段定义** —— `SELECT ... FROM tabDocField WHERE fieldname="default_material_request_type"` → parent `Item` / Select / options 5 值 / default `Purchase`；`tabCustom Field` 无覆盖。
- **Property Setter** —— `SELECT ... FROM \`tabProperty Setter\` WHERE field_name LIKE "%material_request%"` → `Item-default_material_request_type_options` 加了 `Phantom`。
- **全库分布** —— `SELECT IFNULL(default_material_request_type,"<NULL>"),COUNT(*) FROM tabItem GROUP BY 1` → Purchase 10,124 / Manufacture 5,086。
- **前缀 × 值**（`/tmp/q_grp.sql`、`/tmp/q_pre.sql`）—— 见「数据分布」与「填写正确性」两张表。
- **发货方式 × 值**（`/tmp/q_ig.sql`，KS 用 `REGEXP_SUBSTR(item_code,"KS[0-9]+")` 关联 `Item Group.custom_model_id`）—— 见交叉表。
- **BOM/WO/PO/PR 逐物料存在性**（`/tmp/q_chk.sql`、`/tmp/q_chk2.sql`）—— `EXISTS(tabBOM docstatus=1)` / `EXISTS(\`tabWork Order\` docstatus=1)` / `EXISTS(\`tabPurchase Order Item\`)` / `EXISTS(\`tabPurchase Receipt Item\` docstatus=1)`。
- **年份 × 前缀 × 值**（`/tmp/q_yr.sql`）；**owner × 值**、**disabled × 值**、**样例物料**（`/tmp/q_last.sql`）。
- **Work Order 落点**（`/tmp/q_wo.sql`）—— `production_item` 前缀：`PK#` 4,914 / 其它 4,518，`SXBZCP#`/`USTXBZCP#`/`USNJBZCP#`/`PLBZCP#`/`ZLMB#` 均 0。
- **SXBZCP# BOM 结构 × 值**（`/tmp/q_self.sql`）—— 自引用行/普通行两组几乎相同。
- **DB 脚本**（`/tmp/q_scr.sql`）—— `tabServer Script`(共 15) / `tabClient Script` / `tabCustom Script` 均无命中。
