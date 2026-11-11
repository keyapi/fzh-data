---
okf: v0.1
type: Reference
title: 「剔除额（追加半成品成本修正）」完整定义与影响面 —— get_sxbzbcp_deduction 只减不加
description: 逆向 ERPNext V2 报表 bom_cost_list_v2.py 里「绍兴发货方式=半成品」时的重复计成本剔除（get_sxbzbcp_deduction）：公式与输入、进入哪些输出列、订单同步《绍兴发货成本》是否受影响（确定结论：非FBA不受影响）、其它发货方式是否涉及、Jack 的改动 commit（533ecad / cf0bbbd，2026-10-10）、以及用 2026-09-03 快照证实「绍兴包装成品成本=成品 BOM 全额、未扣剔除额」
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, shaoxing, bom, deduction, sxbzbcp, erpnext, order-sync, reference, read-only]
---

# 「剔除额（追加半成品成本修正）」完整定义与影响面

> 数据口径：ERPNext **生产库**（`erpnext.vilavi.cn`，SSH 别名 `阿里云-FZH-ERPNext-frappe`，bench 根 `/home/frappe/frappe-bench`），**全程只读**（只 SELECT；未 INSERT/UPDATE/DELETE，未 migrate / restart / build；临时 SQL 只放服务器 `/tmp`）。
> 相关前作：[en-shaoxing-shipment-cost-logic-spec.md](../en-shaoxing-shipment-cost-logic-spec.md)（按发货方式组合绍兴成本 · 订单同步《绍兴发货成本》）、[en-shaoxing-ship-method-taxonomy-spec.md](../en-shaoxing-ship-method-taxonomy-spec.md)、[old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md)。

## 结论摘要

1. **剔除额只有一处定义**：`work_order_task/.../report/bom_cost_list_v2/bom_cost_list_v2.py:224-252` 的 `get_sxbzbcp_deduction(bom_sxbzbcp, pkg_item_groups)`。
   公式 = **`半成品 BOM 的 operating_cost` + Σ(半成品 BOM 中物料组属于「包装箱」或「包装袋」子树的 BOM Item 的 `amount`）**，是**每 1 件半成品**的金额；调用时再 **× `绍兴包装成品 BOM 中「半成品整件」那一行的 qty`**（`deduct_qty`）。
2. **只减不加**：只在 `绍兴发货方式 == "半成品"` 时触发；结果写回 **`cost_sxbzcp`（绍兴包装成品成本）**，再随动到 **`sx_cost_all`（绍兴总成本）**。**不修改** `皮壳成本`、`绍兴包装半成品成本`、加工成本三列、头程运费三列。
3. **用户最关心的判定（确定结论）**：订单同步里的 **《绍兴发货成本》在「半成品」+ 非 FBA 仓库时 = `皮壳成本 + 绍兴包装半成品成本`（`order_sync.py:3005-3010`），两项都不被剔除额改动 → 不受影响**。剔除额只改 `cost_sxbzcp`，半成品分支根本不读它。
   > ⚠️ 唯一例外：**FBA 仓库**走 `sx_cost_all`（`order_sync.py:2924-2928`），而 `sx_cost_all` 对半成品行**是**被剔除额改过的 → FBA 仓的半成品产品《绍兴发货成本》**会**被间接影响（见「存疑」）。
4. **其它发货方式（皮壳 / 成品 / 空）**：代码把剔除**硬闸在 `== "半成品"`**，因此一律不触发。数据侧看双计前置条件（成品 BOM 是否引用了 `SXBZBCP#` 整件）：皮壳 0 行、成品 1 行、半成品 61 行 → 「非半成品一般不存在绍兴包装半成品」成立（仅 1 例例外，且它因闸门**不会**被剔除，见「存疑」）。
5. **Jack 的改动已定位并在生产库 `main` 上**：`work_order_task@533ecad961c864f3ecdf3d21ad7fc8e7ea78b84e`（2026-10-10 14:35:29 +0800，作者 `Jack-wq-ops <2314176017@qq.com>`，+49 行）；同内容在 `key_test@cf0bbbd`（2026-10-10 14:36:24，改 `report/bom_cost_list/bom_cost_list.py`，+49 行）。**未见 PR**（app 仓库直接提交 `main`）。
6. **数据验证（2026-09-03 快照 × 现库）**：该 3693 行快照的 `绍兴包装成品成本` = **成品 BOM 的全额**（59/61 个半成品 BOM 与现库 `total_cost` 精确相等；样本 KS0495 快照 398.3743333 = 现库 `BOM-SXBZCP#KS0495-143x84x88-001.total_cost` 398.3743333）→ **快照未扣剔除额**，与 Jack 提交（10-10）的时序一致。

## 剔除额的定义（公式 + 输入）

### 函数体（逐字，`bom_cost_list_v2.py:224-252`）

```python
def get_sxbzbcp_deduction(bom_sxbzbcp, pkg_item_groups, deduction_cache=None, item_name_group_cache=None):
    """绍兴包装半成品 BOM 里应剔除的金额（每 1 件半成品）。"""
    if not bom_sxbzbcp:
        return 0
    if bom_sxbzbcp in deduction_cache:
        return deduction_cache[bom_sxbzbcp]

    # 包装工序成本（BOM.operating_cost = 各工序工时费之和）
    deduction = flt(frappe.db.get_value("BOM", bom_sxbzbcp, "operating_cost") or 0)

    for bi in frappe.get_all("BOM Item", filters={"parent": bom_sxbzbcp},
                             fields=["item_code", "item_name", "amount"]):
        _item_name, item_group = get_item_name_group(bi.get("item_code"), item_name_group_cache)
        if item_group in pkg_item_groups:
            deduction += flt(bi.get("amount") or 0)

    deduction_cache[bom_sxbzbcp] = deduction
    return deduction
```

### 输入分解

| 维度 | 取值 | 依据 |
|---|---|---|
| 取哪张 BOM | 被剔除的是**「绍兴包装半成品」BOM**（`bom_sxbzbcp`，由 `get_sxbzbcp_info` 拼 `绍兴包装半成品#{item_group}` → `custom_model_id` → `{id}-{size}`，`:318-353`） | `:1511-1513` |
| 取哪些 BOM Item 行 | **只取** `parent = 该半成品 BOM` 的**直接子件**（`frappe.get_all("BOM Item", {"parent": bom_sxbzbcp})`，**不递归子树**） | `:242-246` |
| 按什么判定「是包装」 | **按物料组**：`item.item_group ∈ pkg_item_groups`，`pkg_item_groups = 子树(「包装箱」) ∪ 子树(「包装袋」)`（`:1056-1057`，用 `get_item_groups_descendants` = `WITH RECURSIVE` 取所有子孙组，`key_test/search_item_by_item_group_and_name.py:5-20`）。**不按物料名** | `:1056-1057`、`:247-249` |
| 工序金额 | `BOM.operating_cost`（**整张半成品 BOM 的工序费合计**，不进 items 循环） | `:240` |
| 物料金额 | `BOM Item.amount`（**已含 `qty × rate` 的金额，不再乘子件 qty**） | `:249` |
| 乘数 | 调用处 `× flt(deduct_qty)`，而 `deduct_qty = 绍兴包装成品 BOM 中 item_code = 半成品整件( item_sxbzbcp ) 那一行的 qty`（`frappe.db.get_value("BOM Item", {"parent": bom_sxbzcp, "item_code": item_sxbzbcp}, "qty")`） | `:1506-1513` |

**为什么整条链成立**：`绍兴包装成品 BOM` 直接引用了 `绍兴包装半成品` **整件**（BOM Item `item_code = SXBZBCP#…`，其 `amount = 半成品 BOM total_cost`），于是半成品自带的「包装工序 + 纸箱 + 袋」在成品层 **又被算了一遍** → 从「绍兴包装成品成本」里减掉这一份。

**包装子树实况（只读查 `tabItem Group`）**：

- 子树(`包装箱`) = {`包装箱`, `内包装纸箱`, `外包装纸箱`}
- 子树(`包装袋`) = {`包装袋`, `PO袋`, `PP袋`, `拉链塑料袋`, `真空袋`, `编织袋`(组)→{`不带背胶编织袋`,`带背胶编织袋`,`红心编织袋`}, `自封袋`}
- ⚠️ 名字里带「袋」但**不属于**上述子树、故**不**被剔除的：`内胆#…收纳袋`、`助眠睡眠袋`、`床边收纳袋`、`垃圾袋`（分属「内胆#/配件/易耗品」）。这正是代码注释「按物料组认定、避免名字误伤」的实际效果。

### 调用处（逐字，`bom_cost_list_v2.py:1500-1530`）

```python
cost_sxbzcp_val = cached_info.get("cost_sxbzcp", 0) or 0
if str(shipping_method or "").strip() == "半成品" and cached_info.get("bom_sxbzcp"):
    deduct_qty = frappe.db.get_value("BOM Item",
        {"parent": cached_info.get("bom_sxbzcp"), "item_code": cached_info.get("item_sxbzbcp")}, "qty")
    if deduct_qty:
        deduction = get_sxbzbcp_deduction(
            cached_info.get("bom_sxbzbcp"), pkg_item_groups, deduction_cache, item_name_group_cache) * flt(deduct_qty)
        cost_sxbzcp_val = max(cost_sxbzcp_val - deduction, 0)
        row["cost_sxbzcp"] = cost_sxbzcp_val        # ← 覆写「绍兴包装成品成本」列
sx_cost_all_val = 0
if shipping_method == "成品" and (cost_fg or 0) != 0 and cost_sxbzcp_val == 0:   # 自采购特例
    if bom_fg and bom_has_item(bom_fg, frappe.db.get_value("BOM", bom_fg, "item"), bom_items_cache):
        sx_cost_all_val = cost_fg or 0
else:
    if bom_fg and cached_info.get("bom_sxbzcp"):
        sx_cost_all_val = (cost_fg or 0) + (cost_sxbzcp_val or 0)   # ← 用扣后的 cost_sxbzcp_val
row["sx_cost_all"] = sx_cost_all_val
```

（`cost_sxbzcp_val` 原始值来自 `get_default_bom_and_cost` = `BOM.operating_cost + raw_material_cost + scrap_material_cost`，`:96-120`。）

## 受影响的输出列（完整清单）

### 被剔除额**修改**的列（仅 `绍兴发货方式 == "半成品"` 的行）

| 层 | 列 / 字段 | 代码 | 说明 |
|---|---|---|---|
| V2 报表列 | **绍兴包装成品成本**（`cost_sxbzcp`） | `:1514-1515` | 直接减法覆写（`max(…-deduction, 0)`） |
| V2 报表列 | **绍兴总成本**（`sx_cost_all`） | `:1528` | = `皮壳成本 + 扣后成品成本` → 同步降低 |
| V2 报表列 | **发成品尾程前成本**（`pllc_fg_{price}`，全部价格表） | `:1600` | = `sx_cost_all + 成品运费` → 随之降低 |
| 订单同步 | `order item.cost_sxbzcp` | `order_sync.py:2899-2900` | = 报表该列 × 数量 |
| 订单同步 | `order item.sx_cost_all` | `order_sync.py:2901-2902` | = 报表该列 × 数量 |
| 订单同步 | `order item.sx_shipping_cost`（**仅 FBA 仓**） | `order_sync.py:2924-2928` | FBA 无条件取 `sx_cost_all` → 间接被影响 |

### **不**受剔除额影响的列

| 列 / 字段 | 代码 | 理由 |
|---|---|---|
| 皮壳成本（`cost_fg`） | `:1369-1401` | 剔除只减成品成本 |
| 绍兴包装半成品成本（`cost_sxbzbcp`） | `:1419` | 半成品成本列**只被读取（`pllc_cover`）、从不被减** |
| 各目的地加工成本 `usnj/ustx/pl_valuation_rate` | `:1177/1190/1203` | 取对应目的地成品 BOM `total_cost`，与剔除无关 |
| 头程三列（皮壳/半成品/成品运费） | `:1533-1549`、`transform_logistic_header :834-858` | 按价格表算运费，与剔除无关 |
| 发皮壳/发半成品尾程前成本（`pllc_cover`） | `:1560-1585` | 半成品分支用 `cost_fg + cost_sxbzbcp`（未减） |
| 订单同步 `sx_shipping_cost`（**非 FBA**：皮壳 / 半成品 / 成品） | `order_sync.py:2935-3013` | 皮壳→`cost_fg`；半成品→`cost_fg+cost_sxbzbcp`；成品→`sx_cost_all`（成品行不触发剔除） |
| 订单同步 `first_freight`、加工成本 `valuation_rate` | `order_sync.py:2910-2917`、`:2950-2958` 等 | 取自头程/加工成本列 |
| 重量、体积、图片、填充物、工序等 | 全表 | 与成本无关 |

## 半成品发货成本是否受影响（判定）

**结论（确定）：非 FBA 仓库下，「绍兴发货方式 = 半成品」的订单同步《绍兴发货成本》不受剔除额影响。**

代码链（`tongtool_integration/tongtool_integration/sync/order_sync.py`）：

```python
# :2920-2921
is_fba_warehouse = 'FBA' in warehouse_classification.upper()
# :2932  非FBA分支
shipping_mode = (bom_row.get(shipping_method_field) or "").strip()
...
# :2984  elif shipping_mode == '半成品':
# :3005-3010（无 -COVER/-FOAM 后缀时）
cost_sum = 0
if cost_fg_field:        cost_sum += bom_row.get(cost_fg_field) or 0        # 皮壳成本（未减）
if cost_sxbzbcp_field:   cost_sum += bom_row.get(cost_sxbzbcp_field) or 0   # 半成品成本（未减）
item.sx_shipping_cost = flt((cost_sum or 0) * quantity * factor, 4)
```

- 字段映射（`order_sync.py:2852-2860` + `_get_warehouse_cost_config :2193-2242`）：`cost_fg_field ← '皮壳成本'`、`cost_sxbzbcp_field ← '绍兴包装半成品成本'`、`sx_cost_all_field ← '绍兴总成本'`、`cost_sxbzcp_field ← '绍兴包装成品成本'`。
- **半成品分支只读 `皮壳成本` 与 `绍兴包装半成品成本`，从不读 `绍兴包装成品成本`** → 剔除额（只改后者）无从影响它。
- 这与用户的预期判断**一致**（半成品发货成本 = 皮壳成本 + 绍兴包装半成品成本，不受剔除额影响）。

> **FBA 例外**：`is_fba_warehouse` 分支（`:2924-2928`）忽略发货方式、无条件 `sx_shipping_cost = 绍兴总成本 × qty × factor`；而半成品行的「绍兴总成本」是**被剔除额降过的**。因此**若**某半成品产品的订单落在 FBA 仓，其《绍兴发货成本》会**间接**变小。此组合是否真实发生未取订单核实 → 见「存疑」。

## 其它发货方式是否涉及

**代码侧**：闸门 `if str(shipping_method).strip() == "半成品"`，故 皮壳 / 成品 / 空 → 剔除额恒为不参与（不是「算出 0」，而是整段跳过）。

**数据侧（双计前置条件：成品 BOM 是否引用了 `SXBZBCP#` 整件）** —— 对快照里 370 个「绍兴包装成品 BOM」逐一核对（只读 SQL）：

| 发货方式 | 涉及的「成品 BOM」行数 | 其中「成品 BOM 引用了 `SXBZBCP#` 整件」 |
|---|---|---|
| 皮壳 | 181 | **0** |
| 半成品 | 61 | **61** |
| 成品 | 128 | **1** |
| 空/NULL | 0（快照 34 行为空，无对应成品 BOM） | 0 |

→ 「非半成品一般不存在绍兴包装半成品」**成立**；唯一例外是 1 个**成品**行：

- 产品 `KS0501-FMYJBHLR-160x85x70-TANGERINEBROWN…`，`绍兴发货方式 = 成品`，但其 `绍兴包装成品 BOM = BOM-SXBZCP#KS0501-160x85x70-001` **确实**引用了 `SXBZBCP#…` 整件 → 双计条件成立，**却因闸门不会触发剔除**（见「存疑」）。

## Jack 的改动（commit/PR）

| 仓库 | commit | 日期（+0800） | 作者 | 改动文件 | 摘要 |
|---|---|---|---|---|---|
| `work_order_task` | **`533ecad961c864f3ecdf3d21ad7fc8e7ea78b84e`** | **2026-10-10 14:35:29** | `Jack-wq-ops <2314176017@qq.com>` | `…/report/bom_cost_list_v2/bom_cost_list_v2.py`（+49） | 绍兴发货方式 = 半成品时「绍兴包装成品」BOM 直接引用了「绍兴包装半成品」整件，导致半成品自带的包装工序 + 纸箱 + 袋被重复计入「绍兴包装成品成本」。需在取值时剔除，同时保持 绍兴总成本 = 皮壳成本 + 绍兴包装成品成本 |
| `key_test` | **`cf0bbbd611318ea66e6563375b3ddca16e05defc`** | **2026-10-10 14:36:24** | `Jack-wq-ops <2314176017@qq.com>` | `…/report/bom_cost_list/bom_cost_list.py`（+49） | 同上（老报表副本） |

- 两者均为 `main` 的**祖先已合入**（`git merge-base --is-ancestor … HEAD` = YES）；生产库当前 `work_order_task` HEAD = `e667558`（2026-10-12 15:05，`main`）。
- `git log -S 'sxbzbcp_deduction' / '剔除' / 'deduction'` 全量扫三个 app：**仅命中 Jack 这两笔**（`tongtool_integration` 零命中）。
- **未找到 PR**（app 仓库工作流为直推 `main`，无 GitHub PR 记录）。
- 时间相邻的 Jack 其它提交（同属成本列调整，但**与剔除无关**）：`68df651`（2026-10-09，包装成本标签）、`aa456da`（2026-10-10，包装成本标签优化）、`ee14bd1`（2026-10-12，加工成本改取 `total_cost`）、`e667558`（2026-10-12，加工成本列点击跳 BOM）。

## 数据验证

**数据源 A**：快照 CSV `tongtool_order_cost/out/profitability_audit/2026年7月订单_ustx2/en_bom_cost/EN产品BOM成本列表20260202.csv`（3693 行；col4=`绍兴发货方式`、col12=`皮壳成本`、col13=`绍兴包装半成品成本`、col14=`绍兴包装成品成本`、col15=`绍兴总成本`，此处为 0 基索引 11/12/13/14）。
**数据源 B**：现库只读 SQL（`tabBOM.total_cost` / `tabBOM Item`）。

### 1. 分布与不变量（快照 3693 行）

| 项 | 值 |
|---|---|
| `绍兴发货方式` 分布 | 皮壳 2853 / 成品 639 / 半成品 167 / 空 34 |
| `绍兴总成本 == 皮壳成本 + 绍兴包装成品成本` | **3404 行** |
| `绍兴总成本 == 0` | 289 行 |
| `绍兴总成本 == 皮壳 + 半成品 + 成品`（三段相加） | **0 行** |

→ 与 [en-shaoxing-shipment-cost-logic-spec.md](../en-shaoxing-shipment-cost-logic-spec.md) 结论一致：**报表「绍兴总成本」从不是三段相加**（半成品只被剔除、从不被加）。

### 2. `绍兴包装成品成本` 是否已扣剔除额？（快照 col14 vs 现库 `BOM.total_cost`）

对快照中**全部 370 个不同的「绍兴包装成品 BOM」**逐一对现库 `tabBOM.total_cost`（同 BOM 名）：

| 关系 | 数量 |
|---|---|
| 快照 == 现库全额（未扣；或期间成本未变） | **136** |
| 现库 > 快照（快照后原料涨价，与剔除无关） | 182 |
| 现库 < 快照（快照后成本下调，与剔除无关） | 52 |

**按发货方式拆分「半成品」**（61 个半成品用到的成品 BOM）：

| 关系 | 数量 |
|---|---|
| 快照 == 现库全额 | **59** |
| 快照 ≠ 现库（且均为**现库 > 快照** = 涨价） | 2（`BOM-SXBZCP#KS0437-120x200x45-001` 346.94→351.45；`BOM-SXBZCP#KS0206-75-002` 68.988→69.618） |

→ **没有一个半成品 BOM 出现「快照 < 现库全额 − 剔除额」这类扣除特征**；差异全部是「现库 > 快照」的原料涨价方向（扣除只会让快照**更低**，与观测相反）。

### 3. 逐行精确对照（样本 KS0495，决定性）

| 口径 | 值 |
|---|---|
| 快照 col14 `绍兴包装成品成本` | **398.3743333** |
| 现库 `BOM-SXBZCP#KS0495-143x84x88-001.total_cost` | **398.374333333**（= operating 5.833… + raw 392.541） |
| 现库 `BOM-SXBZBCP#KS0495-143x84x88-001`（半成品）`operating_cost` | 2.916666667 |
| 该半成品 BOM 的包装子树物料 `amount` | 内包装纸箱 12.0（NBZX1470…）+ 外包装纸箱 0.484（WBZX1460…）+ 真空袋 2.19（ZKD1010…）+ PO袋 0.9（POD1400…） |
| 成品 BOM 里「半成品整件」行 qty（`deduct_qty`） | 1.000000000 |
| **按现行代码应算的剔除额** | 2.916666667 + (12.0+0.484+2.19+0.9) = **18.4906667**；即 `扣后成品成本 = 379.8836667` |
| 快照实际值 | **398.3743333 = 全额（未扣）** |

→ **证实**：2026-09-03 快照**未扣**剔除额（快照值 = 成品 BOM 全额）。与 Jack 提交日 2026-10-10 的时序一致：**剔除逻辑是快照之后才上线的**。

### 4. 半成品行 vs 非半成品行 检验小结

| 分组 | 结论 |
|---|---|
| 半成品行（167 行 / 61 个成品 BOM） | 快照 `绍兴包装成品成本` = 成品 BOM **全额**（59/61 精确相等，2 例为涨价差异）→ **未扣剔除额** |
| 非半成品行（皮壳 2853 / 成品 639 / 空 34） | 代码闸门决定**永不扣**；快照与现库差异（价格涨跌）均与剔除无关 |

## 其它「只减不加」修正

全量 grep（`bom_cost_list_v2.py`、其副本 `key_test/.../bom_cost_list.py`、`order_sync.py`）结果：

| 位置 | 形态 | 是否「只减不加」 |
|---|---|---|
| `bom_cost_list_v2.py:1514` `cost_sxbzcp_val = max(cost_sxbzcp_val - deduction, 0)` | 减法 + 零下限 | **是**（本页主题；唯一一处纯减法修正） |
| `bom_cost_list_v2.py:1518-1524` 自采购特例：`sx_cost_all = cost_fg`（丢弃成品成本） | 分支取值 | 否（是「取其一」，非扣减） |
| `order_sync.py:2941-2945` `-PPCOTTON`：`sx_shipping_cost=0`、`first_freight=0` | 清零 | 否（整体置 0） |
| `order_sync.py:2947/2964/2989` `-COVER`：`valuation_rate=0`（加工成本清零） | 清零 | 否 |
| `order_sync.py:2971-2978 / 2996-3003` `-FOAM`：头程取「成品/半成品头程 − 皮壳头程」 | **差减** | 否（是两列相减求差额，非「修正重复计」，且不作用绍兴成本） |

→ **「只减不加」式的重复计修正，全库仅 `get_sxbzbcp_deduction` 一处**。另 `pllc_cover / pllc_fg` 有「任一项为 0 → 整列置 0」的守卫（`:1571-1577`、`:1582-1583`、`:1602-1603`），属**清零**、非扣减。

## 未证实 / 存疑

1. **现行代码在生产实际报表输出中是否已生效**：只读核实到「commit 已是 `main` 祖先、当前代码该分支成立」；**未实际跑报表**（未 `bench execute`、未取 10-10 之后的 report JSON）产出对比。快照（09-03）已证实**早于**该逻辑。
2. **FBA 仓 × 半成品产品的《绍兴发货成本》会被剔除额间接降低**（经 `sx_cost_all`）：机制在代码上成立（`order_sync.py:2924-2928`），但「绍兴发货方式=半成品的产品是否真的会走 FBA 仓」**未取订单核实**；若会，则属语义可疑（FBA 应按成品成本计）。**建议业务确认是否需把剔除限定在非 FBA 路径。**
3. **1 个成品行（`KS0501-FMYJBHLR-160x85x70…`）的双计未修正**：其成品 BOM 引用了半成品整件但发货方式=成品，闸门 `== "半成品"` 使其**不被剔除** → 该行「绍兴包装成品成本」仍含重复的包装工序/纸箱/袋。是否应修（放宽闸门到「只要成品 BOM 引用了半成品整件就剔除」）**未决**。
4. **`key_test/.../report/bom_cost_list/bom_cost_list.py` 副本是否仍被使用**：同一改动被同步到 `key_test`，但该报表是否还在任何入口产出/被 `order_sync` 读取（`_load_bom_cost_data` 指向哪张报表）**未逐条确认**。
5. **剔除额的财务影响未定量**：只给出「进入哪些列 + 单件公式」；未按订单/数量加权算月度金额（需订单行与发货数量，本次未取）。
6. **`deduct_qty` 是否恒为 1**：样本 KS0495 为 1.0；未全量统计是否存在 ≠1 的成品 BOM（理论上 >1 会放大剔除额）。

## 证据清单（路径:行号 / SQL）

### 代码（EN 生产库 `/home/frappe/frappe-bench/apps/`）

| 位置 | 内容 |
|---|---|
| `work_order_task/work_order_task/work_order_task/report/bom_cost_list_v2/bom_cost_list_v2.py:224-252` | `get_sxbzbcp_deduction()` —— 剔除额定义（operating_cost + 包装子树 items amount） |
| 同上 `:1056-1057` | `pkg_item_groups = 子树(「包装箱」) ∪ 子树(「包装袋」)` |
| 同上 `:1058` | `deduction_cache`（按半成品 BOM 缓存） |
| 同上 `:1500-1515` | 剔除**调用点**：闸门 `== "半成品"` + `deduct_qty` + `max(…-deduction,0)` 覆写 `cost_sxbzcp` |
| 同上 `:1516-1530` | `sx_cost_all`（绍兴总成本）用扣后的 `cost_sxbzcp_val`；含自采购特例 |
| 同上 `:1560-1585` | `pllc_cover`（发皮壳/半成品尾程前成本）：半成品用 `cost_fg+cost_sxbzbcp`（未减） |
| 同上 `:1600-1605` | `pllc_fg = sx_cost_all + 成品运费`（随之被影响） |
| 同上 `:96-120` | `get_default_bom_and_cost()`（`operating+raw_material+scrap`，`:110-115`） |
| 同上 `:135-147` / `:318-353` | `get_item_name_group()` / `get_sxbzbcp_info()`（半成品物品拼装） |
| 同上 `:1265-1267` / `:1629-1631` | 列定义：皮壳成本 / 绍兴包装半成品成本 / 绍兴包装成品成本 |
| `key_test/key_test/key_test/report/bom_cost_list/bom_cost_list.py` | 老报表副本，含**同款** `get_sxbzbcp_deduction` |
| `key_test/key_test/search_item_by_item_group_and_name.py:5-20` | `get_item_groups_descendants()`（`WITH RECURSIVE` 取子孙物料组） |
| `tongtool_integration/tongtool_integration/sync/order_sync.py:2895-2902` | 回写 `cost_fg / cost_sxbzbcp / cost_sxbzcp / sx_cost_all` |
| 同上 `:2919-2931` | `is_fba_warehouse` 分支（`sx_shipping_cost = sx_cost_all`） |
| 同上 `:2932-3013` | 非 FBA 三档；**半成品** `cost_sum = cost_fg + cost_sxbzbcp`（`:3005-3010`） |
| 同上 `:2193-2242` / `:2852-2860` | `_get_warehouse_cost_config()` + 报表列名 → fieldname 映射 |

### Git（app 仓库）

- `work_order_task`: `git log -1 533ecad`（hash `533ecad961c864f3ecdf3d21ad7fc8e7ea78b84e`，2026-10-10 14:35:29 +0800，Jack-wq-ops，+49）；`git merge-base --is-ancestor 533ecad HEAD` = YES；HEAD = `e667558`。
- `key_test`: `git log -1 cf0bbbd`（hash `cf0bbbd611318ea66e6563375b3ddca16e05defc`，2026-10-10 14:36:24，Jack-wq-ops，+49）；ancestor of HEAD = YES。
- `git log --all -S 'sxbzbcp_deduction' -S '剔除' -S 'deduction'`：仅上述两笔（`tongtool_integration` 零命中）。

### SQL（均为只读 SELECT，落服务器 `/tmp`）

- **BOM 成本** —— `SELECT name,item,is_active,is_default,docstatus,total_cost,operating_cost,raw_material_cost,scrap_material_cost FROM tabBOM WHERE name IN (…)`。
- **BOM 子件含物料组** —— `SELECT bi.item_code,bi.qty,bi.amount,i.item_group FROM \`tabBOM Item\` bi JOIN tabItem i ON i.name=bi.item_code WHERE bi.parent IN (…)`（KS0495：成品 BOM 含 `SXBZBCP#KS0495-143x84x88 ×1 @337.041`；半成品 BOM 含 内包装纸箱 12.0 / 外包装纸箱 0.484 / 真空袋 2.19 / PO袋 0.9）。
- **包装子树** —— `SELECT name,parent_item_group,is_group FROM \`tabItem Group\` WHERE name LIKE '%纸箱%' OR name LIKE '%袋%' OR name IN ('包装箱','包装袋')`。
- **成品 BOM 是否引用半成品整件** —— `SELECT DISTINCT parent FROM \`tabBOM Item\` WHERE parent IN (370 个成品 BOM) AND item_code LIKE 'SXBZBCP#%'` → 62 个（半成品 61 + 成品 1）。
- **370 个成品 BOM 的现库 total_cost** —— 与快照 col14 逐一对拍（136 相等 / 182 涨 / 52 降；半成品组 59 相等 / 2 涨）。

### 快照文件

- `tongtool_order_cost/out/profitability_audit/2026年7月订单_ustx2/en_bom_cost/EN产品BOM成本列表20260202.csv`（3693 行；0 基列 3=`绍兴发货方式`、11=`皮壳成本`、12=`绍兴包装半成品成本`、13=`绍兴包装成品成本`、14=`绍兴总成本`、10=`绍兴包装成品, BOM`、7=`绍兴包装半成品, BOM`）。
