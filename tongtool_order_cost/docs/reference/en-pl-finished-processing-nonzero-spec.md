---
okf: v0.1
type: Reference
title: EN 波兰 PL「发货方式=成品」却带非零加工成本的 16 个物料调查（15 启用 + 1 停用）
description: 只读调查 ERPNext 生产库中 16 个「绍兴发货方式=成品」但 PLBZCP# 加工成本非零的物料：逐条清单、非零值来源（手工 valuation_rate vs BOM total_cost）、根因（2025-02-21 建料批次的手工初值未被 BOM 回写覆盖）、是否属于 PP棉→海绵 那批、与「成品=0」规则是否矛盾、清零 1463.17 的对账影响复核
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, pl, poland, shipping-method, bom, valuation-rate, erpnext, reference, read-only]
---

# EN 波兰 PL「发货方式=成品」却带非零加工成本的 16 个物料调查

> 数据口径：ERPNext **生产库**（`erpnext.vilavi.cn`，SSH 别名 `阿里云-FZH-ERPNext-frappe`，bench 根 `/home/frappe/frappe-bench`），**全程只读**（只 SELECT；未 INSERT/UPDATE/DELETE，未 migrate / restart / build；临时 SQL 只落服务器 `/tmp`）。
> 相关前作：[en-shaoxing-ship-method-taxonomy-spec.md](en-shaoxing-ship-method-taxonomy-spec.md)（发货方式取值域、「成品→0」核实）、[en-ustx-no-bom-items-spec.md](en-ustx-no-bom-items-spec.md)（无 BOM 物料画像、BOM→Item 回写链路）、[ustx-cost-caliber-note.md](ustx-cost-caliber-note.md)（口径变更）。

## 结论摘要

1. **16 个物料不是一个成因，是两类，只是恰好都落在「成品」桶里、且都非零**：
   - **15 个（全部启用）**：`PLBZCP#` 物料**任何 docstatus 下都没有 BOM**，非零值来自**人工填入的 `Item.valuation_rate`**（有 `tabVersion` 逐条留痕）。
   - **1 个（`PLBZCP#KS0524-140`，已停用）**：非零 = 其自身「active+default」BOM 的 `total_cost`（158.5308615），由 2026-03-31 的**自动复制**产生，**不是**手工值。
2. **15 个的根因是「建料时的手工初值，后来一直没被 BOM 回写覆盖」**。2025-02-21 PL 侧一次性建了 **274** 个物料，其中 **91** 个当天被手工写入了非零 `valuation_rate`；这 91 个里 **60 个**后来拿到了「active+default」BOM → 被 `key_test` 的 BOM→Item 回写覆盖（PL 侧 **261/261** 个有默认 BOM 的物料，`valuation_rate` 与 `total_cost` **逐位相等**）；**剩下 31 个**没拿到 BOM → 手工值**原样留存**。这 31 个 = 15 个成品（**1463.170**）+ 14 个皮壳（**1364.870**）+ 2 个发货方式为空/NULL（**127.640**）。
3. **不是「三角等填充物 PP棉→海绵」那一批**。16 个里只有 `KS0524`（三角靠枕(碎海绵款)）属于换海绵家族；其余 15 个是互不相关的产品线（懒人沙发/猫吊床/宠物爬梯/便携椅包/圆形坐垫…），且其中 13 个的绍兴对应物料**连 BOM 都没有**、2 个有但**不含 PP棉**。
4. **确实与「成品=0」规则矛盾，但矛盾性质是「陈旧遗留」而非「多算了加工费」**：这些物料在 EN 里**零引用**（无库存/采购/工单/销售/领料/BOM 子件），也没有任何「国外加工工序」的凭证；尤其是 15 个连 BOM 都没有，PL 侧根本没有任何加工动作。它们的值**不可能**是算出来的加工成本。
5. **对账影响复核：1463.17 精确成立**（= 15 个启用项 `valuation_rate` 之和，逐项列示可加）。影响的是 EN 报告 `bom_cost_list_v2` 的列**「波兰加工成本-PL」**（`pl_valuation_rate`）→ `destination_processing_cost` → **「皮壳尾程前成本」（`pllc_cover`）**；**不影响「绍兴总成本」**（`cost_sxbzbcp` / `cost_fg` 与 PL 物料无关）。⚠️ 但按**行**看，非半成品路径在 `destination_processing_cost == 0` 时会把**整行 `pllc_cover` 置 0**（`bom_cost_list_v2.py:1582-1583`），所以按订单加权的实际差异 **≠ 1463.17**（可能更大）——需 PL 订单行才能算（本次未取，见「未证实」）。
6. **USTX/USNJ 的 `KS0524-140` 与 PL 的 `KS0524-140` 同因，与 PL 的另外 15 个不同因**：三家都是 2026-03-31 从**同一张 PP棉 版绍兴 BOM** 复制出来的各自分公司 BOM，值差异只来自各自工资/单价；三家均 `disabled=1`，且绍兴侧 2026-05-16 换成海绵版后**都没再复制** → 三家都是**陈旧值**。

## 16 个物料的逐条清单

判定口径：`PLBZCP#` 物料 → 抽 KS 号 → 找 `Item Group{custom_model_id=KS}` → 读 `custom_shipment_type_to_branch`；筛出 `= 成品` 且 `valuation_rate ≠ 0`。得到 **16 个**，合计 **1621.700861**；其中 **15 个启用**（`disabled=0`），合计 **1463.170000**。

| # | PLBZCP# 物料 | 对应 SXBZCP# | KS 号 | KS 物料组 | 发货方式 | disabled | is_stock_item | valuation_rate | PL BOM 张数 | 其中 active+default | BOM total_cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `PLBZCP#KS0109-170` | `SXBZCP#KS0109-170` | KS0109 | 翻片懒人沙发 | 成品 | 0 | 1 | 222.240000 | 0 | 0 | — |
| 2 | `PLBZCP#KS0524-140` | `SXBZCP#KS0524-140` | KS0524 | 三角靠枕(碎海绵款) | 成品 | **1** | 1 | 158.530861 | 1 | **1** | **158.530861** |
| 3 | `PLBZCP#KS0201-180` | `SXBZCP#KS0201-180` | KS0201 | 可调长度双面床头靠枕 | 成品 | 0 | 1 | 141.470000 | 0 | 0 | — |
| 4 | `PLBZCP#KS0152-140` | `SXBZCP#KS0152-140` | KS0152 | 胸腹部术后枕 | 成品 | 0 | 1 | 111.930000 | 0 | 0 | — |
| 5 | `PLBZCP#KS0108-50` | `SXBZCP#KS0108-50` | KS0108 | 猫吊床 | 成品 | 0 | 1 | 109.270000 | 0 | 0 | — |
| 6 | `PLBZCP#KS0143-165` | `SXBZCP#KS0143-165` | KS0143 | 多功能阅读枕 | 成品 | 0 | 1 | 109.110000 | 0 | 0 | — |
| 7 | `PLBZCP#KS0302-95` | `SXBZCP#KS0302-95` | KS0302 | good靠枕 | 成品 | 0 | 1 | 107.600000 | 0 | 0 | — |
| 8 | `PLBZCP#KS0147-80` | `SXBZCP#KS0147-80` | KS0147 | 多功能倚靠枕 | 成品 | 0 | 1 | 102.870000 | 0 | 0 | — |
| 9 | `PLBZCP#KS0103-67` | `SXBZCP#KS0103-67` | KS0103 | 护颈枕 | 成品 | 0 | 1 | 90.150000 | 0 | 0 | — |
| 10 | `PLBZCP#KS0230-60` | `SXBZCP#KS0230-60` | KS0230 | 侧睡两用楔形枕 | 成品 | 0 | 1 | 85.050000 | 0 | 0 | — |
| 11 | `PLBZCP#KS0102-55` | `SXBZCP#KS0102-55` | KS0102 | 骨头枕 | 成品 | 0 | 1 | 79.400000 | 0 | 0 | — |
| 12 | `PLBZCP#KS0010` | `SXBZCP#KS0010` | KS0010 | 圆形坐垫 | 成品 | 0 | 1 | 78.100000 | 0 | 0 | — |
| 13 | `PLBZCP#KS0113-70` | `SXBZCP#KS0113-70` | KS0113 | 半圆宠物爬梯 | 成品 | 0 | 1 | 64.030000 | 0 | 0 | — |
| 14 | `PLBZCP#KS0111-53` | `SXBZCP#KS0111-53` | KS0111 | 异形沙包坐墩 | 成品 | 0 | 1 | 56.560000 | 0 | 0 | — |
| 15 | `PLBZCP#KS0307-26` | `SXBZCP#KS0307-26` | KS0307 | 绑带款膝盖腿枕 | 成品 | 0 | 1 | 53.430000 | 0 | 0 | — |
| 16 | `PLBZCP#KS0170-45` | `SXBZCP#KS0170-45` | KS0170 | 便携椅包 | 成品 | 0 | 1 | 51.960000 | 0 | 0 | — |

- **合计（16 个）= 1621.700861**；**启用 15 个 = 1463.170000**；差值 158.530861 = `KS0524-140`。
- 16 个的 `PLBZCP#` 物料名去掉前缀 `PLBZCP#` 后与绍兴对应物料名**逐字相同**，且 16 个绍兴对应物料**全部存在**。
- 16 个的 `is_stock_item` 全为 1；`item_group` 都是 `波兰PL包装成品#<KS 组名>`（如 `波兰PL包装成品#三角靠枕(碎海绵款)`）。
- `PLBZCP#KS0010` 是**模板**（`has_variants=1` / `variant_of=NULL`），其余 15 个是**变体**（`variant_of=PLBZCP#KSxxxx`）。
- 16 个的 `Item Group.custom_shipment_type_to_branch` 全部读作 **成品**（KS 组上的字段，见证据 E2）。

## 非零值的来源

### 15 个启用项 —— 人工 `Item.valuation_rate`（无 BOM）

- **`tabBOM` 里没有任何一张 BOM**（`item LIKE` 命中 0 行，含草稿/已取消；`tabDeleted Document` 也无删除痕迹）。所以不可能是 BOM `total_cost`。
- `tabVersion` 逐条留痕（证据 E4），例如 `PLBZCP#KS0102-55`：

  ```
  2025-02-21 17:44:47  by liugaoqing26@dingtalk.com
      changed: [["valuation_rate", 0.0, "人民币 79.40"], ["weight_uom", "克", ""]]
  ```

  即：**从 0 改成一个币种值**（`人民币 79.40` 是 Frappe 对 Currency 字段的格式化显示），同一笔还把 `weight_uom` 由「克」清空。15 个的首笔写入**全部发生在 2025-02-21 17:06–18:26**，操作人 **`liugaoqing26@dingtalk.com`**。
- 随后 `wangzhongyu9295@dingtalk.com` 在 **2025-05-19 ~ 2025-06-04** 之间多次改动（有的先归 0 再重设），**当前值全部定于 2025-06-04（或 06-03）**。例：`PLBZCP#KS0152-140`：`59.42`（02-21）→ `0`（05-19）→ `111.93`（06-04）。
- 全部 `data_import = null`（**不是** Data Import 工具），形态是**逐条表单编辑**。

### 1 个停用项 `PLBZCP#KS0524-140` —— BOM `total_cost`

- 该物料有且仅有 1 张 BOM：`BOM-PLBZCP#KS0524-140-001`，`docstatus=1 / is_active=1 / is_default=1`，`total_cost = 158.530861500`，创建于 **2026-03-31 18:12:33**，owner `wangzhongyu9295@dingtalk.com`。
- `Item.valuation_rate = 158.530861` 与 `total_cost` **逐位相等** → 是 BOM→Item 回写的结果（`tabVersion` 同秒记录 `0.0 → ¥ 158.531`）。
- 该 BOM 只有 **1 行物料**：`PPM1500-15D64-SILICONIZED-NEW × 4.2 @10.8`（**PP棉**，`item_group LIKE 'PP棉%'` 计数 = 1）——即「绍兴 BOM 复制 → 只保留 PP棉 行」的标准产物。

## 画像与品类

### 是什么（品类）

16 个覆盖 **16 个互不相同的 KS 产品线**：翻片懒人沙发、三角靠枕(碎海绵款)、可调长度双面床头靠枕、胸腹部术后枕、猫吊床、多功能阅读枕、good靠枕、多功能倚靠枕、护颈枕、侧睡两用楔形枕、骨头枕、圆形坐垫、半圆宠物爬梯、异形沙包坐墩、绑带款膝盖腿枕、便携椅包。

**共同点：它们都不是「三角/平条/圆滚」这类核心 PP棉 靠枕产线**，而是宠物用品 / 医疗康复枕 / 沙发坐垫 / 包袋这类**边缘品线**——形态上更像「绍兴直接采购成品后发给分公司」的款。这与「发货方式=成品」相符。

### 引用面（Q3）

对 16 个物料逐表统计，**全部为 0**（证据 E5）：

| 引用面 | 行数 |
|--------|------|
| `tabBin`（库存） | 0 |
| `tabStock Ledger Entry` | 0 |
| `tabPurchase Order Item` / `tabPurchase Receipt Item` | 0 / 0 |
| `tabWork Order`（`production_item`） | 0 |
| `tabSales Order Item` / `tabDelivery Note Item` | 0 / 0 |
| `tabStock Entry Detail`（领料/入库） | 0 |
| `tabBOM Item`（作为组件） | 0 |
| `tabProduct Bundle`（成品包装/组合） | 0 |
| `tabItem Customer Detail` | 0 |

补充（放大量级后仍是 0）：**整个 `PLBZCP#%` 前缀**（772 个物料）在 Bin / SLE / PO / WO / SO / DN / Stock Entry 上**也是 0 行**；`USTXBZCP#%`、`USNJBZCP#%` 同样 0。`SXBZCP#%` 只有 1 行 Bin 且 `actual_qty=0`。
→ **EN 对这些海外包装成品只做「物料主数据」，不做库存/采购/生产/销售**。所以「有没有单据佐证这些是加工件」这个问题在 EN 里查不到（本来就无单据），结论只能是「无任何加工痕迹」。

### 创建时间

- **15 个启用项**：全部 **2025-02-21 17:06:33 ~ 18:26:02**（同一批，同一天建成，owner `liugaoqing26@dingtalk.com`）。
- **1 个停用项**：`PLBZCP#KS0524-140` 建于 **2026-01-12 09:14:01**（owner `ch3-70i0lr3f2@dingtalk.com`），晚于另一批 11 个月。

### 是不是「三角等填充物 PP棉 改成海绵」那一批

**不是（16 个里只有 1 个沾边）**：

- 只有 **`KS0524`（三角靠枕(碎海绵款)）**属于换海绵家族。它的绍兴侧确实发生了 PP棉→海绵：`BOM-SXBZCP#KS0524-140-001`（2026-03-31，含 PP棉，`is_default=0`）→ `BOM-SXBZCP#KS0524-140-002`（2026-05-16，含海绵 `TCWSHM3030-MEDIUMDENSITY-WHITE`，`is_default=1`）。
- 其余 15 个与换填充物**无关**，且没有换料的痕迹可查：**13 个的绍兴对应物料连一张 BOM 都没有**；剩下 2 个（`KS0230-60`、`KS0524-140`）里，`KS0230-60` 的绍兴默认 BOM **PP棉 行数 = 0**（只有海绵 `HM1510-YD1+YD4-…` + 纸箱/袋）。
- **反而是这个「无 PP棉」事实解释了为什么这 15 个没有 PL BOM**：自动复制有硬闸门 `check_pp_cotton_in_bom_items`（`utils/bom.py:381`），源 BOM 没有 `item_group='PP棉'` 的行就直接早退 → 不复制 → `Item.valuation_rate` 保持手工值。

### 根因（15 个）：建料批次手工初值 + 未获 BOM 覆盖

对 2025-02-21 当天建的那 **274** 个 PL 物料做拆解（当天有非零 `valuation_rate` 的共 **91** 个）：

| 发货方式 | 是否已有 active+default BOM | 个数 | 非零 `valuation_rate` 合计 |
|----------|------------------------------|------|---------------------------|
| 半成品 | 是 | 11 | 1220.243 |
| 皮壳 | 是 | 49 | 7628.400 |
| **皮壳** | **否** | **14** | **1364.870** |
| **成品** | **否** | **15** | **1463.170** |
| 空/NULL | 否 | 2 | 127.640 |

**60 个「已有 BOM」的被回写覆盖，31 个「没有 BOM」的原样留存。**
支撑这条因果链的两条硬数据：

1. PL 侧**所有**有 active+default BOM 的物料（**261/261**，含 KS0524-140）`valuation_rate` 与 BOM `total_cost` **逐位相等，0 例外** —— 证明回写确实生效且必然覆盖手工值。
2. 31 个留存项**全部没有** active+default BOM —— 回写任务（只扫 `is_active=1, is_default=1, docstatus=1`）覆盖不到。

### 为什么这 15 个「该有 BOM 却没有」

按业务规则，发货方式=成品 → 国外不该有加工 → **本来就不该有 PL 加工 BOM**。所以「没 BOM」本身**不是缺陷**；缺陷是**建料时手工填的 `valuation_rate` 从来没人清掉**——它是「绍兴侧成品采购价/参考价」的残留，占的是「国外加工成本」这个位置。

## 与「成品=0」规则是否矛盾

**逐条结论：16 个全部矛盾**（发货方式都是`成品`，值都非零），但**矛盾的性质分两类**：

| 分组 | 条数 | 是否真的「无需国外加工」 | 判断依据 |
|------|------|--------------------------|----------|
| 15 个启用项 | 15 | **是**（高度可信） | PL 侧**零 BOM、零引用、零工序**；绍兴对应件 13 个无 BOM、2 个无 PP棉 → 上游根本不具备「复制出加工 BOM」的条件。值只能是手工残值。 |
| `KS0524-140` | 1 | **是**（且已停用） | 它确有 PL 加工 BOM，但那是 2026-03-31 从**旧 PP棉 版**复制来的；绍兴 2026-05-16 已切海绵（`-002`，PP棉 行 0），复制闸门随之中断 → 该 BOM 已成**孤儿陈旧值**；物料 2026-05-20 被停用。 |

**有没有可能是「发货方式填错」？——无法证伪，但旁证支持没填错。**

- 无法证伪的原因：数据模型里「成品」是一个**单一桶**（见前作），没有「是否绍兴自采购 / 是否需海外二次加工」字段，无从机器判定。
- 支持「确是成品」的旁证：这 16 个品线全部是**边缘品线**（宠物床/爬梯、医疗术后枕、懒人沙发、便携椅包…），而 PL 侧 392 个`皮壳`物料里 **198 个**都有 PP棉 加工 BOM —— 若这些边缘款真需 PL 加工，业界形态上应当同样长出一张 PP棉 BOM，但 15 个都没有。
- **无法排除**的残余可能：这 15 个的 `valuation_rate` 也可能被**当作了「国外加工成本」而有意填**（数值区间 51.96~222.24 与真加工 BOM 的成本同量级），若是如此则属口径认知错误而非字段填错。两者**从数据上无法区分**（见「未证实」）。

## 清零的对账影响（复核数字）

### 复核：1463.17 精确成立

15 个启用项逐项相加（= 上表 #1、#3–#16）：

```
222.24 + 141.47 + 111.93 + 109.27 + 109.11 + 107.60 + 102.87 + 90.15
      + 85.05 + 79.40 + 78.10 + 64.03 + 56.56 + 53.43 + 51.96
= 1463.170000
```

含停用项则为 `1463.170000 + 158.530861 = 1621.700861`。**与用户给的 1463.17 / 1621.70 完全一致。**

### 影响的是哪一项口径

代码链路（EN 生产库 `apps/work_order_task/.../bom_cost_list_v2/bom_cost_list_v2.py`）：

| 位置 | 内容 |
|------|------|
| `:541-566` | `get_item_valuation_rate(item_code)` —— 优先取「active+default」BOM 的 `total_cost`，否则回退 `Item.valuation_rate`；同时返回 `is_disabled` |
| `:503-538` | `get_plbzcp_info(item)` —— 行物料 → `波兰PL包装成品#{item_group}` → `custom_model_id`（实测 = `PLBZCP#KS0001`）→ `item_plbzcp = f"{custom_model_id}-{size}"` = **`PLBZCP#KS0001-100`** |
| `:1177` | `pl_valuation_rate = rate if not is_disabled else None` —— **停用项直接置 None** |
| `:1282` / `:1637` | 列定义：**「波兰加工成本-PL」**（fieldname `pl_valuation_rate`） |
| `:1558` | `destination_processing_cost = row["pl_valuation_rate"]`（当 price_list 含 `PL`） |
| `:1569` / `:1580` | `pllc_cover = cost_fg + [cover_freight/sfg_freight] + destination_processing_cost` —— 即**「皮壳尾程前成本」** |
| `:1582-1583` | 非半成品路径守卫：`if cost_fg == 0 or cover_freight == 0 or destination_processing_cost == 0: pllc_cover = 0` |

**结论**：
1. 清零这 15 个 → `pl_valuation_rate`（列「波兰加工成本-PL」）在这 15 项上由「51.96~222.24」变为 **0**，**合计少 1463.17**（单位成本之和）。
2. 它汇入的是 **`pllc_cover`（皮壳尾程前成本）**，**不是**「绍兴总成本」——`cost_sxbzbcp` / `cost_fg` 取自绍兴侧物料，与 `PLBZCP#` 无关，`Δ = 0`。
3. ⚠️ **按行看，实际影响不是简单的 −1463.17**：`:1582` 的守卫规定「`destination_processing_cost == 0` → 整行 `pllc_cover` 归零」。所以某行一旦清零，损失的是该行 **(`cost_fg` + `cover_freight` + 加工成本)** 的**全部**，而非仅加工成本那一项。**要给出按订单加权的金额，必须有 PL 侧的订单行**（本次未取，见「未证实」）。
4. `PLBZCP#KS0524-140`（158.530861）**本来就已被 `:1177` 置 None**（`disabled=1`），故**不在任何对账口径里**——清零它不产生额外影响。

### PL 侧分发货方式合计（report 口径，供对照）

按 `get_item_valuation_rate` 口径（BOM 优先、`disabled` 置 None）统计 `PLBZCP#` 全部 772 个物料：

| 发货方式 | 物料数 | 有 active+default BOM | 非零项数 | 值合计 |
|----------|--------|------------------------|----------|--------|
| 皮壳 | 392 | 198 | 216 | 46835.820096 |
| **成品** | **233** | **1** | **16 → 生效 15** | **1621.700861（生效 1463.170000）** |
| 半成品 | 125 | 62 | 62 | 8854.081410 |
| 空串 | 12 | 0 | 0 | 0 |
| NULL | 10 | 0 | 2 | 127.640000 |

**可对照**：`半成品` 的 62 个非零**全部**来自 BOM（无一个手工残值）——即「有加工才有成本」；`成品` 恰好相反，**唯一一个有 BOM 的还已停用**，生效的全是手工残值。这也从侧面证实「成品→0」在当前数据上是**被违反**的。

**附带发现（同类异常）**：`皮壳` 里也有 **18 个**「无 BOM 却非零」的手工残值，合计 **1707.801**（`KS0004-100/-54`、`KS0005-145`、`KS0018-SET7`、`KS0019`、`KS0021`、`KS0106-45`、`KS0107-240`、`KS0115-45`、`KS0122-100`、`KS0139-72`、`KS0146-60`、`KS0158-61`、`KS0159-34`、`KS0168`/`KS0168-74`、`KS0251-SET6`、`KS0529-45x45=0.001`）。**与 15 个成品同根同因**（同属 2025-02-21 建料批次），只是发货方式不是成品、不在本次「成品=0」的适用范围。

## 未证实 / 存疑

1. **15 个手工值的业务含义未证实。** 已确认「是人工表单编辑」（`tabVersion` 留痕、`data_import=null`），但**当时为什么填**未证实——可能是「绍兴成品采购价/参考价」，也可能是「误当国外加工成本填」。两者从数据上不可区分（无字段、无单据、无备注）。数值区间（51.96~222.24）与真实 PL 加工 BOM 成本同量级，是歧义的主因。
2. **「发货方式=成品」字段是否被填错未证实。** 前作已指出数据模型层面**无字段**区分「绍兴自采购成品 / 绍兴不用加工 / 绍兴仍需加工后发成品」，「成品」是单一桶。本次只能给出「品类形态像自采购成品」这一旁证，**无法证伪**。
3. **按订单加权的实际对账差异金额未算。** 本次只复核了「单位成本之和 = 1463.17」；`pllc_cover` 的整行守卫（`:1582`）意味着实际差异可能大于 1463.17。**未取 PL 侧订单行**（仓库/账期数据不在本次范围内）。
4. **15 个里没有 BOM 的「应有 BOM 吗」未验证。** 按规则「成品不应有 PL 加工 BOM」，所以「无 BOM」应属正常；但本次**未逐条比对绍兴对应款是否本该有 PP棉 填充工序**（13 个绍兴无 BOM，另 2 个无 PP棉）——若某款实际在绍兴做了填充再发，则它是「半成品」而非「成品」，字段应为半成品（无法证伪，同第 2 条）。
5. **2026-10-15 13:30:38 有一次 `Item Group` 批量 `modified` 刷新未解释。** 全库 **311** 个 `Item Group` 的 `modified` 被写在同一秒内，但 `tabVersion` 中 `Item Group` **当天零记录**（说明不是 `doc.save()`，更像 `frappe.db.set_value` 或补丁脚本）。**关键：字段值未变**——本次快照与今早前作快照 `ks_ig.tsv` 逐行比对 **401/401 完全一致**（`成品` 计数同为 165）。故不影响本报告结论，但**成因未查**。
6. **PL 皮壳侧 18 个同类残值（1707.801）未逐个展开**（本次只列名单与合计），其逐条清单/字段来源未验证。
7. **`KS0524-140` 的「三家为何值不同」只做了机理归因**（各自 BOM 的工资/单价不同），**未逐项拆解** raw_material_cost 与 operating_cost 的构成。
8. **本报告未核对 `PLBZCP#KS0010` 作为模板（`has_variants=1`）是否有变体继承其 `valuation_rate`**（`key_test/update_variant_valuation_rate.py` 的模板→变体传播），仅列出该形态差异。

## 证据清单

### 代码（EN 生产库 `/home/frappe/frappe-bench/apps/`）

| 位置 | 内容 |
|------|------|
| `work_order_task/.../report/bom_cost_list_v2/bom_cost_list_v2.py:541-566` | `get_item_valuation_rate()` —— BOM(active+default) `total_cost` 优先，回退 `Item.valuation_rate`；返回 `is_disabled` |
| 同上 `:503-538` | `get_plbzcp_info()` —— `波兰PL包装成品#{item_group}` → `custom_model_id` → `item_plbzcp = "{custom_model_id}-{size}"` |
| 同上 `:1169-1182` | 组4「波兰PL包装成品组」：`pl_valuation_rate = rate if not is_disabled else None`（`:1177`） |
| 同上 `:1282` / `:1637` | 列「波兰加工成本-PL」(`pl_valuation_rate`) |
| 同上 `:1551-1583` | `destination_processing_cost` 按 price_list 取 USNJ/USTX/PL；`pllc_cover` 计算 + `:1582-1583` 整行守卫 |
| `work_order_task/.../utils/bom.py:25-29` | 前缀映射（`波兰PL包装成品# → PLBZCP#` 等三种「包装成品」） |
| 同上 `:316` / `:381` | `auto_copy_bom_for_sxbzcp_on_submit()` / `check_pp_cotton_in_bom_items()`（PP棉 硬闸门） |
| 同上 `:183-200` | `copy_bom_with_new_item()` 只保留 `item_group='PP棉'` 的行 |
| `key_test/key_test/bom_cost_synchronizer.py:87-119` | `scheduled_sync_all_bom_costs()` —— `BOM(is_active=1,is_default=1,docstatus=1)` → `item_doc.valuation_rate = bom.total_cost` |

### SQL（均为只读；快照落 `tongtool_order_cost/out/pl_probe/`，`out/` 已 gitignore）

- **E1 基础快照**
  - `pl_items.tsv` ← `SELECT name,item_group,disabled,is_stock_item,valuation_rate,variant_of,has_variants,creation,modified,owner FROM tabItem WHERE name LIKE 'PLBZCP#%'` → **772** 行
  - `pl_bom.tsv` ← `... FROM tabBOM WHERE item LIKE 'PLBZCP#%'` → **303** 行
  - `pl_ig.tsv` ← `SELECT name,custom_model_id,custom_shipment_type_to_branch FROM \`tabItem Group\` WHERE custom_model_id LIKE 'KS%'` → **401** 行
  - `sx_items.tsv` / `sx_bom.tsv` ← 同口径 `SXBZCP#%` → 921 / 588 行
- **E2 发货方式分布（PL 物料）** —— `皮壳 392 / 成品 233 / 半成品 125 / 空串 12 / NULL 10`；`custom_model_id` **无重号**（401 个 KS 组一一对应）。
- **E3 16 个的判定** —— 成品 ∩ `valuation_rate≠0` → 16 个，合计 1621.700861；启用 15 个 = 1463.170000（`out/pl_probe/j1.py`、`j2.py`）。
- **E4 `tabVersion` 逐条留痕** —— `SELECT name,docname,owner,creation,data FROM \`tabVersion\` WHERE ref_doctype='Item' AND docname IN (<16>)` → 32 条；15 个启用项的 `valuation_rate` 首笔 `0.0 → 币种值`、`weight_uom: 克 → 空`，owner `liugaoqing26@dingtalk.com`（`out/pl_probe/pl_ver2.tsv`、`j3.py`）。
- **E5 引用面（16 个全 0）** —— `tabBin` / `tabStock Ledger Entry` / `tabPurchase Order Item` / `tabPurchase Receipt Item` / `tabWork Order` / `tabSales Order Item` / `tabDelivery Note Item` / `tabBOM Item` / `tabStock Entry Detail`，`item_code IN (<16>)` → **0 行**（`q_refs.sql`）。
- **E5b 放大量级仍为 0** —— `PLBZCP#%` 在上述各表 **0 行**；`USTXBZCP#%` / `USNJBZCP#%` Bin 亦 0；`SXBZCP#%` Bin 仅 1 行 `actual_qty=0`（`q_ctl2.sql`）。
- **E6 建料批次拆解** —— 2025-02-21 建 PL 物料 **274** 个，其中当天非零 `valuation_rate` **91** 个；按 (发货方式, 有无 active+default BOM) 分桶见正文表（`j6.py`）。
- **E7 BOM 回写一致性** —— PL 侧有 active+default BOM 的物料 `valuation_rate == total_cost` **261/261 逐位相等，0 例外**（`j6.py`）。
- **E8 `KS0524-140` 三家对照** —— `SELECT ... FROM tabItem WHERE name IN (PL/USNJ/USTX 的 KS0524-140...)`：PL `158.5308615` / USNJ `187.038321` / USTX `100.791582`，三家各自等于其自己 BOM 的 `total_cost`，三家 `disabled=1`（`q_3branch.sql`）。
- **E9 `KS0524-140` 的 BOM 树** —— `BOM-SXBZCP#KS0524-140-001`（2026-03-31，含 PP棉，`is_default=0`）→ 同日自动复制出 `BOM-{PL,USNJ,USTX}BZCP#KS0524-140-001`（各 1 行 PP棉，rate 10.8 / 14.8 / 15.0）；`BOM-SXBZCP#KS0524-140-002`（2026-05-16，含海绵，`is_default=1`）后到，海外未再复制（`q_524bom.sql`）。
- **E10 `KS0230-60` 绍兴默认 BOM 无 PP棉** —— `BOM-SXBZCP#KS0230-60-002`（`is_default=1`，`total_cost=62.355`）行内容 = 海绵 `HM1510-YD1+YD4-60x56x30-WHITE` + 内/外纸箱 + 真空袋，**PP棉 行数 = 0**（`q_sxbom2.sql`）。
- **E11 `Item` 无自定义成本字段** —— `SELECT fieldname,fieldtype FROM \`tabCustom Field\` WHERE dt='Item'` 全量列出：只有尺寸/重量类自定义字段，**无任何 cost/加工 字段**；故 `valuation_rate` 是唯一成本载体。
- **E12 无已删 BOM** —— `tabDeleted Document WHERE deleted_name IN (<16>)` → 0 行。
- **E13 2026-10-15 13:30:38 批量 `modified`** —— `SELECT modified,COUNT(*) FROM \`tabItem Group\` WHERE modified>='2026-10-15'` → 311 行同一秒；`tabVersion` 当日 `Item Group` **0 条**（`q_igmod.sql`、`q_igver.sql`）。

### 本地复算脚本（scratch，`out/` 已 gitignore）

- `out/pl_probe/j1.py`（16 个判定）、`j2.py`（16 个逐条 + BOM 明细）、`j3.py`（`tabVersion` 解析）、`j4.py`（PL 分发货方式聚合）、`j5.py`（皮壳同类异常 + 建料批次）、`j6.py`（因果链验证）、`j7.py`（成表）
- `out/pl_probe/cmpig.py`（新快照 vs 前作 `out/ks_ig.tsv` 逐行比对，401/401 一致）
- SQL：`q_refs.sql`、`q_ctl*.sql`、`q_sx_vr.sql`、`q_ver*.sql`、`q_3branch.sql`、`q_524bom.sql`、`q_sxbom2.sql`、`q_itemcf.sql`、`q_names.sql`、`q_plig.sql`、`q_ksns.sql`、`q_igver*.sql`、`q_igmod*.sql`
