---
okf: v0.1
type: Reference
title: 背贴品名缺失怎么补——通途SKU 在 EN 有两种登记写法，且不在 item_languages 里
date: 2026-09-22
category: integration-issues
module: sellfox_shipping
problem_type: integration_issue
component: tooling
severity: medium
applies_when:
  - "背贴 PDF 上某个 SKU 的中/西语品名是空白"
  - "要判断 US SKU Name 表是不是真的缺条目，以及缺的那条该叫什么"
  - "要拿通途SKU 反查 EN 物料（item_languages 里查不到的时候）"
tags: [sku-name, backing-label, erpnext, customer-code, pim-api]
---

# 背贴品名缺失怎么补

## Context

背贴（4×2" 标签）按 SKU 显示**中/西语品名**，查名的键是通途导出里 `Reference 2` 列的**原样字符串**（两侧 `strip().upper()` 后匹配）—— 不是 EN 物料号，也不是基码。

组合件会把这个键变得不规整：一个包裹里的皮壳写成 `TT0031249K0064109-Cover`，海绵写成 `TT0312588K0064183-Foam`（**注意两者的数字段不同族、且尺寸与序号不成顺序**）。只要表里漏一条，标签上那一行品名就是空白。

## Guidance（本学习沉淀的做法）

**1. 先确认「表里到底有没有」——别跳过这步。**
背贴实际查的是 `US SKU Name` 这张 Google Sheet（列：`通途SKU | 中文名称 | 西班牙语名称`），不是 EN。先读表、按 `通途SKU` 大写比对，得到一个明确的「缺哪几条」清单，再决定补什么。

**2. 缺失时去 EN 找，但要知道通途SKU 存在哪儿。**
同一个通途SKU 在 EN 里有**两种写法**，都在 `Item` 的两个地方，**都不在 `item_languages`**：

| 位置 | 形态 | 例 |
|---|---|---|
| `Item.customer_code` | 逗号分隔的字符串 | `删除TT0312588K0064179-Foam,删除TT0312588K0064179` |
| `Item.customer_items[].ref_code` | 子表逐行 | `ref_code = 删除TT0312588K0064179` |

- **带后缀**（`X-Foam`）：通途导出实际使用的形式；
- **不带后缀**（`X`，裸基础码）：EN 里也登记，但导出里**没出现过**。

⇒ **只登记导出里真正出现的那种。** 想确认哪种会出现，就去扫真实导出的 `Reference 2` 列，而不是猜。

**3. `item_languages.tt_sku` 只存成品码。**
床头板类物料里，`item_languages.tt_sku` 存的是 ` ...-Cover` 形式的**成品码**（例如 `KS0397-...` 挂 `TT0031249K0064109-Cover`），海绵件的 `item_languages` 干脆是**空的**。所以「在 EN 里搜通途SKU」不能只查 `item_languages`。

**4. 访问性坑（实测）：**

- `Item Language` 子表**不能 list** —— `GET /api/resource/Item Language?filters=...` 返回 `403 PermissionError`；但**可以**逐个 Item 读（`GET /api/resource/Item/{code}` 里带出 `item_languages`）。
- `Item` 的 `commodity_sku` **不能当过滤字段** —— `Field not permitted in query: commodity_sku`。
- `Item.name` 是**物料编码**（如 `ABML1010-BEIGESE-150-260`），不是通途SKU；`name like %TT...%` 一律空。

**5. PIM API 能一把映射，但必须先做假阳性测试。**

```
POST /api/method/vilavi_pim.api.pim_api.get_sku_item_itemgroup_mapping
body: {"skus": ["TT0312588K0064183-Foam", ...]}
→ results[].item_code / item_name / item_group ；不中则进 not_found
```

它会剥离后缀、按基码回退匹配。**先丢一个不存在的 SKU 进去看它怎么答**：

- 丢 `TT9999999K9999999-Foam` / `ZZZ-NOT-A-REAL-SKU` → 返回 `not_found`、不给结果 ⇒ 不是「乱猜型」，可信；
- 同时横向验一组同族不同尺寸，看映射是否**自洽**（实测 100→100、153→153、160→160、183→183 全对）⇒ 才敢用它的答案。

**6. 尺寸↔SKU 必须逐条读，不能推。**
同一族的序号**不是按尺寸排的**（153 是 `...4183`、160 却是 `...4182`）。从 EN 逐条读 `item_code` 里的尺寸段（`HM1510-YD2-{尺寸}x60x10cmZJ-WHITE`）再落表，不要靠加减。

**7. 判断「这是中性件还是专属件」时，多系统对不上就别硬选。**
本例同一个海绵件：通途叫**直角**、EN PIM 映射到**方格**（KS0396）、而同包裹的皮壳是**菱形**（KS0397）——三个说法互斥，且 EN 里三种款式各自都有独立物料 ⇒ 该件是**跨款式通用的中性件**。结论：写中性名（或按用户认可的通途措辞）比咬着某一个款式名更安全。

## Why This Matters

- 背贴是给**分拣员**看的：品名空白 = 只能靠 SKU 号认货，拣错的概率上升。
- 补错比不补更糟：写上一个**错误的款式**（直角/方格/菱形），会让拣货员拿着标签去找不属于这个包裹的件。
- 「导出里出现的是带后缀还是裸码」直接决定要不要多写一倍的行 —— 扫一眼真实导出就能省掉。

## When to Apply

- 背贴合成了、但某行品名是空白（流水线一般会有「背贴缺名」的报告行，先看它）。
- 要给 `US SKU Name` 表批量补条目 —— 从 EN 侧一次性取全尺寸，按尺寸紧挨着对应的皮壳行插入，便于维护。
- 任何「通途SKU → EN 物料」的反查（`item_languages` 查不到时，改走 `customer_code` / `customer_items.ref_code`）。

## Examples

一次真实补齐（直角床头板海绵 8 个尺寸）：

1. 对账：表里 8 条只命中 1 条 ⇒ 缺 7 条；
2. 从 EN 的 8 个 `HM1510-YD2-{尺寸}x60x10cmZJ-WHITE` 读 `customer_code`，剥掉 `删除` 前缀得到 8 个 `-Foam` SKU 与尺寸的对应；
3. 落表：中文名 `直角床头板(海绵) {尺寸}*60*10cm`、西班牙语 `Cabecero rectangular (espuma) {尺寸}x60x10cm`，每行紧跟同尺寸的皮壳行（表 926 → 933 行）；
4. 复测：模拟查名逻辑（`Reference 2` 大写后 merge）⇒ 8 条全部命中、缺名数 0。

## 参考

- `conventions/tongtu-en-sellfox-instock-sku-mainline.md` —— 同族结论：`-Cover/-Foam` 的**基码匹配 ≠ 完整登记**，完整登记要看 EN 的 `customer_items`
- `sellfox_shipping/sku_label/name_lookup.py` —— 仓库内已迁移的查名实现（走 `item_languages`）
- `docs/solutions/architecture-patterns/sku-label-pdf-generation-and-name-lookup.md` —— 背贴 PDF 与查名的架构说明
- 同批学习：`integration-issues/carrier-label-batch-field-length-limits.md`
