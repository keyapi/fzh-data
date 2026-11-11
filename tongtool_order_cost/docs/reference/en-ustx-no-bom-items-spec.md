---
okf: v0.1
type: Reference
title: EN 美中 USTX 无 BOM 物料画像 · 309 张 BOM 来源 · PP棉→海绵 对自动复制的影响
description: 只读调查 ERPNext 生产库中 Google Sheet 引用但无 BOM 的 96 个 USTXBZCP# 物料：它们是什么、现有 309 张 BOM 从哪来、能否补齐，以及绍兴侧填充物 PP棉→海绵 会如何影响自动复制链路
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, ustx, bom, erpnext, pp-cotton, sponge, reference, read-only]
---

# EN 美中 USTX 无 BOM 物料画像 · 309 张 BOM 来源 · PP棉→海绵 影响

> 数据口径：ERPNext **生产库**（`erpnext.vilavi.cn`，`erpnext 15.43.3` / `frappe 15.48.0`），**全程只读**（只 SELECT；未创建 / 修改 / 删除任何记录；未 migrate / restart / build；临时文件只落服务器 `/tmp`）。
> 输入清单：`tongtool_order_cost/out/ustx_wage_sim/sheet_ustx_items.csv`（`bom_status=NO_BOM` 的 96 行）。
> 相关前作：[en-ustx-bom-wage-rate-spec.md](en-ustx-bom-wage-rate-spec.md)（工资率链路）、[ustx-cost-caliber-note.md](ustx-cost-caliber-note.md)（口径变更）。

## 结论摘要

1. **96 个不是「建了又删」，而是「没走到建 BOM 那一步」。** 10 个 `USTXBZCP#` 物料压根不存在；其余 86 个存在但在 EN 里**零引用**（无库存、无采购、无工单、无销售、无 BOM）。主因是**绍兴对应变体本身没有 BOM**（52 个）或**绍兴 BOM 里没有 PP棉 行**（36 个，自动复制的硬闸门）。只有 1 个有「删过 Item 再重建」的痕迹。
2. **89 个 `valuation_rate` 为 0**（79 个存在且为 0 + 10 个不存在）。原因是 `valuation_rate` 由 `key_test` 的每日任务从「激活+默认 BOM 的 total_cost」回写；**没有 BOM 就没有回写**，而这些物料又没有任何库存/采购，ERPNext 自身也推不出估价。剩余 **7 个非零**值查不到自动来源（见「未证实」）。
3. **309 张 USTX BOM 高度聚集在 2025-10（190 张，61.5%）**，尾部延续到 2025-11（46）、2025-12（29）、2026-01（25），此后零散到 2026-09。这是一次**历史批量回填**，不是逐日自然产生。
4. **不能靠现有自动复制补齐这 96 个。** 卡在 `check_pp_cotton_in_bom_items` 闸门：**36 个绍兴对应 BOM（已提交+默认+启用）的 PP棉 行数全部 = 0**，`auto_copy_bom_for_sxbzcp_on_submit` 会直接早退。即使绕过闸门，`copy_bom_with_new_item` 只保留 `item_group='PP棉'` 的行，结果会是一张**物料行为 0 的空 BOM**。
5. **PP棉→海绵：自动/批量路径会「静默不复制」（安全但停更）；表单按钮路径没有这道闸门，反而会生成空物料 BOM 并抢占默认（危险）。**
6. **可以显式地从某张指定的旧绍兴 BOM 复制。** 白名单函数 `copy_bom_for_supporting_items(bom_name, selected_prefixes)` 接受**任意** BOM 名；前端按钮传的就是 `frm.doc.name`（当前打开的那张）。批量路径则**不行**——它只挑「最新 + 已提交 + 默认 + 启用」那张。旧的（非默认 / 已取消）BOM 只要没被物理删除，就一直留在 `tabBOM` 里可作参考源。

## 96 个无 BOM 物料的画像

清单来源：`out/ustx_wage_sim/sheet_ustx_items.csv`（`bom_status=NO_BOM`，96 行）；并与 `tabItem` / `tabBOM` 全量快照做连接。

### 是否存在、是否启用

| 维度 | 数量 | 说明 |
|------|------|------|
| `USTXBZCP#` Item 存在 | 86 | 全部是**变体**（`variant_of` 非空），没有模板 |
| `USTXBZCP#` Item 不存在 | 10 | sheet 引用了根本没建的编号 |
| 其中 `disabled=1` | 3 | `KS0524-100` / `KS0524-153` / `KS0524-194` |
| 绍兴对应物料 `SXBZCP#X` 存在 | 89 | |
| 绍兴对应物料不存在 | 7 | |

### 是否在使用中（**全部为 0**）

对这 96 个物料代码逐表统计（SQL 见证据清单 E1）：

| 引用面 | 行数 |
|--------|-----|
| `tabBin` 非零库存 | 0 |
| `tabStock Ledger Entry`（任意凭证类型） | 0 |
| `tabPurchase Order Item` | 0 |
| `tabPurchase Receipt Item` | 0 |
| `tabWork Order`（`production_item`） | 0 |
| `tabSales Order Item` | 0 |
| `tabDelivery Note Item` | 0 |
| `tabBOM Item`（作为组件） | 0 |
| `tabBOM`（作为产品） | 0 |
| `tabProduct Bundle` / `tabProduct Bundle Item` | 0 |
| `tabItem Customer Detail` | 0 |

结论：**这 96 个是「登记了但从未被任何业务单据引用」的空壳物料**，既不产、不采、不销、不存。

### 有没有共同特征

- **无时间聚集**：创建月份分散在 2025-02(12) / 2025-05(13) / 2025-07(15) / 2025-08(7) / 2025-09(9) / 2025-10(4) / 2025-11(5) / 2025-12(2) / 2026-01(3) / 2026-02(3) / 2026-03(2) / 2026-04(3) / 2026-06(2) / 2026-08(4)。贯穿全年，不像 309 张 BOM 那样是个批次。
- **无品类聚集**：横跨印花石头抱枕、泰迪熊、床上用品印花套装、圆滚靠枕、弧形海绵靠枕、狗狗出行辅助带、方形抱枕…… 都是**零散规格**（如 `-45x45`、`-60x48x40`、`-102x160x90` 这类尺寸型 SKU）。
- **不是「建了又删」**：`tabDeleted Document` 里只有 **1 条** 命中（`USTXBZCP#KS0489-100x90x8`，2025-08-22 由 `Administrator` 删除，且该物料**现在又存在**）。其余 95 个从没被删过。
- **家族层面看，是「整个家族没建」而非「漏了一个规格」**：96 个里只有 **9 个**在同一 `variant_of` 家族里能找到已建 BOM 的兄弟；**77 个**所在家族在 USTX 侧一张 BOM 都没有。

### `Item.valuation_rate` 从哪来 / 为什么 89 个是 0

**回写机制（已定位）**：

```
key_test/hooks.py:233-235   BOM.on_update / on_update_after_submit
                              → key_test.bom_cost_synchronizer.sync_bom_cost_to_item
key_test/hooks.py:249-251   cron "0 3 * * *"
                              → key_test.bom_cost_synchronizer.scheduled_sync_all_bom_costs
key_test/bom_cost_synchronizer.py:87-119
    boms = BOM(is_active=1, is_default=1, docstatus=1)
    item_doc.valuation_rate = bom.total_cost
```

即：**只有「激活 + 默认 + 已提交」的 BOM 的成本会被写进对应物料的 `valuation_rate`**。

数据自证：**261/261** 个「有 active+default BOM」的 USTX 物料，`Item.valuation_rate` 与 BOM `total_cost` **逐位相等**（6 位小数，0 例外）。

因此：

- **79 个存在但无 BOM** → 回写任务不覆盖它们 → 保持 0。
- **10 个不存在** → 自然算 0。
- 这 79 个也没有任何库存/采购（上一节表格），所以 ERPNext 标准逻辑也推不出估价 → 只能是 0。
- **7 个非零**（`KS0004-100=13.48`、`KS0004-54=6.13`、`KS0011-40=6.13`、`KS0018-SET7=101.07`、`KS0026-340=377.17`、`KS0251-SET6=101.07`、`KS0529-45x45=0.001`）**查不到自动来源**——已排除库存、采购、PR、WO、BOM、模板→变体传播（`key_test/update_variant_valuation_rate.py`，其模板的 `valuation_rate` 全为 0，推不出这些值）。它们正好等于 sheet 里那 7 个非零值，说明 sheet 的「美中加工成本, USTX」确实是**回退读 `valuation_rate`**（与前作一致），但值本身怎么来的**未证实**（形态上像人工填报：两个 SET 款共用一个 101.07、一个 0.001 占位）。

## 现有 309 张 BOM 的来源（时间分布）

### USTX 侧创建时间分布（逐月）

| 月份 | 张数 |
|------|------|
| 2025-10 | **190** |
| 2025-11 | 46 |
| 2025-12 | 29 |
| 2026-01 | 25 |
| 2026-02 | 1 |
| 2026-03 | 1 |
| 2026-04 | 5 |
| 2026-07 | 1 |
| 2026-08 | 2 |
| 2026-09 | 9 |
| **合计** | **309** |

**结论：是聚集的。** 2025-10 ~ 2026-01 四个月占 **290/309（93.9%）**，其中 2025-10 一个月就占 61.5%。这是一次**批量回填**的形态，之后只零星新增（2026-04 的 5 张、2026-09 的 9 张等）。

代码侧有对应的批量入口：`work_order_task/.../utils/bom.py:316` 附近的 `trigger_batch_process_sxbzcp_boms` 与 `bom_batch_process.py:358` 的 `get_sxbzcp_boms_to_process`——正是为「历史 SXBZCP BOM 批量补建国外分公司 BOM」而写。

### 绍兴侧对应情况

| 指标 | 数值 |
|------|------|
| `SXBZCP#%` 物料 | 921 |
| `SXBZCP#%` BOM 总数 | 588（其中已提交 583、已取消 4、草稿 1） |
| 有 BOM 的 `SXBZCP#` 物料 | 393 |
| 已提交且**含 PP棉 行**的 SXBZCP BOM | **365** |

绍兴侧 BOM 的创建时间**从 2024-08 起长期铺开**（2024-08:83、2024-12:77、2025-03:90、2025-11:52、2025-12:35、2026-01:25……），本身就是持续维护的正常产线数据，**不像 USTX 侧那样是一次性批次**。USTX 侧的 309 张，是从这 365 张「含 PP棉」的绍兴 BOM 里挑出来复制的产物。

### 父子关系（内容级验证，不是照抄命名）

**命名不可靠**（`-001` 是通用尾号，309/309 都与某张绍兴 BOM 尾号相同，属于巧合级证据），所以直接比对**行内容**：

`SXBZCP#KS0001-100`（`BOM-SXBZCP#KS0001-100-001`，5 行）：

| item_code | qty | rate |
|-----------|-----|------|
| `PPM1500-7D51-SILICONIZED-NEW` | 3.2 | 11.00 |
| `KZKP1010-5#-IRONBOTTOMSURFACE-SILVERY` | 6.0 | 0.095 |
| `NBZX1470-60x12x53-5STOREY-YELLOW` | 1.0 | 4.00 |
| `WBZX1460-62x40x55-5STOREY-YELLOW` | 0.334 | 7.00 |
| `ZKD1010-800x1000-0.06-SMALLEDGEOPENING-TRANSPARENT` | 1.0 | 1.76 |

`USTXBZCP#KS0001-100`（`BOM-USTXBZCP#KS0001-100-001`，**1 行**）：

| item_code | qty | rate | amount |
|-----------|-----|------|--------|
| `PPM1500-15D64-SILICONIZED-NEW` | **3.2** | **15.00** | **48.00** |

三条线索全部对上，证实「整张复制 → 只留 PP棉 → 换料 → 换价」：

1. **同源**：qty 3.2 逐位相同。
2. **换料**：`PPM1500-7D51-…` → `PPM1500-15D64-…`（正是 `utils/bom.py:197-198` 写死的替换规则）。
3. **换价**：rate 11.00 → 15.00（`utils/bom.py` 把 `rm_cost_as_per` 改成 `Price List`、`buying_price_list` = `美中USTX标准采购`），48.00 = `raw_material_cost`，与 `ustx_boms_all.csv` 里该 BOM 的 `raw_material_cost=48.0` 完全一致。
4. **过滤**：4 行非 PP棉 组件被丢弃，只剩 1 行——这就是「只保留 PP棉」的直接后果。

**机制确认**（`work_order_task` app）：

- `hooks.py:238-241` —— `"BOM": {"on_submit": "work_order_task.doc_events.auto_copy_bom_on_submit", ...}`
- `doc_events.py:400` —— `auto_copy_bom_on_submit(doc, method)` → 调 `auto_copy_bom_for_sxbzcp_on_submit(doc.name)`
- `utils/bom.py:25-29` —— 前缀映射 `美中USTX包装成品# → USTXBZCP#`
- `utils/bom.py:147` —— `copy_bom_with_new_item()`，用 `frappe.copy_doc` **整张**复制（含 items + operations）

## 能否用同样方法补齐

把 96 个按「补齐路径上缺哪一环」分组（详见证据清单 E2）：

| 组 | 描述 | 数量 | 能否补齐 |
|----|------|------|---------|
| A | `USTXBZCP#` 与 `SXBZCP#` 两侧物料**都没建** | 5 | ❌ 无源 |
| B | 仅缺 `USTXBZCP#` 配套物料（绍兴侧有） | 5 | ⚠️ 需先建物料；且绍兴 BOM 无 PP棉（见下） |
| C | 缺绍兴对应变体（USTX 侧反而有） | 2 | ❌ 无源 |
| D | 绍兴有**已提交+默认+启用** BOM | 31 | ⚠️ 物料齐，但绍兴 BOM **PP棉 行 = 0** |
| E | 绍兴仅有**草稿** BOM | 1 | ❌ 草稿不触发（`on_submit` 未发生） |
| G | 绍兴有物料但**无任何 BOM** | 52 | ❌ 无源 |

（B 组 5 个 + D 组 31 个 = **36 个**，即「绍兴侧有已提交+默认 BOM」的全集。）

**这 36 张绍兴 BOM 的 PP棉 行数全部为 0**（逐张计数；唯一的例外 `BOM-SXBZCP#KS0018-SET7-001` 只有 1 行 PP棉，但它是**草稿**，`docstatus=0`）。

因此失败点是**确定的**：

```
utils/bom.py:316  auto_copy_bom_for_sxbzcp_on_submit()
utils/bom.py:381  check_pp_cotton_in_bom_items(doc)
utils/bom.py:344  → 早退 'BOM物料子表中不存在物料组为"PP棉"的物料，无法执行自动复制'
```

**即使绕过这道闸门**，`copy_bom_with_new_item`（`utils/bom.py:183-187`）只保留 `item_group='PP棉'` 的行，源里一行都没有 → 产出一张 **items 为空的 BOM**（只剩工序），`raw_material_cost=0`。这不是「补齐」，是污染。

反面佐证：**现有 309 张 USTX BOM 里，PP棉 行为 0 的张数是 0**。整条链路的不变式就是「有 USTX BOM ⟺ 源 BOM 有 PP棉」。这 96 个之所以没有 BOM，正是因为源侧不满足。

其他潜在阻碍（本次**未**逐条实测，仅列出）：

- **缺 PP棉 料**：已确认为主因（36/36）。
- 缺重量模板：`USTX` 物料本身无 `weight_template_variant` 字段值（前作已述），但复制链路不依赖它 → 疑非阻碍。
- 缺价目 / 工序工站缺失：`copy_bom_with_new_item` 里取工站失败是 `try/except` 静默跳过（`utils/bom.py` 工站段），**不会阻断**复制。
- 配套物料创建依赖 `key_test.add_item_semi.create_supporting_items_and_variants`，导入失败时降级为「跳过创建、继续复制」。

## PP棉→海绵 对复制的影响

> 前置事实：**除 1 张草稿外，309 张 USTX BOM 全部含 ≥1 行 PP棉**；UTX 侧 BOM 的物料行就是「绍兴 BOM 里那些 PP棉 行」的换料换价镜像。

### ① 新版绍兴 BOM 换成海绵，提交它触发复制 → 会不会导致海外 BOM 没有 PP棉 填充料？

会。而且**不是「复制出没有 PP棉 的海外 BOM」，而是「整条复制被闸门拦下、什么都不做」**：

- `auto_copy_bom_for_sxbzcp_on_submit` 在复制前先跑 `check_pp_cotton_in_bom_items`（`utils/bom.py:381`）。海绵 BOM 里没有 `item_group='PP棉'` 的行 → 直接返回失败（`utils/bom.py:344`），复制不发生。
- 副作用是「静默停更」：新绍兴版 BOM 的工艺改动也**不会**传播到海外，海外仍停在旧 PP棉 版上。

### ② `copy_bom_with_new_item` 到底复制**哪一张**绍兴 BOM？

**取决于调用方传进来的 `original_bom`：**

| 入口 | 源 BOM 的取法 | 文件:行 |
|------|--------------|--------|
| **自动（提交触发）** | **刚提交的那张** —— `auto_copy_bom_on_submit(doc)` → `auto_copy_bom_for_sxbzcp_on_submit(doc.name)` → `frappe.get_doc("BOM", docname)` | `doc_events.py:400`、`utils/bom.py:316` |
| **表单按钮（手工）** | **当前打开的那张** —— 前端传 `bom_name: frm.doc.name` | `public/js/bom.js:322` |
| **白名单函数（可指定）** | **调用者给什么就用什么** —— `copy_bom_for_supporting_items(bom_name, selected_prefixes)` 第一行 `original_bom = frappe.get_doc("BOM", bom_name)` | `utils/bom.py:7` |
| **批量回填** | **只挑「最新 + 已提交 + 默认 + 启用」那张** | `bom_batch_process.py:358-395` |

关键：**没有任何一处会自动去追「绍兴的 active+default」那一步**——自动路径用的是「刚提交的」，批量路径用的才是「默认的」。所以「只能从最新的复制」这个印象**只对批量路径成立**。

### ③ 海外已有一张 PP棉 版 BOM，再复制一次海绵版会怎样？

**结论：新建一张 BOM，并抢走默认；旧的 PP棉 版**不会被删**，但会被降为「非默认」（`is_active` 视情形）。** 依据：

- `copy_bom_with_new_item` 用 `frappe.copy_doc(source)` **整张复制**，随后 `new_bom.insert()` + `new_bom.submit()`（`utils/bom.py:292-298`）。`copy_doc` 会把源 BOM 的 `is_default` 一并带过来。
- ERPNext `BOM.manage_default_bom`（`apps/erpnext/.../bom/bom.py:523-544`）：`if self.is_default and self.is_active:` → `set_default(self, "item")`，**把同物料的其它 BOM 的 `is_default` 置 0**。
- 数据自证：36 个「一物多 BOM」的 USTX 物料里，**35 个的默认就是最新那张**，且**没有任何物料存在两个默认**。
- 旧 BOM **不会被删除**：`KS0455-92x56x75` 有 6 张 BOM（2025-10-30 的 `-001` 到 2026-09-15 的 `-006`），`-001`..`-005` 全部 `is_active=1 / is_default=0` 且**各自的 PP棉 行仍完整保留（npp=1）**。

⚠️ **一个真实隐患**：`check_bom_exists`（`utils/bom.py:127-136`）本意是「已存在就跳过」，但它把条件写成了 `"docstatus": 0`（注释却写「确保是已提交状态」，应为 1）。已提交的 BOM 是 `docstatus=1`，所以这道「已存在」闸门**实际上永不命中** → 重复复制会不断**新建** BOM。这正是 36 个物料上出现 45 张重复 BOM 的原因。

⚠️ **另一个隐患（海绵场景专属）**：`copy_bom_for_supporting_items` 本身**没有** PP棉 闸门（闸门只在 `auto_copy_bom_for_sxbzcp_on_submit` 里）。如果操作员在**海绵版绍兴 BOM** 的表单上点「复制BOM」按钮，会走完 `copy_bom_with_new_item` → 过滤后 items 为 **0 行** → 生成一张只有工序、`raw_material_cost=0` 的 BOM，并且**因为抢默认，直接把该 USTX 物料的加工成本打成「只剩工费」**。批量路径有 `check_what_needs_to_be_created`（`bom_batch_process.py:447-464`）拦「不包含PP棉物料」，**表单按钮没有**。

### ④ 关键诉求：旧的非默认 PP棉 BOM，能否作为「国外分公司复制 PP棉填充」的**显式**源？

**能。** 依据：

1. **函数签名就是显式的**：`copy_bom_for_supporting_items(bom_name, selected_prefixes)`，第一行 `frappe.get_doc("BOM", bom_name)`，**不校验 `is_default` / `is_active` / `docstatus`**（`utils/bom.py:7`）。
2. **前端按钮传的就是当前打开的那张**：`public/js/bom.js:322` → `bom_name: frm.doc.name`。所以**打开任意一张旧绍兴 BOM（哪怕已非默认、甚至已取消）+ 点按钮**，就是一次显式复制。
3. **旧 BOM 的行不会被抹掉**：复制是「新建 + 抢默认」，不改写旧文档。`KS0455` 的 6 张 BOM 里，没被选为默认的那 5 张**至今保留完整 PP棉 行**。
4. **批量路径做不到**：`get_sxbzcp_boms_to_process`（`bom_batch_process.py:358-395`）的 SQL 硬写 `docstatus=1 AND is_default=1 AND is_active=1` + `MAX(creation)`，**只能拿最新的默认版**。要批量从旧版复制，得改这个查询或另写脚本。

**但有两个必须一起处理的点**（否则「参考源」会变成「替身」）：

- 复制出的新 BOM 会**抢默认**（见 ③）。如果目的只是「留一张 PP棉 参考」，需要复制后把 `is_default` 调回去，或干脆把新 BOM 建成 `is_active=0`。
- `check_bom_exists` 的 `docstatus` bug 让「已存在就跳过」失效，重复执行会**堆重复 BOM**。

## 可操作建议

1. **不要对这 96 个硬跑批量复制**。36 个绍兴源 BOM 的 PP棉 行为 0，跑也是空 BOM 或直接早退；剩余 60 个连源都没有。要补，先补**绍兴侧**的 BOM 与 PP棉 料。
2. **改海绵前，先把「参考源」固化**：
   - 对将要改填充物的款，**先记下当前绍兴 BOM 的 `name`**（如 `BOM-SXBZCP#KS0001-100-001`）。改版后这张会变成非默认（或 amend 后旧版被取消），但**仍在 `tabBOM` 里**，可作为显式复制源。
   - 若担心被后续操作波及，可把旧 PP棉 版单独留档（导出 BOM Item 行到 `out/`，本仓库已有 `ustx_boms_all.csv` 这类抽取先例）。
3. **改填充物时优先「新建新版 BOM」而不是「改旧版」**：旧版保持 `docstatus=1` 能让 `copy_bom_for_supporting_items` 直接取用；amend 会让旧版变 `docstatus=2`（仍可取，但批量 SQL 会排除）。
4. **显式复制的正确姿势**：打开目标**旧绍兴 BOM** → 点表单上的「复制BOM」按钮 → 得到海外 BOM 后，**立即核对 `is_default`**（它会抢默认）。
5. **建议修 `check_bom_exists`**（`utils/bom.py:136` 的 `docstatus` 由 `0` 改 `1`），否则任何「补齐/重跑」都会堆重复 BOM。
6. **建议给表单按钮路径补 PP棉 闸门**（与 `auto_copy_bom_for_sxbzcp_on_submit` / `check_what_needs_to_be_created` 对齐），否则海绵切换后，人工点按钮会造出 `raw_material_cost=0` 的默认 BOM。

## 未证实 / 存疑

1. **7 个非零 `valuation_rate` 的来源未证实。** 已排除：库存（`tabBin`=0、`tabStock Ledger Entry`=0）、采购（PO=0、PR=0）、工单（0）、BOM（0 张，含已取消/已删）、模板→变体传播（`key_test/update_variant_valuation_rate.py`，相关模板 `valuation_rate` 全为 0）。**未排除**：人工填报、本仓库之外的脚本、或早期数据导入。形态（两个 SET 款共用 101.07、一个 0.001 占位）更像人工。
2. **`is_default` 由 `frappe.copy_doc` 复制过来的判断是推断，未做写入实测。** 支撑：36 个一物多 BOM 物料中 35 个「默认 = 最新」，且无任何物料存在两个默认。**未验证** ERPNext 15.43.3 是否对 BOM 设了 `no_copy`。
3. **例外：`USTXBZCP#KS0101-45` 的 3 张 BOM 全部 `is_active=0`**（该物料在 USTX 侧没有默认 BOM）。成因未查（怀疑与 `bom_batch_process.update_existing_foreign_bom` 的就地更新路径有关，未核实）。
4. **`copy_bom_for_supporting_items` 对「已取消（`docstatus=2`）的绍兴 BOM」是否可用，未实测。** 代码上 `frappe.get_doc` 不筛 docstatus、`frappe.copy_doc` 应可复制，但未实跑。
5. **`sx_counterpart` 侧 52 个「有物料但无任何 BOM」的具体原因未逐个查**（可能是款式停用、或绍兴侧也还没做）。
6. **`-00N` 尾号 309/309 全命中**仅作旁证，不作为父子关系证据（已改用行内容比对，见上）。
7. **本报告未核对 N 个「SXBZCP 含 PP棉(365) − USTX BOM(309) = 56」的差额去路**（可能对应「USTX 物料未建」或「同一物料多 BOM」）。

## 证据清单（路径:行号 / SQL）

### 代码（EN 生产库 `/home/frappe/frappe-bench/apps/`）

| 位置 | 内容 |
|------|------|
| `work_order_task/work_order_task/hooks.py:238-241` | `BOM.on_submit → work_order_task.doc_events.auto_copy_bom_on_submit` |
| `work_order_task/work_order_task/doc_events.py:400-423` | `auto_copy_bom_on_submit(doc, method)` → 调 `auto_copy_bom_for_sxbzcp_on_submit(doc.name)` |
| `work_order_task/work_order_task/work_order_task/utils/bom.py:7` | `copy_bom_for_supporting_items(bom_name, selected_prefixes)` —— **显式源，白名单** |
| 同上 `:25-29` | 前缀映射 `波兰PL包装成品#→PLBZCP#` / `美东USNJ…→USNJBZCP#` / `美中USTX包装成品#→USTXBZCP#` |
| 同上 `:127-136` | `check_bom_exists()` —— **`"docstatus": 0` 写错，闸门失效** |
| 同上 `:147` | `copy_bom_with_new_item(original_bom, new_item_code)`，`frappe.copy_doc` 整张复制 |
| 同上 `:183-187` | **只保留 `item_group='PP棉'` 的行** |
| 同上 `:197-198` | `PPM1500-7D51-SILICONIZED-NEW → PPM1500-15D64-SILICONIZED-NEW` 替换 |
| 同上 `:209-…` | 工站映射 `→ 美中USTX包装`，改写 `hour_rate*`（失败静默 `try/except`） |
| 同上 `:292-298` | `is_active=1` → `insert()` → `submit()` |
| 同上 `:316` | `auto_copy_bom_for_sxbzcp_on_submit(docname)` —— 自动入口，取 `docname` 对应 BOM |
| 同上 `:344` | 早退文案：`'…不存在物料组为"PP棉"的物料，无法执行自动复制'` |
| 同上 `:381` | `check_pp_cotton_in_bom_items(bom_doc)` —— **硬闸门** |
| `work_order_task/.../utils/bom_batch_process.py:61` | `update_existing_foreign_bom(...)` —— **就地更新**已存在的海外 BOM（不取消/不删除） |
| 同上 `:358-395` | `get_sxbzcp_boms_to_process()` —— SQL 硬筛 `docstatus=1 AND is_default=1 AND is_active=1` + `MAX(creation)` |
| 同上 `:447-464` | `check_what_needs_to_be_created()` —— 批量路径的 PP棉 闸门（`'不包含PP棉物料'`） |
| `work_order_task/work_order_task/public/js/bom.js:312-322` | 表单按钮 → `method: ...utils.bom.copy_bom_for_supporting_items`，`bom_name: frm.doc.name` |
| `key_test/key_test/hooks.py:233-235` | `BOM.on_update` / `on_update_after_submit → bom_cost_synchronizer.sync_bom_cost_to_item` |
| `key_test/key_test/hooks.py:249-251` | cron `0 3 * * *` → `bom_cost_synchronizer.scheduled_sync_all_bom_costs` |
| `key_test/key_test/bom_cost_synchronizer.py:25-58` | `sync_bom_cost_to_item`：`if not doc.is_active or not doc.is_default: return`；`item_doc.valuation_rate = new_cost` |
| 同上 `:87-119` | `scheduled_sync_all_bom_costs`：`BOM(is_active=1,is_default=1,docstatus=1)` → `item_doc.valuation_rate = bom.total_cost` |
| `key_test/key_test/update_variant_valuation_rate.py:4-23` | 模板→变体传播（模板 `valuation_rate`，本例全 0） |
| `erpnext/erpnext/manufacturing/doctype/bom/bom.py:523-544` | `manage_default_bom()` —— `if self.is_default and self.is_active: set_default(self,"item")`（抢默认、置他人 `is_default=0`） |
| 同上 `:273` | `on_cancel` → `is_active=0, is_default=0` |

### SQL / 快照（均为只读；快照落在 `tongtool_order_cost/out/ustx_wage_sim/`，`out/` 已 gitignore）

- **E0 基础快照**
  - `q_ustx_items.tsv` ← `SELECT name,item_group,disabled,is_stock_item,valuation_rate,creation,variant_of,has_variants FROM tabItem WHERE name LIKE 'USTXBZCP#%'` → 609 行
  - `q_ustx_boms.tsv` ← `SELECT name,item,creation,is_active,is_default,docstatus,total_cost FROM tabBOM WHERE item LIKE 'USTXBZCP#%'` → 309 行
  - `q_sxbzcp_items.tsv` ← `… tabItem WHERE name LIKE 'SXBZCP#%'` → 921 行
  - `q_sxbzcp_boms.tsv` ← `… tabBOM WHERE item LIKE 'SXBZCP#%'` → 588 行
  - `q_sx_counterpart_boms.tsv` ← 96 个对应的 `SXBZCP#` BOM + 每张的 PP棉 行数/总行数
- **E1 引用面（96 个全为 0）** —— `SELECT … FROM tabBin / tabStock Ledger Entry / tabPurchase Order Item / tabPurchase Receipt Item / tabWork Order / tabSales Order Item / tabDelivery Note Item / tabBOM Item / tabBOM / tabProduct Bundle / tabProduct Bundle Item / tabItem Customer Detail WHERE item_code IN (<96>)`
- **E2 分组** —— `q_sx_counterpart_boms.tsv` + `tabItem`，按「两侧物料是否存在 / 绍兴 BOM 状态」分 A/B/C/D/E/G
- **E3 时间分布** —— `SELECT DATE_FORMAT(creation,'%Y-%m') m, COUNT(*) FROM tabBOM WHERE item LIKE 'USTXBZCP#%' GROUP BY m`
- **E4 父子内容比对** —— `SELECT item_code,qty,rate,amount FROM \`tabBOM Item\` WHERE parent IN ('BOM-SXBZCP#KS0001-100-001','BOM-USTXBZCP#KS0001-100-001')`
- **E5 重复 BOM** —— `is_default=1` 计 261、`is_active=1` 计 304、`docstatus` 分布 `{1:308, 0:1}`；一物多 BOM 36 个（默认=最新 35 / 无默认 1）
- **E6 多 BOM 保留 PP棉** —— `SELECT b.name,b.creation,b.is_default,b.is_active, (PP棉行数) FROM tabBOM b WHERE b.item='USTXBZCP#KS0455-92x56x75'` → 6 张，npp 全为 1
- **E7 已删除痕迹** —— `SELECT deleted_doctype,deleted_name,owner,creation FROM \`tabDeleted Document\` WHERE deleted_name IN (<96>)` → 1 条（Item `USTXBZCP#KS0489-100x90x8`）
- **E8 PP棉 覆盖** —— 已提交 SXBZCP BOM 583 张，其中含 PP棉 365 张；USTX 侧「PP棉 行 = 0」的已提交 BOM **0 张**

### 本地复算脚本（scratch，`out/` 已 gitignore）

- `out/ustx_wage_sim/_analyze_nobom.py`（96 画像）
- `out/ustx_wage_sim/_analyze2.py`（`valuation_rate` vs BOM、多 BOM、绍兴时间分布）
- `out/ustx_wage_sim/_analyze3.py`（A/B/C/D/E/G 分组 + 家族分析）
